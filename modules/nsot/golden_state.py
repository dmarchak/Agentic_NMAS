"""Golden state: the network CONFIGURED as approved AND WORKING (register E7).

Dr. Perigo's "golden state of the network" is a claim that everything is
working as intended. A baseline could not make it: a `baseline/<ts>` tag is
every device's config at one moment, and a broken moment and a good one read
the same. So a baseline taken here carries the fleet's OPERATIONAL snapshot,
read with the verify readers fixed against real output (C62, C64-C68), and it
earns the stronger claim only when every routing protocol each device's
committed intent declares is up on that device.

**The two claims** (Stage 7's `baseline-is-earned` draws which one a baseline
makes):
- ``configured``: every device's configuration captured. The only claim a
  baseline taken without a snapshot can make, and the eleven on the host
  before this existed make exactly that.
- ``configured and working``: that, AND every declared protocol up on every
  device, read at the same moment.

**"Up", per protocol, from real output** (`tests/fixtures/operational/`):
- ``ospf``, ``ospfv3``: at least one neighbour, and every neighbour FULL or
  2WAY. 2WAY is the steady state between DROTHERs on a broadcast segment
  (r1 and s3 show it), so "all FULL" would call a healthy segment broken.
- ``bgp``: at least one peer configured, and every configured peer
  ESTABLISHED.
- ``rip``: at least one gateway in RIP's own Information Sources table.
- ``ripng``: at least one next hop being heard. Not "learned a route": r1
  hears s1 and installs nothing, because OSPFv3 carries those prefixes at a
  better distance (measured 2026-09-27), so the route table would call a
  working RIPng broken.

**It fails closed, and names why.** A device not read, a device with no
committed intent (so what it should run is unknown), and a declared protocol
the tool does not measure all mean "not working", each stated as its reason.
None becomes a pass by being absent.

**What it does not read, stated in the claim:** the heartbeats (Loki and
Grafana). NMAS reads no alert state until 7.2's reader, so the snapshot is
the routing plane and the interfaces, not the syslog path.
"""

import logging
import time

log = logging.getLogger(__name__)

CONFIGURED = "configured"
WORKING = "configured and working"

NOT_READ = ["heartbeats: NMAS reads no alert state until 7.2's reader, so the "
            "syslog path is not part of this snapshot"]

#: What any snapshot of this kind cannot see, carried in every tag (the
#: operator, 2026-09-27; the census's honest-limits line is the precedent).
LIMITS = ("the tool sees what the managed devices report about themselves. A peer "
          "outside management, a link the emulator abstracts, and anything beyond "
          "the managed fleet are invisible to it, and 'established' or 'FULL' is "
          "ONE side's report of a two-sided relationship.")


def managed_addresses(configs: dict) -> dict:
    """``{address: hostname}`` from each managed device's configuration: every
    `ip address` and `ipv6 address` (loopbacks too, since an OSPF neighbour
    is named by its router ID). IPv6 is upper-cased without its length."""
    import re

    out = {}
    for host, text in (configs or {}).items():
        for line in (text or "").splitlines():
            m = re.match(r"^\s+ip address\s+(\d+\.\d+\.\d+\.\d+)\s", line)
            if m:
                out[m.group(1)] = host
            m = re.match(r"^\s+ipv6 address\s+([0-9A-Fa-f:]+)/\d+", line)
            if m:
                out[m.group(1).upper()] = host
    return out


def outside_management(protocols: dict, address_map: dict) -> tuple:
    """``(outside, unattributed)`` for one device's protocols.

    *outside* names every routing peer that is not an address of a managed
    device: its state is observed only from this side. *unattributed* names
    what cannot be tied to a device at all from configurations (RIPng next
    hops are link-local), stated rather than guessed."""
    outside, unattributed = [], []

    def check(proto, peer):
        if peer and peer.upper() not in address_map and peer not in address_map:
            outside.append(f"{proto} {peer}")

    for peer in (protocols.get("bgp") or {}).get("peers") or []:
        check("bgp", peer.get("neighbor", ""))
    for proto in ("ospf", "ospfv3"):
        for rid in (protocols.get(proto) or {}).get("neighbors") or []:
            check(proto, rid)
    for source in (protocols.get("rip") or {}).get("sources") or []:
        check("rip", source.get("gateway", ""))
    hops = (protocols.get("ripng") or {}).get("next_hops") or []
    if hops:
        unattributed.append(f"ripng: {len(hops)} link-local next hop(s), not tied to a "
                            "device from configurations")
    return outside, unattributed

#: The protocols this module can judge. A declared protocol outside this set
#: is "declared, not measured", which is not working.
MEASURED = ("ospf", "ospfv3", "bgp", "rip", "ripng")


def declared_protocols(host_vars: dict) -> list:
    """The routing protocols a device's COMMITTED intent declares."""
    routing = (host_vars or {}).get("routing") or {}
    out = []
    for name in ("ospf", "ospfv3", "ripng"):
        if routing.get(name):
            out.append(name)
    for name in ("bgp", "rip"):
        if routing.get(name):
            out.append(name)
    for name, value in routing.items():
        if name not in out and name not in ("ospf", "ospfv3", "ripng", "bgp", "rip") \
                and value:
            out.append(name)
    return sorted(out)


def protocol_up(name: str, measured: dict) -> tuple:
    """``(up, why)`` for one declared protocol, from what verify's reader
    returned for it (``None`` when the device did not answer for it)."""
    if name not in MEASURED:
        return False, f"{name} is declared and this tool does not measure it"
    if not measured:
        return False, f"{name} is declared and the device reported none"
    if name in ("ospf", "ospfv3"):
        states = measured.get("states") or []
        if not states:
            return False, f"{name}: no neighbour"
        bad = [s for s in states if not s.upper().startswith(("FULL", "2WAY"))]
        if bad:
            return False, f"{name}: neighbour(s) not FULL or 2WAY: {bad}"
        return True, f"{name}: {len(states)} neighbour(s), all FULL or 2WAY"
    if name == "bgp":
        peers = measured.get("peers") or []
        if not peers:
            return False, "bgp: no peer configured"
        down = [p.get("neighbor") for p in peers if not p.get("established")]
        if down:
            return False, f"bgp: peer(s) not established: {down}"
        return True, f"bgp: {len(peers)} peer(s), all established"
    if name == "rip":
        sources = measured.get("sources") or []
        return (bool(sources), f"rip: {len(sources)} gateway(s) heard"
                if sources else "rip: no gateway heard")
    hops = measured.get("next_hops") or []
    return (bool(hops), f"ripng: {len(hops)} next hop(s) heard"
            if hops else "ripng: no next hop heard")


def judge_device(declared: list, snapshot: dict, *, intent_known: bool = True) -> dict:
    """``{"working", "why", "protocols"}`` for one device."""
    if not intent_known:
        return {"working": False, "protocols": {},
                "why": ["no committed intent, so what this device should run is "
                        "unknown"]}
    per = (snapshot.get("routing_neighbors") or {}).get("protocols") or {}
    protocols, why = {}, []
    for name in declared:
        up, reason = protocol_up(name, per.get(name))
        protocols[name] = {"up": up, "why": reason}
        if not up:
            why.append(reason)
    if not declared:
        why_ok = ["no routing protocol declared: a real state, nothing to judge"]
    else:
        why_ok = [p["why"] for p in protocols.values()]
    return {"working": not why, "protocols": protocols, "why": why or why_ok}


def take(devices: list, read, intent_for, address_map: dict = None) -> dict:
    """The fleet's operational snapshot and the claim it supports.

    *read(device)* returns `pipeline._capture_operational_snapshot`'s dict or
    raises; *intent_for(hostname)* returns committed host_vars or None. Both
    are injected so the judgement is testable without a device.
    """
    rows, unread = {}, []
    for device in devices:
        host = device.get("hostname", device.get("ip", ""))
        intent = intent_for(host)
        try:
            snap = read(device)
        except Exception as exc:               # noqa: BLE001
            unread.append(host)
            rows[host] = {"working": False, "read": False,
                          "why": [f"not read: {type(exc).__name__}: {exc}"]}
            continue
        declared = declared_protocols(intent) if intent is not None else []
        judged = judge_device(declared, snap, intent_known=intent is not None)
        per = (snap.get("routing_neighbors") or {}).get("protocols") or {}
        if address_map is None:
            outside, unattributed = None, []
        else:
            outside, unattributed = outside_management(per, address_map)
        rows[host] = {
            "read": True, "declared": declared, **judged,
            "outside_management": outside,
            "unattributed": unattributed,
            "interfaces_up": (snap.get("interfaces") or {}).get("up_count"),
            "routes": (snap.get("routes") or {}).get("total_count"),
        }
    working = bool(rows) and all(r["working"] for r in rows.values())
    return {
        "taken_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "claim": WORKING if working else CONFIGURED,
        "working": working,
        "devices": rows,
        "unread": sorted(unread),
        "not_working": sorted(h for h, r in rows.items() if not r["working"]),
        "not_read": list(NOT_READ),
        "outside_management": {h: r["outside_management"] for h, r in rows.items()
                               if r.get("outside_management")},
        "outside_assessed": address_map is not None,
        "limits": LIMITS,
    }


def claim_lines(snapshot: dict) -> list:
    """The lines a baseline tag's message carries, for a person reading it."""
    if not snapshot:
        return [f"Claim: {CONFIGURED} (no operational snapshot was taken)",
                f"Limits: {LIMITS}"]
    outside = snapshot.get("outside_management") or {}
    count = sum(len(v) for v in outside.values())
    claim = snapshot["claim"]
    if claim == WORKING and count:
        claim += (f", resting on {count} routing peer(s) outside management, whose "
                  "state is observed from one side only (named below)")
    lines = [f"Claim: {claim}"]
    for host, row in sorted(snapshot["devices"].items()):
        state = "working" if row["working"] else "NOT working"
        lines.append(f"  {host}: {state}: {'; '.join(row['why'])}")
    for host, peers in sorted(outside.items()):
        lines.append(f"Outside management: {host}: {', '.join(peers)}")
    if not snapshot.get("outside_assessed", True):
        lines.append("Outside management: NOT assessed (no address map was supplied)")
    for host, row in sorted(snapshot["devices"].items()):
        for note in row.get("unattributed") or []:
            lines.append(f"Unattributed: {host}: {note}")
    lines += [f"Not read: {n}" for n in snapshot["not_read"]]
    lines.append(f"Limits: {snapshot.get('limits', LIMITS)}")
    return lines
