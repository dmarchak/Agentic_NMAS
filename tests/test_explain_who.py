"""WHO, guaranteed in code (the operator's order of 2026-10-29): modules/ai/who.py, the fact
sheet's "Changes and actions in the window" line (modules/ai/fact_sheet.py, `changes_line`),
Explain's who on each hypothesis (modules/ai/explain.py, `_checked`), the grader as kept
(modules/ai/cases.py, `guarded`), the intent difference's lines and last commit in the pack
(modules/evidence_pack.py, `intent_lines`, `intent_commit`), and the card
(templates/v2/_explain.html, templates/v2/_evidence_pack.html).

**Why:** an answer could say "a configuration change preceded the drop" and never say who made
it, though the pack held the receipt, the commit or the device's own log line naming them; and
the pack carried the Intent check's state but never its lines, so the model could not judge
whether a difference could explain the alert.

**The properties:**
- (a) a fact-sheet line, computed by Mercury from the pack as sent: each Mercury receipt or
  record in the window (action, actor and how established, time, id), each configuration-change
  log line with the user and source it names (IPv4 and IPv6), the Intent check's difference
  with its intent file's last commit; "no record of who" where none exists; masked; labelled;
- (b) a hypothesis that cites a change or an action (by what it cites, never by its words)
  carries who made it; one whose claim does not name them has them added by Mercury, kept
  apart (``mercury_who``) and drawn as Mercury's; the model's response untouched in the call's
  record; the grader grades raw and as kept, and on the recorded answers no grade moves;
- (c) the intent difference's lines in the pack, masked as what leaves the host is masked: a
  secret planted in a line reaches the stored pack and the bytes sent only as its shape.

The log lines are real captures (tests/fixtures/loki/lines_s3.json, its `<user>` the
publication placeholder for the account; the console capture
tests/fixtures/console/s5-kickstart-take-copy-echo.txt line 97 and 99, rejoined across the
echo that split it), each edit said where it is made; the CONFIG_P and DMI forms are Cisco's
documented message formats, not captures (none is in the fixtures).
"""
import copy
import json
import os
import re
import subprocess
from html import unescape

import pytest

from modules import evidence_pack as EP
from modules.ai import calls, cases, explain, fact_sheet, who
from tests.test_ai_explain import _answer, _explain, world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import _alerts, _build, _section, pack_lab  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fixture(*parts):
    with open(os.path.join(ROOT, "tests", "fixtures", *parts), encoding="utf-8") as fh:
        return json.load(fh)


WALK = _fixture("evidence_pack", "walk2_r1_pack.json")
RECORDED = _fixture("ai_cases", "explain", "recorded.json")
#: The two CONFIG_I lines of the s3 capture, as Loki returned them.
CAPTURED = [v for s in _fixture("loki", "lines_s3.json")["answer"]["data"]["result"]
            for _t, v in s["values"] if "%SYS-5-CONFIG_I" in v]
VTY0 = next(x for x in CAPTURED if "on vty0" in x)
#: The console capture, rejoined (its `%` and the rest were split by an echoed command).
CONSOLE = "*Oct 23 22:04:04.083: %SYS-5-CONFIG_I: Configured from console by console"
PROGRAMMATIC = ("%SYS-5-CONFIG_P: Configured programmatically by process SEP_webui_wsma_http "
                "from console as admin on vty0")
NETCONF = ("%DMI-5-CONFIG_I: R0/0: nesd: Configured from NETCONF/RESTCONF by admin, "
           "transaction-id 21")


# ── the configuration-change line: its user and source ───────────────────────────────────

def test_the_captures_hold_the_shapes_tested():
    assert len(CAPTURED) == 2, "the floor: the capture's two CONFIG_I lines"
    assert {re.search(r"on (vty\d)", x).group(1) for x in CAPTURED} == {"vty0", "vty2"}


@pytest.mark.parametrize("text,want", [
    (VTY0, {"user": "<user>", "line": "vty0", "address": "192.0.2.1", "source": "console"}),
    # Edit: the capture's address made IPv6 (the rule's IPv6 case beside its IPv4 one).
    (VTY0.replace("(192.0.2.1)", "(2001:db8::1)"),
     {"user": "<user>", "line": "vty0", "address": "2001:db8::1", "source": "console"}),
    # Edit: no AAA user, the line where the user stands (IOS without login local).
    (VTY0.replace("by <user> on vty0", "by vty0"),
     {"user": "", "line": "vty0", "address": "192.0.2.1", "source": "console"}),
    (CONSOLE, {"user": "", "line": "console", "address": "", "source": "console"}),
    (PROGRAMMATIC, {"user": "admin", "line": "vty0", "address": "", "source": "console",
                    "process": "SEP_webui_wsma_http"}),
    (NETCONF, {"user": "admin", "line": "", "address": "", "source": "NETCONF/RESTCONF"}),
])
def test_a_configuration_change_names_its_user_line_and_address(text, want):
    got = who.config_change(text)
    assert {k: got[k] for k in want} == want, got


@pytest.mark.parametrize("text", [
    "%SYS-5-RELOAD: Reload requested by admin on vty0 (192.0.2.5). Reload Reason: test.",
    "*Oct  5 20:56:38.522 UTC: %GRUB-5-CONFIG_WRITTEN: GRUB configuration was written to disk",
    "%LINK-3-UPDOWN: Interface GigabitEthernet3, changed state to down", ""])
def test_a_line_that_is_no_configuration_change_is_none(text):
    assert who.config_change(text) is None


# ── what a change or an action is: by what the piece is ──────────────────────────────────

def _hist(n, kind, who_="operator@example.com", at="2026-10-26T11:52:00Z", **extra):
    return dict({"ref": f"history:{n}", "at": at, "kind": kind, "what": f"a {kind}",
                 "who": who_, "outcome": "", "sha": f"{n:012x}", "detail": ""}, **extra)


@pytest.mark.parametrize("kind", who.ACTION_KINDS)
def test_each_action_kind_is_a_change_with_its_actor_and_how(kind):
    c = who.change_of("history", _hist(1, kind, verified="access"))
    assert c["who"] == "operator@example.com"
    assert c["words"] == "operator@example.com (verified sign-in)"
    assert who.change_of("history", _hist(1, kind))["words"] == "operator@example.com"
    assert who.change_of("history", _hist(1, kind, who_=""))["words"] == who.NO_RECORD


def test_a_restart_or_another_section_s_piece_is_no_change():
    assert who.change_of("history", _hist(1, "restart")) == {}
    assert who.change_of("health", {"ref": "health:x:cpu"}) == {}
    assert who.change_of("intent", {"ref": "intent:1", "state": "match"}) == {}


def test_an_intent_difference_s_actor_is_its_last_commit_s():
    piece = {"ref": "intent:1", "state": "differs", "lines": [],
             "intent_commit": {"state": "ok", "sha": "64f190c68307", "actor": "t",
                               "verified": "host-shell", "at": "2026-10-22T00:28:43+00:00"}}
    assert who.change_of("intent", piece)["words"] == (
        "intent last committed by t (host login, not verified)")
    older = {"ref": "intent:1", "state": "differs"}
    assert who.change_of("intent", older)["words"] == who.NO_RECORD


# ── (a) the fact sheet's line ────────────────────────────────────────────────────────────

FROM, TO = "2026-10-26T11:35:00Z", "2026-10-26T12:00:00Z"
SAME = "username admin privilege 15 secret 9 <redacted:user_password>"


def _changes_pack():
    """A real-shaped pack: a deploy's receipt and a window in the window (one with no actor),
    a golden recorded the day before, two configuration-change lines (the capture's IPv4 one,
    and its IPv6 one naming only its line), and an intent difference whose one line differs
    only in its masked secret, its intent last committed by a verified person."""
    sec = lambda name, pieces, **x: dict({"ref": name, "name": name, "state": "ok",  # noqa: E731
                                          "source": f"the {name} source", "why": "",
                                          "pieces": pieces}, **x)
    sections = [
        sec("alert", [{"ref": "alert:1", "kind": "condition", "state": "Alerting",
                       "labels": {"device": "edge1"}}]),
        sec("history", [
            _hist(1, "receipt", at="2026-10-26T11:48:10Z", verified="access",
                  what="Interface description sent: deployed"),
            _hist(2, "window", who_="", at="2026-10-26T11:40:00Z",
                  what="Planned-restart window declared"),
            _hist(3, "restart", at="2026-10-26T11:41:00Z", what="Restarted as planned"),
            _hist(4, "golden", at="2026-10-25T06:35:36+00:00", verified="none",
                  what="Golden recorded (save_all)")]),
        sec("intent", [{"ref": "intent:1", "state": "differs", "adds": 1, "removes": 1,
                        "reordered": 0, "words": "+1 -1", "lines": [f"+ {SAME}", f"- {SAME}"],
                        "intent_commit": {"state": "ok", "sha": "64f190c68307",
                                          "at": "2026-10-22T00:28:43+00:00",
                                          "actor": "operator@example.com",
                                          "verified": "access"}}]),
        sec("health", [], window={"from": FROM, "to": TO}),
        sec("logs", [
            {"ref": "logs:1", "at": "2026-10-26T11:49:02Z", "device": "edge1", "text": VTY0},
            {"ref": "logs:2", "at": "2026-10-26T11:50:30Z", "device": "edge1",
             "text": VTY0.replace("by <user> on vty0 (192.0.2.1)", "by vty0 (2001:db8::1)")},
            {"ref": "logs:3", "at": "2026-10-26T11:51:00Z", "device": "edge1",
             "text": "%LINK-3-UPDOWN: Interface GigabitEthernet3.10, changed state to down"}])]
    return {"device": "edge1", "rule": "Interface down", "onset": "2026-10-26T11:50:00Z",
            "built_at": TO, "schema": 7, "sections": sections}


#: The line on `_changes_pack`, word for word: what the operator reads in the report.
WANT = (
    "Changes and actions in the window (computed by Mercury): "
    "2026-10-26T11:40:00Z: Planned-restart window declared by no record of who [history:2], "
    "record 000000000002; "
    "2026-10-26T11:48:10Z: Interface description sent: deployed by operator@example.com "
    "(verified sign-in) [history:1], record 000000000001; "
    "2026-10-26T11:49:02Z: edge1 logged a configuration change from console, by <user> on vty0 "
    "from 192.0.2.1, the device's account as its log line names it [logs:1]; "
    "2026-10-26T11:50:30Z: edge1 logged a configuration change from console, by no record of "
    "who (the log line names only the line vty0 and the address 2001:db8::1) [logs:2]; "
    "before the window, History holds 1 more, the newest 2026-10-25T06:35:36+00:00: Golden "
    "recorded (save_all) by operator@example.com (not verified) [history:4], record "
    "000000000004; "
    "the Intent check differs [intent:1]: 1 line(s) in intent and not on the device (+), 1 on "
    "the device and not in intent (-), 0 section(s) reordered; 2 of the lines are in the pack, "
    "masked; 1 differ only in a masked value, the same line on both sides (" + SAME + "); "
    "intent last committed 2026-10-22T00:28:43+00:00 by operator@example.com (verified "
    "sign-in), commit 64f190c68307.")


def test_the_line_names_each_change_its_actor_its_time_and_its_id():
    pack = _changes_pack()
    assert fact_sheet.changes_line(pack, pack["sections"]) == WANT


def test_only_a_line_on_both_sides_differing_in_its_masked_value_is_quoted():
    """The sheet quotes no intent line but a pair, the same shape in intent and on the device,
    a masked value between them (the lines themselves ride in the pack's intent piece): an
    unpaired line, a masked one included, is counted, never quoted."""
    pack = _changes_pack()
    piece = pack["sections"][2]["pieces"][0]
    piece["lines"] += ["+ ntp server 192.0.2.250", "- ntp server 2001:db8::250",
                       "+ snmp-server community <redacted:snmp_community> RO"]
    line = fact_sheet.changes_line(pack, pack["sections"])
    assert ("5 of the lines are in the pack, masked; 1 differ only in a masked value, the same "
            f"line on both sides ({SAME}); intent last committed") in line
    assert "ntp server" not in line and "snmp-server community" not in line


def test_the_line_is_in_the_sheet_after_the_reloads_masked_and_labelled(monkeypatch):
    from modules import redact
    pack = _changes_pack()
    # A secret planted where a user stands in a log line (a value the store knows).
    pack["sections"][4]["pieces"][0]["text"] = VTY0.replace("<user>", "Pl4ntedKnownValue9")
    monkeypatch.setattr(redact, "known_secret_values",
                        lambda: {"Pl4ntedKnownValue9": "Lab:planted"})
    lines = fact_sheet.sheet(pack, pack["sections"]).split("\n")
    assert fact_sheet.LINES.index("changes") == fact_sheet.LINES.index("reloads") + 1
    assert lines[3].startswith("Changes and actions in the window (computed by Mercury): ")
    assert lines[2].startswith("Reloads in the window")
    assert "Pl4ntedKnownValue9" not in "\n".join(lines) and "<redacted:" in lines[3]


def test_none_in_the_window_is_said_with_what_was_read():
    pack = _changes_pack()
    pack["sections"][1]["pieces"] = [_hist(3, "restart", at="2026-10-26T11:41:00Z")]
    pack["sections"][2]["pieces"][0]["state"] = "match"
    pack["sections"][4]["pieces"] = pack["sections"][4]["pieces"][2:]
    assert fact_sheet.changes_line(pack, pack["sections"]) == (
        "Changes and actions in the window (computed by Mercury): none between "
        "2026-10-26T11:35:00Z and 2026-10-26T12:00:00Z: no Mercury receipt or record in "
        "History, and no configuration-change line (%SYS-5-CONFIG_I) among the pack's 1 log "
        "line.")


def test_a_source_not_read_and_an_older_pack_s_intent_are_said():
    pack = _changes_pack()
    pack["sections"][1] = dict(pack["sections"][1], state="unreadable", pieces=[])
    pack["sections"][4] = dict(pack["sections"][4], state="unreadable", pieces=[])
    piece = pack["sections"][2]["pieces"][0]
    del piece["lines"], piece["intent_commit"]
    line = fact_sheet.changes_line(pack, pack["sections"])
    assert "History was not read (unreadable), so no receipt or record is known" in line
    assert "the log lines were not read (unreadable)" in line
    assert ("This pack (older than schema 7) holds neither the lines nor who committed the "
            "intent: no record of who") in line


def test_the_captured_walk_pack_s_line():
    """Walk 2's pack (schema 5): its History's receipt, intent commit and goldens are before
    the window, the newest three named; no configuration line; the intent matches."""
    sent = explain.sent_sections(WALK, {"sent": False})
    line = fact_sheet.changes_line(WALK, sent)
    assert line.startswith("Changes and actions in the window (computed by Mercury): none "
                           "between 2026-10-22T17:44:50Z and 2026-10-22T18:01:50Z")
    assert "before the window, History holds" in line and "[history:2]" in line
    assert "Intent check" not in line


# ── (c) the intent difference's lines in the pack, masked ────────────────────────────────

USER_SECRET = "Pl4ntedUserPass"
COMMUNITY = "Pl4ntedC0mm"
HASH = "$9$Pl4ntedHashValue/abc"
LATE = "Pl4ntedLateValue99"
RAW = [f"+ username admin privilege 15 secret 0 {USER_SECRET}",
       f"- snmp-server community {COMMUNITY} RO",
       f"+ alias exec planted {HASH}",
       f"+ description uplink {LATE}",
       "- ntp server 2001:db8::250", "+ ntp server 192.0.2.250"]


def _differs(monkeypatch, lines=RAW):
    """The comparison as if its own mask had failed (`intent_match` masks its lines; this
    returns them in clear), so what keeps a value out is the pack's own mask."""
    from modules.nsot import intent_match as IM
    monkeypatch.setattr(IM, "intent_match", lambda *a, **k: {
        "state": "differs", "adds": 4, "removes": 2, "reordered": 0, "lines": list(lines),
        "why": ""})


def test_a_secret_in_an_intent_line_is_kept_as_its_shape(pack_lab, monkeypatch):  # noqa: F811
    _differs(monkeypatch)
    pack = _build(_alerts(heartbeat=True))
    (st,) = _section(pack, "intent")["pieces"]
    text = json.dumps(pack)
    for value in (USER_SECRET, COMMUNITY, HASH):
        assert value not in text, value
    assert st["lines"][0].startswith("+ username admin privilege 15 secret 0 <redacted:")
    assert st["lines"][1].startswith("- snmp-server community <redacted:") and \
        st["lines"][1].endswith(" RO")
    # A hash where no position names it: only the egress shapes mask it.
    assert st["lines"][2] == "+ alias exec planted <redacted:egress_hash>"
    assert st["lines"][4:] == RAW[4:], "addresses, IPv6 and IPv4, are never masked"
    EP.record(pack)
    with open(EP._path(), encoding="utf-8") as fh:
        stored = fh.read()
    assert USER_SECRET not in stored and COMMUNITY not in stored and HASH not in stored


def test_at_most_the_cap_of_lines_is_kept_and_its_counts_whole(pack_lab, monkeypatch):  # noqa: F811
    many = [f"+ ntp server 192.0.2.{i}" for i in range(30)]
    _differs(monkeypatch, many)
    (st,) = _section(_build(_alerts(heartbeat=True)), "intent")["pieces"]
    assert st["lines"] == many[:EP.INTENT_LINES] and EP.INTENT_LINES == 20
    assert (st["adds"], st["removes"]) == (4, 2)


def test_the_bytes_sent_hold_each_planted_secret_only_masked(world, monkeypatch):  # noqa: F811
    """Through Explain, the real gateway and the adapter's bytes: the pack holds the lines
    masked; a value that became a known secret only after the pack was built (LATE) is masked
    by the gateway's own mask, by value."""
    from modules import redact
    _differs(monkeypatch)
    pack = _build(_alerts(heartbeat=True))
    assert LATE in json.dumps(pack), "built before LATE was a known secret"
    assert EP.record(pack)["ok"]
    monkeypatch.setattr(redact, "known_secret_values", lambda: {LATE: "Lab:planted"})
    world.answer = _answer(pack, hypotheses=[{
        "claim": "The intent difference does not touch the alerting interface.",
        "evidence_refs": ["intent:1", "alert"], "confirm_with": "show running-config"}])
    from modules.ai import triggers
    from tests.ai_person import pressed_by
    with pressed_by("operator@example.com"):
        got = explain.explain(pack["id"], actor="operator@example.com",
                              trigger=triggers.person("operator@example.com"),
                              send=world.send, today="2026-10-25")
    sent = world.sent[-1]["bytes"]
    for value in (USER_SECRET, COMMUNITY, HASH, LATE):
        assert value not in sent, value
    assert "username admin privilege 15 secret 0 <redacted:" in sent
    assert "alias exec planted <redacted:egress_hash>" in sent
    assert "ntp server 2001:db8::250" in sent and "ntp server 192.0.2.250" in sent
    assert got.get("error") != "unmasked_secret", got


def test_the_intent_s_last_commit_is_read_from_its_trailers(pack_lab):  # noqa: F811
    """The commit's own trailers, read here by git directly (an independent path): the pack
    names the same actor, how established and time."""
    from tests.interface_pages import _commit_intent
    _commit_intent(pack_lab["repo"], "r1")
    pack = _build(_alerts("2001:db8::11"))
    (st,) = _section(pack, "intent")["pieces"]
    fmt = "%h|%cI|%(trailers:key=Actor,valueonly)|%(trailers:key=Actor-Verified,valueonly)"
    out = subprocess.run(["git", "-C", pack_lab["repo"], "log", "-1", "--abbrev=12",
                          f"--format={fmt}", "--", "host_vars/r1.yml"],
                         capture_output=True, text=True, check=True).stdout
    sha, at, actor, verified = [x.strip() for x in out.replace("\n", "").split("|")]
    c = st["intent_commit"]
    assert (c["state"], c["sha"], c["at"], c["actor"], c["verified"]) == (
        "ok", sha, at, actor, verified)
    assert actor == "t" and c["how"] == who.HOW.get(verified, "not verified")


def test_a_history_piece_carries_how_its_actor_was_established(pack_lab):  # noqa: F811
    """Schema 7: each History piece's ``verified`` is its commit's Actor-Verified, read here by
    git directly; the fact sheet and Explain say it beside the actor."""
    (piece,) = _section(_build(_alerts("2001:db8::11")), "history")["pieces"]
    out = subprocess.run(["git", "-C", pack_lab["repo"], "log", "-1", "--abbrev=12",
                          "--format=%h|%(trailers:key=Actor-Verified,valueonly)",
                          piece["sha"]], capture_output=True, text=True, check=True).stdout
    sha, verified = [x.strip() for x in out.replace("\n", "").split("|")]
    assert (piece["kind"], piece["sha"], piece["verified"]) == ("golden", sha, verified)
    assert verified, "the floor: the lab's commit carries an Actor-Verified"
    assert who.change_of("history", piece)["words"] == (
        f"{piece['who']} ({who.HOW.get(verified, 'not verified')})")


def test_no_intent_commit_is_no_record_of_who(pack_lab):  # noqa: F811
    (st,) = _section(_build(_alerts("2001:db8::11")), "intent")["pieces"]
    assert st["intent_commit"]["state"] == "absent"
    assert st["intent_commit"]["why"] == "no commit holds host_vars/r1.yml"
    assert who.change_of("intent", dict(st, state="differs"))["words"] == who.NO_RECORD


def test_the_pack_card_draws_the_lines_and_who_committed(pack_lab, monkeypatch):  # noqa: F811
    _differs(monkeypatch)
    pack = _build(_alerts(heartbeat=True))
    EP.record(pack)
    r = pack_lab["client"].get(f"/v2/monitoring/alerts/pack/{pack['id']}",
                               headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200, html[:400]
    assert "The lines, masked:" in html and "username admin privilege 15 secret 0 <redacted:" \
        in html
    assert USER_SECRET not in html
    # One line each, its side drawn: "+ " in intent, "- " on the device (merged card, 2026-10-29).
    (st,) = _section(pack, "intent")["pieces"]
    drawn = re.findall(r'<span class="pack-diff-line" data-side="([a-z]+)">(.*?)</span>', html)
    assert drawn == [({"+ ": "intent", "- ": "device"}[x[:2]], x) for x in st["lines"]], drawn
    assert {s for s, _ in drawn} == {"intent", "device"}, "the floor: both sides drawn"
    assert "Intent last committed: no record of who" in html


# ── (b) who on each hypothesis ───────────────────────────────────────────────────────────

def _golden_ref(pack):
    return next(p["ref"] for p in _section(pack, "history")["pieces"] if p["kind"] == "golden")


def test_mercury_adds_who_the_claim_omits_and_the_model_s_answer_is_kept(world,  # noqa: F811
                                                                         monkeypatch):
    used = []
    real = calls.record_use

    def record(cid, use, **kw):
        used.append((use, kw))
        return real(cid, use, **kw)
    monkeypatch.setattr(calls, "record_use", record)
    ref = _golden_ref(world.pack)
    claim = "The golden recorded before the errors changed r1's configuration."
    world.answer = _answer(world.pack, hypotheses=[{
        "claim": claim, "evidence_refs": [ref, "alert"],
        "confirm_with": "show interfaces | include errors"}])
    got = _explain(world)
    assert got["ok"] is True, got
    (h,) = got["answer"]["hypotheses"]
    piece = next(p for p in _section(world.pack, "history")["pieces"] if p["ref"] == ref)
    words = who.change_of("history", piece)["words"]
    assert piece["who"] == "operator@example.com" and words.startswith("operator@example.com")
    assert h["claim"] == claim, "the model's words are never changed"
    # One representation of who (merged with the answer card, 2026-10-29): each actor once,
    # Mercury's marked by *by*, its pieces as the card's citations; no second list beside it.
    assert "mercury_who" not in h, h
    assert h["who"] == [{"words": words, "who": "operator@example.com", "refs": [ref],
                         "by": "mercury", "cites": [{"ref": ref, "in_pack": True}]}]
    assert [{k: w[k] for k in ("words", "who", "refs")} for w in h["who"]
            if w["by"] == "mercury"] == [{"words": words, "who": "operator@example.com",
                                          "refs": [ref]}]
    assert f"who, added by Mercury to hypothesis 1: {words} ({ref})" in used[-1][1]["detail"]
    row = next(r for r in calls.read()["rows"] if r.get("id") == got["call_id"])
    assert json.loads(row["response"])["hypotheses"][0]["claim"] == claim
    assert who.unattributed([dict(h, evidence_refs=[ref, "alert"])], world.pack["sections"]) \
        == []


def test_a_claim_naming_the_actor_or_citing_no_change_is_left_as_written(world):  # noqa: F811
    ref = _golden_ref(world.pack)
    world.answer = _answer(world.pack, hypotheses=[
        {"claim": "operator@example.com recorded the golden before the errors.",
         "evidence_refs": [ref], "confirm_with": "show interfaces | include errors"},
        {"claim": "Input errors rose on r1.", "evidence_refs": ["alert"],
         "confirm_with": "show interfaces | include errors"}])
    got = _explain(world)
    h1, h2 = got["answer"]["hypotheses"]
    assert [w["by"] for w in h1["who"]] == ["model"]
    assert h1["who"][0]["cites"] == [{"ref": ref, "in_pack": True}]
    assert h2["who"] == []
    assert "mercury_who" not in h1 and "mercury_who" not in h2


def test_the_card_draws_who_added_by_mercury_after_the_claim(world):  # noqa: F811
    ref = _golden_ref(world.pack)
    world.answer = _answer(world.pack, hypotheses=[{
        "claim": "The golden recorded before the errors changed r1.",
        "evidence_refs": [ref, "alert"], "confirm_with": "show interfaces | include errors"}])
    r = world.lab["client"].post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
                                 headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    # The answer card (board AlertsExplain revised 2026-10-29): the hypothesis is Most likely
    # cause, its claim, then who, then what it cites.
    li = re.search(r'<strong class="answer-claim">The golden recorded before the errors '
                   r"changed r1\.</strong>(.*?)</section>", html, re.S)
    assert li, html[:2000]
    body = li.group(1)
    line = re.search(r'<span class="answer-line explain-who" data-who-by="([^"]+)" '
                     r'data-actor="([^"]*)" data-refs="([^"]+)" title="([^"]*)">'
                     r'(.*?)</span>\s*<span class="answer-line"><span class="faint">Cites',
                     body, re.S)
    assert line, body
    by, actor, refs, title, drawn = line.groups()
    assert (by, actor, refs) == ("mercury", "operator@example.com", ref)
    # Who, on hover: each actor of its changes and whose words said it.
    assert title.startswith("Who: operator@example.com") and \
        title.endswith(f"({ref}, added by Mercury)")
    # Mercury's words after the claim, under their own chip, naming the piece as a citation.
    assert re.match(r'<span class="faint">Who:</span> (operator@example\.com[^<]*) '
                    r'<span class="badge badge-neutral" title="[^"]*">who, added by Mercury'
                    r'</span> <span class="faint">from</span> <a class="pack-ref cite-chip" '
                    rf'href="#{re.escape(world.pack["id"])}-{re.escape(ref)}"', drawn), drawn
    assert body.index("explain-who") < body.index(">Cites<"), "who comes after the claim"


@pytest.mark.parametrize("claim,named", [
    ("operator@example.com deployed it", True), ("Operator deployed it", True),
    ("the operator's deploy", False), ("OPERATOR@EXAMPLE.COM did", True),
    ("nooperator@example.com", False), ("operators deployed it", False),
    ("no record of who did it", False)])
def test_an_actor_is_named_as_a_whole_word(claim, named):
    assert who.names_who(claim, "operator@example.com") is named


def test_no_record_of_who_is_named_only_in_those_words():
    assert who.names_who("No record of who changed it", "") is True
    assert who.names_who("an unknown person changed it", "") is False


def test_a_cited_section_holds_each_of_its_changes_and_one_actor_is_said_once():
    pack = _changes_pack()
    hyps = [{"claim": "History shows recent changes.", "evidence_refs": ["history", "logs:1"],
             "confirm_with": "show logging"}]
    added = who.mercury_who(hyps, pack["sections"])
    assert [(a["words"], a["refs"]) for a in added] == [
        ("operator@example.com (verified sign-in)", ["history:1"]),
        (who.NO_RECORD, ["history:2"]),
        ("operator@example.com (not verified)", ["history:4"]),
        ("<user> on vty0 from 192.0.2.1, the device's account as its log line names it",
         ["logs:1"])]
    claim = who.inserted(hyps[0]["claim"], added)
    assert claim.startswith("History shows recent changes. (who, added by Mercury: ")
    assert who.unattributed([dict(hyps[0], claim=claim)], pack["sections"]) == []
    assert who.unattributed(hyps, pack["sections"]) == [1]


# ── the grader, raw and as kept, on the recorded answers ─────────────────────────────────

def _recorded_answer(a):
    """A recorded run's answer as `explain_misses` reads it (the recording keeps the structured
    answer, not the prose: every claim is empty)."""
    return {"outcome": a["outcome"], "needs_human": a["needs_human"],
            "checked": list(a.get("checked") or []), "rationale": "", "why_not": "",
            "hypotheses": [{"claim": "", "confirm_with": "", "evidence_refs": list(e)}
                           for e in a.get("evidence") or []]}


def _without_who(expect, raw, pack):
    """The misses of the answer as kept with Mercury's needs_human alone (C2141's guard), never
    its who: what `explain_graded`'s kept misses were before this order."""
    guard = explain.needs_human_guard(raw["outcome"], bool(raw["needs_human"]), pack)
    return cases.explain_misses(expect, dict(raw, needs_human=True) if guard else raw, pack)


def _runs():
    for c in RECORDED["cases"]:
        for run in (c.get("recorded") or {}).get("runs") or []:
            yield c, run, _recorded_answer(run["answer"])


def _walk_differing():
    """Walk 2's pack with its Intent check differing, schema 7's shape (its commit unknown)."""
    pack = copy.deepcopy(WALK)
    piece = _section(pack, "intent")["pieces"][0]
    piece.update(state="differs", adds=1, removes=1, lines=[f"+ {SAME}", f"- {SAME}"],
                 intent_commit={"state": "absent", "why": "planted"})
    return pack


#: The recorded runs citing a change on the Walk pack with its intent differing: every run
#: citing intent:1 (Walk 2's history:1 is a restart, and its History holds no history:11 or
#: history:14).
CHANGED = [(9, 5), (12, 1), (14, 1), (14, 2), (14, 5)]


def test_the_recorded_answers_who_changes_and_no_grade_it_moves():
    walk_changed, differ_changed, moved = [], [], []
    differing = _walk_differing()
    for c, run, raw in _runs():
        for pack, into in ((WALK, walk_changed), (differing, differ_changed)):
            got = cases.explain_graded(c["expect"], raw, pack)
            if got["guarded"]["who_by_mercury"]:
                into.append((c["n"], run["round"]))
            if got["guarded"]["misses"] != _without_who(c["expect"], raw, pack):
                moved.append((c["n"], run["round"]))
        assert raw == _recorded_answer(run["answer"]), "the raw answer is never changed"
    assert sum(1 for _ in _runs()) == 100, "the floor: the recording's 100 runs"
    assert walk_changed == []
    assert sorted(differ_changed) == CHANGED
    assert moved == []


def test_every_change_cited_is_attributed_and_no_grade_moves_when_every_ref_is_a_change():
    """The widest case: every recorded run on a pack in which each history, logs or intent
    piece it cites is a change (a receipt by a person, a configuration line naming no user, an
    intent difference with no commit): each such run has who added, every hypothesis is
    attributed as kept, and no run's misses differ from the answer without them."""
    changed, moved = 0, []
    for c, run, raw in _runs():
        refs = {r for h in raw["hypotheses"] for r in h["evidence_refs"]}
        pack = copy.deepcopy(WALK)
        hist, logs = _section(pack, "history"), _section(pack, "logs")
        intent = _section(pack, "intent")
        for ref in sorted(refs):
            name, _sep, n = ref.partition(":")
            if name == "history" and n.isdigit():
                hist["pieces"] = [p for p in hist["pieces"] if p["ref"] != ref] + [
                    _hist(int(n), "receipt")]
            elif name == "logs" and n.isdigit():
                logs["pieces"] = [p for p in logs["pieces"] if p["ref"] != ref] + [
                    {"ref": ref, "at": "2026-10-22T18:00:00Z", "device": "r1", "text": CONSOLE}]
            elif ref == "intent:1":
                intent["pieces"][0].update(state="differs")
        got = cases.explain_graded(c["expect"], raw, pack)
        kept = cases.guarded(raw, pack)
        cites = bool(who.mercury_who(raw["hypotheses"], pack["sections"]))
        changed += cites
        assert bool(got["guarded"]["who_by_mercury"]) is cites
        assert who.unattributed(kept["hypotheses"], pack["sections"]) == []
        if got["guarded"]["misses"] != _without_who(c["expect"], raw, pack):
            moved.append((c["n"], run["round"]))
    # Independently: the runs a hypothesis of which cites a history or logs piece, or intent:1.
    citing = sum(1 for _c, _r, raw in _runs() if any(
        re.fullmatch(r"(?:history|logs):\d+|intent:1", ref)
        for h in raw["hypotheses"] for ref in h["evidence_refs"]))
    assert changed == citing >= 41, "the floor: the recording's 41 runs citing them"
    assert moved == []
