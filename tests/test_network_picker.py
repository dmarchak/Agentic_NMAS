"""The network picker in every v2 page's top bar (board N, approved 2026-10-05), through the real
app on a temporary store with four networks (tests/test_settings_v2's `networks`: Default the
base, Branch differing from it, Lab-3 inheriting, Remote standalone).

Two verified people are told apart at `identity.identify`, the one function the gate and the
page both ask: each one's choice moves only their own pages, a page's address wins over any
choice, and a background read takes the installation's list as before.
"""

import json
import re

import pytest

from modules import identity
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

ANA, BEN = "ana@example.invalid", "ben@example.invalid"


@pytest.fixture
def as_person(monkeypatch):
    who = {"actor": ANA}

    def identify(_request=None):
        return identity.Identity(actor=who["actor"], email=who["actor"], kind="person",
                                 verified=True, outcome="ok", peer="198.51.100.7",
                                 peer_trusted=True, header_present=True)
    monkeypatch.setattr(identity, "identify", identify)
    return who


def _get(n, path):
    r = n["client"].get(path)
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


def _choose(n, name, nxt="/v2/settings"):
    return n["client"].post("/v2/network/choose", data={"name": name, "next": nxt},
                            headers={"HX-Request": "true"})


def _shown(html):
    m = re.search(r'<details class="net net-pick menu-wrap"[^>]*>.*?<strong>(.*?)</strong>', html)
    assert m, "no network picker in the top bar"
    return m.group(1)


class TestThePicker:
    def test_every_page_s_top_bar_has_it_naming_the_network(self, networks, as_person):
        for path in ("/v2/", "/v2/devices", "/v2/history", "/v2/settings/installation"):
            _r, html = _get(networks, path)
            assert _shown(html) == "Default", path
            assert f'hx-get="/v2/network/picker?next={path}"' in html, path

    def test_it_lists_every_network_with_its_mode(self, networks, as_person):
        _r, html = _get(networks, "/v2/network/picker?next=/v2/devices")
        rows = re.findall(r'<span class="grow">(.*?)</span><span class="muted small">(.*?)</span>', html)
        assert dict(rows) == {"Default": "the base", "Branch": "differs from Default",
                              "Lab-3": "inherits", "Remote": "standalone"}
        assert [n for n, _m in rows] == ["Branch", "Default", "Lab-3", "Remote"]
        assert "changes no one else's pages" in html

    def test_search_narrows_the_list(self, networks, as_person):
        _r, html = _get(networks, "/v2/network/picker/items?q=re&next=/v2/")
        assert re.findall(r'<span class="grow">(.*?)</span>', html) == ["Remote"]
        _r, html = _get(networks, "/v2/network/picker/items?q=zzz&next=/v2/")
        assert "No network's name holds that." in html


class TestChoosing:
    def test_it_opens_the_same_kind_of_page_for_that_network(self, networks, as_person):
        r = _choose(networks, "Branch", "/v2/history?tab=commits")
        assert r.status_code == 204 and r.headers["HX-Redirect"] == "/v2/history?list=Branch"
        r = _choose(networks, "Branch", "/v2/device/r1")
        assert r.headers["HX-Redirect"] == "/v2/devices?list=Branch"
        for bad in ("https://example.invalid/x", "//example.invalid/x", "/settings"):
            assert _choose(networks, "Branch", bad).headers["HX-Redirect"] == "/v2/?list=Branch"

    def test_the_choice_is_the_person_s_alone(self, networks, as_person):
        assert _choose(networks, "Remote").status_code == 204
        _r, html = _get(networks, "/v2/devices")
        assert _shown(html) == "Remote"
        as_person["actor"] = BEN
        _r, html = _get(networks, "/v2/devices")
        assert _shown(html) == "Default", "another person's pages did not move"
        stored = json.loads((networks["dir"] / "network_choices.json").read_text())
        assert stored[ANA]["current"] == "Remote" and BEN not in stored

    def test_recent_ones_come_first(self, networks, as_person):
        _choose(networks, "Remote")
        _choose(networks, "Lab-3")
        _r, html = _get(networks, "/v2/network/picker?next=/v2/")
        names = re.findall(r'<span class="grow">(.*?)</span>', html)
        assert names == ["Lab-3", "Remote", "Branch", "Default"]
        assert "recent · inherits" in html

    def test_the_address_wins_over_the_choice(self, networks, as_person):
        _choose(networks, "Remote")
        _r, html = _get(networks, "/v2/devices?list=Branch")
        assert _shown(html) == "Branch"

    def test_a_background_read_takes_the_installation_s_list(self, networks, as_person):
        from modules.nsot import listref

        _choose(networks, "Remote")
        assert listref.active().name == "Default"

    def test_an_unknown_network_is_refused_its_name_escaped(self, networks, as_person):
        r = _choose(networks, "No<b>where</b>")
        body = r.get_data(as_text=True)
        assert r.status_code == 404 and "<b>" not in body and "nothing was chosen" in body

    def test_an_unreadable_store_refuses_a_choice_and_reads_the_installation_s(self, networks,
                                                                              as_person):
        (networks["dir"] / "network_choices.json").write_text("{not json")
        r = _choose(networks, "Remote")
        assert r.status_code == 409 and "cannot be read" in r.get_data(as_text=True)
        assert (networks["dir"] / "network_choices.json").read_text() == "{not json"
        _r, html = _get(networks, "/v2/devices")
        assert _shown(html) == "Default"
