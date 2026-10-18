"""Every reveal and secret-bearing answer says ``Cache-Control: no-store`` (C840, re-graded B
by the operator 2026-10-15: secrets).

app.py's header hook gave every HTML answer ``no-cache, must-revalidate, no-transform`` by
ASSIGNMENT, so no route could say no-store: a revealed golden, bootstrap config or log line was
a page a browser and any cache on the way may keep. The hook now sets its default only where a
route set none, and every reveal says no-store through `outbound.no_store`.

THE POPULATION, by property, never by list:

- every endpoint the gate table declares ``reveal`` (`route_gates.GATES`: a secret or a
  device's configuration leaves to the caller), read from the table, so a newly reveal-gated
  route is in it by being declared;
- every routed view that reveals CONDITIONALLY (a GET that gates itself, route_gates' own
  words): found by parsing every blueprint for a view that calls the reveal cores
  (`bootstrap_reveal`; today's `_serve_config` and `config_text` until P7-27) or asks `identity.require` for
  ``reveal``.

Each one's view is wrapped by `no_store` (a scan: a new member without it fails), and each
one's answer, asked here, carries no-store (one test per route, parametrised over the
population, with a floor). The secret-bearing answers themselves are asserted where they are
drawn: tests/test_reveals_fail_closed.py (golden and bootstrap revealed), test_log_reveal.py,
test_breakglass_export.py. An ordinary page keeps the default.
"""

import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The calls that make a view a reveal: the cores every conditional reveal goes through.
#: `_serve_config` and `config_text` (today's golden routes' helper) left with them at 7.8
#: (2026-10-17, P7-27).
REVEAL_CORES = {"bootstrap_reveal"}
#: The population's floor (2026-10-15: 10 reveal-gated endpoints, 3 conditional GETs).
#: Conditional 3 -> 2: today's onboard.bootstrap left at 7.8 (P7-25); 2 -> 0: today's
#: golden.version and golden.diff left with today's index (P7-27). Every reveal now is gated
#: by declaration; the scan stays for the next view that reveals conditionally, and its
#: predicate is shown to find one (TestThePopulation).
FLOOR_GATED, FLOOR_CONDITIONAL = 10, 0


@pytest.fixture(scope="module")
def flask_app():
    os.environ.setdefault("NMAS_HEADLESS", "1")
    import app as A
    return A.app


def _gated():
    from modules.route_gates import GATES
    return sorted(ep for ep, g in GATES.items() if g.kind == "reveal")


def _asks_for_reveal(call) -> bool:
    name = getattr(call.func, "attr", getattr(call.func, "id", ""))
    if name in REVEAL_CORES:
        return True
    if name != "require":
        return False
    words = [a.value for a in call.args if isinstance(a, ast.Constant)]
    words += [k.value.value for k in call.keywords
              if k.arg == "action" and isinstance(k.value, ast.Constant)]
    return "reveal" in words


def _conditional(flask_app):
    """Every routed view in routes/ whose body asks for a reveal, as its endpoint."""
    by_func = {}
    for ep, view in flask_app.view_functions.items():
        inner = getattr(view, "__wrapped__", view)
        code = getattr(inner, "__code__", None)
        if code is not None:
            by_func[(os.path.realpath(code.co_filename), code.co_firstlineno)] = ep
    found = set()
    folder = os.path.join(ROOT, "routes")
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(folder, fname)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            if not any(getattr(getattr(d, "func", None), "attr", "") == "route"
                       for d in fn.decorator_list):
                continue
            if not any(_asks_for_reveal(c) for c in ast.walk(fn) if isinstance(c, ast.Call)):
                continue
            first = min([fn.lineno] + [d.lineno for d in fn.decorator_list])
            ep = by_func.get((os.path.realpath(path), fn.lineno)) or \
                by_func.get((os.path.realpath(path), first))
            assert ep, f"{fname}:{fn.name} asks for a reveal and is no endpoint the app serves"
            found.add(ep)
    return sorted(found)


def _population(flask_app):
    return sorted(set(_gated()) | set(_conditional(flask_app)))


class TestThePopulation:
    def test_it_has_its_floor(self, flask_app):
        assert len(_gated()) >= FLOOR_GATED, _gated()
        conditional = [ep for ep in _conditional(flask_app) if ep not in _gated()]
        assert len(conditional) >= FLOOR_CONDITIONAL, conditional
        # The planted cases the parse must find (the golden GETs were the last real ones, until
        # they left with today's index at 7.8, 2026-10-17, P7-27): a call to a reveal core, and
        # a view asking `identity.require` for a reveal; and the control, a require for
        # anything else.
        calls = [n for n in ast.walk(ast.parse(
            "bootstrap_reveal(repo, host)\nidentity.require(request, 'reveal')\n"
            "identity.require(request, action='reveal')\nidentity.require(request, 'confirm')"))
            if isinstance(n, ast.Call)]
        assert [_asks_for_reveal(c) for c in calls] == [True, True, True, False]

    def test_every_member_says_no_store(self, flask_app):
        """The scan: a newly reveal-gated route, or a view newly calling a reveal core,
        without `no_store` fails here, by name."""
        missing = [ep for ep in _population(flask_app)
                   if not getattr(flask_app.view_functions[ep], "no_store", False)]
        assert missing == [], f"a reveal that does not say no-store: {missing}"


def _url(flask_app, ep):
    """The endpoint's rule with a placeholder for each of its arguments, and its method."""
    rule = next(r for r in flask_app.url_map.iter_rules() if r.endpoint == ep)
    url = rule.rule
    for arg in rule.arguments:
        url = url.replace(f"<{arg}>", "zz-none")
        for conv in ("path", "run_id", "string", "int"):
            url = url.replace(f"<{conv}:{arg}>", "zz-none")
    method = "POST" if "POST" in rule.methods else "GET"
    return url, method


#: Each reveal asked once as a person with nothing it can act on: the answer is the view's own
#: (a refusal, mostly), and `no_store` puts the header on every answer the view gives.
def _population_static():
    os.environ.setdefault("NMAS_HEADLESS", "1")
    import app as A
    return _population(A.app)


@pytest.mark.parametrize("ep", _population_static())
def test_its_answer_says_no_store(flask_app, ep):
    url, method = _url(flask_app, ep)
    client = flask_app.test_client()
    r = client.post(url, data={}) if method == "POST" else client.get(url)
    from modules.outbound import NO_STORE
    assert r.status_code < 500, (ep, r.status_code, r.get_data(as_text=True)[:300])
    # Exactly the view's own header: a JSON answer's default (`no-store` alone) would pass a
    # looser check for an answer the view never gave (a gate's refusal, say).
    assert r.headers.get("Cache-Control") == NO_STORE, \
        (ep, method, url, r.status_code, r.headers.get("Cache-Control"))


class TestTheHookIsADefault:
    def test_an_ordinary_page_keeps_the_default(self, flask_app):
        client = flask_app.test_client()
        for path in ("/", "/v2/help/credentials/panel"):
            r = client.get(path)
            assert r.mimetype == "text/html", path
            assert r.headers.get("Cache-Control") == "no-cache, must-revalidate, no-transform", \
                (path, r.headers.get("Cache-Control"))

    def test_a_route_s_own_header_stands(self, flask_app):
        """An HTML answer that set its own Cache-Control keeps it (the reveals' case, asked of
        the hook directly so it does not depend on any one route)."""
        from flask import Response
        with flask_app.test_request_context("/v2/anything"):
            resp = Response("<p>x</p>", mimetype="text/html")
            resp.headers["Cache-Control"] = "no-store, no-transform"
            for hook in flask_app.after_request_funcs.get(None, []):
                if hook.__name__ == "_cache_policy":
                    resp = hook(resp)
                    break
            else:
                pytest.fail("app.py's cache hook is not installed")
        assert resp.headers["Cache-Control"] == "no-store, no-transform"
