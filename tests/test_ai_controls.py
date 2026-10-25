"""The AI controls' one registry and their readiness (PHASE8_PLAN 15.13; NSOT_GUI_BRIEF section
6, "AI controls"; modules/ai/controls.py).

- **The registry is complete, by a scan.** Every route that reaches the gateway's `ask` (read
  by parsing `routes/` and `app.py` with `modules/`, following references through each
  module's functions, never by substring) is a registered control's endpoint or is in
  `ALSO_REACHES` with why, and every registered endpoint is a route the scan finds. A planted
  route reaching it directly, through a helper in its own module, or through another module's
  function is found; one that does not reach it is not. Every task `profiles.TASKS` pins is a
  registered control's.
- **A template posting to a control's endpoint draws the mark,** its disabled state and its
  reason (`ai.mark`, `ai.attrs`, `ai.reason`); a planted one without them is found. A control
  registered as not drawn is drawn by no template.
- **Every drawn control is checked through its real route,** by a call of
  `ai_controls_check.check_screen` naming it in a test file, found by parsing.
- **Readiness asks the gateway's questions in the gateway's order,** through the real chain:
  the allowance (`settings_schema`), the key's presence without decrypting it (the secrets
  store's `is_set`; a decrypt planted to fail is never reached), and today's spend from the
  record against the day cap; at the cap exactly a call is still allowed (the gateway's own
  comparison), past it the reason names both operands; an unreadable record is its own state.
- **The mark's hover** names each task's words, its pinned model and its per-call cap.
- **The spend is read once per request,** however many controls a page draws.
- **No key's value** is in anything a control returns.
"""
import ast
import json
import os
import re

import pytest

from modules.ai import calls, controls, profiles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The one call every AI path ends in.
SEED = ("modules.ai.gateway", "ask")


# ------------------------------------------------------------------------- the scan of routes

def _dotted(rel: str) -> str:
    return rel[:-3].replace(os.sep, ".").replace("/", ".")


def _sources() -> dict:
    """``{relative path: text}``: app.py, routes/ and modules/, as git tracks them (never a
    walk of the disk, which would read an agent's worktree as program)."""
    from tests.source_index import tracked
    paths = tracked("app.py")
    paths += tracked("routes", suffix=".py", recursive=False)
    paths += tracked("modules", suffix=".py")
    out = {}
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            out[os.path.relpath(p, ROOT)] = fh.read()
    return out


def _imports(nodes, modules: set) -> dict:
    """alias -> ("mod", module) or ("obj", module, name), from the import statements given."""
    out = {}
    for node in nodes:
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname and a.name in modules:
                    out[a.asname] = ("mod", a.name)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for a in node.names:
                full = f"{node.module}.{a.name}"
                out[a.asname or a.name] = (("mod", full) if full in modules
                                           else ("obj", node.module, a.name))
    return out


def _refs(func, mod: str, imports: dict, local: set, modules: set) -> set:
    """What *func* references: (module, name) for each module attribute, imported name and
    function of its own module it names (a call or not: a function passed is reached). Its
    own imports (a function-local `from modules.ai import explain`) over its module's."""
    own = dict(imports)
    own.update(_imports(ast.walk(func), modules))
    out = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            got = own.get(node.value.id)
            if got and got[0] == "mod":
                out.add((got[1], node.attr))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            got = own.get(node.id)
            if got and got[0] == "obj":
                out.add((got[1], got[2]))
            elif node.id in local:
                out.add((mod, node.id))
    return out


def _blueprint(tree) -> str:
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Blueprint"
                and node.args and isinstance(node.args[0], ast.Constant)):
            return node.args[0].value
    return ""


def _endpoint(func, bp: str):
    """The endpoint a route-decorated function serves, or None."""
    for d in func.decorator_list:
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr == "route"):
            named = [k.value.value for k in d.keywords
                     if k.arg == "endpoint" and isinstance(k.value, ast.Constant)]
            name = named[0] if named else func.name
            return f"{bp}.{name}" if bp else name
    return None


def reaching_endpoints(sources: dict) -> set:
    """Every route endpoint whose function reaches `gateway.ask`, through any chain of
    references across the modules given."""
    trees = {_dotted(rel): (rel, ast.parse(text)) for rel, text in sources.items()}
    modules = set(trees)
    # The packages too (`from modules import ai` names a package, not an object in it).
    modules |= {m.rsplit(".", 1)[0] for m in trees if "." in m}
    funcs, endpoints = {}, {}
    for mod, (rel, tree) in trees.items():
        top = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        local = {f.name for f in top}
        imports = _imports([n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))],
                           modules)
        bp = _blueprint(tree) if rel.startswith("routes") or rel == "app.py" else ""
        for f in top:
            funcs[(mod, f.name)] = _refs(f, mod, imports, local, modules)
            if rel.startswith("routes") or rel == "app.py":
                ep = _endpoint(f, bp)
                if ep:
                    endpoints[ep] = (mod, f.name)
    reached = {SEED}
    grew = True
    while grew:
        grew = False
        for key, refs in funcs.items():
            if key not in reached and refs & reached:
                reached.add(key)
                grew = True
    return {ep for ep, key in endpoints.items() if key in reached}


def _registered() -> set:
    return {ep for c in controls.CONTROLS.values() for ep in c["endpoints"]}


def test_every_route_reaching_the_gateway_is_registered_and_each_registered_one_reaches_it():
    found = reaching_endpoints(_sources())
    assert len(found) >= 5, f"the scan's floor: the five known routes ({sorted(found)})"
    assert found == _registered() | set(controls.ALSO_REACHES), (
        "a route reaches the AI gateway without a registered control (modules/ai/controls.py "
        f"CONTROLS or ALSO_REACHES): {sorted(found - _registered() - set(controls.ALSO_REACHES))}"
        f"; registered and not reaching it: {sorted(_registered() - found)}")
    assert not _registered() & set(controls.ALSO_REACHES)
    import app as A
    assert _registered() | set(controls.ALSO_REACHES) <= set(A.app.view_functions)


PLANTED = {
    "direct": ("from modules.ai import nl_query\n"
               "@bp.route('/x', methods=['POST'])\n"
               "def planted():\n    return nl_query.metrics('Lab', 'q', actor='a')\n"),
    "passed, not called": ("from modules.ai import explain\n"
                           "def _helper(fn):\n    return fn('p', actor='a')\n"
                           "@bp.route('/x', methods=['POST'])\n"
                           "def planted():\n    return _helper(explain.explain)\n"),
    "through a helper of its own": ("@bp.route('/x', methods=['POST'])\n"
                                    "def planted():\n    return _go()\n"
                                    "def _go():\n"
                                    "    from modules.ai.connection import check\n"
                                    "    return check(actor='a')\n"),
    "through another module": ("@bp.route('/x', methods=['POST'])\n"
                               "def planted():\n"
                               "    from modules import installation_settings as I\n"
                               "    return I.test_card('ai', actor='a')\n"),
}


@pytest.mark.parametrize("how", sorted(PLANTED))
def test_the_scan_finds_a_planted_route(how):
    head = "from flask import Blueprint\nbp = Blueprint('planted', __name__)\n"
    sources = dict(_sources(), **{os.path.join("routes", "planted_ai.py"): head + PLANTED[how]})
    assert "planted.planted" in reaching_endpoints(sources) - reaching_endpoints(_sources())


def test_the_scan_does_not_find_a_route_that_reaches_no_model():
    text = ("from flask import Blueprint\nbp = Blueprint('planted', __name__)\n"
            "from modules.ai import profiles, calls\n"
            "@bp.route('/x')\ndef planted():\n"
            "    return str(profiles.cap_per_call('explain')) + str(calls.read())\n")
    sources = dict(_sources(), **{os.path.join("routes", "planted_ai.py"): text})
    assert "planted.planted" not in reaching_endpoints(sources)


# ------------------------------------------------------------------------ the templates' marks

URL_FOR = re.compile(r"url_for\(\s*['\"]([\w.]+)['\"]")
INCLUDE = re.compile(r"\{%-?\s*include\s+[\"']v2/([\w.]+)[\"']")
MARK_PARTS = ("ai.mark(", "ai.attrs(", "ai.reason(")


def _with_includes(name: str, texts: dict, seen=None) -> str:
    """A template's text with every template it includes, as it is drawn (a builder names
    Ask in words' address and includes the row that draws it)."""
    seen = set() if seen is None else seen
    if name in seen or name not in texts:
        return ""
    seen.add(name)
    text = texts[name]
    return text + "".join(_with_includes(n, texts, seen) for n in INCLUDE.findall(text))


def unmarked(texts: dict) -> list:
    """Each template naming a registered control's endpoint whose drawing (it and what it
    includes) lacks the mark, its disabled state or its reason."""
    out = []
    for name, text in sorted(texts.items()):
        if set(URL_FOR.findall(text)) & _registered():
            drawn = _with_includes(name, texts)
            missing = [p for p in MARK_PARTS if p not in drawn]
            if missing:
                out.append((name, missing))
    return out


def _templates() -> dict:
    out = {}
    from tests.source_index import tracked
    for p in tracked("templates/v2", suffix=".html", recursive=False):
        with open(p, encoding="utf-8") as fh:
            out[os.path.basename(p)] = fh.read()
    return out


def test_every_template_drawing_an_ai_control_draws_its_mark_state_and_reason():
    texts = _templates()
    assert len(texts) > 100, "the floor on templates read"
    posting = [n for n, t in texts.items() if set(URL_FOR.findall(t)) & _registered()]
    assert len(posting) >= 3, posting
    assert unmarked(texts) == []
    for name, c in controls.CONTROLS.items():
        drawn = sorted(n for n, t in texts.items() if f"ai_control('{name}')" in t)
        if c["template"] is None:
            assert drawn == [], f"{name} is registered as not drawn, and {drawn} draw it"
        else:
            assert drawn == [os.path.basename(c["template"])], (name, drawn)


def test_a_template_posting_to_an_ai_endpoint_without_the_mark_is_found():
    planted = ("<form hx-post=\"{{ url_for('v2.monitoring_alert_explain', pack_id=p) }}\">"
               "<button type=\"submit\"{{ gate('configure') }}>Explain</button></form>")
    assert unmarked({"_planted.html": planted}) == [("_planted.html", list(MARK_PARTS))]
    marked = planted + "{{ ai.mark(c) }}{{ ai.attrs(c) }}{{ ai.reason(c) }}"
    assert unmarked({"_planted.html": marked}) == []
    # Drawn by a template it includes, as the builders draw Ask in words.
    row = "{{ ai.mark(c) }}<button{{ ai.attrs(c) }}></button>{{ ai.reason(c) }}"
    page = "{% set u = url_for('v2.history_ask_logs_words') %}{%- include \"v2/_row.html\" %}"
    assert unmarked({"_page.html": page, "_row.html": row}) == []
    assert unmarked({"_page.html": page, "_row.html": "<button></button>"}) == [
        ("_page.html", list(MARK_PARTS))]


def test_every_task_is_a_registered_control_s():
    assert {c["task"] for c in controls.CONTROLS.values()} == set(profiles.TASKS)
    for name, c in controls.CONTROLS.items():
        assert c["words"] and c["screen"] and c["beside"], name
        if c["template"]:
            assert c["endpoints"], f"{name} is drawn and reaches no endpoint"
            assert os.path.isfile(os.path.join(ROOT, "templates", c["template"])), name


def test_each_drawn_control_is_checked_through_its_route():
    """A call of `ai_controls_check.check_screen` naming the control, in a test file."""
    from tests import ai_controls_check as AIC

    checked = set()
    from tests.source_index import tracked
    for p in [t for t in tracked("tests", suffix=".py", recursive=False)
              if os.path.basename(t).startswith("test_")]:
        with open(p, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "check_screen" and len(node.args) >= 3
                    and isinstance(node.args[2], ast.Constant)):
                checked.add(node.args[2].value)
    drawn = {n for n, c in controls.CONTROLS.items() if c["template"]}
    assert drawn <= checked, sorted(drawn - checked)
    assert drawn == set(AIC.MARKUP), "each drawn control's markup is named for the check"


# ------------------------------------------------------------------------------- readiness

KEY = "sk-ant-planted-controls-key-0123456789"


@pytest.fixture
def chain(tmp_path, monkeypatch):
    """The real chain beneath the seams: the allowance and the day cap from settings, the
    key's presence from the stored settings (a decrypt fails if it is ever asked), the spend
    from a record of its own."""
    from modules import secrets_store, settings_schema
    settings = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                              "reason": "the lab's proof of concept"},
                "ai_cap_usd_per_day": 1.50}
    monkeypatch.setattr(settings_schema, "get_setting", lambda k, d=None: settings.get(k, d))
    stored = {"anthropic_api_key": "enc:v1:planted-sealed-value"}
    monkeypatch.setattr(secrets_store, "get_user_setting", lambda k, d=None: stored.get(k, d))

    def never(*_a, **_k):
        raise AssertionError("the key was decrypted")
    monkeypatch.setattr(secrets_store, "decrypt_value", never)
    monkeypatch.setattr(secrets_store, "get_secret", never)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))

    class C:
        pass
    c = C()
    c.settings, c.stored = settings, stored
    return c


def _spend(usd, at="2026-10-25T06:00:00Z"):
    assert calls.record({"id": calls.new_id(), "feature": "explain", "verdict": "ok",
                         "cost_usd": usd, "at": at})["recorded"]


@pytest.mark.parametrize("task", sorted(profiles.TASKS))
def test_ready_through_the_real_chain_and_the_hover_names_task_model_and_cap(chain, task):
    got = controls.readiness(task, today="2026-10-25")
    assert got["ready"] is True and got["kind"] == "" and got["reason"] == "", got
    pin = profiles.TASKS[task]
    title = got["title"]
    assert pin["words"] in title and pin["model"] in title, title
    assert profiles.MODELS[pin["model"]]["words"] in title, title
    assert f"${profiles.cap_per_call(task):.4f}" in title, title


def test_hosted_ai_off_is_said_first(chain):
    chain.settings.pop("ai_hosted")
    chain.stored.clear()
    got = controls.readiness("explain", today="2026-10-25")
    assert (got["ready"], got["kind"]) == (False, "ai_off")
    assert "hosted AI is off" in got["reason"]


def test_an_allowance_without_its_reason_is_off_as_the_gateway_reads_it(chain):
    chain.settings["ai_hosted"] = {"by": "operator@example.com", "reason": ""}
    assert controls.readiness("explain", today="2026-10-25")["kind"] == "ai_off"


def test_no_key_is_said_before_the_spend_and_presence_never_decrypts(chain):
    chain.stored.clear()
    got = controls.readiness("nl_query", today="2026-10-25")
    assert (got["ready"], got["kind"]) == (False, "no_key")
    assert "no Anthropic API key is set" in got["reason"]
    chain.stored["anthropic_api_key"] = "enc:v1:planted-sealed-value"
    assert controls._key_set() is True


def test_the_day_cap_counts_today_s_spend_and_names_both_operands(chain):
    per_call = profiles.cap_per_call("explain")
    _spend(1.0, at="2026-10-24T23:59:59Z")                 # yesterday's: not counted
    _spend(1.50 - per_call)                                 # at the cap exactly: allowed
    assert controls.readiness("explain", today="2026-10-25")["ready"] is True
    _spend(0.0001)
    got = controls.readiness("explain", today="2026-10-25")
    assert (got["ready"], got["kind"]) == (False, "day_cap")
    spent = 1.50 - per_call + 0.0001
    assert f"${spent:.4f}" in got["reason"] and f"${per_call:.4f}" in got["reason"]
    assert "$1.5000" in got["reason"] and "is over the day cap" in got["reason"]
    # A cheaper task's call may still fit what is left.
    assert controls.readiness("nl_query", today="2026-10-25")["ready"] is True


def test_an_unreadable_record_is_its_own_state(chain, monkeypatch):
    monkeypatch.setattr(calls, "spent_usd", lambda day: {
        "state": "unreadable", "usd": None, "calls": 0, "error": "planted: not JSON"})
    got = controls.readiness("explain", today="2026-10-25")
    assert (got["ready"], got["kind"]) == (False, "unreadable")
    assert "cannot be read (planted: not JSON)" in got["reason"]


def test_an_unknown_task_raises_naming_the_known_ones():
    with pytest.raises(KeyError, match="known:"):
        controls.readiness("no_such_task")


def test_the_spend_is_read_once_a_request_and_no_key_value_is_returned(chain, monkeypatch):
    import app as A
    read = []
    real = calls.spent_usd

    def counted(day):
        read.append(day)
        return real(day)
    monkeypatch.setattr(calls, "spent_usd", counted)
    with A.app.test_request_context("/v2/history"):
        got = [controls.control(n) for n in controls.CONTROLS]
        again = controls.control("explain")
    assert len(read) == 1 and again is got[1], read
    assert all(g["may_configure"] for g in got), "the test's viewer is a verified person"
    assert got[0]["settings_url"] == "/v2/settings/installation?tab=connections#card-ai"
    text = json.dumps(got, default=str)
    assert KEY not in text and "planted-sealed-value" not in text
