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


def _active_list(payload=None) -> str:
    from modules.config import get_current_list_name

    name = (payload or {}).get("list_name") or request.args.get("list_name") or ""
    return name.strip() or get_current_list_name()


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


@bp.route("/plan", methods=["POST"])
def plan():
    """Build a plan and return it. **Creates nothing.**

    Called on every step change, so the review step shows a plan computed
    from what the operator has entered rather than a stale one — the same
    reason the deploy plan recomputes at apply.
    """
    from modules.nsot.onboard import build_plan

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
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
    list_name = _active_list(data)
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
