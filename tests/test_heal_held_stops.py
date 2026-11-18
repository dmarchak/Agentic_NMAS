"""A heal's stops once it waits for and holds its device, and the stops round 2 kept
(`modules/heal/act.py` `_stops`, `stopped_now`, `hold_device`; `modules/heal/decide.py`
`_outcome`), no network, no device. The debt pass of 2026-11-18 (docs/FAST_LANE_DEBT.md):

- **e400a31f** (items 1, 4 and 5): another operation holding the device is a declared wait;
  a Stop everywhere or an Off landing during the wait ends it, nothing sent; one landing
  between the last busy poll and the hold is caught by the stops judged again once held.
- **617ff2f0** (guard 3 and the heal's own hold): the stops judged once held do not count the
  act's own hold, while a person's planned window declared during the wait still refuses, and
  the check before the hold is unchanged.
- **70e89a47's kept stops** (round 2 of the speed pass): Stop everywhere, Off, a person's
  planned window, an observe-only device and Tier 3 or 4 still stop a heal, nothing sent.
"""
import pytest

from modules.nsot import device_ops
from tests.test_heal_act import A, DS, FakeAct, act, decided
from tests.test_heal_decide import GOLDEN, ROUTE4
from tests.test_heal_decide import lab  # noqa: F401 (the fixture, named by each test)
from tests.test_heal_policy import T0
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

RUNNING = GOLDEN + ROUTE4
HOLDER = {"operation": "deploy", "actor": "op@example.com", "detail": "a person's deploy"}
WINDOW = {"end": T0 + 900, "words": "edge-b is restarting as planned"}
#: The real holder, kept before `lab` replaces it with nobody (tests/test_heal_decide.py).
REAL_HOLDER = device_ops.holder


@pytest.fixture
def real_holder(monkeypatch):
    """Who holds a device read for real (`device_ops.holder`), so the act's own hold is seen."""
    monkeypatch.setattr(device_ops, "holder", REAL_HOLDER)


@pytest.fixture
def the_tests_time(monkeypatch):
    """The policy read with no time given (`act.stopped_now`'s, at each poll of the wait) at
    the test's time, as the act's own reads are (`FakeAct.clock`): the AUTO the test confirmed
    around T0 is in force, never expired by the wall clock."""
    monkeypatch.setattr("modules.heal.policy._now",
                        lambda now=None: (T0 + 5) if now is None else float(now))


@pytest.fixture
def busy(monkeypatch, the_tests_time):
    """`device_ops.acquire` refusing the first *n* tries (another operation holding the
    device), calling ``during(try)`` at each refused try and ``at_hold()`` just as the real
    hold is taken; the tries counted."""
    real = device_ops.acquire
    state = {"n": 1, "tries": 0, "during": None, "at_hold": None}

    def acquire(*a, **k):
        state["tries"] += 1
        if state["tries"] <= state["n"]:
            if state["during"]:
                state["during"](state["tries"])
            raise device_ops.DeviceBusy(dict(HOLDER))
        real(*a, **k)
        if state["at_hold"]:
            state["at_hold"]()
    monkeypatch.setattr(device_ops, "acquire", acquire)
    return state


def _stop_everywhere(*_a):
    from modules.heal import policy
    policy.stop(actor="op@example.com", actor_verified="access", why="the test's Stop")


def _off(*_a):
    from modules.heal import policy
    policy.turn_off("Default", actor="op@example.com", actor_verified="access")


class TestTheWaitedHold:
    """e400a31f: the wait for a held device, and the stops judged again once held."""

    def test_a_free_device_after_the_wait_heals(self, lab, busy):
        got, src, _d = act(RUNNING)
        assert busy["tries"] == 2 and got["outcome"] == "healed", got["words"]
        assert src.apply_kw is not None

    @pytest.mark.parametrize("press, said", [
        (_stop_everywhere, "self-healing is stopped everywhere"),
        (_off, "self-healing is no longer in Auto")])
    def test_a_stop_during_the_wait_ends_it_nothing_sent(self, lab, busy, press, said):
        d = decided(RUNNING)
        busy.update(n=50, during=lambda n: press() if n == 1 else None)
        got, src, _d = act(RUNNING, decision=d)
        assert got["outcome"] == "refused" and src.apply_kw is None, got["words"]
        assert said in got["words"] and "while the act waited" in got["words"], got["words"]
        assert busy["tries"] == 1, "the wait ended at the first poll after the press"

    @pytest.mark.parametrize("press, said", [
        (_stop_everywhere, "self-healing is stopped everywhere"),
        (_off, "only AUTO sends a heal")])
    def test_a_stop_as_the_hold_is_taken_is_judged_again_once_held(self, lab, busy, press,
                                                                   said):
        d = decided(RUNNING)
        busy.update(n=1, at_hold=press)
        got, src, _d = act(RUNNING, decision=d)
        assert got["outcome"] == "refused" and src.apply_kw is None, got["words"]
        assert said in got["words"] and "judged again once edge-b was held" in got["words"]
