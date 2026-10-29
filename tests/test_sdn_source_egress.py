"""What leaves the host for a port's source found in the topology (C2002's egress, the
irreversible tier's hand check of 2026-10-28, docs/TIER_HAND_CHECK.md): for a flood or a
fallback scan whose flows name no address, the classifier's request carries the detection's
``source_from`` (and its ``source`` when the port resolves to one host) and its ``names`` the
port's hosts' addresses, inside the topology-class gate, exactly that and no more.

**The data is the Lab 8 walk's own** (tests/test_sdn_source_from_topology.py's: the MAC-only
flood on s1 port 2 judged again with Ryu 4.34's captured topology, h2 the one host there; a
second host, IPv6-only, planted beside it for the several case). The pack is built and kept as
`detect.observe` keeps it (`evidence_pack.build_detection`, masked and hashed); the classifier
runs through the real gateway with a fake provider (tests/test_sdn_classify.py's `world`), so
the request asserted is the one that would be sent, after the gateway's egress mask. Every
expected value is read off the fixtures by hand.

- **The request, the topology class allowed**: the detection block is the section's detection
  piece as sent, its keys exactly the piece's own plus ``source_from`` (nothing else of the
  topology), ``source_from`` exactly how, state, port, the port's hosts (each its MAC and one
  address) and the read's time and words; the names block exactly the switch and the port's
  hosts' addresses (no MAC); IPv4, and an IPv6 host beside it.
- **The topology class off sends nothing** for such a detection (the classifier), and Explain
  withholds the whole sdn section, ``source_from`` with it.
- **Masking still covers it**: a credential shape a controller put in a host's entry is masked
  in the pack as kept and in the request as sent; the MAC and the address are not secrets and
  are sent as they are (the topology class, PHASE8_PLAN 15.15).
"""
import json
import re

import pytest

from modules import evidence_pack as EP
from modules.ai import explain, triggers
from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from tests.ai_person import PERSON, pressed_by
from tests.test_sdn_classify import world  # noqa: F401 - the fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_source_from_topology import H2, H2_MAC, plus, stored, walk_flood

NET = "Default"
DPID = "0000000000000001"
H5_V6 = {"mac": "00:00:00:00:00:05", "ipv4": [], "ipv6": ["2001:db8:8::5"]}
#: The detection piece's own keys (`detect.section`), as sent (`closed_loop.as_sent`: its
#: evidence id and the count of evidence not sent added), and C2002's one more.
PIECE_KEYS = {"kind", "rule", "title", "words", "connection", "dpid", "source", "targets", "port",
              "measurement", "threshold", "confidence", "confidence_why", "evidence", "id",
              "evidence_not_sent", "source_from"}


def kept(d, collected, sw):
    """*d*'s evidence pack built and kept as `detect.observe` keeps it."""
    at = D._epoch(d["at"])
    pack = EP.build_detection(D.instance(d, at, at), network=NET,
                              sdn=D.section(d, collected, sw), now=at,
                              trigger=f"planted: {d['words']}",
                              switch_words=f"switch {d['dpid_hex']} on {d['connection']}")
    assert EP.record(pack)["ok"]
    return pack


def flood(topo):
    d, collected, sw = walk_flood("walk-flood-1-s1", topo)
    d = dict(d, network=NET)
    return d, kept(d, collected, sw)


def classify(w, d, pack):
    with pressed_by(PERSON):
        return CL.classify_pack(NET, d, pack, actor=PERSON, trigger=triggers.person(PERSON),
                                send=w.send)


def blocks(body) -> dict:
    """The request's data blocks by name, each parsed."""
    text = body["messages"][0]["content"]
    return {m.group(1): json.loads(m.group(2)) for m in
            re.finditer(r'<data name="([a-z]+)">\n(.*?)\n</data>', text, re.S)}


@pytest.mark.parametrize("topo,source,hosts,names", [
    (lambda: stored(), H2, [{"mac": H2_MAC, "address": H2}], [DPID, H2]),
    (lambda: stored(edit=plus(H5_V6)), None,
     [{"mac": H2_MAC, "address": H2}, {"mac": "00:00:00:00:00:05", "address": "2001:db8:8::5"}],
     [DPID, H2, "2001:db8:8::5"]),
], ids=["one-host-ipv4", "several-ipv6-beside"])
def test_the_request_carries_how_the_source_was_found_and_the_port_s_hosts_and_no_more(
        world, topo, source, hosts, names):  # noqa: F811
    d, pack = flood(topo())
    world.answer = dict(world.answer, threat_type="flood", affected_devices=[DPID],
                        action_id="none", threat_detected=True,
                        parameters=dict(world.answer["parameters"], source=""),
                        evidence_refs=["port:lab-ryu:0000000000000001:2"])
    got = classify(world, d, pack)
    assert got["ok"], got
    (body,) = world.sent
    sent = blocks(body)
    det = sent["detection"]
    assert set(det) == PIECE_KEYS, "nothing else of the topology rides in the detection"
    assert det["source"] == source
    assert det["source_from"] == {
        "how": "topology", "state": "named" if source else "several", "port": 2,
        "hosts": hosts, "read_at": "2026-10-27T09:35:49Z", "words": d["source_from"]["words"]}
    assert sent["names"] == names, "the switch and the port's hosts' addresses, never a MAC"


def test_the_topology_class_off_sends_nothing_of_a_port_s_source(world, monkeypatch):  # noqa: F811,E501
    d, pack = flood(stored())
    assert d["source_from"]["state"] == "named", "premise"
    monkeypatch.setattr("modules.ai.egress_classes.topology_allowed",
                        lambda net: {"allowed": False, "why": "planted: an admin turned it off"})
    got = classify(world, d, pack)
    assert got["error"] == "withheld" and world.sent == []
    (sec,) = [s for s in explain.sent_sections(pack) if s["name"] == EP.SDN_SECTION]
    assert sec["pieces"] == [] and "source_from" not in json.dumps(sec)
    assert sec["withheld"].startswith("the flows and port rates are not sent")
    monkeypatch.setattr("modules.ai.egress_classes.topology_allowed",
                        lambda net: {"allowed": True, "why": ""})
    (sec,) = [s for s in explain.sent_sections(pack) if s["name"] == EP.SDN_SECTION]
    (piece,) = [p for p in sec["pieces"] if p["kind"] == "detection"]
    assert piece["source_from"]["hosts"] == [{"mac": H2_MAC, "address": H2}], "premise: open"


def test_a_credential_shape_in_a_host_s_entry_is_masked_and_its_mac_and_address_are_not(
        world):  # noqa: F811
    planted = "username planted password 0 planted-pw-0123"

    def edit(hosts):
        h2 = next(h for h in hosts if h["mac"] == H2_MAC)
        h2["mac"] = f"{H2_MAC} {planted}"
        return hosts

    d, pack = flood(stored(edit=edit))
    (sec,) = [s for s in pack["sections"] if s["name"] == EP.SDN_SECTION]
    (piece,) = [p for p in sec["pieces"] if p["kind"] == "detection"]
    assert "planted-pw-0123" not in json.dumps(pack), "masked in the pack as kept"
    assert "<redacted:user_password>" in piece["source_from"]["words"]
    world.answer = dict(world.answer, action_id="none", affected_devices=[DPID],
                        parameters=dict(world.answer["parameters"], source=""),
                        evidence_refs=["port:lab-ryu:0000000000000001:2"])
    got = classify(world, d, pack)
    assert got["ok"], got
    (body,) = world.sent
    text = json.dumps(body)
    assert "planted-pw-0123" not in text, "masked in the request as sent"
    assert H2_MAC in text and H2 in text, "not secrets: sent as they are"
