"""The hand-over: an incident's write-up for an engineer and its relay event
(modules/fixit/handover.py; the fix-it board's step 8, the fix-it plan's S3; the operator's
order of 2026-11-12, overnight item 6: "on failure STOP with Retry with more information (cost
shown first), Cancel or Hand over"). No AI call, nothing drawn.

**On real records.** The incident's attempt is a real Re-subscribe run whose verify reads no
data (`not_back`), its proposal Mercury's own, recorded by the incident's own writer; its call
of AI is a row the record of AI calls' writer wrote; the diagnosis is the lost-stream runbook
run on its real captures (tests/test_fixit_catalogue.py's `half_open_run`); the teams are made
by the teams store's own functions and named by Who is told's own save; the message is checked
by the notifier's own `check_event`. The relay itself is a stand-in that records what it was
handed (`Relay`), and once the real `deliver_event` with no destination to send to.

**People by display name, no email address and no secret** (the board): the planted actor is an
email address with a display name set, and a planted SNMP community in the note; the
write-up, its Markdown and the message each hold the display name and neither of the two.
"""
import json
import os

import pytest

from modules.fixit import handover as H
from modules.fixit import incident as F
from modules.fixit import validate as V
from tests.test_fixit_catalogue import half_open_run, inc
from tests.test_fixit_incident import CALL_A, LATER, T0, a_call, a_run, carry
from tests.test_heal_resubscribe import ACTOR, NET, Src, lab  # noqa: F401 (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

#: A display name a test sets for the planted actor (no real person's).
NAME = "Riley Tester"
#: A planted secret in a note: an SNMP community in its position.
COMMUNITY = "Wq9xZr7Lp2"
NOTE = f"the collector's socket looked stuck; snmp-server community {COMMUNITY} RO"


class Relay:
    """A stand-in for `delivery.deliver_event`: what it was handed, each event checked by the
    notifier's own `check_event` as the real one checks it first."""

    def __init__(self, answer=None):
        self.sent, self.answer = [], answer

    def __call__(self, event, team_ids):
        from modules.notify import message
        self.sent.append((message.check_event(event), list(team_ids)))
        return self.answer or {"ok": True, "sent": len(team_ids), "failed": 0,
                               "deliveries": [], "error": ""}


@pytest.fixture
def named(lab):  # noqa: F811
    from modules import display_names
    display_names.set_name(ACTOR, NAME, by=ACTOR, actor_verified="access")
    return lab


def a_team(name="Network team", told=True):
    """A team in the teams store, told about the network's can't-fix through Who is told's
    own save when *told*."""
    from modules import heal_notify
    from modules.notify import teams
    team = teams.add_team(name, by=ACTOR)["team"]
    if told:
        heal_notify.save(NET, team, ["cant_fix"], actor=ACTOR, actor_verified="access",
                         loaded=heal_notify.drawn(heal_notify.read(NET)))
    return team


def an_incident():
    """The worked example's shape: Mercury proposed a Re-subscribe, a person approved it, its
    verify read no data; an AI call made since."""
    line = V.propose(inc(), "mercury", "telemetry-resubscribe",
                     {"device": "r2", "subscriptions": ["101", "102"]}, now=T0 - 60,
                     sources=Src())
    assert line["ok"], line
    failed = a_run(T0, ok=False, subs=("101", "102"))
    carry(failed, {"incident": inc().id, "attempt": 1, "proposal": line["proposal"]})
    a_call(CALL_A, 0.0257)
    F.record_proposal(inc(), "ai", calls=[CALL_A], prompt="fixit_troubleshoot/1", now=T0 + 900)
    return failed


def hand_over(**kw):
    kw.setdefault("actor", ACTOR)
    kw.setdefault("actor_verified", "access")
    kw.setdefault("now", LATER)
    return H.hand_over(inc(), **kw)


def everything(got) -> str:
    """Every byte a hand-over leaves: the kept write-up, its Markdown and each message."""
    kept = H.read_version(inc(), got["version"])["doc"]
    return json.dumps([got["doc"], kept]) + got["doc"]["markdown"]


# ── The nine sections ───────────────────────────────────────────────────────────────────────

class TestTheWriteUp:
    def test_the_nine_sections_in_the_boards_order_from_the_record(self, named, tmp_path):
        failed = an_incident()
        diagnosis = half_open_run(tmp_path)
        got = hand_over(note=NOTE, notes=["streams stay lost after the path came back"],
                        diagnosis=diagnosis, title="telemetry stream lost (101, 102)")
        doc = got["doc"]
        assert got["version"] == 1 == doc["version"]
        assert [s["key"] for s in doc["sections"]] == [k for k, _t in H.SECTIONS] == [
            "summary", "impact", "known", "tried", "ai", "config", "next", "notes", "cost"]
        s = {x["key"]: x["lines"] for x in doc["sections"]}
        assert s["summary"] == ["r2: telemetry stream lost (101, 102); 1 fix tried; not fixed."]
        # Each time is kept as its instant (C3290): the page draws it in the viewer's zone, and
        # the Markdown and a team's message, which leave Mercury, say it in UTC.
        assert s["impact"][0].startswith("r2 has sent no telemetry for subscription 101 and "
                                         "102 since 2026-11-09T17:46Z (")
        assert s["known"][0].startswith("strong (half_open): the collector still holds an "
                                        "established session from r2")
        assert "(read " in s["known"][0] and "Mercury's diagnosis " in s["known"][0]
        (tried,) = s["tried"]
        assert tried.startswith("Attempt 1, 2026-11-09T18:46:40Z: Re-subscribe a device's "
                                "lost telemetry streams (subs 101, 102); proposed by "
                                f"Mercury's diagnosis; approved by {NAME}; did not pass: ")
        md = doc["markdown"]
        assert ("- r2 has sent no telemetry for subscription 101 and 102 since "
                "2026-11-09 17:46 UTC (") in md
        assert "- Attempt 1, 2026-11-09 18:46:40 UTC: Re-subscribe a device's " in md
        assert "T17:46Z" not in md and "T18:46:40Z" not in md
        assert failed["why"].split(";")[0] in tried
        assert s["ai"][0].startswith("2026-11-09T19:01:40Z: proposed no operation Mercury has")
        assert s["config"] == ["No receiver a run left removed on r2."]
        assert ("Not tried: Add back the receiver of one telemetry subscription a run left "
                "removed (telemetry-readd)") in s["next"]
        assert any(x.startswith("The read that would decide: ") for x in s["next"])
        assert s["next"][-2:] == list(H.DONTS)
        assert s["notes"] == ["Retry note: streams stay lost after the path came back",
                              "Hand-over note: the collector's socket looked stuck; "
                              "snmp-server community <redacted:snmp_community> RO"]
        assert s["cost"] == [f"{CALL_A}: $0.0257",
                             "Total $0.0257 in this incident. The provider bills, not Mercury."]
        assert doc["by"] == NAME and doc["link"] == f"/v2/incident/{inc().id}?list={NET}"

    def test_no_email_address_and_no_secret_and_the_display_name_present(self, named):
        an_incident()
        got = hand_over(note=NOTE)
        text = everything(got)
        assert NAME in text
        assert ACTOR not in text and "@" not in text
        assert COMMUNITY not in text
        with open(H.path(inc(), 1), encoding="utf-8") as fh:
            stored = fh.read()
        assert ACTOR not in stored and COMMUNITY not in stored and NAME in stored

    def test_with_nothing_tried_nothing_asked_and_no_diagnosis_it_says_so(self, lab):  # noqa
        got = hand_over()
        s = {x["key"]: x["lines"] for x in got["doc"]["sections"]}
        assert s["summary"] == ["r2: telemetry subscription 101 and 102 lost; no fix tried; "
                                "not fixed."]
        assert s["known"] == ["Mercury has not diagnosed this incident."]
        assert s["tried"] == ["Nothing was tried."] and s["ai"] == ["No AI was asked."]
        assert s["notes"] == ["No note was given."]
        assert s["cost"] == ["Total $0.00 in this incident. The provider bills, not Mercury."]

    def test_markdown_holds_every_section_in_order(self, lab):  # noqa: F811
        md = hand_over()["doc"]["markdown"]
        assert md.startswith(f"# Hand-over 1: {inc().id} on r2\n")
        at = [md.index(f"## {title}\n") for _k, title in H.SECTIONS]
        assert at == sorted(at) and len(at) == 9


# ── Versions are kept ───────────────────────────────────────────────────────────────────────

class TestVersions:
    def test_each_hand_over_is_a_new_version_and_the_first_is_never_written_over(self, lab):  # noqa
        one = hand_over(note="first", now=LATER)
        with open(H.path(inc(), 1), "rb") as fh:
            first = fh.read()
        two = hand_over(note="second", now=LATER + 60)
        assert (one["version"], two["version"]) == (1, 2)
        with open(H.path(inc(), 1), "rb") as fh:
            assert fh.read() == first
        got = H.versions(inc())
        assert [(v["version"], v["by"], v["kept"]) for v in got["versions"]] == [
            (1, "op", "ok"), (2, "op", "ok")]
        assert "Hand-over note: second" in H.read_version(inc(), 2)["doc"]["markdown"]

    def test_a_version_already_kept_is_refused_and_preserved(self, lab):  # noqa: F811
        os.makedirs(H.folder(inc()))
        with open(H.path(inc(), 1), "w", encoding="utf-8") as fh:
            fh.write('{"planted": true}')
        with pytest.raises(H.Refused, match="hand-over 1 is already kept, and a write-up is "
                                            "never written over"):
            hand_over()
        with open(H.path(inc(), 1), encoding="utf-8") as fh:
            assert fh.read() == '{"planted": true}'
        assert any(n.startswith("1.json.corrupt-") for n in os.listdir(H.folder(inc())))
        assert [v["kept"] for v in H.versions(inc())["versions"]] == ["unreadable"]

    def test_the_store_masks_what_it_is_handed_whoever_built_it(self, lab):  # noqa: F811
        """Masked at rest by the store itself, not only by the builder: a write-up handed in
        holding a secret is kept without it."""
        H._keep(inc(), 7, {"version": 7, "incident": inc().id,
                           "sections": [{"key": "notes", "title": "Notes",
                                         "lines": [f"snmp-server community {COMMUNITY} RO"]}]})
        with open(H.path(inc(), 7), encoding="utf-8") as fh:
            kept = fh.read()
        assert COMMUNITY not in kept and "snmp-server community <redacted" in kept
        assert H.read_version(inc(), 7)["state"] == "ok"

    def test_a_read_creates_nothing_and_says_absent_and_unreadable_apart(self, lab):  # noqa
        assert H.read_version(inc(), 3) == {"state": "absent", "doc": None, "error": ""}
        assert not os.path.exists(H.folder(inc()))
        assert H.versions(inc()) == {"state": "ok", "versions": [], "error": ""}
        with pytest.raises(H.Refused, match="a whole number from 1"):
            H.read_version(inc(), 0)

    def test_an_unverified_request_keeps_nothing(self, lab):  # noqa: F811
        with pytest.raises(F.NotAPerson):
            hand_over(actor_verified="none")
        assert F.read(inc())["state"] == "absent" and not os.path.exists(H.folder(inc()))


# ── The relay event and the team chosen ─────────────────────────────────────────────────────

class TestTheRelay:
    def test_the_team_chosen_is_recorded_and_told_with_the_pages_link(self, named):
        team = a_team()
        relay = Relay()
        got = hand_over(team_ids=[team], note=NOTE, deliver=relay)
        assert got["sent"] == {"ok": True, "sent": 1, "failed": 0, "nobody": False,
                               "error": "", "words": "Sent"}
        (event, ids), = relay.sent
        assert ids == [team]
        assert (event["event"], event["incident"], event["link"]) == (
            "fixit_handover", inc().id, f"/v2/incident/{inc().id}?list={NET}")
        assert event["outcome"].startswith(f"Handed over by {NAME} at 2026-11-09 20:46 UTC "
                                           "(version 1).")
        blob = json.dumps(event)
        assert ACTOR not in blob and "@" not in blob and COMMUNITY not in blob
        (line,) = [ln for ln in F.read(inc())["lines"] if ln.get("choice") == "handover"]
        assert (line["teams"], line["version"]) == (["Network team"], 1)
        assert got["doc"]["teams"] == ["Network team"]

    def test_with_no_team_chosen_nothing_is_sent_and_it_is_kept(self, lab):  # noqa: F811
        a_team()
        relay = Relay()
        got = hand_over(deliver=relay)
        assert relay.sent == []
        assert got["sent"]["nobody"] is True and got["sent"]["words"] == (
            "Kept; no team was chosen, so no team is told about this hand-over")
        assert H.read_version(inc(), 1)["state"] == "ok"

    def test_a_team_not_told_about_cant_fix_is_refused_with_nothing_kept(self, lab):  # noqa
        told = a_team()
        other = a_team("Facilities", told=False)
        relay = Relay()
        with pytest.raises(H.Refused) as e:
            hand_over(team_ids=[other], deliver=relay)
        assert str(e.value) == (
            f"a hand-over goes to the teams told about {NET}'s can't-fix, and team {other} is "
            "not one of them (they are Network team): nothing was kept or sent")
        assert relay.sent == [] and F.read(inc())["state"] == "absent"
        assert H.offered(NET)["teams"] == [{"id": told, "name": "Network team"}]

    def test_the_real_relay_with_no_destination_sends_nothing_and_says_so(self, lab):  # noqa
        team = a_team()
        got = hand_over(team_ids=[team])
        assert (got["sent"]["ok"], got["sent"]["sent"]) == (True, 0)
        assert got["sent"]["words"] == ("Kept; the teams chosen have no destination that is "
                                        "verified and on, so nothing was sent")

    def test_a_relay_failure_is_said_and_the_write_up_kept_for_send_again(self, lab):  # noqa
        team = a_team()
        down = Relay({"ok": False, "sent": 0, "failed": 1, "deliveries": [],
                      "error": "the relay did not answer"})
        got = hand_over(team_ids=[team], deliver=down)
        assert got["sent"]["words"] == "Kept, not sent: the relay did not answer"
        again = Relay()
        assert H.send(inc(), 1, [team], deliver=again)["words"] == "Sent"
        assert len(again.sent) == 1

    def test_a_version_not_kept_is_never_sent(self, lab):  # noqa: F811
        relay = Relay()
        got = H.send(inc(), 4, ["0123456789ab"], deliver=relay)
        assert got["ok"] is False and got["words"] == "Not sent: the write-up to send is not kept"
        assert relay.sent == []

    def test_the_link_is_the_incident_pages_own_route(self):
        import app as A
        path, _q, query = H.page(inc()).partition("?")
        endpoint, args = A.app.url_map.bind("localhost").match(path)
        assert (endpoint, args, query) == ("incident_v2.incident",
                                           {"incident_id": inc().id}, f"list={NET}")

    def test_the_event_is_one_the_notifier_knows(self):
        from modules.notify import message
        assert message.EVENTS[H.EVENT] == "an incident handed over to an engineer"
        assert len(H.EVENT) <= message.FIELDS["event"]
