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
AS_CATALOG = {"subs": "subscriptions", "sub": "subscription"}
#: Why a repeat is refused, the attempt it repeats named.
REPEAT_WORDS = ("it already failed on this incident as attempt {attempt} ({words}), so it is "
                "not offered again; it stays in Attempts and under Other actions")


def as_catalog(operation: str, params: dict, device: str) -> dict:
    """An attempt-form proposal's parameters (`incident.canonical`) as the catalog takes them
    (`catalog.checked`): the incident's *device*, each parameter by the catalog's name, the
    collector flag (an attempt's, never the catalog's) left out."""
    from modules.heal import resubscribe as R

    out = {"device": device}
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
    "proposal", "steps"}``."""
    return {"incident": incident.id, "proposal": line.get("proposal") or "",
            "steps": steps_of(line, incident.device)}


def _check_one(incident, operation: str, params: dict, *, resolved=None, now=None,
               sources=None, planned=None) -> dict:
    """One step's preflight: ``{"ok", "hash", "drawn", "refused", "code", "repeat"}``."""
    from modules.fixit import validate as V

    got = V.check(incident, operation, params, resolved=resolved, now=now, sources=sources,
                  planned=planned)
    if not got["ok"]:
        return {"ok": False, "hash": "", "drawn": {}, "refused": got["refused"],
                "code": got["code"], "repeat": {}}
    rep = got.get("repeat") or {}
    if rep.get("kind") == "repeat":
        from modules.fixit.section import outcome_words

        return {"ok": False, "hash": got["hash"], "drawn": got["preview"], "code": "repeat",
                "refused": REPEAT_WORDS.format(
                    attempt=rep.get("attempt"),
                    words=outcome_words(rep.get("outcome") or "", rep.get("words") or "")
                    or "it did not pass"), "repeat": rep}
    return {"ok": True, "hash": got["hash"], "drawn": got["preview"], "refused": "",
            "code": "", "repeat": rep}


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
    only when every step would run. ``None`` for a line that
    proposed nothing. *sources* and *planned* are the check's seams (tests)."""
    from modules import plan_engine as PE
    from modules.fixit.handover import params_words
    from modules.fixit.section import SOURCE_WORDS, short_words

    steps = steps_of(line, incident.device)
    if not steps:
        return None
    at = time.time() if now is None else float(now)
    drawn, refused = [], ""
    for n, s in enumerate(steps, 1):
        got = _check_one(incident, s["operation"], s["params"], resolved=resolved, now=at,
                         sources=sources, planned=planned)
        attempt = {AS_ATTEMPT_NAME.get(k, k): v for k, v in s["params"].items()
                   if k != "device"}
        rep = got.get("repeat") or {}
        drawn.append({"n": n, "operation": s["operation"],
                      "words": short_words(s["operation"], incident.device, attempt),
                      "params": params_words(attempt), "hash": got["hash"],
                      "preflight": {"ok": got["ok"], "refused": got["refused"],
                                    "code": got["code"]},
                      # A step refused as a repeat: the parameter hash it was compared by and
                      # the attempt it matched, for The record (never the section's words).
                      "repeat": ({"attempt": rep.get("attempt"),
                                  "params_hash": rep.get("params_hash") or ""}
                                 if got["code"] == "repeat" else {})})
        if not got["ok"] and not refused:
            refused = f"Step {n} would be refused: {got['refused']}"
    plan_hash, refused_hash = "", ""
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
            got_hash = PE.plan_hash(PE.INCIDENT_FIX, held, engine_steps, incident.network)
            plan_hash, refused_hash = ("", got_hash) if refused else (got_hash, "")
    shown = line.get("shown") if isinstance(line.get("shown"), dict) else {}
    return {"id": line.get("proposal") or "", "hash": plan_hash, "refused_hash": refused_hash,
            "approvable": not refused and bool(plan_hash), "steps": drawn,
            "found": str(shown.get("rationale") or line.get("words") or ""),
            "why_refused": refused, "source": SOURCE_WORDS.get(line.get("source"), ""),
            "by": line.get("by") or "", "at": line.get("at") or "",
            "calls": list(line.get("calls") or []), "note": line.get("note") or "",
            # What the section draws of the AI's checked answer (its rationale, hypotheses,
            # what was cut to fit), and the prompt it came from, as kept with the line.
            "shown": shown, "prompt": line.get("prompt") or ""}


#: The catalog's parameter names in an attempt's words (`section.short_words` reads these).
AS_ATTEMPT_NAME = {"subscriptions": "subs", "subscription": "sub"}
