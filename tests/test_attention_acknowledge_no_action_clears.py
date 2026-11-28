"""A Needs attention row a person cannot clear by an action offers Acknowledge… as its one
action, says its why once, and a time-only row offers nothing that does nothing to it (C4308,
C4309; the operator, 2026-11-27/28).

C4308: r7's command plan of 2026-11-17 (telemetry-subscription-recreate, its reads after the
plan timed out; tests/fixtures/receipts/r7_command_plan_unverified.json, the receipt as the
store held it) drew "The last command_plan to r7: failed" with its explanation twice (the
receipt's reason is verify's unreadable checks, joined, and the row said them again after
"could not be read reliably after the change:"), three actions (Open r7 on its line, Open r7
and Open… under What to do), and "clears when a later deploy or restore to the device finishes
clean" with no control for that.

C4309: detection's skipped span ("Self-healing did not scan configuration changes on Default
from … to …") began its explanation mid-sentence ("older than detection's 24 h horizon when it
read again.") and offered a drift check's Open… and job health's Run the check again, neither
of which clears it: it clears only by time.

- **The population, by property:** every kind whose clearing has no "resolves" way (time, or a
  person's word, alone) is acknowledged here; a planted kind without it is found.
- **r7's row:** its why once, acknowledged per receipt, its one action Acknowledge… on its line
  and under What to do (the receipt's words a link to where it is read), no Open r7, no Open…;
  acknowledged through the real route as the verified person it leaves, and a later failed
  receipt raises it again.
- **The gap row:** its explanation a whole sentence, its own kind cleared by time (its moment
  drawn) or acknowledged per span, no Open… and no Run the check again, Acknowledge… its action.
"""

import copy
import json
import os
import re
import time

import pytest

from modules import attention as A

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R7 = os.path.join(ROOT, "tests", "fixtures", "receipts", "r7_command_plan_unverified.json")


def _r7() -> dict:
    with open(R7, encoding="utf-8") as fh:
        return json.load(fh)["receipt"]


def _rows(*receipts):
    return A.deploy_source(read=lambda: {"state": "ok", "rows": list(receipts)})["rows"]


def _draw(rows) -> str:
    """The list as Needs attention draws it, from these rows (`v2/_attention.html`)."""
    from flask import render_template

    import app as APP
    with APP.app.test_request_context("/v2/"):
        return render_template("v2/_attention.html", a={
            "ok": True, "rows": rows, "sources": [], "headline": "1", "counts": {},
            "badge": {"n": len(rows), "level": rows[0]["level"]}})


def _item(html: str, row_id: str) -> str:
    """One row's markup: from its `data-attention-row` to the next row's."""
    start = html.index(f'data-attention-row="{row_id}"')
    nxt = html.find("data-attention-row=", start + 1)
    return html[start:nxt if nxt > 0 else len(html)]


def _line(item: str) -> str:
    return item.split('class="att-primary"', 1)[1].split("</summary>", 1)[0]


def _todo(item: str) -> str:
    return item.split('class="att-action"', 1)[1].split('class="att-ack"', 1)[0]


class TestThePopulation:
    def test_every_kind_that_never_resolves_is_acknowledged_here(self):
        """By property, never a list: a kind that clears by time or a person's word alone has
        no action that clears it, so a person's acknowledgement is how it leaves."""
        never = [k for k, (ways, _w) in A.CLEARS.items() if "resolves" not in ways]
        assert len(never) >= 5, never                 # the floor: the scan saw the kinds
        missing = [k for k in never if k not in A.ACKNOWLEDGED_HERE]
        assert missing == [], f"kinds no action clears, with no Acknowledge…: {missing}"

    def test_a_planted_time_only_kind_without_it_is_found(self):
        planted = {**A.CLEARS, ("planted", "time_only"): (("time",), "a day passes")}
        never = [k for k, (ways, _w) in planted.items() if "resolves" not in ways]
        assert [k for k in never if k not in A.ACKNOWLEDGED_HERE] == [("planted", "time_only")]


class TestRsevensRow:
    def test_its_why_is_said_once(self):
        (r,) = _rows(_r7())
        assert r["kind"] == "failed" and r["level"] == "danger"
        assert r["cause"].count("The streams are back: 101:") == 1, r["cause"]
        assert "could not be read reliably after the change" not in r["cause"]
        assert r["cause"].count("whether it is net zero cannot be told") == 1

    def test_a_finding_the_reason_does_not_say_is_still_said(self):
        """Said once, never dropped: an unreadable check the reason does not hold is named."""
        rec = _r7()
        rec["checks"]["unreadable"].append("BGP's neighbours could not be read after it")
        (r,) = _rows(rec)
        assert ("could not be read reliably after the change: BGP's neighbours could not be "
                "read after it") in r["cause"]

    def test_it_is_acknowledged_per_receipt_and_acknowledge_is_its_action(self):
        (r,) = _rows(_r7())
        assert r["acknowledge"] is True and r["event"] == "c4308r7plan0001a"
        assert A.first_action(r) == "acknowledge"
        assert "acknowledges this one with a reason" in r["clears"]["when"]

    def test_an_earned_baseline_after_it_clears_it_and_what_was_checked_names_it(self):
        """C4322: r7's row stood while r7 was at intent in baseline 20261127T233631Z. An earned
        baseline recorded after the run measured the device at its intent, so the row clears
        and What was checked says which baseline; one recorded before it changes nothing."""
        rec = _r7()
        ran = A._ts(rec.get("completed_at") or rec.get("at"))
        assert ran, "the premise: the receipt is dated"
        seen = []

        def baseline(lst, at):
            seen.append(lst)
            return {"tag": "baseline/20261127T233631Z", "at": at}
        after = A.deploy_source(read=lambda: {"state": "ok", "rows": [rec]},
                                baseline=lambda lst: baseline(lst, ran + 60))
        assert after["rows"] == [], after["rows"]
        assert "1 failed and at intent since, in baseline baseline/20261127T233631Z" in \
            after["checked"], after["checked"]
        before = A.deploy_source(read=lambda: {"state": "ok", "rows": [rec]},
                                 baseline=lambda lst: baseline(lst, ran - 60))
        assert [r["kind"] for r in before["rows"]] == ["failed"]
        assert "at intent since" not in before["checked"]
        none = A.deploy_source(read=lambda: {"state": "ok", "rows": [rec]},
                               baseline=lambda lst: {})
        assert [r["kind"] for r in none["rows"]] == ["failed"]
        assert len(seen) == 2, "asked once per read, only while such a row would be drawn"

    def test_the_newest_baseline_is_read_from_the_tags_passing_a_withdrawn_one(
            self, tmp_path, monkeypatch):
        import subprocess
        from modules import config
        from modules.nsot import record_exceptions

        repo = tmp_path / "Net" / "config_repo"
        repo.mkdir(parents=True)

        def git(*a, when="2026-11-27T23:00:00Z"):
            env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when,
                       GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                       GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
            return subprocess.run(["git", *a], cwd=repo, env=env, check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("init", "-q")
        git("commit", "-q", "--allow-empty", "-m", "one", when="2026-11-27T22:00:00Z")
        git("tag", "-a", "baseline/20261127T220000Z", "-m", "earned",
            when="2026-11-27T22:00:00Z")
        git("commit", "-q", "--allow-empty", "-m", "two", when="2026-11-27T23:36:31Z")
        git("tag", "-a", "baseline/20261127T233631Z", "-m", "earned",
            when="2026-11-27T23:36:31Z")
        monkeypatch.setattr(config, "get_list_data_dir", lambda lst: str(tmp_path / lst))
        got = A._newest_baseline("Net")
        assert got == {"tag": "baseline/20261127T233631Z", "at": A._ts("2026-11-27T23:36:31Z")}
        newest = git("rev-parse", "baseline/20261127T233631Z^{commit}")
        monkeypatch.setitem(record_exceptions.WITHDRAWN_BASELINES, newest,
                            {"tag": "baseline/20261127T233631Z", "why": "a test's"})
        assert A._newest_baseline("Net")["tag"] == "baseline/20261127T220000Z"
        assert A._newest_baseline("Absent") == {}

    def test_a_baseline_never_clears_a_failed_run_left_unsaved(self):
        rec = _r7()
        rec["saved_startup"] = {"state": "not_saved", "detail": "the save was refused"}
        rec["outcome"] = "failed"
        ran = A._ts(rec.get("completed_at") or rec.get("at"))
        got = A.deploy_source(read=lambda: {"state": "ok", "rows": [rec]},
                              baseline=lambda lst: {"tag": "baseline/x", "at": ran + 60})
        assert [r["kind"] for r in got["rows"]] == ["failed"], got["rows"]

    def test_it_draws_one_action(self):
        (r,) = _rows(_r7())
        item = _item(_draw([r]), r["id"])
        line = _line(item)
        assert re.findall(r'class="btn[^"]*"[^>]*>([^<]+)<', line) == ["Acknowledge…"], line
        assert f'href="#att-ack-{r["id"].replace(":", "%3A")}"' in line
        todo = _todo(item)
        assert "btn" not in todo and "Open r7" not in todo and "Open…" not in todo, todo
        assert ('<a class="att-label att-read" href="/v2/device/r7?tab=history">Read its '
                "receipt") in todo
        assert f'id="att-ack-{r["id"]}"' in item, "the line's jump lands on the form's button"
        assert item.count("Open r7") == 0

    def test_acknowledged_through_the_route_it_leaves_and_a_later_failure_returns(
            self, tmp_path, monkeypatch):
        from modules import acknowledgements
        from modules.nsot import receipts
        from tests.test_acknowledge import _ack, _attention, _only

        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        held = [_r7()]
        monkeypatch.setattr(receipts, "read", lambda *_a, **_k: {"state": "ok",
                                                               "rows": list(held)})
        _only(monkeypatch, "deploy_source")
        (r,) = [x for x in _attention()["rows"] if "r7" in x["devices"]]
        got = _ack(r["id"], r["event"], "streams back since; r7 is at intent in its baseline")
        assert got.status_code == 200, got.get_json()
        rec = acknowledgements.read()["rows"][0]
        assert rec["by"] == "test-person@example.invalid" and rec["event"] == r["event"]
        assert [x for x in _attention()["rows"] if "r7" in x["devices"]] == []
        later = dict(copy.deepcopy(held[0]), id="c4308r7plan0002b",
                     at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        held.insert(0, later)
        (again,) = [x for x in _attention()["rows"] if "r7" in x["devices"]]
        assert again["event"] == "c4308r7plan0002b"


NS = 10 ** 9


@pytest.fixture
def healing(monkeypatch):
    monkeypatch.setattr("modules.heal.policy.current",
                        lambda n: {"mode": "dry_run" if n == "Default" else "off"})


def _gap_row(now):
    """Detection's skipped span, as its liveness writes it and job health draws it."""
    from modules.heal import detect_read as D

    gap = {"from": int((now - 36 * 3600) * NS), "to": int((now - 24 * 3600) * NS),
           "from_at": "2026-11-25T23:29:00Z", "to_at": "2026-11-26T11:30:00Z",
           "until": now + 19 * 3600, "why": "older than detection's 24 h horizon when it "
                                            "read again"}
    got = {"state": "ok", "doc": {
        "last_attempt": {"at": "x", "ok": True},
        "last_good": {"value": {"configured": True, "unscanned": gap},
                      "value_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 2))}}}
    (job,) = D.liveness(D.READER, got, now)
    res = A.job_health_source(health=lambda: {"jobs": [job]})
    (r,) = res["rows"]
    return r, gap


class TestTheGapRow:
    def test_its_explanation_is_a_whole_sentence(self, healing):
        r, _gap = _gap_row(time.time())
        assert r["what"].startswith("Self-healing did not scan configuration changes on Default")
        assert r["cause"][0].isupper() and not r["cause"].startswith("older"), r["cause"]
        assert "24 h horizon" in r["cause"] and r["cause"].endswith(".")

    def test_it_clears_by_time_or_a_persons_word_and_offers_nothing_else(self, healing):
        now = time.time()
        r, gap = _gap_row(now)
        assert (r["source"], r["kind"]) == ("job_health", "unscanned")
        assert r["clears"]["ways"] == ["acknowledge", "time"]
        assert r["clears_at"] == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(gap["until"]))
        assert r["acknowledge"] is True and r["event"] == f"{gap['from']}-{gap['to']}"
        assert not r["action"].get("href") and A.first_action(r) == "acknowledge"

    def test_no_run_the_check_again_on_a_row_a_reading_does_not_clear(self, healing):
        r, _gap = _gap_row(time.time())
        res = A.source_result("job_health", "Job health", read_at=time.time(), took_ms=1,
                              rows=[r], reader=A.JOB_HEALTH_READER,
                              checked="2 job-health row(s)")
        other = A.row(source="job_health", kind="job", key="nightly-backup", level="warning",
                      what="nightly-backup has not succeeded recently", cause="c",
                      action={"label": "read its output"})
        res["rows"].append(other)
        drawn = {x["id"]: x for x in A.assemble([res])["rows"]}
        gap_row, job_row = drawn[r["id"]], drawn[other["id"]]
        assert not gap_row.get("reader"), "Run the check again does nothing to this row"
        assert job_row.get("reader") == A.JOB_HEALTH_READER, "a row a reading clears keeps it"

    def test_it_draws_acknowledge_and_when_it_clears_alone(self, healing):
        r, _gap = _gap_row(time.time())
        item = _item(_draw([r]), r["id"])
        assert re.findall(r'class="btn[^"]*"[^>]*>([^<]+)<', _line(item)) == ["Acknowledge…"]
        todo = _todo(item)
        assert "btn" not in todo and "Open…" not in todo and "Diagnostics" not in todo, todo
        assert "Clears when a day after detection read again (by time)" in item
        assert "Run the check again" not in item
