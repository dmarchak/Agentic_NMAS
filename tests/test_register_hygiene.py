"""The register's open rows are open, and each carries its bucket.

Measured 2026-09-28: 31 of the 92 rows in the open sections were FIXED, DONE
or closed in their own status cell and had never moved to Closed, so the open
count read about twice the work there was. The same night, D8 sat CLOSED in
"Scheduled", a section this check did not cover, and every row recorded after
the triage got a home but no BUCKET (C148, blocking the central loop, was filed
as work for 7.3): the severity axis stopped being applied the night it was
defined. So both are now the shape of a row, not a habit.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTER = os.path.join(ROOT, "docs", "OPEN_FINDINGS.md")

#: Every section whose rows are not closed. "Scheduled" included: a row with a
#: home is still a row (C143 was invisible to the triage for having one).
LIVE = ("## A.", "## B.", "## C.", "## D.", "## E.", "## Scheduled")

TAG = re.compile(r"^\*\*\[(A|B|UNKNOWN|C)\b([^\]]*)\]\*\*")
#: A status cell that says the row is finished, after its bucket tag.
DONE = re.compile(r"^(\*\*\[[^\]]*\]\*\*\s*)?\**\s*(FIXED|CLOSED|DONE|MERGED|RE-RUN DONE)\b"
                  r"|^(\*\*\[[^\]]*\]\*\*\s*)?closed\b", re.I)


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


def live_rows(text):
    return [(rid, cells) for sec, rid, cells in rows_by_section(text)
            if sec.startswith(LIVE)]


def done_rows_in_live_sections(text):
    """The status can sit in the third cell or the fourth: in "Scheduled" the
    third is a date and D8's CLOSED was in its "Where" (the first version of
    this check read only the third, and passed with D8 in place)."""
    return [rid for rid, cells in live_rows(text)
            if any(DONE.match(c) for c in cells[2:4])]


def bucket_problems(text):
    """Every live row opens its status cell with ONE bucket: B names what it
    blocks, UNKNOWN names the measurement that would settle it."""
    out = []
    for rid, cells in live_rows(text):
        m = TAG.match(cells[2] if len(cells) > 2 else "")
        if not m:
            out.append(f"{rid}: no bucket")
        elif m.group(1) == "B" and "blocks" not in m.group(2):
            out.append(f"{rid}: B names nothing it blocks")
        elif m.group(1) == "UNKNOWN" and not m.group(2).startswith(":"):
            out.append(f"{rid}: UNKNOWN names no measurement")
        elif "sorted 20" not in m.group(2):
            out.append(f"{rid}: the bucket carries no date it was sorted")
    return out


#: A bucket that places a row in a stage other than Stage 9 (the deferral
#: stage): "C, F → 7.2", "→ P.7", "→ Stage 8", "→ each screen as it is rebuilt".
STAGE_PLACED = re.compile(r"→\s*(7\.\d+|P\.\d+|Stage [1-8]\b|each (?:screen|route))")
OPEN = ("## A.", "## B.", "## C.", "## D.", "## E.")


def stage_work_in_open_sections(text):
    """The open count is a claim about DEFERRED work (the operator,
    2026-09-28). 26 of 61 open rows were `C, F → <stage>`: work a stage owns,
    counted as deferred findings, so the register overstated its backlog by
    about 40%, one level up from the 31 done rows. A row a stage owns lives in
    Scheduled; an open row placed in a stage is the defect."""
    out = []
    for sec, rid, cells in rows_by_section(text):
        if not sec.startswith(OPEN):
            continue
        tag = re.match(r"^\*\*\[([^\]]*)\]\*\*", cells[2] if len(cells) > 2 else "")
        if tag and STAGE_PLACED.search(tag.group(1)):
            out.append(rid)
    return out


def _real():
    return open(REGISTER, encoding="utf-8").read()


def test_no_finished_row_sits_in_a_live_section():
    text = _real()
    rows = rows_by_section(text)
    assert len(live_rows(text)) >= 40, len(live_rows(text))
    assert len([r for r in rows if r[0].startswith("## Closed")]) >= 100
    assert done_rows_in_live_sections(text) == []


def test_every_live_row_carries_its_bucket():
    assert bucket_problems(_real()) == []


def malformed_rows(text):
    """A row whose leading pipe was lost is not a row to any check here, so a
    bad edit could hide a finding from every rule at once (measured
    2026-09-28: a scripted C166 edit dropped the pipe, and every hygiene test
    still passed)."""
    return [ln[:12] for ln in text.split("\n") if re.match(r"^[A-E]\d+ \|", ln)]


def test_no_row_has_lost_its_leading_pipe():
    assert malformed_rows(_real()) == []
    assert malformed_rows("| C1 | ok | x | y |\nC166 | lost | x | y |") == ["C166 | lost "]


#: A table's separator line: `|---|---|`, colons allowed.
SEPARATOR = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")
#: The triage sections' tables are read as the register's state too (C591).
TRIAGE = ("## Triage",)


def tables(text):
    """``(section, header cells, [(line number, row cells)])`` for every table: a
    header is a row whose next line is a separator, and its rows run to the first
    line that is not a row."""
    lines, sec, out, i = text.split("\n"), None, [], 0
    while i < len(lines):
        if lines[i].startswith("## "):
            sec = lines[i]
        if lines[i].startswith("|") and i + 1 < len(lines) and SEPARATOR.match(lines[i + 1]):
            header, rows, j = split_cells(lines[i]), [], i + 2
            while j < len(lines) and lines[j].startswith("|"):
                rows.append((j + 1, split_cells(lines[j])))
                j += 1
            out.append((sec, header, rows))
            i = j
            continue
        i += 1
    return out


def rows_with_the_wrong_cell_count(text):
    """C591 (2026-10-08): C571's live row had three cells, its Where lost to an
    edit, and every check here passed: a row reads by position, so a lost cell
    moves every cell after it. Each row of a live or triage table has exactly its
    header's count."""
    out = []
    for sec, header, rows in tables(text):
        if not (sec and sec.startswith(LIVE + TRIAGE)):
            continue
        for line, cells in rows:
            if len(cells) != len(header):
                out.append(f"{cells[0]} (line {line}): {len(cells)} cells, "
                           f"its table's header has {len(header)}")
    return out


def test_every_live_row_has_its_tables_cell_count():
    text = _real()
    judged = [r for s, _h, rows in tables(text) if s and s.startswith(LIVE + TRIAGE)
              for r in rows]
    assert len(judged) >= 100, len(judged)                  # the floor
    assert rows_with_the_wrong_cell_count(text) == []


def test_a_row_that_lost_a_cell_is_found():
    planted = "\n".join([
        "## C. Tooling that reports wrongly", "| # | Finding | Kind | Where recorded |",
        "|---|---|---|---|",
        "| C900 | a thing | **[C, M; sorted 2026-10-08]** build | here |",
        "| C901 | a thing | **[C, M; sorted 2026-10-08]** build |",
        "| C902 | a `x || y` thing | **[C, M; sorted 2026-10-08]** build | here |",
        "", "## Triage, 2026-09-28: every open row placed", "| Bucket | Rows | Count |",
        "|---|---|---|", "| **A** | C143 | **1** |",
        "## Triage against the charter", "| # | Class | Where | Why |", "|---|---|---|---|",
        "| C143 | CORE | Now |",
        "## Closed", "| # | Finding | Closed | Reason |", "|---|---|---|---|",
        "| C906 | a thing | 2026-09-28 |",
    ])
    assert rows_with_the_wrong_cell_count(planted) == [
        "C901 (line 5): 3 cells, its table's header has 4",
        "C143 (line 15): 3 cells, its table's header has 4"]


def test_no_open_row_is_work_a_stage_owns():
    text = _real()
    assert stage_work_in_open_sections(text) == []
    # The floor: Scheduled really holds the stage work (a check that could
    # pass because the section vanished would prove nothing).
    scheduled = [r for s, r, _c in rows_by_section(text) if s.startswith("## Scheduled")]
    assert len(scheduled) >= 30, len(scheduled)


PLANTED = "\n".join([
    "## C. Tooling that reports wrongly", "| # | Finding | Kind | Where |", "|---|---|---|---|",
    "| C900 | a thing | **[C, M; sorted 2026-09-28]** **FIXED 2026-09-28**: done | here |",
    "| C901 | a thing | closed | here |",
    "| C902 | a `x || y` thing | **[B, later: blocks 7.4; sorted 2026-09-28]** build | here |",
    "| C903 | a thing | build | here |",
    "| C904 | a thing | **[B; sorted 2026-09-28]** build | here |",
    "| C905 | a thing | **[UNKNOWN; sorted 2026-09-28]** measure | here |",
    "| C907 | a thing | **[C, F → 7.2; sorted 2026-09-28]** build | here |",
    "| C908 | a thing | **[C, M → Stage 9; sorted 2026-09-28]** later | here |",
    "| C909 | a thing | **[C, F → each screen as it is rebuilt; sorted 2026-09-28]** | x |",
    "| C910 | a thing | **[C, F → P.7; sorted 2026-09-28]** build | here |",
    "## Scheduled out of the register", "| # | Finding | Scheduled | Where |", "|---|---|---|---|",
    "| D900 | a thing | **[C, F; sorted 2026-09-28]** 2026-09-26 | **CLOSED** by X |",
    "| D901 | a thing | **[C, F → 7.3; sorted 2026-09-28]** 2026-09-28 | **7.3** |",
    "## Closed", "| # | Finding | Closed | Reason |", "|---|---|---|---|",
    "| C906 | a thing | 2026-09-28 | **FIXED** |",
])


def test_the_planted_rows_are_found():
    """The control: a finished row after a tag, a bare one, and one in
    Scheduled are found; a tagged open row is left alone; and a missing
    bucket, a B that blocks nothing and an UNKNOWN with no measurement are
    each named. A Closed row is never examined."""
    assert done_rows_in_live_sections(PLANTED) == ["C900", "C901", "D900"]
    assert bucket_problems(PLANTED) == [
        "C901: no bucket", "C903: no bucket", "C904: B names nothing it blocks",
        "C905: UNKNOWN names no measurement"]
    # Stage work in an open section is named; Stage 9 (the deferral stage)
    # and a stage-placed row already in Scheduled are left alone.
    assert stage_work_in_open_sections(PLANTED) == ["C907", "C909", "C910"]
