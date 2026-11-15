"""C3733: an incident whose investigation ended in a missing capability restarts once, within
its caps, when the missing step becomes available (`ai.missing`'s rows keyed to their incident
and to what they wanted; `fixit.auto.capability_failures`, R1's reader). Also C3731's wording
of a state problem (`heal.said.headline`).

s1's err-disabled port (tests/test_errdisable.py's captures and store): its gap recorded while
Mercury had no step for an err-disabled port restarts ONCE when the err-disable plan is
registered, never twice. No device, no network, no AI.
"""
import pytest

from modules.ai import missing
from modules.heal import catalog
from tests import test_errdisable as T
from tests.test_errdisable import store  # noqa: F401 (the fixture)


class Gap:
    what = "recover the err-disabled port once its BPDU source is gone"
    evidence_refs = ["logs:1"]


class Answer:
    gap = Gap()


@pytest.fixture
def s1(store, monkeypatch):  # noqa: F811
    """s1's open err-disable incident, classified, with a troubleshooting record; its gap
    recorded while no step fixed an err-disabled port (the plan not yet registered)."""
    from modules import incident_page
    from modules.fixit import incident as F
    from modules.fixit import section

    # s1's identity as its manifest would give it (the store holds no manifest).
    monkeypatch.setattr(section, "_identity", lambda network, device: f"uid:{device}-0001")
    iid = T.opened("Critical syslog received")["incident"]
    T.opened("Interface down", "GigabitEthernet1/0", at=T.AT + 20)
    T.E.reclassify_step(T.NET, sources=T.Src(), now=T.AT + 600)
    found = incident_page.resolve(T.NET, iid)
    inc = section.incident_of(T.NET, found)["incident"]
    monkeypatch.setattr(missing, "path", lambda: str(store / "ai_missing.jsonl"))
    before = {k: v for k, v in catalog.capabilities().items() if k != "errdisable-recover"}
    with monkeypatch.context() as m:
        m.setattr(missing, "capabilities", lambda: before)
        rows = missing.wanted(Answer(), [], feature="fixit_troubleshoot", network=T.NET,
                              about=("incident", iid), condition="err_disabled")
    assert missing.record(rows)["recorded"] == 1
    F.record_proposal(inc, "mercury", words="no step recovers an err-disabled port")
    return iid, inc


class TestTheRestart:
    def test_the_gap_restarts_once_when_the_plan_exists_never_twice(self, s1):
        from modules.fixit import auto
        from modules.fixit import incident as F
        iid, inc = s1
        (f,) = auto.capability_failures(T.NET, inc)
        assert f["key"].startswith("capability:") and f["now"] == ["errdisable-recover"]
        listed = next(p for p in auto.pending(T.NET)["incidents"] if p["id"] == iid)
        assert f["key"] in {x["key"] for x in listed["failures"]}
        assert F.claim_start(inc, f["key"], trigger="auto", state="started") is not None
        assert F.claim_start(inc, f["key"], trigger="auto", state="started") is None, \
            "its start is keyed to the record: never twice"
        assert not [i for i in auto.catch_up(T.NET)["items"] if i["id"] == iid]

    def test_nothing_restarts_while_the_step_is_still_missing(self, s1, monkeypatch):
        from modules.fixit import auto
        _iid, inc = s1
        now = {k: v for k, v in catalog.capabilities().items() if k != "errdisable-recover"}
        monkeypatch.setattr(missing, "capabilities", lambda: now)
        assert auto.capability_failures(T.NET, inc) == []

    def test_a_row_is_keyed_to_its_incident_and_what_it_wanted(self, s1):
        iid, _inc = s1
        (row,) = missing.for_incident(iid)
        assert row["id"] == missing.row_id({"kind": "incident", "id": iid}, "operation",
                                           Gap.what)
        assert row["wants"]["condition"] == "err_disabled"
        assert "errdisable-recover" not in row["wants"]["known"]


class TestAStateProblemIsSaidAsOne:
    def d(self, **kw):
        return dict({"device": "s1", "outcome": "cant_fix", "tier": 3, "kind": "unknown_cause",
                     "headline": "x"}, **kw)

    def test_an_err_disabled_port_is_its_state_not_its_config(self):
        from modules.heal import said
        got = said.headline(self.d(problem={"condition": "err_disabled", "object": "Gi1/0"}))
        assert got.endswith("s1's config is as intended; the port's state is the problem "
                            "(err-disabled)"), got

    def test_a_physical_departure_is_the_links_state(self):
        from modules.heal import said
        got = said.headline(self.d(kind="physical"))
        assert got.endswith("the link's state is the problem (down)"), got

    def test_an_unknown_cause_with_no_state_keeps_its_words(self):
        from modules.heal import said
        assert "no fix on s1 can cure it" in said.headline(self.d())
