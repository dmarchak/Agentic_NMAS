"""PERSIST, from the Device page (7.3, C164): save the running config on the
device and read the startup config back.

The operation ``nmas-persist-native`` runs on the host, given a screen. It is
the remedy the worst Needs attention rows name (`not_safe_to_reboot`: the
running config holds the only working credential), and until now no stage had
put it where a person could reach it. The first action added from the other
direction: persist came from a row asking for it.

One implementation, two entry points, as retire: the device-side save and its
read-back are `onboard.persist_on_device` (the ONE save of a startup config,
C53), and the record is `onboard._record_native_persist`, the rotation record
job health's row reads. An operation like every other change: a preview that
reads nothing from the device and says what will happen and what will NOT, a
confirm bound to the plan's hash, the device held while it saves (C98, C101),
and a result drawn from what the device answered.

What it does NOT do, stated on every run: it changes no running configuration,
rotates nothing, and writes no boot file anywhere but the device (a tool
building one elsewhere follows the golden-committed event, C663).
"""

import hashlib
import json
import logging
import time

log = logging.getLogger(__name__)

#: Persist's steps on the one stepper (`device_actions.stepper`'s ``(key, words, waits,
#: names)``): the hold notes "saving" as the save begins and "read_back" as the read-back does
#: (`onboard.persist_on_device`); the record follows, noted by nothing.
STEPS = (("save", "Save to startup", "the device's own save (`write memory`)", ("saving",)),
         ("read_back", "Read back", "the startup config and the running config's accounts",
          ("read_back",)),
         ("record", "Recorded", "the outcome's record", ("record",)))


def result_run(host: str, got: dict) -> dict:
    """Persist's result on the one stepper (`modules.run_stepper`): the stages it reached, with
    their times, finished as its outcome says (persisted: done; the read-back did not carry
    the accounts: the read-back failed; otherwise the stage it stopped in)."""
    from modules import device_actions
    from modules import run_stepper as RS

    trail = got.get("trail") or []
    state = got.get("state", "")
    group = "done" if state == "persisted" else "failed"
    if not trail:
        return RS.card([RS.row(host, group, detail=got.get("detail", ""))],
                       label="Persist", key="persist")
    steps = RS.from_stepper(device_actions.stepper(STEPS, {"trail": trail},
                                                   now=got.get("ended"), starts=True))
    steps = RS.finished(steps, group)
    return RS.card([RS.row(host, group, steps,
                           detail="" if group == "done" else got.get("detail", ""))],
                   label="Persist", key="persist")

#: Each refusal the plan can make, as the gate that draws it: the plan's
#: `refused_by` keys. A key with no gate would be a reason drawn nowhere, and a
#: test holds the two sets equal.
GATES = (
    ("list", "a list of that name exists", "the list is in the registry"),
    ("present", "the device is in this list's inventory",
     "it has an inventory row with its address"),
    ("device_type", "its platform driver is recorded", "the inventory names its device type"),
    ("credential", "the tool holds its credential", "its inventory row carries a password"),
)

NOT_DOING = (
    "its running configuration is not changed: the save copies it to startup as it is",
    "no credential is rotated",
    "no boot file is written anywhere but the device: a tool that builds one elsewhere "
    "follows the golden-committed event, and a persist commits nothing",
    "no golden is committed: the running config is not captured into the record",
)


def _last_check(list_name: str, hostname: str) -> dict:
    """The hourly startup check's last reading for this device (C53's job):
    ``{"state", "detail", "at"}``, or a state saying why there is none.
    Unreadable is its own answer, never "never checked"."""
    from modules.nsot import startup_check

    try:
        results = startup_check.read_results()
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "detail": f"the check's record could not be read ({exc})",
                "at": None}
    for d in (results or {}).get("devices") or []:
        if d.get("list") == list_name and d.get("device") == hostname:
            return {"state": d.get("state", "unknown"), "detail": d.get("detail", ""),
                    "at": results.get("at")}
    return {"state": "never", "at": (results or {}).get("at"),
            "detail": ("the hourly check has not recorded this device"
                       if results else "the hourly check has never run")}


def row_checks(list_name: str, hostname: str, row: dict) -> tuple:
    """``(refused_by, hash)`` for one inventory *row*: the device-side refusals (no driver,
    no credential) and the plan's hash, the ONE computation `plan` and Save (`save_op`)
    share, so the two cannot disagree about a device or bind a different hash."""
    from modules.device import open_stored

    refused = {}
    if not row.get("device_type"):
        refused["device_type"] = (f"{hostname} has no device_type in the inventory, and the "
                                  "driver that saves it is not guessed")
    # Opened by the one reader that names an unopenable value (C410: it raised, a 500).
    password, unopened = open_stored(row)
    if unopened:
        refused["credential"] = unopened
    elif not password:
        refused["credential"] = f"the inventory holds no credential for {hostname}"
    digest = hashlib.sha256(json.dumps({
        "list": list_name, "device": hostname, "ip": row.get("ip", ""),
        "device_type": row.get("device_type", ""),
        "username": row.get("username", "admin")}, sort_keys=True).encode()).hexdigest()[:16]
    return refused, digest


def plan(list_name: str, hostname: str) -> dict:
    """Everything persist would do, what it will not, and why it would refuse.
    Reads only: the registry, the inventory and the check's record. It never
    contacts the device, so a preview is safe to repeat."""
    from modules.device import load_saved_devices
    from modules.nsot.listref import UnknownList, resolve

    out = {"ok": True, "list_name": list_name, "hostname": hostname, "refusals": [],
           "refused_by": {}, "steps": [], "not_doing": list(NOT_DOING)}

    def refuse(key, text):
        out["refusals"].append(text)
        out["refused_by"][key] = text

    row = None
    try:
        ref = resolve(list_name)
        row = next((d for d in load_saved_devices(ref.csv_path)
                    if d.get("hostname") == hostname), None)
    except UnknownList as exc:
        refuse("list", f"no device list named {list_name!r} ({exc})")
    if row is None and "list" not in out["refused_by"]:
        refuse("present", f"{hostname!r} is not in list {list_name!r}'s inventory: a device "
                          "the tool does not manage has nothing to persist from here")
    row = row or {}
    if row:
        for key, text in row_checks(list_name, hostname, row)[0].items():
            refuse(key, text)

    out["ip"] = row.get("ip", "")
    out["device_type"] = row.get("device_type", "")
    # The session driver and the config dialect are different facts
    # (`nsot/platform.py`), drawn apart so neither reads as the other: r2
    # records driver `cisco_ios` and dialect `cisco_iosxe`.
    try:
        from modules.nsot.platform import platform_for_device
        out["dialect"] = platform_for_device(row) if row else ""
    except Exception as exc:                   # noqa: BLE001
        out["dialect"] = f"not resolved ({exc})"
    out["username"] = row.get("username", "admin")
    out["last_check"] = _last_check(list_name, hostname)
    out["steps"] = [
        {"key": "save", "what": f"save {hostname}'s running config to its startup config "
                                "(the device's own save, `write memory`)"},
        {"key": "read_back", "what": "read the startup config back, and the running config's "
                                     "`username` lines: it is persisted only if the startup "
                                     "config carries every one of them, verbatim"},
        {"key": "record", "what": "record the outcome where job health's rotation row reads it, "
                                  "as you, so the row clears only on a read-back that matched"},
    ]
    out["ok"] = not out["refusals"]
    out["hash"] = row_checks(list_name, hostname, row)[1]
    return out


#: Persist's preview read (C886): the job's kind, the key it announces and its announcer
#: (`invalidation.ANNOUNCERS`).
READ_KIND = "persist preview"
READ_KEYS = ("persist_read",)
READ_ANNOUNCER = "persist-read"


def person_lines(lines) -> list:
    """A comparison's `section :: line` entries as a person reads them, masked
    (`redact_text`): a global line alone, a nested one as `section > line`."""
    from modules.redact import redact_text

    return [redact_text(l[4:] if l.startswith(" :: ") else l.replace(" :: ", " > ", 1))
            for l in lines]


def startup_effect(startup: str, running: str, nvram_dir: str = "") -> dict:
    """What saving *running* to startup changes in what the device boots, from the ONE
    comparison of the two, Reload's gate's (`roundtrip.startup_is_running`, C881: startup's
    "Using N bytes" header out, a certificate startup keeps as a file in nvram: the same
    certificate running prints inline when *nvram_dir* lists it). Persist's preview (C886)
    and Adopt's (C913) both draw it.

    ``{"state": "same"|"differs"|"no_startup", "gains": [...], "loses": [...],
    "present": [...], "missing": [...]}``: ``gains`` the lines only running holds (startup
    gains them), ``loses`` those only startup holds (startup loses them), both masked;
    ``present``/``missing`` the certificate pointers whose file `dir nvram:` lists or not."""
    from modules.nsot import roundtrip

    if "startup-config is not present" in (startup or "") or not (startup or "").strip():
        return {"state": "no_startup", "gains": [], "loses": [], "present": [], "missing": []}
    same = roundtrip.startup_is_running(startup, running, nvram_dir or "")
    return {"state": "same" if same.get("equal") else "differs",
            "gains": person_lines(same.get("only_right") or []),
            "loses": person_lines(same.get("only_left") or []),
            "present": [{k: p[k] for k in ("chain", "certificate", "file")}
                        for p in same.get("present") or []],
            "missing": [{k: p[k] for k in ("chain", "certificate", "file")}
                        for p in same.get("missing") or []]}


def read_effect(list_name: str, hostname: str, *, reader=None) -> dict:
    """Persist's preview read (C886): one session reading what *hostname* runs and boots as
    Reload's gate reads them (`reload_op.read_boot_pair`), and `startup_effect` over them.
    Reads only, so it takes no hold. ``startup_effect``'s answer with ``host`` and
    ``read_at``, or ``{"ok": False, "error"}``; *reader* replaces the device read in tests."""
    from modules.connection import with_temp_connection
    from modules.nsot import reload_op

    device = reload_op._device(list_name, hostname)
    if device is None:
        return {"ok": False, "error": f"{hostname} is not in {list_name}'s inventory"}
    try:
        reads = (reader or (lambda d: with_temp_connection(
            d, lambda conn: reload_op.read_boot_pair(conn, hostname))))(device)
    except Exception as exc:                   # noqa: BLE001 (said on the card)
        return {"ok": False, "error": f"{hostname} could not be read: "
                                      f"{type(exc).__name__}: {exc}"}
    out = startup_effect(reads.get("startup", ""), reads.get("running", ""),
                         reads.get("nvram") or "")
    return dict(out, ok=True, host=hostname,
                read_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


def read_effect_start(list_name: str, hostname: str, actor: str) -> str:
    """Persist's preview read as a job (it reads the device): its id; the card's part
    redraws when the job announces `persist_read`."""
    from modules.nsot import capture_job
    from modules.outbound import mask_payload

    return capture_job.start(list_name, f"reading {hostname}'s startup and running "
                                        "configurations for a persist", actor,
                             lambda _j: mask_payload(read_effect(list_name, hostname)),
                             kind=READ_KIND, announce_keys=READ_KEYS,
                             announcer=READ_ANNOUNCER)


def apply(list_name: str, hostname: str, *, actor: str, confirmed_hash: str,
          persist=None, record=None) -> dict:
    """Save and read back the confirmed device, holding it, as *actor*.
    ``{"ok", "state", "detail", "plan"}``. The plan is computed again and a
    different hash refuses with nothing sent."""
    from modules.device import decrypt_field, load_saved_devices
    from modules.nsot import credential_rotation as cr
    from modules.nsot import device_ops, onboard
    from modules.nsot.listref import resolve

    p = plan(list_name, hostname)
    if not p["ok"]:
        return {"ok": False, "state": "refused", "plan": p,
                "detail": "; ".join(p["refusals"]) + ". Nothing was sent."}
    if confirmed_hash != p["hash"]:
        return {"ok": False, "state": "refused", "plan": p,
                "detail": (f"the plan changed since the preview you confirmed "
                           f"({confirmed_hash} -> {p['hash']}): its address, driver or "
                           "account moved. Nothing was sent; preview again.")}
    row = next(d for d in load_saved_devices(resolve(list_name).csv_path)
               if d.get("hostname") == hostname)
    try:
        with device_ops.hold(list_name, hostname, "persist", actor, ip=p["ip"]):
            device_ops.note("saving")
            out = (persist or onboard.persist_on_device)(
                p["ip"], p["username"], decrypt_field(row.get("password", "")),
                cr.enable_secret(row), p["device_type"])
            # The stages it reached, with their times, kept before the hold goes: the result
            # draws them on the one stepper (`STEPS`).
            trail = list((((device_ops.holder(list_name, hostname) or {}).get("progress"))
                          or {}).get("trail") or [])
            ended = time.time()
    except device_ops.DeviceBusy as exc:
        return {"ok": False, "state": "refused", "plan": p,
                "detail": f"{exc}. Nothing was sent."}
    (record or onboard._record_native_persist)(hostname, out, actor, via="device page",
                                               list_name=list_name)
    log.info("persist: %s/%s by %s: %s", list_name, hostname, actor, out.get("state"))
    return {"ok": bool(out.get("ok")), "state": out.get("state", "unknown"),
            "detail": out.get("detail", ""), "plan": p, "trail": trail, "ended": ended}
