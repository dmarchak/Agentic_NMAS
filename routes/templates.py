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


def _platform_for(hostname: str) -> str:
    """The device's config dialect — not its Netmiko driver."""
    from modules.device import get_current_device_list, load_saved_devices
    from modules.nsot.platform import DEFAULT_PLATFORM, platform_for_device

    _name, csv_path = get_current_device_list()
    for dev in load_saved_devices(csv_path):
        if dev.get("hostname") == hostname:
            return platform_for_device(dev)
    return DEFAULT_PLATFORM


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
    `binding_fingerprint()` accepts `host_vars_by_device` and deliberately
    ignores it -- that ignoring IS the scheme-2 correction. The bound set is
    read from the repo, so the verdict is a statement about the template
    against every device it covers, and an edit to one device's intent cannot
    move it. Nothing is passed here, because this caller does not have the
    bound set and inventing a one-device stand-in would be a wrong value kept
    alive by the fact that nothing currently reads it.
    """
    from modules.nsot import approval
    from modules.nsot.render_artifact import build_artifact

    approved = approval.is_approved(repo, template)
    return build_artifact(hostname, capture, platform, template=template,
                          template_approved=approved, host_vars=host_vars)


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
    entries = []
    for tpl in templates_repo.list_templates(repo):
        bound = templates_repo.devices_for_template(repo, tpl["path"])
        entries.append({**tpl, "bound_devices": [b["device"] for b in bound]})
    return jsonify({"ok": True, "templates": entries,
                    "bindings": templates_repo.load_bindings(repo)})


@bp.route("/file/<path:rel_path>", methods=["GET"])
def read_template(rel_path):
    from modules.nsot import templates_repo

    repo = _repo_for(_active_list())
    content = templates_repo.read_template(repo, rel_path)
    if content is None:
        return jsonify({"ok": False, "error": "Template not found"}), 404
    bound = templates_repo.devices_for_template(repo, rel_path)
    return jsonify({"ok": True, "path": rel_path, "content": content,
                    "bound_devices": [b["device"] for b in bound]})


@bp.route("/file/<path:rel_path>", methods=["POST"])
def write_template(rel_path):
    """Save a template and commit it. Saving revokes any approval."""
    from modules.nsot import approval, repo as repo_service, templates_repo

    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    list_name = _active_list(data)
    repo = _repo_for(list_name)

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
    revoked = []
    for stored_path in approval.approved_templates(repo):
        if rel_path in approval.template_closure(repo, stored_path):
            approval.revoke(
                repo, stored_path,
                reason=(f"'{rel_path}' was edited, and this template imports "
                        "it; re-approval must validate the new content "
                        "against every bound device"),
                actor=data.get("actor", "user"))
            revoked.append(stored_path)

    commit = repo_service.save_templates(
        list_name, [rel_path], actor=data.get("actor", "user"),
        message=data.get("message", ""))
    return jsonify({"ok": True, "path": rel_path, "commit": commit.get("commit", ""),
                    "approval_revoked": bool(revoked), "revoked": revoked})


@bp.route("/revoke/<path:rel_path>", methods=["POST"])
def revoke_approval(rel_path):
    """Withdraw a template's approval, recording why.

    Separate from editing. An approval is withdrawn when the *claim* it makes
    stops being true — which can happen without the template changing at all,
    as when a defect is found in what validated it.
    """
    from modules.nsot import approval, repo as repo_service

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)
    reason = (data.get("reason") or "").strip()

    result = approval.revoke(repo, rel_path, reason=reason,
                             actor=data.get("actor", "user"))
    if not result.get("ok"):
        return jsonify(result), 400

    commit = repo_service.save_templates(
        list_name, [".approvals.json"], actor=data.get("actor", "user"),
        message=f"template: revoke approval for {rel_path}",
        paths=[os.path.join("templates", ".approvals.json")])
    return jsonify({**result, "commit": commit.get("commit", "")})


@bp.route("/bindings", methods=["POST"])
def save_bindings():
    from modules.nsot import repo as repo_service, templates_repo

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)
    templates_repo.save_bindings(repo, data)
    commit = repo_service.save_templates(list_name, ["bindings.yml"],
                                         actor=data.get("actor", "user"),
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

    platform = _platform_for(hostname)
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
    """Approve a template — only if it round-trips against every bound device."""
    from modules.nsot import approval, repo as repo_service, templates_repo

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)

    devices = []
    missing = []
    for entry in templates_repo.devices_for_template(repo, rel_path):
        golden, _ = _captured_golden(entry["device"], list_name)
        if not golden:
            missing.append(entry["device"])
            continue
        devices.append({"device": entry["device"], "platform": entry["platform"],
                        "running_config": golden})

    if missing:
        return jsonify({"ok": False, "error": (
            f"{len(missing)} bound device(s) have no captured config: "
            f"{', '.join(missing)}. A template cannot be approved against a "
            "device it has never been validated on.")}), 400

    result = approval.approve(repo, rel_path, devices,
                              actor=data.get("actor", "user"))
    if result["ok"]:
        repo_service.save_templates(list_name, [".approvals.json"],
                                    actor=data.get("actor", "user"),
                                    message=f"template: approve {rel_path}")
    return jsonify(result), (200 if result["ok"] else 400)


@bp.route("/validate/<path:rel_path>", methods=["POST"])
def validate(rel_path):
    """Dry-run the approval gate without approving."""
    from modules.nsot import approval, templates_repo

    list_name = _active_list()
    repo = _repo_for(list_name)
    devices = []
    for entry in templates_repo.devices_for_template(repo, rel_path):
        golden, _ = _captured_golden(entry["device"], list_name)
        if golden:
            devices.append({"device": entry["device"], "platform": entry["platform"],
                            "running_config": golden})
    result = approval.validate_template(repo, rel_path, devices)
    result.pop("host_vars_by_device", None)     # internal; large
    return jsonify(result)
