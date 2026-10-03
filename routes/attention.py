"""Needs attention (Stage 7.2): the landing list, every source in one shape.

A READ that reports. A source that cannot be read is a row in the answer,
never a failed request, so the page can say which source it could not read.
"""

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("attention", __name__, url_prefix="/attention")


@bp.route("", methods=["GET"])
def needs_attention():
    from modules.attention import needs_attention as build
    from modules.outbound import mask_payload

    # Rows quote their sources' own words (a job's error line, an approval's
    # description): masked on the way out, like every read that draws text
    # a store holds.
    page = build()
    # The badge is the v2 sidebar's count (/v2/attention-count draws it); today's panel
    # counts its own rows, stale sources included, and retires at cutover.
    page.pop("badge", None)
    return jsonify(mask_payload(page))


@bp.route("/acknowledge", methods=["POST"])
def acknowledge():
    """A person acknowledges ONE event row (an unplanned restart, a line authorised again
    and again) with a reason: recorded with who, how established and when, and the row
    leaves Needs attention. Body ``{"row", "event", "why"}``; the row is found again on
    the server, never taken from the browser (`attention.acknowledge`)."""
    from modules import identity
    from modules.attention import acknowledge as ack
    from modules.outbound import mask_payload

    data = request.get_json(silent=True) or {}
    actor = identity.request_actor()
    got = ack(str(data.get("row") or ""), str(data.get("event") or ""),
              str(data.get("why") or ""), by=actor,
              verified=identity.actor_verification(actor))
    # The row's words quote its source (a device's reason, an authorised line): masked.
    return jsonify(mask_payload(got)), (200 if got["ok"] else 409)
