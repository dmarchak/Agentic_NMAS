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
against nothing. A device with no routing protocol (edge1, say) records that
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

**Where the lines live** (Phase 4, section 7): the file above, or, once a person moved the
store on the Records database card (`records_migrate.move`), the records database's
`audit.receipt_lines`, one INSERT per line in one transaction. The setting
`records_store_receipts` is read at each call. Either way the lines are the same JSON and
`_merged` runs unchanged on both, so a reader cannot tell them apart.
"""

import json
import logging
import os
import re
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

#: A row's commit state (CONCURRENCY_AUDIT R5's open half, the operator, 2026-10-02). A
#: device's row is written as the device FINISHES, ``pending``: the batch's golden commit
#: comes after the whole batch, and a process that ended in between used to leave the
#: devices already pushed with no receipt at all. After the commit a COMPLETION line names
#: the row (``completes``) and fills in the commit: ``committed`` (the golden is in it) or
#: ``no_golden`` (this device's outcome recorded none). The file stays append-only;
#: `read()` merges each completion into its row. A row still pending is drawn PENDING by
#: every reader, never as done; after a restart it is named by the interrupted-operation row.
PENDING, COMMITTED, NO_GOLDEN = "pending", "committed", "no_golden"
COMMIT_STATES = (PENDING, COMMITTED, NO_GOLDEN)

#: How every reader words a pending row: never done, never green.
PENDING_WORDS = "commit PENDING: its batch has not recorded it yet"

#: A SCOPED batch (the monitoring profile, the IP SLA probes, the missing monitoring templates)
#: is a deploy of part of intent, recorded `action: deploy` with its `scope` beside it (C364:
#: History said "Deployed", Needs attention "the last deploy" and an interrupted one "A deploy
#: was cut off" for a run that sent only the profile's or the probes' lines). Per scope: its
#: noun, which is also the hold's operation and the job's kind, and its past tense.
SCOPES = {"profile": ("monitoring profile apply", "Monitoring profile applied"),
          "ip_sla": ("IP SLA send", "IP SLA probes sent"),
          "templates": ("monitoring templates deploy", "Monitoring templates deployed")}
_PAST = {"deploy": "Deployed", "restore": "Restored", "reapply": "Re-applied"}


def noun(row: dict) -> str:
    """What the receipt's run was, as a noun: its scope's, else its action."""
    scope = SCOPES.get(row.get("scope") or "")
    return scope[0] if scope else (row.get("action") or "deploy")


def past(row: dict) -> str:
    """What the receipt's run did, in the past tense, for History."""
    scope = SCOPES.get(row.get("scope") or "")
    return scope[1] if scope else _PAST.get(row.get("action") or "", "Changed")


def operation(scope: str) -> str:
    """The hold's operation for a batch of *scope*: its noun, or ``deploy`` unscoped."""
    return SCOPES[scope][0] if scope in SCOPES else "deploy"


def is_pending(row: dict) -> bool:
    """Whether *row* still waits for its batch's commit (a row read by `read()`)."""
    return (row or {}).get("commit_state") == PENDING


def path_for(list_name: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(list_name), FILENAME)


def _checks(result: dict) -> dict:
    """What verify compared on this device, or why it did not run."""
    from modules.redact import redact_text

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
        # Read after the change and not trustworthy (C272): verify did not
        # pass, did not fail on them, and nothing was rolled back for them.
        "unreadable": list(verify.get("unreadable") or []),
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
        # Mode B: how many removed lines verify read back GONE. It was read and
        # not recorded, so r2's first removal receipt could not show it.
        "removals_checked": verify.get("removals_checked") or 0,
        # C178: BGP read once more no earlier than its hold time after the
        # push, with the hold time's basis; absent when BGP was not checked.
        "bgp_watch": verify.get("bgp_watch"),
        # Quick or full, and why (verify_scope); a quick verify's read-back.
        "verify_scope": verify.get("verify_scope"),
        "read_back": verify.get("read_back"),
        # C713: the IP SLA operations against rendered intent, both ways (None: not checked).
        "ip_sla_against_intent": verify.get("ip_sla_against_intent"),
        # C506 phase 3: each declared move's outcome, and verify's notes (an adjacency nobody
        # declared forming beside the expected ones; a declared route change read).
        "declared_moves": list(verify.get("declared_moves") or []),
        "notes": [redact_text(n) for n in verify.get("notes") or []],
        # C506 phase 4: the interfaces as verify compared them (by name, or counted when a read
        # named none), the program's expected effects, and the settle an unexpected loss was
        # given and whether verify failed at once over it.
        "interfaces": dict(verify.get("interfaces") or {}),
        "expected_effects": dict(verify.get("expected_effects") or {}),
        "unexpected_settle": verify.get("unexpected_settle"),
        "failed_at_once": verify.get("failed_at_once"),
        # The paired deploy (C1964): what of the link this end's own verify left to the link's
        # verify after both ends, and what of it was seen down. Absent on every other row.
        **({"pair_transient": dict(verify["pair_transient"])}
           if verify.get("pair_transient") else {}),
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


def _saved_startup(result: dict) -> dict:
    """Whether the change was saved to startup after verify (C511): ``{"state", "detail"}``,
    the state `saved`, `not_saved` (verified and running, a reload loses it) or `not_run`,
    with why. Since C501 the save follows a passed verify, so "saved" and "running and not
    saved" are different results, and a receipt that said neither read them alike."""
    from modules.redact import redact_text

    got = result.get("saved_startup") or {}
    if got.get("ok") is True:
        return {"state": "saved", "detail": ""}
    if got:
        return {"state": "not_saved",
                "detail": redact_text(got.get("error") or "no reason was recorded")}
    if result.get("rolled_back"):
        why = "the change was rolled back, so there was nothing to save"
    elif not result.get("commands") or result.get("outcome") == "refused":
        why = "nothing was sent"
    elif result.get("outcome") == "deployed":
        why = "the save did not run"
    else:
        why = f"the deploy stopped at {result.get('stage') or 'an unnamed stage'}, before it"
    return {"state": "not_run", "detail": why}


def stages_before_send() -> tuple:
    """The pipeline's stages that run before the program is sent (`pipeline.STAGE_NAMES` up to
    `deploy`): a run that stopped at one sent nothing (C1540)."""
    from modules.pipeline import STAGE_NAMES
    return tuple(STAGE_NAMES[:STAGE_NAMES.index("deploy")])


def was_sent(result: dict) -> bool:
    """Whether a batch's per-device *result* sent its program (C1540): a program in hand, not
    refused, and not stopped at a stage before the send. Never attempted, found changed since
    its capture (`deploy.SKIPPED_DRIFTED`) and stopped before the send are not sent. The one
    answer: the receipt's ``sent`` and the paired deploy's ends never sent (C1967)."""
    return (bool(result.get("commands")) and result.get("outcome") != "refused"
            and result.get("stage") not in stages_before_send())


def intent_commits(list_name: str, hosts: list) -> dict:
    """``{host: commit}``: each device's newest commit of its committed intent
    (``host_vars/<host>.yml``) now, the intent a deploy renders at apply (C1775); a device whose
    commit cannot be read is absent (its receipt says "not read", never a guess)."""
    from modules.nsot import listref, repo as R

    out = {}
    if not listref.exists(list_name):              # resolve() would create its folder
        return out
    try:
        repo = listref.resolve(list_name).repo_dir
    except Exception as exc:                            # noqa: BLE001 (said by the receipt)
        log.warning("receipts: %s's repository could not be resolved: %s", list_name, exc)
        return out
    for host in sorted({h for h in hosts if h}):
        rc, sha, _err = R.git(repo, "log", "-1", "--format=%H", "--",
                              f"host_vars/{host}.yml")
        sha = (sha or "").strip()
        if rc == 0 and re.fullmatch(r"[0-9a-f]{40}", sha):
            out[host] = sha
    return out


def rows_for(report: dict, *, list_name: str, action: str, actor: str,
             actor_kind: str, confirmations: dict = None,
             command_hashes: dict = None, source_ref: str = "", scope: str = "") -> list:
    """One receipt row per device in *report* (sent, failed or refused)."""
    from modules.redact import redact_text

    confirmations = confirmations or {}
    command_hashes = command_hashes or {}
    golden = report.get("golden") or {}
    golden_devices = (set(golden.get("devices") or [])
                      - {r.get("device") for r in golden.get("refused") or []})
    batch_id = golden.get("batch_id", "")
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # C1775: the intent commit a deploy rendered (a restore or re-apply sends a golden: None).
    intent = (intent_commits(list_name, [r.get("device", "") for r in
                                         report.get("results") or []])
              if action == "deploy" else {})
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
            **({"scope": scope} if scope else {}),
            "outcome": result.get("outcome", ""),
            "stage": result.get("stage", ""),
            "reason": redact_text(result.get("reason", "") or ""),
            # C1540: a run that stopped at a stage before the send sent nothing, its program
            # in hand or not (a router's failed at pre_snapshot read "It received 8 line(s)",
            # Lab 9).
            "sent": was_sent(result),
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
            # Mode B: each line selected for removal, by ID, masked like the
            # program. Its reason is in `authorised`, keyed by the removal line.
            "removals": [{"id": r.get("id", ""), "chain": [redact_text(c) for c in r.get("chain") or []],
                          "line": redact_text(r.get("line", ""))}
                         for r in (result.get("removals") or [])],
            # What the person declared verify should expect (C506 phase 3), each with its
            # reason, in the hash: testimony, masked like the authorisations' reasons.
            "declared": [dict(d, reason=redact_text(d.get("reason", "")))
                         for d in (result.get("declared") or [])],
            # The capture guard ACCEPTED these device-only lines as new hardware (C1383): an
            # interface the capture lacked, its block the platform's measured default, which
            # the program configured. Each interface with its lines, masked like the program.
            "new_hardware": [{"interface": n.get("interface", ""),
                              "lines": [redact_text(x) for x in n.get("lines") or []]}
                             for n in (result.get("new_hardware") or [])],
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
            "saved_startup": _saved_startup(result),
            "golden_commit": golden.get("commit", "") if host in golden_devices else "",
            # The intent it deployed (C1775): its commit, "" when it could not be read, None
            # for a run that deploys no intent; a row from before C1775 has no key at all.
            "intent_commit": intent.get(host, "") if action == "deploy" else None,
            "commit_state": (COMMITTED if golden.get("commit") and host in golden_devices
                             else NO_GOLDEN),
            "second_reading": dict(SECOND_READING_NOT_BUILT),
            "follow_up": dict(FOLLOW_UP_NOT_BUILT),
            # The paired deploy (C1908, C1909): the link this device is one end of, the link's
            # verify, and why this end was rolled back when its far end or the link failed.
            # Only on a pair's rows; a row without it is a single device's.
            **({"pair": _pair_record(result["pair"])} if result.get("pair") else {}),
        })
    return rows


def _pair_record(pair: dict) -> dict:
    """A paired deploy's facts on one end's receipt, its words masked like the reason."""
    from modules.redact import redact_text

    return {"link": pair.get("link", ""), "end": pair.get("end"),
            "verify": pair.get("verify", ""),
            "verify_words": redact_text(pair.get("verify_words", "") or ""),
            "rolled_back_for": redact_text(pair.get("rolled_back_for", "") or ""),
            "checks": [{"family": c.get("family", ""), "state": c.get("state", ""),
                        "words": redact_text(c.get("words", "") or "")}
                       for c in pair.get("checks") or []]}


def pending_row(result: dict, *, list_name: str, action: str, actor: str, actor_kind: str,
                confirmations: dict = None, command_hashes: dict = None,
                source_ref: str = "", run_id: str = "", scope: str = "") -> dict:
    """The row for ONE device as it finishes, before the batch's commit: `rows_for`'s row
    with ``commit_state: pending`` and no commit. *run_id* names the batch run it is part of
    (the commit's own batch id does not exist yet)."""
    (row,) = rows_for({"results": [result], "golden": {}}, list_name=list_name,
                      action=action, actor=actor, actor_kind=actor_kind,
                      confirmations=confirmations, command_hashes=command_hashes,
                      source_ref=source_ref, scope=scope)
    row.update(commit_state=PENDING, golden_commit="", run_id=run_id)
    return row


def completion(row: dict, pending_id: str) -> dict:
    """The line that fills in a pending row's commit, from the final *row*."""
    return {"completes": pending_id,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "commit_state": row.get("commit_state", NO_GOLDEN),
            "golden_commit": row.get("golden_commit", ""),
            "batch_id": row.get("batch_id", "")}


def _merged(lines: list) -> list:
    """Rows in file order, each completion applied to the row it names. A row written
    before commit states existed is final: its state is derived from its commit."""
    rows, by_id = [], {}
    for line in lines:
        if "completes" in line:
            target = by_id.get(line["completes"])
            if target is None:
                log.error("receipts: a completion names %s, which no row has",
                          line["completes"])
                continue
            target.update(commit_state=line.get("commit_state", NO_GOLDEN),
                          golden_commit=line.get("golden_commit", ""),
                          completed_at=line.get("at", ""))
            if line.get("batch_id"):
                target["batch_id"] = line["batch_id"]
            continue
        line.setdefault("commit_state", COMMITTED if line.get("golden_commit") else NO_GOLDEN)
        by_id[line.get("id")] = line
        rows.append(line)
    return rows


def on_database() -> bool:
    """Whether the receipts are in the records database now (read at each call)."""
    from modules import records_db

    return records_db.backend("receipts") == records_db.POSTGRES


def encode(row: dict) -> str:
    """A line as the file holds it, and as the table's hash is taken of."""
    return json.dumps(row, sort_keys=True)


def files() -> dict:
    """``{network: path}`` for every receipts file that exists, the network being the list's
    folder name: the population a move copies, registered list or not."""
    import glob

    from modules.config import LISTS_DIR

    return {os.path.basename(os.path.dirname(p)): p
            for p in sorted(glob.glob(os.path.join(LISTS_DIR, "*", FILENAME)))}


def file_lines(list_name: str) -> list:
    """The file's non-empty lines, as text, in order; ``[]`` when there is no file. Raises
    when it cannot be read."""
    path = path_for(list_name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [line.rstrip("\n") for line in fh if line.strip()]


def write(list_name: str, rows: list) -> dict:
    """Append *rows*. ``{"ok", "written", "error"}``; never raises, because
    the deploy has already happened and a failed receipt must not read as a
    failed deploy. It is loud instead: logged at ERROR and returned."""
    from modules.config import open_secure

    if not rows:
        return {"ok": True, "written": 0, "error": ""}
    if on_database():
        from modules import records_migrate

        try:
            records_migrate.append_lines(list_name, [encode(r) for r in rows])
        except Exception as exc:               # noqa: BLE001
            log.error("receipts: could not write %d receipt(s) for %s to the records "
                      "database: %s", len(rows), list_name, exc)
            return {"ok": False, "written": 0,
                    "error": "the deploy happened and its receipt could not be written to the "
                             f"records database: {exc}"}
        return {"ok": True, "written": len(rows), "error": ""}
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
    prevent. On the records database, a database that does not answer is
    ``unreadable`` naming why, and a network with no line there is ``absent``.
    """
    try:
        if on_database():
            from modules import records_migrate

            lines = records_migrate.table_lines(list_name)
            if not lines:
                return {"state": "absent", "rows": []}
            rows = _merged(lines)
        else:
            path = path_for(list_name)
            if not os.path.exists(path):
                return {"state": "absent", "rows": []}
            rows = _merged([json.loads(line) for line in file_lines(list_name)])
    except Exception as exc:                   # noqa: BLE001
        return {"state": "unreadable", "rows": [], "error": str(exc)}
    if device:
        rows = [r for r in rows if r.get("device") == device]
    return {"state": "ok", "rows": list(reversed(rows))[:limit]}


def current_rows(list_name: str, rows: list, cut: dict = None) -> list:
    """*rows* without a RETIRED device's receipts (C1334): a receipt names its device by name,
    and one written at or before that name's newest retirement in *list_name* was the retired
    device's, never a new device's of that name. Those stay in the record, read on History;
    the readers that act for the device now (Needs attention's deploy and authorisation rows,
    a preview's prior authorisations) read these. *cut*: `retire.retirements`' answer, read
    here when not given."""
    from modules.nsot import retire

    cut = retire.retirements(list_name) if cut is None else cut
    if not cut:
        return list(rows or [])
    return [r for r in rows or []
            if not retire.before_retirement(cut, r.get("device", ""), r.get("at", ""))]


def _authorisation_counts(rows: list, want=None) -> dict:
    """``{device: {line: {count, first_at, last_at, last_actor, last_reason}}}``
    from receipt rows given NEWEST FIRST: the one counting both readers use
    (a preview asks for one device, Needs attention for all of them)."""
    from modules.nsot import authorisation

    out: dict = {}
    for row in reversed(rows):                         # oldest first
        if row.get("outcome") == "refused" or not row.get("sent"):
            continue
        for a in authorisation.normalise(
                [a if isinstance(a, dict) else {"line": a, "reason": ""}
                 for a in (row.get("authorised") or [])]):
            if want is not None and a["line"] not in want:
                continue
            e = out.setdefault(row.get("device", ""), {}).setdefault(
                a["line"], {"count": 0, "first_at": row.get("at", "")})
            e.update({"count": e["count"] + 1, "last_at": row.get("at", ""),
                      "last_actor": row.get("actor", ""),
                      "last_reason": a["reason"] or "(none recorded: before reasons existed)"})
            # And whether that change was ROLLED BACK, when and why: a line
            # re-selected after a failure is written knowing the old one
            # failed (the operator, 2026-09-29: unblocked, but visible).
            rb = row.get("rollback") or {}
            if rb.get("performed"):
                e.update({"rolled_back_at": row.get("at", ""),
                          "rolled_back_why": row.get("reason") or rb.get("detail")
                          or "no reason recorded"})
    return out


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
    got = read(list_name, device=device, limit=10 ** 6)
    if got["state"] != "ok":
        return {"state": got["state"], "lines": {}}
    want = set(lines) if lines is not None else None
    # The preview's shape, unchanged: `first_at` is the page's, and a key the
    # preview carries and does not draw would be a new undrawn field. A retired device's
    # authorisations are not a new device's of the name (C1334).
    rows = current_rows(list_name, got["rows"])
    return {"state": "ok",
            "lines": {k: {f: v for f, v in e.items() if f != "first_at"}
                      for k, e in _authorisation_counts(rows, want).get(device, {}).items()}}


def authorisations_by_device(list_name: str) -> dict:
    """Every device's authorisation counts, from ONE read of the receipts:
    ``{"state", "error", "devices": {device: {line: {...}}}}`` (7.2's
    repeated-authorisation row). Absent and unreadable stay different."""
    got = read(list_name, limit=10 ** 6)
    if got["state"] != "ok":
        return {"state": got["state"], "error": got.get("error", ""), "devices": {}}
    return {"state": "ok", "error": "",
            "devices": _authorisation_counts(current_rows(list_name, got["rows"]))}
