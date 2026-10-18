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


def _two_versions(prof, monkeypatch):
    """r1 joins the lab holding SNMP without `snmp ifmib ifindex persist` (test_profile_apply's
    `_add_r1`), and the card's own links name the network, so "Lab" is a network here."""
    from tests.test_profile_apply import _add_r1

    _add_r1(prof, monkeypatch, ifindex=False)
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: str(name) == "Lab")


def _versions(prof):
    """{devices: version id} of the SNMP section, from the proposal itself (the expectation by
    a path independent of the card)."""
    from modules.nsot import profile_propose as pp

    (snmp,) = [s for s in pp.propose("Lab")["sections"] if s["section"] == "snmp"]
    return {tuple(v["devices"]): v["id"] for v in snmp.get("variants") or []}


def _snmp_row(html):
    m = re.search(r'<tr data-section="snmp">(.*?)</tr>', html, re.S)
    assert m, html[html.find("What changes"):][:1500]
    return m.group(1)


def _words(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


class TestChoosingAVersion:
    """C1269: today's page (`/templatize/profile`, nmas_profile.js) let a PERSON choose between
    the versions of a section's shared fields the devices hold (the operator, 2026-09-30: the
    tool never picks); v2's Propose card did not ("choosing between them is not on v2 yet").
    On v2 the card offers one control per version, previews the choice (which devices change
    and how), carries it into the confirm, whose hash is bound to it, and the commit records
    it as today's route did. r1 is r2's configuration without `snmp ifmib ifindex persist`."""

    def test_each_version_is_offered_and_none_is_picked_by_the_tool(self, prof, monkeypatch):
        _two_versions(prof, monkeypatch)
        versions = _versions(prof)
        assert sorted(versions) == [("r1",), ("r2",)], versions
        r, html = _get(prof, "/v2/monitoring/profile/propose?list=Lab")
        assert r.status_code == 200
        row = _snmp_row(html)
        assert "not on v2 yet" not in html
        assert ">not proposed<" in row and "choose a version" in row, _words(row)
        for devices, vid in versions.items():
            assert (f'hx-get="/v2/monitoring/profile/propose?list=Lab&choose=snmp:{vid}"'
                    in row), row
            assert f"Use the version held by {', '.join(devices)}" in _words(row), _words(row)
        assert 'name="choose"' not in html, "nothing chosen: the confirm carries no choice"

    def test_the_chosen_version_is_previewed_with_who_changes_and_how(self, prof, monkeypatch):
        _two_versions(prof, monkeypatch)
        vid = _versions(prof)[("r2",)]
        _r, plain = _get(prof, "/v2/monitoring/profile/propose?list=Lab")
        r, html = _get(prof, f"/v2/monitoring/profile/propose?list=Lab&choose=snmp:{vid}")
        assert r.status_code == 200
        said = _words(_snmp_row(html))
        assert f"You chose the version held by r2 ({vid})" in said, said
        assert "r1 gains: snmp ifmib ifindex persist" in said, said
        assert _hidden(html, "choose") == f"snmp:{vid}"
        assert _hidden(html, "hash") and _hidden(html, "hash") != _hidden(plain, "hash"), \
            "the choice is in the hash"

    def test_the_choice_is_confirmed_and_recorded(self, prof, monkeypatch):
        import subprocess

        from modules.nsot import profile
        _two_versions(prof, monkeypatch)
        vid = _versions(prof)[("r2",)]
        _r, card = _get(prof, f"/v2/monitoring/profile/propose?list=Lab&choose=snmp:{vid}")
        # The card's own confirm: what its form carries, the choice with it.
        r = prof["client"].post("/v2/monitoring/profile/propose", data={
            "list": "Lab", "hash": _hidden(card, "hash"), "choose": _hidden(card, "choose")})
        html = html_mod.unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and "The profile is committed" in html, _words(html)[-600:]
        subject = subprocess.run(["git", "-C", prof["repo"], "log", "-1", "--format=%s"],
                                 capture_output=True, text=True).stdout
        assert "chosen: snmp as held by r2" in subject, subject
        assert "snmp" in profile.read_committed(prof["repo"])["sections"]

    def test_the_hash_is_bound_to_the_choice(self, prof, monkeypatch):
        """The chosen preview's hash confirmed without its choice: refused, nothing
        committed, and the card drawn again."""
        from modules.nsot import profile
        _two_versions(prof, monkeypatch)
        vid = _versions(prof)[("r2",)]
        _r, card = _get(prof, f"/v2/monitoring/profile/propose?list=Lab&choose=snmp:{vid}")
        r = prof["client"].post("/v2/monitoring/profile/propose",
                                data={"list": "Lab", "hash": _hidden(card, "hash")})
        html = html_mod.unescape(r.get_data(as_text=True))
        assert r.status_code == 409, r.status_code
        assert "the proposal changed since the preview" in html
        assert "snmp" not in (profile.read_committed(prof["repo"]) or {}).get("sections", {})

    def test_a_version_the_devices_do_not_hold_is_said_and_never_applied(self, prof,
                                                                        monkeypatch):
        _two_versions(prof, monkeypatch)
        r, html = _get(prof, "/v2/monitoring/profile/propose?list=Lab&choose=snmp:0000beef")
        assert r.status_code == 200
        said = _words(html)
        assert ("Not applied: no device holds version 0000beef of SNMP now; choose one of the "
                "versions below.") in said, said
        assert ">not proposed<" in _snmp_row(html)
        assert 'name="choose"' not in html
