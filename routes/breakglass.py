"""The break-glass export from the browser (7.3; `modules/breakglass_export.py`).

The most sensitive action in the tool: the file holds every device's
credential. A verified PERSON (the `reveal` gate), a reveal row before
anything leaves, the passphrase never logged, stored or echoed. The file is
built and verified in memory and returned in the response, beside the result
the one component draws; the host's disk never holds it.
"""

import base64
import logging

from flask import Blueprint, jsonify, request

from modules.identity import request_actor

log = logging.getLogger(__name__)

bp = Blueprint("breakglass", __name__, url_prefix="/breakglass")


@bp.route("/preview", methods=["POST"])
def preview():
    """What the record would hold: device names, the key's fingerprint and
    verdict, and the hash the confirm binds. Reveals no value."""
    from modules.breakglass_export import export_plan
    from modules.config import get_current_list_name
    from modules.outbound import mask_payload
    from modules.preview_confirm import breakglass_preview

    data = request.get_json(silent=True) or {}
    list_name = (data.get("list_name") or "").strip() or get_current_list_name()
    plan = export_plan(list_name)
    return jsonify(mask_payload({"ok": True, "list": list_name,
                                 "preview": breakglass_preview(plan, request=request)}))


@bp.route("/export", methods=["POST"])
def export():
    """Build, seal, verify, record, and return the record. The list is
    carried from the preview; the passphrase arrives twice and leaves in
    nothing this route writes or answers."""
    from modules import identity, reveal_audit
    from modules.breakglass_export import export_in_memory
    from modules.outbound import mask_payload
    from modules.preview_confirm import breakglass_result

    data = request.get_json(silent=True) or {}
    list_name = (data.get("list_name") or "").strip()
    if not list_name:
        return jsonify({"ok": False, "error": (
            "No list named: the record holds one list's credentials, so the list comes from "
            "the preview that was confirmed, never from whichever list is active. Nothing "
            "was built.")}), 400
    confirmed = (data.get("hash") or "").strip()
    if not confirmed:
        return jsonify({"ok": False, "error": "Nothing confirmed: nothing was built"}), 400
    actor = request_actor()
    ident = identity.identify(request)

    def record_reveal(sha256, count):
        entry = reveal_audit.record(
            actor=actor, kind=ident.kind, what="breakglass_record", target=list_name,
            detail=f"{count} device(s), sha256 {sha256}", peer=ident.peer,
            extra={"device_count": count, "sha256": sha256})
        return bool(entry.get("recorded"))

    out = export_in_memory(list_name, data.get("passphrase") or "", data.get("confirm") or "",
                           confirmed, actor=actor, record_reveal=record_reveal)
    blob = out.pop("blob", None)
    result = mask_payload({"ok": True, "list": list_name,
                           "result": breakglass_result(out, list_name, actor)})
    if blob is not None:
        # Attached AFTER the mask: the sealed bytes are ciphertext the person
        # asked for, never a value to redact (C136's rule for a capability).
        result.update(filename=out["filename"], sha256=out["sha256"],
                      file=base64.b64encode(blob).decode("ascii"))
        log.info("breakglass: %s exported %s (%d device(s)) to a browser, sha256 %s",
                 actor, list_name, out["verified"]["devices"], out["sha256"])
    else:
        log.warning("breakglass: an export of %s by %s was refused at %s", list_name, actor,
                    out.get("stage"))
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    return response
