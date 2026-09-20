#!/usr/bin/env python3
"""Collapse duplicate manifest entries for one device. Dry-run by default.

A repair for manifests written before ``resolve_identity()`` existed, when
``save_golden()`` minted a fresh identity for any item that arrived without
one. A deploy against a device the manifest already knew therefore created a
second entry for it — same name, same management IP, empty platform.

Grouping is by management IP first, then case-folded name, matching how
``find_by_ip`` and ``find_by_name`` resolve. The survivor is the entry the
lookups already return, so nothing that reads the manifest changes behaviour;
the others are removed.

**Refuses to merge entries that disagree.** Two entries with different golden
paths, or both carrying a different non-empty platform, are reported and left
alone — that is a question for a person, not a script.

Usage::

    python scripts/nsot_dedupe_manifest.py <repo-path>            # dry run
    python scripts/nsot_dedupe_manifest.py <repo-path> --apply    # commit
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.nsot import manifest as M    # noqa: E402
from modules.nsot import repo as R        # noqa: E402


def _groups(devices: dict) -> dict:
    keyed = {}
    for identity, entry in devices.items():
        key = (entry.get("mgmt_ip") or "").strip() \
            or (entry.get("name") or "").strip().lower()
        if not key:
            continue
        keyed.setdefault(key, []).append((identity, entry))
    return {k: v for k, v in keyed.items() if len(v) > 1}


def _survivor(repo: str, members: list):
    """The entry the lookups already return, so behaviour does not change."""
    identity, entry = members[0]
    resolved = M.find_by_ip(repo, entry.get("mgmt_ip", ""))[0] \
        or M.find_by_name(repo, entry.get("name", ""))[0]
    for candidate_identity, candidate in members:
        if candidate_identity == resolved:
            return candidate_identity, candidate
    return identity, entry


def _conflicts(members: list) -> list:
    problems = []
    goldens = {(e.get("golden") or "") for _i, e in members}
    if len(goldens) > 1:
        problems.append(f"different golden paths: {sorted(goldens)}")
    platforms = {(e.get("platform") or "").strip() for _i, e in members}
    platforms.discard("")
    if len(platforms) > 1:
        problems.append(f"different platforms: {sorted(platforms)}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo", help="path to a list's config_repo")
    ap.add_argument("--apply", action="store_true",
                    help="write and commit; without this, report only")
    ap.add_argument("--list-name", default="",
                    help="device list name, for the commit (default: current)")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    data = M.load(repo)
    duplicates = _groups(data["devices"])

    if not duplicates:
        print(f"{len(data['devices'])} entr(ies), no duplicates")
        return 0

    removals = []
    blocked = False
    for key, members in sorted(duplicates.items()):
        keep_id, keep = _survivor(repo, members)
        problems = _conflicts(members)
        print(f"\n{key} — {len(members)} entries")
        for identity, entry in members:
            mark = "KEEP  " if identity == keep_id else "REMOVE"
            print(f"  {mark} {identity}")
            print(f"         platform={entry.get('platform')!r} "
                  f"golden={entry.get('golden')!r}")
        if problems:
            blocked = True
            print("  REFUSING: " + "; ".join(problems))
            continue
        removals.extend(i for i, _e in members if i != keep_id)

    if blocked:
        print("\nSome groups disagree and were left alone — resolve those by hand.")
    if not removals:
        return 1 if blocked else 0

    print(f"\n{len(removals)} entr(ies) would be removed.")
    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply to commit.")
        return 0

    for identity in removals:
        data["devices"].pop(identity, None)
    M.save(repo, data)

    from modules.config import get_current_list_name
    list_name = args.list_name or get_current_list_name()
    result = R._commit_paths(
        list_name, [os.path.join(".nsot", "manifest.json")],
        f"manifest: collapse {len(removals)} duplicate device entr(ies)",
        [f"Removed: {','.join(removals)}", "Actor: operator"],
        "manifest")
    print(f"commit: {result.get('commit', '')[:12]} ok={result.get('ok')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
