"""The reader-job pattern (7.2; modules/reader_job.py): one background read of
an outside service, stored, dated by its value, watched as a job-health row,
and announced. Each test names the rule (the module's numbering) it holds."""

import json
import os
import threading
import time

import pytest

from modules import config
from modules import reader_job as R


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    yield tmp_path
    for name in ("t-reader", "t-other"):
        R.unregister(name)


def make(read, **over):
    kw = dict(name="t-reader", what="a test reader", endpoints=("api/test",),
              interval_seconds=60, interval_basis="the test's own choice",
              read=read, invalidates=("monitoring",), remedy="check the test service")
    kw.update(over)
    return R.Reader(**kw)


class Clock:
    def __init__(self, t=1_790_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


# ---------------------------------------------------------------------------
# Registration refuses a reader that omits a claim
# ---------------------------------------------------------------------------

class TestRegistration:
    @pytest.mark.parametrize("over, words", [
        ({"name": "Not A Slug"}, "not a slug"),
        ({"what": " "}, "says nothing"),
        ({"endpoints": ()}, "names no endpoint"),
        ({"interval_seconds": 0}, "positive number"),
        ({"interval_basis": ""}, "states no measurement"),
        ({"invalidates": ()}, "announces no data key"),
        ({"invalidates": ("no_such_key",)}, "vocabulary does not hold: no_such_key"),
        ({"stale_after_intervals": 1}, "one slow read"),
    ])
    def test_each_missing_claim_is_refused_by_name(self, over, words):
        with pytest.raises(R.ReaderRefused, match=words):
            R.register(make(lambda: {}, **over))

    def test_a_second_reader_with_the_same_name_is_refused(self):
        R.register(make(lambda: {}))
        with pytest.raises(R.ReaderRefused, match="already registered"):
            R.register(make(lambda: {"other": 1}))

    def test_a_correct_reader_registers_and_is_in_the_population(self):
        r = R.register(make(lambda: {}))
        assert r in R.readers()


# ---------------------------------------------------------------------------
# Rules 2, 3, 4: dated by its value; a failure keeps the last good value
# ---------------------------------------------------------------------------

class TestTheStore:
    def test_a_good_read_is_stored_with_its_value_time_and_its_endpoints(self):
        clock = Clock()
        doc = R.run_once(make(lambda: {"firing": 2}), clock=clock)
        assert doc["last_good"]["value"] == {"firing": 2}
        assert doc["last_good"]["value_at"] == R._iso(clock.t)
        assert doc["endpoints"] == ["api/test"]
        assert doc["interval_basis"] == "the test's own choice"
        assert doc["last_attempt"]["ok"] is True
        stored = json.load(open(R.store_path("t-reader")))
        assert stored == doc

    def test_a_failed_read_keeps_the_last_good_value_and_says_the_attempt_failed(self):
        clock = Clock()
        R.run_once(make(lambda: {"firing": 2}), clock=clock)
        clock.t += 60

        def boom():
            raise ConnectionError("grafana refused")
        doc = R.run_once(make(boom), clock=clock)
        assert doc["last_good"]["value"] == {"firing": 2}, "a failure must not empty the value"
        assert doc["last_good"]["value_at"] == R._iso(clock.t - 60)
        assert doc["last_attempt"]["ok"] is False
        assert "ConnectionError: grafana refused" in doc["last_attempt"]["error"]
        assert doc["failing_since"] == R._iso(clock.t)

    def test_the_failing_streak_keeps_its_start_and_a_success_ends_it(self):
        clock = Clock()

        def boom():
            raise TimeoutError("slow")
        R.run_once(make(boom), clock=clock)
        first = R._iso(clock.t)
        clock.t += 60
        assert R.run_once(make(boom), clock=clock)["failing_since"] == first
        clock.t += 60
        assert R.run_once(make(lambda: {}), clock=clock)["failing_since"] is None

    def test_a_read_that_returns_no_mapping_is_a_failure(self):
        doc = R.run_once(make(lambda: [1, 2]), clock=Clock())
        assert doc["last_attempt"]["ok"] is False
        assert "not a mapping" in doc["last_attempt"]["error"]
        assert doc["last_good"] is None

    def test_the_error_text_is_redacted(self):
        def leak():
            raise RuntimeError("line was: snmp-server community Pl4ntedC0mmunity RO")
        doc = R.run_once(make(leak), clock=Clock())
        assert "Pl4ntedC0mmunity" not in json.dumps(doc)
        assert "snmp-server community" in doc["last_attempt"]["error"]

    def test_a_store_that_cannot_be_written_raises(self, monkeypatch):
        def refuse(path, text, **kw):
            raise OSError("disk full")
        monkeypatch.setattr(R._filestore, "write_atomic", refuse)
        with pytest.raises(OSError, match="disk full"):
            R.run_once(make(lambda: {}), clock=Clock())


class TestAnUnreadableCacheIsReplacedAndSaysSo:
    def test_rule_10(self, store):
        path = R.store_path("t-reader")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write("{not json")
        doc = R.run_once(make(lambda: {"firing": 0}), clock=Clock())
        assert doc["last_good"]["value"] == {"firing": 0}
        assert "could not be read" in doc["replaced_unreadable"]["why"]
        preserved = [f for f in os.listdir(os.path.dirname(path)) if ".corrupt-" in f]
        assert preserved, "the damaged cache is preserved before it is replaced"


class TestTruncation:
    def test_exactly_full_is_partial_and_refused(self):
        with pytest.raises(R.Truncated, match="100 of a 100-item page"):
            R.refuse_truncated(list(range(100)), 100, "the state history")

    def test_below_the_limit_passes(self):
        assert R.refuse_truncated([1, 2], 100, "x") == [1, 2]

    def test_a_truncated_read_is_a_failed_attempt_with_the_last_value_kept(self):
        clock = Clock()
        R.run_once(make(lambda: {"n": 5}), clock=clock)
        clock.t += 60
        doc = R.run_once(make(lambda: {"n": R.refuse_truncated([0] * 10, 10, "the page")}),
                         clock=clock)
        assert doc["last_attempt"]["ok"] is False and "Truncated" in doc["last_attempt"]["error"]
        assert doc["last_good"]["value"] == {"n": 5}


# ---------------------------------------------------------------------------
# Rule 9: it announces, after a failure too, and a failed announcement is counted
# ---------------------------------------------------------------------------

class TestAnnounce:
    def test_it_announces_its_keys_after_a_good_read_and_after_a_failed_one(self):
        heard = []
        R.run_once(make(lambda: {}), announce=lambda *a: heard.append(a), clock=Clock())

        def boom():
            raise RuntimeError("x")
        R.run_once(make(boom), announce=lambda *a: heard.append(a), clock=Clock())
        assert heard == [(["monitoring"], "t-reader", True), (["monitoring"], "t-reader", False)]

    def test_a_failed_announcement_is_counted_and_never_breaks_the_read(self):
        before = R.announce_health()["failed"]

        def deaf(*a):
            raise ConnectionError("no socket")
        doc = R.run_once(make(lambda: {"v": 1}), announce=deaf, clock=Clock())
        assert doc["last_good"]["value"] == {"v": 1}
        h = R.announce_health()
        assert h["failed"] == before + 1 and "no socket" in h["last_error"]


class TestEveryCompletedCheckRefreshesOpenPages:
    """The operator, 2026-10-01: the Update page read "asked 7 min ago" from a
    reader asking every 300 s. An unchanged scheduled answer was not
    announced, so an open page kept its older copy (rule 13's C244 fix, for
    the schedule)."""

    def test_only_the_declared_readers_skip_an_unchanged_run(self):
        skipping = {r.name for r in R.readers() if r.announce_if is not None}
        assert skipping == set(R.CHANGE_ONLY), skipping
        assert len(R.readers()) >= 8                       # the population was read
        for name, why in R.CHANGE_ONLY.items():
            assert len(why.split()) >= 12, name            # a reason, not a label

    def test_each_scheduled_run_of_the_app_pushed_reader_is_announced(self, monkeypatch):
        import dataclasses
        monkeypatch.setattr(R, "_LAST_ANNOUNCED", {})
        from modules.readers import app_pushed
        heard = []
        r = dataclasses.replace(app_pushed.READER, name="t-reader", read=lambda: {"v": 1},
                                after_store=None)
        for _ in range(3):
            R.run_once(r, announce=lambda *a: heard.append(a), clock=Clock())
        assert len(heard) == 3

    def test_a_change_only_reader_still_skips_the_control(self, monkeypatch):
        monkeypatch.setattr(R, "_LAST_ANNOUNCED", {})
        heard = []
        r = make(lambda: {"v": 1}, announce_if=lambda a, b: False, announce_at_least_every=10 ** 9)
        R.run_once(r, announce=lambda *a: heard.append(a), clock=Clock())
        R.run_once(r, announce=lambda *a: heard.append(a), clock=Clock())
        assert len(heard) == 1


class TestARequestedRunPastItsBoundIsLogged:
    """The operator, 2026-10-01: "No answer after 12 s", and nothing in the app
    log. A run on request that answers after the bound its page waits says so."""

    def _run(self, monkeypatch, caplog, took_s):
        import logging
        caplog.set_level(logging.INFO, logger="modules.reader_job")
        monkeypatch.setattr(R, "_REQUESTS", {})
        r = make(lambda: (time.sleep(took_s), {"v": 1})[1])
        monkeypatch.setattr(R, "answer_bound", lambda name: {"seconds": 1, "basis": "b"})
        got = R.request_run(r, "p@example.invalid", announce=lambda *a: None)
        deadline = time.time() + 10
        while not R._REQUESTS["t-reader"]["done"] and time.time() < deadline:
            time.sleep(0.02)
        return got, [m for m in caplog.messages if "past the" in m]

    def test_late_is_logged_naming_the_run_and_the_bound(self, monkeypatch, caplog):
        got, late = self._run(monkeypatch, caplog, 1.2)
        assert late and got["run"] in late[0] and "p@example.invalid" in late[0]
        assert "past the 1 s its page waits" in late[0]

    def test_on_time_logs_no_warning(self, monkeypatch, caplog):
        _got, late = self._run(monkeypatch, caplog, 0)
        assert late == []


# ---------------------------------------------------------------------------
# Rule 7: liveness from the store alone
# ---------------------------------------------------------------------------

def one_row(reader, now):
    rows = R.health_rows(now=now, population=[reader])
    assert len(rows) == 1
    return rows[0]


class TestLiveness:
    def test_never_run_is_its_own_state(self):
        row = one_row(make(lambda: {}), time.time())
        assert row["state"] == "not_run" and row["unit"] == "reader:t-reader"
        assert row["action"]["label"]

    def test_a_fresh_good_read_is_ok_and_names_its_basis(self):
        clock = Clock()
        r = make(lambda: {})
        R.run_once(r, clock=clock)
        row = one_row(r, clock.t + 30)
        assert row["state"] == "ok" and "the test's own choice" in row["detail"]

    def test_a_failing_reader_is_failing_since_the_streak_began_with_its_remedy(self):
        clock = Clock()
        R.run_once(make(lambda: {}), clock=clock)
        clock.t += 60

        def boom():
            raise RuntimeError("401")
        r = make(boom)
        R.run_once(r, clock=clock)
        row = one_row(r, clock.t + 5)
        assert row["state"] == "failing" and row["since"] == clock.t
        assert row["action"] == {"label": "check the test service"}
        assert "api/test" in row["detail"] and "401" in row["detail"]

    def test_failing_with_no_value_ever_is_never_succeeded(self):
        def boom():
            raise RuntimeError("401")
        r = make(boom)
        R.run_once(r, clock=Clock())
        assert one_row(r, Clock().t + 5)["state"] == "never_succeeded"

    def test_no_attempt_for_three_intervals_is_stale_from_the_window_end(self):
        clock = Clock()
        r = make(lambda: {})
        R.run_once(r, clock=clock)
        assert one_row(r, clock.t + 179)["state"] == "ok"
        row = one_row(r, clock.t + 181)
        assert row["state"] == "stale" and row["since"] == clock.t + 180

    def test_an_unreadable_store_is_unknown_never_absent(self):
        r = make(lambda: {})
        path = R.store_path("t-reader")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write("[")
        assert one_row(r, time.time())["state"] == "unknown"

    def test_job_health_carries_the_rows_and_the_page_has_words_for_each_state(self):
        from modules import attention, job_health
        R.register(make(lambda: {}))
        rows = [x for x in job_health.reader_rows() if x["unit"] == "reader:t-reader"]
        assert rows and rows[0]["state"] == "not_run"
        for state in ("not_run", "failing", "never_succeeded", "stale", "unknown"):
            assert state in attention._JOB_STATES, state


# ---------------------------------------------------------------------------
# The scheduler: started, each reader runs on its own thread. That importing
# starts none is C36's test (test_harness_isolation), over the whole app.
# ---------------------------------------------------------------------------

class TestScheduler:
    def test_start_runs_each_reader_and_stop_ends_it(self):
        ran = threading.Event()

        def read():
            ran.set()
            return {}
        R.register(make(read))
        try:
            assert "t-reader" in R.start()
            assert ran.wait(10), "the reader did not run within 10 s of start()"
            assert "t-reader" not in R.start(), "a running reader is not started twice"
        finally:
            R.stop()
            R._threads["t-reader"].join(10)
            R._threads.pop("t-reader", None)
        assert R.read_cached("t-reader")["state"] == "ok"
