"""What a person has seen under "Finished, not opened yet" is kept, per person (C3081; the
operator, 2026-11-12: ""Finished, not opened yet" keeps r7's two failed runs (16:49 and 20:12
UTC) after I press "Open the result"; they're back on every page, and the "2 failed" chip
stays. Opening a result must mark it seen PERSISTENTLY (per person, stored), so it leaves the
list and the chip; add a "Dismiss" on each entry too").

Before it, "opened" was kept in memory only (`heal.run_card._opened`, each job's ``opened``),
so a restart listed again every run of the day a person had opened; and the device's page
reopened the device's NEWEST unopened run, whichever entry was pressed.

Through the real app over the re-subscribe's lab (tests/test_run_outcomes.py's ``resub``: two
real runs of r2 whose streams did not come back, recorded as the operations' records keep them),
the real chip, the real route and the real device page. "A restart" is what one loses: the jobs
this process held, the in-memory marks, and the store's parsed cache; the store is read again
from its file.
"""
import json
import os
import re
import stat

import pytest

from tests.conftest import TEST_PERSON
from tests.test_heal_resubscribe import NET
from tests.test_heal_resubscribe import lab as resub_lab  # noqa: F401 (the fixtures resub uses)
from tests.test_run_outcomes import HX, bar, not_back, resub, run_one  # noqa: F401 (fixture)
from tests.test_sdn_connections import networks  # noqa: F401 (the lab builds on it)

OTHER = "someone-else@example.invalid"
FORM = re.compile(r'<form class="ip-acts"[^>]*>(.*?)</form>', re.S)
HIDDEN = re.compile(r'<input type="hidden" name="(\w+)" value="([^"]*)">')


@pytest.fixture
def store(tmp_path, monkeypatch):
    """The store where the app keeps it, in this test's own data folder (the lab's
    `networks` points the data folder at the same *tmp_path*)."""
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return tmp_path / "seen_runs.json"


def restart(monkeypatch):
    """Mercury restarted: no job held, nothing remembered in memory, and the store's module
    loaded afresh (its parsed cache gone), so what it knows is what its file holds."""
    import importlib

    from modules import seen_runs
    from modules.heal import run_card
    from modules.nsot import capture_job
    monkeypatch.setattr(capture_job, "_jobs", {})
    monkeypatch.setattr(run_card, "_opened", {})
    importlib.reload(seen_runs)


def entries(html):
    """Each Finished entry's form, as its hidden fields: ``[{"job", "run", "device", "list"}]``."""
    return [dict(HIDDEN.findall(f)) for f in FORM.findall(html)]


def press(c, entry, how):
    return c.post("/v2/operations/seen", data=dict(entry, how=how), headers=HX)


def two_failed_runs(c, monkeypatch):
    """Two re-subscribes of r2 that ended failed, started by the person looking: one
    subscription, then two, so each run's card is told apart by its steps. The card that
    started the second led with the first's outcome, which this process remembers in memory as
    drawn; that memory is let go, as a restart lets it go (the operator's r7: both listed)."""
    from modules.heal import run_card
    from modules.nsot import privileged
    run_one(c, not_back(), subs=("101",))
    run_one(c, not_back(), subs=("101", "102"))
    monkeypatch.setattr(run_card, "_opened", {})
    newer, older = privileged.runs(NET)["runs"][:2]
    assert len(newer["steps"]) != len(older["steps"]), "the premise: the cards differ"
    return newer, older


class TestOpening:
    def test_it_leaves_the_list_and_the_chip_for_that_person_and_stays_after_a_restart(
            self, resub, store, monkeypatch):
        from modules.nsot import capture_job
        newer, older = two_failed_runs(resub, monkeypatch)
        html = bar(resub)
        assert "In progress: 2 failed" in html and "Finished, not opened yet · 2" in html
        both = entries(html)
        assert {e["run"] for e in both} == {newer["id"], older["id"]}
        pick = next(e for e in both if e["run"] == older["id"])      # the OLDER, not the newest
        r = press(resub, pick, "opened")
        assert r.status_code == 204, r.get_data(as_text=True)
        assert r.headers["HX-Redirect"] == f"/v2/device/r2?list={NET}&result={pick['job']}"
        body = resub.get(f"/v2/device/r2?list={NET}&result={pick['job']}").get_data(as_text=True)
        # Premise corrected (the operator, 2026-11-12: a run's card draws its stages, each
        # expanding to its steps): the pressed run's card, its own record id on it.
        assert older["id"][-12:] in body and newer["id"][-12:] not in body, \
            "the run pressed, opened"
        assert 'class="run-stages"' in body
        html = bar(resub)
        assert "In progress: 1 failed" in html and "Finished, not opened yet · 1" in html
        assert [e["run"] for e in entries(html)] == [newer["id"]]
        # Its effect, kept: this person, this run (its job's id and its run's), opened.
        assert store.exists(), "kept in its file"
        kept = json.loads(store.read_text())["entries"]
        assert {(e["viewer"], e["id"], e["how"]) for e in kept} == {
            (TEST_PERSON, pick["job"], "opened"), (TEST_PERSON, older["id"], "opened")}
        # Another person still sees it (a job's result is everybody's while it is kept).
        resub.state["viewer"] = OTHER
        assert len(entries(bar(resub))) == 2, "another person's list is their own"
        resub.state["viewer"] = TEST_PERSON
        restart(monkeypatch)
        assert capture_job.card_jobs() == [], "the premise: nothing in memory"
        html = bar(resub)
        assert "In progress: 1 failed" in html, "after a restart it does not come back"
        assert [e["run"] for e in entries(html)] == [newer["id"]]

    def test_its_page_is_the_run_pressed_after_a_restart_too(self, resub, store, monkeypatch):
        newer, older = two_failed_runs(resub, monkeypatch)
        restart(monkeypatch)
        pick = next(e for e in entries(bar(resub)) if e["run"] == older["id"])
        assert pick["job"] == "", "known by its record alone"
        r = press(resub, pick, "opened")
        assert r.status_code == 204
        assert r.headers["HX-Redirect"] == f"/v2/device/r2?list={NET}&result={older['id']}"
        body = resub.get(f"/v2/device/r2?list={NET}&result={older['id']}").get_data(as_text=True)
        assert older["id"][-12:] in body and newer["id"][-12:] not in body
        assert 'class="run-stages"' in body
        restart(monkeypatch)
        assert [e["run"] for e in entries(bar(resub))] == [newer["id"]]

    def test_without_script_it_is_a_303_to_the_same_page(self, resub, store, monkeypatch):
        _newer, older = two_failed_runs(resub, monkeypatch)
        pick = next(e for e in entries(bar(resub)) if e["run"] == older["id"])
        r = resub.post("/v2/operations/seen", data=dict(pick, how="opened"))
        assert r.status_code == 303 and "/v2/device/r2" in r.headers["Location"]
        # Its effect without script too: this person, this run, opened, kept in its file.
        kept = json.loads(store.read_text())["entries"]
        assert {(e["viewer"], e["id"], e["how"]) for e in kept} == {
            (TEST_PERSON, pick["job"], "opened"), (TEST_PERSON, older["id"], "opened")}


class TestDismissing:
    def test_it_leaves_the_list_in_place_and_stays_after_a_restart(self, resub, store,
                                                                   monkeypatch):
        newer, older = two_failed_runs(resub, monkeypatch)
        pick = next(e for e in entries(bar(resub)) if e["run"] == newer["id"])
        r = press(resub, pick, "dismissed")
        assert r.status_code == 200
        drawn = r.get_data(as_text=True)
        assert "HX-Redirect" not in r.headers, "it stays on the page"
        assert "In progress: 1 failed" in drawn and "Finished, not opened yet · 1" in drawn
        assert [e["run"] for e in entries(drawn)] == [older["id"]], "the list drawn in place"
        assert "in_progress" in r.headers.get("X-NMAS-Invalidates", ""), "every chip redraws"
        assert store.exists(), "kept in its file"
        kept = json.loads(store.read_text())["entries"]
        assert {e["how"] for e in kept} == {"dismissed"} and {e["viewer"] for e in kept} == {
            TEST_PERSON}
        resub.state["viewer"] = OTHER
        assert len(entries(bar(resub))) == 2, "another person's list is their own"
        resub.state["viewer"] = TEST_PERSON
        restart(monkeypatch)
        assert [e["run"] for e in entries(bar(resub))] == [older["id"]]

    def test_both_gone_the_chip_goes(self, resub, store, monkeypatch):
        two_failed_runs(resub, monkeypatch)
        for e in entries(bar(resub)):
            assert press(resub, e, "dismissed").status_code == 200
        assert "ip-chip" not in bar(resub)
        restart(monkeypatch)
        assert "ip-chip" not in bar(resub), "neither comes back"


class TestRefused:
    def test_nobody_verified_cannot_mark_and_open_is_the_page_s_link(self, resub, store,
                                                                   monkeypatch):
        two_failed_runs(resub, monkeypatch)
        pick = entries(bar(resub))[0]
        resub.state["viewer"] = ""                    # the gate open to anyone (the kit's)
        html = bar(resub)
        assert entries(html) == [] and "Dismiss" not in html, "no mark to keep for nobody"
        assert html.count(">Open the result</a>") == 2, "each still opens its page"
        assert f"?list={NET}&amp;result={pick['job']}" in html, "on its own run"
        r = press(resub, pick, "dismissed")
        assert r.status_code == 403
        assert "Not marked dismissed: nobody verified is looking" in r.get_data(as_text=True)
        assert not store.exists(), "nothing was written"

    @pytest.mark.real_identity
    def test_the_gate_refuses_an_unverified_request(self, store):
        import app as A
        A.app.config["TESTING"] = True
        r = A.app.test_client().post("/v2/operations/seen",
                                     data={"run": "20261112T164900-x", "how": "dismissed"},
                                     headers=HX)
        assert r.status_code in (401, 403), r.status_code
        assert not store.exists()

    def test_an_unreadable_store_refuses_says_so_and_lists_everything(self, resub, store,
                                                                     monkeypatch):
        from modules import seen_runs
        _newer, older = two_failed_runs(resub, monkeypatch)
        store.write_text("{not json")
        before = store.read_bytes()
        html = bar(resub)
        assert "What you have opened could not be read" in html
        assert "Finished, not opened yet · 2" in html and "In progress: 2 failed" in html
        assert entries(html) == [] and html.count(">Open the result</a>") == 2
        # A press drawn before the store broke: refused, said, nothing written.
        pick = {"job": "", "run": older["id"], "device": "r2", "list": NET}
        r = press(resub, pick, "dismissed")
        assert r.status_code == 409, r.get_data(as_text=True)
        assert "Not marked dismissed:" in r.get_data(as_text=True)
        got = seen_runs.mark(TEST_PERSON, ["a-run"], "dismissed")
        assert not got["ok"] and "cannot be read" in got["error"]
        assert store.read_bytes() == before, "nothing written over it"
        assert seen_runs.is_seen(TEST_PERSON, "a-run") is False


class TestAReadWritesNothing:
    def test_the_chip_and_the_device_page_write_nothing(self, resub, store, monkeypatch):
        two_failed_runs(resub, monkeypatch)
        bar(resub)
        resub.get(f"/v2/device/r2?list={NET}")
        assert not store.exists(), "no store made by a read"
        pick = entries(bar(resub))[0]
        assert press(resub, pick, "dismissed").status_code == 200
        assert store.exists(), "the press kept it"
        before = (store.read_bytes(), os.stat(store).st_mtime_ns)
        bar(resub)
        resub.get(f"/v2/device/r2?list={NET}&result={pick['run']}")
        assert (store.read_bytes(), os.stat(store).st_mtime_ns) == before


class TestTheStore:
    def test_it_keeps_the_newest_2000(self, store):
        from modules import seen_runs
        assert seen_runs.KEEP == 2000
        full = [{"viewer": TEST_PERSON, "id": f"run-{i}", "how": "opened",
                 "at": "2026-11-12T00:00:00Z"} for i in range(seen_runs.KEEP)]
        store.write_text(json.dumps({"entries": full}))
        assert seen_runs.mark(TEST_PERSON, ["new-1", "new-2"], "dismissed")["news"]
        ids = [e["id"] for e in seen_runs.read()["entries"]]
        assert len(ids) == seen_runs.KEEP and ids[:1] == ["run-2"] and ids[-2:] == [
            "new-1", "new-2"], "the oldest two go"
        assert not seen_runs.is_seen(TEST_PERSON, "run-1") and seen_runs.is_seen(
            TEST_PERSON, "new-2")
        assert stat.S_IMODE(os.stat(store).st_mode) == 0o600, "replaced owner-only"

    def test_marks_are_per_person_and_once(self, store):
        from modules import seen_runs
        assert not store.exists()
        assert seen_runs.mark(TEST_PERSON, ["j1", "r1"], "opened")["news"]
        assert store.exists(), "kept in its file"
        assert stat.S_IMODE(os.stat(store).st_mode) == 0o600, "owner-only from creation"
        assert not seen_runs.mark(TEST_PERSON, ["r1"], "dismissed")["news"], "once is news"
        assert seen_runs.is_seen(TEST_PERSON, "r1") and not seen_runs.is_seen(OTHER, "r1")
        assert not seen_runs.mark("", ["r1"], "opened")["ok"]
        assert not seen_runs.mark(TEST_PERSON, ["r1"], "read")["ok"]
        assert not seen_runs.mark(TEST_PERSON, [], "opened")["ok"]
