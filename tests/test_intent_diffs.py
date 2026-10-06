"""C500 (the operator, 2026-10-05, on tw-ztp-a; board H revised, approved 2026-10-05, canvas
v52): the intent editor drew two identical diffs whenever the device matched its intent, which
teaches a person to skim the one that matters when they differ.

- The rule, as approved: the two diffs are EQUAL when the deploy's lines are exactly the edit's
  added lines and every line the edit deletes is a one-setting line an added one replaces; then
  ONE diff and "A deploy would send exactly this change". Otherwise both, the deploy's lines
  split into those from this edit and those not, and a line this edit deletes that a
  merge-only deploy keeps said plainly.
- "Not from this edit" lines are labelled from the device's golden history: held by an earlier
  golden and gone since is "changed on the device"; never held is "not yet deployed"; when the
  history cannot say, "already pending" alone.
- Every diff line is its own row: a 3-line diff renders as 3 lines, in a real browser.
"""

import os
import re
import subprocess

import pytest

from modules.nsot import intent_edit
from tests.test_intent_editor_v2 import _post, ed  # noqa: F401 (the fixture)
from tests.test_intent_editor import world  # noqa: F401 (the fixture)

DEVICE = ("hostname r3\nntp server 192.0.2.9\n"
          "interface GigabitEthernet2\n ip ospf cost 20\n description to-r2\n"
          "interface GigabitEthernet3\n description to-r1 (test)\n"
          " ip address 192.0.2.1 255.255.255.0\n")


def _edit(text, old, new):
    assert old in text
    return text.replace(old, new)


@pytest.fixture
def no_history(monkeypatch):
    monkeypatch.setattr("modules.nsot.repo.golden_history", lambda repo, host, limit=50: [])


class TestTheRule:
    def test_equal_diffs_are_one_with_the_line_saying_so(self, no_history):
        edited = _edit(DEVICE, "description to-r1 (test)", "description core uplink to r1")
        d = intent_edit.diffs("/nowhere", "r3", DEVICE, edited, DEVICE)
        assert d["same"] is True and d["replaces"] is True and d["sent"] == 1
        assert [(r["kind"], r["text"]) for r in d["edit_rows"]] == [
            ("head", "interface GigabitEthernet3"), ("del", "description to-r1 (test)"),
            ("add", "description core uplink to r1")]
        assert d["not_from"] == [] and d["not_removed"] == []

    def test_a_pending_line_makes_them_differ_and_is_not_from_this_edit(self, no_history):
        committed = DEVICE + "logging host 192.0.2.50\n"      # intent the device lacks
        edited = _edit(committed, "description to-r1 (test)", "description core uplink to r1")
        d = intent_edit.diffs("/nowhere", "r3", committed, edited, DEVICE)
        assert d["same"] is False and d["from_edit"] == 1 and d["sent"] == 2
        assert [n["line"] for n in d["not_from"]] == ["logging host 192.0.2.50"]
        assert d["not_from"][0]["words"] == "already pending", "no history: it cannot say"

    def test_a_deleted_line_a_deploy_keeps_is_named(self, no_history):
        edited = _edit(DEVICE, " ip ospf cost 20\n", "")
        d = intent_edit.diffs("/nowhere", "r3", DEVICE, edited, DEVICE)
        assert d["same"] is False and d["sent"] == 0
        assert [(r["kind"], r["text"]) for r in d["not_removed"]] == [
            ("head", "interface GigabitEthernet2"), ("keep", "ip ospf cost 20")]

    @pytest.mark.parametrize("old, new", [
        (" ip address 192.0.2.1 255.255.255.0\n",
         " ip address 192.0.2.1 255.255.255.0\n ip address 192.0.2.65 255.255.255.192 secondary\n"),
        ("ntp server 192.0.2.9\n", "ntp server 192.0.2.10\n"),
    ])
    def test_a_line_not_known_to_be_one_setting_is_never_read_as_replaced(self, no_history,
                                                                          old, new):
        """The safe reading: an ntp server or a secondary address is ADDED beside the old line,
        so the old one stays and both diffs are drawn."""
        edited = _edit(DEVICE, old, new)
        d = intent_edit.diffs("/nowhere", "r3", DEVICE, edited, DEVICE)
        if "ntp" in old:
            assert d["same"] is False and any(r["text"] == "ntp server 192.0.2.9"
                                              for r in d["not_removed"])
        else:
            assert d["same"] is True, "a secondary address is an addition, nothing deleted"

    def test_one_setting_keys(self):
        assert intent_edit._setting("description core uplink") == "description"
        assert intent_edit._setting("ip ospf cost 10") == "ip ospf cost"
        assert intent_edit._setting("ip address 192.0.2.1 255.255.255.0") == "ip address"
        assert intent_edit._setting("ip address 192.0.2.1 255.255.255.0 secondary") == ""
        assert intent_edit._setting("ntp server 192.0.2.9") == ""


def _git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          env=env, check=True).stdout.strip()


class TestWhereEachCameFrom:
    """On a real git history of r3's goldens: the first golden held `logging host 192.0.2.50`,
    the second (newest) lacks it."""

    @pytest.fixture
    def repo(self, tmp_path):
        repo = str(tmp_path)
        _git(repo, "init", "-q")
        os.makedirs(os.path.join(repo, "golden"))
        path = os.path.join(repo, "golden", "r3.cfg")
        for body in (DEVICE + "logging host 192.0.2.50\n", DEVICE):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            _git(repo, "add", "golden/r3.cfg")
            _git(repo, "commit", "-q", "-m", "golden: r3")
        intent_edit._GOLDEN_LINES.clear()
        return repo

    def test_a_line_an_earlier_golden_held_was_changed_on_the_device(self, repo):
        first = _git(repo, "rev-list", "--max-parents=0", "HEAD")
        got = intent_edit.where_from(repo, "r3", [("(global)", "logging host 192.0.2.50")])
        label = got["labels"][("(global)", "logging host 192.0.2.50")]
        assert label["words"] == "on r3 until its golden of" and label["sha"] == first
        assert label["then"] == "gone since: changed on the device"
        assert got["golden"]["sha"] == _git(repo, "rev-parse", "HEAD") and got["read"] == 2

    def test_the_newest_golden_holding_it_names_that_golden(self, repo):
        """Compared against the RUNNING config (no golden captured since), a line the newest
        golden holds and the device lost reads as on the device until that golden."""
        got = intent_edit.where_from(repo, "r3", [("interface GigabitEthernet2",
                                                   "ip ospf cost 20")])
        label = got["labels"][("interface GigabitEthernet2", "ip ospf cost 20")]
        assert label["sha"] == _git(repo, "rev-parse", "HEAD"), label

    def test_a_line_no_golden_held_is_not_yet_deployed(self, repo):
        got = intent_edit.where_from(repo, "r3", [("(global)", "snmp-server location lab")])
        assert got["labels"][("(global)", "snmp-server location lab")]["words"] == \
            "never on r3: not yet deployed"

    def test_a_history_that_cannot_be_read_says_already_pending(self, tmp_path):
        got = intent_edit.where_from(str(tmp_path), "r3", [("(global)", "x")])
        assert got["labels"][("(global)", "x")]["words"] == "already pending"


class TestTheCard:
    def _desc_edit(self, ed):  # noqa: F811
        text = intent_edit.open_doc("lab", "s4")["yaml"]
        return _edit(text, "description: uplink", "description: core uplink to r1")

    def test_differing_diffs_draw_both_and_label_the_pending_line(self, ed):  # noqa: F811
        _r, html = _post(ed, "/v2/device/s4/intent/check", yaml=self._desc_edit(ed))
        assert "What your edit changes in s4's intent" in html
        assert "What a deploy would send to s4, after this commit" in html
        assert "From this edit: 1 line" in html and "not from this edit" in html
        assert "some-construct nobody modelled" in html and "not yet deployed" in html
        first = html.split('class="ie-diff')[1].split("</div></div>")[0]
        assert re.findall(r'class="dr dr-(\w+)"', first) == ["head", "del", "add"]

    def test_equal_diffs_draw_one(self, ed, monkeypatch):  # noqa: F811
        monkeypatch.setattr(intent_edit, "diffs", lambda *a: {
            "same": True, "replaces": True, "sent": 1, "golden": None,
            "edit_rows": [{"kind": "head", "text": "interface Gi3"},
                          {"kind": "del", "text": "description a"},
                          {"kind": "add", "text": "description b"}],
            "edit_changes": True, "not_removed": [], "from_edit_rows": [], "from_edit": 1,
            "not_from": [], "masked": 0})
        _r, html = _post(ed, "/v2/device/s4/intent/check", yaml=self._desc_edit(ed))
        assert "and what a deploy would send" in html and "the same" in html
        assert "A deploy would send exactly this change: 1 line, merge-only" in html
        assert html.count('class="ie-diff') == 1 and "From this edit" not in html


def test_a_real_browser_draws_a_three_line_diff_as_three_lines(ed):  # noqa: F811
    """The approval's condition: the 3-line diff (a section, the removed line, the added one)
    is three rows, each one line tall, one under another."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    text = intent_edit.open_doc("lab", "s4")["yaml"]
    _r, card = _post(ed, "/v2/device/s4/intent/check",
                     yaml=_edit(text, "description: uplink", "description: core uplink to r1"))
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            for width in (1280, 500):
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": width, "height": 1000})
                b.go(srv.url("/v2/help/about"))
                b.wait_for("return !!document.querySelector('main')", 10)
                got = b.js(
                    "var m=document.createElement('div'); m.className='ie-split';"
                    "m.innerHTML='<div></div><div>'+arguments[0]+'</div>';"
                    "document.querySelector('main').appendChild(m);"
                    "var d=m.querySelector('.ie-diff'), rows=d.querySelectorAll('.dr');"
                    "var lh=parseFloat(getComputedStyle(rows[0]).lineHeight);"
                    "return [rows.length, lh, Array.from(rows).map(function(r){"
                    "var b=r.getBoundingClientRect(); return [Math.round(b.top), b.height,"
                    " r.textContent]; })];", card)
                count, line_height, rows = got
                assert count == 3, (width, rows)
                assert all(h <= line_height * 1.5 for _t, h, _x in rows), (width, line_height,
                                                                         rows)
                tops = [t for t, _h, _x in rows]
                assert tops == sorted(tops) and len(set(tops)) == 3, (width, rows)
                assert [x for _t, _h, x in rows] == [
                    "interface GigabitEthernet0/1", "-description uplink",
                    "+description core uplink to r1"], rows
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
