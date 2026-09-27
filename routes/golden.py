"""Golden config repository blueprint: timeline, diffs, baselines, migration."""

import logging
import os

from flask import Blueprint, jsonify, request

from modules.identity import request_actor

log = logging.getLogger(__name__)

bp = Blueprint("golden", __name__, url_prefix="/golden")


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _active_list(payload=None) -> str:
    from modules.config import get_current_list_name
    name = (payload or {}).get("list_name") or request.args.get("list_name") or ""
    return name.strip() or get_current_list_name()


def _serve_config(text: str, *, what: str, target: str, detail: str = ""):
    """``(payload, status)`` for config text, masked unless revealed. The
    pattern lives in `modules/outbound.py` since register C56, so the backup
    download and these routes are one pattern rather than two."""
    from modules import outbound

    return outbound.config_text(request, text, what=what, target=target, detail=detail)


@bp.route("/history/<path:hostname>", methods=["GET"])
def history(hostname):
    """Promotion timeline for one device, following renames."""
    from modules.nsot.repo import get_ci_note, golden_history

    list_name = _active_list()
    repo = _repo_for(list_name)
    try:
        entries = golden_history(repo, hostname)
        for entry in entries:
            entry["ci"] = get_ci_note(repo, entry["sha"])
        return jsonify({"ok": True, "hostname": hostname, "list": list_name,
                        "history": entries})
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: history failed for %s", hostname)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/version/<path:hostname>", methods=["GET"])
def version(hostname):
    """One device's golden config at a given ref."""
    from modules.nsot.repo import golden_at

    ref = request.args.get("ref", "HEAD")
    content = golden_at(_repo_for(_active_list()), hostname, ref)
    if content is None:
        return jsonify({"ok": False,
                        "error": f"No golden config for {hostname} at {ref}"}), 404

    payload, status = _serve_config(content, what="golden_config",
                                    target=hostname, detail=ref)
    payload["config"] = payload.pop("text")
    return jsonify({**payload, "hostname": hostname, "ref": ref}), status


@bp.route("/diff/<path:hostname>", methods=["GET"])
def diff(hostname):
    """Unified diff of one device's golden config between two refs."""
    import difflib

    from modules.nsot.repo import golden_at

    repo = _repo_for(_active_list())
    ref_a = request.args.get("a", "")
    ref_b = request.args.get("b", "HEAD")
    if not ref_a:
        return jsonify({"ok": False, "error": "Parameter 'a' is required"}), 400

    left, right = golden_at(repo, hostname, ref_a), golden_at(repo, hostname, ref_b)
    if left is None or right is None:
        return jsonify({"ok": False,
                        "error": "One of the versions has no golden config"}), 404

    lines = list(difflib.unified_diff(
        left.splitlines(), right.splitlines(),
        fromfile=f"{hostname}@{ref_a}", tofile=f"{hostname}@{ref_b}", lineterm=""))

    # A diff of two configs carries the same secrets as either of them, on the
    # `-` and `+` lines. Easy to leave masked-by-default behind when adding a
    # view, which is why both go through one helper.
    payload, status = _serve_config("\n".join(lines), what="golden_diff",
                                    target=hostname,
                                    detail=f"{ref_a}..{ref_b}")
    payload["diff"] = payload.pop("text")
    return jsonify({**payload, "hostname": hostname, "a": ref_a, "b": ref_b,
                    "changed": bool(lines)}), status


@bp.route("/baselines", methods=["GET"])
def baselines():
    """Network-wide restore points."""
    from modules.nsot.repo import devices_at, list_baselines

    repo = _repo_for(_active_list())
    try:
        from modules.nsot.restore import baseline_credential_gaps

        list_name = _active_list()
        entries = list_baselines(repo)
        # The population, read ONCE for all baselines.
        from modules.device import load_saved_devices
        from modules.config import get_list_data_dir
        inventory = {d.get("hostname", "") for d in load_saved_devices(
            os.path.join(get_list_data_dir(list_name), "devices.csv"))}

        for entry in entries:
            devices = devices_at(repo, entry["tag"])
            entry["device_count"] = len(devices)
            # The scope chooser (C80) lists these, none ticked.
            entry["devices"] = sorted(devices)
            # PARTIAL RELATIVE TO TODAY'S FLEET, named rather than left to
            # arithmetic. The count alone made an older baseline read "9"
            # and a newer one "10" with nothing saying the first covers less
            # than the network does now -- visible as a number, and a number
            # is not a statement. A device onboarded after the tag has no
            # golden at it, so re-applying leaves that device untouched:
            # correct, and not what "restore the network" sounds like.
            entry["inventory_size"] = len(inventory)
            entry["missing_devices"] = sorted(inventory - set(devices))
            entry["partial"] = bool(entry["missing_devices"])
            # Which devices' credentials this ref predates, computed here so
            # it can be shown BESIDE the re-apply button rather than after
            # the operator has committed to the operation.
            gaps = baseline_credential_gaps(repo, entry["tag"], list_name,
                                            devices)
            entry["credential_stale"] = sorted(gaps["stale"])
            entry["credential_detail"] = gaps["stale"]
            # Stale AND refused by neither guard. Since C75 nothing that
            # rewrites a held credential passes, so these would only ADD an
            # account the baseline has and the device lacks.
            entry["credential_silent"] = gaps["silent"]
            entry["credential_refused"] = gaps["refused"]
            # The restore's own credential guard refuses these (C75).
            entry["credential_guarded"] = gaps["guarded"]
            entry["no_intent"] = gaps["no_golden"]
        return jsonify({"ok": True, "baselines": entries})
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/restore_points/<path:hostname>", methods=["GET"])
def restore_points(hostname):
    """Where one device can be restored from (C80, 7.1 step 5): the Device
    page's "Restore from…" chooser. Reads only.

    Each point carries this device's credential state at that ref, measured
    the way the Baselines panel measures it, so the chooser warns BEFORE the
    click: ``current``, ``refused`` (the restore's own guards stop it),
    ``silent`` (an account the ref has and the device lacks would be ADDED
    back) or ``no_golden``. The username lines themselves never leave."""
    from modules.nsot.repo import device_restore_points
    from modules.nsot.restore import baseline_credential_gaps

    list_name = _active_list()
    repo = _repo_for(list_name)
    try:
        points = device_restore_points(repo, hostname)
        for point in points:
            if point["kind"] == "head":
                point["credential"] = "current"
                continue
            gaps = baseline_credential_gaps(repo, point["ref"], list_name, [hostname])
            if hostname in gaps["no_golden"]:
                point["credential"] = "no_golden"
            elif hostname in gaps["silent"]:
                point["credential"] = "silent"
            elif hostname in set(gaps["refused"]) | set(gaps["guarded"]):
                point["credential"] = "refused"
            else:
                point["credential"] = "current"
        return jsonify({"ok": True, "hostname": hostname, "list": list_name,
                        "points": points})
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: restore points failed for %s", hostname)
        return jsonify({"ok": False, "error": str(exc)}), 500


def _read_running(device: dict) -> tuple:
    """``(running_config, error)`` read NOW from *device* (the list's own
    row, carried, never looked up in the active list)."""
    from modules.commands import run_device_command
    from modules.connection import with_temp_connection

    # A temporary connection, closed when the read ends. It was a persistent
    # connection in a fresh pool nobody kept, so every preview and apply left
    # a session open until the device timed it out (C97).
    try:
        text = with_temp_connection(
            device, lambda conn: run_device_command(conn, "show running-config"))
    except Exception as exc:                  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    return (text, "") if text else (None, "the device returned an empty running config")


def _capture_entry(list_name: str, repo: str, device: dict) -> tuple:
    """``(entry, running_config)`` for one device read for a capture: what
    its golden would become, and how that compares with its committed INTENT
    (C89). The raw config is returned BESIDE the entry, never in it, so it
    cannot reach a response."""
    import difflib

    from modules.nsot.intent_match import intent_match
    from modules.nsot.platform import platform_for_device
    from modules.nsot.repo import golden_body
    from routes.deploy import _capture_hash, _captured_config

    host, ip = device.get("hostname", ""), device.get("ip", "")
    platform = platform_for_device(device)
    text, error = _read_running(device)
    if text is None:
        return {"device": host, "read": False, "error": error, "platform": platform}, None
    current = _captured_config(repo, host)
    incoming = golden_body(host, ip, text)
    diff = [l for l in difflib.unified_diff(current.splitlines(), incoming.splitlines(),
                                             lineterm="", n=1)
            if not l.startswith(("---", "+++"))]
    return ({"device": host, "read": True, "error": "", "platform": platform,
             "capture_hash": _capture_hash(text), "changed": incoming != current,
             "diff": diff, "intent": intent_match(repo, list_name, host, text, platform)},
            text)


@bp.route("/capture/preview", methods=["POST"])
def capture_preview():
    """Record running configs as goldens: the PREVIEW (7.1 step 4, C82, C89).

    Reads each device NOW and shows what its golden would become and how that
    compares with its committed intent. No `devices` is the whole fleet (what
    Save All now opens). Masked on the way out; writes nothing."""
    from modules.nsot.restore import _devices_of
    from modules.outbound import mask_payload
    from modules.preview_confirm import capture_preview as _parts

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    inventory = _devices_of(list_name)
    wanted = [d for d in (data.get("devices") or []) if d]
    names = {d.get("hostname") for d in inventory}
    unknown = sorted(set(wanted) - names)
    if unknown:
        return jsonify({"ok": False, "error": f"not in {list_name}: {', '.join(unknown)}"}), 404
    repo = _repo_for(list_name)
    scope = data.get("scope") or ""
    if scope and scope != "no_golden":
        return jsonify({"ok": False, "error": f"unknown capture scope {scope!r}"}), 400
    excluded = []
    if scope == "no_golden":
        # What Auto-Create was, as a scope of the ONE capture operation
        # (minimalism, NSOT_STAGE7_PLAN section 6a): every device with no
        # COMMITTED golden, or a refused one (a refusal's own remedy is to
        # capture the device). Decided from git, never from files on disk.
        from modules.nsot import manifest as _m
        from modules.nsot.repo import committed_golden_for
        devices = []
        for d in inventory:
            record = committed_golden_for(repo, _m.find_by_name(repo, d.get("hostname", ""))[1])
            if record["text"] is None:
                devices.append(d)
            else:
                excluded.append(d.get("hostname", ""))
        if not devices:
            return jsonify({"ok": True, "list": list_name, "fleet": False, "preview": None,
                            "nothing": (f"Every device in {list_name} has a committed golden "
                                        f"({len(excluded)} device(s)): nothing to capture, "
                                        f"and nothing was read.")})
        fleet = False
    else:
        fleet = not wanted
        devices = [d for d in inventory if fleet or d.get("hostname") in set(wanted)]
    entries = [_capture_entry(list_name, repo, d)[0] for d in devices]
    preview = _parts(entries, fleet=fleet, inventory=inventory, request=request,
                     not_read=excluded)
    # The preview alone: it draws each device's read, and its `select_data`
    # carries the hash the confirm is bound to. The raw reads are not sent.
    # `nothing` is always carried (empty here): one payload shape whether or
    # not a scope found anything, so the client reads a key that is there.
    return jsonify(mask_payload({"ok": True, "list": list_name, "fleet": fleet,
                                 "preview": preview, "nothing": ""}))


@bp.route("/capture/apply", methods=["POST"])
def capture_apply():
    """Record the confirmed captures: each device is READ AGAIN, and one whose
    running config moved since the preview is refused. One commit, as the
    verified person, through `save_golden()`, which writes the computed
    `Intent-Match:` trailer and takes a baseline only for a whole-fleet
    capture with every device at its committed intent (C89 (c))."""
    from modules.identity import request_actor
    from modules.nsot.repo import GoldenItem, save_golden
    from modules.nsot.restore import _devices_of
    from modules.outbound import mask_payload
    from modules.preview_confirm import capture_result
    from routes.deploy import _capture_hash

    data = request.get_json(silent=True) or {}
    confirmations = {k: v for k, v in (data.get("confirmations") or {}).items() if k}
    if not confirmations:
        return jsonify({"ok": False, "error": "Nothing confirmed: nothing recorded"}), 400
    list_name = _active_list(data)
    fleet = bool(data.get("fleet"))
    inventory = _devices_of(list_name)
    repo = _repo_for(list_name)
    # One operation per device (C98): a capture recording a device while a
    # deploy or restore changes it would record a half-made state.
    from modules.nsot import device_ops
    held, refused_busy = device_ops.acquire_many(
        list_name, [d.get("hostname", "") for d in inventory
                    if d.get("hostname", "") in confirmations], "capture", request_actor())
    busy = {r["device"]: r["reason"] for r in refused_busy}
    try:
        outcomes, items, skipped, texts = [], [], [], {}
        for device in inventory:
            host = device.get("hostname", "")
            if host not in confirmations:
                skipped.append({"hostname": host, "reason": "not confirmed"})
                continue
            if host in busy:
                outcomes.append({"device": host, "outcome": "busy", "reason": busy[host]})
                skipped.append({"hostname": host, "reason": "another operation holds it"})
                continue
            entry, text = _capture_entry(list_name, repo, device)
            if not entry["read"]:
                outcomes.append({"device": host, "outcome": "unread", "reason": entry["error"]})
                skipped.append({"hostname": host, "reason": "could not be read"})
                continue
            if entry["capture_hash"] != confirmations[host]:
                outcomes.append({"device": host, "outcome": "moved",
                                 "reason": f"its running config moved since the preview "
                                           f"({confirmations[host]} -> {entry['capture_hash']})"})
                skipped.append({"hostname": host, "reason": "moved since the preview"})
                continue
            outcomes.append({"device": host, "outcome": "pending", "diff": entry["diff"],
                             "intent": entry["intent"], "platform": entry["platform"]})
            texts[host] = text
        # The configs to record are the ones just read and matched to the confirmed
        # hash; read once more would be a third read with no one to confirm it.
        pending = [o for o in outcomes if o["outcome"] == "pending"]
        save = {}
        if pending:
            by_host = {d.get("hostname"): d for d in inventory}
            for o in pending:
                d = by_host[o["device"]]
                items.append(GoldenItem(o["device"], texts[o["device"]], d.get("ip", ""),
                                        netbox_id=d.get("_netbox_id"),
                                        device_uid=d.get("device_uid", ""),
                                        platform=o["platform"]))
            save = save_golden(list_name, items, source="save_all" if fleet else "capture",
                               actor=request_actor(), allow_new=False,
                               inventory_size=len(inventory) if fleet else 0,
                               skipped=skipped, baseline=None if fleet else False)
            for o in pending:
                if not save.get("ok"):
                    o.update(outcome="unread", reason=save.get("error") or "the save failed")
                else:
                    o["outcome"] = ("captured" if o["device"] in (save.get("changed") or [])
                                    else "unchanged")
                    o["intent"] = (save.get("intent") or {}).get(o["device"], o["intent"])
        result = capture_result(outcomes, save, fleet=fleet)
        return jsonify(mask_payload({"ok": True, "list": list_name, "fleet": fleet,
                                     "result": result}))
    finally:
        device_ops.release_many(list_name, held)


@bp.route("/restore/preview", methods=["POST"])
def restore_preview():
    """What re-applying a ref would do, per device, before anything is sent.

    **Additive.** This re-applies stored configuration; it does not remove
    lines a device has gained since. The three categories exist so that
    distinction is visible rather than implied:

    * ``add``     — in the stored config, absent from the device
    * ``replace`` — in the stored config, the device sets it to something else
    * ``residue`` — on the device, the stored config does not mention it

    Only ``residue`` is left behind, so only ``residue`` is reported as "will
    not be removed". The previous report listed every device line absent from
    the target, which included lines about to be overwritten.
    """
    from modules.nsot.deploy import (NotAuthorised, assert_authorised,
                                     command_fingerprint, dangerous_in,
                                     merge_commands, merge_diff,
                                     prepare_restore, residue_in_context)
    from modules.nsot import normalize
    from modules.nsot.restore import build_targets
    from routes.deploy import _capture_hash

    data = request.get_json(silent=True) or {}
    ref = (data.get("ref") or "").strip()
    if not ref:
        return jsonify({"ok": False, "error": "ref is required"}), 400

    list_name = _active_list(data)
    # Per device, exactly as /deploy/plan: an authorisation for one device
    # never covers another. It is folded into the command hash, so the apply
    # (run_targets) recomputes both, and a restore can now carry a dangerous
    # line that a person authorised. It could not before (P.3 step 4).
    authorise = data.get("authorise") or {}
    try:
        targets, skipped = build_targets(list_name, ref, data.get("devices"),
                                         un_onboard=data.get("un_onboard"))
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: restore preview failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

    devices = []
    for target in targets:
        entry = {"device": target.device, "platform": target.platform,
                 "deployable": target.deployable,
                 "blocking_reasons": target.blocking_reasons,
                 "capture_hash": _capture_hash(target.captured),
                 # The restore's own gates, by name: the list its refusal is
                 # computed from, so the preview and the refusal cannot differ.
                 "checks": [{"name": n, "state": st, "detail": dt}
                            for n, st, dt in target.checks],
                 # The intent half of the same unit, stated before it happens.
                 "intent": _intent_preview(list_name, target)}
        try:
            prepared = prepare_restore(target)
            diff = merge_diff(prepared["config"], target.captured)
            commands = merge_commands(prepared["config"], target.captured)
            entry.update({
                "add": diff["add"],
                "replace": diff["replace"],
                "residue": diff["residue"],
                # Each residue line under its section (C73, which the deploy
                # preview had and this path had too).
                "residue_in_context": residue_in_context(diff["residue"],
                                                         target.captured),
                # Blocks a re-apply cannot send at all — certificate chains,
                # licence UDI, banners. Correct to exclude, and the operator
                # has to know: a drifted banner on s3 is NOT re-applied by
                # this, and "100%" would otherwise imply it was.
                "excluded_unrenderable": normalize.excluded_unrenderable(
                    target.target_config),
                "commands": commands,
                "dangerous": dangerous_in(commands),
                "unchanged_count": diff["unchanged_count"],
            })
            authorised = [a.strip() for a in (authorise.get(target.device) or [])]
            entry["authorised"] = authorised
            entry["command_hash"] = command_fingerprint(commands, authorised)
            if entry["dangerous"] or authorised:
                try:
                    assert_authorised(commands, authorised)
                    entry["authorisation_ok"] = True
                except NotAuthorised as exc:
                    entry["authorisation_ok"] = False
                    entry["authorisation_error"] = str(exc)
        except Exception as exc:              # noqa: BLE001
            entry.update({"add": [], "replace": [], "residue": [],
                          "commands": [],
                          "excluded_unrenderable": normalize.excluded_unrenderable(
                              target.target_config),
                          "error": str(exc)})
        devices.append(entry)

    from modules.nsot.restore import coverage
    cov = coverage(list_name, data.get("devices"), skipped)
    residue_total = sum(len(d.get("residue") or []) for d in devices)
    excluded_total = sum(len(d.get("excluded_unrenderable") or [])
                         for d in devices)
    intent_restored = [d["device"] for d in devices
                       if (d.get("intent") or {}).get("action") == "restore"]
    un_onboarding = [d["device"] for d in devices
                     if (d.get("intent") or {}).get("action") == "un_onboard"]
    scope = ("Device configuration AND committed intent from this ref — "
             "one unit per device, one commit. Never templates, bindings "
             "or approvals: those are code, and rolling them back to fix "
             "a network would silently revert template fixes.")
    summary = (
        f"Re-applying stored configuration to {len(devices)} of "
        f"{cov['denominator']} device(s) {cov['scope_words']}."
        + (" This ref is a PARTIAL restore point: it predates "
           + ", ".join(s["hostname"] for s in skipped if s.get("not_at_ref"))
           + ", which will be left exactly as they are."
           if cov["partial"] else "")
        + (f" {residue_total} line(s) present on devices are absent from "
           "this ref and will NOT be removed." if residue_total else "")
        + (f" {excluded_total} block(s) cannot be re-applied at all "
           "(certificates, licence UDI, banners)." if excluded_total else "")
        + (f" Committed intent moves back to this ref for "
           f"{len(intent_restored)} device(s)." if intent_restored else "")
        + (f" UN-ONBOARDING (committed intent removed): "
           f"{', '.join(un_onboarding)}." if un_onboarding else "")
        + (f" Skipped: {', '.join(s['hostname'] for s in skipped)}."
           if skipped else ""))
    # Stage 7.1: the six parts, from the one builder, drawn by the one
    # renderer. The fields below stay: the apply's confirmations are read
    # from them by the same client.
    from modules.preview_confirm import restore_preview as _parts
    preview = _parts(devices, skipped, ref=ref, summary=summary, scope=scope,
                     request=request)
    # Masked on the way out, AFTER every hash is computed from the truthful
    # program (C77): stored config lines (the program, residue, what a line
    # replaces) came back verbatim.
    from modules.outbound import mask_payload
    return jsonify(mask_payload({
        "ok": True, "ref": ref, "list": list_name, "mode": "re-apply",
        "devices": devices, "skipped": skipped, "preview": preview,
        "intent_restored": intent_restored, "un_onboarding": un_onboarding,
        # Echoed back so the confirm dialog can show "what the agent saw"
        # beside the freshly computed program. Never an input to anything.
        "advisory_diff": (data.get("advisory_diff") or ""),
        "approval_id": (data.get("approval_id") or ""),
        "scope": scope,
        # C23: the denominator is the INVENTORY for a whole restore and the
        # selection for a scoped one, never "whatever the ref happened to
        # hold". A device the ref predates is named in `skipped`.
        "inventory_size": cov["inventory_size"],
        "partial": cov["partial"],
        "summary": summary,
    }))


def _intent_preview(list_name: str, target) -> dict:
    """What the intent half of this device's restore will do. Reads only.

    Device and intent move as one unit, so the preview has to show both. The
    three outcomes are ``unchanged`` (the ref's intent is what is committed
    today), ``restore`` (it differs and will be re-committed forward), and
    ``un_onboard`` (the ref predates the device and the operator ticked it).
    """
    import os as _os

    from modules.config import get_list_data_dir
    from modules.nsot import hostvars

    repo = _os.path.join(get_list_data_dir(list_name), "config_repo")
    text = getattr(target, "ref_intent_text", "") or ""

    if getattr(target, "un_onboard", False):
        return {"action": "un_onboard",
                "detail": ("Committed intent for this device will be REMOVED "
                           "by a forward commit — recoverable from git "
                           "history, but it un-does the onboarding review.")}
    if not text:
        return {"action": "none", "detail": "no committed intent at this ref"}

    # Committed intent is what is at HEAD (C104), not the working file.
    current = hostvars.committed_at_head(repo, target.device)[0] or ""
    if current == text:
        return {"action": "unchanged",
                "detail": "committed intent already matches this ref"}
    return {"action": "restore",
            "detail": ("Committed intent will be set back to this ref's "
                       "version by a forward commit." if current else
                       "This device has no committed intent today; the ref's "
                       "will be committed."),
            "had_intent": bool(current)}


@bp.route("/restore/apply", methods=["POST"])
def restore_apply():
    """Re-apply a ref through the confirmed deploy path.

    Not the approval queue. That path pushed whole-config text with none of the
    guarantees built since: no confirm hash, no ASCII guard, no provenance, no
    ``error_pattern``, no failure capture, no rollback. Any entry it left
    queued is rejected on first use of this route, because executing one now
    would send exactly the payload this replaced.
    """
    from modules.nsot.restore import build_targets, invalidate_queued_restores
    from routes.deploy import run_targets

    data = request.get_json(silent=True) or {}
    ref = (data.get("ref") or "").strip()
    if not ref:
        return jsonify({"ok": False, "error": "ref is required"}), 400
    confirmations = data.get("confirmations") or {}
    if not confirmations:
        return jsonify({"ok": False,
                        "error": "Nothing confirmed — re-apply refused"}), 400

    list_name = _active_list(data)
    invalidated = invalidate_queued_restores()
    try:
        targets, skipped = build_targets(list_name, ref, list(confirmations),
                                         un_onboard=data.get("un_onboard"))
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: restore apply failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

    report = run_targets(list_name, targets, data,
                         label=f"re-apply {ref}", source_ref=ref, skipped=skipped)
    report.update({"ref": ref, "mode": "re-apply", "skipped": skipped,
                   "invalidated_queue_items": invalidated["rejected"]})

    # Close the queue item that handed off to this, but ONLY for devices that
    # actually succeeded. An item left pending for ever teaches the operator to
    # clear the queue by rejecting things, which is the habit that makes an
    # approval queue worthless; an item closed on a failed push would be the
    # queue claiming work that did not happen.
    approval_id = (data.get("approval_id") or "").strip()
    if approval_id:
        from modules.approval_queue import mark_done
        from modules.nsot.deploy import DEPLOYED

        succeeded = [r.get("device") for r in (report.get("results") or [])
                     if r.get("outcome") == DEPLOYED]
        if succeeded:
            closed = mark_done(approval_id,
                               f"Re-applied {ref} to {', '.join(succeeded)} "
                               "through the confirmed deploy path")
            report["approval_closed"] = closed.get("ok", False)
        else:
            report["approval_closed"] = False
            report["approval_note"] = (
                "left pending: no device completed successfully")

    # Masked on the way out (C77's apply side, measured 2026-09-27: a planted
    # community came back in `results[].commands`). The receipts and the
    # golden commit are written above from the truthful report; nothing
    # reads this response back into a confirm.
    from modules.outbound import mask_payload
    return jsonify(mask_payload({"ok": True, "list": list_name, **report}))


@bp.route("/migrate/plan", methods=["GET", "POST"])
def migrate_plan():
    """Dry-run migration report. Writes nothing — this is the UI default."""
    from modules.nsot.migrate import plan

    data = request.get_json(silent=True) or {}
    try:
        return jsonify(plan(_active_list(data)))
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: migration plan failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/migrate/apply", methods=["POST"])
def migrate_apply():
    """Perform the migration. Requires an explicit confirm."""
    from modules.nsot.migrate import apply as apply_migration

    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({"ok": False,
                        "error": "Review the dry-run report and confirm first."}), 400
    try:
        result = apply_migration(_active_list(data),
                                 actor=request_actor())
        # A refused re-run is a conflict, not a server error and not a success.
        # The body carries the marker, so the UI can say when it happened.
        return jsonify(result), (409 if result.get("already_migrated") else 200)
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: migration failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/renames", methods=["GET"])
def renames():
    """Renames noticed by an inventory refresh but not yet committed."""
    from modules.inventory import pending_renames
    return jsonify({"ok": True, "pending": pending_renames(_active_list())})


@bp.route("/renames/sync", methods=["POST"])
def sync_renames():
    """Apply pending renames as their own commits."""
    from modules.inventory import sync_device_names_to_repo

    data = request.get_json(silent=True) or {}
    try:
        return jsonify(sync_device_names_to_repo(_active_list(data),
                                                 actor=request_actor()))
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/legacy_store", methods=["GET"])
def legacy_store():
    """What still depends on the deprecated ``golden_configs/`` directory.

    **The retirement condition, made measurable.** "Deprecated" with no exit
    criterion never ends: the directory has been read-only since the
    migration, and until Stage 3.3 it was also the thing every reader
    enumerated. It is now consulted for exactly two purposes -- the last link
    of `_find_golden_config_file`'s resolution chain, for a device whose
    management IP changed outside NMAS, and the legacy-only entries in
    `repo.list_goldens()`.

    When ``only_legacy`` is empty for every list, both can go and so can the
    directory. That number is reported here rather than left to be
    rediscovered by whoever next wonders whether it is safe to delete.
    """
    from modules.config import get_list_data_dir
    from modules.nsot.repo import legacy_only_goldens, list_goldens

    list_name = _active_list()
    try:
        goldens = list_goldens(list_name)
        known = {e["hostname"] for e in goldens if not e["legacy"]}
        only_legacy = legacy_only_goldens(get_list_data_dir(list_name), known)
        legacy_dir = os.path.join(get_list_data_dir(list_name), "golden_configs")
        files = ([f for f in sorted(os.listdir(legacy_dir)) if f.endswith(".cfg")]
                 if os.path.isdir(legacy_dir) else [])
        return jsonify({
            "ok": True,
            "list": list_name,
            "in_repo": len(known),
            "legacy_files": len(files),
            "only_legacy": [{"hostname": e["hostname"],
                             "device_ip": e["device_ip"],
                             "file": e["file"]} for e in only_legacy],
            "retirable": not only_legacy,
        })
    except Exception as exc:                   # noqa: BLE001
        log.exception("golden: legacy store report failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
