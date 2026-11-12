"""C3330: self-healing's detection has its own live, bounded Loki read
(modules/heal/detect_read.py; the operator, 2026-11-12: "Detection's source: its own live,
bounded Loki read, never through logs-tail (Display only)").

On r3's real lines (tests/fixtures/loki/device_logs.json) and minimal edits of one into a
configuration change and a link transition; the fake Loki answers each query by its own line
filter, time range, limit and direction. Counted, never timed.

- the read asks ONE query for every device, only the lines detection decides on (Loki's own line
  filter), oldest first, at most the window a query and `PAGES_PER_READ` queries a read;
- blind for longer than several windows with changes planted in the gap, then recovery: the
  reads re-scan from the cursor in bounded pages, oldest first, until current, and every change
  is handed over exactly once, in order;
- a full page reads on from its last line, none twice; a cursor past the horizon starts at the
  horizon and the span not scanned is said; a first read resumes where the steps stopped;
- detection's input is the lines of the read just made, handed to its steps by the reader job;
- its liveness is its own WARNING Needs attention row (critical is a network outage) past Loki's start grace, never a reader
  row: "Self-healing can't see configuration changes on <network> since <time>", with one
  action, clearing when a read succeeds; waiting inside the grace; nothing where healing is off;
- no heal module reads the logs-tail reader's store or the logs buffer (ast, with floors and a
  planted case).
"""

import ast
import dataclasses
import json
import os
import re
import time

import pytest

from modules import reader_job as RJ
from modules.heal import detect_read as D
from modules.heal import triggers as T
from tests.test_device_logs import _keep, _lines, _stages
from tests.source_index import tracked
from tests.test_logs_buffer import CONFIG, data  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = 10 ** 9
NOW = time.time()
#: r3's captured lines, moved to end an hour before this run.
_SHIFT = int((NOW - 3600) * NS) - max(ns for ns, _l in _lines("r3"))
R3 = [(ns + _SHIFT, line) for ns, line in _lines("r3")]
#: A minimal edit of the same r3 line into a link transition.
UPDOWN = re.sub(r"%SYS-5-CONFIG_I: .*$", "%LINK-3-UPDOWN: Interface GigabitEthernet2, changed "
                "state to down", CONFIG)


class FakeLoki:
    """Loki's query_range: the corpus by the query's own stages, start (inclusive), end
    (exclusive), limit and direction."""

    def __init__(self, corpus, fail=False):
        self.corpus, self.asked, self.fail = sorted(corpus), [], fail

    def configured(self):
        return True

    def ask(self, path, **p):
        self.asked.append(dict(p, path=path))
        if self.fail:
            raise RuntimeError("Loki did not answer within 5 s (loki/api/v1/query_range)")
        lo, hi, stages = int(p["start"]), int(p["end"]), _stages(p["query"])
        kept = [x for x in self.corpus if lo <= x[0] < hi and _keep(x[1], stages)]
        if p.get("direction") != "forward":
            kept = kept[::-1]
        kept = kept[:p["limit"]]
        return [{"stream": {}, "values": [[str(ns), l] for ns, l in kept]}] if kept else []


def change(ns, n):
    return (ns, CONFIG.replace("vty0", f"vty{n}"))


def _query(monkeypatch):
    monkeypatch.setattr(D, "query", lambda loki: f'{{job="network_syslog"}} |~ `{D.line_filter()}`')


class TestTheRead:
    def test_one_query_for_every_device_only_its_lines_oldest_first_bounded(self, data,
                                                                            monkeypatch):
        _query(monkeypatch)
        planted = [change(int((NOW - 300) * NS), 1), (int((NOW - 200) * NS), UPDOWN)]
        loki = FakeLoki(R3 + planted)
        v = D.read("Lab", loki=loki, clock=lambda: NOW, previous={})
        assert len(loki.asked) == 1
        (a,) = loki.asked
        assert a["direction"] == "forward" and a["limit"] == D.PAGE_LIMIT
        assert int(a["end"]) - int(a["start"]) <= D.WINDOW_SECONDS * NS
        assert int(a["end"]) == int((NOW - D.SETTLE_SECONDS) * NS)
        assert "CONFIG_" in a["query"] and "LINK-3-UPDOWN" in a["query"]
        # Every device in one query: no device is named in it.
        assert "r3" not in a["query"]
        # Only the lines detection decides on: r3's other lines are filtered by Loki.
        assert [l["ns"] for l in v["lines"]] == [ns for ns, _l in planted]
        assert [l["mn"] for l in v["lines"]] == ["%SYS-5-CONFIG_I", "%LINK-3-UPDOWN"]
        assert v["current"] is True and v["through_ns"] == int(a["end"])

    def test_blind_for_hours_then_every_change_once_in_order(self, data, monkeypatch):
        _query(monkeypatch)
        t0 = NOW - 4 * 3600
        good = D.read("Lab", loki=FakeLoki([]), clock=lambda: t0, previous={})
        # Three hours blind (twelve windows), nine changes planted in the gap, out of order.
        gap = [change(int((t0 + m * 60) * NS), m) for m in (170, 5, 90, 31, 150, 60, 120, 15, 179)]
        failing = FakeLoki(gap, fail=True)
        for i in range(1, 30):
            with pytest.raises(RuntimeError):
                D.read("Lab", loki=failing, clock=lambda i=i: t0 + i * 360, previous=good)
        spans = {(int(a["end"]) - int(a["start"])) // NS for a in failing.asked}
        assert max(spans) <= D.WINDOW_SECONDS, "a failed read never asks more"
        loki = FakeLoki(gap)
        handed, reads, t = [], 0, t0 + 3 * 3600 + 60
        v = good
        while reads < 20:
            before = len(loki.asked)
            v = D.read("Lab", loki=loki, clock=lambda t=t: t, previous=v)
            reads += 1
            assert len(loki.asked) - before <= D.PAGES_PER_READ
            handed += [l["ns"] for l in v["lines"]]
            if v["current"]:
                break
            t += D.INTERVAL_SECONDS
        assert v["current"] is True, v
        assert handed == sorted(ns for ns, _l in gap), "each change once, oldest first"
        # Twelve windows at four a read: three reads, the last current.
        assert reads == 4 and all((int(a["end"]) - int(a["start"])) // NS <= D.WINDOW_SECONDS
                                  for a in loki.asked)

    def test_a_full_page_reads_on_from_its_last_line_none_twice(self, data, monkeypatch):
        _query(monkeypatch)
        monkeypatch.setattr(D, "PAGE_LIMIT", 3)
        start = int((NOW - 600) * NS)
        # Two lines at one nanosecond where the first page is cut, and two at the last: none
        # skipped, none twice, across pages and across reads.
        burst = ([change(start + i * NS, i) for i in range(8)]
                 + [change(start + 2 * NS, 99), change(start + 7 * NS, 98)])
        loki = FakeLoki(burst)
        prev = {"configured": True, "store": "heal-detect", "through_ns": start}
        got = []
        v = D.read("", loki=loki, clock=lambda: NOW, previous=prev)
        got += [(l["ns"], l["text"]) for l in v["lines"]]
        while not v["current"]:
            v = D.read("", loki=loki, clock=lambda: NOW, previous=v)
            got += [(l["ns"], l["text"]) for l in v["lines"]]
        assert len(got) == len(set(got)) == 10, got

    def test_past_the_horizon_it_starts_there_and_says_what_was_not_scanned(self, data,
                                                                            monkeypatch):
        _query(monkeypatch)
        old = int((NOW - 30 * 3600) * NS)
        prev = {"configured": True, "store": "heal-detect", "through_ns": old}
        loki = FakeLoki([])
        v = D.read("", loki=loki, clock=lambda: NOW, previous=prev)
        assert int(loki.asked[0]["start"]) == int((NOW - D.HORIZON_SECONDS) * NS)
        gap = v["unscanned"]
        assert gap["from"] == old and gap["to"] == int((NOW - D.HORIZON_SECONDS) * NS)
        assert "24 h horizon" in gap["why"]

    def test_a_first_read_resumes_where_the_steps_stopped_under_the_old_store(self, data,
                                                                               monkeypatch):
        _query(monkeypatch)
        at = NOW - 1800
        os.makedirs(os.path.join(str(data), "heal"), exist_ok=True)
        with open(os.path.join(str(data), "heal", "triggers.json"), "w") as fh:
            json.dump({"cursors": {"logs-tail": at}}, fh)
        loki = FakeLoki([])
        v = D.read("", loki=loki, clock=lambda: NOW, previous={})
        assert int(loki.asked[0]["start"]) == int(at * NS)
        assert v["resumed_from"] == "the last line self-healing's steps processed"
        # The step's own cursor for the new store starts at the old one: nothing replayed.
        assert T.cursor_for("heal-detect") == at


class TestTheStepsTakeTheReadJustMade:
    def test_the_reader_job_hands_its_steps_this_reads_lines(self, data, monkeypatch):
        _query(monkeypatch)
        planted = [change(int((NOW - 120) * NS), 7)]
        loki = FakeLoki(R3 + planted)
        reader = dataclasses.replace(D.READER, per_group=(), read_for=None,
                                     read=lambda: D.read("", loki=loki, clock=lambda: NOW,
                                                         previous={}))
        handed = []
        monkeypatch.setitem(T.STEPS, "heal-detect", lambda store, value: handed.append(
            (store, value)))
        T.install()
        try:
            doc = RJ.run_once(reader, clock=lambda: NOW)
        finally:
            T.uninstall()
        assert doc["last_attempt"]["ok"] is True
        ((store, value),) = handed
        assert store == "heal-detect"
        assert [l["ns"] for l in value["lines"]] == [ns for ns, _l in planted]
        assert "buffer" not in value, "detection's value is its own read, never the buffer"


def _doc(value_at, ok=True, error="", value=None, attempt_at=None, waiting=None):
    doc = {"last_attempt": {"at": attempt_at or value_at, "ok": ok,
                            **({"error": error} if error else {})},
           "last_good": {"value": value or {"configured": True, "through_at": value_at},
                         "value_at": value_at} if value_at else None}
    if waiting:
        doc["waiting"] = waiting
    return {"state": "ok", "doc": doc}


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


@pytest.fixture
def healing(monkeypatch):
    modes = {"Default": "dry_run"}
    monkeypatch.setattr("modules.heal.policy.current", lambda n: {"mode": modes.get(n, "off")})
    return modes


class TestItsOwnRow:
    def test_past_the_grace_a_failing_read_is_a_warning_row_never_a_reader_row(self, healing):
        from modules import attention as A
        last = NOW - 600
        got = _doc(_iso(last), ok=False, attempt_at=_iso(NOW - 3),
                   error="RuntimeError: Loki did not answer within 5 s (loki/api/v1/query_range)")
        (row,) = D.liveness(D.READER, got, NOW)
        assert row["state"] == "blind" and row["unit"] == "self-healing:heal-detect"
        assert row["headline"] == ("Self-healing can't see configuration changes on Default "
                                   f"since {time.strftime('%H:%M UTC on %Y-%m-%d', time.gmtime(last))}")
        assert "Loki did not answer within 5 s" in row["detail"] and "Clears when" in row["detail"]
        assert row["action"]["href"] == "/v2/settings/network/Default?tab=integrations"
        assert A._JOB_STATES["blind"][1] == "warning"     # noqa: SLF001 (the level drawn)

    def test_a_dead_thread_is_blind_too(self, healing):
        (row,) = D.liveness(D.READER, _doc(_iso(NOW - 120)), NOW)
        assert row["state"] == "blind" and "its thread is not reading" in row["detail"]

    def test_inside_the_grace_it_waits_and_a_fresh_read_is_ok(self, healing):
        w = {"for": "loki", "label": "Loki", "since": _iso(NOW - 20),
             "grace_until": _iso(NOW + 10), "grace_seconds": 30}
        (row,) = D.liveness(D.READER, _doc(_iso(NOW - 400), ok=False, error="x", waiting=w), NOW)
        assert row["state"] == "waiting"
        (row,) = D.liveness(D.READER, _doc(_iso(NOW - 5)), NOW)
        assert row["state"] == "ok"

    def test_it_clears_when_a_read_succeeds(self, healing):
        assert D.liveness(D.READER, _doc(_iso(NOW - 600), ok=False, error="x"),
                          NOW)[0]["state"] == "blind"
        assert D.liveness(D.READER, _doc(_iso(NOW - 2)), NOW)[0]["state"] == "ok"

    def test_where_healing_is_off_there_is_no_row(self, healing):
        healing.clear()
        (row,) = D.liveness(D.READER, _doc(_iso(NOW - 600), ok=False, error="x"), NOW)
        assert row["state"] == "ok" and "healing is off" in row["detail"]

    def test_a_span_not_scanned_is_said_for_a_day(self, healing):
        gap = {"from_at": "2026-11-10T08:00:00Z", "to_at": "2026-11-11T08:00:00Z",
               "to": int((NOW - 86400) * NS), "until": NOW + 3600, "why": "older than its horizon"}
        value = {"configured": True, "unscanned": gap}
        (row,) = D.liveness(D.READER, _doc(_iso(NOW - 2), value=value), NOW)
        assert row["state"] == "unscanned" and "2026-11-10T08:00:00Z" in row["headline"]
        gone = dict(gap, until=NOW - 1)
        (row,) = D.liveness(D.READER, _doc(_iso(NOW - 2), value=dict(value, unscanned=gone)),
                            NOW)
        assert row["state"] == "ok"

    def test_health_rows_draws_its_row_and_no_reader_row(self, data, healing):
        rows = RJ.health_rows(now=NOW, population=[dataclasses.replace(
            D.READER, per_group=(), read_for=None)])
        assert [r["unit"] for r in rows] == ["self-healing:heal-detect"]


# ── No heal module reads the display reader's store or the buffer ──────────────────────────

HEAL = sorted(set(tracked("modules/heal", suffix=".py", recursive=False))
              | {p for p in tracked("modules", suffix=".py", recursive=False)
                 if os.path.basename(p).startswith("heal_")})
STORE_CALLS = {"read_cached", "read_cached_for", "store_for", "request_run", "run_once"}


def display_reads(text: str) -> list:
    """Each place *text* reads the logs-tail reader's store or the logs buffer: an import of
    `logs_buffer` or `readers.logs_tail`, a store call naming "logs-tail", a "buffer" key
    read, and "logs-tail" in a READERS or STEPS table."""
    out = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.ImportFrom):
            names = [f"{node.module}.{a.name}" for a in node.names]
            out += [n for n in names if "logs_buffer" in n or "logs_tail" in n]
        elif isinstance(node, ast.Import):
            out += [a.name for a in node.names if "logs_buffer" in a.name or "logs_tail" in a.name]
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            args = [a.value for a in node.args if isinstance(a, ast.Constant)]
            if name in STORE_CALLS and any(str(a).startswith("logs-tail") for a in args):
                out.append(f"{name}({args[0]!r})")
            if name == "get" and args[:1] == ["buffer"]:
                out.append("get('buffer')")
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and node.slice.value == "buffer":
            out.append("['buffer']")
        elif isinstance(node, ast.Assign) and any(getattr(t, "id", "") in ("READERS", "STEPS")
                                                  for t in node.targets):
            consts = [c.value for c in ast.walk(node.value) if isinstance(c, ast.Constant)]
            out += [f"READERS/STEPS: {c}" for c in consts if c == "logs-tail"]
    return out


class TestNoHealModuleReadsTheDisplayStore:
    def test_every_heal_module_is_parsed_and_none_reads_it(self):
        assert len(HEAL) >= 35, HEAL                  # the population's floor
        found = {}
        for p in HEAL:
            got = display_reads(open(p, encoding="utf-8").read())
            if got:
                found[os.path.relpath(p, ROOT)] = got
        assert found == {}, found
        # The detection read is among them, and its query is its own.
        assert os.path.join(ROOT, "modules", "heal", "detect_read.py") in HEAL

    @pytest.mark.parametrize("planted", [
        "from modules import logs_buffer\n",
        "from modules.readers import logs_tail\n",
        "def f(R):\n    return R.read_cached_for('logs-tail', 'Lab')\n",
        "def f(v):\n    return v.get('buffer')\n",
        "READERS = ('logs-tail', 'adjacencies')\n",
    ])
    def test_a_planted_read_is_found(self, planted):
        assert display_reads(planted), planted

    def test_the_steps_are_keyed_by_detections_store(self):
        assert "logs-tail" not in T.READERS and "logs-tail" not in T.STEPS
        assert T.STEPS["heal-detect"] is T.from_syslog
        from modules.heal import flaps
        assert flaps.READER == "heal-detect"
