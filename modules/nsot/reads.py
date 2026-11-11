"""The reads engine: one way to ask devices read-only commands (NSOT_READS.md, section 2).

Signed off 2026-10-08 (the design and boards A to E, decisions R1 to R5). ONE engine, two users
(NSOT_PLAN 8.16): a person, through Ask the device (one device, its page's tab) and Show
commands (many devices, OBSERVE), and the Stage 8 agent, which opens no session of its own.

A run, in order, and nothing out of it:

1. **Refuse first** (`refusal`): every command through the read-only allowlist, whole
   (`readonly_commands`), or a discovery capture list's (`modules/discovery.py`); `show
   tech-support` across more than one device (R1); no command, or more than `MAX_COMMANDS`. A
   refused run asks no device, and is still recorded. Each device is then asked only what its
   own driver's rule allows (`device_refusal`), refused by name before its session opens.
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
   replaced atomically, read by History. A run started as a job (`start`) is recorded at its
   start by the request that started it, before the job's thread exists (C2988): the run's
   page opens with that request's answer, and a record the job wrote first could arrive after
   the page asked for it.

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


#: A failure's reason is kept to this many characters. Nothing reads it but a person: it is
#: drawn on one line of the result (a failed device's row, Ask the device's notice), and a
#: library's failure text can run to pages (Netmiko's sign-in failure lists its common causes).
REASON_MAX = 400


def kept_reason(text: str) -> str:
    """A failure's reason as it is kept and drawn: whole, or its first `REASON_MAX` characters
    and, in place, that it was cut and how much (as a capped answer says, C2990; it was cut
    at 400 characters and said nothing)."""
    text = text or ""
    if len(text) <= REASON_MAX:
        return text
    return (f"{text[:REASON_MAX]} [cut: the first {REASON_MAX} of this reason's {len(text)} "
            f"characters are kept and the last {len(text) - REASON_MAX} were cut]")


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


#: Tier 1's members beyond the reads (`readonly_commands.EXTRAS`) each kind of caller may run
#: (NSOT_READS.md section 11). A person: all of them. The agent: `verify /md5` only, a read of
#: a file; a line in a device's log and the session's settings are a person's to send. A
#: diagnosis runbook (`modules/heal/diagnose.py`, HEAL_TO_INTENT 19.3): none, reads only.
EXTRAS = {"person": ("verify", "send log", "terminal"), "agent": ("verify",),
          "diagnosis": (), "ai_analysis": ()}

#: The caller kinds whose reads sign in with the device's read-only account, never the deploy
#: account, and never escalate (no `enable`): the AI analysis's reads (H28; HEAL_TO_INTENT
#: 19.5, prerequisite 1). A device whose read-only account does not resolve is refused by name
#: before any session opens.
READ_ACCOUNT_KINDS = ("ai_analysis",)


def read_account_for(dev: dict) -> dict:
    """The read-only account *dev* signs in with for a `READ_ACCOUNT_KINDS` read:
    `credentials.resolve_read` on its platform, kind and site."""
    from modules import credentials

    return credentials.resolve_read(role=dev.get("role", ""), site=dev.get("_site", ""),
                                    platform=dev.get("_platform", ""))


def as_read_account(dev: dict, account: dict) -> dict:
    """*dev* signing in as *account* (`read_account_for`'s, ok): its login replaced, sealed in
    the inventory's own shape, its enable secret empty."""
    from modules.inventory.netbox_source import _encrypt_for_shape

    return dict(dev, username=account["username"],
                password=_encrypt_for_shape(account["password"]),
                secret=_encrypt_for_shape(""), _cred_source=account["source"])

#: A reason long enough to allow `send log` at levels 0 to 3 for a person (the operator,
#: 2026-10-08: "three words minimum, like dangerous lines"); recorded with the run.
REASON_WORDS = 3


def extras(by: str, reason: str = "") -> tuple:
    """What Tier 1 allows *by*: a person with a stated reason may also log at levels 0 to 3."""
    from modules.readonly_commands import URGENT_LOG
    allowed = EXTRAS.get(by, ())
    if by == "person" and len((reason or "").split()) >= REASON_WORDS:
        allowed = allowed + (URGENT_LOG,)
    return allowed


def refusal(commands: list, n_devices: int, by: str = "person", reason: str = "",
            drivers=None) -> str:
    """``""`` when the run may ask its devices, else why (the comparison and its operands).

    A command the allowlist refuses passes only when a discovery capture list allows it whole
    (Comware's `display`; `modules/discovery.py`): of one of *drivers* (the devices' drivers,
    when the caller knows them), else of any. Each device is then asked only what its own rule
    allows (`device_refusal`), so such a command never reaches a device of another driver."""
    from modules import discovery
    from modules.readonly_commands import refusal as one

    commands = [c for c in (commands or [])]
    if not commands:
        return "Refused: no command to run."
    if len(commands) > MAX_COMMANDS:
        return (f"Refused: {len(commands)} commands; a run asks at most {MAX_COMMANDS} "
                "(a longer list is a script, not a read).")
    for c in commands:
        why = one(c, extras(by, reason))
        if why and not discovery.listed_on(c, drivers):
            elsewhere = discovery.listed_on(c)
            if elsewhere:
                # A capture list's read, and none of these devices is of that list.
                families = sorted({discovery.DRIVERS[d]["family"] for d in elsewhere})
                why = (f"REFUSED: a read only on a {' or '.join(families)} discovery session "
                       f"({', '.join(elsewhere)}), and the devices' drivers are "
                       f"{', '.join(sorted({str(d) for d in drivers}))}. Nothing was sent.")
            else:
                # On no list, and a near miss of a listed read: the refusal names the listed
                # form it compared with, never only "in no tier" (C2991).
                why = discovery.near_miss(c) or why
            return f"`{c[:120]}`: {why}"
    if n_devices > 1:
        for c in commands:
            for words in FLEET_REFUSED:
                if matches(c, words):
                    return (f"Refused: `{c}` on {n_devices} devices; {HEAVY[words]}, so it is "
                            "asked of one device, on its page.")
    return ""


def device_refusal(driver: str, commands: list, by: str = "person", reason: str = "") -> str:
    """``""`` when a device of *driver* may be asked every one of *commands*, else why: a
    discovery driver by its capture list, every other driver by the read-only allowlist
    (`readonly_commands`, Tier 1's extras for *by*), each command whole."""
    from modules import discovery
    from modules.readonly_commands import refusal as one

    if discovery.is_driver(driver):
        return discovery.refusal(driver, commands)
    for c in commands or []:
        why = discovery.foreign_refusal(driver, c) or one(c, extras(by, reason))
        if why:
            return f"`{c[:120]}`: {why}"
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


#: A run id's one shape: its start time to the millisecond, then 32 hex. The URL converter below
#: is built from it, so a route never meets an id this module would refuse (C785).
RUN_ID = r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}"


def url_converter():
    """A werkzeug converter for `<run_id:...>`: an id of any other shape matches no route, so a
    hand-typed or stale URL answers 404 instead of raising in the view (C785)."""
    from werkzeug.routing import BaseConverter

    class RunIdConverter(BaseConverter):
        regex = RUN_ID
        #: A well-formed id naming no run, for a sweep that builds every rule's URL.
        example = "20261014T" + "0" * 12 + "Z-" + "0" * 32

    return RunIdConverter


def _path(list_name: str, run_id: str) -> str:
    if not re.fullmatch(RUN_ID, run_id or ""):
        raise ValueError(f"not a run id: {run_id!r}")
    return os.path.join(_dir(list_name), f"{run_id}.json")


def _write(list_name: str, record: dict) -> None:
    from modules.filestore import write_atomic
    os.makedirs(_dir(list_name), exist_ok=True)
    write_atomic(_path(list_name, record["id"]), json.dumps(record, indent=1, sort_keys=True))


def annotate(list_name: str, run_id: str, key: str, value) -> dict:
    """Add *key* to a finished run's record: a follow-on step of the same run (the logging
    path's watch, `logging_path`). Its one writer is the job that started the run."""
    record = get(list_name, run_id)
    if record is None:
        raise ValueError(f"{list_name} holds no run {run_id}")
    record[key] = value
    _write(list_name, record)
    _announce()
    return record


def actor_words(record: dict) -> str:
    """Who ran it, as History says it: a person, the agent for a person, or a diagnosis for
    the person or the heal that ran it."""
    if record.get("by") == "agent":
        return f"the agent, for {record.get('actor') or 'nobody named'}"
    if record.get("by") == "diagnosis":
        return f"a diagnosis, for {record.get('actor') or 'nobody named'}"
    if record.get("by") == "heal":
        return f"self-healing's action reads, for {record.get('actor') or 'nobody named'}"
    if record.get("by") == "ai_analysis":
        return (f"the AI analysis, turned on by {record.get('actor') or 'nobody named'}, "
                "as the read-only account")
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

def _answer(conn, command: str, values: dict, cap: int, driver: str = "") -> dict:
    """One command's answer, masked by `redact_text`; on a discovery driver's session
    (`modules/discovery.py`) also by `discovery.mask_lines`, whose rules are not IOS's."""
    from modules.commands import run_device_command
    from modules.discovery import masked

    from modules.readonly_commands import bound_seconds

    started = time.time()
    try:
        # A ping or traceroute waits its own worst case (its arguments, IOS's defaults); every
        # other command the read timeout's bound.
        bound = bound_seconds(command)
        raw = (run_device_command(conn, command, read_timeout=bound) if bound
               else run_device_command(conn, command)) or ""
    except Exception as exc:                          # noqa: BLE001 (the command's failure)
        from modules.utils import error_text
        return {"command": command, "state": FAILED,
                "why": kept_reason(masked(error_text(exc), values, driver)),
                "took_s": round(time.time() - started, 2), "at": round(time.time(), 3)}
    text = masked(raw, values, driver)
    data = text.encode("utf-8")
    kept = data[:cap].decode("utf-8", errors="ignore") if len(data) > cap else text
    return {"command": command, "state": ANSWERED, "answer": kept, "bytes": len(data),
            "cut": len(data) > cap, "sha256": hashlib.sha256(data).hexdigest(),
            "took_s": round(time.time() - started, 2), "at": round(time.time(), 3)}


def new_id(now: float = None) -> str:
    """A run's id: its UTC start to the microsecond, then 32 hex characters, so ids sort by
    time even for two runs in one second (the random part decided their order before)."""
    now = time.time() if now is None else now
    micro = min(999999, int((now - int(now)) * 1e6))      # truncated: never wraps the second
    return (time.strftime("%Y%m%dT%H%M%S", time.gmtime(now)) + f"{micro:06d}Z-"
            + uuid.uuid4().hex)


def begun(list_name: str, run_id: str, hosts: list, commands: list, actor: str, *,
          by: str = "person", purpose: str = "", reason: str = "", drivers: dict = None,
          started: float = None) -> dict:
    """A run's record at its start: who, when, the network, the commands and the devices,
    nothing read yet (`state` ``running``, no result). The one shape `run` fills in and
    `start` writes before its job exists."""
    return {"id": run_id, "list": list_name, "actor": actor, "by": by, "purpose": purpose,
            "reason": (reason or "").strip(),
            "started_at": time.time() if started is None else started, "finished_at": None,
            "state": "running", "commands": list(commands), "devices": list(hosts),
            "results": {}, "refused": "", "drivers": dict(drivers or {}),
            "retention": {"days": retention_days(list_name), "archived": None}}


def begin(list_name: str, run_id: str, hosts: list, commands: list, actor: str, **kw) -> dict:
    """Record a run at its start (`begun`), written before its job's thread exists (C2988).
    The request that starts a job answers with the run's page, and the page reads this record
    by its id: written first by the job, it could land after the page asked, and a run in
    progress was drawn as "No such run", a region that listens for nothing, until a person
    reloaded (on an installation reached over loopback, on every run). The job writes the
    same shape again as it begins (`run`), then each device's outcome as it lands."""
    record = begun(list_name, run_id, hosts, commands, actor, **kw)
    _write(list_name, record)
    return record


def refuse_begun(list_name: str, run_id: str, why: str) -> None:
    """A run recorded at its start (`begin`) whose job then refused before asking any device:
    its record says so, with why, never left as running. A record already ended is kept."""
    record = get(list_name, run_id)
    if record is None or record.get("state") != "running":
        return
    record.update(state="refused", refused=why, finished_at=time.time())
    _write(list_name, record)
    _announce()


def fail(list_name: str, run_id: str, exc: BaseException) -> None:
    """The job running *run_id* raised *exc*: its record says ``failed`` with the reason
    (masked, `kept_reason`), keeping whatever it had read, so the run's page says it failed and
    why, never "running" for ever (every action ends in something readable; a raising work is
    its job's failed state, and the record is what outlives the job). A record already refused
    or failed is kept as it is; a failure to write this one is logged, never raised over the
    work's own."""
    from modules.redact import known_secret_values, redact_text
    from modules.utils import error_text
    try:
        record = get(list_name, run_id)
        if record is None or record.get("state") in ("refused", "failed"):
            return
        record.update(state="failed",
                      failed=kept_reason(redact_text(error_text(exc), known_secret_values())),
                      finished_at=record.get("finished_at") or time.time(),
                      summary=summarise(record))
        _write(list_name, record)
        _announce()
    except Exception:                                 # noqa: BLE001 (the work's own is raised)
        log.exception("reads: run %s failed, and its record could not say so", run_id)


def run(list_name: str, hosts: list, commands: list, actor: str, *, by: str = "person",
        purpose: str = "", progress=None, session=None, run_id: str = "",
        reason: str = "", drivers: dict = None, inline: bool = False) -> dict:
    """Ask *hosts* of *list_name* each of *commands*; the run's record (also written).

    *by* is ``person`` or ``agent`` (*actor* is then the person it acts for). *progress* is
    called with each device's outcome as it lands. *session* (tests) replaces
    ``connection.with_temp_connection``. *drivers* (``{host: netmiko driver}``) opens those
    hosts' sessions with that driver instead of the inventory's, recorded in the run (board
    F4's platform map Test). *inline* asks a run of ONE device in the calling thread (its hold
    is then re-entrant for an operation this thread already holds it for); every other run
    reads concurrently. Raises `Refused` with nothing asked; the refusal is recorded
    first."""
    from modules import fanout
    from modules.nsot import device_ops
    from modules.redact import known_secret_values

    hosts = list(dict.fromkeys(h for h in (hosts or []) if h))
    commands = [c.strip() for c in (commands or []) if c and c.strip()]
    started = time.time()
    run_id = run_id or new_id(started)
    record = begun(list_name, run_id, hosts, commands, actor, by=by, purpose=purpose,
                   reason=reason, drivers=drivers, started=started)
    why = (refusal(commands, len(hosts), by, reason)
           or ("" if hosts else "Refused: no device to ask."))
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
    read_account = by in READ_ACCOUNT_KINDS
    if session is None and read_account:
        # The read-only account signs in and never escalates: no `enable` (H28).
        from modules.connection import with_plain_connection as session
    elif session is None:
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
        if dev is not None and drivers and host in drivers:
            dev = dict(dev, device_type=drivers[host])
        from modules import discovery
        driver = (dev or {}).get("device_type", "")
        account = read_account_for(dev) if (dev is not None and read_account) else None
        if dev is None:
            out = {"state": UNKNOWN, "why": f"{host} is not a device of {list_name}"}
        elif account is not None and not account["ok"]:
            # H28: never read with the deploy account. Refused by name before any session.
            out = {"state": FAILED, "why": (f"no read-only account for {host}: "
                                            f"{account['error']}. Nothing was sent")}
        elif device_refusal(driver, commands, by, reason):
            # Each device is asked only what its own driver's rule allows: a device Mercury
            # has no driver for its capture list, every other the allowlist, so a Comware
            # `display` never reaches an IOS device. Refused before any session opens, naming
            # the command (modules/discovery.py).
            out = {"state": FAILED, "why": device_refusal(driver, commands, by, reason)}
        else:
            t0 = time.time()
            try:
                signed = as_read_account(dev, account) if account is not None else dev
                with device_ops.hold(list_name, host, "read", holder,
                                     detail=f"{len(commands)} command(s)", ip=dev.get("ip", "")):
                    answers = session(signed, lambda conn: [_answer(conn, c, values, cap,
                                                                    driver)
                                                            for c in commands])
                failed = [a for a in answers if a["state"] != ANSWERED]
                out = {"state": FAILED if len(failed) == len(answers) else ANSWERED,
                       "answers": answers, "took_s": round(time.time() - t0, 2)}
                if account is not None:
                    # Who it signed in as: the account's name and the profile it came from,
                    # never its password (History › Reads says "as the read-only account").
                    out["signed_in_as"] = {"username": account["username"],
                                           "source": account["source"]}
                if discovery.is_driver(driver):
                    # Its answers are captures (`discovery.captures`): which driver read them.
                    out["driver"] = driver
            except device_ops.DeviceBusy as exc:
                out = {"state": SKIPPED, "why": str(exc)}
            except Exception as exc:                  # noqa: BLE001 (that device's failure)
                from modules.redact import redact_text
                from modules.utils import error_text
                out = {"state": FAILED, "why": kept_reason(redact_text(error_text(exc), values)),
                       "took_s": round(time.time() - t0, 2)}
        landed(host, out)
        if progress is not None:
            try:
                progress(host, out)
            except Exception:                         # noqa: BLE001 (a page's progress only)
                log.debug("reads: progress callback failed for %s", host, exc_info=True)
        return out

    if inline and len(hosts) == 1:
        # One device asked in the caller's own thread, so an operation that already holds it
        # (its hold is re-entrant in the thread that took it) reads it holding it, never
        # skipped as busy by its own hold (the controller app deploy's confirm, C2765).
        try:
            results = [one(hosts[0])]
        except Exception as exc:                      # noqa: BLE001 (that device's failure)
            results = [fanout.Failed(exc)]
    else:
        results = fanout.read_each(one, hosts, name="reads",
                                   max_workers=max_workers(list_name))
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
    from modules.integrations.s3_archive import Unavailable, archive
    integration = archive(list_name)
    if not integration.is_configured():
        return None, (f"{list_name} has no S3/MinIO archive configured, so answers past "
                      "retention stay here, unmoved")
    try:
        # The archive's one client (TLS verification as set: C355).
        client = integration.client()
    except Unavailable as exc:
        return None, f"{exc}, so answers past retention stay here"

    def put(key, data):
        integration.put(integration.key(key), data, client=client)
    return put, ""


# --------------------------------------------------------------------------- as a job

#: The announcement a finished run makes (`invalidation.ANNOUNCERS`): every page showing a
#: run in progress re-reads it by id, never by a timer.
ANNOUNCE_KEYS = ("reads",)
ANNOUNCER = "show-commands"


def start(list_name: str, hosts: list, commands: list, actor: str, *, by: str = "person",
          purpose: str = "", reason: str = "", drivers: dict = None) -> dict:
    """Refuse now, or start the run as a job: {"refused": why} (recorded, nothing asked)
    or {"job": id, "run": id}. A run of one device is a job too: one device's read is
    bounded by the read timeout (120 s), past the edge proxy's 100 s limit on a request."""
    from modules.nsot import capture_job

    hosts = list(dict.fromkeys(h for h in (hosts or []) if h))
    commands = [c.strip() for c in (commands or []) if c and c.strip()]
    run_id = new_id()
    why = (refusal(commands, len(hosts), by, reason)
           or ("" if hosts else "Refused: no device to ask."))
    if why:
        try:
            run(list_name, hosts, commands, actor, by=by, purpose=purpose, run_id=run_id,
                reason=reason)
        except Refused:
            pass
        return {"refused": why, "run": run_id}
    label = (f"{len(commands)} command(s) on " +
             (hosts[0] if len(hosts) == 1 else f"{len(hosts)} devices"))
    # Recorded at its start, before the job's thread exists (C2988, `begin`).
    begin(list_name, run_id, hosts, commands, actor, by=by, purpose=purpose, reason=reason,
          drivers=drivers)

    def work(job_id):
        try:
            return {"run": run(list_name, hosts, commands, actor, by=by, purpose=purpose,
                               run_id=run_id, reason=reason, drivers=drivers)["id"]}
        except Exception as exc:                      # noqa: BLE001 (recorded, then the job's)
            fail(list_name, run_id, exc)
            raise

    job = capture_job.start(list_name, label, actor, work,
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
