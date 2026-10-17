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


def _out(events=None, errors=None, cut=None, unborn=None):
    return {"events": events or [], "errors": errors or [], "cut": cut or [],
            "unborn": unborn or []}


def _unborn(ctx, words):
    """A source that reads the network's repository, for a network with no repository yet
    (C957): ``_out(unborn=[words])``, or None when the repository exists. Decided by
    `repo.has_repository` (the folder's ``.git``, the header's test, C945), never by git's
    words: its first commit makes the repository, so there is nothing to read yet, which is a
    state, not a failure. Any other failure stays an error, naming git's."""
    from modules.nsot import repo as R

    return None if R.has_repository(ctx["ref"].repo_dir) else _out(unborn=[words])


def about(event: dict, device: str) -> bool:
    """Whether *event* is about *device*: named, or one for every device of the list."""
    devices = event.get("devices") or []
    return device in devices or "*" in devices


def _mine(ctx, device: str) -> bool:
    """A row about *device*, from a store that is the NETWORK'S OWN (its repository, its receipts,
    its runs), belongs to this read: the device asked for, or any of the list's. *members* None
    (a caller that passed none) filters no device out of the network's own records."""
    if ctx["device"]:
        return device == ctx["device"]
    return ctx["members"] is None or device in ctx["members"]


#: The stores every network SHARES whose rows name a device and no network (each with why), so
#: the network's own devices are the only way to tell its rows (C1028). Their sources ask
#: `_ours`, never `_mine`: an empty network has none of their rows, never everyone's.
SHARED_BY_DEVICE = {
    "rotation": "the rotation and save record (`rotation_audit.jsonl`): one file for the "
                "installation, each row naming its device and no network (C361)",
    "acknowledgements": "the acknowledgement record: one file for the installation, a row "
                        "naming its devices (or an alert's address) and no network",
    "reveals": "the reveal record: a row recorded before reveals named their network names "
               "only its device",
    "restart_windows": "the planned-restart windows: a window declared with no network names "
                       "only its devices (one naming every device, `*`, is every network's)",
    "host_keys": "the host-key windows' summaries: one closed with no network names only its "
                 "devices",
}


def _ours(ctx, device: str) -> bool:
    """A row about *device* from a store every network shares (`SHARED_BY_DEVICE`), naming no
    network: the network's only when *device* is one of its own (`inventory`, always a set:
    an empty network has none, and an inventory that could not be read has none, said as an
    error). C1028: W2 walk, with no devices, drew Default's persists and rotations."""
    if ctx["device"]:
        return device == ctx["device"]
    # A source called alone, with no `timeline` context: the members it was given, else none.
    inventory = ctx["inventory"] if "inventory" in ctx else ctx.get("members")
    return device in (inventory or ())


def _inventory(ref, members, device: str) -> tuple:
    """``(names, error)``: the network's devices, for `_ours`. The *members* its caller read,
    else the device asked for (a device's own view), else its inventory read once here. An
    inventory that cannot be read is no devices, and says so: never every network's."""
    if members is not None:
        return set(members), ""
    if device:
        return {device}, ""
    try:
        from modules.device import load_saved_devices

        return {d.get("hostname", "") for d in load_saved_devices(ref.csv_path)
                if d.get("hostname")}, ""
    except Exception as exc:                          # noqa: BLE001 (said on the page)
        return set(), (f"the network's inventory could not be read ({type(exc).__name__}: "
                       f"{exc}): the records every network shares (rotations, saves, "
                       "acknowledgements) are not drawn, since which are this network's "
                       "cannot be told")


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
                     "verified": parts[9].strip(),
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
        from modules.nsot.repo import not_targeted_only

        why = d.partition(":")[2].strip()
        # Not taken only when not covering the network is ALL it says (C885's one reading).
        n = not_targeted_only(why)
        if n:
            return {"state": "not_taken", "words": f"not taken: {n} not targeted", "tag": tag}
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
    # Its Actor-Verified value, for the window's identity line (7.5): "" on a commit made
    # before the trailer existed.
    e["verified"] = r.get("verified", "")
    if why:
        e["exception"] = why
    return e


#: The identity line's words for each Actor-Verified value other than a verified sign-in.
IDENTITY_KINDS = (("host-shell", "host login"), ("none", "not verified"),
                  ("", "before verification was recorded"))


def identity(events) -> dict:
    """The 7.5 line for the commits in *events* (the window the filters draw): ``{commits,
    verified, others: [(words, n)], unverified}``. A value the table does not name counts as
    not verified."""
    # One commit can be two events (a Save All's measurement and its baseline decision, the
    # same sha; measured on the host 2026-10-11): each commit is counted once.
    seen, commits = set(), []
    for e in events:
        if "verified" in e and (e.get("sha") or id(e)) not in seen:
            seen.add(e.get("sha") or id(e))
            commits.append(e)
    counts = {}
    for e in commits:
        v = e["verified"] if e["verified"] in ("access", "host-shell", "") else "none"
        counts[v] = counts.get(v, 0) + 1
    return {"commits": len(commits), "verified": counts.get("access", 0),
            "others": [(w, counts.get(k, 0)) for k, w in IDENTITY_KINDS],
            "unverified": len(commits) - counts.get("access", 0)}


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
        unborn = _unborn(ctx, f"the {words} history")
        if unborn:
            return unborn
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
    unborn = _unborn(ctx, "the saves that measured devices")
    if unborn:
        return unborn
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
    unborn = _unborn(ctx, "the repository's other commits")
    if unborn:
        return unborn
    # A reload's record commit is drawn as its reload (`reloads`), never a second row.
    rows, err = _log(ctx, [".", ":(exclude)golden", ":(exclude)host_vars",
                           ":(exclude).nsot/reloads.jsonl"])
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
    unborn = _unborn(ctx, "the baseline decisions")
    if unborn:
        return unborn
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
        # A window naming this network is its own; one naming none is told by its devices.
        mine = _mine if w.get("list") else _ours
        if "*" in devices:
            devices = ["*"]
        elif not any(mine(ctx, d) for d in devices):
            continue
        events.append(_event(w.get("recorded_at") or w.get("from"), "window",
                             "Planned-restart window declared"
                             + (" (a correction)" if w.get("correction") else ""), devices,
                             who=w.get("by", ""), detail=w.get("why", ""),
                             marks=["correction"] if w.get("correction") else [],
                             record=[("From", iso(w.get("from"))), ("Until", iso(w.get("until"))),
                                     ("Devices", ", ".join(w.get("devices") or [])),
                                     ("Via", w.get("via")), ("Correction", w.get("correction")),
                                     ("Grafana", _restarts.silence_words(w["silence"])
                                      if w.get("silence") else "")]))
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
        rows = [r for r in cr.rotation_records_as_known() if _ours(ctx, r.get("device", ""))]
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
        # C724: a scheduled rotation's rows say so, and whose policy ran it (its `via`).
        if not save and str(r.get("via") or "").startswith("scheduled rotation"):
            what = f"{r['via'][0].upper()}{r['via'][1:]}: {what[0].lower()}{what[1:]}"
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


#: Acknowledged kinds another source draws on its own event (a restart's acknowledgement is a
#: mark on the restart), so this source does not draw them twice.
DRAWN_ELSEWHERE = ("restarts/unplanned",)


def _hosts_by_address(ref) -> dict:
    """The list's devices by management address, for an older acknowledgement that names an
    alert's `instance` and no device."""
    try:
        from modules.device import load_saved_devices
        return {(d.get("ip") or "").strip(): d.get("hostname", "")
                for d in load_saved_devices(ref.csv_path) if d.get("ip")}
    except Exception:                                # noqa: BLE001 - the record still reads
        return {}


def acknowledgements(ctx):
    """A person's acknowledgement of a row about a device, of EVERY kind acknowledged on Needs
    attention but a restart (drawn on the restart): a repeated authorisation, an interrupted
    operation, and an alert acknowledged within its measured band (C433, 2026-10-05: the
    first real one, s3's discards, was recorded and drawn nowhere). Its devices come from the
    record, or from its row (`acknowledgements.devices_of`)."""
    from modules import acknowledgements as _acks
    got = _acks.read()
    if got["state"] == "unreadable":
        return _out(errors=[f"the acknowledgement record could not be read: {got.get('error', '')}"])
    hosts = None
    rows = []
    for r in got["rows"]:
        if r.get("kind") in DRAWN_ELSEWHERE:
            continue
        row_id = str(r.get("row", ""))
        if row_id.startswith("authorisations:") and not row_id.startswith(
                f"authorisations:{ctx['ref'].name}:"):
            continue
        if hosts is None and not r.get("devices") and row_id.startswith("grafana:"):
            hosts = _hosts_by_address(ctx["ref"])
        devices = [d for d in _acks.devices_of(r, hosts) if _ours(ctx, d)]
        if devices:
            rows.append((devices, r))
    events = []
    for devices, r in reversed(rows[-ctx["limit"]:]):
        band = r.get("band")
        what = r.get("what") or r.get("kind") or "a row"
        title = (f"Acknowledged within its band: {what}" if band is not None
                 else f"Acknowledged: {what}")
        events.append(_event(
            r.get("at", ""), "acknowledged", title, devices, who=r.get("by", ""),
            detail=(r.get("why", "") + (f" (band {float(band):.3g}, value then "
                                         f"{float(r['value']):.3g})" if band is not None
                                         and r.get("value") is not None else "")),
            record=[("Row", r.get("row")), ("Reason", r.get("why")),
                    ("Band", f"{float(band):.4g}" if band is not None else None),
                    ("Value then", f"{float(r['value']):.4g}" if r.get("value") is not None else None),
                    ("Verified", r.get("verified"))]))
    return _out(events)


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
    verdicts = bg.intact_verdicts(config.DATA_DIR)
    if verdicts.get("state") == "unreadable":
        return _out(errors=[f"the break-glass download verdicts could not be read: "
                            f"{verdicts.get('error')}"])
    events = []
    for r in reversed(rows):
        held = list(r.get("devices") or {})
        v = (verdicts.get("by_sha") or {}).get(r.get("sha256") or "")
        if r.get("list") != ctx["ref"].name or not any(_mine(ctx, d) for d in held):
            continue
        events.append(_event(r.get("at"), "breakglass",
                             f"Break-glass record exported ({len(held)} device"
                             f"{'' if len(held) == 1 else 's'})", held,
                             who=r.get("actor", ""), detail=f"via {r.get('via', '?')}",
                             marks=(["downloaded intact"] if v and v.get("ok") else
                                    ["not intact"] if v else []),
                             outcome="" if not v or v.get("ok") else "not_intact",
                             record=[("Key fingerprint", r.get("key_fingerprint")),
                                     ("Devices", ", ".join(sorted(held))),
                                     ("Written to", r.get("path")), ("Via", r.get("via"))]))
        if len(events) >= ctx["limit"]:
            break
    done = bg.drills(config.DATA_DIR)
    if done["state"] == "unreadable":
        return _out(events, errors=[f"the break-glass drills could not be read: {done.get('error')}"])
    for r in reversed(done["rows"][-ctx["limit"]:]):
        if r.get("list") != ctx["ref"].name or ctx["device"]:
            continue
        events.append(_event(r.get("at"), "breakglass",
                             f"Offline drill recorded: the file opened without the tool, "
                             f"{r.get('devices')} device(s)", [], who=r.get("actor", ""),
                             detail=f"the file made {r.get('created') or '(no date)'}, opened "
                                    f"{r.get('opened', '?')}",
                             record=[("File sha256", r.get("sha256")), ("Key", r.get("key")),
                                     ("Opened", r.get("opened"))]))
    got = bg.checks(config.DATA_DIR)
    if got["state"] == "unreadable":
        return _out(events, errors=[f"the break-glass checks could not be read: {got.get('error')}"])
    for r in reversed(got["rows"][-ctx["limit"]:]):
        held = list(r.get("devices") or {})
        if r.get("list") != ctx["ref"].name or not any(_mine(ctx, d) for d in held):
            continue
        bad = sorted(d for d, st in (r.get("devices") or {}).items() if st in ("differs", "missing"))
        events.append(_event(r.get("at"), "breakglass",
                             "Break-glass file checked: " + (f"{len(bad)} of {len(held)} not current"
                                                            if bad else "every device current"),
                             held, who=r.get("actor", ""),
                             detail=(f"the file made {r.get('created') or '(no date)'}; the key "
                                     f"{r.get('key', '?')}"
                                     + (f"; it cannot recover {', '.join(bad)}" if bad else "")),
                             marks=["not current"] if bad or r.get("key") != "current" else [],
                             outcome="not_intact" if bad or r.get("key") != "current" else "",
                             record=[("File sha256", r.get("sha256")), ("Made", r.get("created")),
                                     ("Key", r.get("key")),
                                     ("Not current", ", ".join(bad))]))
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


def credential_profiles(ctx):
    """Each change to a credential profile from Credentials › Profiles: who, which profile, and
    the fields set, never a value. Installation-wide, so the fleet's, never one device's."""
    from modules import credential_changes
    if ctx["device"]:
        return _out()
    got = credential_changes.entries()
    if got["error"]:
        return _out(errors=[f"the credential profile record could not be read: {got['error']}"])
    def what(r):
        if r.get("action") == "rotation_policy":
            return (f"Credential profile {r.get('profile', '?')}'s rotation policy set: "
                    f"{r.get('policy') or 'not recorded'}")
        return (f"Credential profile {r.get('profile', '?')} "
                f"{'deleted' if r.get('action') == 'deleted' else 'saved'}"
                + (f": {', '.join(r.get('fields') or [])} set" if r.get("fields") else ""))
    return _out([_event(r.get("at"), "credential", what(r), [],
                        who=_who(r.get("actor", ""), r.get("verified", "")),
                        record=[("Profile", r.get("profile")), ("Action", r.get("action")),
                                ("Fields set", ", ".join(r.get("fields") or []))]
                        + ([("Rotation policy", r.get("policy"))] if r.get("policy") else []))
                 for r in reversed(got["rows"]) if _recent(ctx, r.get("at"))])


def topology_expected(ctx):
    """Each island declared expected on Topology, or withdrawn: who, which device, why."""
    from modules import topology_expected as TE
    got = TE.history(getattr(ctx["ref"], "data_dir", ""))
    if got["error"]:
        return _out(errors=[f"the expected-island record could not be read: {got['error']}"])
    return _out([_event(r.get("at"), "expected",
                        f"{r.get('device', '?')} "
                        + ("declared an expected island: " + r.get("reason", "")
                           if r.get("action") == "declared" else "no longer an expected island"),
                        [r.get("device", "")], who=r.get("actor", ""),
                        record=[("Device", r.get("device")), ("Action", r.get("action")),
                                ("Reason", r.get("reason"))])
                 for r in reversed(got["rows"])
                 if _mine(ctx, r.get("device", "")) and _recent(ctx, r.get("at"))])


def topology_layout(ctx):
    """Each device a person moved on Topology, and each Reset layout (C661): who, which device,
    where to. A device's History lists its own moves; a reset belongs to the network."""
    from modules import topology_positions as TP
    got = TP.history(getattr(ctx["ref"], "data_dir", ""))
    if got["error"]:
        return _out(errors=[f"the Topology layout record could not be read: {got['error']}"])
    rows = []
    for r in reversed(got["rows"]):
        device = r.get("device", "")
        if not _recent(ctx, r.get("at")) or (ctx.get("device") and not device) or \
                (device and not _mine(ctx, device)):
            continue
        to = r.get("to") or []
        rows.append(_event(r.get("at"), "layout",
                           f"{device} moved on Topology"
                           + (f" to ({to[0]}, {to[1]})" if len(to) == 2 else "")
                           + ", the network's layout saved for everyone"
                           if r.get("action") == "moved" else
                           "Topology's layout reset: the generated one drawn for everyone",
                           [device] if device else [], who=r.get("actor", ""),
                           record=[("Action", r.get("action")), ("Device", device),
                                   ("Places", r.get("places"))]))
    return _out(rows)


def saved_views(ctx):
    """Each History › Query view saved, pinned, unpinned or removed (C667): who, its title and
    the question it opens. The network's; no device's History lists them."""
    from modules import saved_views as SV
    if ctx.get("device"):
        return _out()
    got = SV.history(getattr(ctx["ref"], "data_dir", ""))
    if got["error"]:
        return _out(errors=[f"the saved-views record could not be read: {got['error']}"])
    return _out([_event(r.get("at"), "view",
                        f"History › Query view “{r.get('title', '?')}” "
                        f"{r.get('action', '?')}", [], who=r.get("actor", ""),
                        record=[("Action", r.get("action")), ("Title", r.get("title")),
                                ("Opens", r.get("address"))])
                 for r in reversed(got["rows"]) if _recent(ctx, r.get("at"))])


#: The reveal record's kinds this view leaves to another, each with why. Every other kind, a
#: new one included, is drawn by `reveals` (who, when, which object; never a value).
REVEALS_ELSEWHERE = {
    "breakglass_record": "the break-glass export: History's `breakglass` source draws it from "
                         "the export's own log, with its download verdicts",
    "bootstrap_config_refused": "a TFTP request the ZTP responder refused: nothing was served, "
                                "so nothing was revealed (a pending device's page reads it, "
                                "modules/nsot/ztp.py)",
}


def _reveal_network(r) -> str:
    """The network a reveal row names: its `list`, or a bootstrap's ``list=<name>`` detail;
    "" for a row recorded before reveals named one."""
    name = str(r.get("list") or "").strip()
    if not name:
        m = re.match(r"list=(.+)$", str(r.get("detail") or ""))
        name = m.group(1).strip() if m else ""
    return name


def _reveal_drawn(r) -> tuple:
    """``(what, record)`` for one reveal row: the object revealed, from the fields its kind
    records, each masked again on the way out. Only named fields are read, so a field holding
    a value is never drawn whatever it is called."""
    from modules.redact import redact_text

    def m(value):
        return redact_text(str(value)) if value not in (None, "") else ""

    what, dev, detail = str(r.get("what") or ""), m(r.get("target")), m(r.get("detail"))
    if what == "log_line":
        stream = ", ".join(f'{k}="{m(v)}"' for k, v in sorted((r.get("stream") or {}).items()))
        at = m(r.get("line_at"))
        return (f"Log line revealed: {dev or 'a line'} at {at[:19].replace('T', ' ')} UTC",
                [("Line", f"{{{stream}}} at {at}"),
                 ("What was shown", f"the masked line, sha256 {m(r.get('shown_sha256'))}")])
    if what == "golden_config":
        return (f"Golden config revealed: {dev} at {detail[:10]}",
                [("Device", dev), ("Version", detail)])
    if what == "golden_diff":
        return f"Golden diff revealed: {dev}, {detail}", [("Device", dev), ("Versions", detail)]
    if what == "bootstrap_config" and str(r.get("actor") or "").startswith("ztp:"):
        return (f"Bootstrap config served to {dev} over TFTP",
                [("Device", dev), ("Asked from", m(r.get("peer"))), ("File", m(r.get("file"))),
                 ("What was served", f"sha256 {m(r.get('sha256'))}" if r.get("sha256")
                  else "")])
    if what == "bootstrap_config":
        return f"Bootstrap config revealed: {dev}", [("Device", dev)]
    return (f"{what.replace('_', ' ').capitalize() or 'Something'} revealed: {dev or '?'}",
            [("Kind", m(what)), ("Object", dev)])


def reveals(ctx):
    """Every reveal the reveal record holds (C837; C818's log lines first): a golden version,
    a golden diff, a bootstrap config (to a person, or served to a device over TFTP), a log
    line, and any kind added later; who, when, which object and the reason where the kind
    records one, never the value, which the record does not hold (and a field that did is not
    read). The break-glass export is its own source (`REVEALS_ELSEWHERE`). A reveal about a
    device outside the list's inventory is the network's own record; one recorded before
    reveals named their network is drawn by its device's name, and says so."""
    from modules import reveal_audit
    from modules.redact import redact_text
    got = reveal_audit.read()
    if got["state"] == "unreadable":
        return _out(errors=[f"the reveal record could not be read: {got['error']}"])
    events, more = [], False
    for r in got["rows"]:
        if r.get("what") in REVEALS_ELSEWHERE:
            continue
        dev = str(r.get("target") or "")
        net = _reveal_network(r)
        if net and net != ctx["ref"].name:
            continue
        if not net and not (dev and _ours(ctx, dev)):
            continue
        if (ctx["device"] and dev != ctx["device"]) or not _recent(ctx, r.get("at")):
            continue
        if len(events) >= ctx["limit"]:
            more = True
            break
        what, record = _reveal_drawn(r)
        reason = redact_text(str(r.get("reason") or ""))
        devices = [dev] if dev and (ctx["members"] is None or dev in ctx["members"]) else []
        events.append(_event(
            r.get("at"), "reveal", what, devices, who=r.get("actor", ""), detail=reason,
            record=record + [("Reason", reason), ("Verified", r.get("kind")),
                             ("Network", "" if net else "not recorded (drawn by its device's "
                                                        "name)")]))
    return _out(events, cut=[f"the reveals' newest {ctx['limit']}"] if more else [])


def show_commands(ctx):
    """Each Show commands run (C547, C548; board D's row): who (the agent, for a person), the
    commands, the devices, and each one's outcome. Its answers stay on the run's own page."""
    from modules.nsot import reads
    got = reads.runs(ctx["ref"].name, device=ctx["device"], limit=ctx["limit"],
                     data_dir=getattr(ctx["ref"], "data_dir", ""))
    errors = ([f"{len(got['unreadable'])} Show commands record(s) could not be read: "
               f"{', '.join(got['unreadable'][:5])}"] if got["unreadable"] else [])
    events = []
    for r in got["runs"]:
        hosts = [h for h in r.get("devices") or [] if _mine(ctx, h)]
        if not hosts or not _recent(ctx, r.get("started_at")):
            continue
        s = r.get("summary") or {}
        outcome = ("refused" if r.get("state") == "refused" else
                   "running" if r.get("state") == "running" else s.get("words", ""))
        what = f"Show commands: {'; '.join(r.get('commands') or [])[:120]}"
        lp = r.get("logging_path") or {}
        if r.get("purpose") == "test the logging path":
            # Board F's History row: what to act on first, in the test's own words.
            n = len(r.get("devices") or [])
            what = f"Logging path on {n} device{'s' if n != 1 else ''}"
            if lp.get("state") == "done":
                order = ("not received", "not sent", "unknown", "received")
                outcome = ", ".join(f"{lp['counts'][k]} {k}" for k in order
                                    if lp.get("counts", {}).get(k))
            elif r.get("state") != "refused":
                outcome = "watching"
        events.append(_event(r.get("started_at"), "show_commands", what,
                             hosts, who=reads.actor_words(r),
                             detail=(r.get("refused") or r.get("purpose")
                                     or (f"Why: {r['reason']}" if r.get("reason") else "")),
                             outcome=outcome,
                             record=[("Run", r.get("id")), ("Devices", len(r.get("devices") or [])),
                                     ("Outcome", outcome)]))
    return _out(events, errors)


def privileged(ctx):
    """Each Tier 2 run (Run a privileged command…, modules/nsot/privileged.py): who, why, the
    command, and its verdict. Its kept before-state stays in the record."""
    from modules.nsot import privileged as P
    got = P.runs(ctx["ref"].name, device=ctx["device"], limit=ctx["limit"],
                 data_dir=getattr(ctx["ref"], "data_dir", ""))
    errors = ([f"{len(got['unreadable'])} Tier 2 record(s) could not be read: "
               f"{', '.join(got['unreadable'][:5])}"] if got["unreadable"] else [])
    events = []
    for r in got["runs"]:
        host = r.get("device", "")
        if not _mine(ctx, host) or not _recent(ctx, r.get("started_at")):
            continue
        state = r.get("state", "")
        outcome = {"done": "done, verified", "unverified": "done, not verified",
                   "refused": "not sent", "failed": "failed", "running": "running"}.get(state, state)
        events.append(_event(r.get("started_at"), "privileged",
                             f"Privileged: {r.get('command', '')}", [host], who=r.get("actor", ""),
                             detail=r.get("reason", ""), outcome=outcome,
                             record=[("Run", r.get("id")), ("Reason", r.get("reason")),
                                     ("Verify", (r.get("verify") or {}).get("words")),
                                     ("Why", r.get("why"))]))
    return _out(events, errors)


def reloads(ctx):
    """Each Reload run from the device page (P.14, modules/nsot/reload_op.py): who, why, and
    how it ended, each step's outcome in the record. The restart and its window are their own
    sources."""
    from modules.nsot import reload_op
    got = reload_op.read_records(ctx["ref"].repo_dir)
    if got["state"] == "unreadable":
        return _out(errors=[f"the reload record could not be read: {got.get('error', '')}"])
    events = []
    for r in got["rows"]:
        host = r.get("device", "")
        if not _mine(ctx, host) or not _recent(ctx, r.get("at")):
            continue
        events.append(_event(r.get("at", ""), "reload",
                             f"Reload: {'back, verified' if r.get('ok') else r.get('outcome', '')}",
                             [host], who=r.get("by", ""), detail=r.get("reason", ""),
                             outcome="ok" if r.get("ok") else "failed",
                             marks=[] if r.get("ok") else ["stopped"],
                             record=[("Reason", r.get("reason")), ("Outcome", r.get("outcome")),
                                     ("Steps", "; ".join(f"{s.get('step')}: {s.get('detail')}"
                                                         for s in r.get("steps") or [])),
                                     ("Window", (r.get("window") or {}).get("end_words"))]))
        if len(events) >= ctx["limit"]:
            break
    return _out(events)


def _host_key_window_summaries(ctx, hk) -> tuple:
    """``(events, errors)``: each closed window's ONE summary of the keys it kept
    (`host_keys.close_windows`), for this list, when it closed: the devices are those whose
    keys it took, else every device of the window. An unreadable summaries file is an
    error, never "none"."""
    got = hk.summaries()
    if got.get("state") == "unreadable":
        return [], [f"the host-key windows' summaries could not be read: {got.get('error')}"]
    out = []
    for s in got.get("rows") or []:
        if s.get("list") and s.get("list") != ctx["ref"].name:
            continue
        keys = s.get("keys") or []
        devices = sorted({k.get("device") for k in keys if k.get("device")}) or \
            list(s.get("devices") or [])
        mine = _mine if s.get("list") else _ours      # one naming no network: by its devices
        if not _recent(ctx, s.get("closed_at")) or not (
                "*" in devices or any(mine(ctx, d) for d in devices)):
            continue
        out.append(_event(
            s.get("closed_at", ""), "hostkey", hk.summary_words(s), devices,
            who=s.get("by", ""), detail=f"the planned window {s.get('from', '')} to "
                                        f"{s.get('until', '')} closed",
            outcome="window",
            record=[("Window", f"{s.get('by', '')}: {s.get('why', '')}"),
                    ("Keys", "; ".join(f"{k.get('device')}: {k.get('fingerprint')} (was "
                                       f"{k.get('replaced') or 'none recorded'})"
                                       for k in keys) or "none"),
                    ("Written", s.get("written_at"))]))
    return out, []


def host_keys(ctx):
    """Each SSH host key Mercury kept for a device of the list (C906): on first contact, by a
    person's re-key, or under a planned window that expected new keys, the key it replaced in
    the record. The store is keyed by address, so the list's addresses name the devices."""
    from modules import host_keys as _hk
    words = {_hk.FIRST_CONTACT: "SSH host key kept on first contact",
             _hk.REKEYED: "SSH host key re-keyed",
             _hk.WINDOW: "SSH host key kept under a planned window"}
    try:
        keys = _hk.read()["keys"]
    except _hk.HostKeyStoreUnreadable as exc:
        return _out(errors=[str(exc)])
    hosts = _hosts_by_address(ctx["ref"])
    events = []
    for ip, rec in sorted(keys.items()):
        chain = list(rec.get("history") or []) + [rec]
        # Whose each key was (C940): a key forgotten when its device left names that device
        # and network, and so does every key before it at this address; a key after the last
        # forgotten one is the device the inventory names at the address now.
        owners, owner = [], hosts.get(ip)
        for k in reversed(chain):
            if k.get("forgotten"):
                owner = (k.get("device") if k.get("network") == ctx["ref"].name else None)
            owners.append(owner)
        owners.reverse()
        for i in reversed(range(len(chain))):
            k, host = chain[i], owners[i]
            if not host or not _mine(ctx, host):
                continue
            if k.get("forgotten") and _recent(ctx, k.get("replaced_at")):
                events.append(_event(
                    k.get("replaced_at", ""), "hostkey", "SSH host key forgotten", [host],
                    who=k.get("replaced_by", ""),
                    detail=f"{k.get('fingerprint', '')} ({k.get('type', '')}): "
                           f"{k.get('replaced_why', '')}",
                    outcome="forgotten",
                    record=[("Address", ip), ("Fingerprint", k.get("fingerprint")),
                            ("Type", k.get("type")), ("How", _hk.FORGOTTEN),
                            ("Network", k.get("network")), ("Why", k.get("replaced_why")),
                            ("Forgotten at", k.get("replaced_at")),
                            ("Forgotten by", k.get("replaced_by"))]))
            if not k.get("fingerprint") or not _recent(ctx, k.get("kept_at")):
                continue
            current = k is rec
            # The key this one took the place of: recorded with it since 2026-10-16, else the
            # one before it in the record's history, unless that one was forgotten (a first
            # contact after a forget replaced nothing).
            before = k.get("replaced") or (chain[i - 1].get("fingerprint", "")
                                           if i and not chain[i - 1].get("forgotten") else "")
            window = k.get("window") or {}
            detail = f"{k.get('fingerprint', '')} ({k.get('type', '')})"
            if window:
                # The operator, 2026-10-16: every key a window takes is a row naming the new
                # key, the one it replaced and the window's reason.
                detail += (f", replacing {before or 'no recorded key'}, during "
                           f"'{window.get('why', '')}'")
            events.append(_event(
                k.get("kept_at", ""), "hostkey",
                words.get(k.get("how", ""), "SSH host key kept"), [host],
                who=k.get("kept_by", ""), detail=detail,
                outcome=("held" if current else
                         "forgotten" if k.get("forgotten") else "replaced"),
                record=[("Address", ip), ("Fingerprint", k.get("fingerprint")),
                        ("Type", k.get("type")), ("How", k.get("how")),
                        ("Replaced", before),
                        ("Why", rec.get("why") if current else k.get("replaced_why")),
                        ("Window", f"{window.get('by', '')}: {window.get('why', '')}"
                         if window else None),
                        ("Window from", window.get("from")),
                        ("Window until", window.get("until")),
                        ("Replaced at", None if current else k.get("replaced_at")),
                        ("Replaced by", None if current else k.get("replaced_by"))]))
    summed, errors = _host_key_window_summaries(ctx, _hk)
    events += summed
    events.sort(key=lambda e: epoch(e["at"]), reverse=True)
    return _out(events[:ctx["limit"]], errors, cut=[f"the host keys' newest {ctx['limit']}"]
                if len(events) > ctx["limit"] else [])


#: Every store History reads, in the order it asks them. A source absent here is read nowhere;
#: `operation_stages.HISTORY` names one per operation, `WRITTEN_ELSEWHERE` the rest.
SOURCES = {
    "golden": golden, "intent": intent, "measured": measured, "commits": fleet_commits,
    "decisions": decisions, "receipts": receipts, "restarts": restarts,
    "restart_windows": restart_windows, "rotation": rotation, "retries": retries,
    "onboarding": onboarding, "acknowledgements": acknowledgements, "breakglass": breakglass,
    "interrupted": interrupted, "approvals": approvals,
    "updates": updates, "show_commands": show_commands, "privileged": privileged,
    "reloads": reloads, "credential_profiles": credential_profiles,
    "topology_expected": topology_expected, "topology_layout": topology_layout,
    "saved_views": saved_views, "reveals": reveals, "host_keys": host_keys,
}

#: The kind filter (board D): each a group of event kinds, in the board's four headings.
KIND_GROUPS = (
    ("The repository", (("commits", "Commits (golden, intent, profile)", ("golden", "intent", "commit")),
                        ("measured", "Measured, unchanged", ("measured",)))),
    ("What ran on a device", (("receipts", "Deploys and restores", ("receipt",)),
                              ("rotations", "Rotations", ("rotation",)),
                              ("persists", "Persists", ("persist",)),
                              ("privileged", "Privileged commands (Tier 2)", ("privileged",)),
                              ("reloads", "Reloads", ("reload",)),
                              ("onboarding", "Onboarding and adopt", ("onboarding",)),
                              ("interrupted", "Cut off mid-run", ("interrupted",)),
                              ("retries", "Retries authorised", ("retry",)))),
    ("What happened to a device", (("restarts", "Restarts", ("restart",)),
                                   ("windows", "Planned windows", ("window",)))),
    ("Decisions and records", (("approvals", "Approvals", ("approval",)),
                               ("acknowledged", "Acknowledgements", ("acknowledged",)),
                               ("breakglass", "Break-glass exports", ("breakglass",)),
                               ("credentials", "Credential profiles", ("credential",)),
                               ("expected", "Expected islands", ("expected",)),
                               ("layout", "Topology layouts", ("layout",)),
                               ("views", "Saved views", ("view",)),
                               ("reveals", "Reveals", ("reveal",)),
                               ("hostkeys", "SSH host keys", ("hostkey",)),
                               ("decisions", "Baseline decisions", ("decision",)),
                               ("updates", "App updates", ("update",)),
                               ("show_commands", "Show commands", ("show_commands",)))),
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
             limit: int = DEFAULT_LIMIT, members=None, unverified: bool = False) -> dict:
    """THE reader (C369): ``{"events", "errors", "cut", "limit", "total", "people",
    "counts"}``, newest first. Both the History page and a device's History tab call it; the
    tab with *device* set. *kinds*: KIND_FILTERS keys to keep (None or empty: every kind);
    *since_days*: "" for all time. *people* and *counts* are of the rows before the person and
    kind filters, for the filters' choices. *members*: the list's devices as its caller read
    them (an empty network's is ``[]``, which keeps none of another network's rows); None
    reads the inventory here, for the stores every network shares (`SHARED_BY_DEVICE`, C1028),
    and filters no device out of the network's own. *unborn*: the records that
    live in the network's repository, for a network with no repository yet (C957): drawn as
    that state, once, never as errors."""
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    since = (time.time() - int(since_days) * 86400) if str(since_days or "").isdigit() else None
    inventory, inventory_error = _inventory(ref, members, device or "")
    ctx = {"ref": ref, "device": device or "", "limit": limit, "since": since,
           "members": set(members) if members is not None else None, "inventory": inventory}
    events, errors, cut, unborn = [], [inventory_error] if inventory_error else [], [], []
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
        unborn += got.get("unborn") or []
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
    if unverified:
        events = [e for e in events if "verified" in e and e["verified"] != "access"]
    events.sort(key=lambda e: epoch(e["at"]), reverse=True)
    return {"events": events[:limit], "errors": errors, "cut": cut, "unborn": unborn,
            "limit": limit,
            "total": len(events), "people": people, "counts": counts,
            "identity": identity(events)}
