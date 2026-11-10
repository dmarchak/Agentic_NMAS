"""What a v2 route hands its template, and what the template reads of it.

**Not a test module.** Stage 7 section 10, acceptance criterion 4 ("payloads drawn"), re-based
on v2 (P7-04, 2026-10-15). Today's pages draw in the browser from JSON, and
`tests/payload_render.py` compares a JSON payload with the shipped JavaScript that reads it.
v2 draws on the server: a route builds a context and `render_template` draws it, so the
payload IS the context, and the renderer IS the template.

**What it compares, and at what grain:**

* **Carried keys** come from a REAL render: Flask's `template_rendered` signal, connected while
  the pages and fragments are requested through the test client, records the context each
  route passed (`render_template(name, **ctx)`), never a hand-built dict. A key is every
  top-level name the route passed and every key NAME at every depth beneath it: a dict's keys,
  a dataclass's fields, a named tuple's fields. What every page receives without its route
  asking (Flask's `request`, `session`, `g`, `config`, and the context processors' names) is
  not the route's payload and is left out, when it holds the value injected: a route that
  passes its own value under one of those names (`g=` for its payload) has shadowed it, and
  that value is examined (`given`; C2082).
* **Template reads** come from the template's Jinja AST, parsed by the app's own environment
  (`jinja_env.parse`), and from every template it extends, includes or imports, followed by
  name: a name loaded, an attribute (`x.name`), a constant subscript (`x['name']`), a
  constant `.get('name')`, a constant `'name' in x`, and a filter's or test's attribute
  argument (`map(attribute='name')`, `selectattr('name')`, `sort(attribute='name')`,
  `groupby('name')`). Parsed, never matched as text: a template's comments and prose name
  fields they do not draw.
* **Keys read as data:** a dict the template iterates (`for k in x`, `x.items()`,
  `x.values()`, `x.keys()`, `x | dictsort`) or indexes by a variable (`x[row.kind]`) has DATA
  as its keys (a device, an outcome), drawn by iteration, never by name: its keys are not
  examined, its values are.
* **Handed on whole:** a value passed to `tojson` reaches the page whole (a confirm body, a
  script's data); nothing beneath it is examined.

**What it cannot see, stated so it is not read as seen:** the comparison is by key NAME
within one template's closure, not by path, so a key read on another object with the same
name (`name`, `host`, `ok`) counts as read; a key the fixture's render does not carry is not
examined; a Python filter or global the template calls (`gate`, `one_run`, `age_words`) may
read keys itself, and those keys read as undrawn unless the template also names them; and a
template no measured request renders is not examined at all (the test names those).

**The loops, which state the test data reaches (C1274):** a key carried in an EMPTY list hides
every field its items would carry, from the comparison above and from every check that
photographs the page: the loop's body never drew. So while the walk runs, every `{% for %}` in
a v2 template is compiled with one mark more, first in its body (`recording_loops`): the body
ran at least once, on this template's line. The population is every `{% for %}` in every
template the measured renders reach (`loops`), each named by its template and its iterable as
written (`{% for d in s.skipped %}` is `s.skipped`), a second loop over the same iterable in
the same template numbered `#2`. A loop whose body never drew is one the fixtures do not reach:
its collection was empty (or absent) in every render, or the branch holding it never ran. What
it cannot see: a collection drawn by a filter (`join`, `map`, `length`) rather than a loop, and
which item reached a nested field (a loop over rows drew if ANY row was drawn).
"""

import contextlib
import dataclasses
import os
import re
from html import unescape
from typing import NamedTuple

from jinja2 import nodes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Filters and tests whose constant first argument names an attribute read on each item.
_ATTR_FIRST = {"selectattr", "rejectattr", "groupby", "attr"}
#: Filters whose `attribute=` keyword names an attribute read on each item.
_ATTR_KW = {"map", "sort", "sum", "min", "max", "unique", "groupby", "selectattr", "rejectattr"}
#: A dict's keys as data: these methods and filters iterate it.
_ITERATES = {"items", "values", "keys"}
_ITER_FILTERS = {"dictsort", "items"}


def _terminal(node):
    """The name a value is reached by: `x` for Name, `b` for `a.b`, `'b'` for `a['b']`."""
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Getattr):
        return node.attr
    if isinstance(node, nodes.Getitem) and isinstance(node.arg, nodes.Const) \
            and isinstance(node.arg.value, str):
        return node.arg.value
    # `(m.variables or {})` and `x | default({})` are still `variables` and `x`.
    if isinstance(node, nodes.Or):
        return _terminal(node.left)
    if isinstance(node, nodes.Filter) and node.name in ("default", "d") and node.node is not None:
        return _terminal(node.node)
    return None


def _const_str(node):
    return node.value if isinstance(node, nodes.Const) and isinstance(node.value, str) else None


class Reads:
    """What one template, with everything it extends, includes and imports, reads."""

    def __init__(self):
        self.names = set()       # every name and key it reads
        self.iterated = set()    # names whose dict value is iterated or indexed by data
        self.whole = set()       # names handed whole to `tojson`
        self.templates = set()   # the closure, by name
        self.dynamic = set()     # an include or import by a non-constant name, by template
        self.aliases = {}        # `{% set ops = r.operands %}`: ops -> operands

    def merge(self, other):
        for field in ("names", "iterated", "whole", "templates", "dynamic"):
            getattr(self, field).update(getattr(other, field))
        self.aliases.update(other.aliases)

    def resolve(self):
        """A name set or bound to another value stands for it: iterating or handing on the
        alias iterates or hands on what it names."""
        for _ in range(len(self.aliases) + 1):
            grew = False
            for alias, source in self.aliases.items():
                for field in (self.iterated, self.whole):
                    if alias in field and source not in field:
                        field.add(source)
                        grew = True
            if not grew:
                break


def _scan(ast, reads: Reads, follow: list):
    for node in ast.find_all(nodes.Node):
        if isinstance(node, nodes.Name) and node.ctx == "load":
            reads.names.add(node.name)
        elif isinstance(node, nodes.Getattr):
            reads.names.add(node.attr)
            if node.attr in _ITERATES:
                t = _terminal(node.node)
                if t:
                    reads.iterated.add(t)
        elif isinstance(node, nodes.Getitem):
            key = _const_str(node.arg)
            if key is not None:
                reads.names.add(key)
            elif not isinstance(node.arg, (nodes.Const, nodes.Slice)):
                t = _terminal(node.node)
                if t:
                    reads.iterated.add(t)
        elif isinstance(node, nodes.Call):
            if isinstance(node.node, nodes.Getattr) and node.node.attr == "get" and node.args:
                key = _const_str(node.args[0])
                if key is not None:
                    reads.names.add(key)
                else:                     # `words.get(o.outcome, ...)`: keys looked up by data
                    t = _terminal(node.node.node)
                    if t:
                        reads.iterated.add(t)
        elif isinstance(node, (nodes.Filter, nodes.Test)):
            if node.name in _ATTR_FIRST and node.args:
                key = _const_str(node.args[0])
                if key is not None:
                    reads.names.add(key)
            if node.name in _ATTR_KW:
                for kw in node.kwargs:
                    if kw.key == "attribute" and _const_str(kw.value) is not None:
                        # `attribute='a.b'` reads a, then b
                        reads.names.update(_const_str(kw.value).split("."))
            if isinstance(node, nodes.Filter) and node.node is not None:
                t = _terminal(node.node)
                if t and node.name in _ITER_FILTERS:
                    reads.iterated.add(t)
                if t and node.name == "tojson":
                    reads.whole.add(t)
        elif isinstance(node, nodes.Compare):
            key = _const_str(node.expr)
            if key is not None and any(op.op in ("in", "notin") for op in node.ops):
                reads.names.add(key)
        elif isinstance(node, nodes.For):
            t = _terminal(node.iter)
            if t:
                reads.iterated.add(t)
        elif isinstance(node, nodes.Assign) and isinstance(node.target, nodes.Name):
            t = _terminal(node.node)
            if t and t != node.target.name:
                reads.aliases[node.target.name] = t
        elif isinstance(node, nodes.With):
            for target, value in zip(node.targets, node.values):
                t = _terminal(value)
                if isinstance(target, nodes.Name) and t and t != target.name:
                    reads.aliases[target.name] = t
        elif isinstance(node, (nodes.Include, nodes.Import, nodes.FromImport, nodes.Extends)):
            name = _const_str(node.template)
            if name is not None:
                follow.append(name)
            elif isinstance(node.template, (nodes.List, nodes.Tuple)):
                follow.extend(n for n in (_const_str(i) for i in node.template.items) if n)
            else:
                reads.dynamic.add(True)


_READS: dict = {}


def template_reads(env, name: str) -> Reads:
    """*name*'s reads, with its whole closure, parsed by *env* (the app's own environment, so
    its extensions and syntax are the ones that draw the page)."""
    if name in _READS:
        return _READS[name]
    out, todo = Reads(), [name]
    while todo:
        t = todo.pop()
        if t in out.templates:
            continue
        out.templates.add(t)
        source, _filename, _up = env.loader.get_source(env, t)
        follow: list = []
        _scan(env.parse(source), out, follow)
        if out.dynamic and True in out.dynamic:
            out.dynamic.discard(True)
            out.dynamic.add(t)
        todo += follow
    out.resolve()
    _READS[name] = out
    return out


def _fields(obj):
    """A value's named parts, or None when it has none a template could read by name."""
    if isinstance(obj, dict):
        return obj.items()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return ((f.name, getattr(obj, f.name, None)) for f in dataclasses.fields(obj))
    if isinstance(obj, tuple) and hasattr(obj, "_fields"):
        return zip(obj._fields, obj)
    return None


def carried(context: dict, reads: Reads) -> tuple:
    """``(carried, undrawn)``: every key NAME the route's *context* carries, as far down as
    the template reads, and the ones it never reads.

    A key the template never names is undrawn, and nothing beneath it is examined (its whole
    value is undrawn: one entry, not one per key inside it). A dict reached by an iterated
    name gives no key names (its keys are data) and its values are walked; a value handed
    whole to `tojson` is not walked; a key that is not an identifier (an anchor, an address,
    a panel number) is data, since a template can name it only by a constant subscript."""
    out, undrawn, seen = set(), set(), set()

    def walk(obj, depth):
        if depth > 40 or id(obj) in seen:
            return
        parts = _fields(obj)
        if parts is None:
            if isinstance(obj, (list, tuple, set, frozenset)):
                seen.add(id(obj))
                for v in obj:
                    walk(v, depth + 1)
            return
        seen.add(id(obj))
        for k, v in parts:
            key(k, v, depth)

    def key(k, v, depth):
        if not isinstance(k, str) or not k.isidentifier():
            walk(v, depth + 1)
            return
        out.add(k)
        if k not in reads.names:
            undrawn.add(k)
            return
        if k in reads.whole:
            return
        if k in reads.iterated and isinstance(v, dict):
            for inner in v.values():
                walk(inner, depth + 1)
            return
        walk(v, depth + 1)

    for k, v in context.items():
        key(k, v, 0)
    return out, undrawn


# --- the loops: every `{% for %}` a v2 template holds, and which of them drew an item ---------

#: The environment attribute the marked loops call: ``environment.<this>("<template>#<n>")``.
LOOP_HOOK = "nmas_loop_drew"


def _expr(node) -> str:
    """An iterable as written, from its AST: `s.skipped`, `rows | selectattr()`, `x.items()`."""
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Getattr):
        return f"{_expr(node.node)}.{node.attr}"
    if isinstance(node, nodes.Getitem):
        key = node.arg.value if isinstance(node.arg, nodes.Const) else "…"
        return f"{_expr(node.node)}[{key!r}]" if isinstance(key, str) and key != "…" \
            else f"{_expr(node.node)}[{key}]"
    if isinstance(node, nodes.Filter):
        return f"{_expr(node.node)} | {node.name}" if node.node is not None else node.name
    if isinstance(node, nodes.Call):
        return f"{_expr(node.node)}()"
    if isinstance(node, (nodes.Or, nodes.And)):
        op = "or" if isinstance(node, nodes.Or) else "and"
        return f"({_expr(node.left)} {op} {_expr(node.right)})"
    if isinstance(node, nodes.CondExpr):
        return f"({_expr(node.expr1)} if … else {_expr(node.expr2) if node.expr2 else ''})"
    if isinstance(node, (nodes.Tuple, nodes.List)):
        return f"({len(node.items)} literal items)" if node.items else "()"
    if isinstance(node, nodes.Dict):
        return "{…}" if node.items else "{}"
    if isinstance(node, nodes.Const):
        return repr(node.value)
    if isinstance(node, nodes.Concat):
        return " ~ ".join(_expr(n) for n in node.nodes)
    if isinstance(node, nodes.BinExpr):
        return f"({_expr(node.left)} {node.operator} {_expr(node.right)})"
    return type(node).__name__


def _fors(ast) -> list:
    """Every `{% for %}` in a parsed template, in the parse's own walk order (the same source
    parsed by the same environment gives the same order, so a loop's position names it exactly,
    where a line would merge the several loops one line of a template often holds)."""
    return list(ast.find_all(nodes.For))


def template_loops(env, name: str) -> dict:
    """``{"<template>#<position>": key}`` for every `{% for %}` in *name*'s own source, the key
    its template and its iterable as written (`v2/x.html rows`), a repeat of the same iterable
    in the same template numbered in order (`#2`)."""
    source, _filename, _up = env.loader.get_source(env, name)
    out, seen = {}, {}
    for i, node in enumerate(_fors(env.parse(source))):
        expr = _expr(node.iter)
        seen[expr] = seen.get(expr, 0) + 1
        out[f"{name}#{i}"] = f"{name} {expr}" + (f" #{seen[expr]}" if seen[expr] > 1 else "")
    return out


def loops(env, templates) -> dict:
    """``{"<template>#<position>": key}`` for every `{% for %}` in *templates* under `v2/`."""
    out: dict = {}
    for t in sorted(templates):
        if t.startswith("v2/"):
            out.update(template_loops(env, t))
    return out


@contextlib.contextmanager
def recording_loops(env):
    """While inside, every v2 template *env* compiles marks each `{% for %}`'s body: its first
    statement calls ``environment.nmas_loop_drew("<template>#<position>")``, so the set this
    yields holds every loop whose body ran. The marks draw nothing. Templates compiled before
    are dropped from the cache on the way in, and the marked ones on the way out, so no other
    test renders a marked template."""
    drew: set = set()
    real = env._generate

    def generate(source, name, filename, defer_init=False):
        if name and name.startswith("v2/"):
            for i, node in enumerate(_fors(source)):
                mark = nodes.ExprStmt(nodes.Call(nodes.EnvironmentAttribute(LOOP_HOOK),
                                                 [nodes.Const(f"{name}#{i}")],
                                                 [], None, None))
                mark.set_lineno(node.lineno)
                mark.set_environment(env)
                node.body.insert(0, mark)
        return real(source, name, filename, defer_init)

    setattr(env, LOOP_HOOK, drew.add)
    env._generate = generate
    if env.cache is not None:
        env.cache.clear()
    try:
        yield drew
    finally:
        del env._generate
        delattr(env, LOOP_HOOK)
        if env.cache is not None:
            env.cache.clear()


def never_drew(population: dict, drew: set) -> set:
    """The keys of every loop in *population* whose body never ran (one key, one loop)."""
    return {key for at, key in population.items() if at not in drew}


# --- the measurement: real requests, every render recorded ---------------------------------

#: A fragment a page or another fragment asks for by `hx-get`, and a page a GET form opens.
_HX_GET = re.compile(r'\bhx-get="(/v2/[^"#]*)"')
_FORM = re.compile(r"<form\b([^>]*)>", re.I)
_ACTION = re.compile(r'\baction="(/v2/[^"#]*)"')
#: A bound on the fragments followed, about 2.5x the 927 measured (2026-10-15); reaching it
#: fails, naming the bound.
MAX_FRAGMENTS = 2300


class Route(NamedTuple):
    """One route's measurement: every request to it, unioned."""
    templates: frozenset     # every template a response rendered (the closure is read)
    carried: frozenset       # every key name examined
    undrawn: frozenset       # the keys no template in the same response reads
    requests: int


def given(name: str, value, injected: dict) -> bool:
    """Whether *name* is what every page receives without its route asking: a name Flask or a
    context processor injects, holding the value it injects. A route that passes its own value
    under such a name (`g=` for its payload; Flask lets the route's value win) has shadowed it,
    and that value is the route's payload, examined like any other (C2082: SDN, DHCP, Logs and
    discovery pass theirs as `g`, and the check skipped all of it by name)."""
    if name not in injected:
        return False
    other = injected[name]
    if value is other:
        return True
    try:
        return bool(value == other)
    except Exception:                       # noqa: BLE001 (a value that will not compare)
        return False


class _Recorder:
    """The renders of one request at a time, through Flask's `template_rendered` signal."""

    def __init__(self, app):
        self.app, self.buf, self.routes = app, [], {}

    def __call__(self, sender, template, context, **_extra):
        from flask import request

        if not template.name:            # render_template_string: no template to parse
            return
        injected: dict = {}
        self.app.update_template_context(injected)
        rule = request.url_rule.rule if request.url_rule else request.path
        self.buf.append((f"{request.method} {rule}", template.name,
                         {k: v for k, v in context.items() if not given(k, v, injected)}))

    def request(self, call):
        """Run *call* (one request) and fold its renders into its route: the response's
        templates read together, since a route that sends several parts in one answer
        (an out-of-band part beside its card) draws its context across all of them."""
        self.buf.clear()
        out = call()
        env = self.app.jinja_env
        merged = Reads()
        for _route, name, _ctx in self.buf:
            merged.merge(template_reads(env, name))
        for route, name, ctx in self.buf:
            seen, undrawn = carried(ctx, merged)
            got = self.routes.get(route) or Route(frozenset(), frozenset(), frozenset(), 0)
            self.routes[route] = Route(got.templates | {name}, got.carried | seen,
                                       got.undrawn | undrawn, got.requests + 1)
        self.buf.clear()
        return out


class RecordingClient:
    """A test client whose every GET and POST is folded into the recorder."""

    def __init__(self, client, recorder):
        self.client, self.recorder = client, recorder

    def get(self, *a, **k):
        return self.recorder.request(lambda: self.client.get(*a, **k))

    def post(self, *a, **k):
        return self.recorder.request(lambda: self.client.post(*a, **k))


def follow(html: str) -> list:
    """The v2 GETs a body asks for: its `hx-get` fragments and its GET forms' actions."""
    out = [unescape(u) for u in _HX_GET.findall(html)]
    for attrs in _FORM.findall(html):
        if re.search(r'\bmethod="post"|\bhx-post=', attrs, re.I):
            continue
        out += [unescape(u) for u in _ACTION.findall(attrs)]
    return out


def walk_fragments(client, pages: dict) -> int:
    """Every fragment the pages ask for, and every fragment those ask for, once each."""
    todo, seen = [u for html in pages.values() for u in follow(html)], set(pages)
    count = 0
    while todo:
        url = todo.pop(0)
        if url in seen:
            continue
        seen.add(url)
        count += 1
        assert count <= MAX_FRAGMENTS, (
            f"{MAX_FRAGMENTS} fragments followed, the bound (2.5x the 927 measured "
            "2026-10-15): a fragment that links without end, or a bound to re-measure")
        r = client.get(url, headers={"HX-Request": "true", "Accept": "text/html"})
        if r.status_code == 200 and r.mimetype == "text/html":
            todo += [u for u in follow(r.get_data(as_text=True)) if u not in seen]
    return count


_CACHE: dict = {}


def _store_aside() -> str:
    """The test store emptied for the measurement (its key files kept), its contents copied
    aside: the walk reads a store as a fresh install has it, never what an earlier test in this
    process left there. Measured 2026-10-15: in the full suite a heartbeat re-measure's record
    and a break-glass record, left by earlier tests, added three keys the module run alone never
    carried, so the verdict depended on test order."""
    import shutil
    import tempfile

    from modules import config

    store = config.DATA_DIR
    aside = tempfile.mkdtemp(prefix="nmas-v2-context-store-")
    shutil.copytree(store, aside, dirs_exist_ok=True)
    for name in os.listdir(store):
        if name.endswith(".key"):
            continue
        path = os.path.join(store, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    return aside


def _store_back(aside: str) -> None:
    """The store as it was before the measurement, exactly."""
    import shutil

    from modules import config

    store = config.DATA_DIR
    for name in os.listdir(store):
        path = os.path.join(store, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    shutil.copytree(aside, store, dirs_exist_ok=True)
    shutil.rmtree(aside, ignore_errors=True)


def measure() -> dict:
    """``{"routes": {route: Route}, "pages": n, "fragments": n, "posts": n}`` for v2, built once
    per test process on test_device_v2's lab (tests/interface_pages.py's walk, from the same
    starts, with the same verified person), both undone before it returns."""
    if "m" in _CACHE:
        return _CACHE["m"]
    import contextlib
    import pathlib
    import tempfile

    import pytest
    from flask import template_rendered

    import app as A
    from tests import interface_pages as IP
    from tests.test_device_v2 import lab_setup

    recorder = _Recorder(A.app)
    mp = pytest.MonkeyPatch()
    aside = _store_aside()
    try:
        IP.as_a_verified_person(mp)
        with tempfile.TemporaryDirectory(prefix="nmas-v2-context-") as tmp:
            with contextlib.contextmanager(lab_setup)(pathlib.Path(tmp), mp) as lab:
                IP.seed(lab, mp, tmp)
                client = RecordingClient(lab["client"], recorder)
                template_rendered.connect(recorder, A.app)
                try:
                    with recording_loops(A.app.jinja_env) as drew:
                        pages = IP._walk(client)
                        fragments = walk_fragments(client, pages)
                        upstream: dict = {}
                        for provide in PROVIDERS:
                            for route, got in (provide(client, lab, mp) or {}).items():
                                upstream.setdefault(route, []).extend(got)
                        drew = set(drew)
                finally:
                    template_rendered.disconnect(recorder, A.app)
    finally:
        mp.undo()
        _store_back(aside)
    _CACHE["m"] = {"routes": recorder.routes, "pages": len(pages), "fragments": fragments,
                   "providers": len(PROVIDERS), "upstream": upstream, "drew": drew}
    return _CACHE["m"]


def _golden_sha(lab) -> str:
    import subprocess

    return subprocess.run(["git", "-C", lab["repo"], "log", "-1", "--format=%H", "--",
                           "golden/r3.cfg"], capture_output=True, text=True,
                          check=True).stdout.strip()


def _reveal(client, lab, _mp):
    """A golden version revealed from the History tab's timeline (a verified person)."""
    r = client.post("/v2/device/r3/golden/reveal", data={"ref": _golden_sha(lab)})
    assert r.status_code == 200, r.status_code


def _intent_check(client, lab, _mp):
    """The intent editor's check, on r3's committed intent with one value changed."""
    text = open(os.path.join(lab["repo"], "host_vars", "r3.yml"), encoding="utf-8").read()
    edited = text.replace("hostname: r3", "hostname: r3-edited", 1)
    assert edited != text, "r3's committed intent names no hostname to edit"
    for yaml in (text, edited):
        r = client.post("/v2/device/r3/intent/check", data={"yaml": yaml})
        assert r.status_code == 200, r.status_code


def _intent_deploy_offer(client, _lab, _mp):
    """The commit result's deploy offer (C2288) on r3, whose references the walk's credential
    store holds no value for: each named with Set value…, Plan a deploy… greyed."""
    r = client.get("/v2/device/r3/intent/deploy-offer")
    assert r.status_code == 200, r.status_code
    assert "Before it can be deployed" in r.get_data(as_text=True), "r3 has every value"


def _reload_effects(client, _lab, _mp):
    """The Reload card's result with board PS's part (C2274): r3's window two hours ago,
    predicting r4; the holding sources stubbed to hold one signal for it, raise one row about
    r9 begun in the window (unexpected) and one about r3 past its time (overdue). The job and
    the window are planted for this provider alone, then undone."""
    import time as _time

    import pytest

    from modules import planned_state as PS
    from modules import restarts as R
    from modules.nsot import capture_job

    mp = pytest.MonkeyPatch()
    try:
        now = _time.time()
        w = {"devices": ["r3"], "list": "Lab", "from": R._iso(now - 7200),
             "until": R._iso(now - 6600), "by": "op@example.com", "why": "planned reload",
             "via": "reload", "recorded_at": R._iso(now - 7200),
             "expected": {"unreachable": ["r4"]}}
        mp.setattr(R, "planned_rows", lambda: [w])
        mp.setattr(R, "ends", lambda: {})
        held = [{"source": "drift", "window": R.window_id(w), "devices": ["r3"],
                 "what": "Drift: r3 not read; read again by the next run", "how": "restarting",
                 "back_by": R._iso(now - 6600 + R.SETTLE_SECONDS)}]
        rows = [{"what": "r9 is not answering", "devices": ["r9"], "since": now - 7000},
                {"what": "r3 is not answering", "devices": ["r3"], "since": now - 7100}]
        src = lambda: {"source": "reachability", "label": "Reachability",  # noqa: E731
                       "state": "read", "rows": rows, "held": held}
        real = PS.expected_effects
        mp.setattr(PS, "expected_effects",
                   lambda window, list_name: real(window, list_name, sources=[src]))
        job = capture_job.start("Lab", "Reload r3", "op@example.com", lambda _j: {
            "outcome": "reloaded", "ok": True, "steps": [], "by": "op@example.com",
            "reason": "planned", "window": {"from": w["from"], "until": w["until"]}},
            kind="reload", device="r3", card="reload")
        assert capture_job.wait(job, 10)
        r = client.get(f"/v2/device/r3/reload/job/{job}?list=Lab")
        assert r.status_code == 200, r.status_code
        html = r.get_data(as_text=True)
        assert "Unexpected during this reload, raised" in html and "Overdue, past" in html, html
    finally:
        mp.undo()


def _fleet_plan(client, _lab, _mp):
    """A layer change's plan card (board FC4, C2283) with every part drawn: a group, a device
    carrying pending lines, an unchanged device and a refused one. The plan is `plan_layer`'s
    shape, planted for this provider alone, then undone; the job is the real one."""
    import pytest

    from modules.nsot import capture_job, fleet_change

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(fleet_change, "plan_layer", lambda list_name, key, steps: {
            "ok": True, "error": "",
            "layer": {"key": key, "rank": "tag", "slug": "blind-lab", "label": "tag blind-lab",
                      "file": "layers/tag-blind-lab.yml", "before": {},
                      "after": {"ntp_servers": ["192.0.2.123"]}},
            "base": "5a1e2f0" + "0" * 33,
            "groups": [{"lines": ["ntp server 192.0.2.123"], "left": ["ntp server 192.0.2.9"],
                        "devices": ["r3"]}],
            "unchanged": [{"device": "r4", "by": "this device"}],
            "refused": [{"device": "r9", "reasons": ["no committed golden"]}],
            "devices": [{"device": "r3", "change": ["ntp server 192.0.2.123"], "pending": 2,
                         "command_hash": "h"}],
            "headline": "1 device, 1 group", "hash": "x",
            "steps": [{"path": ["ntp_servers"], "before": {"__absent__": True},
                       "after": ["192.0.2.123"]}]})
        r = client.post("/v2/intent/change/plan", data={
            "list": "Lab", "layer": "tag-blind-lab", "path": "ntp_servers",
            "before": "(absent)", "after": "[192.0.2.123]"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html[:300]
        job = html.split("/v2/intent/change/job/", 1)[1].split("?", 1)[0]
        assert capture_job.wait(job, 10)
        r = client.get(f"/v2/intent/change/job/{job}?list=Lab&layer=tag-blind-lab")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "data-fc-refused" in html and "data-fc-pending" in html, \
            html[:400]
    finally:
        mp.undo()


def _fleet_selection(client, _lab, _mp):
    """Devices' Change across the N ticked… (board FC1, phase 2 (f2)): its form for the ticked
    r3 and r4 with a layer both take, and its plan, each ticked device's own document, its steps
    and the approval carrying the selection. The layers' view and the plan are planted for this
    provider alone, then undone; the job is the real one."""
    import pytest

    from modules import intent_layers_page
    from modules.nsot import capture_job, fleet_change

    real = intent_layers_page.view
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(intent_layers_page, "view", lambda ref, chosen="": dict(
            real(ref, chosen), layers=[{"key": "tag-blind-lab", "rank": "tag",
                                        "slug": "blind-lab", "label": "tag blind-lab",
                                        "file": "layers/tag-blind-lab.yml",
                                        "devices": ["r3", "r4", "r9"], "count": 3}]))
        html = client.get("/v2/intent/change?list=Lab&device=r3&device=r4").get_data(as_text=True)
        assert "data-fc-where" in html and 'value="layer:tag-blind-lab"' in html, html[:400]
        mp.setattr(fleet_change, "plan_selection", lambda list_name, devices, steps: {
            "ok": True, "error": "", "layer": {},
            "target": {"kind": "devices", "devices": ["r3", "r4"],
                       "label": "2 devices' own intent"},
            "texts": {"r3": "hostname: r3\n"}, "base": "5a1e2f0" + "0" * 33,
            "groups": [{"lines": ["ntp server 192.0.2.123"], "left": [], "devices": ["r3"]}],
            "unchanged": [], "refused": [{"device": "r4", "reasons": ["its current intent is "
                                                                       "not what the change expects"]}],
            "devices": [{"device": "r3", "change": ["ntp server 192.0.2.123"], "pending": 0,
                         "command_hash": "h"}],
            "headline": "1 device, 1 group", "hash": "x",
            "steps": [{"path": ["ntp_servers"], "before": [], "after": ["192.0.2.123"]}]})
        r = client.post("/v2/intent/change/plan", data={
            "list": "Lab", "target": "devices", "device": ["r3", "r4"], "path": "ntp_servers",
            "before": "[]", "after": "[192.0.2.123]"})
        html = r.get_data(as_text=True)
        job = html.split("/v2/intent/change/job/", 1)[1].split("?", 1)[0]
        assert capture_job.wait(job, 10)
        html = client.get(f"/v2/intent/change/job/{job}?list=Lab").get_data(as_text=True)
        assert "data-fc-steps" in html and 'name="target" value="devices"' in html, html[:400]
    finally:
        mp.undo()


def _fleet_run(client, _lab, _mp):
    """A layer change's run card (board FC5, C2283): paused after its canary (the devices left,
    Go on), and stopped at a failed device (what landed, the failure, the unattempted). THE
    apply and the plan's programs are planted for this provider alone, then undone; the jobs
    are the real ones. Nothing reaches a device."""
    import pytest

    import routes.deploy as rd
    from modules.nsot import capture_job, fleet_change
    from modules.nsot.deploy import DEPLOYED

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(rd, "plan_devices", lambda ln, batch: [
            {"device": d, "capture_hash": f"c-{d}", "command_hash": f"h-{d}"} for d in batch])
        mp.setattr(rd, "apply_batch", lambda ln, conf, hashes, **kw: {"results": [
            {"device": d, "outcome": "failed" if d == "r4" else DEPLOYED,
             "verify": {"ok": d != "r4", "summary": "a sent line was not read back"}}
            for d in conf]})
        plan = {"layer": {"label": "tag blind-lab"},
                "devices": [{"device": d, "command_hash": f"h-{d}"} for d in ("r3", "r4", "r9")]}
        for after in ("pause", "go"):
            job = fleet_change.run_start("Lab", plan, "5a1e2f0" + "0" * 33,
                                         [["r3"], ["r4"], ["r9"]], after_canary=after,
                                         actor="op@example.com", actor_kind="person")
            assert capture_job.wait(job, 10)
            r = client.get(f"/v2/intent/change/run/{job}?list=Lab&layer=tag-blind-lab")
            html = r.get_data(as_text=True)
            assert r.status_code == 200 and ("data-fc-paused" if after == "pause"
                                             else "data-fc-stopped") in html, html[:400]
    finally:
        mp.undo()


def _deploy_layer_lines(client, _lab, _mp):
    """r3's Deploy… card with an inherited line a committed intent layer supplies (board FC,
    22.1 (6), C2283): the preview the card is built from is given an attribution note carrying
    a layer's group, in `preview_confirm`'s shape, planted for this provider alone, then
    undone."""
    import pytest

    from modules import device_actions

    mp = pytest.MonkeyPatch()
    real = device_actions.deploy_card

    def card(ref, host, entry, preview, *a, **kw):
        for t in preview.get("targets") or []:
            program = t.setdefault("program", {})
            # The card draws its notes beside the lines it sends; r3 sends none here.
            program["lines"] = list(program.get("lines") or []) or ["ntp server 192.0.2.123"]
            program["notes"] = list(program.get("notes") or []) + [{
                "title": "Where the added lines come from", "intent_commit": "",
                "intent_subject": "", "note": "", "from_profile": [],
                "from_layers": [{"label": "tag blind-lab", "sha": "5a1e2f0" + "0" * 33,
                                 "subject": "layer tag-blind-lab.yml",
                                 "lines": ["ntp server 192.0.2.123"]}],
                "from_this_edit": [], "pre_existing": []}]
        return real(ref, host, entry, preview, *a, **kw)
    try:
        mp.setattr(device_actions, "deploy_card", card)
        r = client.get("/v2/device/r3/deploy")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and 'data-attribution-group="layer"' in html, html[:400]
    finally:
        mp.undo()


def _intent_layers_from(client, _lab, _mp):
    """r3's Intent tab with two committed layers it takes (board FC3, C2283): the network layer
    and a tag layer its row names, read by the real merge and provenance; the layer files, the
    row's tags and the layer commit are planted for this provider alone, then undone."""
    import pytest

    from modules.nsot import intent_layers as L
    from modules.nsot import profile

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(L, "read_layers", lambda repo, ref="HEAD": [
            ("network", "", "network", {"domain_name": "corp.example"}),
            ("tag", "blind-lab", "tag blind-lab",
             {"users": [{"name": "lab", "privilege": 15, "secret_ref": "user_lab_secret"}]})])
        mp.setattr(L, "last_change", lambda repo, rel, ref: {"sha": "5a1e2f0" + "0" * 33,
                                                             "subject": f"layer {rel}"})
        mp.setattr(profile, "_row_of", lambda list_name, host: {"hostname": host,
                                                                 "_tags": ["blind-lab"]})
        r = client.get("/v2/device/r3/intent", headers={"HX-Request": "true"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and '<tr data-from="tag blind-lab"><td>users › lab</td>' \
            in html, html[:400]
    finally:
        mp.undo()


def _intent_layers_page(client, _lab, _mp):
    """Source of Truth › Intent with three committed layers (board FC2, C2283): the network
    layer's domain, which r3's own overrides; tag blind-lab's account and its secret reference;
    and tag other disagreeing with blind-lab on the banner for r3, which carries both. The layer
    files, the rows' tags and the layer commit are planted for this provider alone, then
    undone."""
    import pytest

    from modules.nsot import intent_layers as L

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(L, "read_layers", lambda repo, ref="HEAD": [
            ("network", "", "network", {"domain_name": "corp.example"}),
            ("tag", "blind-lab", "tag blind-lab",
             {"banner_motd": "a", "users": [{"name": "lab", "privilege": 15,
                                             "secret_ref": "user_lab_secret"}]}),
            ("tag", "other", "tag other", {"banner_motd": "b"})])
        mp.setattr(L, "last_change", lambda repo, rel, ref: {"sha": "5a1e2f0" + "0" * 33,
                                                            "subject": f"layer {rel}"})
        mp.setattr("modules.nsot.restore._devices_of", lambda ln: [
            {"hostname": "r3", "_tags": ["blind-lab", "other"]}, {"hostname": "r4"}])
        for layer, drawn in (("network", "<td>domain_name</td>"),
                             ("tag-blind-lab", "<code>user_lab_secret</code>")):
            r = client.get(f"/v2/intent?list=Lab&layer={layer}")
            html = r.get_data(as_text=True)
            assert r.status_code == 200 and drawn in html and "data-layers-conflict" in html, \
                html[:400]
    finally:
        mp.undo()


def _attention_expected(client, _lab, _mp):
    """Needs attention while r3's Reload runs (board NA-R's decision 4): a source holding two
    of its effects, so the summary links them to the Reload's card. The window and the source
    are planted for this provider alone, then undone."""
    import time as _time

    import pytest

    from modules import attention
    from modules import restarts as R

    mp = pytest.MonkeyPatch()
    try:
        now = _time.time()
        w = {"devices": ["r3"], "list": "Lab", "from": R._iso(now - 120),
             "until": R._iso(now + 600), "by": "op@example.com", "why": "planned reload",
             "via": "reload", "recorded_at": R._iso(now - 120)}
        mp.setattr(R, "planned_rows", lambda: [w])
        held = [{"source": "drift", "window": R.window_id(w), "devices": ["r3"],
                 "what": f"effect {i}", "how": "restarting", "back_by": ""} for i in (1, 2)]
        mp.setattr(attention, "SOURCES", [lambda: attention.source_result(
            "drift", "Drift", read_at=now, took_ms=1, checked="read", held=held)])
        r = client.get("/v2/attention")
        assert r.status_code == 200, r.status_code
        assert "2 expected effects of r3&#39;s Reload are on its card" in \
            r.get_data(as_text=True), "the summary's link is not drawn"
    finally:
        mp.undo()


def _attention_explain(client, _lab, _mp):
    """An alert-backed Needs attention item's Explain (board NA-R part 2), as its item loads it
    when opened: a pack id no pack is built for says so and links Monitoring › Alerts."""
    r = client.get("/v2/attention/explain/ep-" + "0" * 20)
    assert r.status_code == 200, r.status_code
    assert "No evidence pack is built for this alert yet" in r.get_data(as_text=True)


def _attention_heal_analysis(client, _lab, _mp):
    """A can't-fix row's AI analysis (board H, H8), as its item loads it when opened: an
    incident with no analysis kept yet draws its state, pending; one with a checked answer kept
    (the store's read planted for this provider alone, then undone) draws its label, its
    hypothesis and its next step. Neither calls anything."""
    import pytest

    from modules.ai import heal_analysis as HA

    r = client.get("/v2/attention/heal-analysis/Lab/hi-000000000000")
    assert r.status_code == 200, r.status_code
    assert "AI analysis: pending" in r.get_data(as_text=True)
    kept = {"row": "analysis", "incident": "hi-000000000001", "state": "answered",
            "words": HA.words_of("answered"), "label": HA.beta(), "call_id": "ai-0",
            "cost_usd": 0.03, "at": "2026-11-04T02:00:00Z",
            "answer": {"rationale": "The ACL drops OSPF.", "needs_human": True,
                       "mercury_cites": [],
                       "hypotheses": [{"claim": "An inbound ACL drops OSPF on Gi2.",
                                       "cites": ["tried:7"], "next": "show ip access-lists"}]}}
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(HA, "read", lambda network: {"state": "ok", "rows": [kept], "error": ""})
        r = client.get("/v2/attention/heal-analysis/Lab/hi-000000000001")
        text = r.get_data(as_text=True)
        assert "Hypothesis:" in text and "show ip access-lists" in text, text[:400]
    finally:
        mp.undo()


def _attention_withheld(client, _lab, _mp):
    """Needs attention with a withheld-lines row (C2295): its Acknowledge… form draws the
    disposition choice. The record of AI calls planted for this provider alone, then undone."""
    import time as _time

    import pytest

    from modules import attention

    mp = pytest.MonkeyPatch()
    try:
        at = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(_time.time() - 60))
        call = {"id": "call-1", "feature": "explain", "at": at, "actor": "op@example.com",
                "subject": {"kind": "alert", "id": "ep-1", "devices": ["r2"]},
                "withheld": [{"where": "pack[9].pieces[0].text",
                              "patterns": ["ignore_instructions"]}]}
        real = attention.ai_withheld_source
        mp.setattr(attention, "ai_withheld_source", lambda rows=None, now=None: real([call]))
        mp.setattr(attention, "SOURCES", [attention.ai_withheld_source])
        r = client.get("/v2/attention")
        assert r.status_code == 200, r.status_code
        assert 'name="disposition"' in r.get_data(as_text=True), "no disposition drawn"
    finally:
        mp.undo()


def _attention_quiet_period(client, _lab, _mp):
    """Needs attention with an adjacency-log row, a band row (C2316): its Acknowledge… form
    draws the planned quiet period's hours. The reader's value planted for this provider
    alone, then undone."""
    import time as _time

    import pytest

    from modules import attention

    mp = pytest.MonkeyPatch()
    try:
        now = _time.time()
        at = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(now - 300))
        k = "Lab|r2|OSPF|192.0.2.3"
        value = {"configured": True, "lines": 1, "devices": 1, "window_days": 7,
                 "adjacencies": {k: {"list": "Lab", "device": "r2", "protocol": "OSPF",
                                     "neighbor": "192.0.2.3", "interface": "GigabitEthernet2",
                                     "drops": [{"at": at, "epoch": now - 300,
                                                "reason": "Dead timer expired"}],
                                     "by_day": {at[:10]: 1}, "band": 1}}}
        cached = {"state": "ok", "doc": {"last_good": {"value": value, "value_at": at},
                                         "stale_after_seconds": 300}}
        real = attention.adjacency_log_source
        mp.setattr(attention, "SOURCES", [lambda: real(cached=cached, planned=[],
                                                       receipts=lambda ln, dev: [])])
        r = client.get("/v2/attention")
        assert r.status_code == 200, r.status_code
        assert 'name="hours"' in r.get_data(as_text=True), "no quiet period drawn"
    finally:
        mp.undo()


def _intent_words(client, lab, _mp):
    """Change it in words on r3's Intent tab (feature 7, 15.16): hosted AI allowed and the
    adapter answering as planted, a draft that sets the description of r3's first committed
    interface, previewed by the intent editor (its changes listed). Its patches and stores
    are undone before the next provider (the row's not-ready states are
    tests/test_ai_intent_change.py's `check_screen`)."""
    import json
    import shutil
    import tempfile

    import pytest
    import yaml

    from modules import settings_schema
    from modules.ai import anthropic_adapter, calls, gateway

    from modules.nsot import intent_edit
    from modules.nsot.repo import save_host_vars
    # r2's real capture holds a partial syslog block (`heartbeat: 0`), which the editor's check
    # refuses, so a draft on it is refused before the patch. The heartbeat typed in, as
    # tests/test_intent_editor_v2.py's person does, and committed: a document the check passes.
    text = intent_edit.open_doc("Lab", "r3")["yaml"]
    assert "heartbeat: 0" in text, "the walk's r3 holds no syslog heartbeat to set"
    with open(os.path.join(lab["repo"], "host_vars", "r3.yml"), "w", encoding="utf-8") as fh:
        fh.write(text.replace("heartbeat: 0", "heartbeat: 300", 1))
    assert save_host_vars("Lab", ["r3"], actor="t", source="extraction")["ok"]
    doc = yaml.safe_load(intent_edit.open_doc("Lab", "r3")["yaml"])
    iface = next(i["name"] for i in doc.get("interfaces") or [] if i.get("name"))
    answer = {"outcome": "answer", "question": "", "why_not": "", "patches": [
        {"hostname": "r3", "operations": [
            {"op": "set_description", "interface": iface, "description": "drafted in words",
             "vlan": 0, "vlan_name": "", "process": 0, "prefix": "", "area": ""}]}]}
    mp = pytest.MonkeyPatch()
    folder = tempfile.mkdtemp(prefix="nmas-v2-context-words-")
    try:
        allowed = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                                 "reason": "the walk's planted answer"}, "ai_cap_usd_per_day": 1.5}
        real_get = settings_schema.get_setting
        mp.setattr(settings_schema, "get_setting",
                   lambda k, d=None: allowed[k] if k in allowed else real_get(k, d))
        mp.setattr(gateway, "_api_key", lambda: "sk-planted-walk-key-0123456789")
        mp.setattr("modules.ai.controls._key_set", lambda: True)
        mp.setattr(calls, "_path", lambda: os.path.join(folder, "ai_calls.jsonl"))
        mp.setattr(anthropic_adapter, "send", lambda body, key: anthropic_adapter.Reply(
            status=200, body={"content": [{"type": "text", "text": json.dumps(answer)}],
                              "stop_reason": "end_turn",
                              "usage": {"input_tokens": 1500, "output_tokens": 120}},
            attempts=1, latency_s=0.4))
        # Part 1: the interface named in its short form, so the draft lists how it was read;
        # then a reference two uplinks match (planted neighbours), which Mercury asks about;
        # then a name r3 does not hold, said with its interfaces.
        from modules.ai import intent_names
        from modules.nsot import ifnames
        r = client.post("/v2/device/r3/intent/words",
                        data={"words": f"describe {ifnames.abbreviate(iface)} as drafted in "
                                       "words"},
                        headers={"HX-Request": "true", "Accept": "text/html"})
        html = r.get_data(as_text=True)
        import re
        assert r.status_code == 200 and "Drafted from your words" in html \
            and "How your words were read" in html, \
            re.sub(r"<svg.*?</svg>", "", html.split("</form>", 1)[-1], flags=re.S)[:600]
        ports = [i["name"] for i in doc.get("interfaces") or []
                 if str(i.get("name", "")).startswith("GigabitEthernet")][:2]
        mp.setattr(intent_names, "neighbours_of", lambda network, device: {"ports": {
            p: [{"name": f"edge{n}", "role": "router", "by": "observed (LLDP)"}]
            for n, p in enumerate(ports, 1)}, "said": []})
        for words, said in (("shut the uplink", "which one?"),
                            ("shut Gi9/9", "has no interface Gi9/9")):
            r = client.post("/v2/device/r3/intent/words", data={"words": words},
                            headers={"HX-Request": "true", "Accept": "text/html"})
            assert r.status_code == 200 and said in r.get_data(as_text=True), words
        # C1907: Mercury's own question with its controls (board F7-Q, Q2), no call.
        r = client.post("/v2/device/r3/intent/words",
                        data={"words": "add VLAN 40 or 41, whichever is free"},
                        headers={"HX-Request": "true", "Accept": "text/html"})
        html = r.get_data(as_text=True)
        assert 'name="ask" value="alternatives"' in html and ">VLAN 41<" in html, html[-800:]
        # C1908: both ends of a link as one draft and one commit (board F7-Q, Q1): r4 committed
        # as a copy of r3 (its intent and golden renamed), their first port linked.
        import re as _re
        r4_text = intent_edit.open_doc("Lab", "r3")["yaml"].replace("hostname: r3",
                                                                    "hostname: r4", 1)
        with open(os.path.join(lab["repo"], "host_vars", "r4.yml"), "w", encoding="utf-8") as fh:
            fh.write(r4_text)
        assert save_host_vars("Lab", ["r4"], actor="t", source="extraction")["ok"]
        link = ports[0]
        mp.setattr(intent_names, "neighbours_of", lambda network, device, far=False: {
            "ports": {link: [{"name": "r4" if device == "r3" else "r3", "role": "router",
                              "by": "observed (LLDP)", "port": link}]}, "said": []})
        mp.setattr(intent_names, "_devices", lambda network: {"r3": "router", "r4": "router"})
        answer = {"outcome": "answer", "question": "", "why_not": "", "patches": [
            {"hostname": h, "operations": [
                {"op": "set_description", "interface": link, "description": "both ends",
                 "vlan": 0, "vlan_name": "", "process": 0, "prefix": "", "area": ""}]}
            for h in ("r3", "r4")]}
        r = client.post("/v2/device/r3/intent/words",
                        data={"words": f"describe both ends of {ifnames.abbreviate(link)} as "
                                       "both ends"},
                        headers={"HX-Request": "true", "Accept": "text/html"})
        html = r.get_data(as_text=True)
        assert "One draft, both ends" in html, _re.sub(r"<svg.*?</svg>", "", html,
                                                       flags=_re.S)[-1200:]
        import html as _h
        form = html.split('class="iw-commit"', 1)[1].split("</form>", 1)[0]
        fields = {m.group(1): _h.unescape(m.group(2)) for m in _re.finditer(
            r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', form)}
        r = client.post("/v2/device/r3/intent/words/commit",
                        data=dict(fields, summary="both ends of a link"),
                        headers={"HX-Request": "true", "Accept": "text/html"})
        assert "Committed to r3 and r4" in r.get_data(as_text=True), r.get_data(as_text=True)[-800:]
        # C1933: r4's end of the link put in OSPFv3 area 7 in committed intent, where r3's is
        # in none; a draft describing both ends again leaves it as it is, so it is drawn
        # beside the draft, which is offered.
        doc4 = yaml.safe_load(intent_edit.open_doc("Lab", "r4")["yaml"])
        end4 = next(i for i in doc4["interfaces"] if i.get("name") == link)
        end4["ospfv3"] = ["1 area 7"]
        from modules.nsot import hostvars
        with open(os.path.join(lab["repo"], "host_vars", "r4.yml"), "w", encoding="utf-8") as fh:
            fh.write(hostvars.canonical(yaml.safe_dump(doc4), "r4"))
        assert save_host_vars("Lab", ["r4"], actor="t", source="extraction")["ok"]
        for p in answer["patches"]:
            p["operations"][0]["description"] = "both ends again"
        r = client.post("/v2/device/r3/intent/words",
                        data={"words": f"describe both ends of {ifnames.abbreviate(link)} as "
                                       "both ends again"},
                        headers={"HX-Request": "true", "Accept": "text/html"})
        html = _h.unescape(r.get_data(as_text=True))
        assert "The ends already differ:</strong>" in html and "Commit both devices' intent" \
            in html, _re.sub(r"<svg.*?</svg>", "", html.split("</form>", 1)[-1],
                             flags=_re.S)[:1500]
    finally:
        mp.undo()
        shutil.rmtree(folder, ignore_errors=True)


def _intent_normalise(client, lab, _mp):
    """Normalise the formatting… (C1693, board H-N) on r3's committed intent, hand-formatted as
    an editor writes YAML (its `interfaces` list indented under its key, a comment above it):
    the Intent tab's offer, the editor opened on Mercury's formatting, the check's proof, and
    then the same with the credential store answering the new document's true render with
    another value (planted), so the proof stops naming the masked line, and the commit's
    refusal draws it. r3's intent is put back after."""
    import inspect

    import pytest

    from modules.nsot import hostvars, intent_edit
    from modules.nsot.repo import save_host_vars

    path = os.path.join(lab["repo"], "host_vars", "r3.yml")
    before = open(path, encoding="utf-8").read()
    hand, inside = [], False
    for line in before.splitlines():
        if line and not line.startswith((" ", "-")):
            inside = line == "interfaces:"
            hand += ["# typed in an editor that indents lists"] if inside else []
            hand.append(line)
        else:
            hand.append("  " + line if inside and line else line)
    hand_text = "\n".join(hand) + "\n"
    assert hostvars.from_yaml(hand_text) == hostvars.from_yaml(before) and hand_text != before
    mp = pytest.MonkeyPatch()
    flips = {"n": 0}

    def hydrate(hv, h, ln=""):
        value = "walk-secret-value"
        if inspect.stack()[1].function == "_masked_compared" and flips.get("on"):
            flips["n"] += 1
            value += "-moved" if flips["n"] % 2 == 0 else ""
        return {**hv, "secrets": {ref: value for ref in hv.get("secret_refs") or []}}
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(hand_text)
        assert save_host_vars("Lab", ["r3"], actor="t", source="extraction")["ok"]
        mp.setattr("modules.nsot.hostvars.hydrate_secrets", hydrate)
        mp.setattr("modules.redact.known_secret_values", lambda: {})
        r = client.get("/v2/device/r3/intent", headers={"HX-Request": "true"})
        assert r.status_code == 200 and "Normalise the formatting" in r.get_data(as_text=True)
        r = client.get("/v2/device/r3/intent/normalise", headers={"HX-Request": "true"})
        assert r.status_code == 200 and "Mercury's formatting loaded" in r.get_data(as_text=True)
        opened = intent_edit.open_doc("Lab", "r3")
        norm = hostvars.canonical(opened["yaml"])
        for planted in (False, True):
            flips["on"] = planted
            r = client.post("/v2/device/r3/intent/check", data={"yaml": norm})
            html = r.get_data(as_text=True)
            assert r.status_code == 200 and "ie-proof" in html, html[:400]
            assert ("A masked line differs by keyed hash" in html) == planted
        r = client.post("/v2/device/r3/intent/commit",
                        data={"yaml": norm, "base": opened["base"], "summary": "normalise"})
        assert r.status_code == 409 and "this is not formatting only" in r.get_data(as_text=True)
    finally:
        mp.undo()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(before)
        assert save_host_vars("Lab", ["r3"], actor="t", source="extraction")["ok"]


def _persist_read(client, _lab, mp):
    """Persist's preview read (C886), asked by a POST on load and drawn by its job's GET: r3
    answering with r1's real running and startup (tests/test_persist_effect.py), one logging
    line changed, so the lines startup gains and loses and the certificates kept as files are
    all carried."""
    from modules.nsot import capture_job
    from tests import test_persist_effect as PE

    pair = {k: PE._as(PE._read("r1", c), "r1", "r3")
            for k, c in (("running", "show running-config"),
                         ("startup", "show startup-config"))}
    running = pair["running"].replace("\nlogging trap notifications\n",
                                      "\nlogging trap informational\n")
    mp.setattr("modules.connection.with_temp_connection",
               lambda dev, fn: fn(PE.Device(running, pair["startup"])))
    r = client.post("/v2/device/r3/persist/read", data={"list": "Lab"})
    assert r.status_code == 200, r.status_code
    get = unescape(re.search(r'hx-get="([^"]+)"', r.get_data(as_text=True)).group(1))
    assert capture_job.wait(get.split("?", 1)[0].rsplit("/", 1)[1], 10)
    r = client.get(get)
    assert r.status_code == 200, r.status_code


def _unlinked(client, _lab, _mp):
    """Pages and fragments a script asks for, not a link: the name chip's refresh, and the
    heartbeat page (unsigned, D3; linked from nothing yet)."""
    for url in ("/v2/who", "/v2/monitoring/heartbeat"):
        r = client.get(url, headers={"Accept": "text/html"})
        assert r.status_code == 200, (url, r.status_code)


def _deploy(client, lab, mp):
    """The deploy card with all three things D4 dropped, as tests/test_device_deploy_v2.py
    builds them on r2's REAL capture: r3's golden lacks `lldp run` and carries
    `load-interval 30` on GigabitEthernet2, its intent adds a dangerous `shutdown` on
    GigabitEthernet3. The card drawn bare, with the dangerous line's reason (the confirm
    offered), and with the residue line ticked for removal (Mode B) and its reason. Last, as
    it changes r3's golden and intent: every page above was walked on the lab as it was."""
    from modules.nsot import approval, hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars
    from tests.test_intent_match import R2

    # The built-in template approved, as test_profile_apply's lab approves it: an unapproved
    # template blocks the plan, and the card draws its refusal and no program.
    mp.setattr(approval, "is_approved", lambda repo, t: True)
    real = open(R2, encoding="utf-8").read()
    golden = real.replace("\nlldp run\n", "\n").replace(
        "\ninterface GigabitEthernet2\n", "\ninterface GigabitEthernet2\n load-interval 30\n")
    assert golden != real
    out = save_golden("Lab", [GoldenItem("r3", golden, "10.255.1.13", platform="cisco_iosxe")],
                      source="capture", actor="operator@example.com", baseline=False)
    assert out.get("commit"), out
    hv = get_parser("cisco_iosxe").parse(real.replace(
        "\ninterface GigabitEthernet3\n", "\ninterface GigabitEthernet3\n shutdown\n"))
    hv["hostname"] = "r3"
    # The credential store holds the intent's secrets, as tests/test_capture.py's lab does: a
    # plan with an unresolved secret is refused before it has a program (MaskedContentError).
    secrets = dict(hv.get("secrets") or {})
    mp.setattr("modules.nsot.hostvars.hydrate_secrets",
               lambda v, host, ln="": {**v, "secrets": dict(secrets)})
    mp.setattr("modules.credentials.get_template_secret",
               lambda key: secrets.get(key.rsplit(":", 1)[-1]))
    hostvars.write_committed(lab["repo"], hv)
    assert save_host_vars("Lab", ["r3"], actor="t", source="extraction")["ok"]
    # What the card is built FROM (the plan's entry and its preview), as the adapter receives
    # it: a key the adapter drops never reaches the context, D4's failure one step upstream.
    from modules import device_actions

    seen, real_card = [], device_actions.deploy_card

    def spy(ref, host, entry, preview, **kw):
        seen.append({"entry": entry, "preview": preview})
        return real_card(ref, host, entry, preview, **kw)

    mp.setattr(device_actions, "deploy_card", spy)
    reason = "&dz::0=the+link+is+being+retired"
    bare = client.get("/v2/device/r3/deploy")
    assert bare.status_code == 200, bare.status_code
    rid = re.search(r'name="rm" value="([^"]+)"', bare.get_data(as_text=True))
    assert rid, "the deploy card offers no residue line for removal"
    for query in (reason, f"{reason}&rm={rid.group(1)}&why::{rid.group(1)}=left+from+the+old+design"):
        r = client.get(f"/v2/device/r3/deploy?back=overview{query}")
        assert r.status_code == 200, r.status_code
    return {"GET /v2/device/<name>/deploy": seen}


def _change_record(client, _lab, _mp):
    """A change record drafted in the deploy card `_deploy` leaves on r3 (PHASE8_PLAN 16.11 item
    3, board CR): Draft a change record pressed with the dangerous line's reason typed, hosted AI
    allowed and the provider's planted answer; then the card planned again carrying the draft's
    call (drawn again from it), and once with another reason (stale)."""
    import json
    import re
    import shutil
    import tempfile
    from html import unescape

    import pytest

    from modules import settings_schema
    from modules.ai import anthropic_adapter, calls, gateway

    answer = {"summary": "Enables LLDP on r3 and shuts GigabitEthernet3.",
              "risk": "Shutting GigabitEthernet3 takes its link down; verify reads it down.",
              "mentions": ["r3", "GigabitEthernet3"]}
    mp = pytest.MonkeyPatch()
    folder = tempfile.mkdtemp(prefix="nmas-v2-context-record-")
    try:
        allowed = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                                 "reason": "the walk's planted answer"}, "ai_cap_usd_per_day": 1.5}
        real_get = settings_schema.get_setting
        mp.setattr(settings_schema, "get_setting",
                   lambda k, d=None: allowed[k] if k in allowed else real_get(k, d))
        mp.setattr(gateway, "_api_key", lambda: "sk-planted-walk-key-0123456789")
        mp.setattr("modules.ai.controls._key_set", lambda: True)
        mp.setattr(calls, "_path", lambda: os.path.join(folder, "ai_calls.jsonl"))
        mp.setattr(anthropic_adapter, "send", lambda body, key: anthropic_adapter.Reply(
            status=200, body={"content": [{"type": "text", "text": json.dumps(answer)}],
                              "stop_reason": "end_turn",
                              "usage": {"input_tokens": 1500, "output_tokens": 120}},
            attempts=1, latency_s=0.4))
        reason = "the link is being retired"
        card = client.get(f"/v2/device/r3/deploy?back=overview&dz::0={reason}").get_data(
            as_text=True)
        vals = re.search(r"data-op=\"change-record\"[^>]*?hx-vals='([^']*)'", card)
        assert vals, "the deploy card offers Draft a change record"
        r = client.post("/v2/device/r3/deploy/change-record",
                        data={"back": "overview", "plan": "card", "dz::0": reason,
                              "program_hash": json.loads(unescape(vals.group(1)))[
                                  "program_hash"]},
                        headers={"HX-Request": "true", "Accept": "text/html"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "DRAFT by AI" in html, html[:600]
        call = re.search(r'name="cr" value="([^"]+)"', html).group(1)
        for why in (reason, "another reason"):
            r = client.get(f"/v2/device/r3/deploy?back=overview&dz::0={why}&cr={call}")
            assert r.status_code == 200, r.status_code
        r = client.get(f"/v2/device/r3/deploy/change-record/{call}.md")
        assert r.status_code == 200, r.status_code
    finally:
        mp.undo()
        shutil.rmtree(folder, ignore_errors=True)


def _rekey(client, _lab, mp):
    """The re-key card (C906) for r3, whose address answers with a key other than the one
    Mercury holds, and its confirm's result. The device's key read is replaced (its own test
    reads a real SSH server: tests/test_host_keys.py); the keys are real, generated here."""
    import paramiko

    from modules import host_keys
    from modules.device import load_saved_devices
    from modules.nsot.listref import resolve

    ip = next(d["ip"] for d in load_saved_devices(resolve("Lab").csv_path)
              if d.get("hostname") == "r3")
    held, now = (paramiko.RSAKey.generate(1024) for _ in range(2))
    host_keys.check(ip, held, owner="v2-context")
    mp.setattr("modules.connection.read_host_key", lambda ip, **kw: host_keys.offered(now))
    card = client.get("/v2/device/r3/rekey?back=overview")
    assert card.status_code == 200, card.status_code
    vals = re.search(r'"hash": "([0-9a-f]+)"', card.get_data(as_text=True))
    assert vals, "the re-key card offers no confirm"
    r = client.post("/v2/device/r3/rekey/confirm",
                    data={"list": "Lab", "hash": vals.group(1), "back": "overview",
                          "reason": "the device was rebuilt from a fresh disk"})
    assert r.status_code == 200, r.status_code


def _drift(client, _lab, _mp):
    """The Overview's Drift row drifted and opened (C342): the REAL drift run of the lab's
    network, r3 answering with its golden (r2's real configuration) with one description
    edited, as tests/test_drift_overview.py runs it; then the Overview and what its row opens
    onto. Its patches are undone before the next provider."""
    import pytest

    from modules import drift_check
    from tests.test_intent_match import R2

    golden = open(R2, encoding="utf-8").read()
    running = golden.replace(" description P2P to s2 Gi0/2 - RIPng",
                             " description temp test link", 1)
    assert running != golden, "r2's capture moved: re-take the edit"
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr("modules.connection.get_persistent_connection",
                   lambda dev, pool, lock: dev["hostname"])
        mp.setattr("modules.commands.run_device_command",
                   lambda conn, cmd: running if conn == "r3" else "")
        mp.setattr("modules.config_read.check",
                   lambda text, hostname, previous=None, strict=True: text)
        result = drift_check.run_drift_check(triggered_by="v2-context", list_name="Lab")
        drift_check._save_state({"last_check_ts": 1.0, "last_result": result}, "Lab")
    finally:
        mp.undo()
    for url in ("/v2/device/r3/overview?list=Lab", "/v2/device/r3/drift?list=Lab"):
        r = client.get(url)
        assert r.status_code == 200, (url, r.status_code)


def _diagnose(client, _lab, _mp):
    """Diagnose… (board H, H16) on r3: the card on the fleet's real intent (each adjacency
    offered, those with no protocol not offered, the reads on both ends; then Can't reach's
    devices), the press as a job, and the diagnosis drawn by its job's card. The run is the
    route test's recorded diagnosis (tests/test_heal_diagnose_v2.py `FAKE`), whose real run its
    own tests make; its patches are undone before the next provider."""
    import pytest

    from modules.heal import diagnose as D
    from modules.nsot import capture_job
    from tests import test_heal_diagnose as T
    from tests.test_heal_diagnose_v2 import FAKE

    model, intents = T.fleet()
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(D, "_sources", lambda network, model_=None, intents_=None: (model, intents))
        mp.setattr(D, "run", lambda network, runbook, target, actor: dict(FAKE))
        body = client.get("/v2/device/r3/diagnose?back=overview").get_data(as_text=True)
        fp = re.search(r'name="fingerprint" value="([0-9a-f]{16})"', body)
        assert fp, "the card offers no run"
        reach = client.get("/v2/device/r3/diagnose?back=overview&runbook=cant_reach")
        assert reach.status_code == 200, reach.status_code
        r = client.post("/v2/device/r3/diagnose/run", data={
            "list": "Lab", "back": "overview", "runbook": "adjacency_down",
            "adjacency": "link|r4|Gi4", "fingerprint": fp.group(1)})
        job = re.search(r"/diagnose/job/([0-9a-f]+)", r.get_data(as_text=True))
        assert job and capture_job.wait(job.group(1), 10), r.status_code
        done = client.get(f"/v2/device/r3/diagnose/job/{job.group(1)}?back=overview")
        assert "Diagnosis:" in done.get_data(as_text=True), done.status_code
        # H16's second part: an alert's hint naming no offered adjacency (said on the card),
        # r4 already in a diagnosis (named in place of Run; its lock in a folder of its own,
        # never the store), and Can't reach's hops drawn by its job's card.
        import tempfile

        from tests.test_heal_diagnose_v2 import TestTheHopsDrawn
        hinted = client.get("/v2/device/r3/diagnose?back=overview&interface=GigabitEthernet9")
        assert "the first is chosen" in hinted.get_data(as_text=True), hinted.status_code
        with tempfile.TemporaryDirectory(prefix="nmas-v2-context-diag-") as folder:
            mp.setattr("modules.config.LISTS_DIR", folder)
            with D.DiagnosisLock("Lab", ["r4"], "dg-held", "operator@example.com"):
                busy = client.get("/v2/device/r3/diagnose?back=overview&adjacency=link|r4|Gi4")
            assert "r4 is in diagnosis dg-held" in busy.get_data(as_text=True), busy.status_code
        job = capture_job.start("Lab", "diagnosing r3", "operator@example.com", lambda _j: dict(
            FAKE, runbook="cant_reach", hops=TestTheHopsDrawn.HOPS), kind="diagnosis")
        assert capture_job.wait(job, 10)
        hops = client.get(f"/v2/device/r3/diagnose/job/{job}?back=overview")
        assert "The path, hop by hop" in hops.get_data(as_text=True), hops.status_code
    finally:
        mp.undo()


def _in_progress(client, _lab, mp):
    """The top bar's In progress chip (C537) while r3 is held by a deploy: the walk's pages
    ask for it with nothing running, when it draws nothing. Its list carries the running row;
    a finished row is a kept job's, drawn by tests/test_in_flight.py's rotation."""
    from modules.nsot import device_ops

    mp.setattr("modules.integration_groups.network_names", lambda: ["Lab"])
    with device_ops.hold("Lab", "r3", "deploy", "operator@example.com"):
        r = client.get("/operations/in_flight", headers={"HX-Request": "true",
                                                         "Accept": "text/html"})
    assert r.status_code == 200 and "ip-chip" in r.get_data(as_text=True), r.status_code


def _pending(client, lab, _mp):
    """A device pending onboarding (C1193's page and fragment): recorded the way Create records
    it (`manifest.upsert_device(pending=True)`), so the product's own `find_pending` finds it;
    then its page, its progress fragment, and the fragment for a device that is not pending."""
    from modules.nsot import manifest

    manifest.upsert_device(lab["repo"], manifest.identity_for(device_uid="ctx-pending-s9"),
                           "s9", platform="cisco_iosxe", pending=True, address_source="static",
                           mgmt_ip="192.0.2.9", role="router")
    for url in ("/v2/device/s9?list=Lab", "/v2/device/s9/pending/progress?list=Lab",
                "/v2/device/r3/pending/progress?list=Lab"):
        r = client.get(url, headers={"Accept": "text/html"})
        assert r.status_code == 200, (url, r.status_code)


def _netbox_source(client, lab, _mp):
    """The Inventory source card of a network sourced from NetBox (C1160): the lab's network
    read through the inventory's REAL fetch, adapt and refresh from the shared fake
    (tests/fake_netbox.py), as tests/test_network_source_v2.py's `nb_branch` reads it: a device
    with no primary address and one on a platform Mercury does not map (skipped), one whose
    role NetBox does not classify (a warning), and one deleted from NetBox between two reads
    (gone). Its patches are undone and the network put back on its own list before the next
    provider."""
    import pytest

    from modules import credentials, inventory
    from modules.inventory.source_config import save
    from tests.fake_netbox import FakeNetBox

    nb = FakeNetBox()
    site = nb.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
    nb.seed("extras/custom-fields", {"name": "mercury_kind"})
    nb.seed("dcim/device-roles", {"name": "Router", "slug": "router",
                                  "custom_fields": {"mercury_kind": "router"}})
    nb.seed("dcim/device-roles", {"name": "Edge", "slug": "edge", "custom_fields": {}})

    def device(name, ip, platform="cisco-ios-xe", role="router"):
        return nb.seed("dcim/devices", {
            "name": name, "primary_ip4": {"address": f"{ip}/24"} if ip else None,
            "platform": {"slug": platform}, "role": {"slug": role},
            "site": {"id": site["id"], "slug": "lab", "name": "Lab"},
            "status": {"value": "active"}})

    device("nb-r1", "192.0.2.31")
    gone = device("nb-r2", "192.0.2.32")
    device("nb-noaddr", None)
    device("nb-arista", "192.0.2.34", platform="arista-eos")
    device("nb-edge", "192.0.2.35", role="edge")
    mp = pytest.MonkeyPatch()
    folder = os.path.dirname(lab["repo"])
    try:
        mp.setattr(credentials, "_FILE", os.path.join(folder, "v2-context-creds.json"))
        credentials.save_profile("default", "admin", "pw", "en")
        mp.setattr("modules.netbox_client._nb_ready",
                   lambda: (True, "", nb, "http://netbox.example.invalid"))
        mp.setattr("modules.inventory.refresh_async", lambda name: None)
        # The lab points `get_list_data_dir` at its folder (where a save writes); a read finds
        # the file through `list_data_path`, which the lab leaves on the store.
        mp.setattr("modules.config.list_data_path", lambda name: folder)
        save("Lab", {"source": "netbox", "filters": {"site": "lab"}})
        inventory.invalidate()
        got = inventory.refresh_list("Lab")
        assert got["ok"], got
        nb.delete(f"http://netbox.example.invalid/api/dcim/devices/{gone['id']}/")
        got = inventory.refresh_list("Lab")
        assert got["ok"], got
        for url in ("/v2/settings/network/Lab/source", "/v2/settings/network/Lab?tab=network"):
            r = client.get(url, headers={"Accept": "text/html"})
            assert r.status_code == 200, (url, r.status_code)
    finally:
        save("Lab", {"source": "local"})
        inventory.invalidate()
        mp.undo()


def _silenced_alert(client, _lab, _mp):
    """Needs attention with a Grafana alert firing under a silence (C1277): the real capture's
    `Critical syslog received` instance set Alerting for s4 and silenced, as
    tests/test_grafana_reader.py's `silenced_syslog` edits it, read through the REAL
    `attention.grafana_source` and drawn by GET /v2/attention. Its patch is undone before the
    next provider."""
    import pytest

    from modules import attention
    from modules.readers import grafana_alerts
    from tests import test_grafana_reader as GR

    view, am = GR.silenced_syslog()
    value = grafana_alerts.parse(GR.load("ruler"), view, am, GR.READ_AT, silences=[GR.SILENCE])
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(attention, "SOURCES",
                   (lambda: attention.grafana_source(cached=GR.cached(value)),))
        r = client.get("/v2/attention")
        assert r.status_code == 200 and "silenced in Grafana" in r.get_data(as_text=True), \
            r.status_code
    finally:
        mp.undo()


def _alert_evidence(client, _lab, _mp):
    """Monitoring › Alerts with packs (PHASE8_PLAN 15.9, P1): r3's real heartbeat instance
    firing (its device by label, r3 in the lab), the real `Critical syslog received` instance
    firing for s4 under a silence (no device of the lab's), and an earlier pack of r3's alert
    from a first firing, each built by the real trigger over the Loki and Prometheus captures
    (tests/test_evidence_pack.py's stand-ins); then the tab and each card's pack drawn. Its
    patches and stores are undone before the next provider."""
    import json
    import shutil
    import tempfile

    import pytest

    from modules import evidence_pack as EP
    from modules import history_logq as Q
    from modules import reader_job
    from modules.readers import grafana_alerts as G
    from tests import test_evidence_pack as T
    from tests import test_grafana_reader as GR

    mp = pytest.MonkeyPatch()
    folder = tempfile.mkdtemp(prefix="nmas-v2-context-packs-")
    try:
        mp.setattr(EP, "_path", lambda: os.path.join(folder, "evidence_packs.jsonl"))
        mp.setattr(EP, "_alert_stores", lambda: ["grafana-alerts-walk"])
        mp.setattr(reader_job, "store_path",
                   lambda name: os.path.join(folder, "readers", f"{name}.json"))
        mp.setattr(Q, "_client", lambda *a, **k: T.DeviceLoki())
        T._prometheus(mp)
        # The observer's questions (C1896) from Walk 2's captured answers, an SNMP exporter's
        # own scrape planted (the lab's Prometheus scrapes none): every kind of its pieces.
        from tests import test_evidence_observer as OB
        OB._install(mp, edit={"figures": OB.with_self_scrape})
        # The neighbours read (C2176, schema 8): the network model's one-hop answer planted
        # (the walk's lab holds no shared link; the model's walk over the real fleet is
        # tests/test_evidence_pack_neighbours.py's), so a pack's neighbours line draws.
        mp.setattr(EP, "neighbours_of",
                   lambda capture: ([("dev:302", "r2", "a link in 10.255.3.0/24")], 1))
        os.makedirs(os.path.join(folder, "readers"))

        def store(value):
            with open(reader_job.store_path("grafana-alerts-walk"), "w", encoding="utf-8") as fh:
                json.dump({"last_good": {"value": value, "value_at": "2026-10-15T08:24:00Z"}},
                          fh)
        store(T._alerts(heartbeat=True, active="2026-10-15T08:05:00Z"))
        assert EP.after_alerts_read(clock=lambda: T.NOW)
        value = T._alerts(heartbeat=True)
        view, am = GR.silenced_syslog()
        value["instances"] += G.parse(GR.load("ruler"), view, am, GR.READ_AT,
                                      silences=[GR.SILENCE])["instances"]
        store(value)
        assert EP.after_alerts_read(clock=lambda: T.NOW)
        r = client.get("/v2/monitoring/alerts", headers={"Accept": "text/html"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "2 firing" in html, r.status_code
        for pack in EP.read()["rows"]:
            r = client.get(f"/v2/monitoring/alerts/pack/{pack['id']}",
                           headers={"HX-Request": "true", "Accept": "text/html"})
            assert r.status_code == 200 and 'data-ref="logs"' in r.get_data(as_text=True)
            # P1's Explain on each pack, hosted AI off (its default): the answer it draws,
            # with nothing sent.
            r = client.post(f"/v2/monitoring/alerts/pack/{pack['id']}/explain",
                            headers={"HX-Request": "true", "Accept": "text/html"})
            assert r.status_code == 200 and "hosted AI is off" in r.get_data(as_text=True)
        # And one answered (hosted AI allowed, the adapter answering as planted): the
        # hypotheses and their references drawn.
        from modules import settings_schema
        from modules.ai import anthropic_adapter, calls, gateway
        pack = EP.read()["rows"][-1]
        cite = next(s["ref"] for s in pack["sections"] if s["name"] == "alert")
        # Two hypotheses: the answer card's Most likely cause and its Other possibilities
        # (board AlertsExplain revised 2026-10-29), so both of the card's loops draw.
        answer = {"outcome": "answer", "rationale": "The heartbeat stopped.",
                  "hypotheses": [{"claim": "The device stopped sending heartbeats.",
                                  "evidence_refs": [cite],
                                  "confirm_with": "show logging | include HEARTBEAT"},
                                 {"claim": "The collector stopped receiving them.",
                                  "evidence_refs": [cite], "confirm_with": "show logging"}],
                  "checked": [], "needs_human": True, "why_not": ""}
        allowed = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                                 "reason": "the walk's planted answer"}, "ai_cap_usd_per_day": 1.5}
        real_get = settings_schema.get_setting
        mp.setattr(settings_schema, "get_setting",
                   lambda k, d=None: allowed[k] if k in allowed else real_get(k, d))
        mp.setattr(gateway, "_api_key", lambda: "sk-planted-walk-key-0123456789")
        mp.setattr(calls, "_path", lambda: os.path.join(folder, "ai_calls.jsonl"))
        # The answers kept with their packs (C1853), in this walk's own folder.
        from modules.ai import explain_answers
        mp.setattr(explain_answers, "_path", lambda: os.path.join(folder, "explain_answers.jsonl"))
        mp.setattr(anthropic_adapter, "send", lambda body, key: anthropic_adapter.Reply(
            status=200, body={"content": [{"type": "text", "text": json.dumps(answer)}],
                              "stop_reason": "end_turn",
                              "usage": {"input_tokens": 4000, "output_tokens": 200}},
            attempts=1, latency_s=0.5))
        r = client.post(f"/v2/monitoring/alerts/pack/{pack['id']}/explain",
                        headers={"HX-Request": "true", "Accept": "text/html"})
        assert r.status_code == 200 and "The device stopped sending heartbeats." in \
            r.get_data(as_text=True)
        # And no fault found (C1742): what was checked drawn, no hypothesis. A second answer for
        # the same pack is Explain again (C1853: a plain Explain draws the one kept).
        answer = {"outcome": "no_fault_found", "rationale": "Every figure of the alert is steady.",
                  "hypotheses": [], "checked": [cite], "needs_human": False, "why_not": ""}
        r = client.post(f"/v2/monitoring/alerts/pack/{pack['id']}/explain", data={"again": "1"},
                        headers={"HX-Request": "true", "Accept": "text/html"})
        assert r.status_code == 200 and "Every figure of the alert is steady." in \
            r.get_data(as_text=True)
        # And an answer naming the alert's device while citing nothing of it (the operator's
        # decision 7a, 2026-10-28): Mercury cites it by the alert, drawn as Mercury's.
        # r3's pack: the syslog alert's is of no one device.
        pack = next(p for p in reversed(EP.read()["rows"]) if p.get("device"))
        own = pack["device"]
        others = next(s["ref"] for s in pack["sections"] if s["name"] == "concurrent")
        answer = {"outcome": "answer", "rationale": f"The heartbeat stopped while {own} was up.",
                  "hypotheses": [{"claim": "The device stopped sending heartbeats.",
                                  "evidence_refs": [others],
                                  "confirm_with": "show logging | include HEARTBEAT"}],
                  "checked": [], "needs_human": True, "why_not": ""}
        r = client.post(f"/v2/monitoring/alerts/pack/{pack['id']}/explain", data={"again": "1"},
                        headers={"HX-Request": "true", "Accept": "text/html"})
        assert r.status_code == 200 and "cited by Mercury" in r.get_data(as_text=True)
        # And a hypothesis citing a change without saying who made it (the operator's order of
        # 2026-10-29, "WHO, guaranteed in code"): Mercury adds who, drawn as Mercury's. The
        # walk's packs are replays, so History after the alert's time is left out of them: a
        # copy of r3's pack holding a deploy's receipt, kept under its own id and hashed.
        import copy
        planted = copy.deepcopy(pack)
        planted["id"] = EP.pack_id("f" * 20)
        hist = next(s for s in planted["sections"] if s["name"] == "history")
        hist.update(state="ok", why="", pieces=[{
            "ref": "history:1", "at": planted["built_at"], "kind": "receipt",
            "what": "Interface description sent: deployed", "who": "operator@example.com",
            "outcome": "deployed", "sha": "0123456789ab", "detail": "1 line(s) sent",
            "verified": "access"}])
        planted.pop("hash")
        planted["hash"] = EP.digest(planted)
        assert EP.record(planted)["ok"]
        answer = {"outcome": "answer", "rationale": "A recorded change preceded it.",
                  "hypotheses": [{"claim": "A recorded change preceded the heartbeat's stop.",
                                  "evidence_refs": ["history:1", "alert"],
                                  "confirm_with": "show logging | include HEARTBEAT"}],
                  "checked": [], "needs_human": True, "why_not": ""}
        r = client.post(f"/v2/monitoring/alerts/pack/{planted['id']}/explain",
                        headers={"HX-Request": "true", "Accept": "text/html"})
        assert r.status_code == 200 and "who, added by Mercury" in r.get_data(as_text=True)
        # History's window on that call (15.14): the prompt as sent, the answer as received.
        newest = calls.read()["rows"][0]["id"]
        r = client.get(f"/v2/history/ai-call/{newest}", headers={"Accept": "text/html"})
        assert r.status_code == 200 and "Sent to the model" in r.get_data(as_text=True)
    finally:
        mp.undo()
        shutil.rmtree(folder, ignore_errors=True)


def _logs_builder_leftovers(client, _lab, _mp):
    """History › Query's logs builder (the operator's walk of 2026-10-26) with Loki answering
    as the lab's did (tests/test_history_ask_logs.py's stand-in over its captures): a kind
    chosen that the range does not hold, kept and marked "not seen in this range", and a
    mnemonic chosen while the text names another, said as filters that cannot match together
    with the click that drops the leftover. Its patches are undone before the next provider."""
    import pytest

    from modules import history_logq as Q
    from tests import test_history_ask_logs as T

    mp = pytest.MonkeyPatch()
    try:
        loki = T.FakeLoki()
        mp.setattr(Q, "_client", lambda *a, **k: loki)
        mp.setattr(Q, "_now", lambda: T.NOW)
        Q.forget()
        r = client.get("/v2/history/query/ask/logs?list=Lab&job=no-such-kind"
                       "&mn=%25LINK-3-UPDOWN&has=OSPF-5-ADJCHG", headers={"Accept": "text/html"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "not seen in this range" in html \
            and "cannot match together" in html, r.status_code
    finally:
        mp.undo()
        Q.forget()


def _alert_history(client, _lab, _mp):
    """Monitoring › Alerts › History (the alert history, 2026-10-26): the captured state
    history of 21 Oct, 01:00 to 03:00 UTC (tests/fixtures/grafana/alert_history/), backfilled
    by the real recorder; the tab with every alert shown, Build evidence pressed on one (its
    rebuilt pack drawn in place), and the tab again with that pack. Its patches and stores are
    undone before the next provider."""
    import shutil
    import tempfile

    import pytest

    from modules import alert_history as H
    from modules import evidence_pack as EP
    from tests.test_alert_history import _backfill, load

    mp = pytest.MonkeyPatch()
    folder = tempfile.mkdtemp(prefix="nmas-v2-context-history-")
    try:
        mp.setattr(EP, "_path", lambda: os.path.join(folder, "evidence_packs.jsonl"))
        mp.setattr(H, "_path", lambda: os.path.join(folder, "alert_history.jsonl"))
        mp.setattr(H, "_networks", lambda: {"grafana-alerts": ["Lab"]})
        mp.setattr(H, "_firing_now", lambda: set())
        assert _backfill(load("annotations_firing"))["added"] == 93
        url = "/v2/monitoring/alerts/history?range=all&show=all"
        r = client.get(url, headers={"Accept": "text/html"})
        assert r.status_code == 200 and "Build evidence" in r.get_data(as_text=True)
        e = next(e for e in H.episodes(H.read()["rows"]) if e["outcome"] == "fired")
        r = client.post(f"/v2/monitoring/alerts/history/{e['id']}/evidence",
                        headers={"HX-Request": "true", "Accept": "text/html"})
        assert r.status_code == 200 and "rebuilt afterwards" in r.get_data(as_text=True)
        r = client.get(url, headers={"Accept": "text/html"})
        assert r.status_code == 200 and EP.read()["rows"][0]["id"] in r.get_data(as_text=True)
    finally:
        mp.undo()
        shutil.rmtree(folder, ignore_errors=True)


def _save_no_golden(client, _lab, _mp):
    """Devices › Save's no-golden scope (C1232) on the lab as it is: r3 holds a committed
    golden and is left out, named; r9 holds none and is planned."""
    r = client.get("/v2/devices/save?list=Lab&scope=no_golden", headers={"Accept": "text/html"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'data-keep="save-scope-left"' in html, r.status_code


def _profile_versions(client, _lab, _mp):
    """Monitoring › Profile's Propose with two versions of SNMP's shared fields (C1269): the
    lab's fleet as `profile_propose._fleet` reads it, plus r1, r2's real configuration with
    `snmp ifmib ifindex persist` removed (test_profile_apply's `_add_r1` edit), parsed by the
    real parser. The card offering each version, previewing a chosen one (the confirm carrying
    it), and naming a version no device holds. Its patch is undone before the next provider."""
    import pytest

    from modules.nsot import profile_propose as pp
    from modules.nsot.parsers import get_parser
    from tests.test_intent_match import R2

    lines = [ln for ln in open(R2, encoding="utf-8").read().splitlines()
             if not ln.startswith("snmp ifmib ifindex persist")]
    assert len(lines) < len(open(R2, encoding="utf-8").read().splitlines()), "re-take the edit"
    other = get_parser("cisco_iosxe").parse(
        "\n".join("hostname r1" if ln.startswith("hostname ") else ln for ln in lines) + "\n")
    real = pp._fleet

    def fleet(name):
        got, skipped = real(name)
        return got + [("r1", "cisco_iosxe", "", other)], skipped

    from modules import list_settings
    setting = list_settings.value

    def value(name, key, default=None):
        # SNMP's section is proposed only where Prometheus is configured (as on the host, and
        # in test_profile_apply's lab); the address is never reached.
        if key == "prometheus_url":
            return "http://prometheus.invalid:9090"
        return setting(name, key, default)

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(pp, "_fleet", fleet)
        mp.setattr(list_settings, "value", value)
        (snmp,) = [s for s in pp.propose("Lab")["sections"] if s["section"] == "snmp"]
        assert len(snmp.get("variants") or []) == 2, snmp
        vid = snmp["variants"][0]["id"]
        for url, words in (("/v2/monitoring/profile/propose", 'data-profile-choice="snmp"'),
                           (f"/v2/monitoring/profile/propose?choose=snmp:{vid}",
                            'name="choose"'),
                           ("/v2/monitoring/profile/propose?choose=snmp:0000beef",
                            "Not applied:")):
            r = client.get(url, headers={"Accept": "text/html"})
            assert r.status_code == 200 and words in r.get_data(as_text=True), (url, words)
    finally:
        mp.undo()


def _read_only_account(client, lab, _mp):
    """Credentials › Profiles' Read-only account card (board H, artboard N; H28) with two
    profiles, one carrying a read-only account set by a person and one without: its rows, the
    form open on each (Set and Replace), and What AI may send on the Network tab with device
    state on. The store is this provider's own; its patches are undone before the next."""
    import pytest

    from modules import credentials
    from modules.ai import egress_classes

    mp = pytest.MonkeyPatch()
    folder = os.path.dirname(lab["repo"])
    try:
        mp.setattr(credentials, "_FILE", os.path.join(folder, "v2-context-read-creds.json"))
        credentials.save_profile("default", "admin", "pw-ctx-1", "en")
        credentials.save_profile("role:router", "netops", "pw-ctx-2", "")
        credentials.set_read_account("default", "mercury-ro", "ReadOnly-ctx-1",
                                     actor="v2-context@example.invalid", verified="access")
        mp.setattr(egress_classes, "device_state", lambda network: {
            "state": "on", "switch": True, "why": "",
            "on_record": {"by": "v2-context@example.invalid", "at": "2026-11-06T00:00:00Z",
                          "reason": "the walk's analysis reads"}})
        # The card's own region and forms, not the whole tab: the walk's Credential profiles
        # table stays as the walk's store draws it.
        for url in ("/v2/credentials/profiles/read-account",
                    "/v2/credentials/profiles/read-account/form?name=default",
                    "/v2/credentials/profiles/read-account/form?name=role:router",
                    "/v2/settings/network/Lab?tab=network"):
            r = client.get(url, headers={"Accept": "text/html"})
            assert r.status_code == 200, (url, r.status_code)
        html = client.get("/v2/credentials/profiles/read-account").get_data(as_text=True)
        assert "mercury-ro" in html and "ReadOnly-ctx-1" not in html
    finally:
        mp.undo()


def _no_change_window(client, _lab, _mp):
    """Credentials › Profiles with a no-change window set (C1317; none by default, so the
    walk's lab has none): `change_windows.windows` answers one, as the installation's setting
    would, and the summary names it. Its patch is undone before the next provider."""
    import pytest

    from modules import change_windows

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(change_windows, "windows",
                   lambda: [{"start": "22:00", "end": "23:00", "reason": "a freeze"}])
        r = client.get("/v2/credentials/profiles?list=Lab", headers={"Accept": "text/html"})
        assert r.status_code == 200 and ("No run starts inside the no-change window 22:00 to "
                                         "23:00 UTC (a freeze).") in r.get_data(as_text=True), \
            r.status_code
    finally:
        mp.undo()


def _netbox_lag(client, _lab, _mp):
    """The device page's NetBox tab with NetBox holding less than r3's committed golden
    (C1344): the reader's stored answer as tests/test_netbox_after_intent.py reads it from the
    fleet's r3 and r4 and the captured LLDP (one interface, an IPv4 and an IPv6 address, one
    cable), and NetBox configured with no record of r3. Its patches are undone before the next
    provider."""
    import pytest

    lag = {"state": "behind", "value_at": "2026-10-19T00:00:00Z", "why": "", "lldp_error": "",
           "lag": {"absent": True, "netbox_id": None, "interfaces": ["GigabitEthernet4"],
                   "addresses": ["192.0.2.14/31", "2001:db8:2:e::1/64"],
                   "cables": ["r3 Gi4 to r4 Gi4"]}}
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr("modules.readers.netbox_lag.stored_for", lambda list_name, host: lag)
        mp.setattr("modules.device_netbox.for_device", lambda ref, dev: {
            "configured": True, "errors": [], "record": None, "absent": True, "counts": {},
            "provenance": None, "mods": None, "platform_note": "", "ui_url": ""})
        r = client.get("/v2/device/r3/netbox?list=Lab", headers={"Accept": "text/html"})
        assert r.status_code == 200 and "NetBox holds less" in r.get_data(as_text=True), \
            r.status_code
    finally:
        mp.undo()


#: Two real commits asking for the same checked host step, `[updater]`, newest first, each
#: trailer cut to its first sentence: what the panel's checked-done row draws (C2246).
UPDATER_STEPS = (
    ("149c8f89761a9f93edd938f2f8d87c4100daf0a4",
     "C1669: a rollback in minutes\n\nHost-Step-After: [updater] re-install the updater's copy "
     "of scripts/nmas-deploy (docs/UPDATE.md, \"Re-install\"); the updater check reads done "
     "once it matches.\n"),
    ("63c0b436f99c2e85d16ebfcea5c84abb2cf8d62c",
     "The updater\n\nHost-Step-After: [updater] re-install the updater's copies of "
     "deploy/update/nmas-update and scripts/nmas-deploy (docs/UPDATE.md, \"Re-install\"); the "
     "updater check reads done once they match.\n"),
)


def _update_owed(client, _lab, _mp):
    """Update with a host step the running release still owes (C795) and one the tool's own
    check reads done, asked for by two commits (C442's superseded row): `host_steps.owed` read
    from real commits' trailers, 99664f27's not-checkable `Host-Step-After` and two
    `[updater]` steps (UPDATER_STEPS), never from the checkout's history. The walk drew each
    only while the checkout's last 200 commits held one: 3db04b01 moved 99664f27 to 201 back
    (CI #994), and ebbf71ca moved 149c8f89, the last `[updater]` step, to 201 back
    (2026-11-01, C2246). Its patches are undone before the next provider."""
    import pytest

    from modules import host_steps
    from routes import health

    sha = "99664f2792d7e8eb872f8c2728364b3896f6a07c"
    body = ("C794: the host step turning Loki's own detected_level off\n\nHost-Step-After: on "
            "the NMAS host: bash scripts/host-steps/c794-loki-detected-level-off.sh (Loki's own "
            "detected_level off; severity the one level)\n")
    log_text = "".join(f"{s}\x1f{b}\x1e" for s, b in UPDATER_STEPS) + f"{sha}\x1f{body}\x1e"
    real = host_steps.owed
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(health, "_COMMIT", sha)
        mp.setattr(host_steps, "owed", lambda running, **kw: real(running, log_text=log_text))
        mp.setitem(host_steps.CHECKS, "updater",
                   lambda root: {"state": "done", "detail": "the updater's copies match"})
        for path in ("/v2/update", "/v2/update/panel"):
            r = client.get(path, headers={"Accept": "text/html"})
            text = r.get_data(as_text=True)
            assert r.status_code == 200 and 'id="update-owed-steps"' in text, (path,
                                                                               r.status_code)
            assert "the updater&#39;s copies match" in text or "the updater's copies match" \
                in text, f"{path}: the checked-done step was not drawn"
    finally:
        mp.undo()


def _lease_release(client, _lab, _mp):
    """DHCP › Leases' Release lease… (C1403): the card from a real preview, on Kea's captured
    leases (tests/fixtures/kea) behind the page, as tests/test_dhcp_leases.py reads them, on
    Lab owning its Kea (the walk's Lab inherits Default's, and changes nothing, C1181). The
    walk's DHCP reader has never read, so no followed GET draws a lease row to release. Its
    patches are undone before the next provider."""
    import pytest

    from modules import reader_job
    from tests.test_dhcp_leases import RIG, LeaseKea
    from tests.test_dhcp_v2 import _value

    # The DHCP reader's value as test_dhcp_v2 builds it from the same captures: the page draws
    # its Leases tab only over a stored read.
    doc = {"last_attempt": {"at": "2026-10-11T01:38:20Z", "ok": True, "error": ""},
           "last_good": {"value": _value(), "value_at": "2026-10-11T01:38:20Z"}}
    real = reader_job.read_cached_for
    mp = pytest.MonkeyPatch()
    try:
        kea = LeaseKea({})
        mp.setattr("modules.integrations.kea.KeaIntegration", lambda **kw: kea)
        mp.setattr("modules.reader_job.read_cached_for",
                   lambda name, list_name: ({"state": "ok", "doc": doc, "why": ""}
                                            if name == "dhcp" else real(name, list_name)))
        # Lab setting its own Kea, as test_dhcp_v2's `web` gives it (C1181: the owner's page).
        mp.setattr("modules.list_settings.kea_owner", lambda page: (page, "set here"))
        r = client.get("/v2/dhcp/lease?list=Lab&family=IPv4&address=" + RIG["address"],
                       headers={"Accept": "text/html", "HX-Request": "true"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "Release 10.10.10.102" in html, \
            (r.status_code, re.findall(r'class="dh-refuse"[^>]*><p>([^<]*)', html),)
        assert kea.dels == [], "a preview released a lease"
    finally:
        mp.undo()


def _ip_sla_retunes(client, _lab, _mp):
    """C1491: the IP SLA page with a policy, so r3's probe (r2's real `ip sla 1`, every 10 s)
    is drawn off its 60 s in the page's frequency section. The profile is put back as it was
    before the next provider."""
    import copy

    from modules.nsot import listref
    from modules.nsot import profile as P

    repo = listref.resolve("Lab").repo_dir
    before = P.read_committed(repo)
    doc = copy.deepcopy(before) if before else {"version": P.VERSION, "sections": {}}
    doc.setdefault("sections", {})["ip_sla"] = {"policy": "upstream", "frequency": 60}
    assert P.commit_profile("Lab", doc, "v2-context", "IP SLA policy for the walk")["ok"]
    try:
        r = client.get("/v2/monitoring/ip-sla?list=Lab")
        assert r.status_code == 200, r.status_code
        assert 'id="ipsla-retunes"' in r.get_data(as_text=True), \
            "floor: r3's 10 s probe is proposed back to the policy's 60 s"
    finally:
        back = before if before else {"version": P.VERSION, "sections": {}}
        assert P.commit_profile("Lab", back, "v2-context", "the profile put back")["ok"]


def _ip_sla_unsent(client, _lab, _mp):
    """C1499: the IP SLA page with a probe committed in intent that its device does not run
    (r3's, at 60 s in intent while its golden runs it every 10 s), so the page's "Committed,
    not yet on the device" section draws its row and Retry. Planted at `ip_sla_policy.unsent`
    for this one GET, through the real route and receipts read, and put back before the next
    provider."""
    import pytest

    from modules.nsot import ip_sla_policy as P

    row = {"on": "r3", "id": "1", "target": "192.0.2.13", "want": 60,
           "has": {"target": "192.0.2.13", "frequency": 10}, "elsewhere": False}
    with pytest.MonkeyPatch.context() as m:
        m.setattr(P, "unsent", lambda intents, goldens: [row])
        r = client.get("/v2/monitoring/ip-sla?list=Lab")
        assert r.status_code == 200, r.status_code
        assert 'id="ipsla-retry-r3"' in r.get_data(as_text=True), \
            "floor: the committed probe r3 does not run is listed with its Retry"


def _console_netbox(mp):
    """A NetBox holding a Planned device `edge1` cabled to a console server's port (and a
    second port with no record), the shared fake's measured console shapes; `_nb_ready` answers
    with it. ``(fake, device, server_port, spare_port)``."""
    from tests.fake_netbox import FakeNetBox

    fake = FakeNetBox()
    dev = fake.seed("dcim/devices", {"name": "edge1", "status": "planned"})
    cs = fake.seed("dcim/devices", {"name": "cons-1", "status": "active"})
    port = fake.seed("dcim/console-ports", {"device": dev["id"], "name": "con 0"})
    sport = fake.seed("dcim/console-server-ports", {"device": cs["id"], "name": "port 5"})
    spare = fake.seed("dcim/console-server-ports", {"device": cs["id"], "name": "port 6"})
    fake.seed("dcim/cables", {
        "a_terminations": [{"object_type": "dcim.consoleport", "object_id": port["id"]}],
        "b_terminations": [{"object_type": "dcim.consoleserverport",
                            "object_id": sport["id"]}], "status": "connected", "label": ""})
    mp.setattr("modules.netbox_client._nb_ready", lambda: (True, "", fake, "http://nb.invalid"))
    return fake, dev, sport, spare


def _console_ztp(client, lab, _mp):
    """Out-of-band ZTP's card (O6b) and Add device's offer (O7), through the real routes and
    the real survey and kick-start, on a fake console server answering with s5's captured
    console text (tests/test_console_ztp.py's), at its short timings: the offer on a review,
    the survey's preview and its refusal, its run's result, the kick-start's form, preview and
    result, and a run no job explains. Its patches are undone before the next provider."""
    import pytest

    from modules.nsot import capture_job, console_servers
    from modules.nsot import console_ztp as Z
    from modules.nsot import console_survey as V
    from modules.nsot import console_profiles as P
    from tests.console_fakes import Console, RawServer
    from tests.test_console_session import PNP
    from tests.test_console_ztp import FAST, ONBOARDING, PLANNED, blank_answers, kick_answers

    mp = pytest.MonkeyPatch()
    consoles = []
    server = RawServer(lambda: Console(*consoles.pop(0)))
    try:
        _fake, dev, sport, _spare = _console_netbox(mp)
        mp.setattr(Z, "DEFAULT_TIMINGS", FAST)
        # C1592: the switch's kick-start types its out-of-band onboarding's static address.
        mp.setattr(Z, "_onboarding", lambda *a, **k: dict(ONBOARDING))
        # The lab points `get_list_data_dir` (where a run's record is written) at its folder
        # and leaves `list_data_path` (where it is read) on the store; one folder here, as on
        # an installation, where the two are the same path.
        from modules import config
        mp.setattr("modules.config.list_data_path", config.get_list_data_dir)
        assert console_servers.set_port(sport["id"], {"driver": "raw_tcp", "host": server.host,
                                                      "tcp_port": server.port},
                                        actor="v2-context")["ok"]
        # Add device's review asks for the offer as it draws: a device NetBox holds as Planned
        # with its console path, and one it holds no Planned record of.
        r = client.get(f"/v2/onboard/console/offer?list_name=Lab&netbox_id={dev['id']}"
                       "&hostname=edge1&platform=cisco_ios&role=switch")
        assert "Kick-start through the console…" in r.get_data(as_text=True), r.status_code
        r = client.get("/v2/onboard/console/offer?list_name=Lab&hostname=edge1")
        assert 'data-console-absent="no_record"' in r.get_data(as_text=True), r.status_code
        base = f"/v2/onboard/console/{dev['id']}"
        form = {"list_name": "Lab", "step": "survey", "hostname": "edge1", "add": "1",
                "profile": "cisco_ios_switch"}
        assert client.get(f"{base}?list_name=Lab&step=survey&profile=cisco_ios_switch"
                          "&hostname=edge1&add=1").status_code == 200
        refused = client.post(f"{base}/survey/preview", data=dict(form, profile="nope"))
        assert refused.status_code == 409, refused.status_code
        pv = client.post(f"{base}/survey/preview", data=form)
        digest = re.search(r'name="hash" value="([0-9a-f]{64})"', pv.get_data(as_text=True))
        assert digest, pv.status_code
        consoles.append((PNP, blank_answers()))
        run = client.post(f"{base}/survey", data=dict(form, hash=digest.group(1)))
        html = run.get_data(as_text=True)
        run_id = re.search(r"run=([0-9]{8}T[0-9]{12}Z-[0-9a-f]{32})", html).group(1)
        job = re.search(r"job=([0-9a-f]{32})", html).group(1)
        assert capture_job.wait(job, 30)
        done = client.get(f"{base}?list_name=Lab&step=survey&run={run_id}&job={job}"
                          "&hostname=edge1&add=1")
        assert "factory-blank" in done.get_data(as_text=True), done.status_code
        # The kick-start, the device taken as in the network (Create's part is onboarding's).
        mp.setattr("routes.console_ztp_v2._onboarded", lambda l, h: "")
        kick = {"list_name": "Lab", "step": "kickstart", "hostname": "edge1",
                "param_interface": "GigabitEthernet0/1", "param_vlan": "10"}
        assert client.get(f"{base}?list_name=Lab&step=kickstart").status_code == 200
        pv = client.post(f"{base}/kickstart/preview", data=kick)
        digest = re.search(r'name="hash" value="([0-9a-f]{64})"', pv.get_data(as_text=True))
        assert digest, pv.status_code
        lines = V.render_kickstart(P.load("cisco_ios_switch"),
                                   {"hostname": "edge1", "interface": "GigabitEthernet0/1",
                                    "vlan": "10", **PLANNED})
        consoles.append((b"", kick_answers(lines)))
        run = client.post(f"{base}/kickstart", data=dict(kick, hash=digest.group(1)))
        html = run.get_data(as_text=True)
        run_id = re.search(r"run=([0-9]{8}T[0-9]{12}Z-[0-9a-f]{32})", html).group(1)
        job = re.search(r"job=([0-9a-f]{32})", html).group(1)
        assert capture_job.wait(job, 30)
        done = client.get(f"{base}?list_name=Lab&step=kickstart&run={run_id}&job={job}")
        assert "typed, verified" in done.get_data(as_text=True), done.status_code
        lost = client.get(f"{base}?list_name=Lab&run=20261022T000000000000Z-{'a' * 32}")
        assert lost.status_code == 200
    finally:
        mp.undo()
        server.close()


def _day_cap_confirm(client, _lab, _mp):
    """Settings › Installation, the AI card's two confirmations (the operator, 2026-10-27): a
    large increase of the day cap, and No cap with its words typed wrong. Neither writes, so
    nothing is undone."""
    from html import unescape

    from modules.ai import gateway

    before = gateway.day_cap()
    card = client.get("/v2/settings/installation/card/ai").get_data(as_text=True)
    loaded = unescape(re.search(r'name="loaded" value=\'([^\']*)\'', card).group(1))
    base = {"ai_cap_usd_per_day": str(float(before) * 100), "ai_cap_day_boundary": "UTC",
            "loaded": loaded}
    for data, code, words in ((base, 200, "A large increase"),
                              (dict(base, no_cap="on", no_cap_typed="yes"), 409,
                               "typed to confirm")):
        r = client.post("/v2/settings/installation/card/ai/save", data=data,
                        headers={"HX-Request": "true", "Accept": "text/html"})
        assert r.status_code == code and words in r.get_data(as_text=True), r.status_code
    assert gateway.day_cap() == before, "a confirmation writes nothing"


def _settings_ai(client, _lab, _mp):
    """Settings › Installation › AI (board AI3, C1843): a planted background feature with a
    measured frequency turned on for Lab through Turn on…'s form, its caps changed (refused
    over the installation's day cap, then saved), another network's switch stopped by its day
    cap (a planted refusal row) drawn under the list, and both turned off; the settings it
    changed put back. The lab reads settings from a dict (tests/test_device_v2.lab_setup), so
    the two keys this writes are read from the settings file it writes to."""
    import json as _json
    import time as _time
    from html import unescape

    import pytest

    from modules import config
    from modules import settings_schema as S
    from modules.ai import background as B
    from modules.ai import calls
    from modules.settings_schema import write_settings

    mp = pytest.MonkeyPatch()
    lab_reads = S.get_setting

    def reads(key, default=None):
        if key not in ("ai_hosted", "ai_background"):
            return lab_reads(key, default)
        try:
            with open(config.USER_SETTINGS_FILE, encoding="utf-8") as fh:
                return _json.load(fh).get(key, default)
        except (OSError, ValueError):
            return default
    mp.setattr(S, "get_setting", reads)
    before = {k: reads(k, {}) for k in ("ai_hosted", "ai_background")}
    try:
        mp.setitem(B.FEATURES, "fake_loop", {
            "task": "connection_check", "words": "The planted loop", "findings": ("detection",),
            "trigger_words": "a detection rule fires", "calls_per_finding": 1,
            "frequency": lambda network: {"per_day": 2.0, "basis": "2 a day, planted"}})
        at = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
        assert write_settings({"ai_hosted": {"by": "v2-context", "at": at,
                                             "reason": "the walk's background feature"},
                               "ai_background": {"elsewhere": {"fake_loop": {
                                   "on": True, "by": "v2-context", "at": at,
                                   "day_cap_usd": 0.0001, "month_cap_usd": 1.0}}}})["ok"]
        assert calls.record({"id": calls.new_id(), "feature": "connection_check",
                             "actor": "job:walk", "model": "m", "verdict": "feature_cap",
                             "cap_kind": "day", "cost_usd": 0.0,
                             "trigger": {"kind": "background", "feature": "fake_loop",
                                         "job": "walk", "network": "elsewhere",
                                         "finding": {"kind": "detection", "id": "d"}}}
                            )["recorded"]
        base = "/v2/settings/installation/ai/background/Lab/fake_loop"
        hx = {"HX-Request": "true", "Accept": "text/html"}
        form = unescape(client.get(f"{base}/on", headers=hx).get_data(as_text=True))
        shown = re.search(r'name="shown" value="([0-9a-f]{64})"', form).group(1)
        r = client.post(f"{base}/on", headers=hx, data={"shown": shown, "day_cap_usd": "0.50",
                                                        "month_cap_usd": "5", "accept": "on"})
        assert r.status_code == 200 and 'data-result="on"' in r.get_data(as_text=True)
        html = client.get("/v2/settings/installation?tab=ai&network=Lab").get_data(as_text=True)
        assert "was stopped by its day cap" in html, "another network's stopped feature"
        assert client.get(f"{base}/caps", headers=hx).status_code == 200
        assert client.post(f"{base}/caps", headers=hx, data={"day_cap_usd": "999",
                                                             "month_cap_usd": "5"}
                           ).status_code == 409
        assert client.post(f"{base}/caps", headers=hx, data={"day_cap_usd": "0.25",
                                                             "month_cap_usd": "5"}
                           ).status_code == 200
        assert client.post(f"{base}/off", headers=hx).status_code == 200
    finally:
        assert write_settings(before)["ok"]
        mp.undo()


def _ai_feedback(client, _lab, _mp):
    """Was this right? and the review of answers said wrong (PHASE8_PLAN 16.11 item 1, board
    FB): a planted call with its subject, another person's Yes on it, the walk's person's No
    through the control, the review card, the No's row opened (its call, the others on it, the
    draft), Accept refused on a moved draft and then accepted, and the accepted row and the
    drafts' download; in a folder of the walk's own."""
    import json
    import tempfile

    import pytest

    from modules.ai import calls, feedback

    folder = tempfile.mkdtemp(prefix="v2ctx-feedback-")
    mp = pytest.MonkeyPatch()
    mp.setattr(calls, "_path", lambda: os.path.join(folder, "ai_calls.jsonl"))
    try:
        cid = "ai-00000000000000fb"
        assert calls.record({"id": cid, "feature": "explain", "actor": "asker@example.com",
                             "model": "claude-sonnet-5-5", "prompt": "explain.v8",
                             "subject": {"pack": "ep-walk", "alert": "walk"},
                             "request": {"messages": [{"role": "user", "content": "pack"}]},
                             "response": '{"outcome": "answer", "rationale": "walk"}',
                             "verdict": "ok", "cost_usd": 0.04})["recorded"]
        with open(feedback._path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": "verdict", "id": "fb-other", "call_id": cid,
                                 "task": "explain", "verdict": "yes", "why": "", "words": "",
                                 "actor": "other@example.com", "at": "2026-10-28T10:00:00Z",
                                 "subject": {"pack": "ep-walk"}}) + "\n")
        hx = {"HX-Request": "true", "Accept": "text/html"}
        r = client.post(f"/v2/ai/feedback/answer/{cid}", headers=hx,
                        data={"verdict": "no", "why": "missed",
                              "words": "it missed the neighbour going down first"})
        assert r.status_code == 200 and "you said wrong" in unescape(r.get_data(as_text=True))
        assert client.get("/v2/ai/feedback/review", headers=hx).status_code == 200
        fb_id = next(v["id"] for v in feedback.read()["rows"]
                     if v.get("actor") != "other@example.com")
        page = unescape(client.get(f"/v2/ai/feedback/review/{fb_id}/open",
                                   headers=hx).get_data(as_text=True))
        shown = re.search(r'name="draft" value="([0-9a-f]{64})"', page).group(1)
        assert client.post(f"/v2/ai/feedback/review/{fb_id}", headers=hx,
                           data={"outcome": "accepted", "draft": "0" * 64}).status_code == 409
        assert client.post(f"/v2/ai/feedback/review/{fb_id}", headers=hx,
                           data={"outcome": "accepted", "draft": shown}).status_code == 200
        assert client.get("/v2/ai/feedback/review?status=accepted", headers=hx).status_code == 200
        assert client.get("/v2/ai/feedback/drafts/explain.json").status_code == 200
    finally:
        mp.undo()


def _assistant(client, _lab, mp):
    """The toolbar assistant's answer (card P7, stage 1): a question the manual does not cover,
    which is answered with no call (no passage chosen) and recorded as a gap, its record in the
    walk's own folder."""
    import html
    from modules.ai import assistant
    gaps = []
    mp.setattr(assistant, "record_gap", lambda *a, **k: gaps.append((a, k)) or {})
    r = client.post("/v2/assistant/ask", data={"question": "What is the capital of France?",
                                               "screen": "Devices"})
    assert r.status_code == 200 and "The manual doesn't cover this." in html.unescape(
        r.get_data(as_text=True)), r.get_data(as_text=True)[:300]
    assert len(gaps) == 1
    # An answer Mercury's check passed, with its citations, and one the passages did not
    # cover, with the nearest they hold: planted, as the model's answers are (no provider).
    link = {"link": "/v2/help/reload#the-run", "page": "Reload a device", "heading": "The run"}
    states = {
        "answered": {"ok": True, "state": "answered", "error": "", "detail": "",
                     "answer": "Open the device page, then Actions › Reload…",
                     "cites": [link], "passages": [link], "call_id": "ai-0123456789abcdef",
                     "gap": False, "typed_masked": ""},
        "not_covered": {"ok": True, "state": "not_covered", "error": "",
                        "detail": assistant.NOT_COVERED, "passages": [link],
                        "call_id": "ai-0123456789abcdef", "gap": True, "typed_masked": ""}}
    for state, got in states.items():
        mp.setattr(assistant, "answer", lambda *a, got=got, **k: dict(got))
        r = client.post("/v2/assistant/ask", data={"question": "How do I reload?",
                                                   "screen": "Devices"})
        assert r.status_code == 200 and 'href="/v2/help/reload#the-run"' in r.get_data(
            as_text=True), state


def _ai_spend(client, _lab, _mp):
    """The top bar's AI chip and its spend panel (boards AI1 and AI2, C1843) with spend to draw:
    a key, hosted AI allowed, a planted background feature on for Lab (and one for a network
    Mercury does not hold, whose Turn off is refused), today's calls by a person, an evaluation
    run and the feature; then the panel with the record unreadable, Turn off pressed in it (the
    refusal and the answer), and the settings it changed put back."""
    import json as _json
    import time as _time

    import pytest

    from modules import config, secrets_store
    from modules import settings_schema as S
    from modules.ai import background as B
    from modules.ai import calls
    from modules.nsot import listref
    from modules.settings_schema import write_settings

    mp = pytest.MonkeyPatch()
    lab_reads = S.get_setting

    def reads(key, default=None):
        if key not in ("ai_hosted", "ai_background"):
            return lab_reads(key, default)
        try:
            with open(config.USER_SETTINGS_FILE, encoding="utf-8") as fh:
                return _json.load(fh).get(key, default)
        except (OSError, ValueError):
            return default
    mp.setattr(S, "get_setting", reads)
    before = {k: reads(k, {}) for k in ("ai_hosted", "ai_background")}
    try:
        mp.setattr(secrets_store, "is_set", lambda key: key == "anthropic_api_key")
        mp.setitem(B.FEATURES, "fake_loop", {
            "task": "connection_check", "words": "The planted loop", "findings": ("detection",),
            "trigger_words": "a detection rule fires", "calls_per_finding": 1,
            "frequency": lambda network: {"per_day": 2.0, "basis": "2 a day, planted"}})
        at = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
        lab = listref.network_id("Lab")
        on = {"on": True, "by": "v2-context", "at": at, "day_cap_usd": 0.5,
              "month_cap_usd": 5.0, "estimate": {"usd_per_day": 0.02}}
        assert write_settings({"ai_hosted": {"by": "v2-context", "at": at,
                                             "reason": "the walk's spend panel"},
                               "ai_background": {lab: {"fake_loop": on},
                                                 "elsewhere": {"fake_loop": on}}})["ok"]
        for actor, trigger, cost in (
                ("operator@example.com", {"kind": "person", "by": "operator@example.com"}, 0.2),
                ("evaluation:walk-run", {"kind": "evaluation", "run": "walk-run"}, 0.05),
                ("job:walk", {"kind": "background", "feature": "fake_loop", "job": "walk",
                              "network": lab, "finding": {"kind": "detection", "id": "d"}},
                 0.01)):
            assert calls.record({"id": calls.new_id(), "feature": "connection_check",
                                 "actor": actor, "model": "m", "verdict": "ok",
                                 "cost_usd": cost, "trigger": trigger})["recorded"]
        hx = {"HX-Request": "true", "Accept": "text/html"}
        chip = client.get("/v2/ai/chip", headers=hx).get_data(as_text=True)
        assert 'data-state="on"' in chip and "2 background on" in chip, chip
        panel = client.get("/v2/ai/spend", headers=hx).get_data(as_text=True)
        # C2123: an evaluation run is counted, never listed by name (each is in History).
        assert "The planted loop" in panel and "Evaluations, 1 run" in panel
        assert "walk-run" not in panel
        real = calls.rows_since
        mp.setattr(calls, "rows_since", lambda start: {"state": "unreadable", "rows": [],
                                                       "error": "planted by the walk"})
        panel = client.get("/v2/ai/spend", headers=hx).get_data(as_text=True)
        assert "planted by the walk" in panel and "The planted loop" in panel
        mp.setattr(calls, "rows_since", real)
        off = "/v2/settings/installation/ai/background/{}/fake_loop/off?answer=panel"
        r = client.post(off.format("elsewhere"), headers=hx)
        assert r.status_code == 409 and "Not changed:" in r.get_data(as_text=True)
        r = client.post(off.format("Lab"), headers=hx)
        assert r.status_code == 200 and 'data-result="off"' in r.get_data(as_text=True)
    finally:
        assert write_settings(before)["ok"]
        mp.undo()


def _console_servers(client, _lab, _mp):
    """Settings › Installation › Console servers (O8) with a port record, a NetBox port with
    none, a key, a held host key and the store's log: the tab, each card, each change and its
    answer, and a re-key's preview and confirm (C1560; the key read is replaced, the keys real,
    generated here). Its patches are undone before the next provider."""
    import paramiko
    import pytest

    from modules import host_keys
    from modules.nsot import console_keys, console_servers

    mp = pytest.MonkeyPatch()
    try:
        _fake, _dev, sport, spare = _console_netbox(mp)
        console_keys.generate("ctx-console", username="mercury",
                              wrapper_path=console_keys.WRAPPER_PATH,
                              allowlist_path=console_keys.ALLOWLIST_PATH, replace=True)
        assert console_servers.set_port(sport["id"], {
            "driver": "command_bridge", "host": "192.0.2.60", "ssh_port": 22,
            "container": "edge-a", "credential_ref": "ctx-console"}, actor="v2-context")["ok"]
        held, now = (paramiko.RSAKey.generate(1024) for _ in range(2))
        host_keys.check("192.0.2.60", held, owner="v2-context")
        mp.setattr("modules.connection.read_host_key",
                   lambda host, **kw: host_keys.offered(now))
        tab = "/v2/settings/installation/console-servers"
        for url in ("/v2/settings/installation?tab=console", tab, f"{tab}/port/form",
                    f"{tab}/port/form?port={sport['id']}",
                    f"{tab}/port/{sport['id']}/remove/form", f"{tab}/key/form"):
            assert client.get(url).status_code == 200, url
        saved = client.post(f"{tab}/port", data={"port_id": str(spare["id"]),
                                                 "driver": "raw_tcp", "host": "2001:db8::61",
                                                 "tcp_port": "5000"})
        assert saved.status_code == 200, saved.status_code
        assert client.post(f"{tab}/port", data={"port_id": str(spare["id"]),
                                                "driver": "raw_tcp"}).status_code == 409
        assert client.post(f"{tab}/key", data={
            "ref": "ctx-console-2", "username": "mercury",
            "wrapper_path": console_keys.WRAPPER_PATH,
            "allowlist_path": console_keys.ALLOWLIST_PATH}).status_code in (200, 409)
        assert client.post(f"{tab}/port/{spare['id']}/rekey/preview").status_code == 409
        pv = client.post(f"{tab}/port/{sport['id']}/rekey/preview")
        digest = re.search(r'name="hash" value="([0-9a-f]{16})"', pv.get_data(as_text=True))
        assert digest, pv.status_code
        assert client.post(f"{tab}/port/{sport['id']}/rekey",
                           data={"hash": digest.group(1)}).status_code == 200
        assert client.post(f"{tab}/port/{spare['id']}/remove").status_code == 200
    finally:
        mp.undo()


def _oob_onboard(client, _lab, _mp):
    """The one-decision out-of-band onboarding (routes/oob_onboard_v2.py), through the real
    routes and a real run on a fake console answering as tests/test_oob_onboard.py's (Create,
    its undo, the MAC's record and SSH stood in for, as there): Add device's Address from, a
    refused review and a clean one (its program drawn), the confirm's stepper, the result, the
    run's own page, a running card read from the hold, and Devices' In progress list with the
    run held. Its patches are undone before the next provider."""
    import pytest

    from modules import config
    from modules.nsot import capture_job, console_servers, device_ops
    from modules.nsot import oob_onboard as O
    from tests.console_fakes import Console, RawServer
    from tests.test_oob_onboard import answers, facts, fake_plan, seed_link
    from tests.test_oob_onboard_v2 import ADD, QUICK

    mp = pytest.MonkeyPatch()
    consoles = []
    server = RawServer(lambda: Console(*consoles.pop(0)))
    try:
        fake, dev, sport, _spare = _console_netbox(mp)
        seed_link(fake, dev)
        from tests.oob_fake_steps import install
        install(mp)                      # Phase A's console pieces stood in at the adapter
        mp.setattr("modules.nsot.ztp_relayed.intent_everywhere", facts)
        mp.setattr(O, "_plan", fake_plan)
        mp.setattr(O, "_create", lambda *a: {"ok": True, "completed": ["commit"],
                                             "commit": "c0ffee", "reason": ""})
        mp.setattr(O, "undo_created", lambda *a: {"ok": True, "undone": [], "remaining": []})
        mp.setattr(O, "_record_mac", lambda *a: "")
        mp.setattr(O, "DEFAULT_TIMINGS", QUICK)
        mp.setattr("modules.readers.reachability.probe", lambda a: (True, "port 22 accepted"))
        mp.setattr("modules.config.list_data_path", config.get_list_data_dir)
        assert console_servers.set_port(sport["id"], {"driver": "raw_tcp", "host": server.host,
                                                      "tcp_port": server.port},
                                        actor="v2-context")["ok"]
        form = dict(ADD, list_name="Lab")
        r = client.get("/v2/onboard/oob/source?list_name=Lab&hostname=edge1"
                       "&address_source=ztp_console")
        assert '<option value="ztp_console" selected>' in r.get_data(as_text=True)
        refused = client.post("/v2/onboard/preview", data=dict(form, role="router"))
        assert refused.status_code == 409, refused.status_code
        pv = client.post("/v2/onboard/preview", data=form)
        digest = re.search(r'name="hash" value="([0-9a-f]{64})"', pv.get_data(as_text=True))
        assert digest, pv.status_code
        consoles.append((b"", answers()))
        run = client.post("/v2/onboard/oob/confirm", data=dict(
            {k: form[k] for k in O.FORM_FIELDS + O.ASKED_FIELDS}, add="1",
            hash=digest.group(1), reason="a new access switch"))
        html = run.get_data(as_text=True)
        run_id = re.search(r"run=([0-9]{8}T[0-9]{12}Z-[0-9a-f]{32})", html).group(1)
        job = re.search(r"job=([0-9a-f]{32})", html).group(1)
        assert capture_job.wait(job, 30)
        done = client.get(f"/v2/onboard/oob/card?list_name=Lab&run={run_id}&job={job}"
                          "&hostname=edge1")
        assert "ready to Verify" in done.get_data(as_text=True), done.status_code
        assert client.get("/v2/onboard/oob/run?list=Lab&device=edge1").status_code == 200
        # Devices' In progress list: the run held in Lab, and a second network whose holds
        # cannot be read (said, never drawn as nothing running).
        real = device_ops.in_flight

        def in_flight(name, now=None):
            if name == "Unreadable":
                raise device_ops.HoldsUnreadable("/holds/Unreadable", OSError("denied"))
            return real(name, now)

        mp.setattr("modules.integration_groups.network_names", lambda: ["Lab", "Unreadable"])
        mp.setattr(device_ops, "in_flight", in_flight)
        with device_ops.hold("Lab", "edge1", O.OP, "v2-context"):
            device_ops.note("onboard: answering")
            assert client.get(f"/v2/onboard/oob/card?list_name=Lab&run={run_id}"
                              "&hostname=edge1").status_code == 200
            panel = client.get("/operations/in_flight?view=panel",
                               headers={"HX-Request": "true"}).get_data(as_text=True)
            assert "Open its stepper" in panel and "Could not read what runs in" in panel
    finally:
        mp.undo()
        server.close()


def _sdn_apps(client, _lab, _mp):
    """SDN › Apps (P6, board controller-app-deploy) on Lab, through `deploy_op.Sources` faked at
    its seam (tests/test_controller_deploy_op.py's `FakeSources`, a real code repository with
    two Published versions): the tab at rest with no record, a refused preview, a first deploy
    confirmed (its running card, then its result), the controller as recorded and an app's
    page, a plan that changes nothing, drift, the receipt and its download. Its patches are
    undone before the next provider."""
    import re
    import tempfile
    from html import unescape
    from pathlib import Path

    import pytest

    from modules import controller_deploy_receipts as deploy_receipts
    from modules.apps import channel, deploy_op
    from modules.nsot import capture_job
    from tests.test_controller_deploy_op import ALL_BACK_TWO, HEADER, FakeSources
    from tests.test_sdn_apps_v2 import as_recorded

    import shutil

    mp = pytest.MonkeyPatch()
    root = tempfile.mkdtemp(prefix="v2ctx-apps-")
    src = FakeSources(Path(root))
    mp.setattr(deploy_op, "SOURCES", src)
    try:
        mp.setattr("tests.test_sdn_apps_v2.NET", "Lab")
        assert client.get("/v2/sdn/apps?list=Lab").status_code == 200
        form = {"list": "Lab", "controller": "ctl", "set": "of_versions=1.0.0"}
        assert client.post("/v2/sdn/apps/preview", data=dict(form, set="nope")).status_code == 400
        # A preview whose app compiles its start-time config (C2760): its config and the
        # basis of each switch's tables drawn.
        from tests.test_app_compile import HP, OVS, CompiledSources

        mp.setattr(deploy_op, "SOURCES", CompiledSources(Path(root) / "compiled", [HP, OVS]))
        assert "start-time config, staged to" in client.post(
            "/v2/sdn/apps/preview", data=dict(form, set="quirky=1.0.0")).get_data(as_text=True)
        mp.setattr(deploy_op, "SOURCES", src)
        html = client.post("/v2/sdn/apps/preview", data=form).get_data(as_text=True)
        fields = {m.group(1): unescape(m.group(2)) for m in re.finditer(
            r'<input type="hidden" name="([a-z]+)" value="([^"]*)"', html)}
        src.reads = [ALL_BACK_TWO]
        r = client.post("/v2/sdn/apps/confirm", data={k: fields[k] for k in (
            "list", "controller", "set", "hash", "parts")})
        job = re.search(r"/v2/sdn/apps/run/([0-9a-f]+)", r.get_data(as_text=True)).group(1)
        assert capture_job.wait(job, 60)
        assert "Deployed" in client.get(f"/v2/sdn/apps/run/{job}").get_data(as_text=True)
        as_recorded(src)
        for url in ("/v2/sdn/apps?list=Lab",
                    "/v2/sdn/apps?list=Lab&app=of_versions&controller=ctl",
                    "/v2/sdn/view?list=Lab&tab=apps&app=of_versions&controller=ctl&v=1.1.0"):
            assert client.get(url).status_code == 200
        rid = deploy_receipts.read("Lab")["rows"][0]["id"]
        assert client.get(f"/v2/sdn/apps?list=Lab&receipt={rid}").status_code == 200
        assert client.get(f"/v2/sdn/apps/receipt/{rid}.json?list=Lab").status_code == 200
        rec = deploy_receipts.record("Lab", "ctl")
        src.cat = (f"{HEADER}\n" + channel.render_dropin(rec["request"],
                                                         "/opt/ryu-venv/bin/ryu-manager"))
        assert "Nothing to deploy" in client.post("/v2/sdn/apps/preview", data=form)\
            .get_data(as_text=True)
        src.controller_read = lambda n, c: {"state": "ok", "at": "2026-11-08T05:00:00Z",
                                            "show": "User=ryu\n", "cat": "", "health": {},
                                            "observed": None, "error": ""}
        assert client.get("/v2/sdn/apps?list=Lab").status_code == 200
        as_recorded(src)
        recorded = src.controller_read
        src.controller_read = lambda n, c: dict(recorded(n, c),
                                                cat=f"{HEADER}\n[Service]\nUser=ryu\n")
        assert "differs from Mercury" in client.get("/v2/sdn/apps?list=Lab")\
            .get_data(as_text=True)
    finally:
        mp.undo()
        shutil.rmtree(root, ignore_errors=True)


def _nsot_export_and_code_repo(client, _lab, _mp):
    """SDN › Apps' NSOT export card (C2777, board nsot-export) and Settings › Network's Code
    repository card (board code-repository) on Lab: the export none committed, its preview
    (every object added), its commit, the card at rest committed, a preview that changes
    nothing and a refused confirm; a code repository with one app and one folder that does not
    register, saved, fetched and drawn. NetBox's GETs are served by tests/test_openflow_golden's
    fake client. Its patches are undone before the next provider."""
    import copy
    import os
    import re
    import shutil
    import subprocess
    import tempfile
    from html import unescape

    import pytest

    from modules.nsot import export as X
    from tests.test_coderepo import GIT_ENV, manifest
    from tests.test_openflow_golden import _records, fake_netbox

    mp = pytest.MonkeyPatch()
    root = tempfile.mkdtemp(prefix="v2ctx-export-")
    records = copy.deepcopy(_records())
    real = X.build
    try:
        mp.setattr("modules.inventory.source_config.load",
                   lambda name: {"source": "netbox", "filters": {"role": "openflow-switch"}})
        mp.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        mp.setattr(X, "build", lambda network, **kw: real(
            network, get=fake_netbox(records)[0], version=lambda: records["netbox_version"]))
        assert client.get("/v2/sdn/apps?list=Lab").status_code == 200
        html = client.post("/v2/sdn/export/preview", data={"list": "Lab"}).get_data(as_text=True)
        fields = {m.group(1): unescape(m.group(2)) for m in re.finditer(
            r'<input type="hidden" name="([a-z_0-9]+)" value="([^"]*)"', html)}
        assert client.post("/v2/sdn/export/confirm", data={k: fields[k] for k in (
            "list", "hash", "sha256", "base_blob")}).status_code == 200
        assert client.get("/v2/sdn/export?list=Lab").status_code == 200
        assert "nothing to commit" in client.post("/v2/sdn/export/preview",
                                                  data={"list": "Lab"}).get_data(as_text=True)
        assert client.post("/v2/sdn/export/confirm", data={
            "list": "Lab", "hash": "0" * 64, "sha256": fields["sha256"],
            "base_blob": ""}).status_code == 409
        # A code repository with one app and a folder that does not register.
        code = os.path.join(root, "code")
        os.makedirs(os.path.join(code, "apps", "of_versions"))
        os.makedirs(os.path.join(code, "apps", "loose"))
        with open(os.path.join(code, "apps", "of_versions", "manifest.yml"), "w") as fh:
            fh.write(manifest("of_versions", "1.0.0"))
        with open(os.path.join(code, "apps", "loose", "x.py"), "w") as fh:
            fh.write("x = 1\n")
        env = dict(os.environ, **GIT_ENV)
        for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "a")):
            subprocess.run(["git", "-C", code, *args], check=True, capture_output=True, env=env)
        assert client.post("/v2/settings/network/Lab/code-repository",
                           data={"location": code, "branch": "", "loaded": "\n"}
                           ).status_code == 200
        assert "Fetched commit" in client.post("/v2/settings/network/Lab/code-repository/fetch")\
            .get_data(as_text=True)
        assert client.get("/v2/settings/network/Lab?tab=network").status_code == 200
        assert client.get("/v2/sdn/apps?list=Lab").status_code == 200
        # C2854 (board app-publish): Run its tests (failing, then passing; the harness faked at
        # its seam), a refused preview, the preview, its confirm, and Who may publish.
        from modules.apps import channel, publish_op, test_run
        passing = {"ok": False}

        def fake_run(folder, python, *, tests, timeout_s, runner=None):
            sha = channel.script().folder_hash(folder)
            return {"ok": passing["ok"], "passed": 1, "failed": 0 if passing["ok"] else 1,
                    "errors": 0, "skipped": 0, "python": python, "content_sha256": sha,
                    "output": "1 failed" if not passing["ok"] else "1 passed", "error": ""}
        mp.setattr(test_run, "run", fake_run)
        mp.setattr(publish_op, "_python", lambda network: ("3.5", "recorded"))
        with open(os.path.join(code, "apps", "of_versions", "manifest.yml"), "a") as fh:
            fh.write("tests:\n  - tests/test_x.py\n")
        for args in (("add", "-A"), ("commit", "-q", "-m", "b")):
            subprocess.run(["git", "-C", code, *args], check=True, capture_output=True, env=env)
        client.post("/v2/settings/network/Lab/code-repository/fetch")
        form = {"list": "Lab", "app": "of_versions", "version": "1.0.0"}
        assert client.post("/v2/sdn/apps/version/test", data=form).status_code == 409
        passing["ok"] = True
        assert client.post("/v2/sdn/apps/version/test", data=form).status_code == 200
        assert client.post("/v2/sdn/apps/version/publish/preview",
                           data=dict(form, version="9.9.9")).status_code == 409
        html = client.post("/v2/sdn/apps/version/publish/preview", data=form).get_data(
            as_text=True)
        hash_ = re.search(r'name="hash" value="([0-9a-f]{64})"', html).group(1)
        assert client.post("/v2/sdn/apps/version/publish/confirm",
                           data=dict(form, hash=hash_, reason="read it")).status_code == 200
        assert client.post("/v2/settings/network/Lab/code-review",
                           data={"review": "self_recorded", "loaded_review": "another_person"}
                           ).status_code == 200
        assert client.get("/v2/settings/network/Lab?tab=network").status_code == 200
        assert client.post("/v2/settings/network/Lab/code-review",
                           data={"review": "another_person", "loaded_review": "self_recorded"}
                           ).status_code == 200
        # The operator's decision of 2026-11-10 (board authoring-from-words F): Add an app as a
        # Draft… on a bare copy of the code repository (a push lands only where no branch is
        # checked out): at rest, the picker, a refused preview (the folder is there), the
        # preview, its confirm (added and registered), a stale confirm refused.
        from tests.test_draft_write import draft, hidden, upload
        bare = os.path.join(root, "code.git")
        subprocess.run(["git", "clone", "-q", "--bare", code, bare], check=True,
                       capture_output=True, env=env)
        assert client.post("/v2/settings/network/Lab/code-repository",
                           data={"location": bare, "branch": "main", "loaded": f"{code}\n"}
                           ).status_code == 200
        assert client.get("/v2/sdn/apps?list=Lab").status_code == 200
        assert client.get("/v2/sdn/apps/draft?list=Lab&open=form").status_code == 200
        assert client.get("/v2/sdn/apps/draft?list=Lab").status_code == 200
        mp.setattr("tests.test_draft_write.NET", "Lab")
        assert upload(client, draft("of_versions", "2.0.0"), "of_versions").status_code == 409
        f = hidden(upload(client).get_data(as_text=True))
        draft_form = {"list": "Lab", "name": "dhcp_watch", "hash": f["hash"][0],
                      "base": f["base"][0], "files_sha": f["files_sha"][0], "path": f["path"],
                      "content": f["content"]}
        assert client.post("/v2/sdn/apps/draft/confirm", data=draft_form).status_code == 200
        assert client.post("/v2/sdn/apps/draft/confirm", data=draft_form).status_code == 409
        assert client.post("/v2/settings/network/Lab/code-repository",
                           data={"location": "", "branch": "", "loaded": f"{bare}\nmain"}
                           ).status_code == 200
    finally:
        mp.undo()
        shutil.rmtree(root, ignore_errors=True)


def _sdn(client, _lab, _mp):
    """SDN › Controllers and Flows and Settings' SDN controllers card (PHASE8_PLAN 17.1 S11),
    on Lab with one Ryu connection answered by Ryu 4.34's captured answers through the real
    driver (tests/test_sdn_v2.py's `Captured`), its flow intent recorded as that test records
    it, and the SDN reader run: connected, then L2-only flows (the granularity note), then not
    answering; the card's Edit, Remove…, Test (answered, and not), a refused Save, and the
    removal. Its patches are undone and the connection removed before the next provider."""
    import json

    import pytest

    from modules.sdn import connections as C
    from modules.sdn import drivers
    from modules.sdn import flow_intent as F
    from tests.test_sdn_ryu import LIMIT, V6_DROP
    from tests.test_sdn_v2 import BASE, WITH_PEER, Captured, Down, T0, store_read

    mp = pytest.MonkeyPatch()
    session = {"now": Captured()}
    real = drivers.make
    try:
        mp.setattr(drivers, "make", lambda kind, connection, **kw: real(
            kind, connection, **dict(kw, session=session["now"])))
        C.save_connection("Lab", {"name": "lab-controller", "kind": "ryu", "url": BASE,
                                  "southbound": "192.0.2.10:6653"}, actor="v2-context")
        for spec in (LIMIT, V6_DROP):
            F.record_installed("Lab", connection="lab-controller", flow=dict(spec, dpid=1),
                               actor="v2-context", response={"id": "resp-1", "action": "x"},
                               at=T0)
        assert "Not read yet" in client.get("/v2/sdn?list=Lab").get_data(as_text=True)
        store_read("Lab")
        for url in ("/v2/sdn?list=Lab", "/v2/sdn/flows?list=Lab",
                    "/v2/sdn/flows?list=Lab&own=show", "/v2/sdn/flows?list=Lab&q=METER",
                    "/v2/sdn/view?list=Lab&tab=flows&q=no-such-flow"):
            assert client.get(url).status_code == 200, url
        flows = json.loads(next(e for e in WITH_PEER if e["path"] == "/stats/flow/1")["body"])
        session["now"] = Captured(flows=[f for f in flows["1"]
                                         if not set(f["match"]) - {"in_port", "dl_dst",
                                                                    "dl_src"}])
        store_read("Lab", clock=lambda: T0 + 40)
        assert "match L2 only" in client.get("/v2/sdn/flows?list=Lab").get_data(as_text=True)
        session["now"] = Down()
        store_read("Lab", clock=lambda: T0 + 70)
        assert "Not answering since" in client.get("/v2/sdn?list=Lab").get_data(as_text=True)
        assert client.post("/v2/sdn/controller/lab-controller/test?list=Lab").status_code == 200
        session["now"] = Captured()
        card = "/v2/settings/network/Lab/sdn"
        for url in ("/v2/settings/network/Lab", card, f"{card}/edit/lab-controller",
                    f"{card}/lab-controller/remove"):
            assert client.get(url).status_code == 200, url
        form = {"name": "branch-ctl", "kind": "ryu", "url": BASE, "verify_tls": "on",
                "southbound": "", "own_cookies": "0", "loaded": "{}"}
        assert "Answered" in client.post(f"{card}/test", data=form).get_data(as_text=True)
        assert client.post(f"{card}/lab-controller/test").status_code == 200
        assert client.post(f"{card}/save", data=form).status_code == 409
        # C2009: the network's stage, refused without a reason, then marked lab (which the
        # Responses tab's Turn AUTO on below needs).
        assert client.get("/v2/sdn/responses?list=Lab").status_code == 200
        assert client.post(f"{card}/stage", data={"stage": "lab", "reason": "",
                                                  "loaded": ""}).status_code == 409
        assert "Marked Lab lab" in client.post(f"{card}/stage", data={
            "stage": "lab", "reason": "the lab's own network", "loaded": ""}).get_data(as_text=True)
        session["now"] = Down()
        assert "Couldn't connect" in client.post(f"{card}/test", data=form)\
            .get_data(as_text=True)
        _sdn_operations(client, mp, session)
        assert client.post(f"{card}/lab-controller/remove").status_code == 200
    finally:
        mp.undo()


def _sdn_operations(client, mp, session):
    """SDN's operations (PHASE8_PLAN 17.1 S8 to S10, S16) on Lab's connection, over
    `tests.sdn_fakes.FakeRyu` seeded with Ryu's captured table: the editor's form, preview and
    confirm (a verified result), a refused preview, the Responses tab with a response awaiting a
    person and a log line, its preview and confirm, a dismissal, AUTO on and off, and the loop
    started and stopped (its pass replaced, so no thread reads a controller)."""
    import html
    import re

    from modules.sdn import loop as LP
    from tests.sdn_fakes import FakeRyu
    from tests.test_sdn_flow_ops import captured_table
    from tests.test_sdn_v2 import BASE

    session["now"] = FakeRyu(BASE, flows={1: captured_table()})
    mp.setattr("modules.sdn.flow_ops.COUNTER_INTERVAL", 0)
    mp.setattr(LP, "run_pass", lambda network, **kw: None)

    def fields(text):
        return {m.group(1): html.unescape(m.group(2)) for m in re.finditer(
            r'<input type="hidden" name="([a-z]+)" value="([^"]*)"', text)}

    sw = "0000000000000001"
    assert client.get(f"/v2/sdn/flow/form?list=Lab&do=add&connection=lab-controller&dpid={sw}"
                      ).status_code == 200
    preview = client.post("/v2/sdn/flow/preview", data={
        "list": "Lab", "do": "add", "connection": "lab-controller", "dpid": sw,
        "priority": "250", "hard_timeout": "60", "match": "eth_type=0x0800, ipv4_src=198.51.100.9",
        "actions": "drop"}).get_data(as_text=True)
    assert "Done, verified" in client.post("/v2/sdn/flow/confirm", data=fields(preview))\
        .get_data(as_text=True)
    assert client.post("/v2/sdn/flow/preview", data={
        "list": "Lab", "do": "add", "connection": "lab-controller", "dpid": sw,
        "priority": "250", "match": "tcp_dst=22", "actions": "drop"}).status_code == 409
    # The table-miss flow's removal, previewed: its warnings and the typed words (not sent).
    warned = client.post("/v2/sdn/flow/preview", data={
        "list": "Lab", "do": "remove", "connection": "lab-controller", "dpid": sw,
        "target": '{"table_id": 0, "priority": 0, "match": {}, "cookie": 0}'})
    assert "remove table-miss" in warned.get_data(as_text=True)
    # A write the switch does not apply: Verify fails and the rollback is drawn.
    session["now"].ignore = {"/stats/flowentry/add"}
    preview = client.post("/v2/sdn/flow/preview", data={
        "list": "Lab", "do": "add", "connection": "lab-controller", "dpid": sw,
        "priority": "251", "match": "eth_type=0x86dd, ipv6_src=2001:db8::9",
        "actions": "drop"}).get_data(as_text=True)
    assert "Rolled back" in client.post("/v2/sdn/flow/confirm", data=fields(preview))\
        .get_data(as_text=True)
    session["now"].ignore = set()
    d = {"key": "k-ctx", "rule": "scan", "title": "SDN scan", "network": "Lab",
         "connection": "lab-controller", "dpid": 1, "dpid_hex": sw, "source": "192.0.2.1",
         "targets": ["192.0.2.2"], "confidence": "high", "words": "192.0.2.1 reached 25 ports"}
    row = LP.propose("Lab", d, "drop_source", "low", why="HITL")
    # C1999: the flood an incident seen on two switches, its response proposed at the ingress
    # and the other switch seen also, so the incident's detail draws its seen-also list.
    from modules.sdn import incidents
    flood = dict(d, key="k-ctx-2", rule="flood")
    other = LP.propose("Lab", flood, "rate_limit_source", "low", why="HITL", incident={
        "key": incidents.group_key(flood), "rule": "flood", "source": "192.0.2.1",
        "window_s": 30, "window_setting": "sdn_flood_window_seconds",
        "window_words": "within 30 s, the flood rule's own window (sdn_flood_window_seconds)",
        "ingress_known": True, "ingress_port": 1,
        "ingress_words": f"the ingress switch is {sw}: the controller's topology lists "
                         "192.0.2.1's host on its port 1",
        "seen_also": [incidents.brief(dict(flood, key="k-ctx-3", dpid=2,
                                           dpid_hex="0000000000000002", port=3))]})
    # S-HR (C2238): a High packet rate watched, seen also on a second switch, and the flood
    # above marked as begun as one, so the watching row, its seen-also list and the flood's
    # "began as" draw.
    rate = dict(d, key="k-ctx-5", rule="high_rate", title="SDN high packet rate", port=2,
                confidence="lower", confidence_why="flows match only Ethernet fields",
                measurement={"what": "packets received a second", "value": 1240.0,
                             "unit": "pps"},
                threshold={"what": "the high packet rate threshold", "value": 100,
                           "unit": "pps", "setting": "sdn_scan_fallback_pps"})
    watch = LP.watch("Lab", rate, {
        "key": incidents.group_key(rate), "rule": "high_rate", "source": "192.0.2.1",
        "window_s": 30, "window_setting": "sdn_flood_window_seconds",
        "window_words": incidents.window("high_rate", {"sdn_flood_window_seconds": 30})["words"],
        "seen_also": [incidents.brief(dict(rate, key="k-ctx-6", dpid=2,
                                           dpid_hex="0000000000000002", port=3))]})
    LP.began("Lab", other["id"], watch)
    LP.say("Lab", "detect", "a scan from 192.0.2.1 on " + sw)
    assert "2 awaiting approval</strong> · 1 watching" in client.get(
        "/v2/sdn/responses?list=Lab").get_data(as_text=True)
    card = client.post(f"/v2/sdn/response/{row['id']}/preview",
                       data={"list": "Lab", "hard_timeout": "90"}).get_data(as_text=True)
    assert "Done, verified" in client.post("/v2/sdn/response/confirm", data=fields(card))\
        .get_data(as_text=True)
    assert client.post(f"/v2/sdn/response/{other['id']}/dismiss",
                       data={"list": "Lab", "reason": "the lab's own test"}).status_code == 200
    assert client.post(f"/v2/sdn/response/{watch['id']}/dismiss",
                       data={"list": "Lab", "reason": "the lab's own iperf"}).status_code == 200
    _sdn_reapply(client, session, d, fields)
    _sdn_picker(client, d)
    # The response policy (objective 3.1): one refused (an action that does not answer its
    # rule), one saved and the region drawn again with it.
    page = client.get("/v2/sdn/responses?list=Lab").get_data(as_text=True)
    loaded = html.unescape(re.search(r'name="loaded" value="([^"]*)"', page).group(1))
    policy = {"list": "Lab", "loaded": loaded, "scan_default": "rate_limit_source",
              "flood_default": "rate_limit_source", "flood_allowed": "drop_source",
              "unauthorised_flow_default": "remove_flow"}
    assert client.post("/v2/sdn/policy", data=dict(policy, scan_default="remove_flow"))\
        .status_code == 409
    assert client.post("/v2/sdn/policy", data=policy).status_code == 200
    assert client.post("/v2/sdn/mode", data={"list": "Lab", "mode": "auto", "reason": "lab run",
                                             "hours": "1", "risk": "low"}).status_code == 200
    assert client.post("/v2/sdn/mode", data={"list": "Lab", "mode": "hitl"}).status_code == 200
    assert client.post("/v2/sdn/loop", data={"list": "Lab", "run": "start",
                                             "interval": "10"}).status_code == 200
    assert client.post("/v2/sdn/loop", data={"list": "Lab", "run": "stop"}).status_code == 200
    LP._jobs["Lab"]["thread"].join(10)


def _sdn_picker(client, d):
    """C2002: a flood on a port whose flows named no source, two hosts the controller's topology
    lists there (IPv4 and IPv6), as `detect.port_source` keeps them: the card's source picker
    drawn, limited to them, and a preview with one chosen."""
    from modules.sdn import loop as LP

    hosts = [{"mac": "00:00:00:00:00:02", "address": "192.0.2.2"},
             {"mac": "00:00:00:00:00:05", "address": "2001:db8:8::5"}]
    flood = dict(d, key="k-ctx-pick", rule="flood", title="SDN flood", source=None, sources=[],
                 port=2, subject={"kind": "port", "value": 2}, source_from={
                     "how": "topology", "state": "several", "port": 2, "hosts": hosts,
                     "read_at": "2026-10-27T09:35:49Z",
                     "words": "not named: the controller's topology lists 2 hosts on port 2 "
                              "(192.0.2.2 (00:00:00:00:00:02), 2001:db8:8::5 "
                              "(00:00:00:00:00:05))"})
    row = LP.propose("Lab", flood, "drop_source", "low", why="HITL")
    page = client.get(f"/v2/sdn/responses?list=Lab&incident={row['id']}").get_data(as_text=True)
    assert '<select name="source"' in page and ">2001:db8:8::5 (00:00:00:00:00:05)<" in page
    card = client.post(f"/v2/sdn/response/{row['id']}/preview",
                       data={"list": "Lab", "source": "2001:db8:8::5", "hard_timeout": "60"})\
        .get_data(as_text=True)
    assert "chosen from the 2 hosts" in card, card


def _sdn_reapply(client, session, d, fields):
    """A lost response put back (C2018): a drop applied for 600 s, its switch restarted (a
    fresh `tests.test_sdn_reapply.Switch` holding the capture alone), the SDN reader run, then
    Flows' Re-apply… on the switch, its preview and its confirm."""
    import re
    import time

    from modules.sdn import loop as LP
    from tests.test_sdn_flow_ops import captured_table
    from tests.test_sdn_reapply import Switch
    from tests.test_sdn_v2 import BASE, store_read

    row = LP.propose("Lab", dict(d, key="k-ctx-3", source="192.0.2.7"), "drop_source", "low",
                     why="HITL")
    card = client.post(f"/v2/sdn/response/{row['id']}/preview",
                       data={"list": "Lab", "hard_timeout": "600"}).get_data(as_text=True)
    assert "Done, verified" in client.post("/v2/sdn/response/confirm", data=fields(card))\
        .get_data(as_text=True)
    session["now"] = Switch(BASE, flows={1: captured_table()})
    store_read("Lab", clock=time.time)
    page = client.get("/v2/sdn/flows?list=Lab").get_data(as_text=True)
    lost = re.search(r'<form class="sdn-lost".*?</form>', page, re.S).group(0)
    card = client.post("/v2/sdn/reapply/preview", data=fields(lost)).get_data(as_text=True)
    assert "Re-apply: " in card, card
    assert "Done, verified" in client.post("/v2/sdn/reapply/confirm", data=fields(card))\
        .get_data(as_text=True)
    # C2077: lost again in a second restart, then the scan answered again (a newer drop of the
    # same source, confirmed by a person): Flows draws the lost one answered, naming it.
    session["now"] = Switch(BASE, flows={1: captured_table()})
    newer = LP.propose("Lab", dict(d, key="k-ctx-4", source="192.0.2.7"), "drop_source", "low",
                       why="HITL")
    card = client.post(f"/v2/sdn/response/{newer['id']}/preview",
                       data={"list": "Lab", "hard_timeout": "600"}).get_data(as_text=True)
    assert "Done, verified" in client.post("/v2/sdn/response/confirm", data=fields(card))\
        .get_data(as_text=True)
    store_read("Lab", clock=time.time)
    page = client.get("/v2/sdn/flows?list=Lab").get_data(as_text=True)
    assert 'class="small sdn-answered"' in page and newer["id"] in page, \
        "the lost drop drawn answered by the newer one"


def _sdn_no_topology(client, _lab, _mp):
    """SDN › Controllers' capabilities a driver lacks (`c.caps.lacks`): since S14 the one built
    driver, Ryu, declares every capability, so a connection's card is drawn once with Ryu's
    declaration less read_topology (its own words for why), the planted case of a built
    driver that lacks one. Patches undone, the connection removed."""
    import pytest

    from modules.sdn import connections as C
    from modules.sdn import drivers
    from modules.sdn.drivers.ryu import RyuDriver
    from tests.test_sdn_v2 import BASE, T0, Captured, store_read

    mp = pytest.MonkeyPatch()
    real = drivers.make
    try:
        mp.setattr(RyuDriver, "capabilities", RyuDriver.capabilities - {"read_topology"})
        mp.setattr(RyuDriver, "absent", {"read_topology": "planted: no topology application"})
        mp.setattr(drivers, "make", lambda kind, connection, **kw: real(
            kind, connection, **dict(kw, session=Captured())))
        C.save_connection("Lab", {"name": "lab-controller", "kind": "ryu", "url": BASE},
                          actor="v2-context")
        # After _sdn's last read (T0 + 70), so this read is the one stored.
        store_read("Lab", clock=lambda: T0 + 100)
        html = client.get("/v2/sdn?list=Lab").get_data(as_text=True)
        assert "read topology: not offered by this driver" in html
        # C2325: a network with none names the networks that have one. The walk's lab is one
        # network, so for this one request Lab is read as having none and `elsewhere` names it
        # (its link then resolves); tests/test_sdn_v2.py holds the two real networks' case.
        real_conns, real_else = C.connections, C.elsewhere
        mp.setattr(C, "connections", lambda n: dict(real_conns(n), state="none",
                                                    connections=[]))
        mp.setattr(C, "elsewhere", lambda n: ["Lab"])
        other = client.get("/v2/sdn?list=Lab").get_data(as_text=True)
        mp.setattr(C, "connections", real_conns)
        mp.setattr(C, "elsewhere", real_else)
        assert "Open Lab's SDN" in other, "the network with a controller is not named"
        assert client.post("/v2/settings/network/Lab/sdn/lab-controller/remove").status_code \
            == 200
    finally:
        mp.undo()


def _sdn_trace(client, _lab, _mp):
    """Topology › Path… on the Flow tables layer (board D, docs/boards/sdn-trace.html; C2578):
    Lab's Topology drawn from tests/test_sdn_trace_v2.py's `topology_value()` (the captured
    network with its controller layer), the SDN reader's store answering the captured fabric
    (`fresh()`): the form with its suggestions, IPv6 TCP delivered with every hop's pipeline,
    an address listed at two places (each MAC offered), an end host named from the NSOT export,
    and the nine-switch flooded chain (`chain_fabric`: the folded middle, the summary and the
    groups). The Topology store it replaced is put back; patches undone."""
    import pytest

    from modules import reader_job
    from modules.sdn import trace as TR
    from tests import test_sdn_trace_v2 as V
    from tests.test_sdn_trace import _twice
    from tests.test_topology_v2 import _store

    mp = pytest.MonkeyPatch()
    path = reader_job.store_path("topology-graph")
    before = None
    if os.path.exists(path):
        with open(path, "rb") as fh:
            before = fh.read()
    try:
        _store(V.topology_value())
        box = {"store": V.fresh(), "asked": []}
        V.answering(mp, box)
        q = "/v2/topology/map?list=Lab&layer=of"
        assert "Trace the path" in client.get("/v2/topology?list=Lab&layer=of").get_data(
            as_text=True)
        html = client.get(f"{q}&src=2001:db8:8::1&dst=2001:db8:8::3&proto=tcp&dport=80")\
            .get_data(as_text=True)
        assert "delivered through 2 switches" in html
        box["store"] = V.fresh(topo_edit=_twice("192.0.2.3"))
        assert "Trace to " in client.get(f"{q}&src=192.0.2.1&dst=192.0.2.3").get_data(
            as_text=True)
        box["store"] = V.fresh()
        mp.setattr("modules.nsot.export.read", lambda network: V._export(V.H1_EXPORT))
        assert "end hosts, in the NSOT export" in client.get(f"{q}&src=h1&dst=192.0.2.3").get_data(
            as_text=True)
        mp.setattr(TR, "fabric", lambda network, cached=None, now=None: V.chain_fabric(9))
        assert "Hops 3 to 7" in client.get(f"{q}&src=192.0.2.1&dst=192.0.2.3").get_data(
            as_text=True)
    finally:
        mp.undo()
        if before is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            with open(path, "wb") as fh:
                fh.write(before)


def _sdn_analyse(client, _lab, _mp):
    """SDN › Flows' Analyse this network (Lab 9 B1, board I): Lab's connection over the lab's
    recorded Ryu (tests/test_sdn_analyst.py's `LabRyu`), a snapshot collected and kept, two
    planted issues, then an analysis whose answer (the gateway's, planted at its call) keeps one
    finding, drops one citing nothing, and leaves one planted issue found and one missed; the
    page and the region drawn. Its patches undone, its folder and the connection removed."""
    import json
    import shutil

    import pytest

    from modules.ai import gateway, triggers
    from modules.sdn import analyst as AN
    from modules.sdn import closed_loop as CL
    from modules.sdn import connections as C
    from tests.ai_person import pressed_by
    from tests.fixtures.sdn.ryu_recorded import BASE_URL
    from tests.test_sdn_analyst import OVS3, LabRyu

    mp = pytest.MonkeyPatch()
    try:
        assert C.save_connection("Lab", {"name": "lab-analyse", "kind": "ryu", "url": BASE_URL},
                                 actor="v2-context")["ok"]
        session = LabRyu()
        got = CL.collect_threat_data(
            "Lab", 1.0, sleep=lambda s: None, links=True,
            driver=lambda net, name: C.driver_for(net, name, session=session))
        snap = AN.build_snapshot("Lab", got, by="v2-context")
        AN.save_snapshot("Lab", snap)
        port = f"port:lab-analyse:{OVS3}:3"
        assert AN.add_planted("Lab", "OVS 3's port 3 pulled", port, actor="v2-context")["ok"]
        assert AN.add_planted("Lab", "A stale drop", f"drop:lab-analyse:{OVS3}:*",
                              why="its count is zero", actor="v2-context")["ok"]
        output = AN.NetworkAnalysis.model_validate_json(json.dumps({"findings": [
            {"severity": "high", "finding": "Port 3 on 0000000000000003 is down",
             "why": "The switch reports LINK_DOWN.", "evidence": [port, "port:made:up"]},
            {"severity": "low", "finding": "A claim citing nothing", "why": "w",
             "evidence": []}]}))
        mp.setattr(gateway, "ask", lambda *a, **k: {"ok": True, "output": output,
                                                    "call_id": "c-v2-context-analyse",
                                                    "cost_usd": 0.0021})
        with pressed_by("v2-context@example.com"):
            r = AN.analyse("Lab", snap["id"], actor="v2-context@example.com",
                           trigger=triggers.person("v2-context@example.com"))
        assert r["ok"] and r["dropped"] == 1
        html = client.get("/v2/sdn/flows?list=Lab").get_data(as_text=True)
        assert "Port 3 on 0000000000000003 is down" in html and "missed" in html
        region = client.post("/v2/sdn/analyse/planted", data={
            "list": "Lab", "name": "", "evidence": "nothing"}, headers={"HX-Request": "true"})
        assert region.status_code == 422 and "Couldn't add" in region.get_data(as_text=True)
    finally:
        mp.undo()
        shutil.rmtree(AN._dir("Lab"), ignore_errors=True)
        client.post("/v2/settings/network/Lab/sdn/lab-analyse/remove")


def _sdn_evidence(client, _lab, _mp):
    """An SDN detection's evidence on Monitoring › Alerts (C1867): Lab's connection over Ryu
    4.34's capture (tests/test_sdn_v2.py's `Captured`), the SDN reader run, and the detection
    judged over the same capture (the unauthorised drop flow, its effect naming Mercury's meter
    flow: the meter drawn as the reader read it); the Lab 8 walk's displaced flow and port
    (tests/test_sdn_evidence_v2.py's `walk_pack`); one detection resolved, so the Earlier list
    names its switch. The tab, its list and each pack drawn. Its stores are a folder of its own
    and its patches undone, the connection removed, before the next provider."""
    import json
    import shutil
    import tempfile
    import time

    import pytest

    from modules import alert_history as H
    from modules import evidence_pack as EP
    from modules.sdn import closed_loop as CL
    from modules.sdn import connections as C
    from modules.sdn import detect as D
    from modules.sdn import drivers
    from tests.test_sdn_evidence_v2 import walk_pack
    from tests.test_sdn_v2 import BASE, T0, WITH_PEER, Captured, store_read

    mp = pytest.MonkeyPatch()
    folder = tempfile.mkdtemp(prefix="nmas-v2-context-sdn-packs-")
    real = drivers.make
    session = {"now": Captured()}
    try:
        mp.setattr(EP, "_path", lambda: os.path.join(folder, "evidence_packs.jsonl"))
        mp.setattr(D, "_path", lambda: os.path.join(folder, "sdn_detect.json"))
        mp.setattr(H, "_path", lambda: os.path.join(folder, "alert_history.jsonl"))
        mp.setattr(drivers, "make", lambda kind, connection, **kw: real(
            kind, connection, **dict(kw, session=session["now"])))
        C.save_connection("Lab", {"name": "lab-controller", "kind": "ryu", "url": BASE},
                          actor="v2-context")
        # The newest read stored: _sdn_operations' reads (over FakeRyu, no meter) are stamped
        # by the wall clock, so this one is too, a minute on.
        store_read("Lab", clock=lambda: time.time() + 60)

        def judged(at, flows=None):
            if flows is not None:
                session["now"] = Captured(flows=flows)
            got = CL.collect_threat_data("Lab", 1.0, sleep=lambda s: None, now=lambda: at)
            out = D.observe("Lab", got, values=dict(D.THRESHOLDS))
            assert out["ok"], out["error"]
            return out
        assert judged(T0 + 120)["fired"]
        walk_pack("walk-unauthorised-s1", network="Lab")
        walk_pack("walk-flood-1-s1", network="Lab")
        r = client.get("/v2/monitoring/alerts", headers={"Accept": "text/html"})
        assert r.status_code == 200 and "SDN detection" in r.get_data(as_text=True)
        drawn = ""
        for row in EP.read()["rows"]:
            r = client.get(f"/v2/monitoring/alerts/pack/{row['id']}",
                           headers={"HX-Request": "true", "Accept": "text/html"})
            assert r.status_code == 200 and 'data-ref="sdn"' in r.get_data(as_text=True)
            drawn += r.get_data(as_text=True)
        assert "its drop band" in drawn, "meter 1 as the SDN reader read it"
        # The unauthorised drop flow gone: its detection resolves, its pack listed as earlier.
        flows = json.loads(next(e for e in WITH_PEER if e["path"] == "/stats/flow/1")["body"])
        judged(T0 + 140, flows=[f for f in flows["1"] if f.get("cookie") != 0x4D45524300000001])
        r = client.get("/v2/monitoring/alerts/list", headers={"HX-Request": "true"})
        assert r.status_code == 200 and "Earlier" in r.get_data(as_text=True)
        assert client.post("/v2/settings/network/Lab/sdn/lab-controller/remove").status_code \
            == 200
    finally:
        mp.undo()
        shutil.rmtree(folder, ignore_errors=True)


#: What no followed GET reaches, each on the lab's own state: a POST's card, a script's GET,
#: a state the lab's walk does not hold. In order: `_deploy` changes r3, so it is last.
def _heal_and_notify(client, _lab, _mp):
    """Board H's two screens (H9): Lab's Self-healing tab with a team told, a confirmed change
    in its history, each change card, a preview drawn in place, the kill switch stopped (every
    network's mode once resumed) and resumed; and Settings › Installation › Notifications with
    a team holding an address (code sent) and a webhook (verified, its last delivery failed),
    each form open in turn. The webhook's POST is a fake (no test touches a network); the
    policy is turned off and the switch resumed before the next provider."""
    import types

    import pytest

    from modules import heal_notify
    from modules.heal import policy as H
    from modules.notify import delivery, teams, webhook

    import json as _json

    from modules import config
    from modules import settings_schema as S

    hx = {"HX-Request": "true"}
    mp = pytest.MonkeyPatch()
    lab_reads = S.get_setting

    def reads(key, default=None):
        # The lab reads settings from a dict (tests/test_device_v2.lab_setup); the kill switch
        # is read from the file Stop writes, as _settings_ai reads its keys.
        if key != "heal_stopped":
            return lab_reads(key, default)
        try:
            with open(config.USER_SETTINGS_FILE, encoding="utf-8") as fh:
                return _json.load(fh).get(key, default)
        except (OSError, ValueError):
            return default
    try:
        mp.setattr(S, "get_setting", reads)
        mp.setattr(webhook, "POST", lambda url, **kw: types.SimpleNamespace(status_code=503))
        mp.setattr(delivery, "SLEEP", lambda s: None)
        team = teams.add_team("Lab on-call", by="v2-context")["team"]
        mail = teams.add_email(team, "noc@example.com", by="v2-context")["destination"]
        hook = teams.add_webhook(team, "https://hooks.example.com/x/token", "S" * 20,
                                 by="v2-context", name="on-call chat")["destination"]
        code = teams.issue_code(team, hook, by="v2-context")
        teams.confirm_code(team, hook, code, by="v2-context")
        teams.set_enabled(team, hook, True, by="v2-context")
        delivery.send_test(team, hook, by="v2-context")                  # its last: failed
        teams.issue_code(team, mail, by="v2-context")                    # a code waiting
        heal_notify.save("Lab", team, ["cant_fix", "halted"], actor="v2-context",
                         loaded=heal_notify.drawn(heal_notify.read("Lab")))
        p = H.plan("Lab", {"heal_mode": "dry_run"})
        H.apply("Lab", {"heal_mode": "dry_run"}, p["fingerprint"], reason="dry run first",
                actor="v2-context", actor_verified="access", person=True)
        base = "/v2/settings/network/Lab/heal"
        for url in ("/v2/settings/network/Lab?tab=heal", base + "/tab",
                    base + "/change?part=mode", base + "/change?part=kinds",
                    base + "/change?part=heal_grace_seconds",
                    "/v2/settings/installation/heal/stop/ask?list_name=Lab"):
            assert client.get(url, headers=hx).status_code == 200, url
        for data in ({"part": "mode", "heal_mode": "off"},
                     {"part": "kinds", "heal_kinds_auto": "", "heal_kinds_propose": ""},
                     # Two Tier 1 kinds at once: drawn, and not confirmable (its refusal).
                     {"part": "kinds", "heal_kinds_auto": ["", "missing_line", "added_line"]}):
            assert client.post(base + "/preview", data=data, headers=hx).status_code == 200
        assert client.post(base + "/preview", data={"part": "mode", "heal_mode": "auto"},
                           headers=hx).status_code == 409
        assert client.post("/v2/settings/installation/heal/stop?list_name=Lab",
                           data={"why": "a drill"}, headers=hx).status_code == 200
        pv = client.post("/v2/settings/installation/heal/resume/preview?list_name=Lab",
                         headers=hx)
        assert pv.status_code == 200
        H.resume(H.resume_plan()["fingerprint"], reason="drill over", actor="v2-context",
                 actor_verified="access", person=True)
        notify = "/v2/settings/installation/notify"
        for url in ("/v2/settings/installation?tab=notifications",
                    "/v2/settings/installation/card/relay", notify + "/relay/password/form",
                    notify + "/relay/test/form", notify + "/teams/new", notify + "/webhooks/new",
                    f"{notify}/teams/{team}/{hook}/edit",
                    f"{notify}/teams/{team}/{mail}/remove/ask"):
            assert client.get(url, headers=hx).status_code == 200, url
        assert client.post(f"{notify}/teams/{team}/{mail}/verify", data={"code": "x"},
                           headers=hx).status_code == 409
    finally:
        H.turn_off("Lab", actor="v2-context")
        if H.stopped()["stopped"]:
            H.resume(H.resume_plan()["fingerprint"], reason="provider's end",
                     actor="v2-context", actor_verified="access", person=True)
        mp.undo()


def _heal_proposal(client, _lab, _mp):
    """Board H, artboard E (H9): a self-healing proposal's Needs attention row and its card, in
    each state the card draws: the proposal confirmable, a refusal in place (the reason typed
    kept, an unmeasured reset's refusal beside it), approved, declined, and no longer held. The
    decision store and propose's reads and writes are planted for this provider alone (the
    store's writers are tests/test_heal_proposal_v2.py's), then undone."""
    import time as _time

    import pytest

    from modules.heal import decisions as HD
    from modules.heal import propose as P

    hx = {"HX-Request": "true"}
    net, did, host = "Lab", "hd-0123456789ab", "r3"
    d = {"id": did, "row": "decision", "outcome": "propose", "device": host,
         "epoch": _time.time() - 540, "kind": "process_reset", "tier": 2, "mode": "dry_run",
         "program_hash": "0123456789abcdef", "words": "a fix that needs a person: "
         "process_reset (Tier 2)", "units": [{"words": "a fix that takes effect only through a "
                                             "process reset (Tier 2): set 1 line(s) in router "
                                             "ospf 1"}]}
    reset = {"key": "clear-ospf-process", "label": "reset the OSPF process",
             "command": "clear ip ospf 1 process", "read": "show ip ospf neighbor",
             "affects": "every OSPF adjacency of process 1 on r3 drops and forms again",
             "not_doing": "the reset changes no configuration",
             "rollback": "a reset cannot be undone", "bound_s": 100,
             "measured": {"device": "r2", "at": "2026-11-10T00:00:00Z"},
             "refused": ""}
    view = {"network": net, "decision": did, "incident": "hi-0123456789", "device": host,
            "platform": "cisco_iosxe", "kind": "process_reset",
            "kind_words": "a fix that takes effect only through a process reset", "tier": 2,
            "units": [d["units"][0]["words"]], "program": ["router ospf 1",
                                                           " router-id 192.0.2.16"],
            "program_hash": d["program_hash"], "reset": reset,
            "lines": ["router ospf 1", " router-id 192.0.2.16", reset["command"]],
            "hash": "fedcba9876543210", "refusals": [], "confirmable": True,
            "person": "lab (vty0), 18:02", "policy": {"fingerprint": "pol-3f9c2a81",
                                                      "by": "v2-context", "reason": "dry run"},
            "triggers": ["r3 logged a configuration change from vty0 by lab"],
            "words": d["words"], "at": "2026-11-04T18:12:30Z", "steps": [w for _k, w in P.STEPS]}
    # C2817, C2823: the card's plain words, the cause facts first with a labelled hypothesis,
    # and a check Mercury does not make yet ("can't tell").
    cause = {"facts": [
        {"text": "r3's configuration was changed outside Mercury (the line names the account "
                 "lab on vty0): in router ospf 1, “router-id 192.0.2.13” was changed to "
                 "“router-id 192.0.2.14”", "at": "2026-11-04T18:02:00Z", "epoch": 1.0,
         "kind": "config_change"},
        {"text": "r3 logged a duplicate OSPF router-id 192.0.2.14", "at": "2026-11-04T18:03:00Z",
         "epoch": 2.0, "kind": "duplicate_router_id"},
        {"text": "the alert “Telemetry lost” fired on r7", "at": "2026-11-04T18:04:00Z",
         "epoch": 3.0, "kind": "telemetry"}],
        "hypothesis": {"label": "Likely cause (a hypothesis, not checked)",
                       "text": "r3's router-id is now 192.0.2.14, which r4 also uses: two "
                               "routers with one router-id cannot peer",
                       "at": "2026-11-04T18:03:00Z"}}
    d.update(cause=cause, headline="r3: in router ospf 1, “router-id 192.0.2.13” was changed "
             "to “router-id 192.0.2.14”. Mercury has a fix that restarts OSPF on r3: it needs "
             "your decision", outcome_words="Mercury proposes a fix (Tier 2)")
    reset["settle_s"] = 6
    from modules.heal import said as SAID
    view.update(headline=d["headline"], cause=SAID.drawn(cause), outcome_words=d["outcome_words"],
                fix="set “router-id 192.0.2.14” back to “router-id 192.0.2.13” in router ospf 1",
                checks=[("the lines sent are read back on r3", "checked"),
                        ("the alert “Telemetry lost” fired on r7: Mercury does not read this "
                         "again yet", "cant_tell")],
                if_not="r3 keeps the change", reason_needed=False)
    # A dry-run record attached to r3's drift row brings its Right / Wrong there (C2817).
    would = {"id": "hd-0123456789ac", "row": "decision", "outcome": "would_heal",
             "device": host, "epoch": _time.time() - 300, "kind": "missing_line", "tier": 1,
             "mode": "dry_run", "program_hash": "0123456789abcdee", "words": "would heal",
             "headline": "r3: “logging host 192.0.2.10” was removed from the global "
                         "configuration. Mercury would have put it back itself, but Lab is "
                         "watching only (dry run), so nothing was sent", "cause": cause,
             "units": []}
    # H17 (artboard E's insert): Mercury's diagnosis, run before the proposal was offered, on
    # the card; and on a can't-fix row of the same network, under "Mercury's diagnosis".
    from modules.heal import auto_diagnose as AD
    from modules.heal import steplog as SL
    diag = {"id": "dg-0123456789abcdef", "runbook": "adjacency_down",
            "runbook_words": "adjacency down with both ends at intent", "incident":
            "hi-0123456789", "actor": AD.ACTOR, "state": "done", "words": "", "steps": [],
            "hypotheses": [{"rule": "down_admin_up", "layer": "physical",
                            "strength": "decisive", "incomplete": [], "agree": 2,
                            "claim": "r3 Gi4 is down while administratively up, and r4 Gi4 is up",
                            "evidence": [{"read": "read:rr-1:r3:show interfaces "
                                                  "GigabitEthernet4", "line": "", "intent": ""}],
                            "rule_out": "", "todo": "Check the link"}],
            "more": 0, "ruled_out": [{"check": "both ends on one subnet", "rule": "subnet"}],
            "not_checked": [], "commands": 16, "cap": 70, "runs": ["rr-1"], "stopped": "",
            "devices": ["r3", "r4"], "started_at": "2026-11-04T18:12:10Z",
            "finished_at": "2026-11-04T18:12:40Z"}
    view["diagnosis"] = AD.drawn(net, "hi-0123456789", host, d=diag)
    entry = {"incident": "hi-0123456780", "device": host, "network": net, "decisions": [],
             "steps": [{"step": "decide", "result": "cant_fix", "words": "physical"}],
             "program": [], "program_hash": "", "records": {}, "outcome": "cant_fix",
             "words": "self-healing will not fix it: physical (Tier 3)", "mode": "dry_run",
             "kind": "physical", "tier": 3, "epoch": _time.time() - 120,
             "diagnosis": dict(diag, incident="hi-0123456780")}
    refused = dict(view, confirmable=False, reset=dict(reset, measured={}, bound_s=None,
                                                       refused="not measured"),
                   refusals=["`clear ip ospf 1 process` is not measured on cisco_iosxe"])
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(HD, "decisions", lambda n: [d, would] if n == net else [])
        mp.setattr(SL, "incidents", lambda n, device="": (
            {"state": "ok", "entries": [entry], "error": ""} if n == net else
            {"state": "absent", "entries": [], "error": ""}))
        state = {"v": view}

        def read(n, i, **_kw):
            if i != did:
                raise P.Refused(f"no heal decision {i} is held for {n}")
            return state["v"]
        mp.setattr(P, "view", read)
        r = client.get(f"/v2/attention?list={net}")
        assert r.status_code == 200 and "Review the fix" in r.get_data(as_text=True)
        assert "Mercury&#39;s diagnosis" in r.get_data(as_text=True) or \
            "Mercury's diagnosis" in r.get_data(as_text=True)
        base = f"/v2/network/{net}/heal/proposal/{did}"
        assert client.get(base, headers=hx).status_code == 200
        # C2839: a security control's proposal, its two answers and its lines (masked).
        state["v"] = dict(view, kind="security_control", reset=None, security={
            "lines": [" ip ospf authentication message-digest",
                      " ip ospf message-digest-key 1 md5 <redacted:ospf_key>"],
            "remove_words": "Remove it (back to intent): the program below, sent as you once "
                            "approved by its hash with a reason",
            "keep_words": "Keep it: add it to intent: open the intent editor"})
        secure = client.get(base, headers=hx).get_data(as_text=True)
        assert "Remove it (back to intent)" in secure and "Keep it: add it to intent" in secure
        from modules import attention as A

        def drift_source():
            return A.source_result("drift", "Drift", read_at=_time.time(), took_ms=0, rows=[
                A.row(source="drift", kind="drifted", key=f"{net}:drifted:{host}",
                      what=f"{host} has drifted from its golden", cause="2 lines differ",
                      action={"label": "Capture it, or put it back", "open": "drift",
                              "device": host, "list": net},
                      level="danger", devices=[host])])
        mp.setattr(A, "SOURCES", [drift_source, A.heal_source])
        attached = client.get(f"/v2/attention?list={net}").get_data(as_text=True)
        assert f'id="heal-mark-{would["id"]}"' in attached
        mp.undo()
        mp.setattr(HD, "decisions", lambda n: [d, would] if n == net else [])
        mp.setattr(SL, "incidents", lambda n, device="": (
            {"state": "ok", "entries": [entry], "error": ""} if n == net else
            {"state": "absent", "entries": [], "error": ""}))
        mp.setattr(P, "view", read)
        state["v"] = refused

        def no(*_a, **_kw):
            raise P.Refused("not approved: the proposal is not the one you confirmed (confirmed "
                            "fedcba9876543210, now 0000000000000000)")
        mp.setattr(P, "approve", no)
        assert client.post(base + "/approve", data={"hash": view["hash"], "reason": "the lab's "
                           "drill now"}, headers=hx).status_code == 409
        mp.setattr(P, "approve", lambda n, i, **kw: {"ok": True, "network": n, "decision": i,
                                                     "device": host, "job": "j-1",
                                                     "hash": view["hash"]})
        assert client.post(base + "/approve", data={"hash": view["hash"], "reason": "the lab's "
                           "drill now"}, headers=hx).status_code == 200
        mp.setattr(P, "decline", lambda n, i, **kw: {
            "ok": True, "network": n, "decision": i, "device": host, "outcome": "declined",
            "words": "declined by v2-context: not during the lab", "sent": False,
            "steps": [{"step": "take", "result": "ok", "words": "taken to decline it"},
                      {"step": "record", "result": "declined", "words": "nothing was sent"}],
            "records": {"approval": "declined by v2-context (access)", "step_log": "written"}})
        assert client.post(base + "/decline", data={"reason": "not during the lab"},
                           headers=hx).status_code == 200
        gone = client.get(f"/v2/network/{net}/heal/proposal/hd-000000000000", headers=hx)
        assert gone.status_code == 404
    finally:
        mp.undo()


def _sdn_switches(client, _lab, _mp):
    """SDN › Switches (board lab9-sdn artboard A; Lab 9 Objective 2, C2902) on Lab: the lab's
    NSOT export (tests/fixtures/nsot_export/lab9_records.json, built by `export.build`) as Lab's
    committed one, the SDN reader's switch list holding one Arista, OVS's datapath 3 and one
    datapath no switch carries, a verified and a rolled-back configuration recorded, and an
    Arista capture to confirm against: the tab and its region (every group, the unknown
    datapath, a template's captures), the templates card's preview and a refused one, the
    configure preview (a switch planned, one on a draft template) and its result (one verified,
    one rolled back) and a refused confirm, the empty slot and Verify now's answer. The plans
    and applies are the operation's answers as recorded (`openflow_config.plan` and `apply`
    replaced: no switch is reached here; tests/test_openflow_vendor.py runs them for real)."""
    import pytest

    from modules.nsot import export as X
    from modules.sdn import openflow_config as OC
    from tests.test_openflow_golden import _records, fake_netbox

    mp = pytest.MonkeyPatch()
    try:
        records = _records()
        get, _calls = fake_netbox(records)
        with pytest.MonkeyPatch.context() as m:
            m.setattr("modules.inventory.source_config.load",
                      lambda name: {"source": "netbox", "filters": {"role": "openflow-switch"}})
            built = X.build("Lab", get=get, version=lambda: records["netbox_version"])
        doc = X.parse(built["bytes"])
        sha = doc["sha256"]
        mp.setattr("modules.nsot.export.read", lambda network, rev="HEAD": {
            "ok": True, "export": doc, "sha256": sha, "error": ""})
        mp.setattr("modules.nsot.export.last_commit", lambda network: {
            "commit": "a1b2c3d4e5", "at": "2026-11-10T02:00:00Z", "actor": "op@example.com"})
        mp.setattr("modules.sdn_page.stored", lambda network: {
            "state": "ok", "value_at": "2026-11-10T03:00:00Z", "failed": "",
            "value": {"controllers": [{"name": "lab-controller", "switches": [
                {"dpid": d} for d in (2214744208935, 3, 999)]}]}})
        rows = [{"kind": "operation", "id": "ofcfg-1", "at": "2026-11-10T02:10:00Z",
                 "actor": "op@example.com", "outcome": "verified", "export_sha256": sha,
                 "dpid_hex": "00000203a90ab627", "verify": {"checks": [
                     {"name": "x", "state": "pass", "words": "reads as the program sets it"}]},
                 "response": {"kind": "openflow_config", "device": "arista-sw1"}},
                {"kind": "operation", "id": "ofcfg-2", "at": "2026-11-10T02:12:00Z",
                 "actor": "op@example.com", "outcome": "rolled_back", "export_sha256": "f" * 64,
                 "error": "Verify failed", "verify": {"checks": []},
                 "response": {"kind": "openflow_config", "device": "procurve-sw"}}]
        mp.setattr("modules.sdn.flow_intent.operations",
                   lambda network: {"state": "ok", "rows": rows, "error": ""})
        capture = {"name": "arista-sw1/show_running-config/20261110T020000Z",
                   "device": "arista-sw1", "driver": "arista_eos", "family": "Arista EOS",
                   "command": "show running-config", "run": "20261110T020000Z",
                   "at": "2026-11-10T02:00:00Z", "sha256": "9ab0" * 16, "cut": False,
                   "archived": False, "text": "openflow\n   no shutdown\n"}
        mp.setattr("modules.discovery.captures",
                   lambda network, device="", limit=200: {"captures": [capture],
                                                          "unreadable": []})
        mp.setattr("modules.discovery.capture", lambda network, name: dict(capture))
        base = "/v2/sdn/switches"
        page = client.get(f"{base}?list=Lab").get_data(as_text=True)
        assert 'data-state="differs"' in page and "00000000000003e7" in page
        assert client.get(f"{base}/view?list=Lab&q=arista").status_code == 200
        assert "Confirm arista_eos against" in client.post(f"{base}/template/preview", data={
            "list": "Lab", "template": "arista_eos", "capture": capture["name"]}).get_data(
                as_text=True)
        assert client.post(f"{base}/template/preview", data={
            "list": "Lab", "template": "nosuch", "capture": capture["name"]}).status_code == 409

        def planned(network, device, **kw):
            confirmed = device == "arista-sw1"
            return {"ok": True, "device": device, "template": "arista_eos",
                    "family": "Arista EOS", "program": ["openflow", "   no shutdown"],
                    "lines": [], "undo": ["no openflow"], "hash": "a" * 64,
                    "export_sha256": sha, "different": ["enabled: wanted True"],
                    "unchanged": False, "defaults": ["openflow.fail_mode secure"],
                    "excluded": ["Management1 is the management interface (mgmt_only): "
                                 "excluded from OpenFlow"], "version": "4.17.0F",
                    "values": {}, "status": {"status": "confirmed" if confirmed else "draft",
                                             "why": "" if confirmed else "Lab has not "
                                                                        "confirmed it"}}
        mp.setattr(OC, "plan", planned)
        preview = client.post(f"{base}/configure/preview", data={
            "list": "Lab", "device": ["arista-sw1", "arista-sw2"]}).get_data(as_text=True)
        assert "Configure OpenFlow on 1 switch" in preview and "Not sent" in preview

        def applied(network, device, h, **kw):
            ok = device == "arista-sw1"
            return {"outcome": "verified" if ok else "rolled_back", "id": f"ofcfg-{device}",
                    "error": "" if ok else "Verify failed: not in the switch list",
                    "sent": [{"lines": 2}], "saved": False, "save_words": OC.NOT_SAVED,
                    "verify": {"checks": [{"name": "x", "state": "pass" if ok else "fail",
                                           "words": "the read-back"}]},
                    "rollback": {} if ok else {"ran": True, "ok": True,
                                               "words": "reads as it did before"},
                    "record": {"ok": True}}
        mp.setattr(OC, "apply", applied)
        from modules import sdn_switches_page as SP
        pairs = [("arista-sw1", "a" * 64), ("procurve-sw", "b" * 64)]
        done = client.post(f"{base}/configure/confirm", data={
            "list": "Lab", "hash": SP.batch_hash([{"device": d, "hash": h} for d, h in pairs]),
            "plan": [f"{d}={h}" for d, h in pairs]}).get_data(as_text=True)
        assert "Configured 1 of 2" in done
        assert client.post(f"{base}/configure/confirm", data={
            "list": "Lab", "hash": "0" * 64, "plan": ["arista-sw1=" + "a" * 64]}).status_code == 409
        assert client.get(f"{base}/slot?card=template").status_code == 200
        assert client.post(f"{base}/verify", data={"list": "Lab"}).status_code == 409
    finally:
        mp.undo()


PROVIDERS: list = [_reveal, _intent_check, _intent_deploy_offer, _reload_effects,
                   _intent_layers_from, _intent_layers_page, _deploy_layer_lines, _fleet_plan,
                   _fleet_selection, _fleet_run,
                   _attention_expected, _attention_explain, _attention_heal_analysis,
                   _attention_withheld,
                   _attention_quiet_period,
                   _persist_read, _unlinked, _rekey, _drift, _diagnose,
                   _in_progress, _pending, _netbox_source, _netbox_lag, _silenced_alert,
                   _alert_evidence, _logs_builder_leftovers, _alert_history,
                   _save_no_golden, _profile_versions,
                   _no_change_window, _read_only_account,
                   _update_owed, _lease_release, _ip_sla_retunes, _ip_sla_unsent,
                   _console_ztp, _console_servers, _day_cap_confirm, _settings_ai, _ai_feedback,
                   _ai_spend, _assistant, _oob_onboard, _sdn, _sdn_apps,
                   _nsot_export_and_code_repo, _heal_and_notify,
                   _heal_proposal,
                   _sdn_no_topology, _sdn_evidence, _sdn_trace, _sdn_switches, _sdn_analyse,
                   _deploy,
                   # After _deploy, on the deploy card it leaves (PHASE8_PLAN 16.11 item 3).
                   _change_record,
                   # After _deploy: r3's intent is then a real device's (r2's capture,
                   # parsed), which the editor's check passes; the walk's own r3 lacks a
                   # syslog heartbeat, so a draft on it is refused before the patch.
                   _intent_words,
                   # After _intent_words, on the r3 it leaves (its syslog heartbeat committed).
                   _intent_normalise]
