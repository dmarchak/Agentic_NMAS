"""nsot/expected_effects.py

What a change INTENDS, so verify can tell an intended effect from a failure (C506, board
approved 2026-10-06).

Verify compared COUNTS before and after. So a program's own `shutdown` counted as a loss and
was rolled back, and because interfaces were counted, not named, a cable move that downs Gi3
and brings up Gi4 netted to zero and would hide an untouched interface lost at the same moment.

This module answers two questions, both by NAME:

* :func:`derive`: the effects the program itself implies. An interface section it shuts is
  expected to go down; one it brings up (`no shutdown`) is expected to be up when verify ends.
* :func:`interface_states`: each interface's state from the read verify already makes
  (`show interfaces | include (line protocol|Internet address)`).

and :func:`judge` compares them: an interface up before and down after that the program did
not shut is UNEXPECTED (a hard failure, rolled back after a short settle), one it shut is
expected, and one it brings up that is not up is the intended end state not reached.
"""

import re

#: IOS abbreviations, longest first, to the name `show interfaces` prints.
_ABBREVIATIONS = (
    ("tengigabitethernet", "TenGigabitEthernet"), ("te", "TenGigabitEthernet"),
    ("gigabitethernet", "GigabitEthernet"), ("gi", "GigabitEthernet"),
    ("fastethernet", "FastEthernet"), ("fa", "FastEthernet"),
    ("ethernet", "Ethernet"), ("et", "Ethernet"),
    ("port-channel", "Port-channel"), ("po", "Port-channel"),
    ("loopback", "Loopback"), ("lo", "Loopback"),
    ("tunnel", "Tunnel"), ("tu", "Tunnel"),
    ("vlan", "Vlan"), ("vl", "Vlan"),
)

_STATE_LINE = re.compile(r"^(\S+) is (administratively down|up|down|deleted)[^,]*, "
                         r"line protocol is (up|down)", re.I)


def canonical(name: str) -> str:
    """*name* as `show interfaces` prints it (`Gi3` -> `GigabitEthernet3`); unknown prefixes are
    returned as given."""
    m = re.match(r"^([A-Za-z-]+)\s*([0-9/.:]+)$", (name or "").strip())
    if not m:
        return (name or "").strip()
    word, number = m.group(1).lower(), m.group(2)
    for short, full in _ABBREVIATIONS:
        if word == short:
            return full + number
    return m.group(1) + number


def interface_states(output: str) -> dict:
    """``{interface: "up" | "down" | "admin_down"}`` from the interfaces read; "up" only when
    the line protocol is up. Empty when nothing could be parsed (the caller then falls back to
    counting, and says so)."""
    states = {}
    for line in (output or "").splitlines():
        m = _STATE_LINE.match(line.strip())
        if not m:
            continue
        name, admin, proto = m.group(1), m.group(2).lower(), m.group(3).lower()
        if admin == "administratively down":
            states[name] = "admin_down"
        elif proto == "up":
            states[name] = "up"
        else:
            states[name] = "down"
    return states


def derive(commands) -> dict:
    """The interface effects the program implies: ``{"down": [...], "up": [...]}``, sorted
    canonical names. Within an `interface X` section, `shutdown` expects X down and
    `no shutdown` expects X up; the last of the two in a section wins, as on the device."""
    effect = {}
    current = None
    for raw in commands or []:
        line = (raw or "").rstrip()
        stripped = line.strip()
        if not stripped or stripped == "!":
            continue
        if not line.startswith(" ") and not line.startswith("\t"):
            m = re.match(r"^interface\s+(\S+)", stripped, re.I)
            current = canonical(m.group(1)) if m else None
            if stripped.lower() in ("exit", "end"):
                current = None
            continue
        if current is None:
            continue
        if stripped.lower() == "shutdown":
            effect[current] = "down"
        elif stripped.lower() == "no shutdown":
            effect[current] = "up"
    return {"down": sorted(n for n, e in effect.items() if e == "down"),
            "up": sorted(n for n, e in effect.items() if e == "up")}


def _ospf_on(commands, interface: str) -> bool:
    """Whether the program enables OSPF on *interface* (`ip ospf N area A` in its section)."""
    current = None
    for raw in commands or []:
        line = (raw or "").rstrip()
        if line and not line[0].isspace():
            m = re.match(r"^interface\s+(\S+)", line.strip(), re.I)
            current = canonical(m.group(1)) if m else None
        elif current == interface and re.match(r"^(ip ospf \d+ area|ipv6 ospf \d+ area|"
                                                r"ospfv3 \d+ ipv6 area)", line.strip()):
            return True
    return False


def _interface_networks(hv: dict) -> dict:
    """``{canonical interface: ip_network}`` of the IPv4 addresses intent gives *hv*'s
    interfaces."""
    import ipaddress

    out = {}
    for iface in (hv or {}).get("interfaces") or []:
        address = (iface.get("ipv4") or "").split()
        if len(address) == 2:
            try:
                out[canonical(iface.get("name", ""))] = ipaddress.ip_interface(
                    f"{address[0]}/{address[1]}").network
            except ValueError:
                continue
    return out


def for_device(intents: dict, host: str, commands) -> dict:
    """Every effect the program implies on *host*, derived, never declared (C506 phase 2):

    * ``down``, ``up``: interfaces the program shuts and brings up (:func:`derive`);
    * ``adjacencies_drop``: each adjacency committed intent puts on an interface the program
      shuts (OSPF and OSPFv3, by interface), and each BGP session sourced from one
      (`neighbor X update-source IFACE`) or to a peer on one's subnet, with why;
    * ``may_form``: an interface the program brings up with OSPF enabled on it: an adjacency
      may form there, required only if a person declares who it is with.

    Read from committed intent, never the device: what the plan shows is what verify uses."""
    import ipaddress

    from modules.neighbours import expected as expected_adjacencies

    fx = derive(commands)
    down = set(fx["down"])
    hv = intents.get(host) or {}
    drops = []
    for adj in expected_adjacencies(intents, host):
        if adj["proto"] in ("ospf", "ospfv3") and canonical(adj.get("via", "")) in down:
            drops.append({"proto": adj["proto"], "peer": adj.get("peer", ""),
                          "rid": adj.get("rid", ""), "address": adj.get("address", ""),
                          "via": canonical(adj["via"]),
                          "why": f"its adjacency is on {canonical(adj['via'])}, which the "
                                 "program shuts"})
    bgp_lines = (((hv.get("routing") or {}).get("bgp") or {}).get("neighbors") or [])
    sources = {}
    for line in bgp_lines:
        m = re.match(r"^neighbor (\S+) update-source (\S+)", (line or "").strip())
        if m:
            sources[m.group(1)] = canonical(m.group(2))
    nets = _interface_networks(hv)
    owners = {}
    try:
        from modules.neighbours import addresses
        owners = addresses(intents)
    except Exception:                          # noqa: BLE001
        owners = {}
    for line in bgp_lines:
        m = re.match(r"^neighbor (\S+) remote-as (\S+)", (line or "").strip())
        if not m:
            continue
        peer = m.group(1)
        why = ""
        if sources.get(peer) in down:
            why = f"it is sourced from {sources[peer]}, which the program shuts"
        else:
            try:
                addr = ipaddress.ip_address(peer)
            except ValueError:
                continue
            for name in sorted(down):
                net = nets.get(name)
                if net is not None and addr.version == net.version and addr in net:
                    why = f"its peer is on {name}'s subnet, and the program shuts {name}"
                    break
        if why:
            try:
                owner = owners.get(ipaddress.ip_address(peer), "")
            except ValueError:
                owner = ""
            drops.append({"proto": "bgp", "peer": owner, "rid": "", "address": peer,
                          "via": sources.get(peer, ""), "why": why})
    return {"down": fx["down"], "up": fx["up"], "adjacencies_drop": drops,
            "may_form": [{"proto": "ospf", "via": n} for n in fx["up"] if _ospf_on(commands, n)]}


def _addr(value: str) -> str:
    import ipaddress
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return (value or "").strip().lower()


def expected_ids(drops, proto: str) -> set:
    """The identities of *proto*'s adjacencies expected to drop: OSPF and OSPFv3 by the peer's
    router-id (what `show ip ospf neighbor` prints as Neighbor ID), BGP by the peer's address.
    An adjacency whose identity intent does not give (no explicit router-id) is not counted as
    expected, so its loss still fails verify: the safe reading."""
    key = "address" if proto == "bgp" else "rid"
    return {(_addr(d.get(key)) if proto == "bgp" else d.get(key))
            for d in drops or [] if d.get("proto") == proto and d.get(key)}


def neighbour_ids(snapshot: dict, proto: str) -> set:
    """The identities a neighbour read holds for *proto*: OSPF's neighbour router-ids, BGP's
    ESTABLISHED peers' addresses (what verify counts)."""
    info = ((snapshot or {}).get("protocols") or {}).get(proto) or {}
    if proto == "bgp":
        return {_addr(p.get("neighbor")) for p in info.get("peers") or []
                if p.get("established")}
    return set(info.get("neighbors") or [])


# ---------------------------------------------------------------------------
# Declared effects (C506 phase 3): what the program cannot show, declared by a person with a
# reason, in the confirmed plan's hash and the record. Three kinds (the board, approved
# 2026-10-06); anything else that happens is still unexpected.
# ---------------------------------------------------------------------------

#: The kinds a person may declare, and how the card names each.
DECLARE_WORDS = {"moves": "An adjacency moves",
                 "ends": "A session ends (decommission)",
                 "routes": "Routes are expected to change"}

_PROTO_WORDS = {"ospf": "OSPF", "ospfv3": "OSPFv3", "bgp": "BGP"}

#: OSPF states that count as an adjacency having formed: FULL, and 2WAY, the steady state
#: between two DROTHERs on a broadcast segment (r1 and s3 show three).
_FORMED_STATES = ("FULL", "2WAY")


def _adj_id(proto: str, ident: str, via: str = "") -> str:
    return f"{proto}:{ident}" + (f"@{via}" if via else "")


def offers(intents: dict, host: str, effects: dict) -> dict:
    """What a person may declare on this plan, each by an id the form sends back:

    * ``moves``: each OSPF or OSPFv3 adjacency the program drops (derived) whose identity intent
      gives (a router-id), to be re-formed elsewhere;
    * ``to``: the interfaces it may move to: those the program brings up with OSPF on them;
    * ``ends``: each other adjacency committed intent puts on *host*, with an identity, that the
      program does not already drop (a session decommissioned at the far end, a peer retired).

    Routes need no choice: a reason alone declares them."""
    from modules.neighbours import expected as expected_adjacencies

    drops = (effects or {}).get("adjacencies_drop") or []
    moves = [{"id": _adj_id(d["proto"], d["rid"], d.get("via", "")), "proto": d["proto"],
              "peer": d.get("peer", ""), "rid": d["rid"], "from": d.get("via", "")}
             for d in drops if d.get("proto") in ("ospf", "ospfv3") and d.get("rid")]
    to = sorted({m.get("via", "") for m in (effects or {}).get("may_form") or []
                 if m.get("via")})
    dropped = {(d.get("proto"), _addr(d.get("address")) if d.get("proto") == "bgp"
                else d.get("rid")) for d in drops}
    ends, seen = [], set()
    for adj in expected_adjacencies(intents or {}, host):
        proto = adj.get("proto")
        if proto not in _PROTO_WORDS:
            continue
        ident = _addr(adj.get("address")) if proto == "bgp" else adj.get("rid")
        if not ident or (proto, ident) in dropped:
            continue
        item_id = _adj_id(proto, ident)
        if item_id in seen:
            continue
        seen.add(item_id)
        ends.append({"id": item_id, "proto": proto, "peer": adj.get("peer", ""),
                     "rid": "" if proto == "bgp" else ident,
                     "address": ident if proto == "bgp" else "",
                     "via": "" if proto == "bgp" else canonical(adj.get("via", ""))})
    return {"moves": moves, "to": to, "ends": ends}


def _who(d: dict) -> str:
    proto = _PROTO_WORDS.get(d.get("proto"), d.get("proto", ""))
    ident = d.get("address") if d.get("proto") == "bgp" else d.get("rid")
    if d.get("peer"):
        return f"{proto} to {d['peer']}" + (f" ({ident})" if ident else "")
    return f"{proto} to {ident}"


def words(d: dict) -> str:
    """One declaration as a person reads it."""
    if d.get("kind") == "moves":
        return f"{_who(d)} moves from {d.get('from')} to {d.get('to')}"
    if d.get("kind") == "ends":
        return f"{_who(d)} ends"
    return "the route table is expected to change"


def offer_words(o: dict) -> str:
    """An offered adjacency as the card's choice names it."""
    where = o.get("from") or o.get("via")
    return _who(o) + (f" over {where}" if where else "")


def raw_of(d: dict) -> dict:
    """A canonical declaration back in the form it was declared in (``{kind, id, to?,
    reason}``): what the card carries between plans, so each re-plan checks it again."""
    if d.get("kind") == "moves":
        return {"kind": "moves", "id": _adj_id(d["proto"], d["rid"], d.get("from", "")),
                "to": d.get("to", ""), "reason": d.get("reason", "")}
    if d.get("kind") == "ends":
        ident = _addr(d.get("address")) if d.get("proto") == "bgp" else d.get("rid")
        return {"kind": "ends", "id": _adj_id(d["proto"], ident), "reason": d.get("reason", "")}
    return {"kind": d.get("kind", ""), "reason": d.get("reason", "")}


def declared_from(raw, offer: dict) -> tuple:
    """``(declared, problems)``: each declaration in *raw* checked against what *offer* holds,
    in the canonical shape the hash folds in and verify reads. A declaration that names
    something the plan does not offer, or whose reason is not the shape of one, is a problem
    naming it, never silently dropped: the caller refuses the plan with it."""
    from modules.nsot.authorisation import reason_problem

    moves = {m["id"]: m for m in (offer or {}).get("moves") or []}
    ends = {e["id"]: e for e in (offer or {}).get("ends") or []}
    to = set((offer or {}).get("to") or [])
    out, problems, seen = [], [], set()
    for item in raw or []:
        if not isinstance(item, dict):
            problems.append(f"{item!r} is not a declaration")
            continue
        kind, reason = item.get("kind"), str(item.get("reason") or "").strip()
        if kind == "moves":
            m = moves.get(item.get("id"))
            target = canonical(item.get("to") or "")
            if m is None:
                problems.append(f"the adjacency {item.get('id')!r} is not one this program "
                                "drops, so it cannot be declared to move")
                continue
            if target not in to:
                problems.append(f"{_who(m)} cannot be declared to move to {target or 'nothing'}"
                                ": the program brings up no interface of that name with OSPF "
                                "on it" + (f" (it may move to {', '.join(sorted(to))})"
                                           if to else ""))
                continue
            entry = {"kind": "moves", "proto": m["proto"], "peer": m["peer"], "rid": m["rid"],
                     "from": m["from"], "to": target, "reason": reason}
            ident = ("moves", m["id"])
        elif kind == "ends":
            e = ends.get(item.get("id"))
            if e is None:
                problems.append(f"the adjacency {item.get('id')!r} is not one committed intent "
                                "gives this device outside what the program drops, so it "
                                "cannot be declared to end")
                continue
            entry = {"kind": "ends", "proto": e["proto"], "peer": e["peer"], "rid": e["rid"],
                     "address": e["address"], "reason": reason}
            ident = ("ends", e["id"])
        elif kind == "routes":
            entry, ident = {"kind": "routes", "reason": reason}, ("routes",)
        else:
            problems.append(f"{kind!r} is not a kind of declaration (one of "
                            f"{', '.join(DECLARE_WORDS)})")
            continue
        why = reason_problem({"line": words(entry), "reason": reason})
        if why:
            problems.append(why)
            continue
        if ident in seen:
            problems.append(f"{words(entry)} is declared twice")
            continue
        seen.add(ident)
        out.append(entry)
    return out, problems


def as_drops(declared) -> list:
    """The adjacencies a declaration expects to go away, in the shape of a derived drop: an
    ended session, and a moved adjacency's old place (verify then requires the new one)."""
    out = []
    for d in declared or []:
        if d.get("kind") in ("moves", "ends"):
            out.append({"proto": d["proto"], "peer": d.get("peer", ""), "rid": d.get("rid", ""),
                        "address": d.get("address", ""), "via": d.get("from", ""),
                        "why": f"declared: {d.get('reason', '')}"})
    return out


def neighbour_rows(snapshot: dict, proto: str) -> list:
    """``[{"id", "interface", "state"}]`` from a neighbour read of OSPF or OSPFv3."""
    info = ((snapshot or {}).get("protocols") or {}).get(proto) or snapshot or {}
    return [{"id": r.get("neighbor_id", ""), "interface": canonical(r.get("interface", "")),
             "state": r.get("state", "")} for r in info.get("rows") or []]


def judge_move(move: dict, rows: list, before: list = ()) -> dict:
    """Where a declared move's adjacency is in *rows*: ``formed`` on the declared interface;
    ``elsewhere`` (formed on another interface than the declared one and its old one, named);
    ``replaced`` (someone NEW formed on the declared interface, and the declared peer did not:
    both named); ``absent``. A neighbour already on the declared interface *before* the change
    replaces nothing: a broadcast segment holds several."""
    up = [r for r in rows or [] if (r.get("state") or "").upper().startswith(_FORMED_STATES)]
    on_to = [r for r in up if r["interface"] == move.get("to")]
    mine = [r for r in up if r["id"] == move.get("rid")]
    if any(r["id"] == move.get("rid") for r in on_to):
        return {"state": "formed", "on": move.get("to")}
    elsewhere = sorted({r["interface"] for r in mine} - {move.get("from")})
    if elsewhere:
        return {"state": "elsewhere", "on": elsewhere}
    already = {r["id"] for r in before or [] if r.get("interface") == move.get("to")}
    others = sorted({r["id"] for r in on_to} - already)
    if others:
        return {"state": "replaced", "others": others}
    return {"state": "absent"}


def move_words(move: dict, judged: dict, seconds) -> str:
    """The issue a move that did not happen raises, naming what was found instead."""
    who = _who(move)
    if judged["state"] == "elsewhere":
        return (f"{who} was declared to move to {move['to']}, and re-formed on "
                f"{', '.join(judged['on'])} instead")
    if judged["state"] == "replaced":
        return (f"{who} was declared to move to {move['to']}; within {seconds} s an adjacency "
                f"formed there with {', '.join(judged['others'])} (not declared), and "
                f"{move.get('rid')} did not")
    return f"{who} was declared to move to {move['to']}, and did not form there within {seconds} s"


def judge(expected: dict, before: dict, after: dict) -> dict:
    """Compare the interface states by name against the expected effects.

    ``{"lost_expected": [...], "lost_unexpected": [...], "not_up": [...], "came_up": [...]}``:
    up before and not up after, split by whether the program shut it; an interface the program
    brings up that is not up; and anything that came up. Interfaces missing from either read
    are not judged (a read that lists fewer interfaces is the caller's to treat as unreadable)."""
    down = set(expected.get("down") or [])
    up = set(expected.get("up") or [])
    lost = sorted(n for n, s in before.items() if s == "up" and n in after and after[n] != "up")
    return {
        "lost_expected": [n for n in lost if n in down],
        "lost_unexpected": [n for n in lost if n not in down],
        "not_up": sorted(n for n in up if after.get(n) != "up"),
        # The program shuts it and it is still up: the program did not take (C506 phase 2).
        "not_down": sorted(n for n in down if before.get(n) == "up" and after.get(n) == "up"),
        "came_up": sorted(n for n, s in after.items() if s == "up" and before.get(n) != "up"),
    }
