"""Platform capability profiles, P2a's minimum (the SDN platform design revision 6, section 6 D;
`modules/platforms/profile.py`): each lab platform's OpenFlow `versions` and
`hello.rejects_above`, port-state reliability, and the ProCurve's measured tables.

- **Every profile is usable:** no problem `profile.problems` finds, every value sourced or
  listed unconfirmed with its reason, every source defined. Planted files show each problem is
  found (a value with no source, a source not defined, an empty range, a bad version, a table
  without an id).
- **Selection by the device's own version text:** each recorded switch's `sw_desc` (the masked
  bring-up capture) selects its entry; a version no entry covers is refused naming the family,
  the version and the ranges there are, never given a neighbouring entry.
- **The values the conformance check and the compiler read:** EOS 4.17 offers 1.0 and 1.3 and
  refuses a hello above 1.3 (C2598); OVS 3.3 refuses none (measured in the harness).
"""

import copy

import pytest

from modules.platforms import profile
from tests.fixtures.sdn import ryu_recorded as R

CAPTURE = R.RecordedRyu()
#: Each recorded switch maker and the driver Mercury knows it by.
MAKER_DRIVER = {"Arista Networks": "arista_eos", "HP": "hp_procurve",
                "Nicira, Inc.": "ovs_linux"}


@pytest.mark.parametrize("name", profile.names())
def test_every_profile_is_usable(name):
    assert profile.problems(profile.load(name)) == []


def test_the_profiles_cover_the_three_platforms_p2a_needs():
    # P2 adds Comware's, from its vendor reference, so every rendering template has one (T11).
    assert profile.names() == ["arista_eos", "aruba_os_switch", "hp_comware", "ovs"]
    for driver in MAKER_DRIVER.values():
        assert profile.for_driver(driver), driver


def test_each_recorded_switch_selects_its_entry_by_its_own_version_text():
    seen = set()
    for dpid in CAPTURE.dpids():
        desc = CAPTURE.get(f"/stats/desc/{dpid}")[str(dpid)]
        got = profile.select(MAKER_DRIVER[desc["mfr_desc"]], desc["sw_desc"])
        assert got["ok"], (desc, got)
        seen.add(got["profile"])
    assert seen == {"arista_eos", "aruba_os_switch", "ovs"}


def test_eos_417_offers_10_and_13_and_refuses_a_hello_above_13():
    got = profile.select("arista_eos", "4.17.0F (Indigo-2 OpenFlow)")
    assert profile.offered_versions(got["entry"]) == ["1.0", "1.3"]
    assert profile.rejects_above(got["entry"]) == "1.3"
    assert got["entry"]["openflow"]["port_state"]["live_reliable"] is False


def test_ovs_33_refuses_no_hello_and_the_procurve_refusal_is_unconfirmed():
    ovs = profile.select("ovs_linux", "3.3.9")["entry"]
    assert profile.rejects_above(ovs) is None
    hp = profile.select("hp_procurve", "K.16.02.0020")["entry"]
    assert "openflow.hello.rejects_above" in hp["unconfirmed"] and hp["unconfirmed_why"]


@pytest.mark.parametrize("driver, version, words", [
    ("arista_eos", "4.21.1F", "no platform profile covers Arista EOS 4.21.1F: arista_eos covers "
                              "4.17 to below 4.18"),
    ("hp_procurve", "KB.16.02.0020", "no platform profile covers HP ProCurve / ArubaOS-Switch "
                                     "KB.16.02.0020: aruba_os_switch covers K.16.02 to below "
                                     "K.16.03"),
    ("ovs_linux", "2.17.9", "no platform profile covers Open vSwitch 2.17.9"),
    ("cisco_ios", "15.1(4)M8", "no platform profile covers the driver 'cisco_ios'"),
    ("arista_eos", "unknown", "'unknown' is not a version"),
])
def test_a_version_no_entry_covers_is_refused_by_name(driver, version, words):
    got = profile.select(driver, version)
    assert not got["ok"] and got["error"].startswith(words), got


@pytest.mark.parametrize("text, want", [
    ("4.17.0F (Indigo-2 OpenFlow)", ("", (4, 17, 0))),
    ("K.16.02.0020", ("K", (16, 2, 20))),
    ("3.3.4", ("", (3, 3, 4))),
])
def test_a_version_text_is_read_as_its_train_and_numbers(text, want):
    assert profile.parse_os(text) == want


def _planted():
    return copy.deepcopy(profile.load("aruba_os_switch"))


@pytest.mark.parametrize("plant, words", [
    (lambda d: d["entries"][0]["sources"].pop("openflow.versions"),
     "entry 1: openflow.versions names no source and is not listed unconfirmed"),
    (lambda d: d["entries"][0]["sources"].__setitem__("openflow.versions", ["nowhere"]),
     "entry 1: openflow.versions cites 'nowhere', which the file does not define"),
    (lambda d: d["entries"][0]["os"].__setitem__("below", "16.01"),
     "entry 1's range is empty"),
    (lambda d: d["entries"][0]["openflow"].__setitem__("versions", ["1.3", "2.0"]),
     "entry 1's openflow.versions are from"),
    (lambda d: d["entries"][0]["openflow"]["hello"].pop("rejects_above"),
     "entry 1's openflow.hello.rejects_above is a version or null"),
    (lambda d: d["entries"][0]["openflow"]["tables"][1].pop("table_id"),
     "entry 1: openflow.tables[1]'s table_id None is not a table id"),
    (lambda d: d["entries"][0]["openflow"]["tables"][2].__setitem__("match", "every"),
     "entry 1: table 200's match is a list or 'any'"),
    (lambda d: d["entries"][0].__setitem__("unconfirmed_why", ""),
     "entry 1 lists unconfirmed values and does not say why"),
    (lambda d: d["measurements"]["c2601"].pop("evidence"),
     "measurement 'c2601' names no evidence"),
    (lambda d: d["entries"][0]["openflow"].__setitem__("bind_change_requires", "reboot"),
     "entry 1's openflow.bind_change_requires is one of agent_restart or null"),
    (lambda d: d["entries"][0]["openflow"].__setitem__("openflow_ports_require", ["stp_off"]),
     "entry 1's openflow.openflow_ports_require is a list from lldp_off"),
    (lambda d: d["entries"][0]["openflow"].__setitem__("port_numbering", "random"),
     "entry 1's openflow.port_numbering is one of"),
    (lambda d: d["entries"][0]["sources"].pop("openflow.port_numbering"),
     "entry 1: openflow.port_numbering names no source and is not listed unconfirmed"),
])
def test_each_problem_is_found_in_a_planted_profile(plant, words):
    doc = _planted()
    plant(doc)
    assert any(p.startswith(words) for p in profile.problems(doc)), profile.problems(doc)
