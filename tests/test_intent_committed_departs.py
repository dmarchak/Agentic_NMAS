"""C884 (the operator's walk W1, step 22, 2026-10-16; capture 26): after an intent edit that
only deletes a line, the "Committed to s1's intent" card was headed "What a deploy would send
now", showed `- description spare port`, said "until a deploy sends the lines beside" and made
Plan a deploy… its primary button, though a merge-only deploy sends nothing for a deletion.

On s1's real running configuration (`tests/fixtures/transcripts/s1/`, read through the tool's
own session, 2026-10-01), with the one line the walk deployed at step 18 added (Gi0/1's
` description spare port`), its intent parsed from it by the parser, committed, and the edit
committed through the real route (`/v2/device/s1/intent/commit`):

- an edit that only deletes: headed "How s1 now departs from its intent", the line drawn as
  one s1 holds, the words say a deploy sends nothing, and Remove lines (Mode B)… is the
  primary action, opening the device page's Mode B card; no Plan a deploy…;
- an edit that deletes and adds: "What a deploy would send now" draws only the line it sends,
  Plan a deploy… stays primary, and the deleted line is drawn apart with Remove lines
  (Mode B)… beside it;
- an edit that only adds (the control): as before, Plan a deploy… and no Mode B.
"""

import html as _h
import os
import re
from types import SimpleNamespace

import pytest

from modules.nsot import intent_edit
from tests.test_reload_certificate_storage import _read

SPARE = "interface GigabitEthernet0/1\n description spare port\n negotiation auto\n"


def _s1_running() -> str:
    """s1's `show running-config` as Netmiko returns it (the echo and the prompt out,
    `_read`), with Gi0/1's description the walk deployed."""
    text = _read("s1", "show running-config")
    plain = "interface GigabitEthernet0/1\n negotiation auto\n"
    assert plain in text
    return text.replace(plain, SPARE)


@pytest.fixture
def s1(tmp_path, monkeypatch):
    """A list `lab` holding s1, its golden (the capture above) and its intent parsed from it,
    both committed; the v2 routes find s1 there as the device page does."""
    import csv as _csv

    from modules.device import DEVICE_CSV_FIELDS
    from modules.nsot import hostvars, repo as _repo
    from modules.nsot.parsers import get_parser

    list_dir = tmp_path / "lab"
    repo_dir = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo_dir, "golden"), exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {"nsot_git_author_name": "NMAS",
                                                   "nsot_git_author_email": "n@l"}
                        .get(key, default))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    inventory = list_dir / "devices.csv"
    with open(inventory, "w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=DEVICE_CSV_FIELDS)
        writer.writeheader()
        writer.writerow({"hostname": "s1", "device_type": "cisco_ios", "ip": "192.0.2.21",
                         "platform": "cisco_ios", "role": "switch"})
    monkeypatch.setattr("modules.device.get_current_device_list",
                        lambda: ("lab", str(inventory)))
    _repo.init_repo(repo_dir)
    config = _s1_running()
    _repo.save_golden("lab", [_repo.GoldenItem("s1", config, "192.0.2.21")],
                      source="test", actor="test", allow_new=True)
    document = get_parser("cisco_ios").parse(config)
    document["hostname"] = "s1"
    hostvars.write_committed(repo_dir, document)
    _repo.save_host_vars("lab", ["s1"], actor="test", message="host_vars: s1 parsed", source="test")
    # Its template in the library and approved against s1, as the walk's was: a removal is
    # made as part of a deploy, and the deploy card builds no program from an unapproved one.
    from modules.nsot import approval, templates_repo
    from tests.test_template_approval import _commit_approvals
    templates_repo.seed_templates(repo_dir)
    approval.approve(repo_dir, "cisco_ios/base.j2", [{"device": "s1", "platform": "cisco_ios",
                                                     "running_config": config}],
                     actor="operator@example.invalid")
    _commit_approvals(repo_dir)
    dev ={"hostname": "s1", "ip": "192.0.2.21", "platform": "cisco_ios",
           "device_type": "cisco_ios"}
    monkeypatch.setattr("routes.intent_v2._device_or_404",
                        lambda name: ((SimpleNamespace(name="lab"), dev), None))
    import app as nmas
    return {"client": nmas.app.test_client(), "repo": repo_dir}


def _commit(w, old, new, summary):
    opened = intent_edit.open_doc("lab", "s1")
    assert old in opened["yaml"], old
    text = opened["yaml"].replace(old, new, 1)
    r = w["client"].post("/v2/device/s1/intent/commit",
                         data={"yaml": text, "base": opened["base"], "summary": summary})
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "Committed to s1's intent" in body, body[:600]
    return body


def _words(html: str) -> str:
    return " ".join(_h.unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _primary(html: str) -> list:
    return [(op, _h.unescape(href)) for op, href in re.findall(
        r'<a class="btn btn-primary" data-op="([^"]+)" href="([^"]+)"', html)]


def _rows(html: str) -> list:
    """Each diff row drawn in *html*: ``(kind, words)``, the sign included."""
    return [(kind, _words(text)) for kind, text in
            re.findall(r'<div class="dr dr-(\w+)">(.*?)</div>', html)]


def _block(html: str, heading: str) -> str:
    """The rows drawn under *heading*, up to the next heading or the card's foot."""
    at = html.index(heading)
    end = min([i for i in (html.find('<h3', at + 1), html.find('class="ie-ft"', at))
               if i > 0])
    return html[at:end]


def test_the_device_holds_what_its_intent_renders_before_any_edit(s1):
    """The world the walk had: s1 at its intent, so whatever the card draws is the edit's."""
    p = intent_edit.preview("lab", "s1", intent_edit.open_doc("lab", "s1")["yaml"])
    assert p["ok"] and p["diffs"]["sent"] == 0 and p["diffs"]["departs"] == 0, p["vs_device"]


class TestAnEditThatOnlyDeletes:
    def test_it_is_headed_by_the_departure_and_mode_b_is_the_action(self, s1):
        html = _commit(s1, "description: spare port", "description: ''",
                       "W1 walk: Gi0/1 back to no description")
        words = _words(html)
        assert "How s1 now departs from its intent" in words
        assert "What a deploy would send now" not in words
        assert _rows(_block(html, "How s1 now departs from its intent")) == [
            ("head", "interface GigabitEthernet0/1"), ("keep", "description spare port")]
        assert "A deploy sends nothing: it is merge-only" in words
        assert "until a deploy sends the lines beside" not in words
        assert "Remove lines (Mode B)… takes them off" in words
        assert _primary(html) == [("removal",
                                   "/v2/device/s1?tab=intent&op=deploy&focus=removal")]
        assert "Plan a deploy…" not in words

    def test_the_link_opens_the_device_page_s_mode_b_card(self, s1, monkeypatch):
        """Where the primary action goes, loaded as the link loads it (without script): the
        device page with its deploy card focused on the removal, Mode B's "Left on the
        device". (Which lines it offers is the deploy card's, tests/test_menu_clicks_and_busy.py
        `TestC403`: here its program is not built, s1's capture holding masked secrets.)"""
        html = _commit(s1, "description: spare port", "description: ''", "W1: no description")
        (_op, href), = _primary(html)
        r = s1["client"].get(href)
        page = r.get_data(as_text=True)
        assert r.status_code == 200, page[:600]
        assert "op-focus" in page and 'id="removal"' in page, page[:2000]
        removal = page[page.index('id="removal"'):]
        assert "Left on the device" in removal and "tick the lines to remove here" in removal


def test_a_line_only_the_device_holds_is_drawn_masked(s1):
    """The departure is the golden's side, verbatim: a secret in a line intent lacks is masked
    in its row (a community planted in s1's golden, not in its intent)."""
    planted = "Planted-Community-41z"
    text = intent_edit.open_doc("lab", "s1")["yaml"]
    p = intent_edit.preview("lab", "s1", text)
    capture = _s1_running().replace("\nend", f"\nsnmp-server community {planted} RW\nend")
    assert planted in capture
    d = intent_edit.diffs(s1["repo"], "s1", p["rendered"], p["rendered"], capture)
    rows = [r["text"] for r in d["departs_rows"]]
    assert any(t.startswith("snmp-server community ") for t in rows), rows
    assert planted not in repr(d["departs_rows"])


class TestAnEditThatDeletesAndAdds:
    def test_what_a_deploy_sends_and_the_removals_apart(self, s1):
        opened = intent_edit.open_doc("lab", "s1")["yaml"]
        assert opened.count("description: h1 - VLAN 10") == 1
        html = _commit(s1, "description: spare port", "description: ''", "deletes")
        # Then one that adds, on top: s1's h1 port described again.
        html = _commit(s1, "description: h1 - VLAN 10", "description: h1 - VLAN 10 users",
                       "adds")
        words = _words(html)
        sends = _rows(_block(html, "What a deploy would send now"))
        assert sends == [("head", "interface GigabitEthernet1/0"),
                         ("add", "+ description h1 - VLAN 10 users")], sends
        kept = _rows(_block(html, "What a deploy keeps: only s1 holds these"))
        assert kept == [("head", "interface GigabitEthernet0/1"),
                        ("keep", "description spare port")], (
            "only the deleted line: a one-setting line the deploy replaces is not kept", kept)
        assert [op for op, _ in _primary(html)] == ["deploy"]
        assert 'class="btn" data-op="removal" href="/v2/device/s1?tab=intent&amp;op=deploy' \
               '&amp;focus=removal"' in html or \
               'class="btn" data-op="removal" href="/v2/device/s1?tab=intent&op=deploy' \
               '&focus=removal"' in html
        assert "and keeps the lines only s1 holds until you remove them (Mode B)." in words


class TestAnEditThatOnlyAdds:
    def test_the_control_plan_a_deploy_and_no_mode_b(self, s1):
        html = _commit(s1, "description: h1 - VLAN 10", "description: h1 - VLAN 10 users",
                       "adds")
        words = _words(html)
        assert "What a deploy would send now" in words
        assert "How s1 now departs" not in words and "Remove lines (Mode B)" not in words
        assert [op for op, _ in _primary(html)] == ["deploy"]
        assert "until a deploy sends the lines beside" in words
