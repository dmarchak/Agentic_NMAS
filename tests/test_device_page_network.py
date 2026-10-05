"""C494 (the operator, 2026-10-05): the v2 device page takes its network from `?list=`, never
only the active list. `/v2/device/tw-ztp-a?list=throwaway` answered "no device named
'tw-ztp-a' in the list 'Default'", so opening a throwaway device meant switching the active
list, which pauses every other network's scheduled work (C491).

On two real networks in the suite's store, written by the real list writer: `Twin` holds
tw-a, the active list does not.

- `?list=Twin` opens tw-a's page, and every device URL the page draws (tabs, the Actions menu's
  rows, the intent editor) carries `list=Twin`, so a click resolves the device where the page
  found it, whichever network is active by then;
- with no `?list=`, a name in exactly one other network is said as such, with the link;
- a confirm whose card names one network, sent from a page of another, does nothing and names
  both;
- a network nobody has is refused, naming it.
"""

import re

import pytest

ROWS = [{"hostname": "tw-a", "ip": "192.0.2.61", "platform": "cisco_iosxe",
         "device_type": "cisco_xe", "role": "router", "username": "u", "password": "enc-a",
         "secret": "enc-b"}]


@pytest.fixture
def twin(tmp_path, monkeypatch):
    """A store of its own (the registry and the lists folder), Default active and empty, then
    `Twin` made by the real list writer and given tw-a by the real CSV writer."""
    import json

    import app as A
    from modules import config, device
    from modules.nsot import listref

    reg = tmp_path / "device_lists.json"
    reg.write_text(json.dumps({"current_list": "Default", "lists": {"Default": "default"}}))
    for mod in (config, device):
        monkeypatch.setattr(mod, "DEVICE_LISTS_CONFIG", str(reg))
        monkeypatch.setattr(mod, "LISTS_DIR", str(tmp_path / "lists"))
    device.write_devices_csv([], config.get_list_data_dir("Default") + "/devices.csv")
    ok, msg = device.create_device_list("Twin")
    assert ok, msg
    device.write_devices_csv([dict(r) for r in ROWS], listref.resolve("Twin").csv_path)
    assert listref.active().name == "Default", "Twin is NOT the active list"
    yield {"client": A.app.test_client(), "active": "Default"}


def _get(t, url):
    r = t["client"].get(url)
    import html as _h
    return r, _h.unescape(r.get_data(as_text=True))


class TestTheNetworkComesFromTheAddress:
    def test_the_named_network_opens_its_device(self, twin):
        r, html = _get(twin, "/v2/device/tw-a?list=Twin")
        assert r.status_code == 200, html[:400]
        assert "tw-a" in html and "no device named" not in html

    def test_every_device_url_the_page_draws_carries_it(self, twin):
        _r, html = _get(twin, "/v2/device/tw-a?list=Twin")
        urls = re.findall(r'(?:href|hx-get|hx-post|data-panel-src)="(/v2/device/tw-a[^"]*)"', html)
        assert len(urls) >= 10, urls            # tabs, menu rows, their no-script hrefs
        missing = [u for u in urls if "list=Twin" not in u]
        assert not missing, missing

    def test_a_tab_fragment_and_the_editor_resolve_in_it(self, twin):
        for path in ("/v2/device/tw-a/overview?list=Twin", "/v2/device/tw-a/intent?list=Twin"):
            r, html = _get(twin, path)
            assert r.status_code == 200, (path, html[:300])

    def test_without_a_network_the_other_one_is_named_with_its_link(self, twin):
        r, html = _get(twin, "/v2/device/tw-a")
        assert r.status_code == 404
        assert "tw-a is in Twin." in html
        assert 'href="/v2/device/tw-a?list=Twin"' in html

    def test_a_named_network_without_it_names_no_other(self, twin):
        r, html = _get(twin, f"/v2/device/tw-a?list={twin['active']}")
        assert r.status_code == 404 and "is in Twin" not in html
        assert f"in the list {twin['active']!r}" in html

    def test_a_network_nobody_has_is_refused_naming_it(self, twin):
        r = twin["client"].get("/v2/device/tw-a?list=Nowhere")
        assert r.status_code == 404 and "Nowhere" in r.get_data(as_text=True)


class TestAConfirmCarriesItsNetwork:
    def test_a_confirm_from_a_page_of_another_network_does_nothing(self, twin):
        r = twin["client"].post(f"/v2/device/tw-a/capture/start?list={twin['active']}",
                                data={"list": "Twin"})
        import html as _h
        html = _h.unescape(r.get_data(as_text=True))
        assert r.status_code == 409
        assert "'Twin'" in html and repr(twin["active"]) in html
        assert "preview again" in html
