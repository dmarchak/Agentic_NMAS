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
        """What an audit row should carry. Never the email, never the token."""
        return {"actor": self.actor, "verified": self.verified,
                "outcome": self.outcome, "peer": self.peer,
                "peer_trusted": self.peer_trusted}


def _setting(key, default=None):
    from modules.settings_schema import get_setting
    return get_setting(key, default)


def trusted_peers() -> list:
    raw = (_setting("cf_access_trusted_peers", "") or "").strip()
    return [p.strip() for p in raw.split(",") if p.strip()]


def is_configured() -> bool:
    return bool((_setting("cf_access_team_domain", "") or "").strip()
                and (_setting("cf_access_aud", "") or "").strip())


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
    peer_trusted = (not allowed) or (peer in allowed)
    token = request.headers.get(JWT_HEADER, "")
    present = bool(token)

    def _no(outcome, reason):
        log.info("identity: %s (header_present=%s peer_trusted=%s)",
                 outcome, present, peer_trusted)
        return Identity(outcome=outcome, reason=reason, peer=peer,
                        peer_trusted=peer_trusted, header_present=present)

    if not is_configured():
        return _no("not_configured",
                   "Cloudflare Access is not configured (team domain and AUD "
                   "tag are unset in Settings)")
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
                   "PyJWKClientError": "verifier_unavailable",
                   }.get(type(exc).__name__, "invalid_token")
        log.warning("identity: assertion rejected (%s) peer_trusted=%s",
                    outcome, peer_trusted)
        return Identity(outcome=outcome, peer=peer, peer_trusted=peer_trusted,
                        header_present=True,
                        reason=f"the Access assertion was rejected ({outcome})")

    email = (claims.get("email") or claims.get("common_name") or "").strip()
    if not email:
        return Identity(outcome="invalid_token", peer=peer,
                        peer_trusted=peer_trusted, header_present=True,
                        reason="the assertion carried no identity claim")

    if not peer_trusted:
        log.warning("identity: valid assertion from an untrusted peer %s", peer)
        return Identity(actor=UNAUTHENTICATED, email="", verified=True,
                        outcome="untrusted_peer", peer=peer,
                        peer_trusted=False, header_present=True,
                        reason=(f"the assertion is valid but arrived from {peer}, "
                                "which is not a trusted peer — a captured "
                                "assertion replayed from elsewhere looks like "
                                "this"))

    log.info("identity: verified (outcome=ok peer=%s)", peer)
    return Identity(actor=email, email=email, verified=True, outcome="ok",
                    peer=peer, peer_trusted=True, header_present=True)


def require(request, action: str = "reveal"):
    """``(identity, refusal)``. *refusal* is ``None`` when the action may proceed.

    Fail-closed by setting, per action. ``reveal`` defaults ON because
    revealing a secret is the action whose audit entry is worthless without a
    name attached to it.
    """
    ident = identify(request)
    if ident.is_identified:
        return ident, None

    key = f"require_identity_for_{action}"
    if not _setting(key, action == "reveal"):
        return ident, None

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
