"""What each SDN switch can do, and the fallback where it cannot (Lab 9 B3, board F's capability
matrix; `modules/sdn/capability.py`; the handout: "if a vendor switch cannot support an action,
for example meters, document the limit and your fallback").

Every row is read by Mercury's real Ryu driver from REAL answers:
- **Open vSwitch**: what it says it is and its table features from the container harness's
  recording (Ryu 4.34 over Open vSwitch 3.3.9, tests/fixtures/sdn/harness/, which keeps three of
  OVS's 254 tables), and its meter features from the Lab 8 controller's capture (Ryu 4.34 over
  Open vSwitch 2.17, tests/fixtures/sdn/lab8/scan_s1.json: 200,000 meters, a DROP band);
- **the Arista** (EOS 4.17): what it says it is from the lab's capture (ryu-rest.txt), which
  recorded no meter or table features, so both are NOT READ, never "none";
- **a switch with no meters**: the Lab 8 answer with ``max_meter`` 0 (an edit, as a switch
  offering none reports it), and a switch whose controller answers 501 for both (OpenFlow 1.0).

The fallback: a rate limit on a switch whose meters are none is a drop, said in words, in HITL
and AUTO alike; on one whose meters were not read it stays (its preview reads them); a policy
that does not allow a drop leaves it to a person. AUTO's fallback drop is still refused by the
protected set (B), with nothing sent, and goes to a person.
"""
import json
import time

import pytest

from modules.sdn import capability as CAP
from modules.sdn import closed_loop as CL
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from modules.sdn.drivers.base import Connection
from modules.sdn.drivers.ryu import RyuDriver
from tests.fixtures.sdn.ryu_recorded import HARNESS, RecordedRyu
from tests.sdn_fakes import RYU_BASE, Replay, Response, Session, lab8
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"
ARISTA = 2214744208935


def _ryu(entries):
    return RyuDriver(Connection(RYU_BASE), session=Replay(entries, RYU_BASE), sleep=lambda s: None)


def _lab8_meters(edit=None):
    entries = [e for e in lab8("scan_s1.json") if e["path"] == "/stats/meterfeatures/1"]
    if edit:
        body = json.loads(entries[0]["body"])
        edit(body["1"][0])
        entries = [dict(entries[0], body=json.dumps(body))]
    return _ryu(entries).meter_features(1)


def ovs_row():
    h = RecordedRyu(HARNESS).driver()
    return CAP.summarise(3, h.switch_desc(3), _lab8_meters(), h.table_features(3))


def test_open_vswitch_offers_meters_groups_and_rewrite_from_its_own_answers():
    row = ovs_row()
    assert row["desc"] == "Nicira, Inc. Open vSwitch 3.3.9"
    assert row["version"]["value"] == "1.3" and row["tables"]["value"] == 3
    assert row["meters"] == {"state": "yes", "value": 200000,
                             "words": "200,000 meters, DROP band, kbps and pktps"}
    assert row["groups"]["state"] == "yes" and row["set_field"]["state"] == "yes"
    assert row["fast_failover"]["state"] == "not_read"
    assert not any(w.startswith(("rate-limit", "meters")) for w in row["cannot"])


def test_the_arista_s_features_were_not_read_and_are_never_called_none():
    d = RecordedRyu().driver()
    row = CAP.summarise(ARISTA, d.switch_desc(ARISTA), d.meter_features(ARISTA),
                        d.table_features(ARISTA))
    assert row["name"] == "arista-sw1"
    assert row["desc"].startswith("Arista Networks DCS-7050Q-16")
    for col in ("version", "tables", "meters", "groups", "set_field"):
        assert row[col]["state"] == "not_read", col
        assert row[col]["words"].startswith("not read"), col
    assert row["cannot"][0].startswith("meters not read: a rate limit reads them at its preview")


def test_a_switch_reporting_no_meter_has_none_and_the_fallback_said():
    h = RecordedRyu(HARNESS).driver()
    row = CAP.summarise(3, h.switch_desc(3), _lab8_meters(lambda f: f.update(max_meter=0)),
                        h.table_features(3))
    assert row["meters"] == {"state": "none", "value": 0, "words": "none: it reports no meter"}
    assert row["cannot"][0].startswith("rate-limit → drop: a rate limit needs a meter")


def test_a_controller_answering_501_reads_openflow_1_0_with_no_meters():
    drv = RyuDriver(Connection(RYU_BASE), sleep=lambda s: None, session=Session(
        Response(501, "", "text/html"), Response(501, "", "text/html")))
    row = CAP.summarise(5, {"ok": False, "error": "not asked"}, drv.meter_features(5),
                        drv.table_features(5))
    assert row["version"]["value"] == "1.0" and row["meters"]["state"] == "none"
    assert row["meters"]["words"] == "none: its OpenFlow version has no meters"
    assert row["tables"]["state"] == "not_read"


@pytest.mark.parametrize("state,action,fell", [("none", "drop_source", True),
                                               ("not_read", "rate_limit_source", False),
                                               ("yes", "rate_limit_source", False)])
def test_the_fallback_is_a_drop_only_where_meters_are_none(state, action, fell):
    row = {"name": "of-eos-1", "meters": {"state": state, "words": f"{state} words"}}
    got = CAP.fallback("rate_limit_source", row)
    assert (got["action"], got["fell_back"]) == (action, fell)
    if fell:
        assert got["words"] == ("of-eos-1 cannot rate-limit (none words): the fallback is to drop "
                                "the source instead (the capability matrix on SDN › Responses)")
    assert CAP.fallback("remove_flow", row) == {"action": "remove_flow", "fell_back": False,
                                                "words": ""}
    assert CAP.fallback("rate_limit_source", None)["action"] == "rate_limit_source"


# ───────────────────────────────────────────────────────────────────────────── the store

def _driver_of(answers):
    """A driver factory over a session answering *answers* by path (each a callable or
    Response), the real Ryu driver reading them."""
    class S(Session):
        def request(self, method, url, **kw):
            self.sent.append((method, url))
            path = url[len(RYU_BASE):]
            got = answers.get(path)
            if got is None:
                return Response(404, "", "text/html")
            return got() if callable(got) else got
    return lambda n, c: {"ok": True, "driver": RyuDriver(Connection(RYU_BASE), session=S(),
                                                         sleep=lambda s: None)}


def _no_meters_switch():
    feat = json.loads([e for e in lab8("scan_s1.json")
                       if e["path"] == "/stats/meterfeatures/1"][0]["body"])
    feat["1"][0]["max_meter"] = 0
    return {"/stats/switches": Response(200, "[1]"),
            "/stats/desc/1": Response(200, json.dumps({"1": {"dp_desc": "of-eos-1"}})),
            "/stats/meterfeatures/1": Response(200, json.dumps(feat)),
            "/stats/tablefeatures/1": Response(501, "", "text/html")}


def test_read_keeps_the_matrix_and_absent_and_unreadable_are_apart(networks,  # noqa: F811
                                                                    monkeypatch):
    assert CAP.stored(NET)["state"] == "absent"
    monkeypatch.setattr(CL, "_connections", lambda n: {
        "state": "ok", "error": "", "connections": [{"name": "lab-controller"}]})
    got = CAP.read(NET, driver=_driver_of(_no_meters_switch()), now=1_790_000_000.0)
    assert got["ok"] and got["read_at"] == time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                         time.gmtime(1_790_000_000.0))
    row = CAP.row_for(NET, "lab-controller", 1)
    assert row["name"] == "of-eos-1" and row["meters"]["state"] == "none"
    assert CAP.view(NET)["rows"][0]["connection"] == "lab-controller"
    with open(CAP._path(NET), "w", encoding="utf-8") as fh:
        fh.write("{")
    assert CAP.stored(NET)["state"] == "unreadable" and CAP.row_for(NET, "lab-controller", 1) \
        is None


def test_the_matrix_names_a_switch_as_netbox_names_it_by_its_datapath_id(networks,  # noqa: F811
                                                                         monkeypatch):
    """C3010: the switch describes itself as of-eos-1; NetBox's device with datapath id 1 is
    leaf-1, so the matrix's row is leaf-1; the stored row keeps what the switch said, and with
    NetBox naming none the row is the switch's own description."""
    from modules.sdn import known
    monkeypatch.setattr(CL, "_connections", lambda n: {
        "state": "ok", "error": "", "connections": [{"name": "lab-controller"}]})
    assert CAP.read(NET, driver=_driver_of(_no_meters_switch()), now=1_790_000_000.0)["ok"]
    monkeypatch.setattr(known, "read", lambda network: dict(known.NOT_ASKED, state="read",
                                                            names={1: "leaf-1"}))
    assert CAP.view(NET)["rows"][0]["name"] == "leaf-1"
    assert CAP.row_for(NET, "lab-controller", 1)["name"] == "of-eos-1"
    monkeypatch.setattr(known, "read", lambda network: dict(known.NOT_ASKED))
    assert CAP.view(NET)["rows"][0]["name"] == "of-eos-1"


def test_read_again_on_responses_reads_the_matrix_and_draws_it(networks,  # noqa: F811
                                                                monkeypatch):
    """Board F's matrix: absent, it says not read yet; Read again pressed reads every switch
    (the lab's capture: the Arista's columns not read, never none) and draws each row with its
    fallback words."""
    from html import unescape

    import app as A
    recorded = RecordedRyu()
    monkeypatch.setattr(CL, "_connections", lambda n: {
        "state": "ok", "error": "", "connections": [{"name": "lab9-ryu"}]})
    monkeypatch.setattr(CL, "_driver", lambda n, name: {"ok": True, "driver": recorded.driver()})
    c = A.app.test_client()
    before = unescape(c.get(f"/v2/sdn/responses?list={NET}").get_data(as_text=True))
    assert "not read yet: the loop reads it at its start, or press Read again" in before
    r = c.post("/v2/sdn/capabilities/read", data={"list": NET})
    assert r.status_code == 200 and CAP.stored(NET)["state"] == "ok"
    assert len(CAP.view(NET)["rows"]) == 5
    page = unescape(r.get_data(as_text=True))
    assert "arista-sw1" in page and "meters not read: a rate limit reads them at its preview" \
        in page
    assert ">none<" not in page.split("What each switch can do")[1].split("</section>")[0]


def test_a_large_fabric_draws_fifty_rows_those_that_cannot_first(networks):  # noqa: F811
    good = ovs_row()
    h = RecordedRyu(HARNESS).driver()
    bad = CAP.summarise(3, h.switch_desc(3), _lab8_meters(lambda f: f.update(max_meter=0)),
                        h.table_features(3))
    rows = [dict(good, dpid=n, dpid_hex=f"{n:016x}", name=f"ovs-{n:03d}") for n in range(60)]
    rows.append(dict(bad, dpid=99, dpid_hex=f"{99:016x}", name="zz-no-meters"))
    path = CAP._path(NET)
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema": CAP.SCHEMA, "read_at": "2026-11-10T00:00:00Z", "controllers": [
            {"connection": "c", "error": "", "switches": rows}]}, fh)
    got = CAP.view(NET)
    assert got["total"] == 61 and len(got["rows"]) == CAP.ROWS_DRAWN
    assert got["rows"][0]["name"] == "zz-no-meters"


def _verdict():
    return {"action": "rate_limit_source", "risk": "low", "person": False, "why": "",
            "params": {"rate": 1000, "unit": "kbps", "burst": 100, "hard_timeout": 600},
            "classification": None, "refused_call": "", "words": "AI call c1: a flood"}


def _detection():
    return {"key": "f1", "rule": "flood", "network": NET, "connection": "lab-controller",
            "dpid": 1, "dpid_hex": "0000000000000001", "source": "192.0.2.1",
            "targets": ["192.0.2.2"], "words": "a flood", "at": "2026-10-28T00:50:00Z",
            "title": "SDN flood", "subject": {"kind": "port", "value": 1}, "port": 1}


def test_capable_falls_back_to_a_drop_and_a_policy_forbidding_it_leaves_it_to_a_person(
        networks, monkeypatch):  # noqa: F811
    monkeypatch.setattr(CL, "_connections", lambda n: {
        "state": "ok", "error": "", "connections": [{"name": "lab-controller"}]})
    CAP.read(NET, driver=_driver_of(_no_meters_switch()))
    got = LP.capable(NET, _detection(), _verdict())
    assert got["action"] == "drop_source" and got["params"] == {"hard_timeout": 600}
    assert got["words"].startswith("AI call c1: a flood; of-eos-1 cannot rate-limit (none: it "
                                   "reports no meter): the fallback is to drop the source")
    monkeypatch.setattr(CL, "policy_refusal", lambda n, r, a, pol=None: "the policy says no")
    kept = LP.capable(NET, _detection(), _verdict())
    assert kept["action"] == "rate_limit_source" and kept["person"]
    assert kept["why"].endswith("but the policy says no: a person decides")


# ───────────────────────────────────────────────────────────────────────────── in the loop

@pytest.fixture
def auto_lab(networks, monkeypatch):  # noqa: F811
    """The Lab 8 fake controller (tests/test_sdn_ops_v2.py's), its switch reporting no meters,
    AUTO on for the network marked lab, and a flood whose classification proposes a rate
    limit."""
    from tests.test_sdn_modes_loop import mark_lab
    from modules.sdn import connections as C, drivers
    from tests.sdn_fakes import FakeRyu
    from tests.test_sdn_ops_v2 import BASE, captured_table

    fake = FakeRyu(BASE, flows={1: captured_table()}, features={
        "max_meter": 0, "band_types": [], "capabilities": [], "max_bands": 0, "max_color": 0})
    real = drivers.make

    def make(kind, connection, **kw):
        kw.setdefault("session", fake)
        kw.setdefault("sleep", lambda s: None)
        return real(kind, connection, **kw)

    monkeypatch.setattr(drivers, "make", make)
    monkeypatch.setattr("modules.sdn.flow_ops.COUNTER_INTERVAL", 0)
    C.save_connection(NET, {"name": "lab-controller", "kind": "ryu", "url": BASE},
                      actor="op@example.com")
    assert CAP.read(NET)["ok"]
    mark_lab(NET)
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 9 run",
               until=time.time() + 600, allowed_risk="low")
    monkeypatch.setattr(LP, "classify", lambda network, d, job, **kw: _verdict())
    return fake


def _pass():
    d = _detection()
    return LP.run_pass(NET, collect=lambda: {"network": NET, "summary": {"switches": 1},
                                             "state": "ok"},
                       observe=lambda n, c: {"ok": True, "fired": ["f1"], "resolved": [],
                                             "detections": [d]}, sleep=lambda s: None)


def test_auto_applies_the_drop_where_the_switch_cannot_meter(auto_lab):
    assert CAP.row_for(NET, "lab-controller", 1)["meters"]["state"] == "none"
    out = _pass()
    assert out["applied"] and out["applied"][0]["outcome"] == "verified", out["lines"]
    (body,) = [json.loads(b) for p, b in auto_lab.writes if p == "/stats/flowentry/add"]
    assert body["actions"] == [] and body["match"]["ipv4_src"] == "192.0.2.1"
    assert not any("meterentry" in p for p, _b in auto_lab.writes)
    said = [l["words"] for l in out["lines"] if l["step"] == "respond"]
    assert said[0].startswith("0000000000000001 cannot rate-limit (none: it reports no meter): "
                              "the fallback is to drop the source instead")


def test_the_fallback_drop_never_reaches_a_protected_flow(auto_lab, monkeypatch):
    from modules import protected as P
    from tests.test_protected import _pset

    monkeypatch.setattr(P, "for_network", lambda network: _pset())
    out = _pass()
    assert out["applied"] == [] and auto_lab.writes == []
    (row,) = LP.awaiting(NET)["rows"]
    assert row["action"] == "drop_source" and "protected class management" in row["auto_failed"]
