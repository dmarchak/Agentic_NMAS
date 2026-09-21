"""Identity diagnostics — read-only.

Exists to answer one question end to end: **does the tunnel actually forward
``Cf-Access-Jwt-Assertion``, and does this app verify it?** Every other check
in ``modules/identity.py`` is unit-tested against a throwaway key pair, which
proves the logic and proves nothing about the deployment.

Three deliberate choices:

* **Not gated by identity.** A diagnostic that refuses unverified callers is
  useless precisely when it is needed — when identity is not working. It
  reports the unauthenticated state instead of hiding behind it.
* **No configuration is echoed.** Not the team domain, not the AUD tag. It
  reports *whether* Access is configured, never with what. A diagnostic is a
  natural place for a config dump to creep in, and that would hand an
  unauthenticated caller the values the check depends on.
* **The email goes to the requester and nowhere else.** It is returned in the
  response body — to the person who just proved they are that person — and is
  never logged. ``modules/identity`` already logs presence and outcome only.
"""

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("identity", __name__, url_prefix="/identity")


def _redaction_health() -> dict:
    """Is outbound redaction working, and is every log handler covered?"""
    try:
        from modules import redact
        return redact.health()
    except Exception as exc:                  # noqa: BLE001
        log.error("identity: could not read redaction health: %s", exc)
        return {"healthy": False, "error": "redaction health unavailable"}


@bp.route("/status", methods=["GET"])
def status():
    """Who does this app think is making *this* request?"""
    from modules import identity as ident_mod

    ident = ident_mod.identify(request)

    return jsonify({
        "ok": True,
        # The end-to-end question: did the assertion survive the tunnel?
        "token_present": ident.header_present,
        "verified": ident.verified,
        "peer": ident.peer,
        "peer_trusted": ident.peer_trusted,
        "is_identified": ident.is_identified,
        "outcome": ident.outcome,
        "reason": ident.reason,
        # To the requester only. Empty unless an assertion verified.
        "email": ident.email,
        "actor": ident.actor,
        # person | service | "". A service token carries no email, so an
        # empty `email` beside a set `actor` is the normal service shape
        # rather than a fault.
        "kind": ident.kind,
        "service_id": ident.service_id,
        # How the audit trail will name this caller. For a service that is its
        # label when one is configured, so the diagnostic shows the same string
        # the trail will — an unlabelled token reads as 32 hex characters, and
        # discovering that later, in a log, is the wrong moment.
        "audit_name": (ident_mod.service_label(ident.service_id)
                       if ident.kind == "service" else ident.actor),
        # Presence only — this is how you tell "the tunnel forwards the email
        # header but not the assertion" from "it forwards neither", which are
        # different deployment problems with different fixes.
        "headers_seen": {
            ident_mod.JWT_HEADER: bool(request.headers.get(ident_mod.JWT_HEADER)),
            ident_mod.EMAIL_HEADER: bool(request.headers.get(ident_mod.EMAIL_HEADER)),
        },
        # Outbound redaction fails OPEN, which stays defensible only while
        # the failure is visible. A log line saying "the log is unreliable" is
        # written in the medium that just became unreliable.
        "redaction": _redaction_health(),
        # Whether, not with what.
        "access_configured": ident_mod.is_configured(),
        "trusted_peers_configured": bool(ident_mod.trusted_peers()),
        # What THIS caller may do — not which gates are switched on.
        #
        # This field used to report the latter, and it was misread within
        # minutes of first being shown: `gates: {reveal: true}` looks like
        # permission and means the opposite, that the gate is *closed*. A
        # diagnostic whose most prominent field inverts on the reader is worse
        # than one that omits it. Computed through `identity.may()` — the same
        # function the gates use — so the answer here cannot drift from the
        # answer at the gate.
        "may": {
            action: dict(zip(("allowed", "reason"),
                             ident_mod.may(ident, action)))
            for action in ident_mod.GATED_ACTIONS
        },
    })
