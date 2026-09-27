"""The device list's two regions, re-rendered for an in-place redraw.

Stage 7.0, the first of the three measured cases (NSOT_STAGE7_GUI.md 6b):
onboarding's Verify promoted a device and the list still read `0 devices`
until a manual reload. The list is server-rendered, and a list with no
devices renders no table at all, so the redraw needs the SAME templates the
index uses (`partials/device_toolbar.html`, `partials/device_table.html`),
fed the same data. It reads the inventory and the in-memory ping cache and
does no per-device work (section 0a).
"""

import logging

from flask import Blueprint, current_app, jsonify, render_template

log = logging.getLogger(__name__)
bp = Blueprint("devices_view", __name__, url_prefix="/devices")


def _devices():
    """The active list's devices, each with `online`, exactly as the index
    computes them."""
    from modules.device import get_current_device_list, load_saved_devices

    name, csv_path = get_current_device_list()
    status = current_app.extensions.get("nmas_device_status", {})
    devices = load_saved_devices(csv_path)
    for d in devices:
        d["online"] = status.get(d["ip"], False)
    return name, devices


def _tftp_server() -> str:
    """The value the index renders into the bulk TFTP field. A getter, since
    `save_tftp_server` rebinds app.py's global at run time."""
    getter = current_app.extensions.get("nmas_tftp_server")
    return getter() if callable(getter) else ""


@bp.route("/regions", methods=["GET"])
def regions():
    try:
        name, devices = _devices()
        return jsonify({
            "ok": True, "list": name, "count": len(devices),
            "toolbar_html": render_template("partials/device_toolbar.html",
                                            devices=devices),
            "table_html": render_template("partials/device_table.html",
                                          devices=devices,
                                          tftp_server=_tftp_server()),
        })
    except Exception as exc:                  # noqa: BLE001
        log.exception("devices_view: could not render the device list")
        return jsonify({"ok": False, "error": str(exc)}), 500
