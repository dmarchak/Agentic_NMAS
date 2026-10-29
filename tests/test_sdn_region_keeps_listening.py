"""SDN › Responses keeps listening after a refused control (C2003, the operator's Lab 8 walk,
2026-10-28: the page stopped updating and new cards and log lines appeared only after a reload).

Found reading the page's live path (`routes/sdn_v2.py` against static/js/nmas_v2.js): Classify,
Dismiss, Turn AUTO on or off, and the loop's Start and Stop each post with `hx-target="#sdn"`
and `hx-swap="outerHTML"`, because their success redraws the whole region. Their REFUSAL was a
one-line `_sdn_answer.html`, and an error answer that is a fragment is swapped (`neverSilent`),
so the line replaced the region: the cards, the region's listener (`nmas:sdn from:body`) and
its stale note (C2003's part 2) went with it. Shown in a real browser before the fix: after a
refused Dismiss the page held only "Not saved: …", no `#sdn`, and a response proposed and
announced after it never appeared until the page was loaded again.

- **The shape, held on every member:** each form of the region that targets the region itself
  posts to a route that never renders its refusal as the region's replacement: a refusal is
  drawn after the form that asked (`HX-Retarget: this`, `HX-Reswap: afterend`,
  `_refused_beside`). The forms are found by rendering the page, never listed by hand (a floor
  of four, and the policy form, which answers in its own slot, is not one of them).
- **Each refusal:** its status, its words, beside the form.
- **The live key:** a loop pass that proposes a response announces a key the region listens on
  and the page relays (tests/test_sdn_loop_announces.py holds the pass's keys).
- **In a real browser:** after a refused Dismiss the region is still there, still listening,
  the refusal after the form, and a response proposed and announced as the loop's job then
  appears without a reload.
"""

import ast
import os
import re
import time

import pytest

from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_modes_loop import T0, collected, observed
from tests.test_sdn_ops_v2 import lab, mark_stage  # noqa: F401 - the fixture

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES = os.path.join(ROOT, "routes", "sdn_v2.py")
FORM = re.compile(r"<form\b[^>]*>", re.S)


def _det(key, src):
    return {"key": key, "rule": "scan", "title": "SDN scan", "network": "Default",
            "connection": "lab-controller", "dpid": 1, "dpid_hex": "0000000000000001",
            "source": src, "targets": ["192.0.2.2"], "confidence": "high",
            "words": f"{src} reached 25 distinct destination ports"}


def _attr(tag, name):
    m = re.search(rf'\s{name}="([^"]*)"', tag)
    return m.group(1) if m else None


def _region_forms(html):
    """``[(path, form tag)]``: every form inside the page's region that posts and targets the
    region itself."""
    out = []
    for tag in FORM.findall(html):
        post = _attr(tag, "hx-post")
        if post and _attr(tag, "hx-target") == "#sdn":
            out.append((post.split("?", 1)[0].replace("&amp;", "&"), tag))
    return out


def _renders_the_answer_itself(fn) -> bool:
    """Whether *fn* calls ``render_template("v2/_sdn_answer.html", …)`` itself (parsed)."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "render_template" \
                and node.args and isinstance(node.args[0], ast.Constant) \
                and node.args[0].value == "v2/_sdn_answer.html":
            return True
    return False


def test_every_form_that_redraws_the_region_is_refused_beside_itself(lab):
    import app as A

    LP.propose("Default", _det("k-a", "192.0.2.1"), "drop_source", "low", why="HITL")
    c = lab["client"]
    forms = []
    # Both of the loop's and of the mode's forms: stopped and running, HITL and AUTO.
    forms += _region_forms(c.get("/v2/sdn/responses?list=Default").get_data(as_text=True))
    assert mark_stage(c, "lab").status_code == 200
    assert c.post("/v2/sdn/mode", data={"list": "Default", "mode": "auto", "reason": "a test",
                                        "hours": "1", "risk": "low"}).status_code == 200
    forms += _region_forms(c.get("/v2/sdn/responses?list=Default").get_data(as_text=True))
    paths = sorted({p for p, _ in forms})
    assert len(paths) >= 4, paths                     # the floor: classify, dismiss, mode, loop
    assert not any("/policy" in p for p in paths), "the policy form answers in its own slot"
    tree = ast.parse(open(ROUTES, encoding="utf-8").read())
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    adapter = A.app.url_map.bind("localhost")
    bad = []
    for path in paths:
        endpoint, _args = adapter.match(path, method="POST")
        name = endpoint.split(".", 1)[1]
        assert name in fns, (path, endpoint)
        if _renders_the_answer_itself(fns[name]):
            bad.append(f"{path} ({endpoint}) renders its refusal as the region's replacement")
    assert bad == []
    # The planted case: the helper itself renders the answer, and is found by the same parse.
    assert _renders_the_answer_itself(fns["_refused_beside"])


def _beside(r, status, words):
    body = r.get_data(as_text=True)
    assert r.status_code == status, body
    assert r.headers.get("HX-Retarget") == "this" and r.headers.get("HX-Reswap") == "afterend"
    assert "sdn-ans-bad" in body and words in body and 'id="sdn"' not in body


def test_a_refused_dismiss_is_drawn_beside_its_form(lab):
    row = LP.propose("Default", _det("k-a", "192.0.2.1"), "drop_source", "low", why="HITL")
    r = lab["client"].post(f"/v2/sdn/response/{row['id']}/dismiss",
                           data={"list": "Default", "reason": ""})
    _beside(r, 409, "names its reason")


def test_a_refused_classify_is_drawn_beside_its_form(lab):
    r = lab["client"].post("/v2/sdn/response/resp-gone/classify", data={"list": "Default"})
    _beside(r, 404, "no response resp-gone is awaiting a person")


def test_a_refused_auto_is_drawn_beside_its_form(lab):
    assert mark_stage(lab["client"], "lab").status_code == 200
    r = lab["client"].post("/v2/sdn/mode", data={"list": "Default", "mode": "auto",
                                                 "reason": "", "hours": "1", "risk": "low"})
    _beside(r, 409, "recorded reason")


def test_a_refused_stop_is_drawn_beside_its_form(lab):
    r = lab["client"].post("/v2/sdn/loop", data={"list": "Default", "run": "stop"})
    _beside(r, 409, "no loop is running on Default")


def test_a_loop_pass_proposing_a_response_announces_a_key_the_region_relays(lab,
                                                                            monkeypatch):
    """The pass's own announcement (`run_pass`, as its job) against the region's `hx-trigger`
    and the page's relays (`NMAS.subscribe` in static/js/nmas_v2.js)."""
    from modules import invalidation as I
    from modules.sdn import closed_loop as CL

    heard = []
    monkeypatch.setattr(I, "_emitter", lambda event, msg: heard.append(msg))
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: {})
    out = LP.run_pass("Default", collect=collected, now=lambda: T0,
                      observe=lambda n, got: dict(observed(fired=["k1"])(n, got),
                                                  changed=True),
                      driver=lambda n, c: {"ok": False, "error": "unused"})
    assert out["proposed"], out
    html = lab["client"].get("/v2/sdn/responses?list=Default").get_data(as_text=True)
    region = re.search(r'<div id="sdn"[^>]*\shx-trigger="([^"]+)"', html)
    assert region, "the region draws its listener"
    listens = set(re.findall(r"nmas:([a-z_]+) from:body", region.group(1)))
    js = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
    relayed = set(re.findall(r"NMAS\.subscribe\('([a-z_]+)'", js))
    announced = {k for m in heard for k in m["keys"]}
    assert announced & listens & relayed, (announced, listens)


# ── In a real browser ─────────────────────────────────────────────────────────────────────

READY = ("return !!window.htmx && !!document.getElementById('sdn') && "
         "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')")


def test_after_a_refused_dismiss_the_region_still_draws_a_new_response(lab):
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as A

    a = LP.propose("Default", _det("k-a", "192.0.2.1"), "drop_source", "low", why="HITL")
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url(f"/v2/sdn/responses?list=Default&incident={a['id']}"))
            b.wait_for(READY, 15)
            b.wait_for("return window.NMAS && NMAS.live().state === 'connected'", 15)
            # Another person dismissed it first; this page still offers Dismiss.
            LP.resolve("Default", a["id"], "dismissed", actor="other@example.com",
                       why="seen to")
            b.js(f"var f = document.querySelector('form[hx-post*=\"/response/{a['id']}"
                 "/dismiss\"]'); f.querySelector('input[name=reason]').value = 'mine';"
                 " f.querySelector('button[type=submit]').click(); return 1")
            b.wait_for("return !!document.querySelector('#sdn .sdn-ans-bad')", 15)
            b.wait_for(READY, 15)
            after = b.js(
                "var r = document.getElementById('sdn'), p = r && r.querySelector('.sdn-ans-bad');"
                "return {region: !!r, listens: r && r.getAttribute('hx-trigger'),"
                " stale: !!(r && r.querySelector('.stale-note')),"
                " beside: !!(p && p.previousElementSibling &&"
                " p.previousElementSibling.matches('form.sdn-dismiss')),"
                " words: p ? p.textContent.replace(/\\s+/g, ' ').trim() : ''}")
            # The typed reason holds a live redraw (C459); emptied, nothing holds it.
            b.js("var i = document.querySelector('#sdn input[name=reason]');"
                 " if (i) { i.value = ''; } return 1")
            fresh = LP.propose("Default", _det("k-b", "192.0.2.9"), "drop_source", "low",
                               why="HITL")
            LP._announce("Default", ["sdn"], "sdn-loop-Default-probe")
            started = time.monotonic()
            b.wait_for(f"return !!document.getElementById('sdn-i-{fresh['id']}')", 15)
            took = time.monotonic() - started
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert after["region"] and after["listens"] == "nmas:sdn from:body", after
    assert after["stale"] and after["beside"], after
    assert after["words"].startswith("Not saved: no response"), after
    assert took < 15
