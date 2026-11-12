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
    leaves Needs attention. Body ``{"row", "event", "why"}``, and on a band row ``hours`` for a
    planned quiet period (C2316); the row is found again on
    the server, never taken from the browser (`attention.acknowledge`)."""
    from modules import identity
    from modules.attention import acknowledge as ack
    from modules.outbound import mask_payload

    data = request.get_json(silent=True) or {}
    actor = identity.request_actor()
    got = ack(str(data.get("row") or ""), str(data.get("event") or ""),
              str(data.get("why") or ""), by=actor,
              verified=identity.actor_verification(actor),
              disposition=str(data.get("disposition") or ""),
              hours=str(data.get("hours") or ""))
    # The row's words quote its source (a device's reason, an authorised line): masked.
    return jsonify(mask_payload(got)), (200 if got["ok"] else 409)


def recheck():
    """The handler of Run the check again, served at `/v2/attention/recheck` (`v2.attention_recheck`,
    a press on the person's own page). The operator's overnight item 9, 2026-11-12: the reader a row's
    reading came from (form ``reader``, a registered reader's name, never a command) runs once
    now through its own run path (`reader_job.request_run`, recorded as this person's request)
    on its own thread. Answers at once, the control drawn again in place (form ``row``, the
    row it is on, keeps its id): busy (202) on a run started, or on a run in progress the person
    did not start, which it waits for; "Checked just now" (200) on a read within the spacing
    the person did not start, in the row's words; or the refusal naming both operands (409).
    The row is drawn again when the run's value is assembled (modules/recheck.py, C3360,
    C3361)."""
    from flask import render_template

    from modules import identity
    from modules import recheck as R
    from routes.device_v2 import _strict

    who = identity.viewer()
    row = str(request.form.get("row") or "")
    got = R.ask(str(request.form.get("reader") or ""),
                who.actor if who.is_identified else "")
    if got["ok"] and got.get("checked"):
        rc = R.checked_answer(got, row)
        return _strict(render_template("v2/_attention_recheck.html", reader=got["reader"],
                                       rc=rc, refused=None, row=row),
                       202 if rc.get("busy") else 200)
    if got["ok"]:
        rc = {"busy": True, "since": got["since"]}
        if got.get("joined"):
            rc["cause"] = got["cause"]
        return _strict(render_template("v2/_attention_recheck.html", reader=got["reader"],
                                       rc=rc, refused=None, row=row), 202)
    return _strict(render_template("v2/_attention_recheck.html",
                                   reader=got["reader"] or "unknown", rc=None, refused=got,
                                   row=row),
                   409)
