"""Template library blueprint — Phase 3b. Read-mostly.

Lists, reads, edits, renders, diffs, and approves templates. **Nothing here
opens a socket to a device.** Every comparison is against a captured artifact —
a golden config or a stored backup. "Refresh capture" delegates to the existing
backup/drift flow, so sessions stay in the module that owns them.

Deploy is Phase 3c and lives elsewhere.
"""

import logging
import os

from flask import Blueprint, jsonify, request

from modules.identity import request_actor

log = logging.getLogger(__name__)

bp = Blueprint("templates", __name__, url_prefix="/templates")


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
    restore (`restore.py`) and `/golden/version` use -- NOT the legacy
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

    That mattered beyond the diff, because `preview()` does
    ``source = golden or running``: whatever this returns is what the artifact
    is BUILT from, so the render, its coverage and its deployability all rest
    on it. Reading one store, through the path deploy and restore use, removes
    the question rather than answering it.

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


def _captured_running(list_name: str, hostname: str):
    """The most recent *captured* running config from backups. Never a live read."""
    from modules.config import get_list_data_dir

    backups = os.path.join(get_list_data_dir(list_name), "backups")
    if not os.path.isdir(backups):
        return None, ""
    candidates = [f for f in os.listdir(backups)
                  if f.startswith(hostname) and f.endswith((".cfg", ".txt"))]
    if not candidates:
        return None, ""
    newest = max(candidates, key=lambda f: os.path.getmtime(os.path.join(backups, f)))
    path = os.path.join(backups, newest)
    import time as _time
    stamp = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(os.path.getmtime(path)))
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(), stamp
    except OSError:
        return None, ""


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

    rc, out, _ = repo_service.git(repo, "status", "--porcelain", "-uall",
                                  "--", "templates")
    untracked, modified = [], []
    if rc != 0:
        return untracked, modified
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


def _seed_and_commit(list_name: str, repo: str) -> dict:
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
    """
    from modules.nsot import repo as repo_service, templates_repo

    result = templates_repo.seed_templates(repo)   # idempotent; never overwrites
    untracked, modified = _untracked_templates(repo)
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
        list_name, untracked, actor="nmas",
        message=f"template: seed library ({len(untracked)} file(s))",
        paths=untracked)
    result["commit"] = commit.get("commit", "")
    if not commit.get("ok"):
        log.error("templates: seeding committed nothing: %s", commit.get("error"))
    return result


@bp.route("", methods=["GET"])
def list_templates():
    from modules.nsot import templates_repo

    list_name = _active_list()
    repo = _repo_for(list_name)
    _seed_and_commit(list_name, repo)
    from modules.nsot import approval

    entries = []
    listed = templates_repo.list_templates(repo)
    try:
        bindings = templates_repo.load_bindings(repo)
    except templates_repo.BindingsUnreadable as exc:            # R14: said, never a guess
        return jsonify({"ok": False, "error": str(exc),
                        "templates": [dict(t, bound_devices=[]) for t in listed]}), 409
    platform_templates = [t["path"] for t in listed
                          if not t["path"].split("/")[-1].startswith("_")]
    for tpl in listed:
        bound = templates_repo.devices_for_template(repo, tpl["path"])
        entry = {**tpl, "bound_devices": [b["device"] for b in bound]}
        # A SHARED file (`_common.j2`) has no bindings and no approval of its
        # own, and was hidden from the panel -- so the only way to edit the
        # macros every template renders through was the shell, bypassing the
        # editor's syntax check and its recorded revocation. It is listed
        # now, with what editing it would revoke.
        if tpl["path"].split("/")[-1].startswith("_"):
            entry["shared"] = True
            entry["imported_by"] = [p for p in platform_templates
                                    if tpl["path"] in approval.template_closure(repo, p)]
        entries.append(entry)
    # NO approval state here, deliberately: `/templates/approval/<path>` is
    # the one answer. An `approved` key read from this listing is a missing
    # key, not a verdict.
    return jsonify({"ok": True, "templates": entries, "bindings": bindings})


@bp.route("/file/<path:rel_path>", methods=["GET"])
def read_template(rel_path):
    from modules.nsot import templates_repo

    from modules.nsot import hostvars

    repo = _repo_for(_active_list())
    # The text is read FROM the blob handed out as the BASE, the version the save sends back
    # (CONCURRENCY_AUDIT R14, as R2 for intent); a template not yet committed opens from its
    # file with an empty base.
    base = templates_repo.committed_blob(repo, rel_path)
    content = hostvars.blob_text(repo, base) if base else \
        templates_repo.read_template(repo, rel_path)
    if content is None:
        return jsonify({"ok": False, "error": "Template not found"}), 404
    bound = templates_repo.devices_for_template(repo, rel_path)
    return jsonify({"ok": True, "path": rel_path, "content": content, "base": base,
                    "bound_devices": [b["device"] for b in bound]})


def _template_moved(repo: str, rel_path: str, base: str, current: str):
    """The refusal when the template's committed version moved after the editor opened it:
    both blobs named, and who moved it. 409."""
    from modules.nsot import templates_repo

    last = templates_repo.last_commit(repo, rel_path)
    by = (f"{last.get('by') or 'someone'} in {last.get('commit')} "
          f"(\"{last.get('subject')}\", {last.get('at')})") if last else "a commit"
    return jsonify({
        "ok": False, "stage": "moved", "path": rel_path, "base": base, "current": current,
        "last_commit": last,
        "error": (f"Not saved: {rel_path} changed after you opened it. You opened "
                  f"{base[:8] or 'a version not yet committed'}; committed now is "
                  f"{current[:8] or 'nothing'}, by {by}. Nothing was written. Open the "
                  "template again to make your edit on their version.")}), 409


@bp.route("/file/<path:rel_path>", methods=["POST"])
def write_template(rel_path):
    """Save a template and commit it, bound to the version the editor opened (R14). Saving
    revokes any approval."""
    from modules.nsot import repo as repo_service, templates_repo

    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    list_name = _active_list(data)
    repo = _repo_for(list_name)
    if not isinstance(data.get("base"), str):
        return jsonify({"ok": False, "stage": "base", "error": (
            f"Not saved: this editor did not say which version of {rel_path} it opened, so "
            "the save could replace a commit made since. Nothing was written. Reload the "
            "page, open the template again and make the edit there.")}), 400
    # Compared, written, revoked and committed under ONE hold of the repository (R14).
    with repo_service.repo_lock(repo):
        current = templates_repo.committed_blob(repo, rel_path)
        if current != data["base"].strip():
            return _template_moved(repo, rel_path, data["base"].strip(), current)
        return _write_template_locked(repo, list_name, rel_path, content, data)


def _write_template_locked(repo: str, list_name: str, rel_path: str, content: str,
                           data: dict):
    from modules.nsot import approval, repo as repo_service, templates_repo

    result = templates_repo.write_template(repo, rel_path, content)
    if not result["ok"]:
        return jsonify(result), 400

    # Editing changes the content hash, so the stored approval no longer
    # matches its fingerprint. Recording WHY makes that explicit — an edit is
    # a reason, and "unapproved" on its own does not say an edit caused it.
    #
    # Every approval whose import closure contains this file, not just this
    # file's own. `_common.j2` holds the routing, interface and service macros
    # for BOTH platforms: editing it changes what every base.j2 renders, and
    # revoking only `_common.j2` (which has no approval of its own) would leave
    # them all standing.
    revoked, not_revoked = [], []
    for stored_path in approval.approved_templates(repo):
        if rel_path in approval.template_closure(repo, stored_path):
            done = approval.revoke(
                repo, stored_path,
                reason=(f"'{rel_path}' was edited, and this template imports "
                        "it; re-approval must validate the new content "
                        "against every bound device"),
                actor=request_actor())
            (revoked if done.get("ok") else not_revoked).append(stored_path)

    # The revocations are COMMITTED WITH THE EDIT (CONCURRENCY_AUDIT R13): they were left in
    # the working record, out of history, and the commit staged the template alone.
    commit = repo_service.save_templates(
        list_name, [rel_path] + ([".approvals.json"] if revoked else []),
        actor=request_actor(), message=data.get("message", ""))
    if not commit.get("ok"):
        return jsonify({"ok": False, "path": rel_path, "revoked": revoked,
                        "error": (f"The template is written but its commit failed "
                                  f"({commit.get('error')}): it is not in the repository's "
                                  "history. The deploy gate already counts the edited "
                                  "template as unapproved.")}), 500
    return jsonify({"ok": True, "path": rel_path, "commit": commit.get("commit", ""),
                    "approval_revoked": bool(revoked), "revoked": revoked,
                    "not_revoked": not_revoked})


@bp.route("/revoke/<path:rel_path>", methods=["POST"])
def revoke_approval(rel_path):
    """Withdraw a template's approval, recording why.

    Separate from editing. An approval is withdrawn when the *claim* it makes
    stops being true — which can happen without the template changing at all,
    as when a defect is found in what validated it.
    """
    from modules.nsot import approve_op

    data = request.get_json(silent=True) or {}
    result = approve_op.revoke(_active_list(data), rel_path,
                               (data.get("reason") or "").strip(), request_actor())
    status = result.pop("status")
    result.pop("actor", None)
    if not result.get("ok") and status == 400:
        return jsonify(result), 400
    return jsonify(result), status


@bp.route("/bindings", methods=["POST"])
def save_bindings():
    from modules.nsot import repo as repo_service, templates_repo

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)
    templates_repo.save_bindings(repo, data)
    commit = repo_service.save_templates(list_name, ["bindings.yml"],
                                         actor=request_actor(),
                                         message="template: update bindings")
    return jsonify({"ok": True, "commit": commit.get("commit", ""),
                    "bindings": templates_repo.load_bindings(repo)})


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

@bp.route("/preview/<path:hostname>", methods=["GET", "POST"])
def preview(hostname):
    """Render a device and diff it against golden and last-captured running.

    Both sides are captured artifacts. This endpoint opens no session.
    """
    import difflib

    from modules.nsot import approval, roundtrip, templates_repo
    from modules.nsot.render_artifact import build_artifact

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)

    golden, golden_at = _captured_golden(hostname, list_name)
    running, running_at = _captured_running(list_name, hostname)
    source = golden or running
    if not source:
        return jsonify({"ok": False, "error": (
            "No captured configuration for this device. Save a golden config "
            "or run a backup first — this view never reads from the device.")}), 404

    platform = _platform_for(hostname, list_name)
    from modules.nsot.platform import is_dialect
    if not is_dialect(platform):
        return jsonify({"ok": False,
                        "error": unknown_platform_words(hostname, list_name)}), 409
    template = templates_repo.template_for_device(repo, hostname, platform)

    artifact = artifact_for(hostname, source, repo, platform, template)

    def _diff(other, label):
        if not other:
            return {"available": False,
                    "message": f"No captured {label}. Use Refresh capture."}
        # `canonical_diff` is section-aware: it sorts children only where the
        # device does not care about order, and keeps the sequence in an ACL,
        # prefix-list, route-map or `ip sla`, where reordering changes what
        # the device does.
        #
        # The previous version normalised both sides and then compared them
        # with a flat `difflib`, which reported two things that are not
        # configuration differences: order in sections IOS reorders itself,
        # and indentation. The machinery to answer both already existed in
        # `roundtrip`; the preview simply was not using it, so a correct
        # render read as a broken one.
        diff, masked = roundtrip.canonical_diff(
            other, artifact.rendered_masked,
            fromfile=f"{label} ({hostname})", tofile=f"rendered ({hostname})",
            report_masked=True)
        return {"available": True, "diff": diff, "changed": bool(diff),
                # Counted, not merely absent. "Three lines could not be
                # compared" is a fact the operator can act on; silence about
                # them is a clean preview that quietly means less than it
                # appears to.
                "masked_not_compared": masked}

    return jsonify({
        "ok": True,
        **artifact.summary(),
        "rendered": artifact.rendered_masked,     # masked: never a deploy source
        "secrets_masked": True,
        "diff_vs_golden": {**_diff(golden, "golden"), "captured_at": golden_at},
        "diff_vs_running": {**_diff(running, "running config"),
                            "captured_at": running_at},
    })


@bp.route("/refresh-capture/<path:hostname>", methods=["POST"])
def refresh_capture(hostname):
    """Resolve which device to capture and hand the UI the existing endpoint.

    3b opens no sockets. Rather than duplicating connection code, this returns
    the address of the backup route that already owns it; the browser calls
    that and then reloads the preview.
    """
    from modules.device import get_current_device_list, load_saved_devices

    _name, csv_path = get_current_device_list()
    device = next((d for d in load_saved_devices(csv_path)
                   if d.get("hostname") == hostname), None)
    if device is None:
        return jsonify({"ok": False, "error": f"'{hostname}' is not in this list"}), 404

    # Point the UI at the existing backup route rather than opening a session
    # here. 3b owns no connection code: sessions stay in the module that owns
    # them, and this endpoint only resolves which device to capture.
    return jsonify({
        "ok": True,
        "hostname": hostname,
        "delegate_to": f"/device/{device.get('ip', '')}/backup_config",
        "method": "POST",
        "message": ("Triggering the existing backup flow; reload the preview "
                    "when it completes."),
    })


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------

@bp.route("/approval/<path:rel_path>", methods=["GET"])
def approval_status(rel_path):
    from modules.nsot import approval, templates_repo
    from modules.nsot.parsers import get_parser

    list_name = _active_list()
    repo = _repo_for(list_name)
    host_vars = {}
    for entry in templates_repo.devices_for_template(repo, rel_path):
        golden, _ = _captured_golden(entry["device"], list_name)
        if golden:
            host_vars[entry["device"]] = get_parser(entry["platform"]).parse(golden)
    return jsonify({"ok": True, "path": rel_path,
                    **approval.approval_status(repo, rel_path, host_vars)})


@bp.route("/approve/<path:rel_path>", methods=["POST"])
def approve(rel_path):
    """Approve a template (scheme 3): it must round-trip against AT LEAST ONE
    bound device, and every bound device's result is recorded as evidence.

    A bound device with no captured config is recorded as NOT VALIDATED
    instead of refusing the whole approval. Under scheme 2 the refusal was
    load-bearing, because the stored fingerprint covered the device set. Under
    scheme 3 it covers only the template, and the device is checked at its own
    deploy, so the refusal only kept a never-reached device's whole platform
    offline (D2)."""
    from modules.nsot import approve_op

    data = request.get_json(silent=True) or {}
    # What the person was SHOWN (CONCURRENCY_AUDIT R12): the row's approval state carries the
    # closure's fingerprint and Approve sends it back; one that moved since is refused.
    result = approve_op.approve(_active_list(data), rel_path, data.get("fingerprint"),
                                request_actor())
    status = result.pop("status")
    result.pop("actor", None)
    return jsonify(result), status


@bp.route("/validate/<path:rel_path>", methods=["POST"])
def validate(rel_path):
    """Dry-run the approval gate without approving."""
    from modules.nsot import approval, approve_op

    repo = _repo_for(_active_list())
    devices, _not_validated = approve_op.bound_captures(repo, rel_path)
    result = approval.validate_template(repo, rel_path, devices)
    result.pop("host_vars_by_device", None)     # internal; large
    return jsonify(result)


@bp.route("/seed_status", methods=["GET"])
def seed_status():
    """Is this network running a stale seed of any shipped template?

    OPEN_FINDINGS C6. Four states -- current, stale, edited,
    edited_and_stale -- and ``edited`` is a deliberate local change, not a
    defect. The list is looked up in the registry rather than through
    ``get_list_data_dir()``, which creates a directory: a READ must not be
    able to bring a list into existence from a typo.
    """
    from modules.config import LISTS_DIR, get_current_list_name
    from modules.device import get_device_lists
    from modules.nsot import templates_repo

    name = (request.args.get("list_name") or "").strip() or \
        get_current_list_name()
    match = next((l for l in get_device_lists() if l["name"] == name), None)
    if match is None:
        return jsonify({"ok": False, "error": f"no device list named {name!r}"}), 404
    repo = os.path.join(LISTS_DIR, match["filename"], "config_repo")
    report = templates_repo.seed_status(repo)
    report["list_name"] = name
    report["needs_attention"] = [e["path"] for e in report["files"]
                                 if e["state"] in ("stale", "edited_and_stale")]
    return jsonify(report)
