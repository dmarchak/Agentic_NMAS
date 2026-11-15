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

import contextlib
import contextvars
import functools
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
#: "unverified" (B2, W2 2026-10-16), never the "unauthenticated" it was: that word was
#: recorded for a verified person's own click on every route whose gate did not run, so it
#: read as a fact about the person when it was a fact about where the code looked. What it
#: says now is exactly what is known: the request carried no assertion this code verified.
UNVERIFIED = "unverified"

#: The ways a REQUEST's identity is established, each stated by the code that established it
#: (`Identity.verification`): the access proxy's verified assertion (`_identify_access`), and
#: the installation's one local account (`modules/local_account.py`).
ACCESS, LOCAL_ACCOUNT = "access", "local-account"
REQUEST_VERIFICATIONS = (ACCESS, LOCAL_ACCOUNT)

_jwks_lock = threading.Lock()
_jwks_client = None
_jwks_for = ("", 0.0)


@dataclass(frozen=True)
class Identity:
    """The outcome of asking who is making a request."""

    actor: str = UNVERIFIED
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
    #: How an identified request was established (`actor_verification`'s word for it):
    #: ``access``, the proxy's verified assertion, or ``local-account``, the one local account
    #: of an installation listening on loopback only (`modules/local_account.py`). The code
    #: that establishes an identity states it (`_identify_access`, `local_account.identity`);
    #: `verification_of` reads it and fails closed.
    verification: str = ACCESS

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
#: person. `e367826f93b8….access` and `operator@example.com` are both opaque
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


def display_name(actor: str) -> str:
    """How *actor* is drawn on a screen, a record's summary and an export (board E2a, the
    operator, 2026-11-11): the name the person set (`modules/display_names.py`, per verified
    person), else the part of their identity before the "@", else the label a host login or a
    service already has (`service_label`). Never the domain.

    **A name, never an identity.** What a record keeps, what a gate compares and what a commit's
    ``Actor:`` says is still the verified actor (`request_actor`); this only decides how that
    person reads where a person is looking."""
    from modules import display_names

    return display_names.shown(actor)


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


#: The key cache's bounds, seconds (C621, the operator, 2026-10-10): never "keep for ever".
#: Cloudflare rotates its signing keys; PyJWT fetches a key it has not seen (measured in
#: PyJWT 2.7's `get_signing_key`: an unknown kid refreshes the set once), but a key Cloudflare
#: RETIRES stays trusted here until the cache is read again. 300 s is the lifespan floor this
#: module already gave PyJWKClient; a day bounds how long a retired key is trusted.
JWKS_TTL_MIN, JWKS_TTL_MAX, JWKS_TTL_DEFAULT = 300, 86400, 3600


def jwks_ttl() -> tuple:
    """``(seconds, problem)``: the key cache's lifetime, and why the stored value was not used
    ("" when it was). Outside JWKS_TTL_MIN..JWKS_TTL_MAX (0 included), or not a number, the
    default is used and the problem says so: the schema refuses such a value on write, so it
    reached the file by hand."""
    raw = _setting("cf_access_jwks_ttl", JWKS_TTL_DEFAULT)
    try:
        ttl = int(raw)
    except (TypeError, ValueError):
        return JWKS_TTL_DEFAULT, f"cf_access_jwks_ttl {raw!r} is not a number of seconds"
    if not JWKS_TTL_MIN <= ttl <= JWKS_TTL_MAX:
        return JWKS_TTL_DEFAULT, (f"cf_access_jwks_ttl {ttl} is outside {JWKS_TTL_MIN} to "
                                  f"{JWKS_TTL_MAX} seconds")
    return ttl, ""


def _get_jwks_client():
    """A cached ``PyJWKClient``, rebuilt when the team domain changes.

    The cache has a TTL rather than being permanent, so a key Cloudflare retires stops being
    trusted (C621) — and it is generous, so a brief outage of the certs endpoint
    does not lock an operator out of a tool that is otherwise entirely local.
    """
    global _jwks_client, _jwks_for

    url = certs_url()
    if not url:
        return None
    ttl, problem = jwks_ttl()
    if problem:
        log.error("identity: %s; using %d s", problem, ttl)

    with _jwks_lock:
        cached_url, built_at = _jwks_for
        if _jwks_client is not None and cached_url == url and (
                time.time() - built_at < ttl):
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


#: Headers a proxy writes or carries. NEVER trusted for who is asking (anything that reaches
#: the port can set them): they are read only to REFUSE, by `carries_proxy_header`, where a
#: request must be this machine's own and a relayed one is not (`modules/local_account.py`).
PROXY_WRITTEN_HEADERS = ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto",
                         "Forwarded", "X-Real-IP", "X-Client-IP", "True-Client-IP",
                         "CF-Connecting-IP", JWT_HEADER, "Via")


def carries_proxy_header(request) -> bool:
    """Does *request* carry a header a proxy writes? True only ever narrows: a request that
    carries one is not taken as this machine's own. PRESENCE is the test, never the value: a
    header sent empty is still one a proxy wrote (or one somebody sent to look like none), and
    nothing is read from what it holds."""
    return any(h in request.headers for h in PROXY_WRITTEN_HEADERS)


def verification_of(ident) -> str:
    """How *ident* was established: one of `REQUEST_VERIFICATIONS`, else ``none``.

    FAILS CLOSED. An identity that does not say how it was established (the field missing,
    empty, or a word this table does not hold) is ``none``, never ``access``: a record that
    says "access" is a claim that the proxy's assertion was verified, and only the code that
    verified it may make it."""
    how = getattr(ident, "verification", "")
    return how if isinstance(how, str) and how in REQUEST_VERIFICATIONS else "none"


def identify(request) -> Identity:
    """Who is making *request*. Never raises; never logs a value.

    The access proxy's verified assertion first, unchanged (`_identify_access`). Only when it
    identifies nobody is the installation's local account asked (`modules/local_account.py`:
    off by default, and only where Mercury listens on loopback only); a request signed in there
    is a person verified as ``local-account``, never ``access``. With it off, this answers
    exactly what the proxy's path answers."""
    ident = _identify_access(request)
    if ident.is_identified:
        return ident
    try:
        from modules import local_account
        local = local_account.identity(request)
    except Exception as exc:                            # noqa: BLE001 (no sign-in, never a raise)
        log.warning("identity: the local account could not be asked (%s)", type(exc).__name__)
        local = None
    return local or ident


def _identify_access(request) -> Identity:
    """Who the access proxy's assertion says is making *request*. Never raises; never logs a
    value."""
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
        return Identity(actor=UNVERIFIED, email="", kind="", verified=True,
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
                    header_present=True, verification=ACCESS)


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
#:
#: `configure` and `break_glass` were added by P.3 (2026-09-26), when the gate
#: became a table (`modules/route_gates.py`). `configure` covers the tool's own
#: settings, gates, inventory and records. `break_glass` is the terminal, kept
#: distinct from `confirm` because typing into a device shell and confirming a
#: previewed program mean different things about what happened.
GATED_ACTIONS = ("reveal", "approve", "confirm", "publish_remote",
                 "configure", "break_glass")


# ---------------------------------------------------------------------------
# The AI's own identity and its role (the operator, 2026-11-15; C3596, C3597 as far as Gate 1
# needs: "the AI acts under its own identity with an engineer-level role ... Every
# settings/admin route refuses that identity")
# ---------------------------------------------------------------------------

#: The AI's kind beside ``person`` and ``service`` (`Identity.kind`), and its actor's prefix:
#: ``ai:<feature>``, never a person's name, so a record says the AI did it.
AI_KIND = "ai"
AI_ACTOR_PREFIX = "ai:"
#: The AI's role: an engineer's, without a person's authority. It may read every page and
#: read devices through the read engine, propose plans, draft intent changes and record a
#: missing capability; every gated action is a person's (`GATED_ACTIONS`): it never changes a
#: setting, approves, confirms, reveals or publishes.
AI_ROLE = "engineer"
AI_ROLE_MAY = ("read every page", "read devices through the read engine", "propose a plan",
               "draft an intent change", "record a missing capability")
#: What is never the AI's, by the gate kind a route is declared under (`route_gates.GATES`):
#: the tool's own settings, its users and roles, credentials and secrets and notifications
#: (``configure``), revealing a secret, publishing, the break-glass terminal; and approving
#: anything (``approve`` and ``confirm`` are a person's press, always).
AI_NEVER = {"configure": "system settings, users and roles, credentials and secrets, and "
                         "notifications (the AI's on/off, its spend caps, automatic "
                         "troubleshooting, self-healing's mode and limits among them)",
            "reveal": "revealing a secret or a device's configuration",
            "publish_remote": "publishing a network's history",
            "break_glass": "typed device commands",
            "approve": "approving anything (a template, intent, a plan)",
            "confirm": "approving anything that changes a device"}
#: The routes an AI may never PROPOSE a step through though their kind is a person's approval
#: of a proposal (template approval: what renders every device's configuration).
AI_NEVER_ENDPOINTS = {"templates_v2.approve": "approving a template",
                      "templates_v2.revoke": "revoking a template's approval"}


#: The approval rights (the operator, 2026-11-15, Gate 1b): running a plan is any engineer's
#: (any verified person); saving or promoting a self-heal script needs self-healing rights;
#: saving a reusable action or adding a shape to Mercury's rule for raw lines is an admin's.
#: The AI proposes each and approves none. Each right's holders: `access_rights`.
RIGHTS = {"run_plan": "running a plan (any engineer)",
          "self_healing": "saving or promoting a self-heal script (self-healing rights)",
          "admin": "saving a reusable action or adding a shape to Mercury's rule for raw lines "
                   "(an admin)"}
#: The rights a list in `access_rights` may narrow; running a plan is every verified person's.
LISTED_RIGHTS = ("self_healing", "admin")


def right_refusal(right: str, *, actor: str, actor_verified: str, person: bool) -> str:
    """``""``, or why *actor* (verified as *actor_verified*; *person* the caller's word that a
    person pressed) may not do what *right* covers (`RIGHTS`): the one chokepoint each approval
    asks. Refused: an unknown right; the AI's identity, as the actor named or acting now
    (`acting_ai`); anyone not a verified person; and, for a right whose list in
    `access_rights` names anyone, anyone it does not name (a list not set is every verified
    person's, the behaviour before rights existed)."""
    if right not in RIGHTS:
        return f"Refused: {right!r} is no right Mercury knows ({', '.join(RIGHTS)})"
    what = RIGHTS[right]
    if is_ai(actor) or acting_ai() is not None:
        who = actor if is_ai(actor) else acting_ai().actor
        return (f"Refused: {who} may not approve {what}: the AI acts with the {AI_ROLE} role, "
                "which proposes and never approves")
    if not (person is True and actor and actor != UNVERIFIED
            and actor_verified in REQUEST_VERIFICATIONS):
        return (f"Refused: {what} is approved by a verified person, and this request is not "
                f"one (actor {actor or 'none'}, verified {actor_verified or 'none'})")
    if not holds(right, actor):
        return (f"Refused: {actor} does not hold the {right.replace('_', '-')} right "
                f"({what}); its holders are {', '.join(sorted(holders(right)))} "
                "(Settings' access_rights)")
    return ""


def holders(right: str) -> list:
    """The people `access_rights` names for *right* (one of `LISTED_RIGHTS`), or ``[]``: its
    list not set, so every verified person holds it."""
    if right not in LISTED_RIGHTS:
        return []
    return list((_setting("access_rights", {}) or {}).get(right) or [])


def holds(right: str, actor: str) -> bool:
    """Whether *actor* holds *right* by `access_rights` (a list not set is every verified
    person's): the one reading of the setting, asked by `right_refusal` and by anything that
    checks a right held earlier still holds (a promoted script's promoter)."""
    named = holders(right)
    return not named or actor in named


def rights_unset() -> list:
    """The listed rights (`LISTED_RIGHTS`) `access_rights` names no one for: every verified
    person holds each, and a screen offering one says so."""
    return [r for r in LISTED_RIGHTS if not holders(r)]


def ai_identity(feature: str) -> "Identity":
    """The AI's own identity for *feature* (``ai:<feature>``): identified, with the engineer
    role (`AI_ROLE`), and never a request's verification (`verification_of` reads ``none``),
    so nothing it does is recorded as a verified person's."""
    return Identity(actor=f"{AI_ACTOR_PREFIX}{feature}", email="", kind=AI_KIND, verified=True,
                    outcome="ok", peer_trusted=True, verification="")


#: The AI's identity while an AI entry point runs (`as_ai`): a context variable, so it is the
#: running code's own, never a request's, and the person a request verified stays recorded
#: as that person (`request_actor`, `actor_verification` read only the request and `carried`).
_AI_ACTING = contextvars.ContextVar("identity_ai_acting", default=None)


@contextlib.contextmanager
def as_ai(feature: str):
    """Inside the block, Mercury acts for the AI (`ai_identity` of *feature*): what it proposes
    is the AI's, and an Approve, a confirm or a settings write is refused (`ai_acting_refusal`,
    `may`, `ai_refusal`)."""
    token = _AI_ACTING.set(ai_identity(feature))
    try:
        yield _AI_ACTING.get()
    finally:
        _AI_ACTING.reset(token)


def acts_as_ai(feature: str):
    """Decorator: the function is an AI entry point and runs under `as_ai` (*feature*); the
    function carries ``acts_as_ai`` naming it."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            with as_ai(feature):
                return fn(*args, **kwargs)
        inner.acts_as_ai = feature
        return inner
    return wrap


def acting_ai():
    """The AI's identity when an AI entry point is running (`as_ai`), else None."""
    return _AI_ACTING.get()


def ai_carried(fn):
    """*fn*, to run in another thread (a job, a fan-out's worker) as the AI when it is handed
    over inside an AI entry point (`as_ai`): the one helper a thread starter uses to carry it,
    used today by the capture job (`capture_job`) and the fan-out (`fanout.read_each`) only. A
    thread started any other way (heal_notice's notice threads,
    reader_wakes, nsot/hooks) runs without the AI's identity, so what it records is Mercury's,
    not the AI's; nothing it approves is a person's either, since every approval asks for a
    verified person (`right_refusal`). The review of Gate 1b found no gated action an AI entry
    point reaches that way; a new one carries it through here. Each
    call runs in a fresh context (`contextvars.Context`) holding the AI's identity alone, never
    a copy of the whole context (`contextvars.copy_context`), which would also carry Flask's
    request (a context variable since Flask 2.3) into a thread that outlives it; outside an AI
    entry point *fn* is returned as it is."""
    ai = acting_ai()
    if ai is None:
        return fn

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        ctx = contextvars.Context()
        ctx.run(_AI_ACTING.set, ai)
        return ctx.run(fn, *args, **kwargs)
    return inner


def ai_acting_refusal(what: str = "approve or confirm anything") -> str:
    """``""``, or why nothing a person approves may happen now: an AI entry point is running
    (`as_ai`), and the AI proposes and never approves."""
    ai = acting_ai()
    return f"Refused: {ai.actor} may not {what}: {ai_role_words('approve')}" if ai else ""


def is_ai(who) -> bool:
    """Whether *who* (an `Identity`, or an actor's name) is the AI's."""
    if isinstance(who, Identity):
        return who.kind == AI_KIND or str(who.actor or "").startswith(AI_ACTOR_PREFIX)
    return isinstance(who, str) and who.startswith(AI_ACTOR_PREFIX)


def ai_role_words(action: str) -> str:
    """Why the AI's role refuses *action* (one of `GATED_ACTIONS`)."""
    return (f"the AI acts under its own identity with the {AI_ROLE} role, which may "
            f"{', '.join(AI_ROLE_MAY)}, and never {AI_NEVER.get(action, action)}")


def acting() -> "Identity":
    """Who is acting now: the AI while an AI entry point runs (`as_ai`), else this request's
    identity, else the one a job carries (`carried`), else none (unverified)."""
    if acting_ai() is not None:
        return acting_ai()
    try:
        from flask import has_request_context
        if has_request_context():
            return request_identity()
    except Exception:                                   # noqa: BLE001
        pass
    return getattr(_CARRIED, "ident", None) or Identity()


def ai_refusal(what: str, actor: str = "") -> str:
    """``""``, or why the AI may not do *what* (a setting written, a user changed): when
    *actor* is the AI's, or the identity acting now is (`acting`), the AI's role refuses it,
    naming *what*. The store's own check, beside the route gate's (`may`)."""
    if not (is_ai(actor) or is_ai(acting())):
        return ""
    who = actor if is_ai(actor) else acting().actor
    return f"Refused: {who} may not change {what}: {ai_role_words('configure')}"


def ai_never_proposes(endpoint: str, gate_kind: str, gate_reason: str = "") -> str:
    """``""``, or why the AI may not propose a step a person would take through *endpoint*
    (declared under *gate_kind*, `route_gates.GATES`): a kind the AI never touches through a
    proposal (`AI_NEVER`, all but a person's own approval of the proposal: ``approve`` and
    ``confirm``), or a route `AI_NEVER_ENDPOINTS` names."""
    what = AI_NEVER_ENDPOINTS.get(endpoint) or (
        AI_NEVER.get(gate_kind) if gate_kind not in ("approve", "confirm") else "")
    if not gate_kind:
        what = "a change whose route declares no gate"
    if not what:
        return ""
    return (f"the AI acts with the {AI_ROLE} role and never proposes {what}: this step is "
            f"{endpoint}" + (f" ({gate_reason})" if gate_reason else ""))


def actor_verification(actor: str) -> str:
    """How *actor* on a commit was established (register D10, P.3 step 10).

    - ``access``: inside a request whose access assertion VERIFIED this same
      actor (`request_identity()`: the gate's verification, or the same
      `identify()` made for a route whose gate did not run, B2);
    - ``host-shell``: a CLI on the host, where SSH to the host is the
      authentication (the process never installed the gate);
    - ``policy``: a background job acting on a standing policy a verified person
      confirmed by its fingerprint (board H, H4: an automatic heal, `carried_policy`),
      only for that person, the policy's setter, who is accountable for it;
    - ``none``: anything else, including the app's background threads and a
      request whose recorded actor is not the one its assertion verified.

    Decided by what the code knows at the moment of the commit, never by date:
    the host ran old code after c5a34c1 was pushed, so a commit's date does not
    say which code wrote it.
    """
    try:
        from flask import has_request_context
        if has_request_context():
            ident = request_identity()
            ok = (ident.is_identified and actor
                  and actor != UNVERIFIED and ident.actor == actor)
            return verification_of(ident) if ok else "none"
    except Exception:                                   # noqa: BLE001
        return "none"
    # A JOB a gated request started (the rotate screen, 7.3): the request's
    # verified identity, carried into its thread by `carried()`, and only for
    # that same actor. Without it every commit a job made read "none" although
    # the gate had verified the person who confirmed it.
    ident = getattr(_CARRIED, "ident", None)
    if ident is not None:
        ok = (ident.is_identified and actor and actor != UNVERIFIED
              and ident.actor == actor)
        # The kind `carried()` read at the hand-over and carried beside the identity: the
        # job's commit records that, and with nothing stated there it is "none".
        return getattr(_CARRIED, "verification", "none") if ok else "none"
    # A job acting on a confirmed policy (`carried_policy`): the policy's setter, and no one else.
    policy = getattr(_CARRIED, "policy", None)
    if policy is not None:
        return "policy" if actor and actor != UNVERIFIED and actor == policy["actor"] else "none"
    from modules import route_gates
    return "none" if route_gates.installed() else "host-shell"


def host_actor() -> str:
    """Who ran a host command, as every record names them: the OS login, LABELLED
    (`inventory_edit.actor_label`'s rule), never bare. C237: the app records a verified
    email and the host commands recorded the bare login, so the audit trail held two
    unlabelled identities for one person. The one place a host command reads its login
    for a record (tests/test_host_actor_is_labelled.py refuses another)."""
    import getpass

    from modules.inventory_edit import actor_label

    return actor_label(getpass.getuser(), "host-shell")


import contextlib as _contextlib  # noqa: E402
import threading as _threading  # noqa: E402

_CARRIED = _threading.local()


def verified_identity():
    """The identity THIS request's assertion verified (`request_identity()`, whatever its
    gate), to hand to a job it starts, or None. Only a request can produce one: outside a
    request there is nothing verified to carry."""
    try:
        from flask import has_request_context
        if has_request_context():
            ident = request_identity()
            return ident if ident.is_identified else None
    except Exception:                                   # noqa: BLE001
        return None
    return None


@_contextlib.contextmanager
def carried(ident):
    """Inside a job's thread: commits naming *ident*'s actor record how that person was
    verified, the kind the request's identity states (``access`` or ``local-account``), as
    they would have inside the request that verified it. *ident* comes from
    `verified_identity()`; None carries nothing.

    The kind is read ONCE, here, at the hand-over (`verification_of`, which fails closed),
    and carried beside the identity for the whole job: an identity that does not state its
    kind carries ``none``, never ``access``, and nothing the job does later changes it."""
    before = (getattr(_CARRIED, "ident", None), getattr(_CARRIED, "verification", "none"))
    _CARRIED.ident = ident
    _CARRIED.verification = verification_of(ident) if ident is not None else "none"
    try:
        yield
    finally:
        _CARRIED.ident, _CARRIED.verification = before


@_contextlib.contextmanager
def carried_policy(actor: str, fingerprint: str):
    """Inside a job acting on a standing policy (board H, H4: an automatic heal): commits
    naming *actor*, the policy's setter, read ``Actor-Verified: policy``. *fingerprint* is the
    confirmed policy the authority stands on; with no setter or no fingerprint nothing is
    carried, so the commit reads ``none``, which is true."""
    before = getattr(_CARRIED, "policy", None)
    _CARRIED.policy = ({"actor": actor, "fingerprint": fingerprint}
                       if actor and fingerprint else None)
    try:
        yield
    finally:
        _CARRIED.policy = before


def viewer(request=None) -> "Identity":
    """Who is LOOKING at this request's page or fragment: the identity to draw.

    `request_actor()` answered only inside a gated request (until B2), because the gate
    is what puts the verified identity on ``flask.g``, and a GET page is never
    gated. So the redesign's first page drew every person as
    ``unauthenticated`` while today's pages, which ask ``/identity/status``,
    drew them correctly (the operator, 2026-09-30). This is the same
    `identify()` the gate and the status route call, once per request: the
    gate's own result when it ran, else a verification made here and kept on
    ``flask.g`` for the rest of the request. It draws; it authorises nothing
    (the gate still decides every gated request itself)."""
    try:
        from flask import g, has_request_context
        from flask import request as _request
        if not has_request_context():
            return Identity(outcome="no_request", reason="there is no request to ask about")
        gated = getattr(g, "nmas_identity", None)
        if gated is not None:
            return gated
        seen = getattr(g, "nmas_viewer", None)
        if seen is None:
            seen = identify(request or _request)
            g.nmas_viewer = seen
        return seen
    except Exception as exc:                            # noqa: BLE001
        log.warning("identity: could not resolve the viewer (%s)", type(exc).__name__)
        return Identity(outcome="error", reason="the identity could not be resolved")


def request_identity() -> "Identity":
    """The identity the current request's access assertion establishes, WHATEVER its gate:
    the gate's own verification when it ran (``flask.g.nmas_identity``), else the same
    `identify()` made once for this request (`viewer()`). The one answer every recorder
    reads: `request_actor()`, `actor_verification()` and `verified_identity()`.

    B2 (W2, 2026-10-16): these three read only ``flask.g.nmas_identity``, which the gate
    sets only for a gated kind (`route_gates.enforce`, which returns before it for
    ``not_device``). A verified person's NetBox import preview, Verify the remote and every
    other ungated route that records therefore recorded ``unauthenticated``. A gate of N
    means no person is REQUIRED, never that none is NAMED. This verifies; it authorises
    nothing: whether a gated request may proceed is still `require()`'s, in the gate."""
    return viewer()


def request_actor() -> str:
    """The VERIFIED actor of the current request, never one the client named.

    The gate (`route_gates.enforce`) puts the identity it verified on
    ``flask.g``. Fourteen routes used to record ``data.get("actor", "user")``,
    a name the client typed, beside a gate that had just verified a different
    one; the audit then says whatever the request body said. Read through
    `request_identity()`, so a route whose gate did not run (a preview, a read)
    names its verified person too (B2). A request whose assertion was not
    verified answers `UNVERIFIED`, which is what it was.

    Outside a request, a job a verified request started (`carried()`) answers that
    request's person; anything else answers `UNVERIFIED`. A caller outside any request
    that records names itself (`recorded_actor`).
    """
    try:
        from flask import has_request_context
        if has_request_context():
            ident = request_identity()
            return ident.actor if ident.is_identified else UNVERIFIED
    except Exception:                                   # noqa: BLE001
        return UNVERIFIED
    ident = getattr(_CARRIED, "ident", None)
    if ident is not None and ident.is_identified:
        return ident.actor
    return UNVERIFIED


#: How Mercury names itself as the actor of what it does with nobody's request behind it.
MERCURY_ACTOR = "Mercury: {job}"


def recorded_actor(job: str) -> str:
    """Who a record names, wherever it is made: inside a request, `request_actor()` (its
    verified person or service, or `UNVERIFIED`); in a job a verified request started, that
    person; with neither, Mercury itself, naming *job* ("Mercury: repository init"). Never
    "unauthenticated" or an empty actor for something somebody did (B2)."""
    try:
        from flask import has_request_context
        in_request = has_request_context()
    except Exception:                                   # noqa: BLE001
        in_request = False
    carried_ident = getattr(_CARRIED, "ident", None)
    if in_request or (carried_ident is not None and carried_ident.is_identified):
        return request_actor()
    return MERCURY_ACTOR.format(job=job)


def may(ident: "Identity", action: str, operation: str = "") -> tuple:
    """``(allowed, reason)`` for *ident* performing *action*.

    Split out from :func:`require` so a caller that already has an ``Identity``
    can ask about several actions without re-validating the assertion each
    time, and so the diagnostic answers the same question the gate does, using
    the same code.
    """
    if is_ai(ident) or acting_ai() is not None:
        # The AI's own identity (its engineer role), or an AI entry point running: no gated
        # action is its, whatever a setting says, since each is a person's or a granted
        # service's.
        return False, ai_role_words(action)

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


def access_scope() -> str:
    """What the requester of this request may do, as one comparable string: who `may` sees
    (a person, a service by its label, or unverified) and the gated actions `may` allows them,
    in `GATED_ACTIONS`' order. An AI call is never handed across it (C1854: a press joins
    another's call only under the same scope, `modules/ai/presses.py`).

    It is `may`'s answer because `may` is the one function every gate asks. Mercury resolves no
    role per network yet (NSOT_AUTHORIZATION section 6's ``any_person``: every verified person
    may do every action; the roles per network are NSOT_STAGE10_PLAN's 9.I), so the scope is
    the same on every network; when `may` takes a network, this takes it too. Two verified
    persons share a scope today, and a person, a service and an unverified requester do not.
    The identity is this request's (`request_identity()`), else the one a job carries
    (`carried()`), else none (unverified)."""
    ident = None
    try:
        from flask import has_request_context
        if has_request_context():
            ident = request_identity()
    except Exception:                                   # noqa: BLE001
        ident = None
    if ident is None:
        ident = getattr(_CARRIED, "ident", None) or Identity()
    if not ident.is_identified:
        who = "unverified"
    elif ident.kind == "service":
        who = f"service {service_label(ident.service_id)}"
    else:
        who = ident.kind or "person"
    allowed = [a for a in GATED_ACTIONS if may(ident, a)[0]]
    return f"{who}; may {', '.join(allowed) if allowed else 'no gated action'}"


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

    if is_ai(ident) or acting_ai() is not None:
        return ident, {"ok": False, "error": f"Refused: {reason}.", "outcome": "ai_role",
                       "requires_person": True, "actor_kind": AI_KIND, "reason": reason}

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
