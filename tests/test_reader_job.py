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
    # Rule 14's grace start, set by a test, put back (read by name, so the file still collects
    # and runs where rule 14 does not exist).
    started = getattr(R, "_STARTED_AT", None)
    yield tmp_path
    if hasattr(R, "mark_started"):
        R.mark_started(started)
    for name in ("t-reader", "t-other"):
        R.unregister(name)


def make(read, **over):
    kw = dict(name="t-reader", what="a test reader", endpoints=("api/test",),
              interval_seconds=60, interval_basis="the test's own choice",
              read=read, invalidates=("logs",), remedy="check the test service")
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
        assert heard == [(["logs"], "t-reader", True), (["logs"], "t-reader", False)]

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
# Rule 14 (C2568): a dependency not answering yet is retried on a backoff and, within its start
# grace, waiting, never failing; past the grace it is the row it was.
# ---------------------------------------------------------------------------

def dep():
    """The test's dependency: a 120 s grace, its own start unreadable (built per test, so the
    file collects where `Dependency` does not exist and each test fails on its own)."""
    return R.Dependency(key="t-dep", label="TestService", start_grace_seconds=120,
                        grace_basis="2.5x the test service's measured start, 48 s",
                        start_unreadable="the test service reports no start time")


def refused():
    raise ConnectionRefusedError(111, "Connection refused")


def _closed_port():
    """A loopback port nothing listens on: bound, then closed."""
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _requests_refused():
    """What requests raises for a refused connection, from a REAL refused connect on loopback."""
    import requests
    try:
        requests.get(f"http://127.0.0.1:{_closed_port()}/api/", timeout=5)
    except requests.exceptions.ConnectionError as exc:
        return exc
    raise AssertionError("a closed loopback port answered")


class TestWhatCountsAsNotAnswering:
    def test_a_refused_connection_through_requests_is_not_answering(self):
        assert R.not_answering(_requests_refused())

    @pytest.mark.parametrize("exc", [
        ConnectionRefusedError(111, "Connection refused"),
        ConnectionResetError(104, "Connection reset by peer"),
        TimeoutError("timed out"),
    ])
    def test_refused_reset_and_timed_out_are_not_answering(self, exc):
        assert R.not_answering(exc)

    def test_a_server_that_closed_before_answering_is_not_answering(self):
        import http.client
        import requests
        exc = requests.exceptions.ConnectionError(
            ("Connection aborted.", http.client.RemoteDisconnected("closed")))
        assert R.not_answering(exc)
        assert R.not_answering(requests.exceptions.ReadTimeout("read timed out"))
        assert R.not_answering(requests.exceptions.ConnectTimeout("connect timed out"))

    def test_an_answer_or_a_fault_that_is_not_a_start_is_never_not_answering(self):
        import socket
        import requests
        import urllib3
        resp = requests.Response()
        resp.status_code = 503
        unresolved = requests.exceptions.ConnectionError(urllib3.exceptions.MaxRetryError(
            None, "/api/", urllib3.exceptions.NameResolutionError("netbox.invalid", None,
                                                                  socket.gaierror(-2, "x"))))
        # A name that does not resolve stops the walk, even raised while handling a refusal.
        try:
            try:
                refused()
            except ConnectionRefusedError:
                raise socket.gaierror(-2, "Name or service not known")
        except socket.gaierror as exc:
            name_after_refusal = exc
        for exc in (requests.exceptions.HTTPError("503", response=resp),
                    requests.exceptions.SSLError("certificate verify failed"),
                    unresolved, socket.gaierror(-2, "Name or service not known"),
                    name_after_refusal, ValueError("a wrong answer"), KeyError("results")):
            assert not R.not_answering(exc), exc

    def test_a_wrapper_says_what_happened_under_it(self):
        try:
            try:
                refused()
            except ConnectionRefusedError as inner:
                raise RuntimeError("the read failed") from inner
        except RuntimeError as exc:
            assert R.not_answering(exc)


class TestTheBackoff:
    def test_it_doubles_from_15_s_to_its_cap_and_a_good_read_ends_it(self, monkeypatch):
        R.mark_started(0.0)                                        # the grace long past
        clock = Clock()
        r = make(refused, interval_seconds=3600, dependency=dep())
        waits = []
        for _ in range(7):
            waits.append(R.next_wait(r, R.run_once(r, clock=clock)))
            clock.t += waits[-1]
        assert waits == [15, 30, 60, 120, 240, 300, 300]
        good = make(lambda: {"held": 0}, interval_seconds=3600, dependency=dep())
        doc = R.run_once(good, clock=clock)
        assert "retry" not in doc and "waiting" not in doc
        assert R.next_wait(good, doc) == 3600

    def test_the_backoff_never_exceeds_a_short_interval(self, monkeypatch):
        R.mark_started(0.0)
        r = make(refused, interval_seconds=60)
        clock = Clock()
        waits = []
        for _ in range(4):
            waits.append(R.next_wait(r, R.run_once(r, clock=clock)))
        assert waits == [15, 30, 60, 60]

    def test_an_http_error_waits_its_interval_as_before(self):
        import requests

        def http_error():
            raise requests.exceptions.HTTPError("500 Server Error")
        r = make(http_error, interval_seconds=3600, dependency=dep())
        doc = R.run_once(r, clock=Clock())
        assert "retry" not in doc and "waiting" not in doc
        assert R.next_wait(r, doc) == 3600

    def test_the_scheduler_waits_the_backoff_not_the_interval(self, monkeypatch):
        """`_loop` itself: three reads refused, each followed by its backoff."""
        R.mark_started(0.0)
        waited = []

        class Stop:
            def is_set(self):
                return len(waited) >= 3

            def wait(self, seconds):
                waited.append(seconds)
        R._loop(make(refused, interval_seconds=3600), announce=None, stop=Stop())
        assert waited == [15, 30, 60]

    def test_a_reader_with_no_dependency_backs_off_and_still_fails_as_before(self, monkeypatch):
        R.mark_started(time.time())
        r = make(refused, interval_seconds=3600)
        doc = R.run_once(r)
        assert doc["retry"]["in_seconds"] == 15 and "waiting" not in doc
        (row,) = [x for x in R.health_rows(population=[r]) if x["unit"] == "reader:t-reader"]
        assert row["state"] == "never_succeeded"


class TestTheStartGrace:
    def test_inside_the_grace_it_is_waiting_never_failing_and_past_it_the_row_it_was(
            self, monkeypatch):
        clock = Clock()
        R.mark_started(clock.t)
        r = make(refused, interval_seconds=3600, dependency=dep())
        doc = R.run_once(r, clock=clock)
        w = doc["waiting"]
        assert w["since"] == R._iso(clock.t) and w["grace_until"] == R._iso(clock.t + 120)
        assert w["grace_from_basis"].startswith("Mercury's start, because the test service "
                                                "reports no start time")
        (row,) = R.health_rows(now=clock.t + 60, population=[r])
        assert row["state"] == "waiting"
        assert row["headline"] == (f"reader:t-reader is waiting for TestService to answer "
                                   f"(since {R._iso(clock.t)}, grace until "
                                   f"{R._iso(clock.t + 120)})")
        from modules import job_health
        assert "waiting" not in job_health.OK_STATES, "a wait is never drawn as ok"
        (past,) = R.health_rows(now=clock.t + 121, population=[r])
        assert past["state"] == "never_succeeded"

    def test_the_grace_runs_from_the_dependency_s_own_start_when_it_can_be_read(
            self, monkeypatch):
        clock = Clock()
        R.mark_started(clock.t - 3600)
        own = R.Dependency(key="t-dep", label="TestService", start_grace_seconds=120,
                           grace_basis="b", started_at=lambda: clock.t - 30)
        doc = R.run_once(make(refused, dependency=own), clock=clock)
        assert doc["waiting"]["grace_from"] == R._iso(clock.t - 30)
        assert doc["waiting"]["grace_from_basis"] == "TestService's own start"
        assert doc["waiting"]["grace_until"] == R._iso(clock.t + 90)

    def test_a_start_that_cannot_be_read_is_mercury_s_said_why(self, monkeypatch):
        clock = Clock()
        R.mark_started(clock.t - 10)

        def broken():
            raise OSError("no")
        own = R.Dependency(key="t-dep", label="TestService", start_grace_seconds=120,
                           grace_basis="b", started_at=broken)
        doc = R.run_once(make(refused, dependency=own), clock=clock)
        assert doc["waiting"]["grace_from"] == R._iso(clock.t - 10)
        assert "TestService's start could not be read (OSError)" in \
            doc["waiting"]["grace_from_basis"]

    def test_the_wait_keeps_its_start_and_the_retry_lands_at_the_grace_s_end(self, monkeypatch):
        clock = Clock()
        start = clock.t
        R.mark_started(start)
        r = make(refused, interval_seconds=3600, dependency=dep())
        waits = []
        for _ in range(5):
            doc = R.run_once(r, clock=clock)
            waits.append(R.next_wait(r, doc))
            clock.t += waits[-1]
        # 15, 30, 60, then 15 to land at the grace's end (120 s), then past it: 240.
        assert waits == [15, 30, 60, 15, 240]
        assert doc["waiting"]["since"] == R._iso(start)

    def test_a_dependency_that_answers_ends_the_wait(self, monkeypatch):
        clock = Clock()
        R.mark_started(clock.t)
        state = {"up": False}

        def read():
            if not state["up"]:
                refused()
            return {"held": 0}
        r = make(read, interval_seconds=3600, dependency=dep())
        R.run_once(r, clock=clock)
        state["up"] = True
        clock.t += 15
        doc = R.run_once(r, clock=clock)
        assert "waiting" not in doc
        (row,) = R.health_rows(now=clock.t, population=[r])
        assert row["state"] == "ok"

    def test_a_part_of_a_value_its_dependency_did_not_answer_waits_too(self, monkeypatch):
        clock = Clock()
        R.mark_started(clock.t)
        r = make(lambda: {"credentials": [], R.NOT_ANSWERING: ["t-dep"]},
                 interval_seconds=3600, dependency=dep())
        doc = R.run_once(r, clock=clock)
        assert doc["last_attempt"]["ok"] and doc["last_good"]["value"]["credentials"] == []
        assert doc["waiting"]["for"] == "t-dep" and doc["retry"]["in_seconds"] == 15
        other = make(lambda: {"credentials": [], R.NOT_ANSWERING: []},
                     interval_seconds=3600, dependency=dep())
        assert "waiting" not in R.run_once(other, clock=clock)

    def test_a_dependency_without_its_grace_or_measurement_is_refused(self):
        bad = R.Dependency(key="x", label="X", start_grace_seconds=0, grace_basis="")
        with pytest.raises(R.ReaderRefused, match="rule 14"):
            R.register(make(lambda: {}, dependency=bad))

    def test_netbox_s_grace_is_2_5x_its_measured_start(self):
        assert R.NETBOX.start_grace_seconds == 120 and "46.5 s" in R.NETBOX.grace_basis
        assert 2.4 * 46.5 <= R.NETBOX.start_grace_seconds <= 2.6 * 46.5

    def test_the_netbox_readers_declare_it(self):
        by = {r.name: r for r in R.readers()}
        for name in ("netbox-secrets", "netbox-lag", "credential-health"):
            assert by[name].dependency is R.NETBOX, name


class TestTheWaitOnScreen:
    """C2568's screen: a waiting reader under What was checked as "waiting for NetBox to answer
    (since <time>, grace until <time>)", never a row and never drawn as read; past the grace,
    the rows it raised before."""

    def _never_read(self, monkeypatch, clock):
        R.mark_started(clock.t)
        r = make(refused, interval_seconds=3600, dependency=R.NETBOX)
        R.run_once(r, clock=clock)
        return r

    def test_job_health_draws_the_wait_as_its_own_line_and_no_row(self, monkeypatch):
        from modules import attention as A
        clock = Clock(time.time())
        r = self._never_read(monkeypatch, clock)
        res = A.job_health_source(health=lambda: {"jobs": R.health_rows(population=[r])})
        assert res["rows"] == []
        (line,) = [x for x in A._checked_lines([res]) if x["state"] == A.WAITING]
        assert line["label"] == "Job health › reader:t-reader"
        assert line["checked"].startswith("waiting for NetBox to answer (since ")
        past = R.health_rows(now=clock.t + 121, population=[r])
        res = A.job_health_source(health=lambda: {"jobs": past})
        assert [x["level"] for x in res["rows"]] == ["danger"]

    def test_netbox_secrets_never_read_is_waiting_then_unreadable(self, monkeypatch):
        from modules import attention as A
        clock = Clock(time.time())
        self._never_read(monkeypatch, clock)
        res = A.netbox_secrets_source(cached=R.read_cached("t-reader"))
        assert res["state"] == A.WAITING and res["rows"] == [] and res["value_at"] is None
        assert res["checked"].startswith("waiting for NetBox to answer (since ")
        assert A.badge_of([], [res])["unreadable"] == 0
        R.mark_started(clock.t - 121)
        R.run_once(make(refused, interval_seconds=3600, dependency=R.NETBOX))
        res = A.netbox_secrets_source(cached=R.read_cached("t-reader"))
        assert res["state"] == "unreadable" and res["rows"][0]["kind"] == "unreadable"

    def test_netbox_lag_never_read_is_waiting(self, monkeypatch):
        from modules import attention as A
        self._never_read(monkeypatch, Clock(time.time()))
        res = A.netbox_lag_source(cached=R.read_cached("t-reader"))
        assert res["state"] == A.WAITING and res["rows"] == []

    def test_the_netbox_token_not_answering_is_a_line_then_the_row(self, monkeypatch):
        from modules import attention as A
        from modules.readers import credential_health as CH

        class Session:
            def get(self, *a, **k):
                raise _requests_refused()
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (True, "", Session(), "http://192.0.2.7"))
        monkeypatch.setattr(CH, "SOURCES", (CH.netbox,))
        clock = Clock(time.time())
        R.mark_started(clock.t)
        r = make(CH.read, interval_seconds=3600, dependency=R.NETBOX)
        doc = R.run_once(r, clock=clock)
        assert doc["last_good"]["value"][R.NOT_ANSWERING] == ["netbox"]
        res = A.credential_health_source(cached=R.read_cached("t-reader"))
        assert res["rows"] == []
        (line,) = [x for x in A._checked_lines([res]) if x["state"] == A.WAITING]
        assert line["label"] == "Credential expiry and age › NetBox API token"
        assert line["checked"].startswith("waiting for NetBox to answer (since ")
        R.mark_started(clock.t - 121)
        R.run_once(r)
        res = A.credential_health_source(cached=R.read_cached("t-reader"))
        assert [x["kind"] for x in res["rows"]] == ["unread"]


# ---------------------------------------------------------------------------
# The scheduler: started, each reader runs on its own thread. That importing
# starts none is C36's test (test_harness_isolation), over the whole app.
# ---------------------------------------------------------------------------

class TestScheduler:
    def test_the_integration_clients_are_loaded_before_any_reader_thread_starts(self,
                                                                                monkeypatch):
        """C836: the DHCP reader's read failed with `_DeadlockError` on
        `modules.integrations.loki` after a restart, the readers' threads making their first
        imports of the integration package together. `start()` imports the package whole in
        the starting thread first. The package is set aside (restored after) so the import
        is seen to happen before the first thread is made."""
        import sys
        import types

        import modules
        monkeypatch.delitem(sys.modules, "modules.integrations")
        monkeypatch.setattr(modules, "integrations", None, raising=False)
        seen = []

        class Thread:
            def __init__(self, *a, **kw):
                seen.append("modules.integrations" in sys.modules)

            def start(self):
                pass

            def is_alive(self):
                return False
        mine = R.register(make(lambda: {}))
        monkeypatch.setattr(R, "readers", lambda: [mine])
        monkeypatch.setattr(R, "threading", types.SimpleNamespace(Thread=Thread))
        monkeypatch.setattr(R, "_threads", {})
        monkeypatch.setattr(R, "_supervisor", {"thread": None})
        assert R.start() == ["t-reader"]
        # The reader's thread and the supervisor's (C3330), each made after the package loaded.
        assert seen == [True, True], "a thread was made before the integration package loaded"

    def test_start_runs_each_reader_and_stop_ends_it(self, monkeypatch):
        """ONLY the test's own reader is started (C163, 2026-10-05): `start()` starts every
        registered reader, and `readers()` imports every declared one, so this test once
        launched the REAL readers too (job-health, app-pushed, reachability...). Its stop
        ended only the one it joined; a real reader mid-read finished afterwards and wrote
        into the worker's store while the next modules (test_reads_create_no_list,
        test_reads_write_nothing) removed and restored it. Measured: `reader:job-health`
        was alive at the collision. So the population is this reader alone, and every
        thread started is joined and shown ended."""
        ran = threading.Event()

        def read():
            ran.set()
            return {}
        mine = R.register(make(read))
        monkeypatch.setattr(R, "readers", lambda: [mine])
        started = []
        try:
            started = R.start()
            assert started == ["t-reader"], f"start() started more than this reader: {started}"
            assert ran.wait(10), "the reader did not run within 10 s of start()"
            assert R.start() == [], "a running reader is not started twice"
        finally:
            R.stop()
            for name in started:
                R._threads[name].join(10)
            alive = [n for n in started if R._threads[n].is_alive()]
            for name in started:
                R._threads.pop(name, None)
        assert not alive, f"threads still running after stop() and a 10 s join: {alive}"
        assert R.read_cached("t-reader")["state"] == "ok"
