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
