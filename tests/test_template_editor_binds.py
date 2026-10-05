"""The template editor's client halves (CONCURRENCY_AUDIT R12 and R14, the operator's
decision of 2026-10-04: "take your recommendations, unless either changes what a screen
shows").

R14: the editor's open hands out the template's blob at HEAD as its BASE, and the save sends
it back. A save whose base is no longer HEAD's is refused (409), naming both blobs and who
moved it, and nothing is written. Before this, the last writer won silently: a person who
opened the template before another person's commit put their whole text back over it.

R12: the approval state the library row loads carries the closure's fingerprint, and Approve
sends it. A template that moved after the row was drawn is refused, naming both
fingerprints. The server's own snapshot check (validation against one fingerprint) covered
an edit DURING validation; this covers one between looking and pressing.

Both refusals are drawn where the editor already draws a refusal: the save's status line and
the approve's "Cannot approve" alert. The shipped client is checked as R2's was, by lifting
the functions and anchoring on the assignments."""

import os
import subprocess

from modules.nsot import approval
from tests.payload_render import lift, shipped
from tests.test_approvals_record import REL, lab  # noqa: F401  (the fixture)
from tests.test_template_approval import _devices

FILE = f"/templates/file/{REL}"


def _client():
    import app as nmas
    return nmas.app.test_client()


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=True).stdout


def _opened(client):
    body = client.get(FILE).get_json()
    return body["content"], body["base"]


def _save(client, content, base, **extra):
    return client.post(FILE, json={"content": content, "base": base, **extra})


class TestTheSaveIsBoundToWhatWasOpened:
    def test_the_base_is_heads_blob_and_the_text_is_that_blob(self, lab):
        text, base = _opened(_client())
        assert base == _git(lab, "rev-parse", f"HEAD:templates/{REL}").strip()
        assert text == _git(lab, "show", f"HEAD:templates/{REL}")

    def test_a_save_on_the_current_base_commits(self, lab):
        client = _client()
        text, base = _opened(client)
        before = _git(lab, "rev-parse", "HEAD").strip()
        r = _save(client, text + "{# an edit #}\n", base)
        assert r.status_code == 200 and r.get_json()["ok"] is True
        assert _git(lab, "rev-parse", "HEAD").strip() != before

    def test_a_save_over_another_persons_commit_is_refused_and_writes_nothing(self, lab):
        a, b = _client(), _client()
        text_a, base_a = _opened(a)
        text_b, base_b = _opened(b)
        assert _save(b, text_b + "{# B's edit #}\n", base_b).get_json()["ok"] is True
        head = _git(lab, "rev-parse", "HEAD").strip()
        on_disk = open(os.path.join(lab, "templates", REL), encoding="utf-8").read()

        r = _save(a, text_a + "{# A's edit #}\n", base_a)
        body = r.get_json()
        assert r.status_code == 409 and body["ok"] is False and body["stage"] == "moved"
        now = _git(lab, "rev-parse", f"HEAD:templates/{REL}").strip()
        assert base_a[:8] in body["error"] and now[:8] in body["error"]
        assert "Nothing was written" in body["error"]
        assert _git(lab, "rev-parse", "HEAD").strip() == head
        assert open(os.path.join(lab, "templates", REL), encoding="utf-8").read() == on_disk
        assert "B's edit" in on_disk and "A's edit" not in on_disk

    def test_a_save_that_names_no_base_is_refused(self, lab):
        client = _client()
        text, _base = _opened(client)
        head = _git(lab, "rev-parse", "HEAD").strip()
        r = client.post(FILE, json={"content": text + "{# x #}\n"})
        assert r.status_code == 400 and r.get_json()["stage"] == "base"
        assert _git(lab, "rev-parse", "HEAD").strip() == head


class TestTheApproveIsBoundToWhatWasShown:
    def _golden(self, monkeypatch):
        # The approval's one capture read (`approve_op._capture`, which today's route and v2
        # share).
        monkeypatch.setattr("modules.nsot.approve_op._capture",
                            lambda _repo, name: _devices([name])[0]["running_config"])

    def test_the_rows_state_carries_the_fingerprint_and_approve_takes_it(self, lab,
                                                                         monkeypatch):
        self._golden(monkeypatch)
        client = _client()
        shown = client.get(f"/templates/approval/{REL}").get_json()["fingerprint"]
        r = client.post(f"/templates/approve/{REL}", json={"fingerprint": shown})
        assert r.status_code == 200 and r.get_json()["ok"] is True
        assert approval.is_approved(lab, REL) is True

    def test_a_template_that_moved_after_the_row_was_drawn_is_not_approved(self, lab,
                                                                          monkeypatch):
        self._golden(monkeypatch)
        client = _client()
        shown = client.get(f"/templates/approval/{REL}").get_json()["fingerprint"]
        text, base = _opened(client)
        assert _save(client, text + "{# moved #}\n", base).get_json()["ok"] is True
        now = approval.template_fingerprint(lab, REL)["fingerprint"]
        r = client.post(f"/templates/approve/{REL}", json={"fingerprint": shown})
        body = r.get_json()
        assert r.status_code == 400 and body["ok"] is False
        assert shown[:12] in body["error"] and now[:12] in body["error"]
        assert approval.is_approved(lab, REL) is False

    def test_an_approve_that_names_no_fingerprint_is_refused(self, lab, monkeypatch):
        self._golden(monkeypatch)
        r = _client().post(f"/templates/approve/{REL}", json={})
        assert r.status_code == 400 and "did not say which version" in r.get_json()["error"]
        assert approval.is_approved(lab, REL) is False


class TestTheShippedClient:
    SRC = shipped("partials__template_editor.1.js")

    def test_the_editor_keeps_the_base_it_opened_and_sends_it(self):
        assert "_tplBase = d.base;" in lift(self.SRC, "openTemplate")
        assert "JSON.stringify({content, base: _tplBase})" in lift(self.SRC, "saveTemplate")

    def test_the_row_keeps_the_fingerprint_it_drew_and_approve_sends_it(self):
        assert "_tplShown[path] = d.fingerprint;" in lift(self.SRC, "_loadApproval")
        assert "JSON.stringify({fingerprint: _tplShown[path] || ''})" in \
            lift(self.SRC, "approveTemplate")

    def test_both_refusals_land_where_a_refusal_is_already_drawn(self):
        save = lift(self.SRC, "saveTemplate")
        assert "status.textContent = d.error;" in save
        assert "alert(`Cannot approve ${path}\\n\\n${d.error}" in lift(self.SRC, "approveTemplate")
