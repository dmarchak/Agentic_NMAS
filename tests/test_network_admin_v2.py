"""Creating and deleting a network on v2 (board I's pattern; networks live in Settings), through
the real app on a temporary store with four networks (tests/test_settings_v2's `networks`).

Create derives the network's folder from its name, as every reader derives it, and refuses a name
whose folder another network uses or that exists unregistered (C639). Delete previews what the
network holds, takes its name typed and the preview's fingerprint, and moves its folder aside,
never erasing it; Default is never deleted; a running operation refuses it.
"""

import json
import os
import re

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)


def _post(n, path, data=None):
    r = n["client"].post(path, data=data or {}, headers={"HX-Request": "true"})
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


def _fp(html):
    return re.search(r'name="fingerprint" value="([0-9a-f]+)"', html).group(1)


def _registry(n):
    return json.loads((n["dir"] / "device_lists.json").read_text())["lists"]


def _record(n):
    p = n["dir"] / "settings_record.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


class TestCreate:
    def test_the_scope_bar_offers_it(self, networks):
        html = networks["client"].get("/v2/settings/network/Branch").get_data(as_text=True)
        assert 'hx-get="/v2/settings/networks/new"' in html and "New network…" in html

    def test_preview_then_create(self, networks):
        _r, pv = _post(networks, "/v2/settings/networks/new/preview", {"name": "Site East"})
        assert "Create <strong>Site East</strong>" in pv and "lists/site_east" in pv
        assert "Site East" not in _registry(networks), "the preview writes nothing"
        r, html = _post(networks, "/v2/settings/networks/new",
                        {"name": "Site East", "fingerprint": _fp(pv)})
        assert r.status_code == 200 and "Created Site East" in html
        assert _registry(networks)["Site East"] == "site_east"
        assert os.path.isdir(networks["dir"] / "lists" / "site_east")
        rec = _record(networks)[-1]
        assert rec["kind"] == "network_create" and rec["fields"] == ["Site East"]

    @pytest.mark.parametrize("name,said", [
        ("branch", "A list named &#39;Branch&#39; already exists"),
        ("Lab 3", "would use the folder lists/lab_3, which &#39;Lab-3&#39; already uses"),
        ("Bad/Name", "can only contain letters"),
    ])
    def test_a_name_that_cannot_be_a_network_is_refused_naming_why(self, networks, name, said):
        _r, pv = _post(networks, "/v2/settings/networks/new/preview", {"name": name})
        assert said in pv and "Create " not in pv.split("<form", 1)[0]
        r, _html = _post(networks, "/v2/settings/networks/new", {"name": name, "fingerprint": "x"})
        assert r.status_code == 409

    def test_a_folder_on_disk_with_no_network_is_never_reused(self, networks):
        """C639: create used to name the new folder site_west_1, while every reader derives
        site_west, so the new network read the stray folder's data."""
        (networks["dir"] / "lists" / "site_west").mkdir()
        _r, pv = _post(networks, "/v2/settings/networks/new/preview", {"name": "Site West"})
        assert "the folder lists/site_west already exists and no network is registered" in pv
        from modules import device
        ok, msg = device.create_device_list("Site West")
        assert ok is False and "already exists" in msg and "Site West" not in _registry(networks)

    def test_a_tampered_fingerprint_is_refused(self, networks):
        r, html = _post(networks, "/v2/settings/networks/new",
                        {"name": "Site East", "fingerprint": "0000"})
        assert r.status_code == 409 and "out of date" in html
        assert "Site East" not in _registry(networks)


class TestDelete:
    def test_default_s_page_has_no_delete_and_a_network_s_does(self, networks):
        html = networks["client"].get("/v2/settings/network/Default?tab=network").get_data(as_text=True)
        assert 'id="network-delete"' not in html
        html = networks["client"].get("/v2/settings/network/Branch?tab=network").get_data(as_text=True)
        assert 'id="network-delete"' in html and "Delete this network…" in html

    def test_default_is_never_deleted(self, networks):
        _r, html = _post(networks, "/v2/settings/network/Default/delete/preview")
        assert "it is never deleted" in html and 'name="typed"' not in html

    def test_preview_counts_and_says_the_data_survives(self, networks):
        from modules import device
        device.write_devices_csv([{"hostname": "b1", "ip": "192.0.2.41"},
                                  {"hostname": "b2", "ip": "192.0.2.42"}],
                                 str(networks["dir"] / "lists" / "branch" / "devices.csv"))
        _r, html = _post(networks, "/v2/settings/network/Branch/delete/preview")
        assert "It holds 2 devices, 0 committed goldens and 0 commits" in html
        assert "Its data survives" in html and "lists_removed/branch-" in html

    def test_the_wrong_name_typed_deletes_nothing(self, networks):
        _r, pv = _post(networks, "/v2/settings/network/Branch/delete/preview")
        r, html = _post(networks, "/v2/settings/network/Branch/delete",
                        {"typed": "branch", "fingerprint": _fp(pv)})
        assert r.status_code == 409 and "type &#39;Branch&#39; exactly" in html
        assert "Branch" in _registry(networks)

    def test_delete_moves_the_folder_aside_and_unregisters(self, networks):
        marker = networks["dir"] / "lists" / "branch" / "keep.txt"
        marker.write_text("history")
        _r, pv = _post(networks, "/v2/settings/network/Branch/delete/preview")
        r, html = _post(networks, "/v2/settings/network/Branch/delete",
                        {"typed": "Branch", "fingerprint": _fp(pv)})
        assert r.status_code == 200 and "Branch is deleted:" in html, html
        assert "Branch" not in _registry(networks)
        assert not (networks["dir"] / "lists" / "branch").exists()
        moved = list((networks["dir"] / "lists_removed").glob("branch-*/keep.txt"))
        assert [m.read_text() for m in moved] == ["history"], "nothing was erased"
        assert "survives at lists_removed/branch-" in html
        assert _record(networks)[-1]["kind"] == "network_delete"

    def test_a_running_operation_refuses_it(self, networks, monkeypatch):
        from modules import device
        monkeypatch.setattr(device, "_list_busy", lambda name: (
            f"List '{name}' was not deleted: r1 is held by a deploy"))
        _r, pv = _post(networks, "/v2/settings/network/Branch/delete/preview")
        assert "r1 is held by a deploy" in pv and 'name="typed"' not in pv
        r, _html = _post(networks, "/v2/settings/network/Branch/delete",
                         {"typed": "Branch", "fingerprint": "x"})
        assert r.status_code == 409 and "Branch" in _registry(networks)
