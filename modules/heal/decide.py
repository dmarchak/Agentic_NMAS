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
to watching until then (`incidents.defer`); ``would_heal``, ``cant_fix`` and ``held`` without a
time leave its cause standing, so it STANDS on the decision (C2813, `incidents.stand`): a later
symptom folds into it, and a drift record of the same departure joins it without a second
decision; every other outcome closes it, naming the decision. A standing incident closes when
its device is read back (`end_standing`: a drift run's clean read, its symptoms read gone).

**What is judged after a standing incident is sent back** (`judged_triggers`): for a departure,
only the triggers from the change that sent it back, so a revert to the golden is nothing to
heal; and the rates (guards 9 to 11) are not counted for an incident settled at its golden,
which has nothing to heal (C2840). A symptom read gone inside the flap window is checked again
once the window has passed, once (C2825): never a can't-fix for what Mercury reads gone.

**What is recorded** (`decisions.record`): the outcome and mode, the first guard that applied
with both operands, each unit by kind and tier with its lines masked, the program masked and
its hash, the departure, the policy's fingerprint and who confirmed it, the person a change was
from (N12: a person's change is healed, the person named), and the words a person reads. Its
steps (`STEPS`, each passed with its words, then the one it ended on) go to the step log
(H6, `steplog.record_decision`), never to the decision's own store.

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
#: Each step in two to four words, for its column on the stepper (the operator, 2026-11-11:
#: "short labels ... No full sentences in the step columns"); the long words above are its
#: hover. `{device}` is the run's own.
STEP_LABELS = {"claim": "Take incident", "stops": "Check stops",
               "approved": "Find approved state", "guards": "Check guards",
               "read": "Read {device}", "classify": "Classify change", "decide": "Decide",
               "record": "Record decision"}


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _hhmm(epoch: float) -> str:
    return time.strftime("%H:%M", time.gmtime(float(epoch)))


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
        # C2815 (H11 W3): THE intent state (C532's one owner, which the Devices list and the
        # device page draw): the device's NEWEST measurement, a Save All that found it
        # unchanged included, while nothing it was judged against has moved since. Never the
        # trailer of the commit that last changed the golden alone: on the lab, one said
        # "departs" from before the device's intent was corrected, while the Save All after it
        # measured that device at intent.
        reads = device_list.reads(repo, only=device)
        entry = (reads.get("history") or {}).get(device) or {}
        intent = device_list.intent_state(device, reads)
        if intent.get("state") in ("at_intent", "departs"):
            return {"text": rec["text"], "commit": entry.get("commit", ""),
                    "state": intent["state"], "words": intent.get("words", "")}
        got = intent_match.intent_match(repo, self.network, device, rec["text"])
        state = {"match": "at_intent", "differs": "departs"}.get(got["state"], "unknown")
        why = intent.get("why") or intent.get("words") or intent.get("state")
        return {"text": rec["text"], "commit": entry.get("commit", ""), "state": state,
                "words": (f"its newest measurement does not stand ({why}); compared now: "
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

    def symptom_now(self, device: str, triggers: list) -> str:
        """The incident's symptoms as their stores read them NOW, with no wait (C2750):
        ``gone`` only when every symptom trigger's store was read after the trigger and no
        longer holds it; ``present``, ``stale`` or ``unreadable`` otherwise, or ``none``
        when no trigger names a symptom. `act.judge`'s rule, the one verify uses."""
        from modules import reader_job
        from modules.heal import act

        wanted = act.symptom_triggers(triggers)
        if not wanted:
            return "none"
        states = set()
        for t in wanted:
            got = reader_job.read_cached(act._store_for(t))
            states.add("unreadable" if got.get("state") != "ok" else
                       act.judge(t, got.get("doc"), self.network, device,
                                 float(t.get("epoch") or 0)))
        for state in ("unreadable", "stale", "present"):
            if state in states:
                return state
        return "gone"


# ── The program: one computation for the decision and the apply ────────────────────────────

def program(golden: str, running: str, units: list, removal_ids: list, *, mgmt_ip: str,
            platform: str) -> dict:
    """The heal's exact program and its hash: the golden's own lines for each missing or
    changed unit, merged (`deploy.merge_commands` through the deploy's `_program`), then the
    measured removals the units name (`removal.with_removals`). ``{"commands", "hash",
    "removal_commands", "refused", "fragment", "keys", "ids"}``: *fragment* is what the merge
    merges from (the apply's capture source, H4), *keys* each removal's line as an
    authorisation names it (each needs a stated reason) and *ids* the removed units' ids. In
    memory only: a record keeps masked lines and the hash."""
    from modules.heal.kinds import _stored
    from modules.nsot.deploy import command_fingerprint
    from modules.nsot.removal import _subtree_fragment
    from routes.deploy import _program

    adds = []
    for u in units:
        if u["op"] in ("add", "change"):
            # A stanza by its header, a leaf by each line, a joined unit (C2822) by its parts'.
            lines = u.get("heads") or (u["add"][:1] if u.get("stanza") else u["add"])
            adds.extend({"chain": list(c), "line": l} for c, l in lines)
    fragment = _subtree_fragment(adds, golden) if adds else ""
    got = _program(fragment, _stored(running), list(removal_ids), {"ip": mgmt_ip}, platform)
    commands = list(got["commands"])
    return {"commands": commands, "removal_commands": list(got.get("removal_commands") or []),
            "refused": list(got.get("refused") or []), "fragment": fragment,
            "keys": list(got.get("keys") or []), "ids": list(got.get("ids") or []),
            "hash": command_fingerprint(commands, selected=tuple(removal_ids))}


# ── The decision ────────────────────────────────────────────────────────────────────────────

def judged_triggers(incident: dict) -> list:
    """The incident's triggers the decision judges: all of them, or, for an incident sent back
    to watching from standing on a departure (C2813, `incidents._rejudge`), those from the
    change that sent it back (``judged_from``) on. The symptoms before it were the departure's
    its earlier decision judged: a revert that puts the device back at its golden is nothing
    to heal, never a can't-fix on a symptom the reverted change caused."""
    since = incident.get("judged_from")
    trig = list(incident.get("triggers") or [])
    if since is None:
        return trig
    return [t for t in trig if float(t.get("epoch") or 0) >= float(since)]


def _symptom(incident: dict) -> str:
    trig = judged_triggers(incident)
    kinds = {t.get("kind") for t in trig}
    link = any(t.get("kind") == "adjacency" or t.get("interface") for t in trig)
    if link:
        return "physical"
    if kinds & {"alert", "adjacency_log", "duplicate_router_id"}:
        return "unknown_cause"
    return ""


def _person(incident: dict) -> dict:
    """N12: the newest outside change's person, as its line named them."""
    for t in reversed(incident.get("triggers") or []):
        if t.get("kind") == "config_change" and t.get("person"):
            return t["person"]
    return {}


def revert_scope(mode: dict, incident: dict):
    """C2839's per-network question for this incident: ``{"words"}`` when the network allows
    Mercury to put back a one-sided security change that broke an adjacency
    (``heal_security_revert_adjacency``, default no) AND the incident judges an adjacency down
    (`judged_triggers`: the adjacency reader's or the adjacency log's) AND spans no other device
    (one-sided: a change on both ends is multi-device, Tier 4); else None. `kinds.classify`
    makes such a unit's kind `security_revert` (Tier 1)."""
    if not (mode or {}).get("security_revert") or incident.get("related"):
        return None
    adj = [t for t in judged_triggers(incident) if t.get("kind") in ("adjacency",
                                                                       "adjacency_log")]
    if not adj:
        return None
    return {"words": (f"{len(adj)} adjacency trigger(s) on this incident, no other device in it, "
                      "and the network allows a one-sided security change that broke an "
                      "adjacency to be put back (heal_security_revert_adjacency)")}


def _outcome(mode: dict, c: dict, kinds_auto: list, kinds_propose: list,
             device: str = "") -> tuple:
    """Guard 13, the tier: ``(outcome, words)``, the words plain (`said.outcome_words`: what
    Mercury did or would do, the tier a label after them; the fix kind's key, the tier's
    number and the mode's key are the record's own fields, which "Details for the record"
    draws: C2817, the survey's item 3, one function behind four surfaces' words). The security
    kinds (C2839, `policy.SECURITY_KINDS`) are always proposed: a person decides, never a
    setting."""
    from modules.heal import said
    from modules.heal.kinds import NEVER_WHY, masked_unit
    from modules.heal.policy import SECURITY_KINDS

    kinds_propose = list(kinds_propose) + list(SECURITY_KINDS)
    tier, kind = c["tier"], c["kind"]
    units = [u if "section" in u else masked_unit(u) for u in c.get("units") or []]
    if tier >= 3:
        return "cant_fix", said.outcome_words("cant_fix", units=units, kind=kind, tier=tier,
                                              device=device, why=NEVER_WHY.get(kind, ""))
    if c.get("blocked"):
        b = c["blocked"]
        return "cant_fix", said.outcome_words("cant_fix", units=units, kind=b["kind"],
                                              tier=tier, device=device, why=b["why"])
    kinds = sorted({u["kind"] for u in c["units"]})
    if tier == 2:
        missing = [k for k in kinds if k not in kinds_propose and _tier(k) == 2]
        if missing:
            return "cant_fix", said.outcome_words("cant_fix", units=units, kind=kind,
                                                  tier=tier, device=device,
                                                  not_proposed=missing)
        return "propose", said.outcome_words("propose", units=units, kind=kind, tier=tier,
                                             device=device)
    not_auto = [k for k in kinds if k not in kinds_auto]
    if mode.get("mode") == "auto" and not not_auto:
        return "heal", said.outcome_words("heal", units=units, kind=kind, tier=tier,
                                          device=device)
    return "would_heal", said.outcome_words("would_heal", units=units, kind=kind, tier=tier,
                                            device=device, not_auto=not_auto,
                                            dry_run=mode.get("mode") != "auto")


def _tier(kind: str) -> int:
    from modules.heal.kinds import TIER

    return TIER.get(kind, 4)


#: The outcomes whose words state the cause first (C2823): what a person reads where they
#: decide, or where Mercury says what it did or could not do. A deferral, an off and nothing to
#: heal say only why.
SAYS_CAUSE = ("heal", "would_heal", "propose", "cant_fix", "held", "halted")
#: What a guard's stop says before the guard's own words (C2817: its number and name go to the
#: record, `guard`).
MODE_WORDS = {"dry_run": "watching only (dry run)", "auto": "fixing by itself (Auto)",
              "off": "off"}
STOP_WORDS = {"held": "Self-healing holds {device}: ",
              "halted": "Self-healing stops on {network}: ",
              "off": "Self-healing does nothing: ",
              "cant_fix": "Mercury cannot fix this by itself: ",
              "deferred": "Checked again later: "}


def decide_one(network: str, incident: dict, *, now: float, sources=None, mode=None) -> dict:
    """The decision for one claimed incident: a record (not yet written) ``{"incident",
    "device", "outcome", "mode", "guard", "words", "outcome_words", "cause", "kind", "tier",
    "units", "program", "program_hash", "removal_ids", "departure", "policy", "person",
    "until", "verify"}``. *cause* is what happened, from the incident's judged triggers and the
    decision's units (`said.cause_of`, C2823: facts first, a hypothesis labelled), or None;
    *words* state it first, then *outcome_words*, what Mercury did or would do."""
    from modules.heal import said

    d = _decide_one(network, incident, now=now, sources=sources, mode=mode)
    d["outcome_words"] = d.get("words") or ""
    try:
        d["cause"] = said.cause_of(judged_triggers(incident), d)
    except Exception as exc:                      # the decision stands; its cause is not said
        log.error("heal: %s's cause on %s could not be said: %s: %s", network,
                  d.get("device"), type(exc).__name__, exc)
        d["cause"] = None
    if d["cause"] and d.get("outcome") in SAYS_CAUSE:
        d["words"] = said.with_cause(d["cause"], d["outcome_words"])
    elif (d.get("person") or {}).get("words") and d.get("outcome") in SAYS_CAUSE:
        d["words"] += (f"; the change was made outside Mercury "
                       f"({d['person']['words']})")
    d["headline"] = said.headline(d, network)
    return d


def _decide_one(network: str, incident: dict, *, now: float, sources=None, mode=None) -> dict:
    """`decide_one`'s decision, its words what Mercury did or would do."""
    from modules.drift_check import departure, drift_diff
    from modules.heal import decisions, guards, incidents, kinds, policy
    from modules.heal.guards import value

    from modules import fault_drills

    src = sources or Sources(network)
    device = incident["device"]
    mode = mode or policy.current(network, now)
    # A declared fault drill: the tag the incident took at its creation, never a declaration
    # read now. Guards 9 and 11 do not apply to it; its decision carries the tag, so its heal
    # is counted as a drill's (`guards.GUARDS_A_DRILL_PASSES`).
    drill = fault_drills.tag_of(incident)
    base = {"incident": incident["id"], "device": device, "mode": mode.get("mode"),
            **({fault_drills.FIELD: drill} if drill else {}),
            "policy": {"fingerprint": mode.get("fingerprint"),
                       "by": (mode.get("confirmed") or {}).get("by"),
                       "reason": (mode.get("confirmed") or {}).get("reason")},
            "person": _person(incident), "settled": (incident.get("settled") or {}).get("how"),
            "guard": None, "units": [], "kind": "", "tier": 0, "program": [],
            "program_hash": "", "removal_ids": [], "departure": "", "until": None,
            "triggers": [t.get("words") for t in (incident.get("triggers") or [])[-5:]],
            # The step log's (H6, `steplog.decision_steps`): each step passed, and the step
            # the decision is on, which a return ends with its outcome.
            # C2817: a step's words name no id or hash; the record's own fields hold them.
            "steps": [{"step": "claim", "result": "ok",
                       "words": f"the incident on {device} taken"}],
            "phase": "stops"}

    def passed(name, words, then):
        base["steps"].append({"step": name, "result": "ok", "words": words})
        base["phase"] = then

    def stop(g):
        # C2817: the guard's number and name are its record's (``guard``), drawn under
        # "Details for the record"; the words say what holds it.
        lead = STOP_WORDS.get(g["outcome"], "").format(device=device, network=network)
        return dict(base, outcome=g["outcome"], guard={k: g[k] for k in
                                                       ("guard", "name", "words", "operands")},
                    words=f"{lead}{g['words']}", until=g.get("until"))

    try:
        halt = decisions.halted(network)
    except Exception as exc:
        halt = {"unreadable": str(exc)}
    for g in (guards.g1_kill_switch(mode), guards.g2_mode(mode, halt),
              guards.g3_planned(network, device, now)):
        if g:
            return stop(g)
    passed("stops", f"no kill switch, {MODE_WORDS.get(mode.get('mode'), mode.get('mode'))}, no "
                    "halt, no planned work", "approved")
    dev = src.device(device)
    # C2606, C2608: an observe-only device or a host has no approved state Mercury may heal
    # to; held under guard 4 (the approved state), naming the key and where NetBox set it.
    from modules.inventory.management import refusal_for
    why = refusal_for(network, device, what="heal",
                      dev=dev if isinstance(dev, dict) else None)
    if why:
        return stop(guards.hit(4, "held", f"heal off for this device: {why}",
                               {"management": (dev or {}).get("_management", "")
                                if isinstance(dev, dict) else "",
                                "role": (dev or {}).get("role", "")
                                if isinstance(dev, dict) else ""}))
    golden = src.golden(device, dev)
    g = guards.g4_golden(golden)
    if g:
        return stop(g)
    passed("approved", (f"the golden {(golden.get('commit') or '')[:10] or '(no commit)'} is the "
                        f"approved state: {golden.get('words') or golden.get('state')}"), "guards")
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
    # C2840: the rates (guards 9 to 11) bound HEALS. An incident whose grace period settled at
    # its golden (its newest read, after every outside change, found the device at its golden:
    # a person's revert, say) has nothing to heal, and can end only nothing to heal or a Tier 3
    # can't-fix, neither of which sends; so it passes them, said, never held by the rate its
    # own departure's would-heal used.
    at_golden = base["settled"] == "at_golden"
    rates = () if at_golden else (
        guards.g9_device_rate(rows, device, outcome_counted, now,
                              value(mode, "heal_max_per_device_hour"), drill=drill),
        guards.g10_network_rate(rows, network, outcome_counted, now,
                                value(mode, "heal_max_per_network_hour")),
        guards.g11_repeat(rows, device, settled_dep, outcome_counted, now,
                          value(mode, "heal_repeat_halts_hours"), drill=drill))
    for g in (guards.g5_topology(src.topology(device, now), now),
              guards.g6_many(got["incidents"], now, grace_s,
                             value(mode, "heal_max_devices_drifting")),
              guards.g7_person(incident, now, value(mode, "heal_person_working_changes"),
                               value(mode, "heal_person_working_minutes")),
              guards.g8_grace(incident)) + rates:
        if g:
            return stop(g)
    passed("guards", "no topology hold, not many devices at once, no person working, the grace "
                     "period settled, " + (
                         "and no rate counted: its read found it at its golden, so there is "
                         "nothing to heal" if at_golden else
                         "under the network's rate; a declared fault drill, so the per-device "
                         "rate and the same-deviation guard do not apply" if drill else
                         "under every rate"), "read")
    if at_golden:
        base["phase"] = "decide"
        symptom = _symptom(incident)
        judged = judged_triggers(incident)
        # C2750: an incident held past its symptom (guard 5's topology hold held one for four
        # hours, 2026-11-07) is judged on what its stores read now, never on its triggers'
        # words alone: a symptom gone by itself is nothing to heal, and no can't-fix row. Gone
        # means read gone AND quiet for the flap window since its last trigger, so a link still
        # flapping (I5), up at the moment it is read, is never called cleared.
        now_state = (src.symptom_now(device, judged)
                     if symptom and hasattr(src, "symptom_now") else "")
        quiet_s = float(value(mode, "heal_flap_minutes") or 10) * 60
        last = max((float(t.get("epoch") or 0) for t in judged), default=0.0)
        if symptom and now_state == "gone" and now - last >= quiet_s:
            return dict(base, outcome="nothing",
                        words=(f"nothing to heal: every symptom the incident named has cleared "
                               f"by itself at {_hhmm(now)} UTC, nothing to do: {device} is at "
                               "its golden, which matches its intent (each symptom read again "
                               f"after it, and quiet {int(quiet_s // 60)} minutes since its "
                               "last trigger)"))
        if symptom and now_state == "gone" and not incident.get("quiet_deferred"):
            # C2825 (H11 W5): read gone inside the flap window is not yet cleared (a link still
            # flapping reads up between its drops), and not a can't-fix either: no Critical row
            # and no "could not fix" message for what Mercury reads gone. Checked again once
            # the window has passed since its last trigger; once only, so a link that keeps
            # flapping is a can't-fix after one window, as before.
            until = last + quiet_s
            return dict(base, kind=symptom, tier=3, outcome="deferred", until=until, quiet=True,
                        words=(f"checked again at {_hhmm(until)} UTC: every symptom the "
                               f"incident named reads gone now, and {device} is at its golden, "
                               f"which matches its intent; it is called cleared only once "
                               f"nothing is logged for {int(quiet_s // 60)} minutes since its "
                               "last trigger, so a link still flapping is never called "
                               "cleared"))
        if symptom:
            out = {"kind": symptom, "tier": 3, "units": [], "blocked": None}
            return dict(base, kind=symptom, tier=3, outcome="cant_fix",
                        words=_outcome(mode, out, [], [], device)[1])
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
    passed("read", f"{device} read again: it holds the change the grace period settled on",
           "classify")
    platform = src.platform(device, dev)
    intended = src.intended(device, platform)
    if not intended.get("text"):
        return dict(base, outcome="cant_fix",
                    words=f"committed intent cannot be rendered: {intended.get('why')}")
    c = kinds.classify(golden["text"], text, intended["text"], platform=platform,
                       mgmt_ip=dev.get("ip", ""), related=bool(incident.get("related")),
                       revert=revert_scope(mode, incident))
    base.update(units=[kinds.masked_unit(u) for u in c["units"]], kind=c["kind"],
                tier=c["tier"], left_out=c["left_out"])
    if not c["units"]:
        base["phase"] = "decide"
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
    passed("classify", (f"{len(c['units'])} part(s) changed, "
                        f"{kinds.KIND_WORDS.get(c['kind'], c['kind'])} (Tier {c['tier']})"
                        + (f"; the fix {len(base['program'])} line(s)"
                           if base["program_hash"] else "")),
           "decide")
    outcome, words = _outcome(mode, c, list(mode.get("kinds_auto") or []),
                              list(mode.get("kinds_propose") or []), device)
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
        incidents.defer(network, incident["id"], d["until"], d["words"], now,
                        quiet=bool(d.get("quiet")))
        return
    if d["outcome"] in incidents.STANDS:
        # C2813: its cause still stands, so the incident stays open on this decision: a later
        # symptom folds into it, a later trigger of the same departure joins it.
        incidents.stand(network, incident["id"], d, settled=incident.get("settled"), now=now)
        return
    incidents.close(network, incident["id"], f"{d['outcome']}: {d['words']} (decision "
                                             f"{d['id']})", now)


def end_standing(network: str, incident_id: str, words: str, *, now: float, by: str,
                 read_words: str) -> dict:
    """Close a STANDING incident (C2813, C2825) because what read its device back found its
    cause gone: a drift run that read the device at its golden after its decision, the detect
    pass reading every symptom it named gone and quiet for the flap window, or the can't-fix
    notice's diagnosis. One decision of nothing to heal is recorded on it (*words*, what read
    it and when, *read_words*), in the decisions and the step log, so History says why it
    closed and its Needs attention item leaves (a later decision of nothing to heal resolves a
    can't-fix, `attention._later_done`). Taken first (`incidents.take_standing`), so a change
    that sent it back to watching meanwhile wins: then nothing is recorded and ``{}`` is
    returned. Returns the decision recorded."""
    from modules.heal import decisions, incidents, policy

    try:
        inc = incidents.take_standing(network, incident_id, by=by, now=now)
    except incidents.Refused as exc:
        log.info("heal: %s's %s is not ended: %s", network, incident_id, exc)
        return {}
    s = inc.get("standing") or {}
    try:
        mode = policy.current(network, now)
    except Exception as exc:                          # the record names the mode it could read
        mode = {"mode": "unknown", "words": str(exc)}
    made = {"incident": incident_id, "device": inc.get("device") or "",
            "mode": mode.get("mode"), "outcome": "nothing", "words": words,
            "policy": {"fingerprint": mode.get("fingerprint"),
                       "by": (mode.get("confirmed") or {}).get("by"),
                       "reason": (mode.get("confirmed") or {}).get("reason")},
            "person": {}, "settled": (inc.get("settled") or {}).get("how"), "guard": None,
            "units": [], "kind": "", "tier": 0, "program": [], "program_hash": "",
            "removal_ids": [], "departure": "", "until": None, "ends": s.get("decision") or "",
            "triggers": [t.get("words") for t in (inc.get("triggers") or [])[-5:]]}
    steps = [{"step": "claim", "result": "ok",
              "words": f"the incident on {made['device']} taken by {by}: it stood on its "
                       f"decision ({s.get('outcome') or '?'})"},
             {"step": "read", "result": "ok", "words": read_words}]
    try:
        d = decisions.record(network, made, now)
    except Exception as exc:
        log.error("heal: %s's %s could not be ended (%s): it stands", network, incident_id, exc)
        incidents.stand(network, incident_id, None, now=now)
        return {}
    incidents.close(network, incident_id, f"nothing: {words} (decision {d['id']})", now)
    _log_steps(network, dict(d, steps=steps, phase="decide"), now)
    try:
        from modules import invalidation
        invalidation.announce(invalidation.ANNOUNCERS["heal-decide"], by="heal-decide")
    except Exception as exc:
        log.info("heal: %s's %s ended, not announced: %s", network, incident_id, exc)
    return d


def _log_steps(network: str, d: dict, now: float) -> None:
    """The decision's row in the step log (H6, `steplog.record_decision`). A failure is logged,
    never raised: the decision is recorded in its own store, and a heal's act writes its own
    ``started`` row before anything is sent, refusing the heal when it cannot."""
    from modules.heal import steplog

    try:
        steplog.record_decision(network, d, now)
    except Exception as exc:
        log.error("heal: %s's decision %s is not in the step log: %s: %s", network,
                  d.get("id"), type(exc).__name__, exc)


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
                    made = decide_one(network, claimed, now=now, sources=sources)
                    steps, phase = made.pop("steps", []), made.pop("phase", "decide")
                    d = decisions.record(network, made, now)
                    _act(network, claimed, d, now)
                    _log_steps(network, dict(d, steps=steps, phase=phase), now)
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
