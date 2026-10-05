"""Mask a credential NetBox still holds in a device's stored context (C139).

ONE implementation, two entry points: `scripts/nmas-netbox-mask-context`
(every device the checker flags) and retire (the device it is releasing,
7.3). C95 (a) masks a device's config on its way INTO NetBox, and a
re-import overwrites every copy the import can reach. It cannot reach a
device no list claims: retire keeps the NetBox record by design ("NetBox
records what exists, not what NMAS manages"), and so removes the device from
every path that would correct its data. Measured 2026-09-28 on r5.

- **The population is what NetBox HOLDS**, never a list: a device the
  secret-storage checker's own scan flags. Its pattern is independent of the
  redactor that masks, so the check does not share a source with the fix.
- **The authority is the modification record**: NMAS masks only a context it
  recorded writing itself ("did NMAS write this value", C131, section 16),
  and names any other as somebody's data, left alone.
- It masks with the import's own function (`netbox_client.masked_context`),
  so the result is what an import would have written. A context already
  partly masked is refused: the redactor is not idempotent over its masks.
- After the write it READS NetBox back and runs the checker's scan on what
  NetBox holds: a PATCH answering 200 is evidence about the transport.
"""

import importlib.machinery
import importlib.util
import logging
import os

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENDPOINT = "dcim/devices"


def checker_scan():
    """The secret-storage checker's NetBox scan, loaded from its script: its
    pattern is the one that does not share a source with the redactor."""
    path = os.path.join(ROOT, "scripts", "nmas-check-secret-storage")
    loader = importlib.machinery.SourceFileLoader("nmas_check_secret_storage", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod.scan_netbox_context


def nmas_wrote_context(modified: dict, obj_id: int) -> str:
    """When NMAS last recorded writing this device's `local_context_data`, in
    any list's record, or ``""``. The record is keyed by list, and a retired
    device's list may no longer claim it: the WRITE is what gives authority."""
    last = ""
    for _lst, per in (modified or {}).items():
        if not isinstance(per, dict):
            continue
        for e in per.get(ENDPOINT) or []:
            if (str(e.get("id")) == str(obj_id)
                    and "local_context_data" in (e.get("fields") or {})):
                last = max(last, e.get("at") or "")
    return last


def masked(lcd: dict) -> dict:
    from modules.netbox_client import masked_context

    return masked_context(lcd)


def lines_changed(before: str, after: str) -> int:
    b, a = before.splitlines(), after.splitlines()
    return sum(1 for x, y in zip(b, a) if x != y) + abs(len(b) - len(a))


def plan(devices: list, modified: dict, scan) -> tuple:
    """``(todo, refused)`` from NetBox's devices and the modification record.
    Pure, so it is tested against real shapes without a NetBox."""
    todo, refused = [], []
    flagged = {f["device"]: f for f in scan(devices)["findings"]}
    for d in devices:
        f = flagged.get(d.get("name") or d.get("id"))
        if not f:
            continue
        lcd = d.get("local_context_data") or {}
        wrote = nmas_wrote_context(modified, d["id"])
        if not wrote:
            refused.append((d, f, "Mercury has no record of writing this context, so it "
                               "is somebody's data: named here, not changed"))
            continue
        if "<redacted" in (lcd.get("running_config") or ""):
            refused.append((d, f, "its running config is partly masked already, and "
                               "masking again would change masked lines too: "
                               "re-import it through its list instead"))
            continue
        after = masked(lcd)
        todo.append({"device": d, "finding": f, "after": after, "wrote": wrote,
                     "lines": lines_changed(lcd.get("running_config") or "",
                                            after.get("running_config") or "")})
    return todo, refused


def read_devices(session, base, device: str = "") -> list:
    url = f"{base}/api/{ENDPOINT}/"
    params = {"limit": 200, **({"name": device} if device else {})}
    out = []
    while url:
        r = session.get(url, params=params, timeout=30)
        r.raise_for_status()
        body = r.json()
        out += body.get("results") or []
        url, params = body.get("next"), None
    return out


def describe(f: dict) -> str:
    return (f"unmasked: {', '.join(f['slots']) or '-'}"
            f"{' (the positional redactor also finds one)' if f['positional'] else ''}; "
            f"structured communities with a value: {f['communities']}")


def mask_one(session, base, item: dict, scan) -> dict:
    """Write one planned mask and read NetBox back. ``{"ok", "why"}``: ok only
    when what NetBox HOLDS afterwards has no unmasked credential. The caller
    holds `netbox_guard.for_list(..., authority=...)`."""
    from modules.netbox_client import _nb_patch

    d = item["device"]
    try:
        _nb_patch(session, base, f"{ENDPOINT}/{d['id']}/",
                  {"local_context_data": item["after"]})
    except Exception as exc:                  # noqa: BLE001
        return {"ok": False, "why": f"the write failed: {exc}"}
    try:
        back = read_devices(session, base, d["name"])
    except Exception as exc:                  # noqa: BLE001
        return {"ok": False, "why": f"written, and the read-back failed ({exc}): UNPROVEN"}
    left = scan(back)["findings"]
    if left:
        return {"ok": False, "why": f"written, and NetBox STILL holds: {describe(left[0])}"}
    return {"ok": True, "why": "written; read back, NetBox holds no unmasked credential"}


def assess_device(device: dict, modified: dict = None, scan=None) -> dict:
    """For ONE NetBox device dict: does NetBox hold an unmasked credential for
    it, and may NMAS mask it. ``{"holds", "may", "why", "item"}``. A failed
    read of the record or the scan is ``holds: None``: unknown, never clean."""
    from modules.netbox_guard import read_modified

    try:
        scan = scan or checker_scan()
        if modified is None:
            modified, why = read_modified()
            if modified is None:
                return {"holds": None, "may": False, "item": None,
                        "why": f"the modification record could not be read: {why}"}
        todo, refused = plan([device], modified, scan)
    except Exception as exc:                  # noqa: BLE001
        return {"holds": None, "may": False, "item": None,
                "why": f"the context could not be checked: {type(exc).__name__}: {exc}"}
    if todo:
        t = todo[0]
        return {"holds": True, "may": True, "item": t,
                "why": (f"NetBox holds {describe(t['finding'])}; Mercury wrote this context "
                        f"at {t['wrote']} (modification record), so it may mask it")}
    if refused:
        _d, f, why = refused[0]
        return {"holds": True, "may": False, "item": None,
                "why": f"NetBox holds {describe(f)}; NOT maskable here: {why}"}
    return {"holds": False, "may": False, "item": None,
            "why": "NetBox holds no unmasked credential for it"}
