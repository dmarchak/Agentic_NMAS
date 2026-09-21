"""D3: config masked by default, reveal audited, and the app log redacted.

The audit found nothing masked on any path OUT. D1 closed the model-API path.
This closes the other two: the HTTP API and the app log.
"""

import json
import logging
import time

import pytest

from modules import identity, redact

TEAM = "example-team.cloudflareaccess.com"
AUD = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
TUNNEL = "10.0.0.21"

CONFIG = ("hostname r1\n"
          "snmp-server community public RO\n"
          "username admin privilege 15 password cisco123\n"
          "interface Loopback0\n"
          " description mgmt\n")


@pytest.fixture
def keys():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def access(monkeypatch, keys, tmp_path):
    values = {"cf_access_team_domain": TEAM, "cf_access_aud": AUD,
              "cf_access_trusted_peers": TUNNEL,
              "require_identity_for_reveal": True,
              "require_person_for_reveal": True,
              "service_allowed_operations": []}
    monkeypatch.setattr(identity, "_setting",
                        lambda key, default=None: values.get(key, default))

    class _Key:
        key = keys.public_key()

    class _Client:
        def get_signing_key_from_jwt(self, token):
            return _Key()

    monkeypatch.setattr(identity, "_get_jwks_client", lambda: _Client())
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return values


def _person(private, email="dustin@example.com"):
    import jwt
    now = int(time.time())
    return jwt.encode({"type": "app", "aud": AUD, "iss": f"https://{TEAM}",
                       "email": email, "iat": now, "exp": now + 600,
                       "sub": "uuid-1"}, private, algorithm="RS256")


def _service(private):
    import jwt
    now = int(time.time())
    return jwt.encode({"type": "app", "aud": AUD, "iss": f"https://{TEAM}",
                       "common_name": "abc123.access", "iat": now,
                       "exp": now + 600, "sub": ""}, private, algorithm="RS256")


@pytest.fixture
def client(access, monkeypatch, tmp_path):
    import flask

    import routes.golden as golden

    monkeypatch.setattr(golden, "_repo_for", lambda name: str(tmp_path / "repo"))
    monkeypatch.setattr(golden, "_active_list", lambda data=None: "Lab")
    monkeypatch.setattr("modules.nsot.repo.golden_at",
                        lambda repo, host, ref: CONFIG)

    app = flask.Flask(__name__)
    app.register_blueprint(golden.bp)
    return app.test_client()


class TestConfigIsMaskedByDefault:
    def test_the_plain_request_is_masked(self, client):
        body = client.get("/golden/version/r1",
                          environ_base={"REMOTE_ADDR": TUNNEL}).get_json()

        assert body["masked"] is True
        assert "public" not in body["config"]
        assert "cisco123" not in body["config"]
        assert "<redacted:" in body["config"]
        # Still useful: the shape of the config survives.
        assert "hostname r1" in body["config"]
        assert "description mgmt" in body["config"]

    def test_the_diff_is_masked_too(self, client, monkeypatch):
        """A diff carries the same secrets on its - and + lines."""
        import routes.golden as golden

        monkeypatch.setattr("modules.nsot.repo.golden_at",
                            lambda repo, host, ref: CONFIG if ref == "a" else
                            CONFIG.replace("cisco123", "newpassword99"))
        body = client.get("/golden/diff/r1?a=a&b=b",
                          environ_base={"REMOTE_ADDR": TUNNEL}).get_json()

        assert body["masked"] is True
        assert "cisco123" not in body["diff"]
        assert "newpassword99" not in body["diff"]

    def test_a_short_community_is_covered(self, client):
        """6 characters — below the value floor, caught positionally."""
        body = client.get("/golden/version/r1",
                          environ_base={"REMOTE_ADDR": TUNNEL}).get_json()
        assert "community public" not in body["config"]


class TestRevealRequiresAPersonAndIsAudited:
    def test_an_unidentified_reveal_is_refused_and_still_masked(self, client):
        response = client.get("/golden/version/r1?reveal=1",
                              environ_base={"REMOTE_ADDR": TUNNEL})
        body = response.get_json()

        assert response.status_code == 403
        assert body["masked"] is True
        assert "public" not in body["config"], (
            "a refused reveal must not return the secret anyway")

    def test_a_service_reveal_is_refused(self, client, keys):
        response = client.get(
            "/golden/version/r1?reveal=1",
            headers={identity.JWT_HEADER: _service(keys)},
            environ_base={"REMOTE_ADDR": TUNNEL})
        body = response.get_json()

        assert response.status_code == 403
        assert body["outcome"] == "person_required"
        assert body["masked"] is True
        assert "cisco123" not in body["config"]

    def test_a_person_may_reveal(self, client, keys):
        body = client.get("/golden/version/r1?reveal=1",
                          headers={identity.JWT_HEADER: _person(keys)},
                          environ_base={"REMOTE_ADDR": TUNNEL}).get_json()

        assert body["masked"] is False
        assert "snmp-server community public RO" in body["config"]
        assert body["revealed_by"] == "dustin@example.com"

    def test_the_reveal_is_recorded(self, client, keys):
        from modules import reveal_audit

        client.get("/golden/version/r1?reveal=1&ref=HEAD",
                   headers={identity.JWT_HEADER: _person(keys)},
                   environ_base={"REMOTE_ADDR": TUNNEL})
        rows = reveal_audit.entries()

        assert len(rows) == 1
        assert rows[0]["actor"] == "dustin@example.com"
        assert rows[0]["kind"] == "person"
        assert rows[0]["what"] == "golden_config"
        assert rows[0]["target"] == "r1"
        assert rows[0]["peer"] == TUNNEL

    def test_the_audit_records_what_was_looked_at_not_what_was_seen(
            self, client, keys):
        """A trail that copies the secret has become a second place it lives."""
        from modules import reveal_audit

        client.get("/golden/version/r1?reveal=1",
                   headers={identity.JWT_HEADER: _person(keys)},
                   environ_base={"REMOTE_ADDR": TUNNEL})
        raw = json.dumps(reveal_audit.entries())

        assert "public" not in raw
        assert "cisco123" not in raw
        assert "hostname r1" not in raw

    def test_a_refused_reveal_records_nothing(self, client, keys):
        from modules import reveal_audit

        client.get("/golden/version/r1?reveal=1",
                   headers={identity.JWT_HEADER: _service(keys)},
                   environ_base={"REMOTE_ADDR": TUNNEL})
        assert reveal_audit.entries() == []

    def test_a_masked_read_records_nothing(self, client):
        """The trail records reveals, not requests — or it drowns."""
        from modules import reveal_audit

        for _ in range(5):
            client.get("/golden/version/r1",
                       environ_base={"REMOTE_ADDR": TUNNEL})
        assert reveal_audit.entries() == []


class TestTheAppLogIsRedacted:
    @pytest.fixture
    def handler(self, monkeypatch):
        from modules import credentials

        values = {"lab:r1:snmp_community_ro": "Str0ngC0mmunityValue"}
        monkeypatch.setattr(credentials, "get_template_secret",
                            lambda name: values.get(name, ""))
        monkeypatch.setattr(credentials, "list_template_secrets",
                            lambda ln="": [{"name": n, "secret_kind": "plaintext",
                                            "rotatable": True} for n in values])
        monkeypatch.setattr(credentials, "device_credential_values", dict)

        records = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(self.format(record))

        h = _Capture()
        h.setFormatter(logging.Formatter("%(message)s"))
        redact.install_log_redaction(h)
        return h, records

    def _log(self, handler, fn):
        h, records = handler
        logger = logging.getLogger("test.redaction")
        logger.handlers = [h]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        fn(logger)
        return records

    def test_a_secret_in_the_message_is_redacted(self, handler):
        out = self._log(handler, lambda lg: lg.info(
            "pushed: snmp-server community Str0ngC0mmunityValue RO"))
        assert "Str0ngC0mmunityValue" not in out[0]
        assert "<redacted:" in out[0]

    def test_a_secret_in_an_ARGUMENT_is_redacted(self, handler):
        """Far more common than one in the format string."""
        out = self._log(handler, lambda lg: lg.info(
            "device said: %s", "snmp-server community Str0ngC0mmunityValue RO"))
        assert "Str0ngC0mmunityValue" not in out[0]

    def test_a_positional_secret_is_redacted_even_if_unknown(self, handler):
        """A device never onboarded — nothing in the store to match."""
        out = self._log(handler, lambda lg: lg.warning(
            "config: username admin privilege 15 password NeverExtracted"))
        assert "NeverExtracted" not in out[0]

    def test_an_exception_message_is_redacted(self, handler):
        def _raise(lg):
            try:
                raise ValueError(
                    "rejected: snmp-server community Str0ngC0mmunityValue RO")
            except ValueError:
                lg.exception("push failed")
        out = self._log(handler, _raise)
        assert "Str0ngC0mmunityValue" not in "\n".join(out)

    def test_ordinary_lines_are_untouched(self, handler):
        out = self._log(handler, lambda lg: lg.info(
            "pipeline[8.5/save_golden]: 3 capture(s) handed to the batch"))
        assert out[0] == "pipeline[8.5/save_golden]: 3 capture(s) handed to the batch"

    def test_it_fails_open_rather_than_dropping_records(self, handler,
                                                         monkeypatch):
        """A log that silently loses entries is the worse failure."""
        def _boom(*a, **k):
            raise RuntimeError("store exploded")
        monkeypatch.setattr(redact, "known_secret_values", _boom)

        out = self._log(handler, lambda lg: lg.info("something happened"))
        assert out and "something happened" in out[0]

    def test_installation_is_idempotent(self):
        h = logging.Handler()
        assert redact.install_log_redaction(h) is True
        assert redact.install_log_redaction(h) is False
        assert sum(isinstance(f, redact.RedactingFilter) for f in h.filters) == 1

    def test_the_app_installs_it_on_the_file_handler(self):
        import inspect

        import app as app_module

        source = inspect.getsource(app_module)
        assert "install_log_redaction(file_handler)" in source
