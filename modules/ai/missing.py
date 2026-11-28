"""Missing capabilities: what the AI wanted that Mercury lacks (the operator, 2026-11-14, C3663:
"When the AI wants a tool or catalog operation Mercury lacks, it records a finding (what it
wanted, why, for which incident or question), listed for review").

**What is recorded.** One row per want, from the AI's own answer as Mercury checked it, never
from the model's say-so alone:
- **a read** (`KIND_READ`): a read the model asked for that Mercury refused because Mercury
  lacks it, not because the request was out of scope: the allowlist refuses the command, it is
  left out of the AI's reads on purpose, it is in none of the AI's command families (or none of
  a family's forms), or it is no operation of the read family (`LACKING`). A read refused for its scope (an address not of the network, an interface the
  golden does not hold) or its class (the configuration class off) is the check working, and
  is not recorded here;
- **an operation** (`KIND_OPERATION`): a gap, the fix the evidence points to that no catalog
  operation does (the answer's ``gap``); or what a person asked the toolbar assistant for that
  no operation or read of Mercury's does (its answer's ``no_tool``, one row per answer, for
  the question, 2026-11-28).
Each row: when, the feature, the network, what was wanted (the read's operation and its words,
or the gap's words), why (the request's why, or the gap's evidence), Mercury's reason, and what
it was for (``incident`` or ``question``).

**Listed for review; one thing acts on a row** (C3733, the operator, 2026-11-15): `rows` lists
them (History › AI missing capabilities, `history_sources.ai_missing`), and the AI is never
shown one. A gap keeps what it wanted (``wants``: its incident's problem condition, and the
steps Mercury could propose then); once a step that fixes that condition exists (registered
and deployed, `available`), R1's reader (`fixit.auto.capability_failures`) offers its incident
ONE restart, keyed to the row's id, within its caps. Nothing else reads a row to do anything. Kept beside the record of AI calls (`calls._path`), owner-only from creation,
append-only, one line per want, under the store's lock across processes, masked at rest
(`redact.redact_payload`).

**Cost:** one line per refused read or gap, a few hundred bytes; no call, no device.
**Prevents:** Mercury not learning which reads and operations engineers (and the AI on their
behalf) need, so the next build is chosen by measurement.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

FILE_NAME = "ai_missing_capabilities.jsonl"
KIND_READ, KIND_OPERATION = "read", "operation"
KINDS = (KIND_READ, KIND_OPERATION)
KIND_WORDS = {KIND_READ: "a read Mercury lacks", KIND_OPERATION: "an operation Mercury lacks"}
#: What a row is for: an incident's investigation, or a person's question.
ABOUT = ("incident", "question")
#: A refused read's reason that says Mercury lacks it (`router_reads.command_refusal` and
#: `read_loop._judge`'s own words), each the start of the reason after its operation's name.
LACKING = ("Mercury's read-only allowlist refuses", "is left out of the AI's reads on purpose",
           "is not an operation of the", "is not one of the AI's read families")
#: The most rows one investigation records (three reads a pass, and a gap).
MOST_PER_ASK = 4
TEXT_MAX = 300


def path() -> str:
    from modules.ai import calls

    return os.path.join(os.path.dirname(calls._path()), FILE_NAME)


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _one_line(text) -> str:
    text = " ".join(str(text or "").split())
    return text[:TEXT_MAX]


def lacking(reason: str) -> bool:
    """Whether a refused read's *reason* says Mercury lacks the read (`LACKING`)."""
    return any(w in (reason or "") for w in LACKING)


def row_id(about: dict, kind: str, what: str) -> str:
    """A row's stable id: what it was for and what it wanted (C3733: a restart is keyed to it,
    so one want restarts its incident once)."""
    import hashlib

    text = json.dumps([about.get("kind"), about.get("id"), kind, what], sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def capabilities() -> dict:
    """What Mercury can propose now, by key, with the problem conditions each fixes, through
    the one door that holds the catalog (`fix_proposal.capabilities`)."""
    from modules.ai import fix_proposal

    return fix_proposal.capabilities()


def available(row: dict, now_has: dict = None) -> list:
    """The steps that fix what *row* wanted and that it lacked when it was recorded (C3733):
    each key `capabilities` gives that fixes its ``wants`` condition and was not among the
    ``known`` keys of that moment, sorted; ``[]`` for a row that wanted no condition (a read,
    or an incident with no classified problem)."""
    wants = (row or {}).get("wants") or {}
    condition = wants.get("condition") or ""
    if not condition:
        return []
    known = set(wants.get("known") or ())
    have = capabilities() if now_has is None else now_has
    return sorted(k for k, fixes in have.items() if condition in fixes and k not in known)


def for_incident(incident_id: str) -> list:
    """The rows recorded for *incident_id*'s investigations, newest first; ``[]`` when the
    store is absent or cannot be read (an unread store restarts nothing)."""
    got = rows()
    return [r for r in got["rows"] if (r.get("about") or {}).get("kind") == "incident"
            and (r.get("about") or {}).get("id") == incident_id]


def wanted(answer, records, *, feature: str, network: str, about: tuple,
           condition: str = "", no_tool: dict = None) -> list:
    """The rows one checked answer makes: each refused read Mercury lacks (`lacking`), the
    answer's gap, if any, and *no_tool* (the toolbar assistant's "Mercury has no tool for
    this", ``{"wanted", "why", "reason"}``: an operation Mercury lacks, 2026-11-28), if given.
    *records* are the read loop's records; *about* is ``(kind, id)``,
    kind one of `ABOUT`. Each row has its stable `row_id`; a gap of an incident whose problem's
    *condition* is known also keeps what it wanted (``wants``: that condition, and the keys
    Mercury could propose then, `capabilities`), so it restarts once when a step that fixes it
    exists (`available`, C3733)."""
    out = []
    for r in records or ():
        if r.get("verdict") != "refused" or not lacking(r.get("reason") or ""):
            continue
        args = r.get("args") or {}
        what = " ".join(x for x in (r.get("op") or "", str(args.get("words") or "")) if x)
        out.append({"kind": KIND_READ, "what": _one_line(what or "a read"),
                    "device": str(args.get("device") or ""),
                    "why": _one_line(r.get("why")), "reason": _one_line(r.get("reason"))})
    gap = getattr(answer, "gap", None) if answer is not None else None
    if gap is not None:
        out.append({"kind": KIND_OPERATION, "what": _one_line(gap.what), "device": "",
                    "why": _one_line("cites " + ", ".join(list(gap.evidence_refs)[:6])),
                    "reason": "no catalog operation does it"})
        if condition:
            out[-1]["wants"] = {"condition": condition, "known": sorted(capabilities())}
    if no_tool and _one_line(no_tool.get("wanted")):
        out.append({"kind": KIND_OPERATION, "what": _one_line(no_tool.get("wanted")),
                    "device": "", "why": _one_line(no_tool.get("why")),
                    "reason": _one_line(no_tool.get("reason") or "Mercury has no tool for it")})
    kind, ident = about
    ab = {"kind": kind, "id": str(ident)}
    return [dict(row, feature=feature, network=network, about=ab,
                 id=row_id(ab, row["kind"], row["what"])) for row in out[:MOST_PER_ASK]]


def record(rows, now: float = None) -> dict:
    """Append *rows* (`wanted`'s). ``{"ok", "recorded", "error"}``: a store that cannot be
    written is said, never raised: the investigation's answer stands without its review row."""
    from modules import filestore, redact
    from modules.config import open_secure

    rows = [r for r in (rows or ()) if r.get("kind") in KINDS
            and (r.get("about") or {}).get("kind") in ABOUT]
    if not rows:
        return {"ok": True, "recorded": 0, "error": ""}
    now = time.time() if now is None else float(now)
    p = path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with filestore.PathLock(p):
            with open_secure(p, "a") as fh:
                for r in rows:
                    kept = redact.redact_payload(dict(r, at=_iso(now), epoch=now))
                    fh.write(json.dumps(kept, sort_keys=True) + "\n")
    except (OSError, ValueError) as exc:
        log.error("missing capabilities: %d row(s) not recorded: %s", len(rows), exc)
        return {"ok": False, "recorded": 0,
                "error": f"the missing capabilities store cannot be written "
                         f"({type(exc).__name__})"}
    return {"ok": True, "recorded": len(rows), "error": ""}


def rows() -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``, newest first. A line that
    will not parse makes the read unreadable, never a row quietly missing; a read creates
    nothing."""
    p = path()
    if not os.path.exists(p):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            got = [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [],
                "error": f"the missing capabilities store cannot be read ({type(exc).__name__})"}
    return {"state": "ok", "rows": list(reversed(got)), "error": ""}
