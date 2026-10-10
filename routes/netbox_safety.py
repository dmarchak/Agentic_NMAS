"""NetBox import/removal safety blueprint.

Adds the dry-run preview and in-context consent that let the Import and Remove
buttons keep working while ``netbox_allow_writes`` defaults to off.

Flow for both buttons:

1. Click → ``/preview`` runs a **read-only** dry run. Because it issues no
   writes it is allowed regardless of the gate, and because it runs the real
   sync code path against the real NetBox the preview is accurate. The preview
   returns a short-lived, single-use token bound to a hash of that exact plan.
2. The modal shows what would be created, updated, or deleted.
3. Confirm → ``/apply`` consumes the token, **recomputes the plan**, and aborts
   if the hash differs — NetBox changed since the preview, so the approval no
   longer describes what would happen.

Authorization is therefore one-shot: confirming authorizes *that* operation and
nothing else. ``netbox_allow_writes`` is a separate, persistent operator
decision meaning "writes are permitted at all"; it is never flipped as a side
effect of confirming, and both it and a valid token are required.
"""

import logging

from flask import Blueprint, jsonify, request


def _actor() -> str:
    """The VERIFIED person behind this request (the gate table requires one),
    carried into every NetBox write so its modification record names who
    (C149: 56 of 58 recorded writes read `unattributed`)."""
    from modules.identity import request_actor
    return request_actor() or ""

log = logging.getLogger(__name__)

bp = Blueprint("netbox_safety", __name__, url_prefix="/netbox/safety")

#: Pseudo-list name for the all-lists import, so a token issued for it cannot
#: be replayed against a single named list.
_ALL_LISTS = "__all_lists__"


def _authorization_for(operation: str, list_name: str, plan: dict) -> dict:
    """Fields every preview returns: the master-switch state and a one-shot token bound to a
    hash of *this* plan (`netbox_ops.authorization_for`, the one code path v2 shares)."""
    from modules import netbox_ops

    return netbox_ops.authorization_for(operation, list_name, plan)


def _load_list_devices(list_name: str):
    """Resolve a device list name to ``(name, devices)`` (`netbox_ops.list_devices`)."""
    from modules import netbox_ops

    return netbox_ops.list_devices(list_name)


def _authorize(data: dict, operation: str, list_name: str, recompute) -> tuple:
    """The master switch, the one-shot token and the recomputed plan (`netbox_ops.authorize`,
    C330's order: the switch comes on only after both pass). ``(True, None, 0)`` or
    ``(False, error_payload, http_status)``."""
    from modules import netbox_ops

    try:
        netbox_ops.authorize(data, operation, list_name, recompute, actor=_actor())
    except netbox_ops.Refused as exc:
        return False, exc.payload, exc.status
    return True, None, 0


@bp.route("/import/preview", methods=["POST"])
def preview_import():
    """Dry-run the import and return a create/update preview. Writes nothing."""
    from modules.netbox_client import get_netbox_config, sync_list_to_netbox

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"ok": False,
                        "error": "NetBox is not configured — set URL and API token first."}), 400

    data = request.get_json(silent=True) or {}
    list_name, devices = _load_list_devices((data.get("list_name") or "").strip())
    if list_name is None:
        return jsonify({"ok": False, "error": "Device list not found"}), 404
    if not devices:
        return jsonify({"ok": False, "error": f"List '{list_name}' has no devices"}), 400

    from modules import op_progress

    pid = _progress_start(data, "previewed for import", list_name)
    try:
        result = sync_list_to_netbox(list_name, devices, dry_run=True, progress_id=pid,
                                     actor=_actor())
    except Exception as exc:                  # noqa: BLE001
        log.exception("netbox_safety: import preview failed for '%s'", list_name)
        op_progress.finish(pid, "failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
    op_progress.finish(pid)

    plan = result.get("plan", {})
    # Masked on the way out, AFTER the authorisation is bound to the truthful
    # plan (C77's sweep, 2026-09-27): each device's payload carries its golden
    # in `local_context_data`, and this returned its secrets verbatim. What the
    # import WRITES to NetBox is register C95, a separate decision.
    from modules.outbound import mask_payload
    out = {"ok": True, "list": list_name, "device_count": len(devices), "plan": plan,
           **_authorization_for("import", list_name, plan)}
    return jsonify(_drawn(out, mask_payload(_preview("import", out))))


@bp.route("/import/apply", methods=["POST"])
def apply_import():
    """Execute a previously previewed import.

    Requires the single-use token from ``/import/preview`` and re-verifies that
    NetBox still matches the previewed plan.
    """
    from modules.netbox_client import get_netbox_config

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"ok": False, "error": "NetBox is not configured"}), 400

    data = request.get_json(silent=True) or {}
    list_name, devices = _load_list_devices((data.get("list_name") or "").strip())
    if list_name is None:
        return jsonify({"ok": False, "error": "Device list not found"}), 404
    if not devices:
        return jsonify({"ok": False, "error": f"List '{list_name}' has no devices"}), 400

    from modules import netbox_ops

    pid = _progress_start(data, "re-checked, then imported", list_name)
    # The actor is captured in the request: the import runs on a thread after the response,
    # where there is no request to ask (C149). The busy check (R21) is the core's too.
    try:
        return jsonify(netbox_ops.start_import("import", list_name, data, _actor(),
                                               progress_id=pid))
    except netbox_ops.Refused as exc:
        return jsonify(exc.payload), exc.status


def _all_lists_with_devices():
    """Every device list paired with its devices (`netbox_ops.all_lists_with_devices`)."""
    from modules import netbox_ops

    return netbox_ops.all_lists_with_devices()


@bp.route("/import_all/preview", methods=["POST"])
def preview_import_all():
    """Dry-run the all-lists import. Writes nothing."""
    from modules.netbox_client import get_netbox_config, sync_all_lists_to_netbox
    from modules.netbox_guard import writes_allowed

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"ok": False, "error": "NetBox is not configured"}), 400

    payload = _all_lists_with_devices()
    if not payload:
        return jsonify({"ok": False, "error": "No device lists have any devices"}), 400

    from modules import op_progress

    data = request.get_json(silent=True) or {}
    pid = _progress_start(data, "previewed for import", "every list")
    try:
        result = sync_all_lists_to_netbox(payload, dry_run=True, progress_id=pid,
                                          actor=_actor())
    except Exception as exc:                  # noqa: BLE001
        log.exception("netbox_safety: import-all preview failed")
        op_progress.finish(pid, "failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
    op_progress.finish(pid)

    plan = result.get("plan", {})
    # Masked after the authorisation is bound to the truthful plan (C77's
    # sweep): the same device payloads as a single list's preview.
    from modules.outbound import mask_payload
    out = {"ok": True, "list": _ALL_LISTS, "device_count": sum(len(d) for _, d in payload),
           "plan": plan, **_authorization_for("import_all", _ALL_LISTS, plan)}
    return jsonify(_drawn(out, mask_payload(_preview("import_all", out))))


@bp.route("/import_all/apply", methods=["POST"])
def apply_import_all():
    """Import every device list, optionally enabling writes as the consent."""
    from modules.netbox_client import get_netbox_config

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"ok": False, "error": "NetBox is not configured"}), 400

    data = request.get_json(silent=True) or {}
    payload = _all_lists_with_devices()
    if not payload:
        return jsonify({"ok": False, "error": "No device lists have any devices"}), 400

    from modules import netbox_ops

    pid = _progress_start(data, "re-checked, then imported", "every list")
    try:
        return jsonify(netbox_ops.start_import("import_all", _ALL_LISTS, data, _actor(),
                                               progress_id=pid))
    except netbox_ops.Refused as exc:
        return jsonify(exc.payload), exc.status


@bp.route("/remove/preview", methods=["POST"])
def preview_removal():
    """Dry-run the removal and list exactly which objects would be deleted."""
    from modules.netbox_client import get_netbox_config, remove_list_from_netbox

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"ok": False, "error": "NetBox is not configured"}), 400

    data = request.get_json(silent=True) or {}
    list_name = (data.get("list_name") or "").strip()
    if not list_name:
        return jsonify({"ok": False, "error": "list_name is required"}), 400

    try:
        result = remove_list_from_netbox(list_name, dry_run=True, actor=_actor())
    except Exception as exc:                  # noqa: BLE001
        log.exception("netbox_safety: removal preview failed for '%s'", list_name)
        return jsonify({"ok": False, "error": str(exc)}), 500

    plan = {"deletes": [{"endpoint": o["endpoint"], "name": o.get("name", ""),
                         "id": o.get("id")} for o in result.get("deleted", [])]}
    result.update(_authorization_for("remove", list_name, plan))
    return jsonify(_drawn(result, _preview("remove", result)))


@bp.route("/remove/apply", methods=["POST"])
def apply_removal():
    """Remove NMAS-created objects, or just drop NMAS's record of them."""
    data = request.get_json(silent=True) or {}
    list_name = (data.get("list_name") or "").strip()
    if not list_name:
        return jsonify({"ok": False, "error": "list_name is required"}), 400

    from modules import netbox_ops

    # "Forget" needs neither the switch nor a token — it deletes nothing.
    try:
        result = netbox_ops.remove(list_name, data, _actor())
    except netbox_ops.Refused as exc:
        return jsonify(exc.payload), exc.status
    if data.get("forget_only"):
        return jsonify(_recorded_removal(list_name, result, forget_only=True))
    out = _recorded_removal(list_name, result)
    return jsonify(out), (200 if result.get("ok") else 500)


def _recorded_removal(list_name: str, result: dict, forget_only: bool = False) -> dict:
    """Record the removal (C121) and attach its result, drawn by the result
    component from the recorded row, by the verified person."""
    from modules import netbox_guard
    from modules.identity import request_actor
    from modules.preview_confirm import netbox_removal_result

    status = netbox_guard.record_removal(list_name, request_actor(), result,
                                         forget_only=forget_only)
    return {**result, "result": netbox_removal_result(status["row"], status)}


@bp.route("/progress/<op_id>", methods=["GET"])
def progress(op_id):
    """What a NetBox preview or import is doing now: ``{"ok", "state",
    "progress"}``. A READ. `unknown` is its own state (never started here, or
    the server restarted since), never "not running"."""
    from modules import op_progress

    got = op_progress.get(op_id) if op_progress.valid_id(op_id) else None
    if got is None:
        return jsonify({"ok": True, "state": "unknown", "progress": None})
    return jsonify({"ok": True, "state": "finished" if got["finished_at"] else "running",
                    "progress": got})


@bp.route("/removals", methods=["GET"])
def removals():
    """Every recorded removal for a list, newest first, each drawn by the
    result component as it was at apply (C121). A removal nothing recorded
    existed only in a toast and in NetBox's changelog."""
    from modules import netbox_guard
    from modules.preview_confirm import netbox_removal_result

    list_name = (request.args.get("list") or "").strip()
    read = netbox_guard.read_removals(list_name)
    if read["state"] == "unreadable":
        return jsonify({"ok": False, "state": "unreadable",
                        "error": f"the removal record could not be read: {read['error']}"}), 500
    return jsonify({"ok": True, "state": read["state"], "list": list_name,
                    "removals": [{**netbox_guard.removal_heading(r),
                                  "result": netbox_removal_result(r)}
                                 for r in read["rows"][:20]]})


def _drawn(d: dict, preview: dict) -> dict:
    # THE TOKEN IS NOT MASKED, AND THAT IS DELIBERATE (2026-09-28). The import
    # previews used to wrap this whole response in `mask_payload`, which masks
    # by KEY, and `token` is a secret key name: every import preview since
    # C77's sweep sent `<redacted:token>` where the one-shot confirmation
    # belongs, so Confirm could never succeed ("expired or already used", 5
    # seconds after a preview, measured on the host). The token is a
    # capability THIS server issued for the browser to hand back, not a stored
    # secret; the preview, which is built from stored config, is what is masked.
    """What a preview response carries: the preview, and what the modal needs
    to confirm it (7.1). The raw dry run stays on the server. It had carried
    every object's payload, a device's `local_context_data` config among them,
    to a browser that drew two counts from it; the payload-to-render check
    named 80-odd keys nothing read. The token is bound to the plan's hash
    before this, so the confirm still covers the whole plan."""
    return {"ok": d.get("ok", True), "list": d.get("list", ""), "preview": preview,
            **({"device_count": d["device_count"]} if "device_count" in d else {}),
            "writes_allowed": d.get("writes_allowed", False),
            "token": d.get("token", ""), "expires_in": d.get("expires_in", 0),
            "plan_hash": d.get("plan_hash", "")}


def _progress_start(data: dict, kind: str, list_name: str) -> str:
    """Start reporting under the page's `progress_id` (modules.op_progress):
    the modal polls it and the in-flight panel lists it, so a ~54 s preview
    says what it is doing instead of a bare spinner (the operator, 2026-09-28).
    Returns the id, or "" when the page sent none (then nothing is recorded)."""
    from modules import identity, op_progress

    pid = str((data or {}).get("progress_id") or "")
    who = identity.identify(request)
    op_progress.start(pid, kind, f"NetBox ({list_name})",
                      actor=who.actor if who.is_identified else "an unidentified viewer")
    return pid if op_progress.valid_id(pid) else ""


def _preview(operation: str, d: dict) -> dict:
    """The preview, drawn by the component (7.1), as the verified person who
    would confirm (the apply routes are gated `approve`)."""
    from modules.preview_confirm import (confirm_part, netbox_import_preview,
                                         netbox_removal_preview)
    confirm = confirm_part(request, "approve")
    if operation == "remove":
        return netbox_removal_preview(d, confirm)
    return netbox_import_preview(d, confirm, all_lists=operation == "import_all")
