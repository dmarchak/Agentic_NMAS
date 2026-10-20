"""C1403 part 2: a ZTP subnet matches a lease by the device's MAC, never its client-id
(`modules/dhcp_lease_identity.py`).

The premise is a measurement, kept as a fixture (tests/fixtures/kea/
c1403_match_client_id_probe.txt: this installation's Kea 2.4.1, a throwaway copy on loopback):
with `match-client-id` true a reserved device back with the same MAC and a new client-id is
never answered (0d's ALLOC_ENGINE_V4_DISCOVER_ADDRESS_CONFLICT) and its REQUEST is NAKed; with
it false it is offered and acknowledged its reserved address. Then, on Kea's captured
configuration (global `match-client-id` true, ZTP's subnet 255 on enp6s19) and on
test_ztp_relayed's two ZTP subnets (255 direct, 40 relayed):

- where the value Kea runs comes from (subnet, shared network, global, Kea's default);
- job health's row per ZTP subnet: client-id matched names its fix (the host step for a direct
  subnet, Edit… for a relayed one), and reads ok once the subnet says false;
- the planner for board C's one write path, and the write itself (Kea's check, write, reload,
  read back), only `match-client-id` moving, only on a ZTP subnet;
- a relayed subnet added for ZTP is written with it, and an edit of one written before writes it;
- the host step's comparison of two snapshots.
"""

import copy
import json
import os
import sys

import pytest

from modules import dhcp_lease_identity as LI
from tests.test_dhcp_subnets import SubnetKea, _ok_test, moved  # noqa: F401 (the fixture)
from tests import test_ztp_relayed as TZ
from tests.test_ztp_relayed import ADDRS, FakeKea, kea_files  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "tests", "fixtures", "kea", "c1403_match_client_id_probe.txt")
CAPTURED = os.path.join(ROOT, "tests", "fixtures", "kea", "dhcp4-config-get.json")
#: This host's address on the captured config's listening interface, in ZTP's subnet 255.
HOST = {"enp6s19": ["10.255.0.10"], "lan0": ["203.0.113.5"]}


def _captured() -> dict:
    with open(CAPTURED, encoding="utf-8") as fh:
        return json.load(fh)[0]["arguments"]["Dhcp4"]


class TestTheMeasurement:
    """What the probe recorded: the reason for the setting, held so it cannot drift from it."""

    def _setting(self, which):
        text = open(PROBE, encoding="utf-8").read()
        return text.split(f"== match-client-id {which}\n", 1)[1].split("\n== ", 1)[0]

    def test_true_never_answers_a_new_client_id_on_the_same_mac(self):
        t = self._setting("true")
        assert "2a DISCOVER, NEW client-id, same MAC: no answer" in t
        assert "2b REQUEST, NEW client-id, same MAC: NAK" in t
        assert "ALLOC_ENGINE_V4_DISCOVER_ADDRESS_CONFLICT" in t

    def test_false_answers_it_with_its_reserved_address(self):
        t = self._setting("false")
        assert "2a DISCOVER, NEW client-id, same MAC: OFFER 10.255.96.2" in t
        assert "2b REQUEST, NEW client-id, same MAC: ACK 10.255.96.2" in t

    def test_the_old_client_id_is_answered_either_way(self):
        for which in ("true", "false"):
            assert "3  control: DISCOVER, old client-id again: OFFER 10.255.96.2" in \
                self._setting(which)


class TestWhereTheValueComesFrom:
    @pytest.mark.parametrize("subnet, net, glob, want", [
        ({"id": 1, LI.KEY: False}, None, {LI.KEY: True}, (False, "subnet 1")),
        ({"id": 1}, {"name": "n", LI.KEY: False}, {LI.KEY: True}, (False, "shared network n")),
        ({"id": 1}, None, {LI.KEY: True}, (True, "Kea's global level")),
        ({"id": 1}, None, {}, (True, "Kea's default (no level sets it)")),
    ], ids=["subnet", "shared-network", "global", "kea-default"])
    def test_the_nearest_level_wins(self, subnet, net, glob, want):
        assert LI.effective(glob, subnet, net) == want


class TestTheRows:
    def test_the_captured_ztp_subnet_matches_by_client_id_and_names_the_host_step(self):
        rows = LI.rows(_captured(), HOST)
        assert [r["unit"] for r in rows] == ["ztp-lease-identity:subnet-255"]
        r = rows[0]
        assert r["state"] == "client_id_matched"
        assert "match-client-id true, from Kea's global level" in r["detail"]
        assert r["action"]["command"] == "bash scripts/host-steps/c1403-ztp-lease-identity.sh"

    def test_once_the_subnet_says_false_it_is_ok(self):
        d = _captured()
        next(s for s in d["subnet4"] if s["id"] == 255)[LI.KEY] = False
        r = LI.rows(d, HOST)[0]
        assert r["state"] == "ok" and "set at subnet 255" in r["detail"]

    def test_a_non_ztp_subnet_has_no_row(self):
        assert [r["unit"] for r in LI.rows(_captured(), {"lan0": ["203.0.113.5"]})] == []

    def test_a_relayed_one_names_edit(self, kea_files):  # noqa: F811
        d = FakeKea({255: kea_files["direct"], 40: kea_files["relayed"]})._config()[0][
            "arguments"]["Dhcp4"]
        rows = {r["unit"]: r for r in LI.rows(d, ADDRS)}
        assert set(rows) == {"ztp-lease-identity:subnet-255", "ztp-lease-identity:subnet-40"}
        relayed = rows["ztp-lease-identity:subnet-40"]
        assert relayed["state"] == "client_id_matched"
        assert "Edit the subnet on DHCP › Subnets" in relayed["action"]["label"]
        assert "Kea's default" in relayed["detail"]

    def test_job_health_carries_them_only_while_ztp_is_configured(self):
        from modules.nsot import ztp

        class Kea:
            def command(self, command, service=None):
                return {"ok": True, "result": [{"result": 0, "arguments": {
                    "Dhcp4": _captured()}}]}
        on = ztp.lease_identity_rows(kea=Kea(), addrs=HOST,
                                     get=lambda k, d=None: "/etc/kea/nmas/ztp.json")
        assert [r["state"] for r in on] == ["client_id_matched"]
        assert ztp.lease_identity_rows(kea=Kea(), addrs=HOST, get=lambda k, d=None: "") == []

    def test_job_health_lists_the_source(self):
        from modules import job_health as J
        row = {"unit": "ztp-lease-identity:subnet-255", "state": "client_id_matched",
               "max_age_minutes": 0, "detail": "x"}
        h = J.health(images=[], settings=[], rotations=[], ztp=[], responder=[], startup=[],
                     sessions=[], version=[], readers=[], breakglass=[], prometheus=[],
                     monitoring=[], updater=[], helpers=[], serials=[], lease_identity=[row],
                     run=lambda cmd: (0, "LoadState=loaded\nActiveState=inactive\n"))
        assert "ztp-lease-identity:subnet-255" in h["not_ok"]


class TestThePlannerAndTheWrite:
    def test_the_ztp_subnet_gains_only_the_setting(self, moved):  # noqa: F811
        p = LI.plan("Lab", {"family": "IPv4", "id": "255"}, kea=moved["kea"])
        assert p["ok"], p["refused"]
        assert p["after"] == dict(p["before"], **{LI.KEY: False})
        assert ("+", f"{LI.KEY}: false") in p["change"]
        assert p["op"] == "edit" and len(p["hash"]) == 64

    @pytest.mark.parametrize("values, words", [
        ({"family": "IPv4", "id": "10"}, "subnet 10 is not a ZTP subnet"),
        ({"family": "IPv6", "id": "255"}, "ZTP serves IPv4 only"),
        ({"family": "IPv4", "id": "x"}, "'x' is not a Kea subnet id"),
        ({"family": "IPv4", "id": "99"}, "subnet 99 is in Mercury's IPv4 subnet file 0 times"),
    ], ids=["not-ztp", "ipv6", "not-an-id", "absent"])
    def test_what_it_cannot_change_is_refused_by_name(self, moved, values, words):  # noqa: F811
        p = LI.plan("Lab", values, kea=moved["kea"])
        assert not p["ok"] and words in p["refused"], p["refused"]

    def test_the_write_goes_through_board_c_s_path_and_reads_back(self, moved):  # noqa: F811
        from modules import dhcp_subnets as S
        values = {"family": "IPv4", "id": "255"}
        p = LI.plan("Lab", values, kea=moved["kea"])
        recorded = []
        got = S.apply_edit("Lab", values, p["hash"], actor="op@example.invalid",
                           reason="C1403", kea=moved["kea"], run_test=_ok_test,
                           record=lambda l, plan, **k: recorded.append(plan["subject"]) or
                           {"ok": True, "commit": "c0ffee1"}, planner=LI.plan)
        assert got["ok"], got["error"]
        written = {s["id"]: s for s in S.load(open(moved["files"]["dhcp4"],
                                                   encoding="utf-8").read())}
        assert written[255][LI.KEY] is False
        assert all(LI.KEY not in s for i, s in written.items() if i != 255)
        assert recorded == ["dhcp: IPv4 subnet 255 (10.255.0.0/24) matches leases by MAC "
                            "(C1403)"]
        again = LI.plan("Lab", values, kea=moved["kea"])
        assert not again["ok"] and again["refused"].startswith("nothing would change")


class TestARelayedSubnetCarriesIt:
    def test_an_add_for_ztp_writes_it(self, kea_files, monkeypatch):  # noqa: F811
        t = TZ.TestTheSubnetIsDeclaredAtAdd()
        p = t._plan(kea_files, monkeypatch, t._intent())
        assert p["ok"], p["refused"]
        assert p["after"][LI.KEY] is False
        assert any("match-client-id false" in text for _s, text in p["checks"])

    def test_an_add_not_for_ztp_leaves_kea_s_default(self, kea_files, monkeypatch):  # noqa: F811
        t = TZ.TestTheSubnetIsDeclaredAtAdd()
        p = t._plan(kea_files, monkeypatch, t._intent(), ztp="")
        assert p["ok"], p["refused"]
        assert LI.KEY not in p["after"]

    def test_an_edit_of_one_written_before_writes_it(self, kea_files, monkeypatch):  # noqa: F811
        p = TZ.TestTheDhcpPageChangesARelayedSubnet._plan(kea_files, monkeypatch,
                                                          pool="198.51.100.2 - 198.51.100.2")
        assert p["ok"], p["refused"]
        assert p["after"][LI.KEY] is False and ("+", f"{LI.KEY}: false") in p["change"]


class TestTheHostStepsComparison:
    def _tool(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader(
            "nmas_kea_lease_identity", os.path.join(ROOT, "scripts", "nmas-kea-lease-identity"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    def _snap(self):
        return {"IPv4": {"config": {"subnet4": copy.deepcopy(_captured()["subnet4"])},
                         "reservations": [], "leases": []}}

    def test_only_the_setting_on_a_ztp_subnet_is_as_expected(self):
        a, b = self._snap(), self._snap()
        next(s for s in b["IPv4"]["config"]["subnet4"] if s["id"] == 255)[LI.KEY] = False
        assert self._tool().expected(a, b, {255}) == []

    @pytest.mark.parametrize("edit, words", [
        (lambda s: s[0].update({LI.KEY: False}), "subnet 10 moved beyond match-client-id"),
        (lambda s: s[2].update({"valid-lifetime": 60}), "subnet 255 moved beyond"),
        (lambda s: s[2].update({LI.KEY: True}), "subnet 255 does not say match-client-id false"),
    ], ids=["another-subnet", "another-key", "still-true"])
    def test_anything_else_is_named(self, edit, words):
        a, b = self._snap(), self._snap()
        edit(b["IPv4"]["config"]["subnet4"])
        moved_ = self._tool().expected(a, b, {255})
        assert any(words in m for m in moved_), moved_
