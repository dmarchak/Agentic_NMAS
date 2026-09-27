"""Refresh Hostnames records a PENDING rename; it never re-saves a golden.

It used to re-save the device's golden under its new name through
`_save_golden_config_file()` (recorded `Source: ai`, `Actor: ai-agent`),
bypassing the designed rename, so every rename through it broke the device's
history (`git log --follow`). Removed on the operator's decision (C102,
2026-09-27): a rename has one home, the manifest's pending rename, committed
alone by the next save or by "Sync device names to repo". Driven here through
the real route, against a real repository.
"""

import subprocess

import pytest

from modules.nsot import manifest as M
from modules.nsot import repo as R

IP = "192.0.2.41"


@pytest.fixture
def lab(tmp_path, monkeypatch, intent_matches):
    import app as A

    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {"nsot_git_author_name": "NMAS",
                                                   "nsot_git_author_email": "n@l",
                                                   "nsot_device_tag_retention": 50
                                                   }.get(key, default))
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    assert R.save_golden("lab", [R.GoldenItem("r1", "hostname r1\n!\nend\n", IP)],
                         allow_new=True)["ok"]
    repo = str(list_dir / "config_repo")
    devices = [{"hostname": "r1", "ip": IP, "device_type": "cisco_ios",
                "username": "u", "password": "p"}]
    monkeypatch.setattr(A, "get_current_device_list", lambda: ("lab", "lab.csv"))
    monkeypatch.setattr(A, "load_saved_devices", lambda path=None: devices)
    monkeypatch.setattr(A, "write_devices_csv", lambda rows, path: None)
    monkeypatch.setattr(A, "with_temp_connection", lambda dev, fn: "r1-renamed")
    monkeypatch.setitem(A.device_status_cache, IP, True)
    monkeypatch.setattr("modules.ai_assistant._nsot_repo_dir", lambda: repo)
    monkeypatch.setattr("modules.ai_assistant._load_variables", lambda: {})
    monkeypatch.setattr("modules.netbox_client.get_netbox_config", lambda: {})
    return {"client": A.app.test_client(), "repo": repo}


def _git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout


def _refresh(lab):
    r = lab["client"].post("/refresh_hostnames")
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def test_it_records_a_pending_rename_and_commits_nothing(lab):
    head = _git(lab["repo"], "rev-parse", "HEAD")
    out = _refresh(lab)
    assert _git(lab["repo"], "rev-parse", "HEAD") == head, "nothing is committed"
    assert _git(lab["repo"], "ls-tree", "--name-only", "HEAD", "golden/") == "golden/r1.cfg\n"
    assert [(p["from"], p["to"]) for p in M.pending_renames(lab["repo"])] == [("r1", "r1-renamed")]
    assert out["pending_renames"] == ["r1 -> r1-renamed"]


def test_the_message_leads_with_what_is_left_to_do(lab):
    out = _refresh(lab)
    assert out["message"].startswith("1 golden rename(s) PENDING")
    assert "Sync device names to repo" in out["message"]


def test_syncing_moves_it_alone_and_history_follows(lab):
    _refresh(lab)
    assert R.apply_pending_renames(lab["repo"])["renamed"]
    files = _git(lab["repo"], "show", "--name-status", "--format=", "HEAD")
    # A 100% rename (no content change), plus the manifest that every commit
    # moving a device carries, and nothing else.
    assert sorted(files.strip().splitlines()) == [
        "M\t.nsot/manifest.json", "R100\tgolden/r1.cfg\tgolden/r1-renamed.cfg"], files
    follow = _git(lab["repo"], "log", "--follow", "--format=%s", "--", "golden/r1-renamed.cfg")
    assert len(follow.strip().splitlines()) >= 2, "history follows the rename"


def test_nothing_is_recorded_as_the_agent(lab):
    _refresh(lab)
    R.apply_pending_renames(lab["repo"])
    assert "ai-agent" not in _git(lab["repo"], "log", "--format=%B")
