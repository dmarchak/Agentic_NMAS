"""History as ONE timeline (C369; board D, signed off 2026-10-03; NSOT_PLAN 1c's one timeline,
extended to every operation by C359).

The sidebar's History read git commits only, and a device's History tab read every per-device
record: two readers of one history, so the place a person looks for "what happened recently"
lacked most of it. Here is ONE reader, `timeline()`, behind both: every record about a device,
across every device, and the records that belong to no one device (a commit to the profile, a
Save All's baseline decision, an update of the app). The History page draws it filtered by
device, person, kind and time; a device's History tab IS it filtered to the device, the same
rows by the same code (tests/test_history_one_timeline.py holds the two to the same rows).

A source is ``fn(ctx) -> {"events", "errors", "cut"}``, *ctx* being ``{"ref", "device",
"limit", "since", "members"}``: *device* "" for every device; *since* an epoch or None for all
time; *members* the list's device names, for a store whose rows name no list. Each source
reads its store ONCE for the request, whatever the number of devices (the enterprise-scale
rule); a git source passes a device's paths to git itself. An event is ``{"at", "kind",
"what", "devices", "who", "detail", "sha", "outcome", "marks", "record"}``: *devices* the
devices it is about, ``[]`` for the fleet's own records and ``["*"]`` for every device of the
list; *record* ``[(label, value)]``, the full record drawn where the line expands. A store that
cannot be read is an ERROR said on the page, never a shorter timeline. Reads only: git, the
stores' files, nothing from a device.
"""

import logging
import re
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


def epoch(value) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _event(at, kind, what, devices, *, who="", detail="", sha="", outcome="", marks=None,
           record=None):
    return {"at": iso(at), "kind": kind, "what": what,
            "devices": sorted({d for d in devices if d}), "who": who or "", "detail": detail,
            "sha": sha or "", "outcome": outcome, "marks": list(marks or []),
            "record": [(k, v) for k, v in (record or []) if v not in (None, "", [], {})]}


def _out(events=None, errors=None, cut=None):
    return {"events": events or [], "errors": errors or [], "cut": cut or []}


def about(event: dict, device: str) -> bool:
    """Whether *event* is about *device*: named, or one for every device of the list."""
    devices = event.get("devices") or []
    return device in devices or "*" in devices


def _mine(ctx, device: str) -> bool:
    """A row about *device* belongs to this read: the device asked for, or any of the list's."""
    if ctx["device"]:
        return device == ctx["device"]
    return ctx["members"] is None or device in ctx["members"]


def _recent(ctx, at) -> bool:
    return ctx["since"] is None or epoch(at) >= ctx["since"]


# ---------------------------------------------------------------------------- git records

_FIELD, _RECORD, _END = "\x1f", "\x1e", "\x1d"
_HEAD = _FIELD.join(["%H", "%cI", "%(trailers:key=Source,valueonly)",
                     "%(trailers:key=Actor,valueonly)",
                     "%(trailers:key=Devices,valueonly,separator=%x2c)",
                     "%(trailers:key=Device-Name,valueonly,separator=%x2c)",
                     "%(trailers:key=Devices-Measured,valueonly,separator=%x2c)",
                     "%(trailers:key=Baseline,valueonly)", "%s",
                     "%(trailers:key=Actor-Verified,valueonly)", "%D"])
_PATH = re.compile(r"^(golden|host_vars)/([^/]+)\.(cfg|yml)$")


def _log(ctx, paths, *extra, follow=False, count=None):
    """ONE bounded `git log` with each commit's files: ``(rows, error)``, newest first. Each row
    is ``{"sha", "at", "source", "actor", "devices_trailer", "measured", "baseline",
    "subject", "files": [(status, path, old_path)]}``."""
    from modules.nsot import repo as R

    count = count or ctx["limit"] + 1
    since = [f"--since=@{int(ctx['since'])}"] if ctx["since"] is not None else []
    if follow:
        # ONE device's file followed across renames, as `golden_history` did; git refuses
        # --follow with --full-diff (2.53), so a second bounded read takes those commits' whole
        # file lists, which the fleet's read sees too (the two views must agree).
        rc, out, err = R.git(ctx["ref"].repo_dir, "log", f"--max-count={count}", "--follow",
                             "--format=%H", *since, *extra, "--", *paths)
        if rc != 0:
            return [], (err or out or "").strip()
        shas = [s for s in (out or "").split() if re.fullmatch(r"[0-9a-f]{40}", s)]
        if not shas:
            return [], ""
        rc, out, err = R.git(ctx["ref"].repo_dir, "log", "--no-walk", "-M", "--name-status",
                             f"--format={_RECORD}{_HEAD}{_END}", *shas)
    else:
        rc, out, err = R.git(ctx["ref"].repo_dir, "log", f"--max-count={count}", "-M",
                             "--name-status", f"--format={_RECORD}{_HEAD}{_END}", *since, *extra,
                             *(["--", *paths] if paths else []))
    if rc != 0:
        return [], (err or out or "").strip()
    rows = []
    for chunk in (out or "").split(_RECORD):
        if not chunk.strip():
            continue
        # A trailer's value ends with a newline, so the header ends with its own separator.
        head, _sep, rest = chunk.partition(_END)
        parts = [p.strip() for p in head.split(_FIELD)]
        if len(parts) < 11:
            continue
        files = []
        for line in rest.splitlines():
            cols = line.split("\t")
            if len(cols) >= 2:
                files.append((cols[0], cols[-1], cols[1] if len(cols) == 3 else ""))
        split = lambda s: {x.strip() for x in s.split(",") if x.strip()}    # noqa: E731
        rows.append({"sha": parts[0], "at": parts[1], "source": parts[2].strip(),
                     "actor": parts[3].strip(),
                     "devices_trailer": split(parts[4]) | split(parts[5]),
                     "measured": split(parts[6]), "baseline": parts[7].strip(),
                     "subject": parts[8], "files": files,
                     "who": _who(parts[3].strip(), parts[9].strip()),
                     "tags": [d.strip()[len("tag: "):] for d in parts[10].split(",")
                              if d.strip().startswith("tag: ")]})
    return rows, ""


# ---------------------------------------------------------------------------- a commit's words
# (from modules/fleet_history.py, folded in with C369: one module owns History)

#: How an ``Actor-Verified:`` value is said beside the actor.
VERIFIED_WORDS = {"access": "", "host-shell": "host login, not verified",
                  "none": "not verified", "": "before verification was recorded"}


def actor_words(actor: str, verified: str) -> dict:
    """``{"who", "how"}``: the actor, and how it was established."""
    return {"who": actor or "nobody recorded", "how": VERIFIED_WORDS.get(verified, verified)}


def baseline_words(decision: str, tags: list) -> dict:
    """``{"state", "words", "tag"}`` for the Baseline column: earned (its tag),
    not taken (a deploy that did not cover the network), denied (and why),
    unrecorded (a tag on a commit that recorded nothing), or none."""
    tag = next((t for t in tags if t.startswith("baseline/")), "")
    d = (decision or "").strip()
    if d == "earned":
        return {"state": "earned", "words": "earned", "tag": tag}
    if d.startswith("denied"):
        why = d.partition(":")[2].strip()
        m = re.match(r"(\d+) device\(s\) not targeted", why)
        if m:
            return {"state": "not_taken", "words": f"not taken: {m.group(1)} not targeted",
                    "tag": tag}
        m = re.search(r"\(([^)]*skipped)\)", why)
        return {"state": "denied", "words": "denied: " + (m.group(1) if m else why)[:80],
                "tag": tag}
    if tag:
        return {"state": "unrecorded", "words": "not recorded", "tag": tag}
    return {"state": "", "words": "", "tag": ""}


def diff(repo: str, sha: str, max_lines: int = 400, git=None) -> dict:
    """One commit's change, MASKED (C77), for the row a person opens:
    ``{"ok", "stat", "text", "cut", "error"}``."""
    from modules.nsot import repo as R
    from modules.redact import redact_text

    git = git or R.git
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha or ""):
        return {"ok": False, "error": f"{sha!r} is not a commit id", "stat": "", "text": "",
                "cut": False}
    rc, out, err = git(repo, "show", "--format=", "--stat", "--patch", sha)
    if rc != 0:
        return {"ok": False, "error": f"the commit could not be read: {(err or '').strip()}",
                "stat": "", "text": "", "cut": False}
    lines = redact_text(out or "").splitlines()
    return {"ok": True, "error": "", "text": "\n".join(lines[:max_lines]),
            "cut": len(lines) > max_lines, "stat": ""}


def _who(actor: str, verified: str) -> str:
    """The actor, with how it was established when that is not a verified sign-in: "alex (host
    login, not verified)". The line draws the name; the detail draws it whole."""
    w = actor_words(actor, verified)
    return w["who"] + (f" ({w['how']})" if w["how"] else "")


def _known_wrong(sha: str) -> str:
    """Why a commit's record is known to be wrong (record_exceptions), or "". The table's
    reason is `why` (C363: reading `reason`, which no exception has, drew none)."""
    from modules.nsot.record_exceptions import exception_for
    exc = exception_for(sha) or {}
    return exc.get("why", "") if isinstance(exc, dict) else ""


def _from_commit(r, kind, what, devices, **kw):
    """A commit's event: its person and how established, and a known-wrong record marked."""
    why = _known_wrong(r["sha"])
    e = _event(r["at"], kind, what, devices, who=r["who"], detail=kw.pop("detail", r["subject"]),
               sha=r["sha"], marks=["record known wrong"] if why else [], **kw)
    if why:
        e["exception"] = why
    return e


def _renames(ctx, folder):
    """``([(epoch, sha, old, new)], error)``: every rename under *folder*, newest first, in ONE read.
    Both views attribute a commit by these, so a device's view (which follows one file and never
    sees another device's rename) and the fleet's name the same devices."""
    from modules.nsot import repo as R

    rc, out, err = R.git(ctx["ref"].repo_dir, "log", "-M", "--diff-filter=R", "--name-status",
                         f"--format={_RECORD}%ct %H", "--", f"{folder}/")
    if rc != 0:
        return [], (err or out or "").strip()
    found = []
    for chunk in (out or "").split(_RECORD):
        lines = [l for l in chunk.strip().splitlines() if l.strip()]
        head = lines[0].split() if lines else []
        if len(head) != 2 or not head[0].isdigit():
            continue
        for line in lines[1:]:
            cols = line.split("\t")
            o, n = (_PATH.match(cols[1]), _PATH.match(cols[2])) if len(cols) == 3 else (None, None)
            if o and n and o.group(1) == n.group(1) == folder:
                found.append((int(head[0]), head[1], o.group(2), n.group(2)))
    return found, ""


def _named(rows, folder, renames):
    """Each row's devices under *folder* (golden, host_vars), by the name each file has NOW: a
    commit older than a rename is attributed to the new name, as `git log --follow` follows one
    device's file (C369: one reader, so a device's view and the fleet's must agree)."""
    for r in rows:
        t = epoch(r["at"])
        names = set()
        for _status, path, _old in r["files"]:
            m = _PATH.match(path)
            if not m or m.group(1) != folder:
                continue
            name = m.group(2)
            for tr, sha, old, new in reversed(renames):   # oldest first
                # Older than the rename: git's time is to the second, so a commit in the same
                # second counts as older unless it is the rename itself.
                if (tr > t or (tr == int(t) and r["sha"] != sha)) and name == old:
                    name = new
            names.add(name)
        r["named"] = names
    return rows


def _commit_source(folder, kind, words):
    def source(ctx):
        ext = "cfg" if folder == "golden" else "yml"
        paths = [f"{folder}/{ctx['device']}.{ext}"] if ctx["device"] else [f"{folder}/"]
        rows, err = _log(ctx, paths, follow=bool(ctx["device"]))
        if err:
            return _out(errors=[f"the {words} history could not be read: {err}"])
        renames, err = _renames(ctx, folder)
        if err:
            return _out(errors=[f"the {words} history's renames could not be read: {err}"])
        rows = _named(rows, folder, renames)
        events = []
        for r in rows[:ctx["limit"]]:
            # A row names EVERY device it is about, and is kept when one is the one asked for:
            # a device's view and the fleet's must be the same rows (C369). --follow only finds
            # the candidates; it also follows a new file into a near-identical OTHER device's
            # history, which the commit's own files then refuse.
            devices = r["named"]
            if not any(_mine(ctx, d) for d in devices):
                continue
            what = (f"Golden recorded ({r['source'] or 'no Source: trailer'})" if kind == "golden"
                    else "Intent committed" + (f" ({r['source']})" if r["source"] else ""))
            events.append(_from_commit(r, kind, what, devices,
                                     record=[("Commit", r["sha"][:12]), ("Source", r["source"]),
                                             ("By", r["who"])]))
        return _out(events, cut=[f"the {words} history's newest {ctx['limit']}"]
                    if len(rows) > ctx["limit"] else [])
    source.__name__ = folder
    return source


_golden = _commit_source("golden", "golden", "golden")
_intent = _commit_source("host_vars", "intent", "intent")


def golden(ctx):
    """Each commit that recorded a golden, naming every device it recorded."""
    return _golden(ctx)


def intent(ctx):
    """Each commit that changed a device's committed intent, naming every device."""
    return _intent(ctx)


def measured(ctx):
    """A save that READ the device and changed no golden (a capture that found it unchanged, a
    Save All that measured it): its commit names it in `Devices-Measured:` and touches no
    `golden/<device>` file, so the golden history alone never shows it."""
    # No pathspec: a measurement that changed no file is an EMPTY commit, which `-- .` skips.
    rows, err = _log(ctx, [], "--grep=^Devices-Measured: ", count=ctx["limit"] * 4)
    if err:
        return _out(errors=[f"the saves that measured devices could not be read: {err}"])
    events = []
    for r in rows:
        devices = r["measured"] - r["devices_trailer"]
        if not any(_mine(ctx, d) for d in devices):
            continue
        events.append(_from_commit(r, "measured", f"Measured, golden unchanged ({r['source']})",
                                 devices,
                                 record=[("Commit", r["sha"][:12]), ("Source", r["source"]),
                                         ("Baseline", r["baseline"]), ("By", r["who"])]))
        if len(events) >= ctx["limit"]:
            break
    return _out(events)


def fleet_commits(ctx):
    """The fleet's own commits: those that touch no device's golden or intent and measured no
    device (the monitoring profile, the templates, an IP SLA policy). About no one device, so a
    device's view has none."""
    if ctx["device"]:
        return _out()
    rows, err = _log(ctx, [".", ":(exclude)golden", ":(exclude)host_vars"])
    if err:
        return _out(errors=[f"the repository's other commits could not be read: {err}"])
    events = [_from_commit(r, "commit", r["subject"], [],
                         detail=f"{len(r['files'])} file(s): "
                                + ", ".join(p for _s, p, _o in r["files"][:6])
                                + (" …" if len(r["files"]) > 6 else ""),
                         record=[("Commit", r["sha"][:12]), ("Source", r["source"]),
                                 ("By", r["who"])])
              for r in rows[:ctx["limit"]] if not r["measured"]]
    return _out(events, cut=[f"the other commits' newest {ctx['limit']}"]
                if len(rows) > ctx["limit"] else [])


def decisions(ctx):
    """A Save All's baseline decision (its commit's `Baseline:` trailer): the fleet's record of
    whether every device was at its intent. About the list, so a device's view has none."""
    if ctx["device"]:
        return _out()
    rows, err = _log(ctx, [], "--grep=^Baseline: ")
    if err:
        return _out(errors=[f"the baseline decisions could not be read: {err}"])
    events = []
    for r in rows[:ctx["limit"]]:
        b = baseline_words(r["baseline"], r["tags"])
        events.append(_from_commit(r, "decision",
                                 f"Baseline {b['words'] or 'recorded'} "
                                 f"({r['source'] or 'no Source: trailer'})", [],
                                 outcome=b["state"],
                                 record=[("Commit", r["sha"][:12]), ("Baseline", r["baseline"]),
                                         ("Tag", b["tag"]),
                                         ("Measured", ", ".join(sorted(r["measured"]))),
                                         ("By", r["who"])]))
    return _out(events)


# ---------------------------------------------------------------------------- the stores

def receipts(ctx):
    from modules.nsot import receipts as R
    got = R.read(ctx["ref"].name, device=ctx["device"], limit=ctx["limit"])
    if got["state"] == "unreadable":
        return _out(errors=[f"the deploy receipts could not be read: {got.get('error', '')}"])
    verbs = {"deploy": "Deployed", "restore": "Restored", "reapply": "Re-applied"}
    events = []
    for r in got.get("rows") or []:
        if not _mine(ctx, r.get("device", "")):
            continue
        pending = R.is_pending(r)
        removals = r.get("removals") or []
        rb = r.get("rollback") or {}
        e = _event(r.get("at", ""), "receipt",
                   f"{verbs.get(r.get('action', ''), 'Changed')}: "
                   f"{r.get('outcome', '?').replace('_', ' ')}"
                   + (f", {R.PENDING_WORDS}" if pending else ""), [r.get("device", "")],
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
    return _out(events, cut=[f"the receipts' newest {ctx['limit']}"]
                if len(got.get("rows") or []) >= ctx["limit"] else [])


def restarts(ctx):
    """Every restart, planned or not (the operator, 2026-10-02), with a person's acknowledgement
    of an unplanned one: it stays unplanned, marked acknowledged, by whom and why."""
    from modules import acknowledgements as _acks
    from modules import restarts as _restarts
    errors = []
    rs = _restarts.events(device=ctx["device"], list_name=ctx["ref"].name)
    if rs["state"] == "unreadable":
        errors.append(f"the restart record could not be read: {rs.get('error', '')}")
    limit = ctx["limit"]
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
        if not _mine(ctx, r.get("device", "")):
            continue
        ack = None if r.get("planned") else _acks.covering(
            f"restarts:{r.get('list', '')}|{r.get('device', '')}|{r.get('at', '')}",
            r.get("at", ""), acks["rows"])
        e = _event(r.get("at", ""), "restart",
                   "Restarted as planned" if r.get("planned") else "Restarted unexpectedly",
                   [r.get("device", "")],
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


def restart_windows(ctx):
    """Each planned-restart window declared for a device (or the whole list), whether or not a
    restart came: a reload that failed is a window with no restart."""
    from modules import restarts as _restarts
    try:
        rows = _restarts.planned_rows()
    except RuntimeError as exc:
        return _out(errors=[str(exc)])
    events = []
    for w in reversed(rows):
        devices = w.get("devices") or []
        if w.get("list") not in (ctx["ref"].name, None, ""):
            continue
        if "*" in devices:
            devices = ["*"]
        elif not any(_mine(ctx, d) for d in devices):
            continue
        events.append(_event(w.get("recorded_at") or w.get("from"), "window",
                             "Planned-restart window declared"
                             + (" (a correction)" if w.get("correction") else ""), devices,
                             who=w.get("by", ""), detail=w.get("why", ""),
                             marks=["correction"] if w.get("correction") else [],
                             record=[("From", iso(w.get("from"))), ("Until", iso(w.get("until"))),
                                     ("Devices", ", ".join(w.get("devices") or [])),
                                     ("Via", w.get("via")), ("Correction", w.get("correction"))]))
        if len(events) >= ctx["limit"]:
            break
    return _out(events)


#: A save's line (the device's own save, C362): its own words, never a rotation's.
SAVE_WORDS = {"persisted": "Persisted: the startup config carries the running credential",
              "saved_not_persisted": "Saved: the startup config does NOT carry a running "
                                     "credential line",
              "save_unverified": "Save not verified: it could not run or be read back"}
#: A rotation's rows, by phase: the rotation itself, its persistence chain, a recovery.
ROTATION_WORDS = {"rotate": "Rotation", "persist": "Rotation's persistence",
                  "recover": "Rotation recovery"}


def rotation(ctx):
    """Persist, rotate and recover: the rotation record job health's row reads (C359: a
    persist was readable now and not later). Its rows name the device and NO list (C361), so
    the list's own devices (`members`) choose them. A device's own save is kind `persist` and
    worded by ITS state (C362: a save recorded with a rotation's state read as a rotation); a
    row `record_exceptions` corrects is drawn as what is known, marked corrected, with what it
    recorded and why."""
    from modules.nsot import credential_rotation as cr
    try:
        rows = [r for r in cr.rotation_records_as_known() if _mine(ctx, r.get("device", ""))]
    except OSError as exc:
        return _out(errors=[f"the rotation record could not be read: {exc}"])
    events = []
    for r in reversed(rows[-ctx["limit"]:]):
        state, phase = r.get("state", ""), r.get("phase", "")
        failed = r.get("failed_stage", "")
        save = state in cr.SAVE_STATES
        what = (SAVE_WORDS[state] if save else
                f"{ROTATION_WORDS.get(phase, phase or 'Rotation')}: "
                f"{state.replace('_', ' ') or 'no state recorded'}")
        known = r.get("exception") or {}
        marks = (["failed"] if failed or state == cr.SAVE_NOT_PERSISTED else []) + (
            ["corrected"] if known else [])
        e = _event(r.get("at", ""), "persist" if save else "rotation", what, [r.get("device", "")],
                   who=r.get("actor", ""),
                   detail=(f"stopped at {failed}" if failed else "every stage passed")
                   + f"; via {r.get('via') or known.get('via') or 'not named'}",
                   outcome=state, marks=marks,
                   record=[("Phase", phase), ("State", state)]
                   + ([("Recorded as", r.get("recorded_state", "")),
                       ("Corrected by", known.get("finding", ""))] if known else [])
                   + [("Via", r.get("via") or known.get("via") or "not named")]
                   + [(s.get("name", "?"), ("ok" if s.get("ok") else "FAILED")
                       + (f": {s['reason']}" if s.get("reason") else ""))
                      for s in r.get("stages") or []])
        if known:
            e["exception"] = known.get("why", "")
        events.append(e)
    return _out(events, cut=[f"the rotation record's newest {ctx['limit']}"]
                if len(rows) > ctx["limit"] else [])


def retries(ctx):
    """Each authorised retry of a change that was rolled back (gitignored, so no commit)."""
    from modules.nsot import hostvars
    rows = [r for r in hostvars.retry_log(ctx["ref"].repo_dir) if _mine(ctx, r.get("device", ""))]
    return _out([_event(r.get("at", ""), "retry", "Retry authorised after a rollback",
                        [r.get("device", "")], who=r.get("actor", ""), detail=r.get("reason", ""),
                        record=[("Reason", r.get("reason")), ("The rollback it lifted", r.get("note"))])
                 for r in reversed(rows[-ctx["limit"]:])])


def onboarding(ctx):
    """Onboarding's and adopt's runs (create, verify, abandon, adopt), from their run record."""
    from modules.nsot import onboard
    got = onboard.read_runs(ctx["ref"].repo_dir)
    if got["state"] == "unreadable":
        return _out(errors=[f"the onboarding runs could not be read: {got.get('error', '')}"])
    rows = [r for r in got["rows"] if _mine(ctx, r.get("device", ""))][:ctx["limit"]]
    return _out([_event(r.get("at", ""), "onboarding",
                        f"{'Adopted' if r.get('kind') == 'adopt' else 'Onboarding ' + str(r.get('kind', 'run'))}"
                        f": {'done' if r.get('ok') else 'stopped'}", [r.get("device", "")],
                        who=r.get("actor", ""), detail=r.get("reason") or r.get("error") or "",
                        sha=r.get("golden_commit", ""), outcome="ok" if r.get("ok") else "failed",
                        marks=[] if r.get("ok") else ["stopped"],
                        record=[("Kind", r.get("kind")), ("Promoted", r.get("promoted")),
                                ("Golden commit", (r.get("golden_commit") or "")[:12]),
                                ("Steps", "; ".join(f"{s.get('name', s) if isinstance(s, dict) else s}"
                                                    for s in r.get("steps") or [])),
                                ("Remaining", "; ".join(str(x) for x in r.get("remaining") or []))])
                 for r in rows])


def acknowledgements(ctx):
    """A person's acknowledgement of a row about a device other than a restart (a restart's is
    drawn on the restart): a repeated authorisation, by its row id."""
    from modules import acknowledgements as _acks
    got = _acks.read()
    if got["state"] == "unreadable":
        return _out(errors=[f"the acknowledgement record could not be read: {got.get('error', '')}"])
    prefix = f"authorisations:{ctx['ref'].name}:"
    rows = []
    for r in got["rows"]:
        row_id = str(r.get("row", ""))
        if not row_id.startswith(prefix):
            continue
        device = row_id[len(prefix):].split(":", 1)[0]
        if _mine(ctx, device):
            rows.append((device, r))
    return _out([_event(r.get("at", ""), "acknowledged",
                        f"Acknowledged: {r.get('what') or r.get('kind') or 'a row'}", [device],
                        who=r.get("by", ""), detail=r.get("why", ""),
                        record=[("Row", r.get("row")), ("Reason", r.get("why")),
                                ("Verified", r.get("verified"))])
                 for device, r in reversed(rows[-ctx["limit"]:])])


def breakglass(ctx):
    """Each break-glass export of the list's record, about every device whose credential it
    sealed."""
    import json
    import os
    from modules import breakglass as bg
    from modules import config
    path = os.path.join(config.DATA_DIR, bg.EXPORT_LOG)
    if not os.path.exists(path):
        return _out()
    try:
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    except (OSError, ValueError) as exc:
        return _out(errors=[f"the break-glass export log could not be read: {exc}"])
    events = []
    for r in reversed(rows):
        held = list(r.get("devices") or {})
        if r.get("list") != ctx["ref"].name or not any(_mine(ctx, d) for d in held):
            continue
        events.append(_event(r.get("at"), "breakglass",
                             f"Break-glass record exported ({len(held)} device"
                             f"{'' if len(held) == 1 else 's'})", held,
                             who=r.get("actor", ""), detail=f"via {r.get('via', '?')}",
                             record=[("Key fingerprint", r.get("key_fingerprint")),
                                     ("Devices", ", ".join(sorted(held))),
                                     ("Written to", r.get("path")), ("Via", r.get("via"))]))
        if len(events) >= ctx["limit"]:
            break
    return _out(events)


def interrupted(ctx):
    """An operation whose process ended while it held a device (CONCURRENCY_AUDIT R5)."""
    from modules.nsot import device_ops
    try:
        rows = [r for r in device_ops.interrupted(ctx["ref"].name)
                if _mine(ctx, r.get("device", ""))]
    except OSError as exc:
        return _out(errors=[f"the device holds could not be read: {exc}"])
    return _out([_event(r.get("started"), "interrupted",
                        f"A {r.get('operation', 'operation')} was cut off: its process ended",
                        [r.get("device", "")], who=r.get("actor", ""),
                        detail=f"last step {(r.get('progress') or {}).get('step') or 'started'}",
                        outcome="interrupted", marks=["did not finish"],
                        record=[("Operation", r.get("operation")), ("Process", r.get("pid")),
                                ("Last step", (r.get("progress") or {}).get("step")),
                                ("Found", iso(r.get("found_at")))])
                 for r in rows[:ctx["limit"]]])


def freshness(ctx):
    """Each authorisation to deploy past the freshness gate, with its reason."""
    from modules.nsot import freshness as fr
    try:
        rows = [a for a in fr.authorisations(ctx["ref"].name, include_expired=True)
                if _mine(ctx, a.get("device", ""))]
    except Exception as exc:                          # noqa: BLE001
        return _out(errors=[f"the freshness authorisations could not be read: {exc}"])
    return _out([_event(a.get("at", ""), "freshness", "Freshness gate authorised",
                        [a.get("device", "")], who=a.get("actor", ""), detail=a.get("reason", ""),
                        record=[("Reason", a.get("reason")), ("Expires", iso(a.get("expires_at"))),
                                ("Fingerprint", a.get("fingerprint"))])
                 for a in rows[-ctx["limit"]:]])


def approvals(ctx):
    """Each approval-queue item about a device that a person or a capture resolved."""
    from modules import approval_queue
    from modules.filestore import StoreUnreadable
    try:
        rows = approval_queue.read_list(ctx["ref"])
    except StoreUnreadable as exc:
        return _out(errors=[str(exc)])
    rows = [r for r in rows if _mine(ctx, r.get("device_hostname", "")) and r.get("resolved_at")]
    return _out([_event(r.get("resolved_at"), "approval",
                        f"{str(r.get('action_type', 'item')).replace('_', ' ').capitalize()}: "
                        f"{r.get('status', '?')}", [r.get("device_hostname", "")],
                        who=r.get("resolved_by", ""), detail=str(r.get("context") or ""),
                        outcome=r.get("status", ""),
                        record=[("Raised", iso(r.get("created_at"))), ("Status", r.get("status")),
                                ("Item", r.get("id"))])
                 for r in rows[-ctx["limit"]:]])


def updates(ctx):
    """Each update of the app by its updater (deploy/update): the fleet's, never a device's."""
    from modules import update_op
    if ctx["device"]:
        return _out()
    got = update_op.history(limit=ctx["limit"])
    if got["state"] == "unreadable":
        return _out(errors=[f"the updater's record could not be read: {got.get('error', '')}"])
    return _out([_event(o.get("ended_at") or o.get("at"), "update",
                        f"The app updated to {(o.get('to') or '')[:10] or '?'}: "
                        f"{str(o.get('outcome', '?')).replace('_', ' ')}", [],
                        who=o.get("requested_by", ""),
                        detail=f"from {(o.get('from') or '')[:10] or '?'}",
                        outcome=o.get("outcome", ""),
                        record=[("From", o.get("from")), ("To", o.get("to")),
                                ("Outcome", o.get("outcome"))])
                 for o in got.get("rows") or []])


#: Every store History reads, in the order it asks them. A source absent here is read nowhere;
#: `operation_stages.HISTORY` names one per operation, `WRITTEN_ELSEWHERE` the rest.
SOURCES = {
    "golden": golden, "intent": intent, "measured": measured, "commits": fleet_commits,
    "decisions": decisions, "receipts": receipts, "restarts": restarts,
    "restart_windows": restart_windows, "rotation": rotation, "retries": retries,
    "onboarding": onboarding, "acknowledgements": acknowledgements, "breakglass": breakglass,
    "interrupted": interrupted, "freshness": freshness, "approvals": approvals,
    "updates": updates,
}

#: The kind filter (board D): each a group of event kinds, in the board's four headings.
KIND_GROUPS = (
    ("The repository", (("commits", "Commits (golden, intent, profile)", ("golden", "intent", "commit")),
                        ("measured", "Measured, unchanged", ("measured",)))),
    ("What ran on a device", (("receipts", "Deploys and restores", ("receipt",)),
                              ("rotations", "Rotations", ("rotation",)),
                              ("persists", "Persists", ("persist",)),
                              ("onboarding", "Onboarding and adopt", ("onboarding",)),
                              ("interrupted", "Cut off mid-run", ("interrupted",)),
                              ("retries", "Retries authorised", ("retry",)))),
    ("What happened to a device", (("restarts", "Restarts", ("restart",)),
                                   ("windows", "Planned windows", ("window",)))),
    ("Decisions and records", (("approvals", "Approvals", ("approval",)),
                               ("acknowledged", "Acknowledgements", ("acknowledged",)),
                               ("freshness", "Freshness authorised", ("freshness",)),
                               ("breakglass", "Break-glass exports", ("breakglass",)),
                               ("decisions", "Baseline decisions", ("decision",)),
                               ("updates", "App updates", ("update",)))),
)
KIND_FILTERS = {key: kinds for _h, group in KIND_GROUPS for key, _w, kinds in group}
SINCE_CHOICES = (("7", "7 days"), ("30", "30 days"), ("365", "a year"), ("", "all time"))
DEFAULT_LIMIT = 50
MAX_LIMIT = 800


def short_who(who: str) -> str:
    """A person's name for a one-line summary: "alex" for "alex (host login, not a verified
    identity)". How they were identified is said in full where the row expands."""
    return (who or "").split(" (", 1)[0].strip()


def devices_words(devices: list) -> str:
    """The Device column: the fleet's own record, every device, one, a few, or how many."""
    if not devices:
        return "fleet"
    if "*" in devices:
        return "every device"
    if len(devices) <= 3:
        return ", ".join(devices)
    return f"{len(devices)} devices"


def timeline(ref, device: str = "", person: str = "", kinds=None, since_days: str = "",
             limit: int = DEFAULT_LIMIT, members=None) -> dict:
    """THE reader (C369): ``{"events", "errors", "cut", "limit", "total", "people",
    "counts"}``, newest first. Both the History page and a device's History tab call it; the
    tab with *device* set. *kinds*: KIND_FILTERS keys to keep (None or empty: every kind);
    *since_days*: "" for all time. *people* and *counts* are of the rows before the person and
    kind filters, for the filters' choices. *members*: the list's devices, for a store whose
    rows name no list (the rotation record); None reads them all."""
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    since = (time.time() - int(since_days) * 86400) if str(since_days or "").isdigit() else None
    ctx = {"ref": ref, "device": device or "", "limit": limit, "since": since,
           "members": set(members) if members is not None else None}
    events, errors, cut = [], [], []
    for name, source in SOURCES.items():
        try:
            got = source(ctx)
        except Exception as exc:                      # noqa: BLE001
            log.warning("history: source %s failed: %s", name, exc)
            errors.append(f"the {name.replace('_', ' ')} record could not be read "
                          f"({type(exc).__name__}: {exc})")
            continue
        events += got.get("events") or []
        errors += got.get("errors") or []
        cut += got.get("cut") or []
    events = [e for e in events if _recent(ctx, e["at"])
              and (not device or about(e, device))]
    for e in events:
        # The row's ONE line (the operator, 2026-10-02): what, its marks and the person's short
        # name; the full wording, who with how they were identified, expands under the row.
        e["who_short"] = short_who(e.get("who", ""))
        e["devices_words"] = devices_words(e["devices"])
    people = sorted({e["who_short"] for e in events if e["who_short"]})
    counts = {}
    for e in events:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    if person:
        events = [e for e in events if e["who_short"] == person]
    wanted = {k for key in (kinds or ()) for k in KIND_FILTERS.get(key, ())}
    if wanted:
        events = [e for e in events if e["kind"] in wanted]
    events.sort(key=lambda e: epoch(e["at"]), reverse=True)
    return {"events": events[:limit], "errors": errors, "cut": cut, "limit": limit,
            "total": len(events), "people": people, "counts": counts}
