"""Golden config repository blueprint: timeline, diffs, baselines, migration."""

import logging
import os

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("golden", __name__, url_prefix="/golden")


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _active_list(payload=None) -> str:
    from modules.config import get_current_list_name
    name = (payload or {}).get("list_name") or request.args.get("list_name") or ""
    return name.strip() or get_current_list_name()


@bp.route("/history/<path:hostname>", methods=["GET"])
def history(hostname):
    """Promotion timeline for one device, following renames."""
    from modules.nsot.repo import get_ci_note, golden_history

    list_name = _active_list()
    repo = _repo_for(list_name)
    try:
        entries = golden_history(repo, hostname)
        for entry in entries:
            entry["ci"] = get_ci_note(repo, entry["sha"])
        return jsonify({"ok": True, "hostname": hostname, "list": list_name,
                        "history": entries})
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: history failed for %s", hostname)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/version/<path:hostname>", methods=["GET"])
def version(hostname):
    """One device's golden config at a given ref."""
    from modules.nsot.repo import golden_at

    ref = request.args.get("ref", "HEAD")
    content = golden_at(_repo_for(_active_list()), hostname, ref)
    if content is None:
        return jsonify({"ok": False,
                        "error": f"No golden config for {hostname} at {ref}"}), 404
    return jsonify({"ok": True, "hostname": hostname, "ref": ref, "config": content})


@bp.route("/diff/<path:hostname>", methods=["GET"])
def diff(hostname):
    """Unified diff of one device's golden config between two refs."""
    import difflib

    from modules.nsot.repo import golden_at

    repo = _repo_for(_active_list())
    ref_a = request.args.get("a", "")
    ref_b = request.args.get("b", "HEAD")
    if not ref_a:
        return jsonify({"ok": False, "error": "Parameter 'a' is required"}), 400

    left, right = golden_at(repo, hostname, ref_a), golden_at(repo, hostname, ref_b)
    if left is None or right is None:
        return jsonify({"ok": False,
                        "error": "One of the versions has no golden config"}), 404

    lines = list(difflib.unified_diff(
        left.splitlines(), right.splitlines(),
        fromfile=f"{hostname}@{ref_a}", tofile=f"{hostname}@{ref_b}", lineterm=""))
    return jsonify({"ok": True, "hostname": hostname, "a": ref_a, "b": ref_b,
                    "diff": "\n".join(lines), "changed": bool(lines)})


@bp.route("/baselines", methods=["GET"])
def baselines():
    """Network-wide restore points."""
    from modules.nsot.repo import devices_at, list_baselines

    repo = _repo_for(_active_list())
    try:
        entries = list_baselines(repo)
        for entry in entries:
            entry["device_count"] = len(devices_at(repo, entry["tag"]))
        return jsonify({"ok": True, "baselines": entries})
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/restore/preview", methods=["POST"])
def restore_preview():
    """What a restore would do — including which devices are skipped."""
    from modules.nsot.restore import plan_restore

    data = request.get_json(silent=True) or {}
    ref = (data.get("ref") or "").strip()
    if not ref:
        return jsonify({"ok": False, "error": "ref is required"}), 400
    return jsonify(plan_restore(_active_list(data), ref, data.get("devices")))


@bp.route("/restore/apply", methods=["POST"])
def restore_apply():
    """Queue a restore for approval. Never pushes directly."""
    from modules.nsot.restore import execute_restore

    data = request.get_json(silent=True) or {}
    ref = (data.get("ref") or "").strip()
    if not ref:
        return jsonify({"ok": False, "error": "ref is required"}), 400
    return jsonify(execute_restore(_active_list(data), ref, data.get("devices"),
                                   actor=data.get("actor", "user")))


@bp.route("/migrate/plan", methods=["GET", "POST"])
def migrate_plan():
    """Dry-run migration report. Writes nothing — this is the UI default."""
    from modules.nsot.migrate import plan

    data = request.get_json(silent=True) or {}
    try:
        return jsonify(plan(_active_list(data)))
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: migration plan failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/migrate/apply", methods=["POST"])
def migrate_apply():
    """Perform the migration. Requires an explicit confirm."""
    from modules.nsot.migrate import apply as apply_migration

    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({"ok": False,
                        "error": "Review the dry-run report and confirm first."}), 400
    try:
        result = apply_migration(_active_list(data),
                                 actor=data.get("actor", "user"))
        # A refused re-run is a conflict, not a server error and not a success.
        # The body carries the marker, so the UI can say when it happened.
        return jsonify(result), (409 if result.get("already_migrated") else 200)
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: migration failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/renames", methods=["GET"])
def renames():
    """Renames noticed by an inventory refresh but not yet committed."""
    from modules.inventory import pending_renames
    return jsonify({"ok": True, "pending": pending_renames(_active_list())})


@bp.route("/renames/sync", methods=["POST"])
def sync_renames():
    """Apply pending renames as their own commits."""
    from modules.inventory import sync_device_names_to_repo

    data = request.get_json(silent=True) or {}
    try:
        return jsonify(sync_device_names_to_repo(_active_list(data),
                                                 actor=data.get("actor", "user")))
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500
