"""A detection that fires again while Mercury's response holds its source off is recorded as
already mitigated, never proposed (C2005; `modules/sdn/loop.py`, `holds`, `covering`,
`_judge_holds`). The Lab 8 walk's section D (2026-10-28 00:26:20 UTC) raised a second scan card
while the first scan's rate limit was in force, the rule's 60 s window still holding the
ports; in AUTO the same response would have been applied on every re-fire.

**The data.** The walk's own case: the scan from h1 found by the real collection and scan rule
over the Lab 8 run's capture (tests/fixtures/sdn/lab8/scan_s1.json), against the walk's own
records of the rate limit it applied to that scan (walk_intent_s1.json: three flows through
meter 1, hard 600 s, installed 23:05:23 UTC), each installed on the switch as captured; the
records' connection is the test's ("lab"), and each record's response carries the rule and
source `closed_loop.build_response` binds into it (the fixture cut it to the fields a
displaced flow's piece names). IPv6 and the lost, expired and AUTO cases apply a real drop
through `closed_loop.respond_to_threat` on `tests.sdn_fakes.FakeRyu` seeded with Ryu's captured
table (tests/test_sdn_reapply.py's switch, its restart the table put back and its meters
emptied). The MAC case is the walk's flood over MAC-only flows (C2002), which names no
address: its drop takes h2 from the controller's captured topology, and the re-fired flood is
held by its own key, its port.

- **Held**: a detection whose rule, switch and source (or its own key) an active response
  covers is recorded (the response store's ``mitigated`` row, a log line naming the response
  and until when), with no card, no AI call (none sent, none recorded) and, in AUTO, no apply.
- **Not held**: another source, another rule, another switch, a record naming no rule; an
  expired response (named, then answered as new); a lost one, its flow gone from the switch or
  its meter read missing by the SDN reader (named with C2018's Needs attention row and
  Re-apply…, then answered as new).
- **Once per attack in AUTO**: two passes of the same attack apply once; past the hard timeout,
  the attack still detected, the hold is released and the response applied again.
"""
import json
import time

import pytest

from modules.ai import calls
from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from modules.sdn import flow_intent as F
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.sdn_fakes import FakeRyu, lab8, with_flows
from tests.test_sdn_classify import _feature_on, world  # noqa: F401 - the fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_lab8 import _mac_only_flood, captured_topology, collect, l2_only_switch
from tests.test_sdn_lab8 import lab as lab8_net  # noqa: F401 - the fixture
from tests.test_sdn_modes_loop import mark_lab
from tests.test_sdn_reapply import NET, T, detection, drop, rate_limit, read
from tests.test_sdn_reapply import lab  # noqa: F401 - the fixture

NO_DRIVER = lambda n, c: {"ok": False, "error": "unused"}  # noqa: E731
JOB = "sdn-loop-default-test"

# ── the walk's own case (Lab 8, IPv4) ─────────────────────────────────────────────────────────

WALK = lab8("walk_intent_s1.json")["rows"]
#: The walk's rate limit: installed at 23:05:23 UTC, its hard timeout 600 s.
WALK_AT = WALK[0]["installed_at"]
WALK_OP = WALK[0]["response"]["operation"]


def walk_flows(source="192.0.2.1", dpid=1):
    """The walk's three flows as recorded; *source* and *dpid* edited for the cases that must
    not match."""
    out = []
    for r in WALK:
        flow = {k: r[k] for k in ("table_id", "priority", "cookie", "idle_timeout",
                                  "hard_timeout", "actions")}
        out.append(dict(flow, dpid=dpid, match=dict(r["match"], ipv4_src=source)))
    return out


def plant_walk(source="192.0.2.1", rule="scan", dpid=1):
    """The walk's three records, installed for the test's connection, each response with the
    rule and source its detection had (`build_response` binds them)."""
    for r, flow in zip(WALK, walk_flows(source, dpid)):
        response = dict(r["response"], detection={"rule": rule, "source": source,
                                                  "dpid_hex": f"{dpid:016x}"})
        F.record_installed(NET, connection="lab", flow=flow, actor="op@example.com",
                           response=response, at=WALK_AT)


def scan_with_walk_flows(installed=True, source="192.0.2.1", dpid=1):
    """The Lab 8 scan capture, with the walk's three flows installed on switch *dpid* (or
    nowhere: as a switch's restart left them). On s2, the run's s2 capture is read beside s1
    (unauthorised_s2.json), the switch list naming both."""
    s1 = lab8("scan_s1.json")
    if not installed:
        return s1
    walk = [FakeRyu._ryu_flow(dict(f, packet_count=0)) for f in walk_flows(source, dpid)]
    if dpid == 1:
        return with_flows(s1, 1, lambda flows: flows + walk)
    s2 = with_flows(lab8("unauthorised_s2.json"), 2, lambda flows: flows + walk)
    both = dict(s1[0], body=json.dumps([1, 2]))
    return [both] + [e for e in s1 + s2 if e["path"] != "/stats/switches"]


def walk_pass(world, at, *, installed=True, **edit):  # noqa: F811 - the fixture's value
    got = collect(scan_with_walk_flows(installed, **edit), at=at)
    return LP.run_pass(NET, collect=lambda: got, job=JOB, send=world.send, driver=NO_DRIVER,
                       now=lambda: at)


def respond_lines(out):
    return [x["words"] for x in out["lines"] if x["step"] == "respond"]


@pytest.mark.usefixtures("lab8_net")
def test_the_walk_s_scan_under_its_rate_limit_is_recorded_not_proposed_and_costs_no_ai(world):
    """Section D: the scan from h1 fires while the walk's rate limit holds h1 off (three
    minutes into its 600 s): recorded as already mitigated by that response, until its hard
    timeout; no card, no AI call although the feature is on, no request at all."""
    _feature_on()
    plant_walk()
    at = WALK_AT + 180
    out = walk_pass(world, at)
    assert out["ok"], out
    (key,) = out["fired"]
    assert out["mitigated"] == [{"key": key, "by": WALK_OP, "until": "2026-10-27T23:15:23Z",
                                 "hold": out["mitigated"][0]["hold"]}]
    assert out["proposed"] == [] and LP.awaiting(NET)["rows"] == [], "no card"
    assert world.sent == [] and calls.read()["rows"] == [], "no AI call, none recorded"
    (said,) = respond_lines(out)
    assert said.startswith(f"SDN scan from 192.0.2.1 on 0000000000000001 fired again while "
                           f"mitigated by response {WALK_OP} (rate_limit_source, operation "
                           f"{WALK_OP}) until 2026-10-27T23:15:23Z UTC: its 3 flow(s) on the "
                           "switch as this collection read it")
    assert said.endswith("not proposed: no AI call, nothing sent")
    (hold,) = LP.open_holds(NET)["rows"]
    assert (hold["key"], hold["by"], hold["action"], hold["until"]) == (
        key, WALK_OP, "rate_limit_source", "2026-10-27T23:15:23Z")
    assert hold["detection"]["source"] == "192.0.2.1"
    assert sorted(hold["cookies"]) == sorted(r["cookie_hex"] for r in WALK)


@pytest.mark.usefixtures("lab8_net")
def test_in_auto_the_held_scan_is_not_applied(world, monkeypatch):
    mark_lab(NET)
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=WALK_AT + 3600, allowed_risk="low", now=WALK_AT)
    applied = []
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: applied.append(a) or {})
    plant_walk()
    out = walk_pass(world, WALK_AT + 180)
    assert out["mitigated"] and applied == [] and out["applied"] == []


@pytest.mark.parametrize("edit,why", [
    ({"source": "192.0.2.2"}, "another source"),
    ({"rule": "flood"}, "another rule"),
    ({"dpid": 2}, "another switch"),
    ({"rule": ""}, "a record naming no rule"),
])
@pytest.mark.usefixtures("lab8_net")
def test_a_response_for_another_source_rule_or_switch_holds_nothing(world, edit, why):
    """Each response in force on its switch (on s2, its flows read there beside s1), and the
    scan from h1 on s1 is not its to hold."""
    plant_walk(**edit)
    out = walk_pass(world, WALK_AT + 180, **{k: v for k, v in edit.items() if k != "rule"})
    assert out["mitigated"] == [], why
    (resp,) = [r for r in LP.awaiting(NET)["rows"] if r["detection"]["rule"] == "scan"]
    assert resp["detection"]["source"] == "192.0.2.1" and resp["id"] in out["proposed"]
    (hold,) = [h for h in LP.holds(NET, collect(scan_with_walk_flows(
        **{k: v for k, v in edit.items() if k != "rule"}), at=WALK_AT + 180),
        WALK_AT + 180)["holds"]]
    assert hold["state"] == "active", "premise: the response is in force where it acts"
    assert LP.open_holds(NET)["rows"] == []


@pytest.mark.usefixtures("lab8_net")
def test_with_the_flow_intent_unreadable_the_scan_is_answered_as_new_saying_why(world):
    """Whether a response holds the source off cannot be known: never called mitigated."""
    plant_walk()
    with open(F._path(NET), "a", encoding="utf-8") as fh:
        fh.write("{not a record\n")
    out = walk_pass(world, WALK_AT + 180)
    assert out["mitigated"] == [] and len(out["proposed"]) == 1
    said = respond_lines(out)[0]
    assert said.startswith("SDN scan from 192.0.2.1 on 0000000000000001: whether a response "
                           "already holds it off could not be read (")
    assert said.endswith("): answered as new")


@pytest.mark.parametrize("spelled,canon", [
    ("192.0.2.1", "192.0.2.1"), (" 192.0.2.1 ", "192.0.2.1"),
    ("2001:DB8:0:0::1", "2001:db8::1"), ("2001:db8:0:0:0:0:0:1", "2001:db8::1"),
    ("00-00-00-00-00-0A", "00:00:00:00:00:0a"), ("00:00:00:00:00:0a", "00:00:00:00:00:0a"),
    ("192.0.2.0/24", ""), ("not an address", ""), (None, ""),
])
def test_a_source_is_compared_in_one_spelling(spelled, canon):
    assert LP.canon_source(spelled) == canon


@pytest.mark.usefixtures("lab8_net")
def test_once_its_hard_timeout_passed_the_scan_is_answered_as_new_naming_it(world):
    _feature_on()
    plant_walk()
    out = walk_pass(world, WALK_AT + 600, installed=False)
    assert out["mitigated"] == [] and len(out["proposed"]) == 1
    assert len(world.sent) == 1, "classified as any new detection is"
    assert respond_lines(out)[0] == (
        f"response {WALK_OP} (rate_limit_source, operation {WALK_OP}) held SDN scan from "
        "192.0.2.1 on 0000000000000001 off until 2026-10-27T23:15:23Z UTC, its hard timeout; "
        "answered as new")


@pytest.mark.usefixtures("lab8_net")
def test_a_lost_rate_limit_is_answered_as_new_naming_c2018_s_path(world):
    """Its flows gone from the switch while it has time left (a restart): not mitigated; the
    detection is proposed, and its line names the lost response and where it is put back."""
    plant_walk()
    out = walk_pass(world, WALK_AT + 180, installed=False)
    assert out["mitigated"] == [] and len(out["proposed"]) == 1
    said = respond_lines(out)[0]
    assert said.startswith(f"response {WALK_OP} (rate_limit_source, operation {WALK_OP}) would "
                           "hold SDN scan from 192.0.2.1 on 0000000000000001 off and is not in "
                           "force: 3 of its 3 flow(s) (")
    assert said.endswith("are not on the switch as this collection read it, with 7 min 0 s of "
                         "its hard timeout left; Needs attention names it and SDN › Flows "
                         "offers its Re-apply… (C2018); answered as new")


# ── IPv6, lost and the meter, on a switch the real code wrote ─────────────────────────────────

def a_pass(at, d, *, fired=True):
    """One pass on the fake switch: the real collection, a detection *d* the observe planted
    (*fired* first seen in this pass, else still active); the classify step is the test's."""
    seen = {"ok": True, "fired": [d["key"]] if fired else [], "resolved": [],
            "detections": [d], "kept": {}}
    return LP.run_pass(NET, collect=lambda: CL.collect_threat_data(NET, 2.0,
                                                                   sleep=lambda s: None),
                       observe=lambda n, c: seen, job=JOB, now=lambda: at,
                       sleep=lambda s: None)


def planted_classify(monkeypatch):
    """The classify step answering every detection as the catalogue's drop of its source, a
    classification that passed: so AUTO may act. Each call is kept."""
    asked = []

    def classify(network, d, job, *, send=None, pack=None, clock=None):
        asked.append(d["key"])
        return {"action": "drop_source", "risk": "low", "params": {"source": d["source"]},
                "classification": {"threat_type": "port_scan", "severity": "high"},
                "person": False, "why": "", "refused_call": "",
                "words": "planted: a port_scan threat; proposed drop_source"}
    monkeypatch.setattr(LP, "classify", classify)
    return asked


@pytest.mark.parametrize("source,seen_as", [("2001:db8::1", "2001:DB8:0:0::1"),
                                            ("192.0.2.1", "192.0.2.1")])
def test_a_source_held_off_is_held_whatever_its_key_or_spelling(
        lab, monkeypatch, source, seen_as):  # noqa: F811 - the fixture
    """A drop a person confirmed on its card: a later detection of the same rule on the same
    switch naming the same source (in another spelling, with another key) is held by that
    response, named by the card's id."""
    asked = planted_classify(monkeypatch)
    card = LP.propose(NET, detection(source), "drop_source", "low", why="a person decides",
                      now=T)
    done = drop(source)
    LP.resolve(NET, card["id"], "confirmed", actor="op@example.com", operation=done["id"],
               now=T)
    again = dict(detection(seen_as), key="another-key")
    out = a_pass(T + 60, again)
    (m,) = out["mitigated"]
    assert (m["by"], m["until"]) == (card["id"], F._iso(T + 600))
    assert asked == [] and LP.awaiting(NET)["rows"] == []
    assert f"until {F._iso(T + 600)} UTC: its 1 flow(s) on the switch" in respond_lines(out)[0]


def test_an_ipv6_drop_lost_in_a_restart_is_answered_as_new_and_its_row_is_up(lab):  # noqa: F811
    from modules import attention as A
    done = drop("2001:db8::1")
    lab.restart()
    out = a_pass(T + 60, detection("2001:db8::1"))
    assert out["mitigated"] == [] and len(out["proposed"]) == 1
    assert respond_lines(out)[0].startswith(f"response {done['id']} (drop_source, operation "
                                            f"{done['id']}) would hold SDN scan from "
                                            "2001:db8::1 on")
    (row,) = A.sdn_mitigation_source(found=read(T + 60), now=T + 60)["rows"]
    assert row["operands"]["operation"] == done["id"], "C2018's row is up beside the card"


def test_a_rate_limit_whose_meter_the_reader_reads_missing_holds_nothing(lab):  # noqa: F811
    """The collection reads flows, not meters: the SDN reader's stored value says the meter is
    gone, so the rate limit is not in force although its flows are there."""
    done, _flows = rate_limit()
    lab.meter[1] = {}
    read(T + 30)
    out = a_pass(T + 60, detection())
    assert out["mitigated"] == [] and len(out["proposed"]) == 1
    assert "is not in force: its meter 5 is missing from the switch as the SDN reader read " \
           "it at" in respond_lines(out)[0]


def test_a_rate_limit_whose_meter_the_reader_reads_installed_holds(lab):  # noqa: F811
    done, _flows = rate_limit()
    read(T + 30)
    out = a_pass(T + 60, detection())
    (m,) = out["mitigated"]
    assert m["by"] == done["id"] and LP.awaiting(NET)["rows"] == []


# ── once per attack in AUTO ───────────────────────────────────────────────────────────────────

def test_auto_applies_once_across_two_passes_and_again_once_the_hold_ends(
        lab, monkeypatch):  # noqa: F811 - the fixture
    """Pass 1: the scan fires, is classified and dropped. Pass 2: it fires again (its window
    still held the ports): held, no call, no write. Pass 3, past the drop's hard timeout, the
    scan still detected: the hold is released, said, and the scan answered as new."""
    mark_lab(NET)
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=T + 3600, allowed_risk="low", now=T)
    asked = planted_classify(monkeypatch)
    d = detection()
    first = a_pass(T, d)
    assert [a["outcome"] for a in first["applied"]] == ["verified"] and asked == [d["key"]]
    writes = len(lab.writes)
    second = a_pass(T + 30, d)
    assert second["applied"] == [] and len(second["mitigated"]) == 1
    assert asked == [d["key"]] and len(lab.writes) == writes, "no call, nothing sent"
    # Its hard timeout passes: the switch removes the drop, as asked (the fake does not).
    dropped = {r["cookie"] for r in F.intent(NET)["flows"]}
    lab.table[1] = [f for f in lab.table[1] if f["cookie"] not in dropped]
    third = a_pass(T + 601, d, fired=False)
    assert third["released"] == [d["key"]] and asked == [d["key"], d["key"]]
    assert [a["outcome"] for a in third["applied"]] == ["verified"], third["lines"]
    assert respond_lines(third)[0].startswith(
        "SDN scan from 192.0.2.1 on 0000000000000001 is still detected, and response "
        f"{first['applied'][0]['id']} no longer holds it off (its hard timeout ended at "
        f"{F._iso(T + 600)}): hold ")
    assert LP.open_holds(NET)["rows"] == []


def test_a_held_detection_that_resolves_releases_its_hold(lab, monkeypatch):  # noqa: F811
    planted_classify(monkeypatch)
    drop()
    d = detection()
    a_pass(T + 30, d)
    assert len(LP.open_holds(NET)["rows"]) == 1
    seen = {"ok": True, "fired": [], "resolved": [d["key"]], "detections": [], "kept": {}}
    LP.run_pass(NET, collect=lambda: CL.collect_threat_data(NET, 2.0, sleep=lambda s: None),
                observe=lambda n, c: seen, job=JOB, now=lambda: T + 60)
    assert LP.open_holds(NET)["rows"] == []
    rows = [json.loads(x) for x in open(LP._path(NET, LP.PENDING_FILE), encoding="utf-8")]
    assert rows[-1]["kind"] == "released" and rows[-1]["why"] == "its detection resolved"


# ── a flood naming no address (MAC-only flows, C2002) ─────────────────────────────────────────

def flood_on(port):
    """The walk's MAC-only flood on *port* (`_mac_only_flood`), titled and keyed as the flood
    rule writes one (`detect.detection_key`, its subject the port)."""
    return dict(_mac_only_flood(port), title="SDN flood", key=D.detection_key(
        "flood", NET, "lab", "0000000000000001", ["port", port]))


def collection_of(fake, at):
    """The collection's shape for s1 from the fake's flow table (its ports not read)."""
    drv = fake.driver(NET, "lab")["driver"]
    sw = CL._switch(1, (drv.flows(1), {"ok": False, "error": "not read"}, None),
                    ({"ok": False, "error": "not read"}, None), 2.0, connection="lab")
    return {"network": NET, "collected_at": F._iso(at), "state": "partial", "error": "",
            "summary": {"switches": 1}, "controllers": [
                {"connection": "lab", "state": "partial", "error": "", "switches": [sw]}]}


@pytest.mark.parametrize("port,held", [(2, True), (1, False)])
@pytest.mark.usefixtures("lab8_net")
def test_a_flood_over_mac_only_flows_is_held_by_its_own_port(monkeypatch, port, held):
    asked = planted_classify(monkeypatch)
    fake, _table = l2_only_switch(captured_topology())
    d = flood_on(2)
    preview = CL.respond_to_threat(NET, d, "drop_source", driver=fake.driver)
    assert preview["ok"], preview["error"]
    at = time.time()
    done = CL.respond_to_threat(NET, d, "drop_source", confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        actor_verified="access", driver=fake.driver, sleep=lambda s: None, now=lambda: at)
    assert done["outcome"] == "verified", done["error"]
    again = flood_on(port)
    assert again["source"] is None, "premise: it names no address"
    seen = {"ok": True, "fired": [again["key"]], "resolved": [], "detections": [again],
            "kept": {}}
    got = collection_of(fake, at + 30)
    out = LP.run_pass(NET, collect=lambda: got, observe=lambda n, c: seen, job=JOB,
                      driver=fake.driver, now=lambda: at + 30)
    assert bool(out["mitigated"]) is held
    assert (asked == []) is held and bool(out["proposed"]) is not held
    if held:
        assert "SDN flood on port 2 on 0000000000000001 fired again while mitigated by " \
               f"response {done['id']}" in respond_lines(out)[0]
