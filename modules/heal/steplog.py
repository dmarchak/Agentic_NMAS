"""The heal step log: every heal and dry-run decision's steps, and what the act did, masked
(board H, part H6; docs/HEAL_TO_INTENT.md sections 4, 8 and 9).

**One store, Mercury's records** (MERCURY_CHARTER, "Mercury's own records"): a line store kept
per network (``heal_steps.jsonl`` in the network's folder, owner-only), or the records database
once moved (`records_db.STORES`' ``heal_steps``, its switch ``records_store_heal_steps``),
written and read through `records_migrate.store_append` and `store_rows` as every other line
store. Append-only, one line per event, never rewritten.

**The rows** (`ROWS`), each naming its decision, incident and device:
- ``decision``: the decision's own steps (`decide.STEPS`), each its result and words, the
  outcome, the mode, the guard that applied, the masked program and its hash (`decide.run`
  writes it once the decision is recorded);
- ``started``: the act's steps up to its apply, with the masked program and its hash, written
  BEFORE anything is sent (section 4: "written to the step log before anything is sent"); the
  act refuses a heal whose ``started`` row cannot be written;
- ``act``: the act's every step (`act.STEPS`), the outcome, and its records: the golden commit,
  the deploy receipt's decision, the golden re-check, the change record (deterministic, no AI
  call: `modules/heal/change_record.py`) and the NetBox journal entry (`modules/heal/journal.py`);
- ``raised``: the act's job raised before it recorded an outcome (its exception's words);
- ``interrupted``: a heal whose job ended before it recorded its outcome, found and recorded by
  `modules/heal/interrupted.py`;
- ``diagnosis``: one diagnosis runbook's run (`modules/heal/diagnose.py`, 19.3): its steps, its
  ranked hypotheses and the checks it ruled out, each read named by its reads run (History ›
  Reads holds the masked answer; this row never holds a device's text). Attached to its
  incident when the heal ran it (`incidents` draws it on that entry), its own record when a
  person did (`diagnoses`). "Diagnosed" is not a fix: the row changes no entry's outcome.
- ``advisory``: the AI analysis's one step for an incident (19.5, H26): its words, each pass,
  each read request the check refused with its reason, the reads run, and the calls' and the
  send log's ids; written by `modules/ai/heal_analysis.py` (`record_advisory`), never by the
  heal loop, and read only by History (`advisories`). It makes no entry and is never an
  entry's step, so what Mercury tried (H8's ``tried``) stays Mercury's.

**Masked:** every string a row carries passes through `redact.redact_text` before it is kept
(a secret's position and value never reach the store), and again on the way out (History).

**The seams it leaves.** H8's AI analysis of a can't-fix reads an incident's steps through
`incident` (what Mercury tried, in Mercury's words) and writes only its ``advisory`` step
(H26); the heal loop never reads the analysis or that step. H5's approved proposal writes its rows through `record_started` and
`record_act` as H4's apply does, its ``by`` the person who approved it. H9's History step log
draws `incidents`.
"""

import logging
import os
import time
import uuid

log = logging.getLogger(__name__)

STORE = "heal_steps"
FILE_NAME = "heal_steps.jsonl"
ROWS = ("decision", "started", "act", "raised", "interrupted", "diagnosis", "advisory")
#: An advisory row's fields kept (`record_advisory`): its words, its steps and its references
#: (the calls' ids, the send log's loop), never a model's answer.
ADVISORY_FIELDS = ("words", "steps", "state", "calls", "loop", "pass")
#: A diagnosis row's fields kept (`record_diagnosis`): Mercury's words and read references only.
DIAGNOSIS_FIELDS = ("id", "runbook", "runbook_words", "target", "incident", "actor", "state",
                    "words", "steps", "hypotheses", "more", "ruled_out", "not_checked",
                    "commands", "cap", "runs", "stopped", "devices", "started_at",
                    "finished_at", "hops")
#: Each outcome as History marks it (section 8: healed, would heal, proposed, can't fix, held
#: and halted), the decision's and the act's.
MARKS = {"heal": "healing", "would_heal": "would heal", "propose": "proposed",
         "cant_fix": "can't fix", "held": "held", "halted": "halted", "off": "off",
         "nothing": "nothing to heal", "deferred": "checked again later",
         "healed": "healed", "symptom_remains": "symptom remains", "partial": "partial",
         "refused": "nothing sent", "rolled_back": "rolled back",
         "failed": "failed after sending", "interrupted": "interrupted",
         "declined": "declined", "withdrawn": "withdrawn",
         # 19.4's marks for an action (H20, `bounce.OUTCOMES`): bounced, and each way it was not.
         "bounced": "bounced", "still_flapping": "bounced, still flapping",
         "not_formed": "bounced, adjacency not formed", "unverified": "bounced, not verified",
         "reverted": "reverted by its timer", "repaired": "repaired",
         # 19.4's marks for a session clear (H21, `session_clear.OUTCOMES`).
         "cleared": "cleared", "not_back": "cleared, session not back",
         "reset": "soft clear reset the session", "rejected": "clear refused by the device"}
#: The outcomes that are not a success: drawn amber or red, never as healed.
NOT_HEALED = ("symptom_remains", "partial", "rolled_back", "failed", "interrupted",
              "still_flapping", "not_formed", "unverified", "reverted", "repaired",
              "not_back", "reset", "rejected")
MODE_WORDS = {"auto": "AUTO", "dry_run": "dry run", "off": "off"}
#: Each action kind's family (19.4: an action is named as an action wherever it is drawn).
ACTION_FAMILY = {"port_bounce": "bounce", "ospf_reset": "bounce", "session_clear": "clear",
                 "dampening_proposal": "dampening"}
#: An action's marks where its family's words differ from `MARKS` (H23): a dry run of a bounce
#: "would bounce", never "would heal"; a clear's or a dampening's end never "bounced".
ACTION_MARKS = {
    "bounce": {"heal": "bouncing", "would_heal": "would bounce", "propose": "bounce proposed",
               "failed": "bounced, NOT RESTORED"},
    "clear": {"heal": "clearing", "would_heal": "would clear", "propose": "clear proposed",
              "unverified": "cleared, not verified"},
    "dampening": {"propose": "dampening proposed", "dampened": "dampened",
                  "unverified": "dampened, not verified",
                  "rolled_back": "dampening rolled back",
                  "failed": "dampening NOT RESTORED"},
}
#: The fields of a decision's ``action`` every row keeps (H23), so History names the port or the
#: neighbour an action was on. A row written before them has none, and is drawn as before.
ACTION_FIELDS = ("kind", "device", "interface", "peer", "variant", "far_device",
                 "far_interface", "trigger")


def mark(outcome: str, kind: str = "") -> str:
    """*outcome* as History marks it for *kind* (`ACTION_MARKS`, else `MARKS`)."""
    fam = ACTION_MARKS.get(ACTION_FAMILY.get(kind or "", ""), {})
    return fam.get(outcome) or MARKS.get(outcome, (outcome or "").replace("_", " "))


def subject(entry: dict) -> str:
    """What an entry acted on, as History's line names it: ``edge1 GigabitEthernet4`` for a
    bounce or a dampening, ``edge1's BGP neighbour 198.51.100.3`` for a clear, else the
    device."""
    a, host = entry.get("action") or {}, entry.get("device") or ""
    fam = ACTION_FAMILY.get(a.get("kind") or entry.get("kind") or "", "")
    if fam == "clear" and a.get("peer"):
        return f"{host}'s BGP neighbour {a['peer']}"
    if fam in ("bounce", "dampening") and a.get("interface"):
        return f"{host} {a['interface']}"
    return host


def far_ends(entry: dict) -> list:
    """``[{"device", "interface"}]``: the far ends an action's planned window named (C2749), from
    its act's records, else its decision's far end; the entry's own device left out."""
    host = entry.get("device") or ""
    w = (entry.get("records") or {}).get("window") or {}
    got = [f for f in w.get("far_ends") or [] if isinstance(f, dict) and f.get("device")]
    if not got:
        a = entry.get("action") or {}
        if a.get("far_device"):
            got = [{"device": a["far_device"], "interface": a.get("far_interface") or ""}]
    return [f for f in got if f["device"] != host]


class Refused(ValueError):
    """A row refused (no network, an unknown row), in words."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _path(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), FILE_NAME)


def _network(network: str) -> str:
    """The store's network: the list's folder name, verbatim, as every per-network store names
    it (never re-slugged)."""
    return os.path.basename(os.path.dirname(_path(network)))


def masked(value):
    """Every string in *value* masked by the one redactor, its shape kept."""
    from modules.redact import redact_text

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: masked(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [masked(v) for v in value]
    return value


def append(network: str, row: dict, now: float = None) -> dict:
    """Append one row, masked, with its id and time. Raises naming why when it is not kept: a
    network that does not exist (a write creates no network), an unknown row, or the store's
    own failure (`records_migrate.store_append`'s)."""
    from modules import records_migrate
    from modules.nsot import listref

    if not network or not listref.exists(network):
        raise Refused(f"{network or 'no network'} is no network, so no step is recorded")
    if row.get("row") not in ROWS:
        raise Refused(f"a step log row is one of {', '.join(ROWS)}, not {row.get('row')!r}")
    now = time.time() if now is None else float(now)
    kept = masked(dict(row, id="hs-" + uuid.uuid4().hex[:12], network=network, at=_iso(now),
                       epoch=now))
    records_migrate.store_append(STORE, _path(network), kept, network=_network(network))
    return kept


def read(network: str) -> dict:
    """*network*'s rows, oldest first: ``{"state": "ok"|"absent"|"unreadable", "rows",
    "error"}``. Absent (nothing recorded yet) and unreadable are different answers, and a read
    creates nothing."""
    from modules import records_migrate

    if not network:
        return {"state": "unreadable", "rows": [], "error": "no network was named"}
    got = records_migrate.store_rows(STORE, _path(network), network=_network(network))
    if got["state"] == "unreadable":
        log.error("heal: %s's step log is unreadable (%s)", network, got["error"])
    return got


# ── The writers ─────────────────────────────────────────────────────────────────────────────

def _of(decision: dict) -> dict:
    """The fields every row names: the decision, its incident and device, its mode, policy."""
    from modules import fault_drills

    pol = decision.get("policy") or {}
    a = decision.get("action") or {}
    # A declared fault drill's decision (its incident's tag at creation): History says so.
    drill = fault_drills.tag_of(decision)
    return {**({fault_drills.FIELD: drill} if drill else {}),
            "decision": decision.get("id") or "", "incident": decision.get("incident") or "",
            "device": decision.get("device") or "", "mode": decision.get("mode") or "",
            "kind": decision.get("kind") or "", "tier": decision.get("tier") or 0,
            "policy": {"fingerprint": pol.get("fingerprint") or "", "by": pol.get("by") or "",
                       "reason": pol.get("reason") or ""},
            # An action's port or neighbour (H23): History names what it acted on.
            **({"action": {k: a.get(k) or "" for k in ACTION_FIELDS}} if a.get("kind")
               else {})}


def decision_steps(decision: dict) -> list:
    """The decision's steps (`decide.STEPS`): each step it passed, then the step it ended on
    (its outcome and words), then the record."""
    steps = [dict(s) for s in decision.get("steps") or []]
    # The step's words are what Mercury did or would do (C2817); the cause is the decision's
    # own, said once where the decision is drawn.
    steps.append({"step": decision.get("phase") or "decide",
                  "result": decision.get("outcome") or "",
                  "words": decision.get("outcome_words") or decision.get("words") or ""})
    # C2817: the decision's id is the row's own field, drawn under "Details for the record".
    steps.append({"step": "record", "result": "ok", "words": "the decision recorded"})
    return steps


def record_decision(network: str, decision: dict, now: float = None) -> dict:
    """The ``decision`` row for one recorded decision (`decisions.record`'s, its id held)."""
    guard = decision.get("guard") or {}
    return append(network, dict(
        _of(decision), row="decision", outcome=decision.get("outcome") or "",
        words=decision.get("words") or "", steps=decision_steps(decision),
        guard={k: guard.get(k) for k in ("guard", "name", "words")} if guard else {},
        program=list(decision.get("program") or []),
        program_hash=decision.get("program_hash") or "",
        units=[u.get("words") for u in decision.get("units") or []],
        triggers=[t for t in decision.get("triggers") or [] if t],
        person=(decision.get("person") or {}).get("words") or "",
        # C2817, C2823 (expand: a row written before them has neither): what Mercury did or
        # would do on its own, and the cause it stated, facts first.
        outcome_words=decision.get("outcome_words") or "",
        headline=decision.get("headline") or "", cause=decision.get("cause") or None), now)


def policy_words(what: str, setter: str) -> str:
    """"<what> (policy set by <name>)": how a heal run as the policy names itself in its rows'
    words, the policy's setter by display name (board E2a, `identity.display_name`). The
    setter's identity is kept beside the words, in the row's own field (`policy_by`), so a
    row written from now on needs no filter to be drawn; a row from before, whose words hold
    the identity, is drawn through `display_names.people`."""
    from modules import identity

    return f"{what} (policy set by {identity.display_name(setter) if setter else 'nobody recorded'})"


def _policy_by(policy_by: str) -> dict:
    """The row's ``policy_by``: the policy setter's identity, beside words that name them by
    display name. Expand only: a row whose writer names none carries no key."""
    return {"policy_by": policy_by} if policy_by else {}


def record_started(network: str, decision: dict, steps: list, program: list,
                   program_hash: str, *, by: str, policy_by: str = "",
                   now: float = None) -> dict:
    """The ``started`` row: the act's steps so far and the program (masked) and its hash,
    BEFORE anything is sent. Raises when it is not kept: the act then refuses the heal."""
    return append(network, dict(_of(decision), row="started", steps=list(steps),
                                program=list(program), program_hash=program_hash, by=by,
                                **_policy_by(policy_by)), now)


def record_act(network: str, decision: dict, result: dict, *, by: str, policy_by: str = "",
               now: float = None) -> dict:
    """The ``act`` row: the act's every step, its outcome and words, and its records."""
    return append(network, dict(
        _of(decision), row="act", outcome=result.get("outcome") or "",
        words=result.get("words") or "", steps=list(result.get("steps") or []),
        sent=bool(result.get("sent")), records=dict(result.get("records") or {}), by=by,
        **_policy_by(policy_by)), now)


def record_raised(network: str, decision: dict, words: str, now: float = None) -> dict:
    """The ``raised`` row: the act's job raised before it recorded an outcome."""
    return append(network, dict(_of(decision), row="raised", words=words), now)


def record_diagnosis(network: str, diagnosis: dict, now: float = None) -> dict:
    """The ``diagnosis`` row for one run of a diagnosis runbook (`diagnose.run`'s answer):
    `DIAGNOSIS_FIELDS` only, masked; its first device is the row's device."""
    kept = {k: diagnosis.get(k) for k in DIAGNOSIS_FIELDS}
    return append(network, dict(row="diagnosis", decision="",
                                incident=diagnosis.get("incident") or "",
                                device=(diagnosis.get("devices") or [""])[0],
                                diagnosis=kept), now)


def record_advisory(network: str, incident: str, *, device: str, words: str, steps: list,
                    state: str = "", calls=(), loop: str = "", passes: int = 0,
                    now: float = None) -> dict:
    """The ``advisory`` row: the AI's advisory step for *incident* (docs/HEAL_TO_INTENT.md
    19.5: "The incident's step log gets one step"), written by its caller outside the heal
    loop (`modules/ai/heal_analysis.py`, H26): *words* the step ("AI analysis: asked for 3
    reads; 2 run, 1 refused; second pass answered", or why nothing was sent), *steps* each
    pass, each refusal with its reason and the reads run, *calls* the calls' ids and *loop* the
    send log's. It makes no entry, changes no outcome and is not one of an entry's steps
    (`_fold` passes over it): nothing in the heal loop reads it; History draws it
    (`advisories`)."""
    kept = {"words": words, "steps": [dict(s) for s in steps or []], "state": state,
            "calls": [c for c in calls or () if c], "loop": loop, "pass": int(passes or 0)}
    return append(network, dict(row="advisory", decision="", incident=incident or "",
                                device=device or "",
                                advisory={k: kept[k] for k in ADVISORY_FIELDS}), now)


def advisories(network: str) -> dict:
    """``{"state", "by_incident": {incident: [its advisory rows' ``advisory``, oldest first,
    each with its ``at``]}, "error"}``: History's reader of the advisory step. No reader of the
    heal loop calls it (tests/test_read_loop_never_read.py)."""
    got = read(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "by_incident": {}, "error": got["error"]}
    out = {}
    for r in got["rows"]:
        if r.get("row") == "advisory" and r.get("incident"):
            out.setdefault(r["incident"], []).append(dict(r.get("advisory") or {},
                                                          at=r.get("at")))
    return {"state": got["state"], "by_incident": out, "error": ""}


def record_interrupted(network: str, decision: dict, words: str, *, halted: bool, by: str,
                       now: float = None) -> dict:
    """The ``interrupted`` row (`modules/heal/interrupted.py`)."""
    return append(network, dict(_of(decision), row="interrupted", outcome="interrupted",
                                words=words, halted=bool(halted), by=by,
                                steps=[{"step": "record", "result": "interrupted",
                                        "words": words}]), now)


# ── The readers ─────────────────────────────────────────────────────────────────────────────

def _fold(rows: list) -> list:
    """*rows* folded into one entry per incident, oldest first (section 8: one record per
    incident; an incident checked again later holds each of its decisions). A ``diagnosis`` row
    makes no entry: it is attached to its incident's entry (its last), and a person's own
    diagnosis is `diagnoses`'."""
    by = {}
    for r in rows:
        if r.get("row") in ("diagnosis", "advisory"):
            # An advisory row (the AI's step, H26) is never an entry's step: what Mercury
            # tried stays Mercury's, and no reader of the loop meets the AI's.
            continue
        key = r.get("incident") or r.get("decision") or r.get("id")
        e = by.get(key)
        if e is None:
            e = by[key] = {"incident": r.get("incident") or "", "device": r.get("device") or "",
                           "network": r.get("network") or "", "decisions": [], "steps": [],
                           "program": [], "program_hash": "", "records": {}, "outcome": "",
                           "words": "", "mode": "", "kind": "", "policy": {}, "by": "",
                           "first_at": r.get("at"), "at": r.get("at"),
                           "epoch": float(r.get("epoch") or 0), "state": "decided",
                           "units": [], "triggers": [], "person": "", "guard": {}, "tier": 0,
                           "cause": None, "outcome_words": "", "headline": ""}
        if r.get("decision") and r["decision"] not in e["decisions"]:
            e["decisions"].append(r["decision"])
        e["at"], e["epoch"] = r.get("at"), float(r.get("epoch") or 0)
        # The tier its decision recorded (H17: an Alert incident, Tier 3, is diagnosed before
        # its notice).
        for k in ("mode", "kind", "tier", "action"):
            if r.get(k):
                e[k] = r[k]
        from modules import fault_drills
        if fault_drills.tag_of(r):
            e[fault_drills.FIELD] = fault_drills.tag_of(r)
        if (r.get("policy") or {}).get("fingerprint"):
            e["policy"] = r["policy"]
        row = r.get("row")
        steps = [dict(s, row=row, decision=r.get("decision") or "") for s in r.get("steps") or []]
        if row == "decision":
            e.update(outcome=r.get("outcome") or "", words=r.get("words") or "",
                     state="decided", guard=r.get("guard") or {}, units=r.get("units") or [],
                     triggers=r.get("triggers") or [], person=r.get("person") or "",
                     outcome_words=r.get("outcome_words") or "",
                     headline=r.get("headline") or "")
            if r.get("cause"):
                e["cause"] = r["cause"]
            e["steps"] += steps
            if r.get("program_hash"):
                e.update(program=list(r.get("program") or []), program_hash=r["program_hash"])
        elif row == "started":
            # The steps the act row repeats once it ends: kept only until then.
            e["started"] = steps
            e.update(state="applying", by=r.get("by") or e["by"])
            if r.get("program_hash"):
                e.update(program=list(r.get("program") or []), program_hash=r["program_hash"])
        elif row == "act":
            e.pop("started", None)
            e["steps"] += steps
            e.update(outcome=r.get("outcome") or "", words=r.get("words") or "", state="done",
                     records=dict(r.get("records") or {}), by=r.get("by") or e["by"],
                     sent=bool(r.get("sent")))
        elif row == "raised":
            e["raised"] = r.get("words") or ""
        elif row == "interrupted":
            e["steps"] += e.pop("started", [])
            e["steps"] += steps
            e.update(outcome="interrupted", words=r.get("words") or "", state="interrupted",
                     halted=bool(r.get("halted")), by=r.get("by") or e["by"])
    for r in rows:
        if r.get("row") == "diagnosis" and r.get("incident") in by:
            by[r["incident"]]["diagnosis"] = r.get("diagnosis") or {}
    out = []
    for e in by.values():
        if "started" in e:
            e["steps"] += e.pop("started")
        out.append(e)
    return out


def diagnoses(network: str, device: str = "", incident: str = "") -> dict:
    """*network*'s diagnoses, newest first: ``{"state", "diagnoses", "error"}``; *device* keeps
    those that read it, *incident* those attached to it. Each is its row's ``diagnosis`` with
    the row's ``at``. A read creates nothing; absent and unreadable are different answers."""
    got = read(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "diagnoses": [], "error": got["error"]}
    out = []
    for r in got["rows"]:
        if r.get("row") != "diagnosis":
            continue
        d = dict(r.get("diagnosis") or {}, at=r.get("at"))
        if device and device not in (d.get("devices") or []):
            continue
        if incident and d.get("incident") != incident:
            continue
        out.append(d)
    return {"state": got["state"], "diagnoses": out[::-1], "error": ""}


def incidents(network: str, device: str = "") -> dict:
    """*network*'s step log, one entry per incident, oldest first: ``{"state", "entries",
    "error"}``; *device* keeps one device's. Each entry: its incident and device, its decisions,
    every step (``step``, ``result``, ``words`` and the ``row`` and ``decision`` it came from),
    the program (masked) and its hash, the outcome and words, the mode, the policy, its records,
    and its ``state``: ``decided``, ``applying`` (its act started and has not ended), ``done``
    or ``interrupted``."""
    got = read(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "entries": [], "error": got["error"]}
    entries = _fold(got["rows"])
    if device:
        entries = [e for e in entries if e["device"] == device]
    return {"state": got["state"], "entries": entries, "error": ""}


def incident(network: str, incident_id: str) -> dict:
    """One incident's entry (**H8's seam**: what Mercury tried, in its own words), or ``{}``.
    Raises when the store cannot be read: an analysis of what is unread is never made."""
    got = incidents(network)
    if got["state"] == "unreadable":
        raise RuntimeError(f"{network}'s heal step log cannot be read: {got['error']}")
    return next((e for e in got["entries"] if e["incident"] == incident_id), {})


def of_decision(network: str, decision_id: str) -> dict:
    """``{"state", "rows", "started", "raised", "last", "error"}`` for one decision: its rows,
    whether its act wrote ``started`` (so something may have been sent), the last ``raised``
    words, and the last step any row recorded."""
    got = read(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "rows": [], "started": None, "raised": "", "last": {},
                "error": got["error"]}
    rows = [r for r in got["rows"] if r.get("decision") == decision_id]
    steps = [s for r in rows for s in r.get("steps") or []]
    raised = [r.get("words") or "" for r in rows if r.get("row") == "raised"]
    return {"state": got["state"], "rows": rows,
            "started": any(r.get("row") == "started" for r in rows),
            "raised": raised[-1] if raised else "", "last": steps[-1] if steps else {},
            "error": ""}
