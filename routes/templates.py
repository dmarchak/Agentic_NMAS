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

def _captured_golden(hostname: str):
    """The device's current golden config, or None."""
    from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
    entry = next((e for e in _list_golden_configs()
                  if e.get("hostname") == hostname), None)
    if not entry:
        return None, ""
    return _load_golden_config_file(entry["device_ip"]), entry.get("saved_at", "")


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

def _seed_and_commit(list_name: str, repo: str) -> dict:
    """Seed the library, and commit what seeding actually wrote.

    Seeding copies files in; it never committed them. The first thing that ran
    ``save_templates()`` afterwards — in practice the approval — swept the whole
    seeded library into a commit subjected ``template: approve <path>``. Two
    problems: a commit whose subject describes one file while it adds forty,
    and an approval that cannot be reviewed as a diff because the diff is the
    entire library.

    Seeding gets its own commit, with a subject that says what it is.
    """
    from modules.nsot import repo as repo_service, templates_repo

    result = templates_repo.seed_templates(repo)   # idempotent; never overwrites
    copied = result.get("copied") or []
    if not copied:
        return result
    commit = repo_service.save_templates(
        list_name, copied, actor="nmas",
        message=f"template: seed library ({len(copied)} file(s))")
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
    # matches its fingerprint. Dropping the record makes that explicit.
    approval.revoke(repo, rel_path)

    commit = repo_service.save_templates(
        list_name, [rel_path], actor=data.get("actor", "user"),
        message=data.get("message", ""))
    return jsonify({"ok": True, "path": rel_path, "commit": commit.get("commit", ""),
                    "approval_revoked": True})


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

    from modules.nsot import approval, templates_repo
    from modules.nsot.normalize import strip_for_roundtrip
    from modules.nsot.render_artifact import build_artifact

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)

    golden, golden_at = _captured_golden(hostname)
    running, running_at = _captured_running(list_name, hostname)
    source = golden or running
    if not source:
        return jsonify({"ok": False, "error": (
            "No captured configuration for this device. Save a golden config "
            "or run a backup first — this view never reads from the device.")}), 404

    platform = _platform_for(hostname)
    template = templates_repo.template_for_device(repo, hostname, platform)

    artifact = build_artifact(hostname, source, platform, template=template)
    approved = approval.is_approved(repo, template,
                                    {hostname: artifact.host_vars})
    if approved:
        artifact = build_artifact(hostname, source, platform, template=template,
                                  template_approved=True,
                                  host_vars=artifact.host_vars)

    def _diff(other, label):
        if not other:
            return {"available": False,
                    "message": f"No captured {label}. Use Refresh capture."}
        left = strip_for_roundtrip(other)
        right = strip_for_roundtrip(artifact.rendered_masked)
        lines = list(difflib.unified_diff(left, right,
                                          fromfile=f"{label} ({hostname})",
                                          tofile=f"rendered ({hostname})", lineterm=""))
        return {"available": True, "diff": "\n".join(lines), "changed": bool(lines)}

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
        golden, _ = _captured_golden(entry["device"])
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
        golden, _ = _captured_golden(entry["device"])
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

    repo = _repo_for(_active_list())
    devices = []
    for entry in templates_repo.devices_for_template(repo, rel_path):
        golden, _ = _captured_golden(entry["device"])
        if golden:
            devices.append({"device": entry["device"], "platform": entry["platform"],
                            "running_config": golden})
    result = approval.validate_template(repo, rel_path, devices)
    result.pop("host_vars_by_device", None)     # internal; large
    return jsonify(result)
