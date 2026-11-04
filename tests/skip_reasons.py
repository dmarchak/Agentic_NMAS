"""The declared skip reasons (C2412, the operator, 2026-11-04): every reason a test may skip
with, and where. Any other skip fails CI's test job and the gate (`scripts/nmas-skip-check`),
so a run that passes with its tests unrun is never green. (Not a test module.)

Each entry is `(name, pattern, places)`. The pattern is anchored at both ends (`re.fullmatch`)
on the JUnit `<skipped message>`, so a reason matches by its whole shape, never as a phrase
inside another (CLAUDE.md, "Match code by parsing or anchoring"). A place is `ci` (GitHub's test
job), `gate` (scripts/nmas-gate) or `local` (the local CI runner).

Left off by the operator's decision, each a failure wherever it appears:
- a browser that cannot start (C2412; `NMAS_REQUIRE_BROWSER=1` fails it at its source);
- root's files read as another uid (C2455: those three tests are deselected in confined runs
  and run unconfined on every gate and CI run instead);
- the month's first day (C2436: a fixed clock instead).

This list only shrinks (tests/ratchet_lists.py).
"""

DECLARED = (
    ("the board shots, run only when asked",
     r"board shots run only when asked \(NMAS_BOARD_SHOTS, NMAS_BOARDS_DIR\)",
     ("ci", "gate", "local")),
    ("the operator's publication denylist, local by design",
     r"\S*/data/publication_denylist\.txt is absent on this machine \(it is local by design\), "
     r"so the denylist rule checked NOTHING here; the other rules ran",
     ("ci",)),
    ("the operator's lab hosts file, local by design",
     r"\S*/data/lab_hosts\.json is absent on this machine; nothing to compare",
     ("ci",)),
)

PLACES = ("ci", "gate", "local")
