"""The preflight's forwarding check: no forwarding to or from the lab interface (the operator,
2026-11-05; docs/LAB9_LAPTOP_RUN.md section 7).

    sudo nft -j list table inet lab9guard | python3 -I kit_guard_check.py LAB_IF

The `lab9guard` table `kit start` installs (lab9guard.nft.in) must be present and in force:
- a base chain hooked on forward, a filter at priority -10;
- one rule dropping what comes in on LAB_IF, and one dropping what goes out on it, each with
  its counter.

This is a rule-and-counter check, never the forwarding sysctl: forwarding stays on for the
laptop's containers and VMs. One PASS or FAIL line; exit 0 or 1.
"""
import json
import re
import sys

IFNAME = re.compile(r"^[A-Za-z0-9._-]{1,15}$")


def judge(doc: dict, lab_if: str) -> tuple:
    """``(ok, words)`` for *doc*, `nft -j list table inet lab9guard`'s answer."""
    items = doc.get("nftables", []) if isinstance(doc, dict) else []
    chains = [i["chain"] for i in items if "chain" in i]
    rules = [i["rule"] for i in items if "rule" in i]
    if not any("table" in i and i["table"].get("name") == "lab9guard"
               and i["table"].get("family") == "inet" for i in items):
        return False, "the inet lab9guard table is not loaded (kit start installs it)"
    hooked = [c for c in chains if c.get("hook") == "forward" and c.get("type") == "filter"
              and c.get("prio") == -10]
    if not hooked:
        found = ", ".join(f"{c.get('name')} (hook {c.get('hook')}, type {c.get('type')}, "
                          f"priority {c.get('prio')})" for c in chains) or "none"
        return False, ("no chain is hooked on forward as a filter at priority -10; the "
                       f"table's chains: {found}")
    names = {c["name"] for c in hooked}
    counts = {}
    for key in ("iifname", "oifname"):
        for r in rules:
            if r.get("chain") not in names:
                continue
            ex = r.get("expr", [])
            match = [e["match"] for e in ex if "match" in e]
            if (len(match) == 1 and match[0].get("op") == "=="
                    and match[0].get("left") == {"meta": {"key": key}}
                    and match[0].get("right") == lab_if
                    and any("drop" in e for e in ex)
                    and any("counter" in e for e in ex)):
                counts[key] = next(e["counter"]["packets"] for e in ex if "counter" in e)
                break
    missing = [k for k in ("iifname", "oifname") if k not in counts]
    if missing:
        return False, (f"no counted drop for {' or '.join(missing)} {lab_if!r} in the forward "
                       "chain, so forwarding to or from the lab is not stopped")
    return True, (f"lab9guard in force on {lab_if}: forwarded from the lab dropped "
                  f"{counts['iifname']}, to the lab dropped {counts['oifname']} (packets)")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not IFNAME.match(sys.argv[1]):
        print("FAIL no forwarding to or from the lab interface: LAB_IF is not an interface "
              "name")
        sys.exit(1)
    raw = sys.stdin.read()
    try:
        doc = json.loads(raw) if raw.strip() else {}
    except ValueError:
        doc = {}
    ok, words = judge(doc, sys.argv[1])
    print(f"{'PASS' if ok else 'FAIL'} no forwarding to or from the lab interface: {words}")
    sys.exit(0 if ok else 1)
