#!/usr/bin/env python3
"""Make ``devices.csv`` device_uids agree with the manifest. Dry-run by default.

Migration minted identities into two places independently: ``backfill_device_uids()``
wrote uids into ``devices.csv``, and ``migrate.apply()`` created manifest
entries with uids of its own. Nothing ever made them agree, so a device could
carry a CSV uid the manifest had never held.

That is not cosmetic. A supplied identity used to be trusted outright, so every
deploy created a *second* manifest entry for a device that already had one —
and the duplicates carried no platform, which bound them to the default
template and quietly revoked template approvals.

The manifest is authoritative here: it is what ``golden/`` is keyed on and what
``find_by_identity`` resolves. The CSV is updated to match, matched by
management IP first and case-folded hostname second.

Usage::

    python scripts/nsot_reconcile_uids.py [list-name]
    python scripts/nsot_reconcile_uids.py [list-name] --apply
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.nsot import manifest as M        # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("list_name", nargs="?", default="")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from modules.config import get_current_list_name, get_list_data_dir
    from modules.device import load_saved_devices, write_devices_csv

    list_name = args.list_name or get_current_list_name()
    list_dir = get_list_data_dir(list_name)
    repo = os.path.join(list_dir, "config_repo")
    csv_path = os.path.join(list_dir, "devices.csv")

    devices = load_saved_devices(csv_path)
    entries = M.load(repo)["devices"]

    by_ip = {(e.get("mgmt_ip") or "").strip(): i for i, e in entries.items()
             if (e.get("mgmt_ip") or "").strip()}
    by_name = {}
    for identity, entry in entries.items():
        name = (entry.get("name") or "").strip().lower()
        if name:
            by_name.setdefault(name, []).append(identity)

    changes, unresolved = [], []
    for device in devices:
        hostname = device.get("hostname", "")
        ip = (device.get("ip") or "").strip()
        current = (device.get("device_uid") or "").strip()

        identity = by_ip.get(ip)
        if not identity:
            candidates = by_name.get(hostname.lower(), [])
            identity = candidates[0] if len(candidates) == 1 else None
        if not identity:
            unresolved.append(hostname)
            continue
        if not identity.startswith("uid:"):
            # A NetBox-identified device carries its id, not a uid; leave it.
            continue

        wanted = identity.split(":", 1)[1]
        if current != wanted:
            changes.append((hostname, current or "(empty)", wanted))
            device["device_uid"] = wanted

    print(f"\n{len(devices)} device(s), {len(entries)} manifest entr(ies)\n")
    if unresolved:
        print(f"NOT IN THE MANIFEST — left alone: {sorted(unresolved)}\n")
    if not changes:
        print("every device_uid already matches the manifest")
        return 0

    width = max(len(h) for h, _o, _n in changes)
    for hostname, old, new in changes:
        print(f"  {hostname.ljust(width)}  {old}")
        print(f"  {' '.ljust(width)}  -> {new}")
    print(f"\n{len(changes)} device_uid(s) would change.")

    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply.")
        return 0

    write_devices_csv(devices, csv_path)
    print("devices.csv rewritten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
