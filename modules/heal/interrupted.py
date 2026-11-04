"""A heal whose job ended before it recorded its outcome, made a visible state (board H, part
H6; docs/HEAL_TO_INTENT.md sections 4 and 9; the finding H4 left: a heal whose job dies
mid-apply left its decision taken and its incident claimed, and nothing showed it).

**The mark** (`Mark`): each heal's act holds an exclusive `flock` on one file per decision
(``heal/running/<decision>.lock``, owner-only), holding who, which device, which process and
when, from BEFORE its decision is taken until AFTER its outcome is recorded: `act.run` takes
it before `decisions.take`, and the job releases it once `decisions.applied` is written (empty
first, then unlock, then the file removed). The kernel releases a `flock` when its process
ends (`device_ops`' and `incidents.HealLock`'s pattern), so the mark is held exactly while the
act's process lives.

**What is interrupted** (`find`, a READ: it writes nothing): a ``heal`` decision, or a
``propose`` decision a person approved (H5), TAKEN, with no ``applied`` row, whose mark is not
held. Its mark file says which way it ended: a record left
(``left``: the process ended while it ran: a restart, an update, a crash) or none (``none``:
its job ended without recording an outcome, having raised, `steplog.record_raised`). The mark
is probed before the decisions are read again, so a heal that finished between the two reads
(its outcome written before its mark is released) is never counted.

**What Mercury does with one** (`reap`, run at each heal pass by `act.run`): Mercury cleans up
after its own operation, so a person is left only the decision. It records the outcome
``interrupted`` (`decisions.applied`), with the last step the step log holds; when the act had
written ``started`` (its program may have been sent, and nothing verified or rolled it back),
it halts the network (guard 14, as a send neither verified nor rolled back does); it closes the
incident, so the device may take a new one; and it writes the ``interrupted`` row to the step
log. Needs attention raises it (`attention.heal_source`, ``heal``/``interrupted``) until a later
decision finds the device at intent, or a person acknowledges it with what they found.

**H5's approved proposal** (`modules/heal/propose.py`) holds the same mark (`hold`, `release`)
from before its take until its outcome is recorded, so an approval whose job ended first is
found and recorded here as a heal's is. A declined proposal records its outcome as it is taken,
so it is never found.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

RUN_DIR = "running"
OUTCOME = "interrupted"

#: The marks this process holds, by (network, decision): released by the job that ran it.
_HELD: dict = {}


class Busy(RuntimeError):
    """The decision's mark is held: its act is running."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def path(network: str, decision_id: str) -> str:
    from modules.heal.incidents import _dir

    safe = "".join(ch for ch in decision_id if ch.isalnum() or ch in "-_")
    if not safe or safe != decision_id:
        raise ValueError(f"{decision_id!r} is not a heal decision's id")
    return os.path.join(_dir(network), RUN_DIR, f"{safe}.lock")


class Mark:
    """One decision's act, held across processes (the module's docstring)."""

    def __init__(self, network: str, decision_id: str, device: str = "", by: str = ""):
        self.network, self.decision, self.device, self.by = network, decision_id, device, by
        self.fd = None

    def acquire(self) -> "Mark":
        import fcntl

        from modules.config import secure_dir

        p = path(self.network, self.decision)
        secure_dir(os.path.dirname(p))
        fd = os.open(p, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise Busy(f"the heal of {self.device or '?'} ({self.decision}) is running in "
                       "another job, so it is not started again") from None
        now = time.time()
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({"decision": self.decision, "device": self.device,
                                 "by": self.by, "pid": os.getpid(), "started": now,
                                 "started_at": _iso(now)}).encode("utf-8"))
        os.fsync(fd)
        self.fd = fd
        return self

    def release(self) -> None:
        """Empty the record, unlock, remove the file: a clean end leaves nothing."""
        import fcntl

        if self.fd is None:
            return
        try:
            os.ftruncate(self.fd, 0)
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None
        try:
            os.unlink(path(self.network, self.decision))
        except FileNotFoundError:
            pass


def hold(network: str, decision_id: str, device: str = "", by: str = "") -> Mark:
    """Take *decision_id*'s mark and keep it for the job that runs it (`release`); `Busy` when
    another job holds it."""
    m = Mark(network, decision_id, device, by).acquire()
    _HELD[(network, decision_id)] = m
    return m


def release(network: str, decision_id: str) -> bool:
    """Release the mark this process holds for *decision_id*; False when it holds none."""
    m = _HELD.pop((network, decision_id), None)
    if m is None:
        return False
    m.release()
    return True


def mark_state(network: str, decision_id: str) -> tuple:
    """``(state, record)``: ``held`` (its act runs, in any process), ``left`` (free, a record
    left: its process ended while it ran) or ``none`` (no record). A READ: it creates nothing.
    A mark that cannot be opened raises: never read as nothing."""
    import fcntl

    p = path(network, decision_id)
    try:
        fd = os.open(p, os.O_RDONLY)
    except FileNotFoundError:
        return "none", {}
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return "held", {}
        try:
            text = os.read(fd, 1 << 16).decode("utf-8", "replace")
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    if not text.strip():
        return "none", {}
    try:
        record = json.loads(text)
    except ValueError:
        record = {}
    return "left", record if isinstance(record, dict) else {}


#: The decisions an act takes: a heal (H4) and an approved proposal (H5).
TAKEN_OUTCOMES = ("heal", "propose")


def _open_takes(network: str) -> list:
    from modules.heal import decisions

    return [d for d in decisions.decisions(network)
            if d.get("outcome") in TAKEN_OUTCOMES and d.get("taken") and not d.get("applied")]


def find(network: str) -> dict:
    """Every heal of *network* whose job ended before it recorded its outcome: ``{"state":
    "ok"|"unreadable", "found": [decision + {"mark", "left"}], "error"}``. A READ."""
    try:
        taken = _open_takes(network)
    except Exception as exc:
        return {"state": "unreadable", "found": [],
                "error": f"{network}'s heal decisions cannot be read: {exc}"}
    if not taken:
        return {"state": "ok", "found": [], "error": ""}
    marks = {}
    try:
        for d in taken:
            marks[d["id"]] = mark_state(network, d["id"])
    except OSError as exc:
        return {"state": "unreadable", "found": [],
                "error": f"{network}'s heal marks cannot be read: {exc}"}
    ended = [d for d in taken if marks[d["id"]][0] != "held"]
    if not ended:
        return {"state": "ok", "found": [], "error": ""}
    # Read again AFTER the marks: a heal that finished meanwhile wrote its outcome first.
    try:
        still = {d["id"] for d in _open_takes(network)}
    except Exception as exc:
        return {"state": "unreadable", "found": [],
                "error": f"{network}'s heal decisions cannot be read: {exc}"}
    return {"state": "ok", "error": "",
            "found": [dict(d, mark=marks[d["id"]][0], left=marks[d["id"]][1])
                      for d in ended if d["id"] in still]}


def words(network: str, d: dict, log_view: dict) -> str:
    """How one interrupted heal ended, in words: which way its job ended, and the last step
    the step log holds."""
    left = d.get("left") or {}
    if d.get("mark") == "left":
        how = (f"its job's process ({left.get('pid', '?')}) ended while it ran, started "
               f"{left.get('started_at') or 'at an unrecorded time'}: a restart, an update or a "
               "crash")
    elif log_view.get("raised"):
        how = f"its job raised before it recorded an outcome ({log_view['raised']})"
    else:
        how = "its job ended without recording an outcome"
    last = log_view.get("last") or {}
    if log_view.get("state") == "unreadable":
        step = f"the step log cannot be read ({log_view.get('error')})"
    elif last:
        step = (f"the last step recorded was {last.get('step')} ({last.get('result')}: "
                f"{last.get('words')})")
    else:
        step = "no step was recorded"
    sent = ("its program may have been sent, and nothing verified it or rolled it back"
            if log_view.get("started") or log_view.get("state") == "unreadable"
            else "nothing was sent: its act had not reached its apply")
    return f"the heal of {d.get('device')} ({d['id']}) was interrupted: {how}; {step}; {sent}"


def reap(network: str, *, now: float = None, by: str = "heal to intent") -> dict:
    """Record each interrupted heal of *network* (the module's docstring): ``{"reaped":
    [{"decision", "device", "halted", "words"}], "failed": [words]}``. Under the decisions'
    reap lock, across processes, each checked again inside it, so two passes record one."""
    from modules import filestore
    from modules.heal import decisions, incidents, steplog

    now = time.time() if now is None else float(now)
    out = {"reaped": [], "failed": []}
    got = find(network)
    if got["state"] != "ok":
        out["failed"].append(got["error"])
        return out
    if not got["found"]:
        return out
    with filestore.PathLock(decisions.path(network) + ".reap"):
        again = find(network)
        if again["state"] != "ok":
            out["failed"].append(again["error"])
            return out
        for d in again["found"]:
            view = steplog.of_decision(network, d["id"])
            said = words(network, d, view)
            halts = bool(view.get("started")) or view.get("state") == "unreadable"
            try:
                decisions.applied(network, d["id"], OUTCOME, by=f"{by}: the job's end found",
                                  words=said, now=now)
                if halts:
                    decisions.halt(network, guard=14, name="a heal interrupted after it may "
                                                           "have sent",
                                   words=said, operands={"decision": d["id"],
                                                         "device": d.get("device")}, now=now)
                incidents.close(network, d.get("incident"), f"{OUTCOME}: {said} (decision "
                                                            f"{d['id']})", now)
            except Exception as exc:
                log.error("heal: %s's interrupted heal %s was not recorded: %s", network,
                          d["id"], exc)
                out["failed"].append(f"{d.get('device')}: {type(exc).__name__}: {exc}")
                continue
            try:
                steplog.record_interrupted(network, d, said, halted=halts, by=by, now=now)
            except Exception as exc:
                log.error("heal: %s's interrupted heal %s is not in the step log: %s",
                          network, d["id"], exc)
            if d.get("mark") == "left":
                try:
                    os.unlink(path(network, d["id"]))
                except OSError:
                    pass
            log.warning("heal: %s", said)
            out["reaped"].append({"decision": d["id"], "device": d.get("device"),
                                  "halted": halts, "words": said})
    return out
