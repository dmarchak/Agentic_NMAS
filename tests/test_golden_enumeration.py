"""One enumerator for golden configs.

Stage 3.3's finding. `ai_assistant._list_golden_configs()` was

    gdir = _get_golden_configs_dir()          # data/lists/<slug>/golden_configs/
    for fname in sorted(os.listdir(gdir)):    # ...and nothing else

while `_load_golden_config_file()` resolved through the manifest.
**Enumeration and content came from different stores**, and seventeen
executable call sites across nine modules asked the enumerator which devices
have a golden: the drift checker, the event monitor, `check_runner` (twice),
`pipeline_builder`, `/templatize/report`, `/list/golden_configs` and six paths
in the AI tool layer.

The nine reference devices were enumerable only because their pre-migration
files still sat in `golden_configs/`. **That coverage was inherited, not
designed.** A device onboarded after the migration has a golden in the repo
and no legacy file, so it was checked by nothing -- and reported by the event
monitor as having no golden at all, while its config sat in `config_repo/`.

Every test here fails against `os.listdir`.
"""

import os
import time

import pytest

from tests.js_source import with_loaded_scripts

CONFIG = "hostname {name}\n!\nend\n"

# The legacy header carries an em dash. It is what the scan matches on, so it
# is reproduced here verbatim rather than normalised.
LEGACY_HEADER = "! Golden config — {name} ({ip})\n"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A repo holding r1 and r2, and a legacy store holding only r1."""
    from modules.nsot import repo as _repo

    list_dir = tmp_path / "lab"
    repo_dir = str(list_dir / "config_repo")
    os.makedirs(repo_dir, exist_ok=True)

    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
    monkeypatch.setattr("modules.config.get_current_list_data_dir",
                        lambda: str(list_dir))
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "n@l"}.get(key, default))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)

    _repo.init_repo(repo_dir)
    _repo.save_golden("lab", [
        _repo.GoldenItem("r1", CONFIG.format(name="r1"), "203.0.113.1"),
        _repo.GoldenItem("r2", CONFIG.format(name="r2"), "203.0.113.2"),
    ], source="test", actor="test", allow_new=True)

    # The legacy store holds r1 only -- the pre-migration world. r2 is the
    # post-migration device that used to be invisible.
    legacy = list_dir / "golden_configs"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "r1.cfg").write_text(
        LEGACY_HEADER.format(name="r1", ip="203.0.113.1") + CONFIG.format(name="r1"),
        encoding="utf-8")

    return {"list_dir": list_dir, "repo": repo_dir, "legacy": legacy}


class TestTheRepoIsThePopulation:
    """The headline: a device with no legacy file is still a device."""

    def test_a_repo_only_device_is_enumerated(self, lab):
        from modules.ai_assistant import _list_golden_configs

        names = {e["hostname"] for e in _list_golden_configs()}
        assert names == {"r1", "r2"}, (
            "r2 has a golden in config_repo/ and no legacy file; listing the "
            "legacy directory reports only r1")

    def test_an_empty_legacy_store_changes_nothing(self, lab):
        """The migration permits emptying it. Nothing may depend on it."""
        from modules.ai_assistant import _list_golden_configs

        for f in lab["legacy"].iterdir():
            f.unlink()
        names = {e["hostname"] for e in _list_golden_configs()}
        assert names == {"r1", "r2"}

    def test_the_ip_comes_from_the_manifest(self, lab):
        from modules.ai_assistant import _list_golden_configs

        by_name = {e["hostname"]: e for e in _list_golden_configs()}
        assert by_name["r2"]["device_ip"] == "203.0.113.2"

    def test_a_manifest_entry_whose_file_is_gone_is_not_listed(self, lab):
        """`list_goldens` answers "has a golden", not "is known"."""
        from modules.ai_assistant import _list_golden_configs

        os.remove(os.path.join(lab["repo"], "golden", "r2.cfg"))
        names = {e["hostname"] for e in _list_golden_configs()}
        assert names == {"r1"}


class TestSavedAtIsTheCommitNotTheMtime:
    """The 1.4 correction, applied to every reader instead of one.

    Measured on s1 during Stage 1: the template preview reported "captured
    2026-09-15 22:35", which was exactly the legacy file's mtime, for a golden
    committed the same day. The `! Saved:` header was removed precisely so a
    save would not produce a diff on every write, which leaves the commit as
    the only honest record of when a golden was promoted.
    """

    def test_it_is_an_iso_commit_timestamp(self, lab):
        from modules.ai_assistant import _list_golden_configs

        saved = {e["hostname"]: e["saved_at"] for e in _list_golden_configs()}
        assert saved["r1"].startswith("20") and "T" in saved["r1"], saved

    def test_touching_the_file_does_not_move_it(self, lab):
        """Both copies are touched, deliberately.

        Touching only the repo file left this passing against the old
        enumerator, which read the LEGACY file's mtime -- a control that
        could not fail, testing a path the code under test never took.
        """
        from modules.ai_assistant import _list_golden_configs

        before = {e["hostname"]: e["saved_at"] for e in _list_golden_configs()}
        for path in (os.path.join(lab["repo"], "golden", "r1.cfg"),
                     str(lab["legacy"] / "r1.cfg")):
            os.utime(path, (0, 0))
        after = {e["hostname"]: e["saved_at"] for e in _list_golden_configs()}
        assert after == before, "an mtime is not a promotion"


class TestOneSubprocessForTheWholeStore:
    """Enumeration is called from panels, the scheduler and the AI loop.

    `git log -1` per device is nine processes per refresh on the reference
    fleet, and the shape gets worse with every device added.
    """

    def test_commit_times_take_one_git_call(self, lab, monkeypatch):
        from modules.nsot import repo as _repo

        calls = []
        real = _repo.git
        monkeypatch.setattr(_repo, "git",
                            lambda r, *a: calls.append(a) or real(r, *a))
        _repo.golden_commit_times(lab["repo"])
        assert len(calls) == 1, calls

    def test_every_device_gets_a_time_from_that_one_call(self, lab):
        from modules.nsot import repo as _repo

        times = _repo.golden_commit_times(lab["repo"])
        assert {"golden/r1.cfg", "golden/r2.cfg"} <= set(times)

    def test_the_newest_commit_wins(self, lab):
        """`--name-only` prints newest first; the first sighting is the one."""
        from modules.nsot import repo as _repo

        first = _repo.golden_commit_times(lab["repo"])["golden/r1.cfg"]
        time.sleep(1.1)
        _repo.save_golden("lab", [_repo.GoldenItem("r1", "hostname r1\n!\nchanged\nend\n",
                                                   "203.0.113.1")],
                          source="test", actor="test")
        second = _repo.golden_commit_times(lab["repo"])["golden/r1.cfg"]
        assert second > first, (first, second)


class TestTheLegacyStoreIsNotDroppedSilently:
    """Retiring an enumerator must not lose a device on the day it changes."""

    def test_a_legacy_only_device_is_still_enumerated(self, lab):
        from modules.ai_assistant import _list_golden_configs

        (lab["legacy"] / "r9.cfg").write_text(
            LEGACY_HEADER.format(name="r9", ip="203.0.113.9") + "hostname r9\n",
            encoding="utf-8")
        by_name = {e["hostname"]: e for e in _list_golden_configs()}
        assert "r9" in by_name
        assert by_name["r9"]["legacy"] is True

    def test_a_device_in_both_stores_is_reported_once(self, lab):
        from modules.ai_assistant import _list_golden_configs

        entries = [e for e in _list_golden_configs() if e["hostname"] == "r1"]
        assert len(entries) == 1
        assert entries[0]["legacy"] is False, "the repo copy is the real one"

    def test_the_retirement_condition_is_measurable(self, lab):
        from modules.nsot.repo import legacy_only_goldens, list_goldens

        known = {e["hostname"] for e in list_goldens("lab")}
        assert legacy_only_goldens(str(lab["list_dir"]), known) == [], (
            "r1 is in the manifest, so the legacy store holds nothing unique "
            "-- this is what 'the legacy store can be deleted' looks like")

    def test_it_names_what_is_still_only_legacy(self, lab):
        from modules.nsot.repo import legacy_only_goldens

        (lab["legacy"] / "r9.cfg").write_text(
            LEGACY_HEADER.format(name="r9", ip="203.0.113.9") + "hostname r9\n",
            encoding="utf-8")
        only = legacy_only_goldens(str(lab["list_dir"]), {"r1", "r2"})
        assert [e["hostname"] for e in only] == ["r9"]


class TestEnumerationFailsLoudly:
    """Returning [] is indistinguishable from a fleet with no goldens, and
    several callers treat that as nothing to do."""

    def test_a_broken_repo_logs_an_error(self, lab, monkeypatch, caplog):
        import logging

        from modules import ai_assistant

        monkeypatch.setattr("modules.nsot.repo.list_goldens",
                            lambda name: (_ for _ in ()).throw(OSError("boom")))
        with caplog.at_level(logging.ERROR):
            assert ai_assistant._list_golden_configs() == []
        assert any("enumeration failed" in r.message for r in caplog.records)


class TestTheRetirementConditionHasAnEntryPoint:
    """A measurement nobody can see is a measurement nobody will act on.

    `test_blueprint_reachability.py` checks whole blueprints, so a new route
    inside an already-reachable one passes it without being reachable itself.
    This is the per-route version for the one route added here.
    """

    @pytest.fixture(scope="class")
    def page(self):
        import app as nmas

        return with_loaded_scripts(nmas.app.test_client().get("/").get_data(as_text=True))

    def test_the_page_calls_the_route(self, page):
        assert "/golden/legacy_store" in page

    def test_the_card_that_renders_it_is_called(self, page):
        assert page.count("_gLegacyStoreCard") >= 2, (
            "defined and called, not defined only")

    def test_the_route_reports_retirability(self, lab, monkeypatch):
        import app as nmas

        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        body = nmas.app.test_client().get("/golden/legacy_store").get_json()
        assert body["ok"] is True
        # r1 is in both stores, r2 only in the repo: nothing is legacy-only.
        assert body["retirable"] is True
        assert body["only_legacy"] == []

    def test_a_legacy_only_device_blocks_retirement(self, lab, monkeypatch):
        import app as nmas

        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        (lab["legacy"] / "r9.cfg").write_text(
            LEGACY_HEADER.format(name="r9", ip="203.0.113.9") + "hostname r9\n",
            encoding="utf-8")
        body = nmas.app.test_client().get("/golden/legacy_store").get_json()
        assert body["retirable"] is False
        assert [d["hostname"] for d in body["only_legacy"]] == ["r9"]
