"""NetBox device lookup must never guess.

The previous implementation tried an exact name, then fell back to a ``q=``
fuzzy search and took the first hit. Asking for "R1" could therefore return
"R10", and a template would be rendered against — or config pushed to — the
wrong device. A clear "not found" is the safe answer.
"""

import pytest

from fake_netbox import FakeNetBox
from modules.netbox_client import _resolve_device


@pytest.fixture
def nb():
    box = FakeNetBox()
    box.seed("dcim/devices", {"name": "R1"})
    box.seed("dcim/devices", {"name": "R10"})
    box.seed("dcim/devices", {"name": "R100"})
    return box


class TestExactNameFirst:
    def test_exact_name_wins(self, nb):
        assert _resolve_device(nb, "http://nb.invalid", "R1")["name"] == "R1"

    def test_each_similar_name_resolves_to_itself(self, nb):
        for name in ("R1", "R10", "R100"):
            assert _resolve_device(nb, "http://nb.invalid", name)["name"] == name

    def test_partial_name_is_not_resolved(self, nb):
        """The regression: 'R' used to fuzzy-match and return R1."""
        assert _resolve_device(nb, "http://nb.invalid", "R") is None

    def test_unknown_name_returns_none(self, nb):
        assert _resolve_device(nb, "http://nb.invalid", "does-not-exist") is None

    def test_empty_input_returns_none(self, nb):
        assert _resolve_device(nb, "http://nb.invalid", "") is None


class TestIpamLookup:
    def test_ip_resolves_via_assigned_interface(self, nb):
        device = nb.objects("dcim/devices")[0]
        iface = nb.seed("dcim/interfaces", {"name": "Gi1", "device": device["id"]})
        nb.seed("ipam/ip-addresses", {
            "address": "203.0.113.1/24",
            "assigned_object": {"id": iface["id"], "device": {"id": device["id"]}},
        })
        found = _resolve_device(nb, "http://nb.invalid", "203.0.113.1/24")
        assert found is not None and found["name"] == "R1"

    def test_bare_address_also_resolves(self, nb):
        device = nb.objects("dcim/devices")[1]
        iface = nb.seed("dcim/interfaces", {"name": "Gi1", "device": device["id"]})
        nb.seed("ipam/ip-addresses", {
            "address": "203.0.113.10/24",
            "assigned_object": {"id": iface["id"], "device": {"id": device["id"]}},
        })
        found = _resolve_device(nb, "http://nb.invalid", "203.0.113.10")
        assert found is not None and found["name"] == "R10"

    def test_unassigned_ip_returns_none(self, nb):
        nb.seed("ipam/ip-addresses", {"address": "203.0.113.50/24",
                                      "assigned_object": None})
        assert _resolve_device(nb, "http://nb.invalid", "203.0.113.50") is None


class TestErrorMessages:
    def test_not_found_names_both_strategies(self, nb, monkeypatch):
        from modules import netbox_client
        monkeypatch.setattr(netbox_client, "_nb_ready",
                            lambda: (True, "", nb, "http://nb.invalid"))
        result = netbox_client.netbox_get_device("nope")
        assert result["ok"] is False
        assert "exact name" in result["error"] and "IP address" in result["error"]

    def test_interfaces_lookup_uses_the_same_resolver(self, nb, monkeypatch):
        from modules import netbox_client
        monkeypatch.setattr(netbox_client, "_nb_ready",
                            lambda: (True, "", nb, "http://nb.invalid"))
        result = netbox_client.netbox_get_interfaces("R")
        assert result["ok"] is False, "a partial name resolved to a device"
