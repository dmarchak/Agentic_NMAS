"""Decide: each ready incident judged, in section 6's order, and recorded (board H, part H3;
docs/HEAL_TO_INTENT.md section 4 step 2, sections 5 to 7 and 11). It reads the device and
changes nothing: the decision records, and H4 acts.

**The decision, per incident** (`decide_one`), each step the first that applies ends it:
1. guards 1 to 3 (`guards.g1_kill_switch`, `g2_mode` with a halt in force, `g3_planned`),
   before any read;
2. guard 4, the approved state (N5): the device's newest golden carries ``Intent-Match:`` at
   intent for it (`device_list._golden_history`), or, where no trailer was recorded, the golden
   matches committed intent now (`intent_match.intent_match`);
3. guard 6, many devices at once (a person decides), and guard 11 where the network stops a
   fight (`heal_fight_stop`). Guards 5, 7, 8's wait, 9 and 10 hold nothing since the operator's
   decision of 2026-11-16 ("Remove all time-based holds"): `heal.findings` says a problem that
   keeps coming back and a fix something keeps undoing instead;
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
         ("guards", "Check many devices at once, and a fight the network stops"),
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


def _config_line_count(program) -> int:
    from modules.nsot.deploy import config_line_count

    return config_line_count(program)


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
        """``{"text", "commit", "state", "words", "lines", "adds", "removes"}``: the committed
        golden and whether it is the approved state (N5). When it departs, *lines* are the exact
        lines it departs by, as `intent_match` gives them (``- x`` on the device and not in
        intent, ``+ x`` in intent and not on the device; masked there, once, for every reader),
        so guard 4's hold can say each line and its way out (C3581; the operator, 2026-11-14:
        "A departure row ... shows the exact lines"). Where the newest measurement stands, that
        is one comparison of this device's golden with its intent, read live: the heal pipeline
        reads live (CLAUDE.md, "Display only")."""
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
        if intent.get("state") == "at_intent":
            return {"text": rec["text"], "commit": entry.get("commit", ""),
                    "state": "at_intent", "words": intent.get("words", ""), "lines": [],
                    "adds": 0, "removes": 0}
        got = intent_match.intent_match(repo, self.network, device, rec["text"])
        lines = list(got.get("lines") or []) if got.get("state") == "differs" else []
        counts = {"lines": lines, "adds": int(got.get("adds") or 0) if lines else 0,
                  "removes": int(got.get("removes") or 0) if lines else 0}
        if intent.get("state") == "departs":
            # The measurement's state stands; the comparison gives its lines.
            return dict({"text": rec["text"], "commit": entry.get("commit", ""),
                         "state": "departs", "words": intent.get("words", "")}, **counts)
        state = {"match": "at_intent", "differs": "departs"}.get(got["state"], "unknown")
        why = intent.get("why") or intent.get("words") or intent.get("state")
        return dict({"text": rec["text"], "commit": entry.get("commit", ""), "state": state,
                     "words": (f"its newest measurement does not stand ({why}); compared now: "
                               f"{intent_match.words(got)}")}, **counts)

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

def restore_source(golden: dict, intended: dict) -> str:
    """The text a restore's lines come from (C3909; the operator, 2026-11-17: "The restore
    targets intent ... when golden and intent disagree, render from intent"): the golden's
    where it is at its intent (as before), else committed intent rendered for the device
    (`Sources.intended`, the render the intersection rule already compares with). The one
    choice, the decision's and the act's, so their programs and hashes agree."""
    if golden.get("state") == "at_intent" and golden.get("text"):
        return golden["text"]
    return intended.get("text") or ""


def program(golden: str, running: str, units: list, removal_ids: list, *, mgmt_ip: str,
            platform: str) -> dict:
    """The heal's exact program and its hash: *golden* is the text the lines come from
    (`restore_source`: the golden at its intent, else committed intent rendered), its own
    lines for each missing or changed unit, merged (`deploy.merge_commands` through the deploy's `_program`), then the
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
        # Kept (the review, 2026-11-17): a Tier 2 kind's own mode on Fixes (Manual when in the
        # fix kinds to propose, else Off) decides, as `propose._stops` judges it at apply.
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


def decide_one(network: str, incident: dict, *, now: float, sources=None, mode=None,
               batch: dict = None) -> dict:
    """The decision for one claimed incident: a record (not yet written) ``{"incident",
    "device", "outcome", "mode", "guard", "words", "outcome_words", "cause", "kind", "tier",
    "units", "program", "program_hash", "removal_ids", "departure", "policy", "person",
    "until", "verify"}``. *cause* is what happened, from the incident's judged triggers and the
    decision's units (`said.cause_of`, C2823: facts first, a hypothesis labelled), or None;
    *words* state it first, then *outcome_words*, what Mercury did or would do."""
    d = _decide_one(network, incident, now=now, sources=sources, mode=mode, batch=batch)
    return said_of(network, incident, d)


def said_of(network: str, incident: dict, d: dict) -> dict:
    """*d*, a decision for *incident* (`_decide_one`'s, or a batch's made from the decision it
    previewed, `heal.batch._as_previewed`, C3865), with its words as `decide_one` states them:
    the cause first, then what Mercury did or would do (``outcome_words``), the classified
    problem and the headline. The one home of a decision's words."""
    from modules.heal import said

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
    # The incident's classified problem, when it has one (G7's err-disabled port): kept on the
    # decision, so its headline says a state problem as one, drawn again from the record.
    from modules.heal import errdisable
    got = errdisable.problem_fields(d.get("device") or "", errdisable.of_record(incident))
    if got:
        d["problem"] = {"condition": got["condition"], "object": got["object"]}
    d["headline"] = said.headline(d, network, incident.get("triggers") or [])
    return d


#: Guard 6's batch (G6, the operator's design of 2026-11-14): the guards a person's approval of
#: the previewed batch resolves for its incidents. Guard 6 (many devices at once) is resolved
#: for that batch; the grace (guard 8) is dropped once approved, unless it found the device
#: unreadable or unjudgeable (a can't-fix stays one). Guard 10 still counts every heal.
BATCH_RESOLVES = (6, 8)
#: What the grace may have said that a batch approval does not drop.
GRACE_KEPT = ("not_checkable", "unreadable")
#: The fields of the decision past guard 6 a guard-6 hold carries for the batch's preview
#: (``beyond``): what the decision would be were guard 6 resolved, with the program it would
#: send and its hash, so the batch card shows the exact program before the press. C3865: with
#: its verify and (``units_masked``, `_beyond`) its units as a record keeps them, so the batch's
#: press makes the heal decision from this hold with no second device read
#: (`heal.batch._as_previewed`); the act reads the device at apply.
BEYOND_FIELDS = ("outcome", "words", "kind", "tier", "program", "program_hash",
                 "removal_ids", "departure", "dangerous", "guard", "verify")


def _resolves(batch, g: dict, incident: dict) -> bool:
    """Whether *batch* (an approval, `heal.batch`, or the preview's own reckoning) resolves
    guard hit *g* for *incident*."""
    if not batch or not g or g.get("guard") not in BATCH_RESOLVES:
        return False
    if g["guard"] == 8:
        return (incident.get("settled") or {}).get("how") not in GRACE_KEPT
    return True


def _beyond(network, incident, *, now, sources, mode) -> dict:
    """The decision were guard 6 resolved for *incident* (the batch's preview, G6): decided as
    in AUTO, so its outcome says whether the batch's press would heal it. Never recorded on its
    own; a failure is said, never raised."""
    try:
        got = _decide_one(network, incident, now=now, sources=sources,
                          mode=dict(mode, mode="auto"), batch={"preview": True})
    except Exception as exc:                          # noqa: BLE001 (the hold stands, said)
        return {"outcome": "unknown", "words": f"the batch's preview could not be made "
                                               f"({type(exc).__name__}: {exc})"}
    out = {k: got.get(k) for k in BEYOND_FIELDS}
    out["units"] = len(got.get("units") or [])
    # Masked by `kinds.masked_unit` as every decision keeps them: no configuration text.
    out["units_masked"] = list(got.get("units") or [])
    return out


def _decide_one(network: str, incident: dict, *, now: float, sources=None, mode=None,
                batch: dict = None) -> dict:
    """`decide_one`'s decision, its words what Mercury did or would do. *batch*: the person's
    approval of guard 6's batch holding this incident (`heal.batch.approve`), or the preview's
    reckoning (``{"preview": True}``): guards 6 and 8 are resolved for it (`BATCH_RESOLVES`)."""
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
    # Another operation holding the device is the act's wait (`act.hold_device`), never a
    # hold of the decision (the operator, 2026-11-17, round 2).
    for g in (guards.g1_kill_switch(mode), guards.g2_mode(mode, halt),
              guards.g3_planned(network, device, now, holder=lambda _n, _d: None)):
        if g:
            return stop(g)
    passed("stops", f"no kill switch, {MODE_WORDS.get(mode.get('mode'), mode.get('mode'))}, no "
                    "halt, no planned work", "approved")
    dev = src.device(device)
    g, golden = _g4(network, device, src, dev)
    if g:
        return stop(g)
    if not golden.get("text"):
        # C3909: no golden to judge the departure against is a failure R1 starts on, never
        # a hold.
        return dict(base, outcome="cant_fix",
                    words=f"no golden of {device} can be read: {golden.get('words') or 'none'}")
    commit = (golden.get("commit") or "")[:10] or "(no commit)"
    passed("approved", (f"the golden {commit} is the approved state: "
                        f"{golden.get('words') or golden.get('state')}"
                        if golden.get("state") == "at_intent" else
                        f"the golden {commit} departs from intent "
                        f"({golden.get('words') or golden.get('state')}): the restore's lines "
                        "come from committed intent"), "guards")
    # The operator, 2026-11-17 (round 2): guard 10 (the decisions store unread) is a wait,
    # never a halt; guards 11 (the fight stop), 12 (the program's size) and 14 (a rolled-back
    # heal) hold nothing: verify and rollback are the safety, and a rolled-back heal is a
    # failure R1 sees.
    try:
        decisions.decisions(network)
    except Exception as exc:
        return dict(base, outcome="deferred", until=now + 60,
                    words=(f"Checked again later: the heal record cannot be read ({exc}); "
                           "the decision waits for it and is made again in a minute"))
    grace_s = float(value(mode, "heal_grace_seconds") or 900)
    got = incidents.read(network)
    # The operator, 2026-11-16: "Remove all time-based holds from self-healing ... Keep guard 4
    # and guard 6 as 'a person decides'". Guards 5 (the topology hold), 7 (a person working),
    # 8's wait and the rates 9 to 11 hold or defer nothing now: each run's own preconditions
    # and verify are the safety, and the findings (`heal.findings`) say a problem that keeps
    # coming back or a fix something keeps undoing. A fight stops a fix only where the network
    # set heal_fight_stop (guard 11, a person's setting, no time).
    # A port problem its classification's device read confirmed (`detect._settle_port`) is
    # judged on that read, as one settled at its golden is: its symptom, not a departure.
    at_golden = base["settled"] in ("at_golden", "confirmed")
    # Guard 11 (the fight stop) holds nothing (the operator, 2026-11-17): the fight finding
    # (`heal.findings`) still says a fix something keeps undoing.
    for g in (_g6(incident, got["incidents"], now, grace_s,
                  value(mode, "heal_max_devices_drifting")),
              guards.g8_grace(incident)):
        if _resolves(batch, g, incident):
            continue
        if g:
            held = stop(g)
            if g["guard"] == 6 and not batch:
                # G6: the hold carries what the batch's press would send for this incident.
                held["beyond"] = _beyond(network, incident, now=now, sources=src, mode=mode)
            return held
    batch_words = ""
    if batch and not batch.get("preview"):
        base["batch"] = {"id": batch.get("id"), "by": batch.get("by"),
                         "hash": batch.get("hash"),
                         **({"named": batch["named"]} if batch.get("named") else {})}
        # C2817: the step's words name no id or hash, and a person by display name only.
        # C3823: a switch-on's batch is named after the switch-on.
        batch_words = (f"many devices at once resolved, and the grace dropped, by "
                       f"{batch['named']}; " if batch.get("named") else
                       f"many devices at once resolved, and the grace dropped, by "
                       f"{batch.get('by_shown') or 'a person'}'s approval of the batch; ")
    passed("guards", batch_words + "nothing holds it", "read")
    if at_golden:
        base["phase"] = "decide"
        symptom = _symptom(incident)
        judged = judged_triggers(incident)
        if base["settled"] == "confirmed":
            # Its port problem, confirmed by the device read that settled it: a can't-fix of
            # configuration (Tier 3), as one settled at its golden is, so the saved fix or AI
            # troubleshooting takes it. Its symptom stores are not read: that read is the
            # problem's own.
            out = {"kind": symptom or "physical", "tier": 3, "units": [], "blocked": None}
            return dict(base, kind=out["kind"], tier=3, outcome="cant_fix",
                        words=_outcome(mode, out, [], [], device)[1])
        # C2750: judged on what its stores read now, never on its triggers' words alone: a
        # symptom read gone is nothing to heal at once (the operator, 2026-11-16: "an incident
        # whose device read finds no problem closes at once on that read, never on a quiet
        # timer"), and no can't-fix row.
        now_state = (src.symptom_now(device, judged)
                     if symptom and hasattr(src, "symptom_now") else "")
        if symptom and now_state == "gone":
            return dict(base, outcome="nothing",
                        words=(f"nothing to heal: every symptom the incident named has cleared "
                               f"by itself at {_hhmm(now)} UTC, nothing to do: {device} is at "
                               "its golden, which matches its intent (each symptom read again "
                               "after it)"))
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
    # No grace (the operator, 2026-11-17): the decision is made on this read, never deferred
    # because the device moved since a grace settled.
    passed("read", f"{device} read: the decision is made on what it holds now", "classify")
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
    if c["tier"] < 3 and not c.get("blocked"):
        from modules.nsot import expected_effects
        from modules.pipeline import dangerous_commands
        from modules.redact import redact_text

        if golden.get("state") != "at_intent":
            # The review of C3909 (HIGH): a whole stanza restored from intent would carry
            # intent-only lines no kind judged (an ACL, a secret, a QoS policy) under Tier 1.
            # Until that restore classifies every line it sends (C3910), a golden departing
            # from intent is no fix of Mercury's own: R1's failure, the AI investigates; never
            # a hold, never a send of unjudged lines.
            return dict(base, tier=3, outcome="cant_fix",
                        words=(f"{device}'s golden departs from its committed intent, and a "
                               "restore to intent that adds lines the golden never held is "
                               "not built yet: no fix of Mercury's own, so the AI "
                               "investigates"))
        prog = program(restore_source(golden, intended), text, c["units"], c["removal_ids"],
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
                        # The one count of a program's lines (`deploy.config_line_count`): a
                        # sub-mode's exit is not a line re-applied.
                        + (f"; the fix {_config_line_count(base['program'])} line(s)"
                           if base["program_hash"] else "")),
           "decide")
    outcome, words = _outcome(mode, c, list(mode.get("kinds_auto") or []),
                              list(mode.get("kinds_propose") or []), device)
    return dict(base, outcome=outcome, words=words)


def _g4(network: str, device: str, src, dev):
    """Guard 4, the approved state, as the decision judges it (its one home: `_decide_one` and
    `guard_holds`): ``(hit, golden)``, *hit* None when it does not hold. C2606, C2608: an
    observe-only device or a host has no approved state Mercury may heal to (held, naming the
    key and where NetBox set it; *golden* None then). C3909 (the operator, 2026-11-17: "remove
    the hold, but don't restore a golden that departs from intent"): a golden that departs
    from intent holds nothing; the restore's lines come from committed intent then
    (`restore_source`)."""
    from modules.heal import guards
    from modules.inventory.management import refusal_for

    why = refusal_for(network, device, what="heal",
                      dev=dev if isinstance(dev, dict) else None)
    if why:
        return guards.hit(4, "held", f"heal off for this device: {why}",
                          {"management": (dev or {}).get("_management", "")
                           if isinstance(dev, dict) else "",
                           "role": (dev or {}).get("role", "")
                           if isinstance(dev, dict) else ""}), None
    return None, src.golden(device, dev)


def guard_holds(network: str, incident: dict, guard, *, now: float = None, sources=None):
    """Whether *guard*, the guard a standing incident's held decision named, still holds
    *incident* now, as the decision judges it: guard 4 (`_g4`) and guard 6 (`_g6`), the guards
    a person resolves that hold anything since the operator's decision of 2026-11-16; its
    `guards.hit`, or None when it no longer holds (any other guard: 9 and the time-based
    holds were retired, so none holds). A read (the golden and intent, no device): the retry
    pass asks it before sending a held incident back for a fresh decision
    (`modules/heal/retry.py`)."""
    from modules.heal import incidents, policy
    from modules.heal.guards import value

    now = time.time() if now is None else float(now)
    device = (incident or {}).get("device") or ""
    if guard == 4:
        # C3909: only a device Mercury changes nothing on still holds (`_g4`).
        src = sources or Sources(network)
        return _g4(network, device, src, src.device(device))[0]
    if guard == 6:
        mode = policy.current(network, now)
        return _g6(incident, incidents.read(network)["incidents"], now,
                   float(value(mode, "heal_grace_seconds") or 900),
                   value(mode, "heal_max_devices_drifting"))
    return None


def _act(network: str, incident: dict, d: dict, now: float) -> None:
    """What the decision does to its incident, after it is recorded."""
    from modules.heal import incidents

    # No decision halts the network (the operator, 2026-11-17: guards 10, 11 and 14 halt
    # nothing); Stop everywhere and Off are the stops.
    if d["outcome"] in ("heal", "propose"):
        return                                   # claimed: H4's or H5's
    if d["outcome"] in ("deferred", "held") and d.get("until"):
        incidents.defer(network, incident["id"], d["until"], d["words"], now,
                        quiet=bool(d.get("quiet")), guard=(d.get("guard") or {}).get("guard"))
        return
    if d["outcome"] in incidents.STANDS:
        # C2813: its cause still stands, so the incident stays open on this decision: a later
        # symptom folds into it, a later trigger of the same departure joins it.
        incidents.stand(network, incident["id"], d, settled=incident.get("settled"), now=now)
        return
    if (incident.get("stood") or {}).get("act"):
        # The review's findings 2 and 5: an incident a heal could not confirm ends only with
        # proof. A re-decision that would close it (halted, nothing to heal) puts it back on
        # its act; nothing to heal asks for Mercury's confirmation read (`act.request_confirm`),
        # which alone closes it, with that read as its proof.
        from modules.heal import act
        incidents.stand(network, incident["id"], None, now=now)
        if d["outcome"] == "nothing":
            act.request_confirm(network, incident["id"], f"decided again: {d['words']}"[:300])
        return
    incidents.close(network, incident["id"], f"{d['outcome']}: {d['words']} (decision "
                                             f"{d['id']})", now)


def end_standing(network: str, incident_id: str, words: str, *, now: float, by: str,
                 read_words: str, fixed: dict = None, also_watching: bool = False) -> dict:
    """Close a STANDING incident (C2813, C2825) because what read its device back found its
    cause gone: a drift run that read the device at its golden after its decision, the detect
    pass reading every symptom it named gone and quiet for the flap window, or the can't-fix
    notice's diagnosis. One decision of nothing to heal is recorded on it (*words*, what read
    it and when, *read_words*), in the decisions and the step log, so History says why it
    closed and its Needs attention item leaves (a later decision of nothing to heal resolves a
    can't-fix, `attention._later_done`). Taken first (`incidents.take_standing`), so a change
    that sent it back to watching meanwhile wins: then nothing is recorded and ``{}`` is
    returned. Returns the decision recorded. *fixed* is the fix whose own device check
    verified it (`detect.verified_fix`: the run, its device and when), kept on the decision and
    on the closed incident (the operator's item 4, 2026-11-15: it closes on the problem's own
    verification, not on an alert clearing). *also_watching*: a watching incident too, closed
    on a device read that found no problem before any decision (the operator, 2026-11-16)."""
    from modules.heal import decisions, incidents, policy

    try:
        inc = incidents.take_standing(network, incident_id, by=by, now=now,
                                      states=("standing", "watching") if also_watching
                                      else ("standing",))
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
    if fixed:
        made["fixed"] = dict(fixed)
    steps = [{"step": "claim", "result": "ok",
              "words": f"the incident on {made['device']} taken by {by}: it stood on its "
                       f"decision ({s.get('outcome') or '?'})"},
             {"step": "read", "result": "ok", "words": read_words}]
    try:
        d = decisions.record(network, made, now)
    except Exception as exc:
        log.error("heal: %s's %s could not be ended (%s): it stands", network, incident_id, exc)
        try:
            incidents.stand(network, incident_id, None, now=now)
        except incidents.Refused as why:          # taken from watching: it stood on nothing
            log.error("heal: %s's %s stays claimed: %s", network, incident_id, why)
        return {}
    incidents.close(network, incident_id, f"nothing: {words} (decision {d['id']})", now,
                    fixed=fixed)
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


#: The decisions a saved self-heal script may fire on (C3696; Gate 1b's review): the heal
#: neither acted (``heal``, ``would_heal``), nor proposed (``propose``), nor was held
#: (``held``, ``halted``, ``off``, ``deferred``), nor found nothing (``nothing``): Mercury's
#: code has no fix for it.
SCRIPT_OUTCOMES = ("cant_fix",)


def script_hold(network: str, incident: dict, *, now: float = None, sources=None,
                batch: bool = False):
    """The heal guard that holds a promoted script's run on *incident*'s device now, as
    `_decide_one` judges each (guard 1 the kill switch, 2 the mode and a halt, 3 planned work,
    4 the device Mercury's to change, 6 many devices at once, for a configuration departure
    only, `_g6`: a record with no ``cause`` of ``change`` is an event, never held by 6), its
    `guards.hit` shape; None when none does. *batch*: the run is one of G6's batch a person
    approved, which resolves guard 6 for it (`BATCH_RESOLVES`). A read. *sources* is kept for
    its callers; no guard here reads it now."""
    from modules.heal import decisions, guards, incidents, policy
    from modules.heal.guards import value
    from modules.inventory.management import refusal_for

    now = time.time() if now is None else float(now)
    del sources
    device = incident.get("device") or ""
    mode = policy.current(network, now)
    try:
        halt = decisions.halted(network)
    except Exception as exc:
        halt = {"unreadable": str(exc)}
    # Another operation holding the device is a wait (the runner's, `command_plan_run.run`),
    # never a hold here (the operator, 2026-11-17, round 2).
    for g in (guards.g1_kill_switch(mode), guards.g2_mode(mode, halt),
              guards.g3_planned(network, device, now, holder=lambda _n, _d: None)):
        if g:
            return g
    why = refusal_for(network, device, what="a saved script")
    if why:
        return guards.hit(4, "held", f"heal off for this device: {why}", {})
    grace_s = float(value(mode, "heal_grace_seconds") or 900)
    # The operator, 2026-11-16: no time-based hold (guards 5, 7, 9 and 10 no longer hold), as
    # in `_decide_one`; C3909: guard 6 holds nothing either (`_g6` is None).
    if batch:
        return None
    g = _g6(incident, incidents.read(network)["incidents"], now, grace_s,
            value(mode, "heal_max_devices_drifting"))
    return g or None


def _g6(incident: dict, all_incidents: list, now: float, grace_s: float, most):
    """Guard 6 for *incident* (`guards.g6_many`, anchored on its opening, `_opened`), or None
    when *incident* is no configuration departure (C3819, the operator, 2026-11-16): guard 6
    counts config departures only (``cause`` ``change``), so it holds only them; an event
    problem (an err-disabled port, port security, a lost stream: any incident whose ``cause``
    is not ``change``, or a record that carries none) is never held by it. The one scope, both
    callers' (`_decide_one`, `script_hold`).

    C3909 (the operator, 2026-11-17: "remove guard 4 and guard 6 holds entirely (mass change,
    etc.)"): guard 6 holds nothing now, for either caller; the batch's hold card it fed is
    unreachable until its removal after the recording."""
    del incident, all_incidents, now, grace_s, most
    return None


def _opened(incident: dict):
    """*incident*'s own opening, guard 6's anchor (C3816), or None (anchored on now) when the
    record carries none."""
    try:
        got = float((incident or {}).get("opened_epoch") or 0)
    except (TypeError, ValueError):
        return None
    return got or None


def run(network: str, *, now: float = None, sources=None, by: str = "heal to intent") -> dict:
    """Decide every ready incident of *network* under its heal lock. ``{"ran", "decided":
    [{"incident", "decision", "outcome"}], "busy", "failed"}``."""
    from modules import filestore
    from modules.heal import decisions, incidents

    now = time.time() if now is None else float(now)
    out = {"ran": False, "network": network, "decided": [], "busy": "", "failed": []}
    decided_records = []
    # The retry pass's incidents (`modules/heal/retry.py`): each carries its retry's id
    # (``retry_pending``), finished here, whichever process decides it: {incident: (id, d)}.
    retried = {}
    try:
        with incidents.HealLock(network, actor="Mercury", trigger=f"the decision ({by})"):
            try:
                ready = incidents.ready(network)
            except filestore.StoreUnreadable as exc:
                return dict(out, failed=[str(exc)])
            for inc in ready:
                claimed = incidents.claim(network, inc["id"], by=by, now=now)
                pending = str(claimed.get("retry_pending") or "")
                try:
                    made = decide_one(network, claimed, now=now, sources=sources)
                    steps, phase = made.pop("steps", []), made.pop("phase", "decide")
                    if pending and steps:
                        # History's decision row says it was a retry and why (its claim step).
                        from modules.heal import retry
                        steps[0] = dict(steps[0], words=(
                            f"{steps[0].get('words') or ''}: tried again, "
                            f"{retry.trigger_words_of(claimed, pending)}"))
                    # Recorded under the one lock G6's batch counts guard 10 under too.
                    with filestore.PathLock(decisions.rate_lock_path(network)):
                        d = decisions.record(network, made, now)
                    _act(network, claimed, d, now)
                    _log_steps(network, dict(d, steps=steps, phase=phase), now)
                    if d["outcome"] == "heal" and not d.get("batch"):
                        # The act starts at once (the operator, 2026-11-16, item 4; C3865: r2's
                        # began 13 s after its decision, behind the pass's other decisions and
                        # scripts). Its own job; a later `act.run` finds it taken.
                        from modules.heal import act
                        try:
                            started = act.start_decided(network, d, by=by)
                        except Exception as start_exc:    # noqa: BLE001 (the next pass's)
                            started = {"failed": f"{type(start_exc).__name__}: {start_exc}"}
                        if not started.get("started"):
                            log.info("heal: %s's heal of %s starts on the next pass: %s",
                                     network, d.get("device"),
                                     started.get("refused") or started.get("failed"))
                except Exception as exc:
                    log.error("heal: %s's decision on %s failed: %s: %s", network,
                              inc["device"], type(exc).__name__, exc)
                    out["failed"].append(f"{inc['device']}: {type(exc).__name__}: {exc}")
                    incidents.defer(network, inc["id"], now + 60,
                                    f"the decision failed ({type(exc).__name__}: {exc}); "
                                    "checked again", now)
                    if pending:
                        retried[inc["id"]] = (pending, {
                            "id": "", "outcome": "failed",
                            "words": f"the decision failed ({type(exc).__name__}: {exc})"})
                    continue
                out["decided"].append({"incident": inc["id"], "decision": d["id"],
                                       "outcome": d["outcome"]})
                if d["outcome"] in SCRIPT_OUTCOMES:
                    decided_records.append(claimed)
                if pending:
                    retried[inc["id"]] = (pending, d)
    except incidents.HealBusy as exc:
        return dict(out, busy=str(exc))
    # C3696: a saved self-heal script whose R4 match an incident's problem holds fires from the
    # decision, under self-healing's mode (`saved_plans.fire_matching`: Dry run records what it
    # would run; a promoted script in Auto runs through the runner on its authority, after the
    # heal guards for its device, `script_hold`), whatever the AI's switch says: only where
    # the heal neither acted nor was held and no code fix exists (`SCRIPT_OUTCOMES`). After
    # the heal lock: a run holds its own device. The problem is classified from the incident
    # as its page resolves it, as the card and the investigation classify it.
    out["scripts"] = []
    from modules import incident_page
    from modules.nsot import saved_plans
    fired = {}

    def fire_on(rec):
        iid = rec.get("id") or ""
        found = incident_page.resolve(network, iid)
        if found.get("found") != "page":
            found = {"incident": rec, "entry": {}}
        # A retry's scripts fire under its key (`saved_plans.fire`'s *retry*): each once
        # for this retry, a run that failed before tried again (the operator, 2026-11-16).
        return saved_plans.fire_matching(network, found, retry=(retried.get(iid) or ("",))[0])

    # Every incident's scripts at once, each run holding its own device, verified and rolled
    # back on its own, a failure stopping no other (the operator, 2026-11-16: "a self-healing
    # batch (switch-on, Fix all, retries) runs every device at once ... no canary device
    # first"); one incident's scripts stay in order (`fire_matching`: one incident, one change).
    from modules.fanout import Failed, read_each
    for rec, got in zip(decided_records, read_each(fire_on, decided_records,
                                                   name="heal-scripts")):
        if isinstance(got, Failed):
            log.error("heal: %s's saved scripts did not fire on %s: %s", network,
                      rec.get("id"), got)
            out["failed"].append(f"saved scripts on {rec.get('id')}: {got.error}")
            continue
        fired[rec.get("id") or ""] = got
        out["scripts"] += got
    if retried:
        from modules.heal import retry
        for iid, (rid, d) in retried.items():
            try:
                retry.finish(network, iid, rid, d, fired.get(iid) or [], now=now)
            except Exception as exc:                  # noqa: BLE001 (said; the decision stands)
                log.error("heal: %s's retry %s on %s was not recorded: %s", network, rid, iid,
                          exc)
                out["failed"].append(f"the retry on {iid}: {exc}")
    if out["decided"]:
        try:
            from modules import invalidation
            invalidation.announce(invalidation.ANNOUNCERS["heal-decide"], by="heal-decide")
        except Exception as exc:
            log.info("heal: %s's decisions recorded, not announced: %s", network, exc)
    out["ran"] = True
    return out
