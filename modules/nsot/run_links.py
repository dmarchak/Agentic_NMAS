"""Which operations' runs are an incident's: its runs read from the runners' own records, never
from the AI's (moved out of `modules/fixit/incident.py`, the operator's ruling of 2026-11-23 on
test_heal_analysis_never_read: "fix the code", so the heal loop's verified-fix read takes a fact
whose owner is the runner, never the fix-it record; docs/HEAL_TO_INTENT.md section 12).

A run is an incident's when its record names the incident (`RUN_FIELD`, set by the confirm
pressed on the incident's page), or, naming none, when it is a catalogue operation on the
incident's device started inside the incident's window (before any cut of the device's name).
A plan engine run of an incident's fix is read as each of its admitted steps (`plan_step_runs`).
`fixit.incident.attempts` builds the attempts from these; `heal.detect.verified_fix` reads the
newest one. A read of the records; it writes nothing.
"""

import calendar
import logging
import re
import time

from modules.heal import catalog as _catalog

log = logging.getLogger(__name__)

#: The run record's field naming the incident a run was pressed on.
RUN_FIELD = "fixit"
#: The state an operation writes when its verify passed, and the one a refused run is kept in.
PASSED_STATE, REFUSED_STATE = "done", "refused"
#: The catalogue's operations and command plans, an attempt's operations.
CATALOGUE_KEYS = tuple(_catalog.CATALOG) + tuple(_catalog.COMMAND_PLANS)
#: Marks a run read from a step of an incident's plan (`plan_step_runs`), never a record's.
PLAN_STEP = "_plan_step"
#: A plan step's states that ran (its own apply was reached), and the one that passed.
PLAN_STEP_RAN = ("done", "failed")
#: The newest run records read for an incident's runs.
RUNS_READ = 500
_RUN_NAME = re.compile(r"([0-9]{8}T[0-9]{6})([0-9]{6})Z-[0-9a-f]{32}")


def _iso_epoch(iso):
    """An ISO instant's epoch seconds, or None."""
    try:
        return float(calendar.timegm(time.strptime(str(iso or "")[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, OverflowError):
        return None


def epoch(value):
    """*value* as epoch seconds, or None for what is no time (a run record's own times)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def detected_of(inc: dict, entry: dict = None) -> float:
    """When a heal incident *inc* was detected, epoch seconds: its first trigger's, else its
    opening's, else its Needs attention *entry*'s first sighting; 0 when none is kept."""
    trig = [t for t in (inc or {}).get("triggers") or [] if isinstance(t, dict)]
    try:
        detected = float((trig[0] if trig else {}).get("epoch") or 0)
    except (TypeError, ValueError):
        detected = 0.0
    return (detected or _iso_epoch((inc or {}).get("opened_at"))
            or _iso_epoch((entry or {}).get("first_at")) or 0)


def stamp(name: str):
    """The start a run's id (or its file's name) states, epoch seconds, or None."""
    m = _RUN_NAME.match(str(name or ""))
    if not m:
        return None
    try:
        return calendar.timegm(time.strptime(m.group(1), "%Y%m%dT%H%M%S")) + int(m.group(2)) / 1e6
    except ValueError:
        return None


def named(run: dict) -> tuple:
    """``(incident id, proposal id)`` *run*'s record names (`RUN_FIELD`), each ``""`` when it
    names none."""
    link = run.get(RUN_FIELD)
    if not isinstance(link, dict) or not isinstance(link.get("incident"), str):
        return "", ""
    proposal = link.get("proposal")
    return link["incident"], proposal if isinstance(proposal, str) else ""


def passed(run: dict) -> bool:
    """Whether *run*'s own record says its fix worked: the state its operation writes when
    its verify passed (`PASSED_STATE`). A run that sent nothing is never one: a command plan's
    run whose precondition said there was nothing to do is recorded ``done`` with outcome
    ``not_needed`` (`command_plan_run.RECORD_STATE`), its verify never run (the correctness
    review's G1-H1, 2026-11-18)."""
    from modules.nsot.command_plan_run import NOT_NEEDED

    return run.get("state") == PASSED_STATE and run.get("outcome") != NOT_NEEDED


def cut_of(network: str, device: str, detected: float):
    """The moment *device*'s name passed to another device after *detected*
    (`retire.name_cuts`: a retirement, an abandoned onboarding, a new device's Create), or
    None: a run keyed by the name after it is never this incident's device's."""
    from modules.nsot import retire

    cut = retire.name_cuts(network).get((device or "").lower())
    return cut if cut and cut.get("epoch", 0) > detected else None


def plan_step_runs(run: dict, incident_id: str) -> list:
    """Each step of *run* (a plan engine run record, `plan_engine.KEY`, of an incident's fix)
    that is a step kind the fix admits beside the catalogue (`plan_engine.FIX_ADMITTED`), names
    *incident_id* and ran, as a run of its own the attempts read: its kind as the operation, the
    values its kind compares an attempt by (`StepKind.attempt_of`, from its parameters and what
    its preview resolved), its state ``done`` only when it passed, and the plan run's id, actor
    and times. ``[]`` for any other record."""
    from modules import plan_engine as PE

    if run.get("key") != PE.KEY or run.get("plan") != PE.INCIDENT_FIX:
        return []
    out = []
    for st in run.get("plan_steps") or []:
        p = st.get("params") if isinstance(st, dict) else None
        if (not isinstance(p, dict) or st.get("kind") not in PE.FIX_ADMITTED
                or p.get("incident") != incident_id or st.get("state") not in PLAN_STEP_RAN):
            continue
        kind = PE.STEP_KINDS[st["kind"]]
        out.append({PLAN_STEP: True, "key": st["kind"], "id": run.get("id"),
                    "device": p.get("device") or "", "started_at": run.get("started_at"),
                    "finished_at": run.get("finished_at"), "actor": run.get("actor"),
                    "actor_verified": run.get("actor_verified"),
                    "outcome": st.get("outcome") or "",
                    "state": PASSED_STATE if st.get("state") == "done" else "failed",
                    "why": st.get("words_said") or "",
                    "params": kind.attempt_of(p, st.get("resolved") or {}),
                    RUN_FIELD: {"incident": incident_id,
                                "proposal": str(p.get("proposal") or "")}})
    return out


def linked_runs(network: str, incident_id: str, device: str, detected: float, end: float, *,
                limit: int = RUNS_READ) -> dict:
    """The runs of incident *incident_id* (on *device*, detected at *detected*, its window
    ending at *end*), from the newest *limit* run records: ``{"runs", "refused", "unreadable",
    "truncated", "cut"}``. *runs* are ``(started, run id, linked, proposal, record)`` in start
    order, refused runs left out (counted in *refused*); *linked* is ``record`` (its record
    names the incident) or ``window`` (a catalogue operation on the device inside the window,
    before the name's *cut*). *unreadable* names the records inside the window that could not
    be read; *truncated* says the oldest record read is still inside it."""
    from modules.config import list_data_path
    from modules.nsot import privileged

    got = privileged.runs(network, limit=limit, data_dir=list_data_path(network))
    runs = [r for r in got["runs"] if isinstance(r, dict)]
    oldest = stamp(runs[-1].get("id")) if runs else None
    truncated = len(got["runs"]) >= limit and (oldest is None or oldest >= detected)
    bad = [n for n in got["unreadable"] if stamp(n) is None or detected <= stamp(n) <= end]
    found = []
    for r in [s for run in runs for s in plan_step_runs(run, incident_id)] + runs:
        if (r.get("key") not in CATALOGUE_KEYS and not r.get(PLAN_STEP)
                and not _catalog.is_command_plan(r.get("key"))):
            continue
        name, proposal = named(r)
        if name and name != incident_id:
            continue
        if not name and (not device or r.get("device") != device):
            continue
        started = epoch(r.get("started_at"))
        if started is None:
            bad.append(str(r.get("id") or "a run with no id"))
            continue
        if not name and not detected <= started <= end:
            continue
        found.append((started, str(r.get("id") or ""), "record" if name else "window",
                      proposal, r))
    cut = cut_of(network, device, detected) if any(f[2] == "window" for f in found) else None
    if cut:
        found = [f for f in found if f[2] == "record" or f[0] <= cut["epoch"]]
    refused = sum(1 for f in found if f[4].get("state") == REFUSED_STATE)
    kept = sorted((f for f in found if f[4].get("state") != REFUSED_STATE), key=lambda f: f[:2])
    return {"runs": kept, "refused": refused, "unreadable": sorted(bad), "truncated": truncated,
            "cut": cut}
