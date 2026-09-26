"""P.3 step 6 (register B11): no GET returns a secret, and an empty secret
field saves nothing. And register B16: no GET runs a command a request named.

B11: `GET /settings` returned the Anthropic key and both Jenkins secrets in
cleartext, ungated, on every opening of the Settings modal since e729267
(2026-04-12). The NetBox token beside them was always a `*_set` flag.

B16, found while sweeping the GET routes for this step: `/run_command/<ip>`
ran any exec-mode command (reload, delete, copy, clear) from a URL. The gate
table covers mutating METHODS, so a GET that changes a device was outside it,
and a link an operator logged in to Access followed would have run it.
"""

import ast
import inspect
import socket
import textwrap

import pytest

PLANTED = {
    "anthropic": "sk-ant-PLANTED-a1b2c3d4e5f6",
    "jenkins_api_key": "JENKINS-PLANTED-9f8e7d6c",
    "jenkins_token": "JTOKEN-PLANTED-1a2b3c4d",
    "netbox": "nbt_PLANTED_5e6f7a8b9c0d",
}


@pytest.fixture
def planted(monkeypatch, tmp_path):
    """Every secret reader returns a known value; no socket may connect; the
    settings file is a temp path, so a GET that migrates writes nowhere real."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", PLANTED["anthropic"])

    def _no_network(*a, **k):
        raise OSError("tests do not touch a network")
    monkeypatch.setattr(socket.socket, "connect", _no_network)
    import modules.config as C
    monkeypatch.setattr(C, "USER_SETTINGS_FILE", str(tmp_path / "user_settings.json"))
    import modules.jenkins_runner as J
    store = {"jenkins_url": "", "jenkins_user": "",
             "jenkins_api_key": PLANTED["jenkins_api_key"],
             "jenkins_token": PLANTED["jenkins_token"]}
    monkeypatch.setattr(J, "load_config", lambda: dict(store))
    monkeypatch.setattr(J, "save_config", lambda cfg: store.update(cfg))
    import modules.netbox_client as NB
    monkeypatch.setattr(NB, "get_netbox_config", lambda: {"url": "", "token": PLANTED["netbox"]})
    return store


def _sweep(app) -> tuple:
    """(routes swept, [(route, which secret)]) for every argument-free GET."""
    client = app.test_client()
    swept, hits = 0, []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if "GET" not in (rule.methods or ()) or rule.endpoint == "static" or rule.arguments:
            continue
        swept += 1
        body = client.get(rule.rule).get_data(as_text=True)
        hits += [(rule.rule, k) for k, v in PLANTED.items() if v in body]
    return swept, hits


class TestNoGetReturnsASecret:
    def test_no_argument_free_get_carries_a_planted_secret(self, planted):
        import app as A
        swept, hits = _sweep(A.app)
        assert swept >= 80, swept          # 86 measured; the sweep can fail to run
        assert hits == [], hits

    def test_the_sweep_finds_a_secret_that_is_returned(self, planted):
        """Control: the sweep can say yes."""
        import flask
        probe = flask.Flask("probe")

        @probe.route("/leak")
        def leak():
            return {"key": PLANTED["anthropic"]}
        _swept, hits = _sweep(probe)
        assert hits == [("/leak", "anthropic")]

    def test_the_modal_is_told_whether_each_secret_is_set(self, planted):
        import app as A
        body = A.app.test_client().get("/settings").get_json()
        assert body["anthropic_api_key_set"] is True
        assert body["jenkins_api_key_set"] is True and body["jenkins_token_set"] is True
        assert "anthropic_api_key" not in body and "jenkins_api_key" not in body


class TestAnEmptySecretFieldSavesNothing:
    def test_empty_jenkins_secrets_leave_the_stored_values(self, planted):
        import app as A
        A.app.test_client().post("/settings", json={
            "jenkins_url": "https://ci.example.invalid",
            "jenkins_api_key": "", "jenkins_token": ""})
        assert planted["jenkins_api_key"] == PLANTED["jenkins_api_key"]
        assert planted["jenkins_token"] == PLANTED["jenkins_token"]
        assert planted["jenkins_url"] == "https://ci.example.invalid", "the rest still saves"

    def test_a_typed_secret_is_saved(self, planted):
        """Control: 'empty is unchanged' is not 'never saved'."""
        import app as A
        A.app.test_client().post("/settings", json={"jenkins_token": "NEW-VALUE-123456"})
        assert planted["jenkins_token"] == "NEW-VALUE-123456"

    def test_the_modal_sends_a_secret_only_if_typed(self):
        from tests.js_source import read_shipped
        page = read_shipped("templates/index.html")
        for field in ("s.anthropic_api_key ", "s.jenkins_api_key ", "s.jenkins_token "):
            assert field not in page and field.strip() + ")" not in page, field
        assert "if (jApi) payload.jenkins_api_key = jApi;" in page
        assert "if (jTok) payload.jenkins_token = jTok;" in page
        assert "jenkins_api_key:       document.getElementById" not in page


# ---------------------------------------------------------------------------
# B16: a command a request names reaches a device only through a gated POST
# ---------------------------------------------------------------------------

DEVICE_SENDS = {"run_device_command", "send_command", "send_command_timing",
                "send_config_set"}


def _sends_request_text(src: str) -> bool:
    """Does this view send text taken from `request.args` to a device?"""
    tree = ast.parse(textwrap.dedent(src))
    tainted = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and "request.args" in ast.unparse(node.value)):
            tainted |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in DEVICE_SENDS and any(
                    isinstance(n, ast.Name) and n.id in tainted
                    for a in node.args for n in ast.walk(a)):
                return True
    return False


class TestNoGetSendsWhatTheRequestNamed:
    def test_no_get_only_view_does(self):
        import app as A
        checked, offenders = 0, []
        for rule in A.app.url_map.iter_rules():
            if set(rule.methods or ()) - {"HEAD", "OPTIONS"} != {"GET"} or rule.endpoint == "static":
                continue
            try:
                src = inspect.getsource(A.app.view_functions[rule.endpoint])
            except (OSError, TypeError):
                continue
            checked += 1
            if _sends_request_text(src):
                offenders.append(rule.rule)
        assert checked >= 80, checked
        assert offenders == [], offenders

    def test_the_scan_sees_the_shape_that_was_there(self):
        """Control: run_command's old body."""
        old = ('def run_command(ip):\n'
               '    command = request.args.get("command")\n'
               '    output = run_device_command(conn, command)\n')
        assert _sends_request_text(old) is True
        assert _sends_request_text('def f():\n    x = request.args.get("v")\n'
                                   '    run_device_command(c, "show clock")\n') is False

    def test_run_command_is_a_gated_post(self):
        import app as A
        from modules.route_gates import GATES
        assert GATES["run_command"].kind == "confirm"
        assert A.app.test_client().get("/run_command/192.0.2.1?command=reload").status_code == 405

    @pytest.mark.real_identity
    def test_without_a_person_it_is_refused_before_any_device(self, monkeypatch):
        import app as A
        reached = []
        monkeypatch.setattr(A, "run_device_command", lambda *a, **k: reached.append(a))
        resp = A.app.test_client().post("/run_command/192.0.2.1", data={"command": "reload"})
        assert resp.status_code == 403 and reached == []


class TestAnHttpErrorKeepsItsStatus:
    """Register C29: only 404 had a handler, so the catch-all turned every
    other HTTP error into a 500 'unexpected error, check the logs'."""

    def test_a_wrong_method_is_405_not_500(self):
        import app as A
        resp = A.app.test_client().get("/deploy/apply")
        assert resp.status_code == 405, resp.status_code

    def test_a_real_exception_is_still_500(self, monkeypatch):
        """Control: the catch-all still catches what it is for."""
        import app as A
        import routes.deploy as rd

        def _boom(*a, **k):
            raise RuntimeError("boom")
        monkeypatch.setitem(A.app.view_functions, "deploy.plan", _boom)
        resp = A.app.test_client().post("/deploy/plan", json={})
        assert resp.status_code == 500
