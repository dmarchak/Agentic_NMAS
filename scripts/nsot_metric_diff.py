#!/usr/bin/env python3
"""Flat vs depth-aware round-trip comparison, construct by construct. Read-only.

The flat comparison scored ``cisco_iosxe/base.j2`` 100% on r3/r4/r5 while its
render hoisted BGP networks and neighbor activations out of their
address-families. That defect was found by checking a *named* item. The metric
would have hidden any others exactly as well, so this enumerates every
construct where the two comparisons disagree rather than assuming BGP was the
only casualty.

The superseded flat implementation is reproduced here verbatim so the
comparison is self-contained and does not depend on git history.

Usage::

    python scripts/nsot_metric_diff.py                 # the fleet fixtures
    python scripts/nsot_metric_diff.py <config-dir>
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.nsot import normalize, roundtrip                 # noqa: E402
from modules.nsot.parsers import get_parser, base as _pbase   # noqa: E402

FLEET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tests", "fixtures", "configs", "fleet")


def sections_flat(config: str) -> dict:
    """The SUPERSEDED implementation: one level, children flattened."""
    out = {}
    for block in _pbase.split_blocks(config):
        header = roundtrip._norm(block.line)
        if not header or header in ("!", "end"):
            continue
        children = [roundtrip._norm(c) for c in block.children
                    if roundtrip._norm(c) not in ("", "!")]
        out.setdefault(header, []).extend(children)
    return out


def nested_constructs(config: str) -> dict:
    """``{outermost header: [nested container paths]}`` — what flattening hid."""
    from modules.nsot import sections as _sec

    found = defaultdict(list)
    for line, chain in _sec.chains(normalize.strip_for_roundtrip(config),
                                   norm=roundtrip._norm):
        if len(chain) >= 2:
            found[chain[0]].append(_sec.path_of(chain))
    return {k: sorted(set(v)) for k, v in found.items()}


def platform_of(name, config):
    if "IOS XE" in config[:400] or "C8000V" in config:
        return "cisco_iosxe"
    return "cisco_ios"


def main() -> int:
    directory = sys.argv[1] if len(sys.argv) > 1 else FLEET
    names = sorted(f[:-4] for f in os.listdir(directory) if f.endswith(".cfg"))

    print("\nflat vs depth-aware round-trip, per device\n")
    header = (f"{'device':<8}{'platform':<14}{'flat fid':>9}{'deep fid':>9}"
              f"{'flat ok':>9}{'deep ok':>9}{'reordered':>11}")
    print(header)
    print("-" * len(header))

    all_nested = defaultdict(set)
    disagreements = []

    for name in names:
        with open(os.path.join(directory, f"{name}.cfg"), encoding="utf-8") as fh:
            config = fh.read()
        platform = platform_of(name, config)
        try:
            hv = get_parser(platform).parse(config)
            rendered = roundtrip.render(hv, platform)
        except Exception as exc:                        # noqa: BLE001
            print(f"{name:<8}{platform:<14}  RENDER FAILED: {exc}")
            continue

        deep = roundtrip.compare(config, rendered, hv)

        original = roundtrip._sections
        roundtrip._sections = sections_flat
        try:
            flat = roundtrip.compare(config, rendered, hv)
        finally:
            roundtrip._sections = original

        print(f"{name:<8}{platform:<14}"
              f"{flat['round_trip_fidelity']:>9.1f}{deep['round_trip_fidelity']:>9.1f}"
              f"{str(flat['ok']):>9}{str(deep['ok']):>9}"
              f"{deep['reordered_sections']:>11}")

        for header_path, paths in nested_constructs(config).items():
            all_nested[header_path].update(paths)

        if (flat["ok"] != deep["ok"]
                or flat["round_trip_fidelity"] != deep["round_trip_fidelity"]
                or flat["missing_from_render"] != deep["missing_from_render"]
                or flat["extra_in_render"] != deep["extra_in_render"]):
            disagreements.append((name, flat, deep))

    print(f"\n{'=' * 72}\nWHERE THE TWO METRICS DISAGREE\n{'=' * 72}")
    if not disagreements:
        print("  nowhere — the two agree on every device in this corpus")
    for name, flat, deep in disagreements:
        print(f"\n  {name}:")
        print(f"     fidelity  {flat['round_trip_fidelity']:.1f} -> {deep['round_trip_fidelity']:.1f}"
              f"    ok {flat['ok']} -> {deep['ok']}")
        print(f"     missing   {flat['missing_from_render']} -> {deep['missing_from_render']}"
              f"    extra {flat['extra_in_render']} -> {deep['extra_in_render']}"
              f"    reordered {flat['reordered_sections']} -> {deep['reordered_sections']}")
        for row in (deep.get("details", {}).get("missing") or [])[:6]:
            print(f"       missing: {row.get('section')} :: {row.get('line')}")
        for row in (deep.get("details", {}).get("extra") or [])[:6]:
            print(f"       extra:   {row.get('section')} :: {row.get('line')}")
        for row in (deep.get("details", {}).get("reordered") or [])[:4]:
            print(f"       reordered: {row.get('section')}")

    print(f"\n{'=' * 72}\nEVERY NESTED CONSTRUCT IN THE CORPUS\n{'=' * 72}")
    print("  (each was compared as ONE level by the flat metric)\n")
    for header_path in sorted(all_nested):
        paths = sorted(all_nested[header_path])
        print(f"  {header_path}")
        for p in paths[:6]:
            print(f"       {p}")
        if len(paths) > 6:
            print(f"       ... {len(paths) - 6} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
