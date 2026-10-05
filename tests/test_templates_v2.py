"""Source of truth › Templates on v2 (7.6, boards A to C, signed off 2026-10-05; C481), through
the real app and routes on test_approvals_record's lab: list `Lab`, the seeded library
committed, s1 to s3 bound to `cisco_ios/base.j2`. s1's capture is its REAL fleet config with
one block the parser does not model; s2 and s3 have no capture yet.

- A: the counts, each template's platform, imports, bound devices and approval, under the
  strict policy; the sidebar's Templates opens it.
- B: Approve… names, device by device, the comparison and every failing line: the unmodelled
  line not acknowledged in s1's committed intent, with the link to its Intent tab's editor; the
  devices not validated; no confirm. Once the acknowledgement is committed in s1's intent the
  same check passes (C481), and the confirm carries the fingerprint and the check as read.
- The confirm approves as the person and commits; a check that moved since it was read, or a
  template that moved since it was shown, approves nothing and says what moved.
- C: Revoke… asks why, refuses without one, and records and commits it; the row says so.
- A viewer who may not approve gets no confirm; `?approve=<path>` opens the card on the page.
- Today's routes and these share one code path (`modules/nsot/approve_op.py`).
"""

import re

import pytest

from modules.nsot import approval
from tests.test_approvals_record import REL, lab  # noqa: F401 (the fixture)
from tests.test_template_approval import QUANTUM, _ack_doc, _commit_intent, _config


@pytest.fixture
def tl(lab, monkeypatch):  # noqa: F811
    """The v2 page on the lab: `Lab` exists, and s1 alone has a capture."""
    import app as A

    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    caps = {"s1": _config("s1") + QUANTUM}
    monkeypatch.setattr("modules.nsot.approve_op._capture", lambda _repo, name: caps.get(name))
    return {"repo": lab, "client": A.app.test_client(), "caps": caps}


def _get(tl, url):
    r = tl["client"].get(url)
    return r, r.get_data(as_text=True)


def _check(tl):
    return _get(tl, f"/v2/templates/approve?list=Lab&path={REL}")


def _hidden(html, name):
    m = re.search(rf'name="{name}" value="([^"]*)"', html)
    return m.group(1) if m else None


def _ack_s1(tl):
    """Commit s1's acknowledgement of every line its capture does not model, as the intent
    editor writes it (the lines from the check itself)."""
    from modules.nsot import approve_op
    lines = approve_op.check("Lab", REL)["results"][0]["unacknowledged"]
    assert "quantum-tunnel profile ALPHA" in lines
    _commit_intent(tl["repo"], "s1", _ack_doc("s1", lines))


def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


class TestThePage:
    def test_the_templates_with_their_approvals(self, tl):
        from modules import csp
        r, html = _get(tl, "/v2/templates?list=Lab")
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert "Templates · Lab" in html and REL in html and "IOS-XE" in html
        assert re.search(r"not approved <strong>\d+</strong>", html)
        assert "3: " in html and ">s1</a>" in html and ">s3</a>" in html
        assert "never approved" in html
        assert 'data-op="approve-template"' in html and re.search(r'approve=cisco_ios(/|%2F)base.j2', html)
        assert 'aria-current="page"' in html.split("Templates</span>")[0][-400:]

    def test_the_deep_link_opens_the_check_on_the_page(self, tl):
        _r, html = _get(tl, f"/v2/templates?list=Lab&approve={REL}")
        assert f"Approve {REL} for Lab" in html and 'id="templates"' in html


class TestApproveRefusesNamingTheLine:
    def test_the_unacknowledged_line_is_named_with_where_to_clear_it(self, tl):
        r, html = _check(tl)
        assert r.status_code == 200
        assert "quantum-tunnel profile ALPHA" in html and "not acknowledged" in html
        assert "/v2/device/s1?tab=intent&amp;edit=1" in html
        assert "s2</a>: no captured config yet" in html and "s3</a>: no captured config yet" in html
        assert "Not available: no bound device reproduces" in html
        assert "op-confirm" not in html, "nothing to confirm"

    def test_a_committed_acknowledgement_lets_it_pass(self, tl):
        _ack_s1(tl)
        _r, html = _check(tl)
        assert "unmodelled, acknowledged" in html and "not acknowledged" not in html
        assert 'data-op="approve-template"' in html and "op-confirm" in html
        assert _hidden(html, "fingerprint") and _hidden(html, "seen")


class TestTheConfirm:
    def test_it_approves_as_the_person_and_commits(self, tl):
        from tests.conftest import TEST_PERSON
        _ack_s1(tl)
        _r, card = _check(tl)
        r = tl["client"].post("/v2/templates/approve", data={
            "list": "Lab", "path": REL, "fingerprint": _hidden(card, "fingerprint"),
            "seen": _hidden(card, "seen")})
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html
        assert "Approved by" in html and "Validated: s1" in html and "Not validated: s2" in html
        assert approval.is_approved(tl["repo"], REL)
        assert _git(tl["repo"], "log", "-1", "--format=%s").strip() == f"template: approve {REL}"
        assert TEST_PERSON in _git(tl["repo"], "log", "-1", "--format=%B")
        assert re.search(r"approved <strong>1</strong>", html), "the row redrawn"

    def test_a_check_that_moved_since_it_was_read_approves_nothing(self, tl):
        _ack_s1(tl)
        _r, card = _check(tl)
        _commit_intent(tl["repo"], "s1", _ack_doc("s1", []))      # the acknowledgement withdrawn
        head = _git(tl["repo"], "rev-parse", "HEAD")
        r = tl["client"].post("/v2/templates/approve", data={
            "list": "Lab", "path": REL, "fingerprint": _hidden(card, "fingerprint"),
            "seen": _hidden(card, "seen")})
        html = r.get_data(as_text=True)
        assert r.status_code == 409 and "the check you read is not the check now" in html
        assert "fails s1" in html and not approval.is_approved(tl["repo"], REL)
        assert _git(tl["repo"], "rev-parse", "HEAD") == head

    def test_a_template_that_moved_since_it_was_shown_approves_nothing(self, tl):
        _ack_s1(tl)
        _r, card = _check(tl)
        r = tl["client"].post("/v2/templates/approve", data={
            "list": "Lab", "path": REL, "fingerprint": "0" * 16, "seen": _hidden(card, "seen")})
        html = r.get_data(as_text=True)
        assert r.status_code == 400 and "changed after your page showed it" in html
        assert "000000000000" in html and not approval.is_approved(tl["repo"], REL)

    def test_a_viewer_who_may_not_approve_gets_no_confirm(self, tl, monkeypatch):
        from modules import identity
        _ack_s1(tl)
        monkeypatch.setattr(identity, "identify",
                            lambda r: identity.Identity(peer="198.51.100.7"))
        _r, html = _check(tl)
        assert "op-confirm" not in html and "Nothing can be approved from here" in html


class TestRevoke:
    def _approved(self, tl):
        _ack_s1(tl)
        _r, card = _check(tl)
        assert tl["client"].post("/v2/templates/approve", data={
            "list": "Lab", "path": REL, "fingerprint": _hidden(card, "fingerprint"),
            "seen": _hidden(card, "seen")}).status_code == 200

    def test_revoke_asks_why_and_refuses_without_one(self, tl):
        self._approved(tl)
        _r, form = _get(tl, f"/v2/templates/revoke?list=Lab&path={REL}")
        assert 'name="reason"' in form and "required" in form
        r = tl["client"].post("/v2/templates/revoke", data={"list": "Lab", "path": REL,
                                                             "reason": " "})
        assert r.status_code == 400 and "needs a reason" in r.get_data(as_text=True)
        assert approval.is_approved(tl["repo"], REL)

    def test_the_revocation_is_recorded_committed_and_shown(self, tl):
        self._approved(tl)
        why = "the interface macro drops descriptions on Port-channels"
        r = tl["client"].post("/v2/templates/revoke", data={"list": "Lab", "path": REL,
                                                             "reason": why})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "Revoked by" in html and why in html
        assert not approval.is_approved(tl["repo"], REL)
        assert _git(tl["repo"], "log", "-1", "--format=%s").strip() == \
            f"template: revoke approval for {REL}"
        assert re.search(r"revoked <strong>1</strong>", html)


def test_a_real_browser_approves_after_the_acknowledgement_then_revokes(tl):
    """The path a person takes, in a real browser: the row's Approve…, the refusal naming the
    line; the acknowledgement committed in s1's intent (as the intent editor would); Check
    again, now passing; the confirm, the result and the row in place (the page never reloaded);
    then Revoke… with its reason. What landed in git is both commits, as the person."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from tests.test_device_seed_v2 import SETTLED
    CARD = "document.querySelector('#tpl-card')"
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/templates?list=Lab"))
            b.wait_for("return !!window.Alpine && window.NMAS && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            b.click(".tpl-act a.btn-primary[data-op='approve-template']")
            b.wait_for(f"return !!{CARD} && /quantum-tunnel profile ALPHA/.test({CARD}.textContent)"
                       f" && /Not available/.test({CARD}.textContent) && " + SETTLED, 15)
            _ack_s1(tl)
            b.click("#tpl-card .op-ft button[data-op='approve-template']")     # Check again
            b.wait_for(f"return !!{CARD} && !!{CARD}.querySelector('.op-confirm') && " + SETTLED,
                       15)
            b.click("#tpl-card .op-confirm")
            b.wait_for(f"return !!{CARD} && /Approved by/.test({CARD}.textContent) && "
                       "/approved <strong>1<\\/strong>/.test(document.querySelector('.tpl-counts')"
                       ".innerHTML) && " + SETTLED, 20)
            b.click(".tpl-act a.btn[data-op='approve-template']")              # Revoke…
            b.wait_for("return !!document.querySelector('#tpl-card input[name=reason]') && "
                       + SETTLED, 15)
            b.js("document.querySelector('#tpl-card input[name=reason]').value = "
                 "'the interface macro drops descriptions'; return 1")
            b.click("#tpl-card .op-confirm")
            b.wait_for(f"return !!{CARD} && /Revoked by/.test({CARD}.textContent) && " + SETTLED,
                       20)
            assert b.js("return window.__notReloaded") == 1, "approved and revoked in place"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    subjects = _git(tl["repo"], "log", "-2", "--format=%s").split("\n")
    assert subjects[:2] == [f"template: revoke approval for {REL}", f"template: approve {REL}"]
    assert not approval.is_approved(tl["repo"], REL)


def test_todays_routes_and_v2_share_one_code_path():
    from tests.astcheck import calls_in

    from routes import templates, templates_v2

    assert calls_in(templates.approve, "approve") >= 1
    assert calls_in(templates.revoke_approval, "revoke") >= 1
    assert calls_in(templates.validate, "bound_captures") >= 1
    assert calls_in(templates_v2.approve, "approve") >= 1
    assert calls_in(templates_v2.revoke, "revoke") >= 1
