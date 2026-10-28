"""An AI call starts only from an explicit POST tied to a person's click (C1855; CLAUDE.md, AI
cost safety rule 1; the operator's Walk 2, 2026-10-27).

- **By parsing** (tests/test_ai_controls.py's scan of app.py, routes/ and modules/, following
  references through each module's functions): every way into the code that reaches
  `gateway.ask` (a function nothing else references, or a module's own top-level code) is a
  route served by POST alone and declared in modules/route_gates.py. A planted GET route, a
  route with no methods named (GET), a POST route no gate declares, a reader registered at a
  module's top level and a socket handler reaching it are each found.
- **Through the real routes:** loading and refreshing every page that draws an AI control,
  and the fragments they redraw (Monitoring › Alerts, its list, History and its list, a pack's
  card with a kept answer, History › Query's two Ask in words pages, a device's Intent tab,
  Settings › Installation › Connections), with hosted AI allowed and a key set, calls the
  gateway zero times and sends nothing. Every registered control names its pages here.
"""
import ast
import os
from html import unescape

import pytest

from modules import route_gates
from modules.ai import anthropic_adapter as A
from modules.ai import controls, gateway
from tests import test_ai_controls as T
from tests.test_ai_explain import _answer, world  # noqa: F401 (the fixture)
from tests.test_committed_before_p1 import host  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)

TOP = "<top level>"


def _methods(func):
    """The methods a route-decorated function names (GET when none is named)."""
    for d in func.decorator_list:
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr == "route"):
            for k in d.keywords:
                if k.arg == "methods" and isinstance(k.value, (ast.List, ast.Tuple)):
                    return sorted(e.value for e in k.value.elts if isinstance(e, ast.Constant))
            return ["GET"]
    return None


def entry_points(sources: dict) -> dict:
    """``{(module, function or TOP): {"endpoint", "methods"}}``: every way into the code that
    reaches the gateway: a function that reaches it and that nothing scanned references, and
    a module whose top-level code (a registration) references one that does."""
    trees = {T._dotted(rel): (rel, ast.parse(text)) for rel, text in sources.items()}
    modules = set(trees) | {m.rsplit(".", 1)[0] for m in trees if "." in m}
    funcs, routes = {}, {}
    for mod, (rel, tree) in trees.items():
        top = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        local = {f.name for f in top}
        imports = T._imports([n for n in tree.body if isinstance(n, (ast.Import,
                                                                      ast.ImportFrom))], modules)
        bp = T._blueprint(tree) if rel.startswith("routes") or rel == "app.py" else ""
        for f in top:
            funcs[(mod, f.name)] = T._refs(f, mod, imports, local, modules)
            if rel.startswith("routes") or rel == "app.py":
                ep = T._endpoint(f, bp)
                if ep:
                    routes[(mod, f.name)] = {"endpoint": ep, "methods": _methods(f)}
        rest = [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                             ast.Import, ast.ImportFrom))]
        funcs[(mod, TOP)] = T._refs(ast.Module(body=rest, type_ignores=[]), mod, imports, local,
                                    modules)
    reached = {T.SEED}
    grew = True
    while grew:
        grew = False
        for key, refs in funcs.items():
            if key not in reached and refs & reached:
                reached.add(key)
                grew = True
    referenced = set().union(*funcs.values())
    return {k: routes.get(k, {"endpoint": None, "methods": None}) for k in reached
            if k != T.SEED and (k[1] == TOP or k not in referenced)}


def violations(sources: dict, gates=None) -> list:
    """Each way in that is not a POST-only route its gate declares, in words."""
    gates = route_gates.GATES if gates is None else gates
    out = []
    for (mod, name), r in sorted(entry_points(sources).items()):
        if r["endpoint"] is None:
            out.append(f"{mod}.{name} reaches the AI gateway and is no route: a background "
                       "path (a reader, a job, a socket handler, a registration)")
        elif r["methods"] != ["POST"]:
            out.append(f"{r['endpoint']} reaches the AI gateway and is served by "
                       f"{', '.join(r['methods'])}, not POST alone")
        elif r["endpoint"] not in gates:
            out.append(f"{r['endpoint']} reaches the AI gateway and no gate declares it")
    return out


def test_every_way_to_the_gateway_is_a_gated_post():
    found = entry_points(T._sources())
    assert len(found) >= 6, f"the scan's floor: the six known routes ({sorted(found)})"
    assert violations(T._sources()) == []
    import app as APP
    served = {r.endpoint: r.methods - {"HEAD", "OPTIONS"} for r in APP.app.url_map.iter_rules()}
    for r in found.values():
        assert served[r["endpoint"]] == {"POST"}, r
        assert route_gates.gate_for(r["endpoint"]) is not None, r


HEAD = "from flask import Blueprint\nbp = Blueprint('planted', __name__)\n"
PLANTED = {
    "a GET route": (HEAD + "from modules.ai import explain\n"
                    "@bp.route('/x', methods=['GET'])\n"
                    "def planted():\n    return explain.explain('p', actor='a')\n",
                    "served by GET"),
    "a route naming no methods": (HEAD + "from modules.ai import nl_query\n"
                                  "@bp.route('/x')\n"
                                  "def planted():\n    return nl_query.metrics('L', 'q', actor='a')\n",
                                  "served by GET"),
    "a POST no gate declares": (HEAD + "from modules.ai import explain\n"
                                "@bp.route('/x', methods=['POST'])\n"
                                "def planted():\n    return explain.explain('p', actor='a')\n",
                                "no gate declares it"),
    "a reader registered at the top level": (
        "from modules import reader_job\nfrom modules.ai import explain\n"
        "READER = reader_job.register(reader_job.Reader(name='x', read=explain.explain))\n",
        "a background path"),
    "a socket handler": ("from modules.ai import explain\n"
                         "@socketio.on('explain')\n"
                         "def handler(data):\n    return explain.explain(data, actor='a')\n",
                         "a background path"),
}


@pytest.mark.parametrize("how", sorted(PLANTED))
def test_a_planted_way_in_is_found(how):
    text, words = PLANTED[how]
    sources = dict(T._sources(), **{os.path.join("routes", "planted_ai.py"): text})
    found = violations(sources)
    assert len(found) == 1 and words in found[0], found


# --------------------------------------------------------------------- through the real routes

def _pages(world):
    """Each registered AI control: the pages and fragments that draw it, as a person loads
    them (and as a live redraw asks for them again)."""
    pid = world.pack["id"]
    return {
        "explain": ["/v2/monitoring/alerts", "/v2/monitoring/alerts/list",
                    "/v2/monitoring/alerts/history?range=all&show=all",
                    "/v2/monitoring/alerts/history/list?range=all&show=all",
                    f"/v2/monitoring/alerts/pack/{pid}"],
        "ask_in_words": ["/v2/history/query/ask/metrics?list=Lab",
                         "/v2/history/query/ask/logs?list=Lab"],
        "ai_card_test": ["/v2/settings/installation?tab=ai"],
    }


#: Drawn only for a device with committed intent: `test_the_intent_tab_calls_no_model`'s.
INTENT_PAGES = {"intent_in_words": ["/v2/device/s1?tab=intent&list=Lab"]}
#: Drawn only on a response awaiting a person: `test_sdn_responses_call_no_model`'s.
SDN_PAGES = {"sdn_classify": ["/v2/sdn/responses?list=Default",
                              "/v2/sdn/view?tab=responses&list=Default"]}


def _count_ai(monkeypatch) -> dict:
    """The gateway's calls and the provider's requests, counted from here on."""
    seen = {"asked": [], "sends": []}
    real = gateway.ask

    def counted(*a, **k):
        seen["asked"].append(a[0] if a else k.get("feature"))
        return real(*a, **k)
    monkeypatch.setattr(gateway, "ask", counted)

    def send(body, key):
        seen["sends"].append(body)
        pytest.fail("a page load reached the provider")
    monkeypatch.setattr(A, "send", send)
    return seen


def _load_each(client, pages) -> set:
    """Each page loaded, redrawn as a fragment and refreshed: the controls they drew."""
    drawn = set()
    for name, urls in pages.items():
        for url in urls:
            for headers in ({}, {"HX-Request": "true"}, {}):        # load, redraw, refresh
                r = client.get(url, headers=headers)
                assert r.status_code == 200, (url, r.status_code)
                if f'data-ai-control="{name}"' in unescape(r.get_data(as_text=True)):
                    drawn.add(name)
    return drawn


def test_loading_and_refreshing_every_page_with_an_ai_control_calls_no_model(world,
                                                                              monkeypatch):
    world.answer = _answer(world.pack)
    c = world.lab["client"]
    # The metrics builder asks Prometheus for its limits and series, which the pack's captures
    # do not hold: the builder is drawn as for a network with no Prometheus (its Ask in words
    # row drawn as ever; no AI is near it).
    class NoPrometheus:
        def is_configured(self):
            return False
    monkeypatch.setattr("modules.history_promq._client", lambda *a, **k: NoPrometheus())
    # A kept answer, so the pack's card draws one (C1853): made before counting starts.
    assert c.post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
                  headers={"HX-Request": "true"}).status_code == 200
    assert len(world.sent) == 1
    seen = _count_ai(monkeypatch)
    pages = _pages(world)
    assert set(pages) | set(INTENT_PAGES) | set(SDN_PAGES) == set(controls.CONTROLS), \
        "every registered control names its pages"
    drawn = _load_each(c, pages)
    assert drawn == set(pages), f"pages that drew no control: {set(pages) - drawn}"
    assert seen == {"asked": [], "sends": []}


def test_the_intent_tab_calls_no_model(host, monkeypatch, tmp_path):  # noqa: F811
    """A device's Intent tab, drawn for s1's committed intent (tests/test_committed_before_p1's
    list), hosted AI allowed and a key set."""
    from modules import settings_schema
    from modules.ai import calls
    hosts = settings_schema.get_setting
    extra = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                           "reason": "the lab's proof of concept"}}
    monkeypatch.setattr(settings_schema, "get_setting",
                        lambda k, d=None: extra[k] if k in extra else hosts(k, d))
    monkeypatch.setattr(gateway, "_api_key", lambda: "sk-planted-entry-points-0123456789")
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    seen = _count_ai(monkeypatch)
    assert _load_each(host["client"], INTENT_PAGES) == set(INTENT_PAGES)
    assert seen == {"asked": [], "sends": []}


def test_sdn_responses_call_no_model(tmp_path, monkeypatch):
    """SDN › Responses with a scan awaiting a person (PHASE8_PLAN 17.1 S7), hosted AI allowed
    and a key set: drawing Classify asks no model."""
    import app as APP
    from modules.ai import calls
    from modules.sdn import loop
    from modules.settings_schema import write_settings
    from tests.test_sdn_connections import make_networks

    make_networks(tmp_path, monkeypatch)
    assert write_settings({"ai_hosted": {"by": "operator@example.com",
                                         "at": "2026-10-27T00:00:00Z",
                                         "reason": "the lab's proof of concept"}})["ok"]
    monkeypatch.setattr(gateway, "_api_key", lambda: "sk-planted-entry-points-0123456789")
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    loop.propose("Default", {"key": "k1", "rule": "scan", "title": "SDN scan",
                             "dpid_hex": "0000000000000001", "source": "192.0.2.1",
                             "words": "192.0.2.1 reached 25 ports"}, "drop_source", "low",
                 why="HITL")
    seen = _count_ai(monkeypatch)
    assert _load_each(APP.app.test_client(), SDN_PAGES) == set(SDN_PAGES)
    assert seen == {"asked": [], "sends": []}
