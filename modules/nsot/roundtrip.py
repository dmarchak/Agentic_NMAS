"""nsot/roundtrip.py

Round-trip validation: render(template, host_vars) vs. the real config.

**Comparison model.** Top level is compared as a *set* of section headers,
because IOS canonicalises top-level ordering itself — the order you type
commands in is not the order the device reports them, so top-level order is not
semantic. Within a section, children are compared **in order by default**.

That default matters: a reordered ACL is a different ACL. A reordered
``prefix-list`` or ``route-map`` sequence changes what matches first. Passing
those as equivalent would report success for a silent traffic-behaviour change.

The unordered allowlist is deliberately short, and each entry has a reason:

* BGP neighbors, OSPF/RIP ``network`` statements, ``snmp-server host``,
  ``ntp server``, ``logging host`` — the device treats these as a set.
* interface bodies — IOS reorders interface sub-commands itself, so the order
  in ``show running-config`` is the device's, not the operator's.

**Coverage.** Reported honestly, per the agreed formula:

``modeled_coverage = matched / (matched + missing_from_render + unmodeled)``

``unmodeled`` counts *against* modelled coverage: a line parked in a raw
pass-through block round-trips but is not modelled. ``round_trip_fidelity``
is reported separately — it answers "does the config reproduce", which is a
different question from "do we understand it".
"""

import logging
import os
import re

from modules.nsot import ifnames, normalize
from modules.nsot.parsers.base import split_blocks

log = logging.getLogger(__name__)

TEMPLATE_ROOT = os.path.join(os.path.dirname(__file__), "templates")

#: Sections whose children the device treats as a set. Everything else is
#: compared in order.
UNORDERED_SECTIONS = (
    re.compile(r"^router bgp\b"),
    re.compile(r"^router ospf\b"),
    re.compile(r"^router rip\b"),
    re.compile(r"^ipv6 router\b"),
    re.compile(r"^interface\b"),        # IOS reorders interface sub-commands
    re.compile(r"^vrf definition\b"),
    re.compile(r"^line\b"),
)

#: Sections whose child order is semantic. Listed explicitly so the intent is
#: recorded even though "ordered" is already the default.
ORDER_SIGNIFICANT_SECTIONS = (
    re.compile(r"^ip access-list\b"),
    re.compile(r"^ipv6 access-list\b"),
    re.compile(r"^ip prefix-list\b"),
    re.compile(r"^route-map\b"),
    re.compile(r"^class-map\b"),
    re.compile(r"^policy-map\b"),
    re.compile(r"^ip sla\b"),
)


def section_is_unordered(header: str) -> bool:
    text = header.strip()
    if any(p.match(text) for p in ORDER_SIGNIFICANT_SECTIONS):
        return False
    return any(p.match(text) for p in UNORDERED_SECTIONS)


def _norm(line: str) -> str:
    """Canonicalise a line for comparison: interface names, whitespace."""
    return re.sub(r"\s+", " ", ifnames.canonicalise_line(line.strip())).strip()


def _sections(config: str) -> dict:
    """``{normalised header: [normalised children]}``.

    Repeated headers (``ip sla 1`` twice) are merged; that is what the device
    does too.
    """
    out = {}
    for block in split_blocks(config):
        header = _norm(block.line)
        if not header or header in ("!", "end"):
            continue
        children = [_norm(c) for c in block.children if _norm(c) not in ("", "!")]
        out.setdefault(header, []).extend(children)
    return out


def render(host_vars: dict, platform: str, secret_lookup=None,
           template_root: str = TEMPLATE_ROOT, template_name: str = "base.j2") -> str:
    """Render host_vars through a platform template.

    *template_root* lets the caller point at a network's own template library
    in its repo instead of the built-in seeds; *template_name* selects a
    non-default template within the platform directory.
    """
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    secrets = dict(host_vars.get("secrets") or {})

    def _secret(name):
        if secret_lookup is not None:
            value = secret_lookup(name)
            if value:
                return value
        # Hashes are emitted verbatim: a type-5/8/9 secret carries a per-hash
        # salt and cannot be regenerated, so this is the only correct behaviour.
        return secrets.get(name, f"<missing-secret:{name}>")

    env = Environment(
        loader=FileSystemLoader([os.path.join(template_root, platform), template_root]),
        undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=False,
        keep_trailing_newline=True,
    )
    def _resolve_markers(text):
        """Expand ``__secret__:ref`` markers inside an otherwise opaque string."""
        import re as _re
        return _re.sub(r"__secret__:(\S+)", lambda m: _secret(m.group(1)), str(text))

    env.globals["secret"] = _secret
    env.filters["resolve_secrets"] = _resolve_markers
    template = env.get_template(template_name)
    return template.render(vars=host_vars, secret=_secret)


def configs_equivalent(left: str, right: str) -> dict:
    """Are two **complete** configs the same network state?

    ``{"equal": bool, "only_left": [...], "only_right": [...]}``.

    Section-aware and volatile-line aware: headers with their children, over
    :func:`normalize.strip_for_diff` output. A flat list comparison decides on
    bare ``!`` lines and on ordering, neither of which is a difference in
    configuration — and a baseline tag that turns on those is a tag that is
    wrong for reasons nobody can act on.

    For **complete** configs only. A rendered template is a statement of
    intent, not a whole config, so comparing one against a device here would
    report every unmodelled construct as a difference. That question is
    ``compare()``, and it is a different question.
    """
    left_sections = _sections("\n".join(normalize.strip_for_diff(left or "")))
    right_sections = _sections("\n".join(normalize.strip_for_diff(right or "")))

    only_left, only_right = [], []
    for header in sorted(set(left_sections) | set(right_sections)):
        a = left_sections.get(header)
        b = right_sections.get(header)
        if a is None:
            only_right.append(header)
            continue
        if b is None:
            only_left.append(header)
            continue
        for child in a:
            if child not in b:
                only_left.append(f"{header} :: {child}")
        for child in b:
            if child not in a:
                only_right.append(f"{header} :: {child}")

    return {"equal": not only_left and not only_right,
            "only_left": only_left, "only_right": only_right}


def compare(running_config: str, rendered_config: str, host_vars: dict = None) -> dict:
    """Compare a rendered config against the real one. Returns a coverage report."""
    running = _sections("\n".join(normalize.strip_for_roundtrip(running_config)))
    rendered = _sections("\n".join(normalize.strip_for_roundtrip(rendered_config)))

    matched, missing, extra, reordered = [], [], [], []

    for header, run_children in running.items():
        if header not in rendered:
            missing.append({"section": header, "line": header, "kind": "section"})
            missing.extend({"section": header, "line": c, "kind": "child"}
                           for c in run_children)
            continue

        matched.append({"section": header, "line": header, "kind": "section"})
        ren_children = rendered[header]

        if section_is_unordered(header):
            run_set, ren_set = list(run_children), list(ren_children)
            for child in run_children:
                if child in ren_set:
                    ren_set.remove(child)
                    matched.append({"section": header, "line": child, "kind": "child"})
                else:
                    missing.append({"section": header, "line": child, "kind": "child"})
            extra.extend({"section": header, "line": c, "kind": "child"} for c in ren_set)
        else:
            if run_children == ren_children:
                matched.extend({"section": header, "line": c, "kind": "child"}
                               for c in run_children)
            elif sorted(run_children) == sorted(ren_children):
                # Same entries, different order. For an ACL or a route-map that
                # is a behaviour change, so it is a failure, reported distinctly
                # from missing/extra so it cannot be mistaken for one.
                reordered.append({"section": header,
                                  "running": run_children, "rendered": ren_children})
                matched.extend({"section": header, "line": c, "kind": "child"}
                               for c in run_children)
            else:
                ren_remaining = list(ren_children)
                for child in run_children:
                    if child in ren_remaining:
                        ren_remaining.remove(child)
                        matched.append({"section": header, "line": child, "kind": "child"})
                    else:
                        missing.append({"section": header, "line": child, "kind": "child"})
                extra.extend({"section": header, "line": c, "kind": "child"}
                             for c in ren_remaining)

    for header, ren_children in rendered.items():
        if header not in running:
            extra.append({"section": header, "line": header, "kind": "section"})
            extra.extend({"section": header, "line": c, "kind": "child"}
                         for c in ren_children)

    unmodeled_lines = _count_unmodeled(host_vars or {})
    matched_count = len(matched)
    # Unmodeled lines round-trip (the template re-emits them) so they are inside
    # `matched`. Subtract them so they are not double-counted as modelled.
    modeled_matched = max(matched_count - unmodeled_lines, 0)
    denominator = modeled_matched + len(missing) + unmodeled_lines

    return {
        "matched": matched_count,
        "modeled_matched": modeled_matched,
        "missing_from_render": len(missing),
        "extra_in_render": len(extra),
        "unmodeled": unmodeled_lines,
        "reordered_sections": len(reordered),
        "modeled_coverage": round(100.0 * modeled_matched / denominator, 1) if denominator else 0.0,
        "round_trip_fidelity": round(
            100.0 * matched_count / (matched_count + len(missing)), 1
        ) if (matched_count + len(missing)) else 0.0,
        # Named, so "100%" never travels without what it did not examine.
        # Information, not a gate — template_report decides deployability.
        "excluded_unrenderable": normalize.excluded_unrenderable(running_config),
        "ok": not missing and not extra and not reordered,
        "details": {"missing": missing, "extra": extra, "reordered": reordered},
    }


def _count_unmodeled(host_vars: dict) -> int:
    """Lines carried verbatim in `unmodeled` blocks, device-wide."""
    total = 0
    for entry in host_vars.get("unmodeled", []):
        total += 1 + len(entry.get("children", []))
    for iface in host_vars.get("interfaces", []):
        total += len(iface.get("unmodeled", []))
    return total


def validate_device(running_config: str, platform: str,
                    secret_lookup=None) -> dict:
    """Extract → render → compare, in one call. The 3a deliverable."""
    from modules.nsot.parsers import get_parser

    host_vars = get_parser(platform).parse(running_config)
    parser_platform = host_vars.get("platform", platform)
    try:
        rendered = render(host_vars, parser_platform, secret_lookup)
    except Exception as exc:                  # noqa: BLE001
        log.exception("roundtrip: render failed for %s", host_vars.get("hostname"))
        return {"ok": False, "error": f"render failed: {exc}",
                "hostname": host_vars.get("hostname", ""), "host_vars": host_vars}

    report = compare(running_config, rendered, host_vars)
    report["hostname"] = host_vars.get("hostname", "")
    report["platform"] = parser_platform
    report["host_vars"] = host_vars
    report["rendered"] = rendered
    return report


def rank_unmodeled(reports: list) -> list:
    """Rank unmodeled constructs across devices — the 'what to model next' list."""
    from collections import Counter

    counter = Counter()
    devices = {}
    for report in reports:
        host_vars = report.get("host_vars") or {}
        hostname = report.get("hostname", "?")
        for entry in host_vars.get("unmodeled", []):
            key = " ".join(entry["line"].strip().split()[:2])
            counter[key] += 1
            devices.setdefault(key, set()).add(hostname)
        for iface in host_vars.get("interfaces", []):
            for line in iface.get("unmodeled", []):
                key = " ".join(line.split()[:2])
                counter[key] += 1
                devices.setdefault(key, set()).add(hostname)

    return [{"construct": key, "occurrences": count,
             "devices": sorted(devices.get(key, [])),
             "device_count": len(devices.get(key, []))}
            for key, count in counter.most_common()]
