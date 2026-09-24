"""modules/identity.py

Who is making this request.

The app has no auth layer of its own — it sits behind a Cloudflare tunnel, and
identity comes from in front of it. That makes *what counts as evidence* the
whole design question, and it has exactly one answer:

**The email header is not evidence.** ``Cf-Access-Authenticated-User-Email`` is
an ordinary HTTP header. Anything that can reach the port can set it to
anything. Measured before the firewall was closed: a laptop on the LAN sent
``Cf-Access-Authenticated-User-Email: forged@example.com`` and got HTTP 200.

What is evidence is ``Cf-Access-Jwt-Assertion``: a signed assertion verified
against the team's public keys, with ``aud`` and ``iss`` checked. The email is
then read from the **verified claims**, never from a header. Per Cloudflare:
*"You should validate the token with your public key to ensure that the request
came from Access and not a malicious third party."* Their guidance also prefers
the header over the ``CF_Authorization`` cookie, "since the cookie is not
guaranteed to be passed".

Two independent conditions, neither sufficient alone:

1. a **valid signed assertion** for this application, and
2. a **raw socket peer** on the trusted list.

(2) is not redundant. A valid assertion captured from a browser session and
replayed from elsewhere on the LAN satisfies (1). It is also the condition that
survives a firewall rule being edited later — the same shape as
``netbox_allow_writes`` plus a one-shot token.

**Nothing here logs a value.** Not the email, not the token, not a claim. The
log records whether a header was present and how validation came out, because
an audit trail that leaks the identity it is recording has traded one problem
for another.
"""

import logging
import threading
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

JWT_HEADER = "Cf-Access-Jwt-Assertion"
EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"

#: Recorded as the actor when no verified identity accompanied the request.
#: A NAME, not an empty string: an audit row whose actor is "" reads as a bug,
#: and the reader cannot tell "nobody was identified" from "we forgot to look".
UNAUTHENTICATED = "unauthenticated"

_jwks_lock = threading.Lock()
_jwks_client = None
_jwks_for = ("", 0.0)


@dataclass(frozen=True)
class Identity:
    """The outcome of asking who is making a request."""

    actor: str = UNAUTHENTICATED
    email: str = ""
    #: ``person`` | ``service`` | ``""``. Cloudflare issues the same *shape* of
    #: assertion for both, so this is derived from the claims — see
    #: :func:`_actor_from_claims`.
    kind: str = ""
    #: The service token's Client ID (its ``common_name``), for a service only.
    service_id: str = ""
    verified: bool = False
    #: Machine-readable outcome, safe to log: ok | no_header | invalid_token |
    #: wrong_audience | expired | untrusted_peer | not_configured | verifier_unavailable
    outcome: str = "no_header"
    reason: str = ""
    peer: str = ""
    peer_trusted: bool = False
    header_present: bool = False

    @property
    def is_identified(self) -> bool:
        return self.verified and self.peer_trusted

    def audit(self) -> dict:
        """What an audit row should carry. Never the token.

        ``kind`` is recorded alongside the actor because "a person approved
        this" and "a script approved this" are different facts about a change,
        and an audit trail that cannot distinguish them cannot answer the
        question it exists to answer.
        """
        row = {"actor": self.actor, "kind": self.kind,
               "verified": self.verified, "outcome": self.outcome,
               "peer": self.peer, "peer_trusted": self.peer_trusted}
        if self.kind == "service" and self.service_id:
            row["service"] = service_label(self.service_id)
        return row


#: Service actors are prefixed so no reader can mistake a Client ID for a
#: person. `e367826f93b8….access` and `dustin@example.com` are both opaque
#: strings in a log line; only one of them is a human being.
SERVICE_ACTOR_PREFIX = "service:"


def _actor_from_claims(claims: dict) -> tuple:
    """``(actor, email, kind, service_id)`` from verified claims.

    Cloudflare issues the **same shape** of assertion for a person and for a
    service token — both carry ``type: "app"``, so ``type`` is not the
    discriminator it looks like. What differs is which identity claim is
    present:

    * person  — ``email`` set, ``sub`` a user UUID, plus ``identity_nonce``
    * service — ``common_name`` set (the token's Client ID), ``sub`` empty,
      and **no** ``email`` at all

    Handled explicitly rather than by ``email or common_name``, which collapsed
    both into one field and would have recorded a service token's Client ID in
    a column every reader takes to be a person's address.
    """
    email = (claims.get("email") or "").strip()
    common_name = (claims.get("common_name") or "").strip()

    if email:
        return email, email, "person", ""
    if common_name:
        return f"{SERVICE_ACTOR_PREFIX}{common_name}", "", "service", common_name
    return "", "", "", ""


def service_label(client_id: str) -> str:
    """A friendly name for a service token's Client ID, or the ID itself.

    **A label, never a grant.** Identity comes from the verified assertion;
    this only decides how the audit row reads. An unlabelled token
    authenticates exactly as well — it just reads as 32 hex characters, which
    is how a legitimate token and a leaked one come to look identical to
    whoever is reading the trail later.
    """
    labels = _setting("cf_access_service_labels", {}) or {}
    return labels.get(client_id, "") or client_id


def _setting(key, default=None):
    from modules.settings_schema import get_setting
    return get_setting(key, default)


def trusted_peers() -> list:
    raw = (_setting("cf_access_trusted_peers", "") or "").strip()
    return [p.strip() for p in raw.split(",") if p.strip()]


#: Every Access value that must be set before an assertion means anything.
#:
#: **`cf_access_trusted_peers` is in here, and that is the fix.**
#: `identify()` computed `peer_trusted = (not allowed) or (peer in allowed)`,
#: so an EMPTY allowlist trusted **every** peer — a blank silently removing
#: the check this file describes as *"the layer that survives a firewall
#: rule being edited later"*. Two independent conditions, one of which
#: switched itself off when unset.
#:
#: It was masked here by the other two values also being blank, so
#: `is_configured()` refused first and the composite failed closed. That is
#: the dangerous kind of safe: restoring the team domain and the AUD
#: **without** the peer list would have turned verification back on with the
#: peer check silently off — strictly worse than refusing everything,
#: because an assertion captured from a browser replays from anywhere on the
#: LAN.
REQUIRED_ACCESS_VALUES = ("cf_access_team_domain", "cf_access_aud",
                          "cf_access_trusted_peers")


def missing_access_values() -> list:
    """Which of :data:`REQUIRED_ACCESS_VALUES` are unset. Named, not counted.

    "Access is not configured" sends an operator to read JSON; "the trusted
    peer list is unset" tells them what to do.
    """
    return [k for k in REQUIRED_ACCESS_VALUES
            if not (_setting(k, "") or "").strip()]


def is_configured() -> bool:
    """All three, not two.

    An unset peer list used to leave `is_configured()` true while the peer
    check accepted everything. Requiring it means the check can no longer be
    disabled by omission — the failure mode is a refusal that names the
    missing value, which is recoverable, rather than a gate that quietly
    stopped being one.
    """
    return not missing_access_values()


def certs_url(team_domain: str = "") -> str:
    team = (team_domain or _setting("cf_access_team_domain", "") or "").strip()
    team = team.replace("https://", "").replace("http://", "").strip("/")
    return f"https://{team}/cdn-cgi/access/certs" if team else ""


def _get_jwks_client():
    """A cached ``PyJWKClient``, rebuilt when the team domain changes.

    The cache has a TTL rather than being permanent, so a key rotation is
    picked up — and it is generous, so a brief outage of the certs endpoint
    does not lock an operator out of a tool that is otherwise entirely local.
    """
    global _jwks_client, _jwks_for

    url = certs_url()
    if not url:
        return None
    ttl = int(_setting("cf_access_jwks_ttl", 3600) or 3600)

    with _jwks_lock:
        cached_url, built_at = _jwks_for
        if _jwks_client is not None and cached_url == url and (
                ttl <= 0 or time.time() - built_at < ttl):
            return _jwks_client
        try:
            from jwt import PyJWKClient
        except ImportError:
            log.error("identity: PyJWT is not installed — assertions cannot be "
                      "verified and every request will be unauthenticated")
            return None
        _jwks_client = PyJWKClient(url, cache_keys=True,
                                   lifespan=max(ttl, 300), timeout=10)
        _jwks_for = (url, time.time())
        return _jwks_client


def peer_address(request) -> str:
    """The **raw socket peer**, never a forwarded header.

    ``REMOTE_ADDR`` is set by the WSGI server from the accepted socket. It is
    only trustworthy while nothing rewrites it, which is why
    ``X-Forwarded-For`` is not consulted here and ``ProxyFix`` is not installed
    — both pinned by tests. A proxy header is written by whoever is talking to
    us, which is precisely the thing being checked.
    """
    return (request.environ.get("REMOTE_ADDR") or "").strip()


def identify(request) -> Identity:
    """Who is making *request*. Never raises; never logs a value."""
    peer = peer_address(request)
    allowed = trusted_peers()
    # NO EMPTY-MEANS-EVERYONE. An unset allowlist is not a permissive one;
    # `is_configured()` refuses before this matters, so an install without
    # peers gets a named refusal rather than a check that passed vacuously.
    peer_trusted = bool(allowed) and peer in allowed
    token = request.headers.get(JWT_HEADER, "")
    present = bool(token)

    def _no(outcome, reason):
        log.info("identity: %s (header_present=%s peer_trusted=%s)",
                 outcome, present, peer_trusted)
        return Identity(outcome=outcome, reason=reason, peer=peer,
                        peer_trusted=peer_trusted, header_present=present)

    if not is_configured():
        return _no("not_configured",
                   "Cloudflare Access is not configured — unset: "
                   + ", ".join(missing_access_values()))
    if not present:
        return _no("no_header",
                   f"the request carried no {JWT_HEADER} header")

    client = _get_jwks_client()
    if client is None:
        return _no("verifier_unavailable",
                   "the Access signing keys could not be loaded")

    aud = (_setting("cf_access_aud", "") or "").strip()
    team = (_setting("cf_access_team_domain", "") or "").strip()
    issuer = f"https://{team}".rstrip("/")

    try:
        import jwt

        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256"],
            audience=aud, issuer=issuer,
            options={"require": ["exp", "iat", "aud", "iss"]},
            leeway=30,
        )
    except Exception as exc:                  # noqa: BLE001
        # The class name is safe to log; the message can quote token content.
        outcome = {"ExpiredSignatureError": "expired",
                   "InvalidAudienceError": "wrong_audience",
                   "InvalidIssuerError": "wrong_issuer",
                   }.get(type(exc).__name__, "invalid_token")

        if type(exc).__name__ == "PyJWKClientError":
            # PyJWKClient raises the SAME error for "could not fetch the key
            # set" and "the token's kid is not in the key set I fetched". Those
            # are opposite diagnoses: one is our connectivity, the other is a
            # bad token. Found live — a forged token reported
            # `verifier_unavailable`, and the refusal then told the operator to
            # check their configuration while someone was presenting a forgery.
            # Ask the verifier whether IT is healthy, and let that decide.
            outcome = "invalid_token"
            try:
                client.get_jwk_set()
            except Exception:                 # noqa: BLE001
                outcome = "verifier_unavailable"
        log.warning("identity: assertion rejected (%s) peer_trusted=%s",
                    outcome, peer_trusted)
        return Identity(outcome=outcome, peer=peer, peer_trusted=peer_trusted,
                        header_present=True,
                        reason=f"the Access assertion was rejected ({outcome})")

    actor, email, kind, service_id = _actor_from_claims(claims)
    if not actor:
        return Identity(outcome="invalid_token", peer=peer,
                        peer_trusted=peer_trusted, header_present=True,
                        reason=("the assertion carried neither an email nor a "
                                "common_name, so it names nobody"))

    if not peer_trusted:
        log.warning("identity: valid %s assertion from an untrusted peer %s",
                    kind, peer)
        return Identity(actor=UNAUTHENTICATED, email="", kind="", verified=True,
                        outcome="untrusted_peer", peer=peer,
                        peer_trusted=False, header_present=True,
                        reason=(f"the assertion is valid but arrived from {peer}, "
                                "which is not a trusted peer — a captured "
                                "assertion replayed from elsewhere looks like "
                                "this"))

    # kind is safe to log; the actor is not.
    log.info("identity: verified (outcome=ok kind=%s peer=%s)", kind, peer)
    return Identity(actor=actor, email=email, kind=kind, service_id=service_id,
                    verified=True, outcome="ok", peer=peer, peer_trusted=True,
                    header_present=True)


def service_may(operation: str) -> bool:
    """May a service perform *operation* where a person is normally required?

    The allowlist starts **empty**, so the exception grants nothing until
    somebody names an operation. Naming kinds one at a time is the difference
    between "services may rotate credentials" and "services may deploy" — a
    boolean would have said both.
    """
    allowed = _setting("service_allowed_operations", []) or []
    return bool(operation) and operation in allowed


#: Actions that are gated. Listed once so the diagnostic and the gates cannot
#: drift apart — the route used to report which gates were ENABLED, which is a
#: fact about configuration and not about the caller asking.
#: `publish_remote` is its own kind rather than reusing `confirm`.
#:
#: Two reasons, and the second is the load-bearing one. The audit should read
#: "published", not "confirmed" — they are different acts and a reader should
#: not have to infer which. And `service_allowed_operations` is keyed on the
#: KIND: sharing confirm's kind would mean a future grant letting a service
#: run Part 2's credential rotation would also let it publish a network's
#: history to a remote. A grant should not reach further than the thing it
#: was written for.
GATED_ACTIONS = ("reveal", "approve", "confirm", "publish_remote")


def may(ident: "Identity", action: str, operation: str = "") -> tuple:
    """``(allowed, reason)`` for *ident* performing *action*.

    Split out from :func:`require` so a caller that already has an ``Identity``
    can ask about several actions without re-validating the assertion each
    time, and so the diagnostic answers the same question the gate does, using
    the same code.
    """
    if not ident.is_identified:
        if not _setting(f"require_identity_for_{action}", True):
            return True, ""
        return False, (ident.reason or "requires a verified identity")

    if ident.kind != "service":
        return True, ""

    if not _setting(f"require_person_for_{action}", True):
        return True, ""

    if service_may(operation):
        return True, ""

    if operation:
        return False, (f"operation {operation!r} is not in the service "
                       "allowlist")
    return False, "requires a person"


def require(request, action: str = "reveal", operation: str = ""):
    """``(identity, refusal)``. *refusal* is ``None`` when the action may proceed.

    Two gates, in order, both fail-closed by setting:

    1. **Is anyone identified?** ``require_identity_for_<action>``.
    2. **Is a person required?** ``require_person_for_<action>``. A verified
       service is still not a person, and *approve* and *confirm* are the
       points where a human is supposed to have read an exact command list
       before it reaches a device. The confirm hash is only worth something
       because somebody looked at what it covers.

    *operation* names the kind of work — a service may be allowed specific
    kinds via ``service_allowed_operations`` without being allowed all of them.
    """
    ident = identify(request)
    allowed, reason = may(ident, action, operation)
    if allowed:
        if ident.kind == "service" and operation:
            log.info("identity: service permitted for operation=%s action=%s",
                     operation, action)
        return ident, None

    if ident.is_identified and ident.kind == "service":
        what = f" for {operation!r}" if operation else ""
        return ident, {
            "ok": False,
            "error": (f"'{action}'{what} requires a person. This request was "
                      f"authenticated as a service "
                      f"({service_label(ident.service_id)}), which may plan and "
                      "queue work but may not reveal a secret or change a "
                      "device."),
            "outcome": "person_required",
            "requires_person": True,
            "actor_kind": "service",
            "reason": reason,
        }

    # An honest message: "we could not verify you" is a different fact from
    # "you are not allowed", and only one of them tells the operator what to fix.
    detail = ident.reason or "identity could not be established"
    if ident.outcome in ("verifier_unavailable", "not_configured"):
        detail += (" — this is a configuration or connectivity problem, not a "
                   "permissions one")
    return ident, {
        "ok": False,
        "error": f"This action requires a verified identity: {detail}.",
        "outcome": ident.outcome,
        "requires_identity": True,
    }


# ---------------------------------------------------------------------------
# Posture — what the gates are set to, and where each value came from
# ---------------------------------------------------------------------------

#: Keys whose value is configuration a caller should not be handed. The gate
#: states are NOT here: "a person is required to reveal a secret" is a posture
#: statement, and hiding it protects nothing while making it uncheckable.
#: The team domain and the AUD are what an assertion is validated *against*,
#: and `routes/identity.py` has refused to echo them since it was written.
_POSTURE_SENSITIVE = ("cf_access_team_domain", "cf_access_aud",
                      "cf_access_trusted_peers")


def _setting_origin(key: str) -> str:
    """``"file"`` or ``"default"`` — where the effective value came from.

    **This is the whole reason the panel exists.** `_setting()` falls back to
    `DEFAULTS` when a key is absent, so a gate that is ON because nobody ever
    set it and a gate that is ON because somebody chose ON are
    indistinguishable by reading the value. They are different facts: the
    second was decided, the first was inherited.

    It matters more than it looks. `migrate()` returns early once the stored
    `settings_schema_version` has caught up, and `SCHEMA_VERSION` is still 1 —
    so **a key added to `DEFAULTS` after an install reached v1 is never
    written to that install's file.** Measured directly: seed a store at v1,
    add a key to `DEFAULTS`, run `migrate()`; `added_keys` is empty, the key
    is absent from the file, and `get_setting()` returns its default anyway.
    Working, correct, and recorded nowhere — which is precisely the state the
    identity gates are most likely to be in.
    """
    from modules.config import load_user_settings

    try:
        return "file" if key in (load_user_settings() or {}) else "default"
    except Exception:                          # noqa: BLE001
        log.error("identity: could not read stored settings for '%s'", key)
        return "unknown"


def posture(reveal_config: bool = False) -> dict:
    """The security posture: every gate, its effective value, and its origin.

    **Effective values are read through `_setting()`** — the same function
    `may()` and `service_may()` call — so the panel cannot drift from the
    gate. The same rule that made `/identity/status` report `may` rather than
    which gates are enabled: a diagnostic computed a second way is a
    diagnostic that can be wrong on its own.

    *reveal_config* adds the Access values. The caller decides, and
    `routes/identity.py` grants it only to a verified person: those values are
    what an assertion is validated against, and an ungated endpoint handing
    them out would be a config dump to exactly the caller the gates exist to
    stop. The team domain is a hostname and is shown whole; the AUD is
    abbreviated, because verifying a tag by eye needs its ends and not its
    middle.
    """
    gates = []
    for action in GATED_ACTIONS:
        for prefix, what in (("require_identity_for",
                              "anyone at all must be verified"),
                             ("require_person_for",
                              "a service is refused; a person is required")):
            key = f"{prefix}_{action}"
            gates.append({
                "key":      key,
                "action":   action,
                "means":    what,
                "value":    bool(_setting(key, True)),
                "origin":   _setting_origin(key),
                "default":  True,
            })

    allowed = _setting("service_allowed_operations", []) or []
    access_set = {k: bool((_setting(k, "") or "")) for k in _POSTURE_SENSITIVE}

    # THE SETTINGS FILE'S OWN HEALTH, on the panel that reports what it read.
    #
    # A settings layer running on defaults because it could not read its own
    # file is the wrong-thing-looking-right state: every gate below would
    # report its default and look deliberate. It was logged and nothing
    # more, and `device_manager.log` is not read until something else has
    # already gone wrong.
    try:
        from modules.config import settings_read_health

        read_health = settings_read_health()
    except Exception:                          # noqa: BLE001
        read_health = {}

    out = {
        "settings_readable": not read_health.get("unreadable"),
        "settings_read_failure": read_health,
        "gates": gates,
        "service_allowed_operations": list(allowed),
        "service_allowlist_origin": _setting_origin("service_allowed_operations"),
        "access_configured": is_configured(),
        "access_values_set": access_set,
        "config_revealed": bool(reveal_config),
    }

    if reveal_config:
        team = (_setting("cf_access_team_domain", "") or "").strip()
        aud  = (_setting("cf_access_aud", "") or "").strip()
        out["access"] = {
            "team_domain": team,
            "certs_url":   certs_url(team),
            # Ends only. Enough to check against what you expect, not a value
            # to copy out of a browser tab someone left open.
            "aud_preview": (f"{aud[:8]}…{aud[-8:]}" if len(aud) > 20 else
                            ("set" if aud else "")),
            "trusted_peer_count": len(trusted_peers()),
        }
    return out
