"""Templatize blueprint — Phase 3a, read-only.

Extraction, round-trip validation, and the coverage report. No editor, no
deploy, and **no commits**: extractions go to a gitignored staging area, and
Phase 3b adds the reviewed commit step.
"""

import logging
import os

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("templatize", __name__, url_prefix="/templatize")


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _active_list(payload=None) -> str:
    from modules.config import get_current_list_name
    name = (payload or {}).get("list_name") or request.args.get("list_name") or ""
    return name.strip() or get_current_list_name()


def _platform_for(device: dict) -> str:
    """The device's config dialect.

    Previously this returned the platform map's ``netmiko_device_type``, which
    is the session driver rather than the config dialect — the same conflation
    corrected in modules/nsot/platform.py.
    """
    from modules.nsot.platform import platform_for_device
    return platform_for_device(device)


@bp.route("/report", methods=["GET", "POST"])
def report():
    """Round-trip coverage for every device with a golden config.

    Reads golden configs only — it opens no SSH session and writes nothing.
    """
    from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
    from modules.device import get_current_device_list, load_saved_devices
    from modules.nsot.roundtrip import rank_unmodeled, validate_device

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)

    try:
        _name, csv_path = get_current_device_list()
        devices = {d.get("ip", ""): d for d in load_saved_devices(csv_path)}

        reports, errors = [], []
        for entry in _list_golden_configs():
            ip = entry.get("device_ip", "")
            config = _load_golden_config_file(ip)
            if not config:
                continue
            device = devices.get(ip, {})
            result = validate_device(config, _platform_for(device))
            if result.get("error"):
                errors.append({"hostname": entry.get("hostname", ip),
                               "error": result["error"]})
                continue
            reports.append(result)

        summary = _summarise(reports)
        return jsonify({
            "ok": True, "list": list_name,
            "devices": [_public(r) for r in reports],
            "summary": summary,
            "unmodeled_ranked": rank_unmodeled(reports),
            "errors": errors,
        })
    except Exception as exc:                  # noqa: BLE001
        log.exception("templatize: report failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/extract/<path:hostname>", methods=["POST"])
def extract(hostname):
    """Extract one device's host_vars to the staging area. Commits nothing."""
    from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
    from modules.device import get_current_device_list, load_saved_devices
    from modules.nsot import hostvars
    from modules.nsot.roundtrip import validate_device

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)

    entry = next((e for e in _list_golden_configs()
                  if e.get("hostname") == hostname), None)
    if entry is None:
        return jsonify({"ok": False,
                        "error": f"No golden config for '{hostname}'"}), 404

    config = _load_golden_config_file(entry["device_ip"])
    if not config:
        return jsonify({"ok": False, "error": "Golden config is empty"}), 400

    _name, csv_path = get_current_device_list()
    device = next((d for d in load_saved_devices(csv_path)
                   if d.get("ip") == entry["device_ip"]), {})

    result = validate_device(config, _platform_for(device))
    if result.get("error"):
        return jsonify({"ok": False, "error": result["error"]}), 500

    repo = _repo_for(list_name)
    path = hostvars.write_staged(repo, result["host_vars"])
    secrets = hostvars.store_secrets(result["host_vars"], hostname,
                                     dry_run=not data.get("store_secrets"))

    return jsonify({"ok": True, "hostname": hostname,
                    "staged_path": os.path.relpath(path, repo),
                    "committed": False,
                    "secrets": secrets, **_public(result)})


@bp.route("/staged", methods=["GET"])
def staged():
    """Extractions waiting in the staging area."""
    from modules.nsot import hostvars
    repo = _repo_for(_active_list())
    return jsonify({"ok": True, "staged": hostvars.list_staged(repo)})


@bp.route("/rendered/<path:hostname>", methods=["GET"])
def rendered(hostname):
    """The rendered config for a staged extraction, for eyeballing."""
    from modules.nsot import hostvars, roundtrip

    repo = _repo_for(_active_list())
    host_vars = hostvars.read_staged(repo, hostname)
    if host_vars is None:
        return jsonify({"ok": False, "error": "Not extracted yet"}), 404
    try:
        return jsonify({"ok": True, "hostname": hostname,
                        "rendered": roundtrip.render(host_vars,
                                                     host_vars.get("platform", "cisco_ios"))})
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


def _public(result: dict) -> dict:
    """Report fields for the UI — host_vars and rendered config excluded."""
    return {k: v for k, v in result.items()
            if k not in ("host_vars", "rendered", "details")} | {
        "missing_sample": [m["line"] for m in result.get("details", {}).get("missing", [])[:20]],
        "extra_sample": [e["line"] for e in result.get("details", {}).get("extra", [])[:20]],
        "reordered": result.get("details", {}).get("reordered", []),
    }


def _summarise(reports: list) -> dict:
    if not reports:
        return {"devices": 0, "mean_modeled_coverage": 0.0,
                "mean_round_trip_fidelity": 0.0, "fully_reproduced": 0}
    count = len(reports)
    return {
        "devices": count,
        "mean_modeled_coverage": round(
            sum(r["modeled_coverage"] for r in reports) / count, 1),
        "mean_round_trip_fidelity": round(
            sum(r["round_trip_fidelity"] for r in reports) / count, 1),
        "fully_reproduced": sum(1 for r in reports if r["ok"]),
        "total_unmodeled": sum(r["unmodeled"] for r in reports),
    }
