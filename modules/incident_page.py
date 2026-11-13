"""One incident's page (`/v2/incident/<id>`; the incident page's board, parts B, C and F; the
operator's design change of 2026-11-11: "each incident gets its own page"): the page for one
self-healing incident (an ``hi-`` id), with its timeline, its TIME TO REPAIR, its one state
and its one action. A read throughout: it reads three of the network's stores and the list
Needs attention holds, and writes nothing, creates no network and reaches no device.

**What it reads, for one id** (no per-device work: each is one read of a network's own store):
- the incident, from the heal incidents (`heal.incidents.read`): its device, its triggers,
  its members, whether it is open, and where it was folded;
- its step-log entry (`heal.steplog.incident`): every step Mercury took, each with its own
  time, the outcome and its records;
- its decisions (`heal.decisions.decisions`): what was decided and when, who took each one
  (the policy's apply, or a person's approval), and what was applied;
- the AI analysis kept for it today (`heal.steplog.advisories`), drawn as advice.

**The header's fields, each from a recorded time** (the board's B0; `timeline`):
- **Detected:** the event's receive time, the incident's first trigger's ``epoch``.
- **Decided:** when the fix was chosen: a heal decision's ``at``, or the ``at`` of a person's
  approval of a proposal (its ``taken`` row).
- **Applied** (per attempt): when the attempt's fix was on the device, whatever its verify then
  said: the act's ``intent`` step's ``at`` (an action's ``send`` step's); where the act
  recorded neither (the deploy's own verify failed before the heal's check), the ``at`` of the
  ``apply`` step that recorded its end.
- **Fixed:** the applied time of the attempt whose verify PASSED, and only that.
- **Verified:** the ``at`` of the act's ``record`` step, when its outcome is a passed verify
  (`passed`: `run_card.HEALED`, an allowlist).
- **TIME TO REPAIR:** verified minus detected, in whole seconds, drawn only from a passed
  verify, by THE one function its Done stage uses too (`run_card.repair_seconds`), its span in
  the one format (`run_stepper.duration_words`). Computed each time, never stored.
- **Its span:** a resolved incident ends when it ended (`ended_at`): a fixed one at its
  verify, a declined one at the decline, a cleared one at its close. Its close is the act's
  record step for an incident its act closed (`closed_at`), never the act's start, with which
  the act stamps its store's close.
- **A drill:** a declared fault drill's incident says Drill beside its state, its drill's
  ``fd-`` id on hover (`drill_of`), by the tag it took at its creation (`drill_tag`).
- **who:** "by Mercury's self-healing · policy set by <display name>" (`run_card.by_words`,
  the words its card and History use) only where the record shows no person in the
  incident: the act ran in Auto as the policy, no approval is recorded, and every take was the
  policy's apply; "by Mercury's self-healing · approved by <display name>" where a person
  approved the fix. Anything else names nobody.

**What Mercury has done** is the heal's card as its device's page draws it (`heal_card`):
THE stepper's five stages (Detected, Decided, Fixing, Checking, Done; `run_stepper.stages`
through `run_card`), never a second stepper or a copy of the steps.

**Page speed** (CLAUDE.md, "No page load or badge poll waits on…"): every read is of what the
background already holds, the network's own heal stores and this server's jobs; nothing here
reaches a device, Grafana, Loki or NetBox.

**A failed verify never reads "Fixed"** (the operator, 2026-11-11). An attempt that was sent
and whose outcome is not a passed verify (rolled back, failed, partial, symptom remains,
interrupted: `steplog.NOT_HEALED`) leaves the incident "needs a person"; its Fixed cell reads
"not fixed", its Verified cell "failed" at its time, its attempt "applied <time> · verify
failed", and its TIME TO REPAIR "not repaired".

**Each fact once** (the GUI review's item 6, C3454; docs/UI_RULES.md, "Each fact appears once
on a screen"): the header's cells and the attempt line hold state words, each reason on the
hover; the failure's sentence is said once, in the stage where it happened, on THE stepper
(`run_stepper.stages`), and the timeline says each attempt's outcome by its mark. Measured
before: "verify failed" five times on the rolled-back incident's page.

**The five states** (`state_of`, from the heal's own records): ``open`` (Mercury is watching
or working), ``needs_person``, ``fixed`` (a verified fix), ``cleared`` (closed with no fix
recorded) and ``cancelled`` (a person declined the proposed fix).

**One state for the whole page** (`status`; the GUI review's item 2, C3450, the operator,
2026-11-13): the page's state is `state_of`'s answer AND the incident's troubleshooting
record's (a fix a person ran that stopped, a fix proposed, one running or passed), and a lost
telemetry stream needs a person from the start (its fix is a person's to approve). The
header's badge and level, What's wrong, What Mercury has done, What to do and AI
troubleshooting (`fixit.section.view` asks the same function) each draw that one answer.

**Its action** is its own Needs attention item's (`item_of`, read from the list the
background holds, never reckoned a second time; which action being `attention.first_action`'s
answer, the resolver the item's line asks): What to do draws it as the page's one primary
button while a person is needed, and none otherwise. The page itself starts nothing: an
action's card (a proposal's, a Re-subscribe's) is its operation's own route, read when the
button is pressed. **What the item kept under its Details is drawn here** (C3488): Mercury's
diagnosis in full, the AI analysis in full (the routes add it to the section through the one
page-side reader of the analysis, `routes.v2.heal_analysis_of`), a lost stream's
reachability, what Mercury cannot see and Seen before, and a decision's mode, fix kind and
program hash in The record.

**People** are drawn by display name (`identity.display_name`, `display_names.people` over
every recorded text); the identity as recorded is only in the page's collapsed record.
**Secrets:** every text is masked again on the way out (`steplog.masked`).

**What this slice does not hold, said so it is not read as held:** the severity is derived
from the outcome each time (the incident index, a later slice, keeps the level the Needs
attention card had); only ``hi-`` ids have a page; an incident past the newest
`incidents.CLOSED_KEPT` closed ones is drawn from its step log alone, and says so.
"""

import calendar
import logging
import re
import time

log = logging.getLogger(__name__)

#: A self-healing incident's id, as `heal.incidents._new` mints it.
HI = re.compile(r"hi-[0-9a-f]{12}\Z")
STATES = ("open", "needs_person", "fixed", "cleared", "cancelled")
STATE_WORDS = {"open": "Open", "needs_person": "Needs a person", "fixed": "Fixed",
               "cleared": "Cleared", "cancelled": "Cancelled"}
#: The states in which nothing is left for Mercury or a person to do.
RESOLVED = ("fixed", "cleared", "cancelled")
#: The fix-it section's states (`fixit.section.STATES`) in which a person's choice is waited
#: for, each with why the page then needs a person (`status`); and those in which a fix a
#: person approved is under way or passed, so nobody is needed now.
FIXIT_WAITS = {"stopped": "attempt_stopped", "proposed": "fix_proposed",
               "cancelled": "troubleshooting_cancelled", "handed_over": "handed_over"}
FIXIT_WORKING = {"running": "attempt_running", "passed": "attempt_passed"}
#: Why the page's state is what it is (`status`), each said once, as What to do's words.
WHYS = RESOLVED + ("healing", "watching", "verify_failed", "proposal", "decided",
                   "lost_stream") + tuple(FIXIT_WAITS.values()) + tuple(FIXIT_WORKING.values())
#: A level in Needs attention's own words (`templates/v2/_attention.html`, ``LEVEL_WORDS``).
LEVEL_WORDS = {"danger": "Critical", "warning": "Warning", "unknown": "Unknown"}
#: The level a decision's outcome has on Needs attention (`attention.heal_source`'s rows).
DECISION_LEVELS = {"cant_fix": "danger", "propose": "danger", "halted": "danger",
                   "held": "warning", "would_heal": "warning"}
#: An act's outcomes that sent nothing: no attempt was made.
NOT_SENT = ("refused", "declined", "withdrawn")
#: The steps whose time is when the fix was on the device, in the order they are looked for:
#: a heal's check of each unit at intent (the first step after its program was sent), then an
#: action's send.
APPLIED_STEPS = ("intent", "send")
#: How a take by a person reads in the decisions store (`propose.approve`, `propose.decline`),
#: and the policy's own (`act.act_one`, `act.run`).
APPROVED, DECLINED, POLICY_TAKE = ": approved", ": declined", ": the apply"
#: The policy's ``by`` on an act row, as `steplog.policy_words` writes it.
_POLICY_BY = re.compile(r".+ \(policy set by .+\)\Z")
#: The decision a close names, as `act`'s and `decide`'s closes end their why: "(decision
#: hd-…)".
_CLOSED_BY = re.compile(r"\(decision (hd-[0-9a-f]{12})\)\Z")
#: Where a text drawn on the page stops; the whole of it is in the record. (A title's bound
#: is THE title builder's, `said.TITLE_MAX`.)
REASON_CHARS = 200
#: How many of a list the page draws before it counts the rest.
TRIGGERS_SHOWN = 5
MEMBERS_SHOWN = 10
#: What each trigger kind's time is (the board's B0, "Detected at").
BASIS = {"config_change": "Mercury's log reader received the device's configuration-change "
                          "line (the event's receive time)",
         "alert": "the alert began (Grafana's time)",
         "adjacency": "the adjacency went down, as the adjacencies reader recorded it",
         "adjacency_log": "Mercury's log reader received the adjacency drop's line (the "
                          "event's receive time)",
         "duplicate_router_id": "Mercury's log reader received the duplicate router-id line "
                                "(the event's receive time)",
         "drift": "the drift check that found it ran"}


def _epoch(iso):
    """An ISO time a record keeps (``2026-11-11T18:05:12Z``) as an epoch, or None."""
    try:
        return calendar.timegm(time.strptime(str(iso or "")[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, OverflowError):
        return None


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _cut(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def passed(outcome: str) -> bool:
    """Whether an act's recorded *outcome* is a verify that PASSED: one of `run_card.HEALED`,
    an allowlist. Every other outcome is not a fix, whatever it sent."""
    from modules.heal import run_card

    return outcome in run_card.HEALED


# ── Where an id is held ─────────────────────────────────────────────────────────────────────

def resolve(network: str, incident_id: str) -> dict:
    """Where *incident_id* is held in *network*: ``{"found", "id", "network", "incident",
    "entry", "decisions", "advisories", "unreadable", "into"}``. *found* is ``page`` (a record
    holds it), ``folded`` (closed into ``into``: its address redirects there), ``other_kind``
    (not an ``hi-`` id: its page is a later slice's), ``unreadable`` (no record that could be
    read holds it, and one could not be read: absent is not known) or ``unknown`` (every
    store was read and none holds it). ``unreadable`` names each store that could not be
    read. A read: it creates nothing."""
    from modules.heal import decisions as HD
    from modules.heal import incidents, steplog

    iid = str(incident_id or "")[:64]
    out = {"found": "unknown", "id": iid, "network": network, "incident": None, "entry": {},
           "decisions": [], "advisories": [], "unreadable": [], "into": ""}
    if not iid.startswith("hi-"):
        return dict(out, found="other_kind")
    if not HI.match(iid):
        return out
    got = incidents.read(network)
    if got["state"] == "unreadable":
        out["unreadable"].append(got["error"])
    else:
        out["incident"] = next((i for i in got["incidents"] if i.get("id") == iid), None)
    try:
        out["entry"] = steplog.incident(network, iid) or {}
    except RuntimeError as exc:
        out["unreadable"].append(str(exc))
    try:
        out["decisions"] = [d for d in HD.decisions(network) if d.get("incident") == iid]
    except RuntimeError as exc:
        out["unreadable"].append(str(exc))
    adv = steplog.advisories(network)
    if adv["state"] != "unreadable":
        out["advisories"] = list(adv["by_incident"].get(iid) or [])
    inc = out["incident"]
    if inc and inc.get("state") == "closed" and inc.get("folded_into"):
        return dict(out, found="folded", into=str(inc["folded_into"]))
    if inc or out["entry"] or out["decisions"]:
        return dict(out, found="page")
    return dict(out, found="unreadable" if out["unreadable"] else "unknown")


# ── What ran, and who took part ─────────────────────────────────────────────────────────────

def acts(entry: dict) -> list:
    """Each act the entry holds, in order: the steps recorded under one decision by anything
    but the decision itself (its ``started``, ``act`` and ``interrupted`` rows). Each is
    ``{"decision", "steps", "outcome", "sent", "running", "passed", "applied_at", "ended_at",
    "words"}``; *outcome* is its ``record`` step's result, *sent* whether anything reached the
    device (an act that was refused, declined or withdrawn sent nothing)."""
    groups = {}
    for s in entry.get("steps") or []:
        if isinstance(s, dict) and s.get("row") not in ("decision", None):
            groups.setdefault(s.get("decision") or "", []).append(s)
    out = []
    for n, (decision, steps) in enumerate(groups.items()):
        last = n == len(groups) - 1
        rec = next((s for s in reversed(steps) if s.get("step") == "record"), None)
        outcome = str((rec or {}).get("result") or "")
        running = rec is None and last and entry.get("state") == "applying"
        sent = bool(outcome) and outcome not in NOT_SENT
        if last and entry.get("state") == "done":
            sent = bool(entry.get("sent")) and outcome not in NOT_SENT
        applied = ""
        for key in APPLIED_STEPS:
            applied = next((str(s.get("at") or "") for s in steps
                            if s.get("step") == key and s.get("at")), "")
            if applied:
                break
        if not applied and sent:
            applied = next((str(s.get("at") or "") for s in reversed(steps)
                            if s.get("step") == "apply" and s.get("result") != "running"
                            and s.get("at")), "")
        out.append({"decision": decision, "steps": steps, "outcome": outcome, "sent": sent,
                    "running": running, "passed": sent and passed(outcome),
                    "applied_at": applied, "ended_at": str((rec or {}).get("at") or ""),
                    "words": str((entry.get("words") if last else (rec or {}).get("words"))
                                 or (rec or {}).get("words") or "")})
    return out


def _taken_by(d: dict) -> str:
    return str((d.get("taken") or {}).get("by") or "")


def who_of(entry: dict, decisions: list) -> dict:
    """Who took part in the fix: ``{"kind", "actor"}``. ``person`` with the approver's identity
    where a person approved it (the act's ``approval`` record, or a take that says
    approved); ``none`` (no person took part) only where the record shows the policy alone:
    the act ran in Auto, its ``by`` is the policy's, no approval is recorded and every take is
    the policy's apply, its *actor* then the policy's setter as the act recorded them
    (`run_card.entry_by`, whose decision it ran under); else ``unknown``, which names nobody
    and claims nothing."""
    from modules.heal import run_card

    approval = str((entry.get("records") or {}).get("approval") or "")
    for d in decisions:
        by = _taken_by(d)
        if by.endswith(APPROVED):
            return {"kind": "person", "actor": by[:-len(APPROVED)]}
    if approval.startswith("approved by ") and entry.get("by"):
        return {"kind": "person", "actor": str(entry["by"])}
    takes = [_taken_by(d) for d in decisions if d.get("taken")]
    if (entry.get("mode") == "auto" and not approval and takes
            and all(t.endswith(POLICY_TAKE) for t in takes)
            and _POLICY_BY.match(str(entry.get("by") or ""))):
        actor, kind = run_card.entry_by(entry)
        return {"kind": "none", "actor": actor if kind == "policy" else ""}
    return {"kind": "unknown", "actor": ""}


def _declined(decisions: list) -> dict:
    """The decision a person declined, or ``{}``."""
    return next((d for d in reversed(decisions) if _taken_by(d).endswith(DECLINED)), {})


def state_of(incident, entry: dict, decisions: list) -> str:
    """The incident's state, one of `STATES`, from its records:
    - ``open``: its store holds it watching, ready or claimed, with no proposal waiting; or
      its act is applying;
    - ``needs_person``: it stands on a decision (a would-heal in dry run, a can't-fix, a
      hold), a proposal waits for a person, self-healing halted on it, or an act ended
      without a passed verify (**a failed verify is never fixed**; a heal refused at its
      apply sent nothing and fixed nothing, so a person reads it too);
    - ``fixed``: its last act's verify passed;
    - ``cancelled``: a person declined the fix proposed;
    - ``cleared``: closed with no fix recorded."""
    from modules.heal import incidents

    inc = incident or {}
    ran = acts(entry)
    last = ran[-1] if ran else None
    newest = decisions[-1] if decisions else {}
    if inc.get("state") in incidents.OPEN_STATES:
        if inc["state"] == "standing":
            return "needs_person"
        if newest.get("outcome") == "propose" and not newest.get("taken"):
            return "needs_person"
        return "open"
    if last and last["running"]:
        return "open"
    if last and last["passed"]:
        return "fixed"
    if _declined(decisions):
        return "cancelled"
    if last:
        return "needs_person"
    outcome = entry.get("outcome") or newest.get("outcome") or ""
    if outcome == "halted":
        return "needs_person"
    if not inc and outcome in incidents.STANDS + ("propose",):
        # Known from the step log alone (its own record is not kept or not readable): the
        # last thing recorded is a decision that leaves it to a person.
        return "needs_person"
    return "cleared"


def status(incident, entry: dict, decisions: list, fixit: str = "") -> dict:
    """THE incident's state as its page says it, from ONE function for the page and every
    section on it (the GUI review's item 2, C3450; the operator, 2026-11-13): ``{"state",
    "words", "needs", "why"}``. *state* is one of `STATES`, *words* its badge's, *needs*
    whether a person is needed now, and *why* one of `WHYS`, which What to do says in words.
    The header's badge and level, What's wrong, What Mercury has done, What to do and AI
    troubleshooting (`fixit.section.view`, which asks this function too) each draw this
    answer, so no part of the page says "No person needed" or "Mercury is working on it"
    beside another saying "Stopped … Nothing more runs unless you choose".

    From the incident's own records (`state_of`) AND its troubleshooting record's state
    (*fixit*, `fixit.section.STATES`), in this order:
    - resolved (``fixed``, ``cleared``, ``cancelled``): as `state_of` says, whatever was tried;
    - ``open``, nobody needed now: its heal is applying (``healing``); a fix a person approved
      is running or passed its verify (``attempt_running``, ``attempt_passed``: the incident
      closes when its symptom clears);
    - ``needs_person``: a fix a person ran stopped without fixing it, a fix is proposed, its
      troubleshooting was cancelled or handed over (`FIXIT_WAITS`: nothing more runs unless a
      person chooses); else `state_of` says so (``verify_failed``, ``proposal``, ``decided``);
      else its triggers are lost telemetry streams (``lost_stream``: their fix changes the
      device's configuration, so a person approves it, as its Needs attention row says);
    - else ``open``, Mercury watching or deciding (``watching``)."""
    from modules.heal import diagnose_stream

    heal = state_of(incident, entry, decisions)
    ran = acts(entry)
    last = ran[-1] if ran else None
    newest = decisions[-1] if decisions else {}
    if heal in RESOLVED:
        state, why = heal, heal
    elif last and last["running"]:
        state, why = "open", "healing"
    elif fixit in FIXIT_WORKING:
        state, why = "open", FIXIT_WORKING[fixit]
    elif fixit in FIXIT_WAITS:
        state, why = "needs_person", FIXIT_WAITS[fixit]
    elif heal == "needs_person":
        state = "needs_person"
        why = ("verify_failed" if last and last["sent"] and not last["passed"] else
               "proposal" if newest.get("outcome") == "propose" and not newest.get("taken")
               else "decided")
    elif diagnose_stream.target_from(incident or {}):
        state, why = "needs_person", "lost_stream"
    else:
        state, why = "open", "watching"
    return {"state": state, "words": STATE_WORDS[state], "needs": state == "needs_person",
            "why": why}


# ── The timeline ───────────────────────────────────────────────────────────────────────────

def _cell(state: str, at: str = "", words: str = "", hover: str = "") -> dict:
    """One header cell: *state* is ``at`` (a recorded time), ``not_yet``, ``not_needed``,
    ``failed`` (a verify that failed, at its time) or ``none`` (empty, with its reason)."""
    return {"state": state, "at": at, "words": words, "hover": hover}


def _detected(incident, device: str) -> dict:
    trig = list((incident or {}).get("triggers") or [])
    first = trig[0] if trig else {}
    try:
        epoch = float(first.get("epoch") or 0)
    except (TypeError, ValueError):
        epoch = 0.0
    if not epoch:
        why = ("its first trigger kept no time" if trig else
               "the incident's own record is not held here, and its first trigger's time is "
               "kept only there")
        return dict(_cell("none", words=f"not recorded: {why}"), epoch=None, basis="")
    seen = int((incident or {}).get("triggers_seen") or len(trig))
    basis = BASIS.get(first.get("kind"), "its first trigger was recorded")
    if seen > len(trig):
        basis += (f"; the first of the {len(trig)} triggers still kept ({seen} were seen, so "
                  "an earlier one is no longer kept)")
    return dict(_cell("at", _iso(epoch), hover=f"When {basis}, on {device}."), epoch=int(epoch),
                basis=basis)


def _fix_decision(decisions: list, act: dict) -> dict:
    """The decision an act ran, else the newest that chose a fix."""
    if act:
        for d in decisions:
            if d.get("id") == act["decision"]:
                return d
    return next((d for d in reversed(decisions) if d.get("outcome") in ("heal", "propose")),
                {})


def _decided_at(d: dict) -> str:
    if d.get("outcome") == "heal":
        return str(d.get("at") or "")
    if d.get("outcome") == "propose" and _taken_by(d).endswith(APPROVED):
        return str((d.get("taken") or {}).get("at") or "")
    return ""


def _name(actor: str) -> str:
    from modules import identity

    return identity.display_name(actor) if actor else "a person not recorded"


def _who_words(who: dict) -> str:
    """Who a fix was by, in the words its card and History use (`run_card.by_words`; the
    operator, 2026-11-12: a self-heal reads "by Mercury's self-healing · policy set by
    <display name>"): Mercury's own, under the policy its setter confirmed, or the proposal a
    person approved; nothing where the record shows neither."""
    from modules.heal import run_card

    if who["kind"] == "none":
        return "by " + run_card.by_words(who["actor"], "policy")
    if who["kind"] == "person":
        return "by " + run_card.by_words(who["actor"], "approval")
    return ""


def closed_at(incident, ran: list) -> str:
    """When the incident closed, from a record written then: the ``at`` of the record step of
    the act that closed it (its ``closed_why`` names that act's decision: the act's last step
    is "Record the outcome and close the incident", `act.STEPS`), else its store's
    ``closed_at``; "" while it is open. The act stamps its store's close with the time its job
    STARTED (`act.apply_decision`'s ``now``), so a heal verified at 20:46:18 kept a close of
    20:42:07, when it was taken (the operator's test of the incident page, 2026-11-13): that
    stamp is in The record as kept, and no screen draws it as the close."""
    inc = incident or {}
    if inc.get("state") != "closed":
        return ""
    m = _CLOSED_BY.search(str(inc.get("closed_why") or ""))
    act = next((a for a in reversed(ran) if m and a["decision"] == m.group(1)
                and a["ended_at"]), None)
    return act["ended_at"] if act else str(inc.get("closed_at") or "")


def ended_at(state: str, tl: dict, closed: str) -> str:
    """When a RESOLVED incident ended: a fixed one when its fix was verified (its Verified
    cell's time), a cancelled one when the fix was declined, a cleared one when it closed;
    "" otherwise (an open incident, or one a person still needs, has not ended)."""
    if state == "fixed":
        return tl["verified"]["at"] if tl["verified"]["state"] == "at" else ""
    if state == "cancelled":
        return tl["decided"]["at"]
    if state == "cleared":
        return closed
    return ""


def _attempts(ran: list, who: dict, kind: str) -> list:
    """One line per attempt (an act that sent something, or is running): ``{"n", "state",
    "applied", "at", "who"}``, *state* ``verified``, ``failed`` or ``running``. A failed one
    says its state alone, "verify failed": why it failed is said once, in the stage where it
    happened (the GUI review's item 6, C3454)."""
    out = []
    for a in ran:
        if not (a["sent"] or a["running"]):
            continue
        state = "running" if a["running"] else "verified" if a["passed"] else "failed"
        out.append({"n": len(out) + 1, "state": state, "applied": a["applied_at"],
                    "at": a["ended_at"], "who": _who_words(who)})
    return out


def _events(incident, entry: dict, decisions: list, ran: list, device: str) -> list:
    """Every recorded event, oldest first: ``[{"at", "words"}]``. The first `TRIGGERS_SHOWN`
    triggers and members are said one by one, the rest counted."""
    from modules.heal import incidents, said, steplog

    inc = incident or {}
    out = []

    def add(at, words):
        if at and words:
            out.append({"at": str(at), "words": words, "epoch": _epoch(at) or 0})

    trig = list(inc.get("triggers") or [])
    for t in trig[:TRIGGERS_SHOWN]:
        kind = t.get("kind")
        what = (said.symptom_words(t, device) if kind in incidents.SYMPTOM_KINDS else
                f"{device}: {incidents.KIND_WORDS.get(kind, kind or 'a trigger')}")
        at = _iso(t["epoch"]) if t.get("epoch") else t.get("at")
        add(at, what + (" (Grafana's time)" if kind == "alert" else ""))
    if len(trig) > TRIGGERS_SHOWN:
        last = trig[-1]
        add(_iso(last["epoch"]) if last.get("epoch") else last.get("at"),
            f"{len(trig) - TRIGGERS_SHOWN} more trigger(s) by this time; each is in the record")
    members = list(inc.get("attached") or [])
    for m in members[:TRIGGERS_SHOWN]:
        add(m.get("attached_at"), f"{m.get('device') or 'a device'} was attached: "
                                  f"{m.get('why') or 'no reason recorded'}")
    if len(members) > TRIGGERS_SHOWN:
        add(members[-1].get("attached_at"),
            f"{len(members) - TRIGGERS_SHOWN} more device(s) attached by this time")
    kind = entry.get("kind") or ""
    for d in decisions:
        mode = steplog.MODE_WORDS.get(d.get("mode"), d.get("mode") or "no mode recorded")
        add(d.get("at"), f"self-healing decided: {steplog.mark(d.get('outcome'), d.get('kind'))}"
                         f" ({mode})")
        by = _taken_by(d)
        if by.endswith(APPROVED):
            add((d.get("taken") or {}).get("at"),
                f"the fix was approved by {_name(by[:-len(APPROVED)])}")
        elif by.endswith(DECLINED):
            add((d.get("taken") or {}).get("at"),
                f"the fix was declined by {_name(by[:-len(DECLINED)])}")
    n = 0
    for a in ran:
        if not (a["sent"] or a["running"]):
            if a["ended_at"]:
                add(a["ended_at"], "nothing was sent")
            continue
        n += 1
        if a["applied_at"]:
            add(a["applied_at"], f"attempt {n}: applied")
        if a["ended_at"]:
            # Its outcome by its mark ("rolled back"): why is said once, in its stage (C3454).
            add(a["ended_at"], (f"attempt {n}: verified" if a["passed"] else
                                f"attempt {n}: {steplog.mark(a['outcome'], kind)}"))
    # Its close, when a record written then says (`closed_at`): the act's record step for an
    # incident its act closed, never the act's start its store stamped.
    add(closed_at(incident, ran), "the incident closed")
    out.sort(key=lambda e: e["epoch"])
    return [{"at": e["at"], "words": e["words"]} for e in out]


def timeline(incident, entry: dict, decisions: list) -> dict:
    """The header's times and what follows from them: ``{"detected", "decided", "fixed",
    "verified", "ttr", "attempts", "events", "who", "closed", "ended"}``. Each of the first
    four is a cell (`_cell`); ``ttr`` is ``{"seconds", "words", "span", "who", "hover"}``,
    *seconds* None unless a verify passed; ``closed`` when it closed (`closed_at`), ``ended``
    when a resolved one ended (`ended_at`). Every time is a record's own: nothing here reads a
    clock."""
    from modules import run_stepper
    from modules.heal import run_card

    inc = incident or {}
    device = inc.get("device") or entry.get("device") or "the device"
    ran = acts(entry)
    state = state_of(incident, entry, decisions)
    who = who_of(entry, decisions)
    tries = _attempts(ran, who if state != "fixed" else {"kind": "unknown", "actor": ""},
                      entry.get("kind") or "")
    fixed_by = next((a for a in reversed(ran) if a["passed"]), None)
    failed = next((a for a in reversed(ran) if a["sent"] and not a["passed"]
                   and not a["running"]), None)
    last = ran[-1] if ran else None
    detected = _detected(incident, device)
    chosen = _fix_decision(decisions, fixed_by or failed or last)
    at = _decided_at(chosen)
    declined = _declined(decisions)
    said_who = _who_words(who)
    if at:
        decided = _cell("at", at)
    elif state == "cancelled":
        decided = _cell("none", (declined.get("taken") or {}).get("at") or "",
                        "declined by " + _name(_taken_by(declined)[:-len(DECLINED)]))
    elif state == "cleared":
        decided = _cell("not_needed")
    else:
        decided = _cell("not_yet")
    ttr = {"seconds": None, "words": "not repaired", "span": "", "who": "", "hover": ""}
    if state == "fixed" and fixed_by:
        fixed = _cell("at", fixed_by["applied_at"]) if fixed_by["applied_at"] else _cell(
            "none", words="not recorded: its steps kept no time")
        verified = _cell("at", fixed_by["ended_at"]) if fixed_by["ended_at"] else _cell(
            "none", words="not recorded: its steps kept no time")
        end = _epoch(fixed_by["ended_at"])
        if end is None or detected["epoch"] is None:
            ttr["words"] = ("not recorded: closed before verify times were kept"
                            if end is None else "not recorded: its detected time is not kept")
        else:
            # THE one duration (`run_card.repair_seconds`), from the two times its Done stage
            # says too, drawn in the one format (`run_stepper.duration_words`). Its hover names
            # what each time is; the times themselves are the Detected and Verified cells'
            # (each the viewer's own, UTC on hover): no time is worded here.
            seconds = run_card.repair_seconds(detected["epoch"], fixed_by["ended_at"])
            ttr.update(seconds=seconds, words=f"{seconds:,} s", who=said_who,
                       span=run_stepper.duration_words(seconds) if seconds >= 60 else "",
                       hover=(f"From Detected, when {detected['basis']}, to Verified, when "
                              f"the fix's last check passed: {seconds:,} seconds. A device's "
                              "clock is never used."))
    # Each fact once (C3454): a cell holds its state's words, and why on its hover; the reason
    # itself is said where it happened (a failed verify's in its stage, a decline in Decided).
    elif failed and state == "needs_person":
        why = "its verify failed: What Mercury has done says why, in the stage it failed in"
        fixed = _cell("none", words="not fixed", hover=f"Not fixed: {why}.")
        verified = _cell("failed", failed["ended_at"], "failed")
        ttr.update(words="not repaired", hover=f"Not repaired: {why}.")
    elif state == "cancelled":
        fixed = _cell("none", words="not fixed", hover="Not fixed: the fix was declined.")
        verified = _cell("not_needed")
        ttr.update(words="not repaired", hover="Not repaired: the fix was declined.")
    elif state == "cleared":
        fixed, verified = _cell("not_needed"), _cell("not_needed")
        ttr["words"] = "cleared, no repair recorded"
    elif last and not last["sent"] and not last["running"]:
        fixed = _cell("none", words="not fixed", hover="Not fixed: nothing was sent.")
        verified = _cell("not_needed")
        ttr.update(words="not repaired", hover="Not repaired: nothing was sent.")
    else:
        fixed, verified = _cell("not_yet"), _cell("not_yet")
    closed = closed_at(incident, ran)
    out = {"detected": {k: detected[k] for k in ("state", "at", "words", "hover")},
           "decided": decided, "fixed": fixed, "verified": verified, "ttr": ttr,
           "attempts": tries, "who": who, "closed": closed,
           "events": _events(incident, entry, decisions, ran, device)}
    out["ended"] = ended_at(state, out, closed)
    return out


# ── The title ───────────────────────────────────────────────────────────────────────────────

def _happened(incident, entry: dict, decisions: list, room: int) -> str:
    """What happened, in plain words and at most *room* characters, from THE title builder
    (`said.title`; the GUI review's item 5, C3453): the newest decision's units that say a
    change ("edge-b: static route added outside Mercury"), with its cause's facts and the
    incident's triggers, else its first symptom, else what opened it. Never the configuration
    line, a mnemonic, a code key or an id: the line is What's wrong's."""
    from modules.heal import said

    inc = incident or {}
    device = inc.get("device") or entry.get("device") or "A device"
    trig = [t for t in inc.get("triggers") or [] if isinstance(t, dict)]
    newest = decisions[-1] if decisions else {}
    for d in reversed(decisions):
        units = [u for u in d.get("units") or [] if isinstance(u, dict)]
        if units:
            newest = d
            break
    units = [u for u in newest.get("units") or [] if isinstance(u, dict)]
    facts = ((newest.get("cause") or entry.get("cause") or {}).get("facts")) or []
    return (said.title(device, units, trig, facts, room=room)
            or f"{device}: an incident whose triggers are not kept")[:room]


def title(incident, entry: dict, decisions: list, state: str = "", who: dict = None) -> str:
    """The page's title, at most `said.TITLE_MAX` characters (docs/UI_RULES.md, "A title is a
    summary of at most 70 characters"; C3453), built from words (the board's part C): what
    happened (`_happened`), and once the incident is closed how it ended: ", and Mercury put
    it back" (fixed, no human), ", put back by <name>" (an approved fix), ", and it cleared".
    An action's fix (a bounce, a clear) put nothing back, so it says the fix was verified.
    The heading, the breadcrumb's last crumb and the message's lead (`heal_notice.lead`) are this
    one string."""
    from modules.heal import said, steplog

    state = state or state_of(incident, entry, decisions)
    who = who or who_of(entry, decisions)
    end = ""
    if state == "fixed":
        end = (", and Mercury's fix was verified"
               if steplog.ACTION_FAMILY.get(entry.get("kind") or "") else
               f", put back by {_name(who['actor'])}" if who["kind"] == "person" else
               ", and Mercury put it back")
    elif state == "cleared":
        end = ", and it cleared"
    # The ending is said whole or not at all: what happened gives up its room first.
    end = end if len(end) <= said.TITLE_MAX // 2 else ""
    return _happened(incident, entry, decisions, said.TITLE_MAX - len(end)) + end


# ── The page ───────────────────────────────────────────────────────────────────────────────

def _severity(state: str, decisions: list, ran: list, who: dict, resolved: bool,
              row_level: str = "") -> dict:
    """``{"words", "kind"}``: the level the incident's Needs attention card has or had, or "No
    person needed" for one that never needed a card. Derived each time (the module's
    docstring): a failed attempt by its outcome (`run_card.level_of`), a decision by
    `DECISION_LEVELS`; an incident that needs a person and has neither (a lost stream nothing
    has decided on yet) takes its own Needs attention item's level (*row_level*), and draws no
    level when that item is not held: "No person needed" is never drawn beside "Needs a
    person" (`status`)."""
    from modules.heal import run_card

    level = ""
    last = ran[-1] if ran else None
    if last and (last["sent"] or last["outcome"]) and not last["passed"] and not last["running"]:
        level = {"warn": "warning", "danger": "danger"}.get(run_card.level_of(last["outcome"]),
                                                            "danger")
    for d in decisions:
        got = DECISION_LEVELS.get(d.get("outcome") or "")
        if got and (not level or got == "danger"):
            level = got
    if not level and state == "needs_person":
        level = row_level if row_level in LEVEL_WORDS else ""
        if not level:
            return {"words": "", "kind": "muted"}
    if not level or (state == "fixed" and who["kind"] == "none"):
        return {"words": "No person needed", "kind": "muted"}
    return {"words": ("was " if resolved else "") + LEVEL_WORDS[level],
            "kind": "muted" if resolved else "danger" if level == "danger" else "warn"}


def heal_card(network: str, device: str, entry: dict):
    """The heal's card for What Mercury has done, drawn the way its device's page draws it,
    never a second stepper and never its own copy of the steps: a run (its act started,
    `run_card.acted_entry`) is the card History's Open the card reopens (`run_card.named_heal`:
    from the step log's entry, the five stages from what was seen and the decision through the
    act to its outcome; a heal job still running on the device draws its live card); a
    decision alone (a can't-fix, a proposal, a dry run) is its Needs attention row's steps
    (`run_card.steps_card`, the same five-stage stepper). ``{"state", "steps", "by"}`` (a
    run's card also says its ``level``, ``words``, ``started`` and ``finished``), or None when
    nothing ran. A read of the network's own stores and this server's jobs: no device."""
    from modules.heal import run_card

    if not entry:
        return None
    if run_card.acted_entry(entry):
        found = run_card.named_heal(network, device, entry.get("incident") or "")
        if found is not None and found[0].get("steps"):
            return found[0]
    steps = run_card.steps_card(device, entry)
    if steps is None:
        return None
    return {"state": "decision", "steps": steps, "by": run_card.by_words(*run_card.entry_by(entry))}


def drill_tag(found: dict):
    """The declared fault drill this incident is, by the tag it took at its creation
    (`fault_drills.tag_of`): on its own record, else on its step log's entry or a decision,
    which carry the incident's tag (`steplog._of`, `decide`). Keyed on that tag alone, never
    on a name or a word. None for a real incident (the operator, 2026-11-11: a drill is
    counted as a drill, never as real)."""
    from modules import fault_drills

    records = [found.get("incident"), found.get("entry")] + list(found.get("decisions") or [])
    for record in records:
        tag = fault_drills.tag_of(record)
        if tag:
            return tag
    return None


def drill_of(found: dict):
    """What the page draws of a drill (`drill_tag`): ``{"id", "hover"}``, the hover naming
    the declaration's ``fd-`` id, who declared it (by display name) and the fault it expected;
    or None for a real incident."""
    from modules import identity

    tag = drill_tag(found)
    if not tag:
        return None
    by = identity.display_name(tag["declared_by"]) if tag.get("declared_by") else \
        "a person not recorded"
    return {"id": tag["id"],
            "hover": (f"Fault drill {tag['id']}, declared by {by} before its fault was "
                      f"injected: {tag.get('expects') or 'no fault named'}. A drill's figures "
                      "are counted as a drill's, never as a real incident's.")}


#: What the page keeps of the incident's Needs attention item (`item_of`): its action, and
#: what its What to do, What's wrong and Seen before draw of it. Nothing else of the row.
_ACTION_KEYS = ("label", "open", "list", "decision", "device", "subs", "href")
_FIX_KEYS = ("device", "lead", "answers", "unseen", "seen")


def item_of(attention, incident_id: str, decisions: list, network: str, device: str) -> dict:
    """The incident's own item on Needs attention, as that list holds it now: ``{"state",
    "first", "level", "row"}``. *attention* is the list as it is drawn (`routes.v2._attention`:
    the value the background holds, masked, each run's hold marked for this request), so the
    page's action is the one its row offers, never a second reckoning of it.

    *state* is ``stands`` (a row is about this incident: it opens this page, or it carries the
    mark of one of the incident's dry-run decisions, attached to its device's drift row),
    ``none`` (the list was read and holds no such row: it cleared there, or a person
    acknowledged it) or ``reading`` (the list's first value has not landed: not known, never
    read as none). *first* is which ONE action the row offers (`attention.first_action`, the
    resolver the row's own line asks); *level* the row's; *row* what the page draws of it
    (`_ACTION_KEYS`, its devices and their networks, the likeliest cause, the run holding its
    device, its mark, Diagnose…, how it clears, and a lost stream's lead, whether it needs a
    person, whether the device answers, what Mercury cannot see and Seen before). With no row,
    *row* stands in with the incident's device alone, so the page can still open it."""
    from modules import attention as A

    a = attention or {}
    stand_in = {"id": "", "action": {}, "devices": [device] if device else [],
                "networks": {device: [network]} if device else {}}
    if (a.get("store") or {}).get("state") == "reading":
        return {"state": "reading", "first": "", "level": "", "row": stand_in}
    mine = {d.get("id") for d in decisions if d.get("id")}
    found = marked = None
    for r in [x for top in a.get("rows") or [] for x in [top] + (top.get("folded") or [])]:
        if (r.get("incident_page") or {}).get("id") == incident_id:
            found = r
            break
        mark = next((m for m in r.get("heal_marks") or [] if m.get("decision") in mine), None)
        if mark and marked is None:
            marked = dict(stand_in, id=r.get("id") or "", level=r.get("level"), heal_mark=mark,
                          clears=r.get("clears"), clears_at=r.get("clears_at"),
                          action={"label": mark.get("what") or "", "open": "heal_mark",
                                  "list": mark.get("list"), "decision": mark.get("decision"),
                                  "device": device})
    r = found or marked
    if r is None:
        return {"state": "none", "first": "", "level": "", "row": stand_in}
    act, fix, likely = r.get("action") or {}, r.get("fix") or {}, r.get("likely") or {}
    kept = {"id": r.get("id") or "",
            "action": {k: act[k] for k in _ACTION_KEYS if act.get(k) not in (None, "", [])},
            "devices": list(r.get("devices") or []),
            "networks": dict(r.get("networks") or stand_in["networks"]),
            "likely": ({k: likely.get(k) or "" for k in ("device", "at", "words")}
                       if likely else None),
            "held": r.get("held") or None, "heal_mark": r.get("heal_mark") or None,
            "diagnose": r.get("diagnose") or None,
            "clears": (r.get("clears") or {}).get("when") or "",
            "clears_at": r.get("clears_at") or "",
            "fix": {k: fix.get(k) for k in _FIX_KEYS} if fix else None}
    return {"state": "stands", "first": A.first_action(r), "level": r.get("level") or "",
            "row": kept}


def _todo(st: dict, device: str, tl: dict, fixit: dict, item: dict) -> dict:
    """What to do: ``{"words", "more", "links"}``, from the page's ONE state (`status`: *st*).
    *words* say why that state holds; *more* what the incident's Needs attention item says to
    do, in its own words (its action's label; where no item stands, that it does not, or that
    the list is still being read: absent and not read are said apart); *links* are the keys
    the template draws beside the action (``device``, ``history``, ``intent``), never the one
    the primary button already is. The action itself is the item's (`item_of`): a page that
    needs a person draws it as its one primary button, and a page that needs nobody draws
    none (resolved, or Mercury or a run a person approved is working)."""
    why, n = st["why"], (fixit.get("stop") or {}).get("n")
    row = item["row"]
    if why == "fixed":
        return {"words": "Nothing: it is fixed and verified. If it should not have been put "
                         f"back, change {device}'s intent.", "more": "", "links": ["intent"]}
    if why == "cleared":
        return {"words": "Nothing: it closed with no repair recorded. If it comes back, it "
                         "is a new incident.", "more": "", "links": ["device"]}
    if why == "cancelled":
        return {"words": f"Nothing runs: the fix was {tl['decided']['words']}. {device} "
                         "keeps what it has until a person changes it.", "more": "",
                "links": ["device", "history"]}
    if why == "healing":
        return {"words": "Nothing yet: Mercury is fixing it now. Each step is drawn under "
                         "What Mercury has done as it runs.", "more": "", "links": ["device"]}
    if why == "attempt_running":
        return {"words": f"Nothing yet: attempt {n} is running, a fix a person approved. Its "
                         "outcome is drawn under AI troubleshooting when it ends.",
                "more": "", "links": ["device"]}
    if why == "attempt_passed":
        return {"words": f"Nothing now: attempt {n} passed its verify. The incident closes "
                         "when its symptom clears.", "more": "", "links": ["device"]}
    if why == "watching":
        return {"words": "Nothing yet: Mercury is working on it. This page says what it "
                         "decided as soon as it does.", "more": "", "links": ["device"]}
    words = {
        # Its item's own words say what failed and what to do about it; with no item, here.
        "verify_failed": ("It needs a person." if item["state"] == "stands" else
                          "It needs a person. Read the stage that failed under What Mercury "
                          f"has done, then {device} itself."),
        "proposal": "It needs a person: a fix waits for a person's decision. Nothing is sent "
                    "until it is approved.",
        "decided": "It needs a person.",
        "lost_stream": f"It needs a person: the fix changes {device}'s configuration, so a "
                       f"person approves it. Until one does, {device}'s telemetry stays lost.",
        "attempt_stopped": f"It needs a person: attempt {n} did not fix it. Retry with more "
                           "information, Cancel and Hand over are under AI troubleshooting, "
                           "below.",
        "fix_proposed": "It needs a person: a fix is proposed under AI troubleshooting, below. "
                        "It runs only when a person approves it in its card.",
        "troubleshooting_cancelled": "It needs a person: troubleshooting was cancelled, and "
                                     "the incident stays open.",
        "handed_over": "It needs a person: it was handed over, and the incident stays open "
                       "until its symptom clears.",
    }[why]
    label = str((row.get("action") or {}).get("label") or "").strip()
    if item["state"] == "stands":
        more = (label[:1].upper() + label[1:] + ("" if label.endswith((".", "…")) else ".")
                if label else "")
    elif item["state"] == "reading":
        more = ("Needs attention is still being read, so the action its item offers is not "
                "known yet: this page draws it when that list has been read.")
    else:
        more = ("Its item is not on Needs attention now: it cleared there, or a person "
                f"acknowledged it. Open {device} to see how it stands.")
    # The primary button already opens the device where that is the item's action.
    links = (["history"] if item["first"] in ("device", "") else ["device", "history"])
    return {"words": words, "more": more, "links": links}


def _record(found: dict, tl: dict) -> list:
    """The record, collapsed on the page: ids, hashes, the raw times behind the header, every
    step of every run with its result, words and time, and who acted as their identity was
    recorded. ``[(name, value)]``, an empty value left out. Every time is the instant as
    recorded (ISO UTC), never worded here: the page draws each in the viewer's zone, its UTC
    on the hover (the `times` filter; C3290)."""
    from modules.nsot.deploy import config_line_count

    inc, entry, decisions = found["incident"] or {}, found["entry"], found["decisions"]
    drill = drill_tag(found)
    standing = inc.get("standing") or {}
    trig = list(inc.get("triggers") or [])
    pol = entry.get("policy") or {}
    # C3488: a decision alone (a proposal waiting, a dry-run record) has no act, so its step
    # log entry may hold neither its mode, its fix kind nor its program's hash: the newest
    # decision's own are the record's then (what its Needs attention row kept under Details
    # for the record).
    newest = decisions[-1] if decisions else {}
    lines = [
        ("Incident", found["id"]), ("Network", found["network"]),
        ("Opened (Mercury's sight)", inc.get("opened_at")),
        ("State in its store", (f"{inc.get('state')}"
                                + (f" on decision {standing.get('decision')} "
                                   f"({standing.get('outcome')}, on {standing.get('on')})"
                                   if standing else "")) if inc else ""),
        ("Closed", (f"{inc.get('closed_at')}: {inc.get('closed_why')}"
                    if inc.get("state") == "closed" else "")),
        # The store's close as kept above; an act stamps it with the time its job started, so
        # the close a screen draws is its act's record step (`closed_at`).
        ("Closed, by its act's record step",
         tl["closed"] if tl["closed"] and tl["closed"] != inc.get("closed_at") else ""),
        ("Triggers", (f"{len(trig)} of {inc.get('triggers_seen') or len(trig)} kept"
                      if inc else "")),
        ("Members", str(len(inc.get("attached") or [])) if inc else ""),
        ("Related", "; ".join(f"{r.get('incident')} ({r.get('device')}): {r.get('why')}"
                              for r in inc.get("related") or [])),
        ("Decisions", ", ".join(d.get("id") or "" for d in decisions)
         or ", ".join(entry.get("decisions") or [])),
        ("Mode", entry.get("mode") or newest.get("mode")),
        ("Fix kind", entry.get("kind") or newest.get("kind")),
        ("Tier", entry.get("tier") or newest.get("tier")),
        ("Policy", (f"{pol.get('fingerprint')} confirmed by {pol.get('by')}"
                    if pol.get("fingerprint") else "")),
        ("Fault drill", (f"{drill['id']}, declared by {drill.get('declared_by')}: "
                         f"{drill.get('expects')}, until {drill.get('until')}" if drill else "")),
        # The one count of a program's lines (`deploy.config_line_count`); every line as sent
        # is the next line's.
        ("Program", (f"{config_line_count(entry.get('program') or [])} line(s), hash "
                     f"{entry.get('program_hash')}" if entry.get("program_hash") else "")),
        ("Program hash, as decided", (newest.get("program_hash") or ""
                                      if not entry.get("program_hash") else "")),
        ("Program lines (masked)", "; ".join(entry.get("program") or [])),
        ("Golden commit", str((entry.get("records") or {}).get("golden") or "")[:12]),
        ("Approval", (entry.get("records") or {}).get("approval")),
        ("Detected", tl["detected"]["at"]),
        ("Decided" if tl["decided"]["state"] == "at" else "Declined",
         tl["decided"]["at"]),
        ("Fixed", tl["fixed"]["at"]),
        ("Verified" if tl["verified"]["state"] == "at" else "Verify failed",
         tl["verified"]["at"]),
        ("Time to repair", tl["ttr"]["words"]),
    ]
    for d in decisions:
        took = d.get("taken") or {}
        done = d.get("applied") or {}
        lines.append((f"Decision {d.get('id')}",
                      f"{d.get('outcome')} at {d.get('at')}"
                      + (f"; taken by {took.get('by')} at {took.get('at')}" if took else "")
                      + (f"; applied {done.get('outcome')} by {done.get('by')} at "
                         f"{done.get('at')}" if done else "")))
    for t in trig:
        lines.append((f"Trigger {t.get('kind')}", f"{t.get('at')}: {t.get('words')}"))
    for n, s in enumerate(entry.get("steps") or [], 1):
        if isinstance(s, dict):
            lines.append((f"{n}. {s.get('step')}",
                          f"{s.get('result')}: {s.get('words')}"
                          + (f" · {s['at']}" if s.get("at") else "")))
    return [(k, str(v)) for k, v in lines if v not in (None, "", [], {})]


def _held_attention(network: str) -> dict:
    """Needs attention's list for *network* as the background holds it (`attention_store.read`:
    never computed for this page, the page-speed rule), masked and its people named, as the
    list's own page draws it; a run's hold is the request's to mark (`routes.v2._attention`)."""
    from modules import attention_store, display_names
    from modules.outbound import mask_payload

    return display_names.people_payload(mask_payload(attention_store.read(network)))


def page(network: str, incident_id: str, attention: dict = None) -> dict:
    """What the incident's page draws (`templates/v2/incident.html`), for one id of *network*.
    ``{"kind", "id", "network", ...}``: *kind* is ``page`` (drawn in full), ``folded`` (its
    address redirects to ``into``), ``other_kind``, ``unknown`` or ``unreadable`` (said on the
    frame). Every text is masked again on the way out, and every person outside ``record`` is
    named by display name. *attention* is Needs attention's list as it is drawn for this
    request, or what gives it (its route passes `routes.v2._attention`, a run's hold marked,
    asked only for an id that has a page); None reads the held value here. Its
    state is `status`'s, the one answer every section draws; its action is its own Needs
    attention item's (`item_of`)."""
    from modules import display_names
    from modules.fixit import section
    from modules.heal import incidents, run_card, said, steplog

    found = resolve(network, incident_id)
    base = {"kind": found["found"], "id": found["id"], "network": network,
            "unreadable": list(found["unreadable"]), "kept": incidents.CLOSED_KEPT}
    if found["found"] == "folded":
        return dict(base, into=found["into"])
    if found["found"] != "page":
        return base
    inc, entry, decisions = found["incident"] or {}, found["entry"], found["decisions"]
    device = inc.get("device") or entry.get("device") or ""
    ran = acts(entry)
    tl = timeline(found["incident"], entry, decisions)
    # Resolved: nothing is left for Mercury or a person to do. An incident whose heal ended
    # without a passed verify is closed in its own store and still needs a person.
    resolved = state_of(found["incident"], entry, decisions) in RESOLVED
    # The AI troubleshooting section (board recurring-fixes v2; `modules/fixit/section.py`),
    # drawn with no AI call: a read of the incident's troubleshooting record, the operations'
    # run records, the record of AI calls and the settings. Resolved, it is read-only. Read
    # first: its state is part of the page's ONE state (`status`).
    closed = _epoch(tl["closed"]) if tl["closed"] else None
    fixit = section.drawn(network, found,
                          resolved=(closed or time.time()) if resolved else None,
                          ended=state_of(found["incident"], entry, decisions) if resolved
                          else "")
    st = status(found["incident"], entry, decisions, fixit["state"])
    state = st["state"]
    # The incident's own Needs attention item, as that list holds it: its action is the
    # page's one primary button while a person is needed, and its lost-stream lines are
    # What's wrong's (C3488). A page that needs nobody draws no action.
    item = item_of(_held_attention(network) if attention is None else
                   attention() if callable(attention) else attention,
                   found["id"], decisions, network, device)
    if not st["needs"]:
        item["first"] = ""
    elif st["why"] == "fix_proposed" and (fixit.get("proposal") or {}).get("operation"):
        # A fix proposed under AI troubleshooting is the state's action: its card is opened
        # there, with its repeat flag and its reasons, never a second card of the same
        # operation under What to do.
        item["first"] = "proposed"
    elif not item["first"] and device:
        # No control of its own (no item, or an item whose action is its words alone): the
        # device's page is where a person reads how it stands.
        item["first"] = "device"
        item["row"] = dict(item["row"], devices=[device],
                           networks=dict(item["row"].get("networks") or {},
                                         **{device: [network]}))
    newest = decisions[-1] if decisions else {}
    outcome = entry.get("outcome") or newest.get("outcome") or ""
    kind = entry.get("kind") or newest.get("kind") or ""
    sev = _severity(state, decisions, ran, tl["who"], resolved, item["level"])
    members = list(inc.get("attached") or [])
    card = heal_card(network, device, entry)
    cr = (entry.get("records") or {}).get("change_record") or {}
    # Mercury's diagnosis attached to the incident, in full (C3488: the page drew one line of
    # it, and its hypotheses only on its Needs attention row): one that ran, or, for a
    # can't-fix (the rule its row draws it by), that none has, said as the row says it.
    # An incident nothing has decided on (a lost stream a person diagnosed) has no entry to
    # carry its diagnosis: it is the step log's own row then, read here.
    from modules import attention as A
    attached = entry.get("diagnosis")
    if not attached:
        logged = steplog.diagnoses(network, incident=found["id"])
        attached = (logged["diagnoses"] or [None])[0] if logged["state"] != "unreadable" \
            else None
    diagnosis = (A.heal_diagnosis(network, dict(entry, incident=found["id"], device=device,
                                                diagnosis=attached))
                 if attached or A.is_cant_fix(outcome) else None)
    pol = entry.get("policy") or newest.get("policy") or {}
    # The configuration line is What's wrong's, never the title's (C3453): its cause's facts
    # say it where a cause is kept; a decision kept without one says it here.
    cause = said.drawn(newest.get("cause") or entry.get("cause"))
    told = " ".join(f["text"] for f in (cause or {}).get("facts") or [])
    with_units = next((d for d in reversed(decisions)
                       if any(isinstance(u, dict) for u in d.get("units") or [])), {})
    changed = said.changes_words([u for u in with_units.get("units") or []
                                  if isinstance(u, dict)])
    model = dict(
        base, title=title(found["incident"], entry, decisions, state, tl["who"]),
        state=state, state_words=st["words"],
        state_kind={"open": "info", "fixed": "ok",
                    "needs_person": "danger" if sev["kind"] == "danger" else "warn"}.get(
                        state, "muted"),
        severity=sev, device=device, resolved=resolved,
        opened=tl["detected"]["at"] or inc.get("opened_at") or entry.get("first_at") or "",
        # When it closed, and when a resolved one ended (the operator's test, 2026-11-13: a
        # fixed incident ends when its fix is verified), each from a record written then.
        closed_at=tl["closed"], ended_at=tl["ended"],
        drill=drill_of(found),
        only_log=not inc,
        header=[dict(tl[k], name=name) for k, name in (
            ("detected", "Detected"), ("decided", "Decided"), ("fixed", "Fixed"),
            ("verified", "Verified"))],
        ttr=dict(tl["ttr"], no_human=(
            f"No person took part in this incident. Self-healing applied it in Auto, under "
            f"{network}'s policy, which {_name(pol.get('by') or '')} confirmed (the policy's "
            "record). Turning Auto on was a person's decision; this fix was not."
            if tl["who"]["kind"] == "none" else "")),
        attempts=tl["attempts"], events=tl["events"],
        folded_in=[{"device": m.get("device") or "", "at": m.get("attached_at") or "",
                    "why": m.get("why") or "", "incident": m.get("from_incident") or ""}
                   for m in members if m.get("from_incident")][:MEMBERS_SHOWN],
        related=[{"incident": r.get("incident") or "", "device": r.get("device") or "",
                  "why": r.get("why") or ""} for r in inc.get("related") or []
                 if HI.match(str(r.get("incident") or ""))][:MEMBERS_SHOWN],
        wrong={"cause": cause,
               "change": (f"What changed on {device}: {changed}."
                          if changed and changed not in told else ""),
               "words": (newest.get("outcome_words") or entry.get("outcome_words")
                         or (newest.get("words") if not entry else "") or ""),
               # Said only while that IS the page's state (`status`: watching), never beside
               # "Needs a person".
               "watching": (f"Mercury is still reading {device}: it decides once its reads "
                            "agree, after the grace period."
                            if st["why"] == "watching" and not decisions and not entry
                            else "")},
        done={"mark": steplog.mark(outcome, kind) if entry else "",
              "level": ((card.get("level") if card and card.get("state") == "result" else
                         "ok" if outcome in run_card.HEALED + run_card.DECISION_GOOD
                         else run_card.level_of(outcome)) if entry else ""),
              "mode": steplog.MODE_WORDS.get(entry.get("mode"), "") if entry else "",
              # Whether its heal runs now: the live region then redraws on each step, as its
              # device's card does. Its times are the stages' own and the header's (each fact
              # once).
              "running": bool(card and card.get("state") == "running"),
              # THE stepper's five stages, as its device's card draws them (`heal_card`): who
              # it was by is said once, in the header; the outcome once, in its Done stage.
              "steps": card["steps"] if card else None,
              "change_record": bool(cr.get("state") == "made" and cr.get("markdown")),
              "diagnosis": diagnosis},
        todo=_todo(st, device, tl, fixit, item),
        evidence={"triggers": len(inc.get("triggers") or []),
                  "seen": int(inc.get("triggers_seen") or 0),
                  "reads": len(inc.get("reads") or []),
                  "members": [{"device": m.get("device") or "", "why": m.get("why") or ""}
                              for m in members[:MEMBERS_SHOWN]],
                  "more_members": max(0, len(members) - MEMBERS_SHOWN)},
        members_n=len(members))
    model = display_names.people_payload(steplog.masked(model))
    model["record"] = steplog.masked(_record(found, tl))
    # The item as its own list drew it (masked there, its people named there), and the
    # section as it draws itself (`section.drawn`): neither is worded again here.
    model["item"] = item
    model["fixit"] = fixit
    return model
