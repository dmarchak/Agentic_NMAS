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
    intent = None if bootstrap else hostvars.hydrate_secrets(committed, hostname)

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
            hostvars.hydrate_secrets(previous, hostname),
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
                log.warning("deploy: %s refused — commands changed since "
                            "confirmation (%s -> %s)", hostname, expected, now)
                refused.append({"device": hostname, "outcome": "refused",
                                "reason": ("the device or intent changed since "
                                           "you confirmed — re-run the preview "
                                           "and confirm the new command list"),
                                "confirmed_hash": expected,
                                "current_hash": now})
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
        report.setdefault("results", []).extend(refused)
        report["refused"] = refused

    report["golden"] = _commit_batch_golden(list_name, report)
    return jsonify({"ok": True, "list": list_name, **report})


def _commit_batch_golden(list_name: str, report: dict) -> dict:
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
                                   save_golden)

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
    earned = _baseline_earned(report, pending, failed)
    subject = (f"golden: baseline {len(pending)} device(s) via pipeline "
               f"{batch_id}")
    trailers = [f"Failed-Devices: {','.join(sorted(failed))}"] if failed else []

    items = [GoldenItem(p["hostname"], p["config_text"], p["mgmt_ip"],
                        netbox_id=p["netbox_id"], device_uid=p["device_uid"])
             for p in pending]
    result = save_golden(list_name, items, source="pipeline", actor="pipeline",
                         message=subject, pipeline_id=batch_id,
                         baseline=earned["baseline"], allow_new=False,
                         extra_trailers=trailers)

    if result.get("ok"):
        repo = _os.path.join(get_list_data_dir(list_name), "config_repo")
        clear_post_deploy_staging(repo, [p["hostname"] for p in pending])
    else:
        log.error("deploy: batch golden commit failed: %s — captures remain in "
                  ".nsot/staging/post_deploy/", result.get("error"))
    return {**result, "batch_id": batch_id, "devices": succeeded,
            "failed_devices": failed, **earned}


def _baseline_earned(report: dict, pending: list, failed: list) -> dict:
    """Whether this batch produced a state worth calling a baseline.

    Measured, not categorised. ``baseline/<ts>`` asserts *the network looked
    like this*, so it is earned when three things are observably true: every
    targeted device succeeded, the whole inventory was targeted, and each
    device's post-deploy capture equals what was pushed to it. An additive
    re-apply that leaves residue on one device did not produce the baseline; an
    additive re-apply that leaves none did, and refusing the tag by category
    would understate what happened.

    Same principle as ``device_changed``: ask the artifact, do not infer from
    the kind of operation.
    """
    from modules.device import get_current_device_list, load_saved_devices
    from modules.nsot import normalize

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

    targeted = {p["hostname"] for p in pending} | set(failed)
    missing = sorted(inventory - targeted)
    if missing:
        reasons.append(f"{len(missing)} device(s) not targeted: {missing}")

    residual = []
    for item in pending:
        target = item.get("target_config")
        if target is None:
            continue          # a template deploy has no single target text
        post = normalize.strip_for_diff(item["config_text"])
        if post != normalize.strip_for_diff(target):
            residual.append(item["hostname"])
    if residual:
        reasons.append(f"{len(residual)} device(s) differ from what was pushed: "
                       f"{sorted(residual)}")

    return {"baseline": not reasons,
            "baseline_reasons": reasons or ["every targeted device matches"]}


def _deploy_one(entry, list_name: str, device_rows: dict,
                authorise: dict = None) -> dict:
    """Run the pipeline for a single device. The only path that connects."""
    import threading

    from modules.nsot.deploy import (DEPLOYED, FAILED, assert_merge_only,
                                     merge_commands, prepare_device)
    from modules.pipeline import PipelineContext, PipelineRunner

    artifact = entry["artifact"]
    hostname = artifact.device
    device = device_rows.get(hostname, {})

    try:
        prepared = prepare_device(artifact)     # refuse → real secrets → mask check
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
        return {"device": hostname, "outcome": DEPLOYED, "stage": "",
                "reason": "nothing to change", "commands": []}
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
        "golden_pending": list(result.golden_pending or []),
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
