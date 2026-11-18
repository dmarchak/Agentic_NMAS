"""Timing laps change nothing sent and never raise (0093fb8b, speed pass round 1, the operator's
word of 2026-11-17; the debt pass of 2026-11-18, docs/FAST_LANE_DEBT.md).

THE plan (`routes.deploy.plan_devices`) planned with a laps record is the plan planned without
one, byte for byte (its program, both hashes, what it holds back); the laps it fills name the
plan's own steps in order; `pipeline.lap` with no record does nothing and with one never
raises; `command_plan_run._laps` turns the marks into each step's seconds. On
tests/test_committed_before_p1.py's host (Lab's r2 and s1, golden, intent, the shipped
templates). No device, no network.
"""
from tests.test_committed_before_p1 import host  # noqa: F401 (the fixture)

#: What a plan entry carries that the person confirms or the apply recomputes.
CONFIRMED = ("commands", "command_hash", "capture_hash", "deployable", "authorisation_ok")


def test_a_plan_with_laps_is_the_plan_without(host):  # noqa: F811
    from routes.deploy import plan_devices

    plain = plan_devices("Lab", ["r2", "s1"])
    laps = []
    timed = plan_devices("Lab", ["r2", "s1"], laps=laps)
    assert [e["device"] for e in timed] == [e["device"] for e in plain]
    for a, b in zip(plain, timed):
        assert {k: a.get(k) for k in CONFIRMED} == {k: b.get(k) for k in CONFIRMED}, a["device"]
        assert a == b, a["device"]
    names = [n for n, _at in laps]
    assert "plan: program" in names and names.index("plan: inventory rows") < names.index(
        "plan: program"), names


def test_a_lap_with_no_record_does_nothing_and_with_one_never_raises():
    from modules.pipeline import lap

    assert lap(None, "anything") is None
    laps = []
    lap(laps, "a step")
    lap(laps, 7)
    assert [n for n, _at in laps] == ["a step", "7"]
    assert all(isinstance(at, float) for _n, at in laps)


def test_the_marks_become_each_steps_seconds():
    from modules.nsot.command_plan_run import _laps

    assert _laps(None) == [] and _laps([]) == []
    assert _laps([("start", 100.0), ("read", 101.25), ("send", 104.0)]) == [
        {"lap": "read", "at_s": 1.2, "took_s": 1.2},
        {"lap": "send", "at_s": 4.0, "took_s": 2.8}]
