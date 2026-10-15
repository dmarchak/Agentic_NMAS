"""Stage 7 acceptance criterion 6 on v2: ONE pattern for preview and confirm (P7-06, 2026-10-15).

NSOT_STAGE7_PLAN.md section 10, criterion 6: "every task listed in section 2.1 goes through the
one preview-then-confirm component, and a test asserts no second confirm implementation
exists". tests/test_preview_confirm.py's `TestNoSecondImplementation` holds it for today's
pages (their client-side renderer, `nmas_preview_confirm.js`). Today's pages go at cutover; this
holds it for v2, whose previews are drawn on the server and confirmed in place.

**The population, by property:** every route that sends a confirm (`route_gates` kind
`confirm`), and every route that confirms a preview (`operation_stages.STAGES` naming a preview
endpoint the app serves): the five-stage lifecycle's confirm and approve routes. 55 when this
was written. Each one is, exactly one of:

- **reached from v2 in THE pattern**, at every place a v2 template names it: htmx posts it
  (`hx-post` on the button, or on the form whose submit button it is), and the confirm button
  is busy on itself (`hx-disabled-elt="this"`, its `op-idle` and `op-busy` words), names its
  operation (`data-op`, the manual's "How does this work?"), draws its state from `may`
  (`gate()`, criterion 13), and the request carries the field the route binds the confirm to
  (`operation_stages`' hash stage: a hidden input, `hx-vals`, or the URL), so what is confirmed
  is what was previewed. 30 routes when this was written;
- **a second implementation, named** (`SECOND_IMPLEMENTATIONS`, only shrinking): an Alpine
  component that posts the confirm itself. Four when this was written (register finding, P7-06);
- **today's route, not named by any v2 template** (`LEGACY_HOMES`, exact): with the v2 route
  that does its job (itself in the pattern), or why it has none. Removed at cutover.

And nothing on v2 asks the browser: no `confirm()`, `alert()` or `prompt()` in a script v2
loads, no `hx-confirm` or `hx-prompt` (htmx's own `window.confirm`) in a v2 template; and no
v2 page loads today's client-side preview renderer.

Each scan is run on a planted case it must find (`TestTheScansFind`).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

URL = re.compile(r"url_for\(\s*['\"]([\w.]+)['\"]")
OPEN = re.compile(r"<(\w+)\b")
XDATA = re.compile(r'\bx-data="(\w+)"')

#: Measured 2026-10-15 (P7-06): the population, the routes reached in the pattern, and the
#: scripts v2 loads. Floors: a scan that finds fewer has stopped seeing.
POPULATION_FLOOR = 55
PATTERN_FLOOR = 30
V2_SCRIPTS_FLOOR = 12

#: Confirms v2 posts some other way: the Alpine component (its x-data name) -> its script, the
#: routes it posts, and why it is not the pattern. ONLY SHRINKS (ceiling below); each is a
#: register finding to bring onto the pattern, or to remove with its screen.
SECOND_IMPLEMENTATIONS = {
    "applyConfirm": ("static/js/nmas_apply.js",
                     {"v2.profile_apply_confirm", "v2.history_reapply_confirm"},
                     "the batch Apply, Coverage's Deploy missing and History's Re-apply post a "
                     "JSON body by fetch and fetch the job card themselves"),
    "ipslaPost": ("static/js/nmas_apply.js", {"v2.ip_sla_commit", "v2.ip_sla_policy_set"},
                  "IP SLA's page, built without a board (signed_off_screens.UNSIGNED); it goes "
                  "with the monitoring templates (P.12, D3)"),
    "update": ("static/js/nmas_update.js", {"update.apply"},
               "the Update follows the updater's own record while this app restarts under it, "
               "which an htmx swap from the app cannot"),
    "stepDone": ("static/js/nmas_update.js", {"update.step_done"},
                 "a person saying a host step is done: no preview, and nothing previewed to "
                 "bind (operation_stages: n/a)"),
}
SECOND_IMPLEMENTATIONS_CEILING = 4

#: A route in the pattern whose binding is held on the server, named in the URL, not carried by
#: the request: route -> where it is held.
BOUND_ON_THE_SERVER = {
    "netbox_v2.confirm": "the job the URL names holds the one-shot token its preview minted "
                         "(netbox_jobs, netbox_ops.authorize); the page never holds it",
}

#: Today's routes no v2 template names: route -> (the v2 route that does its job, in the
#: pattern) or (None, why it has none). Exact. They go at cutover (docs/CUTOVER.md).
LEGACY_HOMES = {
    "deploy.apply": "device_v2.deploy_confirm",
    "golden.capture_apply": "device_v2.capture_confirm",
    "golden.restore_apply": "device_v2.restore_confirm",
    "netbox_safety.apply_import": "netbox_v2.confirm",
    "netbox_safety.apply_import_all": "netbox_v2.confirm",
    "netbox_safety.apply_removal": "netbox_v2.confirm",
    "onboard.abandon": "onboard_v2.abandon",
    "onboard.create": "onboard_v2.create",
    "onboard.verify": "onboard_v2.verify",
    "persist.apply": "device_v2.persist_confirm",
    "retire.apply": "device_v2.retire_confirm",
    "rotate.apply": "device_v2.rotate_confirm",
    "run_command": (None, "the terminal's single command, removed at 7.8: v2 sends no typed "
                          "text (CLAUDE.md, no terminal steps); Run a privileged command… is "
                          "privileged_v2.confirm, an allowlisted recorded run"),
    "templates.approve": "templates_v2.approve",
    "templatize.edit_committed": "intent_v2.commit",
    "templatize.profile_propose_apply": "v2.profile_propose_commit",
    "templatize.retry_apply": "device_v2.retry_confirm",
    "templatize.revert_apply": "device_v2.revert_confirm",
    "templatize.seed_apply": "device_v2.seed_confirm",
}


def population() -> set:
    import app as A
    from modules.operation_stages import STAGES
    from modules.route_gates import GATES

    served = {r.endpoint for r in A.app.url_map.iter_rules()}
    out = {k for k, g in GATES.items() if g.kind == "confirm"}
    return out | {k for k, s in STAGES.items() if s.preview in served}


def binding_field(endpoint: str):
    """The request field `operation_stages` says the route binds its confirm to, or None."""
    from modules.operation_stages import STAGES
    s = STAGES.get(endpoint)
    if not s or s.hash.startswith(("n/a", "MISSING")):
        return None
    return s.hash.split()[0]


def _tag_end(text, i):
    from tests.test_controls_consult_may import _tag_end as end
    return end(text, i)


def references(texts: dict, wanted: set) -> list:
    """Every element in *texts* ({path: template text}) naming a wanted route: dicts of
    `path`, `endpoint`, `element`, `tag`, the element's `body` (to its close), and `xdata`
    (the component of the nearest enclosing or own `x-data`, if any)."""
    out = []
    for path, text in texts.items():
        for m in OPEN.finditer(text):
            end = _tag_end(text, m.start())
            tag = text[m.start():end + 1]
            eps = [e for e in URL.findall(tag) if e in wanted]
            if not eps:
                continue
            element = m.group(1).lower()
            close = text.lower().find(f"</{element}>", end)
            body = text[end + 1:close] if close > 0 else ""
            own = XDATA.search(tag)
            out.append({"path": path, "endpoint": eps[0], "element": element, "tag": tag,
                        "body": body, "xdata": own.group(1) if own else ""})
    return out


def _confirm_buttons(ref) -> list:
    """(button tag, its body) of the confirm a reference draws: the button itself, or each
    submit button of the form that sends the form's own request (a button with a request of its
    own, "Change the fields" back to the preview, is not the confirm)."""
    if ref["element"] == "button":
        return [(ref["tag"], ref["body"])]
    out = []
    for b in re.finditer(r"<button\b", ref["body"], re.I):
        s = b.start()
        btag = ref["body"][s:_tag_end(ref["body"], s) + 1]
        if re.search(r'type\s*=\s*"(button|reset)"', btag):
            continue
        if re.search(r"\b(hx-(get|post|put|patch|delete)|formaction)\s*=", btag):
            continue
        close = ref["body"].lower().find("</button>", s)
        out.append((btag, ref["body"][s + len(btag):close]))
    return out


def shape_problems(ref) -> list:
    """What makes this reference not THE pattern; empty when it is."""
    where = f"{ref['path']}: {ref['endpoint']}"
    if ref["element"] not in ("button", "form"):
        return [f"{where} is named by a <{ref['element']}>"
                + (f" (x-data {ref['xdata']!r})" if ref["xdata"] else "")
                + ", not posted by an htmx button or form"]
    if not re.search(r"\bhx-post\s*=", ref["tag"]):
        return [f"{where}: the {ref['element']} does not post it with htmx (hx-post)"]
    buttons = _confirm_buttons(ref)
    if not buttons:
        return [f"{where}: the form has no confirm button"]
    wrong = []
    for btag, bbody in buttons:
        for words, ok in (("data-op", 'data-op="' in btag),
                          ('hx-disabled-elt="this"', 'hx-disabled-elt="this"' in btag),
                          ("gate()", "gate('" in btag),
                          ("op-idle", 'class="op-idle"' in bbody),
                          ("op-busy", 'class="op-busy"' in bbody)):
            if not ok:
                wrong.append(f"{where}: its confirm button lacks {words}")
    field = binding_field(ref["endpoint"])
    if field and ref["endpoint"] not in BOUND_ON_THE_SERVER:
        scope = ref["tag"] + (ref["body"] if ref["element"] == "form" else "")
        if not (re.search(r'name="%s"' % re.escape(field), scope)
                or re.search(r'"%s"\s*:' % re.escape(field), scope)
                or re.search(r"\b%s=" % re.escape(field), ref["tag"])):
            wrong.append(f"{where}: the request does not carry {field!r}, the field the route "
                         "binds its confirm to (operation_stages)")
    return wrong


def _v2_templates() -> dict:
    from tests.source_index import tracked
    return {os.path.relpath(p, ROOT): open(p, encoding="utf-8").read()
            for p in tracked("templates/v2", suffix=".html")}


def v2_scripts(texts: dict) -> list:
    """The project's own scripts a v2 template loads (`js/nmas_*.js`), vendored libraries
    aside."""
    names = set()
    for text in texts.values():
        names |= set(re.findall(r"filename=['\"]js/(nmas_[\w]+\.js)['\"]", text))
    return sorted(os.path.join("static", "js", n) for n in names)


def _strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(^|[\s;{}()])//[^\n]*", r"\1", src)


DIALOG_CALL = re.compile(r"(?:(?<![\w.$])|\bwindow\.)(confirm|alert|prompt)\s*\(")
DIALOG_ATTR = re.compile(r"\bhx-(confirm|prompt)\s*=")


def dialog_calls(src: str) -> list:
    return [m.group(0) for m in DIALOG_CALL.finditer(_strip_js_comments(src))]


@pytest.fixture(scope="module")
def survey():
    texts = _v2_templates()
    pop = population()
    refs = references(texts, pop)
    return {"texts": texts, "population": pop, "refs": refs,
            "named": {r["endpoint"] for r in refs}}


class TestThePopulation:
    def test_the_floors(self, survey):
        assert len(survey["population"]) >= POPULATION_FLOOR, len(survey["population"])
        pattern = {r["endpoint"] for r in survey["refs"] if not shape_problems(r)}
        assert len(pattern) >= PATTERN_FLOOR, sorted(pattern)

    def test_every_route_is_in_the_pattern_a_named_second_or_todays(self, survey):
        named, second = survey["named"], set().union(
            *(eps for _s, eps, _w in SECOND_IMPLEMENTATIONS.values()))
        unplaced = sorted(survey["population"] - named - set(LEGACY_HOMES))
        assert unplaced == [], f"a confirm route v2 never names, and not today's: {unplaced}"
        assert not set(LEGACY_HOMES) & named, sorted(set(LEGACY_HOMES) & named)
        assert set(LEGACY_HOMES) <= survey["population"], sorted(
            set(LEGACY_HOMES) - survey["population"])
        assert second <= named, sorted(second - named)


class TestOnePattern:
    def test_every_place_v2_names_a_confirm_route_is_the_pattern(self, survey):
        """The second implementations are named, with their routes; anything else is
        refused, saying what it lacks."""
        wrong = []
        for r in survey["refs"]:
            listed = SECOND_IMPLEMENTATIONS.get(r["xdata"])
            if listed and r["endpoint"] in listed[1]:
                continue
            wrong += shape_problems(r)
        assert wrong == [], "\n".join(wrong)

    def test_the_second_implementations_only_shrink_and_are_real(self, survey):
        assert len(SECOND_IMPLEMENTATIONS) <= SECOND_IMPLEMENTATIONS_CEILING
        found = {(r["xdata"], r["endpoint"]) for r in survey["refs"] if r["xdata"]}
        for name, (script, eps, why) in SECOND_IMPLEMENTATIONS.items():
            assert {(name, e) for e in eps} <= found, f"{name} no longer posts {eps}: drop it"
            src = open(os.path.join(ROOT, script), encoding="utf-8").read()
            assert re.search(r"\.data\(\s*'%s'" % name, src), (name, script)
            assert why, name

    def test_a_route_bound_on_the_server_is_in_the_pattern_otherwise(self, survey):
        for ep in BOUND_ON_THE_SERVER:
            refs = [r for r in survey["refs"] if r["endpoint"] == ep]
            assert refs and all(not shape_problems(r) for r in refs), ep


class TestTodaysRoutes:
    def test_each_has_its_v2_home_in_the_pattern_or_says_why_none(self, survey):
        pattern = {r["endpoint"] for r in survey["refs"] if not shape_problems(r)}
        for ep, home in LEGACY_HOMES.items():
            if isinstance(home, tuple):
                assert home[0] is None and len(home[1]) > 40, ep
            else:
                assert home in pattern, f"{ep}'s v2 home {home} is not reached in the pattern"

    def test_no_legacy_route_is_a_v2_blueprints(self):
        v2ish = [ep for ep in LEGACY_HOMES if ep.split(".")[0].endswith("v2")]
        assert v2ish == [], v2ish


class TestNoBrowserDialog:
    def test_no_v2_script_calls_one(self, survey):
        scripts = v2_scripts(survey["texts"])
        assert len(scripts) >= V2_SCRIPTS_FLOOR, scripts
        found = {s: dialog_calls(open(os.path.join(ROOT, s), encoding="utf-8").read())
                 for s in scripts}
        assert {s: c for s, c in found.items() if c} == {}

    def test_no_v2_template_asks_htmx_to(self, survey):
        found = {p: DIALOG_ATTR.findall(t) for p, t in survey["texts"].items()}
        assert {p: f for p, f in found.items() if f} == {}

    def test_no_v2_page_loads_todays_preview_renderer(self, survey):
        """v2 draws every preview on the server; today's client-side renderer
        (`nmas_preview_confirm.js`, its `previewConfirmHtml` and `data-pc-part`) is today's."""
        loaded = [p for p, t in survey["texts"].items() if "nmas_preview_confirm" in t]
        assert loaded == []
        for s in v2_scripts(survey["texts"]):
            src = open(os.path.join(ROOT, s), encoding="utf-8").read()
            assert "previewConfirmHtml" not in src and "data-pc-part" not in src, s


class TestTheScansFind:
    """A planted second implementation, beside a real one in the pattern: each scan finds the
    plant and passes the real one."""

    REAL = ('<form class="op-ft" hx-post="{{ url_for(\'device_v2.reload_confirm\', name=h) }}">'
            '<input type="hidden" name="fingerprint" value="x">'
            '<span class="op-act"><button type="submit" class="btn" data-op="reload" '
            'hx-disabled-elt="this"{{ gate(\'confirm\') }}><span class="op-idle">Reload</span>'
            '<span class="op-busy">Reloading…</span></button></span></form>')

    def _refs(self, text):
        return references({"planted.html": text}, {"device_v2.reload_confirm"})

    def test_the_real_shape_passes(self):
        refs = self._refs(self.REAL)
        assert len(refs) == 1 and shape_problems(refs[0]) == []

    def test_an_alpine_confirm_is_found(self):
        planted = ('<div x-data="myConfirm" data-url="{{ url_for(\'device_v2.reload_confirm\') }}">'
                   '<button x-on:click="go">Reload</button></div>')
        wrong = shape_problems(self._refs(planted)[0])
        assert wrong and "x-data 'myConfirm'" in wrong[0]

    def test_a_confirm_that_is_not_busy_on_itself_is_found(self):
        planted = self.REAL.replace(' hx-disabled-elt="this"', "").replace(
            '<span class="op-busy">Reloading…</span>', "")
        wrong = shape_problems(self._refs(planted)[0])
        assert any('hx-disabled-elt="this"' in w for w in wrong)
        assert any("op-busy" in w for w in wrong)

    def test_a_plain_post_form_is_found(self):
        planted = self.REAL.replace('hx-post=', 'action=').replace('<form ', '<form method="post" ')
        assert "does not post it with htmx" in shape_problems(self._refs(planted)[0])[0]

    def test_a_confirm_bound_to_nothing_is_found(self):
        planted = self.REAL.replace('name="fingerprint"', 'name="other"')
        assert any("'fingerprint'" in w for w in shape_problems(self._refs(planted)[0]))

    def test_a_browser_dialog_is_found_and_a_method_named_confirm_is_not(self):
        assert dialog_calls("if (window.confirm('Sure?')) go();") == ["window.confirm("]
        assert dialog_calls("x = alert ('no');") == ["alert ("]
        assert dialog_calls("var y = prompt('reason');") == ["prompt("]
        assert dialog_calls("confirm: function () { this.confirm(); }") == []
        assert dialog_calls("/* confirm('in a comment') */ // alert('too')\n") == []
        assert DIALOG_ATTR.findall('<button hx-post="/x" hx-confirm="Sure?">') == ["confirm"]
