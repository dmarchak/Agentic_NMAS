"""routes/netbox_v2.py — Source of truth › NetBox on v2 (cutover blocker 2, 2026-10-10; the board
drawn under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md).

One page: NetBox's connection and the master switch, then every network with its devices, its last
import's result, and Import into NetBox… / Remove from NetBox…, with Import every network…. Each is
a preview job (`modules/netbox_jobs.py`, the real dry run on a thread), drawn in a card that redraws
when the job announces ``netbox``; the confirm is bound to that preview's one-shot token, gated
``approve`` as today's, and may turn NetBox writes on with it (C619: v2 could turn them off and not
on). The work is `modules/netbox_ops.py`'s, the one code path today's NetBox tab calls too.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict, _who

log = logging.getLogger(__name__)

bp = Blueprint("netbox_v2", __name__, url_prefix="/v2/netbox")


def _networks() -> list:
    """Every registered network: its devices, its last import's result, its removals."""
    import os

    from modules import netbox_guard
    from modules.config import list_data_path
    from modules.device import _load_devices_csv, get_device_lists
    from modules.netbox_client import sync_status_with_results

    lists = (sync_status_with_results().get("lists") or {})
    out = []
    for entry in get_device_lists():
        name = entry["name"]
        csv = os.path.join(list_data_path(name), "devices.csv")
        removals = netbox_guard.read_removals(name)
        last = lists.get(name) or {}
        out.append({"name": name,
                    "devices": len(_load_devices_csv(csv)) if os.path.exists(csv) else 0,
                    "last": last.get("result"), "last_at": str(last.get("timestamp") or ""),
                    "removals": len(removals.get("rows") or []),
                    "removals_unreadable": removals.get("state") == "unreadable"})
    return out


def _view() -> dict:
    from modules import installation_settings as I
    from modules import netbox_ops
    from modules.netbox_guard import writes_allowed

    return {"configured": netbox_ops.configured(), "health": I._health("netbox"),
            "writes": writes_allowed(), "networks": _networks()}


def _card(job: dict, code: int = 200, **ctx):
    from modules import op_progress

    progress = op_progress.get(job.get("id", "")) if job.get("id") else None
    return _strict(render_template("v2/_netbox_job.html", job=job, progress=progress, **ctx), code)


@bp.route("", methods=["GET"])
def page():
    """The NetBox page."""
    return _strict(render_template("v2/netbox.html", who=_who(), active_nav="netbox",
                                   v=_view()))


@bp.route("/preview", methods=["POST"])
def preview():
    """Start a preview job (import, import every network, or remove) and draw its card."""
    from modules import identity, netbox_jobs
    from modules.preview_confirm import confirm_part

    operation = (request.form.get("operation") or "").strip()
    list_name = (request.form.get("list") or "").strip()
    if operation not in ("import", "import_all", "remove"):
        return _card({"state": "refused", "error": f"no operation {operation!r}: import, "
                      "import_all or remove"}, 404)
    if operation != "import_all":
        from modules.nsot import listref
        if not listref.exists(list_name):
            return _card({"state": "refused", "error": f"there is no network {list_name!r}"},
                         404)
    job_id = netbox_jobs.start_preview(operation, list_name, identity.request_actor(),
                                       confirm_part(request, "approve"))
    return _card(netbox_jobs.read(job_id))


@bp.route("/job/<job_id>", methods=["GET"])
def job(job_id):
    """A job's card, redrawn from its record when it announces."""
    from modules import netbox_jobs

    return _card(netbox_jobs.read(job_id))


@bp.route("/job/<job_id>/confirm", methods=["POST"])
def confirm(job_id):
    """Confirm the previewed job: the import starts, or the removal runs; writes may come on
    with it when the person permits them."""
    from modules import identity, netbox_jobs, netbox_ops

    data = {"permit_writes": request.form.get("permit_writes") == "on"}
    current = netbox_jobs.read(job_id)
    try:
        if current.get("operation") == "remove":
            done = netbox_jobs.remove(job_id, data, identity.request_actor())
        else:
            done = netbox_jobs.start_import(job_id, data, identity.request_actor())
    except netbox_ops.Refused as exc:
        return _card(current, exc.status, refused=exc.payload.get("error", ""))
    return _card(done)


@bp.route("/removals", methods=["GET"])
def removals():
    """Every recorded removal of a network, newest first, drawn as at its apply."""
    from modules import netbox_guard
    from modules.preview_confirm import netbox_removal_result

    name = (request.args.get("list") or "").strip()
    got = netbox_guard.read_removals(name)
    rows = [{**netbox_guard.removal_heading(r), "result": netbox_removal_result(r)}
            for r in got.get("rows") or []][:20]
    return _strict(render_template("v2/_netbox_removals.html", name=name, state=got["state"],
                                   error=got.get("error", ""), rows=rows))
