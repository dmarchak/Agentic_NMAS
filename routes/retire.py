"""Retire a device from management, from the Device page (7.3).

`modules/nsot/retire.py` is the one implementation; `scripts/nmas-retire` and
these routes are two entry points into it. What differs is the break-glass
BASIS, and each says which it is: the CLI opens the record, and this page,
which cannot reach a file on the operator's laptop, trusts the export log on
this host (the operator, 2026-09-28: "the screen trusts the export log, the
CLI trusts the record").
"""

import logging

from flask import Blueprint, jsonify, request

from modules.identity import request_actor

log = logging.getLogger(__name__)

bp = Blueprint("retire", __name__, url_prefix="/retire")


def _plan_args(data: dict, *, carried: bool):
    """(list, device, reason). The list is CARRIED on apply (a write may not
    derive its list: this ends in a commit and a deleted row), and a read
    may derive it."""
    from modules.config import get_current_list_name

    list_name = (data.get("list_name") or "").strip()
    if not list_name and not carried:
        list_name = get_current_list_name()
    return list_name, (data.get("device") or "").strip(), (data.get("reason") or "").strip()


@bp.route("/preview", methods=["POST"])
def preview():
    """What retiring one device would do, what it will not, and each gate.
    Reads only: the repository, the CSV, the credential store, the settings
    and the export log."""
    from modules.nsot import retire
    from modules.nsot.device_ops import busy_text
    from modules.outbound import mask_payload
    from modules.preview_confirm import retire_preview

    list_name, device, reason = _plan_args(request.get_json(silent=True) or {}, carried=False)
    if not device:
        return jsonify({"ok": False, "error": "No device named: nothing to preview"}), 400
    p = retire.plan(list_name, device, reason)
    return jsonify(mask_payload({
        "ok": True, "list": list_name,
        "preview": retire_preview(p, busy=busy_text(list_name, device), request=request)}))


@bp.route("/apply", methods=["POST"])
def apply():
    """Retire the confirmed device against the export log, as the verified
    person. The plan is computed again and a different hash refuses."""
    from modules.nsot import retire
    from modules.outbound import mask_payload
    from modules.preview_confirm import retire_result

    data = request.get_json(silent=True) or {}
    list_name, device, reason = _plan_args(data, carried=True)
    if not list_name:
        return jsonify({"ok": False, "error": (
            "No list named: retiring commits into one list's repository and deletes a row "
            "from its inventory, so the list comes from the preview that was confirmed, "
            "never from whichever list is active. Nothing was done.")}), 400
    if not device or not (data.get("hash") or "").strip():
        return jsonify({"ok": False, "error": "Nothing confirmed: nothing was done"}), 400
    out = retire.apply(list_name, device, reason=reason, actor=request_actor(),
                       confirmed_hash=data["hash"].strip(), breakglass_log=True)
    # The plan it refused on, when it refused; never a second plan after a
    # success, which would only say "nothing to retire".
    plan = out.get("plan") or {"hostname": device, "list_name": list_name}
    log.info("retire: %s/%s by %s: ok=%s done=%s", list_name, device, request_actor(),
             out.get("ok"), out.get("done"))
    return jsonify(mask_payload({"ok": True, "list": list_name,
                                 "result": retire_result(out, plan)}))
