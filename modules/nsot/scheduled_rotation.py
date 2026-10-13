"""SCHEDULED CREDENTIAL ROTATION (C724; Labs 4 and 5 Part 2, Obj 1.2b: "passwords changed
automatically on a regular basis").

A policy per credential profile (Credentials › Profiles): off, or every N days, inside a
preferred window of UTC hours, at most K devices a run. A device follows the policy of the
profile the resolver would give it a login from (`credentials.resolve`'s order after a
device's own: ``role:<role>``, then ``site:<site>``, then ``default``), the most specific
profile that EXISTS; that profile's policy alone, off included.

A timer, and "Rotate due devices now", find the devices whose credential is older than their
policy and rotate them ONE AT A TIME through `rotate_op.run`, the v2 Rotate button's own job
path (plan, rotate, verify on a fresh login, record, persist): no rotation code of its own, so
its stages, records and History rows are a manual rotation's, named "scheduled rotation
(policy set by <person>)".

What it refuses, and what it skips (each with its reason, kept in the run's record):

* never inside the nightly backup window, 08:30 to 09:10 UTC (the whole run; a run that
  reaches it stops, the rest not reached);
* the timer runs a policy only inside its preferred window, once in any 24 hours; a person's "Rotate
  due devices now" runs every due device now (outside the preferred window too);
* a device another operation holds (`device_ops`), or one mid-restart (a planned-restart
  window covering now, or a restart recorded in the last 10 minutes), is skipped;
* a device off its intent (its committed golden differs from what its intent renders), or one
  whose plan cannot be made (unreachable, its account line unreadable), is skipped;
* the FIRST failure stops the run: a CRITICAL Needs attention row names the device and the
  stage, and the timer starts no scheduled run until a later run (a person's) finishes clean;
* never two runs at once, across processes (an exclusive `flock`, refused by name).

Credential age is the rotation record's (`credential_rotation.rotation_records_as_known`):
the device's last rotation that reached the device. None recorded: "never rotated by Mercury",
and due.
"""

import datetime as _dt
import hashlib
import json
import logging
import os
import re
import threading
import time

log = logging.getLogger(__name__)

SETTING = "credential_rotation_policies"
#: The commit's ``Source:`` slug for a scheduled rotation's record.
SOURCE = "scheduled-rotation"
#: Announced when a run ends or a device in it finishes (`invalidation.ANNOUNCERS`).
ANNOUNCER = "scheduled-rotation"
ANNOUNCE_KEYS = ("rotation", "credentials")
KIND = "scheduled rotation"
DEFAULT_DAYS = 30
DEFAULT_MAX = 5
#: A device name as an inventory holds it (a policy's "only these devices").
_DEVICE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
#: The nightly backup window, UTC (CLAUDE.md, standing facts): no run inside it.
BACKUP_WINDOW = ((8, 30), (9, 10))
#: The timer's tick. The preferred window is whole hours, so five minutes is at most a
#: twelfth of the shortest window; a tick does no device work unless a policy is due.
TICK_SECONDS = 300
#: A restart recorded this recently still counts as the device restarting
#: (`restarts.SAME_RESTART_SECONDS`, the span the tool treats as one restart).
RESTART_RECENT_SECONDS = 600
#: A run's steps, as the manual names them (docs/manual/how-it-works/rotate.md, "On a
#: schedule"): each device then runs Rotate's own steps (`rotate_op.STEPS`).
STEPS = (("refuse", "Refuse the backup window and a second run"),
         ("select", "Select the due devices"),
         ("check", "Check each device before it"),
         ("rotate", "Rotate it, one at a time"),
         ("stop", "Stop at the first failure"),
         ("record", "Record the run"))
RUNS_LOG = "scheduled_rotation_runs.jsonl"
LOCK_FILE = "scheduled_rotation.lock"


class RunInProgress(Exception):
    """Another run holds the lock: ``holder`` says who started it and when."""

    def __init__(self, holder: dict):
        self.holder = holder or {}
        super().__init__(
            "another scheduled rotation run is going (started "
            f"{self.holder.get('started_at') or 'at an unrecorded time'} by "
            f"{self.holder.get('actor') or 'an unrecorded caller'}, "
            f"{self.holder.get('trigger') or '?'}): one run at a time; nothing was started")


# ------------------------------------------------------------------ time and windows

def _now(now=None) -> float:
    return time.time() if now is None else float(now)


def _iso(ts) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


def _epoch(iso: str):
    try:
        return _dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def in_backup_window(now=None) -> bool:
    """Is *now* inside 08:30 to 09:10 UTC?"""
    t = time.gmtime(_now(now))
    minute = t.tm_hour * 60 + t.tm_min
    (h0, m0), (h1, m1) = BACKUP_WINDOW
    return h0 * 60 + m0 <= minute < h1 * 60 + m1


def in_window(policy: dict, now=None) -> bool:
    """Is *now* inside the policy's preferred window ``[start, end)`` in UTC hours? Start
    equal to end is the whole day; a start after its end wraps past midnight."""
    start, end = int(policy.get("window_start", 0)), int(policy.get("window_end", 24))
    hour = time.gmtime(_now(now)).tm_hour
    if start == end or (start == 0 and end == 24):
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


# ------------------------------------------------------------------ policies

def policies() -> dict:
    """``{profile: policy}`` as set (the settings' one key); {} when none."""
    from modules.settings_schema import get_setting
    got = get_setting("credential_rotation_policies", {}) or {}     # SETTING, host-scoped
    return got if isinstance(got, dict) else {}


def policy_words(p) -> str:
    """A policy in words, for the page, the record and History."""
    if not p or p.get("state") != "on":
        return "off"
    days = int(p.get("days", DEFAULT_DAYS))
    start, end = int(p.get("window_start", 0)), int(p.get("window_end", 24))
    window = ("any hour" if start == end or (start == 0 and end == 24)
              else f"{start:02d}:00 to {end:02d}:00 UTC")
    only = f", only {', '.join(p['devices'])}" if p.get("devices") else ""
    return (f"every {days} day{'s' if days != 1 else ''}, {window}, at most "
            f"{int(p.get('max_per_run', DEFAULT_MAX))} a run{only}")


def set_policy(profile: str, form: dict, *, actor: str, verified: str,
               person: bool) -> dict:
    """Set *profile*'s policy from *form* (``state``, ``days``, ``window_start``,
    ``window_end``, ``max_per_run``) as *actor*, and record it (who, when, what).
    ``{"ok", "error", "policy", "words", "recorded", "record_error"}``. Refused, nothing
    written, unless a verified PERSON asks (*person* and ``verified == "access"``)."""
    from modules import credential_changes, credentials
    from modules.settings_schema import write_settings

    if not person or verified != "access":
        return {"ok": False, "error": (
            "a rotation policy is set only by a verified person (this request is "
            f"{actor or 'nobody named'}, verified {verified or 'none'}): nothing was changed")}
    if profile not in {p["name"] for p in credentials.list_profiles()}:
        return {"ok": False, "error": f"no profile is named {profile!r}: nothing was changed"}
    state = (form.get("state") or "").strip()
    if state not in ("on", "off"):
        return {"ok": False, "error": f"a policy is on or off, not {state!r}"}

    def number(name, default, low, high):
        raw = str(form.get(name, "") if form.get(name, "") != "" else default).strip()
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(f"{name.replace('_', ' ')} is a whole number, not {raw!r}") from None
        if not low <= value <= high:
            raise ValueError(f"{name.replace('_', ' ')} is between {low} and {high}, "
                             f"not {value}")
        return value

    try:
        policy = {"state": state, "days": number("days", DEFAULT_DAYS, 1, 3650),
                  "window_start": number("window_start", 0, 0, 23),
                  "window_end": number("window_end", 24, 0, 24),
                  "max_per_run": number("max_per_run", DEFAULT_MAX, 1, 1000)}
    except ValueError as exc:
        return {"ok": False, "error": f"{exc}: nothing was changed"}
    # Only these devices (a pilot set): names, by comma or space; none = every device the
    # profile covers.
    devices = sorted({d for d in re.split(r"[\s,]+", str(form.get("devices") or "")) if d})
    bad = [d for d in devices if not _DEVICE_NAME.match(d)]
    if bad:
        return {"ok": False, "error": f"{', '.join(bad)} is not a device name: nothing was "
                                      "changed"}
    if devices:
        policy["devices"] = devices
    policy.update(set_by=actor, set_at=_iso(time.time()), verified=verified)
    merged = dict(policies())
    merged[profile] = policy
    got = write_settings({SETTING: merged}, actor=actor)
    if not got["ok"]:
        return {"ok": False, "error": f"the setting was refused, nothing changed: {got['error']}"}
    words = policy_words(policy)
    rec = credential_changes.record(action="rotation_policy", profile=profile, fields=[],
                                    actor=actor, verified=verified, policy=words)
    log.info("scheduled rotation: %s set %s's policy: %s", actor, profile, words)
    return {"ok": True, "error": "", "profile": profile, "policy": policy, "words": words,
            "recorded": rec["ok"], "record_error": rec["error"]}


def governing_profile(dev: dict, names: set) -> str:
    """The profile whose policy *dev* follows: the most specific that exists, in the
    resolver's order (role, site, default), or ""."""
    from modules.credentials import DEFAULT_PROFILE
    for name in (f"role:{dev.get('role')}" if dev.get("role") else "",
                 f"site:{dev.get('site')}" if dev.get("site") else "", DEFAULT_PROFILE):
        if name and name in names:
            return name
    return ""


# ------------------------------------------------------------------ credential age

def last_rotations() -> dict:
    """``{device: (epoch, iso)}``: each device's last rotation that reached the device
    (the rotation record's `rotate` rows whose state is rotated), newest."""
    from modules.nsot import credential_rotation as cr
    out = {}
    for r in cr.rotation_records_as_known():
        if r.get("phase") != "rotate" or not cr.rotation_succeeded(r):
            continue
        at = _epoch(r.get("at", ""))
        if at is not None and at >= out.get(r.get("device", ""), (0, ""))[0]:
            out[r.get("device", "")] = (at, r.get("at", ""))
    return out


#: A rotation's commit subject (credential_rotation._commit): the device is its second word.
_ROTATION_SUBJECT = re.compile(r"^credential: (?P<device>\S+) rotated ")


def committed_rotations(list_name: str) -> dict:
    """``{device: (epoch, iso)}``: each device's newest rotation COMMIT in *list_name*'s config
    repository. The rotation record (`last_rotations`) began after the first rotations: on
    2026-10-12 it held s1's and r2's while the repository held every device's from 2026-09-21,
    so a device read only from the record said "never rotated by Mercury" falsely. One `git
    log` a network; {} when the repository cannot be read (the record alone then answers)."""
    from modules.nsot import listref
    from modules.nsot.repo import git

    try:
        rc, out, _err = git(listref.resolve(list_name).repo_dir, "log",
                            "--format=%ct\t%cI\t%s", "--grep=^credential: .* rotated ")
    except Exception as exc:                            # noqa: BLE001
        log.warning("scheduled rotation: %s's rotation commits could not be read: %s",
                    list_name, exc)
        return {}
    if rc != 0:
        return {}
    found = {}
    for line in (out or "").splitlines():
        try:
            ct, iso, subject = line.split("\t", 2)
        except ValueError:
            continue
        m = _ROTATION_SUBJECT.match(subject)
        if m and int(ct) > found.get(m.group("device"), (0, ""))[0]:
            found[m.group("device")] = (int(ct), iso)
    return found


def _age_words(seconds: float) -> str:
    days = seconds / 86400
    if days >= 1:
        return f"{int(days)} day{'s' if int(days) != 1 else ''}"
    hours = seconds / 3600
    return f"{int(hours)} h" if hours >= 1 else f"{max(1, int(seconds // 60))} min"


def device_states(now=None, *, lists=None, devices_of=None, rotations=None,
                  pols=None, profile_names=None) -> list:
    """Every managed device's credential age and its policy: ``[{"list", "device", "profile",
    "policy", "policy_words", "rotated_at", "never", "age_words", "due", "due_at",
    "words"}]``. Reads files only (the registry, each inventory, the rotation record, the
    settings): no device is asked."""
    from modules import credentials
    from modules.device import load_saved_devices
    from modules.nsot import listref

    now = _now(now)
    names = (set(profile_names) if profile_names is not None
             else {p["name"] for p in credentials.list_profiles()})
    pols = policies() if pols is None else pols
    read_commits = rotations is None                  # a caller's *rotations* is the whole truth
    rotations = last_rotations() if rotations is None else rotations
    out = []
    for list_name in (sorted(listref._registry()) if lists is None else lists):
        committed = committed_rotations(list_name) if read_commits else {}
        try:
            rows = (devices_of(list_name) if devices_of else
                    load_saved_devices(listref.resolve(list_name).csv_path))
        except Exception as exc:                        # noqa: BLE001
            log.warning("scheduled rotation: %s's inventory could not be read: %s",
                        list_name, exc)
            continue
        for dev in rows:
            host = dev.get("hostname", "")
            if not host:
                continue
            profile = governing_profile(dev, names)
            pol = pols.get(profile) if profile else None
            on = bool(pol and pol.get("state") == "on")
            # A policy limited to named devices (a pilot set) covers only those.
            outside = bool(on and pol.get("devices") and host not in pol["devices"])
            on = on and not outside
            at, iso = max(rotations.get(host, (None, "")), committed.get(host, (None, "")),
                          key=lambda r: r[0] or 0)
            s = {"list": list_name, "device": host, "profile": profile, "policy": pol or {},
                 "policy_words": policy_words(pol), "on": on, "rotated_at": iso,
                 "never": at is None,
                 "age_words": ("never rotated by Mercury" if at is None
                               else f"rotated {_age_words(now - at)} ago")}
            if outside:
                s.update(due=False, due_at="", words=(
                    f"{profile}'s rotation policy names other devices "
                    f"({', '.join(pol['devices'])}), not this one"))
            elif not on:
                s.update(due=False, due_at="", words=(
                    "no profile covers it, so no rotation policy" if not profile else
                    f"{profile}'s rotation policy is off"))
            elif at is None:
                s.update(due=True, due_at="", words=(
                    f"never rotated by Mercury: due now under {profile}'s policy "
                    f"({policy_words(pol)})"))
            else:
                due_at = at + int(pol.get("days", DEFAULT_DAYS)) * 86400
                s.update(due=now >= due_at, due_at=_iso(due_at), words=(
                    f"due now under {profile}'s policy ({policy_words(pol)})"
                    if now >= due_at else f"next due {_iso(due_at)} under {profile}'s policy"))
            out.append(s)
    return out


def device_state(list_name: str, host: str, now=None) -> dict:
    """One device's entry (its page's Credential line), or None."""
    for s in device_states(now, lists=[list_name]):
        if s["device"] == host:
            return s
    return None


# ------------------------------------------------------------------ the runs record

def _data(name: str) -> str:
    from modules import config
    return os.path.join(config.DATA_DIR, name)


def runs() -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``, oldest first."""
    path = _data(RUNS_LOG)
    if not os.path.exists(path):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"state": "ok", "rows": [json.loads(l) for l in fh if l.strip()],
                    "error": ""}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{RUNS_LOG}: {exc}"}


def _append(row: dict) -> None:
    from modules.config import open_secure
    from modules.filestore import PathLock
    path = _data(RUNS_LOG)
    try:
        with PathLock(path):
            with open_secure(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("scheduled rotation: COULD NOT RECORD run %s (%s)", row.get("run"), exc)


#: A run's end states that decide whether the timer is stopped (a refused run decides
#: nothing: it changed nothing).
DECISIVE = ("done", "stopped", "nothing_due")


def last_decisive(rows=None):
    """The last run that ran (done, stopped on a failure, or found nothing due), or None."""
    rows = runs()["rows"] if rows is None else rows
    return next((r for r in reversed(rows) if r.get("state") in DECISIVE), None)


# ------------------------------------------------------------------ the lock

class RunLock:
    """One run at a time across processes: an exclusive `flock` the kernel releases with its
    holder (drift_check's shape, CONCURRENCY_AUDIT R19); a second run raises
    `RunInProgress` naming the first, never waits."""

    def __init__(self, actor: str, trigger: str):
        self.actor, self.trigger, self.fd = actor, trigger, None

    def __enter__(self):
        import fcntl
        path = _data(LOCK_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            text = os.read(fd, 1 << 16).decode("utf-8", "replace")
            os.close(fd)
            try:
                holder = json.loads(text) if text.strip() else {}
            except ValueError:
                holder = {}
            raise RunInProgress(holder) from None
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({"pid": os.getpid(), "actor": self.actor,
                                 "trigger": self.trigger,
                                 "started_at": _iso(time.time())}).encode())
        self.fd = fd
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            import fcntl
            try:
                os.ftruncate(self.fd, 0)
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None
        return False


# ------------------------------------------------------------------ selection

def select(states: list, now=None, *, scheduled: bool, ran_today=()) -> tuple:
    """``(chosen, waiting)``: the due devices this run takes, oldest credential first (never
    rotated first), at most each policy's ``max_per_run``; and the due ones it leaves, each
    with why. A scheduled run takes a policy only inside its preferred window and only once a
    24 hours (*ran_today*: the profiles a scheduled run took in the last 24 hours, C724)."""
    now = _now(now)
    due = sorted((s for s in states if s.get("due")),
                 key=lambda s: (not s["never"], _epoch(s["rotated_at"]) or 0,
                                s["list"], s["device"]))
    chosen, waiting, taken = [], [], {}
    for s in due:
        pol = s["policy"]
        if scheduled and not in_window(pol, now):
            waiting.append(dict(s, why=f"outside {s['profile']}'s preferred window "
                                       f"({policy_words(pol)})"))
            continue
        if scheduled and s["profile"] in ran_today:
            waiting.append(dict(s, why=f"{s['profile']}'s scheduled run ran in the last 24 hours"))
            continue
        limit = int(pol.get("max_per_run", DEFAULT_MAX))
        if taken.get(s["profile"], 0) >= limit:
            waiting.append(dict(s, why=f"past {s['profile']}'s limit of {limit} a run: the "
                                       "next run takes it"))
            continue
        taken[s["profile"]] = taken.get(s["profile"], 0) + 1
        chosen.append(s)
    return chosen, waiting


def selection_hash(chosen: list) -> str:
    """What a person confirms on "Rotate due devices now": the devices it would take."""
    return hashlib.sha256(json.dumps(sorted([s["list"], s["device"]] for s in chosen))
                          .encode()).hexdigest()[:16]


def preview(now=None) -> dict:
    """"Rotate due devices now"'s preview: the due devices it takes and those it leaves, the
    hash to confirm. Reads files only; asks no device."""
    now = _now(now)
    states = device_states(now)
    chosen, waiting = select(states, now, scheduled=False)
    return {"chosen": chosen, "waiting": waiting, "hash": selection_hash(chosen),
            "backup_window": in_backup_window(now),
            "covered": sum(1 for s in states if s["on"]), "total": len(states)}


# ------------------------------------------------------------------ the checks before each

def restarting(list_name: str, host: str, now=None) -> str:
    """Why *host* counts as mid-restart now, or "". An unreadable restart record is a reason
    too: whether it is restarting cannot be told."""
    from modules import restarts
    now = _now(now)
    try:
        planned = restarts.planned_rows()
    except RuntimeError as exc:
        return str(exc)
    for p in planned:
        if restarts._window_covers(p, host, now, list_name):
            return (f"a planned restart window covers it now ({p.get('from')} to "
                    f"{p.get('until')}, declared by {p.get('by') or '?'})")
    seen = restarts.events(host, list_name)
    if seen["state"] == "unreadable":
        return f"the restart record could not be read ({seen.get('error')})"
    for r in seen["rows"]:
        at = _epoch(r.get("at", ""))
        if at is not None and now - at < RESTART_RECENT_SECONDS:
            return f"it restarted at {r.get('at')}, under {RESTART_RECENT_SECONDS // 60} min ago"
    return ""


def off_intent(list_name: str, host: str) -> str:
    """Why *host* is off its intent (its committed golden differs from its intent), or ""."""
    from modules import device_page
    from modules.device import load_saved_devices
    from modules.nsot import listref
    ref = listref.resolve(list_name)
    dev = next((d for d in load_saved_devices(ref.csv_path) if d.get("hostname") == host), None)
    if dev is None:
        return "it is no longer in its list's inventory"
    got = device_page.intent_check(ref, dev)
    return f"off its intent: {got.get('text')}" if got.get("state") == "warn" else ""


def failed_stage(out: dict) -> str:
    """The stage a rotation stopped at, in the code's own step names."""
    from modules.nsot import credential_rotation as cr
    step = next((s for s in out.get("steps") or [] if not s.get("ok")), None)
    if step:
        return step.get("name", "?")
    if out.get("persist_skipped"):
        return "persist (not attempted)"
    stage = cr._failed_stage(out)
    return f"persist: {stage}" if stage else (out.get("state") or "unknown")


# ------------------------------------------------------------------ the run

#: Live progress of the runs in THIS process, for the card: ``{run: {...}}``.
_progress = {}
_progress_lock = threading.Lock()


def progress(run_id: str):
    with _progress_lock:
        got = _progress.get(run_id)
        return json.loads(json.dumps(got)) if got else None


def _set_progress(run_id: str, **kw) -> None:
    with _progress_lock:
        _progress.setdefault(run_id, {"rows": {}, "skipped": []}).update(kw)


def _row_progress(run_id: str, key: str, **kw) -> None:
    with _progress_lock:
        _progress.setdefault(run_id, {"rows": {}, "skipped": []})["rows"].setdefault(
            key, {}).update(kw)


def _announce() -> None:
    try:
        from modules import invalidation
        invalidation.announce(ANNOUNCE_KEYS, by=ANNOUNCER)
    except Exception as exc:                            # noqa: BLE001
        log.info("scheduled rotation: not announced (%s)", exc)


def run(*, trigger: str, actor: str = "", now=None, run_id: str = "", confirmed: str = "",
        plan=None, rotate=None, checks=None, clock=None) -> dict:
    """One run. *trigger*: ``scheduled`` (the timer; each rotation's actor is its policy's
    setter) or ``request`` (a person's "Rotate due devices now", *actor* that person, bound to
    the preview's *confirmed* hash). *plan*, *rotate*, *checks* (``{"held", "restarting",
    "off_intent"}``) and *clock* stand in for the real ones in tests.

    ``{"ok", "state", "run", "rotated", "skipped", "failed", "not_reached", "waiting",
    "error"}``; recorded whether it rotated anything or not."""
    from modules.nsot import credential_rotation as cr
    from modules.nsot import device_ops, rotate_op

    clock = clock or (lambda: _now(now))
    plan = plan or rotate_op.plan
    rotate = rotate or rotate_op.run
    checks = checks or {}
    held = checks.get("held") or (lambda l, h: device_ops.holder(l, h))
    is_restarting = checks.get("restarting") or (lambda l, h: restarting(l, h, clock()))
    is_off_intent = checks.get("off_intent") or off_intent
    run_id = run_id or f"{int(clock())}-{os.getpid()}"
    started = clock()
    record = {"run": run_id, "trigger": trigger, "actor": actor, "started": _iso(started),
              "rotated": [], "skipped": [], "failed": None, "not_reached": [], "waiting": [],
              "policies": [], "error": ""}

    def finish(state, error=""):
        record.update(state=state, error=error, finished=_iso(clock()))
        _append(record)
        _set_progress(run_id, state=state, error=error, finished=record["finished"])
        _announce()
        return dict(record, ok=state in ("done", "nothing_due"))

    if in_backup_window(started):
        return finish("refused", "inside the nightly backup window, 08:30 to 09:10 UTC: no "
                                 "run starts then, so a measurement does not measure the "
                                 "backup; nothing was sent")
    try:
        lock = RunLock(actor or "the timer", trigger)
        lock.__enter__()
    except RunInProgress as exc:
        record.update(state="refused", error=str(exc), finished=_iso(clock()))
        _append(record)
        return dict(record, ok=False)
    try:
        prior = runs()["rows"]
        if trigger == "scheduled":
            last = last_decisive(prior)
            if last and last.get("state") == "stopped":
                f = last.get("failed") or {}
                return finish("refused", (
                    f"the last run stopped on {f.get('device', '?')} at {f.get('stage', '?')} "
                    f"({last.get('finished')}): the timer starts no run until a person runs "
                    "Rotate due devices now on Credentials › Profiles"))
        today = started - 86400            # a scheduled run per policy in any 24 h (C724)
        ran_today = {p for r in prior if r.get("trigger") == "scheduled"
                     and (_epoch(r.get("started", "")) or 0) > today
                     and r.get("state") in DECISIVE for p in r.get("policies") or []}
        states = device_states(started)
        chosen, waiting = select(states, started, scheduled=trigger == "scheduled",
                                 ran_today=ran_today)
        if trigger == "request" and confirmed and selection_hash(chosen) != confirmed:
            return finish("refused", (
                f"the due devices changed since the preview you confirmed ({confirmed} -> "
                f"{selection_hash(chosen)}): a rotation, a policy or the inventory moved. "
                "Nothing was sent; preview again"))
        record["waiting"] = [{"list": s["list"], "device": s["device"], "why": s["why"]}
                             for s in waiting]
        record["policies"] = sorted({s["profile"] for s in chosen})
        _set_progress(run_id, state="running", trigger=trigger, actor=actor,
                      started=record["started"],
                      order=[f"{s['list']}/{s['device']}" for s in chosen])
        for s in chosen:
            _row_progress(run_id, f"{s['list']}/{s['device']}", list=s["list"],
                          device=s["device"], group="waiting", detail="waiting its turn")
        if not chosen:
            return finish("nothing_due")
        for i, s in enumerate(chosen):
            key, lst, host = f"{s['list']}/{s['device']}", s["list"], s["device"]
            if in_backup_window(clock()):
                record["not_reached"] = [{"list": c["list"], "device": c["device"]}
                                         for c in chosen[i:]]
                for c in chosen[i:]:
                    _row_progress(run_id, f"{c['list']}/{c['device']}", group="not_reached",
                                  detail="not reached: the backup window began")
                return finish("done", "stopped at the nightly backup window, 08:30 UTC: "
                                      "the rest wait for the next run")
            reason = ""
            holder = held(lst, host)
            if holder:
                reason = f"held by another operation: {device_ops.describe(holder)}"
            reason = reason or is_restarting(lst, host)
            if not reason:
                try:
                    reason = is_off_intent(lst, host)
                except Exception as exc:                # noqa: BLE001
                    reason = f"its intent could not be compared ({type(exc).__name__}: {exc})"
            p = None
            if not reason:
                _row_progress(run_id, key, group="running", detail="reading its account line")
                p = plan(lst, host)
                if not p.get("ok"):
                    reason = ("its plan could not be made (unreachable, or its account "
                              f"line unreadable): {p.get('error') or 'the preflight failed'}")
            if reason:
                record["skipped"].append({"list": lst, "device": host, "why": reason})
                _row_progress(run_id, key, group="skipped", detail=f"skipped: {reason}")
                with _progress_lock:
                    _progress[run_id]["skipped"].append({"device": host, "why": reason})
                continue
            setter = (s["policy"] or {}).get("set_by") or "nobody recorded"
            who = actor if trigger == "request" else setter
            via = (f"scheduled rotation (policy set by {setter})"
                   + (f", run now by {actor}" if trigger == "request" else ""))
            _row_progress(run_id, key, group="running", detail="")
            out = rotate(lst, host, actor=who, fingerprint=p.get("fingerprint", ""),
                         via=via, actor_kind="person" if trigger == "request" else "policy",
                         source=SOURCE)
            if out.get("state") == cr.ROTATED_PERSISTED:
                record["rotated"].append({"list": lst, "device": host, "actor": who})
                _row_progress(run_id, key, group="done", detail="rotated and persisted")
                _announce()
                continue
            stage = failed_stage(out)
            record["failed"] = {"list": lst, "device": host, "stage": stage,
                                "state": out.get("state", ""),
                                "detail": str(out.get("reason") or out.get("persist_skipped")
                                              or "")[:300]}
            record["not_reached"] = [{"list": c["list"], "device": c["device"]}
                                     for c in chosen[i + 1:]]
            _row_progress(run_id, key, group="failed",
                          detail=f"stopped at {stage} ({out.get('state', '?')})")
            for c in chosen[i + 1:]:
                _row_progress(run_id, f"{c['list']}/{c['device']}", group="not_reached",
                              detail="not reached: the run stopped on the failure before it")
            log.error("scheduled rotation: run %s stopped on %s/%s at %s", run_id, lst, host,
                      stage)
            return finish("stopped", f"{host} failed at {stage}: the run stopped")
        return finish("done")
    finally:
        lock.__exit__(None, None, None)


def start_now(*, actor: str, confirmed: str) -> tuple:
    """"Rotate due devices now": the run as a job, as the verified person (the request's
    identity carried into the job, so its commits read ``Actor-Verified: access``):
    ``(job id, run id)``."""
    from modules.nsot import capture_job

    run_id = f"{int(time.time())}-{os.getpid()}-{threading.get_ident() % 10000}"
    _set_progress(run_id, state="starting", trigger="request", actor=actor)

    def work(_job):
        return {"ok": True, "run": run_id,
                "result": run(trigger="request", actor=actor, run_id=run_id,
                              confirmed=confirmed)}

    job = capture_job.start("", "rotating due devices", actor, work, kind=KIND,
                            announce_keys=ANNOUNCE_KEYS, announcer=ANNOUNCER)
    with _progress_lock:
        _progress[run_id]["job"] = job
    return job, run_id


def run_card(run_id: str) -> dict:
    """A run on the one stepper (`modules.run_stepper`): a row per device it takes, each on
    Rotate's own steps (`rotate_op.STEPS`, read from the device's hold while it runs), the
    skipped devices beside it with their reasons. None when this process has no such run."""
    from modules import device_actions
    from modules import run_stepper as RS
    from modules.nsot import rotate_op

    got = progress(run_id)
    if not got:
        return None
    rows, skipped = [], []
    for key in got.get("order") or []:
        r = (got.get("rows") or {}).get(key) or {}
        group, host, lst = r.get("group", "waiting"), r.get("device", key), r.get("list", "")
        if group == "skipped":
            skipped.append({"device": host, "why": r.get("detail", "")})
            continue
        if group == "running":
            steps = RS.from_stepper(device_actions.job_steps("rotate", lst, host))
        elif group in ("done", "failed"):
            steps = RS.finished(RS.from_stepper(device_actions.stepper(rotate_op.STEPS, None)),
                                group) if group == "done" else []
        else:
            steps = []
        rows.append(RS.row(host, group, steps, detail=r.get("detail", "")))
    card = RS.card(rows, label="Rotate due devices", key="scheduled-rotation")
    return {"card": card, "skipped": skipped, "state": got.get("state", "running"),
            "error": got.get("error", ""), "finished": got.get("finished", ""),
            "running": got.get("state") in ("starting", "running")}


# ------------------------------------------------------------------ the page

def page_view(now=None) -> dict:
    """Credentials › Profiles' rotation part: each profile's policy and what it covers (devices,
    due, the next due), every device's credential age and next due (grouped by state), the
    last run, and whether the timer is stopped. Files only."""
    now = _now(now)
    try:
        states = device_states(now)
        error = ""
    except Exception as exc:                            # noqa: BLE001
        states, error = [], f"the devices' credential ages could not be read: {exc}"
    pols = policies()
    by_profile = {}
    for s in states:
        if not s["profile"]:
            continue
        p = by_profile.setdefault(s["profile"], {"devices": 0, "due": 0, "never": 0,
                                                 "next_due": ""})
        p["devices"] += 1
        p["due"] += 1 if s["due"] else 0
        p["never"] += 1 if s["never"] else 0
        if s["on"] and not s["due"] and s["due_at"] and (not p["next_due"]
                                                          or s["due_at"] < p["next_due"]):
            p["next_due"] = s["due_at"]
    got = runs()
    last = got["rows"][-1] if got["rows"] else None
    decisive = last_decisive(got["rows"])
    groups = [("due", "due now", [s for s in states if s["due"]]),
              ("later", "rotated within their policy",
               [s for s in states if s["on"] and not s["due"]]),
              ("off", "no policy on", [s for s in states if not s["on"]])]
    return {"profiles": {name: dict(by_profile.get(name, {"devices": 0, "due": 0, "never": 0,
                                                          "next_due": ""}),
                                    policy=pols.get(name) or {},
                                    words=policy_words(pols.get(name)))
                         for name in set(by_profile) | set(pols)},
            "groups": [{"key": k, "words": w, "rows": rows, "count": len(rows)}
                       for k, w, rows in groups],
            "due": sum(1 for s in states if s["due"]), "total": len(states),
            "covered": sum(1 for s in states if s["on"]), "error": error,
            "runs_error": got.get("error", ""), "last": last,
            "stopped": bool(decisive and decisive.get("state") == "stopped"),
            "backup_window": in_backup_window(now), "now": _iso(now)}


# ------------------------------------------------------------------ the timer

_timer = {"thread": None}


def tick(now=None) -> dict:
    """One timer tick: a scheduled run when any policy is on and inside its window now;
    otherwise nothing, and nothing recorded."""
    now = _now(now)
    pols = {k: v for k, v in policies().items() if (v or {}).get("state") == "on"}
    if not pols or in_backup_window(now) or not any(in_window(p, now) for p in pols.values()):
        return {"ok": True, "state": "idle"}
    states = device_states(now)
    today = now - 86400                    # a scheduled run per policy in any 24 h (C724)
    ran_today = {p for r in runs()["rows"] if r.get("trigger") == "scheduled"
                 and (_epoch(r.get("started", "")) or 0) > today
                 and r.get("state") in DECISIVE for p in r.get("policies") or []}
    chosen, _w = select(states, now, scheduled=True, ran_today=ran_today)
    if not chosen:
        return {"ok": True, "state": "idle"}
    return run(trigger="scheduled", now=now)


def _loop(sleep=time.sleep) -> None:
    while True:
        sleep(TICK_SECONDS)
        try:
            tick()
        except Exception as exc:                        # noqa: BLE001
            log.error("scheduled rotation: the timer's tick raised: %s", exc)


def start() -> None:
    """Start the timer in this process (the app's `_start_background_daemons`, only)."""
    if _timer["thread"] is not None:
        return
    t = threading.Thread(target=_loop, daemon=True, name="scheduled-rotation")
    _timer["thread"] = t
    t.start()
