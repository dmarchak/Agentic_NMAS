"""A scheduled quality job's failed row is acknowledged until the workflow's next scheduled run
(the operator, 2026-11-11: "an acknowledge with reason and expiry, or say why it should stay
open"; the decision taken: acknowledgeable with a typed reason, the acknowledgement EXPIRING at
the next scheduled run read from the workflow's cron, so a red that persists comes back by
itself).

On the mutation workflow's real failed runs (#68 newest, captured 2026-11-03,
tests/fixtures/github/) and this checkout's own workflows (`0 14 * * 0`):

- the next scheduled run is read from a cron, in UTC, strictly after now; a cron that cannot be
  read gives none, and then nothing is acknowledged;
- through the real route, the acknowledgement records its reason, who, and *until* that next
  run; the row leaves and is listed "Acknowledged by <name> until the next scheduled run
  (<when>): <reason>"; the count re-reads at that moment;
- past it the row comes back by itself, naming the acknowledgement that ended; a later failed
  run is a new row;
- the expiry is declared for that one kind: an overdue row is not acknowledged here, and an
  acknowledgement of any other kind never expires so.
"""

import calendar
import json
import time

import pytest

from tests.test_scheduled_jobs import _github, repo  # noqa: F401 (the fixture)

ROW = "scheduled_jobs:mutation-nightly.yml"
RUN_68 = "41337732668"
WHY = "the mutation canary is being reworked this week (C2551)"
PERSON = "test-person@example.invalid"


def _epoch(stamp):
    return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))


def _iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def failed(repo, store, monkeypatch):  # noqa: F811
    """The scheduled-jobs reader's stored value, read just now, from the captures; Needs
    attention with that source alone."""
    from modules import attention, reader_job
    from modules.readers import scheduled_jobs as SJ
    value = SJ.read(repo, get=_github())
    fresh = {"state": "ok", "doc": {"last_good": {"value": value, "value_at": _iso(time.time())},
                                    "stale_after_seconds": 3600}}
    real = reader_job.read_cached
    monkeypatch.setattr(reader_job, "read_cached",
                        lambda name: fresh if name == SJ.NAME else real(name))
    monkeypatch.setattr(attention, "SOURCES", [attention.scheduled_jobs_source])
    return value


def _client():
    from app import app
    app.config["TESTING"] = True
    return app.test_client()


def _attention():
    from app import app
    from routes.v2 import _attention as page
    with app.test_request_context("/v2/attention"):
        return page()


def _ack(event=RUN_68, why=WHY):
    return _client().post("/attention/acknowledge", json={"row": ROW, "event": event, "why": why})


class TestTheNextScheduledRun:
    @pytest.mark.parametrize("cron, after, then", [
        ("0 14 * * 0", "2026-11-11T12:00:00Z", "2026-11-15T14:00:00Z"),   # a Wednesday
        ("0 14 * * 0", "2026-11-15T14:00:00Z", "2026-11-22T14:00:00Z"),   # strictly after
        ("0 14 * * 0", "2026-11-15T13:59:59Z", "2026-11-15T14:00:00Z"),
        ("47 3 * * *", "2026-11-11T12:00:00Z", "2026-11-12T03:47:00Z"),
        ("*/15 * * * *", "2026-11-11T12:07:00Z", "2026-11-11T12:15:00Z"),
        ("0 6 1 * *", "2026-11-11T12:00:00Z", "2026-12-01T06:00:00Z"),
        ("0 0 * * 7", "2026-11-11T12:00:00Z", "2026-11-15T00:00:00Z"),    # 7 is Sunday too
        ("0 14 * * 0; 47 3 * * *", "2026-11-11T12:00:00Z", "2026-11-12T03:47:00Z"),
    ])
    def test_a_cron_s_next_run_in_utc(self, cron, after, then):
        from modules.readers import scheduled_jobs as SJ
        assert _iso(SJ.next_run(cron, _epoch(after))) == then

    @pytest.mark.parametrize("cron", ["", "0 14 * *", "0 14 * * MON", "61 * * * *", "0 14 * * 0;"])
    def test_one_it_cannot_read_gives_none(self, cron):
        from modules.readers import scheduled_jobs as SJ
        assert SJ.next_run(cron, _epoch("2026-11-11T12:00:00Z")) is None


class TestAcknowledgingAFailedRun:
    def test_the_drawn_acknowledge_names_its_newest_run_and_is_accepted(self, failed):
        """Pressed: the form the page draws posts its row and event, and the record keeps that
        run's id."""
        import re

        from modules.acknowledgements import read
        (r,) = [x for x in _attention()["rows"] if x["id"] == ROW]
        assert r["acknowledge"] is True and r["event"] == RUN_68 and r["kind"] == "failed"
        assert r["clears"]["ways"] == ["resolves", "acknowledge"]
        assert "until the workflow's next scheduled run by its cron" in r["clears"]["when"]
        html = _client().get("/v2/attention").get_data(as_text=True)
        form = re.search(r'<div class="att-ack"[^>]*data-row="scheduled_jobs:mutation-nightly'
                         r'\.yml" data-event="(\d+)"', html)
        assert form and "Why this can wait until the next scheduled run" in html
        assert _ack(event=form.group(1)).status_code == 200
        (rec,) = read()["rows"]
        assert (rec["row"], rec["event"]) == (ROW, RUN_68)

    def test_through_the_route_it_holds_until_the_next_scheduled_run(self, failed):
        from modules.acknowledgements import read
        from modules.readers import scheduled_jobs as SJ
        before = SJ.next_run("0 14 * * 0", time.time())
        got = _ack()
        after = SJ.next_run("0 14 * * 0", time.time())
        assert got.status_code == 200, got.get_json()
        (rec,) = read()["rows"]
        assert (rec["row"], rec["event"], rec["by"], rec["why"]) == (ROW, RUN_68, PERSON, WHY)
        assert rec["expires"] == "next_scheduled_run"
        assert rec["until"] in {_iso(before), _iso(after)}
        when = f"{rec['until'][:10]} 14:00 UTC"
        said = f"Acknowledged by {PERSON} until the next scheduled run ({when}): {WHY}"
        assert got.get_json()["words"] == (f"Recorded: {said}. If that run has not succeeded "
                                           "by then, the row comes back by itself.")
        a = _attention()
        assert ROW not in [x["id"] for x in a["rows"]]
        (k,) = [x for x in a["acknowledged"] if x["id"] == ROW]
        assert k["said"] == said
        # The count re-reads at that moment, when the row comes back by itself.
        assert a["badge"]["next_change_at"] == rec["until"]
        html = _client().get("/v2/attention").get_data(as_text=True)
        assert "Acknowledged, so not listed" in html and said in html

    def test_past_its_moment_the_row_comes_back_naming_it(self, failed):
        from modules import acknowledgements as ACK
        ACK.record(ROW, RUN_68, why=WHY, by=PERSON, verified="access",
                   kind="scheduled_jobs/failed", what="w", expires=ACK.NEXT_SCHEDULED_RUN,
                   until_at=time.time() - 60)
        (r,) = [x for x in _attention()["rows"] if x["id"] == ROW]
        assert f"Acknowledged by {PERSON} until the next scheduled run (" in r["cause"]
        assert r["cause"].endswith(f"): {WHY}; that time has passed and the row's condition "
                                   "stands, so it is shown again")

    def test_a_later_failed_run_is_a_new_row(self, failed, monkeypatch):
        assert _ack().status_code == 200
        from modules import reader_job
        from modules.readers import scheduled_jobs as SJ
        value = json.loads(json.dumps(failed))
        w = next(x for x in value["workflows"] if x["file"] == "mutation-nightly.yml")
        w["newest"] = dict(w["newest"], id=41999999999, run_number=69,
                           created_at="2026-11-08T17:00:00Z")
        fresh = {"state": "ok", "doc": {"last_good": {"value": value,
                                                      "value_at": _iso(time.time())},
                                        "stale_after_seconds": 3600}}
        before = reader_job.read_cached
        monkeypatch.setattr(reader_job, "read_cached",
                            lambda name: fresh if name == SJ.NAME else before(name))
        (r,) = [x for x in _attention()["rows"] if x["id"] == ROW]
        assert r["event"] == "41999999999" and "Acknowledged by" not in r["cause"]

    def test_a_cron_that_cannot_be_read_acknowledges_nothing(self, failed, monkeypatch):
        from modules.acknowledgements import read
        from modules.readers import scheduled_jobs as SJ
        monkeypatch.setattr(SJ, "scheduled_workflows", lambda root=None: [])
        got = _ack()
        assert got.status_code == 409
        assert "holds only until the next scheduled run, and that could not be read" \
            in got.get_json()["error"]
        assert read()["state"] == "absent"

    def test_a_reason_is_required(self, failed):
        from modules.acknowledgements import read
        got = _ack(why="ok")
        assert got.status_code == 409 and "needs a reason" in got.get_json()["error"]
        assert read()["state"] == "absent"


class TestOnlyThisKindExpires:
    def test_the_expiry_is_declared_for_the_failed_kind_alone(self):
        from modules import acknowledgements as ACK
        from modules import attention as A
        assert ACK.EXPIRES == {("scheduled_jobs", "failed"): ACK.NEXT_SCHEDULED_RUN}
        assert set(ACK.EXPIRES) <= A.ACKNOWLEDGED_HERE
        assert ("scheduled_jobs", "overdue") not in A.ACKNOWLEDGED_HERE
        assert ("scheduled_jobs", "unread") not in A.ACKNOWLEDGED_HERE
        for kind in ACK.EXPIRES:
            assert "until the workflow's next scheduled run" in A.CLEARS[kind][1]

    def test_another_kind_s_acknowledgement_never_expires_so(self, store, monkeypatch):
        """A restart's acknowledgement recorded with an expiry past (none is ever recorded so,
        but a store is data) still covers its restart: the expiry is that one kind's."""
        from modules import acknowledgements as ACK
        from tests.test_acknowledge import _restarts_cached
        from tests.test_restarts import _read
        _restarts_cached(monkeypatch, _read(now=time.time()))
        from modules import attention
        monkeypatch.setattr(attention, "SOURCES", [attention.restart_source])
        (r,) = _attention()["rows"]
        ACK.record(r["id"], r["event"], why=WHY, by=PERSON, verified="access",
                   kind="restarts/unplanned", what=r["what"], expires=ACK.NEXT_SCHEDULED_RUN,
                   until_at=time.time() - 60)
        a = _attention()
        assert a["rows"] == [] and a["acknowledged"][0]["id"] == r["id"]
        assert "said" not in a["acknowledged"][0]

    def test_acknowledging_another_kind_records_no_expiry(self, store, monkeypatch):
        from modules.acknowledgements import read
        from tests.test_acknowledge import _restarts_cached
        from tests.test_restarts import _read
        _restarts_cached(monkeypatch, _read(now=time.time()))
        from modules import attention
        monkeypatch.setattr(attention, "SOURCES", [attention.restart_source])
        (r,) = _attention()["rows"]
        got = _client().post("/attention/acknowledge",
                             json={"row": r["id"], "event": r["event"], "why": WHY})
        assert got.status_code == 200, got.get_json()
        (rec,) = read()["rows"]
        assert "expires" not in rec and "until" not in rec
