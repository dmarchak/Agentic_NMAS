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


def _target_list(data) -> str:
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
        raise NoTargetList(
            "no target list was chosen. The wizard sends the list it is "
            "onboarding into rather than inheriting whichever list happens "
            "to be active, because onboarding into the wrong one leaves a "
            "commit and a NetBox object behind.")
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
        list_name = _target_list(data)
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
        list_name = _target_list(data)
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
