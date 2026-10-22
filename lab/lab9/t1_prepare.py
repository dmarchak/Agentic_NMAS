#!/usr/bin/env python3
"""Lab 9 T1 (C1547): routers' telemetry subscription 101 changed in their committed intent, as
TEXT, in two variants; nothing is written or committed (docs/LAB9_PLAN.md section 7, T1). LAB
TOOLING: never read by the product. Run on the NMAS host from its checkout, in Mercury's
interpreter: `PYTHONPATH=. python lab/lab9/t1_prepare.py r1 r6 r7`.

Variant A narrows 101's xpath to the one leaf anything reads (`one-minute`: the device
dashboard's two CPU panels); 101 today carries every process's counters, about 146 KiB every
10 s per router, which the collector flattens to one process per update. Variant B keeps the
xpath and slows 101 to `periodic 6000` (60 s). For each: the text diff (masked), the editor's
validation, and the lines the editor's deploy preview would ADD (its `vs_device` '+' lines only,
masked: lines of the intent, never of the device)."""

import difflib
import sys

LIST = "Default"
OLD_FILTER = "  - filter xpath /process-cpu-ios-xe-oper:cpu-usage/cpu-utilization\n"
NEW_FILTER = "  - filter xpath /process-cpu-ios-xe-oper:cpu-usage/cpu-utilization/one-minute\n"


def variant(text: str, which: str) -> str:
    """*text* with subscription 101 changed: "A" swaps its filter for the `one-minute` leaf, "B"
    its `update-policy periodic 1000` for `6000`. 101's block runs from its filter line to its
    `subscription: '101'` line. Refuses a document without exactly one 101 filter, or (B) a
    block without exactly one `periodic 1000`."""
    if text.count(OLD_FILTER) != 1:
        raise ValueError(f"expected one 101 filter line, found {text.count(OLD_FILTER)}")
    if which == "A":
        return text.replace(OLD_FILTER, NEW_FILTER)
    if which != "B":
        raise ValueError(f"variant {which!r}: A or B")
    start = text.index(OLD_FILTER)
    end = text.index("subscription: '101'", start)
    block = text[start:end]
    if block.count("update-policy periodic 1000") != 1:
        raise ValueError("101's block has no single `update-policy periodic 1000`")
    return (text[:start] + block.replace("update-policy periodic 1000",
                                         "update-policy periodic 6000") + text[end:])


def main(hosts: list, variants=("A", "B")) -> int:
    from modules.nsot import intent_edit
    from modules.redact import redact_text

    for host in hosts:
        opened = intent_edit.open_doc(LIST, host)
        if not opened.get("ok"):
            print(f"{host}: {opened.get('error')}")
            return 1
        old = opened["yaml"]
        for which in variants:
            new = variant(old, which)
            print(f"===== {host}, variant {which} (base blob {opened['base'][:12]})")
            for d in difflib.unified_diff(old.splitlines(), new.splitlines(), "committed",
                                          "prepared", lineterm="", n=0):
                if d.startswith(("+", "-")) and not d.startswith(("+++", "---")):
                    print("  text " + redact_text(d))
            pv = intent_edit.preview(LIST, host, new)
            print("  validation/preview ok:", pv.get("ok"), pv.get("error") or "")
            adds = [ln for ln in str(pv.get("vs_device") or "").splitlines()
                    if ln.startswith("+") and not ln.startswith("+++")]
            print(f"  a deploy would add ({len(adds)} line(s)):")
            for ln in adds:
                print("    " + redact_text(ln))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["r1", "r6", "r7"]))
