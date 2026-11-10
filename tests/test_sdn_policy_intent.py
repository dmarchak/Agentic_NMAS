"""The intent controller (Lab 9 Objective B2, `modules/sdn/policy_intent.py`; board lab9-sdn E):
a policy in words, its names resolved in code, one recorded AI call, every check in code, the
compile to flows on the source's ingress switch, and the one flow-operation core's preview,
confirm and record.

**The data.** The Lab 9 fabric as its NetBox records hold it (tests/fixtures/nsot_export/
lab9_records.json, built by the real `export.build`), with these edits, each a record NetBox
does not hold yet: the Aristas' and the ProCurve's datapath ids (the masked ones Ryu reports in
tests/fixtures/lab9_captures/2026-11-06/ryu-rest.txt); end hosts tagged ``mercury-end-host``
on the data network 198.51.100.0/24 (h1 on ovs1 eno4 and h2 on arista-sw2 Ethernet17, the two
ports the captured links leave at the edge; web-1 and web-2 tagged ``web``, db-1 and db-2, and
h3 with no cable); and the DNS (udp 53) and DHCP (udp 67, 68) Services tagged
``mercury-protected``. The controller's topology is Ryu's captured switch list and links
(ryu-rest.txt, through the real Ryu parsers) with one learned host on h2's port. Each switch is
the real Ryu driver over `tests.sdn_fakes.FakeRyu` holding the table-miss flow Ryu's application
installs on connect (rest_with_peer.json's first flow); the OVS servers report the lab OVS's
meter features, the Aristas and the ProCurve none. The model is a fake `send` through the real
gateway.

- **The four intents** of the handout, previewed, confirmed and verified by reading the table
  back: a block for an hour on an Arista (a tag's two hosts), an allow on an OVS server (IPv4
  and IPv6), a block with a duration on OVS, a rate limit where meters exist;
- **the bad requests**: ambiguous (asked back, no call), unknown host (refused naming both
  operands, no call), impossible (a meter on a meterless switch, with its offers; a host on no
  OpenFlow port; a duration past OpenFlow's), contradictory (within one request, and against a
  committed policy), protected (DNS and DHCP covered, with a narrowing), a conflict with an
  installed flow (lifting a response's drop);
- **never trusting the model**: a malformed answer and a name the sentence did not resolve to
  are refused, and neither reaches `flow_ops` (a stand-in that fails if called).
"""
import copy
import json

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, gateway, triggers
from modules.nsot import export as X
from modules.sdn import flow_intent as F
from modules.sdn import flow_ops as O
from modules.sdn import policy_intent as P
from modules.sdn.drivers.base import Connection
from modules.sdn.drivers.ryu import RyuDriver, flow_from_ryu, host_from_ryu, link_from_ryu
from tests.ai_person import pressed_by
from tests.sdn_fakes import Clock, FakeRyu, Response, fixture
from tests.test_openflow_golden import _records, fake_netbox
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"
BASE = "http://192.0.2.10:8080"
KEY = "sk-planted-test-key-0123456789"
ACTOR = "operator@example.com"
CONN = "lab-controller"
OVS1, OVS2 = 3, 4
ARISTA1, ARISTA2 = int("00000203a90ab627", 16), int("0000029625637b84", 16)
PROCURVE = int("00c802d5027901e6", 16)
CAPTURE = "tests/fixtures/lab9_captures/2026-11-06/ryu-rest.txt"


def _ryu_capture() -> dict:
    out, key = {}, None
    with open(CAPTURE, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("### "):
                key = line[4:].strip()
            elif key and line.strip():
                out[key] = json.loads(line)
                key = None
    return out


def lab9_records() -> dict:
    """The Lab 9 records with the edits the module's docstring lists."""
    records = copy.deepcopy(_records())
    dpids = {"arista-sw1": "00000203a90ab627", "arista-sw2": "0000029625637b84",
             "procurve-sw": "00c802d5027901e6"}
    for d in records["devices"]:
        if d["name"] in dpids:
            d["custom_fields"]["openflow_datapath_id"] = dpids[d["name"]]
    site = {"id": 1, "slug": "lab"}
    hosts = [("h1", ["198.51.100.11/24", "2001:db8:c8::11/64"], ("ovs1", "eno4"), []),
             ("h2", ["198.51.100.12/24"], ("arista-sw2", "Ethernet17"), []),
             ("h3", ["198.51.100.13/24"], None, []),
             ("web-1", ["198.51.100.21/24", "2001:db8:c8::21/64"], None, ["web"]),
             ("web-2", ["198.51.100.22/24"], None, ["web"]),
             ("db-1", ["198.51.100.31/24"], None, []),
             ("db-2", ["198.51.100.32/24"], None, [])]
    for n, (name, addrs, cable, tags) in enumerate(hosts):
        dev_id, if_id = 900 + n, 9100 + n
        records["devices"].append({
            "id": dev_id, "name": name, "role": {"slug": "end-host"},
            "status": {"value": "active"}, "site": site, "custom_fields": {}, "platform": None,
            "tags": [{"slug": t, "name": t} for t in [X.HOST_TAG] + tags]})
        records["interfaces"].append({
            "id": if_id, "device": {"id": dev_id, "name": name}, "name": "eth0",
            "type": {"value": "1000base-t"}, "enabled": True, "mgmt_only": False, "mode": None,
            "untagged_vlan": None, "tagged_vlans": [], "tags": [], "custom_fields": {},
            "primary_mac_address": {"mac_address": f"02:00:00:00:00:{n + 1:02x}"}})
        for k, a in enumerate(addrs):
            records["ip_addresses"].append({"id": 9200 + 10 * n + k, "address": a,
                                            "assigned_object": {"id": if_id}})
        if cable:
            records["cables"].append({
                "a_terminations": [{"object": {"device": {"name": name}, "name": "eth0"}}],
                "b_terminations": [{"object": {"device": {"name": cable[0]}, "name": cable[1]}}],
                "status": {"value": "connected"}, "label": ""})
    tag = [{"slug": "mercury-protected", "name": "mercury-protected"}]
    records["services"] += [
        {"device": {"id": 16, "name": "controller"}, "name": "dns", "protocol": {"value": "udp"},
         "ports": [53], "ipaddresses": [], "tags": tag},
        {"device": {"id": 16, "name": "controller"}, "name": "dhcp",
         "protocol": {"value": "udp"}, "ports": [67, 68], "ipaddresses": [], "tags": tag}]
    return records


class Fabric(FakeRyu):
    """FakeRyu over Lab 9's switches, each answering its own meter features: the OVS servers
    the lab OVS's, every other switch none (Ryu answers an empty list for a switch that has
    none)."""

    def _answer(self, method, path, body):
        if method == "GET" and path.startswith("/stats/meterfeatures/"):
            dpid = int(path.rsplit("/", 1)[1])
            return Response(200, json.dumps({str(dpid): [self.features]
                                             if dpid in (OVS1, OVS2) else []}))
        return super()._answer(method, path, body)


def _table_miss() -> list:
    entry = next(e for e in fixture("rest_with_peer.json") if e["path"] == "/stats/flow/1")
    first = json.loads(entry["body"])["1"][0]
    assert first["priority"] == 0 and first["match"] == {}, first
    return [flow_from_ryu(1, first).as_dict()]


@pytest.fixture
def lab(networks, monkeypatch, tmp_path):  # noqa: F811 - the fixture
    from modules import settings_schema

    records = lab9_records()
    monkeypatch.setattr("modules.inventory.source_config.load",
                        lambda name: {"source": "netbox", "filters": {"role": "openflow-switch"}})
    get, _calls = fake_netbox(records)
    built = X.build(NET, get=get, version=lambda: records["netbox_version"])
    assert built["ok"], built["error"]
    doc = X.parse(built["bytes"])
    monkeypatch.setattr(X, "read", lambda network, rev="HEAD": {
        "ok": True, "export": doc, "sha256": doc["sha256"], "error": ""})
    cap = _ryu_capture()
    switches = cap["switches"]
    links = [link_from_ryu(e) for e in cap["links"]]
    learned = host_from_ryu({"mac": "02:00:00:00:00:40", "ipv4": ["198.51.100.40"], "ipv6": [],
                             "port": {"dpid": "0000029625637b84", "port_no": "00000011",
                                      "hw_addr": "02:90:d3:08:55:b3", "name": "Ethernet17"}})
    topo = {"state": "read", "why": "", "controllers": [{
        "name": CONN, "state": "read", "switches": [{"dpid": d} for d in switches],
        "links": links, "hosts": [learned]}]}
    monkeypatch.setattr(P, "_stored_topology", lambda network: topo)
    fake = Fabric(BASE, flows={d: _table_miss() for d in switches}, dpids=switches)

    def driver(_network, name):
        return {"ok": True, "error": "", "connection": {"name": name, "own_cookies": [0]},
                "driver": RyuDriver(Connection(BASE), session=fake, clock=Clock(),
                                    sleep=lambda s: None)}

    settings = {"ai_hosted": {"by": ACTOR, "at": "2026-11-09T05:00:00Z",
                              "reason": "the lab's proof of concept"},
                "ai_cap_usd_per_day": 1.50}
    real = settings_schema.get_setting
    monkeypatch.setattr(settings_schema, "get_setting",
                        lambda k, d=None: settings[k] if k in settings else real(k, d))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))

    class W:
        pass
    w = W()
    w.fake, w.driver, w.doc, w.sent, w.answer, w.topo = fake, driver, doc, [], None, topo

    def send(body, key):
        w.sent.append(body)
        text = w.answer if isinstance(w.answer, str) else json.dumps(w.answer)
        return A.Reply(status=200, body={"content": [{"type": "text", "text": text}],
                                         "stop_reason": "end_turn",
                                         "usage": {"input_tokens": 900, "output_tokens": 120}},
                       attempts=1, latency_s=0.3)
    w.send = send
    monkeypatch.setattr(A, "send", send)
    return w


def rule(kind, source, destination, protocol="any", port=0, rate=0, duration=0):
    return {"kind": kind, "source": source, "destination": destination, "protocol": protocol,
            "port": port, "rate_kbps": rate, "duration_s": duration}


def answer(*rules, outcome="answer", question="", why_not=""):
    return {"outcome": outcome, "question": question, "why_not": why_not, "rules": list(rules)}


def draft(lab, sentence, picks=None):
    with pressed_by(ACTOR):
        return P.draft(NET, sentence, actor=ACTOR, trigger=triggers.person(ACTOR),
                       send=lab.send, today="2026-11-09", picks=picks, driver=lab.driver)


def applied(lab, policy):
    """The policy previewed and confirmed as the person: ``(preview, done)``."""
    pv = P.preview(NET, policy, driver=lab.driver)
    assert pv["ok"], (pv["check"].get("words"), (pv["plan"] or {}).get("error"))
    done = P.confirm(NET, policy, pv["check"]["ask"], pv["plan"]["hash"], actor=ACTOR,
                     actor_verified="access", driver=lab.driver, sleep=lambda s: None)
    return pv, done


def _added(lab, dpid):
    return [json.loads(b) for path, b in lab.fake.writes if path == "/stats/flowentry/add"
            and json.loads(b)["dpid"] == dpid]


# ───────────────────────────────────────────────────────────────────────────── names, no call

class TestNamesBeforeAnyCall:
    def test_names_resolve_in_code_with_no_model(self, lab):
        got = P.screen(NET, "Block h2 from reaching the web servers on TCP 443 for an hour")
        assert got["ok"], got
        assert set(got["names"]) == {"h2", "tag:web"}
        assert got["names"]["tag:web"]["hosts"] == ["web-1", "web-2"]
        assert got["names"]["h2"]["addresses"] == ["198.51.100.12"]
        assert lab.sent == [], "resolving names asks no model"

    @pytest.mark.parametrize("address,host", [("198.51.100.11", "h1"),
                                              ("2001:db8:c8::11", "h1")])
    def test_an_address_names_its_netbox_host_ipv4_and_ipv6(self, lab, address, host):
        got = P.screen(NET, f"block {address} from web-1 on tcp 80")
        assert got["names"][address]["hosts"] == [host] and lab.sent == []

    def test_a_learned_address_is_placed_by_the_controller(self, lab):
        lab.answer = answer(rule("block", "198.51.100.40", "web-1", "tcp", 80))
        got = draft(lab, "block 198.51.100.40 from web-1 on tcp 80")
        assert got["state"] == "checked", got["words"]
        assert got["dpid"] == ARISTA2 and "the controller learned it" in got["where"]

    def test_a_quoted_netbox_name_is_put_back_and_other_quoted_text_never_is(self, lab):
        got = P.screen(NET, 'block "h2" from web-1 on tcp 80 because "cleanup Friday"')
        assert "h2" in got["names"] and "<<text_" in got["sentence"]
        assert "cleanup Friday" not in got["sentence"]

    def test_ambiguity_is_asked_back_as_buttons_with_no_call(self, lab):
        got = draft(lab, "block h1 from the db on tcp 5432")
        assert got["state"] == "asked" and got["kind"] == "ambiguous"
        assert [c["key"] for c in got["ask"]["candidates"]] == ["db-1", "db-2"]
        assert lab.sent == [] and got["call_id"] == "" and got["by"] == "mercury"
        lab.answer = answer(rule("block", "h1", "db-1", "tcp", 5432))
        again = draft(lab, "block h1 from the db on tcp 5432", picks={"db": "db-1"})
        assert again["state"] == "checked", again["words"]
        assert len(lab.sent) == 1 and "db-1" in json.dumps(lab.sent[0])

    def test_a_pick_that_was_not_offered_is_refused(self, lab):
        got = draft(lab, "block h1 from the db on tcp 5432", picks={"db": "web-1"})
        assert got["state"] == "refused" and "not one of the choices" in got["words"]
        assert lab.sent == []

    @pytest.mark.parametrize("word", ["h9", "web-7"])
    def test_an_unknown_host_is_refused_naming_both_operands_with_no_call(self, lab, word):
        got = draft(lab, f"block {word} from web-1 on tcp 80")
        assert got["state"] == "refused" and got["kind"] == "unknown"
        assert (f"NetBox holds no host {word} and the controller has not seen one. Compared: "
                "the name against 7 NetBox hosts and 1 controller-learned host") in got["words"]
        assert lab.sent == []

    def test_a_switch_s_name_is_no_unknown_host(self, lab):
        got = P.screen(NET, "block h1 from web-1 on tcp 80 at ovs1")
        assert got["ok"] and "ovs1" not in got["names"]


# ───────────────────────────────────────────────────────────────────────────── the four intents

class TestTheFourIntents:
    def test_a_block_for_an_hour_on_an_arista(self, lab):
        lab.answer = answer(rule("block", "h2", "tag:web", "tcp", 443, duration=3600))
        got = draft(lab, "Block h2 from reaching the web servers on TCP 443 for an hour")
        assert got["state"] == "checked", got["words"]
        assert got["dpid"] == ARISTA2 and "arista-sw2 (an Arista EOS switch" in \
            got["rows"][1]["words"]
        assert [r["check"] for r in got["rows"]] == [
            "Hosts named", "Where it applies", "Conflicts with installed flows",
            "Committed policies", "Protected flows"]
        _pv, done = applied(lab, got["policy"])
        assert done["outcome"] == "verified", done["error"]
        adds = _added(lab, ARISTA2)
        assert sorted(a["match"]["ipv4_dst"] for a in adds) == ["198.51.100.21", "198.51.100.22"]
        assert all(a["actions"] == [] and a["hard_timeout"] == 3600 and a["match"]["tcp_dst"] ==
                   443 for a in adds)
        assert len(lab.fake.table[ARISTA2]) == 3, "the two drops beside the table-miss"
        (pol,) = P.committed(NET)["policies"]
        assert pol["id"] == got["policy"]["id"] and len(pol["flows"]) == 2

    def test_an_allow_on_an_ovs_server_ipv4_and_ipv6(self, lab):
        lab.answer = answer(rule("allow", "h1", "web-1", "tcp", 80))
        got = draft(lab, "Allow h1 to reach web-1 on tcp 80")
        assert got["state"] == "checked" and got["dpid"] == OVS1, got["words"]
        _pv, done = applied(lab, got["policy"])
        assert done["outcome"] == "verified", done["error"]
        adds = _added(lab, OVS1)
        assert sorted(a["match"].get("ipv4_dst") or a["match"]["ipv6_dst"] for a in adds) == [
            "198.51.100.21", "2001:db8:c8::21"]
        assert all(a["actions"] == [{"type": "OUTPUT", "port": "NORMAL"}] and
                   a["hard_timeout"] == 0 for a in adds)
        rows = [r for r in F.intent(NET)["flows"] if r["dpid"] == OVS1]
        assert {r["response"]["kind"] for r in rows} == {"policy"}

    def test_a_block_with_a_duration(self, lab):
        lab.answer = answer(rule("block", "h1", "web-2", "udp", 5001, duration=600))
        got = draft(lab, "Block h1 from web-2 on udp 5001 for 10 minutes")
        _pv, done = applied(lab, got["policy"])
        assert done["outcome"] == "verified", done["error"]
        (add,) = _added(lab, OVS1)
        assert add["hard_timeout"] == 600 and add["match"]["ip_proto"] == 17

    def test_a_rate_limit_where_the_switch_reports_meters(self, lab):
        lab.answer = answer(rule("rate_limit", "h1", "web-2", rate=1000))
        got = draft(lab, "Rate-limit h1 to web-2 to 1 Mbit/s")
        assert got["state"] == "checked", got["words"]
        assert "the switch reports meters" in got["rows"][1]["words"]
        _pv, done = applied(lab, got["policy"])
        assert done["outcome"] == "verified", done["error"]
        meters = [json.loads(b) for p, b in lab.fake.writes if p == "/stats/meterentry/add"]
        assert [(m["dpid"], m["bands"][0]["rate"]) for m in meters] == [(OVS1, 1000)]
        (add,) = _added(lab, OVS1)
        assert add["actions"][0] == {"type": "METER", "meter_id": meters[0]["meter_id"]}


# ───────────────────────────────────────────────────────────────────────────── bad requests

class TestRefusedOrQuestioned:
    def test_impossible_a_meter_on_a_switch_with_none_offers_drop_and_a_meter_switch(self, lab):
        lab.answer = answer(rule("rate_limit", "h2", "web-1", rate=1000))
        got = draft(lab, "rate-limit h2 to web-1 to 1 Mbit/s")
        assert got["state"] == "refused" and got["kind"] == "impossible"
        assert "enters at arista-sw2" in got["words"] and "it reports no meters" in got["words"]
        assert "Compared: the action rate-limit against arista-sw2's meter features" in \
            got["words"]
        assert got["offers"] == [{"kind": "block"}, {"place": OVS2, "name": "ovs2"}]
        assert lab.fake.writes == []
        as_drop = P.check(NET, got["policy"], driver=lab.driver, instead={"kind": "block"})
        assert as_drop["ok"] and all(c["flow"]["actions"] == [] for c in as_drop["ask"]["changes"])
        at_ovs2 = P.check(NET, got["policy"], driver=lab.driver, instead={"place": OVS2})
        assert at_ovs2["ok"] and at_ovs2["dpid"] == OVS2
        assert at_ovs2["ask"]["changes"][0]["do"] == "add_meter"
        refused = P.check(NET, got["policy"], driver=lab.driver, instead={"place": OVS1})
        assert not refused["ok"] and "not one the refusal offered" in refused["words"]

    def test_impossible_a_host_on_no_openflow_port(self, lab):
        lab.answer = answer(rule("block", "h3", "web-1", "tcp", 80))
        got = draft(lab, "block h3 from web-1 on tcp 80")
        assert got["kind"] == "impossible"
        assert "h3 is on no OpenFlow port: h3 eth0 has no cable recorded in NetBox, and the " \
               "controller has not learned 198.51.100.13" in got["words"]

    @pytest.mark.parametrize("address", ["198.51.100.99", "2001:db8:c8::99"])
    def test_impossible_an_address_nothing_places(self, lab, address):
        lab.answer = answer(rule("block", address, "web-1", "tcp", 80))
        got = draft(lab, f"block {address} from web-1 on tcp 80")
        assert got["kind"] == "impossible" and f"{address} is on no OpenFlow port" in got["words"]

    def test_impossible_a_duration_past_openflow_s(self, lab):
        lab.answer = answer(rule("block", "h1", "web-1", "tcp", 80, duration=86400))
        got = draft(lab, "block h1 from web-1 on tcp 80 for a day")
        assert got["kind"] == "impossible" and "at most 65535 s" in got["words"]

    def test_contradictory_two_parts_of_one_request(self, lab):
        lab.answer = answer(rule("allow", "h2", "web-1", "tcp", 443),
                            rule("block", "h2", "tag:web", "tcp", 443))
        got = draft(lab, "allow h2 to web-1 on 443 and block h2 from all web servers on 443")
        assert got["state"] == "refused" and got["kind"] == "contradictory"
        assert got["words"].startswith("part 1 (allow h2 to web-1 on tcp 443) and part 2 "
                                       "(block h2 to the hosts tagged web on tcp 443): the "
                                       "block does what "
                                       "the allow undoes")
        assert "the first lies inside the second" in got["words"]
        assert lab.fake.writes == []

    def test_contradictory_against_a_committed_policy(self, lab):
        lab.answer = answer(rule("block", "h1", "web-2", "udp", 5001, duration=600))
        first = draft(lab, "Block h1 from web-2 on udp 5001 for 10 minutes")
        assert applied(lab, first["policy"])[1]["outcome"] == "verified"
        writes = list(lab.fake.writes)
        lab.answer = answer(rule("allow", "h1", "web-2", "udp", 5001))
        got = draft(lab, "allow h1 to web-2 on udp 5001")
        assert got["kind"] == "contradictory"
        assert f"contradicts the committed policy {first['policy']['id']}" in got["words"]
        assert "it would allow what that policy blocks" in got["words"]
        assert lab.fake.writes == writes

    def test_a_protected_dns_and_dhcp_flow_covered_is_refused_with_a_narrowing(self, lab):
        lab.answer = answer(rule("block", "h1", "any", "udp"))
        got = draft(lab, "block all UDP from h1")
        assert got["state"] == "refused" and got["kind"] == "protected"
        assert "it would cover the protected flows dhcp (must_reach dhcp" in got["words"]
        assert "and dns (must_reach dns" in got["words"]
        assert "Narrow it: name the protocol and port to block" in got["words"]
        assert "udp 67" in got["words"] and "udp 53 (dns)" in got["words"]
        assert lab.fake.writes == []

    def test_a_conflict_lifting_a_response_s_drop_is_refused(self, lab):
        drop = {"connection": CONN, "dpid": OVS1, "response": True, "changes": [
            {"do": "add_flow", "flow": {"table_id": 0, "priority": 300, "cookie": F.new_cookie(),
                                        "hard_timeout": 600, "actions": [],
                                        "match": {"eth_type": 0x0800, "ip_proto": 6,
                                                  "ipv4_src": "198.51.100.11",
                                                  "tcp_dst": 80}}}]}
        p = O.plan(NET, drop, driver=lab.driver)
        assert p["ok"], p["error"]
        done = O.apply(NET, drop, p["hash"], actor=ACTOR, actor_verified="access",
                       driver=lab.driver, sleep=lambda s: None)
        assert done["outcome"] == "verified", done["error"]
        lab.answer = answer(rule("allow", "h1", "web-1", "tcp", 80))
        got = draft(lab, "allow h1 to web-1 on tcp 80")
        assert got["kind"] == "conflict" and "lifts Mercury's flow" in got["words"]
        assert "so Mercury's drop is undone" in got["words"]

    def test_the_model_s_question_back_is_said_and_nothing_checked(self, lab):
        lab.answer = answer(outcome="ask", question="Should h1 reach web-1, or web-1 reach h1?")
        got = draft(lab, "only h1 and web-1 on tcp 80")
        assert got["state"] == "question" and got["words"].startswith("Should h1")
        assert calls.uses()[got["call_id"]][0]["use"] == "asked a question back"


# ───────────────────────────────────────────────────────────────────────────── never trusted

@pytest.fixture
def no_flow_ops(monkeypatch):
    """A stand-in for the flow-operation core that fails if anything reaches it."""
    def never(*a, **k):
        raise AssertionError("an unchecked policy reached flow_ops")
    monkeypatch.setattr(O, "plan", never)
    monkeypatch.setattr(O, "apply", never)


class TestTheModelIsNeverTrusted:
    @pytest.mark.parametrize("bad,said", [
        (rule("block", "h7", "web-1", "tcp", 80), "rule 1's source is 'h7', which is not among "
                                                   "the names the sentence resolved to"),
        (rule("block", "web-2", "web-1", "tcp", 80), "rule 1's source is 'web-2', which is not "
                                                      "among the names"),
        (rule("block", "h1", "web-1", "tcp", 80, rate=500), "rule 1 is a block with a rate"),
        (rule("rate_limit", "h1", "web-1"), "rule 1 is a rate limit with no rate"),
    ])
    def test_a_malformed_rule_is_refused_before_anything(self, lab, no_flow_ops, bad, said):
        lab.answer = answer(bad)
        got = draft(lab, "block h1 from web-1 on tcp 80")
        assert got["state"] == "refused" and got["kind"] == "malformed", got
        assert said in got["words"] and "nothing of the answer is used" in got["words"]
        assert calls.uses()[got["call_id"]][0]["use"] == "refused by validation"

    def test_an_answer_not_of_the_schema_is_refused_by_the_gateway(self, lab, no_flow_ops):
        lab.answer = '{"outcome": "answer", "rules": [{"kind": "redirect"}]}'
        got = draft(lab, "block h1 from web-1 on tcp 80")
        assert got["state"] == "refused" and got["kind"] == "gateway" and got["call_id"]

    def test_a_carried_policy_is_checked_again_before_the_plan(self, lab, no_flow_ops):
        carried = {"id": "pol-x", "rules": [rule("block", "h1", "any", "udp")]}
        got = P.preview(NET, carried, driver=lab.driver)
        assert not got["ok"] and got["check"]["kind"] == "protected" and got["plan"] is None
        done = P.confirm(NET, carried, {"connection": CONN, "dpid": OVS1, "changes": []}, "0" * 64,
                         actor=ACTOR, driver=lab.driver)
        assert done["outcome"] == "refused" and "protected" in done["error"]

    def test_a_confirm_whose_requests_moved_sends_nothing(self, lab):
        lab.answer = answer(rule("block", "h1", "web-2", "udp", 5001, duration=600))
        got = draft(lab, "Block h1 from web-2 on udp 5001 for 10 minutes")
        pv = P.preview(NET, got["policy"], driver=lab.driver)
        ask = copy.deepcopy(pv["check"]["ask"])
        ask["changes"][0]["flow"]["hard_timeout"] = 60000
        done = P.confirm(NET, got["policy"], ask, pv["plan"]["hash"], actor=ACTOR,
                         driver=lab.driver, sleep=lambda s: None)
        assert done["outcome"] == "refused" and "not what this policy compiles" in done["error"]
        assert lab.fake.writes == []
