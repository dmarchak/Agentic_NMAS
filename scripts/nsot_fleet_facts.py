#!/usr/bin/env python3
"""Per-device facts that matter when choosing a deploy target. Read-only.

Answers, from the golden configs and the manifest, the questions asked before
touching anything: which platform, which redundancy protocols are running,
whether the device carries BGP, and whether its platform is configured for
NETCONF. Nothing here opens a session.

Usage::

    python scripts/nsot_fleet_facts.py [list-name]
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.config import get_current_list_name, get_list_data_dir   # noqa: E402
from modules.nsot import manifest as _m                               # noqa: E402

PROTOCOLS = {
    "vrrp": re.compile(r"^\s*vrrp\s", re.M | re.I),
    "hsrp": re.compile(r"^\s*standby\s", re.M | re.I),
    "bgp": re.compile(r"^router bgp\s", re.M | re.I),
    "ospf": re.compile(r"^router ospf\s", re.M | re.I),
    "rip": re.compile(r"^router rip\s", re.M | re.I),
}


def main() -> int:
    list_name = sys.argv[1] if len(sys.argv) > 1 else get_current_list_name()
    repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    devices = _m.load(repo)["devices"]

    from modules.nsot.deploy import transport_for
    from modules.nsot import hostvars

    print(f"\nFleet facts — list '{list_name}'\n")
    header = (f"{'device':<6} {'platform':<13} {'transport':<9} {'intent':<8} "
              f"{'version':<8} protocols")
    print(header)
    print("-" * len(header))

    for entry in sorted(devices.values(), key=lambda e: e.get("name", "")):
        name = entry.get("name", "?")
        path = _m.golden_path_for(repo, entry)
        config = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                config = fh.read()

        running = [key for key, pattern in PROTOCOLS.items()
                   if pattern.search(config)]
        version = ""
        match = re.search(r"^version (\S+)", config, re.M)
        if match:
            version = match.group(1)

        platform = entry.get("platform", "") or "(none)"
        try:
            transport = transport_for(platform)
        except Exception:                      # noqa: BLE001
            transport = "?"
        intent = "yes" if hostvars.read_committed(repo, name) else "BOOTSTRAP"

        print(f"{name:<6} {platform:<13} {transport:<9} {intent:<8} "
              f"{version:<8} {', '.join(running) or '-'}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
