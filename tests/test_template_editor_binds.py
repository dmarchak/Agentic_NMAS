"""The template editor's and Approve's bindings (CONCURRENCY_AUDIT R12 and R14, the operator's
decision of 2026-10-04: "take your recommendations, unless either changes what a screen
shows").

R14: the editor's open hands out the template's blob at HEAD as its BASE, and the save sends
it back. A save whose base is no longer HEAD's is refused (409), naming both blobs, and
nothing is written. Before this, the last writer won silently: a person who opened the
template before another person's commit put their whole text back over it.

R12: what the person was shown carries the closure's fingerprint, and Approve sends it. A
template that moved after it was drawn is refused, naming both fingerprints. The server's own
snapshot check (validation against one fingerprint) covered an edit DURING validation; this
covers one between looking and pressing.

Today's template editor (its file read and save, its approval read and Approve) left at 7.8 on
2026-10-17 (P7-23). The bindings are held here on its home, Source of truth › Templates: Edit…
(`templates_v2.edit_form` and `edit_commit`, the base a hidden field) and Approve… (the
check's card, its fingerprint a hidden field), through the real routes. Expected values come
from git directly.
"""

import os
import subprocess

from modules.nsot import approval
from tests.test_approvals_record import REL, lab  # noqa: F401  (the fixture)
from tests.test_template_approval import _devices
from tests.test_templates_v2 import _get, _hidden, tl  # noqa: F401  (the fixture)


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=True).stdout


def _opened(tl):  # noqa: F811
    import html as H
    import re

    _r, html = _get(tl, f"/v2/templates/edit?list=Lab&path={REL}")
    text = H.unescape(re.search(r'<textarea id="te-text"[^>]*>(.*?)</textarea>', html,
                                re.S).group(1))
    return text, _hidden(html, "base")


def _save(tl, content, base, summary="an edit"):  # noqa: F811
    return tl["client"].post("/v2/templates/edit", data={
        "list": "Lab", "path": REL, "text": content, "base": base, "summary": summary})


class TestTheSaveIsBoundToWhatWasOpened:
    def test_the_base_is_heads_blob_and_the_text_is_that_blob(self, tl):  # noqa: F811
        text, base = _opened(tl)
        assert base == _git(tl["repo"], "rev-parse", f"HEAD:templates/{REL}").strip()
        assert text == _git(tl["repo"], "show", f"HEAD:templates/{REL}")

    def test_a_save_on_the_current_base_commits(self, tl):  # noqa: F811
        text, base = _opened(tl)
        before = _git(tl["repo"], "rev-parse", "HEAD").strip()
        r = _save(tl, text + "{# an edit #}\n", base)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        assert _git(tl["repo"], "rev-parse", "HEAD").strip() != before

    def test_a_save_over_another_persons_commit_is_refused_and_writes_nothing(self, tl):  # noqa: F811
        text_a, base_a = _opened(tl)
        text_b, base_b = _opened(tl)
        assert _save(tl, text_b + "{# B's edit #}\n", base_b, "B's edit").status_code == 200
        head = _git(tl["repo"], "rev-parse", "HEAD").strip()
        on_disk = open(os.path.join(tl["repo"], "templates", REL), encoding="utf-8").read()

        r = _save(tl, text_a + "{# A's edit #}\n", base_a, "A's edit")
        out = r.get_data(as_text=True)
        assert r.status_code == 409 and "not saved" in out
        now = _git(tl["repo"], "rev-parse", f"HEAD:templates/{REL}").strip()
        assert base_a[:7] in out and now[:7] in out
        assert _git(tl["repo"], "rev-parse", "HEAD").strip() == head
        assert open(os.path.join(tl["repo"], "templates", REL), encoding="utf-8").read() == \
            on_disk
        assert "B's edit" in on_disk and "A's edit" not in on_disk

    def test_a_save_that_names_no_base_is_refused(self, tl):  # noqa: F811
        text, _base = _opened(tl)
        head = _git(tl["repo"], "rev-parse", "HEAD").strip()
        r = tl["client"].post("/v2/templates/edit", data={
            "list": "Lab", "path": REL, "text": text + "{# x #}\n", "summary": "no base"})
        assert r.status_code == 409 and "not saved" in r.get_data(as_text=True)
        assert _git(tl["repo"], "rev-parse", "HEAD").strip() == head


class TestTheApproveIsBoundToWhatWasShown:
    def _golden(self, monkeypatch):
        # The approval's one capture read (`approve_op._capture`).
        monkeypatch.setattr("modules.nsot.approve_op._capture",
                            lambda _repo, name: _devices([name])[0]["running_config"])

    def _shown(self, tl):  # noqa: F811
        _r, card = _get(tl, f"/v2/templates/approve?list=Lab&path={REL}")
        return _hidden(card, "fingerprint"), _hidden(card, "seen")

    def _approve(self, tl, fingerprint, seen):  # noqa: F811
        data = {"list": "Lab", "path": REL, "seen": seen}
        if fingerprint is not None:
            data["fingerprint"] = fingerprint
        return tl["client"].post("/v2/templates/approve", data=data)

    def test_the_card_carries_the_fingerprint_and_approve_takes_it(self, tl, monkeypatch):  # noqa: F811
        self._golden(monkeypatch)
        shown, seen = self._shown(tl)
        assert shown == approval.template_fingerprint(tl["repo"], REL)["fingerprint"]
        r = self._approve(tl, shown, seen)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        assert approval.is_approved(tl["repo"], REL) is True

    def test_a_template_that_moved_after_it_was_shown_is_not_approved(self, tl, monkeypatch):  # noqa: F811
        self._golden(monkeypatch)
        shown, seen = self._shown(tl)
        text, base = _opened(tl)
        assert _save(tl, text + "{# moved #}\n", base).status_code == 200
        now = approval.template_fingerprint(tl["repo"], REL)["fingerprint"]
        r = self._approve(tl, shown, seen)
        out = r.get_data(as_text=True)
        assert r.status_code in (400, 409), out[:400]
        assert shown[:12] in out and now[:12] in out
        assert approval.is_approved(tl["repo"], REL) is False

    def test_an_approve_that_names_no_fingerprint_is_refused(self, tl, monkeypatch):  # noqa: F811
        self._golden(monkeypatch)
        _shown, seen = self._shown(tl)
        r = self._approve(tl, None, seen)
        assert r.status_code == 400 and "did not say which version" in r.get_data(as_text=True)
        assert approval.is_approved(tl["repo"], REL) is False
