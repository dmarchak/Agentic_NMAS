"""A command plan its own precondition refused, nothing sent, is "skipped: nothing to fix",
never a Needs attention row (C3821), and a status that is not the AI's never draws as the
AI's (C3822): 811bbe36 (the operator, 2026-11-16; `modules/nsot/receipts.py` `skipped`,
`past`, `modules/attention.py` `deploy_source`, `modules/incidents_list.py` `_fixit_of`). The
debt pass, 2026-11-18 (docs/FAST_LANE_DEBT.md's row for 811bbe36).

- **Skipped:** s2's receipt shape (a command plan refused at ``pre_apply``, nothing sent) is
  skipped, said "Skipped: nothing to fix" on History and no row on Needs attention; one that
  sent, or another action refused there, is still a row.
- **The AI's status:** the Incidents row says the AI's state only while an AI result stands:
  investigating, or ended with the AI's own finding; an investigation ready to start again,
  or a status whose source is not the AI's, draws no AI status.
No device, no store: the receipts handed to the source as its read hands them, the section's
view planted as `section.view` returns it.
"""
import pytest

from modules import attention as A
from modules import incidents_list as L
from modules.nsot import receipts

AT = "2026-11-16T01:12:00Z"


def receipt(**over) -> dict:
    """s2's 01:12 UTC receipt's shape: a command plan its precondition refused, nothing sent."""
    return dict({"device": "s2", "action": "command_plan", "stage": "pre_apply",
                 "outcome": "failed", "sent": False, "at": AT,
                 "error": "a precondition refused: the port is not err-disabled"}, **over)


def rows_of(*rs):
    return [r for r in A.deploy_source(read=lambda: {"state": "ok", "rows": list(rs)})["rows"]
            if "s2" in (r.get("devices") or [])]


class TestSkipped:
    @pytest.mark.parametrize("outcome", ["failed", "refused"])
    def test_a_precondition_refusal_that_sent_nothing_is_skipped_and_no_row(self, outcome):
        r = receipt(outcome=outcome)
        assert receipts.skipped(r)
        assert receipts.past(r) == "Skipped: nothing to fix"
        assert rows_of(r) == []

    @pytest.mark.parametrize("over", [{"sent": True}, {"stage": "verify"},
                                      {"action": "deploy"}])
    def test_anything_else_refused_or_failed_is_still_a_row(self, over):
        r = receipt(**over)
        assert not receipts.skipped(r)
        assert len(rows_of(r)) == 1, over


class TestTheAIsStatus:
    def fixit(self, monkeypatch, view):
        from modules.fixit import incident as F
        from modules.fixit import section

        # The row reads the section as its page draws it (`section.drawn`, C4086), which asks
        # `view` with the page's resolved, ended and now.
        monkeypatch.setattr(section, "view", lambda network, found, **kw: dict(view))
        monkeypatch.setattr(section, "incident_of", lambda network, found: {
            "incident": object()})
        monkeypatch.setattr(F, "starts", lambda inc: {"starts": [
            {"state": "started", "epoch": 1_790_000_000.0}]})
        return L._fixit_of("Default", {"id": "hi-000000000001"})["ai"]

    def test_investigating_and_ended_with_the_ais_own_finding_are_the_ais(self, monkeypatch):
        assert self.fixit(monkeypatch, {"state": "investigating"})["words"] == \
            "AI investigating"
        got = self.fixit(monkeypatch, {"state": "answered", "status_source": "AI",
                                       "status": "s1 Gi1/0 was err-disabled by BPDU guard."})
        assert (got["state"], got["source"], got["words"]) == (
            "ended", "AI", "s1 Gi1/0 was err-disabled by BPDU guard.")

    @pytest.mark.parametrize("view", [
        {"state": "ready", "status_source": "AI", "status": "an old finding"},
        {"state": "none"},
        {"state": "answered", "status_source": "Mercury",
         "status": "Mercury has no fix it runs by itself; held by guard 4"}])
    def test_a_status_not_the_ais_draws_no_ai_status(self, monkeypatch, view):
        assert self.fixit(monkeypatch, view) is None
