"""P.21, credential expiry and health (signed off 2026-10-03): the credential-health reader and
its Needs attention rows. Metadata only, never a value.

- The signed thresholds, at their edges: an exposed expiry is expired, danger within 7 days,
  warning within 30, ok within a year, listed beyond a year or never; an age past 180 days is a
  warning, an unknown age is listed.
- Each source with the service faked: NetBox's token chosen by the suffix it shows (refused as
  unknown when it cannot be told which is the tool's), Proxmox's token record (0 is never),
  Grafana's DECLARED expiry (blank listed, a non-date unknown), each device's last rotation from
  the rotation record, each SNMP community from the store's `last_rotated`.
- A source that raises is said; the others are kept.
- No planted secret value reaches the stored value.
- The rows: expired and danger are danger, warning is a warning, an old credential names Rotate,
  an unreadable expiry is a row; ok and listed are none.
"""

import json
import time

import pytest

from modules import attention as A
from modules.readers import credential_health as CH

NOW = 1_800_000_000.0
DAY = 86400.0


class TestTheThresholds:
    @pytest.mark.parametrize("days, state", [
        (-1, "expired"), (0.5, "danger"), (7, "danger"), (7.1, "warning"), (30, "warning"),
        (30.1, "ok"), (365, "ok"), (366, "listed")])
    def test_an_exposed_expiry(self, days, state):
        assert CH.judge_expiry(NOW + days * DAY, NOW) == state

    def test_never_is_listed(self):
        assert CH.judge_expiry(None, NOW) == "listed"

    def test_an_age(self):
        assert CH.judge_age(NOW - 181 * DAY, NOW) == "warning"
        assert CH.judge_age(NOW - 179 * DAY, NOW) == "ok"
        assert CH.judge_age(None, NOW) == "listed"


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Session:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    def get(self, url, **kw):
        return _Resp(self.payload, self.status)


TOKEN = "nbtok-PLANTED-0123456789abcdWXYZ"


@pytest.fixture
def netbox(monkeypatch):
    state = {"payload": {"results": []}, "status": 200}
    monkeypatch.setattr("modules.netbox_client._nb_ready",
                        lambda: (True, "", _Session(state["payload"], state["status"]),
                                 "http://192.0.2.7"))
    monkeypatch.setattr("modules.netbox_client.get_netbox_config",
                        lambda: {"url": "http://192.0.2.7", "token": TOKEN})
    return state


class TestNetBox:
    def test_the_tools_token_by_its_suffix(self, netbox):
        netbox["payload"] = {"results": [
            {"display": "**********1111", "expires": "2026-01-01T00:00:00Z"},
            {"display": "**********WXYZ", "expires": "2027-12-01T00:00:00Z"}]}
        (c,) = CH.netbox(NOW)
        assert c["state"] == "ok" and c["expires_at"] == "2027-12-01T00:00:00Z"
        assert "API tokens" in c["renew_at"] and "Settings" in c["put_at"]

    def test_which_is_the_tools_cannot_be_told(self, netbox):
        netbox["payload"] = {"results": [{"display": "**********1111"}]}
        (c,) = CH.netbox(NOW)
        assert c["state"] == "unknown" and "cannot be told" in c["why"]

    def test_an_unreadable_list_is_unknown_naming_only_the_error_kind(self, netbox):
        netbox["status"] = 403
        (c,) = CH.netbox(NOW)
        assert c["state"] == "unknown" and c["why"].endswith("RuntimeError")


class TestProxmoxAndGrafana:
    def test_proxmox_zero_is_never(self, monkeypatch):
        from modules.integrations.proxmox import ProxmoxIntegration
        monkeypatch.setattr(ProxmoxIntegration, "is_configured", lambda self: True)
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: "nmas@pve!probe" if k == "proxmox_token_id" else d)
        got = {"data": {"expire": 0}}
        monkeypatch.setattr(ProxmoxIntegration, "_get",
                            lambda self, path, **p: {"ok": True, "response": _Resp(got)})
        assert CH.proxmox(NOW)[0]["state"] == "listed"
        got["data"]["expire"] = int(NOW + 5 * DAY)
        assert CH.proxmox(NOW)[0]["state"] == "danger"

    @pytest.mark.parametrize("declared, state", [("", "listed"), ("2027-02-01", "ok"),
                                                 ("not a date", "unknown")])
    def test_grafana_by_its_declared_expiry(self, monkeypatch, declared, state):
        monkeypatch.setattr("modules.secrets_store.get_secret", lambda k: "tok")
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: declared if k == "grafana_token_expires" else d)
        (c,) = CH.grafana(time.mktime((2026, 10, 3, 0, 0, 0, 0, 0, 0)))
        assert c["state"] == state, c


class TestAges:
    def test_each_device_by_its_last_rotation(self, monkeypatch):
        from modules.nsot import credential_rotation as cr
        monkeypatch.setattr("modules.job_health.known_devices", lambda: ({"r2", "s1"}, ""))
        monkeypatch.setattr(cr, "rotation_records", lambda: [
            {"phase": "rotate", "device": "r2", "state": cr.ROTATED_PERSISTED,
             "at": CH._iso(NOW - 200 * DAY)},
            {"phase": "persist", "device": "s1", "state": cr.SAVE_PERSISTED,
             "at": CH._iso(NOW - 1 * DAY)}])
        got = {c["id"]: c for c in CH.device_ages(NOW)}
        assert got["device:r2"]["state"] == "warning" and "Rotate" in got["device:r2"]["renew_at"]
        assert got["device:s1"]["state"] == "listed", "a save is not a rotation"

    def test_each_community_by_when_it_was_set(self, monkeypatch):
        monkeypatch.setattr("modules.credentials.list_template_secrets", lambda l="": [
            {"name": "lab:r2:snmp_community_ro", "list": "lab", "device": "r2",
             "last_rotated": NOW - 300 * DAY},
            {"name": "lab:r2:user_admin_password", "list": "lab", "device": "r2",
             "last_rotated": NOW}])
        (c,) = CH.community_ages(NOW)
        assert c["state"] == "warning" and c["id"] == "secret:lab:r2:snmp_community_ro"


class TestTheRead:
    def test_a_source_that_raises_is_said_and_the_rest_kept(self, monkeypatch):
        def boom(now):
            raise ValueError("planted")
        monkeypatch.setattr(CH, "SOURCES", (boom, lambda now: [{"id": "x", "state": "ok"}]))
        v = CH.read(NOW)
        assert v["credentials"] == [{"id": "x", "state": "ok"}]
        assert v["errors"] == ["boom: ValueError: planted"]

    def test_no_planted_value_reaches_the_stored_value(self, netbox, monkeypatch):
        netbox["payload"] = {"results": [{"display": "**********WXYZ",
                                          "expires": "2027-01-11T00:00:00Z"}]}
        monkeypatch.setattr(CH, "SOURCES", (CH.netbox,))
        blob = json.dumps(CH.read(NOW))
        assert TOKEN not in blob and TOKEN[:-4] not in blob

    def test_the_reader_is_declared(self):
        from modules import reader_job
        assert "modules.readers.credential_health" in reader_job.DECLARED_MODULES
        assert any(r.name == "credential-health" for r in reader_job.readers())


def _source(creds):
    cached = {"state": "ok", "doc": {"last_good": {"value": {"credentials": creds,
                                                             "errors": []},
                                                   "value_at": CH._iso(NOW)},
                                     "stale_after_seconds": 7200}}
    return A.credential_health_source(cached=cached)


class TestTheRows:
    def test_each_state_its_row_or_none(self):
        creds = [
            {"id": "a", "label": "NetBox API token", "kind": "expiry", "state": "expired",
             "expires_at": "2026-10-01T00:00:00Z", "renew_at": "NetBox: Admin > API tokens",
             "put_at": "Settings > Integrations > NetBox"},
            {"id": "b", "label": "Proxmox API token", "kind": "expiry", "state": "danger",
             "days": 3.0, "expires_at": "x", "renew_at": "r", "put_at": "p"},
            {"id": "c", "label": "Grafana API token", "kind": "expiry", "state": "warning",
             "days": 20.0, "expires_at": "x", "renew_at": "r", "put_at": "p"},
            {"id": "d", "label": "r2's login credential", "kind": "age", "state": "warning",
             "days": 200.0, "set_at": "x", "renew_at": "Rotate credential on r2's page"},
            {"id": "e", "label": "TLS", "kind": "expiry", "state": "unknown", "why": "no answer",
             "renew_at": "r", "put_at": "p"},
            {"id": "f", "label": "ok one", "kind": "expiry", "state": "ok"},
            {"id": "g", "label": "listed one", "kind": "expiry", "state": "listed"}]
        rows = {r["id"].split(":", 1)[1]: r for r in _source(creds)["rows"]}
        assert set(rows) == {"a", "b", "c", "d", "e"}
        assert rows["a"]["level"] == "danger" and "EXPIRED" in rows["a"]["what"]
        assert "API tokens" in rows["a"]["action"]["label"]
        assert rows["b"]["level"] == "danger" and rows["c"]["level"] == "warning"
        assert rows["d"]["kind"] == "age" and "Rotate" in rows["d"]["action"]["label"]
        assert rows["e"]["kind"] == "unread"

    def test_nothing_stored_is_unreadable(self):
        res = A.credential_health_source(cached={"state": "absent", "doc": None, "why": "never"})
        assert res["state"] == "unreadable" and "not read yet" in res["rows"][0]["cause"]
