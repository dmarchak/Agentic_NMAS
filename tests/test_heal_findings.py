"""A saved script's verified fix is a verified fix to self-healing's findings (the correctness
review's G4-D5; `modules/nsot/saved_plans.py` `close_fixed`, `modules/heal/findings.py`
`_fixes`).

`findings._fixes` counts an incident closed on its fix's own device check by the moment that
check passed (its ``fixed`` ``epoch``). A saved script's run that verified closes its incident
through `close_fixed`; that close must carry the moment too, or the script's fix is no fix to
`later_fix` (a dry-run row it fixed keeps asking "Was that right?") and to `fights` (a script
that keeps fixing what something keeps undoing is never found).

No device, no network; the decision's sources are tests/test_heal_decide.py's `Fake`.
"""
from tests.test_heal_decide import DC, GOLDEN, I, ROUTE4, Fake, lab, settle  # noqa: F401
from tests.test_heal_policy import T0
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

NET = "Default"
RUNNING = GOLDEN + ROUTE4


def test_script_fix_counts_as_fix(lab):  # noqa: F811
    from modules.heal import decisions, findings
    from modules.nsot import saved_plans

    inc = settle(RUNNING, device="edge-b", claim=False)
    (d,) = DC.run(NET, now=T0, sources=Fake(RUNNING))["decided"]
    assert d["outcome"] == "would_heal", d
    closed = saved_plans.close_fixed(NET, inc["id"], {"id": "run-0001", "device": "edge-b"},
                                     {"key": "sp-1", "name": "restore the route"},
                                     by="a saved script")
    assert closed, "the script's verified run did not close its standing incident"
    incs = I.read(NET)["incidents"]
    got = [f for f in findings.verified_fixes(incs, decisions.decisions(NET))
           if f[3].get("id") == inc["id"]]
    assert len(got) == 1, (got, next(i for i in incs if i["id"] == inc["id"]).get("fixed"))
    at, device, _operation, _inc = got[0]
    assert device == "edge-b" and at > 0


def _healed_then(reopened: bool):
    """edge-b's heal applied healed at T0; its tail then failed and reopened its incident
    (`act.reopen_on_tail`: standing on ``tail_failed``, the close kept as ``reopened``), or
    did not (*reopened* False: the incident closed by that heal, as `incidents.close` keeps)."""
    from modules.heal.policy import _iso
    heal = {"id": "d-heal", "incident": "hi-d9", "device": "edge-b", "kind": "heal",
            "applied": {"outcome": "healed", "at": _iso(T0)}}
    inc = {"id": "hi-d9", "device": "edge-b", "state": "closed", "triggers": []}
    if reopened:
        inc.update(state="standing", reopened={"decision": "d-heal", "epoch": T0 + 60},
                   standing={"decision": "d-heal", "outcome": "tail_failed", "act": True})
    dry = {"id": "d-dry", "incident": "hi-d9", "epoch": T0 - 600}
    return dry, [inc], [heal, dry]


def test_a_heal_whose_tail_reopened_its_incident_is_no_later_fix():
    """The correctness review's G4-D9: a healed act whose tail then failed (its incident
    reopened, standing on ``tail_failed``) is no verified fix: `later_fix` does not close a
    dry-run row on it, and it counts toward no fight."""
    from modules.heal import findings

    dry, incs, decs = _healed_then(reopened=True)
    assert findings.later_fix(dry, incs, decisions=decs) == ()
    assert [f for f in findings.verified_fixes(incs, decs) if f[3]["id"] == "hi-d9"] == []


def test_a_heal_whose_tail_held_is_a_later_fix():
    from modules.heal import findings

    dry, incs, decs = _healed_then(reopened=False)
    got = findings.later_fix(dry, incs, decisions=decs)
    assert got and got[3]["id"] == "hi-d9", got
