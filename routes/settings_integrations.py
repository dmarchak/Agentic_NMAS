"""Integration health, as stored: `GET /settings/integrations/status`.

The blueprint backed today's Settings → Integrations. Its form routes (the settings read and
each integration's save, its Test and the general block: `GET /settings/integrations`,
`POST /settings/integrations/<name>`, `POST /settings/integrations/<name>/test`,
`/settings/integrations/general`) left with today's Settings modal at 7.8 (2026-10-15): each
network's integration cards are Settings › Default and each network's own (`routes/settings_v2.py`,
boards A to J), NetBox's and Proxmox's Settings › Installation › Connections (board F3).

`/status` stays: docs/DEPLOY_LINUX.md's Verify reads it on a new install (a question for the
operator, 7.8: whether that check moves elsewhere and this route goes).
"""

import logging

from flask import Blueprint, jsonify

log = logging.getLogger(__name__)

bp = Blueprint("settings_integrations", __name__, url_prefix="/settings/integrations")


@bp.route("/status", methods=["GET"])
def integration_status():
    """Each integration's state from the integration-health READER's stored value, never
    probed per request (modules/readers/integration_health.py, 7.2). v2's strip and Needs
    attention read the same stored value."""
    from modules import reader_job
    from modules.readers import integration_health

    got = reader_job.read_cached(integration_health.READER.name)
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return jsonify({"ok": False, "error": f"not probed yet: {why}"}), 503
    return jsonify({"ok": True, "statuses": (good.get("value") or {}).get("integrations") or [],
                    "value_at": good.get("value_at"),
                    "stale_after_seconds": doc.get("stale_after_seconds")})
