"""Needs attention (Stage 7.2): a person acknowledges one of its rows.

The list itself is v2's (`/v2/` and `/v2/attention`, `routes/v2.py`, over
`modules.attention.needs_attention`). Today's JSON read of it (GET /attention), which only
today's index panel called, left with that panel at 7.8 (2026-10-17, P7-27; restore point tag
`pre-remove/v1-pages`).
"""

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("attention", __name__, url_prefix="/attention")


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
