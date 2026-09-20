"""Deploy-from-template blueprint — Phase 3c.

The only route family in the NSoT work that reaches a device. Everything before
this point was deliberately inert; this is where the contract built in 3b is
either honoured or not.

Flow: **plan** (per-device diff and deployability, read-only) → operator
confirms per device → **apply** (fresh capture, drift check, push, verify,
golden save). Nothing is pushed without a confirmation token bound to what the
operator actually saw.
"""

import hashlib
import logging
import os

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("deploy", __name__, url_prefix="/deploy")


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _active_list(payload=None) -> str:
    from modules.config import get_current_list_name
    name = (payload or {}).get("list_name") or request.args.get("list_name") or ""
    return name.strip() or get_current_list_name()


def _capture_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _artifact_for(list_name: str, hostname: str):
    """Build the render artifact for one device from its captured config."""
    from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
    from modules.device import get_current_device_list, load_saved_devices
    from modules.nsot import approval, templates_repo
    from modules.nsot.render_artifact import build_artifact

    entry = next((e for e in _list_golden_configs()
                  if e.get("hostname") == hostname), None)
    if entry is None:
        return None, "no golden config for this device"
    captured = _load_golden_config_file(entry["device_ip"])
    if not captured:
        return None, "golden config is empty"

    _name, csv_path = get_current_device_list()
    device = next((d for d in load_saved_devices(csv_path)
                   if d.get("hostname") == hostname), {})
    platform = device.get("device_type", "cisco_ios")

    repo = _repo_for(list_name)
    template = templates_repo.template_for_device(repo, hostname, platform)

    artifact = build_artifact(hostname, captured, platform, template=template)
    approved = approval.is_approved(repo, template, {hostname: artifact.host_vars})
    if approved:
        artifact = build_artifact(hostname, captured, platform, template=template,
                                  template_approved=True,
                                  host_vars=artifact.host_vars)
    return (artifact, captured, device), ""


@bp.route("/plan", methods=["POST"])
def plan():
    """Per-device diff and deployability. Reads captured configs only."""
    from modules.nsot.deploy import merge_diff, prepare_device
    from modules.nsot.deploy import DeployRefused

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    hostnames = data.get("devices") or []
    if not hostnames:
        return jsonify({"ok": False, "error": "No devices selected"}), 400

    devices = []
    for hostname in hostnames:
        built, error = _artifact_for(list_name, hostname)
        if built is None:
            devices.append({"device": hostname, "deployable": False,
                            "blocking_reasons": [error], "to_add": [],
                            "removal_warnings": []})
            continue

        artifact, captured, _device = built
        entry = {**artifact.summary(),
                 "capture_hash": _capture_hash(captured)}

        try:
            prepared = prepare_device(artifact)
            diff = merge_diff(prepared["config"], captured)
            entry["to_add"] = diff["to_add"]
            entry["removal_warnings"] = diff["removal_warnings"]
            entry["unchanged_count"] = diff["unchanged_count"]
        except DeployRefused as exc:
            entry["to_add"] = []
            entry["removal_warnings"] = []
            entry["refused"] = str(exc)
        except Exception as exc:              # noqa: BLE001
            log.exception("deploy: plan failed for %s", hostname)
            entry["to_add"] = []
            entry["removal_warnings"] = []
            entry["error"] = str(exc)

        devices.append(entry)

    return jsonify({"ok": True, "list": list_name, "devices": devices,
                    "deployable_count": sum(1 for d in devices if d.get("deployable"))})


@bp.route("/apply", methods=["POST"])
def apply():
    """Deploy the confirmed devices through the pipeline.

    *confirmations* maps device → the capture hash shown in the plan. A device
    whose fresh capture no longer matches is skipped and reported, never
    deployed against a diff the operator did not see.
    """
    from modules.nsot.deploy import CircuitBreaker, plan_batch, run_batch

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    confirmations = data.get("confirmations") or {}
    if not confirmations:
        return jsonify({"ok": False,
                        "error": "Nothing confirmed — deploy refused"}), 400

    artifacts, fresh_captures, device_rows = [], {}, {}
    for hostname in confirmations:
        built, error = _artifact_for(list_name, hostname)
        if built is None:
            log.warning("deploy: %s unavailable: %s", hostname, error)
            continue
        artifact, captured, device = built
        artifacts.append(artifact)
        device_rows[hostname] = device
        # Phase 3c reads a FRESH capture inside the pipeline (stage 4). Here the
        # comparison is against the same captured artifact the plan used, so a
        # change committed between plan and apply is caught before connecting.
        fresh_captures[hostname] = captured

    batch = plan_batch(artifacts, confirmations, fresh_captures)

    report = run_batch(batch,
                       lambda entry: _deploy_one(entry, list_name, device_rows),
                       CircuitBreaker())
    return jsonify({"ok": True, "list": list_name, **report})


def _deploy_one(entry, list_name: str, device_rows: dict) -> dict:
    """Run the pipeline for a single device. The only path that connects."""
    import threading

    from modules.nsot.deploy import DEPLOYED, FAILED, prepare_device
    from modules.pipeline import PipelineContext, PipelineRunner

    artifact = entry["artifact"]
    hostname = artifact.device
    device = device_rows.get(hostname, {})

    try:
        prepared = prepare_device(artifact)     # refuse → real secrets → mask check
    except Exception as exc:                    # noqa: BLE001
        return {"device": hostname, "outcome": FAILED, "stage": "prepare",
                "reason": str(exc)}

    ctx = PipelineContext(
        config_type="template",
        device_ips=[device.get("ip", "")],
        params={"skip_route_check": True},
        ip_params_map={},
        selected_devices=[device],
        check_devices=[device],
        connections_pool={},
        pool_lock=threading.Lock(),
        config_id=f"tpl-{hostname}",
    )
    ctx.rendered_commands = {device.get("ip", ""): prepared["config"].splitlines()}

    try:
        result = PipelineRunner(ctx).run()
    except Exception as exc:                    # noqa: BLE001
        log.exception("deploy: pipeline raised for %s", hostname)
        return {"device": hostname, "outcome": FAILED, "stage": "pipeline",
                "reason": str(exc)}

    failed_stage = result.stages_failed[-1] if result.stages_failed else ""
    outcome = DEPLOYED if result.final_status == "success" else FAILED
    return {
        "device": hostname,
        "outcome": outcome,
        "stage": failed_stage,
        "reason": result.error or "",
        "rolled_back": result.rollback_performed,
        "pending_convergence": list(result.pending_convergence),
        "golden_commit": (result.golden_result or {}).get("commit", ""),
        "golden_skipped": list(result.golden_skipped),
        "warnings": list(result.warnings),
    }
