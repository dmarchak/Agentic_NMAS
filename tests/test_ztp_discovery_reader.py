"""The discovery reader (`modules/readers/ztp_discovery.py`, board L): Kea's leases in the
discovery range, as the host's Kea was captured (tests/fixtures/kea/) with the range added as the
host step adds it, and lease records from the capture with minimal edits (moved into the
discovery pools, another MAC): the lab has had no discovery lease yet.

- a lease in ciscopnp's pool is a device sending that vendor class, one in the other pool sends
  none; a lease outside the range (the lab's hosts in subnet 10) is never listed;
- the reader remembers when a device was first seen and the gaps between its requests;
- a device is asking under ten minutes after its last request, quiet after, dropped after a day;
- a MAC Kea now reserves, or an onboarding not yet verified names, is "picked", with the name;
- the announcement ignores the read's time and the ages.
"""

import json
import os

import pytest

from modules import dhcp_discovery as L
from modules.readers import ztp_discovery as Z

KEA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "kea")
ADDRS = {"enp6s19": ["10.255.0.10"]}
NOW = 1791756000                       # 2026-10-11T23:20:00Z


def _config():
    with open(os.path.join(KEA, "dhcp4-config-get.json"), encoding="utf-8") as fh:
        config = json.load(fh)[0]["arguments"]["Dhcp4"]
    config["client-classes"] = L.classes("enp6s19")
    # As Kea's config-get reports the pools the host step wrote (read on the host 2026-10-11
    # 21:17 UTC): an aligned range comes back as a prefix.
    next(s for s in config["subnet4"] if s["id"] == 255)["pools"] = [
        {"pool": "10.255.0.192/28", "client-class": "nmas-discovery-pnp", "option-data": []},
        {"pool": "10.255.0.208/28", "client-class": "nmas-discovery", "option-data": []}]
    return config


def _captured():
    with open(os.path.join(KEA, "dhcp4-lease4-get-all.json"), encoding="utf-8") as fh:
        return json.load(fh)[0]["arguments"]["leases"]


def _lease(address, mac, cltt, client_id="01:52:54:00:8a:11:08"):
    """A captured lease moved into the discovery range (the minimal edit)."""
    lease = dict(_captured()[0])
    lease.update({"ip-address": address, "hw-address": mac, "subnet-id": 255, "cltt": cltt,
                  "valid-lft": 300, "client-id": client_id, "hostname": "", "state": 0})
    return lease


PNP = "52:54:00:8a:11:08"
PLAIN = "52:54:00:3c:7e:21"


def _shape(leases, previous=None, now=NOW, pending=None, config=None):
    return Z.shape(config or _config(), leases, previous or {}, now, pending or {}, ADDRS)


class TestWhatIsListed:

    def test_the_pool_says_the_vendor_class_and_the_lab_s_hosts_are_not_listed(self):
        got = _shape(_captured() + [_lease("10.255.0.192", PNP, NOW - 20),
                                    _lease("10.255.0.208", PLAIN, NOW - 40)])
        by = {d["mac"]: d for d in got["devices"]}
        assert set(by) == {PNP, PLAIN}, "the captured leases (subnets 10 and 20) are not listed"
        assert by[PNP]["vendor"] == "ciscopnp" and by[PLAIN]["vendor"] == ""
        assert by[PNP]["state"] == by[PLAIN]["state"] == "asking"
        assert got["counts"] == {"asking": 2, "picked": 0, "quiet": 0}
        assert got["range"]["state"] == "on"

    def test_a_range_kea_runs_only_in_part_says_so(self):
        config = _config()
        config.pop("client-classes")
        got = _shape([], config=config)
        assert got["range"]["state"] == "partial"
        assert got["range"]["problem"] == "Kea runs 0 of the 2 discovery classes as written " \
                                          "and 2 of the 2 pools"


class TestTheMemory:

    def test_first_seen_is_kept_and_each_new_request_adds_a_gap(self):
        one = _shape([_lease("10.255.0.192", PNP, NOW - 300)], now=NOW - 290)
        two = _shape([_lease("10.255.0.192", PNP, NOW - 150)], previous=one, now=NOW - 140)
        three = _shape([_lease("10.255.0.192", PNP, NOW)], previous=two, now=NOW + 5)
        d = three["devices"][0]
        assert d["first_seen_ts"] == NOW - 300
        assert d["gaps"] == [150, 150]
        same = _shape([_lease("10.255.0.192", PNP, NOW)], previous=three, now=NOW + 35)
        assert same["devices"][0]["gaps"] == [150, 150], "an unchanged lease is no new request"

    @pytest.mark.parametrize("age, state", [(599, "asking"), (601, "quiet")])
    def test_asking_under_ten_minutes_then_quiet(self, age, state):
        assert _shape([_lease("10.255.0.192", PNP, NOW - age)])["devices"][0]["state"] == state

    def test_a_device_kea_no_longer_leases_stays_quiet_for_a_day_then_drops(self):
        seen = _shape([_lease("10.255.0.192", PNP, NOW)])
        later = _shape([], previous=seen, now=NOW + 3600)
        assert [d["state"] for d in later["devices"]] == ["quiet"]
        assert _shape([], previous=later, now=NOW + 86401)["devices"] == []


class TestPicked:

    def test_a_mac_kea_now_reserves_is_picked_and_named(self):
        config = _config()
        ztp = next(s for s in config["subnet4"] if s["id"] == 255)
        ztp["reservations"] = [{"hw-address": PNP, "ip-address": "10.255.0.18"}]
        got = _shape([_lease("10.255.0.192", PNP, NOW - 20)], config=config,
                     pending={PNP: ("r8", "2026-10-11T23:19:00Z")})
        d = got["devices"][0]
        assert (d["state"], d["reserved"], d["picked_as"]) == ("picked", "10.255.0.18", "r8")
        assert got["not_listed"] == {"reserved": 1, "pending": 1}


def test_the_announcement_ignores_the_read_s_time_and_the_ages():
    a = dict(_shape([_lease("10.255.0.192", PNP, NOW)]), read_at="x")
    b = dict(_shape([_lease("10.255.0.192", PNP, NOW)], now=NOW + 30), read_at="y")
    assert not Z.changed(a, b)
    c = _shape([_lease("10.255.0.192", PNP, NOW + 20)], previous=a, now=NOW + 30)
    assert Z.changed(a, c)
