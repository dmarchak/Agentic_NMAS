"""The intent writers that check a hash hold the repository's lock from the recompute to the
commit (CONCURRENCY_AUDIT R15, 2026-10-04).

R15: bulk intent, profile propose and the IP SLA writers recomputed their plan and compared it
with the confirmed hash, then wrote and committed with no lock spanning the three, so an editor
commit landing in between passed the dirty check and was overwritten; `profile.commit_profile`
restored the previous bytes on a failed commit over any other writer's. Each now runs under
`repo.RepoLock` (cross-process, re-entrant per thread), so the editor (which takes the same
lock, R2) waits.

Shown by spying on each writer's own recompute (and the commit, for `commit_profile`): the lock
is held by this thread when they run.
"""

import os
import types

import pytest

from modules.nsot import repo as R


@pytest.fixture
def repo(tmp_path, monkeypatch):
    path = tmp_path / "lab" / "config_repo"
    path.mkdir(parents=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    return str(path)


def _held(repo):
    return R.RepoLock(repo).held()


def test_bulk_intent_recomputes_under_the_lock(repo, monkeypatch):
    from modules.nsot import bulk_intent
    seen = []
    monkeypatch.setattr(bulk_intent, "plan", lambda *a, **k: seen.append(_held(repo)) or
                        {"ok": False, "error": "spied"})
    got = bulk_intent.apply("Lab", repo, ["r2"], [{"path": ["x"]}], "h", render=None,
                            summary="s", actor="a")
    assert got["error"] == "spied" and seen == [True]
    assert not _held(repo), "released after"


def test_profile_propose_recomputes_under_the_lock(repo, monkeypatch):
    from modules.nsot import profile_propose
    seen = []
    monkeypatch.setattr(profile_propose, "propose", lambda *a, **k: seen.append(_held(repo)) or
                        {"changed": False})
    monkeypatch.setattr(profile_propose, "public", lambda p: p)
    assert profile_propose.apply("Lab", "h", "a")["outcome"] == "nothing"
    assert seen == [True]


def test_ip_sla_policy_recomputes_under_the_lock(repo, monkeypatch):
    from modules.nsot import ip_sla_policy
    ref = types.SimpleNamespace(name="Lab", repo_dir=repo)
    seen = []
    monkeypatch.setattr(ip_sla_policy, "policy_view", lambda r: seen.append(_held(repo)) or
                        {"error": "spied"})
    with pytest.raises(ip_sla_policy.Refused, match="spied"):
        ip_sla_policy.set_policy(ref, "gateway", 60, "a", "h")
    monkeypatch.setattr(ip_sla_policy, "plan", lambda r, chosen: seen.append(_held(repo)) or
                        {"fingerprint": "other"})
    with pytest.raises(ip_sla_policy.Refused, match="changed since they were shown"):
        ip_sla_policy.apply(ref, [], [], "h", "a")
    assert seen == [True, True]


def test_commit_profile_reads_writes_commits_and_restores_under_the_lock(repo, monkeypatch):
    from modules.nsot import profile
    seen = []
    monkeypatch.setattr(profile, "problems", lambda doc: [])
    monkeypatch.setattr(profile, "dump", lambda doc: "sections: {}\n")
    monkeypatch.setattr(R, "_commit_paths", lambda *a, **k: seen.append(_held(repo)) or
                        {"ok": False, "error": "spied"})
    os.makedirs(os.path.join(repo, os.path.dirname(profile.PROFILE_REL)), exist_ok=True)
    with open(os.path.join(repo, profile.PROFILE_REL), "w", encoding="utf-8") as fh:
        fh.write("before\n")
    out = profile.commit_profile("Lab", {"sections": {}}, "a", "s")
    assert out["error"] == "spied" and seen == [True]
    with open(os.path.join(repo, profile.PROFILE_REL), encoding="utf-8") as fh:
        assert fh.read() == "before\n", "the failed commit restored the earlier bytes"
