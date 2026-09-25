"""Integrations settings blueprint.

Backs Settings → Integrations. Every field is user-supplied: no endpoint,
credential, query template, or identity mapping is hardcoded, so the tool stays
network-agnostic.

Secrets are write-only over the wire. A GET returns a set/unset indicator, never
a value; a POST with an empty secret field leaves the stored value untouched.
"""

import logging

from flask import Blueprint, jsonify, request

from modules.integrations import REGISTRY, all_statuses, get_integration
from modules.settings_schema import DEFAULTS, get_setting, migrate, validate
from modules.config import load_user_settings, save_user_settings, settings_lock
from modules.secrets_store import SECRET_KEYS

log = logging.getLogger(__name__)

bp = Blueprint("settings_integrations", __name__, url_prefix="/settings/integrations")


@bp.route("", methods=["GET"])
def get_integrations():
    """Return every integration's settings, with secrets masked."""
    try:
        migrate()
        out = {}
        for name in REGISTRY:
            client = get_integration(name)
            out[name] = client.get_config()
            out[name]["label"] = client.label
        return jsonify({"ok": True, "integrations": out})
    except Exception as exc:                  # noqa: BLE001
        log.exception("settings_integrations: GET failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/<name>", methods=["POST"])
def save_integration(name):
    """Persist one integration's settings."""
    client = get_integration(name)
    if client is None:
        return jsonify({"ok": False, "error": f"Unknown integration '{name}'"}), 404

    values = request.get_json(silent=True) or {}
    try:
        # Validate the non-secret values before writing anything.
        candidate = load_user_settings()
        candidate.update({k: v for k, v in values.items() if k not in SECRET_KEYS})
        ok, err = validate(candidate)
        if not ok:
            return jsonify({"ok": False, "error": f"Invalid setting — {err}"}), 400

        client.save_config(values)
        log.info("settings_integrations: saved '%s'", name)
        return jsonify({"ok": True, "integration": client.get_config()})
    except Exception as exc:                  # noqa: BLE001
        log.exception("settings_integrations: save '%s' failed", name)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/<name>/test", methods=["POST"])
def test_integration(name):
    """Probe one integration. Never raises; a failure is reported, not thrown."""
    client = get_integration(name)
    if client is None:
        return jsonify({"ok": False, "error": f"Unknown integration '{name}'"}), 404
    try:
        return jsonify(client.test_connection())
    except Exception as exc:                  # noqa: BLE001
        log.warning("settings_integrations: test '%s' raised: %s", name, exc)
        return jsonify({"ok": False, "error": str(exc)})


@bp.route("/status", methods=["GET"])
def integration_status():
    """Badge state for the dashboard strip: green / red / grey per tool."""
    try:
        return jsonify({"ok": True, "statuses": all_statuses()})
    except Exception as exc:                  # noqa: BLE001
        log.exception("settings_integrations: status failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/general", methods=["GET", "POST"])
def general_settings():
    """Settings that are not tied to one integration.

    Server bind, browser auto-open, TFTP, Jenkins step shell, collector toggles,
    monitoring identity mapping, and the PromQL query templates.
    """
    keys = (
        "flask_host", "flask_port", "auto_open_browser",
        "tftp_root", "tftp_server_ip",
        "jenkins_step_shell",
        "collector_trap_enabled", "collector_netflow_enabled",
        "collector_syslog_enabled",
        "monitoring_identity_mode", "monitoring_identity_field",
        "monitoring_prom_label", "monitoring_strip_port",
        "promql_device_up", "promql_cpu", "promql_interface_oper",
    )

    if request.method == "GET":
        migrate()
        return jsonify({"ok": True,
                        "settings": {k: get_setting(k, DEFAULTS.get(k)) for k in keys}})

    values = request.get_json(silent=True) or {}
    try:
        # A read-modify-write outside `write_settings()`, so it takes the
        # lock itself (C20).
        with settings_lock():
            settings = load_user_settings()
            settings.update({k: v for k, v in values.items() if k in keys})
            ok, err = validate(settings)
            if not ok:
                return jsonify({"ok": False, "error": f"Invalid setting — {err}"}), 400
            save_user_settings(settings)
        log.info("settings_integrations: saved general settings (%d key(s))",
                 len([k for k in values if k in keys]))
        return jsonify({"ok": True,
                        "settings": {k: get_setting(k, DEFAULTS.get(k)) for k in keys},
                        "restart_required": any(k in values
                                                for k in ("flask_host", "flask_port"))})
    except Exception as exc:                  # noqa: BLE001
        log.exception("settings_integrations: general save failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
