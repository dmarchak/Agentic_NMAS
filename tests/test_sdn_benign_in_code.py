"""C2305, the deterministic part (Lab 9 B3; `modules/sdn/benign.py`): benign traffic a detection
rule fired on, decided "no threat" in code with no AI call, where the evidence pack's own
counters settle it; and the same figures sent to the classifier where they do not.

The cases are the blind round's own benign packs, exactly as kept
(tests/fixtures/ai_cases/sdn_classify/recorded_from_blind.json: BS3, passive-FTP-like
sessions; BF1, a nightly-backup-like bulk TCP session; BF2, an elephant flow at line rate; BF3,
a software-update fan-out; 10 cases, 0 of 100 runs said no threat), and every threat case of
the four classify sets (recorded, held out, recorded from blind, and the blind set's own).

- each of the 10 benign cases is decided no threat in code, its call never made (the provider
  fails the test if asked), its action none, so a person decides and AUTO never acts;
- no threat case of any set is decided in code: a flood is one-way, a scan's flows carry a
  probe's packet or none;
- a transfer at or over 90% of its link's speed (where the speed was read) is not decided in
  code; under it, it is; the speed not read is said;
- an IPv6 twin of each benign shape (its addresses rewritten, nothing else) is decided alike;
- a flood code did not decide is sent its shape, as one more evidence piece;
- an evaluation's batch decides the same cases in code, with no request for them.
"""
import copy
import json
import os

import pytest

from modules.sdn import benign as B
from modules.sdn import closed_loop as CL
from modules.sdn import loop as LP

CASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
BENIGN = (5, 21, 22, 23, 24, 25, 26, 27, 28, 29)


def _load(name):
    with open(os.path.join(CASES, name), encoding="utf-8") as fh:
        return json.load(fh)["cases"]


BLIND = {c["n"]: c for c in _load("ai_cases/sdn_classify/recorded_from_blind.json")}


def _threats():
    out = []
    for name in ("ai_cases/sdn_classify/recorded.json", "ai_cases/sdn_classify/held_out.json",
                 "ai_cases/sdn_classify/recorded_from_blind.json",
                 "blind_sets/sdn_classify/blind_cases.json"):
        for c in _load(name):
            e = c.get("expect") or {}
            alts = e.get("any_of") or [e]
            if all(a.get("threat_detected") for a in alts):
                out.append(pytest.param(c, id=f"{name.split('/')[-1]}-{c['n']}"))
    return out


def _pack(case):
    from modules import evidence_pack as EP

    return {"id": f"case-{case['n']}", "network": "SDN lab", "store": "sdn",
            "sections": [dict(case["section"], name=EP.SDN_SECTION)]}


def _never(*_a, **_k):
    raise AssertionError("the model was asked")


def test_the_ten_benign_cases_are_the_blind_round_s():
    assert [BLIND[n]["name"].split(":")[0].split(" ")[0] for n in BENIGN] == [
        "BS3", "BF2", "BF2", "BF3", "BF3", "BF3", "BF3", "BF3", "BF1", "BF1"]
    assert all(BLIND[n]["expect"]["threat_detected"] is False for n in BENIGN)


@pytest.mark.parametrize("n", BENIGN)
def test_each_benign_case_is_decided_no_threat_in_code_with_no_call(n):
    c = BLIND[n]
    got = CL.classify_pack("SDN lab", c["detection"], _pack(c), actor="job:test",
                           trigger={"kind": "background"}, send=_never, intact=False)
    assert got["ok"] and got["action"] == CL.NO_ACTION and got["call_id"] == ""
    cls = got["classification"]
    assert cls["by_code"] and cls["threat_detected"] is False and cls["model"] == "code"
    assert cls["reasoning"].startswith("no threat, decided in code with no AI call: ")
    verdict = LP.verdict_of("Default", c["detection"], got)
    assert verdict["person"] and "never AUTO's" in verdict["words"]


def test_the_transfer_s_figures_are_its_counters():
    shape = B.decide(BLIND[28]["section"])["shape"]
    assert (shape["side"], shape["protocols"], shape["sessions"]) == ("data", [6], 1)
    assert shape["rx_mean_bytes"] == pytest.approx(8043695464 / 183740, abs=0.1)
    assert shape["tx_mean_bytes"] == pytest.approx(66.0, abs=0.1)
    assert shape["ack_share"] == pytest.approx(0.777, abs=0.001)
    assert shape["words"].endswith("the link's speed was not read")
    acks = B.decide(BLIND[29]["section"])["shape"]
    assert acks["side"] == "acks" and acks["protocols"] == []


@pytest.mark.parametrize("case", _threats())
def test_no_threat_case_is_decided_in_code(case):
    got = B.decide(case["section"])
    assert not got["decided"], got["words"]


@pytest.mark.parametrize("kbps,decided", [(1_000_000, False), (100_000_000, True)])
def test_a_transfer_at_its_link_s_capacity_is_left_to_the_model(kbps, decided):
    section = copy.deepcopy(BLIND[28]["section"])
    for p in section["pieces"]:
        if p["kind"] == "port":
            p["curr_speed_kbps"] = kbps
    got = B.decide(section)
    assert got["decided"] is decided
    if not decided:
        assert got["words"].startswith("not decided in code (under_capacity not met)")
        assert "of its 1,000 Mbit/s link" in got["words"]


def test_the_link_speed_reaches_the_port_s_piece_where_link_status_was_read():
    from modules.sdn import detect as D

    det = BLIND[28]["detection"]
    port = next(p for p in BLIND[28]["section"]["pieces"] if p["kind"] == "port")
    sw = {"dpid": 1, "dpid_hex": det["dpid_hex"], "flows": [], "sample": port["sample"],
          "ports": [{k: v for k, v in port.items() if k not in ("kind", "ref", "sample")}],
          "port_desc": [{"port_no": 1, "curr_speed": 1_000_000, "link_up": True}]}
    got = D.section(dict(det, effect=None), {"network": "SDN lab"}, sw)
    (piece,) = [p for p in got["pieces"] if p["kind"] == "port"]
    assert piece["curr_speed_kbps"] == 1_000_000
    assert not B.decide(got)["decided"], "12.8 Gbit/s on a 1 Gbit/s link is not decided"
    sw.pop("port_desc")
    (piece,) = [p for p in D.section(dict(det, effect=None), {"network": "SDN lab"},
                                     sw)["pieces"] if p["kind"] == "port"]
    assert "curr_speed_kbps" not in piece


def _ipv6(section):
    out = copy.deepcopy(section)
    for p in out["pieces"]:
        m = p.get("match") or {}
        for side in ("src", "dst"):
            if f"ipv4_{side}" in m:
                m[f"ipv6_{side}"] = "2001:db8:8::" + m.pop(f"ipv4_{side}").rsplit(".", 1)[1]
                m["eth_type"] = 0x86DD
        if p.get("kind") == "detection" and p.get("source"):
            p["source"] = "2001:db8:8::" + p["source"].rsplit(".", 1)[1]
    return out


@pytest.mark.parametrize("n", [5, 28])
def test_an_ipv6_twin_is_decided_alike(n):
    got = B.decide(_ipv6(BLIND[n]["section"]))
    assert got["decided"], got["words"]


def test_a_flood_code_did_not_decide_is_sent_its_shape():
    recorded = {c["n"]: c for c in _load("ai_cases/sdn_classify/recorded.json")}
    sent = CL.sent_evidence(recorded[5]["section"])
    (shape,) = [p for p in sent["pieces"] if p["kind"] == "shape"]
    assert shape["id"] == "shape:0000000000000001" and shape["id"] in sent["ids"]
    assert shape["holds"]["symmetric"] is False and shape["protocols"] == [17]


def test_an_evaluation_s_batch_decides_the_same_cases_with_no_request(monkeypatch):
    from modules.ai import gateway

    asked = []
    monkeypatch.setattr(gateway, "ask_batch", lambda reqs, **kw: asked.append(reqs) or {
        "ok": True, "error": "", "detail": "", "batch_id": "b", "worst_usd": 0.0,
        "results": {}})
    monkeypatch.setattr(CL, "prepare_classify", lambda *a, **k: {"refused": {"ok": False}})
    items = [{"n": n, "detection": BLIND[n]["detection"], "pack": _pack(BLIND[n])}
             for n in BENIGN]
    got = CL.classify_packs_batch("SDN lab", items, 2, actor="eval", trigger={},
                                  intact=False)
    assert asked == [] and len(got["results"]) == 20
    assert all(r["classification"]["by_code"] for r in got["results"].values())
