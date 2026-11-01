"""The recorded-case series helper (tests/sdn_series.py; C2237, C2238): a capture series is
checked for what a case needs and replayed through the detection rules as `detect.observe`
runs them.

The series here is tests/test_sdn_detect.py's own: the captured switch's flows and ports
(tests/test_sdn_collect.py's `Sampled`), port 1 receiving 100 packets a second for six passes
(the baseline), then 2,000 for five (a flood), then 100 again for five, ten seconds apart, as
the collector writes them. The replay is compared, pass by pass, with the real `observe` over
the same collections (its own stores, this test's), so "as observe runs them" is measured.
"""
import json
import time

import pytest

from modules.sdn import detect as D
from tests import sdn_series as S
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_detect import T0, VALUES, collect, lab, rx  # noqa: F401 - the fixture


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _plan(quiet_before=6, flood=5, quiet_after=5):
    """``[(at, extra packets in the second sample)]``: 500 is 100 a second, 10,000 is 2,000."""
    plan, n = [], 0
    for extra, count in ((500, quiet_before), (10000, flood), (500, quiet_after)):
        for _ in range(count):
            n += 1
            plan.append((T0 + 10 * n, extra))
    return plan


def _series(plan):
    passes = [{"kind": "pass", "n": i + 1, "collected": collect(at, second=rx(extra)),
               "topology": {"state": "read", "controllers": []}}
              for i, (at, extra) in enumerate(plan)]
    from modules.sdn import flow_intent
    head = {"kind": "head", "thresholds": {"ok": True, "values": dict(VALUES)},
            "intent": flow_intent.intent("Default")}
    return {"head": head, "passes": passes, "unparsed": 0}


def _keys(detections):
    return sorted(d["key"] for d in detections)


@pytest.mark.usefixtures("lab")
class TestReplay:
    def test_it_matches_observe_pass_by_pass(self):
        plan = _plan()
        series = _series(plan)
        got = S.replay(series)
        topo = {"state": "read", "controllers": []}
        seen = [D.observe("Default", p["collected"], values=VALUES, topo=topo)
                for p in series["passes"]]
        assert [_keys(g["detections"]) for g in got] == [_keys(o["detections"]) for o in seen]
        assert [[x["port"] for x in g["pending"]] for g in got] == \
            [[x["port"] for x in o["pending"]] for o in seen]
        assert any(g["detections"] for g in got), "the floor: the flood was detected"

    def test_the_flood_is_pending_through_its_hold_then_detected(self):
        got = S.replay(_series(_plan()))
        floods = [g["n"] for g in got if any(d["rule"] == "flood" for d in g["detections"])]
        hold = VALUES["sdn_flood_window_seconds"] // 10
        assert floods[0] == 7 + hold, floods
        assert all(g["pending"] for g in got if 7 <= g["n"] < floods[0])
        assert not any(d["rule"] in ("scan", "flood") for g in got if g["n"] < 7
                       for d in g["detections"]), "no scan or flood before it"


class TestCheck:
    def _series(self, n_before, n_during, n_after):
        passes, n = [], 0
        for count in (n_before, n_during, n_after):
            for _ in range(count):
                n += 1
                passes.append({"kind": "pass", "n": n, "collected": {
                    "state": "ok", "collected_at": _iso(T0 + 10 * n),
                    "controllers": [{"switches": [{}, {}]}]}})
        return {"head": {"thresholds": {"ok": True}}, "passes": passes, "unparsed": 0}

    def test_a_whole_series_holds_a_case(self):
        s = self._series(8, 6, 6)
        assert S.check(s, _iso(T0 + 85), _iso(T0 + 145)) == []

    def test_each_shortfall_is_named(self):
        s = self._series(3, 2, 1)
        s["passes"][1]["collected"]["state"] = "unreadable"
        s["passes"][2]["collected"]["controllers"] = [{"switches": [{}]}]
        s["head"], s["unparsed"] = None, 2
        got = S.check(s, _iso(T0 + 35), _iso(T0 + 55))
        assert got == [
            "no head line: the thresholds and flow intent the rules ran with are unknown",
            "2 line(s) did not parse", "6 passes, fewer than 18",
            "passes [2, 3] were not read whole (state ok with 2 switches)",
            "3 pass(es) before the traffic, fewer than 6",
            "2 pass(es) inside it, fewer than 4",
            "1 pass(es) after it ended, fewer than 3"]


def test_load_reads_the_collector_s_lines_and_counts_what_did_not_parse(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join([json.dumps({"kind": "head", "label": "RC-ICMP"}),
                            json.dumps({"kind": "pass", "n": 1, "collected": {}}),
                            "{not json", ""]), encoding="utf-8")
    got = S.load(str(p))
    assert got["head"]["label"] == "RC-ICMP" and len(got["passes"]) == 1
    assert got["unparsed"] == 1
