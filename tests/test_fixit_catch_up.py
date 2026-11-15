"""Turning "Start AI troubleshooting automatically when Mercury's fix fails" on catches up on the
person's choice (C3732; the operator, 2026-11-15: "when the switch is turned on, it starts on
every open incident whose fix failed or that has no fix, within the caps. Turning it on shows
the list first ("starts on these N open incidents, about $X"), each tickable, and records what
was chosen. After that, every new failure starts by itself"), and a hold a person resolves is
no fix Mercury can run alone (the operator, 2026-11-15: "count held incidents (e.g. r4's
guard-4 hold) as 'no fix Mercury can run alone', so they're on the switch's list").

Through tests/test_fixit_troubleshoot.py's world (the real app, the real gateway with only the
provider replaced, a job run in the request's thread), with incidents on seven devices opened
by the incidents store's own writer and their decisions and acts kept by the step log's own
writer. No device, no network, no live AI call.

Each test holds one purpose:
- the list is R1's own reader's (`auto.pending`, read by the automatic pass too): a no-code-fix,
  a can't-fix, a guard-4 hold and a failed fix listed; a waiting hold, a dry run's would-heal, a
  closed incident, one already started and one a cap stopped (its key taken) never;
- the guards a person resolves are the ones held with no time to check again;
- Turn on… draws each listed incident ticked with its device, title, why and estimate, and the
  total; none qualifying says so and turns on as before;
- the ticks are recorded with the turn-on, and only the ticked start, once each;
- the automatic pass never starts a ticked or an unticked one again for that failure;
- a cap that would be passed starts nothing and the incident's card names it;
- the investigation's trigger is the person who ticked, and its card says who started it;
- a new hold with the switch on starts once by itself;
- the AI is told the hold and its guard;
- in a real browser, the ticks change the total.
"""
import json
from html import unescape

import pytest

from modules.fixit import auto as A
from modules.fixit import incident as F
from modules.fixit import section as S
from tests.conftest import TEST_PERSON
from tests.test_fixit_auto import NOW, decide, iso, policy, run, turn_on  # noqa: F401
from tests.test_fixit_section_v2 import DETECTED, NET, plant
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_fixit_troubleshoot import ai  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import DEV
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

BASE = "/v2/settings/installation/ai/background"
#: The devices the incidents are on, each known to the inventory by its own NetBox id.
DEVICES = ("r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10")
#: Guard 4's hold, in its own words (`heal.guards.g4_golden`).
G4 = {"guard": 4, "name": "golden departs from intent",
      "words": ("heal off for this device: its golden departs from its intent (departs), so "
                "there is no approved state to heal to; a person resolves it first")}


@pytest.fixture
def world(ai, monkeypatch):  # noqa: F811
    """`ai` with r3 to r9 in the inventory beside r2, the background switches' clock at the
    test's moment, and self-healing's policy stood in (`policy`)."""
    rows = [dict(DEV, _netbox_id=7)] + [dict(DEV, hostname=d, ip=f"192.0.2.{20 + n}",
                                             _netbox_id=20 + n) for n, d in enumerate(DEVICES)]
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: list(rows))
    monkeypatch.setattr("modules.ai.background._now", lambda: NOW)
    return ai


def opened(device: str, at: float = DETECTED) -> str:
    """An incident on *device*, opened by the store's own writer from one alert (no stream)."""
    from modules.heal import incidents
    got = incidents.sight(NET, device, {"kind": "alert", "key": f"alert:cpu-{device}",
                                        "epoch": at, "at": "", "rule": f"CPU high: {device}",
                                        "words": f"the alert fired on {device}"}, now=at)
    return got["incident"]


def acted(iid: str, device: str, outcome: str, at: float) -> None:
    """A heal act on *iid* that ended *outcome*, through the step log's own writer."""
    from modules.heal import steplog
    steplog.append(NET, {"row": "act", "decision": "hd-00000000ac7d", "incident": iid,
                         "device": device, "outcome": outcome, "kind": "missing_line"}, at)


def inc_of(iid: str):
    from modules import incident_page
    return S.incident_of(NET, incident_page.resolve(NET, iid))["incident"]


def planted():
    """Every kind: ``{name: incident id}``."""
    from modules.heal import incidents
    got = {"stream": plant(),                                   # r2: a lost stream, no code fix
           "cant_fix": opened("r3"), "held4": opened("r4"), "waits": opened("r5"),
           "dry": opened("r6"), "failed": opened("r7"), "closed": opened("r8"),
           "started": opened("r9"), "capped": opened("r10")}
    decide(got["cant_fix"], 1, "cant_fix", DETECTED + 10)
    decide(got["held4"], 2, "held", DETECTED + 11, G4)
    decide(got["waits"], 3, "held", DETECTED + 12,
           {"guard": 7, "name": "a person working", "words": "a person appears to be working"})
    decide(got["dry"], 4, "would_heal", DETECTED + 13)
    acted(got["failed"], "r7", "rolled_back", DETECTED + 14)
    decide(got["closed"], 5, "cant_fix", DETECTED + 15)
    incidents.close(NET, got["closed"], "cleared", now=DETECTED + 16)
    decide(got["started"], 6, "cant_fix", DETECTED + 17)
    F.claim_start(inc_of(got["started"]), f"decision:{got['started']}", trigger="auto",
                  state="started", now=DETECTED + 18)
    # Taken by an automatic start that a cap stopped: no AI was asked, and its key is taken.
    decide(got["capped"], 7, "cant_fix", DETECTED + 19)
    F.claim_start(inc_of(got["capped"]), f"decision:{got['capped']}", trigger="auto",
                  state="capped", which="incident", words="the cap", now=DETECTED + 20)
    return got


LISTED = ("stream", "cant_fix", "held4", "failed")


def get(w, path):
    r = w.client.get(path)
    return r, unescape(r.get_data(as_text=True))


def form_of(w):
    r, html = get(w, f"{BASE}/{NET}/fixit_auto/on")
    assert r.status_code == 200, html
    import re
    shown = re.search(r'name="shown" value="([0-9a-f]{64})"', html).group(1)
    each = re.search(r'name="catch_up_each" value="([0-9.]+)"', html)
    return html, shown, each.group(1) if each else ""


def post(w, shown, each, listed, ticked, day="1.50", month="10.00"):
    data = {"shown": shown, "day_cap_usd": day, "month_cap_usd": month, "accept": "on",
            "listed": list(listed), "start": list(ticked), "catch_up_each": each}
    r = w.client.post(f"{BASE}/{NET}/fixit_auto/on", data=data, headers={"HX-Request": "true"})
    return r, unescape(r.get_data(as_text=True))


def record(w):
    from modules import installation_settings as I
    return [x for x in I.changes()["rows"] if x.get("kind") == "ai_background_on"]


@pytest.fixture
def counted(monkeypatch):
    """Each catch-up investigation started, counted by its incident and key (the job runs in
    the request's thread, `web`), asking no model."""
    from modules import heal_notice
    seen = []
    monkeypatch.setattr(heal_notice, "catch_up_investigation",
                        lambda network, iid, key, **kw: seen.append((iid, key, kw)) or {},
                        raising=False)
    return seen


class TestTheList:
    def test_it_is_r1s_own_reader_and_lists_exactly_what_r1_would_start_on(self, world,
                                                                          monkeypatch):
        got = planted()
        real, calls = A.pending, []

        def spy(network):
            calls.append(network)
            return real(network)
        monkeypatch.setattr(A, "pending", spy)
        items = A.catch_up(NET, now=NOW)["items"]
        assert {i["id"] for i in items} == {got[k] for k in LISTED}, items
        why = {i["id"]: (i["why_kind"], i["why"]) for i in items}
        assert why[got["stream"]][0] == why[got["cant_fix"]][0] == "no_fix"
        assert why[got["failed"]] == ("failed", "Mercury's fix was rolled back")
        assert why[got["held4"]][0] == "held"
        assert why[got["held4"]][1].startswith("held by guard 4: heal off for this device")
        assert calls == [NET]
        # The automatic pass reads the same reader (one definition of a failure).
        turn_on(NOW - 10)
        run(NOW)
        assert calls == [NET, NET]

    def test_the_guards_a_person_resolves_are_those_held_with_no_time_to_check_again(self):
        from modules.heal import guards as G
        g4 = G.g4_golden({"state": "departs", "words": "departs", "lines": []})
        assert g4["outcome"] == "held" and g4["until"] is None and 4 in A.HELD_FOR_A_PERSON
        inc = {"device": "r5", "triggers": [{"kind": "config_change", "epoch": NOW - 10,
                                             "person": {"words": "op"}}]}
        g7 = G.g7_person(inc, NOW, changes=1, minutes=30)
        assert g7["outcome"] == "held" and g7["until"] and 7 not in A.HELD_FOR_A_PERSON


class TestTheForm:
    def test_what_is_drawn_ticked_with_its_estimate_is_what_turning_on_starts(self, world,
                                                                              counted):
        from modules.ai import fixit_troubleshoot as AIT
        from modules.money import usd
        got = planted()
        html, shown, each = form_of(world)
        est = AIT.estimate()["usd"]
        assert float(each) == pytest.approx(est, abs=1e-6)
        assert f"Starts on these 4 open incidents, about {usd(est * 4)}" in html
        for k in LISTED:
            assert f'name="start" value="{got[k]}" checked' in html, k
            assert f'name="listed" value="{got[k]}"' in html, k
        for k in ("waits", "dry", "closed", "started", "capped"):
            assert got[k] not in html, k
        assert "held by guard 4: heal off for this device" in html
        assert "r4" in html and f"about {usd(est)}" in html
        # Pressed with every box as drawn (all ticked): each drawn one starts, once.
        r, out = post(world, shown, each, [got[k] for k in LISTED], [got[k] for k in LISTED])
        assert r.status_code == 200, out
        assert sorted(i for i, _k, _kw in counted) == sorted(got[k] for k in LISTED)
        (rec,) = record(world)
        assert rec["catch_up"]["usd_total"] == pytest.approx(est * 4, abs=1e-6)

    def test_none_qualifying_says_so_and_turns_on_as_before(self, world, counted):
        html, shown, each = form_of(world)
        assert "No open incident to start on." in html and 'name="start"' not in html
        r, out = post(world, shown, each, (), ())
        assert r.status_code == 200 and "fixit_auto is on for" in out, out
        (rec,) = record(world)
        assert rec["catch_up"] == {"ticked": [], "unticked": [], "usd_each": 0.0,
                                   "usd_total": 0.0}
        assert counted == []

    def test_another_feature_lists_and_starts_nothing(self, world, counted):
        import re
        planted()
        r, html = get(world, f"{BASE}/{NET}/sdn_classify/on")
        assert r.status_code == 200 and "ai-catchup" not in html
        shown = re.search(r'name="shown" value="([0-9a-f]{64})"', html).group(1)
        r = world.client.post(f"{BASE}/{NET}/sdn_classify/on", headers={"HX-Request": "true"},
                              data={"shown": shown, "day_cap_usd": "0.50",
                                    "month_cap_usd": "10.00", "accept": "on"})
        assert r.status_code == 200, r.get_data(as_text=True)
        (rec,) = record(world)
        assert "catch_up" not in rec and counted == []


class TestTheChoice:
    def test_the_ticks_are_recorded_and_only_the_ticked_start_once(self, world, counted):
        got = planted()
        html, shown, each = form_of(world)
        listed = [got[k] for k in LISTED]
        ticked = [got["stream"], got["held4"]]
        r, out = post(world, shown, each, listed, ticked)
        assert r.status_code == 200, out
        (rec,) = record(world)
        assert rec["catch_up"]["ticked"] == ticked
        assert rec["catch_up"]["unticked"] == [got["cant_fix"], got["failed"]]
        assert rec["catch_up"]["usd_total"] == pytest.approx(float(each) * 2, abs=1e-6)
        assert rec["actor"] == TEST_PERSON
        assert [(i, k) for i, k, _kw in counted] == [(got["stream"], f"decision:{got['stream']}"),
                                                    (got["held4"], f"held:{got['held4']}")]
        assert all(kw == {"actor": TEST_PERSON, "verified": "access"} for *_x, kw in counted)
        (line,) = F.starts(inc_of(got["held4"]))["starts"]
        assert (line["start"], line["trigger"], line["state"], line["words"], line["by"]) == (
            f"held:{got['held4']}", "person", "started", A.CATCH_UP_WORDS, TEST_PERSON)
        assert F.starts(inc_of(got["cant_fix"]))["starts"] == [], "unticked: nothing taken"
        assert "AI troubleshooting started on 2 open incidents" in out
        assert "2 open incidents left unticked keep Start AI troubleshooting" in out
        # Turned on again (its renewal), neither ticked one is listed again.
        _html, shown, each = form_of(world)
        assert got["stream"] not in _html and got["held4"] not in _html
        assert got["cant_fix"] in _html

    def test_the_automatic_pass_never_starts_one_again_for_that_failure(self, world, counted):
        got = planted()
        _html, shown, each = form_of(world)
        post(world, shown, each, [got[k] for k in LISTED], [got["stream"]])
        # Its investigation answered (a proposal line), so nothing is in flight.
        F.record_proposal(inc_of(got["stream"]), "mercury", words="nothing", now=NOW + 1)
        out, started = run(NOW + 60)
        assert out["started"] == [] and started == [], out
        assert len(counted) == 1

    def test_a_ticked_one_not_listed_is_refused_and_nothing_changes(self, world, counted):
        got = planted()
        _html, shown, each = form_of(world)
        r, out = post(world, shown, each, [got["stream"]], [got["stream"], got["waits"]])
        assert r.status_code == 409 and "is not on the list drawn" in out, out
        assert record(world) == [] and counted == []

    def test_an_estimate_the_server_did_not_compute_is_refused(self, world, counted):
        # The second review of the verify-speed gate, 2026-11-15: the estimate recorded with
        # the turn-on is the server's own, never what the browser sent.
        got = planted()
        _html, shown, each = form_of(world)
        r, out = post(world, shown, "0.000001", [got["stream"]], [got["stream"]])
        assert r.status_code == 409 and "the estimate drawn was 0.000001" in out, out
        assert record(world) == [] and counted == []
        r, out = post(world, shown, each, [got["stream"]], [got["stream"]])
        assert r.status_code == 200, out


class TestTheCaps:
    def test_past_the_incidents_cap_nothing_starts_and_its_card_says_which(self, world,
                                                                           counted):
        from modules import incident_page
        from modules.settings_schema import write_settings
        got = planted()
        assert write_settings({"ai_cap_usd_per_incident": 0.0001})["ok"]
        _html, shown, each = form_of(world)
        assert "its incident's AI cap would be passed" in _html
        r, out = post(world, shown, each, [got[k] for k in LISTED], [got["cant_fix"]])
        assert r.status_code == 200 and "Not started, a cap would be passed" in out, out
        assert counted == [] and world.sent == []
        (line,) = F.starts(inc_of(got["cant_fix"]))["starts"]
        assert (line["state"], line["which"], line["trigger"]) == ("capped", "incident",
                                                                   "person")
        x = S.view(NET, incident_page.resolve(NET, got["cant_fix"]), now=NOW + 1)
        assert x["state"] == "capped" and x["cap"]["which"] == "incident"
        assert "this incident's AI cap would be passed" in x["status"]

    def test_past_the_features_typed_day_cap_the_start_is_refused_naming_it(self, world,
                                                                            counted):
        # Premise corrected (the operator, C3745, 2026-11-15: "Catch-up starts count against
        # every cap ... The builder's test that expects a start at a $0.01 feature cap is
        # wrong"): at a $0.01 feature day cap the one ticked is refused, naming that cap.
        got = planted()
        _html, shown, each = form_of(world)
        r, out = post(world, shown, each, [got[k] for k in LISTED], [got["stream"]],
                      day="0.01", month="0.10")
        assert r.status_code == 200 and "Not started, a cap would be passed" in out, out
        assert counted == [] and world.sent == []
        (line,) = F.starts(inc_of(got["stream"]))["starts"]
        assert (line["state"], line["which"], line["trigger"]) == ("capped", "day", "person")
        assert "fixit_auto's spend on" in line["words"] and "day cap $0.0100" in line["words"]

    def test_three_ticked_room_for_two_under_the_features_day_cap(self, world, counted):
        from modules.ai import fixit_troubleshoot as AIT
        got = planted()
        _html, shown, each = form_of(world)
        three = [got["stream"], got["cant_fix"], got["held4"]]
        day = f"{AIT.worst_usd() * 2 + 0.01:.2f}"
        r, out = post(world, shown, each, [got[k] for k in LISTED], three, day=day)
        assert r.status_code == 200, out
        assert [i for i, _k, _kw in counted] == three[:2], "2 start, in tick order"
        (line,) = F.starts(inc_of(got["held4"]))["starts"]
        assert (line["state"], line["which"]) == ("capped", "day")
        assert (f"day cap ${float(day):.4f}" in line["words"]
                and "reserved by its 2 call(s) in flight" in line["words"]), line["words"]

    @pytest.mark.parametrize("room, ticked, starts", [(2, 3, 2), (1, 2, 1)])
    def test_only_the_overall_day_cap_binds(self, world, counted, room, ticked, starts):
        """Today's spend elsewhere leaves room for *room* under the installation's $1.50 day
        cap, with the feature's own day cap at $1.50 holding five: the later ones are refused
        at the day cap, naming today's spend and the starts ahead of them."""
        from modules.ai import calls
        from modules.ai import fixit_troubleshoot as AIT
        got = planted()
        spent = round(1.50 - AIT.worst_usd() * room - 0.001, 4)
        assert calls.record({"id": calls.new_id(), "feature": "explain", "actor": TEST_PERSON,
                             "model": "m", "cost_usd": spent, "tokens": {"in": 1, "out": 1},
                             "trigger": {"kind": "person", "by": TEST_PERSON}})["recorded"]
        _html, shown, each = form_of(world)
        assert f"{room} under the day cap" in _html, "the list says the room first"
        picked = [got[k] for k in LISTED][:ticked]
        r, out = post(world, shown, each, [got[k] for k in LISTED], picked)
        assert r.status_code == 200, out
        assert [i for i, _k, _kw in counted] == picked[:starts]
        for iid in picked[starts:]:
            (line,) = F.starts(inc_of(iid))["starts"]
            assert (line["state"], line["which"]) == ("capped", "day")
            assert f"today's AI spend ${spent:.2f}" in line["words"], line["words"]
            assert "would pass the day cap of $1.50" in line["words"]
            assert "held by the investigations started with it" in line["words"]


class TestWhatFits:
    """The list says, before the press, how many fit under each cap (C3745), with the same
    arithmetic the start refuses by, in Python and in the browser's own script."""

    def test_the_arithmetic(self):
        from modules.ai import settings_view as V
        rooms = [("day", 1.0), ("feature_day", 0.51), ("feature_month", 10.0)]
        fit = V.catch_up_fit([True, True, True], 0.2502, rooms)
        assert (fit["start"], fit["refused_cap"], fit["binding"]) == (2, 1, "feature_day")
        assert fit["slots"] == {"day": 3, "feature_day": 2, "feature_month": 39}
        fit = V.catch_up_fit([True, False, True], 0.2502, [("day", None),
                                                            ("feature_day", 5.0),
                                                            ("feature_month", 5.0)])
        assert (fit["start"], fit["refused_incident"], fit["refused_cap"]) == (2, 1, 0)
        assert V.catch_up_fit([True], 0.25, [("feature_day", "unknown")])["unknown"]


class TestThePerson:
    def test_the_investigation_asks_as_the_person_who_ticked(self, world):
        from modules.ai import calls
        got = {"stream": plant()}
        _html, shown, each = form_of(world)
        post(world, shown, each, [got["stream"]], [got["stream"]])
        assert world.sent, "the ticked one's investigation asked the provider"
        rows = [r for r in calls.read()["rows"] if r.get("feature") == "fixit_troubleshoot"]
        assert rows and all(r["trigger"]["kind"] == "person" for r in rows), rows
        assert all(r["trigger"]["by"] == TEST_PERSON for r in rows)

    def test_its_card_says_it_was_started_at_turn_on_by_the_person(self, world):
        from modules import display_names, incident_page
        iid = plant()
        F.claim_start(inc_of(iid), f"decision:{iid}", trigger="person", state="started",
                      words=A.CATCH_UP_WORDS, by=TEST_PERSON, verified="access", now=NOW)
        x = S.view(NET, incident_page.resolve(NET, iid), now=NOW + 5)
        assert x["state"] == "investigating"
        assert (f"started at turn-on by {display_names.people(TEST_PERSON)}, 5 s ago"
                in x["status"]), x["status"]


class TestTheHold:
    def test_a_new_hold_with_the_switch_on_starts_once_by_itself(self, world, policy):  # noqa: F811
        turn_on(DETECTED - 600)
        iid = opened("r4")
        decide(iid, 9, "held", DETECTED + 30, G4)
        out, started = run()
        assert out["started"] == [f"held:{iid}"] and len(started) == 1
        assert run(NOW + 30)[0]["started"] == [], "once"

    def test_a_dry_runs_would_heal_and_a_waiting_hold_never_start(self, world, policy):  # noqa: F811
        turn_on(DETECTED - 600)
        dry, waits = opened("r6"), opened("r5")
        decide(dry, 10, "would_heal", DETECTED + 30)
        decide(waits, 11, "held", DETECTED + 31, {"guard": 3, "name": "planned work",
                                                  "words": "a planned window holds it"})
        out, started = run()
        assert out["started"] == [] and started == []

    def test_the_ai_is_told_the_hold_and_its_guard(self, world):
        from modules import incident_page
        from modules.ai import fixit_troubleshoot as AIT
        iid = opened("r4")
        decide(iid, 12, "held", DETECTED + 30, G4)
        found = incident_page.resolve(NET, iid)
        prep = AIT.request(NET, found, inc_of(iid), now=NOW)
        said = prep["data"]["the_incident"]
        assert "self-healing holds it by guard 4 (golden departs from intent)" in said, said
        assert "a person resolves it" in said


class TestInABrowser:
    def test_unticking_changes_the_total(self, world):
        from tests import browser
        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the tests above still run")
        import app as nmas
        from modules.money import usd
        got = planted()
        _html, _shown, each = form_of(world)
        each = float(each)
        with browser.Served(nmas.app) as srv, browser.Browser() as b:
            try:
                # Settings › AI, then Turn on… on the feature's row, as a person opens it.
                b.go(srv.url(f"/v2/settings/installation?tab=ai&network={NET}"))
                on = f'#bg-fixit_auto a[href$="/{NET}/fixit_auto/on"]'
                b.wait_for("return !!window.Alpine && !!window.htmx && "
                           "!!document.querySelector(arguments[0])", 20, on)
                b.click(on)
                b.wait_for("return !!document.querySelector('.ai-catchup-pick strong')", 20)
                lead = "return document.querySelector('.ai-catchup-pick strong').innerText"
                assert b.js(lead) == f"Starts on these 4 open incidents, about {usd(each * 4)}"
                # What fits follows the caps as they are typed (C3745), key by key.
                fit = "return document.querySelector('.ai-catchup-fit strong').innerText"
                for name, typed in (("month_cap_usd", "10"), ("day_cap_usd", "0.60")):
                    b.js("document.querySelector('input[name=' + arguments[0] + ']').value = '';"
                         " return 1", name)
                    b.type(f"input[name={name}]", typed)
                b.wait_for(fit + ".indexOf('2 of the 4') === 0", 10)
                assert b.js(fit) == ("2 of the 4 ticked fit under the caps; the later 2 would "
                                     "pass this feature's day cap: refused before anything "
                                     "starts, each page naming the cap.")
                b.js("document.querySelector('input[name=day_cap_usd]').value = '';"
                     " return 1")
                b.type("input[name=day_cap_usd]", "1.50")
                b.wait_for(fit + ".indexOf('All 4') === 0", 10)
                assert b.js(fit) == "All 4 ticked fit under every cap."
                b.click(f'input[name="start"][value="{got["held4"]}"]')
                b.wait_for(lead + ".indexOf('these 3') >= 0", 10)
                assert b.js(lead) == f"Starts on these 3 open incidents, about {usd(each * 3)}"
                for k in ("stream", "cant_fix", "failed"):
                    b.click(f'input[name="start"][value="{got[k]}"]')
                b.wait_for(lead + ".indexOf('none') >= 0", 10)
                assert b.js(lead).startswith("Starts on none of these open incidents")
                b.click(f'input[name="start"][value="{got["failed"]}"]')
                b.wait_for(lead + ".indexOf('this open') >= 0", 10)
                assert b.js(lead) == f"Starts on this open incident, about {usd(each)}"
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()


def test_the_words_are_the_browsers_own():
    """The component's words as the browser computes them (duktape), against the server's."""
    import dukpy
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "static", "js", "nmas_apply.js"), encoding="utf-8").read()
    js = ("var window = {};\n" + src
          + "\n[window.NMAS_APPLY.catchUpWords(4, 0.5), window.NMAS_APPLY.catchUpWords(1, "
            "0.0011), window.NMAS_APPLY.catchUpWords(0, 0), window.NMAS_APPLY.usd(1234.5)]")
    assert json.loads(json.dumps(dukpy.evaljs(js))) == [
        "Starts on these 4 open incidents, about $0.50",
        "Starts on this open incident, about $0.0011",
        "Starts on none of these open incidents: each keeps Start AI troubleshooting",
        "$1,234.50"]




#: Cases the list's words are drawn for, in Python and in the browser's script alike (C3745):
#: ``(oks, worst, rooms)``, a room None for no cap and "unknown" when not typed.
FIT_CASES = [
    ([True, True, True], 0.2502, [["day", 1.0], ["feature_day", 0.51], ["feature_month", 10.0]]),
    ([True, False, True], 0.2502, [["day", None], ["feature_day", 5.0], ["feature_month", 5.0]]),
    ([True, True], 0.2502, [["day", 0.3], ["feature_day", 5.0], ["feature_month", 5.0]]),
    ([True], 0.2502, [["day", 1.0], ["feature_day", 1.0], ["feature_month", 1.0]]),
    ([], 0.2502, [["day", 1.0], ["feature_day", 1.0], ["feature_month", 1.0]]),
    ([True], 0.2502, [["day", 1.0], ["feature_day", "unknown"], ["feature_month", 1.0]]),
]


def test_what_fits_is_said_alike_by_the_server_and_the_browsers_script():
    import dukpy
    import os
    from modules.ai import settings_view as V
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "static", "js", "nmas_apply.js"), encoding="utf-8").read()
    for oks, worst, rooms in FIT_CASES:
        py = [(c, r) for c, r in rooms]
        fit = V.catch_up_fit(oks, worst, py)
        want = [V.fit_words(fit, len(oks)), V.room_words(fit, py, worst)]
        js_rooms = json.dumps([[c, "NaN" if r == "unknown" else r] for c, r in rooms]).replace(
            '"NaN"', "NaN")
        got = dukpy.evaljs(
            "var window = {};\n" + src + "\nvar A = window.NMAS_APPLY, rooms = " + js_rooms
            + ", fit = A.catchUpFit(" + json.dumps(oks) + ", " + str(worst) + ", rooms);"
            + " [A.catchUpFitWords(fit, " + str(len(oks)) + "), A.catchUpRoomWords(fit, rooms, "
            + str(worst) + ")]")
        assert list(got) == want, (oks, rooms)
