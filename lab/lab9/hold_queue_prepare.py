#!/usr/bin/env python3
"""Lab 9 lever c (C1485, C1547): s3's intent with `hold_queue: ['256 out']` added to its
management uplink GigabitEthernet1/1, as s1 holds it; nothing is written or committed (docs/
LAB9_PLAN.md section 9). LAB TOOLING: never read by the product. Run on the NMAS host from its
checkout, in Mercury's interpreter: `PYTHONPATH=. python lab/lab9/hold_queue_prepare.py`.
Printed: the text diff (masked), the editor's validation, and the lines its deploy preview would
ADD (vs_device '+' lines, masked: lines of the intent)."""

import difflib
import sys

LIST, HOST, IFACE, VALUE = "Default", "s3", "GigabitEthernet1/1", "['256 out']"


def add_hold_queue(text: str, iface: str = IFACE, value: str = VALUE) -> str:
    """*text* with `hold_queue: <value>` added to the `interfaces` item named *iface*, placed in
    key order (the documents are written with sorted keys); every other byte kept. Refuses an
    interface it cannot find, or one that already holds the key."""
    rows = text.splitlines(keepends=True)
    try:
        name_at = next(i for i, r in enumerate(rows) if r.strip() == f"name: {iface}")
    except StopIteration:
        raise ValueError(f"no interface named {iface!r}") from None
    start = max(i for i in range(name_at + 1) if rows[i].startswith("- "))
    end = next((i for i in range(start + 1, len(rows))
                if rows[i].startswith("- ") or not rows[i].startswith((" ", "-"))), len(rows))
    item = rows[start:end]
    if any(r[2:].startswith("hold_queue:") for r in item):
        raise ValueError(f"{iface} already holds hold_queue")
    for i in range(start, end):
        top = rows[i].startswith("- ") or (rows[i].startswith("  ") and rows[i][2] != " ")
        key = rows[i][2:].split(":", 1)[0]
        if top and key > "hold_queue":
            if rows[i].startswith("- "):          # the item's first key carries the dash
                rows[i] = "  " + rows[i][2:]
                return "".join(rows[:i] + [f"- hold_queue: {value}\n"] + rows[i:])
            return "".join(rows[:i] + [f"  hold_queue: {value}\n"] + rows[i:])
    return "".join(rows[:end] + [f"  hold_queue: {value}\n"] + rows[end:])


def main() -> int:
    from modules.nsot import intent_edit
    from modules.redact import redact_text

    opened = intent_edit.open_doc(LIST, HOST)
    if not opened.get("ok"):
        print(f"{HOST}: {opened.get('error')}")
        return 1
    old = opened["yaml"]
    new = add_hold_queue(old)
    print(f"===== {HOST} {IFACE} (base blob {opened['base'][:12]})")
    for d in difflib.unified_diff(old.splitlines(), new.splitlines(), "committed", "prepared",
                                  lineterm="", n=1):
        print("  " + redact_text(d))
    pv = intent_edit.preview(LIST, HOST, new)
    print("validation/preview ok:", pv.get("ok"), pv.get("error") or "")
    adds = [ln for ln in str(pv.get("vs_device") or "").splitlines()
            if ln.startswith("+") and not ln.startswith("+++")]
    print(f"a deploy would add ({len(adds)} line(s)):")
    for ln in adds:
        print("  " + redact_text(ln))
    return 0


if __name__ == "__main__":
    sys.exit(main())
