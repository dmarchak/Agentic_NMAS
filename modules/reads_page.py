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


def check(command: str, n_devices: int = 1) -> dict:
    """The command as typed: ``{"ok", "why", "heavy", "does"}``. Empty is not ok and says
    nothing."""
    command = (command or "").strip()
    if not command:
        return {"ok": False, "why": "", "heavy": [], "does": ("", "")}
    why = reads.refusal([command], n_devices)
    return {"ok": not why, "why": why, "heavy": [] if why else reads.warnings([command]),
            "does": ("", "") if why else what_it_does(command)}


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
        compare: str = "") -> dict:
    """Ask the device's card, in its state (the module's docstring)."""
    from modules.nsot import capture_job

    c = {"host": host, "list": list_name, "command": command, "check": check(command),
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
        c["check"] = check(c["command"])
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
         commands=None, message: str = "", error: str = "") -> dict:
    """The pick card (board B): the filters with their choices, the devices they match (the
    run asks exactly these), the commands each checked, the saved sets, and whether Run may
    be pressed (every command a read, at least one device)."""
    from modules.nsot import command_sets
    inv = _inventory(list_name)
    matched = [d for d in inv if _matches(d, q, role, platform, site)]
    rows = [c for c in (commands or []) if c is not None] or [""]
    checks = [check(c, max(2, len(matched))) for c in rows]
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
            "heavy": reads.warnings(filled), "can_run": bool(matched and filled) and all(
                k["ok"] for c, k in zip(rows, checks) if c.strip()),
            "max_commands": reads.MAX_COMMANDS, "workers": reads.max_workers(list_name),
            "sets": sets["sets"], "sets_unreadable": sets["unreadable"],
            "message": message, "error": error}


def recent_runs(list_name: str, limit: int = 20) -> dict:
    got = reads.runs(list_name, limit=limit)
    return {"rows": [{"id": r["id"], "at": _when(r.get("started_at")), "who": reads.actor_words(r),
                      "commands": r.get("commands") or [], "devices": len(r.get("devices") or []),
                      "state": r.get("state"), "refused": r.get("refused", ""),
                      "words": (r.get("summary") or {}).get("words", "")} for r in got["runs"]],
            "unreadable": got["unreadable"]}


def _groups(record: dict, command: str) -> dict:
    """``{"groups": [{"devices", "answer", "cut", "bytes", "sha", "archived"}], "failed": [(host,
    why)], "skipped": [(host, why)], "unknown": [(host, why)]}`` for one command, the largest
    group first."""
    by_sha, failed, skipped, unknown = {}, [], [], []
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
        g = by_sha.setdefault(a["sha256"], {"devices": [], "answer": a.get("answer", ""),
                                            "cut": a.get("cut", False), "bytes": a.get("bytes", 0),
                                            "sha": a["sha256"], "archived": "answer" not in a})
        g["devices"].append(host)
    groups = sorted(by_sha.values(), key=lambda g: (-len(g["devices"]), g["devices"]))
    return {"groups": groups, "failed": failed, "skipped": skipped, "unknown": unknown}


def _side(answer: str, other: str) -> list:
    """``[(line, only_here)]``: *answer*'s lines, each marked when *other* lacks it."""
    theirs = set((other or "").splitlines())
    return [(line, line not in theirs) for line in (answer or "").splitlines()]


def result(list_name: str, run_id: str, *, job: str = "", find: str = "", text: str = "",
           show: str = "grouped", left: str = "", right: str = "", command: str = "",
           against: str = "") -> dict:
    """The run's page (boards C and D): running with its progress, or the summary and every
    command's groups, filtered; a side-by-side of two devices; only the differences against
    a group (by default the largest)."""
    from modules.nsot import capture_job
    record = reads.get(list_name, run_id)
    c = {"list": list_name, "run": run_id, "job": job, "find": find, "text": text,
         "show": show if show in ("grouped", "differences", "failed") else "grouped",
         "state": "unknown", "commands": [], "compare": None, "differences": None}
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
                     "refused": record.get("refused", ""),
                     "took_s": (round(record["finished_at"] - record["started_at"], 1)
                                if record.get("finished_at") else None)},
             summary=summary)
    find_l, text_l = (find or "").strip().lower(), (text or "").strip()
    for cmd in record.get("commands") or []:
        g = _groups(record, cmd)
        groups = g["groups"]
        if find_l:
            groups = [x for x in groups if any(find_l in h.lower() for h in x["devices"])]
        if text_l:
            groups = [x for x in groups if text_l in (x["answer"] or "")]
        c["commands"].append({"command": cmd, "groups": groups, "all_groups": g["groups"],
                              "failed": g["failed"], "skipped": g["skipped"],
                              "unknown": g["unknown"],
                              "answered": sum(len(x["devices"]) for x in g["groups"]),
                              "distinct": len(g["groups"])})
    if left and right and command:
        a = (reads.answer_of(record, left, command) or {}).get("answer", "")
        b = (reads.answer_of(record, right, command) or {}).get("answer", "")
        c["compare"] = {"command": command, "left": left, "right": right,
                        "left_lines": _side(a, b), "right_lines": _side(b, a)}
    if c["show"] == "differences":
        diffs = []
        for x in c["commands"]:
            base = next((gr for gr in x["all_groups"] if against and against in gr["devices"]),
                        x["all_groups"][0] if x["all_groups"] else None)
            if base is None:
                continue
            for gr in x["all_groups"]:
                if gr is base:
                    continue
                diffs.append({"command": x["command"], "devices": gr["devices"],
                              "base": base["devices"],
                              "lines": reads.compare(base["answer"], gr["answer"])})
        c["differences"] = diffs
    return c
