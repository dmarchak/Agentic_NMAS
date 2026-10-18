"""A network's inventory source on v2 (CUTOVER: the network's Settings page), through the real
app on a temporary store with four networks (tests/test_settings_v2's `networks`). NetBox's
answer is the captured device records (tests/fixtures/netbox/device_records.json, r3 and r6),
adapted by the inventory's own `adapt_devices`; only the fetch is replaced.
"""

import json
import os
import re
import time
from html import unescape as html_unescape

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


def _nb_device(nb, site, name, ip, platform="cisco-ios-xe", role="router"):
    return nb.seed("dcim/devices", {
        "name": name, "primary_ip4": {"address": f"{ip}/24"} if ip else None,
        "platform": {"slug": platform}, "role": {"slug": role},
        "site": {"id": site["id"], "slug": "lab", "name": "Lab"}, "status": {"value": "active"}})


@pytest.fixture
def nb_branch(networks, monkeypatch):
    """Branch sourced from NetBox, read through the inventory's REAL fetch, adapt and refresh
    from the shared fake (tests/fake_netbox.py), as tests/test_netbox_inventory.py's lab
    reads it: five devices, one with no primary address and one on a platform Mercury does not
    map (both skipped), one whose role NetBox does not classify (loaded with a warning); then
    one is deleted from NetBox and the network read again, so it is gone from NetBox."""
    from modules import credentials, inventory
    from modules.inventory.source_config import save
    from tests.fake_netbox import FakeNetBox

    monkeypatch.setattr(credentials, "_FILE", str(networks["dir"] / "creds.json"))
    credentials.save_profile("default", "admin", "pw", "en")
    nb = FakeNetBox()
    site = nb.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
    nb.seed("extras/custom-fields", {"name": "mercury_kind"})
    nb.seed("dcim/device-roles", {"name": "Router", "slug": "router",
                                  "custom_fields": {"mercury_kind": "router"}})
    nb.seed("dcim/device-roles", {"name": "Edge", "slug": "edge", "custom_fields": {}})
    _nb_device(nb, site, "br-r1", "192.0.2.11")
    gone = _nb_device(nb, site, "br-r2", "192.0.2.12")
    _nb_device(nb, site, "br-noaddr", None)
    _nb_device(nb, site, "br-arista", "192.0.2.14", platform="arista-eos")
    _nb_device(nb, site, "br-edge", "192.0.2.15", role="edge")
    monkeypatch.setattr("modules.netbox_client._nb_ready",
                        lambda: (True, "", nb, "http://netbox.example.invalid"))
    monkeypatch.setattr("modules.inventory.refresh_async", lambda name: None)
    save("Branch", {"source": "netbox", "filters": {"site": "lab"}})
    inventory.invalidate()
    assert inventory.refresh_list("Branch")["ok"]
    nb.delete(f"http://netbox.example.invalid/api/dcim/devices/{gone['id']}/")
    assert inventory.refresh_list("Branch")["ok"]
    yield dict(networks, nb=nb, site=site)
    inventory.invalidate()


def _source_card(n):
    r = n["client"].get("/v2/settings/network/Branch/source", headers={"HX-Request": "true"})
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _closed(html):
    """The card with every closed <details> taken out: what is drawn before anything opens."""
    return re.sub(r"<details(?![^>]*\bopen\b)[^>]*>.*?</details>", "", html, flags=re.S)


class TestWhatNetBoxLeftOut:
    """C1160: the card at rest names each device NetBox holds that is not in the inventory, with
    the inventory's own reason; each loaded with a warning; and each NetBox no longer returns,
    since when. Counts first; every group collapsed (CLAUDE.md "Built for large fleets")."""

    def test_the_counts_lead(self, nb_branch):
        card = _card(_source_card(nb_branch))
        assert "2 devices" in card, card
        assert "2 skipped" in card and "1 with a warning" in card, card
        assert "1 no longer in NetBox" in card, card

    def test_each_skipped_device_is_named_with_its_reason(self, nb_branch):
        from modules.inventory import get_status

        html = _source_card(nb_branch)
        skipped = get_status("Branch")["skipped"]
        assert {s["name"] for s in skipped} == {"br-noaddr", "br-arista"}, skipped
        for s in skipped:
            row = re.search(rf"<tr>\s*<td>{s['name']}</td>\s*<td>(.*?)</td>", html, re.S)
            assert row, f"{s['name']} is not drawn as a row"
            assert html_unescape(row.group(1)).strip() == s["reason"], row.group(1)
        assert "no primary IPv4 address" in html and "set one on the device in NetBox" in html
        assert "a platform Mercury does not map" in html

    def test_each_warning_is_named_with_its_reason(self, nb_branch):
        from modules.inventory import get_status

        html = _source_card(nb_branch)
        (w,) = get_status("Branch")["warnings"]
        assert w["name"] == "br-edge" and w["field"] == "role", w
        row = re.search(r"<tr>\s*<td>br-edge</td>\s*<td>(.*?)</td>", html, re.S)
        assert row and html_unescape(row.group(1)).strip() == w["reason"], html

    def test_each_device_gone_from_netbox_is_named_with_since_when(self, nb_branch):
        from modules.inventory import get_stale_devices

        html = _source_card(nb_branch)
        (ip, e), = get_stale_devices("Branch").items()
        assert e["hostname"] == "br-r2", e
        row = re.search(r"<tr>\s*<td>br-r2</td>\s*<td[^>]*>(.*?)</td>\s*<td>(.*?)</td>", html,
                        re.S)
        assert row and row.group(1) == ip, html
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(e["last_seen"]))
        assert f'datetime="{since}"' in row.group(2), row.group(2)
        assert "drift checks, rotation and restore refuse them by name" in html

    def test_every_group_is_collapsed(self, nb_branch):
        """Nothing is named before a group is opened: the names are one level down."""
        card = _card(_source_card(nb_branch))
        rest = _closed(card)
        for name in ("br-noaddr", "br-arista", "br-edge", "br-r2"):
            assert name in card, f"{name} is not drawn"
            assert name not in rest, f"{name} is drawn outside a closed group"

    def test_the_network_tab_draws_the_same(self, nb_branch):
        html = nb_branch["client"].get("/v2/settings/network/Branch?tab=network").get_data(
            as_text=True)
        card = _card(html)
        for name in ("br-noaddr", "br-arista", "br-edge", "br-r2"):
            assert name in card, name

    def test_a_large_fleet_is_never_one_long_list(self, nb_branch):
        """Sixty skipped devices: the counts lead, and no device name is drawn outside a
        closed group (tests/test_large_fleets.py's measure, on the card)."""
        from modules import inventory
        from tests.test_large_fleets import expanded_devices

        nb, site = nb_branch["nb"], nb_branch["site"]
        for i in range(60):
            _nb_device(nb, site, f"acc{i:04d}", None)
        assert inventory.refresh_list("Branch")["ok"]
        card = _card(_source_card(nb_branch))
        assert "62 skipped" in card, card
        assert expanded_devices("<body>" + card) == set()
        assert "acc0042" in card, "the group does not hold the devices"

    def test_the_control_a_whole_list_draws_no_group(self, networks, monkeypatch):
        """A NetBox network whose every device loaded draws its counts and no group, and a
        network on its own list draws none of this."""
        from modules import credentials, inventory
        from modules.inventory.source_config import save
        from tests.fake_netbox import FakeNetBox

        monkeypatch.setattr(credentials, "_FILE", str(networks["dir"] / "creds.json"))
        credentials.save_profile("default", "admin", "pw", "en")
        nb = FakeNetBox()
        site = nb.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
        nb.seed("extras/custom-fields", {"name": "mercury_kind"})
        nb.seed("dcim/device-roles", {"name": "Router", "slug": "router",
                                      "custom_fields": {"mercury_kind": "router"}})
        _nb_device(nb, site, "br-r1", "192.0.2.11")
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (True, "", nb, "http://netbox.example.invalid"))
        monkeypatch.setattr("modules.inventory.refresh_async", lambda name: None)
        save("Branch", {"source": "netbox", "filters": {"site": "lab"}})
        inventory.invalidate()
        try:
            assert inventory.refresh_list("Branch")["ok"]
            card = _card(_source_card(networks))
        finally:
            inventory.invalidate()
        assert "1 device, 0 skipped" in card and "<details" not in card, card
        assert "no longer in NetBox" not in card and "with a warning" not in card
        local = _card(networks["client"].get("/v2/settings/network/Default?tab=network")
                      .get_data(as_text=True))
        assert "skipped" not in local and "<details" not in local


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
