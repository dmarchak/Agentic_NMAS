"""Persist a device's running config from the Device page (7.3, C164).

`modules/nsot/persist_op.py` is the operation; `scripts/nmas-persist-native`
runs the same save and read-back on the host. The remedy the worst Needs
attention rows name (`not_safe_to_reboot`), given a screen.
"""

import logging

from flask import Blueprint, jsonify, request

from modules.identity import request_actor

log = logging.getLogger(__name__)

bp = Blueprint("persist", __name__, url_prefix="/persist")


def _args(data: dict, *, carried: bool):
    """(list, device). The list is CARRIED on apply (a write may not derive
    its list: this saves a device of that list), and a read may derive it."""
    from modules.config import get_current_list_name

    list_name = (data.get("list_name") or "").strip()
    if not list_name and not carried:
        list_name = get_current_list_name()
    return list_name, (data.get("device") or "").strip()


@bp.route("/preview", methods=["POST"])
def preview():
    """What persisting one device would do, what it will not, and each gate.
    Reads only the registry, the inventory and the startup check's record:
    the device is not contacted."""
    from modules.nsot import persist_op
    from modules.nsot.device_ops import busy_text
    from modules.outbound import mask_payload
    from modules.preview_confirm import persist_preview

    list_name, device = _args(request.get_json(silent=True) or {}, carried=False)
    if not device:
        return jsonify({"ok": False, "error": "No device named: nothing to preview"}), 400
    p = persist_op.plan(list_name, device)
    return jsonify(mask_payload({
        "ok": True, "list": list_name,
        "preview": persist_preview(p, busy=busy_text(list_name, device), request=request)}))


@bp.route("/apply", methods=["POST"])
def apply():
    """Save and read back the confirmed device, as the verified person. The
    plan is computed again and a different hash refuses with nothing sent."""
    from modules.nsot import persist_op
    from modules.outbound import mask_payload
    from modules.preview_confirm import persist_result

    data = request.get_json(silent=True) or {}
    list_name, device = _args(data, carried=True)
    if not list_name:
        return jsonify({"ok": False, "error": (
            "No list named: persisting saves a device of one list, so the list comes from "
            "the preview that was confirmed, never from whichever list is active. Nothing "
            "was sent.")}), 400
    if not device or not (data.get("hash") or "").strip():
        return jsonify({"ok": False, "error": "Nothing confirmed: nothing was sent"}), 400
    actor = request_actor()
    out = persist_op.apply(list_name, device, actor=actor, confirmed_hash=data["hash"].strip())
    return jsonify(mask_payload({"ok": True, "list": list_name,
                                 "result": persist_result(out, out.get("plan") or {}, actor)}))
