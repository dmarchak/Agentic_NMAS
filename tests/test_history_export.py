"""History › Export (Lab 9 B5; modules/history_export.py; board H of docs/boards/lab9-sdn.html):
the call and cost log and the false-positive and failure log, each as CSV and JSON.

The records are made by their own writers: AI calls through the real gateway (SDN › Flows'
analyst, `tests/test_sdn_analyst.py`'s world: hosted AI allowed, a key, a fake provider) and the
ledger's own `calls.record` for a background job's call and an evaluation's; SDN responses by
`loop.propose` and `loop.resolve`, the protected refusal in the real guard's words; flow
operations by the real `flow_ops.apply` over `tests/test_sdn_flow_ops.py`'s fake Ryu (a write
the switch ignored, so Verify fails; a write the controller refused); a planted issue missed by a
real analysis; an answer said wrong by `feedback.say` and its review.

- **Calls:** every call in the range, one row each, oldest first, with its trigger (a person, a
  background job), outcome (ok, refused by validation, refused at a cap), tokens, dollars and
  History link; a total per UTC day and per feature; the dollars the ledger's, summed by day.
  One network's log holds the calls that name it; the others are counted, never dropped unsaid.
- **Failures:** each source its row, kind, reason, who and record link; a protected refusal
  named as one; what a rollback achieved; the network's own rows only on its log.
- **Bounded:** 31 days a range, 32 refused naming its length, on the page and the download.
- **Masked:** a secret planted in a call's text and a dismissal's reason never leaves.
- **Files:** each opens with its log, range, network, when and who.
- **Reads only:** the page and every download write nothing.
- **The page:** History links it; an empty range says so; IPv4 and IPv6 addresses kept whole.
"""
import csv
import io
import json
import os
import time

import pytest

from modules import history_export as X
from modules.ai import calls
from modules.sdn import loop as LP
from tests.ai_person import PERSON, pressed_by
from tests.test_device_v2 import _get, lab  # noqa: F401 (the fixture)
from tests.test_sdn_analyst import (OVS3, analyse, answer, finding, snap_of,  # noqa: F401
                                    world)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)
from tests.test_sdn_flow_ops import ask, ctl, drop, run  # noqa: F401 (the fixture)

NET = "Default"
URL_SECRET = "SeCrEt-Tok3n"
PLANTED = f"fatal: https://x-access-token:{URL_SECRET}@example.invalid/o/r.git denied"


def _day(offset=0):
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + offset * 86400))


TODAY, YESTERDAY = _day(), _day(-1)


def _stamp(day, hms):
    return f"{day}T{hms}Z"


def _background_call(day, *, cost=0.002, verdict="ok", network="default", detail=""):
    """A background job's call as the gateway records it (`gateway._prepared` and `_received`'s
    fields), through the ledger's own writer."""
    return calls.record({
        "id": calls.new_id(), "at": _stamp(day, "10:00:00"), "feature": "sdn_classify",
        "actor": "job:sdn-loop-default-1", "model": "claude-haiku-5-5",
        "prompt": "sdn_classify.v3", "schema": "sdn_classify.v3", "detail": detail,
        "cost_usd": cost, "subject": {"kind": "sdn_detection", "id": "k1", "rule": "scan",
                                      "devices": []},
        "trigger": {"kind": "background", "feature": "sdn_classify",
                    "job": "sdn-loop-default-1", "network": network,
                    "finding": {"kind": "detection", "id": "k1"}},
        "tokens": {"input_tokens": 1000, "output_tokens": 50, "cache_read_input_tokens": 200,
                   "cache_creation_input_tokens": 0},
        "latency_s": 1.5, "verdict": verdict})


def _analyst_calls(world):  # noqa: F811
    """Three of the analyst's calls as a person, through the real gateway: one answered, one
    whose answer is not its schema (refused by validation), one refused at the day cap."""
    from modules.settings_schema import write_settings

    snap = snap_of(world)
    world.answer = answer(finding([f"port:ctl-1:{OVS3}:3"]))
    ok = analyse(world, snap)
    world.raw = "the network looks fine"
    bad = analyse(world, snap)
    world.raw = None
    assert write_settings({"ai_cap_usd_per_day": 0.0001})["ok"]
    capped = analyse(world, snap)
    assert write_settings({"ai_cap_usd_per_day": 1.50})["ok"]
    assert ok["ok"] and bad["error"] == "schema" and capped["error"] == "over_cap"
    return ok, bad, capped


def _rows(text):
    return list(csv.reader(io.StringIO(text)))


# ── the call and cost log ───────────────────────────────────────────────────────────────────

def test_every_call_is_a_row_with_its_trigger_outcome_and_link(world):  # noqa: F811
    bg = _background_call(YESTERDAY)
    ok, bad, capped = _analyst_calls(world)
    got = X.calls(X.EVERY, YESTERDAY, TODAY)
    assert got["ok"] and got["cut"] == 0
    by = {r["call"]: r for r in got["rows"]}
    assert [r["call"] for r in got["rows"]] == [bg["id"], ok["call_id"], bad["call_id"],
                                                capped["call_id"]]
    b = by[bg["id"]]
    assert (b["trigger"], b["network"], b["outcome"], b["day"]) == (
        "background", "default", "ok", YESTERDAY)
    assert b["by"] == "job sdn-loop-default-1 (sdn_classify, finding detection k1)"
    assert (b["tokens_in"], b["tokens_out"], b["cache_read"], b["usd"]) == (1000, 50, 200, 0.002)
    assert b["link"] == f"/v2/history?call={bg['id']}&since="
    a = by[ok["call_id"]]
    assert (a["trigger"], a["by"], a["feature"], a["model"], a["prompt"]) == (
        "person", PERSON, "sdn_analyse", "claude-haiku-5-5", "sdn_analyse.v1")
    # C2942: a person's call records the network it names, so it is listed under it.
    assert a["network"] == "default" and a["outcome"] == "ok" and a["usd"] > 0
    assert a["then"].startswith("shown: 1 findings")
    assert by[bad["call_id"]]["outcome"] == "refused by validation"
    assert by[bad["call_id"]]["verdict"] == "schema" and by[bad["call_id"]]["tokens_in"] == 6000
    assert by[capped["call_id"]]["outcome"] == "refused at a cap"
    # The ledger's own figures, summed by UTC day: the state, read again here.
    ledger = {r["id"]: float(r.get("cost_usd") or 0) for r in calls.read()["rows"]}
    assert got["summary"]["usd"] == pytest.approx(sum(ledger.values()))
    days = {d["day"]: d for d in got["by_day"]}
    assert set(days) == {YESTERDAY, TODAY}
    assert days[YESTERDAY]["calls"] == 1 and days[YESTERDAY]["usd"] == pytest.approx(0.002)
    assert days[TODAY]["calls"] == 3 and days[TODAY]["validation"] == 1
    assert days[TODAY]["cap"] == 1 and days[TODAY]["ok"] == 1
    feats = {f["feature"]: f for f in got["by_feature"]}
    assert feats["sdn_analyse"]["calls"] == 3 and feats["sdn_classify"]["calls"] == 1
    s = got["summary"]
    assert (s["calls"], s["ok"], s["validation"], s["cap"]) == (4, 2, 1, 1)
    assert X.calls_words(s) == (f"4 calls · ${s['usd']:.4f} · 1 refused by validation · "
                                "1 refused at a cap")


def test_one_network_s_log_holds_its_calls_and_counts_the_rest(world):  # noqa: F811
    bg = _background_call(TODAY)
    branch = _background_call(TODAY, network="branch")
    ok, bad, capped = _analyst_calls(world)
    got = X.calls(NET, YESTERDAY, TODAY)
    # C2942: the person's three calls name Default, answered or refused, so they are its own.
    assert sorted(r["call"] for r in got["rows"]) == sorted(
        [bg["id"], ok["call_id"], bad["call_id"], capped["call_id"]])
    assert [r["call"] for r in X.calls("Branch", YESTERDAY, TODAY)["rows"]] == [branch["id"]]
    assert X.calls(X.EVERY, YESTERDAY, TODAY)["unattributed"] == 0
    assert len(calls.read()["rows"]) == 5


def test_a_range_past_31_days_is_refused_naming_its_length(world):  # noqa: F811
    _background_call(TODAY)
    long = X.calls(X.EVERY, _day(-31), TODAY)
    assert not long["ok"] and long["rows"] == []
    assert f"the range {_day(-31)} to {TODAY} is 32 days" in long["error"]
    assert "at most 31" in long["error"]
    assert X.calls(X.EVERY, _day(-30), TODAY)["ok"]
    assert "is after To" in X.failures(X.EVERY, TODAY, YESTERDAY)["error"]
    assert "is not a day" in X.calls(X.EVERY, "2026-13-01", TODAY)["error"]
    assert len(calls.read()["rows"]) == 1


def test_a_file_past_its_cap_says_how_many_it_left_out(world, monkeypatch):  # noqa: F811
    for _ in range(3):
        _background_call(TODAY, cost=0.001)
    monkeypatch.setattr(X, "MAX_ROWS", 2)
    got = X.calls(X.EVERY, TODAY, TODAY)
    assert len(got["rows"]) == 2 and got["cut"] == 1 and got["summary"]["calls"] == 3
    text = X.to_csv("calls", got, by=PERSON)
    assert ["# rows left out", "1 past the first 2; the totals count every row in the range"] \
        in _rows(text)
    assert len(calls.read()["rows"]) == 3


# ── the false-positive and failure log ──────────────────────────────────────────────────────

def _detection(key, source, words):
    return {"key": key, "rule": "scan", "title": "SDN scan", "network": NET,
            "connection": "lab", "dpid": 1, "dpid_hex": "0000000000000001", "source": source,
            "targets": [], "words": words, "subject": {"kind": "source", "value": source}}


def _protected_words():
    """The guard's own refusal of a response covering the control channel (C2022)."""
    from modules import protected

    return protected.flow_refusal({"state": "ok", "classes": []},
                                  [{"do": "add_flow", "flow": {"match": {"eth_type": 0x88CC}}}],
                                  1, {"url": "http://192.0.2.10:8080"}, writer="response")


def _responses(now):
    one = LP.propose(NET, _detection("k4", "192.0.2.66", "192.0.2.66 reached 25 ports"),
                     "drop_source", "low", why="HITL", now=now)
    LP.resolve(NET, one["id"], "dismissed", actor="op@example.com",
               why="normal traffic: the nightly backup", now=now + 1)
    two = LP.propose(NET, _detection("k6", "2001:db8::66", "2001:db8::66 reached 30 ports"),
                     "drop_source", "low", why="HITL", now=now + 2)
    LP.resolve(NET, two["id"], "dismissed", actor="op@example.com",
               why="normal traffic: the nightly backup", now=now + 3)
    refused = LP.propose(NET, _detection("k7", "198.51.100.7", "198.51.100.7 reached 40 ports"),
                         "drop_source", "low", why="HITL", now=now + 4,
                         classified="AI classification refused: it cited evidence the pack "
                                    "does not hold",
                         refused_call="ai-0123456789abcdef")
    guarded = LP.propose(NET, _detection("k8", "198.51.100.8", "198.51.100.8 reached 50 ports"),
                         "drop_source", "low", why="HITL", now=now + 5,
                         auto_failed=f"AUTO could not preview drop_source: {_protected_words()}")
    other = LP.propose(NET, _detection("k9", "198.51.100.9", "198.51.100.9 reached 60 ports"),
                       "drop_source", "low", why="HITL", now=now + 6,
                       auto_failed="AUTO could not preview drop_source: the controller did "
                                   "not answer")
    return one, two, refused, guarded, other


def test_every_dismissal_refusal_and_auto_failure_is_a_row(world):  # noqa: F811
    now = time.time() - 60
    one, two, refused, guarded, other = _responses(now)
    got = X.failures(NET, YESTERDAY, TODAY)
    assert got["ok"] and got["errors"] == []
    kinds = [(r["kind"], r["outcome"].rsplit("(", 1)[-1].rstrip(")")) for r in got["rows"]]
    assert kinds == [("dismissed", one["id"]), ("dismissed", two["id"]),
                     ("classification_refused", refused["id"]),
                     ("protected_refusal", guarded["id"]), ("auto_failed", other["id"])]
    d4, d6, c, p, a = got["rows"]
    assert d4["what"] == "SDN scan on 0000000000000001: 192.0.2.66 reached 25 ports"
    assert d6["what"] == "SDN scan on 0000000000000001: 2001:db8::66 reached 30 ports"
    assert (d4["reason"], d4["who"]) == ("normal traffic: the nightly backup", "op@example.com")
    assert d4["record"] == "/v2/sdn/responses?list=Default"
    assert c["got"] == "AI call ai-0123456789abcdef"
    assert c["record"] == "/v2/history?call=ai-0123456789abcdef&since="
    assert "the control channel" in p["reason"] and p["who"] == "AUTO"
    assert a["reason"].endswith("the controller did not answer")
    assert X.failures_words(got) == (
        "2 SDN detections dismissed (2 “normal traffic: the nightly backup”) · "
        "1 classification refused by the check · 1 protected-flow refusal · "
        "1 response AUTO could not send")
    assert X.failures("Branch", YESTERDAY, TODAY)["rows"] == [], "another network's rows"
    assert len(LP.responses_record(NET)["rows"]) == 7


def test_a_failed_verify_and_a_refused_request_say_what_the_rollback_achieved(ctl):  # noqa: F811
    ctl.ignore = {"/stats/flowentry/add"}
    _p, ignored = run(ctl, ask(drop(src="192.0.2.77")))
    ctl.ignore, ctl.fail = set(), {"/stats/flowentry/add": 400}
    six = drop()
    six["flow"]["match"] = {"eth_type": 0x86DD, "ipv6_src": "2001:db8::77"}
    _p, refused = run(ctl, ask(six))
    assert ignored["outcome"] == refused["outcome"] == "rolled_back"
    got = X.failures(NET, YESTERDAY, TODAY)
    v, s = got["rows"]
    assert (v["kind"], v["case"]) == ("verify_failed", ignored["id"])
    assert v["reason"].startswith("Verify failed: no flow with cookie")
    assert v["outcome"] == ("rolled back: 1 of 1 undo request sent, 1 of 1 read back as before")
    assert v["who"] == "op@example.com" and "192.0.2.77" in v["what"]
    assert v["record"] == f"/v2/history?list=Default&kind=sdn&on={TODAY}&since="
    assert (s["kind"], s["case"]) == ("send_failed", refused["id"])
    assert "the controller refused request 1 of 1" in s["reason"]
    assert s["outcome"].startswith("rolled back: no rollback: nothing had landed")
    assert "2001:db8::77" in s["what"]
    assert X.failures(X.EVERY, YESTERDAY, TODAY)["rows"] == got["rows"]


def test_a_planted_miss_an_evaluation_false_positive_and_an_answer_said_wrong(world):  # noqa: F811
    from modules.ai import feedback
    from modules.sdn import analyst as AN

    snap = snap_of(world)
    assert AN.add_planted(NET, "A stale drop", f"drop:ctl-1:{OVS3}:*", actor=PERSON,
                          why="its count is zero")["ok"]
    world.answer = answer(finding([f"port:ctl-1:{OVS3}:3"]))
    ok = analyse(world, snap)
    fp = calls.record({
        "id": calls.new_id(), "feature": "sdn_classify", "actor": "evaluation:normal-1",
        "model": "claude-haiku-5-5", "prompt": "sdn_classify.v3", "cost_usd": 0.001,
        "subject": {"kind": "sdn_collection", "id": "2026-11-09T10:00:00Z", "rule": "",
                    "devices": []},
        "trigger": {"kind": "evaluation", "run": "normal-1"},
        "tokens": {"input_tokens": 900, "output_tokens": 40}, "verdict": "ok",
        "output": {"threat_detected": True, "threat_type": "port_scan", "severity": "low",
                   "reasoning": "many ports from 192.0.2.5"}})
    with pressed_by(PERSON):
        said = feedback.say(ok["call_id"], feedback.NO, why="missed",
                            words="it missed the stale drop flow on switch three")
        feedback.review(said["id"], feedback.DISMISSED,
                        reason="the drop was planted after the collection ran")
    got = X.failures(X.EVERY, YESTERDAY, TODAY)
    by = {r["kind"]: r for r in got["rows"]}
    assert set(by) == {"planted_missed", "evaluation_miss", "answer_wrong"}
    m = by["planted_missed"]
    assert (m["case"], m["got"], m["reason"]) == ("A stale drop", "missed", "its count is zero")
    assert m["expected"] == f"found by evidence drop:ctl-1:{OVS3}:*"
    assert m["outcome"] == f"missed by analysis {ok['id']}"
    e = by["evaluation_miss"]
    assert (e["case"], e["got"], e["who"]) == ("2026-11-09T10:00:00Z", "port_scan, severity low",
                                               "run normal-1")
    assert e["record"] == f"/v2/history?call={fp['id']}&since="
    w = by["answer_wrong"]
    assert w["reason"] == "it missed the stale drop flow on switch three"
    assert w["outcome"].startswith(f"dismissed by {PERSON} at ")
    assert w["outcome"].endswith(": the drop was planted after the collection ran")
    assert w["record"] == f"/v2/history?call={ok['call_id']}&since="
    # C2942: the answer said wrong was a person's call naming Default, so it is Default's too.
    assert [r["kind"] for r in X.failures(NET, YESTERDAY, TODAY)["rows"]] == [
        "planted_missed", "answer_wrong"]
    assert len(feedback.read()["rows"]) == 2


def test_a_store_that_cannot_be_read_is_said_never_a_shorter_log(world):  # noqa: F811
    from modules.config import list_data_path

    path = os.path.join(list_data_path(NET), LP.PENDING_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json\n")
    got = X.failures(NET, YESTERDAY, TODAY)
    assert got["ok"] and any(e.startswith("Default's SDN responses could not be read")
                             for e in got["errors"])
    text = X.to_csv("failures", got, by=PERSON)
    assert any(r[0] == "# could not read" for r in _rows(text))
    assert LP.responses_record(NET)["state"] == "unreadable"


# ── masking, and the files' first lines ─────────────────────────────────────────────────────

def test_a_secret_planted_in_a_call_and_a_reason_never_leaves(world):  # noqa: F811
    _background_call(TODAY, verdict="exception", detail=PLANTED)
    one = LP.propose(NET, _detection("k4", "192.0.2.66", "192.0.2.66 reached 25 ports"),
                     "drop_source", "low", why="HITL", now=time.time() - 30)
    LP.resolve(NET, one["id"], "dismissed", actor="op@example.com", why=PLANTED,
               now=time.time() - 20)
    assert any(URL_SECRET in (r.get("detail") or "") for r in calls.read()["rows"]), \
        "the premise: the ledger holds it as the test planted it"
    for kind in ("calls", "failures"):
        for fmt in ("csv", "json"):
            got = X.download(kind, fmt, X.EVERY, YESTERDAY, TODAY, by=PERSON, default=NET)
            assert got["ok"], got
            assert URL_SECRET not in got["body"], (kind, fmt)
            assert "<redacted:url_userinfo>@example.invalid" in got["body"], (kind, fmt)


def test_each_file_opens_with_its_log_range_network_and_who_made_it(world):  # noqa: F811
    _background_call(TODAY)
    now = time.time()
    made = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    c = X.download("calls", "csv", NET, YESTERDAY, TODAY, by=PERSON, default=NET, now=now)
    head = _rows(c["body"])[:5]
    assert head == [["# log", "Mercury: AI calls and cost"],
                    ["# range", YESTERDAY, TODAY, "2 whole UTC days, inclusive"],
                    ["# network", NET], ["# made", made, "by", PERSON],
                    ["# amounts", X.AMOUNTS]]
    assert c["filename"] == f"mercury-ai-calls-Default-{YESTERDAY}-to-{TODAY}.csv"
    f = X.download("failures", "json", X.EVERY, YESTERDAY, TODAY, by=PERSON, default=NET,
                   now=now)
    lines = f["body"].splitlines()
    assert lines[:3] == ['{', ' "log": "Mercury: false positives and failures",',
                         ' "range": {']
    doc = json.loads(f["body"])
    assert (doc["range"]["from"], doc["range"]["to"], doc["network"], doc["made_at"],
            doc["made_by"]) == (YESTERDAY, TODAY, "every network", made, PERSON)
    assert doc["not_recorded"] == X.NOT_RECORDED and doc["rows"] == []
    j = json.loads(X.download("calls", "json", NET, YESTERDAY, TODAY, by=PERSON,
                              default=NET, now=now)["body"])
    assert list(j)[:5] == ["log", "range", "network", "made_at", "made_by"]
    assert j["summary"]["calls"] == 1 and j["by_day"][0]["day"] == TODAY
    assert len(calls.read()["rows"]) == 1


def test_an_unknown_log_format_or_network_is_refused_naming_it(world):  # noqa: F811
    assert "the logs are calls and failures" in X.download(
        "spend", "csv", NET, "", "", by=PERSON, default=NET)["error"]
    assert "a log downloads as csv or json" in X.download(
        "calls", "xlsx", NET, "", "", by=PERSON, default=NET)["error"]
    assert "there is no network named 'Nowhere'" in X.download(
        "calls", "csv", "Nowhere", "", "", by=PERSON, default=NET)["error"]
    assert calls.read()["state"] == "absent"


# ── the page and its downloads ──────────────────────────────────────────────────────────────

def _tree(root):
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            p = os.path.join(base, name)
            st = os.stat(p)
            out[p] = (st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture
def page(lab, tmp_path, monkeypatch):  # noqa: F811
    """The lab's app with its record of AI calls in the test's folder: a person's call and a
    background job's on Lab, both today."""
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ledger" / "ai_calls.jsonl"))
    os.makedirs(tmp_path / "ledger")
    calls.record({"id": calls.new_id(), "feature": "explain", "actor": PERSON,
                  "model": "claude-sonnet-5-5", "prompt": "explain.v4", "cost_usd": 0.01,
                  "trigger": {"kind": "person", "by": PERSON}, "verdict": "ok",
                  "tokens": {"input_tokens": 4000, "output_tokens": 300}})
    _background_call(TODAY, network="lab")
    lab["root"] = str(tmp_path)
    return lab


def test_history_links_the_export_and_the_export_its_four_downloads(page):
    _r, html = _get(page, "/v2/history")
    # The page's network is written into every address it draws (routes/page_network).
    assert 'href="/v2/history?tab=export&amp;list=Lab"' in html
    r, html = _get(page, "/v2/history?tab=export")
    assert r.status_code == 200 and "AI calls and cost" in html
    q = f"network=Lab&amp;start={_day(-6)}&amp;end={TODAY}&amp;list=Lab"
    for kind in ("calls", "failures"):
        for fmt in ("csv", "json"):
            assert f'href="/v2/history/export/{kind}/{fmt}?{q}"' in html, (kind, fmt)
    stored = calls.read()["rows"]
    drawn = X.calls_words(X.calls("Lab", _day(-6), TODAY)["summary"])
    assert drawn.startswith("1 call · ") and drawn in html
    assert len(stored) == 2


def test_every_network_draws_every_call_and_a_download_is_the_file(page):
    _r, html = _get(page, f"/v2/history?tab=export&network=*&start={TODAY}&end={TODAY}")
    assert "2 calls · $0.0120" in html
    r = page["client"].get(f"/v2/history/export/calls/csv?network=*&start={TODAY}&end={TODAY}")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert r.headers["Content-Disposition"] == (
        f'attachment; filename="mercury-ai-calls-every_network-{TODAY}-to-{TODAY}.csv"')
    rows = _rows(r.get_data(as_text=True))
    assert rows[2] == ["# network", "every network"]
    header = rows.index(list(X.CALL_COLUMNS))
    listed = {row[2] for row in rows[header + 1:header + 3]}
    stored = calls.read()["rows"]
    assert listed == {r["id"] for r in stored} and len(stored) == 2


def test_a_range_past_31_days_is_refused_on_the_page_and_the_download(page):
    start = _day(-40)
    _r, html = _get(page, f"/v2/history?tab=export&start={start}&end={TODAY}")
    assert f"Not shown: the range {start} to {TODAY} is 41 days" in html
    r = page["client"].get(f"/v2/history/export/failures/json?start={start}&end={TODAY}")
    assert r.status_code == 400 and "is 41 days" in r.get_data(as_text=True)
    assert len(calls.read()["rows"]) == 2


def test_an_empty_range_says_so_and_its_file_says_none(page):
    _r, html = _get(page, "/v2/history?tab=export&start=2020-01-01&end=2020-01-07")
    assert "Nothing in the range: no AI call, and no false positive or failure, on Lab from " \
           "2020-01-01 to 2020-01-07 (UTC)" in html
    r = page["client"].get("/v2/history/export/calls/csv?start=2020-01-01&end=2020-01-07")
    rows = _rows(r.get_data(as_text=True))
    assert ["# in the range", "0 calls · $0.0000"] in rows
    assert rows[rows.index(list(X.CALL_COLUMNS)) + 1] == []
    assert X.calls("Lab", "2020-01-01", "2020-01-07")["rows"] == []


def test_the_page_and_every_download_write_nothing(page):
    before = _tree(page["root"])
    q = f"network=*&start={YESTERDAY}&end={TODAY}"
    assert _get(page, f"/v2/history?tab=export&{q}")[0].status_code == 200
    for kind in ("calls", "failures"):
        for fmt in ("csv", "json"):
            assert page["client"].get(f"/v2/history/export/{kind}/{fmt}?{q}").status_code == 200
    assert _tree(page["root"]) == before
