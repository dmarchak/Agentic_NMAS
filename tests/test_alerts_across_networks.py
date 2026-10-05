"""P.8 step 6: an alert's device is resolved against EVERY network, never the active one alone.

Needs attention named each Grafana alert's device from the inventory of the ACTIVE list. With two
lists, an alert for the other network's device read "NOT in the inventory (a rule left behind by
a device that left)": a false claim, latent while one list exists (NSOT_P8_DESIGN, section 4).
Two networks may also reuse an address; an alert found by that address names both and decides
neither, rather than pick one.
"""

import pytest

from modules import attention as A
from modules import device

LISTS = {"default": [{"hostname": "r1", "ip": "192.0.2.1"},
                     {"hostname": "r2", "ip": "192.0.2.2"}],
         "branch": [{"hostname": "br-r1", "ip": "192.0.2.51"},
                    {"hostname": "br-r2", "ip": "192.0.2.2"}]}


@pytest.fixture
def two_networks(monkeypatch):
    monkeypatch.setattr(device, "get_device_lists",
                        lambda: [{"name": "Default", "filename": "default"},
                                 {"name": "Branch", "filename": "branch"}])
    monkeypatch.setattr(device, "load_saved_devices",
                        lambda path=None: list(LISTS["default" if path is None
                                                     else path.split("/")[-2]]))
    # The ACTIVE list is Default: the defect resolved everything against it alone.
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Default")


def _member(**inst):
    inv, why = A._inventory()
    assert not why, why
    return A._member({"onset": None, "onset_basis": "not recorded", **inst}, inv)


@pytest.mark.usefixtures("two_networks")
class TestAnAlertOfAnotherNetwork:
    def test_a_labelled_device_of_the_other_network_is_found(self):
        m = _member(device="br-r1", device_from="label")
        assert "NOT in the inventory" not in m["device_note"], m

    def test_a_device_in_no_network_is_still_said_to_be_left_behind(self):
        """The control: the note still fires for a name no network holds."""
        m = _member(device="gone-9", device_from="label")
        assert "NOT in the inventory" in m["device_note"], m

    def test_an_address_of_the_other_network_names_its_device(self):
        m = _member(address="192.0.2.51", device_from="address")
        assert m["device"] == "br-r1", m

    def test_an_address_two_networks_use_decides_neither(self):
        m = _member(address="192.0.2.2", device_from="address")
        assert m["device"] is None, m
        assert "br-r2" in m["device_note"] and "r2" in m["device_note"], m
        assert "not decided" in m["device_note"], m
