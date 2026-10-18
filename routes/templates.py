"""The template library's shared helpers (Phase 3b). **Nothing here opens a socket to a
device.** Every comparison is against the device's committed golden, the store deploy and
restore read (C632: the backup store, and the "Refresh capture" that wrote to it, retired at
7.8).

Today's template editor and its routes (the library's listing, a file's read and save, the
render preview, the approval read, Approve and Validate under /templates) left at 7.8 on
2026-10-17 (P7-23; restore point tag `pre-remove/v1-editors`). Their home is Source of truth ›
Templates (`routes/templates_v2.py`). Kept, each with its callers: `artifact_for`, the one
pairing of a render with its approval, with `_captured_golden`, `_platform_for` and
`unknown_platform_words` (the intent editor's core, `modules/nsot/intent_edit.py`, and bulk
intent's render, `routes/templatize._bulk_render_and_eligible`); and `_seed_and_commit` (v2's
Seed the library…, `templates_v2.seed`).
"""

import logging
import os

from flask import request

log = logging.getLogger(__name__)


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _active_list(payload=None) -> str:
    from modules.config import get_current_list_name
    name = (payload or {}).get("list_name") or request.args.get("list_name") or ""
    return name.strip() or get_current_list_name()


# ---------------------------------------------------------------------------
# Captured configs — the only inputs. No device contact.
# ---------------------------------------------------------------------------

def _captured_golden(hostname: str, list_name: str = ""):
    """The device's current golden config at repo HEAD, or None.

    Reads through the NSoT path -- ``repo.golden_at()``, the same function
    restore (`restore.py`) and the device page's golden reveal use -- NOT the legacy
    ``golden_configs/`` store.

    It used to locate the entry with `ai_assistant._list_golden_configs()`,
    which lists the deprecated `golden_configs/` directory and takes
    ``saved_at`` from each file's mtime. Measured on s1: the preview reported
    "captured 2026-09-15 22:35", exactly that file's mtime, while
    `config_repo/golden/s1.cfg` had been committed the same day.

    The date was provably wrong. Whether the *content* was also stale depended
    on a second lookup -- `_load_golden_config_file()` resolves through the
    manifest first and only falls back to the legacy scan -- so it was stale
    for any device the manifest could not resolve by IP, and correct for the
    rest. A view whose correctness varies per device by which of two stores
    answers first is the two-stores problem, not a date bug.

    That mattered beyond the diff, because whatever this returns is what the
    render's artifact is BUILT from (today's template preview's then; the intent
    editor's and bulk intent's now), so the render, its coverage and its
    deployability all rest on it. Reading one store, through the path deploy
    and restore use, removes the question rather than answering it (C632: the
    fallback to the newest file in `backups/` went with the backup store).

    The timestamp comes from the commit rather than the file's mtime, because
    in this repository the commit *is* the record: the `! Saved:` header was
    removed precisely so a save would not produce a diff on every write.
    """
    from modules.nsot import repo as _repo

    repo_dir = _repo_for(list_name or _active_list())
    content = _repo.golden_at(repo_dir, hostname, "HEAD")
    if content is None:
        return None, ""
    history = _repo.golden_history(repo_dir, hostname, limit=1)
    return content, (history[0]["timestamp"] if history else "")


def _row_for(hostname: str, list_name: str = "") -> dict:
    """The device's inventory row in *list_name* (C495: a caller that holds its list passes
    it; only one with none reads the active list), or ``{}``."""
    from modules.device import get_current_device_list, load_saved_devices

    if list_name:
        from modules.nsot import listref
        csv_path = listref.resolve(list_name).csv_path
    else:
        _name, csv_path = get_current_device_list()
    for dev in load_saved_devices(csv_path):
        if dev.get("hostname") == hostname:
            return dev
    return {}


def _platform_for(hostname: str, list_name: str = "") -> str:
    """The device's config dialect — not its Netmiko driver. A device not in
    the list has none: "" (C452), refused by name, never `cisco_ios` by default."""
    from modules.nsot.platform import platform_for_device

    row = _row_for(hostname, list_name)
    return platform_for_device(row) if row else ""


def unknown_platform_words(hostname: str, list_name: str = "") -> str:
    """Why *hostname*'s platform is refused, naming what was compared: its row's platform and
    device_type when the list holds one; when it holds none, THAT, naming the list read
    (C495: "its inventory row says no platform" was said of a row that was never found)."""
    from modules.config import get_current_list_name
    from modules.nsot.platform import DIALECTS, unknown_words

    row = _row_for(hostname, list_name)
    if row:
        return unknown_words(row)
    where = list_name or get_current_list_name()
    return (f"{hostname}: no row in {where}'s inventory, so its platform cannot be read; the "
            f"tool refuses rather than read it as another. The platforms the tool knows: "
            f"{', '.join(sorted(DIALECTS))}")


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

def artifact_for(hostname, capture, repo, platform, template, host_vars=None):
    """An artifact with its approval resolved. The ONE place that pairing is
    made.

    `build_artifact()` takes `template_approved` as a plain argument and
    defaults it to **False**, and `render_artifact.py` turns a False into
    *"template '<x>' is not approved for this device"* -- a message about the
    approval store, produced without consulting it. A caller that forgets the
    check does not get a missing feature; it gets a confident, wrong
    statement about something it never looked at.

    That is exactly what happened to the intent editor: it built artifacts
    directly, reported the device as not deployable, and read as an approval
    that had revoked itself overnight.

    **Approval is not asked about this device's host_vars, and must not be.**
    `template_fingerprint()` accepts `host_vars_by_device` and deliberately
    ignores it. Under scheme 3 the verdict is a statement about the template
    alone, so an edit to one device's intent cannot move it. Nothing is passed here, because this caller does not have the
    bound set and inventing a one-device stand-in would be a wrong value kept
    alive by the fact that nothing currently reads it.
    """
    from modules.nsot import approval
    from modules.nsot.render_artifact import build_artifact

    from modules.nsot import templates_repo

    # The network's own library, through the one resolver (C239): this path
    # rendered the BUILT-IN seeds while deploy rendered the library.
    src = templates_repo.render_source(repo, hostname, platform)
    approved = approval.is_approved(repo, src["template"])
    return build_artifact(hostname, capture, platform, template=src["template"],
                          template_approved=approved, host_vars=host_vars,
                          template_root=src["root"])


class StatusUnreadable(RuntimeError):
    """`git status` failed: what is untracked is not known, so nothing may be said of it."""


def _untracked_templates(repo: str) -> tuple:
    """``(untracked, modified)`` paths under ``templates/``.

    ``-uall`` matters: without it git reports a wholly-untracked directory as
    one entry (``?? templates/``) rather than the files inside it.

    Parsed by splitting on whitespace, not by column offset. Porcelain pads the
    status field to two characters — a tracked-but-modified file is `` M`` with
    a *leading* space — and ``git()`` strips its stdout, so the first line loses
    that space and a fixed ``line[3:]`` slice eats the first character of the
    path. It produced ``emplates/...``, which would have looked like a path that
    simply did not match anything.
    """
    from modules.nsot import repo as repo_service

    rc, out, err = repo_service.git(repo, "status", "--porcelain", "-uall",
                                    "--", "templates")
    untracked, modified = [], []
    if rc != 0:
        # Never "nothing untracked" (C931): an unreadable status is not an empty one.
        raise StatusUnreadable(f"the repository's status could not be read ({err or rc})")
    for line in out.splitlines():
        if not line.strip():
            continue
        code, _sep, rest = line.strip().partition(" ")
        path = rest.strip()
        if " -> " in path:                      # a rename reports both sides
            path = path.split(" -> ", 1)[1].strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if not path:
            continue
        (untracked if code == "??" else modified).append(path)
    return untracked, modified


def _seed_and_commit(list_name: str, repo: str, actor: str = "nmas") -> dict:
    """Seed the library, and commit whatever the repo is still missing.

    Seeding copies files in; it never committed them. The first thing that ran
    ``save_templates()`` afterwards — in practice the approval — swept the whole
    seeded library into a commit subjected ``template: approve <path>``. Two
    problems: a commit whose subject describes one file while it adds the whole
    library, and an approval that cannot be reviewed as a diff because the diff
    is that library.

    **The condition is repo state, not this run's filesystem activity.** Keying
    the commit off ``seed_templates()["copied"]`` was wrong in the one shape
    that matters: on a box where the old code had already copied the library in
    and committed nothing, ``copied`` comes back empty and the files stay
    untracked forever. ``copied`` describes what ``shutil`` did; ``git status``
    describes what the repository lacks, and only the second is the question.

    Only **untracked** paths are staged. A tracked-but-modified template is
    someone's in-progress edit — seeding never overwrites, so it cannot be
    seeding's doing — and sweeping it into a commit labelled "seed library"
    would mislabel it exactly the way this function exists to prevent.

    *actor*: who seeds: the verified person on v2's Seed the library… (cutover blocker 5;
    today's library listing, which seeded as ``nmas`` on its read, left at 7.8, P7-23).

    **A failure is said, never "nothing to add"** (C931): ``result["error"]`` names it when
    the status could not be read or the commit failed. The repository is made first, by the
    one init (`repo.init_repo`), so a network created before networks were born with one is
    a repository from its first seed: seeding is a write, and every write path inits.
    """
    from modules.nsot import repo as repo_service, templates_repo

    repo_service.init_repo(repo)
    result = templates_repo.seed_templates(repo)   # idempotent; never overwrites
    try:
        untracked, modified = _untracked_templates(repo)
    except StatusUnreadable as exc:
        log.error("templates: seeding committed nothing in %s: %s", repo, exc)
        return dict(result, untracked=[], uncommitted_edits=[], not_seeding=[],
                    error=f"nothing was committed: {exc}")
    # Only what the seed library provides (C345): any other untracked file under
    # templates/ (a damaged record's copy, a write's temp, a person's new file) is not
    # seeding's, and a commit labelled "seed library" must not carry it.
    seeded = templates_repo.seed_paths()
    others = [p for p in untracked if p.split("/", 1)[-1] not in seeded]
    untracked = [p for p in untracked if p not in others]
    if others:
        log.info("templates: seeding leaves %d untracked file(s) it did not provide: %s",
                 len(others), ", ".join(others))
    result["not_seeding"] = others
    result["untracked"] = untracked
    result["uncommitted_edits"] = modified
    if modified:
        log.info("templates: leaving %d modified template(s) for their own "
                 "commit: %s", len(modified), ", ".join(modified))
    if not untracked:
        return result

    commit = repo_service.save_templates(
        list_name, untracked, actor=actor,
        message=f"template: seed library ({len(untracked)} file(s))",
        paths=untracked)
    result["commit"] = commit.get("commit", "")
    if not commit.get("ok"):
        log.error("templates: seeding committed nothing: %s", commit.get("error"))
        result["error"] = f"nothing was committed: {commit.get('error') or 'the commit failed'}"
    elif not result["commit"]:
        # `_commit_paths` found nothing to commit after staging what was untracked: a
        # contradiction, said as the failure it is, never as "the network had every file".
        result["error"] = ("nothing was committed: git staged no change for the "
                           f"{len(untracked)} untracked file(s) it had just listed")
    return result

