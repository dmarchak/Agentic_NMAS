"""Config text on its way out: masked, or revealed to a PERSON and recorded.

Masked is the default, because the caller who wants to read a config or a
diff is the common case and none of them need the community to do it. The
mask is `redact_text`, positional first, so a six-character community is
covered though it is under the value floor. A refused reveal shows nothing
unmasked, never the secret beside an error.

The `?reveal=1` helper that served today's golden version and diff routes and, before them,
the backup download (`config_text`, `wants_reveal`; register C56) left with its last routes at
7.8 (2026-10-17, P7-27). Each v2 reveal asks `identity.require` for a person and writes the
reveal record first (the device page's golden version, the bootstrap config, a log line).
What stays here: the no-store header every reveal and secret-carrying response sends, and
`mask_payload`, the mask on every JSON payload on its way out.
"""

import logging

log = logging.getLogger(__name__)


#: What every response carrying an unmasked secret, a credential or a device's configuration
#: says to a browser and to every cache on the way (C840): keep no copy, and change nothing.
NO_STORE = "no-store, no-transform"


def no_store(view):
    """A view whose every response says ``Cache-Control: no-store`` (C840): the reveals and
    every route that returns a secret, its refusals included. app.py's header hook sets a
    default only where a route set none, so this stands. ``view.no_store`` marks it, which
    tests/test_secret_responses_no_store.py reads for every reveal-gated endpoint."""
    import functools

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        from flask import make_response
        response = make_response(view(*args, **kwargs))
        response.headers["Cache-Control"] = NO_STORE
        return response

    wrapped.no_store = True
    return wrapped


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
