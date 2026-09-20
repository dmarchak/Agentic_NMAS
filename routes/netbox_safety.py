"""NetBox import/removal safety blueprint.

Adds the dry-run preview and in-context consent that let the Import and Remove
buttons keep working while ``netbox_allow_writes`` defaults to off.

Flow for both buttons:

1. Click → ``/preview`` runs a **read-only** dry run. Because it issues no
   writes it is allowed regardless of the gate, and because it runs the real
   sync code path against the real NetBox the preview is accurate.
2. The modal shows what would be created, updated, or deleted.
3. Confirm → ``/apply`` flips the gate if the operator ticked the box in the
   modal, then performs the write.

So the operator never meets a disabled button with no explanation, and no write
reaches NetBox without someone seeing the object list first.
"""

import logging
import os

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("netbox_safety", __name__, url_prefix="/netbox/safety")


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
    from modules.netbox_guard import writes_allowed
    return jsonify({
        "ok": True,
        "list": list_name,
        "device_count": len(devices),
        "writes_allowed": writes_allowed(),
        "plan": plan,
        "summary": _describe_plan(plan),
    })


@bp.route("/import/apply", methods=["POST"])
def apply_import():
    """Perform the import, optionally enabling writes as the confirming action."""
    from modules.netbox_client import get_netbox_config, set_sync_running, sync_list_to_netbox
    from modules.config import set_user_setting

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"ok": False, "error": "NetBox is not configured"}), 400

    data = request.get_json(silent=True) or {}
    if data.get("enable_writes"):
        # Ticking the box in the confirm modal is the consent; persist it so
        # later imports do not re-prompt.
        set_user_setting("netbox_allow_writes", True)
        log.info("netbox_safety: writes enabled by operator from the import modal")

    list_name, devices = _load_list_devices((data.get("list_name") or "").strip())
    if list_name is None:
        return jsonify({"ok": False, "error": "Device list not found"}), 404
    if not devices:
        return jsonify({"ok": False, "error": f"List '{list_name}' has no devices"}), 400

    import threading

    def _run(name=list_name, devs=devices):
        try:
            set_sync_running(name, True)
            sync_list_to_netbox(name, devs)
        except Exception as exc:              # noqa: BLE001
            log.error("netbox_safety: import thread failed: %s", exc, exc_info=True)
        finally:
            set_sync_running(name, False)

    from modules.netbox_guard import writes_allowed
    if not writes_allowed():
        return jsonify({"ok": False, "blocked": True,
                        "error": "NetBox writes are still disabled — confirm the import "
                                 "with 'Enable writes' ticked, or turn them on in "
                                 "Settings → Integrations."}), 403

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
        "list": f"{len(payload)} list(s)",
        "device_count": sum(len(d) for _, d in payload),
        "writes_allowed": writes_allowed(),
        "plan": plan,
        "summary": _describe_plan(plan),
    })


@bp.route("/import_all/apply", methods=["POST"])
def apply_import_all():
    """Import every device list, optionally enabling writes as the consent."""
    import threading

    from modules.netbox_client import (
        get_netbox_config, set_sync_running, sync_all_lists_to_netbox,
    )
    from modules.netbox_guard import writes_allowed
    from modules.config import set_user_setting

    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return jsonify({"ok": False, "error": "NetBox is not configured"}), 400

    data = request.get_json(silent=True) or {}
    if data.get("enable_writes"):
        set_user_setting("netbox_allow_writes", True)
        log.info("netbox_safety: writes enabled by operator from the import-all modal")

    if not writes_allowed():
        return jsonify({"ok": False, "blocked": True,
                        "error": "NetBox writes are still disabled — confirm with "
                                 "'Enable writes' ticked."}), 403

    payload = _all_lists_with_devices()
    if not payload:
        return jsonify({"ok": False, "error": "No device lists have any devices"}), 400

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

    from modules.netbox_guard import writes_allowed
    result["writes_allowed"] = writes_allowed()
    return jsonify(result)


@bp.route("/remove/apply", methods=["POST"])
def apply_removal():
    """Remove NMAS-created objects, or just drop NMAS's record of them."""
    from modules.netbox_client import remove_list_from_netbox
    from modules.config import set_user_setting

    data = request.get_json(silent=True) or {}
    list_name = (data.get("list_name") or "").strip()
    if not list_name:
        return jsonify({"ok": False, "error": "list_name is required"}), 400

    # "Forget" needs no write gate — it deletes nothing from NetBox.
    if data.get("forget_only"):
        return jsonify(remove_list_from_netbox(list_name, forget_only=True))

    if data.get("enable_writes"):
        set_user_setting("netbox_allow_writes", True)
        log.info("netbox_safety: writes enabled by operator from the removal modal")

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
