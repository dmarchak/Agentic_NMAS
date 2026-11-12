"""AI troubleshooting's evaluation (the fix-it plan's S7; scripts/nmas-fixit-cases,
`fixit_troubleshoot.snapshot`, `request_of_case` and `case_result`, the script's `ask_case`, `cases.fixit_unready` and
`fixit_misses`; tests/fixtures/ai_cases/fixit_troubleshoot/). No live AI call: the provider is
replaced, the paid run is the operator's (E1).

- **The cases:** the committed files hold the plan's eight recorded and four blind cases, each
  with its expectation and none with a pack yet (each awaits its capture on the host), so
  ``--check`` says every one not ready and nothing is asked; their model is the task's pin.
- **A capture is the request the press sends:** built on the lab's real incident by Mercury's
  own code and kept as a case (the note left out), its replay asks exactly what the press asks,
  with the case's own note.
- **The judge:** the expected operation and parameters, a gap, no fix, a forbidden repeat, the
  citations each case must hold, no device outside the case, no command; an answer Mercury's
  check refused is a miss.
- **The runner:** ``--out`` inside the checkout, a person's address as the actor, a case not
  ready (nothing asked) and no ``--yes`` (the estimate, nothing asked) each refused; a recorded
  run judged by case, its calls an evaluation's, past ``--stop-usd`` stopped, a refusal of
  Mercury's stopped.
"""
import importlib.machinery
import importlib.util
import json
import os
import types

import pytest

from modules.ai import cases

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "tests", "fixtures", "ai_cases", "fixit_troubleshoot")


def _script():
    loader = importlib.machinery.SourceFileLoader(
        "nmas_fixit_cases", os.path.join(ROOT, "scripts", "nmas-fixit-cases"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def answered(fix=None, gap=None, cites=("attempt:1",), needs_human=True, rationale="r"):
    return {"state": "answered", "why": "", "answer": {
        "outcome": "answer", "rationale": rationale, "needs_human": needs_human,
        "hypotheses": [{"claim": "c", "evidence_refs": list(cites), "confirm_with": "x"}],
        "fix": fix, "gap": gap, "why_not": ""}}


def resub(device="r7", subs=("101", "102")):
    return {"operation": "telemetry-resubscribe",
            "params": {"device": device, "subscriptions": list(subs), "subscription": None},
            "why": "w", "evidence_refs": ["attempt:1"]}


EXPECT_RESUB = {"operation": "telemetry-resubscribe",
                "params": {"device": "r7", "subscriptions": ["101", "102"]}}


# ── The committed cases ─────────────────────────────────────────────────────────────────────

class TestTheCases:
    def test_eight_recorded_and_four_blind_each_awaiting_its_capture(self):
        rec = cases.load(os.path.join(FOLDER, "recorded.json"))
        blind = cases.load(os.path.join(FOLDER, "blind.json"))
        assert [c["n"] for c in rec["cases"]] == list(range(1, 9))
        assert [c["n"] for c in blind["cases"]] == [101, 102, 103, 104]
        for c in rec["cases"] + blind["cases"]:
            assert c["pack"] is None and c["awaiting"] and c["expect"], c["key"]
            assert "configure terminal" in c["expect"].get("no_text", []), c["key"]

    def test_their_model_is_the_task_s_pin(self):
        from modules.ai import profiles
        off = [p for p in profiles.cases_off_pin(os.path.join(ROOT, "tests", "fixtures",
                                                              "ai_cases"))
               if "fixit_troubleshoot" in p[0]]
        assert off == []

    def test_check_says_every_one_not_ready_and_asks_nothing(self, capsys):
        assert _script().main(["--check"]) == 5
        said = capsys.readouterr().out
        assert "12 problem(s)" in said and "no pack captured yet" in said


# ── The judge ───────────────────────────────────────────────────────────────────────────────

class TestTheJudge:
    def test_the_expected_fix_passes_and_another_misses(self):
        assert cases.fixit_misses({"fix": EXPECT_RESUB}, answered(resub())) == []
        assert cases.fixit_misses({"fix": EXPECT_RESUB}, answered(resub(subs=("101",))))
        assert cases.fixit_misses({"fix": EXPECT_RESUB}, answered())

    @pytest.mark.parametrize("expect, got, said", [
        ({"gap": True}, answered(resub()), "expects a gap and no fix"),
        ({"gap": True}, answered(), "names no gap"),
        ({"no_fix": True}, answered(resub()), "expects no fix"),
        ({"not_fix": [dict(EXPECT_RESUB, why="attempt 1's")]}, answered(resub()), "forbids"),
        ({"cites_any": [["note:1"]]}, answered(gap={"what": "x", "evidence_refs": ["attempt:1"]}),
         "cites none of note:1"),
        ({"never_devices": ["r6"]}, answered(resub(device="r6")), "acts on r6"),
        ({"no_text": ["configure terminal"]},
         answered(rationale="run configure terminal then"), "'configure terminal'"),
        ({"needs_human": True}, answered(needs_human=False), "needs_human is False"),
        ({"fix": EXPECT_RESUB}, {"state": "unchecked", "why": "it acts on 103"}, "it acts on 103"),
    ], ids=["a fix for a gap", "no gap", "a fix for none", "a repeat", "a citation missing",
            "another device", "a command said", "needs a person", "refused by the check"])
    def test_each_rule_misses(self, expect, got, said):
        misses = cases.fixit_misses(expect, got)
        assert misses and any(said in m for m in misses), misses

    def test_a_section_wildcard_and_a_gap_pass(self):
        gap = {"what": "close the collector's session", "evidence_refs": ["attempt:1", "note:1"]}
        assert cases.fixit_misses({"gap": True, "cites_any": [["attempt:*"], ["note:1"]]},
                                  answered(gap=gap)) == []

    def test_unready_names_what_is_missing(self):
        case = {"n": 9, "key": "k", "pack": None, "awaiting": "its capture", "expect": {}}
        assert "no pack captured yet: its capture" in cases.fixit_unready(case)[0]
        pack = {"checked_sections": [{"ref": "attempts", "pieces": [{"ref": "attempt:1"}]}]}
        case = dict(case, pack=pack, expect={"cites_any": [["seen_before:1"]], "fix": {
            "operation": "telemetry-readd", "params": {"device": "<the case's device>"}}})
        got = cases.fixit_unready(case)
        assert any("holds none of ['seen_before:1']" in g for g in got)
        assert any("to be filled from its capture" in g for g in got)
        assert cases.fixit_unready(dict(case, note="n", expect={"cites_any": [["note:1"]]})) == []


# ── A capture, and its replay, on the lab's real incident ───────────────────────────────────

from tests.test_fixit_troubleshoot import ai, answer, fix, stopped  # noqa: E402,F401
from tests.test_fixit_section_v2 import NET, web  # noqa: E402,F401 (the fixture `ai` builds on)
from tests.test_heal_resubscribe import lab  # noqa: E402,F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: E402,F401 (the fixture `lab` builds on)


def captured(ai):  # noqa: F811
    iid = stopped(ai)
    got = _script().capture(NET, iid)
    assert "pack" in got, got
    return iid, got["pack"]


def test_a_capture_is_the_request_the_press_sends_and_its_replay_asks_it(ai):  # noqa: F811
    """The request built for the incident, kept as a case (JSON, the note left out), is asked
    again with the case's own note: the same parts and context the press sends, the note
    the typed part, under an evaluation's trigger; the answer held to the same check."""
    from modules.ai import fixit_troubleshoot as T
    from modules.ai import triggers
    _iid, pack = captured(ai)
    assert json.loads(json.dumps(pack)) == pack and "note" not in pack["data"]
    assert pack["incident"]["device"] == "r2" and pack["actable"] == ["r2", "101", "102"]
    ai.answer = answer(fix(device="r2"))
    prep = T.request_of_case(pack, "the collector holds a dead session")
    got = _script().ask_case(prep, trigger=triggers.evaluation("evaluation:fixit-test"))
    assert got["state"] == "answered", got
    assert got["answer"]["fix"]["operation"] == "telemetry-resubscribe"
    (body,) = ai.sent
    text = body["messages"][0]["content"]
    assert "the collector holds a dead session" in text and '"name":"attempts"' in text
    from modules.ai import calls
    (row,) = [r for r in calls.read()["rows"] if r["id"] == got["call_id"]]
    assert row["trigger"]["kind"] == "evaluation" and row["actor"] == "evaluation:fixit-test"
    assert row["prompt"] == "fixit_troubleshoot.v1"
    # A case's note is the typed part as the press's is: a secret in it masked as it leaves.
    secret = "$9$abcdefghijklmn$opqrstuvwxyz0123456789ABCDEFG"
    masked = _script().ask_case(T.request_of_case(pack, f"it had enable secret 9 {secret} on it"),
                        trigger=triggers.evaluation("evaluation:fixit-test"))
    assert "opqrstuvwxyz0123456789" not in json.dumps(ai.sent[-1])
    (row,) = [r for r in calls.read()["rows"] if r["id"] == masked["call_id"]]
    assert row.get("typed_masked"), "masked as the person's own words, and said"


@pytest.mark.parametrize("given, said", [
    ({"subscriptions": ("101", "103")}, "103"),
    ({"cites": ("seen_before:2",)}, "seen_before:2"),
], ids=["outside the actable set", "a citation not sent"])
def test_a_replayed_answer_out_of_scope_is_refused_by_the_same_check(ai, given, said):  # noqa: F811
    from modules.ai import fixit_troubleshoot as T
    from modules.ai import triggers
    _iid, pack = captured(ai)
    ai.answer = answer(fix(device="r2", **given))
    got = _script().ask_case(T.request_of_case(pack), trigger=triggers.evaluation("evaluation:t"))
    assert got["state"] == "unchecked" and said in got["why"], got
    assert cases.fixit_misses({"fix": EXPECT_RESUB}, got)


# ── The runner ──────────────────────────────────────────────────────────────────────────────

def _checkout(tmp_path, pack, expect=None, n_blind=0):
    """A checkout's case files with one recorded case (and *n_blind* blind ones) on *pack*."""
    folder = tmp_path / "co" / "tests" / "fixtures" / "ai_cases" / "fixit_troubleshoot"
    folder.mkdir(parents=True)
    case = {"n": 1, "key": "k", "title": "t", "pack": pack, "note": "", "awaiting": "",
            "expect": expect or {"fix": dict(EXPECT_RESUB, params={
                "device": "r2", "subscriptions": ["101", "102"]})}}
    head = {"task": "fixit_troubleshoot", "prompt": ["fixit_troubleshoot", 1],
            "model": "claude-sonnet-5-5", "source": "s", "bar": "b"}
    (folder / "recorded.json").write_text(json.dumps(dict(head, cases=[case])))
    blind = [dict(case, n=100 + i) for i in range(n_blind)]
    (folder / "blind.json").write_text(json.dumps(dict(head, cases=blind)))
    return str(tmp_path / "co")


class TestTheRunner:
    def test_out_inside_the_checkout_and_a_person_s_address_are_refused(self, tmp_path):
        S = _script()
        co = _checkout(tmp_path, {"checked_sections": []})
        assert S.record(co, "", os.path.join(co, "x.json"), 1, 1.0, True) == 2
        assert S.record(co, "op@example.invalid", str(tmp_path / "o.json"), 1, 1.0, True) == 2

    def test_a_case_not_ready_asks_nothing(self, tmp_path, capsys):
        S = _script()
        co = _checkout(tmp_path, None)
        sent = []
        assert S.record(co, "", str(tmp_path / "o.json"), 1, 1.0, True,
                        send=lambda b, k: sent.append(b)) == 5
        assert sent == [] and not (tmp_path / "o.json").exists()

    def test_without_yes_it_prints_the_estimate_and_asks_nothing(self, ai, tmp_path,  # noqa: F811
                                                                 capsys):
        S = _script()
        _iid, pack = captured(ai)
        co = _checkout(tmp_path, pack, n_blind=1)
        assert S.record(co, "", str(tmp_path / "o.json"), 10, 4.0, False) == 6
        said = capsys.readouterr().out
        assert "20 call(s), about $" in said and "at most $" in said and ai.sent == []

    def test_a_run_is_judged_by_case_and_recorded_as_an_evaluation(self, ai, tmp_path):  # noqa: F811
        S = _script()
        _iid, pack = captured(ai)
        co = _checkout(tmp_path, pack, n_blind=1)
        ai.answer = answer(fix(device="r2"))
        out = tmp_path / "o.json"
        assert S.record(co, "evaluation:t1", str(out), 2, 4.0, True) == 0
        got = json.loads(out.read_text())
        assert len(ai.sent) == 4 and got["actor"] == "evaluation:t1"
        assert {s["n"]: s["reliable"] for s in got["summary"]} == {1: True, 100: True}
        assert got["blind_share"] == 1.0 and got["met"] is True

    def test_past_stop_usd_it_stops(self, ai, tmp_path):  # noqa: F811
        S = _script()
        _iid, pack = captured(ai)
        co = _checkout(tmp_path, pack)
        ai.answer = answer(fix(device="r2"))
        assert S.record(co, "", str(tmp_path / "o.json"), 5, 0.000001, True) == 4
        assert len(ai.sent) == 1

    def test_a_refusal_of_mercury_s_stops_with_nothing_more_spent(self, ai, tmp_path,  # noqa: F811
                                                                    monkeypatch):
        S = _script()
        _iid, pack = captured(ai)
        co = _checkout(tmp_path, pack)
        from modules.ai import gateway
        monkeypatch.setattr(gateway, "hosted_allowed",
                            lambda: {"allowed": False, "why": "hosted AI is off"})
        assert S.record(co, "", str(tmp_path / "o.json"), 3, 4.0, True) == 3
        assert ai.sent == []
