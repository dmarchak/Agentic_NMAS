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

**Kinds and tiers (section 5).** Each unit's kind, checked in this order, the first that
applies: a cause spanning devices (Tier 4); Mercury's management path (the management
interface, vty, SSH, a route that may be the manager's, a removal refused as the management
path; Tier 4); any ACL, its entries or a binding (N4: every one; Tier 4); credentials and AAA
(accounts, enable secrets, AAA, SNMP communities and users, key chains, crypto; Tier 4); a QoS
policy (Tier 2); a router-id changed (a fix that takes effect only through a process reset;
Tier 2); a line in a secret position added back (N9; Tier 2); `shutdown` added where intent says
up (Tier 1); otherwise a missing, changed or added line (Tier 1). Removing a routing-protocol
key is an added line (N9; Tier 1), its line masked everywhere. **A kind's tier is a ceiling in
code**: `TIER` is not a setting. An added unit whose removal is not measured on the platform, or
is refused for another reason, keeps its kind and is blocked: can't fix, naming why.

**The incident's tier** is the strictest among its units: a device is healed whole or not at
all, never partly.
"""

import logging
import re

log = logging.getLogger(__name__)

#: Each fix kind's tier: a ceiling in code (section 5). Tiers 3 and 4 are never settings.
TIER = {"missing_line": 1, "changed_line": 1, "added_line": 1, "admin_down": 1,
        "process_reset": 2, "qos_policy": 2, "secret_added_back": 2,
        "physical": 3, "unknown_cause": 3,
        "security_acl": 4, "credentials": 4, "management_path": 4, "multi_device": 4}
KIND_WORDS = {
    "missing_line": "a missing line", "changed_line": "a changed line",
    "added_line": "an added line", "admin_down": "admin down where intent says up",
    "process_reset": "a fix that takes effect only through a process reset",
    "qos_policy": "a QoS policy", "secret_added_back": "a line in a secret position, added back",
    "physical": "a link down while administratively up, configuration at intent",
    "unknown_cause": "a symptom with the configuration at intent",
    "security_acl": "a security ACL", "credentials": "credentials or AAA",
    "management_path": "Mercury's management path", "multi_device": "a cause spanning devices"}
#: Why each Tier 3 and 4 kind is never automatic (section 5's last column).
NEVER_WHY = {
    "physical": "configuration cannot fix a cable, an optic or a far end",
    "unknown_cause": "there is no departure to heal, and guessing is not a fix",
    "security_acl": ("removing a security control is a security decision; every ACL counts "
                     "(N4)"),
    "credentials": ("a deploy may add an account, never change one; rotation and break-glass "
                    "have their own operations"),
    "management_path": ("a change to the path Mercury reaches the device on needs a repair "
                        "route independent of it, and none is built"),
    "multi_device": ("a change across devices has an ordering and a partial state no "
                     "single-device heal can verify")}

_ACL = re.compile(r"^\s*(ip access-list\s|ipv6 access-list\s|access-list\s|ip access-group\s|"
                  r"ipv6 traffic-filter\s|access-class\s|ipv6 access-class\s)")
_CREDENTIALS = re.compile(r"^\s*(username\s|enable (secret|password)\b|aaa\s|"
                          r"snmp-server (community|user|group)\s|key chain\s|crypto\s|"
                          r"tacacs(-server)?\s|radius(-server)?\s)")
_MANAGEMENT = re.compile(r"^\s*(line vty\s|ip ssh\s|ip domain[- ]name\s|ip http\s)")
_QOS = re.compile(r"^\s*(service-policy\s|policy-map\s|class-map\s)")
_ROUTER_ID = re.compile(r"^\s*(router-id|bgp router-id)\s")
_ROUTER = re.compile(r"^(router ospf|ipv6 router ospf|router ospfv3|router bgp)\b")
_SHUTDOWN = re.compile(r"^\s*shutdown$")


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


def kind_of(u: dict, *, mgmt_ifaces: set, mgmt_routes: dict, related: bool) -> tuple:
    """``(kind, why)`` for one unit, section 5's checks in order, the first that applies."""
    texts = _texts(u)
    if related:
        return "multi_device", "another device of this incident changed too"
    why = _mgmt(u, mgmt_ifaces, mgmt_routes)
    if why:
        return "management_path", why
    if any(_ACL.search(t) for t in texts):
        return "security_acl", "an ACL, its entry or its binding departed (N4: every ACL)"
    if any(_CREDENTIALS.search(t) for t in texts):
        return "credentials", "an account, AAA, an SNMP community or user, a key or crypto"
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
             related: bool = False) -> dict:
    """The departure of one device, classified: ``{"units", "tier", "kind", "blocked",
    "left_out", "removal_ids"}``. Each unit gains ``kind``, ``tier``, ``why``, ``blocked`` (why
    it cannot be fixed now, or "") and ``id``; *tier* and *kind* are the strictest unit's;
    *blocked* the first unit's that is; *left_out* says what the intersection rule did not
    heal. The manager's routes are judged from this host's addresses (`removal.host_addresses`,
    the one read Mode B's own refusal makes); unreadable, every static route may be one."""
    from modules.nsot import removal

    running_s = _stored(running)
    dep = departures(golden, running_s, intended)
    units = units_of(dep, platform)
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
                                      related=related)
        u["tier"] = TIER[u["kind"]]
        u["blocked"] = ""
        u["id"] = removal.unit_id(u["chain"], u["lines"][0] if u["lines"] else "")
        if u["op"] == "remove" and u["tier"] < 4:
            heads = ([{"chain": list(u["remove"][0][0]), "line": u["remove"][0][1]}]
                     if u["stanza"] else
                     [{"chain": list(c), "line": l} for c, l in u["remove"]])
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

    return {"id": u.get("id"), "op": u["op"], "kind": u.get("kind"), "tier": u.get("tier"),
            "why": u.get("why", ""), "blocked": u.get("blocked", ""),
            "section": (u["chain"][0] if u["chain"] else (u["lines"][0] if u["lines"] else "")),
            "stanza": bool(u.get("stanza")),
            "add": [redact_text(l) for _c, l in u["add"]],
            "remove": [redact_text(l) for _c, l in u["remove"]],
            "secret_position": bool(u.get("secret_position")),
            "words": unit_words(u)}


def unit_words(u: dict) -> str:
    """A unit in the words a record and a notice use: its kind, what is done, where, and how
    many lines; never the lines themselves."""
    where = u["chain"][0].strip() if u["chain"] else "the global configuration"
    n = len(u["add"]) + len(u["remove"])
    do = {"add": "re-apply", "remove": "remove", "change": "set back"}[u["op"]]
    return (f"{KIND_WORDS.get(u.get('kind'), u.get('kind'))} (Tier {u.get('tier')}): {do} "
            f"{n} line(s) in {where}")
