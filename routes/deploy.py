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

from modules.identity import request_actor

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


def _captured_config(repo: str, hostname: str) -> str:
    """The device's captured golden config, resolved through the manifest.

    Manifest first, legacy listing second. The previous version discovered the
    device by scanning ``golden_configs/`` for a matching hostname and then fed
    that IP to ``_load_golden_config_file()``. So identity came from the
    deprecated store even though content came from the repo — and emptying
    ``golden_configs/``, which the migration explicitly permits, would have
    reported "no golden config for this device" for every device that has one.
    """
    from modules.nsot import manifest as _m

    entry = _m.find_by_name(repo, hostname)[1]
    if entry:
        path = _m.golden_path_for(repo, entry)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read()

    from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
    legacy = next((e for e in _list_golden_configs()
                   if e.get("hostname") == hostname), None)
    if legacy is None:
        return ""
    return _load_golden_config_file(legacy["device_ip"]) or ""


def _bound_host_vars(repo: str, template: str, platform: str, cache: dict) -> dict:
    """host_vars for **every** device bound to *template*.

    What ``binding_fingerprint()`` requires, and what the deploy path was not
    supplying. The fingerprint hashes the whole bound device set by design —
    onboarding a device must revoke approval — so a device it is not given
    hashes to the literal string ``"unknown"``. Passing only the device being
    deployed therefore produced a fingerprint that could never equal the one
    approval stored, and ``is_approved()`` returned False for every template
    bound to more than one device. Fail-closed, so nothing unsafe shipped; the
    deploy path was simply unreachable.

    Cached per request: a plan over nine devices would otherwise reparse each
    bound set once per device.
    """
    from modules.nsot import templates_repo
    from modules.nsot.render_artifact import build_artifact

    if template in cache:
        return cache[template]

    host_vars = {}
    for entry in templates_repo.devices_for_template(repo, template):
        name = entry["device"]
        captured = _captured_config(repo, name)
        if not captured:
            log.warning("deploy: %s is bound to %s but has no captured config",
                        name, template)
            continue
        host_vars[name] = build_artifact(
            name, captured, entry.get("platform") or platform,
            template=template,
            template_root=templates_repo.templates_dir(repo)).host_vars

    cache[template] = host_vars
    return host_vars


def _artifact_for(list_name: str, hostname: str, cache: dict = None):
    """Build the render artifact for one device.

    **Intent comes from committed host_vars, and from nowhere else.** Deriving
    it by parsing the device's own capture makes intent a function of current
    state, which guarantees an empty diff by construction — both sides of the
    comparison come from one source, so it cannot say anything. A device with
    no committed intent is marked ``bootstrap`` and refused, because treating
    its status quo as its goal is how a tool confidently pushes nothing and
    reports success.

    Template approval stays keyed on host_vars parsed from each bound device's
    **capture**. Approval is a statement about the template — that it faithfully
    reproduces every bound device — and editing one device's intent must not
    silently revoke it.
    """
    from modules.device import get_current_device_list, load_saved_devices
    from modules.nsot import approval, hostvars, templates_repo
    from modules.nsot.render_artifact import build_artifact

    repo = _repo_for(list_name)
    captured = _captured_config(repo, hostname)
    if not captured:
        return None, "no golden config for this device"

    _name, csv_path = get_current_device_list()
    device = next((d for d in load_saved_devices(csv_path)
                   if d.get("hostname") == hostname), {})
    from modules.nsot.platform import platform_for_device
    platform = platform_for_device(device)

    template = templates_repo.template_for_device(repo, hostname, platform)

    committed = hostvars.read_committed(repo, hostname)
    bootstrap = committed is None
    # Names become values here and only here, in memory, as late as possible.
    intent = (None if bootstrap else
              hostvars.hydrate_secrets(committed, hostname, list_name))

    bound = _bound_host_vars(repo, template, platform,
                             cache if cache is not None else {})
    approved = approval.is_approved(repo, template, bound)

    common = dict(template=template, template_approved=approved,
                  host_vars=intent, bootstrap=bootstrap,
                  template_root=templates_repo.templates_dir(repo))
    artifact = build_artifact(hostname, captured, platform, **common)

    # A standing rolled-back note blocks only while the program a fresh plan
    # would send is the one that failed. Computing it needs a rendered
    # artifact, so the artifact is built once to get the program and rebuilt
    # carrying the note — a second render on the plan path, which is not hot,
    # in exchange for a block that cannot be lifted by an unrelated edit.
    if hostvars.rolled_back_note(repo, hostname) is not None:
        note = hostvars.rolled_back_note(
            repo, hostname, _current_program(artifact, captured))
        if note is not None:
            artifact = build_artifact(hostname, captured, platform,
                                      rolled_back=note, **common)
    return (artifact, captured, device), ""


def _current_program(artifact, captured: str) -> list:
    """What a fresh plan would send, or ``[]`` if it cannot be computed."""
    from modules.nsot.deploy import merge_commands, render_for_deploy

    try:
        rendered = render_for_deploy(
            artifact.host_vars, artifact.platform,
            template_root=getattr(artifact, "template_root", "") or None,
            template_name=(artifact.template or "base.j2").split("/")[-1])
        return merge_commands(rendered, captured)
    except Exception as exc:                  # noqa: BLE001
        # Cannot tell whether this is the failed program. Keep the block:
        # an unreadable answer is not a clean bill of health.
        log.warning("deploy: could not recompute %s's program to test the "
                    "rolled-back note (%s) — keeping the block", artifact.device, exc)
        return list((artifact.rolled_back or {}).get("commands") or [])


def _attribute_additions(repo: str, hostname: str, artifact, captured: str,
                         to_add: list) -> dict:
    """Split ``to_add`` into what this intent edit explains and what it does not.

    The deploy is **merge-only**, which means it pushes every line the render
    has and the device lacks — not only the line the operator changed. If
    anyone touched the device since the capture, or an earlier intent edit was
    never deployed, those lines ride along in the same push. Merge-only is the
    right safety property and this is its cost: the change you confirm is not
    necessarily the change you made.

    Attribution is measured, not guessed: render the **previous** committed
    intent against the same capture and diff the two addition sets. Lines
    present in both were already going to be pushed before this edit existed.
    """
    from modules.nsot import hostvars, roundtrip
    from modules.nsot.deploy import merge_diff

    change = hostvars.intent_change(repo, hostname)
    result = {"intent_commit": change.get("sha", ""),
              "intent_subject": change.get("subject", ""),
              "intent_diff": change.get("diff", ""),
              "from_this_edit": list(to_add),
              "pre_existing": [],
              "attributable": True}

    previous_sha = change.get("previous_sha") or ""
    if not previous_sha:
        # First intent commit for this device: there is no earlier render to
        # compare against, so nothing can be attributed. Say so rather than
        # claiming every line is the operator's.
        result["attributable"] = not to_add
        result["from_this_edit"] = []
        result["pre_existing"] = list(to_add)
        result["note"] = ("first committed intent for this device — no earlier "
                          "render to attribute against")
        return result

    previous = hostvars.committed_at(repo, hostname, previous_sha)
    if previous is None:
        result["attributable"] = False
        result["note"] = f"could not read host_vars at {previous_sha[:8]}"
        return result

    try:
        render_kwargs = {
            "template_name": (artifact.template or "base.j2").split("/")[-1]}
        if getattr(artifact, "template_root", ""):
            render_kwargs["template_root"] = artifact.template_root
        before = roundtrip.render(
            hostvars.hydrate_secrets(previous, hostname,
                                     hostvars.list_name_for_repo(repo)),
            artifact.platform, **render_kwargs)
    except Exception as exc:                  # noqa: BLE001
        log.warning("deploy: could not render previous intent for %s: %s",
                    hostname, exc)
        result["attributable"] = False
        result["note"] = f"previous intent did not render: {exc}"
        return result

    already = set(merge_diff(before, captured)["to_add"])
    result["from_this_edit"] = [l for l in to_add if l not in already]
    result["pre_existing"] = [l for l in to_add if l in already]
    return result


@bp.route("/plan", methods=["POST"])
def plan():
    """Per-device diff and deployability. Reads captured configs only."""
    from modules.nsot.deploy import (DeployRefused, NotAuthorised,
                                     assert_authorised, command_fingerprint,
                                     dangerous_in, merge_commands, merge_diff,
                                     prepare_device)

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    hostnames = data.get("devices") or []
    # Per device, always. Authorising a line for one device must never
    # authorise it for another in the same batch.
    authorise = data.get("authorise") or {}
    if not hostnames:
        return jsonify({"ok": False, "error": "No devices selected"}), 400

    devices = []
    cache = {}
    for hostname in hostnames:
        built, error = _artifact_for(list_name, hostname, cache)
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
            # The exact program, not a description of it. What the operator
            # confirms is this list, byte for byte.
            commands = merge_commands(prepared["config"], captured)
            entry["commands"] = commands
            # Flagged HERE, so the operator sees them while deciding, rather
            # than the CI gate discovering them at stage 3 with no reachable
            # way to authorise them.
            entry["dangerous"] = dangerous_in(commands)
            authorised = [a.strip() for a in (authorise.get(hostname) or [])]
            entry["authorised"] = authorised
            entry["command_hash"] = command_fingerprint(commands, authorised)
            if entry["dangerous"]:
                try:
                    assert_authorised(commands, authorised)
                    entry["authorisation_ok"] = True
                except NotAuthorised as exc:
                    entry["authorisation_ok"] = False
                    entry["authorisation_error"] = str(exc)
            # Every pushed line, attributed — before anyone confirms.
            entry["attribution"] = _attribute_additions(
                _repo_for(list_name), hostname, artifact, captured,
                diff["to_add"])
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
    from modules.nsot.deploy import (CircuitBreaker, NotAuthorised,
                                     assert_authorised, command_fingerprint,
                                     merge_commands, plan_batch, prepare_device,
                                     run_batch)

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    confirmations = data.get("confirmations") or {}
    if not confirmations:
        return jsonify({"ok": False,
                        "error": "Nothing confirmed — deploy refused"}), 400

    # One-shot discipline, the same shape as the Phase 0 plan token: the
    # operator confirmed one exact command list, so that exact list is what
    # may be sent. Recomputed here and compared, never trusted from the
    # request — a hash the client supplies proves only what the client saw.
    command_hashes = data.get("command_hashes") or {}
    authorise = data.get("authorise") or {}

    artifacts, fresh_captures, device_rows = [], {}, {}
    refused = []
    cache = {}
    for hostname in confirmations:
        built, error = _artifact_for(list_name, hostname, cache)
        if built is None:
            log.warning("deploy: %s unavailable: %s", hostname, error)
            continue
        artifact, captured, device = built

        expected = command_hashes.get(hostname)
        if expected is not None:
            try:
                recomputed = merge_commands(
                    prepare_device(artifact)["config"], captured)
                device_auth = [a.strip() for a in (authorise.get(hostname) or [])]
                assert_authorised(recomputed, device_auth)
                now = command_fingerprint(recomputed, device_auth)
            except NotAuthorised as exc:
                refused.append({"device": hostname, "outcome": "refused",
                                "reason": str(exc)})
                continue
            except Exception as exc:          # noqa: BLE001
                refused.append({"device": hostname, "outcome": "refused",
                                "reason": f"could not recompute commands: {exc}"})
                continue
            if now != expected:
                # WHICH SIDE MOVED, not just that something did.
                #
                # The capture hash is already in hand — it is what
                # `confirmations` carries — so comparing it separates the two
                # causes at no cost. "The device or intent changed" makes the
                # reader check both; naming the one that moved makes it one
                # place to look.
                #
                # This refusal is also NEW BEHAVIOUR on a path that used to
                # succeed: the wizard never sent `command_hashes`, so the
                # recompute never ran and a plan left open while the device
                # moved was applied against a program nobody had seen. The
                # message says so, because the first time somebody meets a
                # guard that was not there yesterday it reads as a
                # malfunction.
                capture_now = _capture_hash(captured)
                capture_confirmed = confirmations.get(hostname)
                if capture_confirmed and capture_now != capture_confirmed:
                    moved = ("the device's captured config has changed since "
                             f"you planned ({capture_confirmed} -> "
                             f"{capture_now})")
                else:
                    moved = ("the device's captured config is unchanged, so "
                             "the difference is in the intent or the template "
                             "— a host_vars commit or a template edit landed "
                             "between your plan and this apply")
                log.warning("deploy: %s refused — commands changed since "
                            "confirmation (%s -> %s)", hostname, expected, now)
                refused.append({
                    "device": hostname, "outcome": "refused",
                    "reason": (
                        f"the exact command list changed since you confirmed "
                        f"it ({expected} -> {now}): {moved}. Nothing was sent. "
                        "Re-run the preview and confirm the new list — what "
                        "you confirm is what is sent, so a list you have not "
                        "read is never deployed."),
                    "confirmed_hash": expected,
                    "current_hash": now,
                    "capture_confirmed": capture_confirmed,
                    "capture_current": capture_now,
                    "moved": ("capture" if capture_confirmed
                              and capture_now != capture_confirmed
                              else "intent_or_template")})
                continue

        artifacts.append(artifact)
        device_rows[hostname] = device
        # Phase 3c reads a FRESH capture inside the pipeline (stage 4). Here the
        # comparison is against the same captured artifact the plan used, so a
        # change committed between plan and apply is caught before connecting.
        fresh_captures[hostname] = captured

    batch = plan_batch(artifacts, confirmations, fresh_captures)

    report = run_batch(batch,
                       lambda entry: _deploy_one(entry, list_name, device_rows,
                                                 authorise),
                       CircuitBreaker())
    if refused:
        _merge_refusals(report, refused)

    report["golden"] = _commit_batch_golden(list_name, report)
    return jsonify({"ok": True, "list": list_name, **report})


def _merge_refusals(report: dict, refused: list) -> None:
    """Fold pre-batch refusals into the report, **and re-derive its totals**.

    A device refused before `plan_batch()` never entered the batch, so
    `run_batch()` could not count it. Extending `results` alone left `total`
    at the batch's own figure while the table showed more rows — measured:
    one refusal rendered as *"0 device(s) accounted for. Every device in a
    batch appears here."* beside a row for that device.

    **A count that contradicts the rows beneath it, in a sentence claiming
    completeness**, is the exact shape this project treats as serious: not a
    stale number, a false statement of coverage. `by_outcome` needs the same
    treatment or the summary badge disagrees with the table too.
    """
    report.setdefault("results", []).extend(refused)
    report["refused"] = refused
    report["results"].sort(key=lambda r: r.get("device", ""))

    by_outcome = {}
    for result in report["results"]:
        by_outcome.setdefault(result["outcome"], []).append(result["device"])
    report["by_outcome"] = by_outcome
    report["deployed"] = by_outcome.get("deployed", [])
    report["total"] = len(report["results"])


def run_targets(list_name: str, targets: list, data: dict,
                label: str = "", source_ref: str = "") -> dict:
    """Run a batch of already-built targets. Shared by deploy and re-apply.

    Everything below the intent layer is the same operation whether the target
    came from rendering committed intent or from reading a stored config: the
    confirm hash, the authorisation, the circuit breaker, sequential
    execution, failure capture, rollback and the single golden commit. Only
    *what to send* differs, and that was decided before this is called.
    """
    from modules.nsot.deploy import (CircuitBreaker, NotAuthorised,
                                     assert_authorised, command_fingerprint,
                                     merge_commands, plan_batch,
                                     prepare_for_deploy, run_batch)

    confirmations = data.get("confirmations") or {}
    command_hashes = data.get("command_hashes") or {}
    authorise = data.get("authorise") or {}

    accepted, fresh_captures, device_rows, refused = [], {}, {}, []
    for target in targets:
        hostname = target.device
        if hostname not in confirmations:
            refused.append({"device": hostname, "outcome": "refused",
                            "reason": "not confirmed"})
            continue

        captured = getattr(target, "captured", "")
        expected = command_hashes.get(hostname)
        if expected is not None:
            try:
                recomputed = merge_commands(
                    prepare_for_deploy(target)["config"], captured)
                device_auth = [a.strip() for a in (authorise.get(hostname) or [])]
                assert_authorised(recomputed, device_auth)
                now = command_fingerprint(recomputed, device_auth)
            except NotAuthorised as exc:
                refused.append({"device": hostname, "outcome": "refused",
                                "reason": str(exc)})
                continue
            except Exception as exc:          # noqa: BLE001
                refused.append({"device": hostname, "outcome": "refused",
                                "reason": f"could not recompute commands: {exc}"})
                continue
            if now != expected:
                refused.append({"device": hostname, "outcome": "refused",
                                "reason": ("the device changed since you "
                                           "confirmed — re-run the preview and "
                                           "confirm the new command list"),
                                "confirmed_hash": expected,
                                "current_hash": now})
                continue

        accepted.append(target)
        device_rows[hostname] = getattr(target, "device_row", {}) or {}
        fresh_captures[hostname] = captured

    batch = plan_batch(accepted, confirmations, fresh_captures)
    report = run_batch(batch,
                       lambda entry: _deploy_one(entry, list_name, device_rows,
                                                 authorise, source_ref),
                       CircuitBreaker())
    if refused:
        # Same helper as the deploy path: the restore path merged refusals the
        # same way and had the same disagreement between its count and its
        # rows. Two copies of a fold is how they come to differ.
        _merge_refusals(report, refused)
    report["golden"] = _commit_batch_golden(list_name, report, label=label,
                                            source_ref=source_ref)
    return report


def _measure_unchanged(list_name: str, device: dict, hostname: str,
                       target_config: str) -> list:
    """Read a device that needs no changes, so its state is measured.

    Returns a ``golden_pending`` entry shaped exactly like the one stage 8.5
    produces, or ``[]`` if the read fails. A failed read is not a failed
    deploy — nothing was sent — but it does mean this device contributes no
    measurement, and :func:`_baseline_earned` then declines the tag rather than
    assuming.

    The capture is staged the same way stage 8.5 stages its own, so a crash
    between here and the batch commit does not lose it.
    """
    import os as _os

    from modules.config import get_list_data_dir
    from modules.connection import with_temp_connection
    from modules.nsot import manifest as _manifest
    from modules.nsot.repo import stage_post_deploy
    from modules.settings_schema import get_setting

    ip = device.get("ip", "")
    try:
        timeout = get_setting("nsot_config_read_timeout", 120)
        config = with_temp_connection(
            device, lambda c: c.send_command("show running-config",
                                             read_timeout=timeout))
    except Exception as exc:                    # noqa: BLE001
        log.warning("deploy: %s needed no changes but could not be read back "
                    "(%s) — it contributes no measurement", hostname, exc)
        return []
    if not config:
        return []

    repo = _os.path.join(get_list_data_dir(list_name), "config_repo")
    netbox_id = device.get("_netbox_id")
    device_uid = device.get("device_uid", "")
    if not _manifest.identity_for(netbox_id, device_uid):
        existing, _entry = _manifest.find_by_ip(repo, ip)
        if not existing:
            existing, _entry = _manifest.find_by_name(repo, hostname)
        if existing and existing.startswith("uid:"):
            device_uid = existing.split(":", 1)[1]
        elif existing and existing.startswith("nb:"):
            netbox_id = existing.split(":", 1)[1]

    stage_post_deploy(repo, hostname, config)
    return [{"hostname": hostname, "config_text": config, "mgmt_ip": ip,
             "netbox_id": netbox_id, "device_uid": device_uid,
             "target_config": target_config, "sent_nothing": True}]


def _deploy_one(entry, list_name: str, device_rows: dict,
                authorise: dict = None, source_ref: str = "") -> dict:
    """Run the pipeline for a single device. The only path that connects."""
    import threading

    from modules.nsot.deploy import (DEPLOYED, FAILED, assert_merge_only,
                                     merge_commands, prepare_for_deploy)
    from modules.pipeline import PipelineContext, PipelineRunner

    artifact = entry["artifact"]
    hostname = artifact.device
    device = device_rows.get(hostname, {})

    try:
        prepared = prepare_for_deploy(artifact)  # refuse → resolve → mask check
    except Exception as exc:                    # noqa: BLE001
        return {"device": hostname, "outcome": FAILED, "stage": "prepare",
                "reason": str(exc)}

    # The merge diff in sendable form — NOT the whole rendered config. Pushing
    # the full render made assert_merge_only() vacuous (to_push was the
    # intended config, so it could not fail) and meant the operator confirmed
    # one line while 83 were sent.
    captured = entry.get("fresh") or ""
    commands = merge_commands(prepared["config"], captured)
    if not commands:
        # Nothing to send — but "nothing to send" was decided against a STORED
        # capture, which is a record of the device at some earlier moment. A
        # baseline tag is a claim about the device now, so the device is read
        # once here and the capture handed to the batch like any other. Without
        # it this device is *inferred* to match and contributes no measurement,
        # which is the distinction the tag rule turns on.
        return {"device": hostname, "outcome": DEPLOYED, "stage": "",
                "reason": "nothing to change", "commands": [],
                "ref_intent": getattr(artifact, "ref_intent", None),
                "ref_intent_text": getattr(artifact, "ref_intent_text", ""),
                "un_onboard": getattr(artifact, "un_onboard", False),
                "device_changed": False,
                "golden_pending": _measure_unchanged(
                    list_name, device, hostname, prepared["config"])}
    try:
        assert_merge_only(commands, prepared["config"])
    except Exception as exc:                    # noqa: BLE001
        return {"device": hostname, "outcome": FAILED, "stage": "merge-only",
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
        # Carried, never re-derived. The pipeline must not ask a global which
        # network it is writing to: a list switch during a 45-90s convergence
        # window would land this device's golden in another list's repository.
        list_name=list_name,
    )
    # Scoped to THIS device. The batch's other devices get their own list.
    authorised = [a.strip() for a in ((authorise or {}).get(hostname) or [])]
    ctx.params["allowed_dangerous"] = authorised
    # Confirmed, not merely pre-populated: rendered_commands derives from this,
    # so stage 2 cannot overwrite it and an attempt to do so raises.
    ctx.confirmed_commands = {device.get("ip", ""): commands}
    # The batch commits; this device hands its capture back.
    ctx.defer_golden = True

    try:
        result = PipelineRunner(ctx).run()
    except Exception as exc:                    # noqa: BLE001
        log.exception("deploy: pipeline raised for %s", hostname)
        return {"device": hostname, "outcome": FAILED, "stage": "pipeline",
                "reason": str(exc)}

    failed_stage = result.stages_failed[-1] if result.stages_failed else ""
    # What actually landed. A failed push does not mean an unchanged device.
    failure_state = list((result.failure_state or {}).values())
    outcome = DEPLOYED if result.final_status == "success" else FAILED
    return {
        "device": hostname,
        "outcome": outcome,
        "commands": commands,
        "failure_state": failure_state,
        "authorised": authorised,
        # Carried so the batch commit knows whether this device's intent is
        # part of this event, and whether the operator asked to un-onboard it.
        "ref_intent": getattr(artifact, "ref_intent", None),
        "ref_intent_text": getattr(artifact, "ref_intent_text", ""),
        "un_onboard": getattr(artifact, "un_onboard", False),
        # The target text, so the batch can MEASURE whether the post-deploy
        # capture equals what was pushed — which is what earns baseline/<ts>.
        "golden_pending": [{**p, "target_config": prepared["config"]}
                           for p in (result.golden_pending or [])],
        "rollback_commands": list(
            (result.rollback_commands or {}).get(device.get("ip", ""), [])),
        "rollback_failures": dict(result.rollback_failures or {}),
        "rollback_not_undone": list(
            (result.rollback_not_undone or {}).get(device.get("ip", ""), [])),
        "rollback_dangerous_exempt": list(
            (result.rollback_dangerous or {}).get(device.get("ip", ""), [])),
        "device_changed": any(e.get("device_changed") for e in failure_state),
        "stage": failed_stage,
        "reason": result.error or "",
        "rolled_back": result.rollback_performed,
        "pending_convergence": list(result.pending_convergence),
        "golden_commit": (result.golden_result or {}).get("commit", ""),
        "golden_skipped": list(result.golden_skipped),
        "warnings": list(result.warnings),
    }


def _write_restored_intent(list_name: str, report: dict,
                           source_ref: str) -> dict:
    """Put the ref's committed intent back, for devices that succeeded.

    **A forward commit, not a rewind.** The ref's ``host_vars`` are written
    into the working tree as today's intent and committed with the batch; the
    history in between is untouched and the previous intent stays reachable by
    ``git log`` on the file. Nothing is reset, reverted or force-pushed.

    **Device and intent move together or not at all.** Only devices whose
    restore succeeded get their intent written, because a device still at its
    drifted state with the ref's intent committed is the same fight-itself
    state in the other direction.

    **Un-onboarding is opt-in and still a forward commit.** A device the ref
    predates has no intent to restore; removing today's is a deletion of
    reviewed work, so it happens only when the operator ticked it, and the
    file is removed by a commit rather than by rewriting history — recoverable
    from git history.

    Returns ``{"restored": [...], "un_onboarded": [...], "skipped": [...]}``.
    """
    import os as _os

    from modules.config import get_list_data_dir
    from modules.nsot import hostvars
    from modules.nsot.deploy import DEPLOYED
    from modules.nsot.repo import stage_restored_intent

    repo = _os.path.join(get_list_data_dir(list_name), "config_repo")
    restored, un_onboarded, skipped = [], [], []

    for entry in report.get("results") or []:
        device = entry.get("device", "")
        text = entry.get("ref_intent_text") or ""
        if entry.get("outcome") != DEPLOYED:
            if text or entry.get("un_onboard"):
                skipped.append({"device": device,
                                "reason": "the device did not reach the ref, "
                                          "so its intent is left alone"})
            continue

        if entry.get("un_onboard"):
            path = hostvars.committed_path(repo, device)
            if _os.path.exists(path):
                _os.remove(path)
                un_onboarded.append(device)
            continue

        if not text:
            continue
        # Staged first: between here and the batch commit the device is at the
        # ref and the committed intent is not, and a crash in that window is
        # exactly the state this pairing exists to prevent.
        stage_restored_intent(repo, device, text)
        hostvars.write_committed_text(repo, device, text)
        restored.append(device)

    if restored or un_onboarded:
        log.info("restore: intent restored for %s%s", sorted(restored),
                 f", un-onboarded {sorted(un_onboarded)}" if un_onboarded else "")
    return {"restored": sorted(restored), "un_onboarded": sorted(un_onboarded),
            "skipped": skipped, "ref": source_ref}


def _commit_batch_golden(list_name: str, report: dict, label: str = "",
                         source_ref: str = "") -> dict:
    """One commit for the batch, naming exactly the devices that succeeded.

    A batch is an event, and the record should say so. Three per-device commits
    are not wrong — each is truthful — but they leave no single reference for
    "the network after this batch", because ``baseline/<ts>`` only appeared
    when one call changed more than one device. Collecting here means the
    baseline exists for any completed batch, including a single-device one.

    The subject and trailers name the **successful subset** and the failures
    alongside it, so a partial batch is legible from the commit rather than
    only from a report someone has to still be holding.
    """
    import os as _os

    from modules.config import get_list_data_dir
    from modules.nsot.deploy import DEPLOYED
    from modules.nsot.repo import (GoldenItem, clear_post_deploy_staging,
                                   clear_restored_intent_staging, save_golden)

    results = report.get("results") or []
    pending, succeeded, failed = [], [], []
    for entry in results:
        device = entry.get("device", "")
        if entry.get("outcome") == DEPLOYED:
            succeeded.append(device)
            pending.extend(entry.pop("golden_pending", []) or [])
        else:
            failed.append(device)
            entry.pop("golden_pending", None)

    if not pending:
        # Every device failed, or none had a capture. No empty commit, and no
        # baseline tag — there is no post-batch state worth pointing at.
        log.info("deploy: no successful captures to record for this batch")
        return {"ok": True, "commit": "", "devices": [], "skipped": failed,
                "reason": "no device completed successfully"}

    batch_id = f"batch-{report.get('batch_id') or _os.urandom(3).hex()}"
    earned = _baseline_earned(report, pending, failed, source_ref=source_ref)
    what = label or f"via pipeline {batch_id}"
    subject = f"golden: baseline {len(pending)} device(s) {what}"
    trailers = [f"Failed-Devices: {','.join(sorted(failed))}"] if failed else []

    # Device and intent are ONE UNIT per device, so the restored intent is part
    # of this commit, not a second one after it. A restore path names
    # ``host_vars`` explicitly; a template deploy does not, and so can never
    # carry intent into a commit by accident.
    intent, extra_paths = {}, None
    if source_ref:
        intent = _write_restored_intent(list_name, report, source_ref)
        if intent["restored"] or intent["un_onboarded"]:
            extra_paths = ["host_vars"]
            trailers.append(f"Restored-Intent: {','.join(intent['restored'])}")
            if intent["un_onboarded"]:
                trailers.append(
                    f"Un-Onboarded: {','.join(intent['un_onboarded'])}")

    items = [GoldenItem(p["hostname"], p["config_text"], p["mgmt_ip"],
                        netbox_id=p["netbox_id"], device_uid=p["device_uid"])
             for p in pending]
    result = save_golden(list_name, items, source="pipeline", actor=request_actor(),
                         message=subject, pipeline_id=batch_id,
                         baseline=earned["baseline"], allow_new=False,
                         extra_trailers=trailers, extra_paths=extra_paths)

    repo = _os.path.join(get_list_data_dir(list_name), "config_repo")
    if result.get("ok"):
        clear_post_deploy_staging(repo, [p["hostname"] for p in pending])
        if intent:
            clear_restored_intent_staging(
                repo, intent["restored"] + intent["un_onboarded"])
    else:
        log.error("deploy: batch golden commit failed: %s — captures remain in "
                  ".nsot/staging/post_deploy/%s", result.get("error"),
                  " and restored intent in .nsot/staging/restored_intent/"
                  if intent else "")
    return {**result, "batch_id": batch_id, "devices": succeeded,
            "failed_devices": failed, "intent": intent, **earned}


def _baseline_earned(report: dict, pending: list, failed: list,
                     source_ref: str = "") -> dict:
    """Whether this batch produced a state worth calling a baseline.

    **Each path's baseline is keyed on the claim its tag makes**, which are not
    the same claim:

    * A **deploy** baseline says *this commit's goldens are the network*. The
      goldens in that commit ARE the post-deploy captures, so for devices that
      succeeded it is true by construction. What remains is coverage: every
      targeted device succeeded, and the whole inventory was targeted.
    * A **restore** baseline says *the network is back to the ref's state*.
      That is a claim about content, so it is measured: **every inventory
      device measured equivalent to the ref, whatever path got it there.**
      Pushed, already matching, or needing one line — the tag does not care
      how a device arrived, only that this batch read it back and compared it.

    A device is *measured* only if this batch produced a live capture for it.
    That is why a device with nothing to send is still read (see
    :func:`_measure_unchanged`): "no commands" was decided against a stored
    capture, and a stored capture is a record of an earlier moment, not
    evidence about now. A device skipped at plan time — stale, unconfirmed, no
    golden or no usable intent at the ref — produced no measurement, so it
    blocks the tag rather than being assumed fine.

    Note that residue keeps a restore from earning ``baseline/``, and should:
    merge-only cannot remove it, so the network is demonstrably *not* back to
    the ref. That is the whole point of measuring instead of asserting.

    An earlier version measured content on both paths and compared a *rendered
    template* against a device. A render is a statement of intent, not a whole
    config, so every unmodelled construct read as a difference and a whole-fleet
    template deploy would have been denied a baseline it had earned. Substituting
    ``template_report`` would have been the adjacent-question mistake in the
    other direction: it answers whether the template reproduces the device, not
    whether the commit is the network.
    """
    from modules.device import get_current_device_list, load_saved_devices

    reasons = []
    if failed:
        reasons.append(f"{len(failed)} device(s) did not succeed: {sorted(failed)}")

    try:
        _name, csv_path = get_current_device_list()
        inventory = {d.get("hostname", "") for d in load_saved_devices(csv_path)}
    except Exception as exc:                  # noqa: BLE001
        log.warning("deploy: could not read the inventory to judge baseline "
                    "eligibility (%s)", exc)
        return {"baseline": False, "baseline_reasons": ["inventory unreadable"]}

    measured = {p["hostname"] for p in pending}
    targeted = measured | set(failed)
    missing = sorted(inventory - targeted)
    if missing:
        reasons.append(f"{len(missing)} device(s) not targeted: {missing}")

    if not source_ref:
        return {"baseline": not reasons, "measured": sorted(measured),
                "baseline_reasons": reasons or ["every inventory device is in "
                                                "this commit"]}

    # Restore only: the tag claims the network matches the ref, so every
    # inventory device has to have been read back and compared.
    from modules.nsot import roundtrip

    unmeasured = sorted(inventory - measured)
    if unmeasured:
        reasons.append(f"{len(unmeasured)} device(s) were not measured against "
                       f"{source_ref}: {unmeasured}")

    residual = []
    for item in pending:
        target = item.get("target_config")
        if target is None:
            # No target to compare against is not a pass. It is the absence of
            # the measurement the tag is named for.
            residual.append({"device": item["hostname"],
                             "still_differs": ["no reference config to "
                                               "compare against"]})
            continue
        outcome = roundtrip.configs_equivalent(item["config_text"], target)
        if not outcome["equal"]:
            residual.append({
                "device": item["hostname"],
                "still_differs": (outcome["only_left"][:3]
                                  + outcome["only_right"][:3]),
            })
    if residual:
        reasons.append(f"{len(residual)} device(s) do not match {source_ref}: "
                       + ", ".join(r["device"] for r in residual))

    return {"baseline": not reasons, "measured": sorted(measured),
            "residual": residual,
            "baseline_reasons": reasons or [
                f"every inventory device measured equivalent to {source_ref}"]}
