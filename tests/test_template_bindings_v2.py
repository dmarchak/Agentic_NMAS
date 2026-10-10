"""Templates › Bindings… on v2 (cutover blocker 5, 2026-10-10), through the real app on
test_templates_v2's lab: list `Lab`, the seeded library committed (`cisco_ios/base.j2` and
`cisco_iosxe/base.j2`), s1 to s3 cisco_ios devices bound through their platform's template.

- the view: each platform's template and the overrides, each choosing among its own
  platform's committed templates;
- the preview: every device whose template moves, from and to, with whether the template it
  moves to is approved; a template of another platform, an unknown device or a template not
  committed refused naming it; nothing written;
- the apply, as the person: one commit `template: bindings <reason>`, `template_for_device`
  answering the new template; bound to the file committed at the preview and to the change
  previewed (either moved: refused, nothing written); no reason refused; a failed commit puts
  the committed file back.
"""

import re
import subprocess

import pytest

from tests.test_approvals_record import REL, lab  # noqa: F401 (the fixture)
from tests.test_templates_v2 import _get, _hidden, tl  # noqa: F401 (the fixture)

ALT = "cisco_ios/alt.j2"


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


@pytest.fixture
def alt(tl):  # noqa: F811
    """A second cisco_ios template, committed, so a device has somewhere to move."""
    from modules.nsot import repo as R, templates_repo

    text = templates_repo.read_template(tl["repo"], REL)
    assert templates_repo.write_template(tl["repo"], ALT, text)["ok"]
    assert R.save_templates("Lab", ["cisco_ios/alt.j2"], actor="t@example.invalid",
                            message="template: add alt")["ok"]
    return tl


def _form(**extra):
    return {"list": "Lab", "platform::cisco_ios": REL, **extra}


def _preview(tl, **extra):  # noqa: F811
    return tl["client"].post("/v2/templates/bindings/preview", data=_form(**extra))


def _apply(tl, html, summary="s2 renders through alt for the trial", **over):  # noqa: F811
    form = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', html))
    form.update(summary=summary, **over)
    return tl["client"].post("/v2/templates/bindings", data=form)


class TestTheView:
    def test_the_page_offers_bindings_and_the_card_draws_both_maps(self, alt):
        _r, page = _get(alt, "/v2/templates?list=Lab")
        assert 'hx-get="/v2/templates/bindings?list=Lab"' in page and "Bindings…" in page
        _r, html = _get(alt, "/v2/templates/bindings?list=Lab")
        assert 'name="platform::cisco_ios"' in html
        assert f'<option value="{ALT}">' in html and f'<option value="{REL}" selected>' in html
        assert "None: every device renders through its platform's template." in html
        assert 'name="add_device"' in html and '<option value="s2">' in html


class TestThePreview:
    def test_a_moved_device_is_named_from_and_to_with_its_approval(self, alt):
        before = _git(alt["repo"], "rev-parse", "HEAD")
        r = _preview(alt, add_device="s2", add_template=ALT)
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html[:500]
        assert "1 device will render through another template" in html
        row = re.search(r"<tr><td><a [^>]*>s2</a></td>(.*?)</tr>", html, re.S).group(1)
        assert REL in row and ALT in row and "not approved" in row
        assert "a deploy to that device is refused until approved" in html
        assert _git(alt["repo"], "rev-parse", "HEAD") == before

    @pytest.mark.parametrize("extra,words", [
        ({"add_device": "zz", "add_template": ALT}, "there is no device &#39;zz&#39;"),
        ({"add_device": "s2", "add_template": "cisco_iosxe/base.j2"},
         "s2 is a cisco_ios device"),
        ({"add_device": "s2", "add_template": "cisco_ios/nope.j2"}, "not a committed template"),
        ({"platform::cisco_ios": "cisco_iosxe/base.j2"}, "is a cisco_iosxe template"),
        ({"add_device": "s2"}, "needs both a device and a template"),
    ])
    def test_a_wrong_binding_is_refused_naming_it(self, alt, extra, words):
        r = _preview(alt, **extra)
        assert r.status_code == 400 and words in r.get_data(as_text=True)


class TestTheApply:
    def test_it_commits_as_the_person_and_the_device_renders_through_the_new_one(self, alt):
        from modules.nsot import templates_repo

        html = _preview(alt, add_device="s2", add_template=ALT).get_data(as_text=True)
        r = _apply(alt, html)
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out[:600]
        msg = _git(alt["repo"], "log", "-1", "--format=%B")
        assert msg.startswith("template: bindings s2 renders through alt for the trial")
        assert "Actor: test-person@example.invalid" in msg
        assert templates_repo.template_for_device(alt["repo"], "s2", "cisco_ios") == ALT
        assert templates_repo.template_for_device(alt["repo"], "s1", "cisco_ios") == REL
        assert "Bindings" in out and "committed" in out and "s2" in out

    def test_bindings_moved_since_the_preview_are_refused(self, alt):
        from modules.nsot import repo as R, templates_repo

        html = _preview(alt, add_device="s2", add_template=ALT).get_data(as_text=True)
        b = templates_repo.load_bindings(alt["repo"])
        b["overrides"]["s3"] = ALT
        templates_repo.save_bindings(alt["repo"], b)
        R.save_templates("Lab", ["bindings.yml"], actor="other@example.invalid",
                         message="template: bindings someone else's")
        head = _git(alt["repo"], "rev-parse", "HEAD")
        r = _apply(alt, html)
        assert r.status_code == 409 and "changed after your preview" in r.get_data(as_text=True)
        assert _git(alt["repo"], "rev-parse", "HEAD") == head

    def test_a_change_other_than_the_one_previewed_is_refused(self, alt):
        html = _preview(alt, add_device="s2", add_template=ALT).get_data(as_text=True)
        head = _git(alt["repo"], "rev-parse", "HEAD")
        r = _apply(alt, html, add_device="s3")
        assert r.status_code == 409 and "not the change previewed" in r.get_data(as_text=True)
        assert _git(alt["repo"], "rev-parse", "HEAD") == head

    def test_no_reason_is_refused(self, alt):
        html = _preview(alt, add_device="s2", add_template=ALT).get_data(as_text=True)
        r = _apply(alt, html, summary=" ")
        assert r.status_code == 400 and "say why in one line" in r.get_data(as_text=True)

    def test_a_failed_commit_puts_the_committed_file_back(self, alt, monkeypatch):
        from modules.nsot import repo as R, templates_repo

        html = _preview(alt, add_device="s2", add_template=ALT).get_data(as_text=True)
        monkeypatch.setattr(R, "save_templates", lambda *a, **k: {"ok": False,
                                                                  "error": "planted"})
        r = _apply(alt, html)
        out = r.get_data(as_text=True)
        assert r.status_code == 500 and "the committed bindings are back in place" in out
        assert templates_repo.template_for_device(alt["repo"], "s2", "cisco_ios") == REL

    @pytest.mark.real_identity
    def test_it_needs_a_person(self, alt):
        r = alt["client"].post("/v2/templates/bindings", data=_form(summary="x"))
        assert r.status_code in (401, 403)


def test_hidden_fields_carry_the_change_and_the_binding(alt):
    html = _preview(alt, add_device="s2", add_template=ALT).get_data(as_text=True)
    assert _hidden(html, "add_device") == "s2" and _hidden(html, "add_template") == ALT
    assert re.fullmatch(r"[0-9a-f]{64}", _hidden(html, "fingerprint") or "")
    assert _hidden(html, "base") is not None
