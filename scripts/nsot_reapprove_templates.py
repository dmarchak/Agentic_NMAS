#!/usr/bin/env python3
"""Re-approve every template whose record predates the current fingerprint scheme.

A scheme bump is the one case where re-approval is bookkeeping rather than a
new decision: the template and the device set are unchanged, and only the
question the record answers has changed. It still runs the **full gate** —
every bound device must round-trip cleanly — because a migration that skipped
validation would be a record asserting something nobody checked.

Templates that are already on the current scheme are left alone. Dry-run by
default.

Usage::

    python scripts/nsot_reapprove_templates.py [list-name]
    python scripts/nsot_reapprove_templates.py [list-name] --apply
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.nsot import approval, manifest as _m            # noqa: E402
from modules.nsot import repo as repo_service                # noqa: E402
from modules.nsot import templates_repo                      # noqa: E402

MESSAGE = "template: re-approve under fingerprint v2"


def _golden(repo, device):
    entry = _m.find_by_name(repo, device)[1]
    if not entry:
        return ""
    path = _m.golden_path_for(repo, entry)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("list_name", nargs="?", default="")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--actor", default="operator")
    args = ap.parse_args()

    from modules.config import get_current_list_name, get_list_data_dir
    list_name = args.list_name or get_current_list_name()
    repo = os.path.join(get_list_data_dir(list_name), "config_repo")

    stored = approval._load(repo)
    stale = [path for path, record in stored.items()
             if record.get("revoked")
             or record.get("scheme") != approval.FINGERPRINT_SCHEME]
    if not stale:
        print(f"every approval is already on scheme {approval.FINGERPRINT_SCHEME}")
        return 0

    # Say which it is. A revoked record and a scheme-migrated one both need
    # re-approval and are not the same event: one is a finding somebody
    # recorded, the other is bookkeeping. Reporting the second when it is the
    # first buries the reason the template was withdrawn.
    print()
    for path in sorted(stale):
        record = stored[path]
        if record.get("revoked"):
            print(f"{path}: REVOKED {record.get('revoked_at', '')} by "
                  f"{record.get('actor', '?')}")
            print(f"    reason: {record.get('reason', '(none recorded)')}")
        else:
            print(f"{path}: approved under fingerprint scheme "
                  f"{record.get('scheme', 1)}, current is "
                  f"{approval.FINGERPRINT_SCHEME}")
    print(f"\n{len(stale)} approval(s) need re-validation\n")

    approved, refused = [], []
    for rel_path in sorted(stale):
        bound = templates_repo.devices_for_template(repo, rel_path)
        devices, missing = [], []
        for entry in bound:
            config = _golden(repo, entry["device"])
            if not config:
                missing.append(entry["device"])
                continue
            devices.append({"device": entry["device"],
                            "platform": entry["platform"],
                            "running_config": config})

        print(f"{rel_path}   ({len(bound)} bound device(s))")
        if missing:
            print(f"  NO CAPTURED CONFIG: {', '.join(missing)}")
            refused.append(rel_path)
            continue

        if not args.apply:
            report = approval.validate_template(repo, rel_path, devices)
            for r in sorted(report["results"], key=lambda x: x["device"]):
                status = "PASS" if r.get("ok") else "FAIL"
                print(f"    {r['device']:<6} {status}")
            print(f"  => would {'re-approve' if report['ok'] else 'REFUSE'}\n")
            continue

        result = approval.approve(repo, rel_path, devices, actor=args.actor)
        if not result["ok"]:
            print(f"  REFUSED: {result['error']}")
            refused.append(rel_path)
            continue
        for r in sorted(result["validation"]["results"], key=lambda x: x["device"]):
            print(f"    {r['device']:<6} {'PASS' if r['ok'] else 'FAIL'}  "
                  f"coverage {r['modeled_coverage']:.2f}%  "
                  f"missing {r['missing']}  extra {r['extra']}  "
                  f"reordered {r['reordered']}  unmodeled {r['unmodeled']}")
        print(f"  => re-approved, fingerprint {result['fingerprint']}\n")
        approved.append(rel_path)

    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply.")
        return 0
    if not approved:
        print("nothing re-approved")
        return 1

    commit = repo_service.save_templates(
        list_name, [".approvals.json"], actor=args.actor, message=MESSAGE,
        paths=[os.path.join("templates", ".approvals.json")])
    print(f"commit: {commit.get('commit', '')[:12]} ok={commit.get('ok')}")
    if refused:
        print(f"still unapproved: {sorted(refused)}")
    return 0 if commit.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
