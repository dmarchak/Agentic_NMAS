"""C566, board B (signed off 2026-10-07): Templates › Bring in the shipped version, end to end.

The operator's walk of P1 found the network's `_common.j2` an older shipped version, unedited,
that renders none of the profile's management section (C565). On v2 the row says "behind", its
Bring in the shipped version… previews the diff and what each bound device's render gains, and
the confirm commits the shipped file as the person, bound to both files, revoking the approvals
over it. Then the device's plan sends the section's two lines.

On test_profile_apply's lab (r2's real golden and intent), with the management section
proposed as on the host and `_common.j2` committed as the shipped version from before P1.
"""

import html as html_mod
import os
import re

import pytest

from tests.test_profile_apply import lab  # noqa: F401 (the fixture)
from tests.test_profile_reaches_the_program import (BEFORE_P1, LINES, _plan,
                                                   _propose_management, _stale_common)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _commit_stale(lab):  # noqa: F811
    from modules.nsot import repo as R
    _stale_common(lab)
    assert R.save_templates("Lab", ["_common.j2", "cisco_ios/base.j2", "cisco_iosxe/base.j2"],
                            actor="t", message="the host's copy")["ok"]


@pytest.fixture
def stale(lab, monkeypatch):  # noqa: F811
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    _propose_management(lab)
    _commit_stale(lab)
    return lab


def _hidden(html, name):
    m = re.search(rf'name="{name}" value="([^"]*)"', html)
    return m.group(1) if m else None


class TestTheRow:
    def test_the_shared_file_is_a_row_and_says_behind(self, stale):
        from modules.nsot import approve_op
        lib = approve_op.library("Lab")
        row = next(r for r in lib["rows"] if r["path"] == "_common.j2")
        assert row["kind"] == "shared" and row["shipped"]["state"] == "stale"
        assert sorted(row["importers"]) == ["cisco_ios/base.j2", "cisco_iosxe/base.j2"]
        assert lib["behind"] == 1
        html = stale["client"].get("/v2/templates?list=Lab").get_data(as_text=True)
        assert "1 behind the shipped version" in html
        assert 'href="/v2/templates?list=Lab&amp;bring=_common.j2"' in html
        assert "no approval of its own: imported by 2 templates" in html


class TestThePreview:
    def test_it_shows_the_diff_and_what_r2_gains(self, stale):
        html = html_mod.unescape(stale["client"].get(
            "/v2/templates/bring?list=Lab&path=_common.j2").get_data(as_text=True))
        assert "Bring in the shipped" in html and "source_interfaces" in html
        assert re.search(r"r2</a>: gains 2, loses 0", html), html[html.find("On the devices"):][:600]
        for line in LINES:
            assert f"+ {line}" in html
        assert _hidden(html, "copy_blob") and _hidden(html, "shipped_blob")

    def test_a_current_copy_is_not_offered(self, lab, monkeypatch):  # noqa: F811
        monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
        html = lab["client"].get("/v2/templates/bring?list=Lab&path=_common.j2").get_data(
            as_text=True)
        assert "is already the shipped version: nothing to bring in" in html
        assert 'name="copy_blob"' not in html

    def test_an_edited_copy_is_not_offered(self, stale):
        from modules.nsot import repo as R
        path = os.path.join(stale["repo"], "templates", "_common.j2")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("{#- a local note -#}\n")
        assert R.save_templates("Lab", ["_common.j2"], actor="t", message="edit")["ok"]
        html = html_mod.unescape(stale["client"].get(
            "/v2/templates/bring?list=Lab&path=_common.j2").get_data(as_text=True))
        assert "a merge a person makes" in html and 'name="copy_blob"' not in html


class TestTheConfirm:
    def _confirm(self, stale, **over):
        card = stale["client"].get("/v2/templates/bring?list=Lab&path=_common.j2").get_data(
            as_text=True)
        data = {"list": "Lab", "path": "_common.j2", "copy_blob": _hidden(card, "copy_blob"),
                "shipped_blob": _hidden(card, "shipped_blob")}
        data.update(over)
        return stale["client"].post("/v2/templates/bring", data=data)

    def test_it_commits_the_shipped_file_and_then_r2_is_sent_the_lines(self, stale):
        from modules.nsot import templates_repo
        _body, d = _plan(stale)
        assert d["unrendered"][0]["section"] == "management"
        r = self._confirm(stale)
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html
        assert "is the shipped version" in html
        shipped = open(os.path.join(templates_repo.BUILTIN_ROOT, "_common.j2"),
                       encoding="utf-8").read()
        copy = open(os.path.join(stale["repo"], "templates", "_common.j2"),
                    encoding="utf-8").read()
        assert copy == shipped
        import subprocess
        log = subprocess.run(["git", "-C", stale["repo"], "log", "-1", "--format=%s"],
                             capture_output=True, text=True).stdout
        assert log.startswith("template: ") and "_common.j2" in log
        _body, d = _plan(stale)
        assert "unrendered" not in d
        assert LINES <= {c.strip() for c in d["commands"]}

    def test_a_moved_copy_refuses_and_writes_nothing(self, stale):
        before = open(os.path.join(stale["repo"], "templates", "_common.j2"),
                      encoding="utf-8").read()
        r = self._confirm(stale, copy_blob="0" * 40)
        html = html_mod.unescape(r.get_data(as_text=True))
        assert r.status_code == 409
        assert "Not brought in: the preview was of the network's copy 0000000000" in html
        assert open(os.path.join(stale["repo"], "templates", "_common.j2"),
                    encoding="utf-8").read() == before

    def test_the_history_before_p1_is_the_stale_copy(self):
        """The fixture's premise: the shipped file before P1 lacks the lines (C565)."""
        assert BEFORE_P1
