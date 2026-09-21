"""Per-list git remote: adopt, verify, preview, acknowledge, push.

Publishing a network's configuration history — including the credentials in
it — is gated on ``publish_remote``: a verified PERSON, by default. Its own
operation kind rather than ``confirm``, so the audit reads "published" and so
a service grant written for some other operation cannot reach this one.

Read-only endpoints (status, verify, preview) are not gated. Verification and
the preview exist to be read *before* deciding, and a gate on them would mean
asking someone to authorise the thing they are trying to evaluate.
"""

import logging

from flask import Blueprint, jsonify, request

from modules import identity
from modules.nsot import remote as R

log = logging.getLogger(__name__)
bp = Blueprint("remote", __name__, url_prefix="/remote")


def _list_name() -> str:
    from modules.config import get_current_list_name

    payload = request.get_json(silent=True) or {}
    return payload.get("list") or request.args.get("list") \
        or get_current_list_name()


@bp.route("/status", methods=["GET"])
def status():
    """What this list's remote is, and whether it may be pushed to."""
    list_name = _list_name()
    config = R.load_remote(list_name)
    if not config:
        return jsonify({"ok": True, "list": list_name, "configured": False})

    covers = R.acknowledgement_covers(list_name)
    return jsonify({
        "ok": True, "list": list_name, "configured": True,
        "owner_repo": f"{config['owner']}/{config['repo']}",
        "ssh_alias": config["ssh_alias"], "branch": config.get("branch"),
        "managed_by_nmas": config.get("managed_by_nmas"),
        "verified_at": config.get("verified_at"),
        "auto_push": config.get("auto_push"),
        "last_push": config.get("last_push"),
        "acknowledged": config.get("acknowledged_secrets"),
        "acknowledgement_covers": covers,
    })


@bp.route("/adopt", methods=["POST"])
def adopt():
    """Record an existing, hand-made setup. Never edits ~/.ssh/config."""
    ident, refusal = identity.require(request, "publish_remote")
    if refusal:
        return refusal
    payload = request.get_json(silent=True) or {}
    missing = [k for k in ("ssh_alias", "owner", "repo") if not payload.get(k)]
    if missing:
        return jsonify({"ok": False, "error": f"missing: {', '.join(missing)}"}), 400

    out = R.adopt(_list_name(), ssh_alias=payload["ssh_alias"],
                  owner=payload["owner"], repo=payload["repo"],
                  branch=payload.get("branch", "main"),
                  key_path=payload.get("key_path", ""), actor=ident.actor)
    return jsonify(out), (200 if out["ok"] else 409)


@bp.route("/verify", methods=["POST"])
def verify():
    """All five pre-push checks. Not gated: this is how you decide."""
    out = R.verify(_list_name())
    return jsonify(out)


@bp.route("/preview", methods=["GET"])
def preview():
    """What a first push would publish. Counts and modes, never values."""
    list_name = _list_name()
    out = R.first_push_preview(list_name)
    if out.get("ok"):
        out["gated"] = R.gated_summary(out["secrets"])
    return jsonify(out)


@bp.route("/acknowledge", methods=["POST"])
def acknowledge():
    """A person accepts publishing the gated material.

    The typed confirmation must name the gated kinds, so that acknowledging
    is an act of reading rather than of clicking. It is checked against what
    the scan says NOW, not against what the client was shown — a stale page
    must not be able to acknowledge something that has since grown.
    """
    ident, refusal = identity.require(request, "publish_remote")
    if refusal:
        return refusal

    list_name = _list_name()
    payload = request.get_json(silent=True) or {}
    typed = (payload.get("typed") or "").strip()

    out = R.first_push_preview(list_name)
    if not out.get("ok"):
        return jsonify(out), 400
    gated = R.gated_summary(out["secrets"])
    if not gated["kinds"]:
        return jsonify({"ok": False,
                        "error": "nothing requires acknowledgement"}), 400

    expected = " ".join(gated["kinds"])
    if typed != expected:
        return jsonify({
            "ok": False,
            "error": "the typed acknowledgement must name the gated kinds",
            "expected": expected,
            "counts": gated["counts"],
        }), 400

    result = R.acknowledge(list_name, actor=ident.actor,
                           actor_kind=ident.kind)
    log.info("remote: publish acknowledged for '%s' by %s (%s)",
             list_name, ident.actor, ident.kind)
    return jsonify(result), (200 if result["ok"] else 400)


@bp.route("/push", methods=["POST"])
def push():
    """Publish. main + --follow-tags, then notes if any note ref exists."""
    ident, refusal = identity.require(request, "publish_remote")
    if refusal:
        return refusal

    list_name = _list_name()
    out = R.push(list_name, actor=ident.actor)
    if not out["ok"]:
        return jsonify(out), 409
    out["auto_push_offered"] = True
    return jsonify(out)


@bp.route("/auto-push", methods=["POST"])
def auto_push():
    """Enable auto-push. Offered only after a successful push."""
    ident, refusal = identity.require(request, "publish_remote")
    if refusal:
        return refusal
    out = R.enable_auto_push(_list_name(), actor=ident.actor)
    return jsonify(out), (200 if out["ok"] else 409)
