"""A lost mitigation is noticed and put back by a person (C2018): `modules/sdn/reapply.py`,
`attention.sdn_mitigation_source`, Re-apply… on SDN › Flows (`routes/sdn_v2.py`).

**The data.** Default's `lab-controller` is answered by `tests.sdn_fakes.FakeRyu` seeded with
Ryu 4.34's captured flow table, its port counters and description answered from the same
capture (rest_with_peer.json). A response is applied through the real code: a scan answered by
`closed_loop.respond_to_threat`'s drop of its source (IPv4 and IPv6), or a rate-limit's meter
and its two flows through `flow_ops.apply` with the response record `respond_to_threat` passes.
A switch's restart is the fake's table put back to the capture and its meters emptied. The
SDN reader then reads it (`readers/sdn_controllers.read`, stored as the scheduler stores it).

- **The row:** one WARNING row per response with a flow or meter missing while its hard
  timeout has time left, naming the network, the switch (its DPID and the name it reports),
  the response, what is missing and the time left, its action the switch on SDN › Flows, and
  clearing at the hard timeout; none when installed, none when expired (judged by the reader,
  or at the moment the row is asked), none for a flow a person added (not a response);
- **the preview:** exactly the missing flows (and the meter), each as recorded, its hard
  timeout the record's time left less the confirm window; refused when nothing is missing or
  the time left is inside the window; writes nothing;
- **the confirm:** applied, verified, recorded as a re-apply of the response, the records
  unchanged and the row gone at the next read; refused, sending nothing, for a preview older
  than the window or an ask that is not the response's;
- **through the app:** Flows draws Re-apply… on the switch, the preview and the confirm answer
  in place, and the loop's log says it.
"""
import json
import re
import time
from html import unescape

import pytest

from modules import attention as A
from modules.sdn import closed_loop as CL
from modules.sdn import connections as C
from modules.sdn import flow_intent as F
from modules.sdn import flow_ops as FO
from modules.sdn import reapply as RA
from tests.sdn_fakes import FakeRyu, captured
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_flow_ops import captured_table
from tests.test_sdn_v2 import WITH_PEER, store_read

BASE = "http://192.0.2.10:8080"
NET = "Default"
CONN = "lab-controller"
SW = "0000000000000001"
#: When the responses are installed: a whole second, a little before the tests' "now".
T = float(int(time.time())) - 100


class Switch(FakeRyu):
    """FakeRyu, its port counters and description answered from the capture, so the SDN
    reader reads it whole."""

    def _answer(self, method, path, body):
        if method == "GET" and path in ("/stats/port/1", "/stats/desc/1"):
            return captured(next(e for e in WITH_PEER if e["path"] == path))
        return super()._answer(method, path, body)

    def restart(self):
        """The switch restarts: its flow table is the controller's own again, its meters
        gone, as Open vSwitch comes back from a restart."""
        self.table[1] = [dict(f) for f in captured_table()]
        self.meter[1] = {}


@pytest.fixture
def lab(networks, monkeypatch):  # noqa: F811 - the fixture, used
    from modules.sdn import drivers

    fake = Switch(BASE, flows={1: captured_table()})
    real = drivers.make

    def make(kind, connection, **kw):
        kw.setdefault("session", fake)
        kw.setdefault("sleep", lambda s: None)
        return real(kind, connection, **kw)

    monkeypatch.setattr(drivers, "make", make)
    monkeypatch.setattr("modules.sdn.flow_ops.COUNTER_INTERVAL", 0)
    C.save_connection(NET, {"name": CONN, "kind": "ryu", "url": BASE}, actor="op@example.com")
    return fake


def detection(source="192.0.2.1"):
    return {"key": f"k-{source}", "rule": "scan", "title": "SDN scan", "network": NET,
            "connection": CONN, "dpid": 1, "dpid_hex": SW, "source": source,
            "targets": ["192.0.2.2"], "confidence": "high",
            "words": f"{source} reached 25 distinct destination ports", "at": "2026-10-28T00:50:00Z"}


def drop(source="192.0.2.1", at=None):
    """A scan from *source* answered by a drop of it, applied at *at* (T by default): its
    operation's answer. A test that then reads the real clock (a route) passes its own time:
    T is fixed at import, and a slow run can reach T + 540, inside the confirm window."""
    preview = CL.respond_to_threat(NET, detection(source), "drop_source")
    assert preview["ok"], preview["error"]
    at = T if at is None else at
    done = CL.respond_to_threat(NET, None, "drop_source", confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        actor_verified="access", sleep=lambda s: None, now=lambda: at)
    assert done["outcome"] == "verified", done["error"]
    return done


def rate_limit():
    """A rate-limit: meter 5 and the source's flows to two hosts through it, applied at T with
    the response record `respond_to_threat` passes."""
    flows = [{"table_id": 0, "priority": 300, "cookie": F.new_cookie(), "idle_timeout": 0,
              "hard_timeout": 600, "match": {"eth_type": 0x0800, "ipv4_src": "192.0.2.1",
                                             "ipv4_dst": dst},
              "actions": [{"type": "METER", "meter_id": 5}, {"type": "OUTPUT", "port": port}]}
             for dst, port in (("192.0.2.2", 2), ("192.0.2.3", 3))]
    ask = {"connection": CONN, "dpid": 1, "response": True, "action": "rate_limit_source",
           "changes": [{"do": "add_meter", "meter": {
               "meter_id": 5, "flags": ["KBPS", "STATS", "BURST"],
               "bands": [{"type": "DROP", "rate": 1000, "burst_size": 100}]}}]
           + [{"do": "add_flow", "flow": f} for f in flows]}
    p = FO.plan(NET, ask)
    assert p["ok"], p["error"]
    done = FO.apply(NET, ask, p["hash"], actor="op@example.com", actor_verified="access",
                    response={"kind": "response", "action": "rate_limit_source", "risk": "low",
                              "detection": detection(), "classified_by": CL.DEFAULT_WORDS},
                    sleep=lambda s: None, now=lambda: T, counter_interval=0)
    assert done["outcome"] == "verified", done["error"]
    return done, flows


def read(at):
    """The SDN reader's run at *at*, stored; the source's answer for Default."""
    store_read(NET, clock=lambda: at)
    from modules import reader_job
    from modules.readers import sdn_controllers as R
    return {NET: reader_job.read_cached_for(R.READER_NAME, NET)}


def rows(at, asked=None):
    return A.sdn_mitigation_source(found=read(at), now=asked or at)["rows"]


# ───────────────────────────────────────────────────────────────────────────── the row

@pytest.mark.parametrize("source,field", [("192.0.2.1", "ipv4_src"),
                                          ("2001:db8::1", "ipv6_src")])
def test_a_lost_drop_is_a_row_naming_its_network_switch_response_and_time_left(lab, source,
                                                                                field):
    done = drop(source)
    (rec,) = F.intent(NET, CONN)["flows"]
    assert rec["match"][field] == source
    lab.restart()
    (r,) = rows(T + 100)
    assert (r["source"], r["kind"], r["level"]) == ("sdn_mitigation", "lost", "warning")
    cookie = F.cookie_hex(rec["cookie"])
    assert r["what"] == (f"Drop traffic from the source ({source}) on Default is not in force on "
                         f"switch {SW} (s1): 1 flow ({cookie}) missing, 8 min 20 s left")
    assert f"Operation {done['id']} (installed {F._iso(T)}" in r["cause"]
    assert f"until {F._iso(T + 600)}" in r["cause"] and "restarts or reboots" in r["cause"]
    assert r["operands"]["left_s"] == 500 and r["operands"]["operation"] == done["id"]
    assert r["action"]["href"] == f"/v2/sdn/flows?list=Default&q={SW}"
    assert r["action"]["label"].startswith(f"Re-apply it on Default's SDN › Flows, switch {SW}")
    assert r["clears"]["ways"] == ["resolves", "time"] and r["clears_at"] == F._iso(T + 600)


def test_installed_is_no_row(lab):
    drop()
    assert rows(T + 100) == []


def test_expired_is_no_row_whether_the_reader_or_the_row_judges_it(lab):
    drop()
    lab.restart()
    found = read(T + 100)
    assert len(A.sdn_mitigation_source(found=found, now=T + 599)["rows"]) == 1
    assert A.sdn_mitigation_source(found=found, now=T + 600)["rows"] == [], \
        "read missing, then its hard timeout passed: no row"
    assert rows(T + 600) == [], "the reader reads it expired"
    (sw,) = read(T + 600)[NET]["doc"]["last_good"]["value"]["controllers"][0]["switches"]
    assert [x["state"] for x in sw["records"]] == ["expired"]


def test_a_flow_a_person_added_is_drawn_on_flows_and_is_not_a_response_s_row(lab):
    ask = {"connection": CONN, "dpid": 1, "changes": [{"do": "add_flow", "flow": {
        "table_id": 0, "priority": 250, "cookie": F.new_cookie(), "idle_timeout": 0,
        "hard_timeout": 600, "match": {"eth_type": 0x0800, "ipv4_src": "198.51.100.9"},
        "actions": []}}]}
    p = FO.plan(NET, ask)
    assert FO.apply(NET, ask, p["hash"], actor="op@example.com", sleep=lambda s: None,
                    now=lambda: T)["outcome"] == "verified"
    lab.restart()
    found = read(T + 100)
    (sw,) = found[NET]["doc"]["last_good"]["value"]["controllers"][0]["switches"]
    assert [x["state"] for x in sw["records"]] == ["missing"]
    assert A.sdn_mitigation_source(found=found, now=T + 100)["rows"] == []


def test_a_lost_rate_limit_names_its_flows_and_its_meter(lab):
    _done, flows = rate_limit()
    lab.restart()
    (r,) = rows(T + 100)
    cookies = sorted(F.cookie_hex(f["cookie"]) for f in flows)
    assert f"2 flows ({', '.join(cookies)}) and meter 5 missing" in r["what"]
    assert r["what"].startswith("Rate-limit the source (192.0.2.1) on Default")


def test_the_source_is_read_by_the_page_and_moved_by_sdn(lab):
    assert A.sdn_mitigation_source in A.SOURCES
    assert A.SOURCE_KEYS["sdn_mitigation_source"] == ("sdn",)
    drop()
    lab.restart()
    store_read(NET, clock=lambda: T + 100)
    got = A.sdn_mitigation_source(now=T + 100)
    assert got["state"] == "read" and len(got["rows"]) == 1, got


# ───────────────────────────────────────────────────────────────────────────── the preview

def test_the_preview_puts_back_exactly_what_is_missing_for_the_time_left(lab):
    done, flows = rate_limit()
    key = done["id"]
    lost, kept = flows
    lab.table[1] = [f for f in lab.table[1] if f["cookie"] != lost["cookie"]]
    writes = list(lab.writes)
    got = RA.preview(NET, CONN, SW, key, now=T + 100)
    assert got["ok"], got["error"]
    (step,) = got["plan"]["steps"]
    body = json.loads(step["request"]["body"])
    assert step["request"]["path"] == "/stats/flowentry/add" and step["reinstall"]
    assert body["cookie"] == lost["cookie"] and body["cookie"] != kept["cookie"]
    assert body["actions"] == [{"type": "METER", "meter_id": 5}, {"type": "OUTPUT", "port": 2}]
    # 600 s recorded at T, asked at T + 100: 500 s left, less the 60 s a confirm may take.
    assert body["hard_timeout"] == 500 - RA.CONFIRM_WINDOW_S == 440
    assert body["priority"] == lost["priority"] and body["idle_timeout"] == 0
    assert any("outlives the response's own hard timeout" in w for w in got["plan"]["will_not"])
    assert lab.writes == writes, "a preview writes nothing"
    # The meter and the flow both gone: the meter first, as recorded.
    lab.restart()
    got = RA.preview(NET, CONN, SW, key, now=T + 100)
    meter, *added = got["plan"]["steps"]
    assert meter["role"] == "add_meter" and json.loads(meter["request"]["body"])["meter_id"] == 5
    assert sorted(json.loads(s["request"]["body"])["cookie"] for s in added) == sorted(
        f["cookie"] for f in flows)


def test_the_preview_is_refused_when_nothing_is_missing_or_the_time_is_up(lab):
    done = drop()
    got = RA.preview(NET, CONN, SW, done["id"], now=T + 100)
    assert not got["ok"] and f"nothing of response {done['id']} is missing" in got["error"]
    lab.restart()
    got = RA.preview(NET, CONN, SW, done["id"], now=T + 545)
    assert not got["ok"] and "within the 60 s a confirm may take" in got["error"]
    assert f"ends at {F._iso(T + 600)}, 55 s from now" in got["error"]
    got = RA.preview(NET, CONN, SW, "sdnop-no-such", now=T + 100)
    assert not got["ok"] and "no response sdnop-no-such is recorded" in got["error"]


# ───────────────────────────────────────────────────────────────────────────── the confirm

def test_the_confirm_applies_verifies_and_records_a_re_apply(lab):
    done = drop("2001:db8::1")
    (rec,) = F.intent(NET, CONN)["flows"]
    lab.restart()
    got = RA.preview(NET, CONN, SW, done["id"], now=T + 100)
    out = RA.confirm(NET, got["ask"], got["plan"]["hash"], actor="op@example.com",
                     actor_verified="access", sleep=lambda s: None, now=lambda: T + 110)
    assert out["outcome"] == "verified", out["error"]
    assert out["record"]["ok"], out["record"]
    (held,) = [f for f in lab.table[1] if f["cookie"] == rec["cookie"]]
    assert held["hard_timeout"] == 440
    op = F.operations(NET)["rows"][-1]
    assert op["response"]["kind"] == "reapply" and op["response"]["of"] == done["id"]
    assert op["response"]["action"] == "drop_source" and op["outcome"] == "verified"
    assert F.intent(NET, CONN)["flows"] == [rec], "the record stands: its expiry unchanged"
    assert rows(T + 120) == [], "read installed again: the row clears"


def test_a_confirm_later_than_the_window_or_off_the_record_sends_nothing(lab):
    done = drop()
    lab.restart()
    got = RA.preview(NET, CONN, SW, done["id"], now=T + 100)
    writes = list(lab.writes)
    late = RA.confirm(NET, got["ask"], got["plan"]["hash"], actor="op@example.com",
                      sleep=lambda s: None, now=lambda: T + 100 + RA.CONFIRM_WINDOW_S + 1)
    assert late["outcome"] == "refused"
    assert "put back for 440 s, and its record has 439 s left now" in late["error"]
    other = json.loads(json.dumps(got["ask"]))
    other["changes"][0]["reinstall"] = False
    assert "is not a reinstall" in RA.confirm(NET, other, got["plan"]["hash"],
                                              actor="op@example.com")["error"]
    other = json.loads(json.dumps(got["ask"]))
    other["changes"][0]["flow"]["cookie"] = F.new_cookie()
    assert "is not response" in RA.confirm(NET, other, got["plan"]["hash"],
                                           actor="op@example.com")["error"]
    assert lab.writes == writes


# ───────────────────────────────────────────────────────────────────────────── the app

def form_fields(html):
    return {m.group(1): unescape(m.group(2)) for m in
            re.finditer(r'<input type="hidden" name="([a-z]+)" value="([^"]*)"', html)}


def test_flows_draws_re_apply_and_its_preview_and_confirm_answer_in_place(lab):
    from modules.sdn import loop as LP

    import app as APP
    c = APP.app.test_client()
    # The route reads the real clock: the drop is 100 s before this test, never T (import).
    done = drop(at=float(int(time.time())) - 100)
    lab.restart()
    store_read(NET, clock=lambda: time.time())
    html = c.get(f"/v2/sdn/flows?list=Default&q={SW}").get_data(as_text=True)
    form = re.search(r'<form class="sdn-lost".*?</form>', html, re.S).group(0)
    assert 'hx-post="/v2/sdn/reapply/preview' in form and "Re-apply…" in form
    assert "Not in force" in form and "of its hard timeout left" in unescape(form)
    fields = form_fields(form)
    assert fields == {"list": NET, "connection": CONN, "dpid": SW, "key": done["id"]}
    r = c.post("/v2/sdn/reapply/preview", data=fields)
    card = r.get_data(as_text=True)
    assert r.status_code == 200, card
    assert "Re-apply: Drop traffic from the source (192.0.2.1)" in unescape(card)
    assert 'hx-post="/v2/sdn/reapply/confirm' in card
    r = c.post("/v2/sdn/reapply/confirm", data=form_fields(card))
    assert r.status_code == 200 and "Done, verified" in r.get_data(as_text=True)
    last = LP._read(NET, LP.LOG_FILE)["rows"][-1]
    assert last["step"] == "respond" and "re-apply of drop_source" in last["words"]
    again = c.post("/v2/sdn/reapply/preview", data=fields)
    assert again.status_code == 409 and "is missing" in unescape(again.get_data(as_text=True))
