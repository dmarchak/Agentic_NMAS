"""C1192 (the operator, 2026-10-18): Needs attention's RECORD, each row's life from its first
sighting to how it cleared, built when each reader finishes, safe across workers.

- the appear-and-clear case: a row that appears at one reader's finish and is gone at the
  next, with no read of the page between, is recorded: first seen, last seen, cleared, how;
- a reader the page does not draw takes no sighting; a process that starts no readers
  installs nothing;
- how a row cleared: resolved (its source read, the row gone), acknowledged (who and why), or
  by time (its due time passed); a row whose source could not be read stays open;
- a row that comes back starts a new life; a row folded into another is still present;
- what a row says is masked at rest; cleared lives are kept 30 days, at most KEPT_MAX;
- two processes sighting at once lose no sighting (an exclusive lock, an atomic replace);
  in one process sightings coalesce, never queue.
"""

import json
import os
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from modules import attention as A
from modules import attention_record as AR
from modules import reader_job as RJ

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = 1_800_000_000.0


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    yield tmp_path
    AR.uninstall()


def _row(rid="remote:Lab", source="remote", what="1 commit(s) on Lab not pushed to origin",
         level="warning", clears_at=None, attached=()):
    return {"id": rid, "source": source, "kind": "publication", "what": what,
            "level": level, "devices": [], "clears_at": clears_at,
            "attached": list(attached)}


def _result(rows=(), unread=(), acknowledged=(), sources=("remote",)):
    return {"rows": list(rows), "acknowledged": list(acknowledged),
            "sources": [{"source": s, "state": "error" if s in unread else "read"}
                        for s in set(sources) | set(unread)]}


def _stored(data):
    with open(data / AR.FILE, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- the appear-and-clear case

class TestARowSeenOnlyBetweenTwoPageReadsIsRecorded:
    """Through the real path: a reader the page draws finishes (`reader_job.run_once`), and
    the page's own rows (`attention.needs_attention`) are sighted. No read of the page."""

    @pytest.fixture
    def world(self, data, monkeypatch):
        state = {"pushed": False}

        def remote_source():
            rows = [] if state["pushed"] else [A.row(
                source="remote", kind="publication", key="Lab", level="warning",
                what="1 commit(s) on Lab not pushed to origin",
                cause="Lab: 1 commit not pushed",
                action={"label": "Push it from History's Remote set-up"})]
            return A.source_result("remote", "Publication to the remote", read_at=time.time(),
                                   took_ms=0, rows=rows, checked="Lab's remote")

        monkeypatch.setattr(A, "SOURCES", (remote_source,))
        reader = RJ.Reader(name="test-remote-publication", what="a test's remote reader",
                           endpoints=("git ls-remote",), interval_seconds=120,
                           interval_basis="a test", read=lambda: {"pushed": state["pushed"]},
                           invalidates=("remote",))
        AR.install()
        return state, reader

    def test_a_row_that_appears_and_clears_between_two_reads_is_recorded(self, world, data):
        state, reader = world
        RJ.run_once(reader)
        doc = _stored(data)
        assert list(doc["open"]) == ["remote:Lab"], "floor: the first finish sighted the row"
        state["pushed"] = True
        RJ.run_once(reader)
        doc = _stored(data)
        assert doc["open"] == {}
        (life,) = doc["cleared"]
        assert life["id"] == "remote:Lab" and life["how"] == "resolved"
        assert life["what"] == "1 commit(s) on Lab not pushed to origin"
        assert life["first_seen"] and life["last_seen"] and life["cleared_at"]
        assert life["first_seen"] <= life["last_seen"] <= life["cleared_at"]
        assert life["seen"] == 1 and doc["observed"]["count"] == 2

    def test_a_reader_the_page_does_not_draw_takes_no_sighting(self, world, data):
        _state, reader = world
        import dataclasses
        RJ.run_once(dataclasses.replace(reader, name="test-logs", invalidates=("logs",)))
        assert not (data / AR.FILE).exists()

    def test_a_reader_that_announces_only_on_change_is_sighted_only_on_change(self, world,
                                                                               data):
        """The 5 s reachability probe's shape: `announce_if` says whether the page's value
        moved, and an unchanged finish takes no sighting."""
        import dataclasses
        state, reader = world
        fast = dataclasses.replace(reader, announce_if=lambda before, now: before != now,
                                   announce_at_least_every=300)
        RJ.run_once(fast)                                   # first value: moved
        assert _stored(data)["observed"]["count"] == 1
        RJ.run_once(fast)                                   # the same value: no sighting
        assert _stored(data)["observed"]["count"] == 1
        state["pushed"] = True
        RJ.run_once(fast)                                   # moved: sighted, and it cleared
        doc = _stored(data)
        assert doc["observed"]["count"] == 2 and doc["cleared"][0]["how"] == "resolved"

    def test_nothing_is_sighted_unless_installed(self, world, data):
        _state, reader = world
        AR.uninstall()
        RJ.run_once(reader)
        assert not (data / AR.FILE).exists()

    def test_which_readers_the_page_draws_is_attention_keys(self):
        drawn = [r for r in RJ.readers() if AR.draws(r)]
        assert len(drawn) >= 10, "floor: most readers feed Needs attention"
        assert all(set(r.invalidates) & set(A.ATTENTION_KEYS) for r in drawn)
        assert not AR.draws(RJ.Reader(name="x", what="x", endpoints=(), interval_seconds=5,
                                      interval_basis="x", read=dict, invalidates=("logs",)))


class TestTheReadersInstallIt:
    def test_start_installs_the_sighting(self, monkeypatch, data):
        monkeypatch.setattr(RJ, "readers", lambda: [])
        assert AR._after_store not in RJ._AFTER_ANY_STORE
        RJ.start()
        assert AR._after_store in RJ._AFTER_ANY_STORE


# ---------------------------------------------------------------- how a row cleared

class TestHowARowCleared:
    def test_resolved_when_its_source_was_read_and_it_is_gone(self, data):
        AR.observe(_result([_row()]), now=T0)
        AR.observe(_result([]), now=T0 + 60)
        (life,) = _stored(data)["cleared"]
        assert life["how"] == "resolved"
        assert (life["first_seen"], life["cleared_at"]) == (AR._iso(T0), AR._iso(T0 + 60))

    def test_acknowledged_names_who_and_why(self, data):
        AR.observe(_result([_row()]), now=T0)
        AR.observe(_result([], acknowledged=[{"id": "remote:Lab", "by": "a@example.invalid",
                                              "why": "a planned push freeze"}]), now=T0 + 60)
        (life,) = _stored(data)["cleared"]
        assert (life["how"], life["by"], life["why"]) == (
            "acknowledged", "a@example.invalid", "a planned push freeze")

    def test_by_time_when_its_due_time_passed(self, data):
        AR.observe(_result([_row(clears_at=AR._iso(T0 + 30))]), now=T0)
        AR.observe(_result([]), now=T0 + 60)
        assert _stored(data)["cleared"][0]["how"] == "time"

    def test_gone_before_its_due_time_is_resolved(self, data):
        AR.observe(_result([_row(clears_at=AR._iso(T0 + 600))]), now=T0)
        AR.observe(_result([]), now=T0 + 60)
        assert _stored(data)["cleared"][0]["how"] == "resolved"

    def test_a_row_whose_source_was_not_read_stays_open(self, data):
        AR.observe(_result([_row()]), now=T0)
        AR.observe(_result([], unread=("remote",)), now=T0 + 60)
        doc = _stored(data)
        assert list(doc["open"]) == ["remote:Lab"] and doc["cleared"] == []
        assert doc["open"]["remote:Lab"]["last_seen"] == AR._iso(T0)

    def test_a_row_that_comes_back_starts_a_new_life(self, data):
        for i, rows in enumerate(([_row()], [], [_row()], [])):
            AR.observe(_result(rows), now=T0 + 60 * i)
        lives = _stored(data)["cleared"]
        assert [l["first_seen"] for l in lives] == [AR._iso(T0), AR._iso(T0 + 120)]

    def test_a_row_folded_into_another_is_still_present(self, data):
        child = {"id": "job_health:nmas-updater", "kind": "job", "source": "job_health",
                 "what": "the updater differs", "since": "", "devices": []}
        AR.observe(_result([_row(attached=[child])], sources=("remote", "job_health")),
                   now=T0)
        assert set(_stored(data)["open"]) == {"remote:Lab", "job_health:nmas-updater"}
        AR.observe(_result([_row()], sources=("remote", "job_health")), now=T0 + 60)
        (life,) = _stored(data)["cleared"]
        assert life["id"] == "job_health:nmas-updater" and life["how"] == "resolved"

    def test_attach_keeps_the_folded_rows_id(self):
        target = {"id": "host_steps:updater", "attached": [], "action": {"label": "x"}}
        other = {"id": "j:2", "kind": "job", "source": "job_health", "what": "w", "since": "",
                 "devices": [], "attach_to": target["id"], "action": {"label": "x"}}
        kept = A._attach([target, other])
        assert kept == [target] and target["attached"][0]["id"] == "j:2"


# ---------------------------------------------------------------- what is kept

class TestWhatIsKept:
    def test_what_a_row_says_is_masked_at_rest(self, data):
        said = "snmp-server community Str0ngC0mmunityValue RO is on r1"
        AR.observe(_result([_row(what=said)]), now=T0)
        text = (data / AR.FILE).read_text(encoding="utf-8")
        assert "Str0ngC0mmunityValue" not in text and "snmp-server community" in text

    def test_cleared_lives_older_than_kept_days_are_dropped_and_counted(self, data):
        AR.observe(_result([_row()]), now=T0)
        AR.observe(_result([]), now=T0 + 60)
        AR.observe(_result([]), now=T0 + 60 + AR.KEPT_DAYS * 86400 + 1)
        doc = _stored(data)
        assert doc["cleared"] == [] and doc["dropped"] == 1

    def test_at_most_kept_max_the_oldest_dropped(self, data, monkeypatch):
        monkeypatch.setattr(AR, "KEPT_MAX", 3)
        for i in range(5):
            AR.observe(_result([_row(rid=f"remote:L{i}")]), now=T0 + 10 * i)
            AR.observe(_result([]), now=T0 + 10 * i + 5)
        doc = _stored(data)
        assert [l["id"] for l in doc["cleared"]] == ["remote:L2", "remote:L3", "remote:L4"]
        assert doc["dropped"] == 2

    def test_an_unreadable_record_is_preserved_and_never_overwritten(self, data):
        (data / AR.FILE).write_text("{not json", encoding="utf-8")
        got = AR.observe(_result([_row()]), now=T0)
        assert got["ok"] is False and "could not be read" in got["error"]
        assert (data / AR.FILE).read_text(encoding="utf-8") == "{not json"
        assert any(p.name.startswith(AR.FILE + ".corrupt-") for p in data.iterdir())

    def test_read_says_absent_read_or_unreadable(self, data):
        assert AR.read()["state"] == "absent"
        AR.observe(_result([_row()]), now=T0)
        assert AR.read()["state"] == "read"
        (data / AR.FILE).write_text("{", encoding="utf-8")
        assert AR.read()["state"] == "unreadable"


# ---------------------------------------------------------------- across workers

SIGHTER = textwrap.dedent("""
    import sys
    sys.path.insert(0, sys.argv[1])
    from modules import attention_record as AR
    me, other, n = sys.argv[2], sys.argv[3], int(sys.argv[4])
    result = {"rows": [{"id": me + ":row", "source": me, "kind": "k", "what": me,
                        "level": "warning", "devices": [], "attached": []}],
              "acknowledged": [],
              "sources": [{"source": me, "state": "read"},
                          {"source": other, "state": "error"}]}
    for _ in range(n):
        assert AR.observe(result)["ok"]
""")


class TestTwoProcessesAtOnce:
    def test_no_sighting_is_lost(self, data):
        n = 25
        env = dict(os.environ, NMAS_DATA_DIR=str(data), PYTHONDONTWRITEBYTECODE="1")
        procs = [subprocess.Popen([sys.executable, "-c", SIGHTER, ROOT, me, other, str(n)],
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for me, other in (("sa", "sb"), ("sb", "sa"))]
        for p in procs:
            _out, err = p.communicate(timeout=120)
            assert p.returncode == 0, err.decode()[-800:]
        doc = _stored(data)
        assert doc["observed"]["count"] == 2 * n
        assert {k: v["seen"] for k, v in doc["open"].items()} == {"sa:row": n, "sb:row": n}


class TestSightingsCoalesceInOneProcess:
    def test_a_finish_during_a_sighting_asks_for_one_more_never_a_queue(self, monkeypatch):
        started, release, runs = threading.Event(), threading.Event(), []

        def slow(result=None, now=None):
            runs.append(time.time())
            if len(runs) == 1:
                started.set()
                release.wait(10)
            return {"ok": True}

        monkeypatch.setattr(AR, "observe", slow)
        t = threading.Thread(target=AR.sight, args=("first",))
        t.start()
        assert started.wait(10)
        for _ in range(5):
            AR.sight("during")              # each returns at once
        release.set()
        t.join(10)
        assert len(runs) == 2, runs

    def test_a_failing_sighting_is_logged_and_never_raises(self, monkeypatch, caplog):
        def boom(result=None, now=None):
            raise RuntimeError("the page could not be computed")

        monkeypatch.setattr(AR, "observe", boom)
        AR.sight("a reader")
        assert any("the page could not be computed" in r.getMessage() for r in caplog.records)
