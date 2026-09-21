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

    def test_the_app_covers_every_handler_not_just_the_file_one(self):
        """A StreamHandler to stdout is the systemd journal.

        And the file handler only exists when app.debug is false, so installing
        on it alone leaves debug runs entirely unredacted.
        """
        import inspect

        import app as app_module

        source = inspect.getsource(app_module)
        assert "redact_all_handlers()" in source
        assert "guard_new_handlers()" in source
        assert "install_log_redaction(file_handler)" not in source


class TestEveryHandlerIsCovered:
    """A filter on one handler leaves every other handler unredacted.

    And a filter on the root *logger* would not help: a record emitted by a
    child logger is handed to ancestor HANDLERS without ancestor logger filters
    being consulted. Handler filters are the only ones every record must pass.
    """

    @pytest.fixture
    def secret(self, monkeypatch):
        from modules import credentials

        values = {"lab:r1:snmp_community_ro": "Str0ngC0mmunityValue"}
        monkeypatch.setattr(credentials, "get_template_secret",
                            lambda name: values.get(name, ""))
        monkeypatch.setattr(credentials, "list_template_secrets",
                            lambda ln="": [{"name": n, "secret_kind": "plaintext",
                                            "rotatable": True} for n in values])
        monkeypatch.setattr(credentials, "device_credential_values", dict)
        redact.invalidate_cache()
        return values

    def _capture(self):
        records = []

        class _Cap(logging.Handler):
            def emit(self, record):
                records.append(self.format(record))
        h = _Cap()
        h.setFormatter(logging.Formatter("%(message)s"))
        return h, records

    def test_a_child_logger_record_is_redacted_in_EVERY_handler(self, secret,
                                                                 monkeypatch):
        """The case the file-handler-only install missed."""
        file_like, file_out = self._capture()
        stream_like, stream_out = self._capture()

        root = logging.getLogger()
        monkeypatch.setattr(root, "handlers", [file_like, stream_like])
        monkeypatch.setattr(root, "level", logging.DEBUG)

        installed = redact.redact_all_handlers()
        assert installed >= 2

        child = logging.getLogger("modules.some.deep.child")
        monkeypatch.setattr(child, "handlers", [])
        child.propagate = True
        child.setLevel(logging.DEBUG)
        child.warning("snmp-server community Str0ngC0mmunityValue RO")

        assert file_out and stream_out, "both handlers should have received it"
        for out in (file_out, stream_out):
            assert "Str0ngC0mmunityValue" not in out[0]
            assert "<redacted:" in out[0]

    def test_a_handler_added_later_inherits_the_filter(self, secret):
        """Coverage established once at startup decays."""
        redact.guard_new_handlers()

        late, out = self._capture()
        logger = logging.getLogger("added.later")
        logger.handlers = []
        logger.addHandler(late)          # the patched addHandler
        logger.propagate = False
        logger.setLevel(logging.DEBUG)

        assert any(isinstance(f, redact.RedactingFilter) for f in late.filters)
        logger.error("password Str0ngC0mmunityValue")
        assert "Str0ngC0mmunityValue" not in out[0]

    def test_coverage_is_reported(self, monkeypatch):
        bare, _ = self._capture()
        root = logging.getLogger()
        monkeypatch.setattr(root, "handlers", [bare])

        health = redact.health()
        assert health["log_handlers_unprotected"] >= 1
        assert health["healthy"] is False

        redact.redact_all_handlers()
        assert redact.health()["log_handlers_unprotected"] == 0


class TestRedactionFailureIsVisible:
    """Failing open is only defensible while the failure is visible.

    A log line saying "the log is unreliable" is written in the medium that
    just became unreliable.
    """

    def test_an_unreadable_store_marks_redaction_unhealthy(self, monkeypatch):
        from modules import credentials

        def _boom(*a, **k):
            raise RuntimeError("store exploded")
        monkeypatch.setattr(credentials, "list_template_secrets", _boom)
        redact.invalidate_cache()

        redact.known_secret_values()
        health = redact.health()

        assert health["healthy"] is False
        assert health["redaction_failures"] >= 1
        assert health["last_error"] == "RuntimeError"
        assert health["first_failure_at"]

    def test_the_filter_does_not_recurse_when_the_store_fails(self, monkeypatch):
        """known_secret_values() logs on failure; that record re-enters here.

        Unbounded recursion that can hang the process, not merely the test
        suite it was first seen in.
        """
        from modules import credentials

        def _boom(*a, **k):
            raise RuntimeError("store exploded")
        monkeypatch.setattr(credentials, "list_template_secrets", _boom)
        redact.invalidate_cache()

        records = []

        class _Cap(logging.Handler):
            def emit(self, record):
                records.append(self.format(record))

        h = _Cap()
        h.setFormatter(logging.Formatter("%(message)s"))
        redact.install_log_redaction(h)
        logger = logging.getLogger("recursion.guard")
        logger.handlers = [h]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)

        logger.error("a record that triggers the failure path")
        assert len(records) == 1, "the filter recursed"

    def test_health_is_reported_in_the_diagnostic(self):
        import inspect

        import routes.identity as route_mod

        assert "_redaction_health()" in inspect.getsource(route_mod.status)
        assert "redact.health()" in inspect.getsource(route_mod._redaction_health)


class TestTheSecretTableIsCached:
    def test_a_newly_stored_secret_is_redacted_immediately(self, tmp_path,
                                                            monkeypatch):
        """Not at the next cache expiry — the window right after an extraction
        is exactly when config carrying the secret is flowing."""
        from modules import credentials

        monkeypatch.setattr(credentials, "_FILE",
                            str(tmp_path / "credential_profiles.json"))
        monkeypatch.setattr(credentials, "device_credential_values", dict)
        redact.invalidate_cache()

        # A banner carries no secret POSITION, so only value matching can
        # cover it — which isolates the cache question from the positional one.
        prose = "banner motd ^JustStoredValue^"
        assert redact.redact_text(prose) == prose, (
            "nothing is stored yet, so there is no value to match")

        credentials.set_template_secret("lab:r1:snmp_community_ro",
                                        "JustStoredValue", list_name="lab")
        out = redact.redact_text(prose)
        assert "JustStoredValue" not in out, (
            "a freshly stored secret must be redacted from the next record, "
            "not from the next cache expiry")
        assert "<redacted:snmp_community_ro>" in out


class TestTheReentrantPathStillMasks:
    """A reentrant record is a credential-store failure — the riskiest kind.

    Its exception text can quote a config line or a ciphertext verbatim.
    Skipping ALL redaction to avoid recursion would mean the one record most
    likely to carry a secret is the one written in the clear. Only the VALUE
    lookup recurses; positional needs no store, so positional still runs.
    """

    def _capture(self):
        records = []

        class _Cap(logging.Handler):
            def emit(self, record):
                records.append(self.format(record))
        h = _Cap()
        h.setFormatter(logging.Formatter("%(message)s"))
        redact.install_log_redaction(h)
        return h, records

    def _exploding_store(self, monkeypatch):
        from modules import credentials

        def _boom(*a, **k):
            raise RuntimeError(
                "store read failed near: snmp-server community public RO")
        monkeypatch.setattr(credentials, "list_template_secrets", _boom)
        redact.invalidate_cache()

    def test_a_reentrant_record_is_still_positionally_masked(self, monkeypatch):
        self._exploding_store(monkeypatch)
        h, out = self._capture()
        logger = logging.getLogger("reentrant.mask")
        logger.handlers = [h]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)

        # The outer record triggers the store failure; the inner diagnostic it
        # produces is the reentrant one.
        logger.error("config seen: username admin privilege 15 password s3cret99")

        joined = "\n".join(out)
        assert "s3cret99" not in joined
        assert "<redacted:user_password>" in joined
        assert len(out) >= 1

    def test_the_diagnostic_itself_is_masked(self, monkeypatch):
        """The inner record quotes a config line in its exception text."""
        from modules import credentials

        def _boom(*a, **k):
            raise RuntimeError("x")
        monkeypatch.setattr(credentials, "list_template_secrets", _boom)
        redact.invalidate_cache()

        h, out = self._capture()
        logger = logging.getLogger("modules.redact")
        logger.handlers = [h]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)

        # Emit a record from *inside* redaction by marking the guard active.
        redact.RedactingFilter._local.active = True
        try:
            logger.error("store failure near snmp-server community public RO")
        finally:
            redact.RedactingFilter._local.active = False

        assert out, "the diagnostic must survive"
        assert "community public" not in out[0]
        assert "<redacted:snmp_community>" in out[0]

    def test_it_still_does_not_recurse(self, monkeypatch):
        self._exploding_store(monkeypatch)
        h, out = self._capture()
        logger = logging.getLogger("reentrant.norecurse")
        logger.handlers = [h]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)

        logger.error("a record")
        assert len(out) == 1


class TestEveryCredentialWriteInvalidatesTheCache:
    """Rotation is the case this exists for.

    Item (4) rotates the router passwords. With only set_template_secret()
    invalidating, a brand-new password would be unredacted for up to 30
    seconds — exactly while the rotation logs its commands and its verify
    output.
    """

    @pytest.fixture
    def store(self, tmp_path, monkeypatch):
        from modules import credentials

        monkeypatch.setattr(credentials, "_FILE",
                            str(tmp_path / "credential_profiles.json"))
        monkeypatch.setattr(credentials, "device_credential_values", dict)
        return credentials

    def _warm(self):
        """Populate the cache, and return the view it holds."""
        return dict(redact.known_secret_values())

    def _stale(self):
        """True if the cache is still serving the view captured by _warm()."""
        return redact._cache["values"] is not None

    def test_storing_a_template_secret_is_visible_immediately(self, store):
        """Not at the next TTL expiry.

        Note the cache may be repopulated within the same call — the write's
        own `log.info` passes through the redacting filter, which rebuilds it.
        That is the behaviour working: the log line announcing the write is
        already redacted against the value it just stored.
        """
        before = self._warm()
        assert "AValueLongEnough" not in before

        store.set_template_secret("lab:r1:x", "AValueLongEnough", list_name="lab")
        assert "AValueLongEnough" in redact.known_secret_values()

    def test_saving_a_profile_is_visible_immediately(self, store, monkeypatch):
        from modules import credentials

        monkeypatch.undo()          # let the real device_credential_values run
        monkeypatch.setattr(credentials, "_FILE", store._FILE)
        monkeypatch.setattr("modules.config.LISTS_DIR", "/nonexistent")
        self._warm()

        store.save_profile("default", "admin", "ProfilePassword1")
        assert "ProfilePassword1" in redact.known_secret_values()

    def test_a_device_override_is_visible_immediately(self, store, monkeypatch):
        from modules import credentials

        monkeypatch.undo()
        monkeypatch.setattr(credentials, "_FILE", store._FILE)
        monkeypatch.setattr("modules.config.LISTS_DIR", "/nonexistent")
        self._warm()

        store.set_device_override("203.0.113.1", "admin", "OverridePassword1")
        assert "OverridePassword1" in redact.known_secret_values()

    def test_deleting_a_profile_drops_it_from_the_table(self, store, monkeypatch):
        from modules import credentials

        monkeypatch.undo()
        monkeypatch.setattr(credentials, "_FILE", store._FILE)
        monkeypatch.setattr("modules.config.LISTS_DIR", "/nonexistent")
        store.save_profile("temp", "admin", "TempPassword123")
        assert "TempPassword123" in self._warm()

        store.delete_profile("temp")
        assert "TempPassword123" not in redact.known_secret_values()

    def test_the_scope_migration_invalidates(self, store):
        store.set_template_secret("r1:legacy", "LegacyValue123")
        self._warm()
        redact.invalidate_cache()
        redact.known_secret_values()
        assert self._stale()

        store.migrate_template_secrets_to_list_scope("Default", dry_run=False)
        # The value is unchanged by a re-key, but the table was rebuilt.
        assert "LegacyValue123" in redact.known_secret_values()

    def test_rewriting_devices_csv_invalidates(self, tmp_path, monkeypatch):
        """Device passwords live in the CSV, not the credential store."""
        from modules import device

        monkeypatch.setattr(device, "_refuse_if_netbox_sourced",
                            lambda f, w: None)
        redact.invalidate_cache()
        redact.known_secret_values()
        assert self._stale()

        device.write_devices_csv([], str(tmp_path / "devices.csv"))
        assert redact._cache["values"] is None, (
            "a CSV rewrite must drop the cached table")

    def test_the_invalidation_is_at_the_store_chokepoint(self):
        """Six call sites is six chances to add a seventh and forget."""
        import inspect

        from modules import credentials

        assert "invalidate_cache" in inspect.getsource(credentials._save)

    def test_a_rotated_password_is_redacted_on_the_very_next_record(
            self, store, monkeypatch):
        """The end-to-end property item (4) depends on."""
        prose = "verify output: banner motd ^Rotated-Password-99^"
        assert redact.redact_text(prose) == prose

        store.set_template_secret("lab:r1:user_admin_password",
                                  "Rotated-Password-99", list_name="lab")

        out = redact.redact_text(prose)
        assert "Rotated-Password-99" not in out
        assert "<redacted:user_admin_password>" in out


class TestTheCanaryReplacesGreppingTheLog:
    """Ask each handler whether a record reaching IT comes out masked.

    `handler.filters` answers a weaker question: a filter can be present and
    shadowed by an earlier one returning False, installed on a handler that was
    later replaced, or raising. The canary runs the real filter chain over a
    synthetic record and reads the result.

    It never emits — the record is filtered, not handled — so no canary line
    ever appears in a log.
    """

    def test_an_unprotected_handler_is_reported_as_leaking(self):
        h = logging.StreamHandler()
        result = redact.canary(h)
        assert result["ok"] is False
        assert result["dropped"] is False

    def test_a_protected_handler_passes(self):
        h = logging.StreamHandler()
        redact.install_log_redaction(h)
        assert redact.canary(h)["ok"] is True

    def test_a_shadowed_filter_is_caught(self):
        """A filter present but never reached is not protection.

        `handler.filters` would say this handler is covered.
        """
        h = logging.StreamHandler()
        redact.install_log_redaction(h)
        # An earlier filter that drops nothing but raises would break the chain;
        # here, one that *passes* but is ordered before ours is fine. The real
        # hazard is a filter returning False first — then nothing is written at
        # all, which is reported as dropped rather than leaking.
        h.filters.insert(0, lambda record: False)
        result = redact.canary(h)
        assert result["dropped"] is True
        assert result["ok"] is True

    def test_a_raising_filter_is_reported_not_swallowed(self):
        class _Boom(logging.Filter):
            def filter(self, record):
                raise RuntimeError("bad filter")

        h = logging.StreamHandler()
        h.addFilter(_Boom())
        result = redact.canary(h)
        assert result["ok"] is False
        assert result["error"] == "RuntimeError"

    def test_the_canary_emits_nothing(self):
        """No canary line may appear in any log."""
        records = []

        class _Cap(logging.Handler):
            def emit(self, record):
                records.append(record)

        h = _Cap()
        redact.install_log_redaction(h)
        redact.canary(h)
        assert records == [], "the canary must not be emitted"

    def test_health_reports_the_canary_and_fails_on_a_leak(self, monkeypatch):
        bare = logging.StreamHandler()
        root = logging.getLogger()
        monkeypatch.setattr(root, "handlers", [bare])

        health = redact.health()
        assert health["canary_leaking"] >= 1
        assert health["healthy"] is False
        assert health["canary_leaking_detail"][0]["handler"] == "StreamHandler"

        redact.redact_all_handlers()
        healthy = redact.health()
        assert healthy["canary_leaking"] == 0
        assert healthy["healthy"] is True

    def test_the_report_names_where_a_leaking_handler_writes(self, tmp_path,
                                                             monkeypatch):
        """An operator needs the file, not just the class name."""
        path = tmp_path / "unprotected.log"
        h = logging.FileHandler(str(path))
        try:
            root = logging.getLogger()
            monkeypatch.setattr(root, "handlers", [h])
            detail = redact.canary_report()["leaking_detail"]
            assert detail and str(path) in detail[0]["target"]
        finally:
            h.close()


class TestAMentionIsNotASetting:
    """A config keyword named with nothing after it is a mention.

    Found in the live log:

        show running-config | include snmp-server community [in /home/…:2613]

    An operator searching for the community — no value present — and the token
    the pattern ate was the log formatter's own `[in`. Masking it corrupted the
    line and protected nothing.
    """

    def test_a_filter_expression_is_not_masked(self):
        line = ("Bulk execute on 1 devices: show running-config | include "
                "snmp-server community [in /home/x/app.py:2613]")
        assert redact.redact_positional(line) == line

    def test_bracketed_and_piped_tokens_are_never_values(self):
        for tail in ("[in /path:1]", "| include foo", "<something>", "(none)"):
            line = f"snmp-server community {tail}"
            assert redact.redact_positional(line) == line, tail

    def test_a_real_value_is_still_masked(self):
        """The guard must not have been bought at the cost of the point."""
        for line, token in (
            ("snmp-server community public RO", "public"),
            ("username admin privilege 15 password cisco123", "cisco123"),
            ("enable secret 5 $1$xyz$hashvalue", "$1$xyz$hashvalue"),
            ("key-string MySharedKey", "MySharedKey"),
        ):
            out = redact.redact_positional(line)
            assert token not in out, line
            assert "<redacted:" in out, line


class TestTheCanaryCoversEveryShapeTheToolEmits:
    """A canary that only tests shapes we already handle finds nothing new.

    The `algorithm-type` shape was a live gap: the pattern allowed
    `username X [privilege N] secret <v>` but not an `algorithm-type` clause
    between them, so the exact line the credential rotation sends matched
    nothing and the password would have reached the log in clear.
    """

    def test_the_rotation_command_shape_is_a_canary(self):
        shapes = dict(redact.CANARY_LINES)
        assert "user_secret_algo" in shapes
        assert "algorithm-type scrypt secret" in shapes["user_secret_algo"]

    def test_every_canary_shape_is_masked_by_a_protected_handler(self):
        h = logging.StreamHandler()
        redact.install_log_redaction(h)
        result = redact.canary(h)
        assert result["ok"] is True
        assert result["leaked_shapes"] == []

    def test_an_unprotected_handler_names_every_leaking_shape(self):
        result = redact.canary(logging.StreamHandler())
        assert result["ok"] is False
        assert set(result["leaked_shapes"]) == set(dict(redact.CANARY_LINES))

    def test_a_broken_pattern_is_caught_by_shape(self, monkeypatch):
        """Remove the user-password pattern; only that shape must leak."""
        kept = tuple(p for p in redact._POSITIONAL if p[0] != "user_password")
        monkeypatch.setattr(redact, "_POSITIONAL", kept)

        h = logging.StreamHandler()
        redact.install_log_redaction(h)
        result = redact.canary(h)

        assert result["ok"] is False
        assert set(result["leaked_shapes"]) == {"user_password",
                                                "user_secret_algo"}

    def test_the_rotation_command_the_tool_builds_is_the_shape_covered(self):
        """Not a hand-written approximation of it."""
        from modules.nsot import credential_rotation as cr

        real = cr.rotation_command("admin", 15, "CanaryTokenC3")
        assert real == dict(redact.CANARY_LINES)["user_secret_algo"]
