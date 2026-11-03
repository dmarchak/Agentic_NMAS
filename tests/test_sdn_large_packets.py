"""A flood is a high packet rate of small packets (C2313, the operator's decision of 2026-11-03,
option (a); `detect.flood`, `detect._large_packets`).

On the operator's five recorded captures (tests/fixtures/sdn/recorded/: the collector's head
and passes 1 to 16 of each, the one edit the operator's address replaced by a documentation
one), replayed through the rules as `detect.observe` runs them (tests/sdn_series.py):

- **Floods:** RC-ICMP (h1 to h3, 42-byte packets), RC-UDPF (hping3, 42-byte packets) and RC-UDP
  (three senders to h2, 1,512-byte datagrams: several sources at one host are one attack, judged
  on the host's total).
- **Watched, no response proposed:** RC-TCP (a transfer, C2278) and RC-UDP1 (one iperf UDP
  sender, 1,512-byte datagrams: one large-packet stream, `large_packets`).

Measured before the change (2026-11-03): RC-UDP1 was a flood on s1 port 1 and s2 port 3 at pass
13, and a rate limit was proposed against its sender.
"""
import copy

import pytest

from modules.sdn import detect as D
from tests import sdn_series as S
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_incidents import NET, NO_DRIVER, calls, collected  # noqa: F401

DIR = "tests/fixtures/sdn/recorded"


def replayed(label: str, **values) -> list:
    series = S.load(f"{DIR}/{label}.jsonl")
    if values:
        v = dict(series["head"]["thresholds"]["values"], **values)
        return S.replay(series, values=v)
    return S.replay(series)


def _all(passes, rule=None, basis=None) -> list:
    return [d for r in passes for d in r["detections"]
            if (rule is None or d["rule"] == rule) and (basis is None or d.get("basis") == basis)]


@pytest.mark.parametrize("label", ["RC-ICMP", "RC-UDPF", "RC-UDP"])
def test_each_flood_capture_stays_a_flood(label):
    passes = replayed(label)
    assert _all(passes, "flood"), label
    assert not _all(passes, basis="large_packets"), label


@pytest.mark.parametrize("label,basis", [("RC-TCP", "transfer"), ("RC-UDP1", "large_packets")])
def test_each_benign_capture_is_watched_with_no_flood(label, basis):
    passes = replayed(label)
    assert not _all(passes, "flood"), label
    watched = _all(passes, "high_rate", basis)
    assert watched and all(d["rule"] in D.WATCH_ONLY for d in watched), label


def test_rc_udp1_s_one_sender_says_why_it_is_not_a_flood():
    (first,) = [r for r in replayed("RC-UDP1") if _all([r], "high_rate", "large_packets")][:1]
    assert first["n"] == 13
    got = {(d["dpid"], d["port"]): d for d in _all([first], "high_rate", "large_packets")}
    assert sorted(got) == [(1, 1), (2, 3)]
    d = got[(1, 1)]
    assert d["source"] == "192.0.2.1" and d["confidence"] == "lower"
    assert "not called a flood: its packets average 1,512 B, over the flood's 200 B" in d["words"]
    assert d["words"].endswith("a large-packet flood is left to a person")


def test_rc_udp_s_three_senders_to_one_host_are_one_attack_on_its_total():
    (first,) = [r for r in replayed("RC-UDP") if _all([r], "flood")][:1]
    floods = {(d["dpid"], d["port"]): d for d in _all([first], "flood")}
    assert sorted(floods) == [(1, 1), (1, 3), (2, 1), (2, 2)]
    for d in floods.values():
        assert d["attack_host"] == "192.0.2.2"
        assert d["attack_sources"] == ["192.0.2.1", "192.0.2.3", "192.0.2.4"]
        assert "3 sources (192.0.2.1, 192.0.2.3, 192.0.2.4) send to 192.0.2.2" in d["words"]
        assert "judged as one attack on that host" in d["words"]
    # The host's total counts each source once, at the port it enters by: about 64 Mb/s.
    words = floods[(1, 1)]["words"]
    mbits = float(words.split("about ")[1].split(" Mb/s")[0])
    assert 60 <= mbits <= 70, words


def test_rc_udp1_s_watching_row_says_it_is_left_to_a_person(calls):  # noqa: F811
    """On SDN › Responses' data and its row: the watching row of RC-UDP1's stream carries the
    large-packet reason in place of the rate-only one, no AI call is made, and the row draws
    it with "A large-packet flood is left to you"."""
    import app as A
    from modules import sdn_ops_page as P
    from modules.sdn import loop as LP
    r = next(r for r in replayed("RC-UDP1") if _all([r], "high_rate", "large_packets"))
    d = next(x for x in _all([r], "high_rate", "large_packets") if x["port"] == 1)
    LP.run_pass(NET, collect=collected, observe=lambda n, c: {
        "ok": True, "fired": [d["key"]], "resolved": [], "detections": [d],
        "thresholds": {"sdn_flood_window_seconds": 30}, "collected_at": r["at"]},
        now=lambda: D._epoch(r["at"]), driver=NO_DRIVER)
    view = P.responses_view(NET)
    (w,) = view["watching"]
    assert w["large_words"] == d["confidence_why"] and w["transfer_words"] == "" and calls == []
    assert "over the flood's 200 B" in w["large_words"]
    # The row's template, parsed: the branch on `w.large_words` draws the words and says it is
    # left to a person.
    from jinja2 import nodes
    env = A.app.jinja_env
    src = env.loader.get_source(env, "v2/_sdn_responses.html")[0]
    found = {}
    for node in env.parse(src).find_all(nodes.If):
        # An elif is walked both as its If's branch and as an If node itself: keyed by test.
        for test, body in [(node.test, node.body)] + [(e.test, e.body) for e in node.elif_]:
            if isinstance(test, nodes.Getattr) and test.attr == "large_words":
                text = "".join(t.data for b in body for t in b.find_all(nodes.TemplateData))
                drawn = [g.attr for b in body for g in b.find_all(nodes.Getattr)]
                found[id(test)] = (text, drawn)
    assert len(found) == 1, found
    ((text, drawn),) = found.values()
    assert "A large-packet flood is left to you" in text and "large_words" in drawn


def test_the_line_is_the_network_s_setting():
    """`sdn_flood_max_mean_bytes` moves it: at 2,000 B RC-UDP1's 1,512-byte stream is small
    enough to be a flood again, so the rule reads the network's value, not a constant."""
    assert _all(replayed("RC-UDP1", sdn_flood_max_mean_bytes=2000), "flood")
    assert D.THRESHOLDS["sdn_flood_max_mean_bytes"] == 200


def test_a_port_whose_bytes_were_not_read_is_judged_on_its_rate():
    series = S.load(f"{DIR}/RC-UDP1.jsonl")
    for p in series["passes"]:
        p["collected"] = copy.deepcopy(p["collected"])
        for ctl in p["collected"].get("controllers") or []:
            for sw in ctl.get("switches") or []:
                for port in sw.get("ports") or []:
                    port.pop("rx_bytes_per_s", None)
    passes = S.replay(series)
    assert _all(passes, "flood") and not _all(passes, basis="large_packets")


def test_one_source_to_a_host_by_its_ipv6_address_is_one_source():
    """The host is read in its canonical spelling (IPv4 or IPv6): one sender's two ports to one
    host, named by a documentation IPv6 address, are still one source, watched."""
    c = {"ctl": {"connection": "lab-ryu"}, "rate": 1785.0, "mean": 1512.0, "words": "w",
         "sw": {"dpid": 1, "dpid_hex": "0000000000000001"}}
    kw = {"subject": ("port", 1), "scope": "p1", "port": 1, "source": "2001:db8::1",
          "targets": ["2001:DB8::3"], "dst_hosts": [], "measurement": {}, "threshold": {},
          "confidence": "high", "confidence_why": "", "evidence": [], "basis": "rate"}
    a = dict(c, kw=dict(kw))
    b = dict(c, kw=dict(kw, port=3, scope="p3", subject=("port", 3), targets=["2001:db8::3"]))
    out = D._large_packets({"network": "SDN lab", "collected_at": ""}, [a, b], 200)
    assert [d["rule"] for d in out] == ["high_rate", "high_rate"]
    two = dict(c, kw=dict(kw, source="2001:db8::4", port=4, scope="p4", subject=("port", 4)))
    out = D._large_packets({"network": "SDN lab", "collected_at": ""}, [a, two], 200)
    assert [d["rule"] for d in out] == ["flood", "flood"]
    assert out[0]["attack_host"] == "2001:db8::3"
