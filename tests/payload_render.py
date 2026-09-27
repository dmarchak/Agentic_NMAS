"""What a payload carries, and what the shipped renderer reads from it.

**Not a test module.** Stage 7.0 (3), `test_payload_is_rendered.py`: "if a
payload carries it, the screen shows it", made mechanical. Four instances
were recorded before this existed, and each was a key computed, carried to
the browser and drawn nowhere: D4 (`commands`, `dangerous`, `attribution`
on the deploy wizard), the pending banner's list, `/jobs/health` with no
view, and C27 (the restore preview never drew the lines to be added).

**What it compares, and at what grain:**

* **Payload keys** come from a REAL response (the route called through the
  test client, never a hand-built dict), every key NAME at every depth.
* **Renderer reads** come from the shipped functions' source, comments
  stripped (a commented-out read is not a read): every property name read
  anywhere in them, by `.name`, `?.name`, `['name']` or destructuring.
* **Forward** (the direction the four instances were): a payload key no
  declared function reads is a finding.
* **Reverse**: a read rooted at the payload VARIABLE (`data.x`, depth one)
  naming a key the payload does not carry is a finding: a panel drawing a
  field nothing sends.

**What it cannot see, stated so it is not read as seen:** the forward check
matches key NAMES, not paths, so a key read on a different object with the
same name (`name`, `ip`) counts as read; and a key the fixture's payload
does not carry is not examined at all. That second limit is why the anchor
routes are driven with fixtures that CAN carry the keys that failed before.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "static", "js", "gen")


def strip_comments(src: str) -> str:
    """JavaScript without comments, strings kept (so `'http://x'` survives).
    A small scanner, not a regex: a regex cannot tell a `//` in a string or a
    URL from the start of a comment."""
    out, i, n = [], 0, len(src)
    quote = None
    while i < n:
        c = src[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"`":
            quote = c
            out.append(c)
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j == -1 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def lift(src: str, name: str) -> str:
    """The source of function *name*: ``function name(`` or
    ``window.name = function``/``name = async (`` forms, brace-matched."""
    pats = [rf"(?:^|\n)[ \t]*(?:async\s+)?function\s+{re.escape(name)}\s*\(",
            rf"(?:^|\n)[ \t]*(?:window\.)?{re.escape(name)}\s*=\s*(?:async\s+)?function\b",
            rf"(?:^|\n)[ \t]*(?:const|let|var)\s+{re.escape(name)}\s*=\s*(?:async\s+)?\("]
    m = None
    for pat in pats:
        m = re.search(pat, src)
        if m:
            break
    if not m:
        raise KeyError(f"no function {name!r} in the shipped source")
    start = m.start()
    depth, i, seen = 0, src.index("{", m.end() - 1), False
    while i < len(src):
        if src[i] == "{":
            depth += 1
            seen = True
        elif src[i] == "}":
            depth -= 1
            if seen and depth == 0:
                break
        i += 1
    return src[start:i + 1]


#: The shared components live beside gen/, not in it: named by their path
#: under static/js/.
COMPONENTS = ("nmas_preview_confirm.js", "nmas_capture.js")


def shipped(file: str) -> str:
    base = os.path.dirname(GEN) if file in COMPONENTS else GEN
    return open(os.path.join(base, file), encoding="utf-8").read()


_DOT = re.compile(r"(?:\?\.|\.)\s*([A-Za-z_$][\w$]*)")
_BRACKET = re.compile(r"""\[\s*['"]([A-Za-z_$][\w$]*)['"]\s*\]""")
_DESTRUCT = re.compile(r"(?:const|let|var)\s*\{([^}]*)\}\s*=")


def reads(body: str) -> set:
    """Every property name read anywhere in *body* (comments stripped)."""
    text = strip_comments(body)
    names = set(_DOT.findall(text)) | set(_BRACKET.findall(text))
    for group in _DESTRUCT.findall(text):
        for part in group.split(","):
            key = part.split(":")[0].split("=")[0].strip()
            if key:
                names.add(key)
    return names


def root_reads(body: str, var: str) -> set:
    """Properties read directly on *var* (depth one), comments stripped."""
    text = strip_comments(body)
    v = re.escape(var)
    names = set(re.findall(rf"\b{v}\s*(?:\?\.|\.)\s*([A-Za-z_$][\w$]*)", text))
    names |= set(re.findall(rf"""\b{v}\s*\[\s*['"]([A-Za-z_$][\w$]*)['"]\s*\]""", text))
    for group in re.findall(rf"(?:const|let|var)\s*\{{([^}}]*)\}}\s*=\s*{v}\b", text):
        for part in group.split(","):
            key = part.split(":")[0].split("=")[0].strip()
            if key:
                names.add(key)
    return names


def payload_keys(obj, _into=None) -> set:
    """Every key name at every depth of a JSON value."""
    out = set() if _into is None else _into
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            payload_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            payload_keys(v, out)
    return out


def literal_keys(src: str, name: str) -> set:
    """The keys of object literal *name* (``const name = { a: 1, b: 2 }``).
    A renderer that reads the payload through a lookup table
    (``d.settings[key]`` for each key of ``_GENERAL_MAP``) reads exactly the
    table's keys, and a key missing from the table is not drawn."""
    m = re.search(rf"(?:const|let|var)\s+{re.escape(name)}\s*=\s*\{{", src)
    if not m:
        raise KeyError(f"no object literal {name!r} in the shipped source")
    depth, i = 0, m.end() - 1
    start = i
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = strip_comments(src[start + 1:i])
    return set(re.findall(r"(?:^|[,{\s])([A-Za-z_$][\w$]*)\s*:", body))


def python_reads(path: str, name: str) -> set:
    """Keys a server-side ADAPTER reads from the payload (``d.get("x")``,
    ``d["x"]``) in function *name* of *path*. The preview-confirm component
    (7.1) draws a preview the server builds FROM the plan's entries, so a
    key the adapter never reads is dropped before any renderer sees it: D4's
    failure moved one step upstream, and this is where it would reappear."""
    import ast

    src = open(os.path.join(ROOT, path), encoding="utf-8").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            body = ast.get_source_segment(src, node)
            break
    else:
        raise KeyError(f"no function {name!r} in {path}")
    return (set(re.findall(r"""\.get\(\s*["']([\w-]+)["']""", body))
            | set(re.findall(r"""\[\s*["']([\w-]+)["']\s*\]""", body)))


def render_preview(preview: dict, hooks: dict = None) -> str:
    """The SHIPPED preview-confirm renderer, executed in duktape against a
    preview from a real route. The whole file runs, as the browser runs it,
    rather than lifted functions: it is one IIFE."""
    import json

    import dukpy

    src = shipped("nmas_preview_confirm.js")
    return dukpy.evaljs("var window = {};\n" + src + "\nwindow.previewConfirmHtml("
                        + json.dumps(preview) + ", " + json.dumps(hooks or {}) + ")")


def render_result(result: dict, hooks: dict = None) -> str:
    """The SHIPPED result half of the component, executed in duktape against
    a result from a real route (7.1 step 2)."""
    import json

    import dukpy

    src = shipped("nmas_preview_confirm.js")
    return dukpy.evaljs("var window = {};\n" + src + "\nwindow.previewConfirmResultHtml("
                        + json.dumps(result) + ", " + json.dumps(hooks or {}) + ")")
