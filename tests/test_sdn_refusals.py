"""A refusal by the protected set is a record (C2944), and a refusal's reason is kept whole
(C3014): `flow_intent.record_refusal`, `flow_ops.keep_refusal`, `policy_intent.keep_refusal`,
History's SDN rows (`history_sources.sdn_operations`) and History › Export
(`modules/history_export.py`).

The Lab 9 sitting (2026-11-10) made three refusals in a day, and History › Export counted
none: a person's Add flow refused for the control channel, the policy "block all UDP from h1"
refused by the protected DHCP and DNS flows, and that policy's AI call, whose use the AI-calls
file cut mid-word.

**The data.** The policy and its flows run on tests/test_sdn_policy_intent.py's Lab 9 world
(the fabric's NetBox records as `export.build` gives them, with the protected DNS and DHCP
Services; Ryu's captured topology; FakeRyu behind the real Ryu driver; a fake `send` behind the
real gateway) through the real routes (tests/test_sdn_policies_v2.py's `ui`). The sentence is
the sitting's own, "block all UDP from h1". The planted management class (IPv4 and IPv6) is
tests/test_protected.py's, on tests/test_sdn_ops_v2.py's lab (Ryu's captured flow table).
AUTO's refusal is `loop.propose`'s, in the real guard's words, as tests/test_history_export.py
makes it. A call recorded before the record existed is a real refused call's row and use
copied under a new id, its detail cut to 200 characters as the parent recorded it.

- **A policy the protected set refuses** is a record: who and how verified, the policy asked,
  each protected flow that refused it with its citation, its AI call; the answer says it is
  recorded; nothing is sent.
- **Its reason is whole** in the call's use and in the AI-calls file's "then" column; a use
  recorded at the old cut says its end may be missing.
- **A person's flow preview** the control channel, a class (IPv4 and IPv6) or a protected
  object refuses is a record, written by the press and never by the plan; any other refusal
  and a preview that passes keep none.
- **A confirm** the protected set refuses is a record; AUTO's is the response's own, never a
  second one.
- **History › Export** counts each kind once and says which each row is; **History** draws
  each as an SDN row naming who and how they were verified.
- **A record that cannot be kept** is said on the card, and an unreadable store in the file.
- **Who is recorded** (`TestWhoIsRecorded`, the real identity layer): a record is a verified
  person's. For each recording route (a flow's, a response's and a re-apply's preview; a
  policy's draft, check again and preview) and a confirm reached where its gate is opened, a
  signed-out press is answered, leaves the whole data folder byte for byte what it was and
  draws the not-recorded line; the local account's, signed in, is recorded as local-account.
"""
import csv
import io
import json
import os
import time
from html import unescape

import pytest

from modules import history_export as X
from modules import history_sources as H
from modules import protected as PR
from modules.ai import calls
from modules.sdn import flow_intent as F
from modules.sdn import flow_ops as O
from modules.sdn import loop as LP
from modules.sdn import policy_intent as P
from tests.conftest import TEST_PERSON
from tests.test_protected import MGMT, _pset
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ops_v2 import form_fields
from tests.test_sdn_ops_v2 import lab as ops  # noqa: F401 - the fixture, Ryu's captured table
from tests.test_sdn_policies_v2 import _draft, _text, ui  # noqa: F401 - the fixture
from tests.test_sdn_policy_intent import CONN, NET, OVS1, answer, lab, rule  # noqa: F401

SENTENCE = "block all UDP from h1"
OVS1_HEX = f"{OVS1:016x}"
SECRET = "SeCrEt-Tok3n"
PLANTED = f"https://x-access-token:{SECRET}@example.invalid/o/r.git"


def _day(offset=0):
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + offset * 86400))


TODAY, YESTERDAY = _day(), _day(-1)


def _refused_policy(ui):  # noqa: F811
    """The sitting's policy, drafted through the route and refused by the protected flows."""
    ui.answer = answer(rule("block", "h1", "any", "udp"))
    r = _draft(ui, SENTENCE)
    assert r.status_code == 409, _text(r)[:400]
    return unescape(_text(r))


def _flow(client, match, *, network=NET, dpid=OVS1_HEX, actions="drop"):
    return client.post("/v2/sdn/flow/preview", data={
        "list": network, "do": "add", "connection": CONN, "dpid": dpid, "priority": "250",
        "match": match, "actions": actions})


def _csv(text):
    rows = list(csv.reader(io.StringIO(text)))
    head = next(i for i, r in enumerate(rows) if r and r[0] == "at")
    return [dict(zip(rows[head], r)) for r in rows[head + 1:] if len(r) == len(rows[head])]


# ── a policy ────────────────────────────────────────────────────────────────────────────────

def test_a_policy_the_protected_set_refuses_is_a_record_naming_each_flow(ui):  # noqa: F811
    html = _refused_policy(ui)
    assert "Refused by a protected flow:" in html and "Nothing was sent." in html
    assert ('This refusal is recorded in <a href="/v2/history?list=Default&kind=sdn">History</a>'
            ", as you: the policy asked and each protected flow that refused it.") in html
    (row,) = F.refusals(NET)["rows"]
    assert (row["what"], row["stage"], row["network"]) == ("policy", "draft", NET)
    assert (row["actor"], row["actor_verified"]) == (TEST_PERSON, "access")
    assert row["id"].startswith("sdnrf-") and row["at"].endswith("Z")
    assert (row["connection"], row["dpid"], row["dpid_hex"]) == (CONN, OVS1, OVS1_HEX)
    assert row["asked"] == [f"“{SENTENCE}”", "block h1 to any on udp"]
    by = row["refused_by"]
    assert [b["name"] for b in by] == ["dhcp", "dns"]
    assert {(b["guard"], b["citation"]) for b in by} == {("class", "B, C2379")}
    assert [b["invariant"] for b in by] == ["must_reach dhcp", "must_reach dns"]
    assert all(b["source"].startswith("NetBox: the Service ") and b["met"] for b in by)
    assert row["policy"]["words"] == SENTENCE and row["policy"]["id"].startswith("pol-")
    assert row["words"].startswith("Refused by a protected flow: it would cover the protected "
                                   "flows dhcp (must_reach dhcp")
    (call,) = [r for r in calls.read()["rows"] if r["id"] == row["call_id"]]
    assert call["feature"] == "sdn_policy" and ui.fake.writes == []


def test_the_call_s_use_and_the_ai_calls_file_keep_the_reason_whole(ui):  # noqa: F811
    """C3014: the parent cut the check's words to 200 characters, mid-word, before it
    recorded them; the file's "then" column drew that."""
    _refused_policy(ui)
    (call,) = [r for r in calls.read()["rows"] if r.get("feature") == "sdn_policy"]
    (use,) = calls.uses()[call["id"]]
    whole = use["detail"]
    assert use["use"] == "refused by validation"
    assert whole.startswith("it would cover the protected flows dhcp (must_reach dhcp")
    assert len(whole) > 300 and whole.endswith(" alone"), (len(whole), whole[-60:])
    got = X.calls(NET, YESTERDAY, TODAY)
    (line,) = [r for r in got["rows"] if r["call"] == call["id"]]
    assert line["then"] == f"refused by validation ({whole})"
    assert line["outcome"] == "refused by validation"
    (drawn,) = [r for r in _csv(X.to_csv("calls", got, by=TEST_PERSON))
                if r["call"] == call["id"]]
    assert drawn["then"] == line["then"] and "characters:" not in drawn["then"]
    # The refusal's own record says the same words, whole.
    (row,) = F.refusals(NET)["rows"]
    assert row["call_id"] == call["id"]
    assert row["words"] == f"Refused by a protected flow: {whole}"


def _before_the_record(call_id: str) -> str:
    """A refused call as the parent release left it: the real call's row and use under a new
    id, the use's detail cut to 200 characters (`detail[:200]`, the parent's own cut), and no
    refusal record."""
    (row,) = [r for r in calls.read()["rows"] if r["id"] == call_id]
    (use,) = calls.uses()[call_id]
    old = calls.new_id()
    calls.record(dict({k: v for k, v in row.items() if k != "recorded"}, id=old))
    calls.record_use(old, use["use"], actor=use["actor"], detail=use["detail"][:200],
                     links=use["links"])
    return old


def test_a_refusal_made_before_records_were_kept_is_its_call_s_row_marked_cut(ui):  # noqa: F811
    _refused_policy(ui)
    (kept,) = F.refusals(NET)["rows"]
    old = _before_the_record(kept["call_id"])
    got = X.failures(NET, YESTERDAY, TODAY)
    assert got["ok"] and got["errors"] == []
    rows = [r for r in got["rows"] if r["kind"] == "protected_refusal"]
    assert sorted((r["source"], r["case"]) for r in rows) == sorted([
        ("sdn_refusals", kept["policy"]["id"]), ("ai_calls", old)]), \
        "the call a record names is that record's row, never a second one"
    (call_row,) = [r for r in rows if r["source"] == "ai_calls"]
    assert call_row["got"] == ("an AI call's answer: refused by the protected set, in the "
                               "words its use recorded")
    assert call_row["what"] == ("An AI call's answer, refused by validation: an SDN policy "
                                "drafted for Default")
    assert call_row["reason"].startswith("it would cover the protected flows dhcp (must_reach")
    assert call_row["reason"].endswith(
        " [200 characters: as long as the cut made when this was recorded, so its end may be "
        "missing]")
    assert call_row["record"] == f"/v2/history?call={old}&since="
    assert call_row["outcome"] == ("nothing sent; kept only as the call's use: it was made "
                                   "before a refusal was a record of its own")
    (line,) = [r for r in X.calls(NET, YESTERDAY, TODAY)["rows"] if r["call"] == old]
    assert line["then"].endswith("so its end may be missing])")
    assert [n for k, _w, n in got["counts"] if k == "protected_refusal"] == [2]


# ── a person's flow ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def planted(monkeypatch):
    """tests/test_protected.py's management class (192.0.2.0/24 and 2001:db8::/64) as the
    network's set; emptied or made unreadable by the test."""
    got = {"set": _pset()}
    monkeypatch.setattr(PR, "for_network", lambda network: got["set"])
    return got


def test_a_flow_preview_the_set_refuses_is_a_record_and_any_other_is_none(ops, planted):  # noqa: F811
    c, hexid = ops["client"], "0000000000000001"
    four = _flow(c, "eth_type=0x0800, ipv4_dst=192.0.2.9", dpid=hexid)
    six = _flow(c, "eth_type=0x86dd, ipv6_dst=2001:db8::9", dpid=hexid)
    lldp = _flow(c, "eth_type=0x88cc", dpid=hexid, actions="output:controller")
    assert [r.status_code for r in (four, six, lldp)] == [409, 409, 409]
    for r in (four, six, lldp):
        assert "This refusal is recorded in <a href=" in r.get_data(as_text=True)
    v4, v6, channel = F.refusals("Default")["rows"]
    assert {(r["what"], r["stage"], r["actor"], r["actor_verified"], r["dpid_hex"])
            for r in (v4, v6, channel)} == {("flow", "preview", TEST_PERSON, "access", hexid)}
    assert v4["refused_by"] == [{
        "guard": "class", "name": "management", "invariant": "untouchable",
        "source": "NetBox: m", "citation": "B, C2379",
        "met": ["eth_type 2048 meets the class's 2048",
                "ipv4_dst 192.0.2.9 meets the class's 192.0.2.0/24",
                "ipv4_src unset in the rule (so every ipv4_src) meets the class's "
                "192.0.2.0/24"]}]
    assert "ipv6_dst 2001:db8::9 meets the class's 2001:db8::/64" in v6["refused_by"][0]["met"]
    assert v6["asked"][0].startswith(f"Add a flow on {hexid}: table 0, priority 250, match ")
    assert "2001:db8::9" in v6["asked"][0]
    (by,) = channel["refused_by"]
    assert (by["guard"], by["name"], by["citation"]) == ("control_channel", "control channel",
                                                         "C2022, C2379")
    assert by["met"] == ["LLDP (EtherType 0x88cc), the controller's topology discovery"]
    assert channel["words"].endswith("(this is person's; C2022, C2379)")
    # A refusal that is not the protected set's, and a preview that passes, keep nothing:
    # the network's whole folder is byte for byte what it was.
    from modules.config import list_data_path

    def store():
        out = {}
        for base, _dirs, files in os.walk(list_data_path("Default")):
            for name in files:
                with open(os.path.join(base, name), "rb") as fh:
                    out[os.path.join(base, name)] = fh.read()
        return out

    before = store()
    planted["set"] = _pset([])
    unmet = _flow(c, "ipv4_dst=198.51.100.9", dpid=hexid)
    assert unmet.status_code == 409
    assert "This refusal" not in unmet.get_data(as_text=True)
    passed = _flow(c, "eth_type=0x0800, ipv4_dst=198.51.100.9", dpid=hexid)
    assert passed.status_code == 200, unescape(passed.get_data(as_text=True))[:300]
    assert store() == before and before, "neither wrote the store"
    assert len(F.refusals("Default")["rows"]) == 3 and ops["fake"].writes == []


def test_the_plan_writes_nothing_whoever_asks(ops, planted):  # noqa: F811
    """The record is the press's, never the plan's: a preview runs the real code, so a write
    in the plan would be every preview's, the closed loop's and the apply's own too."""
    ask = {"connection": CONN, "dpid": 1, "changes": [{"do": "add_flow", "flow": {
        "table_id": 0, "priority": 250, "cookie": F.new_cookie(), "actions": [],
        "match": {"eth_type": 0x0800, "ipv4_dst": "192.0.2.9"}}}]}
    p = O.plan("Default", ask)
    assert not p["ok"] and p["refused_by"][0]["name"] == "management"
    assert F.read("Default")["rows"] == [], "nothing was written"
    # AUTO's confirm refused is the response's own record (`auto_failed`), never a second one.
    auto = O.apply("Default", ask, "0" * 64, actor="Mercury: sdn-loop", mode="auto",
                   autonomous={"reason": "AUTO is on", "by": "op@example.com"})
    assert auto["outcome"] == "refused" and "refusal" not in auto
    assert F.read("Default")["rows"] == []
    # A confirm that reaches the apply as nobody verified (an installation whose confirm gate
    # is opened, as the kit's is) is refused the same, and keeps no record either.
    for kind in ("none", ""):
        theirs = O.apply("Default", ask, "0" * 64, actor="unverified", actor_verified=kind)
        assert theirs["outcome"] == "refused" and theirs["refusal"] == {
            "kept": False, "id": "", "unverified": True,
            "error": "a refusal's record is made for a verified person, and this request is "
                     "not one"}
    assert F.read("Default")["rows"] == []
    # A verified person's is kept, at its confirm.
    mine = O.apply("Default", ask, "0" * 64, actor="op@example.com", actor_verified="access")
    assert mine["outcome"] == "refused" and mine["refusal"]["kept"]
    (row,) = F.refusals("Default")["rows"]
    assert (row["what"], row["stage"], row["id"]) == ("flow", "confirm", mine["refusal"]["id"])
    assert ops["fake"].writes == []


def test_a_confirm_the_set_refuses_says_it_is_recorded(ops, planted):  # noqa: F811
    """The set moved between the preview and the confirm (a class NetBox gained): the
    confirm's card says the refusal is recorded, where it said "Not recorded: nothing reached
    the record"."""
    c, hexid = ops["client"], "0000000000000001"
    planted["set"] = _pset([])
    pv = _flow(c, "eth_type=0x0800, ipv4_dst=192.0.2.9", dpid=hexid)
    assert pv.status_code == 200, unescape(pv.get_data(as_text=True))[:300]
    planted["set"] = _pset()
    done = c.post("/v2/sdn/flow/confirm", data=form_fields(pv.get_data(as_text=True)))
    card = done.get_data(as_text=True)
    assert done.status_code == 409 and "Nothing was sent" in card
    assert "This refusal is recorded in <a href=" in card and "Not recorded" not in card
    (row,) = F.refusals("Default")["rows"]
    assert (row["stage"], row["actor"], row["actor_verified"]) == ("confirm", TEST_PERSON,
                                                                   "access")
    assert ops["fake"].writes == []


def test_a_record_that_cannot_be_kept_is_said_on_the_card_and_in_the_file(ops, planted,  # noqa: F811
                                                                         monkeypatch):
    def broken(network, row, check):
        raise OSError("the disk is full")

    real = F._append
    monkeypatch.setattr(F, "_append", broken)
    r = _flow(ops["client"], "eth_type=0x0800, ipv4_dst=192.0.2.9", dpid="0000000000000001")
    card = unescape(r.get_data(as_text=True))
    assert r.status_code == 409 and "meets the protected class management" in card
    assert "This refusal could not be recorded: OSError: the disk is full." in card
    assert "is recorded in" not in card
    monkeypatch.setattr(F, "_append", real)
    assert F.refusals("Default") == {"state": "absent", "rows": [], "error": ""}
    with open(F._path("Default"), "w", encoding="utf-8") as fh:
        fh.write("{not json\n")
    got = X.failures("Default", YESTERDAY, TODAY)
    assert got["ok"]
    assert any(e.startswith("Default's refusals by the protected set could not be read: ")
               for e in got["errors"]), got["errors"]


def test_a_refusal_s_text_is_masked_at_rest(networks):  # noqa: F811
    row = F.record_refusal(
        "Default", what="policy", stage="draft", actor="op@example.com",
        actor_verified="access", asked=[f"“block {PLANTED}”"], words=f"refused: {PLANTED}",
        refused_by=[PR.refused_by("class", "dns", invariant="must_reach dns",
                                  source=f"NetBox: {PLANTED}", met=[f"udp_dst 53 {PLANTED}"],
                                  citation=PR.CITATION)],
        policy={"id": "pol-x", "words": f"block {PLANTED}"})
    with open(F._path("Default"), encoding="utf-8") as fh:
        kept = fh.read()
    assert SECRET not in kept and SECRET not in json.dumps(row)
    assert "example.invalid" in kept, "what is not secret stays readable"
    with pytest.raises(F.IntentRefused, match="names what was refused"):
        F.record_refusal("Default", what="guess", stage="draft", actor="a", words="w",
                         actor_verified="access", refused_by=[{"name": "dns"}])
    with pytest.raises(F.IntentRefused, match="what of the protected set refused it"):
        F.record_refusal("Default", what="flow", stage="preview", actor="a", words="w",
                         actor_verified="access", refused_by=[])


# ── History › Export and History ────────────────────────────────────────────────────────────

def _auto_refusal(now):
    """AUTO's response refused by the real guard (the control channel), as the loop keeps it."""
    words = PR.flow_refusal({"state": "ok", "classes": []},
                            [{"do": "add_flow", "flow": {"match": {"eth_type": 0x88CC}}}],
                            1, {"url": "http://192.0.2.10:8080"}, writer="response")
    detection = {"key": "k8", "rule": "scan", "title": "SDN scan", "network": NET,
                 "connection": CONN, "dpid": OVS1, "dpid_hex": OVS1_HEX,
                 "source": "198.51.100.8", "targets": [],
                 "words": "198.51.100.8 reached 50 ports",
                 "subject": {"kind": "source", "value": "198.51.100.8"}}
    return LP.propose(NET, detection, "drop_source", "low", why="HITL", now=now,
                      auto_failed=f"AUTO could not preview drop_source: {words}")


def test_the_export_counts_each_kind_of_refusal_and_says_which(ui):  # noqa: F811
    """The sitting's day: AUTO's, a person's flow change and a policy. The parent counted the
    first alone."""
    _auto_refusal(time.time() - 60)
    assert _flow(ui.client, "eth_type=0x88cc", actions="output:controller").status_code == 409
    _refused_policy(ui)
    flow, policy = F.refusals(NET)["rows"]
    got = X.failures(NET, YESTERDAY, TODAY)
    assert got["ok"] and got["errors"] == []
    rows = [r for r in got["rows"] if r["kind"] == "protected_refusal"]
    assert [r["got"].split(":")[0] for r in rows] == [
        "AUTO's response", "a person's flow change", "a person's policy"]
    assert [r["source"] for r in rows] == ["sdn_responses", "sdn_refusals", "sdn_refusals"]
    assert {r["expected"] for r in rows} == {
        "no write that meets a protected flow class, a protected object or the control channel"}
    assert "1 protected-flow refusal" not in X.failures_words(got)
    assert "3 protected-flow refusals" in X.failures_words(got)
    auto, f, p = rows
    assert auto["got"] == "AUTO's response: refused by the protected set (C2022)"
    assert f["what"].startswith(f"A person's flow change on {OVS1_HEX}, refused at its "
                                f"preview: Add a flow on {OVS1_HEX}: table 0, priority 250, ")
    assert f["got"] == ("a person's flow change: refused by control channel (untouchable; "
                        "C2022, C2379)")
    assert (f["who"], f["case"]) == (TEST_PERSON, flow["id"])
    assert f["outcome"] == f"nothing sent; recorded ({flow['id']})"
    assert f["record"] == f"/v2/history?list=Default&kind=sdn&on={TODAY}&since="
    assert p["what"] == (f"A person's policy on {OVS1_HEX}, refused when it was drafted: "
                         f"“{SENTENCE}”; block h1 to any on udp")
    assert p["got"] == ("a person's policy: refused by dhcp (must_reach dhcp; B, C2379); dns "
                        f"(must_reach dns; B, C2379); drafted by AI call {policy['call_id']}")
    assert p["reason"] == policy["words"] and p["reason"].endswith(" alone")
    assert p["record"] == f"/v2/history?call={policy['call_id']}&since="
    assert p["case"] == policy["policy"]["id"]
    # The files: the same three rows, each field whole, and the page's count.
    drawn = [r for r in _csv(X.to_csv("failures", got, by=TEST_PERSON))
             if r["kind"] == "protected_refusal"]
    assert [(r["got"], r["reason"]) for r in drawn] == [(r["got"], r["reason"]) for r in rows]
    doc = json.loads(X.to_json("failures", got, by=TEST_PERSON))
    assert doc["counts"]["protected_refusal"] == 3
    assert "is here from the release that began keeping a record of each one" in doc[
        "not_recorded"]
    view = X.view(NET, YESTERDAY, TODAY, default=NET)
    assert ("protected-flow refusals", 3) in view["fail_counts"]
    assert X.failures("Branch", YESTERDAY, TODAY)["rows"] == [], "another network's rows"


def test_a_secret_in_a_refusal_never_leaves_in_the_file(networks):  # noqa: F811
    F.record_refusal("Default", what="flow", stage="preview", actor="op@example.com",
                     actor_verified="host-shell", asked=["Add a flow"], words="refused",
                     refused_by=[PR.refused_by("object", "eno9", citation=PR.CITATION)])
    # A row written before masking at rest would hold it: the file masks on the way out too.
    path = F._path("Default")
    with open(path, encoding="utf-8") as fh:
        line = json.loads(fh.read())
    line["words"] = f"refused: {PLANTED}"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")
    got = X.failures("Default", YESTERDAY, TODAY)
    (row,) = got["rows"]
    assert SECRET not in json.dumps(row) and "example.invalid" in row["reason"]
    assert row["who"] == "op@example.com (host login, not verified)", \
        "how they were established is said where it is no sign-in"
    assert SECRET not in X.to_csv("failures", got, by=TEST_PERSON)


def test_history_draws_each_refusal_as_an_sdn_row_with_who_and_how(ui, monkeypatch):  # noqa: F811
    from modules.nsot import listref

    assert _flow(ui.client, "eth_type=0x88cc", actions="output:controller").status_code == 409
    _refused_policy(ui)
    ctx = {"device": "", "ref": listref.resolve(NET), "limit": 50, "since": None,
           "until": None, "members": None}
    # This world's export is not committed in a repository, so no stored read names the
    # switch, and the row says so; with the name History's own reader gives, it is named.
    unnamed = H.sdn_operations(ctx)["events"][0]
    assert unnamed["what"] == ("Flow change refused by the protected set on a switch no stored "
                               "read names at its preview: nothing sent")
    monkeypatch.setattr(H, "_sdn_switch_names", lambda ref, rows: {OVS1_HEX: "ovs1"})
    events = H.sdn_operations(ctx)["events"]
    flow, policy = events
    assert H.sdn_operations(dict(ctx, device="arista-sw1"))["events"] == [], \
        "another switch's History tab"
    assert flow["what"] == "Flow change refused by the protected set on ovs1 at its preview: " \
                           "nothing sent"
    assert policy["what"] == ("Policy refused by the protected set on ovs1 when it was "
                              "drafted: nothing sent")
    assert {e["kind"] for e in events} == {"sdn"} and {e["outcome"] for e in events} == {
        "refused"}
    assert {e["who"] for e in events} == {TEST_PERSON}
    record = dict(policy["record"])
    assert record["Refused by"] == ("dhcp (must_reach dhcp; B, C2379); dns (must_reach dns; "
                                    "B, C2379)")
    assert record["Asked"] == f"“{SENTENCE}”; block h1 to any on udp"
    assert record["Verified by"] == "access" and record["AI call"].startswith("ai-")
    assert policy["detail"].startswith("Refused by a protected flow: it would cover")
    # A record is a verified person's: the store itself refuses one for nobody verified, so
    # no row can read "(not verified)"; one verified another way than the proxy's sign-in
    # says how, never a bare name (C3023's gap).
    by = [PR.refused_by("class", MGMT["name"], citation=PR.CITATION)]
    for kind in ("none", ""):
        with pytest.raises(F.IntentRefused, match="a refusal's record is made for a verified "
                                                  "person, and this request is not one"):
            F.record_refusal(NET, what="flow", stage="preview", actor="unverified",
                             actor_verified=kind, asked=["Add a flow"], words="refused",
                             dpid=OVS1, connection=CONN, refused_by=by)
    assert len(F.refusals(NET)["rows"]) == 2
    F.record_refusal(NET, what="flow", stage="preview", actor="kit-admin",
                     actor_verified="local-account", asked=["Add a flow"], words="refused",
                     dpid=OVS1, connection=CONN, refused_by=by)
    last = H.sdn_operations(ctx)["events"][-1]
    assert last["who"] == "kit-admin (local account, kit)"
    page = unescape(ui.client.get(f"/v2/history?list={NET}&kind=sdn").get_data(as_text=True))
    assert "Policy refused by the protected set on ovs1 when it was drafted: nothing sent" in page
    assert "Flow change refused by the protected set on ovs1 at its preview: nothing sent" in page


# ── who is recorded: the real identity layer ────────────────────────────────────────────────
#
# No access proxy is configured here, so nobody is identified unless the installation's one
# local account signs them in (tests/test_local_account.py's account and sign-in, as
# tests/test_heal_resubscribe_v2.py's "Who may confirm" and tests/test_kit_mode_walks.py use
# them): `me` is that account's browser, verified as ``local-account``; `nobody` is a browser
# with no session, whose requests `identity.actor_verification` answers ``none``. The previews
# are not gated, so both are answered; only `me`'s refusal is a record.

ACCOUNT = "lab-admin"
PW = "correct horse battery staple 42"
ORIGIN = {"Origin": "http://localhost"}
SIGN_IN = "/v2/settings/installation/local-account/sign-in"
NOT_RECORDED = ("This refusal is not recorded: a refusal's record is made for a verified "
                "person, and this request is not one. Sign in, and a refusal like this one is "
                "recorded in History.")
RECORDED = "This refusal is recorded in <a href="


def _people(monkeypatch):
    """``(me, nobody)``: the local account's three conditions (the setting, Mercury listening
    on loopback only, the account), `me` signed in through the real sign-in route."""
    import app as A
    from modules import config
    from modules import local_account as LA
    from modules.settings_schema import write_settings

    monkeypatch.setattr(config, "FLASK_HOST", "127.0.0.1")
    assert write_settings({LA.SETTING: True}, actor="test")["ok"]
    LA.set_password(ACCOUNT, PW)
    me, nobody = A.app.test_client(), A.app.test_client()
    r = me.post(SIGN_IN, data={"name": ACCOUNT, "password": PW}, headers=ORIGIN)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    assert 'data-identified="yes"' in me.get("/v2/who").get_data(as_text=True)
    assert 'data-identified="no"' in nobody.get("/v2/who").get_data(as_text=True)
    return me, nobody


def _store():
    """Every file of the test's whole data folder with its bytes (the networks' flow intent,
    the record of AI calls, the settings), to show a press wrote nothing."""
    from modules import config

    out = {}
    for base, _dirs, files in os.walk(config.DATA_DIR):
        for name in files:
            with open(os.path.join(base, name), "rb") as fh:
                out[os.path.join(base, name)] = fh.read()
    return out


def _unverified_then_verified(press, network, monkeypatch, *, what, stage):
    """*press*, a refused press of one recording route, made signed out and then signed in:
    signed out it is answered with the same refusal, the store byte for byte what it was, the
    card saying it is not recorded and why; signed in it is one record, the account's,
    verified as local-account."""
    me, nobody = _people(monkeypatch)
    before = _store()
    theirs = press(nobody)
    said = unescape(theirs.get_data(as_text=True))
    assert theirs.status_code == 409 and "Nothing was sent" in said, said[:400]
    assert NOT_RECORDED in said and RECORDED not in said, said[:600]
    assert "could not be recorded" not in said and 'role="alert">This refusal' not in said
    assert _store() == before and before, "an unverified press writes nothing"
    assert F.refusals(network)["rows"] == []
    mine = press(me)
    card = unescape(mine.get_data(as_text=True))
    assert mine.status_code == 409 and RECORDED in card and "not recorded" not in card
    (row,) = F.refusals(network)["rows"]
    assert (row["actor"], row["actor_verified"]) == (ACCOUNT, "local-account")
    assert (row["what"], row["stage"]) == (what, stage)
    return row


def _a_response_awaiting(now):
    """A scan's response awaiting a person, its drop of 192.0.2.1 inside the planted class."""
    from tests.test_protected import _detection

    return LP.propose("Default", _detection("192.0.2.1"), "drop_source", "low", why="HITL",
                      now=now)


def _a_lost_response(ops, planted):  # noqa: F811
    """tests/test_protected.py's lost response: a drop applied while the set held no class,
    then taken off the switch behind Mercury's back; its operation's id."""
    from modules.sdn import closed_loop as CL
    from tests.test_protected import _detection

    planted["set"] = _pset([])
    preview = CL.respond_to_threat("Default", _detection("192.0.2.1"), "drop_source")
    done = CL.respond_to_threat("Default", None, "drop_source", confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        actor_verified="access", sleep=lambda s: None)
    assert done["outcome"] == "verified", done["error"]
    cookie = json.loads(done["sent"][0]["request"]["body"])["cookie"]
    ops["fake"].table[1] = [f for f in ops["fake"].table[1] if f["cookie"] != cookie]
    planted["set"] = _pset()
    return done["id"]


@pytest.mark.real_identity
class TestWhoIsRecorded:
    def test_a_flow_s_preview(self, ops, planted, monkeypatch):  # noqa: F811
        row = _unverified_then_verified(
            lambda c: _flow(c, "eth_type=0x86dd, ipv6_dst=2001:db8::9", network="Default",
                            dpid="0000000000000001"),
            "Default", monkeypatch, what="flow", stage="preview")
        assert row["refused_by"][0]["name"] == "management" and ops["fake"].writes == []

    def test_a_response_s_preview(self, ops, planted, monkeypatch):  # noqa: F811
        one = _a_response_awaiting(time.time() - 60)
        row = _unverified_then_verified(
            lambda c: c.post(f"/v2/sdn/response/{one['id']}/preview", data={"list": "Default"}),
            "Default", monkeypatch, what="response", stage="preview")
        assert row["refused_by"][0]["name"] == "management" and ops["fake"].writes == []

    def test_a_re_apply_s_preview(self, ops, planted, monkeypatch):  # noqa: F811
        key = _a_lost_response(ops, planted)
        writes = list(ops["fake"].writes)
        row = _unverified_then_verified(
            lambda c: c.post("/v2/sdn/reapply/preview", data={
                "list": "Default", "connection": CONN, "dpid": "0000000000000001", "key": key}),
            "Default", monkeypatch, what="reapply", stage="preview")
        assert row["refused_by"][0]["name"] == "management" and ops["fake"].writes == writes

    def test_a_policy_s_check_again(self, ui, monkeypatch):  # noqa: F811
        policy = json.dumps({"id": "pol-x", "words": "limit all UDP from h1",
                             "rules": [rule("rate_limit", "h1", "any", "udp", rate=1000)]})
        row = _unverified_then_verified(
            lambda c: c.post("/v2/sdn/policies/check", data={
                "list": NET, "policy": policy, "instead_kind": "block"}),
            NET, monkeypatch, what="policy", stage="check")
        assert [b["name"] for b in row["refused_by"]] == ["dhcp", "dns"]
        assert row["policy"] == {"id": "pol-x", "words": "limit all UDP from h1"}
        assert ui.sent == [] and ui.fake.writes == []

    def test_a_policy_s_preview(self, ui, monkeypatch):  # noqa: F811
        policy = json.dumps({"id": "pol-y", "words": SENTENCE,
                             "rules": [rule("block", "h1", "any", "udp")]})
        row = _unverified_then_verified(
            lambda c: c.post("/v2/sdn/policies/preview", data={"list": NET, "policy": policy}),
            NET, monkeypatch, what="policy", stage="preview")
        assert [b["name"] for b in row["refused_by"]] == ["dhcp", "dns"]
        assert ui.sent == [] and ui.fake.writes == []

    def test_a_policy_s_draft(self, ui, monkeypatch):  # noqa: F811
        """The draft is an AI call a person starts: signed out it is refused at its gate,
        before any check, so no refusal by the protected set can be reached unverified."""
        me, nobody = _people(monkeypatch)
        ui.answer = answer(rule("block", "h1", "any", "udp"))
        before = _store()
        theirs = _draft_as(nobody)
        assert theirs.status_code == 403 and theirs.get_json()["requires_identity"] is True
        assert _store() == before and ui.sent == [], "nothing asked, nothing written"
        mine = _draft_as(me)
        said = unescape(mine.get_data(as_text=True))
        assert mine.status_code == 409 and RECORDED in said, said[:600]
        (row,) = F.refusals(NET)["rows"]
        assert (row["actor"], row["actor_verified"]) == (ACCOUNT, "local-account")
        assert (row["what"], row["stage"]) == ("policy", "draft") and len(ui.sent) == 1
        from modules.nsot import listref
        (event,) = H.sdn_operations({"device": "", "ref": listref.resolve(NET), "limit": 50,
                                     "since": None, "until": None, "members": None})["events"]
        assert event["who"] == f"{ACCOUNT} (local account, kit)"

    def test_a_confirm_reached_unverified_is_refused_and_not_recorded(self, ops, planted,  # noqa: F811
                                                                      monkeypatch):
        """Where an installation opens its confirm gate (the kit's identity exception), a
        confirm reaches the apply as nobody verified: the protected set refuses it as it
        refuses anyone's, the card says it is not recorded, and nothing is written."""
        from modules import identity

        me, nobody = _people(monkeypatch)
        real = identity._setting
        monkeypatch.setattr(identity, "_setting", lambda key, default=None: (
            False if key == "require_identity_for_confirm" else real(key, default)))
        planted["set"] = _pset([])
        pv = _flow(nobody, "eth_type=0x0800, ipv4_dst=192.0.2.9", network="Default",
                   dpid="0000000000000001")
        assert pv.status_code == 200, unescape(pv.get_data(as_text=True))[:300]
        planted["set"] = _pset()
        before = _store()
        form = form_fields(pv.get_data(as_text=True))
        done = nobody.post("/v2/sdn/flow/confirm", data=form)
        card = unescape(done.get_data(as_text=True))
        assert done.status_code == 409 and "Nothing was sent" in card, card[:400]
        assert NOT_RECORDED in card and RECORDED not in card
        assert _store() == before and ops["fake"].writes == []
        mine = me.post("/v2/sdn/flow/confirm", data=form)
        assert RECORDED in mine.get_data(as_text=True)
        (row,) = F.refusals("Default")["rows"]
        assert (row["actor"], row["actor_verified"], row["stage"]) == (
            ACCOUNT, "local-account", "confirm")


def _draft_as(client):
    return client.post("/v2/sdn/policies/draft", data={"list": NET, "words": SENTENCE})
