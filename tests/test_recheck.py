"""A fix made through Mercury re-runs the check that raised its row, and the row offers Run the
check again (the operator's overnight item 9, 2026-11-12; modules/reader_wakes.py,
modules/recheck.py).

(1) An operation's announcements, however many in a burst, run each reader its keys name ONCE,
    through `reader_job.request_run`, after the burst's debounce; a mark after the run opens the
    next burst. Counted, never timed: the debounce's timer is replaced and fired by hand.
(2) A person's press runs the row's reader through the same run path, recorded as their
    request; refused, naming both operands, while it runs (a scheduled run included), within its
    minimum spacing, or inside its backoff; the row is drawn again on the fresh read: gone when
    it no longer finds the problem, still there with the new reading's age when it does.
(3) Where the control sits: on the row's Details line beside the reading's age, never beside
    the row's one action; busy on itself while the run is owed; declared as a not-device route.
"""

import os
import types

import pytest

from modules import attention as A
from modules import invalidation as I
from modules import reader_job, reader_wakes as W
from modules import recheck as RC

pytestmark = pytest.mark.usefixtures("reader_stores_in_tmp")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "t-recheck"


class _Inline:
    """`threading.Thread` for `request_run`'s run: the run happens at `start`, so a test
    counts it without waiting on a clock."""

    def __init__(self, target=None, name=None, daemon=None, args=(), kwargs=None):
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


@pytest.fixture
def inline(monkeypatch):
    monkeypatch.setattr(reader_job, "threading",
                        types.SimpleNamespace(Thread=_Inline, Lock=reader_job.threading.Lock,
                                              Event=reader_job.threading.Event))


@pytest.fixture
def announced(monkeypatch):
    got = []
    monkeypatch.setattr(I, "_emitter", lambda event, msg: got.append(msg))
    return got


@pytest.fixture
def planted(monkeypatch, inline, announced):
    """A registered reader whose read returns what the test sets, counting its reads; the
    readers "running" in this process; no press or end left over from another test."""
    state = {"bad": True, "reads": 0}

    def read():
        state["reads"] += 1
        return {"bad": state["bad"]}

    reader_job.register(reader_job.Reader(
        name=NAME, what="a planted check", endpoints=("api/planted",), interval_seconds=3600,
        interval_basis="the test's own choice", read=read, invalidates=("logs",)))
    monkeypatch.setattr(reader_job, "running", lambda name: True)
    monkeypatch.setattr(reader_job, "_REQUESTS", {})
    monkeypatch.setattr(RC, "_ENDED", {})
    yield state
    reader_job.unregister(NAME)


def _attempt_at(seconds_ago: float, now: float, **extra):
    """Rewrite the planted reader's stored last attempt to *seconds_ago* before *now*."""
    import json

    path = reader_job.store_path(NAME)
    doc = json.loads(open(path, encoding="utf-8").read())
    doc["last_attempt"]["at"] = reader_job._iso(now - seconds_ago)
    doc.update(extra)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc))


# ---------------------------------------------------------------------------
# (1) An operation's end runs exactly the readers its keys name, once per burst
# ---------------------------------------------------------------------------

class TestAnOperationsEndRunsItsReadersOncePerBurst:
    @pytest.fixture
    def asked(self, monkeypatch):
        import modules.readers  # noqa: F401  (registers every reader)
        for name in os.listdir(os.path.join(ROOT, "modules", "readers")):
            if name.endswith(".py") and name != "__init__.py":
                __import__(f"modules.readers.{name[:-3]}")
        runs, timers = [], []
        monkeypatch.setattr(reader_job, "running", lambda name: True)
        monkeypatch.setattr(reader_job, "request_run",
                            lambda reader, by, **kw: runs.append((reader.name, by, kw["kind"]))
                            or {"started": True, "run": "r"})
        monkeypatch.setattr(W, "_schedule", lambda seconds, fn: timers.append((seconds, fn)))
        monkeypatch.setattr(W, "_BURSTS", {})
        monkeypatch.setattr(I, "_emitter", lambda event, msg: None)
        return types.SimpleNamespace(runs=runs, timers=timers)

    def test_a_burst_of_announcements_runs_each_named_reader_once(self, asked):
        # A Save's end announces its keys; a deploy's devices announce theirs, again and again.
        burst = [("save", I.ANNOUNCERS["save"])] + [("deploy-job", ("deploy_job", "goldens"))] * 4
        for by, keys in burst:
            I.announce(list(keys), by)
        named = W.readers_for({k for _by, keys in burst for k in keys})
        assert named and "baseline-usability" in named and "netbox-lag" in named
        assert asked.runs == [], "nothing runs before the burst's debounce ends"
        assert sorted(W.pending()) == named
        assert {s for s, _fn in asked.timers} == {W.debounce_s()}
        assert len(asked.timers) == len(named), "one timer per reader's burst, not per mark"
        for _s, fn in asked.timers:
            fn()
        assert sorted(n for n, _b, _k in asked.runs) == named, "each exactly once"
        assert {k for _n, _b, k in asked.runs} == {"after_operation"}
        by = dict((n, b) for n, b, _k in asked.runs)["baseline-usability"]
        assert by == "save and deploy-job", by
        assert W.pending() == {}

    def test_a_mark_after_the_run_opens_the_next_burst(self, asked):
        I.announce(["rotation"], "rotation")
        first = list(asked.timers)
        for _s, fn in first:
            fn()
        n = len(asked.runs)
        assert n == len(W.readers_for(["rotation"])) > 0
        I.announce(["rotation"], "rotation")
        assert len(asked.timers) == 2 * len(first), "a second burst schedules again"
        for _s, fn in asked.timers[len(first):]:
            fn()
        assert len(asked.runs) == 2 * n

    def test_a_timer_that_fires_twice_runs_nothing_more(self, asked):
        I.announce(["restarts"], "restarts.planned")
        named = W.readers_for(["restarts"])
        assert len(asked.timers) == len(named) > 0
        for _s, fn in asked.timers:
            fn()
            fn()
        assert sorted(n for n, _b, _k in asked.runs) == named

    def test_a_run_in_progress_at_the_burst_s_end_is_followed_by_one_more(self, asked,
                                                                         monkeypatch):
        after = []
        monkeypatch.setattr(reader_job, "request_run",
                            lambda reader, by, **kw: {"started": False, "run": "x"})
        monkeypatch.setattr(W, "_after", lambda reader, by: after.append((reader.name, by)))
        I.announce(["restarts"], "restarts.planned")
        for _s, fn in asked.timers:
            fn()
        assert ("restarts", "restarts.planned") in after

    def test_a_reader_s_own_announcement_marks_nothing(self, asked):
        reader_job.announce_via_page(["baselines"], "baseline-usability", True)
        assert asked.timers == [] and W.pending() == {}

    def test_the_cause_names_every_operation_of_the_burst(self):
        assert W._by_words(["a"]) == "a"
        assert W._by_words(["a", "b", "c"]) == "a, b and c"
        assert W._by_words(["a", "b", "c", "d", "e"]) == "a, b and 3 more"


# ---------------------------------------------------------------------------
# (2) The press: its own run path, its refusals, and the row on the fresh read
# ---------------------------------------------------------------------------

def _source():
    """A Needs attention source standing on the planted reader's stored value, as every
    reader-backed source does (`source_result(..., reader=...)`)."""
    got = reader_job.read_cached(NAME)
    good = ((got.get("doc") or {}).get("last_good") or {})
    value_at = reader_job._parse_iso(good.get("value_at"))
    rows = []
    if (good.get("value") or {}).get("bad"):
        rows = [A.row(source="job_health", kind="job", key="planted.service",
                      what="planted.service failed", cause="the planted check found it",
                      action={"label": "Open the planted service and read why it failed"},
                      level="warning")]
    return A.source_result("job_health", "Job health", read_at=value_at or 0, took_ms=1,
                           rows=rows, value_at=value_at, checked="the planted check",
                           reader=NAME)


def _rows():
    return [r for r in A.needs_attention(sources=[_source])["rows"]
            if r["id"] == "job_health:planted.service"]


class TestThePress:
    def test_it_runs_the_reader_through_its_own_path_recorded_as_the_person_s(self, planted,
                                                                             announced):
        got = RC.ask(NAME, "operator@example.com")
        assert got["ok"] and got["started"] and planted["reads"] == 1
        doc = reader_job.read_cached(NAME)["doc"]
        trigger = doc["last_attempt"]["trigger"]
        assert trigger["kind"] == "request" and trigger["by"] == "operator@example.com"
        assert trigger["run"] == got["run"]
        # The reader's own announcement (rule 13: a run on request always announces), then the
        # list told to draw the control again.
        bys = [m["by"] for m in announced]
        assert bys == [f"reader:{NAME}", RC.ANNOUNCER], bys
        assert RC._ENDED[NAME]["ok"] is True

    def test_the_row_stays_with_its_new_reading_on_a_read_that_still_finds_it(self, planted):
        reader_job.run_once(RC._reader(NAME))
        (before,) = _rows()
        assert before["reader"] == NAME
        import time
        now = time.time()
        _attempt_at(3600, now)
        _rewrite_value_at(3600, now)
        (old,) = _rows()
        assert RC.ask(NAME, "")["ok"]
        (after,) = _rows()
        assert reader_job._parse_iso(after["read_at"]) > reader_job._parse_iso(old["read_at"]), (
            old["read_at"], after["read_at"])
        assert planted["reads"] == 2

    def test_the_row_clears_on_a_read_that_no_longer_finds_it(self, planted):
        reader_job.run_once(RC._reader(NAME))
        assert len(_rows()) == 1
        import time
        _attempt_at(3600, time.time())
        planted["bad"] = False
        assert RC.ask(NAME, "")["ok"]
        assert _rows() == []

    def test_a_reader_already_running_is_not_run_twice(self, planted, monkeypatch):
        reader_job.run_once(RC._reader(NAME))
        import time
        _attempt_at(3600, time.time())
        reads = planted["reads"]
        monkeypatch.setitem(reader_job._IN_PROGRESS, NAME,
                            {"since": time.time() - 4, "kind": "scheduled", "by": "", "run": ""})
        got = RC.ask(NAME, "")
        assert not got["ok"] and got["refused"] == "running"
        assert got["operands"]["since"] and got["operands"]["cause"] == "the scheduled check"
        assert planted["reads"] == reads, "refused, never queued behind the run"

    def test_a_press_while_another_press_runs_is_refused(self, planted, monkeypatch):
        import time
        monkeypatch.setitem(reader_job._REQUESTS, NAME,
                            {"run": "abc", "by": "someone@example.com", "since": time.time(),
                             "done": False})
        got = RC.ask(NAME, "operator@example.com")
        assert not got["ok"] and got["refused"] == "running" and planted["reads"] == 0
        assert "someone@example.com" in got["operands"]["cause"]

    def test_within_its_minimum_spacing_it_is_refused_naming_both(self, planted):
        reader_job.run_once(RC._reader(NAME))
        import time
        now = time.time()
        _attempt_at(5, now)
        got = RC.ask(NAME, "", now=now)
        assert not got["ok"] and got["refused"] == "spacing" and planted["reads"] == 1
        o = got["operands"]
        assert o["spacing"] == RC.spacing_s(RC._reader(NAME)) == reader_job.BACKOFF_FIRST_SECONDS
        assert o["ago"] == 5 and o["last"] == reader_job._iso(now - 5)
        assert o["next"] == reader_job._iso(now - 5 + o["spacing"])
        # Just past it, it runs.
        assert RC.ask(NAME, "", now=now - 5 + o["spacing"] + 1)["ok"]

    def test_a_reader_faster_than_the_spacing_is_spaced_by_its_interval(self):
        fast = types.SimpleNamespace(interval_seconds=5)
        assert RC.spacing_s(fast) == 5

    def test_inside_its_backoff_it_is_refused_naming_both(self, planted):
        reader_job.run_once(RC._reader(NAME))
        import time
        now = time.time()
        _attempt_at(20, now, retry={"in_seconds": 60, "why": "nothing answered"})
        got = RC.ask(NAME, "", now=now)
        assert not got["ok"] and got["refused"] == "backoff" and planted["reads"] == 1
        o = got["operands"]
        assert o["last"] == reader_job._iso(now - 20) and o["next"] == reader_job._iso(now + 40)

    def test_an_unknown_name_and_a_process_without_readers_are_refused(self, planted,
                                                                       monkeypatch):
        got = RC.ask("no-such-check", "")
        assert got["refused"] == "unknown" and got["operands"]["asked"] == "no-such-check"
        monkeypatch.setattr(reader_job, "running", lambda name: False)
        got = RC.ask(NAME, "")
        assert got["refused"] == "not_here" and planted["reads"] == 0

    def test_a_configuration_s_store_runs_its_reader(self, planted):
        assert RC.ask(f"{NAME}@branch", "")["reader"] == NAME and planted["reads"] == 1


def _rewrite_value_at(seconds_ago: float, now: float):
    import json

    path = reader_job.store_path(NAME)
    doc = json.loads(open(path, encoding="utf-8").read())
    doc["last_good"]["value_at"] = reader_job._iso(now - seconds_ago)
    doc["last_good"]["read_started"] = now - seconds_ago
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc))


# ---------------------------------------------------------------------------
# The control's state, from memory only
# ---------------------------------------------------------------------------

class TestTheControlIsBusyUntilTheAnswerIsDrawn:
    def test_owed_while_the_run_is_not_done(self, monkeypatch):
        import time
        monkeypatch.setattr(reader_job, "_REQUESTS",
                            {NAME: {"run": "r1", "by": "", "since": time.time(), "done": False}})
        assert RC.state(NAME)["busy"] is True

    def test_done_and_stored_but_not_yet_in_the_held_list_is_still_busy(self, monkeypatch):
        import time
        now = time.time()
        monkeypatch.setattr(reader_job, "_REQUESTS",
                            {NAME: {"run": "r1", "by": "", "since": now - 2, "done": True}})
        monkeypatch.setattr(RC, "_ENDED", {NAME: {"run": "r1", "ok": True, "error": "",
                                                  "at": now - 1}})
        old = reader_job._iso(now - 600)
        assert RC.state(NAME, old, now=now)["busy"] is True
        assert RC.state(NAME, reader_job._iso(now - 2), now=now) is None, "drawn: idle"
        assert RC.state(NAME, old, now=now + RC.SETTLE_S + 1) is None, "past the settle"

    def test_a_failed_run_says_so(self, monkeypatch):
        import time
        now = time.time()
        monkeypatch.setattr(reader_job, "_REQUESTS",
                            {NAME: {"run": "r1", "by": "", "since": now - 2, "done": True}})
        monkeypatch.setattr(RC, "_ENDED", {NAME: {"run": "r1", "ok": False,
                                                  "error": "ConnectionRefusedError: refused",
                                                  "at": now - 1}})
        assert RC.state(NAME, now=now)["failed"] == "ConnectionRefusedError: refused"

    def test_a_run_no_press_started_draws_nothing_once_done(self, monkeypatch):
        import time
        monkeypatch.setattr(reader_job, "_REQUESTS",
                            {NAME: {"run": "w1", "by": "save", "since": time.time(),
                                    "done": True}})
        monkeypatch.setattr(RC, "_ENDED", {})
        assert RC.state(NAME) is None


# ---------------------------------------------------------------------------
# (3) Where it sits, the route and its declarations
# ---------------------------------------------------------------------------

class TestWhereItSits:
    def test_a_row_carries_the_reader_its_reading_came_from(self):
        def src():
            return A.source_result("job_health", "Job health", read_at=2_000_000_000.0,
                                   took_ms=1, value_at=1_999_999_000.0, checked="read",
                                   reader="job-health", rows=[
                                       A.row(source="job_health", kind="job", key="x.service",
                                             what="x.service failed", cause="it failed",
                                             action={"label": "Open x and read why"},
                                             level="warning"),
                                       A.row(source="job_health", kind="job",
                                             key="reader:netbox-secrets",
                                             what="reader:netbox-secrets failing",
                                             cause="its read failed",
                                             action={"label": "Read its error"},
                                             level="warning")])
        rows = {r["id"]: r for r in A.needs_attention(sources=[src])["rows"]}
        assert rows["job_health:x.service"]["reader"] == "job-health"
        assert "reader" not in rows["job_health:reader:netbox-secrets"], (
            "a reader's liveness row is job health's judgement (C3241)")

    def test_a_row_from_a_live_source_carries_none(self):
        def src():
            return A.source_result("drift", "Drift", read_at=2_000_000_000.0, took_ms=1,
                                   checked="read", rows=[
                                       A.row(source="drift", kind="drifted", key="r1",
                                             what="r1 has drifted", cause="a line changed",
                                             action={"label": "Open r1 and review the drift"},
                                             level="warning", devices=["r1"])])
        (r,) = A.needs_attention(sources=[src])["rows"]
        assert "reader" not in r

    def test_it_is_on_the_details_line_never_beside_the_row_s_action(self):
        page = open(os.path.join(ROOT, "templates", "v2", "_attention.html"),
                    encoding="utf-8").read()
        meta = page.split('class="att-meta"')[1].split("</p>")[0]
        assert "recheck(r.reader, r.recheck)" in meta
        primary = page.split("{%- macro primary(r, nets) -%}")[1].split("{%- endmacro -%}")[0]
        assert "recheck" not in primary
        assert page.count("recheck(") == 1

    def test_pressed_on_the_page_it_runs_the_check_and_the_item_is_drawn_again(
            self, planted, monkeypatch):
        """The list as a person gets it (GET /v2/attention), its control pressed as the page
        presses it (its own hx-post and hx-vals), and the list drawn again on the fresh read:
        still there with the new reading, then gone once the read no longer finds it."""
        import html
        import json
        import re
        import time

        import app as APP

        live = A.needs_attention
        monkeypatch.setattr(A, "needs_attention", lambda sources=None: live(sources=[_source]))
        reader_job.run_once(RC._reader(NAME))
        _attempt_at(3600, time.time())
        _rewrite_value_at(3600, time.time())
        client = APP.app.test_client()
        page = client.get("/v2/attention").get_data(as_text=True)
        assert page.count('class="att-recheck') == 1
        meta = page.split('class="att-meta"')[1].split("</p>")[0]
        assert 'class="att-recheck' in meta, "on the Details line, beside the reading's age"
        control = meta.split('class="att-recheck')[1]
        post = re.search(r'hx-post="([^"]+)"', control).group(1)
        vals = json.loads(html.unescape(re.search(r"hx-vals='([^']+)'", control).group(1)))
        assert 'data-manual="needs-attention#run-the-check-again"' in control
        before = re.search(r'read <time class="stamp" datetime="([^"]+)"', meta).group(1)

        r = client.post(post, data=vals)
        assert r.status_code == 202 and planted["reads"] == 2
        assert 'aria-busy="true"' in r.get_data(as_text=True), "busy on itself"
        meta = client.get("/v2/attention").get_data(as_text=True).split(
            'class="att-meta"')[1].split("</p>")[0]
        after = re.search(r'read <time class="stamp" datetime="([^"]+)"', meta).group(1)
        assert after > before, (before, after)

        _attempt_at(3600, time.time())
        planted["bad"] = False
        assert client.post(post, data=vals).status_code == 202 and planted["reads"] == 3
        assert 'data-recheck="' not in client.get("/v2/attention").get_data(as_text=True)

    def test_a_run_still_owed_draws_the_control_busy_on_the_page(self, planted, monkeypatch):
        import time

        import app as APP

        live = A.needs_attention
        monkeypatch.setattr(A, "needs_attention", lambda sources=None: live(sources=[_source]))
        reader_job.run_once(RC._reader(NAME))
        monkeypatch.setitem(reader_job._REQUESTS, NAME,
                            {"run": "r9", "by": "", "since": time.time(), "done": False})
        client = APP.app.test_client()
        page = client.get("/v2/attention").get_data(as_text=True)
        control = page.split('class="att-recheck')[1].split("</span>")[0]
        assert 'aria-busy="true"' in control and "hx-post" not in control
        # And a press sent anyway (another tab's idle copy) runs nothing: refused by name.
        reads = planted["reads"]
        r = client.post("/v2/attention/recheck", data={"reader": NAME})
        assert r.status_code == 409 and "is already running" in r.get_data(as_text=True)
        assert planted["reads"] == reads

    def test_the_route_answers_at_once_busy_or_refused(self, planted):
        import app as APP
        client = APP.app.test_client()
        r = client.post("/v2/attention/recheck", data={"reader": NAME})
        assert r.status_code == 202, r.get_data(as_text=True)
        body = r.get_data(as_text=True)
        assert 'aria-busy="true"' in body and planted["reads"] == 1
        assert "Content-Security-Policy" in r.headers
        r = client.post("/v2/attention/recheck", data={"reader": NAME})
        assert r.status_code == 409 and "within its minimum spacing" in r.get_data(as_text=True)
        assert planted["reads"] == 1
        r = client.post("/v2/attention/recheck", data={"reader": "no-such-check"})
        assert r.status_code == 409 and "no check named no-such-check" in r.get_data(as_text=True)

    def test_declared_as_a_read_that_changes_nothing(self):
        from modules import route_gates
        assert route_gates.GATES["v2.attention_recheck"].kind == route_gates.NOT_DEVICE
        assert isinstance(I.DECLARED["v2.attention_recheck"], I.Nothing)
        assert I.ANNOUNCERS[RC.ANNOUNCER] == RC.ANNOUNCE_KEYS == ("attention",)
