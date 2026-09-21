"""Identity comes from a verified assertion, never from a header.

Measured before the firewall was closed: a laptop on the LAN sent
`Cf-Access-Authenticated-User-Email: forged@example.com` to the app and got
HTTP 200. The email header is an ordinary HTTP header and anything that can
reach the port can set it.

Two independent conditions are required, and the tests below pin that neither
is sufficient alone.

No test contacts Cloudflare: a throwaway RSA key pair stands in for the team's
signing key, and the JWKS client is replaced.
"""

import time

import pytest

from modules import identity

TEAM = "example-team.cloudflareaccess.com"
AUD = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
TUNNEL = "10.0.0.21"


@pytest.fixture
def keys():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())
    return private, pem


@pytest.fixture
def configured(monkeypatch, keys):
    """Settings populated, and the JWKS client replaced by our own key."""
    private, _pem = keys
    values = {
        "cf_access_team_domain": TEAM,
        "cf_access_aud": AUD,
        "cf_access_trusted_peers": TUNNEL,
        "cf_access_jwks_ttl": 3600,
        "require_identity_for_reveal": True,
        "require_identity_for_approve": False,
        "require_identity_for_confirm": False,
    }
    monkeypatch.setattr(identity, "_setting",
                        lambda key, default=None: values.get(key, default))

    class _Key:
        key = private.public_key()

    class _Client:
        def get_signing_key_from_jwt(self, token):
            return _Key()

    monkeypatch.setattr(identity, "_get_jwks_client", lambda: _Client())
    return values


def _token(private, **overrides):
    import jwt

    now = int(time.time())
    claims = {"aud": AUD, "iss": f"https://{TEAM}", "email": "dustin@example.com",
              "iat": now, "exp": now + 600, "sub": "abc123"}
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm="RS256")


class _Req:
    """Minimal request stand-in: headers plus a raw socket peer."""

    def __init__(self, token=None, peer=TUNNEL, email_header=None):
        self.headers = {}
        if token:
            self.headers[identity.JWT_HEADER] = token
        if email_header:
            self.headers[identity.EMAIL_HEADER] = email_header
        self.environ = {"REMOTE_ADDR": peer}


class TestTheEmailHeaderIsNotEvidence:
    def test_the_email_header_alone_identifies_nobody(self, configured):
        """The exact forgery that returned HTTP 200 before the firewall."""
        ident = identity.identify(_Req(email_header="forged@example.com"))

        assert ident.verified is False
        assert ident.actor == identity.UNAUTHENTICATED
        assert ident.email == ""
        assert ident.outcome == "no_header"

    def test_the_email_header_is_ignored_even_beside_a_valid_assertion(
            self, configured, keys):
        """The claim wins; the header is never read."""
        private, _ = keys
        ident = identity.identify(
            _Req(token=_token(private), email_header="attacker@evil.example"))

        assert ident.email == "dustin@example.com"
        assert ident.actor == "dustin@example.com"


class TestAssertionValidation:
    def test_a_valid_assertion_from_the_tunnel_identifies(self, configured, keys):
        private, _ = keys
        ident = identity.identify(_Req(token=_token(private)))

        assert ident.is_identified is True
        assert ident.outcome == "ok"
        assert ident.actor == "dustin@example.com"

    def test_the_wrong_audience_is_refused(self, configured, keys):
        """The AUD tag is what binds a token to THIS application."""
        private, _ = keys
        ident = identity.identify(_Req(token=_token(private, aud="someone-elses-app")))

        assert ident.verified is False
        assert ident.outcome == "wrong_audience"

    def test_the_wrong_issuer_is_refused(self, configured, keys):
        private, _ = keys
        ident = identity.identify(
            _Req(token=_token(private, iss="https://other-team.cloudflareaccess.com")))
        assert ident.verified is False
        assert ident.outcome == "wrong_issuer"

    def test_an_expired_assertion_is_refused(self, configured, keys):
        private, _ = keys
        past = int(time.time()) - 3600
        ident = identity.identify(
            _Req(token=_token(private, iat=past, exp=past + 60)))
        assert ident.verified is False
        assert ident.outcome == "expired"

    def test_a_token_signed_by_another_key_is_refused(self, configured):
        """The signature is the point."""
        from cryptography.hazmat.primitives.asymmetric import rsa

        impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ident = identity.identify(_Req(token=_token(impostor)))
        assert ident.verified is False
        assert ident.outcome == "invalid_token"

    def test_garbage_is_refused_without_raising(self, configured):
        ident = identity.identify(_Req(token="not-a-jwt"))
        assert ident.verified is False
        assert ident.outcome == "invalid_token"

    def test_an_unsigned_none_algorithm_token_is_refused(self, configured):
        """`alg: none` is the classic JWT forgery."""
        import base64
        import json

        def _b64(obj):
            return base64.urlsafe_b64encode(
                json.dumps(obj).encode()).rstrip(b"=").decode()

        forged = (_b64({"alg": "none", "typ": "JWT"}) + "."
                  + _b64({"aud": AUD, "iss": f"https://{TEAM}",
                          "email": "attacker@evil.example",
                          "iat": int(time.time()), "exp": int(time.time()) + 600})
                  + ".")
        ident = identity.identify(_Req(token=forged))
        assert ident.verified is False
        assert ident.email == ""


class TestThePeerCheckIsIndependent:
    """A valid assertion replayed from elsewhere on the LAN still fails."""

    def test_a_valid_assertion_from_an_untrusted_peer_does_not_identify(
            self, configured, keys):
        private, _ = keys
        ident = identity.identify(_Req(token=_token(private), peer="10.0.0.30"))

        assert ident.verified is True          # the token really is valid
        assert ident.peer_trusted is False
        assert ident.is_identified is False    # but nobody is identified
        assert ident.actor == identity.UNAUTHENTICATED
        assert ident.outcome == "untrusted_peer"
        assert "replayed" in ident.reason

    def test_the_peer_comes_from_the_socket_not_a_forwarded_header(self, configured):
        """X-Forwarded-For is written by whoever is talking to us."""
        request = _Req(peer="10.0.0.30")
        request.headers["X-Forwarded-For"] = TUNNEL
        request.headers["X-Real-IP"] = TUNNEL

        assert identity.peer_address(request) == "10.0.0.30"

    def test_an_empty_trusted_list_disables_the_peer_check(self, configured, keys,
                                                           monkeypatch):
        """Blank means 'not configured', not 'trust nothing' — stated in settings."""
        private, _ = keys
        base = dict(configured, cf_access_trusted_peers="")
        monkeypatch.setattr(identity, "_setting",
                            lambda key, default=None: base.get(key, default))
        ident = identity.identify(_Req(token=_token(private), peer="10.0.0.30"))
        assert ident.is_identified is True


class TestNoForwardedHeaderTrustAnywhere:
    """Pinned for the whole app, not just this module."""

    def test_proxyfix_is_not_installed(self):
        import app as app_module

        chain, seen = app_module.app.wsgi_app, []
        while chain is not None and len(seen) < 10:
            seen.append(type(chain).__name__)
            chain = getattr(chain, "app", None)
        assert not any("ProxyFix" in name for name in seen), seen

    def test_nothing_reads_a_forwarded_header(self):
        import subprocess

        out = subprocess.run(
            ["grep", "-rniE", r"proxyfix|x[-_]forwarded[-_]for|x[-_]real[-_]ip",
             "--include=*.py", "modules/", "routes/", "app.py"],
            capture_output=True, text=True).stdout
        offending = [l for l in out.splitlines()
                     if l.strip() and "identity.py" not in l.split(":")[0]]
        assert offending == [], (
            "something trusts a proxy-written header:\n" + "\n".join(offending))


class TestFailClosedAndHonestMessages:
    def test_reveal_is_refused_without_identity_by_default(self, configured):
        ident, refusal = identity.require(_Req(), action="reveal")
        assert refusal is not None
        assert refusal["requires_identity"] is True
        assert ident.actor == identity.UNAUTHENTICATED

    def test_reveal_proceeds_with_a_verified_identity(self, configured, keys):
        private, _ = keys
        ident, refusal = identity.require(_Req(token=_token(private)), "reveal")
        assert refusal is None
        assert ident.actor == "dustin@example.com"

    def test_approve_is_not_gated_by_default(self, configured):
        _ident, refusal = identity.require(_Req(), action="approve")
        assert refusal is None

    def test_an_unreachable_verifier_says_so_rather_than_access_denied(
            self, configured, monkeypatch, keys):
        """A Cloudflare outage is a connectivity problem, not a permissions one."""
        private, _ = keys
        monkeypatch.setattr(identity, "_get_jwks_client", lambda: None)
        ident, refusal = identity.require(_Req(token=_token(private)), "reveal")

        assert ident.outcome == "verifier_unavailable"
        assert "configuration or connectivity problem" in refusal["error"]

    def test_unconfigured_access_does_not_silently_identify_anyone(self, monkeypatch):
        monkeypatch.setattr(identity, "_setting", lambda key, default=None: default)
        ident = identity.identify(_Req(token="anything"))
        assert ident.outcome == "not_configured"
        assert ident.actor == identity.UNAUTHENTICATED


class TestNothingLogsAValue:
    def test_no_email_or_token_reaches_the_log(self, configured, keys, caplog):
        import logging

        private, _ = keys
        token = _token(private)
        with caplog.at_level(logging.DEBUG):
            identity.identify(_Req(token=token))
            identity.identify(_Req(token=token, peer="10.0.0.30"))
            identity.identify(_Req(email_header="dustin@example.com"))

        logged = "\n".join(r.getMessage() for r in caplog.records)
        assert "dustin@example.com" not in logged
        assert token not in logged
        assert token[:40] not in logged

    def test_the_audit_row_carries_no_email(self, configured, keys):
        private, _ = keys
        row = identity.identify(_Req(token=_token(private))).audit()
        assert row["actor"] == "dustin@example.com"      # the actor IS the point
        assert "email" not in row                         # but not twice over
        assert set(row) == {"actor", "verified", "outcome", "peer", "peer_trusted"}

    def test_the_unidentified_actor_has_a_name(self):
        """An audit row with actor "" reads as a bug, not as an absence."""
        assert identity.UNAUTHENTICATED == "unauthenticated"
