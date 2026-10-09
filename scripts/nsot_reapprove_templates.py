#!/usr/bin/env python3
"""Re-approve every template whose record predates the current fingerprint scheme.

A scheme bump is the one case where re-approval is bookkeeping rather than a
new decision: the template is unchanged, and only the question the record
answers has changed. It still runs the **gate** (scheme 3, P.5): the template
must round-trip on at least one bound device, and every bound device's result
is recorded as evidence, a device with no captured config as not validated.
A migration that skipped validation would be a record asserting something
nobody checked. The actor is the person running it (host-shell).

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

# Phase 4 section 8.1: the interpreter flask-app runs, before any other import.
from modules.app_interpreter import adopt  # noqa: E402
adopt(__name__)

from modules.nsot import approval, manifest as _m            # noqa: E402
from modules.nsot import repo as repo_service                # noqa: E402
from modules.nsot import templates_repo                      # noqa: E402

MESSAGE = f"template: re-approve under fingerprint scheme {approval.FINGERPRINT_SCHEME}"


def _golden(repo, device):
    entry = _m.find_by_name(repo, device)[1]
    if not entry:
        return ""
    # As COMMITTED (C104): approval evidence from a file nobody committed
    # would approve a template against a state that is not the record.
    from modules.nsot.repo import committed_golden_for
    return committed_golden_for(repo, entry)["text"] or ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("list_name", nargs="?", default="")
    ap.add_argument("--apply", action="store_true")
    # WHO is accountable (repo.ACTOR_CONVENTION): for a command run on the
    # host, the OS user. "operator" named nobody.
    import getpass
    ap.add_argument("--actor", default=getpass.getuser())
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
            print(f"  not validated (no captured config): {', '.join(missing)}")
        not_validated = [{"device": d, "reason": "no captured config yet"} for d in missing]

        if not args.apply:
            report = approval.validate_template(repo, rel_path, devices) if devices else {"results": []}
            for r in sorted(report["results"], key=lambda x: x["device"]):
                status = "PASS" if r.get("ok") else "FAIL (blocked at its own deploy)"
                print(f"    {r['device']:<6} {status}")
            passes = any(r.get("ok") for r in report["results"])
            print(f"  => would {'re-approve' if passes else 'REFUSE: no bound device round-trips'}\n")
            continue

        result = approval.approve(repo, rel_path, devices, actor=args.actor,
                                  not_validated=not_validated)
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
