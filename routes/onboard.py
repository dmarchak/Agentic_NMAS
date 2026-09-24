"""routes/onboard.py — the onboarding wizard, Phase 4 / Stage 4C.4.

**Two routes that create nothing and one that does.** `/plan` and
`/platforms` are pure reads; `/create` is the only path that writes, and it
refuses a plan `build_plan()` has not cleared.

**A refusal the operator cannot see is not a refusal.** `blocking_reasons`
already carries every reason at once (4C.1); this blueprint's job is to get
all of them onto the screen, with the create action disabled, rather than
leaving the plan object to be right in private.

Reached from a **button on the Devices toolbar**, not a thirteenth tab.
Onboarding is fleet-level, Stage 7 reorganises around exactly that
distinction, and a new tab is the thing that redesign exists to undo.
"""

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("onboard", __name__, url_prefix="/onboard")


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

    So an absent list is refused rather than guessed. The wizard always sends
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

    Both `/onboard/plan` and `/onboard/create` build a plan from the same
    request, and `/onboard/create` rebuilds it deliberately -- the state can
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
    )


@bp.route("/platforms", methods=["GET"])
def platforms():
    """What can be onboarded, and what cannot — with the reason.

    A platform blocked pending a measurement is **listed and disabled**, not
    omitted: an absent option teaches the operator the tool does not support
    their device, which is a different and wrong lesson.
    """
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
    return jsonify({"ok": True, "platforms": out})


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


@bp.route("/pending", methods=["GET"])
def pending():
    """Devices onboarded and never reached, with age and state.

    **An error here must not render as an empty list.** The banner's
    wrong-and-looks-right state is showing "no pending devices" because the
    query failed — a reassuring sentence produced by a broken read, which is
    the shape this project has corrected in the drift panel ("all 9 clean"
    over ten devices) and the agent panel (a disabled read returning `[]`).
    So a failure answers `ok: false` with the reason, and the client is
    required to draw that differently from an empty list.
    """
    # A READ MAY DERIVE THE ACTIVE LIST; a write may not.
    #
    # `_target_list()` refuses an absent list because onboarding into the
    # wrong one leaves a commit and a NetBox object behind. Listing pending
    # devices leaves nothing, and the page asking "what is pending here"
    # means the list it is showing — so the fallback is correct rather than
    # a relaxation. The list is echoed in the response so a caller can see
    # which one it got.
    from modules.config import get_current_list_name

    list_name = (request.args.get("list_name") or "").strip() \
        or get_current_list_name()
    try:
        from modules.nsot.manifest import (PENDING_OVERDUE_SECONDS,
                                           PENDING_STALE_SECONDS,
                                           pending_devices)

        rows = pending_devices(_repo_for(list_name))
        return jsonify({"ok": True, "list": list_name, "pending": rows,
                        "counts": {"total": len(rows),
                                   "overdue": sum(1 for r in rows
                                                  if r["state"] != "in_flight")},
                        "thresholds": {"overdue": PENDING_OVERDUE_SECONDS,
                                       "stale": PENDING_STALE_SECONDS}})
    except Exception as exc:                   # noqa: BLE001
        log.exception("onboard: could not list pending devices")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/bootstrap/<hostname>", methods=["GET"])
def bootstrap(hostname):
    """The config a pending device was onboarded with. **A reveal.**

    It carries the one-time bootstrap credential in the clear, because a
    node cannot boot a masked password — so this is gated and audited
    exactly like `/golden/version/<host>?reveal=1`, and for the same reason.
    Requires a person by default: a service credential leaking would
    otherwise hand over the credential of every device still pending.

    Re-rendered rather than stored. See `bootstrap_artifact()` for why the
    config and the credential must share a lifetime.
    """
    from modules import identity as ident_mod, reveal_audit

    try:
        list_name = _target_list(request.args, "bootstrap")
    except NoTargetList as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    ident, refusal = ident_mod.require(request, action="reveal",
                                       operation="onboard_bootstrap")
    if refusal is not None:
        # A refused reveal returns no config at all — there is no masked
        # form worth returning, since a masked bootstrap config is the one
        # thing this artefact must never be.
        return jsonify({**refusal, "config": ""}), 403

    from modules.nsot.onboard import bootstrap_artifact

    out = bootstrap_artifact(_repo_for(list_name), hostname)
    if not out.get("ok"):
        return jsonify(out), 404

    reveal_audit.record(actor=ident.actor, kind=ident.kind,
                        what="bootstrap_config", target=hostname,
                        detail=f"list={list_name}", peer=ident.peer)
    return jsonify({**out, "revealed_by": ident.actor})


@bp.route("/verify/<hostname>", methods=["POST"])
def verify(hostname):
    """Phase 2: reach the device and promote it if it answered.

    Requires a person: promotion puts a device into the population the tool
    polls, backs up and deploys to, and reaching it uses a credential.
    """
    from modules import identity as ident_mod

    ident, refusal = ident_mod.require(request, action="confirm",
                                       operation="onboard_verify")
    if refusal is not None:
        return refusal

    data = request.get_json(silent=True) or {}
    try:
        list_name = _target_list(data, "verify")
    except NoTargetList as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    from modules.nsot.onboard import run_phase_two

    try:
        out = run_phase_two(
            _repo_for(list_name), hostname, list_name, actor=ident.actor,
            actor_kind=ident.kind)
    except Exception as exc:                   # noqa: BLE001
        log.exception("onboard: verify failed for %r", hostname)
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify(out), (200 if out.get("ok") else 409)


@bp.route("/abandon/<hostname>", methods=["POST"])
def abandon(hostname):
    """Undo an onboarding. Requires a person: it deletes from NetBox."""
    from modules import identity as ident_mod

    ident, refusal = ident_mod.require(request, action="confirm",
                                       operation="onboard_abandon")
    if refusal is not None:
        return refusal

    data = request.get_json(silent=True) or {}
    try:
        list_name = _target_list(data, "abandon")
    except NoTargetList as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    from modules.nsot.onboard import abandon_onboarding

    try:
        out = abandon_onboarding(_repo_for(list_name), hostname, list_name,
                                 actor=ident.actor,
                                 dry_run=bool(data.get("dry_run")))
    except Exception as exc:                   # noqa: BLE001
        log.exception("onboard: abandon failed for %r", hostname)
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify(out), (200 if out.get("ok") else 409)


@bp.route("/lists", methods=["GET"])
def onboard_lists():
    """The lists that can be onboarded into, and which one is active.

    Its own endpoint rather than reusing `/device_lists`, for the reason
    `/onboard/platforms` is: this blueprint answers `{"ok": ...}` and the
    wizard reads one shape. `is_current` is a **default for the select**,
    not a decision -- the operator chooses, and the request carries it.
    """
    try:
        from modules.device import get_device_lists

        lists = get_device_lists() or []
        return jsonify({
            "ok": True,
            "lists": [{"name": row.get("name", ""),
                       "slug": row.get("filename", ""),
                       "device_count": row.get("device_count", 0),
                       "is_current": bool(row.get("is_current"))}
                      for row in lists],
        })
    except Exception as exc:                   # noqa: BLE001
        log.exception("onboard: could not list device lists")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/plan", methods=["POST"])
def plan():
    """Build a plan and return it. **Creates nothing.**

    Called on every step change, so the review step shows a plan computed
    from what the operator has entered rather than a stale one — the same
    reason the deploy plan recomputes at apply.
    """
    from modules.nsot.onboard import build_plan

    data = request.get_json(silent=True) or {}
    try:
        list_name = _target_list(data, "plan")
    except NoTargetList as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    try:
        # A placeholder secret so the render is exercised. The real one-time
        # credential is minted at create time and never round-trips through
        # the browser.
        built = build_plan(**_plan_args(
            data, list_name, secret="PLACEHOLDER-not-the-real-credential"))
    except Exception as exc:                   # noqa: BLE001
        log.exception("onboard: plan failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({
        "ok": True,
        "plan": built.summary,
        # The review step shows the config that WILL be created. It carries
        # only the placeholder secret, by construction.
        "bootstrap_config": built.bootstrap_config,
        "host_vars": built.host_vars,
    })


@bp.route("/create", methods=["POST"])
def create():
    """The only step that creates anything.

    Requires a **person**: this puts a device into NetBox, a credential into
    the store and a commit into the repository. `approve` is the action kind —
    a human putting their name to something that changes state.
    """
    from modules import identity as ident_mod

    ident, refusal = ident_mod.require(request, action="approve",
                                       operation="onboard_device")
    if refusal:
        return jsonify(refusal), 403

    import os

    from modules.config import get_list_data_dir
    from modules.nsot.onboard import build_plan, real_steps, run_onboarding

    data = request.get_json(silent=True) or {}
    try:
        list_name = _target_list(data, "create")
    except NoTargetList as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    repo = os.path.join(get_list_data_dir(list_name), "config_repo")

    # REBUILT HERE, not carried from the review. The stores can change
    # between the screen and the confirm -- the same reason the deploy path
    # recomputes its program at apply rather than trusting what was shown.
    # secret="" -- the real one is minted by the credentials step.
    plan = build_plan(**_plan_args(data, list_name, secret=""))
    if not plan.onboardable:
        return jsonify({"ok": False, "error": "; ".join(plan.blocking_reasons),
                        "blocking_reasons": plan.blocking_reasons}), 409

    result = run_onboarding(plan, repo=repo,
                            **real_steps(repo, actor=ident.actor))
    return jsonify(result), (200 if result.get("ok") else 500)
