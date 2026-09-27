"""Register C53, as a JOB: does each device's STARTUP config carry the
credential NMAS holds?

Read-only: two show commands per device, never a save. Its answer changes
silently. A rotation that does not save (every CLI rotation before C53's
fix), a hand change, a device that reloaded: none of them tells anyone. It
was measured twice by hand on 2026-09-27, and the first time it found s1
booting the credential the terminal had exposed (B13).

It asks the DEVICE, so it does not care which lab a device belongs to, or
whether it belongs to one (the `kind: native` half of C50). The results go to
``data/startup_check.json``; `job_health` reads that file and never opens a
session itself, because job health runs on a page load and must not do
per-device work per request.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)


def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, "startup_check.json")


def _inventory():
    """``[(list_name, row)]`` for every device in every list. Never creates a
    list directory (register C51's lesson)."""
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists, load_saved_devices

    out = []
    for item in get_device_lists():
        csv = os.path.join(LISTS_DIR, item["filename"], "devices.csv")
        if os.path.exists(csv):
            out += [(item["name"], row) for row in load_saved_devices(csv)]
    return out


def _check_row(row: dict) -> dict:
    from modules.device import decrypt_field
    from modules.nsot import credential_rotation as cr
    from modules.nsot.onboard import check_startup

    if not row.get("device_type"):
        return {"ok": False, "state": "unknown",
                "detail": "no device_type in the inventory; not guessed"}
    password = decrypt_field(row.get("password", ""))
    if not password:
        return {"ok": False, "state": "unknown", "detail": "no stored credential"}
    return check_startup(row.get("ip", ""), row.get("username", "admin"), password,
                         cr.enable_secret(row), row["device_type"])


def run_check(*, inventory=None, check=None, write=True, clock=time.time) -> dict:
    """Check every device. ``{"at", "devices": [{list, device, state,
    detail}], "counts"}``, written atomically when *write*."""
    rows = inventory() if callable(inventory) else (inventory if inventory is not None
                                                     else _inventory())
    check = check or _check_row
    devices = []
    for list_name, row in rows:
        try:
            got = check(row)
        except Exception as exc:                  # noqa: BLE001
            got = {"state": "unknown", "detail": f"the check raised {type(exc).__name__}: {exc}"}
        devices.append({"list": list_name, "device": row.get("hostname", "?"),
                        "state": got.get("state", "unknown"), "detail": got.get("detail", "")})
    counts = {}
    for d in devices:
        counts[d["state"]] = counts.get(d["state"], 0) + 1
    out = {"at": clock(), "devices": devices, "counts": counts}
    if write:
        from modules.config import open_secure

        tmp = _path() + f".{os.getpid()}.tmp"
        with open_secure(tmp, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, sort_keys=True)
        os.replace(tmp, _path())
    return out


def read_results() -> dict:
    """The last run, or ``{}`` when it has never run. Unreadable RAISES: absent
    and unreadable are different facts."""
    path = _path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
