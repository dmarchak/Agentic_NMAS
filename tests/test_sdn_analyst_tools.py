"""The SDN analyst with the trace tool (Lab 9 B4; modules/ai/sdn_analyst_tools.py;
docs/HEAL_TO_INTENT.md 19.12 and 19.13; board I's alternative on SDN › Flows).

The controller is B1's: the lab's recorded Ryu (tests/test_sdn_analyst.py's `LabRyu`, the real
switch list, links and port descriptions, flow tables and counters planted in Ryu's shapes), with
one more planted answer, its host table (`/v1.0/topology/hosts`, which the capture did not
record): three hosts on Open vSwitch 3, in Ryu 4.34's shape. No model is called: the gateway is
real (its trigger, caps, mask and record) and its provider a fake `send` answering each call in
turn from a script.

- **The collection** keeps the controller's hosts with the snapshot, and B1's facts never send
  them; a host read that fails is said, and the snapshot then holds no host table.
- **The trace tool** walks the sealed snapshot's flow tables, IPv4 and IPv6 alike, a drop flow
  deciding, and names the evidence ids it passed; it reads nothing live.
- **Each read** is held to the closed set and to what the snapshot holds, by shape and by
  comparison, else refused naming both; a fourth is refused.
- **The loop** is two calls at most, pass 2 cannot ask again, and its total token cap stops pass 2
  before it is sent.
- **The final answer** is checked as B1's, a read that ran citable.
- **The comparison** with B1's answer on the same snapshot: found, missed, false positives by the
  code's rule, calls and cost.
- **The person trigger**, the topology class, and the route and its region.
"""
import json
import types
from html import unescape

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, gateway, read_log, triggers
from modules.ai import read_loop as RL
from modules.sdn import analyst as AN
from modules.ai import sdn_analyst_tools as AT
from modules.sdn import connections as C
from tests.ai_person import PERSON, pressed_by
from tests.sdn_fakes import Response
from tests.test_sdn_analyst import NET, OVS3, LabRyu, finding, world  # noqa: F401 (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

#: Planted host table entries (Ryu 4.34's `rest_topology` shape), each on Open vSwitch 3's port 3,
#: the capture's one port that is no link (every other port of its fabric is): a source, the
#: destination OVS3_FLOWS forward out port 2, toward Open vSwitch 4, and the address the planted
#: drop flow matches. A host Ryu learned on a link port is never a trace's end (`trace.fabric`).
HOSTS = [
    {"mac": "0a:00:00:00:00:10", "ipv4": ["198.51.100.10"], "ipv6": ["2001:db8::10"],
     "port": {"dpid": OVS3, "port_no": "00000003", "hw_addr": "02:9c:90:e0:25:af",
              "name": "eno4"}},
    {"mac": "0a:00:00:00:00:20", "ipv4": ["198.51.100.20"], "ipv6": ["2001:db8::20"],
     "port": {"dpid": OVS3, "port_no": "00000003", "hw_addr": "02:9c:90:e0:25:af",
              "name": "eno4"}},
    {"mac": "0a:00:00:00:00:fa", "ipv4": ["198.51.100.250"], "ipv6": [],
     "port": {"dpid": OVS3, "port_no": "00000003", "hw_addr": "02:9c:90:e0:25:af",
              "name": "eno4"}},
]
OVS4 = "0000000000000004"
LINK_3_4 = "link:ctl-1:0000000000000003:2-0000000000000004:2"


class HostsRyu(LabRyu):
    """B1's recorded Ryu, and the planted host table."""

    def request(self, method, url, **kwargs):
        if url.endswith("/v1.0/topology/hosts"):
            self.sent.append(dict(kwargs, method=method, url=url))
            return Response(200, json.dumps(HOSTS))
        return super().request(method, url, **kwargs)


def collected_snapshot(session=None):
    session = session or HostsRyu()
    got = AN.collect_job(NET, actor=PERSON, sleep=lambda s: None, announce=False,
                         driver=lambda net, name: C.driver_for(net, name, session=session))
    assert got["ok"], got
    return got["snapshot"], session


def reply(answer: dict, tokens=(6000, 400)):
    return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(answer)}],
                                     "stop_reason": "end_turn",
                                     "usage": {"input_tokens": tokens[0],
                                               "output_tokens": tokens[1]}},
                   attempts=1, latency_s=0.1)


@pytest.fixture
def tw(world):  # noqa: F811 - the fixture, used
    """B1's world, its provider answering each call in turn from `tw.script`."""
    tw = types.SimpleNamespace(sent=world.sent, script=[], dir=world.dir)

    def send(body, key):
        tw.sent.append(body)
        if not tw.script:
            pytest.fail("the provider was asked more times than the script answers")
        return reply(tw.script.pop(0))
    tw.send = send
    return tw


def ask(op, why="to check", **args):
    return {"op": op, "args": args, "why": why, "hypothesis": "something is wrong there"}


def tools(tw, snap, **kw):
    with pressed_by(PERSON):
        return AT.analyse(NET, snap["id"], actor=PERSON, trigger=triggers.person(PERSON),
                          send=tw.send, **kw)


def flows_of(snap, dpid=OVS3):
    return next(s for s in snap["switches"] if s["dpid_hex"] == dpid)


# ── the collection keeps the hosts ────────────────────────────────────────────────────────────

def test_the_collection_keeps_the_controller_s_hosts_and_b1_never_sends_them(tw):
    snap, session = collected_snapshot()
    assert sum(u["url"].endswith("/v1.0/topology/hosts") for u in session.sent) == 1
    assert [(h["dpid_hex"], h["port_no"], h["mac"]) for h in snap["hosts"]] == [
        (OVS3, 3, "0a:00:00:00:00:10"), (OVS3, 3, "0a:00:00:00:00:20"),
        (OVS3, 3, "0a:00:00:00:00:fa")]
    assert AN.intact(snap) and AN.latest_snapshot(NET)["hosts"] == snap["hosts"]
    assert AN.view(NET)["tools"]["hosts"] == 3
    tw.script = [{"findings": []}]
    with pressed_by(PERSON):
        AN.analyse(NET, snap["id"], actor=PERSON, trigger=triggers.person(PERSON), send=tw.send)
    (body,) = tw.sent
    assert "0a:00:00:00:00:10" not in json.dumps(body) and "hosts" not in AN.facts(snap)


def test_a_host_read_that_fails_is_said_and_no_trace_can_start(tw):
    snap, _session = collected_snapshot(LabRyu())
    assert "hosts" not in snap
    assert any(u.startswith("controller ctl-1's hosts:") for u in snap["unread"])
    got = AT.trace_answer(snap, "198.51.100.10", "198.51.100.20")
    assert "holds no host table" in got["refused"]
    why = RL.check(AT.SEALED, [ask("trace", src="198.51.100.10", dst="198.51.100.20",
                                   proto="icmp")], network=NET, scope={"snapshot": snap})
    assert why[0]["verdict"] == "refused" and "holds no host table" in why[0]["reason"]
    assert AN.view(NET)["tools"]["hosts"] is None


# ── the trace tool over the seal ──────────────────────────────────────────────────────────────

def test_ipv4_and_ipv6_traces_walk_the_sealed_flow_tables_across_a_link(tw):
    """Each family's flow on Open vSwitch 3 sends the packet out port 2, across the discovered
    link to Open vSwitch 4, whose table-miss sends it to the controller: each hop's deciding
    flow, its ports and the link are the evidence the trace names."""
    snap, _s = collected_snapshot()
    sw, miss4 = flows_of(snap), flows_of(snap, OVS4)["flows"][0]["id"]
    v4 = next(f["id"] for f in sw["flows"] if "ipv4_dst" in f["match"])
    v6 = next(f["id"] for f in sw["flows"] if "ipv6_dst" in f["match"])
    four = AT.trace_answer(snap, "198.51.100.10", "198.51.100.20")
    assert four.get("state") == "not_delivered" and four["family"] == 4, four
    assert four["branches"][0]["outcome"] == "to_controller"
    assert four["branches"][0]["hops"] == [
        {"switch": OVS3, "in": 3, "out": 2, "flows": [v4]},
        {"switch": OVS4, "in": 2, "out": "CONTROLLER", "flows": [miss4]}]
    assert {v4, miss4, LINK_3_4, f"port:ctl-1:{OVS3}:2", f"port:ctl-1:{OVS4}:2"} <= \
        set(four["evidence"])
    six = AT.trace_answer(snap, "2001:db8::10", "2001:db8::20", "tcp", 443)
    assert six["state"] == "not_delivered" and six["family"] == 6 and six["port"] == 443
    assert six["branches"][0]["hops"][0]["flows"] == [v6] and v6 in six["evidence"]
    assert v4 not in six["evidence"] and LINK_3_4 in six["evidence"]


def test_a_drop_flow_decides_a_trace_and_is_cited(tw):
    snap, _s = collected_snapshot()
    (drop,) = flows_of(snap)["drops"]
    got = AT.trace_answer(snap, "198.51.100.250", "198.51.100.20", "udp", 53)
    assert got["state"] == "not_delivered" and got["branches"][0]["outcome"] == "dropped"
    assert drop["id"] in got["evidence"] and got["branches"][0]["hops"][0]["flows"] == [drop["id"]]


def test_every_read_is_served_from_the_seal_and_never_live(tw, monkeypatch):
    from modules import reader_job
    from modules.sdn import closed_loop, trace

    snap, session = collected_snapshot()
    before = len(session.sent)

    def live(*a, **k):
        pytest.fail("a read reached something live")
    for target, name in ((reader_job, "read_cached_for"), (C, "driver_for"),
                         (closed_loop, "collect_threat_data"), (trace, "fabric"),
                         (AN, "latest_snapshot")):
        monkeypatch.setattr(target, name, live)
    tw.script = [{"findings": [], "reads": [
                     ask("trace", src="198.51.100.10", dst="198.51.100.20", proto="icmp"),
                     ask("switch_flows", dpid=OVS3), ask("link_state", dpid=OVS3, port=3)]},
                 {"findings": []}]
    r = tools(tw, snap)
    assert r["ok"] and [x["verdict"] for x in r["reads"]] == ["run", "run", "run"]
    assert r["reads"][0]["short"].startswith("Not delivered:")
    assert r["reads"][2]["short"].startswith("link DOWN")
    assert len(session.sent) == before, "no controller was asked"
    (row,) = [x for x in read_log.read()["rows"] if x["row"] == "reads"]
    assert [e["commands"] for e in row["reads"]] == [
        ["snapshot trace 198.51.100.10 198.51.100.20 icmp"], [f"snapshot flows {OVS3}"],
        [f"snapshot link {OVS3} 3"]]
    assert {e["egress_class"] for e in row["reads"]} == {"topology"}


# ── each read checked ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("request_, words", [
    (ask("delete_flow", dpid=OVS3), "is not an operation of the sdn_sealed read family"),
    (ask("switch_flows", dpid="00000000000000ff"), "00000000000000ff is not a switch the "
                                                  "snapshot holds: it holds"),
    (ask("port_stats", dpid=OVS3, port=9), f"port 9 is not a port the snapshot lists for {OVS3}"),
    (ask("trace", src="198.51.100.99", dst="198.51.100.20", proto="icmp"),
     "198.51.100.99 is no host the snapshot lists (3 hosts listed)"),
    (ask("trace", src="198.51.100.10", dst="198.51.100.20", proto="icmp", port=80),
     "an ICMP echo has no port"),
    (ask("trace", src="198.51.100.10", dst="198.51.100.20", proto="tcp"),
     "a TCP trace needs its destination port"),
    (ask("trace", src="0A:00:00:00:00:10", dst="198.51.100.20", proto="icmp"),
     "is not a host's IPv4 or IPv6 address, or its MAC"),
    (ask("link_state", dpid=OVS3, port=True), "is not a port number, or LOCAL"),
    (ask("switch_flows", dpid=OVS3, device="r1"), "takes no argument"),
])
def test_a_read_out_of_the_set_or_the_snapshot_is_refused_naming_why(tw, request_, words):
    snap, _s = collected_snapshot()
    (got,) = RL.check(AT.SEALED, [request_], network=NET, scope={"snapshot": snap})
    assert got["verdict"] == "refused" and words in got["reason"], got["reason"]


def test_a_fourth_read_is_refused_and_a_refused_read_never_runs(tw):
    snap, _s = collected_snapshot()
    tw.script = [{"findings": [], "reads": [ask("switch_flows", dpid=OVS3)] * 3
                  + [ask("port_stats", dpid=OVS3)]},
                 {"findings": []}]
    r = tools(tw, snap)
    assert [x["verdict"] for x in r["reads"]] == ["run", "run", "run", "refused"]
    assert "past the 3 reads a pass may ask for" in r["reads"][3]["reason"]
    assert r["reads"][3]["short"] == ""


def test_the_seal_transport_declares_only_a_snapshot_read():
    with pytest.raises(RL.Undeclarable, match="a sealed read is 'snapshot <section>'"):
        RL.ReadFamily(name="planted", transport="seal", egress_class="topology",
                      run=lambda *a: "", operations=(RL.Operation(
                          "flows", {}, sends=("GET /stats/flow/3",)),))


# ── the loop's caps ───────────────────────────────────────────────────────────────────────────

def test_two_calls_at_most_and_the_second_cannot_ask_again(tw):
    snap, _s = collected_snapshot()
    port = f"port:ctl-1:{OVS3}:3"
    tw.script = [{"findings": [finding([port])], "reads": [ask("switch_flows", dpid=OVS3)]},
                 {"findings": [], "reads": [ask("switch_flows", dpid=OVS3)]}]
    r = tools(tw, snap)
    assert len(tw.sent) == 2 and tw.script == []
    assert r["state"] == "first_pass" and r["passes"] == 1 and len(r["calls"]) == 2
    assert "second pass failed: schema" in r["words"]
    assert [f["evidence"] for f in r["findings"]] == [[port]], "the first pass's answer stands"
    second = [x for x in calls.read()["rows"] if x.get("feature") == AT.FEATURE][0]
    assert second["verdict"] == "schema" and second["prompt"] == "sdn_analyse_tools.v2"


def test_the_loop_s_total_token_cap_stops_pass_two_before_it_is_sent(tw):
    snap, _s = collected_snapshot()
    port = f"port:ctl-1:{OVS3}:3"
    tw.script = [{"findings": [finding([port])], "reads": [ask("switch_flows", dpid=OVS3)]}]
    with pressed_by(PERSON):
        r = AT.ask_snapshot(NET, snap, actor=PERSON, trigger=triggers.person(PERSON),
                            send=tw.send, cap=20000)
    assert len(tw.sent) == 1 and r["ok"] and r["passes"] == 1
    assert "second pass not run: a cap is reached" in r["words"]
    assert "over its total cap of 20000" in r["words"]
    assert [x["verdict"] for x in r["reads"]] == ["run"]
    (row,) = [x for x in read_log.read()["rows"] if x["row"] == "sent"]
    assert row["left_host"] is False


# ── the final answer, checked as B1's ─────────────────────────────────────────────────────────

def test_the_final_answer_is_checked_as_b1_s_a_read_that_ran_citable(tw):
    snap, _s = collected_snapshot()
    (drop,) = flows_of(snap)["drops"]
    tw.script = [
        {"findings": [], "reads": [ask("trace", src="198.51.100.250", dst="198.51.100.20",
                                       proto="icmp")]},
        {"findings": [finding([drop["id"], "drop:made:up"], "medium", "A drop flow on OVS 3"),
                      finding(["read:1"], "low", "The trace from .250 is dropped"),
                      finding(["flow:never:held"], "critical", "A claim citing nothing held")]}]
    r = tools(tw, snap)
    assert r["ok"] and r["passes"] == 2 and r["state"] == "answered"
    assert [f["evidence"] for f in r["findings"]] == [[drop["id"]], ["read:1"]]
    assert r["dropped"] == 1 and r["removed_ids"] == 2
    kept = AN.analysis(NET, r["id"])
    assert kept["findings"] == r["findings"] and kept["technique"] == "trace_tool"
    assert AN._latest(NET)["analysis_tools"] == r["id"]
    (use,) = calls.uses()[r["call_id"]]
    assert use["use"].startswith("shown: 2 findings after 2 pass(es) and 1 read(s)")


def test_the_trace_tool_s_answer_citing_whole_lines_is_cut_to_ids_by_the_same_check(tw):
    """B4 shares B1's check (`analyst.check`): an entry cited as a whole line is its leading
    id, a read's too, and a made-up id leading a line is still dropped."""
    snap, _s = collected_snapshot()
    (drop,) = flows_of(snap)["drops"]
    tw.script = [
        {"findings": [], "reads": [ask("trace", src="198.51.100.250", dst="198.51.100.20",
                                       proto="icmp")]},
        {"findings": [finding([f"{drop['id']} table 0, priority 500, a drop"], "medium",
                              "A drop flow on OVS 3"),
                      finding(["read:1 the trace from .250"], "low", "The trace is dropped"),
                      finding(["flow:never:held and its words"], "critical",
                              "A claim citing nothing held")]}]
    r = tools(tw, snap)
    assert r["ok"] and r["state"] == "answered"
    assert [f["evidence"] for f in r["findings"]] == [[drop["id"]], ["read:1"]]
    assert [f["trimmed"] for f in r["findings"]] == [[drop["id"]], ["read:1"]]
    assert r["dropped"] == 1 and r["removed_ids"] == 1 and r["trimmed_ids"] == 3


def test_an_answer_citing_a_refused_read_falls_back_to_the_first_pass(tw):
    snap, _s = collected_snapshot()
    port = f"port:ctl-1:{OVS3}:3"
    tw.script = [{"findings": [finding([port])],
                  "reads": [ask("switch_flows", dpid=OVS3),
                            ask("switch_flows", dpid="00000000000000ff")]},
                 {"findings": [finding(["read:2"], "high", "the second read shows it")]}]
    r = tools(tw, snap)
    assert r["state"] == "first_pass" and "which Mercury refused" in r["words"]
    assert [f["evidence"] for f in r["findings"]] == [[port]]


# ── compared with B1 on the same snapshot ─────────────────────────────────────────────────────

def test_the_comparison_counts_found_missed_and_false_positives_by_the_code_s_rule(tw):
    snap, _s = collected_snapshot()
    (drop,) = flows_of(snap)["drops"]
    v4 = next(f["id"] for f in flows_of(snap)["flows"] if "ipv4_dst" in f["match"])
    assert AN.add_planted(NET, "A stale drop on OVS 3", f"drop:ctl-1:{OVS3}:*",
                          actor=PERSON)["ok"]
    tw.script = [{"findings": [finding([v4], "medium", "IPv4 traffic to .20 is unusual")]},
                 {"findings": [], "reads": [ask("switch_flows", dpid=OVS3)]},
                 {"findings": [finding([drop["id"]], "medium", "A drop flow matching nothing"),
                               finding([f"port:ctl-1:{OVS3}:3"], "high", "Port 3 is down"),
                               finding([v4], "info", "Ordinary IPv4 forwarding")]}]
    with pressed_by(PERSON):
        b1 = AN.analyse(NET, snap["id"], actor=PERSON, trigger=triggers.person(PERSON),
                        send=tw.send)
    r = tools(tw, snap)
    assert b1["ok"] and r["ok"] and len(tw.sent) == 3
    cmp = AN.view(NET)["tools"]["comparison"]
    assert cmp["snapshot_id"] == snap["id"] and cmp["planted"] == 1
    (base, tool) = cmp["rows"]
    assert (base["findings"], base["found"], base["missed"], base["false_positives"],
            base["calls"]) == (1, 0, 1, 1, 1)
    assert (tool["findings"], tool["found"], tool["missed"], tool["false_positives"],
            tool["real"], tool["notes"], tool["calls"], tool["reads"]) == \
        (3, 1, 0, 0, 1, 1, 2, 1)
    assert tool["cost_usd"] == pytest.approx(sum(
        x["cost_usd"] for x in calls.read()["rows"] if x["id"] in r["calls"]))


# ── who may ask, and what may go ──────────────────────────────────────────────────────────────

def test_only_a_person_s_press_asks_and_nothing_is_sent_otherwise(tw):
    snap, _s = collected_snapshot()
    with pressed_by(PERSON):
        bg = AT.analyse(NET, snap["id"], actor="job:x", send=tw.send,
                        trigger=triggers.background(AT.FEATURE, "x", NET, "snapshot", "s"))
        none = AT.analyse(NET, snap["id"], actor=PERSON, trigger=None, send=tw.send)
    assert bg["error"] == "trigger" and "not a background feature" in bg["detail"]
    assert none["error"] == "trigger" and tw.sent == []
    rows = [x for x in calls.read()["rows"] if x.get("feature") == AT.FEATURE]
    assert [x["verdict"] for x in rows] == ["trigger", "trigger"]


def test_the_topology_class_off_sends_nothing_and_keeps_nothing(tw, monkeypatch):
    from modules.ai import egress_classes
    snap, _s = collected_snapshot()
    monkeypatch.setattr(egress_classes, "topology_allowed",
                        lambda n: {"allowed": False, "why": "the topology class is off"})
    r = tools(tw, snap)
    assert r["error"] == "withheld" and tw.sent == [] and "every read of it" in r["detail"]
    assert "analysis_tools" not in AN._latest(NET)


def test_a_snapshot_changed_since_kept_is_refused(tw):
    import os
    snap, _s = collected_snapshot()
    path = os.path.join(AN._dir(NET), "snapshots", f"{snap['id']}.json")
    kept = json.load(open(path, encoding="utf-8"))
    kept["hosts"][0]["ipv4"] = ["198.51.100.99"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(kept, fh)
    r = tools(tw, snap)
    assert r["error"] == "snapshot" and tw.sent == []


# ── the route and the region ──────────────────────────────────────────────────────────────────

def test_the_press_draws_the_answer_its_tool_calls_and_the_comparison(tw, monkeypatch):
    import app as APP

    monkeypatch.setattr(gateway, "anthropic_adapter",
                        types.SimpleNamespace(**{**vars(gateway.anthropic_adapter),
                                                 "send": tw.send}))
    snap, _s = collected_snapshot()
    port = f"port:ctl-1:{OVS3}:3"
    c = APP.app.test_client()
    h = {"HX-Request": "true"}
    tw.script = [{"findings": [finding([port])]}]
    assert c.post("/v2/sdn/analyse/ask", data={"list": NET, "snapshot": snap["id"]},
                  headers=h).status_code == 200
    tw.script = [{"findings": [], "reads": [
                     ask("trace", src="2001:db8::10", dst="2001:db8::20", proto="icmp")]},
                 {"findings": [finding([port], "high", "Port 3 on OVS 3 is down, traced")]}]
    r = c.post("/v2/sdn/analyse/ask-tools", data={"list": NET, "snapshot": snap["id"]},
               headers=h)
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and "With the trace tool: 1 finding" in html
    assert "Tool calls" in html and "read:1 trace(" in html and "Not delivered:" in html
    assert "Without tools (B1)" in html and "Port 3 on OVS 3 is down, traced" in html
    kept = AN.view(NET)["tools"]["result"]
    assert kept["passes"] == 2 and kept["reads"][0]["args"]["dst"] == "2001:db8::20"
    assert len(tw.sent) == 3


def test_the_trace_tool_is_an_ai_control_and_the_rest_stay_usable(tw, monkeypatch):
    """PHASE8_PLAN 15.13 through the page's real route: Analyse with the trace tool carries the AI
    mark with its task, model and cap; while hosted AI cannot answer it is disabled with the
    reason in place, and Collect now and the sheet stay usable."""
    import app as APP
    from tests import ai_controls_check as AIC

    collected_snapshot()
    c = APP.app.test_client()

    def get():
        return c.get(f"/v2/sdn/flows?list={NET}").get_data(as_text=True)

    def parity(html):
        text = unescape(html)
        assert "Collect now" in text and "Download the sheet" in text
        assert "the same snapshot" in text and "3 hosts a trace can take" in text
    AIC.check_screen(monkeypatch, get, "sdn_analyse_tools", parity)


# ── the prompts built on B1's v2: an evidence item is one id (the Lab 9 sitting, 2026-11-10) ──

#: prompts/sdn_analyse_tools.v1.md and .v2.md as released (pass 1 and pass 2 on B1's v1).
RELEASED_SHA256 = {1: "c6578a1cab0fabc697add39a0da2f07e7c844c84ad3c5942d5dba4f246cb5302",
                   2: "bd63b58a93d3a75120196f22e8ba00aebb7237b43e33b0842d753069dee05b36"}


def test_the_prompts_built_on_b1_s_v2_are_its_text_with_the_reads_part_and_asked_only_when_named(tw):
    from modules.ai import prompts

    assert {("sdn_analyse_tools", 3), ("sdn_analyse_tools", 4)} <= set(prompts.available())
    assert AT.PASSES_OF[2] == (("sdn_analyse_tools", 3), ("sdn_analyse_tools", 4))
    for version, sha in RELEASED_SHA256.items():
        assert prompts.load("sdn_analyse_tools", version)["sha256"] == sha, "never edited"
    b1_was, b1_now = (prompts.load("sdn_analyse", v)["text"] for v in (1, 2))
    was = [prompts.load(*p)["text"] for p in AT.PASSES_OF[1]]
    now = [prompts.load(*p)["text"] for p in AT.PASSES_OF[2]]
    # "Same prompt otherwise": each is B1's v2 whole, then that pass's reads' part.
    assert all(t.startswith(b1_now) for t in now) and all(t.startswith(b1_was) for t in was)
    assert now[0][len(b1_now):] == was[0][len(b1_was):], "pass 1's reads' part is unchanged"
    assert "that id alone and never the read's words" in now[1]
    # The pair in use is the one built on B1's prompt in use, so both are adopted together.
    assert (AT.PROMPT_FIRST, AT.PROMPT_SECOND) == AT.PASSES_OF[AN.PROMPT[1]]
    assert AT.LOOP is AT.LOOPS[AN.PROMPT[1]]
    snap, _s = collected_snapshot()
    (drop,) = flows_of(snap)["drops"]
    tw.script = [{"findings": [], "reads": [ask("switch_flows", dpid=OVS3)]},
                 {"findings": [finding([f"{drop['id']} table 0, priority 500, a drop",
                                        "read:1 the switch's flows"], "medium",
                                       "A drop flow on OVS 3")]}]
    actor = "evaluation:v2-candidate"
    r = AT.ask_snapshot(NET, snap, actor=actor, trigger=triggers.evaluation(actor),
                        send=tw.send, prompt=2)
    rows = [x for x in calls.read()["rows"] if x.get("feature") == AT.FEATURE]
    assert [(x["prompt"], x["schema"]) for x in reversed(rows)] == [
        ("sdn_analyse_tools.v3", "sdn_analyse_tools.v2"), ("sdn_analyse_tools.v4", "sdn_analyse.v2")]
    assert [b["system"][0]["text"] for b in tw.sent] == now
    # B1's check stays in force: entries cited as whole lines, a read among them, are cut.
    assert r["ok"] and r["findings"][0]["evidence"] == [drop["id"], "read:1"]
    assert r["trimmed_ids"] == 2
    with pytest.raises(ValueError, match="no trace-tool prompts are built on sdn_analyse v9"):
        AT.loop_for(9)


# ── check this answer again: no new call (the Lab 9 sitting, 2026-11-10) ─────────────────────

def test_the_trace_tool_s_recorded_answer_is_checked_again_against_the_reads_that_ran(
        tw, monkeypatch):
    """The trace tool's final answer, recorded, read again with no new call: held to the same
    sealed snapshot AND the reads its record says ran; kept beside the first check; its found
    and missed counts and the comparison's row then come from it, and say so, on the card the
    press redraws."""
    import re

    import app as APP

    snap, _s = collected_snapshot()
    (drop,) = flows_of(snap)["drops"]
    assert AN.add_planted(NET, "A stale drop", drop["id"], actor=PERSON)["ok"]
    tw.script = [{"findings": [finding([drop["id"]], "medium", "B1 sees the drop flow")]}]
    with pressed_by(PERSON):
        b1 = AN.analyse(NET, snap["id"], actor=PERSON, trigger=triggers.person(PERSON),
                        send=tw.send)
    tw.script = [
        {"findings": [], "reads": [ask("trace", src="198.51.100.250", dst="198.51.100.20",
                                       proto="icmp")]},
        {"findings": [finding([f"{drop['id']} table 0, priority 500, a drop"], "medium",
                              "A drop flow on OVS 3"),
                      finding(["read:1"], "low", "The trace is dropped")]}]
    # As the check stood at the sitting: an entry compared whole, so the whole line kept nothing.
    with monkeypatch.context() as m:
        m.setattr(AN, "evidence_id", lambda entry: str(entry if entry is not None else "").strip())
        r = tools(tw, snap)
    assert r["ok"] and [f["finding"] for f in r["findings"]] == ["The trace is dropped"]
    assert r["dropped"] == 1 and AN.view(NET)["tools"]["missed"] == 1
    before = calls.read()["rows"]
    c = APP.app.test_client()
    page = unescape(c.get(f"/v2/sdn/flows?list={NET}").get_data(as_text=True))
    forms = re.findall(r'<form[^>]*hx-post="(/v2/sdn/analyse/recheck[^"]*)"[^>]*>(.*?)</form>',
                       page, re.S)
    assert len(forms) == 2, "one on each findings card"
    carried = [dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', body))
               for _url, body in forms]
    assert carried == [{"list": NET, "analysis": b1["id"]}, {"list": NET, "analysis": r["id"]}]
    assert "and to the reads that ran" in forms[1][1] and "Makes no AI call" in forms[1][1]
    pressed = c.post(forms[1][0], data=carried[1], headers={"HX-Request": "true"})
    html = unescape(pressed.get_data(as_text=True))
    assert pressed.status_code == 200
    assert len(tw.sent) == 3 and calls.read()["rows"] == before, "no call made, none recorded"
    kept = AN.analysis(NET, r["id"])
    again = kept["rechecked"]
    assert [f["finding"] for f in kept["findings"]] == ["The trace is dropped"], "as it was"
    assert [(f["finding"], f["evidence"]) for f in again["findings"]] == [
        ("A drop flow on OVS 3", [drop["id"]]), ("The trace is dropped", ["read:1"])]
    assert again["dropped"] == 0 and again["trimmed_ids"] == 1
    assert "rechecked" not in AN.analysis(NET, b1["id"]), "B1's analysis is not touched"
    # The card: both checks, the counts and the comparison's row from the re-check, each said.
    card = html[html.index('aria-labelledby="sdn-an-t"'):]
    assert ">With the trace tool: 1 finding</h2>" in card
    region = card[card.index('id="sdn-an-recheck-tools"'):card.index(">Tool calls</h3>")]
    assert re.search(r">Checked again <time[^>]*>[^<]*</time> by " + re.escape(again["by"])
                     + r", no new AI call: 2 findings</h3>", region)
    assert "A drop flow on OVS 3" in region and "no claim was dropped" in region
    assert "1 found · 0 missed, marked from the answer as checked again (no new AI call)" in card
    rows = {row["name"]: row for row in AN.view(NET)["tools"]["comparison"]["rows"]}
    assert rows["With the trace tool"]["rechecked"] is True and rows["With the trace tool"]["found"] == 1
    assert rows["Without tools (B1)"]["rechecked"] is False
    assert card.count("counted from the answer as checked again, no new AI call") == 1
    (use,) = [u for u in calls.uses()[r["call_id"]] if u["use"].startswith("checked again")]
    assert use["use"] == "checked again: 2 findings, 0 dropped by the check"
    final = "{}.v{}".format(*AN.SCHEMA_OF[AN.PROMPT[1]].__ai_schema__)
    assert f"the recorded answer read as {final}" in use["detail"]
