"""A network's inventory source on v2 (CUTOVER: the network's Settings page), through the real
app on a temporary store with four networks (tests/test_settings_v2's `networks`). NetBox's
answer is the captured device records (tests/fixtures/netbox/device_records.json, r3 and r6),
adapted by the inventory's own `adapt_devices`; only the fetch is replaced.
"""

import json
import os
import re

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDS = json.load(open(os.path.join(ROOT, "tests", "fixtures", "netbox",
                                      "device_records.json"), encoding="utf-8"))


@pytest.fixture
def netbox(monkeypatch):
    asked = []

    def fetch(filters):
        asked.append(dict(filters))
        return {"ok": True, "devices": [dict(r) for r in RECORDS.values()]}
    monkeypatch.setattr("modules.inventory.netbox_source.fetch_netbox_devices", fetch)
    refreshed = []
    monkeypatch.setattr("modules.inventory.refresh_async", lambda name: refreshed.append(name))
    return {"asked": asked, "refreshed": refreshed}


def _post(n, path, data=None):
    r = n["client"].post(path, data=data or {}, headers={"HX-Request": "true"})
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


def _card(html):
    m = re.search(r'<section class="card[^"]*" id="network-source".*?</section>', html, re.S)
    assert m, "no inventory source card"
    return re.sub(r"\s+", " ", m.group(0))


TO_NETBOX = {"source": "netbox", "filter_site": "lab", "filter_role": "", "filter_tag": "",
             "filter_status": "", "credential_list": "", "refresh_interval": "300"}


def _source_json(n, slug="branch"):
    p = n["dir"] / "lists" / slug / "source.json"
    return json.loads(p.read_text()) if p.exists() else None


class TestTheCard:
    @pytest.mark.parametrize("name", ["Default", "Branch"])
    def test_every_network_s_network_tab_draws_it(self, networks, name):
        html = networks["client"].get(f"/v2/settings/network/{name}?tab=network").get_data(as_text=True)
        card = _card(html)
        assert "Its devices are its own list on this host" in card
        assert "Preview the change" in card and "Refresh now" not in card


class TestPreview:
    def test_netbox_is_read_once_with_the_new_filters_and_nothing_written(self, networks, netbox):
        from modules.inventory.netbox_source import adapt_devices
        _r, html = _post(networks, "/v2/settings/network/Branch/source/preview", TO_NETBOX)
        card = _card(html)
        assert netbox["asked"] == [{"site": "lab", "role": "", "tag": "", "status": ""}]
        devices, skipped, _w = adapt_devices([dict(r) for r in RECORDS.values()])
        assert f"NetBox holds <strong>{len(devices)}</strong>" in card
        for d in devices:
            assert d["hostname"] in card
        assert _source_json(networks) is None, "the preview writes nothing"
        assert 'name="fingerprint"' in card and "Save the source" in card

    @pytest.mark.parametrize("change,said", [
        ({"filter_site": ""}, "needs at least one filter"),
        ({"filter_site": "lab site"}, "is not a NetBox slug"),
        ({"refresh_interval": "5"}, "it is 60 to 86400"),
        ({"credential_list": "Nowhere"}, "it is not a network with its own list here"),
        ({"source": "elsewhere"}, "is not one of: local, netbox"),
    ])
    def test_a_change_that_cannot_be_is_refused_naming_it(self, networks, netbox, change, said):
        r, html = _post(networks, "/v2/settings/network/Branch/source/preview",
                        dict(TO_NETBOX, **change))
        assert r.status_code == 409 and said in html and netbox["asked"] == []

    def test_netbox_not_answering_is_said(self, networks, monkeypatch):
        monkeypatch.setattr("modules.inventory.netbox_source.fetch_netbox_devices",
                            lambda f: {"ok": False, "error": "connection refused", "devices": []})
        _r, html = _post(networks, "/v2/settings/network/Branch/source/preview", TO_NETBOX)
        assert "NetBox could not be read with these filters: connection refused" in html


class TestApply:
    def test_the_change_is_written_refreshed_and_recorded(self, networks, netbox):
        _r, pv = _post(networks, "/v2/settings/network/Branch/source/preview", TO_NETBOX)
        fp = re.search(r'name="fingerprint" value="([0-9a-f]+)"', pv).group(1)
        r, html = _post(networks, "/v2/settings/network/Branch/source",
                        dict(TO_NETBOX, fingerprint=fp))
        assert r.status_code == 200 and "Saved:" in html, html
        saved = _source_json(networks)
        assert saved["source"] == "netbox" and saved["filters"]["site"] == "lab"
        assert "Branch" in netbox["refreshed"], "the change asked for a refresh"
        rec = [json.loads(l) for l in (networks["dir"] / "settings_record.jsonl").read_text()
               .splitlines()][-1]
        assert rec["kind"] == "inventory_source" and rec["fields"] == ["Branch", "netbox"]

    def test_a_moved_source_is_refused(self, networks, netbox):
        _r, pv = _post(networks, "/v2/settings/network/Branch/source/preview", TO_NETBOX)
        fp = re.search(r'name="fingerprint" value="([0-9a-f]+)"', pv).group(1)
        from modules.inventory.source_config import save
        save("Branch", {"source": "local", "refresh_interval": 600})
        r, html = _post(networks, "/v2/settings/network/Branch/source",
                        dict(TO_NETBOX, fingerprint=fp))
        assert r.status_code == 409 and "changed since the preview" in html
        assert _source_json(networks)["source"] == "local"


class TestRefresh:
    def test_a_local_network_is_refused(self, networks):
        r, html = _post(networks, "/v2/settings/network/Branch/source/refresh")
        assert r.status_code == 409 and "is not a NetBox-sourced list" in html

    def test_a_netbox_network_is_read_now(self, networks, monkeypatch):
        from modules.inventory.source_config import save
        save("Branch", {"source": "netbox", "filters": {"site": "lab"}})
        monkeypatch.setattr("modules.inventory.refresh_list", lambda name: {
            "ok": True, "device_count": 2, "skipped": [{"name": "r9"}], "warnings": []})
        r, html = _post(networks, "/v2/settings/network/Branch/source/refresh")
        assert r.status_code == 200 and "Read from NetBox now:</strong> 2 devices, 1 skipped" in html
