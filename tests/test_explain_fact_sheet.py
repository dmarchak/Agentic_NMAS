"""Explain's fact sheet (the operator's order of 2026-10-29, C2117 and C2141):
modules/ai/fact_sheet.py, sent by modules/ai/explain.py (`facts`, `parts`, `budgeted`).

Lines computed by Mercury from the pack as sent, each labelled "computed by Mercury", sent as
the first data block (the changes and actions in the window, the operator's order of
2026-10-29, are tests/test_explain_who.py's):

- **heartbeat cadence** (C2117): the alert's device's beats beside its neighbours', its own
  role first, its longest gap against their median; recorded case 19's shape (s4's 392 s
  against the routers' 300 s, its clock at 0.775 of real time) planted from its recording's
  `found`, and Walk 2's captured pack;
- **reloads in the window**: each reload or restart line and each restart Mercury's record
  holds, with the Reload or window that accounts for it, else "unexplained", an address in a
  line kept whole, IPv4 and IPv6;
- **observer health at the alert's time**: each scrape job, the alert's own first, failing in
  the last minute or not, at most at once (`evidence_observer.at_once`, the grader's count),
  the pack's devices failing in it, every job counted together;
- **what the pack lacks**: each section not read, empty, withheld or not in the pack, each
  figure not measured.

And: built from the pack AS SENT, so with the topology class off no device but the alert's
own is named in it; masked on the way out; the cached prefix unchanged by it, v4 and v8 sent
the same sheet, v1 none.
"""
import json
import os
import re

import pytest

from modules import evidence_observer as O
from modules.ai import cases, explain, fact_sheet, gateway, profiles, prompts
from tests.test_ai_explain import _answer, _explain, world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "tests", "fixtures", "evidence_pack", "walk2_r1_pack.json"),
          encoding="utf-8") as _fh:
    WALK = json.load(_fh)
WALK_SENT = [s for s in WALK["sections"] if s["name"] not in explain.NOT_SENT]
#: Walk 2's topology sent names each device's role (tests/fixtures/evidence_pack/).
WALK_ROLES = {"r1": "router", "r2": "router", "r3": "router", "r4": "router", "s1": "switch",
              "s3": "switch", "s4": "switch"}

FROM, TO = "2026-10-26T11:35:00Z", "2026-10-26T12:00:00Z"


def _beat(dev, name, hop, gap, beats=4, last="2026-10-26T11:58:12Z", state="ok"):
    return {"ref": f"health:{dev}:heartbeat", "dev": dev, "device": name, "hop": hop,
            "figure": "heartbeat", "state": state, "beats": beats, "max_gap_s": gap,
            "max_gap_ended_at": last, "last_at": last, "since_last_s": 108}


def _scrapes(dev, name, hop, jobs=()):
    return {"ref": f"health:{dev}:scrapes", "dev": dev, "device": name, "hop": hop,
            "figure": "scrapes", "state": "ok", "scrapes": 50, "failed": 3 if jobs else 0,
            "jobs_failing": list(jobs)}


def _sec(name, state="ok", pieces=(), **extra):
    return dict({"ref": name, "name": name, "state": state, "why": extra.pop("why", ""),
                 "source": f"the {name} source", "pieces": list(pieces)}, **extra)


def _case19(**over):
    """Case 19's shape, from its recording's `found`: s4's longest beat gap 392 s, no failed
    scrape, no log line; the routers around it at 300 s (C2117's words)."""
    health = _sec("health", window={"from": FROM, "to": TO}, pieces=[
        _beat("dev:u66688a5c", "s4", 0, 392, beats=4),
        _beat("dev:uc038a8be", "r1", 1, 300, beats=5),
        _beat("dev:u342aff19", "r2", 1, 300, beats=5),
        _beat("dev:ub937e1ed", "r3", 1, 301, beats=5)])
    sections = [
        _sec("alert", pieces=[{"ref": "alert:1", "kind": "condition", "state": "Alerting",
                               "labels": {"device": "s4"}}]),
        _sec("history", "empty", why="nothing recorded"), health,
        _sec("logs", "empty", why="Loki holds no line from s4")]
    pack = {"device": "s4", "rule": "NMAS heartbeat missing: s4", "onset": "2026-10-26T11:50:00Z",
            "built_at": TO, "schema": 6, "sections": sections}
    pack.update(over)
    return pack


def _line(text, name):
    head = {"heartbeat": "Heartbeat cadence", "reloads": "Reloads in the window",
            "observer": "Observer health at the alert's time",
            "lacks": "What the pack lacks"}[name]
    return next(ln for ln in text.split("\n") if ln.startswith(head))


# ── 1. heartbeat cadence ──────────────────────────────────────────────────────────────────

def test_case_19_s_cadence_is_computed_against_its_neighbours():
    pack = _case19()
    line = fact_sheet.heartbeat_line(pack, pack["sections"])
    assert line.startswith("Heartbeat cadence (computed by Mercury): s4 "
                           "[health:dev:u66688a5c:heartbeat]: 4 beats in the window's 1500 s, "
                           "longest gap 392 s ending 2026-10-26T11:58:12Z, the last received "
                           "2026-10-26T11:58:12Z, 108 s before the alert's time.")
    assert ("r1 longest gap 300 s [health:dev:uc038a8be:heartbeat], r2 longest gap 300 s "
            "[health:dev:u342aff19:heartbeat] and r3 longest gap 301 s") in line
    assert ("s4's longest gap, 392 s, against the median of theirs, 300 s over 3 devices: "
            "+92 s, 1.31 times") in line
    assert "no role of these devices was sent, so every device measured is compared" in line
    assert line.endswith("not every receive time.")


def test_the_device_s_own_role_is_compared_first_when_the_topology_names_roles():
    pack = _case19()
    pack["sections"][2]["pieces"].append(_beat("dev:u654297ae", "s1", 1, 300, beats=5))
    line = fact_sheet.heartbeat_line(pack, pack["sections"],
                                     {"s4": "switch", "s1": "switch", "r1": "router"})
    assert "Beside it, of its role (switch): s1 longest gap 300 s" in line
    assert "; the others: r1 longest gap 300 s" in line
    assert "against the median of its role's (switch), 300 s over 1 device: +92 s" in line
    # A role none of the others shares is said, and every device is compared.
    line = fact_sheet.heartbeat_line(pack, pack["sections"], {"s4": "switch"})
    assert "(none of these is of its role, switch, in what was sent)" in line
    assert "the median of theirs, 300 s over 4 devices" in line


def test_walk_2_s_router_is_compared_with_the_routers():
    line = fact_sheet.heartbeat_line(WALK, WALK_SENT, WALK_ROLES)
    assert "r1 [health:dev:uc038a8be:heartbeat]: 4 beats in the window's 1020 s" in line
    assert "of its role (router): r2 longest gap 300 s [health:dev:u342aff19:heartbeat]" in line
    assert "s3 1 beat, no gap measured" in line and "r8 no beat in the window" in line
    assert "r1's longest gap, 300 s, against the median of its role's (router), 300 s" in line


@pytest.mark.parametrize("state,beats,said", [
    ("ok", 0, "no heartbeat received in the window's 1500 s"),
    ("empty", 0, "no heartbeat received in the window's 1500 s"),
    ("unreadable", None, "its heartbeat was not measured (unreadable)")])
def test_the_device_s_own_heartbeat_missing_or_unread_is_said(state, beats, said):
    pack = _case19()
    own = pack["sections"][2]["pieces"][0]
    own.update(state=state, beats=beats, max_gap_s=None)
    line = fact_sheet.heartbeat_line(pack, pack["sections"])
    assert said in line and "s4's longest gap" not in line


def test_with_no_topology_sent_nothing_of_the_neighbours_is_in_it():
    """The class gate holds in the sheet: with no topology sent, the pack as sent holds the
    alert's device's figures alone, and the sheet names no other device."""
    sent = explain.sent_sections(WALK, {"sent": False})
    text = fact_sheet.sheet(WALK, sent, explain.roles_of({"sent": False}))
    assert "No other device's heartbeat was sent (the figures of the devices around it are " \
           "not sent" in _line(text, "heartbeat")
    others = {p["device"] for s in WALK_SENT if s["name"] == "health" for p in s["pieces"]
              if p["device"] != "r1"}
    assert len(others) >= 8, "the floor: Walk 2's two-hop devices"
    for name in others:
        assert not re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text), name
    assert set(re.findall(r"dev:u?[0-9a-f]+", text)) == {"dev:uc038a8be"}


# ── 2. reloads in the window ──────────────────────────────────────────────────────────────

RELOAD4 = "%SYS-5-RELOAD: Reload requested by admin on vty0 (192.0.2.5). Reload Reason: test."
RELOAD6 = "%SYS-5-RELOAD: Reload requested by admin on vty0 (2001:db8::5). Reload Reason: test."
RESTART = "%SYS-5-RESTART: System restarted --"


def _reloaded(text, history=()):
    pack = _case19()
    pack["sections"][3] = _sec("logs", pieces=[{"ref": "logs:1", "at": "2026-10-26T11:52:00Z",
                                                "device": "s4", "text": text}])
    pack["sections"][1] = _sec("history", pieces=list(history)) if history else \
        _sec("history", "empty", why="nothing recorded")
    return pack


@pytest.mark.parametrize("text,address", [(RELOAD4, "192.0.2.5"), (RELOAD6, "2001:db8::5")])
def test_a_reload_no_reload_or_window_accounts_for_is_unexplained(text, address):
    pack = _reloaded(text)
    line = fact_sheet.reloads_line(pack, pack["sections"])
    assert line.startswith("Reloads in the window (computed by Mercury): 2026-10-26T11:52:00Z: "
                           "s4 logged ")
    assert f"({address})" in line, "an address is kept whole"
    assert "[logs:1]; no receipt or window: unexplained." in line


def test_mercury_s_reload_accounts_for_it_by_who():
    reload = {"ref": "history:1", "kind": "reload", "at": "2026-10-26T11:58:30Z",
              "who": "operator@example.com", "what": "Reload: back, verified"}
    pack = _reloaded(RELOAD6, [reload])
    line = fact_sheet.reloads_line(pack, pack["sections"])
    assert "requested by Mercury's Reload, operator@example.com [history:1]" in line
    # Further than the planned slack from the line, it does not.
    far = dict(reload, at="2026-10-26T12:30:00Z")
    pack = _reloaded(RELOAD6, [far])
    assert "unexplained" in fact_sheet.reloads_line(pack, pack["sections"])


def test_a_restart_judged_planned_accounts_for_it_and_the_restart_is_listed():
    restart = {"ref": "history:1", "kind": "restart", "at": "2026-10-26T11:53:00Z",
               "outcome": "planned", "who": "operator@example.com",
               "what": "Restarted as planned"}
    pack = _reloaded(RESTART, [restart])
    line = fact_sheet.reloads_line(pack, pack["sections"])
    assert line.count("a planned-restart window accounts for it, operator@example.com "
                      "[history:1]") == 2
    assert ("2026-10-26T11:53:00Z: Restarted as planned: Mercury's restart record (the uptime "
            "counter fell) [history:1]") in line


def test_an_unplanned_restart_is_unexplained_and_a_window_s_span_is_not_guessed():
    restart = {"ref": "history:1", "kind": "restart", "at": "2026-10-26T11:53:00Z",
               "outcome": "unplanned", "who": "", "what": "Restarted unexpectedly"}
    pack = _reloaded(RESTART, [restart])
    line = fact_sheet.reloads_line(pack, pack["sections"])
    assert line.count("no receipt or window: unexplained") == 2
    window = {"ref": "history:2", "kind": "window", "at": "2026-10-26T11:40:00Z",
              "who": "operator@example.com", "what": "Planned-restart window declared"}
    pack = _reloaded(RESTART, [restart, window])
    assert "a planned-restart window was declared 2026-10-26T11:40:00Z by operator@example.com " \
           "[history:2]; its span is not in the pack" in fact_sheet.reloads_line(
               pack, pack["sections"])


def test_none_in_the_window_and_sources_not_read_are_said():
    pack = _case19()
    assert fact_sheet.reloads_line(pack, pack["sections"]) == (
        "Reloads in the window (computed by Mercury): none: no %SYS-5-RELOAD or %SYS-5-RESTART "
        "line among the pack's 0 log lines, and no restart in History between "
        "2026-10-26T11:35:00Z and 2026-10-26T12:00:00Z; the log lines were read and hold none.")
    pack["sections"][1]["state"] = "unreadable"
    pack["sections"][3]["state"] = "unreadable"
    line = fact_sheet.reloads_line(pack, pack["sections"])
    assert "the log lines were not read (unreadable)" in line
    assert "History was not read (unreadable)" in line and "no restart in History" not in line
    restart = _reloaded(RESTART)
    restart["sections"][1]["state"] = "unreadable"
    assert "whether a Reload or a window accounts for it is not known" in \
        fact_sheet.reloads_line(restart, restart["sections"])


# ── 4. observer health at the alert's time ────────────────────────────────────────────────

def _job(job, targets, failed, most, last, **extra):
    return dict({"ref": f"observer:job:{job}", "what": f"job:{job}", "job": job, "state": "ok",
                 "targets": targets, "targets_failed": failed, "most_failing": most,
                 "most_failing_of": targets, "most_failing_at": "2026-10-26T11:58:00Z",
                 "minutes_failing": 3 if most else 0, "last_failing_at": last,
                 "first_failing_at": last}, **extra)


def _observed(*jobs, job_label="cisco_vios_l2"):
    pack = _case19()
    pack["sections"][0]["pieces"][0]["labels"]["job"] = job_label
    pack["sections"][2]["pieces"] += [_scrapes("dev:u66688a5c", "s4", 0, ["cisco_vios_l2"]),
                                      _scrapes("dev:uc038a8be", "r1", 1)]
    pack["sections"].append(_sec("observer", window={"from": FROM, "to": TO},
                                 pieces=list(jobs)))
    return pack


def test_the_alert_s_own_job_leads_failing_in_the_last_minute_its_devices_named():
    pack = _observed(_job("cisco_8000v", 6, 0, 0, None),
                     _job("cisco_vios_l2", 5, 3, 2, "2026-10-26T11:59:30Z"))
    line = fact_sheet.observer_line(pack, pack["sections"])
    assert line.startswith(
        "Observer health at the alert's time (computed by Mercury): observer:job:cisco_vios_l2 "
        "(the alert's own job): failing in the window's last minute; at most 2 of 5 targets "
        "failing at once, at 2026-10-26T11:58:00Z; 3 of its 5 targets failed at least once; "
        "failing in it among the pack's devices: s4 [health:dev:u66688a5c:scrapes] (the other "
        "2 are not named in the pack)")
    assert "observer:job:cisco_8000v: no minute failing in the window; 0 of its 6 targets" in line
    assert line.endswith("Across the 2 jobs read: 3 of 11 targets failed at least once (counted "
                         "per job: a device two jobs poll is two targets).")


def test_a_job_that_stopped_failing_before_the_alert_says_when():
    pack = _observed(_job("cisco_vios_l2", 5, 3, 2, "2026-10-26T11:50:00Z"))
    assert "not failing at the alert's time: last failing 2026-10-26T11:50:00Z, 600 s before " \
           "it" in fact_sheet.observer_line(pack, pack["sections"])


def test_at_once_is_the_graders_count():
    """One count for the sheet and the grader (`cases._across`, C2111): the most at once, else
    the targets that failed when the minutes were not read."""
    assert O.at_once({"most_failing": 2, "targets_failed": 3}) == 2
    assert O.at_once({"targets_failed": 3}) == 3 and O.at_once({}) == 0
    job = _job("cisco_vios_l2", 5, 3, 2, "2026-10-26T11:59:30Z")
    assert cases._across({"evidence_refs": [job["ref"]]}, set(), {},
                         {"sections": [_sec("observer", pieces=[job])]}) == 2


def test_an_observer_not_in_the_pack_or_not_read_is_said():
    assert fact_sheet.observer_line(WALK, WALK_SENT) == (
        "Observer health at the alert's time (computed by Mercury): this pack holds no "
        "observer section (pack schema 5, built before the monitoring side was gathered).")
    pack = _observed()
    pack["sections"][-1]["state"] = "unreadable"
    assert fact_sheet.observer_line(pack, pack["sections"]).endswith(
        "the observer section was not read (unreadable).")


# ── 5. what the pack lacks ────────────────────────────────────────────────────────────────

def test_walk_2_s_pack_lacks_are_named():
    line = fact_sheet.lacks_line(WALK, WALK_SENT)
    assert line.startswith("What the pack lacks (computed by Mercury): neighbours (Neighbours): "
                           "absent (cannot be rebuilt;")
    assert "observer (The monitoring side over the window): not in this pack (pack schema 5)" \
        in line
    assert "health scrapes absent for r8" in line and "health heartbeat empty for r8" in line
    assert "observed (" not in line, "the observed overlay rides in the topology, never the pack"


def test_withheld_and_empty_sections_are_named_and_a_whole_pack_lacks_nothing():
    sent = explain.sent_sections(WALK, {"sent": False})
    line = fact_sheet.lacks_line(WALK, sent)
    assert "health: not sent (the figures of the devices around it are not sent" in line
    assert "endpoints: not sent (the endpoints are not sent" in line
    pack = _case19()
    assert "logs (Log lines around the onset): empty (Loki holds no line from s4)" in \
        fact_sheet.lacks_line(pack, pack["sections"])
    whole = {"schema": 6, "sections": [_sec(n) for n in ("alert", "concurrent", "device",
                                                          "history", "intent", "neighbours",
                                                          "observed", "endpoints", "health",
                                                          "observer", "logs")]}
    assert fact_sheet.lacks_line(whole, whole["sections"]).endswith(
        "nothing: every section was read and held something, every figure measured.")


# ── the sheet as sent ─────────────────────────────────────────────────────────────────────

def test_every_line_is_labelled_and_the_sheet_is_masked(monkeypatch):
    from modules import redact
    pack = _reloaded("%SYS-5-RELOAD: Reload requested by admin. key Planted5ecretValue9 "
                     "snmp-server community Pl4ntedCommunity RO")
    monkeypatch.setattr(redact, "known_secret_values",
                        lambda: {"Planted5ecretValue9": "Lab:planted"})
    text = fact_sheet.sheet(pack, pack["sections"])
    assert text.split("\n")[0] == fact_sheet.HEAD
    # The head and a line each of `LINES` (the changes and actions since the operator's order
    # of 2026-10-29; tests/test_explain_who.py).
    assert len(text.split("\n")) == 1 + len(fact_sheet.LINES) == 6
    assert all("(computed by Mercury)" in ln for ln in text.split("\n")[1:])
    assert "Planted5ecretValue9" not in text and "Pl4ntedCommunity" not in text
    assert "<redacted:" in text


def _data_blocks(body):
    return re.findall(r'<data name="([^"]+)">', body["messages"][0]["content"])


def _block(body, name):
    return re.search(r'<data name="' + name + r'">\n(.*?)\n</data>',
                     body["messages"][0]["content"], re.S).group(1)


def test_the_sheet_is_the_first_data_block_and_the_cached_prefix_is_unchanged(world):  # noqa: F811
    world.answer = _answer(world.pack)
    assert _explain(world)["ok"] is True
    body = world.sent[-1]["body"]
    assert _data_blocks(body)[0] == fact_sheet.PART
    sheet = _block(body, fact_sheet.PART)
    assert sheet.startswith(fact_sheet.HEAD) and "Heartbeat cadence (computed by Mercury)" in sheet
    # The prefix the cache keeps is the same bytes with the sheet as without it.
    topo = explain.topology(world.pack)
    data = explain.parts(world.pack, topo)
    without = {k: v for k, v in data.items() if k != fact_sheet.PART}
    pin = profiles.TASKS["explain"]
    loaded = prompts.load(*explain.PROMPT)
    a = gateway.build_request(loaded, explain.ExplanationV2, data, pin, explain.context(topo))
    b = gateway.build_request(loaded, explain.ExplanationV2, without, pin,
                              explain.context(topo))
    assert a["system"] == b["system"] == body["system"]
    assert a["messages"] != b["messages"]


def test_v4_and_v8_are_sent_the_same_sheet_and_v1_none(world):  # noqa: F811
    from modules.ai import triggers
    from tests.ai_person import pressed_by
    world.answer = _answer(world.pack)
    sheets = {}
    for version in (4, 8, 1):
        with pressed_by("operator@example.com"):
            explain.explain_pack(world.pack, actor="operator@example.com",
                                 trigger=triggers.person("operator@example.com"),
                                 send=world.send, today="2026-10-25",
                                 prompt=("explain", version))
        body = world.sent[-1]["body"]
        sheets[version] = (_block(body, fact_sheet.PART)
                           if fact_sheet.PART in _data_blocks(body) else None)
    assert sheets[4] and sheets[4] == sheets[8]
    assert sheets[1] is None


def test_v6_under_its_budget_keeps_the_sheet_whole(world):  # noqa: F811
    topo = explain.topology(world.pack)
    whole = explain.budgeted(world.pack, topo, ("explain", 6), explain.SCHEMA_OF[6])
    assert whole["data"][fact_sheet.PART] == explain.facts(
        world.pack, explain.sent_sections(world.pack, topo), topo)


def test_its_size_on_the_captured_pack():
    """Walk 2's pack (case 21's schema-5 rebuild): the sheet's size, so its cost is known. The
    other recorded cases' packs are kept off the repository (their sha256 alone)."""
    text = fact_sheet.sheet(WALK, WALK_SENT, WALK_ROLES)
    assert 1500 <= len(text) <= 3000, len(text)
