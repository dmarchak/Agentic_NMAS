"""nsot/template_bring.py — bring a network's stale template to the shipped version (C566, board B,
signed off 2026-10-07).

A template seeded into a network's library is never overwritten by the code that seeded it (a
local edit must survive), so a fix shipped later does not reach the network by itself: the
operator's walk of P1 found `_common.j2` an older shipped version, unedited, that renders none of
the profile's management section, and every plan said "nothing to send" (C565). This is the
person's way to bring the shipped file in, previewed and confirmed, offered only where nothing
local would be lost (`stale`: an older shipped version, unedited). "Edited and stale" is a merge a
person makes, named and never offered as one action.

The steps, as the manual's How it works page names them:

- ``compare``: the network's copy against the shipped file (`templates_repo.seed_status`), and
  the lines the shipped file adds and removes. Writes nothing.
- ``measure``: every device bound to a template that imports the file, rendered through the
  library as it is and with the shipped file in its place; what each device's render gains and
  loses, masked. The same per-device read the approval check makes. Writes nothing.
- ``confirm``: refused when the network's copy or the shipped file moved since the preview
  (both blobs), or the copy is no longer `stale`.
- ``write``: the shipped file written over the network's copy (`template_write.commit`).
- ``revoke``: every approval whose import closure holds the file, revoked with the reason, so
  no deploy renders through it until a person approves again on this page.
- ``commit``: the file and the revocations in one commit, as the person.

Nothing here contacts a device.
"""

import difflib
import logging
import os
import shutil
import tempfile

log = logging.getLogger(__name__)

STEPS = ("compare", "measure", "confirm", "write", "revoke", "commit")
#: How many changed lines a device's row carries per side (the counts are always whole).
LINES_SHOWN = 6


def _seed_state(repo: str, path: str) -> dict:
    from modules.nsot import templates_repo

    report = templates_repo.seed_status(repo)
    for f in list(report.get("files") or []) + list(report.get("unclassified") or []):
        if f["path"] == path:
            return f
    return {"path": path, "state": "unclassified", "reason": "not a shipped template"}


def importers(repo: str, path: str) -> list:
    """The committed templates whose import closure holds *path* (itself, when it is one)."""
    from modules.nsot import approval, approve_op

    return [t for t in approve_op.committed_templates(repo)
            if not t.split("/")[-1].startswith("_")
            and path in approval.template_closure(repo, t)]


def _render_both(list_name: str, repo: str, host: str, platform: str, path: str,
                 shipped_text: str, tmp_root: str):
    """``(lines now, lines with the shipped file)`` for one device, or ``None`` when it has no
    intent to render (bootstrap, or none committed)."""
    from modules.nsot import hostvars, profile, templates_repo
    from modules.nsot.deploy import render_for_deploy

    own = hostvars.read_committed(repo, host)
    if own is None or hostvars.is_bootstrap_only(own):
        return None
    intent = hostvars.hydrate_secrets(profile.effective_for(repo, list_name, host, own, platform),
                                      host, list_name)
    src = templates_repo.render_source(repo, host, platform)
    now = render_for_deploy(intent, platform, template_root=src["root"],
                            template_name=src["name"])
    then = render_for_deploy(intent, platform, template_root=tmp_root,
                             template_name=src["name"])
    return now.splitlines(), then.splitlines()


def preview(list_name: str, path: str) -> dict:
    """What bringing the shipped *path* in changes, and whether it may: ``{"ok", "path",
    "state", "why", "offered", "diff", "added", "removed", "importers", "devices",
    "unchanged", "not_measured", "copy_blob", "shipped_blob"}``. Writes nothing."""
    from modules.nsot import approve_op, templates_repo
    from modules.redact import redact_text

    repo = approve_op.repo_for(list_name)
    shipped_path = os.path.join(templates_repo.BUILTIN_ROOT, path)
    copy_path = os.path.join(templates_repo.templates_dir(repo), path)
    out = {"ok": True, "list": list_name, "path": path, "offered": False, "diff": [],
           "added": 0, "removed": 0, "importers": [], "devices": [], "unchanged": 0,
           "not_measured": [], "copy_blob": "", "shipped_blob": ""}
    if not os.path.isfile(shipped_path):
        return dict(out, ok=False, state="", why=f"{path} is not a shipped template")
    if not os.path.isfile(copy_path):
        return dict(out, ok=False, state="", why=f"{path} is not in {list_name}'s library")
    seed = _seed_state(repo, path)
    out["state"] = seed["state"]
    out["copy_blob"] = templates_repo._blob_of_file(copy_path)
    out["shipped_blob"] = templates_repo._blob_of_file(shipped_path)
    shipped = open(shipped_path, encoding="utf-8").read()
    copy = open(copy_path, encoding="utf-8").read()
    out["diff"] = [l for l in difflib.unified_diff(copy.splitlines(), shipped.splitlines(),
                                                    lineterm="", n=1)][2:]
    out["added"] = sum(1 for l in out["diff"] if l.startswith("+"))
    out["removed"] = sum(1 for l in out["diff"] if l.startswith("-"))
    if seed["state"] == "current":
        out["why"] = f"{path} is already the shipped version: nothing to bring in"
        return out
    if seed["state"] != "stale":
        out["why"] = (f"{path} is {seed['state'].replace('_', ' ')}"
                      + (f" ({seed['reason']})" if seed.get("reason") else "")
                      + ": only an older shipped version, unedited, is brought in as one action, "
                        "so nothing local is lost; anything else is a merge a person makes")
        return out
    out["importers"] = importers(repo, path)
    tmp = tempfile.mkdtemp(prefix="nmas-shipped-")
    try:
        root = os.path.join(tmp, "templates")
        shutil.copytree(templates_repo.templates_dir(repo), root)
        with open(os.path.join(root, path), "w", encoding="utf-8") as fh:
            fh.write(shipped)
        seen = set()
        for template in out["importers"]:
            for entry in templates_repo.devices_for_template(repo, template):
                host = entry["device"]
                if host in seen:
                    continue
                seen.add(host)
                try:
                    both = _render_both(list_name, repo, host, entry["platform"], path,
                                        shipped, root)
                except Exception as exc:                 # noqa: BLE001
                    out["not_measured"].append({"device": host,
                                                "why": f"{type(exc).__name__}: {exc}"})
                    continue
                if both is None:
                    out["not_measured"].append({"device": host, "why": "no committed intent"})
                    continue
                now, then = both
                gains = [l for l in then if l not in set(now)]
                loses = [l for l in now if l not in set(then)]
                if not gains and not loses:
                    out["unchanged"] += 1
                    continue
                out["devices"].append({
                    "device": host, "gains": len(gains), "loses": len(loses),
                    "gain_lines": [redact_text(l) for l in gains[:LINES_SHOWN]],
                    "lose_lines": [redact_text(l) for l in loses[:LINES_SHOWN]]})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out["offered"] = True
    return out


def bring(list_name: str, path: str, copy_blob: str, shipped_blob: str, actor: str) -> dict:
    """The confirm: refused, writing nothing, unless the network's copy and the shipped file are
    the ones previewed and the copy is still an older shipped version, unedited; else the
    shipped file written, the approvals over it revoked, both committed as *actor*."""
    from modules.nsot import approve_op, repo as repo_service, template_write, templates_repo

    repo = approve_op.repo_for(list_name)
    shipped_path = os.path.join(templates_repo.BUILTIN_ROOT, path)
    copy_path = os.path.join(templates_repo.templates_dir(repo), path)
    if not os.path.isfile(shipped_path) or not os.path.isfile(copy_path):
        return {"ok": False, "status": 404, "error": f"{path} is not both shipped and in "
                                                      f"{list_name}'s library: nothing written"}
    with repo_service.repo_lock(repo):
        now_copy = templates_repo._blob_of_file(copy_path)
        now_shipped = templates_repo._blob_of_file(shipped_path)
        if (now_copy, now_shipped) != ((copy_blob or "").strip(), (shipped_blob or "").strip()):
            return {"ok": False, "status": 409, "error": (
                f"Not brought in: the preview was of the network's copy {copy_blob[:10]} and "
                f"the shipped file {shipped_blob[:10]}; they are {now_copy[:10]} and "
                f"{now_shipped[:10]} now. Nothing was written: preview again.")}
        state = _seed_state(repo, path)["state"]
        if state != "stale":
            return {"ok": False, "status": 409, "error": (
                f"Not brought in: {path} is {state.replace('_', ' ')} now, not an older "
                "shipped version: nothing was written.")}
        got = template_write.commit(
            list_name, repo, path, open(shipped_path, encoding="utf-8").read(), actor=actor,
            message=f"template: {path} to the shipped version",
            why="was brought to the shipped version")
    return got
