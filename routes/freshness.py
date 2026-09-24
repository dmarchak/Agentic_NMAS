"""routes/freshness.py — is Oxidized's copy of each device the approved one?

Three endpoints for one measurement (:mod:`modules.nsot.freshness`):

* ``POST /freshness/gate`` — the sanitiser's pre-write check. It posts the raw
  configs it is about to write **from**, and gets a per-device verdict back.
  The last moment before an unapproved state becomes durable.
* ``GET  /freshness/report`` — the Monitoring signal. Same comparison, read
  through the Oxidized client, continuous and cheap. A report; it refuses
  nothing.
* ``POST /freshness/authorise`` — the way through the gate, for one
  divergence, recorded with who and why.

**Every config line that leaves here is redacted.** A diff carries the same
secrets as either config on its `-`/`+` lines, which is why the golden routes
send both through one helper rather than each remembering; the same applies to
a difference list. There is no ``?reveal=1`` here at all — nothing about this
question needs the value, only that the line differs.
"""

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("freshness", __name__, url_prefix="/freshness")


def _list_name() -> str:
    """The list being asked about.

    **A read may derive the active list; a write may not.** Every endpoint
    here is a read or an authorisation *for a named device in a named list*,
    and the authorisation carries its list explicitly.
    """
    from modules.device import get_current_device_list

    return (request.args.get("list")
            or (request.get_json(silent=True) or {}).get("list_name")
            or get_current_device_list()[0])


def _redacted(report: dict) -> dict:
    """The report with every config line masked, in place of the raw lines."""
    from modules.redact import redact_text

    for row in report.get("devices", []):
        for key in ("only_left", "only_right"):
            row[key] = [redact_text(line) for line in row.get(key, [])]
        if row.get("reason"):
            row["reason"] = redact_text(row["reason"])
    report["errors"] = [redact_text(e) for e in report.get("errors", [])]
    return report


@bp.route("/gate", methods=["POST"])
def gate():
    """Per-device verdicts for the configs the caller is about to write.

    The caller supplies the **raw** Oxidized configs — the exact bytes in its
    hand. Not the sanitised output: that is a derived artefact whose own
    header, re-injected ``no shutdown`` lines and appended ``crypto key``
    lines would read as drift for ever. And not a re-fetch here either, which
    would compare a copy the caller is not writing.

    HTTP status carries the answer for a shell script: **200** nothing blocks,
    **409** at least one device blocks, **400/500** the comparison could not
    run. Three outcomes, three codes — a missing baseline and a failed
    teardown sharing exit 1 is a mistake this project has already made once.
    """
    from modules.nsot import freshness

    body = request.get_json(silent=True) or {}
    configs = body.get("configs")
    if not isinstance(configs, dict) or not configs:
        return jsonify({"ok": False, "error": (
            "no configs supplied. An empty gate request would pass "
            "vacuously, which is the one answer this endpoint must not "
            "give")}), 400

    list_name = _list_name()
    try:
        report = freshness.check(list_name, supplied=configs)
    except Exception as exc:                   # noqa: BLE001
        log.exception("freshness: gate failed for %r", list_name)
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    if not report.get("ok"):
        return jsonify(_redacted(report)), 500

    report["summary"] = freshness.gate_summary(report)
    status = 409 if report.get("blocked") else 200
    return jsonify(_redacted(report)), status


@bp.route("/report", methods=["GET"])
def report():
    """The Monitoring signal: is the fleet diverging from what was approved?

    A **report**, not a gate. Its value is timing — the gate discovers
    divergence when somebody is already preparing a redeploy; this discovers
    it while the person who caused it still remembers what they did.
    """
    from modules.nsot import freshness

    list_name = _list_name()
    try:
        result = freshness.check(list_name)
    except Exception as exc:                   # noqa: BLE001
        log.exception("freshness: report failed for %r", list_name)
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    if not result.get("ok"):
        return jsonify(_redacted(result)), 500
    result["summary"] = freshness.gate_summary(result)
    return jsonify(_redacted(result))


@bp.route("/authorise", methods=["POST"])
def authorise():
    """Deliberately allow one divergence to be written.

    **A person, not a service.** Writing an unapproved state into what a
    device boots with is the same kind of act as approving a deploy: somebody
    is meant to have read exactly what it covers, and the fingerprint is only
    worth something because they did.
    """
    from modules import identity as ident_mod
    from modules.nsot import freshness

    body = request.get_json(silent=True) or {}
    hostname = (body.get("device") or "").strip()
    fingerprint = (body.get("fingerprint") or "").strip()
    reason = (body.get("reason") or "").strip()
    list_name = _list_name()

    ident, refusal = ident_mod.require(
        request, action="approve",
        operation=f"freshness authorisation for {hostname or '?'}")
    if refusal:
        return jsonify(refusal), 403

    if not hostname or not fingerprint:
        return jsonify({"ok": False, "error": (
            "a device and the fingerprint of the divergence being authorised "
            "are both required — an authorisation not tied to what differs "
            "would cover the next difference too")}), 400

    result = freshness.authorise(list_name, hostname, fingerprint,
                                 actor=ident.actor, reason=reason)
    return jsonify(result), (200 if result.get("ok") else 400)


@bp.route("/authorisations", methods=["GET"])
def authorisation_log():
    """Every authorisation, so a withdrawal is visible rather than implied."""
    from modules.nsot import freshness

    list_name = _list_name()
    include = request.args.get("all") == "1"
    return jsonify({"ok": True, "list": list_name,
                    "authorisations": freshness.authorisations(
                        list_name, include_expired=include)})
