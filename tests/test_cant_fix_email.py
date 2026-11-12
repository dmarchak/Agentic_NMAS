"""Lab 10 objective 2, end to end: a can't-fix tells an engineer the steps taken. The
operator's order, 2026-11-12 (overnight item 4): "Objective 2 (couldn't fix → notify an
engineer with the steps taken): verify end to end with stand-ins that the can't-fix email lists
the steps taken in plain words, with local times and display names, and links to the incident.
Fix any gaps."

Through the real code with stand-ins only: the real decision (`decide.run`) and the real act
(`act.act_one`, over tests/test_heal_act.py's fakes) writing the real step log, a captured
record (tests/fixtures/heal_run/rolled_back.json, an act row as the NMAS host wrote it, its
words naming the policy's setter by identity), the real notifier (`heal_notice.notice`: its
diagnosis, analysis and delivery), the real Who is told, teams, relay and egress mask; the mail
transport is tests/test_notify.py's capturing SMTP class and the AI provider a fake answer. No
device, no network, no real mail.

Each email is read as received (its decoded text) and holds:

- (a) "What Mercury tried:" lists every step the incident's record holds, in the record's
  order, each as THE stepper says it (its operation's short label: `decide.STEP_LABELS`,
  `act.STEP_LABELS`) with its result in words; no code key (``cant_fix``, ``d-claim``), no raw
  id outside "Incident <id>" and the link;
- (b) every time local, in the installation's zone (the host's own, pinned here to a zone that
  is not UTC), the zone named once; a time across a daylight-saving change says its own zone;
- (c) each person by display name (one set, so the record's default cannot pass for it), never
  an identity; and the AI payload names nobody by identity either;
- (d) "Open in Mercury" is the incident's absolute address (`incidents.incident_href`, behind
  `notify_link_base`), and that page opens the incident's card.
"""
import email.utils
import json
import os
import re
import time

import pytest

from tests.test_heal_analysis import T0, cant_fix, turn_on
from tests.test_heal_analysis import ai, lab, networks  # noqa: F401 (the fixtures)
from tests.test_notify import _mail, _relay, _team_with_email
from tests.test_notify import env  # noqa: F401 (the fixture)

NET, HOST = "Default", "edge-b"
BASE = "https://mercury.example.net"
#: The policy's setter in the heal lab (tests/test_heal_policy.py `PERSON`), and the display
#: name they set: a test person, never a real one.
SETTER, SETTER_NAME = "admin@example.com", "Avery Admin"
#: The person who saved Who is told: named nowhere in a message.
SAVER = "alex@example.com"
#: A zone that is not UTC and has no daylight saving, as POSIX states it (no zone database
#: needed): India's, 5 h 30 min east of UTC.
ZONE, ZONE_OFFSET_S, ZONE_WORDS = "IST-5:30", 19800, "IST (UTC+05:30)"
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "heal_run", "rolled_back.json")
#: A step's result, as the stepper says it in words (`run_stepper.STATE_WORDS`' ended states),
#: and a step a later record of itself ends (`steplog.finished_steps`).
PLAIN_RESULTS = ("done", "failed", "not fully done", "not needed in this run",
                 "ended: its outcome is its later line")
_ID = re.compile(r"\bh[id]-[0-9a-f]{12}\b")
_CODE_KEY = re.compile(r"\b[a-z]+_[a-z_]+\b|\b[dax]-[a-z]+\b")


@pytest.fixture
def zone():
    """The installation's zone pinned for the test (the host's own: TZ), put back after."""
    was = os.environ.get("TZ")

    def pin(tz):
        os.environ["TZ"] = tz
        time.tzset()
    pin(ZONE)
    yield pin
    if was is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = was
    time.tzset()


@pytest.fixture
def told(ai, env, zone, monkeypatch):  # noqa: F811
    """The relay, a verified team told about can't-fix on Default, the address Mercury is
    reached by, and the setter's display name; ``told(incident)`` runs the real notice and
    returns the email as received."""
    from modules import config, display_names, heal_notice, heal_notify

    monkeypatch.setattr(config, "DATA_DIR", str(ai.dir))
    _relay(env)
    env.settings["notify_link_base"] = BASE
    team, _dest = _team_with_email()
    assert heal_notify.save(NET, team, ["cant_fix"], actor=SAVER,
                            loaded=heal_notify.drawn(heal_notify.read(NET)))["ok"]
    display_names.set_name(SETTER, SETTER_NAME, by=SETTER, actor_verified="access",
                           admin=True)
    turn_on()

    def run(incident, now):
        heal_notice.notice(NET, incident, send=ai.send, wait_s=10, follow_s=0, now=now)
        (raw,) = [r for s in env.smtp for r in s.sent]
        return _mail(raw)
    return run


def _decided_heal(running):
    """A heal decided by the real decision in AUTO (`decide.run`), in the step log: its id."""
    from tests.test_heal_decide import Fake, settle
    from tests.test_heal_policy import auto
    from modules.heal import decide

    auto(NET, now=T0 - 60, kinds=("added_line",))
    settle(running, claim=False)
    (d,) = decide.run(NET, now=T0, sources=Fake(running))["decided"]
    assert d["outcome"] == "heal", d
    return d


def rolled_back_by_the_act():
    """A heal the real act rolled back: the read after the change still holds the route."""
    from modules.heal import act
    from tests.test_heal_act import FakeAct, K
    from tests.test_heal_decide import GOLDEN, ROUTE4

    d = _decided_heal(GOLDEN + ROUTE4)
    got = act.act_one(NET, d["decision"], now=T0 + 5,
                      sources=FakeAct(GOLDEN + ROUTE4, post=K._stored(GOLDEN + ROUTE4)))
    assert got["outcome"] == "rolled_back", got["words"]
    return d["incident"]


def rolled_back_as_captured():
    """The captured act record (as the NMAS host wrote it, its words naming the setter by
    identity) written by the step log's own writer for a real decision."""
    from modules.heal import decisions, steplog
    from tests.test_heal_decide import GOLDEN, ROUTE4

    d = _decided_heal(GOLDEN + ROUTE4)
    with open(FIXTURE, encoding="utf-8") as fh:
        result = json.load(fh)
    assert any(SETTER in s.get("words", "") for s in result["steps"]), "the fixture's premise"
    steplog.record_act(NET, decisions.find(NET, d["decision"]), result,
                       by=f"heal to intent (policy set by {SETTER})", policy_by=SETTER,
                       now=T0 + 5)
    return d["incident"]


def _local(epoch, day=True):
    """*epoch* in the pinned zone, computed apart from the product: UTC plus its offset."""
    return time.strftime("%Y-%m-%d %H:%M" if day else "%H:%M",
                         time.gmtime(epoch + ZONE_OFFSET_S))


def _epoch(iso):
    import calendar
    return calendar.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))


def recorded_steps(incident):
    """Every step the incident's record holds, in order, as the stepper labels it (from the
    operations' own tables, never the notice's), with when it was recorded."""
    from modules.heal import act, decide, steplog

    out = []
    for r in steplog.read(NET)["rows"]:
        if r.get("incident") != incident or r.get("row") not in ("decision", "act"):
            continue
        labels = decide.STEP_LABELS if r["row"] == "decision" else act.STEP_LABELS
        for s in r.get("steps") or []:
            out.append((labels[s["step"]].format(device=HOST), s.get("at") or r["at"]))
    return out


def tried(text):
    """The lines under "What Mercury tried:", up to the next field."""
    lines = text.splitlines()
    start = lines.index("What Mercury tried:") + 1
    out = []
    for line in lines[start:]:
        if not line.startswith("  - "):
            break
        out.append(line)
    return out


def check_email(mail, incident, client):
    text = mail.get_content().replace("\r\n", "\n")   # as a mail reader shows its lines
    # The subject, unchanged.
    assert mail["Subject"] == f"[Mercury] {HOST} on {NET}: could not fix"
    # (a) Every step taken, in order, in plain words.
    want = recorded_steps(incident)
    got = tried(text)
    assert len(got) == len(want) > 3, (got, want)
    for line, (label, at) in zip(got, want):
        assert line.startswith(f"  - {_local(_epoch(at), day=False)} {label}"), (line, label)
        assert line.endswith(tuple(f": {r}" for r in PLAIN_RESULTS)), line
        assert not _CODE_KEY.search(line.split(": ", 1)[0]), line
    assert not [w for w in _CODE_KEY.findall("\n".join(got))
                if w in ("cant_fix", "rolled_back", "symptom_remains", "would_heal")], got
    assert not re.search(r"step \d+'s", "\n".join(got)), "no step named by a number not drawn"
    body = text.split("\nOpen in Mercury:")[0]
    assert not _ID.search(body), "no raw id before the link and the incident's own line"
    # (b) Every time local, the zone named once.
    assert text.count(ZONE_WORDS) == 1 and text.rstrip().endswith(
        f"Times are in {ZONE_WORDS}, the time zone of the host Mercury runs on.")
    assert not re.search(r"\d{2}:\d{2}(:\d{2})? UTC|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text), text
    sent = email.utils.parsedate_to_datetime(mail["Date"]).timestamp()
    assert any(f"Incident {incident} · sent {_local(s)}\n" in text for s in (sent, sent - 60))
    # (c) People by display name, never by identity.
    from modules import display_names
    assert not display_names.EMAIL.search(text), text
    # (d) The incident's absolute address, and the incident's card at it.
    path = f"/v2/device/{HOST}?list={NET}&tab=history&result={incident}"
    assert f"\nOpen in Mercury: {BASE}{path}\n" in text
    page = client.get(path).get_data(as_text=True)
    assert 'id="device-op"' in page and f"Self-healing on {HOST}" in page, \
        "the link opens the incident's card"
    return text


@pytest.fixture
def client(monkeypatch):
    """The app with edge-b on Default's page (tests/test_run_outcomes.py's `heal`)."""
    import app as A
    from tests.conftest import TEST_PERSON

    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [
        {"hostname": HOST, "ip": "192.0.2.6", "device_type": "cisco_xe"}])
    monkeypatch.setattr("modules.integration_groups.network_names", lambda: [NET])
    monkeypatch.setattr("routes.operations.viewer_key", lambda: TEST_PERSON)
    A.app.config["TESTING"] = True
    return A.app.test_client()


class TestTheCantFixEmail:
    def test_a_decision_that_could_not_fix_says_its_steps_times_and_link(self, told, client,
                                                                           ai):
        inc = cant_fix()                  # the real decision: a security ACL, Tier 2
        text = check_email(told(inc, T0 + 1), inc, client)
        assert f"Detected: CONFIG_I at {_local(T0 - 1000)}\n" in text, "detected, local"
        assert f"At {_local(T0 - 1000, day=False)}, {HOST}'s configuration" in text, \
            "what happened, its recorded UTC time said locally"
        card = client.get(f"/v2/device/{HOST}?list={NET}&tab=history&result={inc}").get_data(
            as_text=True)
        assert 'data-outcome="cant_fix"' in card and 'data-stage="decided"' in card
        assert 'data-stage="fixing"' not in card, "a can't-fix ran nothing: no act is drawn"

    def test_a_heal_the_act_rolled_back_names_the_setter_by_display_name(self, told, client,
                                                                          ai):
        inc = rolled_back_by_the_act()
        text = check_email(told(inc, T0 + 6), inc, client)
        assert f"policy set by {SETTER_NAME}" in text
        assert "running" not in "\n".join(tried(text)), "a finished record runs nothing"
        # The act's words name the setter by display name as it records them: the AI is
        # sent a stable label in that name's place.
        from modules import display_names
        sent = json.dumps(ai.sent)
        assert ai.sent and SETTER_NAME not in sent and display_names.label(SETTER) in sent

    def test_the_captured_record_names_nobody_by_identity_to_the_reader_or_the_ai(
            self, told, client, ai):
        inc = rolled_back_as_captured()
        text = check_email(told(inc, T0 + 6), inc, client)
        assert f"policy set by {SETTER_NAME}" in text
        # The record's apply, written running when it sent and ended by its later record
        # (C3173's shape, `steplog.finished_steps`): said as ended, never running or done.
        assert f" Apply: as the policy set by {SETTER_NAME}, holding {HOST}: ended: its " \
               "outcome is its later line" in text
        assert ai.sent, "the analysis ran"
        from modules import display_names
        sent = json.dumps(ai.sent)
        assert not display_names.EMAIL.search(sent), "no identity in the AI payload"
        assert SETTER_NAME not in sent and SETTER.split("@")[0] not in sent.lower(), \
            "nor a person's name: a stable label"
        # The webhook's JSON, built from the same facts, names the setter as the email does.
        from modules import heal_notice
        from modules.heal import steplog
        from modules.notify import message
        hook = json.dumps(message.payload(message.check_event(
            heal_notice.facts(NET, steplog.incident(NET, inc)))))
        assert not display_names.EMAIL.search(hook) and SETTER_NAME in hook

    def test_more_steps_than_a_message_carries_end_in_how_many_more(self, told):
        from modules import heal_notice
        from modules.notify import message

        entry = {"incident": "hi-000000000003", "state": "decided", "steps": [
            {"step": "read", "result": "ok", "row": "decision", "words": f"read {n}",
             "at": "2026-09-21T13:57:00Z"} for n in range(25)]}
        steps = heal_notice.steps_said(NET, HOST, entry, [])
        room = message.FIELDS["steps"]
        assert len(steps) == room and steps[-1]["said"] == f"{25 - room + 1} more steps"
        assert [s["said"] for s in steps[:3]] == [f"Read {HOST}: read {n}" for n in range(3)]

    def test_the_ai_s_record_of_what_was_tried_labels_every_person(self, told):
        """The pack's tried section, the part of the AI payload a record's words reach: an
        identity in a step's words or the outcome's, and the setter's display name where the
        act wrote it, each its stable label."""
        from modules import display_names
        from modules import evidence_pack as EP

        entry = {"incident": "hi-000000000002", "policy_by": SETTER, "outcome": "rolled_back",
                 "words": f"rolled back; reported to {SAVER}",
                 "steps": [{"step": "take", "result": "ok", "row": "act",
                            "words": f"taken by heal to intent (policy set by {SETTER})"},
                           {"step": "apply", "result": "failed", "row": "act",
                            "words": f"as the policy set by {SETTER_NAME}, holding {HOST}"}]}
        got = json.dumps(EP.tried_section(entry, [], T0))
        assert not display_names.EMAIL.search(got) and SETTER_NAME not in got, got
        assert got.count(display_names.label(SETTER)) == 2 and display_names.label(SAVER) in got
        assert display_names.label(SETTER) != display_names.label(SAVER), "one label a person"

    def test_a_time_across_a_daylight_saving_change_says_its_own_zone(self, zone):
        from modules.notify import message
        zone("EST5EDT,M3.2.0,M11.1.0")
        facts = message.check_event({
            "incident": "hi-000000000001", "event": "cant_fix", "network": NET,
            "device": HOST, "detected": "seen", "detected_at": "2026-09-21T13:56:40Z",
            "steps": [{"what": "read: x", "said": "Read edge-b: read at 13:57 UTC",
                       "result": "done", "at": "2026-09-21T13:57:00Z"}]})
        text = message.text(facts, sent_at=_epoch("2026-11-12T08:00:00Z"))
        assert "Detected: seen at 2026-09-21 09:56 EDT (UTC-04:00)\n" in text
        assert "  - 09:57 EDT (UTC-04:00) Read edge-b: read at 09:57 EDT (UTC-04:00): done" \
            in text
        assert "sent 2026-11-12 03:00\n" in text and text.count("EST (UTC-05:00)") == 1
