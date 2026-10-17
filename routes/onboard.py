"""routes/onboard.py — onboarding's cores, Phase 4 / Stage 4C.4. **No blueprint** since 7.8.

**Two cores that create nothing and one that does.** `plan_of` and
`platform_choices` are pure reads; `create_run` is the only one that writes, and it
refuses a plan `build_plan()` has not cleared, or one that is not the plan previewed.

**A refusal the operator cannot see is not a refusal.** `blocking_reasons`
already carries every reason at once (4C.1); these cores' job is to get
all of them onto the screen, with the create action disabled, rather than
leaving the plan object to be right in private.

Today's onboarding wizard, its pending banner and their nine routes (/onboard/platforms,
/pending, /bootstrap/<host>, /verify/<host> and its preview, /abandon/<host>, /lists, /plan,
/create) left at 7.8 on 2026-10-17 (P7-25; restore point tag `pre-remove/v1-onboarding`).
Their home is v2 (`routes/onboard_v2.py`): Devices › Add device… (the plan's review, then
Create bound to it) and a pending device's page (Verify…, Get the bootstrap config…,
Abandon…), each calling the cores below; the pending page's last run is `_run_history`
(`routes/device_v2.py`).
"""

import logging

from flask import request

log = logging.getLogger(__name__)


def _dialect(platform: str) -> str:
    """A NetBox platform slug → the config dialect, through the one owner."""
    from modules.nsot.platform import platform_for_device

    value = (platform or "").strip()
    return platform_for_device({"platform": value}) if value else ""


class NoTargetList(ValueError):
    """The request did not say which list to onboard into."""


#: What each caller of `_target_list()` is doing, in its own words.
#:
#: The refusal used to explain why ONBOARDING carries its list — to an
#: operator who had pressed Abandon. A correct refusal describing a
#: different action reads as a bug in the tool, and sent the reader looking
#: for a wizard they had not opened.
#:
#: **A refusal on a shared helper names the caller's operation, not the
#: helper's reason for existing.** The consequence clause differs too: the
#: onboarding one is about what a wrong list leaves behind, and the abandon
#: one is about what it would remove.
_WHAT = {
    "plan":    ("plan an onboarding",
                "onboarding into the wrong one leaves a commit and a NetBox "
                "object behind"),
    "create":  ("onboard a device",
                "onboarding into the wrong one leaves a commit and a NetBox "
                "object behind"),
    "verify":  ("verify a pending device",
                "the device, its credential and its manifest entry all live "
                "in one list"),
    "abandon": ("abandon a pending device",
                "abandoning the wrong one would delete another list's "
                "commit and NetBox objects"),
    "pending": ("list pending devices", "pending state is per list"),
    "bootstrap": ("download a bootstrap config",
                  "the config and its staged credential belong to one list"),
}


def _target_list(data, what: str = "plan") -> str:
    """The list this request names. **Never the active one as a fallback.**

    `PipelineContext.list_name` already established this rule the expensive
    way: the pipeline asked `get_current_list_name()` at three points after
    the push, and a list switch during a 45-90s convergence window committed
    one network's captures into another's repository. The wizard was on the
    wrong side of a rule this codebase already has.

    The asymmetry is what decides it. Onboarding into the wrong list leaves a
    **commit, a NetBox object and a `devices.csv` row** in a live network,
    and repairing it means the provenance-based Remove plus a git revert --
    where Remove is the very mechanism the Stage 4C probe exists to prove.
    **The failure is repaired by something that is itself unproven.**

    Inheriting the active list made that a one-click mistake caught only by
    an operator reading a line on the review screen that is correct ~95% of
    the time. It was very nearly made, and was caught only because the hard
    stop at step 6 exists to be read.

    So an absent list is refused rather than guessed. Add device always sends
    one; it is a field like any other.
    """
    name = ((data or {}).get("list_name") or "").strip()
    if not name:
        action, why = _WHAT.get(what, _WHAT["plan"])
        raise NoTargetList(
            f"no target list was sent with the request to {action}. The "
            f"list is carried by the caller rather than inherited from "
            f"whichever list happens to be active, because {why}.")
    return name


def _plan_args(data, list_name: str, *, secret: str) -> dict:
    """The request fields `build_plan` needs, derived ONCE.

    Both `plan_of` and `create_run` build a plan from the same
    request, and `create_run` rebuilds it deliberately -- the state can
    change between the review and the confirm. That only works while the two
    builds read the request the same way: a field added to one and not the
    other means the operator confirms a plan that differs from the one they
    read, which is the failure the rebuild exists to prevent.

    Same reasoning as `real_steps()` being assembled once. Two copies of a
    mapping are two mappings.
    """
    return dict(
        hostname=(data.get("hostname") or "").strip(),
        # Translated because the operator picks a NetBox slug and
        # `build_plan` speaks the config dialect.
        platform=_dialect(data.get("platform")),
        # And the slug itself, compared with a Planned NetBox record's platform (C676).
        platform_slug=(data.get("platform") or "").strip(),
        list_name=list_name,
        mgmt_ip=(data.get("mgmt_ip") or "").strip(),
        mgmt_mask=(data.get("mgmt_mask") or "").strip(),
        # Never defaulted here either. A route that fills in Gi1 on a C8000v
        # has made the guess the generator refuses to make.
        manager_interface=(data.get("manager_interface") or "").strip(),
        manager_gateway=(data.get("manager_gateway") or "").strip(),
        source_kind=data.get("source_kind") or "local",
        secret=secret,
        domain=(data.get("domain") or "rcn.lab").strip(),
        mgmt_interface=(data.get("mgmt_interface") or "").strip(),
        # A STATED SOURCE, defaulted to `static` so every existing caller and
        # every existing test is unchanged. `dhcp` is only ever reached by
        # somebody saying so.
        address_source=(data.get("address_source") or "static").strip(),
        mgmt_mac=(data.get("mgmt_mac") or "").strip(),
        # ASKED, never guessed from the platform (C225).
        role=(data.get("role") or "").strip().lower(),
    )


def platform_choices() -> list:
    """Each platform a device can be onboarded as, blocked ones listed with their reason;
    v2's Add device draws this one list.

    A platform blocked pending a measurement is **listed and disabled**, not
    omitted: an absent option teaches the operator the tool does not support
    their device, which is a different and wrong lesson."""
    from modules.nsot.onboard import BLOCKED_PENDING_MEASUREMENT
    from modules.nsot.platform import platform_for_device
    from modules.settings_schema import get_setting

    # TWO NAMESPACES, and they are not the same. `platform_map` is keyed on
    # NetBox platform SLUGS (`cisco-ios-xe`); `bootstrap_config` and the
    # parsers are keyed on the config DIALECT (`cisco_iosxe`). Looking a slug
    # up in the dialect table silently found nothing, so every platform
    # reported unblocked -- including the one stage D blocks.
    #
    # `platform_for_device()` owns that translation and is called rather than
    # copied: a second copy of the mapping is how the two come to disagree
    # about what `cisco-ios` means.
    out = []
    for slug in sorted(get_setting("platform_map", {}) or {}):
        dialect = platform_for_device({"platform": slug})
        blocked = BLOCKED_PENDING_MEASUREMENT.get(dialect, "")
        out.append({"platform": slug, "dialect": dialect,
                    "blocked": bool(blocked), "reason": blocked})
    return out


def _driver_for(list_name: str, hostname: str, data) -> str:
    """The Netmiko driver for a pending device.

    Derived from the dialect the manifest stores, through the one
    translator. A `device_type` default here would be one platform's driver
    asserted as every platform's — `test_platform_keying` caught exactly
    that, as an undeclared platform literal in this file.
    """
    given = (data.get("device_type") or "").strip()
    if given:
        return given

    from modules.nsot import manifest as _m
    from modules.nsot.platform import netmiko_type_for_dialect

    _identity, entry = _m.find_by_name(_repo_for(list_name), hostname)
    return netmiko_type_for_dialect((entry or {}).get("platform", ""))


def _repo_for(list_name: str) -> str:
    import os

    from modules.config import get_list_data_dir

    return os.path.join(get_list_data_dir(list_name), "config_repo")


def bootstrap_reveal(hostname: str, data, req) -> tuple:
    """``(answer, status)``: the bootstrap config, revealed to a person and recorded; the one
    path, for v2's pending page."""
    from modules import identity as ident_mod, reveal_audit

    try:
        list_name = _target_list(data, "bootstrap")
    except NoTargetList as exc:
        return {"ok": False, "error": str(exc)}, 400

    ident, refusal = ident_mod.require(req, action="reveal",
                                       operation="onboard_bootstrap")
    if refusal is not None:
        # A refused reveal returns no config at all — there is no masked
        # form worth returning, since a masked bootstrap config is the one
        # thing this artefact must never be.
        return {**refusal, "config": ""}, 403

    from modules.nsot.onboard import bootstrap_artifact

    out = bootstrap_artifact(_repo_for(list_name), hostname)
    if not out.get("ok"):
        return out, 404

    entry = reveal_audit.record(actor=ident.actor, kind=ident.kind,
                                what="bootstrap_config", target=hostname,
                                detail=f"list={list_name}", peer=ident.peer,
                                extra={"list": list_name})
    if not entry.get("recorded"):
        # C841: fail closed, as the log line's reveal does. The record is written first and
        # read; a reveal it could not record shows nothing, the config and its credential
        # included.
        return {"ok": False, "config": "",
                "error": ("the reveal could not be recorded, so nothing is shown: a bootstrap "
                          "config is never revealed unrecorded")}, 503
    return {**out, "revealed_by": ident.actor}, 200


def verify_run(hostname: str, data, ident) -> tuple:
    """``(answer, status)``: Verify (phase 2) for a verified person, as previewed. The one code
    path, for v2's pending page."""
    try:
        list_name = _target_list(data, "verify")
    except NoTargetList as exc:
        return {"ok": False, "error": str(exc)}, 400
    # Verify is a preview and a confirm (P.9 step c): phase 2 sends a program
    # (the RW removal and the monitoring profile), and a program nobody was
    # shown is what the confirm exists to prevent.
    fingerprint = (data.get("fingerprint") or "").strip()
    if not fingerprint:
        return {"ok": False, "error": (
            "Verify confirms what its preview showed, and no preview fingerprint was "
            "sent: open Verify's preview first")}, 400

    from modules.nsot.onboard import run_phase_two

    repo = _repo_for(list_name)
    try:
        out = run_phase_two(repo, hostname, list_name, actor=ident.actor,
                            actor_kind=ident.kind, confirmed=fingerprint)
    except Exception as exc:                   # noqa: BLE001
        log.exception("onboard: verify failed for %r", hostname)
        out = {"ok": False, "reason": f"phase 2 raised: {exc}", "steps": []}
    return (_recorded_run(repo, "verify", list_name, hostname, ident.actor, out),
            200 if out.get("ok") else 409)


def verify_preview_of(hostname: str, data, req) -> tuple:
    """``(answer, status)``: Verify's preview, masked; for v2's pending page."""
    try:
        list_name = _target_list(data, "verify")
    except NoTargetList as exc:
        return {"ok": False, "error": str(exc)}, 400
    from modules import outbound, preview_confirm
    from modules.nsot.onboard import phase_two_plan

    plan = phase_two_plan(_repo_for(list_name), hostname, list_name)
    if not plan.get("ok"):
        seen = plan.get("verify") or {}
        return outbound.mask_payload({
            "ok": False, "error": plan.get("reason") or "the preview could not be made",
            "state": seen.get("state", ""), "causes": seen.get("causes") or []}), 409
    return outbound.mask_payload({
        "ok": True, "preview": preview_confirm.onboard_verify_preview(
            plan, preview_confirm.confirm_part(req))}), 200


def abandon_run(hostname: str, data, actor: str, confirmed: str = "") -> tuple:
    """``(answer, status)``: Abandon, or its dry run (``dry_run``), for v2's pending page.
    *confirmed* binds it to the dry run shown: an Abandon without one is refused, removing
    nothing (today's unbound Abandon left at 7.8 on 2026-10-17)."""
    try:
        list_name = _target_list(data, "abandon")
    except NoTargetList as exc:
        return {"ok": False, "error": str(exc)}, 400

    from modules.nsot.onboard import abandon_onboarding

    repo = _repo_for(list_name)
    dry_run = bool(data.get("dry_run"))
    if not dry_run and not confirmed:
        return {"ok": False, "error": (
            "Abandon confirms what its preview showed, and no preview fingerprint was sent: "
            "preview first. Nothing was removed")}, 400
    try:
        out = abandon_onboarding(repo, hostname, list_name, actor=actor, dry_run=dry_run,
                                 **({"confirmed": confirmed} if confirmed else {}))
    except Exception as exc:                   # noqa: BLE001
        log.exception("onboard: abandon failed for %r", hostname)
        out = {"ok": False, "error": f"abandon raised: {exc}", "steps": []}
    if not dry_run and not out.get("moved"):   # a dry run or a refusal removes nothing: no record
        out = _recorded_run(repo, "abandon", list_name, hostname, actor, out)
    return out, (200 if out.get("ok") else 409)


def _recorded_run(repo: str, kind: str, list_name: str, hostname: str, actor: str,
                  out: dict) -> dict:
    """Record the run, then draw its result FROM the recorded row (7.1), so
    the result now and the one the device's pending page reads back later are one
    computation. The record failing is part of the result, never silent."""
    from modules.nsot.onboard import record_run
    from modules.preview_confirm import onboard_run_result

    rec = record_run(repo, kind, list_name, hostname, actor, out)
    return {**out, "result": onboard_run_result(rec["row"], rec)}


def _run_history(repo: str, pending_names: set) -> dict:
    """What a pending device's page reads back (`routes/device_v2.py`): each pending
    device's last run, and the runs that took a device OFF the list (promoted or abandoned),
    newest first. A row that leaves the list takes its result with it
    otherwise, and those are the results most worth reading again."""
    from modules.nsot.onboard import read_runs, run_heading
    from modules.preview_confirm import onboard_run_result

    read = read_runs(repo)
    last, finished = {}, []
    for r in read["rows"]:
        name = r.get("device", "")
        if name in last:
            continue
        last[name] = {**run_heading(r), "result": onboard_run_result(r)}
        if name not in pending_names and len(finished) < 10:
            finished.append(dict(last[name], device=name))
    return {"state": read["state"], "error": read["error"],
            "last": {n: v for n, v in last.items() if n in pending_names},
            "finished": finished}


def plan_of(data) -> tuple:
    """``(answer, status)``: the plan and its review for the request's fields (v2's Add
    device), with ``shown`` and ``fingerprint``, what its Create sends back. **Creates
    nothing.**"""
    from modules.nsot.onboard import build_plan, plan_fingerprint, plan_shown

    try:
        list_name = _target_list(data, "plan")
    except NoTargetList as exc:
        return {"ok": False, "error": str(exc)}, 400
    try:
        # A placeholder secret so the render is exercised. The real one-time
        # credential is minted at create time and never round-trips through
        # the browser.
        built = build_plan(**_plan_args(
            data, list_name, secret="PLACEHOLDER-not-the-real-credential"))
    except Exception as exc:                   # noqa: BLE001
        log.exception("onboard: plan failed")
        return {"ok": False, "error": str(exc)}, 500

    shown = plan_shown(built)
    return {
        "ok": True,
        "plan": built.summary,
        "host_vars": built.host_vars,
        # The review, drawn by the preview component (7.1), as the verified
        # person who would press Create (its gate kind is `approve`).
        # The config that WILL be created is its program part (one copy: the
        # separate `bootstrap_config` key went with the old review). It
        # carries only the placeholder secret, by construction.
        "preview": _onboard_preview(built.summary, built.bootstrap_config),
        "shown": shown, "fingerprint": plan_fingerprint(shown),
    }, 200


def _onboard_preview(summary: dict, bootstrap_config: str) -> dict:
    from modules.preview_confirm import confirm_part, onboard_preview
    return onboard_preview(summary, bootstrap_config, confirm_part(request, "approve"))


def create_run(data, actor: str) -> tuple:
    """``(answer, status)``: Create (phase 1) for a verified person (v2's Add device). Refused
    unless the plan rebuilt under the hold is the one previewed: the request's ``shown`` and
    ``fingerprint`` (7.1's binding). Today's wizard, which rebuilt without one
    (CONCURRENCY_AUDIT R36), left at 7.8 on 2026-10-17, and with it the unbound form."""
    import os

    from modules.config import get_list_data_dir
    from modules.nsot.onboard import build_plan, plan_moved, real_steps, run_onboarding

    try:
        list_name = _target_list(data, "create")
    except NoTargetList as exc:
        return {"ok": False, "error": str(exc)}, 400
    repo = os.path.join(get_list_data_dir(list_name), "config_repo")

    from modules.nsot import device_ops

    args = _plan_args(data, list_name, secret="")
    # The hostname HELD from the plan's rebuild to the last step (CONCURRENCY_AUDIT R23): with
    # nothing between the name check and the mint, two Creates for one name could leave two
    # identities, and a Create beside an Abandon could rebuild on what the Abandon removed.
    try:
        with device_ops.hold(list_name, args.get("hostname", ""), "onboard (create)", actor):
            # REBUILT HERE, not carried from the review. The stores can change
            # between the screen and the confirm -- the same reason the deploy path
            # recomputes its program at apply rather than trusting what was shown.
            # secret="" -- the real one is minted by the credentials step.
            plan = build_plan(**args)
            moved = plan_moved(data.get("shown") or "", data.get("fingerprint") or "", plan)
            if moved:
                return {"ok": False, "moved": True,
                        "error": f"Not created: {moved}. Nothing was changed."}, 409
            if not plan.onboardable:
                return {"ok": False, "error": "; ".join(plan.blocking_reasons),
                        "blocking_reasons": plan.blocking_reasons}, 409

            result = run_onboarding(plan, repo=repo, **real_steps(repo, actor=actor))
    except device_ops.DeviceBusy as exc:
        return {"ok": False, "error": f"Not created: {exc}. Nothing was changed."}, 409
    # What happened, drawn by the result component (7.1, C86): Create is
    # phase 1 and leaves the device PENDING, which the toast it replaces
    # called "Device onboarded.".
    from modules.preview_confirm import onboard_create_result
    result["result"] = onboard_create_result(result, plan)
    return result, (200 if result.get("ok") else 500)
