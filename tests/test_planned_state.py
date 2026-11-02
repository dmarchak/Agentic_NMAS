"""A device under a planned operation reads as that operation everywhere (PHASE8_PLAN 20.3;
board PS, approved 2026-11-01, C2274): `modules/planned_state.py`.

One amber state, linked to the operation's card: a held device in its operation's words with
its card's step and "back by"; a device inside its planned-restart window; a device the
operation predicted unreachable, only while it is not answering (one that answers is never
drawn as an expectation that did not happen); and red once still down past the window (and the
settle time, for a predicted one), naming the operation it outlasted. The holds are real
(`device_ops.hold` and `note`, the reload's own steps); the windows are `record_planned`'s
shape (tests/test_attribution_b2.py's), the stores stubbed so Grafana is never asked.
"""

import os
import time

import pytest

from modules import planned_state as PS
from modules import restarts as R
from modules.nsot import device_ops as D
from tests.test_attribution_b2 import b2  # noqa: F401 - the fixture

OPERATOR = "ops@example.com"
NET = "lab"


@pytest.fixture(autouse=True)
def no_hold_survives_a_test():
    yield
    with D._mu:
        stale = list(D._held.items())
        D._held.clear()
    for _key, mine in stale:
        try:
            os.close(mine["fd"])
        except (OSError, KeyError, TypeError):
            pass


def _window(start, minutes=13, devices=("r8",), unreachable=("s5",), via="reload"):
    row = {"devices": list(devices), "list": NET, "from": R._iso(start),
           "until": R._iso(start + minutes * 60), "by": OPERATOR, "why": "planned reload",
           "via": via, "recorded_at": R._iso(start)}
    if unreachable:
        row["expected"] = {"unreachable": list(unreachable)}
    return row


@pytest.fixture
def windows(monkeypatch):
    state = {"planned": []}
    monkeypatch.setattr(R, "planned_rows", lambda: state["planned"])
    monkeypatch.setattr(R, "ends", lambda: {})
    return state


def _clock(epoch):
    return time.strftime("%H:%M UTC", time.gmtime(epoch))


DOWN = {"answering": False, "since": None}
UP = {"answering": True, "since": None}


class TestEveryOperationIsPlaced:
    def test_each_operation_a_hold_names_is_drawn_or_declared_a_read(self):
        # The shape, not a list of members: a new operation is placed before it is drawn.
        named = set(D.OPERATION_WORDS)
        assert named == set(PS.STATE_WORDS) | set(PS.READS), (
            named - set(PS.STATE_WORDS) - set(PS.READS))
        assert not set(PS.STATE_WORDS) & set(PS.READS)


class TestAHeldDevice:
    def test_a_reload_at_its_wait_reads_as_its_card_s_step_and_back_by(self, windows):
        now = time.time()
        windows["planned"] = [_window(now - 60)]
        with D.hold(NET, "r8", "reload", OPERATOR):
            for step in ("read", "window", "reload"):
                D.note(step)
            got = PS.state(PS.read(NET, now), "r8", NET, DOWN, now)
        until = now - 60 + 13 * 60
        assert got["level"] == "plan" and got["link"] == "r8", got
        assert got["words"] == (f"Reloading · by {OPERATOR} · step 4 of 6 (wait) · back by "
                                f"~{_clock(until)}")
        # A list row names no person; the map, the operation and when it is back.
        assert got["short"] == f"Reloading · step 4 of 6 (wait) · back by ~{_clock(until)}"
        assert got["tag"] == f"Reloading · back by ~{_clock(until)}"

    def test_a_deploy_with_no_window_says_its_step_and_no_back_by(self, windows):
        with D.hold(NET, "r2", "deploy", OPERATOR):
            D.note("verify")
            got = PS.state(PS.read(NET), "r2", NET, UP)
        assert got["level"] == "plan", got
        assert got["words"].startswith(f"Deploying · by {OPERATOR} · step ")
        assert "(verify)" in got["words"] and "back by" not in got["words"]

    def test_a_read_hold_draws_nothing(self, windows):
        with D.hold(NET, "r2", "capture", OPERATOR):
            assert PS.state(PS.read(NET), "r2", NET, UP) is None

    def test_the_control_nothing_held_and_no_window_is_nothing(self, windows):
        assert PS.state(PS.read(NET), "r2", NET, DOWN) is None


class TestAWindowWithNoHold:
    def test_its_device_down_inside_it_is_restarting_as_planned(self, windows):
        now = time.time()
        windows["planned"] = [_window(now - 60, unreachable=())]
        got = PS.state(PS.read(NET, now), "r8", NET, DOWN, now)
        assert got["words"] == (f"Restarting as planned · by {OPERATOR} · back by "
                                f"~{_clock(now - 60 + 13 * 60)}")
        assert got["level"] == "plan" and got["link"] == "r8"

    def test_its_device_back_and_answering_is_drawn_as_answering(self, windows):
        now = time.time()
        windows["planned"] = [_window(now - 60, unreachable=())]
        assert PS.state(PS.read(NET, now), "r8", NET, UP, now) is None

    def test_a_window_of_another_network_holds_nothing_here(self, windows):
        now = time.time()
        windows["planned"] = [dict(_window(now - 60), list="other")]
        assert PS.state(PS.read(NET, now), "r8", NET, DOWN, now) is None


class TestAPredictedDevice:
    def test_down_it_is_unreachable_as_expected_until_the_settle_time(self, windows):
        now = time.time()
        windows["planned"] = [_window(now - 60)]
        got = PS.state(PS.read(NET, now), "s5", NET, DOWN, now)
        back = now - 60 + 13 * 60 + R.SETTLE_SECONDS
        assert got["words"] == f"Unreachable as expected · r8 reloading · back by ~{_clock(back)}"
        assert got["link"] == "r8", "it opens the reload's card, on r8's page"
        # Past the window, inside the settle time: still the reload's effect.
        later = now - 60 + 13 * 60 + 60
        assert PS.state(PS.read(NET, later), "s5", NET, DOWN, later)["level"] == "plan"

    def test_answering_it_is_never_drawn_as_unreachable(self, windows):
        # The wrong thing that would look right: a prediction that did not happen.
        now = time.time()
        windows["planned"] = [_window(now - 60)]
        assert PS.state(PS.read(NET, now), "s5", NET, UP, now) is None

    def test_not_probed_it_is_not_claimed(self, windows):
        now = time.time()
        windows["planned"] = [_window(now - 60)]
        assert PS.state(PS.read(NET, now), "s5", NET, None, now) is None

    def test_a_planned_restart_names_itself_as_one(self, windows):
        now = time.time()
        windows["planned"] = [_window(now - 60, via="api")]
        got = PS.state(PS.read(NET, now), "s5", NET, DOWN, now)
        assert got["parts"][1] == "r8 restarting", got


class TestOverdue:
    def test_a_predicted_device_still_down_past_the_settle_time_is_red_naming_it(self, windows):
        start = time.time() - 3600
        windows["planned"] = [_window(start)]
        now = start + 13 * 60 + R.SETTLE_SECONDS + 120
        down = {"answering": False, "since": R._iso(start + 120)}
        got = PS.state(PS.read(NET, now), "s5", NET, down, now)
        back = start + 13 * 60 + R.SETTLE_SECONDS
        assert got["level"] == "danger", got
        assert got["words"] == f"Not answering · overdue after r8's reload (back by {_clock(back)})"

    def test_its_own_device_past_its_window_is_red_at_once(self, windows):
        # Needs attention raises it when the window ends (tests/test_planned_restart_quiet.py):
        # the state changes at the same moment.
        start = time.time() - 3600
        windows["planned"] = [_window(start, unreachable=())]
        now = start + 13 * 60 + 60
        down = {"answering": False, "since": R._iso(start + 30)}
        got = PS.state(PS.read(NET, now), "r8", NET, down, now)
        assert got["words"] == (f"Not answering · overdue after its reload (back by "
                                f"{_clock(start + 13 * 60)})")

    def test_down_since_after_the_window_is_not_its_doing(self, windows):
        start = time.time() - 7200
        windows["planned"] = [_window(start)]
        now = time.time()
        down = {"answering": False, "since": R._iso(now - 600)}
        assert PS.state(PS.read(NET, now), "s5", NET, down, now) is None


class TestTheCardsExpectedEffects:
    """Part 2: the operation's card reads the sources' own holds (board PS's decision 4), on
    tests/test_attribution_b2.py's replay of B2 (r2 reloaded, s2 predicted, r1 the peer)."""

    @pytest.fixture(autouse=True)
    def b2_from_now(self, b2, monkeypatch):
        """B2's times are fixed when its module is imported; the sources judge at the real
        time, so in a long run its window had ended before this test (the gate's shard, 18
        min). Its clock moved to this test's start, its window drawn again from it."""
        from tests import test_attribution_b2 as B
        now = time.time()
        monkeypatch.setattr(B, "NOW", now)
        monkeypatch.setattr(B, "T0", now - 480)
        monkeypatch.setattr(B, "UNTIL", now - 480 + 1295)
        b2["planned"] = [B._window()]

    def _sources(self):
        from tests import test_attribution_b2 as B
        return [B._grafana, B._reachability, B._adjacencies, B._adjacency_log,
                lambda: B._drift(now=B.NOW)]

    def test_inside_the_window_each_held_signal_is_an_effect_and_nothing_else(self, b2):
        from tests import test_attribution_b2 as B
        got = PS.expected_effects(B._window(), "Lab", now=B.NOW, sources=self._sources())
        whats = sorted(e["what"] for e in got["effects"])
        assert whats == sorted([
            "1 alert(s) on r2: Device unreachable (SNMP)",
            "1 alert(s) on s2: Device unreachable (SNMP)",
            "r2 not answering", "s2 out of Mercury's reach",
            "OSPF r1–r2 not up", "OSPFv3 r1–r2 not up", "r2's protocols not measured",
            f"r1 logged its OSPF adjacency to r2 down (1)",
            f"r1 logged its OSPFv3 adjacency to r2 down (1)",
            "Drift: r2 not read; read again by the next run",
            "Drift: s2 not read; read again by the next run"]), whats
        assert all(e["state"] == "held" for e in got["effects"])
        by = {e["what"]: e for e in got["effects"]}
        assert by["s2 out of Mercury's reach"]["predicted_by"] == \
            "the preview's What else goes down"
        assert by["r1 logged its OSPF adjacency to r2 down (1)"]["predicted_by"] == \
            "the peer's window"
        # Its own device is back by the window's end; a predicted one, the settle time later.
        assert by["r2 not answering"]["back_by"] == R._iso(B.UNTIL)
        assert by["s2 out of Mercury's reach"]["back_by"] == R._iso(B.UNTIL + R.SETTLE_SECONDS)
        assert got["unexpected"] == [] and got["overdue"] == [] and got["errors"] == []

    def test_past_its_time_nothing_is_held_and_each_raised_row_is_overdue(self, b2,
                                                                           monkeypatch):
        from modules import attention as A
        from tests import test_attribution_b2 as B
        later = B.UNTIL + R.SETTLE_SECONDS + 60
        monkeypatch.setattr(A.time, "time", lambda: later)    # B2's own control's clock
        srcs = [B._grafana, B._reachability, B._adjacencies, B._adjacency_log,
                lambda: B._drift(now=later)]
        got = PS.expected_effects(B._window(), "Lab", now=later, sources=srcs)
        # What is judged NOW (alerts, reachability, adjacencies) is no longer held; a drift run
        # and a logged drop are judged when they happened, inside the window, and stay its.
        assert {e["source"] for e in got["effects"] if e["state"] == "held"} == \
            {"drift", "adjacency_log"}
        assert got["overdue"] and all({"r2", "s2"} & set(o["devices"]) for o in got["overdue"])

    def test_another_window_s_holds_are_not_this_one_s(self, b2):
        from tests import test_attribution_b2 as B
        other = dict(B._window(), why="another reload")
        got = PS.expected_effects(other, "Lab", now=B.NOW, sources=self._sources())
        assert [e for e in got["effects"] if e["state"] == "held"] == []


def _stub(source, label, rows=(), held=(), state="read"):
    return lambda: {"source": source, "label": label, "state": state, "rows": list(rows),
                    "held": list(held)}


class TestTheCardsOtherParts:
    def test_a_predicted_device_answering_is_drawn_answering(self, windows):
        now = time.time()
        w = _window(now - 60)
        got = PS.expected_effects(w, NET, now=now,
                                  sources=[_stub("reachability", "Reachability")])
        (e,) = got["effects"]
        assert (e["what"], e["state"]) == ("s5 out of Mercury's reach", "answering")

    def test_reachability_unread_claims_no_device_answering(self, windows):
        now = time.time()
        got = PS.expected_effects(_window(now - 60), NET, now=now,
                                  sources=[_stub("reachability", "Reachability",
                                                 state="unreadable")])
        assert got["effects"] == [] and got["errors"] == ["Reachability could not be read"]

    def test_a_row_outside_its_scope_begun_in_the_window_is_unexpected(self, windows):
        now = time.time()
        rows = [{"what": "r9 is not answering", "devices": ["r9"], "since": now - 30},
                {"what": "r7 older", "devices": ["r7"], "since": now - 7200}]
        got = PS.expected_effects(_window(now - 60), NET, now=now,
                                  sources=[_stub("reachability", "Reachability", rows)])
        assert [u["what"] for u in got["unexpected"]] == ["r9 is not answering"]
        assert got["overdue"] == []


class TestTheReloadCardDrawsThem:
    def _card(self, monkeypatch, windows, rows=(), held=()):
        import types
        from modules import device_actions as DA
        now = time.time()
        w = _window(now - 60)
        windows["planned"] = [w]
        real = PS.expected_effects
        monkeypatch.setattr(PS, "expected_effects", lambda window, list_name: real(
            window, list_name, sources=[_stub("reachability", "Reachability", rows, held)]))
        got = {"state": "done", "kind": "reload", "payload": {
            "outcome": "reloaded", "ok": True, "steps": [], "by": OPERATOR, "reason": "r",
            "window": {"from": w["from"], "until": w["until"]}}}
        return DA.reload_job_card(types.SimpleNamespace(name=NET), "r8", "j1", got)

    def _html(self, card):
        import app as A
        from flask import render_template
        with A.app.test_request_context("/v2/device/r8"):
            return render_template("v2/_reload.html", c=card)

    def test_the_result_draws_its_effects_and_says_none_unexpected_or_overdue(
            self, windows, monkeypatch):
        card = self._card(monkeypatch, windows)
        html = self._html(card)
        assert '<div class="op-part" id="reload-effects"><h3>Expected effects</h3>' in html
        assert "s5 out of Mercury&#39;s reach" in html and "answering" in html
        assert "Unexpected during this reload: none." in html and "Overdue: none." in html

    def test_an_unexpected_row_is_said_on_the_card(self, windows, monkeypatch):
        card = self._card(monkeypatch, windows, rows=[
            {"what": "r9 is not answering", "devices": ["r9"], "since": time.time() - 20}])
        html = self._html(card)
        assert ("Unexpected during this reload, raised on Needs attention: r9 is not answering "
                "(Reachability).") in html

    def test_a_verify_again_card_draws_none(self, windows, monkeypatch):
        card = self._card(monkeypatch, windows)
        assert card["effects"] is not None
        import types
        from modules import device_actions as DA
        got = {"state": "running", "kind": "reload_verify", "payload": {}}
        monkeypatch.setattr(DA, "job_steps", lambda *a, **k: [])
        assert DA.reload_job_card(types.SimpleNamespace(name=NET), "r8", "j2",
                                  got)["effects"] is None


class TestUnreadable:
    def test_an_unreadable_window_record_is_named_and_holds_still_draw(self, monkeypatch):
        def raises():
            raise RuntimeError("the planned-restart record could not be read: boom")
        monkeypatch.setattr(R, "planned_rows", raises)
        monkeypatch.setattr(R, "ends", lambda: {})
        with D.hold(NET, "r2", "deploy", OPERATOR):
            ctx = PS.read(NET)
            got = PS.state(ctx, "r2", NET, UP)
        assert "planned-restart windows could not be read" in ctx["error"]
        assert got["words"].startswith("Deploying")
