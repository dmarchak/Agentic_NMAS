"""Out-of-band ZTP's STATIC path (C1592 to C1594; the operator's decisions of 2026-10-23):
the address source ``ztp_console`` from the plan to the kick-start, and the responder's gate.

- the plan (`onboard.build_plan`): the planned static address, mask and gateway kept; NO Kea
  (no subnet, no reservation, no MAC asked); the gateway the relay's own address and the config
  server the relay's helper target that is this host's (`ztp_relayed.console_plan`, from
  committed intent); IPv6 refused by name (C1245);
- the bootstrap: static on the management SVI, ``ip default-gateway`` AND
  ``ip route 0.0.0.0 0.0.0.0`` on the switch (a blank vIOS-L2 routes, so it ignores its default
  gateway: measured on s5, 2026-10-23, C1606; the operator's choice, both lines), and its
  re-render byte-identical;
- the pending intent: the bootstrap block static, its server, the default gateway and the
  route in the parsers' keys;
- the kick-start's parameters derived from that onboarding, the preview's refusals, and the
  run over the fake console (tests/console_fakes.py, s5's real text): it types the static
  lines, stops at a refusal (C1593's own), reads back and compares, records the MAC in use,
  and copies the bootstrap, verified; every failure kind of the copy; a silence shorter than
  the copy's bound (key generation, measured 39.5 s on vIOS-L2) is not a failure;
- the responder's gate (`ztp_responder.console_gate`), in the 0-survivor blocking set: served
  only to the planned static address of exactly one pending ``ztp_console`` device, for its own
  boot file, while it is held by its console run; everything else refused, named.

Documentation addresses (RFC 5737) throughout."""

import os
import socket

import pytest

from modules.nsot import console_kickstart as K
from modules.nsot import console_profiles as P
from modules.nsot import console_session as S
from modules.nsot import console_survey as V
from modules.nsot import console_ztp as Z
from modules.nsot import onboard, ztp, ztp_relayed, ztp_responder
from tests.console_ios import copy_answers, read_index
from tests.test_console_session import PNP
from tests.test_console_ztp import (ACTOR, COPY, FAST, LIST, ONBOARDING, PARAMS, PLANNED, World,
                                    _recorded_as_sent, after_lines, blank_answers, kick_answers)
from tests.test_onboard_plan import lab  # noqa: F401 - the fixture

ADDRESS, MASK, GATEWAY, SERVER = "192.0.2.14", "255.255.255.252", "192.0.2.13", "192.0.2.10"
LINK = "192.0.2.12/30"
FACTS = {"IPv4": {LINK: [{"device": "r8", "iface": "GigabitEthernet3", "address": GATEWAY,
                          "relays": [SERVER], "network": "Lab"}]}, "errors": []}
ADDRS = {"ens18": [SERVER], "lo": ["127.0.0.1"]}
FAMILIES = pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6],
                                   ids=["ipv4", "ipv6"])


def _ok_console(address, gateway):
    return ztp_relayed.console_plan(address, gateway, facts=FACTS, addrs=ADDRS)


def _plan(**over):
    args = dict(hostname="s5", platform="cisco_ios", list_name="probe", mgmt_ip=ADDRESS,
                mgmt_mask=MASK, manager_interface="Vlan1", manager_gateway=GATEWAY,
                secret="bootstrap-only", role="switch", address_source=ztp.ZTP_CONSOLE,
                console_check=_ok_console)
    args.update(over)
    return onboard.build_plan(**args)


# ── The plan: static, no Kea ──────────────────────────────────────────────────────────────

class TestThePlan:
    def test_a_static_plan_is_onboardable_with_no_mac_and_no_reservation(self, lab):
        plan = _plan()
        assert plan.onboardable, plan.blocking_reasons
        assert (plan.mgmt_ip, plan.mgmt_mask, plan.manager_gateway) == (ADDRESS, MASK, GATEWAY)
        assert plan.mgmt_mac == "" and plan.reservation_state == ""
        assert plan.reservation_address == "" and plan.ztp_subnet_add == {}
        assert plan.ztp_server == SERVER and plan.ztp_relay == f"r8 GigabitEthernet3 ({GATEWAY})"

    def test_the_claim_says_static_and_no_kea(self, lab):
        claim = _plan().address_claim
        assert claim.startswith(f"Out-of-band (console), STATIC: {ADDRESS} {MASK} on Vlan1, "
                                f"default gateway {GATEWAY} (the relay r8 GigabitEthernet3 "
                                f"({GATEWAY})). No Kea subnet or reservation")
        assert f"copies s5.cfg from the responder at {SERVER}" in claim
        assert "reasons it cannot be onboarded" not in claim

    def test_the_bootstrap_is_static_with_its_default_gateway_and_its_route(self, lab):
        config = _plan().bootstrap_config
        lines = config.splitlines()
        i = lines.index("interface Vlan1")
        assert lines[i:i + 4] == ["interface Vlan1",
                                  " description NMAS management - manager is on this subnet",
                                  f" ip address {ADDRESS} {MASK}", " no shutdown"]
        assert f"ip default-gateway {GATEWAY}" in lines
        assert [l for l in lines if l.startswith("ip route")] == [
            f"ip route 0.0.0.0 0.0.0.0 {GATEWAY}"]
        assert "ip address dhcp" not in config.replace(" ip address dhcp\n negotiation", "")
        assert " no switchport" not in lines[i:i + 4]
        assert "crypto key generate rsa modulus 2048" in lines, "nothing else makes its key"

    @pytest.mark.parametrize("over", [dict(role="router"),
                                      dict(address_source="static")])
    def test_a_router_and_the_static_source_keep_their_route(self, lab, over):
        """Controls: a router and the static source carry C1349's route, as the out-of-band
        switch now does too (C1606)."""
        lines = _plan(**over).bootstrap_config.splitlines()
        assert f"ip route 0.0.0.0 0.0.0.0 {GATEWAY}" in lines
        assert f"ip default-gateway {GATEWAY}" in lines

    @pytest.mark.parametrize("source,role,route", [
        ("ztp_console", "switch", True), ("ztp_console", " Switch ", True),
        ("ztp_console", "router", True), ("ztp_console", "", True), ("ztp", "switch", True),
        ("static", "switch", True), ("dhcp", "switch", True)])
    def test_which_bootstrap_routes_its_gateway(self, source, role, route):
        assert onboard.gateway_route(source, role) is route

    def test_the_check_s_reasons_block_the_plan(self, lab):
        plan = _plan(console_check=lambda a, g: {"relay": {}, "server": "",
                                                 "reasons": ["no relay for the test"]})
        assert not plan.onboardable and "no relay for the test" in plan.blocking_reasons
        assert "(the reasons it cannot be onboarded yet are above)" in plan.address_claim

    def test_a_check_that_raised_has_not_passed(self, lab):
        def boom(a, g):
            raise OSError("intent unreadable")
        plan = _plan(console_check=boom)
        assert ("the out-of-band check could not run: OSError: intent unreadable"
                in plan.blocking_reasons)

    @pytest.mark.parametrize("missing,said", [
        ("mgmt_ip", "no management address: an out-of-band (console) onboarding types"),
        ("mgmt_mask", "no network mask for 192.0.2.14: an out-of-band"),
        ("manager_gateway", "no gateway: an out-of-band (console) onboarding types")])
    def test_the_address_mask_and_gateway_are_each_required(self, lab, missing, said):
        plan = _plan(**{missing: ""})
        assert any(r.startswith(said) for r in plan.blocking_reasons), plan.blocking_reasons

    def test_an_ipv6_address_is_refused_by_name(self, lab):
        plan = _plan(mgmt_ip="2001:db8:4::14", console_check=None)
        assert any("is IPv6" in r and "C1245" in r for r in plan.blocking_reasons), \
            plan.blocking_reasons

    def test_it_never_reserves(self, lab):
        from tests.test_ztp_onboarding import _Steps
        steps = _Steps()
        out = onboard.run_onboarding(_plan(), **steps.kwargs())
        assert out["ok"] and "reserve" not in steps.order

    def test_the_preview_promises_no_kea_reservation(self, lab):
        """The review a person confirms says what Create makes: the static path writes no Kea
        reservation, so its summary must not promise one (the ``ztp`` source's, the control,
        does)."""
        from modules.preview_confirm import onboard_preview
        confirm = {"may": True, "actor": ACTOR, "kind": "person", "statement": "test"}
        plan = _plan()
        assert plan.onboardable, plan.blocking_reasons
        said = onboard_preview(plan.summary, plan.bootstrap_config, confirm)["what"]["summary"]
        assert said.startswith("Create s5 in probe"), said
        assert "Kea reservation" not in said, said
        control = onboard_preview(dict(plan.summary, address_source="ztp"),
                                  plan.bootstrap_config, confirm)["what"]["summary"]
        assert ", its Kea reservation" in control, control


class TestConsolePlan:
    """`ztp_relayed.console_plan`: the link, relay and server from committed intent and this
    host's addresses, never Kea."""

    def test_the_relay_and_the_server_are_derived(self):
        got = ztp_relayed.console_plan(ADDRESS, GATEWAY, facts=FACTS, addrs=ADDRS)
        assert got["reasons"] == [] and got["server"] == SERVER
        assert got["relay"]["device"] == "r8" and got["relay"]["address"] == GATEWAY

    def test_a_gateway_that_is_not_the_relay_is_named(self):
        got = ztp_relayed.console_plan(ADDRESS, "192.0.2.12", facts=FACTS, addrs=ADDRS)
        assert got["reasons"] == [f"the gateway 192.0.2.12 is not the relay's own address "
                                  f"{GATEWAY} (r8 GigabitEthernet3): the relay is the device's "
                                  "one neighbour toward this host"]
        got = ztp_relayed.console_plan(ADDRESS, "", facts=FACTS, addrs=ADDRS)
        assert got["reasons"][0].startswith("the gateway (none) is not")

    @pytest.mark.parametrize("addrs,found", [({"ens18": ["192.0.2.99"]}, 0),
                                             ({"a": [SERVER], "b": ["192.0.2.11"]}, 1)])
    def test_the_server_is_the_one_helper_this_host_has(self, addrs, found):
        facts = {"IPv4": {LINK: [dict(FACTS["IPv4"][LINK][0],
                                      relays=[SERVER, "192.0.2.11"])]}, "errors": []}
        got = ztp_relayed.console_plan(ADDRESS, GATEWAY, facts=facts, addrs=addrs)
        if found:
            assert got["reasons"] == [] or "found 2" in got["reasons"][0]
        else:
            assert got["server"] == "" and "found 0" in got["reasons"][0]

    def test_two_helpers_on_this_host_are_refused(self):
        facts = {"IPv4": {LINK: [dict(FACTS["IPv4"][LINK][0],
                                      relays=[SERVER, "192.0.2.11"])]}, "errors": []}
        got = ztp_relayed.console_plan(ADDRESS, GATEWAY, facts=facts,
                                       addrs={"a": [SERVER, "192.0.2.11"]})
        assert got["server"] == "" and "found 2: ['192.0.2.10', '192.0.2.11']" in \
            got["reasons"][0]

    def test_no_link_in_intent_is_named(self):
        got = ztp_relayed.console_plan(ADDRESS, GATEWAY, facts={"IPv4": {}, "errors": []},
                                       addrs=ADDRS)
        assert got["relay"] == {} and "no interface in committed intent" in got["reasons"][0]

    def test_ipv6_is_refused_by_name(self):
        got = ztp_relayed.console_plan("2001:db8:4::14", GATEWAY, facts=FACTS, addrs=ADDRS)
        assert "the address 2001:db8:4::14 is IPv6" in got["reasons"][0]
        assert "(C1245)" in got["reasons"][0]


# ── The pending intent and its re-render ──────────────────────────────────────────────────

class TestTheIntent:
    def _create(self, lab, monkeypatch):
        from modules.config import get_list_data_dir
        monkeypatch.setattr("modules.config.list_data_path", get_list_data_dir)
        plan = _plan()
        onboard.commit_step(plan, actor="t@example.com")
        return plan, os.path.join(get_list_data_dir("probe"), "config_repo")

    def test_the_committed_intent_is_static_never_dhcp(self, lab, monkeypatch):
        from modules.nsot import hostvars, manifest
        _plan_, repo = self._create(lab, monkeypatch)
        doc = hostvars.read_committed(repo, "s5")
        boot = doc["bootstrap"]
        assert (boot["source"], boot["address"], boot["mask"], boot["gateway"],
                boot["interface"], boot["server"]) == (
            "ztp_console", ADDRESS, MASK, GATEWAY, "Vlan1", SERVER)
        assert "gateway_route" not in boot, "a record without it routes (C1606)"
        assert doc["default_gateway"] == GATEWAY
        assert doc["static_routes"] == [{"family": "ipv4", "spec": f"0.0.0.0 0.0.0.0 {GATEWAY}"}]
        entry = manifest.find_by_name(repo, "s5")[1]
        assert entry["address_source"] == "ztp_console" and entry["mgmt_ip"] == ADDRESS
        assert "reserved_address" not in entry and "mgmt_mac" not in entry

    @pytest.mark.parametrize("given,want", [
        ([{"family": "ipv4", "spec": "198.51.100.0 255.255.255.0 " + GATEWAY}],
         [{"family": "ipv4", "spec": "198.51.100.0 255.255.255.0 " + GATEWAY},
          {"family": "ipv4", "spec": f"0.0.0.0 0.0.0.0 {GATEWAY}"}]),
        ([{"family": "ipv4", "spec": f"0.0.0.0 0.0.0.0 {GATEWAY}"}],
         [{"family": "ipv4", "spec": f"0.0.0.0 0.0.0.0 {GATEWAY}"}]),
    ], ids=["kept-and-added", "not-twice"])
    def test_the_route_joins_the_intent_s_own_routes_once(self, lab, monkeypatch, given, want):
        """The route is added to the routes the plan's intent already holds, never in place of
        them and never twice."""
        from modules.config import get_list_data_dir
        from modules.nsot import hostvars
        monkeypatch.setattr("modules.config.list_data_path", get_list_data_dir)
        onboard.commit_step(_plan(host_vars={"static_routes": given}), actor="t@example.com")
        doc = hostvars.read_committed(os.path.join(get_list_data_dir("probe"), "config_repo"),
                                      "s5")
        assert doc["static_routes"] == want

    def test_the_committed_intent_renders_its_default_gateway_and_its_route(self, lab,
                                                                           monkeypatch):
        """The intent says what the device will run: its committed gateway and routes, laid on a
        real vIOS-L2 switch's parsed intent (tests/fixtures/configs/fleet/s1.cfg, which has no
        gateway and no static route; a bootstrap intent alone is not a renderable document,
        `hostvars.complete_schema`), render through the shipped template as
        ``ip default-gateway <relay>`` and ``ip route 0.0.0.0 0.0.0.0 <relay>``, once each, the
        two lines the kick-start typed (C1606)."""
        from modules.nsot import hostvars, roundtrip
        from modules.nsot.parsers import get_parser
        _plan_, repo = self._create(lab, monkeypatch)
        doc = hostvars.read_committed(repo, "s5")
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "configs",
                               "fleet", "s1.cfg"), encoding="utf-8") as fh:
            base = get_parser("cisco_ios").parse(fh.read())
        assert "default_gateway" not in base and base["static_routes"] == [], "floor"
        lines = roundtrip.render(dict(base, default_gateway=doc["default_gateway"],
                                      static_routes=list(doc.get("static_routes") or [])),
                                 "cisco_ios").splitlines()
        assert lines.count(f"ip default-gateway {GATEWAY}") == 1, lines
        assert [ln for ln in lines if ln.startswith("ip route")] == [
            f"ip route 0.0.0.0 0.0.0.0 {GATEWAY}"], lines

    def test_the_re_render_is_the_plan_s_byte_for_byte(self, lab, monkeypatch):
        plan, repo = self._create(lab, monkeypatch)
        monkeypatch.setattr("modules.secrets_store.KEY_FILE", str(lab["dir"] / "key.key"))
        onboard.stage_bootstrap_credential(repo, "s5", "bootstrap-only")
        out = onboard.bootstrap_artifact(repo, "s5")
        assert out["ok"], out["reason"]
        assert out["config"] == plan.bootstrap_config
        assert out["config"].count("\nip route ") == 1

    def test_the_kick_start_reads_this_onboarding(self, lab, monkeypatch):
        _plan_, repo = self._create(lab, monkeypatch)
        got = K.onboarding_target("probe", "s5")
        assert {k: got[k] for k in ("state", "address", "mask", "gateway", "vlan", "server",
                                    "boot_file")} == {
            "state": "read", "address": ADDRESS, "mask": MASK, "gateway": GATEWAY, "vlan": "1",
            "server": SERVER, "boot_file": "s5.cfg"}
        assert got["uplink"] == "" and got["uplink_why"] == "NetBox was not read for the uplink"

    def test_a_verified_device_has_no_pending_onboarding(self, lab, monkeypatch):
        from modules.nsot import manifest
        _plan_, repo = self._create(lab, monkeypatch)
        identity = manifest.find_by_name(repo, "s5")[0]
        manifest.mark_verified(repo, identity)
        got = K.onboarding_target("probe", "s5")
        assert got["state"] == "absent" and "is not pending" in got["why"]

    def test_another_source_is_absent_naming_it(self, lab, monkeypatch):
        from modules.config import get_list_data_dir
        monkeypatch.setattr("modules.config.list_data_path", get_list_data_dir)
        onboard.commit_step(_plan(address_source="static"), actor="t@example.com")
        got = K.onboarding_target("probe", "s5")
        assert got["state"] == "absent"
        assert got["why"] == ("s5 has no out-of-band onboarding in probe (its address source "
                              "is 'static', not 'ztp_console')")
        assert K.onboarding_target("probe", "nobody")["why"].endswith(
            "(its address source is 'none', not 'ztp_console')")

    def test_an_intent_without_its_server_is_refused(self, lab, monkeypatch):
        from modules.nsot import hostvars
        from tests.intent_fixture import commit_intent
        _plan_, repo = self._create(lab, monkeypatch)
        doc = hostvars.read_committed(repo, "s5")
        del doc["bootstrap"]["server"]
        hostvars.write_committed(repo, doc)
        commit_intent(repo)
        got = K.onboarding_target("probe", "s5")
        assert got["state"] == "refused" and "lacks ['server']" in got["why"]


# ── The kick-start's parameters and preview ───────────────────────────────────────────────

SWITCH = P.load("cisco_ios_switch")


class TestTheParameters:
    def test_the_plan_gives_address_mask_gateway_and_vlan(self):
        got = Z.kickstart_params(SWITCH, {"interface": "Gi0/1"}, "s5",
                                 dict(ONBOARDING, vlan="1"))
        assert got == {"interface": "Gi0/1", "hostname": "s5", **PLANNED, "vlan": "1"}

    def test_an_empty_value_is_none_given(self):
        got = Z.kickstart_params(SWITCH, {"interface": "Gi0/1", "vlan": "", "address": ""},
                                 "s5", ONBOARDING)
        assert got["vlan"] == "10" and got["address"] == ADDRESS

    def test_a_given_value_is_kept(self):
        got = Z.kickstart_params(SWITCH, {"interface": "Gi0/1", "vlan": 20}, "s5", ONBOARDING)
        assert got["vlan"] == 20

    def test_the_uplink_netbox_cables_is_the_interface(self):
        got = Z.kickstart_params(SWITCH, {}, "s5", dict(ONBOARDING, uplink="Gi0/1"))
        assert got["interface"] == "Gi0/1"

    def test_with_no_onboarding_only_the_hostname_and_the_default_vlan(self):
        assert Z.kickstart_params(SWITCH, {}, "s5", {"state": "absent"}) == {
            "hostname": "s5", "vlan": "1"}
        assert Z.kickstart_params(SWITCH, {}, "s5", None) == {"hostname": "s5", "vlan": "1"}

    def test_a_router_is_given_no_static_parameter(self):
        router = P.load("cisco_ios_router")
        assert Z.kickstart_params(router, {"interface": "Gi1"}, "r9", ONBOARDING) == {
            "interface": "Gi1", "hostname": "r9"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, socket.AF_INET)
    yield w
    w.server.close()


class TestThePreview:
    def test_it_names_the_reads_what_is_not_read_and_the_copy(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        p = world.kick_preview()
        assert p["ok"], p["refusals"]
        assert p["copy"] == COPY and p["readback"]["reads"][-1] == "show interfaces Vlan10"
        # C1646: the VLAN typed is read from the VLAN database, first, so nothing is unread and
        # the preview carries no "not read back" list.
        assert p["readback"]["reads"][0] == "show vlan id 10"
        assert "not_read" not in p["readback"]
        assert p["onboarding"]["server"] == SERVER

    def test_the_hash_binds_the_copy(self, world, monkeypatch):
        world.survey(greeting=PNP, answers=blank_answers())
        before = world.kick_preview()["hash"]
        monkeypatch.setattr(Z, "_onboarding",
                            lambda *a, **k: dict(ONBOARDING, server="192.0.2.11"))
        assert world.kick_preview()["hash"] != before

    def test_a_static_profile_without_an_onboarding_is_refused(self, world, monkeypatch):
        world.survey(greeting=PNP, answers=blank_answers())
        monkeypatch.setattr(Z, "_onboarding", lambda *a, **k: K._absent("none for the test"))
        p = world.kick_preview()
        assert not p["ok"] and p["refused_by"]["onboarding"] == (
            "profile cisco_ios_switch types the plan's static address (C1592), and none for "
            "the test: create the device with the out-of-band (console) address source first, "
            "so its plan gives the address, mask, gateway and config server")

    def test_a_refused_onboarding_is_said(self, world, monkeypatch):
        world.survey(greeting=PNP, answers=blank_answers())
        monkeypatch.setattr(Z, "_onboarding",
                            lambda *a, **k: dict(K._absent("x"), state="refused", why="bad"))
        assert world.kick_preview()["refused_by"]["onboarding"] == "bad"

    def test_a_given_address_that_is_not_the_plan_s_is_refused(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        p = world.kick_preview(dict(PARAMS, address="192.0.2.15"))
        assert p["refused_by"]["params"] == ("parameter address '192.0.2.15' is not the "
                                             "plan's '192.0.2.14': the plan is the one source "
                                             "of the static address")

    def test_the_plan_s_own_value_given_is_accepted(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        assert world.kick_preview(dict(PARAMS, address=ADDRESS))["ok"]

    def test_a_dhcp_profile_on_a_static_onboarding_is_refused(self, world):
        world.survey(greeting=PNP, answers=blank_answers(), profile="cisco_ios_router")
        p = world.kick_preview({"interface": "Gi1"})
        assert p["refused_by"]["profile"] == (
            "profile cisco_ios_router types no static address, and edge1's onboarding is "
            "out-of-band with a static one (C1592): choose a profile that types it")

    def test_an_ipv6_parameter_is_refused_by_name(self, world, monkeypatch):
        world.survey(greeting=PNP, answers=blank_answers())
        monkeypatch.setattr(Z, "_onboarding",
                            lambda *a, **k: dict(ONBOARDING, gateway="2001:db8:4::13"))
        p = world.kick_preview()
        assert p["refused_by"]["params"] == ("parameter gateway '2001:db8:4::13' is IPv6: "
                                             "out-of-band ZTP reserves and serves IPv4 (DHCPv4) "
                                             "addresses only (C1245)")

    def test_an_ipv6_server_is_refused_by_name(self, world, monkeypatch):
        world.survey(greeting=PNP, answers=blank_answers())
        monkeypatch.setattr(Z, "_onboarding",
                            lambda *a, **k: dict(ONBOARDING, server="2001:db8::10"))
        assert "is IPv6" in world.kick_preview()["refused_by"]["params"]


@pytest.mark.parametrize("value,why", [
    ("192.0.2.256", "is not an IPv4 address"), ("0.0.0.0", "is not an address a device's"),
    ("127.0.0.1", "is not an address a device's"), ("224.0.0.5", "is not an address a device's"),
    ("255.255.255.255", "is not an address a device's"), ("192.0.2", "is not a valid"),
    ("2001:db8::1", "is IPv6"), (" 192.0.2.1", "is not a valid")])
def test_an_address_parameter_off_its_shape_is_refused(value, why):
    with pytest.raises(ValueError, match=f"parameter address {value!r} {why}"):
        V.check_param("address", "ipv4_address", value)


@pytest.mark.parametrize("value,ok", [
    ("255.255.255.252", True), ("255.255.255.255", True), ("128.0.0.0", True),
    ("255.0.255.0", False), ("0.0.0.0", False), ("0.0.0.255", False), ("255.255.255.253", False)])
def test_a_mask_must_be_contiguous(value, ok):
    if ok:
        assert V.check_param("mask", "ipv4_mask", value) == value
    else:
        with pytest.raises(ValueError, match="is not a network mask"):
            V.check_param("mask", "ipv4_mask", value)


def test_an_ipv6_mask_is_refused_by_name():
    with pytest.raises(ValueError, match=r"is IPv6: .*\(C1245\)"):
        V.check_param("mask", "ipv4_mask", "ffff:ffff::")


# ── The run, over the fake console ────────────────────────────────────────────────────────

def _lines():
    return V.render_kickstart(SWITCH, dict(PARAMS, **PLANNED))


class TestTheRun:
    @FAMILIES
    def test_it_types_reads_back_copies_and_records_the_mac(self, tmp_path, monkeypatch,
                                                             family):
        w = World(tmp_path, monkeypatch, family)
        try:
            w.survey(greeting=PNP, answers=blank_answers())
            lines = _lines()
            rec = w.kick(kick_answers(lines))
            assert rec["outcome"] == "done", rec["reason"]
            assert w.received(1) == (b"\renable\rdir nvram:\r"
                                     + b"".join(f"{l}\r".encode() for l in lines)
                                     + after_lines(lines))
            assert rec["mac"] == "0c:00:6c:e9:80:0a" and rec["readback_differs"] == []
            assert rec["copied"] == {"ok": True, "bytes": 1203, "refused": "",
                                     "why": "the copy printed '[OK - 1203 bytes]'"}
            assert rec["copy"] == COPY and rec["verify"]["ok"]
        finally:
            w.server.close()

    def test_c1593_a_refused_line_stops_the_run_with_nothing_more_typed(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        lines = _lines()
        answers = kick_answers(lines)
        i = lines.index(f" ip address {ADDRESS} {MASK}")
        answers[3 + i] = (f"{lines[i]}\r\n                   ^\r\n% Invalid input detected at "
                          "'^' marker.\r\n\r\nedge1(config-if)#").encode()
        rec = world.kick(answers)
        assert rec["outcome"] == "line_refused"
        assert rec["reason"] == (f"typing: 'ip address {ADDRESS} {MASK}' was refused: "
                                 "\"% Invalid input detected at '^' marker.\"")
        assert rec["refused"] == {"line": f"ip address {ADDRESS} {MASK}",
                                  "words": "% Invalid input detected at '^' marker.",
                                  "before": f"ip address {ADDRESS} {MASK}"}
        assert world.received(1) == (b"\renable\rdir nvram:\r"
                                     + b"".join(f"{l}\r".encode() for l in lines[:i + 1]))
        assert Z.problem({"latest": rec}) == "failed"

    def test_a_read_back_that_differs_sends_no_copy(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        lines = _lines()
        answers = kick_answers(lines)
        svi = read_index(answers, "show running-config interface Vlan10")
        answers[svi] = answers[svi].replace(f" ip address {ADDRESS} {MASK}".encode(),
                                            b" ip address dhcp")
        rec = world.kick(answers)
        assert rec["outcome"] == "readback_differs"
        assert rec["reason"].startswith(f"read-back: typed 'ip address {ADDRESS} {MASK}'; "
                                        "'show running-config interface Vlan10' shows "
                                        "'ip address dhcp'")
        assert COPY.encode() not in world.received(1)
        assert world.received(1).endswith(b"show interfaces Vlan10\r")

    def test_an_unreadable_mac_fails_the_read_back(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        lines = _lines()
        answers = kick_answers(lines)
        answers[read_index(answers, "show interfaces Vlan10")] = \
            b"show interfaces Vlan10\r\nnothing here\r\nedge1#"
        rec = world.kick(answers)
        assert rec["outcome"] == "readback_differs" and rec["mac"] is None
        assert "so the MAC in use is not known" in rec["reason"]
        assert COPY.encode() not in world.received(1)

    def _copy(self, world, transfer: bytes, question: bytes = None):
        world.survey(greeting=PNP, answers=blank_answers())
        answers = kick_answers(_lines())
        if question is not None:
            answers[-2:] = [question]
        else:
            answers[-1] = transfer
        return world.kick(answers)

    def test_a_copy_error_fails_it_naming_ios_s_words(self, world):
        err = "%Error opening tftp://192.0.2.10/edge1.cfg (Timed out)"
        rec = self._copy(world, f"\r\nAccessing tftp://192.0.2.10/edge1.cfg...\r\n{err}\r\n"
                                "edge1#".encode())
        assert rec["outcome"] == "copy_failed"
        assert rec["copied"]["refused"] == err and rec["refused"]["words"] == err
        assert rec["reason"].startswith("copy: the console answered the last send with a "
                                        f"refusal: {err!r}")

    def test_a_copy_of_nothing_fails(self, world):
        transfer = copy_answers(COPY, "edge1#", size=0)[1]
        rec = self._copy(world, transfer)
        assert rec["outcome"] == "copy_failed"
        assert rec["reason"] == ("copy: the copy printed '[OK - 0 bytes]': it must move more "
                                 "than 0 bytes")

    def test_a_refusal_inside_the_copied_file_fails_it(self, world):
        transfer = copy_answers(COPY, "edge1#")[1].replace(
            b"[OK - 1203 bytes]", b"[OK - 1203 bytes]\r\nip foo\r\n  ^\r\n% Invalid input "
                                  b"detected at '^' marker.")
        rec = self._copy(world, transfer)
        assert rec["outcome"] == "copy_failed" and rec["copied"]["bytes"] is None
        assert "% Invalid input detected at '^' marker." in rec["reason"]

    def test_any_other_question_at_the_copy_stops_it(self, world):
        rec = self._copy(world, b"", question=(f"{COPY}\r\nAddress or name of remote host "
                                               "[]? ").encode())
        assert rec["outcome"] == "copy_failed"
        assert "found an unknown prompt 'Address or name of remote host []?'" in rec["reason"]
        assert world.received(1).endswith(f"{COPY}\r".encode()), "the question never answered"


# ── What a kick-start records (run #23's survivors): the record is what the card and History
# read later, so its shape is asserted exactly, and its masking with a planted secret ─────────

#: The SVI's read-back of a device that took another mask than the one typed.
WRONG_MASK = "255.255.255.0"
#: The read-back's words for that difference (`console_kickstart.compare_readback`'s).
SVI_WHY = (f"typed 'ip address {ADDRESS} {MASK}'; 'show running-config interface Vlan10' "
           f"shows 'ip address {ADDRESS} {WRONG_MASK}' (it must show 'ip address {ADDRESS} "
           f"{MASK}')")


def _svi_differs(answers, lines):
    """*answers* with the SVI's read-back showing the address under WRONG_MASK."""
    svi = read_index(answers, "show running-config interface Vlan10")
    answers[svi] = answers[svi].replace(f" ip address {ADDRESS} {MASK}".encode(),
                                        f" ip address {ADDRESS} {WRONG_MASK}".encode())
    return answers


class TestWhatAKickStartRecords:
    def test_a_read_back_difference_is_recorded_as_typed_read_and_why(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        lines = _lines()
        rec = world.kick(_svi_differs(kick_answers(lines), lines))
        assert rec["outcome"] == "readback_differs"
        assert rec["readback_differs"] == [{
            "typed": f"ip address {ADDRESS} {MASK}",
            "read": "show running-config interface Vlan10",
            "why": SVI_WHY}]
        assert Z.get_run(LIST, rec["id"])["readback_differs"] == rec["readback_differs"]

    def test_a_difference_with_the_mac_read_names_only_the_differences(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        lines = _lines()
        rec = world.kick(_svi_differs(kick_answers(lines), lines))
        assert rec["mac"] == "0c:00:6c:e9:80:0a"
        assert rec["reason"] == "read-back: " + SVI_WHY

    def test_the_record_says_where_the_mac_in_use_was_read(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        rec = world.kick(kick_answers(_lines()))
        assert rec["mac"] == "0c:00:6c:e9:80:0a"
        assert rec.get("mac_reason") == "the MAC in use, from 0c00.6ce9.800a"
        assert Z.get_run(LIST, rec["id"])["mac_reason"] == rec["mac_reason"]

    def test_a_kick_start_that_ended_verified_has_no_reason(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        rec = world.kick(kick_answers(_lines()))
        assert rec["outcome"] == "done" and rec["reason"] == ""
        assert Z.get_run(LIST, rec["id"])["reason"] == ""

    @pytest.mark.parametrize("stop", ["unverified", "line_refused", "readback_differs"])
    def test_a_kick_start_that_stopped_records_what_it_sent_and_saw(self, world, stop):
        """The partial record is the evidence: what was sent, how many bytes, the console's
        transcript and the state it was found in (`_finish` with the console)."""
        world.survey(greeting=PNP, answers=blank_answers())
        lines = _lines()
        answers = kick_answers(lines)
        if stop == "unverified":
            answers[2 + len(lines)] = b"end\r\nSwitch#"
            seen = "end\nSwitch#"
        elif stop == "line_refused":
            i = lines.index(f" ip address {ADDRESS} {MASK}")
            answers[3 + i] = (f"{lines[i]}\r\n                   ^\r\n% Invalid input detected "
                              "at '^' marker.\r\n\r\nedge1(config-if)#").encode()
            seen = "% Invalid input detected"
        else:
            answers = _svi_differs(answers, lines)
            seen = f"ip address {ADDRESS} {WRONG_MASK}"
        rec = world.kick(answers)
        assert rec["outcome"] == stop
        assert {"sent", "bytes_written", "transcript", "attach_state"} <= set(rec), sorted(rec)
        _recorded_as_sent(rec, world.received(1), seen, P.USER_EXEC)

    def test_a_secret_in_a_read_back_difference_is_masked_in_the_record(self, world):
        """Masking is a blocking property: a known secret's value in what was typed and in why
        it differs from what the device shows never reaches the record (planted: the
        address; `read` is the read-back's command, the program's own words)."""
        world.survey(greeting=PNP, answers=blank_answers())
        lines = _lines()
        rec = world.kick(_svi_differs(kick_answers(lines), lines),
                         values={ADDRESS: "planted"})
        assert rec["outcome"] == "readback_differs"
        (d,) = rec["readback_differs"]
        assert set(d) == {"typed", "read", "why"}, d
        assert d["typed"] == f"ip address <redacted:planted> {MASK}"
        assert d["why"] == (f"typed 'ip address <redacted:planted> {MASK}'; 'show running-config "
                            f"interface Vlan10' shows 'ip address <redacted:planted> "
                            f"{WRONG_MASK}' (it must show 'ip address <redacted:planted> "
                            f"{MASK}')")
        assert ADDRESS not in rec["reason"] and "<redacted:planted>" in rec["reason"]
        assert ADDRESS not in str(Z.get_run(LIST, rec["id"])), "the stored record"

    def test_a_secret_in_a_refused_line_is_masked_in_the_record(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        lines = _lines()
        answers = kick_answers(lines)
        i = lines.index(f" ip address {ADDRESS} {MASK}")
        answers[3 + i] = (f"{lines[i]}\r\n                   ^\r\n% Invalid input detected at "
                          "'^' marker.\r\n\r\nedge1(config-if)#").encode()
        rec = world.kick(answers, values={ADDRESS: "planted"})
        assert rec["outcome"] == "line_refused"
        assert rec["refused"] == {"line": f"ip address <redacted:planted> {MASK}",
                                  "words": "% Invalid input detected at '^' marker.",
                                  "before": f"ip address <redacted:planted> {MASK}"}
        assert ADDRESS not in rec["reason"]
        assert ADDRESS not in str(Z.get_run(LIST, rec["id"])), "the stored record"


class TestTheCopyWaitsOutKeyGeneration:
    """C1594 with the operator's 2026-10-23 bound: the bootstrap generates the SSH key during
    the copy and IOS prints nothing meanwhile (measured 39.5 s on vIOS-L2, C712): a silence is
    not a failure until the copy's own bound."""

    def _copying(self, timeout):
        s = S.ConsoleSession(SWITCH, S.Plan(steps=(S.Step(P.COPY_DESTINATION, b"\r"),),
                                            final=(P.PRIV_EXEC,)),
                             start=0.0, settle_s=0.5, quiet_s=5.0, step_timeout_s=timeout,
                             values={})
        s.feed(b"Destination filename [running-config]? ", 1.0)
        assert s.tick(2.0).data == b"\r"
        s.feed(b"\r\nAccessing tftp://192.0.2.10/edge1.cfg...\r\nLoading edge1.cfg from "
               b"192.0.2.10 (via Vlan10): !\r\n[OK - 1203 bytes]\r\nThe name for the keys "
               b"will be: edge1.example.net\r\n% The key modulus size is 2048 bits\r\n"
               b"% Generating 2048 bit RSA keys, keys will be non-exportable...", 3.0)
        return s

    def test_a_silence_shorter_than_the_bound_waits(self):
        s = self._copying(Z.DEFAULT_TIMINGS.copy_timeout_s)
        assert s.tick(2.0 + 100.0).action == "wait"
        d = s.feed(b"[OK] (elapsed time was 39 seconds)\r\nedge1#", 102.0)
        assert s.tick(103.0).action == "done" or d.action == "done"

    def test_past_the_bound_it_stops(self):
        s = self._copying(Z.DEFAULT_TIMINGS.copy_timeout_s)
        d = s.tick(2.0 + Z.DEFAULT_TIMINGS.copy_timeout_s)
        assert d.action == "abort" and "within 150 s" in d.reason

    def test_the_bound_is_about_two_and_a_half_times_the_measured_key_generation(self):
        assert 2.5 * 39.5 <= Z.DEFAULT_TIMINGS.copy_timeout_s <= 4 * 39.5
        assert Z.DEFAULT_TIMINGS.copy_timeout_s > Z.DEFAULT_TIMINGS.step_timeout_s

    def test_the_run_gives_the_copy_its_own_bound(self, world, monkeypatch):
        seen = []
        real = Z._Console.then

        def then(self, steps, final, step_timeout_s=None):
            seen.append((steps[0][1][:4], step_timeout_s))
            return real(self, steps, final, step_timeout_s)
        monkeypatch.setattr(Z._Console, "then", then)
        world.survey(greeting=PNP, answers=blank_answers())
        rec = world.kick(kick_answers(_lines()))
        assert rec["outcome"] == "done"
        assert ("copy", FAST.copy_timeout_s) in seen
        assert all(t is None for word, t in seen if word != "copy")


# ── The responder's gate (blocking) ───────────────────────────────────────────────────────

ENTRY = {"name": "s5", "address_source": "ztp_console", "mgmt_ip": ADDRESS,
         "onboarded_at": "2026-10-23T04:00:00Z", "verified_at": None}


def _pending(*entries):
    return lambda: [("Lab", "/repo", e) for e in entries]


def _held_by(operation):
    return lambda list_name, hostname: ({"operation": operation, "device": hostname}
                                        if operation else None)


def _gate(peer=ADDRESS, filename="s5.cfg", entries=(ENTRY,), operation=Z.OP_KICKSTART):
    return ztp_responder.console_gate(peer, filename, pending=_pending(*entries),
                                      holder=_held_by(operation))


class TestTheGate:
    def test_its_planned_address_its_file_and_its_console_run_are_served(self):
        assert _gate() == {"serve": True, "device": "s5", "list": "Lab", "repo": "/repo",
                           "reason": ""}

    def test_not_held_is_refused(self):
        got = _gate(operation=None)
        assert got["serve"] is False and got["device"] == "s5"
        assert got["reason"] == (f"s5 is not held: its bootstrap is served to {ADDRESS} only "
                                 "while its console run holds it (console kick-start, console "
                                 "onboard)")

    @pytest.mark.parametrize("operation", ["deploy", "console survey", "onboard (create)", "?"])
    def test_held_by_another_operation_is_refused(self, operation):
        got = _gate(operation=operation)
        assert got["serve"] is False
        assert got["reason"] == (f"s5 is held by {operation!r}, not by its console run "
                                 "(console kick-start, console onboard): its bootstrap is not "
                                 "served")

    def test_the_one_decision_onboarding_s_hold_is_served(self):
        """The one-decision out-of-band onboarding holds the device under its own name and its
        copy fetches through this gate: that hold serves the bootstrap, and the name the run
        holds under is the one the gate allows (Phase A and B merged, 2026-10-23: the run's
        copy was refused until the gate named it)."""
        from modules.nsot import oob_onboard

        assert oob_onboard.OP == "console onboard"
        assert _gate(operation=oob_onboard.OP)["serve"] is True

    def test_a_different_address_is_refused(self):
        got = _gate(peer="192.0.2.15")
        assert got == {"serve": False, "device": "", "list": "", "repo": "",
                       "reason": "no pending out-of-band (console) device is planned at "
                                 "192.0.2.15"}

    def test_another_device_s_file_is_refused(self):
        got = _gate(filename="s6.cfg")
        assert got["serve"] is False
        assert got["reason"] == f"{ADDRESS} asked for 's6.cfg'; s5's bootstrap is 's5.cfg'"

    @pytest.mark.parametrize("source", ["ztp", "dhcp", "static", "", None])
    def test_a_device_of_another_source_is_not_this_gate_s(self, source):
        got = _gate(entries=(dict(ENTRY, address_source=source),))
        assert got["serve"] is False and got["device"] == ""

    def test_two_devices_planned_at_the_address_are_refused(self):
        got = _gate(entries=(ENTRY, dict(ENTRY, name="s6")))
        assert got["reason"] == f"2 pending out-of-band devices are planned at {ADDRESS}"
        assert got["serve"] is False

    def test_the_address_is_compared_whole(self):
        assert _gate(entries=(dict(ENTRY, mgmt_ip=f" {ADDRESS} "),))["serve"] is True
        assert _gate(entries=(dict(ENTRY, mgmt_ip="192.0.2.140"),))["serve"] is False
        assert _gate(entries=(dict(ENTRY, mgmt_ip=None),))["serve"] is False

    def test_ipv6_is_refused_by_name(self):
        got = _gate(peer="2001:db8:4::14", entries=(dict(ENTRY, mgmt_ip="2001:db8:4::14"),))
        assert got["serve"] is False and got["device"] == ""
        assert got["reason"] == ("2001:db8:4::14 is an IPv6 address: out-of-band ZTP serves "
                                 "IPv4 (DHCPv4) addresses only (C1245)")

    def test_an_unreadable_hold_is_refused(self):
        from modules.nsot import device_ops

        def unreadable(list_name, hostname):
            raise device_ops.HoldsUnreadable("/holds/s5", OSError("denied"))
        got = ztp_responder.console_gate(ADDRESS, "s5.cfg", pending=_pending(ENTRY),
                                         holder=unreadable)
        assert got["serve"] is False and got["reason"].startswith(
            "whether s5 is held could not be read: ")

    def test_unreadable_manifests_are_refused(self):
        def boom():
            raise OSError("manifest locked")
        got = ztp_responder.console_gate(ADDRESS, "s5.cfg", pending=boom,
                                         holder=_held_by(Z.OP_KICKSTART))
        assert got == {"serve": False, "device": "", "list": "", "repo": "",
                       "reason": "the manifests could not be read: manifest locked"}

    def test_the_hold_is_read_across_processes_by_default(self, tmp_path, monkeypatch):
        """The default holder is `device_ops.holder` (the lock file another process holds):
        held by the kick-start here, the gate serves; released, it refuses."""
        from modules.nsot import device_ops
        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        with device_ops.hold("Lab", "s5", Z.OP_KICKSTART, ACTOR):
            assert ztp_responder.console_gate(ADDRESS, "s5.cfg",
                                              pending=_pending(ENTRY))["serve"] is True
        assert ztp_responder.console_gate(ADDRESS, "s5.cfg",
                                          pending=_pending(ENTRY))["serve"] is False

    def test_another_device_s_console_run_does_not_serve_this_one(self, tmp_path, monkeypatch):
        """The hold is read for the device planned at the asking address, by its own list and
        name: another device's kick-start (s6, same list; s5 in another list) serves s5 nothing."""
        from modules.nsot import device_ops
        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        for list_name, name in (("Lab", "s6"), ("Other", "s5")):
            with device_ops.hold(list_name, name, Z.OP_KICKSTART, ACTOR):
                got = ztp_responder.console_gate(ADDRESS, "s5.cfg", pending=_pending(ENTRY))
            assert got["serve"] is False and got["device"] == "s5", (list_name, name, got)
            assert got["reason"].startswith("s5 is not held: "), got

    def test_the_fetching_operations_are_the_kick_start_and_the_one_decision_run(self):
        """Exactly the two runs whose copy fetches the bootstrap; no other hold serves it."""
        assert Z.FETCH_OPERATIONS == ("console kick-start", "console onboard") == \
            (Z.OP_KICKSTART, Z.OP_ONBOARD)


class TestTheResponderDecides:
    def _decide(self, peer=ADDRESS, operation=Z.OP_KICKSTART, fragment=(), rendered=None):
        return ztp_responder.decide(
            peer, "s5.cfg", fragment=lambda: list(fragment), pending=_pending(ENTRY),
            holder=_held_by(operation),
            artifact=lambda repo, name: rendered or {"ok": True, "config": "hostname s5\n"})

    def test_the_console_run_s_copy_is_served_its_bootstrap(self):
        got = self._decide()
        assert (got["serve"], got["config"], got["device"], got["list"]) == (
            True, b"hostname s5\n", "s5", "Lab")

    def test_a_refusal_of_this_device_is_its_gate_s(self):
        got = self._decide(operation="deploy")
        assert got["serve"] is False and got["device"] == "s5"
        assert "not by its console run" in got["reason"]

    def test_a_render_that_fails_is_not_served(self):
        got = self._decide(rendered={"ok": False, "reason": "no staged credential"})
        assert got["serve"] is False
        assert got["reason"] == "the config could not be rendered: no staged credential"

    def test_an_address_nobody_planned_keeps_the_reservation_s_reason(self):
        got = self._decide(peer="192.0.2.15")
        assert got["serve"] is False and got["reason"] == ("192.0.2.15 holds no reservation "
                                                           "the tool wrote")

    def test_a_reserved_address_never_reaches_the_console_gate(self):
        """An address with a reservation is ZTP's (the DHCP path), judged by it alone."""
        fragment = [{"ip-address": ADDRESS, "hw-address": "aa:bb:cc:00:00:01",
                     "option-data": [{"name": "boot-file-name", "data": "s5.cfg"}]}]
        got = self._decide(fragment=fragment)
        assert got["serve"] is False
        assert "no pending ZTP device holds the reservation" in got["reason"]


def test_the_responder_lists_a_pending_out_of_band_device(tmp_path, monkeypatch):
    """`_pending_ztp_devices` reads the manifests: a pending ``ztp_console`` device is listed,
    a verified one is not (pending is the manifest's own)."""
    from modules.nsot import manifest
    from modules.nsot.repo import adopt_identity, init_repo
    lists = tmp_path / "lists"
    repo = str(lists / "lab" / "config_repo")
    os.makedirs(repo)
    monkeypatch.setattr("modules.config.LISTS_DIR", str(lists))
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": "Lab", "filename": "lab"}])
    init_repo(repo)
    identities = {}
    for name in ("s5", "s6"):
        identities[name] = adopt_identity(hostname=name, mgmt_ip="")
        manifest.upsert_device(repo, identities[name], name, mgmt_ip=ADDRESS, pending=True,
                               address_source="ztp_console")
    # The identity the entry was written under: `adopt_identity` MINTS one per call, so a
    # second call names no entry and verifies nothing.
    manifest.mark_verified(repo, identities["s6"])
    got = [(ln, e["name"]) for ln, _r, e in ztp_responder._pending_ztp_devices()]
    assert got == [("Lab", "s5")]
