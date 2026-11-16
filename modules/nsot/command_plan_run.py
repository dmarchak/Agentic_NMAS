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
   refused, the record naming each line). A transient plan is never saved to startup and
   records no golden (`PipelineContext.transient`). Rollback is the pipeline's.
4. **The record**: the receipt (`receipts`, action ``command_plan``, no intent commit), the
   run's record in the operations' record History reads (`privileged.record`, its key the
   plan's), each new shape's measurement (`command_policy.record_measurement`), and the
   plan's ``on_finish`` hook (G7's notification of the MAC, the port, the time and the cause).

One device per plan; a plan engine step is one plan, and the engine stops on the first that
does not pass.
"""

import logging
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


class Sources:
    """Where a run reads: Mercury's model (`command_plan.Sources`), the read engine, the
    clock and the sleep, and a problem's own sources by family (``of``: G7's Loki lines)."""

    def __init__(self, network: str, *, clock=time.time, sleep=time.sleep, model=None,
                 families=None):
        from modules.nsot import command_plan

        self.network, self.clock, self.sleep = network, clock, sleep
        self.model = model or command_plan.Sources(network)
        self._families = dict(families or {})

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
        engine, inline: the run already holds the device, so the read's hold is re-entrant."""
        from modules.nsot import reads

        try:
            rec = reads.run(self.network, [host], commands, "Mercury (reviewed commands)",
                            purpose="a command plan's precondition or verify read",
                            inline=True)
        except reads.Refused as exc:
            log.warning("command plan: a read was refused: %s", exc)
            return {c: None for c in commands}
        r = (rec.get("results") or {}).get(host) or {}
        got = {a["command"]: a.get("answer") or "" for a in r.get("answers") or []
               if a.get("state") == reads.ANSWERED}
        return {c: got.get(c) for c in commands}


class CheckRun:
    """What a named check is handed: the run's network, device and inventory row, the
    validated values (`derived`), the incident it acts in, the sources and the time; *found*
    is what a check learned from the device for the run's record (G7's violating MAC)."""

    def __init__(self, network, device, dev, derived, incident, sources):
        self.network, self.device, self.dev = network, device, dev
        self.derived, self.incident, self.sources = derived, incident, sources
        self.found = {}

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
    """The pre-apply check: each precondition read again (one read engine run, holding the
    device) and judged; all must pass, and stage 4 must have read the configuration before.
    Returns the pipeline's hook, ``hook(ctx) -> why or ""``."""
    from modules.nsot import command_plan as CP

    def hook(ctx):
        ip = run.dev.get("ip", "")
        if not ((ctx.pre_snapshots or {}).get(ip) or {}).get("running_config"):
            why = ("the running configuration before the plan could not be read, so whether "
                   "the plan is net zero cannot be checked. Nothing was sent")
            _step(rec, "read_before", "refused", why)
            return why
        _step(rec, "read_before", "ok", "the running configuration read before anything is "
                                        "sent, holding the device")
        cmds = list(dict.fromkeys(CP.substitute(i["read"], run.derived)
                                  for i in t.preconditions if i["read"]))
        answers = run.sources.read(run.device, cmds) if cmds else {}
        judged = _judge(t.preconditions, run, answers)
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
        # From here the send may land: the record says so, so an end that raises says
        # whether anything was sent, and the run spans its lines (`heal.attribution` rule 4).
        rec["config_change"] = True
        return ""
    return hook


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


def plan_verify(t, run: CheckRun, rec: dict):
    """The pipeline's verify hook for the plan: its verify reads, then the net-zero check.
    ``hook(ctx, ip, pre, post) -> {"issues", "unreadable", "checks", "net_zero"}``; an issue
    fails verify and rolls back."""
    def hook(ctx, ip, pre, post):
        from modules.commands import run_device_command
        from modules.connection import get_persistent_connection

        checks = [_verify_item(i, run, (pre or {}).get("running_config") or "")
                  for i in t.verify]
        # A re-trip (the operator, 2026-11-16) is the run's outcome, never an issue: the port
        # is down again by its own cause, which explains the reads that fail on it, so they
        # roll nothing back; the net-zero check below still does.
        retrip = next((c for c in checks if c["result"] == RETRIPPED), None)
        stop = ({"outcome": RETRIPPED, "words": retrip["words"],
                 "interfaces": [run.derived.get("interface") or ""]} if retrip else {})
        issues = [f"{c['name']}: {c['words']}" for c in checks
                  if c["result"] == "fail" and not retrip]
        unread = [f"{c['name']}: {c['words']}" for c in checks if c["result"] == "unreadable"]
        dev = run.dev
        try:
            after = run_device_command(get_persistent_connection(
                dev, ctx.connections_pool, ctx.pool_lock), "show running-config") or ""
        except Exception as exc:                      # noqa: BLE001 (neither pass nor fail)
            after = ""
            unread.append(f"the running configuration after the plan could not be read "
                          f"({type(exc).__name__}): whether it is net zero cannot be told")
        differs = net_zero((pre or {}).get("running_config") or "", after) if after else []
        if differs:
            issues.append("the running configuration after the plan differs from the one "
                          f"before it ({len(differs)} line(s): " + "; ".join(differs[:8])
                          + (" …" if len(differs) > 8 else "") + "): a command plan is net "
                          "zero, so it is rolled back and refused")
        rec["verify_checks"] = checks
        rec["net_zero"] = {"checked": bool(after), "differs": differs}
        if run.found:
            rec["found"] = dict(run.found)
        return {"issues": issues, "unreadable": unread, "checks": checks,
                "net_zero": {"checked": bool(after), "differs": differs}, "stop": stop}
    return hook


def context(network: str, t, p: dict, run: CheckRun, rec: dict):
    """The pipeline's context for the plan *p* (a preview): its gate's authorisations, the
    planned window of the links it touches, transient, and the plan's pre-apply and verify
    hooks. Its program is confirmed by `run`, beside the runner it is confirmed for (C765:
    every product run confirms its list first, tests/test_pipeline.py)."""
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
    return ctx


def preconditions_now(network: str, key: str, p: dict, *, sources=None,
                      incident: str = "") -> list:
    """The plan *p*'s preconditions read now through the read engine and judged, holding
    nothing beyond the reads' own holds (a proposal's preflight, `catalog.PlanStep`); the run
    reads them again holding the device. *incident* is the one it is proposed in, so a check
    reads its classification as the run's does. ``[{"name", "read", "result", "words"}]``."""
    from modules.nsot import command_plan as CP

    t = CP.template_of(key)
    src = sources or Sources(network)
    run_ = CheckRun(network, p["values"].get("device") or "", p["device_row"], p["derived"],
                    str(incident or ""), src)
    cmds = list(dict.fromkeys(CP.substitute(i["read"], p["derived"])
                              for i in t.preconditions if i["read"]))
    return _judge(t.preconditions, run_, src.read(run_.device, cmds) if cmds else {})


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


def _net_zero_after_rollback(ctx, rec: dict, dev: dict) -> None:
    """After a rollback of a plan that was not net zero, the running configuration read again
    (holding the device) and compared with the one read before once more (`net_zero`): the
    pipeline's rollback inverts only the program's own lines, so a line the device added (a
    sticky MAC learned on recovery) is still there. Kept as ``rec["net_zero"]["after_rollback"]``
    (the lines still differing, masked; ``None`` when it could not be read)."""
    nz = rec.get("net_zero") or {}
    if not ctx.rollback_performed or not nz.get("differs"):
        return
    from modules.commands import run_device_command
    from modules.connection import get_persistent_connection

    before = ((ctx.pre_snapshots or {}).get(ctx.device_ips[0]) or {}).get("running_config") or ""
    try:
        after = run_device_command(get_persistent_connection(
            dev, ctx.connections_pool, ctx.pool_lock), "show running-config") or ""
    except Exception as exc:                          # noqa: BLE001 (said: not told)
        log.warning("command plan: the configuration after the rollback was not read: %s", exc)
        after = ""
    nz["after_rollback"] = net_zero(before, after) if after else None
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
    now = time.time()
    device = str((values or {}).get("device") or "") if isinstance(values, dict) else ""
    rec = {"id": run_id or reads.new_id(), "list": network, "device": device,
           "key": str(key)[:50], "kind": KIND, "command": f"{OPERATION}: {str(key)[:50]}",
           "actor": actor, "actor_verified": (actor_verified if isinstance(actor_verified, str)
                                              and actor_verified else "none"),
           "reason": (reason or "").strip()[:500], "started_at": now, "finished_at": None,
           "at": _iso(now), "state": "running", "outcome": "running", "config_change": False,
           "hash": "", "program": [], "params": {}, "steps": []}
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
    dev = p["device_row"]
    check_run = CheckRun(network, device, dev, p["derived"], incident, src)
    ctx = None
    try:
        with device_ops.hold(network, device, OPERATION, actor, detail=p["title"],
                             ip=dev.get("ip", "")):
            _step(rec, "hold", "ok", f"{device} held for the whole run")
            with reads.within(OPERATION, rec["id"], "preconditions", RECORD):
                ctx = context(network, t, p, check_run, rec)
                # What is sent is the program approved by its hash, byte for byte.
                ctx.confirmed_commands = {dev.get("ip", ""): list(p["program"])}
                from modules.pipeline import PipelineRunner
                try:
                    PipelineRunner(ctx).run()
                    _net_zero_after_rollback(ctx, rec, dev)
                finally:
                    from modules.connection import close_persistent_connection
                    for ip in list(ctx.connections_pool):
                        close_persistent_connection(ip, ctx.connections_pool, ctx.pool_lock)
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
