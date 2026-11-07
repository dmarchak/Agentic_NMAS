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


def run(network: str, *, now: float = None, starter=None, wait_s: float = None) -> dict:
    """The notify step of a runner's pass: each due incident taken once and its notice started
    as its own thread (*starter*, a thread unless given), so the runner never waits on the 60
    s. ``{"network", "started": [incident ids], "failed"}``."""
    out = {"network": network, "started": [], "failed": []}
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

    teams = heal_notify.teams_for(network, EVENT)
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


def notice(network: str, incident_id: str, *, job: str = "", wait_s: float = WAIT_S,
           follow_s: float = None, send=None, deliver=None, now: float = None,
           diagnose=None, diagnosis_wait_s: float = None) -> dict:
    """Tell the network's team about one can't-fix, its analysis waited for up to *wait_s*
    (section 12), then the follow-up when it was not back in time. An Alert incident (Tier 3,
    `auto_diagnose.is_alert`) is diagnosed first (H17, 19.3), waited for up to
    *diagnosis_wait_s* (`auto_diagnose.WAIT_S`), so its analysis reads the diagnosis and its
    message carries it; not back in time, the message says so and the follow-up carries it.
    ``{"incident", "first", "follow_up", "analysis", "diagnosis"}``: each message's state and
    delivery. *send* replaces the provider (tests), *deliver* the delivery (``(network,
    event) -> result``), *diagnose* the diagnosis run (`diagnose.run`'s shape)."""
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
