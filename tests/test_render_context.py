"""The render context is the only way templates get data.

Two defects this covers:

* ``_compact_device`` carries ``local_context_data`` but not the **merged**
  ``config_context``, which is what NetBox actually renders for a device.
* Pipeline stage 1 fetched interfaces and stage 2 discarded them, reading only
  ``["device"]``, so templates never saw an interface or an IP address.
"""

import pytest

from fake_netbox import FakeNetBox
from modules.nsot import build_render_context
from modules.nsot.context import _fetch_interfaces


@pytest.fixture
def nb(monkeypatch):
    box = FakeNetBox()
    site = box.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
    device = box.seed("dcim/devices", {
        "name": "R1", "site": {"id": site["id"], "name": "Lab", "slug": "lab"},
        "role": {"name": "Router", "slug": "router"},
        "platform": {"name": "IOS-XE", "slug": "cisco-ios-xe"},
        "config_context": {"ntp_servers": ["203.0.113.123"], "snmp_ro": "ref:snmp_ro"},
        "custom_fields": {"maintenance_window": "sun-0300"},
        "primary_ip4": {"address": "203.0.113.1/24"},
    })
    for name, addr in (("GigabitEthernet1", "203.0.113.1/24"),
                       ("GigabitEthernet2", "203.0.113.5/30")):
        iface = box.seed("dcim/interfaces", {
            "name": name, "device": device["id"], "enabled": True,
            "description": f"link {name}", "mode": {"value": "access"},
            "vrf": {"name": "MGMT"},
        })
        box.seed("ipam/ip-addresses", {
            "address": addr, "family": {"value": 4}, "status": {"value": "active"},
            "assigned_object": {"id": iface["id"], "device": {"id": device["id"]}},
        })
    # An interface with no IP, to prove they are not required.
    box.seed("dcim/interfaces", {"name": "Loopback0", "device": device["id"],
                                 "enabled": True})

    from modules import netbox_client
    monkeypatch.setattr(netbox_client, "_nb_ready",
                        lambda: (True, "", box, "http://nb.invalid"))
    return box


class TestContextShape:
    def test_returns_the_documented_keys(self, nb):
        built = build_render_context("R1")
        assert built["ok"], built["error"]
        assert set(built["context"]) == {"device", "interfaces", "site", "vars", "params"}

    def test_params_are_passed_through(self, nb):
        built = build_render_context("R1", params={"area": "0"})
        assert built["context"]["params"] == {"area": "0"}

    def test_vars_is_empty_until_phase_3(self, nb):
        assert build_render_context("R1")["context"]["vars"] == {}


class TestDeviceFields:
    def test_config_context_is_present(self, nb):
        """The merged config_context, absent from _compact_device."""
        device = build_render_context("R1")["context"]["device"]
        assert device["config_context"]["ntp_servers"] == ["203.0.113.123"]

    def test_custom_fields_are_present(self, nb):
        device = build_render_context("R1")["context"]["device"]
        assert device["custom_fields"]["maintenance_window"] == "sun-0300"

    def test_compact_device_stays_lean(self):
        """_compact_device feeds AI payloads, where size matters."""
        from modules.netbox_client import _compact_device
        compact = _compact_device({"id": 1, "name": "R1",
                                   "config_context": {"a": 1},
                                   "custom_fields": {"b": 2}})
        assert "config_context" not in compact
        assert "custom_fields" not in compact


class TestInterfaces:
    def test_interfaces_are_returned(self, nb):
        interfaces = build_render_context("R1")["context"]["interfaces"]
        assert {i["name"] for i in interfaces} == {
            "GigabitEthernet1", "GigabitEthernet2", "Loopback0"}

    def test_each_interface_carries_its_ip_addresses(self, nb):
        interfaces = {i["name"]: i for i in build_render_context("R1")["context"]["interfaces"]}
        assert interfaces["GigabitEthernet1"]["ip_addresses"][0]["address"] == "203.0.113.1/24"
        assert interfaces["GigabitEthernet2"]["ip_addresses"][0]["address"] == "203.0.113.5/30"

    def test_interface_without_an_ip_has_an_empty_list(self, nb):
        interfaces = {i["name"]: i for i in build_render_context("R1")["context"]["interfaces"]}
        assert interfaces["Loopback0"]["ip_addresses"] == []

    def test_interface_metadata_survives(self, nb):
        interfaces = {i["name"]: i for i in build_render_context("R1")["context"]["interfaces"]}
        gi1 = interfaces["GigabitEthernet1"]
        assert gi1["description"] == "link GigabitEthernet1"
        assert gi1["vrf"]["name"] == "MGMT"
        assert gi1["enabled"] is True


class TestSiteAndFailure:
    def test_site_record_is_included(self, nb):
        assert build_render_context("R1")["context"]["site"]["slug"] == "lab"

    def test_unknown_device_fails_cleanly(self, nb):
        built = build_render_context("does-not-exist")
        assert built["ok"] is False
        assert "not found" in built["error"]
        # A usable empty context, so a caller can render an error page.
        assert built["context"]["interfaces"] == []

    def test_unconfigured_netbox_does_not_raise(self, monkeypatch):
        from modules import netbox_client
        monkeypatch.setattr(netbox_client, "_nb_ready",
                            lambda: (False, "NetBox not configured", None, ""))
        built = build_render_context("R1")
        assert built["ok"] is False and "not configured" in built["error"]


class TestTemplateRendering:
    """The end the whole context exists for."""

    def test_template_can_reach_interfaces_and_ips(self, nb, tmp_path):
        from modules.pipeline import _render_jinja2

        template = tmp_path / "t.j2"
        template.write_text(
            "hostname {{ device.name }}\n"
            "{% for i in interfaces %}"
            "{% for a in i.ip_addresses %}"
            "interface {{ i.name }}\n ip address {{ a.address }}\n"
            "{% endfor %}{% endfor %}"
            "ntp server {{ device.config_context.ntp_servers[0] }}\n",
            encoding="utf-8")

        context = build_render_context("R1")["context"]
        lines = _render_jinja2(str(template), {}, context["device"], context)

        assert "hostname R1" in lines
        assert " ip address 203.0.113.1/24" in lines
        assert "ntp server 203.0.113.123" in lines

    def test_netbox_alias_still_works(self, nb, tmp_path):
        """Templates written against the old signature must keep rendering."""
        from modules.pipeline import _render_jinja2

        template = tmp_path / "t.j2"
        template.write_text("hostname {{ netbox.name }}\n", encoding="utf-8")
        context = build_render_context("R1")["context"]
        assert _render_jinja2(str(template), {}, context["device"], context) == ["hostname R1"]
