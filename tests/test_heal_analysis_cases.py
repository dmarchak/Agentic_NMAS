"""The AI analysis of a can't-fix, its recorded cases (board H, part H13; docs/HEAL_TO_INTENT.md
section 12; tests/fixtures/ai_cases/heal_analysis/recorded.json; `cases.heal_analysis_misses`,
`cases.heal_analysis_unready`; scripts/nmas-heal-cases). No call: the judge runs on planted
results against a planted pack, and the recording is shown to stop before anything is asked.

- **The set:** three cases, C4 (won't fix, a security ACL), I5 (physical) and V1 (rolled
  back), on the task's pinned model and prompt, each waiting for its walk's captured pack
  (section 15's walks 7, 8 and 9), its expectations written before any capture or run.
- **Not ready stops it:** a case with no pack, or an expected citation its pack does not
  hold, is said by case, and the recording asks nothing and spends nothing.
- **The judge is Explain's:** the honest C4 answer (the ACL, citing what Mercury tried)
  passes; a cable blamed, an answer citing no tried step, a refusal and no answer each miss.
- **Capture** reads the incident's newest kept analysis's pack, never types one.
"""
import copy
import importlib.machinery
import importlib.util
import os

import pytest

from modules.ai import cases

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, "tests", "fixtures", "ai_cases", "heal_analysis", "recorded.json")
SET = cases.load(FILE)
BY = {c["key"]: c for c in SET["cases"]}
#: A pack's sections as the incident's pack holds them (`evidence_pack.build_incident`), cut
#: to the references a case cites: what Mercury tried, and the logs.
PACK = {"id": "ep-00000000000000000000-h", "device": "r6", "network": "Default",
        "sections": [{"name": "tried", "ref": "tried", "state": "ok",
                      "pieces": [{"ref": f"tried:{n}", "what": "step"} for n in range(1, 8)]},
                     {"name": "logs", "ref": "logs", "state": "ok",
                      "pieces": [{"ref": "logs:1", "text": "%OSPF-5-ADJCHG"}]}]}


def answered(claim, cites, nxt="show ip access-lists"):
    return {"state": "answered", "answer": {
        "rationale": "Self-healing stopped at a security ACL, which a person decides.",
        "needs_human": True, "hypotheses": [{"claim": claim, "cites": cites, "next": nxt}]}}


def _script():
    loader = importlib.machinery.SourceFileLoader(
        "nmas_heal_cases", os.path.join(ROOT, "scripts", "nmas-heal-cases"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


class TestTheSet:
    def test_three_cases_on_the_pinned_model_and_prompt_each_awaiting_its_walk(self):
        from modules.ai import heal_analysis as HA
        from modules.ai import profiles
        assert sorted(BY) == ["C4", "I5", "V1"]
        assert SET["model"] == profiles.task(HA.FEATURE)["model"]
        assert tuple(SET["prompt"]) == tuple(HA.PROMPT)
        assert [(c["key"], c["walk"]) for c in SET["cases"]] == [("C4", 7), ("I5", 8),
                                                                 ("V1", 9)]
        for c in SET["cases"]:
            assert c["pack"] is None and c["awaiting"], c["key"]
            assert c["expect"]["outcome"] == ["answer"] and c["expect"]["says_any"]
            assert c["expect"]["needs_human"] is True, "a can't-fix always needs a person"

    def test_the_label_stays_unmeasured_until_the_runs_write_it(self):
        from modules.ai import heal_analysis as HA
        assert HA.MEASURED is None and HA.beta()["state"] == "not_measured"


class TestNotReady:
    def test_each_case_without_a_pack_is_said_with_its_walk(self):
        got = _script().check(ROOT)
        assert len(got) == 3 and got[0].startswith("case 1 (C4): no pack captured yet: walk 7")

    def test_a_pack_that_holds_none_of_the_lead_citations_is_said(self):
        case = dict(BY["C4"], pack={"sections": [{"name": "logs", "ref": "logs",
                                                  "pieces": [{"ref": "logs:1"}]}]})
        assert cases.heal_analysis_unready(case) == [
            "case 1 (C4): its pack holds none of ['tried:*']"]
        assert cases.heal_analysis_unready(dict(BY["C4"], pack=PACK)) == []

    def test_the_recording_asks_nothing_while_a_case_is_not_ready(self, tmp_path, monkeypatch):
        from modules.ai import heal_analysis as HA
        monkeypatch.setattr(HA, "ask_prepared", lambda *a, **k: pytest.fail("asked"))
        s = _script()
        assert s.record(ROOT, "Default", "", str(tmp_path / "out.json"), 10, 2.0,
                        yes=True) == 5
        assert not (tmp_path / "out.json").exists()

    def test_out_inside_the_checkout_is_refused(self):
        assert _script().record(ROOT, "Default", "", os.path.join(ROOT, "x.json"), 1, 2.0,
                                yes=True) == 2


class TestTheJudge:
    def test_the_honest_c4_answer_passes(self):
        got = answered("An inbound access list on r6 Gi2 permits TCP and UDP only, so OSPF "
                       "is dropped.", ["tried:5", "logs:1"])
        assert cases.heal_analysis_misses(BY["C4"]["expect"], got, PACK) == []

    def test_a_cable_blamed_with_no_tried_step_misses(self):
        got = answered("A cable fault on r6 Gi2 dropped the adjacency.", ["logs:1"],
                       "show interfaces GigabitEthernet2")
        misses = cases.heal_analysis_misses(BY["C4"]["expect"], got, PACK)
        assert any("the leading hypothesis cites none of ['tried:*']" in m for m in misses)
        assert any(m.startswith("no hypothesis names acl") for m in misses), misses

    def test_saying_self_healing_will_remove_it_misses(self):
        got = answered("The ACL on Gi2 is outside intent; self-healing will remove it.",
                       ["tried:5"])
        assert any("self-healing will remove" in m
                   for m in cases.heal_analysis_misses(BY["C4"]["expect"], got, PACK))

    def test_a_refusal_and_no_answer_each_miss(self):
        refused = {"state": "unanswerable", "detail": "nothing bears on it"}
        assert cases.heal_analysis_misses(BY["C4"]["expect"], refused, PACK) == [
            "outcome refuse, expected one of ['answer']"]
        off = {"state": "off", "words": "AI analysis: not run, off for this network"}
        assert cases.heal_analysis_misses(BY["C4"]["expect"], off, PACK) == [
            "no answer: AI analysis: not run, off for this network"]

    def test_the_i5_case_misses_an_acl_blamed_on_a_physical_fault(self):
        pack = copy.deepcopy(PACK)
        got = answered("An access list dropped OSPF on r3 Gi4.", ["tried:3"],
                       "show ip interface GigabitEthernet4")
        misses = cases.heal_analysis_misses(BY["I5"]["expect"], got, pack)
        assert any("access list" in m for m in misses), misses


class TestCapture:
    def test_the_newest_kept_pack_is_read_never_typed(self, monkeypatch):
        from modules.ai import heal_analysis as HA
        rows = [{"row": "analysis", "incident": "hi-1", "state": "off", "pack": PACK,
                 "at": "2026-11-20T18:04:58Z"}]
        monkeypatch.setattr(HA, "read", lambda n: {"state": "ok", "rows": rows, "error": ""})
        got = _script().capture("Default", "hi-1")
        assert got["pack"] == PACK and got["state"] == "off"
        assert _script().capture("Default", "hi-2") == {
            "error": "no analysis of hi-2 is kept on Default"}
