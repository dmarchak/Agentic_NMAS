"""Board L's discovery range (`modules/dhcp_discovery.py`, `scripts/nmas-kea-discovery-range`), on
the host's Kea as captured 2026-10-11 (tests/fixtures/kea/) and moved by step 5.

- every discovery class is CONFINED to the ZTP subnet's own clients: Kea's classes are global and
  a class's lease time beats every subnet's (measured on a throwaway kea-dhcp4 2.4.1,
  2026-10-11: an unreserved client in a 365-day subnet was offered 300 s by an unconfined
  class; confined, it kept 365 days and the ZTP segment's unknown device got 300 s);
- Kea's main file gains the two classes before its subnet key and nothing else; a file with
  classes of its own is refused;
- the range is the highest free block of 32 (nothing reserved, leased, pooled, in intent, or
  this host), never one holding the broadcast address; a range asked for and not free is
  refused naming what holds it;
- the pools go through board C's one write path (tested, reloaded, read back as exactly the ZTP
  subnet changed, recorded), and the Update page's check then reads done;
- the host step's before/after accepts only the two classes and the two pools.
"""

import json
import os
import re

import pytest

from modules import dhcp_discovery as L
from modules import dhcp_subnets as S
from tests.test_dhcp_subnets import KEA, _ok_test, _strip, moved  # noqa: F401 (the fixture)

ADDRS = {"enp6s19": ["10.255.0.10"], "lo": ["127.0.0.1"]}


def _config():
    with open(os.path.join(KEA, "dhcp4-config-get.json"), encoding="utf-8") as fh:
        return json.load(fh)[0]["arguments"]["Dhcp4"]


def _leases():
    with open(os.path.join(KEA, "dhcp4-lease4-get-all.json"), encoding="utf-8") as fh:
        return json.load(fh)[0]["arguments"]["leases"]


def _ztp(config):
    return next(s for s in config["subnet4"] if s["id"] == 255)


class TestTheClassesAreConfined:

    def test_each_class_is_the_ztp_subnet_s_own_unreserved_direct_clients(self):
        for c in L.classes("enp6s19"):
            assert c["test"].startswith("not member('KNOWN') and pkt4.giaddr == 0.0.0.0 and "
                                        "pkt.iface == 'enp6s19'"), c
            assert c["valid-lifetime"] == 300
        assert [c["name"] for c in L.classes("enp6s19")] == ["nmas-discovery-pnp",
                                                            "nmas-discovery"]
        assert "substring(option[60].hex,0,8) == 'ciscopnp'" in L.classes("enp6s19")[0]["test"]

    def test_the_segment_is_ztp_s_own_rule(self):
        seg = L.segment(_config(), ADDRS)
        assert seg == {"id": 255, "prefix": "10.255.0.0/24", "iface": "enp6s19",
                       "address": "10.255.0.10"}

    @pytest.mark.parametrize("addrs, words", [
        ({"lo": ["127.0.0.1"]}, "0 subnets are ZTP's"),
        ({"enp6s19": ["10.255.0.10", "10.10.10.9"]}, "2 subnets are ZTP's"),
    ])
    def test_not_exactly_one_ztp_subnet_is_refused(self, addrs, words):
        with pytest.raises(L.Refused, match=words):
            L.segment(_config(), addrs)

    def test_an_interface_name_an_expression_cannot_carry_is_refused(self):
        with pytest.raises(L.Refused):
            L.confined("eth0' or 'a' == 'a")


class TestKeaSMainFile:

    def test_the_classes_go_before_the_subnet_key_and_nothing_else_moves(self, moved):
        main = moved["mains"]["IPv4"]
        text = open(main, encoding="utf-8").read()
        c = L.classes_plan(text, main, _config(), "enp6s19")
        assert c["state"] == "add", c
        cand = c["candidate"]
        assert json.loads(_strip(cand))["Dhcp4"]["client-classes"] == L.classes("enp6s19")
        assert cand.index('"client-classes"') < cand.index('"subnet4"')
        at = cand.index('"client-classes"')
        start = cand.rfind("\n", 0, at) + 1
        end = cand.index("\n", cand.index("],\n", at)) + 1
        assert cand[:start] + cand[end:] == text, "nothing else in Kea's file moves"

    def test_done_when_kea_runs_exactly_the_two(self, moved):
        main = moved["mains"]["IPv4"]
        running = dict(_config(), **{"client-classes": L.classes("enp6s19")})
        got = L.classes_plan(open(main, encoding="utf-8").read(), main, running, "enp6s19")
        assert got["state"] == "done"

    def test_a_file_with_classes_of_its_own_is_refused(self, moved):
        main = moved["mains"]["IPv4"]
        running = dict(_config(), **{"client-classes": [{"name": "voip", "test": "true"}]})
        got = L.classes_plan(open(main, encoding="utf-8").read(), main, running, "enp6s19")
        assert got["state"] == "refused" and "voip" in got["refused"]


class TestTheRange:

    def test_the_highest_free_block_below_the_broadcast_s(self):
        config = _config()
        assert L.free_range(config, _ztp(config), _leases(), {}, "10.255.0.10") == \
            "10.255.0.192/27"

    def test_an_intent_address_in_it_moves_it_down(self):
        config = _config()
        intent = {"IPv4": {"10.255.0.0/24": [{"device": "r8", "iface": "Gi1", "gateway": [],
                                              "address": "10.255.0.200"}]}}
        assert L.free_range(config, _ztp(config), _leases(), intent, "10.255.0.10") == \
            "10.255.0.160/27"

    @pytest.mark.parametrize("rng, words", [
        ("10.255.0.224/27", "network or broadcast"),
        ("10.10.10.192/27", "does not lie inside"),
        ("10.255.0.32/27", "not free: 10.255.0.40 (this host"),
    ])
    def test_a_range_asked_for_and_not_free_is_refused_naming_why(self, rng, words):
        config = _config()
        with pytest.raises(L.Refused, match=re.escape(words)):
            L.check_range(rng, config, _ztp(config), _leases(), {}, "10.255.0.40")

    def test_the_pools_split_it_pnp_first(self):
        assert L.pools("10.255.0.192/27") == [
            {"pool": "10.255.0.192 - 10.255.0.207", "client-class": "nmas-discovery-pnp"},
            {"pool": "10.255.0.208 - 10.255.0.223", "client-class": "nmas-discovery"}]


@pytest.fixture
def classed(moved, monkeypatch):
    """Kea after the host step's first half: it runs the two classes."""
    k = moved["kea"]
    k.base["dhcp4"][0]["arguments"]["Dhcp4"]["client-classes"] = L.classes("enp6s19")
    monkeypatch.setattr(L, "host_addrs", lambda: ADDRS)
    return moved


class TestThePools:

    def test_refused_until_kea_runs_the_classes(self, moved, monkeypatch):
        monkeypatch.setattr(L, "host_addrs", lambda: ADDRS)
        p = L.plan("Lab", {"family": "IPv4"}, kea=moved["kea"], intent={})
        assert not p["ok"] and "does not run the two discovery classes" in p["refused"]

    def test_written_through_board_c_s_path_and_the_update_check_reads_done(self, classed):
        from modules import host_steps
        k = classed["kea"]
        assert host_steps.check_kea_discovery_range(kea=k, addrs=ADDRS)["state"] == "not_done"
        values = {"op": "edit", "family": "IPv4", "range": ""}
        p = L.plan("Lab", values, kea=k, intent={})
        assert p["ok"], p["refused"]
        assert p["range"] == "10.255.0.192/27" and p["id"] == 255
        recorded = []
        with open(classed["files"]["dhcp4"], encoding="utf-8") as fh:
            before = S.load(fh.read())
        got = S.apply_edit("Lab", values, p["hash"], actor="op (host shell)", reason="board L",
                           kea=k, run_test=_ok_test, intent={},
                           record=lambda ln, pp, actor, reason: recorded.append(pp) or
                           {"ok": True, "commit": "abc1234"},
                           planner=lambda ln, v, kea=None, intent=None: L.plan(
                               ln, v, kea=kea, intent=intent))
        assert got["ok"], got
        assert "holds subnet 255 as written" in got["read_back"]
        subs = S.load(open(classed["files"]["dhcp4"], encoding="utf-8").read())
        assert next(s for s in subs if s["id"] == 255)["pools"] == L.pools("10.255.0.192/27")
        assert [s for s in subs if s["id"] != 255] == [s for s in before if s["id"] != 255]
        assert {k: v for k, v in next(s for s in subs if s["id"] == 255).items()
                if k != "pools"} == {k: v for k, v in next(s for s in before if s["id"] == 255)
                                     .items() if k != "pools"}
        assert recorded and recorded[0]["subject"].startswith("dhcp: the discovery range")
        check = host_steps.check_kea_discovery_range(kea=k, addrs=ADDRS)
        assert check["state"] == "done", check
        again = L.plan("Lab", values, kea=k, intent={})
        assert not again["ok"] and "already has discovery pools" in again["refused"]


def _snap(config):
    return {"IPv4": {"config": config, "reservations": ["r"], "leases": [{"ip-address": "a"}]},
            "IPv6": {"config": {"subnet6": []}, "reservations": [], "leases": []}}


def _tool():
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    path = os.path.join(os.path.dirname(KEA), "..", "..", "scripts", "nmas-kea-discovery-range")
    spec = spec_from_loader("discovery_tool", SourceFileLoader("discovery_tool", path))
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTheStepSBeforeAndAfter:

    def _after(self):
        after = json.loads(json.dumps(_config()))
        after["client-classes"] = L.classes("enp6s19")
        _ztp(after)["pools"] = L.pools("10.255.0.192/27")
        return after

    def test_only_the_classes_and_the_ztp_pools_moved(self):
        assert _tool().expected(_snap(_config()), _snap(self._after()), 255) == []

    def test_anything_else_moving_is_named(self):
        after = self._after()
        after["subnet4"][0]["valid-lifetime"] = 300
        b = _snap(after)
        b["IPv4"]["leases"] = []
        moved = _tool().expected(_snap(_config()), b, 255)
        assert "IPv4: subnet 10 moved beyond the discovery pools" in moved
        assert "IPv4: the leases differ" in moved
