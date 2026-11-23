"""The BLUF table (the operator's R2, 2026-11-14; `modules/bluf.py`), keyed by PROBLEM (R4,
"Incidents are problems, not signals"; `modules/problem.py`): every signal kind the code
declares classifies to a problem condition, and every condition has its what, impact and fix,
enumerated from the code's own declarations, never a list typed here; the table's words use only
the problem's fields; severity from impact (critical only for a network outage); the title is the
problem, the alerts its evidence; a guard or hold working as designed is one plain line.
"""
import ast
import os

import pytest

from modules import bluf as B
from modules import problem as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestEveryProblemHasItsThreeLines:
    def test_the_population_is_the_codes_own_and_has_its_floor(self):
        from modules.heal import incidents, kinds
        got = B.declared_kinds()
        # G7 (C3712): the err-disabled port's signal is declared beside the lost stream's.
        assert set(got["signals"]) == (set(incidents.CAUSE_KINDS) | set(incidents.SYMPTOM_KINDS)
                                       | {P.LOST_STREAM, P.ERR_DISABLE} | set(kinds.TIER))
        assert len(got["signals"]) >= 25 and len(got["conditions"]) >= 20
        assert {"telemetry_lost", "neighbour_down", "changed_outside_mercury",
                "departs_from_golden", "link_down"} <= set(got["conditions"])
        assert set(got["conditions"]) <= set(P.CONDITIONS)

    def test_no_problem_lacks_what_impact_or_fix(self):
        assert B.missing() == []

    def test_an_unconfirmed_err_disable_report_is_its_own_problem_no_saved_fix_matches(self):
        """7cc49a1b made the err-disable syslog line a trigger kind (``errdisable``) with no
        problem condition: its incident had no BLUF until the port's confirming read. It is
        classified as reported (`problem.UNCONFIRMED`), with its three lines, and no saved
        fix may name it, so no fix is offered, or fires in Auto, before that read; the
        confirmed port stays `err_disabled`, which a fix may match."""
        from modules import fix_editor
        from modules.nsot import saved_plans
        assert P.CONDITION_OF["errdisable"] == "err_disable_reported"
        assert P.CONDITION_OF[P.ERR_DISABLE] == "err_disabled"
        assert B.TABLE["err_disable_reported"]["fix"] == "none"
        assert "err_disable_reported" not in P.MATCHABLE and "err_disabled" in P.MATCHABLE
        assert saved_plans.match_refusal({"condition": "err_disable_reported"})
        assert saved_plans.match_refusal({"condition": "err_disabled"}) == ""
        from werkzeug.datastructures import MultiDict
        opts = {"causes": [], "roles": [], "lines": [], "checks": {"pre": [], "ver": []}}
        assert fix_editor.draft_from_form(MultiDict({"condition": "err_disable_reported"}),
                                          opts)["match"] == {}
        assert fix_editor.draft_from_form(MultiDict({"condition": "err_disabled"}),
                                          opts)["match"] == {"condition": "err_disabled"}

    def test_a_planted_signal_with_no_problem_is_found(self, monkeypatch):
        from modules.heal import kinds
        monkeypatch.setitem(kinds.TIER, "planted_kind", 1)
        assert ("planted_kind", "no problem condition") in B.missing()

    def test_a_planted_condition_with_no_entry_is_found(self, monkeypatch):
        monkeypatch.setitem(P.CONDITION_OF, "adjacency", "planted_condition")
        assert ("planted_condition", "no entry") in B.missing()

    @pytest.mark.parametrize("part", ["what", "impact", "fix"])
    def test_an_entry_missing_a_part_is_found(self, part):
        table = dict(B.TABLE, neighbour_down=dict(B.TABLE["neighbour_down"], **{part: ""}))
        assert ("neighbour_down", f"no {part}") in B.missing(table)

    def test_no_line_is_one_of_mercurys_codes(self):
        codes = ("CONFIG_I", "g4", "cant_fix", "departs (-", "guard 4", "_", "UTC")
        for cond, e in B.TABLE.items():
            for part in ("what", "impact"):
                text = e[part]
                for f in P.FIELDS:
                    text = text.replace("{" + f + "}", "")
                assert not any(c in text for c in codes), (cond, part, text)


class TestOnlyTheProblemsFields:
    """bluf.py names no field of a problem but `problem.FIELDS`: in its table's templates, and
    as an attribute of a problem in its code."""

    def _attrs(self, source: str) -> set:
        out = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id == "p":
                out.add(node.attr)
        return out

    def test_the_tables_templates_name_only_problem_fields(self):
        for cond, e in B.TABLE.items():
            for part in ("what", "impact"):
                assert B.placeholders(e[part]) <= set(P.FIELDS), (cond, part)

    def test_a_planted_template_field_is_found(self):
        table = dict(B.TABLE, link_down=dict(B.TABLE["link_down"],
                                             what="{device}: {alert_name} down"))
        assert any(c == "link_down" and "alert_name" in why for c, why in B.missing(table))

    def test_the_code_reads_only_problem_fields(self):
        with open(os.path.join(ROOT, "modules", "bluf.py"), encoding="utf-8") as fh:
            source = fh.read()
        used = self._attrs(source)
        assert used, "the scan's floor: bluf.py reads its problem"
        assert used <= set(P.FIELDS) | {"as_dict"}, used - set(P.FIELDS)
        assert "alert" in self._attrs("p.alert\np.device\n")

    def test_the_schema_is_one_dataclass_of_exactly_its_fields(self):
        import dataclasses
        assert tuple(f.name for f in dataclasses.fields(P.Problem)) == P.FIELDS


class TestTheLines:
    def found(self):
        """A planted lost-stream incident record (a fixture): r7's subscriptions 101 and 102."""
        from tests.test_heal_diagnose_stream import stream_alert
        trig = [dict(stream_alert(s), epoch=1_794_250_000.0 + n, at="2026-11-14T09:30:05Z")
                for n, s in enumerate(("101", "102"))]
        return {"incident": {"id": "hi-000000000001", "device": "r7", "triggers": trig,
                             "state": "standing"}, "entry": {}, "decisions": []}

    def test_a_lost_stream_is_titled_by_its_problem_with_its_alerts_as_evidence(self):
        found = self.found()
        for t in found["incident"]["triggers"]:
            t["device"] = "r7"
        got = B.bluf(B.model_of(found))
        assert got["problem"]["condition"] == "telemetry_lost"
        assert got["what"] == "r7: telemetry streams 101 and 102 lost"
        assert got["impact"] == "Mercury can't see r7's interfaces or CPU; traffic is unaffected"
        assert got["title"] == ("r7: telemetry streams 101 and 102 lost: Mercury can't see r7's "
                                "interfaces or CPU; traffic is unaffected")
        assert got["since"] == "2026-11-14T09:30:05Z", "an ISO instant the page localises"
        assert "UTC" not in got["what"] and len(got["evidence"]) == 2
        assert got["severity"] == "warning"

    def test_severity_is_critical_only_for_a_measured_outage(self):
        # No entry claims an outage it did not measure (the review of 2026-11-14).
        assert not [k for k, e in B.TABLE.items() if e["effect"] == "outage"]
        assert set(B.OUTAGE_CAPABLE) <= set(B.TABLE)
        for cond in B.TABLE:
            assert B.severity(cond) != "critical", cond
            assert (B.severity(cond, outage_measured=True) == "critical") == (
                cond in B.OUTAGE_CAPABLE), cond
        assert B.severity("telemetry_lost", outage_measured=True) == "warning"
        assert B.severity("a condition nobody declared") == "warning"
        p = P.Problem("r2", "a link", "link_down")
        assert B.bluf({"problem": p})["severity"] == "warning"
        assert B.bluf({"problem": p, "outage_measured": True})["severity"] == "critical"

    def test_the_next_action_given_is_the_fix(self):
        nxt = {"kind": "start", "label": "Start AI troubleshooting", "href": "/v2/x"}
        got = B.bluf({"problem": P.Problem("r2", "a link", "link_down"), "next": nxt})
        assert got["fix"] == nxt and got["what"] == "r2: a link is down while it is meant to be up"

    def test_a_problem_the_table_lacks_says_so_plainly(self):
        got = B.bluf({"problem": P.Problem("r2", "x", "nonesuch")})
        assert got["what"] == "r2: something happened" and "not known" in got["impact"]


class TestHoldLines:
    def test_guard_4_in_the_operators_words(self):
        hit = {"guard": 4, "operands": {"lines": ["+ a", "- b"], "lines_more": 0}}
        assert B.hold_line(hit, "r7") == (
            "Self-healing won't write to r7 until its saved config matches intent (2 lines "
            "differ). This doesn't block the fix below.")

    def test_every_guard_has_its_plain_line(self):
        from modules.heal.policy import GUARDS
        assert {n for n, _name, _keys in GUARDS} == set(B.HOLD_LINES)
        for n in B.HOLD_LINES:
            line = B.hold_line({"guard": n, "operands": {}}, "r2")
            assert line and "{" not in line and "guard" not in line.lower(), (n, line)

    def test_a_hold_that_refused_the_fix_says_it_blocks_it(self):
        hit = {"guard": 3, "operands": {}}
        assert B.hold_line(hit, "r2", blocks=True).endswith("This blocks the fix below until it "
                                                           "ends.")
        assert B.hold_line(hit, "r2").endswith("This doesn't block the fix below.")

    def test_no_hit_is_no_line(self):
        assert B.hold_line({}, "r2") == "" and B.hold_line(None, "r2") == ""
