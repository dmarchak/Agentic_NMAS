"""C539 (the operator, 2026-10-06, bucket A): a Needs attention row must not outlive the
operation that resolved it.

A baseline was taken and "No stored baseline can be re-applied" stood until the baseline
reader's next 300 s cycle; another person seeing it could take a second baseline. Three parts:

1. Every operation that resolves a cause re-reads, AT ONCE, the reader that reports it
   (`modules/reader_wakes.py`): the table covers every registered reader (woken by named keys,
   or a stated reason nothing Mercury does changes its answer); one test per (operation,
   reader) pair the operator named, through the operation's OWN declaration (a route's
   `invalidation.DECLARED` keys, a job's `ANNOUNCERS` keys); the mechanism (a declared route
   that answered, and a job's announcement, wake; a refusal wakes nothing; a reader not
   running here is not asked; a run in progress is followed by one more, since it may have
   read before the write); no loop (no reader's own announcement wakes a reader). And C542,
   which a wake mid-rotation would have made worse: a held device's "persistence not
   attempted" is the moment between rotate and persist, never a row.
2. A Save All that would repeat the baseline just taken says so, with when and by whom.
3. Every Needs attention row carries the age of its reading.
"""

import os
import subprocess

import pytest

from modules import invalidation as I
from modules import reader_job, reader_wakes as W


def _registered():
    import modules.readers  # noqa: F401  (registers every reader)
    for name in os.listdir(os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules",
                                        "readers")):
        if name.endswith(".py") and name != "__init__.py":
            __import__(f"modules.readers.{name[:-3]}")
    return {r.name: r for r in reader_job.readers()}


class TestTheTable:
    def test_every_registered_reader_is_woken_or_says_why_not(self):
        readers = _registered()
        assert len(readers) >= 16, sorted(readers)   # the floor; 16 since freshness retired
        assert set(W.WOKEN_BY) | set(W.NOT_WOKEN) == set(readers), (
            "a reader missing from the table, or a name no reader has: "
            f"{sorted(set(readers) ^ (set(W.WOKEN_BY) | set(W.NOT_WOKEN)))}")
        assert not set(W.WOKEN_BY) & set(W.NOT_WOKEN)

    def test_every_wake_key_is_a_key_an_operation_sends(self):
        sent = {k for keys in I.DECLARED.values() if isinstance(keys, tuple) for k in keys}
        sent |= {k for keys in I.ANNOUNCERS.values() for k in keys}
        for reader, keys in W.WOKEN_BY.items():
            assert keys and set(keys) <= set(I.VOCABULARY), reader
            assert set(keys) <= sent, (reader, sorted(set(keys) - sent))

    def test_no_reader_s_own_announcement_wakes_a_reader(self, monkeypatch):
        """No loop. Readers DO announce keys the table holds (measured: baseline-usability
        announces `baselines`, which wakes it), so the guard is who announces: a reader's
        announcement, made the way every reader makes it, wakes nothing."""
        announced = {k for r in _registered().values() for k in r.invalidates}
        woken = {k for keys in W.WOKEN_BY.values() for k in keys}
        assert announced & woken, "the case the guard exists for is real"
        woke = []
        monkeypatch.setattr(W, "wake", lambda keys, by: woke.append(by))
        monkeypatch.setattr(I, "_emitter", lambda event, msg: None)
        reader_job.announce_via_page(["baselines"], "baseline-usability", True)
        assert woke == []


def _keys_of(operation):
    if operation in I.ANNOUNCERS:
        return I.ANNOUNCERS[operation]
    keys = I.DECLARED[operation]
    assert isinstance(keys, tuple), f"{operation} declares Nothing: it can wake no reader"
    return keys


#: The operator's pairs (2026-10-06) and the survey's: the operation by its own declaration
#: (an endpoint, or a job's announcer), and the reader whose answer it changes.
PAIRS = [
    ("golden.capture_apply", "baseline-usability"),        # Save All earns a baseline
    ("device_v2.capture_confirm", "baseline-usability"),
    ("golden.capture_apply", "lab-startup"),
    ("rotation", "job-health"),                            # a rotation job's announcement
    ("rotation", "credential-health"),
    ("rotation", "baseline-usability"),
    ("onboard.verify", "job-health"),                      # onboarding: break-glass, rotation
    ("onboard.verify", "credential-health"),
    ("breakglass.export", "job-health"),                   # the record current again (C536)
    ("v2.credentials_intact", "job-health"),
    ("v2.credentials_drill", "job-health"),
    ("persist.apply", "job-health"),                       # the save record
    ("device_v2.persist_confirm", "job-health"),
    ("attention.acknowledge", "grafana-alerts"),           # the band re-read (C533)
    ("restarts.planned", "restarts"),
    ("netbox_safety.apply_import", "netbox-secrets"),
    ("save_settings", "integrations"),
    ("deploy-job", "adjacencies"),                         # a deploy's intent and goldens
    ("deploy-job", "baseline-usability"),
]


@pytest.mark.parametrize("operation, reader", PAIRS, ids=[f"{o}->{r}" for o, r in PAIRS])
def test_the_operation_wakes_the_reader_that_reports_it(operation, reader):
    assert reader in W.readers_for(_keys_of(operation)), (operation, _keys_of(operation))


class TestTheMechanism:
    @pytest.fixture
    def asked(self, monkeypatch):
        _registered()
        got = []
        monkeypatch.setattr(reader_job, "running", lambda name: name != "lab-startup")
        monkeypatch.setattr(reader_job, "request_run",
                            lambda reader, by, **kw: got.append((reader.name, by, kw["kind"]))
                            or {"started": True, "run": "r"})
        return got

    def test_a_wake_asks_each_reader_running_here_and_no_other(self, asked):
        woke = W.wake(("goldens",), "golden.capture_apply")
        assert "lab-startup" not in woke, "not running in this process: not asked"
        assert set(woke) == {"baseline-usability", "remote-publication"}   # freshness retired
        assert {(n, k) for n, _b, k in asked} == {(n, "after_operation") for n in woke}
        assert {b for _n, b, _k in asked} == {"golden.capture_apply"}

    def test_a_run_in_progress_is_followed_by_one_more(self, monkeypatch):
        reader = _registered()["job-health"]
        asked, in_flight = [], [{"run": "x"}, {"run": "x"}, None]
        monkeypatch.setattr(reader_job, "request_in_flight", lambda name: in_flight.pop(0))
        monkeypatch.setattr(reader_job, "request_run",
                            lambda r, by, **kw: asked.append(by) or {"started": True})
        slept = []
        W._after(reader, "rotation", sleep=slept.append, clock=lambda: 0.0,
                 spawn=lambda go: go())
        assert slept == [0.5, 0.5] and asked == ["rotation"], (slept, asked)

    def test_a_job_s_announcement_wakes(self, monkeypatch):
        woke = []
        monkeypatch.setattr(W, "wake", lambda keys, by: woke.append((tuple(keys), by)))
        monkeypatch.setattr(I, "_emitter", lambda event, msg: None)
        I.announce(["rotation"], "rotation")
        assert woke == [(("rotation",), "rotation")]

    def test_a_declared_route_that_answered_wakes_and_a_refusal_does_not(self, monkeypatch):
        from flask import Flask
        app = Flask("t")

        @app.route("/x", methods=["POST"], endpoint="golden.capture_apply")
        def x():
            from flask import request
            return ("refused", 400) if request.args.get("no") else ("ok", 200)

        I.install(app)
        woke = []
        monkeypatch.setattr(W, "wake", lambda keys, by: woke.append((tuple(keys), by)))
        client = app.test_client()
        assert client.post("/x").status_code == 200
        assert woke == [(I.DECLARED["golden.capture_apply"], "golden.capture_apply")]
        client.post("/x?no=1")
        assert len(woke) == 1, "a refusal changed nothing, so it wakes nothing"


class TestARotationMidJobRaisesNoRow:
    """C542: `rotation_rows` read the record regardless of the hold; a read between rotate and
    persist (one hold, seconds apart) drew "persistence NOT ATTEMPTED" Critical."""

    def _rows(self, held):
        from modules import job_health
        from modules.nsot import credential_rotation as cr
        rec = [{"device": "s1", "state": cr.ROTATED_PENDING_PERSIST, "at": "2026-10-06T19:00:00Z"}]
        return job_health.rotation_rows(records=rec, known=({"s1"}, ""), held=held)

    def test_held_it_is_the_moment_between_rotate_and_persist(self):
        assert self._rows({"S1"}) == []

    def test_released_it_is_a_state_left_behind(self):
        (row,) = self._rows(set())
        assert row["state"] == "not_safe_to_reboot"


# ---------------------------------------------------------------------------
# (2) A Save All that would repeat the baseline just taken says so.
# ---------------------------------------------------------------------------

def _entry(name, changed=False):
    return {"device": name, "read": True, "changed": changed, "capture_hash": "h",
            "diff": [], "intent": {"state": "match"}, "platform": "cisco_ios"}


REPEATS = {"tag": "baseline/20261006T200000Z", "at": "2026-10-06T20:00:00+00:00",
           "actor": "operator@example.com"}


class TestTheRepeatIsSaid:
    def _what_not(self, entries, repeats=REPEATS, fleet=True):
        from modules.preview_confirm import capture_preview
        out = capture_preview(entries, fleet=fleet, inventory=[], repeats=repeats,
                              confirm={"may": True, "kind": "person",
                                       "statement": "You are confirming as operator@example.com."})
        return out["what_not"]["items"] if isinstance(out.get("what_not"), dict) \
            else out.get("what_not") or []

    def test_every_device_unchanged_since_the_baseline(self):
        items = self._what_not([_entry("r1"), _entry("s1")])
        first = items[0]
        assert first["kind"] == "repeats" and first["target"] == "this baseline"
        assert "by operator@example.com (baseline/20261006T200000Z)" in first["text"]
        assert "another Save All would record the same state" in first["text"]

    @pytest.mark.parametrize("entries, repeats, fleet", [
        ([_entry("r1"), _entry("s1", changed=True)], REPEATS, True),   # something changed
        ([_entry("r1"), dict(_entry("s1"), read=False)], REPEATS, True),  # one not read
        ([_entry("r1")], None, True),                                  # no current baseline
        ([_entry("r1")], REPEATS, False),                              # one device's capture
    ])
    def test_not_said_otherwise(self, entries, repeats, fleet):
        assert not any(i.get("kind") == "repeats"
                       for i in self._what_not(entries, repeats, fleet))

    def test_the_age_words(self):
        from modules.preview_confirm import _repeats_words
        import datetime as dt
        at = dt.datetime(2026, 10, 6, 20, 0, tzinfo=dt.timezone.utc).timestamp()
        assert "taken 2 min ago by" in _repeats_words(REPEATS, now=at + 150)

    def test_the_current_baseline_by_its_golden_tree(self, tmp_path, monkeypatch):
        """A real repository: the tag's golden tree is HEAD's until a golden commit moves it."""
        import routes.golden as G
        from modules.nsot import repo as R
        repo = str(tmp_path)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")

        def git(*a):
            subprocess.run(["git", "-C", repo, *a], check=True, env=env, capture_output=True)
        os.makedirs(os.path.join(repo, "golden"))
        open(os.path.join(repo, "golden", "r1.cfg"), "w").write("hostname r1\n")
        git("init", "-q")
        git("add", "-A")
        git("commit", "-q", "-m", "golden: Save All\n\nActor: operator@example.com")
        sha = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                             text=True, check=True).stdout.strip()
        monkeypatch.setattr(R, "list_baselines", lambda r: [
            {"tag": "baseline/x", "commit": sha, "created": "2026-10-06T20:00:00+00:00",
             "decision": "earned", "withdrawn": None, "deleted": False}])
        got = G.last_baseline_if_current(repo)
        assert got == {"tag": "baseline/x", "at": "2026-10-06T20:00:00+00:00",
                       "actor": "operator@example.com"}
        open(os.path.join(repo, "golden", "r1.cfg"), "w").write("hostname r1\nlldp run\n")
        git("commit", "-qam", "golden: r1")
        assert G.last_baseline_if_current(repo) is None, "a golden committed since"

    def test_a_denied_or_withdrawn_baseline_is_never_taken(self, monkeypatch):
        import routes.golden as G
        from modules.nsot import repo as R
        monkeypatch.setattr(R, "list_baselines", lambda r: [
            {"tag": "baseline/d", "commit": "x", "decision": "denied"},
            {"tag": "baseline/w", "commit": "y", "decision": "earned", "withdrawn": {"why": "w"}}])
        assert G.last_baseline_if_current("/nonexistent") is None


# ---------------------------------------------------------------------------
# (3) Every Needs attention row carries the age of its reading.
# ---------------------------------------------------------------------------

class TestEveryRowHasItsReading:
    def test_a_row_without_one_takes_its_source_s_value_time(self):
        from modules import attention as A

        def src():
            return A.source_result("baseline", "Baselines", read_at=2_000_000_000.0, took_ms=1,
                                   value_at=1_999_999_700.0, checked="one stored read", rows=[
                                       A.row(source="baseline", kind="unusable", key="k",
                                             what="No stored baseline can be re-applied",
                                             cause="all predate a rotation",
                                             action={"label": "Take a current baseline"},
                                             level="warning")])
        out = A.needs_attention(sources=[src])
        (r,) = [r for r in out["rows"] if r["source"] == "baseline"]
        assert r["read_at"] == A._iso(1_999_999_700.0), "the value's time, not the request's"

    def test_the_row_draws_its_age(self):
        page = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "v2",
                                 "_attention.html"), encoding="utf-8").read()
        meta = page.split('class="att-meta"')[1].split("</p>")[0]
        assert "read {{ stamp(r.read_at" in meta and "r.read_at[11:16]" not in meta
