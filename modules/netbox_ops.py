"""NetBox import and removal: the ONE code path today's routes (routes/netbox_safety.py) and v2's
NetBox page (routes/netbox_v2.py) both call (cutover blocker 2, 2026-10-10: moved out of the
routes, behaviour unchanged, so two entry points share one path).

Each is a dry run of the real sync against the real NetBox (`dry_run`), which writes nothing and
returns a one-shot token bound to a hash of that exact plan, then a confirm (`authorize`) that
checks the master switch (a person may turn it on WITH this confirm, `permit_writes`, and it comes
on only after the token and the recomputed plan both pass, C330), consumes the token, recomputes
the plan and refuses if it moved. An import then runs on a thread (`start_import`), reporting
under its progress id; a removal runs in the request (`remove`). Every write carries the
verified person and the authority it stood on.
"""

import logging
import os
import threading

log = logging.getLogger(__name__)

#: Pseudo-list name for the all-lists import, so a token issued for it cannot be replayed
#: against a single named list.
ALL_LISTS = "__all_lists__"
OPERATIONS = ("import", "import_all", "remove")


class Refused(Exception):
    """Not done: ``payload`` is the answer to send (``ok`` False, ``error``), ``status`` its
    HTTP status."""

    def __init__(self, payload: dict, status: int):
        super().__init__(payload.get("error", ""))
        self.payload, self.status = payload, status


def configured() -> bool:
    from modules.netbox_client import get_netbox_config

    cfg = get_netbox_config()
    return bool(cfg["url"] and cfg["token"])


def list_devices(list_name: str):
    """``(name, devices)`` for a list name, or the active list's for none; ``(None, None)``
    for a name no list has. Mirrors `app.netbox_sync`'s lookup."""
    from modules.config import LISTS_DIR
    from modules.device import get_current_device_list, get_device_lists, load_saved_devices

    if list_name:
        match = next((l for l in get_device_lists() if l["name"] == list_name), None)
        if not match:
            return None, None
        return list_name, load_saved_devices(os.path.join(LISTS_DIR, match["filename"],
                                                          "devices.csv"))
    name, csv_path = get_current_device_list()
    return name, load_saved_devices(csv_path)


def all_lists_with_devices() -> list:
    """Every device list paired with its devices, for the all-lists import."""
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists, load_saved_devices

    out = []
    for entry in get_device_lists():
        devices = load_saved_devices(os.path.join(LISTS_DIR, entry["filename"], "devices.csv"))
        if devices:
            out.append((entry["name"], devices))
    return out


def authorization_for(operation: str, list_name: str, plan: dict) -> dict:
    """The master switch's state and a one-shot token bound to a hash of *plan*."""
    from modules.netbox_authz import compute_plan_hash, issue_token
    from modules.netbox_guard import writes_allowed

    plan_hash = compute_plan_hash(plan)
    issued = issue_token(operation, list_name, plan_hash)
    return {"writes_allowed": writes_allowed(), "token": issued["token"],
            "expires_in": issued["expires_in"], "plan_hash": plan_hash}


def authorize(data: dict, operation: str, list_name: str, recompute, actor: str) -> None:
    """Check the master switch, consume the token, re-verify the plan, and only then turn the
    switch on if the person permitted it. Raises `Refused`."""
    from modules.netbox_authz import consume_token, verify_plan_unchanged
    from modules.netbox_guard import writes_allowed

    permit = bool(data.get("permit_writes")) and not writes_allowed()
    if not writes_allowed() and not permit:
        raise Refused({
            "ok": False, "blocked": True,
            "error": "NetBox writes are off for every network (Writes allowed, on "
                     "Settings › Installation › Connections, NetBox connection). Confirm this "
                     "write with writes permitted to turn them on: they come on only once its "
                     "token and plan both pass."}, 403)
    token = (data.get("token") or "").strip()
    if not token:
        raise Refused({"ok": False, "stale": True,
                       "error": "Missing confirmation. Run the preview again."}, 400)
    ok, err, approved_hash = consume_token(token, operation, list_name)
    if not ok:
        raise Refused({"ok": False, "stale": True, "error": err}, 409)
    try:
        current_plan = recompute()
    except Exception as exc:                          # noqa: BLE001
        log.exception("netbox_ops: could not recompute the plan for '%s'", list_name)
        raise Refused({"ok": False, "error": f"Could not re-verify the plan: {exc}"}, 500) from None
    unchanged, err = verify_plan_unchanged(approved_hash, current_plan)
    if not unchanged:
        log.warning("netbox_ops: plan hash mismatch for %s on '%s' — aborted", operation,
                    list_name)
        raise Refused({"ok": False, "stale": True, "error": err}, 409)
    if permit:
        from modules.settings_schema import write_settings
        written = write_settings({"netbox_allow_writes": True}, actor=actor)
        if not written.get("ok", True):
            raise Refused({"ok": False, "error": "the master switch could not be turned on: "
                           + str(written.get("error") or written)}, 500)
        log.info("netbox_ops: %s turned on the NetBox master write switch with a confirmed %s",
                 actor, operation)


def _removal_plan(result: dict) -> dict:
    return {"deletes": [{"endpoint": o["endpoint"], "name": o.get("name", ""),
                         "id": o.get("id")} for o in result.get("deleted", [])]}


def dry_run(operation: str, list_name: str, actor: str, progress_id: str = "") -> dict:
    """The preview's facts: ``{"ok", "list", "device_count"?, "plan", ...authorization}``, the
    raw dry run kept here (the caller masks what it draws). Raises `Refused`."""
    from modules import op_progress
    from modules.netbox_client import (remove_list_from_netbox, sync_all_lists_to_netbox,
                                       sync_list_to_netbox)

    if operation not in OPERATIONS:
        raise Refused({"ok": False, "error": f"no operation {operation!r}"}, 404)
    if not configured():
        raise Refused({"ok": False, "error": "NetBox is not configured — set URL and API token "
                       "first."}, 400)
    if operation == "remove":
        if not list_name:
            raise Refused({"ok": False, "error": "list_name is required"}, 400)
        try:
            result = remove_list_from_netbox(list_name, dry_run=True, actor=actor)
        except Exception as exc:                      # noqa: BLE001
            log.exception("netbox_ops: removal preview failed for '%s'", list_name)
            raise Refused({"ok": False, "error": str(exc)}, 500) from None
        result.update(authorization_for("remove", list_name, _removal_plan(result)))
        return result
    if operation == "import_all":
        payload = all_lists_with_devices()
        if not payload:
            raise Refused({"ok": False, "error": "No device lists have any devices"}, 400)
        try:
            result = sync_all_lists_to_netbox(payload, dry_run=True, progress_id=progress_id,
                                              actor=actor)
        except Exception as exc:                      # noqa: BLE001
            log.exception("netbox_ops: import-all preview failed")
            op_progress.finish(progress_id, "failed")
            raise Refused({"ok": False, "error": str(exc)}, 500) from None
        op_progress.finish(progress_id)
        plan = result.get("plan", {})
        return {"ok": True, "list": ALL_LISTS, "device_count": sum(len(d) for _, d in payload),
                "plan": plan, **authorization_for("import_all", ALL_LISTS, plan)}
    name, devices = list_devices(list_name)
    if name is None:
        raise Refused({"ok": False, "error": "Device list not found"}, 404)
    if not devices:
        raise Refused({"ok": False, "error": f"List '{name}' has no devices"}, 400)
    try:
        result = sync_list_to_netbox(name, devices, dry_run=True, progress_id=progress_id,
                                     actor=actor)
    except Exception as exc:                          # noqa: BLE001
        log.exception("netbox_ops: import preview failed for '%s'", name)
        op_progress.finish(progress_id, "failed")
        raise Refused({"ok": False, "error": str(exc)}, 500) from None
    op_progress.finish(progress_id)
    plan = result.get("plan", {})
    return {"ok": True, "list": name, "device_count": len(devices), "plan": plan,
            **authorization_for("import", name, plan)}


def start_import(operation: str, list_name: str, data: dict, actor: str,
                 progress_id: str = "", where: str = "the NetBox tab", on_end=None) -> dict:
    """Confirm and start an import (one list, or every list) on a thread: ``{"ok", "status":
    "started", "list", "device_count"}``. Raises `Refused`. *on_end(outcome)* runs when it ends."""
    from modules import netbox_guard as nbg
    from modules import op_progress
    from modules.netbox_client import (set_sync_running, sync_all_lists_to_netbox,
                                       sync_list_to_netbox)

    if not configured():
        raise Refused({"ok": False, "error": "NetBox is not configured"}, 400)
    if operation == "import_all":
        payload = all_lists_with_devices()
        if not payload:
            raise Refused({"ok": False, "error": "No device lists have any devices"}, 400)
        try:
            authorize(data, "import_all", ALL_LISTS, actor=actor,
                      recompute=lambda: sync_all_lists_to_netbox(
                          payload, dry_run=True, progress_id=progress_id,
                          actor=actor).get("plan", {}))
        except Refused:
            op_progress.finish(progress_id, "refused")
            raise
        names = [n for n, _ in payload]

        def _run_all():
            outcome = "done"
            try:
                for n in names:
                    set_sync_running(n, True)
                op_progress.update(progress_id, phase="importing", devices_done=0)
                sync_all_lists_to_netbox(payload, progress_id=progress_id, actor=actor,
                                         authority=f"{where}'s one-time confirmation of this "
                                                   f"import-all, by {actor}")
            except Exception as exc:                  # noqa: BLE001
                outcome = "failed"
                log.error("netbox_ops: import-all thread failed: %s", exc, exc_info=True)
            finally:
                for n in names:
                    set_sync_running(n, False)
                op_progress.finish(progress_id, outcome)
                if on_end:
                    on_end(outcome)
        threading.Thread(target=_run_all, daemon=True, name="netbox-import-all").start()
        return {"ok": True, "status": "started", "list": f"{len(payload)} list(s)",
                "device_count": sum(len(d) for _, d in payload)}

    name, devices = list_devices(list_name)
    if name is None:
        raise Refused({"ok": False, "error": "Device list not found"}, 404)
    if not devices:
        raise Refused({"ok": False, "error": f"List '{name}' has no devices"}, 400)
    try:
        authorize(data, "import", name, actor=actor,
                  recompute=lambda: sync_list_to_netbox(name, devices, dry_run=True,
                                                        progress_id=progress_id,
                                                        actor=actor).get("plan", {}))
    except Refused:
        op_progress.finish(progress_id, "refused")
        raise
    busy = nbg.list_writer_now(name)
    if busy is not None:
        op_progress.finish(progress_id, "refused")
        raise Refused({"ok": False, "busy": True, "error": (
            f"Not imported: {nbg.NetBoxBusy(name, busy)}. Nothing was written; import again "
            "once it finishes.")}, 409)

    def _run():
        outcome = "done"
        try:
            set_sync_running(name, True)
            op_progress.update(progress_id, phase="importing", devices_done=0)
            sync_list_to_netbox(name, devices, progress_id=progress_id, actor=actor,
                                authority=f"{where}'s one-time confirmation of this import, "
                                          f"by {actor}")
        except Exception as exc:                      # noqa: BLE001
            outcome = "failed"
            log.error("netbox_ops: import thread failed: %s", exc, exc_info=True)
        finally:
            set_sync_running(name, False)
            op_progress.finish(progress_id, outcome)
            if on_end:
                on_end(outcome)
    threading.Thread(target=_run, daemon=True, name=f"netbox-import-{name}").start()
    set_sync_running(name, True)
    return {"ok": True, "status": "started", "list": name, "device_count": len(devices)}


def remove(list_name: str, data: dict, actor: str, where: str = "the NetBox tab") -> dict:
    """Confirm and run a removal of what Mercury created and recorded for *list_name*, in the
    request. Returns the sync's result; raises `Refused`. `data["forget_only"]` drops Mercury's
    record of them instead, which deletes nothing and needs neither the switch nor a token."""
    from modules.netbox_client import remove_list_from_netbox

    if not list_name:
        raise Refused({"ok": False, "error": "list_name is required"}, 400)
    if data.get("forget_only"):
        return remove_list_from_netbox(list_name, forget_only=True, actor=actor)
    authorize(data, "remove", list_name, actor=actor,
              recompute=lambda: _removal_plan(remove_list_from_netbox(list_name, dry_run=True,
                                                                      actor=actor)))
    try:
        return remove_list_from_netbox(
            list_name, actor=actor,
            authority=f"{where}'s one-time confirmation of this Remove, by {actor}")
    except Exception as exc:                          # noqa: BLE001
        log.exception("netbox_ops: removal failed for '%s'", list_name)
        return {"ok": False, "error": str(exc)}
