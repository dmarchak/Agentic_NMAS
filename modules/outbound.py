"""Config text on its way out: masked unless a PERSON reveals it, recorded.

One pattern for every route that returns device configuration (register
C56): the golden version and diff routes had it; the backup download
returned a stored backup raw to anyone who reached the URL. The operator's
reading: a backup holding raw config SHOULD require a person and leave a
record, and matching the golden path makes one pattern rather than two. So
the golden routes' helper moved here and both call it.

Masked is the default, because the caller who wants to read a config or a
diff is the common case and none of them need the community to do it. The
mask is `redact_text`, positional first, so a six-character community is
covered though it is under the value floor. A refused reveal returns the
MASKED text, never the secret beside an error.
"""

import logging

log = logging.getLogger(__name__)


def wants_reveal(request) -> bool:
    return (request.args.get("reveal", "") or "").lower() in ("1", "true", "yes")


def config_text(request, text: str, *, what: str, target: str, detail: str = ""):
    """``(payload, status)``: ``{"ok", "masked", "text"}``, masked unless the
    request asks for ``?reveal=1`` and a person is behind it, in which case
    the reveal is recorded in `data/reveal_audit.jsonl` first."""
    from modules import identity as ident_mod
    from modules import redact, reveal_audit

    if not wants_reveal(request):
        return {"ok": True, "masked": True, "text": redact.redact_text(text)}, 200

    ident, refusal = ident_mod.require(request, "reveal", operation=what)
    if refusal is not None:
        log.warning("outbound: reveal of %s/%s refused (%s)", what, target,
                    refusal.get("outcome"))
        return {**refusal, "masked": True, "text": redact.redact_text(text)}, 403

    reveal_audit.record(actor=ident.actor, kind=ident.kind, what=what,
                        target=target, detail=detail, peer=ident.peer,
                        extra={"audit_name": ident_mod.service_label(ident.service_id)
                               if ident.kind == "service" else ident.actor})
    return {"ok": True, "masked": False, "text": text,
            "revealed_by": ident.actor}, 200
