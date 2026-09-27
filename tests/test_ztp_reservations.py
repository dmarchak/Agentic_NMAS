"""P.6 step 1: the reservation writer (D1) and D4's posture.

The fake Kea below does what the real one was MEASURED doing in M5: its
running reservations for the ZTP subnet come from the fragment file, and they
change only when `config-reload` re-reads it. So the writer's read-back is
exercised against a server that can disagree with the file, not assumed.
Documentation addresses (RFC 5737) throughout.
"""

import importlib.machinery
import importlib.util
import json
import os
import socket
import struct

import pytest

from modules.nsot import ztp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBNET = "192.0.2.0/24"
SERVER = "192.0.2.10"
MAC = "aa:bb:cc:00:02:50"
ADDR = "192.0.2.50"


class FakeKea:
    def __init__(self, fragment, *, subnet_options=None, global_options=None,
                 leases=None, other_reservations=None, classes=None):
        self.fragment = fragment
        self.subnet_options = list(subnet_options or [])
        self.global_options = list(global_options or [])
        self.leases = list(leases or [])
        self.other = list(other_reservations or [])
        self.classes = classes
        self.calls = []
        self.fail = set()
        self.ignore_reload = False
        self._load()

    def _load(self):
        with open(self.fragment, encoding="utf-8") as fh:
            self.ztp_reservations = json.load(fh)

    def _config(self):
        dhcp4 = {"option-data": self.global_options, "subnet4": [
            {"id": 10, "subnet": "198.51.100.0/24", "reservations": self.other,
             "option-data": [{"name": "routers"}, {"name": "domain-name-servers"}]},
            {"id": 255, "subnet": SUBNET, "reservations": self.ztp_reservations,
             "option-data": self.subnet_options}]}
        if self.classes:
            dhcp4["client-classes"] = self.classes
        return [{"result": 0, "arguments": {"Dhcp4": dhcp4, "hash": "x"}}]

    def command(self, command, service=None):
        self.calls.append(command)
        if command in self.fail:
            return {"ok": False, "error": f"{command} refused"}
        if command == "config-get":
            return {"ok": True, "result": self._config()}
        if command == "config-reload":
            if not self.ignore_reload:
                self._load()
            return {"ok": True, "result": [{"result": 0}]}
        if command == "lease4-get-all":
            return {"ok": True, "result": [{"result": 0, "arguments": {"leases": self.leases}}]}
        raise AssertionError(command)


@pytest.fixture
def site(tmp_path):
    folder = tmp_path / "nmas"
    folder.mkdir()
    fragment = folder / "reservations-255.json"
    fragment.write_text("[]\n")
    main = tmp_path / "kea-dhcp4.conf"
    main.write_text('{ "Dhcp4": { "subnet4": [ { "id": 255, "reservations": '
                    f'<?include "{fragment}"?> }} ] }} }}\n')
    return str(fragment), str(main)


def _accepting_test(config_path):
    """Stands in for `kea-dhcp4 -t`: the candidate must parse and be a list."""
    text = open(config_path).read()
    included = text.split('<?include "', 1)[1].split('"?>', 1)[0]
    assert os.path.basename(included).startswith(".candidate-"), included
    assert os.path.dirname(included) == os.path.dirname(config_path)
    assert isinstance(json.load(open(included)), list)
    return True, "Syntax check OK"


def _entry(mac=MAC, addr=ADDR, host="bp-ztp-a", **extra):
    e = ztp.reservation_entry(mac, addr, host, SERVER)
    e.update(extra)
    return e


def _write(site, kea, adds=(), removes=(), run_test=_accepting_test):
    fragment, main = site
    return ztp.write_reservations(adds, removes, kea=kea, fragment=fragment,
                                  main_config=main, run_test=run_test)


class TestItWrites:
    def test_a_reservation_is_written_reloaded_and_read_back(self, site):
        kea = FakeKea(site[0])
        out = _write(site, kea, [_entry()])
        assert out["ok"] and out["reloaded"], out
        assert out["outcomes"][MAC]["outcome"] == "written"
        assert json.load(open(site[0])) == [_entry()]
        assert kea.calls[-2:] == ["config-reload", "config-get"]

    def test_the_entry_carries_the_config_source_and_nothing_d4_forbids(self):
        e = _entry()
        names = [o["name"] for o in e["option-data"]]
        assert names == ["tftp-server-name", "boot-file-name"]
        assert e["option-data"][1]["data"] == "bp-ztp-a.cfg"
        assert e["hostname"] == "bp-ztp-a"
        assert all(o["always-send"] for o in e["option-data"])

    def test_writing_it_again_changes_nothing_and_reloads_nothing(self, site):
        kea = FakeKea(site[0])
        _write(site, kea, [_entry()])
        kea.calls.clear()
        out = _write(site, kea, [_entry()])
        assert out["ok"] and out["outcomes"][MAC]["outcome"] == "unchanged"
        assert "config-reload" not in kea.calls

    def test_the_fragment_is_0644_whatever_the_umask(self, site):
        kea = FakeKea(site[0])
        old = os.umask(0o077)
        try:
            _write(site, kea, [_entry()])
        finally:
            os.umask(old)
        assert oct(os.stat(site[0]).st_mode & 0o777) == "0o644"

    def test_the_candidate_and_test_copy_are_cleaned_up(self, site):
        kea = FakeKea(site[0])
        _write(site, kea, [_entry()])
        assert sorted(os.listdir(os.path.dirname(site[0]))) == ["reservations-255.json"]


class TestItRefusesPerDevice:
    """A set in, per-device outcomes out: one refusal does not stop the rest."""

    def test_a_mac_reserved_elsewhere(self, site):
        kea = FakeKea(site[0], other_reservations=[
            {"hw-address": MAC, "ip-address": "198.51.100.7"}])
        out = _write(site, kea, [_entry(), _entry("aa:bb:cc:00:02:51", "192.0.2.51", "bp-ztp-b")])
        assert out["outcomes"][MAC]["outcome"] == "refused"
        assert "198.51.100.7" in out["outcomes"][MAC]["detail"]
        assert out["outcomes"]["aa:bb:cc:00:02:51"]["outcome"] == "written"
        assert not out["ok"], "a refused device must not read as success"

    def test_an_address_reserved_for_another_mac(self, site):
        kea = FakeKea(site[0], other_reservations=[
            {"hw-address": "aa:bb:cc:00:09:99", "ip-address": ADDR}])
        out = _write(site, kea, [_entry()])
        assert out["outcomes"][MAC]["outcome"] == "refused"
        assert "aa:bb:cc:00:09:99" in out["outcomes"][MAC]["detail"]

    def test_an_address_leased_to_another_mac(self, site):
        kea = FakeKea(site[0], leases=[{"ip-address": ADDR, "hw-address": "aa:bb:cc:00:09:98"}])
        out = _write(site, kea, [_entry()])
        assert "leased to aa:bb:cc:00:09:98" in out["outcomes"][MAC]["detail"]

    def test_an_address_no_subnet_contains(self, site):
        kea = FakeKea(site[0])
        out = _write(site, kea, [_entry(addr="203.0.113.5")])
        assert "found 0" in out["outcomes"][MAC]["detail"]


class TestD4AtWriteTime:
    @pytest.mark.parametrize("where", ["subnet", "global"])
    @pytest.mark.parametrize("opt", [{"name": "routers"}, {"name": "domain-name-servers"},
                                     {"code": 33}, {"code": 121}])
    def test_a_route_or_resolver_option_refuses_the_write(self, site, where, opt):
        kw = {"subnet_options": [opt]} if where == "subnet" else {"global_options": [opt]}
        kea = FakeKea(site[0], **kw)
        out = _write(site, kea, [_entry()])
        assert out["outcomes"][MAC]["outcome"] == "refused"
        assert out["outcomes"][MAC]["detail"].startswith("D4:")
        assert json.load(open(site[0])) == []

    def test_an_option_on_the_entry_itself_refuses(self, site):
        kea = FakeKea(site[0])
        e = _entry()
        e["option-data"].append({"name": "domain-name-servers", "data": "192.0.2.53"})
        out = _write(site, kea, [e])
        assert "this reservation" in out["outcomes"][MAC]["detail"]

    def test_client_classes_are_not_ruled_out(self, site):
        kea = FakeKea(site[0], classes=[{"name": "x"}])
        out = _write(site, kea, [_entry()])
        assert "could not be ruled out" in out["outcomes"][MAC]["detail"]

    def test_the_other_subnets_options_do_not_count(self, site):
        # Floor: subnet 10 carries routers and DNS, and it is not the ZTP subnet.
        kea = FakeKea(site[0])
        assert _write(site, kea, [_entry()])["ok"]


class TestTheLiveFragmentIsProtected:
    def test_a_candidate_kea_refuses_never_touches_it(self, site):
        kea = FakeKea(site[0])
        before = open(site[0], "rb").read()
        out = _write(site, kea, [_entry()], run_test=lambda p: (False, "bad reservation"))
        assert open(site[0], "rb").read() == before
        assert "config-reload" not in kea.calls
        assert "was not touched" in out["error"]
        assert out["outcomes"][MAC]["outcome"] == "refused"

    def test_a_failed_reload_restores_the_previous_fragment(self, site):
        kea = FakeKea(site[0])
        kea.fail.add("config-reload")
        out = _write(site, kea, [_entry()])
        assert json.load(open(site[0])) == []
        assert "previous fragment was restored" in out["error"]

    def test_a_server_that_did_not_take_it_is_named_with_both_operands(self, site):
        kea = FakeKea(site[0])
        kea.ignore_reload = True
        out = _write(site, kea, [_entry()])
        assert not out["ok"]
        assert "does not hold what was written" in out["error"]
        assert MAC in out["error"] and ADDR in out["error"]


class TestPreconditionsOfTheWholeWrite:
    def test_not_configured_is_the_guard_message(self, site, monkeypatch):
        kea = FakeKea(site[0])
        out = ztp.write_reservations([_entry()], kea=kea, fragment="", main_config=site[1])
        assert out["error"].startswith("kea_ztp_fragment is not configured")

    def test_a_main_config_that_does_not_include_the_fragment(self, site, tmp_path):
        kea = FakeKea(site[0])
        other = tmp_path / "other.conf"
        other.write_text('{ "Dhcp4": {} }')
        out = ztp.write_reservations([_entry()], kea=kea, fragment=site[0],
                                     main_config=str(other), run_test=_accepting_test)
        assert "does not include" in out["error"]

    def test_an_unreadable_fragment_is_never_written_over(self, site):
        kea = FakeKea(site[0])
        open(site[0], "w").write("{ not json")
        out = _write(site, kea, [_entry()])
        assert "unreadable" in out["error"]
        assert open(site[0]).read() == "{ not json"

    def test_kea_that_cannot_be_asked_writes_nothing(self, site):
        kea = FakeKea(site[0])
        kea.fail.add("lease4-get-all")
        out = _write(site, kea, [_entry()])
        assert "leases" in out["error"] and json.load(open(site[0])) == []


class TestRemoval:
    def test_its_own_reservation_is_removed(self, site):
        kea = FakeKea(site[0])
        _write(site, kea, [_entry()])
        out = _write(site, kea, removes=[MAC])
        assert out["ok"] and out["outcomes"][MAC]["outcome"] == "removed"
        assert json.load(open(site[0])) == []

    def test_one_it_did_not_write_is_refused(self, site):
        kea = FakeKea(site[0], other_reservations=[
            {"hw-address": MAC, "ip-address": "198.51.100.7"}])
        out = _write(site, kea, removes=[MAC])
        assert "removes only what it wrote" in out["outcomes"][MAC]["detail"]

    def test_an_absent_one_is_absent_not_an_error(self, site):
        out = _write(site, FakeKea(site[0]), removes=[MAC])
        assert out["ok"] and out["outcomes"][MAC]["outcome"] == "absent"


class TestServerAddress:
    def test_the_one_address_in_the_subnet(self):
        assert ztp.server_address(SUBNET, {"lo": ["127.0.0.1"], "eth1": [SERVER]}) == SERVER

    @pytest.mark.parametrize("addrs", [{"eth0": ["198.51.100.1"]},
                                       {"eth1": [SERVER], "eth2": ["192.0.2.11"]}])
    def test_none_or_two_is_refused(self, addrs):
        with pytest.raises(ztp.Refused):
            ztp.server_address(SUBNET, addrs)


class _FakeSock:
    def __init__(self, replies=(), fail_bind=False):
        self.replies = list(replies)
        self.fail_bind = fail_bind
        self.sent = []

    def setsockopt(self, *a):
        pass

    def bind(self, addr):
        if self.fail_bind:
            raise OSError("cannot assign requested address")

    def settimeout(self, t):
        pass

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def recvfrom(self, n):
        if self.replies:
            make = self.replies.pop(0)
            return make(self.sent[0][0]), ("192.0.2.53", 53)
        raise socket.timeout

    def close(self):
        pass


def _clock():
    t = [1000.0]

    def now():
        t[0] += 0.25
        return t[0]
    return now


class TestD4DnsCondition:
    def test_it_asks_by_broadcast_on_port_53_with_an_invalid_name(self):
        s = _FakeSock()
        ztp.dns_answerers(SERVER, timeout=1, sock_factory=lambda: s, clock=_clock())
        data, addr = s.sent[0]
        assert addr == ("255.255.255.255", 53)
        assert b"\x07invalid\x00" in data

    def test_a_reply_with_the_query_id_is_an_answerer(self):
        s = _FakeSock([lambda q: q[:2] + b"\x81\x83" + q[4:]])
        out = ztp.dns_answerers(SERVER, timeout=1, sock_factory=lambda: s, clock=_clock())
        assert out["state"] == "answered" and out["answerers"] == ["192.0.2.53"]

    def test_a_reply_to_another_query_is_not(self):
        s = _FakeSock([lambda q: struct.pack(">H", (struct.unpack(">H", q[:2])[0] + 1) & 0xFFFF) + q[2:]])
        out = ztp.dns_answerers(SERVER, timeout=1, sock_factory=lambda: s, clock=_clock())
        assert out["state"] == "silent"

    def test_a_probe_that_could_not_be_sent_is_unknown_not_silent(self):
        out = ztp.dns_answerers(SERVER, sock_factory=lambda: _FakeSock(fail_bind=True))
        assert out["state"] == "unknown" and "could not be sent" in out["error"]


class TestPosture:
    def _posture(self, site, dns_state="silent", **kw):
        kea = FakeKea(site[0], **kw)
        dns = lambda src: {"state": dns_state, "answerers": ["192.0.2.53"] if dns_state == "answered" else [],
                           "error": "", "measured_at": 0}
        return ztp.posture(ADDR, kea=kea, dns=dns, addrs={"eth1": [SERVER]})

    def test_clean(self, site):
        out = self._posture(site)
        assert out["ok"] and out["server"] == SERVER and out["subnet_id"] == 255

    def test_an_option_is_a_reason(self, site):
        out = self._posture(site, subnet_options=[{"name": "domain-name-servers"}])
        assert not out["ok"] and "domain-name-servers" in out["reasons"][0]

    def test_an_answering_host_is_a_reason(self, site):
        out = self._posture(site, dns_state="answered")
        assert not out["ok"] and "answers broadcast DNS (192.0.2.53)" in out["reasons"][0]

    def test_an_unmeasured_segment_is_a_reason(self, site):
        out = self._posture(site, dns_state="unknown")
        assert not out["ok"] and "could not be measured" in out["reasons"][0]

    def test_kea_that_cannot_be_asked_is_a_reason(self, site):
        kea = FakeKea(site[0])
        kea.fail.add("config-get")
        out = ztp.posture(ADDR, kea=kea, dns=lambda s: {"state": "silent"}, addrs={"eth1": [SERVER]})
        assert not out["ok"] and "could not be asked" in out["reasons"][0]


class TestDnsReuse:
    def test_reused_within_the_window_and_says_so(self, monkeypatch):
        monkeypatch.setattr(ztp, "_dns_cache", {})
        calls = []
        probe = lambda s: calls.append(s) or {"state": "silent", "answerers": [],
                                               "measured_at": 100.0, "error": ""}
        first = ztp.dns_posture(SERVER, probe=probe, clock=lambda: 100.0)
        second = ztp.dns_posture(SERVER, probe=probe, clock=lambda: 200.0)
        assert len(calls) == 1 and not first["reused"] and second["reused"]
        assert second["measured_at"] == 100.0

    def test_an_unknown_answer_is_never_reused(self, monkeypatch):
        monkeypatch.setattr(ztp, "_dns_cache", {})
        calls = []
        probe = lambda s: calls.append(s) or {"state": "unknown", "answerers": [],
                                               "measured_at": 100.0, "error": "x"}
        ztp.dns_posture(SERVER, probe=probe, clock=lambda: 100.0)
        ztp.dns_posture(SERVER, probe=probe, clock=lambda: 101.0)
        assert len(calls) == 2


def test_the_module_and_the_probe_helper_agree_on_d4():
    """Two copies of one rule diverge, so they are pinned together: the probe
    helper (stdlib, run by hand as root) and the tool's module."""
    loader = importlib.machinery.SourceFileLoader(
        "kea_m5", os.path.join(ROOT, "docs", "bootstrap-probe", "kea-m5.py"))
    helper = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(helper)
    assert helper.FORBIDDEN_OPTIONS == ztp.FORBIDDEN_OPTIONS
    cases = [[], [{"name": "routers"}], [{"code": 121}], [{"name": "boot-file-name"}]]
    assert len(cases) >= 4
    for opts in cases:
        cfg = {"Dhcp4": {"subnet4": [{"id": 255, "subnet": SUBNET, "option-data": opts,
                                      "reservations": [{"hw-address": MAC, "ip-address": ADDR}]}]}}
        assert bool(helper.forbidden_options(cfg)) == bool(ztp.forbidden_options(cfg["Dhcp4"], ADDR)), opts


class TestPostureRows:
    """The job-health half of D4: a property held by absence, checked where
    somebody adding an option to the ZTP subnet would otherwise go unseen."""

    def _kea(self, site, **kw):
        kea = FakeKea(site[0], **kw)
        cfg = kea._config

        def config():
            c = cfg()
            c[0]["arguments"]["Dhcp4"]["interfaces-config"] = {"interfaces": ["eth1"]}
            return c
        kea._config = config
        return kea

    def _rows(self, kea, dns_state="silent", fragment="/etc/kea/nmas/r.json"):
        dns = lambda s: {"state": dns_state, "answerers": [], "error": "", "measured_at": 0}
        return ztp.posture_rows(kea=kea, dns=dns, addrs={"eth1": [SERVER], "eth0": ["198.51.100.1"]},
                                get=lambda k, d="": fragment)

    def test_no_row_while_ztp_is_not_configured(self, site):
        assert self._rows(self._kea(site), fragment="") == []

    def test_the_ztp_subnet_is_found_from_the_listening_interface(self, site):
        rows = self._rows(self._kea(site))
        # Floor: exactly subnet 255, not subnet 10 (eth0 is not a Kea interface).
        assert [r["unit"] for r in rows] == ["ztp-posture:subnet-255"]
        assert rows[0]["state"] == "ok"

    def test_an_option_added_later_is_named(self, site):
        rows = self._rows(self._kea(site, subnet_options=[{"name": "routers"}]))
        assert rows[0]["state"] == "d4_violated" and "routers" in rows[0]["detail"]

    def test_an_unmeasured_segment_is_unknown_not_ok(self, site):
        assert self._rows(self._kea(site), dns_state="unknown")[0]["state"] == "unknown"

    def test_it_is_in_health(self):
        from modules import job_health
        out = job_health.health(images=[], settings=[], rotations=[], owner=[],
                                ztp=[{"unit": "ztp-posture:subnet-255", "state": "d4_violated",
                                      "what": "", "detail": "", "max_age_minutes": 0}])
        assert "ztp-posture:subnet-255" in out["not_ok"]
