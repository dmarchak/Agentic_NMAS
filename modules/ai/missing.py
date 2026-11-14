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
  operation does (the answer's ``gap``).
Each row: when, the feature, the network, what was wanted (the read's operation and its words,
or the gap's words), why (the request's why, or the gap's evidence), Mercury's reason, and what
it was for (``incident`` or ``question``).

**Listed for review, never acted on.** `rows` lists them (History › AI missing capabilities,
`history_sources.ai_missing`); nothing in Mercury reads a row to do anything, and the AI is
never shown one. Kept beside the record of AI calls (`calls._path`), owner-only from creation,
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


def wanted(answer, records, *, feature: str, network: str, about: tuple) -> list:
    """The rows one checked answer makes: each refused read Mercury lacks (`lacking`), and the
    answer's gap, if any. *records* are the read loop's records; *about* is ``(kind, id)``,
    kind one of `ABOUT`."""
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
    kind, ident = about
    return [dict(row, feature=feature, network=network, about={"kind": kind, "id": str(ident)})
            for row in out[:MOST_PER_ASK]]


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
