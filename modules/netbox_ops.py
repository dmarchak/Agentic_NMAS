"""NetBox import and removal: the ONE code path v2's NetBox page (routes/netbox_v2.py, through
modules/netbox_jobs.py) calls (cutover blocker 2, 2026-10-10: moved out of today's routes,
behaviour unchanged, so two entry points shared one path; today's NetBox tab and its routes,
routes/netbox_safety.py, left at 7.8, 2026-10-17).

Each is a dry run of the real sync against the real NetBox (`dry_run`), which writes nothing and
returns a one-shot token bound to a hash of that exact plan, then a confirm (`authorize`) that
checks the master switch (a person may turn it on WITH this confirm, `permit_writes`, and it comes
on only after the token and the recomputed plan both pass, C330), consumes the token, recomputes
the plan and refuses if it moved. An import then runs on a thread (`start_import`), reporting
under its progress id; a removal runs in the request (`remove`). Every write carries the
verified person and the authority it stood on. Stop tracking (`forget`, C954) is previewed and
confirmed the same way, bound to a hash of Mercury's created record for the network; it writes
that record, never NetBox, so the master switch is not one of its gates.
"""

import logging
import os
import threading

log = logging.getLogger(__name__)

#: Pseudo-list name for the all-lists import, so a token issued for it cannot be replayed
#: against a single named list.
ALL_LISTS = "__all_lists__"
OPERATIONS = ("import", "import_all", "remove", "forget")


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
    """``(name, devices)`` for a list name; ``(None, None)`` for a name no list has, or for
    none. A write path carries its list: the active list's fallback for no name served only
    today's Import Current List, which left with today's NetBox tab at 7.8 (2026-10-17)."""
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists, load_saved_devices

    match = next((l for l in get_device_lists() if l["name"] == list_name), None) \
        if list_name else None
    if not match:
        return None, None
    return list_name, load_saved_devices(os.path.join(LISTS_DIR, match["filename"],
                                                      "devices.csv"))


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


def authorize(data: dict, operation: str, list_name: str, recompute, actor: str,
              switch: bool = True, moved=None) -> None:
    """Check the master switch, consume the token, re-verify the plan, and only then turn the
    switch on if the person permitted it. Raises `Refused`.

    *switch* False: the operation writes nothing to NetBox (Stop tracking, C954), so the master
    switch is neither checked nor turned on; the token and the recomputed plan still are.
    *moved(approved_hash, current_hash, current_plan)* words a moved plan's refusal, naming
    both operands."""
    from modules.netbox_authz import compute_plan_hash, consume_token, verify_plan_unchanged
    from modules.netbox_guard import writes_allowed

    permit = switch and bool(data.get("permit_writes")) and not writes_allowed()
    if switch and not writes_allowed() and not permit:
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
        if moved is not None:
            err = moved(approved_hash, compute_plan_hash(current_plan), current_plan)
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


def forget_plan(list_name: str) -> dict:
    """Stop tracking's plan (C954): ``{"forgets": [{"endpoint", "id", "name"}, ...]}``, every
    object Mercury's created record holds for *list_name*, read from that record alone (NetBox
    is not asked: nothing is sent to it). Raises `Refused` when the record cannot be read,
    which is not "it holds nothing"."""
    from modules.netbox_guard import recorded_objects

    held, reason = recorded_objects(list_name)
    if reason:
        raise Refused({"ok": False, "error": f"{reason}: nothing can be forgotten until it "
                                             "can be read"}, 500)
    return {"forgets": sorted(({"endpoint": ep, "id": oid, "name": name or ""}
                               for ep, oid, name in held),
                              key=lambda o: (o["endpoint"], str(o["id"])))}


def _forget_moved(list_name: str):
    def words(approved: str, now: str, plan: dict) -> str:
        return (f"Mercury's record of what it created for {list_name} changed since the "
                f"preview: the preview's entries hashed {approved[:12]}, the record's "
                f"{len(plan.get('forgets') or [])} entries now hash {now[:12]}: preview again")
    return words


def dry_run(operation: str, list_name: str, actor: str, progress_id: str = "") -> dict:
    """The preview's facts: ``{"ok", "list", "device_count"?, "plan", ...authorization}``, the
    raw dry run kept here (the caller masks what it draws). Raises `Refused`."""
    from modules import op_progress
    from modules.netbox_client import (remove_list_from_netbox, sync_all_lists_to_netbox,
                                       sync_list_to_netbox)

    if operation not in OPERATIONS:
        raise Refused({"ok": False, "error": f"no operation {operation!r}"}, 404)
    if operation == "forget":
        # Reads Mercury's own record only: NetBox is not asked, so it need not be configured.
        if not list_name:
            raise Refused({"ok": False, "error": "list_name is required"}, 400)
        plan = forget_plan(list_name)
        return {"ok": True, "list": list_name, "forgets": plan["forgets"],
                **authorization_for("forget", list_name, plan)}
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
                 progress_id: str = "", where: str = "v2's NetBox page", on_end=None) -> dict:
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
                op_progress.update(progress_id, phase="importing", devices_done=0,
                                   writing=True)
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
            op_progress.update(progress_id, phase="importing", devices_done=0, writing=True)
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


def remove(list_name: str, data: dict, actor: str, where: str = "v2's NetBox page",
           only=None) -> dict:
    """Confirm and run a removal of what Mercury created and recorded for *list_name*, in the
    request. Returns the sync's result; raises `Refused`. `data["forget_only"]` drops Mercury's
    record of exactly the entries *only* instead, which deletes nothing and needs neither the
    switch nor a token of its own: its one caller, v2's Stop tracking (`forget`), has confirmed
    by hash first. (Today's Just stop tracking called it unbound; it left with today's NetBox
    tab at 7.8, 2026-10-17.)"""
    from modules.netbox_client import remove_list_from_netbox

    if not list_name:
        raise Refused({"ok": False, "error": "list_name is required"}, 400)
    if data.get("forget_only"):
        return remove_list_from_netbox(list_name, forget_only=True, actor=actor, only=only)
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


def forget(list_name: str, data: dict, actor: str) -> dict:
    """Confirm and run v2's Stop tracking (C954): Mercury forgets the objects it created for
    *list_name*, deleting nothing in NetBox. The confirm is bound to a hash of the record's
    entries the preview read (`forget_plan`): the token is consumed, the record read again and
    hashed, and a record that moved is refused, naming both hashes. The master switch is not a
    gate: nothing is sent to NetBox. One NetBox writer per list holds from the check to the
    forget, so an import cannot record between them. The forgetting itself is `remove`'s
    `forget_only`, given exactly the confirmed entries. Returns its
    result; raises `Refused`."""
    from modules import netbox_guard as nbg

    if not list_name:
        raise Refused({"ok": False, "error": "list_name is required"}, 400)
    read = {}

    def recompute():
        read["plan"] = forget_plan(list_name)
        return read["plan"]
    try:
        with nbg.list_writer(list_name, "stop tracking", actor):
            authorize(data, "forget", list_name, recompute, actor, switch=False,
                      moved=_forget_moved(list_name))
            only = [(o["endpoint"], o["id"]) for o in read["plan"]["forgets"]]
            return remove(list_name, {"forget_only": True}, actor, only=only)
    except nbg.NetBoxBusy as exc:
        raise Refused({"ok": False, "busy": True, "error": (
            f"Not forgotten: {exc}. Mercury's record was not changed; confirm again once it "
            "finishes")}, 409) from None
