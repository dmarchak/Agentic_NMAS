"""H, the one intent editor, on the v2 device page's Intent tab (board H, signed off
2026-10-04; C444, C481), through the real app and routes on test_intent_editor's world: a list
`lab`, device s4 with committed intent (one unmodelled line) and a committed golden.

- Edit opens the committed document and the blob it was read from; the card is under the
  strict policy.
- Checked as typed: an error with its line and column; else what the edit changes, what a
  deploy would send, the checks, and the unmodelled lines with whether each is acknowledged.
- Acknowledging writes the document's `unmodeled_ack` block (nothing committed until the
  commit), and the check then reads it acknowledged.
- The commit: as the verified person, with the reason as its subject, bound to the version
  opened; when intent moved, nothing is written and both changes are shown, the edit placed
  on theirs only when they touch different lines.
- Today's routes and these share one code path (`modules/nsot/intent_edit.py`).
"""

import re
from types import SimpleNamespace

import pytest

from modules.nsot import intent_edit
from tests.test_intent_editor import world  # noqa: F401 (the fixture)


@pytest.fixture
def ed(world, monkeypatch):  # noqa: F811
    """The v2 routes find s4 in `lab` (its inventory row, as the device page would)."""
    dev = {"hostname": "s4", "ip": "192.0.2.14", "platform": "cisco_ios",
           "device_type": "cisco_ios"}
    monkeypatch.setattr("routes.intent_v2._device_or_404",
                        lambda name: ((SimpleNamespace(name="lab"), dev), None))
    return world


def _text(html):
    m = re.search(r'<textarea id="ie-text"[^>]*>(.*?)</textarea>', html, re.S)
    assert m, html[:400]
    import html as _h
    return _h.unescape(m.group(1))


def _base(html):
    return re.search(r'name="base" value="([0-9a-f]+)"', html).group(1)


def _post(w, path, **form):
    r = w["client"].post(path, data=form)
    return r, r.get_data(as_text=True)


class TestOpening:
    def test_edit_opens_the_committed_document_at_its_blob(self, ed):
        from modules import csp
        r = ed["client"].get("/v2/device/s4/intent/edit")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert "Editing s4's intent" in html
        opened = intent_edit.open_doc("lab", "s4")
        assert _text(html) == opened["yaml"] and _base(html) == opened["base"]
        assert 'data-op="edit-intent"' in html and "Commit to s4's intent" in html

    def test_a_viewer_who_may_not_commit_gets_no_commit(self, ed, monkeypatch):
        from modules import identity
        monkeypatch.setattr(identity, "identify",
                            lambda r: identity.Identity(peer="198.51.100.7"))
        html = ed["client"].get("/v2/device/s4/intent/edit").get_data(as_text=True)
        assert "op-confirm" not in html and "Nothing can be committed from here" in html


class TestChecking:
    def test_an_error_names_its_line_and_column(self, ed):
        _r, html = _post(ed, "/v2/device/s4/intent/check", yaml="hostname: s4\ninterfaces: [\n  bad\n")
        assert re.search(r"<strong>Line \d+(, column \d+)?:</strong>", html), html
        assert "The commit waits until the document is valid" in html

    def test_a_valid_edit_draws_its_diffs_checks_and_unmodelled_lines(self, ed):
        text = intent_edit.open_doc("lab", "s4")["yaml"]
        _r, html = _post(ed, "/v2/device/s4/intent/check", yaml=text)
        assert "What your edit changes in s4" in html and "What a deploy would send" in html
        assert "some-construct nobody modelled" in html
        assert "1 not acknowledged" in html
        assert 'name="ack" value="some-construct nobody modelled"' in html


class TestAcknowledging:
    def test_ticked_lines_are_written_into_the_document_and_read_back(self, ed):
        opened = intent_edit.open_doc("lab", "s4")
        _r, html = _post(ed, "/v2/device/s4/intent/acknowledge", yaml=opened["yaml"],
                         base=opened["base"], summary="keep the construct",
                         ack="some-construct nobody modelled")
        text = _text(html)
        assert "unmodeled_ack:" in text and "some-construct nobody modelled" in text
        assert 'value="keep the construct"' in html and _base(html) == opened["base"]
        assert intent_edit.open_doc("lab", "s4")["yaml"] == opened["yaml"], "nothing committed"
        _r, check = _post(ed, "/v2/device/s4/intent/check", yaml=text)
        assert "all acknowledged" in check

    def test_the_block_is_replaced_never_doubled_and_removed_when_empty(self):
        doc = "hostname: s4\ninterfaces: []\n"
        once = intent_edit.acknowledge(doc, ["b line", "a line"])
        assert once.endswith("unmodeled_ack:\n  lines:\n  - a line\n  - b line\n")
        twice = intent_edit.acknowledge(once, ["a line"])
        assert twice.count("unmodeled_ack:") == 1 and "b line" not in twice
        assert intent_edit.acknowledge(twice, []) == doc


class TestCommitting:
    def _edited(self):
        opened = intent_edit.open_doc("lab", "s4")
        text = opened["yaml"].replace("description: uplink", "description: core uplink")
        assert text != opened["yaml"]
        return opened, text

    def test_the_commit_is_made_as_the_person_with_the_reason(self, ed):
        opened, text = self._edited()
        r, html = _post(ed, "/v2/device/s4/intent/commit", yaml=text, base=opened["base"],
                        summary="the uplink's real description")
        assert r.status_code == 200 and "Committed to s4's intent" in html, html
        assert intent_edit.open_doc("lab", "s4")["yaml"] == text
        from modules.nsot import hostvars
        last = hostvars.last_intent_commit(ed["repo"], "s4")
        assert last["subject"] == "host_vars: s4 the uplink's real description"
        assert "Nothing was sent to s4" in html

    def test_a_moved_intent_writes_nothing_and_places_the_edit_on_theirs(self, ed):
        opened, text = self._edited()
        # Another person commits a change to a DIFFERENT line first.
        theirs = opened["yaml"].replace("hostname: s4", "hostname: s4\ndomain_name: lab.example", 1)
        got = intent_edit.commit("lab", "s4", theirs, "their change", opened["base"], "other")
        assert got["ok"] and got["changed"], got
        r, html = _post(ed, "/v2/device/s4/intent/commit", yaml=text, base=opened["base"],
                        summary="mine")
        assert r.status_code == 409 and "not saved" in html and "Their change" in html
        assert intent_edit.open_doc("lab", "s4")["yaml"] == theirs, "nothing of mine written"
        assert "with your edit on it" in html
        merged = re.search(r'name="yaml" value="([^"]*)"', html, re.S).group(1)
        import html as _h
        merged = _h.unescape(merged)
        assert "domain_name: lab.example" in merged and "description: core uplink" in merged

    def test_the_same_line_changed_by_both_is_never_merged(self, ed):
        opened, text = self._edited()
        theirs = opened["yaml"].replace("description: uplink", "description: their uplink")
        assert intent_edit.commit("lab", "s4", theirs, "theirs", opened["base"], "other")["ok"]
        r, html = _post(ed, "/v2/device/s4/intent/commit", yaml=text, base=opened["base"],
                        summary="mine")
        assert r.status_code == 409 and "with your edit on it" not in html
        assert "Your whole document, to copy from" in html


def test_merge3_places_only_disjoint_changes():
    base = "a\nb\nc\nd\n"
    assert intent_edit.merge3(base, "A\nb\nc\nd\n", "a\nb\nc\nD\n") == "A\nb\nc\nD\n"
    assert intent_edit.merge3(base, "a\nB\nc\nd\n", "a\nX\nc\nd\n") is None
    assert intent_edit.merge3(base, "a\nb\nNEW\nc\nd\n", "a\nb\nMINE\nc\nd\n") is None, \
        "two inserts at one place are a person's decision"


def test_a_real_browser_acknowledges_a_line_and_commits(tmp_path, monkeypatch):
    """The path a person takes, in a real browser, on test_device_seed_v2's lab seeded through
    its real confirm with one line the template does not model: the Intent tab's Edit, the
    check drawn on load, the line ticked and written into the document (the ack form sits
    outside the editor's and carries the document by `hx-include`), the check re-read as typed,
    then the commit, in place. What landed in git is the acknowledged document."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    from tests.test_device_seed_v2 import SETTLED, _git, _serve, _vals
    from tests.test_seed_intent import UNMODELLED, build_seed_lab
    lab = _serve(build_seed_lab(monkeypatch, tmp_path, unmodelled=UNMODELLED), monkeypatch)
    card = lab["client"].get("/v2/device/r2/seed").get_data(as_text=True)
    assert lab["client"].post("/v2/device/r2/seed/confirm", data=_vals(card)).status_code == 200
    seeded = _git(lab["repo"], "rev-parse", "HEAD")
    import app as A
    CHECK = "document.querySelector('#ie-check')"
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/device/r2?tab=intent"))
            b.wait_for("return !!window.Alpine && window.NMAS && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            b.click('.card-head a[data-op="edit-intent"]')
            # The seed recorded r2's partial syslog block as the device holds it (no heartbeat
            # applet, C490); an authored document must carry it whole, so the check refuses it
            # with its line, and the person types the heartbeat in.
            b.wait_for(f"return !!{CHECK} && /no heartbeat/.test({CHECK}.textContent) && "
                       + SETTLED, 15)
            b.js("var t = document.querySelector('#ie-text');"
                 "t.value = t.value.replace('heartbeat: 0', 'heartbeat: 300');"
                 "t.dispatchEvent(new Event('input', {bubbles: true})); return 1")
            b.wait_for(f"return !!{CHECK} && /not acknowledged/.test({CHECK}.textContent) && "
                       + SETTLED, 15)
            b.js("var box = document.querySelector('#ie-check input[name=ack]');"
                 "box.checked = true; return box.value")
            b.click('#ie-check button[form="ie-ack-form"]')
            b.wait_for("var t = document.querySelector('#ie-text');"
                       "return t && /unmodeled_ack:/.test(t.value) && "
                       f"!!{CHECK} && /all acknowledged/.test({CHECK}.textContent) && " + SETTLED,
                       15)
            assert _git(lab["repo"], "rev-parse", "HEAD") == seeded, "nothing committed yet"
            b.js("var s = document.querySelector('#intent-form input[name=summary]');"
                 "s.value = 'acknowledge the alias'; return 1")
            b.click('#intent-form button[data-op="edit-intent"]')
            b.wait_for("return /Committed to r2's intent/.test(document.body.textContent) && "
                       + SETTLED, 20)
            assert b.js("return window.__notReloaded") == 1, "the commit ran in place"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert _git(lab["repo"], "log", "-1", "--format=%s") == \
        "host_vars: r2 acknowledge the alias"
    committed = _git(lab["repo"], "show", "HEAD:host_vars/r2.yml")
    assert "unmodeled_ack:" in committed and UNMODELLED in committed.split("unmodeled_ack:")[1]


def test_todays_routes_and_v2_share_one_code_path():
    from tests.astcheck import calls_in

    from routes import intent_v2, templatize

    assert calls_in(templatize.edit_committed, "commit") >= 1
    assert calls_in(templatize.preview_committed_edit, "preview") >= 1
    assert calls_in(intent_v2.commit, "commit") >= 1
    assert calls_in(intent_v2.check, "preview") >= 1
