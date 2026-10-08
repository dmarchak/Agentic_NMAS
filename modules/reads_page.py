"""What the read screens draw (NSOT_READS.md sections 3 and 4; boards A to E, signed off
2026-10-08), from the reads engine (`modules/nsot/reads.py`) and nothing else.

Ask the device (board A) is one card on the device page, in one of these states:

- ``idle``: the command box (checked as typed), the saved sets, the common reads, and the
  device's recent reads;
- ``running``: a run started as a job; the card listens for the run's end (`reads`), never a
  timer, and its Run is busy on itself;
- ``done``: the answer in place (every command the run asked of this device), with how long it
  took, the person on hover, and "Compare with the last answer";
- ``refused``: the command never ran, and why;
- ``unknown``: this server holds no record of the job (finished long ago, or a restart) and
  the run's record, by its id, is the answer when it exists.
"""

import re
import time

from modules.nsot import reads


def what_it_does(command: str) -> tuple:
    """``(words, title)`` for a command Tier 1 allows: most are reads; `send log` writes a line
    into the device's log, and a terminal setting lasts the session (NSOT_READS.md section 11)."""
    low = command.strip().lower()
    if low.startswith("send log"):
        return ("writes one log line", "Tier 1: one line into the device's log, nothing else")
    if low.startswith("term"):
        return ("this session only", "Tier 1: a terminal setting, ended with the session")
    return ("read-only", "Tier 1: a read")


def check(command: str, n_devices: int = 1, reason: str = "") -> dict:
    """The command as typed: ``{"ok", "why", "heavy", "does"}``. Empty is not ok and says
    nothing. A `send log` at 0 to 3 (C582, board C582) also carries ``urgent`` (its level):
    with no reason of `reads.REASON_WORDS` words it is not ok and says it needs one (never
    "refused", since a reason is all it lacks); with one, the policy's own answer stands."""
    from modules.readonly_commands import urgent_level
    command = (command or "").strip()
    if not command:
        return {"ok": False, "why": "", "heavy": [], "does": ("", "")}
    level = urgent_level(command)
    enough = len((reason or "").split()) >= reads.REASON_WORDS
    if level is not None and not enough:
        return {"ok": False, "why": "", "heavy": [], "does": ("", ""), "urgent": level,
                "needs_reason": True}
    why = reads.refusal([command], n_devices, "person", reason if level is not None else "")
    out = {"ok": not why, "why": why, "heavy": [] if why else reads.warnings([command]),
           "does": ("", "") if why else what_it_does(command)}
    if level is not None:
        out["urgent"] = level
    return out


def reason_part(rows: list, reason: str) -> dict:
    """C582's field, one per run: shown while any typed line is a `send log` at 0 to 3, with
    the most severe such level and whether every such line says TEST."""
    from modules.nsot.logging_path import level_words
    from modules.readonly_commands import says_test, urgent_level
    urgent = [(urgent_level(c), c) for c in rows if urgent_level(c) is not None]
    if not urgent:
        return {"needed": False, "value": reason or ""}
    level = min(lv for lv, _c in urgent)
    return {"needed": True, "value": reason or "", "level": level,
            "level_words": level_words(level),
            "has_test": all(says_test(c) for _lv, c in urgent)}


def _when(ts) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


def _sets(list_name: str) -> list:
    """The network's saved sets for Ask the device to offer (each opens Show commands on this
    device: a set holds several commands, the card's box one)."""
    from modules.nsot import command_sets
    try:
        return command_sets.committed(list_name)["sets"]
    except Exception:                                 # noqa: BLE001 (offered, never required)
        return []


def outcome_words(record: dict, host: str) -> dict:
    """``{"state", "words"}``: one device's outcome in a run, as a row says it."""
    if record.get("state") == "refused":
        return {"state": "refused", "words": "refused: nothing was asked"}
    if record.get("state") == "running":
        return {"state": "running", "words": "reading"}
    r = (record.get("results") or {}).get(host) or {}
    state = r.get("state", "")
    if state == reads.ANSWERED:
        cut = any(a.get("cut") for a in r.get("answers") or [])
        return {"state": "cut" if cut else "answered",
                "words": "answered, an answer cut at the cap" if cut else "answered"}
    if state == reads.SKIPPED:
        return {"state": "skipped", "words": f"skipped: {r.get('why', '')}"}
    return {"state": state or "failed", "words": r.get("why") or state or "no outcome recorded"}


def recent(list_name: str, host: str, limit: int = 10) -> dict:
    got = reads.runs(list_name, device=host, limit=limit)
    rows = [{"id": r["id"], "at": _when(r.get("started_at")), "who": reads.actor_words(r),
             "commands": r.get("commands") or [], "devices": len(r.get("devices") or []),
             **outcome_words(r, host)} for r in got["runs"]]
    return {"rows": rows, "unreadable": got["unreadable"]}


def answers(record: dict, host: str) -> list:
    """Every answer *host* gave in *record*, in the run's command order, with what the card
    needs to draw it (and to offer the comparison)."""
    out = []
    for c in record.get("commands") or []:
        a = reads.answer_of(record, host, c) or {}
        prev = reads.previous(record["list"], host, c, record["id"]) \
            if a.get("state") == reads.ANSWERED else None
        out.append({"command": c, "state": a.get("state", ""), "answer": a.get("answer", ""),
                    "archived": a.get("state") == reads.ANSWERED and "answer" not in a,
                    "why": a.get("why", ""), "cut": a.get("cut", False),
                    "bytes": a.get("bytes", 0), "took_s": a.get("took_s"),
                    "previous": ({"id": prev["id"], "at": _when(prev.get("started_at")),
                                  "who": reads.actor_words(prev)} if prev else None)})
    return out


def ask(list_name: str, host: str, *, command: str = "", job: str = "", run_id: str = "",
        compare: str = "", reason: str = "") -> dict:
    """Ask the device's card, in its state (the module's docstring). *reason* is C582's, for a
    `send log` at 0 to 3."""
    from modules.nsot import capture_job

    c = {"host": host, "list": list_name, "command": command,
         "check": check(command, 1, reason), "reason": reason_part([command], reason),
         "common": reads.COMMON, "sets": _sets(list_name), "recent": recent(list_name, host),
         "state": "idle", "job": job, "run": run_id, "answers": [], "compare": None,
         "why": "", "at": "", "who": ""}
    if job:
        j = capture_job.get(job)
        if j is None and not run_id:
            c["state"] = "unknown"
            return c
        if j is not None and j["state"] == "running":
            c.update(state="running", elapsed_s=j.get("elapsed_s"))
            return c
        if j is not None and j["state"] == "failed":
            c.update(state="failed", why=j.get("error") or "the run failed")
            return c
        if j is not None:
            run_id = (j.get("payload") or {}).get("run") or run_id
    if run_id:
        record = reads.get(list_name, run_id)
        if record is None:
            c.update(state="unknown", run=run_id)
            return c
        c.update(run=run_id, at=_when(record.get("started_at")), who=reads.actor_words(record),
                 command=command or (record.get("commands") or [""])[0])
        reason = reason or record.get("reason", "")
        c.update(check=check(c["command"], 1, reason), reason=reason_part([c["command"]], reason),
                 reason_recorded=record.get("reason", ""))
        if record.get("state") == "refused":
            c.update(state="refused", why=record.get("refused", ""))
            return c
        if record.get("state") == "running":
            c["state"] = "running"
            return c
        c["outcome"] = outcome_words(record, host)
        c["answers"] = answers(record, host)
        c["state"] = "done"
        if compare:
            a = next((x for x in c["answers"] if x["command"] == compare), None)
            prev = reads.get(list_name, a["previous"]["id"]) if a and a["previous"] else None
            old = (reads.answer_of(prev, host, compare) or {}).get("answer", "") if prev else ""
            c["compare"] = ({"command": compare, "lines": reads.compare(old, a["answer"]),
                             "previous": a["previous"]} if prev else
                            {"command": compare, "lines": [], "previous": None})
    return c


# =========================================================================== Show commands
#
# Boards B to E: many devices at once. Picking devices by name, role, platform and site; one or
# more commands (or a saved set); the run as a job; the result led by a summary, its answers
# grouped (devices whose masked answers are identical form one group, by the answer's SHA-256),
# collapsed; two devices side by side; only the differences against a group.

#: Devices named in the pick card before "and N more" (the large-fleet rule: never one long list).
SHOWN_DEVICES = 30


def _inventory(list_name: str) -> list:
    from modules.device import load_saved_devices
    from modules.nsot import listref
    from modules.nsot.platform import platform_for_device
    out = []
    for d in load_saved_devices(listref.resolve(list_name).csv_path):
        out.append({"name": d.get("hostname", ""), "platform": platform_for_device(d) or "",
                    "role": d.get("role", "") or "", "site": d.get("site", "") or ""})
    return [d for d in out if d["name"]]


def _matches(d: dict, q: str, role: str, platform: str, site: str) -> bool:
    import fnmatch
    q = (q or "").strip().lower()
    if q:
        name = d["name"].lower()
        if not any((fnmatch.fnmatch(name, p) if "*" in p or "?" in p else p in name)
                   for p in (x.strip() for x in q.split(",")) if p):
            return False
    return ((not role or d["role"] == role) and (not platform or d["platform"] == platform)
            and (not site or d["site"] == site))


def fingerprint(devices: list) -> str:
    """The devices a card showed, as one value its form carries: the run computes the match
    again and is refused, naming both counts, when it moved (never 900 names in a form)."""
    import hashlib
    return hashlib.sha256("\n".join(sorted(devices)).encode("utf-8")).hexdigest()[:16]


def pick(list_name: str, *, q: str = "", role: str = "", platform: str = "", site: str = "",
         commands=None, reason: str = "", message: str = "", error: str = "") -> dict:
    """The pick card (board B): the filters with their choices, the devices they match (the
    run asks exactly these), the commands each checked, the saved sets, and whether Run may
    be pressed (every command a read, at least one device). *reason* is C582's: the run's
    one stated reason, for a `send log` at 0 to 3."""
    from modules.nsot import command_sets
    inv = _inventory(list_name)
    matched = [d for d in inv if _matches(d, q, role, platform, site)]
    rows = [c for c in (commands or []) if c is not None] or [""]
    checks = [check(c, max(2, len(matched)), reason) for c in rows]
    filled = [c.strip() for c in rows if c.strip()]
    sets = command_sets.committed(list_name)
    return {"list": list_name, "q": q, "role": role, "platform": platform, "site": site,
            "roles": sorted({d["role"] for d in inv if d["role"]}),
            "platforms": sorted({d["platform"] for d in inv if d["platform"]}),
            "sites": sorted({d["site"] for d in inv if d["site"]}),
            "total": len(inv), "devices": [d["name"] for d in matched],
            "fingerprint": fingerprint([d["name"] for d in matched]),
            "shown": [d["name"] for d in matched[:SHOWN_DEVICES]],
            "rows": [{"command": c, "check": k} for c, k in zip(rows, checks)],
            "reason": reason_part(filled, reason),
            "heavy": reads.warnings(filled), "can_run": bool(matched and filled) and all(
                k["ok"] for c, k in zip(rows, checks) if c.strip()),
            "max_commands": reads.MAX_COMMANDS, "workers": reads.max_workers(list_name),
            **_logging_test(matched),
            "sets": sets["sets"], "sets_unreadable": sets["unreadable"],
            "message": message, "error": error}


def _logging_test(matched: list) -> dict:
    """Board F's button: on when a device matches and Loki is configured, else why."""
    from modules.nsot import logging_path
    loki = logging_path.loki_configured()
    why = ("" if matched and loki else
           "Choose at least one device" if loki else
           "Loki is not configured (Settings, Integrations), so nothing could watch for the line")
    return {"can_test": not why, "test_why": why, "test_command": logging_path.LEVEL,
            "test_wait": logging_path.WAIT_SECONDS}


#: The order a logging-path result is drawn in: what to act on first (board F, 8f), and each
#: outcome's colour. An expectation exists here (the line arrives), so colour means something;
#: "unknown" (Mercury could not look) is neither.
LP_ORDER = (("not received", "danger"), ("not sent", "warn"), ("unknown", "muted"),
            ("received", "ok"))


def logging_view(record: dict, running: bool, lost: bool = False) -> dict:
    """Board F's region for a logging-path run: ``sending`` (the engine is sending), ``watching``
    (Loki asked as lines arrive) or ``done``, with each outcome's group."""
    from modules.nsot import logging_path
    lp = record.get("logging_path") or {}
    hosts = record.get("devices") or []
    sent = len(record.get("results") or {})
    v = {"total": len(hosts), "sent": sent, "token": lp.get("token") or
         logging_path.token(record["id"]),
         # A run recorded before C587 sent at informational; its record names no level.
         "level": lp.get("level", logging_path.LEVEL),
         "wait": logging_path.WAIT_SECONDS, "groups": [], "counts": [], "lost": False,
         "received": []}
    if lp.get("state") != "done" and lost:
        # The job that sent and watched is gone (a restart): said, never drawn as running.
        v.update(state="watching", lost=True,
                 received=sorted((lp.get("received") or {}).items()))
        return v
    if running or record.get("state") == "running":
        v["state"] = "sending"
        return v
    if lp.get("state") != "done":
        received = lp.get("received") or {}
        v.update(state="watching", received=sorted(received.items()),
                 until=lp.get("until_iso", ""), waiting=max(0, sent - len(received)))
        return v
    v["state"] = "done"
    results = lp.get("results") or {}
    for outcome, kind in LP_ORDER:
        rows = sorted(({"host": h, **r} for h, r in results.items() if r.get("state") == outcome),
                      key=lambda x: x["host"])
        if not rows:
            continue
        group = {"state": outcome, "kind": kind, "rows": rows}
        if outcome == "received":
            afters = [x.get("after_s", 0) for x in rows]
            group["range"] = (min(afters), max(afters))
        v["groups"].append(group)
        v["counts"].append({"state": outcome, "kind": kind, "n": len(rows)})
    return v


def recent_runs(list_name: str, limit: int = 20) -> dict:
    got = reads.runs(list_name, limit=limit)
    return {"rows": [{"id": r["id"], "at": _when(r.get("started_at")), "who": reads.actor_words(r),
                      "commands": r.get("commands") or [], "devices": len(r.get("devices") or []),
                      "state": r.get("state"), "refused": r.get("refused", ""),
                      "words": (r.get("summary") or {}).get("words", "")} for r in got["runs"]],
            "unreadable": got["unreadable"]}


#: A table's columns in its header line: names separated by two spaces or more ("Dead Time" is
#: one name). IOS prints its tables fixed-width, so a column is the span from its name to the
#: next one's (the last to the line's end).
_COLUMNS = re.compile(r"\S+(?: \S+)*")
#: What an ignored column's characters become when grouping and comparing (board C2, 8t).
IGNORED = "·"
#: "Compare against" offers "the most common answer" only when this many devices share it.
COMMON_AT_LEAST = 2


def _first_line(answer: str) -> str:
    return next((ln for ln in (answer or "").splitlines() if ln.strip()), "")


def columns(answers: list) -> dict:
    """``{"header", "spans": [(name, start, end)], "names"}`` for a command's answers: the header
    line most of them share (at least two answers, two columns), or ``{}`` when there is none
    (C580: the columns a person may tick to ignore)."""
    counts = {}
    for a in answers:
        line = _first_line(a)
        if len(_COLUMNS.findall(line)) >= 2:
            counts[line] = counts.get(line, 0) + 1
    if not counts:
        return {}
    header, n = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    if n < 2:
        return {}
    found = list(_COLUMNS.finditer(header))
    spans = [(m.group(0), m.start(), found[i + 1].start() if i + 1 < len(found) else None)
             for i, m in enumerate(found)]
    return {"header": header, "spans": spans, "names": [s[0] for s in spans]}


def normalise(answer: str, cols: dict, ignore: list) -> str:
    """*answer* with each ignored column's characters replaced by `IGNORED`, on the lines after
    its header; an answer without that header line is returned as it is."""
    if not cols or not ignore or _first_line(answer) != cols["header"]:
        return answer
    spans = [(s, e) for name, s, e in cols["spans"] if name in ignore]
    out, past = [], False
    for line in answer.splitlines():
        if past:
            chars = list(line)
            for s, e in spans:
                for i in range(s, len(chars) if e is None else min(e, len(chars))):
                    if not chars[i].isspace():
                        chars[i] = IGNORED
            line = "".join(chars)
        elif line == cols["header"]:
            past = True
        out.append(line)
    return "\n".join(out)


def _groups(record: dict, command: str, ignore: list = None) -> dict:
    """``{"groups": [{"devices", "answer", "cut", "bytes", "sha", "archived", "empty"}],
    "failed": [(host, why)], "skipped": [(host, why)], "unknown": [(host, why)], "columns"}`` for
    one command, the largest group first. Answers group when the whole masked answer is the same,
    with the columns in *ignore* (recorded with the run, C580) blanked first; a cut or archived
    answer groups by its whole answer's SHA-256 alone."""
    import hashlib
    found, failed, skipped, unknown = [], [], [], []
    for host in record.get("devices") or []:
        r = (record.get("results") or {}).get(host)
        if r is None:
            continue                                   # still reading
        state = r.get("state")
        if state == reads.SKIPPED:
            skipped.append((host, r.get("why", "")))
            continue
        if state == reads.UNKNOWN:
            unknown.append((host, r.get("why", "")))
            continue
        a = reads.answer_of(record, host, command)
        if not a or a.get("state") != reads.ANSWERED:
            failed.append((host, (a or {}).get("why") or r.get("why") or "no answer"))
            continue
        found.append((host, a))
    cols = columns([a.get("answer", "") for _h, a in found if "answer" in a and not a.get("cut")])
    ignore = [n for n in (ignore or []) if n in cols.get("names", [])]
    by_key = {}
    for host, a in found:
        text = a.get("answer", "")
        shown, key = text, a["sha256"]
        if ignore and "answer" in a and not a.get("cut"):
            shown = normalise(text, cols, ignore)
            if shown != text:
                key = hashlib.sha256(shown.encode("utf-8")).hexdigest()
        g = by_key.setdefault(key, {"devices": [], "answer": shown, "cut": a.get("cut", False),
                                    "bytes": a.get("bytes", 0), "sha": key,
                                    "archived": "answer" not in a,
                                    "empty": "answer" in a and not text.strip(),
                                    "lines": len([ln for ln in text.splitlines() if ln.strip()])})
        g["devices"].append(host)
    groups = sorted(by_key.values(), key=lambda g: (-len(g["devices"]), g["devices"]))
    return {"groups": groups, "failed": failed, "skipped": skipped, "unknown": unknown,
            "columns": cols, "ignore": ignore}


def _side(answer: str, other: str) -> list:
    """``[(line, only_here)]``: *answer*'s lines, each marked when *other* lacks it."""
    theirs = set((other or "").splitlines())
    return [(line, line not in theirs) for line in (answer or "").splitlines()]


def _against(groups: list, against: str):
    """The reference group a person CHOSE (C577): a device's group, or the most common answer
    when at least `COMMON_AT_LEAST` devices share it; None when nobody was chosen."""
    if against == "@common":
        return groups[0] if groups and len(groups[0]["devices"]) >= COMMON_AT_LEAST else None
    if against:
        return next((g for g in groups if against in g["devices"]), None)
    return None


def _vs(group: dict, ref: dict) -> dict:
    """How *group* stands against the chosen reference, in counts of lines (never a colour)."""
    if group is ref:
        return {"same": True}
    mine = set((group["answer"] or "").splitlines())
    theirs = set((ref["answer"] or "").splitlines())
    return {"same": False, "only_ref": len(theirs - mine), "only_here": len(mine - theirs)}


def result(list_name: str, run_id: str, *, job: str = "", find: str = "", text: str = "",
           show: str = "grouped", left: str = "", right: str = "", command: str = "",
           against: str = "") -> dict:
    """The run's page (boards C, D and C2): running with its progress, or the summary and every
    command's groups, filtered; a side-by-side of two devices; only the differences against the
    reference a person chose (C577: never a default one)."""
    from modules.nsot import capture_job
    record = reads.get(list_name, run_id)
    c = {"list": list_name, "run": run_id, "job": job, "find": find, "text": text,
         "show": show if show in ("grouped", "differences", "failed") else "grouped",
         "against": against or "", "state": "unknown", "commands": [], "compare": None,
         "differences": None, "answered_devices": []}
    if record is None:
        return c
    j = capture_job.get(job) if job else None
    running = record.get("state") == "running" and (j is None or j["state"] == "running")
    if record.get("state") == "running" and job and j is None:
        running = False                                # the job is gone: a restart
        c["lost"] = True
    total = len(record.get("devices") or [])
    done = len(record.get("results") or {})
    summary = reads.summarise(record)
    c.update(state="refused" if record.get("state") == "refused" else
             "running" if running else "done",
             record={"at": _when(record.get("started_at")), "who": reads.actor_words(record),
                     "commands": record.get("commands") or [], "total": total, "done": done,
                     "refused": record.get("refused", ""), "reason": record.get("reason", ""),
                     # Board C582, 4: the level the reason allowed, named beside it.
                     "urgent": (reason_part(record.get("commands") or [], "")
                                .get("level_words", "")),
                     "took_s": (round(record["finished_at"] - record["started_at"], 1)
                                if record.get("finished_at") else None)},
             summary=summary)
    find_l, text_l = (find or "").strip().lower(), (text or "").strip()
    ignored = record.get("ignored") or {}
    answered = set()
    for cmd in record.get("commands") or []:
        choice = ignored.get(cmd) or {}
        g = _groups(record, cmd, choice.get("columns"))
        ref = _against(g["groups"], against)
        for gr in g["groups"]:
            answered.update(gr["devices"])
            gr["vs"] = _vs(gr, ref) if ref else None
        groups = g["groups"]
        if find_l:
            groups = [x for x in groups if any(find_l in h.lower() for h in x["devices"])]
        if text_l:
            groups = [x for x in groups if text_l in (x["answer"] or "")]
        n_answered = sum(len(x["devices"]) for x in g["groups"])
        c["commands"].append({
            "command": cmd, "groups": groups, "all_groups": g["groups"],
            "failed": g["failed"], "skipped": g["skipped"], "unknown": g["unknown"],
            "answered": n_answered, "distinct": len(g["groups"]),
            "empty": sum(len(x["devices"]) for x in g["groups"] if x["empty"]),
            "columns": g["columns"].get("names", []), "ignore": g["ignore"],
            "ignored_by": choice.get("by", ""), "ignored_at": _when(choice.get("at")),
            "reference": ref, "common_offered": bool(
                g["groups"] and len(g["groups"][0]["devices"]) >= COMMON_AT_LEAST)})
    c["answered_devices"] = sorted(answered)
    from modules.nsot import logging_path
    if record.get("purpose") == logging_path.PURPOSE and c["state"] != "refused":
        c["logging_path"] = logging_view(record, running, lost=bool(job and j is None))
    c["common_offered"] = any(x["common_offered"] for x in c["commands"])
    if left and right and command:
        choice = ignored.get(command) or {}
        g = _groups(record, command, choice.get("columns"))
        a = next((x["answer"] for x in g["groups"] if left in x["devices"]), "")
        b = next((x["answer"] for x in g["groups"] if right in x["devices"]), "")
        c["compare"] = {"command": command, "left": left, "right": right,
                        "left_lines": _side(a, b), "right_lines": _side(b, a)}
    if c["show"] == "differences":
        if not against:
            c["differences"] = None               # nobody chosen: the view says so
        else:
            diffs = []
            for x in c["commands"]:
                base = x["reference"]
                if base is None:
                    continue
                for gr in x["all_groups"]:
                    if gr is base:
                        continue
                    diffs.append({"command": x["command"], "devices": gr["devices"],
                                  "base": base["devices"], "empty": gr["empty"],
                                  "lines": reads.compare(base["answer"], gr["answer"])})
            c["differences"] = diffs
    return c


def ignore(list_name: str, run_id: str, command: str, names: list, actor: str) -> str:
    """Record the columns *actor* ticked to ignore when grouping *command*'s answers (C580): ``""``
    when recorded, else why. Only a column the answers' header line names is accepted."""
    record = reads.get(list_name, run_id)
    if record is None:
        return f"{list_name} holds no run {run_id}."
    if command not in (record.get("commands") or []):
        return f"{command!r} is not a command of this run."
    names = list(dict.fromkeys(n for n in (names or []) if n))
    known = _groups(record, command)["columns"].get("names", [])
    bad = [n for n in names if n not in known]
    if bad:
        return (f"{', '.join(bad)} is not a column of {command}'s answers (their header names "
                f"{', '.join(known) or 'none'}).")
    chosen = dict(record.get("ignored") or {})
    chosen[command] = {"columns": names, "by": actor, "at": time.time()}
    reads.annotate(list_name, run_id, "ignored", chosen)
    return ""
