"""Deploy receipts: what was SENT, what it was checked against, per device.

Register C60, the receipt half (Stage 7.1; the follow-up window is a job
behind it). Before this, "what did we push before this broke" had no answer:
the pipeline's audit file omits the program by design, the golden commit
holds the post-deploy CAPTURE, and the confirmed hash lived only in the
request. The preview-confirm component makes the promise *what you confirm
is what is sent*; the receipt is what lets anyone check it afterwards.

One JSON line per device per batch, in ``data/lists/<slug>/deploy_receipts.jsonl``,
``0600``, append-only, written by the deploy and restore apply paths after
the batch's golden commit so a row can name it. A device refused before
anything was sent gets a row too, saying so: a receipt that lists only the
devices that went through would be a record that silently omits the rest.

**Each row names the checks that RAN on that device** (the operator,
2026-09-27): the routing protocols verify compared, the route and interface
counts, or why verify did not run at all. That is only honest because the
verify it records now reads real output (C62, C64-C68): built before those
fixes, a receipt would have recorded "verified" for four devices checked
against nothing. A device with no routing protocol (r6) records that
genuine state, which is different from a check that did not run.

**The program is MASKED on the way in** (`redact_text`), as the modification
record is: nobody restores a network from a receipt, so it holds the lines'
shape and the hash of the real program, never a secret. The hash is of the
program as SENT, computed from the lines the pipeline pushed, and compared
with the hash the operator confirmed.

**What it does not record yet**, stated in every row rather than left out:
the follow-up window (did anything complain for N minutes after) and the
second reading (8.8). A row saying `not_run` is truthful; an absent key
reads as "nothing to say".
"""

import json
import logging
import os
import time
import uuid

log = logging.getLogger(__name__)

FILENAME = "deploy_receipts.jsonl"

FOLLOW_UP_NOT_BUILT = {
    "state": "not_run",
    "why": "the follow-up window (did anything complain after the deploy) is a "
           "job behind 7.1 (register C60), not built yet",
}
SECOND_READING_NOT_BUILT = {"state": "not_built", "why": "NSOT_PLAN 8.8, not built"}


def path_for(list_name: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(list_name), FILENAME)


def _checks(result: dict) -> dict:
    """What verify compared on this device, or why it did not run."""
    verify = result.get("verify") or {}
    outcome = result.get("outcome", "")
    if outcome == "refused":
        return {"ran": False, "why": "refused before anything was sent"}
    if not result.get("commands"):
        return {"ran": False,
                "why": result.get("reason") or "no program was sent, so nothing was verified"}
    if not verify:
        stage = result.get("stage") or "unknown"
        return {"ran": False, "why": f"verify did not complete (stopped at: {stage})"}
    pre, post = verify.get("pre", {}), verify.get("post", {})
    protocols = verify.get("checked_protocols") or []
    from_intent = list(verify.get("from_intent") or [])
    declared = verify.get("declared_protocols")
    checks = {
        "ran": True,
        "ok": verify.get("ok"),
        "issues": list(verify.get("issues") or []),
        # Declared by the target intent and not up after: verify did not
        # pass, and nothing was rolled back for it.
        "intent_unmet": list(verify.get("intent_unmet") or []),
        "checked_protocols": protocols,
        # Checked because intent declares them, though the device was not
        # running them before (its before-state alone would have missed them).
        "from_intent": from_intent,
        "intent_note": ("" if declared is not None else
                        "no target intent is known, so the protocols checked are "
                        "only those the device ran before the change"),
        "neighbours": {p: [(pre.get("routing_protocols") or {}).get(
                               p, 0 if p in from_intent else None),
                           (post.get("routing_protocols") or {}).get(p)]
                       for p in protocols},
        "routes": [pre.get("routes"), post.get("routes")],
        # False: read, and NOT compared (C115). Absent in rows written before
        # this was recorded, which the renderer draws as unknown.
        "routes_compared": verify.get("routes_compared"),
        "interfaces_up": [pre.get("interfaces_up"), post.get("interfaces_up")],
        "pending_convergence": list(result.get("pending_convergence") or []),
    }
    if not protocols:
        checks["neighbours_note"] = ("no routing protocol on this device: the "
                                     "neighbour check does not apply")
    return checks


def _authorised_record(given) -> list:
    from modules.nsot import authorisation
    from modules.redact import redact_text

    return [{"line": a["line"], "reason": redact_text(a["reason"])}
            for a in authorisation.normalise(given)]


def rows_for(report: dict, *, list_name: str, action: str, actor: str,
             actor_kind: str, confirmations: dict = None,
             command_hashes: dict = None, source_ref: str = "") -> list:
    """One receipt row per device in *report* (sent, failed or refused)."""
    from modules.redact import redact_text

    confirmations = confirmations or {}
    command_hashes = command_hashes or {}
    golden = report.get("golden") or {}
    golden_devices = set(golden.get("devices") or [])
    batch_id = golden.get("batch_id", "")
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows = []
    for result in report.get("results") or []:
        host = result.get("device", "")
        commands = list(result.get("commands") or [])
        confirmed = command_hashes.get(host)
        program_hash = result.get("program_hash", "")
        rows.append({
            "id": uuid.uuid4().hex[:16],
            "at": at,
            "action": action,
            "batch_id": batch_id,
            "list": list_name,
            "device": host,
            "actor": actor,
            "actor_kind": actor_kind,
            "source_ref": source_ref,
            "outcome": result.get("outcome", ""),
            "stage": result.get("stage", ""),
            "reason": redact_text(result.get("reason", "") or ""),
            "sent": bool(commands) and result.get("outcome") != "refused",
            "program": [redact_text(c) for c in commands],
            "program_lines": len(commands),
            "program_hash": program_hash,
            "confirmed_hash": confirmed,
            "matches_confirmed": (program_hash == confirmed) if (confirmed and program_hash)
            else None,
            "capture_hash": confirmations.get(host),
            # Each authorised line WITH the person's stated reason (C140):
            # an exception with no stated cause is indistinguishable from an
            # accident. The reason is testimony, masked like the program.
            "authorised": _authorised_record(result.get("authorised")),
            "checks": _checks(result),
            "rollback": {
                "performed": bool(result.get("rolled_back")),
                # What it achieved (C112): `performed` said a rollback RAN,
                # and was drawn "rolled back" over one that raised.
                "state": (result.get("rollback_outcome") or {}).get("state", ""),
                "detail": redact_text((result.get("rollback_outcome") or {}).get("detail", "")),
                "remaining": [redact_text(c) for c in
                              (result.get("rollback_outcome") or {}).get("remaining") or []],
                "commands": [redact_text(c) for c in result.get("rollback_commands") or []],
                "not_undone": list(result.get("rollback_not_undone") or []),
            },
            "golden_commit": golden.get("commit", "") if host in golden_devices else "",
            "second_reading": dict(SECOND_READING_NOT_BUILT),
            "follow_up": dict(FOLLOW_UP_NOT_BUILT),
        })
    return rows


def write(list_name: str, rows: list) -> dict:
    """Append *rows*. ``{"ok", "written", "error"}``; never raises, because
    the deploy has already happened and a failed receipt must not read as a
    failed deploy. It is loud instead: logged at ERROR and returned."""
    from modules.config import open_secure

    if not rows:
        return {"ok": True, "written": 0, "error": ""}
    path = path_for(list_name)
    try:
        with open_secure(path, "a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception as exc:                   # noqa: BLE001
        log.error("receipts: could not write %d receipt(s) for %s: %s",
                  len(rows), list_name, exc)
        return {"ok": False, "written": 0,
                "error": f"the deploy happened and its receipt could not be written: {exc}"}
    return {"ok": True, "written": len(rows), "error": ""}


def read(list_name: str, device: str = "", limit: int = 50) -> dict:
    """``{"state": "absent"|"ok"|"unreadable", "rows"}``, newest first.

    Absent and unreadable are different facts: no deploy yet, against a
    record that exists and cannot be read. A line that will not parse makes
    the whole read ``unreadable`` rather than being skipped, because a
    receipt quietly missing from an audit is the thing this file exists to
    prevent.
    """
    path = path_for(list_name)
    if not os.path.exists(path):
        return {"state": "absent", "rows": []}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except Exception as exc:                   # noqa: BLE001
        return {"state": "unreadable", "rows": [], "error": str(exc)}
    if device:
        rows = [r for r in rows if r.get("device") == device]
    return {"state": "ok", "rows": list(reversed(rows))[:limit]}


def prior_authorisations(list_name: str, device: str, lines=None) -> dict:
    """How often each line was authorised on *device* before, from the
    receipts: ``{"state", "lines": {key: {"count", "last_at", "last_actor",
    "last_reason"}}}``. The AGGREGATE (the operator, C140, from 8.8's written
    override): the same line authorised on the same device again and again is
    a pattern worth seeing, and a control that makes behaviour visible is
    measured by whether anyone would notice. A receipt written before
    reasons existed counts, with no reason recorded. *lines* narrows it to
    the keys a preview is showing. An unreadable record is said, never read
    as "never authorised"."""
    from modules.nsot import authorisation

    got = read(list_name, device=device, limit=10 ** 6)
    if got["state"] != "ok":
        return {"state": got["state"], "lines": {}}
    want = set(lines) if lines is not None else None
    out: dict = {}
    for row in reversed(got["rows"]):                  # oldest first
        if row.get("outcome") == "refused" or not row.get("sent"):
            continue
        for a in authorisation.normalise(
                [a if isinstance(a, dict) else {"line": a, "reason": ""}
                 for a in (row.get("authorised") or [])]):
            if want is not None and a["line"] not in want:
                continue
            e = out.setdefault(a["line"], {"count": 0})
            e.update({"count": e["count"] + 1, "last_at": row.get("at", ""),
                      "last_actor": row.get("actor", ""),
                      "last_reason": a["reason"] or "(none recorded: before reasons existed)"})
    return {"state": "ok", "lines": out}
