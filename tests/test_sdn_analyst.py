"""The SDN analyst (Lab 9 B1, C2903; modules/sdn/analyst.py; board I of docs/boards/lab9-sdn.html).

The controller is the lab's own recorded Ryu (tests/fixtures/lab9_captures/2026-11-06/ryu-rest.txt:
the switch list, the discovered links and every switch's port descriptions, real, masked), read
through Mercury's real Ryu driver and connection; the recording holds no flow table or port
counters, so those two reads answer planted tables in Ryu 4.34's own shapes (`LabRyu`), the one
edit. No model is called: the gateway is real (its trigger, allowance, caps, mask and record)
and its provider a fake `send` answering `w.answer`.

- **The collection** adds link status: each switch's port descriptions (Open vSwitch dpid 3's
  port 3 reports LINK_DOWN in the capture) and the controller's links; 1 + 1 + 4N calls. Without
  `links` it is as before. A port description that fails is said and the switch partial.
- **The snapshot**: every fact with its evidence id (port, rate, flow, drop, link), masked and
  sealed, kept under its own id and read again by it; changed since kept, refused. A link an
  earlier snapshot discovered and this one does not is kept, "not discovered now".
- **The prompt** holds every evidence id and nothing a person planted; IPv4 and IPv6 flows alike.
- **The check**: an uncited finding and one citing only unknown ids dropped and counted; unknown
  ids removed; lengths capped; a malformed answer refused, named, nothing used.
- **Found and missed** from the evidence the kept findings cite; the sheet downloads.
- **The call**: one, a person's, its cost recorded, the day cap refusing before anything is sent;
  a background trigger refused.
- **The routes**: gated, each press's state kept, the page drawing the region and writing nothing.
"""
import csv
import io
import json
import os
import re
import types
from html import unescape

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, gateway, triggers
from modules.sdn import analyst as AN
from modules.sdn import closed_loop as CL
from modules.sdn import connections as C
from tests.ai_person import PERSON, pressed_by
from tests.fixtures.sdn.ryu_recorded import BASE_URL, RecordedRyu
from tests.sdn_fakes import Clock, FakeRyu, Response, Session
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"
KEY = "sk-planted-sdn-analyse-key-0123456789"
#: The capture's switches (`/stats/switches`): the ProCurve, OVS 4 and 3, the two Aristas.
DPIDS = [56298109234905574, 4, 3, 2214744208935, 2843895626628]
OVS3 = "0000000000000003"
#: Planted flows on Open vSwitch 3, OXM names (FakeRyu._ryu_flow gives Ryu's shapes).
OVS3_FLOWS = [
    {"priority": 0, "cookie": 0, "match": {}, "actions": [{"type": "OUTPUT", "port": "CONTROLLER"}],
     "packet_count": 40, "byte_count": 4000},
    {"priority": 100, "cookie": 0, "match": {"eth_type": 2048, "ipv4_dst": "198.51.100.20"},
     "actions": [{"type": "OUTPUT", "port": 2}], "packet_count": 900, "byte_count": 90000},
    {"priority": 100, "cookie": 0, "match": {"eth_type": 34525, "ipv6_dst": "2001:db8::20"},
     "actions": [{"type": "OUTPUT", "port": 2}], "packet_count": 300, "byte_count": 30000},
    {"priority": 500, "cookie": 0, "match": {"eth_type": 2048, "ipv4_src": "198.51.100.250"},
     "actions": [], "packet_count": 0, "byte_count": 0},
]
#: Words a person types on the planted-issue sheet: none may reach a model.
PLANTED_WORDS = ("Xyzzy stale drop planted by hand", "plugh: shut the port on the OVS host",
                 "Frobozz link pulled")


def ryu_flow(f):
    from tests.sdn_fakes import ryu_action
    out = FakeRyu._ryu_flow(dict(f, actions=[]))
    out["actions"] = [ryu_action(a) for a in f["actions"]]
    return out


class LabRyu(Session):
    """The recorded Ryu (`RecordedRyu`) for what it recorded; flow tables and port counters
    planted for what it did not (each port's second read is its first plus *moved*)."""

    def __init__(self, flows=None, moved=None, fail=()):
        super().__init__()
        self.rec = RecordedRyu()
        self.flows = flows if flows is not None else {3: OVS3_FLOWS}
        self.moved = moved or {}
        self.fail = set(fail)
        self.port_reads = {}

    def request(self, method, url, **kwargs):
        self.sent.append(dict(kwargs, method=method, url=url))
        path = url[len(BASE_URL):]
        if path in self.fail:
            return Response(500, "boom", "text/plain")
        parts = path.strip("/").split("/")
        if path.startswith("/stats/flow/"):
            dpid = int(parts[-1])
            table = self.flows.get(dpid) or [OVS3_FLOWS[0]]
            return Response(200, json.dumps({str(dpid): [ryu_flow(f) for f in table]}))
        if path.startswith("/stats/port/"):
            dpid = int(parts[-1])
            n = self.port_reads[dpid] = self.port_reads.get(dpid, 0) + 1
            desc = self.rec.answer("GET", f"/stats/portdesc/{dpid}")[str(dpid)]
            out = []
            for p in desc:
                move = self.moved.get((dpid, p["port_no"]), 0) if n > 1 else 0
                out.append({"port_no": p["port_no"], "rx_packets": 1000 + move,
                            "tx_packets": 1000, "rx_bytes": 100000 + move * 100,
                            "tx_bytes": 100000, "rx_dropped": 0, "tx_dropped": 0,
                            "rx_errors": 0, "tx_errors": 0})
            return Response(200, json.dumps({str(dpid): out}))
        return Response(200, json.dumps(self.rec.answer(method, path)))


def collect(session=None, **kw):
    session = session or LabRyu()
    clock = Clock()

    def sleep(s):
        clock.now += s
    got = CL.collect_threat_data(NET, 5.0, sleep=sleep, clock=clock, now=lambda: 1_794_000_000.0,
                                 driver=lambda net, name: C.driver_for(net, name, session=session),
                                 **kw)
    return got, session


def answer(*findings) -> dict:
    return {"findings": list(findings)}


def finding(evidence, severity="high", text="Link down on 0000000000000003 port 3",
            why="The switch reports port 3 LINK_DOWN."):
    return {"severity": severity, "finding": text, "why": why, "evidence": list(evidence)}


@pytest.fixture
def world(networks, monkeypatch):  # noqa: F811 - the fixture, used
    """Hosted AI allowed with a day cap in a real settings file, a key, the record of AI calls in
    the test's folder, one Ryu connection on the network, and a fake provider."""
    from modules.settings_schema import write_settings

    assert write_settings({"ai_hosted": {"by": PERSON, "at": "2026-11-09T00:00:00Z",
                                         "reason": "the lab's proof of concept"},
                           "ai_cap_usd_per_day": 1.50})["ok"]
    assert C.save_connection(NET, {"name": "ctl-1", "kind": "ryu", "url": BASE_URL},
                             actor="op@example.com")["ok"]
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    monkeypatch.setattr(calls, "_path", lambda: str(networks / "ai_calls.jsonl"))
    w = types.SimpleNamespace(sent=[], answer=answer(), dir=networks, raw=None)

    def send(body, key):
        w.sent.append(body)
        text = w.raw if w.raw is not None else json.dumps(w.answer)
        return A.Reply(status=200, body={"content": [{"type": "text", "text": text}],
                                         "stop_reason": "end_turn",
                                         "usage": {"input_tokens": 6000, "output_tokens": 400}},
                       attempts=1, latency_s=0.1)
    w.send = send
    return w


def snap_of(world, session=None, previous=None):  # noqa: F811
    got, _s = collect(session, links=True)
    snap = AN.build_snapshot(NET, got, by=PERSON, previous=previous)
    AN.save_snapshot(NET, snap)
    return snap


def analyse(world, snap, **kw):  # noqa: F811
    with pressed_by(PERSON):
        return AN.analyse(NET, snap["id"], actor=PERSON, trigger=triggers.person(PERSON),
                          send=world.send, **kw)


# ── the collection ────────────────────────────────────────────────────────────────────────────

def test_the_collection_reads_each_switch_s_link_state_and_the_controller_s_links(world):
    got, session = collect(links=True)
    assert got["calls"] == 1 + 1 + 4 * len(DPIDS), "the switch list, the links, 4 per switch"
    (ctl,) = got["controllers"]
    assert len(ctl["links"]) == 10 and ctl["links_error"] == "", "the capture's 10 directions"
    by = {s["dpid_hex"]: s for s in ctl["switches"]}
    ovs3 = {p["port_no"]: p["link_up"] for p in by[OVS3]["port_desc"]}
    assert ovs3 == {1: True, "LOCAL": False, 2: True, 3: False}, "the capture's LINK_DOWN bits"
    assert {p["port_no"]: p["link_up"] for p in by["00c802d5027901e6"]["port_desc"]} == \
        {3: True, "LOCAL": True, 2: True}
    assert sum(u["url"].endswith("/stats/portdesc/3") for u in session.sent) == 1


def test_without_links_the_collection_reads_as_it_did(world):
    got, session = collect()
    assert got["calls"] == 1 + 3 * len(DPIDS)
    (ctl,) = got["controllers"]
    assert "links" not in ctl and all("port_desc" not in s for s in ctl["switches"])
    assert not any("portdesc" in u["url"] or "topology" in u["url"] for u in session.sent)


def test_a_port_description_that_fails_is_said_and_its_switch_partial(world):
    got, _s = collect(LabRyu(fail={"/stats/portdesc/3", "/v1.0/topology/links"}), links=True)
    (ctl,) = got["controllers"]
    sw = next(s for s in ctl["switches"] if s["dpid_hex"] == OVS3)
    assert sw["state"] == "partial" and sw["port_desc"] == []
    assert "port descriptions:" in sw["error"] and sw["port_desc_error"]
    assert ctl["links"] == [] and ctl["links_error"]
    snap = AN.build_snapshot(NET, got, by=PERSON)
    assert any(u.startswith("controller ctl-1's discovered links:") for u in snap["unread"])
    assert any(u.startswith(f"switch {OVS3} on ctl-1:") for u in snap["unread"])


# ── the snapshot ─────────────────────────────────────────────────────────────────────────────

def test_every_fact_carries_its_evidence_id_of_each_kind(world):
    snap = snap_of(world)
    ids = AN.evidence_ids(snap)
    s3 = next(s for s in snap["switches"] if s["dpid_hex"] == OVS3)
    assert f"port:ctl-1:{OVS3}:3" in ids and f"rate:ctl-1:{OVS3}:3" in ids
    assert not next(p for p in s3["ports"] if p["port_no"] == 3)["link_up"]
    (drop,) = s3["drops"]
    assert drop["id"].startswith(f"drop:ctl-1:{OVS3}:t0:p500:") and drop["packet_count"] == 0
    assert len(s3["flows"]) == 3 and all(f["id"].startswith(f"flow:ctl-1:{OVS3}:") for f in s3["flows"])
    assert "link:ctl-1:0000000000000003:2-0000000000000004:2" in ids
    assert len(snap["links"]) == 5, "10 directions, 5 links"
    assert {kind for kind in (i.split(":", 1)[0] for i in ids)} == set(AN.ID_KINDS)


def test_the_snapshot_is_kept_sealed_and_read_again_by_its_id(world):
    snap = snap_of(world)
    assert snap["id"].startswith("snap-") and AN.intact(snap)
    assert AN.snapshot(NET, snap["id"]) == {"ok": True, "error": "", "snapshot": snap}
    path = os.path.join(AN._dir(NET), "snapshots", f"{snap['id']}.json")
    kept = json.load(open(path, encoding="utf-8"))
    kept["switches"][0]["name"] = "edited"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(kept, fh)
    got = AN.snapshot(NET, snap["id"])
    assert not got["ok"] and "changed since it was kept" in got["error"]
    r = analyse(world, snap)
    assert r["error"] == "snapshot" and world.sent == [], "nothing is sent"


def test_a_link_an_earlier_snapshot_discovered_is_kept_as_not_discovered_now(world):
    earlier = snap_of(world)
    lost = "link:ctl-1:0000000000000003:3-00c802d5027901e6:2"
    earlier["links"].append({"id": lost, "connection": "ctl-1", "state": "up",
                             "ends": [["0000000000000003", "3"], ["00c802d5027901e6", "2"]],
                             "discovered": True, "words": "discovered"})
    snap = snap_of(world, previous=earlier)
    ln = next(x for x in snap["links"] if x["id"] == lost)
    assert ln["state"] == "not discovered" and ln["since"] == earlier["collected_at"]
    assert "0000000000000003 port 3 down" in ln["words"]
    assert f"{lost} not discovered:" in AN.facts(snap)


# ── the prompt ───────────────────────────────────────────────────────────────────────────────

def test_the_prompt_holds_every_evidence_id_and_nothing_a_person_planted(world):
    snap = snap_of(world)
    for words in PLANTED_WORDS:
        assert AN.add_planted(NET, words, f"port:ctl-1:{OVS3}:*", why=words + " why",
                              actor=PERSON)["ok"]
    analyse(world, snap)
    (body,) = world.sent
    sent = json.dumps(body)
    ids = AN.evidence_ids(snap)
    assert len(ids) > 40
    assert all(i in sent for i in ids), sorted(i for i in ids if i not in sent)
    for words in PLANTED_WORDS:
        assert words not in sent and words.split(":")[0] not in sent
    assert f"port:ctl-1:{OVS3}:*" not in sent
    assert body["model"] == "claude-haiku-5-5"


def test_ipv4_and_ipv6_flows_are_sent_alike_and_each_is_citable(world):
    snap = snap_of(world)
    text = AN.facts(snap)
    s3 = next(s for s in snap["switches"] if s["dpid_hex"] == OVS3)
    v4 = next(f for f in s3["flows"] if "ipv4_dst" in f["match"])
    v6 = next(f for f in s3["flows"] if "ipv6_dst" in f["match"])
    assert f"{v4['id']} table 0, priority 100, match eth_type=2048 ipv4_dst=198.51.100.20" in text
    assert f"{v6['id']} table 0, priority 100, match eth_type=34525 ipv6_dst=2001:db8::20" in text
    world.answer = answer(finding([v6["id"]], "low", "IPv6 traffic to 2001:db8::20"),
                          finding([v4["id"]], "low", "IPv4 traffic to 198.51.100.20"))
    r = analyse(world, snap)
    assert [f["evidence"] for f in r["findings"]] == [[v6["id"]], [v4["id"]]]


# ── the check ────────────────────────────────────────────────────────────────────────────────

def test_the_check_drops_what_cites_nothing_the_snapshot_holds_and_counts_it(world):
    snap = snap_of(world)
    port = f"port:ctl-1:{OVS3}:3"
    world.answer = answer(
        finding([port, "port:ctl-1:00000000000000ff:9"]),
        finding([], "medium", "A claim with no evidence"),
        finding(["flow:made:up"], "critical", "A claim citing an id never sent"),
        finding([port], "critical", "x" * 400, "y" * 1200))
    r = analyse(world, snap)
    assert r["ok"] and [f["severity"] for f in r["findings"]] == ["critical", "high"]
    assert r["dropped"] == 2 and r["dropped_by"]["uncited"] == 1 \
        and r["dropped_by"]["unknown_only"] == 1
    assert r["dropped_words"] == "1 cited nothing; 1 cited only ids the collection does not hold"
    assert r["removed_ids"] == 2 and r["findings"][1]["removed"] == ["port:ctl-1:00000000000000ff:9"]
    first = r["findings"][0]
    assert len(first["finding"]) == AN.MAX_FINDING_CHARS and first["finding"].endswith("…")
    assert len(first["why"]) == AN.MAX_WHY_CHARS and r["capped"] == 2
    kept = AN.analysis(NET, r["id"])
    assert kept["findings"] == r["findings"] and kept["dropped"] == 2
    (use,) = calls.uses()[r["call_id"]]
    assert use["use"] == "shown: 2 findings, 2 dropped by the check"


def test_an_entry_cited_as_a_whole_line_is_cut_to_its_id_which_must_still_exist(world):
    """The Lab 9 sitting, 2026-11-10: the model cited each evidence entry as the WHOLE
    snapshot line ("<id> <the fact's words>"), every one failed the exact-id check, and both
    findings were dropped. The id is the entry's leading token; it is kept only when the
    collection holds exactly that id, and each entry cut is recorded."""
    snap = snap_of(world)
    port = f"port:ctl-1:{OVS3}:3"
    line = next(ln for ln in AN.facts(snap).splitlines() if ln.startswith(port + " "))
    assert line != port and line.split(None, 1)[0] == port, "a real line of the facts sent"
    world.answer = answer(
        finding([line, f"\t{port}\twith a tab"], "high", "Whole lines, one id"),
        finding([port], "medium", "The id alone"),
        finding(["port:made:up"], "critical", "A made-up id"),
        finding(["port:made:up and words after it"], "critical", "A made-up id in a line"),
        finding([f"{port}x LINK_DOWN", line], "low", "One real line, one near miss"))
    r = analyse(world, snap)
    assert r["ok"]
    got = {f["finding"]: f for f in r["findings"]}
    assert sorted(got) == ["One real line, one near miss", "The id alone", "Whole lines, one id"]
    # Whole lines are trimmed and kept, once, as the id; the id alone is not marked trimmed.
    assert got["Whole lines, one id"]["evidence"] == [port]
    assert got["Whole lines, one id"]["trimmed"] == [port]
    assert got["The id alone"]["evidence"] == [port] and got["The id alone"]["trimmed"] == []
    # A trimmed id the collection does not hold is removed; the finding stands on the real one.
    near = got["One real line, one near miss"]
    assert near["evidence"] == [port] and near["removed"] == [f"{port}x"]
    assert sorted(near["trimmed"]) == [port, f"{port}x"]
    # A made-up id is dropped, bare or leading a line.
    assert r["dropped"] == 2 and r["dropped_by"]["unknown_only"] == 2
    assert r["removed_ids"] == 3 and r["trimmed_ids"] == 4
    kept = AN.analysis(NET, r["id"])
    assert kept["findings"] == r["findings"] and kept["trimmed_ids"] == 4
    (use,) = calls.uses()[r["call_id"]]
    assert use["use"] == "shown: 3 findings, 2 dropped by the check"
    assert "4 evidence entries cited as a whole line, cut to their id" in use["detail"]
    # The check itself, by hand: nothing is matched by resemblance.
    direct = AN.check(AN.NetworkAnalysis.model_validate_json(json.dumps(answer(
        finding([f"{port} "]), finding([port.upper() + " x"])))), {port})
    assert [f["evidence"] for f in direct["findings"]] == [[port]]
    assert direct["findings"][0]["trimmed"] == [] and direct["dropped_by"]["unknown_only"] == 1


@pytest.mark.parametrize("raw, words", [
    ("the network looks fine", "the answer is not sdn_analyse.v1"),
    (json.dumps({"findings": [{"severity": "severe", "finding": "f", "why": "w",
                               "evidence": []}]}), "findings.0.severity"),
    (json.dumps({"findings": [{"severity": "high", "finding": "f", "why": "w"}]}),
     "findings.0.evidence"),
    (json.dumps({"findings": [], "extra": 1}), "extra"),
])
def test_a_malformed_answer_is_refused_named_and_nothing_of_it_used(world, raw, words):
    snap = snap_of(world)
    world.raw = raw
    r = analyse(world, snap)
    assert not r["ok"] and r["error"] == "schema" and words in r["detail"], r["detail"]
    assert r["findings"] == [] and calls.uses().get(r["call_id"]) is None
    assert AN.view(NET)["result"]["error"] == "schema"


# ── planted issues: found and missed ─────────────────────────────────────────────────────────

def test_found_and_missed_come_from_the_evidence_the_kept_findings_cite(world):
    snap = snap_of(world)
    s3 = next(s for s in snap["switches"] if s["dpid_hex"] == OVS3)
    drop = s3["drops"][0]["id"]
    assert AN.add_planted(NET, "OVS 3's port 3 pulled", f"port:ctl-1:{OVS3}:3", actor=PERSON)["ok"]
    assert AN.add_planted(NET, "A stale drop", f"drop:ctl-1:{OVS3}:*", actor=PERSON)["ok"]
    assert AN.add_planted(NET, "Not in the collection", "flow:ctl-9:*", actor=PERSON)["ok"]
    world.answer = answer(finding([f"port:ctl-1:{OVS3}:3"]),
                          finding(["drop:never:sent"], "low", "an uncited drop claim"))
    r = analyse(world, snap)
    rows = AN.marks(AN.planted(NET)["issues"], r, AN.evidence_ids(snap))
    assert [(x["name"], x["found"], x["in_collection"]) for x in rows] == [
        ("OVS 3's port 3 pulled", "found", True), ("A stale drop", "missed", True),
        ("Not in the collection", "missed", False)]
    assert rows[0]["by"] == ["Link down on 0000000000000003 port 3"]
    assert drop.startswith(f"drop:ctl-1:{OVS3}:")
    v = AN.view(NET)
    assert (v["found"], v["missed"]) == (1, 2)


def test_planted_evidence_must_name_an_evidence_kind_and_why_is_saved(world):
    got = AN.add_planted(NET, "x", "198.51.100.250", actor=PERSON)
    assert not got["ok"] and "is not an evidence id or pattern" in got["error"]
    assert AN.planted(NET)["state"] == "absent"
    pid = AN.add_planted(NET, "A stale drop", f"drop:ctl-1:{OVS3}:*", actor=PERSON)["issue"]["id"]
    assert AN.set_why(NET, pid, "zero-count drop flow", actor=PERSON)["ok"]
    (issue,) = AN.planted(NET)["issues"]
    assert issue["why"] == "zero-count drop flow" and issue["why_by"] == PERSON
    assert not AN.set_why(NET, "pl-000000000000", "w", actor=PERSON)["ok"]


def test_the_sheet_downloads_as_markdown_and_csv(world):
    snap = snap_of(world)
    AN.add_planted(NET, "OVS 3's port | pulled", f"port:ctl-1:{OVS3}:3", why="pulled the cable",
                   actor=PERSON)
    world.answer = answer(finding([f"port:ctl-1:{OVS3}:3"]))
    r = analyse(world, snap)
    md = AN.sheet_markdown(NET, by=PERSON, now=1_794_000_000.0)
    assert f"- Analysis: {r['id']} (snapshot {snap['id']}" in md
    assert "| OVS 3's port \\| pulled | found |" in md and "pulled the cable |" in md
    rows = list(csv.reader(io.StringIO(AN.sheet_csv(NET, by=PERSON))))
    assert rows[0] == ["# network", NET] and rows[3][:2] == ["planted", "found"]
    assert rows[4][:2] == ["OVS 3's port | pulled", "found"] and rows[4][4] == "yes"


# ── planted issues corrected, removed, and planted after (C2913, C2956) ────────────────────────

def _press(path, **data):
    import app as APP

    return APP.app.test_client().post(path, data=dict(data, list=NET),
                                      headers={"HX-Request": "true"})


def _store():
    with open(AN._planted_path(NET), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("who", ["nobody", "service"])
@pytest.mark.parametrize("verb", ["edit", "remove"])
def test_edit_and_remove_are_a_person_s_and_refused_without_one(world, monkeypatch, who, verb):
    """C2913: the gate refuses an unverified request and a verified service before input, and
    the store is left byte for byte as it was."""
    from modules import identity

    pid = AN.add_planted(NET, "A stale drop", f"drop:ctl-1:{OVS3}:*", actor=PERSON)["issue"]["id"]
    before = _store()
    if who == "nobody":
        ident = identity.Identity(outcome="no_header", reason="no access assertion")
    else:
        ident = identity.Identity(actor="service:ci", kind="service", service_id="ci",
                                  verified=True, outcome="ok", peer="127.0.0.1",
                                  peer_trusted=True)
    monkeypatch.setattr(identity, "identify", lambda _request: ident)
    r = _press(f"/v2/sdn/analyse/planted/{pid}/{verb}", name="Renamed",
               evidence=f"port:ctl-1:{OVS3}:3")
    assert r.status_code in (401, 403), r.status_code
    assert _store() == before


def test_an_edit_keeps_who_when_and_before_and_after_in_the_sheet_s_history(world):
    from tests.conftest import TEST_PERSON

    pid = AN.add_planted(NET, "A stale drop", f"drop:ctl-1:{OVS3}0:*", actor=PERSON,
                         now=1_794_000_000.0)["issue"]["id"]
    issue = AN.planted(NET)["issues"][0]
    r = _press(f"/v2/sdn/analyse/planted/{pid}/edit", name="A stale drop on OVS 3",
               evidence=f"drop:ctl-1:{OVS3}:*", rev=AN.rev(issue))
    assert r.status_code == 200 and "Changes to the sheet (2)" in _html(r)
    kept = _store()
    (got,) = kept["issues"]
    assert (got["id"], got["name"], got["evidence"]) == (pid, "A stale drop on OVS 3",
                                                         [f"drop:ctl-1:{OVS3}:*"])
    assert got["edited_by"] == TEST_PERSON and got["edited_at"].endswith("Z")
    assert got["at"] == "2026-11-06T21:20:00Z", "it keeps when it was planted"
    add, edit = kept["history"]
    assert (add["action"], add["by"], add["before"]) == ("add", PERSON, None)
    assert edit == {"at": got["edited_at"], "by": TEST_PERSON, "action": "edit", "id": pid,
                    "name": "A stale drop on OVS 3",
                    "before": {"name": "A stale drop", "evidence": [f"drop:ctl-1:{OVS3}0:*"]},
                    "after": {"name": "A stale drop on OVS 3",
                              "evidence": [f"drop:ctl-1:{OVS3}:*"]}}
    same = _press(f"/v2/sdn/analyse/planted/{pid}/edit", name="A stale drop on OVS 3",
                  evidence=f"drop:ctl-1:{OVS3}:*")
    assert same.status_code == 422 and "nothing is changed" in _html(same)
    bad = _press(f"/v2/sdn/analyse/planted/{pid}/edit", name="x", evidence="198.51.100.250")
    assert bad.status_code == 422 and "Couldn't save:" in _html(bad)
    assert len(_store()["history"]) == 2, "a refused edit records nothing"


def test_an_edit_made_since_the_form_drew_it_is_refused_naming_both(world):
    pid = AN.add_planted(NET, "A stale drop", f"drop:ctl-1:{OVS3}:*", actor=PERSON)["issue"]["id"]
    drawn = AN.rev(AN.planted(NET)["issues"][0])
    assert AN.edit_planted(NET, pid, "Another tab's name", f"drop:ctl-1:{OVS3}:*",
                           actor=PERSON, drawn=drawn)["ok"]
    now = AN.rev(AN.planted(NET)["issues"][0])
    for verb in ("edit", "remove"):
        r = _press(f"/v2/sdn/analyse/planted/{pid}/{verb}", name="Mine",
                   evidence=f"port:ctl-1:{OVS3}:3", rev=drawn)
        assert r.status_code == 422 and f"(drawn {drawn}, now {now}:" in _html(r), verb
    (issue,) = AN.planted(NET)["issues"]
    assert issue["name"] == "Another tab's name" and not issue.get("removed_at")


def test_an_edited_evidence_turns_a_missed_issue_found_by_the_analysis_that_cited_it(world):
    snap = snap_of(world)
    pid = AN.add_planted(NET, "OVS 3's port 3 pulled", f"port:ctl-1:{OVS3}:30",
                         actor=PERSON)["issue"]["id"]
    world.answer = answer(finding([f"port:ctl-1:{OVS3}:3"]))
    r = analyse(world, snap)
    assert (AN.view(NET)["found"], AN.view(NET)["missed"]) == (0, 1)
    edited = _press(f"/v2/sdn/analyse/planted/{pid}/edit", name="OVS 3's port 3 pulled",
                    evidence=f"port:ctl-1:{OVS3}:3")
    assert edited.status_code == 200
    v = AN.view(NET)
    assert (v["found"], v["missed"]) == (1, 0)
    assert v["planted"][0]["by"] == ["Link down on 0000000000000003 port 3"]
    (sheet,) = AN.sheets(NET)["sheets"]
    assert sheet["analysis"]["id"] == r["id"] and sheet["rows"][0]["found"] == "found"


def test_ipv4_and_ipv6_evidence_ids_are_kept_whole_by_an_edit(world):
    """The IPv4 and the IPv6 flow's ids (an address never in an id) and a typed pattern naming
    each address, kept whole through the edit, its history, both downloads and the match."""
    snap = snap_of(world)
    s3 = next(s for s in snap["switches"] if s["dpid_hex"] == OVS3)
    v4 = next(f for f in s3["flows"] if "ipv4_dst" in f["match"])["id"]
    v6 = next(f for f in s3["flows"] if "ipv6_dst" in f["match"])["id"]
    pid = AN.add_planted(NET, "Traffic to h20", "flow:ctl-9:*", actor=PERSON)["issue"]["id"]
    world.answer = answer(finding([v6], "low", "IPv6 traffic to 2001:db8::20"),
                          finding([v4], "low", "IPv4 traffic to 198.51.100.20"))
    analyse(world, snap)
    typed = [v4, v6, "flow:ctl-1:*:2001:db8::20*", "flow:ctl-1:*:198.51.100.20*"]
    got = AN.edit_planted(NET, pid, "Traffic to h20", "\n".join(typed[:2]) + ", " +
                          " ".join(typed[2:]), actor=PERSON)
    assert got["ok"], got
    assert AN.planted(NET)["issues"][0]["evidence"] == typed
    assert _store()["history"][-1]["after"]["evidence"] == typed
    (row,) = AN.view(NET)["planted"]
    assert row["found"] == "found" and row["by"] == ["IPv6 traffic to 2001:db8::20",
                                                     "IPv4 traffic to 198.51.100.20"]
    rows = list(csv.reader(io.StringIO(AN.sheet_csv(NET, by=PERSON))))
    assert rows[4][2] == " ".join(typed)
    assert " ".join(typed) in AN.sheet_markdown(NET, by=PERSON)


def test_a_removed_issue_leaves_the_sheet_and_its_counts_and_is_kept_with_its_history(world):
    from tests.conftest import TEST_PERSON

    snap = snap_of(world)
    keep = AN.add_planted(NET, "OVS 3's port 3 pulled", f"port:ctl-1:{OVS3}:3",
                          actor=PERSON)["issue"]["id"]
    pid = AN.add_planted(NET, "A wrong port", f"port:ctl-1:{OVS3}:9", why="mistyped",
                         actor=PERSON)["issue"]["id"]
    world.answer = answer(finding([f"port:ctl-1:{OVS3}:3"]))
    analyse(world, snap)
    assert (AN.view(NET)["found"], AN.view(NET)["missed"]) == (1, 1)
    r = _press(f"/v2/sdn/analyse/planted/{pid}/remove",
               rev=AN.rev(AN.planted(NET)["issues"][1]))
    assert r.status_code == 200 and "A wrong port" in _html(r)
    v = AN.view(NET)
    assert (v["found"], v["missed"], v["removed"]) == (1, 0, 1)
    assert [p["id"] for p in v["planted"]] == [keep]
    kept = _store()
    gone = next(i for i in kept["issues"] if i["id"] == pid)
    assert gone["removed_by"] == TEST_PERSON and gone["why"] == "mistyped"
    assert kept["history"][-1] == {
        "at": gone["removed_at"], "by": TEST_PERSON, "action": "remove", "id": pid,
        "name": "A wrong port", "after": None,
        "before": {"name": "A wrong port", "evidence": [f"port:ctl-1:{OVS3}:9"],
                   "why": "mistyped"}}
    assert [r["name"] for r in AN.sheets(NET)["sheets"][0]["rows"]] == ["OVS 3's port 3 pulled"]
    rows = list(csv.reader(io.StringIO(AN.sheet_csv(NET, by=PERSON))))
    assert [x[0] for x in rows[4:]] == ["OVS 3's port 3 pulled"]
    md = AN.sheet_markdown(NET, by=PERSON)
    assert "## Changes to the sheet" in md and f"removed “A wrong port” (it was evidence " \
        f"port:ctl-1:{OVS3}:9;" in md and "- Planted: 1 found · 0 missed" in md
    again = AN.remove_planted(NET, pid, actor=PERSON)
    assert not again["ok"] and f"was removed by {TEST_PERSON}" in again["error"]
    assert not AN.edit_planted(NET, pid, "x", f"port:ctl-1:{OVS3}:3", actor=PERSON)["ok"]
    assert not AN.set_why(NET, pid, "w", actor=PERSON)["ok"]


def test_an_issue_planted_after_the_analysis_reads_so_on_the_page_and_both_downloads(world):
    """C2956: pressed Add a planted issue after the analysis; neither found nor missed, outside
    both counts, on the page, the CSV and the Markdown, as History › Export reads it."""
    import time

    snap = snap_of(world)
    assert AN.add_planted(NET, "OVS 3's port 3 pulled", f"port:ctl-1:{OVS3}:3", actor=PERSON,
                          now=time.time() - 600)["ok"]
    world.answer = answer(finding([f"port:ctl-1:{OVS3}:3"]))
    r = analyse(world, snap, now=time.time() - 300)
    added = _press("/v2/sdn/analyse/planted", name="A stale drop",
                   evidence=f"drop:ctl-1:{OVS3}:*", why="")
    html = _html(added)
    assert added.status_code == 200 and "1 found · 0 missed · 1 planted after this analysis" in html
    assert re.search(r'<span class="badge badge-muted" title="planted [^"]+, after the analysis '
                     rf'of {r["at"]}[^"]*">planted after this analysis</span>', html)
    v = AN.view(NET)
    assert [p["found"] for p in v["planted"]] == ["found", AN.PLANTED_AFTER]
    assert (v["found"], v["missed"], v["after"]) == (1, 0, 1)
    rows = list(csv.reader(io.StringIO(AN.sheet_csv(NET, by=PERSON))))
    assert [x[:2] for x in rows[4:]] == [["OVS 3's port 3 pulled", "found"],
                                        ["A stale drop", AN.PLANTED_AFTER]]
    md = AN.sheet_markdown(NET, by=PERSON)
    assert "| A stale drop | planted after this analysis |" in md
    assert "- Planted: 1 found · 0 missed · 1 planted after this analysis" in md
    (sheet,) = AN.sheets(NET)["sheets"]
    assert [x["found"] for x in sheet["rows"]] == ["found", AN.PLANTED_AFTER]


# ── the call ─────────────────────────────────────────────────────────────────────────────────

def test_one_call_a_person_s_its_cost_recorded(world):
    snap = snap_of(world)
    world.answer = answer(finding([f"port:ctl-1:{OVS3}:3"]))
    r = analyse(world, snap)
    assert len(world.sent) == 1 and r["ok"]
    (row,) = [x for x in calls.read()["rows"] if x.get("feature") == AN.FEATURE]
    assert row["trigger"]["kind"] == "person" and row["actor"] == PERSON
    assert row["model"] == "claude-haiku-5-5" and row["prompt"] == "sdn_analyse.v1"
    assert row["subject"] == {"kind": "sdn_snapshot", "id": snap["id"], "devices": []}
    assert row["cost_usd"] == pytest.approx(r["cost_usd"]) and r["cost_usd"] > 0
    assert r["cost_usd"] <= gateway.caps(AN.FEATURE)["per_call"]


def test_the_day_cap_refuses_before_anything_is_sent(world):
    from modules.settings_schema import write_settings

    snap = snap_of(world)
    assert write_settings({"ai_cap_usd_per_day": 0.0001})["ok"]
    r = analyse(world, snap)
    assert not r["ok"] and r["error"] == "over_cap" and world.sent == []
    (row,) = [x for x in calls.read()["rows"] if x.get("feature") == AN.FEATURE]
    assert row["verdict"] == "over_cap"


def test_a_background_trigger_and_no_trigger_are_refused(world):
    snap = snap_of(world)
    with pressed_by(PERSON):
        bg = AN.analyse(NET, snap["id"], actor="job:x", send=world.send,
                        trigger=triggers.background(AN.FEATURE, "x", NET, "snapshot", "s"))
        none = AN.analyse(NET, snap["id"], actor=PERSON, trigger=None, send=world.send)
    assert not bg["ok"] and bg["error"] == "trigger" and "not a background feature" in bg["detail"]
    assert not none["ok"] and none["error"] == "trigger" and world.sent == []


def test_the_topology_class_off_sends_nothing(world, monkeypatch):
    from modules.ai import egress_classes
    snap = snap_of(world)
    monkeypatch.setattr(egress_classes, "topology_allowed",
                        lambda n: {"allowed": False, "why": "the topology class is off"})
    r = analyse(world, snap)
    assert r["error"] == "withheld" and world.sent == [] and "nothing was sent" in r["detail"]


# ── the collection job ───────────────────────────────────────────────────────────────────────

def test_one_collection_at_a_time_and_the_job_keeps_its_snapshot(world):
    started = []
    assert AN.start_collection(NET, actor=PERSON, spawn=started.append, now=1000.0)["ok"]
    second = AN.start_collection(NET, actor="other@example.com", spawn=started.append, now=1001.0)
    assert not second["ok"] and f"started by {PERSON}" in second["error"] \
        and "never queued" in second["error"] and len(started) == 1
    late = 1000.0 + AN.collection_bound_s(NET) + 1
    assert AN.running(NET, late)["stale"] is True
    session = LabRyu()
    got = AN.collect_job(NET, actor=PERSON, sleep=lambda s: None, announce=False,
                         driver=lambda net, name: C.driver_for(net, name, session=session))
    assert got["ok"] and AN.running(NET) == {}
    v = AN.view(NET)
    assert v["snapshot"]["id"] == got["snapshot"]["id"] and v["snapshot"]["switches"] == 5
    assert v["snapshot"]["ports_down"] == 1 and v["snapshot"]["estimate"]["usd"] > 0


def test_a_network_with_no_controller_is_refused_and_nothing_started(networks):  # noqa: F811
    started = []
    got = AN.start_collection("Branch", actor=PERSON, spawn=started.append)
    assert not got["ok"] and "no SDN controller connection" in got["error"] and started == []
    assert not os.path.exists(AN._dir("Branch"))


# ── the routes ───────────────────────────────────────────────────────────────────────────────

def test_the_routes_are_gated_and_declared():
    from modules import invalidation, route_gates
    for ep in ("collect", "ask", "planted_add", "planted_why"):
        gate = route_gates.gate_for(f"sdn_analyse_v2.{ep}")
        assert gate is not None and gate.kind == "configure", ep
        assert f"sdn_analyse_v2.{ep}" in invalidation.DECLARED, ep


def _html(r):
    return unescape(r.get_data(as_text=True))


def test_each_press_redraws_the_region_and_keeps_its_state(world, monkeypatch):
    import app as APP

    monkeypatch.setattr(gateway, "anthropic_adapter",
                        types.SimpleNamespace(**{**vars(gateway.anthropic_adapter),
                                                 "send": world.send}))
    session = LabRyu()
    monkeypatch.setattr(AN, "_spawn", lambda fn: fn())
    monkeypatch.setattr(AN, "collect_job", (lambda real: lambda network, **kw: real(
        network, sleep=lambda s: None, announce=False,
        driver=lambda net, name: C.driver_for(net, name, session=session), **kw))(AN.collect_job))
    c = APP.app.test_client()
    h = {"HX-Request": "true"}
    r = c.post("/v2/sdn/analyse/collect", data={"list": NET}, headers=h)
    assert r.status_code == 200 and 'id="sdn-analyse"' in _html(r)
    snap = AN.latest_snapshot(NET)
    assert snap["by"] and "5 switches, collected" in _html(r)
    world.answer = answer(finding([f"port:ctl-1:{OVS3}:3"]))
    r = c.post("/v2/sdn/analyse/ask", data={"list": NET, "snapshot": snap["id"]}, headers=h)
    html = _html(r)
    assert r.status_code == 200 and "1 finding" in html and "Link down on 0000000000000003" in html
    assert "Was this right?" in html and len(world.sent) == 1
    r = c.post("/v2/sdn/analyse/planted", headers=h, data={
        "list": NET, "name": "Port 3 pulled", "evidence": f"port:ctl-1:{OVS3}:3", "why": ""})
    assert r.status_code == 200 and "Port 3 pulled" in _html(r)
    (issue,) = AN.planted(NET)["issues"]
    r = c.post(f"/v2/sdn/analyse/planted/{issue['id']}/why", headers=h,
               data={"list": NET, "why": "the port's LINK_DOWN"})
    assert r.status_code == 200 and AN.planted(NET)["issues"][0]["why"] == "the port's LINK_DOWN"
    bad = c.post("/v2/sdn/analyse/planted", headers=h,
                 data={"list": NET, "name": "x", "evidence": "nothing"})
    assert bad.status_code == 422 and "Couldn't add:" in _html(bad)
    assert len(AN.planted(NET)["issues"]) == 1
    md = c.get(f"/v2/sdn/analyse/sheet/md?list={NET}")
    assert md.status_code == 200 and "| Port 3 pulled | found |" in md.get_data(as_text=True)
    assert md.headers["Content-Disposition"].endswith(f'.md"')
    assert c.get(f"/v2/sdn/analyse/sheet/pdf?list={NET}").status_code == 404


def test_the_flows_page_draws_the_region_and_writes_nothing(world):
    import app as APP

    before = os.path.exists(AN._dir(NET))
    r = APP.app.test_client().get(f"/v2/sdn/flows?list={NET}")
    html = _html(r)
    assert r.status_code == 200 and 'id="sdn-analyse"' in html and "Analyse this network" in html
    assert "No collection yet" in html and 'data-ai-control="sdn_analyse"' in html
    assert os.path.exists(AN._dir(NET)) == before is False


def test_analyse_is_an_ai_control_and_collect_and_the_sheet_stay_usable(world, monkeypatch):
    """PHASE8_PLAN 15.13 through the page's real route: Analyse this network carries the AI mark
    with its task, model and cap; while hosted AI cannot answer it is disabled with the reason
    in place, and Collect now, Add a planted issue… and Download the sheet stay usable."""
    import app as APP
    from tests import ai_controls_check as AIC

    snap_of(world)
    c = APP.app.test_client()

    def get():
        return c.get(f"/v2/sdn/flows?list={NET}").get_data(as_text=True)

    def parity(html):
        text = unescape(html)
        assert "Collect now" in text and "Add a planted issue…" in text
        assert "Download the sheet" in text
        assert not AIC.re.search(r'<button[^>]*data-ai-off[^>]*>\s*<span class="op-idle">Collect now',
                                 text)
    AIC.check_screen(monkeypatch, get, "sdn_analyse", parity)
