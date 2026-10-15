"""Which (route, method) pairs the interface actually reaches.

**Not a test module.** Stage 7.0's per-route reachability check
(`test_route_reachability.py`) and anything else that needs to ask "does a
person have a way to send THIS request" share it, so there is one answer.

A reference is found two ways, because each alone is blind to something:

* **In the rendered pages, plus the scripts they load.** A path stem at a
  path boundary, so `/templates` is not counted as a reference to
  `/templates/file`, and a stem with a converter must be followed by `/`.
* **In template SOURCE, by `url_for('<endpoint>')`** ("url_for-aware"). A
  `url_for()` inside a Jinja loop over an empty list renders nothing, so
  the rendered page alone would call its route unreachable on a fixture
  with no backups, and reachable on one with backups: a property of the
  fixture, not of the interface.

**Per method only where a path mixes a read and a write**, because there
the path is two capabilities: a page that fetches `/list/variables` does
not thereby let anyone save one. A path with ONE method is reached by any
reference, since nothing else could be sent to it; that is how a URL held
in a map and sent by a `fetch()` elsewhere (the NetBox import and remove
buttons) counts. On a mixed path a reference counts only when its method
can be read:

* inside a ``<form ...>`` tag: its ``method`` attribute (default GET);
* inside an ``<a ...>`` tag: GET;
* as the first argument of ``fetch(``: the ``method: '<M>'`` in that
  call's options (before the next ``fetch(``, at most 400 characters),
  else GET, which is `fetch()`'s default.

Anything else on a mixed path is ``None``: referenced, method unknown, and
not counted for either.

What this cannot see, stated so it is not read as seen: a URL assembled
from pieces (``'/templates/' + action``) references only its literal
prefix.
"""

import os
import re

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates")

WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
_METHOD = re.compile(r"""method\s*[:=]\s*['"]([A-Za-z]+)['"]""")
_URL_FOR = re.compile(r"""url_for\(\s*['"]([A-Za-z_][\w.]*)['"]""")
#: The v2 panel grid macro calls `url_for(endpoint, ...)` with the endpoint it
#: is HANDED, so the literal is at each call (`panel_grid(layout, '<endpoint>',
#: ...)`): a GET of one panel's data, made by nmas_panels.js.
_PANEL_GRID = re.compile(r"""panel_grid\([^,]*,\s*['"]([A-Za-z_][\w.]*)['"]""")
#: The v2 device page's Actions menu builds its rows in a loop over (label, op, words)
#: tuples, each row's request `url_for('<prefix>' ~ op, ...)` (an hx-get): the endpoint is
#: the prefix joined to each tuple's op.
_OP_LOOP = re.compile(r"\{%-?\s*for label, op, \w+ in \[(.*?)\]\s*-?%\}(.*?)\{%-?\s*endfor",
                      re.S)
_OP_LOOP_URL = re.compile(r"""url_for\(\s*['"]([A-Za-z_][\w.]*)['"]\s*~\s*op\b""")
_OP_LOOP_OPS = re.compile(r"""\(\s*'[^']*',\s*'([\w-]+)'""")


def classify(text: str, index: int):
    """The HTTP method of the reference at *index*, or ``None`` when it
    cannot be read (not a form, a link, or a `fetch()` argument)."""
    lt = text.rfind("<", 0, index)
    gt = text.find(">", index)
    if lt != -1 and gt != -1 and text.find(">", lt, index) == -1:
        tag = text[lt:gt + 1]
        name = tag[1:].split(None, 1)[0].lower() if len(tag) > 1 else ""
        if name == "form":
            m = re.search(r"""\bmethod\s*=\s*['"]?([A-Za-z]+)""", tag)
            return (m.group(1) if m else "GET").upper()
        if name == "a":
            return "GET"
    before = text[max(0, index - 40):index].rstrip("'\"`{ ").rstrip()
    if not (before.endswith("fetch(") or before.endswith("url_for(")
            or before.endswith("{{")):
        return None
    end = text.find("fetch(", index + 1)
    end = min(end if end != -1 else len(text), index + 400)
    m = _METHOD.search(text, index, end)
    return m.group(1).upper() if m else "GET"


def stem(rule: str) -> str:
    return re.split(r"<", rule)[0].rstrip("/")


def tail_words(rule: str) -> list:
    """The literal path words after a route's first converter
    (``/templatize/committed/<h>/revert`` -> ``["revert"]``)."""
    if "<" not in rule:
        return []
    tail = rule[rule.index("<"):]
    return [w for w in re.split(r"<[^>]+>|/", tail) if w]


#: How near a tail word must be to count: an assembled URL names its
#: action close by. `resolveApproval` builds `/ai/approvals/${id}/${action}`
#: with `'approve'` a few lines above, and `'reject'` in the card's onclick
#: about 2,500 characters away (measured: 1,500 lost reject, 4,000 keeps it
#: and still finds no `revert` near the intent editor's fetches).
TAIL_WINDOW = 4000


def path_references(corpus: str, rule: str, has_args: bool) -> set:
    """The methods with which *corpus* references *rule*'s path (``None``
    for a reference whose method cannot be read).

    A route with literal words AFTER its converter needs those words near
    the reference too. The stem alone made `'/templatize/committed/' + host`
    (the editor's own route) a reference to
    `/templatize/committed/<host>/revert`, which no page sends: intent revert
    counted as reachable with no GUI at all (found 2026-09-27 by the result
    survey, which needed this list to be true)."""
    s = stem(rule) if has_args else rule
    if not s or s == "/":
        return set()
    words = tail_words(rule) if has_args else []
    found = set()
    for m in re.finditer(re.escape(s), corpus):
        after = corpus[m.end():m.end() + 1]
        if has_args:
            if after != "/":
                continue
            near = corpus[max(0, m.start() - TAIL_WINDOW):m.end() + TAIL_WINDOW]
            if any(not re.search(rf"\b{re.escape(w)}\b", near) for w in words):
                continue
        elif after and (after.isalnum() or after in "_-/"):
            continue
        found.add(classify(corpus, m.start()))
    return found


def template_sources() -> dict:
    """{relative path: text} for every template."""
    out = {}
    for path in tracked(TEMPLATES, suffix=".html"):
        out[os.path.relpath(path, TEMPLATES)] = open(path, encoding="utf-8").read()
    return out


def url_for_references() -> dict:
    """{endpoint: {methods}} from ``url_for('<endpoint>')`` in template source."""
    out = {}
    for text in template_sources().values():
        for m in _URL_FOR.finditer(text):
            out.setdefault(m.group(1), set()).add(classify(text, m.start()))
        for m in _PANEL_GRID.finditer(text):
            out.setdefault(m.group(1), set()).add("GET")
        for m in _OP_LOOP.finditer(text):
            for prefix in _OP_LOOP_URL.findall(m.group(2)):
                for op in _OP_LOOP_OPS.findall(m.group(1)):
                    out.setdefault(prefix + op, set()).add("GET")
    return out


def corpus() -> str:
    """Every page a person navigates to, each rendered WITH a device, plus the scripts each
    loads: v2's pages by the links between them, and today's while they exist
    (`tests/interface_pages.py` says which, and what it cannot see). Until P7-19
    (2026-10-15) it was today's two pages alone, the index and the device page."""
    from tests import interface_pages

    return interface_pages.corpus()


def reachability(app_module) -> dict:
    """{"<METHOD> <rule>": bool} for every route and method the app serves.

    Whether a path MIXES a read and a write is decided per PATH, across
    every rule registered on it: `/drift/settings` was two rules, a GET and a
    POST (both left at 7.8), and deciding it per rule made each look single-method, so the
    page's GET counted as reaching the POST (found by the method-blind
    negative control, which should have failed and did not)."""
    from tests import interface_pages

    text = corpus()
    by_endpoint = url_for_references()
    rules = [r for r in app_module.app.url_map.iter_rules() if r.endpoint != "static"]
    methods_on_path = {}
    for rule in rules:
        methods_on_path.setdefault(rule.rule, set()).update(
            (rule.methods or set()) - {"HEAD", "OPTIONS"})
    out = {}
    for rule in rules:
        methods = (rule.methods or set()) - {"HEAD", "OPTIONS"}
        on_path = methods_on_path[rule.rule]
        seen = path_references(text, rule.rule, bool(rule.arguments))
        seen |= by_endpoint.get(rule.endpoint, set())
        mixed = "GET" in on_path and bool(on_path & set(WRITE_METHODS))
        for method in methods:
            out[f"{method} {rule.rule}"] = (method in seen) if mixed else bool(seen)
    out["_corpus_size"] = len(text)
    out["_v2_corpus_size"] = len(interface_pages.v2_corpus())
    out["_v2_pages"] = len(interface_pages.pages()["v2"])
    return out


#: A request a page makes: the first argument of `fetch(`, or an `href`,
#: `action`, `formaction` or `data-url` attribute, or v2's `hx-get`, `hx-post`, `hx-put`,
#: `hx-patch` or `hx-delete` (htmx's request attributes, v2's usual request, read since
#: P7-19), when it is a literal path. What this cannot see, stated: a URL held in a variable
#: and fetched elsewhere (only its literal is found, where it is written), and `url_for()`,
#: which Flask resolves at render and which fails the render when its endpoint is gone.
_REQUEST = re.compile(r"""(?:fetch\(\s*|(?:href|action|data-url|hx-(get|post|put|patch|delete))"""
                      r"""\s*=\s*)(['"`])(/[^'"`\s?#]*)""")


def page_requests(text: str) -> dict:
    """{(literal path, method): True} for every literal request in *text*.

    An `hx-<verb>` request's method is its verb; any other is read the way `classify` reads
    it. One `classify` cannot read (a `data-url` a script sends, a button's `formaction`) is
    ``None``, which resolves to a route under ANY method: until P7-19 it was GET, and v2's
    first pages read that way named three live POSTs dead (`/update/check`'s `data-url`,
    sent as a POST by its Alpine component, among them)."""
    out = {}
    for m in _REQUEST.finditer(text):
        raw = m.group(3)
        if raw == "/" or raw.startswith("/static/"):
            continue
        concatenated = (m.group(2) in "'\""
                        and text[m.end(3) + 1:m.end(3) + 8].lstrip().startswith("+"))
        method = m.group(1).upper() if m.group(1) else classify(text, m.start(3) - 1)
        out[(raw + ("+" if concatenated else ""), method)] = True
    return out


def resolves(app_module, request: str, method: str) -> bool:
    """Does *request* (a literal path; `${...}` is one segment; a trailing `+`
    marks a string the page concatenates onto) reach a route with *method*
    (``None``: any method)?"""
    concatenated = request.endswith("+")
    path = request.rstrip("+")
    segs = [s for s in re.sub(r"\$\{[^}]*\}", "\x00", path).split("/")]
    for rule in app_module.app.url_map.iter_rules():
        if method is not None and method not in (rule.methods or set()):
            continue
        rsegs = rule.rule.split("/")
        if concatenated:
            # Only its literal prefix is known: some rule must extend it.
            if rule.rule.startswith(path) and (path.endswith("/") or
                                               rule.rule[len(path):][:1] in ("/", "<")):
                return True
            continue
        if len(rsegs) != len(segs):
            # A `<path:x>` converter takes the rest.
            if not any(s.startswith("<path:") for s in rsegs):
                continue
        ok = True
        for i, s in enumerate(segs):
            if i >= len(rsegs):
                ok = False
                break
            r = rsegs[i]
            if r.startswith("<path:"):
                break
            if s == r or r.startswith("<") or "\x00" in s:
                continue
            ok = False
            break
        if ok:
            return True
    return False
