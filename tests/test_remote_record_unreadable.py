"""C172 (2026-10-07): a list's remote.json that EXISTS and cannot be read is never "no remote".

`remote.load_remote()` caught any error and returned ``None``, the same answer as an absent
file, and a list with no remote is quiet by design, so a damaged record read as a list nobody
gave a remote: the operations refused with "no remote configured", the Remote panel said "No
remote for this list", the History card dropped the record's last failure, the git probe said
"no remote", and another list's damaged record could not stop two lists sharing a repository.
R18 (2026-10-04) had already made the push hook, adoption and every writer refuse it. Now the
reader itself raises `RemoteUnreadable`, and `config_or_refusal` is the one way an operation
reads the record, so each says the record cannot be read, names the file, and that nothing is
pushed until it is repaired; the file is never changed by a read.
"""

import json
import os
import re

import pytest

from modules.nsot import remote as R
from tests.test_remote_store import LIST, store  # noqa: F401 (the fixture)

DAMAGED = "{not json"


def _damage(path):
    path.write_text(DAMAGED, encoding="utf-8")


class TestTheReader:
    def test_absent_is_no_remote(self, store):  # noqa: F811
        store.unlink()
        assert R.load_remote(LIST) is None
        assert R.config_or_refusal(LIST) == (None, "")

    def test_unreadable_raises_naming_the_file_and_leaves_it(self, store):  # noqa: F811
        _damage(store)
        with pytest.raises(R.RemoteUnreadable) as caught:
            R.load_remote(LIST)
        said = str(caught.value)
        assert said.startswith("remote.json could not be read (JSONDecodeError)")
        assert str(store) in said and "nothing is pushed until" in said
        assert store.read_text(encoding="utf-8") == DAMAGED

    def test_json_that_is_not_a_record_is_unreadable(self, store):  # noqa: F811
        store.write_text("[1, 2]", encoding="utf-8")
        config, why = R.config_or_refusal(LIST)
        assert config is None and why.startswith("remote.json holds a list, not a record")

    def test_a_readable_record_reads(self, store):  # noqa: F811
        assert R.config_or_refusal(LIST) == (json.loads(store.read_text()), "")


class TestEveryOperationSaysUnreadable:
    """Each refuses by the reader's words, never "no remote configured"."""

    @pytest.mark.parametrize("call, key", [
        (lambda: R.verify(LIST, repo_dir="unused"), "error"),
        (lambda: R.first_push_preview(LIST, repo_dir="unused"), "error"),
        (lambda: R.acknowledge(LIST, actor="t", actor_kind="person", repo_dir="unused"),
         "error"),
        (lambda: R.push(LIST, actor="t", repo_dir="unused"), "error"),
        (lambda: R.acknowledgement_covers(LIST, repo_dir="unused"), "reason"),
        (lambda: R.auto_push_decision(LIST, repo_dir="unused"), "reason"),
    ])
    def test_it_refuses_naming_the_record(self, store, call, key):  # noqa: F811
        _damage(store)
        out = call()
        said = out[key]
        assert said.startswith("remote.json could not be read"), out
        assert "no remote" not in said
        assert out.get("ok", out.get("push")) is False
        assert store.read_text(encoding="utf-8") == DAMAGED

    def test_no_salt_is_minted_into_a_damaged_record(self, store):  # noqa: F811
        _damage(store)
        assert R.ack_salt(LIST) == ""
        assert store.read_text(encoding="utf-8") == DAMAGED


class TestAnotherListsDamagedRecord:
    def test_it_does_not_clear_this_list_to_share_its_repository(self, tmp_path, monkeypatch):
        """Whether the other list already pushes to this repository is unknown, so this
        list is not cleared (refusing by resemblance is safe)."""
        from modules import config
        root = tmp_path / "lists"
        for slug in ("lab", "branch"):
            (root / slug).mkdir(parents=True)
        (root / "branch" / "remote.json").write_text(DAMAGED, encoding="utf-8")
        monkeypatch.setattr(config, "LISTS_DIR", str(root))
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(root / config.list_slug(name)))
        out = R.check_right_repository(
            {"owner": "example-owner", "repo": "network-golden"}, "lab", str(tmp_path))
        assert (out["ok"], out["name"], out["detail"]) == (False, "not_another_lists_repo",
                                                           "branch")
        assert "remote.json could not be read" in out["fix"]
        assert "example-owner/network-golden cannot be told" in out["fix"]


class TestTheScreensSayIt:
    def test_the_status_route_is_not_configured_false(self, store, monkeypatch):  # noqa: F811
        import app as A
        monkeypatch.setattr("routes.remote._list_name", lambda: LIST)
        monkeypatch.setattr("modules.config_git.publication", lambda name: {"state": "not_read"})
        _damage(store)
        body = A.app.test_client().get("/remote/status").get_json()
        assert body["ok"] is False and body["configured"] is None
        assert body["error"].startswith("remote.json could not be read")

    def test_the_v1_panel_draws_the_error_not_no_remote(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        js = open(os.path.join(root, "static", "js", "gen", "partials__golden_repo.2.js"),
                  encoding="utf-8").read()
        branch = js.index("if (s.configured === null && s.error)")
        assert branch < js.index("if (!s.configured)")
        assert "The remote record cannot be read." in js[branch:js.index("if (!s.configured)")]

    def test_the_history_card_draws_it(self, monkeypatch):
        from modules.nsot import remote as NR

        def damaged(name):
            raise NR.RemoteUnreadable("remote.json could not be read (JSONDecodeError), so "
                                      "this list's remote is unknown")
        monkeypatch.setattr(NR, "load_remote", damaged)
        from routes import v2
        ref = type("Ref", (), {"name": "Lab", "repo_dir": "/nonexistent"})()
        monkeypatch.setattr("modules.readers.remote_publication.status_for",
                            lambda name: {"state": "not_read"})
        out = v2._history_remote(ref)
        assert out["record_unreadable"].startswith("remote.json could not be read")
        assert "push_failure" in out and out["push_failure"] is None

    def test_the_history_template_draws_the_field(self):
        from flask import render_template_string
        import app as A
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(root, "templates", "v2", "_history_remote.html"),
                   encoding="utf-8").read()
        with A.app.test_request_context("/"):
            html = render_template_string(src, remote={
                "d": {"level": "danger", "state": "ahead", "clause": "c", "detail": ""},
                "value_at": "", "dirty": 0, "list": "Lab", "push_failure": None,
                "last_verify": None, "record_unreadable": "remote.json could not be read (X)"})
        said = re.search(r'id="remote-record-unreadable">(.*?)</p>', html, re.S).group(1)
        assert said == "The list's remote record cannot be read: remote.json could not be read (X)."

    def test_the_git_probe_is_down_naming_it(self, tmp_path, monkeypatch):
        from tests.test_nsot_git_probe import NsotGitIntegration
        from modules import config, device
        import subprocess
        root = tmp_path / "lists"
        monkeypatch.setattr(config, "LISTS_DIR", str(root))
        good = root / "lab" / "config_repo"
        good.mkdir(parents=True)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "a"]):
            subprocess.run(["git", "-C", str(good), *args], check=True, capture_output=True,
                           env=env)
        monkeypatch.setattr(device, "get_device_lists",
                            lambda: [{"name": "Lab", "filename": "lab"}])

        def damaged(name):
            raise R.RemoteUnreadable("remote.json could not be read (JSONDecodeError)")
        monkeypatch.setattr(R, "load_remote", damaged)
        st = NsotGitIntegration().status()
        assert st["state"] == "down", st
        assert "Lab: HEAD" in st["message"] and "remote.json could not be read" in st["message"]
        assert "no remote" not in st["message"]
