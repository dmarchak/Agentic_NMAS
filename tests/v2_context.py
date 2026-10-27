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
  not the route's payload and is left out.
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
                         {k: v for k, v in context.items() if k not in injected}))

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
    finally:
        mp.undo()
        shutil.rmtree(folder, ignore_errors=True)


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
                    data={"list": "Lab", "hash": vals.group(1), "back": "overview"})
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
        answer = {"outcome": "answer", "rationale": "The heartbeat stopped.",
                  "hypotheses": [{"claim": "The device stopped sending heartbeats.",
                                  "evidence_refs": [cite],
                                  "confirm_with": "show logging | include HEARTBEAT"}],
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


def _update_owed(client, _lab, _mp):
    """Update with a host step the running release still owes (C795): `host_steps.owed` read
    from one real commit's trailer, 99664f27's not-checkable `Host-Step-After`, never from the
    checkout's history. The walk drew this only while the checkout's last 200 commits held an
    owed step, and 3db04b01 moved 99664f27 to 201 back (CI #994). Its patches are undone before
    the next provider."""
    import pytest

    from modules import host_steps
    from routes import health

    sha = "99664f2792d7e8eb872f8c2728364b3896f6a07c"
    body = ("C794: the host step turning Loki's own detected_level off\n\nHost-Step-After: on "
            "the NMAS host: bash scripts/host-steps/c794-loki-detected-level-off.sh (Loki's own "
            "detected_level off; severity the one level)\n")
    real = host_steps.owed
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(health, "_COMMIT", sha)
        mp.setattr(host_steps, "owed",
                   lambda running, **kw: real(running, log_text=f"{sha}\x1f{body}\x1e"))
        r = client.get("/v2/update", headers={"Accept": "text/html"})
        assert r.status_code == 200 and 'id="update-owed-steps"' in r.get_data(as_text=True), \
            r.status_code
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
    other = LP.propose("Lab", dict(d, key="k-ctx-2", rule="flood"), "rate_limit_source", "low",
                       why="HITL")
    LP.say("Lab", "detect", "a scan from 192.0.2.1 on " + sw)
    assert "2 awaiting approval" in client.get("/v2/sdn/responses?list=Lab")\
        .get_data(as_text=True)
    card = client.post(f"/v2/sdn/response/{row['id']}/preview",
                       data={"list": "Lab", "hard_timeout": "90"}).get_data(as_text=True)
    assert "Done, verified" in client.post("/v2/sdn/response/confirm", data=fields(card))\
        .get_data(as_text=True)
    assert client.post(f"/v2/sdn/response/{other['id']}/dismiss",
                       data={"list": "Lab", "reason": "the lab's own test"}).status_code == 200
    assert client.post("/v2/sdn/mode", data={"list": "Lab", "mode": "auto", "reason": "lab run",
                                             "hours": "1", "risk": "low"}).status_code == 200
    assert client.post("/v2/sdn/mode", data={"list": "Lab", "mode": "hitl"}).status_code == 200
    assert client.post("/v2/sdn/loop", data={"list": "Lab", "run": "start",
                                             "interval": "10"}).status_code == 200
    assert client.post("/v2/sdn/loop", data={"list": "Lab", "run": "stop"}).status_code == 200
    LP._jobs["Lab"]["thread"].join(10)


#: What no followed GET reaches, each on the lab's own state: a POST's card, a script's GET,
#: a state the lab's walk does not hold. In order: `_deploy` changes r3, so it is last.
PROVIDERS: list = [_reveal, _intent_check, _persist_read, _unlinked, _rekey, _drift,
                   _in_progress, _pending, _netbox_source, _netbox_lag, _silenced_alert,
                   _alert_evidence, _logs_builder_leftovers, _alert_history,
                   _save_no_golden, _profile_versions,
                   _no_change_window, _update_owed, _lease_release, _ip_sla_retunes, _ip_sla_unsent,
                   _console_ztp, _console_servers, _day_cap_confirm, _oob_onboard, _sdn,
                   _deploy,
                   # After _deploy: r3's intent is then a real device's (r2's capture,
                   # parsed), which the editor's check passes; the walk's own r3 lacks a
                   # syslog heartbeat, so a draft on it is refused before the patch.
                   _intent_words]
