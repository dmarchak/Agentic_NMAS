"""REVERT and RETRY, from the Device page (7.3): the two intent operations a
rollback leaves a person with, each previewed, confirmed, applied holding the
device, and recorded.

A rollback restores the DEVICE and leaves intent asserting the change that
failed, so the next plan is blocked (`.nsot/rolled_back.json`, containment:
the block stands while the failed lines are among the lines a plan would
send). There are exactly two ways out, and they mean opposite things:

  revert  the change was wrong: undo ONE intent commit's change, keeping every
          later commit (the inverse of that commit's own diff, a forward
          commit, `Source: revert`). A later commit that changed the same
          setting is refused with the paths named;
  retry   the change was right and the failure was elsewhere: authorise the
          blocked program to be sent again, with a stated reason in the shape
          of one (C140's rule), recorded in the retry log.

Both had routes and no screen, so neither was reachable by a person.

**The block is lifted by MEASUREMENT, never by the action's name** (C214,
found replacing the old route): the revert route cleared the
device's rollback note after ANY revert commit, so reverting an unrelated
change lifted the block on a failed one, the side effect `authorise_retry`'s
own docstring says must never happen. A revert now commits, then asks the one
classifier (`note_applicability`) whether the note still blocks, and clears it
only when it measurably does not. A retry is the one path that lifts a
standing block, and it says so.

Nothing here opens a session: intent and the record are read from git and the
repository.
"""

import difflib
import hashlib
import json
import logging

log = logging.getLogger(__name__)

SOURCE_REVERT = "revert"


def _repo(list_name: str) -> str:
    import os

    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _hash(*parts) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def _note(repo: str, hostname: str):
    """``(note, error)``: the device's rollback note as recorded, ``None``
    when it has none, and an error when the record cannot be read (which is
    not "no note": an unreadable record blocks every plan)."""
    from modules.nsot import hostvars

    data = hostvars._load_rolled_back(repo)
    if "__unreadable__" in data:
        return None, hostvars._unreadable_note(repo, data["__unreadable__"])["reason"]
    return data.get(hostname), ""


def block_state(list_name: str, hostname: str) -> dict:
    """Whether a rollback block stands on *hostname*, from ONE read of the record (the v2 device
    page's menu offers Revert and Retry only while one does, board 11): ``{"blocked", "why",
    "at"}``. An unreadable record is said as such, never as "no block"."""
    note, error = _note(_repo(list_name), hostname)
    if error:
        return {"blocked": False, "why": f"the rollback record could not be read ({error})",
                "at": ""}
    if not note:
        return {"blocked": False, "at": "",
                "why": f"no rollback block stands on {hostname}: nothing to revert or retry"}
    return {"blocked": True, "why": "", "at": note.get("at", "")}


def _note_public(note: dict) -> dict:
    return {"at": note.get("at", ""), "reason": note.get("reason", ""),
            "intent_commit": (note.get("intent_commit") or "")[:12],
            "commands": list(note.get("commands") or [])}


def retry_history(repo: str, hostname: str) -> dict:
    """``{count, last, unreadable}``: the retries recorded for *hostname*.
    An unreadable log is said, never counted as none."""
    import os

    from modules.nsot.hostvars import RETRY_LOG_REL

    path = os.path.join(repo, RETRY_LOG_REL)
    if not os.path.exists(path):
        return {"count": 0, "last": None, "unreadable": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh)
        if not isinstance(entries, list):
            raise ValueError("not a list")
    except (OSError, ValueError) as exc:
        return {"count": None, "last": None,
                "unreadable": f"{RETRY_LOG_REL} could not be read ({type(exc).__name__})"}
    mine = [e for e in entries if isinstance(e, dict) and e.get("device") == hostname]
    last = mine[-1] if mine else None
    return {"count": len(mine), "unreadable": "",
            "last": ({"at": last.get("at", ""), "actor": last.get("actor", ""),
                      "reason": last.get("reason", "")} if last else None)}


def _applicability(list_name: str, hostname: str) -> str:
    from routes.templatize import note_applicability
    return note_applicability(list_name, hostname)


# ---------------------------------------------------------------------------
# Revert
# ---------------------------------------------------------------------------

def revert_entry(list_name: str, hostname: str, sha: str = "") -> dict:
    """What reverting one of *hostname*'s intent commits would commit.

    The default commit is the one the device's rollback note was recorded
    against, when there is a note and it is still an intent commit; else the
    most recent. ``hash`` binds the target, the intent committed now and the
    document that would be committed."""
    from modules.nsot import hostvars
    from modules.nsot.device_ops import busy_text

    repo = _repo(list_name)
    commits = hostvars.intent_commits(repo, hostname, limit=20)
    note, note_error = _note(repo, hostname)
    noted = (note or {}).get("intent_commit") or ""
    default = next((c["sha"] for c in commits if noted and c["sha"].startswith(noted)), "")
    chosen = sha or default or (commits[0]["sha"] if commits else "")
    base = {"device": hostname, "busy": busy_text(list_name, hostname),
            "commits": [{"sha": c["sha"][:12], "subject": c["subject"], "date": c["date"],
                         "rolled_back": bool(noted) and c["sha"].startswith(noted)}
                        for c in commits],
            "note": _note_public(note) if note else None, "note_error": note_error,
            "selectable": False, "error": "", "hash": ""}
    if not commits:
        return {**base, "error": f"'{hostname}' has no committed intent: nothing to revert"}
    plan = hostvars.plan_revert(repo, hostname, chosen)
    base.update(target=(plan.get("target") or chosen)[:12], subject=plan.get("subject", ""))
    if not plan.get("ok"):
        return {**base, "conflicts": plan.get("conflicts", []), "error": plan["error"]}
    now_text, _committed = hostvars.committed_at_head(repo, hostname)
    document = hostvars.to_yaml(plan["document"])
    diff = [l for l in difflib.unified_diff((now_text or "").splitlines(),
                                             document.splitlines(), lineterm="", n=2)
            if not l.startswith(("---", "+++"))]
    return {**base, "selectable": True, "target_full": plan["target"],
            "changes": plan["changes"], "diff": diff,
            "kept": [{"sha": k[:12], "subject": s}
                     for k, s in zip(plan["kept_later_commits"], plan["kept_subjects"])],
            "hash": _hash(plan["target"], now_text or "", document),
            "_document": plan["document"]}


def public(entry: dict) -> dict:
    """The entry without what the route must not send."""
    return {k: v for k, v in entry.items() if not k.startswith("_")}


def revert_apply(list_name: str, hostname: str, sha: str, confirmed: str, actor: str) -> dict:
    """Revert the confirmed commit, holding the device (C98): one computation
    with the preview, refused if it moved; ONE commit of exactly this
    device's intent file as the verified person, `Source: revert`; a failed
    commit puts the file back as committed (C106's rule). Then the rollback
    note is measured, and cleared only if it no longer blocks."""
    from modules.nsot import device_ops, hostvars
    from modules.nsot.repo import save_host_vars

    repo = _repo(list_name)
    try:
        with device_ops.hold(list_name, hostname, "revert intent", actor):
            entry = revert_entry(list_name, hostname, sha)
            if entry["error"]:
                return {"device": hostname, "outcome": "refused", "reason": entry["error"],
                        "entry": public(entry)}
            if entry["hash"] != confirmed:
                return {"device": hostname, "outcome": "moved", "entry": public(entry),
                        "reason": (f"the intent or the commit to revert moved since the "
                                   f"preview ({confirmed} -> {entry['hash']})")}
            path = hostvars.committed_path(repo, hostname)
            try:
                hostvars.write_committed(repo, entry["_document"])
            except (hostvars.SecretLeak, hostvars.NonPrintableContent) as exc:
                return {"device": hostname, "outcome": "refused", "reason": str(exc),
                        "entry": public(entry)}
            target = entry["target_full"]
            save = save_host_vars(
                list_name, [hostname], actor=actor, source=SOURCE_REVERT,
                message=f"host_vars: {hostname} revert {target[:8]} ({entry['subject']})",
                extra_trailers=[f"Reverts: {target}"])
            if not save.get("ok"):
                hostvars.put_back_committed(repo, [path])
                return {"device": hostname, "outcome": "failed", "entry": public(entry),
                        "reason": save.get("error") or "the commit failed", "save": save}
            block = _after_block(list_name, repo, hostname, entry["note"])
            return {"device": hostname, "outcome": "reverted", "entry": public(entry),
                    "save": save, "block": block}
    except device_ops.DeviceBusy as exc:
        return {"device": hostname, "outcome": "busy",
                "reason": f"{exc}. Nothing was committed."}


def _after_block(list_name: str, repo: str, hostname: str, note) -> dict:
    """The rollback note after a committed revert, MEASURED."""
    from modules.nsot import hostvars

    if not note:
        return {"state": "none", "text": "There was no rollback block on this device."}
    applicability = _applicability(list_name, hostname)
    if applicability in ("no longer applies", "no committed intent"):
        cleared = hostvars.clear_rolled_back(repo, hostname)
        return {"state": "cleared" if cleared else "gone", "applicability": applicability,
                "text": ("The rollback block is lifted: the failed lines are no longer in the "
                         "program a plan would send, measured after the commit.")}
    if applicability == "blocking":
        return {"state": "standing", "applicability": applicability,
                "text": ("The rollback block STANDS: the failed lines are still in the program "
                         "a plan would send, so this revert did not remove them (they may come "
                         "from an earlier commit). Revert that one, or retry deliberately.")}
    return {"state": "unknown", "applicability": applicability,
            "text": ("Whether the rollback block still applies could not be measured (the "
                     "program could not be computed), so it is left standing; the next plan "
                     "decides.")}


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

def retry_entry(list_name: str, hostname: str) -> dict:
    """What authorising a retry would lift, and whether it blocks anything now.
    ``hash`` binds the note as recorded."""
    from modules.nsot.device_ops import busy_text

    repo = _repo(list_name)
    note, note_error = _note(repo, hostname)
    base = {"device": hostname, "busy": busy_text(list_name, hostname),
            "history": retry_history(repo, hostname), "selectable": False,
            "error": "", "hash": "", "note": None, "applicability": ""}
    if note_error:
        return {**base, "error": note_error}
    if not note:
        return {**base, "error": (f"{hostname} has no rollback block: nothing is blocked, so "
                                  "there is nothing to retry")}
    applicability = _applicability(list_name, hostname)
    entry = {**base, "note": _note_public(note), "applicability": applicability,
             "hash": _hash(json.dumps(note, sort_keys=True))}
    if applicability in ("no longer applies", "no committed intent"):
        return {**entry, "error": (
            "the block no longer applies (" + applicability + "): the failed lines are not in "
            "the program a plan would send now, so a retry would authorise nothing")}
    return {**entry, "selectable": True}


def retry_apply(list_name: str, hostname: str, confirmed: str, reason: str, actor: str) -> dict:
    """Authorise the retry, holding the device: the note must be the one
    previewed, and the reason must have the shape of one (C140)."""
    from modules.nsot import device_ops, hostvars
    from modules.nsot.authorisation import reason_problem

    problem = reason_problem({"line": "retry the rolled-back change", "reason": reason})
    if problem:
        return {"device": hostname, "outcome": "refused",
                "reason": "the stated reason: " + problem.split(": ", 1)[-1]}
    repo = _repo(list_name)
    try:
        with device_ops.hold(list_name, hostname, "authorise retry", actor):
            entry = retry_entry(list_name, hostname)
            if entry["error"]:
                return {"device": hostname, "outcome": "refused", "reason": entry["error"],
                        "entry": entry}
            if entry["hash"] != confirmed:
                return {"device": hostname, "outcome": "moved", "entry": entry,
                        "reason": (f"the rollback block changed since the preview "
                                   f"({confirmed} -> {entry['hash']})")}
            result = hostvars.authorise_retry(repo, hostname, actor=actor, reason=reason)
            if not result.get("ok"):
                return {"device": hostname, "outcome": "failed", "entry": entry,
                        "reason": result.get("error") or "the retry was not recorded"}
            return {"device": hostname, "outcome": "authorised", "entry": entry,
                    "record": {"at": result["record"]["at"], "actor": actor, "reason": reason}}
    except device_ops.DeviceBusy as exc:
        return {"device": hostname, "outcome": "busy",
                "reason": f"{exc}. Nothing was authorised."}
