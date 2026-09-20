"""Settings schema, secret encryption, and forward migration.

Constraint 1 requires that a user who never opens the Integrations panel sees
no behaviour change, so the central assertion here is that every new default
reproduces what the app did before the setting existed.
"""

import json

import pytest

from modules import secrets_store, settings_schema


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """Point the settings and Fernet key at a temp dir for the whole module."""
    path = tmp_path / "user_settings.json"
    key_path = tmp_path / "key.key"

    monkeypatch.setattr("modules.config.USER_SETTINGS_FILE", str(path))
    monkeypatch.setattr(secrets_store, "KEY_FILE", str(key_path))
    monkeypatch.setattr(secrets_store, "_fernet", None)
    return path


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


class TestSecretsStore:
    def test_round_trip(self, settings_file):
        token = secrets_store.encrypt_value("nbt_supersecret")
        assert secrets_store.is_encrypted(token)
        assert "nbt_supersecret" not in token          # not stored in the clear
        assert secrets_store.decrypt_value(token) == "nbt_supersecret"

    def test_legacy_plaintext_passes_through(self, settings_file):
        """Settings written by an older build stay readable."""
        assert secrets_store.decrypt_value("plain-token") == "plain-token"

    def test_empty_stays_empty(self, settings_file):
        assert secrets_store.encrypt_value("") == ""
        assert secrets_store.decrypt_value("") == ""

    def test_encrypting_twice_is_idempotent(self, settings_file):
        once = secrets_store.encrypt_value("abc")
        assert secrets_store.encrypt_value(once) == once

    def test_undecryptable_value_returns_empty_not_raise(self, settings_file):
        """A rotated key must not take the settings page down."""
        assert secrets_store.decrypt_value("enc:v1:not-a-valid-token") == ""

    def test_mask_never_reveals_value(self, settings_file):
        from modules.config import set_user_setting
        secrets_store.set_secret("netbox_token", "nbt_secret")
        assert "nbt_secret" not in secrets_store.mask("netbox_token")
        assert secrets_store.is_set("netbox_token")


class TestSchemaValidation:
    def test_defaults_are_valid(self):
        ok, err = settings_schema.validate(settings_schema.DEFAULTS)
        assert ok, err

    def test_rejects_out_of_range_port(self):
        ok, err = settings_schema.validate({"flask_port": 70000})
        assert not ok and "flask_port" in err

    def test_rejects_unknown_step_shell(self):
        ok, err = settings_schema.validate({"jenkins_step_shell": "powershell"})
        assert not ok

    def test_allows_unknown_keys(self):
        """Keys owned by older features must stay readable."""
        ok, _ = settings_schema.validate({"some_legacy_key": "value"})
        assert ok


class TestDefaultsPreserveBehaviour:
    """Each default must reproduce the behaviour that predates the setting."""

    @pytest.mark.parametrize("key,expected", [
        ("flask_host", "0.0.0.0"),            # config.FLASK_HOST
        ("flask_port", 5000),                 # config.FLASK_PORT
        ("auto_open_browser", True),          # unconditional webbrowser.open()
        ("jenkins_step_shell", "bat"),        # every generator emitted bat
        ("collector_trap_enabled", True),     # collectors ran unconditionally
        ("collector_netflow_enabled", True),
        ("netbox_verify_tls", True),
        ("nsot_git_author_name", "NMAS"),     # config_git._GIT_AUTHOR_NAME
        ("nsot_git_author_email", "nmas@localhost"),
    ])
    def test_default_matches_previous_behaviour(self, key, expected):
        assert settings_schema.DEFAULTS[key] == expected

    def test_netbox_writes_default_off(self):
        """The one intentional change: writes are fail-closed."""
        assert settings_schema.DEFAULTS["netbox_allow_writes"] is False

    def test_list_delete_cascade_default_off(self):
        assert settings_schema.DEFAULTS["netbox_remove_on_list_delete"] is False


class TestMigration:
    def test_seeds_defaults_on_first_run(self, settings_file):
        _write(settings_file, {})
        summary = settings_schema.migrate()
        assert summary["to_version"] == settings_schema.SCHEMA_VERSION
        saved = json.loads(settings_file.read_text())
        assert saved["settings_schema_version"] == settings_schema.SCHEMA_VERSION
        assert saved["jenkins_step_shell"] == "bat"

    def test_existing_values_win_over_defaults(self, settings_file):
        _write(settings_file, {"flask_port": 8080, "jenkins_step_shell": "sh"})
        settings_schema.migrate()
        saved = json.loads(settings_file.read_text())
        assert saved["flask_port"] == 8080
        assert saved["jenkins_step_shell"] == "sh"

    def test_encrypts_plaintext_netbox_token(self, settings_file):
        """The pre-existing plaintext token is upgraded in place."""
        _write(settings_file, {"netbox_token": "nbt_plaintext"})
        summary = settings_schema.migrate()
        assert "netbox_token" in summary["encrypted_keys"]

        saved = json.loads(settings_file.read_text())
        assert saved["netbox_token"] != "nbt_plaintext"
        assert secrets_store.is_encrypted(saved["netbox_token"])
        # and it still reads back correctly
        assert secrets_store.get_secret("netbox_token") == "nbt_plaintext"

    def test_migration_is_idempotent(self, settings_file):
        _write(settings_file, {"netbox_token": "nbt_plaintext"})
        settings_schema.migrate()
        first = settings_file.read_text()
        second_summary = settings_schema.migrate()
        assert second_summary["encrypted_keys"] == []
        assert json.loads(settings_file.read_text()) == json.loads(first)

    def test_old_keys_are_never_deleted(self, settings_file):
        _write(settings_file, {"ai_enabled": False, "some_legacy": 1})
        settings_schema.migrate()
        saved = json.loads(settings_file.read_text())
        assert saved["ai_enabled"] is False
        assert saved["some_legacy"] == 1
