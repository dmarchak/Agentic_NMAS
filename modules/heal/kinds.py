"""What departed, unit by unit, and each unit's fix kind and tier (board H, part H3;
docs/HEAL_TO_INTENT.md sections 2 and 5, N4, N9 and N13). PURE but for the parser and the
measured removal record it reads: it reads no device, and holds configuration only in memory.

**The intersection rule (section 2).** The approved state is the device's last golden that
matched its intent (N5; the caller checks it, guard 4). A line is healed only if it departed
from BOTH the golden and committed intent:
- **missing**: in the golden AND in intent, not on the device (re-applied by merge);
- **added**: on the device, in neither the golden nor intent (removed by Mode B, a measured
  shape only).
What is left out is said, never healed: a line intent has and the golden lacks (an intent edit
not deployed: Activate's, a person's deploy), a line the device and intent have and the golden
lacks (the golden behind), and a line the golden has and intent lacks (the golden departs from
intent, guard 4's).

**Units (N13, the operator, 2026-11-03).** A unit is one feature on one section: the lines the
PARSER groups as one feature there, never by guesswork. Each line's feature is the first place
the parse of its section changes when the line is added (`feature_of`); lines of one section
with one feature are one unit (R3's two OSPF authentication lines on one interface are one); a
line the parser does not model is its own unit, and so is a multi-valued line outside an
interface (each static route, each `network` statement: N13 groups on an interface). A
stanza whose header departed is one unit with its lines. A missing line and an added line of one section with one SINGLE-VALUED feature (the
parse holds a value, not a list: a description, an OSPF cost, a router-id) are one CHANGED unit.

**Dependents are one unit** (C2822, the operator, 2026-11-08; `join_dependents`): a definition
of the departure (an ACL, an object-group, a prefix-, community- or AS-path list, a class-map or
policy-map, a key chain, a track, an IP SLA operation) that only ONE other unit of the same
departure references by name is one unit with it, so W7's added ACL and the `ip access-group`
applying it on Gi2 are one unit, and class-map, policy-map and `service-policy` one chain. The
objects and their shapes are the platform pack's (`modules/nsot/platform_heal.json`,
``references``). A definition an unchanged line also uses, or that two units use, stays its own
unit: one definition never gathers several features into one heal.

**Kinds and tiers (section 5).** Each unit's kind, checked in this order, the first that
applies: a cause spanning devices (Tier 4); Mercury's management path (the management
interface, vty, SSH, a route that may be the manager's, a removal refused as the management
path; Tier 4); credentials and AAA (accounts, enable secrets, AAA, SNMP communities and users,
key chains, crypto; Tier 4); any ACL, its entries or its application (`security_acl`, Tier 2
since C2839: a proposal, a person decides; it was Tier 4); a security control removed or
changed (`security_control`, Tier 2, C2839: the classes the platform pack declares by line
shape: routing authentication and key chains, AAA, crypto and SSH, SNMP restrictions,
control-plane policing, port security and 802.1X, `transport input`); a QoS policy (Tier 2); a
router-id changed (a fix that takes effect only through a process reset; Tier 2); a line in a
secret position added back (N9; Tier 2); `shutdown` added where intent says up (Tier 1);
otherwise a missing, changed or added line (Tier 1). A missing security control added back
stays what it was (a missing line, Tier 1; a routing key, Tier 2 as a secret added back).
**A one-sided security change that broke an adjacency** (C2839's per-network question,
``heal_security_revert_adjacency``, default no): where the network says yes, a removal or change
of a security control on an interface or a routing process, on a device whose incident holds an
adjacency down and spans no other device, is `security_revert` (Tier 1) instead. **A kind's
tier is a ceiling in code**: `TIER` is not a setting. An added unit whose removal is not
measured on the platform, or is refused for another reason, keeps its kind and is blocked:
can't fix, naming why.

**The incident's tier** is the strictest among its units: a device is healed whole or not at
all, never partly.
"""

import functools
import json
import logging
import os
import re

log = logging.getLogger(__name__)

#: Each fix kind's tier: a ceiling in code (section 5). Tiers 3 and 4 are never settings.
TIER = {"missing_line": 1, "changed_line": 1, "added_line": 1, "admin_down": 1,
        "security_revert": 1,
        "process_reset": 2, "qos_policy": 2, "secret_added_back": 2,
        "security_acl": 2, "security_control": 2,
        "physical": 3, "unknown_cause": 3,
        "credentials": 4, "management_path": 4, "multi_device": 4,
        # The action kinds (19.4, H19): no configuration line changes (a bounce, a clear), or a
        # change to intent is proposed (dampening). `heal.actions` holds their guards, their
        # choice from the diagnosis and which are built; a session clear is Tier 1 only on a
        # network marked lab, Tier 2 elsewhere (N16, `actions.tier_of`).
        "port_bounce": 1, "session_clear": 1, "ospf_reset": 1, "dampening_proposal": 2}
KIND_WORDS = {
    "missing_line": "a missing line", "changed_line": "a changed line",
    "added_line": "an added line", "admin_down": "admin down where intent says up",
    "process_reset": "a fix that takes effect only through a process reset",
    "qos_policy": "a QoS policy", "secret_added_back": "a line in a secret position, added back",
    "physical": "a link down while administratively up, configuration at intent",
    "unknown_cause": "a symptom with the configuration at intent",
    "security_acl": "a security ACL",
    "security_control": "a security control added or changed outside intent",
    "security_revert": ("a one-sided security change that broke an adjacency, put back (the "
                        "network allows it)"),
    "credentials": "credentials or AAA",
    "management_path": "Mercury's management path", "multi_device": "a cause spanning devices",
    "port_bounce": "a port bounce (an action: configuration unchanged)",
    "session_clear": "a BGP session clear of one named neighbour (an action)",
    "ospf_reset": "an OSPF adjacency reset, the port bounce on its one-neighbour interface "
                  "(an action)",
    "dampening_proposal": "dampening proposed on a port still flapping (a change to intent)"}
#: Why each Tier 3 and 4 kind is never automatic (section 5's last column).
NEVER_WHY = {
    "physical": "configuration cannot fix a cable, an optic or a far end",
    "unknown_cause": "there is no departure to heal, and guessing is not a fix",
    "credentials": ("a deploy may add an account, never change one; rotation and break-glass "
                    "have their own operations"),
    "management_path": ("a change to the path Mercury reaches the device on needs a repair "
                        "route independent of it, and none is built"),
    "multi_device": ("a change across devices has an ordering and a partial state no "
                     "single-device heal can verify")}

_CREDENTIALS = re.compile(r"^\s*(username\s|enable (secret|password)\b|aaa\s|"
                          r"snmp-server (community|user|group)\s|key chain\s|crypto\s|"
                          r"tacacs(-server)?\s|radius(-server)?\s)")
_MANAGEMENT = re.compile(r"^\s*(line vty\s|ip ssh\s|ip domain[- ]name\s|ip http\s)")
_QOS = re.compile(r"^\s*(service-policy\s|policy-map\s|class-map\s)")
_ROUTER_ID = re.compile(r"^\s*(router-id|bgp router-id)\s")
_ROUTER = re.compile(r"^(router ospf|ipv6 router ospf|router ospfv3|router bgp)\b")
_SHUTDOWN = re.compile(r"^\s*shutdown$")
#: The sections a one-sided security change that broke an adjacency may sit in (C2839's
#: per-network question): an interface, or a routing process.
_ADJACENCY_SECTION = re.compile(r"^(interface |router (ospf|ospfv3|bgp|isis|eigrp|rip)\b|"
                                r"ipv6 router (ospf|eigrp|rip)\b)")
#: The platform pack (C2839's security classes, C2822's references), by config dialect.
PACK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nsot",
                    "platform_heal.json")
#: The security class whose kind is `security_acl`; every other class is `security_control`.
ACL_CLASS = "acl"
#: What a platform with no security classes declared answers (`security_class`).
UNDECLARED = "undeclared"


def pack(dialect: str) -> dict:
    """The platform pack's entry for *dialect*: ``{"security": {class: {"words", "lines",
    "sections"}}, "references": [...]}`` with its shapes compiled, following one ``same_as``;
    ``{}`` for a dialect with no entry, or when the pack cannot be read (logged)."""
    try:
        doc = _pack_doc()
    except (OSError, ValueError) as exc:
        log.error("heal: the platform pack %s cannot be read: %s", PACK, exc)
        return {}
    entry = (doc.get("dialects") or {}).get(dialect or "") or {}
    if entry.get("same_as"):
        entry = (doc.get("dialects") or {}).get(entry["same_as"]) or {}
    return _compiled(json.dumps(entry))                 # in the file's order: the first wins


def _pack_doc() -> dict:
    with open(PACK, encoding="utf-8") as fh:
        return json.load(fh)


@functools.lru_cache(maxsize=8)
def _compiled(raw: str) -> dict:
    entry = json.loads(raw)
    if not entry:
        return {}
    security = {name: {"words": c.get("words") or name,
                       "lines": [re.compile(p) for p in c.get("lines") or []],
                       "sections": [re.compile(p) for p in c.get("sections") or []]}
                for name, c in (entry.get("security") or {}).items()}
    refs = [{"object": r["object"], "words": r.get("words") or r["object"],
             "defines": [re.compile(p) for p in r.get("defines") or []],
             "uses": [re.compile(p) for p in r.get("uses") or []]}
            for r in entry.get("references") or []]
    return {"security": security, "references": refs}


def security_class(platform: str, u: dict) -> tuple:
    """``(class, words)``: the security class (C2839) the unit's lines are in, by the platform
    pack's line shapes, the first class that matches; ``("", "")`` for none; ``(UNDECLARED,
    why)`` for a platform with no classes declared (fail closed: a person's)."""
    classes = pack(platform).get("security") or {}
    if not classes:
        return UNDECLARED, (f"no security classes are declared for {platform or 'this platform'}"
                            " (modules/nsot/platform_heal.json), so every removal or change is "
                            "a person's")
    for c, l in u["add"] + u["remove"]:
        line = l.strip()
        heads = [h.strip() for h in c]
        for name, cls in classes.items():
            if any(p.search(line) for p in cls["lines"]) or any(
                    p.search(h) for h in heads for p in cls["sections"]):
                return name, cls["words"]
    return "", ""


def _paths(text: str) -> list:
    """``[(chain tuple, line)]`` in the device's order, each once: the section model the merge,
    the removal and the rollback use (`deploy._section_chains`)."""
    from modules.nsot.deploy import _section_chains

    out, seen = [], set()
    for line, chain in _section_chains(text or ""):
        key = (tuple(chain), line)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _stored(text: str) -> str:
    """A configuration in the form a golden is STORED (`normalize.strip_for_repo`): a raw read
    carries lines no golden does (the NVRAM comment, `ntp clock-period`), which are not drift."""
    from modules.nsot import normalize

    return "\n".join(normalize.strip_for_repo(text or ""))


def departures(golden: str, running: str, intended: str) -> dict:
    """The intersection rule's sets: ``{"missing", "added", "intent_only", "golden_behind",
    "golden_not_intent"}``, the first two ``[(chain, line)]`` in the device's (missing: the
    golden's) order, the rest counts."""
    g, r, i = _paths(golden), _paths(_stored(running)), _paths(intended)
    gs, rs, is_ = (set(x) for x in (g, r, i))
    return {"missing": [p for p in g if p in is_ and p not in rs],
            "added": [p for p in r if p not in gs and p not in is_],
            "intent_only": sum(1 for p in i if p not in gs and p not in rs),
            "golden_behind": sum(1 for p in r if p in is_ and p not in gs),
            "golden_not_intent": sum(1 for p in g if p not in is_)}


# ── The parser's grouping (N13) ─────────────────────────────────────────────────────────────

def _first_diff(a, b, path=()):
    """The first place two parses differ, and whether the value there is single-valued:
    ``(path, single)``, or None. Two lists of one length are compared item by item; lists of
    different lengths are one multi-valued feature."""
    if a == b:
        return None
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if a.get(k) != b.get(k):
                return _first_diff(a.get(k), b.get(k), path + (k,))
    if isinstance(a, list) and isinstance(b, list):
        if len(a) == len(b):
            for n, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    return _first_diff(x, y, path + (n,))
        return path, False
    return path, not isinstance(b, list)


def feature_of(platform: str, chain: tuple, line: str) -> dict:
    """``{"feature", "single"}``: the place the parse of *line*'s section changes when the line
    is added (one feature), and whether it holds one value. A line the parser leaves in
    ``unmodeled``, or one it does not see at all, is its own feature."""
    from modules.nsot.parsers import get_parser

    head = "hostname heal-unit\n" + "".join(c + "\n" for c in chain)
    try:
        parser = get_parser(platform)
        got = _first_diff(parser.parse(head), parser.parse(head + line + "\n"))
    except Exception as exc:
        log.warning("heal: %r could not be parsed for its feature: %s", line, exc)
        got = None
    if got is None or "unmodeled" in got[0]:
        return {"feature": ("line", line.strip()), "single": False}
    return {"feature": tuple(got[0]), "single": bool(got[1])}


def _stanzas(paths: list) -> tuple:
    """``(stanzas, leaves)``: each departed header with its departed lines under it (one unit),
    and the departed lines not under a departed header."""
    heads = {c + (l,) for c, l in paths}
    stanzas, leaves = {}, []
    for c, l in paths:
        top = next((c[:n] for n in range(1, len(c) + 1) if c[:n] in heads), None)
        if top is not None:
            stanzas.setdefault(top, []).append((c, l))
        elif any(p[0][:len(c) + 1] == c + (l,) for p in paths):
            stanzas.setdefault(c + (l,), [])
        else:
            leaves.append((c, l))
    return stanzas, leaves


def units_of(dep: dict, platform: str) -> list:
    """The departure as units (N13): ``[{"op", "chain", "lines", "add", "remove", "feature",
    "stanza"}]``. *op* is ``add`` (re-apply missing lines), ``remove`` (added lines) or
    ``change`` (a single-valued setting: the golden's value set over the device's); *add* and
    *remove* are ``[(chain, line)]``."""
    out = []
    groups = {}
    for op, key in (("add", "missing"), ("remove", "added")):
        stanzas, leaves = _stanzas(dep[key])
        for head, inner in stanzas.items():
            out.append({"op": op, "chain": list(head[:-1]), "stanza": True,
                        "feature": ("stanza", head[-1]), "single": False,
                        op: [(head[:-1], head[-1])] + inner})
        for c, l in leaves:
            f = feature_of(platform, c, l)
            if f["feature"] and not f["single"] and not (c and c[0].startswith("interface ")):
                # N13 groups one feature on one INTERFACE; anywhere else a multi-valued line
                # (a static route, a network statement) is its own unit.
                f = dict(f, feature=f["feature"] + (l.strip(),))
            groups.setdefault((op, c, f["feature"]), {"single": f["single"], "lines": []})[
                "lines"].append((c, l))
    for (op, c, feat), g in groups.items():
        if op == "remove" and g["single"] and ("add", c, feat) in groups:
            continue                                    # paired below, as a change
        if op == "add" and g["single"] and ("remove", c, feat) in groups:
            out.append({"op": "change", "chain": list(c), "stanza": False, "feature": feat,
                        "single": True, "add": g["lines"],
                        "remove": groups[("remove", c, feat)]["lines"]})
            continue
        out.append({"op": op, "chain": list(c), "stanza": False, "feature": feat,
                    "single": g["single"], op: g["lines"]})
    for u in out:
        u.setdefault("add", [])
        u.setdefault("remove", [])
        u["lines"] = [l for _c, l in u["add"]] + [l for _c, l in u["remove"]]
        u["heads"] = _heads(u)
    return out


def _heads(u: dict) -> list:
    """``[(chain, line)]``: what the program names for the unit, a stanza by its header (the
    merge takes its subtree, the removal its `no <header>`), a leaf by each line; a joined
    unit (C2822) by each part's."""
    if u.get("parts"):
        return [h for p in u["parts"] for h in p["heads"]]
    side = u["add"] if u["op"] in ("add", "change") else u["remove"]
    return list(side[:1] if u.get("stanza") else side)


# ── Dependents (C2822) ──────────────────────────────────────────────────────────────────────

def _names(match) -> list:
    got = match.groupdict()
    if got.get("name"):
        return [got["name"]]
    return (got.get("names") or "").split()


def join_dependents(units: list, golden: str, running: str, platform: str) -> list:
    """N13's dependents (C2822): each definition of the departure that only ONE other unit of
    the same departure references by name joins that unit, transitively (an object-group into
    its ACL into the `ip access-group` applying it), by the platform pack's ``references``.
    A definition is OF the departure when every line defining it is in a unit of that op (all
    added, or all missing); its references are read in the configuration that holds it (the
    device's for an added one, the golden's for a missing one), so a reference from a line that
    did not depart (an unchanged line) keeps it its own unit, and so do references from two
    units. Changed units are never joined. Returns the units, each joined group as one unit
    (``parts``: its units, the use first)."""
    refs = pack(platform).get("references") or []
    if not refs or len(units) < 2:
        return units
    parent = list(range(len(units)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    defined = set()
    for op, text in (("remove", running), ("add", golden)):
        where = {}
        for i, u in enumerate(units):
            if u["op"] == op:
                for c, l in u[op]:
                    where[(tuple(c), l)] = i
        if not where:
            continue
        paths = _paths(text)
        for r in refs:
            defs, uses = {}, {}
            for c, l in paths:
                line = l.strip()
                if not c:
                    for p in r["defines"]:
                        m = p.search(line)
                        if m:
                            defs.setdefault(m.group("name"), set()).add((c, l))
                for p in r["uses"]:
                    m = p.search(line)
                    if m:
                        for n in _names(m):
                            uses.setdefault(n, set()).add((c, l))
            for name, dpaths in defs.items():
                dunits = {where.get(x) for x in dpaths}
                if None in dunits:
                    continue                    # part of the definition did not depart
                upaths = [x for x in uses.get(name, ()) if where.get(x) not in dunits]
                if not upaths:
                    continue
                uunits = {where.get(x) for x in upaths}
                departed = uunits - {None}
                if None in uunits:
                    continue                    # a line that did not depart uses it
                if len(departed) != 1:
                    continue                    # two units use it
                outer = min(departed)
                for d in dunits:
                    parent[find(d)] = find(outer)
                    defined.add(d)
    groups = {}
    for i in range(len(units)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for i, u in enumerate(units):
        members = groups[find(i)]
        if len(members) == 1:
            out.append(u)
            continue
        if i != members[0]:
            continue
        outer = next((m for m in members if m not in defined), members[0])
        parts = [units[outer]] + [units[m] for m in members if m != outer]
        o = units[outer]
        op = o["op"]
        joined = {"op": op, "chain": list(o["chain"]), "stanza": False, "joined": True,
                  "feature": ("dependents",) + tuple(o["feature"]), "single": False,
                  "parts": parts, "add": [], "remove": []}
        joined[op] = [x for p in parts for x in p[op]]
        joined["lines"] = [l for _c, l in joined["add"]] + [l for _c, l in joined["remove"]]
        joined["heads"] = _heads(joined)
        out.append(joined)
    return out


# ── Kinds ───────────────────────────────────────────────────────────────────────────────────

def _texts(u: dict) -> list:
    return [x for c, l in u["add"] + u["remove"] for x in list(c) + [l]]


def _secret(line: str) -> bool:
    from modules.redact import redact_positional

    return redact_positional(line) != line


def _mgmt(u: dict, mgmt_ifaces: set, mgmt_routes: dict) -> str:
    for c, l in u["add"] + u["remove"]:
        top = c[0] if c else l
        if top in mgmt_ifaces:
            return f"{top} is the interface Mercury reaches the device on"
        if _MANAGEMENT.search(top) or _MANAGEMENT.search(l):
            return f"`{(top if _MANAGEMENT.search(top) else l).strip()}` is how Mercury logs in"
        if not c and mgmt_routes.get(l.strip()):
            return mgmt_routes[l.strip()]
    return ""


def _revert_allowed(u: dict, revert) -> bool:
    """C2839's per-network question, answered yes for this incident (*revert*: the network's
    ``heal_security_revert_adjacency`` on, an adjacency down among its triggers and no other
    device in it, `decide.revert_scope`): the unit removes or changes, and sits on an interface
    or a routing process."""
    return bool(revert) and u["op"] in ("remove", "change") and bool(u["chain"]) and bool(
        _ADJACENCY_SECTION.search(u["chain"][0]))


def kind_of(u: dict, *, mgmt_ifaces: set, mgmt_routes: dict, related: bool, platform: str = "",
            revert=None) -> tuple:
    """``(kind, why)`` for one unit, section 5's checks in order, the first that applies."""
    texts = _texts(u)
    if related:
        return "multi_device", "another device of this incident changed too"
    why = _mgmt(u, mgmt_ifaces, mgmt_routes)
    if why:
        return "management_path", why
    if any(_CREDENTIALS.search(t) for t in texts):
        return "credentials", "an account, AAA, an SNMP community or user, a key or crypto"
    cls, words = security_class(platform, u)
    if cls and (cls != UNDECLARED or u["op"] in ("remove", "change")):
        if cls != UNDECLARED and _revert_allowed(u, revert):
            return "security_revert", (
                f"{words} {'removed' if u['op'] == 'remove' else 'changed'} on one side, and "
                f"an adjacency is down: {(revert or {}).get('words') or 'the network allows it'}")
        if cls == ACL_CLASS:
            return "security_acl", ("an ACL, its entries or its application departed: a person "
                                    "decides whether it goes back to intent or into it (C2839)")
        if u["op"] in ("remove", "change"):
            return "security_control", (
                f"{words} added or changed outside intent: a person decides whether it goes "
                "back to intent or into it (C2839)" if cls != UNDECLARED else words)
    if any(_QOS.search(t) for t in texts):
        return "qos_policy", "a service policy, policy map or class map departed"
    if u["op"] == "change" and u["chain"] and _ROUTER.search(u["chain"][0]) and any(
            _ROUTER_ID.search(l) for l in u["lines"]):
        return "process_reset", "a router-id takes effect only through a process reset"
    if u["op"] in ("add", "change") and any(_secret(l) for _c, l in u["add"]):
        return "secret_added_back", "re-adding a line in a secret position needs a person's reason"
    if (u["op"] == "remove" and len(u["remove"]) == 1 and u["chain"]
            and u["chain"][0].startswith("interface ") and _SHUTDOWN.search(u["remove"][0][1])):
        return "admin_down", f"{u['chain'][0]} is shut where intent says up"
    return {"add": "missing_line", "change": "changed_line", "remove": "added_line"}[u["op"]], ""


def classify(golden: str, running: str, intended: str, *, platform: str, mgmt_ip: str = "",
             related: bool = False, revert=None) -> dict:
    """The departure of one device, classified: ``{"units", "tier", "kind", "blocked",
    "left_out", "removal_ids"}``. Each unit gains ``kind``, ``tier``, ``why``, ``blocked`` (why
    it cannot be fixed now, or "") and ``id``; *tier* and *kind* are the strictest unit's;
    *blocked* the first unit's that is; *left_out* says what the intersection rule did not
    heal. The manager's routes are judged from this host's addresses (`removal.host_addresses`,
    the one read Mode B's own refusal makes); unreadable, every static route may be one.
    *revert*: C2839's per-network yes for this incident (`decide.revert_scope`), or None."""
    from modules.nsot import removal

    running_s = _stored(running)
    dep = departures(golden, running_s, intended)
    units = join_dependents(units_of(dep, platform), golden, running_s, platform)
    chains = removal._chains(running_s)
    mgmt_ifaces = removal._management_interfaces(chains, mgmt_ip)
    try:
        addresses = removal.host_addresses()
    except Exception as exc:
        log.warning("heal: this host's addresses could not be read: %s", exc)
        addresses = None
    mgmt_routes = removal._management_routes(chains, addresses)
    removal_ids = []
    for u in units:
        u["kind"], u["why"] = kind_of(u, mgmt_ifaces=mgmt_ifaces, mgmt_routes=mgmt_routes,
                                      related=related, platform=platform, revert=revert)
        u["tier"] = TIER[u["kind"]]
        u["blocked"] = ""
        u["id"] = removal.unit_id(u["chain"], u["lines"][0] if u["lines"] else "")
        if u["op"] == "remove" and u["tier"] < 4:
            heads = [{"chain": list(c), "line": l} for c, l in u["heads"]]
            judged = removal.removal_program(running_s, heads, mgmt_ip=mgmt_ip,
                                             dialect=platform)
            refused = judged["refused"]
            if refused and refused[0]["reason"].startswith("the management path"):
                u["kind"], u["tier"], u["why"] = ("management_path", 4,
                                                  refused[0]["reason"])
            elif refused:
                u["blocked"] = refused[0]["reason"]
            else:
                u["secret_position"] = bool(judged["secret_position"])
                u["removal_ids"] = [removal.unit_id(h["chain"], h["line"]) for h in heads]
                removal_ids.extend(u["removal_ids"])
    strict = max(units, key=lambda x: (x["tier"], bool(x["blocked"])), default=None)
    blocked = next((u for u in units if u["blocked"]), None)
    return {"units": units, "tier": strict["tier"] if strict else 0,
            "kind": strict["kind"] if strict else "", "removal_ids": removal_ids,
            "blocked": ({"unit": blocked["id"], "kind": blocked["kind"],
                         "why": blocked["blocked"]} if blocked else None),
            "left_out": {k: dep[k] for k in ("intent_only", "golden_behind",
                                              "golden_not_intent")}}


def masked_unit(u: dict) -> dict:
    """A unit as a record keeps it: its lines masked (`redact_text`), never configuration
    text."""
    from modules.redact import redact_text

    out = {"id": u.get("id"), "op": u["op"], "kind": u.get("kind"), "tier": u.get("tier"),
           "why": u.get("why", ""), "blocked": u.get("blocked", ""),
           "section": (u["chain"][0] if u["chain"] else (u["lines"][0] if u["lines"] else "")),
           "stanza": bool(u.get("stanza")),
           "joined": len(u.get("parts") or []),
           "add": [redact_text(l) for _c, l in u["add"]],
           "remove": [redact_text(l) for _c, l in u["remove"]],
           "secret_position": bool(u.get("secret_position")),
           "words": unit_words(u)}
    if u.get("parts"):
        # C2822 with C2823: a joined unit keeps its parts, each masked in its own section, so
        # its words name the use where it is (the access-group on its interface) and the
        # definition on its own, never all its lines as the use's section's.
        out["parts"] = [{k: v for k, v in masked_unit(p).items() if k != "parts"}
                        for p in u["parts"]]
    return out


def unit_words(u: dict) -> str:
    """A unit in the words a record and a notice use: its kind, what is done, where, and how
    many lines; never the lines themselves."""
    where = u["chain"][0].strip() if u["chain"] else "the global configuration"
    n = len(u["add"]) + len(u["remove"])
    do = {"add": "re-apply", "remove": "remove", "change": "set back"}[u["op"]]
    parts = len(u.get("parts") or []) - 1
    # C2822: a joined unit says it carries what only it references, never the lines.
    tail = (f", with the {parts} definition(s) only it references (one unit)" if parts > 0
            else "")
    return (f"{KIND_WORDS.get(u.get('kind'), u.get('kind'))} (Tier {u.get('tier')}): {do} "
            f"{n} line(s) in {where}{tail}")
