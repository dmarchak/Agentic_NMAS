"""The monitoring profile's connectors have a home in Settings (the operator,
2026-09-30: ntp_servers, telemetry_receiver, snmp_trap_host and
snmp_exporter_config had to be set by editing data/user_settings.json, a console
step the no-console rule forbids).

Settings > Integrations > Monitoring profile: every key the card's client owns
is drawn, a save goes through the schema (a malformed listener or a heartbeat
under 60 s refused with nothing written), and Test checks what can be checked
(the exporter's file and auth, Telegraf's listener, each NTP server) and says
one-way syslog and traps are not testable rather than drawing them as passing.
"""
import json
import re
import socket
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "static" / "js" / "gen" / "partials__settings_integrations.1.js"


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    from modules import config
    path = tmp_path / "user_settings.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(path))
    return path


def _exporter(tmp_path, community="planted-community-9182", auth="public_v2", version=2):
    p = tmp_path / "snmp.yml"
    p.write_text("modules: {}\nauths:\n"
                 f"  {auth}:\n    community: {community}\n    security_level: noAuthNoPriv\n"
                 f"    auth_protocol: MD5\n    priv_protocol: DES\n    version: {version}\n")
    return str(p)


class TestTheCard:
    def test_every_key_the_client_owns_is_drawn(self):
        from modules.integrations.monitoring_profile import MonitoringProfileIntegration
        js = SPEC.read_text()
        block = js[js.index("monitoring_profile: {"):]
        block = block[:block.index("\n};")]          # the card is the spec's last
        drawn = set(re.findall(r"key: '([a-z0-9_]+)'", block))
        assert drawn == set(MonitoringProfileIntegration.plain_keys)
        assert len(drawn) >= 10

    def test_a_list_and_a_number_are_sent_as_their_types(self):
        js = SPEC.read_text()
        assert "f.type === 'list') out[f.key] = el.value.split(',')" in js
        assert "f.type === 'number') out[f.key] = el.value === '' ? undefined : Number(el.value)" in js
        assert "{key: 'ntp_servers', label: 'NTP servers', type: 'list'" in js


class TestSaving:
    def test_the_values_are_stored_and_read_back(self, settings_file, tmp_path):
        import app as A
        c = A.app.test_client()
        r = c.post("/settings/integrations/monitoring_profile", json={
            "ntp_servers": ["192.0.2.10"], "telemetry_receiver": "192.0.2.10:57000",
            "snmp_trap_host": "192.0.2.10", "snmp_exporter_config": _exporter(tmp_path),
            "syslog_heartbeat_seconds": 300})
        body = r.get_json()
        assert r.status_code == 200 and body["ok"], body
        stored = json.loads(settings_file.read_text())
        assert stored["ntp_servers"] == ["192.0.2.10"] and stored["telemetry_receiver"] == "192.0.2.10:57000"
        assert body["integration"]["snmp_trap_host"] == "192.0.2.10"

    @pytest.mark.parametrize("bad", [{"telemetry_receiver": "no-port-here"},
                                     {"syslog_heartbeat_seconds": 30},
                                     {"ntp_servers": "192.0.2.10"}])
    def test_a_malformed_value_is_refused_and_nothing_written(self, settings_file, bad):
        import app as A
        r = A.app.test_client().post("/settings/integrations/monitoring_profile", json=bad)
        assert r.status_code == 400 and "Invalid setting" in r.get_json()["error"]
        assert json.loads(settings_file.read_text()) == {}


def _listener():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    return srv, srv.getsockname()[1]


def _sntp_server(stratum=2):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))

    def serve():
        data, peer = s.recvfrom(512)
        s.sendto(bytes([0x24, stratum]) + 46 * b"\0", peer)
    threading.Thread(target=serve, daemon=True).start()
    return s, s.getsockname()[1]


class TestTheTest:
    def test_what_can_be_checked_is_checked_and_one_way_is_said(self, settings_file, tmp_path,
                                                                 monkeypatch):
        from modules.config import set_user_setting
        from modules.integrations import monitoring_profile as M
        srv, port = _listener()
        set_user_setting("snmp_exporter_config", _exporter(tmp_path))
        set_user_setting("snmp_exporter_auth", "public_v2")
        set_user_setting("telemetry_receiver", f"127.0.0.1:{port}")
        set_user_setting("ntp_servers", ["127.0.0.1"])
        set_user_setting("syslog_host", "192.0.2.10")
        monkeypatch.setattr(M, "sntp_answers", lambda host: (True, f"{host}: stratum 2"))
        got = M.MonitoringProfileIntegration().test_connection()
        srv.close()
        states = {r["name"]: r["state"] for r in got["checks"]}
        assert got["ok"], got
        assert states["snmp_exporter config"] == "ok" and states["Telegraf listener"] == "ok"
        assert states["NTP 127.0.0.1"] == "ok" and states["syslog to 192.0.2.10"] == "not_testable"
        assert "planted-community-9182" not in json.dumps(got)

    def test_a_listener_that_refuses_and_a_bad_auth_fail_by_name(self, settings_file, tmp_path):
        from modules.config import set_user_setting
        from modules.integrations import monitoring_profile as M
        srv, port = _listener()
        srv.close()
        set_user_setting("telemetry_receiver", f"127.0.0.1:{port}")
        set_user_setting("snmp_exporter_config", _exporter(tmp_path, auth="other_v2"))
        set_user_setting("snmp_exporter_auth", "public_v2")
        got = M.MonitoringProfileIntegration().test_connection()
        assert not got["ok"]
        rows = {r["name"]: r for r in got["checks"]}
        assert rows["Telegraf listener"]["state"] == "failed"
        assert "no auth module 'public_v2'" in rows["snmp_exporter config"]["detail"]

    def test_the_sntp_probe_reads_a_real_answer(self):
        from modules.integrations.monitoring_profile import sntp_answers
        s, port = _sntp_server(stratum=2)
        ok, words = sntp_answers("127.0.0.1", port=port)
        s.close()
        assert ok and "stratum 2" in words
        s, port = _sntp_server(stratum=16)
        ok, words = sntp_answers("127.0.0.1", port=port)
        s.close()
        assert not ok and "unsynchronised" in words

    def test_nothing_set_is_said_never_drawn_as_passing(self, settings_file):
        from modules.integrations.monitoring_profile import MonitoringProfileIntegration
        rows = MonitoringProfileIntegration().checks()
        assert {r["state"] for r in rows} == {"not_set"}
        assert not MonitoringProfileIntegration().is_configured()
