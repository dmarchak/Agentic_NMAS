"""A transfer is not a flood (C2278, PHASE8_PLAN 17.9; `detect.transfer`), and High packet rate
joins the flood on a real capture (S-HR, 17.8). On the operator's three recorded captures of
2026-11-01 (tests/fixtures/sdn/recorded/: the collector's head and passes 1 to 15 or 16 of each,
the one edit the operator's address replaced by a documentation one), replayed through the rules
as `detect.observe` runs them (tests/sdn_series.py).

- **RC-TCP** (one iperf session, h2 to h4): the flood rule's four candidates are High packet
  rate, basis transfer, never a flood: the data's two ports (s1 port 2, s2 port 3) naming the
  session and its sender, the ACKs' two (s1 port 3, s2 port 2) naming no source.
- **RC-UDP** (three sources to h2) and **RC-ICMP** (h1 to h3): their floods stay floods, none a
  transfer.
- **RC-ICMP through the loop:** High packet rate from pass 11 is watched with no AI call, and
  the flood on the same ports at pass 14 joins each watching row.
"""
import pytest

from modules.sdn import detect as D
from modules.sdn import loop as LP
from tests import sdn_series as S
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_incidents import NET, NO_DRIVER, calls, collected  # noqa: F401

DIR = "tests/fixtures/sdn/recorded"


def replayed(label: str) -> list:
    return S.replay(S.load(f"{DIR}/{label}.jsonl"))


def _of(r: dict, *rules) -> dict:
    return {(d["dpid"], d["port"]): d for d in r["detections"] if d["rule"] in rules}


def test_rc_tcp_s_transfer_is_high_packet_rate_never_a_flood():
    passes = replayed("RC-TCP")
    assert not [d for r in passes for d in r["detections"] if d["rule"] == "flood"]
    (first,) = [r for r in passes if _of(r, "high_rate")][:1]
    assert first["n"] == 13
    got = _of(first, "high_rate")
    assert sorted(got) == [(1, 2), (1, 3), (2, 2), (2, 3)]
    assert all(d["basis"] == "transfer" and d["rule"] in D.WATCH_ONLY for d in got.values())
    for key in ((1, 2), (2, 3)):
        d = got[key]
        assert d["transfer"]["side"] == "data" and d["source"] == "192.0.2.2", key
        assert d["transfer"]["session"] == ("192.0.2.2", "192.0.2.4", "tcp/5002")
        assert d["words"].endswith("one TCP session from 192.0.2.2 to 192.0.2.4 tcp/5002 with "
                                   "its ACKs returning, at a mean of 44,739 B a packet: a "
                                   "transfer's shape, not a flood's") or key == (2, 3)
    for key in ((1, 3), (2, 2)):
        d = got[key]
        assert d["transfer"]["side"] == "acks" and d["source"] is None, key
        assert "the ACKs of a TCP session from 192.0.2.2 to 192.0.2.4 tcp/5002" in d["words"]


@pytest.mark.parametrize("label,first,ports", [
    ("RC-UDP", 13, [(1, 1), (1, 3), (2, 1), (2, 2)]),
    ("RC-ICMP", 14, [(1, 1), (1, 3)]),
])
def test_a_flood_stays_a_flood(label, first, ports):
    passes = replayed(label)
    floods = [r for r in passes if _of(r, "flood")]
    assert floods[0]["n"] == first and sorted(_of(floods[0], "flood")) == ports
    assert not [d for r in passes for d in r["detections"] if d.get("basis") == "transfer"]


def test_rc_icmp_through_the_loop_watched_then_joined_by_its_flood(calls):  # noqa: F811
    """The capture's detections each pass, fired when new, through `loop.run_pass` (its
    classify step counted): High packet rate on s1 ports 1 and 3 from pass 11 and s2's from
    12, watched with no AI call; the flood on s1's ports at pass 14 and s2's at 15 joins each
    watching row on its port, and the flood's response says it began as High packet rate."""
    before, watched = set(), {}
    for r in replayed("RC-ICMP"):
        now = {d["key"]: d for d in r["detections"]}
        fired = [d for k, d in now.items() if k not in before]
        at = D._epoch(r["at"])
        observe = lambda network, c, r=r, fired=fired, now=now: {  # noqa: E731
            "ok": True, "fired": [d["key"] for d in fired], "resolved": [],
            "detections": list(now.values()),
            "thresholds": {"sdn_flood_window_seconds": 30, "sdn_scan_window_seconds": 60},
            "collected_at": r["at"]}
        out = LP.run_pass(NET, collect=collected, observe=observe, now=lambda at=at: at,
                          driver=NO_DRIVER)
        assert out["ok"], out
        for wid in out["watching"]:
            watched[wid] = r["n"]
        before = set(now)
        if r["n"] == 13:
            # h1's (s1 port 1, s2's link port 3 seen also, its flows carrying h1's MAC:
            # C2106), s1's link port 3 alone, h3's (s2 port 1, the victim's replies).
            rows = {(w["detection"]["dpid"], w["detection"]["port"]): len(w["members"])
                    for w in LP.watching(NET)["rows"]}
            assert calls == [] and rows == {(1, 1): 2, (1, 3): 1, (2, 1): 1}
            assert sorted(watched.values()) == [11, 11, 12]
    # Pass 14: s1's floods (h1's port, s1's link port), each its incident, each joining its
    # watching row; pass 15: s2's two floods, each its own incident (C2237: h1 and h3 are each
    # other's destination at one size, so neither is named a source, and nothing groups them
    # by one), h3's port joining h3's row; s2's link port's rate was a member of h1's row,
    # already joined, so its flood begins as nothing.
    assert [d["rule"] for d in calls] == ["flood"] * 4, "the floods' calls, and only theirs"
    assert LP.watching(NET)["rows"] == []
    floods = LP.awaiting(NET)["rows"]
    assert all(r["detection"].get("source") is None for r in floods), "neither host named"
    began = [r for r in floods if r.get("began_as")]
    assert len(began) == 3 and {r["began_as"]["watch"] for r in began} == set(watched)


def test_a_transfer_s_watching_row_says_why_it_is_not_a_flood(calls):  # noqa: F811
    """On SDN › Responses' data: the watching row of RC-TCP's data says the transfer's words in
    place of the rate-only reason."""
    from modules import sdn_ops_page as P
    r = next(r for r in replayed("RC-TCP") if _of(r, "high_rate"))
    d = _of(r, "high_rate")[(1, 2)]
    LP.run_pass(NET, collect=collected, observe=lambda n, c: {
        "ok": True, "fired": [d["key"]], "resolved": [], "detections": [d],
        "thresholds": {"sdn_flood_window_seconds": 30}, "collected_at": r["at"]},
        now=lambda: D._epoch(r["at"]), driver=NO_DRIVER)
    (w,) = P.responses_view(NET)["watching"]
    assert w["transfer_words"] == d["transfer"]["words"] and calls == []


def test_with_no_acks_returning_rc_tcp_s_data_is_judged_as_the_flood_rule_judges_it():
    """The return side is the shape's half: RC-TCP with its ACK flows taken out of the switch
    tables (the minimal edit: the flows whose match names h4's MAC as the sender) is judged as
    a flood is, on the data's ports."""
    import copy
    series = S.load(f"{DIR}/RC-TCP.jsonl")
    acks = "00:00:00:00:00:04"
    for p in series["passes"]:
        p["collected"] = copy.deepcopy(p["collected"])
        for ctl in p["collected"].get("controllers") or []:
            for sw in ctl.get("switches") or []:
                sw["flows"] = [f for f in sw.get("flows") or []
                               if (f.get("match") or {}).get("eth_src") != acks]
    passes = S.replay(series)
    assert not [d for r in passes for d in r["detections"] if d.get("basis") == "transfer"]
    # Judged as the flood rule judges it (C2313, the operator's decision of 2026-11-03): one
    # sender's 44 KB-a-packet stream is a large-packet stream, watched, never a transfer.
    judged = [r for r in passes if _of(r, "flood", "high_rate")]
    got = _of(judged[0], "flood", "high_rate")
    assert {(1, 2), (2, 3)} <= set(got)
    assert {got[k]["basis"] for k in ((1, 2), (2, 3))} == {"large_packets"}
    assert not [d for r in passes for d in r["detections"] if d["rule"] == "flood"
                and (d["dpid"], d["port"]) in ((1, 2), (2, 3))]


def _without_sessions_from(label: str, address: str) -> dict:
    """*label*'s series with every TCP session flow from *address* (`detect._session`'s source)
    taken out of the switch tables (the minimal edit); the ports' counters are left as
    captured."""
    import copy
    series = S.load(f"{DIR}/{label}.jsonl")
    for p in series["passes"]:
        p["collected"] = copy.deepcopy(p["collected"])
        for ctl in p["collected"].get("controllers") or []:
            for sw in ctl.get("switches") or []:
                sw["flows"] = [f for f in sw.get("flows") or []
                               if (D._session(f) or ("",))[0] != address]
    return series


def test_a_small_packet_stream_is_a_transfer_s_acks_only_with_its_data_returning():
    """The return side decides flood or not, under C2313's rule: RC-TCP's ACK ports (s1 port 3,
    s2 port 2) receive small packets (66 B, under the flood's 200 B). With the session's data
    flowing the other way on the same switch, they are a transfer's ACKs, watched; with the
    data's flows taken out (the TCP session flows from h2, 192.0.2.2), nothing shows them to
    be a transfer's, so they are a high rate of small packets: a flood."""
    acks_ports = ((1, 3), (2, 2))
    passes = replayed("RC-TCP")
    with_data = {(d["dpid"], d["port"]): d for r in passes for d in r["detections"]
                 if (d["dpid"], d["port"]) in acks_ports}
    assert set(with_data) == set(acks_ports)
    assert all(d["rule"] == "high_rate" and d["basis"] == "transfer"
               and d["transfer"]["side"] == "acks" for d in with_data.values())
    passes = S.replay(_without_sessions_from("RC-TCP", "192.0.2.2"))
    floods = {(d["dpid"], d["port"]) for r in passes for d in r["detections"]
              if d["rule"] == "flood"}
    assert set(acks_ports) <= floods, floods
    assert not [d for r in passes for d in r["detections"]
                if (d["dpid"], d["port"]) in acks_ports and d.get("basis") == "transfer"]
