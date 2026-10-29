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
"limit", "since", "members", "until", "call"}``: *device* "" for every device; *since* an epoch
or None for all time; *members* the list's device names, for a store whose rows name no list;
*until* the page's place (an epoch, or None for the newest), which a source keeps its rows at
or before BEFORE its newest-*limit* cut (`_recent`; those that cannot are `UNPAGED`); *call*
one AI call's id, or "". Each source
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
           record=None, call=""):
    """One row. *call*: an AI call's id, whose prompt and answer the opened row fetches."""
    return {"at": iso(at), "kind": kind, "what": what,
            "devices": sorted({d for d in devices if d}), "who": who or "", "detail": detail,
            "sha": sha or "", "outcome": outcome, "marks": list(marks or []),
            "record": [(k, v) for k, v in (record or []) if v not in (None, "", [], {})],
            "call": call or ""}


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
    "heartbeat_windows": "the heartbeat windows' re-measures (`heartbeat_rules.jsonl`): one "
                         "file for the installation, each naming its devices' windows and no "
                         "network",
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
    """Within the read's window: at or after *since* (the Since filter), and at or before
    *until* (the place a page starts, 15.14 part B: Load more's cursor or a jumped-to day).
    A source that asks this BEFORE its newest-N cut reads its rows older than the cursor, so
    its cut never hides an older record from the next page."""
    if ctx.get("since") is None and ctx.get("until") is None:
        return True
    t = epoch(at)
    if ctx.get("since") is not None and t < ctx["since"]:
        return False
    return ctx.get("until") is None or t <= ctx["until"]


# ---------------------------------------------------------------------------- git records

_FIELD, _RECORD, _END = "\x1f", "\x1e", "\x1d"
_HEAD = _FIELD.join(["%H", "%cI", "%(trailers:key=Source,valueonly)",
                     "%(trailers:key=Actor,valueonly)",
                     "%(trailers:key=Devices,valueonly,separator=%x2c)",
                     "%(trailers:key=Device-Name,valueonly,separator=%x2c)",
                     "%(trailers:key=Devices-Measured,valueonly,separator=%x2c)",
                     "%(trailers:key=Baseline,valueonly)", "%s",
                     "%(trailers:key=Actor-Verified,valueonly)", "%D",
                     # Feature 7's part 2: an intent commit drafted in words names its call.
                     "%(trailers:key=AI-Call,valueonly)",
                     # C1819: whether each device's capture matched its intent, and how the
                     # device's log says a departing one was changed (one value per device).
                     "%(trailers:key=Intent-Match,valueonly)",
                     "%(trailers:key=Out-Of-Band,valueonly,separator=%x1c)"])
_PATH = re.compile(r"^(golden|host_vars)/([^/]+)\.(cfg|yml)$")


def _log(ctx, paths, *extra, follow=False, count=None):
    """ONE bounded `git log` with each commit's files: ``(rows, error)``, newest first. Each row
    is ``{"sha", "at", "source", "actor", "devices_trailer", "measured", "baseline",
    "subject", "files": [(status, path, old_path)]}``."""
    from modules.nsot import repo as R

    count = count or ctx["limit"] + 1
    since = [f"--since=@{int(ctx['since'])}"] if ctx["since"] is not None else []
    # The page's place (15.14 part B): git keeps the commits at or before it, before the count.
    if ctx.get("until") is not None:
        since.append(f"--until=@{int(ctx['until'])}")
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
                              if d.strip().startswith("tag: ")],
                     "ai_call": parts[11].strip() if len(parts) > 11 else "",
                     "intent_match": parts[12].strip() if len(parts) > 12 else "",
                     "out_of_band": [v.strip() for v in parts[13].split("\x1c") if v.strip()]
                     if len(parts) > 13 else []})
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


#: A block larger than this is drawn folded, its size said (15.14: "a large prompt is
#: collapsed, with a note of its size").
AI_BLOCK_FOLD = 4000
_BLOCK = re.compile(r'<(context|data) name="([^"]+)">\n(.*?)\n</\1>', re.S)


STOP_WORDS = {"end_turn": "the model finished its answer",
              "max_tokens": "cut off at the most tokens out: the answer is incomplete",
              "refusal": "the model declined"}


def ai_call(call_id: str) -> dict:
    """One AI call's prompt as it was sent and its answer as received, for the row a person
    opens (15.14; the operator, 2026-10-26: "the exact wording of the prompt that was given
    and the exact structured response", as a commit's change window): ``{"ok", "error",
    "meta", "sent", "received", "raw"}``. *sent* is each part of the request in the order it
    left the host (the instructions, then each context and data block by its name), each
    ``{"name", "text", "size", "fold"}``; *received* the answer, laid out for reading when it
    is JSON, else as it came; *raw* the answer's bytes as recorded. All of it is the record's
    own masked text, masked again here on the way out: the unmasked prompt never left the host
    and is never stored."""
    import json as _json

    from modules.ai import calls
    from modules.redact import redact_text

    if not re.fullmatch(r"ai-[0-9a-f]{16}", call_id or ""):
        return {"ok": False, "error": f"{call_id[:40]!r} is not an AI call's id"}
    got = calls.find(call_id)
    if got["state"] != "ok":
        return {"ok": False, "error": ("the record of AI calls could not be read: "
                                       f"{got['error']}" if got["state"] == "unreadable" else
                                       f"no AI call {call_id} is recorded")}
    r = got["row"]
    body = r.get("request") or {}

    def part(name, text):
        text = redact_text(text or "")
        return {"name": name, "text": text, "size": len(text), "fold": len(text) > AI_BLOCK_FOLD}
    sent = []
    for block in body.get("system") or []:
        text = block.get("text") or ""
        blocks = _BLOCK.findall(text)
        if blocks:
            sent += [part(f"{kind}: {name}", inner) for kind, name, inner in blocks]
        else:
            sent.append(part(f"the instructions ({r.get('prompt', '?')})", text))
    for m in body.get("messages") or []:
        content = m.get("content") if isinstance(m.get("content"), str) else ""
        blocks = _BLOCK.findall(content)
        sent += ([part(f"{kind}: {name}", inner) for kind, name, inner in blocks]
                 or [part(m.get("role", "user"), content)])
    raw = redact_text(r.get("response") or "")
    try:
        received = _json.dumps(_json.loads(raw), indent=2, ensure_ascii=False)
    except ValueError:
        received = raw
    # Only what the row's record above does not already say (its model, prompt, schema,
    # tokens, cost and verdict): the request's bound and thinking, and why the answer ended.
    stop = r.get("stop_reason") or ""
    meta = [("Most tokens out", body.get("max_tokens")),
            ("Thinking", (r.get("thinking") or "the model's default") if body else ""),
            ("Stopped", STOP_WORDS.get(stop, stop))]
    return {"ok": True, "error": "", "meta": [(k, v) for k, v in meta if v not in (None, "")],
            "sent": sent, "received": received, "raw": raw,
            "not_sent": not body, "verdict": r.get("verdict") or "", "id": call_id}


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
    # A change drafted in words (feature 7, part 2) links back to the AI call that drafted it,
    # as the call's row links to what it produced: one id, read from the commit's own trailer.
    if r.get("ai_call") and re.fullmatch(r"ai-[0-9a-f]{16}", r["ai_call"]):
        e["from_call"] = r["ai_call"]
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


def _departure_marks(r: dict, devices, device: str) -> list:
    """A golden commit that recorded a device departing from its intent, marked (C1819, the
    operator's Walk 3: a capture that took in an out-of-band change read as any other):
    "captured, departs from intent (+1 -1); changed out-of-band, by console per SYS-5-CONFIG_I".
    From the commit's own `Intent-Match:` and `Out-Of-Band:` trailers (`out_of_band`), so
    nothing is read per row. A device's view marks that device; the fleet's names each."""
    from modules.nsot import out_of_band as OOB

    off = OOB.departures(r.get("intent_match", ""))
    how = OOB.named(r.get("out_of_band") or [])
    verb = "captured" if r.get("source") in OOB.CAPTURE_SOURCES else "recorded"
    marks = []
    for d in sorted(devices):
        if d not in off or (device and d != device):
            continue
        mark = f"{verb}, departs from intent ({off[d]})"
        if d in how:
            mark += f"; changed out-of-band, {OOB.short(how[d])}"
        marks.append(mark if device else f"{d} {mark}")
    return marks


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
            marks = _departure_marks(r, devices, ctx["device"]) if kind == "golden" else []
            e = _from_commit(r, kind, what, devices,
                             record=[("Commit", r["sha"][:12]), ("Source", r["source"]),
                                     ("By", r["who"])]
                             + ([("Intent-Match", r.get("intent_match", "")),
                                 ("Out-of-band", "; ".join(r.get("out_of_band") or []))]
                                if marks else []))
            e["marks"] += marks
            events.append(e)
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

def _intent_words(r: dict) -> str:
    """A receipt's intent commit in words (C1775): the commit; "not recorded" for a receipt
    written before the receipt recorded it (2026-10-26), never a blank; "not read" when it
    could not be read; and a restore's or re-apply's, which sends a golden, not intent."""
    if "intent_commit" not in r:
        return "not recorded (this receipt is from before the intent commit was recorded)"
    sha = r.get("intent_commit")
    if sha is None:
        return "none: a restore or re-apply sends a golden, not intent"
    return sha[:12] if sha else "not read when the receipt was written"


def receipts(ctx):
    """The deploy and restore receipts. Each text a row carries (its reason, a removed line, an
    authorised line and its reason, its source ref) is masked again on the way out: the rows
    are masked at write, and this is the second layer, as GET /deploy/receipts's was until it
    left with today's device page at 7.8 (P7-22, 2026-10-17). A row written before masking,
    or by hand, never draws a secret."""
    from modules.nsot import receipts as R
    from modules.redact import redact_text

    def m(value):
        return redact_text(str(value)) if value not in (None, "") else ""

    got = R.read(ctx["ref"].name, device=ctx["device"], limit=ctx["limit"])
    if got["state"] == "unreadable":
        return _out(errors=[f"the deploy receipts could not be read: {got.get('error', '')}"])
    events = []
    for r in got.get("rows") or []:
        if not _mine(ctx, r.get("device", "")):
            continue
        pending = R.is_pending(r)
        removals = r.get("removals") or []
        rb = r.get("rollback") or {}
        e = _event(r.get("at", ""), "receipt",
                   f"{R.past(r)}: "
                   f"{r.get('outcome', '?').replace('_', ' ')}"
                   + (f", {R.PENDING_WORDS}" if pending else ""), [r.get("device", "")],
                   who=r.get("actor", ""),
                   detail=(f"{r.get('program_lines', 0)} line(s) sent"
                           + (f"; {len(removals)} removed (Mode B)" if removals else "")
                           + (f"; {m(r['reason'])}" if r.get("reason") else "")),
                   sha=r.get("golden_commit", ""), outcome=r.get("outcome", ""),
                   marks=(["Mode B"] if removals else []) + (["rolled back"] if rb.get("performed") else []),
                   record=[("Program", f"{r.get('program_lines', 0)} line(s), hash "
                                       f"{(r.get('program_hash') or '')[:12]}"),
                           ("Matches what was confirmed", {True: "yes", False: "NO"}.get(
                               r.get("matches_confirmed"))),
                           ("Removed (Mode B)", "; ".join(m(x.get("line")) for x in removals)),
                           ("Authorised", "; ".join(f"{m(a.get('line'))}: {m(a.get('reason'))}"
                                                    for a in r.get("authorised") or [])),
                           ("Rollback", rb.get("state") if rb.get("performed") else ""),
                           ("Commit", (r.get("golden_commit") or "")[:12]),
                           ("Intent deployed", _intent_words(r)),
                           ("Source ref", m(r.get("source_ref")))])
        e["pending"] = pending
        # C1775: the intent commit it deployed, the link to it and back (`?commit=`).
        if re.fullmatch(r"[0-9a-f]{40}", str(r.get("intent_commit") or "")):
            e["intent_commit"] = r["intent_commit"]
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
    # The page's window before the newest-N cut (15.14 part B), so a cut hides no older row.
    found = [r for r in rs["rows"] if _recent(ctx, r.get("at", ""))]
    try:
        rows = _restarts.judged(found[:limit], _restarts.planned_rows())
    except RuntimeError as exc:
        errors.append(str(exc))
        rows = found[:limit]
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
                [f"the restarts' newest {limit}"] if len(found) > limit else [])


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
        if w.get("list") not in (ctx["ref"].name, None, "") or \
                not _recent(ctx, w.get("recorded_at") or w.get("from")):
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
                                     # Ended early (C1389): when, by whom, why.
                                     ("Ended early", (f"{iso(w['ended_at'])} by "
                                                      f"{w.get('ended_by') or 'an unrecorded caller'}: "
                                                      f"{w.get('ended_why', '')}"
                                                      + (f" (a correction: {w['ended_correction']})"
                                                         if w.get("ended_correction") else ""))
                                      if w.get("ended_at") else None),
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
    persist was readable now and not later). A row names its network (`list`, C361) and is
    this network's only when it is this one and the device is ours; an older row names none,
    so the list's own devices (`members`) choose it, said on the row. A device's own save is
    kind `persist` and
    worded by ITS state (C362: a save recorded with a rotation's state read as a rotation); a
    row `record_exceptions` corrects is drawn as what is known, marked corrected, with what it
    recorded and why."""
    from modules.list_settings import same_network
    from modules.nsot import credential_rotation as cr

    def mine(r):
        if r.get("list") and not same_network(r["list"], ctx["ref"].name):
            return False
        return _ours(ctx, r.get("device", ""))

    try:
        rows = [r for r in cr.rotation_records_as_known()
                if mine(r) and _recent(ctx, r.get("at", ""))]
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
                   + f"; via {r.get('via') or known.get('via') or 'not named'}"
                   + ("" if r.get("list") else "; an older row naming no network, matched "
                      "by the device's name alone"),
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
    rows = [r for r in hostvars.retry_log(ctx["ref"].repo_dir)
            if _mine(ctx, r.get("device", "")) and _recent(ctx, r.get("at", ""))]
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
    rows = [r for r in got["rows"] if _mine(ctx, r.get("device", ""))
            and _recent(ctx, r.get("at", ""))][:ctx["limit"]]
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
        if r.get("kind") in DRAWN_ELSEWHERE or not _recent(ctx, r.get("at", "")):
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
    from modules import breakglass as bg
    from modules import config
    # Through its owner (C1324): once moved, the log is on the records database (K31).
    got = bg.all_exports(config.DATA_DIR)
    if got["state"] == "unreadable":
        return _out(errors=[f"the break-glass export log could not be read: "
                            f"{got.get('error')}"])
    rows = got["rows"]
    verdicts = bg.intact_verdicts(config.DATA_DIR)
    if verdicts.get("state") == "unreadable":
        return _out(errors=[f"the break-glass download verdicts could not be read: "
                            f"{verdicts.get('error')}"])
    events = []
    for r in reversed(rows):
        held = list(r.get("devices") or {})
        v = (verdicts.get("by_sha") or {}).get(r.get("sha256") or "")
        if r.get("list") != ctx["ref"].name or not any(_mine(ctx, d) for d in held) \
                or not _recent(ctx, r.get("at")):
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
    for r in reversed([r for r in done["rows"] if _recent(ctx, r.get("at"))][-ctx["limit"]:]):
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
    for r in reversed([r for r in got["rows"] if _recent(ctx, r.get("at"))][-ctx["limit"]:]):
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
                if _mine(ctx, r.get("device", "")) and _recent(ctx, r.get("started"))]
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
    rows = [r for r in rows if _mine(ctx, r.get("device_hostname", "")) and r.get("resolved_at")
            and _recent(ctx, r.get("resolved_at"))]

    def withdrawn(r):
        # C368: a withdrawal records `withdrawn_by` and its reason, never `resolved_by`, so it
        # was drawn with no person; who or what withdrew it, and why, are its record.
        if r.get("status") != "withdrawn":
            return {"who": r.get("resolved_by", ""), "detail": str(r.get("context") or ""),
                    "record": []}
        return {"who": r.get("withdrawn_by", ""),
                "detail": "withdrawn: " + str(r.get("withdrawn_reason") or "no reason recorded"),
                "record": [("Withdrawn by", r.get("withdrawn_by")),
                           ("Why", r.get("withdrawn_reason"))]}

    return _out([_event(r.get("resolved_at"), "approval",
                        f"{str(r.get('action_type', 'item')).replace('_', ' ').capitalize()}: "
                        f"{r.get('status', '?')}", [r.get("device_hostname", "")],
                        who=w["who"], detail=w["detail"], outcome=r.get("status", ""),
                        record=[("Raised", iso(r.get("created_at"))), ("Status", r.get("status")),
                                ("Item", r.get("id"))] + w["record"])
                 for r in rows[-ctx["limit"]:] for w in (withdrawn(r),)])


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


#: A subject's words (15.14): what the call was about, from the row's own `subject`.
SUBJECT_WORDS = {"alert": "the alert", "query": "a question on", "device": "the device",
                 "intent": "an intent change on", "sdn_detection": "the SDN detection",
                 "sdn_collection": "an SDN collection no rule fired on",
                 "deploy_preview": "a change record for the deploy to",
                 "": "the installation"}


def subject_words(subject: dict) -> str:
    """What a call was about, in words: an older row with no subject (before 15.14) and the
    installation's own calls (Test connection) read as the installation."""
    s = subject or {}
    kind = s.get("kind") or ""
    head = SUBJECT_WORDS.get(kind, kind)
    if kind == "alert":
        return f"{head} {s.get('rule') or s.get('id') or ''}".strip()
    if kind == "query":
        return f"{head} {s.get('id') or 'the network'}"
    if kind == "intent":
        return f"{head} {', '.join(s.get('devices') or []) or 'no device'}"
    if kind == "deploy_preview":
        # PHASE8_PLAN 16.11 item 3: the device and the program the draft was for.
        return (f"{head} {', '.join(s.get('devices') or []) or 'no device'}, program "
                f"{str(s.get('id') or '')[:12] or 'unknown'}")
    if kind == "sdn_detection":
        # PHASE8_PLAN 17.1 S7: the rule that fired and the detection's key.
        return f"{head} {s.get('rule') or ''} {s.get('id') or ''}".replace("  ", " ").strip()
    if kind == "sdn_collection":
        # The Lab 8 walk's objective 2.3: a collection classified as an evaluation, by its time.
        return f"{head}, collected {s.get('id') or 'at an unrecorded time'}"
    return head


def ai_calls(ctx):
    """Each call to a model through Phase 8's gateway (modules/ai/calls.py), as 15.14 draws
    it: when, who, the feature and its subject (written with the call), the model, the tokens
    in and out, the cache's write and read, the cost, and the outcome (the gateway's verdict,
    then what became of the answer, its own use row). Opened, the row fetches the prompt as
    sent and the answer as received (`/v2/history/ai-call/<id>`). A device's tab shows the
    calls whose subject names the device; the installation's own calls are no device's."""
    from modules.ai import calls
    # One kept read (`calls.kept_all`), its calls and their use rows both: the whole record
    # read twice (`read` and `uses`) was this page's 13 s on the host (2026-10-29).
    got = calls.kept_all()
    if got["state"] == "unreadable":
        return _out(errors=[f"the record of AI calls could not be read: {got.get('error', '')}"])
    used = {}
    for r in got.get("rows") or []:
        if "use_of" in r:
            used.setdefault(r["use_of"], []).append(r)
    rows = [r for r in reversed(got.get("rows") or []) if "use_of" not in r]
    # A press that joined another's call (C1854) is its own row, drawn as a join of that call:
    # its outcome the call's, its detail opening the call's prompt and answer; the call names
    # who joined it.
    by_id = {r.get("id"): r for r in rows}
    joins = {}
    for r in reversed(rows):
        if r.get("verdict") == calls.JOINED:
            joins.setdefault(r.get("joined"), []).append(r)
    if ctx["device"]:
        rows = [r for r in rows if ctx["device"] in ((r.get("subject") or {}).get("devices")
                                                     or [])]
    # One call by its id (a feature's link to its row, 15.14), and the page's window, both
    # before the newest-N cut, so an old call is found and a page reads older calls.
    if ctx.get("call"):
        rows = [r for r in rows if r.get("id") == ctx["call"]]
    rows = [r for r in rows if _recent(ctx, r.get("at"))]

    def batched(r):
        # An evaluation round's request sent in a batch (PHASE8_PLAN 15.12, the operator's
        # decision of 2026-10-29): its batch's id and the request's custom_id, at the batch
        # rate (`gateway.ask_batch`).
        b = r.get("batch") if isinstance(r.get("batch"), dict) else None
        if b is None:
            return ""
        rate = b.get("multiplier")
        return (f"{b.get('id') or 'not submitted'}, request {b.get('custom_id') or '?'}"
                + (f", at {float(rate) * 100:.0f}% of the standard rates" if rate else ""))

    def what(r):
        verdict = r.get("verdict") or "?"
        last = (used.get(r.get("id")) or [{}])[-1].get("use", "")
        head = (f"AI call{' (batched)' if batched(r) else ''}, {r.get('feature', '?')} on "
                f"{subject_words(r.get('subject'))}: ")
        if verdict == calls.JOINED:
            head += f"joined call {r.get('joined', '?')}, nothing sent"
        else:
            head += (last or "answered") if verdict == "ok" else verdict.replace("_", " ")
        return head + f" ({r.get('model', '?')}, ${float(r.get('cost_usd') or 0):.4f})"

    def outcome(r):
        # The gateway's verdict; an answer it passed that its feature then refused showed the
        # person nothing, so it is no success either (drawn as a failure, as every kind's is).
        # A join's is the call's it joined; a call no longer in the record, "joined" (unknown).
        if r.get("verdict") == calls.JOINED:
            joined = by_id.get(r.get("joined"))
            return outcome(joined) if joined and joined.get("verdict") != calls.JOINED \
                else calls.JOINED
        last = (used.get(r.get("id")) or [{}])[-1].get("use", "")
        return ("refused_by_validation" if r.get("verdict") == "ok"
                and last.startswith("refused") else r.get("verdict", ""))

    def tokens(r):
        t = r.get("tokens") or {}
        return (f"{int(t.get('input_tokens') or 0)} in, {int(t.get('output_tokens') or 0)} "
                f"out, cache {int(t.get('cache_creation_input_tokens') or 0)} written, "
                f"{int(t.get('cache_read_input_tokens') or 0)} read") if t else "none (not sent)"
    def event(r):
        e = _event(r.get("at"), "ai_call", what(r),
                   list((r.get("subject") or {}).get("devices") or []),
                   who=r.get("actor", ""),
                   detail=r.get("detail", "") or f"prompt {r.get('prompt', '?')}",
                   outcome=outcome(r), call=r.get("joined") or r.get("id", ""),
                   record=[("Call", r.get("id")), ("Joined call", r.get("joined")),
                           ("About", subject_words(r.get("subject"))),
                           ("Prompt", r.get("prompt")), ("Schema", r.get("schema")),
                           ("Model", r.get("model")), ("Batch", batched(r)),
                           ("Tokens", tokens(r)),
                           ("Cost", f"${float(r.get('cost_usd') or 0):.4f}"),
                           ("Verdict", r.get("verdict")),
                           ("Then", "; ".join(u.get("use", "") + (f" ({u['detail']})"
                                                                  if u.get("detail") else "")
                                              for u in used.get(r.get("id")) or [])
                            or "nothing recorded"),
                           ("Joined by", "; ".join(f"{j.get('actor', '?')} at {j.get('at', '?')}"
                                                   for j in joins.get(r.get("id")) or []))])
        # What the answer produced (15.14's links both ways): the last use row's page and
        # anchor, drawn as "Open what it produced".
        e["produced"] = produced((used.get(r.get("id")) or [{}])[-1].get("links"))
        return e
    return _out([event(r) for r in rows[:ctx["limit"]]],
                cut=[f"the AI calls' newest {ctx['limit']}"] if len(rows) > ctx["limit"] else [])


#: A use row's page is one of Mercury's own (`/v2/...`, a path and its query): any other value
#: (another host, a scheme, a path outside v2) is not drawn as a link.
_PRODUCED = re.compile(r"^/v2/[A-Za-z0-9/_.~%-]*(\?[A-Za-z0-9_.~%=&+-]*)?$")
_ANCHOR = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def produced(links) -> str:
    """The address of what an AI call's answer produced, from its use row's *links*
    (``{"page", "anchor"}``): the page and ``#anchor``, or "" when the row names none or names
    anything but a page of Mercury's own."""
    links = links if isinstance(links, dict) else {}
    page, anchor = str(links.get("page") or ""), str(links.get("anchor") or "")
    if not _PRODUCED.match(page):
        return ""
    return page + (f"#{anchor}" if _ANCHOR.match(anchor) else "")


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


#: The installation's settings record's kinds, as a row says them (a kind not here is said by
#: its own name, never dropped).
SETTING_WORDS = {
    "card_replace": "replaced", "netbox_writes_off": "NetBox writes turned off",
    "ai_hosted_allow": "hosted AI allowed", "ai_hosted_off": "hosted AI turned off",
    "records_db_save": "saved", "records_db_replace": "password replaced",
    "ratify": "decision recorded", "network_create": "network created",
    "network_delete": "network deleted", "inventory_source": "inventory source set",
    "drift_interval": "drift check interval set", "drift_on": "drift checks turned on",
    "drift_off": "drift checks turned off",
    "records_store_move": "a store moved to the records database",
    "records_store_back": "a store moved back to its files",
    # PHASE8_PLAN 18.3 rule 2 (C1843; modules/ai/background.py): a background AI feature.
    "ai_background_on": "a background AI feature turned on",
    "ai_background_off": "a background AI feature turned off",
    "ai_background_caps": "a background AI feature's caps changed",
}


def installation_settings(ctx):
    """Each change to the installation's own settings (Settings › Installation): who, when, the
    card, and for a card's Save each field's old and new value ("AI (hosted): Cap per day $50
    → $80", the operator, 2026-10-27: a cap change is an admin action recorded in History).
    Installation-wide, so the fleet's on every network, never one device's. A row recorded
    before values were kept names its fields only."""
    from modules import installation_settings as I
    if ctx["device"]:
        return _out()
    got = I.changes()
    if got["state"] == "unreadable":
        return _out(errors=["the installation's settings record could not be read: "
                            f"{got.get('error', '')}"])

    def title(r):
        card = r.get("card") or ""
        if card in I.CARDS:
            return I.CARDS[card]["title"]
        if r.get("kind", "").startswith("records_"):
            return "Records database"
        return card.replace("_", " ").capitalize() or "Installation"

    def what(r):
        kind = r.get("kind", "")
        if kind == "card_save" and r.get("changes"):
            return f"{title(r)}: " + "; ".join(I.change_words(c) for c in r["changes"])
        if kind in ("card_save", "records_db_save"):
            return f"{title(r)} saved: {', '.join(r.get('fields') or []) or 'no fields named'}"
        words = SETTING_WORDS.get(kind, kind.replace("_", " ") or "a change")
        return f"{title(r)}: {words}"
    return _out([_event(r.get("at"), "setting", what(r), [],
                        who=_who(r.get("actor", ""), r.get("actor_verified", "")),
                        record=[("Card", title(r)), ("Recorded as", r.get("kind")),
                                ("Changes", "; ".join(I.change_words(c)
                                                      for c in r.get("changes") or [])),
                                ("Fields", ", ".join(r.get("fields") or [])),
                                ("Reason", r.get("reason"))])
                 for r in got["rows"] if _recent(ctx, r.get("at"))])


#: A Grafana write's action, as a row says it.
_GRAFANA_VERBS = {"silence_set": "set", "silence_moved": "moved", "silence_expired": "expired"}


def grafana_writes(ctx):
    """Each write Mercury sent to Grafana (a silence set, moved or expired, C1089): who it was
    for, the silence, its matchers and Grafana's answer, a refused one in danger. A row names
    the network whose Grafana client sent it (a planned-restart window's); one naming none is
    the installation's own, drawn on every network as app updates are. Never one device's."""
    from modules import grafana_writes as gw
    if ctx["device"]:
        return _out()
    got = gw.entries()
    if got["error"]:
        return _out(errors=[f"the Grafana write record could not be read: {got['error']}"])

    def what(r):
        verb = _GRAFANA_VERBS.get(r.get("action"), r.get("action") or "?")
        target = ", ".join(r.get("matchers") or []) or r.get("silence_id") or "?"
        until = (f" until {r['ends_at']}" if r.get("ends_at")
                 and r.get("action") != "silence_expired" else "")
        return (f"Grafana silence {verb}: {target}{until}" if r.get("ok") else
                f"Grafana silence NOT {verb}: {target}: {r.get('error') or 'no reason recorded'}")
    return _out([_event(r.get("at"), "grafana", what(r), [],
                        who=_who(r.get("by", ""), r.get("verified", "")),
                        outcome="done" if r.get("ok") else "failed",
                        record=[("Silence", r.get("silence_id")),
                                ("Matchers", ", ".join(r.get("matchers") or [])),
                                ("Ends", r.get("ends_at")), ("Asked by", r.get("via")),
                                ("Reason", r.get("comment")),
                                ("Network", r.get("network") or "the installation's"),
                                ("Grafana's answer", r.get("error") or "taken")])
                 for r in reversed(got["rows"])
                 if r.get("network") in (ctx["ref"].name, None, "") and _recent(ctx, r.get("at"))])


#: An alert rule change's kind of row, as its line says it.
_RULE_CHANGE_WORDS = {"added": "added", "changed": "changed", "removed": "removed"}


def alert_rule_changes(ctx):
    """Each change to a Grafana alert rule made in Grafana (C1886; `modules/alert_rule_changes.
    py`, recorded by the alerts reader from the ruler): the rule, its old and new version, what
    changed in words, who Grafana says saved it (or that it does not say) and when. The first
    read of a configuration is one row ("first recorded"), never a change per rule. A row names
    the networks reading that Grafana; one naming none is drawn on every network. A device's
    History draws only a rule whose ``device`` label names it: any other rule is the
    network's."""
    from modules import alert_rule_changes as ARC
    got = ARC.read()
    if got["state"] == "unreadable":
        return _out(errors=[f"the alert rule record could not be read: {got['error']}"])
    name = ctx["ref"].name
    rows = [r for r in got["rows"] if r.get("kind") == "rule"
            and (not r.get("networks") or name in r["networks"])]
    if ctx["device"]:
        rows = [r for r in rows if ctx["device"] in (r.get("devices") or [])]
    rows = [r for r in rows if _recent(ctx, r.get("at"))]

    def version(r):
        if r.get("change") == "changed":
            return f"version {r.get('version_from')} → {r.get('version')}"
        if r.get("change") == "removed":
            return f"was version {r.get('version_from')}"
        return f"version {r.get('version')}"

    def record(r):
        return [("Rule", f"{r.get('title')} ({r.get('uid')})"),
                ("Folder and group", f"{r.get('folder')} › {r.get('group')}"),
                ("Version", version(r)),
                ("Definition hash", (f"{r.get('hash_from') or '—'} → {r.get('hash') or '—'}"
                                     if r.get("change") != "baseline" else r.get("hash"))),
                ("What changed", r.get("summary")),
                ("Saved by (as Grafana says)", r.get("who")),
                ("Saved in Grafana", r.get("updated")),
                ("Seen by Mercury", r.get("seen_at")),
                ("Time shown", r.get("at_basis")),
                ("Read from", f"Grafana's ruler, by the alerts reader ({r.get('store')})"),
                ("Networks", ", ".join(r.get("networks") or []) or "every network"),
                ("Devices", ", ".join(r.get("devices") or [])
                 or "none by label: the network's record only")]

    events, firsts = [], {}
    for r in rows:
        if r.get("change") == "baseline":
            firsts.setdefault((r.get("store"), r.get("seen_at")), []).append(r)
            continue
        verb = _RULE_CHANGE_WORDS.get(r.get("change"), r.get("change") or "?")
        what = f"Alert rule {verb} in Grafana: {r.get('title')}, {version(r)}"
        if r.get("change") == "changed" and r.get("summary"):
            what += f": {r['summary']}"
        events.append(_event(r.get("at"), "alert_rule", what, r.get("devices") or [],
                             who=r.get("who", ""), detail=r.get("at_basis", ""),
                             outcome=r.get("change", ""), record=record(r)))
    for (store, seen), rs in firsts.items():
        n = len(rs)
        events.append(_event(seen, "alert_rule",
                             f"Alert rules first recorded from Grafana: {n} rule"
                             f"{'' if n == 1 else 's'}, each at its version",
                             sorted({d for r in rs for d in r.get("devices") or []})
                             if ctx["device"] else [],
                             who="Mercury's alerts reader",
                             detail=("the first read of this Grafana's rules: no change, the "
                                     "state each later change is judged against"),
                             outcome="baseline",
                             record=[("Read from", f"Grafana's ruler, by the alerts reader "
                                                   f"({store})")]
                             + [(r.get("title"), f"version {r.get('version')}, hash "
                                                 f"{r.get('hash')}, saved by {r.get('who')}")
                                for r in rs]))
    events.sort(key=lambda e: e["at"], reverse=True)
    return _out(events[:ctx["limit"]],
                cut=([f"the alert rule changes' newest {ctx['limit']}"]
                     if len(events) > ctx["limit"] else []))


def heartbeat_windows(ctx):
    """Each re-measure of the heartbeat windows written from Monitoring (C360: `heartbeat_apply`
    kept a record nothing drew): who, how many windows changed, and each device's window. The
    record is the installation's (`SHARED_BY_DEVICE`), so a network draws a re-measure that
    named one of its own devices, and a device's page one that named it."""
    from modules import heartbeat_windows as hw
    got = hw.records()
    if got["error"]:
        return _out(errors=[f"the heartbeat windows' record could not be read: {got['error']}"])
    events = []
    for r in reversed(got["rows"]):
        windows = r.get("windows") or {}
        # A retirement's removal of one device's rule (C1338) names the device it removed.
        removed = [d for d in r.get("removed") or [] if d]
        ours = sorted(d for d in set(windows) | set(removed) if _ours(ctx, d))
        if not ours or not _recent(ctx, r.get("at")):
            continue
        events.append(_event(r.get("at"), "heartbeat",
                             (f"Heartbeat rule removed: {', '.join(removed)}" if removed else
                              f"Heartbeat windows re-measured: {r.get('changes', 0)} changed"),
                             ours, who=r.get("actor", ""),
                             detail=((r.get("why") or "retired") + "; " if removed else "")
                             + "written for Grafana's next restart (its host step)",
                             outcome="done",
                             record=[("File", r.get("path"))]
                             + [(d, "rule removed" if d in removed else
                                 f"{windows[d]} s" if windows[d] else "no window")
                                for d in ours]))
    return _out(events[:ctx["limit"]])


def topology_expected(ctx):
    """Each island declared expected on Topology, or withdrawn: who, which device, why."""
    from modules import topology_expected as TE
    got = TE.history(getattr(ctx["ref"], "data_dir", ""))
    if got["error"]:
        return _out(errors=[f"the expected-island record could not be read: {got['error']}"])
    def said(r):
        key = r.get("device", "?")
        if key == TE.words_for(key):
            return key + (" declared an expected island: " + r.get("reason", "")
                          if r.get("action") == "declared" else " no longer an expected island")
        # C1487: a weak point accepted by design, or no longer.
        return (("Accepted by design: " if r.get("action") == "declared"
                 else "No longer accepted: ") + TE.words_for(key)
                + (f" ({r.get('reason', '')})" if r.get("action") == "declared" else ""))

    def devices(key):
        if key.startswith(TE.SPOF):
            return [key[len(TE.SPOF):]]
        if key.startswith(TE.BRIDGE):
            return key[len(TE.BRIDGE):].split("~")
        return [key]

    return _out([_event(r.get("at"), "expected", said(r), devices(r.get("device", "")),
                        who=r.get("actor", ""),
                        record=[("Device", r.get("device")), ("Action", r.get("action")),
                                ("Reason", r.get("reason"))])
                 for r in reversed(got["rows"])
                 if any(_mine(ctx, d) for d in devices(r.get("device", "")))
                 and _recent(ctx, r.get("at"))])


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
                           f"{device}'s place removed from Topology's layout: it was retired"
                           if r.get("action") == "forgot" else
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


def _netbox_import(name, j):
    """One import's row (B8) from its job record (`netbox_jobs.history`): its result as the
    NetBox page's card draws it, read from the job, never recomputed."""
    result = (j.get("results") or {}).get(name) or {}
    said = str((result.get("happened") or {}).get("summary") or "")
    every = j.get("operation") == "import_all"
    head = "NetBox import" + (" of every network" if every else "")
    if j.get("state") == "importing":
        what, outcome = (f"{head} started: it has recorded no end (running, or cut off by a "
                         "restart of the app)"), "running"
    elif j.get("outcome") == "failed":
        # The result beside a failed import is the network's LAST recorded one, which may be an
        # earlier import's: it is not drawn as this one's.
        what, outcome = f"{head} failed before it finished: the app's log names why", "failed"
    else:
        what = f"{head}: " + (said or "it ended and recorded no result")
        outcome = result.get("level") or "nothing recorded"
    # A confirmed job's `actor` is who confirmed it, `previewed_by` who previewed it (B2's
    # shape); a record without `previewed_by` predates that, and its `actor` previewed it.
    confirmed = "previewed_by" in j
    who = j.get("actor") or ""
    if who and not confirmed:
        who += " (who previewed it: this record predates naming who confirmed it)"
    return _event(j.get("started_at") if j.get("state") == "importing" else j.get("at"),
                  "netbox", what, [], who=who, outcome=outcome,
                  record=[("Network", "every network" if every else name),
                          ("Outcome", outcome), ("Started", j.get("started_at")),
                          ("Ended", j.get("at") if j.get("state") != "importing" else ""),
                          ("Confirmed by", j.get("actor") if confirmed else ""),
                          ("Previewed by", j.get("previewed_by") if confirmed
                           else j.get("actor")), ("Job", j.get("id"))])


def _netbox_removal(r):
    """One Remove or Stop tracking's row (C954) from the removal record, in the words its
    result is drawn in on the NetBox page (`netbox_removal_result`, the same computation)."""
    from modules.preview_confirm import netbox_removal_result

    drawn = netbox_removal_result(r)
    forget = bool(r.get("forget_only"))
    what = ("NetBox: stopped tracking: " if forget else "NetBox removal: ") + \
        str((drawn.get("happened") or {}).get("summary") or "")
    return _event(r.get("at"), "netbox", what, [], who=r.get("actor", ""),
                  outcome=drawn.get("level", ""),
                  record=[("Network", r.get("list")), ("Outcome", drawn.get("level")),
                          ("Operation", "Stop tracking (deletes nothing in NetBox)" if forget
                           else "Remove from NetBox"),
                          ("Deleted", str(len(r.get("deleted") or [])) if not forget else ""),
                          ("Left alone", str(len(r.get("skipped") or [])) if not forget else ""),
                          ("Refused by NetBox", str(len(r.get("failed") or []))
                           if r.get("failed") else ""),
                          ("Forgotten", str(len(r.get("forgotten") or [])) if forget else ""),
                          ("Error", r.get("error"))])


def netbox(ctx):
    """Each import of this network into NetBox, and each Remove from NetBox and Stop tracking
    (C954), from the records those operations write (B8: the operator's import was in neither
    History nor any record History read): who confirmed it, when, its counts in the NetBox
    page's own words, and its outcome. The network's own records, so no device's History lists
    them; an import of every network is each network's it names."""
    from modules import netbox_guard, netbox_jobs
    if ctx.get("device"):
        return _out()
    name = ctx["ref"].name
    events, errors = [], []
    got = netbox_jobs.history(name)
    if got["error"]:
        errors.append(f"the NetBox import record could not be read: {got['error']}")
    events += [_netbox_import(name, j) for j in got["rows"]]
    removals = netbox_guard.read_removals(name)
    if removals["state"] == "unreadable":
        errors.append(f"the NetBox removal record could not be read: {removals['error']}")
    events += [_netbox_removal(r) for r in removals["rows"]]
    events = [e for e in events if _recent(ctx, e["at"])]
    events.sort(key=lambda e: epoch(e["at"]), reverse=True)
    return _out(events[:ctx["limit"]], errors,
                cut=[f"NetBox's newest {ctx['limit']}"] if len(events) > ctx["limit"] else [])


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


def sdn_operations(ctx):
    """Each SDN flow operation (PHASE8_PLAN 17.1 S8 and S16, modules/sdn/flow_ops.py): a
    person's flow change or a response, who confirmed it (or AUTO, with its reason), the
    requests' hash, Verify's checks and the outcome. A switch is not an inventory device, so
    these are the network's own rows, drawn on History, never on a device's tab."""
    from modules.sdn import flow_intent
    if ctx["device"]:
        return _out()
    got = flow_intent.operations(ctx["ref"].name)
    if got["state"] == "unreadable":
        return _out(errors=[f"the SDN operations could not be read: {got['error']}"])
    events = []
    for r in got["rows"]:
        if not _recent(ctx, r.get("at")):
            continue
        response = r.get("response") or {}
        what = ("Response" if response.get("kind") == "response" else
                "Meter expiry" if response.get("kind") == "expiry" else
                # A lost response put back (C2018); its record names the operation it re-applies.
                "Re-apply" if response.get("kind") == "reapply" else "Flow change")
        checks = "; ".join(f"{c.get('state')}: {c.get('words')}"
                           for c in (r.get("verify") or {}).get("checks") or [])
        who = r.get("actor", "")
        if r.get("mode") == "auto":
            auto = r.get("autonomous") or {}
            who = f"{who} (autonomous: AUTO by {auto.get('by')}, {auto.get('reason')})"
        events.append(_event(r.get("at"), "sdn",
                             f"SDN {what.lower()} on {r.get('dpid_hex')}: {r.get('outcome')}",
                             [], who=who, detail="; ".join(r.get("words") or []),
                             outcome=r.get("outcome", ""),
                             record=[("Operation", r.get("id")), ("Controller", r.get("connection")),
                                     ("Requests' hash", r.get("hash")),
                                     ("Action", response.get("action")),
                                     ("Re-applies", response.get("of")),
                                     ("Detection", (response.get("detection") or {}).get("words")),
                                     ("Verify", checks), ("Error", r.get("error"))]))
    events = events[-ctx["limit"]:]
    return _out(events)


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


#: A console run's outcome, as History says it (modules/nsot/console_ztp.py's outcomes).
CONSOLE_OUTCOMES = {"surveyed": "surveyed", "stopped": "stopped: found signed in",
                    "done": "done, verified", "unverified": "done, not verified",
                    "not_blank": "not blank: nothing typed", "unreachable": "console unreachable",
                    "refused_state": "refused: found signed in", "running": "running",
                    # The one-decision out-of-band onboarding's (modules/nsot/oob_onboard.py).
                    "signed_in": "found signed in: nothing typed",
                    "login": "asked for a login: nothing typed",
                    "unexpected": "stopped: an unexpected prompt",
                    "create_failed": "Create failed: undone",
                    "refused_line": "a line was refused: undone",
                    "read_back": "read-back differs: undone", "copy_failed": "copy failed: undone",
                    "not_answering": "copied, not answering", "busy": "held by another operation"}


def console_ztp(ctx):
    """Each console survey and kick-start (out-of-band ZTP, modules/nsot/console_ztp.py) in the
    network's own records: who, what it found or typed, how it ended, and the masked transcript
    kept in the record. A device being onboarded is in no inventory yet, so every run in the
    network's folder is the network's (never filtered by its members); a device's History
    keeps its own."""
    from modules.nsot import console_ztp as Z
    got = Z.runs(ctx["ref"].name, limit=max(ctx["limit"], 1))
    errors = ([f"{len(got['unreadable'])} console run record(s) could not be read: "
               f"{', '.join(got['unreadable'][:5])}"] if got["unreadable"] else [])
    events = []
    for r in got["runs"]:
        host = r.get("device", "")
        if (ctx["device"] and host != ctx["device"]) or not _recent(ctx, r.get("started_at")):
            continue
        survey = r.get("kind") == Z.KIND_SURVEY
        outcome = CONSOLE_OUTCOMES.get(r.get("outcome", ""), r.get("outcome", ""))
        if survey:
            blank = {True: "factory-blank", False: "not factory-blank"}.get(r.get("blank"),
                                                                           "blank unknown")
            what = f"Console survey: {blank}"
        elif r.get("kind") == "onboard":          # oob_onboard.KIND
            what = f"Out-of-band onboarding: {outcome}"
        else:
            what = f"Console kick-start: {outcome}"
        good = r.get("outcome") in ("surveyed", "done") and (not survey or r.get("blank") is True)
        events.append(_event(r.get("started_at"), "console", what, [host],
                             who=r.get("actor", ""), detail=r.get("reason", ""),
                             outcome=outcome, marks=[] if good else ["stopped"],
                             record=[("Run", r.get("id")), ("Outcome", outcome),
                                     ("Reasons", "; ".join(r.get("reasons") or [])),
                                     ("MAC", r.get("mac")),
                                     ("Console-server port", r.get("port_id")),
                                     ("Lines sent", "\n".join(r.get("lines") or [])),
                                     ("Transcript (masked)", r.get("transcript"))]))
    return _out(events, errors)


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
        c = s.get("corrected") or {}
        if c:
            # A correction (C1389) is its own row, when it was made: the summary written
            # before it stays as it was said.
            out.append(_event(
                c.get("at", ""), "hostkey", hk.summary_words(s) + " (corrected)", devices,
                who=c.get("by", ""),
                detail=(f"the planned window {hk.window_words(s)} said "
                        f"{c.get('was_count', '?')} when it closed; it counts the keys credited "
                        f"to it now: {c.get('why', '')} ({c.get('finding', '')})"),
                outcome="window", marks=["corrected"],
                record=[("Window", f"{s.get('by', '')}: {s.get('why', '')}"),
                        ("Window times", hk.window_words(s)),
                        ("Keys", "; ".join(f"{k.get('device')}: {k.get('fingerprint')} (was "
                                           f"{k.get('replaced') or 'none recorded'})"
                                           for k in keys) or "none"),
                        ("Said before", f"{c.get('was_count', '?')}, written "
                                        f"{c.get('was_written_at', '?')}"),
                        ("Corrected by", c.get("by")), ("Why", c.get("why")),
                        ("Finding", c.get("finding"))]))
            continue
        out.append(_event(
            s.get("closed_at", ""), "hostkey", hk.summary_words(s), devices,
            who=s.get("by", ""), detail=f"the planned window {hk.window_words(s)} closed",
            outcome="window",
            record=[("Window", f"{s.get('by', '')}: {s.get('why', '')}"),
                    ("Keys", "; ".join(f"{k.get('device')}: {k.get('fingerprint')} (was "
                                       f"{k.get('replaced') or 'none recorded'})"
                                       for k in keys) or "none"),
                    ("Ended early", f"{s.get('ended_at')}: {s.get('ended_why', '')}"
                     if s.get("ended_at") else None),
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
            # Each correction of the window this key was credited to (C1389), when it was made:
            # the window it named before, the one it names after, who, why and the finding.
            fixes = list(k.get("recredited") or [])
            for j, fix in enumerate(fixes):
                if not k.get("fingerprint") or not _recent(ctx, fix.get("at")):
                    continue
                was = fix.get("window") or {}
                now_w = (fixes[j + 1].get("window") if j + 1 < len(fixes)
                         else k.get("window")) or {}
                events.append(_event(
                    fix.get("at", ""), "hostkey", "SSH host key's window corrected", [host],
                    who=fix.get("by", ""),
                    detail=(f"{k.get('fingerprint', '')} ({k.get('type', '')}): credited to "
                            f"the window {_hk.window_words(was)} ('{was.get('why', '')}'), now "
                            f"to {_hk.window_words(now_w)} ('{now_w.get('why', '')}'): "
                            f"{fix.get('why', '')} ({fix.get('finding', '')})"),
                    outcome="window", marks=["corrected"],
                    record=[("Address", ip), ("Fingerprint", k.get("fingerprint")),
                            ("Kept at", k.get("kept_at")),
                            ("Credited before", f"{was.get('by', '')}: {was.get('why', '')} "
                                                f"({_hk.window_words(was)})"),
                            ("Credited now", f"{now_w.get('by', '')}: {now_w.get('why', '')} "
                                             f"({_hk.window_words(now_w)})"),
                            ("Corrected by", fix.get("by")), ("Why", fix.get("why")),
                            ("Finding", fix.get("finding"))]))
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
    "reloads": reloads, "console_ztp": console_ztp, "credential_profiles": credential_profiles,
    "topology_expected": topology_expected, "topology_layout": topology_layout,
    "saved_views": saved_views, "reveals": reveals, "host_keys": host_keys,
    "netbox": netbox, "grafana_writes": grafana_writes, "heartbeat_windows": heartbeat_windows,
    "ai_calls": ai_calls, "installation_settings": installation_settings,
    "sdn_operations": sdn_operations,
    "alert_rule_changes": alert_rule_changes,
}

#: The kind filter (board D): each a group of event kinds, in the board's four headings.
KIND_GROUPS = (
    ("The repository", (("golden", "Goldens", ("golden",)),
                        ("intent", "Intent", ("intent",)),
                        ("commits", "Commits (golden, intent, profile)", ("golden", "intent", "commit")),
                        ("measured", "Measured, unchanged", ("measured",)))),
    ("What ran on a device", (("receipts", "Deploys and restores", ("receipt",)),
                              ("rotations", "Rotations", ("rotation",)),
                              ("persists", "Persists", ("persist",)),
                              ("privileged", "Privileged commands (Tier 2)", ("privileged",)),
                              ("reloads", "Reloads", ("reload",)),
                              ("console", "Console surveys and kick-starts", ("console",)),
                              ("onboarding", "Onboarding and adopt", ("onboarding",)),
                              ("interrupted", "Cut off mid-run", ("interrupted",)),
                              ("retries", "Retries authorised", ("retry",)))),
    ("What happened to a device", (("restarts", "Restarts", ("restart",)),
                                   ("windows", "Planned windows", ("window",)))),
    ("Decisions and records", (("approvals", "Approvals", ("approval",)),
                               ("acknowledged", "Acknowledgements", ("acknowledged",)),
                               ("breakglass", "Break-glass exports", ("breakglass",)),
                               ("credentials", "Credential profiles", ("credential",)),
                               ("settings", "Installation settings", ("setting",)),
                               ("expected", "Expected islands", ("expected",)),
                               ("layout", "Topology layouts", ("layout",)),
                               ("views", "Saved views", ("view",)),
                               ("reveals", "Reveals", ("reveal",)),
                               ("hostkeys", "SSH host keys", ("hostkey",)),
                               ("decisions", "Baseline decisions", ("decision",)),
                               ("updates", "App updates", ("update",)),
                               ("ai_calls", "AI calls", ("ai_call",)),
                               ("sdn", "SDN flow operations", ("sdn",)),
                               ("netbox", "NetBox imports and removals", ("netbox",)),
                               ("grafana", "Grafana writes", ("grafana", "heartbeat")),
                               ("alert_rules", "Alert rule changes in Grafana",
                                ("alert_rule",)),
                               ("show_commands", "Show commands", ("show_commands",)))),
)
KIND_FILTERS = {key: kinds for _h, group in KIND_GROUPS for key, _w, kinds in group}
#: The kinds one click away, above the timeline on the History page and on a device's History
#: tab, Goldens first (the operator's walk, 2026-10-18, B: r2's last golden sat behind daily
#: Save All rows, past the tab's newest 30, and was found only by scrolling the fleet's page).
#: Each a KIND_FILTERS key, so the reader keeps only its rows BEFORE its newest-N cut.
QUICK_KINDS = (("golden", "Goldens"), ("intent", "Intent"), ("receipts", "Deploys and restores"),
               ("measured", "Measured, unchanged"), ("restarts", "Restarts"))


def kind_filter(values) -> tuple:
    """``(kinds, error)``: the KIND_FILTERS keys among an address's ``kind`` values, in order,
    each once; a value that is no key is IGNORED (the rest still filter, and none left is every
    kind) and named in *error*, said on the page, never dropped unsaid."""
    kinds, unknown = [], []
    for v in values or ():
        (kinds if v in KIND_FILTERS else unknown).append(v)
    kinds = list(dict.fromkeys(kinds))
    unknown = list(dict.fromkeys(unknown))
    if not unknown:
        return kinds, ""
    names = ", ".join(repr(u[:64]) for u in unknown)
    return kinds, (f"the kind filter {names} is not a kind History records"
                   if len(unknown) == 1 else
                   f"the kind filters {names} are not kinds History records")
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


def name_reused(ref, device: str):
    """The newest retirement of *device*'s name while a live device holds the name again
    (C1420): ``{"sha", "at", "epoch"}``, or None (no retirement, the name not in the inventory
    now, or either unreadable: then nothing is cut). Name-keyed records before it are the
    retired device's, which a device onboarded again under the name inherits nothing of."""
    from modules.nsot import retire

    try:
        from modules.device import load_saved_devices

        live = {d.get("hostname", "") for d in load_saved_devices(ref.csv_path)}
        rec = retire.retired_record(ref.repo_dir, device) if device in live else None
    except Exception as exc:                          # noqa: BLE001 (nothing cut, logged)
        log.warning("history: whether %s's name was used before could not be read: %s",
                    device, exc)
        return None
    if not rec:
        return None
    return {"sha": rec["sha"], "at": rec["at"], "epoch": epoch(rec["at"])}


def _from_reuse(events: list, device: str, reused: dict) -> list:
    """*events* about *device* from its name's retirement on (C1420): the retirement's own row
    kept and saying where the earlier records are, the rows before it left out."""
    kept = [e for e in events if epoch(e["at"]) >= reused["epoch"]]
    said = (f"the records about {device} before this retirement are the retired device's: "
            "History of every device still holds them")
    row = next((e for e in kept if e.get("sha") == reused["sha"]), None)
    if row is not None:
        row["detail"] = (row["detail"] + "; " if row.get("detail") else "") + said
    else:
        kept.append(_event(reused["at"], "intent", f"{device} retired (the device before)",
                           [device], sha=reused["sha"], detail=said))
    return kept


# ---------------------------------------------------------------------------- paging (15.14 B)
# The operator, 2026-10-25: "Load more" fetches the next 50 older than the last one shown, by a
# keyset cursor on the time and the id, never an offset or page numbers, so rows that arrive
# meanwhile do not shift it; a jump to a day starts there; the filters apply on the server and
# combine with both; the cursor and the filters live in the address.

#: Each source's event kinds: a kind filter asks only the sources that can hold its kinds, so a
#: load filtered to Goldens reads no other store (and its cut cannot send the reader back to a
#: store none of whose rows it keeps). A source absent here is read for every filter;
#: tests/test_history_paging.py holds every source's rows to the kinds named here.
SOURCE_KINDS = {
    "golden": ("golden",), "intent": ("intent",), "measured": ("measured",),
    "commits": ("commit",), "decisions": ("decision",), "receipts": ("receipt",),
    "restarts": ("restart",), "restart_windows": ("window",), "rotation": ("rotation", "persist"),
    "retries": ("retry",), "onboarding": ("onboarding",), "acknowledgements": ("acknowledged",),
    "breakglass": ("breakglass",), "interrupted": ("interrupted",), "approvals": ("approval",),
    "updates": ("update",), "show_commands": ("show_commands",), "privileged": ("privileged",),
    "reloads": ("reload",), "console_ztp": ("console",), "credential_profiles": ("credential",),
    "topology_expected": ("expected",), "topology_layout": ("layout",), "saved_views": ("view",),
    "reveals": ("reveal",), "host_keys": ("hostkey",), "netbox": ("netbox",),
    "grafana_writes": ("grafana",), "heartbeat_windows": ("heartbeat",), "ai_calls": ("ai_call",),
    "installation_settings": ("setting",), "sdn_operations": ("sdn",),
    "alert_rule_changes": ("alert_rule",),
}

#: The sources that cannot be asked for rows older than a page's place, each with why: their
#: store's reader takes only a newest-N count. The reader asks them again for more (`GROWTH`
#: times as many, at most `ROUNDS` reads a load, never past `MAX_READ` rows), and a page that
#: needed more than that says so by name. Every other source keeps its rows at or before the
#: place (`_recent`, or git's ``--until``) BEFORE its newest-N cut, so one read reaches as far
#: back as the place is.
UNPAGED = {
    "receipts": "the receipts' reader (`receipts.read`) returns its newest N rows",
    "updates": "the updater's record (`update_op.history`) returns its newest N lines",
    "show_commands": "the runs' reader (`reads.runs`) stops at its newest N run files",
    "privileged": "the Tier 2 runs' reader (`privileged.runs`) stops at its newest N run files",
    "console_ztp": "the console runs' reader (`console_ztp.runs`) stops at its newest N files",
}
#: At most this many reads of one source for one load (the first, and three asking for more).
ROUNDS = 4
#: Each further read asks for this many times the rows of the one before.
GROWTH = 4
#: No read of one source asks for more rows than this (50 rows, grown three times).
MAX_READ = DEFAULT_LIMIT * GROWTH ** (ROUNDS - 1)

_CURSOR_ID = re.compile(r"^[A-Za-z0-9_-]{0,80}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def row_id(e: dict) -> str:
    """A row's stable id, its address on the page (``#<id>``) and the second half of the
    cursor: an AI call's own id (``ai-<hex>``, 15.14's link to its row); any other row the sha1
    of what makes it that row (kind, time, commit, devices, what). The same record read again
    has the same id."""
    call = re.sub(r"[^A-Za-z0-9_-]", "", str(e.get("call") or ""))[:64]
    if call:
        return call if call.startswith("ai-") else f"ai-{call}"
    import hashlib
    key = "\x1f".join([e.get("kind", ""), e.get("at", ""), e.get("sha", ""),
                       ",".join(e.get("devices") or []), e.get("what", "")])
    return "r-" + hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:16]


def parse_cursor(text: str) -> tuple:
    """``(cursor, error)`` from an address's ``before=<time>~<id>`` (Load more's): *cursor*
    ``(epoch, id)``, the page holding the rows older than it; None and the reason when it is
    not a time and an id (the filter then is not applied, and the page says so)."""
    from datetime import datetime
    text = str(text or "")
    if not text:
        return None, ""
    at, sep, rid = text.rpartition("~")
    try:
        when = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        when = None
    if not sep or when is None or not _CURSOR_ID.match(rid):
        return None, f"the place {text[:80]!r} is not a time and a row (Load more's before=)"
    if when.tzinfo is None:
        return None, f"the place {text[:80]!r} names no time zone"
    return (when.timestamp(), rid), ""


def parse_day(text: str) -> tuple:
    """``(cursor, error)`` from an address's ``on=YYYY-MM-DD`` (Jump to): the page holds the
    rows at or before the END of that day, UTC (the cursor is the next midnight, which no row
    at it passes)."""
    from datetime import datetime, timedelta, timezone
    text = str(text or "")
    if not text:
        return None, ""
    try:
        day = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc) \
            if _DAY.match(text) else None
    except ValueError:
        day = None
    if day is None:
        return None, f"the day {text[:40]!r} is not a date (YYYY-MM-DD)"
    return ((day + timedelta(days=1)).timestamp(), ""), ""


def after(events: list, cursor) -> list:
    """The rows of *events* (in the timeline's order: newest first, rows of one time in the
    order their stores hold them, which a read gives the same each time) that come after
    *cursor*, ``(epoch, id)``: every row older than its time, and of the rows AT its time those
    after the row with its id. Git's commits within one second keep git's order this way (a
    sort by id would shuffle them). A cursor whose row is no longer among them (or a day's,
    whose id is "") keeps the rows at its time whose id sorts below it."""
    t, rid = cursor
    at_t = [e["id"] for e in events if epoch(e["at"]) == t]
    later = set(at_t[at_t.index(rid) + 1:]) if rid in at_t else {i for i in at_t if i < rid}
    return [e for e in events if epoch(e["at"]) < t
            or (epoch(e["at"]) == t and e["id"] in later)]


def place(*cursors):
    """The earliest of the places given (a jumped-to day and Load more's cursor together:
    the page starts at whichever is further back), or None."""
    given = [c for c in cursors if c]
    return min(given) if given else None


def _read(name, source, ctx) -> dict:
    """One read of one source: its rows, each given its id, and whether the store holds more
    than it returned (*more*: it said it was cut, or it returned as many rows as it was asked
    for, which is a truncated read), and the oldest row it returned (*floor*; with none
    returned and more held, nothing below is known: +inf)."""
    try:
        got = source(ctx)
    except Exception as exc:                          # noqa: BLE001
        log.warning("history: source %s failed: %s", name, exc)
        return {"events": [], "errors": [f"the {name.replace('_', ' ')} record could not be "
                                         f"read ({type(exc).__name__}: {exc})"],
                "cut": [], "unborn": [], "more": False, "floor": None}
    events = list(got.get("events") or [])
    for e in events:
        e["id"] = row_id(e)
    more = bool(got.get("cut")) or len(events) >= ctx["limit"]
    floor = min((epoch(e["at"]) for e in events), default=float("inf") if more else None)
    # The last row the store returned at its oldest time: rows it did not return come after it.
    last = [e["id"] for e in events if epoch(e["at"]) == floor][-1:] or [""]
    return {"events": events, "errors": list(got.get("errors") or []),
            "cut": list(got.get("cut") or []), "unborn": list(got.get("unborn") or []),
            "more": more, "floor": floor, "last": last[0]}


def _short(r: dict, horizon: float, page_last: str) -> bool:
    """Whether read *r* stopped short of the page: its store holds rows it did not return, and
    those can sort inside the page, above its *horizon* (the last row's time). At the horizon's
    own time only when the page's last row is not this store's own last one returned (its
    unreturned rows of that time come after its returned ones, so after the page)."""
    if not r["more"] or r["floor"] is None:
        return False
    return r["floor"] > horizon or (r["floor"] == horizon and r["last"] != page_last)


def timeline(ref, device: str = "", person: str = "", kinds=None, since_days: str = "",
             limit: int = DEFAULT_LIMIT, members=None, unverified: bool = False,
             before=None, call: str = "", commit: str = "") -> dict:
    """THE reader (C369): ``{"events", "errors", "unreached", "unborn", "limit", "total",
    "more", "next", "people", "counts", "identity"}``, newest first. Both the History page and a
    device's History tab call it; the tab with *device* set. *kinds*: KIND_FILTERS keys to keep
    (None or empty: every kind); *since_days*: "" for all time. *people* and *counts* are of
    the rows before the person and kind filters, for the filters' choices. *members*: the
    list's devices as its caller read them (an empty network's is ``[]``, which keeps none of
    another network's rows); None reads the inventory here, for the stores every network
    shares (`SHARED_BY_DEVICE`, C1028), and filters no device out of the network's own.
    *unborn*: the records that live in the network's repository, for a network with no
    repository yet (C957): drawn as that state, once, never as errors.

    **Paging (15.14 part B).** *before* is the page's place, ``(epoch, id)`` (`parse_cursor`,
    `parse_day`, `place`): the page holds the newest *limit* rows older than it. Each source
    is asked for its newest rows at or before the place (``ctx["until"]``), the keyset
    (`after`: the time, then the row's id among the rows of that time) decides the rest, and
    *next* is the last row's place, Load more's cursor, when *more* rows are older. Each source read its own newest N, so the page is exact once
    every source that held more had reached back past the page's last row; one that had not
    is read again with `GROWTH` times as many (at most `ROUNDS` reads a load, `MAX_READ` rows
    a read), and one still short after that is named in *unreached*: older rows of it are not
    on this page or the next, said, never drawn as none. *call*: one AI call by its id (a
    feature's link to its row), whatever its age."""
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    since = (time.time() - int(since_days) * 86400) if str(since_days or "").isdigit() else None
    if call or commit:
        since = None
    inventory, inventory_error = _inventory(ref, members, device or "")
    ctx = {"ref": ref, "device": device or "", "limit": limit, "since": since,
           "members": set(members) if members is not None else None, "inventory": inventory,
           "until": before[0] if before else None, "call": call or "",
           "commit": commit or ""}
    # The kind filter keeps its rows BEFORE the newest-*limit* cut below: each source read its
    # own newest *limit*, so a golden older than the page's other rows is still found under
    # "Goldens" (the operator's walk, 2026-10-18, B; tests/test_history_kind_filter.py).
    wanted = {"ai_call"} if call else \
        {k for key in (kinds or ()) for k in KIND_FILTERS.get(key, ())}
    names = [n for n in SOURCES
             if not wanted or n not in SOURCE_KINDS or wanted & set(SOURCE_KINDS[n])]
    reused = name_reused(ref, device) if device else None
    # A read at or before the place returns the row the cursor names too (the last one shown),
    # which the keyset then leaves out: one more, so a page of *limit* is still read whole.
    first = min(limit + 1, MAX_READ) if before else limit
    asked, reads, pending = {n: first for n in names}, {}, list(names)
    for n_round in range(1, ROUNDS + 1):
        for name in pending:
            reads[name] = _read(name, SOURCES[name], dict(ctx, limit=asked[name]))
        events, people, counts = _kept(reads, ctx, device, person, wanted, unverified, call,
                                       before, reused)
        page = events[:limit]
        # Below the page's last row (a full page), or the Since bound, a source's unread rows
        # cannot change the page; above it, they can.
        horizon = epoch(page[-1]["at"]) if len(page) >= limit else float("-inf")
        if since is not None:
            horizon = max(horizon, since)
        page_last = page[-1]["id"] if len(page) >= limit else ""
        pending = [n for n in names if _short(reads[n], horizon, page_last)]
        if not pending or n_round == ROUNDS:
            break
        pending = [n for n in pending if asked[n] < MAX_READ]
        for n in pending:
            asked[n] = min(asked[n] * GROWTH, MAX_READ)
        if not pending:
            break
    unreached = [n for n in names if _short(reads[n], horizon, page_last)]
    errors = ([inventory_error] if inventory_error else []) + \
        [x for n in names for x in reads[n]["errors"]]
    unborn = [x for n in names for x in reads[n]["unborn"]]
    # Older rows exist when this load kept more than a page, or a source holds rows it did not
    # return that can still be inside the Since window (a source whose oldest row returned is
    # older than Since has none left inside it).
    more = len(events) > limit or any(
        reads[n]["more"] and (since is None or reads[n]["floor"] >= since)
        for n in names if n not in unreached)
    # *total*: the rows this load kept, the page's and those past it (board D's "of 41"; the
    # evidence pack's subset); never the store's own count, which paging does not read.
    return {"events": page, "errors": errors, "unborn": unborn, "limit": limit,
            "total": len(events),
            "unreached": [f"the {n.replace('_', ' ')} record, read to its newest {asked[n]}"
                          + (f" ({UNPAGED[n]})" if n in UNPAGED else "") for n in unreached],
            "more": bool(more and page),
            "next": f"{page[-1]['at']}~{page[-1]['id']}" if more and page else "",
            "people": people, "counts": counts, "identity": identity(events)}


def _kept(reads, ctx, device, person, wanted, unverified, call, before, reused) -> tuple:
    """``(events, people, counts)``: every row read, filtered as the address says, newest
    first, and after the page's place (`after`). Each row is a copy, so a read kept from an
    earlier round is filtered again unchanged."""
    events = [dict(e) for r in reads.values() for e in r["events"]]
    events = [e for e in events if _recent(ctx, e["at"]) and (not device or about(e, device))]
    # A name onboarded again starts its history at the name's retirement (C1420): the device
    # view only; History of every device keeps every row.
    if reused:
        events = _from_reuse(events, device, reused)
    for e in events:
        e.setdefault("id", row_id(e))
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
    if wanted:
        events = [e for e in events if e["kind"] in wanted]
    if call:
        events = [e for e in events if e.get("call") == call]
    if ctx.get("commit"):
        # One commit (C1775): its own row and every row naming it as the intent it deployed,
        # the links both ways between an intent change and its deploys.
        c = ctx["commit"]
        events = [e for e in events if str(e.get("sha") or "").startswith(c)
                  or str(e.get("intent_commit") or "").startswith(c)]
    if unverified:
        events = [e for e in events if "verified" in e and e["verified"] != "access"]
    # Newest first; rows of one time keep their stores' order (a stable sort), as before paging.
    events.sort(key=lambda e: epoch(e["at"]), reverse=True)
    if before:
        events = after(events, before)
    return events, people, counts
