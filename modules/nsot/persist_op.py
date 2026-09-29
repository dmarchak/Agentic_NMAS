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
rotates nothing, and writes neither the containerlab startup file nor
Oxidized's router.db (the lab boot file is `nmas-persist-credential`'s chain,
B15).
"""

import hashlib
import json
import logging

log = logging.getLogger(__name__)

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
    "the containerlab startup file and Oxidized's router.db are not written: a lab "
    "redeploy boots that file, and `nmas-persist-credential` runs that chain (B15)",
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


def plan(list_name: str, hostname: str) -> dict:
    """Everything persist would do, what it will not, and why it would refuse.
    Reads only: the registry, the inventory and the check's record. It never
    contacts the device, so a preview is safe to repeat."""
    from modules.device import decrypt_field, load_saved_devices
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
    if row and not row.get("device_type"):
        refuse("device_type", f"{hostname} has no device_type in the inventory, and the "
                              "driver that saves it is not guessed")
    if row and not decrypt_field(row.get("password", "")):
        refuse("credential", f"the inventory holds no credential for {hostname}")

    out["ip"] = row.get("ip", "")
    out["device_type"] = row.get("device_type", "")
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
    out["hash"] = hashlib.sha256(json.dumps({
        "list": list_name, "device": hostname, "ip": out["ip"],
        "device_type": out["device_type"], "username": out["username"]},
        sort_keys=True).encode()).hexdigest()[:16]
    return out


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
    except device_ops.DeviceBusy as exc:
        return {"ok": False, "state": "refused", "plan": p,
                "detail": f"{exc}. Nothing was sent."}
    (record or onboard._record_native_persist)(hostname, out, actor, via="device page")
    log.info("persist: %s/%s by %s: %s", list_name, hostname, actor, out.get("state"))
    return {"ok": bool(out.get("ok")), "state": out.get("state", "unknown"),
            "detail": out.get("detail", ""), "plan": p}
