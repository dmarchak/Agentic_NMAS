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

**None is built yet** (`NOT_BUILT`): each kind's operation is its own part, H20 (the bounce, its
revert timer, guard 13c's CEF and only-path checks, and the OSPF reset through it), H21 (the
BGP clears, measured on devices) and H22 (the dampening field and its proposal). Until its part
lands a kind is refused by name, "not built yet: H20", never allowed by a policy
(`policy.actions_not_built`) and never offered. `judge` refuses it before any guard runs, so
nothing is read for it.

**The guards** (`GUARDS`, after section 6's guard 13, in this order; each answers None or a hit
naming the guard, both operands it compared and its outcome; one that cannot be read applies,
failing closed):
- **13a, the precondition read fresh, and again just before the send** (`g13a_fresh`): no
  longer holding is "the port came back by itself", and nothing is sent;
- **13b, the far end up and not held** (`g13b_far_end`): read on the far device; an operation
  holding it, or a person working on it (guard 7 on the far end), holds the action; an
  unmanaged far end cannot be read, so there is no action;
- **13c, never Mercury's path, never the only path** (`g13c_path`): H19 builds its first part,
  the interface carrying the address Mercury reaches the device on, from committed intent,
  IPv4 and IPv6 (Never, Tier 4). Its second and third, Mercury's route leaving out of the
  interface (`show ip cef`, `show ipv6 cef`) and the device's only path (the blast radius of
  its shutdown), are H20's, read with the bounce: until then the guard applies, naming them;
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
import time

log = logging.getLogger(__name__)

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
#: Each kind's operation not built yet, with the part that builds it and what it lacks.
NOT_BUILT = {
    "port_bounce": ("H20", "the bounce's program, its revert timer and guard 13c's CEF and "
                           "only-path reads"),
    "ospf_reset": ("H20", "the port bounce it runs through, and its one-neighbour read"),
    "session_clear": ("H21", "the clears, measured on devices"),
    "dampening_proposal": ("H22", "intent's dampening field and its measured shape"),
}
#: The kinds whose operation is built: none, until H20 to H22.
BUILT = tuple(k for k in KINDS if k not in NOT_BUILT)

#: The action guards after guard 13, in order: (id, name, the settings it reads, the kinds it
#: applies to). Guard 13's own row in `policy.GUARDS` names their settings.
GUARDS = (
    ("13a", "the precondition read fresh, and again just before the send", (),
     ("port_bounce", "session_clear", "ospf_reset", "dampening_proposal")),
    ("13b", "the far end up and not held", (), ("port_bounce", "ospf_reset")),
    ("13c", "never Mercury's path, never the only path", (), ("port_bounce", "ospf_reset")),
    ("13d", "once", ("heal_bounce_per_port_hour", "heal_repeat_halts_hours"),
     ("port_bounce", "session_clear", "ospf_reset")),
    ("13e", "a flap is measured, not felt", ("heal_flap_transitions", "heal_flap_minutes"),
     ("port_bounce", "ospf_reset", "dampening_proposal")),
)
#: The kinds that bounce a port (13c and 13d count them together: an OSPF reset is a bounce).
BOUNCES = ("port_bounce", "ospf_reset")
#: 13c's parts H20 builds with the bounce.
PATH_NOT_BUILT = ("Mercury's route to its address leaving out of the interface (`show ip cef`, "
                  "and `show ipv6 cef` for an IPv6 manager)",
                  "the device's only path (the blast radius of the interface's shutdown)")


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
        came_back = ("the port came back by itself" if kind in BOUNCES else
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


def g13c_path(device: str, interface: str, *, mgmt_ip: str, intent: dict):
    """13c's first part: *interface* carries *mgmt_ip*, the address Mercury reaches *device*
    on, by committed intent (*intent*, the device's host_vars), IPv4 or IPv6: Never. Its other
    two parts are H20's (`PATH_NOT_BUILT`): until they are read the guard applies, naming
    them, so no bounce passes it."""
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
    return hit("13c", "cant_fix", ("Not bounced: " + " and ".join(PATH_NOT_BUILT)
                                   + f" are not read yet: {not_built('port_bounce')}"),
               dict(ops, not_read=list(PATH_NOT_BUILT)), tier=4)


# ── 13d: once ───────────────────────────────────────────────────────────────────────────────

def history(network: str, outcome: str) -> list:
    """Each action recorded on *network* with *outcome* (``heal`` in AUTO, ``would_heal`` in
    dry run, as guards 9 to 11 count): ``[{"id", "kind", "device", "interface", "peer",
    "incident", "epoch", "at"}]`` from the decisions store, whose action rows carry
    ``action`` (``{"kind", "device", "interface", "peer"}``; H20 to H22 write them)."""
    from modules.heal import decisions

    out = []
    for d in decisions.decisions(network):
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
