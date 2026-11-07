"""A network's controller app runtime, as measured (the operator's decisions, 2026-11-07): the
Python its controller runs apps on, which `mercury app check` targets
(`modules/apps/python_versions.py`), recorded per network with where it came from. Never a
constant, never a default: a network whose record holds none has none, and the app check says
"can't tell" and fails.

**Where it is kept, and why there.** One file per network, `controller_runtime.json` in the
network's folder (where the network's other SDN stores are: `flow_intent.jsonl`,
`sdn_mode.jsonl`), each network's own and never Default's:
- it is a MEASUREMENT of the controller host (capability discovery's kind of record, the SDN
  design's E), so not a setting (the design's settings placement rule, 16a: "a value that can
  be NetBox data, a measurement or code is not a setting"), and not NetBox data (NetBox holds
  the controller host and its intent, not what its interpreter answered);
- not in the network's configuration repository, where E keeps its per-device records: the app
  gate is code apart from state and never reads that repository (the SDN design revision 7,
  11c.4, T25);
- not on a controller connection (`sdn_controllers`, `connections.py`): those are the
  northbound REST connections a person saves on a card, and nothing a person types may stand
  in for what the host answered.

**What it holds** (`record_python`'s write): ``{"python": {"version": "3.5", "answer": "Python
3.5.2", "read": <the command>, "host": <the controller host>, "at": <when it answered>, "by":
<the run or person that recorded it>, "provisional": bool, "note": <why provisional>,
"recorded_at": <Mercury's clock>}, "change": {...} or absent, "rechecked": {...} or absent}``.
The version is the MINOR, derived from the answer, never typed.
- **Measured** (`provisional` false): the read is the Linux host capture list's interpreter read
  (`discovery.PYTHON_READ`, `/opt/<folder>/bin/python --version`, the app runtime's own
  interpreter, which may differ from the host's `python3`), and `at` a UTC time.
- **Provisional** (the operator, 2026-11-07: a value to check against until the interpreter
  read runs): the read is whatever command answered (an earlier capture's `python3 --version`),
  the note says why it is provisional, and `at` may be a date when the capture kept no time.
  The app check targets it and says so, marked provisional. A provisional value never replaces
  a measured one.
- **A change** (`change`): a value replaced by one of ANOTHER minor version (a measurement
  replacing the provisional value, or a later measurement) is recorded with both, their
  sources, and when; the apps checked against the old one were checked against the wrong
  version, so `attention.controller_python_source` draws a row until the network's apps are
  re-checked against the new one (`record_recheck`) or a person acknowledges the change. The
  same minor replacing it records no change.

**Who writes it:** the controller host's read (the inventory entry's host kind, the SDN design's
9a, P1b; its capture list already declares the command) records a measurement; a provisional
value is recorded by the operator (no v2 control yet). Nothing here dials a host. Each write
holds the store's cross-process lock across its read and its write, replaces the file
atomically, owner-only, refuses on a store it cannot read, and announces `sdn` where the
process can (a write outside the app's process is read at the page's next read).
"""

import json
import logging
import os
import re
import time

from modules.apps import python_versions as versions

log = logging.getLogger(__name__)

FILE_NAME = "controller_runtime.json"
_AT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
LIMIT = 255
NOTE_LIMIT = 500
#: The data key a write announces (`modules/invalidation.VOCABULARY`).
ANNOUNCE_KEYS = ("sdn",)


class RuntimeRefused(ValueError):
    """A measurement that cannot be recorded, in words naming why."""


def _path(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), FILE_NAME)


def read(network: str) -> dict:
    """*network*'s record: ``{"state": "measured"|"provisional"|"absent"|"unreadable",
    "python": {...} or None, "change": {...} or None, "rechecked": {...} or None, "error"}``.
    Absent (nothing recorded) and unreadable are different answers. Writes nothing and makes
    no folder."""
    out = {"state": "unreadable", "python": None, "change": None, "rechecked": None,
           "error": ""}
    if not network:
        return dict(out, error="no network was named")
    path = _path(network)
    if not os.path.exists(path):
        return dict(out, state="absent")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        log.error("controller_runtime: %s's record is unreadable (%s)", network,
                  type(exc).__name__)
        return dict(out, error=f"{FILE_NAME} could not be read ({type(exc).__name__})")
    if not isinstance(data, dict):
        return dict(out, error=f"{FILE_NAME} holds {type(data).__name__}, not the record's "
                               "object")
    python = data.get("python")
    if python is None:
        return dict(out, state="absent")
    if not isinstance(python, dict) or not _version(python.get("version")):
        return dict(out, error=f"{FILE_NAME}'s python holds no version of the shape "
                               "3.<minor>")
    change = data.get("change") if isinstance(data.get("change"), dict) else None
    rechecked = data.get("rechecked") if isinstance(data.get("rechecked"), dict) else None
    return dict(out, state="provisional" if python.get("provisional") else "measured",
                python=dict(python), change=change, rechecked=rechecked)


def _version(value):
    match = re.fullmatch(r"(\d+)\.(\d+)", str(value or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


def source_words(p: dict) -> str:
    """Where a recorded value came from, in a person's words, provisional said first."""
    how = (f"`{p.get('read', '')}` on {p.get('host', '')} at {p.get('at', '')} (it answered "
           f"{p.get('answer', '')!r})")
    if p.get("provisional"):
        from modules.discovery import PYTHON_READ
        return (f"PROVISIONAL: {p.get('note', '')}; {how}; not yet measured by the "
                f"interpreter read ({PYTHON_READ})")
    return f"measured by {how}"


def target(network: str) -> versions.Target:
    """What `mercury app check --network <network>` checks against: the recorded minor
    version with its provenance (a provisional one marked so), or "can't tell" naming why
    (nothing recorded, or unreadable)."""
    got = read(network)
    if got["state"] == "absent":
        return versions.not_measured(network)
    if got["state"] == "unreadable":
        return versions.Target(None, f"can't tell: the controller's Python for {network or '?'} "
                                     f"cannot be read ({got['error']})")
    p = got["python"]
    return versions.Target(_version(p["version"]),
                           f"Python {p['version']} on {network}'s controller, "
                           f"{source_words(p)}", provisional=bool(p.get("provisional")))


def _text(name: str, value, limit: int = LIMIT) -> str:
    text = str(value or "").strip()
    if not text:
        raise RuntimeRefused(f"{name} is empty: a measurement names its {name}")
    if len(text) > limit or not text.isprintable():
        raise RuntimeRefused(f"{name} is not one printable line of at most {limit} characters")
    return text


def _announce(by: str) -> bool:
    from modules import invalidation

    try:
        invalidation.announce(list(ANNOUNCE_KEYS), by)
        return True
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.info("controller_runtime: not announced (%s): the page reads it at its next read",
                 type(exc).__name__)
        return False


def _write(network: str, change):
    """Read-modify-write *network*'s record under its lock: ``change(data)`` edits the
    record's object in place (raising to refuse)."""
    from modules import config
    from modules.filestore import PathLock, StoreUnreadable, read_json_for_write, write_atomic

    folder = config.get_list_data_dir(network)
    if not os.path.isdir(folder):
        raise RuntimeRefused(f"{network} has no folder (a deleted network's is never made "
                             "again), so nothing was recorded")
    path = os.path.join(folder, FILE_NAME)
    with PathLock(lambda: path):
        try:
            data = read_json_for_write(path)
        except StoreUnreadable as exc:
            raise RuntimeRefused(f"{network}'s {FILE_NAME} cannot be read ({exc})") from exc
        if not isinstance(data, dict):
            raise RuntimeRefused(f"{network}'s {FILE_NAME} holds {type(data).__name__}, not "
                                 "the record's object, so nothing was recorded")
        change(data)
        write_atomic(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def record_python(network: str, *, answer: str, read_command: str, host: str, at: str,
                  by: str, provisional: bool = False, note: str = "") -> dict:
    """Record what *network*'s controller app runtime answered to *read_command* on *host*
    at *at* (the read's own time), recorded by *by*: the minor version derived from *answer*
    (`Python 3.5.2` is 3.5). Measured unless *provisional* (see the module's docstring), which
    needs a *note* saying why. Refused, naming the comparison and both operands: an empty
    network; a measurement whose read is not the interpreter read or whose time is not UTC; a
    provisional value without its note, or over a measured value; an answer not of the
    `--version` shape or not Python 3; a store that cannot be read. Returns ``{"python": the
    value written, "change": the change recorded or None, "announced": bool}``."""
    from modules import discovery

    if not network:
        raise RuntimeRefused("no network was named: a measurement is recorded for its network")
    command = _text("read", read_command)
    if not provisional and not discovery.is_python_read(command):
        raise RuntimeRefused(f"the read {command!r} is not the interpreter read "
                             f"({discovery.PYTHON_READ}), so it cannot say which Python the "
                             "controller runs apps on (an earlier capture's answer is "
                             "recorded as provisional, with its note)")
    shown = _text("answer", answer)
    parsed = versions.parse_answer(shown)
    if parsed is None:
        raise RuntimeRefused(f"the answer {shown[:80]!r} is not an interpreter's version "
                             "(`Python <major>.<minor>[.<patch>]`)")
    if parsed[0] != 3:
        raise RuntimeRefused(f"the answer {shown!r} is Python {parsed[0]}, and an app is "
                             "checked against Python 3 only")
    when = _text("at", at)
    if not (_AT.match(when) or (provisional and _DATE.match(when))):
        raise RuntimeRefused(f"at {when!r} is not a UTC time of the shape YYYY-MM-DDTHH:MM:SSZ"
                             + (" or a date, YYYY-MM-DD" if provisional else ""))
    row = {"version": f"{parsed[0]}.{parsed[1]}", "answer": shown, "read": command,
           "host": _text("host", host), "at": when, "by": _text("by", by),
           "provisional": bool(provisional), "recorded_at": _now()}
    if provisional:
        row["note"] = _text("note", note, NOTE_LIMIT)
    out = {"python": row, "change": None}

    def change(data):
        before = data.get("python") if isinstance(data.get("python"), dict) else None
        if provisional and before and not before.get("provisional"):
            raise RuntimeRefused(f"{network}'s controller Python is measured "
                                 f"({before.get('version')}, {source_words(before)}), and a "
                                 "provisional value never replaces a measurement")
        if before and before.get("version") != row["version"]:
            out["change"] = {"id": f"{row['recorded_at']}:{before.get('version')}->"
                                   f"{row['version']}",
                             "at": row["recorded_at"], "from": dict(before), "to": dict(row)}
            data["change"] = out["change"]
        data["python"] = row

    _write(network, change)
    log.info("controller_runtime: %s's controller runs Python %s (%s, recorded by %s)",
             network, row["version"], "provisional" if provisional else "measured", row["by"])
    out["announced"] = _announce(f"controller-runtime:{row['by']}")
    return out


def record_recheck(network: str, *, version: str, by: str) -> dict:
    """Record that *network*'s apps were checked against Python *version* (``3.5``), by *by*:
    the check of the network's registered apps calls this (the registry's, P4). Refused unless
    *version* is the network's recorded version, since a check against another version
    re-checks nothing. Clears the change's row (`attention.controller_python_source`)."""
    if not network:
        raise RuntimeRefused("no network was named: a re-check is recorded for its network")
    who = _text("by", by)
    recheck = {"version": _text("version", version), "at": _now(), "by": who}

    def change(data):
        current = (data.get("python") or {}).get("version") if isinstance(
            data.get("python"), dict) else None
        if current != recheck["version"]:
            raise RuntimeRefused(f"the re-check was against Python {recheck['version']}, and "
                                 f"{network}'s controller Python is "
                                 f"{current or 'not recorded'}: a re-check is against the "
                                 "recorded version")
        data["rechecked"] = recheck

    _write(network, change)
    return {"rechecked": recheck, "announced": _announce(f"controller-runtime:{who}")}


def unresolved_change(got: dict):
    """The record's change still owed a re-check (*got* is `read`'s answer), or None: a change
    whose re-check, against the version now recorded, came at or after it, is resolved."""
    change = got.get("change")
    if not change or got.get("state") not in ("measured", "provisional"):
        return None
    rechecked = got.get("rechecked") or {}
    if rechecked.get("version") == (got.get("python") or {}).get("version") \
            and str(rechecked.get("at") or "") >= str(change.get("at") or ""):
        return None
    return change
