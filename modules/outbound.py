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


#: Keys whose string value IS a secret, in a structured payload. Exact names.
SECRET_FIELDS = frozenset({"community", "password", "secret", "token", "api_token",
                           "auth_key", "priv_key", "key_string"})


def mask_payload(obj):
    """A JSON-shaped response with every string through `redact_text`.

    For the PREVIEWS (register C77): `/deploy/plan` and
    `/golden/restore/preview` returned stored and rendered config lines
    verbatim (the program, residue, what a line replaces), so a planted
    community came back in both, as residue and as a line the program adds.
    B11's sweep planted every store and swept GETs, and these are POSTs: a
    population defined by the method again, where the property is "returns
    stored config" (the B16 lesson, one more member).

    Masked on the way OUT, after every hash is computed from the truthful
    program: the confirm is bound to what is SENT, and the apply recomputes
    it from the truthful render. The operator reads `<redacted:...>` in a
    secret's slot and every other byte as sent. The authorisations the client
    echoes back are dangerous lines, and no dangerous form has a secret slot,
    so masking cannot change what they match.

    **A secret can also arrive as a plain VALUE, not in config syntax**
    (C77's sweep, 2026-09-27; C55's shape). The NetBox import preview carries
    `snmp.communities[].community`, a structured copy of a community, and
    positional redaction cannot see a bare value. So a string under a key in
    `SECRET_FIELDS` is masked by its key. The match is exact: `secret_refs`,
    `password_set` and the like are names and flags, never values.
    """
    from modules import redact

    if isinstance(obj, str):
        return redact.redact_text(obj)
    if isinstance(obj, dict):
        return {k: (f"<redacted:{k}>" if k in SECRET_FIELDS and isinstance(v, str) and v
                    else mask_payload(v))
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask_payload(v) for v in obj]
    return obj
