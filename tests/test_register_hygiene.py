"""The register's open sections hold only open rows.

Measured 2026-09-28: 31 of the 92 rows in the open sections were FIXED, DONE
or closed in their own status cell and had never moved to Closed, so the open
count read about twice the work there was, and the register was read as more
urgent than it was. A row that is fixed moves in the same turn; this refuses
one that did not.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTER = os.path.join(ROOT, "docs", "OPEN_FINDINGS.md")

#: A status cell that opens with one of these says the row is finished.
DONE = re.compile(r"^\**\s*(FIXED|CLOSED|DONE|MERGED|RE-RUN DONE)\b|^closed\b", re.I)
NOT_OPEN = ("## Closed", "## Scheduled", "## Count", "## Triage")


def split_cells(row):
    """Split a table row on pipes outside backtick code spans (a row may
    quote `a || b`)."""
    cells, cur, code = [], "", False
    for ch in row.strip()[1:-1]:
        if ch == "`":
            code = not code
        if ch == "|" and not code:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
    cells.append(cur.strip())
    return cells


def rows_by_section(text):
    sec, out = None, []
    for line in text.split("\n"):
        if line.startswith("## "):
            sec = line
        m = re.match(r"^\| ([A-Z]\d+) \|", line)
        if m and sec:
            out.append((sec, m.group(1), split_cells(line)))
    return out


def done_rows_in_open_sections(text):
    return [rid for sec, rid, cells in rows_by_section(text)
            if not sec.startswith(NOT_OPEN) and len(cells) > 2 and DONE.match(cells[2])]


def test_no_finished_row_sits_in_an_open_section():
    text = open(REGISTER, encoding="utf-8").read()
    rows = rows_by_section(text)
    open_rows = [r for r in rows if not r[0].startswith(NOT_OPEN)]
    closed = [r for r in rows if r[0].startswith("## Closed")]
    assert len(open_rows) >= 20 and len(closed) >= 100, (len(open_rows), len(closed))
    assert done_rows_in_open_sections(text) == []


def test_a_planted_fixed_row_is_found():
    """The control: the scan sees the shape it forbids, bold or bare, and
    leaves an open row alone."""
    planted = "\n".join([
        "## C. Tooling that reports wrongly", "| # | Finding | Kind | Where |", "|---|---|---|---|",
        "| C900 | a thing | **FIXED 2026-09-28**: done | here |",
        "| C901 | a thing | closed | here |",
        "| C902 | a `x || y` thing | **DECIDED**: build | here |",
        "## Closed", "| # | Finding | Closed | Reason |", "|---|---|---|---|",
        "| C903 | a thing | 2026-09-28 | **FIXED** |",
    ])
    assert done_rows_in_open_sections(planted) == ["C900", "C901"]
