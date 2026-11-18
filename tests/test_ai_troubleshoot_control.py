"""Gate 2: ONE AI troubleshooting control per network, Off, Manual or Automatic (C3769), its
spending limits acknowledged with their estimate in Settings, and the control strip's "AI
troubleshooting: Automatic" switch (the operator's minimal design, 2026-11-15:
"1. ... Turning it on with open incidents shows one inline line ('Also starts on N open
incidents, about $X') and nothing else ... All open eligible incidents start, within the caps;
one past a cap is refused, named on its card. 2. Spending limits live in Settings, one place:
per incident, per day, per month (per network, with installation defaults), with the estimate
... The estimate is acknowledged there when limits are set ... 3. Keep tonight's detailed form
reachable from Settings for audit").

Through tests/test_fixit_catch_up.py's world (the real app, the real gateway with only the
provider replaced), with its incidents planted by the stores' own writers. No device, no live
AI call: each investigation started is counted, never asked.

Each test holds one purpose:
- the switch refuses Automatic until the limits and their estimate are acknowledged, its
  refusal linking the limits card, with nothing changed;
- once acknowledged, the strip draws the one line, and one press turns Automatic on and starts
  every listed incident, recorded with the turn-on;
- a limit changed since it was acknowledged is refused, naming both digests;
- a line that moved since it was drawn is refused, naming both;
- off goes back to Manual and keeps the limits acknowledged;
- the mode is per network: a network with none of its own reads the installation's;
- the per-incident limit is per network, and an incident's cap comparison reads it;
- Background features no longer draws automatic AI troubleshooting's row, and draws the
  retired analysis only while it is on; the detailed form stays reachable from the card.
"""
import re
from html import unescape

import pytest

from modules.ai import background as B
from modules import troubleshoot_control as T
from modules.fixit import auto as A
from modules.fixit import policy as P
from tests.test_fixit_auto import NOW, decide, iso, policy, run, turn_on  # noqa: F401
from tests.test_fixit_catch_up import LISTED, counted, planted, world  # noqa: F401
from tests.test_fixit_section_v2 import NET
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_fixit_troubleshoot import ai  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

LEVEL = f"/v2/settings/installation/ai/troubleshoot/{NET}/level"
LIMITS = f"/v2/settings/installation/ai/troubleshoot/{NET}/limits"
HX = {"HX-Request": "true"}


def page(w) -> str:
    r = w.client.get(f"/v2/settings/installation?tab=ai&network={NET}")
    assert r.status_code == 200
    return unescape(r.get_data(as_text=True))


def strip(w) -> str:
    r = w.client.get(f"/v2/control/strip?list={NET}")
    assert r.status_code == 200
    return unescape(r.get_data(as_text=True))


def shown_estimate(html: str) -> str:
    m = re.search(r'class="ai-ts-limits".*?name="estimate_digest" value="([0-9a-f]{64})"', html, re.S)
    assert m, "the limits form sends no estimate digest"
    return m.group(1)


def shown_line(html: str) -> str:
    m = re.search(r'id="ctl-ai".*?name="line_digest" value="([0-9a-f]{64})"', html, re.S)
    assert m, "the strip's switch sends no line digest"
    return m.group(1)


def acknowledge(w, incident="0.80", day="1.50", month="10.00"):
    r = w.client.post(LIMITS, headers=HX, data={
        "estimate_digest": shown_estimate(page(w)), "incident_cap_usd": incident, "day_cap_usd": day,
        "month_cap_usd": month, "accept": "on"})
    return r, unescape(r.get_data(as_text=True))


def press(w, level="automatic", shown=None):
    r = w.client.post(f"{LEVEL}?answer=strip", headers=HX, data={
        "level": level, "line_digest": shown_line(strip(w)) if shown is None else shown})
    return r, unescape(r.get_data(as_text=True))


class TestTheSwitchWaitsForTheLimits:
    def test_automatic_is_refused_until_acknowledged_linking_the_limits_card(self, world,
                                                                            counted):
        planted()
        before = B.switches()
        r, html = press(world)
        assert r.status_code == 409, html
        assert "Automatic was not turned on" in html and "not acknowledged" in html
        assert f'href="{T.limits_href(NET)}"' in html and "#ai-ts" in T.limits_href(NET)
        assert not A.switch(NET)["on"] and counted == [] and B.switches() == before

    def test_a_limit_changed_since_it_was_acknowledged_is_refused_naming_both(self, world,
                                                                             counted):
        planted()
        r, out = acknowledge(world)
        assert r.status_code == 200, out
        was = B.record_of(B._network(NET), A.FEATURE)["limits_ack"]["limits_digest"]
        # A limit moved by another path (the record's own merge), not acknowledged again.
        B.update_record(NET, A.FEATURE, {"day_cap_usd": 1.20}, kind="ai_background_caps",
                        actor="admin@example.com", verified="access")
        r, html = press(world)
        assert r.status_code == 409, html
        now = T.limits_digest(0.80, 1.20, 10.00)
        assert f"acknowledged {was[:12]}, now {now[:12]}" in html
        assert not A.switch(NET)["on"] and counted == []


def _calls_at(usd: float, n: int = 3):
    """*n* sent calls of AI troubleshooting's task at *usd* each, on its pinned model: the
    measured cost per call (`background.measured_cost`) becomes their mean."""
    from modules.ai import calls, profiles
    from tests.conftest import TEST_PERSON
    model = profiles.task("fixit_troubleshoot")["model"]
    for _ in range(n):
        assert calls.record({"id": calls.new_id(), "feature": "fixit_troubleshoot",
                             "actor": TEST_PERSON, "model": model, "cost_usd": usd,
                             "tokens": {"in": 1, "out": 1},
                             "trigger": {"kind": "person", "by": TEST_PERSON}})["recorded"]


class TestWhatTheAcknowledgementBinds:
    """The operator's correction, 2026-11-15: the acknowledgement binds the limits and the
    estimate's cost per call, never the frequency (it moves with every new failure); it holds
    until a limit changes or the cost per call passes 1.5 times the acknowledged (C3770's
    option (a))."""

    def test_a_new_failure_moves_the_frequency_and_leaves_it_standing(self, world, counted):
        from modules.heal import steplog
        from tests.test_fixit_catch_up import DETECTED
        got = planted()
        acknowledge(world)
        before = B.estimate(B._network(NET), A.FEATURE)
        # One failure more: an act of its own decision that rolled back (the step log's writer).
        steplog.append(NET, {"row": "act", "decision": "hd-00000000ac7e", "incident": got["dry"],
                             "device": "r6", "outcome": "rolled_back", "kind": "missing_line"},
                       DETECTED + 41)
        after = B.estimate(B._network(NET), A.FEATURE)
        assert after["frequency"] != before["frequency"] and after["digest"] != before["digest"]
        assert T.readiness(NET) == ""
        r, html = press(world)
        assert r.status_code == 200 and A.switch(NET)["on"], html

    def test_a_cost_per_call_past_one_and_a_half_times_asks_again(self, world, counted):
        planted()
        _calls_at(0.02)
        acknowledge(world)
        assert B.record_of(B._network(NET), A.FEATURE)["limits_ack"]["usd_per_call"] == \
            pytest.approx(0.02)
        _calls_at(0.02 + 0.02 * 3, n=3)          # the mean becomes 0.05: 2.5 times
        why = T.readiness(NET)
        assert "$0.05 passed 1.5 times the $0.02 acknowledged" in why, why
        r, html = press(world)
        assert r.status_code == 409 and "passed 1.5 times" in html
        assert not A.switch(NET)["on"] and counted == []

    def test_a_cost_within_one_and_a_half_times_holds(self, world):
        _calls_at(0.02)
        acknowledge(world)
        _calls_at(0.02 + 0.01 * 2, n=2)          # the mean becomes 0.028: 1.4 times
        assert T.readiness(NET) == ""


class TestTheTurnOnIsBoundToTheLimitsRead:
    def test_limits_changed_between_the_read_and_the_write_refuse(self, world, counted,
                                                                  monkeypatch):
        """Gate 2's review: `set_level` reads the limits, then `background.turn_on` writes the
        switch; a limit changed between (here, while the line is read) is refused at the write,
        under the settings lock, naming both, with nothing turned on."""
        planted()
        acknowledge(world)
        shown = shown_line(strip(world))
        real = T.catch_up_line

        def moving(network, now=None):
            got = real(network, now=now)
            B.update_record(NET, A.FEATURE, {"day_cap_usd": 1.10}, kind="ai_background_caps",
                            actor="admin@example.com", verified="access")
            return got
        monkeypatch.setattr(T, "catch_up_line", moving)
        r, html = press(world, shown=shown)
        assert r.status_code == 409 and "the limits changed since they were read" in html, html
        assert not A.switch(NET)["on"] and counted == []


class TestTheAuditFormIsReadOnly:
    def test_it_lists_and_has_no_turn_on_and_a_post_turns_nothing_on(self, world, counted):
        got = planted()
        r = world.client.get(f"/v2/settings/installation/ai/background/{NET}/fixit_auto/on",
                             headers=HX)
        html = unescape(r.get_data(as_text=True))
        audit = html.split('data-audit="read-only"', 1)[1].split('</div>\n</div>', 1)[0]
        assert r.status_code == 200 and all(got[k] in audit for k in LISTED)
        assert "<form" not in audit and 'type="checkbox"' not in audit
        assert "Turn on" not in audit
        # Posted anyway (as the old form did), it is refused and nothing changes.
        r = world.client.post(f"/v2/settings/installation/ai/background/{NET}/fixit_auto/on",
                              headers=HX, data={
            "shown": B.estimate(B._network(NET), A.FEATURE)["digest"], "accept": "on",
            "day_cap_usd": "1.50", "month_cap_usd": "10.00", "listed": [got["stream"]],
            "start": [got["stream"]]})
        assert r.status_code == 409 and "for audit and turns nothing on" in unescape(
            r.get_data(as_text=True))
        assert not A.switch(NET)["on"] and counted == []


class TestOnePress:
    def test_the_line_then_one_press_starts_every_open_incident_within_the_caps(self, world,
                                                                               counted):
        from modules import installation_settings as I
        from modules.ai import fixit_troubleshoot as AIT
        from modules.money import usd
        got = planted()
        # A day cap that holds four investigations at their worst case (`CALLS_WORST`, four
        # calls each since the investigation loop, C3797), so every listed incident starts.
        r, out = acknowledge(world, day="3.00")
        assert r.status_code == 200 and "Automatic may be turned on" in out, out
        each = AIT.estimate()["usd"]
        html = strip(world)
        # Premise corrected (C3872, 7d54cf24, the operator, 2026-11-16: "a refused start spends
        # no key"): five are listed, the incident whose automatic start a cap refused among them
        # (tests/test_fixit_catch_up.py's LISTED).
        assert f"Also starts on 5 open incidents, about {usd(each * 5)}" in html
        assert 'name="start"' not in html and 'type="checkbox"' not in html, "no ticks, no form"
        r, html = press(world)
        assert r.status_code == 200, html
        assert A.switch(NET)["on"]
        assert sorted(i for i, _k, _kw in counted) == sorted(got[k] for k in LISTED)
        (rec,) = [x for x in I.changes()["rows"] if x.get("kind") == "ai_background_on"]
        assert sorted(rec["catch_up"]["ticked"]) == sorted(got[k] for k in LISTED)
        assert rec["catch_up"]["unticked"] == []
        # Premise corrected (8f1d8006, the operator, 2026-11-16: "Every switch flips
        # instantly; the work it starts happens after, in the background", C3866): the press
        # answers at once, its catch-up a job after it (run in the request here).
        assert "Starting the AI on 5 incidents…" in html, html[-1500:]

    def test_a_line_that_moved_since_it_was_drawn_is_refused_naming_both(self, world, counted):
        planted()
        acknowledge(world)
        drawn = "0" * 64
        r, html = press(world, shown=drawn)
        assert r.status_code == 409, html
        now = T.catch_up_line(NET)["digest"]
        assert f"drawn {drawn[:12]}, now {now[:12]}" in html
        assert not A.switch(NET)["on"] and counted == []

    def test_off_is_manual_and_keeps_the_limits_acknowledged(self, world, counted):
        acknowledge(world)
        r, html = press(world)
        assert r.status_code == 200 and A.switch(NET)["on"], html
        r, html = press(world, level="manual", shown="")
        assert r.status_code == 200, html
        assert not A.switch(NET)["on"] and T.level(NET)["level"] == "manual"
        rec = B.record_of(B._network(NET), A.FEATURE)
        assert rec["on"] is False and rec["limits_ack"]["estimate_digest"]
        assert T.readiness(NET) == ""


class TestPerNetwork:
    def test_a_network_with_no_mode_of_its_own_reads_the_installations(self, world):
        assert P.mode(NET) == {"state": "ok", "mode": "manual", "error": "",
                               "source": "installation"}
        T.set_level(NET, "off", actor="admin@example.com", verified="access")
        assert P.mode(NET)["mode"] == "off" and P.mode(NET)["source"] == "network"
        assert "off for" in P.ai_refusal(NET) and P.ai_refusal() == ""
        assert T.level(NET)["level"] == "off"

    def test_the_per_incident_limit_is_the_networks_and_the_cap_reads_it(self, world):
        from tests.test_fixit_catch_up import inc_of
        got = planted()
        assert P.cap_usd(NET)["source"] == "installation"
        acknowledge(world, incident="0.30")
        assert P.cap_usd(NET) == {"state": "ok", "usd": 0.30, "error": "", "source": "network"}
        cs = P.cap_state(inc_of(got["cant_fix"]), 0.25)
        assert cs["cap"] == 0.30
        assert P.cap_state(inc_of(got["cant_fix"]), 0.31)["state"] == "refused"


class TestTheRowsSayIt:
    """The operator, 2026-11-15: on Incidents' and Needs attention's rows, "AI investigating"
    with its start time while an investigation runs, and its one-line outcome when it ends,
    live (the job's announcements; no polling)."""

    def test_investigating_then_its_outcome_on_the_incidents_row(self, world):
        from modules import incidents_list
        from modules.fixit import incident as F
        from tests.test_fixit_catch_up import inc_of
        got = planted()
        iid = got["cant_fix"]
        F.claim_start(inc_of(iid), f"decision:{iid}", trigger="auto", state="started",
                      now=__import__("time").time())
        row = next(r for r in incidents_list.rows(NET)["rows"] if r["id"] == iid)
        assert row["ai"]["state"] == "investigating" and row["ai"]["since"]
        body = unescape(world.client.get(f"/v2/incidents?list={NET}").get_data(as_text=True))
        assert re.search(r'data-ai="investigating">AI investigating since <time', body), body
        # Ended: its failure kept, the row says the outcome in one line.
        F.claim_start(inc_of(iid), f"decision:{iid}:failed", trigger="auto", state="failed",
                      words="the provider did not answer")
        row = next(r for r in incidents_list.rows(NET)["rows"] if r["id"] == iid)
        assert row["ai"]["state"] == "ended" and "the provider did not answer" in \
            row["ai"]["words"]

    def test_a_needs_attention_row_about_the_incident_says_it_too(self):
        from modules import attention
        ai = {"state": "investigating", "since": "2026-11-15T07:00:00Z",
              "words": "AI investigating"}
        listed = {"rows": [{"id": "hi-00000000aa01", "resolved": False, "state": "open",
                            "ai": ai}], "unreadable": []}
        rows = [{"source": "heal", "kind": "cant_fix", "id": "r1",
                 "incident_page": {"id": "hi-00000000aa01", "list": "Lab"}}]
        out = attention._incidents_agree(rows, "Lab", listed=listed)
        assert out[0]["ai_status"] == ai

    def test_the_analysis_is_folded_into_the_investigation_where_none_answered(self, world):
        from modules.fixit import incident as F
        from routes import v2
        from tests.test_fixit_catch_up import inc_of
        got = planted()
        iid = got["cant_fix"]
        assert v2.heal_analysis_of(NET, iid)["state"] == "ok", "no investigation: as before"
        F.claim_start(inc_of(iid), f"decision:{iid}", trigger="auto", state="started",
                      now=__import__("time").time())
        folded = v2.heal_analysis_of(NET, iid)
        assert folded["state"] == "investigation"
        assert folded["investigation"]["state"] == "investigating"
        assert folded["investigation"]["href"].startswith(f"/v2/incident/{iid}")

    def test_a_start_is_announced_so_open_pages_read_it(self, monkeypatch):
        from modules import invalidation, troubleshoot_job
        from modules.nsot import capture_job
        heard = []
        monkeypatch.setattr(capture_job, "start", lambda *a, **kw: "job-1")
        monkeypatch.setattr(invalidation, "announce",
                            lambda keys, by, ok=True: heard.append((tuple(keys), by)))
        assert troubleshoot_job.start(NET, "hi-000000000001", "a@example.com",
                                      lambda _j: None) == "job-1"
        assert heard == [(("drift",), troubleshoot_job.ANNOUNCER)]


class TestSettings:
    def test_one_card_its_off_press_and_the_detailed_form_reachable(self, world):
        html = page(world)
        assert 'role="listitem" id="bg-fixit_auto"' not in html
        assert 'id="bg-heal_analysis"' not in html, "retired: drawn only while on"
        link = re.search(r'id="bg-fixit_auto"><span class="op-act"><a [^>]*href="([^"]*/'
                         + NET + r'/fixit_auto/on)"', html)
        assert link, "the audit form's link"
        # The audit link opens the detailed form, in the card, for automatic AI troubleshooting.
        r = world.client.get(link.group(1), headers=HX)
        assert r.status_code == 200 and 'data-audit="read-only"' in r.get_data(as_text=True)
        # The card's Off is the network's own mode, recorded; the card redrawn saying so.
        r = world.client.post(LEVEL, headers=HX, data={"level": "off", "line_digest": ""})
        out = unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and "AI troubleshooting is Off on Default" in out, out
        assert P.mode(NET)["mode"] == "off" and 'data-level="off"' in out

    def test_the_limits_refuse_an_estimate_not_acknowledged(self, world):
        r = world.client.post(LIMITS, headers=HX, data={
            "estimate_digest": shown_estimate(page(world)), "incident_cap_usd": "0.80",
            "day_cap_usd": "1.50", "month_cap_usd": "10.00"})
        assert r.status_code == 409 and "not acknowledged" in unescape(
            r.get_data(as_text=True))
        assert "limits_ack" not in B.record_of(B._network(NET), A.FEATURE)
