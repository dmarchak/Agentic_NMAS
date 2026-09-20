#!/usr/bin/env python3
"""Post-migration verification. Read-only — this script writes nothing.

Twelve checks over a migrated list. Run it before approving any template, so
the first template commit lands on a repo whose state has been looked at rather
than assumed.

Usage::

    python scripts/nsot_verify_migration.py [list-name]
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.config import get_list_data_dir                  # noqa: E402
from modules.nsot import manifest as _m, migrate, normalize     # noqa: E402
from modules.nsot import repo as _repo                          # noqa: E402

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"


def _git(repo, *args):
    out = subprocess.run(["git", "-C", repo, *args],
                         capture_output=True, text=True)
    return out.returncode, out.stdout.strip()


def verify(list_name):
    list_dir = get_list_data_dir(list_name)
    repo = os.path.join(list_dir, "config_repo")
    legacy = os.path.join(list_dir, "golden_configs")
    golden = os.path.join(repo, "golden")
    results = []

    def check(n, name, status, detail):
        results.append((n, name, status, detail))

    golden_files = sorted(f for f in os.listdir(golden)
                          if f.endswith(".cfg")) if os.path.isdir(golden) else []
    devices = _m.load(repo)["devices"]

    # 1 ----------------------------------------------------------------
    check(1, "golden/ holds one file per device",
          PASS if golden_files and len(golden_files) == len(devices) else FAIL,
          f"{len(golden_files)} file(s), {len(devices)} manifest entr(ies)")

    # 2 ----------------------------------------------------------------
    legacy_files = sorted(f for f in os.listdir(legacy)
                          if f.endswith(".cfg")) if os.path.isdir(legacy) else []
    marker = migrate.read_marker(repo)
    inert = marker is not None
    check(2, "golden_configs/ is a read-only fallback, not an input",
          PASS if inert else FAIL,
          f"{len(legacy_files)} legacy file(s) kept; migration input closed"
          if inert else
          f"{len(legacy_files)} legacy file(s) and no marker — still an input")

    # 3 ----------------------------------------------------------------
    names = [e.get("name", "") for e in devices.values()]
    dupes = {n for n in names if names.count(n) > 1}
    check(3, "no duplicate device entries in the manifest",
          PASS if devices and not dupes else FAIL,
          f"{len(devices)} entr(ies), duplicates: {sorted(dupes) or 'none'}")

    # 4 ----------------------------------------------------------------
    no_ip = sorted(e.get("name", "?") for e in devices.values()
                   if not (e.get("mgmt_ip") or "").strip())
    check(4, "every manifest entry carries its management IP",
          PASS if devices and not no_ip else FAIL,
          f"{len(devices) - len(no_ip)}/{len(devices)} have an IP"
          + (f"; missing: {no_ip}" if no_ip else ""))

    # 5 ----------------------------------------------------------------
    with_platform = [e for e in devices.values() if (e.get("platform") or "").strip()]
    check(5, "every manifest entry carries a platform",
          PASS if devices and len(with_platform) == len(devices) else FAIL,
          f"{len(with_platform)}/{len(devices)} have a platform")

    # 6 ----------------------------------------------------------------
    unresolved = []
    for entry in devices.values():
        path = _m.golden_path_for(repo, entry)
        if not os.path.exists(path):
            unresolved.append(entry.get("name", "?"))
    check(6, "every device resolves a golden config through the manifest",
          PASS if devices and not unresolved else FAIL,
          f"{len(devices) - len(unresolved)}/{len(devices)} resolve"
          + (f"; unresolved: {unresolved}" if unresolved else ""))

    # 7 ----------------------------------------------------------------
    sample = golden_files[0] if golden_files else ""
    rc, log_out = _git(repo, "log", "--follow", "--oneline", "--",
                       f"golden/{sample}") if sample else (1, "")
    commits = log_out.splitlines() if rc == 0 else []
    check(7, "rename history survives the move into golden/",
          PASS if len(commits) > 1 else FAIL,
          f"golden/{sample}: {len(commits)} commit(s) via --follow")

    # 8 ----------------------------------------------------------------
    backup = os.path.join(repo, ".nsot", "migration-backup")
    backups = sorted(os.listdir(backup)) if os.path.isdir(backup) else []
    check(8, "merged-away copies are backed up, not deleted",
          PASS if backups else WARN,
          f"{len(backups)} file(s) in .nsot/migration-backup/")

    # 9 ----------------------------------------------------------------
    plan = migrate.plan(list_name)
    guarded = bool(plan.get("already_migrated")) and marker is not None
    check(9, "re-running the migration is refused",
          PASS if guarded else FAIL,
          f"marker at {marker.get('commit', '?')[:8]}, plan.already_migrated="
          f"{plan.get('already_migrated')}" if marker else
          "no .nsot/migrated.json — apply() would run again")

    # 10 ---------------------------------------------------------------
    rc, tag_out = _git(repo, "tag", "--list", "baseline/*")
    tags = tag_out.split()
    check(10, "exactly one migration baseline tag",
          PASS if len(tags) == 1 else FAIL,
          f"{len(tags)} baseline tag(s): {tags}")

    # 11 ---------------------------------------------------------------
    rc, status = _git(repo, "status", "--porcelain")
    dirty = [ln for ln in status.splitlines() if ln.strip()]
    tracked_dirty = [ln for ln in dirty if not ln.startswith("??")]
    check(11, "no golden change left uncommitted",
          PASS if not tracked_dirty else FAIL,
          f"{len(tracked_dirty)} tracked change(s), {len(dirty) - len(tracked_dirty)}"
          " untracked path(s)")

    # 12 ---------------------------------------------------------------
    # Compare the legacy copy against golden AS IT WAS AT THE MIGRATION
    # COMMIT, not as it is now.
    #
    # First attempt compared against the working tree, which made the check
    # fail the moment a deploy legitimately re-baselined a device — reporting
    # a success as a failure. Second attempt skipped devices changed since
    # migration, which on this repo skipped all nine and reported PASS having
    # compared nothing: a vacuous pass, the same family as a check positioned
    # where it cannot fail.
    #
    # The question is "did migration preserve content", and it has a fixed
    # answer at a fixed commit. Reading the blob at that commit answers it
    # permanently and cannot be invalidated by later legitimate change.
    marker = migrate.read_marker(repo)
    migration_sha = (marker or {}).get("commit", "")
    drifted, compared, unreadable = [], 0, []
    for entry in devices.values():
        name = entry.get("name", "")
        legacy_path = os.path.join(legacy, f"{name}.cfg")
        if not os.path.exists(legacy_path) or not migration_sha:
            continue
        rel = os.path.relpath(_m.golden_path_for(repo, entry), repo)
        rc, blob = _git(repo, "show", f"{migration_sha}:{rel}")
        if rc != 0 or not blob.strip():
            unreadable.append(name)
            continue
        with open(legacy_path, encoding="utf-8") as fh:
            a = normalize.strip_for_diff(fh.read())
        if a != normalize.strip_for_diff(blob):
            drifted.append(name)
        compared += 1

    if drifted:
        status, detail = FAIL, f"differs on: {sorted(drifted)}"
    elif compared == 0:
        # Never PASS on an empty comparison.
        status, detail = WARN, "nothing could be compared"
    else:
        status = PASS
        detail = f"{compared} device(s) compared at {migration_sha[:8]}, identical"
    if unreadable:
        detail += f"; unreadable at that commit: {sorted(unreadable)}"
    check(12, "migration preserved content (at the migration commit)",
          status, detail)

    return results


def main():
    list_name = sys.argv[1] if len(sys.argv) > 1 else None
    if not list_name:
        from modules.config import get_current_list_name
        list_name = get_current_list_name()

    results = verify(list_name)
    width = max(len(name) for _n, name, _s, _d in results)
    print(f"\nPost-migration verification — list '{list_name}'\n")
    print(f"{'#':>2}  {'check'.ljust(width)}  status  detail")
    print(f"{'-' * 2}  {'-' * width}  ------  {'-' * 40}")
    for n, name, status, detail in results:
        print(f"{n:>2}  {name.ljust(width)}  {status:<6}  {detail}")

    failed = [n for n, _name, s, _d in results if s == FAIL]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed"
          + (f" — failing: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
