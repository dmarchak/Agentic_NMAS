"""A baseline earned writes an event a host service may wait on (C553; Phase 3, P3-2).

`modules/nsot/baseline_event.py`: the post-commit hook writes
``<DATA_DIR>/events/baseline-earned/<network>`` when the commit's tags hold a baseline, names
no tool, and never blocks the commit. The lab's startup sync is started by a path unit watching
the file (lab tooling, `deploy/systemd/clab-sync.path`); that unit is checked here against the
path the product writes, so the two cannot drift apart.
"""

import json
import os
import re

import pytest

from modules.nsot import baseline_event as BE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = "baseline/20261008T171500Z"


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return tmp_path


class TestTheHook:
    def test_a_baseline_earned_writes_its_event(self, data):
        got = BE.hook({"list_name": "Default", "sha": "abc123", "tags": [
            "golden/r1/20261008T171500Z", TAG, "golden-state/20261008T171500Z"]})
        assert got["ok"], got
        path = data / "events" / "baseline-earned" / "Default"
        body = json.loads(path.read_text())
        assert body["tag"] == TAG and body["commit"] == "abc123" and body["list"] == "Default"
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", body["at"])

    def test_no_baseline_writes_nothing(self, data):
        got = BE.hook({"list_name": "Default", "sha": "abc", "tags": ["golden/r1/x"]})
        assert got == {"ok": True, "message": "no baseline earned"}
        assert not (data / "events").exists()

    def test_a_later_baseline_replaces_the_event(self, data):
        BE.hook({"list_name": "Default", "sha": "a", "tags": [TAG]})
        BE.hook({"list_name": "Default", "sha": "b", "tags": ["baseline/20261008T180000Z"]})
        body = json.loads((data / "events" / "baseline-earned" / "Default").read_text())
        assert body["commit"] == "b" and body["tag"] == "baseline/20261008T180000Z"

    def test_a_network_s_name_becomes_one_file_name(self, data):
        assert BE.path("Branch sites/2").endswith(os.path.join("baseline-earned", "Branch_sites_2"))

    def test_a_write_that_fails_is_said_never_raised(self, data):
        (data / "events").write_text("a file where the directory should be")
        got = BE.hook({"list_name": "Default", "sha": "a", "tags": [TAG]})
        assert got["ok"] is False and "could not be written" in got["error"], got


class TestItRunsAfterEveryCommit:
    def test_it_is_a_default_post_commit_hook(self):
        from modules.nsot import archive, hooks
        archive.register_default_hooks()
        assert "baseline-event" in hooks.registered()

    def test_a_published_baseline_reaches_it(self, data, monkeypatch):
        """Through the real runner: `publish` hands the tags to every hook (repo.save_golden
        calls it with the baseline it earned, on both of its paths)."""
        from modules.nsot import hooks
        monkeypatch.setattr(hooks, "_hooks", [])
        hooks.register("baseline-event", BE.hook, timeout=10)
        monkeypatch.setattr(hooks, "ensure_default_hooks", lambda: hooks.registered())
        hooks.run_post_commit({"list_name": "Default", "repo": str(data), "sha": "abc",
                               "tags": [TAG], "devices": []})
        hooks.wait_for_hooks(10)
        assert (data / "events" / "baseline-earned" / "Default").exists()


class TestTheLabUnitWatchesWhatIsWritten:
    def test_the_path_unit_names_the_file_the_product_writes(self, monkeypatch):
        """The unit is a template (@NMAS_CHECKOUT@/data/...); the product writes under
        DATA_DIR, which on the host is the checkout's data/. The sync boots CLAB_LIST,
        Default unless its unit says otherwise."""
        unit = open(os.path.join(ROOT, "lab", "clab-sync", "clab-sync.path"),
                    encoding="utf-8").read()
        watched = re.findall(r"^PathChanged=(.+)$", unit, re.M)
        monkeypatch.setattr("modules.config.DATA_DIR", "@NMAS_CHECKOUT@/data")
        sync = open(os.path.join(ROOT, "lab", "clab-sync", "clab-startup-sync.sh"),
                    encoding="utf-8").read()
        network = re.search(r'^CLAB_LIST="\$\{CLAB_LIST:-([^}]+)\}"$', sync, re.M).group(1)
        # C663: both events, so a rotation's golden (which earns no baseline) starts the sync.
        assert watched == [BE.path(network), BE.path(network, BE.GOLDEN_EVENTS)], watched
        assert re.search(r"^Unit=clab-sync\.service$", unit, re.M)


def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


class TestAGoldenCommittedWritesItsEvent:
    """C663 (the operator, 2026-10-11): Mercury emits a generic "golden committed" event next to
    "baseline earned", naming the devices, so a tool building what a device boots from (its
    current credentials) follows a rotation, which changes a golden and earns no baseline."""

    @pytest.fixture
    def repo(self, tmp_path):
        r = tmp_path / "repo"
        r.mkdir()
        _git(r, "init", "-q")
        (r / "golden").mkdir()
        (r / "golden" / "r1.cfg").write_text("hostname r1\n")
        (r / "notes.txt").write_text("x\n")
        _git(r, "add", "-A")
        _git(r, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "seed")
        return r

    def test_a_golden_changed_writes_the_event_naming_the_devices(self, data, repo):
        sha = _git(repo, "rev-parse", "HEAD")
        got = BE.golden_hook({"list_name": "Default", "repo": str(repo), "sha": sha})
        assert got["ok"], got
        body = json.loads((data / "events" / "golden-committed" / "Default").read_text())
        assert body["devices"] == ["r1"] and body["commit"] == sha and body["list"] == "Default"
        assert not (data / "events" / "baseline-earned" / "Default").exists()

    def test_a_commit_that_changed_no_golden_writes_nothing(self, data, repo):
        (repo / "notes.txt").write_text("y\n")
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit",
             "-qam", "notes")
        got = BE.golden_hook({"list_name": "Default", "repo": str(repo),
                              "sha": _git(repo, "rev-parse", "HEAD")})
        assert got == {"ok": True, "message": "no golden changed"}
        assert not (data / "events" / "golden-committed").exists()

    def test_it_is_a_default_post_commit_hook(self):
        from modules.nsot import archive, hooks
        archive.register_default_hooks()
        assert "golden-event" in hooks.registered()
