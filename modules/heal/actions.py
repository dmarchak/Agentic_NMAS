"""Action remediations: the four action kinds, their guards 13a to 13e, and how an action is
judged before anything is sent (board H's amendment, item 2, part H19; docs/HEAL_TO_INTENT.md
19.4). Deterministic; it reads no device and calls no model.

**Not heal to intent, and said so.** An action changes no configuration line (a bounce, a
clear), or proposes a change to intent (dampening). Each is named as an action wherever it is
drawn, under the same tiers, guards, lifecycle and records as a heal.

**The kinds** (`KINDS`, rows of section 5's tier table, `kinds.TIER`): the port bounce (Tier
1), the BGP session clear of one named neighbour (Tier 1 on a network marked lab, Tier 2
elsewhere: N16, `tier_of`), the OSPF adjacency reset, which is the port bounce on an interface
with exactly one OSPF neighbour (Tier 1), and the dampening proposal on a port still flapping
after its one bounce (Tier 2, a change to intent, a person's).

**Built, each by its own part** (`NOT_BUILT`, `BUILT`): H20 built the port bounce and the OSPF
adjacency reset through it (`modules/heal/bounce.py`: its program, its revert timer, guard
13c's CEF and only-path reads, 13f). H21 built the BGP session clear
(`modules/heal/session_clear.py`: the hard clear of one named neighbour not Established in two
reads, the soft clear of an Established one, each a measured privileged operation,
`privileged.SESSION_CLEARS`, refused by name on a platform where it is not measured). H22
built the dampening proposal (`modules/heal/dampening.py`: raised after a bounce still
flapping or a second need, its intent commit and deploy under one hash as the approving
person, its Approve refused by name until its rollback's `interface.dampening` removal is
measured on the device's platform). A kind whose part has not landed (`NOT_BUILT`, none now)
is refused by name, "not built yet: <part>", never allowed by a policy
(`policy.actions_not_built`) and never offered; `judge` refuses it before any guard runs, so
nothing is read for it.

**The guards** (`GUARDS`, after section 6's guard 13, in this order; each answers None or a hit
naming the guard, both operands it compared and its outcome; one that cannot be read applies,
failing closed):
- **13a, the precondition read fresh, and again just before the send** (`g13a_fresh`): no
  longer holding is "the port came back by itself", and nothing is sent;
- **13b, the far end up and not held** (`g13b_far_end`): read on the far device; an operation
  holding it, or a person working on it (guard 7 on the far end), holds the action; an
  unmanaged far end cannot be read, so there is no action;
- **13c, never Mercury's path, never the only path** (`g13c_path`), each part Never (Tier 4):
  (1) the interface carrying the address Mercury reaches the device on, from committed intent,
  IPv4 and IPv6; (2) Mercury's route leaving out of the interface, by the device's own `show ip
  cef` toward Mercury's source address (`show ipv6 cef` for an IPv6 manager), an answer naming
  no egress refused too; (3) the device's only path, by the blast radius of its shutdown
  (`blast_radius.radius_of_shutdowns`, IPv4 intent only, so an unknown radius is refused,
  saying so). The reads and their words are the bounce's (`bounce.cef_refusal`,
  `radius_refusal`), which the act judges again on its own held session. For a hard session
  clear (`g13c_session`, H21): "a session whose loss would withdraw the manager's route is
  Never too", by the device's own route toward Mercury's source address (`show ip route`, or
  `show ipv6 route` for an IPv6 manager) learned by BGP from that neighbour, a BGP route whose
  source cannot be told refused too; a soft clear withdraws nothing, so it passes unread;
- **13d, once** (`g13d_once`): a port is bounced at most once an hour
  (``heal_bounce_per_port_hour``), and a second need within ``heal_repeat_halts_hours`` is the
  dampening proposal instead; a session is cleared once per incident, a second need being
  can't fix (Tier 3) with its diagnosis;
- **13e, a flap is measured, not felt** (`g13e_flap`): ``heal_flap_transitions`` UPDOWN
  transitions of one interface in ``heal_flap_minutes``, from the flap record the `logs-tail`
  reader's after-store step keeps (`modules/heal/flaps.py`); the stability window is the same
  minutes. The dampening proposal needs a measured flap; a bounce needs the record readable,
  since its verify reads the stability window from it.
"""

import logging
import re
import time

log =logging.getLogger(__name__)

KINDS = ("port_bounce", "session_clear", "ospf_reset", "dampening_proposal")
#: Each kind as a record, a notice and a screen name it: an action, never a heal.
KIND_WORDS = {
    "port_bounce": "a port bounce",
    "session_clear": "a BGP session clear of one named neighbour",
    "ospf_reset": "an OSPF adjacency reset (the port bounce on its one-neighbour interface)",
    "dampening_proposal": "a dampening proposal",
}
#: The kinds a session clear is Tier 1 for only on a network marked lab (N16).
LAB_ONLY_AUTO = ("session_clear",)
#: Each kind's operation not built yet, with the part that builds it and what it lacks. None
#: now: H22 built the dampening proposal (`modules/heal/dampening.py`), Tier 2 and
#: propose-only, its Approve refused by name on a platform where its rollback, Mode B's
#: `interface.dampening` removal, is not measured (C2416).
NOT_BUILT = {}
#: The kinds whose operation is built: the port bounce and the OSPF reset through it (H20), the
#: BGP session clear (H21), the dampening proposal (H22).
BUILT = tuple(k for k in KINDS if k not in NOT_BUILT)

#: The action guards after guard 13, in order: (id, name, the settings it reads, the kinds it
#: applies to). Guard 13's own row in `policy.GUARDS` names their settings.
GUARDS = (
    ("13a", "the precondition read fresh, and again just before the send", (),
     ("port_bounce", "session_clear", "ospf_reset", "dampening_proposal")),
    ("13b", "the far end up and not held", (), ("port_bounce", "ospf_reset")),
    ("13c", "never Mercury's path, never the only path", (),
     ("port_bounce", "ospf_reset", "session_clear")),
    ("13d", "once", ("heal_bounce_per_port_hour", "heal_repeat_halts_hours"),
     ("port_bounce", "session_clear", "ospf_reset")),
    ("13e", "a flap is measured, not felt", ("heal_flap_transitions", "heal_flap_minutes"),
     ("port_bounce", "ospf_reset", "dampening_proposal")),
)
#: The kinds that bounce a port (13c and 13d count them together: an OSPF reset is a bounce).
BOUNCES = ("port_bounce", "ospf_reset")


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def not_built(kind: str) -> str:
    """Why *kind* cannot run yet, naming the part that builds it, or "" once it is built."""
    if kind not in NOT_BUILT:
        return ""
    part, what = NOT_BUILT[kind]
    return f"not built yet: {part} ({what})"


def tier_of(kind: str, lab: bool) -> int:
    """*kind*'s tier on a network (`kinds.TIER`, a ceiling in code): a session clear is Auto
    only on a network marked lab, Propose elsewhere (N16)."""
    from modules.heal.kinds import TIER

    tier = TIER[kind]
    return 2 if kind in LAB_ONLY_AUTO and not lab else tier


def _name(gid: str) -> str:
    return next(name for g, name, _keys, _kinds in GUARDS if g == gid)


def hit(gid: str, outcome: str, words: str, operands: dict, *, until: float = None,
        tier: int = 0, instead: str = "") -> dict:
    """One guard that applied: *outcome* ``nothing`` (nothing to do: it resolved itself),
    ``held`` (checked again at *until*), ``cant_fix`` (nothing is sent; *tier* when the guard
    sets it: 4 for Never, 3 for can't fix) or ``instead`` (*instead* is the kind to judge in
    its place)."""
    return {"guard": gid, "name": _name(gid), "outcome": outcome, "words": words,
            "operands": operands, "until": until, "tier": tier, "instead": instead}


# ── 13a: the precondition, read fresh and again before the send ─────────────────────────────

def precondition(kind: str, facts) -> dict:
    """Whether *kind*'s precondition holds on a read's facts: ``{"holds", "words"}``, *holds*
    None when the facts are absent (unreadable). The facts, by kind:
    - a bounce: the near end's interface (`diagnose_parse`'s ``interfaces``: ``state`` down
      while administratively up);
    - an OSPF reset: ``{"neighbours": [...]}`` on the interface, exactly one, not FULL;
    - a session clear: the session's ``{"established", "state"}`` (hard: not Established;
      soft: Established);
    - the dampening proposal: the flap record's ``{"flapping"}``."""
    if not isinstance(facts, dict):
        return {"holds": None, "words": "it was not read"}
    if kind == "port_bounce":
        state = facts.get("state") or "unread"
        return {"holds": state == "down",
                "words": f"{facts.get('name') or 'the port'} is {state.replace('_', ' ')}"}
    if kind == "ospf_reset":
        rows = facts.get("neighbours")
        if not isinstance(rows, list):
            return {"holds": None, "words": "the interface's OSPF neighbours were not read"}
        stuck = [r for r in rows if (r.get("state") or "").upper() not in ("FULL", "2WAY")]
        return {"holds": len(rows) == 1 and len(stuck) == 1,
                "words": (f"{len(rows)} OSPF neighbour(s) on the interface, {len(stuck)} not "
                          "FULL")}
    if kind == "session_clear":
        if "established" not in facts:
            return {"holds": None, "words": "the session was not read"}
        soft = facts.get("variant") == "soft"
        est = bool(facts.get("established"))
        return {"holds": est if soft else not est,
                "words": f"the session is {facts.get('state') or ('Established' if est else '?')}"}
    if kind == "dampening_proposal":
        if "flapping" not in facts:
            return {"holds": None, "words": "the flap record was not read"}
        return {"holds": bool(facts["flapping"]), "words": facts.get("words") or ""}
    return {"holds": None, "words": f"{kind} is no action kind"}


def g13a_fresh(kind: str, decided: dict, again: dict):
    """*decided* and *again*: `precondition`'s answers on the read the decision was made on
    and the read just before the send. What was decided on is what is acted on (C78)."""
    ops = {"decided": decided.get("words") if decided else None,
           "again": again.get("words") if again else None}
    if not decided or decided.get("holds") is not True:
        return hit("13a", "cant_fix", ("the precondition did not hold on the read the decision "
                                       f"was made on ({ops['decided'] or 'not read'}), so "
                                       "nothing is sent"), ops)
    if not again or again.get("holds") is None:
        return hit("13a", "cant_fix", ("the precondition could not be read again before the "
                                       f"send ({ops['again'] or 'not read'}), so nothing is "
                                       "sent"), ops)
    if again["holds"] is False:
        # An OSPF reset's precondition is its adjacency, not its port (H20).
        came_back = ("the port came back by itself" if kind == "port_bounce" else
                     "it resolved by itself")
        return hit("13a", "nothing", (f"{came_back}: decided on {ops['decided']}, read again "
                                      f"{ops['again']}; nothing is sent"), ops)
    return None


# ── 13b: the far end up and not held ────────────────────────────────────────────────────────

def g13b_far_end(network: str, far: dict, now: float, *, changes: int, minutes: int,
                 holder=None, working=None):
    """*far* is the far end as read: ``{"device", "interface", "managed", "state", "read"}``
    (*state* the far interface's, ``up`` to pass). A bounce never fights an operation holding
    the far end, nor a person working on it: guard 7 applies to both ends (*working(network,
    device, now, minutes)* the outside changes' receive times there, `outside_changes_on`)."""
    from modules.nsot import device_ops

    far = far or {}
    dev, iface = far.get("device") or "", far.get("interface") or ""
    ops = {"far_device": dev, "far_interface": iface, "far_state": far.get("state"),
           "read": far.get("read") or ""}
    if not dev or not far.get("managed"):
        return hit("13b", "cant_fix", (f"the far end{' ' + dev if dev else ''} is not a managed "
                                       "device, so it cannot be read, and there is no action"),
                   ops, tier=3)
    if not far.get("state"):
        return hit("13b", "cant_fix", f"{dev} {iface} was not read, so the far end is not known "
                                      "up", ops, tier=3)
    if far["state"] != "up":
        return hit("13b", "cant_fix", (f"{dev} {iface} is {far['state'].replace('_', ' ')}, "
                                       "not up: both ends down is the link between them, which "
                                       "a bounce cannot fix"), ops, tier=3)
    try:
        h = (holder or device_ops.holder)(network, dev)
    except Exception as exc:                          # noqa: BLE001 (fails closed, said)
        return hit("13b", "held", f"what holds {dev} cannot be read ({exc})", ops,
                   until=now + 60)
    if h:
        return hit("13b", "held", (f"{dev}, the far end, is held by "
                                   f"{h.get('operation') or 'an operation'} of "
                                   f"{h.get('actor') or 'an unrecorded actor'}: a bounce never "
                                   "fights an operation on the far end; checked again in a "
                                   "minute"), dict(ops, operation=h.get("operation")),
                   until=now + 60)
    window = float(minutes) * 60
    try:
        seen = (working or outside_changes_on)(network, dev, now, minutes)
    except Exception as exc:                          # noqa: BLE001 (fails closed, said)
        return hit("13b", "held", (f"whether a person is working on {dev} cannot be read "
                                   f"({exc})"), ops, until=now + 60)
    recent = [t for t in seen if now - window <= t <= now]
    if len(recent) >= int(changes):
        return hit("13b", "held", (f"a person appears to be working on {dev}, the far end: "
                                   f"{len(recent)} changes from outside Mercury in {int(minutes)} "
                                   f"minutes (at least {int(changes)} holds it)"),
                   dict(ops, changes=len(recent), heal_person_working_changes=int(changes),
                        heal_person_working_minutes=int(minutes)),
                   until=max(recent) + window)
    return None


def outside_changes_on(network: str, device: str, now: float, minutes: int) -> list:
    """The receive times of the outside configuration changes on *device* that its open
    incidents hold (`detect.outside_changes`): what guard 7 counts, for the far end."""
    from modules.heal import incidents
    from modules.heal.detect import outside_changes

    out = []
    for inc in incidents.read(network)["incidents"]:
        if inc.get("device") == device and inc.get("state") in incidents.OPEN_STATES:
            out += outside_changes(dict(inc, defer_until=None))
    return sorted(out)


# ── 13c: never Mercury's path, never the only path ──────────────────────────────────────────

def _carries(iface: dict, address: str) -> bool:
    """Whether intent's *iface* holds *address*, IPv4 (``a.b.c.d mask`` or a prefix) or IPv6."""
    import ipaddress

    try:
        want = ipaddress.ip_address(str(address).split("%", 1)[0])
    except ValueError:
        return False
    raw = [(iface.get("ipv4") or "").strip()] + [str(a) for a in iface.get("ipv6") or []]
    for r in raw:
        if not r:
            continue
        try:
            if ipaddress.ip_interface(r.split()[0] if ":" in r else r.replace(" ", "/")).ip \
                    == want:
                return True
        except ValueError:
            continue
    return False


def g13c_path(device: str, interface: str, *, mgmt_ip: str, intent: dict, cef: dict = None,
              intents: dict = None, nets: list = None):
    """13c, each part Never (Tier 4): (1) *interface* carries *mgmt_ip*, the address Mercury
    reaches *device* on, by committed intent (*intent*, the device's host_vars), IPv4 or IPv6;
    (2) *cef* (``{"manager", "command", "answer"}``, the device's own route toward Mercury's
    source address, *answer* None when it was not read) names *interface* as its egress, or
    names none that can be read; (3) *interface* is the device's only path, by the blast radius
    of its shutdown over *intents* (every device's committed host_vars) and *nets* (this host's
    networks). A part not read applies."""
    from modules.heal import bounce

    ops = {"device": device, "interface": interface, "management_address": mgmt_ip}
    if not mgmt_ip:
        return hit("13c", "cant_fix", (f"the address Mercury reaches {device} on is not known, "
                                       "so whether a bounce cuts it cannot be told"), ops, tier=4)
    want = (interface or "").strip().lower()
    mine = next((i for i in (intent or {}).get("interfaces") or []
                 if (i.get("name") or "").strip().lower() == want), None)
    if mine is None:
        return hit("13c", "cant_fix", (f"committed intent holds no {interface} on {device}, so "
                                       f"whether it carries {mgmt_ip} cannot be told"), ops,
                   tier=4)
    if _carries(mine, mgmt_ip):
        return hit("13c", "cant_fix", (f"Not bounced: {interface} carries {mgmt_ip}, the address "
                                       f"Mercury reaches {device} on (committed intent), so a "
                                       f"bounce would cut Mercury's own session to {device}"),
                   ops, tier=4)
    cef = cef or {}
    ops = dict(ops, manager=cef.get("manager") or "", cef_command=cef.get("command") or "")
    if cef.get("answer") is None:
        return hit("13c", "cant_fix", (f"Not bounced: {device}'s route to Mercury was not read "
                                       f"({cef.get('why') or 'not asked'}), so whether "
                                       f"{interface} carries it cannot be told"), ops, tier=4)
    why = bounce.cef_refusal(device, cef.get("manager") or "", interface,
                             cef.get("command") or "", cef["answer"])
    if why:
        return hit("13c", "cant_fix", f"Not bounced: {why}", ops, tier=4)
    if intents is None or nets is None:
        return hit("13c", "cant_fix", (f"Not bounced: the blast radius of shutting {interface} "
                                       "was not read, so whether it is the device's only path "
                                       "cannot be told"), ops, tier=4)
    why = bounce.radius_refusal(intents, nets, device, interface)
    if why:
        return hit("13c", "cant_fix", f"Not bounced: {why}", dict(ops, networks=list(nets)),
                   tier=4)
    return None


def route_command(manager: str) -> str:
    """The device's own route toward Mercury's *manager* address, IPv4 or IPv6."""
    import ipaddress

    return (f"show ipv6 route {manager}"
            if ipaddress.ip_address(str(manager).split("%", 1)[0]).version == 6
            else f"show ip route {manager}")


def g13c_session(device: str, peer: str, variant: str, *, route: dict = None):
    """13c for a session clear (H21): "a session whose loss would withdraw the manager's route
    is Never too". *route* (``{"manager", "command", "answer"}``, *answer* None when it was not
    read) is the device's own route toward Mercury's source address. A route learned by BGP
    from *peer*, or by BGP from a source the answer does not name, is Never (Tier 4); a route
    not learned by BGP, or none in the table (Mercury's session is not routed by it), passes.
    A soft clear resets nothing, so it withdraws nothing, and passes unread."""
    import ipaddress

    if variant == "soft":
        return None
    route = route or {}
    ops = {"device": device, "peer": peer, "manager": route.get("manager") or "",
           "route_command": route.get("command") or ""}
    if not route.get("manager"):
        return hit("13c", "cant_fix", (f"Not cleared: the address Mercury reaches {device} from "
                                       f"is not known ({route.get('why') or 'not read'}), so "
                                       f"whether {device}'s route to Mercury is learned from "
                                       f"{peer} cannot be told"), ops, tier=4)
    answer = route.get("answer")
    if answer is None:
        return hit("13c", "cant_fix", (f"Not cleared: {device}'s route to Mercury "
                                       f"({route['manager']}) was not read "
                                       f"({route.get('why') or 'not asked'}), so whether a "
                                       f"clear of {peer} withdraws it cannot be told"), ops,
                   tier=4)
    text = answer or ""
    if re.search(r"not in table|Route not found|No route", text, re.I) or not text.strip():
        return None
    if not re.search(r'Known via "bgp|^\s*B[ *]', text, re.M):
        return None
    try:
        want = ipaddress.ip_address(peer)
    except ValueError:
        want = None
    named = set()
    for tok in re.findall(r"[0-9A-Fa-f:.]{3,45}", text):
        try:
            named.add(ipaddress.ip_address(tok.strip(".,")))
        except ValueError:
            continue
    sources = set()
    for tok in re.findall(r"\b[Ff]rom ([0-9A-Fa-f:.]{3,45})", text):
        try:
            sources.add(ipaddress.ip_address(tok.strip(".,")))
        except ValueError:
            continue
    if want is not None and want in named:
        return hit("13c", "cant_fix", (f"Not cleared: {device} reaches Mercury "
                                       f"({route['manager']}) by a route learned by BGP from "
                                       f"{peer} (`{route['command']}` on {device}), so a hard "
                                       f"clear would withdraw Mercury's own route to {device}"),
                   ops, tier=4)
    if sources:
        return None
    return hit("13c", "cant_fix", (f"Not cleared: {device} reaches Mercury ({route['manager']}) "
                                   f"by a route learned by BGP (`{route['command']}` on "
                                   f"{device}) whose source the answer does not name, so a hard "
                                   f"clear of {peer} could withdraw it"), ops, tier=4)


# ── 13d: once ───────────────────────────────────────────────────────────────────────────────

def history(network: str, outcome: str) -> list:
    """Each action recorded on *network* with *outcome* (``heal`` in AUTO, ``would_heal`` in
    dry run, as guards 9 to 11 count): ``[{"id", "kind", "device", "interface", "peer",
    "incident", "epoch", "at"}]`` from the decisions store, whose action rows carry
    ``action`` (``{"kind", "device", "interface", "peer"}``; H20 to H22 write them)."""
    from modules.heal import decisions

    return history_of(decisions.decisions(network), outcome)


def history_of(rows: list, outcome: str) -> list:
    """`history` on decision rows already read (`decisions.decisions`'), a read of none."""
    out = []
    for d in rows:
        a = d.get("action")
        if not isinstance(a, dict) or d.get("outcome") != outcome:
            continue
        out.append({"id": d.get("id"), "kind": a.get("kind"), "device": a.get("device"),
                    "interface": a.get("interface") or "", "peer": a.get("peer") or "",
                    "incident": d.get("incident") or "", "epoch": float(d.get("epoch") or 0),
                    "at": d.get("at") or ""})
    return out


def g13d_once(kind: str, rows: list, target: dict, now: float, *, per_hour: int,
              repeat_hours: int):
    """*rows*: `history`'s. *target*: ``{"device", "interface", "peer", "incident"}``."""
    dev = target.get("device") or ""
    if kind in BOUNCES:
        port = (target.get("interface") or "").lower()
        prior = [r for r in rows if r["kind"] in BOUNCES and r["device"] == dev
                 and r["interface"].lower() == port
                 and r["epoch"] >= now - float(repeat_hours) * 3600]
        ops = {"device": dev, "interface": target.get("interface"), "bounced": len(prior),
               "heal_bounce_per_port_hour": int(per_hour),
               "heal_repeat_halts_hours": int(repeat_hours)}
        if prior:
            last = max(prior, key=lambda r: r["epoch"])
            return hit("13d", "instead", (f"{dev} {target.get('interface')} was bounced at "
                                          f"{last['at'] or _iso(last['epoch'])}, within "
                                          f"{int(repeat_hours)} h: a second need is the "
                                          "dampening proposal, never a second bounce"),
                       dict(ops, previous=last["id"]), instead="dampening_proposal")
        if int(per_hour) < 1:
            return hit("13d", "cant_fix", (f"the policy bounces no port (bounces per port an "
                                           f"hour: {int(per_hour)})"), ops, tier=3)
        return None
    if kind == "session_clear":
        peer = target.get("peer") or ""
        prior = [r for r in rows if r["kind"] == "session_clear" and r["device"] == dev
                 and r["peer"] == peer and r["incident"] == (target.get("incident") or "")]
        if prior:
            return hit("13d", "cant_fix", (f"{dev}'s session to {peer} was cleared once in this "
                                           f"incident ({prior[-1]['at']}): a second need is "
                                           "can't fix, with its diagnosis"),
                       {"device": dev, "peer": peer, "incident": target.get("incident"),
                        "previous": prior[-1]["id"]}, tier=3)
    return None


# ── 13e: a flap is measured ─────────────────────────────────────────────────────────────────

def g13e_flap(kind: str, flap: dict):
    """*flap*: `flaps.flapping`'s answer for the target interface."""
    flap = flap or {}
    ops = {k: flap.get(k) for k in ("device", "interface", "transitions", "at_least",
                                    "minutes", "state")}
    if flap.get("state") != "read":
        said = flap.get("words") or "not read"
        return hit("13e", "cant_fix", (f"the flap record cannot be read ({said}), so the flap "
                                       "and the stability window cannot be measured"), ops)
    if kind == "dampening_proposal" and not flap.get("flapping"):
        return hit("13e", "nothing", (f"not flapping: {flap.get('words')}; dampening is "
                                      "proposed only for a measured flap"), ops)
    return None


# ── The judgement ───────────────────────────────────────────────────────────────────────────

def judge(kind: str, facts: dict, *, built=None) -> dict:
    """*kind* judged by its guards in order, after the built check: ``{"kind", "outcome",
    "guard", "words", "steps", "tier", "instead"}``, *outcome* ``pass`` when every guard that
    applies to it passed (H20 to H22 then act), or the first hit's. *facts* hold each guard's
    answer by its id (``13a`` to ``13e``), its function's hit or None, computed by the caller
    on its own reads; a guard that applies and is absent applies. *built*: the built kinds
    (`BUILT`)."""
    built = BUILT if built is None else tuple(built)
    steps = []
    if kind not in KINDS:
        return {"kind": kind, "outcome": "cant_fix", "guard": None, "tier": 4, "instead": "",
                "words": f"{kind!r} is no action kind ({', '.join(KINDS)})", "steps": steps}
    if kind not in built:
        why = not_built(kind) or "not built yet"
        steps.append({"step": "built", "result": "refused", "words": why})
        return {"kind": kind, "outcome": "cant_fix", "guard": None, "tier": 0, "instead": "",
                "words": f"{KIND_WORDS[kind]}: {why}", "steps": steps}
    steps.append({"step": "built", "result": "ok", "words": f"{KIND_WORDS[kind]} is built"})
    for gid, name, _keys, applies in GUARDS:
        if kind not in applies:
            continue
        if gid not in facts:
            g = hit(gid, "cant_fix", f"guard {gid} ({name}) was not judged, and a guard that "
                                     "was not judged applies", {})
        else:
            g = facts[gid]
        if g:
            steps.append({"step": gid, "result": g["outcome"], "words": g["words"]})
            return {"kind": kind, "outcome": g["outcome"],
                    "guard": {k: g[k] for k in ("guard", "name", "words", "operands")},
                    "tier": g.get("tier") or 0, "instead": g.get("instead") or "",
                    "words": f"guard {gid}, {name}: {g['words']}", "steps": steps}
        steps.append({"step": gid, "result": "ok", "words": f"{name}: passed"})
    return {"kind": kind, "outcome": "pass", "guard": None, "tier": 0, "instead": "",
            "words": f"{KIND_WORDS[kind]}: every guard passed", "steps": steps}
