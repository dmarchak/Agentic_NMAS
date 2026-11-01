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
- These run the one code path (`modules/nsot/intent_edit.py`); today's routes, which shared
  it, left at 7.8 (2026-10-17, P7-23).
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

    def test_the_editor_names_the_commit_the_rest_of_mercury_names(self, ed):
        """C2292 (the operator's r2, 2026-11-01: the editor said "opened at ff1ead7", the
        committed view and the deploy 715e3cc14b): opened at the commit, as they name it, and
        the document's own id labelled beside it, never alone."""
        from modules.nsot import hostvars
        html = ed["client"].get("/v2/device/s4/intent/edit").get_data(as_text=True)
        last = hostvars.last_intent_commit(ed["repo"], "s4")
        base = intent_edit.open_doc("lab", "s4")["base"]
        assert re.search(r'opened at commit <span class="mono" title="[0-9a-f]+">'
                         + re.escape(last["commit"][:10]) + "</span>", html), html[:900]
        assert f'document <span class="mono" title="the document' in html and base[:7] in html
        assert f'opened at <span class="mono">{base[:7]}</span>' not in html

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

    def test_a_reference_with_no_value_greys_the_deploy_and_offers_set_value(
            self, ed, tmp_path, monkeypatch):
        """C2288 (the operator's process finding, 2026-11-01, the lab account on r2 to r4): a
        commit naming a reference with no value names it on the result with Set value…, and
        Plan a deploy… is greyed naming it until it holds one; the offer is re-read when a
        value is stored, and offers Plan a deploy… once none is missing. No value is drawn."""
        from modules import credentials
        from modules.nsot import secret_refs
        monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "credential_profiles.json"))
        opened = intent_edit.open_doc("lab", "s4")
        text = opened["yaml"].replace("users: []\n", "users:\n- name: lab\n  privilege: 15\n"
                                      "  secret_kind: secret\n  secret_ref: user_lab_secret\n", 1)
        assert text != opened["yaml"]
        r, html = _post(ed, "/v2/device/s4/intent/commit", yaml=text, base=opened["base"],
                        summary="the temporary lab account")
        assert r.status_code == 200 and "Committed to s4's intent" in html, html[:600]
        offer = html.split('id="ie-deploy-offer"')[1]
        assert "Before it can be deployed" in offer and "user_lab_secret" in offer
        assert 'hx-get="/v2/device/s4/intent/secrets?set=user_lab_secret"' in offer
        assert 'aria-disabled="true"' in offer and "no value" in offer
        assert 'href="/v2/device/s4?op=deploy"' not in offer
        assert 'hx-trigger="nmas:credentials from:body"' in offer
        # Every reference named, valued: the offer re-read offers Plan a deploy….
        for ref in [m for m in re.findall(r'set=([a-z_0-9]+)"', offer)]:
            credentials.set_template_secret(credentials.template_secret_key("lab", "s4", ref),
                                            "Not-Real-1", list_name="lab")
        again = ed["client"].get("/v2/device/s4/intent/deploy-offer").get_data(as_text=True)
        assert "Before it can be deployed" not in again, again[:600]
        assert 'href="/v2/device/s4?op=deploy"' in again and "Not-Real-1" not in again
        assert secret_refs.listing("lab", "s4")["counts"]["none"] == 0

    def test_another_account_naming_the_sign_in_reference_is_refused_at_commit(
            self, ed, monkeypatch):
        """C2289 (the operator's r6, 2026-11-01: `lab` committed with `secret_ref:
        user_admin_secret`, the account Mercury signs in with): refused at commit, nothing
        written, in the words Set value… uses for the same rule; the account itself may name it,
        and bulk intent refuses the same result."""
        from modules.nsot import bulk_intent, secret_refs
        monkeypatch.setattr(intent_edit, "_signs_in_as", lambda list_name, host: "admin")
        opened = intent_edit.open_doc("lab", "s4")

        def users(*names):
            return opened["yaml"].replace("users: []\n", "users:\n" + "".join(
                f"- name: {n}\n  privilege: 15\n  secret_kind: secret\n"
                "  secret_ref: user_admin_secret\n" for n in names), 1)
        shared = users("admin", "lab")
        r, html = _post(ed, "/v2/device/s4/intent/commit", yaml=shared, base=opened["base"],
                        summary="the temporary lab account")
        import html as _h
        words = secret_refs.managed_words("user_admin_secret")
        assert r.status_code == 400 and "Committed to" not in html, html[:400]
        said = _h.unescape(html)
        assert "account lab names user_admin_secret" in said and words in said, said[:800]
        assert intent_edit.open_doc("lab", "s4")["yaml"] == opened["yaml"], "nothing written"
        assert words == ("user_admin_secret is the account Mercury signs in with; it changes "
                         "by Rotate only and can't be shared")
        assert any(c["detail"] == words for c in secret_refs.check(
            "lab", "s4", "user_admin_secret", "x", "x", "r", signs_in_as="admin",
            intent={"users": [{"name": "admin", "secret_ref": "user_admin_secret"}]})), \
            "Set value… keeps the same rule in the same words"
        assert intent_edit.validate("s4", users("admin"), "lab")["ok"], "its own account may"
        report = bulk_intent.plan(ed["repo"], ["s4"], [{
            "path": ["users"], "before": [],
            "after": [{"name": "lab", "privilege": 15, "secret_kind": "secret",
                       "secret_ref": "user_admin_secret"}]}],
            render=lambda h, hv: ("", True, []), list_name="lab")
        assert report["refused"] and words in report["refused"][0]["reason"], report

    def test_a_moved_intent_writes_nothing_and_places_the_edit_on_theirs(self, ed):
        opened, text = self._edited()
        # Another person commits a change to a DIFFERENT line first.
        # In Mercury's own formatting, as every commit is written since C1693, so what is
        # committed is their text byte for byte.
        from modules.nsot import hostvars
        theirs = hostvars.to_yaml(dict(hostvars.from_yaml(opened["yaml"]),
                                       domain_name="lab.example"))
        assert hostvars.canonical(theirs) == theirs
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


def test_the_tab_runs_the_one_code_path():
    """Today's editor routes, which shared `intent_edit`, left at 7.8 (2026-10-17, P7-23); the
    tab's check, acknowledge, commit and opening still run it, and no route outside it
    commits intent edits by another path."""
    from tests.astcheck import calls_in

    from routes import intent_v2, templatize

    assert calls_in(intent_v2.commit, "commit") >= 1
    assert calls_in(intent_v2.check, "preview") >= 1
    assert calls_in(intent_v2.acknowledge, "acknowledge") >= 1
    assert "intent_edit.open_doc" in open(intent_v2.__file__, encoding="utf-8").read()
    assert not any(hasattr(templatize, f) for f in
                   ("read_committed", "preview_committed_edit", "edit_committed"))
