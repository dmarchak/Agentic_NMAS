"""The can't-fix notice and its AI analysis (board H, part H8; docs/HEAL_TO_INTENT.md sections
10 and 12; `modules/heal_notice.py`). No provider and no relay: the gateway's provider is a
fake, and so are the relay's classes (tests/test_notify.py's `env`).

- **Never delaying the notification:** the message waits for the analysis up to its bound
  (60 s in the product); back in time, it carries it after Mercury's facts and before the link;
  not back, it says "AI analysis: pending", and the analysis goes as a follow-up, the event
  ``analysis``, an email threaded under the first (``In-Reply-To``). A failure or refusal is
  said in place (off for this network), never a silent absence.
- **No configuration line in a message:** a unit's line, a program line in a step's words, and
  the same line quoted by the analysis are each withheld.
- **Which incidents:** each can't-fix told about once (taken under the store's lock), a past
  one never (after a deploy, nothing old is analysed or sent); with no team told, nothing is
  sent and the analysis is still kept for Needs attention.
"""
import threading

from tests.test_heal_analysis import ANSWER, HA, T0, cant_fix, turn_on
from tests.test_heal_analysis import ai, lab, networks  # the fixtures, named by the tests
from tests.test_notify import _mail, _relay, _team_with_email
from tests.test_notify import env  # the fixture, named by the thread's test


class _Notice:
    def __getattr__(self, attr):
        import importlib

        return getattr(importlib.import_module("modules.heal_notice"), attr)


N = _Notice()


def told(record):
    """A delivery that keeps each event it was handed."""
    def deliver(network, event):
        record.append(event)
        return {"ok": True, "sent": 1, "failed": 0, "error": ""}
    return deliver


class TestTheWait:
    def test_back_in_time_the_one_message_carries_it_after_the_facts(self, ai):
        from modules.notify import message

        turn_on()
        inc = cant_fix()
        events = []
        got = N.notice("Default", inc, send=ai.send, deliver=told(events), wait_s=30,
                       now=T0 + 1)
        (ev,) = events
        assert got["follow_up"] is None and ev["event"] == "cant_fix"
        assert ev["analysis"]["state"] == "answered"
        text = message.text(message.check_event(ev))
        facts, analysis, link = (text.index("What Mercury tried:"),
                                 text.index("AI analysis: Advisory (beta)"),
                                 text.index("Open in Mercury:"))
        assert facts < analysis < link, "Mercury's facts first, then the analysis, then the link"
        assert "Next step: show ip interface GigabitEthernet2" in text

    def test_not_back_it_says_pending_then_follows_up(self, ai):
        turn_on()
        inc = cant_fix()
        release = threading.Event()
        real = ai.send

        def slow(body, key):
            assert release.wait(10), "the test released it"
            return real(body, key)
        events = []

        def deliver(network, event):
            events.append(event)
            if event["event"] == "cant_fix":
                release.set()              # the first message is out: the answer may come
            return {"ok": True, "sent": 1, "failed": 0, "error": ""}
        got = N.notice("Default", inc, send=slow, deliver=deliver, wait_s=0.2, follow_s=10,
                       now=T0 + 1)
        first, follow = events
        assert first["analysis"]["words"] == "AI analysis: pending"
        assert first["analysis"]["hypotheses"] == []
        assert follow["event"] == "analysis" and follow["incident"] == inc
        assert follow["analysis"]["state"] == "answered"
        assert got["first"]["state"] == "pending" and got["follow_up"]["state"] == "answered"

    def test_a_follow_up_that_never_comes_says_the_bound(self, ai):
        turn_on()
        inc = cant_fix()
        stuck = threading.Event()

        def never(body, key):
            stuck.wait(5)
            raise AssertionError("released at the test's end")
        events = []
        N.notice("Default", inc, send=never, deliver=told(events), wait_s=0.1, follow_s=0.2,
                 now=T0 + 1)
        stuck.set()
        first, follow = events
        assert first["analysis"]["words"] == "AI analysis: pending"
        assert follow["analysis"]["words"] == "AI analysis: the provider did not answer " \
                                              "within 0 s"

    def test_off_for_the_network_is_said_in_place_with_no_follow_up(self, ai):
        inc = cant_fix()
        events = []
        got = N.notice("Default", inc, send=ai.send, deliver=told(events), wait_s=30,
                       now=T0 + 1)
        (ev,) = events
        assert ev["analysis"]["words"] == "AI analysis: not run, off for this network"
        assert got["follow_up"] is None and ai.sent == []


class TestTheThread:
    def test_the_follow_up_is_an_email_threaded_under_the_first(self, ai, env, monkeypatch):
        from modules import config, heal_notify

        monkeypatch.setattr(config, "DATA_DIR", str(ai.dir))
        _relay(env)
        team, _dest = _team_with_email()
        monkeypatch.setattr(heal_notify, "teams_for", lambda network, event: [team])
        turn_on()
        inc = cant_fix()
        release = threading.Event()
        real = ai.send

        def slow(body, key):
            release.wait(10)
            return real(body, key)
        from modules.notify import delivery
        sent = delivery.send_to

        def send_to(*a, **kw):
            out = sent(*a, **kw)
            release.set()
            return out
        monkeypatch.setattr(delivery, "send_to", send_to)
        N.notice("Default", inc, send=slow, wait_s=0.2, follow_s=10, now=T0 + 1)
        mails = [_mail(raw) for s in env.smtp for raw in s.sent]
        first, follow = mails[-2], mails[-1]
        assert "AI analysis: pending" in first.get_content()
        assert follow["In-Reply-To"] == first["Message-ID"]
        assert "AI analysis of what could not be fixed" in follow["Subject"]
        assert "AI analysis: Advisory (beta)" in follow.get_content()


class TestNoConfigurationLine:
    def test_a_unit_s_line_and_its_quote_by_the_analysis_are_withheld(self, ai):
        from modules import evidence_pack as EP
        from modules.notify import message

        turn_on()
        ai.answer = dict(ANSWER, rationale="It added ip access-group EDGE-IN in on Gi2.")
        inc = cant_fix()
        events = []
        N.notice("Default", inc, send=ai.send, deliver=told(events), wait_s=30, now=T0 + 1)
        (ev,) = events
        text = message.text(message.check_event(ev))
        assert "EDGE-IN" not in text and EP.WITHHELD in text
        assert "EDGE-IN" not in str(message.payload(message.check_event(ev)))

    def test_a_program_line_a_step_held_is_withheld_from_the_message(self, ai, monkeypatch):
        from modules.heal import steplog
        from modules.notify import message

        inc = cant_fix()
        real = steplog.incident

        def planted(network, incident_id):
            e = real(network, incident_id)
            e["program"] = ["no ip route 192.0.2.128 255.255.255.128 192.0.2.10"]
            e["steps"].append({"step": "authorise", "result": "refused", "row": "act",
                               "words": "dangerous: NO IP ROUTE 192.0.2.128 255.255.255.128 "
                                        "192.0.2.10"})
            return e
        monkeypatch.setattr(steplog, "incident", planted)
        events = []
        N.notice("Default", inc, send=ai.send, deliver=told(events), wait_s=30, now=T0 + 1)
        (ev,) = events
        text = message.text(message.check_event(ev))
        # C2817: each step by what it does (its key is the webhook's), the line withheld.
        assert "192.0.2.128" not in text and \
            "Carried the reasons the lines need: dangerous: (a configuration line, withheld)" in text

    def test_an_analysis_block_carries_only_its_fields(self):
        import pytest
        from modules.notify import message

        ev = {"incident": "hi-000000000001", "event": "cant_fix", "network": "Default"}
        with pytest.raises(ValueError, match="an analysis block carries only"):
            message.check_event(dict(ev, analysis={"words": "w", "lines": ["ip route x"]}))
        with pytest.raises(ValueError, match="a hypothesis carries only"):
            message.check_event(dict(ev, analysis={"hypotheses": [{"claim": "c",
                                                                   "config": "x"}]}))
        got = message.check_event(dict(ev, analysis={"words": "w\r\nBcc: x@example.com"}))
        assert "\n" not in got["analysis"]["words"], "one line"


class TestWhichIncidents:
    def test_each_can_t_fix_is_told_once_and_a_past_one_never(self, ai):
        inc = cant_fix(now=T0)
        assert N.due("Default", now=T0 + N.NEW_WITHIN_S + 60) == [], \
            "not yet taken, and past: never told"
        assert [e["incident"] for e in N.due("Default", now=T0 + 30)] == [inc]
        started = []
        got = N.run("Default", now=T0 + 30, starter=lambda n, i, job, **kw: started.append(i))
        assert got["started"] == [inc] == started
        assert N.run("Default", now=T0 + 60, starter=lambda *a, **k: started.append(a))[
            "started"] == [], "taken once"
        assert N.due("Default", now=T0 + N.NEW_WITHIN_S + 1) == [], "the past is never told"

    def test_with_no_team_nothing_is_sent_and_the_analysis_is_kept(self, ai):
        turn_on()
        inc = cant_fix()
        got = N.notice("Default", inc, send=ai.send, wait_s=30, now=T0 + 1)
        assert got["first"].get("nobody") is True and got["first"]["sent"] == 0
        assert HA.latest("Default", inc)["state"] == "answered"
        rows = [r for r in HA.read("Default")["rows"] if r["row"] == "notice"]
        assert rows and rows[-1]["analysis_state"] == "answered"

    def test_the_runner_s_notify_step_runs_on_every_network(self, monkeypatch):
        from modules import heal_notice
        from modules.heal import detect

        seen = []
        monkeypatch.setattr("modules.integration_groups.network_names",
                            lambda: ["Default", "Branch"])
        monkeypatch.setattr(heal_notice, "run", lambda name: seen.append(name))
        detect._notify_step()
        assert seen == ["Default", "Branch"]

    def test_the_wait_is_the_operator_s_sixty_seconds(self):
        assert N.WAIT_S == 60.0
        from modules.ai import gateway
        assert N.follow_up_wait_s() == gateway.reservation_ttl_s()


class TestNoCantFixOffersCapture:
    """C2876 with C2824's rule: a can't-fix is a change something went wrong beside, so what
    it says to do never offers Capture (recording the change as the approved state); the
    default names C2824's two answers. Every to-do, the default and each outcome's, by the
    property, never a list of the kinds."""

    def test_no_to_do_names_capture(self):
        todos = dict(N.TODO, default=N.TODO_DEFAULT, **{f"outcome:{k}": v
                                                         for k, v in N.TODO_OUTCOME.items()})
        assert len(todos) >= 8, "the population: every kind's to-do, the default, the outcomes"
        assert [k for k, v in todos.items() if "capture" in v.lower()] == []

    def test_the_default_names_both_answers(self):
        assert "put it back to intent" in N.TODO_DEFAULT
        assert "adding it to intent" in N.TODO_DEFAULT
