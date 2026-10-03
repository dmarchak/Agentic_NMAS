"""The template approvals record (CONCURRENCY_AUDIT R13).

`templates/.approvals.json` was an unlocked load-modify-save through one shared `.tmp`, an
unreadable file read as `{}` (so the next save erased every approval and tombstone in it), a
template edit's revocations were never committed (the commit staged the template alone), the
deploy gate read the working file, and the approve and revoke routes ignored their commit.
If one person revoked template X while another approved Y, Y's stale copy put X's approval
back, and the gate reopened for a template a person withdrew.

Measured here, against real repositories:

- two PROCESSES revoking at once lose no tombstone;
- an unreadable record refuses an approve and a revoke with the file kept byte-identical and
  a `.corrupt-` copy beside it, and the gate refuses rather than reading it as empty;
- the gate fails closed BOTH ways: an approval not committed is not one, and a revocation not
  yet committed already refuses;
- a template edit through the route commits its revocations WITH the template;
- the approve route reports a failed commit as not approved, and the revoke route says the
  gate already refuses but history does not hold it.
"""

import json
import os
import subprocess
import sys

import pytest

from modules.nsot import approval, manifest
from tests.test_template_approval import _commit_approvals, _devices

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = "cisco_ios/base.j2"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A list repository with the seeded library committed and three bound devices."""
    from modules.nsot import repo as R
    from routes import templates as troutes

    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost",
                            "nsot_device_tag_retention": 50}.get(key, default))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    repo = str(list_dir / "config_repo")
    R.init_repo(repo)
    troutes._seed_and_commit("Lab", repo)
    for name in ("s1", "s2", "s3"):
        manifest.upsert_device(repo, f"uid:{name}", name, f"203.0.113.2{name[1]}",
                               platform="cisco-ios")
    monkeypatch.setattr(troutes, "_active_list", lambda *a: "Lab")
    monkeypatch.setattr(troutes, "_repo_for", lambda *_a: repo)
    return repo


def _head_record(repo):
    out = subprocess.run(["git", "-C", repo, "show", "HEAD:templates/.approvals.json"],
                         capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 else {}


class TestTwoProcessesLoseNothing:
    def test_concurrent_revocations_keep_every_tombstone(self, tmp_path):
        repo = str(tmp_path / "config_repo")
        os.makedirs(os.path.join(repo, "templates"))
        script = tmp_path / "revoker.py"
        script.write_text(
            "import sys\n"
            f"sys.path.insert(0, {ROOT!r})\n"
            "from modules.nsot import approval\n"
            "repo, tag = sys.argv[1], sys.argv[2]\n"
            "for i in range(25):\n"
            "    r = approval.revoke(repo, f'{tag}/{i}.j2', reason='withdrawn for the test run')\n"
            "    assert r['ok'], r\n", encoding="utf-8")
        procs = [subprocess.Popen([sys.executable, str(script), repo, tag])
                 for tag in ("a", "b")]
        assert [p.wait(120) for p in procs] == [0, 0]
        data = json.load(open(approval.approvals_path(repo), encoding="utf-8"))
        assert len(data) == 50 and all(v.get("revoked") for v in data.values())


class TestAnUnreadableRecordIsNeverEmpty:
    def test_writes_refuse_and_keep_the_file_and_the_gate_refuses(self, lab):
        path = approval.approvals_path(lab)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"cisco_ios/base.j2": {"fingerprint": ')      # torn
        before = open(path, "rb").read()
        got = approval.approve(lab, REL, _devices(["s1"]), actor="p@example.invalid")
        assert got["ok"] is False and "could not be read" in got["error"]
        assert approval.revoke(lab, REL, reason="withdrawn for the test run")["ok"] is False
        assert open(path, "rb").read() == before
        # Preserved BESIDE the repository, never inside it (C345).
        beside = os.path.dirname(os.path.abspath(lab))
        assert any(n.startswith("config_repo.approvals.json.corrupt-")
                   for n in os.listdir(beside))
        assert not [n for n in os.listdir(os.path.dirname(path)) if "corrupt" in n]
        assert approval.is_approved(lab, REL) is False
        assert "could not be read" in approval.approval_status(lab, REL)["reason"]


class TestNothingOfTheRecordsIsStagedBySeeding:
    """C345: an unreadable record's preserved copy, and a write's temp file, sat inside
    `templates/`, where seeding stages untracked files into a "seed library" commit."""

    def test_the_damaged_copy_and_the_temp_never_enter_the_repository(self, lab, monkeypatch):
        import tempfile

        dirs = []
        real = tempfile.mkstemp

        def spy(*a, **k):
            dirs.append(os.path.abspath(k.get("dir") or ""))
            return real(*a, **k)
        monkeypatch.setattr(tempfile, "mkstemp", spy)
        approval.revoke(lab, REL, reason="withdrawn for the test run")
        assert dirs and all(not d.startswith(os.path.abspath(lab) + os.sep) for d in dirs)

    def test_seeding_never_stages_a_file_it_did_not_provide(self, lab):
        from routes import templates as troutes

        path = approval.approvals_path(lab)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{torn")
        approval.revoke(lab, REL, reason="withdrawn for the test run")    # refused, preserved
        # A stray untracked file under templates/, of the shape the old code left there.
        stray = os.path.join(lab, "templates", ".approvals.json.corrupt-20261002T000000Z")
        with open(stray, "w", encoding="utf-8") as fh:
            fh.write("{torn")
        os.remove(os.path.join(lab, "templates", "cisco_ios", "base.j2"))
        subprocess.run(["git", "-C", lab, "commit", "-q", "-am", "drop base"], check=True,
                       env=dict(os.environ, GIT_AUTHOR_NAME="T", GIT_COMMITTER_NAME="T",
                                GIT_AUTHOR_EMAIL="t@example.invalid",
                                GIT_COMMITTER_EMAIL="t@example.invalid"))
        result = troutes._seed_and_commit("Lab", lab)     # seeds base.j2 back, and commits
        names = subprocess.run(["git", "-C", lab, "show", "--name-only", "--format=", "HEAD"],
                               capture_output=True, text=True).stdout.split()
        assert names == [f"templates/{REL}"], names
        assert "templates/.approvals.json.corrupt-20261002T000000Z" in result["not_seeding"]
        assert not [n for n in names if "corrupt" in n or ".tmp-" in n]


class TestTheGateFailsClosedBothWays:
    def test_an_approval_counts_once_committed(self, lab):
        assert approval.approve(lab, REL, _devices(["s1"]), actor="p@example.invalid")["ok"]
        assert approval.is_approved(lab, REL) is False
        assert "not committed" in approval.approval_status(lab, REL)["reason"]
        _commit_approvals(lab)
        assert approval.is_approved(lab, REL) is True

    def test_a_revocation_refuses_before_it_is_committed(self, lab):
        approval.approve(lab, REL, _devices(["s1"]), actor="p@example.invalid")
        _commit_approvals(lab)
        assert approval.revoke(lab, REL, reason="a defect found in its evidence")["ok"]
        assert not _head_record(lab)[REL].get("revoked")      # HEAD still approves
        assert approval.is_approved(lab, REL) is False
        assert approval.approval_status(lab, REL).get("revoked") is True


class TestTheRoutesCommitAndSayWhenTheyCannot:
    def _client(self):
        import app as nmas
        return nmas.app.test_client()

    def test_a_template_edit_commits_its_revocation_with_the_template(self, lab):
        approval.approve(lab, REL, _devices(["s1"]), actor="p@example.invalid")
        _commit_approvals(lab)
        text = open(os.path.join(lab, "templates", REL), encoding="utf-8").read()
        body = self._client().post(f"/templates/file/{REL}",
                                   json={"content": text + "{# an edit #}\n",
                                         "message": "template: an edit"}).get_json()
        assert body["ok"] is True and body["revoked"] == [REL]
        names = subprocess.run(["git", "-C", lab, "show", "--name-only", "--format=", "HEAD"],
                               capture_output=True, text=True).stdout.split()
        assert f"templates/{REL}" in names and "templates/.approvals.json" in names
        assert _head_record(lab)[REL]["revoked"] is True
        status = subprocess.run(["git", "-C", lab, "status", "--porcelain", "templates"],
                                capture_output=True, text=True).stdout
        assert status.strip() == ""

    def test_the_approve_route_reports_a_failed_commit_as_not_approved(self, lab,
                                                                      monkeypatch):
        from routes import templates as troutes

        monkeypatch.setattr(troutes, "_captured_golden",
                            lambda name, *_a, **_k: (_devices([name])[0]["running_config"],
                                                     None))
        monkeypatch.setattr("modules.nsot.repo.save_templates",
                            lambda *a, **k: {"ok": False, "error": "disk full"})
        r = self._client().post(f"/templates/approve/{REL}", json={})
        body = r.get_json()
        assert r.status_code == 500 and body["ok"] is False
        assert "Not approved yet" in body["error"] and "disk full" in body["error"]
        assert approval.is_approved(lab, REL) is False

    def test_the_revoke_route_says_the_gate_refuses_but_history_lacks_it(self, lab,
                                                                         monkeypatch):
        approval.approve(lab, REL, _devices(["s1"]), actor="p@example.invalid")
        _commit_approvals(lab)
        monkeypatch.setattr("modules.nsot.repo.save_templates",
                            lambda *a, **k: {"ok": False, "error": "disk full"})
        r = self._client().post(f"/templates/revoke/{REL}",
                                json={"reason": "a defect found in its evidence"})
        body = r.get_json()
        assert r.status_code == 500 and body["ok"] is False
        assert "already refused" in body["error"] and "not in the repository" in body["error"]
        assert approval.is_approved(lab, REL) is False
