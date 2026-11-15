"""The can't-fix notice leads with its bottom line (C3726; the operator's R2, 2026-11-14,
MERCURY_CHARTER "Two standing rules": every screen, card and notification leads with what
happened, its impact and the one next action).

Measured on the host for r7's lost streams (hi-22cfdc299000, 2026-11-15 02:17 UTC, read-only):
the notice led with "r7: 2 telemetry streams lost. At 21:30, the alert …", said "What to do:
decide on the change: put it back to intent …" (guard 4's hold's advice, not the lost stream's)
and listed "Find approved state: failed" (a hold drawn as a failure). Planted here in r7's shape
on tests/test_fixit_section_v2.py's lab: r2's incident opened by the incidents store's own
writer from two lost-stream alerts (101 and 102), Mercury's Re-subscribe tried in it and failed
(a real run), then a decision held by guard 4 (its saved config does not match intent) and a
can't-fix, each by the decisions store's and the step log's own writers. No device, no network,
no AI call, no mail sent.

- **The bottom line leads:** the message's first line is the problem, as the incident's page
  titles it (`bluf.what_of`), and its impact (`bluf.TABLE`'s); its second What to do, the
  incident's OWN next action, the one its page's bottom line offers (Start AI troubleshooting),
  never the hold's "decide on the change"; its third the link; its subject the title.
- **A hold is a plain line:** the step guard 4 stopped says the hold's own words
  (`bluf.hold_line`), never "failed"; the webhook's JSON says the same.
- **A decision's own advice stands** where the problem is the decision's (a drift can't-fix
  keeps "decide on the change"), so the rule is the problem's, never one wording for all.
"""
import re

import pytest

from tests import test_fixit_section_v2 as FX
from tests.test_fixit_section_v2 import web  # noqa: F401  (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401  (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

NET = FX.NET
WHAT = "r2: telemetry streams 101 and 102 lost"
IMPACT = "Mercury can't see r2's interfaces or CPU; traffic is unaffected"
#: The lines guard 4 counted as departing (its operands), as the decision records them.
DEPARTING = ["ip route 192.0.2.0 255.255.255.0 Null0", "ipv6 route 2001:db8::/32 Null0"]


def decided(iid, outcome, **more):
    """One decision on r2 in incident *iid*, recorded by the decisions store's own writer and
    its step log row by the step log's (`steplog.record_decision`)."""
    from modules.heal import decisions, steplog

    d = decisions.record(NET, dict({
        "incident": iid, "device": "r2", "outcome": outcome, "mode": "dry_run", "kind": "",
        "tier": 0, "units": [], "program": [], "program_hash": "", "guard": None,
        "steps": [{"step": "claim", "result": "ok", "words": "the incident on r2 taken"},
                  {"step": "stops", "result": "ok", "words": "no kill switch, dry run, no "
                                                             "halt, no planned work"}],
        "phase": "approved", "words": "", "outcome_words": ""}, **more))
    steplog.record_decision(NET, d)
    return d


def held_by_guard_4(iid):
    from modules.heal import guards

    g = guards.hit(4, "held", "its saved config does not match intent",
                   {"lines": DEPARTING, "lines_more": 0})
    return decided(iid, "held", guard={k: g[k] for k in ("guard", "name", "words", "operands")},
                   words="held: its saved config does not match intent")


def lost_stream_cant_fix(web):  # noqa: F811
    """r7's shape: the lost streams, Mercury's re-subscribe failed, guard 4's hold, then a
    can't-fix; ``(incident id, its step log entry, its incidents-store record)``."""
    from modules.heal import incidents, steplog

    iid = FX.plant()
    FX.attempt(web)
    held_by_guard_4(iid)
    said = ("Mercury cannot fix this yet: no configuration fix cures a lost stream; nothing "
            "was sent (Tier 3)")
    decided(iid, "cant_fix", phase="decide", words=said, outcome_words=said)
    entry = steplog.incident(NET, iid)
    record = next(i for i in incidents.read(NET)["incidents"] if i["id"] == iid)
    return iid, entry, record


def page_next_action(web, iid):  # noqa: F811
    """The one next action the incident's page's bottom line offers, in its words, or None
    when it offers nothing to press but a hand-over."""
    _r, html = FX.page(web, iid)
    fix = FX.bluf_of(html).split('data-bluf="fix"', 1)[1]
    m = re.search(r'<span class="op-idle">([^<]+)</span>', fix)
    return m.group(1) if m else None


class TestTheBottomLineLeads:
    def test_a_lost_stream_s_notice_leads_with_its_problem_its_impact_and_its_own_action(
            self, web):  # noqa: F811
        from modules import heal_notice
        from modules.notify import message

        iid, entry, record = lost_stream_cant_fix(web)
        facts = message.check_event(heal_notice.facts(NET, entry, record))
        text = message.text(facts)
        lines = text.splitlines()
        assert lines[0] == f"{WHAT}. {IMPACT}.", lines[:3]
        nxt = page_next_action(web, iid)
        assert nxt == "Start AI troubleshooting", "the page's own next action, read there"
        assert lines[1] == f"What to do: {nxt}, on the incident's page", lines[1]
        assert lines[2].startswith("Open in Mercury: ") and f"/v2/incident/{iid}" in lines[2]
        assert "decide on the change" not in text, "never the hold's advice for a lost stream"
        # The subject names the title (the network left out when beside it the header would
        # pass 69 characters and fold).
        assert message.subject(facts) == f"[Mercury] {WHAT}: could not fix"
        assert message.subject(dict(facts, network="B")) == f"[Mercury] {WHAT} (B): could not fix"
        # The heading of the incident's page is the same title.
        _r, html = FX.page(web, iid)
        h1 = re.sub(r"<[^>]+>", "", html.split('<h1 id="inc-title">', 1)[1].split("</h1>")[0])
        assert h1.strip().startswith(WHAT), h1
        # The rest below: the outcome once, on its own line.
        assert text.count("Mercury cannot fix this yet") == 1
        assert "\nOutcome: Mercury cannot fix this yet: " in text


class TestAHoldIsAPlainLine:
    def test_guard_4_s_step_says_the_hold_never_failed(self, web):  # noqa: F811
        from modules import heal_notice
        from modules.notify import message

        _iid, entry, record = lost_stream_cant_fix(web)
        facts = message.check_event(heal_notice.facts(NET, entry, record))
        held = [s for s in facts["steps"] if s.get("label") == "Find approved state"]
        assert held, facts["steps"]
        hold = ("Self-healing won't write to r2 until its saved config matches intent (2 lines "
                "differ)")
        assert [s["result"] for s in held] == [hold], held
        assert [s.get("words", "") for s in held] == [""], "the hold said once, as its result"
        text = message.text(facts)
        assert f"Find approved state: {hold};" in text or f"Find approved state: {hold}\n" in \
            text, text
        assert not re.search(r"Find approved state[^\n]*: failed", text), text
        assert "doesn't block the fix below" not in text, "a message draws no fix below"
        hook = message.payload(facts)
        assert hook["title"] == WHAT and hook["lead"] == f"{WHAT}. {IMPACT}."
        assert hold in [s["result"] for s in hook["steps"]]

    def test_the_scan_finds_a_hold_said_as_failed(self):
        """The floor: the line the host's notice measured is what the check refuses."""
        assert re.search(r"Find approved state[^\n]*: failed",
                         "  - 21:30 Find approved state: failed\n")


def adjacency_cant_fix(kind):
    """A can't-fix on r2 whose problem is the decision's own (an adjacency, no lost stream)."""
    from modules.heal import incidents, steplog
    from tests.test_heal_act import ADJ

    iid = incidents.sight(NET, "r2", dict(ADJ, related=[]), now=FX.DETECTED)["incident"]
    decided(iid, "cant_fix", phase="decide", kind=kind,
            outcome_words="Mercury cannot fix this yet: nothing was sent (Tier 3)")
    entry = steplog.incident(NET, iid)
    return iid, entry, next(i for i in incidents.read(NET)["incidents"] if i["id"] == iid)


class TestTheNextActionIsTheIncidentsOwn:
    def test_a_link_down_can_t_fix_offers_nothing_its_page_does_not(self, web):  # noqa: F811
        """The notice's next action is the page's own, from the page's model
        (`incident_page.page`, the one its template draws; no request made): where the page
        offers nothing to press, the decision's kind's advice, never a press it lacks."""
        from modules import heal_notice
        from modules import incident_page as IP

        iid, entry, record = adjacency_cant_fix("physical")
        bl = heal_notice.bottom_line(NET, entry, record)
        assert bl["what"] == "r2: a link is down while it is meant to be up", bl
        fix = (IP.page(NET, iid)["fixit"].get("bluf") or {}).get("fix") or {}
        pressed = fix.get("label") if fix.get("kind") in ("start", "approve", "button") else ""
        assert bl["next"] == (f"{pressed}, on the incident's page" if pressed else
                              heal_notice.TODO["physical"]), (bl, fix)

    @pytest.mark.parametrize("kind, want", [
        ("drift", "decide on the change: put it back to intent"),
        ("physical", "check the link: its cable, optics and far end")])
    def test_with_nothing_to_press_the_decision_s_own_advice_stands(self, web, monkeypatch,  # noqa: F811
                                                                     kind, want):
        """Where the page's bottom line offers nothing to press but a hand-over (the section's
        answer planted at its seam), the decision's kind's advice, or the default's two
        answers for a problem that is the decision's own."""
        from modules import heal_notice
        from modules.fixit import section

        monkeypatch.setattr(section, "view", lambda *a, **k: {"bluf": {"fix": {
            "kind": "hand_over", "label": "Hand over"}}})
        _iid, entry, record = adjacency_cant_fix(kind)
        assert heal_notice.bottom_line(NET, entry, record)["next"].startswith(want)

    def test_a_lost_stream_with_nothing_to_press_is_handed_over_never_the_hold_s_advice(
            self, web, monkeypatch):  # noqa: F811
        from modules import heal_notice
        from modules.fixit import section

        monkeypatch.setattr(section, "view", lambda *a, **k: {"bluf": {"fix": {
            "kind": "hand_over", "label": "Hand over"}}})
        _iid, entry, record = lost_stream_cant_fix(web)
        assert heal_notice.bottom_line(NET, entry, record)["next"] == \
            "hand it over to an engineer, on the incident's page"


class TestTheSubjectNamesPeopleByDisplayName:
    def test_an_identity_in_the_title_is_its_display_name_in_the_subject_as_in_the_body(
            self, monkeypatch, tmp_path):
        """A title may carry a person's identity (a change's log line names its account): the
        subject names them by display name, as the body does (`message._people`). The name is
        set in this test's own display-name store: set in the run's shared one, it outlived the
        test and labelled "alex" in a later test's text (CI #1740)."""
        from modules import display_names
        from modules.notify import message

        monkeypatch.setattr(display_names, "_path", lambda: str(tmp_path / "display_names.json"))
        who = "alex@example.invalid"
        display_names.set_name(who, "Alex R", by=who, actor_verified="access")
        facts = message.check_event({
            "incident": "hi-000000000001", "event": "cant_fix", "network": "B", "device": "r2",
            "title": f"r2: changed by {who}", "lead": f"r2: changed by {who}.",
            "outcome": "nothing was sent", "steps": [], "link": ""})
        subject, body = message.subject(facts), message.text(facts)
        assert who not in subject and who not in body, (subject, body)
        assert subject == "[Mercury] r2: changed by Alex R (B): could not fix", subject
        assert body.startswith("r2: changed by Alex R."), body
