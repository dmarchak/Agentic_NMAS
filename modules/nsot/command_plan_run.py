"""The command-plan runner, "Run reviewed commands" (C3757, path 2; the operator, 2026-11-15:
"the runner is a new entry point into the deploy pipeline's existing apply/verify/rollback/
record engine, with its program taken from a validated command plan instead of committed
intent"). One execution path: G7's recovery is its first built-in plan
(`modules/nsot/command_plans/errdisable-recover.yml`); no other device-writing operation.

`run`, in order, and nothing out of it:

1. **The approval** (`approve`): a verified person, by the plan's hash; the plan previewed
   again (`command_plan.preview`: the template, the parameters validated against Mercury's
   model, Mercury's rule for raw lines, the reads the read engine allows) and refused, naming
   both hashes, when it moved.
2. **The device held** (`hold`) for the whole run: one operation per device across processes.
   Every config line Mercury's session sends while it holds the device is Mercury's own
   (`heal.attribution` rule 1), and the run's receipt and record mark it after (rules 2, 4).
3. **The deploy pipeline's engine** (`pipeline.PipelineRunner`), its context built here from
   the plan (`context`): the confirmed program is the plan's (stage 2 renders nothing), its
   gate authorises a dangerous line only by the template's reason, stage 4 reads the running
   configuration before anything is sent, then **the pre-apply checks** (the pipeline's
   ``pre_apply``; `preconditions`: each precondition read again through the read engine,
   holding the device, all must hold or nothing is sent, and the configuration before must
   have been read), the send, the post-change read, and **verify**: the pipeline's own (the
   program's expected effects, by name, so a port the plan brings up is its intended effect
   and never an unexpected change), with the plan's verify reads (`plan_verify`) and **the
   net-zero check** (`net_zero`: the running configuration read again after the verify,
   holding the device, equals the one stage 4 read before the first step, line for line, after
   `normalize.strip_for_repo`'s volatile lines; any difference rolls back and the plan is
   refused, the record naming each line; for a plan of `SECTION_CONFINED` shapes alone, each
   of its interfaces' configuration read just before the send and again after,
   `net_zero_scope`, and again after a rollback). A transient plan is never saved to startup
   and records no golden (`PipelineContext.transient`). Rollback is the pipeline's.

   **One device session per run** (the operator, 2026-11-16): every read the plan makes (its
   preconditions, its verify reads, the net-zero reads) rides the pipeline's own pooled
   session, the one stage 4 signs in on and the push sends on (`Sources.ride`,
   `pool_session`), each read live. Stage 7 still signs in again after the push (C272)
   until a measurement shows the push's session reads alike. The pipeline's snapshots before
   and after are scoped by what the plan touches (`snapshot_scope`). Each step's and each
   read's time is kept in the record's ``laps``.
4. **The record**: the receipt (`receipts`, action ``command_plan``, no intent commit), the
   run's record in the operations' record History reads (`privileged.record`, its key the
   plan's), each new shape's measurement (`command_policy.record_measurement`), and the
   plan's ``on_finish`` hook (G7's notification of the MAC, the port, the time and the cause).

One device per plan; a plan engine step is one plan, and the engine stops on the first that
does not pass.
"""

import logging
import re
import threading
import time

log = logging.getLogger(__name__)

#: The run record's key is its plan's (an incident's attempt is derived by it); its kind is
#: this, and the hold's operation is its words.
KIND = "command_plan"
OPERATION = "reviewed commands"
RECORD = "privileged"
ANNOUNCER = "privileged"
ANNOUNCE_KEYS = ("privileged",)
#: The runner's steps, in order, for the manual's How it works pages and THE stepper.
STEPS = (("approve", "Preview the plan again and compare its hash with the one approved"),
         ("hold", "Hold the device for the whole run"),
         ("read_before", "Read the running configuration before anything is sent"),
         ("preconditions", "Read each precondition again through the read engine; all must "
                           "hold, or nothing is sent"),
         ("send", "Send the plan's lines in config mode, merge-only, never saved"),
         ("verify", "Verify the expected effects and the plan's reads, then the running "
                    "configuration equals the one before, line for line"),
         ("rollback", "When it did not verify: the pipeline's rollback, saying what it "
                      "achieved"),
         ("record", "Record the receipt and the run, and measure each new shape"))
STEP_LABELS = {"approve": "Check hash", "hold": "Hold {device}", "read_before": "Read before",
               "preconditions": "Check preconditions", "send": "Send", "verify": "Verify",
               "rollback": "Roll back", "record": "Record"}
#: A verify check's result, and the run's outcome, when the port the plan recovered tripped
#: again by its own cause (the operator, 2026-11-16): a finding, never a verify failure; no
#: retry and no rollback (the port is already safely down), nothing more sent.
RETRIPPED = "retripped"
OUTCOMES = ("done", "refused", "not_net_zero", "rolled_back", "unverified", "failed",
            RETRIPPED)
OUTCOME_WORDS = {"done": "ran, verified, and the configuration is as it was before",
                 RETRIPPED: "tripped again after the bounce: the port was left err-disabled, "
                            "nothing more was sent and nothing was rolled back",
                 "refused": "nothing was sent",
                 "not_net_zero": "refused: the configuration after differed from before, and "
                                 "it was rolled back",
                 "rolled_back": "did not verify, and was rolled back",
                 "unverified": "ran; verify could not read everything it needs, so it did not "
                               "pass: read the device before anything else",
                 "failed": "failed during the run: read the device before anything else"}
#: A precondition's result that lets the run go on: it holds, or it cannot be told before the
#: send and is judged after it by the plan's own verify (``deferred``: never a pass; G7's
#: BPDU guard, since no BPDU is processed while the port is err-disabled).
DEFERRED = "deferred"
HOLDS = ("pass", DEFERRED)
RECORD_STATE = {"done": "done", "refused": "refused", "not_net_zero": "failed",
                "rolled_back": "failed", "unverified": "unverified", "failed": "failed",
                RETRIPPED: "failed"}


#: How old a device read taken earlier in the same proposing job may be and still answer a
#: proposal's preflight (`Reused`). Reasoned, not measured: s5's port-security run
#: (2026-11-16) took 87 s from the press to a ready plan, 25 s of it this preflight, so the
#: investigation's reads were at most about 62 s old when the preflight asked; 2.5x that is
#: about 150 s. An err-disabled port changes only by IOS's own recovery (300 s by default,
#: and a plan whose switch recovers the cause itself is refused) or a person, and the approved
#: run reads every precondition again live, holding the device, so a stale answer can only
#: misdraw the card, never send. The measurement owed: each preflight's ``reuse`` record (the
#: ages it reused, `fix_proposal._command_plan_reads`) over the next runs.
REUSE_S = 150.0
#: Where a reused read came from, as its words say it ("read 6 s ago, during the
#: investigation").
FROM_INVESTIGATION = "during the investigation"
FROM_PREFLIGHT = "by the first plan's check"


class Reused:
    """The device reads one proposing job already took (the investigation's, through the read
    engine, and each preflight's own), answering a later preflight's same command on the same
    device while at most `REUSE_S` old (the operator, 2026-11-16: "time to a ready plan toward
    45 s"). For the proposal's preflight only, which draws the plan card: the approved run's
    `Sources` never carries one (`run`), so its preconditions and verify read live. Only a
    read that signed in as Mercury's account is kept, the account a preflight's own read signs
    in as (`reads.signs_in_as`), so a reused answer is the one a live read would give, masked
    and capped by the same engine. ``stats``: what it answered and what was read live."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self._kept = {}
        self.stats = {"reused": 0, "live": 0, "live_s": 0.0}

    @staticmethod
    def key(host: str, command: str) -> tuple:
        """*command* on *host* as one read: its words, spacing collapsed, each interface name
        in its canonical long form (`ifnames.canonical`: IOS answers ``Gi1/0/5`` and
        ``GigabitEthernet1/0/5`` alike)."""
        from modules.nsot import ifnames

        words = [ifnames.canonical(w) if any(ch.isdigit() for ch in w) else w
                 for w in str(command or "").split()]
        return (str(host or ""), " ".join(words).lower())

    def keep(self, host: str, command: str, answer: str, at: float, *, run: str = "",
             source: str = FROM_PREFLIGHT) -> None:
        """One answered read, kept unless a younger one of the same read is."""
        k = self.key(host, command)
        old = self._kept.get(k)
        if old is None or float(old["at"]) <= float(at):
            self._kept[k] = {"answer": answer or "", "at": float(at), "run": str(run or ""),
                             "from": source}

    def take(self, host: str, command: str):
        """The kept answer of *command* on *host* with its ``age_s``, or None when none is
        kept or it is older than `REUSE_S` (or from the future: a clock that moved)."""
        got = self._kept.get(self.key(host, command))
        if got is None:
            return None
        age = float(self.clock()) - got["at"]
        if not 0 <= age <= REUSE_S:
            return None
        return dict(got, command=command, age_s=round(age, 1))

    def add_runs(self, network: str, run_ids, source: str = FROM_INVESTIGATION) -> int:
        """Each read-engine run of *run_ids* (History › Reads' records) kept: every answered
        command of each device, at its own answer's time, when it signed in as Mercury's
        account. How many answers were kept; a run that cannot be read keeps none, logged."""
        from modules.nsot import reads

        n = 0
        for rid in dict.fromkeys(r for r in run_ids or () if r):
            try:
                rec = reads.get(network, rid) or {}
            except (OSError, ValueError) as exc:
                log.info("command plan: read run %s is not reused: %s", rid, exc)
                continue
            if rec.get("signs_in_as") == "read_only":
                continue
            for host, res in (rec.get("results") or {}).items():
                for a in (res or {}).get("answers") or []:
                    if a.get("state") == reads.ANSWERED and a.get("at"):
                        self.keep(host, a.get("command") or "", a.get("answer") or "",
                                  float(a["at"]), run=rid, source=source)
                        n += 1
        return n


def reused_words(r: dict) -> str:
    """A reused read's age and where it came from: "read 6 s ago, during the investigation"."""
    return f"read {int(round(float(r.get('age_s') or 0)))} s ago, {r.get('from') or ''}".rstrip(", ")


class Sources:
    """Where a run reads: Mercury's model (`command_plan.Sources`), the read engine, the
    clock and the sleep, and a problem's own sources by family (``of``: G7's Loki lines).
    *reuse* (a `Reused`) is a proposal's preflight's alone: a read it holds young enough
    answers in place of the device, said in ``reused_log``; never the approved run's.
    *session* (`ride`): the run's one device session, which every read rides once the
    pipeline has opened it; None, each read opens its own (a preflight's)."""

    def __init__(self, network: str, *, clock=time.time, sleep=time.sleep, model=None,
                 families=None, reuse=None):
        from modules.nsot import command_plan

        self.network, self.clock, self.sleep = network, clock, sleep
        self.model = model or command_plan.Sources(network)
        self._families = dict(families or {})
        self.reuse = reuse
        self.reused_log = []
        self.session = None

    def ride(self, ctx=None, dev: dict = None) -> None:
        """From now every read rides the pipeline's pooled session for *dev* (*ctx*'s pool,
        `pool_session`); with neither, each read opens its own again (the run's end, before
        its pool is closed, so no read reopens a session nobody closes)."""
        self.session = pool_session(ctx, dev) if ctx is not None and dev else None

    def device(self, host):
        return self.model.device(host)

    def intent(self, host):
        return self.model.intent(host)

    def golden(self, host):
        return self.model.golden(host)

    def of(self, family: str):
        if family not in self._families:
            if family == "errdisable":
                from modules.heal import errdisable
                self._families[family] = errdisable.Sources(self.network)
        return self._families.get(family)

    def read(self, host: str, commands: list) -> dict:
        """``{command: answer}`` (an answer None when it was not read), through THE read
        engine, inline: the run already holds the device, so the read's hold is re-entrant,
        and on the run's one session once it rides one (`ride`): no login per read. With
        *reuse* (a proposal's preflight), a command it holds young enough is answered from it
        and logged in ``reused_log``; the rest are read, and kept for a later preflight in the
        same job (an alternative's)."""
        from modules.nsot import reads

        reuse = self.reuse
        held = {}
        if reuse is not None:
            for c in commands:
                r = reuse.take(host, c)
                if r is not None:
                    held[c] = r
                    self.reused_log.append(r)
            reuse.stats["reused"] += len(held)
        live = [c for c in commands if c not in held]
        out = {c: r["answer"] for c, r in held.items()}
        if not live:
            return {c: out.get(c) for c in commands}
        t0 = time.monotonic()
        try:
            rec = reads.run(self.network, [host], live, "Mercury (reviewed commands)",
                            purpose="a command plan's precondition or verify read",
                            inline=True, **({"session": self.session}
                                            if self.session is not None else {}))
        except reads.Refused as exc:
            log.warning("command plan: a read was refused: %s", exc)
            return {c: out.get(c) for c in commands}
        finally:
            if reuse is not None:
                reuse.stats["live"] += len(live)
                reuse.stats["live_s"] = round(reuse.stats["live_s"] + time.monotonic() - t0, 2)
        r = (rec.get("results") or {}).get(host) or {}
        got = {}
        for a in r.get("answers") or []:
            if a.get("state") == reads.ANSWERED:
                got[a["command"]] = a.get("answer") or ""
                if reuse is not None and a.get("at"):
                    reuse.keep(host, a["command"], got[a["command"]], float(a["at"]),
                               run=rec.get("id") or "")
        out.update({c: got.get(c) for c in live})
        return {c: out.get(c) for c in commands}


def pool_session(ctx, dev: dict):
    """The read engine's *session* (`reads.run`'s ``session(dev, fn) -> fn(conn)``) riding
    the pipeline's pooled session for *dev* (``ctx.connections_pool``, the one stage 4 opened,
    the push sends on and verify reads on): asked of the pool at each engine run, so a session
    a failed read spent is replaced first (C272). A read the engine would make of another
    address, or signed in as another account, raises (that read fails, said in its record):
    never sent on this session."""
    from modules.connection import get_persistent_connection

    ip, user = dev.get("ip", ""), dev.get("username", "")

    def session(signed, fn):
        s_ip, s_user = (signed or {}).get("ip", ""), (signed or {}).get("username", "")
        if s_ip != ip or (s_user and user and s_user != user):
            raise ValueError(f"this read is of {s_ip or 'no address'} as "
                             f"{s_user or 'no account'}, and the run's session is {ip} as "
                             f"{user or 'no account'}: it is not read on that session")
        return fn(get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock))
    return session


class CheckRun:
    """What a named check is handed: the run's network, device and inventory row, the
    validated values (`derived`), the incident it acts in, the sources and the time; *found*
    is what a check learned from the device for the run's record (G7's violating MAC)."""

    def __init__(self, network, device, dev, derived, incident, sources):
        self.network, self.device, self.dev = network, device, dev
        self.derived, self.incident, self.sources = derived, incident, sources
        self.found = {}
        #: ``{interface: its configuration}`` read just before the send, when the net-zero
        #: check is scoped to the plan's interfaces (`net_zero_scope`); None, the whole.
        self.sections_before = None

    @property
    def at(self) -> float:
        return float(self.sources.clock())


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def person_refusal(actor: str, actor_verified: str, person: bool) -> str:
    """Why the approval is not a verified person's, or ``""``: the plan engine's one check
    (`plan_engine.person_refusal`), a plan being what a person approves."""
    from modules.plan_engine import person_refusal as engine_refusal

    why = engine_refusal(actor, actor_verified, person)
    return f"{why}. Nothing was sent" if why else ""


# ── The checks the pipeline runs for the plan ───────────────────────────────────────────────

def _judge(items, run: CheckRun, answers: dict) -> list:
    """Each item judged: ``[{"name", "read", "result", "words"}]``."""
    from modules.nsot import command_plan as CP

    out = []
    for i in items:
        cmd = CP.substitute(i["read"], run.derived) if i["read"] else ""
        result, words = CP.matched(i, answers.get(cmd) if cmd else None, run)
        out.append({"name": i["name"], "read": cmd, "result": result, "words": words})
    return out


def preconditions(t, run: CheckRun, rec: dict):
    """The pre-apply check: each precondition read again, live (one read engine run over the
    run's session, holding the device), and judged; all must pass, and stage 4 must have read
    the configuration before. Then, when the net-zero check can be scoped to the plan's
    interfaces (`net_zero_scope`), each interface's configuration read before the send.
    Returns the pipeline's hook, ``hook(ctx) -> why or ""``."""
    from modules.nsot import command_plan as CP
    from modules.pipeline import lap

    def hook(ctx):
        ip = run.dev.get("ip", "")
        pre = (ctx.pre_snapshots or {}).get(ip) or {}
        if not pre.get("running_config"):
            why = ("the running configuration before the plan could not be read, so whether "
                   "the plan is net zero cannot be checked. Nothing was sent")
            _step(rec, "read_before", "refused", why)
            return why
        why = _live_mode_refusal(rec.get("snapshot_scope") or {}, pre["running_config"])
        if why:
            _step(rec, "read_before", "refused", why)
            return why
        _step(rec, "read_before", "ok", "the running configuration read before anything is "
                                        "sent, holding the device")
        cmds = list(dict.fromkeys(CP.substitute(i["read"], run.derived)
                                  for i in t.preconditions if i["read"]))
        answers = run.sources.read(run.device, cmds) if cmds else {}
        lap(rec.get("laps"), "preconditions: read")
        judged = _judge(t.preconditions, run, answers)
        lap(rec.get("laps"), "preconditions: judged")
        rec["preconditions"] = judged
        if run.found:
            rec["found"] = dict(run.found)
        bad = [j for j in judged if j["result"] not in HOLDS]
        if bad:
            why = "; ".join(f"{j['name']}: {j['words']}" for j in bad) + ". Nothing was sent"
            _step(rec, "preconditions", "refused", why)
            return why
        held = [j["name"] for j in judged if j["result"] == "pass"]
        later = [f"{j['name']}: {j['words']}" for j in judged if j["result"] == DEFERRED]
        _step(rec, "preconditions", "ok",
              ("; ".join(x for x in (
                  ("these hold: " + "; ".join(held)) if held else "",
                  ("not told before the send, judged by verify: " + "; ".join(later))
                  if later else "") if x)) if judged else "no precondition")
        # The net-zero check's before, scoped to the plan's interfaces when it can be (each
        # one's own configuration, read now on the run's session, the last read before the
        # send); else, or when one cannot be read, verify compares the whole configuration
        # with stage 4's.
        names = net_zero_scope(t, (ctx.rendered_commands or {}).get(ip) or [])
        run.sections_before = (_sections(ctx, run.dev, names) if names else None)
        rec["net_zero_scope"] = ({"scope": "interfaces", "interfaces": names}
                                 if run.sections_before else
                                 {"scope": "full", "why": (
                                     "an interface's configuration before could not be read"
                                     if names else "a line of the plan is not confined to an "
                                                   "interface's section")})
        lap(rec.get("laps"), "net zero: before")
        # From here the send may land: the record says so, so an end that raises says
        # whether anything was sent, and the run spans its lines (`heal.attribution` rule 4).
        rec["config_change"] = True
        return ""
    return hook


#: The shapes (`command_policy.shapes`, as a template writes a line) whose every effect on
#: the configuration stays in the interface section they are sent in: entering an
#: interface's section, and its administrative state. A plan of these alone is net-zero-checked
#: per interface (`net_zero_scope`); a shape added later (an admin's approved one, which may
#: write elsewhere, as `switchport access vlan` creates a VLAN) is not on this list, so its
#: plan keeps the whole-configuration compare until it is measured onto it.
SECTION_CONFINED = frozenset(("interface {interface}", "interface {interface} > shutdown",
                              "interface {interface} > no shutdown"))
#: An interface name as one token: letters, then its number (``GigabitEthernet1/0/5``).
_IFNAME = re.compile(r"[A-Za-z][A-Za-z\-]*\d[\d/.:]*")


def net_zero_scope(t, program) -> list:
    """The interfaces the net-zero check is scoped to, ``[name]`` in order, or ``[]`` (the
    whole running configuration is compared): every line of the template a `SECTION_CONFINED`
    shape, and every top-level line of the confirmed *program* (one per template line,
    `command_plan.program`) ``interface <name>``, its name one token of an interface's
    shape."""
    from modules.nsot import command_policy

    lines = list(program or [])
    shapes = command_policy.shapes(t.commands)
    if not shapes or len(shapes) != len([ln for ln in lines if str(ln or "").strip()]):
        return []
    names = []
    for (_raw, shape), line in zip(shapes, [ln for ln in lines if str(ln or "").strip()]):
        if shape not in SECTION_CONFINED:
            return []
        if str(line)[:1] in (" ", "\t"):
            if not names:
                return []
            continue
        words = str(line).split()
        if len(words) != 2 or words[0] != "interface" or not _IFNAME.fullmatch(words[1]):
            return []
        names.append(words[1])
    return list(dict.fromkeys(names))


#: The rules that scope the pipeline's snapshots before and after (the operator, 2026-11-16,
#: decision 2 per R3), by what the plan touches: ``access`` (every interface an access port in
#: committed intent: its state, its spanning-tree state and its own section only), ``routed``
#: (a trunk or routed interface: the full snapshots, every protocol's adjacencies and the route
#: table, since the protocols each interface runs are not yet read from intent, so all are),
#: and ``full`` (anything unclassified).
SNAPSHOT_RULES = ("access", "routed", "full")
#: What the access rule does not see, in its words: the basis the reviewer asked be said
#: (finding 6).
ACCESS_UNSEEN = ("not read: the device's other interfaces, its routing adjacencies, its route "
                 "table and its running configuration after; an on-device script reacting to "
                 "the link event (EEM, say) could write outside the port's section unseen here, "
                 "and drift detection still catches such a change as its own incident")


def snapshot_scope(network: str, t, p: dict, run: CheckRun) -> dict:
    """The scope of the pipeline's snapshots for the plan *p* (`SNAPSHOT_RULES`), from what it
    touches: its interfaces (`net_zero_scope`: every line a `SECTION_CONFINED` shape) and each
    one's switchport mode in committed intent (`errdisable.intent_port`'s, the one reading of
    a port's role, as the plan's own ``access_port`` check reads it). ``{"rule", "words",
    "interfaces"}``, kept as the run's ``snapshot_scope``; the run also refuses, nothing sent,
    when the device's own configuration before does not hold the mode intent says
    (`_live_mode_refusal`)."""
    from modules.heal.errdisable import intent_port

    names = net_zero_scope(t, p.get("program") or [])
    if not names:
        return {"rule": "full", "interfaces": [], "words": (
            "a line of the plan is not confined to an interface's section: the full snapshots "
            "before and after")}
    read_intent = getattr(run.sources, "intent", None)
    try:
        intent, err = read_intent(run.device) if read_intent else (None, "no intent source")
    except Exception as exc:                          # noqa: BLE001 (unclassified: the full)
        intent, err = None, f"{type(exc).__name__}: {exc}"
    if intent is None or err:
        return {"rule": "full", "interfaces": names, "words": (
            f"committed intent could not be read ({err or 'none'}), so the plan's interfaces "
            "are not classified: the full snapshots before and after")}
    roles = {n: intent_port(intent, n) for n in names}
    unknown = [n for n, r in roles.items() if not r["found"] or not r["mode"]]
    if unknown:
        return {"rule": "full", "interfaces": names, "words": (
            f"committed intent names no switchport mode for {', '.join(unknown)}, so it is not "
            "classified: the full snapshots before and after")}
    other = [f"{n} ({r['mode']})" for n, r in roles.items() if r["port_role"] != "access"]
    if other:
        return {"rule": "routed", "interfaces": names, "words": (
            f"{', '.join(other)} is not an access port in committed intent: the full snapshots "
            "before and after, every routing protocol's adjacencies and the route table")}
    from modules.heal.errdisable import same_port

    members = [n for n in names for i in (intent.get("interfaces") or [])
               if isinstance(i, dict) and same_port(i.get("name") or "", n)
               and str(i.get("channel_group") or "").strip()]
    if members:
        # A port-channel member (the review, finding 3): its bundle's state and the bundle's
        # own protocols move with it, which its own section and state do not show.
        return {"rule": "full", "interfaces": names, "words": (
            f"{', '.join(members)} is a port-channel member in committed intent "
            "(channel-group): the full snapshots before and after")}
    return {"rule": "access", "interfaces": names, "words": (
        f"{', '.join(names)}: an access port in committed intent (switchport mode access), so "
        "the snapshots before and after read its state and its spanning-tree state, and its "
        "own section is net-zero checked; " + ACCESS_UNSEEN)}


def _live_mode_refusal(scope: dict, running_config: str) -> str:
    """Why the access rule does not hold on the device itself, or ``""``: each of its
    interfaces' sections in the configuration stage 4 read live before the send must hold
    ``switchport mode access``, the mode committed intent gave it (`snapshot_scope`), and no
    ``channel-group`` (a port-channel member, which the access rule never covers: the
    review's finding 3). A device departed from its intent is never verified on intent's
    word: the snapshot before was already read under the access rule, so the run refuses,
    nothing sent, rather than verify a member or a non-access port by it."""
    if (scope or {}).get("rule") != "access":
        return ""
    from modules.nsot import ifnames

    lines = (running_config or "").splitlines()
    missing, members = [], []
    for name in scope.get("interfaces") or []:
        section, inside = [], False
        for ln in lines:
            if ln[:1] not in (" ", "\t"):
                words = ln.split()
                inside = (len(words) == 2 and words[0] == "interface"
                          and ifnames.same_interface(words[1], name))
                continue
            if inside:
                section.append(" ".join(ln.split()))
        if "switchport mode access" not in section:
            missing.append(name)
        if any(s.startswith("channel-group ") for s in section):
            members.append(name)
    why = []
    if missing:
        why.append(f"committed intent says {', '.join(missing)} is an access port, and the "
                   "device's running configuration before the send does not hold `switchport "
                   "mode access` there")
    if members:
        why.append(f"the device's running configuration before the send makes "
                   f"{', '.join(members)} a port-channel member (channel-group), which "
                   "committed intent does not")
    if not why:
        return ""
    return "; ".join(why) + ", so the plan is not verified on intent's word. Nothing was sent"


def _section_read(name: str) -> str:
    return f"show running-config interface {name}"


def _sections(ctx, dev: dict, names: list):
    """``{name: its configuration}`` for each interface of *names*, read on the run's session
    (the pipeline's pool, holding the device), or None when any one cannot be read or the
    device refuses the read (an IOS ``%`` error line): the caller then compares the whole
    configuration."""
    from modules.commands import run_device_command
    from modules.connection import get_persistent_connection
    from modules.pipeline import IOS_ERROR_PATTERN

    out = {}
    for name in names:
        try:
            text = run_device_command(get_persistent_connection(
                dev, ctx.connections_pool, ctx.pool_lock), _section_read(name)) or ""
        except Exception as exc:                      # noqa: BLE001 (the whole compare, said)
            log.info("command plan: %s's configuration was not read: %s", name, exc)
            return None
        if not text.strip() or re.search(IOS_ERROR_PATTERN, text):
            return None
        out[name] = text
    return out


def _verify_item(item, run: CheckRun, before: str = "") -> dict:
    """One verify read: polled until it holds within its bound, or read once after its wait
    (`waits.PLAN_BOUNDS`). A bound derived per port (``derive``) is derived from *before*, the
    running configuration the run read before it sent anything, and the switch's PoE answer
    for the port, read once first (`command_plan.derived_bound`). ``{"name", "read", "result",
    "words", "took_s"}``, and for a derived bound ``"bound_s"`` and ``"bound_why"``."""
    from modules.nsot import command_plan as CP
    from modules.waits import PLAN_BOUNDS

    src = run.sources
    cmd = CP.substitute(item["read"], run.derived) if item["read"] else ""
    spec = PLAN_BOUNDS.get(item.get("within")) or {}
    derived = {}
    if spec.get("derive"):
        iface = run.derived.get(spec["of"]) or ""
        poe_cmd = f"show power inline {iface}"
        poe = (src.read(run.device, [poe_cmd]) or {}).get(poe_cmd)
        derived = CP.derived_bound(item["within"], before or "", iface, poe)
    t0 = src.clock()
    if item.get("after"):
        src.sleep(PLAN_BOUNDS[item["after"]]["seconds"])
    bound = (derived["seconds"] if derived else
             PLAN_BOUNDS[item["within"]]["seconds"] if item.get("within") else 0)
    poll = PLAN_BOUNDS[item["poll"]]["seconds"] if item.get("poll") else 0
    while True:
        answer = (src.read(run.device, [cmd]) or {}).get(cmd) if cmd else None
        result, words = CP.matched(item, answer, run)
        if result == "pass" or not bound or src.clock() - t0 >= bound:
            break
        src.sleep(poll)
    took = round(src.clock() - t0, 1)
    out = {"name": item["name"], "read": cmd, "result": result, "took_s": took,
           "words": words + (f" after {took} s" if bound else "")}
    if derived:
        # The run record says which rule bounded it (the operator: "portfast edge: 12 s").
        out.update(bound_s=bound, bound_why=derived["words"])
        out["words"] += f" (bound {derived['words']})"
    return out


def net_zero(before: str, after: str) -> list:
    """Each line that differs between the running configuration *before* and *after*, after
    `normalize.strip_for_repo` (the volatile lines: ``! Last configuration change``, ``! NVRAM
    config``, ``! No configuration``, ``Building configuration``, ``Current configuration``,
    ``ntp clock-period`` and Mercury's own header), each ``+ line`` (after only) or ``- line``
    (before only), masked, in order; ``[]`` when they are equal line for line."""
    import difflib

    from modules.nsot.normalize import strip_for_repo
    from modules.redact import redact_text

    a = [ln.rstrip() for ln in strip_for_repo(before or "")]
    b = [ln.rstrip() for ln in strip_for_repo(after or "")]
    out = []
    for d in difflib.ndiff(a, b):
        if d[:2] in ("+ ", "- "):
            out.append(redact_text(d[:2] + d[2:]))
    return out


def _net_zero_after(ctx, run: CheckRun, pre: dict, scope: str = "") -> dict:
    """The net-zero check, on the run's session holding the device: scoped
    (``run.sections_before``), each interface's configuration read again and compared with its
    own read before the send; else, or when one cannot be read again, the whole running
    configuration compared with stage 4's. *scope* (``interfaces`` or ``full``) holds it to
    that one compare, with no fallback: the check after a rollback uses the scope the run's
    own check used (`_net_zero_after_rollback`). ``{"checked", "differs", "scope",
    "interfaces"?, "error"?}``."""
    from modules.commands import run_device_command
    from modules.connection import get_persistent_connection

    dev = run.dev
    before = run.sections_before
    if before and scope != "full":
        after = _sections(ctx, dev, list(before))
        if after is not None:
            differs = []
            for name in before:
                differs += net_zero(before[name], after[name])
            return {"checked": True, "differs": differs, "scope": "interfaces",
                    "interfaces": list(before)}
        if scope == "interfaces":
            return {"checked": False, "differs": [], "scope": "interfaces",
                    "interfaces": list(before),
                    "error": "the configuration of " + ", ".join(before) + " could not be "
                             "read again: whether it is net zero cannot be told"}
    try:
        text = run_device_command(get_persistent_connection(
            dev, ctx.connections_pool, ctx.pool_lock), "show running-config") or ""
    except Exception as exc:                          # noqa: BLE001 (neither pass nor fail)
        return {"checked": False, "differs": [], "scope": "full",
                "error": f"the running configuration after the plan could not be read "
                         f"({type(exc).__name__}): whether it is net zero cannot be told"}
    if not text:
        return {"checked": False, "differs": [], "scope": "full",
                "error": "the running configuration after the plan read empty: whether it is "
                         "net zero cannot be told"}
    return {"checked": True, "scope": "full",
            "differs": net_zero((pre or {}).get("running_config") or "", text)}


def plan_verify(t, run: CheckRun, rec: dict):
    """The pipeline's verify hook for the plan: its verify reads, then the net-zero check
    (`_net_zero_after`). ``hook(ctx, ip, pre, post) -> {"issues", "unreadable", "checks",
    "net_zero"}``; an issue fails verify and rolls back."""
    def hook(ctx, ip, pre, post):
        from modules.pipeline import lap

        checks = []
        for i in t.verify:
            checks.append(_verify_item(i, run, (pre or {}).get("running_config") or ""))
            lap(rec.get("laps"), f"verify: {i['name']}")
        # A re-trip (the operator, 2026-11-16) is the run's outcome, never an issue: the port
        # is down again by its own cause, which explains the reads that fail on it, so they
        # roll nothing back; the net-zero check below still does.
        retrip = next((c for c in checks if c["result"] == RETRIPPED), None)
        stop = ({"outcome": RETRIPPED, "words": retrip["words"],
                 "interfaces": [run.derived.get("interface") or ""]} if retrip else {})
        issues = [f"{c['name']}: {c['words']}" for c in checks
                  if c["result"] == "fail" and not retrip]
        unread = [f"{c['name']}: {c['words']}" for c in checks if c["result"] == "unreadable"]
        nz = _net_zero_after(ctx, run, pre)
        lap(rec.get("laps"), f"net zero: after ({nz['scope']})")
        if nz.get("error"):
            unread.append(nz["error"])
        differs = nz["differs"]
        if differs:
            what = ("the configuration of " + ", ".join(nz["interfaces"])
                    if nz["scope"] == "interfaces" else "the running configuration")
            issues.append(f"{what} after the plan differs from the one "
                          f"before it ({len(differs)} line(s): " + "; ".join(differs[:8])
                          + (" …" if len(differs) > 8 else "") + "): a command plan is net "
                          "zero, so it is rolled back and refused")
        nz = {k: v for k, v in nz.items() if k != "error"}
        rec["verify_checks"] = checks
        rec["net_zero"] = nz
        if run.found:
            rec["found"] = dict(run.found)
        return {"issues": issues, "unreadable": unread, "checks": checks,
                "net_zero": dict(nz), "stop": stop}
    return hook


def context(network: str, t, p: dict, run: CheckRun, rec: dict):
    """The pipeline's context for the plan *p* (a preview): its gate's authorisations, the
    planned window of the links it touches, transient, the plan's pre-apply and verify hooks,
    the run's timing record, the run's reads riding the pipeline's own session
    (`Sources.ride`), and the scope of the pipeline's snapshots before and after
    (`snapshot_scope`, recorded as ``rec["snapshot_scope"]``). Its program is confirmed by
    `run`, beside the runner it is confirmed for (C765: every product run confirms its list
    first, tests/test_pipeline.py)."""
    from modules.neighbours import committed_intents_of
    from modules.nsot import authorisation as _auth
    from modules.pipeline import PipelineContext, link_window

    dev = run.dev
    ip = dev.get("ip", "")
    ctx = PipelineContext(config_type=KIND, device_ips=[ip], params={}, ip_params_map={},
                          selected_devices=[dev], connections_pool={}, pool_lock=threading.Lock(),
                          config_id=f"plan-{run.device}-{rec['id']}", list_name=network)
    ctx.params["allowed_dangerous"] = _auth.valid_keys(p["authorised"])
    ctx.transient = True
    ctx.declared_protocols = {ip: None}
    ctx.link_window = {ip: link_window(network, run.device, p["program"],
                                       committed_intents_of(network))}
    ctx.pre_apply = [preconditions(t, run, rec)]
    ctx.plan_verify = {ip: plan_verify(t, run, rec)}
    ctx.laps = rec.get("laps")
    # One device session per run (the operator, 2026-11-16): every read the plan makes rides
    # the pool stage 4 opens, the push sends on and verify reads on.
    if hasattr(run.sources, "ride"):
        run.sources.ride(ctx, dev)
    scope = snapshot_scope(network, t, p, run)
    ctx.snapshot_scope = {ip: scope}
    rec["snapshot_scope"] = scope
    return ctx


def _laps(marks) -> list:
    """The run's timing record from its marks ``[(lap, epoch)]`` (`pipeline.lap`), the first
    the run's start: ``[{"lap", "at_s", "took_s"}]``, *at_s* from the start, *took_s* since
    the lap before (what that lap's work took)."""
    out = []
    if not marks:
        return out
    t0 = prev = float(marks[0][1])
    for name, at in marks[1:]:
        out.append({"lap": str(name), "at_s": round(float(at) - t0, 1),
                    "took_s": round(float(at) - prev, 1)})
        prev = float(at)
    return out


def preconditions_now(network: str, key: str, p: dict, *, sources=None,
                      incident: str = "", reuse=None) -> list:
    """The plan *p*'s preconditions read now through the read engine and judged, holding
    nothing beyond the reads' own holds (a proposal's preflight, `catalog.PlanStep`); the run
    reads them again holding the device. *incident* is the one it is proposed in, so a check
    reads its classification as the run's does. *reuse* (a `Reused`, the proposing job's
    reads) answers a read it holds young enough in place of the device; each item answered
    so says it in its words and ``reused`` (``[{"command", "age_s", "from", "run"}]``), so a
    reused read never reads as a fresh one. ``[{"name", "read", "result", "words"}]``."""
    from modules.nsot import command_plan as CP

    t = CP.template_of(key)
    src = sources or Sources(network, reuse=reuse)
    run_ = CheckRun(network, p["values"].get("device") or "", p["device_row"], p["derived"],
                    str(incident or ""), src)
    cmds = list(dict.fromkeys(CP.substitute(i["read"], p["derived"])
                              for i in t.preconditions if i["read"]))
    answers = src.read(run_.device, cmds) if cmds else {}
    log_ = getattr(src, "reused_log", None)
    if log_ is None:
        return _judge(t.preconditions, run_, answers)
    batch = list(log_)
    out = []
    for i in t.preconditions:
        # Each item judged alone, so a read its own check makes (G7's port-security read in
        # `cause_cleared`) is told apart from the others'.
        before = len(log_)
        j = _judge([i], run_, answers)[0]
        mine = [r for r in batch if j["read"] and r["command"] == j["read"]] + log_[before:]
        if mine:
            j["reused"] = [{"command": r["command"], "age_s": r["age_s"], "from": r["from"],
                            "run": r.get("run") or ""} for r in mine]
            j["words"] = (f"{j['words']} ("
                          + "; ".join(f"`{r['command']}` {reused_words(r)}" for r in mine) + ")")
        out.append(j)
    return out


def step_apply(key: str):
    """The plan *key* as a step's apply, the one contract a declaration carries
    (`catalog.PlanStep.apply`): ``apply(network, params, confirmed_hash, *, actor, reason,
    actor_verified="", person=False) -> {"ok", "outcome", "words", "receipt"}``. *params* hold
    the incident and its proposal beside the plan's values; the run names the incident's
    attempt (`fixit.plan.run_link_of`)."""
    def apply(network: str, params: dict, confirmed_hash: str, *, actor: str, reason: str,
              actor_verified: str = "", person: bool = False) -> dict:
        from modules.fixit import plan as FP

        values = {k: v for k, v in params.items() if k not in ("incident", "proposal")}
        rec = run(network, key, values, actor=actor, actor_verified=actor_verified,
                  person=person, confirmed=confirmed_hash, reason=reason,
                  incident=str(params.get("incident") or ""),
                  fixit=FP.run_link_of(network, params))
        ok = rec.get("state") == "done"
        # The plan's own words for its end when its finish gave them ("Fixed: pc-12 is back
        # online.", a re-trip's finding), else the runner's.
        return {"ok": ok, "outcome": rec.get("outcome") or "",
                "words": rec.get("said") or (OUTCOME_WORDS.get(rec.get("outcome") or "", "")
                + (f": {rec.get('why')}" if rec.get("why") and not ok else "")),
                "receipt": {"run": rec.get("id") or "", "state": rec.get("state") or "",
                            "receipt": (rec.get("receipt") or {}).get("id") or ""}}
    return apply


# ── The run ─────────────────────────────────────────────────────────────────────────────────

def _step(rec: dict, name: str, result: str, words: str, **more) -> None:
    from modules import op_progress
    from modules.redact import redact_text

    rec["steps"].append(dict({"step": name, "result": result, "words": redact_text(words),
                              "at": _iso(time.time())}, **more))
    op_progress.moved()


def _net_zero_after_rollback(ctx, rec: dict, run: CheckRun) -> None:
    """After a rollback of a plan that was not net zero, the configuration read again (holding
    the device) and compared with the one read before once more (`net_zero`), in the scope the
    run's own check used (`_net_zero_after`'s *scope*: the same interface sections, or the
    whole configuration where the run's was whole): the pipeline's rollback inverts only the
    program's own lines, so a line the device added (a sticky MAC learned on recovery) is still
    there. Kept as ``rec["net_zero"]["after_rollback"]`` (the lines still differing, masked;
    ``None`` when it could not be read) and ``rec["net_zero"]["after_rollback_scope"]``."""
    nz = rec.get("net_zero") or {}
    if not ctx.rollback_performed or not nz.get("differs"):
        return
    pre = (ctx.pre_snapshots or {}).get(ctx.device_ips[0]) or {}
    scope = "interfaces" if nz.get("scope") == "interfaces" else "full"
    got = _net_zero_after(ctx, run, pre, scope=scope)
    if got.get("error"):
        log.warning("command plan: the configuration after the rollback was not read: %s",
                    got["error"])
    nz["after_rollback"] = got["differs"] if got.get("checked") else None
    nz["after_rollback_scope"] = got["scope"]
    rec["net_zero"] = nz


def _outcome(ctx, rec: dict = None) -> tuple:
    """``(outcome, words)`` from the pipeline's result, and the net-zero check after a
    rollback (`_net_zero_after_rollback`)."""
    ip = ctx.device_ips[0]
    left = ((rec or {}).get("net_zero") or {}).get("after_rollback", [])
    if ctx.rollback_performed and left is None:
        return "failed", ("the configuration differed from before, was rolled back, and could "
                          "not be read again to tell whether the rollback restored it: read the "
                          "device before anything else")
    if ctx.rollback_performed and left:
        return "failed", ("the configuration differed from before, and after the rollback it "
                          "still differs: " + "; ".join(left[:8])
                          + (" …" if len(left) > 8 else "") + ". NOT RESTORED: read the device "
                          "before anything else")
    if "pre_apply" in ctx.stages_failed or (
            ctx.stages_failed and not ctx.push_results and not ctx.rollback_performed):
        return "refused", ctx.error or "refused before the send. Nothing was sent"
    v = (ctx.verify_result or {}).get(ip) or {}
    differs = ((v.get("plan_checks") or {}).get("net_zero") or {}).get("differs") or []
    if ctx.rollback_performed:
        o = (ctx.rollback_outcome or {}).get(ip) or {}
        said = f"; the rollback: {o.get('state') or 'not recorded'} ({o.get('detail') or ''})"
        if differs:
            return "not_net_zero", ("the configuration after differed from before: "
                                    + "; ".join(differs[:8]) + said)
        return "rolled_back", (ctx.error or "verify failed") + said
    stop = (v.get("plan_checks") or {}).get("stop") or {}
    if ctx.final_status == "success" and stop.get("outcome") in OUTCOMES:
        # The plan's own stop (a re-trip): its outcome and its words, nothing rolled back.
        return stop["outcome"], stop.get("words") or OUTCOME_WORDS[stop["outcome"]]
    if ctx.final_status == "success" and v.get("ok") is True:
        return "done", "ran, verified, and the configuration is as it was before"
    if ctx.final_status == "success":
        return "unverified", "; ".join(v.get("unreadable") or []) or "verify did not pass"
    return "failed", ctx.error or "the run failed"


def _receipt(network: str, ctx, rec: dict, p: dict, outcome: str) -> dict:
    from modules.nsot import receipts

    ip = ctx.device_ips[0]
    result = {"device": rec["device"], "outcome": "deployed" if outcome == "done" else "failed",
              "stage": (ctx.stages_failed or [""])[-1], "reason": rec.get("why") or "",
              "commands": list(p["program"]), "program_hash": rec["hash"],
              "authorised": p["authorised"], "verify": (ctx.verify_result or {}).get(ip) or {},
              "rolled_back": ctx.rollback_performed,
              "rollback_outcome": (ctx.rollback_outcome or {}).get(ip) or {},
              "rollback_commands": (ctx.rollback_commands or {}).get(ip) or [],
              "rollback_not_undone": (ctx.rollback_not_undone or {}).get(ip) or [],
              "command_plan": {"plan": rec["key"], "run": rec["id"], "hash": rec["hash"],
                               "values": rec["params"], "outcome": outcome,
                               "net_zero": rec.get("net_zero") or {}}}
    rows = receipts.rows_for({"results": [result], "golden": {}}, list_name=network,
                             action=KIND, actor=rec["actor"], actor_kind="person",
                             command_hashes={rec["device"]: rec["hash"]})
    got = receipts.write(network, rows)
    return {"id": rows[0]["id"] if rows else "", "written": bool(got.get("ok")),
            "error": str(got.get("error") or "")}


def _finish(network: str, rec: dict, outcome: str, words: str, t=None) -> dict:
    from modules.nsot import command_plan as CP
    from modules.nsot import privileged

    rec.update(outcome=outcome, state=RECORD_STATE.get(outcome, "failed"), why=words,
               finished_at=time.time())
    _step(rec, "record", "ok", OUTCOME_WORDS.get(outcome, outcome))
    if t is not None and t.on_finish:
        try:
            CP.resolve(CP.FINISH_HOOKS[t.on_finish])(network, rec)
        except Exception as exc:                      # noqa: BLE001 (said in the record)
            rec["on_finish_error"] = f"{type(exc).__name__}: {exc}"
    marks = rec.get("laps")
    if isinstance(marks, list) and marks and isinstance(marks[0], tuple):
        from modules.pipeline import lap
        lap(marks, "record")
        rec["laps"] = _laps(marks)
    privileged.record(network, rec)
    try:
        from modules import invalidation
        invalidation.announce(invalidation.ANNOUNCERS[ANNOUNCER], by=ANNOUNCER)
    except Exception as exc:                          # noqa: BLE001 (a page's freshness only)
        log.info("command plan: a run recorded, not announced: %s", exc)
    log.info("command plan: %s on %s/%s: %s", rec.get("actor"), network, rec.get("device"),
             outcome)
    return rec


def run(network: str, key: str, values: dict, *, actor: str, actor_verified: str,
        person: bool, confirmed: str, reason: str = "", incident: str = "", fixit=None,
        run_id: str = "", sources=None, authority: dict = None) -> dict:
    """Run the approved plan *key* with *values* on its device (the module docstring), as
    *actor*, a person verified as *actor_verified*, bound to *confirmed* (the plan's hash as
    previewed): the run's record, written. *incident* is the incident it acts in (a named
    check reads its classification). Never raises; a refusal is a record too."""
    from modules import op_progress
    from modules.heal.resubscribe import fixit_field
    from modules.nsot import command_plan as CP
    from modules.nsot import command_policy, device_ops, reads

    src = sources or Sources(network)
    if getattr(src, "reuse", None) is not None:
        # The approved run reads its device live, always (CLAUDE.md's display-only rule): a
        # proposing job's kept reads (`Reused`) answer its preflight's card alone.
        log.warning("command plan: a run was handed kept reads; it reads live instead")
        src = Sources(network, clock=src.clock, sleep=src.sleep, model=src.model,
                      families=getattr(src, "_families", None))
    now = time.time()
    device = str((values or {}).get("device") or "") if isinstance(values, dict) else ""
    rec = {"id": run_id or reads.new_id(), "list": network, "device": device,
           "key": str(key)[:50], "kind": KIND, "command": f"{OPERATION}: {str(key)[:50]}",
           "actor": actor, "actor_verified": (actor_verified if isinstance(actor_verified, str)
                                              and actor_verified else "none"),
           "reason": (reason or "").strip()[:500], "started_at": now, "finished_at": None,
           "at": _iso(now), "state": "running", "outcome": "running", "config_change": False,
           "hash": "", "program": [], "params": {}, "steps": [],
           # The run's timing record (the operator, 2026-11-16), ``(lap, epoch)`` marks until
           # `_finish` writes them as ``[{"lap", "at_s", "took_s"}]``.
           "laps": [("start", now)]}
    link = fixit_field(fixit)
    if link:
        rec["fixit"] = link
    op_progress.attach(STEPS, rec["steps"], run=rec["id"],
                       labels={k: v.format(device=device) for k, v in STEP_LABELS.items()})
    if authority is not None:
        # A promoted self-heal script's run (C3696): its promoter's standing approval stands
        # for a person's press, held by `saved_plans.authority_refusal`; recorded as such.
        from modules import identity
        from modules.nsot import saved_plans
        # Recorded as Mercury's, by the script, on its promoter's standing approval: never as
        # the person's own press (Gate 1b's review, item 8).
        rec.update(authority=dict(authority, promoted_by=actor), actor_kind="authority",
                   actor=identity.MERCURY_ACTOR.format(
                       job=f"saved script {authority.get('script')}, promoted by "
                           f"{actor or 'no one'}"))
        why = saved_plans.authority_refusal(key, authority, network)
        why = f"{why}. Nothing was sent" if why else ""
    else:
        why = person_refusal(actor, actor_verified, person)
    if why:
        _step(rec, "approve", "refused", why)
        return _finish(network, rec, "refused", why)
    p = CP.preview(network, key, values, sources=src.model)
    rec.update(params=dict(p["values"]), program=list(p["program"]), title=p["title"])
    if not p["ok"]:
        why = "; ".join(p["refusals"]) + ". Nothing was sent"
        _step(rec, "approve", "refused", why)
        return _finish(network, rec, "refused", why)
    if str(confirmed or "") != p["hash"]:
        why = (f"the plan changed since the preview you approved (approved "
               f"{confirmed or 'no hash'}, now {p['hash']}). Nothing was sent; preview again")
        _step(rec, "approve", "refused", why)
        return _finish(network, rec, "refused", why)
    t = CP.template_of(key)
    rec["hash"] = p["hash"]
    _step(rec, "approve", "ok", f"the plan is the one approved ({p['hash']})")
    from modules.pipeline import lap
    lap(rec["laps"], "approve")
    dev = p["device_row"]
    check_run = CheckRun(network, device, dev, p["derived"], incident, src)
    ctx = None
    try:
        with device_ops.hold(network, device, OPERATION, actor, detail=p["title"],
                             ip=dev.get("ip", "")):
            _step(rec, "hold", "ok", f"{device} held for the whole run")
            lap(rec["laps"], "hold")
            with reads.within(OPERATION, rec["id"], "preconditions", RECORD):
                ctx = context(network, t, p, check_run, rec)
                # What is sent is the program approved by its hash, byte for byte.
                ctx.confirmed_commands = {dev.get("ip", ""): list(p["program"])}
                from modules.pipeline import PipelineRunner
                try:
                    PipelineRunner(ctx).run()
                    _net_zero_after_rollback(ctx, rec, check_run)
                finally:
                    # No read reopens the pool once it is closed: the run's reads open their
                    # own again (none is made past here but `on_finish`'s, its own sources).
                    if hasattr(src, "ride"):
                        src.ride()
                    from modules.connection import close_persistent_connection
                    for ip in list(ctx.connections_pool):
                        close_persistent_connection(ip, ctx.connections_pool, ctx.pool_lock)
                    lap(rec["laps"], "pipeline: session closed")
    except device_ops.DeviceBusy as exc:
        _step(rec, "hold", "refused", str(exc))
        return _finish(network, rec, "refused", f"{exc}. Nothing was sent", t)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.exception("command plan: %s on %s failed", key, device)
        return _finish(network, rec, "failed" if rec["config_change"] else "refused",
                       f"{type(exc).__name__}: {exc}", t)
    outcome, words = _outcome(ctx, rec)
    if ctx.stages_failed and outcome == "refused" and not any(
            s["step"] in ("read_before", "preconditions") and s["result"] == "refused"
            for s in rec["steps"]):
        _step(rec, "preconditions", "refused", words)
    if outcome != "refused":
        pushed = (ctx.push_results or {}).get(ctx.device_ips[0]) or {}
        _step(rec, "send", "ok" if pushed.get("ok") else "fail",
              ("the plan's lines sent in config mode, never saved" if pushed.get("ok")
               else f"the send failed: {pushed.get('error') or ctx.error or 'not recorded'}"))
        v = (ctx.verify_result or {}).get(ctx.device_ips[0]) or {}
        stop = (v.get("plan_checks") or {}).get("stop") or {}
        _step(rec, "verify", "ok" if v.get("ok") is True else "fail",
              "; ".join((v.get("issues") or []) + (v.get("unreadable") or []))
              or stop.get("words")
              or "every check held, and the configuration is as it was before",
              checks=rec.get("verify_checks") or [])
        if ctx.rollback_performed:
            o = (ctx.rollback_outcome or {}).get(ctx.device_ips[0]) or {}
            _step(rec, "rollback", "ok" if o.get("state") in ("restored", "nothing_to_undo")
                  else "fail", f"{o.get('state') or 'not recorded'}: {o.get('detail') or ''}",
                  commands=list((ctx.rollback_commands or {}).get(ctx.device_ips[0]) or []))
    rec.update(outcome=outcome, why=words)
    rec["receipt"] = _receipt(network, ctx, rec, p, outcome)
    if rec["config_change"]:
        try:
            sent = [s for _raw, s in command_policy.shapes(t.commands)]
            rec["measured_shapes"] = command_policy.record_measurement(
                network, p["dialect"], sent, device=device, run=rec["id"], outcome=outcome,
                answer=str(((ctx.push_results or {}).get(ctx.device_ips[0]) or {})
                           .get("output") or ""))
        except Exception as exc:                      # noqa: BLE001 (said in the record)
            rec["measured_shapes_error"] = f"{type(exc).__name__}: {exc}"
    return _finish(network, rec, outcome, words, t)
