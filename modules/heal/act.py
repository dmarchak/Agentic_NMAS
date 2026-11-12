"""Act and verify: a heal decision applied as the policy, verified and recorded (board H, part
H4; docs/HEAL_TO_INTENT.md section 4 steps 3 to 5, sections 8 and 11, N9, N12, N13, C2402).

**No second apply path.** A heal is THE plan and THE apply every deploy runs
(`routes.deploy.plan_devices`, `apply_batch`): the nine stages of `pipeline.PipelineRunner`,
the device held through `device_ops` (one operation per device across processes, refused by
name), merge-only against the rendered intent, Mode B for a removal, the pipeline's verify
(QUICK or FULL, `verify_scope.classify`) and its rollback, which undoes what landed and
re-adds a removal's lines from the pre-change read. What a heal adds is said here.

**The steps, each the first that refuses ends it with nothing sent** (`STEPS`):
1. **take** the decision once (`decisions.take`): a second take is refused by name;
2. **stops** again at apply: the kill switch, the mode now AUTO (in dry run, or off, nothing
   is sent), the network marked lab (C2009's guard), the policy's fingerprint the one the
   decision was made under, every unit's kind still allowed AUTO, no halt in force, no planned
   work, and a person who confirmed the policy (the setter is who is accountable);
3. **read** the device again (the capture path's one checked read);
4. **plan against that read**: its units classified again and the program recomputed
   (`decide.program`, the decision's own computation), refused unless its hash is the
   decision's ``program_hash``, naming what moved (the departure, the units, the program's
   size); then THE plan (`plan_devices`) with that read as its capture source, refused unless
   its program is the heal's, byte for byte, it is deployable, and it cuts nothing of
   Mercury's reach;
5. **authorise (C2402, N9)**: every removal carries the policy's words as its stated reason,
   in the hash and the receipt as a person's reason is; any line the CI gate counts dangerous
   (`pipeline.dangerous_commands`) refuses the heal, since no person stated a reason for it;
6. **apply** as the policy (`actor_kind="policy"`, its setter the actor, its commits
   ``Actor-Verified: policy`` through `identity.carried_policy`), with the plan's capture and
   command hashes, so stage 4 compares the device with the heal's read (C78): a device changed
   again since is refused, "the device changed during the heal", and a later read starts over;
7. **after the pipeline verified, the device still held and its save to startup held**
   (``after_verify``, `routes.deploy._settle_after_verify`): (b) intent, each healed unit at
   intent on the read after the change, or what landed is undone; (a) for a removed feature
   on an interface (N13), its effect: the trigger's own source read again within its bound
   (`SYMPTOM_SECONDS`), and a symptom still there rolls it back, its lines re-added;
8. **the golden re-check** ("the documentation, tested"): the device read again
   (`drift_check.check_device`) must be at its new golden, or the heal is partial; then any
   other symptom is read again, the device saved and released. One still there KEEPS the
   heal (rolling back would re-apply the unauthorised change): healed configuration, symptom
   remains, amber. A symptom that cannot be read neither passes nor fails: kept, partial;
9. **record**: `decisions.applied` with the outcome (`OUTCOMES`; ``rolled_back`` halts the
   network, guard 14, and so does a program sent and neither verified nor rolled back), and
   `incidents.close`. The receipt carries the heal (its decision, incident, policy, the person
   whose change it healed and its check after verify) through `apply_batch`'s ``heal``.

**One job per incident** (`run`, `start`): each heal decision is taken at once and run as a
job (`capture_job.start`, kind ``heal``), so the detect runner is never held by an apply.

**The records** (H6, `modules/heal/steplog.py`): before the apply, the steps so far and the
program (masked) and its hash are written to the step log (``started``), and a heal whose row
cannot be written is refused with nothing sent; at the end, its every step, its outcome and
its records (``act``): the golden commit, which reads ``Source: heal_to_intent`` and
``Actor-Verified: policy`` with a ``Heal-Decision:`` trailer; the receipt naming the decision;
the golden re-check; the deterministic change record (`modules/heal/change_record.py`); and the
NetBox journal entry (`modules/heal/journal.py`), each said when it is not made. Each act holds
its decision's mark (`modules/heal/interrupted.py`) from before its take until its outcome is
recorded, so a job that ends first is found, recorded ``interrupted`` and raised in Needs
attention (`run` records them at each pass).

**What it leaves** (H5, H8): `apply_decision` returns the steps it ran (``steps``, each its
name, its result, its words, masked, and its time), its ``records`` and the batch's report. H5's
approved proposal is a different program (intent's router-id and a measured reset), so it
plans its own and reuses the parts: `apply_batch`'s ``capture``, ``after_verify`` and
``heal``, `units_left`, `read_symptom`, `policy_reason`'s shape for its person's reason, and
`decisions.applied` and `incidents.close` as here.
"""

import logging
import time

log = logging.getLogger(__name__)

KIND = "heal"
ANNOUNCER = "heal-act"
#: What a heal changes, announced at its job's end (`invalidation.ANNOUNCERS[ANNOUNCER]`).
DONE_KEYS = ("drift", "goldens", "remote", "baselines", "device_state", "rolled_back")
#: The steps, in order, for the step log (H6) and the manual's How it works page (H10).
STEPS = (("take", "Take the heal decision, once"),
         ("stops", "Check the kill switch, the mode, the stage, the policy and planned work"),
         ("read", "Read the device again"),
         ("plan", "Recompute the program from that read, and compare its hash"),
         ("authorise", "Give each removal the policy's reason; refuse any dangerous line"),
         ("apply", "Apply as the policy, holding the device: the deploy's nine stages"),
         ("intent", "Check each healed unit is at intent"),
         ("symptom", "Read the symptom again (a removed feature's before its save; any "
                     "other once the device is released)"),
         ("saved", "Saved to startup once verified, the device released"),
         ("golden", "Read the device again against its new golden"),
         ("record", "Record the outcome and close the incident"))
#: Each step in two to four words, for its column on the stepper (the operator, 2026-11-11:
#: "short labels ... No full sentences in the step columns"); the long words above are its
#: hover. `{device}` is the run's own.
STEP_LABELS = {"take": "Take decision", "stops": "Check stops", "read": "Read {device}",
               "plan": "Recompute program", "authorise": "Authorise removals",
               "apply": "Apply", "intent": "Check intent", "symptom": "Read symptom",
               "saved": "Save startup", "golden": "Check golden", "record": "Record"}
#: What an applied heal did (`decisions.applied`); ``rolled_back`` and ``failed`` halt, and so
#: does ``interrupted`` once its act had written its program to the step log
#: (`modules/heal/interrupted.py`, H6, which records it for a job that ended first).
OUTCOMES = ("healed", "symptom_remains", "partial", "refused", "rolled_back", "failed",
            "interrupted")
OUTCOME_WORDS = {"healed": "healed and verified",
                 "symptom_remains": "healed configuration; symptom remains",
                 "partial": "healed, partly shown", "refused": "nothing was sent",
                 "rolled_back": "rolled back", "failed": "failed after sending",
                 "interrupted": "interrupted: its job ended before it recorded its outcome"}
#: Each symptom's settle bound, in seconds: about 2.5 times what the symptom needs to clear
#: once the configuration is right. An adjacency: a dead timer (40 s) and two of the routing
#: scrapes the adjacencies reader judges by (a minute apart, `adjacencies.PERSIST_READS`),
#: so 2.5 x 60 s; an alert: the heartbeat's 300 s interval, 2.5 x 300 s. Reasoned from the
#: intervals, not measured end to end (the register's row names the measurement).
#: A duplicate router-id (C2446, R8's "no duplicate router-id logged"): gone once no line is
#: within the reader's quiet time (`adjacency_log.QUIET_SECONDS`, 165 s, 2.5 times the line's
#: measured 66 s repeat) of a read, and the reader reads every 120 s, so 165 s and two reads:
#: 405 s. Reasoned from the repeat and the interval, not measured end to end.
SYMPTOM_SECONDS = {"adjacency": 150, "adjacency_log": 150, "alert": 750,
                   "duplicate_router_id": 405}
#: How often a symptom's source is read again while it waits: a quarter of the shortest bound.
POLL_SECONDS = 30


class Sources:
    """Where the act reads and what it calls, each replaceable in a test. The decision's own
    sources (`decide.Sources`) for the device, its golden, intent, platform and read; THE
    plan and THE apply; the symptom's source; intent and drift's one-device check."""

    def __init__(self, network: str, *, clock=time.time, sleep=time.sleep):
        from modules.heal.decide import Sources as DecideSources

        self.network, self.clock, self.sleep = network, clock, sleep
        self._d = DecideSources(network)

    def device(self, device):
        return self._d.device(device)

    def golden(self, device, dev):
        return self._d.golden(device, dev)

    def intended(self, device, platform):
        return self._d.intended(device, platform)

    def platform(self, device, dev):
        return self._d.platform(device, dev)

    def read(self, dev):
        return self._d.read(dev)

    def intents(self):
        return self._d.intents()

    def host_networks(self):
        return self._d.host_networks()

    def mode(self, now):
        from modules.heal import policy

        return policy.current(self.network, now)

    def planned(self, device, now):
        from modules.heal import guards

        return guards.g3_planned(self.network, device, now)

    def plan(self, device, **kw) -> dict:
        from routes.deploy import plan_devices

        return plan_devices(self.network, [device], **kw)[0]

    def apply(self, device, **kw) -> dict:
        from routes.deploy import apply_batch

        return apply_batch(self.network, **kw)

    def intent_state(self, device, text, platform) -> dict:
        from modules.nsot import intent_match

        got = intent_match.intent_match(self._d.ref().repo_dir, self.network, device, text,
                                        platform)
        return {"state": got.get("state"), "words": intent_match.words(got)}

    def golden_recheck(self, device, by) -> dict:
        from modules import drift_check

        return drift_check.check_device(self.network, device, by)

    def symptom(self, device, triggers, since) -> dict:
        return read_symptom(self.network, device, triggers, since, clock=self.clock,
                            sleep=self.sleep)

    def journal(self, device, dev, decision, outcome, approval=None) -> dict:
        from modules.heal import journal

        return journal.write(self.network, device, dev, decision, outcome, approval=approval)


# ── The symptom (section 4 step 4 (a)) ──────────────────────────────────────────────────────

def symptom_triggers(triggers: list) -> list:
    """The triggers that name a symptom to read again: an adjacency down, a logged adjacency
    drop, a firing alert, a duplicate router-id logged (C2446: R8's verify). A
    configuration change or a drift record names none."""
    return [t for t in triggers or [] if t.get("kind") in SYMPTOM_SECONDS and t.get("source")]


def adjacency_down(value: dict, network: str, devices: list, protocol: str) -> bool:
    """Whether the adjacencies reader's *value* still holds an adjacency down between
    *devices* (every one of them on it) for *protocol* (any, when none was named), on
    *network*. OSPF and OSPFv3 are different protocols: an IPv6 adjacency is its own."""
    want = {d for d in devices if d}
    for e in ((value or {}).get("adjacencies") or {}).values():
        if network and e.get("list") not in ("", None, network):
            continue
        if protocol and (e.get("protocol") or "") != protocol:
            continue
        if want <= set(e.get("devices") or []):
            return True
    return False


def alert_firing(value: dict, device: str, rule: str, interface: str = "") -> bool:
    """Whether the Grafana alerts reader's *value* still holds *rule* firing on *device* (on
    *interface*, when the trigger named one). The episode's key is not compared: a resolve and
    a re-fire is a new key, and the symptom is the same."""
    from modules.evidence_pack import firing

    for i in firing(value or {}):
        if (i.get("rule") or "") != rule:
            continue
        if device and (i.get("device") or "") not in ("", device):
            continue
        labels = i.get("labels") or {}
        if interface and interface not in (labels.get("ifDescr"), labels.get("ifName")):
            continue
        return True
    return False


def duplicate_logged(value: dict, network: str, protocol: str, router_id: str, at: float,
                     since: float) -> bool:
    """Whether the adjacency-log reader's *value* (read at *at*) still holds *router_id*'s
    duplicate logged after *since*, by any device of *network* (C2446, R8's "no duplicate
    router-id logged"): a line within the reader's quiet time of the read
    (`adjacency_log.still_logged`). Any device, not only this one: either router logging it
    means two still hold the id."""
    from modules.readers import adjacency_log as AL

    for g in ((value or {}).get("duplicates") or {}).values():
        if network and g.get("list") not in ("", None, network):
            continue
        if protocol and (g.get("protocol") or "") != protocol:
            continue
        if g.get("router_id") == router_id and AL.still_logged(g, at, since):
            return True
    return False


def _store_for(trigger: dict) -> str:
    """The store a trigger's symptom is read again from: its own source, but a logged drop's,
    which logs events, is read from the adjacencies reader of the same configuration."""
    store = trigger.get("source") or ""
    if trigger.get("kind") == "adjacency_log":
        base, sep, rest = store.partition("@")
        return "adjacencies" + (sep + rest if base == "adjacency-log" else "")
    return store


def judge(trigger: dict, doc: dict, network: str, device: str, since: float) -> str:
    """One trigger's symptom on its store's document: ``stale`` (not read since *since*; or
    a duplicate router-id that could not be looked for: no Loki read, or no id named),
    ``present`` or ``gone``."""
    good = (doc or {}).get("last_good") or {}
    at = float(good.get("read_started") or 0)
    if at <= float(since):
        return "stale"
    value = good.get("value") or {}
    if trigger["kind"] == "duplicate_router_id" and value.get("configured") is False:
        # The adjacency-log reader's value with no Loki configured holds no line because none
        # was read: neither a pass nor a fail, so never "gone".
        return "stale"
    if trigger["kind"] == "duplicate_router_id" and not trigger.get("router_id"):
        # A trigger that names no router-id names nothing to look for in the log (no group the
        # reader makes holds an empty id): neither a pass nor a fail, so never "gone".
        return "stale"
    if trigger["kind"] == "alert":
        present = alert_firing(value, device, trigger.get("rule") or "",
                               trigger.get("interface") or "")
    elif trigger["kind"] == "duplicate_router_id":
        present = duplicate_logged(value, network, trigger.get("protocol") or "",
                                   trigger.get("router_id"), at, since)
    else:
        present = adjacency_down(value, network, [device] + list(trigger.get("related") or []),
                                 trigger.get("protocol") or "")
    return "present" if present else "gone"


def _reader_for(store: str):
    from modules import reader_job

    base = store.split("@", 1)[0]
    for r in reader_job.readers():
        if r.name == base:
            return next((c for c in reader_job.configuration_readers(r) if c.name == store),
                        None)
    return None


def read_symptom(network: str, device: str, triggers: list, since: float, *, clock=time.time,
                 sleep=time.sleep, read=None, request=None) -> dict:
    """The incident's symptoms read again (``{"state", "words", "checks"}``): each trigger's
    store asked to read now, then read until every symptom is gone or its bound passes. *state*
    is ``none`` (no symptom to read), ``gone``, ``present`` or ``unreadable`` (a store that
    could not be read, or not read since the change, within the bound: neither a pass nor a
    fail). ``reads`` is every read it made, in order, as the act's ``symptom`` step keeps them
    (`reads.read_entry`: when, the store asked, gone, still there or unreadable), so the
    heal's own record says "5 reads, 30 s apart, each still down" (the operator, 2026-11-11);
    a reader's store is no device read, so each names no run of the reads store."""
    from modules import reader_job
    from modules.nsot import reads as reads_store

    wanted = symptom_triggers(triggers)
    if not wanted:
        return {"state": "none", "checks": [], "reads": [],
                "words": "the incident named no symptom beyond the configuration"}
    kept = {"reads": []}
    read = read or reader_job.read_cached

    def ask(store):
        reader = _reader_for(store)
        if reader is None:
            return False
        reader_job.request_run(reader, by="heal to intent: the symptom read again")
        return True

    request = request or ask
    bound = max(SYMPTOM_SECONDS[t["kind"]] for t in wanted)
    deadline = clock() + bound
    asked = {}
    while True:
        checks = []
        for t in wanted:
            store = _store_for(t)
            if store not in asked:
                asked[store] = request(store)
            got = read(store)
            state = ("unreadable" if got.get("state") != "ok" else
                     judge(t, got.get("doc"), network, device, since))
            checks.append({"trigger": t.get("words") or t.get("kind"), "store": store,
                           "state": state, "asked": asked[store]})
            reads_store.keep_read(kept, reads_store.read_entry(
                f"the {store} reader's stored value", {"gone": "pass", "present": "fail"}.get(
                    state, "unreadable"),
                f"{t.get('words') or t.get('kind')}: "
                + {"gone": "gone", "present": "still there",
                   "stale": "not read since the change"}.get(state, state),
                at=_iso(clock())))
        states = {c["state"] for c in checks}
        if states == {"gone"}:
            return {"state": "gone", "checks": checks, "reads": kept["reads"],
                    "words": f"the symptom is gone ({len(checks)} read again)"}
        if clock() >= deadline:
            if "present" in states:
                left = [c["trigger"] for c in checks if c["state"] == "present"]
                return {"state": "present", "checks": checks, "reads": kept["reads"],
                        "words": f"the symptom is still there after {bound} s: {left[0]}"}
            why = [c for c in checks if c["state"] != "gone"][0]
            return {"state": "unreadable", "checks": checks, "reads": kept["reads"],
                    "words": (f"the symptom could not be read again within {bound} s "
                              f"({why['store']}: {why['state']}"
                              + ("" if why["asked"] else ", no reader for it runs here")
                              + ")")}
        sleep(POLL_SECONDS)


# ── The checks after verify ─────────────────────────────────────────────────────────────────

def units_left(units: list, text: str) -> list:
    """The healed units NOT at intent on *text* (the read after the change): a line to add
    still missing, or a line to remove still there. Each by its words, never its lines."""
    from modules.heal import kinds

    have = set(kinds._paths(kinds._stored(text)))
    out = []
    for u in units:
        missing = [p for p in u["add"] if (tuple(p[0]), p[1]) not in have]
        stays = [p for p in u["remove"] if (tuple(p[0]), p[1]) in have]
        if missing or stays:
            out.append(kinds.unit_words(u))
    return out


def feature_removed(units: list) -> bool:
    """N13: a unit that removes one feature on one interface, whose verify is the feature's
    effect (the adjacency up), and whose lines are re-added when it is not."""
    return any(u["op"] == "remove" and u["chain"] and u["chain"][0].startswith("interface ")
               and not u.get("stanza") for u in units)


def policy_reason(network: str, policy: dict) -> str:
    """The stated reason every removal of a heal carries (N9; C2402): the policy's words, in
    the hash and the receipt, as a person's reason is. Testimony: who confirmed the policy and
    their own reason, never a judgement of it."""
    return (f"heal to intent on {network}: the line was added outside intent, removed under "
            f"the policy {policy.get('fingerprint')} confirmed by {policy.get('by')} "
            f"({policy.get('reason') or 'no reason recorded'})")


def _moved(decision: dict, units: list, prog: dict, departure: str) -> str:
    """What moved between the decision and the apply, both sides named."""
    parts = []
    if departure != (decision.get("departure") or ""):
        parts.append(f"the departure (decided {decision.get('departure') or 'none'}, now "
                     f"{departure or 'none: at its golden'})")
    decided = sorted(u.get("id") or "" for u in decision.get("units") or [])
    now = sorted(u.get("id") or "" for u in units)
    if decided != now:
        parts.append(f"the units (decided {len(decided)}: {', '.join(decided) or 'none'}; now "
                     f"{len(now)}: {', '.join(now) or 'none'})")
    if len(decision.get("program") or []) != len(prog["commands"]):
        parts.append(f"the program's size (decided {len(decision.get('program') or [])} "
                     f"line(s), now {len(prog['commands'])})")
    return "; ".join(parts) or "the program's lines, though its size and units are the same"


# ── The records an act leaves (H6) ──────────────────────────────────────────────────────────

def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _records(network: str, decision: dict, result: dict, src, held: dict, now: float,
             approval: dict = None) -> dict:
    """What the step log's ``act`` row keeps beside the steps (section 8, board H artboard C):
    the golden commit, the receipt (it names the decision), the golden re-check, the change
    record (deterministic, `modules/heal/change_record.py`) and the NetBox journal entry
    (`modules/heal/journal.py`). Each is said, never raised: the heal's outcome is recorded
    already, and a record that could not be made says why. *approval* (H5): the person who
    approved a Tier 2 proposal, named in the change record and the journal entry."""
    from modules.heal import change_record, journal

    device = decision["device"]
    report = result.get("report") or {}
    commit = (report.get("golden") or {}).get("commit") or ""
    recheck = next((s for s in reversed(result["steps"]) if s.get("step") == "golden"), {})
    out = {"golden": commit,
           "receipt": (f"the deploy receipt naming decision {decision['id']}" if report
                       else "none: nothing reached the deploy's apply"),
           "recheck": (f"{recheck.get('result')}: {recheck.get('words')}" if recheck
                       else "not read: the heal did not reach its golden re-check")}
    pol = decision.get("policy") or {}
    until = ""
    try:
        mode = src.mode(now)
        if mode.get("fingerprint") == pol.get("fingerprint"):
            until = mode.get("until") or ""
    except Exception as exc:
        log.info("heal: %s's policy could not be read for the change record: %s", network, exc)
    out["change_record"] = change_record.build(
        network, decision, result, host=device, platform=held.get("platform") or "",
        prog=held.get("prog"), read=held.get("read") or "", entry=held.get("entry") or {},
        authorise=held.get("authorise") or [], policy=pol,
        golden_before=held.get("golden_before") or "", golden_commit=commit, until=until,
        at=_iso(now), approval=approval)
    write = getattr(src, "journal", None)
    approved = {"approval": approval} if approval else {}
    try:
        out["journal"] = (write(device, held.get("dev") or {}, decision, result["outcome"],
                                **approved)
                          if write is not None else
                          journal.write(network, device, held.get("dev") or {}, decision,
                                        result["outcome"], **approved))
    except Exception as exc:
        log.error("heal: %s's journal entry for %s failed: %s", network, device, exc)
        out["journal"] = {"state": "failed", "id": None,
                          "words": f"the write failed: {type(exc).__name__}: {exc}"}
    return out


# ── The act ─────────────────────────────────────────────────────────────────────────────────

def _incident(network: str, incident_id: str) -> dict:
    from modules.heal import incidents

    got = incidents.read(network)
    return next((i for i in got.get("incidents") or [] if i.get("id") == incident_id), {})


def _stops(src, network: str, decision: dict, now: float) -> str:
    """Why nothing may be sent now, or ``""``: section 6's stops judged again at apply."""
    from modules.heal import decisions, policy
    from modules.sdn import modes as sdn_modes

    mode = src.mode(now)
    pol = decision.get("policy") or {}
    if (mode.get("stopped") or {}).get("stopped"):
        return f"self-healing is stopped everywhere: {mode['stopped'].get('words')}"
    if mode.get("mode") != "auto":
        return (f"the mode is {policy.MODE_WORDS.get(mode.get('mode'), mode.get('mode'))} now "
                f"({mode.get('words')}), and only AUTO sends a heal")
    stage = (mode.get("stage") or {}).get("stage")
    if stage != sdn_modes.AUTO_STAGE:
        return (f"{network} is marked {stage or 'nothing'}, not {sdn_modes.AUTO_STAGE}, and AUTO "
                "heals only on a network marked lab (C2009's guard)")
    if mode.get("fingerprint") != pol.get("fingerprint"):
        return (f"the policy moved since the decision (decided under {pol.get('fingerprint')}, "
                f"now {mode.get('fingerprint')})")
    allowed = set(mode.get("kinds_auto") or [])
    kinds = sorted({u.get("kind") for u in decision.get("units") or []})
    off = [k for k in kinds if k not in allowed]
    if off:
        return (f"{', '.join(off)} {'is' if len(off) == 1 else 'are'} no longer allowed AUTO "
                f"(allowed now: {', '.join(sorted(allowed)) or 'none'})")
    try:
        halt = decisions.halted(network)
    except Exception as exc:
        return f"whether {network} is halted cannot be read ({exc}), and a halt unread holds"
    if halt.get("id"):
        return f"{network}'s policy is halted by guard {halt.get('guard')}: {halt.get('words')}"
    g = src.planned(decision["device"], now)
    if g:
        return f"guard 3, planned work: {g['words']}"
    if not pol.get("by"):
        return "no person is recorded as having confirmed the policy, so nobody is accountable"
    return ""


def act_one(network: str, decision_id: str, *, now: float = None, sources=None,
            by: str = "heal to intent") -> dict:
    """Take *decision_id* once, then apply it (`apply_decision`), its mark held from before the
    take until its outcome is recorded (`interrupted.Mark`, H6)."""
    from modules.heal import decisions, interrupted

    now = time.time() if now is None else float(now)

    def refused(words):
        return {"decision": decision_id, "outcome": "", "words": words, "steps": [
            {"step": "take", "result": "refused", "words": words}], "sent": False}

    try:
        mark = interrupted.Mark(network, decision_id, by=by).acquire()
    except interrupted.Busy as exc:
        return refused(str(exc))
    try:
        try:
            taken = decisions.take(network, decision_id, by=f"{by}: the apply", now=now)
        except decisions.Refused as exc:
            return refused(str(exc))
        return _guarded(network, taken, lambda: _apply_for(network, taken, now=now,
                                                           sources=sources))
    finally:
        mark.release()


def _apply_for(network: str, decision: dict, *, now: float = None, sources=None) -> dict:
    """A taken decision's act: an action's (19.4, H20: the port bounce and the OSPF reset
    through it, `bounce.apply`; H21: the BGP session clear, `session_clear.apply`), or a heal's
    (`apply_decision`). One taker (`run`), one mark, one record, whichever it is."""
    from modules.heal import bounce, session_clear

    if (decision.get("action") or {}).get("kind") in bounce.KINDS:
        return bounce.apply(network, decision, now=now)
    if (decision.get("action") or {}).get("kind") in session_clear.KINDS:
        return session_clear.apply(network, decision, now=now)
    return apply_decision(network, decision, **({"now": now} if now is not None else {}),
                          sources=sources)


def _guarded(network: str, decision: dict, work):
    """*work* (the act), its raising recorded in the step log (``raised``, H6) before it
    propagates, so the interrupted heal it leaves says why (`interrupted.reap`)."""
    from modules.heal import steplog

    try:
        return work()
    except Exception as exc:
        try:
            steplog.record_raised(network, decision, f"{type(exc).__name__}: {exc}")
        except Exception as again:
            log.error("heal: %s's raised act %s is not in the step log: %s", network,
                      decision.get("id"), again)
        raise


def apply_decision(network: str, decision: dict, *, now: float = None, sources=None,
                   actor_kind: str = "policy") -> dict:
    """Apply one taken heal decision, verify it and record it (the module's steps 2 to 9):
    ``{"decision", "device", "outcome", "words", "steps", "sent", "report"}``."""
    from modules import identity, pipeline
    from modules.heal import decide, decisions, incidents, kinds, steplog
    from modules.nsot import authorisation
    from modules.redact import redact_text

    now = time.time() if now is None else float(now)
    src = sources or Sources(network)
    device = decision["device"]
    pol = decision.get("policy") or {}
    setter = pol.get("by") or ""
    # Board E2a: the words name the policy's setter by display name; the identity is kept
    # beside them, in its own field (`policy_by`), on each row and each step that names them.
    via = steplog.policy_words("heal to intent", setter)
    setter_shown = identity.display_name(setter) if setter else ""
    by_field = {"policy_by": setter} if setter else {}
    steps = [dict({"step": "take", "result": "ok", "words": f"taken by {via}"}, **by_field)]
    # What the records need once the act ends (H6: the change record, the journal entry), as
    # each becomes known.
    held = {"dev": {}, "prog": None, "read": "", "entry": {}, "authorise": [], "platform": "",
            "golden_before": ""}

    # The run's own steps, live (the operator, 2026-11-11: "every state shown must be the
    # run's real current step"): this list is what the heal's card and the In progress list
    # read while the job runs (`op_progress.attach`), and what the step log keeps at its end.
    step, begin = live_steps(steps, STEPS, decision["id"], STEP_LABELS, device)

    def symptom_reads(s):
        """The symptom's reads, under its step (`read_symptom`'s ``reads``); none, no key."""
        return {"reads": list(s["reads"])} if s.get("reads") else {}

    def finish(outcome, words, *, sent=False, report=None):
        step("record", outcome, f"{OUTCOME_WORDS[outcome]}: {words}")
        try:
            decisions.applied(network, decision["id"], outcome, by=via, words=words, now=now)
            if outcome == "failed":
                decisions.halt(network, guard=14, name="a heal sent and not verified",
                               words=f"the heal of {device} ({decision['id']}) failed after "
                                     f"sending and was not rolled back: {words}",
                               operands={"decision": decision["id"], "device": device},
                               now=now)
        except Exception as exc:
            log.error("heal: %s's outcome on %s was not recorded: %s", network, device, exc)
        try:
            incidents.close(network, decision["incident"],
                            f"{outcome}: {words} (decision {decision['id']})", now)
        except Exception as exc:
            log.error("heal: %s's incident %s was not closed: %s", network,
                      decision.get("incident"), exc)
        log.info("heal: %s on %s: %s: %s", network, device, outcome, words)
        result = {"decision": decision["id"], "device": device, "outcome": outcome,
                  "words": redact_text(words), "steps": steps, "sent": sent, "report": report}
        result["records"] = _records(network, decision, result, src, held, now)
        try:
            steplog.record_act(network, decision, result, by=via, policy_by=setter, now=now)
            result["records"]["step_log"] = "written"
        except Exception as exc:
            log.error("heal: %s's act on %s is not in the step log: %s", network, device, exc)
            result["records"]["step_log"] = f"not written: {type(exc).__name__}: {exc}"
        return result

    def refuse(name, words):
        step(name, "refused", words)
        return finish("refused", f"{words}. Nothing was sent")

    why = _stops(src, network, decision, now)
    if why:
        return refuse("stops", why)
    step("stops", "ok", "AUTO on a network marked lab, the policy decided under, nothing held")

    dev = src.device(device)
    begin("read", f"reading {device} again")
    text, error = src.read(dev)
    if not text:
        return refuse("read", f"the read of {device} at apply could not be made ({error})")
    step("read", "ok", f"{device} read again")
    held.update(dev=dev, read=text)

    golden = src.golden(device, dev)
    held["golden_before"] = golden.get("commit") or ""
    if golden.get("state") != "at_intent" or not golden.get("text"):
        return refuse("plan", f"{device}'s golden is not at its intent now ("
                              f"{golden.get('words') or golden.get('state')})")
    platform = src.platform(device, dev)
    intended = src.intended(device, platform)
    if not intended.get("text"):
        return refuse("plan", f"committed intent cannot be rendered: {intended.get('why')}")
    inc = _incident(network, decision["incident"])
    # C2839: classed at apply as it was decided, the network's answer read again (a no since
    # makes a security_revert unit Tier 2, refused below as not the decision's tier).
    c = kinds.classify(golden["text"], text, intended["text"], platform=platform,
                       mgmt_ip=dev.get("ip", ""), related=bool(inc.get("related")),
                       revert=decide.revert_scope(src.mode(now), inc))
    prog = decide.program(golden["text"], text, c["units"], c["removal_ids"],
                          mgmt_ip=dev.get("ip", ""), platform=platform)
    from modules.drift_check import departure, drift_diff

    dep = departure(drift_diff(golden["text"], text, device))
    if prog["hash"] != decision.get("program_hash"):
        return refuse("plan", (f"the program recomputed from the read at apply is not the one "
                               f"decided (decided {decision.get('program_hash')}, now "
                               f"{prog['hash']}): {_moved(decision, c['units'], prog, dep)}; "
                               "a later read starts over"))
    if prog["refused"] or c.get("blocked") or c["tier"] != 1:
        return refuse("plan", f"the program refuses a unit now: "
                              f"{(prog['refused'] or [{}])[0].get('reason') or c.get('blocked')}")
    step("plan", "ok", f"the program recomputed from the read: {len(prog['commands'])} line(s), "
                       f"hash {prog['hash']}, the decision's")
    held.update(prog=prog, platform=platform)

    dangerous = pipeline.dangerous_commands(prog["commands"])
    if dangerous:
        return refuse("authorise", (
            f"the program holds {len(dangerous)} line(s) the CI gate counts dangerous ("
            + "; ".join(authorisation.key(d) for d in dangerous[:3])
            + "), and a heal sends none: only a removal carries the policy's words as its "
              "stated reason (N9, C2402)"))
    reason = policy_reason(network, pol)
    authorise = [{"line": k, "reason": reason} for k in prog["keys"]]
    held["authorise"] = authorise
    step("authorise", "ok", (f"{len(authorise)} removal(s), each with the policy's words as its "
                             "stated reason" if authorise else "nothing that needs a reason"))

    capture = {device: {"text": kinds._stored(text), "intended": prog["fragment"]}}
    plan_kw = {"authorise": {device: authorise}, "remove": {device: list(c["removal_ids"])},
               "capture": capture}
    entry = src.plan(device, **plan_kw)
    held["entry"] = entry
    if entry.get("refused") or entry.get("error"):
        return refuse("plan", f"the deploy's plan refused it: "
                              f"{entry.get('refused') or entry.get('error')}")
    if not entry.get("deployable", True) or entry.get("blocking_reasons"):
        return refuse("plan", "the deploy's plan refused it: "
                              + "; ".join(entry.get("blocking_reasons") or ["not deployable"]))
    if list(entry.get("commands") or []) != prog["commands"]:
        return refuse("plan", (f"the deploy's plan ({len(entry.get('commands') or [])} line(s)) "
                               f"is not the heal's program ({len(prog['commands'])} line(s)): "
                               "what is decided is what is sent, byte for byte"))
    if entry.get("authorisation_ok") is False:
        return refuse("authorise", f"the plan's authorisation check refused it: "
                                   f"{entry.get('authorisation_error')}")
    lost = (entry.get("expected_effects") or {}).get("reach_lost") or {}
    if lost and (lost.get("state") != "known" or lost.get("cut")):
        return refuse("plan", ("the fix would cut Mercury's path ("
                               f"{', '.join(lost.get('cut') or []) or lost.get('why')}), and a "
                               "change to that path needs a repair route independent of it"))

    applied_at = {"t": now}

    def after_verify(host, result, ctx):
        post = ((result.get("golden_pending") or [{}])[0] or {}).get("config_text") or ""
        left = units_left(c["units"], post) if post else ["no read after the change"]
        state = src.intent_state(device, post, platform) if post else {
            "state": "unknown", "words": "no read after the change"}
        record = {"intent": {"left": left, **state}}
        if left:
            step("intent", "failed", f"{len(left)} unit(s) not at intent: {left[0]}")
            return {"rollback": (f"{len(left)} healed unit(s) not at intent after the change "
                                 f"({left[0]}), so what landed was undone"), "record": record}
        step("intent", "ok", f"each healed unit at intent; intent: {state['words']}")
        if not feature_removed(c["units"]):
            # Any other symptom decides no rollback, so it is read once the device is saved
            # and released (`_judge`), never while it is held.
            return {"rollback": "", "record": record}
        s = src.symptom(device, inc.get("triggers") or [], applied_at["t"])
        record["symptom"] = {"state": s["state"], "words": s["words"]}
        step("symptom", s["state"], s["words"], **symptom_reads(s))
        if s["state"] == "present":
            return {"rollback": (f"removing the feature did not clear its symptom ({s['words']}), "
                                 "so its lines were put back (N13)"), "record": record}
        return {"rollback": "", "record": record}

    facts = {"decision": decision["id"], "incident": decision.get("incident"),
             "kind": decision.get("kind"), "mode": "auto",
             "policy": {"fingerprint": pol.get("fingerprint"), "by": setter,
                        "reason": pol.get("reason") or ""},
             "person": dict(decision.get("person") or {}), "program_hash": prog["hash"]}
    # Section 4: the program and its hash are written to the step log BEFORE anything is sent,
    # so a heal whose job ends mid-apply leaves what it was sending (H6).
    try:
        steplog.record_started(network, decision, steps + [{
            "step": "apply", "result": "running", **by_field,
            "words": f"as the policy set by {setter_shown}, holding {device}"}],
            [redact_text(x) for x in prog["commands"]], prog["hash"], by=via,
            policy_by=setter, now=now)
    except Exception as exc:
        return refuse("apply", (f"the program could not be written to the step log before it "
                                f"is sent ({type(exc).__name__}: {exc}), and a heal sends "
                                "nothing it has not recorded"))
    step("apply", "running", f"as the policy set by {setter_shown}, holding {device}",
         **by_field)
    with identity.carried_policy(setter, pol.get("fingerprint") or ""):
        report = src.apply(
            device, confirmations={device: entry.get("capture_hash")},
            command_hashes={device: entry.get("command_hash")}, actor=setter,
            actor_kind=actor_kind, stop_at_first=True, after_verify=after_verify,
            heal={device: facts}, hold_detail=via, **plan_kw)
    r = next((x for x in report.get("results") or [] if x.get("device") == device), {})

    def symptom():
        begin("symptom", "reading the symptom again, until it is gone or its bound passes",
              wait_s=symptom_bound(inc.get("triggers") or []), bound=True)
        s = src.symptom(device, inc.get("triggers") or [], applied_at["t"])
        step("symptom", s["state"], s["words"], **symptom_reads(s))
        return s

    return _judge(device, r, report, src, via, step, finish, symptom, begin=begin)


def symptom_bound(triggers: list) -> int:
    """The longest the symptom read waits for *triggers* (`read_symptom`'s own bound: the
    largest of `SYMPTOM_SECONDS` among the symptoms named), or 0 when none is named."""
    return max((SYMPTOM_SECONDS[t["kind"]] for t in symptom_triggers(triggers)), default=0)


def live_steps(steps: list, declared, run_id: str = "", labels: dict = None,
               device: str = ""):
    """``(step, begin)`` over *steps*, a run's own list: `step(name, result, words)` records a
    step as before (*more* kept on it: the reads a step made, `reads.read_entry`);
    `begin(name, words, wait_s=None, bound=False)` records one that takes time
    as ``running`` the moment it starts (with ``began``, and its declared wait: a fixed length,
    or with *bound* the longest it waits), and that step's own `step` then replaces it, keeping
    when it began. So the recorded list ends as it always did, and while the run goes on its
    newest step is the one it is in. Inside a job the list is the job's own
    (`op_progress.attach`, with the operation's short *labels* for *device*): each step
    written is announced. Used by a heal's act and by an approved proposal's."""
    from modules import op_progress, run_stepper
    from modules.redact import redact_text

    op_progress.attach(declared, steps, run=run_id,
                       labels=run_stepper.labels_for(labels, device=device))

    def begin(name, words, *, wait_s=None, bound=False):
        at = _iso(time.time())
        steps.append(dict({"step": name, "result": "running", "words": redact_text(words),
                           "at": at, "began": at},
                          **({"wait_s": wait_s, "wait_bound": bool(bound)} if wait_s else {})))
        op_progress.moved()

    def step(name, result, words, **more):
        ended = dict({"step": name, "result": result, "words": redact_text(words),
                      "at": _iso(time.time())}, **more)
        last = steps[-1] if steps else {}
        if last.get("step") == name and last.get("result") == "running" and last.get("began"):
            # The step `begin` opened: ended in place, with when it began and what it waited.
            steps[-1] = dict(ended, **{k: last[k] for k in ("began", "wait_s", "wait_bound")
                                       if k in last})
        else:
            steps.append(ended)
        op_progress.moved()

    return step, begin


def _judge(device, r, report, src, via, step, finish, symptom, begin=None):
    """The outcome of the apply, the golden re-check, the symptom (when the check after verify
    did not already read it), and the record."""
    from modules.nsot import receipts
    from modules.nsot.deploy import DEPLOYED, SKIPPED_DRIFTED

    outcome = r.get("outcome") or "refused"
    if outcome == SKIPPED_DRIFTED:
        step("apply", "refused", r.get("reason") or "")
        return finish("refused", ("the device changed during the heal: "
                                  f"{r.get('reason') or 'stage 4 found it moved'}; a later read "
                                  "starts over. Nothing was sent"), report=report)
    if outcome != DEPLOYED:
        sent = receipts.was_sent(r)
        step("apply", outcome, r.get("reason") or "")
        if not sent:
            return finish("refused", f"{r.get('reason') or outcome}. Nothing was sent",
                          report=report)
        state = (r.get("rollback_outcome") or {}).get("state") or ""
        if r.get("rolled_back"):
            return finish("rolled_back", (f"{r.get('reason') or 'verify failed'}; the rollback: "
                                          f"{state or 'ran'}"), sent=True, report=report)
        return finish("failed", f"{r.get('reason') or outcome}; nothing was rolled back",
                      sent=True, report=report)
    saved = r.get("saved_startup") or {}
    if saved.get("held"):
        # C2701: verify did not pass, so the pipeline held the save for a person.
        why = saved.get("why") or "no cause recorded"
        step("saved", "partial", f"NOT saved to startup, held: verify did not pass ({why})")
        return finish("partial", (f"healed, its verify did not pass ({why}), and its save to "
                                  "startup is held for a person: a reload returns the device "
                                  "to before the heal"), sent=True, report=report)
    if saved and not saved.get("ok"):
        step("saved", "partial", f"verified, NOT saved to startup: {saved.get('error')}")
        return finish("partial", (f"healed and verified, and NOT saved to startup "
                                  f"({saved.get('error') or 'not saved'}): a reload loses it"),
                      sent=True, report=report)
    step("saved", "ok", "sent, verified by the pipeline, and saved to startup")
    golden = report.get("golden") or {}
    if not golden.get("commit"):
        step("golden", "failed", golden.get("error") or golden.get("reason") or "no commit")
        return finish("partial", ("healed, and the golden was not committed ("
                                  f"{golden.get('error') or golden.get('reason') or 'no commit'}"
                                  "): the documentation is not shown true"), sent=True,
                      report=report)
    if begin is not None:
        begin("golden", f"reading {device} again against its new golden")
    try:
        again = src.golden_recheck(device, via)
    except Exception as exc:
        again = {"state": "unknown", "error": f"{type(exc).__name__}: {exc}"}
    if again.get("state") != "clean":
        step("golden", "failed", f"read again: {again.get('state')} {again.get('error') or ''}")
        return finish("partial", (f"healed, golden {golden['commit'][:10]} committed, and the "
                                  f"device read again is not at it ({again.get('state')}"
                                  + (f": {again['error']}" if again.get("error") else "")
                                  + "): the documentation is not shown true"), sent=True,
                      report=report)
    # Lab 10's "documentation is updated and tested", said where it happened: the golden is
    # the device's documentation of record; it was committed only after Mercury's config check
    # passed (`repo.commit`), the configuration repository's CI runs that check again on its
    # push, and the device read again matches it.
    step("golden", "ok", (f"documentation updated and tested: golden {golden['commit'][:10]} "
                          "committed after Mercury's config check passed (the configuration "
                          "repository's CI runs the same check on its push); the device read "
                          "again matches it"))
    symptom = ((r.get("heal") or {}).get("symptom") or {}) or symptom()
    if symptom.get("state") == "present":
        return finish("symptom_remains", (f"configuration at intent, and {symptom['words']}: "
                                          "configuration was not the whole cause"), sent=True,
                      report=report)
    if symptom.get("state") == "unreadable":
        return finish("partial", f"configuration at intent, and {symptom['words']}", sent=True,
                      report=report)
    return finish("healed", (f"healed and verified, golden {golden['commit'][:10]} committed, "
                             f"at its golden when read again; {symptom.get('words') or ''}")
                  .rstrip("; "), sent=True, report=report)


# ── The runner's step: one job per incident ─────────────────────────────────────────────────

def start(network: str, decision: dict, sources=None) -> str:
    """Run one taken heal decision as a job (`capture_job.start`, kind ``heal``), its setter
    the actor, announcing what a heal changes at its end. Returns the job's id. The mark `run`
    took for the decision (`interrupted.hold`) is released once the job's outcome is recorded,
    or it raised (H6)."""
    from modules.heal import interrupted
    from modules.nsot import capture_job

    setter = (decision.get("policy") or {}).get("by") or "heal to intent"

    def work(_job):
        try:
            return {"ok": True, "result": _guarded(network, decision, lambda: _apply_for(
                network, decision, sources=sources))}
        finally:
            interrupted.release(network, decision["id"])

    # Its card (the operator, 2026-11-11: "every operation and heal ends with a visible
    # outcome on its card and under 'Finished'"): the device's page reopens it, and the In
    # progress list keeps its outcome until each person opens it (`heal.run_card`).
    return capture_job.start(network, f"healing {decision['device']}", setter, work, kind=KIND,
                             announce_keys=DONE_KEYS, announcer=ANNOUNCER,
                             device=decision["device"], card="heal_run")


def run(network: str, *, now: float = None, starter=None, by: str = "heal to intent") -> dict:
    """Each heal decision of *network* not yet taken (`decisions.to_apply`), taken once here
    and started as its own job (*starter*, `start` unless given). ``{"network", "started":
    [{"decision", "job"}], "refused", "failed", "interrupted"}``.

    First, each heal whose job ended before it recorded its outcome is recorded
    (`interrupted.reap`, H6), so its incident is closed and Needs attention raises it. Each
    decision's mark (`interrupted.hold`) is taken BEFORE it is taken, so a taken heal with no
    outcome and no mark held is one whose job ended."""
    from modules.heal import decisions, incidents, interrupted

    now = time.time() if now is None else float(now)
    out = {"network": network, "started": [], "refused": [], "failed": [], "interrupted": []}
    reaped = interrupted.reap(network, now=now, by=by)
    out["interrupted"] = [r["decision"] for r in reaped["reaped"]]
    out["failed"] += reaped["failed"]
    if out["interrupted"]:
        try:
            from modules import invalidation
            invalidation.announce(invalidation.ANNOUNCERS[ANNOUNCER], by=ANNOUNCER)
        except Exception as exc:
            log.info("heal: %s's interrupted heals recorded, not announced: %s", network, exc)
    try:
        pending = decisions.to_apply(network)
    except Exception as exc:
        return dict(out, failed=out["failed"] + [f"{network}'s heal decisions cannot be read: "
                                                 f"{exc}"])
    for d in pending:
        try:
            interrupted.hold(network, d["id"], d.get("device") or "", by)
        except (interrupted.Busy, OSError) as exc:
            out["refused"].append(str(exc))
            continue
        try:
            taken = decisions.take(network, d["id"], by=f"{by}: the apply", now=now)
        except decisions.Refused as exc:
            interrupted.release(network, d["id"])
            out["refused"].append(str(exc))
            continue
        try:
            job = (starter or start)(network, taken)
        except Exception as exc:
            log.error("heal: %s's heal of %s could not start: %s", network, d["device"], exc)
            words = f"its job could not start ({type(exc).__name__}: {exc}). Nothing was sent"
            decisions.applied(network, d["id"], "refused", by=by, words=words, now=now)
            incidents.close(network, d["incident"], f"refused: {words} (decision {d['id']})",
                            now)
            interrupted.release(network, d["id"])
            out["failed"].append(f"{d['device']}: {type(exc).__name__}: {exc}")
            continue
        out["started"].append({"decision": d["id"], "job": job})
    return out
