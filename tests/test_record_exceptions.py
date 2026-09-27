"""C104: the eleven rotation commits recorded `Source: manual` are named by
hash, and a reader draws the exception beside the record, never over it."""

import re

from modules.nsot import record_exceptions as X


def test_the_eleven_rotation_commits_measured_on_the_host():
    rotations = [e for e in X.EXCEPTIONS.values() if e["was"] == "rotation"]
    assert len(rotations) == 11
    assert all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in X.EXCEPTIONS)


def test_the_two_restores_recorded_as_pipeline():
    """C70: both baseline re-applies on the host name the mechanism."""
    restores = [e for e in X.EXCEPTIONS.values() if e["was"] == "restore"]
    assert len(restores) == 2
    assert {(e["field"], e["recorded"], e["was"]) for e in X.EXCEPTIONS.values()} == {
        ("Source", "manual", "rotation"), ("Source", "pipeline", "restore")}
    assert len(X.EXCEPTIONS) == 13


def test_a_prefix_is_not_a_commit():
    sha = next(iter(X.EXCEPTIONS))
    assert X.exception_for(sha)["was"] == "rotation"
    assert X.exception_for(sha[:8]) is None
    assert X.exception_for("") is None


def test_golden_history_keeps_the_record_and_draws_the_exception(tmp_path, monkeypatch,
                                                                   intent_matches):
    from modules.nsot import repo as R

    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {"nsot_git_author_name": "NMAS",
                                                   "nsot_git_author_email": "n@l",
                                                   "nsot_device_tag_retention": 50
                                                   }.get(key, default))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    R.save_golden("lab", [R.GoldenItem("s1", "hostname s1\n", "192.0.2.5")],
                  allow_new=True, source="manual")
    repo = str(list_dir / "config_repo")
    sha = R.golden_history(repo, "s1")[0]["sha"]
    monkeypatch.setitem(X.EXCEPTIONS, sha, dict(next(iter(X.EXCEPTIONS.values()))))

    entry = R.golden_history(repo, "s1")[0]
    assert entry["source"] == "manual", "the record is drawn as recorded"
    assert entry["exception"]["was"] == "rotation"


def test_a_restore_is_recorded_as_a_restore_and_a_deploy_as_pipeline(monkeypatch, tmp_path):
    """C70: the batch commit named the mechanism for both paths, so "no commit
    carries Source: restore" held whether or not a restore had ever run."""
    import routes.deploy as rd
    from modules.nsot.deploy import DEPLOYED

    seen = []
    monkeypatch.setattr("modules.nsot.repo.save_golden",
                        lambda ln, items, **kw: seen.append(kw["source"]) or {"ok": False})
    monkeypatch.setattr(rd, "request_actor", lambda: "ops@example.com")
    monkeypatch.setattr(rd, "_baseline_earned", lambda *a, **k: {"baseline": False})
    monkeypatch.setattr(rd, "_write_restored_intent",
                        lambda *a, **k: {"restored": [], "un_onboarded": []})
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))

    def report():
        return {"results": [{"device": "r2", "outcome": DEPLOYED, "golden_pending": [
            {"hostname": "r2", "config_text": "hostname r2\n", "mgmt_ip": "203.0.113.12",
             "netbox_id": None, "device_uid": "uid:x"}]}]}
    rd._commit_batch_golden("Lab", report(), source_ref="baseline/20260925T201032Z")
    rd._commit_batch_golden("Lab", report())
    assert seen == ["restore", "pipeline"]
