#!/usr/bin/env python3
"""Write the migration marker on a repo that was migrated before it existed.

One-time helper for exactly one situation: a data directory whose migration ran
under a build of ``modules/nsot/migrate.py`` that predated
``.nsot/migrated.json``. Without the marker those repos are indistinguishable
from un-migrated ones, so ``apply()`` would run again — which is the bug the
marker closes.

It refuses if a marker is already present, and it will not invent one for a
repo that has not actually been migrated: ``golden/`` must hold at least one
config, and the commit named on the command line must exist.

Usage::

    python scripts/nsot_adopt_marker.py <repo-path> <migration-commit-sha>
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.nsot import migrate, repo as _repo   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo", help="path to a list's config_repo")
    ap.add_argument("commit", help="sha of the migration commit")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)

    existing = migrate.read_marker(repo)
    if existing:
        print(f"marker already present: migrated at {existing.get('commit')}")
        return 0

    golden_dir = os.path.join(repo, "golden")
    names = sorted(f[:-4] for f in os.listdir(golden_dir)
                   if f.endswith(".cfg")) if os.path.isdir(golden_dir) else []
    if not names:
        print(f"refusing: {golden_dir} holds no configs — this repo is not migrated",
              file=sys.stderr)
        return 1

    rc, sha, _ = _repo.git(repo, "rev-parse", "--verify", f"{args.commit}^{{commit}}")
    if rc != 0:
        print(f"refusing: {args.commit} is not a commit in {repo}", file=sys.stderr)
        return 1

    marker = migrate._write_marker(repo, sha.strip(),
                                   [{"hostname": n} for n in names], [])
    print(f"wrote {migrate.marker_path(repo)}")
    print(f"  migrated at {marker['commit']}")
    print(f"  {marker['device_count']} device(s): {', '.join(marker['devices'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
