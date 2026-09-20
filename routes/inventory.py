"""Inventory source blueprint.

Per-list source configuration, on-demand refresh, credential profiles, and the
stale-device view.
"""

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@bp.route("/source/<path:list_name>", methods=["GET"])
def get_source(list_name):
    """Source config plus freshness, skips, and warnings for the UI banner."""
    try:
        from modules.inventory import get_status, get_stale_devices
        from modules.inventory.source_config import load

        cfg = load(list_name)
        return jsonify({"ok": True, "config": cfg,
                        "status": get_status(list_name),
                        "stale_devices": get_stale_devices(list_name)})
    except Exception as exc:                  # noqa: BLE001
        log.exception("inventory: source lookup failed for '%s'", list_name)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/source/<path:list_name>", methods=["POST"])
def set_source(list_name):
    """Change a list's inventory source and filters."""
    try:
        from modules.inventory import invalidate, refresh_async
        from modules.inventory.source_config import SOURCE_NETBOX, save

        data = request.get_json(silent=True) or {}
        cfg = save(list_name, data)
        invalidate(list_name)
        if cfg["source"] == SOURCE_NETBOX:
            refresh_async(list_name)
        return jsonify({"ok": True, "config": cfg})
    except Exception as exc:                  # noqa: BLE001
        log.exception("inventory: could not save source for '%s'", list_name)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/refresh/<path:list_name>", methods=["POST"])
def refresh(list_name):
    """Refresh now, blocking, so the UI can report the result."""
    try:
        from modules.inventory import refresh_list
        return jsonify(refresh_list(list_name))
    except Exception as exc:                  # noqa: BLE001
        log.exception("inventory: refresh failed for '%s'", list_name)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/order/<path:list_name>", methods=["POST"])
def set_order(list_name):
    """Persist drag-and-drop ordering for a NetBox-sourced list.

    Local lists reorder by rewriting the CSV; NetBox lists have no CSV, so the
    order lives in source.json instead.
    """
    try:
        from modules.inventory import invalidate
        from modules.inventory.source_config import set_device_order

        data = request.get_json(silent=True) or {}
        order = data.get("order") or []
        cfg = set_device_order(list_name, order)
        invalidate(list_name)
        return jsonify({"ok": True, "order": cfg["device_order"]})
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/credentials/profiles", methods=["GET", "POST"])
def credential_profiles():
    """List or save credential profiles. Secrets are write-only."""
    from modules import credentials

    if request.method == "GET":
        return jsonify({"ok": True, "profiles": credentials.list_profiles()})

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Profile name is required"}), 400
    try:
        credentials.save_profile(
            name,
            username=(data.get("username") or "").strip(),
            password=data.get("password") or "",
            secret=data.get("secret") or "",
            rotation_policy=(data.get("rotation_policy") or "").strip(),
        )
        return jsonify({"ok": True, "profiles": credentials.list_profiles()})
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/credentials/profiles/<path:name>", methods=["DELETE"])
def delete_credential_profile(name):
    from modules import credentials
    return jsonify(credentials.delete_profile(name))


@bp.route("/credentials/copy-inherited/<path:list_name>", methods=["POST"])
def copy_inherited(list_name):
    """Freeze inherited credentials into per-device overrides.

    Decouples a NetBox list from its designated credential list so deleting
    that list cannot strand it.
    """
    from modules.credentials import copy_inherited_to_overrides
    try:
        from modules.inventory import invalidate
        result = copy_inherited_to_overrides(list_name)
        invalidate(list_name)
        return jsonify(result)
    except Exception as exc:                  # noqa: BLE001
        log.exception("inventory: copy-inherited failed for '%s'", list_name)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/dependents/<path:list_name>", methods=["GET"])
def dependents(list_name):
    """NetBox lists that inherit credentials from *list_name*.

    The delete-list confirmation calls this so it can warn before removing a
    list that other lists depend on for credentials.
    """
    try:
        from modules.inventory.source_config import lists_depending_on
        names = lists_depending_on(list_name)
        return jsonify({"ok": True, "dependents": names})
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500
