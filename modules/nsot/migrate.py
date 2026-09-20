"""nsot/migrate.py

One-time migration of a list's golden configs into the NSoT repo layout.

Idempotent, logged, and **dry-run by default** — the UI shows the report and
asks before anything is written.

Steps:

1. Commit anything already staged, so nothing is lost to the old
   stage-now-commit-later flow.
2. Detect duplicates. A device can appear twice under different name casing
   (``R1.cfg`` / ``r1.cfg``) or under two filenames with the same management IP
   in the header. Merge keeping the **newest content**; report every merge.
3. Move ``config_repo/<host>.cfg`` → ``golden/<host>.cfg`` with ``git mv``, so
   history follows.
4. Import any ``golden_configs/<host>.cfg`` newer than the repo copy.
5. Build ``.nsot/manifest.json`` and backfill ``device_uid`` for every device in
   every local list, so identity exists immediately rather than on first save.
6. Tag the result ``baseline/<ts>-migrated``.

Nothing is deleted. Losing copies move to ``.nsot/migration-backup/``.
"""

import logging
import os
import re
import shutil
import time

from modules.nsot import manifest as _manifest
from modules.nsot import normalize as _normalize
from modules.nsot import repo as _repo

log = logging.getLogger(__name__)

_HEADER_RE = re.compile(r"—\s*(.+?)\s*\(([^)]+)\)")
_BACKUP_REL = os.path.join(".nsot", "migration-backup")


def _parse_header(path: str) -> tuple:
    """Return ``(hostname, mgmt_ip)`` from a golden file header.

    The old parser used an IPv4-only pattern, so a device reached over IPv6
    silently mis-parsed. This accepts anything inside the parentheses.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline()
    except OSError:
        return "", ""
    match = _HEADER_RE.search(first)
    if not match:
        return os.path.splitext(os.path.basename(path))[0], ""
    return match.group(1).strip(), match.group(2).strip()


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _case_insensitive_fs(directory: str) -> bool:
    """True if the filesystem folds case, so R1.cfg and r1.cfg are one file."""
    probe = os.path.join(directory, ".nsot-case-probe")
    try:
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("x")
        result = os.path.exists(os.path.join(directory, ".NSOT-CASE-PROBE"))
        os.remove(probe)
        return result
    except OSError:
        return False


def _collect_candidates(golden_dir: str, repo: str) -> list:
    """Every golden file NMAS knows about, from both stores."""
    found = []
    for source, directory in (("golden_configs", golden_dir), ("config_repo", repo)):
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".cfg"):
                continue
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            hostname, mgmt_ip = _parse_header(path)
            found.append({
                "store": source, "file": name, "path": path,
                "hostname": hostname or os.path.splitext(name)[0],
                "mgmt_ip": mgmt_ip, "mtime": _mtime(path),
                "size": os.path.getsize(path),
            })
    return found


def _group_duplicates(candidates: list) -> tuple:
    """Group candidates by identity. Returns ``(groups, merges)``.

    Two files describe the same device if they share a management IP **or** a
    case-folded hostname. Grouping on a single key is not enough, and the
    failure is not hypothetical: on a real NMAS the two stores hold the same
    device in different formats.

    ``golden_configs/s4.cfg`` keeps the NMAS header, so it yields an
    address (``203.0.113.24`` in the tests). ``config_repo/s4.cfg`` was written by
    ``config_git.write_and_stage``, which strips that header, so it yields no
    IP at all and falls back to its filename. Keyed separately they look like
    two devices; both then migrate to ``golden/s4.cfg`` and the second silently
    overwrites the first.

    So identity is a connected component: link every candidate to every other
    that shares either attribute, then merge whole components.
    """
    parent: dict = {}

    def _find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a, b):
        root_a, root_b = _find(a), _find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    # Every candidate is its own node, linked to whichever attributes it has.
    for index, cand in enumerate(candidates):
        node = f"cand:{index}"
        _find(node)
        if cand["mgmt_ip"]:
            _union(node, f"ip:{cand['mgmt_ip']}")
        if cand["hostname"]:
            _union(node, f"name:{cand['hostname'].lower()}")

    groups: dict = {}
    for index, cand in enumerate(candidates):
        groups.setdefault(_find(f"cand:{index}"), []).append(cand)

    # The richest identity in a group wins even if another member is newer:
    # a header-stripped copy has no management IP, and dropping it would break
    # manifest lookups by address.
    for members in groups.values():
        mgmt_ip = next((m["mgmt_ip"] for m in members if m["mgmt_ip"]), "")
        hostname = next((m["hostname"] for m in members
                         if m["hostname"] and not m["hostname"].startswith("unknown")), "")
        for member in members:
            member["group_mgmt_ip"] = mgmt_ip or member["mgmt_ip"]
            member["group_hostname"] = hostname or member["hostname"]

    merges = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda m: m["mtime"], reverse=True)
        winner, losers = ordered[0], ordered[1:]

        distinct_names = {m["hostname"] for m in members}
        distinct_files = {m["file"] for m in members}
        distinct_stores = {m["store"] for m in members}
        contents = set()
        for m in members:
            try:
                with open(m["path"], encoding="utf-8") as fh:
                    contents.add("\n".join(_normalize.strip_for_repo(fh.read())))
            except OSError:
                pass

        if len(distinct_stores) > 1:
            reason = ("the same device held in both stores — the golden_configs "
                      "copy keeps the NMAS header, the config_repo copy has it "
                      "stripped")
        elif len({n.lower() for n in distinct_names}) < len(distinct_names):
            reason = "same device name under different casing"
        elif len(distinct_files) > 1:
            reason = "same management IP under different filenames"
        else:
            reason = "duplicate entries for one device"

        merges.append({
            "key": key,
            "reason": reason,
            "stores": sorted(distinct_stores),
            "winner": {"file": winner["file"], "store": winner["store"],
                       "hostname": winner["hostname"], "size": winner["size"],
                       "modified": time.strftime("%Y-%m-%d %H:%M",
                                                 time.localtime(winner["mtime"]))},
            "losers": [{"file": l["file"], "store": l["store"],
                        "hostname": l["hostname"], "size": l["size"],
                        "modified": time.strftime("%Y-%m-%d %H:%M",
                                                  time.localtime(l["mtime"]))}
                       for l in losers],
            "names": sorted(distinct_names),
            "content_differed": len(contents) > 1,
        })
    return groups, merges


def plan(list_name: str) -> dict:
    """Dry-run report. Reads only — writes nothing."""
    from modules.config import get_list_data_dir

    list_dir = get_list_data_dir(list_name)
    repo = os.path.join(list_dir, "config_repo")
    golden_dir = os.path.join(list_dir, "golden_configs")

    already_migrated = os.path.isdir(os.path.join(repo, "golden"))
    candidates = _collect_candidates(golden_dir, repo)
    groups, merges = _group_duplicates(candidates)

    staged = []
    if os.path.isdir(os.path.join(repo, ".git")):
        rc, out, _ = _repo.git(repo, "diff", "--cached", "--name-only")
        if rc == 0 and out:
            staged = out.splitlines()

    to_migrate = []
    for key, members in groups.items():
        winner = sorted(members, key=lambda m: m["mtime"], reverse=True)[0]
        to_migrate.append({"hostname": winner.get("group_hostname") or winner["hostname"],
                           "mgmt_ip": winner.get("group_mgmt_ip") or winner["mgmt_ip"],
                           "from": f"{winner['store']}/{winner['file']}",
                           "to": f"golden/{_repo._safe_name(winner['hostname'])}.cfg"})

    return {
        "ok": True,
        "list": list_name,
        "already_migrated": already_migrated,
        "case_insensitive_fs": _case_insensitive_fs(list_dir),
        "staged_files": staged,
        "devices": sorted(to_migrate, key=lambda d: d["hostname"].lower()),
        "device_count": len(to_migrate),
        "merges": merges,
        "merge_count": len(merges),
        "candidates": len(candidates),
    }


def apply(list_name: str, actor: str = "nmas") -> dict:
    """Perform the migration. Idempotent."""
    from modules.config import get_list_data_dir

    report = plan(list_name)
    list_dir = get_list_data_dir(list_name)
    repo = os.path.join(list_dir, "config_repo")
    golden_dir = os.path.join(list_dir, "golden_configs")

    with _repo.repo_lock(repo):
        _repo.init_repo(repo)

        # 1. Commit anything the old flow left staged.
        rc, out, _ = _repo.git(repo, "diff", "--cached", "--name-only")
        if rc == 0 and out.strip():
            _repo.git(repo, "commit", "-m",
                      "migration: commit previously staged configs\n\n"
                      f"Source: migration\nActor: {actor}\n")
            log.info("migrate: committed %d previously staged file(s)",
                     len(out.splitlines()))

        backup_dir = os.path.join(repo, _BACKUP_REL)
        os.makedirs(backup_dir, exist_ok=True)
        os.makedirs(os.path.join(repo, "golden"), exist_ok=True)

        candidates = _collect_candidates(golden_dir, repo)
        groups, merges = _group_duplicates(candidates)
        migrated = []

        for key, members in groups.items():
            ordered = sorted(members, key=lambda m: m["mtime"], reverse=True)
            winner, losers = ordered[0], ordered[1:]
            hostname = winner.get("group_hostname") or winner["hostname"]
            group_ip = winner.get("group_mgmt_ip") or winner["mgmt_ip"]
            target_rel = f"golden/{_repo._safe_name(hostname)}.cfg"
            target_abs = os.path.join(repo, target_rel)

            try:
                with open(winner["path"], encoding="utf-8") as fh:
                    raw = fh.read()
            except OSError as exc:
                log.warning("migrate: could not read %s: %s", winner["path"], exc)
                continue

            content = _repo.golden_body(hostname, group_ip, raw)

            # git mv preserves history when the source is already tracked.
            source_rel = os.path.relpath(winner["path"], repo)
            moved = False
            if winner["store"] == "config_repo" and not source_rel.startswith(".."):
                rc, _, _ = _repo.git(repo, "ls-files", "--error-unmatch", source_rel)
                if rc == 0 and os.path.normpath(source_rel) != os.path.normpath(target_rel):
                    rc, _, err = _repo.git(repo, "mv", "-f", source_rel, target_rel)
                    moved = rc == 0
                    if not moved:
                        log.debug("migrate: git mv %s failed: %s", source_rel, err)

            with open(target_abs, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)

            # Reuse an existing identity so re-running the migration is a
            # no-op. Minting a fresh uid every run would rewrite the manifest
            # and create a commit each time.
            identity, existing = _manifest.find_by_ip(repo, group_ip)
            if not identity:
                identity, existing = _manifest.find_by_name(repo, hostname)
            if not identity:
                identity = _manifest.new_device_uid()
            _manifest.upsert_device(repo, identity, hostname, group_ip,
                                    golden=target_rel)

            for loser in losers:
                try:
                    shutil.copy2(loser["path"],
                                 os.path.join(backup_dir, f"{loser['store']}-{loser['file']}"))
                except OSError as exc:
                    log.warning("migrate: could not back up %s: %s", loser["path"], exc)

            migrated.append({"hostname": hostname, "moved_with_history": moved,
                             "merged_from": [l["file"] for l in losers]})

        # .gitattributes and the manifest join the migration commit.
        _repo.git(repo, "add", "-A", "golden", ".nsot", ".gitattributes", ".gitignore")
        rc, out, _ = _repo.git(repo, "status", "--porcelain")
        created_commit = False
        if out.strip():
            message = (
                f"migration: adopt NSoT repo layout for {len(migrated)} device(s)\n\n"
                f"Source: migration\nActor: {actor}\n"
                f"Devices: {','.join(m['hostname'] for m in migrated)}\n"
                + (f"Merged-Duplicates: {len(merges)}\n" if merges else "")
            )
            rc, _, err = _repo.git(repo, "commit", "-m", message)
            created_commit = rc == 0
            if not created_commit:
                log.error("migrate: commit failed: %s", err)

        if created_commit:
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            _repo.git(repo, "tag", "-a", f"baseline/{stamp}-migrated", "-m",
                      f"migrated baseline — {len(migrated)} device(s)")

    backfilled = backfill_device_uids()

    log.info("migrate: '%s' — %d device(s), %d merge(s), %d uid(s) backfilled",
             list_name, len(migrated), len(merges), backfilled["updated"])
    return {"ok": True, "list": list_name, "migrated": migrated,
            "merges": merges, "device_uids": backfilled,
            "committed": created_commit, "report": report}


def backfill_device_uids() -> dict:
    """Give every device in every **local** list a durable ``device_uid``.

    Done in one pass at migration rather than on first save, so identity exists
    immediately. NetBox-sourced lists are skipped: their identity is the NetBox
    device id.
    """
    import csv

    from modules.config import LISTS_DIR
    from modules.device import get_device_lists
    from modules.inventory.source_config import is_netbox_sourced

    updated, skipped = 0, []
    for entry in get_device_lists():
        name = entry["name"]
        if is_netbox_sourced(name):
            skipped.append(name)
            continue
        path = os.path.join(LISTS_DIR, entry["filename"], "devices.csv")
        if not os.path.exists(path):
            continue
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            if not rows:
                continue
            changed = False
            for row in rows:
                if not row.get("device_uid"):
                    row["device_uid"] = _manifest.new_device_uid()
                    changed = True
                    updated += 1
            if changed:
                fields = ["hostname", "device_type", "ip", "username",
                          "password", "secret", "role", "device_uid"]
                tmp = path + ".tmp"
                with open(tmp, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(rows)
                os.replace(tmp, path)
        except Exception as exc:              # noqa: BLE001
            log.warning("migrate: device_uid backfill failed for '%s': %s", name, exc)

    return {"updated": updated, "skipped_netbox_lists": skipped}
