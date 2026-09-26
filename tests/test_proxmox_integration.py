"""The Proxmox client: read-only, token-authenticated, never raising (B6).

No network: `_get` is replaced by a spy recording the paths asked for, so
these pin what is READ, and that nothing is read before it is configured.
"""

import pytest

import modules.integrations.proxmox as P

SETTINGS = {"proxmox_url": "https://pve.example:8006", "proxmox_node": "pve",
            "proxmox_token_id": "nmas-monitor@pve!job-health",
            "proxmox_backup_storage": "vzdump-sda", "proxmox_backup_vmids": "100, 102",
            "proxmox_verify_tls": True}


@pytest.fixture
def client(monkeypatch):
    settings = dict(SETTINGS)
    secrets = {"proxmox_token_secret": "0000-token-secret"}
    import modules.integrations.base as base

    # Both bindings: the client reads its own keys through P.get_setting and
    # its URL through the base class's (CLAUDE.md: *a test that passes alone
    # and fails in the suite is telling you which binding it is missing*).
    for mod in (P, base):
        monkeypatch.setattr(mod, "get_setting", lambda k, d=None: settings.get(k, d))
    monkeypatch.setattr(P, "get_secret", lambda k, d="": secrets.get(k, d))
    c = P.ProxmoxIntegration()
    c._settings, c._secrets = settings, secrets
    return c


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return {"data": self._data}


def test_the_token_header_is_proxmoxs_form(client):
    assert client._auth_headers() == {
        "Authorization": "PVEAPIToken=nmas-monitor@pve!job-health=0000-token-secret"}


def test_the_vm_list_is_parsed_and_a_bad_entry_refused(client):
    assert client.vmids() == [100, 102]
    client._settings["proxmox_backup_vmids"] = "100,1O2"
    with pytest.raises(ValueError) as excinfo:
        client.vmids()
    assert "1O2" in str(excinfo.value)


def test_every_missing_value_is_named(client):
    assert client.missing_settings() == [] and client.is_configured()
    client._settings["proxmox_node"] = ""
    client._secrets.clear()
    assert client.missing_settings() == ["proxmox_node", "proxmox_token_secret"]
    assert not client.is_configured()


def test_it_reads_exactly_these_paths(client, monkeypatch):
    asked = []

    def spy(path, **params):
        asked.append((path, params))
        return {"ok": True, "response": _Resp([])}

    monkeypatch.setattr(client, "_get", spy)
    for method in (client.backups, client.vzdump_tasks, client.storage_status,
                   client.thin_pools):
        assert method()["ok"] is True
    assert [p for p, _ in asked] == [
        "api2/json/nodes/pve/storage/vzdump-sda/content",
        "api2/json/nodes/pve/tasks",
        "api2/json/nodes/pve/storage/vzdump-sda/status",
        "api2/json/nodes/pve/disks/lvmthin"]
    assert asked[0][1] == {"content": "backup"}
    assert asked[1][1]["typefilter"] == "vzdump"


def test_a_failed_request_is_an_error_never_data(client, monkeypatch):
    monkeypatch.setattr(client, "_get", lambda path, **p: {"ok": False, "error": "HTTP 401"})
    assert client.backups() == {"ok": False, "error": "HTTP 401"}


def test_it_is_registered_and_its_secret_is_encrypted():
    from modules.integrations import REGISTRY
    from modules.secrets_store import SECRET_KEYS

    assert REGISTRY["proxmox"] is P.ProxmoxIntegration
    assert "proxmox_token_secret" in SECRET_KEYS


def test_the_settings_card_carries_every_key_the_client_reads():
    """A key only curl could set is a feature no operator has."""
    from tests.js_source import read_shipped

    spec = read_shipped("static/js/gen/partials__settings_integrations.1.js")
    for key in (P.ProxmoxIntegration.plain_keys + P.ProxmoxIntegration.secret_keys
                + (P.ProxmoxIntegration.url_key,)):
        assert f"key: '{key}'" in spec, key


class TestTheTlsWarningIsScopedToThisClient:
    """Verify TLS off for a self-signed certificate is deliberate, and urllib3
    warned four times per run. The warning is correct, so it is silenced for
    THIS client's requests only, replaced by one log line."""

    def _emit(self, *a, **k):
        import warnings
        from urllib3.exceptions import InsecureRequestWarning

        warnings.warn("Unverified HTTPS request", InsecureRequestWarning)
        return {"ok": True, "response": _Resp([])}

    def test_its_own_requests_are_quiet_and_logged_once(self, client, monkeypatch, caplog):
        import warnings
        import modules.integrations.base as base

        client._settings["proxmox_verify_tls"] = False
        monkeypatch.setattr(base.IntegrationClient, "_get", self._emit)
        monkeypatch.setattr(P.ProxmoxIntegration, "_warned_unverified", False)
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            client.backups()
            client.storage_status()
        assert [w for w in seen if "Unverified" in str(w.message)] == []
        assert sum("TLS verification is OFF" in r.getMessage() for r in caplog.records) == 1

    def test_everything_else_still_gets_the_warning(self, client, monkeypatch):
        import warnings
        import modules.integrations.base as base

        client._settings["proxmox_verify_tls"] = False
        monkeypatch.setattr(base.IntegrationClient, "_get", self._emit)
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            client.backups()
            self._emit()                        # some other code's request
        assert len([w for w in seen if "Unverified" in str(w.message)]) == 1

    def test_with_verification_on_nothing_is_suppressed(self, client, monkeypatch):
        import warnings
        import modules.integrations.base as base

        monkeypatch.setattr(base.IntegrationClient, "_get", self._emit)
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            client.backups()
        assert len([w for w in seen if "Unverified" in str(w.message)]) == 1
