"""Every per-device record, read into the device page's History tab (C359; NSOT_PLAN 1c's one
timeline, extended to every operation).

Persist's first real run on v2 was correct, and its record (the rotation record job health
reads) appeared nowhere a person looks later: History read golden commits, intent commits,
deploy receipts and restarts only. Here is ONE registry, `SOURCES`, of the stores that hold a
record about one device; `device_page.history()` draws every source in it, each record as one
line (when, what, who, its result) that opens its full record. Each operation that writes such
a record declares which source reads it (`operation_stages.HISTORY`), so a new operation with
no reader fails the suite.

A source is ``fn(ref, dev, limit) -> {"events", "errors", "cut"}``. An event is
``{"at", "kind", "what", "who", "detail", "sha", "outcome", "marks", "record"}``, *record*
being ``[(label, value)]``, the full record drawn where the line expands. A store that
cannot be read is an ERROR said on the tab, never a shorter timeline. Reads only: git, the
stores' files, nothing from a device.
"""

import calendar
import logging
import time

log = logging.getLogger(__name__)


def iso(value) -> str:
    """Any stored time as ISO UTC: epoch floats (the break-glass log, interrupted holds), ISO
    with an offset, and the approval queue's local naive "%Y-%m-%d %H:%M:%S"."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(value)))
    text = str(value)
    if len(text) == 19 and text[10] == " ":
        try:
            return time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                 time.gmtime(time.mktime(time.strptime(text, "%Y-%m-%d %H:%M:%S"))))
        except ValueError:
            return text
    return text


def _event(at, kind, what, *, who="", detail="", sha="", outcome="", marks=None, record=None):
    return {"at": iso(at), "kind": kind, "what": what, "who": who or "", "detail": detail,
            "sha": sha or "", "outcome": outcome, "marks": list(marks or []),
            "record": [(k, v) for k, v in (record or []) if v not in (None, "", [], {})]}


def _out(events=None, errors=None, cut=None):
    return {"events": events or [], "errors": errors or [], "cut": cut or []}


# ---------------------------------------------------------------------------- git records

def golden(ref, dev, limit):
    from modules.nsot import repo as R
    host = dev.get("hostname", "")
    try:
        rows = R.golden_history(ref.repo_dir, host, limit=limit)
    except Exception as exc:                          # noqa: BLE001
        return _out(errors=[f"the golden history could not be read: {exc}"])
    events = []
    for g in rows:
        exc_reason = (g.get("exception") or {}).get("reason", "")
        e = _event(g["timestamp"], "golden",
                   f"Golden recorded ({g['source'] or 'no Source: trailer'})",
                   who=g["actor"], detail=g["subject"], sha=g["sha"],
                   marks=["record known wrong"] if exc_reason else [],
                   record=[("Commit", g["sha"][:12]), ("Source", g["source"]),
                           ("By", g["actor"])])
        e["exception"] = exc_reason
        events.append(e)
    return _out(events, cut=[f"the golden history's newest {limit}"] if len(rows) >= limit else [])


def intent(ref, dev, limit):
    from modules.nsot import hostvars
    host = dev.get("hostname", "")
    try:
        rows = hostvars.intent_commits(ref.repo_dir, host, limit=limit)
    except Exception as exc:                          # noqa: BLE001
        return _out(errors=[f"the intent history could not be read: {exc}"])
    events = [_event(c["date"], "intent",
                     "Intent committed" + (f" ({c['source']})" if c.get("source") else ""),
                     who=c.get("actor", ""), detail=c["subject"], sha=c["sha"],
                     record=[("Commit", c["sha"][:12]), ("Source", c.get("source")),
                             ("By", c.get("actor"))])
              for c in rows]
    return _out(events, cut=[f"the intent history's newest {limit}"] if len(rows) >= limit else [])


#: A save's Source: words, for a measurement that changed no golden.
_FIELD, _RECORD = "\x1f", "\x1e"


def measured(ref, dev, limit):
    """A save that READ the device and changed no golden (a capture that found it unchanged, a
    Save All that measured it): its commit names it in `Devices-Measured:` and touches no
    `golden/<device>` file, so the golden history alone never shows it."""
    from modules.nsot import repo as R
    host = dev.get("hostname", "")
    fmt = _FIELD.join(["%H", "%cI", "%(trailers:key=Source,valueonly)",
                       "%(trailers:key=Actor,valueonly)",
                       "%(trailers:key=Devices,valueonly,separator=%x2c)",
                       "%(trailers:key=Device-Name,valueonly,separator=%x2c)",
                       "%(trailers:key=Devices-Measured,valueonly,separator=%x2c)",
                       "%(trailers:key=Baseline,valueonly)", "%s"]) + _RECORD
    rc, out, err = R.git(ref.repo_dir, "log", f"-n{limit * 4}", "--grep=^Devices-Measured: ",
                         f"--format={fmt}")
    if rc != 0:
        return _out(errors=[f"the saves that measured {host} could not be read: "
                            f"{(err or out).strip()}"])
    events = []
    for rec in out.split(_RECORD):
        parts = rec.strip("\n").split(_FIELD)
        if len(parts) < 9:
            continue
        sha, at, source, actor, devices, names, measured_, baseline, subject = parts[:9]
        split = lambda s: {x.strip() for x in s.split(",") if x.strip()}    # noqa: E731
        if host not in split(measured_) or host in (split(devices) | split(names)):
            continue
        events.append(_event(at, "measured", f"Measured, golden unchanged ({source.strip()})",
                             who=actor.strip(), detail=subject, sha=sha,
                             record=[("Commit", sha[:12]), ("Source", source.strip()),
                                     ("Baseline", baseline.strip()), ("By", actor.strip())]))
        if len(events) >= limit:
            break
    return _out(events)


# ---------------------------------------------------------------------------- the stores

def receipts(ref, dev, limit):
    from modules.nsot import receipts as R
    host = dev.get("hostname", "")
    got = R.read(ref.name, device=host, limit=limit)
    if got["state"] == "unreadable":
        return _out(errors=[f"the deploy receipts could not be read: {got.get('error', '')}"])
    verbs = {"deploy": "Deployed", "restore": "Restored", "reapply": "Re-applied"}
    events = []
    for r in got.get("rows") or []:
        pending = R.is_pending(r)
        removals = r.get("removals") or []
        rb = r.get("rollback") or {}
        e = _event(r.get("at", ""), "receipt",
                   f"{verbs.get(r.get('action', ''), 'Changed')}: "
                   f"{r.get('outcome', '?').replace('_', ' ')}"
                   + (f", {R.PENDING_WORDS}" if pending else ""),
                   who=r.get("actor", ""),
                   detail=(f"{r.get('program_lines', 0)} line(s) sent"
                           + (f"; {len(removals)} removed (Mode B)" if removals else "")
                           + (f"; {r['reason']}" if r.get("reason") else "")),
                   sha=r.get("golden_commit", ""), outcome=r.get("outcome", ""),
                   marks=(["Mode B"] if removals else []) + (["rolled back"] if rb.get("performed") else []),
                   record=[("Program", f"{r.get('program_lines', 0)} line(s), hash "
                                       f"{(r.get('program_hash') or '')[:12]}"),
                           ("Matches what was confirmed", {True: "yes", False: "NO"}.get(
                               r.get("matches_confirmed"))),
                           ("Removed (Mode B)", "; ".join(x.get("line", "") for x in removals)),
                           ("Authorised", "; ".join(f"{a.get('line')}: {a.get('reason')}"
                                                    for a in r.get("authorised") or [])),
                           ("Rollback", rb.get("state") if rb.get("performed") else ""),
                           ("Commit", (r.get("golden_commit") or "")[:12]),
                           ("Source ref", r.get("source_ref"))])
        e["pending"] = pending
        events.append(e)
    return _out(events, cut=[f"the receipts' newest {limit}"] if len(events) >= limit else [])


def restarts(ref, dev, limit):
    """Every restart, planned or not (the operator, 2026-10-02), with a person's acknowledgement
    of an unplanned one: it stays unplanned, marked acknowledged, by whom and why."""
    from modules import acknowledgements as _acks
    from modules import restarts as _restarts
    host = dev.get("hostname", "")
    errors = []
    rs = _restarts.events(device=host, list_name=ref.name)
    if rs["state"] == "unreadable":
        errors.append(f"the restart record could not be read: {rs.get('error', '')}")
    try:
        rows = _restarts.judged(rs["rows"][:limit], _restarts.planned_rows())
    except RuntimeError as exc:
        errors.append(str(exc))
        rows = rs["rows"][:limit]
    acks = _acks.read()
    if acks["state"] == "unreadable" and any(not r.get("planned") for r in rows):
        errors.append(f"the acknowledgement record could not be read: {acks.get('error', '')}")
    events = []
    for r in rows:
        ack = None if r.get("planned") else _acks.covering(
            f"restarts:{r.get('list', '')}|{r.get('device', '')}|{r.get('at', '')}",
            r.get("at", ""), acks["rows"])
        e = _event(r.get("at", ""), "restart",
                   "Restarted as planned" if r.get("planned") else "Restarted unexpectedly",
                   who=r.get("planned_by", "") or (ack or {}).get("by", ""),
                   detail=(("reason: " + r["reason"]) if r.get("reason") else
                           f"reason not read ({r.get('reason_error') or 'no answer'})")
                   + (f"; crash file {r['crash_file']}" if r.get("crash_file") else "")
                   + (f"; planned: {r['planned_why']}" if r.get("planned_why") else ""),
                   outcome="crash" if r.get("crash_file") else
                   ("planned" if r.get("planned") else "unplanned"),
                   marks=[m for m, on in (("corrected", r.get("planned_correction")),
                                          ("acknowledged", ack),
                                          ("crash file", r.get("crash_file"))) if on])
        e["acknowledged"] = ({"by": ack.get("by"), "why": ack.get("why"), "at": ack.get("at")}
                             if ack else None)
        e["correction"] = r.get("planned_correction", "")
        events.append(e)
    return _out(events, errors,
                [f"the restarts' newest {limit}"] if len(rs["rows"]) > limit else [])


def restart_windows(ref, dev, limit):
    """Each planned-restart window declared for this device (or the whole list), whether or
    not a restart came: a reload that failed is a window with no restart."""
    from modules import restarts as _restarts
    host = dev.get("hostname", "")
    try:
        rows = _restarts.planned_rows()
    except RuntimeError as exc:
        return _out(errors=[str(exc)])
    events = []
    for w in reversed(rows):
        devices = w.get("devices") or []
        if w.get("list") not in (ref.name, None, "") or not (host in devices or "*" in devices):
            continue
        events.append(_event(w.get("recorded_at") or w.get("from"), "window",
                             "Planned-restart window declared"
                             + (" (a correction)" if w.get("correction") else ""),
                             who=w.get("by", ""), detail=w.get("why", ""),
                             marks=["correction"] if w.get("correction") else [],
                             record=[("From", iso(w.get("from"))), ("Until", iso(w.get("until"))),
                                     ("Devices", ", ".join(devices)), ("Via", w.get("via")),
                                     ("Correction", w.get("correction"))]))
        if len(events) >= limit:
            break
    return _out(events)


def rotation(ref, dev, limit):
    """Persist, rotate and recover: the rotation record job health's row reads (C359: a
    persist was readable now and not later). Its rows name the device and no list."""
    from modules.nsot import credential_rotation as cr
    host = dev.get("hostname", "")
    try:
        rows = [r for r in cr.rotation_records() if r.get("device") == host]
    except OSError as exc:
        return _out(errors=[f"the rotation record could not be read: {exc}"])
    words = {"persist": "Persisted", "rotate": "Credential rotated", "recover": "Rotation recovered"}
    events = []
    for r in reversed(rows[-limit:]):
        state = r.get("state", "")
        failed = r.get("failed_stage", "")
        events.append(_event(r.get("at", ""), "rotation",
                             f"{words.get(r.get('phase'), r.get('phase', 'Rotation'))}: "
                             f"{state.replace('_', ' ') or 'no state recorded'}",
                             who=r.get("actor", ""),
                             detail=(f"stopped at {failed}" if failed else "every stage passed")
                             + f"; via {r.get('via', 'not named')}",
                             outcome=state, marks=["failed"] if failed else [],
                             record=[("Phase", r.get("phase")), ("State", state), ("Via", r.get("via"))]
                             + [(s.get("name", "?"), ("ok" if s.get("ok") else "FAILED")
                                 + (f": {s['reason']}" if s.get("reason") else ""))
                                for s in r.get("stages") or []]))
    return _out(events, cut=[f"the rotation record's newest {limit}"] if len(rows) > limit else [])


def retries(ref, dev, limit):
    """Each authorised retry of a change that was rolled back (gitignored, so no commit)."""
    from modules.nsot import hostvars
    host = dev.get("hostname", "")
    rows = [r for r in hostvars.retry_log(ref.repo_dir) if r.get("device") == host]
    return _out([_event(r.get("at", ""), "retry", "Retry authorised after a rollback",
                        who=r.get("actor", ""), detail=r.get("reason", ""),
                        record=[("Reason", r.get("reason")), ("The rollback it lifted", r.get("note"))])
                 for r in reversed(rows[-limit:])])


def onboarding(ref, dev, limit):
    """Onboarding's and adopt's runs (create, verify, abandon, adopt), from their run record."""
    from modules.nsot import onboard
    host = dev.get("hostname", "")
    got = onboard.read_runs(ref.repo_dir)
    if got["state"] == "unreadable":
        return _out(errors=[f"the onboarding runs could not be read: {got.get('error', '')}"])
    rows = [r for r in got["rows"] if r.get("device") == host][:limit]
    return _out([_event(r.get("at", ""), "onboarding",
                        f"{'Adopted' if r.get('kind') == 'adopt' else 'Onboarding ' + str(r.get('kind', 'run'))}"
                        f": {'done' if r.get('ok') else 'stopped'}",
                        who=r.get("actor", ""), detail=r.get("reason") or r.get("error") or "",
                        sha=r.get("golden_commit", ""), outcome="ok" if r.get("ok") else "failed",
                        marks=[] if r.get("ok") else ["stopped"],
                        record=[("Kind", r.get("kind")), ("Promoted", r.get("promoted")),
                                ("Golden commit", (r.get("golden_commit") or "")[:12]),
                                ("Steps", "; ".join(f"{s.get('name', s) if isinstance(s, dict) else s}"
                                                    for s in r.get("steps") or [])),
                                ("Remaining", "; ".join(str(x) for x in r.get("remaining") or []))])
                 for r in rows])


def acknowledgements(ref, dev, limit):
    """A person's acknowledgement of a row about this device other than a restart (a restart's
    is drawn on the restart): a repeated authorisation, by its row id."""
    from modules import acknowledgements as _acks
    host = dev.get("hostname", "")
    got = _acks.read()
    if got["state"] == "unreadable":
        return _out(errors=[f"the acknowledgement record could not be read: {got.get('error', '')}"])
    prefix = f"authorisations:{ref.name}:{host}:"
    rows = [r for r in got["rows"] if str(r.get("row", "")).startswith(prefix)][-limit:]
    return _out([_event(r.get("at", ""), "acknowledged",
                        f"Acknowledged: {r.get('what') or r.get('kind') or 'a row'}",
                        who=r.get("by", ""), detail=r.get("why", ""),
                        record=[("Row", r.get("row")), ("Reason", r.get("why")),
                                ("Verified", r.get("verified"))])
                 for r in reversed(rows)])


def breakglass(ref, dev, limit):
    """Each break-glass export that sealed this device's credential."""
    import json
    import os
    from modules import breakglass as bg
    from modules import config
    host = dev.get("hostname", "")
    path = os.path.join(config.DATA_DIR, bg.EXPORT_LOG)
    if not os.path.exists(path):
        return _out()
    try:
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    except (OSError, ValueError) as exc:
        return _out(errors=[f"the break-glass export log could not be read: {exc}"])
    rows = [r for r in rows if r.get("list") == ref.name and host in (r.get("devices") or {})]
    return _out([_event(r.get("at"), "breakglass", "Break-glass record exported (holds this device)",
                        who=r.get("actor", ""), detail=f"via {r.get('via', '?')}",
                        record=[("Key fingerprint", r.get("key_fingerprint")),
                                ("Written to", r.get("path")), ("Via", r.get("via"))])
                 for r in reversed(rows[-limit:])])


def interrupted(ref, dev, limit):
    """An operation whose process ended while it held this device (CONCURRENCY_AUDIT R5)."""
    from modules.nsot import device_ops
    host = dev.get("hostname", "")
    try:
        rows = [r for r in device_ops.interrupted(ref.name) if r.get("device") == host]
    except OSError as exc:
        return _out(errors=[f"the device holds could not be read: {exc}"])
    return _out([_event(r.get("started"), "interrupted",
                        f"A {r.get('operation', 'operation')} was cut off: its process ended",
                        who=r.get("actor", ""),
                        detail=f"last step {(r.get('progress') or {}).get('step') or 'started'}",
                        outcome="interrupted", marks=["did not finish"],
                        record=[("Operation", r.get("operation")), ("Process", r.get("pid")),
                                ("Last step", (r.get("progress") or {}).get("step")),
                                ("Found", iso(r.get("found_at")))])
                 for r in rows[:limit]])


def freshness(ref, dev, limit):
    """Each authorisation to deploy past the freshness gate, with its reason."""
    from modules.nsot import freshness as fr
    host = dev.get("hostname", "")
    try:
        rows = [a for a in fr.authorisations(ref.name, include_expired=True)
                if a.get("device") == host]
    except Exception as exc:                          # noqa: BLE001
        return _out(errors=[f"the freshness authorisations could not be read: {exc}"])
    return _out([_event(a.get("at", ""), "freshness", "Freshness gate authorised",
                        who=a.get("actor", ""), detail=a.get("reason", ""),
                        record=[("Reason", a.get("reason")), ("Expires", iso(a.get("expires_at"))),
                                ("Fingerprint", a.get("fingerprint"))])
                 for a in rows[-limit:]])


def approvals(ref, dev, limit):
    """Each approval-queue item about this device that a person or a capture resolved."""
    from modules import approval_queue
    from modules.filestore import StoreUnreadable
    host = dev.get("hostname", "")
    try:
        rows = approval_queue.read_list(ref)
    except StoreUnreadable as exc:
        return _out(errors=[str(exc)])
    rows = [r for r in rows if r.get("device_hostname") == host and r.get("resolved_at")]
    return _out([_event(r.get("resolved_at"), "approval",
                        f"{str(r.get('action_type', 'item')).replace('_', ' ').capitalize()}: "
                        f"{r.get('status', '?')}",
                        who=r.get("resolved_by", ""), detail=str(r.get("context") or ""),
                        outcome=r.get("status", ""),
                        record=[("Raised", iso(r.get("created_at"))), ("Status", r.get("status")),
                                ("Item", r.get("id"))])
                 for r in rows[-limit:]])


#: Every store holding a record about one device, in the order History asks them. A source
#: absent here is read nowhere; `operation_stages.HISTORY` names one per operation.
SOURCES = {
    "golden": golden, "intent": intent, "measured": measured, "receipts": receipts,
    "restarts": restarts, "restart_windows": restart_windows, "rotation": rotation,
    "retries": retries, "onboarding": onboarding, "acknowledgements": acknowledgements,
    "breakglass": breakglass, "interrupted": interrupted, "freshness": freshness,
    "approvals": approvals,
}
