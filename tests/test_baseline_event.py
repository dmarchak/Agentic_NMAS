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
        unit = open(os.path.join(ROOT, "deploy", "systemd", "clab-sync.path"),
                    encoding="utf-8").read()
        watched = re.search(r"^PathChanged=(.+)$", unit, re.M).group(1)
        monkeypatch.setattr("modules.config.DATA_DIR", "@NMAS_CHECKOUT@/data")
        sync = open(os.path.join(ROOT, "scripts", "clab-startup-sync.sh"), encoding="utf-8").read()
        network = re.search(r'^CLAB_LIST="\$\{CLAB_LIST:-([^}]+)\}"$', sync, re.M).group(1)
        assert watched == BE.path(network), (watched, BE.path(network))
        assert re.search(r"^Unit=clab-sync\.service$", unit, re.M)
