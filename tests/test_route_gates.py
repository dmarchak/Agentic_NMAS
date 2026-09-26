"""P.3 step 1: every mutating endpoint is declared, and the gate runs first.

Register B12: of the routes that change a device, one checked identity, and
CLAUDE.md said they all did. The gate is now a table
(`modules/route_gates.py`) enforced by one `before_request` hook. These tests
are what make "a route cannot be added without declaring what it is" true:

- the population in BOTH directions, each with a floor, so an empty scan
  cannot pass and a removed route cannot leave a ghost;
- the table agrees with every gate a route still applies to itself;
- refused before input: no identity means 403 before the route's own 400;
- a person passes, a service does not;
- the terminal's socket events, which never reach `before_request`;
- the audit records the VERIFIED actor, never one the request body named.
"""

import ast
import inspect
import json
import os
import subprocess
import sys
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MUTATING_FLOOR = 121     # 131 measured; steps 2-3 cut ten; B16 +1; D12 removed /disconnect


def _app():
    import app as A
    return A.app


def _mutating(app) -> set:
    from modules.route_gates import SAFE_METHODS
    return {r.endpoint for r in app.url_map.iter_rules()
            if set(r.methods or ()) - SAFE_METHODS}


def _unclassified(app) -> set:
    from modules.route_gates import GATES
    return _mutating(app) - set(GATES)


def _socket_events() -> set:
    import app as A
    return {ev for evs in A.socketio.server.handlers.values() for ev in evs
            if ev not in ("connect", "disconnect")}


# ---------------------------------------------------------------------------
# The population
# ---------------------------------------------------------------------------

class TestEveryMutatingEndpointIsDeclared:
    def test_the_scan_finds_the_population(self):
        found = _mutating(_app())
        assert len(found) >= MUTATING_FLOOR, (
            f"{len(found)} mutating endpoints found; the floor is "
            f"{MUTATING_FLOOR}. Either routes were removed (lower the floor in "
            "the same commit) or the scan stopped seeing them.")

    def test_every_mutating_endpoint_is_in_the_table(self):
        missing = _unclassified(_app())
        assert not missing, (
            "mutating endpoints with no declared gate (add each to "
            f"modules/route_gates.py GATES with a kind and a reason): "
            f"{sorted(missing)}")

    def test_the_table_names_no_endpoint_that_does_not_exist(self):
        from modules.route_gates import GATES
        ghosts = set(GATES) - _mutating(_app())
        assert not ghosts, (
            "entries for endpoints that are not mutating routes (removed, "
            f"renamed, or GET-only); remove them with the route: {sorted(ghosts)}")

    def test_the_check_names_an_undeclared_route(self):
        """Control: the set difference can say no."""
        from flask import Flask
        from modules import route_gates

        probe = Flask("probe")

        @probe.route("/probe/push", methods=["POST"])
        def probe_push():
            return ""

        assert _unclassified(probe) == {"probe_push"}

    def test_every_kind_is_a_gate_or_not_device_and_every_entry_says_why(self):
        from modules.identity import GATED_ACTIONS
        from modules.route_gates import GATES, NOT_DEVICE, SOCKET_GATES
        for name, gate in {**GATES, **SOCKET_GATES}.items():
            assert gate.kind in set(GATED_ACTIONS) | {NOT_DEVICE}, (name, gate.kind)
            assert gate.reason.strip(), f"{name} has no reason"

    @pytest.mark.parametrize("endpoint,kind", [
        ("deploy.apply", "confirm"),
        ("golden.restore_apply", "confirm"),
        ("bulk_reload", "confirm"),
        ("bulk_execute", "confirm"),
        ("bulk_tftp_upload", "confirm"),
        ("ai_approval_approve", "approve"),
        ("templatize.bulk_apply", "approve"),
        ("save_settings", "configure"),
        ("identity.ratify_setting", "configure"),
        ("bulk_download_config", "reveal"),
        ("remote.push", "publish_remote"),
        ("deploy.plan", "not_device"),
    ])
    def test_anchors(self, endpoint, kind):
        """Named expectations, including the one that failed on 2026-09-26."""
        from modules.route_gates import GATES
        assert GATES[endpoint].kind == kind

    def test_every_socket_event_is_declared(self):
        from modules.route_gates import SOCKET_GATES
        events = _socket_events()
        assert len(events) >= 3
        assert events == set(SOCKET_GATES), (events, set(SOCKET_GATES))
        assert SOCKET_GATES["connect_terminal"].kind == "break_glass"
        assert SOCKET_GATES["terminal_input"].kind == "break_glass"

    def test_the_hook_is_installed_on_the_real_app(self):
        from modules import route_gates
        assert route_gates.enforce in _app().before_request_funcs.get(None, [])


class TestTheTableAgreesWithEveryInRouteGate:
    """A route that still calls `identity.require()` itself must name the same
    kind and operation as the table, or the hook and the route disagree about
    what the act is."""

    def _in_route_calls(self):
        from modules.route_gates import GATES
        app = _app()
        found = []
        for endpoint, view in app.view_functions.items():
            try:
                src = textwrap.dedent(inspect.getsource(view))
            except (OSError, TypeError):
                continue
            for node in ast.walk(ast.parse(src)):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "require"):
                    continue
                args = [a.value for a in node.args[1:2]
                        if isinstance(a, ast.Constant)]
                kw = {k.arg: k.value for k in node.keywords}
                action = args[0] if args else (
                    kw["action"].value if isinstance(kw.get("action"), ast.Constant)
                    else "reveal")
                op = kw.get("operation")
                operation = op.value if isinstance(op, ast.Constant) else None
                found.append((endpoint, action, operation, endpoint in GATES))
        return found

    def test_the_scan_finds_the_in_route_gates(self):
        # 11 measured: remote x5, onboard x4, freshness, ratify. A grep finds
        # 13 lines: one is a docstring naming require(), and one is the golden
        # reveal helper, which GET views call and which is not a view itself.
        assert len(self._in_route_calls()) >= 11

    def test_kinds_and_operations_agree(self):
        from modules.route_gates import GATES
        disagree = []
        for endpoint, action, operation, declared in self._in_route_calls():
            if not declared:
                continue            # a GET that reveals conditionally
            gate = GATES[endpoint]
            if gate.kind != action:
                disagree.append((endpoint, "kind", gate.kind, action))
            if operation is not None and gate.operation != operation:
                disagree.append((endpoint, "operation", gate.operation, operation))
        assert not disagree, disagree


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------

REFUSED_WITHOUT_IDENTITY = [
    "/deploy/apply",
    "/golden/restore/apply",
    "/ai/approvals/xyz/approve",
    "/bulk_reload",
    "/bulk_tftp_upload",
    "/settings",
    "/inventory/credentials/profiles",
    "/templatize/bulk/apply",
]


@pytest.mark.real_identity
class TestRefusedBeforeInput:
    @pytest.mark.parametrize("path", REFUSED_WITHOUT_IDENTITY)
    def test_no_identity_is_403_before_validation(self, path):
        resp = _app().test_client().post(path, json={})
        body = resp.get_json(silent=True) or {}
        assert resp.status_code == 403, (path, resp.status_code, body)
        assert body.get("requires_identity") is True, (path, body)

    def test_a_not_device_route_is_not_refused_by_the_gate(self):
        resp = _app().test_client().post("/deploy/plan", json={})
        assert resp.status_code != 403, resp.get_json(silent=True)

    def test_an_undeclared_route_is_refused_at_run_time(self):
        from flask import Flask
        from modules import route_gates

        probe = Flask("probe")
        route_gates.install(probe)

        @probe.route("/probe/push", methods=["POST"])
        def probe_push():
            return "pushed"

        resp = probe.test_client().post("/probe/push")
        assert resp.status_code == 403
        assert resp.get_json()["outcome"] == "unclassified"


def _gated_requests(app):
    """(method, url, endpoint, kind) for EVERY gated rule and mutating method,
    URL arguments filled with placeholders."""
    from modules.route_gates import GATES, SAFE_METHODS
    from werkzeug.routing import IntegerConverter, PathConverter
    out = []
    for rule in app.url_map.iter_rules():
        gate = GATES.get(rule.endpoint)
        if gate is None or gate.kind == "not_device":
            continue
        values = {}
        for arg in rule.arguments:
            conv = rule._converters.get(arg)
            values[arg] = (1 if isinstance(conv, IntegerConverter)
                           else "p/q" if isinstance(conv, PathConverter) else "x")
        url = app.url_map.bind("localhost").build(rule.endpoint, values,
                                                  append_unknown=False)
        for method in sorted(set(rule.methods or ()) - SAFE_METHODS):
            out.append((method, url, rule.endpoint, gate.kind))
    return out


@pytest.mark.real_identity
class TestEveryGatedEndpointRefusesWithoutIdentity:
    """P.3 step 9: the statement CLAUDE.md makes, measured over the whole
    table rather than a sample. Every view is replaced by a sentinel first,
    so a gate that failed to refuse would reach a sentinel, never a real
    route, and the failure names it."""

    def test_the_sweep_finds_the_population(self):
        reqs = _gated_requests(_app())
        # 87 measured 2026-09-26: 121 mutating endpoints, 34 of them not_device
        assert len({e for _, _, e, _ in reqs}) >= 80, len(reqs)
        assert any(e == "deploy.apply_deploy" or u == "/deploy/apply"
                   for _, u, e, _ in reqs)

    def test_every_one_is_403_and_no_view_runs(self, monkeypatch):
        app = _app()
        reached = []
        for endpoint in list(app.view_functions):
            monkeypatch.setitem(app.view_functions, endpoint,
                                (lambda ep: (lambda *a, **k: (reached.append(ep) or ("", 599))))(endpoint))
        client = app.test_client()
        wrong = []
        for method, url, endpoint, kind in _gated_requests(app):
            resp = client.open(url, method=method, json={})
            body = resp.get_json(silent=True) or {}
            if resp.status_code != 403 or body.get("requires_identity") is not True:
                wrong.append((method, url, kind, resp.status_code))
        assert not wrong, wrong
        assert not reached, reached


class TestAPersonPasses:
    def test_deploy_apply_reaches_its_own_validation(self):
        """The default harness identity is a verified person: the gate lets
        the request through, and the route's own input check answers."""
        resp = _app().test_client().post("/deploy/apply", json={})
        assert resp.status_code != 403, resp.get_json(silent=True)


class TestAServiceIsNotAPerson:
    @pytest.mark.parametrize("path", ["/deploy/apply", "/settings",
                                      "/templatize/bulk/apply"])
    def test_a_service_is_refused(self, monkeypatch, path):
        from modules import identity
        svc = identity.Identity(actor="service:abc.access", kind="service",
                                service_id="abc.access", verified=True,
                                outcome="ok", peer="198.51.100.7",
                                peer_trusted=True, header_present=True)
        monkeypatch.setattr(identity, "identify", lambda _r: svc)
        resp = _app().test_client().post(path, json={})
        body = resp.get_json(silent=True) or {}
        assert resp.status_code == 403, (path, body)
        assert body.get("requires_person") is True, body


class TestTheTerminal:
    def _client(self, monkeypatch):
        import app as A
        opened = []
        monkeypatch.setattr(A, "ensure_terminal_session",
                            lambda ip, sessions, key="": opened.append(ip))
        monkeypatch.setattr(A, "start_terminal_reader", lambda *a, **k: None)
        return A.socketio.test_client(A.app), opened

    @pytest.mark.real_identity
    def test_no_identity_opens_no_shell(self, monkeypatch):
        client, opened = self._client(monkeypatch)
        client.emit("connect_terminal", {"ip": "192.0.2.1"})
        got = client.get_received()
        assert opened == []
        assert any("refused" in (m["args"][0].get("output", "") if m["args"] else "")
                   for m in got if m["name"] == "terminal_output"), got

    def test_a_person_opens_one(self, monkeypatch):
        """Control: the refusal above is the gate, not a broken handler."""
        client, opened = self._client(monkeypatch)
        client.emit("connect_terminal", {"ip": "192.0.2.1"})
        assert opened == ["192.0.2.1"]


# ---------------------------------------------------------------------------
# The actor
# ---------------------------------------------------------------------------

def _reads_actor_from_request(src: str) -> list:
    """Line numbers of calls that take an actor from the request or a literal."""
    return [line for _fn, line in _actor_sites(src)]


def _actor_sites(src: str) -> list:
    """(enclosing function, line) for each actor not taken from the gate."""
    tree = ast.parse(src)
    owner = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                owner.setdefault(id(node), fn.name)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "actor"):
            hits.append((owner.get(id(node), ""), node.lineno))
        # A literal names nobody either: Save All recorded `actor="user"`.
        for kw in node.keywords:
            if (kw.arg == "actor" and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)):
                hits.append((owner.get(id(node), ""), node.lineno))
    return hits


#: Named, with the reason, and capped. Growing this list is the scan being
#: switched off one site at a time.
ACTOR_EXEMPTIONS = {
    ("routes/templates.py", "_seed_and_commit"): (
        "seeds the shipped template library on the first READ of it, from a "
        "GET no gate covers: nobody decided it, so a person's name would be a "
        "claim. 'nmas' is not one of ACTOR_CONVENTION's three kinds either "
        "(recorded under B12)."),
}


class TestTheActorIsTheVerifiedOne:
    FILES = ["app.py"] + [os.path.join("routes", f)
                          for f in sorted(os.listdir(os.path.join(ROOT, "routes")))
                          if f.endswith(".py")]

    def test_no_route_takes_its_actor_from_the_request(self):
        offenders, exempted = {}, set()
        for rel in self.FILES:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                for fn, line in _actor_sites(fh.read()):
                    if (rel, fn) in ACTOR_EXEMPTIONS:
                        exempted.add((rel, fn))
                    else:
                        offenders.setdefault(rel, []).append((fn, line))
        assert not offenders, offenders
        assert exempted == set(ACTOR_EXEMPTIONS), (
            "an exemption that matches nothing is a ghost; remove it",
            set(ACTOR_EXEMPTIONS) - exempted)
        assert len(ACTOR_EXEMPTIONS) <= 2

    def test_the_scan_can_see_one(self):
        """Control, on the exact shape that was there."""
        assert _reads_actor_from_request(
            'x = f(actor=data.get("actor", "user"))') == [1]
        assert _reads_actor_from_request('save(actor="user")') == [1]

    def test_the_verified_actor_is_used(self):
        n = sum(open(os.path.join(ROOT, rel), encoding="utf-8").read()
                .count("request_actor()") for rel in self.FILES)
        assert n >= 16, n       # 14 replaced, the deploy commit, Save All

    def test_request_actor_is_the_gates_identity(self):
        from flask import g
        from modules import identity
        person = identity.Identity(actor="p@example.invalid", kind="person",
                                   verified=True, outcome="ok",
                                   peer_trusted=True)
        with _app().test_request_context("/"):
            assert identity.request_actor() == identity.UNAUTHENTICATED
            g.nmas_identity = identity.Identity()          # not verified
            assert identity.request_actor() == identity.UNAUTHENTICATED
            g.nmas_identity = person
            assert identity.request_actor() == "p@example.invalid"
        assert identity.request_actor() == identity.UNAUTHENTICATED

    def test_a_gated_request_puts_the_person_on_g(self, monkeypatch):
        from flask import g
        from modules import identity
        seen = {}
        import routes.deploy as D

        def spy():
            seen["actor"] = identity.request_actor()
            return D.jsonify({"ok": False}), 400
        monkeypatch.setitem(_app().view_functions, "deploy.apply", spy)
        _app().test_client().post("/deploy/apply", json={})
        from tests.conftest import TEST_PERSON
        assert seen["actor"] == TEST_PERSON


class TestTheBulkIntentCliRunsInProcess:
    def test_it_runs_without_the_app_and_refuses_an_unknown_list(self, tmp_path):
        """It used to POST to the app, which P.3 refuses from the host. It now
        imports the route helpers; a wrong list name is refused by them."""
        change = tmp_path / "c.json"
        change.write_text(json.dumps({"summary": "x", "steps": [
            {"path": "logging.hosts", "before": [], "after": []}]}))
        out = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "nmas-bulk-intent"),
             "--list", "no-such-list-p3", "--devices", "r1",
             "--change", str(change)],
            capture_output=True, text=True, timeout=120, cwd=str(tmp_path),
            env={**os.environ, "NMAS_HEADLESS": "1"})
        assert out.returncode == 1, (out.stdout, out.stderr)
        assert "no device list named 'no-such-list-p3'" in out.stdout, out.stdout
