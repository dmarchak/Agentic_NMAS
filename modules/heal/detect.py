"""The detect pass: each watching incident's device read, until the grace period settles it
(board H, part H2; docs/HEAL_TO_INTENT.md section 4 step 1, and N1). It reads devices and
changes none: the read is `drift_check.check_device`, the same read and comparison as "Check
drift now" (C2336), a stitched read refused and its session closed, its result merged into the
network's stored run so the drift row says what it found.

**A pass, per network, under its heal lock** (`incidents.HealLock`: one at a time across
processes, refused by name). In it:
1. the network's mode (`policy.current`): off (or stopped everywhere) closes every watching
   incident, "nothing new starts", and reads nothing; an AUTO whose expiry passed is recorded
   once (`policy.record_expiry`);
2. each watching incident, oldest first: the grace period's judgement (`grace.judge`) on its
   reads and the outside changes its triggers hold; a read made when one is due (the first at
   once, the second at least ``heal_grace_seconds`` after the first: 120 s on a network marked
   lab, 900 s otherwise);
3. each attached member read once: it is still checked, and never healed on its own;
4. an incident the grace period settles (`grace.SETTLED_STATES`) is made ``ready``;
5. each Tier 2 proposal still waiting for a person (`decisions.proposals`) has its device read
   again once its last read is a grace period old, or a cause trigger arrived after it (C2470;
   board H artboard E): read back at intent, the proposal is withdrawn and its incident closed;
   read with another departure than the one it was bound to, it is withdrawn and its incident
   watching again, so the decision makes it again (`propose.withdraw`). Each withdrawal is
   recorded in the decisions store and the step log, with the read and the bound state.

**Where H2 ends.** A ready incident is the decision's (H3): `incidents.ready(network)` lists
them, each whole, and the decision takes one with `incidents.claim`. Nothing here classifies,
plans, guards (but the grace period) or sends.

**The runner** (`start`): one thread in the app's process, a pass over every network with a
watching or ready incident each `PASS_SECONDS`, and at once when a trigger was sighted
(`wake`); after each network's pass, the decision (`decide.run`, H3) takes what it settled,
and each heal it made is started as its own job (`act.run`, H4). After every network's pass,
the notify step (H8, `_notify_step`): each new can't-fix on any network is told about once,
with its AI analysis, by the notifier (`modules/heal_notice.py`), whose answer the runner
never reads.
An incident the decision deferred (`incidents.defer`) is not read before its time, and its
grace period restarts there.
"""

import logging
import threading
import time

log = logging.getLogger(__name__)

#: How often the runner passes: a quarter of the lab's 120 s grace period, so a second read is
#: made within 30 s of its due time.
PASS_SECONDS = 30
#: The reads one pass of one network makes; the rest wait for the next pass, said. Past
#: `heal_max_devices_drifting` (3 by default) the decision escalates anyway (guard 6), so ten
#: bound a storm's reads, not what is found.
READS_PER_PASS = 10
#: The pass's steps, in order, for the manual's How it works page (H10).
STEPS = (("mode", "Read the network's mode"),
         ("lock", "Hold the network, one pass at a time"),
         ("judge", "Judge each incident's grace period"),
         ("read", "Read the device when a read is due"),
         ("members", "Read each attached device once"),
         ("settle", "Hand each settled incident to the decision"),
         ("proposals", "Read each waiting proposal's device again, and withdraw one it no "
                       "longer fits"))

_wake = threading.Event()
_stop = threading.Event()
_thread = {"t": None}


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _check(network: str, device: str, by: str) -> dict:
    from modules import drift_check

    return drift_check.check_device(network, device, by=by)


def read_device(network: str, device: str, *, by: str, check=None, clock=time.time) -> dict:
    """One read of *device*: ``{"epoch", "at", "state", "departure", "changed_lines", "error",
    "by"}``, *state* ``drifted``, ``clean``, ``skipped``, ``error`` or ``busy`` (a drift run of
    the network held its one-run lock: not a read, made again at the next pass). Never raises.
    No configuration text is kept."""
    from modules.drift_check import DriftRunning

    check = check or _check
    try:
        got = check(network, device, by)
    except DriftRunning as exc:
        t = clock()
        return {"epoch": t, "at": _iso(t), "state": "busy", "departure": "",
                "changed_lines": None, "error": str(exc), "by": by}
    except Exception as exc:
        t = clock()
        return {"epoch": t, "at": _iso(t), "state": "error", "departure": "",
                "changed_lines": None, "error": f"{type(exc).__name__}: {exc}", "by": by}
    t = float(got.get("read_at") or clock())
    state = got.get("state")
    if got.get("skipped") or state == "skipped":
        state = "skipped"
    elif state not in ("drifted", "clean"):
        state = "error"
    return {"epoch": t, "at": _iso(t), "state": state, "departure": got.get("departure") or "",
            "changed_lines": got.get("changed_lines"),
            "error": "" if state in ("drifted", "clean") else (got.get("error") or "the read "
                                                                 "could not be made"),
            "by": by}


def outside_changes(incident: dict) -> list:
    """The receive times of the configuration-change lines from outside Mercury, or of unknown
    author, on the incident's device: each restarts its grace period."""
    from modules.heal.attribution import MERCURY

    out = [float(t.get("epoch") or 0) for t in incident.get("triggers") or []
           if t.get("kind") == "config_change"
           and (t.get("attribution") or {}).get("by") != MERCURY]
    if incident.get("defer_until"):
        # Deferred by the decision (H3): the grace period restarts when the deferral ends.
        out.append(float(incident["defer_until"]))
    return sorted(out)


def run(network: str, *, now: float = None, check=None, clock=time.time,
        by: str = "heal to intent") -> dict:
    """One detect pass of *network*: ``{"ran", "network", "mode", "words", "ready", "waiting",
    "reads", "deferred", "closed", "busy", "withdrawn"}``. *check* stands in for
    `drift_check.check_device` and *clock* for the time a read was made, in a test."""
    from modules.heal import incidents, policy

    now = clock() if now is None else float(now)
    out = {"ran": False, "network": network, "mode": "off", "words": "", "ready": [],
           "waiting": [], "reads": 0, "deferred": [], "closed": [], "busy": "",
           "withdrawn": []}
    mode = policy.current(network, now)
    out.update(mode=mode["mode"], words=mode["words"])
    if mode["mode"] == "off":
        out["closed"] = incidents.close_watching(
            network, f"self-healing is off for {network} ({mode['words']}): nothing new "
                     "starts", now)
        return out
    try:
        policy.record_expiry(network, now)
    except Exception as exc:
        log.error("heal: %s's AUTO expiry could not be recorded: %s", network, exc)
    grace_s = float(mode["guards"]["heal_grace_seconds"]["value"])
    try:
        with incidents.HealLock(network, actor="Mercury", trigger=f"the detect pass ({by})"):
            got = incidents.read(network)
            if got["state"] == "unreadable":
                return dict(out, words=got["error"])
            budget = READS_PER_PASS
            # Serial, by necessity: each read is `check_device`, which holds the network's one
            # drift-run lock across processes (`drift_check._OneRun`), so two reads of one
            # network at once refuse each other (`DriftRunning`). A pass makes at most
            # READS_PER_PASS reads; the rest wait for the next pass and are named.
            for inc in [i for i in got["incidents"] if i.get("state") == "watching"]:
                try:
                    budget = _one(network, inc, out, budget, grace_s, now, by, check, clock)
                except incidents.Refused as exc:
                    # A trigger moved the incident since this pass read it (promoted, folded,
                    # or sent back): the next pass reads it as it is now.
                    log.info("heal: %s's %s moved during the pass: %s", network, inc["id"],
                             exc)
            _proposals(network, got["incidents"], out, budget, grace_s, now, by, check, clock)
    except incidents.HealBusy as exc:
        return dict(out, busy=str(exc))
    out["ran"] = True
    if out["ready"] or out["deferred"]:
        log.info("heal: %s's detect pass: %d ready for the decision, %d waiting, %d read(s), "
                 "%d deferred to the next pass", network, len(out["ready"]),
                 len(out["waiting"]), out["reads"], len(out["deferred"]))
    return out


def _one(network, inc, out, budget, grace_s, now, by, check, clock) -> int:
    """One watching incident's step of a pass; returns the reads left."""
    from modules.heal import grace, incidents

    if float(inc.get("defer_until") or 0) > now:
        out["waiting"].append({"incident": inc["id"], "device": inc["device"],
                               "state": "deferred", "due_at": inc["defer_until"],
                               "words": (inc.get("deferred") or {}).get("why") or "deferred"})
        return budget
    reads = list(inc.get("reads") or [])
    changes = outside_changes(inc)
    j = grace.judge(reads, changes, grace_s, now)
    if j["state"] in grace.WAITING_STATES and (j["due_at"] or now) <= now:
        if budget <= 0:
            out["deferred"].append(inc["id"])
            return budget
        budget -= 1
        r = read_device(network, inc["device"], by=by, check=check, clock=clock)
        out["reads"] += 1
        if r["state"] != "busy":
            incidents.record_read(network, inc["id"], inc["device"], r)
            reads.append(r)
        j = grace.judge(reads, changes, grace_s, now)
    for m in inc.get("attached") or []:
        if m.get("reads") or budget <= 0:
            continue
        budget -= 1
        r = read_device(network, m["device"], by=by, check=check, clock=clock)
        out["reads"] += 1
        if r["state"] != "busy":
            incidents.record_read(network, inc["id"], m["device"], r)
    if j["state"] in grace.SETTLED_STATES:
        incidents.settle(network, inc["id"], j, now)
        out["ready"].append({"incident": inc["id"], "device": inc["device"],
                             "how": j["state"], "words": j["words"]})
    else:
        out["waiting"].append({"incident": inc["id"], "device": inc["device"],
                               "state": j["state"], "due_at": j["due_at"], "words": j["words"]})
    return budget


def _recheck_due(decision: dict, inc: dict, grace_s: float, now: float) -> bool:
    """Whether a waiting proposal's device is read again now: when its last read (the
    decision's own, or this step's newest since) is a grace period old, the interval that
    judges a departure persisted, or a cause trigger (a configuration change, by anyone, or
    the drift record) arrived after it."""
    from modules.heal.incidents import CAUSE_KINDS

    last = float(decision.get("epoch") or 0)
    last = max([last] + [float(r.get("epoch") or 0) for r in inc.get("reads") or []
                         if float(r.get("epoch") or 0) > last])
    if now - last >= grace_s:
        return True
    return any(t.get("kind") in CAUSE_KINDS and float(t.get("epoch") or 0) > last
               for t in inc.get("triggers") or [])


def _proposals(network, incidents_now, out, budget, grace_s, now, by, check, clock) -> int:
    """Each waiting proposal's device read again when due (C2470; board H artboard E: "If <device>
    changes, the proposal is withdrawn and made again. Clears when ... <device> is back at
    intent"): read back at intent, the proposal is withdrawn and its incident closed; read
    with a departure other than the one it was bound to, it is withdrawn and its incident
    sent back to watching, so the decision makes it again by its normal path; otherwise it
    waits, the read kept on its incident. Shares the pass's read budget; returns what is
    left."""
    from modules.heal import decisions, incidents, propose

    out.setdefault("withdrawn", [])
    try:
        waiting = decisions.proposals(network)
    except Exception as exc:
        log.error("heal: %s's proposals could not be read: %s", network, exc)
        out["proposals_error"] = str(exc)
        return budget
    claimed = {i.get("id"): i for i in incidents_now if i.get("state") == "claimed"}
    for d in waiting:
        inc = claimed.get(d.get("incident"))
        if inc is None or not _recheck_due(d, inc, grace_s, now):
            continue
        if budget <= 0:
            out["deferred"].append(inc["id"])
            continue
        budget -= 1
        r = read_device(network, d["device"], by=by, check=check, clock=clock)
        out["reads"] += 1
        if r["state"] == "busy":
            continue
        incidents.record_read(network, inc["id"], d["device"], r)
        how = propose.withdrawn_how(d, r)
        if not how:
            continue
        try:
            got = propose.withdraw(network, d, r, how=how, now=now, by=by)
        except decisions.Refused as exc:
            log.info("heal: %s's proposal %s was taken before it was withdrawn: %s", network,
                     d["id"], exc)
            continue
        out["withdrawn"].append({"decision": d["id"], "device": d["device"], "how": how,
                                 "words": got["words"]})
    if out["withdrawn"]:
        try:
            from modules import invalidation
            invalidation.announce(invalidation.ANNOUNCERS["heal-decide"], by="heal-decide")
        except Exception as exc:
            log.info("heal: %s's withdrawals recorded, not announced: %s", network, exc)
    return budget


def watching_networks() -> list:
    """The networks with an incident still watching, ready for the decision, or claimed (a
    proposal waiting is read again, C2470; one read of each network's store)."""
    from modules.heal import incidents
    from modules.integration_groups import network_names

    out = []
    for name in network_names():
        got = incidents.read(name)
        if got["state"] == "unreadable":
            log.error("heal: %s", got["error"])
            continue
        if any(i.get("state") in ("watching", "ready", "claimed") for i in got["incidents"]):
            out.append(name)
    return out


def wake() -> None:
    """A trigger was sighted: the runner passes now, not at its next interval."""
    _wake.set()


def _loop() -> None:
    while not _stop.is_set():
        try:
            names = watching_networks()
        except Exception as exc:
            log.error("heal: the networks could not be listed: %s", exc)
            names = []
        for name in names:
            if _stop.is_set():
                break
            try:
                run(name)
            except Exception as exc:
                log.error("heal: %s's detect pass failed: %s: %s", name,
                          type(exc).__name__, exc)
            try:
                # H3: each incident the pass settled is decided, under the same lock, after it.
                from modules.heal import decide
                decide.run(name)
            except Exception as exc:
                log.error("heal: %s's decision failed: %s: %s", name, type(exc).__name__, exc)
            try:
                # H4: each heal the decision made is taken once and run as its own job.
                from modules.heal import act
                act.run(name)
            except Exception as exc:
                log.error("heal: %s's heals could not start: %s: %s", name,
                          type(exc).__name__, exc)
        _notify_step()
        _wake.wait(PASS_SECONDS)
        _wake.clear()


def _notify_step() -> None:
    """Step 6, notify (section 4; board H, H8): on every network, not only those still
    watching (a heal's act ends in its own job, after its incident closed), each new can't-fix
    is told about once, in its own thread (`heal_notice.run`). The pass reads nothing back
    from it: what the notice and its analysis keep is the notifier's and the pages' alone."""
    from modules.integration_groups import network_names

    try:
        names = network_names()
    except Exception as exc:
        log.error("heal: the networks could not be listed for notices: %s", exc)
        return
    for name in names:
        try:
            from modules import heal_notice
            heal_notice.run(name)
        except Exception as exc:
            log.error("heal: %s's can't-fix notices could not start: %s: %s", name,
                      type(exc).__name__, exc)


def start() -> bool:
    """Start the runner once in this process. True when it started now."""
    t = _thread["t"]
    if t is not None and t.is_alive():
        return False
    _stop.clear()
    t = threading.Thread(target=_loop, daemon=True, name="heal-detect")
    _thread["t"] = t
    t.start()
    log.info("heal: the detect pass runs every %d s and when a trigger is sighted",
             PASS_SECONDS)
    return True


def running() -> bool:
    t = _thread["t"]
    return t is not None and t.is_alive()


def stop() -> None:
    _stop.set()
    _wake.set()
    t = _thread["t"]
    if t is not None:
        t.join(timeout=5)
