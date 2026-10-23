"""What is running on the devices now, and what finished recently: one read for every screen
that draws it (every v2 page's In progress chip through `/operations/in_flight`, and Settings ›
Installation › Diagnostics, board F4, for every network at once; today's in-flight panel left
with today's index at 7.8, 2026-10-17, P7-27).

Register C99: a restore ran for fifty seconds with nothing on screen, the operator concluded it
had staged something, started a deploy of the same device, and the silence produced a second
change. C98's per-device lock already records who holds each device, since when, and its last
progress step, across processes (the CLIs included). Operations that FINISHED in the last half
hour come from their receipts, so a reload in the middle of one no longer loses its result.

A READ: it lists lock files and reads the receipt logs; it writes nothing.
"""

import calendar
import logging
import time

log = logging.getLogger(__name__)

#: How far back "finished recently" reaches. Long enough to outlive a reload and a coffee;
#: short enough that the panel is about now.
RECENT_SECONDS = 1800
NOT_RECORDED = ("A capture writes no receipt: its golden commit is its record, on the Git "
                "tab.")


def recent(list_name: str, now: float) -> tuple:
    """``(rows, state)`` from *list_name*'s receipts: deploy and restore, per device, newest
    first, inside RECENT_SECONDS. A capture writes no receipt (its commit is its record)."""
    from modules.nsot import receipts

    got = receipts.read(list_name, limit=100)
    if got["state"] != "ok":
        return [], got["state"]
    rows = []
    for r in got["rows"]:
        try:
            at = calendar.timegm(time.strptime(r.get("at", ""), "%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, OverflowError):
            continue
        if now - at > RECENT_SECONDS:
            break                                   # newest first
        rows.append({"device": r.get("device", ""), "action": r.get("action", ""),
                     "outcome": r.get("outcome", ""), "at": r.get("at", ""),
                     "actor": r.get("actor", ""), "reason": r.get("reason", ""),
                     "commit_state": r.get("commit_state", "")})
    return rows, "ok"


def read(list_name: str, now: float = None) -> dict:
    """*list_name*'s held devices and running operations, and its recent receipts:
    ``{"running", "recent", "recent_state"}``. An operation that holds no device (a NetBox
    preview or import) is running too, in the same row shape. Raises on an unreadable lock
    folder (`device_ops.HoldsUnreadable`, C988; an absent one is nothing held): the caller
    says it."""
    from modules import op_progress
    from modules.nsot import device_ops

    from modules.nsot import capture_job

    now = time.time() if now is None else now
    running = merge([dict(r, list=list_name) for r in device_ops.in_flight(list_name, now)],
                    op_progress.running(now), capture_job.card_jobs(now))
    rows, state = recent(list_name, now)
    return {"running": running, "recent": rows, "recent_state": state}


def merge(holds: list, ops: list, jobs: list) -> list:
    """One operation, one row (C217: a rotation on r2 drew its device's hold, "now:
    persisting", true, AND its job's own row, "starting … may be stuck", false, because the
    job registry never moves its step). A job a device's page started (`capture_job`'s *jobs*,
    each with its list and device) that holds its device is drawn ONCE, as the hold's row,
    which carries the device's real step, with the job's id and card on it; its job row goes.
    One that has not taken its hold yet is drawn as its device's row, in the hold's words, and
    never "may be stuck": its job is running, which is the only liveness it has (the job row's
    step never moves). Every other row is kept as it is. Each hold row carries its ``list``."""
    from modules.nsot.device_ops import OPERATION_WORDS

    held = {(h.get("list", ""), h.get("device", "")): h for h in holds}
    by_id = {j["job"]: j for j in jobs if j.get("state") == "running"}
    out = [dict(h) for h in holds]
    index = {(h.get("list", ""), h.get("device", "")): i for i, h in enumerate(out)}
    rest = []
    for op in ops:
        job = by_id.get(op.get("id"))
        key = (job["list"], job["device"]) if job else None
        if key in held:
            out[index[key]].update(job=job["job"], card=job["card"])
        elif job:
            rest.append(dict(op, device=job["device"], list=job["list"], operation=job["card"],
                             words=OPERATION_WORDS.get(job["card"], job["card"]),
                             job=job["job"], card=job["card"], stalled=False,
                             text=f"{job['device']} is being "
                                  f"{OPERATION_WORDS.get(job['card'], job['card'])} by "
                                  f"{op.get('actor') or 'unknown'}: {op.get('step_words', '')}"))
        else:
            rest.append(op)
    return out + rest


def read_all(networks, now: float = None) -> dict:
    """Every network's: the running operations (each held device once, with its network) and
    the recent receipts, newest first. A network whose read failed is named, never dropped:
    ``{"running", "recent", "unread": [(network, why)], "window_s"}``."""
    from modules import op_progress
    from modules.nsot import capture_job, device_ops

    now = time.time() if now is None else now
    running, recent_rows, unread = [], [], []
    for name in networks:
        try:
            running += [dict(r, list=name) for r in device_ops.in_flight(name, now)]
            rows, state = recent(name, now)
            if state not in ("ok", "absent"):    # absent: no receipt yet, never deployed
                unread.append((name, f"its receipts are {state}"))
            recent_rows += [dict(r, list=name) for r in rows]
        except Exception as exc:                      # noqa: BLE001
            unread.append((name, f"{type(exc).__name__}: {exc}"))
    running = merge(running, op_progress.running(now), capture_job.card_jobs(now))
    recent_rows.sort(key=lambda r: r.get("at", ""), reverse=True)
    return {"running": running, "recent": recent_rows, "unread": unread,
            "window_s": RECENT_SECONDS}


# ---------------------------------------------------------------------------
# The top bar's In progress chip (C537; boards A and B, canvas v66)
# ---------------------------------------------------------------------------

#: A hold's operation, as the In progress list names it.
OPERATION_NAMES = {
    "deploy": "Deploy", "restore": "Restore", "capture": "Capture",
    "rotate": "Rotate credential", "onboard": "Onboard", "persist": "Persist",
    "retire": "Retire", "save": "Save", "command": "A command that is not a read",
    "bulk": "Bulk change", "reload": "Reload", "file": "File action",
    "probe": "Removal probe", "read": "Show commands",
    # A scoped batch's operation is its scope's noun (`receipts.SCOPES`, C364).
    "monitoring profile apply": "Monitoring profile apply", "IP SLA send": "IP SLA send",
    "monitoring templates deploy": "Monitoring templates deploy",
    # Out-of-band: the console survey and kick-start, and the one-decision onboarding.
    "console survey": "Console survey", "console kick-start": "Console kick-start",
    "console onboard": "Out-of-band onboarding",
}

#: A console run's hold -> its run's declared stepper steps (each run's own table). A console
#: run's device may have no page yet (it is being onboarded), so its row opens the run's own
#: page (`oob_onboard_v2.run_page`), which draws its live stepper.
def _console_steps(op: str) -> tuple:
    from modules.nsot import console_ztp as Z
    from modules.nsot import oob_onboard as O

    return {Z.OP_SURVEY: lambda: Z.run_stepper_steps(Z.KIND_SURVEY),
            Z.OP_KICKSTART: lambda: Z.run_stepper_steps(Z.KIND_KICKSTART),
            O.OP: O.run_stepper_steps}.get(op, tuple)()

#: A hold's operation -> the device-page card whose stepper draws its steps.
STEPPED = ("rotate", "deploy", "restore", "reload")


def _clock(iso: str) -> str:
    """``21:03 UTC`` from an ISO time; "" when it is not one."""
    return f"{iso[11:16]} UTC" if len(iso or "") >= 16 else ""


def _who(actor: str, viewer: str) -> str:
    return "you" if actor and actor == viewer else (actor or "unknown")


def _step(row: dict) -> str:
    """The step a held device's operation is on, in the stepper's own words where its card
    draws one (`device_actions.job_steps`: "Persist: … · step 6 of 6"), else the hold's own
    words for its last progress."""
    op = row.get("operation", "")
    console = _console_steps(op)
    if console:
        # The step its last note began (`STEP_NOTES`), in its own stepper's words.
        for i, (_key, words, waits, names) in enumerate(console):
            if row.get("step") in names:
                return f"{words}: {waits} · step {i + 1} of {len(console)}"
        return f"{console[0][1]}: {console[0][2]} · step 1 of {len(console)}"
    if op in STEPPED and row.get("list"):
        from modules import device_actions
        try:
            steps = device_actions.job_steps(op, row["list"], row.get("device", ""))
        except Exception:                             # noqa: BLE001 (the hold's words stand)
            steps = []
        for i, s in enumerate(steps):
            if s.get("state") == "running":
                waits = s.get("waits") or ""
                return (f"{s['words']}" + (f": {waits}" if waits else "")
                        + f" · step {i + 1} of {len(steps)}")
    return row.get("step_words") or row.get("step") or "started"


def running_row(row: dict, viewer: str) -> dict:
    """One running operation as the list draws it: the device (or what the operation is
    about), the operation's name, the step, who, since when, its network, and whether the
    device's page reopens its card. An operation holding no device has no page to open."""
    if row.get("list"):                               # a device's row (`merge` names its list)
        return {"device": row.get("device", ""), "list": row.get("list", ""),
                "name": OPERATION_NAMES.get(row.get("operation", ""),
                                            row.get("operation") or "An operation"),
                "step": _step(row), "who": _who(row.get("actor", ""), viewer),
                "since": _clock(row.get("started", "")), "card": bool(row.get("job")),
                "page": True, "stalled": bool(row.get("stalled")),
                # A console run opens its own page, its live stepper (its device may have no
                # page yet); every other hold, its device's page, which reopens its card.
                "run": bool(_console_steps(row.get("operation", "")))}
    return {"device": row.get("device", ""), "list": "",
            "name": (row.get("operation") or "an operation")[:1].upper()
                    + (row.get("operation") or "an operation")[1:],
            "step": row.get("step_words") or row.get("step") or "started",
            "who": _who(row.get("actor", ""), viewer), "since": _clock(row.get("started", "")),
            "card": False, "page": False, "stalled": False}


def pending_step(d) -> str:
    """A pending onboarding's wait in words, from the onboarding-progress reader's last read
    of it (*d*, or None when it holds none yet)."""
    if not d:
        return "waiting for it to boot (not read yet)"
    if d.get("answering"):
        return "answering: ready to Verify"
    if d.get("stop"):
        return "no fetch 15 minutes after its Create: stop"
    if d.get("stage"):
        return d["stage"].replace("_", " ")
    return "waiting for it to boot" + (": not answering yet" if d.get("answering") is False
                                       else "")


def pending_rows(networks) -> tuple:
    """Every network's pending onboardings as In progress rows (C1193: the wait for a device to
    boot is an operation in progress, and nothing listed it): ``(rows, unread)``. Read from the
    onboarding-progress reader's store alone, which holds only the pending onboardings (it
    reads the manifests every 10 s): the chip is on every page, so walking each network's
    manifest here was work per fleet device per request (tests/test_scale.py). A store that
    cannot be read is named in *unread*."""
    from modules import reader_job
    from modules.readers import onboarding_progress as OP

    got = reader_job.read_cached(OP.READER_NAME)
    good = ((got.get("doc") or {}).get("last_good") or {})
    if got.get("state") != "ok" or not good:
        why = got.get("why") or "the reader has not stored a value yet"
        # Absent: the reader has not run yet, so nothing is known pending (said nowhere);
        # unreadable: said, for every network at once.
        return [], ([("every network", f"its pending onboardings: {why}")]
                    if got.get("state") == "unreadable" else [])
    wanted = set(networks)
    rows = []
    for d in ((good.get("value") or {}).get("devices") or {}).values():
        if d.get("list") not in wanted:
            continue
        rows.append({"device": d.get("name", ""), "list": d.get("list", ""),
                     "name": "Onboarding: waiting for it",
                     "step": pending_step(d), "who": "waiting on the device",
                     "since": _clock(d.get("onboarded_at", "")), "card": False,
                     "page": True, "stalled": bool(d.get("stop"))})
    return rows, []


#: A finished card's level -> how the chip counts it ("never green over a partial").
OUTCOMES = {"ok": "done", "warn": "partial", "danger": "failed"}


def finished_row(job: dict, viewer: str) -> dict:
    """A job a device's page started, finished and not opened by *viewer*: its outcome in its
    own card's words and level (`device_actions.job_card`, the card the page will open), or
    None when the result is no longer known (the card would say so)."""
    from modules import device_actions
    from modules.nsot import listref

    try:
        c = device_actions.job_card(listref.resolve(job["list"]), job["device"], job["card"],
                                    job["job"])
    except Exception:                                 # noqa: BLE001 (the row says it)
        log.warning("in_flight: the result of job %s could not be read", job.get("job"),
                    exc_info=True)
        c = {"state": "failed", "error": "its result could not be read"}
    if c.get("state") == "unknown":
        return None
    if c.get("state") == "failed":
        level, words = "danger", "failed: " + (c.get("error") or "no reason was recorded")
    else:
        level = c.get("level") if c.get("level") in OUTCOMES else "danger"
        words = c.get("words") or c.get("chip") or OUTCOMES[level]
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(job.get("finished_at") or 0))
    return {"device": job["device"], "list": job["list"], "card": job["card"],
            "name": OPERATION_NAMES.get(job["card"], job["card"]), "level": level,
            "outcome": OUTCOMES[level], "words": words, "at": _clock(at),
            "who": _who(job.get("actor", ""), viewer)}


def chip(networks, viewer: str, now: float = None) -> dict:
    """What the In progress chip draws for *viewer*: every operation running in every network
    (each held device once, C217), every job a device's page started that finished and
    *viewer* has not opened (kept as long as its job, `capture_job.KEEP_S`), and the networks
    whose holds could not be read (never drawn as nothing running). A READ: it probes the
    devices each network has MARKED as held (`device_ops.held`, C987: never every lock file a
    network ever had) and reads this process's jobs; it writes nothing."""
    from modules import op_progress
    from modules.nsot import capture_job, device_ops

    now = time.time() if now is None else now
    holds, unread = [], []
    for name in networks:
        try:
            holds += [dict(r, list=name) for r in device_ops.in_flight(name, now)]
        except Exception as exc:                      # noqa: BLE001
            unread.append((name, f"{type(exc).__name__}: {exc}"))
    jobs = capture_job.card_jobs(now)
    running = [running_row(r, viewer)
               for r in merge(holds, op_progress.running(now), jobs)]
    waits, unread_pending = pending_rows(networks)
    running += waits
    unread += unread_pending
    finished = [f for f in (finished_row(j, viewer) for j in jobs
                            if j["state"] != "running" and viewer not in j["opened"]) if f]
    counts = {k: sum(1 for f in finished if f["outcome"] == k) for k in OUTCOMES.values()}
    # Red wins; then a partial; then anything running; green only when all is done and clean.
    level = ("danger" if counts["failed"] or unread else "warn" if counts["partial"]
             else "run" if running else "ok")
    words = "; ".join(w for w in (
        f"{len(running)} running" if running else "",
        f"{counts['failed']} failed" if counts["failed"] else "",
        f"{counts['partial']} partial" if counts["partial"] else "",
        f"{counts['done']} done" if counts["done"] else "",
        f"{len(unread)} network(s) unread" if unread else "") if w)
    return {"running": running, "finished": finished, "unread": unread, "counts": counts,
            "level": level, "words": words, "shown": bool(running or finished or unread)}
