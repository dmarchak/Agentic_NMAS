"""Every board-built screen is compared with its board, and the comparison is kept (C650; the
operator, 2026-10-10: "a screenshot of the page next to the board, compared region by region —
the browser tests checked behaviour, not fidelity, which is why this got through").

A record, `docs/fidelity/<screen>.md`, names the boards it compared (files on the mockups
canvas), the templates it compared and their sha256, and a verdict per region: `same`,
`deviation` (each one a line in docs/STANDING_APPROVAL_LOG.md, said with its reason) or `later`
(a later step of the plan, named). The shots it was read from are taken by
tests/test_board_shots.py (run only when asked).

- every signed-off screen (tests/signed_off_screens.SIGNED_OFF) has a record or is on
  UNCHECKED, which only shrinks;
- a record's templates are unchanged since it was written (a changed template needs its regions
  compared again and the record's hash written again);
- every region has a verdict, and a deviation names its line in the approval log.
"""

import hashlib
import os
import re

from tests.signed_off_screens import SIGNED_OFF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIDELITY = os.path.join(ROOT, "docs", "fidelity")

#: Screen -> its record.
RECORDS = {"topology.html": "topology.md", "history_syslog.html": "logs.md",
           "logs.html": "logs-tail.md", "dhcp.html": "dhcp.md", "onboard.html": "onboard.md",
           "history_ask_logs.html": "history-ask-logs.md",
           "history_ask_metrics.html": "history-ask-metrics.md",
           # C650: the screens the operator walked in W1 (2026-10-16), compared with their
           # boards, the walk's captures and the shots.
           "landing.html": "landing.md", "devices.html": "devices.md",
           "bulk_intent.html": "bulk-intent.md", "device.html": "device.md",
           "history.html": "history.md", "credentials.html": "credentials.md",
           "show_commands.html": "show-commands.md",
           "show_commands_run.html": "show-commands-run.md",
           "tab:ask": "tab-ask.md", "tab:history": "tab-history.md",
           "tab:intent": "tab-intent.md", "tab:overview": "tab-overview.md",
           # C650: the screens the operator's walks W2 (2026-10-16) and W3 (2026-10-17) touched,
           # and the batch Apply W1 ran (steps 16 to 18) and its records left out, each compared
           # with its boards from those sittings' captures.
           "netbox.html": "netbox.md", "templates.html": "templates.md",
           "settings.html": "settings.md", "apply.html": "apply.md", "tab:logs": "tab-logs.md",
           # C650: three of the four screens W4 (2026-10-17) touched, compared with their boards
           # from local board shots and read beside W4's captures (2026-10-18); About waits on
           # the operator's screenshot (docs/walks/P7-27.md, step 12).
           "save.html": "save.md", "pending.html": "pending.md",
           "retired.html": "retired.md",
           # About, from the operator's screenshot in the P7-27 walk (2026-10-18, step 12).
           "about.html": "about.md",
           # The one-decision out-of-band onboarding's run page (board C of
           # docs/boards/oob-onboarding.html, 2026-10-23).
           "oob_run.html": "oob-run.md",
           # PHASE8_PLAN 17.1 S11: SDN › Controllers and Flows (boards SdnControllers, SdnFlows
           # and SdnPhone, signed off under the Phase 7 mode 2026-10-27).
           "sdn.html": "sdn.md"}

#: Components many screens share, each compared with its own boards (the operator, 2026-10-12:
#: the one stepper, "add it to the board-fidelity records"): component -> its record.
COMPONENTS = {"_run_stepper.html": "stepper.md",
              # C718's Decline… and Undo decline… (canvas page C603, approved 2026-10-13).
              "_decline.html": "decline.md",
              # C537's In progress chip in every v2 page's top bar (canvas v66, boards A and B,
              # signed off under the Phase 7 mode 2026-10-16).
              "_in_progress.html": "in-progress.md",
              # P1's Alerts tab, an alert's evidence pack and Explain (canvas page "P1,
              # Monitoring › Alerts", signed off under the Phase 7 mode 2026-10-26).
              "_evidence_pack.html": "alerts-explain.md",
              # Monitoring › Alerts › History (board P1-H, AlertsHistory.dc.html, signed off
              # under the Phase 7 mode 2026-10-26): past alerts, Build evidence.
              "_alert_history.html": "alerts-history.md",
              # Settings › Integrations' SDN controllers card (board SdnSettings, signed off
              # under the Phase 7 mode 2026-10-27).
              "_sdn_settings.html": "sdn-settings.md",
              # Settings › Installation › AI, each network's background AI features (boards
              # AI3 and AI3b, signed off under the Phase 7 mode 2026-10-27; C1843).
              "_settings_ai.html": "settings-ai.md",
              # The top bar's AI chip and the spend panel it opens (boards AI1 and AI2, signed
              # off under the Phase 7 mode 2026-10-27; C1843).
              "_ai_chip.html": "ai-spend.md",
              # Was this right? under every AI answer, and Answers said wrong on Settings ›
              # Installation › AI (board FB, signed off under the Phase 7 mode 2026-10-28;
              # PHASE8_PLAN 16.11 item 1).
              "_ai_feedback.html": "ai-feedback.md"}

#: Signed-off screens built before the fidelity step and not yet compared with their boards
#: (C650). Each is compared, and its differences fixed or logged, before it leaves this list.
UNCHECKED = {
    # W4's four (Save, the pending page, the retired record, About) were recorded 2026-10-18.
    # No walk touches these, so they move to Stage 7's tail: each compared with its boards
    # from board shots, not a sitting. reapply.html was walked in W1 (steps 40 and 41) with no
    # capture taken, so it has nothing to be recorded from.
    "monitoring.html", "help.html", "monitoring_profile.html", "coverage.html",
    "coverage_deploy.html", "update.html", "settings_installation.html", "reapply.html",
    "tab:monitoring", "tab:neighbours", "tab:netbox",
}
#: Only shrinks: 32 until 2026-10-16, when the twelve screens of the operator's walk W1 were
#: recorded; 20 until 2026-10-17, when the five screens of W2, W3 and W1's batch Apply were
#: (C650); 15 until 2026-10-18, when Save, the pending page and the retired record were; 12 until
#: About was, from the operator's screenshot the same day.
UNCHECKED_CEILING = 11

#: A device-page tab's record compares the template that draws the tab (templates/v2/device.html
#: includes one per tab); a page's record compares the page's own template.
TAB_TEMPLATES = {"tab:overview": "_overview.html", "tab:intent": "_intent.html",
                 "tab:history": "_history.html", "tab:monitoring": "_monitoring.html",
                 "tab:logs": "_logs.html", "tab:netbox": "_netbox.html",
                 "tab:neighbours": "_neighbours.html", "tab:ask": "_ask.html"}

VERDICTS = ("same", "deviation", "later")


def templates_hash(paths) -> str:
    """sha256 over each compared file, in the order the record names them, path and bytes."""
    h = hashlib.sha256()
    for p in paths:
        h.update(p.encode() + b"\0")
        with open(os.path.join(ROOT, p), "rb") as fh:
            h.update(fh.read())
        h.update(b"\0")
    return h.hexdigest()


def _record(name):
    with open(os.path.join(FIDELITY, name), encoding="utf-8") as fh:
        text = fh.read()
    paths = re.search(r"^Templates compared: (.+)$", text, re.M).group(1)
    paths = [p.strip().strip("`") for p in paths.split(",")]
    digest = re.search(r"^Templates sha256: `?([0-9a-f]{64})`?$", text, re.M).group(1)
    rows = re.findall(r"^\| *(\S[^|]*?) *\|[^\n]*\| *\*\*(\w+)\*\*([^|\n]*)\|$", text, re.M)
    return {"text": text, "paths": paths, "digest": digest, "rows": rows}


def test_every_signed_off_screen_has_a_record_or_is_unchecked():
    assert set(RECORDS) | UNCHECKED == set(SIGNED_OFF), \
        sorted(set(SIGNED_OFF) ^ (set(RECORDS) | UNCHECKED))
    assert not set(RECORDS) & UNCHECKED
    assert len(UNCHECKED) <= UNCHECKED_CEILING, "UNCHECKED only shrinks"
    tabs = {s for s in SIGNED_OFF if s.startswith("tab:")}
    assert tabs <= set(TAB_TEMPLATES), sorted(tabs - set(TAB_TEMPLATES))
    for tpl in TAB_TEMPLATES.values():
        assert os.path.isfile(os.path.join(ROOT, "templates", "v2", tpl)), tpl


def test_each_record_compares_the_templates_as_they_are():
    for screen, name in {**RECORDS, **COMPONENTS}.items():
        r = _record(name)
        assert f"templates/v2/{TAB_TEMPLATES.get(screen, screen)}" in r["paths"], name
        assert templates_hash(r["paths"]) == r["digest"], (
            f"{name}: its templates changed since they were compared with the boards; compare "
            f"them again (tests/test_board_shots.py) and write the hash: "
            f"{templates_hash(r['paths'])}")


def test_every_region_has_a_verdict_and_a_deviation_its_log_line():
    with open(os.path.join(ROOT, "docs", "STANDING_APPROVAL_LOG.md"), encoding="utf-8") as fh:
        log = fh.read()
    for name in {**RECORDS, **COMPONENTS}.values():
        rows = _record(name)["rows"]
        assert len(rows) >= 10, name
        for region, verdict, _rest in rows:
            assert verdict in VERDICTS, (name, region, verdict)
        for region, verdict, rest in rows:
            if verdict == "deviation":
                tag = re.search(r"\(log: ([^)]+)\)", rest)
                assert tag and tag.group(1) in log, (name, region, "names no approval log line")


def test_a_board_the_folder_lacks_is_refused_never_shot_as_a_404(tmp_path, monkeypatch):
    """The board shots serve NMAS_BOARDS_DIR; a board missing from it was shot as the server's
    404 page and the shot passed (2026-10-26: two records' comparisons rested on 404 shots).
    A missing board is refused by name; a present one is served."""
    import pytest

    from tests import test_board_shots as B
    (tmp_path / "Here.dc.html").write_text("<!doctype html><p>a board</p>")
    monkeypatch.setattr(B, "BOARDS", str(tmp_path))
    with B._Boards() as boards:
        assert boards.url("Here.dc.html").endswith("/Here.dc.html")
        assert boards.url("Here.dc.html?v=1").endswith("/Here.dc.html?v=1")
        with pytest.raises(AssertionError, match="board Gone.dc.html is not in NMAS_BOARDS_DIR"):
            boards.url("Gone.dc.html")


def test_a_changed_template_is_refused(tmp_path):
    """The control: a record whose hash no longer matches is found."""
    r = _record(RECORDS["topology.html"])
    assert templates_hash(r["paths"]) == r["digest"]
    assert templates_hash(r["paths"][:-1]) != r["digest"]
