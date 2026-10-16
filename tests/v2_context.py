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
"""

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
                IP._commit_intent(lab["repo"], "r3")
                client = RecordingClient(lab["client"], recorder)
                template_rendered.connect(recorder, A.app)
                try:
                    pages = IP._walk(client)
                    fragments = walk_fragments(client, pages)
                    upstream: dict = {}
                    for provide in PROVIDERS:
                        for route, got in (provide(client, lab, mp) or {}).items():
                            upstream.setdefault(route, []).extend(got)
                finally:
                    template_rendered.disconnect(recorder, A.app)
    finally:
        mp.undo()
        _store_back(aside)
    _CACHE["m"] = {"routes": recorder.routes, "pages": len(pages), "fragments": fragments,
                   "providers": len(PROVIDERS), "upstream": upstream}
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


#: What no followed GET reaches, each on the lab's own state: a POST's card, a script's GET,
#: a state the lab's walk does not hold. In order: `_deploy` changes r3, so it is last.
PROVIDERS: list = [_reveal, _intent_check, _persist_read, _unlinked, _rekey, _deploy]
