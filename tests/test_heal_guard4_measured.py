"""C2815 (the operator, H11 W3, 2026-11-08): self-healing's guard 4 reads the device's intent
state as the Devices list and the device page do (`device_list.intent_state`, C532's one owner):
its NEWEST measurement, a Save All that found it unchanged included, while nothing it was judged
against has moved since. On the host, r4's golden last changed at a commit whose `Intent-Match:`
said "departs (+2 -2)" (before its intent was corrected), and the Save All after it measured r4
at intent and earned a baseline; guard 4 read only the first and held every heal of r4.

Through a real git repository: the commit that changed the golden, a later Save All's empty
commit naming the device in `Devices-Measured:`, and an intent commit after it."""

import os
import subprocess

import pytest

GOLDEN = "hostname r4\n!\narchive\n path bootflash:mercury-arch\n!\nend\n"


def _git(repo, *args, env=None):
    got = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
                            **(env or {})))
    assert got.returncode == 0, (args, got.stderr)


def _commit(repo, message, at, *paths, empty=False):
    env = {"GIT_AUTHOR_DATE": f"{at} +0000", "GIT_COMMITTER_DATE": f"{at} +0000"}
    for p in paths:
        _git(repo, "add", p)
    _git(repo, "commit", "-q", *(["--allow-empty"] if empty else []), "-m", message, env=env)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """r4's intent, then its golden committed saying it departs, then a Save All measuring it
    at intent; the heal's sources pointed at this repository and this golden."""
    import types

    r = tmp_path / "config_repo"
    (r / "golden").mkdir(parents=True)
    (r / "host_vars").mkdir()
    _git(r, "init", "-q")
    (r / "host_vars" / "r4.yml").write_text("hostname: r4\n", encoding="utf-8")
    _commit(r, "intent of r4", 1794000000, "host_vars/r4.yml")
    (r / "golden" / "r4.cfg").write_text(GOLDEN, encoding="utf-8")
    _commit(r, "golden r4\n\nSource: capture\nDevice-Name: r4\nIntent-Match: no: r4 (+2 -2)\n",
            1794074595, "golden/r4.cfg")
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda network: types.SimpleNamespace(name=network, repo_dir=str(r)))
    monkeypatch.setattr("modules.goldens._golden_record",
                        lambda ip, network: {"text": GOLDEN})
    compared = []

    def now(repo_dir, network, host, text, platform=""):
        compared.append(host)
        return {"state": "match", "adds": 0, "removes": 0, "reordered": 0, "lines": [],
                "why": ""}
    monkeypatch.setattr("modules.nsot.intent_match.intent_match", now)
    return types.SimpleNamespace(path=r, compared=compared)


def _golden():
    from modules.heal import decide

    return decide.Sources("Default").golden("r4", {"ip": "192.0.2.4"})


def test_a_later_save_all_measuring_it_at_intent_is_the_approved_state(repo):
    _commit(repo.path, "Save All\n\nSource: save_all\nDevices-Measured: r4\nIntent-Match: yes "
            "(1 of 1)\nBaseline: earned 2026-11-08T04:15:10Z\n", 1794111310, empty=True)
    got = _golden()
    assert (got["state"], got["words"]) == ("at_intent", "at intent"), got
    assert repo.compared == [], "a measurement that stands is read, never recomputed"
    from modules.heal import guards
    assert guards.g4_golden(got) is None


def test_the_golden_commits_own_trailer_still_counts_when_it_is_the_newest(repo):
    got = _golden()
    assert (got["state"], got["words"]) == ("departs", "departs (+2 -2)"), got
    from modules.heal import guards
    assert guards.g4_golden(got)["guard"] == 4


def test_intent_changed_since_the_measurement_is_compared_now(repo):
    _commit(repo.path, "Save All\n\nSource: save_all\nDevices-Measured: r4\nIntent-Match: no: "
            "r4 (+1)\n", 1794111310, empty=True)
    (repo.path / "host_vars" / "r4.yml").write_text("hostname: r4\nx: 1\n", encoding="utf-8")
    _commit(repo.path, "intent of r4 changed", 1794120000, "host_vars/r4.yml")
    got = _golden()
    assert repo.compared == ["r4"], "a stale measurement is not the state"
    assert got["state"] == "at_intent"
    assert got["words"].startswith("its newest measurement does not stand (")
    assert got["words"].endswith("; compared now: matches"), got["words"]
