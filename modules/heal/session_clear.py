"""The BGP session clear (board H's amendment, item 2, part H21; docs/HEAL_TO_INTENT.md 19.4 and
N16): an action, never a heal. It changes no configuration line.

**One home** (CLAUDE.md, "One owner per piece of state; one home per action"): the command
policy for a clear (which session may be cleared, how, and with what), its prompt and its
verify are `privileged.SESSION_CLEARS`' (`clear_plan`, `send_clear`, `clear_record`), the
platform measurement is `privileged_measured.json`'s, and the probe that measures it is
`scripts/nmas-tier2-probe`'s (steps ``bgp-soft`` and ``bgp-hard``). This module is the
decision and the act self-healing runs on them.

**The two variants** (`diagnose.ACTIONS`): a **hard clear** of one named neighbour intent holds,
not Established in two reads in a row (the diagnosis's read, then the decision's fresh one),
its last reset no configuration cause and the neighbour not shut; a **soft clear** (a route
refresh) of an Established session receiving fewer routes than intent expects. The soft
clear's diagnosis rule is not built (`diagnose.ACTION_RULES_NOT_BUILT`: intent holds no
expected route count), so nothing chooses it yet; its operation is built and measured.

**The tier** (N16, `actions.tier_of`): Tier 1 on a network marked lab, so AUTO with the kind
allowed clears and dry run records "would have cleared"; Tier 2 elsewhere, a **proposal** a
verified person approves with a reason (`propose.approve`, the same Approve… as any proposal),
whose act runs here as that person. No policy names the kind by default.

**The decision** (`consider`, `DECIDE_STEPS`): guards 1 to 3 (the kill switch, the mode, a halt,
planned work), 9 and 10 (the rates), the fresh read of the neighbour through the reads engine
(``show ip bgp neighbors <peer>``, ``show bgp ipv6 unicast neighbors <peer>`` for an IPv6
neighbour) and of the device's route toward Mercury, guards 13a (the precondition again), 13c
(a hard clear never withdraws Mercury's own route: `actions.g13c_session`) and 13d (once per
neighbour per incident), then `privileged.clear_plan`: intent's neighbour, never typed and
never ``*``; the two reads; no clear for Idle (Admin), a shut neighbour or a bad peer AS; the
clear measured on the device's platform, or refused by name.

**The act** (`apply` as the policy; `apply_approved` as the approving person; `STEPS`):
1. ``take``, once (`act.run`, or `propose.approve`);
2. ``stops`` again: the policy's (`act._stops`: AUTO, the network marked lab, the policy's
   fingerprint, the kind allowed, no halt, no planned work) or the proposal's
   (`propose._stops`);
3. ``plan`` again on the decision's reads, refused unless its hash is the decision's;
4. ``hold`` the device (one operation per device, `device_ops`);
5. ``route``: on the held session, the device's route toward Mercury read again (13c);
6. ``window``: the planned window recorded BEFORE anything is sent (CLAUDE.md's rule; C2702),
   naming the neighbour's interface, its length the clear's verify bound and a margin; a window
   that cannot be recorded sends nothing;
7. ``send``: the step log's ``started`` row first, then `privileged.send_clear`: the session
   read again and kept (13a, just before the send: a hard clear is never sent to a session
   Established now), the command once, the measured prompt alone answered;
8. ``verify``: the session Established within about 2.5 times its measured settle time (a soft
   clear: still Established, no connection dropped, the refresh sent);
9. ``record``: the Tier 2 record (`privileged.clear_record`; History's privileged commands),
   `decisions.applied` (a halt, guard 14, when a soft clear reset its session), the step log's
   ``act`` row (History) and the announcement.

Rollback does not apply, and the preview and record say why (`privileged`'s rule): a session
that was not Established had nothing to lose, and a route refresh resets nothing.

**What it ends with** (`OUTCOMES`): ``cleared`` (verified); ``not_back`` (sent, the session not
Established within the bound); ``reset`` (a soft clear dropped its session: it halts);
``unverified`` (the read after not recognised); ``rejected`` (the device refused the command:
nothing was cleared); ``refused`` (nothing sent). H23 draws each as a Needs attention row.
"""

import logging
import time

log = logging.getLogger(__name__)

KINDS = ("session_clear",)
#: Each variant's operation (`privileged.SESSION_CLEARS`).
VARIANT_KEY = {"hard": "clear-bgp-peer", "soft": "clear-bgp-soft"}
VIA = "heal-clear"
#: The clear's hold (`device_ops.OPERATION_WORDS`).
OPERATION = "session clear"
ACTOR = "Mercury (self-healing)"
READS_BY = "heal"
ANNOUNCER = "heal-act"
#: The planned window runs this long past the clear's verify bound: the read after, and the
#: neighbour's own view of the reset (its hold time is the far end's).
WINDOW_MARGIN_S = 60

#: The decision's steps, in order (`consider`), for the manual's How it works page.
DECIDE_STEPS = (("choose", "Choose the clear from the diagnosis's first hypothesis"),
                ("stops", "Check the kill switch, the mode, a halt and planned work"),
                ("rates", "Check the rates per device and per network"),
                ("fresh", "Read the neighbour again, and the device's route to Mercury"),
                ("guards", "Judge guards 13a, 13c and 13d, and the clear's own plan"),
                ("decide", "Decide: clear, would clear, propose or can't fix"),
                ("record", "Record the decision"))
#: The act's steps, in order (`apply`, `apply_approved`).
STEPS = (("take", "Take the decision, once"),
         ("stops", "Check the kill switch, the mode, the stage, the policy and planned work"),
         ("plan", "Plan the clear again and compare its hash"),
         ("hold", "Hold the device for the clear"),
         ("route", "Read the device's route to Mercury again"),
         ("window", "Record the clear's planned window, before anything is sent"),
         ("send", "Read the session again, then send the clear once"),
         ("verify", "Verify: the session Established within its measured bound"),
         ("record", "Record the outcome"))
OUTCOMES = ("cleared", "not_back", "reset", "unverified", "rejected", "refused")
OUTCOME_WORDS = {"cleared": "cleared; configuration unchanged",
                 "not_back": "cleared; the session did not come back",
                 "reset": "a soft clear reset the session",
                 "unverified": "cleared; the session's state after could not be read",
                 "rejected": "the device refused the clear; nothing was cleared",
                 "refused": "nothing was sent"}
#: The outcomes that halt the network (guard 14): a soft clear that reset its session did what
#: the measurement says it does not.
HALTS = ("reset",)
#: `privileged.send_clear`'s states, as the act's outcomes.
_OUTCOME_OF = {"done": "cleared", "not_back": "not_back", "reset": "reset",
               "unverified": "unverified", "rejected": "rejected", "refused": "refused"}


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def reads_for(peer: str) -> dict:
    """The neighbour's read for *peer*'s family (`privileged.SESSION_CLEARS`' one text)."""
    from modules.nsot import privileged

    fam = privileged.family_of(peer) or "ipv4"
    return {"family": fam,
            "session": privileged.SESSION_CLEARS["clear-bgp-peer"]["read"][fam].format(
                peer=peer)}


def policy_reason(network: str, variant: str, peer: str, policy: dict) -> str:
    """The policy's reason for a clear, in its Tier 2 record (as a person's reason is)."""
    return (f"self-healing on {network}: a {variant} clear of BGP neighbour {peer}, one named "
            f"neighbour, under the policy {policy.get('fingerprint')} confirmed by "
            f"{policy.get('by')} ({policy.get('reason') or 'no reason recorded'})")


def window_seconds(plan: dict) -> int:
    """The clear's planned window: its verify bound and `WINDOW_MARGIN_S`."""
    return int(plan.get("bound_s") or 0) + WINDOW_MARGIN_S


# ── Where it reads ──────────────────────────────────────────────────────────────────────────

class Sources:
    """Where the decision and the act read, each replaceable in a test. The decision's reads
    run through THE reads engine (`reads.run`, the allowlist whole); the act's on its own held
    session (`session`)."""

    def __init__(self, network: str, *, clock=time.time, sleep=time.sleep):
        self.network, self.clock, self.sleep = network, clock, sleep

    def mode(self, now):
        from modules.heal import policy

        return policy.current(self.network, now)

    def halted(self):
        from modules.heal import decisions

        return decisions.halted(self.network)

    def planned(self, device, now):
        from modules.heal import guards

        return guards.g3_planned(self.network, device, now)

    def decisions(self):
        from modules.heal import decisions

        return decisions.decisions(self.network)

    def device(self, host):
        from modules import device_page
        from modules.nsot import listref

        _ref, dev = device_page.find_device(host, listref.resolve(self.network))
        return dev or {}

    def intents(self):
        """``(intents, error)``, intents None when committed intent cannot be read whole
        (`bounce.committed_intents_of`, the one reader a window's far ends come from), so a
        hard clear's window refuses rather than naming no far end (C2795)."""
        from modules.heal.bounce import committed_intents_of

        return committed_intents_of(self.network)

    def manager_toward(self, address):
        from modules.heal import bounce

        return bounce.manager_toward(address)

    def read(self, host: str, commands: list) -> dict:
        """``{command: answer}`` for the commands answered, ``{"_why": why}`` when none was."""
        from modules.nsot import reads

        try:
            rec = reads.run(self.network, [host], commands, ACTOR, by=READS_BY,
                            purpose="self-healing: the session clear's fresh reads")
        except reads.Refused as exc:
            return {"_why": str(exc)}
        r = (rec.get("results") or {}).get(host) or {}
        got = {a["command"]: a.get("answer") or "" for a in r.get("answers") or []
               if a.get("state") == "answered"}
        return got or {"_why": r.get("why") or r.get("state") or "not read"}

    def session(self, dev: dict, work):
        """*work(conn)* on a new session to *dev* (`connection.with_temp_connection`)."""
        from modules.connection import with_temp_connection

        return with_temp_connection(dev, work)

    def values(self):
        from modules.redact import known_secret_values

        return known_secret_values()

    def window(self, network, device, interface, now, seconds, *, by, why, far_ends=()):
        from modules import restarts

        try:
            return restarts.record_planned([device], now, now + float(seconds), by, why, VIA,
                                           list_name=network,
                                           interfaces=[interface] if interface else [],
                                           far_ends=far_ends)
        except Exception as exc:                      # noqa: BLE001 (refused, said by the act)
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _intent_peers(hv: dict):
    from modules.neighbours import bgp_peers

    return [str(a) for a, _remote in bgp_peers(hv)] if isinstance(hv, dict) else None


def _dialect(hv: dict, dev: dict, device: str) -> tuple:
    from modules.heal import diagnose

    try:
        return diagnose.dialect_of(hv.get("platform") or dev.get("device_type") or "",
                                   device), ""
    except Exception as exc:                          # an unknown platform, named
        return "", str(exc)


# ── The decision (consider) ─────────────────────────────────────────────────────────────────

def consider(network: str, incident_id: str, diagnosis: dict, *, now: float = None,
             sources=None) -> dict:
    """The clear Mercury's diagnosis of an Alert incident chooses, judged and recorded:
    ``{"state", "decision", "words"}``, *state* ``none`` (no clear chosen, nothing recorded),
    ``recorded`` or ``failed``. Never raises."""
    from modules.heal import decisions, diagnose

    now = time.time() if now is None else float(now)
    pick = diagnose.action_for(diagnosis or {})
    if pick["state"] != "chosen" or pick["kind"] not in KINDS:
        return {"state": "none", "decision": None, "words": pick.get("words") or ""}
    src = sources or Sources(network)
    try:
        made = decide(network, incident_id, pick, now=now, sources=src)
        steps, phase = made.pop("steps", []), made.pop("phase", "decide")
        d = decisions.record(network, made, now)
    except Exception as exc:                          # said, never raised
        log.exception("heal: %s's session clear decision for %s failed", network, incident_id)
        return {"state": "failed", "decision": None,
                "words": f"the clear was not decided ({type(exc).__name__}: {exc})"}
    _log_decision(network, dict(d, steps=steps, phase=phase), now)
    _announce()
    return {"state": "recorded", "decision": d, "words": d.get("words") or ""}


def decide(network: str, incident_id: str, pick: dict, *, now: float, sources) -> dict:
    """The clear's decision on *pick* (`diagnose.action_for`'s): a record, not yet written."""
    from modules.heal import actions, guards
    from modules.heal.guards import value
    from modules.nsot import privileged

    src = sources
    kind, at = pick["kind"], pick.get("at") or {}
    variant = pick.get("variant") or "hard"
    device, peer = at.get("host") or "", str(at.get("peer") or "")
    mode = src.mode(now)
    lab = (mode.get("stage") or {}).get("stage") == "lab"
    tier = actions.tier_of(kind, lab)
    key = VARIANT_KEY.get(variant, "")
    unit = {"kind": kind, "tier": tier, "id": f"{kind}:{peer}",
            "words": f"a {variant} clear of {device}'s BGP neighbour {peer}"}
    base = {"incident": incident_id, "device": device, "mode": mode.get("mode"),
            "policy": {"fingerprint": mode.get("fingerprint"),
                       "by": (mode.get("confirmed") or {}).get("by"),
                       "reason": (mode.get("confirmed") or {}).get("reason")},
            "guard": None, "units": [unit], "kind": kind, "tier": tier, "program": [],
            "program_hash": "", "until": None, "triggers": [pick.get("words") or ""],
            "action": {"kind": kind, "device": device, "interface": "", "peer": peer,
                       "variant": variant, "rule": pick.get("rule") or "",
                       "hypothesis": pick.get("hypothesis")},
            "steps": [{"step": "choose", "result": "ok", "words": pick.get("words") or ""}],
            "phase": "stops"}

    def passed(name, words, then):
        base["steps"].append({"step": name, "result": "ok", "words": words})
        base["phase"] = then

    def stop(g, phase=None):
        if phase:
            base["phase"] = phase
        return dict(base, outcome=g["outcome"] if g["outcome"] in (
            "held", "halted", "off", "nothing", "cant_fix") else "cant_fix",
            guard={k: g.get(k) for k in ("guard", "name", "words", "operands")},
            tier=g.get("tier") or base["tier"],
            words=f"guard {g['guard']}, {g['name']}: {g['words']}", until=g.get("until"))

    def cant(words, gid, name, operands, tier_, phase="guards"):
        return dict(base, outcome="cant_fix", tier=tier_, phase=phase,
                    guard={"guard": gid, "name": name, "words": words, "operands": operands},
                    words=f"{name}: {words}")

    if not device or not peer or not key:
        return dict(base, outcome="cant_fix", phase="choose",
                    words="the diagnosis named no device, neighbour and clear to act on")
    try:
        halt = src.halted()
    except Exception as exc:
        halt = {"unreadable": str(exc)}
    for g in (guards.g1_kill_switch(mode), guards.g2_mode(mode, halt),
              src.planned(device, now)):
        if g:
            return stop(g)
    passed("stops", f"no kill switch, the mode {mode.get('mode')}, no halt, no planned work",
           "rates")
    counted = "heal" if mode.get("mode") == "auto" else "would_heal"
    try:
        rows = src.decisions()
    except Exception as exc:
        return stop(guards.hit(10, "halted", f"the heal record cannot be read ({exc}), and a "
                                             "rate that cannot be counted holds", {}))
    for g in (guards.g9_device_rate(rows, device, counted, now,
                                    value(mode, "heal_max_per_device_hour")),
              guards.g10_network_rate(rows, network, counted, now,
                                      value(mode, "heal_max_per_network_hour"))):
        if g:
            return stop(g)
    passed("rates", "under the rates per device and per network", "fresh")

    # The fresh reads: the neighbour (13a, the second of the two reads), and the device's route
    # toward Mercury (13c), through the reads engine.
    dev = src.device(device) or {}
    intents, _ierr = src.intents()
    hv = (intents or {}).get(device)
    dialect, derr = _dialect(hv or {}, dev, device)
    rd = reads_for(peer)
    address = dev.get("ip", "")
    manager, mwhy = src.manager_toward(address) if address else ("", "no address held")
    cmds = [rd["session"]]
    rcmd = actions.route_command(manager) if manager and variant == "hard" else ""
    if rcmd:
        cmds.append(rcmd)
    got = src.read(device, cmds)
    passed("fresh", (f"{device}: {len([c for c in cmds if c in got])} of {len(cmds)} read(s)"
                     + (f" ({got['_why']})" if "_why" in got else "")), "guards")
    fresh = privileged.bgp_session(got.get(rd["session"], ""))
    # The first of the two reads is the diagnosis's: its rule fires only on a session it read
    # not Established (a hard clear's) or Established (a soft clear's).
    first = {"read": True, "established": variant == "soft",
             "state": f"as the diagnosis read it ({pick.get('hypothesis') or 'its first'})"}
    facts = {"13a": actions.g13a_fresh(
        kind, {"holds": True, "words": pick.get("words") or "the diagnosis's first hypothesis"},
        actions.precondition(kind, {"established": fresh["established"],
                                    "state": fresh["state"] or "not read",
                                    "variant": variant} if fresh["read"] else None)),
        "13b": None}
    route = ({"manager": manager, "command": rcmd, "answer": got.get(rcmd)} if rcmd
             and rcmd in got else {"manager": manager, "command": rcmd, "answer": None,
                                   "why": mwhy or got.get("_why") or "not read"})
    facts["13c"] = actions.g13c_session(device, peer, variant, route=route)
    facts["13d"] = actions.g13d_once(kind, actions.history_of(rows, counted),
                                     {"device": device, "peer": peer, "incident": incident_id},
                                     now, per_hour=value(mode, "heal_bounce_per_port_hour"),
                                     repeat_hours=value(mode, "heal_repeat_halts_hours"))
    judged = actions.judge(kind, facts)
    base["steps"] += [{"step": "guards", "result": "ok", "words": f"{s['step']}: {s['words']}"}
                      for s in judged["steps"] if s.get("result") == "ok"]
    if judged["outcome"] != "pass":
        g = dict(judged["guard"] or {}, outcome=judged["outcome"], tier=judged["tier"],
                 until=None)
        if not judged["guard"]:
            return dict(base, outcome="cant_fix", words=judged["words"], phase="guards")
        return stop(g, "guards")
    plan = privileged.clear_plan(key, peer, dialect=dialect, device=device,
                                 sessions=[first, fresh], intent_peers=_intent_peers(hv))
    if not plan["ok"]:
        why = plan["refused"] + (f" ({derr})" if derr and not dialect else "")
        return cant(why, "clear", "the clear's own plan",
                    {"device": device, "peer": peer, "key": key, "dialect": dialect}, 3)
    passed("guards", f"13a, 13c and 13d passed; the {plan['label']} planned and measured on "
                     f"{dialect}", "decide")
    reason = policy_reason(network, variant, peer, base["policy"])
    h = privileged.clear_hash(network, device, address, plan["command"])
    base.update(program=[plan["command"]], program_hash=h, clear={
        "key": key, "variant": variant, "family": plan["family"], "peer": peer,
        "command": plan["command"], "read": plan["read"], "dialect": dialect,
        "bound_s": plan["bound_s"], "window_s": window_seconds(plan),
        "interface": fresh.get("interface") or "", "manager": manager, "reason": reason,
        "affects": plan["affects"], "not_doing": plan["not_doing"],
        "rollback": plan["rollback"],
        "sessions": [{"state": s.get("state"), "established": s.get("established")}
                     for s in (first, fresh)]})
    if tier == 2:
        if kind in (mode.get("kinds_propose") or []):
            return dict(base, outcome="propose",
                        words=(f"proposed for a person: {unit['words']} (Tier 2 on a network "
                               f"not marked lab, N16); command {h}"))
        return dict(base, outcome="cant_fix", words=(
            f"a Tier 2 action ({kind}) the policy does not propose: nothing is sent, and a "
            "person clears it"))
    allowed = kind in (mode.get("kinds_auto") or [])
    if mode.get("mode") == "auto" and allowed:
        return dict(base, outcome="heal",
                    words=f"clear now: {unit['words']} (Tier 1), allowed AUTO; command {h}")
    why = ("the mode is dry run" if mode.get("mode") != "auto" else
           f"{kind} is not allowed AUTO, so dry run for it")
    return dict(base, outcome="would_heal",
                words=(f"would have cleared {device}'s BGP neighbour {peer} ({plan['command']},"
                       f" command {h}); {why}. Nothing was sent"))


def _log_decision(network: str, d: dict, now: float) -> None:
    from modules.heal import steplog

    try:
        steplog.record_decision(network, d, now)
    except Exception as exc:
        log.error("heal: %s's session clear decision %s is not in the step log: %s", network,
                  d.get("id"), exc)


def _announce() -> None:
    try:
        from modules import invalidation
        invalidation.announce(invalidation.ANNOUNCERS[ANNOUNCER], by=ANNOUNCER)
    except Exception as exc:                          # noqa: BLE001 (a page's freshness only)
        log.info("heal: a session clear recorded, not announced: %s", exc)


# ── The act ─────────────────────────────────────────────────────────────────────────────────

class _ActSources:
    """`act._stops`' and `propose._stops`' reads, from the clear's sources."""

    def __init__(self, src):
        self.src = src

    def mode(self, now):
        return self.src.mode(now)

    def planned(self, device, now):
        return self.src.planned(device, now)


def apply(network: str, decision: dict, *, now: float = None, sources=None) -> dict:
    """Apply one taken clear decision as the policy (Tier 1, a network marked lab), verify it
    and record it: ``{"decision", "device", "outcome", "words", "steps", "sent", "records"}``."""
    from modules.heal import act as heal_act

    src = sources or Sources(network)
    now = src.clock() if now is None else float(now)
    pol = decision.get("policy") or {}
    setter = pol.get("by") or ""
    by = f"self-healing (policy set by {setter or 'nobody recorded'})"
    why = heal_act._stops(_ActSources(src), network, decision, now)
    return _act(network, decision, src, now=now, by=by, actor=setter or ACTOR,
                reason=(decision.get("clear") or {}).get("reason") or "", stops=why)


def apply_approved(network: str, decision: dict, approval: dict, *, now: float = None,
                   sources=None) -> dict:
    """Apply one taken, approved clear proposal (Tier 2) as the approving person, with their
    reason: the same act as `apply`, its stops the proposal's (`propose._stops`)."""
    from modules.heal import propose

    src = sources or Sources(network)
    now = src.clock() if now is None else float(now)
    why = propose._stops(network, decision, now, _ActSources(src))
    return _act(network, decision, src, now=now,
                by=f"heal proposal approved by {approval['by']}", actor=approval["by"],
                reason=approval.get("reason") or "", stops=why,
                taken=f"taken on {approval['by']}'s approval of proposal {approval.get('hash')}",
                approval=approval)


def _act(network: str, decision: dict, src, *, now: float, by: str, actor: str, reason: str,
         stops: str, taken: str = "", approval: dict = None) -> dict:
    from modules.heal import steplog
    from modules.nsot import privileged
    from modules.redact import redact_text

    c, device = decision.get("clear") or {}, decision["device"]
    out = {"decision": decision.get("id"), "device": device, "outcome": "refused", "words": "",
           "sent": False, "records": {},
           "steps": [{"step": "take", "result": "ok", "words": taken or f"taken by {by}"}]}

    def note(step, result, words):
        out["steps"].append({"step": step, "result": result, "words": redact_text(words),
                             "at": _iso(src.clock())})

    def finish(outcome, words):
        out.update(outcome=outcome, words=words)
        return _record(network, decision, out, by=by, now=src.clock(), approval=approval)

    def refuse(step, words, result="refused"):
        note(step, result, words + ". Nothing was sent")
        return finish("refused", words + ". Nothing was sent")

    if stops:
        return refuse("stops", stops)
    note("stops", "ok", "the kill switch, the mode, the stage, the policy and planned work: "
                        "clear")
    dev = src.device(device) or {}
    intents, _ierr = src.intents()
    hv = (intents or {}).get(device)
    dialect, _derr = _dialect(hv or {}, dev, device)
    sessions = [dict(s, read=True) for s in c.get("sessions") or []]
    plan = privileged.clear_plan(c.get("key") or "", c.get("peer") or "", dialect=dialect,
                                 device=device, sessions=sessions,
                                 intent_peers=_intent_peers(hv))
    if not plan["ok"]:
        return refuse("plan", plan["refused"].removesuffix(". Nothing was sent"))
    h = privileged.clear_hash(network, device, dev.get("ip", ""), plan["command"])
    if h != decision.get("program_hash"):
        return refuse("plan", f"the clear's hash moved since the decision (decided "
                              f"{decision.get('program_hash')}, now {h}): the device's address "
                              "or the command moved")
    note("plan", "ok", f"`{plan['command']}`: its hash {h} is the decision's; measured on "
                       f"{dialect}, verify bound {plan['bound_s']} s")
    # Why a clear has no rollback (`privileged`'s rule), in its record and History (H23).
    out["records"]["rollback"] = f"does not apply: {plan.get('rollback') or 'not stated'}"
    values = src.values()
    started = src.clock()

    def prepare(read):
        """On the held session, before anything is sent: 13c again, the window, the started
        row. A refusal names its step; None lets `privileged.send_clear` read and send."""
        from modules.heal import actions

        manager = c.get("manager") or ""
        if plan["variant"] == "hard":
            rcmd = actions.route_command(manager) if manager else ""
            g = actions.g13c_session(device, plan["peer"], "hard", route={
                "manager": manager, "command": rcmd,
                "answer": read(rcmd) if rcmd else None, "why": "no manager address held"})
            if g:
                return {"state": "refused", "why": f"13c: {g['words']}", "step": "route"}
        note("route", "ok", "a hard clear withdraws no route Mercury uses" if
             plan["variant"] == "hard" else "a soft clear withdraws nothing")
        # C2749: a hard clear drops the session at the neighbour too, so the window covers the
        # device committed intent gives the neighbour's address (none for an outside peer).
        from modules.neighbours import peer_device
        far_dev = peer_device(intents or {}, plan["peer"]) if plan["variant"] == "hard" else ""
        w = src.window(network, device, c.get("interface") or "", src.clock(),
                       window_seconds(plan), by=by,
                       why=(f"self-healing's {plan['label']}: `{plan['command']}` on {device} "
                            f"(decision {decision.get('id')})"),
                       far_ends=[(far_dev, "")] if far_dev and far_dev != device else [])
        rec = w.get("record") or {}
        # The far end the window names (C2749), kept so the neighbour's History draws it (H23).
        out["records"]["window"] = ({**{k: rec.get(k) for k in ("from", "until", "via",
                                                                "interfaces")},
                                     "far_ends": (rec.get("expected") or {}).get(
                                         "far_ends") or []}
                                    if w.get("ok") else {"error": w.get("error")})
        if not w.get("ok"):
            return {"state": "refused", "step": "window", "why": (
                f"the planned window for the clear could not be recorded ({w.get('error')}): "
                "an unannounced reset reads as a fault")}
        note("window", "ok", f"planned window recorded: {window_seconds(plan)} s, "
                             f"{rec.get('from')} to {rec.get('until')}"
                             + (f", naming {c['interface']}" if c.get("interface") else ""))
        try:
            steplog.record_started(network, decision, list(out["steps"]), [plan["command"]], h,
                                   by=by, now=src.clock())
        except Exception as exc:
            return {"state": "refused", "step": "send",
                    "why": f"the step log's started row could not be written ({exc})"}
        return None

    if not dev:
        return refuse("hold", f"{device} is not a device of {network}")
    # The one held send (`privileged.run_clear`): the hold, the session, *prepare* above, then
    # `send_clear` (the session read again and kept, the command once, the verify).
    got = privileged.run_clear(network, dev, plan, actor=actor, operation=OPERATION,
                               values=values, session=src.session, prepare=prepare,
                               on_hold=lambda: note("hold", "ok", f"{device} held for the clear"),
                               clock=src.clock, sleep=src.sleep)
    sent = "printed" in got
    out["sent"] = sent
    if not sent:
        step = got.get("step") or "send"
        return refuse(step, got.get("why") or "nothing was sent")
    run = privileged.clear_record(network, plan, got, actor=actor, reason=reason, hash_=h,
                                  decision=decision.get("id") or "", started=started)
    out["records"]["privileged"] = run["id"]
    outcome = _OUTCOME_OF.get(got["state"], "unverified")
    v = (got.get("verify") or {}).get("words") or got.get("why") or ""
    note("send", "failed" if outcome == "rejected" else "ok",
         f"`{plan['command']}` sent once" + (f"; the device asked {got['answered']!r}, the "
                                            "measured prompt, and it was answered"
                                            if got.get("answered") else "")
         + (f": {got.get('why')}" if outcome == "rejected" else ""))
    if outcome != "rejected":
        note("verify", "ok" if outcome == "cleared" else "failed",
             f"{v}, after {got.get('waited_s')} s (bound {plan['bound_s']} s)")
    words = {"cleared": f"{device}'s BGP neighbour {plan['peer']} cleared ({plan['label']}); "
                        f"{v}; configuration unchanged",
             "not_back": f"{device}'s BGP neighbour {plan['peer']} cleared and not Established "
                         f"within {plan['bound_s']} s: {v}",
             "reset": f"the soft clear of {plan['peer']} on {device} reset the session: {v}",
             "unverified": f"{device}'s BGP neighbour {plan['peer']} cleared; {v}",
             "rejected": f"{device} refused `{plan['command']}` ({got.get('why')}): nothing "
                         "was cleared"}[outcome]
    return finish(outcome, words)


def _record(network: str, decision: dict, out: dict, *, by: str, now: float,
            approval: dict = None) -> dict:
    """``record``: what the clear did, in the decisions store (a halt, guard 14, for a soft
    clear that reset its session), its change record (H23), the step log (History) and the
    announcement."""
    from modules.heal import change_record, decisions, steplog

    out["steps"].append({"step": "record", "result": "ok",
                         "words": OUTCOME_WORDS.get(out["outcome"], out["outcome"]),
                         "at": _iso(now)})
    try:
        decisions.applied(network, decision["id"], out["outcome"], by=by, words=out["words"],
                          now=now)
        if out["outcome"] in HALTS:
            decisions.halt(network, guard=14, name="a rolled-back heal",
                           words=(f"the clear on {decision.get('device')} ({decision['id']}) "
                                  f"was {out['outcome']}: {out['words']}"),
                           operands={"decision": decision["id"],
                                     "device": decision.get("device"),
                                     "outcome": out["outcome"]}, now=now)
    except Exception as exc:
        log.error("heal: %s's clear %s outcome not recorded: %s", network, decision.get("id"),
                  exc)
        out["records"]["error"] = f"the outcome could not be recorded ({exc})"
    out["records"].setdefault("rollback", "does not apply: nothing was sent")
    out["records"]["change_record"] = change_record.build_action(
        network, decision, out, approval=approval, at=_iso(now))
    try:
        steplog.record_act(network, decision, out, by=by, now=now)
    except Exception as exc:
        log.error("heal: %s's clear %s is not in the step log: %s", network,
                  decision.get("id"), exc)
    _announce()
    return out
