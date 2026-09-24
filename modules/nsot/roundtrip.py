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
    """Is child order insignificant for the container at this **path**?

    *header* is a path now (``router bgp 65002 > address-family ipv4``), so
    every component is tested rather than letting ``^router bgp`` happen to
    match the joined string. **Order-significant anywhere in the path wins**:
    a route-map nested inside an otherwise unordered block is still a
    route-map, and the stricter answer is the safe one when the two rules
    disagree.
    """
    from modules.nsot.sections import PATH_SEPARATOR

    if not header.strip():
        # The top level is a scope, not a section. A template emits globals in
        # its own order and the device renders them in its own; neither is a
        # configuration difference. The flat comparison never checked global
        # ordering either — each top-level line was its own key, and keys are
        # compared as a set — so treating it as ordered would be a NEW rule
        # smuggled in by a change that was only meant to add depth.
        return True

    parts = [p.strip() for p in header.split(PATH_SEPARATOR) if p.strip()]
    if any(rule.match(part) for part in parts for rule in ORDER_SIGNIFICANT_SECTIONS):
        return False
    return any(rule.match(part) for part in parts for rule in UNORDERED_SECTIONS)


def _norm(line: str) -> str:
    """Canonicalise a line for comparison: interface names, whitespace."""
    return re.sub(r"\s+", " ", ifnames.canonicalise_line(line.strip())).strip()


def _leaf_of(path: str) -> str:
    """The config line a container path names, without its ancestors."""
    from modules.nsot.sections import PATH_SEPARATOR
    return path.split(PATH_SEPARATOR)[-1] if path else ""


def _sections(config: str) -> dict:
    """``{container path: [normalised lines directly under it]}``.

    **Depth-aware.** The key is a line's full ancestor path
    (``router bgp 65002 > address-family ipv4``), so a line carries the
    container it belongs to rather than only the top-level block it is
    somewhere inside.

    The previous version built on ``split_blocks()``, which appends every
    indented line to one flat ``children`` list regardless of depth. That made
    a two-level block compare as one level: a render that hoisted BGP networks
    and neighbor activations out of their address-families to the top of
    ``router bgp`` had all the same lines, so it scored **100%** — on the three
    devices whose configs the comparison least understood. The corpus had the
    right shape; the comparison could not see it.

    Repeated containers (``ip sla 1`` twice) are merged; that is what the
    device does too. A line that opens a container appears both as a child of
    its parent and as a key of its own, so a missing container and a missing
    line inside one are different findings.
    """
    from modules.nsot import sections as _sec

    entries = [(line, chain) for line, chain in
               _sec.chains(config.splitlines(), norm=_norm) if line]

    # A line is a container if it appears in something else's ancestry.
    containers = {chain[:depth + 1]
                  for _line, chain in entries
                  for depth in range(len(chain))}

    out = {}
    for line, chain in entries:
        own = chain + (line,)
        if own in containers:
            # Containers are keys, never also children of their parent: the
            # header is already counted once when its key matches, and listing
            # it again under the parent counted it twice.
            #
            # An EMPTY container still gets a key, so `address-family ipv6`
            # whose networks were hoisted away shows as present-but-empty
            # rather than vanishing and taking the difference with it.
            out.setdefault(_sec.path_of(own), [])
        else:
            out.setdefault(_sec.path_of(chain), []).append(line)
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
    # SELF-SIGNED CERTIFICATES OUT, on both sides. The device regenerates
    # its own at boot with a new body and a new `TP-self-signed-<chassis>`
    # name, so keeping them makes every C8000v permanently non-equivalent to
    # its own golden -- measured: three `only_left` and three `only_right`
    # lines, with nothing in the config changed by anyone.
    #
    # Nobody saw it because the drift checker has been off since 2026-08-30,
    # switched off three minutes after a run that flagged all nine devices.
    # Re-enabling it without this flags every C8000v for something correct,
    # which is the condition that silenced it.
    #
    # Narrow: a CA-signed trustpoint is configuration somebody chose, and a
    # change to it is real drift.
    left_sections = _sections("\n".join(normalize.strip_self_signed_certs(
        normalize.strip_for_diff(left or ""))))
    right_sections = _sections("\n".join(normalize.strip_self_signed_certs(
        normalize.strip_for_diff(right or ""))))

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


def canonical_lines(text: str) -> list:
    """A config as path-qualified lines, for a diff a PERSON reads.

    The Template preview diffed two normalised line lists with ``difflib``.
    That reports two things as differences that are not differences in
    configuration:

    * **order**, in sections where the device itself does not care. IOS
      reorders interface sub-commands on its own, so a render that emits them
      in template order shows a wall of moved lines;
    * **indentation**, which ``_norm`` already collapses but which survived
      because the preview normalised and then compared raw strings anyway.

    The machinery to answer both already existed and the preview was not
    using it. :func:`section_is_unordered` knows which containers care about
    order; :func:`_sections` knows what is inside each one.

    Children are sorted **only** where order is insignificant. An ACL, a
    prefix-list, a route-map or an ``ip sla`` keeps its sequence, because
    reordering those changes what the device does — and a diff that hid that
    would be worse than one that cries wolf.

    Not a config: it is a canonical rendering for comparison. Each line
    carries its container path, so a difference says where it is instead of
    leaving the reader to count indentation in a unified diff.
    """
    # BOTH filters, in this order, and they do different jobs.
    # `strip_for_roundtrip` removes what a template CANNOT render -- without
    # it, every unrenderable line in the capture reads as a difference from a
    # render that could never have contained it. `strip_for_diff` then
    # normalises for comparison and drops bare `!` separators.
    stripped = normalize.strip_for_diff(
        "\n".join(normalize.strip_for_roundtrip(text or "")))
    sections = _sections("\n".join(stripped))
    out = []
    for path in sorted(sections):
        children = sections[path]
        if section_is_unordered(path):
            children = sorted(children)
        out.append(path if path.strip() else "(global)")
        out.extend(f"    {child}" for child in children)
    return out


#: What a neutralised secret value reads as in a canonical diff.
#:
#: Deliberately not the mask itself. `render_artifact.MASK` is a run of
#: bullets, which in a diff looks like a value that differs from the real one;
#: this says the comparison did not happen.
MASKED_TOKEN = "<masked - not compared>"


def _masked_pair(rendered: str, captured: str):
    """Are these the same line differing ONLY inside the mask?

    A preview renders with secrets masked while the capture holds the real
    value, so a secret-bearing line differs on every comparison, for ever.
    That is not drift and reporting it as drift trains people to scroll past
    the section where real drift would appear.

    Matching on the prefix and suffix around the mask is what keeps the line
    itself under comparison: `snmp-server community ****** RO` and
    `snmp-server community ****** RW` do NOT pair, because only the *value*
    is unknowable, not the line.
    """
    from modules.nsot.render_artifact import MASK

    if MASK not in rendered:
        return None
    head, _, tail = rendered.partition(MASK)
    if not captured.startswith(head) or not captured.endswith(tail):
        return None
    # The mask must stand for at least something, or an empty value would
    # pair with any line sharing the prefix and suffix.
    if len(captured) < len(head) + len(tail):
        return None
    return head + MASKED_TOKEN + tail


def _neutralise(left: list, right: list):
    """Pair masked lines between the two sides. Returns (left, right, count).

    *right* is the rendered side (the one carrying masks); *left* is the
    capture. A masked line with no counterpart is left alone and shows as a
    difference, because then something other than the value changed.
    """
    left, right, masked = list(left), list(right), 0
    for index, rendered in enumerate(right):
        for other, captured in enumerate(left):
            paired = _masked_pair(rendered, captured)
            if paired is None:
                continue
            right[index] = paired
            left[other] = paired
            masked += 1
            break
    return left, right, masked


def canonical_diff(left: str, right: str, *, fromfile: str = "left",
                   tofile: str = "right", report_masked: bool = False):
    """Unified diff over :func:`canonical_lines`. Empty when equivalent.

    Masked lines are neutralised rather than reported: see :func:`_masked_pair`.
    With ``report_masked`` the return is ``(diff, masked_count)``, so a caller
    can say *how many* lines could not be compared instead of leaving the
    operator to infer it from silence.
    """
    import difflib

    left_lines, right_lines, masked = _neutralise(
        canonical_lines(left), canonical_lines(right))
    diff = "\n".join(difflib.unified_diff(
        left_lines, right_lines, fromfile=fromfile, tofile=tofile, lineterm=""))
    return (diff, masked) if report_masked else diff


def compare(running_config: str, rendered_config: str, host_vars: dict = None) -> dict:
    """Compare a rendered config against the real one. Returns a coverage report."""
    running = _sections("\n".join(normalize.strip_for_roundtrip(running_config)))
    rendered = _sections("\n".join(normalize.strip_for_roundtrip(rendered_config)))

    matched, missing, extra, reordered = [], [], [], []

    for header, run_children in running.items():
        # "" is the global SCOPE, not a section. It has no config line of its
        # own, so it contributes no section-level entry — counting one would
        # add a match for a thing that does not exist, and it did: a wholly
        # unknown config scored 16.7% instead of 0.
        scope = not header
        if header not in rendered:
            if not scope:
                missing.append({"section": header, "line": _leaf_of(header),
                                "kind": "section"})
            missing.extend({"section": header, "line": c, "kind": "child"}
                           for c in run_children)
            continue

        if not scope:
            matched.append({"section": header, "line": _leaf_of(header),
                            "kind": "section"})
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
            if header:
                extra.append({"section": header, "line": _leaf_of(header),
                              "kind": "section"})
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
