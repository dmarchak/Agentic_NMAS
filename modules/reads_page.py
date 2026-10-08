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


def check(command: str, n_devices: int = 1) -> dict:
    """The command as typed: ``{"ok", "why", "heavy"}``. Empty is not ok and says nothing."""
    command = (command or "").strip()
    if not command:
        return {"ok": False, "why": "", "heavy": []}
    why = reads.refusal([command], n_devices)
    return {"ok": not why, "why": why, "heavy": [] if why else reads.warnings([command])}


def _when(ts) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


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
         "common": reads.COMMON, "sets": [], "recent": recent(list_name, host),
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
