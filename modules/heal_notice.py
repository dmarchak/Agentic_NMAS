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
"cleared by itself at HH:MM UTC, nothing to do" (C2813's wording: "at" for a time Mercury
measured, "by" only for an estimate or a deadline), with no analysis and no message. And an
incident whose newest decision is nothing to heal by the time it would be told is not told
(`_withheld`). A can't-fix is told once per incident (``asked``): one standing and judged again
(C2813) is never told twice.

**R1, AI troubleshooting by itself** (the operator, 2026-11-14; `run_fixit`, after the notices):
on a network whose ``fixit_auto`` switch is on (off by default; Settings › AI), each new failure
of Mercury's fix on an open incident, recorded after the switch went on, is taken ONCE
(`fixit.incident.claim_start`) and its investigation started in its own thread
(`fixit_investigation`, a background call under the feature's trigger), inside the incident's
cap, the feature's caps and the day cap; a proposal is told to the team, its BLUF first
(`proposal_notice`, the event ``proposal``).

**What a message carries** (`facts`): only `notify.message.FIELDS`, every byte through the
egress mask at its sender. Each step is said in Mercury's words with the incident's
configuration lines withheld (`evidence_pack.withhold`), and so is the analysis's text, which
may quote the intent section's masked lines: configuration lines are never in a message
(section 10); they are one click away in Mercury.
"""

import logging
import os
import re
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
    # C2839: a security kind is a can't-fix only while its removal is not measured; otherwise
    # it is a proposal, the person's two answers on its card.
    "security_acl": "decide on the ACL: keep it (add it to intent in the device's intent "
                    "editor), or remove it through the device's deploy plan; self-healing "
                    "proposes it once its removal is measured on the platform",
    "security_control": "decide on the security control: keep it (add it to intent in the "
                        "device's intent editor), or remove it through the device's deploy "
                        "plan; self-healing proposes it once its removal is measured",
    "credentials": "decide on the change: accounts and AAA change only through their own "
                   "operations",
    "management_path": "decide on the change to Mercury's path to the device; a change there "
                       "needs a repair route independent of it",
    "multi_device": "read each device's departure: a change across devices is a person's",
}
#: C2824's two answers (C2876): a can't-fix is a change that something went wrong beside, so it
#: is never offered Capture, which would record it as the approved state.
TODO_DEFAULT = ("decide on the change: put it back to intent through the device's deploy plan, "
                "or keep it by adding it to intent in the device's intent editor")
#: An AI analysis not yet measured on its recorded cases, as a message says it beside its label
#: (`analysis_block`; the incident page's AI troubleshooting section words it so).
NOT_MEASURED_WORDS = "its answers are not measured on recorded cases yet"
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
            # The act's steps as the stepper says them, as a can't-fix's are (`steps_said`).
            "steps": steps_said(network, host, {"incident": r.get("incident") or "",
                                                "state": "done",
                                                "steps": [dict(s, row="act", decision=r.get(
                                                    "decision") or "")
                                                          for s in r.get("steps") or []]},
                                lines),
            "todo": action_todo(r.get("kind") or "", r.get("outcome") or "", host,
                                interface=a.get("interface") or "", peer=a.get("peer") or "",
                                far_device=a.get("far_device") or "",
                                far_interface=a.get("far_interface") or ""),
            "link": incident_link(network, r.get("incident") or "", host)}


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
    try:
        out["fixit"] = run_fixit(network, now=now)
    except Exception as exc:                          # said; the next pass reads it again
        log.exception("heal notice: %s's automatic troubleshooting pass failed", network)
        out["failed"].append(f"automatic troubleshooting: {type(exc).__name__}: {exc}")
    return out


# ── R1: AI troubleshooting started by itself when Mercury's fix fails ────────────────────────

#: The most investigations one pass starts (the caps hold the spend; this holds a burst).
FIXIT_MOST_PER_PASS = 3
#: How long a started investigation is waited for before another failure of its incident may
#: start one: the reservation's life, as a slow analysis is waited for (`follow_up_wait_s`).
FIXIT_JOB_PREFIX = "fixit-auto"
#: The steps of the automatic start, as the manual's How it works page names them.
FIXIT_STEPS = (("switch", "Read the network's switch: off (the default), nothing is read or "
                          "taken; on, only failures recorded after it was turned on count"),
               ("auto", "Self-healing's mode is not asked: the AI only proposes and a person "
                        "approves, so it investigates in every mode, Dry run included"),
               ("failures", "Find each new failure of Mercury's fix on an open incident: a "
                            "can't-fix, a hold a person resolves, an act that did not verify, "
                            "an approved plan that stopped"),
               ("choice", "The AI troubleshooting mode Off, or hosted AI off: take it with no "
                          "AI call"),
               ("caps", "Over the incident's cap, the feature's own day or month cap, or the "
                        "day cap: take it with no AI call, saying which cap"),
               ("claim", "Take the failure once, under the incident record's lock"),
               ("ask", "Ask the AI to investigate, as a background call on that failure"),
               ("notify", "A proposal: tell the network's team, its bottom line first, with "
                          "the incident's link"))


def _fixit_state(inc, trigger: dict, now: float, reserved_usd: float = 0.0, *,
                 feature: dict = None, reserved_calls: int = 0) -> tuple:
    """``(state, which, words)`` a start takes for *inc* now: ``off``, ``capped`` (*which* names
    the cap) or ``started``. An automatic start's (*trigger* its background trigger) asks its
    feature's switch and caps too; a catch-up's at turn-on (a person's trigger) asks the mode,
    hosted AI, the incident's cap, the feature's own day and month caps (*feature*, the
    feature's background trigger, its caps the ones the turn-on just recorded) and the day cap,
    with *reserved_usd* and *reserved_calls* the worst cases of the investigations ahead of it
    in the same catch-up (the operator, C3745: "Catch-up starts count against every cap"). Reads
    the settings and the record of AI calls."""
    from modules.ai import background, calls, fixit_troubleshoot as AIT, gateway, triggers
    from modules.fixit import policy as P

    bg = trigger.get("kind") == triggers.BACKGROUND
    if feature is None and bg:
        feature = trigger
    # The incident's own network's mode (C3769), else the installation's.
    off = P.ai_refusal(getattr(inc, "network", None))
    if off:
        return "off", "", off
    if not gateway.hosted_allowed()["allowed"]:
        return "off", "", "hosted AI is off"
    why = background.admit(trigger) if bg else ""
    if why:
        return "off", "", why
    worst = AIT.worst_usd()
    cs = P.cap_state(inc, worst)
    if cs["state"] != "allowed":
        return "capped", "incident", cs["words"].replace("Retry isn't available", "Not started",
                                                         1)
    day = calls.today()
    held = float(reserved_usd or 0.0)
    # C3753: the calls in flight (the gateway's reservations, and the catch-ups' planned starts,
    # C3752) are counted as the gateway counts them, so a start planned as fitting is never
    # refused at the gateway after one call; an unreadable store is never read as none.
    from modules.ai import reservations
    open_ = reservations.open_reservations()
    if open_["state"] != "ok":
        return "capped", "day", (f"the AI calls in flight cannot be read ({open_['error']}), "
                                 "so they cannot be counted against the caps")
    flying = reservations.in_flight(open_["held"])
    if feature is not None:
        mine = reservations.in_flight(open_["held"], feature=feature.get("feature"),
                                      network=feature.get("network"))
        over = background.over_cap(feature, worst, day, reserved={
            "usd": held + mine["usd"], "calls": int(reserved_calls) + mine["calls"]})
    else:
        over = None
    if over:
        return ("capped" if over["kind"] == "feature_cap" else "off",
                over.get("cap") or "day", over["why"])
    cap = gateway.day_cap()
    if cap is not None:
        spent = calls.spent_usd(day)
        if spent.get("usd") is None:
            return "capped", "day", (f"today's AI spend cannot be read ({spent.get('error')}), "
                                     "so it cannot be compared with the day cap")
        if float(spent["usd"]) + flying["usd"] + held + worst > cap:
            return "capped", "day", (
                f"today's AI spend ${float(spent['usd']):.2f}"
                + (f" plus ${flying['usd']:.2f} reserved by {flying['calls']} call(s) in flight"
                   if flying["calls"] else "")
                + (f" plus ${held:.2f} held by the investigations started with it" if held
                   else "")
                + f" plus this investigation's worst case ${worst:.2f} would pass the day cap "
                f"of ${cap:.2f}")
    return "started", "", ""


def run_fixit(network: str, *, now: float = None, starter=None) -> dict:
    """R1's pass (`modules/fixit/auto.py`): each new failure of Mercury's fix on an open
    incident, recorded since the network's stamp, taken ONCE (`incident.claim_start`) and,
    when the choices are on and the caps allow it, its investigation started as its own
    thread (*starter*, a thread unless given). ``{"network", "started", "capped", "off",
    "failed"}``, each a list of failure keys."""
    from modules.ai import fixit_troubleshoot as AIT
    from modules.fixit import auto as A
    from modules.fixit import incident as F

    at = time.time() if now is None else float(now)
    out = {"network": network, "started": [], "capped": [], "off": [], "failed": []}
    sw = A.switch(network)
    if not sw["on"]:
        # Off (the default on every network): nothing is read further and nothing is taken;
        # a failure while it is off is before any later turn-on's time, so it never starts by
        # itself (turning it on catches up only on what the person ticks, `start_catch_up`).
        return out
    # In every mode of self-healing (the operator, 2026-11-15: "the AI only proposes, and
    # nothing runs without a person's approval, so it investigates in Dry run too").
    heal = None
    # R1's one reader, the catch-up's too (`auto.pending`).
    got = A.pending(network)
    if got["state"] != "ok":
        out["failed"].append(got["error"])
        return out
    out["failed"].extend(got["failed"])
    bound = follow_up_wait_s()
    for p in got["incidents"]:
        if len(out["started"]) >= FIXIT_MOST_PER_PASS:
            break
        iid, inc, fs = p["id"], p["incident"], p["failures"]
        try:
            have = A.taken(inc)
            new = [f for f in fs if f["key"] not in have and not A.eligible(f, sw, heal)]
            if not new or A.in_flight(inc, at, bound):
                continue
            f = new[0]
            job = f"{FIXIT_JOB_PREFIX}-{iid}-{len(have) + 1}"
            trigger = AIT.background_trigger(network, job, f["key"])
            # C3752: planned and claimed under the network's one start lock, so a turn-on's
            # catch-up in another worker plans against what this start holds, and this one
            # against the catch-up's reserved starts (`_fixit_state` counts them).
            from modules import filestore
            with filestore.PathLock(start_lock_path(network)):
                state, which, words = _fixit_state(inc, trigger, at)
                line = F.claim_start(inc, f["key"], trigger="auto", state=state, job=job,
                                     which=which, words=words, now=at,
                                     failure={k: f[k] for k in ("kind", "id", "outcome",
                                                                "at")},
                                     busy_s=bound)
        except Exception as exc:                      # said; the next pass reads it again
            out["failed"].append(f"{iid}: {type(exc).__name__}: {exc}")
            continue
        if line is None:
            continue
        out[state if state in ("started", "capped", "off") else "failed"].append(f["key"])
        if state != "started":
            continue
        if starter is not None:
            starter(network, iid, f["key"], job)
        else:
            # The same job path as a person's press (`troubleshoot_job.start`): listed under In
            # progress, its end announced.
            from modules import troubleshoot_job
            troubleshoot_job.start(network, iid, f"job:{job}",
                            lambda _j, i=iid, k=f["key"], jb=job: fixit_investigation(
                                network, i, k, jb), label=f"Automatic AI troubleshooting: {iid}",
                            actor_kind="policy", key=f["key"], trigger="auto")
    return out


def fixit_investigation(network: str, incident_id: str, key: str, job: str, *,
                        send=None, deliver=None) -> dict:
    """One automatic investigation (R1), its start already taken: AI troubleshooting's own
    investigation as ``fixit_auto``'s background call on the failure *key*
    (`fixit_troubleshoot.troubleshoot` with its trigger), and, when it proposes a plan, the
    team told (`proposal_notice`). A refusal before anything was sent is kept as the failure's
    second start line (``failed``), so the page says why. *send* replaces the provider and
    *deliver* the relay (tests)."""
    from modules.ai import fixit_troubleshoot as AIT
    from modules.ai import triggers

    def ask(found, inc):
        trigger = AIT.background_trigger(network, job, key)
        return AIT.troubleshoot(network, found, inc, actor=triggers.actor_of(trigger),
                                actor_verified="", person=False, trigger=trigger, send=send)
    return _investigation(network, incident_id, key, ask, deliver=deliver, trigger="auto")


def catch_up_investigation(network: str, incident_id: str, key: str, *, actor: str,
                           verified: str, send=None, deliver=None, counts: bool = True,
                           planned: str = "") -> dict:
    """One investigation started at the turn-on of ``fixit_auto`` on an incident the person
    ticked (`start_catch_up`), its start already taken under the failure's own key: the same
    investigation as the automatic start's (`_investigation`), its trigger the person who ticked
    it (`triggers.person`: a person's choice, so its calls count as theirs and the gateway
    checks they are this request's verified person; run inside the turn-on's request context,
    copied into its job). *counts* (C3751): its calls count toward ``fixit_auto``'s spend on
    the network too, for the feature's day and month caps (a turn-on's catch-up; G6's press
    is a person's alone, `start_catch_up`'s *press*). *planned*: the reservation its start
    was planned under (C3752), settled the moment the investigation's own call reserves."""
    from modules.ai import fixit_troubleshoot as AIT
    from modules.ai import presses
    from modules.fixit import auto as A

    def ask(found, inc):
        # The planned start's reservation hands over to the call's own (`gateway`): settled
        # here, just before the call reserves, so the two never count twice for long.
        _settle_planned(planned)
        # One turn-on starts several of these, each in its own job under the turn-on's press
        # key: each one's calls are its own work of the press, named by its incident and its
        # failure (C3771: they shared the key's first slot, and every one after the first
        # took the first's answer).
        with presses.within(f"{incident_id}:{key}"):
            return AIT.troubleshoot(network, found, inc, actor=actor, actor_verified=verified,
                                    person=True, send=send,
                                    counts_for={"feature": A.FEATURE, "network": network}
                                    if counts else None)
    try:
        return _investigation(network, incident_id, key, ask, deliver=deliver,
                              trigger="person", by=actor, verified=verified)
    finally:
        _settle_planned(planned)        # whatever it ended in: never left to its expiry


def _investigation(network: str, incident_id: str, key: str, ask, *, deliver, trigger: str,
                   by: str = "", verified: str = "") -> dict:
    """The one investigation path of a start taken under a failure's key (the automatic start's
    and the catch-up's): the incident resolved, *ask* ``(found, incident)`` asking AI
    troubleshooting, a refusal or a failure before anything was sent kept as the failure's
    ``failed`` start line (as *trigger*, with *by* and *verified* for a person's), and a
    proposal told to the team (`proposal_notice`)."""
    from modules import incident_page, troubleshoot_job
    from modules.ai import fixit_troubleshoot as AIT
    from modules.fixit import section

    found = incident_page.resolve(network, incident_id)
    inc = section.incident_of(network, found)["incident"] if found["found"] == "page" else None
    if inc is None:
        return {"state": "failed", "words": f"{incident_id} has no page"}
    who = {"by": by, "verified": verified} if by else {}
    # C3696: a saved self-heal script whose R4 match the problem holds fires first, with no AI
    # call (`saved_plans.fire_matching`): one in Dry run records what it would run, and one a
    # person promoted runs through the runner; healed so, the AI is not asked.
    from modules.nsot import saved_plans
    fired = saved_plans.fire_matching(network, found)
    healed = next((f for f in fired if f.get("mode") == "auto" and f.get("ok")), None)
    if healed:
        return {"state": "healed_by_script", "script": healed, "words": (
            f"Healed by saved script {healed['key']}: no AI used")}
    running = next((f for f in fired if f.get("mode") == "auto"
                    and f.get("state") == "firing"), None)
    if running:
        return {"state": "script_running", "script": running, "words": (
            f"Saved script {running['key']} is running on this incident: the AI is not asked")}
    try:
        got = ask(found, inc)
    except AIT.Refused as exc:
        troubleshoot_job.record_failure(inc, key, str(exc), trigger=trigger, **who)
        return {"state": "failed", "words": str(exc)}
    except Exception as exc:                          # noqa: BLE001 (kept, then the job's)
        troubleshoot_job.record_failure(inc, key, f"{type(exc).__name__}: {exc}",
                                        trigger=trigger, **who)
        raise
    if got.get("state") == "failed" and not got.get("proposal"):
        troubleshoot_job.record_failure(inc, key, got.get("words") or "", trigger=trigger, **who)
    if got.get("state") == "proposed":
        try:
            proposal_notice(network, incident_id, deliver=deliver)
        except Exception as exc:                      # noqa: BLE001 (said; the page has it)
            log.error("fixit auto: %s: its proposal was not told: %s", incident_id, exc)
    return got


def start_catch_up(network: str, ticked, *, actor: str, verified: str, now: float = None,
                   starter=None, press: str = "", press_label: str = "") -> dict:
    """Turning ``fixit_auto`` on catches up on the person's choice (the operator, 2026-11-15:
    "when the switch is turned on, it starts on every open incident whose fix failed or that
    has no fix, within the caps ... records what was chosen"): each incident in *ticked* (ids)
    that `auto.catch_up` still lists is taken ONCE under its failure's own key
    (`incident.claim_start`, a person's start with *actor* and *verified*), so the automatic
    pass never starts it again for that failure, and, within the mode, hosted AI, the
    incident's cap, the feature's day and month caps and the day cap (`_fixit_state`, every
    start planned before any starts, the worst cases of the ones ahead of it held against the
    feature's caps and the day cap: C3745), its investigation started as its own job
    (`troubleshoot_job.start`, never in the request) under the person's trigger
    (`catch_up_investigation`). A cap that would be passed takes the key with no call, its
    ``which`` the cap, so the incident's card says which. Called inside the turn-on's request.
    ``{"started", "capped", "off", "skipped", "failed"}``: incident ids, *skipped* and
    *failed* ``{"id", "why"}``. *starter* ``(network, id, key, work)`` replaces the job
    (tests).

    *press* (G6, the one-button batch): the same starts made by a person's press with
    ``fixit_auto`` off, its words the start line's: the feature's switch and caps are not
    asked and its calls do not count toward it (a person's press under the incident's cap,
    the day cap and the calls in flight); *press_label* names the press on In progress."""
    from flask import copy_current_request_context

    from modules import troubleshoot_job
    from modules.ai import fixit_troubleshoot as AIT
    from modules.ai import triggers
    from modules.fixit import auto as A
    from modules.fixit import incident as F

    at = time.time() if now is None else float(now)
    bound = follow_up_wait_s()
    out = {"started": [], "capped": [], "off": [], "skipped": [], "failed": []}
    ticked = [t for t in dict.fromkeys(ticked or ())]
    if not ticked:
        return out
    trigger = triggers.person(actor)
    worst = AIT.worst_usd()
    from modules import filestore
    from modules.ai import calls, reservations

    # C3752: plan and claim under ONE lock per network across processes (two turn-ons at
    # once, a turn-on and G6's press, or either and the automatic pass in another worker take
    # turns), each planned start's worst case reserved in the AI caps' reservations before the
    # lock is let go, so every other process and the gateway count it (C3753).
    with filestore.PathLock(start_lock_path(network)):
        got = A.catch_up(network, now=at, bound_s=bound)
        listed = {i["id"]: i for i in got["items"]}
        # Every cap first, before anything starts (C3745): in tick order, each start held
        # against its incident's cap, the feature's day and month caps (the turn-on's, just
        # recorded; never for *press*, a person's press alone) and the day cap, with the worst
        # cases of the ones ahead of it reserved; the later ones past a cap are refused, naming
        # it.
        planned, held, n = [], 0.0, 0
        for iid in ticked:
            item = listed.get(iid)
            if item is None:
                out["skipped"].append({"id": iid, "why": (
                    "no longer one to start on: it was resolved, or started, since the list was "
                    "drawn" if got["state"] == "ok"
                    else f"the list cannot be read ({got['error']})")})
                continue
            try:
                feature = None if press else AIT.background_trigger(
                    network, f"catch-up-{iid}", item["failure"]["key"])
                state, which, words = _fixit_state(item["incident"], trigger, at, held,
                                                   feature=feature, reserved_calls=n)
            except Exception as exc:                      # noqa: BLE001 (said in the answer)
                out["failed"].append({"id": iid, "why": f"{type(exc).__name__}: {exc}"})
                continue
            planned.append((iid, item, state, which, words))
            if state == "started":
                held, n = held + worst, n + 1
        day = calls.today()
        for iid, item, state, which, words in planned:
            inc, f = item["incident"], item["failure"]
            hold = ""
            if state == "started":
                hold = f"fixit-start-{iid}-{len(out['started']) + 1}"
                kept = reservations.reserve(
                    hold, worst, judge=lambda _held: None, ttl_s=bound, feature=A.FEATURE,
                    network=list_slug(network), background=False, day=day, now=at,
                    counts=not press)
                if not kept["ok"]:
                    state, which = "capped", "day"
                    words = kept["refusal"]["why"]
                    hold = ""
            try:
                line = F.claim_start(inc, f["key"], trigger="person", state=state, which=which,
                                     words=(press or A.CATCH_UP_WORDS) if state == "started"
                                     else words,
                                     by=actor, verified=verified, now=at,
                                     failure={k: f[k] for k in ("kind", "id", "outcome", "at")},
                                     busy_s=bound)
            except Exception as exc:                      # noqa: BLE001 (said in the answer)
                _settle_planned(hold)
                out["failed"].append({"id": iid, "why": f"{type(exc).__name__}: {exc}"})
                continue
            if line is None:
                _settle_planned(hold)
                out["skipped"].append({"id": iid, "why": (
                    "its start was taken a moment ago, or an investigation of it is running")})
                continue
            out[state].append(iid)
            if state != "started":
                continue
            def investigate(i=iid, k=f["key"], h=hold):
                # Its planned reservation settled whatever it ends in (C3752).
                try:
                    return catch_up_investigation(network, i, k, actor=actor,
                                                  verified=verified, counts=not press,
                                                  planned=h)
                finally:
                    _settle_planned(h)
            work = copy_current_request_context(investigate)
            label = (f"AI troubleshooting, started by {press_label}: {iid}" if press else
                     f"AI troubleshooting, started at turn-on: {iid}")
            if starter is not None:
                starter(network, iid, f["key"], work)
            else:
                troubleshoot_job.start(network, iid, actor, lambda _j, w=work: w(),
                                       label=label, key=f["key"], trigger="person")
    return out


def start_lock_path(network: str) -> str:
    """The one lock a network's AI troubleshooting starts are planned and claimed under, across
    processes (C3752): a turn-on's catch-up, G6's press and the automatic pass."""
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), "heal", "fixit_starts.lock")


def list_slug(network: str) -> str:
    from modules.config import list_slug as slug

    return slug(network) if network else ""


def _settle_planned(hold: str) -> None:
    """A planned start's reservation (C3752) settled: the investigation's own call reserved, or
    the start was not taken. Never raises (`reservations.settle`)."""
    if not hold:
        return
    from modules.ai import reservations

    reservations.settle(hold, follow_up_wait_s())


def proposal_notice(network: str, incident_id: str, *, deliver=None) -> dict:
    """Tell the network's team that the AI's proposal waits (the R1 flow's step 5; event
    ``proposal``, "a fix waits for a person"), through the existing notification path: the
    BLUF first (`bluf`: what happened, its impact, then the fix), then what the AI found and
    the plan it proposes, step by step, with the incident's link. Mercury's facts and words
    only: no person's name or address, and the incident's configuration lines withheld."""
    from modules import bluf as B
    from modules import evidence_pack as EP
    from modules import incident_page
    from modules.fixit import incident as F
    from modules.fixit import plan as FP
    from modules.fixit import section

    found = incident_page.resolve(network, incident_id)
    inc = section.incident_of(network, found)["incident"]
    if inc is None:
        return {"ok": False, "error": f"{incident_id} has no incident Mercury can name"}
    rec = F.read(inc)
    line = next((ln for ln in reversed(rec["lines"]) if "proposal" in ln), None)
    plan = FP.preflight(inc, line) if line else None
    if not plan:
        return {"ok": False, "error": f"{incident_id} holds no proposal to tell"}
    lines = lines_of(network, found.get("entry") or {})
    b = B.bluf(B.model_of(found, {"kind": "approve", "label": "Approve, Modify or Deny"}))
    steps = "; then ".join(s["words"] for s in plan["steps"])
    event = {"incident": incident_id, "event": "proposal", "network": network,
             "device": inc.device,
             "lead": EP.withhold(f"{b['what']}. {b['impact']}.", lines),
             "happened": EP.withhold(f"The AI found: {plan['found']}", lines)
             if plan["found"] else "",
             "outcome": EP.withhold(f"The AI proposes: {steps}" + (
                 "" if plan["approvable"] else f". {plan['why_refused']}"), lines),
             "todo": ("Approve, Modify or Deny the proposed plan on the incident's page; "
                      "nothing runs until a person approves it"),
             "link": incident_link(network, incident_id, inc.device)}
    return (deliver or _deliver)(network, event)


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
    # R2 (C3726): the bottom line first, from the problem (`bottom_line`): what happened and
    # its impact, then the incident's own next action, then the rest.
    bl = bottom_line(network, entry, incident)
    todo = bl["next"]
    from modules.heal import said as SAID

    # C2817, C2823: what happened first, the cause the decision stated (facts, then a
    # hypothesis labelled); the outcome in plain words; each step by what it does, never its
    # key and number alone.
    cause = entry.get("cause") if outcome == "cant_fix" else None
    words = ((entry.get("outcome_words") if cause else "") or entry.get("words")
             or outcome.replace("_", " "))
    return {"incident": entry.get("incident") or "", "event": EVENT, "network": network,
            "device": device,
            "kind": kinds.KIND_WORDS.get(entry.get("kind"), entry.get("kind") or ""),
            "title": EP.withhold(bl["what"], lines),
            "lead": EP.withhold(f"{bl['what']}. {bl['impact']}." if bl["impact"]
                                else bl["what"], lines),
            **({"happened": EP.withhold(SAID.sentence(cause), lines)} if cause else {}),
            "outcome": EP.withhold(words, lines),
            "detected": EP.withhold(detected_words(first, device, named=not cause), lines),
            "detected_at": first.get("at") or (incident or {}).get("opened_at") or "",
            "steps": steps_said(network, device, entry, lines),
            "todo": todo, "link": incident_link(network, entry.get("incident") or "", device)}


#: The incident page's next action as a message says it (`bottom_line`), by the BLUF's fix kind
#: (`bluf.FIX_KINDS`): the action is pressed on the incident's page, which the message links.
NEXT_WORDS = {"start": "{label}, on the incident's page",
              "approve": "{label}, on the incident's page",
              "button": "{label}, on the incident's page",
              "hand_over": "hand it over to an engineer, on the incident's page"}


def _found_of(network: str, entry: dict, incident: dict) -> dict:
    """The incident as `incident_page.resolve` names it, from what the notifier holds: its
    record, its step log entry and its decisions (read here; unread, none)."""
    from modules.heal import decisions as HD

    iid = entry.get("incident") or ""
    try:
        made = [d for d in HD.decisions(network) if d.get("incident") == iid]
    except Exception as exc:                          # said; the title names the device alone
        log.warning("heal notice: %s's decisions for %s could not be read: %s", network, iid,
                    exc)
        made = []
    return {"found": "page", "id": iid, "incident": incident or {}, "entry": entry or {},
            "decisions": made, "unreadable": []}


def bottom_line(network: str, entry: dict, incident: dict) -> dict:
    """The problem's bottom line for a message (R2, C3726): ``{"what", "impact", "next"}``.
    *what* is THE incident's title (`bluf.what_of`, the one its page's heading, its BLUF and the
    Incidents list say), *impact* its condition's (`bluf.TABLE`), and *next* the incident's
    OWN next action: the one its page's BLUF offers (`fixit.section.view`'s ``bluf.fix``: for a
    lost stream Mercury's fix failed on, Start AI troubleshooting), else what the decision's
    kind or outcome says to do (`TODO`, `TODO_OUTCOME`), else `TODO_DEFAULT` for a problem that
    is the decision's own, else a hand-over. Never a guard's or a hold's advice for a problem it
    is not: a hold is a plain line among the steps (`steps_said`)."""
    from modules import bluf as B
    from modules import problem as P

    found = _found_of(network, entry, incident)
    b = B.bluf(B.model_of(found))
    fix = {}
    try:
        from modules import incident_page
        from modules.fixit import section
        view = section.view(network, found)
        fix = (view.get("bluf") or {}).get("fix") or {}
        # The page's ONE state governs (`incident_page.with_item`): a page that needs nobody
        # offers no next action, so neither does its message.
        if not incident_page.status(found["incident"], found["entry"], found["decisions"],
                                    view.get("state") or "")["needs"]:
            fix = {}
    except Exception as exc:                          # noqa: BLE001 (said; the table's next)
        log.warning("heal notice: %s's incident %s: its page's next action could not be read "
                    "(%s)", network, found["id"], type(exc).__name__)
    kind, label = fix.get("kind") or "", str(fix.get("label") or "")
    outcome = entry.get("outcome") or "cant_fix"
    advice = TODO_OUTCOME.get(outcome) or TODO.get(entry.get("kind") or "")
    own = (b.get("problem") or {}).get("condition") == P.CONDITION_OF.get(entry.get("kind")
                                                                          or "")
    if kind in ("start", "approve", "button") and label:
        nxt = NEXT_WORDS[kind].format(label=label)
    elif advice:
        nxt = advice
    elif own or not (b.get("problem") or {}).get("condition"):
        nxt = TODO_DEFAULT
    else:
        nxt = NEXT_WORDS["hand_over"]
    return {"what": b["what"], "impact": b.get("impact") or "", "next": nxt}


def hold_said(guard: dict, host: str) -> str:
    """A guard or hold that stopped a step, working as designed, as a message's one plain line
    (`bluf.hold_line`, without what it says of the fix below a message does not draw)."""
    from modules import bluf as B

    return B.hold_line(guard, host, tail=False)


def lead(network: str, entry: dict, incident: dict, outcome_words: str) -> str:
    """The one plain sentence a can't-fix's message leads with (the GUI review of 2026-11-13,
    item 9, EM1): what happened, as the incident's page titles it (`incident_page.title`: the
    newest decision's change, else the symptom its cause states, else its first trigger),
    then the outcome. Its caller withholds the incident's configuration lines from it."""
    from modules import incident_page
    from modules.heal import decisions as HD

    iid = entry.get("incident") or ""
    try:
        made = [d for d in HD.decisions(network) if d.get("incident") == iid]
    except Exception as exc:                          # said; the lead names the device alone
        log.warning("heal notice: %s's decisions for %s could not be read: %s", network, iid,
                    exc)
        made = []
    what = incident_page.title(incident, entry, made).rstrip(". ")
    return f"{what}. {outcome_words}" if outcome_words else what


def detected_words(trigger: dict, device: str, *, named: bool = True) -> str:
    """What was detected first, as the incident's page's timeline says it (a symptom by its
    words, `said.symptom_words`; a cause by its kind, `incidents.KIND_WORDS`: "a configuration
    change from outside Mercury"), never a log's mnemonic or a reader's key (EM4); with the
    person its line names when *named* (a message with no What happened line, which names
    them otherwise)."""
    from modules.heal import incidents, said

    kind = (trigger or {}).get("kind")
    if not kind:
        return (trigger or {}).get("words") or ""
    if kind in incidents.SYMPTOM_KINDS:
        return said.symptom_words(trigger, device)
    words = incidents.KIND_WORDS.get(kind) or trigger.get("words") or kind
    person = ((trigger.get("person") or {}).get("words") or "") if named else ""
    return f"{words} ({person})" if person else words


#: A named person's change waiting for them (the operator, 2026-11-16), told as a fix that waits
#: for a person: Mercury holds no address of a device's account, so the network's team named
#: for proposals is told, the message naming the person.
GRACE_EVENT, GRACE_TOLD_AS = "heal_grace", "proposal"


def grace_links(network: str, device: str) -> dict:
    """The two answers' existing controls on the device's page: Keep it (Edit intent, the
    intent editor) and Put it back now (its Deploy plan)."""
    from urllib.parse import quote, urlencode

    base = f"/v2/device/{quote(device, safe='')}?"
    return {"keep": base + urlencode({"list": network, "tab": "intent", "edit": 1}),
            "put_back": base + urlencode({"list": network, "op": "deploy"})}


def grace_notice(network: str, inc: dict, grace: dict, *, deliver=None) -> dict:
    """Tell *grace*'s person once, through the network's team (`GRACE_TOLD_AS`): "You changed
    <device> (<n> lines differ from intent). Keep it: adopt into intent / Put it back now"."""
    from modules import heal_notify
    from modules.heal.attribution import person_said
    from modules.notify import delivery

    device = inc.get("device") or ""
    links = grace_links(network, device)
    # C3863: the person as a person ("lab (vty0, from <address>)"), never the attribution's
    # sentence.
    who = person_said(grace) or "a person"
    lines = grace.get("lines")
    event = {"incident": str(inc.get("id") or "")[:80], "event": GRACE_EVENT,
             "network": network, "device": device,
             "title": (f"You changed {device} ({lines if lines is not None else 'some'} lines "
                       "differ from intent)")[:120],
             "happened": f"{who} changed {device}",
             "outcome": f"Put back automatically at {grace.get('until')} unless kept",
             "todo": (f"Keep it: adopt into intent ({links['keep']}) / Put it back now "
                      f"({links['put_back']})"),
             "link": incident_link(network, str(inc.get("id") or ""), device)}
    teams = heal_notify.teams_for(network, GRACE_TOLD_AS)
    if not teams:
        return {"sent": 0, "nobody": True}
    return (deliver or delivery.deliver_event)(event, teams)


def incident_link(network: str, incident_id: str, device: str) -> str:
    """The incident's page, as a message links it: `incidents.incident_href`, the ONE place an
    incident's address is built (the operator, 2026-11-12, objective 2: "links to the
    incident")."""
    from modules.heal import incidents

    return incidents.incident_href(network, incident_id, device=device)


#: A decision's step results that are a guard or hold stopping it, working as designed
#: (`decide`'s stops; `run_card.DECISION_HELD`, which the stepper draws held), said as the
#: hold's plain line in a message (`steps_said`).
HOLD_RESULTS = ("held", "halted", "off")


def _guard_of(network: str, entry: dict, step: dict) -> dict:
    """The guard record that stopped *step*: its decision's (`decisions.find`, with its
    operands), else the entry's own."""
    from modules.heal import decisions as HD

    did = step.get("decision") or ""
    if did:
        try:
            got = (HD.find(network, did) or {}).get("guard")
        except Exception as exc:                      # said; the entry's guard then
            log.warning("heal notice: %s's decision %s could not be read: %s", network, did,
                        exc)
            got = None
        if isinstance(got, dict) and got.get("guard"):
            return got
    g = entry.get("guard")
    return g if isinstance(g, dict) else {}


def steps_said(network: str, host: str, entry: dict, lines) -> list:
    """The steps taken, as a message lists them (the operator, 2026-11-12, objective 2: "the
    can't-fix email lists the steps taken in plain words, with local times and display
    names"): every step the incident's record holds, in its order, each as THE stepper says it
    (`run_card.decision_phase` and `act_phase`'s ``trail``: its operation's two-to-four-word
    label, "Read edge-b", and its state in words, "done", "failed"), then its recorded words,
    the incident's configuration lines withheld, and the time it was recorded (ISO UTC, said
    locally by the message). A finished record never says a step is running
    (`steplog.finished_steps`, C3173). A step recorded with no time of its own takes its row's
    (a decision's steps are timed by its row, as its card draws them). ``what`` keeps the
    step's key, for the webhook's JSON. More steps than a message carries (`message.FIELDS`)
    end in one line saying how many more, and where they are."""
    from modules import evidence_pack as EP
    from modules.heal import run_card, steplog
    from modules.notify import message

    steps = [s for s in steplog.finished_steps(entry) if isinstance(s, dict)]
    decided = [s for s in steps if s.get("row") in ("decision", None)]
    acted = [s for s in steps if s.get("row") not in ("decision", None)]
    trails = {"d": iter(run_card.decision_phase(decided, host=host)["trail"] if decided else []),
              "a": iter(run_card.act_phase(acted, ended=True, host=host)["trail"]
                        if acted else [])}
    stamps = {}
    got = steplog.read(network)
    for r in got.get("rows") or []:
        if r.get("incident") == entry.get("incident") and r.get("at"):
            stamps[(r.get("decision") or "", r.get("row") or "")] = r["at"]
    out = []
    for s in steps:
        t = next(trails["d" if s.get("row") in ("decision", None) else "a"], {})
        words, result = s.get("words") or "", t.get("state_words") or s.get("result") or ""
        if s.get("result") == "ended":
            # A step a later record of itself ends (`finished_steps`): its words name that
            # record by its number, which a message's list does not draw.
            words = re.sub(r"(?:; )?its outcome is step \d+'s$", "", words)
            result = "ended: its outcome is its later line"
        if s.get("result") in HOLD_RESULTS:
            # A guard or hold working as designed is one plain line, never "failed" (R2,
            # C3726): the hold's own words, from the guard record that stopped it, said once
            # (the step's recorded words name the same guard).
            said = hold_said(_guard_of(network, entry, s), host).rstrip(".")
            words, result = ("", said) if said else (words, "held, as designed")
        label = t.get("words") or s.get("step") or ""
        out.append({"what": EP.withhold(f"{s.get('step')}: {words}", lines),
                    "said": EP.withhold(label + (f": {words}" if words else ""), lines),
                    "label": label, "words": EP.withhold(words, lines),
                    "result": result,
                    "at": s.get("at") or s.get("ended_at") or stamps.get(
                        (s.get("decision") or "", s.get("row") or ""), "")})
    room = message.FIELDS["steps"]
    if len(out) > room:
        more = len(out) - room + 1
        out = out[:room - 1] + [{"what": f"more: {more}", "said": f"{more} more steps",
                                 "result": "on the incident's page in Mercury"}]
    return out


def analysis_block(result: dict, lines) -> dict:
    """The analysis's block for a message (`heal_analysis.block`), its text with the incident's
    configuration lines withheld: a message never carries a configuration line."""
    from modules import evidence_pack as EP
    from modules.ai import heal_analysis as HA

    b = HA.block(result)
    out = {k: EP.withhold(b.get(k) or "", lines) for k in ("state", "words", "label", "score",
                                                           "rationale")}
    if out["score"]:
        # Its measured reliability as the incident's page words it (the AI troubleshooting
        # section's "beta": "The AI's answers are not measured on recorded cases yet"), never
        # the prompt's name, its version or the model pinned (the GUI review's EM4).
        label = (result or {}).get("label") or HA.beta()
        out["score"] = (f"measured: {out['score']}" if label.get("state") == "measured"
                        else NOT_MEASURED_WORDS)
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
            (f"nothing to heal: every symptom the incident named has cleared by itself at "
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
