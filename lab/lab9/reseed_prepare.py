#!/usr/bin/env python3
"""Lab 9: r6's and r7's reseeded intent, PREPARED and CHECKED; nothing is written or committed
(docs/LAB9_PLAN.md section 7, R1). LAB TOOLING: never read by the product. Run on the NMAS host
from its checkout, in Mercury's interpreter: `PYTHONPATH=. python lab/lab9/reseed_prepare.py r6 r7`.

For each device: the committed host_vars text (intent_edit.open_doc, the editor's own read); the
top-level `lines:` block replaced, as text, by the blocks the device holds (read masked
beforehand: vty split as `vty 0`, `vty 1` with `length 0`, `vty 2 4`) and `exec-timeout 15 0`
on `con 0`; every other byte kept. Seed intent cannot do this: it is offered only for absent or
bootstrap-only intent, and it parses the device's saved configuration, which never prints
`no shutdown`, so it would drop each `no_shutdown: true`. It reads INTENT only. Printed: the
text diff (masked), the interfaces declaring no_shutdown before and after (must be equal), and
the new `lines:` block to paste in the Intent editor, whose own two diffs (what the edit
changes, and what a deploy would send) the operator reviews there (R2)."""

import difflib
import sys

import yaml

LIST = "Default"
NEW_LINES = """lines:
- settings:
  - exec-timeout 15 0
  - stopbits 1
  spec: con 0
- settings: []
  spec: aux 0
- settings:
  - logging synchronous
  - login local
  - transport input ssh
  spec: vty 0
- settings:
  - logging synchronous
  - login local
  - length 0
  - transport input ssh
  spec: vty 1
- settings:
  - logging synchronous
  - login local
  - transport input ssh
  spec: vty 2 4
"""


def replace_lines_block(text: str, block: str = NEW_LINES) -> str:
    """*text* with its top-level `lines:` block (the key and every list item and child under
    it) replaced by *block*; every other byte kept. Refuses a document with no such key."""
    out, i, rows = [], 0, text.splitlines(keepends=True)
    while i < len(rows) and rows[i].rstrip("\n") != "lines:":
        out.append(rows[i])
        i += 1
    if i == len(rows):
        raise ValueError("no top-level `lines:` key")
    i += 1
    while i < len(rows) and (rows[i].startswith((" ", "-")) or not rows[i].strip()):
        i += 1
    return "".join(out) + block + "".join(rows[i:])


def no_shutdowns(text: str) -> list:
    """The names of the interfaces *text* declares `no_shutdown: true`, sorted."""
    parsed = yaml.safe_load(text) or {}
    ifaces = parsed.get("interfaces") or {}
    items = ifaces.items() if isinstance(ifaces, dict) else (
        (i.get("name"), i) for i in ifaces if isinstance(i, dict))
    return sorted(str(n) for n, v in items if isinstance(v, dict) and v.get("no_shutdown") is True)


def main(hosts: list) -> int:
    from modules.nsot import intent_edit
    from modules.redact import redact_text

    for host in hosts:
        opened = intent_edit.open_doc(LIST, host)
        if not opened.get("ok"):
            print(f"{host}: {opened.get('error')}")
            return 1
        old = opened["yaml"]
        new = replace_lines_block(old)
        print(f"===== {host} (base blob {opened['base'][:12]})")
        print("--- text diff, committed -> prepared (masked):")
        for d in difflib.unified_diff(old.splitlines(), new.splitlines(), "committed",
                                      "prepared", lineterm="", n=1):
            print("  " + redact_text(d))
        before, after = no_shutdowns(old), no_shutdowns(new)
        print(f"no_shutdown declared: before {before}; after {after}; "
              f"{'KEPT' if before == after else 'CHANGED'}")
        checked = intent_edit.validate(host, new, LIST)
        print("the editor's validation:", "ok" if checked.get("ok") else checked.get("error"))
    print("\n--- the `lines:` block to paste over the old one in the Intent editor:\n" + NEW_LINES)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["r6", "r7"]))
