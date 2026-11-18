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
3. **read** the device again (the capture path's one checked read), holding it from here to
   the end of its tail (`hold_device`: another operation's hold is a declared wait, never an
   outcome); this read is the capture the deploy's stage 4 compares a read again before the
   push with (`PipelineContext.pre_read`; C3967, the operator's decision 16, 2026-11-18: a
   change made from outside between the two is refused, nothing sent);
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
   The read after the change is the healed units' interface sections, on the push's own
   session, where every line of the program sits in one (`pipeline.tail_sections`), else the
   whole configuration, said; the units' own check decides, and no whole-device compare with
   intent is shown as proof (it decides nothing: a departure elsewhere is its own incident).
   **Fixed rests on verify** (the operator's decisions (a) and (b), 2026-11-16, C3864 and
   C3865): where nothing is left to wait for (no symptom named, or a cosmetic heal's one read of
   its store) the outcome is recorded and the incident closed there (`declare`), and the
   **tail** follows under it (`TAIL_STEPS`, `pipeline.run_tail`): the save to startup
   ("Saving to startup…" → "Saved"), the whole configuration read and the golden committed from
   it ("Committing the golden…" → "Golden committed"), and the device read again, its own read
   (`Sources.read_at_golden`, never the network's drift check), against that golden. A tail
   failure or mismatch flags the incident (`tail_of`: "r2 fixed, but its save to startup
   failed: ..."), never leaves it silently Fixed and never changes its outcome. A heal whose
   symptom is waited on runs the tail before that wait (the device is never held through it
   nor left unsaved), and still only flags;
8. **the golden re-check** ("the documentation, tested"): the device read again, its own read,
   against its new golden; then any other symptom is read again, the device released. One
   still there KEEPS the
   heal (rolling back would re-apply the unauthorised change): healed configuration, symptom
   remains, amber. A symptom that cannot be read neither passes nor fails: kept, partial.
   A heal that re-applies the heartbeat applet (C3164, `restored_heartbeat`: decided from
   intent's parse and the heartbeat check's own population) has the heartbeat as a symptom
   too: its next heartbeat in Coverage's stored arrivals, within `heartbeat_bound`; none by
   then is symptom remains. A heal whose every line is cosmetic (`readback_only`, R3: a
   description, an alias, a banner, SNMP's location or contact, the logging buffer) is
   verified by its read-back: its symptom, which no such line can clear or cause, is read
   once from its store's last read and never waited on (``once``), and the step says so
   ("descriptions only: read back, 2 s");
9. **record**: `decisions.applied` with the outcome (`OUTCOMES`; ``rolled_back`` halts the
   network, guard 14, and so does a program sent and neither verified nor rolled back),
   stamped when it is recorded (C3871), and its incident (`outcome_on_incident`, C3870: the
   operator, 2026-11-16, "Only 'healed' closes an incident"): healed closes it with its verify
   as proof; any other outcome leaves it open, standing on the act, its outcome said, so R1
   sees it (`fixit.auto.failures`) and the retry policy takes it once per trigger
   (`retry._in_population`); a tail that fails after Fixed reopens it (`reopen_on_tail`).
   Before any AI call on such a failure, its device is read and the incident closed on that
   read where it is at intent and its symptom gone (`confirm_before_ai`). The receipt
   carries the heal (its decision, incident, policy, the person whose change it healed and its
   check after verify) through `apply_batch`'s ``heal``.

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
`decisions.applied` and `outcome_on_incident` as here.
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
         ("read", "Hold the device (a declared wait while another operation holds it) and "
                  "read it again: the deploy's read before, too"),
         ("plan", "Recompute the program from that read, and compare its hash"),
         ("authorise", "Give each removal the policy's reason; refuse any dangerous line"),
         ("apply", "Apply as the policy, holding the device: the deploy's nine stages"),
         ("intent", "Check each healed unit is at intent, from its own section read after "
                    "the change"),
         ("symptom", "Read the symptom again (a removed feature's before its save; any "
                     "other, and a re-applied heartbeat applet's next heartbeat, once the "
                     "device is released)"),
         ("record", "Record the outcome: Fixed rests on verify and closes the incident; any "
                    "other outcome leaves it open, said"),
         ("saved", "After Fixed: save to startup"),
         ("commit", "After Fixed: read the whole configuration and commit the golden from it"),
         ("golden", "After Fixed: read the device again, its own read, against its new "
                    "golden"))
#: Each step in two to four words, for its column on the stepper (the operator, 2026-11-11:
#: "short labels ... No full sentences in the step columns"); the long words above are its
#: hover. `{device}` is the run's own.
STEP_LABELS = {"take": "Take decision", "stops": "Check stops", "read": "Read {device}",
               "plan": "Recompute program", "authorise": "Authorise removals",
               "apply": "Apply", "intent": "Check intent", "symptom": "Read symptom",
               "saved": "Save startup", "commit": "Commit golden", "golden": "Check golden",
               "record": "Record"}
#: The tail (the operator's decisions (a) and (b), 2026-11-16): the steps after Fixed, each
#: drawn under it with its state; a failure or a mismatch flags the incident (`tail_of`),
#: never changes its outcome. A heal whose symptom is waited on once the device is released
#: runs them before its outcome (the device is never held through that wait, nor left
#: unsaved for it), and still only flags.
TAIL_STEPS = ("saved", "commit", "golden")
#: The checks that decide a heal's outcome, the only ones drawn as its proof
#: (`fixit.proof.of_act`; the operator, 2026-11-16: "don't show a check that decides nothing
#: as proof"): the healed units' own check and the symptom's.
DECIDING_STEPS = ("intent", "symptom")
#: The longest the act waits for its device while another operation holds it, then refuses
#: with nothing sent (item 1: "Waiting on a lock is a declared wait, never an outcome";
#: `waits.WAITS`). Reasoned: the longest operation measured holding a device in a heal pass is
#: r2's restore, 134 s from the switch-on (2026-11-16, C3865); 2.5 times that, rounded up.
HOLD_WAIT_S = 335
#: How often the hold is tried again while it waits.
HOLD_POLL_S = 2
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
#: The heartbeat (C3164, the operator, 2026-11-12: "the restored heartbeat is the applet heal's
#: symptom"): a heal that re-applies the heartbeat applet waits for the device's next heartbeat
#: (`restored_heartbeat`, `heartbeat_trigger`). Its bound is the device's own, from its applet's
#: interval in intent (`heartbeat_bound`), so it is no constant of `SYMPTOM_SECONDS`.
HEARTBEAT_KIND = "heartbeat"
#: Every kind whose symptom is read again.
SYMPTOM_KINDS = tuple(SYMPTOM_SECONDS) + (HEARTBEAT_KIND,)
#: From a heartbeat line reaching Loki to Coverage's reader holding it: the reader counts the
#: lines per minute and stamps each minute's end (`coverage_reporting.STEP_SECONDS`, 60 s: a
#: line is stamped up to a minute after it came), and it reads once a minute
#: (`coverage_reporting.INTERVAL_SECONDS`, 60 s); its queries took 0.02 to 0.14 s for nine
#: devices (measured on the host, 2026-10-03). So 120 s. Loki's own ingestion is not in it,
#: and is measured by the first heartbeat heal's own record ("arrived by ..., N s after the
#: heal began"; C3179).
HEARTBEAT_LAG_SECONDS = 120
#: The margin over the longest the next heartbeat should take: about 2.5 times (CLAUDE.md,
#: "Bounds are about 2.5x a measured time").
HEARTBEAT_MARGIN = 2.5
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

    def read_at_golden(self, device, dev) -> dict:
        """The heal's confirmation (item 1, the operator, 2026-11-16: "the confirmation reads
        only its own device"): *device* read again, its own one checked read (`read`), judged
        against its committed golden by drift's own comparison (`drift_check.drift_diff`),
        under no network lock and writing nothing (the network's drift check, whose one-run
        lock refused r6's, C3864, is never asked). ``{"state": "clean"|"drifted"|"unknown",
        "changed_lines", "error"}``; a read or a golden that cannot be had is ``unknown``,
        neither a pass nor a fail."""
        from modules import goldens

        rec = goldens._golden_record((dev or {}).get("ip", ""), self.network)
        if not rec.get("text"):
            return {"state": "unknown", "changed_lines": 0,
                    "error": rec.get("refused") or "no committed golden could be read"}
        text, error = self.read(dev)
        if not text:
            return {"state": "unknown", "changed_lines": 0,
                    "error": f"the device could not be read again ({error})"}
        return against_golden(rec["text"], text, device)

    def symptom(self, device, triggers, since, once: str = "") -> dict:
        return read_symptom(self.network, device, triggers, since, clock=self.clock,
                            sleep=self.sleep, once=once)

    def journal(self, device, dev, decision, outcome, approval=None) -> dict:
        from modules.heal import journal

        return journal.write(self.network, device, dev, decision, outcome, approval=approval)


# ── The symptom (section 4 step 4 (a)) ──────────────────────────────────────────────────────

def symptom_triggers(triggers: list) -> list:
    """The triggers that name a symptom to read again: an adjacency down, a logged adjacency
    drop, a firing alert, a duplicate router-id logged (C2446: R8's verify), and the heartbeat
    a heal re-applied (C3164, `heartbeat_trigger`). A configuration change or a drift record
    names none."""
    return [t for t in triggers or [] if t.get("kind") in SYMPTOM_KINDS and t.get("source")]


def _bound(trigger: dict) -> int:
    """How long *trigger*'s symptom is read for: its kind's `SYMPTOM_SECONDS`, or the
    heartbeat's own bound, carried on its trigger (`heartbeat_bound`)."""
    if trigger.get("kind") == HEARTBEAT_KIND:
        return int(trigger.get("bound_s") or 0)
    return SYMPTOM_SECONDS[trigger["kind"]]


# ── The heartbeat a heal re-applied (C3164) ─────────────────────────────────────────────────

def heartbeat_bound(interval: int) -> int:
    """The longest a heal waits for the heartbeat it re-applied: about 2.5 times the longest
    the next one should take, which is the applet's watchdog interval from intent (it first
    fires one interval after it is configured) and the logs read's lag
    (`HEARTBEAT_LAG_SECONDS`): 2.5 x (300 + 120) = 1050 s for a 300 s applet. One interval is
    measured: in Coverage's reader's capture of the host (2026-10-03,
    tests/fixtures/coverage_reporting/capture.json) every C8000v's heartbeats are 300 s apart
    at the minute's step; the slowest-clocked vIOS switch's are up to 660 s apart (its clock
    runs at about 0.55 of real time, `scripts/nmas-heartbeat-rules`), and 660 + 120 s is
    inside the bound."""
    return int(round(HEARTBEAT_MARGIN * (int(interval) + HEARTBEAT_LAG_SECONDS)))


def restored_heartbeat(units: list, intended: str, platform: str) -> int:
    """The watchdog interval, from committed intent, of the heartbeat applet *units* re-apply,
    or 0 when they re-apply none. Decided by the parse, never by a device's name or an applet's:

    - *intended* (the device's rendered committed intent) carries a whole syslog block, the
      population the heartbeat check itself declares (`scripts/nmas-heartbeat-rules`
      `expected_devices`: committed intent whose block `hostvars.syslog_block_problems` passes),
      its ``heartbeat`` the interval;
    - a unit that adds a line (or sets one back) does so in a section of intent whose parse on
      its own holds that heartbeat: the parser models a stanza as the heartbeat only in exactly
      the applet's own shape (`parsers.base` `_h_eem_applet`), so any other applet, or one
      that only resembles it, keeps its kind's symptom handling."""
    from modules.nsot import hostvars
    from modules.nsot.deploy import _section_chains
    from modules.nsot.parsers import get_parser

    tops = {(c[0] if c else l) for u in units or [] if u.get("op") in ("add", "change")
            for c, l in u.get("add") or []}
    if not tops or not intended:
        return 0
    try:
        parser = get_parser(platform)
        doc = parser.parse(intended)
    except Exception as exc:                            # noqa: BLE001 (said: no heartbeat read)
        log.warning("heal: intent could not be parsed for its heartbeat: %s", exc)
        return 0
    interval = (((doc.get("logging") or {}).get("syslog")) or {}).get("heartbeat")
    if not (isinstance(interval, int) and interval > 0) or hostvars.syslog_block_problems(doc):
        return 0
    sections = {}
    for line, chain in _section_chains(intended):
        top = chain[0] if chain else line
        if top in tops:
            sections.setdefault(top, []).append(line)
    for lines in sections.values():
        try:
            got = parser.parse("hostname heal-unit\n" + "\n".join(lines) + "\n")
        except Exception as exc:                        # noqa: BLE001 (that section is not it)
            log.info("heal: a section of intent could not be parsed alone: %s", exc)
            continue
        if (((got.get("logging") or {}).get("syslog")) or {}).get("heartbeat") == interval:
            return interval
    return 0


def heartbeat_trigger(network: str, device: str, interval: int) -> dict:
    """The heartbeat as a symptom to read again: no heartbeat from *device* since the heal,
    read from Coverage's not-reporting reader's stored arrivals for *network* (one Loki query
    for the whole fleet each minute; never a device read), within `heartbeat_bound`. A network
    with no such store (Loki not applicable or not configured there) carries ``refused``, its
    why, and its symptom cannot be read."""
    from modules import reader_job
    from modules.device_logs import MARKER
    from modules.readers import coverage_reporting as CR

    store, refused = reader_job.store_for(CR.NAME, network)
    t = {"kind": HEARTBEAT_KIND, "source": store or CR.NAME, "interval": int(interval),
         "bound_s": heartbeat_bound(interval),
         "words": f"no {MARKER} line from {device} since its heartbeat applet was re-applied"}
    if refused:
        t["refused"] = refused.get("why") or refused.get("state") or "no store"
    return t


def _hms(epoch: float) -> str:
    return time.strftime("%H:%M:%S UTC", time.gmtime(epoch))


def heartbeat_seen(value: dict, device: str, since: float) -> tuple:
    """``(state, words)``: whether Coverage's reader's *value* holds a heartbeat from *device*
    after *since*: ``gone`` (the symptom, no heartbeat, is gone), ``present`` (none yet) or
    ``unreadable`` (its heartbeat source was not read: neither a pass nor a fail). A heartbeat
    counts only when the whole minute that counted it is after *since*: the reader stamps each
    minute's count at its end (`coverage_reporting._loki_last`), so a stamp less than a minute
    after *since* may count a line from before it."""
    from modules.readers import coverage_reporting as CR

    value = value or {}
    down = CR._source_down(value, "heartbeat")
    if down:
        return "unreadable", f"Coverage's heartbeat source was not read ({down})"
    at = (value.get("heartbeat") or {}).get(device)
    if at is not None and float(at) - CR.STEP_SECONDS >= float(since):
        return "gone", (f"{device}'s heartbeat arrived by {_hms(at)}, "
                        f"{round(float(at) - float(since))} s after the heal began")
    if at is None:
        return "present", (f"none from {device} in Coverage's last "
                           f"{CR.LOOKBACK_SECONDS // 3600} h")
    return "present", (f"{device}'s newest heartbeat was counted by {_hms(at)}, "
                       + ("before the heal began" if float(at) <= float(since) else
                          "in the minute the heal began, so it is not counted"))


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


def alert_firing(value: dict, device: str, rule: str, interface: str = "",
                 addresses=None) -> bool:
    """Whether the Grafana alerts reader's *value* still holds *rule* firing on *device* (on
    *interface*, when the trigger named one). The episode's key is not compared: a resolve and
    a re-fire is a new key, and the symptom is the same.

    An instance that names no device (a rule with no device label, Interface down among them:
    the reader keeps its polled address alone, `grafana_alerts._instance_device`) is *device*'s
    only when its address is one of *device*'s own: *addresses* is a callable giving them,
    asked once and only when such an instance is met (`device_addresses`). Its answer None (the
    inventory could not be read) counts the instance, as before: an address not read is never
    read as gone. Without this, another switch's Interface down on a port of the same name
    kept this device's symptom present, and its incident open after its fix verified (measured
    on the host, 2026-11-15)."""
    from modules.evidence_pack import firing
    from modules.heal.attribution import address_of

    mine = {}
    for i in firing(value or {}):
        if (i.get("rule") or "") != rule:
            continue
        if device and (i.get("device") or "") not in ("", device):
            continue
        labels = i.get("labels") or {}
        if interface and interface not in (labels.get("ifDescr"), labels.get("ifName")):
            continue
        if device and not i.get("device") and addresses is not None:
            if "known" not in mine:
                mine["known"] = addresses()
            known = mine["known"]
            at = str(i.get("address") or "")
            if known is not None and (address_of(at) or at) not in known:
                continue
        return True
    return False


def device_addresses(trigger: dict, device: str):
    """*device*'s own polled addresses, each in its compressed form (`attribution.address_of`),
    for an alert symptom judged on it (`alert_firing`): the address the trigger was placed by
    (``address``, which `triggers.from_alerts` records when it placed the device by its polled
    address), else every address the inventory holds for *device* (`attention._inventory`, the
    read the trigger's own placing makes: an incident opened before the trigger carried its
    address). None when the inventory cannot be read."""
    from modules.heal.attribution import address_of

    given = str(trigger.get("address") or "")
    own = address_of(given) or given
    if own:
        return {own}
    from modules import attention as A

    inv, _why = A._inventory()
    if inv is None:
        return None
    return {address_of(ip) or ip for ip, names in (inv[1] or {}).items() if device in names}


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
    ``present`` or ``gone``; for the heartbeat (`heartbeat_seen`), also ``unreadable``."""
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
    if trigger["kind"] == HEARTBEAT_KIND:
        return heartbeat_seen(value, device, since)[0]
    if trigger["kind"] == "alert":
        present = alert_firing(value, device, trigger.get("rule") or "",
                               trigger.get("interface") or "",
                               addresses=lambda: device_addresses(trigger, device))
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


def readback_only(units: list) -> str:
    """R3's cosmetic heal (the operator, 2026-11-14: "Cosmetic changes (description, banner,
    snmp location/contact, alias) are a read-back only"): ``"descriptions only"`` (each family
    named) when EVERY line every unit adds or removes is cosmetic
    (`verify_scope.cosmetic_only`), else ``""``. A unit with any other line, or a stanza whose
    header departed, is not: it keeps the symptom's wait."""
    from modules.nsot import verify_scope

    whats = verify_scope.cosmetic_only([(tuple(p[0] or ()), p[1]) for u in units or []
                                        for p in list(u.get("add") or [])
                                        + list(u.get("remove") or [])])
    return f"{' and '.join(whats)} only" if whats else ""


def read_symptom(network: str, device: str, triggers: list, since: float, *, clock=time.time,
                 sleep=time.sleep, read=None, request=None, once: str = "",
                 bound_s: float = None) -> dict:
    """The incident's symptoms read again (``{"state", "words", "checks"}``): each trigger's
    store asked to read now, then read until every symptom is gone or its bound passes. *state*
    is ``none`` (no symptom to read), ``gone``, ``present`` or ``unreadable`` (a store that
    could not be read, or not read since the change, within the bound: neither a pass nor a
    fail). ``reads`` is every read it made, in order, as the act's ``symptom`` step keeps them
    (`reads.read_entry`: when, the store asked, gone, still there or unreadable), so the
    heal's own record says "5 reads, 30 s apart, each still down" (the operator, 2026-11-11);
    a reader's store is no device read, so each names no run of the reads store.

    *once* (R3's cosmetic heal, `readback_only`: its words, "descriptions only: read back,
    2 s"): no line of the change can clear or cause the symptom, so each store is read ONCE,
    its last good read taken if it was made after the newest symptom began (an older one is
    stale: unreadable, never gone), no reader asked to run and nothing waited:
    ``gone``, ``present`` (a symptom the change could not have caused or cleared: symptom
    remains) or ``unreadable``, each saying *once* and why it was not waited on.

    *bound_s* (C3870's confirmation before AI troubleshooting, `confirm_before_ai`): the
    longest it reads in place of the symptoms' own bounds; 0 reads each store once as it
    stands, after asking its reader to run, and waits for nothing: anything but gone is no
    proof."""
    from modules import reader_job
    from modules.nsot import reads as reads_store

    wanted = symptom_triggers(triggers)
    if not wanted:
        return {"state": "none", "checks": [], "reads": [],
                "words": (f"{once}; " if once else "")
                + "the incident named no symptom beyond the configuration"}
    kept = {"reads": []}
    read = read or reader_job.read_cached

    def ask(store):
        reader = _reader_for(store)
        if reader is None:
            return False
        reader_job.request_run(reader, by="heal to intent: the symptom read again")
        return True

    request = (lambda store: False) if once else (request or ask)
    if once:
        # A read from before the change counts (the change cannot move the symptom), but never
        # one from before the symptom began: a reader failing since then keeps an older good
        # value that knows nothing of it. So the newest symptom trigger's time; a trigger
        # carrying none keeps *since*, the heal's own start (later, so stricter).
        began = [float(t["epoch"]) for t in wanted if t.get("epoch")]
        since = max(began) if len(began) == len(wanted) else since
    bound = max(_bound(t) for t in wanted) if bound_s is None else int(bound_s)
    deadline = clock() + bound
    asked = {}

    def said(c):
        return f" ({c['detail']})" if c.get("detail") else ""

    while True:
        checks = []
        for t in wanted:
            store = _store_for(t)
            detail = ""
            if t.get("refused"):
                # A network with no store for it (C3164's heartbeat: Loki not configured
                # there): nothing to ask, and nothing the bound would change.
                asked.setdefault(store, False)
                state, detail = "unreadable", t["refused"]
            else:
                if store not in asked:
                    asked[store] = request(store)
                got = read(store)
                state = ("unreadable" if got.get("state") != "ok" else
                         judge(t, got.get("doc"), network, device, since))
                if t.get("kind") == HEARTBEAT_KIND and state != "stale" and \
                        got.get("state") == "ok":
                    detail = heartbeat_seen(((got.get("doc") or {}).get("last_good") or {})
                                            .get("value") or {}, device, since)[1]
            checks.append(dict({"trigger": t.get("words") or t.get("kind"), "store": store,
                                "state": state, "asked": asked[store]},
                               **({"detail": detail, "final": True} if t.get("refused") else
                                  {"detail": detail} if detail else {})))
            reads_store.keep_read(kept, reads_store.read_entry(
                f"the {store} reader's stored value", {"gone": "pass", "present": "fail"}.get(
                    state, "unreadable"),
                f"{t.get('words') or t.get('kind')}: "
                + {"gone": "gone", "present": "still there",
                   "stale": "not read since the change"}.get(state, state)
                + (f": {detail}" if detail else ""),
                at=_iso(clock())))
        states = {c["state"] for c in checks}
        if once:
            return _read_once(checks, kept["reads"], states, once)
        if states == {"gone"}:
            told = "; ".join(c["detail"] for c in checks if c.get("detail"))
            return {"state": "gone", "checks": checks, "reads": kept["reads"],
                    "words": f"the symptom is gone ({len(checks)} read again)"
                             + (f": {told}" if told else "")}
        final = all(c["state"] == "gone" or c.get("final") for c in checks)
        if final:
            why = next(c for c in checks if c.get("final"))
            return {"state": "unreadable", "checks": checks, "reads": kept["reads"],
                    "words": (f"the symptom cannot be read here ({why['trigger']}: "
                              f"{why['detail']})")}
        if clock() >= deadline:
            if "present" in states:
                left = [c for c in checks if c["state"] == "present"]
                return {"state": "present", "checks": checks, "reads": kept["reads"],
                        "words": (f"the symptom is still there after {bound} s: "
                                  f"{left[0]['trigger']}{said(left[0])}")}
            why = [c for c in checks if c["state"] != "gone"][0]
            return {"state": "unreadable", "checks": checks, "reads": kept["reads"],
                    "words": (f"the symptom could not be read again within {bound} s "
                              f"({why['store']}: {why['state']}"
                              + ("" if why["asked"] else ", no reader for it runs here")
                              + (f"; {why['detail']}" if why.get("detail") else "")
                              + ")")}
        sleep(POLL_SECONDS)


def _read_once(checks: list, reads: list, states: set, once: str) -> dict:
    """`read_symptom`'s answer for a cosmetic heal: its one read of each store, never waited."""
    why = "not waited on: no line of it can clear or cause the symptom"
    if states == {"gone"}:
        return {"state": "gone", "checks": checks, "reads": reads,
                "words": f"{once}; the symptom is gone in its store's last read ({why})"}
    if "present" in states:
        left = next(c for c in checks if c["state"] == "present")
        return {"state": "present", "checks": checks, "reads": reads,
                "words": (f"{once}; the symptom is still there in its store's last read "
                          f"({left['trigger']}; {why})")}
    bad = next(c for c in checks if c["state"] != "gone")
    return {"state": "unreadable", "checks": checks, "reads": reads,
            "words": (f"{once}; the symptom could not be read in its store ({bad['store']}: "
                      f"{bad['state']}" + (f"; {bad['detail']}" if bad.get("detail") else "")
                      + f"; {why})")}


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


def _stops(src, network: str, decision: dict, now: float, held: bool = False) -> str:
    """Why nothing may be sent now, or ``""``: section 6's stops judged again at apply.
    *held*: judged again once this act holds the device, so the hold guard 3 would find is
    this act's own and is not counted (the 18:42 Denver run of 2026-11-17: every restore
    refused itself, "r2 is held by deploy of ..."); planned windows still hold. C3909 (the
    operator, 2026-11-17: one operation per device is "a wait, never a refusal or hold"): the
    call before the hold passes *held* too, since `hold_device` waits for another holder;
    planned-restart and no-change windows are judged at both.

    Round 2 of the speed pass (the operator, 2026-11-17): only Stop everywhere, Off (the mode
    not Auto) and a planned window a person set stop it here; the lab-stage gate, the policy
    moved since the decision, the kinds allowed Auto, a halt and "no person confirmed the
    policy" stop nothing; *network* is read by guard 3 below."""
    from modules.heal import policy

    mode = src.mode(now)
    if (mode.get("stopped") or {}).get("stopped"):
        return f"self-healing is stopped everywhere: {mode['stopped'].get('words')}"
    if mode.get("mode") != "auto":
        return (f"the mode is {policy.MODE_WORDS.get(mode.get('mode'), mode.get('mode'))} now "
                f"({mode.get('words')}), and only AUTO sends a heal")
    # Each fix's own mode decides (the operator, 2026-11-17: Fixes' Automatic, Dry run or
    # Manual per fix): a kind no longer in the network's fix kinds to heal sends nothing.
    allowed = set(mode.get("kinds_auto") or [])
    off = sorted({u.get("kind") for u in decision.get("units") or []} - allowed)
    if off:
        return (f"{', '.join(off)} {'is' if len(off) == 1 else 'are'} no longer allowed AUTO "
                f"(allowed now: {', '.join(sorted(allowed)) or 'none'})")
    # The device held by another operation is `hold_device`'s wait, never a stop here: guard 3
    # is judged with no holder, so a person's planned restart and no-change windows are always
    # reached (the review of round 2: the holder's hit, often this act's own hold, returned
    # first and hid the no-change window).
    from modules.heal import guards
    g = guards.g3_planned(network, decision["device"], now, holder=lambda _n, _d: None)
    if g:
        return f"guard 3, planned work: {g['words']}"
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


def stopped_now(network: str) -> str:
    """``""``, or why the act stops waiting for its device: Stop everywhere, or the mode not
    Auto now (`policy.current`). A policy that cannot be read stops the wait, said."""
    from modules.heal import policy

    try:
        mode = policy.current(network)
    except Exception as exc:                          # noqa: BLE001 (said; nothing is sent)
        return f"self-healing's policy could not be read ({type(exc).__name__}: {exc})"
    if (mode.get("stopped") or {}).get("stopped"):
        return f"self-healing is stopped everywhere: {mode['stopped'].get('words')}"
    if mode.get("mode") != "auto":
        return f"self-healing is no longer in Auto ({mode.get('words') or mode.get('mode')})"
    return ""


def hold_device(network: str, device: str, ip: str, actor: str, detail: str, *, begin=None,
                clock=time.time, sleep=time.sleep) -> str:
    """Hold *device* for the act from its read to the end of its tail (one read for the act and
    the deploy's stage 4, `PipelineContext.pre_read`; the hold THE apply then takes is this
    thread's again, re-entrant). Another operation holding it is WAITED for, a declared wait
    (`waits.WAITS`, `HOLD_WAIT_S`, tried every `HOLD_POLL_S`, drawn on the read step as
    running with its bound, *begin*), never an outcome; past the bound, or a device Mercury
    changes nothing on, ``why`` (nothing was sent), naming the holder. ``""`` once held."""
    from modules.nsot import device_ops
    from modules.nsot.receipts import operation

    # Round 2 of the speed pass (the operator, 2026-11-17): no bound refuses the wait. It waits
    # until the device is free, asking Stop everywhere and Off at each poll (`stopped_now`);
    # HOLD_WAIT_S is the bound the wait is drawn with, never a refusal.
    t0, said = clock(), False
    while True:
        try:
            device_ops.acquire(network, device, operation(""), actor, detail=detail, ip=ip)
            return ""
        except device_ops.NotManaged as exc:
            return str(exc)
        except device_ops.DeviceBusy as exc:
            waited = clock() - t0
            stopped = stopped_now(network)
            if stopped:
                return (f"{stopped} while the act waited {round(waited)} s for {device}, held "
                        f"by another operation ({exc}); nothing was sent")
            if not said and begin is not None:
                begin("read", f"waiting for {device}, held by another operation ({exc})",
                      wait_s=HOLD_WAIT_S, bound=True)
                said = True
        sleep(HOLD_POLL_S)


def apply_decision(network: str, decision: dict, *, now: float = None, sources=None,
                   actor_kind: str = "policy") -> dict:
    """Apply one taken heal decision, verify it and record it (the module's steps 2 to 9):
    ``{"decision", "device", "outcome", "words", "steps", "sent", "report"}``. The device the
    act holds (`hold_device`) is released however it ends."""
    from modules.nsot import device_ops

    holds = []
    try:
        return _apply_decision(network, decision, now=now, sources=sources,
                               actor_kind=actor_kind, holds=holds)
    finally:
        for host in holds:
            device_ops.release(network, host)


def _apply_decision(network: str, decision: dict, *, now: float = None, sources=None,
                    actor_kind: str = "policy", holds: list) -> dict:
    from modules import identity, pipeline
    from modules.heal import decide, decisions, kinds, steplog
    from modules.nsot import authorisation
    from modules.nsot.deploy import config_line_count
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

    #: The outcome recorded at Fixed, before the tail (`declare`): ``{"outcome", "words",
    #: "n"}``, *n* the steps the first act row kept.
    declared = {}
    #: The act's timing record from its authorise step to the push and on (`pipeline.lap`;
    #: the speed pass, 2026-11-16: 39 s between authorise and apply that no lap named): the
    #: plan's pieces, the act's own checks, the apply's pieces, then the pipeline's own laps,
    #: one list, kept as the record's ``laps``. Timing only: nothing reads it to decide.
    act_laps = []

    def record_outcome(outcome, words, tail=None):
        step("record", outcome, f"{OUTCOME_WORDS[outcome]}: {words}")
        # C3871: recorded at the moment the outcome is, never the act's start (*now* stays the
        # act's own for its guards and elapsed times).
        at = time.time()
        try:
            # No halt (the operator, 2026-11-17, round 2): a failed heal is a failure R1 sees.
            decisions.applied(network, decision["id"], outcome, by=via, words=words, now=at)
        except Exception as exc:
            log.error("heal: %s's outcome on %s was not recorded: %s", network, device, exc)
        if outcome == "healed" and (tail or {}).get("state") == "flagged":
            # Healed, and its tail (run before this outcome: a symptom waited on) flagged: it
            # stands on the tail's failure, never closed Fixed first (C3870).
            outcome_on_incident(network, decision, TAIL_FAILED, tail.get("flag") or "")
        else:
            # Only healed closes (C3870), with its verify kept on the close (`verified_of`,
            # the proof the incident's card draws); any other outcome stands, said.
            outcome_on_incident(network, decision, outcome, words,
                                fixed=verified_of(decision, steps) if outcome == "healed"
                                else None)
        log.info("heal: %s on %s: %s: %s", network, device, outcome, words)

    def declare(outcome, words):
        """The outcome at Fixed (decisions (a) and (b)): recorded, the incident closed (healed;
        any other outcome leaves it standing, C3870) and the first ``act`` row written with
        the tail ``running`` (`tail_of`), so the incident reads Fixed while the save, the full
        read, the golden and the read again run under it."""
        record_outcome(outcome, words)
        declared.update(outcome=outcome, words=words, n=len(steps))
        first = {"decision": decision["id"], "device": device, "outcome": outcome,
                 "words": redact_text(words), "steps": list(steps), "sent": True,
                 "records": {"tail": tail_of(device, outcome, [], [], running=True)}}
        try:
            # C3871: stamped when recorded, as the applied row is, so R1's eligibility (the
            # failure after the switch went on) reads the outcome's time, never the act's start.
            steplog.record_act(network, decision, first, by=via, policy_by=setter,
                               now=time.time())
        except Exception as exc:
            log.error("heal: %s's act on %s (at Fixed) is not in the step log: %s", network,
                      device, exc)
        # The speed pass (2026-11-16, item c): the record step's own announcement fires before
        # the outcome reaches the stores (`record_outcome`: its step, then the decision and the
        # incident's close), so a page re-fetched on it read the incident still open until the
        # tail's next step. Told again now that Fixed is stored: an announcement only.
        from modules import op_progress
        op_progress.moved()

    def finish(outcome, words, *, sent=False, report=None, flags=None):
        if declared:
            outcome, words = declared["outcome"], declared["words"]
        # The tail's own record: each step after the outcome and any flag it raised.
        tail = (tail_of(device, outcome, steps, list(flags or []))
                if sent and outcome not in ("refused", "rolled_back", "failed") else None)
        if not declared:
            record_outcome(outcome, words, tail=tail)
        elif outcome == "healed" and (tail or {}).get("state") == "flagged":
            # Closed at Fixed; its tail then failed: the incident is reopened (C3870).
            reopen_on_tail(network, decision, tail, steps)
        result = {"decision": decision["id"], "device": device, "outcome": outcome,
                  "words": redact_text(words), "steps": steps, "sent": sent, "report": report}
        result["records"] = _records(network, decision, result, src, held, now)
        marks = next((x.get("laps") for x in (report or {}).get("results") or []
                      if x.get("device") == device and x.get("laps")), None) or (
            act_laps if len(act_laps) > 1 else None)
        if marks:
            # Where each second of THE apply went (round 2, item 4), from its run's laps.
            from modules.nsot.command_plan_run import _laps
            result["records"]["laps"] = _laps(marks)
        if tail is not None:
            result["records"]["tail"] = tail
        # A heal declared at Fixed writes its tail as a second ``act`` row: only the steps after
        # its record (the step log folds both into one entry, its records the last row's).
        logged = dict(result, steps=steps[declared["n"]:]) if declared else result
        try:
            steplog.record_act(network, decision, logged, by=via, policy_by=setter,
                               now=time.time())                   # C3871: at record time
            result["records"]["step_log"] = "written"
        except Exception as exc:
            log.error("heal: %s's act on %s is not in the step log: %s", network, device, exc)
            result["records"]["step_log"] = f"not written: {type(exc).__name__}: {exc}"
        return result

    def refuse(name, words, waits=False):
        # *waits*: a guard working as designed (`refusal_waits`): no failure R1 starts on.
        step(name, "refused", words, **({"waits": True} if waits else {}))
        return finish("refused", f"{words}. Nothing was sent")

    # C3909: another operation holding the device is waited for below (`hold_device`), never
    # refused here.
    why = _stops(src, network, decision, now, held=True)
    if why:
        return refuse("stops", why, waits=True)
    step("stops", "ok", "AUTO, not stopped everywhere, no planned work a person declared")

    dev = src.device(device)
    # Held from this read to the end of the tail (item 4): the read is the deploy's stage-4
    # read too, and nothing of Mercury's changes the device between them. Another operation
    # holding it is a declared wait, never an outcome (item 1).
    busy = hold_device(network, device, dev.get("ip", ""), setter or "heal to intent", via,
                       begin=begin, clock=getattr(src, "clock", time.time),
                       sleep=getattr(src, "sleep", time.sleep))
    if busy:
        return refuse("read", busy, waits=True)
    holds.append(device)
    # The stops judged again once held (the review, finding 1): the wait for the hold may have
    # lasted up to HOLD_WAIT_S, and a Stop everywhere, a mode change or a planned-restart
    # window declared meanwhile refuses here, nothing sent.
    why = _stops(src, network, decision, getattr(src, "clock", time.time)(), held=True)
    if why:
        return refuse("stops", f"{why} (judged again once {device} was held)", waits=True)
    begin("read", f"reading {device} again")
    text, error = src.read(dev)
    if not text:
        return refuse("read", f"the read of {device} at apply could not be made ({error})")
    step("read", "ok", f"{device} read again, holding it: the deploy's read before, too")
    held.update(dev=dev, read=text)

    golden = src.golden(device, dev)
    held["golden_before"] = golden.get("commit") or ""
    if not golden.get("text"):
        # C3909: a golden that departs from intent is no refusal (its lines come from intent,
        # `decide.restore_source`); none at all is a failure R1 starts on.
        return refuse("plan", f"no golden of {device} can be read now ("
                              f"{golden.get('words') or golden.get('state')})")
    platform = src.platform(device, dev)
    intended = src.intended(device, platform)
    if not intended.get("text"):
        # Not a wait: a failure R1 starts on (`fixit.auto.ACT_FAILURES`, C3909).
        return refuse("plan", f"committed intent cannot be rendered: {intended.get('why')}")
    inc = _incident(network, decision["incident"])
    # C2839: classed at apply as it was decided, the network's answer read again (a no since
    # makes a security_revert unit Tier 2, refused below as not the decision's tier).
    c = kinds.classify(golden["text"], text, intended["text"], platform=platform,
                       mgmt_ip=dev.get("ip", ""), related=bool(inc.get("related")),
                       revert=decide.revert_scope(src.mode(now), inc))
    if golden.get("state") != "at_intent":
        # Not a wait: the golden departed from intent since the decision (the review of C3909:
        # a restore from intent is not built until it classifies every line it sends, C3910),
        # a failure R1 starts on, nothing sent.
        return refuse("plan", f"{device}'s golden departs from its committed intent now "
                              f"({golden.get('words') or golden.get('state')})")
    prog = decide.program(decide.restore_source(golden, intended), text, c["units"],
                          c["removal_ids"], mgmt_ip=dev.get("ip", ""), platform=platform)
    from modules.drift_check import departure, drift_diff

    dep = departure(drift_diff(golden["text"], text, device))
    if prog["hash"] != decision.get("program_hash"):
        return refuse("plan", (f"the program recomputed from the read at apply is not the one "
                               f"decided (decided {decision.get('program_hash')}, now "
                               f"{prog['hash']}): {_moved(decision, c['units'], prog, dep)}; "
                               "a later read starts over"), waits=True)
    if prog["refused"] or c.get("blocked") or c["tier"] != 1:
        return refuse("plan", f"the program refuses a unit now: "
                              f"{(prog['refused'] or [{}])[0].get('reason') or c.get('blocked')}")
    # The one count of a program's lines (`deploy.config_line_count`): a sub-mode's exit is not
    # a line re-applied.
    step("plan", "ok", f"the program recomputed from the read: "
                       f"{config_line_count(prog['commands'])} line(s), "
                       f"hash {prog['hash']}, the decision's")
    held.update(prog=prog, platform=platform)
    # C3164: a unit that re-applies the heartbeat applet makes the heartbeat itself a symptom
    # to read again, after the incident's own: its next line, within the applet's own bound.
    beat = restored_heartbeat(c["units"], intended["text"], platform)
    beats = [heartbeat_trigger(network, device, beat)] if beat else []
    symptoms = list(inc.get("triggers") or []) + beats

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
    pipeline.lap(act_laps, "authorise")

    capture = {device: {"text": kinds._stored(text), "intended": prog["fragment"]}}
    plan_kw = {"authorise": {device: authorise}, "remove": {device: list(c["removal_ids"])},
               "capture": capture}
    entry = src.plan(device, laps=act_laps, purpose="heal", **plan_kw)
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

    pipeline.lap(act_laps, "act: the plan's checks")
    applied_at = {"t": now}
    # R3 (the operator, 2026-11-14): a heal whose every line is cosmetic (`readback_only`: a
    # description, an alias, a banner, ...) verifies by its read-back; no line of it can clear
    # or cause a symptom, so the symptom is read ONCE from its store's last read and never
    # waited on (no `POLL_SECONDS` poll, no reader's cadence). Anything else waits as before.
    cosmetic = readback_only(c["units"])

    def cosmetic_words():
        return f"{cosmetic}: read back, {max(0, round(src.clock() - applied_at['t']))} s"

    def read_again(triggers):
        from modules.device_logs import MARKER

        if cosmetic and not any(t.get("kind") == HEARTBEAT_KIND for t in triggers):
            words = cosmetic_words()
            begin("symptom", f"{words}; reading the symptom's store once, not waiting on it")
            s = src.symptom(device, triggers, applied_at["t"], once=words)
            step("symptom", s["state"], s["words"], **symptom_reads(s))
            return s
        bound = symptom_bound(triggers)
        waits = ({"wait_for": HEARTBEAT_KIND}
                 if any(t.get("kind") == HEARTBEAT_KIND for t in triggers) else {})
        begin("symptom", (f"waiting for {device}'s heartbeat: its next {MARKER} line in "
                          f"Coverage's stored arrivals, up to {bound} s"
                          if waits else
                          "reading the symptom again, until it is gone or its bound passes"),
              wait_s=bound, bound=True, **waits)
        s = src.symptom(device, triggers, applied_at["t"])
        step("symptom", s["state"], s["words"], **symptom_reads(s), **waits)
        return s

    def symptom():
        return read_again(symptoms)

    def heartbeat_after(held):
        """A removed feature's symptom read before the save (N13) gone: the heartbeat the
        heal re-applied, read now that the device is released (C3164)."""
        s = read_again(beats)
        if s.get("state") != "gone":
            return s
        return dict(s, words=f"{held.get('words') or 'its symptom read'}; {s['words']}")

    def after_verify(host, result, ctx):
        # The read after the change, as stage 7 read it on the run's session: the healed
        # units' interface sections where every line sits in one (`pipeline.tail_sections`),
        # else the whole configuration, said (decision (b)).
        snap = ((getattr(ctx, "post_snapshots", None) or {}).get(dev.get("ip", ""))) or {}
        post = snap.get("running_config") or (
            ((result.get("golden_pending") or [{}])[0] or {}).get("config_text") or "")
        scope = snap.get("running_config_sections") or []
        read_words = (f"from {', '.join(scope)}'s own section read after the change" if scope
                      else "from the whole configuration read after the change"
                      + (f" ({snap['full_before_fixed']})" if snap.get("full_before_fixed")
                         else ""))
        left = units_left(c["units"], post) if post else ["no read after the change"]
        # The healed units' own check decides; a whole-device compare with intent decides
        # nothing here and is not shown as proof (the operator, 2026-11-16): a departure
        # elsewhere is its own incident, and the tail's read again flags a device not at its
        # new golden.
        record = {"intent": {"left": left, "read": list(scope) or "whole"}}
        # What the deploy's verify waited out before this check, kept on its step (the first
        # after the apply), so the heal's Fixing stage says the wait inside its duration.
        waited = bgp_hold(result)
        if left:
            step("intent", "failed", f"{len(left)} unit(s) not at intent: {left[0]}", **waited)
            return {"rollback": (f"{len(left)} healed unit(s) not at intent after the change "
                                 f"({left[0]}), so what landed was undone"), "record": record}
        step("intent", "ok", f"each healed unit at intent, {read_words}", **waited)
        verified = ((result.get("verify") or {}).get("ok") is True)
        if feature_removed(c["units"]):
            s = src.symptom(device, inc.get("triggers") or [], applied_at["t"],
                            **({"once": cosmetic_words()} if cosmetic else {}))
            record["symptom"] = {"state": s["state"], "words": s["words"]}
            step("symptom", s["state"], s["words"], **symptom_reads(s))
            if s["state"] == "present":
                return {"rollback": (f"removing the feature did not clear its symptom "
                                     f"({s['words']}), so its lines were put back (N13)"),
                        "record": record}
            if verified and not beats and s["state"] in ("gone", "none"):
                declare("healed", _healed_words(s))
            return {"rollback": "", "record": record}
        # Decision (a): Fixed rests on verify. Where nothing is left to wait for (no symptom
        # named, or a cosmetic heal's one read of its store), the outcome is recorded now and
        # the save, the full read and the golden follow under it. A symptom to wait for is read
        # once the device is released, never while it is held: its outcome comes after.
        if verified and not symptom_triggers(symptoms):
            declare("healed", "healed and verified; the incident named no symptom beyond the "
                              "configuration")
        elif verified and cosmetic and not beats:
            s = read_again(symptoms)
            record["symptom"] = {"state": s["state"], "words": s["words"]}
            outcome = {"gone": "healed", "none": "healed", "present": "symptom_remains"}.get(
                s["state"], "partial")
            declare(outcome, _healed_words(s) if outcome == "healed" else
                    f"configuration at intent, and {s['words']}"
                    + (": configuration was not the whole cause"
                       if outcome == "symptom_remains" else ""))
        return {"rollback": "", "record": record}

    def _healed_words(s):
        return f"healed and verified; {s.get('words') or ''}".rstrip("; ")

    def on_tail(name, state, words):
        """The tail's steps as `pipeline.run_tail` tells them, live under Fixed, each also
        noted on the device's hold (``tail: <step>``), so a tail whose process ends says where
        it stopped (`_last_tail_step`)."""
        from modules.nsot import device_ops

        if state == "running":
            device_ops.note(f"tail: {name}")
            begin(name, words)
        else:
            step(name, state, words)

    # The healed units checked again on the tail's whole read before its golden is committed
    # from it (`pipeline.run_tail`'s *check*; the review, finding 2).
    on_tail.check = lambda text: units_left(c["units"], text)

    facts = {"decision": decision["id"], "incident": decision.get("incident"),
             "kind": decision.get("kind"), "mode": "auto",
             "policy": {"fingerprint": pol.get("fingerprint"), "by": setter,
                        "reason": pol.get("reason") or ""},
             "person": dict(decision.get("person") or {}), "program_hash": prog["hash"],
             # The receipt says what the deploy's stage 4 compared (the review, finding 3).
             "read_before": (f"stage 4 read {device} again before the push and compared it "
                             f"with this heal's own read at apply (C78), made holding the "
                             "device and held since; a change made from outside between the "
                             "two is refused, nothing sent (C3967)")}
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
    pipeline.lap(act_laps, "act: program written to the step log")
    step("apply", "running", f"as the policy set by {setter_shown}, holding {device}",
         **by_field)
    pipeline.lap(act_laps, "act: apply step announced")
    # The act's read is the deploy's read before (item 4: one read), the device held since.
    capture[device]["read"] = text
    with identity.carried_policy(setter, pol.get("fingerprint") or ""):
        report = src.apply(
            device, confirmations={device: entry.get("capture_hash")},
            command_hashes={device: entry.get("command_hash")}, actor=setter,
            actor_kind=actor_kind, stop_at_first=True, after_verify=after_verify,
            heal={device: facts}, hold_detail=via, tail=on_tail, laps=act_laps, **plan_kw)
    r = next((x for x in report.get("results") or [] if x.get("device") == device), {})

    def release():
        """Released once the read again is made (the review, finding 6: the device is held
        through it), before anything is waited on: a symptom's wait never holds it."""
        from modules.nsot import device_ops
        if device in holds:
            holds.remove(device)
            device_ops.release(network, device)

    return _judge_tail(device, r, report, src, via, step, finish, symptom, dev, begin=begin,
                       more=heartbeat_after if beats else None, declared=declared,
                       release=release)


#: The field a heal's first step after its apply keeps what the deploy's verify waited out on:
#: BGP's hold time (C178, `pipeline._watch_bgp_hold`), ``{"hold_s", "watched_s"}``.
BGP_HOLD = "bgp_hold"


def bgp_hold(result) -> dict:
    """``{"bgp_hold": {"hold_s", "watched_s"}}`` when the deploy's verify of *result* (the
    device's row of the apply's report) watched BGP to its hold time: the hold, and how long
    after the push BGP was read again (`pipeline._watch_bgp_hold`'s own measurement); else
    ``{}`` (BGP not watched, or skipped)."""
    watch = ((result or {}).get("verify") or {}).get("bgp_watch") or {}
    if not isinstance(watch, dict):
        return {}
    try:
        watched = int(watch.get("watched_s") or 0)
    except (TypeError, ValueError):
        watched = 0
    if watched <= 0:
        return {}
    return {BGP_HOLD: {"hold_s": int(watch.get("hold_s") or 0), "watched_s": watched}}


def symptom_bound(triggers: list) -> int:
    """The longest the symptom read waits for *triggers* (`read_symptom`'s own bound: the
    largest of the symptoms' bounds named, `_bound`), or 0 when none is named."""
    return max((_bound(t) for t in symptom_triggers(triggers)), default=0)


#: A heal's verify, the steps after its apply that prove it (`verified_of`).
VERIFY_STEPS = ("intent", "symptom", "saved", "golden")


def verified_of(decision: dict, steps: list) -> dict:
    """A verified heal's proof as its incident's close keeps it (``fixed``): ``{"act",
    "device", "at", "epoch", "verify": [{"step", "result", "words", "at", "reads"?}]}``, each
    `VERIFY_STEPS` step as the act recorded it (its words masked as recorded; its reads the
    read engine's references, `reads.read_entry`). No ``run``: it names no operation's run
    record (`incident_page.fixed_how` says nothing of it)."""
    now = time.time()
    kept = []
    for s in steps or []:
        if isinstance(s, dict) and s.get("step") in VERIFY_STEPS:
            kept.append(dict({k: s.get(k) for k in ("step", "result", "words", "at")},
                             **({"reads": list(s["reads"])} if s.get("reads") else {})))
    return {"act": decision.get("id") or "", "device": decision.get("device") or "",
            "at": _iso(now), "epoch": now, "verify": kept}


# ── What an act's outcome does to its incident (C3870, C3871) ───────────────────────────────

#: The act outcome that closes its incident (the operator, 2026-11-16: "Only 'healed' closes an
#: incident. Partial, symptom remains, rolled back, failed, refused, interrupted stay open,
#: stating the outcome"). An approved dampening's is its own (`dampening.finish`).
CLOSES = ("healed",)
#: A healed act whose tail then failed (`reopen_on_tail`): the standing outcome. The one name
#: (`fixit.auto` imports it).
TAIL_FAILED = "tail_failed"
#: A standing act outcome in Mercury's words (`OUTCOME_WORDS`, and the tail's).
STANDING_WORDS = dict(OUTCOME_WORDS, **{TAIL_FAILED: "fixed, and a step after it failed"})
#: What a tail failure stands on: its failed step, which no drift run's read at the golden
#: ends (`incidents.ends_at_golden` ends only ``departure``).
ON_TAIL = "tail"


def stands_on(outcome: str, inc: dict):
    """What an act's standing stands on (the review, finding 2): a tail failure on its step
    (`ON_TAIL`); an incident that names a symptom on it (``symptom``: closed only by Mercury's
    confirmation read, `request_confirm`); else None (its grace period's, `incidents.stand`)."""
    if outcome == TAIL_FAILED:
        return ON_TAIL
    return "symptom" if symptom_triggers((inc or {}).get("triggers") or []) else None


def outcome_on_incident(network: str, decision: dict, outcome: str, words: str, *,
                        fixed: dict = None, closes=CLOSES, said: dict = None) -> str:
    """THE one home of what an act's outcome does to its incident (C3870): an outcome in
    *closes* closes it, *fixed* its proof (`verified_of`); any other leaves it open, standing
    on the act (`incidents.stand` with ``act``, on what `stands_on` says), its outcome and words
    said in Mercury's words (*said*, `STANDING_WORDS` unless given); a healed act whose tail
    flagged before its outcome is recorded stands on `TAIL_FAILED`. Stamped when it is
    recorded (C3871: the time this is called, never the act's start). ``"closed"``,
    ``"stood"``, or why neither was recorded (logged; never raised: the outcome is recorded
    already)."""
    from modules.heal import incidents

    iid = (decision or {}).get("incident") or ""
    if not iid:
        return "no incident"
    at = time.time()
    try:
        if outcome in closes:
            incidents.close(network, iid, f"{outcome}: {words} (decision {decision['id']})", at,
                            fixed=fixed)
            return "closed"
        lead = (said or STANDING_WORDS).get(outcome, outcome)
        on = stands_on(outcome, _incident(network, iid))
        incidents.stand(network, iid, {"id": decision["id"], "outcome": outcome,
                                       "words": f"{lead}: {words}".rstrip(": "),
                                       "departure": decision.get("departure") or "",
                                       "mode": decision.get("mode") or ""},
                        now=at, on=on, act=True)
        return "stood"
    except Exception as exc:                          # noqa: BLE001 (said: logged)
        log.error("heal: %s's incident %s was not %s on %s (%s): %s", network, iid,
                  "closed" if outcome in closes else "left standing", decision.get("id"),
                  outcome, exc)
        return f"{type(exc).__name__}: {exc}"


def tail_failed_step(tail: dict) -> str:
    """The first tail step that did not pass (`TAIL_STEPS`), or ``""`` (it did not finish).
    The one reader of it (`fixit.auto.failures` too)."""
    return next((s.get("step") for s in (tail or {}).get("steps") or []
                 if s.get("result") not in ("ok", "running")), "") or ""


#: A refusal that is a guard working as designed (R2: "a guard or hold working as designed is
#: not a failure"): its step carries ``waits`` (`refuse`'s *waits*): the stops at apply (the
#: kill switch, the mode, the stage, the policy moved, a halt, planned work), the device held
#: past the wait's bound, the program moved since the decision, the device changed during the
#: heal. Its incident stands and is retried by the policy; R1 does not count it.
def refusal_waits(row: dict) -> bool:
    """Whether an ``act`` step-log row refused only by a guard that waits (`refuse`'s
    *waits*), so it is no failure R1 starts on (`fixit.auto.failures`)."""
    return (row or {}).get("outcome") == "refused" and any(
        isinstance(s, dict) and s.get("result") == "refused" and s.get("waits")
        for s in (row or {}).get("steps") or [])


def reopen_on_tail(network: str, decision: dict, tail: dict, steps=None) -> str:
    """A heal closed at Fixed whose tail then failed (the operator, 2026-11-16: "A failed
    save/golden tail step reopens the incident"): `incidents.reopen`, the flag its words.
    Only from a tail running in this code (past incidents are never reopened). The flag stays
    Needs attention's own row (`attention._heal_tail_rows`)."""
    from modules.heal import incidents

    del steps
    try:
        incidents.reopen(network, decision["incident"], decision["id"],
                         f"{STANDING_WORDS[TAIL_FAILED]}: {tail.get('flag') or ''}".rstrip(": "),
                         time.time(), step=tail_failed_step(tail),
                         departure=decision.get("departure") or "", on=ON_TAIL)
        return "reopened"
    except Exception as exc:                          # noqa: BLE001 (said: logged)
        log.error("heal: %s's incident %s was not reopened on its tail: %s", network,
                  decision.get("incident"), exc)
        return f"{type(exc).__name__}: {exc}"


def against_golden(golden_text: str, text: str, device: str) -> dict:
    """*text* (a device's read) judged against *golden_text* by drift's own comparison
    (`drift_check.drift_diff`): ``{"state": "clean"|"drifted", "changed_lines", "error"}``. The
    one comparison `Sources.read_at_golden` and `confirm_before_ai` make."""
    from modules import drift_check

    diff = drift_check.drift_diff(golden_text, text, device)
    n = drift_check.changed_lines(diff) if diff else 0
    return {"state": "drifted" if n else "clean", "changed_lines": n, "error": ""}


# ── The confirmation before AI troubleshooting (C3870) ──────────────────────────────────────

#: The failure kinds (`fixit.auto.failures`) whose device Mercury reads before any AI call.
CONFIRM_KINDS = ("act", "tail")
#: Who holds the device for the confirmation, and its step's name in the step log.
CONFIRM_BY = "Mercury's confirmation before AI troubleshooting"
CONFIRM_STEP = "confirm"
#: A confirmation's proof is marked so (``fixed.by``): `findings._fixes` counts no fix from it.
CONFIRM_MARK = "confirm"
#: How long a confirmation taken (``reading``) may stand before another may take it (its thread
#: died, or it raised): about 2.5 times the longest it can take, reasoned, not measured: the
#: hold's wait (`HOLD_WAIT_S`, 335 s), the symptom's longest bound (`SYMPTOM_SECONDS`' alert,
#: 750 s), and a minute for the device's reads.
CONFIRM_BOUND_S = round(2.5 * (HOLD_WAIT_S + max(SYMPTOM_SECONDS.values()) + 60))
#: An unreadable confirmation is tried again at most this often (the review, finding 10).
CONFIRM_UNREAD_AGAIN_S = 3600
#: The tail steps the confirmation can check by a read: the save (startup boots what runs,
#: Reload's own gate) and the golden's commit and read again (the device at its golden,
#: `Sources.read_at_golden`, the golden step's own check). A tail that did not finish names no
#: step: never proof.
CONFIRM_TAIL_STEPS = ("saved", "commit", "golden")


def _act_began(network: str, decision: dict) -> tuple:
    """``(epoch, last act row)``: when *decision*'s act began (its first ``started`` or ``act``
    row), else the decision's own time; and its newest ``act`` row, or ``{}``."""
    from modules.heal import steplog

    got = steplog.of_decision(network, decision.get("id") or "")
    rows = [r for r in got.get("rows") or [] if r.get("row") in ("started", "act")]
    began = min([float(r.get("epoch") or 0) for r in rows if r.get("epoch")]
                or [float(decision.get("epoch") or 0)])
    last = next((r for r in reversed(rows) if r.get("row") == "act"), {})
    return began, last


def _saved_read(dev: dict, device: str) -> dict:
    """Whether *device* boots what it runs, read on one session as Reload's gate reads it
    (`reload_op.read_boot_pair`: the running configuration, `show startup-config`, and `dir
    nvram:` where startup keeps a certificate there) and judged as it judges it
    (`roundtrip.startup_is_running`): ``{"state": "pass"|"fail"|"unread", "words"}``. A read;
    nothing is sent but reads."""
    from modules.connection import with_temp_connection
    from modules.nsot import reload_op, roundtrip

    try:
        pair = with_temp_connection(dev, lambda conn: reload_op.read_boot_pair(conn, device))
    except Exception as exc:                          # noqa: BLE001 (said: unread, no proof)
        return {"state": "unread", "words": f"its startup could not be read ({exc})"}
    if not (pair or {}).get("startup") or not (pair or {}).get("running"):
        return {"state": "unread", "words": "its startup or running configuration read empty"}
    same = roundtrip.startup_is_running(pair["startup"], pair["running"], pair.get("nvram") or "")
    if same.get("equal"):
        return {"state": "pass", "words": "startup holds what it runs, so the save held"}
    return {"state": "fail", "words": (
        f"startup does not hold what it runs ({len(same.get('only_right') or [])} running "
        "line(s) not in startup), so the save did not hold")}


def _confirm_read(network: str, src, device: str, tail_step: str = None,
                  check_saved: bool = False) -> dict:
    """*device* read, held as the act holds it (`hold_device`; released before anything is
    waited on), by the act's own confirmation (`Sources.read_at_golden`: its one read, its
    golden and its compare), the golden itself at its intent (`Sources.golden`'s state, no
    second compare): ``{"state": "pass"|"fail"|"unread", "words", "at"}``. *tail_step* (a tail
    failure's failed step, `tail_failed_step`): that step checked by a read too (the review,
    finding 8): ``saved`` by startup holding what runs (`_saved_read`); ``commit`` and
    ``golden`` by the read at the golden itself; ``""`` (it did not finish) or any other step
    is never proof. *check_saved* (the second review, B: an act whose save to startup was held,
    failed or not reached, `_save_done`): the save checked by the same read (`_saved_read`).
    Nothing is sent: reads only."""
    from modules.nsot import device_ops

    dev = src.device(device) or {}
    if not dev:
        return {"state": "unread", "at": _iso(time.time()),
                "words": f"{device} is not in the network's inventory, so it was not read"}
    if tail_step is not None and tail_step not in CONFIRM_TAIL_STEPS:
        return {"state": "unread", "at": _iso(time.time()), "words": (
            f"its tail's failed step ({tail_step or 'not recorded: it did not finish'}) cannot "
            "be checked by a read, so no read proves it")}
    busy = hold_device(network, device, dev.get("ip", ""), CONFIRM_BY, CONFIRM_BY,
                       clock=getattr(src, "clock", time.time),
                       sleep=getattr(src, "sleep", time.sleep))
    if busy:
        return {"state": "unread", "at": _iso(time.time()), "words": busy}
    try:
        golden = src.golden(device, dev)
        if golden.get("state") != "at_intent":
            return {"state": "fail", "at": _iso(time.time()), "words": (
                f"{device}'s golden is not at its intent now "
                f"({golden.get('words') or golden.get('state')}), so a read at it proves nothing")}
        got = src.read_at_golden(device, dev)
        at = _iso(time.time())
        saved = _saved_read(dev, device) if (tail_step == "saved" or check_saved) and \
            got.get("state") == "clean" else None
    finally:
        device_ops.release(network, device)
    commit = (golden.get("commit") or "")[:10] or "its committed golden"
    if got.get("state") == "unknown":
        return {"state": "unread", "at": at, "words": (
            f"{device} could not be read against its golden ({got.get('error') or 'unknown'})")}
    if got.get("state") != "clean":
        return {"state": "fail", "at": at, "words": (
            f"{device} read at {at}: {got.get('changed_lines')} line(s) differ from its golden "
            f"{commit}")}
    words = (f"{device} read at {at}, holding it: at its golden {commit}, which is at its "
             "intent, so every healed unit is at intent")
    if saved is not None:
        if saved["state"] != "pass":
            return {"state": saved["state"], "at": at, "words": f"{words}; but {saved['words']}"}
        words = f"{words}; {saved['words']}"
    return {"state": "pass", "at": at, "words": words}


def _save_done(network: str, decision: dict) -> bool:
    """Whether *decision*'s act recorded its save to startup done (a ``saved`` step ``ok`` in
    any of its step-log rows); False when held, failed, not reached or unreadable (B)."""
    from modules.heal import steplog

    got = steplog.of_decision(network, (decision or {}).get("id") or "")
    return any(isinstance(s, dict) and s.get("step") == "saved" and s.get("result") == "ok"
               for r in got.get("rows") or [] for s in r.get("steps") or [])


def _confirm_port(network: str, inc: dict, device: str):
    """The second review, A: for an incident whose problem is a port's (a trigger of
    `incidents.PORT_EVENT_KINDS`), its port's own state read again through the read the
    standing path judges it by (`errdisable.confirm`, judged by `detect._port_found`):
    ``{"state": "gone"|"present"|"unreadable", "words"}``, or None for no port problem. A port
    not classified, or a read missing or unreadable, is never proof."""
    from modules.heal import errdisable, incidents
    from modules.heal.detect import _port_found

    if not any(t.get("kind") in incidents.PORT_EVENT_KINDS
               for t in (inc or {}).get("triggers") or []):
        return None
    c = errdisable.of_record(inc)
    if c.get("state") != "classified":
        return {"state": "unreadable", "words": (
            "its port problem is not classified, so its port's state cannot be read: no proof")}
    try:
        conf = errdisable.confirm(network, device, c)
    except Exception as exc:                          # noqa: BLE001 (said: no proof)
        return {"state": "unreadable", "words": f"{errdisable.CONFIRM_READ} raised {exc}"}
    found = _port_found(dict(c, confirmed=conf))
    port = c.get("short") or c.get("port") or "its port"
    if found is False:
        return {"state": "gone", "words": (
            f"{errdisable.CONFIRM_READ} at {conf.get('at') or '?'} does not list {port}: its "
            "port is clear")}
    if found is True:
        return {"state": "present", "words": (
            f"{errdisable.CONFIRM_READ} at {conf.get('at') or '?'}: {port} is still "
            "err-disabled")}
    return {"state": "unreadable", "words": (
        f"{port}'s state could not be read clear ({conf.get('why') or 'no answer'}): no proof")}


def _confirm_device(network: str, sources, decision: dict, device: str,
                    triggers: list, tail_step: str = None, inc: dict = None) -> dict:
    """The confirmation's reads (`_confirm_read`, then the symptom read again, newer than this
    confirmation's own start, within its own bound: `read_symptom` as an act's verify reads it;
    the review, finding 7): ``{"fixed", "read", "symptom", "sym", "last"}``, *fixed* True only
    when the device is at its golden (at its intent), any failed tail step checked by a read,
    and its symptom gone or none named; a read not made since it began is unreadable, never
    proof. *sym* is the symptom's step as a proof keeps it; *last* the act's newest step-log
    row. Never raises."""
    try:
        src = sources or Sources(network)
        _began, last = _act_began(network, decision)
        began = time.time()
        read = _confirm_read(network, src, device, tail_step,
                             check_saved=not _save_done(network, decision))
        if read["state"] == "pass":
            s = read_symptom(network, device, triggers, began,
                             clock=getattr(src, "clock", time.time),
                             sleep=getattr(src, "sleep", time.sleep))
            # A port problem's own state too (A): anything but clear is no proof.
            port = _confirm_port(network, inc, device)
            if port is not None and (port["state"] != "gone" or s["state"] in ("gone", "none")):
                s = dict(port, reads=list(s.get("reads") or []),
                         words=(f"{s.get('words') or ''}; {port['words']}".lstrip("; ")
                                if port["state"] == "gone" else port["words"]))
        else:
            s = {"state": "not read", "words": "not read: the device read gave no proof",
                 "reads": []}
    except Exception as exc:                          # noqa: BLE001 (said: no proof)
        read = {"state": "unread", "at": _iso(time.time()),
                "words": f"the confirmation raised {type(exc).__name__}: {exc}"}
        s, last = {"state": "not read", "words": "not read", "reads": []}, {}
    fixed = read["state"] == "pass" and s["state"] in ("gone", "none")
    sym = {"step": "symptom", "result": "ok" if fixed else s["state"],
           "words": s.get("words") or "", "at": _iso(time.time()),
           **({"reads": list(s["reads"])} if s.get("reads") else {})}
    return {"fixed": fixed, "read": read, "symptom": s, "sym": sym, "last": last}


def _confirm_proof(decision_id: str, device: str, read: dict, sym: dict, words: str,
                   at: float) -> dict:
    """The confirmation's proof in `verified_of`'s shape, its two deciding steps
    (`DECIDING_STEPS`, drawn by `fixit.proof.of_act`): the healed units at intent (the device
    at its golden, which is at its intent), its words leading with *words* ("already fixed;
    confirmation was blocked (...)"), and the symptom."""
    return {"act": decision_id, "device": device, "at": _iso(at), "epoch": at,
            # Marked a confirmation (`CONFIRM_MARK`): `findings._fixes` counts no fix from it.
            "by": CONFIRM_MARK, "read_by": CONFIRM_BY, "words": words,
            "verify": [{"step": "intent", "result": "ok", "words": f"{words}: {read['words']}",
                        "at": read["at"]}, dict(sym)]}


def _tail_step_of(network: str, decision: dict, standing: dict):
    """A tail failure's failed step (`tail_failed_step`, from its act row's tail record, or its
    standing's own ``step``), for `_confirm_read`; None for any other standing."""
    if (standing or {}).get("outcome") != TAIL_FAILED:
        return None
    _began, last = _act_began(network, decision)
    return (tail_failed_step((last.get("records") or {}).get("tail"))
            or (standing or {}).get("step") or "")


def confirm_before_ai(network: str, key: str, *, sources=None) -> dict:
    """C3870 (the operator, 2026-11-16: "Confirm-first: the deterministic own-device read
    before any AI call"): for a failure of an act or a tail (*key* ``act:<decision>`` or
    ``tail:<decision>``, `fixit.auto.failures`), before anything asks the AI, its device is
    read through Mercury's own read, held as the act holds it (`_confirm_read`: at its golden,
    which is at its intent; a tail failure's failed step checked by a read too), and its
    symptom read again, newer than the confirmation's own start (`read_symptom`, within its
    own bound; none named passes). Both pass:
    the incident closes on that read as its proof (`decide.end_standing`, its ``fixed`` in
    `verified_of`'s shape), "already fixed; confirmation was blocked (<the act's why>)".
    Either fails, or a read is unreadable or refused: no proof, and the read is kept as the
    act's ``confirm`` step in the step log, so the AI's evidence holds it (`evidence_pack.
    tried_section`) beside the failure. ``{"state", "words"}``, *state* ``closed``,
    ``closed_already`` (it closed before the AI was asked: nothing to ask), ``not_fixed``,
    ``not_standing`` (moved since: judged as before), ``unread`` or ``skipped`` (another kind
    of failure). Never raises."""
    from modules.heal import decide, decisions, steplog

    kind, _sep, decision_id = str(key or "").partition(":")
    if kind not in CONFIRM_KINDS or not decision_id:
        return {"state": "skipped", "words": ""}
    try:
        d = decisions.find(network, decision_id)
        inc = _incident(network, d.get("incident") or "")
    except Exception as exc:                          # noqa: BLE001 (said: the AI is asked)
        return {"state": "unread", "words": f"decision {decision_id} could not be read: {exc}"}
    if not inc:
        return {"state": "unread", "words": f"{d.get('incident') or 'its incident'} is not held"}
    if inc.get("state") == "closed":
        return {"state": "closed_already", "words": (
            f"{inc['id']} closed before the AI was asked: "
            f"{inc.get('closed_why') or 'no why was recorded'}")}
    standing = inc.get("standing") or {}
    if inc.get("state") != "standing" or not standing.get("act"):
        return {"state": "not_standing", "words": (
            f"{inc['id']} is {inc.get('state')}, not standing on its act, so it was not "
            "confirmed before the AI was asked")}
    device = d.get("device") or inc.get("device") or ""
    got = _confirm_device(network, sources, d, device, inc.get("triggers") or [],
                          _tail_step_of(network, d, standing), inc=inc)
    read, s, sym, last = got["read"], got["symptom"], got["sym"], got["last"]
    blocked = (standing.get("words") or STANDING_WORDS.get(standing.get("outcome"), ""))[:200]
    if got["fixed"]:
        words = f"already fixed; confirmation was blocked ({blocked})"
        at = time.time()
        ended = decide.end_standing(network, inc["id"], words, now=at, by=CONFIRM_BY,
                                    read_words=f"{read['words']}; {sym['words']}",
                                    fixed=_confirm_proof(decision_id, device, read, sym, words,
                                                         at))
        if ended:
            return {"state": "closed", "words": words, "decision": ended.get("id"),
                    "proof": f"{read['words']}; {sym['words']}"}
        return {"state": "not_standing", "words": f"{inc['id']} moved while it was read"}
    said = (f"Mercury read {device} before asking the AI: {read['words']}; its symptom: "
            f"{sym['words']}: no proof it is fixed")
    if last:
        try:
            steplog.record_act(network, d, {
                "outcome": last.get("outcome") or "", "words": last.get("words") or "",
                "sent": bool(last.get("sent")), "records": dict(last.get("records") or {}),
                "steps": [{"step": CONFIRM_STEP, "result": (
                    "unreadable" if read["state"] == "unread"
                    or (read["state"] == "pass" and s["state"] == "unreadable")
                    else "failed"),
                    "words": said, "at": _iso(time.time())}]},
                by=last.get("by") or CONFIRM_BY, policy_by=last.get("policy_by") or "",
                now=time.time())
        except Exception as exc:                      # noqa: BLE001 (said: logged)
            log.error("heal: %s's confirmation of %s is not in the step log: %s", network,
                      decision_id, exc)
    return {"state": "not_fixed", "words": said,
            "unread": read["state"] == "unread"
            or (read["state"] == "pass" and s["state"] in ("unreadable", "stale"))}


#: The closed outcomes `confirm_closed` reads (C3876): a heal act's that are not healed
#: (`steplog.NOT_HEALED` among `OUTCOMES`), closed before C3870 kept such an incident open.
CLOSED_UNPROVEN = tuple(o for o in OUTCOMES if o != "healed" and o != "refused")


def confirm_due(rec: dict, now: float, *, wanted: bool) -> bool:
    """Whether a confirmation record (*rec*: ``{"state", "epoch"}``) may be taken now (the
    review, finding 10): ``wanted`` (asked for, `request_confirm`); ``reading`` past
    `CONFIRM_BOUND_S` (its thread died, or it raised); ``unread`` past
    `CONFIRM_UNREAD_AGAIN_S`. No record: a closed incident's first (*wanted* False), never a
    standing one's (it waits to be asked)."""
    if not rec:
        return not wanted
    age = float(now) - float(rec.get("epoch") or 0)
    return (rec.get("state") == "wanted"
            or (rec.get("state") == "reading" and age >= CONFIRM_BOUND_S)
            or (rec.get("state") == "unread" and age >= CONFIRM_UNREAD_AGAIN_S))


def _closed_unproven(inc: dict, now: float = None) -> str:
    """The decision a closed incident's close names when it closed on an act outcome that is
    not healed (`CLOSED_UNPROVEN`, its ``closed_why`` "<outcome>: ... (decision <id>)"), with no
    proof kept (no ``fixed``) and a confirmation due (`confirm_due` of its
    ``confirmed_closed``); else ``""``."""
    import re

    from modules.heal import steplog

    now = time.time() if now is None else float(now)
    why = str(inc.get("closed_why") or "")
    outcome = why.split(":", 1)[0]
    if (inc.get("state") != "closed" or inc.get("fixed")
            or not confirm_due(inc.get("confirmed_closed"), now, wanted=False)
            or outcome not in CLOSED_UNPROVEN or outcome not in steplog.NOT_HEALED):
        return ""
    m = re.search(r"\(decision ([\w-]+)\)\s*$", why)
    return m.group(1) if m else ""


def _standing_wanted(inc: dict, now: float = None) -> bool:
    """Whether a standing act incident waits for its confirmation (`request_confirm`)."""
    now = time.time() if now is None else float(now)
    return (inc.get("state") == "standing" and bool((inc.get("standing") or {}).get("act"))
            and confirm_due(inc.get("confirm_wanted"), now, wanted=True))


def request_confirm(network: str, incident_id: str, why: str) -> bool:
    """The review's finding 2 (an incident a heal could not confirm ends only with proof):
    where a close of a STANDING ACT would have been made (a drift run at the golden, the
    symptom read gone, a re-decision of nothing to heal), it is not closed: its confirmation is
    asked for instead (``confirm_wanted``, *why*), and the confirm pass (`confirm_closed`, on
    its own thread) reads its device and closes it with that read as its proof, or leaves it
    standing. Returns whether it was asked. Never raises."""
    from modules.heal import incidents

    try:
        asked = incidents.want_confirm(network, incident_id, why,
                                       again_s=CONFIRM_UNREAD_AGAIN_S)
    except Exception as exc:                          # noqa: BLE001 (said: logged)
        log.error("heal: %s's %s: its confirmation was not asked for: %s", network,
                  incident_id, exc)
        return False
    if asked:
        confirm_closed_soon(network)
    return bool(asked)


def confirm_closed(network: str, *, sources=None) -> list:
    """C3876 (the operator, 2026-11-16: "no reopen of past incidents; r6 stays closed"): each
    incident already closed on a heal act's outcome that is not healed, with no proof
    (`_closed_unproven`), confirmed ONCE by the same read as `confirm_before_ai`
    (`_confirm_device`: its device held and read at its golden, at its intent, and its symptom
    read once), deterministically, with no AI. Taken first under the incidents store's lock
    (`incidents.claim_confirm`), so it never runs twice, in any process. At intent with its
    symptom clear, the read is kept on the closed incident as its proof (``fixed``, in
    `verified_of`'s shape, "already fixed; confirmation was blocked (<the act's why>)"), and
    the incident page reads it Fixed; its state, ``closed_at`` and ``closed_why`` are
    untouched (no reopen). Otherwise nothing changes but the record of the try
    (``confirmed_closed``), and it stays Needs a person. Returns ``[{"incident", "state"}]``.

    The same pass confirms each STANDING act incident whose confirmation was asked for
    (`request_confirm`): `confirm_before_ai`'s own read and close, nothing asked of the AI.
    A taken confirmation that never ended is taken again past `CONFIRM_BOUND_S`, an unreadable
    one at most once an hour (`confirm_due`). Nothing runs while self-healing is Off on the
    network. Never raises."""
    from modules.heal import decisions, incidents, policy

    out = []
    try:
        if policy.current(network).get("mode") == "off":
            return out
    except Exception as exc:                          # noqa: BLE001 (said: an unread mode holds)
        log.error("heal: %s's mode could not be read for the confirm pass: %s", network, exc)
        return out
    got = incidents.read(network)
    if got["state"] != "ok":
        return out
    for inc in got["incidents"]:
        if not _standing_wanted(inc):
            continue
        try:
            if not incidents.claim_confirm(network, inc["id"], field="confirm_wanted",
                                           due=lambda i, t: _standing_wanted(i, t)):
                continue
            s = inc.get("standing") or {}
            kind = "tail" if s.get("outcome") == TAIL_FAILED else "act"
            r = confirm_before_ai(network, f"{kind}:{s.get('decision') or ''}")
            state = {"closed": "fixed", "closed_already": "closed"}.get(
                r["state"], "unread" if r.get("unread") or r["state"] == "unread"
                else "not_fixed")
            incidents.record_confirm(network, inc["id"], {
                "state": state, "by": CONFIRM_BY, "decision": s.get("decision") or "",
                "words": (r.get("words") or "")[:400]}, field="confirm_wanted")
            out.append({"incident": inc["id"], "state": state})
        except Exception as exc:                      # noqa: BLE001 (said: logged)
            log.error("heal: %s's standing incident %s was not confirmed: %s: %s", network,
                      inc.get("id"), type(exc).__name__, exc)
    for inc in got["incidents"]:
        decision_id = _closed_unproven(inc)
        if not decision_id:
            continue
        try:
            taken = incidents.claim_confirm(
                network, inc["id"], due=lambda i, t: bool(_closed_unproven(i, t)))
            if not taken:
                continue
            d = decisions.find(network, decision_id)
            device = d.get("device") or inc.get("device") or ""
            c = _confirm_device(network, sources, d, device, inc.get("triggers") or [],
                                inc=inc)
            why = (str(inc.get("closed_why") or "").split(" (decision ")[0])[:200]
            words = f"already fixed; confirmation was blocked ({why})"
            at = time.time()
            fixed = (_confirm_proof(decision_id, device, c["read"], c["sym"], words, at)
                     if c["fixed"] else None)
            state = "fixed" if c["fixed"] else (
                "unread" if c["read"]["state"] == "unread"
                or c["symptom"]["state"] == "unreadable" else "not_fixed")
            incidents.record_confirm(network, inc["id"], {
                "state": state, "by": CONFIRM_BY, "decision": decision_id,
                "words": (words if fixed else
                          f"no proof it is fixed: {c['read']['words']}; its symptom: "
                          f"{c['sym']['words']}")[:400]}, fixed=fixed, now=at)
            out.append({"incident": inc["id"], "state": state})
        except Exception as exc:                      # noqa: BLE001 (said: logged)
            log.error("heal: %s's closed incident %s was not confirmed: %s: %s", network,
                      inc.get("id"), type(exc).__name__, exc)
    return out


def confirm_closed_soon(network: str) -> bool:
    """`confirm_closed` on its own thread when *network* holds an incident it would read (one
    read of the incidents store; nothing else), so the detect pass is never held by a device
    read or its hold's wait. Returns whether a thread was started."""
    import threading

    from modules.heal import incidents

    got = incidents.read(network)
    if got["state"] != "ok" or not any(_closed_unproven(i) or _standing_wanted(i)
                                       for i in got["incidents"]):
        return False

    def go():
        try:
            confirm_closed(network)
        except Exception as exc:                      # noqa: BLE001 (said: logged)
            log.error("heal: %s's closed incidents were not confirmed: %s", network, exc)
    threading.Thread(target=go, name=f"heal-confirm-closed-{network}", daemon=True).start()
    return True


def live_steps(steps: list, declared, run_id: str = "", labels: dict = None,
               device: str = ""):
    """``(step, begin)`` over *steps*, a run's own list: `step(name, result, words)` records a
    step as before (*more* kept on it: the reads a step made, `reads.read_entry`);
    `begin(name, words, wait_s=None, bound=False, wait_for="")` records one that takes time
    as ``running`` the moment it starts (with ``began``, and its declared wait: a fixed length,
    or with *bound* the longest it waits; *wait_for*, what it waits for when its stage says it:
    ``heartbeat``, C3164), and that step's own `step` then replaces it, keeping when it began.
    So the recorded list ends as it always did, and while the run goes on its newest step is
    the one it is in. Inside a job the list is the job's own
    (`op_progress.attach`, with the operation's short *labels* for *device*): each step
    written is announced. Used by a heal's act and by an approved proposal's."""
    from modules import op_progress, run_stepper
    from modules.redact import redact_text

    op_progress.attach(declared, steps, run=run_id,
                       labels=run_stepper.labels_for(labels, device=device))

    def begin(name, words, *, wait_s=None, bound=False, wait_for=""):
        at = _iso(time.time())
        steps.append(dict({"step": name, "result": "running", "words": redact_text(words),
                           "at": at, "began": at},
                          **({"wait_s": wait_s, "wait_bound": bool(bound)} if wait_s else {}),
                          **({"wait_for": wait_for} if wait_for else {})))
        op_progress.moved()

    def step(name, result, words, **more):
        ended = dict({"step": name, "result": result, "words": redact_text(words),
                      "at": _iso(time.time())}, **more)
        last = steps[-1] if steps else {}
        if last.get("step") == name and last.get("result") == "running" and last.get("began"):
            # The step `begin` opened: ended in place, with when it began and what it waited.
            steps[-1] = dict(ended, **{k: last[k] for k in ("began", "wait_s", "wait_bound",
                                                            "wait_for") if k in last})
        else:
            steps.append(ended)
        op_progress.moved()

    return step, begin


def _not_deployed(r, report, step, finish):
    """The apply's end when it did not deploy (refused, changed during the heal, rolled back,
    failed), finished; None when it deployed. One reading for `_judge` and `_judge_tail`."""
    from modules.nsot import receipts
    from modules.nsot.deploy import DEPLOYED, SKIPPED_DRIFTED

    outcome = r.get("outcome") or "refused"
    if outcome == SKIPPED_DRIFTED:
        # The device changed during the heal: a guard working as designed (`refusal_waits`).
        step("apply", "refused", r.get("reason") or "", waits=True)
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
    return None


def _read_again(src, device, dev, via) -> dict:
    """The device read again against its new golden: its own read (`Sources.read_at_golden`,
    item 1), never the network's drift check; a source without it (an older one) asks
    `golden_recheck`. What raises is ``unknown``: neither a pass nor a fail."""
    try:
        own = getattr(src, "read_at_golden", None)
        if own is not None:
            return own(device, dev if dev is not None else src.device(device))
        return src.golden_recheck(device, via)
    except Exception as exc:                          # noqa: BLE001 (said: unknown)
        return {"state": "unknown", "error": f"{type(exc).__name__}: {exc}"}


def tail_of(device: str, outcome: str, steps: list, flags: list, *,
            running: bool = False) -> dict:
    """The tail's record (the act row's ``records["tail"]``; decisions (a) and (b)): ``{"state":
    "running"|"ok"|"flagged", "flag", "steps": [{"step", "result", "words", "at"}]}``, its
    steps those of `TAIL_STEPS`. *flags* (each "its save to startup failed: <why>", "its golden
    was not committed: <why>", "the device read again is not at its golden: <what>") make it
    ``flagged``, its *flag* the incident's words: "r2 fixed, but its save to startup failed:
    ...". Never changes the outcome."""
    kept = [{k: s.get(k) for k in ("step", "result", "words", "at")}
            for s in steps or [] if isinstance(s, dict) and s.get("step") in TAIL_STEPS]
    if running:
        return {"state": "running", "flag": "", "steps": kept, "began": time.time()}
    if not flags:
        return {"state": "ok", "flag": "", "steps": kept}
    # A healed line gone again is the fix not holding: never led by "fixed" (the review of
    # 2026-11-16, its words contradicting the flag).
    gone = any(f.startswith("its healed line is no longer on the device") for f in flags)
    lead = (f"{device}'s fix did not hold: " if gone else
            f"{device} fixed, but " if outcome == "healed" else
            f"{device} ({OUTCOME_WORDS.get(outcome, outcome)}), and ")
    return {"state": "flagged", "flag": lead + "; and ".join(flags), "steps": kept}


#: Each tail step on the incident card (the operator, 2026-11-16): its words while it runs,
#: and once it passed.
TAIL_WORDS = {"saved": ("Saving to startup…", "Saved"),
              "commit": ("Committing the golden…", "Golden committed"),
              "golden": ("Checking the golden…", "Check golden: at its golden")}


def tail_bound() -> int:
    """How long a tail may stay ``running`` after Fixed before it is drawn as not finished
    (`waits.HEAL_BOUNDS["tail-finish"]`, about 2.5 times its parts, reasoned, to be measured
    by the heal's laps)."""
    from modules.waits import HEAL_BOUNDS

    return int(HEAL_BOUNDS["tail-finish"]["seconds"])


def _live_tail(network: str, device: str):
    """The tail steps of *device*'s heal job running in this process now (`op_progress`),
    or None when none runs here."""
    from modules import op_progress
    from modules.nsot import capture_job

    job = next((j for j in capture_job.card_jobs() if j["state"] == "running"
                and j["kind"] == KIND and j["list"] == network and j["device"] == device), None)
    live = op_progress.run_of(job["job"]) if job else None
    if not live:
        return None
    return [s for s in live["steps"] if s.get("step") in TAIL_STEPS]


def _last_tail_step(network: str, device: str, since: float) -> str:
    """The last tail step *device*'s hold recorded before its process ended
    (`device_ops.interrupted`: the act notes each, ``tail: <step>``), in words, or ``""``."""
    from modules.nsot import device_ops

    try:
        left = [r for r in device_ops.interrupted(network) if r.get("device") == device
                and float(r.get("started") or 0) <= since + tail_bound()]
    except Exception as exc:                          # noqa: BLE001 (said: not recorded)
        log.info("heal: %s's interrupted holds were not read: %s", network, exc)
        return ""
    for r in reversed(left):
        step = str(((r.get("progress") or {}).get("step")) or "")
        if step.startswith("tail: "):
            return TAIL_WORDS.get(step[6:], (step[6:],))[0]
    return ""


def tail_stale(device: str, tail: dict, now: float, last: str = "") -> str:
    """Why a tail recorded ``running`` did not finish, or ``""`` (not past its bound): "r2's
    save and golden did not finish (<its last step>)"."""
    began = float((tail or {}).get("began") or 0)
    if (tail or {}).get("state") != "running" or not began or now - began < tail_bound():
        return ""
    return (f"{device}'s save and golden did not finish ("
            + (f"its last step: {last}" if last else "its last step is not recorded")
            + f"; still running {round(now - began)} s after Fixed, past its "
              f"{tail_bound()} s bound)")


def tail_card(network: str, device: str, entry: dict, now: float = None) -> dict:
    """The tail under Fixed on the incident card: ``{"state": "running"|"ok"|"flagged",
    "flag", "steps": [{"key", "state", "words"}]}``, every `TAIL_STEPS` step in order (one not
    begun ``pending``), live from the act's own steps while its job runs here, else from its
    record (`tail_of`); a ``running`` record past its bound (`tail_stale`) is drawn flagged.
    ``{}`` for an act with no tail (one recorded before it)."""
    import re

    now = time.time() if now is None else float(now)
    tail = ((entry or {}).get("records") or {}).get("tail") or {}
    if not tail:
        return {}
    live = _live_tail(network, device) if tail.get("state") == "running" else None
    steps = live if live is not None else list(tail.get("steps") or [])
    by = {s.get("step"): s for s in steps}
    out = []
    for key in TAIL_STEPS:
        s = by.get(key)
        if s is None:
            out.append({"key": key, "state": "pending", "words": TAIL_WORDS[key][0]})
            continue
        result = s.get("result") or ""
        if result == "running":
            out.append({"key": key, "state": "running", "words": TAIL_WORDS[key][0]})
        elif result == "ok":
            sha = re.search(r"Golden committed: (\w+)", s.get("words") or "")
            out.append({"key": key, "state": "ok", "words": (
                f"Golden committed: {sha.group(1)}" if key == "commit" and sha
                else TAIL_WORDS[key][1])})
        else:
            out.append({"key": key, "state": "failed", "words": s.get("words") or result})
    state, flag = tail.get("state") or "", tail.get("flag") or ""
    if state == "running" and live is None:
        # Its act running in another process holds its decision's mark (a lock file): still
        # running, never drawn as not finished (the review, finding 7).
        from modules.heal import interrupted
        try:
            if interrupted.mark_state(network, (entry.get("decisions") or [""])[-1])[0] == \
                    "held":
                return {"state": "running", "flag": "", "steps": out}
        except Exception as exc:                      # noqa: BLE001 (judged by its bound)
            log.info("heal: %s's tail mark could not be read: %s", device, exc)
        flag = tail_stale(device, tail, now, _last_tail_step(network, device,
                                                             float(tail.get("began") or 0)))
        state = "flagged" if flag else "running"
    return {"state": state, "flag": flag, "steps": out}


def tail_holds(network: str, device: str, epoch: float, now: float = None) -> str:
    """Why a departure of *device* read at *epoch* is not sighted, or ``""`` (round 2, item 3:
    the incident closes at Fixed, before its golden is committed): the newest heal of it read
    the device after *epoch*, so that read's departure is the one it healed. A read made after
    the heal's own is sighted as usual. Read from the step log, never the device."""
    from modules.heal import steplog

    got = steplog.incidents(network, device)
    if got.get("state") == "unreadable":
        return ""
    for e in reversed(got.get("entries") or []):
        tail = (e.get("records") or {}).get("tail") or {}
        if not tail:
            continue
        # Only a read made before the heal's own read at apply is the departure it healed (the
        # review, finding 8): one made after it, a real change made by hand during the tail
        # among them, is sighted as usual (the tail's check keeps a revert out of the golden).
        read_at = max([_epoch_of(s.get("at")) for s in e.get("steps") or []
                       if s.get("step") == "read" and s.get("result") == "ok"
                       and s.get("row") in ("act", "started")] or [0.0])
        if read_at and float(epoch or 0) < read_at:
            return (f"read at {_iso(float(epoch or 0))}, before {device}'s heal read it at "
                    f"{_iso(read_at)}: the departure it healed")
        return ""
    return ""


def _epoch_of(iso) -> float:
    import calendar

    try:
        return float(calendar.timegm(time.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return 0.0


def reap_tails(network: str, *, now: float = None, by: str = "heal to intent") -> list:
    """Each heal tail of *network* still recorded ``running`` past its bound whose act no
    longer runs (`interrupted.mark_state` not ``held``: its job ended, a restart among the
    causes), recorded flagged with `tail_stale`'s words as a closing ``act`` row, so its
    incident's card and Needs attention say it (`run` asks it at every pass, the first after
    a restart included). Returns the decisions marked. Never raises."""
    from modules.heal import decisions, interrupted, steplog

    now = time.time() if now is None else float(now)
    marked = []
    try:
        got = steplog.incidents(network)
    except Exception as exc:                          # noqa: BLE001 (the next pass)
        log.error("heal: %s's step log could not be read for tails: %s", network, exc)
        return marked
    for e in got.get("entries") or []:
        tail = (e.get("records") or {}).get("tail") or {}
        decision_id = (e.get("decisions") or [""])[-1]
        device = e.get("device") or ""
        if tail.get("state") != "running" or not decision_id:
            continue
        began = float(tail.get("began") or 0)
        try:
            if interrupted.mark_state(network, decision_id)[0] == "held":
                continue
        except Exception as exc:                      # noqa: BLE001 (the next pass)
            log.info("heal: %s's mark for %s could not be read: %s", network, decision_id, exc)
            continue
        words = tail_stale(device, tail, now, _last_tail_step(network, device, began))
        if not words:
            continue
        try:
            d = next((x for x in decisions.decisions(network) if x.get("id") == decision_id),
                     {"id": decision_id, "device": device, "incident": e.get("incident")})
            steplog.record_act(network, d, {
                "outcome": e.get("outcome") or "", "words": e.get("words") or "", "steps": [],
                "sent": True, "records": dict(e.get("records") or {}, tail=dict(
                    tail, state="flagged", flag=words, ended=_iso(now)))}, by=by, now=now)
            marked.append(decision_id)
        except Exception as exc:                      # noqa: BLE001 (the next pass)
            log.error("heal: %s's unfinished tail on %s was not recorded: %s", network,
                      device, exc)
    return marked


def _judge_tail(device, r, report, src, via, step, finish, symptom, dev, *, begin=None,
                more=None, declared=None, release=None):
    """The act's end once THE apply returned (decisions (a) and (b)): the tail's steps as they
    ended (the save, the golden commit from the full read), then the device read again, its
    own read, against its new golden; then, where the outcome was not recorded at Fixed
    (`declared`), the symptom and the outcome. A tail failure or a mismatch is a flag on the
    incident (`tail_of`), never the outcome."""
    done = _not_deployed(r, report, step, finish)
    if done is not None:
        return done
    saved = r.get("saved_startup") or {}
    # The tail drew its save as it ran (`pipeline.run_tail`); an apply without one did not.
    drawn = bool(r.get("tail"))
    flags = []
    held_why = ""
    if not r.get("commands"):
        pass                                          # nothing was sent: nothing to save
    elif saved.get("held"):
        # C2701: verify did not pass, so the save is held for a person; no outcome was recorded
        # at Fixed (a verify that did not pass is never Fixed). Its golden is still committed
        # (stage 8.5 runs after a verify that did not fail), so the commit is drawn below.
        held_why = saved.get("why") or "no cause recorded"
        if not drawn:
            step("saved", "partial",
                 f"NOT saved to startup, held: verify did not pass ({held_why})")
    elif not saved.get("ok"):
        why = saved.get("error") or "the save did not run"
        flags.append(f"its save to startup failed: {why}")
        if not drawn:
            step("saved", "failed", f"NOT saved to startup: {why}: a reload loses the fix")
    elif not drawn:
        step("saved", "ok", "Saved")
    golden = report.get("golden") or {}
    commit = golden.get("commit") or ""
    if commit:
        step("commit", "ok", f"Golden committed: {commit[:10]}, from the whole configuration "
                             "read after the change, after Mercury's config check passed")
        if begin is not None:
            begin("golden", f"reading {device} again, its own read, against its new golden")
        again = _read_again(src, device, dev, via)
        if again.get("state") == "clean":
            step("golden", "ok", (f"At its golden: documentation updated and tested, golden "
                                  f"{commit[:10]} committed and {device} read again matches "
                                  "it"))
        else:
            what = (f"{again.get('changed_lines')} line(s) differ" if again.get("state") ==
                    "drifted" else f"it could not be read again ({again.get('error') or ''})")
            flags.append(f"the device read again is not at its golden: {what}")
            step("golden", "failed", f"read again: {again.get('state')}: {what}")
    else:
        why = ((r.get("tail") or {}).get("golden_why") or golden.get("error")
               or golden.get("reason") or "no commit")
        gone = (r.get("tail") or {}).get("healed_gone")
        flags.append(f"its healed line is no longer on the device: {gone}, so no golden was "
                     "committed from it" if gone else f"its golden was not committed: {why}")
        step("commit", "failed", f"the golden was not committed: {why}")
    if release is not None:
        # Held through the read again; released before any symptom is waited on.
        release()
    if held_why:
        return finish("partial", (f"healed, its verify did not pass ({held_why}), and its save "
                                  "to startup is held for a person: a reload returns the "
                                  "device to before the heal"), sent=True, report=report,
                      flags=flags)
    if declared:
        return finish(declared["outcome"], declared["words"], sent=True, report=report,
                      flags=flags)
    held = (r.get("heal") or {}).get("symptom") or {}
    s = held or symptom()
    if held and more is not None and held.get("state") in ("gone", "none"):
        s = more(held)
    if s.get("state") == "present":
        return finish("symptom_remains", (f"configuration at intent, and {s['words']}: "
                                          "configuration was not the whole cause"), sent=True,
                      report=report, flags=flags)
    if s.get("state") == "unreadable":
        return finish("partial", f"configuration at intent, and {s['words']}", sent=True,
                      report=report, flags=flags)
    return finish("healed", f"healed and verified; {s.get('words') or ''}".rstrip("; "),
                  sent=True, report=report, flags=flags)


def _judge(device, r, report, src, via, step, finish, symptom, begin=None, more=None):
    """The outcome of the apply, the golden re-check, the symptom (when the check after verify
    did not already read it; *more*, given the one it read and found gone, reads what is left
    once the device is released: a heal's heartbeat, C3164), and the record. An approved
    proposal's (`propose`), whose apply has no tail."""
    done = _not_deployed(r, report, step, finish)
    if done is not None:
        return done
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
    # Its own read (item 1): never the network's drift check, whose lock refused r6's (C3864).
    again = _read_again(src, device, None, via)
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
    held = (r.get("heal") or {}).get("symptom") or {}
    symptom = held or symptom()
    if held and more is not None and held.get("state") in ("gone", "none"):
        symptom = more(held)
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
        except Exception:
            # A raise leaves no outcome, so its row read "restoring … starting" until the next
            # heal pass reaped it (2026-11-17 04:17 UTC): reaped now, its mark released first,
            # so the decision and its incident stand on "interrupted" with the error's words.
            interrupted.release(network, decision["id"])
            try:
                interrupted.reap(network, by=setter)
            except Exception as exc:                      # noqa: BLE001 (the next pass reaps)
                log.error("heal: %s's raised act %s was not reaped: %s", network,
                          decision.get("id"), exc)
            raise
        finally:
            interrupted.release(network, decision["id"])

    # Its card (the operator, 2026-11-11: "every operation and heal ends with a visible
    # outcome on its card and under 'Finished'"): the device's page reopens it, and the In
    # progress list keeps its outcome until each person opens it (`heal.run_card`).
    return capture_job.start(network, f"healing {decision['device']}", setter, work, kind=KIND,
                             announce_keys=DONE_KEYS, announcer=ANNOUNCER,
                             device=decision["device"], card="heal_run",
                             actor_kind="policy")


def run(network: str, *, now: float = None, starter=None, by: str = "heal to intent") -> dict:
    """Each heal decision of *network* not yet taken (`decisions.to_apply`), taken once here
    and started as its own job (*starter*, `start` unless given). ``{"network", "started":
    [{"decision", "job"}], "refused", "failed", "interrupted"}``.

    First, each heal whose job ended before it recorded its outcome is recorded
    (`interrupted.reap`, H6), so its incident stands on it (C3870) and Needs attention raises
    it. Each decision's mark (`interrupted.hold`) is taken BEFORE it is taken, so a taken heal
    with no outcome and no mark held is one whose job ended."""
    from modules.heal import decisions, interrupted

    now = time.time() if now is None else float(now)
    out = {"network": network, "started": [], "refused": [], "failed": [], "interrupted": []}
    reaped = interrupted.reap(network, now=now, by=by)
    out["interrupted"] = [r["decision"] for r in reaped["reaped"]]
    out["failed"] += reaped["failed"]
    # A tail whose job ended before it finished (a restart among the causes): flagged, so its
    # incident's card and Needs attention say it (round 2, item 2).
    out["tails"] = reap_tails(network, now=now, by=by)
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
        if d.get("batch"):
            # G6: a decision of a batch a person approved is its batch job's to take
            # (`heal.batch.run`, every device at once, each waited for and recorded by the
            # batch); never started here. One its job left untaken past the batch's bound (the
            # job ended) is
            # refused with nothing sent, so it never waits for ever or heals later unwatched.
            from modules.heal import batch as B
            if now - float(d.get("epoch") or now) < B.UNTAKEN_S:
                continue
            words = (f"its batch's job ended before it took it (decided {d.get('at')}, more "
                     f"than {B.UNTAKEN_S} s ago). Nothing was sent")
            try:
                decisions.take(network, d["id"], by=f"{by}: refusing an untaken batch heal",
                               now=now)
                decisions.applied(network, d["id"], "refused", by=by, words=words, now=now)
                # Refused is no fix: its incident stands on it (C3870).
                outcome_on_incident(network, d, "refused", words)
            except Exception as exc:                  # noqa: BLE001 (said; read again next)
                out["failed"].append(f"{d.get('device')}: {type(exc).__name__}: {exc}")
            out["refused"].append(f"{d.get('device')}: {words}")
            continue
        got = start_decided(network, d, now=now, starter=starter, by=by)
        for key in ("started", "refused", "failed"):
            if got.get(key):
                out[key].append(got[key])
    return out


def start_decided(network: str, d: dict, *, now: float = None, starter=None,
                  by: str = "heal to intent") -> dict:
    """One heal decision not yet taken, its mark held, taken once and started as its own job
    (`start`): ``{"started": {"decision", "job"}}``, ``{"refused": words}`` or ``{"failed":
    words}``. `run`'s step for each decision, and the decision's own the moment it is
    recorded (item 4, the operator, 2026-11-16: "the act starts at once once decided"; C3865:
    r2's act began 13 s after its decision, the pass deciding the other incidents and firing
    their scripts first), so a later `run` finds it taken. A batch's decision is never started
    here (its batch job takes it)."""
    from modules.heal import decisions, interrupted

    now = time.time() if now is None else float(now)
    if d.get("batch"):
        return {"refused": f"{d.get('device')}: a batch's heal is its batch job's to take"}
    try:
        interrupted.hold(network, d["id"], d.get("device") or "", by)
    except (interrupted.Busy, OSError) as exc:
        return {"refused": str(exc)}
    try:
        taken = decisions.take(network, d["id"], by=f"{by}: the apply", now=now)
    except decisions.Refused as exc:
        interrupted.release(network, d["id"])
        return {"refused": str(exc)}
    try:
        job = (starter or start)(network, taken)
    except Exception as exc:
        log.error("heal: %s's heal of %s could not start: %s", network, d["device"], exc)
        words = f"its job could not start ({type(exc).__name__}: {exc}). Nothing was sent"
        decisions.applied(network, d["id"], "refused", by=by, words=words, now=now)
        outcome_on_incident(network, d, "refused", words)
        interrupted.release(network, d["id"])
        return {"failed": f"{d['device']}: {type(exc).__name__}: {exc}"}
    return {"started": {"decision": d["id"], "job": job}}
