"""C1346: ZTP for a device behind a DHCP relay (modules/nsot/ztp_relayed.py; docs/P6_ZTP.md,
"Relayed ZTP (C1346)").

P.6 refused a relayed device by construction: the server address needed this host to own an
address in the device's subnet, the writer wrote one fragment, D4 refused option 3 everywhere,
the DNS check was a broadcast on the management segment, and the firewall admitted udp/69 from
the management subnet only. Each is answered here, with a planted case and its control:

1. the server address: the relay's committed helper target that is this host's own address
   on an interface Kea listens on, refused naming both sides; an unmanaged relay refused;
2. the fragment: a declared relayed subnet's own reservations file, ZTP's whole (the writer
   routes to it, the DHCP page refuses it, the record holds it), its JSON in Kea's shape;
3. option 3: the relay's own address only, a per-reservation choice, off by default, in the
   plan's hash and the record;
4. DNS on the relayed segment: every helper target measured by unicast, the relay's golden
   read for `ip dns server`, and a job-health row per relayed subnet;
5. the firewall: the host step's record compared with the declared subnets, absent and
   unreadable apart;
6. the discovery classes left as they are (they never match a relayed client);
7. the responder serves a routed peer at its reserved address.

IPv6 is refused by name at each door (ZTP is IPv4 only, C1245). Documentation addresses
(RFC 5737, RFC 3849) throughout.
"""

import json
import os
import socket
import struct
import threading

import pytest

from modules.nsot import ztp, ztp_relayed

DIRECT = "192.0.2.0/24"
SERVER = "192.0.2.10"
RELAYED = "198.51.100.0/30"
RELAY = "198.51.100.1"
DEVICE = "198.51.100.2"
MAC = "aa:bb:cc:00:04:02"
DIRECT_MAC, DIRECT_ADDR = "aa:bb:cc:00:02:50", "192.0.2.50"
ADDRS = {"ztp0": [SERVER], "lan0": ["203.0.113.5"]}


def _facts(relays=(SERVER,), address=RELAY, prefix=RELAYED, extra=()):
    entries = [{"device": "relay-a", "iface": "GigabitEthernet3", "address": address,
                "relays": list(relays), "network": "Lab", "gateway": []}] + list(extra)
    return {"IPv4": {prefix: entries}, "errors": []}


def _relayed_subnet(relay=(RELAY,), reservations=(), declared=True, prefix=RELAYED, sid=40):
    s = {"id": sid, "subnet": prefix, "relay": {"ip-addresses": list(relay)},
         "reservations": list(reservations)}
    if declared:
        s["user-context"] = ztp_relayed.declaration()
    return s


def _dhcp4(*subnets, options=None):
    return {"interfaces-config": {"interfaces": ["ztp0"]}, "option-data": options or [],
            "subnet4": [{"id": 255, "subnet": DIRECT, "reservations": []}] + list(subnets)}


GOLDEN = {"text": "hostname relay-a\ninterface GigabitEthernet3\n ip helper-address "
                  f"{SERVER}\n!\n", "refused": ""}


def _said(out) -> str:
    """Every reason, as one text: an empty list fails the assertion, never an IndexError."""
    return " | ".join(out.get("reasons") or [])


def _silent(target, source):
    return {"state": "silent", "error": ""}


def _routed(cmd):
    return 0, f"{cmd[5]} from {SERVER} via 192.0.2.1 dev ztp0 uid 1000 \\    cache"


def _seams(**kw):
    out = {"facts": _facts(), "golden": lambda relay: GOLDEN,
           "dns": lambda server, relay, golden: ztp_relayed.dns_posture(
               server, relay, golden, probe=_silent),
           "route": _routed}
    out.update(kw)
    return out


@pytest.fixture(autouse=True)
def _fresh_probe_cache():
    ztp_relayed._probe_cache.clear()
    yield
    ztp_relayed._probe_cache.clear()


# ── 1. the server address ──────────────────────────────────────────────────────────────────

class TestTheServerAddress:
    def test_the_relays_helper_target_that_is_this_hosts_is_the_server(self):
        got = ztp_relayed.posture(_dhcp4(_relayed_subnet()), _relayed_subnet(),
                                  address=DEVICE, addrs=ADDRS, **_seams())
        assert got["reasons"] == [], got
        assert got["server"] == SERVER
        assert got["relay"]["device"] == "relay-a" and got["relay"]["address"] == RELAY

    def test_a_helper_target_this_host_does_not_have_is_refused_naming_both(self):
        got = ztp_relayed.posture(_dhcp4(_relayed_subnet()), _relayed_subnet(), address=DEVICE,
                                  addrs=ADDRS, **_seams(facts=_facts(relays=("192.0.2.99",))))
        assert len(got["reasons"]) == 1, got
        why = _said(got)
        assert "['192.0.2.99']" in why and f"['{SERVER}']" in why and "found 0" in why
        assert got["server"] == ""

    def test_an_address_on_an_interface_kea_does_not_listen_on_is_not_the_server(self):
        """Control for "on an interface Kea listens on": the helper target is this host's,
        on an interface Kea does not serve, so Kea never hears the relayed DISCOVER."""
        got = ztp_relayed.posture(_dhcp4(_relayed_subnet()), _relayed_subnet(), address=DEVICE,
                                  addrs=ADDRS, **_seams(facts=_facts(relays=("203.0.113.5",))))
        assert got["server"] == "" and "found 0" in _said(got)

    def test_kea_listening_on_one_address_of_an_interface_counts_only_that_one(self):
        dhcp4 = _dhcp4(_relayed_subnet())
        dhcp4["interfaces-config"]["interfaces"] = ["ztp0/192.0.2.11"]
        addrs = {"ztp0": [SERVER, "192.0.2.11"]}
        assert ztp_relayed.listening_addresses(dhcp4, addrs) == ["192.0.2.11"]
        dhcp4["interfaces-config"]["interfaces"] = ["*"]
        assert ztp_relayed.listening_addresses(dhcp4, ADDRS) == ["192.0.2.10", "203.0.113.5"]

    def test_two_helper_targets_of_this_host_are_refused(self):
        addrs = {"ztp0": [SERVER, "192.0.2.11"]}
        got = ztp_relayed.posture(_dhcp4(_relayed_subnet()), _relayed_subnet(), address=DEVICE,
                                  addrs=addrs,
                                  **_seams(facts=_facts(relays=(SERVER, "192.0.2.11"))))
        assert "found 2" in _said(got)

    def test_a_relay_mercury_does_not_manage_is_refused(self):
        got = ztp_relayed.posture(_dhcp4(_relayed_subnet()), _relayed_subnet(), address=DEVICE,
                                  addrs=ADDRS, **_seams(facts={"IPv4": {}, "errors": []}))
        assert len(got["reasons"]) == 1, got
        why = _said(got)
        assert "no device Mercury manages has an interface on 198.51.100.0/30" in why
        assert "refused rather than typed in" in why

    def test_an_unreadable_network_is_named_beside_the_missing_relay(self):
        got = ztp_relayed.posture(
            _dhcp4(_relayed_subnet()), _relayed_subnet(), address=DEVICE, addrs=ADDRS,
            **_seams(facts={"IPv4": {}, "errors": ["Branch: its intent could not be listed"]}))
        assert "could not be read, so it may be there: Branch" in _said(got)

    def test_a_relay_with_no_helper_address_is_refused(self):
        got = ztp_relayed.posture(_dhcp4(_relayed_subnet()), _relayed_subnet(), address=DEVICE,
                                  addrs=ADDRS, **_seams(facts=_facts(relays=())))
        assert "relays to no DHCP server in committed intent" in _said(got)

    def test_two_interfaces_on_the_prefix_are_refused_naming_them(self):
        other = {"device": "relay-b", "iface": "Gi4", "address": "198.51.100.3",
                 "relays": [SERVER], "network": "Lab"}
        got = ztp_relayed.posture(_dhcp4(_relayed_subnet()), _relayed_subnet(), address=DEVICE,
                                  addrs=ADDRS, **_seams(facts=_facts(extra=[other])))
        assert "found 2" in _said(got) and "relay-b Gi4" in _said(got)

    def test_kea_and_intent_disagreeing_on_the_relay_address_is_refused_naming_both(self):
        sub = _relayed_subnet(relay=("198.51.100.3",))
        got = ztp_relayed.posture(_dhcp4(sub), sub, address=DEVICE, addrs=ADDRS, **_seams())
        assert len(got["reasons"]) == 1, got
        why = _said(got)
        assert "['198.51.100.3']" in why and f"at {RELAY}" in why

    def test_a_declared_subnet_this_host_is_on_is_not_relayed(self):
        sub = _relayed_subnet(prefix=DIRECT)
        got = ztp_relayed.posture(_dhcp4(), sub, addrs=ADDRS, **_seams())
        assert "this host has 192.0.2.10 in it" in _said(got)

    def test_no_route_back_is_a_reason(self):
        got = ztp_relayed.posture(_dhcp4(_relayed_subnet()), _relayed_subnet(), address=DEVICE,
                                  addrs=ADDRS, **_seams(route=lambda cmd: (2, "RTNETLINK "
                                                                          "answers: Network is "
                                                                          "unreachable")))
        assert any("no route to 198.51.100.2" in r for r in got["reasons"]), got

    def test_a_route_that_could_not_be_asked_is_unknown_never_a_pass(self):
        got = ztp_relayed.posture(_dhcp4(_relayed_subnet()), _relayed_subnet(), address=DEVICE,
                                  addrs=ADDRS, **_seams(route=lambda cmd: (None, "no ip")))
        assert any("could not be measured" in r for r in got["reasons"]), got

    def test_the_route_command_asks_from_the_server_address(self):
        asked = []
        ztp_relayed.route_to(DEVICE, SERVER, lambda cmd: asked.append(cmd) or (0, "x dev y"))
        assert asked == [["ip", "-4", "-o", "route", "get", DEVICE, "from", SERVER]]


class TestThePostureEndToEnd:
    """`ztp.posture` and `ztp.plan_check` dispatch a declared subnet to the relayed check."""

    class Kea:
        def __init__(self, dhcp4):
            self.dhcp4 = dhcp4

        def command(self, command, service=None):
            if command == "config-get":
                return {"ok": True, "result": [{"arguments": {"Dhcp4": self.dhcp4}}]}
            if command == "lease4-get-all":
                return {"ok": True, "result": [{"arguments": {"leases": []}}]}
            raise AssertionError(command)

    def test_a_declared_subnet_is_asked_as_relayed(self):
        kea = self.Kea(_dhcp4(_relayed_subnet()))
        p = ztp.plan_check(MAC, DEVICE, kea=kea, addrs=ADDRS, get=lambda k, d="": "/f",
                           relayed=_seams())
        assert p["ok"], p["reasons"]
        assert p["relayed"] and p["server"] == SERVER and p["relay"]["address"] == RELAY

    def test_an_undeclared_subnet_this_host_is_not_on_is_refused_with_the_way_forward(self):
        """Control: the same subnet, not declared, is P.6's refusal, now naming the fix."""
        kea = self.Kea(_dhcp4(_relayed_subnet(declared=False)))
        p = ztp.plan_check(MAC, DEVICE, kea=kea, addrs=ADDRS, get=lambda k, d="": "/f",
                           relayed=_seams())
        assert not p["ok"] and not p["relayed"]
        assert any("found 0" in r and "For ZTP onboarding" in r for r in p["reasons"]), p

    def test_an_ipv6_address_is_refused_by_name(self):
        kea = self.Kea(_dhcp4(_relayed_subnet()))
        p = ztp.plan_check(MAC, "2001:db8:4::2", kea=kea, addrs=ADDRS,
                           get=lambda k, d="": "/f", relayed=_seams())
        assert not p["ok"] and "IPv6" in _said(p) and "C1245" in _said(p)

    def test_an_ipv6_relayed_prefix_is_refused_by_name(self):
        with pytest.raises(ztp.Refused, match="IPv6.*C1245"):
            ztp_relayed.relay_for("2001:db8:4::/64", _facts(prefix="2001:db8:4::/64"))


# ── 2. the fragment ────────────────────────────────────────────────────────────────────────

class FakeKea:
    """Kea as M5 measured it: each subnet's running reservations come from its file and change
    only at config-reload. Subnet 255 is the one this host is on; subnet 40 is declared relayed,
    its reservations in its own file."""

    def __init__(self, files, relay=(RELAY,), subnet_options=None):
        self.files, self.relay, self.calls = files, list(relay), []
        self.subnet_options = list(subnet_options or [])
        self._load()

    def _load(self):
        self.held = {sid: json.load(open(path, encoding="utf-8"))
                     for sid, path in self.files.items()}

    def _config(self):
        return [{"result": 0, "arguments": {"Dhcp4": {
            "interfaces-config": {"interfaces": ["ztp0"]},
            "subnet4": [{"id": 255, "subnet": DIRECT, "reservations": self.held[255]},
                        {"id": 40, "subnet": RELAYED, "relay": {"ip-addresses": self.relay},
                         "user-context": ztp_relayed.declaration(),
                         "option-data": self.subnet_options,
                         "reservations": self.held[40]}]}}}]

    def command(self, command, service=None):
        self.calls.append(command)
        if command == "config-get":
            return {"ok": True, "result": self._config()}
        if command == "config-reload":
            self._load()
            return {"ok": True, "result": [{"result": 0}]}
        if command == "lease4-get-all":
            return {"ok": True, "result": [{"result": 0, "arguments": {"leases": []}}]}
        raise AssertionError(command)


@pytest.fixture
def kea_files(tmp_path):
    """Kea's main file includes Mercury's subnet file (C529 step 5's shape), which includes
    each subnet's reservations file: 255's (the network's ZTP fragment) and 40's (declared
    relayed)."""
    nmas = tmp_path / "nmas"
    nmas.mkdir()
    direct, relayed = nmas / "reservations-255.json", nmas / "reservations-40.json"
    direct.write_text("[]\n")
    relayed.write_text("[]\n")
    subnets = nmas / "subnets4.json"
    from modules import dhcp_subnets as S
    subnets.write_text(S.dump([
        {"id": 255, "subnet": DIRECT, "reservations": f"@@kea-include:{direct}@@"},
        {"id": 40, "subnet": RELAYED, "relay": {"ip-addresses": [RELAY]},
         "user-context": ztp_relayed.declaration(),
         "reservations": f"@@kea-include:{relayed}@@"}]))
    main = tmp_path / "kea-dhcp4.conf"
    main.write_text('{ "Dhcp4": { "interfaces-config": { "interfaces": [ "ztp0" ] }, '
                    f'"subnet4": <?include "{subnets}"?> }} }}\n')
    return {"direct": str(direct), "relayed": str(relayed), "main": str(main),
            "subnets": str(subnets)}


#: Kea's reservation keys and the option names a ZTP reservation may carry (Kea 2.4.1's
#: standard option names; P.6 M3 measured 66 and 67).
KEA_RESERVATION_KEYS = {"hw-address", "ip-address", "hostname", "option-data"}
KEA_OPTION_NAMES = {"tftp-server-name", "boot-file-name", "routers"}


def _kea_shaped_test(config_path):
    """Stands in for `kea-dhcp4 -t`, which a test cannot run: follows the includes from the
    copy of Kea's main file down to the candidate, and holds it to a reservation list's shape."""
    import re

    def includes(path):
        return re.findall(r'<\?include "([^"]+)"\?>', open(path, encoding="utf-8").read())

    [middle] = includes(config_path)
    found = [p for p in includes(middle) if os.path.basename(p).startswith(".candidate-")]
    assert len(found) == 1, (middle, includes(middle))
    value = json.load(open(found[0], encoding="utf-8"))
    assert isinstance(value, list)
    for r in value:
        assert set(r) <= KEA_RESERVATION_KEYS, r
        assert {o["name"] for o in r["option-data"]} <= KEA_OPTION_NAMES, r
        assert all(isinstance(o["data"], str) and o["data"] for o in r["option-data"]), r
    return True, "Syntax check OK"


@pytest.fixture
def writer(kea_files, monkeypatch):
    kea = FakeKea({255: kea_files["direct"], 40: kea_files["relayed"]})
    monkeypatch.setattr(ztp, "kea_home", lambda n: {"owner": n, "fragment": kea_files["direct"],
                                                    "main_config": kea_files["main"]})
    records = []
    monkeypatch.setattr(ztp, "record_commit", lambda *a, **kw: records.append((a, kw)) or {
        "ok": True, "commit": "abc", "owner": "Lab", "error": ""})

    def write(adds=(), removes=()):
        return ztp.write_reservations(adds, removes, list_name="Lab", actor="op@example.com",
                                      kea=kea, run_test=_kea_shaped_test)
    return dict(kea_files, kea=kea, write=write, records=records)


def _read(path):
    return json.load(open(path, encoding="utf-8"))


class TestTheFragment:
    def test_a_relayed_reservation_lands_in_its_subnets_own_file(self, writer):
        entry = ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER)
        out = writer["write"]([entry])
        assert out["ok"] and out["outcomes"][MAC]["outcome"] == "written", out
        assert _read(writer["relayed"]) == [entry]
        assert _read(writer["direct"]) == [], "a relayed reservation in the direct fragment"
        assert writer["kea"].held[40] == [entry], "Kea's read-back of subnet 40"

    def test_a_direct_reservation_still_lands_in_the_network_fragment(self, writer):
        """Control: an address this host is on goes where P.6 put it."""
        entry = ztp.reservation_entry(DIRECT_MAC, DIRECT_ADDR, "dev-b", SERVER)
        out = writer["write"]([entry])
        assert out["ok"], out
        assert _read(writer["direct"]) == [entry] and _read(writer["relayed"]) == []

    def test_one_write_of_both_lands_each_in_its_own_file(self, writer):
        a = ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER)
        b = ztp.reservation_entry(DIRECT_MAC, DIRECT_ADDR, "dev-b", SERVER)
        out = writer["write"]([a, b])
        assert out["ok"], out
        assert _read(writer["relayed"]) == [a] and _read(writer["direct"]) == [b]

    def test_a_removal_goes_to_the_file_holding_its_mac(self, writer):
        writer["write"]([ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER)])
        out = writer["write"](removes=[MAC])
        assert out["ok"] and out["outcomes"][MAC]["outcome"] == "removed", out
        assert _read(writer["relayed"]) == []

    def test_the_record_is_taken_after_the_write_for_every_ztp_file(self, writer):
        writer["write"]([ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER)])
        assert len(writer["records"]) == 1, writer["records"]
        args, kw = writer["records"][0]
        assert args == ("Lab", writer["direct"]) and kw["main_config"] == writer["main"]

    def test_a_relayed_address_written_to_the_direct_fragment_is_refused(self, writer):
        """The placement guard: a write naming the direct fragment for a relayed address
        (no routing) is refused, naming the subnet."""
        out = ztp.write_reservations([ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER)],
                                     kea=writer["kea"], fragment=writer["direct"],
                                     main_config=writer["main"], run_test=_kea_shaped_test)
        assert out["outcomes"][MAC]["outcome"] == "refused"
        assert "declared relayed for ZTP" in out["outcomes"][MAC]["detail"]
        assert _read(writer["direct"]) == []

    def test_an_unreadable_subnet_file_refuses_the_routed_write(self, writer):
        with open(writer["subnets"], "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        out = writer["write"]([ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER)])
        assert not out["ok"] and "could not be read" in out["error"]
        assert _read(writer["relayed"]) == [] and _read(writer["direct"]) == []

    def test_fragments_names_every_ztp_file(self, kea_files):
        every, error = ztp.fragments(kea_files["direct"], kea_files["main"])
        assert error == "" and every == [(None, kea_files["direct"]), (40, kea_files["relayed"])]

    def test_an_undeclared_subnet_s_file_is_not_ztp_s(self, kea_files):
        """Control: without the declaration subnet 40's file is the DHCP page's."""
        from modules import dhcp_subnets as S
        subs = S.load(open(kea_files["subnets"], encoding="utf-8").read())
        subs[1].pop("user-context")
        with open(kea_files["subnets"], "w", encoding="utf-8") as fh:
            fh.write(S.dump(subs))
        assert ztp.fragments(kea_files["direct"], kea_files["main"])[0] == [
            (None, kea_files["direct"])]


class TestTheRecordHoldsEveryZtpFile:
    def test_relayed_rows_name_their_subnet_and_option_3(self, kea_files, monkeypatch):
        from modules import dhcp_reservations as D
        with open(kea_files["relayed"], "w", encoding="utf-8") as fh:
            json.dump([ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER, router=RELAY)], fh)
        with open(kea_files["direct"], "w", encoding="utf-8") as fh:
            json.dump([ztp.reservation_entry(DIRECT_MAC, DIRECT_ADDR, "dev-b", SERVER)], fh)
        seen = {}
        monkeypatch.setattr(D, "commit_in_owner", lambda ln, rel, text_for, msg, actor: (
            seen.update(text=text_for("Lab"), rel=rel) or {"ok": True}))
        assert ztp.record_commit("Lab", kea_files["direct"], message="m", actor="a",
                                 main_config=kea_files["main"])["ok"]
        import yaml
        rows = yaml.safe_load(seen["text"])["reservations"]
        assert rows == [
            {"mac": DIRECT_MAC, "address": DIRECT_ADDR, "hostname": "dev-b", "server": SERVER,
             "file": "dev-b.cfg"},
            {"mac": MAC, "address": DEVICE, "hostname": "dev-a", "server": SERVER,
             "file": "dev-a.cfg", "relayed_subnet": 40, "router": RELAY}]


class TestTheDhcpPageLeavesItToZtp:
    def test_a_reservation_on_the_dhcp_page_in_a_relayed_ztp_subnet_is_refused(self, kea_files,
                                                                                 monkeypatch):
        from modules import dhcp_reservations as D

        class Kea(FakeKea):
            def is_configured(self):
                return True

        kea = Kea({255: kea_files["direct"], 40: kea_files["relayed"]})
        monkeypatch.setattr(D, "main_config", lambda ln, fam: kea_files["main"])
        monkeypatch.setattr(D, "_ztp_fragment", lambda ln: "")
        p = D.plan("Lab", {"op": "add", "family": "IPv4", "subnet": "40", "key": "hw-address",
                           "identity": MAC, "address": DEVICE}, kea=kea)
        assert not p["ok"] and "is a relayed ZTP subnet" in p["refused"], p

    def test_the_dhcp_page_s_record_leaves_out_relayed_ztp_files(self, kea_files, monkeypatch):
        from modules import dhcp_reservations as D
        with open(kea_files["relayed"], "w", encoding="utf-8") as fh:
            json.dump([ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER)], fh)
        other = os.path.join(os.path.dirname(kea_files["direct"]), "reservations-20.json")
        with open(other, "w", encoding="utf-8") as fh:
            json.dump([{"hw-address": "aa:bb:cc:00:20:01", "ip-address": "192.0.2.201"}], fh)
        monkeypatch.setattr(D, "main_config", lambda ln, fam: kea_files["main"])
        monkeypatch.setattr(D, "_ztp_fragment", lambda ln: kea_files["direct"])
        held = D.held_by_mercury("Lab")
        assert [r["subnet"] for r in held] == [20], held

    def test_the_reader_names_a_declared_subnet_ztp_s(self):
        from modules.readers.dhcp import _ztp_ids
        assert 40 in _ztp_ids(_dhcp4(_relayed_subnet()))
        assert 40 not in _ztp_ids(_dhcp4(_relayed_subnet(declared=False)))


class TestTheSubnetIsDeclaredAtAdd:
    """The DHCP page's Add, the one write path for subnets, carries the declaration."""

    def _plan(self, kea_files, monkeypatch, intent, **ask):
        from modules import dhcp_reservations as D
        from modules import dhcp_subnets as S

        class Kea(FakeKea):
            pass
        kea = Kea({255: kea_files["direct"], 40: kea_files["relayed"]})
        monkeypatch.setattr(D, "main_config", lambda ln, fam: kea_files["main"])
        values = {"op": "add", "family": "IPv4", "prefix": "198.51.100.4/30",
                  "pool": "198.51.100.6 - 198.51.100.6", "ztp": "1"}
        values.update(ask)
        return S.plan("Lab", values, kea=kea, intent=intent)

    @staticmethod
    def _intent(relays=(SERVER,)):
        return {"IPv4": {"198.51.100.4/30": [
            {"device": "relay-b", "iface": "GigabitEthernet2", "address": "198.51.100.5",
             "relays": list(relays), "gateway": ["198.51.100.5"]}]}, "IPv6": {}}

    def test_for_ztp_it_carries_the_declaration_and_the_relay_and_no_gateway(self, kea_files,
                                                                             monkeypatch):
        p = self._plan(kea_files, monkeypatch, self._intent())
        assert p["ok"], p["refused"]
        assert p["after"].get("user-context") == {"mercury-ztp": "relayed"}
        assert p["after"].get("relay") == {"ip-addresses": ["198.51.100.5"]}
        assert "option-data" not in p["after"], "a gateway offered on a ZTP subnet (D4)"

    def test_without_it_the_gateway_comes_from_intent_and_nothing_is_declared(self, kea_files,
                                                                              monkeypatch):
        """Control: the same Add, not for ZTP, is board C's as before."""
        p = self._plan(kea_files, monkeypatch, self._intent(), ztp="")
        assert p["ok"], p["refused"]
        assert "user-context" not in p["after"]
        assert {"name": "routers", "data": "198.51.100.5", "space": "dhcp4"} in \
            p["after"].get("option-data", [])

    def test_the_declaration_is_in_the_hash(self, kea_files, monkeypatch):
        a = self._plan(kea_files, monkeypatch, self._intent())
        b = self._plan(kea_files, monkeypatch, self._intent(), ztp="")
        assert a["hash"] != b["hash"]

    def test_a_gateway_or_dns_on_a_ztp_subnet_is_refused(self, kea_files, monkeypatch):
        for field in ({"gateway": "198.51.100.5"}, {"dns": "192.0.2.53"}):
            p = self._plan(kea_files, monkeypatch, self._intent(), **field)
            assert not p["ok"] and "no gateway or DNS option (D4)" in p["refused"]

    def test_a_prefix_whose_relay_mercury_does_not_manage_is_refused(self, kea_files,
                                                                      monkeypatch):
        p = self._plan(kea_files, monkeypatch, {"IPv4": {}, "IPv6": {}})
        assert not p["ok"] and "no device Mercury manages" in p["refused"]

    def test_an_ipv6_subnet_for_ztp_is_refused_by_name(self, kea_files, monkeypatch):
        """IPv6's twin of the first test above: the same Add, for ZTP, of an IPv6 prefix."""
        from modules import dhcp_reservations as D
        from modules import dhcp_subnets as S

        class Kea6:
            def command(self, command, service=None):
                assert command == "config-get" and service == ["dhcp6"], (command, service)
                return {"ok": True, "result": [{"arguments": {"Dhcp6": {"subnet6": []}}}]}
        monkeypatch.setattr(D, "main_config", lambda ln, fam: kea_files["main"])
        intent = {"IPv4": {}, "IPv6": {"2001:db8:4::/64": [
            {"device": "relay-b", "iface": "GigabitEthernet2", "address": "2001:db8:4::1",
             "relays": ["2001:db8::10"]}]}}
        p = S.plan("Lab", {"op": "add", "family": "IPv6", "prefix": "2001:db8:4::/64",
                           "pool": "2001:db8:4::10 - 2001:db8:4::20", "ztp": "1"},
                   kea=Kea6(), file_text="[]\n", intent=intent)
        assert not p["ok"] and "IPv6" in p["refused"] and "C1245" in p["refused"], p
        # Control: the same IPv6 Add, not for ZTP, is board C's.
        ok = S.plan("Lab", {"op": "add", "family": "IPv6", "prefix": "2001:db8:4::/64",
                            "pool": "2001:db8:4::10 - 2001:db8:4::20"},
                    kea=Kea6(), file_text="[]\n", intent=intent)
        assert ok["ok"], ok["refused"]


# ── 3. option 3: the relay's own address and nothing else ─────────────────────────────────

class TestOptionThree:
    def test_the_entry_carries_option_3_only_when_chosen(self):
        assert "routers" not in {o["name"] for o in
                                 ztp.reservation_entry(MAC, DEVICE, "d", SERVER)["option-data"]}
        opts = {o["name"]: o["data"] for o in
                ztp.reservation_entry(MAC, DEVICE, "d", SERVER, router=RELAY)["option-data"]}
        assert opts["routers"] == RELAY

    def test_the_writer_accepts_the_relays_own_address(self, writer):
        out = writer["write"]([ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER,
                                                     router=RELAY)])
        assert out["ok"] and out["outcomes"][MAC]["outcome"] == "written", out

    def test_the_writer_refuses_any_other_routers_value_naming_both(self, writer):
        out = writer["write"]([ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER,
                                                     router="198.51.100.3")])
        detail = out["outcomes"][MAC]["detail"]
        assert out["outcomes"][MAC]["outcome"] == "refused"
        assert "routers 198.51.100.3" in detail and RELAY in detail
        assert _read(writer["relayed"]) == []

    def test_option_3_on_the_subnet_this_host_is_on_is_still_refused(self, writer):
        """Control: D4 as decided holds on the directly attached subnet."""
        out = writer["write"]([ztp.reservation_entry(DIRECT_MAC, DIRECT_ADDR, "dev-b", SERVER,
                                                     router="192.0.2.1")])
        assert out["outcomes"][DIRECT_MAC]["outcome"] == "refused"
        assert "routers" in out["outcomes"][DIRECT_MAC]["detail"]

    def test_routers_at_the_relayed_subnet_level_is_still_d4(self):
        dhcp4 = _dhcp4(dict(_relayed_subnet(), **{"option-data": [{"name": "routers",
                                                                   "data": RELAY}]}))
        assert ztp.forbidden_options(dhcp4, DEVICE, RELAY) == [("subnet 40", "routers")]

    def test_another_reservations_chosen_option_3_is_not_a_breach(self):
        other = ztp.reservation_entry("aa:bb:cc:00:04:03", "198.51.100.2", "o", SERVER,
                                      router=RELAY)
        dhcp4 = _dhcp4(_relayed_subnet(reservations=[other]))
        assert ztp.forbidden_options(dhcp4, DEVICE, RELAY) == []
        # Control: without the relay address (P.6's call) it is reported, as before.
        assert ztp.forbidden_options(dhcp4, DEVICE) == [
            ("reservation aa:bb:cc:00:04:03", "routers")]

    def test_a_dns_option_in_a_relayed_reservation_is_refused(self, writer):
        entry = ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER)
        entry["option-data"].append({"name": "domain-name-servers", "data": "192.0.2.53"})
        out = writer["write"]([entry])
        assert out["outcomes"][MAC]["outcome"] == "refused"
        assert "domain-name-servers" in out["outcomes"][MAC]["detail"]


class TestTheChoiceInThePlan:
    RELAYED_CHECK = {"ok": True, "reasons": [], "server": SERVER, "subnet_id": 40,
                     "dns": {"state": "silent", "measured_at": 1.0}, "relayed": True,
                     "relay": {"device": "relay-a", "iface": "GigabitEthernet3",
                               "address": RELAY}}
    DIRECT_CHECK = {"ok": True, "reasons": [], "server": SERVER, "subnet_id": 255, "dns": {},
                    "relayed": False, "relay": {}}

    def test_off_by_default(self):
        from modules.nsot.onboard import ztp_relayed_choice
        got = ztp_relayed_choice(self.RELAYED_CHECK, "", RELAY)
        assert got["router"] == "" and got["reasons"] == []
        assert got["relay"] == f"relay-a GigabitEthernet3 ({RELAY})"

    def test_chosen_it_is_the_relays_own_address(self):
        from modules.nsot.onboard import ztp_relayed_choice
        assert ztp_relayed_choice(self.RELAYED_CHECK, "relay", RELAY)["router"] == RELAY

    def test_chosen_on_the_subnet_this_host_is_on_it_is_refused(self):
        from modules.nsot.onboard import ztp_relayed_choice
        got = ztp_relayed_choice(self.DIRECT_CHECK, "relay", "")
        assert got["router"] == "" and "offered only on a relayed ZTP subnet" in _said(got)

    def test_an_unknown_choice_is_refused(self):
        from modules.nsot.onboard import ztp_relayed_choice
        assert "not one of" in _said(ztp_relayed_choice(self.RELAYED_CHECK, "192.0.2.1", RELAY))

    def test_behind_a_relay_the_gateway_must_be_the_relay(self):
        from modules.nsot.onboard import ztp_relayed_choice
        assert "no gateway given" in _said(ztp_relayed_choice(self.RELAYED_CHECK, "", ""))
        why = _said(ztp_relayed_choice(self.RELAYED_CHECK, "", "198.51.100.3"))
        assert "198.51.100.3" in why and RELAY in why
        # Control: the relay's own address is the gateway, and nothing is refused.
        assert _said(ztp_relayed_choice(self.RELAYED_CHECK, "", RELAY)) == ""

    def test_the_choice_is_in_the_preview_s_hash(self, tmp_path, monkeypatch):
        from modules.nsot import onboard
        import modules.settings_schema as ss
        real = ss.get_setting
        monkeypatch.setattr(ss, "get_setting", lambda k, *a, **kw: (
            "192.0.2.10" if k == "syslog_host" else real(k, *a, **kw)))
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr(onboard, "_name_in_manifest", lambda *a: (False, True))
        monkeypatch.setattr(onboard, "_name_in_netbox", lambda *a: (False, True))

        def plan(choice):
            return onboard.build_plan(
                hostname="dev-a", platform="cisco_iosxe", list_name="probe", secret="S3cret12",
                manager_interface="Gi2", address_source="ztp", mgmt_mac=MAC, mgmt_ip=DEVICE,
                manager_gateway=RELAY, role="router", ztp_router=choice,
                ztp_check=lambda m, a, kea=None, list_name="": dict(self.RELAYED_CHECK))
        none, chosen = plan(""), plan("relay")
        assert none.onboardable and chosen.onboardable, chosen.blocking_reasons
        assert none.summary["ztp_router"] == "" and chosen.summary["ztp_router"] == RELAY
        assert onboard.plan_shown(none) != onboard.plan_shown(chosen)
        assert "with no option 3" in none.address_claim
        assert f"offering option 3 (routers) {RELAY}" in chosen.address_claim
        assert f"ip route 0.0.0.0 0.0.0.0 {RELAY}" in chosen.bootstrap_config

    def test_the_reserve_step_writes_the_chosen_option_3(self):
        from modules.nsot import onboard
        seen = {}

        class P:
            mgmt_mac, reservation_address, hostname, list_name = MAC, DEVICE, "dev-a", "probe"
            ztp_router = RELAY

        def write(adds, kea=None, list_name="", actor="", message=""):
            seen["entry"] = adds[0]
            return {"ok": True, "outcomes": {MAC: {"outcome": "written", "detail": ""}}}
        onboard.reserve_step(P(), check=lambda *a, **k: dict(self.RELAYED_CHECK), write=write)
        assert {o["name"]: o["data"] for o in seen["entry"]["option-data"]}["routers"] == RELAY

    def test_a_relay_that_moved_since_the_preview_refuses_the_write(self):
        from modules.nsot import onboard
        moved = dict(self.RELAYED_CHECK, relay=dict(self.RELAYED_CHECK["relay"],
                                                    address="198.51.100.3"))

        class P:
            mgmt_mac, reservation_address, hostname, list_name = MAC, DEVICE, "dev-a", "probe"
            ztp_router = RELAY
        written = []
        with pytest.raises(RuntimeError, match="198.51.100.3"):
            onboard.reserve_step(P(), check=lambda *a, **k: moved,
                                 write=lambda *a, **k: written.append(1))
        assert written == []


# ── 4. DNS on the relayed segment ─────────────────────────────────────────────────────────

RELAY_FACT = {"device": "relay-a", "iface": "GigabitEthernet3", "address": RELAY,
              "relays": [SERVER, "192.0.2.20"], "network": "Lab"}


class TestDnsOnTheRelayedSegment:
    def test_all_helper_targets_silent_and_no_dns_server_is_silent(self):
        got = ztp_relayed.dns_posture(SERVER, RELAY_FACT, GOLDEN, probe=_silent)
        assert got["state"] == "silent" and got["probed"] == {SERVER: "silent",
                                                             "192.0.2.20": "silent"}

    def test_a_helper_target_that_answers_is_named(self):
        got = ztp_relayed.dns_posture(SERVER, RELAY_FACT, GOLDEN, probe=lambda t, s: {
            "state": "answered" if t == "192.0.2.20" else "silent", "error": ""})
        assert got["state"] == "answered" and "192.0.2.20" in got["answerers"][0]

    def test_the_relay_running_a_dns_server_is_named(self):
        golden = {"text": GOLDEN["text"] + "ip dns server\n", "refused": ""}
        got = ztp_relayed.dns_posture(SERVER, RELAY_FACT, golden, probe=_silent)
        assert got["state"] == "answered" and "relay-a (ip dns server" in got["answerers"][0]

    def test_an_unreadable_golden_is_unknown_never_silent(self):
        got = ztp_relayed.dns_posture(SERVER, RELAY_FACT,
                                      {"text": None, "refused": "never committed"},
                                      probe=_silent)
        assert got["state"] == "unknown" and "never committed" in got["error"]

    def test_a_probe_that_could_not_be_sent_is_unknown(self):
        got = ztp_relayed.dns_posture(SERVER, RELAY_FACT, GOLDEN, probe=lambda t, s: {
            "state": "unknown", "error": f"{t}: refused by the test"})
        assert got["state"] == "unknown" and "refused by the test" in got["error"]

    def test_the_relay_s_golden_is_read_as_committed_and_creates_no_list(self, tmp_path,
                                                                        monkeypatch):
        from modules import config
        from modules.nsot import manifest
        from modules.nsot import repo as R
        monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
        got = ztp_relayed.relay_golden(dict(RELAY_FACT, network="Nowhere"))
        assert got["text"] is None and "no network named 'Nowhere'" in got["refused"]
        assert not (tmp_path / "lists").exists(), "a read created a list folder"
        seen = {}
        monkeypatch.setattr("modules.nsot.listref.exists", lambda name: True)
        monkeypatch.setattr("modules.nsot.listref.resolve",
                            lambda name: type("Ref", (), {"repo_dir": "/repo"})())
        monkeypatch.setattr(manifest, "find_by_name",
                            lambda repo, name: ("id-1", {"name": name, "golden": "x"}))
        monkeypatch.setattr(R, "committed_golden_for", lambda repo, entry: seen.update(
            repo=repo, entry=entry) or {"text": "ip dns server\n", "refused": ""})
        got = ztp_relayed.relay_golden(RELAY_FACT)
        assert got["text"] == "ip dns server\n" and seen["repo"] == "/repo"
        assert seen["entry"]["name"] == "relay-a"

    def test_the_golden_s_dns_lines_are_read(self):
        assert ztp_relayed.relay_dns_lines("ip dns server\n") == {"dns_server": True,
                                                                  "forwards_dns": True}
        assert ztp_relayed.relay_dns_lines("no ip forward-protocol udp domain\n") == {
            "dns_server": False, "forwards_dns": False}
        assert ztp_relayed.relay_dns_lines(" ip dns server\n")["dns_server"] is False, \
            "an indented line is not the global command"

    def test_a_dns_answer_on_the_relayed_segment_fails_the_posture(self):
        got = ztp_relayed.posture(
            _dhcp4(_relayed_subnet()), _relayed_subnet(), address=DEVICE, addrs=ADDRS,
            **_seams(dns=lambda server, relay, golden: ztp_relayed.dns_posture(
                server, relay, golden, probe=lambda t, s: {"state": "answered", "error": ""})))
        assert any(r.startswith("D4: something answers DNS for the relayed ZTP segment")
                   for r in got["reasons"]), got


class TestTheUnicastProbeOverLoopback:
    """The real probe, against a loopback listener (the network guard allows loopback)."""

    def test_a_listener_that_answers_is_answered(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]

        def answer():
            data, peer = srv.recvfrom(512)
            srv.sendto(data[:2] + b"\x81\x83" + data[4:], peer)     # NXDOMAIN, same id
        t = threading.Thread(target=answer, daemon=True)
        t.start()

        class Sock(socket.socket):
            def sendto(self, data, addr):                            # to the listener's port
                return super().sendto(data, (addr[0], port))
        try:
            got = ztp_relayed.unicast_answers("127.0.0.1", "127.0.0.1", timeout=2.0,
                                              sock_factory=lambda: Sock(socket.AF_INET,
                                                                        socket.SOCK_DGRAM))
        finally:
            t.join(3)
            srv.close()
        assert got["state"] == "answered", got

    def test_nothing_listening_is_silent(self):
        free = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()

        class Sock(socket.socket):
            def sendto(self, data, addr):
                return super().sendto(data, (addr[0], port))
        got = ztp_relayed.unicast_answers("127.0.0.1", "127.0.0.1", timeout=0.6,
                                          sock_factory=lambda: Sock(socket.AF_INET,
                                                                    socket.SOCK_DGRAM))
        assert got["state"] == "silent", got

    def test_a_source_this_host_does_not_have_is_unknown(self):
        got = ztp_relayed.unicast_answers("127.0.0.1", "192.0.2.254", timeout=0.3)
        assert got["state"] == "unknown" and "could not be sent from 192.0.2.254" in got["error"]


class TestJobHealthRows:
    class Kea(TestThePostureEndToEnd.Kea):
        pass

    def _rows(self, dhcp4, firewall, **seams):
        return ztp.posture_rows(kea=self.Kea(dhcp4), addrs=ADDRS, get=lambda k, d="": "/f",
                                dns=lambda source: {"state": "silent", "measured_at": 1.0},
                                relayed=_seams(**seams), firewall=firewall)

    RECORD_OK = ({"state": "read", "admitted": ["192.0.2.0/24", RELAYED], "read_at": "T",
                  "interface": "ztp0", "error": ""}, "/r")

    def _units(self, dhcp4, firewall, **seams):
        """``{unit: row}``, holding every relayed row's presence to an assertion."""
        rows = {r["unit"]: r for r in self._rows(dhcp4, firewall, **seams)}
        for unit in ("ztp-posture:subnet-40", "ztp-firewall"):
            assert unit in rows, f"no {unit} row in {sorted(rows)}"
        return rows

    def test_a_relayed_subnet_has_its_own_row_and_the_firewall_row(self):
        rows = self._units(_dhcp4(_relayed_subnet()), self.RECORD_OK)
        assert rows["ztp-posture:subnet-40"]["state"] == "ok", rows
        assert "behind relay-a GigabitEthernet3" in rows["ztp-posture:subnet-40"]["detail"]
        assert rows["ztp-firewall"]["state"] == "ok"
        assert rows["ztp-posture:subnet-255"]["state"] == "ok"

    def test_dns_answering_on_the_relayed_segment_is_d4_violated(self):
        rows = self._units(
            _dhcp4(_relayed_subnet()), self.RECORD_OK,
            dns=lambda server, relay, golden: ztp_relayed.dns_posture(
                server, relay, golden, probe=lambda t, s: {"state": "answered", "error": ""}))
        assert rows["ztp-posture:subnet-40"]["state"] == "d4_violated"

    def test_a_dns_server_option_on_the_relayed_subnet_is_d4_violated(self):
        sub = dict(_relayed_subnet(), **{"option-data": [{"name": "domain-name-servers",
                                                          "data": "192.0.2.53"}]})
        rows = self._units(_dhcp4(sub), self.RECORD_OK)
        assert rows["ztp-posture:subnet-40"]["state"] == "d4_violated"
        assert "domain-name-servers" in rows["ztp-posture:subnet-40"]["detail"]

    def test_the_record_is_read_beside_the_ztp_fragment(self, tmp_path):
        fragment = tmp_path / "reservations-255.json"
        rows = {r["unit"]: r for r in ztp.posture_rows(
            kea=self.Kea(_dhcp4(_relayed_subnet())), addrs=ADDRS,
            get=lambda k, d="": str(fragment) if k == "kea_ztp_fragment" else d,
            dns=lambda source: {"state": "silent", "measured_at": 1.0}, relayed=_seams())}
        assert "ztp-firewall" in rows, sorted(rows)
        assert rows["ztp-firewall"]["state"] == "unknown"
        assert str(tmp_path / "ztp-firewall.json") in rows["ztp-firewall"]["detail"]
        (tmp_path / "ztp-firewall.json").write_text(json.dumps(
            {"read_at": "T", "interface": "ztp0", "admitted": [RELAYED]}))
        rows = {r["unit"]: r for r in ztp.posture_rows(
            kea=self.Kea(_dhcp4(_relayed_subnet())), addrs=ADDRS,
            get=lambda k, d="": str(fragment) if k == "kea_ztp_fragment" else d,
            dns=lambda source: {"state": "silent", "measured_at": 1.0}, relayed=_seams())}
        assert rows["ztp-firewall"]["state"] == "ok", rows["ztp-firewall"]

    def test_ztp_not_configured_no_rows_at_all(self):
        """Control: an empty fragment is its own unset row elsewhere; nothing here."""
        assert ztp.posture_rows(kea=self.Kea(_dhcp4(_relayed_subnet())), addrs=ADDRS,
                                get=lambda k, d="": "", relayed=_seams()) == []

    def test_no_relayed_subnet_no_relayed_rows(self):
        """Control: P.6's rows alone, and no firewall row."""
        units = [r["unit"] for r in self._rows(_dhcp4(), self.RECORD_OK)]
        assert units == ["ztp-posture:subnet-255"]

    def test_an_ipv6_relayed_subnet_is_named(self):
        sub = _relayed_subnet(prefix="2001:db8:4::/64", relay=("2001:db8:4::1",))
        rows = self._units(_dhcp4(sub), self.RECORD_OK)
        assert "IPv6" in rows["ztp-posture:subnet-40"]["detail"]
        assert rows["ztp-posture:subnet-40"]["state"] != "ok"


# ── 5. the firewall ────────────────────────────────────────────────────────────────────────

#: `ufw status`'s table (To, Action, From), the shape the responder's rule in
#: docs/DEPLOY_LINUX.md prints; the host step's `check` reads the real one back and fails
#: loudly if it does not parse.
UFW_STATUS = """Status: active

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW       Anywhere
69/udp on ztp0             ALLOW       192.0.2.0/24               # NMAS ZTP responder (P.6)
69/udp on ztp0             ALLOW       198.51.100.0/30            # NMAS ZTP responder, relayed subnet (C1346)
69/udp on lan0             ALLOW       198.51.100.4/30
22/tcp (v6)                ALLOW       Anywhere (v6)
"""


class TestTheFirewall:
    def test_the_admitted_sources_on_the_responder_s_interface_are_read(self):
        assert ztp_relayed.parse_ufw_status(UFW_STATUS, "ztp0") == ["192.0.2.0/24", RELAYED]

    def test_a_rule_on_another_interface_does_not_admit(self):
        assert not ztp_relayed.admitted("198.51.100.4/30",
                                        ztp_relayed.parse_ufw_status(UFW_STATUS, "ztp0"))

    def test_a_wider_source_admits_a_subnet_inside_it(self):
        assert ztp_relayed.admitted(RELAYED, ["198.51.100.0/24"])
        assert ztp_relayed.admitted(RELAYED, ["0.0.0.0/0"])

    def test_every_declared_subnet_admitted_is_ok(self):
        row = ztp_relayed.firewall_row([(40, RELAYED)], {
            "state": "read", "admitted": [RELAYED], "read_at": "2026-10-19T00:00:00Z",
            "interface": "ztp0", "error": ""}, "/r")
        assert row["state"] == "ok" and "2026-10-19T00:00:00Z" in row["detail"]

    def test_a_declared_subnet_not_admitted_is_named(self):
        row = ztp_relayed.firewall_row([(40, RELAYED), (41, "198.51.100.4/30")], {
            "state": "read", "admitted": [RELAYED], "read_at": "T", "interface": "ztp0",
            "error": ""}, "/r")
        assert row["state"] == "firewall_closed" and "subnet 41 (198.51.100.4/30)" in \
            row["detail"] and "subnet 40" not in row["detail"]
        assert ztp_relayed.FIREWALL_STEP in row["detail"]

    def test_absent_and_unreadable_are_different_states(self, tmp_path):
        absent = ztp_relayed.read_firewall_record(str(tmp_path / "none.json"))
        bad = tmp_path / "bad.json"
        bad.write_text("{ not json")
        unreadable = ztp_relayed.read_firewall_record(str(bad))
        assert absent["state"] == "absent" and unreadable["state"] == "unreadable"
        a = ztp_relayed.firewall_row([(40, RELAYED)], absent, "/r")
        u = ztp_relayed.firewall_row([(40, RELAYED)], unreadable, "/r")
        assert a["state"] == u["state"] == "unknown"
        assert "is absent" in a["detail"] and ztp_relayed.FIREWALL_STEP in a["detail"]
        assert "could not be read" in u["detail"] and "is absent" not in u["detail"]

    def test_the_record_written_reads_back(self, tmp_path):
        path = tmp_path / "ztp-firewall.json"
        path.write_text(json.dumps({"read_at": "T", "interface": "ztp0",
                                    "admitted": [RELAYED]}))
        got = ztp_relayed.read_firewall_record(str(path))
        assert got["state"] == "read" and got["admitted"] == [RELAYED]

    def test_the_responder_interface_is_read_from_its_socket_unit(self, tmp_path):
        unit = tmp_path / "nmas-ztp-responder.socket"
        unit.write_text("[Socket]\nListenDatagram=69\nBindToDevice=ztp0\n")
        assert ztp_relayed.responder_interface(str(unit)) == "ztp0"
        assert ztp_relayed.responder_interface(str(tmp_path / "absent")) == ""

    def test_the_host_step_admits_each_prefix_and_feeds_ufw_status_to_the_tool(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        text = open(os.path.join(root, "scripts", "host-steps",
                                 "c1346-ztp-relayed-firewall.sh"), encoding="utf-8").read()
        assert "sudo ufw allow in on '$IFACE' proto udp from \\\"\\$p\\\" to any port 69" in text
        # Parenthesised: `a | cd x && python` would give the pipe to cd, not to the tool.
        assert "sudo ufw status | ( $TOOL check )" in text
        assert "sudo ufw status | ( $TOOL record )" in text
        assert "| $TOOL" not in text


# ── 6. the discovery classes ──────────────────────────────────────────────────────────────

def test_the_discovery_classes_never_match_a_relayed_or_reserved_client():
    """Left as they are, said so: a relayed DISCOVER carries a giaddr, and a reserved client is
    KNOWN, so neither discovery class matches a relayed ZTP device."""
    from modules import dhcp_discovery
    for c in dhcp_discovery.classes("ztp0"):
        assert "pkt4.giaddr == 0.0.0.0" in c["test"] and "not member('KNOWN')" in c["test"]


# ── 7. the responder serves a routed peer ─────────────────────────────────────────────────

class TestTheResponderServesARoutedPeer:
    CONFIG = "hostname dev-a\n"

    def _homes(self, kea_files, monkeypatch):
        monkeypatch.setattr("modules.device.get_device_lists", lambda: [{"name": "Lab"}])
        monkeypatch.setattr(ztp, "kea_home", lambda n: {"owner": n,
                                                        "fragment": kea_files["direct"],
                                                        "main_config": kea_files["main"]})

    def _pending(self, ip=DEVICE, mac=MAC):
        return lambda: [("Lab", "/repo", {"name": "dev-a", "reserved_address": ip,
                                          "mgmt_mac": mac, "address_source": "ztp"})]

    def test_the_relayed_file_is_read_and_its_device_served_at_its_routed_address(
            self, kea_files, monkeypatch):
        from modules.nsot import ztp_responder as r
        with open(kea_files["relayed"], "w", encoding="utf-8") as fh:
            json.dump([ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER)], fh)
        self._homes(kea_files, monkeypatch)
        assert r._fragment_paths() == {kea_files["direct"]: ["Lab"],
                                       kea_files["relayed"]: ["Lab"]}
        d = r.decide(DEVICE, "dev-a.cfg", pending=self._pending(),
                     artifact=lambda repo, host: {"ok": True, "config": self.CONFIG})
        assert d["serve"] and d["device"] == "dev-a", d

    def test_a_routed_peer_arriving_v4_mapped_is_the_reserved_address(self):
        from modules.nsot import ztp_responder as r
        host, reply, family = r.normalise_peer((f"::ffff:{DEVICE}", 1234, 0, 0))
        assert (host, reply, family) == (DEVICE, (DEVICE, 1234), socket.AF_INET)

    def test_a_reservation_in_an_undeclared_subnet_s_file_is_not_served(self, kea_files,
                                                                         monkeypatch):
        """Control: the DHCP page's file for a subnet is not ZTP's, so the responder never
        reads it, and a device reserved there is not served."""
        from modules import dhcp_subnets as S
        from modules.nsot import ztp_responder as r
        subs = S.load(open(kea_files["subnets"], encoding="utf-8").read())
        subs[1].pop("user-context")
        with open(kea_files["subnets"], "w", encoding="utf-8") as fh:
            fh.write(S.dump(subs))
        with open(kea_files["relayed"], "w", encoding="utf-8") as fh:
            json.dump([ztp.reservation_entry(MAC, DEVICE, "dev-a", SERVER)], fh)
        self._homes(kea_files, monkeypatch)
        d = r.decide(DEVICE, "dev-a.cfg", pending=self._pending(),
                     artifact=lambda repo, host: {"ok": True, "config": self.CONFIG})
        assert not d["serve"] and "holds no reservation the tool wrote" in d["reason"]

    def test_an_unreadable_subnet_file_is_named_in_the_refusal(self, kea_files, monkeypatch):
        from modules.nsot import ztp_responder as r
        with open(kea_files["subnets"], "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        self._homes(kea_files, monkeypatch)
        d = r.decide(DEVICE, "dev-a.cfg", pending=self._pending(),
                     artifact=lambda repo, host: {"ok": True, "config": self.CONFIG})
        assert not d["serve"] and "relayed ZTP subnets of Lab" in d["reason"], d


def test_the_dns_query_is_the_rfc_6761_name():
    """The probe asks a name nothing resolves, as P.6's broadcast probe does."""
    _qid, query = ztp_relayed._dns_query(ztp.DNS_PROBE_NAME)
    assert b"\x0enmas-ztp-probe\x07invalid\x00" in query
    assert struct.unpack(">H", query[2:4])[0] == 0x0100
