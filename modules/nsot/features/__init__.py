"""nsot/features — feature packs: structured, vendor-neutral intent for one feature each (K7,
register C764; the design in docs/FEATURE_PACKS.md).

A pack is four things, and the routing packs here (OSPFv2, OSPFv3, RIPv2, RIPng) are the
first:

(a) **a schema**: the fields of its section of intent, with their empty values
    (`ospf.PROCESS`, `rip.RIP`, ...), and the checks a value must pass (`problems`), each
    refusal naming the field, the value and what it was compared with;
(b) **a partial per dialect**: the Jinja macros that render the fields (the routing packs'
    section of `templates/_common.j2`, which each dialect's `base.j2` imports, the loader
    looking in the dialect's directory first; both Cisco dialects print these lines alike, so
    one copy serves both). They live in `_common.j2` rather than a file of their own so that a
    network's library takes them in ONE file, the one "Bring in the shipped version" already
    brings (C566);
(c) **parsing**: the dialect parser hands each line of a block to the pack
    (`ospf.claim_process`, `ospf.claim_interface_line`, ...). A line becomes a field only when
    the dialect's partial renders that field back as exactly that line (`reproduces`); every
    other line stays where it was before the packs, verbatim and in order (`settings`,
    `networks`, `raw`, an interface's `ospf`/`ospfv3`/`ripng` lists), so
(d) **the round trip of every capture is what it was**: the render of a capture's parse
    reproduces the capture, and an intent written before the packs (its lines only) renders
    byte for byte as it did.

**A library from before the packs** (a network's `_common.j2` seeded or brought in before
them, which reads none of their fields) is not left to drop them: the render writes a pack's
fields as the lines the SHIPPED partial renders for them, into the lists such a library emits
verbatim (`for_library`), so structured intent renders the same lines through it.

Nothing here contacts a device or writes a file.
"""

import copy
import functools
import ipaddress
import logging
import os
import re

log = logging.getLogger(__name__)

BUILTIN_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
#: The shipped file holding the packs' macros.
PARTIAL = "_common.j2"
#: Names only the packs' macros read: a template closure naming none of them predates the
#: packs (`library_reads_packs`).
MARKERS = frozenset({"ospf_interface", "ospfv3_interface", "ripng_interface",
                     "classful_networks", "passive_default", "no_passive_interfaces"})


class FeatureIntentInvalid(ValueError):
    """Structured intent a pack refuses to render; the message names every field and value."""


# ── the schema's machinery ───────────────────────────────────────────────────

class ListOf:
    """A list field whose items follow *spec* (a dict spec) or are plain strings (None)."""

    def __init__(self, spec=None):
        self.spec = spec


class DictOf:
    """A mapping field following *spec*; ``{}`` when nobody set it."""

    def __init__(self, spec):
        self.spec = spec


def complete(node, spec: dict) -> dict:
    """A copy of *node* with every field of *spec* present: a scalar as a string ("" when
    unset), a boolean as itself, a tri-state (default None) as given, a list or mapping
    completed item by item. Keys *spec* does not name are kept, untouched."""
    node = dict(node or {})
    out = dict(node)
    for key, default in spec.items():
        value = node.get(key)
        if isinstance(default, ListOf):
            items = value if isinstance(value, list) else []
            out[key] = [complete(i, default.spec) if default.spec is not None
                        else _scalar(i) for i in items]
        elif isinstance(default, DictOf):
            out[key] = complete(value if isinstance(value, dict) else {}, default.spec)
        elif isinstance(default, bool):
            out[key] = default if value is None else bool(value)
        elif default is None:
            out[key] = value
        else:
            out[key] = _scalar(value)
    return out


def _scalar(value) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return str(value)


def compact(node: dict, spec: dict, keep=()) -> dict:
    """*node* without the fields that hold their empty value (what a parser emits for an
    item: only what the line said), the *keep* keys always."""
    out = {}
    for key, value in node.items():
        default = spec.get(key, object())
        if key in keep:
            out[key] = value
        elif isinstance(default, ListOf):
            if value:
                out[key] = [compact(v, default.spec) if default.spec is not None
                            and isinstance(v, dict) else v for v in value]
        elif isinstance(default, DictOf):
            inner = compact(value, default.spec) if isinstance(value, dict) else value
            if inner:
                out[key] = inner
        elif isinstance(default, bool):
            if bool(value) != default:
                out[key] = value
        elif default is None:
            if value is not None:
                out[key] = value
        elif value not in ("", None):
            out[key] = value
    return out


# ── the partial, rendered from Python (the parser's check, the readers' view) ────────────

@functools.lru_cache(maxsize=8)
def partials(platform: str):
    """The packs' macros for *platform*, from the SHIPPED templates, found as the render finds
    them (the dialect's directory first, then the shared root)."""
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(loader=FileSystemLoader([os.path.join(BUILTIN_ROOT, platform or ""),
                                               BUILTIN_ROOT]),
                      undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=False,
                      keep_trailing_newline=True)
    # The file's other macros name these; the packs' macros never call them.
    env.globals["secret"] = lambda _name: ""
    env.filters["resolve_secrets"] = str
    return env.get_template(PARTIAL).module


@functools.lru_cache(maxsize=64)
def _reads_packs(root: str, platform: str, name: str, _signature: str) -> bool:
    from modules.nsot.config_check import template_reads
    return bool(MARKERS & template_reads(root, platform, name))


def library_reads_packs(root: str, platform: str, name: str) -> bool:
    """Does the template *name* (with everything it imports) in the library at *root* render
    the packs' fields? False for a library from before them. Cached by the library's own
    signature (`templates_repo.library_signature`), so an edit is seen; True when the closure
    cannot be read (the render then names what is wrong itself)."""
    from modules.nsot.templates_repo import library_signature
    try:
        return _reads_packs(root, platform, name, library_signature(root))
    except Exception as exc:                       # noqa: BLE001 - the render says it
        log.debug("features: the reads of %s/%s/%s are unreadable: %s", root, platform,
                  name, exc)
        return True


def for_library(host_vars: dict, root: str, platform: str, name: str) -> dict:
    """*host_vars* (prepared) as the library at *root* can render it: as it is when the library
    renders the packs, else with every pack field written as its lines (`raw_view`, by the
    shipped partial), which a library from before the packs emits verbatim. Raises when that
    cannot be done, never returns fields such a library would drop silently."""
    if not structured(host_vars) or library_reads_packs(root, platform, name):
        return host_vars
    return raw_view(host_vars, platform, strict=True)


def body_lines(platform: str, macro: str, *args) -> list:
    """The lines *macro* renders for *args*, stripped, in order."""
    text = str(getattr(partials(platform), macro)(*args))
    return [line.strip() for line in text.splitlines() if line.strip()]


def reproduces(platform: str, macro: str, args: tuple, line: str) -> bool:
    """Does the partial render *args* as exactly *line* and nothing else? The test that lets a
    parser model a line: a line it cannot reproduce stays verbatim."""
    try:
        return body_lines(platform, macro, *args) == [line.strip()]
    except Exception as exc:                       # noqa: BLE001 - unmodelled, never lost
        log.debug("features: %s cannot render %r: %s", macro, line, exc)
        return False


# ── value checks shared by the packs ─────────────────────────────────────────

def is_int(value, low: int, high: int) -> bool:
    text = _scalar(value)
    return text.isdigit() and low <= int(text) <= high


def is_ipv4(value) -> bool:
    try:
        ipaddress.IPv4Address(_scalar(value))
        return True
    except ValueError:
        return False


def area_number(value):
    """An OSPF area id as its 32-bit number (``10`` and its dotted-quad form are one area), or
    None."""
    text = _scalar(value)
    if text.isdigit() and int(text) <= 0xFFFFFFFF:
        return int(text)
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", text) and is_ipv4(text):
        return int(ipaddress.IPv4Address(text))
    return None


def token(value) -> bool:
    """A name IOS takes as one word (an interface, a route-map, a RIPng process)."""
    text = _scalar(value)
    return bool(text) and not re.search(r"\s", text) and text.isprintable()


def dotted(path: tuple, key: str = "") -> str:
    from modules.nsot.hostvars import dotted as _dotted
    return _dotted(path, key)


# ── the whole document ───────────────────────────────────────────────────────

def problems(host_vars: dict) -> list:
    """``[(path, key, message)]``: every structured routing field of *host_vars* a pack refuses,
    in document order; ``[]`` when none. A raw line is never judged here: it renders as typed,
    as it always did."""
    from modules.nsot.features import ospf, rip

    hv = host_vars if isinstance(host_vars, dict) else {}
    found = []
    found += ospf.problems(hv)
    found += rip.problems(hv)
    return found


def prepare(host_vars: dict) -> dict:
    """A copy of *host_vars* whose routing sections and interfaces carry every pack field the
    partial reads, an authored ``prefix`` written out in the dialect's notation; refused, naming
    every bad field, when a pack refuses one (`problems`). The render calls it beside
    `complete_schema`, so a field absent from an intent renders nothing."""
    from modules.nsot.features import ospf, rip

    if not isinstance(host_vars, dict):
        return host_vars
    found = problems(host_vars)
    if found:
        raise FeatureIntentInvalid("; ".join(message for _p, _k, message in found))
    out = dict(host_vars)
    routing = out.get("routing")
    if isinstance(routing, dict):
        routing = dict(routing)
        routing["ospf"] = [ospf.complete_process(p, "ipv4") if isinstance(p, dict) else p
                           for p in routing.get("ospf") or []]
        routing["ospfv3"] = [ospf.complete_process(p, "ipv6") if isinstance(p, dict) else p
                             for p in routing.get("ospfv3") or []]
        if isinstance(routing.get("rip"), dict):
            routing["rip"] = rip.complete_rip(routing["rip"])
        routing["ripng"] = [rip.complete_ripng(p) if isinstance(p, dict) else p
                            for p in routing.get("ripng") or []]
        out["routing"] = routing
    if isinstance(out.get("interfaces"), list):
        out["interfaces"] = [complete_interface(i) if isinstance(i, dict) else i
                             for i in out["interfaces"]]
    return out


def complete_interface(iface: dict) -> dict:
    from modules.nsot.features import ospf, rip

    out = dict(iface)
    out["ospf_interface"] = complete(iface.get("ospf_interface") or {}, ospf.INTERFACE)
    out["ospfv3_interface"] = complete(iface.get("ospfv3_interface") or {}, ospf.INTERFACE)
    out["ripng_interface"] = [complete(e, rip.RIPNG_INTERFACE)
                              for e in iface.get("ripng_interface") or []
                              if isinstance(e, dict)]
    return out


def settle(host_vars: dict, platform: str) -> dict:
    """A parse's last step: a pack element whose fields break a rule BETWEEN elements (an
    interface naming a process the routing section does not hold, which a line-by-line parse
    cannot see) goes back to its lines, verbatim, so a capture's parse always renders (`prepare`
    refuses nothing a parser emits). Returns *host_vars*, changed in place."""
    from modules.nsot.features import ospf, rip

    for _attempt in range(2):
        found = problems(host_vars)
        if not found:
            return host_vars
        routing = host_vars.get("routing") or {}
        for path, key, message in found:
            log.info("features: %s on %s; its lines stay unmodelled",
                     message, host_vars.get("hostname", ""))
            if path[:1] == ("interfaces",) and len(path) >= 2:
                # Only the refused field goes back to lines; the interface's others stand.
                i, field = path[1], (path[2] if len(path) >= 3 else key)
                iface = host_vars["interfaces"][i]
                done = complete_interface(iface)
                if field == "ripng_interface":
                    back = rip.raw_interface(done, platform)
                else:
                    back = ospf.raw_interface(done, platform,
                                              kinds=(field.replace("_interface", ""),))
                host_vars["interfaces"][i] = {**iface, field: back[field],
                                              field.replace("_interface", ""):
                                              back[field.replace("_interface", "")]}
            elif path[:2] in (("routing", "ospf"), ("routing", "ospfv3")) and len(path) >= 3:
                family = "ipv4" if path[1] == "ospf" else "ipv6"
                proc = routing[path[1]][path[2]]
                routing[path[1]][path[2]] = ospf.raw_process(
                    ospf.complete_process(proc, family), family, platform)
            elif path[:2] == ("routing", "rip"):
                routing["rip"] = rip.raw_rip(rip.complete_rip(routing["rip"]), platform)
            elif path[:2] == ("routing", "ripng") and len(path) >= 3:
                routing["ripng"][path[2]] = rip.raw_ripng(
                    rip.complete_ripng(routing["ripng"][path[2]]), platform)
    leftover = problems(host_vars)
    if leftover:
        log.warning("features: %s's parse still carries %d refused field(s): %s",
                    host_vars.get("hostname", ""), len(leftover), leftover[0][2])
    return host_vars


def _is_set(value, default) -> bool:
    if isinstance(default, (ListOf, DictOf)):
        return bool(value)
    if isinstance(default, bool):
        return value is not None and bool(value) != default
    if default is None:
        return value is not None
    return value not in ("", None)


def structured(host_vars: dict) -> bool:
    """Does *host_vars* set any pack field? An intent holding only lines (every intent written
    before the packs) does not, and reads as it is. A walk over the routing section and each
    interface, no render."""
    from modules.nsot.features import ospf, rip

    routing = host_vars.get("routing") if isinstance(host_vars, dict) else None
    if isinstance(routing, dict):
        for key, spec in (("ospf", ospf.PROCESS), ("ospfv3", ospf.PROCESS_V3),
                          ("ripng", rip.RIPNG)):
            for proc in routing.get(key) or []:
                if isinstance(proc, dict) and any(_is_set(proc.get(k), d)
                                                  for k, d in spec.items()):
                    return True
        own = routing.get("rip")
        if isinstance(own, dict) and any(_is_set(own.get(k), d) for k, d in rip.RIP.items()):
            return True
    for iface in (host_vars or {}).get("interfaces") or []:
        if isinstance(iface, dict) and any(iface.get(k) for k in (
                "ospf_interface", "ospfv3_interface", "ripng_interface")):
            return True
    return False


def raw_view(host_vars: dict, platform: str = "", strict: bool = False) -> dict:
    """*host_vars* with every structured routing field written back as the lines it renders,
    in the shape intent had before the packs (`settings`, `networks`, `raw`, an interface's
    `ospf`/`ospfv3`/`ripng` lists), the structured fields emptied. For the readers that judge
    adjacencies from intent's lines (`neighbours`, `readers.topology_graph`, `readers.rip`),
    and for a library from before the packs (`for_library`): intent written either way reads
    and renders the same. Not *strict*, it never raises: an intent a pack refuses is returned
    as it is (the render refuses it, naming why)."""
    from modules.nsot.features import ospf, rip

    if not isinstance(host_vars, dict) or not structured(host_vars):
        return host_vars
    from modules.nsot.platform import DIALECTS, UnknownPlatform, unknown_words

    platform = platform or host_vars.get("platform") or ""
    if platform not in DIALECTS:
        # C452: an unknown dialect is refused, never rendered as another; the readers then see
        # the intent as it is, as they do when a pack refuses it.
        if strict:
            raise UnknownPlatform(unknown_words(host_vars))
        log.warning("features: raw view of %s not drawn: %s", host_vars.get("hostname"),
                    unknown_words(host_vars))
        return host_vars
    try:
        prepared = prepare(host_vars)
    except FeatureIntentInvalid:
        if strict:
            raise
        return host_vars
    out = copy.deepcopy(prepared)
    try:
        routing = out.get("routing")
        if isinstance(routing, dict):
            routing["ospf"] = [ospf.raw_process(p, "ipv4", platform) for p in routing["ospf"]]
            routing["ospfv3"] = [ospf.raw_process(p, "ipv6", platform)
                                 for p in routing["ospfv3"]]
            if isinstance(routing.get("rip"), dict):
                routing["rip"] = rip.raw_rip(routing["rip"], platform)
            routing["ripng"] = [rip.raw_ripng(p, platform) for p in routing["ripng"]]
        out["interfaces"] = [ospf.raw_interface(rip.raw_interface(i, platform), platform)
                             if isinstance(i, dict) else i
                             for i in out.get("interfaces") or []]
    except Exception as exc:                       # noqa: BLE001 - the readers' fallback
        if strict:
            raise
        log.warning("features: raw view of %s failed: %s", host_vars.get("hostname"), exc)
        return host_vars
    return out
