"""The can't-fix notice and its AI analysis (board H, part H8; docs/HEAL_TO_INTENT.md sections
10 and 12): when self-healing stops at can't fix, the network's team is told, Mercury's facts
first, then the analysis, advisory, then the link.

**The notifier, never the loop.** This is the heal's notify step (section 4, step 6), run after
the decision and the act (`run`, from the runner), and the only code besides the pages that
draws an analysis (`modules/ai/heal_analysis.py`). The heal loop's modules never import it
back or read anything it keeps (tests/test_heal_analysis_never_read.py).

**Which incidents** (`due`): each incident of the network's step log that stopped at can't fix
(`heal_analysis.CANT_FIX`) within `NEW_WITHIN_S` of now, and not yet taken: an incident is
taken once (`heal_analysis.claim`, under the store's lock across processes), so it is analysed
and told about once; a past incident is never analysed after a deploy or a restart.

**Never delaying the notification** (section 12): the analysis is started, and the message
waits for it up to `WAIT_S` (60 s, the operator's bound). Back in time, the message carries it.
Not back, the message goes without it, saying "AI analysis: pending", and when it arrives (or
`FOLLOW_UP_WAIT_S` passes, said) a follow-up goes on the same thread: the event ``analysis``,
an email's ``In-Reply-To`` under the first message, a webhook's second event with the
incident's id. A failure or refusal is stated in place (off, capped, couldn't analyse, the
provider not answering), never a silent absence. With no team told about can't fix, nothing is
sent, and the analysis is still made and kept for Needs attention's row.

**Mercury's diagnosis first, on an Alert incident** (H17; 19.3, N14): an incident the decision
stopped at can't fix at Tier 3 is diagnosed before anything is sent (`auto_diagnose.run`, a
runbook chosen from what raised it, read-only), waited for up to `auto_diagnose.WAIT_S`, so
its analysis reads it as the pack's ``diagnosis`` section and its message carries it by kind
after what was detected. Not finished in time, the message says so, the analysis is asked
without it, and the follow-up carries it (the event ``diagnosis`` when the analysis was already
in the first message). A Never incident is not diagnosed automatically: Diagnose… on its row
runs one.

**Cleared by itself, never told** (C2825, H11 W5): a diagnosis that reads the symptom gone
(`auto_diagnose.symptom_gone`) is waited out to the flap window since the incident's last
trigger (`_cleared`); still standing, quiet and read gone from its stores, the incident ends
"cleared by itself by HH:MM UTC, nothing to do", with no analysis and no message. And an
incident whose newest decision is nothing to heal by the time it would be told is not told
(`_withheld`). A can't-fix is told once per incident (``asked``): one standing and judged again
(C2813) is never told twice.

**What a message carries** (`facts`): only `notify.message.FIELDS`, every byte through the
egress mask at its sender. Each step is said in Mercury's words with the incident's
configuration lines withheld (`evidence_pack.withhold`), and so is the analysis's text, which
may quote the intent section's masked lines: configuration lines are never in a message
(section 10); they are one click away in Mercury.
"""

import logging
import threading
import time

log = logging.getLogger(__name__)

#: How long the first message waits for the analysis (section 12: the operator's bound,
#: named there `heal_analysis_wait_seconds`). A constant, not a setting, until section 12's
#: measurement of Explain's answer time on the host is made: no measurement yet says it should
#: move, and a setting nobody needs to change is one more thing to get wrong.
WAIT_S = 60.0
#: The notice's steps, in order, for the manual's How it works page (H10).
STEPS = (("due", "Find each new can't-fix: recorded in the last 10 minutes, not yet told"),
         ("claim", "Take it once, under the store's lock, so it is told and analysed once"),
         ("diagnose", "An Alert incident: run Mercury's diagnosis first, read-only, waited for "
                      "up to 150 s, so the analysis and the message carry it"),
         ("cleared", "When the diagnosis reads the symptom gone, wait out the flap window: "
                     "still gone and quiet, it cleared by itself, and nothing is sent"),
         ("analyse", "Start its AI analysis, a background call, if the feature is on"),
         ("wait", "Wait for the analysis up to 60 s, never longer"),
         ("send", "Send Mercury's facts, then the analysis or its state (pending, not run, "
                  "couldn't analyse), then the link, to the network's team"),
         ("follow_up", "When a pending analysis arrives, send it on the same thread"))


def follow_up_wait_s() -> float:
    """How long a slow analysis is waited for before its follow-up says it did not come: the
    reservation's life (`gateway.reservation_ttl_s`, 2.5 times one call's longest time in the
    adapter), so no call still counted against the caps is given up on."""
    from modules.ai import gateway
    return gateway.reservation_ttl_s()


#: A can't-fix is told about only this soon after it was recorded: a runner starting after a
#: deploy never notifies, or spends, on the past (two of the runner's passes, 30 s each, with
#: room for a decision's own time).
NEW_WITHIN_S = 600
#: The job id a notice's analysis is recorded under (its trigger's job).
JOB_PREFIX = "heal-notice"
#: The event a can't-fix's first message is, and its follow-up's.
EVENT, FOLLOW_UP = "cant_fix", "analysis"
#: The follow-up that carries only Mercury's diagnosis (H17: the analysis was in the first).
DIAGNOSIS_FOLLOW_UP = "diagnosis"
#: What to do, by the kind the decision found (section 9's can't-fix row: "the action the
#: reason names").
TODO = {
    "physical": "check the link: its cable, optics and far end; the configuration is at intent",
    "unknown_cause": "read the symptom's own source: the configuration is at intent, so the "
                     "cause is elsewhere",
    "security_acl": "decide on the ACL: adopt it into intent (Capture), or remove it yourself "
                    "through a deploy; self-healing never removes a security control",
    "credentials": "decide on the change: accounts and AAA change only through their own "
                   "operations",
    "management_path": "decide on the change to Mercury's path to the device; a change there "
                       "needs a repair route independent of it",
    "multi_device": "read each device's departure: a change across devices is a person's",
}
TODO_DEFAULT = ("read what Mercury tried, then adopt the change into intent (Capture) or put "
                "the device back on its golden through a deploy")
#: The act's outcomes that notify as a can't-fix, and what each says to do.
TODO_OUTCOME = {
    "symptom_remains": "the configuration is back at intent and the symptom remains: read the "
                       "symptom's own source, the cause is not the configuration",
    "rolled_back": "verify failed and Mercury undid its own fix: read what verify saw, then "
                   "lift the network's halt once you know why",
}


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# ── An action's end (board H's amendment, 19.4 "Records and History", H23) ──────────────────
#
# 17.7 item 6, "notification of every autonomous action": each action's act, once it ends, is
# told on its incident's thread (`notify.delivery` threads a later message under the first),
# as the event its end needs a person for, matching its Needs attention row: the row's action
# label IS the message's What to do (`action_todo`, which `attention` draws). An action that
# ended as it should is told only when it was automatic (the policy's), as ``action`` under the
# team's "every automatic heal"; a person's own approved action that ended well is theirs.

#: Each action family's end, as the event it is told as (`notify.message.EVENTS`): ``action``
#: (it worked, told only when automatic), ``cant_fix`` (a person must look), ``halted`` (it
#: halted the network, guard 14). An end absent here is not told.
ACTION_EVENTS = {
    "bounce": {"bounced": "action", "still_flapping": "cant_fix", "not_formed": "cant_fix",
               "unverified": "cant_fix", "reverted": "halted", "repaired": "halted",
               "failed": "halted", "refused": "cant_fix"},
    "clear": {"cleared": "action", "not_back": "cant_fix", "reset": "halted",
              "unverified": "cant_fix", "rejected": "cant_fix", "refused": "cant_fix"},
    "dampening": {"rolled_back": "cant_fix", "unverified": "cant_fix", "failed": "halted",
                  "refused": "cant_fix"},
}
#: An action end's notice's steps, in order (`run_actions`), for the manual's How it works page.
ACTION_STEPS = (("due", "Find each action that ended in the last 10 minutes and is to be told: "
                        "every end a person must look at, and a success only when automatic"),
                ("claim", "Take it once, under the store's lock, so it is told once"),
                ("send", "Send what it acted on and how it ended, its steps, and What to do in "
                         "its item's own words, on its incident's thread"))
#: The outcomes that are each family's success: no Needs attention row, and told only when
#: automatic.
ACTION_DONE = {"bounce": "bounced", "clear": "cleared", "dampening": "dampened"}
#: The Who is told choice an event is sent under when it is not its own (`heal_notify.CHOICES`'
#: events, as each network saved them): an automatic action that worked is "every automatic
#: heal"'s, so a team that chose it is told without saving its choices again.
TOLD_AS = {"action": "healed"}


def action_todo(kind: str, outcome: str, host: str, *, interface: str = "", peer: str = "",
                far_device: str = "", far_interface: str = "") -> str:
    """What to do about an action's end, in the words its Needs attention row's action draws
    (`attention._heal_bounce_rows`, `_heal_clear_rows`, `_heal_dampening_rows`) and its notice
    carries: one sentence, so the row and the message never say different things."""
    from modules.heal import steplog

    fam = steplog.ACTION_FAMILY.get(kind or "", "")
    if outcome == ACTION_DONE.get(fam):
        return f"nothing: read the steps on {host}'s History if you want them"
    if fam == "bounce":
        return (f"Read the bounce's steps on {host}'s History, check {interface} and its far end "
                f"({far_device or 'not named'} {far_interface or ''}), then acknowledge with "
                "what you found").replace(" )", ")")
    if fam == "clear":
        return (f"Read the clear's steps on {host}'s History, check the BGP session to {peer} "
                "and the neighbour's own device, then acknowledge with what you found")
    if fam == "dampening":
        if outcome == "propose":
            return (f"Review the change for {host} {interface}, then approve it by its hash with "
                    "a reason, or decline it with a reason")
        return (f"Read the change's steps on {host}'s History, check {interface}'s dampening "
                "and its intent, then act on what they show")
    return TODO_DEFAULT


def actions_due(network: str, now: float = None) -> list:
    """The network's action acts that ended within `NEW_WITHIN_S` of now and are to be told
    (`ACTION_EVENTS`; a success only when automatic: its decision ``heal``, the policy's), not
    yet told (`heal_analysis.told`): ``[{"act", "decision", "event", "family"}]``, oldest first.
    A store that cannot be read gives none, logged: nothing is told twice for want of a read."""
    from modules.ai import heal_analysis as HA
    from modules.heal import steplog

    now = time.time() if now is None else float(now)
    got = steplog.read(network)
    if got["state"] == "unreadable":
        log.error("heal notice: %s's step log cannot be read: %s", network, got["error"])
        return []
    kept = HA.read(network)
    if kept["state"] == "unreadable":
        log.error("heal notice: %s", kept["error"])
        return []
    told = {r.get("decision") for r in kept["rows"] if r.get("row") == "told"}
    decided = {r.get("decision"): r for r in got["rows"] if r.get("row") == "decision"}
    out = []
    for r in got["rows"]:
        fam = steplog.ACTION_FAMILY.get(r.get("kind") or "", "")
        if r.get("row") != "act" or not fam or not r.get("decision") or not r.get("incident"):
            continue
        if r["decision"] in told or now - float(r.get("epoch") or 0) > NEW_WITHIN_S:
            continue
        d = decided.get(r["decision"]) or {}
        outcome = r.get("outcome") or ""
        event = ACTION_EVENTS[fam].get(outcome)
        if outcome == ACTION_DONE[fam]:
            event = "action" if d.get("outcome") == "heal" else None
        if event:
            out.append({"act": r, "decision": d, "event": event, "family": fam})
    return out


def action_facts(network: str, due_one: dict, entry: dict = None) -> dict:
    """One action end's event fields (`notify.message.FIELDS`), Mercury's facts first: what it
    acted on and how it ended, the decision that chose it and when, each step of the act and
    its result, What to do (`action_todo`, its row's words) and the link. The incident's
    configuration lines (its program) are withheld, as a can't-fix's are."""
    from modules import evidence_pack as EP
    from modules.heal import steplog
    from modules.heal.actions import KIND_WORDS

    r, d = due_one["act"], due_one["decision"] or {}
    a = r.get("action") or d.get("action") or {}
    host = r.get("device") or ""
    lines = lines_of(network, entry or {"program": list(d.get("program") or [])})
    what = steplog.subject({"device": host, "action": a, "kind": r.get("kind")})
    words = f"{what} {steplog.mark(r.get('outcome') or '', r.get('kind') or '')}: " \
            f"{r.get('words') or ''}"
    return {"incident": r.get("incident") or "", "event": due_one["event"],
            "network": network, "device": host,
            "kind": KIND_WORDS.get(r.get("kind"), r.get("kind") or ""),
            "outcome": EP.withhold(words, lines),
            "detected": EP.withhold(d.get("words") or "", lines),
            "detected_at": d.get("at") or "",
            "steps": [{"what": EP.withhold(f"{s.get('step')}: {s.get('words') or ''}", lines),
                       "result": s.get("result") or ""} for s in (r.get("steps") or [])[:20]],
            "todo": action_todo(r.get("kind") or "", r.get("outcome") or "", host,
                                interface=a.get("interface") or "", peer=a.get("peer") or "",
                                far_device=a.get("far_device") or "",
                                far_interface=a.get("far_interface") or ""),
            "link": f"/v2/device/{host}?tab=history" if host else ""}


def action_notice(network: str, due_one: dict, *, deliver=None) -> dict:
    """Tell the network's team about one action's end (`action_facts`), on its incident's
    thread, as its event. Never raises: a delivery that fails is said and kept."""
    from modules.heal import steplog

    deliver = deliver or _deliver
    r = due_one["act"]
    try:
        entry = steplog.incident(network, r.get("incident") or "")
    except Exception as exc:                          # said; the decision's program is withheld
        log.error("heal notice: %s's incident %s cannot be read: %s", network,
                  r.get("incident"), exc)
        entry = None
    event = action_facts(network, due_one, entry)
    return _sent(network, r.get("incident") or "", due_one["event"], event, deliver)


def run_actions(network: str, *, now: float = None, starter=None) -> dict:
    """The notify step's actions: each action end due (`actions_due`) taken once
    (`heal_analysis.claim_told`, under the store's lock across processes) and told in its own
    thread (*starter*, a thread unless given). ``{"network", "told": [decision ids],
    "failed"}``."""
    from modules.ai import heal_analysis as HA

    out = {"network": network, "told": [], "failed": []}
    for one in actions_due(network, now):
        r = one["act"]
        try:
            if not HA.claim_told(network, r["decision"], incident=r.get("incident") or "",
                                 event=one["event"], device=r.get("device") or "", now=now):
                continue
        except Exception as exc:                      # said; the next pass reads it again
            out["failed"].append(f"{r['decision']}: {type(exc).__name__}: {exc}")
            continue
        if starter is not None:
            starter(network, one)
        else:
            threading.Thread(target=action_notice, args=(network, one), daemon=True,
                             name=f"heal-action-notice-{r['decision']}").start()
        out["told"].append(r["decision"])
    return out


# ── Which incidents ───────────────────────────────────────────────────────────────────────────

def due(network: str, now: float = None) -> list:
    """The network's can't-fix incidents recorded in the last `NEW_WITHIN_S`, newest last, that
    were not taken for a notice (`heal_analysis.claim`'s ``asked`` rows). A step log or a store
    that cannot be read gives none, logged: nothing is told twice for want of a read."""
    from modules.ai import heal_analysis as HA
    from modules.heal import steplog

    now = time.time() if now is None else float(now)
    got = steplog.incidents(network)
    if got["state"] == "unreadable":
        log.error("heal notice: %s's step log cannot be read: %s", network, got["error"])
        return []
    kept = HA.read(network)
    if kept["state"] == "unreadable":
        log.error("heal notice: %s", kept["error"])
        return []
    taken = {r.get("incident") for r in kept["rows"] if r.get("row") == "asked"}
    return [e for e in got["entries"] if e.get("outcome") in HA.CANT_FIX and e.get("incident")
            and e["incident"] not in taken and now - float(e.get("epoch") or 0) <= NEW_WITHIN_S]


def run(network: str, *, now: float = None, starter=None, wait_s: float = None,
        action_starter=None) -> dict:
    """The notify step of a runner's pass: each due incident taken once and its notice started
    as its own thread (*starter*, a thread unless given), so the runner never waits on the 60
    s; then each action end due (`run_actions`, *action_starter*). ``{"network", "started":
    [incident ids], "told": [action decision ids], "failed"}``."""
    out = {"network": network, "started": [], "failed": []}
    acts = run_actions(network, now=now, starter=action_starter)
    out["told"], out["failed"] = acts["told"], list(acts["failed"])
    from modules.ai import heal_analysis as HA

    for e in due(network, now):
        inc = e["incident"]
        job = f"{JOB_PREFIX}-{inc}"
        try:
            if not HA.claim(network, inc, job=job, device=e.get("device") or "", now=now):
                continue
        except Exception as exc:                      # said; the next pass reads it again
            out["failed"].append(f"{inc}: {type(exc).__name__}: {exc}")
            continue
        kw = {} if wait_s is None else {"wait_s": wait_s}
        if starter is not None:
            starter(network, inc, job, **kw)
        else:
            threading.Thread(target=notice, args=(network, inc), kwargs=dict(kw, job=job),
                             daemon=True, name=f"heal-notice-{inc}").start()
        out["started"].append(inc)
    return out


# ── The message ───────────────────────────────────────────────────────────────────────────────

def lines_of(network: str, entry: dict) -> list:
    """The incident's configuration lines (its program and its units' lines, masked as kept),
    and the intent section's masked lines its analysis may quote: what a message withholds."""
    from modules import evidence_pack as EP
    from modules.heal import decisions

    units = []
    for did in entry.get("decisions") or []:
        try:
            units += list((decisions.find(network, did) or {}).get("units") or [])
        except Exception as exc:                      # said; the program's lines still count
            log.warning("heal notice: %s's decision %s could not be read: %s", network, did,
                        exc)
    return EP.config_lines(entry, units)


def facts(network: str, entry: dict, incident: dict = None) -> dict:
    """The can't-fix event's fields (`notify.message.FIELDS`), Mercury's facts first: what was
    detected and when, each step and its result, the outcome, what to do, the link."""
    from modules import evidence_pack as EP
    from modules.heal import kinds

    lines = lines_of(network, entry)
    trig = list((incident or {}).get("triggers") or [])
    first = trig[0] if trig else {}
    device = entry.get("device") or ""
    outcome = entry.get("outcome") or "cant_fix"
    todo = TODO_OUTCOME.get(outcome) or TODO.get(entry.get("kind") or "", TODO_DEFAULT)
    return {"incident": entry.get("incident") or "", "event": EVENT, "network": network,
            "device": device,
            "kind": kinds.KIND_WORDS.get(entry.get("kind"), entry.get("kind") or ""),
            "outcome": EP.withhold(entry.get("words") or outcome.replace("_", " "), lines),
            "detected": EP.withhold(first.get("words") or "", lines),
            "detected_at": first.get("at") or (incident or {}).get("opened_at") or "",
            "steps": [{"what": EP.withhold(f"{s.get('step')}: {s.get('words') or ''}", lines),
                       "result": s.get("result") or ""}
                      for s in (entry.get("steps") or [])[:20]],
            "todo": todo, "link": f"/v2/device/{device}?tab=history" if device else ""}


def analysis_block(result: dict, lines) -> dict:
    """The analysis's block for a message (`heal_analysis.block`), its text with the incident's
    configuration lines withheld: a message never carries a configuration line."""
    from modules import evidence_pack as EP
    from modules.ai import heal_analysis as HA

    b = HA.block(result)
    out = {k: EP.withhold(b.get(k) or "", lines) for k in ("state", "words", "label", "score",
                                                           "rationale")}
    out["hypotheses"] = [{"claim": EP.withhold(h["claim"], lines),
                          "next": EP.withhold(h["next"], lines)} for h in b["hypotheses"]]
    return out


def _deliver(network: str, event: dict) -> dict:
    from modules import heal_notify
    from modules.notify import delivery

    # A can't-fix's follow-ups go to whoever was told the first message; an action's end to
    # the teams that chose its own event (H23), an automatic action's under the team's "every
    # automatic heal" (`TOLD_AS`).
    which = event.get("event") or EVENT
    teams = heal_notify.teams_for(network, EVENT if which in (
        EVENT, FOLLOW_UP, DIAGNOSIS_FOLLOW_UP) else TOLD_AS.get(which, which))
    if not teams:
        return {"ok": True, "sent": 0, "failed": 0, "error": "", "nobody": True}
    return delivery.deliver_event(event, teams)


def diagnosis_block(d, lines, *, bound_s: float = None) -> dict:
    """Mercury's diagnosis for a message (`auto_diagnose.summary`: by kind, never a value it
    compared), its words with the incident's configuration lines withheld; *d* None is a
    diagnosis not finished within *bound_s*, its result following on the same thread."""
    from modules import evidence_pack as EP
    from modules.heal import auto_diagnose as AD

    if d is None:
        return {"state": "not_finished", "hypotheses": [], "ruled_out": [], "reads": "",
                "words": (f"not finished within {int(round(bound_s or 0))} s; its result "
                          "follows on this thread")}
    s = AD.summary(d)
    return {"state": s["state"], "words": EP.withhold(s["words"], lines),
            "reads": s["reads"],
            "hypotheses": [{"claim": EP.withhold(h["claim"], lines), "strength": h["strength"]}
                           for h in s["hypotheses"]],
            "ruled_out": [EP.withhold(r, lines) for r in s["ruled_out"]]}


def _diagnosis_thread(network: str, incident_id: str, diagnose) -> tuple:
    """The Alert incident's automatic diagnosis started in its own thread: ``(held, done)``,
    *held* ``["got"]`` its diagnosis once *done* is set."""
    from modules.heal import auto_diagnose as AD

    held, done = {}, threading.Event()

    def work():
        try:
            held["got"] = AD.run(network, incident_id, AD.ALERT, diagnose=diagnose)
        except Exception as exc:                      # said in the message, never raised
            log.error("heal notice: the diagnosis of %s raised: %s", incident_id, exc)
            held["got"] = {"state": "refused", "incident": incident_id,
                           "words": f"not diagnosed: {type(exc).__name__}: {exc}"}
        finally:
            done.set()

    threading.Thread(target=work, daemon=True, name=f"heal-diagnose-{incident_id}").start()
    return held, done


def _action_consider(network: str, incident_id: str, diagnosis: dict) -> dict:
    """The action module the diagnosis's choice belongs to (`diagnose.action_for`): the port
    bounce and the OSPF reset (`bounce.consider`, H20), or the BGP session clear
    (`session_clear.consider`, H21); each answers ``none`` for a choice not its own."""
    from modules.heal import bounce, diagnose, session_clear

    kind = diagnose.action_for(diagnosis or {}).get("kind")
    if kind in session_clear.KINDS:
        return session_clear.consider(network, incident_id, diagnosis)
    return bounce.consider(network, incident_id, diagnosis)


def _consider(network: str, incident_id: str, diagnosis: dict, consider=None) -> dict:
    """The action the diagnosis chooses, judged and recorded before the notice is sent
    (`bounce.consider`: in dry run "would bounce", nothing sent; in AUTO a ``heal`` decision
    the act's runner takes). Never raises: a notice is sent whatever it found."""
    try:
        if consider is None:
            consider = _action_consider
        return consider(network, incident_id, diagnosis)
    except Exception as exc:                          # said in the log; the notice still goes
        log.error("heal notice: %s's action for %s was not considered: %s", network,
                  incident_id, exc)
        return {"state": "failed", "words": f"{type(exc).__name__}: {exc}"}


def notice(network: str, incident_id: str, *, job: str = "", wait_s: float = WAIT_S,
           follow_s: float = None, send=None, deliver=None, now: float = None,
           diagnose=None, diagnosis_wait_s: float = None, consider=None, quiet_wait=None,
           symptom=None) -> dict:
    """Tell the network's team about one can't-fix, its analysis waited for up to *wait_s*
    (section 12), then the follow-up when it was not back in time. An Alert incident (Tier 3,
    `auto_diagnose.is_alert`) is diagnosed first (H17, 19.3), waited for up to
    *diagnosis_wait_s* (`auto_diagnose.WAIT_S`), so its analysis reads the diagnosis and its
    message carries it; not back in time, the message says so and the follow-up carries it.
    ``{"incident", "first", "follow_up", "analysis", "diagnosis"}``: each message's state and
    delivery. *send* replaces the provider (tests), *deliver* the delivery (``(network,
    event) -> result``), *diagnose* the diagnosis run (`diagnose.run`'s shape), *quiet_wait*
    the flap window's wait and *symptom* the stores' read (`_cleared`). A diagnosis that read
    the symptom gone and stayed quiet ends it, ``{"cleared": decision}``, nothing sent; an
    incident whose newest decision is nothing to heal is ``{"first": {"withheld": why}}``."""
    from modules.ai import heal_analysis as HA
    from modules.heal import auto_diagnose as AD
    from modules.heal import incidents, steplog

    deliver = deliver or _deliver
    job = job or f"{JOB_PREFIX}-{incident_id}"
    follow_s = follow_up_wait_s() if follow_s is None else float(follow_s)
    diag_wait = AD.WAIT_S if diagnosis_wait_s is None else float(diagnosis_wait_s)
    try:
        alert = AD.is_alert(steplog.incident(network, incident_id))
    except Exception as exc:                          # read again below, and said there
        log.error("heal notice: %s's incident %s cannot be read: %s", network, incident_id,
                  exc)
        alert = False
    dheld, ddone, diagnosed = {}, None, True
    if alert:
        dheld, ddone = _diagnosis_thread(network, incident_id, diagnose)
        diagnosed = ddone.wait(max(0.0, diag_wait))
        if diagnosed and dheld.get("got"):
            # C2825: the diagnosis read the symptom gone, and it stayed quiet: cleared by itself,
            # nothing to do, and no "could not fix" message, no analysis.
            cleared = _cleared(network, incident_id, dheld["got"], wait=quiet_wait,
                               symptom=symptom)
            if cleared:
                return {"incident": incident_id, "first": None, "follow_up": None,
                        "analysis": None, "diagnosis": dheld["got"], "cleared": cleared}
            # 19.3: "then item 2's actions are considered (19.4), and then the notice is sent".
            _consider(network, incident_id, dheld["got"], consider)
    why = _withheld(network, incident_id)
    if why:
        return {"incident": incident_id, "first": {"withheld": why}, "follow_up": None,
                "analysis": None, "diagnosis": dheld.get("got")}
    held, done = {}, threading.Event()

    def work():
        try:
            held["got"] = HA.analyse(network, incident_id, job=job, send=send, now=now)
        except Exception as exc:                      # said in the follow-up, never raised
            log.error("heal notice: the analysis of %s raised: %s", incident_id, exc)
            held["got"] = {"state": "couldnt_analyse", "incident": incident_id,
                           "words": HA.words_of("couldnt_analyse",
                                                f"{type(exc).__name__}: {exc}")}
        finally:
            done.set()

    threading.Thread(target=work, daemon=True, name=f"heal-analysis-{incident_id}").start()
    back = done.wait(max(0.0, float(wait_s)))
    try:
        entry = steplog.incident(network, incident_id)
        found = incidents.read(network).get("incidents") or []
    except Exception as exc:                          # said; nothing is sent from the unread
        log.error("heal notice: %s's incident %s cannot be read: %s", network, incident_id,
                  exc)
        return {"incident": incident_id, "first": {"error": str(exc)}, "follow_up": None,
                "analysis": held.get("got"), "diagnosis": dheld.get("got")}
    incident = next((i for i in found if i.get("id") == incident_id), {})
    lines = lines_of(network, entry)
    event = facts(network, entry, incident)
    got = held.get("got") if back else None
    event["analysis"] = analysis_block(got, lines)
    if alert:
        event["diagnosis"] = diagnosis_block(dheld.get("got") if diagnosed else None, lines,
                                             bound_s=diag_wait)
    first = _sent(network, incident_id, EVENT, event, deliver)
    out = {"incident": incident_id, "first": first, "follow_up": None, "analysis": got,
           "diagnosis": dheld.get("got") if diagnosed else None}
    if back and diagnosed:
        return out
    follow = dict(event)
    which = FOLLOW_UP
    # One deadline for the follow-up: what is still out is waited for until then, together.
    deadline = time.monotonic() + max(0.0, follow_s)
    if not diagnosed:
        # The diagnosis's own bound is its reads' (C2546), so it is waited for as long as the
        # analysis's follow-up is: it ends, or the follow-up says it did not.
        if not ddone.wait(max(0.0, deadline - time.monotonic())):
            follow["diagnosis"] = {"state": "not_finished", "hypotheses": [], "ruled_out": [],
                                   "reads": "", "words": (
                                       f"not finished within {int(round(diag_wait + follow_s))}"
                                       " s; its record is on the device's History when it "
                                       "ends")}
        else:
            follow["diagnosis"] = diagnosis_block(dheld.get("got"), lines)
        out["diagnosis"] = dheld.get("got")
        if back:
            which = DIAGNOSIS_FOLLOW_UP
    if not back:
        if not done.wait(max(0.0, deadline - time.monotonic())):
            later = {"state": "no_answer", "words": HA.words_of(
                "no_answer", f"{int(round(wait_s + follow_s))} s")}
        else:
            later = held.get("got")
        follow["analysis"] = analysis_block(later, lines)
        out["analysis"] = later
    follow["event"] = which
    out["follow_up"] = _sent(network, incident_id, which, follow, deliver)
    return out


def _withheld(network: str, incident_id: str) -> str:
    """C2825: why the can't-fix notice of *incident_id* is not sent, or ``""``: the incident's
    newest decision (not an action's: an action's own "came back by itself" is its guard's, read
    once) is nothing to heal, recorded after the can't-fix (its symptom cleared by itself, or
    its device read back at its golden). A store that cannot be read withholds nothing: the
    notice goes, as before."""
    from modules.heal import decisions

    try:
        rows = [d for d in decisions.decisions(network) if d.get("incident") == incident_id
                and not (d.get("action") or {}).get("kind")]
    except Exception as exc:                          # said; the notice goes
        log.error("heal notice: %s's decisions could not be read: %s", network, exc)
        return ""
    if not rows:
        return ""
    newest = max(rows, key=lambda d: float(d.get("epoch") or 0))
    if newest.get("outcome") != "nothing":
        return ""
    return (f"not sent: the incident's newest decision {newest.get('id')} found nothing to "
            f"heal ({newest.get('words') or ''})")


def _cleared(network: str, incident_id: str, d: dict, *, wait=None, symptom=None,
             clock=time.time) -> dict:
    """C2825 (H11 W5): when Mercury's diagnosis *d* of an Alert incident read its symptom gone
    (`auto_diagnose.symptom_gone`), the notice waits until nothing has been logged for the flap
    window since the incident's last trigger (*wait*, `time.sleep` unless given; at most the
    window), then reads again: still standing, no trigger since, and every symptom read gone
    from its store (*symptom*, `decide.Sources.symptom_now` unless given), the incident ends as
    cleared by itself, nothing to do (`decide.end_standing`), and no message is sent. Anything
    else returns ``{}``, and the notice goes as before: a link still flapping is told."""
    from modules.heal import auto_diagnose as AD
    from modules.heal import decide, incidents, policy
    from modules.heal.guards import value

    gone = AD.symptom_gone(d)
    if not gone:
        return {}

    def standing():
        got = incidents.read(network).get("incidents") or []
        return next((i for i in got if i.get("id") == incident_id
                     and i.get("state") == "standing"), {})

    def last_of(inc):
        return max((float(t.get("epoch") or 0) for t in decide.judged_triggers(inc)),
                   default=0.0)

    try:
        inc = standing()
        if not inc:
            return {}
        quiet_s = float(value(policy.current(network, clock()), "heal_flap_minutes") or 10) * 60
        last = last_of(inc)
        left = last + quiet_s - clock()
        if left > 0:
            (wait or time.sleep)(min(left, quiet_s))
        again = standing()
        if not again or last_of(again) > last:
            return {}
        state = (symptom or decide.Sources(network).symptom_now)(
            again["device"], decide.judged_triggers(again))
        if state != "gone":
            return {}
        now, minutes = clock(), int(quiet_s // 60)
        return decide.end_standing(
            network, incident_id,
            (f"nothing to heal: every symptom the incident named has cleared by itself by "
             f"{decide._hhmm(now)} UTC, nothing to do: Mercury's diagnosis "
             f"{d.get('id') or ''} read {gone}, each symptom reads gone from its store, and "
             f"nothing was logged for {minutes} minutes since its last trigger; no \"could not "
             "fix\" message was sent"),
            now=now, by="the can't-fix notice",
            read_words=(f"Mercury's diagnosis {d.get('id') or ''} "
                        f"({d.get('finished_at') or '?'}): {gone}; every symptom read again from "
                        f"its store: gone; quiet {minutes} minutes since its last trigger"))
    except Exception as exc:                          # said; the notice goes as before
        log.error("heal notice: whether %s cleared by itself could not be judged: %s",
                  incident_id, exc)
        return {}


def _sent(network: str, incident_id: str, which: str, event: dict, deliver) -> dict:
    from modules.ai import heal_analysis as HA

    state = (event.get("analysis") or {}).get("state") or ""
    try:
        got = deliver(network, event)
    except Exception as exc:                          # said and kept; never raised
        log.error("heal notice: the %s notice of %s was not sent: %s", which, incident_id, exc)
        got = {"ok": False, "sent": 0, "failed": 0, "error": f"{type(exc).__name__}: {exc}"}
    try:
        HA.record_notice(network, incident_id, event=which, analysis_state=state, delivery=got)
    except Exception as exc:                          # the delivery log holds each attempt
        log.error("heal notice: the %s notice of %s is not in the store: %s", which,
                  incident_id, exc)
    return dict(got, state=state)
