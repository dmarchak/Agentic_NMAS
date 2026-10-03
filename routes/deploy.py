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
    return _captured_record(repo, hostname)["text"] or ""


def _captured_record(repo: str, hostname: str) -> dict:
    """The device's golden AS COMMITTED (C104), with why not: ``text`` None
    and ``refused`` naming the path when a golden exists and is refused. The
    deploy plan diffs against this and binds its capture hash to it, so it
    read the working file until the second pass of C104's fix."""
    from modules.nsot import manifest as _m
    from modules.nsot.repo import committed_golden_for

    entry = _m.find_by_name(repo, hostname)[1]
    record = committed_golden_for(repo, entry)
    if record["text"] is not None or record["refused"]:
        return record

    from modules.ai_assistant import _golden_record, _list_golden_configs
    legacy = next((e for e in _list_golden_configs()
                   if e.get("hostname") == hostname), None)
    if legacy is None:
        return record
    return _golden_record(legacy["device_ip"])


def _artifact_for(list_name: str, hostname: str):
    """Build the render artifact for one device.

    **Intent comes from committed host_vars, and from nowhere else.** Deriving
    it by parsing the device's own capture makes intent a function of current
    state, which guarantees an empty diff by construction — both sides of the
    comparison come from one source, so it cannot say anything. A device with
    no committed intent is marked ``bootstrap`` and refused, because treating
    its status quo as its goal is how a tool confidently pushes nothing and
    reports success.

    Template approval is a statement about the TEMPLATE (scheme 3, P.5): its
    closure hash. Whether this device is reproduced faithfully is this plan's
    own ``template_report``, which gates here, per device, with the lines
    named; editing one device's intent cannot revoke the template.
    """
    from modules.nsot import approval, hostvars, templates_repo
    from modules.nsot.render_artifact import build_artifact

    repo = _repo_for(list_name)
    record = _captured_record(repo, hostname)
    captured = record["text"] or ""
    if not captured:
        # A refused golden is not "no golden": saying so would send the
        # reader to save one that is already there.
        return None, (f"golden refused: {record['refused']}" if record["refused"]
                      else "no golden config for this device")

    # The row comes from THIS list's inventory (C215): it came from the ACTIVE
    # list's, so a plan for list B read list A's row, and a device with no row
    # there took `platform_for_device({})`, measured as `cisco_ios`: the plan
    # chose the IOS template for an IOS-XE device. A device the list does not
    # hold is refused by name; a lookup that misses never picks a default.
    from modules.nsot.restore import _devices_of
    device = next((d for d in _devices_of(list_name) if d.get("hostname") == hostname), None)
    if device is None:
        return None, (f"{hostname} is not in {list_name}'s inventory, so its platform, and "
                      "the template to render it with, are unknown")
    from modules.nsot.platform import platform_for_device
    platform = platform_for_device(device)

    # The one resolver (C239): the bound template in the network's library.
    source = templates_repo.render_source(repo, hostname, platform)
    template = source["template"]

    committed = hostvars.read_committed(repo, hostname)
    # A committed intent that is only onboarding's bootstrap is bootstrap too,
    # refused with its reason, never rendered (C154: it raised in the template).
    seed_only = committed is not None and hostvars.is_bootstrap_only(committed)
    bootstrap = committed is None or seed_only
    # THE NETWORK'S MONITORING PROFILE (P.9), inherited through the one
    # merge. A profile that cannot be read refuses the plan by name: rendering
    # without it would plan to leave the device without what every device
    # inherits, and look like a clean plan.
    from modules.nsot import profile as _profile
    try:
        effective = (None if bootstrap else
                     _profile.effective_for(repo, list_name, hostname, committed, platform,
                                            role=(device.get("role") or "").strip()))
    except _profile.ProfileRefused as exc:
        return None, f"the network's monitoring profile cannot be used: {exc}"
    # Names become values here and only here, in memory, as late as possible.
    intent = (None if bootstrap else
              hostvars.hydrate_secrets(effective, hostname, list_name))

    # Scheme 3 (P.5): approval is the template's closure hash alone, so no
    # bound device's host_vars are needed here. Building them was a full
    # render of EVERY device bound to the template on every plan, for a
    # fingerprint that no longer reads them.
    approved = approval.is_approved(repo, template)

    common = dict(template=template, template_approved=approved,
                  host_vars=intent, bootstrap=bootstrap,
                  bootstrap_reason=hostvars.BOOTSTRAP_ONLY_REASON if seed_only else "",
                  template_root=source["root"])
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
    from modules.nsot.deploy import render_for_deploy

    try:
        rendered = render_for_deploy(
            artifact.host_vars, artifact.platform,
            template_root=getattr(artifact, "template_root", "") or None,
            template_name=(artifact.template or "base.j2").split("/")[-1])
        # The program a plan sends, re-creates included (with no removal
        # selected): a rolled-back re-create is recorded as its program, and
        # merge_commands alone would never contain it, lifting its own block.
        full = _program(rendered, captured, [], None, getattr(artifact, "platform", ""))
        return list(full["commands"])
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
        return _split_profile(repo, hostname, artifact, captured, to_add, result)

    previous = hostvars.committed_at(repo, hostname, previous_sha)
    if previous is None:
        result["attributable"] = False
        result["note"] = f"could not read host_vars at {previous_sha[:8]}"
        return _split_profile(repo, hostname, artifact, captured, to_add, result)

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
        return _split_profile(repo, hostname, artifact, captured, to_add, result)

    already = set(merge_diff(before, captured)["to_add"])
    result["from_this_edit"] = [l for l in to_add if l not in already]
    result["pre_existing"] = [l for l in to_add if l in already]
    return _split_profile(repo, hostname, artifact, captured, to_add, result)


def _split_profile(repo: str, hostname: str, artifact, captured: str, to_add: list,
                   result: dict) -> dict:
    """``from_profile``: the lines sent only because the network's monitoring
    profile (P.9) supplies them, measured as the lines the device's OWN
    intent, rendered alone, would not send. They leave the other two groups,
    so no inherited line is ever called "from this edit". No profile, or
    none that applies, is ``[]``."""
    from modules.nsot import hostvars, profile as _profile, roundtrip
    from modules.nsot.deploy import merge_diff

    result["from_profile"] = []
    try:
        doc = _profile.read_committed(repo)
        list_name = hostvars.list_name_for_repo(repo)
        own = hostvars.read_committed(repo, hostname)
        if not doc or own is None:
            return result
        if _profile.effective_for(repo, list_name, hostname, own, artifact.platform, doc=doc) == own:
            return result
        render_kwargs = {"template_name": (artifact.template or "base.j2").split("/")[-1]}
        if getattr(artifact, "template_root", ""):
            render_kwargs["template_root"] = artifact.template_root
        alone = roundtrip.render(hostvars.hydrate_secrets(own, hostname, list_name),
                                 artifact.platform, **render_kwargs)
    except Exception as exc:                  # noqa: BLE001
        log.warning("deploy: the profile's lines could not be told apart for %s: %s",
                    hostname, exc)
        result["note"] = ((result.get("note") + "; ") if result.get("note") else "") + \
            f"the profile's lines could not be told apart: {exc}"
        return result
    own_add = set(merge_diff(alone, captured)["to_add"])
    inherited = [l for l in to_add if l not in own_add]
    result["from_profile"] = inherited
    result["from_this_edit"] = [l for l in result["from_this_edit"] if l not in inherited]
    result["pre_existing"] = [l for l in result["pre_existing"] if l not in inherited]
    return result


#: The deploy scopes: the device's whole intent (""), the monitoring
#: profile's lines (P.9 b), or only its IP SLA probes (P.9 d4's add path).
SCOPES = ("", "profile", "ip_sla")


def _scoped(scope: str, list_name: str, hostname: str, artifact, intended: str, captured: str,
            device: dict) -> dict:
    """The intended config scoped by *scope*, with the groups a person reads.
    ONE dispatch for the plan, the apply's recompute and the path that
    connects."""
    from modules.nsot import ip_sla_policy
    if scope == ip_sla_policy.SCOPE:
        return ip_sla_policy.scoped(intended, captured, "the device's own intent (its IP SLA probes)")
    return _profile_scope(list_name, hostname, artifact, intended, captured, device)


def _profile_scope(list_name: str, hostname: str, artifact, intended: str, captured: str,
                   device: dict) -> dict:
    """APPLY MONITORING PROFILE (P.9 step b): the intended config scoped to
    the network's profile, and the groups a person reads. Computed from the
    truthful renders at plan, at apply and on the path that connects; never
    from anything the browser sends. Raises `ScopeRefused` (or
    `ProfileRefused` for a profile that cannot be read), naming why."""
    from modules.nsot import hostvars, profile as _profile, profile_apply
    from modules.nsot.deploy import render_for_deploy

    repo = _repo_for(list_name)
    doc = _profile.read_committed(repo)
    if not doc:
        raise profile_apply.ScopeRefused(
            f"{list_name} has no committed monitoring profile, so there is nothing to apply: "
            "propose the network's profile first")
    own = hostvars.read_committed(repo, hostname)
    if own is None:
        raise profile_apply.ScopeRefused(f"{hostname} has no committed intent")
    role = ((device or {}).get("role") or "").strip()
    sections = _profile.sections_for(doc, artifact.platform, role, own)
    if not sections:
        excluded = _profile.excluded(own)
        raise profile_apply.ScopeRefused(
            f"no section of {list_name}'s monitoring profile applies to {hostname} "
            f"(platform {artifact.platform}, role {role or 'none'}"
            + (f"; its intent excludes {', '.join(sorted(excluded))}" if excluded else "") + ")")
    root = getattr(artifact, "template_root", "") or None
    name = (artifact.template or "base.j2").split("/")[-1]

    def render(intent):
        return render_for_deploy(hostvars.hydrate_secrets(intent, hostname, list_name),
                                 artifact.platform, template_root=root, template_name=name)

    own_render = render(own)
    out = profile_apply.scoped(intended, own_render, captured)

    def render_with(secs):
        one = {"version": doc.get("version"),
               "sections": {k: doc["sections"][k] for k in secs}}
        return render(_profile.effective(own, one, artifact.platform, role))

    out["by_section"] = {k: [{"chain": list(c), "line": l} for c, l in rows]
                         for k, rows in profile_apply.by_section(sections, render_with,
                                                                 own_render).items()}
    out["sources"] = {k: (doc["sections"][k].get("source") or "") for k in sections}
    return out


def plan_devices(list_name: str, hostnames: list, *, authorise: dict = None,
                 remove: dict = None, scope: str = "") -> list:
    """Every device's plan entry: its exact program, hashes, gates and what it
    holds back. THE plan, for `/deploy/plan` and the v2 batch preview (P.9 d2)
    alike. Reads captured configs only; contacts no device."""
    from modules.nsot.deploy import (DeployRefused, NotAuthorised,
                                     assert_authorised, command_fingerprint,
                                     dangerous_in, merge_diff,
                                     prepare_device, residue_in_context)
    from modules.nsot import profile as _profile, profile_apply

    authorise = authorise or {}
    remove = remove or {}
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
        selected = remove.get(hostname) or []

        try:
            prepared = prepare_device(artifact)
            diff = merge_diff(prepared["config"], captured)
            entry["to_add"] = diff["to_add"]
            entry["removal_warnings"] = diff["removal_warnings"]
            # The same residue as a person reads it: each line under its
            # section, since a leaf alone names no interface.
            entry["residue_in_context"] = residue_in_context(
                diff["removal_warnings"], captured)
            entry["unchanged_count"] = diff["unchanged_count"]
            # Lines left on the device that a shared setting key hides from the
            # residue (C201): named, never offered for removal.
            entry["shares_key"] = diff["shares_key"]
            # Scoped to the profile, the program is built from the scoped
            # intended config: the profile's missing lines and nothing else.
            intended = prepared["config"]
            if scope:
                sc = _scoped(scope, list_name, hostname, artifact, intended, captured, _device)
                intended = sc.pop("config")
                entry["scope"] = scope
                entry["profile_scope"] = sc
            # The exact program, not a description of it. What the operator
            # confirms is this list, byte for byte.
            full = _program(intended, captured, selected, _device,
                            entry.get("platform", ""))
            commands = full["commands"]
            entry["commands"] = commands
            entry["removals"] = {k: full[k] for k in
                                 ("removed", "refused", "secret_position",
                                  "removal_commands", "keys", "ids")}
            # Every line the device has and intent lacks, each with its ID and
            # (where it cannot be removed) why: what the screen ticks, by ID.
            from modules.nsot.removal import removable
            entry["removable"] = removable(
                prepared["config"], captured, mgmt_ip=(_device or {}).get("ip", ""),
                dialect=entry.get("platform", ""))
            if scope == profile_apply.SCOPE:
                # The device's lines of the same measured kind as the
                # profile's: superseded, offered for removal, never removed
                # unless ticked (MONITORING_PROFILE.md 5).
                sc = entry["profile_scope"]
                sc["superseded"] = profile_apply.superseded(
                    sc["to_send"] + sc["in_place"], entry["removable"])
            # A running IP SLA operation intent changes: re-created (deleted,
            # defined from intent, rescheduled), drawn with what it replaces,
            # or refused with why; a refused one blocks the device, since the
            # in-place edit is what the device refuses.
            from modules.nsot import recreate as _recreate
            if full["recreate"]["units"]:
                entry["recreates"] = [_recreate.describe(u) for u in full["recreate"]["units"]]
            if full["recreate"]["refused"]:
                entry["deployable"] = False
                entry["blocking_reasons"] = list(entry.get("blocking_reasons") or []) + [
                    r["reason"] for r in full["recreate"]["refused"]]
            if full["refused"]:
                # A removal the person asked for and will not get: the device is
                # not confirmable with it, and the reason says which and why.
                entry["deployable"] = False
                entry["blocking_reasons"] = list(entry.get("blocking_reasons") or []) + [
                    f"a removal you selected is refused: {' > '.join(r['chain'] + [r['line'].strip()])}"
                    f": {r['reason']}" for r in full["refused"]]
            # Flagged HERE, so the operator sees them while deciding, rather
            # than the CI gate discovering them at stage 3 with no reachable
            # way to authorise them.
            entry["dangerous"] = dangerous_in(commands)
            # Each authorisation is {line, reason} (C140): the person's
            # stated reason travels with the line into the hash and the receipt.
            from modules.nsot import authorisation as _auth
            authorised = _auth.normalise(authorise.get(hostname))
            entry["authorised"] = authorised
            entry["command_hash"] = command_fingerprint(commands, authorised, full["ids"])
            # The history of each line needing a reason, removals included: a
            # removal rolled back before shows when and why beside its box (the
            # operator: unblocked, but the person sees what happened last time).
            entry["prior_authorised"] = _prior_authorised(
                list_name, hostname, _auth.flagged(commands, full["keys"]))
            if entry["dangerous"] or authorised or full["keys"]:
                try:
                    assert_authorised(commands, authorised, full["keys"])
                    entry["authorisation_ok"] = True
                except NotAuthorised as exc:
                    entry["authorisation_ok"] = False
                    entry["authorisation_error"] = str(exc)
            # Every pushed line, attributed — before anyone confirms. A
            # profile-scoped plan's lines are the profile's by construction,
            # and its groups say so (`profile_scope`).
            if not scope:
                entry["attribution"] = _attribute_additions(
                    _repo_for(list_name), hostname, artifact, captured,
                    diff["to_add"])
            else:
                # A scoped plan attributes nothing (its lines are the
                # profile's), and still names BOTH commits it renders from:
                # the operands read "intent commit: none" beside a gate passing
                # committed intent (the operator, 2026-09-30, r6's apply).
                from modules.nsot import hostvars as _hv
                from modules.nsot import repo as _R
                entry["intent_commit"] = _hv.intent_change(_repo_for(list_name),
                                                           hostname).get("sha", "")
                rc, out, _e = _R.git(_repo_for(list_name), "log", "-1", "--format=%H", "--",
                                     _profile.PROFILE_REL)
                entry["profile_commit"] = out.strip() if rc == 0 else ""
        except (DeployRefused, profile_apply.ScopeRefused, _profile.ProfileRefused) as exc:
            entry["to_add"] = []
            entry["removal_warnings"] = []
            entry["refused"] = str(exc)
        except Exception as exc:              # noqa: BLE001
            log.exception("deploy: plan failed for %s", hostname)
            entry["to_add"] = []
            entry["removal_warnings"] = []
            entry["error"] = str(exc)

        from modules.nsot.device_ops import busy_text
        entry["busy"] = busy_text(list_name, hostname)       # C99
        devices.append(entry)
    return devices


@bp.route("/plan", methods=["POST"])
def plan():
    """Per-device diff and deployability. Reads captured configs only."""
    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    hostnames = data.get("devices") or []
    # Per device, always. Authorising a line for one device must never
    # authorise it for another in the same batch.
    authorise = data.get("authorise") or {}
    # Mode B (7.3 step 2): the lines a person SELECTED for removal, per device,
    # as `{device: [{chain, line}]}`. Never inferred from the residue: each is a
    # decision, and each needs a stated reason (through `authorise`).
    remove = data.get("remove") or {}
    if not hostnames:
        return jsonify({"ok": False, "error": "No devices selected"}), 400
    # P.9 step (b): "profile" sends only the network's monitoring profile's
    # lines. Anything else is refused by name, never read as the whole intent.
    from modules.nsot import profile_apply
    scope = (data.get("scope") or "").strip()
    if scope not in SCOPES:
        return jsonify({"ok": False, "error": (
            f"unknown deploy scope {scope!r}: the plan sends the device's whole intent, or "
            f"with scope {profile_apply.SCOPE!r} only its monitoring profile's lines, or with "
            f"scope 'ip_sla' only its IP SLA probes")}), 400

    devices = plan_devices(list_name, hostnames, authorise=authorise, remove=remove,
                           scope=scope)

    # The six parts, built ONCE by the shared contract (Stage 7.1); the
    # wizard draws `preview` with the one renderer. `devices` stays: apply's
    # wiring and older callers read it.
    from modules.outbound import mask_payload
    from modules.preview_confirm import deploy_preview
    # Masked on the way out, AFTER every hash is computed from the truthful
    # program (C77): the preview carried a secret the program adds, and
    # residue, verbatim.
    return jsonify(mask_payload({
        "ok": True, "list": list_name, "devices": devices, "scope": scope,
        "deployable_count": sum(1 for d in devices if d.get("deployable")),
        "preview": deploy_preview(devices, request, scope=scope)}))


def apply_batch(list_name: str, confirmations: dict, command_hashes: dict, *,
                authorise: dict = None, remove: dict = None, scope: str = "",
                actor: str, actor_kind: str = "", on_device=None) -> dict:
    """Deploy the confirmed devices, in the ORDER of *confirmations* (the
    rollout order: sequential, the circuit breaker stopping after repeated
    verify failures). THE apply, for `/deploy/apply` and the v2 batch confirm
    (P.9 d2), which runs it as a job: the actor and how it was verified come
    in as arguments, since a job's thread has no request to read them from."""
    from modules.nsot import profile as _profile, profile_apply
    from modules.nsot.deploy import (CircuitBreaker, NotAuthorised,
                                     assert_authorised, command_fingerprint,
                                     plan_batch, prepare_device, run_batch)

    authorise = authorise or {}
    remove = remove or {}
    artifacts, fresh_captures, device_rows = [], {}, {}
    refused = []
    for hostname in confirmations:
        built, error = _artifact_for(list_name, hostname)
        if built is None:
            # Register C24: this was `log.warning(); continue`, so a confirmed
            # device that could not be built vanished from the report, and the
            # result screen said "every device in a batch appears here" over a
            # batch missing one. It is a refusal, and it is named.
            log.warning("deploy: %s unavailable: %s", hostname, error)
            refused.append({"device": hostname, "outcome": "refused",
                            "reason": (f"could not be built at apply: {error}. "
                                       "Nothing was sent.")})
            continue
        artifact, captured, device = built

        expected = command_hashes.get(hostname)
        if expected is not None:
            try:
                intended = prepare_device(artifact)["config"]
                if scope:
                    intended = _scoped(scope, list_name, hostname, artifact, intended,
                                       captured, device)["config"]
                full = _program(intended, captured,
                                remove.get(hostname) or [], device,
                                getattr(artifact, "platform", ""))
                if full["refused"]:
                    raise NotAuthorised("a selected removal is refused: " + "; ".join(
                        f"{r['line'].strip()}: {r['reason']}" for r in full["refused"]))
                if full["recreate"]["refused"]:
                    raise NotAuthorised("; ".join(r["reason"] for r in full["recreate"]["refused"]))
                recomputed = full["commands"]
                device_auth = authorise.get(hostname) or []
                assert_authorised(recomputed, device_auth, full["keys"])
                now = command_fingerprint(recomputed, device_auth, full["ids"])
            except (NotAuthorised, profile_apply.ScopeRefused, _profile.ProfileRefused) as exc:
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

        if scope and expected is None:
            # A scoped apply is only ever a program a person confirmed: with no
            # command hash there is nothing to hold the scope to.
            refused.append({"device": hostname, "outcome": "refused",
                            "reason": ("applying the monitoring profile needs the command hash "
                                       "the preview showed. Nothing was sent.")})
            continue
        artifacts.append(artifact)
        device_rows[hostname] = device
        # Phase 3c reads a FRESH capture inside the pipeline (stage 4). Here the
        # comparison is against the same captured artifact the plan used, so a
        # change committed between plan and apply is caught before connecting.
        fresh_captures[hostname] = captured

    # One operation per device (C98): each device is held from here to its
    # commit and receipt. A device another operation holds is refused alone,
    # by name, and the rest proceed.
    from modules.nsot import device_ops
    held, busy = device_ops.acquire_many(
        list_name, [a.device for a in artifacts], "deploy", actor)
    artifacts = [a for a in artifacts if a.device in held]
    refused += busy
    try:
        batch = plan_batch(artifacts, confirmations, fresh_captures)

        extra = {**({"remove": remove} if remove else {}), **({"scope": scope} if scope else {})}
        record, pending = _pending_receipts(list_name, "deploy", confirmations, command_hashes,
                                            actor=actor, actor_kind=actor_kind)
        def _one(entry):
            # *on_device* (a job, P.9 d2) hears each device start and finish,
            # in the rollout order, so its page can draw where the batch is.
            name = entry["artifact"].device
            if on_device:
                on_device("start", name, None)
            result = record(_deploy_one(entry, list_name, device_rows, authorise, **extra))
            if on_device:
                on_device("done", name, result)
            return result

        report = run_batch(batch, _one, CircuitBreaker())
        if refused:
            _merge_refusals(report, refused)

        report["golden"] = _commit_batch_golden(
            list_name, report, actor=actor or "",
            **({"label": "after the monitoring profile was applied"} if scope else {}))
        report["receipts"] = _write_receipts(list_name, report, "deploy", confirmations,
                                             command_hashes, actor=actor,
                                             actor_kind=actor_kind, pending=pending)
    finally:
        device_ops.release_many(list_name, held)
    return report


@bp.route("/apply", methods=["POST"])
def apply():
    """Deploy the confirmed devices through the pipeline.

    *confirmations* maps device → the capture hash shown in the plan. A device
    whose fresh capture no longer matches is skipped and reported, never
    deployed against a diff the operator did not see.
    """
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
    remove = data.get("remove") or {}                      # Mode B, as at plan
    from modules.nsot import profile_apply
    scope = (data.get("scope") or "").strip()              # P.9 step (b), as at plan
    if scope not in SCOPES:
        return jsonify({"ok": False, "error": f"unknown deploy scope {scope!r}: nothing sent"}), 400

    from modules import identity
    report = apply_batch(list_name, confirmations, command_hashes, authorise=authorise,
                         remove=remove, scope=scope, actor=identity.request_actor(),
                         actor_kind=getattr(identity.identify(request), "kind", ""))
    # Masked on the way out (C77's apply side, measured 2026-09-27: a planted
    # community came back in `results[].commands`). The receipts and the
    # golden commit are written above from the truthful report; nothing
    # reads this response back into a confirm.
    from modules.outbound import mask_payload
    return jsonify(mask_payload({"ok": True, "list": list_name, **report}))


@bp.route("/receipts", methods=["GET"])
def receipts_read():
    """The receipt store, read back (7.1 step 3): what each deploy and restore
    sent, whether it matched what was confirmed, and what verify checked,
    drawn by the same result component as at apply. Masked on the way out
    (the rows are masked at write; this is the second layer). A READ, so it
    may derive the active list."""
    from modules.nsot import receipts
    from modules.outbound import mask_payload
    from modules.preview_confirm import receipt_history

    list_name = _active_list({"list_name": request.args.get("list_name", "")})
    device = (request.args.get("device") or "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 200))
    except ValueError:
        limit = 20
    got = receipts.read(list_name, device=device, limit=limit)
    body = {"ok": got["state"] != "unreadable", "list": list_name, "device": device,
            "state": got["state"], "error": got.get("error", ""),
            "changes": receipt_history(got["rows"], device) if got["state"] == "ok" else []}
    return jsonify(mask_payload(body)), (200 if body["ok"] else 500)


def _prior_authorised(list_name: str, hostname: str, lines) -> dict:
    """How often each line needing an authorisation in this program was
    authorised on this device before (C140's aggregate), for the preview."""
    from modules.nsot.receipts import prior_authorisations

    try:
        return prior_authorisations(list_name, hostname, lines)
    except Exception as exc:                  # noqa: BLE001
        return {"state": "unreadable", "lines": {}, "error": str(exc)}


def _pending_receipts(list_name: str, action: str, confirmations: dict, command_hashes: dict,
                      source_ref: str = "", *, actor: str, actor_kind: str):
    """``(record, pending)``: *record(result)* writes ONE device's receipt row the moment
    that device finishes, marked commit pending (CONCURRENCY_AUDIT R5), and returns the
    result unchanged; *pending* is the run's id and, by device, each row so recorded, for
    `_write_receipts` to complete after the batch's commit. The batch's golden commit
    comes after every device, so a process that ended in between used to leave devices
    already pushed with no receipt at all. A row that could not be written is not in
    *pending*: the device's whole row is written at the end instead, as before."""
    from modules.nsot import receipts

    run_id = os.urandom(8).hex()
    pending = {"run_id": run_id, "ids": {}}

    def record(result: dict) -> dict:
        row = receipts.pending_row(result, list_name=list_name, action=action, actor=actor,
                                   actor_kind=actor_kind or "", confirmations=confirmations,
                                   command_hashes=command_hashes, source_ref=source_ref,
                                   run_id=run_id)
        if receipts.write(list_name, [row])["ok"]:
            pending["ids"][row["device"]] = row["id"]
        return result

    return record, pending


def _write_receipts(list_name: str, report: dict, action: str, confirmations: dict,
                    command_hashes: dict, source_ref: str = "", *, actor: str = None,
                    actor_kind: str = None, pending: dict = None) -> dict:
    """Record what was sent, after the commit it names (C60). A failure is
    loud in the response and the log, and never turns a deploy that happened
    into one that reads as failed. A device whose row was written as it
    finished (*pending*, from `_pending_receipts`) gets a completion line
    naming that row and filling in the commit; every other device (refused
    before it started, left unattempted by the breaker) gets its whole row.

    It also draws the RESULT (7.1 step 2) into ``report["result"]``, from the
    SAME rows it writes: the screen and the record are one computation, so
    the result cannot claim something the receipt does not."""
    from modules import identity
    from modules.nsot import receipts
    from modules.preview_confirm import operation_result

    if actor is None:                     # inside the request: ask it
        actor = identity.request_actor()
        actor_kind = getattr(identity.identify(request), "kind", "")
    rows = receipts.rows_for(report, list_name=list_name, action=action,
                             actor=actor, actor_kind=actor_kind or "",
                             confirmations=confirmations,
                             command_hashes=command_hashes, source_ref=source_ref)
    pending = pending or {}
    lines = []
    for row in rows:
        # One run id on every row of the run, so a history groups a batch that committed
        # nothing (no batch id) as one batch, its refusals with its finished devices.
        if pending.get("run_id"):
            row["run_id"] = pending["run_id"]
        pid = (pending.get("ids") or {}).get(row["device"])
        if pid:
            row["id"] = pid
            lines.append(receipts.completion(row, pid))
        else:
            lines.append(row)
    status = receipts.write(list_name, lines)
    report["result"] = operation_result(rows, report, status,
                                        "deploy" if action == "deploy" else "restore")
    return status


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
                label: str = "", source_ref: str = "", skipped: list = None) -> dict:
    """Run a batch of already-built targets. Shared by deploy and re-apply.

    Everything below the intent layer is the same operation whether the target
    came from rendering committed intent or from reading a stored config: the
    confirm hash, the authorisation, the circuit breaker, sequential
    execution, failure capture, rollback and the single golden commit. Only
    *what to send* differs, and that was decided before this is called.
    """
    from modules.nsot.deploy import (CircuitBreaker, NotAuthorised,
                                     assert_authorised, command_fingerprint,
                                     plan_batch, prepare_for_deploy, run_batch)

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
                # The deploy's own program (`_program`), as the preview built it:
                # a running IP SLA operation is re-created, or the device refused.
                full = _program(prepare_for_deploy(target)["config"], captured, [], None,
                                getattr(target, "platform", ""))
                if full["recreate"]["refused"]:
                    raise NotAuthorised("; ".join(r["reason"] for r in full["recreate"]["refused"]))
                recomputed = full["commands"]
                device_auth = authorise.get(hostname) or []
                # A restore's re-added secret lines need an authorisation too
                # (C79), from the same mechanism as a dangerous line.
                assert_authorised(recomputed, device_auth,
                                  extra=getattr(target, "reintroduced_secrets", ()))
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

    # One operation per device (C98), held from here to the commit and the
    # receipt; a device another operation holds is refused alone, by name.
    from modules import identity
    from modules.nsot import device_ops
    actor = identity.request_actor()
    actor_kind = getattr(identity.identify(request), "kind", "")
    action = "restore" if source_ref else "reapply"
    held, busy = device_ops.acquire_many(
        list_name, [t.device for t in accepted], "restore", actor,
        detail=label or (f"re-apply {source_ref}" if source_ref else ""))
    accepted = [t for t in accepted if t.device in held]
    refused += busy
    try:
        batch = plan_batch(accepted, confirmations, fresh_captures)
        record, pending = _pending_receipts(list_name, action, confirmations, command_hashes,
                                            source_ref, actor=actor, actor_kind=actor_kind)
        report = run_batch(batch,
                           lambda entry: record(_deploy_one(entry, list_name, device_rows,
                                                            authorise, source_ref)),
                           CircuitBreaker())
        if refused:
            # Same helper as the deploy path: the restore path merged refusals
            # the same way and had the same disagreement between its count
            # and its rows. Two copies of a fold is how they come to differ.
            _merge_refusals(report, refused)
        report["golden"] = _commit_batch_golden(list_name, report, label=label,
                                                source_ref=source_ref)
        # Before the result is drawn, so it names the devices the ref did not
        # touch (the restore's own skip list) as well as the ones it did.
        report["skipped"] = list(skipped or [])
        report["receipts"] = _write_receipts(
            list_name, report, action, confirmations, command_hashes, source_ref=source_ref,
            actor=actor, actor_kind=actor_kind, pending=pending)
    finally:
        device_ops.release_many(list_name, held)
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


def _program(intended: str, captured: str, selected: list, device: dict,
             platform: str) -> dict:
    """The deploy program for one device: the merge additions, then the
    RE-CREATED running IP SLA operations, then the SELECTED removals. ONE
    computation for plan, apply and the pipeline's run.

    A running IP SLA operation intent changes is never part of the merge: the
    device refuses to modify it in place, so it is deleted, re-created from
    intent and rescheduled (`recreate.py`), and refused, naming why, where
    that delete is not measured for the platform."""
    from modules.nsot import recreate
    from modules.nsot.deploy import merge_commands
    from modules.nsot.removal import with_removals

    rc = recreate.plan(intended, captured, dialect=platform)
    # A refused operation is excluded too: its in-place edit is what the device
    # refuses, so no program, sent or drawn, ever holds it.
    merge = merge_commands(recreate.exclude(intended, rc["units"] + rc["refused"]), captured)
    full = with_removals(merge, captured, selected,
                         mgmt_ip=(device or {}).get("ip", ""), dialect=platform)
    return {**full, "commands": list(merge) + rc["commands"] + list(full["removal_commands"]),
            "recreate": rc}


def _deploy_one(entry, list_name: str, device_rows: dict,
                authorise: dict = None, source_ref: str = "", remove: dict = None,
                scope: str = "") -> dict:
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
    from modules.nsot import authorisation as _auth
    intended = prepared["config"]
    if scope:
        # The profile's lines only, computed AGAIN here: this is the path that
        # connects, and it holds the truthful renders (P.9 step b).
        try:
            intended = _scoped(scope, list_name, hostname, artifact, intended, captured,
                               device)["config"]
        except Exception as exc:                # noqa: BLE001
            return {"device": hostname, "outcome": FAILED, "stage": "scope",
                    "reason": f"the monitoring profile could not be scoped: {exc}"}
    full = _program(intended, captured, (remove or {}).get(hostname) or [],
                    device, getattr(artifact, "platform", ""))
    if full["recreate"]["refused"]:
        return {"device": hostname, "outcome": FAILED, "stage": "recreate",
                "reason": "; ".join(r["reason"] for r in full["recreate"]["refused"])}
    if full["refused"]:
        return {"device": hostname, "outcome": FAILED, "stage": "removal",
                "reason": "a selected removal is refused: " + "; ".join(
                    f"{r['line'].strip()}: {r['reason']}" for r in full["refused"])}
    # Every removal carries a stated reason, checked HERE too: this is the path
    # that connects, and it runs whether or not the confirm hash was compared.
    authorised_now = _auth.normalise((authorise or {}).get(hostname))
    unreasoned = [k for k in full["keys"] if k not in _auth.valid_keys(authorised_now)]
    if unreasoned:
        return {"device": hostname, "outcome": FAILED, "stage": "authorisation",
                "reason": ("every removal needs a stated reason; none of the right shape for: "
                           + "; ".join(unreasoned))}
    commands = full["commands"]
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
        # The ADDITIONS are merge-only against intent; the removals are held to
        # their own provenance (each is a selected unit on the capture, measured
        # for its platform, with a reason), never to intent, which lacks them.
        assert_merge_only(full["merge"], prepared["config"])
    except Exception as exc:                    # noqa: BLE001
        return {"device": hostname, "outcome": FAILED, "stage": "merge-only",
                "reason": str(exc)}

    ctx = PipelineContext(
        config_type="template",
        device_ips=[device.get("ip", "")],
        # The route check RUNS (C115, the operator's decision 2026-09-27). It
        # was skipped here for every deploy and restore while the result drew
        # "routes 22 -> 22" as though compared.
        params={},
        ip_params_map={},
        selected_devices=[device],
        connections_pool={},
        pool_lock=threading.Lock(),
        config_id=f"tpl-{hostname}",
        # Carried, never re-derived. The pipeline must not ask a global which
        # network it is writing to: a list switch during a 45-90s convergence
        # window would land this device's golden in another list's repository.
        list_name=list_name,
    )
    # Scoped to THIS device. The batch's other devices get their own list.
    from modules.nsot import authorisation as _auth
    # Each {line, reason}, for the receipt. The pipeline's own gate runs on
    # every path, so it honours only an authorisation whose reason has the
    # shape of one (C140): where the confirm hash is not compared, a
    # reason-less authorisation still cannot pass.
    authorised = _auth.normalise((authorise or {}).get(hostname))
    ctx.params["allowed_dangerous"] = _auth.valid_keys(authorised)
    # Confirmed, not merely pre-populated: rendered_commands derives from this,
    # so stage 2 cannot overwrite it and an attempt to do so raises.
    ctx.confirmed_commands = {device.get("ip", ""): commands}
    # The removal half, so rollback undoes it by re-adding the device's own
    # lines and verify reads back that each is gone.
    # And the re-created IP SLA operations, the block before the removals:
    # verify reads each back as intent defines it, and rollback restores
    # each old definition from the pre-change snapshot.
    ctx.removals = {device.get("ip", ""): {"units": full["removed"],
                                           "commands": full["removal_commands"],
                                           "recreates": full["recreate"]["units"],
                                           "recreate_commands": full["recreate"]["commands"]}}
    # The batch commits; this device hands its capture back.
    ctx.defer_golden = True
    # What the TARGET intent declares, so verify checks the protocol this
    # operation may exist to bring back (it read the device's before-state
    # alone). A restore's target is the ref's intent (None: the ref predates
    # the device's onboarding, so unknown); a deploy's, its committed intent.
    from modules.nsot.golden_state import declared_protocols
    if hasattr(artifact, "ref_intent"):
        target_intent = artifact.ref_intent
    else:
        target_intent = getattr(artifact, "host_vars", None)
    ctx.declared_protocols = {device.get("ip", ""): (
        declared_protocols(target_intent) if target_intent is not None else None)}

    try:
        result = PipelineRunner(ctx).run()
    except Exception as exc:                    # noqa: BLE001
        log.exception("deploy: pipeline raised for %s", hostname)
        return {"device": hostname, "outcome": FAILED, "stage": "pipeline",
                "reason": str(exc)}
    finally:
        # The run's pool is this run's, and nothing else will ever close it:
        # each deploy and restore left one session open until the device's
        # ten-minute timeout, and five of them locked the tool out of r2 (C97).
        from modules.connection import close_persistent_connection
        for ip in list(ctx.connections_pool):
            close_persistent_connection(ip, ctx.connections_pool, ctx.pool_lock)

    from modules.nsot.deploy import command_fingerprint

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
        # What the rollback ACHIEVED on this device (C112), not whether one ran.
        "rollback_outcome": dict((result.rollback_outcome or {}).get(device.get("ip", ""), {})),
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
        # The receipt's two load-bearing facts (C60): what verify compared on
        # this device, and the hash of the program as SENT (the lines the
        # pipeline was given, with the authorisation folded in, exactly as the
        # confirm hash is computed).
        "verify": dict((result.verify_result or {}).get(device.get("ip", ""), {})),
        "program_hash": command_fingerprint(commands, authorised, full["ids"]),
        # What was selected for removal, by ID, with the line as the capture
        # held it: the receipt ties the selection to what was sent (Mode B).
        "removals": [{"id": i, "chain": list(u["chain"]), "line": u["line"]}
                     for i, u in zip(full["ids"], full["removed"])],
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
                         source_ref: str = "", actor: str = "") -> dict:
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
    earned = _baseline_earned(report, pending, failed, source_ref=source_ref,
                              list_name=list_name)
    what = label or f"via pipeline {batch_id}"
    # No "baseline" in the subject (C83): the tag is the claim, and it is
    # decided by save_golden after this commit and may be denied.
    subject = f"golden: {len(pending)} device(s) {what}"
    trailers = [f"Failed-Devices: {','.join(sorted(failed))}"] if failed else []
    # The program each device was SENT, by hash (C60): the commit is the
    # capture after the push, and this names what produced it. The full
    # receipt, program included, is in deploy_receipts.jsonl.
    for entry in results:
        if entry.get("program_hash") and entry.get("device") in succeeded:
            trailers.append(f"Program-Hash: {entry['device']}={entry['program_hash']}")

    # Device and intent are ONE UNIT per device, so the restored intent is part
    # of this commit, not a second one after it. A restore path names
    # ``host_vars`` explicitly; a template deploy does not, and so can never
    # carry intent into a commit by accident.
    intent, extra_paths = {}, None
    if source_ref:
        intent = _write_restored_intent(list_name, report, source_ref)
        if intent["restored"] or intent["un_onboarded"]:
            # Exactly the restored devices' files, never the tree (C175).
            from modules.nsot.hostvars import committed_rel
            extra_paths = [committed_rel(h)
                           for h in intent["restored"] + intent["un_onboarded"]]
            trailers.append(f"Restored-Intent: {','.join(intent['restored'])}")
            if intent["un_onboarded"]:
                trailers.append(
                    f"Un-Onboarded: {','.join(intent['un_onboarded'])}")

    items = [GoldenItem(p["hostname"], p["config_text"], p["mgmt_ip"],
                        netbox_id=p["netbox_id"], device_uid=p["device_uid"])
             for p in pending]
    # `Source:` names the WORKFLOW (repo.ACTOR_CONVENTION). A restore was
    # recorded `pipeline`, the mechanism both paths share, so C70's premise
    # ("no commit carries Source: restore") held whether or not a restore
    # had ever run: a lookup that could not miss.
    result = save_golden(list_name, items, source="restore" if source_ref else "pipeline",
                         # The person carried in by a job (deploy_job): outside a
                         # request `request_actor()` reads `unauthenticated`, and
                         # the commit would record nobody behind the deploy.
                         actor=actor or request_actor(),
                         message=subject, pipeline_id=batch_id,
                         baseline=earned["baseline"], allow_new=False,
                         baseline_reasons=(None if earned["baseline"]
                                           else earned.get("baseline_reasons")),
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
                     source_ref: str = "", *, list_name: str) -> dict:
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
    from modules.nsot.restore import _devices_of

    reasons = []
    if failed:
        reasons.append(f"{len(failed)} device(s) did not succeed: {sorted(failed)}")

    try:
        # The batch's own list (C215), never the active one.
        inventory = {d.get("hostname", "") for d in _devices_of(list_name)}
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
