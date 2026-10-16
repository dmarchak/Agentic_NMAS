"""C566, board A (signed off 2026-10-07): Monitoring › Profile and Propose on v2, end to end.

Propose was today's dialog only, so the operator was sent to today's page to commit the
management section (the rule since: no v1 steps in instructions). Now the Profile tab draws the
committed profile, section by section, with how many devices hold each (Coverage's own cells),
and Propose from the connectors previews, says which devices' templates would drop a changed
section, and commits as the person, bound to the proposal's hash.

On test_profile_apply's lab (r2's real golden and intent, r6), with syslog configured as on the
host so the management section is derived.
"""

import html as html_mod
import re

import pytest

from tests.test_profile_apply import lab  # noqa: F401 (the fixture)
from tests.test_profile_reaches_the_program import _propose_management, _stale_common


@pytest.fixture
def prof(lab, monkeypatch):  # noqa: F811
    from modules.nsot import listref
    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda *a, **k: [
        {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
         "platform": "cisco_iosxe"},
        {"hostname": "r6", "ip": "203.0.113.16", "device_type": "cisco_xe",
         "platform": "cisco_iosxe"}])
    lab["settings"].update(syslog_host="192.0.2.10", syslog_source_interface="Loopback0")
    return lab


def _get(prof, url):
    r = prof["client"].get(url)
    return r, html_mod.unescape(r.get_data(as_text=True))


def _hidden(html, name):
    m = re.search(rf'name="{name}" value="([^"]*)"', html)
    return m.group(1) if m else None


class TestThePage:
    def test_the_tab_draws_the_committed_sections(self, prof):
        _propose_management(prof)
        r, html = _get(prof, "/v2/monitoring/profile")
        assert r.status_code == 200
        assert 'aria-current="page">Profile</a>' in html
        assert re.search(r'<tr data-section="management">.*?Management sources', html, re.S)
        assert "syslog_source_interface (Loopback0)" in html
        assert 'href="/v2/monitoring/profile?propose=1"' in html

    def test_a_section_the_template_drops_reads_not_rendered(self, prof):
        _propose_management(prof)
        _stale_common(prof)
        _r, html = _get(prof, "/v2/monitoring/profile")
        row = re.search(r'<tr data-section="management">(.*?)</tr>', html, re.S).group(1)
        assert ": not rendered" in row and "Bring in the shipped version on Templates" in row


class TestPropose:
    def test_the_card_names_the_new_section_and_who_would_not_receive_it(self, prof):
        _stale_common(prof)
        r, html = _get(prof, "/v2/monitoring/profile?propose=1")
        assert r.status_code == 200
        assert "Propose the profile from the connectors" in html
        row = re.search(r'<th scope="row">Management sources[^<]*</th>(.*?)</tr>', html,
                        re.S).group(1)
        assert ">new<" in row
        assert re.search(r"2 of them would not receive (it|every change) yet:", html), html[
            html.find("On the devices"):][:500]
        assert _hidden(html, "hash")

    def test_the_card_says_what_it_read_and_each_device_it_did_not_with_why(self, prof,
                                                                             monkeypatch):
        """C869: today's page drew how many devices' intents were cross-checked and each device
        not read with why; a proposal that does not say what it skipped looks complete. r9 is
        in the inventory with no committed intent."""
        from modules.nsot import hostvars
        rows = [{"hostname": h, "ip": f"203.0.113.{n}", "device_type": "cisco_xe",
                 "platform": "cisco_iosxe"} for h, n in (("r2", 12), ("r6", 16), ("r9", 19))]
        monkeypatch.setattr("modules.nsot.restore._devices_of",
                            lambda ln: [dict(r) for r in rows])
        # The expectation, from the repository rather than from the card's code.
        assert [h for h in ("r2", "r6", "r9")
                if hostvars.read_committed(prof["repo"], h) is not None] == ["r2", "r6"]
        r, html = _get(prof, "/v2/monitoring/profile/propose")
        assert r.status_code == 200
        part = html[html.index("<h3>On the devices</h3>"):html.index("<h3>Checks</h3>")]
        said = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", part))
        assert "Cross-checked against the committed intent of 2 devices; 1 not read." in said
        assert 'class="prof-skipped"' in part, "each device not read is named"
        skipped =part[part.index('class="prof-skipped"'):part.index("</details>")]
        assert 'data-keep="prof-skipped" open><summary>' in skipped, "a few: drawn open"
        assert re.search(r"No full committed intent to read: <span class=\"mono\">r9</span>",
                         skipped), skipped

    def test_with_every_device_read_nothing_is_said_skipped(self, prof):
        """The control: r2 and r6 both carry committed intent, so nothing is skipped."""
        _r, html = _get(prof, "/v2/monitoring/profile/propose")
        part = html[html.index("<h3>On the devices</h3>"):html.index("<h3>Checks</h3>")]
        said = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", part))
        assert "Cross-checked against the committed intent of 2 devices." in said
        assert "not read" not in said and "prof-skipped" not in part

    def test_the_confirm_commits_as_the_person(self, prof):
        from modules.nsot import profile
        _r, card = _get(prof, "/v2/monitoring/profile/propose")
        r = prof["client"].post("/v2/monitoring/profile/propose",
                                data={"list": "Lab", "hash": _hidden(card, "hash")})
        html = html_mod.unescape(r.get_data(as_text=True))
        assert r.status_code == 200, html[:400]
        assert "The profile is committed" in html
        assert "management" in profile.read_committed(prof["repo"])["sections"]

    def test_a_moved_proposal_is_refused_and_drawn_again(self, prof):
        from modules.nsot import profile
        r = prof["client"].post("/v2/monitoring/profile/propose",
                                data={"list": "Lab", "hash": "0" * 16})
        html = html_mod.unescape(r.get_data(as_text=True))
        assert r.status_code == 409
        assert "the proposal changed since the preview (0000000000000000 ->" in html
        assert "Propose the profile from the connectors" in html
        assert "management" not in (profile.read_committed(prof["repo"]) or {}).get(
            "sections", {})
