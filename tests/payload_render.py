"""What a payload carries, and what the shipped renderer reads from it.

**Not a test module.** Its readers serve v2's checks (`python_reads`: an adapter's reads, for
tests/test_v2_context_is_drawn.py; `lift`: a v2 script's function, for
tests/test_results_are_drawn.py), and `render_preview_v2` / `render_result_v2` draw a
component-built preview or result with v2's shared parts. Its first user,
`test_payload_is_rendered.py` (today's JSON routes against today's JavaScript renderers), left
with today's pages at 7.8 (2026-10-17, P7-27). What follows is that check's method, kept because
the readers are its.

Stage 7.0 (3), `test_payload_is_rendered.py`: "if a
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
STATIC_JS = os.path.join(ROOT, "static", "js")


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


def shipped(file: str) -> str:
    """A shipped script by name, in `static/js/` (v2's own; the scripts moved out of today's
    pages into `static/js/gen/` left with them at 7.8, P7-27)."""
    return open(os.path.join(STATIC_JS, file), encoding="utf-8").read()


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


def _v2_part(macro: str, *args) -> str:
    """One macro of v2's preview component (`templates/v2/_preview_parts.html`), rendered by
    the app's own Jinja environment (autoescape and globals as a page has them)."""
    import app as nmas

    with nmas.app.test_request_context("/v2/"):
        parts = nmas.app.jinja_env.get_template("v2/_preview_parts.html").module
        return str(getattr(parts, macro)(*args))


def render_preview_v2(preview: dict) -> str:
    """v2's drawing of a preview the component built (`preview_confirm.build`): the shared
    parts every v2 card that confirms such a preview draws (NetBox, onboarding). Today's
    JavaScript renderer (`static/js/nmas_preview_confirm.js`, `render_preview` here) left with
    today's index at 7.8 (2026-10-17, P7-27); a card that draws its preview with its own template
    (capture, deploy, restore) is read through its own route."""
    return _v2_part("preview_parts", preview)


def render_operation_result_v2(result: dict, list_name: str = "Lab") -> str:
    """v2's drawing of a deploy or restore batch's result (`preview_confirm.operation_result`):
    the batch's card once its job has ended (`templates/v2/_apply_job.html`, as
    `routes.v2._apply_answer` renders it, its stepper from `deploy_job.run_card`). The batch
    Apply, Coverage's Deploy missing and History's Re-apply draw their result here. Today's
    renderer of the same result left with today's index at 7.8 (P7-27)."""
    import app as nmas
    from flask import render_template
    from modules import deploy_job

    st = {"state": "done", "job": "t0", "list": list_name, "elapsed_s": 0, "error": "",
          "payload": {"result": result}}
    with nmas.app.test_request_context("/v2/monitoring/apply/job/t0"):
        return render_template("v2/_apply_job.html", j=st, job="t0",
                               run=deploy_job.run_card(st, list_name), arrivals=None)


def render_device_deploy_result_v2(result: dict, host: str, list_name: str = "Lab") -> str:
    """v2's drawing of one device's deploy result: the device page's Deploy… card once its job
    has ended (`device_actions.deploy_job_card`, `templates/v2/_deploy.html`), as
    `device_v2.deploy_job_card` renders it."""
    from types import SimpleNamespace

    import app as nmas
    from flask import render_template
    from modules import device_actions

    card = device_actions.deploy_job_card(SimpleNamespace(name=list_name), host, "t0",
                                          {"state": "done", "payload": {"result": result}})
    with nmas.app.test_request_context(f"/v2/device/{host}/deploy/job/t0"):
        return render_template("v2/_deploy.html", c=dict(card, back=""))


def render_deploy_card_v2(plan: dict, host: str, list_name: str = "Lab") -> str:
    """v2's drawing of THE deploy plan for one device: the device page's Deploy… card
    (`device_actions.deploy_card`, `templates/v2/_deploy.html`) from the plan's masked entry
    and preview (`tests/deploy_core.plan`), for a verified person, as `device_v2.deploy`
    builds it."""
    from types import SimpleNamespace

    import app as nmas
    from flask import render_template, request
    from modules import device_actions, identity
    from modules.preview_confirm import confirm_part

    entry = next(d for d in plan["devices"] if d.get("device") == host)
    with nmas.app.test_request_context(f"/v2/device/{host}/deploy"):
        card = device_actions.deploy_card(
            SimpleNamespace(name=list_name), host, entry, plan["preview"],
            viewer=dict(confirm_part(request, "confirm"),
                        actor=identity.identify(request).actor or ""))
        return render_template("v2/_deploy.html", c=dict(card, back="", ip=""))


def render_restore_card_v2(plan: dict, host: str, moment: str = "HEAD",
                           list_name: str = "Lab") -> str:
    """v2's drawing of THE restore plan for one device: the device page's Restore from… card
    (`device_actions.restore_card`, `templates/v2/_restore.html`), as `device_v2._restore_card`
    builds it from the masked plan, for a verified person."""
    from types import SimpleNamespace

    import app as nmas
    from flask import render_template, request
    from modules import device_actions, identity
    from modules.preview_confirm import confirm_part

    with nmas.app.test_request_context(f"/v2/device/{host}/restore/preview"):
        card = device_actions.restore_card(
            SimpleNamespace(name=list_name), host, moment, plan,
            viewer=dict(confirm_part(request, "confirm"),
                        actor=identity.identify(request).actor or ""))
        return render_template("v2/_restore.html", c=dict(card, back="", ip=""))


def render_result_v2(result: dict) -> str:
    """v2's drawing of a result the component built (`preview_confirm.build_result`): the shared
    result parts (`result_parts`). Today's (`render_result` here) left with today's index at 7.8
    (P7-27)."""
    return _v2_part("result_parts", result)
