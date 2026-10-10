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
RECORDS = {"topology.html": "topology.md", "logs.html": "logs.md"}

#: Signed-off screens built before the fidelity step and not yet compared with their boards
#: (C650). Each is compared, and its differences fixed or logged, before it leaves this list.
UNCHECKED = {
    "landing.html", "devices.html", "bulk_intent.html", "save.html", "device.html",
    "about.html", "monitoring.html", "history.html", "credentials.html", "help.html",
    "templates.html", "apply.html", "monitoring_profile.html", "show_commands.html",
    "show_commands_run.html", "coverage.html", "coverage_deploy.html", "update.html",
    "settings.html", "settings_installation.html", "netbox.html", "pending.html",
    "reapply.html", "retired.html", "tab:ask", "tab:history", "tab:intent", "tab:logs",
    "tab:monitoring", "tab:neighbours", "tab:netbox", "tab:overview",
}
#: Only shrinks.
UNCHECKED_CEILING = 32

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


def test_each_record_compares_the_templates_as_they_are():
    for screen, name in RECORDS.items():
        r = _record(name)
        assert f"templates/v2/{screen}" in r["paths"], name
        assert templates_hash(r["paths"]) == r["digest"], (
            f"{name}: its templates changed since they were compared with the boards; compare "
            f"them again (tests/test_board_shots.py) and write the hash: "
            f"{templates_hash(r['paths'])}")


def test_every_region_has_a_verdict_and_a_deviation_its_log_line():
    with open(os.path.join(ROOT, "docs", "STANDING_APPROVAL_LOG.md"), encoding="utf-8") as fh:
        log = fh.read()
    for name in RECORDS.values():
        rows = _record(name)["rows"]
        assert len(rows) >= 10, name
        for region, verdict, _rest in rows:
            assert verdict in VERDICTS, (name, region, verdict)
        for region, verdict, rest in rows:
            if verdict == "deviation":
                tag = re.search(r"\(log: ([^)]+)\)", rest)
                assert tag and tag.group(1) in log, (name, region, "names no approval log line")


def test_a_changed_template_is_refused(tmp_path):
    """The control: a record whose hash no longer matches is found."""
    r = _record(RECORDS["topology.html"])
    assert templates_hash(r["paths"]) == r["digest"]
    assert templates_hash(r["paths"][:-1]) != r["digest"]
