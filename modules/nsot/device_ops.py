"""One operation per device at a time (register C98).

**The confirm-by-hash guarantee assumed ONE mover.** The hash protects
against a device's state moving between preview and apply, and the design
never considered a second operation moving it. On 2026-09-27 a restore of r2
and a deploy of r2's intent ran at the same time, both confirmed by the same
person, and the deploy's check passed against a stored config the restore was
mid-way through rewriting. Harmless only because both pushed the same line.
The tool offered both screens without a word; the operator did it by
accident, while running a procedure and paying attention, because the first
operation showed nothing while it ran (C99).

So anything that changes a device, or the record of one, holds that device
from its apply to its commit: deploy, restore, capture, credential rotation,
onboarding's second phase, persisting a device's startup config, and
retirement. A second operation is REFUSED, never queued, and the refusal
names the holder: *"r2 is being restored by operator@example.com, started
18:52:49 UTC"* is a refusal a person can act on. A queue would do the second
change later against a state its confirm never saw.

**Across processes.** The CLIs (`nmas-rotate-credential`, `nmas-retire`,
`nmas-persist-native`) change devices from a separate process on the host,
so the lock is an exclusive `flock` on one file per device, holding the
holder's description as JSON. The kernel releases a `flock` when its process
dies, so a crash cannot leave a device locked for ever. Within one process
the lock is re-entrant for the thread that holds it (onboarding's phase two
rotates inside its own hold) and refuses any other thread. `fcntl` does not
exist on Windows; there the lock is in-process only, and says so.
"""

import contextlib
import json
import logging
import os
import re
import threading
import time

log = logging.getLogger(__name__)

#: What a holder is doing, in the words of the refusal.
OPERATION_WORDS = {
    "deploy": "deployed to", "restore": "restored", "capture": "captured",
    "rotate": "rotated", "onboard": "onboarded", "persist": "persisted",
    "retire": "retired",
    "save": "saved (write memory)",
    "command": "sent a command that is not a read",
    "bulk": "changed by a bulk operation",
    "reload": "reloaded",
    "file": "changed by a file action",
    "probe": "probed for removal shapes (scratch config added and removed, never saved)",
}

#: An operation whose RESULT differs from its kind's usual one, in words
#: (the operator, 2026-09-28): a Save All that will record only a denial
#: holds each device as a capture, and "is being captured" contradicted the
#: button that started it. Keyed on (operation, the hold's detail); a detail
#: not listed here is drawn as it always was.
MODE_WORDS = {
    ("capture", "denial_only"): "read for the denial record (nothing will be recorded as "
                                "its golden)",
    ("capture", "baseline_only"): "read for the baseline (nothing will be recorded as its "
                                  "golden)",
}

#: The capture modes the apply accepts from the confirm; anything else is
#: the ordinary capture, never drawn raw.
CAPTURE_MODES = ("record", "denial_only", "baseline_only")


def _words(holder: dict) -> tuple:
    """(what it is doing, the detail still worth drawing)."""
    op, detail = holder.get("operation", ""), holder.get("detail") or ""
    if (op, detail) in MODE_WORDS:
        return MODE_WORDS[(op, detail)], ""
    if op == "capture" and detail == "record":
        return OPERATION_WORDS["capture"], ""
    return OPERATION_WORDS.get(op, op or "?"), detail


#: No progress for this long and the refusal says the holder may be stuck.
#: A pipeline's longest wait is a settle window (90 s) plus a read (120 s),
#: so ten minutes without a step is past anything a working operation does.
STALL_AFTER_SECONDS = 600


def _for(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return f"{seconds} s"
    if seconds < 5400:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {seconds % 3600 // 60} min"


class DeviceBusy(RuntimeError):
    """Another operation holds this device."""

    def __init__(self, holder: dict):
        self.holder = holder
        super().__init__(describe(holder))


def describe(holder: dict, now: float = None) -> str:
    """The refusal, in the words a person acts on: who, what, since when, how
    long, and whether it is still MOVING. A lock with no age is a lock people
    force (the operator), so the refusal separates "wait" from "something is
    stuck". There is no force: a hold ends when its operation finishes or its
    process stops, and then the kernel releases it."""
    now = time.time() if now is None else now
    word, detail = _words(holder)
    started_at = holder.get("started", 0) or 0
    started = time.strftime("%H:%M:%S UTC", time.gmtime(started_at))
    progress = holder.get("progress") or {}
    moved = progress.get("at", started_at) or started_at
    text = (f"{holder.get('device', '?')} is being {word} by {holder.get('actor') or 'unknown'}, "
            f"started {started}" + (f" ({detail})" if detail else "")
            + f", held for {_for(now - started_at)}")
    if progress.get("step"):
        text += f"; last progress: {progress['step']}, {_for(now - moved)} ago"
    if holder.get("pid"):
        text += f" (process {holder['pid']})"
    text += "."
    if now - moved > STALL_AFTER_SECONDS:
        text += (f" No progress for {_for(now - moved)}: it may be stuck. There is no "
                 "force: the hold ends when that operation finishes or its process stops, "
                 "and the kernel then releases it.")
    return text + (" One operation per device at a time: this one was refused, not "
                   "queued, and nothing was sent to it.")


#: What a holder is waiting on, by the progress step it noted: "what it waits
#: on" is the half of an in-flight state a person needs most (C99). The
#: pipeline's stage names come first; an unknown step is shown as it is.
STEP_WORDS = {
    "netbox_query": "reading NetBox",
    "template_render": "rendering the program",
    "ci_gate": "checking the program for dangerous lines",
    "pre_snapshot": "reading the device before the change",
    "config_diff": "computing the difference",
    "deploy": "sending the program to the device",
    "post_snapshot": "reading the device after the change",
    "verify": ("verifying: routing protocols are given up to 90 s to settle, "
               "and it waits for them"),
    "save_golden": "recording the new golden",
    "audit_log": "writing the audit record",
}


def busy_text(list_name: str, hostname: str) -> str:
    """What holds *hostname* now, in words, or "" when nothing does: the
    preview's gate says it BEFORE the confirm (C99), where it used to surface
    only as the apply's refusal. It is checked again at apply, by the lock."""
    found = holder(list_name, hostname)
    if not found:
        return ""
    return describe(found).split(" One operation per device")[0]


def held(list_name: str) -> list:
    """Every device held in *list_name* now: its holder, newest first. A READ:
    it lists the list's lock files and asks each; it creates nothing."""
    from modules import config

    out, seen = [], set()
    with _mu:
        for (lst, host), mine in _held.items():
            if lst == list_name.lower():
                out.append(dict(mine["holder"]))
                seen.add(host)
    folder = os.path.join(config.DATA_DIR, "device_ops", _safe(list_name.lower()))
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        names = []
    for name in names:
        if not name.endswith(".lock"):
            continue
        path = os.path.join(folder, name)
        host = _read_holder_file(path, name[:-5]).get("device") or name[:-5]
        if host in seen:
            continue
        found = holder(list_name, host)
        if found:
            out.append(found)
    return sorted(out, key=lambda h: h.get("started", 0), reverse=True)


def in_flight(list_name: str, now: float = None) -> list:
    """What is running on *list_name*'s devices, in words (C99): who, what,
    since when, and what it is waiting on. A fifty-second restore showed
    nothing while it ran, and the silence caused a second change."""
    now = time.time() if now is None else now
    rows = []
    for h in held(list_name):
        progress = h.get("progress") or {}
        started = h.get("started", 0) or 0
        moved = progress.get("at", started) or started
        step = progress.get("step", "")
        rows.append({
            "device": h.get("device", ""), "operation": h.get("operation", ""),
            "words": _words(h)[0],
            "actor": h.get("actor", ""), "pid": h.get("pid"),
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "held_for_s": round(now - started),
            "step": step, "step_words": STEP_WORDS.get(step, step),
            "step_ago_s": round(now - moved),
            "stalled": now - moved > STALL_AFTER_SECONDS,
            "text": describe(h, now).split(" One operation per device")[0],
        })
    return rows


#: Where an operation that did not finish is kept once the next operation takes its device
#: (CONCURRENCY_AUDIT R5), one per list's folder.
INTERRUPTED_LOG = "interrupted.jsonl"


def _list_folders() -> list:
    """Every list folder that has ever held a device: the folder's own (safe) name."""
    from modules import config

    root = os.path.join(config.DATA_DIR, "device_ops")
    try:
        return sorted(n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n)))
    except OSError:
        return []


def held_anywhere() -> list:
    """Every device held now, in EVERY list, by any process (CONCURRENCY_AUDIT R5): what a
    restart, an update or a deploy of the application would cut off half-way. A READ."""
    out, seen = [], set()
    for folder in _list_folders():
        for h in held(folder):
            key = (str(h.get("list") or folder).lower(), h.get("device"), h.get("started"))
            if key not in seen:
                seen.add(key)
                out.append(dict(h, list=h.get("list") or folder))
    return sorted(out, key=lambda h: h.get("started", 0) or 0, reverse=True)


def _leftover(path: str, hostname: str):
    """The record a process left in a lock file nobody holds, or None.

    `release()` empties the file before unlocking it, so a non-empty file that no process
    holds is an operation whose process ENDED while it held the device: a restart, an
    update, a crash. The kernel released the `flock`; the record of what was running is
    the only trace left."""
    try:
        import fcntl
    except ImportError:
        return None
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return None                     # held: the operation is running
        try:
            text = os.read(fd, 1 << 20).decode("utf-8", "replace")
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    if not text.strip():
        return None
    try:
        found = json.loads(text)
    except ValueError:
        found = {}
    if not isinstance(found, dict):
        found = {}
    found.setdefault("device", hostname)
    return found


def _record_interrupted(list_name: str, hostname: str, left: dict, operation: str,
                        actor: str) -> None:
    """Keep what an interrupted operation left before the next one overwrites its lock
    file: appended to the list's `interrupted.jsonl` (0600), with who took the device next.
    A failure is logged loudly: the record is the only trace of the interruption."""
    from modules.config import open_secure

    path = os.path.join(os.path.dirname(_path(list_name, hostname)), INTERRUPTED_LOG)
    entry = {"record": dict(left, device=left.get("device") or hostname),
             "found_at": time.time(), "found_by": {"operation": operation, "actor": actor}}
    try:
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("device_ops: an interrupted %s on %s could not be kept (%s); it is lost",
                  left.get("operation", "operation"), hostname, exc)
        return
    log.warning("device_ops: %s's last %s (started by %s, pid %s) did not finish: the "
                "process ended while it held the device; kept in %s",
                hostname, left.get("operation", "operation"), left.get("actor", "?"),
                left.get("pid", "?"), path)


def interrupted(list_name: str) -> list:
    """Every operation on *list_name* whose process ended while it held a device: the ones
    still in their lock file, and the ones kept when the next operation took the device.
    Each is the holder's record (device, operation, actor, started, progress, pid) with
    `found_at` (None while still in the lock file). A READ: it creates nothing."""
    from modules import config

    folder = os.path.join(config.DATA_DIR, "device_ops", _safe(list_name.lower()))
    out, seen = [], set()

    def add(rec, found_at):
        key = (rec.get("device"), rec.get("started"))
        if key in seen:
            return
        seen.add(key)
        out.append(dict(rec, list=rec.get("list") or list_name, found_at=found_at))

    try:
        with open(os.path.join(folder, INTERRUPTED_LOG), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            log.error("device_ops: an unreadable line in %s is skipped", INTERRUPTED_LOG)
            continue
        if isinstance(entry, dict) and isinstance(entry.get("record"), dict):
            add(entry["record"], entry.get("found_at"))
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        names = []
    for name in names:
        if name.endswith(".lock"):
            left = _leftover(os.path.join(folder, name), name[:-5])
            if left:
                add(left, None)
    return sorted(out, key=lambda r: r.get("started", 0) or 0)


def interrupted_anywhere() -> list:
    """`interrupted()` for every list folder."""
    return [r for folder in _list_folders() for r in interrupted(folder)]


_held: dict = {}            # key -> {"fd", "count", "thread", "holder"}
_mu = threading.Lock()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or "") or "_"


def _path(list_name: str, hostname: str) -> str:
    from modules import config

    return os.path.join(config.DATA_DIR, "device_ops", _safe(list_name.lower()),
                        f"{_safe(hostname)}.lock")


def _read_holder_file(path: str, hostname: str) -> dict:
    """The holder another process wrote into its lock file. Reads only, and
    takes no in-process lock, so it is safe to call while holding one."""
    unknown = {"device": hostname, "operation": "?", "actor": "", "started": 0}
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        return json.loads(text) if text.strip() else unknown
    except (OSError, ValueError):
        return unknown


def holder(list_name: str, hostname: str):
    """Who holds this device now, or None. A READ: it creates nothing."""
    key = (list_name.lower(), hostname)
    with _mu:
        mine = _held.get(key)
        if mine:
            return dict(mine["holder"])
    path = _path(list_name, hostname)
    if not os.path.exists(path):
        return None
    try:
        import fcntl
    except ImportError:
        return None
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return _read_holder_file(path, hostname)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return None
    finally:
        os.close(fd)


def acquire(list_name: str, hostname: str, operation: str, actor: str,
            detail: str = "", ip: str = "") -> None:
    """Hold *hostname* for *operation*, or raise :class:`DeviceBusy`."""
    key = (list_name.lower(), hostname)
    me = threading.get_ident()
    now = time.time()
    info = {"device": hostname, "list": list_name, "operation": operation,
            "actor": actor, "detail": detail, "started": now, "ip": ip,
            "pid": os.getpid(), "progress": {"step": "started", "at": now}}
    with _mu:
        mine = _held.get(key)
        if mine:
            if mine["thread"] == me:
                mine["count"] += 1
                return
            raise DeviceBusy(dict(mine["holder"]))
        fd = None
        try:
            import fcntl
        except ImportError:
            fcntl = None
        if fcntl is not None:
            from modules.config import secure_dir

            path = _path(list_name, hostname)
            secure_dir(os.path.dirname(path))
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                # Not holder(): that takes _mu, which this thread holds, and
                # the first version deadlocked here (found by the cross-process
                # test, which hung rather than failed).
                raise DeviceBusy(_read_holder_file(path, hostname)) from None
            # A record left in the file means the last holder's process ENDED while it
            # held the device (release empties it first). Kept before it is overwritten:
            # it is the only trace of an operation that did not finish (R5).
            size = os.fstat(fd).st_size
            if size:
                text = os.pread(fd, size, 0).decode("utf-8", "replace")
                if text.strip():
                    try:
                        left = json.loads(text)
                    except ValueError:
                        left = {}
                    _record_interrupted(list_name, hostname,
                                        left if isinstance(left, dict) else {},
                                        operation, actor)
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps(info).encode("utf-8"))
            os.fsync(fd)
        _held[key] = {"fd": fd, "count": 1, "thread": me, "holder": info}
    log.info("device_ops: %s held for %s by %s%s", hostname, operation, actor,
             f" ({detail})" if detail else "")


def release(list_name: str, hostname: str) -> None:
    key = (list_name.lower(), hostname)
    with _mu:
        mine = _held.get(key)
        if not mine or mine["thread"] != threading.get_ident():
            return
        mine["count"] -= 1
        if mine["count"] > 0:
            return
        _held.pop(key, None)
        fd = mine["fd"]
    if fd is not None:
        import fcntl

        try:
            os.ftruncate(fd, 0)
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    log.info("device_ops: %s released after %s", hostname, mine["holder"]["operation"])
    _announce_released()


def _announce_released() -> None:
    """Tell open pages a device's hold ended (`device_holds`), so a card refused because
    another operation held its device reads again (the device-actions mockup, signed off
    2026-10-02: "this preview reads again when it finishes"). Only the app's own process can
    announce: a hold released by a host script is not heard, and the card says so and offers
    Preview it again."""
    try:
        from modules import invalidation
        invalidation.announce(["device_holds"], "device-ops", True)
    except RuntimeError:
        pass                              # no emitter: a script's process; nobody to tell
    except Exception:                     # noqa: BLE001 - a release never fails on telling
        log.warning("device_ops: the release could not be announced", exc_info=True)


def note(step: str) -> None:
    """Record progress on every device THIS thread holds: the step it is on,
    and when. It is what lets a refusal say "last progress: verify, 20 s ago"
    rather than only when the hold began."""
    me, now = threading.get_ident(), time.time()
    with _mu:
        mine = [info for info in _held.values() if info["thread"] == me]
        for info in mine:
            info["holder"]["progress"] = {"step": step, "at": now}
            if info["fd"] is not None:
                try:
                    os.ftruncate(info["fd"], 0)
                    os.pwrite(info["fd"], json.dumps(info["holder"]).encode("utf-8"), 0)
                except OSError:
                    log.debug("device_ops: progress not written", exc_info=True)


def may_write(ip: str) -> bool:
    """Whether THIS thread holds the device at *ip* (a hold that has not said
    its address covers this thread's sessions: onboarding learns a DHCP
    device's address inside its own hold)."""
    me = threading.get_ident()
    with _mu:
        return any(info["thread"] == me and (not info["holder"].get("ip")
                                             or info["holder"]["ip"] == ip)
                   for info in _held.values())


@contextlib.contextmanager
def hold(list_name: str, hostname: str, operation: str, actor: str, detail: str = "",
         ip: str = ""):
    """``with hold(...)``: the device for the block, released however it ends."""
    acquire(list_name, hostname, operation, actor, detail, ip)
    try:
        yield
    finally:
        release(list_name, hostname)


def hold_device(dev: dict, operation: str, detail: str = ""):
    """A request's hold on one device of the ACTIVE list, as the verified
    person: for the Device page's own actions, which act on the list the
    page shows. Found by scanning every command string the program sends
    through the read-only allowlist (C101): upload, delete and download a
    file, and save to startup, each wrote without holding the device."""
    from modules import identity
    from modules.config import get_current_list_name

    return hold(get_current_list_name(), dev.get("hostname", ""), operation,
                identity.request_actor(), detail=detail, ip=dev.get("ip", ""))


def acquire_many(list_name: str, hostnames: list, operation: str, actor: str,
                 detail: str = "", ips: dict = None) -> tuple:
    """Hold each device a batch targets. ``(held, refused)``: *refused* are
    batch rows naming the holder, so a busy device is refused ALONE and the
    rest proceed, the way a device whose program moved already is."""
    held, refused = [], []
    for host in hostnames:
        try:
            acquire(list_name, host, operation, actor, detail, (ips or {}).get(host, ""))
            held.append(host)
        except DeviceBusy as exc:
            refused.append({"device": host, "outcome": "refused", "reason": str(exc),
                            "held_by": exc.holder})
    return held, refused


def release_many(list_name: str, hostnames: list) -> None:
    for host in hostnames:
        release(list_name, host)
