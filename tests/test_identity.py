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
        # These mirror settings_schema.DEFAULTS deliberately. A fixture that
        # encodes the OLD defaults lies about the system under test: it let an
        # unidentified caller through a gate that is ON in production, and the
        # only thing that noticed was a test written afterwards.
        "require_identity_for_reveal": True,
        "require_identity_for_approve": True,
        "require_identity_for_confirm": True,
        "require_person_for_approve": True,
        "require_person_for_confirm": True,
        "service_allowed_operations": [],
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

    def test_approve_is_gated_by_default(self, configured):
        """Changed deliberately: approve puts configuration on a device."""
        _ident, refusal = identity.require(_Req(), action="approve")
        assert refusal is not None
        assert refusal["requires_identity"] is True

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
        assert set(row) == {"actor", "kind", "verified", "outcome", "peer",
                            "peer_trusted"}
        assert row["kind"] == "person"

    def test_the_unidentified_actor_has_a_name(self):
        """An audit row with actor "" reads as a bug, not as an absence."""
        assert identity.UNAUTHENTICATED == "unauthenticated"


class TestTheOutcomeNamesTheRightCause:
    """`verifier_unavailable` and `invalid_token` are opposite diagnoses.

    PyJWKClient raises PyJWKClientError both when it cannot fetch the key set
    and when a token's `kid` is absent from a key set it fetched successfully.
    Mapping the exception type alone reported a forged token as
    `verifier_unavailable`, and `require()` then told the operator this was
    "a configuration or connectivity problem, not a permissions one" — while
    somebody was presenting a forgery. Found by running against the real
    Cloudflare endpoint, which no unit test would have shown.
    """

    def _client(self, *, keyset_ok):
        class _Client:
            def get_signing_key_from_jwt(self, token):
                from jwt.exceptions import PyJWKClientError
                raise PyJWKClientError("unable to find a signing key")

            def get_jwk_set(self):
                if not keyset_ok:
                    raise OSError("certs endpoint unreachable")
                return object()
        return _Client()

    def test_an_unknown_kid_with_a_healthy_verifier_is_an_invalid_token(
            self, configured, monkeypatch):
        monkeypatch.setattr(identity, "_get_jwks_client",
                            lambda: self._client(keyset_ok=True))
        ident = identity.identify(_Req(token="eyJhbGciOiJSUzI1NiJ9.e30.sig"))

        assert ident.outcome == "invalid_token"
        _i, refusal = identity.require(
            _Req(token="eyJhbGciOiJSUzI1NiJ9.e30.sig"), "reveal")
        assert "connectivity problem" not in refusal["error"]

    def test_an_unreachable_keyset_is_a_verifier_problem(self, configured,
                                                          monkeypatch):
        monkeypatch.setattr(identity, "_get_jwks_client",
                            lambda: self._client(keyset_ok=False))
        ident = identity.identify(_Req(token="eyJhbGciOiJSUzI1NiJ9.e30.sig"))

        assert ident.outcome == "verifier_unavailable"
        _i, refusal = identity.require(
            _Req(token="eyJhbGciOiJSUzI1NiJ9.e30.sig"), "reveal")
        assert "connectivity problem" in refusal["error"]


class TestTheStatusRoute:
    """The end-to-end diagnostic, and the three things it must not do."""

    @pytest.fixture
    def client(self, configured):
        import flask

        import routes.identity as route_mod

        app = flask.Flask(__name__)
        app.register_blueprint(route_mod.bp)
        return app.test_client()

    def test_it_reports_an_unverified_request_rather_than_refusing(self, client):
        """A diagnostic that hides behind identity is useless when identity breaks."""
        response = client.get("/identity/status", environ_base={"REMOTE_ADDR": TUNNEL})

        assert response.status_code == 200
        body = response.get_json()
        assert body["ok"] is True
        assert body["token_present"] is False
        assert body["verified"] is False
        assert body["is_identified"] is False
        assert body["email"] == ""
        assert body["actor"] == identity.UNAUTHENTICATED

    def test_a_verified_request_reports_the_email_to_the_requester(self, client, keys):
        private, _ = keys
        response = client.get(
            "/identity/status",
            headers={identity.JWT_HEADER: _token(private)},
            environ_base={"REMOTE_ADDR": TUNNEL})

        body = response.get_json()
        assert body["token_present"] is True
        assert body["verified"] is True
        assert body["peer_trusted"] is True
        assert body["is_identified"] is True
        assert body["email"] == "dustin@example.com"
        assert body["outcome"] == "ok"

    def test_it_distinguishes_which_headers_survived_the_tunnel(self, client, keys):
        """"Forwards the email but not the assertion" is its own bug."""
        private, _ = keys
        response = client.get(
            "/identity/status",
            headers={identity.EMAIL_HEADER: "dustin@example.com"},
            environ_base={"REMOTE_ADDR": TUNNEL})

        seen = response.get_json()["headers_seen"]
        assert seen[identity.EMAIL_HEADER] is True
        assert seen[identity.JWT_HEADER] is False

    def test_it_never_echoes_the_team_domain_or_aud_tag(self, client, keys):
        """A diagnostic is where a config dump creeps in."""
        private, _ = keys
        response = client.get(
            "/identity/status",
            headers={identity.JWT_HEADER: _token(private)},
            environ_base={"REMOTE_ADDR": TUNNEL})

        raw = response.get_data(as_text=True)
        assert TEAM not in raw
        assert AUD not in raw
        assert response.get_json()["access_configured"] is True

    def test_it_logs_no_email_and_no_token(self, client, keys, caplog):
        import logging

        private, _ = keys
        token = _token(private)
        with caplog.at_level(logging.DEBUG):
            client.get("/identity/status",
                       headers={identity.JWT_HEADER: token,
                                identity.EMAIL_HEADER: "dustin@example.com"},
                       environ_base={"REMOTE_ADDR": TUNNEL})

        logged = "\n".join(r.getMessage() for r in caplog.records)
        assert "dustin@example.com" not in logged
        assert token[:40] not in logged

    def test_an_untrusted_peer_sees_the_refusal_not_the_email(self, client, keys):
        private, _ = keys
        response = client.get(
            "/identity/status",
            headers={identity.JWT_HEADER: _token(private)},
            environ_base={"REMOTE_ADDR": "10.0.0.30"})

        body = response.get_json()
        assert body["verified"] is True
        assert body["peer_trusted"] is False
        assert body["is_identified"] is False
        assert body["email"] == ""

    def test_the_route_is_registered_on_the_real_app(self):
        import app as app_module

        rules = {r.rule for r in app_module.app.url_map.iter_rules()}
        assert "/identity/status" in rules


class TestServiceTokensAreIdentifiedDistinctly:
    """Automation authenticates the same way people do — and is recorded apart.

    Cloudflare issues the **same shape** of assertion for both: `type: "app"`
    either way, so `type` is not the discriminator it looks like. What differs
    is the identity claim — a person carries `email` with a UUID `sub`; a
    service token carries `common_name` (its Client ID) with `sub: ""` and no
    `email` at all.

    The first implementation read `email or common_name` into one field, which
    would have written a Client ID into the column every reader takes to be a
    person's address.
    """

    def _service_token(self, private, **overrides):
        import jwt

        now = int(time.time())
        claims = {"type": "app", "aud": AUD, "iss": f"https://{TEAM}",
                  "common_name": "e367826f93b8d71185e03fe518aff3b4.access",
                  "iat": now, "exp": now + 600, "sub": ""}
        claims.update(overrides)
        return jwt.encode(claims, private, algorithm="RS256")

    def test_a_service_token_identifies_as_a_service(self, configured, keys):
        private, _ = keys
        ident = identity.identify(_Req(token=self._service_token(private)))

        assert ident.is_identified is True
        assert ident.kind == "service"
        assert ident.service_id == "e367826f93b8d71185e03fe518aff3b4.access"
        assert ident.email == "", "a service token has no email to report"

    def test_the_service_actor_cannot_be_mistaken_for_a_person(self, configured,
                                                                keys):
        private, _ = keys
        ident = identity.identify(_Req(token=self._service_token(private)))

        assert ident.actor.startswith(identity.SERVICE_ACTOR_PREFIX)
        assert "@" not in ident.actor

    def test_a_person_is_still_a_person(self, configured, keys):
        private, _ = keys
        ident = identity.identify(_Req(token=_token(private)))

        assert ident.kind == "person"
        assert ident.email == "dustin@example.com"
        assert ident.service_id == ""
        assert not ident.actor.startswith(identity.SERVICE_ACTOR_PREFIX)

    def test_the_audit_row_distinguishes_them(self, configured, keys):
        private, _ = keys
        person = identity.identify(_Req(token=_token(private))).audit()
        service = identity.identify(
            _Req(token=self._service_token(private))).audit()

        assert person["kind"] == "person"
        assert service["kind"] == "service"
        assert person["actor"] != service["actor"]

    def test_an_assertion_naming_nobody_is_refused(self, configured, keys):
        """Valid signature, valid audience, no identity claim."""
        private, _ = keys
        ident = identity.identify(
            _Req(token=self._service_token(private, common_name="")))

        assert ident.verified is False
        assert ident.outcome == "invalid_token"
        assert "names nobody" in ident.reason

    def test_a_service_token_may_reveal_but_not_approve_or_confirm(
            self, configured, keys):
        """Automation authenticates — and is still not a person.

        Reveal is how a service uses a secret it needs. Approve and confirm are
        where a human is supposed to have read an exact command list before it
        reaches a device.
        """
        private, _ = keys
        request = _Req(token=self._service_token(private))

        _ident, refusal = identity.require(request, "reveal")
        assert refusal is None

        for action in ("approve", "confirm"):
            _ident, refusal = identity.require(request, action)
            assert refusal is not None, action
            assert refusal["outcome"] == "person_required"

    def test_a_service_token_from_an_untrusted_peer_still_fails(self, configured,
                                                                 keys):
        private, _ = keys
        ident = identity.identify(
            _Req(token=self._service_token(private), peer="10.0.0.30"))
        assert ident.is_identified is False
        assert ident.kind == ""


class TestAllThreeActionsRequireIdentityByDefault:
    """Reveal exposes a secret; approve and confirm put config on a device."""

    def test_the_defaults(self):
        from modules.settings_schema import DEFAULTS

        for action in ("reveal", "approve", "confirm"):
            assert DEFAULTS[f"require_identity_for_{action}"] is True, action

    def test_an_unidentified_request_is_refused_for_each(self, configured,
                                                          monkeypatch):
        base = dict(configured, require_identity_for_approve=True,
                    require_identity_for_confirm=True)
        monkeypatch.setattr(identity, "_setting",
                            lambda key, default=None: base.get(key, default))
        for action in ("reveal", "approve", "confirm"):
            _ident, refusal = identity.require(_Req(), action)
            assert refusal is not None, action

    def test_there_is_no_localhost_exemption(self):
        """An exemption for the box is an exemption for anything on the box."""
        import inspect

        source = inspect.getsource(identity)
        for loopback in ("127.0.0.1", "localhost", "::1"):
            assert loopback not in source, (
                f"{loopback} appears in identity.py — a loopback exemption "
                "bypasses the audit trail exactly where it matters most")


class TestServiceLabelsAreCosmeticOnly:
    """A label decides how the trail READS, never who gets in."""

    CLIENT_ID = "e367826f93b8d71185e03fe518aff3b4.access"

    def _service_token(self, private):
        import jwt
        now = int(time.time())
        return jwt.encode({"type": "app", "aud": AUD, "iss": f"https://{TEAM}",
                           "common_name": self.CLIENT_ID, "iat": now,
                           "exp": now + 600, "sub": ""},
                          private, algorithm="RS256")

    def test_an_unlabelled_token_falls_back_to_its_id(self, configured, keys):
        private, _ = keys
        row = identity.identify(_Req(token=self._service_token(private))).audit()
        assert row["service"] == self.CLIENT_ID

    def test_a_labelled_token_reads_as_its_name(self, configured, keys, monkeypatch):
        private, _ = keys
        base = dict(configured,
                    cf_access_service_labels={self.CLIENT_ID: "nmas-automation"})
        monkeypatch.setattr(identity, "_setting",
                            lambda key, default=None: base.get(key, default))
        row = identity.identify(_Req(token=self._service_token(private))).audit()
        assert row["service"] == "nmas-automation"
        assert row["actor"].startswith(identity.SERVICE_ACTOR_PREFIX)

    def test_a_label_grants_nothing(self, configured, keys, monkeypatch):
        """Labelling an id the assertion does not carry changes no outcome."""
        private, _ = keys
        base = dict(configured,
                    cf_access_service_labels={"someone-elses.access": "trusted"})
        monkeypatch.setattr(identity, "_setting",
                            lambda key, default=None: base.get(key, default))
        ident = identity.identify(_Req(token=self._service_token(private)))
        assert ident.is_identified is True
        assert ident.service_id == self.CLIENT_ID
        assert ident.audit()["service"] == self.CLIENT_ID

    def test_a_person_row_has_no_service_field(self, configured, keys):
        private, _ = keys
        row = identity.identify(_Req(token=_token(private))).audit()
        assert "service" not in row


class TestAServiceIsNotAPerson:
    """A verified service still may not approve or confirm a change.

    The confirm hash is only worth something because a human read what it
    covers. A non-expiring credential that can skip that step holds a great
    deal of authority implicitly — so the authority is made explicit instead,
    one operation kind at a time.
    """

    CLIENT_ID = "e367826f93b8d71185e03fe518aff3b4.access"

    def _svc(self, private):
        import jwt
        now = int(time.time())
        return jwt.encode({"type": "app", "aud": AUD, "iss": f"https://{TEAM}",
                           "common_name": self.CLIENT_ID, "iat": now,
                           "exp": now + 600, "sub": ""},
                          private, algorithm="RS256")

    def _with(self, monkeypatch, configured, **over):
        base = dict(configured)
        base.update({"require_person_for_approve": True,
                     "require_person_for_confirm": True,
                     "service_allowed_operations": []})
        base.update(over)
        monkeypatch.setattr(identity, "_setting",
                            lambda key, default=None: base.get(key, default))

    def test_the_defaults_require_a_person(self):
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS["require_person_for_approve"] is True
        assert DEFAULTS["require_person_for_confirm"] is True

    def test_the_allowlist_starts_empty(self):
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS["service_allowed_operations"] == [], (
            "the exception must grant nothing until somebody names an operation")

    def test_a_person_is_unaffected(self, configured, keys, monkeypatch):
        private, _ = keys
        self._with(monkeypatch, configured)
        for action in ("reveal", "approve", "confirm"):
            _i, refusal = identity.require(_Req(token=_token(private)), action)
            assert refusal is None, action

    def test_a_service_is_refused_with_an_honest_reason(self, configured, keys,
                                                        monkeypatch):
        private, _ = keys
        self._with(monkeypatch, configured)
        ident, refusal = identity.require(_Req(token=self._svc(private)), "confirm")

        assert ident.is_identified is True       # it DID authenticate
        assert refusal["outcome"] == "person_required"
        assert refusal["actor_kind"] == "service"
        assert "may plan and queue work" in refusal["error"]

    def test_an_empty_allowlist_permits_nothing(self, configured, keys,
                                                 monkeypatch):
        private, _ = keys
        self._with(monkeypatch, configured)
        for operation in ("credential_rotation", "deploy", "", "anything"):
            _i, refusal = identity.require(
                _Req(token=self._svc(private)), "confirm", operation=operation)
            assert refusal is not None, operation

    def test_a_named_operation_is_permitted_and_only_that_one(
            self, configured, keys, monkeypatch):
        """Part 2 adds `credential_rotation` — and nothing else comes with it."""
        private, _ = keys
        self._with(monkeypatch, configured,
                   service_allowed_operations=["credential_rotation"])
        request = _Req(token=self._svc(private))

        _i, allowed = identity.require(request, "confirm",
                                       operation="credential_rotation")
        assert allowed is None

        for other in ("deploy", "restore", "template_edit", ""):
            _i, refusal = identity.require(request, "confirm", operation=other)
            assert refusal is not None, other

    def test_the_allowlist_does_not_rescue_an_unidentified_caller(
            self, configured, monkeypatch):
        """It is an exception for SERVICES, not a bypass for anyone."""
        self._with(monkeypatch, configured,
                   service_allowed_operations=["credential_rotation"])
        _i, refusal = identity.require(_Req(), "confirm",
                                       operation="credential_rotation")
        assert refusal is not None
        assert refusal.get("requires_identity") is True

    def test_the_audit_row_records_kind_for_a_gated_action(self, configured,
                                                            keys, monkeypatch):
        private, _ = keys
        self._with(monkeypatch, configured)
        ident, _refusal = identity.require(_Req(token=self._svc(private)), "confirm")
        assert ident.audit()["kind"] == "service"

        ident2, _r2 = identity.require(_Req(token=_token(private)), "confirm")
        assert ident2.audit()["kind"] == "person"


class TestTheFixtureMatchesTheRealDefaults:
    """A fixture that encodes stale defaults tests a system nobody runs.

    The `configured` fixture above carried the original
    `require_identity_for_{approve,confirm}: False`. When the defaults changed
    to True, every test using that fixture went on exercising the permissive
    system — and an unidentified caller passed a gate that is ON in production.
    """

    def test_every_gate_default_matches_settings_schema(self, configured):
        from modules.settings_schema import DEFAULTS

        for key, value in configured.items():
            if key.startswith(("require_identity_", "require_person_",
                               "service_allowed_")):
                assert DEFAULTS[key] == value, (
                    f"the fixture says {key}={value!r} but the real default is "
                    f"{DEFAULTS[key]!r} — the fixture is testing a system that "
                    "does not exist")
