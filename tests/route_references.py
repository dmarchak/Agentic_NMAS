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

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates")

WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
_METHOD = re.compile(r"""method\s*[:=]\s*['"]([A-Za-z]+)['"]""")
_URL_FOR = re.compile(r"""url_for\(\s*['"]([A-Za-z_][\w.]*)['"]""")


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


def path_references(corpus: str, rule: str, has_args: bool) -> set:
    """The methods with which *corpus* references *rule*'s path (``None``
    for a reference whose method cannot be read)."""
    s = stem(rule) if has_args else rule
    if not s or s == "/":
        return set()
    found = set()
    for m in re.finditer(re.escape(s), corpus):
        after = corpus[m.end():m.end() + 1]
        if has_args:
            if after != "/":
                continue
        elif after and (after.isalnum() or after in "_-/"):
            continue
        found.add(classify(corpus, m.start()))
    return found


def template_sources() -> dict:
    """{relative path: text} for every template."""
    out = {}
    for path in glob.glob(os.path.join(TEMPLATES, "**", "*.html"), recursive=True):
        out[os.path.relpath(path, TEMPLATES)] = open(path, encoding="utf-8").read()
    return out


def url_for_references() -> dict:
    """{endpoint: {methods}} from ``url_for('<endpoint>')`` in template source."""
    out = {}
    for text in template_sources().values():
        for m in _URL_FOR.finditer(text):
            out.setdefault(m.group(1), set()).add(classify(text, m.start()))
    return out


FIXTURE_DEVICE = {"ip": "192.0.2.1", "hostname": "r1", "device_type": "cisco_ios",
                  "username": "admin", "password": "", "secret": ""}


def corpus(app_module, monkeypatch) -> str:
    """Every page a person navigates to (the index and the device page, the
    only two `render_template` renders), each rendered WITH a device, plus
    the scripts each loads.

    With no device, the index's per-device loop renders nothing and the
    device page redirects, and a redirect has no references in it: the
    fixture would decide what the interface can reach.
    """
    from tests.js_source import with_loaded_scripts

    monkeypatch.setattr(app_module, "load_saved_devices",
                        lambda *a, **k: [dict(FIXTURE_DEVICE)])
    monkeypatch.setattr(app_module, "get_device_context",
                        lambda d, *a, **k: (["flash:"], [], "flash:"))
    client = app_module.app.test_client()
    pages = []
    for path in ("/", f"/device/{FIXTURE_DEVICE['ip']}"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} did not render ({r.status_code})"
        pages.append(with_loaded_scripts(r.get_data(as_text=True)))
    return "\n".join(pages)


def reachability(app_module, monkeypatch) -> dict:
    """{"<METHOD> <rule>": bool} for every route and method the app serves.

    Whether a path MIXES a read and a write is decided per PATH, across
    every rule registered on it: `/drift/settings` is two rules, a GET and a
    POST, and deciding it per rule made each look single-method, so the
    page's GET counted as reaching the POST (found by the method-blind
    negative control, which should have failed and did not)."""
    text = corpus(app_module, monkeypatch)
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
    return out
