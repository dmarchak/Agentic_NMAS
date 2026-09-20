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
import os

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("netbox_safety", __name__, url_prefix="/netbox/safety")

#: Pseudo-list name for the all-lists import, so a token issued for it cannot
#: be replayed against a single named list.
_ALL_LISTS = "__all_lists__"


def _authorization_for(operation: str, list_name: str, plan: dict) -> dict:
    """Fields every preview returns: the master-switch state and a one-shot token.

    The token is bound to a hash of *this* plan. Confirming authorizes only this
    operation; it does not open NetBox for writes generally.
    """
    from modules.netbox_authz import compute_plan_hash, issue_token
    from modules.netbox_guard import writes_allowed

    plan_hash = compute_plan_hash(plan)
    issued = issue_token(operation, list_name, plan_hash)
    return {
        "writes_allowed": writes_allowed(),
        "token":          issued["token"],
        "expires_in":     issued["expires_in"],
        "plan_hash":      plan_hash,
    }


def _load_list_devices(list_name: str):
    """Resolve a device list name to ``(name, devices)``.

    Mirrors the lookup in ``app.netbox_sync`` so both paths agree on which CSV
    a list name maps to.
    """
    from modules.config import LISTS_DIR
    from modules.device import (
        get_device_lists, get_current_device_list, load_saved_devices,
    )

    if list_name:
        match = next((l for l in get_device_lists() if l["name"] == list_name), None)
        if not match:
            return None, None
        csv_path = os.path.join(LISTS_DIR, match["filename"], "devices.csv")
        return list_name, load_saved_devices(csv_path)

    name, csv_path = get_current_device_list()
    return name, load_saved_devices(csv_path)



def _maybe_permit_writes(data: dict) -> None:
    """Honour an explicit request to turn on the master write switch.

    This is a deliberate, separately-labelled operator decision — "writes are
    permitted at all" — not the confirmation of the operation. The operation
    itself is still authorized one-shot by a token.
    """
    from modules.config import set_user_setting
    if data.get("permit_writes"):
        set_user_setting("netbox_allow_writes", True)
        log.info("netbox_safety: operator turned on the NetBox master write switch")


def _authorize(data: dict, operation: str, list_name: str, recompute) -> tuple:
    """Check the master switch, consume the token, and re-verify the plan.

    Returns ``(True, None, 0)`` when the write may proceed, otherwise
    ``(False, error_payload, http_status)``.
    """
    from modules.netbox_authz import consume_token, verify_plan_unchanged
    from modules.netbox_guard import writes_allowed

    # 1. Master switch — a persistent operator decision, checked first so an
    #    unauthorized instance cannot burn a token.
    if not writes_allowed():
        return False, {
            "ok": False, "blocked": True,
            "error": "NetBox writes are not permitted for this instance. Turn on "
                     "'Allow writes to NetBox' in Settings → Integrations.",
        }, 403

    # 2. One-shot token from the preview.
    token = (data.get("token") or "").strip()
    if not token:
        return False, {"ok": False, "stale": True,
                       "error": "Missing confirmation. Run the preview again."}, 400

    ok, err, approved_hash = consume_token(token, operation, list_name)
    if not ok:
        return False, {"ok": False, "stale": True, "error": err}, 409

    # 3. Recompute the plan and compare — NetBox may have changed since preview.
    try:
        current_plan = recompute()
    except Exception as exc:                  # noqa: BLE001
        log.exception("netbox_safety: could not recompute the plan for '%s'", list_name)
        return False, {"ok": False, "error": f"Could not re-verify the plan: {exc}"}, 500

    unchanged, err = verify_plan_unchanged(approved_hash, current_plan)
    if not unchanged:
        log.warning("netbox_safety: plan hash mismatch for %s on '%s' — aborted",
                    operation, list_name)
        return False, {"ok": False, "stale": True, "error": err}, 409

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

    try:
        result = sync_list_to_netbox(list_name, devices, dry_run=True)
    except Exception as exc:                  # noqa: BLE001
        log.exception("netbox_safety: import preview failed for '%s'", list_name)
        return jsonify({"ok": False, "error": str(exc)}), 500

    plan = result.get("plan", {})
    return jsonify({
        "ok": True,
        "list": list_name,
        "device_count": len(devices),
        "plan": plan,
        "summary": _describe_plan(plan),
        **_authorization_for("import", list_name, plan),
    })


@bp.route("/import/apply", methods=["POST"])
def apply_import():
    """Execute a previously previewed import.

    Requires the single-use token from ``/import/preview`` and re-verifies that
    NetBox still matches the previewed plan.
    """
    import threading

    from modules.netbox_client import get_netbox_config, set_sync_running, sync_list_to_netbox

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"ok": False, "error": "NetBox is not configured"}), 400

    data = request.get_json(silent=True) or {}
    list_name, devices = _load_list_devices((data.get("list_name") or "").strip())
    if list_name is None:
        return jsonify({"ok": False, "error": "Device list not found"}), 404
    if not devices:
        return jsonify({"ok": False, "error": f"List '{list_name}' has no devices"}), 400

    _maybe_permit_writes(data)

    authorized, err, status = _authorize(
        data, "import", list_name,
        recompute=lambda: sync_list_to_netbox(list_name, devices, dry_run=True).get("plan", {}),
    )
    if not authorized:
        return jsonify(err), status

    def _run(name=list_name, devs=devices):
        try:
            set_sync_running(name, True)
            sync_list_to_netbox(name, devs)
        except Exception as exc:              # noqa: BLE001
            log.error("netbox_safety: import thread failed: %s", exc, exc_info=True)
        finally:
            set_sync_running(name, False)

    threading.Thread(target=_run, daemon=True, name=f"netbox-import-{list_name}").start()
    set_sync_running(list_name, True)
    return jsonify({"ok": True, "status": "started", "list": list_name,
                    "device_count": len(devices)})


def _all_lists_with_devices():
    """Every device list paired with its devices, for the all-lists import."""
    import os as _os
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists, load_saved_devices

    out = []
    for entry in get_device_lists():
        csv_path = _os.path.join(LISTS_DIR, entry["filename"], "devices.csv")
        devices = load_saved_devices(csv_path)
        if devices:
            out.append((entry["name"], devices))
    return out


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

    try:
        result = sync_all_lists_to_netbox(payload, dry_run=True)
    except Exception as exc:                  # noqa: BLE001
        log.exception("netbox_safety: import-all preview failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

    plan = result.get("plan", {})
    return jsonify({
        "ok": True,
        "list": _ALL_LISTS,
        "device_count": sum(len(d) for _, d in payload),
        "plan": plan,
        "summary": _describe_plan(plan),
        **_authorization_for("import_all", _ALL_LISTS, plan),
    })


@bp.route("/import_all/apply", methods=["POST"])
def apply_import_all():
    """Import every device list, optionally enabling writes as the consent."""
    import threading

    from modules.netbox_client import (
        get_netbox_config, set_sync_running, sync_all_lists_to_netbox,
    )
    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"ok": False, "error": "NetBox is not configured"}), 400

    data = request.get_json(silent=True) or {}
    payload = _all_lists_with_devices()
    if not payload:
        return jsonify({"ok": False, "error": "No device lists have any devices"}), 400

    _maybe_permit_writes(data)

    authorized, err, status = _authorize(
        data, "import_all", _ALL_LISTS,
        recompute=lambda: sync_all_lists_to_netbox(payload, dry_run=True).get("plan", {}),
    )
    if not authorized:
        return jsonify(err), status

    def _run(items=payload):
        names = [n for n, _ in items]
        try:
            for n in names:
                set_sync_running(n, True)
            sync_all_lists_to_netbox(items)
        except Exception as exc:              # noqa: BLE001
            log.error("netbox_safety: import-all thread failed: %s", exc, exc_info=True)
        finally:
            for n in names:
                set_sync_running(n, False)

    threading.Thread(target=_run, daemon=True, name="netbox-import-all").start()
    return jsonify({"ok": True, "status": "started",
                    "list": f"{len(payload)} list(s)",
                    "device_count": sum(len(d) for _, d in payload)})


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
        result = remove_list_from_netbox(list_name, dry_run=True)
    except Exception as exc:                  # noqa: BLE001
        log.exception("netbox_safety: removal preview failed for '%s'", list_name)
        return jsonify({"ok": False, "error": str(exc)}), 500

    plan = {"deletes": [{"endpoint": o["endpoint"], "name": o.get("name", ""),
                         "id": o.get("id")} for o in result.get("deleted", [])]}
    result.update(_authorization_for("remove", list_name, plan))
    return jsonify(result)


@bp.route("/remove/apply", methods=["POST"])
def apply_removal():
    """Remove NMAS-created objects, or just drop NMAS's record of them."""
    from modules.netbox_client import remove_list_from_netbox

    data = request.get_json(silent=True) or {}
    list_name = (data.get("list_name") or "").strip()
    if not list_name:
        return jsonify({"ok": False, "error": "list_name is required"}), 400

    # "Forget" needs neither the switch nor a token — it deletes nothing.
    if data.get("forget_only"):
        return jsonify(remove_list_from_netbox(list_name, forget_only=True))

    _maybe_permit_writes(data)

    def _recompute():
        preview = remove_list_from_netbox(list_name, dry_run=True)
        return {"deletes": [{"endpoint": o["endpoint"], "name": o.get("name", ""),
                             "id": o.get("id")} for o in preview.get("deleted", [])]}

    authorized, err, status = _authorize(data, "remove", list_name, recompute=_recompute)
    if not authorized:
        return jsonify(err), status

    try:
        return jsonify(remove_list_from_netbox(list_name))
    except Exception as exc:                  # noqa: BLE001
        log.exception("netbox_safety: removal failed for '%s'", list_name)
        return jsonify({"ok": False, "error": str(exc)}), 500


def _describe_plan(plan: dict) -> str:
    """One-line human summary for the confirm modal."""
    if not plan:
        return "Nothing to do."
    parts = []
    if plan.get("create_count"):
        parts.append(f"create {plan['create_count']} object(s)")
    if plan.get("update_count"):
        parts.append(f"update {plan['update_count']} object(s)")
    if plan.get("delete_count"):
        parts.append(f"delete {plan['delete_count']} object(s)")
    return "Will " + ", ".join(parts) + "." if parts else "No changes — NetBox already matches."
