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
7. Write ``.nsot/migrated.json`` — the marker that says this data directory has
   adopted the layout.

Nothing is deleted. Losing copies move to ``.nsot/migration-backup/``.

**One-directional.** ``golden_configs/`` is an input to the migration exactly
once. After the marker exists, :func:`apply` refuses and ``_collect_candidates``
stops reading that directory at all. The old store survives as a **read-only**
fallback for one lookup — :func:`modules.ai_assistant._find_golden_config_file`
consults it only when the manifest has no entry for a device — and is never
again a source of repo content.

The marker is deliberately **not** version-controlled. "Has this data directory
been migrated" is local installation state, the same kind as
``.nsot/migration-backup/`` and ``.nsot/staging/``, both already ignored. It
also has to carry the commit sha, which does not exist until after the commit
that would contain it. The version-controlled record of the migration is the
migration commit and its ``baseline/`` tag; the marker just answers the guard's
question without inferring it from directory contents.
"""

import json
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
MARKER_REL = os.path.join(".nsot", "migrated.json")


def marker_path(repo: str) -> str:
    return os.path.join(repo, MARKER_REL)


def read_marker(repo: str):
    """The migration marker, or ``None`` if this repo has not been migrated."""
    try:
        with open(marker_path(repo), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_marker(repo: str, sha: str, devices: list, merges: list) -> dict:
    """Record that this data directory has adopted the NSoT layout.

    Written *after* the commit, so it can carry the real sha rather than a
    promise of one.
    """
    marker = {
        "migrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": sha,
        "devices": sorted(d["hostname"] for d in devices),
        "device_count": len(devices),
        "merge_count": len(merges),
    }
    os.makedirs(os.path.dirname(marker_path(repo)), exist_ok=True)
    with open(marker_path(repo), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(marker, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return marker


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
    """Every golden file NMAS knows about, from both stores.

    ``golden_configs/`` is read **only until the marker exists**. Once this
    repo has been migrated the old store is inert as far as migration is
    concerned, whatever it still contains — so a second run cannot re-import
    stale copies over the live goldens.
    """
    stores = [("config_repo", repo)]
    if read_marker(repo) is None:
        stores.insert(0, ("golden_configs", golden_dir))

    found = []
    for source, directory in stores:
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

    # The marker, not the directory listing. ``golden/`` exists the moment
    # init_repo() runs, so its presence never meant "migrated" — that check
    # was computed, reported, and consumed by nothing.
    marker = read_marker(repo)
    already_migrated = marker is not None
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
        "marker": marker,
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

    list_dir = get_list_data_dir(list_name)
    repo = os.path.join(list_dir, "config_repo")
    golden_dir = os.path.join(list_dir, "golden_configs")

    # Refuse before doing anything. A second run is not a harmless no-op: the
    # two stores hold the same config in different shapes, so re-importing
    # rewrites every golden and commits the difference.
    marker = read_marker(repo)
    if marker is not None:
        sha = marker.get("commit") or "unknown"
        log.warning("migrate: refusing to re-run '%s' — already migrated at %s",
                    list_name, sha)
        return {"ok": False, "list": list_name,
                "error": f"already migrated at {sha}",
                "already_migrated": True, "marker": marker,
                "migrated": [], "merges": [], "committed": False}

    report = plan(list_name)

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
        inventory = _manifest.inventory_index(list_name)
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

            # Same discipline as save_golden: an unchanged file is not
            # rewritten, so it cannot contribute a phantom diff.
            if _repo._content_changed(target_abs, content):
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
            # Platform comes from the inventory, never from the config file.
            # A .cfg cannot tell you whether the box is a C8000v or a vIOS-L2;
            # the CSV column (or the NetBox platform) can.
            inv = inventory.get(group_ip) or inventory.get(hostname.lower()) or {}
            _manifest.upsert_device(repo, identity, hostname, group_ip,
                                    netbox_id=inv.get("netbox_id"),
                                    platform=inv.get("platform", ""),
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

        # Ask the index what is actually staged, not the worktree what is
        # merely different. ``status --porcelain`` also reports untracked and
        # unstaged paths that no commit would contain, so it can say "yes"
        # about a tree that is committed-identical.
        rc, staged_out, _ = _repo.git(repo, "diff", "--cached", "--name-only")
        staged_now = staged_out.splitlines() if rc == 0 else []

        created_commit = False
        sha = ""
        if staged_now:
            message = (
                f"migration: adopt NSoT repo layout for {len(migrated)} device(s)\n\n"
                f"Source: migration\nActor: {actor}\n"
                f"Devices: {','.join(m['hostname'] for m in migrated)}\n"
                + (f"Merged-Duplicates: {len(merges)}\n" if merges else "")
            )
            # No --allow-empty, ever: git itself then refuses a commit that
            # would not change the tree. Belt to the guard's braces — an empty
            # migration commit stays impossible even if the check above is
            # wrong or removed.
            rc, _, err = _repo.git(repo, "commit", "-m", message)
            created_commit = rc == 0
            if not created_commit:
                log.error("migrate: commit failed: %s", err)
        else:
            log.info("migrate: nothing staged for '%s' — no commit created", list_name)

        rc, head, _ = _repo.git(repo, "rev-parse", "HEAD")
        if rc == 0:
            sha = head.strip()

        if created_commit:
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            tag = _repo._unique_tag(repo, f"baseline/{stamp}-migrated", sha)
            _repo.git(repo, "tag", "-a", tag, "-m",
                      f"migrated baseline — {len(migrated)} device(s)")

        marker = _write_marker(repo, sha, migrated, merges)

    backfilled = backfill_device_uids()

    log.info("migrate: '%s' — %d device(s), %d merge(s), %d uid(s) backfilled",
             list_name, len(migrated), len(merges), backfilled["updated"])
    return {"ok": True, "list": list_name, "migrated": migrated,
            "merges": merges, "device_uids": backfilled,
            "committed": created_commit, "marker": marker, "report": report}


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
