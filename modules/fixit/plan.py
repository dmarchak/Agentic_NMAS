"""An incident's proposal as a PLAN of catalog operations, preflighted before it is drawn (C3694;
the operator's R1 flow, 2026-11-14, steps 3, 4 and 6; docs/HEAL_TO_INTENT.md sections 12 and
20).

**A plan is 1 to `incident.MOST_STEPS` operations of the catalog** (`modules/heal/catalog.py`),
in order, each with the parameters its schema names, never a composed command. A proposal line
of the incident's record holds them (``steps``; a line of one operation is a plan of one,
`steps_of`). It runs as the plan engine's ``incident-fix`` plan (`plan_engine.INCIDENT_FIX`):
approved ONCE by its hash, each step's own apply re-checking its own hash, the first that does
not pass stopping it, nothing retried.

**Preflight, before anything is drawn** (`preflight`, the R1 flow's step 4): each step is
asked what it would do if it ran now, by the check every proposal passes (`validate.check`:
the catalog's schema, the incident's scope, the device managed, the planned work, holds and
windows of guard 3, committed intent through the operation's own preview), and **a step that
repeats what already failed in this incident is refused** (the operator, R2: "Never offer, as
the next action, anything that already failed on this incident"). A refused step is drawn
refused with why, and the plan is then not approvable: a refusal is shown in the proposal,
never discovered after approval. The per-incident and day caps hold the AI's calls, never a
plan's run, which spends nothing.

**The plan's hash binds every step's own hash**, the incident, the proposal and the order: it
is the plan engine's (`plan_engine.plan_hash` over `plan_engine.checked`'s steps), so the hash
drawn is the one Approve sends and the engine compares (`plan_engine.start`).

Reads only: the incident's record, the operations' run records, the inventory, committed
intent and the planned windows. Nothing here runs, holds, starts or asks anything
(tests/test_fixit_incident.py's scan of `modules/fixit/`).
"""

import logging
import time

log = logging.getLogger(__name__)

#: A catalog parameter's name in an attempt's form (`validate.AS_ATTEMPT`), reversed.
AS_CATALOG = {"subs": "subscriptions", "sub": "subscription",
              # G7 (C3712): Recover an err-disabled interface's, by the same names.
              "interface": "interface", "cause": "cause"}
#: A repeat's risk, the attempt it repeats named: drawn on the step, which stays approvable
#: (the operator, 2026-11-17: plan.py's repeat refusal removed).
REPEAT_WORDS = ("risk: it already failed on this incident as attempt {attempt} ({words}); "
                "approving runs it again")


def as_catalog(operation: str, params: dict, device: str) -> dict:
    """An attempt-form proposal's parameters (`incident.canonical`) as the catalog takes them
    (`catalog.checked`): the incident's *device*, each parameter by the catalog's name, the
    collector flag (an attempt's, never the catalog's) left out."""
    from modules import plan_engine as PE
    from modules.heal import resubscribe as R

    out = {"device": device}
    if operation in PE.FIX_ADMITTED:
        # A step kind the fix admits beside the catalog: its own parameters, by their own
        # names (`StepKind.params`), the incident and proposal the plan gives it left out, and
        # a value only its preview resolves (a deploy's program) never a parameter.
        names = {p.name for p in PE.STEP_KINDS[operation].params} - {"device", "incident",
                                                                    "proposal"}
        out.update({k: (list(v) if isinstance(v, (list, tuple)) else v)
                    for k, v in (params or {}).items() if k in names})
        return out
    for k, v in (params or {}).items():
        if k in AS_CATALOG:
            out[AS_CATALOG[k]] = list(v) if isinstance(v, (list, tuple)) else v
    if operation == R.READD_KEY:
        out.pop("subscriptions", None)
    return out


def steps_of(line: dict, device: str) -> list:
    """The plan a proposal *line* holds, ``[{"operation", "params"}]`` in the catalog's form:
    its ``steps`` when it keeps them, else its one operation (a plan of one), else ``[]`` (a
    line that proposed nothing)."""
    raw = line.get("steps") if isinstance(line.get("steps"), list) else None
    if raw is None:
        raw = ([{"operation": line["operation"], "params": line.get("params") or {}}]
               if line.get("operation") else [])
    return [{"operation": s["operation"], "params": as_catalog(s["operation"], s["params"],
                                                               device)}
            for s in raw if isinstance(s, dict) and s.get("operation")]


def plan_params(incident, line: dict) -> dict:
    """The plan engine's parameters for *line*'s plan in *incident*: ``{"incident",
    "proposal", "steps"}``. A collector step carries the session read when the plan was
    proposed (``session``, `plan_engine.read_sessions`, kept on the line), so the plan's
    hash binds it and What its hash binds draws it; a step whose read named none carries
    none."""
    from modules.heal import resubscribe as R

    kept = line.get("sessions") if isinstance(line.get("sessions"), dict) else {}
    steps = steps_of(line, incident.device)
    for n, s in enumerate(steps, 1):
        got = str((kept.get(str(n)) or {}).get("session") or "")
        if s["operation"] in R.COLLECTOR_STEP_KEYS and got:
            s["session"] = got
    return {"incident": incident.id, "proposal": line.get("proposal") or "", "steps": steps}


def _check_one(incident, operation: str, params: dict, *, resolved=None, now=None,
               sources=None, planned=None) -> dict:
    """One step's preflight: ``{"ok", "hash", "drawn", "refused", "code", "repeat", "warn"}``;
    a repeat of a failed attempt is approvable, its risk in *warn*."""
    from modules.fixit import validate as V

    got = V.check(incident, operation, params, resolved=resolved, now=now, sources=sources,
                  planned=planned)
    if not got["ok"]:
        return {"ok": False, "hash": "", "drawn": {}, "refused": got["refused"],
                "code": got["code"], "repeat": {}, "warn": ""}
    rep = got.get("repeat") or {}
    warn = ""
    if rep.get("kind") == "repeat":
        from modules.fixit.section import outcome_words

        warn = REPEAT_WORDS.format(
            attempt=rep.get("attempt"),
            words=outcome_words(rep.get("outcome") or "", rep.get("words") or "")
            or "it did not pass")
    return {"ok": True, "hash": got["hash"], "drawn": got["preview"], "refused": "",
            "code": "", "repeat": rep, "warn": warn}


def _admitted_one(incident, operation: str, params: dict, candidate: dict) -> dict:
    """One step of a kind the fix admits beside the catalog (`plan_engine.FIX_ADMITTED`),
    preflighted by its own step kind's preview (`StepKind.preview`: the incident's scope, the
    heal guards, the repeat of a failed attempt, then its own checks), on the engine's own
    parameters, handed *candidate* (the intent an earlier step would commit; updated here with
    this one's): ``_check_one``'s shape, with what it resolved. A read."""
    from modules import plan_engine as PE

    kind = PE.STEP_KINDS[operation]
    got = kind.preview(incident.network, params,
                       **({"candidate": dict(candidate)} if kind.candidate else {}))
    if got.get("ok"):
        candidate.update(got.get("candidate") or {})
    from modules.redact import redact_payload

    return {"ok": bool(got.get("ok")), "hash": got.get("hash") or "" if got.get("ok") else "",
            "drawn": redact_payload(got.get("drawn") or {}),
            "refused": got.get("refused") or "", "code": got.get("code") or (
                "" if got.get("ok") else "refused"),
            "repeat": {}, "resolved": dict(got.get("resolved") or {})}


def admitted_repeat(network: str, p: dict, operation: str, compared: dict) -> tuple:
    """``(refusal, differs)``: the catalog's repeat rule (`incident.repeat_of`) for a step of a
    kind the fix admits beside the catalog, on the values its kind compares an attempt by
    (*compared*): an attempt of this incident that ran *operation* with the same values and
    failed is named as a risk (`REPEAT_WORDS`, naming the attempt), never refused (the
    operator, 2026-11-17); one that ran it with other values is named with each value that
    differs; ``("", "")`` when none ran it. A read."""
    from modules.fixit import incident as F
    from modules.fixit.section import outcome_words

    incident, why = _incident_for(network, p.get("incident") or "")
    if incident is None:
        return why, ""
    got = F.repeat_of(incident, operation, compared)
    if got["kind"] == "repeat":
        return "", REPEAT_WORDS.format(attempt=got["attempt"], words=outcome_words(
            got["outcome"], got["words"]) or "it did not pass")
    if got["kind"] == "variation":
        return "", (f"attempt {got['attempt']} ran it and did not pass; this one differs in "
                    + "; ".join(f"{c['name']} (was {str(c['before'])[:60] or 'none'}, now "
                                f"{str(c['after'])[:60] or 'none'})" for c in got["changed"]))
    return "", ""


def _incident_for(network: str, incident_id: str):
    """``(incident, why)``: the incident *incident_id* of *network* as the fix-it record takes
    it, or None with why."""
    from modules import incident_page
    from modules.fixit import section

    found = incident_page.resolve(network, incident_id)
    if found["found"] != "page":
        return None, f"{incident_id} is no incident of {network} that has a page"
    got = section.incident_of(network, found)
    return got["incident"], got["why"]


def step_preview(network: str, key: str, p: dict) -> dict:
    """A plan step's own preview as the plan engine asks it (`plan_engine._catalog_preview`),
    at its preview and again before its apply: *p* holds the incident, its proposal and the
    catalog's parameters. ``{"ok", "hash", "drawn", "refused"}``, refused (nothing previewed)
    when the incident has no page, the step repeats a failed attempt, or the check refuses."""
    incident, why = _incident_for(network, p.get("incident") or "")
    if incident is None:
        return {"ok": False, "hash": "", "drawn": {}, "refused": why}
    # The collector step's bound session is the plan engine's to read again (its close
    # helper's dry run is no read of this package's: `plan_engine._catalog_preview`).
    params = {k: v for k, v in p.items() if k not in ("incident", "proposal", "session")}
    got = _check_one(incident, key, params)
    return {"ok": got["ok"], "hash": got["hash"] if got["ok"] else "", "drawn": got["drawn"],
            "refused": got["refused"]}


def run_link_of(network: str, p: dict) -> dict:
    """What a plan step's run record names (`incident.RUN_FIELD`): its incident, the attempt's
    number and the proposal (`incident.run_link`), or ``{}`` when the incident cannot be read
    (the run is then the incident's by its window, as any run on its device is)."""
    from modules.fixit import incident as F

    incident, _why = _incident_for(network, p.get("incident") or "")
    if incident is None:
        return {}
    try:
        return F.run_link(incident, p.get("proposal") or "")
    except F.Refused as exc:
        log.warning("fixit plan: %s: its run names no proposal: %s", p.get("incident"), exc)
        return F.run_link(incident)


def _unverified_mark(line: dict, n: int) -> str:
    """The words of step *n*'s unverified mark when it rests ONLY on citations not in what was
    sent (``shown.steps``, kept with an AI line), else ``""``."""
    shown = line.get("shown") if isinstance(line.get("shown"), dict) else {}
    for st in shown.get("steps") or ():
        if isinstance(st, dict) and st.get("n") == n and st.get("only_unverified"):
            return str(st.get("unverified_words") or "unverified")
    return ""


#: How a command plan's and a deploy's lines reach the device: the pipeline's one push
#: (`pipeline._push_via_netmiko`, netmiko's ``send_config_set``) enters config mode with
#: `CONFIG_IN` and leaves it with `CONFIG_OUT`; a re-subscribe's units carry both themselves.
CONFIG_IN, CONFIG_OUT = "configure terminal", "end"
#: Whether a step kind saves to startup: a command plan is transient (`command_plan_run`,
#: ``ctx.transient``), a re-subscribe refuses a save shape (`bounce.assert_no_save`), a deploy
#: saves once its verify passes (`pipeline._stage_save_startup`: ``write memory``).
NOT_SAVED, SAVED_AFTER_VERIFY = "not saved", "write memory (once its verify passes)"


def sent_of(operation: str, drawn, device: str) -> dict:
    """What a step sends to *device*, as the operator's rule (2026-11-16) asks the plan card to
    show before Approve, from what the step's hash binds (*drawn*, its own preview's): ``{"device",
    "lines", "save", "diff", "host", "binds"}``. *lines* in the order sent, config mode's entry
    and exit included; *diff* an intent change's before/after; *host* what it does on Mercury's
    host (no device line); *binds* what the hash binds instead, for a step that names no lines."""
    import os

    from modules.heal import catalog
    from modules.heal import collector_close as CC
    from modules.heal import resubscribe as R

    d = drawn if isinstance(drawn, dict) else {}
    out = {"device": device, "lines": [], "save": "", "diff": "", "host": "", "binds": ""}
    if catalog.is_command_plan(operation):
        # The hash binds the program between entry and exit (`command_plan.bound_fields`).
        return dict(out, lines=[CONFIG_IN, *[str(x) for x in d.get("program") or []], CONFIG_OUT],
                    save=NOT_SAVED)
    if operation == R.CLOSE_KEY:
        # The collector step alone (2026-11-16): the host's one action; nothing to the device.
        close = d.get("close") or {}
        host = (f"close TCP session {close['remote']} -> {close['local']} "
                f"({os.path.basename(CC.HELPER)})" if close else
                "close the collector's stale session, as the close helper's dry run names it "
                "at Approve")
        return dict(out, host=host, binds=f"sends nothing to {device}",
                    parts=[{"system": "the Mercury host (collector)", "actions": [host]}])
    if operation in (R.KEY, R.READD_KEY, R.COLLECTOR_KEY):
        # The hash binds this program whole, entry and exit in each unit (`program_hash`), and
        # the session to close (`close_id`): a combined operation is its systems' steps, in the
        # order run (the operator, 2026-11-16: "Step 1, on the Mercury host (collector): close
        # TCP session <device end> -> <collector end>. Step 2, on r7: ..."; the run stops at
        # the close's failure with nothing sent to the device, `resubscribe` `not_closed`).
        close = d.get("close") or {}
        lines = R.program_of(d.get("units") or [], operation == R.READD_KEY)
        host = (f"close TCP session {close['remote']} -> {close['local']} "
                f"({os.path.basename(CC.HELPER)})" if close else "")
        parts = ([{"system": "the Mercury host (collector)", "actions": [host]}] if host else [])
        parts.append({"system": device, "lines": lines, "save": NOT_SAVED})
        return dict(out, lines=lines, save=NOT_SAVED, host=host, parts=parts)
    if operation == "intent-deploy":
        # The hash binds the program's fingerprint (`plan_engine`'s deploy preview).
        return dict(out, lines=[CONFIG_IN, *[str(x) for x in d.get("program") or []], CONFIG_OUT],
                    save=SAVED_AFTER_VERIFY)
    if operation == "intent-edit":
        # The hash binds the intent before and after (`base`, `changes`, `text`): no device line.
        return dict(out, diff=str(d.get("diff") or ""),
                    binds="sends nothing to the device: a deploy step sends its lines")
    return dict(out, binds=f"its hash binds {operation}'s parameters, not lines it sends")


def lines_of(drawn) -> dict:
    """A command plan step's preview (`command_plan.drawn`) as the plan card draws it (board R5's
    screen 4, approved 2026-11-15): ``{"program", "checks", "verify"}``, *program* the exact
    lines sent (masked, as the preview drew them), *checks* each precondition's name and
    *verify* each verify item's ``{"name", "within", "within_why", "after"}`` (*within* the
    connect bound in seconds as the preview derived it for this port, *within_why* how, *after*
    a quiet wait's seconds). ``{}`` for a step whose preview is no command plan's."""
    d = drawn if isinstance(drawn, dict) else {}
    program = [str(x).strip() for x in d.get("program") or [] if str(x).strip()]
    if not program:
        return {}
    return {"program": program,
            "checks": [str(p.get("name") or "") for p in d.get("preconditions") or []
                       if isinstance(p, dict) and p.get("name")],
            "verify": [{"name": str(v.get("name") or ""), "within": v.get("within"),
                        "within_why": str(v.get("within_why") or ""), "after": v.get("after")}
                       for v in d.get("verify") or [] if isinstance(v, dict) and v.get("name")]}


def checked_of(line: dict, n: int) -> list:
    """Step *n*'s preconditions as the job that proposed *line* read and judged them
    (`fix_proposal._command_plan_reads`), each ``{"name", "result", "words", "reused"}``, a
    read it reused from that job saying its age in its words; ``[]`` when none was kept.
    Read from the record: a page draw reads nothing."""
    shown = line.get("shown") if isinstance(line.get("shown"), dict) else {}
    pre = (shown.get("preconditions_read") or {}).get(str(n)) or {}
    return [c for c in pre.get("checked") or [] if isinstance(c, dict)]


def preflight(incident, line: dict, *, resolved: float = None, now: float = None,
              sources=None, planned=None) -> dict:
    """*line*'s plan, every step preflighted (the module's docstring), as the section's
    ``proposal`` draws it: ``{"id", "hash", "refused_hash", "approvable", "steps", "found",
    "why_refused", "source", "by", "at", "calls", "note"}``; each step ``{"n", "operation",
    "words", "params", "hash", "preflight": {"ok", "refused"}, "repeat"}``. *hash* is the plan
    engine's over every step's own (`plan_engine.plan_hash`), ``""`` when a step is refused or
    the plan cannot be held to the engine's schema; *refused_hash* the same hash of a refused
    plan whose every step has its own (a repeat), for The record; a step's *repeat* is
    ``{"attempt", "params_hash"}`` when it repeats a failed attempt, else ``{}``; *approvable*
    only when every step would run; *bound* everything that hash binds, as rows a person reads
    (`plan_engine.bound_rows`, C3725), and *sessions* each collector step's session as read
    when the plan was proposed (`plan_engine.read_sessions`), bound by the hash. ``None`` for
    a line that
    proposed nothing. *sources* and *planned* are the check's seams (tests)."""
    from modules import plan_engine as PE
    from modules.fixit.handover import params_words
    from modules.fixit.section import SOURCE_WORDS, short_words

    steps = steps_of(line, incident.device)
    if not steps:
        return None
    at = time.time() if now is None else float(now)
    drawn, refused = [], ""
    # The plan as the engine holds it, read once: a step of a kind the fix admits beside the
    # catalog (`plan_engine.FIX_ADMITTED`) is preflighted by its own step kind's preview, on
    # the engine's own parameters, each later one handed the intent an earlier one would
    # commit (C3646), so the hash drawn is the one Approve's run computes.
    try:
        _p, _held, engine = PE.checked(PE.INCIDENT_FIX, plan_params(incident, line))
    except PE.Refused as exc:
        engine, not_held = None, f"The plan is not one Mercury runs: {exc}"
    candidate = {}
    for n, s in enumerate(steps, 1):
        never = PE.ai_step_refusal(s["operation"]) if line.get("source") == "ai" else ""
        if never:
            got = {"ok": False, "hash": "", "drawn": {}, "refused": never, "code": "ai_role",
                   "repeat": {}}
        elif s["operation"] in PE.FIX_ADMITTED:
            got = _admitted_one(incident, s["operation"], engine[n - 1]["params"], candidate) \
                if engine else {"ok": False, "hash": "", "drawn": {}, "refused": not_held,
                                "code": "schema", "repeat": {}}
        else:
            got = _check_one(incident, s["operation"], s["params"], resolved=resolved, now=at,
                             sources=sources, planned=planned)
            # A built-in command plan's preconditions, read once by the job that made the
            # proposal (`fix_proposal._command_plan_reads`, C3755): one that did not hold is a
            # warning on the step a person approves by hash (the operator, 2026-11-17), drawn
            # from the record, never read again on a page draw.
            pre = ((line.get("shown") or {}).get("preconditions_read") or {}).get(str(n)) or {}
            if got["ok"] and pre and not pre.get("ok"):
                got = dict(got, warn="; ".join(x for x in (
                    got.get("warn"), f"warning: its preconditions, read when it was proposed: "
                                     f"{pre.get('refused') or 'they did not hold'}") if x))
        # A step the AI rests only on citations that are not in what it was sent is marked,
        # and stays approvable (the operator, 2026-11-17): drawn from the marks kept with the
        # line (`fixit_troubleshoot.shown`), the citations named.
        mark = _unverified_mark(line, n)
        if got["ok"] and mark:
            got = dict(got, warn="; ".join(x for x in (
                got.get("warn"), f"unverified: it rests only on evidence Mercury could not "
                                 f"find: {mark}") if x))
        attempt = {AS_ATTEMPT_NAME.get(k, k): v for k, v in s["params"].items()
                   if k != "device"}
        rep = got.get("repeat") or {}
        own = got.get("drawn") or {}
        drawn.append({"n": n, "operation": s["operation"],
                      "words": (short_words(s["operation"], incident.device, attempt)
                                if s["operation"] not in PE.FIX_ADMITTED else
                                ": ".join(x for x in (own.get("title"), own.get("change")) if x)
                                or PE.words_of(s["operation"])),
                      "params": params_words(attempt), "hash": got["hash"],
                      "preflight": {"ok": got["ok"], "refused": got["refused"],
                                    "code": got["code"]},
                      # What a person approves it with in view (the operator, 2026-11-17):
                      # a repeat's risk, a precondition that did not hold, an unverified mark.
                      "warn": got.get("warn") or "",
                      # A step that repeats a failed attempt: the parameter hash it was
                      # compared by and the attempt it matched, for The record.
                      "repeat": ({"attempt": rep.get("attempt"),
                                  "params_hash": rep.get("params_hash") or ""}
                                 if rep.get("kind") == "repeat" else {}),
                      # What the step's own preview resolved (a deploy's program and capture),
                      # bound by the plan's hash as the engine's run binds it.
                      "resolved": dict(got.get("resolved") or {}),
                      # A command plan's exact lines, its checks and its verify (board R5's
                      # screen 4: the plan card lists what Approve sends), from its preview.
                      "lines": lines_of(got.get("drawn")),
                      # Each precondition as the proposing job judged it (`fix_proposal.
                      # _command_plan_reads`), a reused read's age in its words (2026-11-16).
                      "checked": checked_of(line, n),
                      # What it sends, per device, from what its hash binds (2026-11-16).
                      "sent": sent_of(s["operation"], own,
                                      str(s["params"].get("device") or incident.device))})
        if not got["ok"] and not refused:
            refused = f"Step {n} would be refused: {got['refused']}"
    # Each collector step's session, as read when the plan was proposed (PE.read_sessions):
    # drawn from the line, never read here (a page draw waits on nothing). A step whose read
    # named no session makes the plan unapprovable, saying why.
    from modules.heal import resubscribe as R
    kept = line.get("sessions") if isinstance(line.get("sessions"), dict) else {}
    sessions = []
    for d in drawn:
        if d["operation"] not in R.COLLECTOR_STEP_KEYS:
            continue
        s = dict(kept.get(str(d["n"])) or {}, n=d["n"])
        if not s.get("session") and d["operation"] == R.CLOSE_KEY and s.get("nothing"):
            # The collector step alone with nothing stale to close (the review of 2026-11-16):
            # approvable; it closes nothing and says so.
            pass
        elif not s.get("session"):
            # Words only (the operator, 2026-11-17): Approve reads the session (the plan
            # engine's own read), so the plan stays approvable.
            s["note"] = s.get("refused") or (
                "the plan was proposed before Mercury read the session it closes; Approve "
                "reads it")
            d["warn"] = "; ".join(x for x in (d.get("warn"), f"names no collector session "
                                              f"to close yet: {s['note']}") if x)
        sessions.append(s)
    plan_hash, refused_hash, bound = "", "", []
    # The plan's hash as Approve would have bound it, kept for The record when a step is
    # refused but every step still has its own hash (a repeat): the record names what was
    # refused; *hash* stays empty, so nothing approves it.
    if not refused or all(d["hash"] for d in drawn):
        try:
            _p, held, engine_steps = PE.checked(PE.INCIDENT_FIX, plan_params(incident, line))
        except PE.Refused as exc:
            refused = refused or f"The plan is not one Mercury runs: {exc}"
        else:
            for es, d in zip(engine_steps, drawn):
                es["hash"] = d["hash"]
                if d["resolved"]:
                    es["resolved"] = d["resolved"]
            got_hash = PE.plan_hash(PE.INCIDENT_FIX, held, engine_steps, incident.network)
            plan_hash, refused_hash = ("", got_hash) if refused else (got_hash, "")
            # Everything that hash binds, drawn in the plan before Approve (C3725); a refused
            # plan offers no Approve, and its hashes are The record's alone (C3455's AI3).
            # Masked as the plan card's are (routes/plans_v2.py): each row through the mask.
            from modules.redact import redact_text
            bound = [] if refused else [
                (label, redact_text(words)) for label, words in PE.bound_rows(
                    incident.network, PE.INCIDENT_FIX, held, engine_steps, got_hash)]
    shown = line.get("shown") if isinstance(line.get("shown"), dict) else {}
    # A person's plan keeps what they approve; one that resets a stream's device side with no
    # close of the collector's stale half before it says so (the review of 2026-11-16).
    from modules.fixit.ladder import close_first_note
    note_close = close_first_note(steps)
    found = " ".join(x for x in (str(shown.get("rationale") or line.get("words") or ""),
                                 note_close) if x)
    return {"id": line.get("proposal") or "", "hash": plan_hash, "refused_hash": refused_hash,
            "approvable": not refused and bool(plan_hash), "steps": drawn, "bound": bound,
            # The collector steps' sessions as read when the plan was proposed, each
            # ``{"n", "session", "local", "quiet_s", "dry_run", "refused", "at"}``: the hash
            # binds each session (`plan_params`), and Approve reads it again and refuses,
            # naming both, when it moved since.
            "sessions": sessions,
            "found": found,
            "why_refused": refused, "source": SOURCE_WORDS.get(line.get("source"), ""),
            "by": line.get("by") or "", "at": line.get("at") or "",
            "calls": list(line.get("calls") or []), "note": line.get("note") or "",
            # What the section draws of the AI's checked answer (its rationale, hypotheses,
            # what was cut to fit), and the prompt it came from, as kept with the line.
            "shown": shown, "prompt": line.get("prompt") or ""}


#: The catalog's parameter names in an attempt's words (`section.short_words` reads these).
AS_ATTEMPT_NAME = {"subscriptions": "subs", "subscription": "sub"}
