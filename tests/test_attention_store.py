"""Needs attention held in the background (C3166, slice 1; modules/attention_store.py).

The operator's rule (2026-11-12): no page load or badge poll waits on a computation; each
source refreshes on its own cadence; an event recomputes only the sources it touches,
debounced, so a heal's step announcements cause ONE recompute; a fix made through Mercury still
clears its row within seconds; the badge is pushed over the page's live connection.

Counted, never timed: every planted source counts its own computations (a path independent of
the store's own counter), and the store's clock is the test's. C1262's properties (a burst of
tabs, each network its own, each caller its own copy) are tests/test_attention_shared.py's.
"""

import pytest

from modules import attention as A
from modules import attention_store as S
from modules import invalidation as I

T0 = 1_790_000_000.0


class World:
    """Planted sources, each named as a real source (so its declared keys are the product's,
    `attention.SOURCE_KEYS`), each counting its own computations and drawing the rows its
    state names; the store's clock, the network, its repository head, and what was pushed."""

    def __init__(self):
        self.now = T0
        self.calls = {}
        self.rows = {}
        self.raises = {}
        self.head = "h1"
        self.pushed, self.announced = [], []

    def source(self, name, source="drift", label="Drift"):
        def fn():
            self.calls[name] = self.calls.get(name, 0) + 1
            if self.raises.get(name):
                raise RuntimeError(self.raises[name])
            return A.source_result(source, label, read_at=self.now, took_ms=0,
                                   rows=list(self.rows.get(name) or []),
                                   checked=f"{label}: computation {self.calls[name]}")
        fn.__name__ = name
        return fn

    def n(self, name):
        return self.calls.get(name, 0)


NAMES = ("drift_source", "deploy_source", "baseline_source", "job_health_source",
         "records_source", "approvals_source", "template_behind_source")
LABELS = {"drift_source": ("drift", "Drift"), "deploy_source": ("deploys", "Deploys"),
          "baseline_source": ("baseline", "Baseline"),
          "job_health_source": ("job_health", "Job health"),
          "records_source": ("records", "Records"), "approvals_source": ("approvals", "Approvals"),
          "template_behind_source": ("templates", "Templates behind the shipped version")}


@pytest.fixture
def world(monkeypatch):
    w = World()
    monkeypatch.setattr(A, "SOURCES", tuple(w.source(n, *LABELS[n]) for n in NAMES))
    monkeypatch.setattr(S, "COMPUTE_ON_READ", False)
    monkeypatch.setattr(S, "_clock", lambda: w.now)
    monkeypatch.setattr(S, "_network", lambda: "Lab")
    monkeypatch.setattr(S, "_current", lambda: "Lab")
    monkeypatch.setattr(S, "_head", lambda name: w.head)
    monkeypatch.setattr(S, "_exists", lambda name: name == "Lab")
    monkeypatch.setattr(S, "_room_emit", lambda event, msg, room: w.pushed.append((room, msg)))
    monkeypatch.setattr(I, "_emitter", lambda event, msg: w.announced.append(msg))
    S.clear()
    S.step()                           # the first value: every source once
    S.step()                           # the head read once (it is due at once)
    yield w
    S.clear()


def _row(key, **kw):
    return A.row(source="approvals", kind="pending", key=key, level="warning",
                 what="An approval is waiting", cause="a test's approval",
                 action={"label": "Review the approval"}, **kw)


def _ids(page):
    return [r["id"] for r in page["rows"]]


class TestOneRecomputePerBurst:
    def test_a_heals_step_announcements_are_one_recompute(self, world):
        """A heal announces each step (its running card's `device_progress`, the In progress
        chip's `in_progress`) and, at its end, what a deploy changes (modules/invalidation.py
        ANNOUNCERS heal-act): twelve announcements within the debounce, one recompute of each
        source they touch, none of the others."""
        before = dict(world.calls)
        burst = ([I.ANNOUNCERS["heal-act"]] + [I.ANNOUNCERS["run-progress"]] * 6
                 + [I.ANNOUNCERS["device-ops"]] * 3 + [I.ANNOUNCERS["in-progress"]]
                 + [I.ANNOUNCERS["heal-act"]])
        assert len(burst) == 12
        for keys in burst:
            I.announce(list(keys), by="heal-act")
            world.now += 0.1
        S.step()
        assert world.calls == before, "nothing computed inside the debounce"
        world.now = T0 + S.DEBOUNCE_S + 0.01
        S.step()
        moved = set().union(*(set(k) for k in burst))
        touched = {n for n in NAMES if set(A.SOURCE_KEYS[n]) & moved}
        assert touched and touched != set(NAMES), "the burst touches some sources, not all"
        assert {n: world.n(n) - before[n] for n in NAMES} == \
            {n: (1 if n in touched else 0) for n in NAMES}

    def test_a_running_cards_steps_alone_recompute_nothing(self, world):
        before = dict(world.calls)
        for _ in range(20):
            I.announce(list(I.ANNOUNCERS["run-progress"]), by="run-progress")
        world.now += S.DEBOUNCE_S + 1
        S.step()
        assert world.calls == before

    def test_a_mutating_routes_invalidation_recomputes_only_its_sources(self, world):
        """A route's declared invalidation (the response's keys, `_declare_invalidations`),
        through the real app: only the sources its keys move are computed again."""
        import app as APP
        endpoint = next(e for e in sorted(I.mutating_endpoints(APP.app))
                        if {n for n in NAMES if set(A.SOURCE_KEYS[n]) & set(I.keys_for(e))}
                        and len({n for n in NAMES
                                 if set(A.SOURCE_KEYS[n]) & set(I.keys_for(e))}) < 3)
        expected = {n for n in NAMES if set(A.SOURCE_KEYS[n]) & set(I.keys_for(endpoint))}
        before = dict(world.calls)
        with APP.app.test_request_context("/v2/", method="POST"):
            from flask import request
            request.url_rule = next(r for r in APP.app.url_map.iter_rules()
                                    if r.endpoint == endpoint)
            APP.app.process_response(APP.app.make_response(
                ("{}", 200, {"Content-Type": "application/json"})))
        world.now += S.DEBOUNCE_S
        S.step()
        assert {n for n in NAMES if world.n(n) > before[n]} == expected, endpoint

    def test_an_acknowledgement_reassembles_at_once_and_computes_no_source(self, world):
        """The person's own press: re-assembled before its response is sent (its page redraws
        on the response), no source read, no debounce."""
        before, first = dict(world.calls), S.read()["store"]["checked_at"]
        world.now += 1
        S.mark(["acknowledgements"], by="attention.acknowledge")
        assert world.calls == before
        assert S.read()["store"]["checked_at"] == A._iso(world.now), "assembled at once"
        assert first != A._iso(world.now)

    def test_an_acknowledgement_while_a_computation_runs_never_waits(self, world):
        """A computation holding the store: the press returns at once, and its mark assembles
        after it (the debounce)."""
        import threading
        first = S.read()["store"]["checked_at"]
        held, done = threading.Event(), threading.Event()

        def hold():
            with S._compute:
                held.set()
                done.wait(5)
        t = threading.Thread(target=hold)
        t.start()
        assert held.wait(5)
        world.now += 1
        S.mark(["acknowledgements"], by="attention.acknowledge")
        assert S.read()["store"]["checked_at"] == first, "not assembled while it is held"
        done.set()
        t.join(5)
        world.now += S.DEBOUNCE_S
        S.step()
        assert S.read()["store"]["checked_at"] != first


class TestAFixThroughMercury:
    def test_its_row_clears_after_one_debounce_through_the_real_announce_path(self, world):
        world.rows["approvals_source"] = [_row("q1")]
        world.now += S.SLOW_S
        S.step()
        assert "approvals:q1" in _ids(S.read())
        pushed_at = len(world.pushed)
        world.rows["approvals_source"] = []         # the approval decided, in Mercury
        I.announce(["approvals"], by="approval queue")
        world.now += S.DEBOUNCE_S - 0.5
        S.step()
        assert "approvals:q1" in _ids(S.read()), "still inside the debounce"
        world.now += 0.5
        S.step()
        assert "approvals:q1" not in _ids(S.read())
        (room, msg), = world.pushed[pushed_at:]
        assert room == "attention:Lab" and msg["badge"]["n"] == 0, "the count pushed"
        assert any(m["keys"] == ["attention"] for m in world.announced), "the list told"

    def test_through_a_mutating_routes_declared_invalidation(self, world):
        import app as APP
        world.rows["approvals_source"] = [_row("q2")]
        world.now += S.SLOW_S
        S.step()
        endpoint = next(e for e in sorted(I.mutating_endpoints(APP.app))
                        if "approvals" in I.keys_for(e))
        world.rows["approvals_source"] = []
        with APP.app.test_request_context("/v2/", method="POST"):
            from flask import request
            request.url_rule = next(r for r in APP.app.url_map.iter_rules()
                                    if r.endpoint == endpoint)
            APP.app.process_response(APP.app.make_response(
                ("{}", 200, {"Content-Type": "application/json"})))
        world.now += S.DEBOUNCE_S
        S.step()
        assert "approvals:q2" not in _ids(S.read()), endpoint


class TestTheCadence:
    def test_a_viewed_network_is_read_fast_and_an_idle_one_slowly(self, world):
        before = world.n("records_source")
        world.now += S.FAST_S
        S.step()
        assert world.n("records_source") == before, "idle: not yet"
        S.read()                                     # a page views it
        world.now += S.FAST_S
        S.step()
        assert world.n("records_source") == before + 1

    def test_an_alerting_source_is_read_fast_unviewed(self, world):
        world.rows["records_source"] = [_row("q3")]
        world.now += S.SLOW_S
        S.step()                                     # it now has a row
        before = world.n("records_source")
        world.now += S.FAST_S
        S.step()
        assert world.n("records_source") == before + 1
        assert world.n("job_health_source") == 1 + 1, "the quiet one at SLOW_S only"

    def test_the_template_check_runs_only_when_the_head_moves(self, world):
        assert world.n("template_behind_source") == 1
        world.now += S.SLOW_S * 3
        S.step()
        assert world.n("template_behind_source") == 1, "no commit: not read again"
        world.head = "h2"                           # a commit lands
        world.now += S.SLOW_S
        S.step()
        assert world.n("template_behind_source") == 2

    def test_a_row_that_clears_by_time_has_its_source_read_at_that_moment(self, world):
        """Sooner than its cadence (an alerting source's FAST_S): at the moment itself."""
        at = T0 + S.SLOW_S + S.FAST_S / 2
        world.rows["approvals_source"] = [_row("q4", clears_at=at)]
        world.now += S.SLOW_S
        S.step()
        before = world.n("approvals_source")
        world.now = at - 1
        S.step()
        assert world.n("approvals_source") == before, "not yet"
        world.rows["approvals_source"] = []
        world.now = at
        S.step()
        assert world.n("approvals_source") == before + 1
        assert "approvals:q4" not in _ids(S.read())

    def test_the_worker_sleeps_until_the_soonest_due_thing(self, world):
        S.mark(["drift"])
        assert S._seconds_to_next(world.now) == pytest.approx(S.DEBOUNCE_S)


class TestNeverWrongLookingRight:
    def test_a_failed_refresh_keeps_the_last_good_value_and_says_it_failed(self, world):
        world.rows["approvals_source"] = [_row("q5")]
        world.now += S.SLOW_S
        S.step()
        world.raises["approvals_source"] = "the queue's store is locked"
        world.now += S.FAST_S                        # alerting: read again fast
        S.step()
        page = S.read()
        assert "approvals:q5" in _ids(page), "the last good value is kept"
        (line,) = [s for s in page["sources"] if s["source"] == "approvals"]
        assert "the queue's store is locked" in line["failed"]["error"]
        assert line["failed"]["at"] == A._iso(world.now)
        assert page["store"]["failed"] == ["Approvals"]
        world.raises.clear()
        world.rows["approvals_source"] = []
        world.now += S.FAST_S
        S.step()
        page = S.read()
        assert page["store"]["failed"] == [] and "approvals:q5" not in _ids(page)

    def test_every_value_says_its_age(self, world):
        world.now += S.SLOW_S
        S.step()                                     # every source but the template check
        page = S.read()
        assert page["store"]["checked_at"] == A._iso(world.now)
        assert page["store"]["oldest_at"] == A._iso(T0), "the template check, read at start"
        assert all(s["read_at"] for s in page["sources"])

    def test_before_its_first_value_it_says_reading_and_fills_itself(self, world, monkeypatch):
        S.clear()
        calls = dict(world.calls)
        page = S.read()
        assert page["store"]["state"] == "reading" and page["rows"] == []
        assert S.badge() is None
        assert world.calls == calls, "a read computes nothing"
        S.step()
        assert world.pushed[-1][1]["badge"]["n"] == 0, "the count pushed when it lands"
        assert S.read()["store"]["state"] == "read"


class TestNoRequestComputes:
    def test_the_three_routes_draw_what_is_held_and_compute_nothing(self, world):
        import app as APP
        client = APP.app.test_client()
        S.clear()
        before = dict(world.calls)
        for url in ("/v2/", "/v2/attention", "/v2/attention-count"):
            body = client.get(url).get_data(as_text=True)
            assert "Reading Needs attention" in body, url
        assert world.calls == before, "the first requests after a start computed nothing"
        S.step()
        world.rows["approvals_source"] = [_row("q6")]
        world.now += S.SLOW_S
        S.step()
        before = dict(world.calls)
        page = client.get("/v2/attention").get_data(as_text=True)
        count = client.get("/v2/attention-count").get_data(as_text=True)
        assert "An approval is waiting" in page and ">1</span>" in count.replace("\n", "")
        assert world.calls == before


class TestTheLiveConnection:
    def test_a_page_joins_its_network_and_is_sent_the_held_count(self, world, monkeypatch):
        import app as APP
        monkeypatch.setattr(S, "_room_emit",
                            lambda event, msg, room: APP.socketio.emit(event, msg, to=room))
        client = APP.socketio.test_client(APP.app, query_string="network=Lab")
        try:
            got = [m for m in client.get_received() if m["name"] == S.PUSH_EVENT]
            assert [m["args"][0]["badge"]["n"] for m in got] == [0], "sent on connect"
            assert "Lab" in S._watchers.values(), "a view of its network while connected"
            world.rows["approvals_source"] = [_row("q7")]
            world.now += S.FAST_S                    # viewed: fast
            S.step()
            got = [m for m in client.get_received() if m["name"] == S.PUSH_EVENT]
            assert [m["args"][0]["badge"]["n"] for m in got] == [1], "pushed to its room"
        finally:
            client.disconnect()
        assert "Lab" not in S._watchers.values()

    def test_a_count_that_did_not_move_is_not_pushed_again(self, world):
        sent = len(world.pushed)
        world.now += S.SLOW_S
        S.step()
        assert len(world.pushed) == sent
