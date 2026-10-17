"""A v2 control that posts is busy on itself until its answer is drawn (C1023, the operator's B1
from walk W2, 2026-10-17).

CLAUDE.md: "A v2 control is busy on itself until the answer arrives (never a timer) and the
result updates in place; no narration beside it, provenance on hover; no toast." On W2 NetBox's
Import showed nothing until its card drew, and the operator started a second run (two running,
from 22:50Z and 22:51Z); the remote's write probe and Templates' Approve did the same.

**The cause, measured:** every one of them is the submit button of a `<form hx-post>`. htmx
reads `hx-disabled-elt`, and puts its `htmx-request` class, on the element that ISSUES the
request (htmx 2.0.11, `addRequestIndicatorClasses` and `disableElements`, reading the attribute
from that element up through its ancestors). For a form that is the form, never the button
inside it, so the button's own `hx-disabled-elt="this"` was never read, it stayed enabled, and
its `op-busy` words (`.htmx-request > .op-busy`) never showed. A button carrying its own
`hx-post` issues its request itself, and was busy as declared. tests/test_v2_one_confirm.py
checked the declaration on the confirm buttons, never its effect.

**The one mechanism:** `nmas_v2.js` (loaded by every v2 page) holds the button that submitted a
form whose request htmx sends (the submit event's `submitter`, else the form's one submit
button declaring it) exactly as htmx holds a button that posts itself: disabled, `htmx-request`
and `aria-busy`, until `htmx:afterRequest`, which follows the swap. No timer. So the declaration
is one shape whatever issues the request: `hx-disabled-elt="this"` on the button, its idle words
in `op-idle` and what runs in `op-busy`.

**The population, by property:** every control in a v2 template that sends a POST through htmx
when a person presses it: (1) a `<button>` carrying `hx-post`; (2) each submit button of a
`<form>` carrying `hx-post`: in the form's body, in a template the body includes, or outside it
naming it by `form="<id>"` (a `type="button"` or `"reset"` button, or one with a request or
`formaction` of its own, is not the form's submit). Whether a route is slow is a fact about the
world at run time (a device, NetBox, the git remote, a job), not something a scan can read, so
the population is every POST a person presses: the superset. Elements that post on `load` or as
text is typed are not pressed, and are outside it. The scripts' own posts (Alpine components
that `fetch` with POST, in the scripts a v2 template loads) are a second population: each sets
its `busy` before its fetch.

Each scan is run on planted cases it must find (`TestTheScansFind`); the browser test clicks
NetBox's Import with its answer held.
"""

import os
import re
import threading

import pytest

from tests.test_netbox_v2 import nb  # noqa: F401 (the fixture: NetBox replaced at its edge)
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: `nb` runs a job's thread inline by replacing `threading.Thread` (the module, so everywhere);
#: a served app needs real threads, its own and each request's.
_REAL_THREAD = threading.Thread

OPEN = re.compile(r"<(\w+)\b")
INCLUDE = re.compile(r"\{%-?\s*include\s+[\"'](v2/[\w.]+)[\"']")
FORM_ATTR = re.compile(r'\bform="([\w-]+)"')
ID_ATTR = re.compile(r'\bid="([\w-]+)"')
POSTS = re.compile(r"\bhx-post\s*=")
OWN_REQUEST = re.compile(r"\b(hx-(get|post|put|patch|delete)|formaction)\s*=")
NOT_SUBMIT = re.compile(r'\btype\s*=\s*"(button|reset)"')

#: Measured 2026-10-17 (C1023): 117 members (85 form submits, 32 buttons posting
#: themselves; 17 of them declared no busy words), and five Alpine components posting from a
#: v2 script. A scan that finds fewer has stopped seeing.
MEMBERS_FLOOR = 117
FORM_SUBMITS_FLOOR = 85
SCRIPT_POSTERS_FLOOR = 5


def _tag_end(text, i):
    from tests.test_controls_consult_may import _tag_end as end
    return end(text, i)


def _line(text, i):
    return text.count("\n", 0, i) + 1


def _buttons(text):
    """(start, tag, body) of every `<button>` in *text*."""
    for m in re.finditer(r"<button\b", text):
        end = _tag_end(text, m.start())
        close = text.find("</button>", end)
        yield m.start(), text[m.start():end + 1], text[end + 1:close if close > 0 else end + 1]


def _is_submit(tag):
    return not NOT_SUBMIT.search(tag) and not OWN_REQUEST.search(tag)


def _submits_through_includes(texts, path, start, end, seen):
    """Submit buttons in `texts[path][start:end]` (a form's body) and in every template it
    includes, each as (path, offset in its own template, tag, body); *seen* stops a cycle."""
    text, out = texts[path][start:end], []
    for s, tag, body in _buttons(text):
        if _is_submit(tag) and not FORM_ATTR.search(tag):
            out.append((path, start + s, tag, body))
    for inc in INCLUDE.findall(text):
        inc_path = "templates/" + inc
        if inc_path in seen or inc_path not in texts:
            continue
        out += _submits_through_includes(texts, inc_path, 0, len(texts[inc_path]),
                                         seen | {inc_path})
    return out


def members(texts: dict) -> list:
    """Every pressed control in *texts* ({path: template text}) that posts through htmx:
    dicts of `path`, `line`, `kind` ("button" or "form-submit"), `tag` and `body`. One member
    per place in a template, however many forms include it."""
    found, posting_forms = {}, set()

    def add(path, pos, kind, tag, body):
        found.setdefault((path, pos), {"path": path, "line": _line(texts[path], pos),
                                       "kind": kind, "tag": tag, "body": body})

    for path, text in texts.items():
        for m in OPEN.finditer(text):
            el = m.group(1).lower()
            if el not in ("button", "form"):
                continue
            end = _tag_end(text, m.start())
            tag = text[m.start():end + 1]
            if not POSTS.search(tag):
                continue
            if el == "button":
                add(path, m.start(), "button", tag, text[end + 1:text.find("</button>", end)])
                continue
            fid = ID_ATTR.search(tag)
            if fid:
                posting_forms.add(fid.group(1))
            close = text.lower().find("</form>", end)
            for hit in _submits_through_includes(texts, path, end + 1,
                                                 close if close > 0 else len(text), {path}):
                add(hit[0], hit[1], "form-submit", hit[2], hit[3])
    for path, text in texts.items():          # a submit button outside its form, naming it
        for s, tag, body in _buttons(text):
            f = FORM_ATTR.search(tag)
            if f and f.group(1) in posting_forms and _is_submit(tag):
                add(path, s, "form-submit", tag, body)
    return list(found.values())


def problems(member) -> list:
    """What keeps *member* from being busy on itself; empty when it is."""
    where = f"{member['path']}:{member['line']} ({member['kind']})"
    wrong = []
    if 'hx-disabled-elt="this"' not in member["tag"]:
        wrong.append(f'{where}: no hx-disabled-elt="this"')
    if not re.search(r'class="(?:[^"]*\s)?op-idle(?:\s[^"]*)?">\s*\S', member["body"]):
        wrong.append(f"{where}: no op-idle words")
    if not re.search(r'class="(?:[^"]*\s)?op-busy(?:\s[^"]*)?">\s*\S', member["body"]):
        wrong.append(f"{where}: no op-busy words naming what runs")
    return wrong


def _v2_templates() -> dict:
    from tests.source_index import tracked
    return {os.path.relpath(p, ROOT): open(p, encoding="utf-8").read()
            for p in tracked("templates/v2", suffix=".html")}


# ------------------------------------------------ the scripts' own posts

COMPONENT = re.compile(r"\b(?:Alpine|A)\.data\(\s*'(\w+)'")
POST_FETCH = re.compile(r"fetch\([^;]*?method:\s*'POST'", re.S)


def script_posters(sources: dict) -> list:
    """(script, component, busy-before-each-post) for every Alpine component in *sources*
    ({path: source}) that sends a POST with fetch."""
    out = []
    for path, src in sources.items():
        starts = [(m.start(), m.group(1)) for m in COMPONENT.finditer(src)]
        for i, (s, name) in enumerate(starts):
            chunk = src[s:starts[i + 1][0] if i + 1 < len(starts) else len(src)]
            posts = [p.start() for p in POST_FETCH.finditer(chunk)]
            if not posts:
                continue
            busy = all(re.search(r"\.busy\s*=\s*true", chunk[:p]) for p in posts)
            out.append((path, name, busy))
    return out


def _v2_scripts(texts) -> dict:
    from tests.test_v2_one_confirm import v2_scripts
    return {p: open(os.path.join(ROOT, p), encoding="utf-8").read() for p in v2_scripts(texts)}


@pytest.fixture(scope="module")
def survey():
    texts = _v2_templates()
    return {"texts": texts, "members": members(texts),
            "posters": script_posters(_v2_scripts(texts))}


class TestThePopulation:
    def test_the_floors(self, survey):
        found = survey["members"]
        assert len(found) >= MEMBERS_FLOOR, len(found)
        assert sum(m["kind"] == "form-submit" for m in found) >= FORM_SUBMITS_FLOOR
        assert len(survey["posters"]) >= SCRIPT_POSTERS_FLOOR, survey["posters"]

    def test_the_three_the_operator_met_are_members(self, survey):
        """NetBox's Import, the remote's write probe and Templates' Approve: W2's steps."""
        names = {(m["path"], re.sub(r"\s+", " ", m["body"])) for m in survey["members"]}

        def has(path, words):
            return any(p == path and words in b for p, b in names)
        assert has("templates/v2/netbox.html", "Import into NetBox…")
        assert has("templates/v2/_remote_setup.html", "Run the write probe")
        assert has("templates/v2/_template_op.html", "Approve {{ c.template }}")


class TestEveryMemberIsBusyOnItself:
    def test_every_member_declares_its_busy_words(self, survey):
        wrong = [w for m in survey["members"] for w in problems(m)]
        assert wrong == [], "\n".join(wrong)

    def test_every_component_posting_from_a_v2_script_is_busy_first(self, survey):
        wrong = [f"{p}: {name}" for p, name, busy in survey["posters"] if not busy]
        assert wrong == [], wrong

    def test_the_page_holds_a_forms_submitter_while_its_request_is_out(self):
        """The mechanism every form submit relies on, wired on every v2 page: held on
        `htmx:beforeSend`, released on `htmx:afterRequest` (the browser test clicks it)."""
        base = open(os.path.join(ROOT, "templates", "v2", "base.html"), encoding="utf-8").read()
        assert re.search(r"filename='js/nmas_v2\.js'", base)
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        assert re.search(r"addEventListener\('htmx:beforeSend',\s*holdSubmitter\)", src)
        assert re.search(r"addEventListener\('htmx:afterRequest',\s*releaseSubmitter\)", src)


class TestWhichButtonIsHeld:
    """`submitterOf`, the one choice the mechanism makes, run in duktape: the button that sent
    the form when the browser names it; else the form's one submit button declaring it; never a
    guess between two, never one that did not declare it."""

    def _pick(self, case):
        import json
        import dukpy
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        fixture = (
            "function btn(id, type, declared) { return {id: id, tagName: 'BUTTON', type: type,"
            " getAttribute: function (n) { return n === 'hx-disabled-elt' && declared ? 'this'"
            " : null; }}; }\n"
            "var go = btn('go', 'submit', true), plain = btn('plain', 'submit', false),"
            " back = btn('back', 'button', true), two = btn('two', 'submit', true);\n"
            "function form(els) { return {tagName: 'FORM', elements: els}; }\n"
            "var CASES = {\n"
            " named: [form([go, plain]), {submitter: go}],\n"
            " named_undeclared: [form([go, plain]), {submitter: plain}],\n"
            " unnamed_one: [form([back, go, plain]), {}],\n"
            " unnamed_two: [form([go, two]), {}],\n"
            " not_a_form: [{tagName: 'BUTTON', elements: []}, {submitter: go}]};\n")
        out = dukpy.evaljs("var window = {};\n" + src + "\n" + fixture
                           + f"var c = CASES['{case}'], b = window.NMAS_V2.submitterOf(c[0], c[1]);"
                           "JSON.stringify(b ? b.id : null);")
        return json.loads(out)

    @pytest.mark.parametrize("case,want", [("named", "go"), ("named_undeclared", None),
                                           ("unnamed_one", "go"), ("unnamed_two", None),
                                           ("not_a_form", None)])
    def test_the_choice(self, case, want):
        assert self._pick(case) == want


class TestTheScansFind:
    PLANTED = {
        "templates/v2/_a.html": (
            '<form hx-post="/x"><button type="submit" class="btn">Go</button></form>\n'
            '<form hx-post="/y">{% include "v2/_b.html" %}</form>\n'
            '<form id="f-c" hx-post="/z"></form>\n'
            '<button type="submit" form="f-c"><span class="op-idle">C</span></button>\n'
            '<button type="button" hx-post="/w" hx-disabled-elt="this">'
            '<span class="op-idle">W</span><span class="op-busy">Doing W…</span></button>\n'
            '<form hx-post="/v"><button type="button" hx-get="/u">Back</button>'
            '<button type="submit" hx-disabled-elt="this"><span class="op-idle">V</span>'
            '<span class="op-busy">Doing V…</span></button></form>\n'
            '<form hx-get="/t"><button type="submit">T</button></form>\n'),
        "templates/v2/_b.html": '<button type="submit" class="btn">In an include</button>',
    }

    def test_the_member_scan_finds_each_shape(self):
        found = members(self.PLANTED)
        kinds = sorted((m["path"], m["kind"]) for m in found)
        assert kinds == [("templates/v2/_a.html", "button"),
                         ("templates/v2/_a.html", "form-submit"),
                         ("templates/v2/_a.html", "form-submit"),
                         ("templates/v2/_a.html", "form-submit"),
                         ("templates/v2/_b.html", "form-submit")], kinds
        wrong = [w for m in found for w in problems(m)]
        assert len([w for w in wrong if "hx-disabled-elt" in w]) == 3, wrong
        assert any("_b.html" in w for w in wrong) and any("op-busy" in w for w in wrong)
        assert not any(":5 " in w or ":6 " in w for w in wrong), wrong

    def test_the_script_scan_finds_a_post_before_busy(self):
        src = ("A.data('late', function () { return { go: function () {"
               " fetch(u, {method: 'POST'}); this.busy = true; } }; });\n"
               "A.data('fine', function () { return { go: function () {"
               " self.busy = true; root.fetch(u, {\n method: 'POST' }); } }; });\n"
               "A.data('reads', function () { return { go: function () { fetch(u); } }; });")
        assert script_posters({"x.js": src}) == [("x.js", "late", False), ("x.js", "fine", True)]


# ------------------------------------------------ clicking NetBox's Import

def _browser_or_skip():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the static scans above still run")
    return browser


IMPORT = "#t-import"
MARK = ("var b = Array.prototype.find.call(document.querySelectorAll('#netbox-networks button'),"
        " function (x) { return /Import into NetBox/.test(x.textContent) && !x.disabled; });"
        "if (b) b.id = 't-import'; return !!b")
SHOWN = "var s = document.querySelector('#t-import .%s'); return !!(s && s.offsetParent !== null)"


@pytest.fixture
def held_import(nb, monkeypatch):  # noqa: F811
    """The real app served on loopback, NetBox's preview held until the test lets it answer."""
    browser = _browser_or_skip()
    import app as A
    from modules import netbox_jobs

    monkeypatch.setattr(threading, "Thread", _REAL_THREAD)
    gate, asked = threading.Event(), threading.Event()
    real = netbox_jobs.start_preview

    def held(*a, **k):
        asked.set()
        assert gate.wait(30), "the test never let the preview answer"
        return real(*a, **k)
    monkeypatch.setattr(netbox_jobs, "start_preview", held)
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            yield {"b": b, "srv": srv, "gate": gate, "asked": asked}
        finally:
            gate.set()
            b.go("about:blank")
            browser.close_socketio_sessions()


class TestNetBoxImportInABrowser:
    def test_busy_and_disabled_while_asked_and_free_once_its_card_draws(self, held_import):
        s, b = held_import, held_import["b"]
        b.go(s["srv"].url("/v2/netbox"))
        b.wait_for("return !!window.Alpine && !!window.htmx", 15)
        assert b.wait_for(MARK), "no enabled Import into NetBox… button"
        assert b.js(SHOWN % "op-idle") and not b.js(SHOWN % "op-busy")
        b.click(IMPORT)
        assert s["asked"].wait(10), "the click sent no preview"
        # Busy ON ITSELF while the answer is out: disabled, its busy words in place of its
        # idle ones, and nothing narrated beside it.
        b.wait_for("var x = document.querySelector('#t-import');"
                   "return x.disabled && x.getAttribute('aria-busy') === 'true'", 5)
        assert b.js(SHOWN % "op-busy") and not b.js(SHOWN % "op-idle")
        words = b.js("return document.querySelector('#t-import').innerText.trim()")
        assert words == "Starting the dry run…", words
        assert not b.js("return !!document.querySelector('#netbox-job .card-head')"), \
            "the card drew before its answer"
        s["gate"].set()
        # The answer draws in place; the button is free again with its idle words.
        b.wait_for("return !!document.querySelector('#netbox-job h2') && "
                   "/Import into NetBox: Branch/.test(document.querySelector('#netbox-job h2')"
                   ".textContent)", 15)
        b.wait_for("var x = document.querySelector('#t-import');"
                   "return x && !x.disabled && !x.hasAttribute('aria-busy') && "
                   "!x.classList.contains('htmx-request')", 5)
        assert b.js(SHOWN % "op-idle") and not b.js(SHOWN % "op-busy")

    def test_an_answer_that_fails_frees_it_too(self, held_import, monkeypatch):
        from modules import netbox_jobs
        s, b = held_import, held_import["b"]

        def broken(*a, **k):
            s["asked"].set()
            assert s["gate"].wait(30)
            raise RuntimeError("planted: the preview failed")
        monkeypatch.setattr(netbox_jobs, "start_preview", broken)
        b.go(s["srv"].url("/v2/netbox"))
        b.wait_for("return !!window.Alpine && !!window.htmx", 15)
        assert b.wait_for(MARK)
        b.click(IMPORT)
        assert s["asked"].wait(10)
        b.wait_for("return document.querySelector('#t-import').disabled", 5)
        s["gate"].set()
        b.wait_for("var x = document.querySelector('#t-import');"
                   "return x && !x.disabled && !x.hasAttribute('aria-busy')", 15)
        assert b.js(SHOWN % "op-idle") and not b.js(SHOWN % "op-busy")
