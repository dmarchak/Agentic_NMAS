"""C2237 on the operator's recorded captures (tests/fixtures/sdn/recorded/, replayed by
tests/sdn_series.py): a victim's replies are never named a flood's source when the flows are L2
only. Before, a detection on MAC-only flows named no targets, so `detect.mark_replies` could not
see that the victim was the attacker's destination, and RC-ICMP named the victim (192.0.2.3, s2
port 1) a flood source. Its targets are now the addresses the controller's topology lists for
the entering flows' destination MACs (`detect._l2_targets`; link-local left out).

- **RC-ICMP** (h1 to h3, 42 B both ways): s1 port 1 (h1's) and s2 port 1 (h3's) are each
  other's destination at one size, so neither is named a source, and a person decides from the
  evidence (C2237's rule for a pair the sizes cannot tell apart).
- **RC-UDP** (three senders to h2, one-way): each sender keeps its source; h2 sends nothing
  back.
"""
from tests import sdn_series as S

DIR = "tests/fixtures/sdn/recorded"


def floods(label: str, n: int) -> dict:
    (r,) = [r for r in S.replay(S.load(f"{DIR}/{label}.jsonl")) if r["n"] == n]
    return {(d["dpid"], d["port"]): d for d in r["detections"] if d["rule"] == "flood"}


def test_rc_icmp_names_neither_the_attacker_nor_the_victim_a_source():
    got = floods("RC-ICMP", 15)
    assert sorted(got) == [(1, 1), (1, 3), (2, 1), (2, 3)]
    for key, host in (((1, 1), "192.0.2.1"), ((2, 1), "192.0.2.3")):
        d = got[key]
        assert d["source"] is None and d["replying_hosts"] == [host], key
        assert "neither is named a source" in d["replying_to"]["words"], key
    assert got[(1, 1)]["dst_hosts"] == ["192.0.2.3", "2001:db8:8::3"]
    assert got[(2, 1)]["dst_hosts"] == ["192.0.2.1", "2001:db8:8::1"]


def test_the_topology_s_other_hosts_are_never_sent_to_the_classifier():
    """`dst_hosts` stays on the detection: the section the classifier is sent holds none of it
    (the topology egress class sends only the port's own hosts)."""
    import json

    from modules.sdn import detect as D
    from modules.sdn.closed_loop import rejudge
    series = S.load(f"{DIR}/RC-ICMP.jsonl")
    (p,) = [p for p in series["passes"] if p["n"] == 15]
    c = rejudge(p["collected"])
    d = floods("RC-ICMP", 15)[(1, 1)]
    sw = next(s for _ctl, s in D._switches(c) if s["dpid"] == d["dpid"])
    sent = json.dumps(D.section(d, c, sw))
    assert d["dst_hosts"] and "dst_hosts" not in sent and "2001:db8:8::3" not in sent


def test_rc_udp_s_senders_keep_their_sources():
    got = floods("RC-UDP", 15)
    assert {k: d["source"] for k, d in got.items() if d["source"]} == {
        (1, 1): "192.0.2.1", (2, 1): "192.0.2.3", (2, 2): "192.0.2.4"}
    assert not [d for d in got.values() if d.get("replying_to")]
