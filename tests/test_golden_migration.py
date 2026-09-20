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
