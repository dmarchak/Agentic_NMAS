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

**THE CONTRACT** (the operator's R1 and R2, 2026-11-14; the incident page's frontend draws
these keys of `view`, and this module keeps to them):

- ``bluf``: ``{"what", "impact", "fix": {"kind": "approve"|"button"|"hand_over"|"start"|"none",
  "label", "href"?, "read"?}, "severity"}``, the three lines from Mercury's own table
  (`modules/bluf.py`, never the AI's words); *severity* ``critical`` only for a network outage;
  with no plan to approve the fix is never blank: the read the AI's answer said it lacked
  (``read``, `lacked_read`), a ``button`` linking Show commands with it filled in, else Ask the
  AI again when offered, else Hand over;
- ``status``: one plain line ("The AI is investigating, started at <ISO instant>"; the screen
  draws the instant in the viewer's zone);
- ``card``: the incident card's default view (board R5, approved 2026-11-15; `card_of`):
  ``{"status", "kind", "step", "how", "fixed_at", "plan_ready"}``;
- ``proposal``: ``{"id", "hash", "refused_hash", "approvable", "steps": [{"n", "operation",
  "words", "params", "hash", "preflight": {"ok", "refused"}, "repeat"}], "found",
  "why_refused", "source", "by", "at",
  "calls", "note", "shown", "prompt"}`` or None, *shown* the AI's checked answer as kept
  (``rationale``, ``hypotheses`` each ``{"claim", "cites"}``, the fix's ``why`` and ``cites``,
  ``reads``, ``fit``);
- ``ai_answer``: the AI's newest answer, with or without a plan: ``{"id", "words", "shown",
  "gap", "has_plan", "calls", "prompt", "at", "note"}`` or None, so the page draws its diagnosis
  and the missing capability (``gap``) of an answer that proposed no operation (`fixit.plan.preflight`): every step preflighted before it is
  drawn, a refused one drawn refused with why and the plan then not approvable; *hash* the
  plan's, the one Approve sends (``hash``, with ``proposal`` its id);
- ``actions``: ``{"approve", "modify", "deny", "ask_again", "start", "hand_over"}``, each
  ``{"offered", "href", "refused"}`` (POSTs of routes/fixit_v2.py: approve takes ``proposal``,
  ``hash`` and an optional ``reason``; modify ``proposal`` and ``text``; deny ``proposal`` and
  an optional ``reason``; ask_again and start an optional ``text``; hand_over is the existing
  Hand over form);
- ``attempts`` (as before), ``other_actions`` (each operation that already failed here:
  ``{"operation", "attempt", "words", "run"}``, drawn only collapsed, never as the next
  action), ``holds`` (each guard or hold working as designed, one plain line), ``cap``
  (``{"state": "ok"|"reached"|"unreadable", "which": "incident"|"day"|"month"|"", "words"}``);
- ``auto``: the network's switch for automatic troubleshooting (`auto_model`: ``{"feature",
  "words", "trigger_words", "on", "by", "at", "ends", "estimate": {"label", "calls_per_day",
  "usd_per_day", "usd_per_month", "frequency_basis", "cost_basis", "suggested", "digest",
  "error"}, "incident_cap", "day_cap", "settings_href"}``); turned on and off only in Settings ›
  AI (`background.turn_on`, `turn_off`), off by default on every network;
- the section's ``state`` (`STATES`) adds ``investigating`` (an investigation started and
  nothing come of it yet), ``denied`` and ``capped``.

Cancel and Retry with more information are removed (the operator: Deny and Modify replace
them); a cancel line written before stays readable.

**The AI is offered beside it** (`ai_offer`, S5): Troubleshoot with AI with nothing tried, and
Retry's Ask the AI to re-plan, in Manual mode while the cap allows, the estimate and the worst
case drawn before the press (`fixit_troubleshoot.estimate`, no call made). The press is
`routes/fixit_v2.py`'s ``troubleshoot``, whose investigation is `modules/ai/fixit_troubleshoot`
's; nothing here calls it.

**Nothing here starts anything** (the operator, 2026-11-11: "FAIL: STOP. Never retry on its
own"): `view` reads; `retry` records one line and asks no model, holds no device, starts no
job and sends nothing; the proposal's Approve is the operation's own card and confirm, a
person's press (tests/test_fixit_never_retries.py: every caller of a proposer is the retry
route or the troubleshoot route, each a POST a verified person makes; the section's template
loads and repeats nothing).

**People** are drawn by display name (the template's ``people`` filter); a hand-over's
recipients by team name. No email address is drawn.
"""

import calendar
import logging
import os
import re
import time

log = logging.getLogger(__name__)

#: The card's steps, from a plan to its run, as its manual page names them
#: (docs/manual/how-it-works/fixit-troubleshoot.md, "The steps"): each plan's preflight, then
#: each press (`actions`), a verified person's.
STEPS = ("preflight", "approve", "modify", "deny", "ask_again", "start")
#: The section's states, each drawn by templates/v2/_fixit_section.html.
STATES = ("none", "ready", "running", "passed", "stopped", "proposed", "cancelled",
          "handed_over", "resolved", "investigating", "denied", "capped")
#: The states in which Retry with more information is offered (the cap permitting).
RETRY_IN = ("passed", "stopped", "proposed", "cancelled", "handed_over")
#: A retry's figure is the least one AI call costs (`fixit_troubleshoot.start_usd`); ``WORST_PIN`` and
#: ``CALLS_PER_ATTEMPT`` are gone with the worst case (the operator, 2026-11-16).
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
    """Kept ONLY for tests/test_fixit_section_v2.py until the full pass updates it (skip mode,
    2026-11-16): `fixit_troubleshoot.start_usd`'s value. Nothing in the product calls it; the
    section's own figure is `start_usd`, drawn as ``least`` (there is no worst case any more)."""
    from modules.ai import fixit_troubleshoot as AIT

    return AIT.start_usd()


def today() -> dict:
    """``{"spent", "cap", "error"}``: today's AI spend (`calls.spent_usd` of the cap's day) and
    the installation's day cap (`gateway.day_cap`; None is no cap), as the toolbar chip reads
    them. *spent* None when the record of calls cannot be read, said in *error*."""
    from modules.ai import calls, gateway

    got = calls.spent_usd(calls.today())
    return {"spent": got["usd"], "cap": gateway.day_cap(),
            "error": got["error"] if got["state"] == "unreadable" else ""}


# ── The section, drawn ──────────────────────────────────────────────────────────────────────

#: What a check's state says, as a subscription's line says it when its run names no outcome.
CHECK_STATE_WORDS = {"fail": "did not pass", "cant_tell": "could not be told"}


def found_said(outcome: str, checks: list) -> str:
    """One subscription's state in words, as What it found's one line says it (the GUI
    review's AI2, C3455): its outcome in the operation's own words, else what its checks say
    ("the stream did not pass; the collector could not be told", "every check passed");
    never an address, a port or a connection number, which are one level down."""
    if outcome:
        return outcome
    if not checks:
        return "nothing was read"
    said = []
    for state, words in CHECK_STATE_WORDS.items():
        names = [f"the {c['name']}" for c in checks if c["state"] == state]
        if names:
            said.append(f"{' and '.join(names)} {words}")
    return "; ".join(said) or "every check passed"


def flag_kind(flag: str) -> str:
    """A stale flag's kind, as a subscription's line names it ("stale half-open"): the words
    before its first colon; the flag's whole words (its addresses and ports) are one level
    down."""
    return str(flag).split(":", 1)[0].strip()


def _run_checks(network: str, run_id: str) -> list:
    """What a run's own record says it found, per subscription: ``[{"sub", "said", "checks":
    [{"name", "state", "words"}], "stale", "flags"}]`` (its verify reads, kept in the record);
    *said* its state in words (`found_said`: its outcome in the operation's words, else its
    checks') and *flags* each stale flag's kind (`flag_kind`), once each, for its one line. A
    read of one record; a record that cannot be read gives nothing (its card says why)."""
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
        words = R.OUTCOME_WORDS.get(outcome, outcome)
        checks = [{"name": k, "state": (v or {}).get("state") or "",
                   "words": (v or {}).get("words") or ""}
                  for k, v in (s.get("verify") or {}).items()]
        stale = [str(f) for f in s.get("stale") or []]
        out.append({"sub": str(s.get("sub") or ""),
                    "said": found_said(words, checks), "checks": checks, "stale": stale,
                    "flags": list(dict.fromkeys(flag_kind(f) for f in stale))})
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
    if operation == R.COLLECTOR_KEY:
        subs = ", ".join(map(str, params.get("subs") or [])) or "no subscription"
        return R.COLLECTOR_TITLE.format(device=device) + f" ({subs})"
    if operation == R.CLOSE_KEY:
        subs = ", ".join(map(str, params.get("subs") or [])) or "no subscription"
        return R.CLOSE_TITLE.format(device=device) + f" ({subs})"
    from modules.heal import catalog
    if catalog.is_command_plan(operation):
        # A built-in command plan (C3757): its own title with the attempt's values.
        from modules.nsot import command_plan
        return command_plan.title_of(operation, dict(params, device=device))
    # Any other step of an incident's plan (an intent change, a deploy): the plan engine's own
    # words for its kind, never its key (R2), with the device.
    from modules import plan_engine
    words = plan_engine.words_of(operation)
    return f"{words} ({device})" if words != operation and device else words


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


def _proposal(incident, line: dict, resolved, now, usd: dict = None) -> dict:
    """The newest proposal, as the proposed state draws it, with what its card opens with, and
    for an AI proposal what is shown of its answer and what its calls cost (*usd*, by call)."""
    from modules.fixit.handover import params_words
    from modules.fixit.policy import money
    from modules.heal import resubscribe as R

    params = line.get("params") if isinstance(line.get("params"), dict) else {}
    subs = (list(params.get("subs") or []) if line.get("operation") in (R.KEY, R.COLLECTOR_KEY,
                                                                         R.CLOSE_KEY)
            else [params["sub"]] if params.get("sub") else [])
    return {"id": line["proposal"], "source": SOURCE_WORDS.get(line.get("source"), ""),
            "operation": line.get("operation") or "",
            "words": (short_words(line["operation"], incident.device, params)
                      if line.get("operation") else ""),
            "params": params_words(params) if params else "", "subs": subs,
            "none": line.get("words") or "", "note": line.get("note") or "",
            "by": line.get("by") or "", "at": line.get("at") or "",
            "flag": _flag(incident, line, resolved, now),
            "shown": line.get("shown") if isinstance(line.get("shown"), dict) else {},
            "calls": list(line.get("calls") or []), "prompt": line.get("prompt") or "",
            "ai_usd": money(sum(((usd or {}).get(c, 0.0) for c in line.get("calls") or []),
                                0.0))}


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
    "cancelled", "handover", "handovers", "retry", "teams", "mode", "advisories", "ended",
    "cant_fix", "page_state"}``; *advisories* the AI analysis kept for the incident today,
    drawn as advice; *cant_fix* whether its kept AI analysis is drawn in full (`analysed`: the
    routes that draw the section then add ``analysis``); *page_state* the incident's one state
    as its whole page says it (`_stated`)."""
    from modules.fixit import handover as H
    from modules.fixit import incident as F
    from modules.fixit import policy as P
    from modules.heal import steplog

    got = incident_of(network, found)
    inc = got["incident"]
    out = {"state": "none", "why": got["why"], "id": found.get("id") or "", "network": network,
           "device": inc.device if inc else "", "totals": {}, "attempts": [], "more": 0,
           "incomplete": "", "stop": {}, "proposal": {}, "cancelled": {}, "handover": {},
           "handovers": [], "retry": {}, "teams": {}, "mode": {}, "unreadable": "",
           "ended": ended if resolved is not None else "",
           "advisories": [{"at": a.get("at") or "", "words": a.get("words") or "",
                           # Whether it ran: one not run sent nothing and is no analysis
                           # (`steplog.ADVISORY_NOT_RUN`), drawn as one closed line.
                           "ran": a.get("state") not in steplog.ADVISORY_NOT_RUN}
                          for a in (found.get("advisories") or [])[-1:]],
           "cant_fix": analysed(found), "ai_failed": ""}
    if inc is None:
        return _stated(out, found)
    now = time.time() if now is None else float(now)
    rec = F.read(inc)
    tried = F.attempts(inc, resolved, now=now)
    calls = F.calls_of(inc)
    cost = F.cost_so_far(inc)
    cap = P.cap_usd(network)
    day = today()
    usd = {c["id"]: c["usd"] for c in calls["calls"]}
    # The calls whose answer is another incident's (`calls_of`'s ``about_other``), read once
    # here for `_contract`'s answer: never drawn as this incident's.
    out["_other_calls"] = {c["id"] for c in calls["calls"] if c.get("about_other")}
    proposals = {ln["proposal"]: ln for ln in rec["lines"] if "proposal" in ln}
    # Each attempt's "Open the run" opens the run's home, its incident's card (the operator,
    # 2026-11-16, one home; C3838), never the device page.
    from modules import plan_engine as PE
    drawn = [dict(_attempt(a, proposals, usd),
                  page=PE.run_page(network, PE.INCIDENT_FIX, {"incident": inc.id}, a["run"]))
             for a in tried["attempts"]]
    out.update(
        attempts=drawn[-SHOWN:], more=max(0, len(drawn) - SHOWN),
        incomplete=tried["error"] if tried["state"] != "ok" else "",
        unreadable=rec["error"] if rec["state"] == "unreadable" else "",
        mode={"state": P.mode(network)["state"], "refused": P.ai_refusal(network)},
        totals={"spent": P.money(cost["usd"]) if cost["usd"] is not None else "",
                "spent_error": cost["error"],
                "cap": P.money(cap["usd"]) if cap["state"] == "ok" else "",
                "cap_error": cap["error"],
                "today": P.money(day["spent"]) if day["spent"] is not None else "",
                "today_error": day["error"],
                "day_cap": P.money(day["cap"]) if day["cap"] is not None else ""},
        handovers=H.versions(inc)["versions"])
    events = [(a["started_at"], 0, "attempt", a) for a in tried["attempts"]]
    # Record lines in their written order at one time (a start and the proposal it led to may
    # share a second): the later line is the newer.
    # A save choice (Not now, board R5's screen 5) is about the offer to save the fix, never a
    # step of the troubleshooting: it moves no state.
    events += [(float(ln["epoch"]), 1 + n, _line_kind(ln), ln)
               for n, ln in enumerate(rec["lines"])
               if _line_kind(ln) not in ("start", "save")
               # C3870: a start that Mercury's own read closed ends there (``closed``), so
               # the card never reads "investigating" after it.
               or ln.get("state") in ("started", "capped", "failed", "closed")]
    # Ties go to the later event: every step of one plan run carries the run's one start, so
    # its attempts tie, and the later step is the newer (the correctness review's G7-D6,
    # 2026-11-18: `max` takes the first of a tie, and a plan whose deploy failed after its
    # intent change passed was drawn "passed").
    newest = max(reversed(events), key=lambda e: (e[0], e[1])) if events else None
    if resolved is not None:
        out["state"] = "resolved"
        _contract(out, network, found, inc, rec, tried, drawn, None, resolved, now)
        return _stated(out, found)
    if newest is None:
        state = "ready"
    elif newest[2] == "start":
        state = ("investigating" if newest[3].get("state") == "started"
                 and now - newest[0] < investigation_bound_s() else
                 "capped" if newest[3].get("state") == "capped" else "ready")
        if newest[3].get("state") == "failed":
            # The investigation's job failed or was refused before anything was sent: drawn in
            # place, never silent (`troubleshoot_job.record_failure`).
            out["ai_failed"] = newest[3].get("words") or "the investigation gave no reason"
        elif newest[3].get("state") == "started" and state == "ready":
            # Started, and nothing came of it within its bound: its job was lost (a restart, a
            # worker gone). Said as a failure, with Ask the AI again, never a dead end.
            out["ai_failed"] = (f"the AI did not answer in {int(investigation_bound_s())} s; "
                                "its job may have stopped (a restart)")
    elif newest[2] == "deny":
        state = "denied"
    elif newest[2] == "approve":
        state = "running"
        lost = approve_lost(network, found.get("id") or "", rec, now)
        if lost:
            # Its run never started (a restart between the approval and its job): the plan is
            # offered again, its one action Approve, and the status says why.
            state = "proposed"
            out["approve_lost"] = {"at": lost["at"]}
    elif newest[2] == "attempt":
        a = newest[3]
        state = ("running" if a["state"] == "running" else "passed" if a["passed"]
                 else "stopped")
        out["stop"] = dict(drawn[a["n"] - 1], found=_run_checks(network, a["run"]))
    elif newest[2] == "proposal":
        state = "proposed"
        out["proposal"] = _proposal(inc, newest[3], resolved, now, usd)
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
    from modules.ai import fixit_troubleshoot as AIT

    # The least one AI call costs (`start_usd`; no worst case since 2026-11-16), and this
    # incident's spend after that least call: named for what they hold.
    least = AIT.start_usd()
    cs = P.cap_state(inc, least)
    out["retry"] = {
        "offered": state in RETRY_IN and cs["state"] == "allowed",
        "in_state": state in RETRY_IN,
        "refused": cs["words"] if cs["state"] != "allowed" else "",
        "least": P.money(least),
        "least_after": P.money(cs["total"]) if cs["total"] is not None else "",
        "drawn_spent": "" if cs["spent"] is None else f"{cs['spent']:.6f}",
        "drawn_cap": "" if cs["cap"] is None else f"{cs['cap']:.6f}",
        "sent": _what_is_sent(drawn, rec["lines"])}
    out["ai"] = ai_offer(state, cs, network)
    out["teams"] = H.offered(network)
    _contract(out, network, found, inc, rec, tried, drawn, cs, resolved, now)
    return _stated(out, found)


def _line_kind(line: dict) -> str:
    """A record line's kind as the section's events name it: ``proposal``, ``start`` or its
    choice (``deny``, ``approve``, ``handover``, ``save``, ``cancel``)."""
    if "proposal" in line:
        return "proposal"
    if "start" in line:
        return "start"
    return line.get("choice") or ""


def investigation_bound_s() -> float:
    """How long a started investigation is drawn as going: the reservation's life
    (`gateway.reservation_ttl_s`, 2.5 times one call's longest time), as the notifier waits."""
    from modules.ai import gateway

    return float(gateway.reservation_ttl_s())


def _href(network: str, incident_id: str, name: str) -> str:
    from urllib.parse import quote

    return f"/v2/incident/{incident_id}/fixit/{name}?list={quote(network)}"


#: What a superseded answer says in place of its content (the operator, 2026-11-15: one
#: switch's incident showed an answer about another switch, C3786).
OTHER_INCIDENT_WORDS = ("Superseded: this answer was about another incident (its call joined "
                        "another device's call, C3771), so it is not shown here")


def _answer_drawn(line: dict, other: set, rec: dict, state: str) -> dict:
    """The AI's newest answer line as the card draws it: its words, what it showed, its calls,
    prompt and time; ``superseded`` (why, or "") when a call it rests on is another
    incident's (`calls_of`'s ``about_other``), its content then withheld, never drawn as this
    incident's; ``previous`` True while a newer investigation runs, the answer then drawn
    labelled as the previous one (the operator, 2026-11-15)."""
    shown = line.get("shown") if isinstance(line.get("shown"), dict) else {}
    superseded = OTHER_INCIDENT_WORDS if set(line.get("calls") or []) & set(other) else ""
    epoch = float(line.get("epoch") or 0)
    newer_start = any("start" in ln and float(ln.get("epoch") or 0) > epoch
                      for ln in rec["lines"])
    prompt = str(line.get("prompt") or "")
    return {"id": line.get("proposal") or "",
            "words": superseded or line.get("words") or "",
            "shown": {} if superseded else shown,
            "gap": "" if superseded else (shown.get("gap") or ""),
            "has_plan": bool(line.get("operation")) and not superseded,
            "calls": list(line.get("calls") or []), "prompt": prompt,
            "version": prompt.rsplit(".", 1)[-1] if "." in prompt else "",
            "at": line.get("at") or "", "note": line.get("note") or "",
            # The steps Mercury's check says a gap overlooked, where the line keeps them
            # (`finding_words` reads them back from its words otherwise).
            "overlooked": [] if superseded else list(line.get("overlooked") or []),
            "superseded": superseded,
            "previous": bool(state == "investigating" or (newer_start and state != "proposed"))}


def _current_proposal(rec: dict, network: str = "", incident_id: str = "", now: float = None):
    """The proposal a person may decide on now: the newest proposal line naming an operation,
    when no deny or approve of it, and no newer proposal, followed it; else None. An approve
    whose run never started (`approve_lost`, asked only with *network* and *incident_id*)
    decides nothing: its proposal may be approved again."""
    lines = rec["lines"]
    last = max((n for n, ln in enumerate(lines) if "proposal" in ln), default=None)
    if last is None or not lines[last].get("operation"):
        return None
    pid = lines[last]["proposal"]
    lost = approve_lost(network, incident_id, rec, now) if network and incident_id else {}
    if any(ln.get("choice") in ("deny", "approve") and ln.get("decides") == pid
           and not (lost and ln is lost.get("line"))
           for ln in lines[last + 1:]):
        return None
    return lines[last]


def approve_start_bound() -> int:
    """How long after an approval its run's record or job must exist (`waits.HEAL_BOUNDS`
    ``approve-start``) before the approval reads as not started."""
    from modules.waits import HEAL_BOUNDS

    return int(HEAL_BOUNDS["approve-start"]["seconds"])


def approve_lost(network: str, incident_id: str, rec: dict, now: float = None) -> dict:
    """The newest approve line whose run did not start (the lead's round 2, 2026-11-16:
    capture_job keeps its jobs in memory, so a process that ended after the approval was
    recorded and before its job started leaves the card "running since" for good):
    ``{"line", "at"}`` when it is the record's newest choice, it is older than
    `approve_start_bound`, its run has no record (`plan_engine.record_of`) and no job for the
    incident runs here (`progress._job_of`); else ``{}``. A read."""
    from modules import plan_engine as PE
    from modules.fixit import progress

    now = time.time() if now is None else float(now)
    choices = [ln for ln in rec.get("lines") or [] if "choice" in ln]
    line = choices[-1] if choices else None
    if not line or line.get("choice") != "approve":
        return {}
    if now - float(line.get("epoch") or now) < approve_start_bound():
        return {}
    try:
        # Across processes (the review, finding 7): the run's record, which any process's job
        # writes, and the device's hold, which any process's run takes before it sends
        # (`device_ops.holder`, a lock file); this process's own job list only adds to them.
        if line.get("run") and PE.record_of(network, line["run"]):
            return {}
        if progress._job_of(network, incident_id) is not None:
            return {}
        from modules import incident_page
        from modules.nsot import device_ops
        device = ((incident_page.resolve(network, incident_id) or {}).get("incident")
                  or {}).get("device") or ""
        if not device or device_ops.holder(network, device):
            return {}
    except Exception as exc:                          # noqa: BLE001 (unread: never "lost")
        log.info("fixit: whether %s's approved run started could not be read: %s",
                 incident_id, exc)
        return {}
    return {"line": line, "at": line.get("at") or ""}


#: A preflight refusal's code (`validate.check`) to the guard that made it: such a guard
#: blocks the plan's step, and its hold line says so.
BLOCKING_CODES = {"planned_work": 3}


def _holds(found: dict, device: str, plan=None) -> list:
    """Each guard or hold that applied to the incident's heal, working as designed, as one
    plain line (`bluf.hold_line`), once each: the step log's newest guard and each decision's.
    A guard whose refusal stopped a step of *plan* at its preflight says it blocks the fix."""
    from modules import bluf as B

    blocking = {BLOCKING_CODES[s["preflight"].get("code")] for s in (plan or {}).get("steps", [])
                if s["preflight"].get("code") in BLOCKING_CODES}
    hits = [(found.get("entry") or {}).get("guard")]
    hits += [d.get("guard") for d in found.get("decisions") or []]
    out = []
    for h in hits:
        n = (h or {}).get("guard") if isinstance(h, dict) else None
        line = B.hold_line(h, device, blocks=n in blocking)
        if line and line not in out:
            out.append(line)
    return out


#: The longest lacked read the fix names (Show commands' own row holds one command).
LACKED_MOST = 240


def lacked_read(answer) -> str:
    """The read the AI's newest answer said would settle the question but its read set does
    not offer (its ``shown["lacked_read"]``, C3797), when that answer proposed no plan and is
    this incident's own: one line a person's Show commands runs (`readonly_commands.refusal`,
    the one allowlist), else ``""``. A read the allowlist refuses is never offered as a
    button: the fix then falls to Ask the AI again or Hand over."""
    from modules import readonly_commands

    if not isinstance(answer, dict) or answer.get("has_plan") or answer.get("superseded"):
        return ""
    shown = answer.get("shown") if isinstance(answer.get("shown"), dict) else {}
    read = shown.get("lacked_read")
    read = " ".join(read.split()) if isinstance(read, str) else ""
    if not read or len(read) > LACKED_MOST or readonly_commands.refusal(read):
        return ""
    return read


def show_commands_href(network: str, device: str, command: str) -> str:
    """Show commands (`routes/reads_v2.py`'s page) for *device* of *network* with *command* in
    its first row: its own query fields, ``q`` the device filter and ``command`` the row, as
    the device's Ask the device card's saved sets link it."""
    from urllib.parse import urlencode

    return "/v2/show-commands?" + urlencode({"list": network, "q": device,
                                             "command": command})


def _contract(out: dict, network: str, found: dict, inc, rec: dict, tried: dict, drawn: list,
              cs, resolved, now: float) -> None:
    """The R1 and R2 contract (the module's docstring, "THE CONTRACT"), added to *out*:
    ``bluf``, ``status``, ``proposal``, ``actions``, ``attempts`` (as drawn), ``other_actions``,
    ``holds`` and ``cap``. A read."""
    from modules import bluf as B
    from modules.fixit import auto as A
    from modules.fixit import plan as FP
    from modules.fixit import policy as P

    state = out["state"]
    iid = out["id"]
    done = resolved is not None
    failed = [a for a in drawn if a["state"] == "failed"]
    out["other_actions"] = [{"operation": a["operation"], "attempt": a["n"],
                             "words": a["words"], "run": a["run"]} for a in failed]
    line = None if done else _current_proposal(rec, network, iid, now)
    plan = FP.preflight(inc, line, now=now) if line else None
    out["holds"] = _holds(found, inc.device, plan)
    out["proposal"] = plan
    # The AI's newest answer as the page draws it, with or without a plan (its diagnosis, its
    # hypotheses and what each cites, the fix's why, or the missing capability it names).
    newest_ai = next((ln for ln in reversed(rec["lines"])
                      if "proposal" in ln and ln.get("source") == "ai"), None)
    other = out.pop("_other_calls", set())
    out["ai_answer"] = None if newest_ai is None or done else _answer_drawn(
        newest_ai, other, rec, state)
    off = P.ai_refusal(network)
    capped = cs is not None and cs["state"] != "allowed"
    starts = [ln for ln in rec["lines"] if "start" in ln]
    last_start = starts[-1] if starts else None
    which = (last_start or {}).get("which") or ("incident" if capped else "")
    cap_reached = state == "capped" or capped
    out["cap"] = {"state": "reached" if cap_reached else "unreadable" if (
                      cs is not None and cs.get("spent") is None and capped) else "ok",
                  "which": which if cap_reached else "",
                  "words": ((last_start or {}).get("words") if state == "capped" else
                            cs["words"] if capped else "")}
    ai_refused = off or (out["cap"]["words"] if cap_reached else "")
    proposed = plan is not None and state == "proposed"
    sw = A.switch(network)
    legacy = (A.manual_start(network, iid, extra=failed, record=found.get("incident") or {})
              if not done else {"offered": False, "words": ""})
    asked = any("proposal" in ln and ln.get("source") == "ai" for ln in rec["lines"])
    # Start AI troubleshooting, a person's press, the R1 flow from step 3: for an incident
    # whose failure will not start an investigation by itself (`auto.manual_start`: the
    # network's switch is off, or the failure was recorded before it was turned on), or one
    # whose automatic start was taken with no AI call (the mode off, hosted AI off); never
    # once the AI was asked or an automatic start went.
    # C3872: a refused start (capped, off) took nothing, so only a start that started, or one
    # Mercury's own read closed, counts as gone.
    went = [s for s in starts if s.get("state") in ("started", "closed")]
    taken_off = any(s.get("state") in ("off", "failed") for s in starts)
    start_offered = (not done and not asked and not went and state in ("ready", "stopped")
                     and (legacy["offered"] or taken_off))
    out["auto"] = auto_model(network, sw)
    # After a denial, or an answer that named no plan (a gap, no fix, the evidence cannot say):
    # the AI may be asked again.
    deny_last = (state == "denied" or (state == "proposed" and plan is None)
                 or bool(out.get("ai_failed"))
                 # An approved plan that stopped (the R1 flow's step 7): with the switch or
                 # Auto off nothing asks again by itself, so the person may.
                 or (state == "stopped" and any(ln.get("choice") == "approve"
                                                for ln in rec["lines"])))
    actions = {
        "approve": {"offered": bool(proposed and plan["approvable"]),
                    "href": _href(network, iid, "approve"),
                    "refused": "" if not proposed or plan["approvable"] else
                    plan["why_refused"]},
        "modify": {"offered": bool(proposed and not ai_refused),
                   "href": _href(network, iid, "modify"),
                   "refused": ai_refused if proposed else ""},
        "deny": {"offered": bool(proposed), "href": _href(network, iid, "deny"), "refused": ""},
        # Also for a plan that can't be approved (refused at its preflight, or its hash moved):
        # asking again is its primary action (the operator, 2026-11-16).
        "ask_again": {"offered": bool((deny_last or (proposed and not plan["approvable"]))
                                      and not ai_refused),
                      "href": _href(network, iid, "ask_again"),
                      "refused": ai_refused if deny_last or proposed else ""},
        "start": {"offered": bool(start_offered and not ai_refused),
                  "href": _href(network, iid, "start"),
                  "refused": ai_refused if start_offered else ""},
        "hand_over": {"offered": not done, "href": _href(network, iid, "handover"),
                      "refused": ""},
    }
    out["actions"] = actions
    lacked = lacked_read(out["ai_answer"])
    # C3805: an Automatic saved script matching the problem fixes it with no AI; an AI answer
    # it overtakes is labelled outdated (the operator's status-line rule, 2026-11-15).
    offers = []
    if not done and state != "passed":
        from modules.nsot import saved_plans
        try:
            # Every matching fix is offered (C3849), an Automatic one first: the first is the
            # next action, the rest its own buttons beside it.
            offers = saved_plans.fix_offers(network, found)
        except Exception as exc:                      # noqa: BLE001 (said; no offer drawn)
            log.error("fixit: %s's saved-script offer could not be read: %s", iid, exc)
    offer = offers[0] if offers else {}
    out["script"] = offer
    if offer and out["ai_answer"]:
        out["ai_answer"]["outdated"] = f"outdated: a saved script now fixes this ({offer['name']})"
    if done or state == "passed":
        # A run that passed its verify leaves nothing to press (the operator, 2026-11-16: a switch's
        # verified AI plan read "No saved fix, and the AI found no safe plan", its next action
        # fallen through to Hand over): its incident closes on that verify at once
        # (`detect.close_verified`), and until it has, the status says the run passed.
        nxt = {"kind": "none", "label": ""}
    elif offer:
        held_now = bool(_held_of(found))
        nxt = {"kind": "button", "script": True,
               "label": (f"Fix now with saved script {offer['name']}" if held_now
                         else f"Fix with saved script: {offer['name']}"),
               "key": offer["key"], "hash": offer["hash"],
               "more": [{"key": o["key"], "hash": o["hash"],
                         "label": f"Fix with saved script: {o['name']}"} for o in offers[1:]]}
    elif actions["approve"]["offered"] or proposed:
        nxt = {"kind": "approve", "label": "Approve the plan" if plan["approvable"] else
               "Modify or deny the plan", "href": actions["approve"]["href"]}
    elif state == "investigating":
        nxt = {"kind": "none", "label": "The AI is investigating"}
    elif actions["start"]["offered"]:
        nxt = {"kind": "start", "label": "Start AI troubleshooting",
               "href": actions["start"]["href"]}
    elif lacked:
        # No plan, and the AI named the read that would settle it but its read set lacks
        # (C3797): a person's read in Show commands, the command filled in, Ask the AI again
        # beside it when offered (the template draws it).
        nxt = {"kind": "button", "label": f"Run {lacked} in Show commands",
               "href": show_commands_href(network, inc.device, lacked), "read": lacked}
    elif actions["ask_again"]["offered"]:
        nxt = {"kind": "button", "label": "Ask the AI again",
               "href": actions["ask_again"]["href"]}
    elif state == "running":
        nxt = {"kind": "none", "label": "The approved plan is running"}
    elif state in ("ready",) and not failed and not starts:
        nxt = {"kind": "none", "label": "Mercury is working on it"}
    else:
        nxt = {"kind": "hand_over", "label": "Hand over", "href": actions["hand_over"]["href"]}
    out["why_person"] = ("" if state == "passed" else
                         _why_person(nxt, offer, found, out.get("ai_answer"), network))
    out["bluf"] = {k: v for k, v in B.bluf(B.model_of(found, nxt)).items()
                   if k in ("what", "impact", "fix", "severity", "title", "since", "evidence",
                            "problem", "kept")}
    # The page draws the problem by its condition (the rest of its fields are the BLUF's
    # words): only what is drawn is carried.
    out["bluf"]["problem"] = {"condition": (out["bluf"].get("problem") or {}).get("condition")
                              or ""}
    newest = next((ln for ln in reversed(rec["lines"]) if "proposal" in ln), {})
    out["status"] = _status(state, inc, network, plan, failed, last_start, legacy, done,
                            out.get("ended") or "", now, said=newest.get("words") or "",
                            failed_words=out.get("ai_failed") or "",
                            approved=_approved(state, rec, out.get("stop") or {}),
                            planned=any("proposal" in ln and ln.get("source") == "ai"
                                        and ln.get("operation") for ln in rec["lines"]))
    out["status"] = _best_status(out["status"], offer, done, found, starts, newest_ai,
                                 proposed and plan.get("approvable"))
    # A troubleshoot that failed (its job's error, a bound passed, a request the provider
    # refused) is the incident's best current knowledge, said with its action: never replaced
    # by why a person is needed, which would say the AI can investigate, or found no safe plan,
    # of an AI that was asked and failed (the operator, 2026-11-15: "a call that was sent and
    # got no answer is a failure, never an answer that named no fix").
    failed_now = "Couldn't troubleshoot:" in out["status"]
    if not done and _held_of(found):
        # A guard holds it: said, with when the next automatic heal is allowed (the operator,
        # 2026-11-16), never "reading it, before it decides".
        out["status"] = _held_of(found)
    elif not done and out["why_person"] and state not in KEEPS_STATUS and not failed_now:
        # Why a person is needed, at a glance, beside its one action (the operator, 2026-11-16).
        # A start a cap refused keeps its own line ("The AI did not start: this incident's AI
        # cap would be passed"): why a person is needed would say the AI found no safe plan.
        out["status"] = out["why_person"]
    # Who said the status line, drawn once as a small label beside it (the operator's wording
    # rule, 2026-11-16): ``AI`` when it is the AI's finding, else none.
    ai_lines = {w for w in (finding_words(out.get("ai_answer")), finding_words(newest_ai))
                if w}
    if not done and plan is not None and state == "proposed" and not plan.get("approvable"):
        # The AI's one-line finding and, plainly, why its fix can't run yet (the operator,
        # 2026-11-16: never "Mercury would refuse a step of it as it stands").
        out["status"] = _refused_plan_words(out.get("ai_answer"), plan.get("why_refused"))
        ai_lines.add(out["status"])
    # A recovery whose port tripped again is its own finding, never "the last attempt did not
    # fix it" (the operator, 2026-11-16): the run's words, "The device with MAC <mac> is still
    # connected to <device> <port>. Port left err-disabled; nothing more sent."
    from modules.nsot.command_plan_run import RETRIPPED
    newest_try = (tried.get("attempts") or [{}])[-1]
    if not done and state == "stopped" and newest_try.get("outcome") == RETRIPPED:
        out["status"] = newest_try.get("words") or out["status"]
    if not done and out.get("approve_lost"):
        # An approval whose run never started (`approve_lost`): said, with Approve its action.
        out["status"] = (f"Approved at {out['approve_lost']['at'] or 'a time not recorded'}, "
                         "but its run did not start (Mercury restarted?): approve again")
    out["status_source"] = "AI" if out["status"] in ai_lines else ""
    # While Mercury works on it, said so with what it is doing now, a spinner beside it
    # (`working`): a saved script's run, or an AI investigation's live step.
    out["working"], out["working_step"], out["investigating"] = "", "", False
    if not done:
        from modules import incident_page
        from modules import troubleshoot_job
        from modules.nsot import saved_plans
        run = saved_plans.running_on(network, iid)
        # C3862: a heal act running on it (a batch's restore or any), THE answer the Incidents
        # row and Needs attention read too (`incident_page.fix_running`).
        heal = {} if run else incident_page.fix_running(network, found)
        if run:
            out["working"] = (f"Self-healing: fixing with saved script "
                              f"{offer.get('name') or 'a saved script'}")
            out["working_step"] = run["step"]
            out["status"], out["status_source"] = out["working"], ""
        elif heal:
            out["working"], out["working_step"] = heal["words"], heal["step"]
            out["status"], out["status_source"] = out["working"], ""
        elif state == "investigating":
            out["working"] = "The AI is investigating"
            out["working_step"] = troubleshoot_job.shown(network, iid)
            # A plan still drawn is the previous one: greyed and not pressable while the new
            # investigation runs (the operator, 2026-11-16).
            out["investigating"] = True


#: The most characters of the AI's finding the status line says, cut at a word (the operator,
#: 2026-11-16: "shortened, not cut mid-word").
FINDING_CHARS = 140
#: The states whose own status line why a person is needed never replaces: the AI or a plan
#: at work (its live step), and a start a cap refused (its cap named).
KEEPS_STATUS = ("investigating", "running", "capped")


def _first_sentence(text, most: int = 0) -> str:
    """The first sentence of *text*, without its full stop; with *most*, cut at the last whole
    word within it, an ellipsis said."""
    text = " ".join(str(text or "").split())
    one = text.split(". ")[0].rstrip(".") if text else ""
    if most and len(one) > most:
        one = one[:most].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return one


def _refused_plan_words(answer, why_refused) -> str:
    """"<the AI's finding>; Mercury refuses its fix as it stands: <the plain reason>." (one
    sentence, its source the AI's label beside it: the operator's wording rule, 2026-11-16)
    from the AI's answer (its rationale) and the plan's refusal, its step and preflight wording
    dropped."""
    shown = (answer or {}).get("shown") or {}
    found = _plain(_first_sentence(shown.get("rationale") or (answer or {}).get("words"),
                                   FINDING_CHARS))
    reason = re.sub(r"^(?:step \d+(?: \([^)]*\))?:\s*|refused at its preflight:\s*)+", "",
                    _first_sentence(why_refused), flags=re.I)
    tail = (f"Mercury refuses its fix as it stands: {reason}" if reason
            else "Mercury refuses its fix as it stands")
    if not found:
        return tail + "."
    return f"{found.rstrip('.…')}; {tail}."


#: The meta-leads an answer's kept words may open with (the AI loop's, before the wording
#: rule): never said, its source is the label beside the line.
META_LEADS = re.compile(
    r"^(?:(?:ai|mercury)\s*:\s*|the ai (?:named no fix|found|thinks|stopped[^:]*|reported a gap"
    r"[^:]*)\s*:\s*|no mercury operation does what the fix needs yet \(a gap\)\s*:\s*)+", re.I)
#: The flag Mercury's check puts on a gap it knows a step for (`fixit_troubleshoot.
#: overlooked_words`), read back from a line kept before the line kept its keys.
FLAGGED = re.compile(r"Mercury's catalogue has (.+?) for this incident's problem, not yet "
                     r"tried here")


def _plain(said: str) -> str:
    """*said* without its meta-leads (`META_LEADS`), its first letter a capital, unless its
    first word is a name with a digit in it (a device or a port: "access1 Gi0/3 saw…" stays)."""
    said = META_LEADS.sub("", str(said or "")).strip()
    first = said.split(" ", 1)[0]
    if not said or any(ch.isdigit() for ch in first):
        return said
    return said[:1].upper() + said[1:]


def _flagged(answer: dict) -> list:
    """The steps Mercury's check says the AI's gap overlooked (its line's ``overlooked``,
    else read back from its words, `FLAGGED`), or ``[]``."""
    keys = [str(k) for k in answer.get("overlooked") or [] if k]
    if keys:
        return keys
    m = FLAGGED.search(str(answer.get("words") or ""))
    if not m:
        return []
    return [k.strip() for k in re.split(r",\s*|\s+and\s+", m.group(1)) if k.strip()]


def finding_words(answer) -> str:
    """The AI's finding as ONE sentence in an engineer's words (the operator's wording rule,
    2026-11-16: "a status line is one sentence in an engineer's words, no meta-prefixes"):
    its rationale's first sentence (else its gap's, else its words without their leads) and,
    where Mercury's check flags the answer, the disagreement said plainly in the same sentence
    ("…; Mercury notes telemetry-readd (Re-add the receiver) exists and is not yet tried
    here."). Its source is drawn once beside it as a label (the section's
    ``status_source``), never in it. ``""`` for no answer, or one superseded or withheld."""
    a = answer if isinstance(answer, dict) else {}
    if not a or a.get("superseded") or a.get("previous"):
        return ""
    shown = a.get("shown") if isinstance(a.get("shown"), dict) else {}
    gap = shown.get("gap") or a.get("gap") or ""
    gap = gap.get("what") if isinstance(gap, dict) else gap
    words = str(a.get("words") or "")
    flagged = _flagged(a)
    if flagged:
        own = shown.get("rationale") or gap or words.split("What it said:", 1)[-1]
    else:
        own = shown.get("rationale") or words or gap or shown.get("diagnosis")
    said = _plain(_first_sentence(own, FINDING_CHARS))
    if flagged:
        from modules import plan_engine as PE
        named = _and_words([f"{k} ({PE.STEP_LABELS.get(k) or PE.words_of(k)})"
                            for k in flagged])
        verb = "exists and is" if len(flagged) == 1 else "exist and are"
        note = f"Mercury notes {named} {verb} not yet tried here"
        said = f"{said.rstrip('.…')}; {note}" if said else note
    if not said:
        return ""
    return said if said.endswith(("…", ".")) else said + "."


def _and_words(items: list) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _why_person(nxt: dict, offer: dict, found: dict, answer: dict = None,
                network: str = "") -> str:
    """Why a person is needed, one short reason beside its one action (the operator,
    2026-11-16), or ``""``: guard 4's disagreement, guard 6's many devices, a saved script, the
    AI's plan, no saved fix yet (the AI can investigate), or nothing safe found. *network*:
    the section's own (the Incidents row's found carries none, C4086)."""
    from modules import problem as P

    inc = (found or {}).get("incident") or {}
    network = network or (found or {}).get("network") or ""
    g = (inc.get("standing") or {}).get("guard")
    g = g.get("guard") if isinstance(g, dict) else g
    if g == 4:
        return "Saved config and intent disagree: decide which is right"
    if g == 6:
        return "Many devices changed at once: approve fixing them all"
    standing = inc.get("standing") or {}
    if standing.get("outcome") == "would_heal":
        # A dry run's would-heal says what Mercury would put back and why it has not (the
        # operator, 2026-11-16: "Would put back the description on Gi3 (self-healing was in
        # dry run)"), from its decision's own units (`incident_page.waits_words`).
        said = _standing_words(found)
        if said:
            return said
    if offer:
        return f"A saved script can fix this: {offer['name']}"
    kind = (nxt or {}).get("kind")
    if kind == "approve":
        return "The AI's plan is ready: needs your approval"
    if kind == "start" or (kind == "button" and not nxt.get("script") and not nxt.get("read")):
        # The AI's latest finding is the best current knowledge, ahead of the retry's reason
        # (the operator, 2026-11-16: a router's status said the 04:53 retry, not the AI's 05:17
        # finding); an answer superseded or withheld is not drawn as this incident's. Its
        # source is the label beside it (`status_source`), never a lead in its words.
        said = finding_words(answer)
        if said:
            return said
        # What Mercury tried on THIS incident and that the AI can investigate, from its own
        # record (the retry policy, the operator, 2026-11-16; `heal.retry.reason`): a lost
        # stream says Mercury has no fix it runs by itself.
        from modules.heal import retry
        try:
            said = retry.reason(network, inc)
        except Exception as exc:                      # noqa: BLE001 (said without it)
            log.error("fixit: %s's retries could not be said: %s", inc.get("id"), exc)
            said = ""
        if said:
            return said + _switch_off(network, inc)
    if kind == "start":
        try:
            prob = P.classify(found)
            what = prob.cause or prob.condition.replace("_", " ")
        except Exception:                             # noqa: BLE001 (said without the cause)
            what = ""
        return (f"No saved fix for {what} yet: the AI can investigate" if what
                else "No saved fix yet: the AI can investigate")
    if kind == "hand_over":
        return "No saved fix, and the AI found no safe plan"
    # Standing on a decision with nothing above to say: the decision's own reason, never a
    # reasonless "waits for a person" (the operator, 2026-11-16).
    return _standing_words(found) if standing else ""


def _switch_off(network: str, inc: dict) -> str:
    """What a lost stream's status line adds while the network's automatic troubleshooting is
    off (ruling 12, the operator, 2026-11-18: "restore 'the switch is off' on the lost stream's
    status line"): ", but automatic troubleshooting is off for this network" (the words R1's
    refusal says, `fixit.auto.eligible`), linked to the switch where it is drawn
    (`switch_linked`); "" for any other incident, with the switch on, or unreadable."""
    from modules.fixit import auto as A

    try:
        if not A.no_code_fix(inc or {}) or A.switch(network)["on"]:
            return ""
    except Exception as exc:                          # noqa: BLE001 (said without it)
        log.error("fixit: %s's automatic troubleshooting switch could not be read: %s",
                  (inc or {}).get("id"), exc)
        return ""
    return ", but automatic troubleshooting is off for this network"


def _standing_words(found: dict) -> str:
    """Why the standing incident of *found* waits for a person, from its decision
    (`incident_page.waits_words`, the one home of that reason), or ``""``."""
    from modules import incident_page

    try:
        return incident_page.waits_words((found or {}).get("incident") or {},
                                         (found or {}).get("entry") or {},
                                         (found or {}).get("decisions") or [], "decided")
    except Exception as exc:                          # noqa: BLE001 (said without it)
        log.error("fixit: why %s waits could not be said: %s",
                  ((found or {}).get("incident") or {}).get("id"), exc)
        return ""


def _held_of(found: dict) -> str:
    """The guard's hold on the incident, said (`incident_page.held_words`), or ``""``."""
    from modules import incident_page
    return incident_page.held_words((found or {}).get("incident") or {})


#: A failed start's words when the press never reached the AI (a refusal before any call):
#: an event for Details, never the headline (the operator's status-line rule, 2026-11-15).
UNASKED = ("was not asked", "refused by the gateway", "nothing was sent to the AI")


def _best_status(status: str, offer: dict, done: bool, found: dict, starts: list,
                 newest_ai, plan_ready) -> str:
    """The status line as the incident's best current knowledge, not its latest event (the
    operator, 2026-11-15): a fix available first ("A saved script can fix this: <name>", "The
    AI's plan is ready"), then the AI's latest real diagnosis, and a failed attempt only when
    nothing else exists; a press that never reached the AI is never the headline. Closed by a
    script: "Fixed by saved script <name> at <instant>"."""
    if done:
        from modules import incident_page
        how = incident_page.fixed_how((found or {}).get("network") or "",
                                      (found or {}).get("incident") or {})
        return f"{how['label']}: {how['words']}." if how else status
    if offer:
        return f"A saved script can fix this: {offer['name']}."
    if plan_ready:
        return "The AI's plan is ready."
    last = starts[-1] if starts else {}
    unasked = last.get("state") == "failed" and any(
        w in str(last.get("words") or "") for w in UNASKED)
    if unasked and newest_ai:
        # The AI's finding, its source the label beside it (`status_source`).
        return finding_words(newest_ai) or "The AI's finding is in Details."
    return status


def _approved(state: str, rec: dict, stop: dict) -> dict:
    """An approved plan's run as the status line says it (item 5, the operator, 2026-11-15:
    "AI plan approved by <user>, passed at 14:29"): ``{"what", "by", "at", "how"}`` for a
    ``running`` or ``passed`` section, *how* ``running since`` or ``passed at`` and *at* an ISO
    UTC instant (the screen draws it in the viewer's zone); ``{}`` otherwise. From the newest
    attempt (`out["stop"]`: who confirmed it, its start and its end), else, before its first
    run is recorded, the approval line (who, when)."""
    if state not in ("running", "passed"):
        return {}
    words = PLAN_APPROVED
    how = "passed at" if state == "passed" else "running since"
    if stop.get("n"):
        source = {v: k for k, v in SOURCE_WORDS.items()}.get(stop.get("source") or "", "")
        at = (stop.get("finished") if state == "passed" else "") or stop.get("started") or ""
        return {"what": words.get(source, f"Attempt {stop['n']}, run"),
                "by": stop.get("actor") or "", "at": at, "how": how}
    line = next((ln for ln in reversed(rec["lines"]) if ln.get("choice") == "approve"), None)
    if line is None:
        return {}
    sources = {ln["proposal"]: ln.get("source") for ln in rec["lines"] if "proposal" in ln}
    return {"what": words.get(sources.get(line.get("decides")) or "", "The plan approved"),
            "by": line.get("by") or "", "at": line.get("at") or "", "how": how}


#: Where the network's background AI switches are turned on and off (Settings › AI, the
#: background features' card, `routes/settings_v2.py`).
SETTINGS_AI_HREF = "/v2/settings/installation?tab=ai"


def auto_model(network: str, sw: dict = None) -> dict:
    """The network's switch for automatic troubleshooting as the section and the Settings card
    draw it (the contract's ``auto``): ``{"feature", "words", "on", "by", "at", "ends",
    "estimate", "settings_href"}``; *estimate* `background.estimate`'s labelled figures (calls
    a day, dollars a day and a month, its basis), shown before Turn on, with the per-incident
    cap and the day cap beside them. A read: no call is made."""
    from modules.ai import background, gateway
    from modules.fixit import auto as A
    from modules.fixit import policy as P

    sw = sw or A.switch(network)
    spec = background.FEATURES[A.FEATURE]
    # No estimate is made on a page draw, on or off (2026-11-17: it was 14.5 s of a 17 s
    # incident page on the host, `background.measured_cost` re-reading the AI calls record each
    # time it changed): on, the switch's own estimate; off, Settings › AI shows it at Turn on.
    est = (sw.get("entry") or {}).get("estimate") or {} if sw["on"] else {}
    estimate = {"label": ("the estimate shown when it was turned on" if sw["on"] else
                          "its estimate, shown in Settings › AI when it is turned on"),
                "calls_per_day": est.get("calls_per_day"),
                "usd_per_day": est.get("usd_per_day"),
                "usd_per_month": est.get("usd_per_month"), "error": ""}
    cap = P.cap_usd(network)
    ends = background.approval_ends(sw["entry"]) if sw.get("entry") else None
    return {"feature": A.FEATURE, "words": spec["words"], "trigger_words": spec["trigger_words"],
            "on": bool(sw["on"]), "by": sw.get("by") or "", "at": sw.get("at") or "",
            "ends": _iso(ends) if ends else "", "estimate": estimate,
            "incident_cap": P.money(cap["usd"]) if cap["state"] == "ok" else "",
            "day_cap": (P.money(gateway.day_cap()) if gateway.day_cap() is not None else ""),
            "settings_href": SETTINGS_AI_HREF, "switch_href": switch_href(network)}


def switch_href(network: str) -> str:
    """Where the network's automatic troubleshooting switch is (the operator, 2026-11-15:
    every sentence naming it links straight to it): the AI toggle on Incidents' control strip
    for *network* (C3748, `control_strip`; on Incidents alone since C3789)."""
    from urllib.parse import quote

    return f"/v2/incidents?list={quote(network or '', safe='')}#ctl-ai"


def _status(state: str, inc, network: str, plan, failed: list, last_start, legacy: dict,
            done: bool, ended: str, now: float, said: str = "",
            failed_words: str = "", approved: dict = None, planned: bool = False) -> str:
    """The section's one status line, in plain words (the contract's ``status``); *said* is
    the newest proposal line's own words (a proposal that names no operation says why);
    *approved* an approved plan's run (`_approved`); *planned* whether the AI has proposed a
    plan in this incident, after which the line never says Mercury's fix failed or that the
    AI did not start by itself (item 5, the operator, 2026-11-15): it says where the AI's
    plan stands."""
    from modules.ai import fixit_troubleshoot as AIT
    from modules.fixit import auto as A

    if done:
        return f"Resolved: {ended or 'closed'}."
    if approved:
        from modules import display_names
        who = display_names.people(approved["by"]) if approved["by"] else "nobody recorded"
        when = f", {approved['how']} {approved['at']}" if approved["at"] else ""
        return f"{approved['what']} by {who}{when}."
    got = A.failures(network, open_ids={inc.id})
    # A hold a person resolves is no failure of a fix that ran (C3732): said as the hold.
    held = [f for f in got["failures"] if f["kind"] == "held"]
    n = len(got["failures"]) - len(held) + len(failed)
    times = {0: "", 1: " once", 2: " twice"}.get(n, f" {n} times")
    lead = f"Mercury's fix failed{times}." if n and not planned else ""
    if planned:
        held, legacy = [], dict(legacy, failure=None, offered=False)
    if not lead and held:
        g = held[-1].get("guard") or {}
        lead = (f"Self-healing is held by guard {g.get('guard')} ({g.get('name') or 'a guard'}): "
                "Mercury cannot fix it alone, a person resolves it.")
    if not lead and legacy.get("failure"):
        # A failure Mercury holds with no attempt of its own: no fix of its own exists for this
        # problem (a lost stream), or its decision stopped it.
        lead = ("Mercury has no fix of its own for this problem."
                if legacy["failure"].get("outcome") == "no_code_fix" else
                "Mercury's fix did not run.")
    if not failed_words and state == "proposed" and said.startswith(
            (AIT.NOT_ANSWERED, AIT.NOT_ANSWERED_BEFORE)):
        # A call that was sent and got no answer is a failure, never an answer that named no
        # fix (the operator, 2026-11-15: a refused request was drawn as one); a line kept
        # before these words were, read again into them.
        if said.startswith(AIT.NOT_ANSWERED_BEFORE):
            kind, _, detail = said[len(AIT.NOT_ANSWERED_BEFORE):].rstrip(")").partition(": ")
            said = AIT.not_answered_words(kind, detail)
        failed_words = said.rstrip(".")
    if failed_words:
        return f"{lead} Couldn't troubleshoot: {failed_words}. Ask the AI again, or hand over."\
            .strip()
    if state == "investigating":
        # The start's instant, never a count of seconds (C3801: "started 0 s ago" stayed 0 s on
        # a card nine minutes on): the screen draws it in the viewer's zone (`times`), so it is
        # right on every draw and needs no ticking.
        at = float((last_start or {}).get("epoch") or now)
        when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at))
        how = "started"
        if (last_start or {}).get("words") == A.CATCH_UP_WORDS and last_start.get("by"):
            # A catch-up's start at the switch's turn-on (C3732): the person who ticked it.
            from modules import display_names
            how = f"started at turn-on by {display_names.people(last_start['by'])}"
        # Board R5's screen 3 (approved 2026-11-15): one line, "The AI is investigating,
        # started at 14:23", its live step after it on the page; its cost (about
        # `estimate()`'s) is the Details', never the default view's.
        return f"The AI is investigating, {how} at {when}"
    if state == "capped":
        which = (last_start or {}).get("which") or "a"
        return (f"{lead} The AI did not start: this incident's AI cap would be passed. "
                "Hand over to an engineer.").strip() if which == "incident" else (
               f"{lead} The AI did not start: the {which} cap would be passed. Hand over to "
               "an engineer.").strip()
    if plan is not None and state == "proposed":
        steps = len(plan["steps"])
        who = {"the AI": "The AI", "Mercury's diagnosis": "Mercury's diagnosis",
               "a person": "A person"}.get(plan.get("source") or "", "The AI")
        plural = "s" if steps != 1 else ""
        if plan["approvable"]:
            return (f"{lead} {who} proposes a plan of {steps} step{plural}. Nothing runs until "
                    "you approve it.").strip()
        # Why is drawn once, on the refused step and beside Approve: never again here.
        return (f"{lead} {who} proposes a plan of {steps} step{plural}, and Mercury would "
                "refuse a step of it as it stands: modify it or deny it.").strip()
    if state == "proposed" and said:
        # What the answer said is drawn below it (its diagnosis, its missing capability): the
        # status names only what kind of answer it was.
        kind = ("the AI found what the fix needs, and no Mercury operation does it yet"
                if said.startswith("No Mercury operation") else
                "the AI's answer couldn't be checked" if "couldn't be checked" in said else
                "the AI says the evidence cannot say" if "cannot say" in said else
                "the AI was not asked" if said.startswith("The AI was not asked") else
                "the AI named no fix Mercury can run")
        return f"{lead} No plan to approve: {kind}. Ask it again, or hand over.".strip()
    if state == "denied":
        return f"{lead} The proposal was denied; nothing ran. Ask the AI again, or hand over."\
            .strip()
    if state == "running":
        return f"{lead} The approved plan is running.".strip()
    if legacy.get("offered"):
        return (f"{lead} {legacy['words']}. Start AI troubleshooting to have the AI "
                "investigate.").strip()
    if state == "stopped":
        return f"{lead} The last attempt did not fix it.".strip()
    if state == "handed_over":
        return f"{lead} Handed over to an engineer.".strip()
    return lead or "Mercury is watching it; nothing has failed yet."


def _stated(out: dict, found: dict) -> dict:
    """*out* with ``page_state``: the incident's state as its whole page says it
    (`incident_page.status`, the ONE function, asked with this section's own state), so the
    section never says a person may leave it while the header says one is needed, or the
    reverse (the GUI review's item 2, C3450). Asked here, so a post that draws the section
    again alone (routes/fixit_v2.py) says the same."""
    from modules import incident_page

    out["page_state"] = incident_page.status(found.get("incident"), found.get("entry") or {},
                                             found.get("decisions") or [],
                                             out["state"])["state"]
    out["card"] = card_of(out, found)
    return out


#: An approved plan's words by who proposed it (`_approved`, `card_of`).
PLAN_APPROVED = {"ai": "AI plan approved", "mercury": "Mercury's plan approved",
                 "person": "A person's plan approved"}
#: Whose plan waits, by who proposed it (board R5's screen 4).
PLAN_READY = {"the AI": "The AI's plan", "Mercury's diagnosis": "Mercury's plan",
              "a person": "A person's plan"}


def card_of(out: dict, found: dict) -> dict:
    """The incident card's default view (MERCURY_CHARTER R5; board R5, approved 2026-11-15,
    screens 3 to 5): ``{"status", "kind", "step", "how", "fixed_at", "plan_ready", "live",
    "run", "run_page", "proof"}``, *proof* a fixed incident's verify (`_proof_of`, drawn one
    line by default and its reads on expand), *live* the live stepper's steps while a job runs
    (`progress.of`),
    *run* an approved plan's run's steps once it ended, each its result (`progress.recorded`),
    *run_page* where Open the run opens a running approved plan (its incident's card at its
    stepper, `plan_engine.run_page`; ``""`` for any other run). *status*
    the one status line (an instant in its words, drawn in the viewer's zone), *kind* ``ai``
    while the AI investigates, ``ok`` once fixed and verified, else ``""``; *step* the
    investigation's live step (`troubleshoot_job.shown`); *how* how a fixed incident was fixed
    (``{"words", "device", "run"}``: the run's record is its link), and *plan_ready* whether a
    plan waits on Approve (its own card, below). A read of *out* and the incident's problem."""
    from modules import bluf as B
    from modules import display_names
    from modules import problem as P

    from modules.fixit import progress

    state = out.get("state") or ""
    card = {"status": out.get("status") or "", "source": out.get("status_source") or "",
            "kind": "", "step": "", "how": None, "fixed_at": "", "plan_ready": False, "run": [], "run_page": "", "proof": {},
            "tail": {}}
    network, iid, device = out.get("network") or "", out.get("id") or "", out.get("device") or ""
    # The compact live stepper while the AI investigates or a run goes (the operator,
    # 2026-11-16): its steps stand in for the one status line (`progress.of`).
    card["live"] = progress.of(network, iid, device, state)
    rid = (progress.approved_run(network, found)
           if state in ("running", "passed", "stopped", "resolved") else "")
    if not card["live"] and rid:
        # The approved plan's run, once it ended (or while it runs in another process), drawn
        # on the card with each step's result: the run's one home (the operator, 2026-11-16).
        newest = (out.get("stop") or {}).get("run") or ""
        if state == "resolved":
            passed = [a.get("run") for a in out.get("attempts") or []
                      if a.get("state") == "passed"]
            newest = passed[-1] if passed else newest
        card["run"] = progress.recorded(network, found, device, newest=newest, rid=rid)
        if state == "running" and card["run"]:
            # Running in another process: its record's steps, redrawn as the live ones are.
            card["live"], card["run"] = card["run"], []
    if state == "running":
        # Open the run opens the run's home: an approved plan's its incident's card at its
        # stepper (`plan_engine.run_page`); a saved script's run its device's page, as before.
        from modules import plan_engine as PE
        rec = PE.record_of(network, rid) if rid else None
        if rec and rec.get("state") == "running":
            card["run_page"] = PE.run_page(network, rec.get("plan"),
                                           {"incident": rec.get("incident") or iid}, rid)
    if state == "resolved" and out.get("ended") == "fixed":
        passed = [a for a in out.get("attempts") or [] if a.get("state") == "passed"]
        a = passed[-1] if passed else None
        record = found.get("incident") or {}
        at = ((a or {}).get("finished") or ((record.get("fixed") or {}).get("at")) or
              record.get("closed_at") or "")
        try:
            back = B.restored(P.classify(found))
        except Exception:                             # noqa: BLE001 (said without it)
            back = ""
        card.update(kind="ok", source="", fixed_at=at, status=(
            f"Fixed{' at ' + at if at else ''}, verified" + (f"; {back}" if back else "") + "."))
        if a:
            source = {v: k for k, v in SOURCE_WORDS.items()}.get(a.get("source") or "", "")
            what = PLAN_APPROVED.get(source, f"Attempt {a['n']}, run")
            who = display_names.people(a["actor"]) if a.get("actor") else "nobody recorded"
            card["how"] = {"words": f"{what} by {who}", "device": a.get("device") or "",
                           "run": a.get("run") or ""}
        else:
            card["how"] = {"words": "Mercury's self-healing, verified on the device",
                           "device": "", "run": ""}
        if card["run"] and card["how"].get("run"):
            # The plan's run is drawn on this card: its link opens it here.
            card["how"]["page"] = "#inc-run"
        fixed = record.get("fixed") or {}
        if fixed.get("script"):
            # A saved fix closed it (`saved_plans.close_fixed`): its own page (C3849 piece 3).
            card["how"]["fix"] = {"key": fixed["script"],
                                  "name": fixed.get("name") or "the saved fix"}
        # "Fixed" shows its proof (the operator, 2026-11-16): the verify's reads, one line by
        # default, the output on expand (`fixit.proof`).
        card["proof"] = _proof_of(network, a, record, found)
        # The heal's tail under Fixed (the operator, 2026-11-16, decisions (a) and (b)): its
        # save, golden commit and read again, live while they run, a failure its flag.
        card["tail"] = _tail_of(network, device, found)
        return card
    if state == "investigating":
        from modules import troubleshoot_job
        card.update(kind="ai", step=troubleshoot_job.shown(out.get("network") or "",
                                                           out.get("id") or ""))
        return card
    plan = out.get("proposal") if isinstance(out.get("proposal"), dict) else None
    approve = ((out.get("actions") or {}).get("approve") or {}).get("offered")
    if state == "proposed" and plan and plan.get("steps") is not None and approve \
            and plan.get("approvable"):
        who = PLAN_READY.get(plan.get("source") or "", "The plan")
        took = _plan_took(out, found)
        # Collapsed to one line once ready ("Plan ready in 1 min 27 s").
        card.update(plan_ready=True, source="", status=(
            f"Plan ready in {progress.took_words(took)}: approve it below" if took else
            f"{who} is ready for your approval, below"))
    return card


def _tail_of(network: str, device: str, found: dict) -> dict:
    """A heal's tail on the card (`heal.act.tail_card`), or ``{}`` (no tail recorded, or it
    cannot be read: the card is drawn without it)."""
    from modules.heal import act

    try:
        return act.tail_card(network, device, (found or {}).get("entry") or {})
    except Exception as exc:                          # noqa: BLE001 (drawn without it)
        log.error("fixit: %s's tail could not be read: %s", device, exc)
        return {}


def _proof_of(network: str, attempt, record: dict, found: dict) -> dict:
    """The proof of the fix that closed the incident (`fixit.proof`): the passed attempt's run
    (an approved plan's step, a saved script's), else the run its close names, else the heal
    act's verify (kept on its close, else the act's own steps). ``{}`` when none is kept."""
    from modules import incident_page
    from modules.fixit import proof as PR

    fixed = (record or {}).get("fixed") or {}
    try:
        for run_id in ((attempt or {}).get("run"), fixed.get("run")):
            got = PR.of_run(network, run_id or "")
            if got:
                return got
        if fixed.get("verify"):
            return PR.of_act(network, fixed["verify"])
        ran = [a for a in incident_page.acts((found or {}).get("entry") or {}) if a["passed"]]
        return PR.of_act(network, ran[-1]["steps"]) if ran else {}
    except Exception as exc:                          # noqa: BLE001 (drawn without it)
        log.error("fixit: %s's proof could not be read: %s", (record or {}).get("id"), exc)
        return {}


def _plan_took(out: dict, found: dict):
    """Seconds from the investigation's start to the plan it proposed, or None (no start line
    before it, or a record that cannot be read). A read."""
    from modules.fixit import incident as F

    inc = incident_of(out.get("network") or "", found).get("incident")
    try:
        lines = F.read(inc)["lines"] if inc is not None else []
    except Exception:                                 # noqa: BLE001 (said without it)
        return None
    last = max((n for n, ln in enumerate(lines) if "proposal" in ln), default=None)
    if last is None:
        return None
    start = next((ln for ln in reversed(lines[:last]) if "start" in ln), None)
    if not start:
        return None
    return float(lines[last].get("epoch") or 0) - float(start.get("epoch") or 0) or None


def analysed(found: dict) -> bool:
    """Whether the incident is one whose AI analysis the page draws in full (C3488: the page
    drew its one advisory line, and the answer itself only on the incident's Needs attention
    row): a can't-fix, by the rule its row draws the analysis by (`attention.is_cant_fix`).
    The section reads no analysis itself: what is kept is read by the one page-side reader of
    the analysis (`routes.v2.heal_analysis_of`, a read of its store and never a call), which
    the routes that draw the section ask (tests/test_read_loop_never_read.py holds the exact
    list of who reaches it)."""
    from modules import attention

    return bool(found.get("id")) and attention.is_cant_fix((found.get("entry") or {})
                                                           .get("outcome"))


#: The states in which the AI may be asked: nothing tried yet (Troubleshoot with AI), and
#: those Retry is offered in (its Ask the AI to re-plan).
AI_IN = ("ready",) + RETRY_IN


def ai_offer(state: str, cs: dict, network: str = None) -> dict:
    """Whether the section offers the AI for a section in *state* whose cap comparison is *cs*
    (`policy.cap_state` at the AI's worst case): ``{"offered", "in_state", "refused",
    "estimate", "worst", "measured", "basis"}``. Offered only in `AI_IN`, the mode Manual
    (`policy.ai_refusal`) and the cap allowing it; whether hosted AI can answer now is the AI
    control's own readiness, drawn on its button (`modules/ai/controls.py`). The figures are
    drawn before the press (`fixit_troubleshoot.estimate`: no call made)."""
    from modules.ai import fixit_troubleshoot as AIT
    from modules.fixit import policy as P

    off = P.ai_refusal(network)
    est = AIT.estimate()
    return {"offered": state in AI_IN and not off and cs["state"] == "allowed",
            "in_state": state in AI_IN, "refused": off or (
                cs["words"] if cs["state"] != "allowed" else ""),
            # No worst case and no calls bound (the operator, 2026-11-16): "least" is the least
            # one call costs; the spending limits stop the spend.
            "estimate": P.money(est["usd"]), "least": P.money(est["least"]),
            "measured": est["measured"], "basis": est["basis"]}


def drawn(network: str, found: dict, *, resolved: float = None, ended: str = "",
          now: float = None) -> dict:
    """`view` as a page draws it: every text masked again on the way out (`steplog.masked`) and
    every person named by display name (`display_names.people_payload`). Only what the section
    draws is carried: why a person is needed is drawn as the status line it becomes (`view`),
    and the steps a gap overlooked as the finding's words and ``shown.gap_overlooked``, so
    neither is handed on (the Incidents list reads why a person is needed from `view`)."""
    from modules import display_names
    from modules.heal import steplog

    out = view(network, found, resolved=resolved, ended=ended, now=now)
    out.pop("why_person", None)
    if isinstance(out.get("ai_answer"), dict):
        out["ai_answer"] = {k: v for k, v in out["ai_answer"].items() if k != "overlooked"}
    return display_names.people_payload(steplog.masked(out))


# ── Mercury's diagnosis, and what moved since the panel was drawn ─────────────────────────

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


# ── The operation's card, opened from the section ───────────────────────────────────────────

def _card(network: str, incident_id: str, proposal: str, device: str, subs, readd: bool,
          collector: bool = False):
    """``(incident, link)`` for `card_link`; *incident* None when *link* is a refusal. The
    link names the proposal's operation (``operation``: the card draws the collector step for
    one that names it, C3078)."""
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
    operation = next((ln.get("operation") or "" for ln in rec["lines"]
                      if proposal and ln.get("proposal") == proposal), "")
    # The repeat is read under the operation that RUNS (*collector*: the card drew the step), never
    # the proposal's own: a collector proposal whose step the card could not take runs, and is
    # recorded as, the plain re-subscribe.
    subs = [str(s) for s in subs or ()]
    if not subs:
        flag = {"kind": "new"}
    elif readd:
        flag = F.repeat_of(inc, R.READD_KEY, {"sub": subs[0]})
    elif collector:
        flag = F.repeat_of(inc, R.COLLECTOR_KEY, {"subs": subs})
    else:
        flag = F.repeat_of(inc, R.KEY, {"subs": subs})
    flag = dict(flag, changed=[{"name": c["name"], "before": _said(c["before"]),
                                "after": _said(c["after"])} for c in flag.get("changed") or []])
    if flag.get("kind") != "new":
        flag["words"] = outcome_words(flag.get("outcome") or "", flag.get("words") or "")
    return inc, {"incident": incident_id, "proposal": proposal or "", "repeat": flag,
                 "operation": operation}


def card_link(network: str, incident_id: str, proposal: str, device: str, subs,
              readd: bool = False, collector: bool = False) -> dict:
    """What the operation's card carries when it is opened from the section's proposal, read
    for its form: ``{"incident", "proposal", "repeat", "operation"}`` (*repeat*
    `incident.repeat_of` for the subscriptions ticked, or the one a re-add names; *operation*
    the proposal's), or ``{"incident", "proposal", "refused": why}``, which the confirm refuses
    again. A read."""
    got = _card(network, incident_id, proposal, device, subs, readd, collector)[1]
    return dict({"incident": incident_id, "proposal": proposal or ""}, **got)


#: A repeat's "what is different now" is one line of at least this many words.
DIFFERENT_WORDS = 3


def confirm_link(network: str, incident_id: str, proposal: str, device: str, subs,
                 different: str = "", readd: bool = False, collector: bool = False) -> dict:
    """What the operation's confirm writes into its run record (`incident.RUN_FIELD`) when it
    was opened from the section: the incident, the attempt's number and the proposal
    (`incident.run_link`), and, for a proposal that repeats a failed attempt, the person's
    "what is different now" (`different`), required. Raises `Refused` naming what it compared,
    with nothing sent. A read."""
    from modules.fixit import incident as F

    inc, got = _card(network, incident_id, proposal, device, subs, readd, collector)
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
