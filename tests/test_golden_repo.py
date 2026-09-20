"""The golden config repository: one write path, committed immediately.

Covers the Phase 2 acceptance criteria — one call is one commit, unchanged
devices create no commit, timestamps live in git rather than the file, renames
preserve history through ``git log --follow``, and concurrent writers do not
collide on ``.git/index.lock``.
"""

import os
import subprocess
import threading

import pytest

from modules.nsot import manifest as M
from modules.nsot import repo as R

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git is not available",
)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """An isolated list directory with a settings stub."""
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost",
                            "nsot_device_tag_retention": 50,
                        }.get(key, default))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    return str(list_dir / "config_repo")


def _item(name="R1", body="hostname R1\n", ip="203.0.113.1", nb_id=42):
    return R.GoldenItem(name, body, ip, netbox_id=nb_id)


def _commit_count(repo):
    rc, out, _ = R.git(repo, "rev-list", "--count", "HEAD")
    return int(out) if rc == 0 else 0


class TestOneCallOneCommit:
    def test_single_device_creates_one_commit(self, lab):
        result = R.save_golden("Lab", [_item()])
        assert result["ok"] and result["commit"]
        assert result["changed"] == ["R1"]

    def test_save_all_is_one_commit_not_n(self, lab):
        """A nine-device Save All is one network-wide snapshot."""
        R.init_repo(lab)                       # so `before` excludes the init commit
        items = [_item(f"R{i}", f"hostname R{i}\n", f"203.0.113.{i}", nb_id=i)
                 for i in range(1, 10)]
        before = _commit_count(lab)
        result = R.save_golden("Lab", items, source="save_all")
        assert len(result["changed"]) == 9
        assert _commit_count(lab) == before + 1

    def test_unchanged_device_creates_no_commit(self, lab):
        R.save_golden("Lab", [_item()])
        after_first = _commit_count(lab)
        result = R.save_golden("Lab", [_item()])
        assert result["commit"] == ""
        assert result["unchanged"] == ["R1"]
        assert _commit_count(lab) == after_first

    def test_acceptance_two_saves_one_changed(self, lab):
        """Three devices twice, one changed the second time → exactly two commits."""
        items = [_item("R1", "hostname R1\n", "203.0.113.1", 1),
                 _item("R3", "hostname R3\n", "203.0.113.3", 3),
                 _item("S3", "hostname S3\n", "203.0.113.13", 13)]
        first = R.save_golden("Lab", items, source="save_all")
        assert len(first["changed"]) == 3
        assert sum(1 for t in first["tags"] if t.startswith("golden/")) == 3
        assert sum(1 for t in first["tags"] if t.startswith("baseline/")) == 1

        items[1] = _item("R3", "hostname R3\n ip routing\n", "203.0.113.3", 3)
        second = R.save_golden("Lab", items, source="save_all")
        assert second["changed"] == ["R3"]
        assert second["unchanged"] == ["R1", "S3"]
        assert _commit_count(lab) == 3          # init + two golden commits


class TestFileContent:
    def test_one_stable_header_line(self, lab):
        R.save_golden("Lab", [_item()])
        content = open(os.path.join(lab, "golden", "R1.cfg"), encoding="utf-8").read()
        assert content.startswith("! Golden config — R1 (203.0.113.1)")

    def test_no_saved_or_source_headers(self, lab):
        """They created a diff on every save even when nothing changed."""
        R.save_golden("Lab", [_item()])
        content = open(os.path.join(lab, "golden", "R1.cfg"), encoding="utf-8").read()
        assert "! Saved:" not in content
        assert "! Source:" not in content

    def test_identical_config_produces_identical_file(self, lab):
        R.save_golden("Lab", [_item()])
        first = open(os.path.join(lab, "golden", "R1.cfg"), encoding="utf-8").read()
        R.save_golden("Lab", [_item()])
        assert open(os.path.join(lab, "golden", "R1.cfg"), encoding="utf-8").read() == first


class TestTrailersAndTags:
    def test_trailers_carry_provenance(self, lab):
        R.save_golden("Lab", [_item()], source="pipeline", actor="dustin",
                      pipeline_id="cfg-7f3a")
        _rc, out, _ = R.git(lab, "log", "-1", "--format=%B")
        assert "Source: pipeline" in out
        assert "Actor: dustin" in out
        assert "Pipeline-Id: cfg-7f3a" in out
        assert "Device-Id: nb:42" in out
        assert "Device-Name: R1" in out

    def test_tags_are_utc_without_colons(self, lab):
        result = R.save_golden("Lab", [_item()])
        tag = result["tags"][0]
        assert tag.startswith("golden/R1/") and tag.endswith("Z")
        assert ":" not in tag

    def test_baseline_tag_on_save_all(self, lab):
        result = R.save_golden("Lab", [_item()], source="save_all")
        assert any(t.startswith("baseline/") for t in result["tags"])

    def test_single_manual_save_has_no_baseline_tag(self, lab):
        result = R.save_golden("Lab", [_item()], source="manual")
        assert not any(t.startswith("baseline/") for t in result["tags"])


class TestRenamePreservesHistory:
    """The acceptance test: git log --follow must survive a rename."""

    def test_follow_returns_pre_rename_commits(self, lab):
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        R.save_golden("Lab", [_item("R1", "hostname R1\n ip routing\n")])

        # An inventory refresh notices the rename — manifest only, no git.
        M.record_pending_rename(lab, "nb:42", "R1-CORE")
        assert len(M.pending_renames(lab)) == 1

        R.save_golden("Lab", [_item("R1-CORE", "hostname R1-CORE\n ip routing\n")])

        history = R.golden_history(lab, "R1-CORE")
        assert len(history) >= 3, "history did not survive the rename"
        assert any(h["source"] == "rename" for h in history)
        subjects = [h["subject"] for h in history]
        assert any("R1 → R1-CORE" in s for s in subjects)

    def test_rename_is_its_own_commit(self, lab):
        """A rename mixed with content edits defeats git's rename detection."""
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        M.record_pending_rename(lab, "nb:42", "R1-CORE")
        R.save_golden("Lab", [_item("R1-CORE", "hostname R1-CORE\n")])

        _rc, out, _ = R.git(lab, "log", "--format=%s")
        subjects = out.splitlines()
        rename_subjects = [s for s in subjects if s.startswith("rename:")]
        assert len(rename_subjects) == 1
        # The rename commit moves one path pair and edits no config. It also
        # carries .nsot/manifest.json — the identity mapping has to travel with
        # the move or a restore at this commit cannot resolve the new name.
        _rc, files, _ = R.git(lab, "show", "--name-status", "--format=",
                              f"HEAD~{subjects.index(rename_subjects[0])}")
        statuses = dict(reversed(ln.split("\t", 1)) for ln in files.splitlines())
        golden = {p: st for p, st in statuses.items() if p.startswith("golden/")}
        assert len(golden) == 1, f"rename commit touched {golden}"
        assert next(iter(golden.values())).startswith("R"), "not detected as a rename"
        assert statuses.get(".nsot/manifest.json") == "M"

    def test_old_file_is_gone_after_rename(self, lab):
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        M.record_pending_rename(lab, "nb:42", "R1-CORE")
        R.save_golden("Lab", [_item("R1-CORE", "hostname R1-CORE\n")])
        assert not os.path.exists(os.path.join(lab, "golden", "R1.cfg"))
        assert os.path.exists(os.path.join(lab, "golden", "R1-CORE.cfg"))

    def test_manifest_resolves_both_names_while_pending(self, lab):
        """The golden config must stay reachable under either name."""
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        M.record_pending_rename(lab, "nb:42", "R1-CORE")
        assert M.find_by_name(lab, "R1")[0] == "nb:42"
        assert M.find_by_name(lab, "R1-CORE")[0] == "nb:42"

    def test_refresh_does_not_commit(self, lab):
        """Amendment 1: recording a rename must not create a commit."""
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        before = _commit_count(lab)
        M.record_pending_rename(lab, "nb:42", "R1-CORE")
        assert _commit_count(lab) == before


class TestHistoryReading:
    def test_history_reports_source_and_actor(self, lab):
        R.save_golden("Lab", [_item()], source="ai", actor="ai-agent")
        entry = R.golden_history(lab, "R1")[0]
        assert entry["source"] == "ai" and entry["actor"] == "ai-agent"
        assert entry["timestamp"]                  # from the commit, not file mtime

    def test_golden_at_returns_the_old_version(self, lab):
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        first_sha = R.golden_history(lab, "R1")[0]["sha"]
        R.save_golden("Lab", [_item("R1", "hostname R1\n ip routing\n")])
        old = R.golden_at(lab, "R1", first_sha)
        assert "ip routing" not in old
        assert "ip routing" in R.golden_at(lab, "R1", "HEAD")

    def test_devices_at_lists_the_tagged_tree(self, lab):
        items = [_item("R1", "a\n", "203.0.113.1", 1), _item("R2", "b\n", "203.0.113.2", 2)]
        result = R.save_golden("Lab", items, source="save_all")
        baseline = next(t for t in result["tags"] if t.startswith("baseline/"))
        assert set(R.devices_at(lab, baseline)) == {"R1", "R2"}

    def test_baselines_are_listed_newest_first(self, lab):
        R.save_golden("Lab", [_item("R1", "a\n", "203.0.113.1", 1)], source="save_all")
        R.save_golden("Lab", [_item("R1", "b\n", "203.0.113.1", 1)], source="save_all")
        baselines = R.list_baselines(lab)
        assert len(baselines) == 2, "two save_all runs must yield two baseline tags"
        assert all("tag" in b and "created" in b for b in baselines)


class TestCiNotes:
    def test_note_attaches_to_the_exact_commit(self, lab):
        result = R.save_golden("Lab", [_item()])
        sha = result["commit"]
        assert R.add_ci_note(lab, sha, "verify-ospf", 17, "SUCCESS",
                             "http://ci.invalid/17")["ok"]
        note = R.get_ci_note(lab, sha)
        assert note["job"] == "verify-ospf" and note["result"] == "SUCCESS"

    def test_absent_note_returns_none(self, lab):
        result = R.save_golden("Lab", [_item()])
        assert R.get_ci_note(lab, result["commit"]) is None


class TestRobustness:
    def test_concurrent_saves_do_not_collide(self, lab):
        """Two threads calling save_golden must not hit .git/index.lock."""
        R.init_repo(lab)
        errors, results = [], []

        def worker(n):
            try:
                results.append(R.save_golden(
                    "Lab", [_item(f"R{n}", f"hostname R{n}\n", f"203.0.113.{n}", n)]))
            except Exception as exc:          # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        assert all(r["ok"] for r in results), [r.get("error") for r in results]
        assert _commit_count(lab) == 3          # init + two commits

    def test_stale_index_lock_is_cleared(self, lab):
        import time as _time
        R.init_repo(lab)
        lock_path = os.path.join(lab, ".git", "index.lock")
        open(lock_path, "w").close()
        old = _time.time() - (R.STALE_LOCK_SECONDS + 60)
        os.utime(lock_path, (old, old))

        result = R.save_golden("Lab", [_item()])
        assert result["ok"], result.get("error")
        assert not os.path.exists(lock_path)

    def test_fresh_lock_is_not_removed(self, lab):
        R.init_repo(lab)
        lock_path = os.path.join(lab, ".git", "index.lock")
        open(lock_path, "w").close()
        R._clear_stale_lock(lab)
        assert os.path.exists(lock_path), "a live lock was removed"
        os.remove(lock_path)

    def test_tag_retention_prunes_device_tags_only(self, lab, monkeypatch):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "nmas@localhost",
                                "nsot_device_tag_retention": 3,
                            }.get(key, default))
        for i in range(6):
            R.save_golden("Lab", [_item("R1", f"hostname R1\n line {i}\n")],
                          source="save_all")

        _rc, device_tags, _ = R.git(lab, "tag", "--list", "golden/R1/*")
        _rc, baseline_tags, _ = R.git(lab, "tag", "--list", "baseline/*")
        assert len([t for t in device_tags.splitlines() if t]) == 3
        assert len([t for t in baseline_tags.splitlines() if t]) == 6, \
            "baseline tags must never be pruned"

    def test_commits_survive_tag_pruning(self, lab, monkeypatch):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "nmas@localhost",
                                "nsot_device_tag_retention": 2,
                            }.get(key, default))
        for i in range(5):
            R.save_golden("Lab", [_item("R1", f"hostname R1\n line {i}\n")])
        assert len(R.golden_history(lab, "R1")) == 5


class TestGitignoreReachesExistingRepos:
    """A rule added after a repo exists must still reach that repo.

    The live lab repo was created with a two-line ``.gitignore`` and never got
    ``.nsot/migration-backup/`` — because ``init_repo()`` wrote the file only
    when absent, and later only ``init_repo()`` called the append-if-missing
    helper. Result: nine migration backups committed into version control, and
    ``.nsot/migrated.json`` showing as untracked. This is the fifth instance of
    one shape in this project, so it gets a test of its own.
    """

    def _gitignore(self, repo):
        with open(os.path.join(repo, ".gitignore"), encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip()]

    def test_a_fresh_repo_carries_every_rule(self, lab):
        R.init_repo(lab)
        assert set(R.GITIGNORE_RULES) <= set(self._gitignore(lab))

    def test_a_stale_gitignore_is_topped_up_on_next_touch(self, lab):
        """The live case: the repo predates the rules."""
        R.init_repo(lab)
        path = os.path.join(lab, ".gitignore")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("*.swp\n*.tmp\n")           # the repo as it was created

        R.git(lab, "status", "--porcelain")      # any touch at all, even a read

        rules = self._gitignore(lab)
        assert ".nsot/migration-backup/" in rules
        assert ".nsot/migrated.json" in rules
        assert ".nsot/staging/" in rules

    def test_top_up_preserves_operator_additions(self, lab):
        R.init_repo(lab)
        path = os.path.join(lab, ".gitignore")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("*.swp\n# my own rule\nscratch/\n")

        R.git(lab, "status", "--porcelain")

        rules = self._gitignore(lab)
        assert "scratch/" in rules and "# my own rule" in rules
        assert set(R.GITIGNORE_RULES) <= set(rules)

    def test_it_is_idempotent(self, lab):
        R.init_repo(lab)
        R.git(lab, "status", "--porcelain")
        first = self._gitignore(lab)
        for _ in range(3):
            R.git(lab, "status", "--porcelain")
        assert self._gitignore(lab) == first

    def test_a_non_repo_directory_is_left_alone(self, lab, tmp_path):
        """Hygiene must not create files in a directory that is not a repo."""
        plain = tmp_path / "not-a-repo"
        plain.mkdir()
        R.ensure_repo_hygiene(str(plain))
        assert os.listdir(plain) == []

    def test_migration_backups_are_ignored_not_committed(self, lab):
        """What the live repo got wrong, end to end."""
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        backup = os.path.join(lab, ".nsot", "migration-backup")
        os.makedirs(backup, exist_ok=True)
        with open(os.path.join(backup, "golden_configs-R1.cfg"), "w",
                  encoding="utf-8") as fh:
            fh.write("! backup\n")

        R.save_golden("Lab", [_item("R1", "hostname R1\n ip routing\n")])

        _rc, tracked, _ = R.git(lab, "ls-files", ".nsot/migration-backup")
        assert tracked.strip() == "", "a migration backup reached version control"


class TestManifestTravelsWithTheCommit:
    """A clone or bundle restore must carry the identity mapping.

    Without ``.nsot/manifest.json`` at the restored commit,
    ``_find_golden_config_file()`` finds no entry and falls through to the
    deprecated legacy header scan — which reads ``golden_configs/``, a
    directory a restore does not recreate.
    """

    def _tracked_at_head(self, repo):
        _rc, out, _ = R.git(repo, "show", "--name-only", "--format=", "HEAD")
        return out.split()

    def test_golden_commit_carries_the_manifest(self, lab):
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        assert ".nsot/manifest.json" in self._tracked_at_head(lab)

    def test_rename_commit_carries_the_manifest(self, lab):
        """The bug: the manifest was updated *after* the rename commit, so the
        commit that moved the file did not record where it moved to."""
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        M.record_pending_rename(lab, "nb:42", "R1-CORE")
        R.apply_pending_renames(lab)

        _rc, subject, _ = R.git(lab, "log", "-1", "--format=%s")
        assert subject.startswith("rename:")
        assert ".nsot/manifest.json" in self._tracked_at_head(lab)

    def test_the_manifest_at_the_rename_commit_names_the_new_file(self, lab):
        import json
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        M.record_pending_rename(lab, "nb:42", "R1-CORE")
        R.apply_pending_renames(lab)

        _rc, blob, _ = R.git(lab, "show", "HEAD:.nsot/manifest.json")
        entry = json.loads(blob)["devices"]["nb:42"]
        assert entry["name"] == "R1-CORE"
        assert entry["golden"] == "golden/R1-CORE.cfg"
        assert entry["pending_rename"] is None

    def test_the_manifest_is_never_left_uncommitted(self, lab):
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        M.record_pending_rename(lab, "nb:42", "R1-CORE")
        R.apply_pending_renames(lab)
        _rc, status, _ = R.git(lab, "status", "--porcelain", ".nsot/manifest.json")
        assert status.strip() == ""

    def test_a_template_commit_does_not_touch_the_manifest(self, lab):
        """Confirming the other half: save_templates has no business changing
        identity, so a template commit must not carry a manifest diff."""
        R.save_golden("Lab", [_item("R1", "hostname R1\n")])
        _rc, before, _ = R.git(lab, "rev-parse", "HEAD:.nsot/manifest.json")

        os.makedirs(os.path.join(lab, "templates"), exist_ok=True)
        with open(os.path.join(lab, "templates", "x.j2"), "w", encoding="utf-8") as fh:
            fh.write("hostname {{ hostname }}\n")
        R.save_templates("Lab", ["x.j2"])

        _rc, after, _ = R.git(lab, "rev-parse", "HEAD:.nsot/manifest.json")
        assert before == after
        _rc, subject, _ = R.git(lab, "log", "-1", "--format=%s")
        assert subject.startswith("template:")
