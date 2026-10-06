"""C506 phase 2 (board approved 2026-10-06): the effects a program implies on adjacencies,
derived from it and committed intent, drawn in the plan's Expected effects, and honoured by
verify.

Part 5.3's change shut Loopback1 on tw-ztp-a; its BGP session was sourced from Loopback1, so it
dropped, and verify waited out the hold time and rolled the change back. A person reading the
program sees `shutdown`; they do not see which sessions ride on that interface. So the plan now
says it ("BGP to 198.51.100.1 drops: it is sourced from Loopback1, which the program shuts"),
and verify leaves exactly those adjacencies out of its comparison. An adjacency whose identity
intent does not give (no explicit router-id) is not counted as expected: its loss still fails.
"""

import pytest

from modules import pipeline
from modules.nsot import expected_effects as fx
from tests.test_bgp_hold_watch import _summary, world  # noqa: F401 (the fixture)
from tests.test_device_deploy_v2 import _get, deploy  # noqa: F401 (the fixture)
from tests.test_device_deploy_v2 import lab  # noqa: F401

INTENTS = {
    "r3": {"hostname": "r3", "interfaces": [
        {"name": "GigabitEthernet3", "ipv4": "192.0.2.13 255.255.255.0"},
        {"name": "GigabitEthernet4", "ipv4": "192.0.2.74 255.255.255.252"},
        {"name": "Loopback1", "ipv4": "192.0.2.81 255.255.255.255"}],
        "routing": {"ospf": [{"networks": ["network 192.0.2.0 0.0.0.255 area 0"],
                              "settings": ["router-id 10.255.1.13"]}],
                    "bgp": {"neighbors": ["neighbor 198.51.100.1 remote-as 65002",
                                          "neighbor 198.51.100.1 update-source Loopback1",
                                          "neighbor 192.0.2.98 remote-as 65003"]}}},
    "r1": {"hostname": "r1", "interfaces": [
        {"name": "GigabitEthernet1", "ipv4": "192.0.2.11 255.255.255.0"}],
        "routing": {"ospf": [{"networks": ["network 192.0.2.0 0.0.0.255 area 0"],
                              "settings": ["router-id 10.255.1.11"]}]}},
}


class TestDerived:
    def test_shutting_an_interface_drops_the_adjacencies_on_it(self):
        got = fx.for_device(INTENTS, "r3", ["interface GigabitEthernet3", " shutdown", "exit"])
        assert got["down"] == ["GigabitEthernet3"]
        ospf = [d for d in got["adjacencies_drop"] if d["proto"] == "ospf"]
        assert ospf == [{"proto": "ospf", "peer": "r1", "rid": "10.255.1.11",
                         "address": "192.0.2.11", "via": "GigabitEthernet3",
                         "why": "its adjacency is on GigabitEthernet3, which the program shuts"}]
        bgp = [d for d in got["adjacencies_drop"] if d["proto"] == "bgp"]
        assert [d["address"] for d in bgp] == ["192.0.2.98"], "a peer on the shut subnet"
        assert "GigabitEthernet3's subnet" in bgp[0]["why"]

    def test_shutting_the_loopback_a_session_is_sourced_from_drops_that_session(self):
        """Part 5.3's shape: Loopback1 forms no OSPF adjacency, and BGP rides on it."""
        got = fx.for_device(INTENTS, "r3", ["interface Loopback1", " shutdown", "exit"])
        assert [(d["proto"], d["address"]) for d in got["adjacencies_drop"]] == [
            ("bgp", "198.51.100.1")]
        assert got["adjacencies_drop"][0]["why"] == \
            "it is sourced from Loopback1, which the program shuts"

    def test_bringing_up_an_interface_with_ospf_may_form_an_adjacency(self):
        got = fx.for_device(INTENTS, "r3", ["interface GigabitEthernet4", " ip ospf 1 area 0",
                                             " no shutdown", "exit"])
        assert got["up"] == ["GigabitEthernet4"] and got["adjacencies_drop"] == []
        assert got["may_form"] == [{"proto": "ospf", "via": "GigabitEthernet4"}]

    def test_a_program_that_shuts_nothing_implies_nothing(self):
        got = fx.for_device(INTENTS, "r3", ["interface GigabitEthernet3", " description x"])
        assert got == {"down": [], "up": [], "adjacencies_drop": [], "may_form": []}

    def test_identities_compare_as_the_device_prints_them(self):
        drops = [{"proto": "bgp", "address": "2001:db8:51::2"},
                 {"proto": "ospf", "rid": "10.255.1.11"}, {"proto": "ospf", "rid": ""}]
        assert fx.expected_ids(drops, "bgp") == {"2001:db8:51::2"}
        assert fx.expected_ids(drops, "ospf") == {"10.255.1.11"}, "no router-id, not expected"
        snap = {"protocols": {"bgp": {"peers": [
            {"neighbor": "2001:DB8:51::2", "established": True},
            {"neighbor": "198.51.100.1", "established": False}]}}}
        assert fx.neighbour_ids(snap, "bgp") == {"2001:db8:51::2"}


class TestThePlanSaysIt:
    def test_the_words(self):
        from modules.preview_confirm import expected_part
        part = expected_part(fx.for_device(INTENTS, "r3",
                                           ["interface Loopback1", " shutdown", "exit"]))
        assert part["derived"] == [
            "Loopback1 goes down: the program shuts it.",
            "BGP to 198.51.100.1 drops: it is sourced from Loopback1, which the program shuts."]
        assert "fails at once, without waiting for BGP's hold time" in part["unexpected"]

    def test_the_device_deploy_card_draws_expected_effects(self, deploy, monkeypatch):  # noqa: F811
        import routes.deploy as rd
        monkeypatch.setattr(rd, "_expected_effects", lambda *a, **k: fx.for_device(
            INTENTS, "r3", ["interface Loopback1", " shutdown", "exit"]))
        _r, card = _get(deploy, "/v2/device/r2/deploy")
        part = card.split('id="expected"')[1].split("</div></div>")[0]
        assert "Expected effects" in part
        assert "BGP to 198.51.100.1 drops: it is sourced from Loopback1" in part
        assert "Anything else is unexpected" in part


class TestVerifyHonoursThem:
    """r3's real BGP table: its IPv4 session to 198.51.100.1 Idle after the change."""

    def test_a_session_the_plan_expected_to_drop_is_not_a_failure(self, world):  # noqa: F811
        ctx, clock = world(_summary("Idle"))
        ctx.rendered_commands = {"x": ["interface Loopback1", " shutdown", "exit"]}
        ctx.expected_effects = {"x": {"adjacencies_drop": [
            {"proto": "bgp", "address": "198.51.100.1", "why": "sourced from Loopback1"}]}}
        pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert v["ok"] is True, v["issues"]
        assert v["bgp_watch"]["before"] == 1, "the hold watch counts the session that stays"

    def test_the_same_drop_not_expected_still_fails(self, world):  # noqa: F811
        ctx, clock = world(_summary("Idle"))
        ctx.rendered_commands = {"x": ["interface Loopback9", " description x", "exit"]}
        with pytest.raises(pipeline.PipelineStageError):
            pipeline._stage_verify(ctx)
