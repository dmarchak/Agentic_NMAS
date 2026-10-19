"""What a platform prints for an interface nobody has configured: a dialect operation (C1383).

A NIC added to a device appears in its running configuration as a block of default lines, and
the device's golden, captured before the NIC existed, lacks the interface entirely. The deploy's
capture guard (`deploy.device_against_capture`, C78) asks this one question of such a block:
**is it this platform's measured default for an interface nobody has configured?** It is a
dialect operation, so it moves onto the multi-vendor platform contract (docs/NSOT_STAGE10_PLAN.md
section 12) as a capability a platform declares, with its measurement.

**Measured, never guessed** (the operator's condition, 2026-10-19): the block is the device's
own print, kept as data in ``interface_defaults.json`` (per dialect and interface type, child
lines exactly and in order), from captures kept as a fixture
(tests/fixtures/operational/interface_defaults/). One line more, one fewer, or one out of order
is not the default. A dialect or interface type with no measured row answers False, so the
guard refuses: measured only for IOS-XE on the C8000v, 17.06.01a, GigabitEthernet, 2026-10-19.
IOS (vIOS) and every other platform have no measurement and answer False.
"""

import json
import logging
import os
import re

log = logging.getLogger(__name__)

MEASURED_FILE = os.path.join(os.path.dirname(__file__), "interface_defaults.json")

#: An interface's type: its name without the unit numbers (``GigabitEthernet`` of
#: ``GigabitEthernet4``). The measurement is per type: a loopback's default block is not a NIC's.
_TYPE = re.compile(r"^([A-Za-z][A-Za-z-]*?)(?=\d)")


def measured() -> dict:
    """``{"state": absent|unreadable|ok, "by_dialect": {dialect: {type: row}}}``. Absent and
    unreadable are different answers, and neither accepts anything."""
    if not os.path.exists(MEASURED_FILE):
        return {"state": "absent", "by_dialect": {}}
    try:
        with open(MEASURED_FILE, encoding="utf-8") as fh:
            doc = json.load(fh)
        return {"state": "ok", "by_dialect": doc.get("by_dialect") or {}}
    except (OSError, ValueError) as exc:
        log.error("interface_defaults: %s could not be read: %s", MEASURED_FILE, exc)
        return {"state": "unreadable", "by_dialect": {}, "error": str(exc)}


def interface_type(interface: str) -> str:
    """*interface*'s type (``GigabitEthernet``), or "" when it has no unit number."""
    match = _TYPE.match((interface or "").strip())
    return match.group(1) if match else ""


def default_block(dialect: str, interface: str) -> list:
    """The measured child lines of an unconfigured *interface* on *dialect*, or ``[]`` when
    that dialect and interface type have no measurement."""
    row = ((measured()["by_dialect"].get((dialect or "").strip()) or {})
           .get(interface_type(interface)) or {})
    return list(row.get("lines") or [])


def unconfigured_interface_default(dialect: str, interface: str, lines) -> bool:
    """Is *lines* (an interface block's child lines, as the device printed them, in order)
    *dialect*'s measured default block for an unconfigured *interface*?

    Exact: every line, in order, indentation included, trailing whitespace aside. False for a
    dialect or interface type with no measurement (everything but IOS-XE GigabitEthernet,
    measured on the C8000v, 17.06.01a, 2026-10-19), and for an empty block."""
    expected = default_block(dialect, interface)
    printed = [(line or "").rstrip() for line in (lines or [])]
    return bool(expected) and printed == expected
