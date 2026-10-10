"""Templates › Edit… on v2 (cutover blocker 5, 2026-10-10; intent editor H's pattern), through
the real app on test_templates_v2's lab: list `Lab`, the seeded library committed, s1 to s3
bound to `cisco_ios/base.j2`, s1's capture its REAL fleet config with one block the parser does
not model, s2 and s3 with none.

- Edit… opens the committed template in place, with the blob it was opened at, what it renders
  and the approvals a commit would revoke;
- the check, as typed: a syntax error named with its line; the edit rendered for every device it
  governs against its committed golden (never a backup), each failing line named, a device with
  no golden named with Capture…; a shared file checked through each template importing it; it
  writes nothing in the repository; what it draws is masked;
- the commit, as the person, bound to the version opened: one commit `template: <path>
  <reason>`, the approvals over it revoked in the same commit and Approve… offered; a template
  moved since it was opened is refused naming both versions, nothing written; no reason, a
  syntax error, refused; unchanged text commits nothing;
- one code path: today's `write_template` and this share `template_write.commit`.
"""

import re
import subprocess

import pytest

from tests.test_approvals_record import REL, lab  # noqa: F401 (the fixture)
from tests.test_templates_v2 import _get, _hidden, tl  # noqa: F401 (the fixture)

PLANTED = "PLANTEDKEY7731"


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


def _open(tl, path=REL):  # noqa: F811
    r, html = _get(tl, f"/v2/templates/edit?list=Lab&path={path}")
    assert r.status_code == 200, html[:400]
    return html


def _text(html):
    import html as H
    m = re.search(r'<textarea id="te-text"[^>]*>(.*?)</textarea>', html, re.S)
    return H.unescape(m.group(1))


def _check(tl, text, path=REL):  # noqa: F811
    r = tl["client"].post("/v2/templates/edit/check",
                          data={"list": "Lab", "path": path, "text": text})
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _commit(tl, text, base, summary="tidy the banner", path=REL):  # noqa: F811
    return tl["client"].post("/v2/templates/edit", data={
        "list": "Lab", "path": path, "text": text, "base": base, "summary": summary})


class TestOpen:
    def test_the_row_offers_edit_and_the_card_opens_the_committed_text(self, tl):  # noqa: F811
        from modules import csp
        from modules.nsot import templates_repo

        r, page = _get(tl, "/v2/templates?list=Lab")
        assert r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert f'hx-get="/v2/templates/edit?list=Lab&amp;path={REL.replace("/", "%2F")}"' in page \
            or f'hx-get="/v2/templates/edit?list=Lab&amp;path={REL}"' in page
        html = _open(tl)
        base = _hidden(html, "base")
        assert base and base == templates_repo.committed_blob(tl["repo"], REL)
        assert _text(html) == templates_repo.read_template(tl["repo"], REL)
        assert "3 devices through" in html and "Commit cisco_ios/base.j2" in html

    def test_a_deep_link_opens_the_editor_on_the_page(self, tl):  # noqa: F811
        _r, page = _get(tl, f"/v2/templates?list=Lab&edit={REL}")
        assert '<textarea id="te-text"' in page

    def test_an_unknown_template_is_refused(self, tl):  # noqa: F811
        r, html = _get(tl, "/v2/templates/edit?list=Lab&path=cisco_ios/nope.j2")
        assert r.status_code == 404 and "there is no template" in html


class TestTheCheck:
    def test_a_syntax_error_is_named_with_its_line(self, tl):  # noqa: F811
        html = _check(tl, "hostname {{ hostname }\n")
        assert "Does not parse:" in html and "line 1" in html

    def test_the_edit_is_rendered_for_each_device_against_its_golden(self, tl):  # noqa: F811
        """s1 has a golden: its result is drawn with the failing lines; s2 and s3 have none and
        are named with Capture…."""
        from modules.nsot import templates_repo

        text = templates_repo.read_template(tl["repo"], REL)
        html = _check(tl, text)
        assert "parses" in html and "0 of 1 reproduce" in html
        assert "quantum-tunnel profile ALPHA" in html                # the unmodelled block
        for d in ("s2", "s3"):
            assert f'href="/v2/device/{d}?op=capture"' in html and f"Capture {d}…" in html
        assert "unchanged from what is committed" in html

    def test_an_edit_that_drops_a_section_names_what_the_render_misses(self, tl):  # noqa: F811
        from modules.nsot import templates_repo

        text = templates_repo.read_template(tl["repo"], REL)
        loop = "{%- for i in vars.interfaces %}\n{{ c.interface(i) }}\n{%- endfor %}\n"
        assert loop in text, "the shipped template's interface loop moved: update this test"
        html = _check(tl, text.replace(loop, ""))
        assert "Not reproduced by the render:" in html
        assert re.search(r"(?m)^interface \S", html), "no interface named as missing"

    def test_the_check_writes_nothing_in_the_repository(self, tl):  # noqa: F811
        before = _git(tl["repo"], "status", "--porcelain", "--untracked-files=all")
        head = _git(tl["repo"], "rev-parse", "HEAD")
        _check(tl, "! a different template\n")
        assert _git(tl["repo"], "status", "--porcelain", "--untracked-files=all") == before
        assert _git(tl["repo"], "rev-parse", "HEAD") == head

    def test_what_it_draws_is_masked(self, tl):  # noqa: F811
        """A line the render misses is the golden's line, verbatim: the check masks it."""
        tl["caps"]["s1"] += f"key chain K1\n key 1\n  key-string {PLANTED}\n"
        from modules.nsot import templates_repo
        html = _check(tl, templates_repo.read_template(tl["repo"], REL))
        assert "key-string" in html, "the planted line is not drawn at all, so this proves nothing"
        assert PLANTED not in html


class TestTheCommit:
    def test_it_commits_as_the_person_and_revokes_the_approvals_over_it(self, tl, monkeypatch):  # noqa: F811
        from modules.nsot import approval, templates_repo

        monkeypatch.setattr(approval, "approved_templates", lambda repo: [REL])
        html = _open(tl)
        base = _hidden(html, "base")
        assert "revokes the approval of" in html
        new = templates_repo.read_template(tl["repo"], REL) + "! edited on v2\n"
        r = _commit(tl, new, base)
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out[:600]
        msg = _git(tl["repo"], "log", "-1", "--format=%B")
        assert msg.startswith(f"template: {REL} tidy the banner")
        assert "Actor: test-person@example.invalid" in msg
        assert "committed" in out and "Approve cisco_ios/base.j2…" in out
        assert templates_repo.read_template(tl["repo"], REL).endswith("! edited on v2\n")

    def test_a_template_moved_since_it_was_opened_is_refused_naming_both(self, tl):  # noqa: F811
        from modules.nsot import templates_repo

        html = _open(tl)
        base = _hidden(html, "base")
        text = templates_repo.read_template(tl["repo"], REL)
        assert _commit(tl, text + "! theirs\n", base, summary="their change").status_code == 200
        head = _git(tl["repo"], "rev-parse", "HEAD")
        r = _commit(tl, text + "! mine\n", base, summary="my change")
        out = r.get_data(as_text=True)
        assert r.status_code == 409 and "not saved" in out
        assert f"You opened <span class=\"mono\">{base[:7]}</span>" in out
        assert "their change" in out and "! mine" in out
        assert _git(tl["repo"], "rev-parse", "HEAD") == head

    @pytest.mark.parametrize("text_suffix,summary,words", [
        ("! x\n", "", "say why in one line"),
        ("{% if %}\n", "a reason", "does not parse"),
    ])
    def test_refusals_write_nothing(self, tl, text_suffix, summary, words):  # noqa: F811
        from modules.nsot import templates_repo

        base = _hidden(_open(tl), "base")
        head = _git(tl["repo"], "rev-parse", "HEAD")
        r = _commit(tl, templates_repo.read_template(tl["repo"], REL) + text_suffix, base,
                    summary=summary)
        assert r.status_code == 400 and words in r.get_data(as_text=True)
        assert _git(tl["repo"], "rev-parse", "HEAD") == head

    def test_unchanged_text_commits_nothing(self, tl):  # noqa: F811
        html = _open(tl)
        head = _git(tl["repo"], "rev-parse", "HEAD")
        r = _commit(tl, _text(html), _hidden(html, "base"))
        assert r.status_code == 200 and "unchanged" in r.get_data(as_text=True)
        assert _git(tl["repo"], "rev-parse", "HEAD") == head

    @pytest.mark.real_identity
    def test_it_needs_a_person(self, tl):  # noqa: F811
        r = _commit(tl, "x", "")
        assert r.status_code in (401, 403)


def test_a_shared_file_is_checked_through_each_template_importing_it(tl):  # noqa: F811
    from modules.nsot import templates_repo

    shared = next((t["path"] for t in templates_repo.list_templates(tl["repo"])
                   if t["path"].split("/")[-1].startswith("_")), None)
    if not shared:
        pytest.skip("the seeded library has no shared file")
    html = _check(tl, templates_repo.read_template(tl["repo"], shared), path=shared)
    assert f"Through <span class=\"mono\">{REL}</span>" in html


def test_a_real_browser_edits_checks_and_commits_in_place(tl):  # noqa: F811
    """The path a person takes: the row's Edit…, the check filling in beside the text, an edit
    that drops the interface loop named as missing, then the reason and Commit, the result in
    place with the page never reloaded; what landed in git is the commit, as the person."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from tests.test_device_seed_v2 import SETTLED
    CHECK = "document.querySelector('#te-check')"
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/templates?list=Lab"))
            b.wait_for("return !!window.Alpine && window.NMAS && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            b.click(".tpl-act a[data-op='edit-template']")
            b.wait_for(f"return !!{CHECK} && /parses/.test({CHECK}.textContent) && " + SETTLED,
                       20)
            b.js("var t = document.getElementById('te-text');"
                 "t.value = t.value.replace('{%- for i in vars.interfaces %}\\n{{ c.interface(i) "
                 "}}\\n{%- endfor %}\\n', '');"
                 "t.dispatchEvent(new Event('input', {bubbles: true})); return 1")
            b.wait_for(f"return /Not reproduced by the render/.test({CHECK}.textContent) && "
                       + SETTLED, 20)
            b.js("document.querySelector('#te-form input[name=summary]').value = "
                 "'drop the interfaces for a test'; return 1")
            b.click("#te-form .op-confirm")
            b.wait_for("return !!document.querySelector('#tpl-card') && "
                       "/committed/.test(document.querySelector('#tpl-card').textContent) && "
                       + SETTLED, 20)
            assert b.js("return window.__notReloaded") == 1, "edited and committed in place"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert _git(tl["repo"], "log", "-1", "--format=%s") == \
        f"template: {REL} drop the interfaces for a test\n"


def test_one_code_path_with_today_s_editor():
    from tests.astcheck import calls_in

    from modules.nsot import template_edit
    from routes import templates as v1, templates_v2 as v2

    assert calls_in(template_edit.commit, "commit") >= 1
    assert "template_write" in open(template_edit.__file__, encoding="utf-8").read()
    assert calls_in(v1._write_template_locked, "commit") == 1
    assert calls_in(v2.edit_commit, "commit") == 1
