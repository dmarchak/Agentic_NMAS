"""Planned restarts through the product's API (the operator, 2026-10-02).

"The redeploy script must declare its own planned-restart window, through the product's
API, after the typed confirmation and before it touches the lab — covering exactly the
devices it redeploys." This is that API: the window is recorded by `restarts.record_planned`
(the one writer, which the tool's own Reload and `scripts/nmas-planned-restart` use too),
and the record names the VERIFIED caller, never a name in the body. A window covering a
restart already seen is refused unless the body marks it a correction with its reason.

The gate is `configure` with operation `planned_restart`: a person by default; a script
calling with a Cloudflare Access service token passes only where the host's
`service_allowed_operations` names `planned_restart`.
"""

import logging
import time

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("restarts", __name__, url_prefix="/restarts")

#: The longest window one call may declare: a day, as the command allows.
MAX_MINUTES = 24 * 60


@bp.route("/planned", methods=["POST"])
def planned():
    """Body: ``{"list", "devices": [...] or ["*"], "minutes", "why", "from"?,
    "correction"?}``. ``from`` is a UTC time; absent, the window starts now."""
    from modules import identity
    from modules import restarts as R
    from modules.device import get_device_lists

    data = request.get_json(silent=True) or {}
    list_name = str(data.get("list") or "")
    devices = data.get("devices")
    if not isinstance(devices, list) or not all(isinstance(d, str) and d for d in devices) \
            or not devices:
        return jsonify({"ok": False, "error": "devices is a list of hostnames, or [\"*\"]"}), 400
    if list_name not in {(x.get("name") or "") for x in get_device_lists()}:
        return jsonify({"ok": False, "error": f"no device list is named {list_name!r}"}), 400
    try:
        minutes = int(data.get("minutes"))
    except (TypeError, ValueError):
        minutes = 0
    if not 1 <= minutes <= MAX_MINUTES:
        return jsonify({"ok": False, "error": f"minutes is between 1 and {MAX_MINUTES}"}), 400
    start = time.time()
    if data.get("from"):
        start = R._epoch(str(data["from"]))
        if not start:
            return jsonify({"ok": False, "error": f"from {data['from']!r} is not a UTC time "
                                                  "like 2026-10-01T15:20Z"}), 400
    actor = identity.request_actor()
    got = R.record_planned(devices, start, start + minutes * 60, actor, str(data.get("why") or ""),
                           "api", list_name=list_name,
                           correction=str(data.get("correction") or ""))
    if not got["ok"]:
        return jsonify({"ok": False, "error": got["error"]}), 409
    log.info("planned restart recorded through the API by %s: %s", actor, got["record"])
    return jsonify({"ok": True, "record": got["record"], "covered": len(got["covered"])})
