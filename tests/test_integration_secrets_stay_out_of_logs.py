"""C356's measurement: does an integration secret reach a LOG line, or a probe's own message?

The log redactor masks by value only the template and device secrets (`redact.py`'s value
table); the integration secrets in `secrets_store.SECRET_KEYS` are masked on responses (the GET
and POST sweeps plant every one) and in a log line only by POSITION. So: every one of them
planted, every integration's probe driven against a loopback service that (1) refuses with
401 and (2) fails with 500, each ECHOING the request's headers in its body (the worst a
service can do), and (3) against a port nothing listens on; every record logged at DEBUG, by
any logger, and every probe's message are searched for the planted values. Each auth mode an
integration has is driven (basic and bearer), so every secret is sent somewhere.
"""

import http.server
import json
import logging
import socket
import threading

import pytest


def _planted(key):
    return f"PLANTED{key.replace('_', '')}Zq7x"


class _Echo(http.server.BaseHTTPRequestHandler):
    status = 401
    #: every request's headers, so the test can say which secrets were really SENT
    seen: list = []

    def _answer(self):
        _Echo.seen.append(dict(self.headers))
        body = json.dumps({"detail": "refused", "headers": dict(self.headers),
                           "path": self.path}).encode()
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        self._answer()

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        self._answer()

    def log_message(self, *a):
        pass


def _serve(status):
    handler = type(f"Echo{status}", (_Echo,), {"status": status})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _sent(requests_seen, planted):
    """The planted values that arrived in any request header, a Basic credential decoded."""
    import base64
    texts = []
    for headers in requests_seen:
        for v in headers.values():
            texts.append(v)
            if v.startswith("Basic "):
                try:
                    texts.append(base64.b64decode(v[6:]).decode(errors="replace"))
                except ValueError:
                    pass
    blob = "\n".join(texts)
    return sorted({p for p in planted if p in blob})


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """The clients retry a 500 and a refused connection with a backoff (urllib3's `Retry`,
    0.3 s and 0.5 s factors): every retry still runs and logs here, with no wait between them.
    What is measured is what reaches a log or a message, never the clock (measured
    2026-10-03: the waits were 37 s of this file's 38)."""
    from urllib3.util.retry import Retry
    monkeypatch.setattr(Retry, "get_backoff_time", lambda self: 0)


@pytest.fixture
def planted(tmp_path, monkeypatch):
    """A settings file of the test's own, every integration secret planted in it."""
    from modules import config, secrets_store
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(tmp_path / "user_settings.json"))
    for key in secrets_store.SECRET_KEYS:
        secrets_store.set_secret(key, _planted(key))
    return [_planted(k) for k in secrets_store.SECRET_KEYS]


def _drive(base_url, mode):
    """Every integration's probe against *base_url*, in auth *mode*; the messages they said."""
    from modules.config import set_user_setting
    from modules.integrations import REGISTRY
    said = []
    for name, cls in REGISTRY.items():
        inst = cls(timeout=3)
        for key in (inst.url_key,) if inst.url_key else ():
            set_user_setting(key, base_url)
        for key in getattr(inst, "plain_keys", ()):
            if key.endswith("_auth_mode"):
                set_user_setting(key, mode)
            elif key == "netbox_auth_scheme":
                set_user_setting(key, "Bearer" if mode == "bearer" else "Token")
            elif key.endswith(("_endpoint", "_bucket")):
                set_user_setting(key, base_url.split("://")[1] if key.endswith("endpoint")
                                 else "bucket")
        try:
            said.append(json.dumps(inst.status(), default=str))
        except Exception as exc:                     # noqa: BLE001 - a raise is a message too
            said.append(f"{name} raised {type(exc).__name__}: {exc}")
    from modules import netbox_client
    try:
        said.append(json.dumps(netbox_client.test_connection(
            base_url, _planted("netbox_token")), default=str))
    except Exception as exc:                         # noqa: BLE001
        said.append(f"netbox_client raised {type(exc).__name__}: {exc}")
    return said


@pytest.mark.parametrize("mode", ["basic", "bearer"])
@pytest.mark.parametrize("service", ["refuses 401", "fails 500", "is not there"])
def test_no_planted_integration_secret_reaches_a_log_or_a_message(planted, caplog, service,
                                                                  mode):
    if service == "is not there":
        base, srv = f"http://127.0.0.1:{_closed_port()}", None
    else:
        srv = _serve(401 if "401" in service else 500)
        base = f"http://127.0.0.1:{srv.server_address[1]}"
    caplog.set_level(logging.DEBUG)
    _Echo.seen.clear()
    try:
        said = _drive(base, mode)
    finally:
        if srv:
            srv.shutdown()
    if srv:
        # A leak can only follow a send: say how many planted secrets really reached the
        # service (a Basic header is decoded), with a floor, so a probe that sent nothing
        # cannot pass for one that kept what it sent out of the log.
        sent = _sent(_Echo.seen, planted)
        assert len(sent) >= (5 if mode == "basic" else 4), (mode, sent)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert len(caplog.records) >= 5 and len(said) >= 10, (len(caplog.records), len(said))
    leaked_log = sorted({v for v in planted if v in logged})
    leaked_said = sorted({v for v in planted if v in "\n".join(said)})
    assert leaked_log == [] and leaked_said == [], (service, mode, leaked_log, leaked_said)


def test_the_echo_really_carries_a_planted_secret(planted):
    """The control the search depends on: the service's body DOES hold the secret sent, so
    a probe that put that body into a log line or its message would be found."""
    import requests
    srv = _serve(401)
    try:
        r = requests.get(f"http://127.0.0.1:{srv.server_address[1]}/x",
                         headers={"Authorization": f"Bearer {planted[0]}"}, timeout=3)
    finally:
        srv.shutdown()
    assert planted[0] in r.text
