"""Self-healing in plain words (docs/MERCURY_CHARTER.md, "Human-facing means human-readable",
rules 1 to 5; C2817, C2823): what happened, what Mercury did or would do, and the cause where
Mercury holds both ends of one. Deterministic, from what the decision already holds: the
incident's triggers (each with its kind, time and words) and the decision's units (each with
its section and its lines, masked). Never a guess: a link between a change and a symptom is
drawn only where both name the same interface, or the same router-id, and the change came
first; and it is labelled as a hypothesis, after the facts (rule 5).

**The cause** (`cause_of`): ``{"facts": [{"text", "at", "epoch"}], "hypothesis": {"text",
"label", "at"} or None}``, the facts in time order: the change (who made it, as the line named
them, and what it changed, from the units) and each symptom (an adjacency lost, an alert, a
duplicate router-id); then the hypothesis, when both ends are held:
- **an interface**: a unit in ``interface X`` and a symptom on X after the change. Where the
  unit applies an ACL (``ip access-group N in|out``, ``ipv6 traffic-filter``) whose entries the
  same change added and none of them permits OSPF, and the symptom is OSPF's, that is a fact
  too ("none of its 3 entries permits OSPF"), and the hypothesis says the ACL drops OSPF there
  (C2823, H11 W7); otherwise that the change on X broke what was lost on X (W6's key on Gi4);
- **a router-id**: a unit whose line sets a router-id that a duplicate router-id report names
  (W5): two routers with one router-id cannot peer.

**The words** (`outcome_words`, `decide._outcome`'s): what Mercury did or would do, in plain
words, the tier a label after them; the fix kind, the tier's number, the guard and the mode's
key go to the record's own fields, which "Details for the record" draws.

**Times.** A record keeps UTC (`at`, ISO); text built here for a message or a record says
"at HH:MM UTC" (a time Mercury measured: "by HH:MM" is only for an estimate or a deadline,
the operator, 2026-11-09). A page draws each fact's own ``at`` in the viewer's zone
(`_macros.clock`), UTC on hover.
"""

import logging
import re
import time

log = logging.getLogger(__name__)

#: The longest a change on one device is taken as the likeliest cause of a symptom on another
#: (`likely_elsewhere`): 600 s, 2.5 times the 4 minutes measured in H11 (W4: a change 3 minutes
#: before the probe it broke failed; W7: a change 4 minutes before the streams behind it were
#: lost, 20:00:51 to 20:04:50 UTC).
LIKELY_S = 600
#: Lines of one unit quoted in a sentence; more are counted.
QUOTED = 2
#: The label a hypothesis carries (rule 5: labelled as one, after the facts).
HYPOTHESIS = "Likely cause (a hypothesis, not checked)"
SYMPTOMS = ("adjacency_log", "adjacency", "alert", "duplicate_router_id")
_ISO_TAIL = re.compile(r"\s+(?:since|at)\s+\d{4}-\d\d-\d\dT[\d:.]+Z?")
_IFACE = re.compile(r"^\s*([A-Za-z][A-Za-z-]*)\s*(\d[\d/.:]*)\s*$")
_APPLY = re.compile(r"^\s*(ip access-group|ipv6 traffic-filter)\s+(\S+)\s+(in|out)\b")
_ACL_HEAD = re.compile(r"^\s*(ip|ipv6) access-list\s+(?:(extended|standard)\s+)?(\S+)\s*$")
_NUMBERED = re.compile(r"^\s*access-list\s+(\S+)\s+(permit|deny)\b(.*)$")
_ENTRY = re.compile(r"^\s*(?:\d+\s+)?(permit|deny)\b\s*(\S*)")
_ROUTER_ID = re.compile(r"^\s*(?:bgp\s+)?router-id\s+(\S+)")
_PROCESS = {"router ospf": "OSPF", "ipv6 router ospf": "OSPFv3", "router ospfv3": "OSPFv3",
            "router bgp": "BGP"}


def hhmm(epoch) -> str:
    return time.strftime("%H:%M", time.gmtime(float(epoch)))


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _q(line: str) -> str:
    return f"“{(line or '').strip()}”"


def _plural(n: int, one: str, many: str = "") -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


# ── Units, in words ─────────────────────────────────────────────────────────────────────────

def _where(u: dict) -> str:
    s = (u.get("section") or "").strip()
    # A top-level line's unit names the line as its section (`kinds.masked_unit`): it is in
    # the global configuration.
    if not s or (not u.get("stanza") and s in {(l or "").strip() for l in
                                                 (u.get("add") or []) + (u.get("remove") or [])}):
        return "the global configuration"
    return s


def interface_of(u: dict) -> str:
    """The interface a unit is in (its section ``interface X``), or ``""``."""
    s = (u.get("section") or "").strip()
    return s.split(None, 1)[1] if s.lower().startswith("interface ") and " " in s else ""


def same_interface(a: str, b: str) -> bool:
    """Whether two names are one interface (``Gi2`` and ``GigabitEthernet2``): the type's first
    two letters and the whole number. A name either side cannot be read as one is not."""
    ma, mb = _IFACE.match(a or ""), _IFACE.match(b or "")
    return bool(ma and mb and ma.group(1)[:2].lower() == mb.group(1)[:2].lower()
                and ma.group(2) == mb.group(2))


def current_lines(u: dict) -> list:
    """The unit's lines as the device holds them now (masked): what was added or changed to."""
    return list(u.get("remove") or [])


def changed_words(u: dict) -> str:
    """What happened to one unit, as a fact: ``“logging host 192.0.2.10” was removed``,
    ``in router ospf 1, “router-id 192.0.2.6” was changed to “router-id 192.0.2.99”``."""
    add, rem, op = list(u.get("add") or []), list(u.get("remove") or []), u.get("op")
    where = _where(u)
    if u.get("stanza") and op == "remove":
        return f"{_q(where)} was added ({_plural(len(rem), 'line')})"
    if u.get("stanza") and op == "add":
        return f"{_q(where)} was removed ({_plural(len(add), 'line')})"
    if op == "change":
        if len(add) == 1 and len(rem) == 1:
            return f"in {where}, {_q(add[0])} was changed to {_q(rem[0])}"
        return f"{_plural(max(len(add), len(rem)), 'line')} in {where} were changed"
    if op == "add":
        if len(add) <= QUOTED:
            return f"{' and '.join(_q(l) for l in add)} {'was' if len(add) == 1 else 'were'} " \
                   f"removed from {where}"
        return f"{_plural(len(add), 'line')} were removed from {where}"
    if len(rem) <= QUOTED:
        return f"{' and '.join(_q(l) for l in rem)} {'was' if len(rem) == 1 else 'were'} " \
               f"added to {where}"
    return f"{_plural(len(rem), 'line')} were added to {where}"


def fix_words(u: dict) -> str:
    """What putting one unit back does: ``put back “logging host 192.0.2.10” in …``."""
    add, rem, op = list(u.get("add") or []), list(u.get("remove") or []), u.get("op")
    where = _where(u)
    if u.get("stanza") and op == "remove":
        return f"remove {_q(where)} ({_plural(len(rem), 'line')})"
    if u.get("stanza") and op == "add":
        return f"put back {_q(where)} ({_plural(len(add), 'line')})"
    if op == "change":
        if len(add) == 1 and len(rem) == 1:
            return f"set {_q(rem[0])} back to {_q(add[0])} in {where}"
        return f"set {_plural(max(len(add), len(rem)), 'line')} in {where} back"
    if op == "add":
        if len(add) <= QUOTED:
            return f"put back {' and '.join(_q(l) for l in add)} in {where}"
        return f"put back {_plural(len(add), 'line')} in {where}"
    if len(rem) <= QUOTED:
        return f"remove {' and '.join(_q(l) for l in rem)} from {where}"
    return f"remove the {_plural(len(rem), 'added line')} from {where}"


def _join(parts: list, more: int = 0) -> str:
    parts = [p for p in parts if p]
    text = parts[0] if len(parts) == 1 else (", ".join(parts[:-1]) + " and " + parts[-1]
                                             if parts else "")
    return text + (f", and {_plural(more, 'more change')}" if more else "")


def flat(units: list) -> list:
    """The units as they are worded and linked: a joined unit (C2822: a use and the definitions
    only it references) as its parts, the use first, each in its own section."""
    return [p for u in units or [] for p in (u.get("parts") or [u])]


def changes_words(units: list, limit: int = 3) -> str:
    units = flat(units)
    return _join([changed_words(u) for u in units[:limit]], max(0, len(units) - limit))


def fixes_words(units: list, limit: int = 3) -> str:
    units = flat(units)
    return _join([fix_words(u) for u in units[:limit]], max(0, len(units) - limit))


def process_of(units: list) -> str:
    """The routing process a reset restarts, by name (``OSPF``), from a ``process_reset``
    unit's section; ``""`` when none."""
    for u in units or []:
        if u.get("kind") != "process_reset":
            continue
        s = (u.get("section") or "").lower()
        for head, name in sorted(_PROCESS.items(), key=lambda x: -len(x[0])):
            if s.startswith(head):
                return name
        return "the routing process"
    return ""


# ── The title: what happened, in plain words (the GUI review's item 5, C3453) ──────────────

#: An incident's title is at most this many characters (docs/UI_RULES.md, "A title is a
#: summary of at most 70 characters"; measured: the incident page's heading was the
#: configuration line, 95 characters, two lines at 1280 px).
TITLE_MAX = 70
#: What a configuration line IS, in plain words, by its first words: a title names the thing
#: and never quotes the line (the line is What's wrong's). First match wins; a line none
#: matches is a setting of its section, else "configuration line".
_THINGS = tuple((re.compile(p), w) for p, w in (
    (r"ipv6 route\b", "IPv6 static route"), (r"ip route\b", "static route"),
    (r"(ip access-group|ipv6 traffic-filter)\b", "access list"),
    (r"((ip|ipv6) access-list|access-list)\b", "access list"),
    (r"(ip|ipv6) prefix-list\b", "prefix list"), (r"route-map\b", "route map"),
    (r"(bgp )?router-id\b", "router-id"), (r"logging (host\b|\d)", "logging host"),
    (r"logging\b", "logging setting"), (r"ntp server\b", "NTP server"), (r"ntp\b", "NTP setting"),
    (r"snmp-server\b", "SNMP setting"), (r"username\b", "local account"),
    (r"enable (secret|password)\b", "enable secret"), (r"aaa\b", "AAA setting"),
    (r"banner\b", "banner"), (r"hostname\b", "hostname"), (r"description\b", "description"),
    (r"ipv6 address\b", "IPv6 address"), (r"ip address\b", "IP address"),
    (r"(ip ospf|ipv6 ospf|ospfv3)\b", "OSPF setting"), (r"network\b", "network statement"),
    (r"neighbor\b", "neighbour"), (r"passive-interface\b", "passive interface"),
    (r"redistribute\b", "redistribution"), (r"service-policy\b", "QoS policy"),
    (r"standby\b", "HSRP setting"), (r"vrrp\b", "VRRP setting"),
    (r"switchport\b", "switchport setting"), (r"spanning-tree\b", "spanning-tree setting"),
    (r"channel-group\b", "port-channel membership"), (r"ip nat\b", "NAT setting"),
    (r"ip helper-address\b", "DHCP relay"), (r"ip dhcp\b", "DHCP setting"),
    (r"ip name-server\b", "DNS server"), (r"ip domain\b", "domain setting"),
    (r"ip ssh\b", "SSH setting"), (r"ip http\b", "HTTP server setting"),
    (r"telemetry\b", "telemetry subscription"), (r"crypto\b", "crypto setting"),
    (r"key chain\b", "key chain"), (r"line\b", "terminal lines"),
    (r"(router ospf|router ospfv3|ipv6 router ospf)\b", "OSPF process"),
    (r"router bgp\b", "BGP process"), (r"router eigrp\b", "EIGRP process"),
    (r"router isis\b", "IS-IS process"), (r"vlan\b", "VLAN"),
    (r"(vrf definition|ip vrf)\b", "VRF"), (r"mtu\b", "MTU"), (r"bandwidth\b", "bandwidth"),
    (r"(speed|duplex)\b", "speed or duplex"), (r"cdp\b", "CDP setting"),
    (r"lldp\b", "LLDP setting"), (r"(ip )?sla\b", "IP SLA"), (r"track\b", "tracking object"),
    (r"event manager\b", "EEM applet"), (r"interface\b", "interface")))
#: What happened to a unit's line on the device, by the unit's op (the op is the FIX's:
#: ``remove`` takes away what was added).
_VERBS = {"remove": "added", "add": "removed", "change": "changed"}
#: What a symptom fact is, by its kind, when the trigger behind it is not held.
_FACT_TITLES = {"config_change": "configuration changed outside Mercury",
                "departure": "departed from its approved configuration",
                "adjacency_log": "routing neighbour lost", "adjacency": "routing adjacency down",
                "alert": "an alert firing", "duplicate_router_id": "duplicate router-id"}


def thing_of(line: str) -> str:
    """What one configuration line is, in plain words (`_THINGS`), or ``""``."""
    text = (line or "").strip().lower()
    text = text[3:] if text.startswith("no ") else text
    return next((w for p, w in _THINGS if p.match(text)), "")


def _unit_title(u: dict) -> tuple:
    """``(thing, verb, where)`` for one unit, in plain words: ``("static route", "added",
    "")``, ``("access list", "added", " on GigabitEthernet2")``, ``("OSPF router-id",
    "changed", "")``. A joined unit is said by its use (its first part)."""
    u = (u.get("parts") or [u])[0] if isinstance(u, dict) else {}
    section = (u.get("section") or "").strip()
    lines = list(u.get("remove") or []) + list(u.get("add") or [])
    verb = _VERBS.get(u.get("op"), "changed")
    if u.get("stanza") or not lines:
        return (thing_of(section) or "configuration section", verb, "")
    first, iface = lines[0], interface_of(u)
    if first.strip().lower() == "shutdown" and iface:
        return (iface, "shut down" if verb == "added" else "brought back up", "")
    # In a section (not a top-level line, whose unit names the line as its section): a
    # routing process's setting carries the process's name ("OSPF router-id").
    inside = bool(section) and section not in {(l or "").strip() for l in lines}
    proc = next((name for head, name in sorted(_PROCESS.items(), key=lambda x: -len(x[0]))
                 if section.lower().startswith(head)), "") if inside and not iface else ""
    thing = thing_of(first)
    if proc and thing.startswith(proc):
        proc = ""
    if not thing:
        thing = ("setting" if proc or iface else
                 f"{thing_of(section)} setting" if inside and thing_of(section) else
                 "configuration line")
    return (f"{proc} {thing}" if proc else thing, verb, f" on {iface}" if iface else "")


def _many(thing: str) -> str:
    return thing if thing.endswith("s") else thing + "s"


def units_title(units: list) -> str:
    """What changed, in plain words, for a title: "static route added", "2 static routes
    added", "access list added on GigabitEthernet2, and 1 more change"; ``""`` for none."""
    said = [_unit_title(u) for u in units or [] if isinstance(u, dict)]
    if not said:
        return ""
    thing, verb, where = said[0]
    if len(said) > 1 and all(s == said[0] for s in said):
        return f"{len(said)} {_many(thing)} {verb}{where}"
    more = len(said) - 1
    return f"{thing} {verb}{where}" + (
        f", and {more} more change{'s' if more != 1 else ''}" if more else "")


def fix_title(units: list) -> str:
    """What putting the units back does, in plain words, for a stage's sentence (the Decided
    stage: "Heal: remove the static route"; the GUI review's HC1, C3454): never the line,
    which the decision's own words say one level down. ``""`` for none."""
    said = [_unit_title(u) for u in units or [] if isinstance(u, dict)]
    if not said:
        return ""

    def one(thing, verb, where, n=1):
        what = f"{n} {_many(thing)}{where}" if n > 1 else f"the {thing}{where}"
        return {"added": f"remove {what}", "removed": f"put back {what}",
                "shut down": f"bring {thing} back up",
                "brought back up": f"shut {thing} down again"}.get(verb, f"set {what} back")

    if len(said) > 1 and all(s == said[0] for s in said):
        return one(*said[0], n=len(said))
    more = len(said) - 1
    return one(*said[0]) + (f", and {more} more change{'s' if more != 1 else ''}"
                            if more else "")


def _symptom_title(t: dict, device: str, triggers: list) -> str:
    kind, proto = t.get("kind"), t.get("protocol") or "routing"
    if kind == "adjacency_log":
        peer, port = t.get("peer") or "", t.get("port") or ""
        return (f"{proto} neighbour {peer} lost" if peer else
                f"{proto} neighbour lost on {port}" if port else f"{proto} neighbour lost")
    if kind == "adjacency":
        other = next((d for d in t.get("related") or [] if d != device), "")
        return f"{proto} adjacency to {other} down" if other else f"{proto} adjacency down"
    if kind == "alert" and t.get("subscription"):
        n = len({x.get("subscription") for x in triggers
                 if x.get("kind") == "alert" and x.get("subscription")})
        return "telemetry stream lost" if n <= 1 else f"{n} telemetry streams lost"
    if kind == "alert":
        return f"alert “{t['rule']}” firing" if t.get("rule") else "an alert firing"
    if kind == "duplicate_router_id":
        return f"duplicate {t.get('protocol') or 'OSPF'} router-id"
    return _FACT_TITLES.get(kind, "")


def title(device: str, units: list = (), triggers: list = (), facts: list = (), *,
          room: int = TITLE_MAX) -> str:
    """THE title of an incident, in plain words and at most *room* characters (the GUI
    review's item 5, C3453; docs/UI_RULES.md, "A title is a summary of at most 70
    characters"): "<device>: <what happened>", never a configuration line, a code key, a
    mnemonic or an id; the line itself is What's wrong's. ONE builder: the incident's page
    (`incident_page.title`, its heading and its breadcrumb), its message's lead (through that), and
    every Needs attention and History line that leads with what happened (`headline`).

    What happened is, in this order: the decision's *units* (`units_title`: "static route
    added"), with "outside Mercury" where a configuration change from outside opened it (its
    cause's facts say so, else its *triggers*); else its first symptom (a trigger's own
    fields where *triggers* are held, else its cause's *facts* by kind); else what opened it.
    ``""`` when nothing is held. Past *room*, "outside Mercury" goes first, then the words are
    cut with an ellipsis."""
    host = device or "A device"
    trig = [t for t in triggers or [] if isinstance(t, dict)]
    facts = [f for f in facts or [] if isinstance(f, dict)]
    outside = (any(f.get("kind") == "config_change" for f in facts) if facts else
               any(t.get("kind") == "config_change" for t in trig))
    what, tail = units_title(units), ""
    if what:
        tail = " outside Mercury" if outside else ""
    else:
        sym = next((t for t in trig if t.get("kind") in SYMPTOMS), None)
        what = _symptom_title(sym, host, trig) if sym else ""
        if not what:
            fact = next((f for f in facts if f.get("kind") in SYMPTOMS), None)
            what = _FACT_TITLES.get((fact or {}).get("kind"), "")
        if not what:
            kinds = [t.get("kind") for t in trig] + [f.get("kind") for f in facts]
            first = next((k for k in kinds if k in ("config_change", "drift", "departure")), "")
            what = (_FACT_TITLES["config_change"] if first == "config_change" else
                    "departed from its golden" if first == "drift" else
                    _FACT_TITLES["departure"] if first == "departure" else "")
    if not what:
        return ""
    for text in (f"{host}: {what}{tail}", f"{host}: {what}"):
        if len(text) <= room:
            return text
    return text[:max(1, room - 1)].rstrip(" ,:;") + "…"


# ── The decision's words (`decide._outcome`) ───────────────────────────────────────────────

def outcome_words(outcome: str, *, units: list, kind: str, tier: int, device: str = "",
                  why: str = "", not_auto: list = (), dry_run: bool = True,
                  not_proposed: list = ()) -> str:
    """What Mercury did or would do, in plain words, its tier a label after them."""
    from modules.heal.kinds import KIND_WORDS

    host = device or "the device"
    fixes = fixes_words(units)
    proc = process_of(units)
    if outcome == "cant_fix" and tier >= 3 and kind in ("physical", "unknown_cause"):
        return (f"{host} is at its golden, which matches its intent, so no configuration fix "
                f"on {host} can cure this ({why}): Mercury fixes nothing by itself, and a "
                f"person decides (Tier {tier})")
    if outcome == "cant_fix" and tier >= 3:
        return (f"Mercury does not fix {KIND_WORDS.get(kind, kind)} by itself: {why}; nothing "
                f"was sent, and a person decides (Tier {tier})")
    if outcome == "cant_fix" and not_proposed:
        return (f"Nothing was sent: this fix needs a person, and the policy does not propose "
                f"{_join([KIND_WORDS.get(k, k) for k in not_proposed])}, so a person fixes it "
                f"(Tier {tier})")
    if outcome == "cant_fix":
        return f"Mercury cannot fix this yet: {why}; nothing was sent (Tier {tier})"
    if outcome == "propose":
        restart = (f", then restart {proc} on {host}, which briefly drops all of {host}'s "
                   f"{proc} neighbours, so a person decides when" if proc else
                   ", so a person decides")
        return (f"Mercury proposes a fix: {fixes}{restart}. Nothing is sent until a person "
                f"approves it (Tier {tier})")
    if outcome == "heal":
        return (f"Mercury is putting it back itself: {fixes}; this kind of fix may run by "
                f"itself here (Tier {tier})")
    if not_auto and not dry_run:
        names = _join([KIND_WORDS.get(k, k) for k in not_auto])
        return (f"Mercury would have put it back itself: {fixes}. Nothing was sent: {names} "
                f"{'is' if len(not_auto) == 1 else 'are'} not allowed to be fixed by itself "
                f"(Tier {tier})")
    return (f"Mercury would have put it back itself: {fixes}. Nothing was sent: the network "
            f"is watching only, in dry run (Tier {tier})")


def headline(d: dict, network: str = "", triggers: list = ()) -> str:
    """The one line a row and a History entry lead with (C2817; the mocks' rows): what
    happened on the device, as its incident's title says it (`title`, the one builder: plain
    words, never the configuration line, which the row's cause and the incident's What's
    wrong hold; the GUI review's item 5, C3453), then what Mercury did or would do and whether
    a person is needed. *triggers* are its incident's, where they are held (a symptom is then
    said by its own fields). ``""`` for an outcome it has no line for (its caller's own words
    stand). Deterministic, from the decision alone: a reader draws it again from the record,
    so a decision recorded before C3453 reads the same as one recorded after."""
    from modules.heal.kinds import KIND_WORDS

    host, outcome = d.get("device") or "the device", d.get("outcome")
    units, tier, kind = list(d.get("units") or []), int(d.get("tier") or 0), d.get("kind") or ""
    facts = list((d.get("cause") or {}).get("facts") or [])
    changed = changes_words(units)
    lead = title(host, units, triggers, facts) if changed else ""
    if outcome == "would_heal" and lead:
        net = network or d.get("network") or "the network"
        why = (f"{net} is watching only (dry run)" if d.get("mode") != "auto" else
               "this kind of fix is not allowed to run by itself")
        return f"{lead}. Mercury would have put it back itself, but {why}, so nothing was sent"
    if outcome == "propose" and lead:
        proc = process_of(units)
        does = f" that restarts {proc} on {host}" if proc else ""
        return f"{lead}. Mercury has a fix{does}: it needs your decision"
    if outcome == "heal" and lead:
        return f"{lead}. Mercury is putting it back itself"
    if outcome == "cant_fix" and tier >= 3 and kind in ("physical", "unknown_cause"):
        what = title(host, (), triggers, facts) or f"{host} shows a symptom"
        return f"{what}. {host} itself is as intended, so no fix on {host} can cure it"
    if outcome == "cant_fix" and lead:
        return (f"{lead}. Mercury does not fix {KIND_WORDS.get(kind, kind)} by itself: it "
                "needs a person" if tier >= 3 else
                f"{lead}. Mercury cannot fix it by itself: it needs a person")
    return ""


# ── The cause (C2823) ──────────────────────────────────────────────────────────────────────

def _epoch(t: dict) -> float:
    try:
        return float(t.get("epoch") or 0)
    except (TypeError, ValueError):
        return 0.0


def _at(t: dict) -> str:
    """A trigger's time as a record keeps it, ISO UTC, from its epoch (a reader's own ``at``
    may be in another form)."""
    return _iso(_epoch(t)) if _epoch(t) else str(t.get("at") or "")


def _ports(t: dict) -> list:
    """The interfaces a symptom names: a logged drop's, an alert's, a duplicate's."""
    out = [t.get("port") or "", t.get("interface") or ""] + list(t.get("interfaces") or [])
    return [p for p in out if p]


def symptom_words(t: dict, device: str) -> str:
    """One symptom as a fact, without its time (the fact carries it)."""
    kind = t.get("kind")
    if kind == "adjacency_log" and (t.get("neighbor") or t.get("peer")):
        who = t.get("logged_by") or device
        peer, nbr = t.get("peer") or "", t.get("neighbor") or ""
        named = f"{peer} ({nbr})" if peer and nbr and peer != nbr else (peer or nbr)
        return (f"{who} lost its {t.get('protocol') or 'routing'} neighbour {named}"
                + (f" on {t['port']}" if t.get("port") else "")
                + (f": {t['reason'].strip()}" if (t.get("reason") or "").strip() else ""))
    if kind == "adjacency":
        ends = " – ".join([device] + [d for d in t.get("related") or [] if d != device])
        return f"the {t.get('protocol') or 'routing'} adjacency {ends} went down"
    return _ISO_TAIL.sub("", t.get("words") or "").strip() or (kind or "a symptom")


def _acl_entries(name: str, units: list) -> list:
    """The ACL *name*'s entries as the same change added them, or None when the change did not
    define it (its entries are then not known here)."""
    for u in units or []:
        m = _ACL_HEAD.match(u.get("section") or "")
        if m and m.group(3) == name and u.get("op") == "remove":
            return [l for l in current_lines(u)[1:] if _ENTRY.match(l)] \
                if current_lines(u) and _ACL_HEAD.match(current_lines(u)[0]) else \
                [l for l in current_lines(u) if _ENTRY.match(l)]
    numbered = [l for u in units or [] if u.get("op") == "remove" for l in current_lines(u)
                if (_NUMBERED.match(l) or ["", ""])[1] == name]
    return numbered or None


def _standard(name: str, units: list) -> bool:
    for u in units or []:
        m = _ACL_HEAD.match(u.get("section") or "")
        if m and m.group(3) == name:
            return m.group(2) == "standard"
    return name.isdigit() and (1 <= int(name) <= 99 or 1300 <= int(name) <= 1999)


def permits_ospf(entries: list, *, ipv6: bool, standard: bool) -> bool:
    """Whether any entry permits OSPF: a standard ACL's permit (it filters by source only), or
    an extended entry permitting ``ip``/``ipv6``, ``ospf`` or protocol 89."""
    for line in entries:
        m = _NUMBERED.match(line)
        action, proto = ((m.group(2), (m.group(3).split() or [""])[0]) if m else
                         (_ENTRY.match(line).groups() if _ENTRY.match(line) else ("", "")))
        if action != "permit":
            continue
        if standard or proto.lower() in ("ospf", "89", "ipv6" if ipv6 else "ip"):
            return True
    return False


def _link(units: list, symptoms: list, change_epoch: float, device: str) -> tuple:
    """``(extra facts, hypothesis)`` where both ends of one cause are held, else ``([], None)``."""
    for s in symptoms:
        if change_epoch and _epoch(s) and _epoch(s) < change_epoch:
            continue
        for port in _ports(s):
            for u in units:
                where = interface_of(u)
                if not where or not same_interface(where, port):
                    continue
                at = _at(s)
                lost = symptom_words(s, device)
                ospf = (s.get("protocol") or "").upper().startswith("OSPF")
                for line in current_lines(u):
                    m = _APPLY.match(line)
                    if not m or not ospf:
                        continue
                    ipv6, name, way = m.group(1).startswith("ipv6"), m.group(2), m.group(3)
                    entries = _acl_entries(name, units)
                    if entries is None or permits_ospf(entries, ipv6=ipv6,
                                                       standard=_standard(name, units)):
                        continue
                    n = _plural(len(entries), "entry", "entries")
                    fact = {"text": (f"the ACL {name}, applied {way}bound on {where}, permits "
                                     f"no OSPF: none of its {n} does, and an ACL drops what it "
                                     "does not permit"), "at": "", "epoch": 0.0, "kind": "acl"}
                    return [fact], {"label": HYPOTHESIS, "at": at,
                                    "text": f"this ACL drops OSPF on {where}, so {lost}"}
                return [], {"label": HYPOTHESIS, "at": at,
                            "text": (f"the change on {where} broke what was lost on it: "
                                     f"{lost}")}
    for s in symptoms:
        rid = s.get("router_id") or ""
        if s.get("kind") != "duplicate_router_id" or not rid:
            continue
        for u in units:
            if any((_ROUTER_ID.match(l) or [None, None])[1] == rid for l in current_lines(u)):
                others = [d for d in s.get("related") or [] if d != device]
                also = f", which {_join(others)} also uses" if others else ""
                return [], {"label": HYPOTHESIS, "at": _at(s),
                            "text": (f"{device}'s router-id is now {rid}{also}: two routers "
                                     "with one router-id cannot peer")}
    return [], None


def cause_of(triggers: list, decision: dict) -> dict:
    """The cause the decision states (the module's docstring), or None when nothing is held.
    *triggers* are the incident's judged triggers (`decide.judged_triggers`), whole."""
    device = decision.get("device") or ""
    units = flat(decision.get("units"))
    trig = [t for t in triggers or [] if isinstance(t, dict)]
    changes = sorted((t for t in trig if t.get("kind") == "config_change"), key=_epoch)
    symptoms = sorted((t for t in trig if t.get("kind") in SYMPTOMS), key=_epoch)
    facts = []
    what = changes_words(units)
    if changes:
        last = changes[-1]
        person = ((decision.get("person") or {}).get("words")
                  or (last.get("person") or {}).get("words") or "")
        facts.append({"text": (f"{device}'s configuration was changed outside Mercury"
                               + (f" ({person})" if person else "")
                               + (f": {what}" if what else "")),
                      "at": _at(last), "epoch": _epoch(last), "kind": "config_change"})
    elif what:
        facts.append({"text": f"{device} differs from its approved configuration: {what}",
                      "at": "", "epoch": 0.0, "kind": "departure"})
    seen = set()
    for s in symptoms:
        text = symptom_words(s, device)
        if text in seen:
            continue
        seen.add(text)
        facts.append({"text": text, "at": _at(s), "epoch": _epoch(s), "kind": s.get("kind")})
        if len(seen) >= 4:
            break
    extra, hypothesis = _link(units, symptoms, _epoch(changes[-1]) if changes else 0.0, device)
    facts += extra
    if not facts:
        return None
    timed = sorted((f for f in facts if f["epoch"]), key=lambda f: f["epoch"])
    return {"facts": timed + [f for f in facts if not f["epoch"]], "hypothesis": hypothesis}


def drawn(cause: dict) -> dict:
    """The cause as a page draws it (`_macros.heal_cause`): each fact's words and time, the
    hypothesis's label and words; None when there is none."""
    if not cause or not cause.get("facts"):
        return None
    h = cause.get("hypothesis")
    return {"facts": [{"text": f.get("text") or "", "at": f.get("at") or ""}
                      for f in cause["facts"]],
            "hypothesis": {"label": h.get("label") or HYPOTHESIS, "text": h.get("text") or ""}
            if h else None}


def _cap(text: str) -> str:
    """*text* to start a sentence: a leading "the" or "a" capitalised, never a device's name
    (a label, its case its own)."""
    return text[:1].upper() + text[1:] if re.match(r"(?:the|a|an) ", text or "") else text


def _clause(f: dict) -> str:
    return f"At {hhmm(f['epoch'])} UTC, {f['text']}" if f.get("epoch") else _cap(f["text"])


def sentence(cause: dict) -> str:
    """The cause as one paragraph for a record or a message: each fact "At HH:MM UTC, …", then
    the hypothesis, labelled."""
    if not cause:
        return ""
    out = [_clause(f) + "." for f in cause.get("facts") or []]
    h = cause.get("hypothesis")
    if h:
        out.append(f"{h['label']}: {h['text']}.")
    return " ".join(out)


def with_cause(cause: dict, words: str) -> str:
    """The decision's words with its cause first (facts first, rule 5)."""
    said = sentence(cause)
    return f"{said} {words}" if said and words else (said or words)


# ── A can't-fix whose likeliest cause is another device's change (C2817's amendment) ───────

def likely_elsewhere(incident: dict, incidents: list) -> dict:
    """Another device's change that is the likeliest cause of *incident*'s symptom, labelled
    as a hypothesis (the operator, 2026-11-09: "Open <device> (likely cause)"): an open incident on
    another device holding a configuration change from outside Mercury, made at most
    `LIKELY_S` before this incident's first symptom; one the symptom's own triggers name
    (``related``) first, else the only one in the network. None when none is held, or when
    several unnamed ones are (never a guess between them). ``{"device", "at", "epoch",
    "words"}``."""
    from modules.heal import incidents as INC

    host = incident.get("device") or ""
    trig = [t for t in incident.get("triggers") or [] if isinstance(t, dict)]
    first = min((_epoch(t) for t in trig if t.get("kind") in SYMPTOMS and _epoch(t)),
                default=0.0)
    if not first:
        return None
    related = {d for t in trig for d in t.get("related") or []}
    found = []
    for other in incidents or []:
        dev = other.get("device") or ""
        if dev == host or other.get("state") not in INC.OPEN_STATES:
            continue
        ch = [t for t in other.get("triggers") or [] if isinstance(t, dict)
              and t.get("kind") == "config_change" and first - LIKELY_S <= _epoch(t) <= first]
        if ch:
            c = max(ch, key=_epoch)
            found.append({"device": dev, "at": _at(c),
                          "epoch": _epoch(c),
                          "words": (c.get("person") or {}).get("words") or ""})
    named = [f for f in found if f["device"] in related]
    pick = named or (found if len({f["device"] for f in found}) == 1 else [])
    return max(pick, key=lambda f: f["epoch"]) if pick else None
