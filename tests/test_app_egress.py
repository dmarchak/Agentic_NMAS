"""An app's egress (C2645): the manifest's destinations, their addresses compiled from the
network's config into the start-time config's reserved key (`modules/apps/app_config.py`), and
the SDK's `mercury_app.egress`, which reaches those and nothing else
(`modules/apps/sdk/mercury_app/__init__.py`).

The app is a real file staged at <apps root>/<name>/<version>/, as the controller lays it out,
so the SDK finds its caller by the file's own path; the destination is an HTTP server on the
loopback (IPv4 and IPv6), which every request it serves is recorded by."""

import http.server
import json
import os
import socket
import threading
import types

import pytest

from modules.apps import app_config
from modules.apps.manifest import parse_manifest
from modules.apps.sdk import mercury_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "apps", "dns-blacklist", "manifest.yml")
NAME, VERSION = "dns_blacklist", "0.1.0"


def manifest():
    with open(FIXTURE, encoding="utf-8") as fh:
        return parse_manifest(fh.read())


def given(url="http://192.0.2.53:8053/v1"):
    return {"verdict_service": {"url": url, "timeout_seconds": 2},
            "cache": {"max_entries": 10, "ttl_seconds": 60}, "overrides": {}}


# ── the compile step ─────────────────────────────────────────────────────────────────────────

def test_the_sdk_and_the_compile_reserve_the_same_key():
    assert mercury_app.RESERVED == app_config.RESERVED == "_mercury"


@pytest.mark.parametrize("url", ["http://192.0.2.53:8053/v1", "https://[2001:db8::53]/v1"],
                         ids=["ipv4", "ipv6"])
def test_each_declared_destination_s_address_is_compiled_from_its_config_key(url):
    got = app_config.compile_config(manifest(), given(url))
    assert got["ok"] is True, got["problems"]
    assert got["config"]["_mercury"] == {"egress": {"verdict_service": url}}
    assert got["config"]["verdict_service"]["url"] == url, "the app's own config is untouched"
    assert any(n.startswith("egress: verdict_service to " + url) for n in got["notes"])


@pytest.mark.parametrize("url, words", [
    (None, "is not set in the network's config"),
    ("ftp://192.0.2.53/v1", "is a ftp address, not http or https"),
    ("http://user:pw@192.0.2.53/v1", "carries a user or password"),
    ("http://192.0.2.53/v1?k=1", "carries a query or a fragment"),
    ("http:///v1", "names no host"),
    ("http://192.0.2.53:99999/v1", "does not parse as a URL")])
def test_an_address_an_egress_may_not_reach_is_refused_naming_its_key(url, words):
    m = manifest()
    config = given()
    if url is None:
        del config["verdict_service"]["url"]
    else:
        config["verdict_service"]["url"] = url
    targets, problems = app_config.egress_targets(m, config)
    assert targets == {}
    assert len(problems) == 1 and words in problems[0]
    assert "egress 'verdict_service': its address at verdict_service.url" in problems[0]


def test_a_network_config_setting_the_reserved_key_is_refused():
    got = app_config.compile_config(manifest(), dict(given(), _mercury={"egress": {}}))
    assert got["ok"] is False and "the key Mercury reserves" in got["problems"][0]


# ── the SDK's egress, from a staged app ─────────────────────────────────────────────────────

class Recorder(http.server.BaseHTTPRequestHandler):
    seen = []
    accepts = []

    def log_message(self, *args):
        pass

    def _answer(self):
        length = int(self.headers.get("Content-Length") or 0)
        Recorder.seen.append((self.command, self.path, self.rfile.read(length)))
        Recorder.accepts.append(self.headers.get("Accept"))
        if self.path.startswith("/v1/moved"):
            self.send_response(302)
            self.send_header("Location", "/v1/elsewhere")
            self.end_headers()
            return
        if self.path.startswith("/v1/big"):
            body = b"x" * (mercury_app.MAX_BYTES + 10)
            ctype = "text/plain"
        elif self.path.startswith("/v1/fail"):
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"why": "down"}')
            return
        else:
            body, ctype = json.dumps({"verdict": "allow"}).encode(), "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _answer


class Server6(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6


def _serve(host):
    cls = Server6 if ":" in host else http.server.ThreadingHTTPServer
    server = cls((host, 0), Recorder)               # no ::1 here fails, never skips (IPv6 parity)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture(params=["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
def staged(request, tmp_path, monkeypatch):
    """An app staged as the controller lays it out, its config compiled with the loopback
    server's address, and a `call` that is the app's own code calling egress."""
    server = _serve(request.param)
    Recorder.seen = []
    Recorder.accepts = []
    host = f"[{request.param}]" if ":" in request.param else request.param
    url = f"http://{host}:{server.server_address[1]}/v1"
    root = tmp_path / "opt" / "ryu-apps"
    folder = root / NAME / VERSION
    folder.mkdir(parents=True)
    app_file = folder / f"{NAME}.py"
    app_file.write_text("def call(sdk, *a, **k):\n    return sdk.egress(*a, **k)\n")
    compiled = app_config.compile_config(manifest(), given(url))
    assert compiled["ok"], compiled["problems"]
    (root / NAME / f"{VERSION}.config.json").write_text(json.dumps(compiled["config"]))
    monkeypatch.setattr(mercury_app, "APPS_ROOT", str(root))
    app = types.ModuleType(NAME)
    app.__file__ = str(app_file)
    exec(compile(app_file.read_text(), str(app_file), "exec"), app.__dict__)
    yield types.SimpleNamespace(call=lambda *a, **k: app.call(mercury_app, *a, **k),
                                url=url, root=root)
    server.shutdown()
    server.server_close()


def test_a_declared_destination_is_reached_at_its_compiled_address(staged):
    got = staged.call("verdict_service", "POST", "/verdict", {"domain": "example.invalid"}, 2)
    assert got == {"ok": True, "status": 200, "body": {"verdict": "allow"}, "error": ""}
    assert Recorder.seen == [("POST", "/v1/verdict", b'{"domain": "example.invalid"}')]


def test_the_accept_header_is_json_by_default_and_the_one_media_type_the_app_names(staged):
    """A DNS-over-HTTPS JSON API answers only application/dns-json (Cloudflare's resolver:
    405 to application/json, 200 to application/dns-json, measured 2026-11-10), so the app
    names the one JSON media type its destination speaks."""
    assert staged.call("verdict_service", "GET", "/verdict")["ok"] is True
    assert staged.call("verdict_service", "GET", "/verdict",
                       accept="application/dns-json")["ok"] is True
    assert Recorder.accepts == ["application/json", "application/dns-json"]


def test_the_app_reads_its_config_without_the_reserved_key(staged):
    got = mercury_app.start_config(NAME, VERSION)
    assert got["ok"] is True and "_mercury" not in got["config"]
    assert got["config"]["verdict_service"]["url"] == staged.url


def test_a_destination_the_config_does_not_carry_is_refused_and_nothing_is_sent(staged):
    with pytest.raises(mercury_app.EgressRefused, match="'elsewhere' is not a destination "
                                                        "dns_blacklist 0.1.0's config carries "
                                                        r"\(it carries: verdict_service\)"):
        staged.call("elsewhere", "GET", "/x")
    assert Recorder.seen == []


def test_a_caller_that_is_not_a_staged_app_is_refused(staged):
    with pytest.raises(mercury_app.EgressRefused, match="called from no app staged at"):
        mercury_app.egress("verdict_service", "GET", "/verdict")
    assert Recorder.seen == []


def test_a_redirect_is_never_followed(staged):
    got = staged.call("verdict_service", "GET", "/moved")
    assert got["ok"] is False and got["status"] == 302
    assert [p for _m, p, _b in Recorder.seen] == ["/v1/moved"]


def test_a_destination_answering_an_error_is_not_ok_and_says_so(staged):
    got = staged.call("verdict_service", "GET", "/fail")
    assert got == {"ok": False, "status": 503, "body": {"why": "down"},
                   "error": "verdict_service answered 503 Service Unavailable"}


def test_an_answer_larger_than_the_bound_is_not_ok(staged):
    got = staged.call("verdict_service", "GET", "/big")
    assert got["ok"] is False and "more than 65536 bytes" in got["error"]


@pytest.mark.parametrize("kw, words", [
    ({"method": "PATCH"}, "the method 'PATCH' is not one of"),
    ({"path": "/../../etc"}, "is not an absolute path"),
    ({"path": "//other.example.invalid/x"}, "is not an absolute path"),
    ({"path": "relative"}, "is not an absolute path"),
    ({"timeout": 11}, "the timeout 11 is not a number of seconds in (0, 10.0]"),
    ({"timeout": 0}, "the timeout 0 is not"),
    ({"body": {"x": object()}}, "the body is not JSON"),
    ({"accept": "text/html"}, "the accept 'text/html' is not one JSON media type"),
    ({"accept": "application/json, text/html"}, "is not one JSON media type")])
def test_a_call_out_of_shape_is_refused_and_nothing_is_sent(staged, kw, words):
    with pytest.raises(mercury_app.EgressRefused) as exc:
        staged.call("verdict_service", **kw)
    assert words in str(exc.value)
    assert Recorder.seen == []


def test_a_destination_that_does_not_answer_is_not_ok_and_raises_nothing(tmp_path, monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    root = tmp_path / "ryu-apps"
    (root / NAME / VERSION).mkdir(parents=True)
    app_file = root / NAME / VERSION / f"{NAME}.py"
    app_file.write_text("def call(sdk):\n    return sdk.egress('verdict_service', 'GET', "
                        "'/verdict', None, 1)\n")
    compiled = app_config.compile_config(manifest(), given(f"http://127.0.0.1:{port}/v1"))
    (root / NAME / f"{VERSION}.config.json").write_text(json.dumps(compiled["config"]))
    monkeypatch.setattr(mercury_app, "APPS_ROOT", str(root))
    ns = {"__file__": str(app_file)}
    exec(compile(app_file.read_text(), str(app_file), "exec"), ns)
    got = ns["call"](mercury_app)
    assert got["ok"] is False and got["status"] == 0
    assert got["error"].startswith("verdict_service did not answer")


def test_the_sdk_is_still_written_for_python_3_5():
    import ast

    from modules.apps.python_versions import Target, grammar_problems, name_problem

    with open(mercury_app.__file__, encoding="utf-8") as fh:
        text = fh.read()
    tree = ast.parse(text, feature_version=(3, 5))
    target = Target((3, 5), "the controller's Python (Ubuntu 16.04.5)")
    assert grammar_problems(tree, text, "mercury_app/__init__.py", target) == []
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imported and all(not name_problem(i, target) for i in imported)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)], "no f-strings"
