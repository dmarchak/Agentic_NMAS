"""routes/change_form.py — a change's form as typed: the settings (each a path, the value it holds
now and the value it becomes) and the ticked devices, read from a request and turned into the
compare-and-set steps the fleet change's core takes (`modules/nsot/fleet_change.py`, over
`modules/nsot/bulk_intent.py`'s steps). Moved here from Bulk intent's screen when Change across
the N ticked… replaced it (board FC phase 2 (f3), PHASE8_PLAN 22.2), unchanged.
"""

from flask import request

#: The form's rows: a new form draws this many, and Add a setting one more, up to MAX_ROWS.
ROWS, MAX_ROWS = 1, 12
#: Typed in a value's box, the setting is not there (before) or is removed (after).
ABSENT_WORD = "(absent)"


def devices_sent() -> list:
    """Each ``device`` the request names, in order, once."""
    return list(dict.fromkeys(d.strip() for d in request.values.getlist("device") if d.strip()))


def rows_sent() -> list:
    """The form's settings as typed, one dict per row, blank rows dropped."""
    paths = request.values.getlist("path")
    before = request.values.getlist("before")
    after = request.values.getlist("after")
    out = []
    for i, path in enumerate(paths):
        row = {"path": path.strip(), "before": (before[i] if i < len(before) else "").strip(),
               "after": (after[i] if i < len(after) else "").strip()}
        if row["path"] or row["before"] or row["after"]:
            out.append(row)
    return out


def value_of(text: str):
    """A typed value: ``(absent)`` is the absent marker; anything else is YAML, so ``514`` is
    a number, ``true`` a boolean and ``{a: 1}`` a mapping, as the intent file holds them."""
    import yaml

    from modules.nsot.bulk_intent import ABSENT

    if text == ABSENT_WORD:
        return dict(ABSENT)
    return yaml.safe_load(text)


def steps_of(rows: list) -> tuple:
    """``(steps, problems)``: each row as the core's step, or why it is not one, by row."""
    steps, problems = [], []
    for n, row in enumerate(rows, 1):
        if not row["path"]:
            problems.append(f"setting {n} names no path")
            continue
        if not row["before"] or not row["after"]:
            problems.append(f"setting {n} ({row['path']}) needs the value it holds now and the "
                            f"value it becomes; type {ABSENT_WORD} for a setting not there, "
                            "or to remove one")
            continue
        try:
            steps.append({"path": row["path"], "before": value_of(row["before"]),
                          "after": value_of(row["after"])})
        except Exception as exc:                      # noqa: BLE001 (said by row)
            problems.append(f"setting {n} ({row['path']}): a value is not YAML: {exc}")
    return steps, problems
