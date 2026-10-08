"""The reads engine: one way to ask devices read-only commands (NSOT_READS.md, section 2).

Signed off 2026-10-08 (the design and boards A to E, decisions R1 to R5). ONE engine, two users
(NSOT_PLAN 8.16): a person, through Ask the device (one device, its page's tab) and Show
commands (many devices, OBSERVE), and the Stage 8 agent, which opens no session of its own.

A run, in order, and nothing out of it:

1. **Refuse first** (`refusal`): every command through the read-only allowlist, whole
   (`readonly_commands`); `show tech-support` across more than one device (R1); no command, or
   more than `MAX_COMMANDS`. A refused run asks no device, and is still recorded.
2. **Each device held while it is read** (`device_ops.hold`, operation `read`): a device another
   operation holds is SKIPPED, named with its holder, never queued; while a read holds it, a
   deploy is refused naming the read and its person.
3. **Read through the one sender** (`commands.run_device_command` on a session `open_ssh`
   opened), each command bounded by the deploy path's read timeout; a failure is that device's
   (or that command's), named, never a partial answer drawn as whole.
4. **Masked** (`redact.redact_text`, the installation's values resolved once per run), then
   **capped** at the network's measured size (`reads_answer_cap_kib`): a capped answer says so,
   `cut`, with the SHA-256 of the whole masked answer, so two answers compare even when cut.
5. **Concurrent across devices, bounded** (`fanout.read_each`, `reads_max_workers`, R1).
6. **Recorded**, at its start and at its end: who (a person, or "the agent, for <person>"), when,
   the network, the commands, each device's outcome and its masked answers. One file per run,
   replaced atomically, read by History.

Retention (R2): answers are kept `reads_retention_days`, then MOVED to the network's S3/MinIO
archive (`expire`), never deleted; who, when and what are kept for good. Where no archive is
configured the answers stay, and `expire` says why (measured on the host 2026-10-08: none
configured, the SDK not installed).
"""

import hashlib
import json
import logging
import os
import re
import time
import uuid

log = logging.getLogger(__name__)

#: How often a running run's record is rewritten and announced as devices land.
PROGRESS_SECONDS = 2.0


def _announce() -> None:
    try:
        from modules import invalidation
        invalidation.announce(("reads",), by="show-commands", ok=True)
    except Exception:                                 # noqa: BLE001 (a page's progress only)
        log.debug("reads: a progress announcement failed", exc_info=True)


#: The run's steps, in order, as the manual names them (how-it-works/show-commands.md).
STEPS = ("refuse", "hold", "read", "mask", "cap", "record")

#: Commands in one run: a person's list, or a saved set's. A longer list is a script, not a read.
MAX_COMMANDS = 10

#: Defaults of the three network settings, each with its measurement (SETTINGS.md).
#: 32 KiB: about three times the largest answer measured, a 9,972-byte running configuration
#: (the nine goldens read 2026-10-08: 4,408 to 9,972 bytes; `show ip interface`, the largest
#: captured show, 8,143 bytes).
CAP_KIB = 32
#: 6 at once: the drift check's load, the one measured on these devices: it reads six full
#: running configurations at once every 30 minutes, and read all nine in 47 s and 55 s
#: (02:18 and 02:49 UTC, 2026-10-08), s3 included, every one clean.
MAX_WORKERS = 6
RETENTION_DAYS = 30

#: Commands that load a device or answer at length (R1's warning), by their full words; a
#: command matches when each of its words is a prefix of these (IOS abbreviations: `sh tech`).
#: `show tech-support` is also REFUSED across devices.
HEAVY = {
    ("show", "tech-support"): "runs for minutes and loads the device's CPU",
    ("show", "running-config", "all"): "every default line as well: several times a config's size",
    ("show", "logging"): "the whole log buffer; narrow it with | include",
    ("show", "ip", "bgp"): "the whole BGP table on a router that carries one",
    ("show", "mac", "address-table"): "every learned address on a busy switch",
}
FLEET_REFUSED = (("show", "tech-support"),)

#: The words a device's outcome is drawn with.
ANSWERED, FAILED, SKIPPED, UNKNOWN = "answered", "failed", "skipped", "unknown"


class Refused(ValueError):
    """The run asks no device; the message names why."""


def _words(command: str) -> list:
    return command.split("|", 1)[0].split()


def matches(command: str, words: tuple) -> bool:
    """True when *command*'s words (before any `|`) abbreviate *words*, in order."""
    got = [w.lower() for w in _words(command)]
    if len(got) < len(words):
        return False
    return all(len(g) >= 2 and w.startswith(g) or g == w for g, w in zip(got, words))


def refusal(commands: list, n_devices: int) -> str:
    """``""`` when the run may ask its devices, else why (the comparison and its operands)."""
    from modules.readonly_commands import refusal as one

    commands = [c for c in (commands or [])]
    if not commands:
        return "Refused: no command to run."
    if len(commands) > MAX_COMMANDS:
        return (f"Refused: {len(commands)} commands; a run asks at most {MAX_COMMANDS} "
                "(a longer list is a script, not a read).")
    for c in commands:
        why = one(c)
        if why:
            return f"`{c[:120]}`: {why}"
    if n_devices > 1:
        for c in commands:
            for words in FLEET_REFUSED:
                if matches(c, words):
                    return (f"Refused: `{c}` on {n_devices} devices; {HEAVY[words]}, so it is "
                            "asked of one device, on its page.")
    return ""


def warnings(commands: list, weak: dict = None) -> list:
    """The heavy-command warning (R1): ``[{"command"|"device", "why"}]`` to name at the confirm.
    *weak* is ``{device: why}`` for devices a measurement shows are loaded; no reader measures
    device CPU yet, so callers pass none (NSOT_READS.md section 8, R1)."""
    out = []
    for c in commands or []:
        for words, why in HEAVY.items():
            if matches(c, words):
                out.append({"command": c, "why": why})
                break
    for device, why in sorted((weak or {}).items()):
        out.append({"device": device, "why": why})
    return out


# --------------------------------------------------------------------------- settings

def _setting(list_name: str, key: str, default: int) -> int:
    from modules import list_settings
    try:
        return int(list_settings.value(list_name, key, default) or default)
    except (TypeError, ValueError):
        return default


def cap_bytes(list_name: str) -> int:
    return max(1, _setting(list_name, "reads_answer_cap_kib", CAP_KIB)) * 1024


def max_workers(list_name: str) -> int:
    return max(1, min(16, _setting(list_name, "reads_max_workers", MAX_WORKERS)))


def retention_days(list_name: str) -> int:
    return max(1, _setting(list_name, "reads_retention_days", RETENTION_DAYS))


# --------------------------------------------------------------------------- the record

def _dir(list_name: str) -> str:
    from modules import config
    return os.path.join(config.get_list_data_dir(list_name), "reads")


def _path(list_name: str, run_id: str) -> str:
    if not re.fullmatch(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}", run_id or ""):
        raise ValueError(f"not a run id: {run_id!r}")
    return os.path.join(_dir(list_name), f"{run_id}.json")


def _write(list_name: str, record: dict) -> None:
    from modules.filestore import write_atomic
    os.makedirs(_dir(list_name), exist_ok=True)
    write_atomic(_path(list_name, record["id"]), json.dumps(record, indent=1, sort_keys=True))


def actor_words(record: dict) -> str:
    """Who ran it, as History says it: a person, or the agent for a person."""
    if record.get("by") == "agent":
        return f"the agent, for {record.get('actor') or 'nobody named'}"
    return record.get("actor") or "unknown"


def get(list_name: str, run_id: str):
    """One run's record, or None when the network holds none by that id."""
    try:
        with open(_path(list_name, run_id), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


def runs(list_name: str, device: str = "", actor: str = "", limit: int = 50,
         data_dir: str = "") -> dict:
    """``{"runs": [...newest first], "unreadable": [names]}``: an unreadable file is named,
    never skipped in silence (a subset says so). *data_dir* is the network's directory when the
    caller holds its ref (History): read from it, nothing is created."""
    out, bad = [], []
    folder = os.path.join(data_dir, "reads") if data_dir else _dir(list_name)
    try:
        names = sorted(os.listdir(folder), reverse=True)
    except FileNotFoundError:
        names = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                r = json.load(fh)
        except (OSError, ValueError):
            bad.append(name)
            continue
        if device and device not in (r.get("devices") or []):
            continue
        if actor and actor != r.get("actor"):
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return {"runs": out, "unreadable": bad}


# --------------------------------------------------------------------------- the run

def _answer(conn, command: str, values: dict, cap: int) -> dict:
    from modules.commands import run_device_command
    from modules.redact import redact_text

    started = time.time()
    try:
        raw = run_device_command(conn, command) or ""
    except Exception as exc:                          # noqa: BLE001 (the command's failure)
        from modules.utils import error_text
        return {"command": command, "state": FAILED,
                "why": redact_text(error_text(exc), values)[:400],
                "took_s": round(time.time() - started, 2)}
    masked = redact_text(raw, values)
    data = masked.encode("utf-8")
    kept = data[:cap].decode("utf-8", errors="ignore") if len(data) > cap else masked
    return {"command": command, "state": ANSWERED, "answer": kept, "bytes": len(data),
            "cut": len(data) > cap, "sha256": hashlib.sha256(data).hexdigest(),
            "took_s": round(time.time() - started, 2)}


def new_id(now: float = None) -> str:
    """A run's id: its UTC start to the microsecond, then 32 hex characters, so ids sort by
    time even for two runs in one second (the random part decided their order before)."""
    now = time.time() if now is None else now
    micro = min(999999, int((now - int(now)) * 1e6))      # truncated: never wraps the second
    return (time.strftime("%Y%m%dT%H%M%S", time.gmtime(now)) + f"{micro:06d}Z-"
            + uuid.uuid4().hex)


def run(list_name: str, hosts: list, commands: list, actor: str, *, by: str = "person",
        purpose: str = "", progress=None, session=None, run_id: str = "") -> dict:
    """Ask *hosts* of *list_name* each of *commands*; the run's record (also written).

    *by* is ``person`` or ``agent`` (*actor* is then the person it acts for). *progress* is
    called with each device's outcome as it lands. *session* (tests) replaces
    ``connection.with_temp_connection``. Raises `Refused` with nothing asked; the refusal
    is recorded first."""
    from modules import fanout
    from modules.nsot import device_ops
    from modules.redact import known_secret_values

    hosts = list(dict.fromkeys(h for h in (hosts or []) if h))
    commands = [c.strip() for c in (commands or []) if c and c.strip()]
    started = time.time()
    run_id = run_id or new_id(started)
    record = {"id": run_id, "list": list_name, "actor": actor, "by": by, "purpose": purpose,
              "started_at": started, "finished_at": None, "state": "running",
              "commands": commands, "devices": hosts, "results": {}, "refused": "",
              "retention": {"days": retention_days(list_name), "archived": None}}
    why = refusal(commands, len(hosts)) or ("" if hosts else "Refused: no device to ask.")
    if why:
        record.update(state="refused", refused=why, finished_at=time.time())
        _write(list_name, record)
        raise Refused(why)
    _write(list_name, record)

    from modules.device import load_saved_devices
    from modules.nsot import listref
    inventory = {d.get("hostname"): d for d in load_saved_devices(listref.resolve(list_name).csv_path)}
    values = known_secret_values()
    cap = cap_bytes(list_name)
    if session is None:
        from modules.connection import with_temp_connection as session
    holder = actor_words(record)
    import threading
    mu, last = threading.Lock(), [0.0]

    def landed(host, out):
        """Each device's outcome into the run's record as it lands; the record written and
        `reads` announced at most every `PROGRESS_SECONDS`, so a page shows "6 of 9" without
        a timer and a fleet of 900 announces a few dozen times, not 900."""
        with mu:
            record["results"][host] = out
            if time.time() - last[0] < PROGRESS_SECONDS:
                return
            last[0] = time.time()
            _write(list_name, record)
        _announce()

    def one(host):
        dev = inventory.get(host)
        if dev is None:
            out = {"state": UNKNOWN, "why": f"{host} is not a device of {list_name}"}
        else:
            t0 = time.time()
            try:
                with device_ops.hold(list_name, host, "read", holder,
                                     detail=f"{len(commands)} command(s)", ip=dev.get("ip", "")):
                    answers = session(dev, lambda conn: [_answer(conn, c, values, cap)
                                                         for c in commands])
                failed = [a for a in answers if a["state"] != ANSWERED]
                out = {"state": FAILED if len(failed) == len(answers) else ANSWERED,
                       "answers": answers, "took_s": round(time.time() - t0, 2)}
            except device_ops.DeviceBusy as exc:
                out = {"state": SKIPPED, "why": str(exc)}
            except Exception as exc:                  # noqa: BLE001 (that device's failure)
                from modules.redact import redact_text
                from modules.utils import error_text
                out = {"state": FAILED, "why": redact_text(error_text(exc), values)[:400],
                       "took_s": round(time.time() - t0, 2)}
        landed(host, out)
        if progress is not None:
            try:
                progress(host, out)
            except Exception:                         # noqa: BLE001 (a page's progress only)
                log.debug("reads: progress callback failed for %s", host, exc_info=True)
        return out

    results = fanout.read_each(one, hosts, name="reads", max_workers=max_workers(list_name))
    for host, got in zip(hosts, results):
        if isinstance(got, fanout.Failed):
            got = {"state": FAILED, "why": str(got)}
        record["results"][host] = got
    record.update(state="done", finished_at=time.time(), summary=summarise(record))
    _write(list_name, record)
    log.info("reads: %s ran %d command(s) on %d device(s) in %s: %s", holder, len(commands),
             len(hosts), list_name, record["summary"]["words"])
    return record


def summarise(record: dict) -> dict:
    """Per device and per command: how many answered, failed, skipped, unknown; per command
    how many DISTINCT answers (by the whole masked answer's SHA-256)."""
    by_state = {}
    for host, r in (record.get("results") or {}).items():
        by_state.setdefault(r.get("state", FAILED), []).append(host)
    per_command = []
    for c in record.get("commands") or []:
        shas, failed = {}, []
        for host, r in (record.get("results") or {}).items():
            a = next((a for a in r.get("answers") or [] if a.get("command") == c), None)
            if a and a.get("state") == ANSWERED:
                shas.setdefault(a["sha256"], []).append(host)
            elif r.get("state") in (ANSWERED, FAILED):
                failed.append(host)
        per_command.append({"command": c, "answered": sum(len(v) for v in shas.values()),
                            "distinct": len(shas), "failed": sorted(failed),
                            "groups": sorted((sorted(v) for v in shas.values()),
                                             key=lambda g: (-len(g), g))})
    n = len(record.get("devices") or [])
    words = ", ".join(f"{len(v)} {k}" for k, v in sorted(by_state.items())) or "nothing"
    return {"devices": n, "by_state": {k: sorted(v) for k, v in by_state.items()},
            "commands": per_command, "words": words}


# --------------------------------------------------------------------------- retention

def expire(list_name: str, now: float = None, archive=None) -> dict:
    """Move answers older than the network's retention to its archive (R2), keeping who, when,
    what, each outcome and each answer's SHA-256 and size. ``{"moved", "kept", "why"}``.

    *archive* is ``put(key, bytes) -> None`` (raises on failure); by default the network's
    S3/MinIO archive, and when none is configured nothing moves and ``why`` says so: the
    answers stay live, never deleted."""
    now = time.time() if now is None else now
    days = retention_days(list_name)
    due = [r for r in runs(list_name, limit=10 ** 6)["runs"]
           if r.get("finished_at") and now - r["finished_at"] > days * 86400
           and not (r.get("retention") or {}).get("archived")
           and any(a.get("answer") for x in (r.get("results") or {}).values()
                   for a in x.get("answers") or [])]
    if not due:
        return {"moved": 0, "kept": 0, "why": ""}
    if archive is None:
        archive, why = _s3_put(list_name)
        if archive is None:
            return {"moved": 0, "kept": len(due), "why": why}
    moved = 0
    for r in due:
        key = f"reads/{list_name}/{r['id']}.json"
        try:
            archive(key, json.dumps(r["results"], sort_keys=True).encode("utf-8"))
        except Exception as exc:                      # noqa: BLE001 (kept, named)
            return {"moved": moved, "kept": len(due) - moved,
                    "why": f"the archive refused {key}: {type(exc).__name__}: {exc}"}
        for x in r["results"].values():
            for a in x.get("answers") or []:
                a.pop("answer", None)
        r["retention"] = {"days": days, "archived": {"at": now, "key": key}}
        _write(list_name, r)
        moved += 1
    return {"moved": moved, "kept": 0, "why": ""}


def _s3_put(list_name: str):
    """``(put, "")`` for the network's S3/MinIO archive, or ``(None, why)``."""
    from modules.integrations.s3_archive import S3ArchiveIntegration
    integration = S3ArchiveIntegration(list_name=list_name)
    if not integration.is_configured():
        return None, (f"{list_name} has no S3/MinIO archive configured, so answers past "
                      "retention stay here, unmoved")
    try:
        import io

        from minio import Minio
    except ImportError:
        return None, "the minio SDK is not installed, so answers past retention stay here"
    from modules import list_settings
    endpoint = integration.url
    client = Minio(endpoint.split("://", 1)[-1],
                   access_key=list_settings.secret(list_name, "s3_access_key"),
                   secret_key=list_settings.secret(list_name, "s3_secret_key"),
                   secure=endpoint.startswith("https://"),
                   region=list_settings.value(list_name, "s3_region", "") or None)
    bucket = list_settings.value(list_name, "s3_bucket", "")
    prefix = (list_settings.value(list_name, "s3_prefix", "") or "").strip("/")

    def put(key, data):
        full = "/".join(filter(None, [prefix, key]))
        client.put_object(bucket, full, io.BytesIO(data), len(data))
    return put, ""


# --------------------------------------------------------------------------- as a job

#: The announcement a finished run makes (`invalidation.ANNOUNCERS`): every page showing a
#: run in progress re-reads it by id, never by a timer.
ANNOUNCE_KEYS = ("reads",)
ANNOUNCER = "show-commands"


def start(list_name: str, hosts: list, commands: list, actor: str, *, by: str = "person",
          purpose: str = "") -> dict:
    """Refuse now, or start the run as a job: {"refused": why} (recorded, nothing asked)
    or {"job": id, "run": id}. A run of one device is a job too: one device's read is
    bounded by the read timeout (120 s), past the edge proxy's 100 s limit on a request."""
    from modules.nsot import capture_job

    hosts = list(dict.fromkeys(h for h in (hosts or []) if h))
    commands = [c.strip() for c in (commands or []) if c and c.strip()]
    run_id = new_id()
    why = refusal(commands, len(hosts)) or ("" if hosts else "Refused: no device to ask.")
    if why:
        try:
            run(list_name, hosts, commands, actor, by=by, purpose=purpose, run_id=run_id)
        except Refused:
            pass
        return {"refused": why, "run": run_id}
    label = (f"{len(commands)} command(s) on " +
             (hosts[0] if len(hosts) == 1 else f"{len(hosts)} devices"))
    job = capture_job.start(list_name, label, actor,
                            lambda job_id: {"run": run(list_name, hosts, commands, actor,
                                                        by=by, purpose=purpose,
                                                        run_id=run_id)["id"]},
                            kind="show commands", announce_keys=ANNOUNCE_KEYS,
                            announcer=ANNOUNCER)
    return {"job": job, "run": run_id}


# --------------------------------------------------------------------------- the device's reads

#: Common reads, offered to pick on Ask the device (board A), the same on IOS and IOS-XE.
COMMON = ("show ip interface brief", "show ip route", "show ip ospf neighbor",
          "show ip bgp summary", "show vrrp brief", "show ntp associations",
          "show archive config differences", "show logging | include %")


def answer_of(record: dict, host: str, command: str):
    """*host*'s answer to *command* in *record*, or None."""
    r = (record or {}).get("results", {}).get(host) or {}
    return next((a for a in r.get("answers") or [] if a.get("command") == command), None)


def previous(list_name: str, host: str, command: str, before_id: str):
    """The latest run before *before_id* in which *host* answered *command*, or None."""
    for r in runs(list_name, device=host, limit=500)["runs"]:
        if r["id"] >= before_id:
            continue
        a = answer_of(r, host, command)
        if a and a.get("state") == ANSWERED and "answer" in a:
            return r
    return None


def compare(old: str, new: str) -> list:
    """[("ctx"|"del"|"add", line)]: the lines that changed between two answers, with
    one line of context, in the answers' order."""
    import difflib
    out = []
    for line in difflib.unified_diff((old or "").splitlines(), (new or "").splitlines(),
                                     lineterm="", n=1):
        if line.startswith(("---", "+++", "@@")):
            continue
        kind = {"-": "del", "+": "add"}.get(line[:1], "ctx")
        out.append((kind, line[1:] if line[:1] in "+- " else line))
    return out
