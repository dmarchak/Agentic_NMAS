"""SDN's operations on v2 (routes/sdn_v2.py; PHASE8_PLAN 17.1 S8 to S10 and S16, boards
SdnResponse, SdnResponses and SdnFlowEdit): through the real app, the real connection, the
real Ryu driver and `tests.sdn_fakes.FakeRyu` seeded with Ryu's captured flow table.

- **Flows' editor**: the form opens in place; its preview draws the exact requests and the hash
  and the hidden ask the confirm carries back; the confirm (a verified person) applies, verifies
  and records; a moved hash sends nothing; a prerequisite is refused naming the field.
- **Responses**: a response awaiting a person is drawn with who chose its action (the
  catalogue's default, with no AI classification; tests/test_sdn_classify.py has the AI's); its
  preview is the plan's card; its confirm applies and closes it as confirmed; a dismissal needs
  its reason.
- **The mode and the loop**: AUTO on with a reason and an expiry, off at once; the loop started
  and stopped, each recorded.
"""
import json
import re
from html import unescape

import pytest

from modules.sdn import connections as C
from modules.sdn import flow_intent as F
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.sdn_fakes import FakeRyu
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_flow_ops import captured_table

BASE = "http://192.0.2.10:8080"


@pytest.fixture
def lab(networks, monkeypatch):  # noqa: F811 - the fixture, used
    from modules.sdn import drivers

    fake = FakeRyu(BASE, flows={1: captured_table()})
    real = drivers.make

    def make(kind, connection, **kw):
        kw.setdefault("session", fake)
        kw.setdefault("sleep", lambda s: None)
        return real(kind, connection, **kw)

    monkeypatch.setattr(drivers, "make", make)
    monkeypatch.setattr("modules.sdn.flow_ops.COUNTER_INTERVAL", 0)
    C.save_connection("Default", {"name": "lab-controller", "kind": "ryu", "url": BASE},
                      actor="op@example.com")
    import app as A
    return {"client": A.app.test_client(), "fake": fake}


def form_fields(html):
    return {m.group(1): unescape(m.group(2)) for m in
            re.finditer(r'<input type="hidden" name="([a-z]+)" value="([^"]*)"', html)}


def test_the_editor_opens_in_place_and_its_preview_binds_the_requests(lab):
    c = lab["client"]
    html = c.get("/v2/sdn/flow/form?do=add&connection=lab-controller&dpid=0000000000000001"
                 "&list=Default").get_data(as_text=True)
    assert 'hx-post="/v2/sdn/flow/preview' in html and "Add a flow" in html
    r = c.post("/v2/sdn/flow/preview", data={
        "list": "Default", "do": "add", "connection": "lab-controller",
        "dpid": "0000000000000001", "priority": "250", "hard_timeout": "60",
        "match": "eth_type=0x0800, ipv4_src=198.51.100.9", "actions": "drop"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html
    assert "POST /stats/flowentry/add" in html and "Send 1 request to lab-controller" in html
    fields = form_fields(html)
    assert set(fields) >= {"list", "ask", "hash"} and len(fields["hash"]) == 64
    assert lab["fake"].writes == []
    r = c.post("/v2/sdn/flow/confirm", data=fields)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Done, verified" in html, html
    assert "testing traffic from the hosts is the operator" in html
    (rec,) = F.intent("Default", "lab-controller")["flows"]
    assert rec["match"]["ipv4_src"] == "198.51.100.9" and rec["actor"] == "test-person@example.invalid"


def test_a_moved_hash_sends_nothing(lab):
    c = lab["client"]
    html = c.post("/v2/sdn/flow/preview", data={
        "list": "Default", "do": "add", "connection": "lab-controller", "dpid": "0000000000000001",
        "priority": "250", "match": "in_port=3", "actions": "drop"}).get_data(as_text=True)
    fields = form_fields(html)
    fields["hash"] = "f" * 64
    r = c.post("/v2/sdn/flow/confirm", data=fields)
    assert r.status_code == 409 and "Nothing was sent" in r.get_data(as_text=True)
    assert lab["fake"].writes == []


def test_a_prerequisite_is_refused_naming_the_field(lab):
    r = lab["client"].post("/v2/sdn/flow/preview", data={
        "list": "Default", "do": "add", "connection": "lab-controller", "dpid": "0000000000000001",
        "priority": "200", "match": "in_port=1, eth_type=0x0800, tcp_dst=22", "actions": "drop"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 409 and "tcp_dst needs ip_proto 6" in html


def test_a_response_awaiting_a_person_previews_confirms_and_closes(lab):
    d = {"key": "k1", "rule": "scan", "title": "SDN scan", "network": "Default",
         "connection": "lab-controller", "dpid": 1, "dpid_hex": "0000000000000001",
         "source": "192.0.2.1", "targets": ["192.0.2.2"], "confidence": "high",
         "words": "192.0.2.1 reached 25 distinct destination ports"}
    row = LP.propose("Default", d, "drop_source", "low", why="HITL")
    c = lab["client"]
    html = unescape(c.get("/v2/sdn/responses?list=Default").get_data(as_text=True))
    assert "1 awaiting approval" in html
    assert "the catalogue's default for the rule, chosen in code (no AI classification)" in html
    assert "Preview the drop traffic from the source…" in html
    r = c.post(f"/v2/sdn/response/{row['id']}/preview", data={"list": "Default"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html
    fields = form_fields(html)
    ask = json.loads(fields["ask"])
    assert ask["response"] is True and ask["changes"][0]["flow"]["hard_timeout"] == 600
    r = c.post("/v2/sdn/response/confirm", data=fields)
    assert "Done, verified" in r.get_data(as_text=True)
    assert LP.awaiting("Default")["rows"] == []
    (op,) = F.operations("Default")["rows"]
    assert op["response"]["action"] == "drop_source" and op["mode"] == "hitl"


def test_a_dismissal_needs_its_reason(lab):
    row = LP.propose("Default", {"key": "k2", "rule": "flood"}, "rate_limit_source", "low",
                     why="HITL")
    c = lab["client"]
    r = c.post(f"/v2/sdn/response/{row['id']}/dismiss", data={"list": "Default", "reason": ""})
    assert r.status_code == 409 and "names its reason" in r.get_data(as_text=True)
    r = c.post(f"/v2/sdn/response/{row['id']}/dismiss",
               data={"list": "Default", "reason": "a known test"})
    assert r.status_code == 200 and LP.awaiting("Default")["rows"] == []


def test_auto_on_and_off_and_the_loop_started_and_stopped(lab, monkeypatch):
    c = lab["client"]
    r = c.post("/v2/sdn/mode", data={"list": "Default", "mode": "auto", "reason": "",
                                     "hours": "1", "risk": "low"})
    assert r.status_code == 409 and "recorded reason" in r.get_data(as_text=True)
    r = c.post("/v2/sdn/mode", data={"list": "Default", "mode": "auto",
                                     "reason": "lab 8 run", "hours": "1", "risk": "low"})
    assert r.status_code == 200 and MD.current("Default")["mode"] == "auto"
    assert "AUTO until" in unescape(r.get_data(as_text=True))
    r = c.post("/v2/sdn/mode", data={"list": "Default", "mode": "hitl"})
    assert r.status_code == 200 and MD.current("Default")["mode"] == "hitl"
    import threading
    gate = threading.Event()
    monkeypatch.setattr(LP, "run_pass", lambda network, **kw: gate.wait(5))
    r = c.post("/v2/sdn/loop", data={"list": "Default", "run": "start", "interval": "10"})
    assert r.status_code == 200 and LP.status("Default")["running"]
    r = c.post("/v2/sdn/loop", data={"list": "Default", "run": "stop"})
    gate.set()
    LP._jobs["Default"]["thread"].join(10)
    assert r.status_code == 200 and not LP.status("Default")["running"]
