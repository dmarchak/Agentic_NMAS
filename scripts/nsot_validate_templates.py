#!/usr/bin/env python3
"""Dry-run the template approval gate. Read-only — writes nothing, commits nothing.

The same computation :func:`modules.nsot.approval.approve` runs before it will
record anything, reported per device. Run it before approving, so the approval
is a confirmation of something already looked at rather than the first time
anyone sees the numbers.

Every config comes from a **captured** artifact — the golden config in the
repo. Nothing here opens a socket.

Usage::

    python scripts/nsot_validate_templates.py [list-name]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.config import get_list_data_dir                    # noqa: E402
from modules.nsot import approval, manifest as _m               # noqa: E402
from modules.nsot import templates_repo                         # noqa: E402


def _n(value):
    """compare() reports some of these as counts and some as lists."""
    return value if isinstance(value, int) else len(value)


def _pct(value):
    """``modeled_coverage`` is already a percentage, not a fraction."""
    return f"{value:.2f}%"


def _golden_for(repo, device):
    entry = _m.find_by_name(repo, device)[1]
    if not entry:
        return ""
    path = _m.golden_path_for(repo, entry)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def main():
    list_name = sys.argv[1] if len(sys.argv) > 1 else None
    if not list_name:
        from modules.config import get_current_list_name
        list_name = get_current_list_name()

    repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    templates = templates_repo.list_templates(repo)
    if not templates:
        print(f"no templates in {templates_repo.templates_dir(repo)}")
        return 1

    print(f"\nTemplate validation — list '{list_name}'  (read-only)\n")
    overall = True

    for tpl in templates:
        rel = tpl["path"]
        bound = templates_repo.devices_for_template(repo, rel)
        if not bound:
            print(f"{rel}\n  no bound devices — nothing to validate against\n")
            continue

        devices, missing = [], []
        for entry in bound:
            golden = _golden_for(repo, entry["device"])
            if not golden:
                missing.append(entry["device"])
                continue
            devices.append({"device": entry["device"],
                            "platform": entry["platform"],
                            "running_config": golden})

        print(f"{rel}   ({len(bound)} bound device(s))")
        if missing:
            print(f"  NO CAPTURED CONFIG: {', '.join(missing)}")
            overall = False

        if not devices:
            print()
            continue

        report = approval.validate_template(repo, rel, devices)
        for r in sorted(report["results"], key=lambda x: x["device"]):
            if "error" in r:
                print(f"    {r['device']:<6} FAIL   {r['error']}")
                overall = False
                continue
            status = "PASS" if r["ok"] else "FAIL"
            print(f"    {r['device']:<6} {status:<6} "
                  f"coverage {_pct(r['modeled_coverage']):>7}  "
                  f"missing {_n(r['missing']):<3} extra {_n(r['extra']):<3} "
                  f"reordered {_n(r['reordered']):<3} "
                  f"unmodeled {_n(r['unmodeled']):<3}"
                  f"{'' if r['unmodeled_acknowledged'] else ' (UNACKNOWLEDGED)'}")
            for line in r["missing_sample"]:
                print(f"           - missing: {line}")
            for line in r["extra_sample"]:
                print(f"           + extra:   {line}")
        verdict = "APPROVABLE" if report["ok"] else "NOT APPROVABLE"
        print(f"  => {verdict}\n")
        overall = overall and report["ok"]

    print("all templates approvable" if overall
          else "at least one template is not approvable")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
