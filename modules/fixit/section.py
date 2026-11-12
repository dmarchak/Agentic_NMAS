"""The incident page's "AI troubleshooting" section, drawn with no AI call (board recurring-fixes
v2, every state but the AI's own; the incident page board, B5's frame; the fix-it plan's S4).

The operator's order (overnight item 6, 2026-11-12), which this module implements in part:
"AI troubleshooting, as designed: a background job; the AI proposes one catalog operation with
parameters; code validates it against intent and the guards; a person approves it; on failure
STOP with Retry with more information (cost shown first), Cancel or Hand over; a per-incident
cap of $1.00; a repeated failed proposal is flagged; payloads use stable labels. Settings ›
Background processes, AI mode Manual by default. Section 12's rule stays in force."

**What the section draws** (`view`, a read): the totals (this incident's AI spend against its
cap, today's against the day cap), the incident's attempts in order (each catalogue operation's
run, `incident.attempts`, with who proposed and approved it, its outcome in the operation's
own words, its AI cost and its run's card), and the state the incident's newest record puts it
in (`STATES`): nothing tried, a run going, a run that passed, the STOP after a run that did not
pass, a proposal (flagged when it repeats a failed attempt, a variation said as one), the
cancelled line, the hand-over line, or, once the incident is resolved, the record alone with
no control. Each state's controls are the board's: Retry with more information, Cancel and
Hand over after a STOP; the per-incident cap's refusal in place of Retry (G1); nothing that
acts once resolved.

**Retry with more information re-plans through Mercury's own proposer, with no AI** (`retry`):
the person's press, the cap asked again at the press (spent plus a retry's worst case against
the cap, refused with both operands when it would pass it, the proposer not asked), Mercury's
diagnosis's next step as one catalogue operation (`proposers.mercury`), checked by code
(`validate.check`), and ONE proposal line in the incident's record: the operation and its
parameters, or why there is none, with the person's note. Mercury's diagnosis does not read
the note: it is kept for the hand-over and for the AI, once built. A retry's worst case is the
AI troubleshoot's (`worst_usd`: two calls at the per-call cap of `WORST_PIN`, the pin AI
troubleshooting uses until its own is pinned), so the cap holds the press as it will once the
AI is asked behind it; today the press costs nothing.

**Nothing here starts anything** (the operator, 2026-11-11: "FAIL: STOP. Never retry on its
own"): `view` reads; `retry` records one line and asks no model, holds no device, starts no
job and sends nothing; the proposal's Approve is the operation's own card and confirm, a
person's press (tests/test_fixit_never_retries.py: every caller of a proposer is the retry
route, a POST a verified person makes; the section's template loads and repeats nothing).

**People** are drawn by display name (the template's ``people`` filter); a hand-over's
recipients by team name. No email address is drawn.
"""

import calendar
import logging
import os
import time

log = logging.getLogger(__name__)

#: Retry with more information's steps, as its manual page names them.
STEPS = ("person", "cap", "propose", "check", "record")
#: Cancel's: a verified person, one line.
CANCEL_STEPS = ("person", "record")
#: The section's states, each drawn by templates/v2/_fixit_section.html.
STATES = ("none", "ready", "running", "passed", "stopped", "proposed", "cancelled",
          "handed_over", "resolved")
#: The states in which Retry with more information is offered (the cap permitting).
RETRY_IN = ("passed", "stopped", "proposed", "cancelled", "handed_over")
#: The pin a retry's worst case is drawn from until AI troubleshooting pins its own (S5): the
#: heal analysis's, the board's figure (two calls at $0.125, "at most $0.25").
WORST_PIN = "heal_analysis"
#: The calls one AI attempt makes: the read loop's two passes (`read_loop.CALLS_PER_FINDING`).
CALLS_PER_ATTEMPT = 2
#: Who a proposal came from, as an attempt's line says it.
SOURCE_WORDS = {"mercury": "Mercury's diagnosis", "ai": "the AI", "person": "a person"}
#: How many attempts the section lists before it counts the rest (each one line).
SHOWN = 12


class Refused(ValueError):
    """Nothing was recorded; the words say why. ``status`` is the HTTP status it answers."""

    def __init__(self, words: str, status: int = 409):
        super().__init__(words)
        self.status = status


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _epoch(iso):
    try:
        return float(calendar.timegm(time.strptime(str(iso or "")[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, OverflowError):
        return None


# ── The incident, as its own store reads it ─────────────────────────────────────────────────

def _identity(network: str, device: str) -> str:
    """*device*'s stable identity in *network*: the committed manifest's key for its name, else
    its inventory row's (`manifest.identity_for`), else ``""``. Reads only."""
    from modules.config import list_data_path
    from modules.nsot import manifest

    ident, _entry = manifest.find_by_name(os.path.join(list_data_path(network), "config_repo"),
                                          device)
    if ident:
        return ident
    row = manifest.inventory_index(network).get(device.lower()) or {}
    return manifest.identity_for(row.get("netbox_id"), row.get("device_uid", ""))


def incident_of(network: str, found: dict) -> dict:
    """``{"incident", "why"}``: the incident `incident_page.resolve` found, as the fix-it
    record takes it (`incident.Incident`: its network, id, device by identity with its name,
    detected time and the subscriptions its lost-stream triggers name), or None with why not."""
    from modules.fixit import incident as F
    from modules.heal import diagnose_stream

    inc, entry = found.get("incident") or {}, found.get("entry") or {}
    iid = found.get("id") or ""
    device = inc.get("device") or entry.get("device") or ""
    if not device:
        return {"incident": None, "why": f"{iid} names no device, so no operation of Mercury's "
                                          "catalogue acts in it"}
    ident = _identity(network, device)
    if not ident:
        return {"incident": None, "why": (
            f"{device}'s identity is not known: neither {network}'s manifest nor its inventory "
            "holds it, so this incident's troubleshooting record cannot be kept")}
    trig = [t for t in inc.get("triggers") or [] if isinstance(t, dict)]
    try:
        detected = float((trig[0] if trig else {}).get("epoch") or 0)
    except (TypeError, ValueError):
        detected = 0.0
    detected = detected or _epoch(inc.get("opened_at")) or _epoch(entry.get("first_at")) or 0
    if not detected:
        return {"incident": None, "why": (
            f"when {iid} was detected is not kept, so which runs are its attempts cannot be "
            "told")}
    subs = []
    for t in trig:
        sub = diagnose_stream.stream_of(t).get("subscription")
        if sub and sub not in subs:
            subs.append(sub)
    return {"incident": F.Incident(network, iid, ident, device, float(detected), tuple(subs)),
            "why": ""}


# ── The figures ─────────────────────────────────────────────────────────────────────────────

def worst_usd() -> float:
    """A retry's worst case in US dollars: `CALLS_PER_ATTEMPT` calls at `WORST_PIN`'s per-call
    cap (`profiles.cap_per_call`, from its pinned model's prices at its bounds)."""
    from modules.ai import profiles

    return round(profiles.cap_per_call(WORST_PIN) * CALLS_PER_ATTEMPT, 6)


def today() -> dict:
    """``{"spent", "cap", "error"}``: today's AI spend (`calls.spent_usd` of the cap's day) and
    the installation's day cap (`gateway.day_cap`; None is no cap), as the toolbar chip reads
    them. *spent* None when the record of calls cannot be read, said in *error*."""
    from modules.ai import calls, gateway

    got = calls.spent_usd(calls.today())
    return {"spent": got["usd"], "cap": gateway.day_cap(),
            "error": got["error"] if got["state"] == "unreadable" else ""}


# ── The section, drawn ──────────────────────────────────────────────────────────────────────

def _run_checks(network: str, run_id: str) -> list:
    """What a run's own record says it found, per subscription: ``[{"sub", "outcome", "checks":
    [{"name", "state", "words"}], "stale"}]`` (its verify reads, kept in the record). A read of
    one record; a record that cannot be read gives nothing (its card says why)."""
    from modules.heal import resubscribe as R
    from modules.nsot import privileged

    try:
        rec = privileged.get(network, run_id) or {}
    except (OSError, ValueError, RuntimeError):
        return []
    out = []
    for s in rec.get("subscriptions") or []:
        if not isinstance(s, dict):
            continue
        outcome = s.get("outcome") or ""
        out.append({"sub": str(s.get("sub") or ""),
                    "outcome": R.OUTCOME_WORDS.get(outcome, outcome),
                    "checks": [{"name": k, "state": (v or {}).get("state") or "",
                                "words": (v or {}).get("words") or ""}
                               for k, v in (s.get("verify") or {}).items()],
                    "stale": [str(f) for f in s.get("stale") or []]})
    return out


def _attempt(a: dict, proposals: dict, usd: dict) -> dict:
    """One attempt as its line draws it."""
    from modules.fixit.handover import params_words
    from modules.fixit.policy import money

    p = proposals.get(a["proposal"]) or {}
    spent = sum((usd.get(c, 0.0) for c in p.get("calls") or []), 0.0)
    state = ("running" if a["state"] == "running" else "passed" if a["passed"] else "failed")
    return {"n": a["n"], "run": a["run"], "device": a["device"], "state": state,
            "started": a["at"],
            "finished": _iso(a["finished_at"]) if a["finished_at"] is not None else "",
            "operation": short_words(a["operation"], a["device"], a["params"]),
            "params": params_words(a["params"]),
            "source": SOURCE_WORDS.get(a["source"], ""), "actor": a["actor"],
            "words": outcome_words(a["outcome"], a["words"]),
            "detail": a["words"], "ai_usd": money(spent)}


def short_words(operation: str, device: str, params: dict) -> str:
    """A catalogue operation with its parameters, as the board's attempt line says it ("Re-subscribe
    edge1's telemetry (101, 102)", "… with the collector step", "Re-add edge1's receiver for
    101"); an operation the catalogue does not hold, by its key."""
    from modules.heal import resubscribe as R

    params = params or {}
    if operation == R.KEY:
        subs = ", ".join(map(str, params.get("subs") or [])) or "no subscription"
        return (f"Re-subscribe {device}'s telemetry ({subs})"
                + (" with the collector step" if params.get("collector_step") else ""))
    if operation == R.READD_KEY:
        return f"Re-add {device}'s receiver for {params.get('sub') or 'no subscription'}"
    return operation


def outcome_words(outcome: str, words: str = "") -> str:
    """An outcome in the operation's own short words (`resubscribe.OUTCOME_WORDS`: "re-subscribed;
    the stream did not come back"), else the run's own: one line on a projector, the run's whole
    words one level down (its line's hover and its card)."""
    from modules.heal import resubscribe as R

    return R.OUTCOME_WORDS.get(outcome) or words or outcome or ""


def _flag(incident, line: dict, resolved, now) -> dict:
    """The repeat flag of a proposal line (`incident.repeat_of`), drawn: ``{"kind", "attempt",
    "words", "at", "changed", "params_hash"}``, or ``{}`` for a line that names no operation or
    no parameters (one written before they were kept)."""
    from modules.fixit import incident as F

    if not line.get("operation") or not isinstance(line.get("params"), dict):
        return {}
    got = F.repeat_of(incident, line["operation"], line["params"], resolved, now=now)
    return {"kind": got["kind"], "attempt": got["attempt"],
            "words": outcome_words(got["outcome"], got["words"]),
            "at": got["at"], "params_hash": got["params_hash"],
            "changed": [{"name": c["name"], "before": _said(c["before"]),
                         "after": _said(c["after"])} for c in got["changed"]],
            "complete": got["complete"], "error": got["error"]}


def _said(value) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return ", ".join(map(str, value)) or "none"
    return str(value or "none")


def _proposal(incident, line: dict, resolved, now) -> dict:
    """The newest proposal, as the proposed state draws it, with what its card opens with."""
    from modules.fixit.handover import params_words
    from modules.heal import resubscribe as R

    params = line.get("params") if isinstance(line.get("params"), dict) else {}
    subs = (list(params.get("subs") or []) if line.get("operation") == R.KEY
            else [params["sub"]] if params.get("sub") else [])
    return {"id": line["proposal"], "source": SOURCE_WORDS.get(line.get("source"), ""),
            "operation": line.get("operation") or "",
            "words": (short_words(line["operation"], incident.device, params)
                      if line.get("operation") else ""),
            "params": params_words(params) if params else "", "subs": subs,
            "none": line.get("words") or "", "note": line.get("note") or "",
            "by": line.get("by") or "", "at": line.get("at") or "",
            "flag": _flag(incident, line, resolved, now)}


def _what_is_sent(tried: list, lines: list) -> list:
    """What the AI would be sent of this incident once it is asked (the board's "Sent with
    it"): each attempt as ``tried:<n>``, then each earlier proposal, marked with its outcome."""
    out = [f"tried:{a['n']}: {a['operation']} ({a['params']}): "
           + ("PASSED" if a["state"] == "passed" else "RUNNING" if a["state"] == "running"
              else f"FAILED, {a['words']}") for a in tried]
    from modules.fixit.handover import params_words
    for ln in lines:
        if "proposal" not in ln:
            continue
        what = (f"{ln['operation']} ({params_words(ln.get('params') or {})})"
                if ln.get("operation") else "no operation")
        out.append(f"proposal {ln['proposal']} by {SOURCE_WORDS.get(ln.get('source'), '?')}: "
                   f"{what}")
    return out


def view(network: str, found: dict, *, resolved: float = None, ended: str = "",
         now: float = None) -> dict:
    """What the section draws for the incident `incident_page.resolve` *found* in *network*;
    *resolved* is when it resolved (epoch seconds), None while it stands, and *ended* how (the
    page's state: ``fixed``, ``cleared`` or ``cancelled``). A read: the incident's record, the
    operations' run records, the record of AI calls and the settings. ``{"state", "why", "id",
    "network", "device", "totals", "attempts", "more", "incomplete", "stop", "proposal",
    "cancelled", "handover", "handovers", "retry", "teams", "mode", "advisories", "ended"}``;
    *advisories* the AI analysis kept for the incident today, drawn as advice."""
    from modules.fixit import handover as H
    from modules.fixit import incident as F
    from modules.fixit import policy as P

    got = incident_of(network, found)
    inc = got["incident"]
    out = {"state": "none", "why": got["why"], "id": found.get("id") or "", "network": network,
           "device": inc.device if inc else "", "totals": {}, "attempts": [], "more": 0,
           "incomplete": "", "stop": {}, "proposal": {}, "cancelled": {}, "handover": {},
           "handovers": [], "retry": {}, "teams": {}, "mode": {}, "unreadable": "",
           "ended": ended if resolved is not None else "",
           "advisories": [{"at": a.get("at") or "", "words": a.get("words") or ""}
                          for a in (found.get("advisories") or [])[-1:]]}
    if inc is None:
        return out
    now = time.time() if now is None else float(now)
    rec = F.read(inc)
    tried = F.attempts(inc, resolved, now=now)
    calls = F.calls_of(inc)
    cost = F.cost_so_far(inc)
    cap = P.cap_usd()
    day = today()
    usd = {c["id"]: c["usd"] for c in calls["calls"]}
    proposals = {ln["proposal"]: ln for ln in rec["lines"] if "proposal" in ln}
    drawn = [_attempt(a, proposals, usd) for a in tried["attempts"]]
    out.update(
        attempts=drawn[-SHOWN:], more=max(0, len(drawn) - SHOWN),
        incomplete=tried["error"] if tried["state"] != "ok" else "",
        unreadable=rec["error"] if rec["state"] == "unreadable" else "",
        mode={"state": P.mode()["state"], "refused": P.ai_refusal()},
        totals={"spent": P.money(cost["usd"]) if cost["usd"] is not None else "",
                "spent_error": cost["error"],
                "cap": P.money(cap["usd"]) if cap["state"] == "ok" else "",
                "cap_error": cap["error"],
                "today": P.money(day["spent"]) if day["spent"] is not None else "",
                "today_error": day["error"],
                "day_cap": P.money(day["cap"]) if day["cap"] is not None else ""},
        handovers=H.versions(inc)["versions"])
    events = [(a["started_at"], 0, "attempt", a) for a in tried["attempts"]]
    events += [(float(ln["epoch"]), 1, "proposal" if "proposal" in ln else ln["choice"], ln)
               for ln in rec["lines"]]
    newest = max(events, key=lambda e: (e[0], e[1])) if events else None
    if resolved is not None:
        out["state"] = "resolved"
        return out
    if newest is None:
        state = "ready"
    elif newest[2] == "attempt":
        a = newest[3]
        state = ("running" if a["state"] == "running" else "passed" if a["passed"]
                 else "stopped")
        out["stop"] = dict(drawn[a["n"] - 1], found=_run_checks(network, a["run"]))
    elif newest[2] == "proposal":
        state = "proposed"
        out["proposal"] = _proposal(inc, newest[3], resolved, now)
    elif newest[2] == "cancel":
        state = "cancelled"
        line = newest[3]
        out["cancelled"] = {"at": line.get("at") or "", "by": line.get("by") or "",
                            "attempts": line.get("attempts")}
    elif newest[2] == "handover":
        state = "handed_over"
        line = newest[3]
        out["handover"] = {"at": line.get("at") or "", "by": line.get("by") or "",
                           "teams": list(line.get("teams") or []),
                           "version": line.get("version")}
    else:
        state = "ready"
    out["state"] = state
    worst = worst_usd()
    cs = P.cap_state(inc, worst)
    out["retry"] = {
        "offered": state in RETRY_IN and cs["state"] == "allowed",
        "in_state": state in RETRY_IN,
        "refused": cs["words"] if cs["state"] != "allowed" else "",
        "worst": P.money(worst),
        "after": P.money(cs["total"]) if cs["total"] is not None else "",
        "drawn_spent": "" if cs["spent"] is None else f"{cs['spent']:.6f}",
        "drawn_cap": "" if cs["cap"] is None else f"{cs['cap']:.6f}",
        "sent": _what_is_sent(drawn, rec["lines"])}
    out["teams"] = H.offered(network)
    return out


def drawn(network: str, found: dict, *, resolved: float = None, ended: str = "",
          now: float = None) -> dict:
    """`view` as a page draws it: every text masked again on the way out (`steplog.masked`) and
    every person named by display name (`display_names.people_payload`)."""
    from modules import display_names
    from modules.heal import steplog

    return display_names.people_payload(steplog.masked(view(
        network, found, resolved=resolved, ended=ended, now=now)))


# ── Retry with more information ─────────────────────────────────────────────────────────────

def diagnosis_of(incident) -> dict:
    """The newest diagnosis Mercury ran for *incident* (`steplog.diagnoses` attached to it),
    else the newest of its device since it was detected; ``{}`` when there is none."""
    from modules.heal import steplog

    got = steplog.diagnoses(incident.network, incident=incident.id)
    if got["diagnoses"]:
        return got["diagnoses"][0]
    for d in steplog.diagnoses(incident.network, device=incident.device)["diagnoses"]:
        at = _epoch(d.get("finished_at") or d.get("at"))
        if at is not None and at >= incident.detected:
            return d
    return {}


def _moved_words(drawn_spent, drawn_cap, got: dict) -> str:
    """What moved between the panel and the press, both operands named, or ``""``."""
    from modules.fixit.policy import money

    def num(text):
        try:
            return float(text)
        except (TypeError, ValueError):
            return None
    was_spent, was_cap = num(drawn_spent), num(drawn_cap)
    moved = []
    if was_spent is not None and got["spent"] is not None and \
            round(was_spent, 6) != round(got["spent"], 6):
        moved.append(f"this incident's AI spend was {money(was_spent)} when the panel was "
                     f"drawn and is {money(got['spent'])} now")
    if was_cap is not None and got["cap"] is not None and round(was_cap, 6) != round(got["cap"], 6):
        moved.append(f"the per-incident cap was {money(was_cap)} when the panel was drawn and "
                     f"is {money(got['cap'])} now")
    return "; ".join(moved)


def retry(network: str, found: dict, *, actor: str, actor_verified: str, person: bool,
          note: str = "", drawn_spent: str = "", drawn_cap: str = "", now: float = None,
          sources=None, planned=None) -> dict:
    """Retry with more information, pressed by *actor*, a person verified as *actor_verified*
    (`STEPS`): the cap asked again at the press, Mercury's own proposer asked for the fix its
    diagnosis names, the proposal checked, and ONE proposal line recorded with the person's
    *note*. ``{"line", "checked", "proposed"}``, or raises `Refused` with nothing recorded and
    the proposer not asked. *drawn_spent* and *drawn_cap* are the figures the panel was drawn
    with, so a refusal can say what moved since. *sources* and *planned* are the check's seams
    (tests). Asks no model, holds no device, starts no job and sends nothing."""
    from modules.fixit import incident as F
    from modules.fixit import policy as P
    from modules.fixit import proposers
    from modules.fixit import validate as V

    got = incident_of(network, found)
    inc = got["incident"]
    if inc is None:                                                                # person
        raise Refused(f"Not re-planned: {got['why']}", 404)
    if not person or not actor or actor_verified in ("", "none", None):
        raise Refused("Not re-planned: Retry with more information is a verified person's "
                      f"press, and this request is not one (its actor is {actor or 'none'}, "
                      f"verified by {actor_verified or 'nothing'})", 403)
    cs = P.cap_state(inc, worst_usd())                                             # cap
    if cs["state"] != "allowed":
        moved = _moved_words(drawn_spent, drawn_cap, cs)
        log.info("fixit: %s: a retry refused at the press by the cap: %s", inc.id, cs["words"])
        raise Refused(cs["words"] + (f". Since the panel was drawn, {moved}" if moved else ""),
                      409)
    proposed = proposers.mercury(inc, diagnosis_of(inc))                           # propose
    checked = None
    if proposed["state"] == "proposed":
        checked = V.check(inc, proposed["operation"], proposed["params"], now=now,  # check
                          sources=sources, planned=planned)
    if checked and checked["ok"]:
        line = F.record_proposal(inc, "mercury", checked["operation"],             # record
                                 V.as_attempt(checked["operation"], checked["params"]),
                                 by=actor, verified=actor_verified, note=note, now=now)
    else:
        why = (proposed["words"] if checked is None else
               f"Mercury's diagnosis named {proposed['operation']}, and the check refused it: "
               f"{checked['refused']}")
        line = F.record_proposal(inc, "mercury", by=actor, verified=actor_verified,
                                 note=note, words=why, now=now)
    log.info("fixit: %s: Retry with more information by %s: %s", inc.id, actor,
             line.get("operation") or "no operation")
    return {"line": line, "checked": checked, "proposed": proposed}


# ── The operation's card, opened from the section ───────────────────────────────────────────

def _card(network: str, incident_id: str, proposal: str, device: str, subs, readd: bool):
    """``(incident, link)`` for `card_link`; *incident* None when *link* is a refusal."""
    from modules import incident_page
    from modules.fixit import incident as F
    from modules.heal import resubscribe as R

    found = incident_page.resolve(network, incident_id)
    if found["found"] != "page":
        return None, {"refused": f"{incident_id} is no incident of {network} that has a page"}
    got = incident_of(network, found)
    inc = got["incident"]
    if inc is None:
        return None, {"refused": got["why"]}
    if inc.device != device:
        return None, {"refused": (f"{incident_id} is {inc.device}'s incident, and this card is "
                                  f"{device}'s: a fix is attached to its own device's incident")}
    rec = F.read(inc)
    if rec["state"] == "unreadable":
        return None, {"refused": rec["error"]}
    if proposal and proposal not in [ln.get("proposal") for ln in rec["lines"]]:
        return None, {"refused": f"{incident_id}'s record holds no proposal {proposal!r}"}
    subs = [str(s) for s in subs or ()]
    if not subs:
        flag = {"kind": "new"}
    elif readd:
        flag = F.repeat_of(inc, R.READD_KEY, {"sub": subs[0]})
    else:
        flag = F.repeat_of(inc, R.KEY, {"subs": subs})
    flag = dict(flag, changed=[{"name": c["name"], "before": _said(c["before"]),
                                "after": _said(c["after"])} for c in flag.get("changed") or []])
    if flag.get("kind") != "new":
        flag["words"] = outcome_words(flag.get("outcome") or "", flag.get("words") or "")
    return inc, {"incident": incident_id, "proposal": proposal or "", "repeat": flag}


def card_link(network: str, incident_id: str, proposal: str, device: str, subs,
              readd: bool = False) -> dict:
    """What the operation's card carries when it is opened from the section's proposal, read
    for its form: ``{"incident", "proposal", "repeat"}`` (*repeat* `incident.repeat_of` for the
    subscriptions ticked, or the one a re-add names), or ``{"incident", "proposal",
    "refused": why}``, which the confirm refuses again. A read."""
    got = _card(network, incident_id, proposal, device, subs, readd)[1]
    return dict({"incident": incident_id, "proposal": proposal or ""}, **got)


#: A repeat's "what is different now" is one line of at least this many words.
DIFFERENT_WORDS = 3


def confirm_link(network: str, incident_id: str, proposal: str, device: str, subs,
                 different: str = "", readd: bool = False) -> dict:
    """What the operation's confirm writes into its run record (`incident.RUN_FIELD`) when it
    was opened from the section: the incident, the attempt's number and the proposal
    (`incident.run_link`), and, for a proposal that repeats a failed attempt, the person's
    "what is different now" (`different`), required. Raises `Refused` naming what it compared,
    with nothing sent. A read."""
    from modules.fixit import incident as F

    inc, got = _card(network, incident_id, proposal, device, subs, readd)
    if inc is None:
        raise Refused(f"Not run: {got['refused']}. Nothing was sent")
    try:
        link = F.run_link(inc, proposal)
    except F.Refused as exc:
        raise Refused(f"Not run: {exc}. Nothing was sent") from None
    rep = got["repeat"]
    text = " ".join(str(different or "").split())
    if rep.get("kind") == "repeat":
        if len(text.split()) < DIFFERENT_WORDS:
            raise Refused(
                f"Not run: this repeats attempt {rep['attempt']}, which failed ({rep['words']}), "
                f"with the same parameters (parameter hash {rep['params_hash']} both times); "
                f"say what is different now, at least {DIFFERENT_WORDS} words "
                f"({len(text.split())} given). Nothing was sent")
        link["different"] = text[:F.WORDS_CHARS]
        link["repeats"] = rep["attempt"]
    return link
