"""C1600: the Kea subnet Add device adds for a relayed ZTP device's link is RESERVATIONS-ONLY,
with no pool (`ztp._link_subnet`, `dhcp_subnets._plan_add`).

The pool was the device's own address (``<address> - <address>``), so once the reservation was
removed (Abandon, Retire) Kea leased that address to whatever asked on the link next. With no
pool, the subnet answers only the clients reserved in it: the device's address is served to its
MAC and to nobody else, and to nobody at all once its reservation is gone.

"Served only to its MAC" is read from Kea's own allocation rule, written here independently of
the code under test (`_offered`): a client is offered the addresses reserved for its MAC in the
subnet, plus any address in one of the subnet's pools. It is shown able to find the old defect
(the planted pool of the device's own address serves a stranger).

On real Kea files: tests/fixtures/kea's captured main files after the subnet move (the `moved`
fixture of tests/test_dhcp_subnets.py), and test_ztp_relayed's relayed-link fixture. ZTP is
IPv4 only (C1245): the IPv6 case is the refusal by name. Documentation addresses throughout."""

import ipaddress
import json
import os

import pytest

from modules import dhcp_subnets as S
from modules.nsot import ztp, ztp_relayed
from tests.test_dhcp_subnets import _ok_test, moved  # noqa: F401 - the fixture
from tests.test_ztp_relayed import (ADDRS, LINK, LINK_DEVICE, LINK_MAC, LINK_RELAY, SERVER,
                                    FakeKea, _link_facts, _seams, kea_files)  # noqa: F401

OTHER_MAC = "aa:bb:cc:00:04:99"
VALUES = {"op": "add", "family": "IPv4", "prefix": LINK, "ztp": "1"}
MADE = {"device": "r7", "list": "Lab"}


@pytest.fixture(autouse=True)
def _fresh_probe_cache():
    ztp_relayed._probe_cache.clear()
    yield
    ztp_relayed._probe_cache.clear()


def _offered(subnet: dict, mac: str) -> set:
    """Kea's allocation, independent of the code under test: the addresses a DHCPv4 client with
    *mac* can be given in *subnet* (its reservations for that MAC, and every address of every
    pool)."""
    out = {r["ip-address"] for r in subnet.get("reservations") or []
           if isinstance(r, dict) and r.get("hw-address", "").lower() == mac.lower()}
    for p in subnet.get("pools") or []:
        a, _, b = p["pool"].partition("-")
        lo, hi = ipaddress.ip_address(a.strip()), ipaddress.ip_address(b.strip())
        out |= {str(ipaddress.ip_address(n)) for n in range(int(lo), int(hi) + 1)}
    return out


def _reservation():
    return ztp.reservation_entry(LINK_MAC, LINK_DEVICE, "r7", SERVER)


def _planned(kea_files, monkeypatch, values=VALUES):
    from modules import dhcp_reservations as D
    monkeypatch.setattr(D, "main_config", lambda ln, fam: kea_files["main"])
    kea = FakeKea({255: kea_files["direct"], 40: kea_files["relayed"]})
    return S.plan("Lab", dict(values), kea=kea, intent=_link_facts(), created_by=MADE)


def test_add_device_plans_the_link_subnet_with_no_pool(kea_files, monkeypatch):
    """`ztp.plan_check` for an address no subnet holds plans the link's subnet through the one
    writer with no pool asked for, and says so (``pool`` empty)."""
    from modules import dhcp_reservations as D
    monkeypatch.setattr(D, "main_config", lambda ln, fam: kea_files["main"])
    kea = FakeKea({255: kea_files["direct"], 40: kea_files["relayed"]})
    p = ztp.plan_check(LINK_MAC, LINK_DEVICE, kea=kea, addrs=ADDRS, get=lambda k, d="": "/f",
                       relayed=_seams(facts=_link_facts()), list_name="Lab", hostname="r7")
    assert p["ok"], p["reasons"]
    add = p["subnet_to_add"]
    assert add["values"] == VALUES, add["values"]
    assert add["pool"] == "" and add["prefix"] == LINK


def test_the_writer_builds_it_with_no_pool_and_declared_for_ztp(kea_files, monkeypatch):
    """The subnet the writer would add for those values: no ``pools`` key at all, declared for
    ZTP (relay, MAC matching, created by the onboarding), no gateway or DNS option, and nothing
    that turns Kea's serving of in-subnet reservations off."""
    p = _planned(kea_files, monkeypatch)
    assert p["ok"], p["refused"]
    after = p["after"]
    assert "pools" not in after, after
    assert after["subnet"] == LINK and after["relay"] == {"ip-addresses": [LINK_RELAY]}
    assert ztp_relayed.declared(after) and ztp_relayed.created_by(after) == MADE
    assert after.get("match-client-id") is False
    assert "option-data" not in after
    assert after.get("reservations-in-subnet", True) is not False


def test_its_address_is_served_only_to_its_mac(kea_files, monkeypatch):
    """With the device's reservation in it, the subnet offers the device's address to the
    device's MAC alone; once the reservation is removed (Abandon, Retire), to nobody."""
    p = _planned(kea_files, monkeypatch)
    assert p["ok"], p["refused"]
    after = p["after"]
    subnet = dict(after, reservations=[_reservation()])
    assert _offered(subnet, LINK_MAC) == {LINK_DEVICE}
    assert _offered(subnet, OTHER_MAC) == set()
    assert _offered(dict(after, reservations=[]), LINK_MAC) == set()
    assert _offered(dict(after, reservations=[]), OTHER_MAC) == set()


def test_the_old_pool_would_have_served_a_stranger(kea_files, monkeypatch):
    """The planted case `_offered` must find: the same Add with the pool C1600 removed (the
    device's own address) offers that address to another MAC once the reservation is gone."""
    p = _planned(kea_files, monkeypatch, dict(VALUES, pool=f"{LINK_DEVICE} - {LINK_DEVICE}"))
    assert p["ok"], p["refused"]
    assert _offered(dict(p["after"], reservations=[]), OTHER_MAC) == {LINK_DEVICE}


def test_a_subnet_not_for_ztp_still_needs_its_pool(kea_files, monkeypatch):
    """Control: only a ZTP subnet may have no pool; board C's ordinary Add without one is
    refused as before."""
    p = _planned(kea_files, monkeypatch, dict(VALUES, ztp=""))
    assert not p["ok"] and p["refused"] == "a new subnet needs its pool: first - last"


def test_an_ipv6_link_subnet_is_refused_by_name_not_for_its_pool(kea_files, monkeypatch):
    """IPv6 beside IPv4: the same pool-less ZTP Add of an IPv6 prefix is refused because ZTP is
    IPv4 only (C1245), never for the missing pool."""
    from modules import dhcp_reservations as D

    class Kea6:
        def command(self, command, service=None):
            return {"ok": True, "result": [{"arguments": {"Dhcp6": {"subnet6": []}}}]}
    monkeypatch.setattr(D, "main_config", lambda ln, fam: kea_files["main"])
    intent = {"IPv4": {}, "IPv6": {"2001:db8:4::/64": [
        {"device": "relay-b", "iface": "GigabitEthernet2", "address": "2001:db8:4::1",
         "relays": ["2001:db8::10"]}]}}
    p = S.plan("Lab", {"op": "add", "family": "IPv6", "prefix": "2001:db8:4::/64",
                       "ztp": "1"}, kea=Kea6(), file_text="[]\n", intent=intent)
    assert not p["ok"] and "IPv6" in p["refused"] and "C1245" in p["refused"], p["refused"]
    assert "pool" not in p["refused"]


def test_the_subnet_written_to_kea_s_file_has_no_pool(moved):
    """The write itself, on the captured Kea files: the confirmed Add lands in Mercury's subnet
    file and in Kea's running configuration with no pool, its reservations file fresh."""
    values = {"op": "add", "family": "IPv4", "prefix": LINK, "ztp": "1"}
    p = S.plan("Lab", values, kea=moved["kea"], intent=_link_facts(), created_by=MADE)
    assert p["ok"], p["refused"]
    got = S.apply_edit("Lab", values, p["hash"], actor="p", reason="r7's link",
                       kea=moved["kea"], run_test=_ok_test, intent=_link_facts(),
                       created_by=MADE, record=lambda l, plan, **k: {"ok": True, "commit": "c"})
    assert got["ok"], got["error"]
    with open(moved["files"]["dhcp4"], encoding="utf-8") as fh:
        written = [s for s in S.load(fh.read()) if s.get("subnet") == LINK]
    assert len(written) == 1 and "pools" not in written[0], written
    loaded = [s for s in moved["kea"].loaded["dhcp4"] if s.get("subnet") == LINK]
    assert len(loaded) == 1 and "pools" not in loaded[0] and loaded[0]["reservations"] == []
    fresh = os.path.join(os.path.dirname(moved["files"]["dhcp4"]),
                         f"reservations-{p['id']}.json")
    with open(fresh, encoding="utf-8") as fh:
        assert json.load(fh) == []
