"""C1471's per-device intent patch (PHASE8_PLAN 15.7 and 15.12, feature 7's first piece):
`modules/nsot/intent_patch.py`, deterministic, no AI.

On the host's REAL committed documents (tests/fixtures/committed/README.md: s1's intent, a
vIOS-L2 switch with VLANs, access ports and SVIs; r2's, an IOS-XE router with an OSPF process
holding two network statements), with no edit to either:

- the patch model is strict (no coercion, no undeclared field, no unknown operation) and each
  field's rule refuses by name, an IPv6 prefix in a network operation beside its IPv4 one;
- each operation changes exactly what it names and nothing else, and says when a merge-only
  deploy leaves the device holding what it removed;
- a patch naming an interface, VLAN or OSPF process the intent lacks, or contradicting what it
  holds, is refused naming both; two operations deciding one thing are refused;
- the result is checked by the intent editor's own validator, whose refusal is returned;
- `preview` hands `intent_edit.preview` exactly the patched intent, and `commit` commits it
  through `intent_edit.commit`, bound to the version previewed (a real repository: the
  fixture `host` of tests/test_committed_before_p1.py, the host's documents committed).

Expected documents are built from the fixture's YAML by hand-written edits in each test, never
by the module under test.
"""

import copy
import json
import os
import subprocess

import pytest
import yaml

from tests.test_committed_before_p1 import host  # noqa: F401  (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "committed")


def _text(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def _doc(name: str) -> dict:
    return yaml.safe_load(_text(f"{name}.yml"))


def _patch(hostname: str, *operations) -> dict:
    return {"hostname": hostname, "operations": list(operations)}


def _iface(doc: dict, name: str) -> dict:
    return next(i for i in doc["interfaces"] if i["name"] == name)


#: A VLAN database as the patch's caller hands it in once measured (`vlan_capability.of`,
#: C1692): the patch is pure, so these tests of its document work give it the answer;
#: where the answer comes from, and every refusal without one, is tests/test_vlan_capability.py.
HAS_VLANS = {"has": True, "platform": "cisco_ios", "device_type": "", "source": "measured",
             "words": "measured: a VLAN database"}


def _apply(name: str, *operations, vlan_database=HAS_VLANS) -> dict:
    from modules.nsot import intent_patch
    return intent_patch.apply(_doc(name), _patch(name, *operations), vlan_database)


def _refused(got: dict, status: int, stage: str) -> str:
    assert got["ok"] is False, got
    assert (got["status"], got["stage"]) == (status, stage), got
    return got["error"]


# ── the model ────────────────────────────────────────────────────────────────

class TestThePatchIsStrict:
    @pytest.mark.parametrize("operation, field", [
        ({"op": "add_vlan", "vlan": "40"}, "vlan"),                 # no coercion
        ({"op": "add_vlan", "vlan": True}, "vlan"),
        ({"op": "add_ospf_network", "process": "1", "prefix": "192.0.2.0/24", "area": 0},
         "process"),
        ({"op": "shutdown", "interface": "Gi0/1", "reason": "x"}, "reason"),   # extra field
        ({"op": "rename_interface", "interface": "Gi0/1"}, "op"),
    ])
    def test_a_field_outside_the_model_is_refused_by_name(self, operation, field):
        from modules.nsot import intent_patch
        patch, refusal = intent_patch.parse(_patch("s1", operation))
        assert patch is None
        assert refusal["status"] == 400 and refusal["stage"] == "patch"
        assert "operations.0" in refusal["error"]
        if field != "op":
            assert field in refusal["error"]

    def test_an_empty_patch_and_one_too_long_are_refused(self):
        from modules.nsot import intent_patch
        assert intent_patch.parse(_patch("s1"))[1]["stage"] == "patch"
        many = [{"op": "shutdown", "interface": f"Loopback{n}"}
                for n in range(intent_patch.MAX_OPERATIONS + 1)]
        _p, refusal = intent_patch.parse(_patch("s1", *many))
        assert "operations" in refusal["error"]
        assert intent_patch.parse(_patch("s1", *many[:-1]))[0] is not None

    @pytest.mark.parametrize("description, words", [
        ("x" * 241, "at most 240"),
        ("tab\there", "printable ASCII"),
        (" leading", "begin or end with a space"),
        ("", "at least 1"),
    ])
    def test_a_description_the_cli_cannot_take_is_refused(self, description, words):
        from modules.nsot import intent_patch
        _p, refusal = intent_patch.parse(_patch("s1", {
            "op": "set_description", "interface": "Gi0/1", "description": description}))
        assert words in refusal["error"], refusal

    def test_a_description_of_240_printable_characters_is_taken(self):
        from modules.nsot import intent_patch
        patch, refusal = intent_patch.parse(_patch("s1", {
            "op": "set_description", "interface": "Gi0/1", "description": "y" * 240}))
        assert refusal is None and patch.operations[0].description == "y" * 240

    @pytest.mark.parametrize("vlan", [1, 1002, 1005])
    def test_a_default_vlan_is_refused(self, vlan):
        from modules.nsot import intent_patch
        for op in ("add_vlan", "remove_vlan"):
            _p, refusal = intent_patch.parse(_patch("s1", {"op": op, "vlan": vlan}))
            assert f"VLAN {vlan} is one the device holds by default" in refusal["error"]

    @pytest.mark.parametrize("operation", [
        {"op": "add_vlan", "vlan": 4095},
        {"op": "add_vlan", "vlan": 40, "name": "two words"},
        {"op": "add_vlan", "vlan": 40, "name": "N" * 33},
        {"op": "shutdown", "interface": "Gigabit Ethernet0/1"},
    ])
    def test_a_vlan_or_interface_outside_its_rule_is_refused(self, operation):
        from modules.nsot import intent_patch
        assert intent_patch.parse(_patch("s1", operation))[1]["stage"] == "patch"

    def test_a_patch_is_read_from_json_text(self):
        from modules.nsot import intent_patch
        patch, refusal = intent_patch.parse(json.dumps(_patch("s1", {"op": "add_vlan",
                                                                     "vlan": 40})))
        assert refusal is None and patch.operations[0].vlan == 40

    def test_every_operation_offered_has_one_implementation(self):
        """A new operation in the union with no implementation (or one implemented and not
        offered) fails here, before any patch meets it."""
        from typing import get_args

        from modules.nsot import intent_patch
        union = get_args(get_args(intent_patch.Operation)[0])
        assert set(union) == set(intent_patch._APPLY)
        assert len(intent_patch.OPERATIONS) == len(set(intent_patch.OPERATIONS)) == 8


class TestTheNetworkPrefix:
    """IPv4 and IPv6 side by side: an OSPF network statement is OSPFv2's, so an IPv6 prefix
    is refused saying so, by name, never accepted and never failing silently."""

    @pytest.mark.parametrize("prefix, kept", [
        ("192.0.2.0/24", "192.0.2.0/24"),
        ("198.51.100.7/32", "198.51.100.7/32"),
        ("198.51.100.7", "198.51.100.7/32"),
    ])
    def test_an_ipv4_network_is_taken(self, prefix, kept):
        from modules.nsot import intent_patch
        patch, refusal = intent_patch.parse(_patch("r2", {
            "op": "add_ospf_network", "process": 1, "prefix": prefix, "area": 0}))
        assert refusal is None and patch.operations[0].prefix == kept

    @pytest.mark.parametrize("prefix", ["2001:db8:3::/64", "2001:DB8::1/128"])
    def test_an_ipv6_prefix_is_refused_naming_ospfv3(self, prefix):
        from modules.nsot import intent_patch
        for op in ("add_ospf_network", "remove_ospf_network"):
            _p, refusal = intent_patch.parse(_patch("r2", {
                "op": op, "process": 1, "prefix": prefix, "area": 0}))
            assert "is an IPv6 prefix" in refusal["error"]
            assert "OSPFv3 joins an interface to an area" in refusal["error"]

    def test_host_bits_are_refused_naming_the_network(self):
        from modules.nsot import intent_patch
        _p, refusal = intent_patch.parse(_patch("r2", {
            "op": "add_ospf_network", "process": 1, "prefix": "192.0.2.9/24", "area": 0}))
        assert "has host bits set; its network is 192.0.2.0/24" in refusal["error"]
        _p, refusal = intent_patch.parse(_patch("r2", {
            "op": "add_ospf_network", "process": 1, "prefix": "2001:db8::1/64", "area": 0}))
        assert "is an IPv6 prefix" in refusal["error"]

    @pytest.mark.parametrize("area, ok", [(0, True), ("0.0.0.10", True), ("10", True),
                                          ("backbone", False), (-1, False),
                                          (4294967296, False)])
    def test_the_area_is_a_number_or_a_dotted_quad(self, area, ok):
        from modules.nsot import intent_patch
        _p, refusal = intent_patch.parse(_patch("r2", {
            "op": "add_ospf_network", "process": 1, "prefix": "192.0.2.0/24", "area": area}))
        assert (refusal is None) is ok, refusal


# ── each operation ───────────────────────────────────────────────────────────

class TestEachOperation:
    def test_apply_is_pure(self):
        from modules.nsot import intent_patch
        doc = _doc("s1")
        before = copy.deepcopy(doc)
        got = intent_patch.apply(doc, _patch("s1", {"op": "add_vlan", "vlan": 40},
                                             {"op": "shutdown", "interface": "Gi0/1"}),
                                 HAS_VLANS)
        assert got["ok"] and doc == before and got["doc"] != before

    def test_set_description_changes_that_interface_alone(self):
        got = _apply("s1", {"op": "set_description", "interface": "Gi0/1",
                            "description": "uplink to edge1"})
        expected = _doc("s1")
        _iface(expected, "GigabitEthernet0/1")["description"] = "uplink to edge1"
        assert got["ok"] and got["doc"] == expected
        assert got["changes"] == [{"operation": 0, "op": "set_description", "changed": True,
                                   "device_keeps": False, "summary":
                                   "GigabitEthernet0/1: description 'uplink to edge1' "
                                   "(was '')"}]

    def test_clear_description_says_the_device_keeps_it(self):
        got = _apply("s1", {"op": "clear_description", "interface": "GigabitEthernet1/0"})
        expected = _doc("s1")
        _iface(expected, "GigabitEthernet1/0")["description"] = ""
        assert got["doc"] == expected
        assert got["changes"][0]["device_keeps"] is True
        again = _apply("s1", {"op": "clear_description", "interface": "Gi0/1"})
        assert again["changes"][0]["changed"] is False and again["changed"] is False
        assert again["changes"][0]["device_keeps"] is False

    @pytest.mark.parametrize("op, shutdown", [("shutdown", True), ("no_shutdown", False)])
    def test_shutdown_and_no_shutdown_set_one_key_and_clear_the_other(self, op, shutdown):
        got = _apply("s1", {"op": op, "interface": "Gi1/1"})
        expected = _doc("s1")
        entry = _iface(expected, "GigabitEthernet1/1")
        entry["shutdown"], entry["no_shutdown"] = shutdown, not shutdown
        assert got["doc"] == expected and got["changed"]

    def test_a_shut_interface_brought_up_holds_no_shutdown_alone(self):
        from modules.nsot import intent_patch
        down = _apply("s1", {"op": "shutdown", "interface": "Gi1/1"})["doc"]
        up = intent_patch.apply(down, _patch("s1", {"op": "no_shutdown",
                                                    "interface": "Gi1/1"}))
        entry = _iface(up["doc"], "GigabitEthernet1/1")
        assert (entry["shutdown"], entry["no_shutdown"]) == (False, True)
        same = intent_patch.apply(up["doc"], _patch("s1", {"op": "no_shutdown",
                                                           "interface": "Gi1/1"}))
        assert same["changed"] is False

    def test_add_vlan_lands_in_number_order(self):
        got = _apply("s1", {"op": "add_vlan", "vlan": 15, "name": "PRINTERS"})
        assert [v["id"] for v in got["doc"]["vlans"]] == ["10", "15", "20", "30"]
        assert got["doc"]["vlans"][1] == {"extra": [], "id": "15", "name": "PRINTERS"}
        expected = _doc("s1")
        del got["doc"]["vlans"][1]
        assert got["doc"] == expected

    def test_add_vlan_to_an_intent_with_none(self):
        """A switch's intent holding no VLAN takes one. It was r2's (C1692): the router's
        intent holds `vlans: []` as well, and a VLAN added there would reach a deploy as
        `vlan 40`; with no VLAN database given, it is refused."""
        from modules.nsot import intent_patch
        doc = _doc("s1")
        doc["vlans"] = []
        got = intent_patch.apply(doc, _patch("s1", {"op": "add_vlan", "vlan": 40}), HAS_VLANS)
        assert got["doc"]["vlans"] == [{"extra": [], "id": "40", "name": ""}]
        assert _doc("r2")["vlans"] == []
        refused = _apply("r2", {"op": "add_vlan", "vlan": 40}, vlan_database=None)
        assert _refused(refused, 409, "capability").startswith(
            "operations[0] adds VLAN 40, and whether r2 (platform not known, device type not "
            "named) has a VLAN database is not declared and not measured")

    def test_add_vlan_already_held_changes_nothing(self):
        for op in ({"op": "add_vlan", "vlan": 20}, {"op": "add_vlan", "vlan": 20,
                                                    "name": "USERS"}):
            got = _apply("s1", op)
            assert got["ok"] and got["changed"] is False and got["doc"] == _doc("s1")

    def test_remove_vlan_undoes_add_vlan(self):
        from modules.nsot import intent_patch
        added = _apply("s1", {"op": "add_vlan", "vlan": 40, "name": "GUESTS"})["doc"]
        got = intent_patch.apply(added, _patch("s1", {"op": "remove_vlan", "vlan": 40}))
        assert got["doc"] == _doc("s1")
        assert got["changes"][0]["device_keeps"] is True

    def test_add_ospf_network_writes_the_packs_fields(self):
        got = _apply("r2", {"op": "add_ospf_network", "process": 1,
                            "prefix": "192.0.2.0/24", "area": 0})
        expected = _doc("r2")
        expected["routing"]["ospf"][0]["areas"] = [
            {"id": "0", "networks": [{"address": "192.0.2.0", "wildcard": "0.0.0.255"}]}]
        assert got["doc"] == expected
        assert got["changes"][0]["summary"] == ("OSPF 1: network 192.0.2.0 0.0.0.255 area 0 "
                                                "added")

    def test_a_second_network_in_one_area_joins_it(self):
        got = _apply("r2", {"op": "add_ospf_network", "process": 1,
                            "prefix": "192.0.2.0/24", "area": 0},
                     {"op": "add_ospf_network", "process": 1,
                      "prefix": "198.51.100.0/30", "area": "0.0.0.0"})
        areas = got["doc"]["routing"]["ospf"][0]["areas"]
        assert areas == [{"id": "0", "networks": [
            {"address": "192.0.2.0", "wildcard": "0.0.0.255"},
            {"address": "198.51.100.0", "wildcard": "0.0.0.3"}]}]

    @pytest.mark.parametrize("prefix, area", [("10.255.3.0/24", 0), ("10.255.3.0/24", "0.0.0.0"),
                                              ("10.255.1.12/32", 0)])
    def test_add_a_network_already_held_as_a_line_changes_nothing(self, prefix, area):
        got = _apply("r2", {"op": "add_ospf_network", "process": 1, "prefix": prefix,
                            "area": area})
        assert got["ok"] and got["changed"] is False and got["doc"] == _doc("r2")

    def test_remove_ospf_network_removes_the_line(self):
        got = _apply("r2", {"op": "remove_ospf_network", "process": 1,
                            "prefix": "10.255.3.0/24", "area": 0})
        expected = _doc("r2")
        expected["routing"]["ospf"][0]["networks"] = ["network 10.255.1.12 0.0.0.0 area 0"]
        assert got["doc"] == expected and got["changes"][0]["device_keeps"] is True

    def test_remove_ospf_network_removes_the_packs_field(self):
        from modules.nsot import intent_patch
        added = _apply("r2", {"op": "add_ospf_network", "process": 1,
                              "prefix": "192.0.2.0/24", "area": 0})["doc"]
        got = intent_patch.apply(added, _patch("r2", {"op": "remove_ospf_network",
                                                      "process": 1,
                                                      "prefix": "192.0.2.0/24", "area": 0}))
        proc = got["doc"]["routing"]["ospf"][0]
        assert proc["areas"] == [{"id": "0", "networks": []}]
        assert proc["networks"] == _doc("r2")["routing"]["ospf"][0]["networks"]


# ── refusals: both operands ──────────────────────────────────────────────────

class TestRefusalsNameBothOperands:
    def test_an_interface_the_intent_lacks(self):
        error = _refused(_apply("r2", {"op": "shutdown", "interface": "Gi9"}), 409, "intent")
        assert "'Gi9'" in error
        assert "it holds Loopback0, GigabitEthernet1, GigabitEthernet2, GigabitEthernet3" \
            in error

    def test_a_vlan_the_intent_lacks(self):
        error = _refused(_apply("s1", {"op": "remove_vlan", "vlan": 99}), 409, "intent")
        assert "removes VLAN 99" in error and "it holds 10, 20, 30" in error

    def test_a_vlan_still_in_use(self):
        error = _refused(_apply("s1", {"op": "remove_vlan", "vlan": 10}), 409, "intent")
        assert "GigabitEthernet1/0 (an access port in it)" in error
        assert "Vlan10 (its interface)" in error

    def test_a_vlan_added_under_another_name(self):
        error = _refused(_apply("s1", {"op": "add_vlan", "vlan": 20, "name": "STAFF"}),
                         409, "intent")
        assert "named 'STAFF'" in error and "VLAN 20 named 'USERS'" in error

    def test_an_ospf_process_the_intent_lacks(self):
        op = {"op": "add_ospf_network", "process": 2, "prefix": "192.0.2.0/24", "area": 0}
        error = _refused(_apply("r2", op), 409, "intent")
        assert "OSPF process 2" in error and "it holds 1" in error
        error = _refused(_apply("s1", op), 409, "intent")
        assert "it holds none" in error

    def test_a_statement_the_process_lacks(self):
        error = _refused(_apply("r2", {"op": "remove_ospf_network", "process": 1,
                                       "prefix": "192.0.2.0/24", "area": 0}), 409, "intent")
        assert "removes network 192.0.2.0 0.0.0.255 area 0" in error
        assert ("it holds network 10.255.1.12 0.0.0.0 area 0; "
                "network 10.255.3.0 0.0.0.255 area 0") in error

    def test_one_network_in_two_areas(self):
        for op in ("add_ospf_network", "remove_ospf_network"):
            error = _refused(_apply("r2", {"op": op, "process": 1, "prefix": "10.255.3.0/24",
                                           "area": 1}), 409, "intent")
            assert "network 10.255.3.0 0.0.0.255 area 1" in error
            assert "network 10.255.3.0 0.0.0.255 area 0" in error

    def test_a_patch_for_another_device(self):
        from modules.nsot import intent_patch
        got = intent_patch.apply(_doc("s1"), _patch("edge1", {"op": "add_vlan", "vlan": 40}))
        error = _refused(got, 400, "patch")
        assert "'edge1'" in error and "'s1'" in error
        got = intent_patch.patched_text("s1", _text("s1.yml"),
                                        _patch("edge1", {"op": "add_vlan", "vlan": 40}))
        assert "'edge1'" in _refused(got, 400, "patch")

    @pytest.mark.parametrize("ops, words", [
        (({"op": "shutdown", "interface": "Gi0/1"},
          {"op": "no_shutdown", "interface": "GigabitEthernet0/1"}),
         "the admin state of GigabitEthernet0/1"),
        (({"op": "set_description", "interface": "Gi0/1", "description": "a"},
          {"op": "clear_description", "interface": "gi0/1"}),
         "the description of GigabitEthernet0/1"),
        (({"op": "add_vlan", "vlan": 40}, {"op": "remove_vlan", "vlan": 40}), "VLAN 40"),
    ])
    def test_two_operations_deciding_one_thing(self, ops, words):
        error = _refused(_apply("s1", *ops), 400, "patch")
        assert "operations[0]" in error and "operations[1]" in error and words in error

    def test_a_refused_operation_changes_nothing_before_it(self):
        from modules.nsot import intent_patch
        doc = _doc("s1")
        got = intent_patch.apply(doc, _patch("s1", {"op": "add_vlan", "vlan": 40},
                                             {"op": "shutdown", "interface": "Gi9/9"}),
                                 HAS_VLANS)
        assert got["ok"] is False and got["operation"] == 1 and doc == _doc("s1")

    def test_a_hand_formatted_document_is_refused(self):
        from modules.nsot import intent_patch
        text = "# a person's note\n" + _text("s1.yml")
        got = intent_patch.patched_text("s1", text, _patch("s1", {"op": "add_vlan",
                                                                  "vlan": 40}))
        assert "hand-formatted" in _refused(got, 409, "format")


class TestTheEditorsValidator:
    def test_the_patched_intent_is_refused_by_the_validator(self):
        """A description the editor refuses (C428: a run's notes) is refused with the
        validator's own words, and nothing else lets it through."""
        from modules.nsot import intent_edit, intent_patch
        got = intent_patch.patched_text("s1", _text("s1.yml"), _patch("s1", {
            "op": "set_description", "interface": "Gi0/1", "description": "smoke run"}))
        assert got["ok"] is False and got["refused_by"] == "validator"
        assert got["stage"] == "schema" and got["line"]
        expected = _doc("s1")
        _iface(expected, "GigabitEthernet0/1")["description"] = "smoke run"
        from modules.nsot import hostvars
        own = intent_edit.validate("s1", hostvars.to_yaml(expected))
        assert own["ok"] is False and own["error"] in got["error"]

    def test_the_validator_runs_on_every_result(self, monkeypatch):
        from modules.nsot import intent_edit, intent_patch
        seen = []
        real = intent_edit.validate

        def watch(hostname, text, list_name=""):
            seen.append(text)
            return real(hostname, text, list_name)
        monkeypatch.setattr(intent_edit, "validate", watch)
        got = intent_patch.patched_text("s1", _text("s1.yml"),
                                        _patch("s1", {"op": "add_vlan", "vlan": 40}),
                                        vlan_database=HAS_VLANS)
        assert got["ok"] and seen[-1] == got["text"]

    def test_a_committed_intent_the_validator_refuses_is_named_as_such(self):
        from modules.nsot import intent_patch
        text = _text("s1.yml").replace("description: h1 - VLAN 10", "description: smoke")
        got = intent_patch.patched_text("s1", text, _patch("s1", {"op": "add_vlan",
                                                                  "vlan": 40}))
        assert got["refused_by"] == "validator"
        assert "committed intent is refused by the editor's check before the patch" \
            in got["error"]

    def test_the_patched_text_is_the_serialisers_and_parses_to_the_patched_document(self):
        from modules.nsot import intent_patch
        ops = ({"op": "add_vlan", "vlan": 40}, {"op": "shutdown", "interface": "Gi0/1"})
        got = intent_patch.patched_text("s1", _text("s1.yml"), _patch("s1", *ops),
                                        vlan_database=HAS_VLANS)
        expected = _doc("s1")
        expected["vlans"].append({"extra": [], "id": "40", "name": ""})
        _iface(expected, "GigabitEthernet0/1").update(shutdown=True, no_shutdown=False)
        assert yaml.safe_load(got["text"]) == expected and got["was"] == _text("s1.yml")


# ── the editor's preview and commit, on a real repository ────────────────────

def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=True).stdout


DESCRIBE = {"op": "set_description", "interface": "Gi0/1", "description": "uplink to edge1"}


class TestThePreview:
    def test_preview_receives_exactly_the_patched_intent(self, host, monkeypatch):
        from modules.nsot import intent_edit, intent_patch
        handed = []
        real = intent_edit.preview

        def watch(list_name, hostname, text):
            handed.append((list_name, hostname, text))
            return real(list_name, hostname, text)
        monkeypatch.setattr(intent_edit, "preview", watch)
        got = intent_patch.preview("Lab", "s1", _patch("s1", DESCRIBE))
        expected = _doc("s1")
        _iface(expected, "GigabitEthernet0/1")["description"] = "uplink to edge1"
        assert len(handed) == 1
        list_name, hostname, text = handed[0]
        assert (list_name, hostname) == ("Lab", "s1")
        assert yaml.safe_load(text) == expected and text == got["yaml"]
        committed = _git(host["repo"], "show", "HEAD:host_vars/s1.yml")
        assert committed == _text("s1.yml")
        assert got["base"] == _git(host["repo"], "rev-parse", "HEAD:host_vars/s1.yml").strip()

    def test_the_preview_is_the_editors_answer(self, host):
        from modules.nsot import intent_patch
        got = intent_patch.preview("Lab", "s1", _patch("s1", DESCRIBE))
        assert got["ok"] and got["status"] == 200 and got["changed"] is True, got
        assert " description uplink to edge1" in got["rendered"].splitlines()
        diff = got["vs_intent"].splitlines()
        added = [l[1:].strip() for l in diff if l.startswith("+") and not l.startswith("+++")]
        removed = [l for l in diff if l.startswith("-") and not l.startswith("---")]
        assert (added, removed) == (["description uplink to edge1"], [])
        assert got["document_changed"] is True
        assert got["patch"]["operations"][0]["op"] == "set_description"

    def test_a_patch_that_changes_nothing_says_so_and_previews_nothing(self, host,
                                                                       monkeypatch):
        from modules.nsot import intent_edit, intent_patch
        from tests.test_vlan_capability import SWITCH_ANSWERS, measure
        measure("Lab", "s1", SWITCH_ANSWERS[0])          # s1's VLAN database, measured
        monkeypatch.setattr(intent_edit, "preview",
                            lambda *a: pytest.fail("previewed a patch that changes nothing"))
        got = intent_patch.preview("Lab", "s1", _patch("s1", {"op": "add_vlan", "vlan": 20}))
        assert got["ok"] and got["changed"] is False
        assert got["message"].startswith("Nothing to change")

    def test_a_refused_patch_previews_nothing(self, host, monkeypatch):
        from modules.nsot import intent_edit, intent_patch
        monkeypatch.setattr(intent_edit, "preview",
                            lambda *a: pytest.fail("previewed a refused patch"))
        got = intent_patch.preview("Lab", "s1", _patch("s1", {"op": "shutdown",
                                                              "interface": "Gi9/9"}))
        assert got["ok"] is False and got["stage"] == "intent" and got["base"]

    def test_a_removal_says_what_the_device_keeps(self, host):
        from modules.nsot import intent_patch
        got = intent_patch.preview("Lab", "r2", _patch("r2", {
            "op": "remove_ospf_network", "process": 1, "prefix": "10.255.3.0/24",
            "area": 0}))
        assert got["ok"], got
        assert "the device keeps what these remove" in got["device_keeps"]
        assert "network 10.255.3.0 0.0.0.255 area 0 removed" in got["device_keeps"]


class TestTheCommit:
    def test_the_commit_is_the_patched_intent_as_the_person(self, host):
        from modules.nsot import intent_patch
        shown = intent_patch.preview("Lab", "s1", _patch("s1", DESCRIBE))
        got = intent_patch.commit("Lab", "s1", _patch("s1", DESCRIBE), "describe the uplink",
                                  shown["base"], "a.person")
        assert got["ok"] and got["changed"], got
        assert _git(host["repo"], "show", "HEAD:host_vars/s1.yml") == shown["yaml"]
        log = _git(host["repo"], "log", "-1", "--format=%s%n%b")
        assert log.startswith("host_vars: s1 describe the uplink")
        assert "Actor: a.person" in log

    def test_intent_moved_since_the_preview_writes_nothing(self, host):
        from modules.nsot import intent_edit, intent_patch
        shown = intent_patch.preview("Lab", "s1", _patch("s1", DESCRIBE))
        opened = intent_edit.open_doc("Lab", "s1")
        other = opened["yaml"].replace("description: h2 - VLAN 20",
                                       "description: h2 - VLAN 20 desk")
        assert intent_edit.commit("Lab", "s1", other, "another person's edit",
                                  opened["base"], "someone")["ok"]
        head = _git(host["repo"], "rev-parse", "HEAD").strip()
        got = intent_patch.commit("Lab", "s1", _patch("s1", DESCRIBE), "describe",
                                  shown["base"], "a.person")
        assert got["status"] == 409 and got["stage"] == "moved"
        assert _git(host["repo"], "rev-parse", "HEAD").strip() == head

    def test_no_base_or_an_unknown_one_writes_nothing(self, host):
        from modules.nsot import intent_patch
        head = _git(host["repo"], "rev-parse", "HEAD").strip()
        assert _refused(intent_patch.commit("Lab", "s1", _patch("s1", DESCRIBE), "d", "",
                                            "a.person"), 400, "base")
        error = _refused(intent_patch.commit("Lab", "s1", _patch("s1", DESCRIBE), "d",
                                             "0" * 40, "a.person"), 409, "base")
        assert "000000000000" in error
        assert _git(host["repo"], "rev-parse", "HEAD").strip() == head

    def test_the_summary_is_the_persons(self, host):
        from modules.nsot import intent_patch
        shown = intent_patch.preview("Lab", "s1", _patch("s1", DESCRIBE))
        got = intent_patch.commit("Lab", "s1", _patch("s1", DESCRIBE), "  ", shown["base"],
                                  "a.person")
        assert got["ok"] is False and "summary is required" in got["error"]
