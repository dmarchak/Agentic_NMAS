"""The read loop's send log, and its rows on History (board H, part H26; docs/HEAL_TO_INTENT.md
19.5: "Every send is logged ... in History's AI calls (15.14), beside the reads run it came
from"; "Between the two passes, each read request is a row, linked to both"; artboard M;
`modules/ai/read_log.py`, `read_loop.run`, `history_sources.ai_reads`), on test_ai_read_loop's
planted family and fake gateway, and through the real gateway with only the provider faked: no
provider, no device.

- **Every request is logged, and every answer to be sent BEFORE pass 2 is asked:** the
  incident, the device, the command as matched, the egress class, the verdict and the reason,
  the read's run on History › Reads and whom it signed in as, and the answer's bytes and sha256
  as sent (equal to the bytes pass 2 carried) and whole; never the answer's text.
- **Nothing is sent unlogged:** a log that cannot be written asks no pass 2, said.
- **Pass 2's outcome is logged:** whether its request left the host (an answer and a provider
  failure yes; a cap, a feature off, no) and its call; a ``reads`` row with no ``sent`` row
  reads as possibly sent.
- **Through the real gateway:** the logged sha256 is the sha256 of the bytes inside the body
  the provider was sent.
- **History:** each request one row, kind ``ai_read``, under the AI calls filter, with its
  incident, linked to both calls and its read on History › Reads, a refusal drawn danger with
  its reason, no answer text; a device's tab shows the reads of it; another network's rows are
  not drawn.
- **History › Reads draws whom a read signed in as** (C2661): the read-only account's name and
  its profile, never a password.
"""
import hashlib
import json
import re
import types

import pytest

from modules import history_sources as HS
from modules.ai import read_log
from modules.ai import read_loop as RL
from tests.test_ai_gateway import own_record, world  # noqa: F401 (fixtures)
from tests.test_ai_read_loop import (DPID1, DPID2, FEATURE, FakeGateway, Runner, _ask,  # noqa: F401
                                     _family, _first, _real, _run, _second, class_on,
                                     registered)

#: A read's answer, distinctive enough that any byte of it in the log is found.
ANSWER = "table 0 priority 10 ipv4_src=192.0.2.5 packets 9001 planted-answer-text"
INCIDENT = {"kind": "heal_incident", "id": "hi-5be1c0", "devices": ["edge1"]}


def _loop(gw, **kw):
    runner = Runner({"switch_flows": ANSWER, "port_stats": "port 3 rx 5000 pps"})
    spec = dict(family=_family(run=runner), subject=INCIDENT,
                trigger={"kind": "background", "feature": "heal_analysis", "job": "hj-1",
                         "network": "lab"})
    spec.update(kw)
    return _run(gw, **spec)


def _rows(kind=None):
    rows = read_log.read()["rows"]
    return [r for r in rows if kind is None or r["row"] == kind]


class Watching(FakeGateway):
    """The fake gateway, keeping what the send log held when each call was asked."""

    def __init__(self, *answers):
        super().__init__(*answers)
        self.logged_at_ask = []

    def ask(self, task, prompt, schema, parts, **kw):
        self.logged_at_ask.append([dict(r) for r in _rows()])
        return super().ask(task, prompt, schema, parts, **kw)


# ── The log ───────────────────────────────────────────────────────────────────────────────────

def test_every_request_is_logged_before_pass_2_its_sizes_and_digests_never_its_text():
    gw = Watching(_first(_ask("switch_flows", dpid=DPID1, host="192.0.2.5"),
                         _ask("port_stats", dpid=DPID1, port=True),
                         _ask("port_stats", dpid=DPID2, port=3)),
                  _second(cites=("pack:1", "read:1", "read:3")))
    got = _loop(gw)
    assert got["state"] == "answered" and got["pass"] == 2 and got["logged"] is True
    assert gw.logged_at_ask[0] == [], "nothing is logged before pass 1"
    (before,) = gw.logged_at_ask[1]
    assert before["row"] == "reads" and before["loop"] == got["loop"], \
        "the reads row is written before pass 2 is asked"
    (row,) = _rows("reads")
    assert row["subject"] == INCIDENT and row["network"] == "lab"
    assert row["first_call"] == "call-1" and row["task"] == FEATURE.task
    assert row["trigger"] == {"kind": "background", "feature": "heal_analysis", "job": "hj-1",
                              "network": "lab"}
    one, two, three = row["reads"]
    assert (one["id"], one["op"], one["verdict"]) == ("read:1", "switch_flows", "run")
    assert one["commands"] == [f"GET /stats/flow/{DPID1}"]
    assert one["egress_class"] == "device_state"
    # The bytes and digest sent are those pass 2 carried for that read.
    sent = {r["id"]: r for r in json.loads(gw.calls[1]["parts"]["mercury_reads"])}
    carried = sent["read:1"]["answer"].encode("utf-8")
    assert one["sent_bytes"] == len(carried) and one["sent_sha256"] == \
        hashlib.sha256(carried).hexdigest()
    assert one["bytes"] == len(ANSWER.encode()) and one["sha256"] == \
        hashlib.sha256(ANSWER.encode()).hexdigest()
    assert (one["cut"], one["withheld"]) == (False, 0)
    assert two["verdict"] == "refused" and "True is a true/false value" in two["reason"]
    assert "sent_bytes" not in two and "sha256" not in two
    assert three["commands"] == [f"GET /stats/port/{DPID2}"]
    assert row["to_send"] == ["read:1", "read:3"]
    (done,) = _rows("sent")
    assert done == dict(done, loop=got["loop"], second_call="call-2", left_host=True, why="")
    with open(read_log.path(), encoding="utf-8") as fh:
        text = fh.read()
    assert "planted-answer-text" not in text and "packets 9001" not in text, \
        "never the answer's text"


def test_a_cut_answers_logged_digest_is_of_what_was_sent_beside_the_wholes():
    whole = ("flow table 0 priority 10 packets 900 bytes 1200\n" * 200).encode()
    gw = FakeGateway(_first(_ask("switch_flows", dpid=DPID1)), _second())
    _loop(gw, family=_family(run=Runner({"switch_flows": whole.decode()})))
    (e,) = _rows("reads")[0]["reads"]
    (carried,) = json.loads(gw.calls[1]["parts"]["mercury_reads"])
    data = carried["answer"].encode("utf-8")
    assert e["cut"] is True and len(data) <= RL.AI_READ_CAP < len(whole)
    assert (e["sent_bytes"], e["sent_sha256"]) == (len(data), hashlib.sha256(data).hexdigest())
    assert (e["bytes"], e["sha256"]) == (len(whole), hashlib.sha256(whole).hexdigest())


def test_a_send_log_that_cannot_be_written_asks_no_pass_2(monkeypatch):
    def refuse(row, now=None):
        raise OSError("the disk is full")
    monkeypatch.setattr(read_log, "_append", refuse)
    gw = FakeGateway(_first(_ask("switch_flows", dpid=DPID1)), _second())
    got = _loop(gw)
    assert len(gw.calls) == 1, "nothing of the reads is sent unlogged"
    assert got["state"] == "first_pass" and got["pass"] == 1 and got["logged"] is False
    assert got["words"] == ("AI analysis: asked for 1 read; 1 run; second pass not run: the "
                            "send log could not be written (OSError: the disk is full), so "
                            "nothing of the reads is sent")


@pytest.mark.parametrize("second,left,why", [
    ({"error": "over_cap", "detail": "over the day cap $1.5000"}, False,
     "over_cap: over the day cap $1.5000"),
    ({"error": "feature_off", "detail": "heal_analysis is off for lab"}, False,
     "feature_off: heal_analysis is off for lab"),
    ({"error": "provider_down", "detail": "HTTP 529"}, True, ""),
], ids=["cap", "feature-off", "provider-down"])
def test_pass_2s_outcome_is_logged_whether_it_left_the_host(second, left, why):
    gw = FakeGateway(_first(_ask("switch_flows", dpid=DPID1)), second)
    got = _loop(gw)
    (done,) = _rows("sent")
    assert done["left_host"] is left and done["why"] == why
    assert done["second_call"] == "call-2" and done["loop"] == got["loop"]
    (loop,) = read_log.loops()["loops"]
    words = read_log.left_host_words(loop, "read:1")
    assert words == ("sent to the provider in pass 2's call call-2" if left else
                     f"not sent: {why}")


def test_a_reads_row_with_no_sent_row_reads_as_possibly_sent_and_an_unrun_read_as_unsent():
    loop = {"to_send": ["read:1"], "sent": {}}
    assert read_log.left_host_words(loop, "read:1") == ("not recorded whether pass 2 was sent: "
                                                        "read it as sent")
    assert read_log.left_host_words(loop, "read:2") == "not sent: it did not run"


def test_no_read_run_logs_every_request_and_sends_nothing():
    gw = FakeGateway(_first(_ask("port_stats", dpid=DPID1, port=True)))
    got = _loop(gw)
    assert len(gw.calls) == 1 and got["logged"] is True
    (row,) = _rows("reads")
    assert row["to_send"] == [] and row["reads"][0]["verdict"] == "refused"
    assert _rows("sent") == []


def test_an_executors_run_and_account_reach_the_log_never_the_model():
    def runner(op, args, requests, scope):
        return RL.Answered(ANSWER, run="20261107T000000000000Z-" + "a" * 32,
                           signed_in_as={"username": "mercury-ro", "source": "profile:default",
                                         "password": "never-kept"})
    gw = FakeGateway(_first(_ask("switch_flows", dpid=DPID1)), _second())
    got = _loop(gw, family=_family(run=runner))
    (e,) = _rows("reads")[0]["reads"]
    assert e["run"] == "20261107T000000000000Z-" + "a" * 32
    assert e["signed_in_as"] == {"username": "mercury-ro", "source": "profile:default"}
    parts = gw.calls[1]["parts"]["mercury_reads"]
    assert ANSWER in parts
    for kept_only in ("mercury-ro", "profile:default", "a" * 32, "never-kept"):
        assert kept_only not in parts, kept_only
    assert "never-kept" not in json.dumps(got["reads"])


def test_through_the_real_gateway_the_logged_digest_is_of_the_bytes_the_provider_got(
        world, registered):  # noqa: F811
    from tests.test_ai_read_loop import _body
    family = _family(run=Runner({"topology": ANSWER}))
    got = _real(world, family, _body(_first(_ask("topology"))), _body(_second()))
    assert got["pass"] == 2 and len(world.sent) == 2
    texts = [b.get("text", "") for m in world.sent[1]["body"]["messages"]
             for b in (m["content"] if isinstance(m["content"], list)
                       else [{"text": m["content"]}])]
    block = next(re.search(r'<data name="mercury_reads">\n(.*?)\n</data>', t, re.S)
                 for t in texts if 'name="mercury_reads"' in t)
    (carried,) = json.loads(block.group(1))
    data = carried["answer"].encode("utf-8")
    (e,) = _rows("reads")[0]["reads"]
    assert e["sent_sha256"] == hashlib.sha256(data).hexdigest() and e["sent_bytes"] == len(data)
    (done,) = _rows("sent")
    assert done["left_host"] is True and done["second_call"] == got["second"]["call_id"]


# ── History ───────────────────────────────────────────────────────────────────────────────────

def _drawn(kind: str) -> str:
    """The History timeline's rows of *kind* as the page draws them: THE reader
    (`history_sources.timeline`) on Lab, through the one macro the page and a device's tab
    draw rows with (templates/v2/_timeline.html)."""
    import app as A
    from flask import render_template_string
    from modules.nsot import listref
    h = HS.timeline(listref.resolve("Lab"), kinds=[kind], since_days="")
    with A.app.test_request_context("/v2/history?list=Lab"):
        return render_template_string(
            "{% from 'v2/_timeline.html' import timeline_rows %}{{ timeline_rows(h) }}", h=h)


def _ctx(name="Lab", device=""):
    return {"ref": types.SimpleNamespace(name=name, data_dir=""), "device": device,
            "members": None, "limit": 50, "since": None, "until": None, "call": ""}


def test_history_draws_each_request_as_its_row_with_its_incident_and_both_calls(lab):  # noqa: F811
    run_id = "20261107T000000000000Z-" + "b" * 32

    def runner(op, args, requests, scope):
        return RL.Answered(ANSWER, run=run_id, signed_in_as={"username": "mercury-ro",
                                                             "source": "profile:default"})
    gw = FakeGateway(_first(_ask("switch_flows", dpid=DPID1),
                            _ask("port_stats", dpid=DPID1, port=True)), _second())
    _loop(gw, family=_family(run=runner))
    events = HS.ai_reads(_ctx())["events"]
    assert [e["kind"] for e in events] == ["ai_read", "ai_read"]
    by = {e["record"][0][1]: e for e in events}
    ran, refused = by["read:1"], by["read:2"]
    assert ran["what"].startswith("AI read 1 of incident hi-5be1c0: ? GET /stats/flow/")
    assert "bytes as device state, 0 lines withheld" in ran["what"]
    rec = dict(ran["record"])
    assert rec["Left the host"] == "sent to the provider in pass 2's call call-2"
    assert rec["On History › Reads"] == run_id
    assert rec["Signed in as"] == "mercury-ro (profile:default)"
    assert rec["Pass 1's call"] == "call-1" and rec["Pass 2's call"] == "call-2"
    assert ran["read_of"] == {"first": "call-1", "second": "call-2", "run": run_id,
                              "list": "Lab"}
    assert refused["outcome"] == "refused" and "True is a true/false value" in refused["detail"]
    assert dict(refused["record"])["Left the host"] == "not sent: it did not run"
    assert "planted-answer-text" not in json.dumps(events)
    assert "ai_read" in HS.KIND_FILTERS["ai_calls"] and HS.SOURCE_KINDS["ai_reads"] == \
        ("ai_read",)
    assert HS.ai_reads(_ctx(name="Elsewhere"))["events"] == [], "an unknown network has none"
    read_log.sending("rl-" + "2" * 16, network="branch", subject=INCIDENT, task="heal_analysis",
                     trigger={}, first_call="ai-9", entries=[{"id": "read:1", "op": "x",
                                                              "verdict": "refused"}])
    assert len(HS.ai_reads(_ctx())["events"]) == 2, "another network's rows are not drawn"
    html = _drawn("ai_calls")
    assert re.search(r'badge-danger[^>]*>[^<]*AI read', html), "a refused read is danger"
    assert re.search(r'badge-muted[^>]*>[^<]*AI read', html), "the control: a read that ran"
    # Each link opens what the send log holds: the drawn address against the stored loop (the
    # refused read links its calls too, and has no run).
    (loop,) = [x for x in read_log.loops()["loops"] if x["network"] == "lab"]
    drawn = re.findall(r'<a href="/v2/history\?call=([^&"]+)(?:&amp;list=Lab)?">Open pass '
                       r'([12])', html)
    assert drawn == [(loop["first_call"], "1"), (loop["sent"]["second_call"], "2")] * 2
    runs = re.findall(r'href="/v2/show-commands/run/([^?"]+)\?list=Lab">Open the read', html)
    assert runs == [loop["reads"][0]["run"]]
    assert "planted-answer-text" not in html


def test_a_devices_tab_shows_only_the_reads_of_that_device(lab):  # noqa: F811
    read_log.sending("rl-" + "1" * 16, network="lab", subject=INCIDENT, task="heal_analysis",
                     trigger={"kind": "background"}, first_call="ai-1",
                     entries=[{"id": "read:1", "device": "r3", "op": "interfaces",
                               "commands": ["show interfaces GigabitEthernet4"],
                               "verdict": "refused", "reason": "no read-only account for r3"},
                              {"id": "read:2", "device": "r9", "op": "interfaces",
                               "commands": ["show interfaces GigabitEthernet1"],
                               "verdict": "refused", "reason": "held"}])
    got = HS.ai_reads(_ctx(device="r3"))["events"]
    assert [e["devices"] for e in got] == [["r3"]]
    assert got[0]["what"] == ("AI read 1 of incident hi-5be1c0: r3 show interfaces "
                              "GigabitEthernet4: refused")


def test_an_unreadable_send_log_is_said_never_drawn_as_none(lab):  # noqa: F811
    import os
    os.makedirs(os.path.dirname(read_log.path()), exist_ok=True)
    with open(read_log.path(), "a", encoding="utf-8") as fh:
        fh.write("{torn\n")
    got = HS.ai_reads(_ctx())
    assert got["events"] == [] and got["errors"] == [
        "the read loop's send log could not be read: the read loop's send log cannot be read "
        "(JSONDecodeError)"]


def test_the_log_masks_every_string_at_rest_and_keeps_its_digests(monkeypatch):
    """Whatever a caller hands it: a value Mercury keeps secret, in any string of a row, is kept
    as its mask; a digest is kept as it is."""
    from modules import redact
    from tests.test_ai_read_loop import SECRET
    monkeypatch.setattr(redact, "known_secret_values", lambda: {SECRET: "template_secret"})
    digest = hashlib.sha256(b"x").hexdigest()
    read_log.sending("rl-" + "3" * 16, network="lab", subject={"id": f"hi-{SECRET}"},
                     task="heal_analysis", trigger={}, first_call="ai-1",
                     entries=[{"id": "read:1", "op": "x", "verdict": "run",
                               "reason": f"the read failed: {SECRET}",
                               "signed_in_as": {"username": SECRET, "source": "p"},
                               "sent_sha256": digest, "sha256": digest}])
    with open(read_log.path(), encoding="utf-8") as fh:
        text = fh.read()
    assert SECRET not in text
    (e,) = _rows("reads")[0]["reads"]
    assert e["sent_sha256"] == e["sha256"] == digest


def test_a_row_naming_no_loop_or_an_unknown_row_is_refused():
    with pytest.raises(read_log.Refused, match="names its loop by an id"):
        read_log.answered("loop-1", second_call="ai-1", left_host=True)
    with pytest.raises(read_log.Refused, match="one of reads, sent"):
        read_log._append({"row": "answer", "loop": "rl-" + "0" * 16})


# ── History › Reads: whom a read signed in as (C2661) ─────────────────────────────────────────

def test_history_reads_draws_whom_each_device_signed_in_as(lab):  # noqa: F811
    from modules.nsot import reads
    rid = reads.new_id()
    record = {"id": rid, "list": "Lab", "actor": "admin@example.com", "by": "ai_analysis",
              "purpose": "the AI's read",
              "started_at": 1_800_000_000.0, "finished_at": 1_800_000_001.0, "state": "done",
              "commands": ["show interfaces GigabitEthernet4"], "devices": ["r3"],
              "results": {"r3": {"state": "answered", "answers": [], "signed_in_as": {
                  "username": "mercury-ro", "source": "read-account:profile:default"}}},
              "refused": "", "summary": {"words": "1 answered"}}
    reads._write("Lab", record)
    (e,) = HS.show_commands(dict(_ctx(), members={"r3"}))["events"]
    assert dict(e["record"])["Signed in as"] == ("r3: mercury-ro "
                                                 "(read-account:profile:default)")
    assert e["who"] == ("the AI analysis, turned on by admin@example.com, as the read-only "
                        "account")
    html = _drawn("show_commands")
    # The drawn account against the stored record's.
    signed = reads.get("Lab", rid)["results"]["r3"]["signed_in_as"]
    drawn = re.findall(r"<dt>Signed in as</dt><dd>r3: ([^ <]+) \(([^)<]+)\)</dd>", html)
    assert drawn == [(signed["username"], signed["source"])]


def test_a_read_with_no_account_recorded_draws_no_signed_in_line(lab):  # noqa: F811
    from modules.nsot import reads
    rid = reads.new_id()
    reads._write("Lab", {"id": rid, "list": "Lab", "actor": "op@example.com", "by": "person",
                         "started_at": 1_800_000_000.0, "state": "done",
                         "commands": ["show version"], "devices": ["r3"],
                         "results": {"r3": {"state": "answered", "answers": []}},
                         "summary": {"words": "1 answered"}})
    (e,) = HS.show_commands(dict(_ctx(), members={"r3"}))["events"]
    assert "Signed in as" not in dict(e["record"])


from tests.test_device_v2 import lab  # noqa: E402,F401 (the fixture)
