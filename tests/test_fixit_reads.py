"""AI troubleshooting's reads (`modules/ai/fixit_reads.py`, the read loop's ``local`` transport and
an operation's own transport, `router_reads`' two telemetry shapes; the fix-it plan's S6;
docs/HEAL_TO_INTENT.md section 12, "The AI call (S5)"). No live AI call: the provider is
replaced, and nothing reaches a device or the network.

- **The shapes:** `telemetry_brief` and `telemetry_receiver` are each matched whole on the CLI
  read rule, their commands the stream runbook's own and the captures' (r6's brief, r2's and
  r7's receivers, read through Mercury's reads engine); a subscription the device's intent does
  not declare, or the incident does not name, and a command with a word or a modifier more, are
  refused by name; the heal analysis's read set does not gain them.
- **The local rule:** a local read is one line, ``local <what>`` and its tokens; a planted
  command declared as one is refused when the family is declared.
- **The collector read** is held to the incident's device and its subscription (another
  device's, another subscription refused before anything runs), the collector's address and
  port the receiver the device's intent declares, never the model's; IPv4 and IPv6, on the
  kernel's real tables (tests/fixtures/diagnose/collector/).
- **The class off** refuses each read by name.
- **Each read is in the send log and on History**, through the real gateway and the real route,
  linked to the incident's call.
"""
import json
import os

import pytest

from modules.ai import read_loop as RL
from tests.test_heal_diagnose_stream import proc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "diagnose")
COLLECTOR = os.path.join(FIX, "collector")
#: A receiver in intent's own lines (`diagnose_stream.receiver_of`), IPv4 and IPv6.
RECEIVER4 = {"address": "192.0.2.10", "port": 57000}
RECEIVER6 = {"address": "2001:db8::10", "port": 57000}


def _fixture(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def _ss(family: int):
    text = open(os.path.join(COLLECTOR, f"ss_tni_{family}.txt"), encoding="utf-8").read()
    return lambda port: (text, "")


def scope(streams=None, sources=("192.0.2.6",), subs=("101", "102"), collector=None,
          series=None, declared=("101", "102")) -> dict:
    """A scope as `fixit_reads.scope_for` builds it, for edge1's incident: the router read
    set's device entry (a read-only account, the subscriptions intent declares) and the
    incident's own streams."""
    return {"network": "Default", "addresses": [], "prefixes": [],
            "devices": {"edge1": {"interfaces": [], "peers": [], "dialect": "cisco_iosxe",
                                  "subscriptions": list(declared), "read_account": True,
                                  "read_account_why": ""}},
            "subscriptions": list(subs), "actor": "AI troubleshooting of incident hi-1",
            "fixit": {"device": "edge1", "streams": dict(streams or {
                "101": RECEIVER4, "102": RECEIVER4}), "sources": list(sources),
                      "collector": collector, "series": series}}


def ask(op, **args):
    return {"op": op, "args": dict({"device": "edge1"}, **args), "why": "to see the stream",
            "hypothesis": "the collector holds a dead session"}


@pytest.fixture
def on(monkeypatch):
    """The device state class on for Default (its switch read as on, as an admin's turn-on
    records it), so the check reaches each read's own comparisons."""
    from modules.ai import egress_classes
    monkeypatch.setattr(egress_classes, "device_state_allowed",
                        lambda network: {"allowed": True, "why": ""})
    monkeypatch.setattr(egress_classes, "classification_marking", lambda network: "")


def judged(requests, sc, family=None):
    """*requests* checked by the fixed shapes' family (`fixit_reads.SHAPES_FAMILY`: the shapes
    AI troubleshooting asked by until C3661 moved its reads to Mercury's allowlist, kept for the
    read-only account probe and the diagnosis), or by *family*."""
    from modules.ai import fixit_reads as FR
    return RL.check(family or FR.SHAPES_FAMILY, requests, network="Default", scope=sc)


# ── The shapes ──────────────────────────────────────────────────────────────────────────────

class TestTheShapes:
    def test_the_two_shapes_are_the_runbooks_commands_on_the_cli_rule(self):
        from modules.ai import fixit_reads as FR
        from modules.ai import router_reads as R
        from modules.heal import diagnose as D
        ops = {o.name: o for o in R.TELEMETRY_OPS}
        assert ops["telemetry_brief"].sends == ("show telemetry ietf subscription all",)
        assert ops["telemetry_receiver"].sends == (
            "show telemetry ietf subscription {subscription} receiver",)
        assert D.render("telemetry_brief", "cisco_iosxe") == "show telemetry ietf subscription all"
        assert D.render("telemetry_receiver", "cisco_iosxe", sub="101") == \
            "show telemetry ietf subscription 101 receiver"
        # C3640: the device's connections, IOS-XE 17's form (the operator, 2026-11-14).
        assert ops["telemetry_connection"].sends == ("show telemetry internal connection",)
        assert D.render("telemetry_connection", "cisco_iosxe") == \
            "show telemetry internal connection"
        for name in R.TELEMETRY:
            op = FR.SHAPES_FAMILY.operation(name)
            assert FR.SHAPES_FAMILY.transport_of(op) == "cli" and \
                FR.SHAPES_FAMILY.class_of(op) == "device_state"
        assert not {o.name for o in R.AI_READS.operations} & set(R.TELEMETRY), \
            "the heal analysis's read set (its released schema) does not gain them"

    def test_each_capture_is_the_answer_to_its_shape(self):
        """The commands the captures answer, read through Mercury's reads engine, are the ones
        the shapes render (tests/fixtures/diagnose/README.md)."""
        assert "Telemetry subscription brief" in _fixture(
            "r6__show_telemetry_ietf_subscription_all.txt")
        for dev in ("r2", "r7"):
            text = _fixture(f"{dev}__show_telemetry_ietf_subscription_101_receiver.txt")
            assert "Subscription ID: 101" in text and "State: Connected" in text

    def test_each_shape_is_allowed_whole(self, on):
        got = judged([ask("telemetry_brief"), ask("telemetry_receiver", subscription="101")],
                     scope())
        assert [g["verdict"] for g in got] == ["allowed", "allowed"], got
        assert got[0]["requests"] == ["show telemetry ietf subscription all"]
        assert got[1]["requests"] == ["show telemetry ietf subscription 101 receiver"]

    def test_the_connections_are_ios_xe_s_and_another_platform_s_form_on_ios(self, on):
        """C3640: asked whole on IOS-XE; on IOS refused as another platform's form, by the
        comparison the probe leaves it out by (`router_reads.other_platform`)."""
        from modules.ai import router_reads as R
        got = judged([ask("telemetry_connection")], scope())
        assert got[0]["verdict"] == "allowed", got
        assert got[0]["requests"] == ["show telemetry internal connection"]
        ios = scope()
        ios["devices"]["edge1"]["dialect"] = "cisco_ios"
        got = judged([ask("telemetry_connection")], ios)
        assert got[0]["verdict"] == "refused" and "this form is cisco_iosxe's" in \
            got[0]["reason"], got
        assert R.other_platform("telemetry_connection", "edge1", ios) == (
            "edge1's platform is cisco_ios, and this form is cisco_iosxe's")
        assert R.other_platform("telemetry_connection", "edge1", scope()) == ""

    @pytest.mark.parametrize("request_, why", [
        (ask("telemetry_receiver", subscription="103"), "not one edge1's intent declares"),
        (ask("telemetry_receiver", subscription="101"), "not one the incident names"),
        (ask("telemetry_receiver", subscription="101 receiver | include Address"), "subscription"),
        (ask("telemetry_receiver", subscription="1x"), "subscription"),
        (ask("telemetry_brief", subscription="101"), "takes no argument"),
        (dict(ask("telemetry_receiver", subscription="101"), args={"device": "edge2",
                                                                   "subscription": "101"}),
         "edge2 is not a device the incident names"),
    ], ids=["not declared", "not the incident's", "a modifier", "not digits",
            "an argument it does not take", "another device"])
    def test_a_planted_request_is_refused_by_name(self, on, request_, why):
        sc = scope(subs=("102",)) if why == "not one the incident names" else scope()
        (got,) = judged([request_], sc)
        assert got["verdict"] == "refused" and why in got["reason"], got

    def test_the_whole_command_matched_never_by_resemblance(self, on):
        """A command arriving as text (the runbook's) is matched whole against the router read
        set: a word more is refused, and the heal analysis's set never holds the telemetry
        shapes, so it refuses them by name."""
        from modules.ai import router_reads as R
        sc = scope()
        got = R.match("show telemetry ietf subscription all", "edge1", sc, network="Default")
        assert got["verdict"] == "refused" and "not one of the AI read set's commands" in \
            got["reason"], got


# ── The local rule ──────────────────────────────────────────────────────────────────────────

class TestTheLocalRule:
    @pytest.mark.parametrize("send", ["show running-config", "local collector_sessions; rm -rf /",
                                      "local Collector x", ("GET", "/x")])
    def test_a_planted_command_is_refused_when_declared(self, send):
        op = RL.Operation("planted", args={}, sends=(send,), transport="local")
        with pytest.raises(RL.Undeclarable, match="a local read is"):
            RL.ReadFamily(name="planted", transport="cli", egress_class="device_state",
                          operations=(op,), run=lambda *a: "")

    def test_an_operation_s_own_transport_is_held_to_its_rule(self):
        op = RL.Operation("planted", args={}, sends=("snapshot flows",), transport="seal")
        fam = RL.ReadFamily(name="planted", transport="local", egress_class="topology",
                            operations=(op,), run=lambda *a: "")
        assert fam.transport_of(op) == "seal"
        bad = RL.Operation("planted", args={}, sends=("local x",), transport="snmp")
        with pytest.raises(RL.Undeclarable, match="transport 'snmp' has no read rule"):
            RL.ReadFamily(name="planted", transport="local", egress_class="topology",
                          operations=(bad,), run=lambda *a: "")

    def test_every_local_operation_renders_one_local_line(self, on):
        got = judged([ask("collector_sessions", subscription="101"),
                      ask("stream_series", subscription="102")], scope())
        assert [g["requests"] for g in got] == [["local collector_sessions edge1 101"],
                                                ["local stream_series edge1 102"]]


# ── The collector read ──────────────────────────────────────────────────────────────────────

class TestTheCollectorRead:
    @pytest.mark.parametrize("request_, why", [
        (dict(ask("collector_sessions"), args={"device": "edge2", "subscription": "101"}),
         "edge2 is not the incident's device"),
        (ask("collector_sessions", subscription="103"), "not one the incident names"),
        (dict(ask("collector_sessions", subscription="101"),
              args={"device": "edge1", "subscription": "101", "port": 22}),
         "takes no argument"),
    ], ids=["another device", "another subscription", "a port of the model's own"])
    def test_held_to_the_incident_s_device_and_its_stream(self, on, request_, why):
        (got,) = judged([request_], scope())
        assert got["verdict"] == "refused" and why in got["reason"], got

    @pytest.mark.parametrize("receiver, source, family, remote", [
        (RECEIVER4, "192.0.2.6", 4, "192.0.2.6"),
        (RECEIVER6, "2001:db8:4::6", 6, "2001:db8:4::6"),
    ], ids=["IPv4", "IPv6"])
    def test_it_reads_the_collector_s_side_on_the_kernel_s_tables(self, on, receiver, source,
                                                                   family, remote, tmp_path):
        from modules.ai import fixit_reads as FR
        from modules.heal import diagnose_stream as DS
        root = proc(tmp_path)

        def collector(address, port, sources):
            return DS.read_collector(address, port, sources, proc=root, ss=_ss(family))
        sc = scope(streams={"101": receiver}, sources=(source,), collector=collector)
        (v,) = judged([ask("collector_sessions", subscription="101")], sc)
        assert v["verdict"] == "allowed", v
        (rec,) = RL.run_reads(FR.FAMILY, [dict(v, id="read:1")], sc)
        assert rec["verdict"] == "run", rec
        got = json.loads(rec["answer"])
        assert got["collector"] == f"{receiver['address']} port 57000"
        # Only the device's own sessions (192.0.2.7's, another device's, left out); the IPv4
        # tables hold r7's session twice, as tcp's row and as the dual-stack listener's
        # ::ffff: row (tests/fixtures/diagnose/collector/README.md).
        assert got["listening"] and got["sessions"]
        assert {s["remote"] for s in got["sessions"]} == {remote}
        assert got["activity"] == "read"

    def test_a_receiver_intent_does_not_declare_fails_said(self, on):
        from modules.ai import fixit_reads as FR
        sc = scope(streams={"101": {"why": "intent gives it no receiver address and port"},
                            "102": RECEIVER4})
        (v,) = judged([ask("collector_sessions", subscription="101")], sc)
        (rec,) = RL.run_reads(FR.FAMILY, [dict(v, id="read:1")], sc)
        assert rec["verdict"] == "failed" and "no receiver address and port" in rec["reason"]

    def test_the_series_read_is_the_alert_s_own_query(self, on):
        from modules.ai import fixit_reads as FR
        asked = []

        def series(device, sub):
            asked.append((device, sub))
            return {"state": "absent", "count": 0, "why": "no sample in the last 90 s",
                    "query": "x"}
        sc = scope(series=series)
        (v,) = judged([ask("stream_series", subscription="102")], sc)
        (rec,) = RL.run_reads(FR.FAMILY, [dict(v, id="read:1")], sc)
        assert asked == [("edge1", "102")] and json.loads(rec["answer"])["state"] == "absent"


# ── The stream's reads by Mercury's allowlist (C3661) ───────────────────────────────────────

def test_the_stream_s_device_reads_by_the_allowlist_are_held_to_intent_and_the_incident(on):
    """AI troubleshooting's family (v5) asks the stream's device reads as an engineer types
    them: the brief, the connections and a receiver, the subscription one the device's intent
    declares and the incident names."""
    from modules.ai import fixit_reads as FR
    got = judged([ask("show", words="telemetry ietf subscription all"),
                  ask("show", words="telemetry internal connection"),
                  ask("show", words="telemetry ietf subscription 101 receiver")],
                 scope(), family=FR.FAMILY)
    assert [g["verdict"] for g in got] == ["allowed"] * 3, got
    assert got[2]["requests"] == ["show telemetry ietf subscription 101 receiver"]
    (got,) = judged([ask("show", words="telemetry ietf subscription 103 receiver")], scope(),
                    family=FR.FAMILY)
    assert got["verdict"] == "refused" and "not one edge1's intent declares" in got["reason"]
    (got,) = judged([ask("show", words="telemetry ietf subscription 101 receiver")],
                    scope(subs=("102",)), family=FR.FAMILY)
    assert got["verdict"] == "refused" and "not one the incident names" in got["reason"]


# ── The class off ───────────────────────────────────────────────────────────────────────────

def test_the_class_off_refuses_each_read_by_name(monkeypatch):
    from modules.ai import egress_classes
    monkeypatch.setattr(egress_classes, "device_state_allowed", lambda network: {
        "allowed": False, "why": "off by default, and no admin has turned it on"})
    monkeypatch.setattr(egress_classes, "classification_marking", lambda network: "")
    got = judged([ask("collector_sessions", subscription="101"), ask("telemetry_brief"),
                  ask("stream_series", subscription="101")], scope())
    assert [g["verdict"] for g in got] == ["refused"] * 3
    assert all("the device state class is off for Default" in g["reason"] for g in got)


# ── S5's v2 stays readable: expand, then contract ───────────────────────────────────────────

def test_s5_s_v2_stays_registered_and_reads_an_answer_recorded_under_it():
    """Pass 1 asks v5 now (prompt and schema, over Mercury's allowlist and its own reads,
    C3661); S5's v2 (the router read set alone) and S6's v4 (the fixed shapes) stay registered
    as they shipped, so an answer a call recorded under either is read by its own schema, and
    their prompt files are still there to name."""
    from modules.ai import fixit_troubleshoot as T
    from modules.ai import prompts, schemas
    assert T.PROMPT_READS == ("fixit_troubleshoot", 5) and T.PROMPT_READS_V2[1] == 2
    assert T.PROMPT_READS_V4 == ("fixit_troubleshoot", 4)
    assert schemas.REGISTRY[("fixit_troubleshoot", 2)] is T.TroubleshootReads
    assert schemas.REGISTRY[("fixit_troubleshoot", 4)] is T.TroubleshootFixitReads
    assert schemas.REGISTRY[("fixit_troubleshoot", 5)] is T.TroubleshootEngineerReads
    assert prompts.load("fixit_troubleshoot", 5)["text"] != prompts.load(
        "fixit_troubleshoot", 4)["text"]
    assert prompts.load("fixit_troubleshoot", 2)["text"] and prompts.load(
        "fixit_troubleshoot", 4)["text"] != prompts.load("fixit_troubleshoot", 2)["text"]
    recorded = {"outcome": "answer", "rationale": "r", "hypotheses": [], "fix": None,
                "gap": None, "needs_human": True, "why_not": "",
                "reads": [{"op": "interfaces", "args": {"device": "edge1",
                                                       "interface": "GigabitEthernet2"},
                           "why": "w", "hypothesis": "h"}]}
    got = T.TroubleshootReads.model_validate_json(json.dumps(recorded))
    assert got.reads[0].op.value == "interfaces"
    # v2's reads are the router read set's: the stream's own reads are v4's alone.
    with pytest.raises(Exception):
        T.TroubleshootReads.model_validate_json(json.dumps(dict(recorded, reads=[
            {"op": "collector_sessions", "args": {"device": "edge1", "subscription": "101"},
             "why": "w", "hypothesis": "h"}])))
    assert T.TroubleshootFixitReads.model_validate_json(json.dumps(dict(recorded, reads=[
        {"op": "collector_sessions", "args": {"device": "edge1", "subscription": "101"},
         "why": "w", "hypothesis": "h"}]))).reads[0].op.value == "collector_sessions"


# ── Through the real gateway and route: the send log and History ────────────────────────────

from tests.test_fixit_troubleshoot import ai, answer, fix, press, stopped  # noqa: E402,F401
from tests.test_fixit_section_v2 import web  # noqa: E402,F401 (the fixture `ai` builds on)
from tests.test_heal_resubscribe import lab  # noqa: E402,F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: E402,F401 (the fixture `lab` builds on)


def test_each_read_is_in_the_send_log_and_on_history(ai, monkeypatch, tmp_path):  # noqa: F811
    """With the class on for the network, pass 1 asks for the collector's sessions and the
    receiver: the collector read runs (its answer masked and logged before pass 2), the device
    read runs by Mercury's allowlist through the reads engine as Mercury's account, Show
    commands' own session (C3661: no read-only account needed for the lab's r2), and the send
    log and History hold each request, linked to the incident's two calls."""
    from modules.ai import egress_classes, read_log
    from modules.heal import diagnose_stream as DS
    monkeypatch.setattr(egress_classes, "device_state_allowed",
                        lambda network: {"allowed": True, "why": ""})
    opened = []
    receiver = "show telemetry ietf subscription 101 receiver"

    class Conn:
        """Show commands' session to r2: the AI's receiver read is answered from r2's capture;
        anything else this world's device never answers (no device here)."""

        def answer(self, command):
            if command != receiver:
                raise ConnectionRefusedError("no device in this test")
            opened.append("r2")
            return _fixture("r2__show_telemetry_ietf_subscription_101_receiver.txt")

        def enable(self):
            """Mercury's account escalates, as the pooled session does (H28)."""

        def disconnect(self):
            """Closed at the investigation's end."""

    monkeypatch.setattr("modules.connection.with_temp_connection", lambda dev, fn: fn(Conn()))
    # Premise corrected (231da1d6, the operator, 2026-11-16: "the standard reads on the run's
    # one session (sign in once)"): an investigation's device reads ride its one pooled
    # session (the reads engine's `reads.SessionPool` since C3974, Mercury's account), which
    # opens it with `connection.open_ssh`, where each read took Show commands' own temporary
    # session; the same stand-in session answers it, signed in as the lab's stand-in account
    # (the lab's r2 holds no stored credential: the pool reads the stored parameters itself).
    monkeypatch.setattr("modules.connection.open_ssh", lambda params, plain=False, owner="":
                        Conn())
    monkeypatch.setattr("modules.connection.stored_connection_params", lambda dev: {
        "host": dev.get("ip"), "device_type": dev.get("device_type"), "username": "mercury",
        "password": "stand-in", "secret": "stand-in"})
    monkeypatch.setattr("modules.connection.with_plain_connection",
                        lambda dev, fn: pytest.fail("the read-only session opened"))
    real, root = DS.read_collector, proc(tmp_path)
    # Premise corrected (17215a95, C3720: `collector_of` hands `read_collector` the shared `ss`
    # answer): the stand-in takes its whole signature, its own planted `ss` read in place.
    monkeypatch.setattr(DS, "read_collector", lambda a, p, s, proc="/proc", ss=None: real(
        "192.0.2.10", 57000, ["192.0.2.6"], proc=root, ss=_ss(4)))
    # The lab's committed intent is the operation's sources' (r2's real intent, its two
    # subscriptions and their receiver), as the router read set reads it.
    from tests.test_heal_resubscribe import Src
    intents = Src()._intents
    monkeypatch.setattr("modules.ai.router_reads._committed",
                        lambda network, hosts: (intents, {h: "" for h in hosts}))
    iid = stopped(ai)
    # Premise corrected (17215a95's ladder: `fix()`'s re-subscribe repeats attempt 1 and is
    # refused as tried, ending the press at pass 1): the answers' fix is the collector's close.
    from tests.test_fixit_troubleshoot import CLOSE
    first = answer(fix(operation=CLOSE))
    first["reads"] = [{"op": "collector_sessions", "args": {"device": "r2", "subscription": "101"},
                       "why": "the collector's side", "hypothesis": "a dead session"},
                      {"op": "show", "args": {"device": "r2", "words":
                                              "telemetry ietf subscription 101 receiver"},
                       "why": "the device's side", "hypothesis": "a dead session"}]
    second = answer(fix(operation=CLOSE), cites=("attempt:1", "read:1"))
    script = [first, second]
    ai.answer = None
    sent_answers = iter(script)
    import types
    from modules.ai import anthropic_adapter as AD
    from modules.ai import gateway

    def send(body, key, **_kw):
        ai.sent.append(body)
        return AD.Reply(status=200, body={
            "content": [{"type": "text", "text": json.dumps(next(sent_answers))}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 9000, "output_tokens": 600}},
            attempts=1, latency_s=0.2)
    monkeypatch.setattr(gateway, "anthropic_adapter", types.SimpleNamespace(
        **{**vars(gateway.anthropic_adapter), "send": send}))
    r, html = press(ai, iid)
    assert r.status_code == 200, html
    assert len(ai.sent) == 2, "pass 1 and, a read having run, pass 2"
    assert "collector_sessions" in json.dumps(ai.sent[0]["system"]), "the read set is sent"
    assert "mercury_reads" in ai.sent[1]["messages"][0]["content"]
    # Pass 1 is the version asked now, never an older one. Premise corrected (C3755, C3764,
    # 2026-11-15): the reads pass is v8 (`fixit_troubleshoot.PROMPT_PLAN_READS`, prompt and
    # schema, its answer a plan), where it was v5 (C3661); v5 stays readable, never asked.
    from modules.ai import calls
    from modules.ai import fixit_troubleshoot as FT
    rows = {r["id"]: r for r in calls.read()["rows"]}
    # Premise corrected again (231da1d6, v17's one shape: every pass one prompt and schema, the
    # cached prefix the same bytes call to call; C3918's v18): both calls are v18, where the
    # first pass was v11 and the next its own.
    asked = f"{FT.FEATURE}.v{FT.PROMPT_INVESTIGATE[1]}"
    assert asked == "fixit_troubleshoot.v18"
    both = [r for r in rows.values() if r.get("feature") == "fixit_troubleshoot"
            and r.get("prompt") == asked]
    assert len(both) == 2 and all(r["schema"] == asked for r in both)
    assert not [r for r in rows.values() if r.get("prompt") == "fixit_troubleshoot.v5"]
    assert "FixitReadAsk" in json.dumps(ai.sent[0]["output_config"])
    (loop,) = read_log.loops()["loops"]
    text = json.dumps(loop)
    assert "collector_sessions" in text and "show telemetry ietf subscription 101 receiver" \
        in text
    assert "local collector_sessions r2 101" in text
    assert opened == ["r2"], "the device read ran through the investigation's one session"
    (dev_read,) = [e for e in loop["reads"] if e.get("op") == "show"]
    assert dev_read["verdict"] == "run"
    assert dev_read["signed_in_as"]["source"].startswith("mercury-account:")
    from modules.fixit import incident as F
    from tests.test_fixit_section_v2 import incident
    call1, call2 = loop.get("first_call"), loop["sent"].get("second_call")
    assert call1 and call2 and loop["sent"].get("left_host") is True
    (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
    assert line["calls"] == [call1, call2], "both calls are the incident's"
    # History draws each request as its own row beside the calls.
    import types as _t
    from modules import history_sources as HS
    events = HS.ai_reads({"ref": _t.SimpleNamespace(name="Default", data_dir=""), "device": "",
                          "members": None, "limit": 50, "since": None, "until": None,
                          "call": ""})["events"]
    drawn = json.dumps(events)
    assert len(events) == 2 and "collector_sessions" in drawn and \
        "show telemetry ietf subscription 101 receiver" in drawn
    assert call1 in drawn and call2 in drawn, "each row links both calls"


def test_a_press_whose_answer_names_a_gap_records_it_for_review(ai, monkeypatch):  # noqa: F811
    """C3663 end to end (Tier 1's review, NOTE 10): through the real route and gateway, an answer
    naming a gap is kept as the incident's proposal line AND recorded as a missing capability
    for the incident; with the store unable to be written, the answer still stands."""
    from modules.ai import missing
    from tests.test_fixit_troubleshoot import sec_of
    gap = {"what": "close the collector's half-open session from r2 on its host",
           "evidence_refs": ["attempt:1"]}
    iid = stopped(ai)
    ai.answer = answer(gap=gap)
    r, html = press(ai, iid)
    assert r.status_code == 200 and "a gap" in sec_of(html)
    (row,) = missing.rows()["rows"]
    assert (row["kind"], row["what"], row["about"]) == (
        "operation", gap["what"], {"kind": "incident", "id": iid})
    assert row["feature"] == "fixit_troubleshoot"

    def broken(rows, now=None):
        raise OSError("the store's disk is full")

    monkeypatch.setattr(missing, "record", broken)
    iid2 = stopped(ai)
    ai.answer = answer(gap=gap)
    # Premise corrected (R1, 2026-11-14): Start AI troubleshooting is taken once per incident;
    # the same incident (its alerts fold into it) is asked again by Ask the AI again, which a
    # gap's answer offers.
    if iid2 == iid:
        from tests.test_fixit_section_v2 import post
        r = post(ai.client, iid2, "ask_again", text="")
        html = r.get_data(as_text=True)
    else:
        r, html = press(ai, iid2)
    assert r.status_code == 200 and "a gap" in sec_of(html), "the answer stands"


# ── The scope reaches the devices one hop from the incident's (C3685) ─────────────────────

#: A planted model: edge1 linked to acc1, acc1 to far1, and edge1 to an outside peer.
NEAR_MODEL = {"network": "Lab", "names": {"edge1": "dev:1", "acc1": "dev:2", "far1": "dev:3"},
              "nodes": {"dev:1": {"id": "dev:1", "name": "edge1"},
                        "dev:2": {"id": "dev:2", "name": "acc1"},
                        "dev:3": {"id": "dev:3", "name": "far1"}},
              "edges": {"dev:1": {"dev:2": "link:192.0.2.0/30", "ext:192.0.2.99": "bgp"},
                        "dev:2": {"dev:1": "link:192.0.2.0/30", "dev:3": "link:192.0.2.4/30"},
                        "dev:3": {"dev:2": "link:192.0.2.4/30"}},
              "links": {}, "adjacencies": {}}


class TestTheScopeReachesOneHop:
    """C3685 (the operator, 2026-11-14: "any command on the Show commands allowlist, on devices
    in the incident's scope"): an investigation reads the incident's device and each managed
    device one hop from it in the network's model, the topology its pack sends; two hops, an
    outside peer and Mercury's host are not in it; an unreadable model leaves the device
    alone."""

    def test_the_neighbours_are_the_managed_devices_one_hop_away(self, monkeypatch):
        from modules import network_model as NM
        from modules.ai import fixit_reads as FR
        monkeypatch.setattr(NM, "model_for", lambda network: (NEAR_MODEL, ""))
        assert FR.neighbours_of("Lab", "edge1") == ["acc1"]
        assert FR.neighbours_of("Lab", "acc1") == ["edge1", "far1"]
        assert FR.neighbours_of("Lab", "nobody") == []

    def test_an_unreadable_model_leaves_the_device_alone(self, monkeypatch):
        from modules import network_model as NM
        from modules.ai import fixit_reads as FR
        monkeypatch.setattr(NM, "model_for", lambda network: (None, "planted: unreadable"))
        assert FR.neighbours_of("Lab", "edge1") == []

    def test_the_scope_is_built_for_the_device_and_its_neighbours(self, monkeypatch):
        import types
        from modules import network_model as NM
        from modules.ai import fixit_reads as FR
        from modules.ai import router_reads as RR
        monkeypatch.setattr(NM, "model_for", lambda network: (NEAR_MODEL, ""))
        asked = []
        monkeypatch.setattr(RR, "_committed", lambda network, hosts: (
            asked.append(("committed", list(hosts))) or ({}, {})))
        monkeypatch.setattr(RR, "scope_for", lambda network, hosts, **kw: (
            asked.append(("scope", list(hosts))) or {"network": network, "devices": {},
                                                     "addresses": [], "prefixes": []}))
        inc = types.SimpleNamespace(device="edge1", id="hi-1", subscriptions=["101"])
        FR.scope_for("Lab", inc, actor="person@example.invalid")
        assert asked[:2] == [("committed", ["edge1", "acc1"]), ("scope", ["edge1", "acc1"])]


# ── A lost stream's route read toward its collector (C3892) ────────────────────────────────

class TestTheRouteTowardTheCollector:
    """C3892 (the operator, 2026-11-16: option 1, "a standard route read toward the collector
    in every lost-telemetry investigation"): before the first pass, the device's route toward
    each distinct receiver its subscriptions name, `ip route` for IPv4 and `ipv6 route` for
    IPv6, in the receiver's VRF when intent names one; each passes the investigation's own read
    check where the address is the network's."""

    def _reads(self, monkeypatch, streams):
        import types
        from modules.ai import fixit_reads as FR
        from modules.ai import fixit_troubleshoot as T
        monkeypatch.setattr(FR, "stream_scope", lambda network, incident: {
            "device": "edge1", "streams": streams, "sources": []})
        inc = types.SimpleNamespace(device="edge1", id="hi-1", subscriptions=sorted(streams))
        return T.route_reads("Default", inc)

    def test_one_read_per_receiver_by_its_family_and_vrf(self, monkeypatch):
        got = self._reads(monkeypatch, {"101": RECEIVER4, "102": RECEIVER4,
                                        "103": RECEIVER6,
                                        "104": dict(RECEIVER4, address="192.0.2.20", vrf="Mgmt"),
                                        "105": {"why": "intent gives it no receiver"}})
        assert [r["args"]["words"] for r in got] == [
            "ip route 192.0.2.10", "ipv6 route 2001:db8::10", "ip route vrf Mgmt 192.0.2.20"]
        assert {r["op"] for r in got} == {"show"} and all(
            r["args"]["device"] == "edge1" for r in got)

    def test_each_passes_the_investigation_s_read_check(self, monkeypatch, on):
        from modules.ai import fixit_reads as FR
        reqs = self._reads(monkeypatch, {"101": RECEIVER4, "103": RECEIVER6})
        sc = dict(scope(), prefixes=["192.0.2.0/24", "2001:db8::/64"])
        got = judged([dict(r, why=r["why"][:200]) for r in reqs], sc, family=FR.FAMILY)
        assert [g["verdict"] for g in got] == ["allowed", "allowed"], got

    def test_a_lost_stream_s_standard_reads_carry_it(self, monkeypatch):
        import types
        from modules.ai import fixit_reads as FR
        from modules.ai import fixit_troubleshoot as T
        monkeypatch.setattr(T, "problem_condition", lambda found: "telemetry_lost")
        monkeypatch.setattr(FR, "stream_scope", lambda network, incident: {
            "device": "edge1", "streams": {"101": RECEIVER4}, "sources": []})
        inc = types.SimpleNamespace(device="edge1", id="hi-1", subscriptions=["101"])
        requests, reuse = T.pregather_for("Default", {"incident": {}}, inc)
        assert [r["args"]["words"] for r in requests] == ["ip route 192.0.2.10"] and reuse == {}
        assert requests[0]["why"] == T.ROUTE_WHY
