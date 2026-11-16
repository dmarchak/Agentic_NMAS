"""The detect pass: each watching incident's device read, until the grace period settles it
(board H, part H2; docs/HEAL_TO_INTENT.md section 4 step 1, and N1). It reads devices and
changes none: the read is `drift_check.check_device`, the same read and comparison as "Check
drift now" (C2336), a stitched read refused and its session closed, its result merged into the
network's stored run so the drift row says what it found.

**A pass, per network, under its heal lock** (`incidents.HealLock`: one at a time across
processes, refused by name). In it:
1. the network's mode (`policy.current`): off (or stopped everywhere) closes every watching
   or standing incident, "nothing new starts", and reads nothing; an AUTO whose expiry passed
   is recorded once (`policy.record_expiry`);
2. each watching incident, oldest first: the grace period's judgement (`grace.judge`) on its
   reads and the outside changes its triggers hold; a read made when one is due (the first at
   once, the second at least ``heal_grace_seconds`` after the first: 120 s on a network marked
   lab, 900 s otherwise);
3. each attached member read once: it is still checked, and never healed on its own;
4. an incident the grace period settles (`grace.SETTLED_STATES`) is made ``ready``; one sent
   back from standing (C2813) that settled on THE departure its decision judged stands on that
   decision again (`incidents.restand`), never a second decision of it;
5. each Tier 2 proposal still waiting for a person (`decisions.proposals`) has its device read
   again once its last read is a grace period old, or a cause trigger arrived after it (C2470;
   board H artboard E): read back at intent, the proposal is withdrawn and its incident closed;
   read with another departure than the one it was bound to, it is withdrawn and its incident
   watching again, so the decision makes it again (`propose.withdraw`). Each withdrawal is
   recorded in the decisions store and the step log, with the read and the bound state;
6. each incident standing at its golden on a symptom (a Tier 3 can't-fix; C2813, C2825) has
   its symptoms read from their stores, no device: every one gone, and nothing logged for the
   flap window since its last trigger, ends it as cleared by itself (`_standing`); before that,
   one whose approved fix passed its own device check ends as fixed, its alerts read no more
   (`_fixed`, the operator's item 4, 2026-11-15).

**Where H2 ends.** A ready incident is the decision's (H3): `incidents.ready(network)` lists
them, each whole, and the decision takes one with `incidents.claim`. Nothing here classifies,
plans, guards (but the grace period) or sends.

**The runner** (`start`): one thread in the app's process, a pass over every network with a
watching or ready incident each `PASS_SECONDS`, and at once when a trigger was sighted
(`wake`); after each network's pass, the decision (`decide.run`, H3) takes what it settled,
each proposal it made is diagnosed once in its own thread (`auto_diagnose.proposals_step`,
H17), and each heal it made is started as its own job (`act.run`, H4). After every network's pass,
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
         ("settle", "Hand each settled incident to the decision, or stand it on its decision "
                    "again when it read the departure that decision judged"),
         ("proposals", "Read each waiting proposal's device again, and withdraw one it no "
                       "longer fits"),
         ("standing", "End each standing can't-fix whose approved fix passed its own device "
                      "check; read the others' symptoms from their stores, and end one that "
                      "cleared by itself"))

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
        by: str = "heal to intent", symptom=None) -> dict:
    """One detect pass of *network*: ``{"ran", "network", "mode", "words", "ready", "waiting",
    "reads", "deferred", "closed", "busy", "withdrawn", "stood", "cleared", "fixed"}``. *check*
    stands in for `drift_check.check_device`, *clock* for the time a read was made, and *symptom* for
    `decide.Sources.symptom_now` (``(device, triggers) -> state``), in a test."""
    from modules.heal import incidents, policy

    now = clock() if now is None else float(now)
    out = {"ran": False, "network": network, "mode": "off", "words": "", "ready": [],
           "waiting": [], "reads": 0, "deferred": [], "closed": [], "busy": "",
           "withdrawn": [], "stood": [], "cleared": [], "fixed": []}
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
            _standing(network, got["incidents"], out, mode, now, by, symptom)
    except incidents.HealBusy as exc:
        return dict(out, busy=str(exc))
    out["ran"] = True
    if out["ready"] or out["deferred"]:
        log.info("heal: %s's detect pass: %d ready for the decision, %d waiting, %d read(s), "
                 "%d deferred to the next pass", network, len(out["ready"]),
                 len(out["waiting"]), out["reads"], len(out["deferred"]))
    return out


#: The guards whose time-based deferral the operator retired (2026-11-16: "Remove all time-based
#: holds from self-healing"): one already recorded on an open incident is lifted at the next
#: pass. A deferral recorded before deferrals named their guard is told by its words.
RETIRED_HOLDS = (5, 7, 8, 9, 10, 11)
RETIRED_WORDS = ("-minute topology hold", "a person appears to be working",
                 # The flap-window quiet (C2825), retired with them.
                 "every symptom the incident named reads gone now")


def _hold_lifted(network: str, inc: dict, now: float) -> bool:
    """Whether *inc*'s deferral was one of the retired time-based holds (`RETIRED_HOLDS`, or
    their words), so it ends now; planned work (guard 3) and a read that could not be made keep
    theirs."""
    del network, now                              # kept for its callers; nothing is read
    d = inc.get("deferred") or {}
    why = str(d.get("why") or "")
    return bool(d.get("guard") in RETIRED_HOLDS or any(w in why for w in RETIRED_WORDS))


def _outside(inc: dict) -> list:
    """*inc*'s configuration-change triggers from outside Mercury (or of unknown author)."""
    from modules.heal.attribution import MERCURY

    return [t for t in inc.get("triggers") or [] if isinstance(t, dict)
            and t.get("kind") == "config_change"
            and (t.get("attribution") or {}).get("by") != MERCURY]


def _from_outside(inc: dict) -> bool:
    return bool(_outside(inc))


def _change_person(inc: dict) -> dict:
    """The person the newest outside change's CONFIG_I line names (`attribution.person_of`'s
    ``user``), or ``{}``: only a named person's change has a grace (the operator, 2026-11-16)."""
    got = _outside(inc)
    person = (got[-1].get("person") or {}) if got else {}
    return person if person.get("user") else {}


def _pressed(network: str, inc: dict) -> str:
    """Whether a person answered the grace since it started: ``kept`` (the device's intent
    committed after the change: its Edit intent), ``put_back`` (a deploy receipt of the device
    after it: its Deploy plan), else ``""``. Reads the repository's log and the receipts."""
    from modules.nsot import listref, receipts, repo

    g = inc.get("grace") or {}
    since = float(g.get("change_epoch") or 0)
    if not since:
        return ""
    device = inc.get("device") or ""
    try:
        rel = f"host_vars/{device}.yml"
        got = repo.run_git(listref.resolve(network).repo_dir, "log", "-1", "--format=%ct",
                           "--", rel)
        if got.returncode == 0 and got.stdout.strip() and float(got.stdout.strip()) > since:
            return "kept"
        rows = receipts.read(network, device, limit=5).get("rows") or []
        if any(_epoch_of(r.get("completed_at") or r.get("at")) > since for r in rows):
            return "put_back"
    except Exception as exc:                          # noqa: BLE001 (the grace runs on, said)
        log.error("heal: whether %s's change was answered could not be read: %s",
                  inc.get("id"), exc)
    return ""


def _epoch_of(iso) -> float:
    import calendar

    try:
        return float(calendar.timegm(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (TypeError, ValueError):
        return 0.0


def _grace_started(network: str, inc: dict, person: dict, j: dict, reads: list,
                   now: float) -> None:
    """Keep the grace on *inc* and tell its person once (`heal_notice.grace_notice`): the
    window's end is the existing grace's (`grace.judge`'s ``due_at``), no new timer."""
    from modules import heal_notice
    from modules.heal import incidents

    change = max(outside_changes(dict(inc, defer_until=None)) or [0.0])
    g = inc.get("grace") or {}
    if g.get("change_epoch") == change and g.get("told"):
        return
    lines = next((r.get("changed_lines") for r in reversed(reads)
                  if r.get("state") == "drifted"), None)
    g = {"person": person.get("words") or person.get("user"), "user": person.get("user"),
         "change_epoch": change, "until": _iso(float(j.get("due_at") or now)),
         "lines": lines, "told": False}
    try:
        g["told"] = bool(heal_notice.grace_notice(network, inc, g).get("sent") is not None)
    except Exception as exc:                          # noqa: BLE001 (the grace runs, said)
        log.error("heal: %s's person could not be told: %s", inc.get("id"), exc)
    incidents.record_grace(network, inc["id"], g)


def _port_only(inc: dict, c: dict) -> bool:
    """Whether *inc*'s triggers are only port events: its err-disable lines and Grafana alerts,
    each alert naming no port or the classified one (`errdisable.same_port`)."""
    from modules.heal import errdisable

    trig = [t for t in inc.get("triggers") or [] if isinstance(t, dict)]
    if not trig or any(t.get("kind") not in errdisable.PORT_TRIGGERS for t in trig):
        return False
    port = c.get("port") or ""
    return all(not t.get("interface") or not port or errdisable.same_port(t["interface"], port)
               for t in trig if t.get("kind") == "alert")


def _settle_port(network, inc, out, budget, now, by):
    """A port event settles on its classification's device read, never on the configuration's
    grace (the operator, 2026-11-16): err-disabled as classified, ready for the decision at
    once (``confirmed``); not err-disabled, closed at once as "No problem found", its read
    named. Returns the reads left, or None when *inc* is no port event to judge so (its
    configuration read and grace, as before)."""
    from modules.heal import errdisable, incidents

    c = errdisable.of_record(inc)
    if not _port_only(inc, c):
        return None
    if errdisable._due(inc, now) and budget > 0:
        budget -= 1
        out["reads"] += 1
        c = errdisable.reclassify(network, inc, now=now)
        incidents.record_problem(network, inc["id"], errdisable.FIELD, c)
    found = _port_found(c)
    if found is None:
        if c.get("state") == "classified" and (c.get("confirmed") or {}).get("unread"):
            out["waiting"].append({"incident": inc["id"], "device": inc["device"],
                                   "state": "need_read", "due_at": None,
                                   "words": c["confirmed"].get("why") or "the port is read again"})
            return budget
        return None                               # not a classified err-disable: as before
    conf = c.get("confirmed") or {}
    if found is False:
        d = _no_problem(network, inc, c, now, by, watching=True)
        if d:
            out["cleared"].append({"incident": inc["id"], "device": inc["device"],
                                   "decision": d["id"]})
        return budget
    words = (f"{errdisable.CONFIRM_READ} on {inc['device']} at {conf.get('at') or '?'}: "
             f"{(conf.get('found') or {}).get('port') or c.get('port')} err-disabled by "
             f"{(conf.get('found') or {}).get('reason') or c.get('cause')}, as classified")
    incidents.settle(network, inc["id"], {"state": "confirmed", "words": words,
                                          "operands": {"port": c.get("port"),
                                                       "run": conf.get("run") or ""}}, now)
    out["ready"].append({"incident": inc["id"], "device": inc["device"], "how": "confirmed",
                         "words": words})
    return budget


def _one(network, inc, out, budget, grace_s, now, by, check, clock) -> int:
    """One watching incident's step of a pass; returns the reads left."""
    from modules.heal import decide, grace, incidents

    if float(inc.get("defer_until") or 0) > now and _hold_lifted(network, inc, now):
        # Its hold no longer holds: the deferral ends now, and the grace restarts now.
        incidents.lift(network, inc["id"], now)
        inc = dict(inc, defer_until=now)
    if float(inc.get("defer_until") or 0) > now:
        out["waiting"].append({"incident": inc["id"], "device": inc["device"],
                               "state": "deferred", "due_at": inc["defer_until"],
                               "words": (inc.get("deferred") or {}).get("why") or "deferred"})
        return budget
    port = _settle_port(network, inc, out, budget, now, by)
    if port is not None:
        return port
    reads = list(inc.get("reads") or [])
    changes = outside_changes(inc)
    # The operator, 2026-11-16: the grace is a named person's decision, not a silent timer;
    # none for an unattributed change or an event. Either of that person's presses ends it.
    person = _change_person(inc)
    pressed = _pressed(network, inc) if person else ""
    if pressed == "kept":
        g = inc.get("grace") or {}
        d = decide.end_standing(
            network, inc["id"], f"kept: {person.get('words') or 'the person'}'s change on "
                                f"{inc['device']} was adopted into intent",
            now=now, by=by, also_watching=True,
            read_words=(f"host_vars/{inc['device']}.yml committed after the change at "
                        f"{_iso(float(g.get('change_epoch') or 0))}"))
        if d:
            out["cleared"].append({"incident": inc["id"], "device": inc["device"],
                                   "decision": d["id"]})
        return budget
    once = ("put back now by a person's press" if pressed == "put_back" else "" if person
            else "the change names no person" if _from_outside(inc)
            else "an event, not a configuration change")
    j = grace.judge(reads, changes, grace_s, now, once=once)
    if j["state"] in grace.WAITING_STATES and ((j["due_at"] or now) <= now or pressed):
        if budget <= 0:
            out["deferred"].append(inc["id"])
            return budget
        budget -= 1
        r = read_device(network, inc["device"], by=by, check=check, clock=clock)
        out["reads"] += 1
        if r["state"] != "busy":
            incidents.record_read(network, inc["id"], inc["device"], r)
            reads.append(r)
        j = grace.judge(reads, changes, grace_s, now, once=once)
    if person and j["state"] == "waiting" and not pressed:
        _grace_started(network, inc, person, j, reads, now)
    for m in inc.get("attached") or []:
        if m.get("reads") or budget <= 0:
            continue
        budget -= 1
        r = read_device(network, m["device"], by=by, check=check, clock=clock)
        out["reads"] += 1
        if r["state"] != "busy":
            incidents.record_read(network, inc["id"], m["device"], r)
    stood = inc.get("stood") or {}
    if (j["state"] == "persisted" and stood.get("departure")
            and (j.get("operands") or {}).get("departure") == stood["departure"]):
        # C2813: sent back from standing by a change, and read again with THE departure its
        # decision judged: it stands on that decision again, never a second decision of it.
        incidents.restand(network, inc["id"], j, now)
        out.setdefault("stood", []).append({"incident": inc["id"], "device": inc["device"],
                                            "decision": stood.get("decision") or "",
                                            "words": j["words"]})
    elif j["state"] in grace.SETTLED_STATES:
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


def _standing(network, incidents_now, out, mode, now, by, symptom=None) -> None:
    """Each incident standing on a decision at its golden with a symptom (a Tier 3 can't-fix,
    ``on: symptom``; C2813, C2825) has its symptoms read from their stores (no device: the
    readers' stored values, `decide.Sources.symptom_now`, verify's rule): every one read gone
    ends it at once as cleared by itself (`decide.end_standing`; the operator, 2026-11-16: "an
    incident whose device read finds no problem closes at once on that read, never on a quiet
    timer"), so its can't-fix item leaves and nothing later folds into it. A port problem is
    judged on its classification's device read instead (`_port_clear`). A symptom present,
    stale or unreadable leaves it standing: an unread symptom is not gone."""
    from modules.heal import decide

    del mode                                      # no quiet window: nothing here waits
    read = symptom or decide.Sources(network).symptom_now
    out.setdefault("fixed", [])
    for inc in incidents_now:
        if inc.get("state") != "standing" or (inc.get("standing") or {}).get("on") != "symptom":
            continue
        trig = decide.judged_triggers(inc)
        if _fixed(network, inc, trig, out, now, by):
            continue
        port = _port_clear(network, inc, out, now, by)
        if port is not None:
            continue                              # judged on its device read
        try:
            state = read(inc["device"], trig)
        except Exception as exc:                      # said; it stands, read at the next pass
            log.error("heal: %s's %s: its symptoms could not be read: %s", network, inc["id"],
                      exc)
            continue
        if state != "gone":
            continue
        d = decide.end_standing(
            network, inc["id"],
            (f"nothing to heal: every symptom the incident named has cleared by itself at "
             f"{decide._hhmm(now)} UTC, nothing to do: {inc['device']} is at its golden"),
            now=now, by=by,
            read_words=f"every symptom {inc['id']} named read again from its store: gone")
        if d:
            out["cleared"].append({"incident": inc["id"], "device": inc["device"],
                                   "decision": d["id"]})


def _port_found(c: dict):
    """What the classification's newest device read (`errdisable.confirm`) says of its port:
    ``True`` err-disabled as classified, ``False`` not listed (no problem), ``None`` unread,
    disagreeing or not classified (judged as before)."""
    conf = (c or {}).get("confirmed") or {}
    if c.get("state") != "classified" or not conf or conf.get("unread"):
        return None
    if conf.get("agrees"):
        return True
    return False if not conf.get("found") else None


def _no_problem(network, inc, c, now, by, *, watching: bool) -> dict:
    """Close *inc* at once on its device read finding the port not err-disabled (the operator,
    2026-11-16), through `decide.end_standing`, the read named."""
    from modules.heal import decide, errdisable

    conf = c.get("confirmed") or {}
    port = c.get("short") or c.get("port") or "its port"
    return decide.end_standing(
        network, inc["id"],
        f"No problem found: {inc['device']}'s {port} is not err-disabled",
        now=now, by=by, also_watching=watching,
        read_words=(f"{errdisable.CONFIRM_READ} on {inc['device']} at {conf.get('at') or '?'} "
                    f"does not list {port} (run {conf.get('run') or 'not recorded'})"))


def _port_clear(network, inc, out, now, by):
    """A standing port problem (`errdisable`) judged on its device read: not err-disabled
    closes it at once; still err-disabled leaves it standing. None when it is no classified
    port problem, so its symptoms are read as before."""
    from modules.heal import errdisable

    c = errdisable.of_record(inc)
    found = _port_found(c)
    if found is None:
        return None
    if found is False:
        d = _no_problem(network, inc, c, now, by, watching=False)
        if d:
            out["cleared"].append({"incident": inc["id"], "device": inc["device"],
                                   "decision": d["id"]})
    return found


def _fixed(network, inc, trig, out, now, by) -> bool:
    """The operator's item 4 (2026-11-15: "an incident closes on the problem's own verification
    (the run's direct device check), not on an alert clearing"): a standing incident whose fix
    a person approved and ran PASSED its own device check (`verified_fix`), with no trigger
    since that check, is ended now through `decide.end_standing` (the one close of a standing
    incident), whatever its alerts still say. Whether such an alert clears after it is its own
    finding (`attention._heal_alert_after_fix_rows`). True when it was ended; a fix that cannot
    be read leaves it standing, said in the log."""
    from modules.heal import decide

    try:
        fix = verified_fix(network, inc)
    except Exception as exc:                          # said; it stands, read at the next pass
        log.error("heal: %s's %s: whether its fix verified could not be read: %s: %s",
                  network, inc["id"], type(exc).__name__, exc)
        return False
    if not fix or any(float(t.get("epoch") or 0) > fix["epoch"] for t in trig):
        # A trigger after the fix's check (an err-disable again, a re-fired alert) is the
        # problem back, not the fix's: the incident stands on it.
        return False
    when = time.strftime("%H:%M", time.gmtime(fix["epoch"]))
    d = decide.end_standing(
        network, inc["id"],
        (f"fixed: the plan's run {fix['run'][-8:] or '?'} verified on {fix['device']} at "
         f"{when} UTC (attempt {fix['attempt']}, {fix['operation']}): the incident closes on "
         "its fix's own device check, not on its alerts clearing"),
        now=now, by=by,
        read_words=(f"{inc['id']}'s attempt {fix['attempt']} (run {fix['run']}) passed its "
                    f"verify on {fix['device']} at {fix['at']}, its troubleshooting record's "
                    "newest step"),
        fixed=fix)
    if d:
        out["fixed"].append({"incident": inc["id"], "device": inc["device"],
                             "decision": d["id"], "run": fix["run"]})
    return bool(d)


def verified_fix(network: str, inc: dict) -> dict:
    """The fix a person approved and ran in incident *inc* that passed its own device check:
    ``{"run", "attempt", "operation", "device", "epoch", "at"}`` (*epoch* and *at* when its run
    finished, after its verify), or ``{}``. Passed as its page says it: the troubleshooting
    section's state ``passed`` (`fixit.section.view`, which the incident page reads as
    ``attempt_passed``), its newest attempt's own run record ``done`` (`fixit.incident.passed`:
    the state a command plan's run writes when its verify passed). Read only for an incident
    with a troubleshooting record, and only once its newest attempt passed, so the section is
    read for the rare case alone. ``{}`` when the attempts are incomplete (an attempt not read
    is never read as passed)."""
    from modules import incident_page, incidents_list
    from modules.fixit import incident as F
    from modules.fixit import section

    if inc.get("id") not in incidents_list._fixit_ids(network):
        return {}
    found = incident_page.resolve(network, inc["id"])
    if found["found"] != "page":
        return {}
    fi = section.incident_of(network, found)["incident"]
    if fi is None:
        return {}
    tried = F.attempts(fi)
    last = tried["attempts"][-1] if tried["attempts"] else None
    if (tried["state"] != "ok" or not last or not last["passed"]
            or last["finished_at"] is None):
        return {}
    if section.view(network, found).get("state") != "passed":
        return {}
    return {"run": last["run"], "attempt": last["n"], "operation": last["operation"],
            "device": last["device"] or inc.get("device") or "",
            "epoch": float(last["finished_at"]), "at": _iso(float(last["finished_at"]))}


def watching_networks() -> list:
    """The networks with an incident still watching, ready for the decision, or claimed (a
    proposal waiting is read again, C2470), or standing at its golden on a symptom (read again
    from its stores, C2825); one read of each network's store."""
    from modules.heal import incidents
    from modules.integration_groups import network_names

    out = []
    for name in network_names():
        got = incidents.read(name)
        if got["state"] == "unreadable":
            log.error("heal: %s", got["error"])
            continue
        if any(i.get("state") in ("watching", "ready", "claimed")
               or (i.get("state") == "standing"
                   and (i.get("standing") or {}).get("on") == "symptom")
               for i in got["incidents"]):
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
                # R4 and G7 (C3712): each open incident's own evidence classified into its
                # problem (an err-disabled port), the standing ones included, never re-injected.
                from modules.heal import errdisable
                errdisable.reclassify_step(name)
            except Exception as exc:
                log.error("heal: %s's incidents could not be classified: %s: %s", name,
                          type(exc).__name__, exc)
            try:
                # H3: each incident the pass settled is decided, under the same lock, after it.
                from modules.heal import decide
                decide.run(name)
            except Exception as exc:
                log.error("heal: %s's decision failed: %s: %s", name, type(exc).__name__, exc)
            try:
                # H17 (N14): each proposal waiting for a person is diagnosed once, in its own
                # thread, so its card draws Mercury's diagnosis beside Approve….
                from modules.heal import auto_diagnose
                auto_diagnose.proposals_step(name)
            except Exception as exc:
                log.error("heal: %s's proposals could not be diagnosed: %s: %s", name,
                          type(exc).__name__, exc)
            try:
                # H4: each heal the decision made is taken once and run as its own job.
                from modules.heal import act
                act.run(name)
            except Exception as exc:
                log.error("heal: %s's heals could not start: %s: %s", name,
                          type(exc).__name__, exc)
        _retry_step()
        _notify_step()
        _wake.wait(PASS_SECONDS)
        _wake.clear()


def _retry_step() -> None:
    """The daily retry (the operator, 2026-11-16): on every network each pass, not only those
    still watching (a standing can't-fix or hold is not), `retry.daily` asks whether an
    incident whose fixes failed was last tried 24 hours ago or more, from its recorded retry,
    and tries it again once. The retry is taken under the incidents store's lock, so another
    worker's pass or a restart never takes it twice. Never raises."""
    from modules.integration_groups import network_names

    try:
        names = network_names()
    except Exception as exc:
        log.error("heal: the networks could not be listed for the daily retry: %s", exc)
        return
    for name in names:
        try:
            from modules.heal import retry
            retry.daily(name)
        except Exception as exc:
            log.error("heal: %s's daily retry failed: %s: %s", name, type(exc).__name__, exc)


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
        # The fight finding's notice (the operator, 2026-11-16): once per fight; never raises.
        from modules.heal import findings
        findings.notify_fights(name)


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
