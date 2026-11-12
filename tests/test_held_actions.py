"""A held device's actions (the operator, 2026-11-11, after a re-subscribe of r7: "While the
run is in progress, a page refresh offers 'Re-subscribe r7's telemetry' again. While a device
is held by a run, its actions must be disabled, saying 'running since <time>, by <who>', with
a link to the run."). Through the real app, on the re-subscribe's lab
(tests/test_heal_resubscribe.py), a real hold (`device_ops.hold`) and the real job starter. No
device, no network.

- **One owner:** what the page greys is read from the hold the server refuses by
  (`in_flight.held_action` over `device_ops.holder`); nothing held greys nothing; a hold that
  cannot be read is held, in words.
- **The Actions menu:** every row that would change the device is drawn disabled with the
  run's words on hover and for a reader, the note names the run and links to it, reads stay
  offered, and the rows return when the hold ends; the menu listens for the hold's start and
  end.
- **A Needs attention row:** its action is drawn as the run, with Open the run, on the row's
  line and under What to do, and returns when the hold ends; the list listens for it.
- **A refresh mid-run:** the re-subscribe card opened with no run named draws the run that is
  going, never a fresh offer; held by another operation, its buttons are not offered.
"""
import re
import threading
import time

import pytest

import modules.heal.resubscribe  # noqa: F401  (the operation whose row and card are drawn)
from tests.conftest import TEST_PERSON
from tests.test_heal_resubscribe import NET, Src
from tests.test_heal_resubscribe import lab as resub_lab  # noqa: F401
from tests.test_heal_resubscribe_v2 import HX, _instance, _rows, card, press
from tests.test_in_flight import no_hold_survives_a_test  # noqa: F401 (autouse)
from tests.test_sdn_connections import networks  # noqa: F401 (the lab builds on it)

WHO = "ops@example.invalid"
#: WHO as a screen names them (board E2a): by display name, the part before the "@".
SHOWN = WHO.split("@")[0]
CHANGING = ("Plan a deploy…", "Capture", "Seed intent…", "Restore from…",
            "Remove lines (Mode B)…", "Revert intent…", "Retry rolled-back change…",
            "Rotate credential…", "Persist", "Run a privileged command…", "Reload…",
            "Verify again…", "Re-key…", "Retire…")
READS = ("Check drift now…", "Diagnose…")


@pytest.fixture
def world(resub_lab, monkeypatch):  # noqa: F811
    """The real app's client over the re-subscribe's lab, the real job starter, one network,
    and the person looking named by the test."""
    import app as A
    from modules.nsot import capture_job

    state = {"src": Src(), "jobs": [], "viewer": TEST_PERSON}
    monkeypatch.setattr("modules.heal.resubscribe.Sources", lambda net, **kw: state["src"])
    real = capture_job.start

    def start(*a, **kw):
        state["jobs"].append(real(*a, **kw))
        return state["jobs"][-1]
    monkeypatch.setattr("modules.nsot.capture_job.start", start)
    monkeypatch.setattr("modules.integration_groups.network_names", lambda: [NET])
    monkeypatch.setattr("routes.operations.viewer_key", lambda: state["viewer"])
    monkeypatch.setattr(capture_job, "_jobs", {})
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    c.state = state
    yield c
    for job in state["jobs"]:
        assert capture_job.get(job) is None or capture_job.wait(job, 30), \
            f"job {job} did not end within 30 s"


def menu(c):
    r = c.get(f"/v2/device/r2/actions?list={NET}", headers=HX)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def row_of(html, label):
    """The menu row drawing *label*: its markup."""
    rows = [x for x in html.split('<div class="menu-row">')[1:] if f">{label}<" in x]
    assert len(rows) == 1, f"{len(rows)} rows draw {label!r}"
    return rows[0]


def clock_of(epoch):
    return time.strftime("%H:%M UTC", time.gmtime(epoch))


class TestOneOwner:
    def test_what_the_page_greys_is_the_hold_the_server_refuses_by(self, world):
        from modules import in_flight
        from modules.nsot import device_ops
        assert in_flight.held_action(NET, "r2", TEST_PERSON) is None, "nothing held"
        with device_ops.hold(NET, "r2", "rotate", WHO):
            started = device_ops.holder(NET, "r2")["started"]
            got = in_flight.held_action(NET, "r2", TEST_PERSON)
            assert got["words"] == f"Rotate credential running since {clock_of(started)}, by {SHOWN}"
            assert (got["by"], got["name"]) == (SHOWN, "Rotate credential")
            assert got["since"] == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
            assert in_flight.held_action(NET, "r2", WHO)["by"] == "you"
            refused = []

            def second():
                try:
                    device_ops.acquire(NET, "r2", "deploy", "other@example.invalid")
                except device_ops.DeviceBusy as exc:
                    refused.append(str(exc))
            t = threading.Thread(target=second)
            t.start()
            t.join(30)
            assert refused and WHO in refused[0], "the server refuses by the same hold"
        assert in_flight.held_action(NET, "r2", TEST_PERSON) is None, "released"

    def test_a_hold_that_cannot_be_read_is_held_in_words(self, world, monkeypatch):
        from modules import in_flight
        from modules.nsot import device_ops

        def unreadable(network, host):
            raise device_ops.HoldsUnreadable("/locks/r2.lock", PermissionError(13, "denied"))
        monkeypatch.setattr(device_ops, "holder", unreadable)
        got = in_flight.held_action(NET, "r2", TEST_PERSON)
        assert got["unread"] and "it is treated as held" in got["words"]


class TestTheActionsMenu:
    def test_every_changing_row_is_disabled_with_the_run_and_reads_stay(self, world):
        from modules.nsot import device_ops
        free = menu(world)
        assert "aria-disabled" not in row_of(free, "Plan a deploy…") and \
            'data-op="deploy"' in free
        with device_ops.hold(NET, "r2", "telemetry re-subscribe", WHO):
            started = device_ops.holder(NET, "r2")["started"]
            # A SHORT reason on hover (the operator, 2026-11-11): a dozen words at most.
            short = f"held by Re-subscribe telemetry since {clock_of(started)}"
            assert len(f"Not offered: {short}".split()) <= 12
            html = menu(world)
            for label in CHANGING:
                row = row_of(html, label)
                assert 'aria-disabled="true"' in row and "<a " not in row, label
                assert f'title="Not offered: {short}"' in row, label
                assert f"(not offered: {short})" in row, f"{label}: said to a reader too"
            for label in READS:
                assert "<a " in row_of(html, label) and "aria-disabled" not in row_of(
                    html, label), f"{label} is a read: it stays offered (C3095)"
            # Items only: no notice and no paragraph in the menu.
            assert "is held" not in html and "Every action runs here" not in html
            assert '<p class="menu-note"' not in html and "Open the run" not in html
            # The effect behind the grey: the device is held, by that person.
            assert device_ops.busy_text(NET, "r2").startswith("r2 is being ")
        back = menu(world)
        assert "<a " in row_of(back, "Plan a deploy…") and "<a " in row_of(back, "Reload…")
        assert device_ops.holder(NET, "r2") is None

    def test_the_notice_is_a_banner_under_the_device_s_name_never_menu_text(self, world):
        """The operator, 2026-11-11: "The held notice moves OUT of the Actions menu into a
        banner under the device's name, across the page: 'r7 is held: <run> since <time>, by
        <name> · Open the run'.\""""
        from modules.nsot import device_ops

        def banner():
            r = world.get(f"/v2/device/r2/held?list={NET}", headers=HX)
            assert r.status_code == 200
            return r.get_data(as_text=True)
        assert banner().strip() == "", "nothing held: no banner"
        with device_ops.hold(NET, "r2", "telemetry re-subscribe", WHO):
            html = banner()
            assert 'class="notice notice-warning held-banner" role="status" data-held="r2"' \
                in html
            said = re.sub(r"<svg.*?</svg>", "", html, flags=re.S)
            said = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", said)).strip()
            assert re.fullmatch(r"r2 is held: Re-subscribe telemetry since \d\d:\d\d UTC, "
                                rf"by {re.escape(SHOWN)} · Open the run", said), said
            assert f'<a href="/v2/device/r2?list={NET}">Open the run</a>' in html
            page = world.get(f"/v2/device/r2?list={NET}").get_data(as_text=True)
            at = page.index('id="device-held"')
            assert page.index("<h1") < at < page.index('role="tablist"'), \
                "under the device's name, above the tabs"
            region = page[at:page.index('role="tablist"')]
            assert "r2 is held:" in region and page.count("r2 is held:") == 1, \
                "drawn with the page, once"
            trigger = re.search(r'id="device-held"[^>]*hx-trigger="([^"]+)"', page).group(1)
            assert trigger == "nmas:device_holds from:body, nmas:in_progress from:body"
            assert device_ops.holder(NET, "r2")["actor"] == WHO
        assert banner().strip() == "", "the hold ended: the banner is gone"

    def test_a_hold_that_cannot_be_read_is_said_in_the_banner(self, world, monkeypatch):
        from modules.nsot import device_ops

        def unreadable(network, host):
            raise device_ops.HoldsUnreadable("/locks/r2.lock", PermissionError(13, "denied"))
        monkeypatch.setattr(device_ops, "holder", unreadable)
        html = world.get(f"/v2/device/r2/held?list={NET}", headers=HX).get_data(as_text=True)
        assert "r2 is held:" in html and "it is treated as held" in html
        from modules import in_flight
        assert in_flight.held_action(NET, "r2", TEST_PERSON)["unread"], \
            "the state it says: a hold that could not be read, never nobody's"
        assert 'title="Not offered: its hold could not be read: treated as held"' in row_of(
            menu(world), "Plan a deploy…")

    def test_the_menu_listens_for_a_hold_s_start_and_its_end(self, world):
        page = world.get(f"/v2/device/r2?list={NET}").get_data(as_text=True)
        trigger = re.search(r'id="actions-menu"[^>]*hx-trigger="([^"]+)"', page, re.S).group(1)
        assert "nmas:device_holds from:body" in trigger and "nmas:in_progress from:body" in trigger
        from modules import in_flight, invalidation
        assert set(in_flight.HELD_KEYS) <= set(invalidation.VOCABULARY)


def attention(rows):
    """The Needs attention list drawn for *rows*, as its route marks and draws them."""
    import app as A
    from flask import render_template

    from modules import in_flight
    with A.app.test_request_context("/v2/"):
        in_flight.mark_held(rows, TEST_PERSON)
        return render_template("v2/_attention.html", a={"rows": rows, "sources": [],
                                                         "badge": {"n": len(rows)}})


class TestANeedsAttentionRow:
    def lost(self):
        rows = _rows(_instance("r2", "NMAS telemetry stream lost: r2 subscription 101", 1))
        rows[0]["networks"] = {"r2": [NET]}
        return rows

    def test_a_held_device_s_action_is_the_run_and_returns_when_it_ends(self, world):
        from modules.nsot import device_ops
        offer = "Re-subscribe r2's telemetry (101)…</a>"
        assert offer in attention(self.lost()) and "data-held" not in attention(self.lost())
        with device_ops.hold(NET, "r2", "deploy", WHO):
            started = device_ops.holder(NET, "r2")["started"]
            rows = self.lost()
            html = attention(rows)
            assert rows[0]["held"]["words"] == (
                f"Deploy running since {clock_of(started)}, by {SHOWN}")
            assert offer not in html, "the action is not offered on a held device"
            # The operator, 2026-11-11: "the run's text on a SECOND line under the title;
            # only 'Open the run' on the right"; each fact once on the screen.
            at = html.index('<summary class="att-line">')
            line = html[at:html.index("</summary>", at)]
            assert line.index('class="att-what"') < line.index('class="att-running"') \
                < line.index('class="att-primary"'), "under the title, before the right side"
            assert re.search(r'<span class="att-running" role="status" data-held="r2"[^>]*>'
                             r'Deploy running since <time[^>]*>[^<]+</time>, by '
                             rf"{re.escape(SHOWN)}</span>", line)
            right = line[line.index('class="att-primary"'):].split(">", 1)[1]
            assert re.sub(r"<[^>]+>", "", right).strip() == "Open the run", \
                "the right side holds Open the run alone"
            assert html.count("running since") == 1 and html.count('data-held="r2"') == 1, \
                "the run is said once on the row"
            assert html.count(f'href="/v2/device/r2?list={NET}">Open the run</a>') == 2, \
                "on the line, and under What to do"
            assert "Offered again when the run ends." in html
        rows = self.lost()
        html = attention(rows)
        assert "held" not in rows[0] and offer in html and "data-held" not in html

    def test_the_list_s_own_route_marks_the_rows_it_draws(self, world, monkeypatch):
        """Through the list's route (`v2.attention_list`): the rows the background holds
        (C3166), marked for this request from the holds as they are now."""
        from modules.nsot import device_ops
        monkeypatch.setattr("modules.attention_store.read", lambda network=None: {
            "rows": self.lost(), "sources": [], "badge": {"n": 1}})
        with device_ops.hold(NET, "r2", "rotate", WHO):
            html = world.get("/v2/attention", headers=HX).get_data(as_text=True)
            assert html.count('data-held="r2"') == 1 and "Rotate credential running since" in html
            assert "Re-subscribe r2's telemetry (101)…</a>" not in html
            assert device_ops.holder(NET, "r2")["actor"] == WHO, "the hold it was read from"
        html = world.get("/v2/attention", headers=HX).get_data(as_text=True)
        assert "data-held" not in html and "Re-subscribe r2's telemetry (101)…</a>" in html

    def test_a_row_marked_before_is_read_again_never_kept(self, world):
        from modules import in_flight
        rows = self.lost()
        rows[0]["held"] = {"device": "r2", "name": "Deploy", "since": "", "by": "x",
                           "words": "stale", "list": NET}
        in_flight.mark_held(rows, TEST_PERSON)
        assert "held" not in rows[0], "nothing holds r2 now"

    def test_one_read_of_the_holds_per_network_whatever_the_rows(self, world, monkeypatch):
        from modules import in_flight
        from modules.nsot import device_ops
        asked = []
        real = device_ops.held
        monkeypatch.setattr(device_ops, "held", lambda n: (asked.append(n), real(n))[1])
        monkeypatch.setattr(device_ops, "holder", lambda n, d: pytest.fail("a probe per row"))
        rows = [dict(r, id=f"row-{i}") for i in range(90) for r in self.lost()]
        in_flight.mark_held(rows, TEST_PERSON)
        assert asked == [NET], "work counted: one read for 90 rows"

    def test_the_list_listens_for_a_hold_s_start_and_its_end(self, world):
        page = world.get("/v2/").get_data(as_text=True)
        trigger = re.search(r'id="attention"[^>]*hx-trigger="([^"]+)"', page, re.S).group(1)
        assert "nmas:device_holds from:body" in trigger and "nmas:in_progress from:body" in trigger
        # C3166: every key that moves a row reaches the background store, never the page; the
        # list hears the store's own announcement, made when what it draws moved.
        assert "nmas:attention from:body" in trigger, "and the store's announcement"
        assert "nmas:drift from:body" not in trigger, "a source's key is the store's, not the page's"
        from modules import attention, in_flight, invalidation
        assert set(in_flight.HELD_KEYS) <= set(invalidation.VOCABULARY)
        assert not set(in_flight.HELD_KEYS) & set(attention.ATTENTION_KEYS), \
            "the sources' own keys are not widened: only the page's trigger is"


class TestARefreshMidRun:
    def test_the_card_opened_again_draws_the_run_never_a_fresh_offer(self, world):
        """The operator's refresh: the row's card is asked for with no run named while the
        run goes on."""
        from modules.nsot import capture_job, privileged
        src, entered, gate = Src(), threading.Event(), threading.Event()
        waited = src.sleep

        def held(seconds):
            entered.set()
            assert gate.wait(30), "the test never let the run go on"
            waited(seconds)
        src.sleep = held
        world.state["src"] = src
        _r, html = card(world, subs="101")
        try:
            assert press(world, html, subs=("101",)).status_code == 200
            assert entered.wait(30), "the run never reached its wait"
            _r, again = card(world, subs="101")
            assert "Re-subscribing on r2." in again and 'aria-busy="true"' in again
            assert "Afterwards:" not in again and "resubscribe/confirm" not in again
            run = privileged.runs(NET)["runs"][0]["id"]
            assert f"run={run}" in again, "it waits on THAT run's end"
            # And the row's own action is the run, with its name.
            rows = _rows(_instance("r2", "NMAS telemetry stream lost: r2 subscription 101", 1))
            rows[0]["networks"] = {"r2": [NET]}
            listed = attention(rows)
            assert "Re-subscribe telemetry running since" in listed and ", by you</span>" in listed
        finally:
            gate.set()
        assert capture_job.wait(world.state["jobs"][-1], 30)
        _r, after = card(world, subs="101")
        assert "The last run," in after and "resubscribe/confirm" in after, \
            "ended: its outcome leads, and the offer is back"

    def test_held_by_another_operation_its_buttons_are_not_offered(self, world):
        from modules.nsot import device_ops
        with device_ops.hold(NET, "r2", "deploy", WHO):
            started = device_ops.holder(NET, "r2")["started"]
            _r, html = card(world, subs="101")
            assert "resubscribe/confirm" not in html, "no confirm on a held device"
            assert f'title="Deploy running since {clock_of(started)}, by {SHOWN}"' in html
            assert "Not offered while r2 is held: Deploy running since" in html
            assert f", by {SHOWN}. One operation per device at a time." in html
            assert f'href="/v2/device/r2?list={NET}">Open the run</a>' in html
            assert device_ops.busy_text(NET, "r2"), "the hold the confirm would be refused by"
        _r, html = card(world, subs="101")
        assert "resubscribe/confirm" in html and "data-held" not in html
