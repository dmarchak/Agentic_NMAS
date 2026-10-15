"""Inventory source blueprint.

Per-list source configuration, on-demand refresh, credential profiles, and the
stale-device view.
"""

import logging

from flask import Blueprint, jsonify

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


# Setting a list's source (POST /source/<list>) left at 7.8 on 2026-10-15: no page called it.
# Its home is each network's Settings › Network tab, Inventory source (`routes/settings_v2.py`
# over `modules/network_source.py`: previewed, confirmed and recorded).


@bp.route("/refresh/<path:list_name>", methods=["POST"])
def refresh(list_name):
    """Refresh now, blocking, so the UI can report the result."""
    try:
        from modules.inventory import refresh_list
        return jsonify(refresh_list(list_name))
    except Exception as exc:                  # noqa: BLE001
        log.exception("inventory: refresh failed for '%s'", list_name)
        return jsonify({"ok": False, "error": str(exc)}), 500
