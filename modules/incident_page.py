"""One incident's page (`/v2/incident/<id>`; the incident page's board, parts B, C and F; the
operator's design change of 2026-11-11: "each incident gets its own page"). This is its first
slice: a READ-ONLY page for one self-healing incident (an ``hi-`` id), with its timeline and
its TIME TO REPAIR. A read throughout: it reads three of the network's stores and writes
nothing, creates no network and reaches no device.

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
  verify. Computed each time, never stored.
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
interrupted: `steplog.NOT_HEALED`) leaves the incident "needs a person"; its Fixed cell is
empty with its reason, its attempt reads "applied <time> · verify failed: <reason>", and its
TIME TO REPAIR reads "not repaired: verify failed".

**The five states** (`state_of`): ``open`` (Mercury is watching or working), ``needs_person``,
``fixed`` (a verified fix), ``cleared`` (closed with no fix recorded) and ``cancelled`` (a
person declined the proposed fix; the fix-it path's Cancel joins it when its controls are
built).

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
#: A level in Needs attention's own words (`templates/v2/_attention.html`, ``LEVEL_WORDS``).
LEVEL_WORDS = {"danger": "Critical", "warning": "Warning"}
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
#: Where a text drawn on the page stops; the whole of it is in the record.
TITLE_CHARS = 160
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


def span_words(seconds) -> str:
    """A length of time in words: "3 min 32 s", "3 d 19 h 50 min" (seconds are left out from
    an hour up)."""
    s = max(0, int(seconds))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = [f"{n} {unit}" for n, unit in ((d, "d"), (h, "h"), (m, "min")) if n]
    if not (d or h) and (s or not parts):
        parts.append(f"{s} s")
    return " ".join(parts)


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


def _attempts(ran: list, who: dict, kind: str) -> list:
    """One line per attempt (an act that sent something, or is running): ``{"n", "state",
    "applied", "at", "reason", "who"}``, *state* ``verified``, ``failed`` or ``running``."""
    from modules.heal import steplog

    out = []
    for a in ran:
        if not (a["sent"] or a["running"]):
            continue
        state = "running" if a["running"] else "verified" if a["passed"] else "failed"
        reason = ""
        if state == "failed":
            reason = _cut(a["words"] or steplog.mark(a["outcome"], kind), REASON_CHARS)
        out.append({"n": len(out) + 1, "state": state, "applied": a["applied_at"],
                    "at": a["ended_at"], "reason": reason, "who": _who_words(who)})
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
                add(a["ended_at"], f"nothing was sent: {_cut(a['words'], REASON_CHARS)}")
            continue
        n += 1
        if a["applied_at"]:
            add(a["applied_at"], f"attempt {n}: applied")
        if a["ended_at"]:
            why = _cut(a["words"] or steplog.mark(a["outcome"], kind), REASON_CHARS)
            add(a["ended_at"], (f"attempt {n}: verified" if a["passed"] else
                                f"attempt {n}: verify failed: {why}"))
    if inc.get("state") == "closed":
        add(inc.get("closed_at"), "the incident closed")
    out.sort(key=lambda e: e["epoch"])
    return [{"at": e["at"], "words": e["words"]} for e in out]


def timeline(incident, entry: dict, decisions: list) -> dict:
    """The header's times and what follows from them: ``{"detected", "decided", "fixed",
    "verified", "ttr", "attempts", "events", "who"}``. Each of the first four is a cell
    (`_cell`); ``ttr`` is ``{"seconds", "words", "span", "who", "hover"}``, *seconds* None
    unless a verify passed. Every time is a record's own: nothing here reads a clock."""
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
            seconds = int(end) - detected["epoch"]
            ttr.update(seconds=seconds, words=f"{seconds:,} s", who=said_who,
                       span=span_words(seconds) if seconds >= 60 else "",
                       hover=(f"From {detected['at'][:19].replace('T', ' ')} UTC, when "
                              f"{detected['basis']}, to "
                              f"{fixed_by['ended_at'][:19].replace('T', ' ')} UTC, when the "
                              f"fix's last check passed. {seconds:,} seconds. A device's "
                              "clock is never used."))
    elif failed and state == "needs_person":
        fixed = _cell("none", words="not fixed: verify failed")
        verified = _cell("failed", failed["ended_at"], "verify failed")
        ttr["words"] = "not repaired: verify failed"
    elif state == "cancelled":
        fixed = _cell("none", words="not fixed: the fix was declined")
        verified = _cell("not_needed")
        ttr["words"] = "not repaired: the fix was declined"
    elif state == "cleared":
        fixed, verified = _cell("not_needed"), _cell("not_needed")
        ttr["words"] = "cleared, no repair recorded"
    elif last and not last["sent"] and not last["running"]:
        fixed = _cell("none", words="not fixed: nothing was sent")
        verified = _cell("not_needed")
        ttr["words"] = "not repaired: nothing was sent"
    else:
        fixed, verified = _cell("not_yet"), _cell("not_yet")
    return {"detected": {k: detected[k] for k in ("state", "at", "words", "hover")},
            "decided": decided, "fixed": fixed, "verified": verified, "ttr": ttr,
            "attempts": tries, "who": who,
            "events": _events(incident, entry, decisions, ran, device)}


# ── The title ───────────────────────────────────────────────────────────────────────────────

def _happened(incident, entry: dict, decisions: list) -> str:
    """What happened, in words, never a bare id: "<device>: <what changed>" from the newest
    decision's units (`said.changes_words`, as `said.headline` leads), else the symptom its
    cause states, else "<device>: <the first trigger's words>"."""
    from modules.heal import said

    inc = incident or {}
    device = inc.get("device") or entry.get("device") or "A device"
    for d in reversed(decisions):
        units = [u for u in d.get("units") or [] if isinstance(u, dict)]
        changed = said.changes_words(units) if units else ""
        if changed:
            return f"{device}: {changed}"
        facts = (d.get("cause") or {}).get("facts") or []
        symptom = next((f.get("text") for f in facts if f.get("kind") in said.SYMPTOMS
                        and f.get("text")), "")
        if symptom:
            return symptom[:1].upper() + symptom[1:]
    trig = list(inc.get("triggers") or [])
    if trig:
        return f"{device}: {said.symptom_words(trig[0], device)}"
    head = str(entry.get("headline") or "")
    return head or f"{device}: an incident whose triggers are not kept"


def title(incident, entry: dict, decisions: list, state: str = "", who: dict = None) -> str:
    """The page's title, built from words (the board's part C): what happened, and once the
    incident is closed how it ended: ", and Mercury put it back" (fixed, no human), ", and it
    was put back by <name>" (an approved fix), ", and it cleared". An action's fix (a bounce,
    a clear) put nothing back, so it says the fix was verified."""
    from modules.heal import steplog

    state = state or state_of(incident, entry, decisions)
    who = who or who_of(entry, decisions)
    what = _cut(_happened(incident, entry, decisions), TITLE_CHARS)
    if state == "fixed":
        if steplog.ACTION_FAMILY.get(entry.get("kind") or ""):
            return f"{what}, and Mercury's fix was verified"
        if who["kind"] == "person":
            return f"{what}, and it was put back by {_name(who['actor'])}"
        return f"{what}, and Mercury put it back"
    if state == "cleared":
        return f"{what}, and it cleared"
    return what


# ── The page ───────────────────────────────────────────────────────────────────────────────

def _severity(state: str, decisions: list, ran: list, who: dict, resolved: bool) -> dict:
    """``{"words", "kind"}``: the level the incident's Needs attention card has or had, or "No
    person needed" for one that never needed a card. Derived each time (the module's
    docstring): a failed attempt by its outcome (`run_card.level_of`), a decision by
    `DECISION_LEVELS`."""
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


def _todo(state: str, device: str, tl: dict) -> dict:
    """What to do, in words, with the links it names: ``{"words", "links"}``; *links* are keys
    the template draws (``attention``, ``device``, ``history``, ``intent``). Links only: this
    slice starts nothing."""
    failed = any(a["state"] == "failed" for a in tl["attempts"])
    if state == "fixed":
        return {"words": "Nothing: it is fixed and verified. If it should not have been put "
                         f"back, change {device}'s intent.", "links": ["intent"]}
    if state == "cleared":
        return {"words": "Nothing: it closed with no repair recorded. If it comes back, it "
                         "is a new incident.", "links": ["device"]}
    if state == "cancelled":
        return {"words": f"Nothing runs: the fix was {tl['decided']['words']}. {device} "
                         "keeps what it has until a person changes it.",
                "links": ["device", "history"]}
    if state == "open":
        return {"words": "Nothing yet: Mercury is working on it. This page says what it "
                         "decided as soon as it does.", "links": ["device"]}
    if failed:
        return {"words": "A fix was applied and its verify failed. Read the failed step "
                         f"above, then {device} itself; what a person may do about it is on "
                         "Needs attention.", "links": ["attention", "history", "device"]}
    return {"words": "It needs a person. What a person may do about it is on Needs "
                     f"attention, on {device}'s item.",
            "links": ["attention", "device", "history"]}


def _record(found: dict, tl: dict) -> list:
    """The record, collapsed on the page: ids, hashes, the raw times behind the header (UTC),
    every step of every run with its result, words and time, and who acted as their identity
    was recorded. ``[(name, value)]``, an empty value left out."""
    inc, entry, decisions = found["incident"] or {}, found["entry"], found["decisions"]
    standing = inc.get("standing") or {}
    trig = list(inc.get("triggers") or [])
    pol = entry.get("policy") or {}
    lines = [
        ("Incident", found["id"]), ("Network", found["network"]),
        ("Opened (Mercury's sight)", inc.get("opened_at")),
        ("State in its store", (f"{inc.get('state')}"
                                + (f" on decision {standing.get('decision')} "
                                   f"({standing.get('outcome')}, on {standing.get('on')})"
                                   if standing else "")) if inc else ""),
        ("Closed", (f"{inc.get('closed_at')}: {inc.get('closed_why')}"
                    if inc.get("state") == "closed" else "")),
        ("Triggers", (f"{len(trig)} of {inc.get('triggers_seen') or len(trig)} kept"
                      if inc else "")),
        ("Members", str(len(inc.get("attached") or [])) if inc else ""),
        ("Related", "; ".join(f"{r.get('incident')} ({r.get('device')}): {r.get('why')}"
                              for r in inc.get("related") or [])),
        ("Decisions", ", ".join(d.get("id") or "" for d in decisions)
         or ", ".join(entry.get("decisions") or [])),
        ("Mode", entry.get("mode")), ("Fix kind", entry.get("kind")),
        ("Policy", (f"{pol.get('fingerprint')} confirmed by {pol.get('by')}"
                    if pol.get("fingerprint") else "")),
        ("Program", (f"{len(entry.get('program') or [])} line(s), hash "
                     f"{entry.get('program_hash')}" if entry.get("program_hash") else "")),
        ("Program lines (masked)", "; ".join(entry.get("program") or [])),
        ("Golden commit", str((entry.get("records") or {}).get("golden") or "")[:12]),
        ("Approval", (entry.get("records") or {}).get("approval")),
        ("Detected (UTC)", tl["detected"]["at"]),
        ("Decided (UTC)" if tl["decided"]["state"] == "at" else "Declined (UTC)",
         tl["decided"]["at"]),
        ("Fixed (UTC)", tl["fixed"]["at"]),
        ("Verified (UTC)" if tl["verified"]["state"] == "at" else "Verify failed (UTC)",
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


def page(network: str, incident_id: str) -> dict:
    """What the incident's page draws (`templates/v2/incident.html`), for one id of *network*.
    ``{"kind", "id", "network", ...}``: *kind* is ``page`` (drawn in full), ``folded`` (its
    address redirects to ``into``), ``other_kind``, ``unknown`` or ``unreadable`` (said on the
    frame). Every text is masked again on the way out, and every person outside ``record`` is
    named by display name."""
    from modules import display_names
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
    state = state_of(found["incident"], entry, decisions)
    # Resolved: nothing is left for Mercury or a person to do. An incident whose heal ended
    # without a passed verify is closed in its own store and still needs a person.
    resolved = state in ("fixed", "cleared", "cancelled")
    newest = decisions[-1] if decisions else {}
    outcome = entry.get("outcome") or newest.get("outcome") or ""
    kind = entry.get("kind") or newest.get("kind") or ""
    sev = _severity(state, decisions, ran, tl["who"], resolved)
    members = list(inc.get("attached") or [])
    card = heal_card(network, device, entry)
    cr = (entry.get("records") or {}).get("change_record") or {}
    diagnosis = entry.get("diagnosis") or {}
    pol = entry.get("policy") or newest.get("policy") or {}
    model = dict(
        base, title=title(found["incident"], entry, decisions, state, tl["who"]),
        state=state, state_words=STATE_WORDS[state],
        state_kind={"open": "info", "fixed": "ok",
                    "needs_person": "danger" if sev["kind"] == "danger" else "warn"}.get(
                        state, "muted"),
        severity=sev, device=device, resolved=resolved,
        opened=tl["detected"]["at"] or inc.get("opened_at") or entry.get("first_at") or "",
        closed_at=(inc.get("closed_at") if inc.get("state") == "closed" else "") or "",
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
        wrong={"cause": said.drawn(newest.get("cause") or entry.get("cause")),
               "words": (newest.get("outcome_words") or entry.get("outcome_words")
                         or (newest.get("words") if not entry else "") or ""),
               "watching": (f"Mercury is still reading {device}: it decides once its reads "
                            "agree, after the grace period."
                            if not decisions and not entry else "")},
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
              "diagnosis": ({"words": diagnosis.get("runbook_words") or "a runbook",
                             "at": diagnosis.get("finished_at") or "",
                             "hypotheses": len(diagnosis.get("hypotheses") or [])}
                            if diagnosis else None)},
        todo=_todo(state, device, tl),
        ai={"spent": bool(found["advisories"]),
            "advisories": [{"at": a.get("at") or "", "words": a.get("words") or ""}
                           for a in found["advisories"][-1:]]},
        evidence={"triggers": len(inc.get("triggers") or []),
                  "seen": int(inc.get("triggers_seen") or 0),
                  "reads": len(inc.get("reads") or []),
                  "members": [{"device": m.get("device") or "", "why": m.get("why") or ""}
                              for m in members[:MEMBERS_SHOWN]],
                  "more_members": max(0, len(members) - MEMBERS_SHOWN)},
        members_n=len(members))
    model = display_names.people_payload(steplog.masked(model))
    model["record"] = steplog.masked(_record(found, tl))
    return model
