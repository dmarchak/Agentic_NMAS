"""The paired deploy: both ends of a link deployed as ONE change (C1908's deploy side and C1909;
the operator's design on board F7-Q, 2026-10-27).

A two-ended request in words commits both devices' intent in one commit
(`intent_words.commit_pair`). Its deploy is the existing plan for the ticked devices with both
ticked (`routes.v2._apply_ctx`, scope ``intent``, carrying the link): one preview, each device's
exact program, one confirm by hash as a verified person. The apply is the batch's own
(`routes.deploy.apply_batch` with *pair*), each device through the one pipeline; this module is
what the pair adds to it, in the order the steps run (`STEPS`):

- ``order`` (C1965): which end goes first, judged by Mercury's management path to each device
  from the Topology reader's stored read (`order_for`, `topology`): the end Mercury reaches
  THROUGH the other goes first, so the other's change cannot cut Mercury off from it before it
  is changed or rolled back; neither reached through the other, the link's own order. The
  pair is refused when the read cannot be used or names no path to an end (refused, never
  guessed), or when the link carries an end's only management path and either program can
  take the link down: each order then puts a change on a path it needs (the near end first
  cuts the far end off; the far end first cuts its own path, so it could not be rolled back),
  and no order keeps both ends reachable through every step and its rollback. (The two ends
  cannot each be reached through the other: on a shortest path the end passed through is the
  nearer.) The preview states the order and its
  reason; the confirm and the apply judge it again, and a moved order or a refusal refuses
  both, nothing sent.
- ``both_or_neither``: a device refused at apply (its program moved, another operation holds
  it) refuses the other too, by name, with nothing sent to either: half a link change is never
  started.
- ``first_end``, ``second_end``: each device's pipeline, in the rollout order, with its own
  verify, and its save to startup HELD (`PipelineContext.hold_save`); the second end is sent
  only when the first deployed (anything else, and it is never sent). On the FIRST end the
  link's own line protocol and its adjacency to the far end (by the far end's router ID on
  the link's interface) are an expected transient between the two applies (C1964;
  `transient_for`, `PipelineContext.pair_transient`): its own verify leaves them to the link's
  verify after both ends, and says so; every other interface and adjacency is judged as ever.
- ``link_verify``: once both have applied, the link itself is read on both ends (`verify_link`):
  the link's line protocol on each end (a trunk's and a tunnel's state with it), and the OSPF or
  OSPFv3 adjacency across it when the change touched that protocol, each read only through a
  command the read-only allowlist passes (`readonly_commands.refusal`), polled within the
  network's settle windows as verify polls (`convergence.wait_for`). A read that could not be
  made, or not trusted, neither passes nor fails.
- ``paired_rollback``: if either end failed (its apply or its own verify, which its pipeline has
  already rolled back) or the link's verify failed, the other end is rolled back too, by the
  pipeline's own rollback (`pipeline.roll_back_after`: what landed read back, the undo built from
  that run's pre-change read, the device read back after it), and each rolled-back device's
  intent is marked rolled back, the single-device path's record of a change that did not land
  (`hostvars.record_rolled_back`), so the next plan does not offer it again; an end never sent
  is marked the same way, so its half is never offered alone.
- ``save_both``: when nothing failed, the held saves run, both ends.
- ``record``: each device's receipt says what it achieved, and the link's verify and why it was
  rolled back (``pair`` on its row, `receipts.rows_for`).

**Trunk forwarding is read as the link's line protocol on both ends.** The VLANs each end of a
trunk forwards are not read: there is no captured `show interfaces trunk` to build that parser
on (fixtures are real captures), so the check names what it reads and what it does not.
"""

import logging
import os
import re
import time

log = logging.getLogger(__name__)

#: The steps, as the manual's deploy page names them (docs/manual/how-it-works/deploy.md).
STEPS = (
    ("order", "the end Mercury reaches through the other goes first, from the Topology read; "
              "refused when the read cannot say, or when no order keeps both reachable"),
    ("both_or_neither","a device refused at apply, or held by another operation, refuses the "
                        "other too; nothing is sent to either"),
    ("first_end", "the first device's pipeline, its own verify (the link's own line protocol "
                  "and adjacency left to the link's verify), its save to startup held"),
    ("second_end", "the second device's pipeline, sent only when the first deployed"),
    ("link_verify", "the link read on both ends within the settle windows: its line protocol, "
                    "and the adjacency across it when the change touched OSPF or OSPFv3"),
    ("paired_rollback", "either end failed or the link did: both ends rolled back, each "
                        "device's intent marked rolled back"),
    ("save_both", "nothing failed: both ends saved to startup"),
    ("record", "each device's receipt, with the link's verify and why it was rolled back"),
)

#: The reads the link's verify makes, each one the pipeline's own (`pipeline._INTERFACES_READ`,
#: `pipeline._ROUTING_READS`), so the link is read as verify reads a device.
CHECK_WORDS = {"state": "the link's line protocol on both ends",
               "ospf": "the OSPF adjacency across the link",
               "ospfv3": "the OSPFv3 adjacency across the link"}
#: The settle window each check waits in (`convergence.window_for`).
WINDOW = {"state": "interfaces", "ospf": "ospf", "ospfv3": "ospfv3"}

PASSED, FAILED, UNREADABLE, NOT_JUDGED, NOT_REACHED = (
    "passed", "failed", "unreadable", "not_judged", "not_reached")
#: The link verify's states as a result says them.
STATE_WORDS = {PASSED: "the link verified", FAILED: "the link's verify FAILED",
               UNREADABLE: "the link could not be read, so its verify neither passed nor failed",
               NOT_JUDGED: "the link's state was not judged",
               NOT_REACHED: "the link was not verified: both ends did not deploy"}

#: Seconds to sleep between polls; tests pass a no-op (the pipeline's `settle_sleep`).
SLEEP = None


class LinkRefused(ValueError):
    """A link a paired deploy cannot carry: said, and nothing is planned or sent."""


# ── the link ─────────────────────────────────────────────────────────────────────

def link_of(text: str) -> dict:
    """``{"device", "port", "far", "far_port"}`` from the link as a page carries it,
    ``"<device>:<port>,<far>:<far port>"`` (`link_text`); raises `LinkRefused` naming it."""
    from modules.nsot import ifnames

    halves = [e.strip() for e in str(text or "").split(",")]
    parts = [e.partition(":") for e in halves]
    if len(halves) != 2 or not all(h.strip() and sep and p.strip() for h, sep, p in parts):
        raise LinkRefused(f"the link {str(text)[:80]!r} is not two ends, each a device and its "
                          "interface (device:interface,device:interface)")
    (a, _s, pa), (b, _t, pb) = parts
    if a.strip() == b.strip():
        raise LinkRefused(f"both ends of the link {text!r} are on {a.strip()}: a paired deploy "
                          "is two devices")
    return {"device": a.strip(), "port": ifnames.canonical(pa.strip()), "far": b.strip(),
            "far_port": ifnames.canonical(pb.strip())}


def link_text(link: dict) -> str:
    return f"{link['device']}:{link['port']},{link['far']}:{link['far_port']}"


def link_words(link: dict) -> str:
    return f"{link['device']} {link['port']} ↔ {link['far']} {link['far_port']}"


def ends(link: dict) -> list:
    """``[(device, port), (far, far port)]``."""
    return [(link["device"], link["port"]), (link["far"], link["far_port"])]


def link_problem(link: dict, intents: dict, order: list = None) -> str:
    """Why *link* cannot be deployed as a pair against committed *intents* (``""``: it can):
    each end's interface must be in its device's committed intent, and the devices ticked
    (*order*, when given) must be exactly the link's two."""
    from modules.nsot import ifnames

    if order is not None and sorted(order) != sorted([link["device"], link["far"]]):
        return (f"the devices to deploy ({', '.join(order) or 'none'}) are not exactly the two "
                f"ends of the link {link_words(link)}: both ends deploy together, or neither")
    for host, port in ends(link):
        hv = (intents or {}).get(host)
        if not hv:
            return f"{host} has no committed intent, so its end of the link cannot be deployed"
        if not any(ifnames.same_interface(str(i.get("name", "")), port)
                   for i in hv.get("interfaces") or [] if isinstance(i, dict)):
            return f"{port} is not in {host}'s committed intent, so the link cannot be verified"
    return ""


# ── what the change touches, and what the link's verify checks ───────────────────

def _sections(commands) -> list:
    """``[(header, child)]``: each line of a program under the unindented line that opened its
    section (a header itself with child ``""``); ``exit`` and ``end`` are no line."""
    out, head = [], ""
    for raw in commands or []:
        text = str(raw or "").rstrip()
        if not text.strip() or text.strip() in ("exit", "end", "!"):
            continue
        if not text[:1].isspace():
            head = text.strip()
            out.append((head, ""))
        else:
            out.append((head, text.strip()))
    return out


def touched(commands, port: str) -> dict:
    """What a program does to the link at its end: ``{"families": set, "admin": str}``. A
    family is touched by a line in *port*'s section (`switchport`: trunk; `tunnel`: tunnel;
    `ip ospf` or an IPv4 address: OSPF; `ospfv3`, `ipv6 ospf` or an IPv6 address: OSPFv3) or
    in an OSPF process's (`router ospf`: OSPF; `router ospfv3`, `ipv6 router ospf`: OSPFv3);
    *admin* is ``shutdown`` or ``no shutdown`` when the program sets the port's state, the last
    one winning as on the device."""
    from modules.nsot import ifnames

    fams, admin = set(), ""
    for head, child in _sections(commands):
        words = head.split()
        if not child:
            continue
        low = child.lower()
        if words[:1] == ["interface"] and len(words) > 1 \
                and ifnames.same_interface(words[1], port):
            if re.match(r"(no )?switchport\b", low):
                fams.add("trunk")
            elif re.match(r"(no )?tunnel\b", low):
                fams.add("tunnel")
            elif re.match(r"(no )?ip (ospf|address)\b", low):
                fams.add("ospf")
            elif re.match(r"(no )?(ospfv3|ipv6 ospf|ipv6 address)\b", low):
                fams.add("ospfv3")
            elif low in ("shutdown", "no shutdown"):
                admin = low
        elif words[:2] == ["router", "ospf"]:
            fams.add("ospf")
        elif words[:2] == ["router", "ospfv3"] or words[:3] == ["ipv6", "router", "ospf"]:
            fams.add("ospfv3")
    return {"families": fams, "admin": admin}


def _carries(link: dict, intents: dict) -> dict:
    """``{"ospf": bool, "ospfv3": bool, "rid": {device: router id}}``: whether committed intent
    puts each protocol's adjacency across this link, from both ends (`neighbours.expected`, the
    adjacencies Verify's expectations read), and each end's router ID there."""
    from modules import neighbours
    from modules.nsot import ifnames

    out = {"ospf": True, "ospfv3": True, "rid": {}}
    for (host, port), (other, _p) in ((ends(link)[0], ends(link)[1]),
                                      (ends(link)[1], ends(link)[0])):
        try:
            adj = neighbours.expected(intents, host)
            rid = neighbours.router_id((intents or {}).get(host) or {})
        except Exception as exc:                        # noqa: BLE001 (a document it cannot read)
            log.warning("paired deploy: %s's adjacencies could not be read (%s)", host, exc)
            adj, rid = [], ""
        out["rid"][host] = rid
        for proto in ("ospf", "ospfv3"):
            out[proto] = out[proto] and any(
                a["proto"] == proto and a.get("peer") == other
                and ifnames.same_interface(str(a.get("via", "")), port) for a in adj)
    return out


def link_checks(link: dict, programs: dict, intents: dict) -> list:
    """The checks the link's verify makes, each ``{"family", "expect", "words", "notes"}``, from
    the two programs and the committed intent they were rendered from (read once by the
    caller). The link's state is always checked; an adjacency is checked when either program
    touches its protocol, or brings the port up where intent puts the adjacency: expected FULL
    on both ends when committed intent puts it across the link, absent otherwise."""
    got = {host: touched((programs or {}).get(host) or [], port) for host, port in ends(link)}
    families = set().union(*(g["families"] for g in got.values()))
    carried = _carries(link, intents)
    admin = {h: g["admin"] for h, g in got.items()}
    notes = []
    if "trunk" in families:
        notes.append("the trunk's forwarding is read as its line protocol on both ends; the "
                     "VLANs each end forwards are not read")
    if "tunnel" in families:
        notes.append("the tunnel is read as its line protocol on both ends")
    checks = [{"family": "state", "expect": dict(admin), "words": CHECK_WORDS["state"],
               "notes": notes}]
    up = any(a == "no shutdown" for a in admin.values())
    for proto in ("ospf", "ospfv3"):
        if proto in families or (up and carried[proto]):
            checks.append({"family": proto, "expect": "full" if carried[proto] else "absent",
                           "words": CHECK_WORDS[proto], "rid": dict(carried["rid"]),
                           "notes": []})
    return checks


def checks_words(checks: list) -> list:
    """Each check as the preview says it: what is read, and what it must find."""
    out = []
    for c in checks:
        if c["family"] == "state":
            shut = [h for h, a in c["expect"].items() if a == "shutdown"]
            want = (f"administratively down on {' and '.join(shut)}, as the program shuts it "
                    "there" if shut else "up on both ends")
        else:
            want = ("FULL on both ends" if c["expect"] == "full"
                    else "gone, as committed intent no longer puts it across the link")
        out.append(f"{c['words']}: {want}" + "".join(f" ({n})" for n in c.get("notes") or []))
    return out


# ── the first end's expected transient (C1964) ────────────────────────────────────

def transient_for(link: dict, host: str, intents: dict, checks: list,
                  first: bool = True) -> dict:
    """What an end's own verify leaves to the link's verify (the pipeline's
    `PipelineContext.pair_transient`): ``{"interface", "far", "ids": {"ospf": rid, "ospfv3":
    rid}, "line", "words"}``, or None.

    The FIRST end (``first_end``): between the two applies the link's own line protocol on this
    end, and its adjacency to the far end, can be down as the change intends (OSPF
    authentication on one end only drops the adjacency until the other end has it), so they
    are judged once, by the link's verify after both ends (``line`` True). An adjacency is left
    out only where the link's verify judges it (*checks*, `link_checks`: the change touches
    that protocol); otherwise it is judged here as ever. It is named by the far end's router
    ID AND this end's interface: the far end's router ID on another interface (two routers
    can also meet on a core VLAN) is judged as ever, and so is the adjacency of a far end whose router
    ID committed intent does not give; the words say so.

    The SECOND end (``second_end``, *first* False): its line protocol is judged as ever, and
    the link's adjacency, which its change brings BACK, is left out of both sides of its own
    count, as on the first end; counted, its return would net against an adjacency lost
    elsewhere on that device and hide it. None when the link's verify judges no adjacency."""
    mine = next((port for h, port in ends(link) if h == host), "")
    other = next((h for h, _p in ends(link) if h != host), "")
    rid = (_carries(link, intents).get("rid") or {}).get(other) or ""
    judged = {c.get("family") for c in checks or []}
    ids = {p: rid for p in ("ospf", "ospfv3") if rid and p in judged}
    if not first:
        return ({"interface": mine, "far": other, "ids": ids, "line": False, "words": (
            f"the adjacency to {other} on {mine}: judged by the link's verify after both "
            "ends")} if ids else None)
    words = f"the link to {other}: judged after both ends"
    if not rid and judged & {"ospf", "ospfv3"}:
        words += (f" (its line protocol only: {other}'s router ID is not in its committed "
                  "intent, so its adjacency is judged here as ever)")
    elif not ids:
        words += (" (its line protocol only: the change does not touch the adjacency across "
                  "it, which is judged here as ever)")
    return {"interface": mine, "far": other, "ids": ids, "line": True, "words": words}


# ── the order: Mercury's management path to each end (C1965) ───────────────────────

#: A cable that carries traffic, as `topology_graph.mercury_reach` reads them: up, or a state
#: no read could give (a down or ghost cable carries nothing).
_CARRYING = ("up", "unknown")
#: A family `touched` finds, as a refusal names it.
_FAMILY_WORDS = {"ospf": "OSPF", "ospfv3": "OSPFv3", "trunk": "trunk", "tunnel": "tunnel"}


def topology(list_name: str) -> dict:
    """The network's observed cables as Mercury's network model maps them
    (`network_model.observed`, the Topology reader's stored read: LLDP's links and where
    Mercury's own host attaches, ``mercury_attaches_here``): ``{"names": {device: model id},
    "nodes": {id: node}, "cables": {id: cable}, "read_at", "why"}``. One stored value read and
    the model from this process's memory; no device and no source is asked. *why* says why the
    read cannot be used, and the order is then refused, never guessed."""
    from modules import network_model as M

    out = {"names": {}, "nodes": {}, "cables": {}, "read_at": "", "why": ""}
    try:
        model, err = M.model_for(list_name)
    except Exception as exc:                            # noqa: BLE001 (said, never raised)
        model, err = None, f"{type(exc).__name__}: {exc}"
    if model is None:
        return dict(out, why=f"the network model could not be built ({err})")
    out.update(names=dict(model.get("names") or {}), nodes=dict(model.get("nodes") or {}))
    try:
        obs = M.observed(list_name, model)
    except Exception as exc:                            # noqa: BLE001 (said, never raised)
        obs = {"state": "could not read", "why": f"{type(exc).__name__}: {exc}"}
    out["read_at"] = obs.get("read_at") or ""
    if obs.get("state") != "read":
        return dict(out, why="the Topology read could not be used ("
                             + (obs.get("why") or "no reason was given") + ")")
    out["cables"] = dict(obs.get("cables") or {})
    return out


def _graph(cables: dict, skip=()) -> dict:
    """``{node: [(other, this node's port, other's port, cable id)]}`` over the cables that
    carry traffic, less *skip*."""
    g = {}
    for cid, cable in sorted((cables or {}).items()):
        e = cable.get("ends") or []
        if cid in skip or len(e) != 2 or cable.get("state") not in _CARRYING:
            continue
        a, b = e
        g.setdefault(a.get("dev", ""), []).append((b.get("dev", ""), a.get("port", ""),
                                                   b.get("port", ""), cid))
        g.setdefault(b.get("dev", ""), []).append((a.get("dev", ""), b.get("port", ""),
                                                   a.get("port", ""), cid))
    return g


def _distances(g: dict) -> dict:
    """Each node's hops from Mercury's host, breadth first; an outside peer is reached and
    never walked through (as `network_model._walk`)."""
    from modules.network_model import MANAGER_ID

    dist, frontier = {MANAGER_ID: 0}, [MANAGER_ID]
    while frontier:
        nxt = []
        for node in frontier:
            if node.startswith("ext:"):
                continue
            for other, _mine, _theirs, _cid in g.get(node) or []:
                if other not in dist:
                    dist[other] = dist[node] + 1
                    nxt.append(other)
        frontier = nxt
    return dist


def _paths_to(g: dict, dist: dict, target: str):
    """Every SHORTEST path from Mercury's host to *target*, as what they share: ``{"transit":
    {node}, "cables": {cable id}, "hops": [(node, its port, target's port, cable id)]}`` (the
    last hops into *target*), or None when no carrying cable reaches it. Every shortest path,
    not one: with equal paths Mercury's traffic may take any, so an end on any of them could
    sit on the path."""
    from modules.network_model import MANAGER_ID

    if target not in dist or target == MANAGER_ID:
        return None
    transit, cables, hops, seen, frontier = set(), set(), [], {target}, [target]
    while frontier:
        nxt = []
        for node in frontier:
            for other, mine, theirs, cid in g.get(node) or []:
                if other.startswith("ext:") or dist.get(other, -9) != dist[node] - 1:
                    continue
                cables.add(cid)
                if node == target:
                    hops.append((other, theirs, mine, cid))
                if other != MANAGER_ID:
                    transit.add(other)
                    if other not in seen:
                        seen.add(other)
                        nxt.append(other)
        frontier = nxt
    return {"transit": transit, "cables": cables, "hops": sorted(hops)}


def _link_cables(cables: dict, ids: dict, link: dict) -> set:
    """The observed cable(s) that ARE the link: the near end's port to the far end's."""
    from modules.nsot import ifnames

    want = {(ids.get(h), p) for h, p in ends(link)}
    out = set()
    for cid, cable in (cables or {}).items():
        e = cable.get("ends") or []
        if len(e) == 2 and all(any(x.get("dev") == d and ifnames.same_interface(
                str(x.get("port") or ""), p) for d, p in want) for x in e) \
                and e[0].get("dev") != e[1].get("dev"):
            out.add(cid)
    return out


def _hop_words(hop: tuple, label: dict, link_cids: set) -> str:
    """One last hop into a device, as the preview says it."""
    from modules.network_model import MANAGER_ID
    from modules.nsot import ifnames

    node, port, theirs, cid = hop
    if node == MANAGER_ID:
        return f"directly, on its {ifnames.canonical(theirs) or 'port'}"
    return (f"through {label.get(node, node.replace('ext:', ''))} "
            f"{ifnames.canonical(port) or '(port not named)'}"
            + (", the link being changed" if cid in link_cids else ""))


def _reach_words(paths: dict, label: dict, link_cids: set) -> str:
    hops = paths["hops"]
    first = _hop_words(hops[0], label, link_cids)
    # The link first when it is one of the equal paths: it is the one the change sits on.
    on_link = [h for h in hops if h[3] in link_cids]
    if on_link:
        first = _hop_words(on_link[0], label, link_cids)
    rest = [_hop_words(h, label, link_cids) for h in hops if _hop_words(h, label, link_cids)
            != first]
    return first + (f" (and {' and '.join(rest)})" if rest else "")


def can_cut(commands, port: str) -> str:
    """Why *commands* could take the link at *port* down, in words ("" when they cannot): a
    line in the port's section other than its description (an OSPF setting, an address, its
    state, a trunk's or tunnel's line, an MTU), or a line in an OSPF or OSPFv3 process (read as
    the link's protocol, `touched`). A description cannot. What a program does elsewhere on
    the device is each device's own verify's, as in any deploy."""
    from modules.nsot import ifnames

    got = touched(commands, port)
    if got["families"]:
        return ("changes the link's "
                + " and ".join(_FAMILY_WORDS[f] for f in sorted(got["families"])))
    if got["admin"]:
        return f"sends `{got['admin']}` to {port}"
    for head, child in _sections(commands):
        words = head.split()
        if child and words[:1] == ["interface"] and len(words) > 1 \
                and ifnames.same_interface(words[1], port) \
                and not re.match(r"(no )?description\b", child.lower()):
            return f"changes {port} beyond its description"
    return ""


def order_for(link: dict, topo: dict, programs: dict = None) -> dict:
    """``order`` (C1965): which end goes first, from Mercury's management path to each
    (*topo*, `topology`). ``{"order": [first, second], "words", "refused", "paths": {device:
    words}}``; *refused* non-empty means the pair is not offered, and *words* is the preview's
    sentence ("edge2 first: Mercury reaches edge2 through edge1 GigabitEthernet4, the link
    being changed").

    The end Mercury reaches THROUGH the other (the other end is on a shortest path to it) goes
    first: the other end's change then cannot cut Mercury off from it before it is changed or
    rolled back. Neither through the other: the link's own order. Refused, saying why and
    naming the path: the read cannot be used, or names no path from Mercury to an end
    (unknown, never guessed); or, with *programs*
    given (the plan and the apply; the confirm judges the order alone), either program can
    take the link down (`can_cut`) while the link carries an end's ONLY management path: then
    the near end first cuts the far end off before it is changed, and the far end first leaves
    it unreachable for its rollback should the near end fail, so no order keeps both ends
    reachable through every step and its rollback."""
    from modules.network_model import MANAGER_ID

    near, far = link["device"], link["far"]
    out = {"order": [near, far], "words": "", "refused": "", "paths": {}}
    both = f"{near} and {far}"
    if topo.get("why"):
        return dict(out, refused=(f"Mercury's management path to {both} is unknown: "
                                  f"{topo['why']}; the order is refused rather than guessed"))
    ids = topo.get("names") or {}
    missing = [h for h in (near, far) if h not in ids]
    if missing:
        return dict(out, refused=(f"{' and '.join(missing)} is not in the network's model, so "
                                  "Mercury's management path to it is unknown; the order is "
                                  "refused rather than guessed"))
    label = {i: n for n, i in ids.items()}
    g = _graph(topo.get("cables"))
    if MANAGER_ID not in g:
        return dict(out, refused=("the Topology read shows nowhere Mercury's host attaches, so "
                                  f"its management path to {both} is unknown; the order is "
                                  "refused rather than guessed"))
    dist = _distances(g)
    paths = {h: _paths_to(g, dist, ids[h]) for h in (near, far)}
    lost = [h for h, p in paths.items() if p is None]
    if lost:
        return dict(out, refused=(
            f"the Topology read names no path from Mercury to {' or '.join(lost)} (no carrying "
            "cable reaches it from where Mercury's host attaches), so its management path is "
            "unknown; the order is refused rather than guessed"))
    link_cids = _link_cables(topo.get("cables"), ids, link)
    said = {h: _reach_words(p, label, link_cids) for h, p in paths.items()}
    out["paths"] = {h: f"Mercury reaches {h} {w}" for h, w in said.items()}
    # At most one end is behind the other: on a shortest path the end passed through is
    # nearer Mercury than the end reached, so the two cannot each be behind the other. The
    # case where each order puts a change on a path it needs is the one below.
    behind = {near: ids[far] in paths[near]["transit"], far: ids[near] in paths[far]["transit"]}
    cut = ""
    for host, port in ends(link) if programs is not None else ():
        why = can_cut((programs or {}).get(host) or [], port)
        if why:
            cut = f"{host}'s program {why}"
            break
    without = {}
    if cut and any(paths[h]["cables"] & link_cids for h in (near, far)):
        g2 = _graph(topo.get("cables"), skip=link_cids)
        d2 = _distances(g2)
        alone = [h for h in (near, far) if paths[h]["cables"] & link_cids and ids[h] not in d2]
        if alone:
            h = alone[0]
            other = far if h == near else near
            return dict(out, refused=(
                f"{out['paths'][h]}, and that link is its only management path, while {cut}: "
                f"{other} first would cut Mercury off from {h} before {h} is changed, and {h} "
                f"first would leave {h} unreachable for its rollback should {other} fail; no "
                "order keeps both ends reachable through every step and its rollback"))
        for h in (near, far):
            if paths[h]["cables"] & link_cids:
                without[h] = _reach_words(_paths_to(g2, d2, ids[h]), label, set())
    first = far if behind[far] else near
    second = near if first == far else far
    if behind[first]:
        words = f"{first} first: {out['paths'][first]}"
    else:
        words = (f"{first} first, as the link names it: neither end is reached through the "
                 f"other ({out['paths'][near]}; {out['paths'][far]})")
    if without:
        words += ("; without that link Mercury still reaches "
                  + " and ".join(f"{h} {w}" for h, w in without.items())
                  + ", so a change that takes the link down leaves both ends reachable")
    return dict(out, order=[first, second], words=words)


def refused_order(link: dict, why: str) -> list:
    """``order`` refused at apply: both ends refused, by name, nothing sent to either."""
    return [{"device": host, "outcome": "refused", "reason": (
        f"not sent: the order of the link {link_words(link)} could not be kept ({why}); both "
        "ends change together, or neither does. Nothing was sent.")} for host, _p in ends(link)]


# ── reading the link ──────────────────────────────────────────────────────────────

def _read(device: dict, command: str) -> str:
    """One read-only command on *device*, on a session of its own (as verify's own re-reads
    are): refused unless the read-only allowlist passes it whole."""
    from modules import readonly_commands
    from modules.commands import run_device_command
    from modules.connection import with_temp_connection

    why = readonly_commands.refusal(command)
    if why:
        raise ValueError(why)
    return with_temp_connection(device, lambda conn: run_device_command(conn, command))


def _command(family: str) -> str:
    from modules import pipeline
    return pipeline._INTERFACES_READ if family == "state" else pipeline._ROUTING_READS[family]


def _end_read(family: str, device: dict, port: str) -> dict:
    """One end's read for *family*: ``{"state"}`` (the port's state: up, down, admin_down) or
    ``{"rows"}`` (the neighbour rows on the port), or ``{"unreadable": why}``."""
    from modules import pipeline
    from modules.nsot.expected_effects import canonical, interface_states

    try:
        text = _read(device, _command(family)) or ""
    except Exception as exc:                            # noqa: BLE001 (an unreadable read)
        return {"unreadable": f"{type(exc).__name__}: {exc}"}
    if re.search(r"(?m)^\s*% ", text):
        return {"unreadable": "the device answered with an error: "
                              + next(ln.strip() for ln in text.splitlines()
                                     if ln.strip().startswith("%"))[:120]}
    if family == "state":
        states = interface_states(text)
        if canonical(port) not in states:
            return {"unreadable": f"{port} is not in the interfaces read"
                                  + ("" if states else " (nothing in it could be parsed)")}
        return {"state": states[canonical(port)]}
    return {"rows": [r for r in pipeline._parse_ospf_neighbor_rows(text)
                     if canonical(r.get("interface", "")) == canonical(port)]}


def read_state(link: dict, devices: dict) -> dict:
    """The link's state on both ends, read once: ``{device: {"state"} or {"unreadable"}}`` (the
    read before anything is sent, which the state check's expectation is judged against)."""
    return {host: _end_read("state", devices.get(host) or {}, port) for host, port in ends(link)}


def _judge(check: dict, link: dict, got: dict, before: dict) -> dict:
    """One check's verdict on one read of both ends: ``{"state", "words"}``."""
    unread = {h: e["unreadable"] for h, e in got.items() if "unreadable" in e}
    said = "; ".join(f"{h}: {why}" for h, why in unread.items())
    if check["family"] == "state":
        admin = check["expect"]
        shut = [h for h, a in admin.items() if a == "shutdown"]
        # A shut end is expected administratively down. Its far end is not judged then: whether
        # a link partner's line protocol falls with it depends on the medium (an emulated link
        # can stay up), so judging it could roll back a shutdown that landed as intended.
        want = ({h: "admin_down" for h in shut} if shut
                else {host: "up" for host, _port in ends(link)})
        was = {h: (before or {}).get(h) or {} for h, _p in ends(link)}
        brought_up = any(a == "no shutdown" for a in admin.values())
        if not shut and not brought_up and all("state" in w for w in was.values()) \
                and not all(w["state"] == "up" for w in was.values()):
            return {"state": NOT_JUDGED, "words": (
                "the link was not up before the change ("
                + ", ".join(f"{h} {w['state'].replace('_', ' ')}" for h, w in was.items())
                + "), and the change does not bring it up, so its state is not judged")}
        if unread:
            return {"state": UNREADABLE, "words": f"not read: {said}"}
        now = {h: e["state"] for h, e in got.items()}
        ok = all(now[h] == w for h, w in want.items())
        shown = ", ".join(f"{h} {now[h].replace('_', ' ')}" for h in now)
        if ok:
            return {"state": PASSED, "words": f"read {shown}"}
        if not shut and any("unreadable" in w for w in was.values()):
            return {"state": UNREADABLE, "words": (
                f"read {shown}, and the read before the change could not be made, so whether "
                "the change downed it is unknown")}
        expected = ", ".join(f"{h} {w.replace('_', ' ')}" for h, w in want.items())
        return {"state": FAILED, "words": f"read {shown}; expected {expected}"}
    if unread:
        return {"state": UNREADABLE, "words": f"not read: {said}"}
    rid = check.get("rid") or {}
    proto = "OSPF" if check["family"] == "ospf" else "OSPFv3"
    found = {}
    for (host, port), (other, _p) in ((ends(link)[0], ends(link)[1]),
                                      (ends(link)[1], ends(link)[0])):
        rows = got[host]["rows"]
        peer = rid.get(other) or ""
        mine = [r for r in rows if not peer or r.get("neighbor_id") == peer]
        found[host] = (port, other, peer, mine)
    if check["expect"] == "full":
        bad = [f"{h} {port} has no FULL adjacency to {other}"
               + (f" ({peer})" if peer else "")
               + (f": {', '.join(r['neighbor_id'] + ' ' + r['state'] for r in mine)}"
                  if mine else "")
               for h, (port, other, peer, mine) in found.items()
               if not any(str(r.get("state", "")).upper().startswith("FULL") for r in mine)]
        if bad:
            return {"state": FAILED, "words": f"{proto}: " + "; ".join(bad)}
        return {"state": PASSED, "words": f"{proto} FULL on both ends"}
    still = [f"{h} {port} still has {other}" for h, (port, other, _pe, mine) in found.items()
             if mine]
    if still:
        return {"state": FAILED, "words": f"{proto}: " + "; ".join(still)}
    return {"state": PASSED, "words": f"{proto} adjacency gone on both ends, as intended"}


def verify_link(link: dict, devices: dict, checks: list, *, list_name: str,
                before: dict = None) -> dict:
    """The link's verify (``link_verify``): each check polled within its settle window until it
    passes (`convergence.wait_for`), both ends read each time. ``{"state", "checks": [{"family",
    "state", "words", "elapsed"}], "words"}``: FAILED if any check failed, else UNREADABLE if any
    could not be read, else NOT_JUDGED if any was not judged, else PASSED."""
    from modules.nsot import convergence

    out = []
    for check in checks:
        latest = {}

        def probe(_c=check):
            got = {host: _end_read(_c["family"], devices.get(host) or {}, port)
                   for host, port in ends(link)}
            latest["verdict"] = _judge(_c, link, got, before)
            return latest["verdict"]

        first = probe()
        if first["state"] in (PASSED, NOT_JUDGED):
            out.append(dict(first, family=check["family"], elapsed=0.0))
            continue
        result = convergence.wait_for(WINDOW[check["family"]], probe,
                                      lambda v: v["state"] in (PASSED, NOT_JUDGED),
                                      sleep=SLEEP or time.sleep, list_name=list_name)
        verdict = latest.get("verdict") or first
        if result.get("error") and verdict["state"] != PASSED:
            verdict = {"state": UNREADABLE, "words": f"not read: {result['error']}"}
        out.append(dict(verdict, family=check["family"], elapsed=result.get("elapsed", 0.0)))
    states = [c["state"] for c in out]
    state = next((s for s in (FAILED, UNREADABLE, NOT_JUDGED) if s in states), PASSED)
    return {"state": state, "checks": out,
            "words": STATE_WORDS[state] + ": " + "; ".join(
                f"{CHECK_WORDS[c['family']]}: {c['words']}" for c in out)}


# ── the pair settled: rollback, save, the record ───────────────────────────────────

def _repo(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _close(ctx) -> None:
    from modules.connection import close_persistent_connection
    for ip in list(ctx.connections_pool):
        close_persistent_connection(ip, ctx.connections_pool, ctx.pool_lock)


def _roll_back(list_name: str, host: str, result: dict, ctx, reason: str) -> None:
    """Roll back an end whose own run passed (``paired_rollback``), and say what it achieved on
    its result, as `_deploy_one` says it for a run that rolled back by itself."""
    from modules import pipeline
    from modules.nsot.deploy import FAILED as FAILED_OUTCOME
    from modules.nsot.repo import clear_post_deploy_staging

    result.update(outcome=FAILED_OUTCOME, stage="pair", reason=reason, golden_pending=[])
    if ctx is None:
        # Nothing was sent to it (its intent was already on it): nothing to undo.
        result.update(rolled_back=False, rollback_outcome={
            "state": "nothing_to_undo", "remaining": [],
            "detail": "nothing was sent to it, so there was nothing to undo"})
        return
    try:
        pipeline.roll_back_after(ctx, reason)
    finally:
        _close(ctx)
    ip = (ctx.selected_devices[0] or {}).get("ip", "") if ctx.selected_devices else ""
    result.update(
        rolled_back=ctx.rollback_performed,
        rollback_outcome=dict(ctx.rollback_outcome.get(ip) or {}),
        rollback_commands=list(ctx.rollback_commands.get(ip) or []),
        rollback_failures=dict(ctx.rollback_failures or {}),
        rollback_not_undone=list(ctx.rollback_not_undone.get(ip) or []),
        rollback_dangerous_exempt=list(ctx.rollback_dangerous.get(ip) or []),
        failure_state=list(ctx.failure_state.values()),
        device_changed=any(e.get("device_changed") for e in ctx.failure_state.values()))
    # Its capture after the push was parked for the batch's commit (stage 8.5); the device is
    # back, so the capture is not its golden.
    try:
        clear_post_deploy_staging(_repo(list_name), [host])
    except Exception as exc:                            # noqa: BLE001 (a parked capture)
        log.warning("paired deploy: %s's parked capture was not cleared (%s)", host, exc)


def _note_unsent(list_name: str, host: str, program: list, reason: str, run_id: str) -> None:
    """An end never sent, because its pair failed: its intent marked rolled back as a rolled-back
    end's is (`hostvars.record_rolled_back`, keyed on the program), so its half of the link
    change is never offered alone; Revert and Retry lift it as they lift any."""
    from modules.nsot import hostvars

    if not program:
        return
    try:
        repo = _repo(list_name)
        commits = hostvars.intent_commits(repo, host, limit=1)
        hostvars.record_rolled_back(repo, host, commits[0]["sha"] if commits else "",
                                    reason=reason, pipeline_id=run_id, commands=list(program))
    except Exception as exc:                            # noqa: BLE001 (logged, as the pipeline's)
        log.error("paired deploy: could not mark %s's intent rolled back: %s", host, exc)


def refold(report: dict) -> dict:
    """The report's totals derived again from its rows (as `routes.deploy._merge_refusals`
    does), after the pair changed outcomes."""
    by_outcome = {}
    for r in report.get("results") or []:
        by_outcome.setdefault(r["outcome"], []).append(r["device"])
    report.update(by_outcome=by_outcome, deployed=by_outcome.get("deployed", []),
                  total=len(report.get("results") or []))
    return report


def breaker():
    """The batch's circuit breaker for a pair (``second_end``): the second end is sent only
    when the first DEPLOYED. Any other outcome stops it, a device found drifted at apply too,
    which a batch's breaker lets the rest carry on past (it changed nothing)."""
    from modules.nsot.deploy import DEPLOYED, CircuitBreaker

    class _Pair(CircuitBreaker):
        def counts(self, outcome: dict) -> bool:
            return outcome.get("outcome") != DEPLOYED

        def reason(self) -> str:
            return f"not attempted: its far end {self.tripped_after} did not deploy"

    return _Pair(limit=1)


def refused_both(link: dict, refused: list) -> list:
    """``both_or_neither``: *refused* (rows refused at apply, before anything was sent) with the
    other end refused beside it, naming why; each end once."""
    named = {r["device"]: r for r in refused}
    out = list(refused)
    for host, _port in ends(link):
        if host not in named:
            why = "; ".join(f"{r['device']}: {r.get('reason', '')}" for r in refused)
            out.append({"device": host, "outcome": "refused", "reason": (
                f"not sent: its far end was refused at apply ({why}); both ends of the link "
                f"{link_words(link)} change together, or neither does. Nothing was sent.")})
    return out


def settle(report: dict, link: dict, order: list, *, contexts: dict, devices: dict,
           programs: dict, checks: list, before: dict, list_name: str, run_id: str) -> dict:
    """After both ends' pipelines (``first_end``, ``second_end``): the link verified when both
    deployed (``link_verify``), both rolled back when either end or the link failed
    (``paired_rollback``), both saved when nothing failed (``save_both``), and ``pair`` put on
    each result and on the report for the record. Mutates and returns *report*."""
    from modules import pipeline
    from modules.nsot.deploy import DEPLOYED, UNATTEMPTED

    results = {r["device"]: r for r in report.get("results") or []}
    words = link_words(link)
    failed = next((h for h in order if (results.get(h) or {}).get("outcome") != DEPLOYED), "")
    verdict = {"state": NOT_REACHED, "checks": [], "words": STATE_WORDS[NOT_REACHED]}
    reason = ""
    if all((results.get(h) or {}).get("outcome") == "refused" for h in order):
        # Both or neither, before anything was sent (`refused_both`): nothing to roll back.
        verdict = dict(verdict, words="the link was not verified: both ends were refused at "
                                      "apply, and nothing was sent")
    elif failed:
        r = results.get(failed) or {}
        reason = (f"its far end {failed} did not deploy ("
                  + (f"{r.get('stage')}: " if r.get("stage") else "")
                  + f"{r.get('reason') or r.get('outcome', '')}), so both ends of the link "
                  f"{words} were rolled back")
    else:
        verdict = verify_link(link, devices, checks, list_name=list_name, before=before)
        if verdict["state"] == FAILED:
            reason = (f"the link's verify failed ({verdict['words']}), so both ends of the "
                      f"link {words} were rolled back")
    rolled = []
    for host in reversed(order):
        r = results.get(host)
        if r is None:
            continue
        if reason and r.get("outcome") == DEPLOYED:
            _roll_back(list_name, host, r, contexts.get(host), reason)
            rolled.append(host)
        elif reason and r.get("outcome") == UNATTEMPTED:
            r["reason"] = (f"not sent: {failed} did not deploy, and both ends of the link "
                           f"{words} change together or neither does")
            _note_unsent(list_name, host, programs.get(host) or [], r["reason"], run_id)
        elif not reason and r.get("outcome") == DEPLOYED and contexts.get(host) is not None:
            ctx = contexts[host]
            try:
                saved = pipeline.save_held(ctx)
            finally:
                _close(ctx)
            ip = (ctx.selected_devices[0] or {}).get("ip", "") if ctx.selected_devices else ""
            r["saved_startup"] = dict(saved.get(ip) or {})
            r["warnings"] = list(ctx.warnings)
    for i, host in enumerate(order):
        r = results.get(host)
        if r is None:
            continue
        r["pair"] = {"link": words, "end": i + 1, "verify": verdict["state"],
                     "verify_words": verdict["words"],
                     "rolled_back_for": reason if host in rolled else "",
                     "checks": [{"family": c["family"], "state": c["state"],
                                 "words": c["words"]} for c in verdict["checks"]]}
    report["pair"] = {"link": words, "link_text": link_text(link), "devices": list(order),
                      "verify": verdict, "rolled_back": sorted(rolled), "reason": reason}
    return refold(report)
