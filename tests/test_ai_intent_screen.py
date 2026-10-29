"""Feature 7's deterministic layer before and after the call (the operator's order of
2026-10-27; modules/ai/intent_words.py, modules/ai/intent_names.py), on the host's REAL
committed s1 (tests/fixtures/committed/s1.yml) and its measured neighbours; no call, no network.

- **Quoted text as placeholders** (item a): which quotes count (double always, single only
  where it cannot be an apostrophe), nesting, empty quotes, an unbalanced quote and a typed
  placeholder refused before any call; after the answer, a placeholder invented, altered,
  dropped or put in a field that holds no text is refused, naming it, and the real text is
  put back once (a quoted "<<text_1>>" stays itself).
- **Questions before any call** (item b): both ends of a link (with another device of the
  network, never a pattern), alternatives (VLANs, with which can be added; interfaces, with
  their state), an OSPF network with no area, a description with no text.
- **Target state and the vocabulary** (C1890, the operator's design): only a definite
  reference is resolved; "a trunk", "an access port", "as a trunk", "to a routed port" stay
  as words, and a change no operation makes is refused naming the operations there are.
- **C1904**: a description's value after "description of/on X to" is never resolved.
- **The judge**: Mercury's question passes a case expecting "ask", its vocabulary refusal one
  expecting "refuse"; the case files' signals fire on no case expecting only an answer.
"""
import json
import os

import pytest
import yaml

from modules.ai import cases, intent_names, intent_words
from modules.ai.intent_words import IntentChange
from tests.registered_networks import register

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "tests", "fixtures", "committed", "s1.yml"), encoding="utf-8") as fh:
    S1 = yaml.safe_load(fh)
DIR = os.path.join(ROOT, "tests", "fixtures", "ai_cases", "intent_patch")

#: s1's links as the host's Topology read measured them (2026-10-26), with their far ends.
FAR = {"ports": {
    "GigabitEthernet0/2": [{"name": "r1", "role": "router", "by": "observed (LLDP)",
                            "port": "GigabitEthernet3"}],
    "GigabitEthernet0/3": [{"name": "s2", "role": "switch", "by": "observed (LLDP)",
                            "port": "GigabitEthernet0/3"}]}, "said": []}
DEVICES = {"r1": "router", "s1": "switch", "s2": "switch", "r2": "router"}


@pytest.fixture(autouse=True)
def _inventory(monkeypatch, tmp_path):
    monkeypatch.setattr(intent_names, "_devices", lambda network: dict(DEVICES))
    # Lab is a network (C1903: a read naming no network raises).
    register(monkeypatch, tmp_path, "Lab")


def _resolve(sentence, device="s1"):
    return intent_names.resolve("Lab", device, S1, sentence, neighbours=FAR, endpoints=[])


# ── quoted text, held back ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sentence,masked,quoted", [
    ('describe Gi0/1 as "a  b"', "describe Gi0/1 as <<text_1>>", {"<<text_1>>": "a  b"}),
    ("describe Gi0/1 as “desk 4”", "describe Gi0/1 as <<text_1>>", {"<<text_1>>": "desk 4"}),
    ("describe Gi0/1 as 'Bob's desk'", "describe Gi0/1 as <<text_1>>",
     {"<<text_1>>": "Bob's desk"}),
    ("describe Gi0/1 as ‘spare’", "describe Gi0/1 as <<text_1>>", {"<<text_1>>": "spare"}),
    ("set Gi0/2's description to x and shut Gi1/0's port", None, {}),
    ('describe Gi0/1 as “spare for \'rack 4\', "do not use"”', "describe Gi0/1 as <<text_1>>",
     {"<<text_1>>": 'spare for \'rack 4\', "do not use"'}),
    ("describe Gi0/1 as “a “b” c”", "describe Gi0/1 as <<text_1>>", {"<<text_1>>": "a “b” c"}),
    ('describe Gi0/1 as "x" and Gi0/2 as "y"', "describe Gi0/1 as <<text_1>> and Gi0/2 as "
     "<<text_2>>", {"<<text_1>>": "x", "<<text_2>>": "y"}),
    ('describe Gi0/1 as ""', None, {}),
    ('describe Gi0/1 as "<<text_1>>"', "describe Gi0/1 as <<text_1>>",
     {"<<text_1>>": "<<text_1>>"}),
], ids=["straight-double-spaces-kept", "curly-double", "single-with-an-apostrophe-inside",
        "curly-single", "apostrophes-are-no-quotes", "nested-other-kinds", "curly-nested",
        "two-in-order", "empty-stays", "a-placeholder-inside-quotes"])
def test_quoted_text_becomes_placeholders_by_the_rules(sentence, masked, quoted):
    got = intent_words.hold_quotes(sentence)
    assert got["ok"], got
    assert got["sentence"] == (sentence if masked is None else masked)
    assert got["quoted"] == quoted


@pytest.mark.parametrize("sentence,error,words", [
    ('describe Gi0/1 as "spare port', "unbalanced_quote", "opens a quote it does not close"),
    ("describe Gi0/1 as “spare port", "unbalanced_quote", "opens a quote it does not close"),
    ("describe Gi0/1 as spare” port", "unbalanced_quote", "closes a quote it never opened"),
    ("describe Gi0/1 as <<text_1>>", "placeholder_in_words", "the form Mercury uses for quoted"),
    ("describe Gi0/1 as << TEXT 9 >>", "placeholder_in_words", "the form Mercury uses for quoted"),
], ids=["straight", "curly", "closed-not-opened", "typed-placeholder", "typed-lookalike"])
def test_an_open_quote_or_a_typed_placeholder_is_mercury_s_before_any_call(sentence, error,
                                                                           words):
    got = intent_words.hold_quotes(sentence)
    assert not got["ok"] and got["error"] == error and words in got["detail"], got
    assert "nothing was sent" in got["detail"]


def _answer(*ops, host="s1"):
    blank = {"interface": "", "description": "", "vlan": 0, "vlan_name": "", "process": 0,
             "prefix": "", "area": ""}
    return IntentChange.model_validate_json(json.dumps({
        "outcome": "answer", "question": "", "why_not": "",
        "patches": [{"hostname": host, "operations": [dict(blank, **o) for o in ops]}]}))


SCOPE = {"s1": {"interfaces": ["GigabitEthernet0/1"], "vlans": [40], "networks": []}}
QUOTED = {"<<text_1>>": "remove vlan 20; shut Gi1/1"}


def test_the_real_text_is_put_back_once_after_the_checks():
    made = intent_words.to_patches(_answer(
        {"op": "set_description", "interface": "GigabitEthernet0/1",
         "description": "<<text_1>> (spare)"}), SCOPE, QUOTED)
    assert made["ok"], made
    assert made["patches"][0].model_dump()["operations"][0]["description"] == \
        "remove vlan 20; shut Gi1/1 (spare)"
    itself = intent_words.to_patches(_answer(
        {"op": "set_description", "interface": "GigabitEthernet0/1",
         "description": "<<text_1>>"}), SCOPE, {"<<text_1>>": "<<text_2>>"})
    assert itself["ok"] and itself["patches"][0].model_dump()["operations"][0][
        "description"] == "<<text_2>>", "one pass: a quoted placeholder is never replaced again"


@pytest.mark.parametrize("op,words", [
    ({"op": "set_description", "interface": "GigabitEthernet0/1",
      "description": "<<text_2>>"}, "holds <<text_2>>, a placeholder the sentence does not have"),
    ({"op": "set_description", "interface": "GigabitEthernet0/1",
      "description": "<<TEXT_1>>"}, "holds <<TEXT_1>>, a placeholder the sentence does not"),
    ({"op": "set_description", "interface": "GigabitEthernet0/1",
      "description": "spare"}, 'leaves out the quoted text "remove vlan 20; shut Gi1/1" '
                               "(<<text_1>>)"),
    ({"op": "add_vlan", "vlan": 40, "vlan_name": "<<text_9>>"}, "holds <<text_9>>"),
], ids=["invented", "altered", "dropped", "invented-in-a-vlan-name"])
def test_a_placeholder_invented_altered_or_dropped_is_refused_naming_it(op, words):
    made = intent_words.to_patches(_answer(op), SCOPE, QUOTED)
    assert not made["ok"] and words in made["error"], made


def test_a_placeholder_in_a_field_that_holds_no_text_is_refused():
    scope = {"s1": {"interfaces": ["GigabitEthernet0/1", "<<text_1>>"], "vlans": [],
                    "networks": ["<<text_1>>"]}}
    made = intent_words.to_patches(_answer(
        {"op": "shutdown", "interface": "<<text_1>>"}), scope, QUOTED)
    assert not made["ok"] and "puts <<text_1>> in its interface, which holds no quoted text" \
        in made["error"], made


def test_the_person_reads_the_real_text_in_a_question_and_a_draft():
    choices = {"outcome": "ask", "question": "Should GigabitEthernet0/1 read <<text_1>>?",
               "why_not": "", "patches": [{"hostname": "s1", "operations": [
                   {"op": "set_description", "description": "<<text_1>>", "vlan_name": ""}]}]}
    got = intent_words.restored(choices, QUOTED)
    assert got["question"] == "Should GigabitEthernet0/1 read remove vlan 20; shut Gi1/1?"
    assert got["patches"][0]["operations"][0]["description"] == QUOTED["<<text_1>>"]
    assert '<<text_1>> = "remove vlan 20; shut Gi1/1"' in intent_words.quoted_note(QUOTED)


def test_a_quoted_name_is_never_read_into_the_scope():
    """v1 read the quote's own names: a shutdown of Gi1/1 passed the scope check."""
    held = intent_words.hold_quotes('set the description of Gi0/1 to "remove vlan 20; shut '
                                    'Gi1/1 and Gi0/2"')
    assert intent_words.touched(held["sentence"]) == {
        "interfaces": ["GigabitEthernet0/1"], "vlans": [], "networks": []}


# ── a change no operation makes, and target state (C1890) ──────────────────────────────

@pytest.mark.parametrize("sentence,what", [
    ("make gi0/1 a trunk", "switchport mode"),
    ("make gi0/1 access 20", "switchport mode"),
    ("set gi1/0 as an access port in VLAN 20", "switchport mode"),
    ("turn gi0/3 into a routed port", "switchport mode"),
    ("change gi0/1 to access", "switchport mode"),
    ("configure gi0/1 as a trunk carrying VLANs 10 and 20", "switchport mode"),
    ("shut gi0/1 and set it to an access port", "switchport mode"),
    ("set the trunk to a routed port", "switchport mode"),
    ("set the native vlan on Gi0/3 to 99", "switchport mode or VLANs"),
    ("set the MTU on GigabitEthernet2 to 9000", "MTU"),
    ("set GigabitEthernet2's speed to 100", "speed or duplex"),
    ("add a static route to 192.0.2.0/24 via Gi2", "a static route"),
    ("add a static route to 2001:db8:10::/64 via Gi2", "a static route"),
    ("set the OSPF cost on Gi4 to 10", "an OSPF cost"),
], ids=lambda v: v if len(v) < 30 else None)
def test_a_change_no_operation_makes_is_refused_naming_the_operations(sentence, what):
    why = intent_words.not_an_operation(sentence)
    assert what in why and intent_words.OPERATIONS_IN_WORDS in why, why
    assert why.endswith("nothing was sent")


@pytest.mark.parametrize("sentence", [
    "describe Gi0/3 as trunk to s2 Gi0/3 - VRRP rides this",
    "set the description of Gi0/1 to access layer uplink",
    "desc Gi0/1 as mtu 9000 test port",
    "describe the trunk as trunk to s2 Gi0/3",
    "change gi0/3 trunk description to core",
    "shut Gi0/1, the speed test port",
    "add VLAN 40 named access",
    "add the address 192.0.2.1 to OSPF area 0",
    "add 2001:db8:10::/64 to OSPF area 0",
    "shut the trunk",
], ids=lambda v: v[:30])
def test_words_inside_a_value_or_beside_no_setting_refuse_nothing(sentence):
    assert intent_words.not_an_operation(sentence) == ""


@pytest.mark.parametrize("sentence", ["make GigabitEthernet0/1 a trunk",
                                      "set GigabitEthernet0/1 to an access port",
                                      "configure GigabitEthernet0/1 as a trunk",
                                      "move GigabitEthernet0/1 to a routed port",
                                      "make GigabitEthernet0/1 an uplink",
                                      "shut a host port"])
def test_an_indefinite_or_target_state_phrase_resolves_to_nothing(sentence):
    """C1890 (main35's case 27): "make gi0/1 a trunk" on s2 was sent as "make
    GigabitEthernet0/1 GigabitEthernet0/3"."""
    got = _resolve(sentence)
    assert got["ok"] and got["sentence"] == sentence and got["resolutions"] == [], got


@pytest.mark.parametrize("sentence,device,phrase,names", [
    ("shut the trunk", "s1", "the trunk", ["GigabitEthernet0/3"]),
    ("shut that trunk", "s1", "that trunk", ["GigabitEthernet0/3"]),
    ("shut s2's trunk", "s2", "trunk", ["GigabitEthernet0/3"]),
    ("shut the port to s1", "s2", "the port to s1", []),
    ("shut the port to s2", "s1", "the port to s2", ["GigabitEthernet0/3"]),
    ("shut the uplink to r1", "s1", "the uplink to r1", ["GigabitEthernet0/2"]),
    ("shut all trunks", "s1", "all trunks", ["GigabitEthernet0/3"]),
], ids=["the", "that", "a-possessive-of-the-tab", "the-port-to-x-none-here", "the-port-to-x",
        "the-uplink-to-x", "all"])
def test_a_definite_reference_still_resolves(sentence, device, phrase, names):
    got = intent_names.resolve("Lab", device, S1, sentence, neighbours=FAR, endpoints=[])
    if names:
        assert got["ok"] and {"said": phrase, "to": names} == {
            k: got["resolutions"][0][k] for k in ("said", "to")}, got
    else:
        # s2's tab, given s1's document and s1's neighbours: nothing there faces s1, so the
        # definite reference is read and says it matches nothing (never left as words).
        assert not got["ok"] and got["unknown"]["said"] == phrase, got


def test_another_device_s_possessive_is_not_resolved_on_this_tab():
    got = _resolve("shut s2's trunk")
    assert got["ok"] and got["resolutions"] == [], got


@pytest.mark.parametrize("sentence,sent", [
    ("make gi0/1 the trunk", "make GigabitEthernet0/1 the trunk"),
    ("make gi0/1 the uplink", "make GigabitEthernet0/1 the uplink"),
    ("configure gi0/1 as the uplink to r1", "configure GigabitEthernet0/1 as the uplink to r1"),
    ("turn Gi0/1 into the host port", "turn GigabitEthernet0/1 into the host port"),
    ("shut gi0/1 and set it to the trunk", "shut GigabitEthernet0/1 and set it to the trunk"),
], ids=["make-the-trunk", "make-the-uplink", "as-the-uplink-to", "into-the-host-port",
        "set-it-to"])
def test_a_definite_reference_standing_as_the_state_wanted_stays_as_words(sentence, sent):
    """C1890's class with a definite article (2026-10-29): "make gi0/1 the trunk" on s1 was
    sent as "make GigabitEthernet0/1 GigabitEthernet0/3" and "configure gi0/1 as the trunk" as
    "... as GigabitEthernet0/3": the reference stood as the state wanted, never as ports. Only
    the interface named by its shape is rewritten; "the uplink" and "the host port", which
    no vocabulary refusal catches, reach the model as the person wrote them."""
    got = _resolve(sentence)
    assert got["ok"] and got["sentence"] == sent, got
    assert [r["to"] for r in got["resolutions"]] == [["GigabitEthernet0/1"]], got


@pytest.mark.parametrize("sentence,sent", [
    ("add vlan 30 to the trunk", "add vlan 30 to GigabitEthernet0/3"),
    ("set the trunk to a routed port", "set GigabitEthernet0/3 to a routed port"),
    ("shut Gi0/1 as well as the trunk", "shut GigabitEthernet0/1 as well as "
                                        "GigabitEthernet0/3"),
    ("set vlan 30 to the trunk", "set vlan 30 to GigabitEthernet0/3"),
], ids=["to-the-trunk", "the-subject", "as-well-as", "a-vlan-object"])
def test_a_definite_reference_naming_ports_beside_a_target_word_still_resolves(sentence, sent):
    """The other side of the line (C1890, 2026-10-29): "to" after a VLAN, the reference as
    the sentence's subject, "as well as", and a VLAN as the verb's object (never an interface)
    name ports, and are read."""
    got = _resolve(sentence)
    assert got["ok"] and got["sentence"] == sent, got


with open(os.path.join(ROOT, "tests", "fixtures", "committed", "r2.yml"), encoding="utf-8") as fh:
    R2_COMMITTED = yaml.safe_load(fh)


@pytest.mark.parametrize("device,sentence,sent", [
    ("s1", "make gi0/1 a trunk", "make GigabitEthernet0/1 a trunk"),
    ("s1", "shut gi 0/1", "shut GigabitEthernet0/1"),
    ("s1", "shut Gig0/1", "shut GigabitEthernet0/1"),
    ("s1", "shut lo 0", "shut Loopback0"),
    ("s1", "shut Vl10", "shut Vlan10"),
    ("r2", "shut Gi2", "shut GigabitEthernet2"),
    ("r2", "shut GigabitEthernet 3", "shut GigabitEthernet3"),
    ("r2", "shut gi1 and describe it as trunk 2", "shut GigabitEthernet1 and describe it as "
                                                  "trunk 2"),
], ids=["the-row", "ios-spaced", "ios-gig", "loopback", "svi", "iosxe-gi", "iosxe-spaced",
        "iosxe-value"])
def test_only_an_interface_by_its_shape_is_rewritten_on_ios_and_ios_xe(device, sentence, sent):
    """C1890's sentence and real interface forms on the host's committed s1 (IOS: slot/port)
    and r2 (IOS-XE: GigabitEthernet1 to 3): the shared table's abbreviations, spaced or not,
    become the device's own names; nothing else in the sentence moves."""
    doc = S1 if device == "s1" else R2_COMMITTED
    nb = FAR if device == "s1" else {"ports": {}, "said": []}
    got = intent_names.resolve("Lab", device, doc, sentence, neighbours=nb, endpoints=[])
    assert got["ok"] and got["sentence"] == sent, got


@pytest.mark.parametrize("sentence", [
    "shut trunk", "shut a trunk port", "shut port 1", "add vlan 10", "set the as 65001",
    "add 192.0.2.0/24 to ospf area 0", "add 2001:db8:10::/64 to ospf area 0", "set it to 10",
    "turn up 2 ports",
], ids=lambda v: v[:24])
def test_plain_words_and_numbers_stay_words(sentence):
    """Words with numbers beside them that are no interface's shape ("port 1", "as 65001",
    "area 0", an address), and nouns with no definite article, are never rewritten."""
    for device, doc in (("s1", S1), ("r2", R2_COMMITTED)):
        got = intent_names.resolve("Lab", device, doc, sentence, neighbours={
            "ports": {}, "said": []}, endpoints=[])
        assert got["ok"] and got["sentence"] == sentence and got["resolutions"] == [], got


@pytest.mark.parametrize("sentence,value", [
    ("set the description of Gi0/1 to uplink to r1", "uplink to r1"),
    ("set the description on Gi0/1 to the uplink to r1", "the uplink to r1"),
    ("change the description of GigabitEthernet0/1 to the trunk to s2", "the trunk to s2"),
    ("set the description of Gi0/1 to toward s2", "toward s2"),
    ("set the description on the port to h1 to the trunk", "the trunk"),
], ids=["of", "on-definite", "of-the-trunk", "toward", "on-a-reference"])
def test_a_description_value_after_description_of_x_to_is_never_resolved(sentence, value):
    """C1904, measured 2026-10-27 on ec01d2d5 (before this change): "set the description of
    Gi0/1 to uplink to r1" on s1 was given to the model as "... to GigabitEthernet0/2". The
    name before "to" is still read (Gi0/1, the port to h1)."""
    got = _resolve(sentence)
    assert got["ok"] and got["sentence"].endswith(" to " + value), got
    assert all(r["said"] not in value for r in got["resolutions"]), got["resolutions"]
    assert got["resolutions"] or "GigabitEthernet0/1" in sentence, "the name is still read"


# ── both ends of a link (C1908): one draft of both, or Mercury's question ─────────────

#: Each device's links as the host's reads give them (s1 and s2 by LLDP, r3 and r4 by their
#: /31), far ports included, for the reverse lookups `ends` makes.
LINKS = {
    "s1": FAR,
    "s2": {"ports": {"GigabitEthernet0/3": [{"name": "s1", "role": "switch",
                                             "by": "observed (LLDP)",
                                             "port": "GigabitEthernet0/3"}]}, "said": []},
    "r3": {"ports": {"GigabitEthernet4": [{"name": "r4", "role": "router",
                                           "by": "intent: the subnet 10.255.2.14/31",
                                           "port": "GigabitEthernet4"}]}, "said": []},
    "r4": {"ports": {"GigabitEthernet4": [{"name": "r3", "role": "router",
                                           "by": "intent: the subnet 10.255.2.14/31",
                                           "port": "GigabitEthernet4"}]}, "said": []},
}
ALL = dict(DEVICES, r3="router", r4="router")


@pytest.fixture
def reads(monkeypatch):
    monkeypatch.setattr(intent_names, "neighbours_of", lambda network, device, far=False:
                        LINKS.get(device, {"ports": {}, "said": []}))
    monkeypatch.setattr(intent_names, "_devices", lambda network: dict(ALL))


@pytest.mark.parametrize("sentence,rewritten", [
    ("describe both ends of the trunk to s2 as s1-s2 trunk",
     "describe s1 GigabitEthernet0/3 and s2 GigabitEthernet0/3 as s1-s2 trunk"),
    ("describe both ends of Gi0/3 as s1-s2 trunk",
     "describe s1 GigabitEthernet0/3 and s2 GigabitEthernet0/3 as s1-s2 trunk"),
    ("shut each side of the trunk", "shut s1 GigabitEthernet0/3 and s2 GigabitEthernet0/3"),
], ids=["named-far-end", "by-its-port", "far-end-from-the-reads"])
def test_both_ends_with_a_managed_far_end_is_one_draft_of_both(reads, sentence, rewritten):
    got = intent_names.ends("Lab", "s1", S1, sentence)
    assert got["kind"] == "pair" and got["far"] == "s2", got
    assert (got["port"], got["far_port"]) == ("GigabitEthernet0/3", "GigabitEthernet0/3")
    assert got["sentence"] == rewritten


def test_a_far_end_one_side_sees_is_found_from_the_other(reads, monkeypatch):
    """s1's reads name s2 on Gi0/3 with no port; s2's own reads name s1 and both ports."""
    blind = {"ports": {"GigabitEthernet0/3": [{"name": "s2", "role": "switch", "by": "intent",
                                               "port": ""}]}, "said": []}
    monkeypatch.setitem(LINKS, "s1", blind)
    got = intent_names.ends("Lab", "s1", S1, "describe both ends of the trunk to s2 as x")
    assert got["kind"] == "pair" and got["far_port"] == "GigabitEthernet0/3"


@pytest.mark.parametrize("sentence,words,choices", [
    ("describe both ends of the link to h1 as desk 4",
     "h1 is not a device Mercury manages, so only s1's end, GigabitEthernet1/0, can be drafted",
     ["this-end"]),
    ("describe both ends of the s1-r2 link as core", "nothing on s1 links to r2", []),
    ("describe both ends of Gi0/1 as spare",
     "Mercury does not know what GigabitEthernet0/1 links to",
     ["this-end", "far:r1", "far:r2", "far:r3", "far:r4", "far:s2"]),
], ids=["unmanaged-far-end", "no-link", "unknown-far-end-a-device-picker"])
def test_both_ends_without_a_managed_far_end_asks_with_controls(reads, sentence, words, choices):
    got = intent_names.ends("Lab", "s1", S1, sentence)
    assert got["kind"] == "two_ended" and words in got["question"], got
    assert [c["value"] for c in got["choices"]] == choices


@pytest.mark.parametrize("sentence", [
    "describe the uplink as P2P to r1 and shut it",
    "shut both host ports",
    "describe Gi0/1 as both ends of r2's link",
], ids=["no-quantifier", "a-plural-not-ends", "inside-the-value"])
def test_no_both_ends_quantifier_no_two_ended_reading(reads, sentence):
    assert intent_names.ends("Lab", "s1", S1, sentence) is None


@pytest.mark.parametrize("sentence,value,decided", [
    ("describe both ends of the link to h1 as desk 4", "this-end",
     "describe GigabitEthernet1/0 as desk 4"),
    ("describe both ends of Gi0/1 as spare", "far:r2",
     "describe both ends of Gi0/1 to r2 as spare"),
], ids=["this-end", "the-far-device"])
def test_a_two_ended_answer_continues_the_same_draft(reads, sentence, value, decided):
    got = intent_names.decide("Lab", "s1", S1, sentence, "two_ended", value)
    assert got == {"ok": True, "error": "", "sentence": decided}


# ── the other questions, and their controls (C1907) ──────────────────────────────────

@pytest.mark.parametrize("sentence,said,buttons", [
    ("add VLAN 40 or 41, whichever is free",
     "s1's committed intent holds neither; so either can be added", ["40", "41"]),
    ("add VLAN 20 or 40", "s1's committed intent holds VLAN 20 (named USERS) and not VLAN 40; "
                          "so only VLAN 40 can be added", ["40"]),
    ("remove vlan 30 or 40", "holds VLAN 30 (named IPV6) and not VLAN 40; so only VLAN 30 can "
                             "be removed", ["30"]),
    ("add vlans 10, 20 or 30", "holds all of them (VLAN 10, VLAN 20 (named USERS), VLAN 30 "
                               "(named IPV6)); so none of them can be added", []),
])
def test_vlan_alternatives_are_asked_never_chosen(sentence, said, buttons):
    got = intent_names.alternatives("s1", S1, sentence)
    assert got["kind"] == "alternatives" and said in got["question"], got
    assert "Mercury does not choose for you" in got["question"]
    assert [c["value"] for c in got["choices"]] == buttons, "the possible ones, still a choice"


def test_interface_alternatives_say_each_one_s_state_with_both():
    got = intent_names.alternatives("s1", S1, "shut Gi0/1 or Gi0/2, whichever is unused")
    assert got["question"] == (
        "you offer Gi0/1 or Gi0/2, and Mercury does not choose for you: GigabitEthernet0/1 (no "
        "description, up); GigabitEthernet0/2 (\"P2P to r1 Gi3 - RIPng\", up). Which one?")
    assert [c["value"] for c in got["choices"]] == ["GigabitEthernet0/1", "GigabitEthernet0/2",
                                                    "*"]


@pytest.mark.parametrize("sentence", ["add VLAN 40", "shut Gi0/1 and Gi0/2",
                                      "add 192.0.2.0/24 to OSPF area 0 or 10",
                                      "describe Gi0/1 as Gi0/2 or Gi0/3 backup"])
def test_no_alternatives_no_question(sentence):
    assert intent_names.alternatives("s1", S1, sentence) is None


R2 = {"routing": {"ospf": [{"process": "1", "networks": [
    "network 10.255.1.12 0.0.0.0 area 0", "network 10.255.4.8 0.0.0.3 area 20"]}]}}


@pytest.mark.parametrize("sentence,asked", [
    ("add 192.0.2.64/26 to OSPF", True),
    ("add 2001:db8:10::/64 to OSPF", True),
    ("add 192.0.2.64/26 to OSPF area 0", False),
    ("remove 10.255.4.8/30 from OSPF", False),
    ("move 10.255.4.8/30 into area 0", False),
], ids=["ipv4", "ipv6", "an-area", "a-removal", "a-move"])
def test_an_ospf_network_to_add_with_no_area_is_asked(sentence, asked):
    got = intent_names.no_area("r2", R2, sentence)
    assert bool(got) is asked, got
    if asked:
        assert "r2's committed OSPF holds process 1 (areas 0, 20)" in got["question"]
        assert [c["value"] for c in got["choices"]] == ["0", "20"]
        assert got["field"]["kind"] == "area"


@pytest.mark.parametrize("sentence,asked", [
    ("set a description on GigabitEthernet0/1", "; it has none now"),
    ("change the description on Gi0/2", '; it reads "P2P to r1 Gi3 - RIPng" now'),
    ("give Gi0/1 a description", "; it has none now"),
    ("set a description on GigabitEthernet0/1 to spare", None),
    ("clear the description on GigabitEthernet1/0", None),
])
def test_a_description_with_no_text_is_asked_with_a_text_field(sentence, asked):
    got = intent_names.no_value("s1", S1, sentence)
    assert (got is None) if asked is None else (asked in got["question"]), got
    if asked:
        assert got["field"]["kind"] == "text" and got["choices"] == []


@pytest.mark.parametrize("doc,sentence,kind,value,decided", [
    (S1, "add VLAN 40 or 41, whichever is free", "alternatives", "41", "add VLAN 41"),
    (S1, "shut Gi0/1 or Gi0/2, whichever is unused", "alternatives", "*",
     "shut GigabitEthernet0/1 and GigabitEthernet0/2"),
    (S1, "shut Gi0/1 or Gi0/2", "alternatives", "GigabitEthernet0/2", "shut GigabitEthernet0/2"),
    (R2, "add 192.0.2.64/26 to OSPF", "no_area", "20", "add 192.0.2.64/26 to OSPF area 20"),
    (R2, "add 192.0.2.64/26 to OSPF.", "no_area", "0.0.0.10",
     "add 192.0.2.64/26 to OSPF area 0.0.0.10"),
    (R2, "add 2001:db8:10::/64 to OSPF", "no_area", "0", "add 2001:db8:10::/64 to OSPF area 0"),
    (S1, "set a description on Gi0/1", "no_value", "spare, see 'rack 4'",
     "set the description of GigabitEthernet0/1 to \"spare, see 'rack 4'\""),
    (S1, "set a description on Gi0/1", "no_value", 'the "lab" port',
     "set the description of GigabitEthernet0/1 to “the \"lab\" port”"),
], ids=["vlan", "both-interfaces", "one-interface", "an-offered-area", "a-typed-dotted-area",
        "an-ipv6-network", "text-quoted", "text-with-a-double-quote"])
def test_an_answer_makes_the_sentence_as_decided(doc, sentence, kind, value, decided):
    got = intent_names.decide("Lab", "s1", doc, sentence, kind, value)
    assert got == {"ok": True, "error": "", "sentence": decided}


@pytest.mark.parametrize("doc,sentence,kind,value,words", [
    (S1, "add VLAN 20 or 40", "alternatives", "20", "'20' is not an answer Mercury offered"),
    (R2, "add 192.0.2.64/26 to OSPF", "no_area", "ten", "'ten' is no OSPF area"),
    (R2, "add 192.0.2.64/26 to OSPF", "no_area", "4294967296", "past the largest OSPF area"),
    (S1, "set a description on Gi0/1", "no_value", "", "the description is empty"),
    (S1, "set a description on Gi0/1", "no_value", "x" * 241, "at most 240 characters"),
    (S1, "set a description on Gi0/1", "no_value", "café", "holds other characters"),
    (S1, "set a description on Gi0/1", "alternatives", "40", "no longer asks 'alternatives'"),
], ids=["not-offered", "no-area", "too-large", "empty", "too-long", "not-ascii",
        "another-question"])
def test_an_answer_not_offered_or_not_valid_is_refused_naming_it(doc, sentence, kind, value,
                                                                 words):
    got = intent_names.decide("Lab", "s1", doc, sentence, kind, value)
    assert not got["ok"] and words in got["error"], got


def test_a_text_holding_both_kinds_of_double_quote_cannot_be_quoted_back():
    """`requote` puts a person's quoted text back in quotes for the sentence as decided; one
    holding a straight and a curly double quote has no quote to go in, and says so."""
    assert intent_names.quoted_value('a " b') == ("“a \" b”", "")
    assert intent_names.quoted_value("a b") == ('"a b"', "")
    quoted, why = intent_names.quoted_value('a " and “ b')
    assert quoted == "" and "cannot be quoted as one value" in why


# ── the judge, and the case files ─────────────────────────────────────────────────────

@pytest.mark.parametrize("error,expect,passes", [
    ("two_ended", ["ask", "refuse", "refused_after"], True),
    ("alternatives", ["ask"], True),
    ("alternatives", ["answer"], False),
    ("not_an_operation", ["refuse"], True),
    ("not_an_operation", ["ask"], False),
    ("nothing_named", ["refuse"], False),
], ids=["question-as-ask", "alternatives-as-ask", "not-an-answer", "refusal-as-refuse",
        "a-refusal-is-no-question", "other-mercury-answers-unmapped"])
def test_mercury_s_question_and_refusal_are_judged_as_ask_and_refuse(error, expect, passes):
    got = {"ok": False, "error": error, "by": "mercury", "detail": "planted"}
    assert cases.intent_outcome(got) == "mercury"
    assert (cases.intent_misses({"outcome": expect}, got) == []) is passes


def test_a_mercury_reading_with_its_words_or_a_question_reading_passes():
    """Held-out set 2's case 30 allows Mercury's own answer (with its words) or a question."""
    expect = {"outcome": ["mercury", "ask", "refuse"], "said": {"mercury": "names no interface"}}
    assert cases.intent_misses(expect, {"error": "two_ended", "detail": "r1's tab ..."}) == []
    assert cases.intent_misses({"outcome": ["mercury"], "said": {"mercury": "names no"}},
                               {"error": "two_ended", "detail": "r1's tab ..."})


def _signal(case, docs):
    held = intent_words.hold_quotes(case["sentence"])
    if not held["ok"]:
        return held["error"]
    text = " ".join(held["sentence"].split())
    if intent_words.not_an_operation(text):
        return "not_an_operation"
    q = intent_names.questions("Lab", case["device"], docs.get(case["device"], {}), text,
                               devices=dict(ALL, s3="", s4=""))
    # A two-device draft (C1908) is no answer of Mercury's: the call is made.
    return q["kind"] if q and q["kind"] != "pair" else ""


@pytest.mark.parametrize("name,fires", [
    ("recorded.json", [14, 15, 16, 18, 26, 27, 35, 36, 37, 38, 39, 40, 41, 48, 49]),
    ("held_out.json", [8, 9]), ("names.json", [])])
def test_each_signal_fires_only_where_its_case_allows_mercury_s_answer(reads, name,
                                                                       fires):
    """Measured over the files: the cases Mercury now answers before any call, each passing
    its own expectation, and none of the rest (every case expecting an answer among them).
    The floor: each file's cases read, the injection and target-state cases among them."""
    data = cases.load(os.path.join(DIR, name))
    docs = {"s1": S1, "r2": R2}
    got = []
    for c in data["cases"]:
        kind = _signal(c, docs)
        if kind:
            got.append(c["n"])
            assert cases.intent_misses(c["expect"], {"ok": False, "error": kind,
                                                     "detail": "planted"} if kind not in (
                "unbalanced_quote", "placeholder_in_words") else {
                "ok": False, "error": kind, "detail": intent_words.hold_quotes(
                    c["sentence"])["detail"]}) == [], c["n"]
    assert got == fires
    assert len(data["cases"]) >= 10


# ── C1905: scope comes only from resolved references, never from a value ─────────────

@pytest.mark.parametrize("sentence,interfaces", [
    ("set the description on Gi1/0 to uplink to Gi0/1", ["GigabitEthernet1/0"]),
    ("set the description on Gi1/0 to <<text_1>>", ["GigabitEthernet1/0"]),
    ("describe Gi0/1 as uplink, see Gi1/1 for the spare", ["GigabitEthernet0/1"]),
    ("set Gi0/2's description to uplink to Gi1/0, and shut Gi0/3",
     ["GigabitEthernet0/2", "GigabitEthernet0/3"]),
    ("describe Gi2 as to s4, shut Gi3", ["GigabitEthernet2", "GigabitEthernet3"]),
    ("describe GigabitEthernet0/1 as spare port, desk 4", ["GigabitEthernet0/1"]),
], ids=["description-of-x-to", "a-quoted-value", "describe-as", "and-a-new-clause",
        "a-comma-and-a-verb", "a-comma-in-the-value"])
def test_an_interface_inside_a_value_is_never_in_scope(sentence, interfaces):
    assert intent_words.touched(sentence)["interfaces"] == interfaces


def test_an_answer_touching_an_interface_named_only_in_the_value_is_refused():
    """Recorded case 50's sentence: the scope is Gi1/0; a shutdown of Gi0/1 is refused."""
    scope = {"s1": intent_words.touched("set the description on GigabitEthernet1/0 to uplink "
                                        "to Gi0/1")}
    made = intent_words.to_patches(_answer(
        {"op": "set_description", "interface": "GigabitEthernet1/0",
         "description": "uplink to Gi0/1"},
        {"op": "shutdown", "interface": "GigabitEthernet0/1"}), scope)
    assert not made["ok"] and "changes the interface 'GigabitEthernet0/1', which the request " \
        "does not name" in made["error"], made


# ── C1906: an apostrophe never opens a quote for the resolver ───────────────────────────

def test_names_between_two_apostrophes_are_resolved():
    got = _resolve("shut Gi0/1's twin, Gi1/0, and clear Gi1/1's description")
    assert got["ok"] and got["sentence"] == ("shut GigabitEthernet0/1's twin, GigabitEthernet1/0, "
                                             "and clear GigabitEthernet1/1's description"), got
    assert intent_words.quote_spans("shut Gi0/1's twin, Gi1/0, and clear Gi1/1's")[0] == []


def test_a_real_single_quote_is_still_skipped_by_the_resolver():
    got = _resolve("describe Gi0/1 as 'see Gi1/0'")
    assert got["ok"] and got["sentence"] == "describe GigabitEthernet0/1 as 'see Gi1/0'"


# ── C1908: the two ends must match, checked before any preview is offered ───────────────

def _doc(**ifaces):
    return {"interfaces": [dict({"name": n}, **v) for n, v in ifaces.items()]}


TRUNK = {"switchport_mode": "trunk", "switchport_trunk_vlans": ["10,20,30"]}


@pytest.mark.parametrize("a,b,words", [
    (_doc(Gi1=TRUNK), _doc(Gi1=dict(TRUNK, switchport_trunk_vlans=["10,20"])),
     "s1 Gi1 allows VLANs 10, 20, 30 and s2 Gi1 allows VLANs 10, 20"),
    (_doc(Gi1=dict(TRUNK, switchport=["switchport trunk native vlan 99"])), _doc(Gi1=TRUNK),
     "s1 Gi1 has native VLAN 99 and s2 Gi1 native VLAN 1"),
    (_doc(Gi1=TRUNK), _doc(Gi1={"switchport_mode": "access"}),
     "s1 Gi1 is trunk and s2 Gi1 is access"),
    (_doc(Gi1={"ipv4": "192.0.2.0 255.255.255.254"}) | {"routing": {"ospf": [
        {"process": "1", "networks": ["network 192.0.2.0 0.0.0.1 area 0"]}]}},
     _doc(Gi1={"ipv4": "192.0.2.1 255.255.255.254"}) | {"routing": {"ospf": [
         {"process": "1", "networks": ["network 192.0.2.0 0.0.0.1 area 10"]}]}},
     "s1 Gi1 is in OSPF area 0 and s2 Gi1 in 10"),
    (_doc(Gi1={"ipv4": "192.0.2.0 255.255.255.254", "ospf": ["authentication message-digest"]})
     | {"routing": {"ospf": [{"process": "1", "networks": ["network 192.0.2.0 0.0.0.1 area 0"]}]}},
     _doc(Gi1={"ipv4": "192.0.2.1 255.255.255.254"}) | {"routing": {"ospf": [
         {"process": "1", "networks": ["network 192.0.2.0 0.0.0.1 area 0"]}]}},
     "s1 Gi1 authenticates OSPF as message-digest and s2 Gi1 as none"),
    (_doc(Gi1={"ospfv3": ["1 area 0"]}), _doc(Gi1={"ospfv3": ["1 area 5"]}),
     "s1 Gi1 is in OSPFv3 area 0 and s2 Gi1 in 5"),
], ids=["allowed-vlans", "native-vlan", "trunk-and-access", "ospf-area", "ospf-auth",
        "ospfv3-area"])
def test_ends_that_do_not_match_are_named(a, b, words):
    got = intent_words.ends_match("s1", a, "Gi1", "s2", b, "Gi1")
    assert any(words in m for m in got["mismatches"]), got


def _tunnel(src, dst, addr):
    return {"name": "Tunnel0", "ipv4": addr, "unmodeled": [f"tunnel source {src}",
                                                           f"tunnel destination {dst}"]}


def test_a_tunnel_s_ends_mirror_each_other_and_share_a_network():
    a = {"interfaces": [_tunnel("Loopback0", "198.51.100.2", "203.0.113.1 255.255.255.252"),
                        {"name": "Loopback0", "ipv4": "198.51.100.1 255.255.255.255"}]}
    b = {"interfaces": [_tunnel("198.51.100.2", "198.51.100.1", "203.0.113.2 255.255.255.252")]}
    assert intent_words.ends_match("r1", a, "Tunnel0", "r2", b, "Tunnel0") == {
        "mismatches": [], "facts": ["both in 203.0.113.0/30"]}
    wrong = {"interfaces": [_tunnel("198.51.100.2", "198.51.100.9",
                                    "203.0.113.6 255.255.255.252")]}
    got = intent_words.ends_match("r1", a, "Tunnel0", "r2", wrong, "Tunnel0")["mismatches"]
    assert any("r2 Tunnel0's tunnel destination is 198.51.100.9, and r1 Tunnel0's source is "
               "198.51.100.1" in m for m in got), got
    assert any("both ends of a tunnel share one network" in m for m in got), got


def test_the_lab_s_two_links_match():
    """Recorded cases 33 and 34's links, as committed (masked read of 2026-10-27)."""
    r3 = _doc(GigabitEthernet4={"ipv4": "10.255.2.14 255.255.255.254", "ospfv3": ["1 area 0"]}) \
        | {"routing": {"ospf": [{"process": "1", "networks": [
            "network 10.255.2.14 0.0.0.1 area 0"]}]}}
    r4 = _doc(GigabitEthernet4={"ipv4": "10.255.2.15 255.255.255.254", "ospfv3": ["1 area 0"]}) \
        | {"routing": {"ospf": [{"process": "1", "networks": [
            "network 10.255.2.14 0.0.0.1 area 0"]}]}}
    assert intent_words.ends_match("r3", r3, "GigabitEthernet4", "r4", r4, "GigabitEthernet4") \
        == {"mismatches": [], "facts": ["both in 10.255.2.14/31",
                                        "OSPF area 0, authentication none", "OSPFv3 area 0"]}
    s = {"interfaces": [dict(TRUNK, name="GigabitEthernet0/3")]}
    assert intent_words.ends_match("s1", S1, "GigabitEthernet0/3", "s2", s,
                                   "GigabitEthernet0/3")["mismatches"] == []


# ── C1933: a draft is refused only for a mismatch it creates or changes ─────────────────
#
# The lab's two links as committed (s1's real intent and s2 as s1 renamed, its trunk Gi0/3;
# r3 and r4's Gi4 /31 as the masked read of 2026-10-27 gives them), each with a planted
# mismatch, judged before (committed) and after (what a draft would leave).

def _routed(addr, area="0", **iface):
    return _doc(GigabitEthernet4=dict({"ipv4": f"{addr} 255.255.255.254",
                                        "ospfv3": ["1 area 0"]}, **iface)) | {"routing": {
        "ospf": [{"process": "1", "networks": [f"network 10.255.2.14 0.0.0.1 area {area}"]}]}}


def _end(doc, port, **changes):
    import copy
    out = copy.deepcopy(doc)
    for i in out["interfaces"]:
        if i["name"] == port:
            i.update(changes)
    return out


S2 = dict(_end(S1, "GigabitEthernet0/3"), hostname="s2")
S_LINK = ("s1", "GigabitEthernet0/3", "s2", "GigabitEthernet0/3")
R_LINK = ("r3", "GigabitEthernet4", "r4", "GigabitEthernet4")
R3, R4 = _routed("10.255.2.14"), _routed("10.255.2.15")


def _s2(**changes):
    return _end(S2, "GigabitEthernet0/3", **changes)


def _s1(**changes):
    return _end(S1, "GigabitEthernet0/3", **changes)


def _judged(link, before, after):
    a, port_a, b, port_b = link
    return intent_words.ends_judged(a, port_a, b, port_b, before, after)


@pytest.mark.parametrize("link,before,after,words", [
    (S_LINK, (S1, S2), (S1, _s2(switchport_trunk_vlans=["10,20"])),
     "s1 GigabitEthernet0/3 allows VLANs 10, 20, 30 and s2 GigabitEthernet0/3 allows VLANs 10, "
     "20; both ends of a trunk carry the same VLANs"),
    (R_LINK, (R3, R4), (R3, _routed("10.255.2.15", area="10")),
     "r3 GigabitEthernet4 is in OSPF area 0 and r4 GigabitEthernet4 in 10; both ends of a link "
     "share one area"),
], ids=["s1-s2-vlans", "r3-r4-area"])
def test_a_mismatch_the_draft_creates_is_refused_naming_both_ends(link, before, after, words):
    """The ends matched in committed intent and would not after the draft: refused."""
    got = _judged(link, before, after)
    assert got["refused"] == [words] and got["existing"] == [], got


@pytest.mark.parametrize("link,before,after,words", [
    (S_LINK, (S1, _s2(switchport_trunk_vlans=["10,20"])),
     (S1, _s2(switchport_trunk_vlans=["10"])),
     "s1 GigabitEthernet0/3 allows VLANs 10, 20, 30 and s2 GigabitEthernet0/3 allows VLANs 10; "),
    (R_LINK, (R3, _routed("10.255.2.15", area="10")), (R3, _routed("10.255.2.15", area="20")),
     "r3 GigabitEthernet4 is in OSPF area 0 and r4 GigabitEthernet4 in 20; "),
], ids=["s1-s2-vlans", "r3-r4-area"])
def test_a_mismatch_whose_values_the_draft_changes_is_refused(link, before, after, words):
    """Already mismatched in committed intent, and the draft changes its values: refused,
    naming the values it would leave."""
    got = _judged(link, before, after)
    assert len(got["refused"]) == 1 and got["refused"][0].startswith(words), got
    assert got["existing"] == [], got


@pytest.mark.parametrize("link,before,after,words", [
    (S_LINK, (S1, _s2(switchport_trunk_vlans=["10,20"])),
     (_s1(description="s1-s2 trunk"), _s2(switchport_trunk_vlans=["10,20"],
                                          description="s1-s2 trunk")),
     "s1 GigabitEthernet0/3 allows VLANs 10, 20, 30 and s2 GigabitEthernet0/3 allows VLANs 10, "
     "20, already in committed intent; this change does not touch it"),
    (R_LINK, (R3, _routed("10.255.2.15", area="10")),
     (_routed("10.255.2.14", description="core"),
      _routed("10.255.2.15", area="10", description="core")),
     "r3 GigabitEthernet4 is in OSPF area 0 and r4 GigabitEthernet4 in 10, already in committed "
     "intent; this change does not touch it"),
], ids=["s1-s2-vlans", "r3-r4-area"])
def test_a_mismatch_already_committed_and_left_as_it_is_is_said_and_not_refused(link, before,
                                                                                after, words):
    """A description on both ends of a link whose ends already differ: not refused; the
    mismatch said as untouched."""
    got = _judged(link, before, after)
    assert got["refused"] == [], got
    assert [(e["said"], e["bears"]) for e in got["existing"]] == [(words, False)], got


@pytest.mark.parametrize("link,before,after,words", [
    (S_LINK, (_s1(switchport=["switchport trunk native vlan 99"]), S2),
     (_s1(switchport=["switchport trunk native vlan 99"], switchport_trunk_vlans=["10,20,30,40"]),
      _s2(switchport_trunk_vlans=["10,20,30,40"])),
     "s1 GigabitEthernet0/3 has native VLAN 99 and s2 GigabitEthernet0/3 native VLAN 1, already "
     "in committed intent; this change touches the link's trunk settings and may fail because "
     "of it"),
    (R_LINK, (_routed("10.255.2.14", ospf=["authentication message-digest"]), R4),
     (_routed("10.255.2.14", area="10", ospf=["authentication message-digest"]),
      _routed("10.255.2.15", area="10")),
     "r3 GigabitEthernet4 authenticates OSPF as message-digest and r4 GigabitEthernet4 as none, "
     "already in committed intent; this change touches the link's OSPF settings and may fail "
     "because of it"),
], ids=["s1-s2-native-under-a-vlan-change", "r3-r4-auth-under-an-area-change"])
def test_an_existing_mismatch_bearing_on_the_change_says_it_may_fail(link, before, after, words):
    """The draft changes the same link's trunk (or OSPF) settings, and leaves a mismatch of
    that family as it was: the draft proceeds, and the warning says it may fail because of
    it, naming the fact."""
    got = _judged(link, before, after)
    assert got["refused"] == [], got
    assert [(e["said"], e["bears"]) for e in got["existing"]] == [(words, True)], got


def _v6(addr, v3, **iface):
    return _doc(GigabitEthernet4=dict({"ipv6": [f"{addr}/64"], "ospfv3": [f"1 area {v3}"]},
                                      **iface))


@pytest.mark.parametrize("before,after,refused,existing", [
    ((_v6("2001:DB8:2:C::1", "0"), _v6("2001:DB8:2:C::2", "5")),
     (_v6("2001:DB8:2:C::1", "0"), _v6("2001:DB8:2:C::2", "5", description="core")),
     [], ["r3 GigabitEthernet4 is in OSPFv3 area 0 and r4 GigabitEthernet4 in 5, already in "
          "committed intent; this change does not touch it"]),
    ((_v6("2001:DB8:2:C::1", "0"), _v6("2001:DB8:2:C::2", "5")),
     (_v6("2001:DB8:2:C::1", "0"), _v6("2001:DB8:2:C::2", "6")),
     ["r3 GigabitEthernet4 is in OSPFv3 area 0 and r4 GigabitEthernet4 in 6; both ends of a "
      "link share one area"], []),
    ((_v6("2001:DB8:2:C::1", "0"), _v6("2001:DB8:2:C::2", "0")),
     (_v6("2001:DB8:2:C::1", "0"), _v6("2001:DB8:2:C::2", "5")),
     ["r3 GigabitEthernet4 is in OSPFv3 area 0 and r4 GigabitEthernet4 in 5; both ends of a "
      "link share one area"], []),
], ids=["existing-left", "existing-changed", "created"])
def test_an_ipv6_link_s_ospfv3_area_is_judged_by_what_the_draft_does(before, after, refused,
                                                                      existing):
    """An IPv6-only /64 between r3 and r4, its OSPFv3 area the fact: an existing mismatch
    left as it is said, one the draft changes or creates refused, as on IPv4."""
    got = _judged(R_LINK, before, after)
    assert got["refused"] == refused and [e["said"] for e in got["existing"]] == existing, got
