"""Saved command sets: a name and its read-only commands, per network, committed in the network's
repository (R3, the operator 2026-10-08; NSOT_READS.md section 5).

One file per set, `command_sets/<slug>.yml`: ``{name, description, commands}``. Committed as the
person who saved it (`repo._commit_paths`, which publishes), so a set has a history and a
reviewer. Every command is checked by the allowlist when saved and again when run (the reads
engine refuses a run whatever the set says). Readers take what is COMMITTED (C104): a set is read
at HEAD, never from the working tree. A file that cannot be read or is not a set is named, never
skipped in silence.
"""

import logging
import os
import re

log = logging.getLogger(__name__)

DIR = "command_sets"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:48]


def _repo(list_name: str) -> str:
    from modules.nsot import listref
    return listref.resolve(list_name).repo_dir


def _shape_problem(doc) -> str:
    from modules.nsot import reads
    if not isinstance(doc, dict):
        return "not a mapping"
    if not isinstance(doc.get("name"), str) or not doc["name"].strip():
        return "it names no set"
    cmds = doc.get("commands")
    if not isinstance(cmds, list) or not all(isinstance(c, str) and c.strip() for c in cmds):
        return "its commands are not a list of commands"
    return reads.refusal(cmds, 1)


def committed(list_name: str) -> dict:
    """``{"sets": [{"slug", "name", "description", "commands"}], "unreadable": [(file, why)]}``,
    by name, as committed at HEAD."""
    import yaml

    from modules.nsot.repo import git

    repo = _repo(list_name)
    rc, out, _err = git(repo, "ls-tree", "--name-only", "HEAD", f"{DIR}/")
    names = [n for n in out.splitlines() if n.endswith(".yml")] if rc == 0 else []
    sets, bad = [], []
    for rel in names:
        rc, text, err = git(repo, "show", f"HEAD:{rel}")
        if rc != 0:
            bad.append((rel, f"could not be read: {err.strip()[:120]}"))
            continue
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            bad.append((rel, f"is not YAML: {exc}"[:160]))
            continue
        why = _shape_problem(doc)
        if why:
            bad.append((rel, why))
            continue
        sets.append({"slug": os.path.basename(rel)[:-4], "name": doc["name"].strip(),
                     "description": str(doc.get("description") or ""),
                     "commands": [c.strip() for c in doc["commands"]]})
    return {"sets": sorted(sets, key=lambda s: s["name"].lower()), "unreadable": bad}


def save(list_name: str, name: str, commands: list, actor: str, description: str = "") -> dict:
    """Commit a new set as *actor*: ``{"ok", "error", "path", "commit"}``. A name already taken
    is refused naming it (a set is changed by a person deliberately, not overwritten)."""
    import yaml

    from modules.nsot import reads
    from modules.nsot import repo as R

    name = (name or "").strip()
    commands = [c.strip() for c in (commands or []) if c and c.strip()]
    s = slug(name)
    if not s:
        return {"ok": False, "error": "A set needs a name of letters or digits."}
    why = reads.refusal(commands, 1)
    if why:
        return {"ok": False, "error": f"Not saved: {why}"}
    if s in {x["slug"] for x in committed(list_name)["sets"]}:
        return {"ok": False, "error": f"Not saved: {list_name} already has a set named "
                                      f"{name!r} ({DIR}/{s}.yml)."}
    repo = _repo(list_name)
    rel = f"{DIR}/{s}.yml"
    text = yaml.safe_dump({"name": name, "description": description.strip(),
                           "commands": commands}, sort_keys=False, default_flow_style=False)
    with R.repo_lock(repo):
        os.makedirs(os.path.join(repo, DIR), exist_ok=True)
        from modules.filestore import write_atomic
        write_atomic(os.path.join(repo, rel), text)
        got = R._commit_paths(list_name, [rel], f"command set: {name}",            # noqa: SLF001
                              [f"Actor: {actor}"], "command-set")
    if not got.get("ok"):
        return {"ok": False, "error": f"The set was written and its commit failed: "
                                      f"{got.get('error')}", "path": rel}
    return {"ok": True, "path": rel, "commit": got.get("commit", "")}
