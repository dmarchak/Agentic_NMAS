"""An incident's record for AI troubleshooting, its attempts and what is derived from them
(board recurring-fixes v2: the STOP, Cancel, Hand over, the repeat flag, the per-incident cost;
the incident page board, parts C and H: the list's "cancelled" state and "how fixed").
Deterministic: no AI call, no device, nothing drawn, and nothing here starts anything.

**The incident is named, never minted or resolved here.** Its id is the id its own store gave
it (`valid_id`: a self-healing incident's ``hi-`` and hex, an SDN response's ``resp-`` and hex,
an alert group's ``al-`` and the token the incident index mints), checked by shape only and
used as this record's key. Whoever asks hands in the incident as its own store reads it
(`Incident`): its network, its id, its device and when it was detected. **The device is carried
by its stable identity with its name as a label** (the manifest's key, `manifest.identity_for`:
``nb:<NetBox id>``, or ``uid:<…>`` for a device of a local inventory, which no NetBox holds),
never by a name alone; an incident that names no device carries neither.

**The record stores only what nothing else owns**, one JSON document per incident under its
network's data folder (``fixit/<incident id>.json``), its ``lines`` append-only and of two
kinds only:

- a **proposal** line: ``{"proposal": <id>, "source": "mercury"|"ai"|"person", "calls": [the
  AI calls it came from], "prompt", "operation", "params_hash", "at", "epoch"}``. An answer that
  proposed no operation (a gap, an answer that could not be checked) is a proposal line with
  an empty operation, so the calls it cost are still this incident's;
- a **choice** line, a person's: ``{"choice": "cancel"|"handover"|"save", "by", "verified",
  "at", "epoch", "attempts", "ai_usd"}``, the attempt count and the AI sum as they were at
  that moment; a hand-over carries its ``version`` and the ``teams`` told, a save what was
  ``saved``. What a hand-over says is the hand-over builder's, never kept here.

Nothing a list or a page can derive is written: the words "cancelled" and "AI-assisted", an
attempt, an outcome and a cost are never stored. The header names the incident, its network and
the device it named at the record's first line (identity and label); the incident's own store
stays the owner of its device, and no derivation reads the header's.

**The store** (CLAUDE.md, "Several people, tabs and worker processes are assumed"): every write
is a read-modify-write under the document's lock across processes (`filestore.PathLock`),
replaced atomically, owner-only (`filestore.write_atomic`); a document that exists and cannot
be read, or is not this incident's record, refuses every write and is preserved
(`filestore.StoreUnreadable`), never replaced by an empty one. A read creates neither the
folder nor the file, and says ``absent`` and ``unreadable`` apart. Every line is masked at
rest (`redact.redact_payload`, which is `redact_text` over every text in it). A write creates
no network.

**Attempts are DERIVED, never copied** (`attempts`): an attempt is a catalogue operation's run
on the incident's device whose start falls inside the incident (from when it was detected to
its resolution, or now), read from the operation's own run record (`privileged.runs`) each
time, in the order they started, each with the run's own id, operation, actor and how they
were verified, outcome and words. The outcome has one owner, the operation, and a run made
before this record existed is an attempt with no backfill. A run whose record NAMES an incident
(`RUN_FIELD`: the incident's id, the attempt number and the proposal's id, which the
operation's confirm carries from the incident's page) is that incident's attempt and no
other's, whatever its time or device: the record's word is honoured over the window. A refused
run sent nothing and is no attempt. Runs are keyed by the device's name, so a run made after
the name passed to another device (`retire.name_cuts`: its retirement, or a new device's
Create) is never an earlier device's incident's attempt.

**Nothing here retries, and Cancel runs nothing** (the operator, 2026-11-11: "FAIL: STOP. Never
retry on its own"; "Cancel: nothing more runs, the incident stays open, attempts recorded").
`cancel` appends one line and calls nothing else; no function of this package reaches an
operation's apply, a device hold, the job starter, a session or the AI gateway, and only the
hand-over's send (`handover.send`, and `handover.hand_over` through it) reaches the
notification relay (tests/test_fixit_incident.py, by parsing).

**What is derived:** `cost_so_far` (the incident's AI calls summed from the record of AI calls
by their ids each time; an unreadable record said, never guessed); `repeat_of` (a proposal
that already failed in this incident is a ``repeat``, the same operation with other parameters
a ``variation`` naming each, anything else ``new``); `state_of` (``cancelled`` while the
incident is not resolved, its newest choice is a cancel, and nothing was proposed or run after
it); `how_fixed_source` (the source of the proposal the resolving attempt's run names: ``ai``
only then).
"""

import calendar
import datetime
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass

from modules.heal import catalog as _catalog
from modules.heal.resubscribe import KEY as RESUBSCRIBE_KEY
from modules.heal.resubscribe import READD_KEY, header

log = logging.getLogger(__name__)

STORE_DIR = "fixit"
VERSION = 1

#: The operations whose runs are an incident's attempts: the catalog's own keys
#: (`modules/heal/catalog.py`), the telemetry re-subscribe and its one-step re-add, each the
#: key its module records a run under.
CATALOGUE_KEYS = tuple(_catalog.CATALOG)

#: Each catalogue operation's parameters as an attempt is compared by, and their kinds:
#: ``set`` (its members, in no order), ``flag`` (true or false; absent is false) and ``one``
#: (one value). Not the catalog's schema: an attempt is read from its run's record, which
#: names no device here (the incident does, `NOT_PARAMETERS`) and will say whether the
#: collector step ran (C3108), a step no proposal may name until the operation takes it. A
#: proposal's parameters reach this form by `modules/fixit/validate.py`'s `as_attempt`;
#: tests/test_fixit_catalogue.py holds the two tables to the same operations.
PARAMETERS = {RESUBSCRIBE_KEY: (("subs", "set"), ("collector_step", "flag")),
              READD_KEY: (("sub", "one"),)}
#: Given with a proposal and no parameter of it: the incident names the device, and the reason
#: is the person's words, so a changed reason is the same fix proposed again.
NOT_PARAMETERS = ("device", "reason")

#: Who a proposal came from: Mercury's own diagnosis, a model's answer, or a person's choice.
SOURCES = ("mercury", "ai", "person")
CHOICES = ("cancel", "handover", "save")
#: What the save choice can be: apply alone next time, propose next time, or do not save.
SAVE_CHOICES = ("apply_alone", "propose", "dont_save")

#: The field of an operation's run record that names its incident: ``{"incident", "attempt",
#: "proposal"}`` (`run_link`).
RUN_FIELD = "fixit"
#: The record state the operations write for a run whose own verify passed
#: (`resubscribe.RECORD_STATE`, `privileged.runs`), and for one that sent nothing.
PASSED_STATE, REFUSED_STATE = "done", "refused"
#: The newest run records read for one derivation (`privileged.runs`' limit). Reaching it with
#: the oldest one read still inside the incident is said as truncated, never read as all.
RUNS_READ = 500

_ID = re.compile(r"(?:hi-[0-9a-f]{6,40}|resp-[0-9a-f]{6,40}|al-[a-z0-9][a-z0-9-]{0,63})")
_DEVICE_ID = re.compile(r"(?:nb:[0-9]{1,18}|uid:[0-9A-Za-z-]{1,64})")
_CALL_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SUBSCRIPTION = re.compile(r"[0-9]{1,10}")
_RUN_NAME = re.compile(r"([0-9]{8}T[0-9]{6})([0-9]{6})Z-[0-9a-f]{32}")


class Refused(ValueError):
    """Nothing was written; the words say why."""


class NotAPerson(Refused):
    """A choice is a verified person's, and this request is not one."""


@dataclass(frozen=True)
class Incident:
    """An incident as its own store reads it: *id* (that store's, `valid_id`), *network*, the
    device by its stable identity (*device_id*: ``nb:<NetBox id>``, else ``uid:<…>``) with its
    name as a label (*device*), and when it was *detected* (epoch seconds). An incident that
    names no device carries neither identity nor name. *subscriptions* are the telemetry
    subscriptions its triggers name, by id (a lost stream's; `diagnose_stream.stream_of`), and
    none for an incident of another kind: what a proposal in it may act on
    (`modules/fixit/validate.py`)."""

    network: str
    id: str
    device_id: str
    device: str
    detected: float
    subscriptions: tuple = ()


def valid_id(text) -> bool:
    """Whether *text* has the shape of an incident's id: ``hi-`` or ``resp-`` and hex, or
    ``al-`` and a bounded token of lower-case letters, digits and hyphens. By shape only: no
    store is asked whether it holds one."""
    return isinstance(text, str) and _ID.fullmatch(text) is not None


def _check(incident) -> None:
    if not isinstance(incident, Incident):
        raise Refused("an incident is handed in as an Incident (its network, id, device and "
                      f"detected time), and a {type(incident).__name__} was given")
    if not valid_id(incident.id):
        raise Refused(f"{incident.id!r} is no incident's id: one is hi- or resp- and hex, or "
                      "al- and the token the incident index minted")
    if not isinstance(incident.network, str) or not incident.network.strip():
        raise Refused(f"{incident.id} names no network")
    name, ident = incident.device or "", incident.device_id or ""
    if name and not ident:
        raise Refused(f"{incident.id}'s device was given by its name alone ({name}): a device "
                      "is carried by its identity (nb:<NetBox id>, or uid:<…> for one no "
                      "NetBox holds), its name a label")
    if ident and (not isinstance(ident, str) or not _DEVICE_ID.fullmatch(ident)):
        raise Refused(f"{ident!r} is no device identity: one is nb:<NetBox id> or uid:<…>")
    if ident and not name:
        raise Refused(f"{incident.id}'s device {ident} was given without its name")
    if (isinstance(incident.detected, bool) or not isinstance(incident.detected, (int, float))
            or incident.detected <= 0):
        raise Refused(f"{incident.id} was given no detected time (epoch seconds; "
                      f"{incident.detected!r} given)")
    subs = incident.subscriptions
    if (not isinstance(subs, tuple)
            or not all(isinstance(s, str) and _SUBSCRIPTION.fullmatch(s) for s in subs)):
        raise Refused(f"{incident.id}'s subscriptions are a tuple of subscription ids (text of "
                      f"1 to 10 digits), and {subs!r} was given")
    if subs and not ident:
        raise Refused(f"{incident.id} names subscriptions ({', '.join(subs)}) and no device "
                      "they are on")


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _epoch(value):
    """*value* as epoch seconds, or None for what is no time."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


# ── The store ───────────────────────────────────────────────────────────────────────────────

def path(incident: Incident) -> str:
    """Where *incident*'s record is kept, asked without creating anything."""
    from modules.config import list_data_path

    _check(incident)
    return os.path.join(list_data_path(incident.network), STORE_DIR, f"{incident.id}.json")


def _empty(incident: Incident) -> dict:
    return {"version": VERSION, "incident": incident.id, "network": incident.network,
            "device": {"id": incident.device_id or "", "name": incident.device or ""},
            "lines": []}


def _shape_error(doc, incident: Incident) -> str:
    """Why *doc* is not *incident*'s record as this release writes it, or ``""``."""
    if not isinstance(doc, dict):
        return f"it holds a JSON {type(doc).__name__}, not a record"
    if doc.get("version") != VERSION:
        return f"it is version {doc.get('version')!r}, and this release reads version {VERSION}"
    if doc.get("incident") != incident.id:
        return f"it names the incident {doc.get('incident')!r}, not {incident.id}"
    lines = doc.get("lines")
    if not isinstance(lines, list):
        return "it holds no lines"
    for n, line in enumerate(lines, 1):
        if not isinstance(line, dict) or ("proposal" in line) == ("choice" in line):
            return f"its line {n} is neither a proposal nor a choice"
        if "choice" in line and line["choice"] not in CHOICES:
            return f"its line {n} is a choice this release does not know ({line['choice']!r})"
        if "proposal" in line and line.get("source") not in SOURCES:
            return f"its line {n} is a proposal from no known source ({line.get('source')!r})"
        if _epoch(line.get("epoch")) is None:
            return f"its line {n} holds no time"
    return ""


def _unreadable(incident: Incident, why: str) -> str:
    return (f"{incident.network}'s troubleshooting record of {incident.id} cannot be read "
            f"({why})")


def read(incident: Incident) -> dict:
    """*incident*'s record: ``{"state": "ok"|"absent"|"unreadable", "lines", "error"}``, its
    lines oldest first. A read creates nothing; absent and unreadable are different facts."""
    p = path(incident)
    if not os.path.exists(p):
        return {"state": "absent", "lines": [], "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "lines": [],
                "error": _unreadable(incident, type(exc).__name__)}
    why = _shape_error(doc, incident)
    if why:
        return {"state": "unreadable", "lines": [], "error": _unreadable(incident, why)}
    return {"state": "ok", "lines": list(doc["lines"]), "error": ""}


def _append(incident: Incident, build) -> dict:
    """Append ``build(lines so far)`` to *incident*'s record under its lock, masked, the
    document replaced atomically; the line as stored. A record that cannot be read raises
    `filestore.StoreUnreadable` and is preserved; a network that does not exist is refused."""
    from modules import filestore
    from modules.nsot import listref
    from modules.redact import redact_payload

    p = path(incident)
    if not listref.exists(incident.network):
        raise Refused(f"{incident.network} is no network, so nothing is recorded for "
                      f"{incident.id}")
    with filestore.PathLock(p):
        doc = filestore.read_json_for_write(p, empty=_empty(incident))
        why = _shape_error(doc, incident)
        if why:
            filestore.preserve_corrupt(p, why)
            raise filestore.StoreUnreadable(
                _unreadable(incident, why) + ", so nothing was written: saving would have "
                "replaced what it holds. The file is preserved beside it.")
        line = redact_payload(build(doc["lines"]))
        doc["lines"].append(line)
        filestore.write_atomic(p, json.dumps(doc, indent=1, sort_keys=True))
    return line


# ── A proposal's operation and parameters ───────────────────────────────────────────────────

def _scalar(value, operation: str, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise Refused(f"{operation}'s {name} holds {value!r}, which is no single value")
    return str(value).strip()


def canonical(operation: str, params) -> dict:
    """*params* in *operation*'s canonical form: its declared parameters only (`PARAMETERS`),
    a set's members sorted, a flag true or false, an absent one at its default. A name the
    operation does not declare is refused by name (`NOT_PARAMETERS` aside)."""
    if operation not in PARAMETERS:
        raise Refused(f"{operation!r} is no catalogue operation (the catalogue holds "
                      f"{', '.join(CATALOGUE_KEYS)})")
    given = dict(params or {})
    declared = dict(PARAMETERS[operation])
    unknown = sorted(k for k in given if k not in declared and k not in NOT_PARAMETERS)
    if unknown:
        raise Refused(f"{operation} has no parameter {', '.join(map(repr, unknown))}: its "
                      f"parameters are {', '.join(declared)}")
    out = {}
    for name, kind in PARAMETERS[operation]:
        value = given.get(name)
        if kind == "flag":
            if value is not None and not isinstance(value, bool):
                raise Refused(f"{operation}'s {name} is true or false, and {value!r} was "
                              "given")
            out[name] = bool(value)
        elif kind == "set":
            if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set,
                                                                        frozenset, type(None))):
                raise Refused(f"{operation}'s {name} is a list, and {value!r} was given")
            members = {_scalar(v, operation, name) for v in (value or ())}
            out[name] = sorted(members, key=lambda s: (len(s), s))
        else:
            out[name] = "" if value is None else _scalar(value, operation, name)
    return out


def params_hash(operation: str, params) -> str:
    """The hash a proposal and an attempt are compared by: over *operation* and its canonical
    parameters (`canonical`), 16 hex characters."""
    text = json.dumps({"operation": operation, "params": canonical(operation, params)},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _run_params(run: dict) -> dict:
    """What *run* (a catalogue operation's record) was run with, read from the record itself:
    its subscriptions (each one's own record; before those are kept, the program's
    subscription headers) and, once the collector step exists, its flag."""
    subs = [str(s.get("sub")) for s in run.get("subscriptions") or []
            if isinstance(s, dict) and s.get("sub") not in (None, "")]
    if not subs:
        prefix = header("")
        for line in run.get("program") or []:
            if isinstance(line, str) and line.startswith(prefix):
                sub = line[len(prefix):].strip()
                if sub and sub not in subs:
                    subs.append(sub)
    if run.get("key") == READD_KEY:
        return canonical(READD_KEY, {"sub": subs[0] if subs else ""})
    return canonical(RESUBSCRIBE_KEY, {"subs": subs,
                                       "collector_step": run.get("collector_step") is True})


def record_proposal(incident: Incident, source: str, operation: str = "", params=None, *,
                    calls=(), prompt: str = "", now: float = None) -> dict:
    """Record one proposal made in *incident*, the line as stored (its ``proposal`` the id an
    operation's confirm carries into its run record, `run_link`). *source* is one of
    `SOURCES`; *operation* a catalogue operation's key with its *params* (kept as their hash,
    `params_hash`), or empty with none for an answer that proposed nothing; *calls* the ids of
    the AI calls it came from (an ``ai`` proposal names at least one), and *prompt* the
    prompt's name and version. It starts nothing."""
    _check(incident)
    if source not in SOURCES:
        raise Refused(f"a proposal comes from one of {', '.join(SOURCES)}, and {source!r} was "
                      "given")
    if isinstance(calls, (str, bytes)):
        raise Refused(f"a proposal's calls are a list of ids, and {calls!r} was given")
    ids = []
    for c in calls or ():
        if not isinstance(c, str) or not _CALL_ID.fullmatch(c):
            raise Refused(f"{c!r} is no AI call's id")
        if c not in ids:
            ids.append(c)
    if source == "ai" and not ids:
        raise Refused("an AI proposal names the call it came from, and none was given: its "
                      "cost and \"how fixed\" are read from that call")
    if operation:
        hashed = params_hash(operation, params)
    elif params:
        raise Refused("parameters were given with no operation")
    else:
        hashed = ""
    at = time.time() if now is None else float(now)

    def build(lines):
        n = sum(1 for line in lines if "proposal" in line) + 1
        return {"proposal": f"p{n}", "source": source, "calls": ids, "prompt": str(prompt or ""),
                "operation": operation or "", "params_hash": hashed, "at": _iso(at),
                "epoch": at}

    line = _append(incident, build)
    log.info("fixit: %s: proposal %s recorded (%s, %s)", incident.id, line["proposal"], source,
             operation or "no operation")
    return line


# ── The attempts, derived ───────────────────────────────────────────────────────────────────

def passed(run: dict) -> bool:
    """Whether *run*'s own record says its fix worked: the state its operation writes when
    its verify passed (`PASSED_STATE`). The one place a later verdict (the symptom cleared, no
    harm) joins."""
    return run.get("state") == PASSED_STATE


def _stamp(name: str):
    """The start a run's id (or its file's name) states, epoch seconds, or None."""
    m = _RUN_NAME.match(str(name or ""))
    if not m:
        return None
    try:
        return calendar.timegm(time.strptime(m.group(1), "%Y%m%dT%H%M%S")) + int(m.group(2)) / 1e6
    except ValueError:
        return None


def _named(run: dict) -> tuple:
    """``(incident id, proposal id)`` *run*'s record names (`RUN_FIELD`), each ``""`` when it
    names none."""
    link = run.get(RUN_FIELD)
    if not isinstance(link, dict) or not isinstance(link.get("incident"), str):
        return "", ""
    proposal = link.get("proposal")
    return link["incident"], proposal if isinstance(proposal, str) else ""


def _cut(incident: Incident):
    """The moment *incident*'s device name passed to another device after the incident was
    detected (`retire.name_cuts`: a retirement, an abandoned onboarding, a new device's
    Create), or None: a run keyed by the name after it is never this incident's device's."""
    from modules.nsot import retire

    cut = retire.name_cuts(incident.network).get((incident.device or "").lower())
    return cut if cut and cut.get("epoch", 0) > incident.detected else None


def attempts(incident: Incident, resolved: float = None, *, now: float = None,
             limit: int = RUNS_READ) -> dict:
    """*incident*'s attempts, derived from the operations' own run records each time:
    ``{"state": "ok"|"incomplete", "attempts", "refused", "unreadable", "truncated", "cut",
    "error"}``. *resolved* is when the incident resolved (epoch seconds; None while it is
    open, and the window then ends at *now*).

    Each attempt, oldest first: ``{"n", "run", "operation", "device", "started_at",
    "finished_at", "at", "actor", "actor_verified", "outcome", "state", "passed", "words",
    "params", "params_hash", "proposal", "source", "linked"}``, everything but ``n`` and
    ``linked`` read from the run's record (``source`` from the proposal it names, ``""`` when
    it names none this record holds). ``linked`` says how the run is this incident's:
    ``record`` (its record names the incident) or ``window`` (a catalogue operation on the
    incident's device, started inside it).

    ``incomplete`` when something an attempt could be in was not read: a run record that
    cannot be read or has no start time (``unreadable``, by name), more runs than *limit*
    (``truncated``), or this incident's own record. ``refused`` counts the refused runs left
    out; ``cut`` is the name cut applied, if one was."""
    from modules.config import list_data_path
    from modules.nsot import privileged

    _check(incident)
    end = (float(resolved) if resolved is not None
           else time.time() if now is None else float(now))
    rec = read(incident)
    sources = {line["proposal"]: line["source"] for line in rec["lines"] if "proposal" in line}
    got = privileged.runs(incident.network, limit=limit,
                          data_dir=list_data_path(incident.network))
    runs = [r for r in got["runs"] if isinstance(r, dict)]
    oldest = _stamp(runs[-1].get("id")) if runs else None
    truncated = len(got["runs"]) >= limit and (oldest is None or oldest >= incident.detected)
    bad = [n for n in got["unreadable"]
           if _stamp(n) is None or incident.detected <= _stamp(n) <= end]
    found = []
    for r in runs:
        if r.get("key") not in CATALOGUE_KEYS:
            continue
        named, proposal = _named(r)
        if named and named != incident.id:
            continue
        if not named and (not incident.device or r.get("device") != incident.device):
            continue
        started = _epoch(r.get("started_at"))
        if started is None:
            bad.append(str(r.get("id") or "a run with no id"))
            continue
        if not named and not incident.detected <= started <= end:
            continue
        found.append((started, str(r.get("id") or ""), "record" if named else "window",
                      proposal, r))
    cut = _cut(incident) if any(f[2] == "window" for f in found) else None
    if cut:
        found = [f for f in found if f[2] == "record" or f[0] <= cut["epoch"]]
    refused = sum(1 for f in found if f[4].get("state") == REFUSED_STATE)
    out = []
    for started, run_id, linked, proposal, r in sorted(
            (f for f in found if f[4].get("state") != REFUSED_STATE), key=lambda f: f[:2]):
        params = _run_params(r)
        out.append({"n": len(out) + 1, "run": run_id, "operation": r["key"],
                    "device": r.get("device") or "", "started_at": started,
                    "finished_at": _epoch(r.get("finished_at")), "at": _iso(started),
                    "actor": r.get("actor") or "",
                    "actor_verified": r.get("actor_verified") or "none",
                    "outcome": r.get("outcome") or "", "state": r.get("state") or "",
                    "passed": passed(r), "words": r.get("why") or "", "params": params,
                    "params_hash": params_hash(r["key"], params), "proposal": proposal,
                    "source": sources.get(proposal, "") if proposal else "",
                    "linked": linked})
    why = []
    if rec["state"] == "unreadable":
        why.append(rec["error"])
    if bad:
        why.append(f"{len(bad)} run record(s) of {incident.network} could not be read "
                   f"({', '.join(sorted(bad)[:5])}{', …' if len(bad) > 5 else ''})")
    if truncated:
        why.append(f"{incident.network} holds more than the {limit} newest run records read, "
                   f"and the oldest read is still inside {incident.id}")
    return {"state": "incomplete" if why else "ok", "attempts": out, "refused": refused,
            "unreadable": sorted(bad), "truncated": truncated, "cut": cut,
            "error": "; ".join(why)}


def run_link(incident: Incident, proposal: str = "") -> dict:
    """What an operation's confirm carries into its run record under `RUN_FIELD` when it is
    pressed on *incident*'s page: the incident's id, the attempt's number (one more than the
    attempts so far) and the *proposal* it runs, ``""`` for a fix chosen with no proposal. A
    proposal this record does not hold is refused. A read; it starts nothing."""
    _check(incident)
    if proposal:
        rec = read(incident)
        if rec["state"] == "unreadable":
            raise Refused(rec["error"])
        if proposal not in [line.get("proposal") for line in rec["lines"]]:
            raise Refused(f"{incident.id}'s record holds no proposal {proposal!r}")
    return {"incident": incident.id, "attempt": len(attempts(incident)["attempts"]) + 1,
            "proposal": proposal or ""}


def repeat_of(incident: Incident, op: str, params, resolved: float = None, *,
              now: float = None) -> dict:
    """Whether proposing *op* with *params* repeats what already failed in *incident*:
    ``{"kind": "repeat"|"variation"|"new", "attempt", "run", "outcome", "words", "at",
    "params_hash", "changed", "complete", "error"}``.

    Against every attempt that did not pass (`passed`), newest first: ``repeat`` when one ran
    the same operation with the same canonical parameters (its number, run, outcome and the
    run's own words); else ``variation`` when one ran the same operation, naming each changed
    parameter (``changed``: ``{"name", "before", "after"}``) against the newest such; else
    ``new``. A reason is no parameter. ``complete`` is false, with why, when an attempt could
    be among what was not read (`attempts`): the answer is then of what was read."""
    hashed = params_hash(op, params)
    mine = canonical(op, params)
    got = attempts(incident, resolved, now=now)
    failed = [a for a in reversed(got["attempts"]) if a["operation"] == op and not a["passed"]]
    same = next((a for a in failed if a["params_hash"] == hashed), None)
    hit = same or (failed[0] if failed else None)
    out = {"kind": "repeat" if same else "variation" if hit else "new", "attempt": None,
           "run": "", "outcome": "", "words": "", "at": "", "params_hash": hashed,
           "changed": [], "complete": got["state"] == "ok", "error": got["error"]}
    if hit:
        out.update(attempt=hit["n"], run=hit["run"], outcome=hit["outcome"],
                   words=hit["words"],
                   at=_iso(hit["finished_at"] if hit["finished_at"] is not None
                           else hit["started_at"]))
    if hit and not same:
        out["changed"] = [{"name": name, "before": hit["params"].get(name), "after": mine[name]}
                          for name, _kind in PARAMETERS[op]
                          if hit["params"].get(name) != mine[name]]
    return out


# ── The cost, summed ────────────────────────────────────────────────────────────────────────

def calls_of(incident: Incident) -> dict:
    """*incident*'s AI calls, each read from the record of AI calls by the ids its proposals
    name, each time: ``{"state": "ok"|"partial"|"unreadable", "calls", "missing", "error"}``,
    *calls* in the order the record first names them, each ``{"id", "usd", "joined"}``
    (``joined``: a call that joined another's and cost nothing of its own). Read within the
    incident (`calls.rows_since` from when it was detected), never the whole record; no
    proposal naming a call reads nothing. ``unreadable`` (this record or the calls') holds no
    calls, never none in their place; ``partial`` when the calls' record holds no row for an
    id named (``missing``)."""
    _check(incident)
    rec = read(incident)
    if rec["state"] == "unreadable":
        return {"state": "unreadable", "calls": [], "missing": [], "error": rec["error"]}
    ids = []
    for line in rec["lines"]:
        for c in (line.get("calls") or []) if "proposal" in line else []:
            if c not in ids:
                ids.append(c)
    if not ids:
        return {"state": "ok", "calls": [], "missing": [], "error": ""}
    from modules.ai import calls

    got = calls.rows_since(datetime.datetime.fromtimestamp(incident.detected,
                                                           datetime.timezone.utc))
    if got["state"] == "unreadable":
        return {"state": "unreadable", "calls": [], "missing": [],
                "error": (f"the record of AI calls could not be read ({got['error']}), so what "
                          f"{incident.id}'s {len(ids)} call(s) cost is not known")}
    rows = {r.get("id"): r for r in got["rows"]}
    missing = [c for c in ids if c not in rows]
    return {"state": "partial" if missing else "ok",
            "calls": [{"id": c, "usd": float(rows[c].get("cost_usd") or 0),
                       "joined": rows[c].get("verdict") == calls.JOINED}
                      for c in ids if c in rows],
            "missing": missing,
            "error": (f"the record of AI calls holds no row for {len(missing)} of the "
                      f"{len(ids)} call(s) {incident.id} names ({', '.join(missing[:5])}"
                      f"{', …' if len(missing) > 5 else ''}): the sum is of the rest"
                      if missing else "")}


def cost_so_far(incident: Incident) -> dict:
    """What *incident*'s AI calls cost (`calls_of`), summed each time: ``{"state":
    "ok"|"partial"|"unreadable", "usd", "calls", "missing", "error"}``. ``unreadable`` has no
    sum, never 0; ``partial`` the sum of the calls the record holds; no proposal naming a call
    is 0 with nothing read."""
    got = calls_of(incident)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "usd": None, "calls": 0, "missing": [],
                "error": got["error"]}
    return {"state": got["state"], "usd": sum((c["usd"] for c in got["calls"]), 0.0),
            "calls": sum(1 for c in got["calls"] if not c["joined"]),
            "missing": got["missing"], "error": got["error"]}


# ── A person's choices ──────────────────────────────────────────────────────────────────────

def _person(actor: str, actor_verified: str, what: str) -> None:
    if (not actor or not isinstance(actor_verified, str)
            or actor_verified in ("", "none")):
        raise NotAPerson(f"{what} is recorded for a verified person, and this request is not "
                         f"one: its actor is {actor or 'none'} and its verification is "
                         f"{actor_verified or 'none'}, and a verification of \"\" or \"none\" "
                         "is no person's. Nothing was recorded")


def _choice(incident: Incident, choice: str, actor: str, actor_verified: str, now: float,
            more=None) -> dict:
    """Append one choice line, with the attempt count and the AI sum as they are now (reads
    only: the operations' run records and the record of AI calls)."""
    at = time.time() if now is None else float(now)
    tried, cost = attempts(incident, now=at), cost_so_far(incident)
    base = {"choice": choice, "by": actor, "verified": actor_verified, "at": _iso(at),
            "epoch": at, "attempts": len(tried["attempts"]), "ai_usd": cost["usd"]}
    if tried["state"] != "ok":
        base["attempts_unread"] = tried["error"]
    if cost["state"] != "ok":
        base["ai_unread"] = cost["error"]

    def build(lines):
        return dict(base, **(more(lines) if more else {}))

    line = _append(incident, build)
    log.info("fixit: %s: %s recorded for %s", incident.id, choice, actor)
    return line


def cancel(incident: Incident, actor: str, actor_verified: str, *, now: float = None) -> dict:
    """Record that *actor*, a person verified as *actor_verified*, cancelled troubleshooting
    in *incident*: ONE line appended, the line as stored. It calls nothing else: no AI call,
    no device hold, no job, no notification; the incident stays open and its attempts stay
    where they are, in the operations' own records. An unverified request is refused, naming
    what was compared, with nothing recorded."""
    _check(incident)
    _person(actor, actor_verified, "a cancel")
    return _choice(incident, "cancel", actor, actor_verified, now)


def record_handover(incident: Incident, actor: str, actor_verified: str, *, teams=(),
                    now: float = None) -> dict:
    """Record that *actor* handed *incident* over: one choice line with the next ``version``
    (each hand-over is a new one, none overwritten) and the *teams* told, by name. The line
    only: the write-up and its sending are the hand-over builder's. It sends nothing."""
    _check(incident)
    _person(actor, actor_verified, "a hand-over")
    if isinstance(teams, (str, bytes)):
        raise Refused(f"the teams told are a list of names, and {teams!r} was given")
    names = []
    for t in teams or ():
        if not isinstance(t, str) or not t.strip():
            raise Refused(f"{t!r} is no team's name")
        names.append(t.strip())

    def more(lines):
        return {"version": sum(1 for line in lines if line.get("choice") == "handover") + 1,
                "teams": names}

    return _choice(incident, "handover", actor, actor_verified, now, more)


def record_save(incident: Incident, choice: str, actor: str, actor_verified: str, *,
                now: float = None) -> dict:
    """Record *actor*'s choice about adding the fix to self-healing, one of `SAVE_CHOICES`:
    one choice line (``saved``). The choice only: it changes no policy and saves no fix."""
    _check(incident)
    _person(actor, actor_verified, "a save choice")
    if choice not in SAVE_CHOICES:
        raise Refused(f"the save choice is one of {', '.join(SAVE_CHOICES)}, and {choice!r} "
                      "was given")
    return _choice(incident, "save", actor, actor_verified, now, lambda lines: {"saved": choice})


# ── What the incidents list derives ─────────────────────────────────────────────────────────

def state_of(incident: Incident, resolved: float, *, now: float = None) -> str:
    """What the incidents list reads of troubleshooting in *incident*, derived each time and
    never stored: ``resolved`` when it has resolved (*resolved*: when, epoch seconds; None
    while it stands); ``cancelled`` while it has not, its newest choice is a cancel, and
    nothing was proposed or run after that cancel; ``open`` otherwise; ``unreadable`` when it
    stands and what would say (its record, or a run record an attempt could be in) cannot be
    read: never ``open`` in its place."""
    _check(incident)
    if resolved is not None:
        return "resolved"
    rec = read(incident)
    if rec["state"] == "unreadable":
        return "unreadable"
    last = max((n for n, line in enumerate(rec["lines"]) if "choice" in line), default=None)
    if last is None or rec["lines"][last]["choice"] != "cancel":
        return "open"
    if any("proposal" in line for line in rec["lines"][last + 1:]):
        return "open"
    got = attempts(incident, now=now)
    if got["state"] != "ok":
        return "unreadable"
    cancelled_at = rec["lines"][last]["epoch"]
    return "open" if any(a["started_at"] > cancelled_at for a in got["attempts"]) else "cancelled"


def how_fixed_source(incident: Incident, resolved: float) -> str:
    """Where the fix that resolved *incident* came from, derived each time and never stored:
    the source (`SOURCES`) of the proposal named by the run of the last attempt before
    *resolved*, when that attempt passed (`passed`). ``ai`` only then: the page reads it as
    "AI-assisted". ``""`` when the incident has not resolved, no attempt was made before it
    did, the last one did not pass (a pass followed by a failing attempt fixed nothing), or
    its run names no proposal this record holds; ``unreadable`` when what would say cannot be
    read."""
    _check(incident)
    if resolved is None:
        return ""
    got = attempts(incident, resolved)
    if got["state"] != "ok":
        return "unreadable"
    before = [a for a in got["attempts"] if a["started_at"] <= float(resolved)]
    if not before or not before[-1]["passed"]:
        return ""
    return before[-1]["source"]
