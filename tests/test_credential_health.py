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
import os
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


HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures", "credential_health")
#: The time of the captures (2026-10-03).
CAPTURED = time.mktime((2026, 10, 3, 12, 0, 0, 0, 0, 0))


def _capture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


#: The tool's token in the capture's shape: a NetBox 4.6 v2 token, `nbt_<key>.<secret>`, 57
#: characters as on the host; its key is the one the masked capture lists as the tool's.
TOKEN = "nbt_Kq3x9Z0aB7cD." + "PLANTEDsecret0123456789abcdefPLANTED0123"


@pytest.fixture
def netbox(monkeypatch):
    """NetBox answering with the REAL token list captured on the host (C378), masked."""
    cap = _capture("netbox_tokens.json")
    state = {"payload": cap["body"], "status": cap["status"], "token": TOKEN}
    monkeypatch.setattr("modules.netbox_client._nb_ready",
                        lambda: (True, "", _Session(state["payload"], state["status"]),
                                 "http://192.0.2.7"))
    monkeypatch.setattr("modules.netbox_client.get_netbox_config",
                        lambda: {"url": "http://192.0.2.7", "token": state["token"]})
    return state


class TestNetBox:
    """C378: on the host the row read "1 token(s) readable and 0 end as the tool's does". NetBox
    4.6 lists a v2 token by its KEY, the part between `nbt_` and the dot, never by its
    secret's last characters; the tool's row is the one whose key is its token's."""

    def test_the_tools_v2_token_by_its_key(self, netbox):
        assert len(TOKEN) == 57
        (c,) = CH.netbox(CAPTURED)
        assert c["state"] == "ok" and c["expires_at"] == "2027-09-22T12:00:00Z", c
        assert "API tokens" in c["renew_at"] and "Settings" in c["put_at"]

    def test_another_tokens_key_is_not_the_tools(self, netbox):
        netbox["token"] = "nbt_OtherKey0001." + "x" * 40
        (c,) = CH.netbox(CAPTURED)
        assert c["state"] == "unknown" and "cannot be told" in c["why"]

    def test_a_token_that_is_not_v2_is_said(self, netbox):
        netbox["token"] = "0123456789abcdef0123456789abcdef01234567"
        (c,) = CH.netbox(CAPTURED)
        assert c["state"] == "unknown" and "not a v2 token" in c["why"]

    def test_an_unreadable_list_is_unknown_naming_only_the_error_kind(self, netbox):
        netbox["status"] = 403
        (c,) = CH.netbox(CAPTURED)
        assert c["state"] == "unknown" and c["why"].endswith("RuntimeError")


class _TLSServer:
    """A real TLS server on loopback, its certificate made with the installed `cryptography`
    (41.0.7, the host's and CI's pin), expiring *days* from now: the handshake the reader
    reads is real, never an invented object (C379: AttributeError on the host)."""

    def __init__(self, tmp_path, days):
        import datetime as dt
        import socket
        import ssl
        import threading

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "192.0.2.80")])
        now = dt.datetime.utcnow()
        self.not_after = (now + dt.timedelta(days=days)).replace(microsecond=0)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(self.not_after)
                .sign(key, hashes.SHA256()))
        (tmp_path / "c.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (tmp_path / "k.pem").write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(str(tmp_path / "c.pem"), str(tmp_path / "k.pem"))
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            conn, _a = self.sock.accept()
            with self.ctx.wrap_socket(conn, server_side=True) as s:
                s.recv(1)
        except OSError:
            pass

    def close(self):
        self.sock.close()


class TestTheTLSCertificate:
    def test_a_real_handshake_is_read_with_the_pinned_library(self, monkeypatch, tmp_path):
        srv = _TLSServer(tmp_path, days=20)
        try:
            monkeypatch.setattr("modules.settings_schema.get_setting",
                                lambda k, d=None: f"https://127.0.0.1:{srv.port}"
                                if k == "proxmox_url" else d)
            (c,) = CH.tls(time.time())
        finally:
            srv.close()
        assert c["state"] == "warning", c["why"]
        assert c["expires_at"] == srv.not_after.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert "credential" not in c["why"]


class TestProxmoxAndGrafana:
    """C380: Proxmox's token cannot read its own record (the REAL answer captured on the host:
    403, "Permission check failed"), and is not widened. Its expiry is DECLARED in Settings, as
    Grafana's is; "never" is a valid declaration."""

    @pytest.fixture
    def proxmox(self, monkeypatch):
        from modules.integrations.proxmox import ProxmoxIntegration
        cap = _capture("proxmox_own_token_record.json")
        asked = []

        class _PxSession:
            def get(self, url, **kw):
                asked.append(url)
                r = _Resp(cap["body"], cap["status"])
                r.reason = cap["reason"]
                return r
        monkeypatch.setattr(ProxmoxIntegration, "is_configured", lambda self: True)
        monkeypatch.setattr(ProxmoxIntegration, "session", lambda self: _PxSession())
        declared = {"value": ""}
        monkeypatch.setattr("modules.settings_schema.get_setting", lambda k, d=None: {
            "proxmox_token_id": "nmas@pve!probe", "proxmox_url": "https://192.0.2.80:8006",
            "proxmox_token_expires": declared["value"]}.get(k, d))
        return declared, asked

    @pytest.mark.parametrize("declared, state, why", [
        ("", "listed", "no expiry declared"), ("never", "listed", "declared: it never expires"),
        ("2026-10-20", "warning", ""), ("not a date", "unknown", "is not a date")])
    def test_by_its_declared_expiry_never_its_record(self, proxmox, declared, state, why):
        proxmox[0]["value"] = declared
        (c,) = CH.proxmox(CAPTURED)
        assert c["state"] == state and why in c["why"], c
        assert "403" not in c["why"] and "could not be read" not in c["why"]
        assert not proxmox[1], "its own record is not asked: the token cannot read it"

    @pytest.mark.parametrize("declared, state", [("", "listed"), ("2027-02-01", "ok"),
                                                 ("never", "listed"), ("not a date", "unknown")])
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
        monkeypatch.setattr(CH, "SOURCES", (CH.netbox,))
        blob = json.dumps(CH.read(CAPTURED))
        assert "PLANTED" not in blob and TOKEN not in blob

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
        # C381: an expiry not read is UNKNOWN, never a Warning, which claims a danger seen.
        assert rows["e"]["kind"] == "unread" and rows["e"]["level"] == "unknown"

    def test_nothing_stored_is_unreadable(self):
        res = A.credential_health_source(cached={"state": "absent", "doc": None, "why": "never"})
        assert res["state"] == "unreadable" and "not read yet" in res["rows"][0]["cause"]
