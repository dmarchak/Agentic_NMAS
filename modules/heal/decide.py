"""Decide: each ready incident judged, in section 6's order, and recorded (board H, part H3;
docs/HEAL_TO_INTENT.md section 4 step 2, sections 5 to 7 and 11). It reads the device and
changes nothing: the decision records, and H4 acts.

**The decision, per incident** (`decide_one`), each step the first that applies ends it:
1. guards 1 to 3 (`guards.g1_kill_switch`, `g2_mode` with a halt in force, `g3_planned`),
   before any read;
2. guard 4, the approved state (N5): the device's newest golden carries ``Intent-Match:`` at
   intent for it (`device_list._golden_history`), or, where no trailer was recorded, the golden
   matches committed intent now (`intent_match.intent_match`);
3. guards 5 to 11: the topology hold (`hold.topology`), many devices at once, a person working,
   the grace period, and the rates per device, per network and of the same deviation;
4. a FRESH read of the device (`Sources.read`, the capture path's one checked read), its
   departure from the golden compared with the one the grace period settled on
   (`drift_check.drift_diff`, `departure`): moved since, the incident is checked again;
5. the units and their kinds (`kinds.classify`: the intersection rule, N13's units, the tier
   table, N4, N9), the program from the golden's own lines and the measured removals
   (`program`, the deploy's `_program`), its hash (`deploy.command_fingerprint`), and what it
   would cut of Mercury's reach (`expected_effects.for_device`'s ``reach_lost``: Tier 4);
6. guard 12, the program's size; guard 14, a rolled-back heal; guard 13, the tier (`_outcome`):
   AUTO and every unit's kind allowed AUTO, ``heal``; Tier 1 otherwise, ``would_heal`` (dry
   run); Tier 2 kinds the policy proposes, ``propose``; anything else, ``cant_fix``.

**What happens to the incident.** ``heal`` and ``propose`` keep it claimed for H4 and H5
(`decisions.to_apply`, `proposals`); ``held`` with a time, and a read that moved, send it back
to watching until then (`incidents.defer`); every other outcome closes it, naming the decision.

**What is recorded** (`decisions.record`): the outcome and mode, the first guard that applied
with both operands, each unit by kind and tier with its lines masked, the program masked and
its hash, the departure, the policy's fingerprint and who confirmed it, the person a change was
from (N12: a person's change is healed, the person named), and the words a person reads.

**The program, one computation** (`program`): H4 calls it on its own read at apply and refuses
unless the hash is the decision's, so what was decided is what is sent, byte for byte.
"""

import logging
import time

log = logging.getLogger(__name__)

#: The decision's steps, in order, for the manual's How it works page (H10).
STEPS = (("claim", "Take a ready incident"),
         ("stops", "Check the kill switch, the mode and planned work"),
         ("approved", "Find the approved state: the golden that matched intent"),
         ("guards", "Check the hold, the fleet, a person working, the grace and the rates"),
         ("read", "Read the device again and compare"),
         ("classify", "Class each unit and its tier, and compute the program and its hash"),
         ("decide", "Decide: heal, would heal, propose or can't fix"),
         ("record", "Record the decision"))


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


class Sources:
    """Where the decision reads, each replaceable in a test. None of them sends to a device:
    `read` is the capture path's one checked ``show running-config``."""

    def __init__(self, network: str):
        self.network = network

    def ref(self):
        from modules.nsot import listref

        return listref.resolve(self.network)

    def device(self, device: str) -> dict:
        from modules import device_page

        _ref, dev = device_page.find_device(device, self.ref())
        return dev or {}

    def golden(self, device: str, dev: dict) -> dict:
        """``{"text", "commit", "state", "words"}``: the committed golden and whether it is the
        approved state (N5)."""
        from modules import device_list, goldens
        from modules.nsot import intent_match

        rec = goldens._golden_record(dev.get("ip", ""), self.network)
        if rec.get("text") is None:
            return {"text": None, "commit": "", "state": "unknown",
                    "words": rec.get("refused") or "no golden is saved"}
        repo = self.ref().repo_dir
        hist, err, _full = device_list._golden_history(repo, only=device)
        entry = (hist or {}).get(device) or {}
        intent = entry.get("intent") or {"state": "unrecorded"}
        if intent.get("state") in ("at_intent", "departs"):
            return {"text": rec["text"], "commit": entry.get("commit", ""),
                    "state": intent["state"], "words": intent.get("words", "")}
        got = intent_match.intent_match(repo, self.network, device, rec["text"])
        state = {"match": "at_intent", "differs": "departs"}.get(got["state"], "unknown")
        return {"text": rec["text"], "commit": entry.get("commit", ""), "state": state,
                "words": (f"no Intent-Match trailer recorded ({err or 'none'}); compared now: "
                          f"{intent_match.words(got)}")}

    def intended(self, device: str, platform: str) -> dict:
        from modules.nsot import intent_match

        return intent_match.intended_config(self.ref().repo_dir, self.network, device, platform)

    def platform(self, device: str, dev: dict) -> str:
        from modules.nsot import manifest

        entry = manifest.find_by_name(self.ref().repo_dir, device)[1] or {}
        return entry.get("platform") or dev.get("platform") or dev.get("device_type") or ""

    def read(self, dev: dict) -> tuple:
        from routes.golden import _read_running

        return _read_running(dev)

    def intents(self) -> dict:
        from modules.neighbours import committed_intents

        got, _err = committed_intents(self.ref().repo_dir)
        return got or {}

    def host_networks(self) -> list:
        from modules.nsot import blast_radius

        return blast_radius.host_networks()

    def topology(self, device: str, now: float) -> dict:
        from modules.heal import hold

        return hold.topology(self.network, device, now)


# ── The program: one computation for the decision and the apply ────────────────────────────

def program(golden: str, running: str, units: list, removal_ids: list, *, mgmt_ip: str,
            platform: str) -> dict:
    """The heal's exact program and its hash: the golden's own lines for each missing or
    changed unit, merged (`deploy.merge_commands` through the deploy's `_program`), then the
    measured removals the units name (`removal.with_removals`). ``{"commands", "hash",
    "removal_commands", "refused"}``. In memory only: a record keeps masked lines and the
    hash."""
    from modules.heal.kinds import _stored
    from modules.nsot.deploy import command_fingerprint
    from modules.nsot.removal import _subtree_fragment
    from routes.deploy import _program

    adds = []
    for u in units:
        if u["op"] in ("add", "change"):
            lines = u["add"][:1] if u.get("stanza") else u["add"]
            adds.extend({"chain": list(c), "line": l} for c, l in lines)
    fragment = _subtree_fragment(adds, golden) if adds else ""
    got = _program(fragment, _stored(running), list(removal_ids), {"ip": mgmt_ip}, platform)
    commands = list(got["commands"])
    return {"commands": commands, "removal_commands": list(got.get("removal_commands") or []),
            "refused": list(got.get("refused") or []),
            "hash": command_fingerprint(commands, selected=tuple(removal_ids))}


# ── The decision ────────────────────────────────────────────────────────────────────────────

def _symptom(incident: dict) -> str:
    kinds = {t.get("kind") for t in incident.get("triggers") or []}
    link = any(t.get("kind") == "adjacency" or t.get("interface") for t in
               incident.get("triggers") or [])
    if link:
        return "physical"
    if kinds & {"alert", "adjacency_log"}:
        return "unknown_cause"
    return ""


def _person(incident: dict) -> dict:
    """N12: the newest outside change's person, as its line named them."""
    for t in reversed(incident.get("triggers") or []):
        if t.get("kind") == "config_change" and t.get("person"):
            return t["person"]
    return {}


def _outcome(mode: dict, c: dict, kinds_auto: list, kinds_propose: list) -> tuple:
    """Guard 13, the tier: ``(outcome, words)``."""
    from modules.heal.kinds import KIND_WORDS, NEVER_WHY

    tier, kind = c["tier"], c["kind"]
    if tier >= 3:
        return "cant_fix", (f"self-healing will not fix it: {KIND_WORDS.get(kind, kind)} "
                            f"(Tier {tier}) is never automatic: {NEVER_WHY.get(kind, '')}")
    if c.get("blocked"):
        b = c["blocked"]
        return "cant_fix", (f"self-healing cannot fix it yet: {KIND_WORDS.get(b['kind'])}: "
                            f"{b['why']}")
    kinds = sorted({u["kind"] for u in c["units"]})
    if tier == 2:
        missing = [k for k in kinds if k not in kinds_propose and _tier(k) == 2]
        if missing:
            return "cant_fix", (f"a Tier 2 fix ({', '.join(missing)}) the policy does not "
                                "propose: nothing is sent, and a person fixes it")
        return "propose", f"a fix that needs a person: {', '.join(kinds)} (Tier 2)"
    not_auto = [k for k in kinds if k not in kinds_auto]
    if mode.get("mode") == "auto" and not not_auto:
        return "heal", f"heal now: {', '.join(kinds)} (Tier 1), allowed AUTO"
    why = ("the mode is dry run" if mode.get("mode") != "auto" else
           f"{', '.join(not_auto)} {'is' if len(not_auto) == 1 else 'are'} not allowed AUTO, "
           "so dry run for it")
    return "would_heal", f"would heal: {', '.join(kinds)} (Tier 1); {why}"


def _tier(kind: str) -> int:
    from modules.heal.kinds import TIER

    return TIER.get(kind, 4)


def decide_one(network: str, incident: dict, *, now: float, sources=None, mode=None) -> dict:
    """The decision for one claimed incident: a record (not yet written) ``{"incident",
    "device", "outcome", "mode", "guard", "words", "kind", "tier", "units", "program",
    "program_hash", "removal_ids", "departure", "policy", "person", "until", "verify"}``."""
    from modules.drift_check import departure, drift_diff
    from modules.heal import decisions, guards, incidents, kinds, policy
    from modules.heal.guards import value

    src = sources or Sources(network)
    device = incident["device"]
    mode = mode or policy.current(network, now)
    base = {"incident": incident["id"], "device": device, "mode": mode.get("mode"),
            "policy": {"fingerprint": mode.get("fingerprint"),
                       "by": (mode.get("confirmed") or {}).get("by"),
                       "reason": (mode.get("confirmed") or {}).get("reason")},
            "person": _person(incident), "settled": (incident.get("settled") or {}).get("how"),
            "guard": None, "units": [], "kind": "", "tier": 0, "program": [],
            "program_hash": "", "removal_ids": [], "departure": "", "until": None,
            "triggers": [t.get("words") for t in (incident.get("triggers") or [])[-5:]]}

    def stop(g):
        return dict(base, outcome=g["outcome"], guard={k: g[k] for k in
                                                       ("guard", "name", "words", "operands")},
                    words=f"guard {g['guard']}, {g['name']}: {g['words']}", until=g.get("until"))

    try:
        halt = decisions.halted(network)
    except Exception as exc:
        halt = {"unreadable": str(exc)}
    for g in (guards.g1_kill_switch(mode), guards.g2_mode(mode, halt),
              guards.g3_planned(network, device, now)):
        if g:
            return stop(g)
    dev = src.device(device)
    golden = src.golden(device, dev)
    g = guards.g4_golden(golden)
    if g:
        return stop(g)
    try:
        rows = decisions.decisions(network)
        last_halt = decisions.last_halt_epoch(network)
    except Exception as exc:
        return stop(guards.hit(10, "halted", f"the heal record cannot be read ({exc}), and a "
                                             "rate that cannot be counted holds", {}))
    outcome_counted = "heal" if mode.get("mode") == "auto" else "would_heal"
    grace_s = float(value(mode, "heal_grace_seconds") or 900)
    got = incidents.read(network)
    settled_dep = ((incident.get("settled") or {}).get("operands") or {}).get("departure", "")
    for g in (guards.g5_topology(src.topology(device, now), now),
              guards.g6_many(got["incidents"], now, grace_s,
                             value(mode, "heal_max_devices_drifting")),
              guards.g7_person(incident, now, value(mode, "heal_person_working_changes"),
                               value(mode, "heal_person_working_minutes")),
              guards.g8_grace(incident),
              guards.g9_device_rate(rows, device, outcome_counted, now,
                                    value(mode, "heal_max_per_device_hour")),
              guards.g10_network_rate(rows, network, outcome_counted, now,
                                      value(mode, "heal_max_per_network_hour")),
              guards.g11_repeat(rows, device, settled_dep, outcome_counted, now,
                                value(mode, "heal_repeat_halts_hours"))):
        if g:
            return stop(g)
    if base["settled"] == "at_golden":
        symptom = _symptom(incident)
        if symptom:
            out = {"kind": symptom, "tier": 3, "units": [], "blocked": None}
            return dict(base, kind=symptom, tier=3, outcome="cant_fix",
                        words=_outcome(mode, out, [], [])[1]
                        + f": {device} is at its golden, which matches its intent")
        return dict(base, outcome="nothing",
                    words=f"nothing to heal: {device} is at its golden, which matches its intent")
    text, error = src.read(dev)
    if not text:
        return dict(base, outcome="deferred", until=now + 60,
                    words=f"the decision's read of {device} could not be made ({error}): it is "
                          "checked again")
    now_dep = departure(drift_diff(golden["text"], text, device))
    base["departure"] = now_dep
    if settled_dep and now_dep != settled_dep:
        return dict(base, outcome="deferred", until=now,
                    words=(f"{device} changed since its grace period settled (departure "
                           f"{settled_dep}, now {now_dep or 'none: at its golden'}): its grace "
                           "period starts again"))
    platform = src.platform(device, dev)
    intended = src.intended(device, platform)
    if not intended.get("text"):
        return dict(base, outcome="cant_fix",
                    words=f"committed intent cannot be rendered: {intended.get('why')}")
    c = kinds.classify(golden["text"], text, intended["text"], platform=platform,
                       mgmt_ip=dev.get("ip", ""), related=bool(incident.get("related")))
    base.update(units=[kinds.masked_unit(u) for u in c["units"]], kind=c["kind"],
                tier=c["tier"], left_out=c["left_out"])
    if not c["units"]:
        return dict(base, outcome="nothing",
                    words=(f"nothing to heal: what departed is not from the approved state "
                           f"({c['left_out']['intent_only']} line(s) only intent holds: an "
                           f"intent edit not deployed; {c['left_out']['golden_behind']} the "
                           "golden lacks while intent holds them)"))
    g = guards.g12_size(c["units"], value(mode, "heal_max_removed_units"),
                        value(mode, "heal_max_units"))
    if g:
        return stop(g)
    g = guards.g14_rolled_back(rows, device, last_halt)
    if g:
        return stop(g)
    if c["tier"] < 3 and not c.get("blocked"):
        from modules.nsot import expected_effects
        from modules.pipeline import dangerous_commands
        from modules.redact import redact_text

        prog = program(golden["text"], text, c["units"], c["removal_ids"],
                       mgmt_ip=dev.get("ip", ""), platform=platform)
        base.update(program=[redact_text(x) for x in prog["commands"]],
                    program_hash=prog["hash"], removal_ids=c["removal_ids"],
                    dangerous=[redact_text(x) for x in dangerous_commands(prog["commands"])])
        if prog["refused"]:
            return dict(base, outcome="cant_fix",
                        words=f"the program refuses a unit: {prog['refused'][0]['reason']}")
        fx = expected_effects.for_device(src.intents(), device, prog["commands"],
                                         src.host_networks())
        lost = fx.get("reach_lost")
        if lost and (lost.get("state") != "known" or lost.get("cut")):
            c = dict(c, kind="management_path", tier=4)
            base.update(kind="management_path", tier=4)
            return dict(base, outcome="cant_fix",
                        words=("self-healing will not fix it: the fix would cut Mercury's path "
                               f"({lost.get('cut') or lost.get('why')}), and a change to that "
                               "path needs a repair route independent of it"))
        base["verify"] = {"read_back": len(prog["commands"]),
                          "symptom": [t for t in base["triggers"] if t][:2],
                          "intent": "intent_match on the read after the change"}
    outcome, words = _outcome(mode, c, list(mode.get("kinds_auto") or []),
                              list(mode.get("kinds_propose") or []))
    if base.get("person"):
        words += f"; the change it heals was made outside Mercury ({base['person']['words']})"
    return dict(base, outcome=outcome, words=words)


def _act(network: str, incident: dict, d: dict, now: float) -> None:
    """What the decision does to its incident, after it is recorded."""
    from modules.heal import decisions, incidents

    if d["outcome"] == "halted" and d.get("mode") == "auto" and (d.get("guard") or {}).get(
            "guard") in (10, 11, 14):
        decisions.halt(network, guard=d["guard"]["guard"], name=d["guard"]["name"],
                       words=d["guard"]["words"], operands=d["guard"]["operands"], now=now)
    if d["outcome"] in ("heal", "propose"):
        return                                   # claimed: H4's or H5's
    if d["outcome"] in ("deferred", "held") and d.get("until"):
        incidents.defer(network, incident["id"], d["until"], d["words"], now)
        return
    incidents.close(network, incident["id"], f"{d['outcome']}: {d['words']} (decision "
                                             f"{d['id']})", now)


def run(network: str, *, now: float = None, sources=None, by: str = "heal to intent") -> dict:
    """Decide every ready incident of *network* under its heal lock. ``{"ran", "decided":
    [{"incident", "decision", "outcome"}], "busy", "failed"}``."""
    from modules import filestore
    from modules.heal import decisions, incidents

    now = time.time() if now is None else float(now)
    out = {"ran": False, "network": network, "decided": [], "busy": "", "failed": []}
    try:
        with incidents.HealLock(network, actor="Mercury", trigger=f"the decision ({by})"):
            try:
                ready = incidents.ready(network)
            except filestore.StoreUnreadable as exc:
                return dict(out, failed=[str(exc)])
            for inc in ready:
                claimed = incidents.claim(network, inc["id"], by=by, now=now)
                try:
                    d = decisions.record(network, decide_one(network, claimed, now=now,
                                                             sources=sources), now)
                    _act(network, claimed, d, now)
                except Exception as exc:
                    log.error("heal: %s's decision on %s failed: %s: %s", network,
                              inc["device"], type(exc).__name__, exc)
                    out["failed"].append(f"{inc['device']}: {type(exc).__name__}: {exc}")
                    incidents.defer(network, inc["id"], now + 60,
                                    f"the decision failed ({type(exc).__name__}: {exc}); "
                                    "checked again", now)
                    continue
                out["decided"].append({"incident": inc["id"], "decision": d["id"],
                                       "outcome": d["outcome"]})
    except incidents.HealBusy as exc:
        return dict(out, busy=str(exc))
    if out["decided"]:
        try:
            from modules import invalidation
            invalidation.announce(invalidation.ANNOUNCERS["heal-decide"], by="heal-decide")
        except Exception as exc:
            log.info("heal: %s's decisions recorded, not announced: %s", network, exc)
    out["ran"] = True
    return out
