"""SDN detection rules (`modules/sdn/detect.py`, PHASE8_PLAN 17.1 S6): scan, flood and
unauthorised flow over `collect_threat_data`'s answer, each detection an alert in Mercury's
alert stream with an evidence pack, Explain reading it unchanged.

**The data.** Every collection is made by the real `collect_threat_data` through the real
connection and Ryu driver from S1's capture (tests/fixtures/sdn/ryu/rest_with_peer.json, via
tests/test_sdn_collect.py's `Sampled`), a fake clock and no sleep. The minimal edits, each
made where it is used:
- **a scan:** the captured IPv4 L4 flow (in_port 1, 192.0.2.1 to 192.0.2.2, `tp_dst` 22)
  copied with only `tp_dst` changed, one copy per destination port; the IPv6 scan copies the
  captured IPv6 L4 flow (2001:db8::1 to 2001:db8::2, `tp_dst` 443) the same way;
- **a port's rate:** the second port sample is the captured read with port 1's `rx_packets`
  raised (500 more is 100 packets a second over the 5 s sample, the capture's own edit in
  test_sdn_collect; 10,000 more is 2,000 a second, the flood);
- **L2 coverage:** the captured flows less those naming an IP address (as test_sdn_collect's
  coverage test does);
- **an IPv4 or an IPv6 flood:** port 1's flows less the other family's L4 flow, so the flood's
  one source is 192.0.2.1 or 2001:db8::1.
The capture's own two Mercury-prefixed flows (cookies ...0001 and ...0002), with no record, are
the unauthorised flows; recording the /24 drop's spec (test_sdn_ryu's `DROP`) makes it
Mercury's.
"""
import copy
import json

import pytest

from modules import alert_history as H
from modules import evidence_pack as EP
from modules import list_settings as L
from modules.sdn import closed_loop as CL
from modules.sdn import connections as C
from modules.sdn import detect as D
from modules.sdn import flow_intent as F
from tests.sdn_fakes import Clock, Response
from tests.test_sdn_collect import BASE, BASE6, Sampled, captured_flows, second_ports
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ryu import DROP

T0 = 1_790_000_000.0
VALUES = dict(D.THRESHOLDS)
V4_L4 = ("192.0.2.1", 22)
V6_L4 = ("2001:db8::1", 443)


def save(name="ctl-1", url=BASE):
    C.save_connection("Default", {"name": name, "kind": "ryu", "url": url}, actor="op")


def l4_copy(src, port):
    """The captured L4 flow from *src*, only its destination port changed."""
    base = next(f for f in captured_flows()
                if (f["match"].get("nw_src") or f["match"].get("ipv6_src")) == src[0]
                and f["match"].get("tp_dst") == src[1])
    flow = copy.deepcopy(base)
    flow["match"]["tp_dst"] = port
    return flow


def scan_flows(n, src=V4_L4, first=1000):
    """The capture's flows and *n* copies of *src*'s L4 flow to ports first..first+n-1."""
    return captured_flows() + [l4_copy(src, first + i) for i in range(n)]


def rx(extra):
    """The second port sample with port 1 receiving *extra* packets more than the capture."""
    def edit(ports):
        ports[1]["rx_packets"] += extra - 500
    return second_ports(edit)


def without(family):
    """Port 1's flows less the *family* L4 flow ("v4" or "v6")."""
    gone = "nw_src" if family == "v4" else "ipv6_src"
    return [f for f in captured_flows() if not (gone in f["match"] and "tp_dst" in f["match"])]


def collect(at, flows=None, second=None, url=BASE):
    sessions = {"ctl-1": Sampled(url, second=second, flows=flows)}
    clock = Clock()
    return CL.collect_threat_data(
        "Default", 5.0, sleep=lambda s: setattr(clock, "now", clock.now + s), clock=clock,
        now=lambda: at,
        driver=lambda net, name: C.driver_for(net, name, session=sessions[name]))


def observe(at, **kw):
    return D.observe("Default", collect(at, **kw), values=VALUES)


def history():
    return [r for r in H.read()["rows"] if r.get("kind") == "transition"]


@pytest.fixture
def lab(networks):
    save()
    return networks


# ───────────────────────────────────────────────────────────────────────────── evidence ids

@pytest.mark.usefixtures("lab")
class TestEvidenceIds:
    def test_every_flow_and_port_carries_an_id_stable_across_collections(self):
        one = collect(T0)["controllers"][0]["switches"][0]
        two = collect(T0 + 10)["controllers"][0]["switches"][0]
        assert [f["id"] for f in one["flows"]] == [f["id"] for f in two["flows"]]
        assert len({f["id"] for f in one["flows"]}) == 9, "no two flows share an id"
        assert [p["id"] for p in one["ports"]] == [
            "port:ctl-1:0000000000000001:1", "port:ctl-1:0000000000000001:2",
            "port:ctl-1:0000000000000001:3", "port:ctl-1:0000000000000001:LOCAL"]

    def test_a_match_spelled_either_way_is_one_id(self):
        dotted = {"table_id": 0, "priority": 100,
                  "match": {"eth_type": 2048, "ipv4_src": "192.0.2.0/255.255.255.0"}}
        prefix = dict(dotted, match={"ipv4_src": "192.0.2.0/24", "eth_type": "2048"})
        assert CL.flow_ref("ctl-1", 1, dotted) == CL.flow_ref("ctl-1", 1, prefix)
        v6 = dict(dotted, match={"ipv6_src": "2001:DB8::0/64"})
        assert CL.flow_ref("ctl-1", 1, v6) == CL.flow_ref(
            "ctl-1", 1, dict(dotted, match={"ipv6_src": "2001:db8::/64"}))


# ───────────────────────────────────────────────────────────────────────────── scan

@pytest.mark.usefixtures("lab")
class TestScan:
    @pytest.mark.parametrize("src,dst", [(V4_L4, "192.0.2.2"), (V6_L4, "2001:db8::2")])
    def test_a_source_reaching_many_destination_ports_is_a_scan(self, src, dst):
        got = collect(T0, flows=scan_flows(25, src))
        out = D.scan(got, VALUES)
        (d,) = out["detections"]
        assert (d["rule"], d["source"], d["targets"], d["confidence"]) == \
            ("scan", src[0], [dst], "high")
        # 25 copies, plus the captured flow's own port unless it is in the copied range.
        assert d["measurement"]["value"] == 26 and d["measurement"]["unit"] == "ports"
        assert d["threshold"] == {"what": "the scan's ports in its window", "value": 20,
                                  "unit": "ports", "window_s": 60, "setting": "sdn_scan_ports",
                                  "window_setting": "sdn_scan_window_seconds"}
        assert "at or above the threshold of 20 (sdn_scan_ports)" in d["words"]
        ids = {f["id"] for f in got["controllers"][0]["switches"][0]["flows"]}
        assert len(d["evidence"]) == 26 and set(d["evidence"]) <= ids, \
            "every evidence id is a flow in the collected data"
        assert (d["connection"], d["dpid_hex"]) == ("ctl-1", "0000000000000001")

    def test_it_counts_destination_ports_never_source_ports(self):
        """30 flows from one source to ONE destination port, each from its own source port:
        one destination port, no scan."""
        flows = captured_flows()
        for i in range(30):
            f = l4_copy(V4_L4, 22)
            f["match"]["tp_src"] = 40000 + i          # the edit: a distinct source port
            flows.append(f)
        assert D.scan(collect(T0, flows=flows), VALUES)["detections"] == []

    def test_below_the_threshold_is_no_scan(self):
        assert D.scan(collect(T0, flows=scan_flows(18)), VALUES)["detections"] == []

    def test_the_window_counts_across_collections_and_ages_out(self):
        first = D.scan(collect(T0, flows=scan_flows(12)), VALUES)
        assert first["detections"] == []
        second = D.scan(collect(T0 + 30, flows=scan_flows(12, first=2000)), VALUES,
                        first["seen"])
        (d,) = second["detections"]
        assert d["measurement"]["value"] == 25 and d["measurement"]["in_this_collection"] == 13
        later = D.scan(collect(T0 + 100, flows=captured_flows()), VALUES, second["seen"])
        assert later["detections"] == [], "sightings past the 60 s window no longer count"

    def test_tcp_and_udp_ports_are_counted_apart(self):
        assert D._dst_port({"tcp_dst": 53}) == "tcp/53"
        assert D._dst_port({"udp_dst": "53"}) == "udp/53"


@pytest.mark.usefixtures("lab")
class TestTheFallback:
    def _l2(self):
        return [f for f in captured_flows() if "nw_src" not in f["match"]
                and "ipv6_src" not in f["match"]]

    def test_l2_flows_fall_back_to_the_port_rate_at_lower_confidence(self):
        got = collect(T0, flows=self._l2(), second=rx(10000))
        (d,) = D.scan(got, VALUES)["detections"]
        assert (d["rule"], d["port"], d["confidence"], d["basis"]) == \
            ("scan", 1, "lower", "rate")
        assert d["measurement"]["value"] == 2000.0 and d["threshold"]["value"] == 100
        assert "cannot show a per-port scan" in d["confidence_why"]
        assert "a rate alone cannot tell a scan from other heavy traffic" in d["confidence_why"]
        assert d["evidence"][0] == "port:ctl-1:0000000000000001:1"

    def test_a_port_under_the_fallback_rate_is_no_scan(self):
        assert D.scan(collect(T0, flows=self._l2(), second=rx(450)), VALUES)["detections"] == []

    def test_an_l4_switch_never_falls_back(self):
        assert D.scan(collect(T0, second=rx(10000)), VALUES)["detections"] == []


# ───────────────────────────────────────────────────────────────────────────── flood

def baseline_runs(n=5, start=T0, step=10.0, **kw):
    """*n* collections at 100 packets a second on port 1, each judged: a baseline."""
    outs = []
    for i in range(n):
        outs.append(observe(start + i * step, second=rx(500), **kw))
    return outs


@pytest.mark.usefixtures("lab")
class TestFlood:
    def test_a_port_with_no_baseline_yet_is_never_a_flood(self):
        """A window of 0 fires at the first collection over, so only the missing baseline
        stands between 10,000 packets a second and a detection."""
        out = D.observe("Default", collect(T0, second=rx(50000)),
                        values=dict(VALUES, sdn_flood_window_seconds=0))
        assert out["ok"] and not [d for d in out["detections"] if d["rule"] == "flood"]
        assert out["pending"] == []
        port = next(n for n in out["no_baseline"] if n["port"].endswith(":1"))
        assert port["words"] == "no baseline yet (0 of 5 earlier collections)"

    def test_the_baseline_is_ready_after_five_collections(self):
        outs = baseline_runs(5)
        assert outs[-1]["no_baseline"][0]["words"] == "no baseline yet (4 of 5 earlier " \
                                                      "collections)"
        nxt = observe(T0 + 50, second=rx(500))
        assert not [n for n in nxt["no_baseline"] if n["port"].endswith(":1")]

    @pytest.mark.parametrize("family,src,url", [("v6", "192.0.2.1", BASE),
                                                ("v4", "2001:db8::1", BASE6)])
    def test_a_rate_held_over_the_factor_for_the_window_is_a_flood(self, family, src, url):
        """IPv4 (the IPv6 flow taken away) and IPv6 (the IPv4 one taken away, the controller
        reached over IPv6)."""
        if url == BASE6:
            C.save_connection("Default", {"name": "ctl-1", "kind": "ryu", "url": BASE6},
                              actor="op")
        kw = {"flows": without(family), "url": url}
        baseline_runs(5, **kw)
        pending = observe(T0 + 50, second=rx(10000), **kw)
        assert pending["fired"] == [] and pending["pending"][0]["words"] == \
            "over its threshold for 0 s of 30 s"
        assert observe(T0 + 70, second=rx(10000), **kw)["fired"] == []
        out = observe(T0 + 80, second=rx(10000), **kw)
        (d,) = [d for d in out["detections"] if d["rule"] == "flood"]
        assert out["fired"] == [d["key"]]
        assert d["measurement"]["value"] == 2000.0 and d["measurement"]["held_s"] == 30
        assert d["threshold"]["baseline_pps"] == 100.0 and d["threshold"]["value"] == 500.0
        assert d["threshold"]["factor"] == 5 and d["threshold"]["window_s"] == 30
        assert d["source"] == src and d["sources"] == [src]
        assert "at or above 5x its baseline of 100 (500), for 30 s" in d["words"]

    def test_a_flood_is_never_its_own_baseline(self):
        baseline_runs(5)
        for t in (50, 60, 70, 80):
            observe(T0 + t, second=rx(10000))
        state = D.read_state()["doc"]["networks"]["Default"]
        assert state["baseline"]["port:ctl-1:0000000000000001:1"]["samples"] == [100.0] * 5

    def test_a_collection_under_the_threshold_clears_the_wait(self):
        baseline_runs(5)
        observe(T0 + 50, second=rx(10000))
        observe(T0 + 60, second=rx(500))
        assert observe(T0 + 80, second=rx(10000))["pending"][0]["measurement"]["held_s"] == 0


# ───────────────────────────────────────────────────────────────────────────── unauthorised

@pytest.mark.usefixtures("lab")
class TestUnauthorised:
    def test_mercury_s_prefix_with_no_record_is_unauthorised(self):
        got = collect(T0)
        out = D.unauthorised(got, F.intent("Default"), now=T0)
        cookies = sorted(d["measurement"]["cookie"] for d in out["detections"])
        assert cookies == ["0x4d45524300000001", "0x4d45524300000002"]
        d = out["detections"][0]
        assert d["rule"] == "unauthorised_flow" and d["confidence"] == "high"
        assert d["threshold"]["own_cookies"] == ["0x0000000000000000"]
        assert "no record" in d["measurement"]["why"]

    def test_a_recorded_flow_is_mercury_s_and_the_application_s_are_its_own(self):
        F.record_installed("Default", connection="ctl-1", flow=dict(DROP, dpid=1),
                           actor="op@example.com", response={"id": "r1", "action": "drop"},
                           at=T0)
        out = D.unauthorised(collect(T0 + 10), F.intent("Default"), now=T0 + 10)
        assert [d["measurement"]["cookie"] for d in out["detections"]] == \
            ["0x4d45524300000002"]

    def test_an_unreadable_intent_judges_nothing_and_says_so(self):
        out = D.unauthorised(collect(T0), {"state": "unreadable", "error": "torn"})
        assert out["detections"] == [] and out["judged"] == set()
        assert "could not be read (torn)" in out["error"]


# ───────────────────────────────────────────────────────────────────────────── the alert

@pytest.mark.usefixtures("lab")
class TestEachDetectionIsAnAlert:
    def test_it_fires_once_with_a_transition_and_a_pack(self):
        out = observe(T0)
        assert out["ok"] and len(out["fired"]) == 2 and out["changed"]
        rows = history()
        assert {(r["store"], r["source"], r["to"], r["rule"]) for r in rows} == \
            {("sdn", "sdn", "condition", "SDN unauthorised flow")}
        assert all(r["at"] == "2026-09-21T14:13:20Z" for r in rows)
        assert "Mercury's clock" in rows[0]["at_basis"]
        packs = EP.read()["rows"]
        assert len(packs) == 2 and all(EP.intact(p) for p in packs)
        again = observe(T0 + 10)
        assert again["fired"] == [] and not again["changed"]
        assert len(history()) == 2 and len(EP.read()["rows"]) == 2

    def test_it_resolves_when_no_longer_seen(self):
        observe(T0)
        gone = [f for f in captured_flows() if f["cookie"] != 0x4D45524300000002]
        out = observe(T0 + 10, flows=gone)
        assert len(out["resolved"]) == 1 and out["firing"] == 1
        resolved = [r for r in history() if r["to"] == "normal"]
        assert len(resolved) == 1 and resolved[0]["at"] == "2026-09-21T14:13:30Z"
        eps = H.episodes(H.read()["rows"], H._firing_now())
        done = [e for e in eps if not e["ongoing"]]
        assert len(done) == 1 and done[0]["resolved_at"] == "2026-09-21T14:13:30Z"
        assert len([e for e in eps if e["ongoing"]]) == 1, "the other still fires"

    def test_a_subject_not_read_stays_firing(self):
        observe(T0)
        # Port 1 at 20 packets a second, under the scan fallback's rate (with the flows unread,
        # the fallback judges the ports).
        out = observe(T0 + 10, flows=Response(500, "Traceback\nboom"), second=rx(100))
        assert out["resolved"] == [] and out["firing"] == 2
        assert len(out["unjudged"]) == 2 and "was not read" in out["unjudged"][0]["words"]

    def test_the_tab_draws_it_firing_with_its_pack(self):
        observe(T0)
        tab = EP.tab()
        assert tab["counts"]["firing"] == 2 and tab["counts"]["packed"] == 2
        assert {"store": "sdn", "state": "ok"}.items() <= next(
            s for s in tab["sources"] if s["store"] == "sdn").items()
        assert {g["family"] for g in tab["groups"]} == {"SDN unauthorised flow"}

    def test_an_older_collection_is_refused(self):
        observe(T0 + 10)
        out = observe(T0)
        assert not out["ok"] and "older than the one last judged" in out["error"]

    def test_an_unreadable_state_refuses_and_is_kept_aside(self, lab):
        (lab / D.STATE_FILE).write_text("{torn", encoding="utf-8")
        out = observe(T0)
        assert not out["ok"] and "could not be read" in out["error"]
        assert list(lab.glob(D.STATE_FILE + ".corrupt-*"))
        assert D.firing()["state"] == "unreadable"

    def test_a_transition_the_history_refused_is_offered_again(self, monkeypatch):
        real = H.record
        monkeypatch.setattr(H, "record", lambda rows: {
            "ok": False, "added": 0, "held": 0, "unopened": 0, "error": "disk full"})
        out = observe(T0)
        assert out["ok"] and "offered again" in out["notes"][-1]
        monkeypatch.setattr(H, "record", real)
        observe(T0 + 10)
        assert len(history()) == 2

    def test_no_sdn_state_leaves_the_tab_as_before(self):
        tab = EP.tab()
        assert all(s["store"] != "sdn" for s in tab["sources"])


# ───────────────────────────────────────────────────────────────────────────── the pack

@pytest.mark.usefixtures("lab")
class TestThePack:
    def _pack(self, rule="scan", **kw):
        out = observe(T0, **kw)
        assert out["ok"], out["error"]
        d = next(d for d in out["detections"] if d["rule"] == rule)
        inst = D.read_state()["doc"]["networks"]["Default"]["firing"][d["key"]]
        return EP.find(inst["pack"])[0], d

    def test_its_sdn_section_holds_what_the_detection_rests_on_captured(self):
        pack, d = self._pack(flows=scan_flows(25))
        assert [s["name"] for s in pack["sections"]] == ["alert", "device", "sdn"]
        sdn = EP.resolve(pack, "sdn")
        assert sdn["provenance"] == "captured" and sdn["read_at"] == "2026-09-21T14:13:20Z"
        first = EP.resolve(pack, "sdn:1")
        assert first["kind"] == "detection" and first["measurement"]["value"] == 26
        flows = [p for p in sdn["pieces"] if p["kind"] == "flow"]
        assert {p["id"] for p in flows} == set(d["evidence"])
        assert EP.resolve(pack, "device")["state"] == "absent"
        assert pack["store"] == "sdn" and pack["provenance"] == "captured"
        alert = EP.resolve(pack, "alert:1")
        assert alert["labels"]["source"] == "192.0.2.1" and alert["kind"] == "condition"

    def test_other_packs_are_unchanged(self):
        assert "sdn" not in EP.SECTIONS
        from modules.ai import explain
        assert "sdn" not in explain.vocabulary()

    def test_history_finds_the_pack_of_a_resolved_detection(self):
        pack, _d = self._pack(flows=scan_flows(25))
        observe(T0 + 100, flows=captured_flows())
        got = H.tab({"range": "all"}, now=T0 + 200)
        eps = [e for g in got["groups"] if g["family"] == "SDN scan" for e in g["episodes"]]
        assert len(eps) == 1 and eps[0]["pack"]["id"] == pack["id"]


# ───────────────────────────────────────────────────────────────────────────── Explain

@pytest.mark.usefixtures("lab")
class TestExplainReadsIt:
    def test_the_section_is_sent_while_the_topology_class_is_allowed(self):
        from modules.ai import explain
        pack, _d = TestThePack()._pack(flows=scan_flows(25))
        sent = {s["name"]: s for s in explain.sent_sections(pack, explain.topology(pack))}
        assert sent["sdn"]["pieces"] and "withheld" not in sent["sdn"]

    def test_the_section_is_withheld_when_the_class_is_off(self):
        from modules.ai import explain
        pack, _d = TestThePack()._pack(flows=scan_flows(25))
        L.write("Default", {"ai_topology_class": False}, actor="op")
        sent = {s["name"]: s for s in explain.sent_sections(pack, explain.topology(pack))}
        assert sent["sdn"]["pieces"] == []
        assert "the topology class is off for Default" in sent["sdn"]["withheld"]
        assert "flows and port rates are not sent" in sent["sdn"]["withheld"]

    def test_explain_answers_citing_the_section(self, monkeypatch, tmp_path):
        from modules import settings_schema
        from modules.ai import anthropic_adapter as A
        from modules.ai import calls, explain, gateway, prompts
        settings = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                                  "reason": "the lab's proof of concept"},
                    "ai_cap_usd_per_day": 1.50}
        real = settings_schema.get_setting
        monkeypatch.setattr(settings_schema, "get_setting",
                            lambda k, d=None: settings[k] if k in settings else real(k, d))
        monkeypatch.setattr(gateway, "_api_key", lambda: "sk-planted-test-key-0123456789")
        monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
        monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
        pack, _d = TestThePack()._pack(flows=scan_flows(25))
        sent = []
        answer = {"outcome": "answer", "rationale": "One source reached 26 ports.",
                  "hypotheses": [{"claim": "192.0.2.1 is scanning 192.0.2.2.",
                                  "evidence_refs": ["sdn:1", "sdn:2"],
                                  "confirm_with": "show interfaces"}],
                  "checked": [], "needs_human": False, "why_not": ""}

        def send(body, key):
            sent.append(body)
            asked = body["output_config"]["format"]["schema"].get("properties") or {}
            return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(
                {k: v for k, v in answer.items() if k in asked})}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 4000, "output_tokens": 300}},
                attempts=1, latency_s=0.9)
        monkeypatch.setattr(A, "send", send)
        got = explain.explain(pack["id"], actor="operator@example.com", send=send,
                              today="2026-10-25")
        assert got["ok"] is True, got
        assert [c["ref"] for c in got["answer"]["hypotheses"][0]["cites"]] == ["sdn:1", "sdn:2"]
        content = sent[0]["messages"][0]["content"]
        assert '"name":"sdn"' in content and "192.0.2.1" in content
        prefix = sent[0]["system"][1]["text"]
        assert explain.vocabulary() in prefix and "sdn" not in prefix, "the prefix unchanged"
        assert sent[0]["system"][0]["text"] == prompts.load(*explain.PROMPT)["text"]


# ───────────────────────────────────────────────────────────────────────────── thresholds

@pytest.mark.usefixtures("lab")
class TestThresholds:
    def test_the_defaults(self):
        got = D.thresholds("Default")
        assert got["ok"] and got["values"] == {
            "sdn_scan_ports": 20, "sdn_scan_window_seconds": 60, "sdn_scan_fallback_pps": 100,
            "sdn_flood_factor": 5, "sdn_flood_window_seconds": 30}

    def test_a_network_s_own_are_its_own(self):
        L.write("Default", {"sdn_scan_ports": 30, "sdn_flood_factor": 3}, actor="op")
        got = D.thresholds("Default")["values"]
        assert (got["sdn_scan_ports"], got["sdn_flood_factor"]) == (30, 3)
        out = D.observe("Default", collect(T0, flows=scan_flows(25)))
        assert out["thresholds"]["sdn_scan_ports"] == 30
        assert not [d for d in out["detections"] if d["rule"] == "scan"], "26 < 30"

    def test_a_value_a_rule_cannot_use_refuses_the_run(self, monkeypatch):
        monkeypatch.setattr(L, "value", lambda net, key, default=None:
                            "lots" if key == "sdn_scan_ports" else default)
        got = D.thresholds("Default")
        assert not got["ok"] and "sdn_scan_ports is 'lots'" in got["error"]
        out = D.observe("Default", collect(T0))
        assert not out["ok"] and out["fired"] == []
