"""P.3 step 6 (register B11): no GET returns a secret, and an empty secret
field saves nothing. And register B16: no GET runs a command a request named.

B11: `GET /settings` returned the Anthropic key and both Jenkins secrets in
cleartext, ungated, on every opening of the Settings modal since e729267
(2026-04-12). The NetBox token beside them was always a `*_set` flag. P.4
removed Jenkins, so its fields were refused by name rather than stored; the
modal and `/settings` left at 7.8 (2026-10-15).

B16, found while sweeping the GET routes for this step: `/run_command/<ip>`
ran any exec-mode command (reload, delete, copy, clear) from a URL. The gate
table covers mutating METHODS, so a GET that changes a device was outside it,
and a link an operator logged in to Access followed would have run it. The route left at 7.8
with today's device page (2026-10-17); its two checks hold v2's Ask tab, the one place a
person types a command for one device.
"""

import ast
import inspect
import socket
import textwrap

import pytest

PLANTED = {
    "anthropic": "sk-ant-PLANTED-a1b2c3d4e5f6",
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
    import modules.netbox_client as NB
    monkeypatch.setattr(NB, "get_netbox_config", lambda: {"url": "", "token": PLANTED["netbox"]})


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


# Today's Settings modal's own tests (its payload said whether each secret was set, never the
# value; it sent a secret only if typed; an old page's Jenkins and AI fields were refused by name)
# left with the modal and GET and POST /settings at 7.8 (2026-10-15). On v2 a secret is drawn as
# set or not set and changed only by Replace… (tests/test_installation_settings.py,
# test_each_field_is_a_control_and_a_token_is_never_drawn), and a card's Save reads only its own
# fields, so an old page's removed keys reach nothing.


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

    # Today's /run_command, B16's route, left at 7.8 with today's device page (P7-22,
    # 2026-10-17). The one place a person types a command for one device is v2's Ask tab, and
    # these two hold it to what B16 asked of its predecessor.

    def test_ask_is_a_gated_post(self):
        import app as A
        from modules.route_gates import GATES, NOT_DEVICE
        assert GATES["reads_v2.ask_run"].kind not in (NOT_DEVICE, "configure")
        methods = {m for r in A.app.url_map.iter_rules() if r.endpoint == "reads_v2.ask_run"
                   for m in r.methods} - {"HEAD", "OPTIONS"}
        assert methods == {"POST"}, methods

    @pytest.mark.real_identity
    def test_without_a_person_it_is_refused_before_any_device(self, monkeypatch):
        import app as A
        from modules.nsot import reads
        reached = []
        monkeypatch.setattr(reads, "start", lambda *a, **k: reached.append(a) or {})
        resp = A.app.test_client().post("/v2/device/r1/ask", data={"command": "reload"})
        assert resp.status_code == 403 and reached == []


class TestAnHttpErrorKeepsItsStatus:
    """Register C29: only 404 had a handler, so the catch-all turned every
    other HTTP error into a 500 'unexpected error, check the logs'."""

    def test_a_wrong_method_is_405_not_500(self):
        import app as A
        resp = A.app.test_client().get("/attention/acknowledge")   # POST only (/deploy/apply until 7.8)
        assert resp.status_code == 405, resp.status_code

    def test_a_real_exception_is_still_500(self, monkeypatch):
        """Control: the catch-all still catches what it is for."""
        import app as A

        def _boom(*a, **k):
            raise RuntimeError("boom")
        monkeypatch.setitem(A.app.view_functions, "attention.acknowledge", _boom)
        resp = A.app.test_client().post("/attention/acknowledge", json={})
        assert resp.status_code == 500
