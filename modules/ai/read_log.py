"""The read loop's send log: every read a model asked for, and every answer sent to the provider
(board H, part H26; docs/HEAL_TO_INTENT.md 19.5, "Every send is logged", and 15.14 of
docs/PHASE8_PLAN.md, History's AI calls; the operator's N20: "every send logged").

**What it holds, never what was read.** One store for the installation, ``ai_reads.jsonl``
beside the record of AI calls (`calls._path`), owner-only from creation, append-only, one line
per event, under the store's lock across processes. Two rows (`ROWS`), each naming its loop
(``loop``, `new_id`):

- ``reads``, written by `read_loop.run` once Mercury's check has judged pass 1's requests and
  the allowed ones have run, and **before** pass 2 is asked (`sending`): the loop's network,
  its subject (the incident), its task and trigger, pass 1's call id, and one entry per request
  (`ENTRY`): its id (``read:<n>``), the device, the operation and the command as matched (the
  requests the check rendered), the egress class it goes out under, the verdict (run, refused
  or failed) and the reason, why the model asked and the hypothesis it tests, the reads
  engine's run (History › Reads) and whom it signed in as, and for a read that ran: the
  answer's bytes and sha256 as sent (masked and cut) and as a whole (masked), whether it was
  cut and how many lines the mask withheld. **The answer's text is never here**: the masked
  bytes that left the host are pass 2's prompt, in the record of AI calls (15.14).
  A loop whose ``reads`` row cannot be written asks no pass 2: nothing is sent that is not
  logged first (`read_loop.run`).
- ``sent``, written once pass 2's ask has returned (`answered`): its call id and whether the
  request left the host (``left_host``): no when the gateway refused it before any provider
  request (a feature off, a cap, the key, a marking: `read_loop.NOT_SENT_KINDS` and
  `CAP_KINDS`), yes for every other outcome, an answer or the provider's failure. A ``reads``
  row with no ``sent`` row is read as possibly sent (`loops`: "not recorded"), never as kept.

**Masked at rest:** every string but the digests passes `redact.redact_payload` before it is
kept, as the step log's and the analyses' rows do; the requests were masked for egress by the
check already. History draws each request as its own row, kind ``ai_read``, beside the two
calls (`history_sources.ai_reads`).
"""

import json
import logging
import os
import re
import time
import uuid

log = logging.getLogger(__name__)

FILE_NAME = "ai_reads.jsonl"
ROWS = ("reads", "sent")
#: What each request's entry keeps (`entry`): never the answer's text.
ENTRY = ("id", "device", "op", "commands", "egress_class", "verdict", "reason", "why",
         "hypothesis", "run", "signed_in_as", "sent_bytes", "sent_sha256", "bytes", "sha256",
         "cut", "withheld")
#: The digests, kept as they are (a mask never reads a hex digest as a secret's value).
DIGESTS = ("sent_sha256", "sha256")
_HEX = re.compile(r"[0-9a-f]{64}")
LOOP_ID = re.compile(r"rl-[0-9a-f]{16}")


class Refused(ValueError):
    """A row not kept; the words say why."""


def path() -> str:
    """The log's file: beside the record of AI calls, so whatever folder holds that record
    holds this one."""
    from modules.ai import calls

    return os.path.join(os.path.dirname(calls._path()), FILE_NAME)


def new_id() -> str:
    return "rl-" + uuid.uuid4().hex[:16]


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _command(request) -> str:
    """One rendered request as text: a CLI command as it is, an HTTP ``(method, path)`` as
    ``METHOD path``."""
    if isinstance(request, (list, tuple)) and len(request) == 2:
        return f"{request[0]} {request[1]}"
    return str(request)


def entry(record: dict, egress_class: str = "") -> dict:
    """One read record (`read_loop.run_reads`'s) as the log keeps it (`ENTRY`): its answer's
    sizes and digests, never its text."""
    args = record.get("args") or {}
    out = {"id": record.get("id") or "", "device": str(args.get("device") or ""),
           "op": record.get("op") or "",
           "commands": [_command(r) for r in record.get("requests") or []],
           "egress_class": egress_class, "verdict": record.get("verdict") or "",
           "reason": record.get("reason") or "", "why": record.get("why") or "",
           "hypothesis": record.get("hypothesis") or "", "run": record.get("run") or "",
           "signed_in_as": dict(record.get("signed_in_as") or {})}
    if record.get("verdict") == "run":
        out.update(sent_bytes=int(record.get("sent_bytes") or 0),
                   sent_sha256=record.get("sent_sha256") or "",
                   bytes=int(record.get("bytes") or 0), sha256=record.get("sha256") or "",
                   cut=bool(record.get("cut")), withheld=int(record.get("withheld") or 0))
    return {k: out[k] for k in ENTRY if k in out}


def _masked(row: dict) -> dict:
    from modules import redact

    kept = redact.redact_payload(dict(row))
    for e, raw in zip(kept.get("reads") or [], row.get("reads") or []):
        for k in DIGESTS:
            if k in raw:
                e[k] = raw[k] if _HEX.fullmatch(str(raw[k] or "")) else ""
    return kept


def _append(row: dict, now: float = None) -> dict:
    from modules import filestore
    from modules.config import open_secure

    if row.get("row") not in ROWS:
        raise Refused(f"a send log row is one of {', '.join(ROWS)}, not {row.get('row')!r}")
    if not LOOP_ID.fullmatch(str(row.get("loop") or "")):
        raise Refused(f"a send log row names its loop by an id of the shape rl-<16 hex>, not "
                      f"{row.get('loop')!r}")
    now = time.time() if now is None else float(now)
    kept = _masked(dict(row, at=_iso(now), epoch=now))
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with filestore.PathLock(p):
        with open_secure(p, "a") as fh:
            fh.write(json.dumps(kept, sort_keys=True) + "\n")
    return kept


def sending(loop: str, *, network: str, subject: dict, task: str, trigger: dict,
            first_call: str, entries: list, now: float = None) -> dict:
    """The ``reads`` row, written BEFORE pass 2 is asked: the loop's requests and what of them
    is to be sent (``to_send``, the ids that ran). Raises when it is not kept; the loop then
    asks no pass 2."""
    trig = trigger or {}
    return _append({"row": "reads", "loop": loop, "network": network or "",
                    "subject": dict(subject or {}), "task": task or "",
                    "trigger": {k: trig.get(k) for k in ("kind", "feature", "job", "network")
                                if trig.get(k)},
                    "first_call": first_call or "", "reads": list(entries),
                    "to_send": [e["id"] for e in entries if e.get("verdict") == "run"]}, now)


def answered(loop: str, *, second_call: str, left_host: bool, why: str = "",
             now: float = None) -> dict:
    """The ``sent`` row, written once pass 2's ask has returned: its call id and whether the
    request left the host."""
    return _append({"row": "sent", "loop": loop, "second_call": second_call or "",
                    "left_host": bool(left_host), "why": why or ""}, now)


def read() -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``, oldest first. A line that
    will not parse makes the read unreadable, never a row quietly missing; a read creates
    nothing."""
    p = path()
    if not os.path.exists(p):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [],
                "error": f"the read loop's send log cannot be read ({type(exc).__name__})"}
    return {"state": "ok", "rows": rows, "error": ""}


def loops(rows=None) -> dict:
    """``{"state", "loops", "error"}``: each loop's ``reads`` row with its ``sent`` (``{}``
    while none is recorded), oldest first. *rows* the store's, read once by a caller."""
    if rows is None:
        got = read()
        if got["state"] == "unreadable":
            return {"state": "unreadable", "loops": [], "error": got["error"]}
        state, rows = got["state"], got["rows"]
    else:
        state = "ok"
    sent = {r.get("loop"): r for r in rows if r.get("row") == "sent"}
    out = [dict(r, sent=sent.get(r.get("loop")) or {}) for r in rows if r.get("row") == "reads"]
    return {"state": state, "loops": out, "error": ""}


def left_host_words(loop: dict, read_id: str) -> str:
    """Whether the answer of *read_id* left the host, in words: sent in pass 2's call, not sent
    and why, not to be sent (it did not run), or not recorded (a ``reads`` row with no ``sent``
    row: it may have left)."""
    if read_id not in (loop.get("to_send") or []):
        return "not sent: it did not run"
    sent = loop.get("sent") or {}
    if not sent:
        return "not recorded whether pass 2 was sent: read it as sent"
    if sent.get("left_host"):
        return f"sent to the provider in pass 2's call {sent.get('second_call') or '?'}"
    return f"not sent: {sent.get('why') or 'pass 2 was not asked'}"
