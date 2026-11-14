"""The heal analysis asked through the read loop (board H, part H26; docs/HEAL_TO_INTENT.md 19.5;
`modules/ai/heal_analysis.py`'s `_ask_looped`), on test_heal_analysis's world: a real can't-fix
decided by the real decision, the real gateway with a real settings file and record of AI calls
in the test's folder, H28's real device state switch and read-only account, and the reads
engine with only its session faked (`connection.with_plain_connection`); no provider, no device.

- **The feature off (its default):** the gateway refuses pass 1 with no provider request;
  nothing is sent, no read runs, and the incident's step says so.
- **The device state class off (its default):** pass 1 is today's call exactly (v1, no
  ``reads``, no read set in its context); the step says why no read was asked for.
- **Both on:** pass 1 is v2 with the read set; each request checked (a device the incident does
  not name, the configuration class off), the allowed one run as the read-only account through
  the reads engine and recorded; pass 2 is v3 carrying the reads, its answer citing the read
  that ran accepted; every send logged; the incident's one step in the step log, drawn on its
  History row, and never one of the entry's steps (what Mercury tried stays Mercury's).
- **Pass 2 citing a refused read** is refused by Mercury's check: pass 1's answer is shown,
  said, and pass 2's call is recorded as refused by validation.
- **The can't-fix row** says what the loop asked for and links its first call on History.
"""
import json

import pytest

from modules import history_sources as HS
from modules.ai import calls, egress_classes, read_log, triggers
from modules.ai import router_reads as RR
from tests.test_ai_router_reads import Session
from tests.test_heal_analysis import (ANSWER, HA, SL, ai, analyse, cant_fix,  # noqa: F401
                                      lab, networks, turn_on)
from tests.test_heal_decide import GOLDEN

RO_PW = "ReadOnly-Pass-8812"
DEVICE = "edge-b"
INTENT = {"platform": "cisco_iosxe",
          "interfaces": [{"name": "GigabitEthernet4", "ipv4": "192.0.2.9 255.255.255.252"},
                         {"name": "GigabitEthernet2", "ipv4": "192.0.2.13 255.255.255.252"}]}
INVENTORY = [{"hostname": DEVICE, "ip": "192.0.2.6", "device_type": "cisco_xe",
              "role": "router", "_platform": "cisco-ios-xe", "_site": "lab"}]
SHOWN = "GigabitEthernet4 is up, line protocol is up\n  5 interface resets\n  0 input errors"


def _first(*reads):
    return dict(ANSWER, reads=list(reads))


def _ask(op, device=DEVICE, **args):
    return {"op": op, "args": dict(args, device=device), "why": "to see the port's resets",
            "hypothesis": "the port flaps on its own"}


def _second(cites=("tried:7", "read:1")):
    a = json.loads(json.dumps(ANSWER))
    a["hypotheses"][0]["evidence_refs"] = list(cites)
    a["hypotheses"][0]["claim"] = "The port resets on its own, the configuration aside."
    return a


@pytest.fixture
def device(ai, monkeypatch):
    """edge-b in Default's inventory, its committed intent and golden, the reads engine's
    session seams; the feature, the class and the account are each test's own."""
    session = Session()
    monkeypatch.setattr("modules.connection.with_plain_connection", session.plain)
    monkeypatch.setattr("modules.connection.with_temp_connection", session.temp)
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, c: SHOWN)
    monkeypatch.setattr(RR, "_committed", lambda network, hosts: ({DEVICE: INTENT},
                                                                  {DEVICE: GOLDEN}))
    return session


def _inventory(monkeypatch):
    # After the decision: the heal's own reads are faked (`Fake`), and the reads engine and the
    # read set's account check read this inventory.
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path: [dict(d) for d in INVENTORY])


def _class_on():
    got = egress_classes.turn_on_device_state("Default", "lab ten analysis reads",
                                              actor="admin@example.com",
                                              actor_verified="access", person=True)
    assert got.get("ok") is not False, got


def _account():
    from modules import credentials
    credentials.save_profile("default", username="netops", password="Deploy-Pass-5531")
    credentials.set_read_account("default", "mercury-ro", RO_PW, actor="admin@example.com",
                                 verified="access")


def _answers(ai, *answers):
    """The fake provider answers *answers* in order."""
    queue = list(answers)
    real = ai.send

    def send(body, key):
        ai.answer = queue.pop(0)
        return real(body, key)
    return send


def _data_of(body, name):
    import re
    m = re.search(rf'<data name="{name}">\n(.*?)\n</data>', body["messages"][0]["content"],
                  re.S)
    return m.group(1) if m else None


def _context_names(body):
    import re
    return re.findall(r'<context name="([^"]+)">',
                      "\n".join(b.get("text", "") for b in body["system"]))


def _rows():
    """The calls, oldest first (the record reads newest first)."""
    return list(reversed(calls.read()["rows"]))


class TestOff:
    def test_the_feature_off_sends_nothing_reads_nothing_and_the_step_says_so(
            self, ai, device, monkeypatch):
        _class_on()
        _account()
        inc = cant_fix()
        _inventory(monkeypatch)
        got = analyse(ai, inc)
        assert got["state"] == "off" and ai.sent == [] and device.signed == []
        assert read_log.read()["state"] == "absent", "no read asked for, none logged"
        (step,) = SL.advisories("Default")["by_incident"][inc]
        assert step["words"].startswith("AI analysis: not run: feature_off: the background "
                                        "feature heal_analysis is off for the network default")
        assert step["words"].endswith("nothing was sent")
        assert step["steps"][0]["step"] == "pass 1" and step["steps"][0]["result"] == "failed"

    def test_the_class_off_is_todays_one_call_and_the_step_says_why_no_read(
            self, ai, device, monkeypatch):
        turn_on()
        _account()
        inc = cant_fix()
        _inventory(monkeypatch)
        got = analyse(ai, inc)
        assert got["state"] == "answered" and len(ai.sent) == 1 and device.signed == []
        (row,) = _rows()
        assert (row["prompt"], row["schema"]) == ("heal_analysis.v1", "heal_analysis.v1")
        assert "read_set" not in _context_names(ai.sent[0])
        assert got["reads_said"]["words"].startswith(
            "AI analysis: reads not asked: the device state class is off for default: off by "
            "default")
        (step,) = SL.advisories("Default")["by_incident"][inc]
        assert step["words"] == got["reads_said"]["words"] and step["pass"] == 1


class TestTheLoop:
    def _run(self, ai, monkeypatch, second):
        turn_on()
        _class_on()
        _account()
        inc = cant_fix()
        _inventory(monkeypatch)
        before = SL.incident("Default", inc)
        send = _answers(ai, _first(_ask("interfaces", interface="GigabitEthernet4"),
                                   _ask("running_config"),
                                   _ask("interfaces", device="r9",
                                        interface="GigabitEthernet4")), second)
        got = HA.analyse("Default", inc, job="heal-notice-test", send=send, now=None)
        return inc, before, got

    def test_both_on_two_passes_the_allowed_read_run_as_the_read_only_account(
            self, ai, device, monkeypatch):
        # Under the installation's read-only choice (C3661: by default the AI's reads sign in
        # as Mercury's account, tests/test_ai_engineer_reads.py).
        monkeypatch.setattr("modules.nsot.reads.ai_reads_as", lambda: "read_only")
        inc, before, got = self._run(ai, monkeypatch, _second())
        assert got["state"] == "answered" and got["passes"] == 2, got.get("words")
        assert got["answer"]["hypotheses"][0]["cites"] == ["tried:7", "read:1"]
        assert len(ai.sent) == 2
        first, second = _rows()
        assert (first["prompt"], first["schema"]) == ("heal_analysis.v2", "heal_analysis.v2")
        assert (second["prompt"], second["schema"]) == ("heal_analysis.v3", "heal_analysis.v1")
        assert first["trigger"] == second["trigger"] == triggers.background(
            "heal_analysis", "heal-notice-test", "default", "heal_incident", inc)
        assert "read_set" in _context_names(ai.sent[0])
        assert _data_of(ai.sent[0], "mercury_reads") is None
        sent = {r["id"]: r for r in json.loads(_data_of(ai.sent[1], "mercury_reads"))}
        assert sent["read:1"]["answer"] == SHOWN
        assert "the configuration class is off for default" in sent["read:2"]["reason"]
        assert sent["read:3"]["reason"].startswith("interfaces's argument device: r9 is not a "
                                                   "device the incident names in Default")
        # Run as the read-only account, through the reads engine, recorded on History › Reads.
        assert device.signed == [{"host": DEVICE, "username": "mercury-ro", "password": RO_PW}]
        assert device.deploy == []
        from modules.nsot import reads
        (record,) = reads.runs("Default")["runs"]
        assert record["by"] == "ai_analysis" and record["commands"] == [
            "show interfaces GigabitEthernet4"]
        assert record["actor"] == "the AI analysis of incident " + inc + \
            ", turned on by admin@example.com"
        # Every send logged, its run named.
        (loop,) = read_log.loops()["loops"]
        assert loop["subject"]["id"] == inc and loop["network"] == "default"
        assert [e["verdict"] for e in loop["reads"]] == ["run", "refused", "refused"]
        assert loop["reads"][0]["run"] == record["id"]
        assert loop["reads"][0]["signed_in_as"]["username"] == "mercury-ro"
        assert loop["sent"]["left_host"] is True
        assert loop["first_call"] == first["id"] and loop["sent"]["second_call"] == second["id"]
        # The incident's one step, never one of the entry's steps.
        words = ("AI analysis: asked for 3 reads; 1 run, 2 refused; second pass answered")
        assert got["reads_said"]["words"] == words
        (step,) = SL.advisories("Default")["by_incident"][inc]
        assert step["words"] == words and step["calls"] == [first["id"], second["id"]]
        assert [s["step"] for s in step["steps"]] == ["pass 1", "check", "check", "reads",
                                                      "pass 2"]
        assert SL.incident("Default", inc)["steps"] == before["steps"], \
            "what Mercury tried stays Mercury's"
        assert SHOWN not in json.dumps(step)
        # Drawn on the incident's History row.
        ctx = {"ref": type("R", (), {"name": "Default", "data_dir": ""})(), "device": "",
               "members": None, "limit": 50, "since": None, "until": None, "call": ""}
        (row,) = HS.heal(ctx)["events"]
        rec = dict(row["record"])
        assert rec["AI analysis (advice; self-healing never reads it)"] == words
        assert rec["AI · reads"].startswith("ok: read:1 interfaces on edge-b: run (History › "
                                            "Reads " + record["id"] + ")")
        # The uses: pass 1's answer used for its reads, pass 2's shown.
        uses = calls.uses()
        assert uses[first["id"]][-1]["use"] == ("used: it asked for reads, and the second pass "
                                                "answered")
        assert uses[second["id"]][-1]["use"] == "shown: advisory analysis"
        kept = HA.latest("Default", inc)
        assert kept["calls"] == [first["id"], second["id"]] and kept["passes"] == 2
        assert kept["loop"] == loop["loop"]

    def test_pass_2_citing_a_refused_read_shows_pass_1s_answer_said(
            self, ai, device, monkeypatch):
        inc, _before, got = self._run(ai, monkeypatch, _second(cites=("tried:7", "read:2")))
        assert got["state"] == "answered" and got["passes"] == 1
        assert got["answer"]["hypotheses"][0]["cites"] == ["tried:7"], "pass 1's answer"
        assert got["reads_said"]["words"] == (
            "AI analysis: asked for 3 reads; 1 run, 2 refused; second pass refused by Mercury's "
            "check: the answer cites read:2, which Mercury refused: nothing of it was run or "
            "sent; the first pass's answer is shown")
        first, second = _rows()
        assert calls.uses()[second["id"]][-1]["use"] == "refused by validation"
        assert calls.uses()[first["id"]][-1]["use"] == "shown: advisory analysis"
        (step,) = SL.advisories("Default")["by_incident"][inc]
        assert step["steps"][-1]["step"] == "pass 2" and step["steps"][-1]["result"] == \
            "refused"

    def test_the_cant_fix_row_says_what_the_loop_asked_and_links_its_first_call(
            self, ai, device, monkeypatch):
        import app as A
        from flask import render_template
        inc, _before, got = self._run(ai, monkeypatch, _second())
        drawn = HA.drawn("Default", inc)
        b = drawn["block"]
        assert b["reads"] == got["reads_said"]["words"]
        assert b["reads_call"] == got["reads_said"]["first_call"]
        assert drawn["provenance"]["calls"] == 2
        with A.app.test_request_context("/"):
            html = render_template("v2/_heal_analysis.html", got=drawn, incident=inc)
        assert "AI analysis: asked for 3 reads; 1 run, 2 refused; second pass answered" in html
        assert f'href="/v2/history?call={b["reads_call"]}">History</a>' in html
        assert "2 background calls" in html

    def test_an_analysis_that_asked_for_no_read_draws_no_reads_line(self, ai, device,
                                                                     monkeypatch):
        turn_on()
        inc = cant_fix()
        got = analyse(ai, inc)
        b = HA.drawn("Default", inc)["block"]
        assert got["state"] == "answered" and b["reads"] == "" and b["reads_call"] == ""
