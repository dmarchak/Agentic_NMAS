"""`respond_to_threat` (`modules/sdn/closed_loop.py`; PHASE8_PLAN 17.1 S8): a detection answered
by a catalogue action through the flow-operation core.

**The data.** Each detection is made by the real rules (`modules/sdn/detect.py`) over a
collection made by the real `collect_threat_data` from Ryu's captured answers, with
tests/test_sdn_detect.py's minimal edits (a scan: the captured L4 flow copied per destination
port, IPv4 and IPv6; a flood: port 1's received packets raised after five baseline
collections). The switch the response acts on is `tests.sdn_fakes.FakeRyu`, seeded with the same
flows. The lab's own run of each threat on Open vSwitch is tests/test_sdn_lab8.py's.

- **drop_source**: one flow dropping the source (IPv4 or IPv6), above every flow not Mercury's,
  with the network's hard timeout; applied, verified and recorded with the detection it answers;
- **rate_limit_source**: one meter with a single drop band (an id no flow points at), then the
  source's flow to each destination the evidence saw, its forwarding read from the controller's
  own flow, through the meter;
- **remove_flow**: the unauthorised flow the detection names, by delete-strict, and Mercury's
  recorded flow put back where it displaced it;
- **refusals** before any request: an action not in the catalogue, one for another rule, a
  source not in the evidence, a timeout past the ceiling, a flow no longer in the table.
"""
import json

import pytest

from modules.sdn import closed_loop as CL
from modules.sdn import connections as C
from modules.sdn import detect as D
from modules.sdn import flow_intent as F
from modules.sdn.drivers.ryu import flow_from_ryu
from tests.sdn_fakes import FakeRyu
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_detect import (BASE, T0, V6_L4, VALUES, baseline_runs, collect, observe,
                                   rx, save, scan_flows, without)


@pytest.fixture
def lab(networks):  # noqa: F811 - the fixture, used
    save()
    return networks


def switch_with(ryu_flows):
    """A FakeRyu holding *ryu_flows* (Ryu's answer's entries) on switch 1, and its driver."""
    fake = FakeRyu(BASE, flows={1: [flow_from_ryu(1, e).as_dict() for e in ryu_flows]})

    def driver(network, name):
        return C.driver_for(network, name, session=fake, sleep=lambda s: None)

    fake.driver = driver
    return fake


def scan_detection(flows):
    (d,) = D.scan(collect(T0, flows=flows), VALUES)["detections"]
    return d


def confirm(fake, preview, **kw):
    return CL.respond_to_threat("Default", None, preview["action"], confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        actor_verified="access", driver=fake.driver, sleep=lambda s: None, **kw)


@pytest.mark.usefixtures("lab")
@pytest.mark.parametrize("src,eth,field", [(None, 0x0800, "ipv4_src"),
                                           (V6_L4, 0x86DD, "ipv6_src")])
def test_a_scan_is_answered_by_a_drop_of_its_source(src, eth, field):
    flows = scan_flows(25) if src is None else scan_flows(25, src)
    d = scan_detection(flows)
    fake = switch_with(flows)
    preview = CL.respond_to_threat("Default", d, driver=fake.driver)
    assert preview["ok"], preview["error"]
    assert (preview["action"], preview["risk"]) == ("drop_source", "low")
    (step,) = preview["plan"]["steps"]
    body = json.loads(step["request"]["body"])
    assert body["match"] == {"eth_type": eth, field: d["source"]} and body["actions"] == []
    # Above every flow not Mercury's: the capture's highest is 100.
    assert body["priority"] == 300 and body["hard_timeout"] == 600
    assert fake.writes == []
    done = confirm(fake, preview)
    assert done["outcome"] == "verified"
    (op,) = F.operations("Default")["rows"]
    assert op["response"]["action"] == "drop_source"
    assert op["response"]["detection"]["key"] == d["key"]
    assert op["response"]["classified_by"] == "the catalogue's default (no AI: C1843)"


@pytest.mark.usefixtures("lab")
def test_a_flood_is_answered_by_one_meter_and_the_source_s_flows_through_it():
    kw = {"flows": without("v6")}
    baseline_runs(5, **kw)
    observe(T0 + 50, second=rx(10000), **kw)
    observe(T0 + 70, second=rx(10000), **kw)
    out = observe(T0 + 80, second=rx(10000), **kw)
    (d,) = [x for x in out["detections"] if x["rule"] == "flood"]
    fake = switch_with(without("v6"))
    preview = CL.respond_to_threat("Default", d, driver=fake.driver)
    assert preview["ok"], preview["error"]
    meter, *flows = preview["plan"]["steps"]
    body = json.loads(meter["request"]["body"])
    # The captured flow at priority 90 points at METER:1, so the meter takes 2.
    assert body["meter_id"] == 2 and body["bands"] == [{"burst_size": 100, "rate": 1000,
                                                        "type": "DROP"}]
    assert body["flags"] == ["KBPS", "STATS", "BURST"]
    assert flows, "one flow per destination whose forwarding is in the table"
    for s in flows:
        b = json.loads(s["request"]["body"])
        assert b["match"]["ipv4_src"] == d["source"]
        assert b["actions"][0] == {"meter_id": 2, "type": "METER"}
        assert b["actions"][1]["type"] == "OUTPUT"
    assert confirm(fake, preview)["outcome"] == "verified"
    (m,) = F.meters("Default")["meters"]
    assert m["meter_id"] == 2 and m["expires_at"] is not None


@pytest.mark.usefixtures("lab")
def test_an_unauthorised_flow_is_removed_and_mercury_s_put_back():
    flows = scan_flows(0)
    collected = collect(T0, flows=flows)
    dets = D.unauthorised(collected, F.intent("Default"))["detections"]
    d = next(x for x in dets if x["measurement"]["cookie"] == "0x4d45524300000001")
    fake = switch_with(flows)
    # Mercury's own recorded drop at the same place, displaced (not installed).
    hit = next(f for f in fake.table[1] if f["cookie"] == 0x4d45524300000001)
    mine = dict({k: hit[k] for k in ("table_id", "priority", "match", "actions")},
                cookie=F.mercury_cookie(77), hard_timeout=0, idle_timeout=0, dpid=1)
    F.record_installed("Default", connection="ctl-1", flow=mine, actor="op@example.com",
                       response={"id": "r-0"})
    preview = CL.respond_to_threat("Default", d, driver=fake.driver)
    assert preview["ok"], preview["error"]
    assert (preview["action"], preview["risk"]) == ("remove_flow", "medium")
    paths = [s["request"]["path"] for s in preview["plan"]["steps"]]
    assert paths == ["/stats/flowentry/delete_strict", "/stats/flowentry/add"]
    assert json.loads(preview["plan"]["steps"][1]["request"]["body"])["cookie"] == \
        F.mercury_cookie(77)
    done = confirm(fake, preview)
    assert done["outcome"] == "verified", done["error"]
    cookies = {f["cookie"] for f in fake.table[1]}
    assert 0x4d45524300000001 not in cookies and F.mercury_cookie(77) in cookies


@pytest.mark.usefixtures("lab")
@pytest.mark.parametrize("action,params,words", [
    ("shutdown_port", {}, "'shutdown_port' is not in the response catalogue"),
    ("remove_flow", {}, "remove_flow answers unauthorised_flow, not scan"),
    ("drop_source", {"source": "198.51.100.1"}, "the source 198.51.100.1 is not one the "
                                                "evidence saw (192.0.2.1)"),
    ("drop_source", {"hard_timeout": 7200}, "a response lasts from 1 to 3600 s"),
])
def test_a_response_is_refused_before_any_request(action, params, words):
    flows = scan_flows(25)
    d = scan_detection(flows)
    fake = switch_with(flows)
    got = CL.respond_to_threat("Default", d, action, params, driver=fake.driver)
    assert not got["ok"] and words in got["error"], got["error"]
    assert fake.writes == []


@pytest.mark.usefixtures("lab")
def test_a_flow_gone_before_the_response_is_said():
    flows = scan_flows(0)
    dets = D.unauthorised(collect(T0, flows=flows), F.intent("Default"))["detections"]
    fake = switch_with([f for f in flows if f["cookie"] != 0x4d45524300000001])
    d = next(x for x in dets if x["measurement"]["cookie"] == "0x4d45524300000001")
    got = CL.respond_to_threat("Default", d, driver=fake.driver)
    assert not got["ok"] and "is no longer in switch 1's table: nothing to remove" in got["error"]
