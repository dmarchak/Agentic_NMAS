"""Device serials, as each device's committed golden states them, and which are SHARED.

The operator, 2026-10-04: every C8000v in the lab (r1, r2, r3, r4, r6) reports one serial,
`license udi pid C8000V sn <one value>`, unchanged across redeploys since 2026-09-20: it is
baked into the virtual image. Two rules follow:

1. A serial is never assumed unique. Anything that matches a device by serial refuses when
   more than one device reports that serial, naming them, rather than take one device for
   another (`netbox_client._existing_device`; ZTP keyed by serial, when it is built).
2. Nothing else keys on the serial: five devices sharing one stay five devices.

A shared serial is INFORMATION in job health (`job_health.serial_rows`): expected for virtual
images that share one, a fault on real hardware, where a serial is unique. The tool cannot
tell the two apart from what it reads, so it says both and acts on neither.
"""

import logging
import re

log = logging.getLogger(__name__)

#: IOS-XE's and IOS's chassis identity line in a running configuration.
SERIAL_LINE = re.compile(r"^license udi pid (?P<pid>\S+) sn (?P<sn>\S+)\s*$", re.M)


def serial_of(config: str) -> str:
    """The serial a configuration states, or ""."""
    m = SERIAL_LINE.search(config or "")
    return m.group("sn") if m else ""


def _lists() -> list:
    """``[(list name, config repo)]`` for every device list."""
    from modules.device import get_device_lists
    from modules.nsot import listref

    out = []
    for item in get_device_lists():
        try:
            ref = listref.resolve(item["name"])
        except Exception as exc:                            # noqa: BLE001
            log.warning("device_serials: list %r could not be resolved: %s", item.get("name"), exc)
            continue
        out.append((ref.name, ref.repo_dir))
    return out


def by_serial(lists: list = None) -> dict:
    """``{serial: [(list, device), ...]}`` from every list's committed goldens. A golden with
    no serial line, or one not committed, is left out."""
    from modules.nsot import repo as _repo

    out = {}
    for list_name, repo_dir in (_lists() if lists is None else lists):
        for entry in _repo.list_goldens(list_name):
            if entry.get("legacy") or not entry.get("rel"):
                continue
            text = _repo.committed_golden(repo_dir, entry["rel"]).get("text") or ""
            sn = serial_of(text)
            if sn:
                out.setdefault(sn, []).append((list_name, entry.get("hostname") or ""))
    return out


def shared(lists: list = None) -> dict:
    """The serials more than one device reports: ``{serial: [(list, device), ...]}``."""
    return {sn: devs for sn, devs in by_serial(lists).items() if len(devs) > 1}


def devices_with(serial: str, lists: list = None) -> list:
    """Every ``(list, device)`` whose golden states *serial*."""
    return by_serial(lists).get(serial, []) if serial else []
