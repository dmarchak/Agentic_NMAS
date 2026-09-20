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


def _captured_config(repo: str, hostname: str):
    """``(config_text, mgmt_ip)`` for a device, resolved through the manifest.

    Same correction as on the deploy path: discovering the device by scanning
    ``golden_configs/`` took identity from the deprecated store while content
    came from the repo, so emptying that directory — which the migration
    permits — would report "no golden config" for a device that has one.
    """
    from modules.nsot import manifest as _m

    entry = _m.find_by_name(repo, hostname)[1]
    if entry:
        path = _m.golden_path_for(repo, entry)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read(), entry.get("mgmt_ip", "")

    from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
    legacy = next((e for e in _list_golden_configs()
                   if e.get("hostname") == hostname), None)
    if legacy is None:
        return "", ""
    return _load_golden_config_file(legacy["device_ip"]) or "", legacy["device_ip"]


def _extract(repo: str, hostname: str):
    """Parse a device's captured config. ``(result, error, status)``.

    Shared by extract and commit. The commit route **re-runs** this rather than
    reading the staged YAML back, because secret *values* exist only here: the
    staged file carries ``secret_refs`` by design, so promoting from it can
    never move a value into the credential store.
    """
    from modules.device import get_current_device_list, load_saved_devices
    from modules.nsot.roundtrip import validate_device

    config, device_ip = _captured_config(repo, hostname)
    if not config:
        return None, f"No golden config for '{hostname}'", 404

    _name, csv_path = get_current_device_list()
    device = next((d for d in load_saved_devices(csv_path)
                   if d.get("ip") == device_ip or d.get("hostname") == hostname), {})

    result = validate_device(config, _platform_for(device))
    if result.get("error"):
        return None, result["error"], 500
    return result, "", 200


@bp.route("/extract/<path:hostname>", methods=["POST"])
def extract(hostname):
    """Extract one device's host_vars to the staging area. Commits nothing."""
    from modules.nsot import hostvars

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)

    repo = _repo_for(list_name)
    result, error, _status = _extract(repo, hostname)
    if error:
        return jsonify({"ok": False, "error": error}), _status

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


# ---------------------------------------------------------------------------
# Committed intent
# ---------------------------------------------------------------------------

@bp.route("/committed", methods=["GET"])
def committed():
    """Devices that have committed intent. The deploy path reads only these."""
    from modules.nsot import hostvars

    repo = _repo_for(_active_list())
    return jsonify({"ok": True,
                    "committed": hostvars.list_committed(repo),
                    "staged": hostvars.list_staged(repo)})


@bp.route("/committed/<path:hostname>", methods=["GET"])
def read_committed(hostname):
    """The committed host_vars document, verbatim, for editing."""
    from modules.nsot import hostvars

    repo = _repo_for(_active_list())
    path = hostvars.committed_path(repo, hostname)
    if not os.path.exists(path):
        return jsonify({"ok": False, "committed": False, "error": (
            f"'{hostname}' has no committed intent. Extract it, review the "
            "diff, and commit before it can be deployed.")}), 404
    with open(path, encoding="utf-8") as fh:
        return jsonify({"ok": True, "hostname": hostname, "committed": True,
                        "yaml": fh.read()})


@bp.route("/commit/<path:hostname>", methods=["POST"])
def commit_extraction(hostname):
    """Promote a staged extraction to committed intent.

    The review-and-commit step Phase 3a deliberately stopped short of: staging
    is a proposal, this is the decision. ``save_host_vars()`` has existed and
    been tested since Phase 2 with no caller; this is its caller.

    Secrets move into the credential store **for real** here, not as a dry run.
    Committed intent references them by name, and the deploy path resolves
    those names in memory — so a reference with nothing behind it renders as a
    missing-secret marker rather than the value it should have had.
    """
    from modules.nsot import hostvars, repo as repo_service

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)

    staged_path = hostvars.staging_path(repo, hostname)
    if not os.path.exists(staged_path):
        return jsonify({"ok": False, "error": (
            f"Nothing staged for '{hostname}'. Extract it first.")}), 404

    # Re-derive from the capture: the staged YAML has refs, never values, so
    # promoting from it would commit an intent whose secrets resolve to
    # nothing — a render full of <missing-secret:…> that only the deploy
    # backstop would catch.
    fresh, error, status = _extract(repo, hostname)
    if error:
        return jsonify({"ok": False, "error": error}), status

    with open(staged_path, encoding="utf-8") as fh:
        reviewed = fh.read()
    if hostvars.to_yaml(fresh["host_vars"]) != reviewed:
        return jsonify({"ok": False, "error": (
            f"The captured config for '{hostname}' has changed since it was "
            "staged, so committing now would commit something nobody "
            "reviewed. Extract again and review the new diff.")}), 409

    secrets = hostvars.store_secrets(fresh["host_vars"], hostname, dry_run=False)
    try:
        path = hostvars.write_committed(repo, fresh["host_vars"])
    except hostvars.SecretLeak as exc:
        log.error("templatize: refused to commit host_vars for %s: %s",
                  hostname, exc)
        return jsonify({"ok": False, "error": str(exc)}), 400

    result = repo_service.save_host_vars(
        list_name, [hostname], actor=data.get("actor", "user"),
        message=f"host_vars: {hostname} commit reviewed extraction")
    return jsonify({"ok": result.get("ok", False),
                    "hostname": hostname,
                    "committed_path": os.path.relpath(path, repo),
                    "commit": result.get("commit", ""),
                    "message": result.get("message", ""),
                    "secrets": secrets,
                    "error": result.get("error", "")})


@bp.route("/committed/<path:hostname>", methods=["POST"])
def edit_committed(hostname):
    """Edit committed intent and commit the edit.

    **This is how a change is expressed.** Not by configuring the device and
    re-extracting — that makes intent a function of current state and can only
    ever produce an empty diff. Edit what the network is supposed to be, commit
    it, and the render diff *is* the change.
    """
    from modules.nsot import hostvars, repo as repo_service

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)
    text = data.get("yaml")
    summary = (data.get("summary") or "").strip()

    if not isinstance(text, str) or not text.strip():
        return jsonify({"ok": False, "error": "No host_vars document sent"}), 400
    if not summary:
        return jsonify({"ok": False, "error": (
            "A one-line summary is required — it becomes the commit subject, "
            "and 'host_vars: s4' on its own says nothing in a log.")}), 400
    if not os.path.exists(hostvars.committed_path(repo, hostname)):
        return jsonify({"ok": False, "error": (
            f"'{hostname}' has no committed intent yet. Commit the extraction "
            "first, so the edit has a reviewed baseline to diff against.")}), 404

    try:
        hostvars.write_committed_text(repo, hostname, text)
    except hostvars.SecretLeak as exc:
        log.error("templatize: refused host_vars edit for %s: %s", hostname, exc)
        return jsonify({"ok": False, "error": str(exc)}), 400
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    result = repo_service.save_host_vars(
        list_name, [hostname], actor=data.get("actor", "user"),
        message=f"host_vars: {hostname} {summary}")
    return jsonify({"ok": result.get("ok", False), "hostname": hostname,
                    "commit": result.get("commit", ""),
                    "message": result.get("message", ""),
                    "error": result.get("error", "")})


@bp.route("/committed/<path:hostname>/revert", methods=["POST"])
def revert_committed(hostname):
    """Undo the most recent intent edit, restoring the previous committed state.

    The other half of a rollback. Rollback restores the *device*; this restores
    the *intent*, which otherwise keeps asserting that the change should be
    there and makes the next plan propose exactly what just failed.

    A forward commit, not a ``git revert``: the intent history stays linear and
    a revert reads like any other edit, which is what it is. The rolled-back
    note is cleared because the thing it warned about is no longer what would
    be sent.
    """
    from modules.nsot import hostvars, repo as repo_service

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)

    change = hostvars.intent_change(repo, hostname)
    if not change.get("sha"):
        return jsonify({"ok": False, "error": (
            f"'{hostname}' has no committed intent to revert.")}), 404
    previous_sha = change.get("previous_sha")
    if not previous_sha:
        return jsonify({"ok": False, "error": (
            f"'{hostname}' has only one intent commit, so there is no previous "
            "state to restore. Edit the intent instead.")}), 409

    previous = hostvars.committed_at(repo, hostname, previous_sha)
    if previous is None:
        return jsonify({"ok": False, "error": (
            f"could not read host_vars at {previous_sha[:8]}")}), 500

    try:
        hostvars.write_committed(repo, previous)
    except (hostvars.SecretLeak, hostvars.NonPrintableContent) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    result = repo_service.save_host_vars(
        list_name, [hostname], actor=data.get("actor", "user"),
        message=(f"host_vars: {hostname} revert to {previous_sha[:8]} "
                 f"(undo {change['sha'][:8]})"))
    cleared = hostvars.clear_rolled_back(repo, hostname)

    return jsonify({"ok": result.get("ok", False), "hostname": hostname,
                    "reverted_from": change["sha"], "restored": previous_sha,
                    "commit": result.get("commit", ""),
                    "rolled_back_note_cleared": cleared,
                    "error": result.get("error", "")})


@bp.route("/rolled-back/<path:hostname>/retry", methods=["POST"])
def retry_rolled_back(hostname):
    """Deliberately allow a rolled-back change to be attempted again.

    The only way the block lifts while the failed change is still in intent,
    and it is an explicit action with a recorded reason. A retry that happened
    as a side effect of editing something else would be indistinguishable, in
    the log, from never having been blocked.
    """
    from modules.nsot import hostvars

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": (
            "A reason is required. This re-authorises a change that was rolled "
            "back after failing verification.")}), 400

    repo = _repo_for(_active_list(data))
    result = hostvars.authorise_retry(repo, hostname,
                                      actor=data.get("actor", "user"),
                                      reason=reason)
    return jsonify(result), (200 if result.get("ok") else 404)


@bp.route("/rolled-back/retries", methods=["GET"])
def rolled_back_retries():
    """Every authorised retry, for audit."""
    from modules.nsot import hostvars
    return jsonify({"ok": True,
                    "retries": hostvars.retry_log(_repo_for(_active_list()))})


@bp.route("/rolled-back", methods=["GET"])
def rolled_back():
    """Devices whose current intent was rolled back and not yet resolved."""
    from modules.nsot import hostvars

    repo = _repo_for(_active_list())
    notes = {}
    for hostname in hostvars.list_committed(repo):
        note = hostvars.rolled_back_note(repo, hostname)
        if note:
            notes[hostname] = note
    return jsonify({"ok": True, "rolled_back": notes})


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
