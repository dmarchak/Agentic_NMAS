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
    test's moment, and self-healing's policy stood in (`policy`); the installation's day cap
    `DAY_CAP`."""
    from modules.settings_schema import write_settings
    rows = [dict(DEV, _netbox_id=7)] + [dict(DEV, hostname=d, ip=f"192.0.2.{20 + n}",
                                             _netbox_id=20 + n) for n, d in enumerate(DEVICES)]
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: list(rows))
    monkeypatch.setattr("modules.ai.background._now", lambda: NOW)
    assert write_settings({"ai_cap_usd_per_day": DAY_CAP})["ok"]
    return ai


#: The installation's and the feature's day cap in this world: five investigations fit under it
#: at their worst. Premise corrected (C3797): an investigation's worst case is four calls since
#: the loop is iterative ($0.5004), so five need $2.502, past the $1.50 they fitted under at two.
DAY_CAP = 3.00


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
    # An automatic start that a cap stopped: no AI was asked. Premise corrected (C3872,
    # 7d54cf24, the operator, 2026-11-16: "a refused start spends no key"): its key is not
    # taken, so it is listed again, where it was left out.
    decide(got["capped"], 7, "cant_fix", DETECTED + 19)
    F.claim_start(inc_of(got["capped"]), f"decision:{got['capped']}", trigger="auto",
                  state="capped", which="incident", words="the cap", now=DETECTED + 20)
    return got


#: What R1 would start on (C3872: the capped start's refusal spent no key, so it is among them).
LISTED = ("stream", "cant_fix", "held4", "failed", "capped")
#: The AI switch's answer while its catch-up starts (`troubleshoot_control.starting_words`).
STARTING = "Starting the AI on {n} incidents…"


def get(w, path):
    r = w.client.get(path)
    return r, unescape(r.get_data(as_text=True))


def form_of(w):
    """Gate 2 (C3769): the read-only list for audit (what Automatic would start, and why), the
    digest of the control strip's line (what its press is bound to) and one investigation's
    estimate: ``(audit html, line digest, each)``."""
    import re

    from modules.ai import fixit_troubleshoot as AIT
    r, html = get(w, f"{BASE}/{NET}/fixit_auto/on")
    assert r.status_code == 200, html
    strip = unescape(w.client.get(f"/v2/control/strip?list={NET}").get_data(as_text=True))
    shown = re.search(r'name="line_digest" value="([0-9a-f]*)"', strip).group(1)
    return html, shown, f"{AIT.estimate()['usd']:.6f}"


def post(w, shown, each, day=f"{DAY_CAP:.2f}", month="10.00", incident=None):
    """Turn Automatic on the one way (Gate 2): the network's limits set with the estimate
    acknowledged (Settings › AI's card), then the control strip's switch pressed, bound to the
    line it drew (*shown*). Every listed incident starts (no ticks). *each* is unused by the
    server, kept so the callers read as before."""
    import re

    from modules.fixit import policy as P
    page = unescape(w.client.get(f"/v2/settings/installation?tab=ai&network={NET}")
                    .get_data(as_text=True))
    est = re.search(r'class="ai-ts-limits".*?name="estimate_digest" value="([0-9a-f]{64})"',
                    page, re.S).group(1)
    inc = incident if incident is not None else f"{P.cap_usd()['usd']:.6f}"
    r = w.client.post(f"/v2/settings/installation/ai/troubleshoot/{NET}/limits",
                      headers={"HX-Request": "true"},
                      data={"estimate_digest": est, "incident_cap_usd": inc, "day_cap_usd": day,
                            "month_cap_usd": month, "accept": "on"})
    assert r.status_code == 200, r.get_data(as_text=True)
    r = w.client.post(f"/v2/settings/installation/ai/troubleshoot/{NET}/level?answer=strip",
                      headers={"HX-Request": "true"},
                      data={"level": "automatic", "line_digest": shown})
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
        assert f"Starts on these 5 open incidents, about {usd(est * 5)}" in html
        for k in LISTED:
            assert f'data-incident="{got[k]}"' in html, k
        for k in ("waits", "dry", "closed", "started"):
            assert got[k] not in html, k
        assert "held by guard 4: heal off for this device" in html
        assert "r4" in html and f"about {usd(est)}" in html
        # Turned on (the strip's switch, Gate 2): each listed one starts, once.
        r, out = post(world, shown, each)
        assert r.status_code == 200, out
        assert sorted(i for i, _k, _kw in counted) == sorted(got[k] for k in LISTED)
        (rec,) = record(world)
        assert rec["catch_up"]["usd_total"] == pytest.approx(est * 5, abs=1e-6)

    def test_none_qualifying_says_so_and_turns_on_as_before(self, world, counted):
        html, shown, each = form_of(world)
        assert "No open incident to start on." in html and 'data-incident=' not in html
        r, out = post(world, shown, each)
        assert r.status_code == 200 and "Automatic is on" in out, out
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
        """Premise corrected (Gate 2, C3769; the operator, 2026-11-15: "All open eligible
        incidents start, within the caps ... no ticks"; the name predates it): every listed
        incident is recorded with the turn-on and starts once, in the person's name, each
        counting toward the feature (C3751) under its own planned reservation (C3752)."""
        got = planted()
        html, shown, each = form_of(world)
        listed = [got[k] for k in LISTED]
        r, out = post(world, shown, each)
        assert r.status_code == 200, out
        (rec,) = record(world)
        assert sorted(rec["catch_up"]["ticked"]) == sorted(listed)
        assert rec["catch_up"]["unticked"] == []
        assert rec["catch_up"]["usd_total"] == pytest.approx(float(each) * 5, abs=1e-6)
        assert rec["actor"] == TEST_PERSON
        assert sorted((i, k) for i, k, _kw in counted) == sorted(
            [(got["stream"], f"decision:{got['stream']}"),
             (got["cant_fix"], f"decision:{got['cant_fix']}"),
             (got["held4"], f"held:{got['held4']}"),
             (got["failed"], "act:hd-00000000ac7d"),
             (got["capped"], f"decision:{got['capped']}")])
        assert all({k: kw[k] for k in ("actor", "verified", "counts")} == {
            "actor": TEST_PERSON, "verified": "access", "counts": True}
            and str(kw.get("planned") or "").startswith("fixit-start-")
            for *_x, kw in counted), counted
        (line,) = F.starts(inc_of(got["held4"]))["starts"]
        assert (line["start"], line["trigger"], line["state"], line["words"], line["by"]) == (
            f"held:{got['held4']}", "person", "started", A.CATCH_UP_WORDS, TEST_PERSON)
        assert "started on 4 open incidents now" in out
        # Read again, none of them is listed again (each start took its failure's key).
        _html, shown, each = form_of(world)
        assert all(got[k] not in _html for k in LISTED)

    def test_the_automatic_pass_never_starts_one_again_for_that_failure(self, world, counted):
        got = planted()
        _html, shown, each = form_of(world)
        post(world, shown, each)
        # Their investigations answered (a proposal line each), so nothing is in flight.
        for k in LISTED:
            F.record_proposal(inc_of(got[k]), "mercury", words="nothing", now=NOW + 1)
        out, started = run(NOW + 60)
        assert out["started"] == [] and started == [], out
        assert len(counted) == 5

    def test_a_ticked_one_not_listed_is_refused_and_nothing_changes(self, world, counted):
        """Premise corrected (Gate 2, C3769: no ticks; the name predates the change): an
        incident that leaves the list between the line drawn and the press (here resolved) is
        not started, and nothing else changes: the press is refused by the line's digest,
        naming both, with nothing recorded and nothing started."""
        from modules.heal import incidents
        got = planted()
        _html, shown, each = form_of(world)
        incidents.close(NET, got["cant_fix"], "cleared", now=NOW)
        r, out = post(world, shown, each)
        assert r.status_code == 409 and "moved since the line was drawn" in out, out
        assert record(world) == [] and counted == []
        assert F.starts(inc_of(got["cant_fix"]))["starts"] == []

    def test_an_estimate_the_server_did_not_compute_is_refused(self, world, counted):
        """The second review of the verify-speed gate, 2026-11-15: what turning on records and
        starts is the server's own, never what the browser sent. Premise corrected (Gate 2,
        C3769; the name predates it): the press is bound to the line's digest, the open
        incidents and their estimate as drawn."""
        planted()
        _html, shown, each = form_of(world)
        r, out = post(world, "0" * 64, each)
        assert r.status_code == 409 and "moved since the line was drawn" in out, out
        assert record(world) == [] and counted == []
        r, out = post(world, shown, each)
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
        r, out = post(world, shown, each)
        assert r.status_code == 200 and "a cap would be passed" in out, out
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
        # wrong"): at a $0.01 day limit every listed one is refused, naming that cap. And
        # (Gate 2, C3769; the name predates it): the cap is the limit acknowledged on the
        # card, not one typed in the turn-on form.
        got = planted()
        _html, shown, each = form_of(world)
        r, out = post(world, shown, each, day="0.01", month="0.10")
        assert r.status_code == 200 and "a cap would be passed" in out, out
        assert counted == [] and world.sent == []
        (line,) = F.starts(inc_of(got["stream"]))["starts"]
        assert (line["state"], line["which"], line["trigger"]) == ("capped", "day", "person")
        assert "fixit_auto's spend on" in line["words"] and "day cap $0.0100" in line["words"]

    def test_three_ticked_room_for_two_under_the_features_day_cap(self, world, counted):
        """Premise corrected (Gate 2, C3769: no ticks; the name predates it): with room for two
        under the feature's day limit, the first two listed start, in the list's order, and the
        third is refused at that limit, naming the starts ahead of it."""
        from modules.ai import fixit_troubleshoot as AIT
        from modules import troubleshoot_control as T
        planted()
        _html, shown, each = form_of(world)
        order = T.catch_up_line(NET)["ids"]
        day = f"{AIT.worst_usd() * 2 + 0.01:.2f}"
        r, out = post(world, shown, each, day=day)
        assert r.status_code == 200, out
        assert [i for i, _k, _kw in counted] == order[:2], "2 start, in the list's order"
        (line,) = F.starts(inc_of(order[2]))["starts"]
        assert (line["state"], line["which"]) == ("capped", "day")
        assert (f"day cap ${float(day):.4f}" in line["words"]
                and "reserved by its 2 call(s) in flight" in line["words"]), line["words"]

    @pytest.mark.parametrize("room, ticked, starts", [(2, 3, 2), (1, 2, 1)])
    def test_only_the_overall_day_cap_binds(self, world, counted, room, ticked, starts):
        """Today's spend elsewhere leaves room for *room* under the installation's `DAY_CAP`
        day cap, with the feature's own day limit at it holding five: the later ones are refused
        at the day cap, naming today's spend and the starts ahead of them. Premise corrected
        (Gate 2, C3769: no ticks; the ids predate it): every listed incident is pressed, at
        least *ticked* of them, and *starts* (the room) start, the rest refused."""
        from modules.ai import calls
        from modules.ai import fixit_troubleshoot as AIT
        from modules import troubleshoot_control as T
        planted()
        spent = round(DAY_CAP - AIT.worst_usd() * room - 0.001, 4)
        assert calls.record({"id": calls.new_id(), "feature": "explain", "actor": TEST_PERSON,
                             "model": "m", "cost_usd": spent, "tokens": {"in": 1, "out": 1},
                             "trigger": {"kind": "person", "by": TEST_PERSON}})["recorded"]
        _html, shown, each = form_of(world)
        assert f"{room} under the day cap" in _html, "the list says the room first"
        order = T.catch_up_line(NET)["ids"]
        assert len(order) >= ticked > starts == room
        r, out = post(world, shown, each)
        assert r.status_code == 200, out
        assert [i for i, _k, _kw in counted] == order[:starts]
        for iid in order[starts:]:
            # The newest start line: the planted capped incident keeps its earlier refused
            # start too (C3872: a refused start spends no key, so it is pressed again).
            line = F.starts(inc_of(iid))["starts"][-1]
            assert (line["state"], line["which"]) == ("capped", "day")
            assert f"today's AI spend ${spent:.2f}" in line["words"], line["words"]
            assert f"would pass the day cap of ${DAY_CAP:.2f}" in line["words"]
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
        post(world, shown, each)
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
        # Its start as the instant itself, drawn in the viewer's zone (C3801), never "5 s ago".
        assert (f"started at turn-on by {display_names.people(TEST_PERSON)} at {iso(NOW)}"
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
    def test_unticking_changes_the_total(self, world, counted):
        """Premise corrected (Gate 2, C3769: no ticks; the name predates the change): in a real
        browser, Settings › AI's AI troubleshooting card's Automatic, pressed once the
        network's limits are acknowledged, turns Automatic on and starts every listed open
        incident, the total the list drew (the read-only list for audit has no Turn on)."""
        from tests import browser
        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the tests above still run")
        import app as nmas
        from modules import troubleshoot_control as troubleshoot
        from modules.ai import background
        got = planted()
        est = background.estimate(background._network(NET), A.FEATURE)
        troubleshoot.set_limits(NET, incident_usd=1.0, day_usd=DAY_CAP, month_usd=10.0,
                                shown=est["digest"], accepted=True, actor=TEST_PERSON,
                                verified="access")
        with browser.Served(nmas.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url(f"/v2/settings/installation?tab=ai&network={NET}"))
                on = '#ai-ts button[name="level"][value="automatic"]'
                b.wait_for("return !!window.Alpine && !!window.htmx && "
                           "!!document.querySelector(arguments[0])", 20, on)
                b.click(on)
                b.wait_for("return !!document.querySelector('[data-result=ts-set]')", 20)
                assert A.switch(NET)["on"]
                assert sorted(i for i, _k, _kw in counted) == sorted(got[k] for k in LISTED)
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
