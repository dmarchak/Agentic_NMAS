"""Feature 7's egress and scope (PHASE8_PLAN 15.16, the operator's ruling of 2026-10-26: the
schema of allowed keys and the current values of the intent sections the request touches, for
the devices in scope; never a full intent document, never a secret-bearing key), on the
host's REAL committed documents (tests/fixtures/committed: r2's and s1's intent, each holding
some forty sections).

- What a sentence touches is read by code: interfaces in their written forms, VLANs after
  "vlan", networks as prefixes (an address and wildcard read as its prefix); IPv6 beside IPv4.
- The slice holds only the touched sections, with only their allowed keys, their current
  values read from the fixtures' YAML by this test's own code; what is named and not held is
  said. Every other leaf of the real documents, a planted description on an untouched
  interface, and a planted secret reference are absent from its bytes.
- The answer, before any preview: an operation on an interface, VLAN, network or device the
  request does not name is refused, as is one filling a field its op does not use; the patch's
  own rules then hold (an IPv6 prefix refused by name beside an IPv4 one that passes).
"""
import ipaddress
import json
import os

import yaml

from modules.ai import intent_words

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "committed")


def _doc(name: str) -> dict:
    with open(os.path.join(FIX, f"{name}.yml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _leaves(node, path=()):
    """Every scalar of *node* with its path."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, path + (str(k),))
    elif isinstance(node, list):
        for v in node:
            yield from _leaves(v, path)
    elif node is not None:
        yield path, str(node)


def _r2_statements():
    """r2's network statements as IOS wrote them, read here: [(prefix, area)]."""
    (proc,) = _doc("r2")["routing"]["ospf"]
    out = []
    for line in proc["networks"]:
        _n, address, wildcard, _a, area = line.split()
        width = 32 - int(ipaddress.IPv4Address(wildcard)).bit_length()
        out.append((str(ipaddress.IPv4Network(f"{address}/{width}", strict=False)), area))
    return out


# ── what a sentence touches ──────────────────────────────────────────────────

def test_interfaces_are_read_in_their_written_forms():
    t = intent_words.touched("describe Gi0/1 as uplink and shut GigabitEthernet 0/2, lo0 too")
    assert t["interfaces"] == ["GigabitEthernet0/1", "GigabitEthernet0/2", "Loopback0"]
    assert t["vlans"] == [] and t["networks"] == []


def test_a_vlan_is_a_vlan_and_vlan10_is_an_interface():
    t = intent_words.touched("add vlans 40 and 41, remove VLAN 30, describe Vlan10 as users")
    assert t["vlans"] == [40, 41, 30]
    assert t["interfaces"] == ["Vlan10"]


def test_networks_are_prefixes_ipv4_and_ipv6_side_by_side():
    t = intent_words.touched("add 192.0.2.0 0.0.0.255 and 198.51.100.4/30 to OSPF area 0, "
                             "and 2001:db8:10::/64")
    assert t["networks"] == ["192.0.2.0/24", "198.51.100.4/30", "2001:db8:10::/64"]
    assert t["interfaces"] == [], "area 0 is no interface"


def test_a_sentence_naming_nothing_to_change_is_said():
    assert intent_words.nothing_named(intent_words.touched("shut the uplink on r3"))
    assert not intent_words.nothing_named(intent_words.touched("shut Gi2 on r3"))


# ── the slice: the touched sections, their allowed keys, their current values ─

def test_s1_s_slice_is_the_named_interfaces_and_vlans_with_their_values():
    doc = _doc("s1")
    t = intent_words.touched("describe GigabitEthernet0/2 as core, shut Gi0/3, rename VLAN 20 "
                             "and add vlan 99")
    got = intent_words.slice_of(doc, t)
    want = [{"name": i["name"], "description": str(i.get("description") or ""),
             "shutdown": bool(i.get("shutdown"))}
            for i in doc["interfaces"] if i["name"] in ("GigabitEthernet0/2",
                                                         "GigabitEthernet0/3")]
    assert got["interfaces"] == want and len(want) == 2
    assert want[0]["description"], "the floor: a real description is carried"
    (v20,) = [v for v in doc["vlans"] if str(v["id"]) == "20"]
    assert got["vlans"] == [{"id": "20", "name": str(v20["name"])}]
    assert got["not_held"] == ["VLAN 99"] and got["ospf"] == []


def test_r2_s_ospf_slice_holds_only_the_named_statement():
    (named, area), (other, _a2) = _r2_statements()
    got = intent_words.slice_of(_doc("r2"), intent_words.touched(f"remove {named} from OSPF"))
    assert got["ospf"] == [{"process": "1", "networks": [{"prefix": named, "area": area}]}]
    assert other not in json.dumps(got)
    got = intent_words.slice_of(_doc("r2"), intent_words.touched("add 192.0.2.0/24 area 0"))
    assert got["ospf"] == [{"process": "1", "networks": []}]
    assert got["not_held"] == ["the OSPF network 192.0.2.0/24"]


def test_an_interface_named_and_not_held_is_said():
    got = intent_words.slice_of(_doc("r2"), intent_words.touched("shut GigabitEthernet9"))
    assert got["interfaces"] == [] and got["not_held"] == ["interface GigabitEthernet9"]


def test_nothing_else_of_the_document_leaves():
    """Every leaf of both real documents outside the slice's own values is absent from the
    slice's bytes: the untouched interfaces' descriptions, the users, SNMP, NTP, logging, the
    secret references, OSPF's settings and the rest."""
    checked = 0
    for name, sentence in (("r2", "describe GigabitEthernet2 as to s4"),
                           ("s1", "shut Gi0/3 and remove vlan 30")):
        doc = _doc(name)
        doc["interfaces"][0]["description"] = "PLANTED circuit 7781-QX to the customer"
        refs = doc.get("secret_refs")
        assert isinstance(refs, list), type(refs)
        refs.append("PLANTED-secret-ref-key")
        got = intent_words.slice_of(doc, intent_words.touched(sentence))
        sent = json.dumps(got)
        kept = {v for _p, v in _leaves(got)}
        for path, value in _leaves(doc):
            # A value inside a carried one ("trunk" in a sent description) proves nothing.
            if any(value in k for k in kept) or len(value) < 4 or value in ("True", "False"):
                continue
            checked += 1
            assert value not in sent, (name, path, value)
        assert "PLANTED" not in sent
    assert checked >= 150, f"the floor: {checked} leaves checked"


def test_the_slice_reads_only_its_allowlisted_keys():
    """A key the allowlist does not name, planted inside a touched section, is not read."""
    doc = _doc("s1")
    gi = next(i for i in doc["interfaces"] if i["name"] == "GigabitEthernet0/2")
    gi["planted_key"] = "PLANTED-in-an-interface"
    gi["ipv4"] = "192.0.2.9 255.255.255.0"
    next(v for v in doc["vlans"] if str(v["id"]) == "20")["planted_key"] = "PLANTED-in-a-vlan"
    got = intent_words.slice_of(doc, intent_words.touched("shut Gi0/2 and remove vlan 20"))
    assert {k for i in got["interfaces"] for k in i} == set(intent_words.READS["interfaces"])
    assert {k for v in got["vlans"] for k in v} == set(intent_words.READS["vlans"])
    assert "PLANTED" not in json.dumps(got) and "192.0.2.9" not in json.dumps(got)


def test_a_document_that_is_not_one_gives_an_empty_slice():
    t = intent_words.touched("shut Gi2")
    assert intent_words.slice_of(None, t) == {"interfaces": [], "vlans": [], "ospf": [],
                                              "not_held": ["interface GigabitEthernet2"]}


# ── the answer, checked against the scope before any preview ─────────────────

def _op(op, **fields):
    base = {"op": op, "interface": "", "description": "", "vlan": 0, "vlan_name": "",
            "process": 0, "prefix": "", "area": ""}
    base.update(fields)
    return base


def _answer(*patches, outcome="answer"):
    """As the gateway reads a model's answer: its JSON text, validated strictly."""
    return intent_words.IntentChange.model_validate_json(json.dumps({
        "outcome": outcome, "question": "", "why_not": "",
        "patches": [{"hostname": h, "operations": list(ops)} for h, ops in patches]}))


def _scope(**sentences):
    return {h: intent_words.touched(s) for h, s in sentences.items()}


def test_each_operation_becomes_the_patch_s_own_shape():
    got = intent_words.to_patches(_answer(
        ("r2", [_op("set_description", interface="GigabitEthernet2", description="to s4"),
                _op("shutdown", interface="GigabitEthernet3"),
                _op("add_ospf_network", process=1, prefix="192.0.2.0/24", area="0")]),
        ("s1", [_op("add_vlan", vlan=40, vlan_name="LAB"), _op("remove_vlan", vlan=30)])),
        _scope(r2="describe Gi2 as to s4, shut Gi3, add 192.0.2.0/24 to OSPF",
               s1="add vlan 40 named LAB and remove vlan 30"))
    assert got["ok"] is True, got
    r2, s1 = (p.model_dump() for p in got["patches"])
    assert r2["operations"] == [
        {"op": "set_description", "interface": "GigabitEthernet2", "description": "to s4"},
        {"op": "shutdown", "interface": "GigabitEthernet3"},
        {"op": "add_ospf_network", "process": 1, "prefix": "192.0.2.0/24", "area": "0"}]
    assert s1["operations"] == [{"op": "add_vlan", "vlan": 40, "name": "LAB"},
                                {"op": "remove_vlan", "vlan": 30}]


def test_a_change_outside_what_the_request_names_is_refused_before_preview():
    scope = _scope(r2="shut Gi3 and remove vlan 30 and 192.0.2.0/24 from OSPF")
    for op, words in ((_op("shutdown", interface="GigabitEthernet2"),
                       "the interface 'GigabitEthernet2'"),
                      (_op("remove_vlan", vlan=31), "VLAN 31"),
                      (_op("remove_ospf_network", process=1, prefix="198.51.100.0/24",
                           area="0"), "the network '198.51.100.0/24'")):
        got = intent_words.to_patches(_answer(("r2", [op])), scope)
        assert got["ok"] is False
        assert got["error"] == (f"r2's operation 0 ({op['op']}) changes {words}, which the "
                                "request does not name"), got["error"]
    out = intent_words.to_patches(_answer(("r9", [_op("shutdown", interface="Gi3")])), scope)
    assert out["error"] == "the answer changes 'r9', a device outside the request (it names r2)"


def test_an_operation_filling_a_field_its_op_does_not_use_is_refused():
    got = intent_words.to_patches(_answer(
        ("r2", [_op("shutdown", interface="GigabitEthernet3", description="down for works")])),
        _scope(r2="shut Gi3"))
    assert got == {"ok": False, "error": "r2's operation 0 (shutdown) fills description, "
                   "which it does not use"}


def test_the_patch_s_own_rules_hold_an_ipv6_prefix_beside_an_ipv4_one():
    v4 = intent_words.to_patches(_answer(
        ("r2", [_op("add_ospf_network", process=1, prefix="192.0.2.0/24", area="0")])),
        _scope(r2="add 192.0.2.0/24 to OSPF"))
    assert v4["ok"] is True
    v6 = intent_words.to_patches(_answer(
        ("r2", [_op("add_ospf_network", process=1, prefix="2001:db8::/64", area="0")])),
        _scope(r2="add 2001:db8::/64 to OSPF"))
    assert v6["ok"] is False
    assert v6["error"].startswith("r2: The patch is refused: operations.0.add_ospf_network.prefix")
    assert "is an IPv6 prefix" in v6["error"] and "OSPFv3" in v6["error"]
