"""Migration into the NSoT repo layout.

Dry-run first and dry-run by default. The interesting case is duplicates: a
device can appear twice under different name casing (``R1.cfg`` / ``r1.cfg``)
or under two filenames carrying the same management IP. Merging must keep the
newest content and **report every merge** — silently creating two golden files
for one device is the failure this guards against.
"""

import os
import subprocess
import time

import pytest

from modules.nsot import migrate

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git is not available",
)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost",
                            "nsot_device_tag_retention": 50,
                        }.get(key, default))
    list_dir = tmp_path / "lab"
    (list_dir / "golden_configs").mkdir(parents=True)
    (list_dir / "config_repo").mkdir(parents=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr(migrate, "backfill_device_uids",
                        lambda: {"updated": 0, "skipped_netbox_lists": []})
    return list_dir


def _write(lab, store, filename, hostname, ip, body, age_seconds=0):
    path = lab / store / filename
    path.write_text(f"! Golden config — {hostname} ({ip})\n"
                    f"! Saved: 2026-01-01 00:00:00\n{body}\n", encoding="utf-8")
    if age_seconds:
        old = time.time() - age_seconds
        os.utime(path, (old, old))
    return path


class TestDryRun:
    def test_plan_writes_nothing(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        before = sorted(os.listdir(lab / "config_repo"))
        report = migrate.plan("Lab")
        assert report["ok"]
        assert sorted(os.listdir(lab / "config_repo")) == before

    def test_plan_lists_devices_to_migrate(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        _write(lab, "golden_configs", "S1.cfg", "S1", "203.0.113.20", "hostname S1")
        report = migrate.plan("Lab")
        assert report["device_count"] == 2
        assert {d["hostname"] for d in report["devices"]} == {"R1", "S1"}

    def test_plan_reports_target_paths(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        device = migrate.plan("Lab")["devices"][0]
        assert device["to"] == "golden/R1.cfg"
        assert device["from"] == "golden_configs/R1.cfg"


class TestDuplicateDetection:
    def test_case_differing_names_are_merged(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "newer")
        _write(lab, "config_repo", "r1.cfg", "r1", "203.0.113.1", "older", age_seconds=9000)
        report = migrate.plan("Lab")
        assert report["merge_count"] == 1
        assert report["device_count"] == 1, "a device was about to be duplicated"

    def test_ip_level_duplicates_are_merged(self, lab):
        """Same device, two different filenames, same management IP."""
        _write(lab, "golden_configs", "R2.cfg", "R2", "203.0.113.2", "newer")
        _write(lab, "config_repo", "R2-old.cfg", "R2", "203.0.113.2", "older",
               age_seconds=9000)
        merge = migrate.plan("Lab")["merges"][0]
        assert merge["winner"]["file"] == "R2.cfg"
        assert merge["losers"][0]["file"] == "R2-old.cfg"

    def test_newest_content_wins(self, lab):
        _write(lab, "config_repo", "R1.cfg", "R1", "203.0.113.1", "OLD", age_seconds=9000)
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "NEW")
        migrate.apply("Lab")
        content = (lab / "config_repo" / "golden" / "R1.cfg").read_text(encoding="utf-8")
        assert "NEW" in content and "OLD" not in content

    def test_every_merge_is_reported(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "a")
        _write(lab, "config_repo", "r1.cfg", "r1", "203.0.113.1", "b", age_seconds=9000)
        merge = migrate.plan("Lab")["merges"][0]
        for key in ("reason", "winner", "losers", "names", "content_differed"):
            assert key in merge
        assert sorted(merge["names"]) == ["R1", "r1"]
        assert merge["content_differed"] is True

    def test_losers_are_backed_up_not_deleted(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "new")
        _write(lab, "config_repo", "r1.cfg", "r1", "203.0.113.1", "old", age_seconds=9000)
        migrate.apply("Lab")
        backup = lab / "config_repo" / ".nsot" / "migration-backup"
        assert backup.is_dir()
        assert any("r1.cfg" in f for f in os.listdir(backup))

    def test_distinct_devices_are_not_merged(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "a")
        _write(lab, "golden_configs", "R2.cfg", "R2", "203.0.113.2", "b")
        report = migrate.plan("Lab")
        assert report["merge_count"] == 0
        assert report["device_count"] == 2

    def test_case_insensitive_filesystem_is_reported(self, lab):
        """On Windows R1.cfg and r1.cfg are already one file — say so."""
        assert "case_insensitive_fs" in migrate.plan("Lab")


class TestApply:
    def test_creates_golden_layout(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        result = migrate.apply("Lab")
        assert result["ok"]
        assert (lab / "config_repo" / "golden" / "R1.cfg").exists()
        assert (lab / "config_repo" / ".nsot" / "manifest.json").exists()
        assert (lab / "config_repo" / ".gitattributes").exists()

    def test_header_is_normalised(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        content = (lab / "config_repo" / "golden" / "R1.cfg").read_text(encoding="utf-8")
        assert content.startswith("! Golden config — R1 (203.0.113.1)")
        assert "! Saved:" not in content

    def test_creates_a_migrated_baseline_tag(self, lab):
        from modules.nsot.repo import git
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        _rc, tags, _ = git(str(lab / "config_repo"), "tag", "--list", "baseline/*")
        assert any("migrated" in t for t in tags.splitlines())

    def test_manifest_records_every_device(self, lab):
        from modules.nsot.manifest import load
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "a")
        _write(lab, "golden_configs", "S1.cfg", "S1", "203.0.113.20", "b")
        migrate.apply("Lab")
        devices = load(str(lab / "config_repo"))["devices"]
        assert len(devices) == 2
        assert {e["name"] for e in devices.values()} == {"R1", "S1"}

    def test_is_idempotent(self, lab):
        from modules.nsot.repo import git
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        repo = str(lab / "config_repo")
        _rc, first, _ = git(repo, "rev-list", "--count", "HEAD")
        migrate.apply("Lab")
        _rc, second, _ = git(repo, "rev-list", "--count", "HEAD")
        assert first == second, "re-running the migration created another commit"

    def test_ipv6_header_parses(self, lab):
        """The old parser was IPv4-only, so a v6-managed device mis-parsed."""
        _write(lab, "golden_configs", "R9.cfg", "R9", "2001:db8::1", "hostname R9")
        report = migrate.plan("Lab")
        assert report["devices"][0]["mgmt_ip"] == "2001:db8::1"
        assert report["devices"][0]["hostname"] == "R9"


class TestBothStoresHoldTheSameDevice:
    """The real-world shape, found on the NMAS and missed by every fixture here.

    A device exists in **both** stores in **different formats**:

    * ``golden_configs/s4.cfg`` keeps the NMAS header, so it parses a
      management IP and groups as ``ip:10.255.1.24``
    * ``config_repo/s4.cfg`` was written by ``config_git.write_and_stage``,
      which strips that header, so it has no IP and groups as ``name:s4``

    Keyed separately they look like two devices. Both then migrate to
    ``golden/s4.cfg`` and the second silently overwrites the first — the exact
    data loss the merge detection exists to prevent.

    Every fixture in this file gave both copies the same header format, so none
    of them could catch it. These do.
    """

    HEADERED = ("! Golden config — s4 (10.255.1.24)\n"
                "! Saved: 2026-09-15 22:36:40\n"
                "! Source: show startup-config\n"
                "!\n"
                "hostname s4\n interface GigabitEthernet0/1\n")

    STRIPPED = "\n!\nhostname s4\n interface GigabitEthernet0/1\n"

    def _both_stores(self, lab):
        (lab / "golden_configs" / "s4.cfg").write_text(self.HEADERED, encoding="utf-8")
        (lab / "config_repo" / "s4.cfg").write_text(self.STRIPPED, encoding="utf-8")

    def test_counted_as_one_device_not_two(self, lab):
        self._both_stores(lab)
        report = migrate.plan("Lab")
        assert report["device_count"] == 1, (
            "the same device in two stores was counted twice; both would have "
            "migrated to the same path and one would have been overwritten")

    def test_detected_as_a_merge(self, lab):
        self._both_stores(lab)
        report = migrate.plan("Lab")
        assert report["merge_count"] == 1
        assert sorted(report["merges"][0]["stores"]) == ["config_repo", "golden_configs"]

    def test_reason_explains_the_format_difference(self, lab):
        self._both_stores(lab)
        reason = migrate.plan("Lab")["merges"][0]["reason"]
        assert "both stores" in reason

    def test_management_ip_survives_the_merge(self, lab):
        """The stripped copy has no IP. The group's IP must still be used.

        Losing it would leave a manifest entry with no address, breaking
        ``find_by_ip`` and therefore ``_find_golden_config_file``.
        """
        self._both_stores(lab)
        assert migrate.plan("Lab")["devices"][0]["mgmt_ip"] == "10.255.1.24"

    def test_manifest_records_the_ip_after_apply(self, lab):
        from modules.nsot.manifest import load
        self._both_stores(lab)
        migrate.apply("Lab")
        entries = list(load(str(lab / "config_repo"))["devices"].values())
        assert len(entries) == 1
        assert entries[0]["mgmt_ip"] == "10.255.1.24"

    def test_only_one_golden_file_results(self, lab):
        self._both_stores(lab)
        migrate.apply("Lab")
        golden = list((lab / "config_repo" / "golden").glob("*.cfg"))
        assert [p.name for p in golden] == ["s4.cfg"]

    def test_the_loser_is_backed_up(self, lab):
        self._both_stores(lab)
        migrate.apply("Lab")
        backup = lab / "config_repo" / ".nsot" / "migration-backup"
        assert any("s4.cfg" in f for f in os.listdir(backup))

    def test_scales_to_the_whole_fleet(self, lab):
        """Nine devices in two stores is nine devices, not eighteen."""
        # Real lab addressing: routers .11-.15, switches .21-.24. Deriving
        # both from the digit alone would give r1 and s1 the same address and
        # correctly merge them into one device.
        for name in ("r1", "r2", "r3", "r4", "r5", "s1", "s2", "s3", "s4"):
            base = 10 if name.startswith("r") else 20
            ip = f"10.255.1.{base + int(name[1])}"
            (lab / "golden_configs" / f"{name}.cfg").write_text(
                f"! Golden config — {name} ({ip})\n!\nhostname {name}\n",
                encoding="utf-8")
            (lab / "config_repo" / f"{name}.cfg").write_text(
                f"\n!\nhostname {name}\n", encoding="utf-8")
        report = migrate.plan("Lab")
        assert report["candidates"] == 18
        assert report["device_count"] == 9
        assert report["merge_count"] == 9


class TestMigrationMarker:
    """``.nsot/migrated.json`` — the guard's own record, not an inference.

    The first implementation computed ``already_migrated`` from
    ``os.path.isdir(repo/golden)`` and then never consumed it. Two things were
    wrong with that: ``golden/`` exists from ``init_repo`` onward, so the value
    was false in meaning as well as unused; and a computed check nothing reads
    is indistinguishable from no check at all.
    """

    def test_no_marker_before_migration(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        assert migrate.read_marker(str(lab / "config_repo")) is None
        assert migrate.plan("Lab")["already_migrated"] is False

    def test_golden_dir_alone_does_not_mean_migrated(self, lab):
        """The old signal. init_repo creates golden/, so it was always true."""
        from modules.nsot.repo import init_repo
        init_repo(str(lab / "config_repo"))
        assert os.path.isdir(lab / "config_repo" / "golden")
        assert migrate.plan("Lab")["already_migrated"] is False

    def test_marker_records_timestamp_and_commit(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        result = migrate.apply("Lab")
        marker = migrate.read_marker(str(lab / "config_repo"))
        assert marker is not None
        assert marker["migrated_at"].endswith("Z")
        assert len(marker["commit"]) == 40
        assert marker["commit"] == result["marker"]["commit"]
        assert marker["devices"] == ["R1"]

    def test_marker_points_at_the_migration_commit(self, lab):
        from modules.nsot.repo import git
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        repo = str(lab / "config_repo")
        _rc, head, _ = git(repo, "rev-parse", "HEAD")
        assert migrate.read_marker(repo)["commit"] == head.strip()

    def test_marker_is_not_committed(self, lab):
        """Local installation state, like the backup dir — the commit is the
        version-controlled record."""
        from modules.nsot.repo import git
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        repo = str(lab / "config_repo")
        _rc, tracked, _ = git(repo, "ls-files", ".nsot/migrated.json")
        assert tracked.strip() == ""
        _rc, status, _ = git(repo, "status", "--porcelain")
        assert "migrated.json" not in status, "marker left the worktree dirty"

    def test_plan_reports_already_migrated_afterwards(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        report = migrate.plan("Lab")
        assert report["already_migrated"] is True
        assert report["marker"]["devices"] == ["R1"]


class TestSecondRunIsRefused:
    """The bug this closes, reproduced.

    The two stores hold the same device in different shapes: ``golden_configs/``
    keeps the NMAS header, ``config_repo/`` has it stripped. The first run moves
    the repo copy and wins; a second run finds only the *other* copy, renders it,
    and commits the whitespace difference — nine files changed, for nothing.
    """

    def _both_shapes(self, lab):
        (lab / "golden_configs" / "s4.cfg").write_text(
            "! Golden config — s4 (10.255.1.24)\n!\n!\nhostname s4\n", encoding="utf-8")
        (lab / "config_repo" / "s4.cfg").write_text(
            "hostname s4\n", encoding="utf-8")

    def test_apply_refuses_with_the_sha(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        first = migrate.apply("Lab")
        second = migrate.apply("Lab")
        assert second["ok"] is False
        assert second["error"] == f"already migrated at {first['marker']['commit']}"
        assert second["already_migrated"] is True

    def test_refusal_creates_no_commit(self, lab):
        from modules.nsot.repo import git
        self._both_shapes(lab)
        migrate.apply("Lab")
        repo = str(lab / "config_repo")
        _rc, before, _ = git(repo, "rev-parse", "HEAD")
        migrate.apply("Lab")
        _rc, after, _ = git(repo, "rev-parse", "HEAD")
        assert before == after

    def test_refusal_leaves_the_golden_file_byte_identical(self, lab):
        self._both_shapes(lab)
        migrate.apply("Lab")
        target = lab / "config_repo" / "golden" / "s4.cfg"
        before = target.read_bytes()
        migrate.apply("Lab")
        assert target.read_bytes() == before

    def test_refusal_creates_no_second_baseline_tag(self, lab):
        from modules.nsot.repo import git
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        migrate.apply("Lab")
        _rc, tags, _ = git(str(lab / "config_repo"), "tag", "--list", "baseline/*")
        assert len(tags.split()) == 1

    def test_golden_configs_is_no_longer_an_input(self, lab):
        """One-directional: the old store may be read for a lookup, never as
        migration input again."""
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        (lab / "golden_configs" / "R2.cfg").write_text(
            "! Golden config — R2 (203.0.113.2)\nhostname R2\n", encoding="utf-8")
        assert migrate.plan("Lab")["candidates"] == 0


class TestNeverCommitsAnUnchangedTree:
    """Separate from the guard, and it has to hold without it.

    ``save_golden`` already refuses to rewrite a file whose content matches and
    refuses to commit when nothing is staged. Migration now matches that, so an
    empty commit is impossible even with the marker deleted.
    """

    def test_bypassed_guard_still_creates_no_commit(self, lab):
        from modules.nsot.repo import git
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        repo = str(lab / "config_repo")
        _rc, before, _ = git(repo, "rev-list", "--count", "HEAD")

        os.remove(migrate.marker_path(repo))   # simulate the guard being bypassed
        result = migrate.apply("Lab")

        _rc, after, _ = git(repo, "rev-list", "--count", "HEAD")
        assert result["committed"] is False
        assert before == after, "an unchanged tree produced a commit"

    def test_unchanged_golden_file_is_not_rewritten(self, lab):
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        repo = str(lab / "config_repo")
        target = lab / "config_repo" / "golden" / "R1.cfg"
        stamp = os.stat(target).st_mtime_ns

        os.remove(migrate.marker_path(repo))
        migrate.apply("Lab")
        assert os.stat(target).st_mtime_ns == stamp

    def test_allow_empty_is_never_used(self, lab):
        """A commit that cannot be empty is stronger than a check that says so."""
        import inspect
        code = [ln.split("#", 1)[0] for ln in
                inspect.getsource(migrate.apply).splitlines()]
        assert "--allow-empty" not in "\n".join(code)


class TestPlatformComesFromInventory:
    """A .cfg cannot say whether the box is a C8000v or a vIOS-L2.

    Migration builds its entries from config files, so before this the manifest
    carried an empty platform for every device — and parser selection, which
    reads it, silently fell back to the default dialect.
    """

    def _inventory(self, lab, rows):
        header = ("hostname,device_type,ip,username,password,secret,role,"
                  "device_uid,platform\n")
        body = "".join(
            f"{r['hostname']},{r.get('device_type', 'cisco_ios')},{r['ip']},"
            f"u,p,s,,,{r.get('platform', '')}\n" for r in rows)
        (lab / "devices.csv").write_text(header + body, encoding="utf-8")

    def test_csv_platform_column_reaches_the_manifest(self, lab):
        from modules.nsot.manifest import load
        self._inventory(lab, [{"hostname": "R1", "ip": "203.0.113.1",
                               "platform": "cisco_iosxe"}])
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        entry = next(iter(load(str(lab / "config_repo"))["devices"].values()))
        assert entry["platform"] == "cisco_iosxe"

    def test_platform_is_derived_when_the_column_is_blank(self, lab):
        from modules.nsot.manifest import load
        self._inventory(lab, [{"hostname": "S1", "ip": "203.0.113.21",
                               "device_type": "cisco_ios"}])
        _write(lab, "golden_configs", "S1.cfg", "S1", "203.0.113.21", "hostname S1")
        migrate.apply("Lab")
        entry = next(iter(load(str(lab / "config_repo"))["devices"].values()))
        assert entry["platform"] == "cisco_ios"

    def test_a_correction_reaches_the_manifest_after_migration(self, lab):
        """The reason this cannot be migration-time only: a platform recorded
        wrongly and fixed later must still reach the manifest, because Phase 4
        onboarding reads it from there."""
        from modules.nsot.manifest import load, sync_platforms
        self._inventory(lab, [{"hostname": "R1", "ip": "203.0.113.1",
                               "platform": "cisco_ios"}])
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        repo = str(lab / "config_repo")

        self._inventory(lab, [{"hostname": "R1", "ip": "203.0.113.1",
                               "platform": "cisco_iosxe"}])
        result = sync_platforms(repo, "Lab")

        assert result["updated"] == [{"name": "R1", "from": "cisco_ios",
                                      "to": "cisco_iosxe"}]
        entry = next(iter(load(repo)["devices"].values()))
        assert entry["platform"] == "cisco_iosxe"

    def test_sync_is_idempotent(self, lab):
        from modules.nsot.manifest import sync_platforms
        self._inventory(lab, [{"hostname": "R1", "ip": "203.0.113.1",
                               "platform": "cisco_iosxe"}])
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        repo = str(lab / "config_repo")
        assert sync_platforms(repo, "Lab")["updated"] == []

    def test_sync_creates_no_commit(self, lab):
        """Runs on the refresh thread — manifest only, like pending renames."""
        from modules.nsot.manifest import sync_platforms
        from modules.nsot.repo import git
        self._inventory(lab, [{"hostname": "R1", "ip": "203.0.113.1",
                               "platform": "cisco_ios"}])
        _write(lab, "golden_configs", "R1.cfg", "R1", "203.0.113.1", "hostname R1")
        migrate.apply("Lab")
        repo = str(lab / "config_repo")
        _rc, before, _ = git(repo, "rev-list", "--count", "HEAD")

        self._inventory(lab, [{"hostname": "R1", "ip": "203.0.113.1",
                               "platform": "cisco_iosxe"}])
        sync_platforms(repo, "Lab")

        _rc, after, _ = git(repo, "rev-list", "--count", "HEAD")
        assert before == after
