"""Needs attention's background store, idle: the work it does while nothing is viewed (C3230).

Measured on the NMAS host on 2026-11-12: with C3166 slice 1 deployed and no page open, flask-app
used 47.5% of one CPU over a whole run against about 34% before it, and the approved budget
(the plan's "Bounded cost") is under 5% added while nothing is viewed. This file counts the
work, never the clock (CLAUDE.md: performance tests assert on work or growth): the real store
(modules/attention_store.py), the real reader population (`reader_job.readers()`, each with
its own interval, keys and announce rule), the real reader finish (`reader_job.run_once`: its
store, the after-store steps `reader_job.start` installs for Needs attention's record, its
announcement through `invalidation.announce`), and every one of `attention.SOURCES` planted
under its own name at its edge, counting its computations. Only the readers' reads and the
sources' bodies are stood in: a reader's value moves at every run (its read time, as 16 of
the 17 readers that ran in 90 s on the host did, 2026-11-12), a reader that announces only on
change hears that nothing it draws moved, and a source returns a quiet result.

Over IDLE_S of the store's own clock the harness counts, per source and per cause, each
computation, and each full assembly of the page:

- ``cadence``: the source's held result was due by its cadence (SLOW_S idle);
- ``event``: an announcement marked it (`attention_store.mark`);
- ``record``: Needs attention's record of sightings computed it (C3182: before the fix, every
  reader the page draws computed every source again at its finish).

Before the fix (a451d419), in 10 idle minutes: 4,700 computations and 100 assemblies by the
record, 251 computations and 70 assemblies by readers' events, 132 computations and 33
assemblies by cadence.
"""

import collections
import dataclasses

import pytest

from modules import attention as A
from modules import attention_record as AR
from modules import attention_store as S
from modules import invalidation as I
from modules import reader_job as R

T0 = 1_790_000_000.0
#: Ten idle minutes: five idle cadence periods (SLOW_S), and every reader of 300 s or less
#: finishing at least twice.
IDLE_S = 600.0


class Idle:
    """The store, the readers and the record on one clock; every source counted by cause."""

    def __init__(self, monkeypatch, tmp_path, alerting=()):
        self.now = T0
        self.alerting = set(alerting)
        self.computed = collections.Counter()      # (source, cause) -> computations
        self.assembled = collections.Counter()     # cause -> full assemblies
        self.sighted = []                          # the record's sightings, by time
        self.announced = []
        self.cause, self.taken, self.marks = "first", set(), {}
        self.names = [getattr(s, "__name__", "") for s in A.SOURCES]
        self.readers = [self._stand_in(r) for r in R.readers()]
        _window()                                  # read from the population before it is set aside
        monkeypatch.setattr(A, "SOURCES", tuple(self._source(n) for n in self.names))
        monkeypatch.setattr(A, "_with_every_configuration", list)
        monkeypatch.setattr(S, "COMPUTE_ON_READ", False)
        monkeypatch.setattr(S, "_clock", lambda: self.now)
        monkeypatch.setattr(S, "_network", lambda: "Lab")
        monkeypatch.setattr(S, "_current", lambda: "Lab")
        monkeypatch.setattr(S, "_head", lambda name: "h1")
        monkeypatch.setattr(S, "_exists", lambda name: name == "Lab")
        monkeypatch.setattr(S, "_room_emit", lambda event, msg, room: None)
        monkeypatch.setattr(S, "_started", [True])           # the worker's process
        monkeypatch.setattr(I, "_emitter", lambda event, msg: self.announced.append(msg))
        monkeypatch.setattr(R, "store_path", lambda name: str(tmp_path / f"{name}.json"))
        monkeypatch.setattr(AR, "path", lambda: str(tmp_path / AR.FILE))
        # What `reader_job.start` installs for Needs attention's record, through the real start
        # with no reader to start: only the record's steps are kept (the heal's triggers and
        # flaps ride on stores too, and are not this file's). An older record's install flag
        # is reset where it has one, so the start installs it afresh.
        monkeypatch.setattr(R, "_AFTER_ANY_STORE", [])
        monkeypatch.setattr(AR, "_installed", {"on": False}, raising=False)
        monkeypatch.setattr(R, "readers", lambda: [])
        R.start()
        monkeypatch.setattr(R, "_AFTER_ANY_STORE", [s for s in R._AFTER_ANY_STORE
                                                    if s.__module__ == AR.__name__])
        self._wrap(monkeypatch)
        S.clear()

    # ── what is counted ────────────────────────────────────────────────────────────────────

    def _source(self, name):
        def fn():
            if self.cause == "store":
                cause = "event" if S._wanted(name, self.taken) else "cadence"
            else:
                cause = self.cause
            self.computed[(name, cause)] += 1
            rows = ([A.row(source=name, kind="test", key="k", level="warning",
                           what=f"{name} alerts", cause="a planted row",
                           action={"label": "Look"})] if name in self.alerting else [])
            return A.source_result(name, name, read_at=self.now, took_ms=0, rows=rows,
                                   checked=f"{name}: quiet")
        fn.__name__ = name
        return fn

    def _wrap(self, monkeypatch):
        assemble, plan, refresh = A.assemble, S._plan, S.refresh
        needs_attention, observe = A.needs_attention, AR.observe

        def counted_assemble(results):
            self.assembled[self.bucket] += 1
            return assemble(results)

        def counted_plan(now):
            with S._lock:
                before = {name: set(n.dirty) for name, n in S._nets.items()}
            out = plan(now)
            with S._lock:
                # The marks a pass took: those it cleared.
                self.marks = {name: (d if d and not S._nets[name].dirty else set())
                              for name, d in before.items() if name in S._nets}
            return out

        def counted_refresh(network, names=None, **kw):
            before = self.cause, self.taken
            if self.cause != "first":
                self.cause, self.taken = "store", self.marks.get(network, set())
            try:
                return refresh(network, names, **kw)
            finally:
                self.cause, self.taken = before

        def counted_needs_attention(sources=None):
            before = self.cause
            self.cause = "record"
            try:
                return needs_attention(sources)
            finally:
                self.cause = before

        def counted_observe(*args, **kw):
            self.sighted.append(self.now)
            return observe(*args, **kw)

        monkeypatch.setattr(A, "assemble", counted_assemble)
        monkeypatch.setattr(S, "_plan", counted_plan)
        monkeypatch.setattr(S, "refresh", counted_refresh)
        monkeypatch.setattr(A, "needs_attention", counted_needs_attention)
        monkeypatch.setattr(AR, "observe", counted_observe)

    @property
    def bucket(self):
        if self.cause == "store":
            return "store (event)" if self.taken else "store (cadence)"
        return self.cause

    def _stand_in(self, reader):
        """The reader itself (its name, interval, keys and announce rule), its read answering
        a value that moves at every run (its read time); one that announces only on change
        hears that nothing it draws moved, and announces at its keepalive."""
        return dataclasses.replace(
            reader, read=lambda: {"read_at": self.now}, per_group=(), read_for=None,
            after_store=None, dependency=None,
            announce_if=(None if reader.announce_if is None else (lambda before, now: False)))

    def finish(self, reader):
        R.run_once(reader, announce=R.announce_via_page, clock=lambda: self.now)

    # ── the run ────────────────────────────────────────────────────────────────────────────

    def start(self):
        S.step()
        self.cause = "running"
        return self

    def run(self, seconds=IDLE_S):
        """The worker's first value, then every reader on its own interval and the worker
        waking when it says it is due (`_seconds_to_next`, at least 0.2 s apart, as `run`
        sleeps) or when a reader's finish wakes it, for *seconds* of the store's clock."""
        self.start()
        # Each reader starts within its first interval, spread so no two finish together.
        due = {r.name: T0 + (i * 1.37) % r.interval_seconds for i, r in enumerate(self.readers)}
        by_name = {r.name: r for r in self.readers}
        end = T0 + seconds
        while True:
            worker_at = self.now + max(0.2, S._seconds_to_next(self.now))
            reader_name = min(due, key=due.get)
            at = min(worker_at, due[reader_name])
            if at > end:
                break
            self.now = at
            if at == due[reader_name]:
                self.finish(by_name[reader_name])
                due[reader_name] = at + by_name[reader_name].interval_seconds
            S.step()
        return self

    # ── what the counts say ────────────────────────────────────────────────────────────────

    def per_source(self, cause=None):
        out = collections.Counter()
        for (name, c), k in self.computed.items():
            if cause is None or c == cause:
                out[name] += k
        return out

    def finishes(self, source, seconds=IDLE_S):
        """How many times the readers feeding *source* (their keys meet its declared ones)
        announce in *seconds*, from their own intervals and keepalives: what could mark it."""
        keys = set(A.SOURCE_KEYS.get(source, ()))
        n = 0
        for r in self.readers:
            if keys & set(r.invalidates):
                every = r.announce_at_least_every if r.announce_if else r.interval_seconds
                n += 1 + int(seconds // every)
        return n


@pytest.fixture
def idle(monkeypatch, tmp_path):
    def make(alerting=()):
        return Idle(monkeypatch, tmp_path, alerting).run()
    yield make
    S.clear()


#: The budget's two numbers, stated here rather than read from the store (C3230): a source is
#: computed at most a quarter of its cadence early (riding along a pass that runs anyway), and
#: while nothing is viewed the readers' finishes are collected for the interval of the fastest
#: periodic reader the page draws (`sdn-controllers`, 30 s), read from the population.
EARLY = 0.25
_WINDOW = []


def _window():
    if not _WINDOW:
        _WINDOW.append(min(r.interval_seconds for r in R.readers()
                           if r.announce_if is None
                           and set(r.invalidates) & set(A.ATTENTION_KEYS)))
    return _WINDOW[0]


def _cadence_bound(every, seconds=IDLE_S):
    """How many times a source on a cadence of *every* may be computed by it in *seconds*: its
    first value, then once a period, a period shortened by its earliest ride along."""
    return 1 + int(seconds // (every * (1 - EARLY)))


def _bursts(seconds=IDLE_S):
    """How many passes the readers' finishes may cause in *seconds* while nothing is viewed:
    one per collection window, and one more for the window open at the end."""
    return 1 + int(seconds // _window())


class TestIdleWorkFitsTheBudget:
    def test_each_source_is_computed_by_its_cadence_and_its_readers_bursts_alone(self, idle):
        """No source computed more often than its cadence (SLOW_S idle) and the passes its
        own readers' finishes can cause: at most one per collection window, and never more
        than those readers announce. A source no reader feeds is on its cadence alone."""
        got = idle()
        per = got.per_source()
        assert set(per) == set(got.names), "every source was computed (a floor)"
        over = {}
        for name in got.names:
            bound = _cadence_bound(S.SLOW_S) + min(got.finishes(name), _bursts())
            if name in S.ON_HEAD:
                bound = 1                      # no commit landed: its first value alone
            if per[name] > bound:
                over[name] = (per[name], bound)
        assert not over, (f"computed more than its bound in {IDLE_S:.0f} idle s, "
                          f"(count, bound): {over}; by cause: {dict(got.computed)}")
        quiet = [n for n in got.names if not got.finishes(n)]
        assert quiet, "some sources no reader feeds (a floor)"
        assert all(per[n] <= _cadence_bound(S.SLOW_S) for n in quiet), \
            {n: per[n] for n in quiet}

    def test_the_page_is_assembled_once_a_pass_and_the_passes_are_bounded(self, idle):
        """The readers' finishes are at most one pass per collection window, the cadences at
        most one per period (they ride along otherwise), the first value one."""
        got = idle()
        total = sum(got.assembled.values())
        bound = 1 + _bursts() + int(IDLE_S // (S.SLOW_S * (1 - EARLY)))
        assert total <= bound, (total, bound, dict(got.assembled))

    def test_a_readers_finish_computes_nothing_where_the_store_holds_the_value(self, idle):
        """C3182: Needs attention's record takes the page each pass assembled; it never
        computes every source again after a reader finishes, and every pass is sighted."""
        got = idle()
        assert got.per_source("record") == collections.Counter(), dict(got.assembled)
        assert got.assembled["record"] == 0, dict(got.assembled)
        passes = sum(k for c, k in got.assembled.items() if c != "record")
        assert passes >= 2 and len(got.sighted) == passes, (len(got.sighted), passes)

    def test_an_alerting_source_is_read_fast_and_the_quiet_ones_stay_slow(self, idle):
        """A source with a row is read at FAST_S, unviewed; the quiet ones keep SLOW_S."""
        got = idle(alerting=("approvals_source",))
        per = got.per_source()
        assert IDLE_S // S.FAST_S - 1 <= per["approvals_source"] <= _cadence_bound(S.FAST_S)
        assert per["drift_source"] <= _cadence_bound(S.SLOW_S)


class TestEventsStillReachTheirSources:
    @pytest.fixture
    def world(self, monkeypatch, tmp_path):
        w = Idle(monkeypatch, tmp_path).start()
        yield w
        S.clear()

    def _fed(self, w, reader):
        return {n for n in w.names if set(A.SOURCE_KEYS.get(n, ())) & set(reader.invalidates)}

    def test_a_readers_finish_unviewed_recomputes_only_its_sources_in_one_window(self, world):
        """Nothing viewed: its marks are collected for the idle window, then the sources its
        keys feed are computed, those alone; an ON_HEAD source is not one (a reader commits
        nothing)."""
        w = world
        reader = next(r for r in w.readers if r.name == "intent-format")
        fed = self._fed(w, reader) - set(S.ON_HEAD)
        assert fed and set(S.ON_HEAD) & self._fed(w, reader), "a floor: it feeds both kinds"
        before = w.per_source()
        w.now += 1
        w.finish(reader)
        w.now += _window() - 0.5
        S.step()
        assert w.per_source() == before, "collected, not yet computed"
        w.now += 0.5
        S.step()
        after = w.per_source()
        assert {n for n in w.names if after[n] > before[n]} == fed

    def test_a_viewed_networks_reader_marks_come_due_within_the_debounce(self, world):
        w = world
        reader = next(r for r in w.readers if r.name == "restarts")
        fed = self._fed(w, reader)
        S.read("Lab")                                # a page views it
        before = w.per_source()
        w.now += 1
        w.finish(reader)
        w.now += S.DEBOUNCE_S
        S.step()
        after = w.per_source()
        assert {n for n in w.names if after[n] > before[n]} == fed

    def test_a_page_opened_on_collected_marks_brings_them_due(self, world):
        """Marks collected while nothing was viewed: a page's read wakes the worker, and they
        come due DEBOUNCE_S after the first, not at the end of the idle window."""
        w = world
        reader = next(r for r in w.readers if r.name == "restarts")
        w.now += 1
        w.finish(reader)
        S._wake.clear()
        S.read("Lab")
        assert S._wake.is_set(), "the read woke the worker"
        assert S._seconds_to_next(w.now) == 0.0

    def test_a_change_through_mercury_unviewed_is_computed_within_the_debounce(self, world):
        """Not a reader's finish (a job's end, a person's change): DEBOUNCE_S, viewed or not."""
        w = world
        before = w.per_source()
        I.announce(["approvals"], by="approval queue")
        w.now += S.DEBOUNCE_S
        S.step()
        after = w.per_source()
        assert {n for n in w.names if after[n] > before[n]} == \
            {n for n in w.names if "approvals" in A.SOURCE_KEYS.get(n, ())}


class TestOneAssemblyReadsTheNameCutsOnce:
    def test_the_acknowledgement_record_and_its_cuts_are_read_once(self, monkeypatch):
        """`acknowledgements.current` reads every network's name cuts (two `git log` each,
        C1476): one assembly reads them once, for both of its uses (C3230)."""
        from modules import acknowledgements as ACK
        from modules.nsot import retire

        reads, cuts = [0], [0]
        ack = {"row": "restarts:r1", "event": "e1", "by": "a person", "why": "a test",
               "at": "2026-11-12T00:00:00Z", "kind": "unplanned"}
        monkeypatch.setattr(ACK, "read", lambda: reads.__setitem__(0, reads[0] + 1) or
                            {"state": "read", "rows": [ack], "error": ""})
        monkeypatch.setattr(retire, "name_cuts_everywhere",
                            lambda: cuts.__setitem__(0, cuts[0] + 1) or {})
        row = A.row(source="restarts", kind="unplanned", key="r1", level="warning",
                    event="e2", what="r1 restarted", cause="a test's restart",
                    action={"label": "Read why r1 restarted"})
        assert row.get("acknowledge"), "a floor: the row can be acknowledged"
        A.assemble([A.source_result("restarts", "Restarts", read_at=T0, took_ms=0,
                                    rows=[row], checked="one restart")])
        assert (reads[0], cuts[0]) == (1, 1)
