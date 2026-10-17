"""A function nothing calls is a feature that does not exist.

Four times now, this project has shipped working code with no entry point:

1. the **Remote card** — `loadGoldenRepoPanel()` invoked it six lines before
   creating its container, so it returned quietly forever;
2. `showRenderPreview()` — render + round-trip coverage + host_vars, reachable
   only from `refreshCapture()`, which is itself reachable only from inside
   the preview it opens;
3. `openDeployPlan()` — the whole template-deploy path, reachable only from a
   *Re-preview* button inside the modal you could not open;
4. `showGoldenHistory()` — per-device golden history, **zero** callers.

Every one had a working backend and passing tests. Tests asserted the markup
*contained* the right strings and that the routes returned the right JSON.
Nothing asserted a human could get there, so the gap survived until someone
looked for a button and there was none.

This is the check that was run by hand after the fourth. It compares
definitions against references on the **rendered** page, so an `onclick` in a
Jinja loop counts as a caller and a partial that fails to render does not.

**Named IIFEs are not dead.** `(async function loadHistory() { ... })()` is
invoked at its own definition site, and counting it as uncalled is the
matcher being wrong rather than the code.

**The rendered page is the interface's pages** (tests/interface_pages.py): v2's, by the
links between them, and today's while they exist, with the scripts each loads (P7-19,
2026-10-15; until then today's index alone, so removing it would have emptied the check).
The two classes about today's device rows and dispatcher read today's index as before
(`todays_page`): their property is today's alone, and they leave with it (P7-27).
"""

import collections
import re

import pytest

#: Functions defined with no reference anywhere in the rendered page, each
#: with the reason it is tolerated.
#:
#: **Empty, and a test asserts it stays empty.** An allowlist with entries is
#: a place findings go to be forgotten; one that must stay empty is a gate.
#: Adding an entry is therefore a deliberate act with a reason attached, not
#: the path of least resistance when a test goes red.
#:
#: The three it held were each decided rather than defaulted (Stage 1.5):
#:
#: * ``_deployList`` -- a helper reading the list name off the wizard
#:   container. The plan carries the list, so nothing needed it. Deleted.
#: * ``loadJenkinsResults`` -- a second implementation. ``loadJenkinsTab()``
#:   is the live path and calls the same ``_renderJenkinsResults()`` renderer
#:   from ``/jenkins/sync``; this one fetched ``/jenkins/results``. Deleted.
#:   The route itself is left alone: it is API surface, not dead UI.
#: * ``invalidateTopologyCache`` -- inside the chat panel's IIFE, so the
#:   deploy code could not have called it even if someone had wanted to, and
#:   the legacy discovery keeps no such cache. Deleted -- and the staleness it
#:   was written to mitigate was fixed at the reader instead: the local-answer
#:   path read the topology cache with no age check at all, while a matching
#:   TTL had existed beside it the whole time.
KNOWN_DEAD = {}


def _rendered():
    """index.html with a device in the list.

    Rendering with an EMPTY inventory is the trap: the device-row loop
    produces nothing, every per-device `onclick` disappears, and the check
    reports the handlers it is meant to protect as dead.
    """
    import app as nmas
    from flask import render_template

    from tests.js_source import with_loaded_scripts

    with nmas.app.test_request_context("/"):
        # `with_loaded_scripts`: Stage 7 0b moved most of the script into
        # `static/js/gen`, so the rendered page now REFERENCES the
        # definitions this check looks for. Reading the page alone would
        # report every extracted function as unreachable -- and the floor
        # below (">= 100 functions") is what caught that, which is what the
        # floor is for.
        return with_loaded_scripts(render_template(
            "index.html",
            devices=[{"ip": "10.0.0.14", "hostname": "s4", "online": True},
                     {"ip": "10.0.0.11", "hostname": "r1", "online": False}]))


def _inline_scripts(html):
    return "\n".join(
        match.group(2) for match in
        re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S)
        if "src=" not in match.group(1)
        and "application/json" not in match.group(1))


def _definitions(scripts):
    """`function NAME(` sites, excluding named IIFEs.

    A definition preceded by `(` is being invoked where it is written. The
    character before it is found by walking back over whitespace, not by
    slicing the whole prefix: that copy per match cost O(n^2) (C45).
    """
    found = set()
    for match in re.finditer(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(",
                             scripts):
        i = match.start() - 1
        while i >= 0 and scripts[i].isspace():
            i -= 1
        if i >= 0 and scripts[i] == "(":
            continue
        found.add(match.group(1))
    return found


def _unreferenced(html, scripts):
    """Every definition whose name appears nowhere but its own definition.

    Counted in ONE pass over the page (C45): for a name made only of word
    characters, `\\bNAME\\b` matches exactly a maximal run of word characters
    equal to NAME, which is what a Counter over `\\w+` counts, and likewise for
    `function\\s+NAME\\b`. It ran two regular expressions over the whole
    rendered page per name, about 3,000 scans a run. A name containing `$`
    keeps the per-name expressions, since `$` is not a word character.
    """
    words = collections.Counter(re.findall(r"\w+", html))
    defined = collections.Counter(re.findall(r"function\s+(\w+)", html))
    dead = []
    for name in sorted(_definitions(scripts)):
        if re.fullmatch(r"\w+", name):
            references, definitions = words[name], defined[name]
        else:
            references = len(re.findall(r"\b" + re.escape(name) + r"\b", html))
            definitions = len(re.findall(r"function\s+" + re.escape(name) + r"\b", html))
        if references - definitions <= 0:
            dead.append(name)
    return dead


@pytest.fixture(scope="module")
def page():
    from tests import interface_pages

    html = interface_pages.corpus()
    return html, _inline_scripts(html)


@pytest.fixture(scope="module")
def todays_page():
    """Today's index with two devices, one online: the device rows' own classes below."""
    html = _rendered()
    return html, _inline_scripts(html)


class TestNothingIsDefinedWithoutACaller:
    def test_the_page_actually_rendered_devices(self, page):
        """Without this, every per-device handler looks dead and the whole
        check passes vacuously. v2's Devices page lists the lab's two devices, each a link
        to its page."""
        from tests import interface_pages

        devices = interface_pages.pages()["v2"]["/v2/devices"]
        for name in ("r3", "r9"):
            assert re.search(rf'href="/v2/device/{name}[?"]', devices), name

    def test_there_are_functions_to_check(self, page):
        """A regex that matches nothing also reports no findings. The floor is v2's pages
        alone, which define 214 functions (403 with today's; measured 2026-10-15)."""
        from tests import interface_pages

        _html, scripts = page
        v2 = _definitions(_inline_scripts(interface_pages.v2_corpus()))
        assert len(v2) > 150, len(v2)
        assert v2 <= _definitions(scripts)

    def test_no_new_unreachable_function(self, page):
        html, scripts = page
        dead = set(_unreferenced(html, scripts))
        new = dead - set(KNOWN_DEAD)
        assert not new, (
            f"defined but never called: {sorted(new)}. Either wire it to "
            f"something a human can click, or add it to KNOWN_DEAD with the "
            f"reason. A working backend with no entry point is not a feature.")

    def test_the_allowlist_has_no_stale_entries(self, page):
        """An entry that is now called must be removed, or the allowlist
        stops describing anything."""
        html, scripts = page
        dead = set(_unreferenced(html, scripts))
        stale = set(KNOWN_DEAD) - dead
        assert not stale, (
            f"these are reachable now and should leave KNOWN_DEAD: "
            f"{sorted(stale)}")

    def test_the_allowlist_is_empty(self):
        """A gate, not a parking space.

        An allowlist with entries is somewhere findings go to be forgotten.
        Keeping it empty makes adding one a deliberate act with a reason
        attached, rather than the path of least resistance when a test goes
        red.
        """
        assert KNOWN_DEAD == {}, (
            f"{sorted(KNOWN_DEAD)} are allowlisted. Wire each to something a "
            f"human can click, or delete it.")

    def test_every_allowlist_entry_gives_a_reason(self):
        """Still enforced, for whenever an entry is genuinely warranted."""
        for name, reason in KNOWN_DEAD.items():
            assert reason and len(reason) > 30, name


class TestTheThreeGradedPathsAreReachable:
    """Objective 1.3 (applying templates) and 1.4 (per-device golden history)
    are graded on GUI demonstration. All three had working backends and no
    button.

    The first, today's template preview (`showRenderPreview`), left with today's template
    editor at 7.8 (2026-10-17, P7-23): a device's render against its golden is its Intent
    tab's check and its Deploy… plan on v2. The second, today's deploy plan
    (`openDeployPlan`), left with today's deploy wizard at 7.8 (2026-10-17, P7-25): a
    device's Deploy… on v2 (tests/test_device_deploy_v2.py). The third stays until P7-27."""

    GRADED = ("showGoldenHistory",)

    def test_each_is_defined(self, todays_page):
        _html, scripts = todays_page
        defined = _definitions(scripts)
        for name in self.GRADED:
            assert name in defined, name

    def test_each_has_a_caller(self, todays_page):
        html, scripts = todays_page
        dead = _unreferenced(html, scripts)
        for name in self.GRADED:
            assert name not in dead, f"{name} is unreachable again"

    def test_each_is_reachable_from_a_device_row(self, todays_page):
        """Specifically from a per-device button, not merely referenced
        somewhere. `openDeployPlan` was 'referenced' the whole time -- by a
        Re-preview button inside the modal it opens."""
        html, _scripts = todays_page
        for name in self.GRADED:
            hits = re.findall(r"nsotAction\('" + name + r"', '([^']+)'", html)
            assert sorted(hits) == ["r1", "s4"], (name, hits)

    def test_the_deploy_plan_left_with_its_wizard(self, todays_page):
        """Nothing on today's page names the removed wizard's opener, so no button calls a
        function the page no longer defines (the dispatcher would report it, loudly)."""
        html, scripts = todays_page
        assert "openDeployPlan" not in html and "openDeployPlan" not in _definitions(scripts)

    def test_an_offline_device_keeps_them(self, todays_page):
        """All three read captured artifacts and open no socket, so an
        unreachable device is exactly when its history is worth looking at."""
        html, _scripts = todays_page
        assert "nsotAction('showGoldenHistory', 'r1')" in html


class TestTheDispatcherFailsLoudly:
    """A `typeof` guard that skips quietly is how the Remote card failed:
    the symbol was absent, the click did nothing, and nothing distinguished
    'not wired' from 'nothing to show'."""

    def _dispatcher(self):
        with open("templates/partials/device_nsot_actions.html",
                  encoding="utf-8") as handle:
            return handle.read()

    def test_a_missing_function_is_reported_not_skipped(self):
        source = self._dispatcher()
        guard = source[source.index("if (typeof fn !== 'function')"):]
        guard = guard[:guard.index("return;")]
        assert "console.error" in guard
        assert "showToast" in guard or "alert" in guard

    def test_it_never_returns_silently(self):
        """Every early exit must have said something first.

        Scoped to the preceding few lines rather than "since the last `{`":
        the nearest brace is the `else { window.alert(msg); }` branch, which
        speaks perfectly well, so the narrow matcher failed on correct code.
        """
        source = self._dispatcher()
        speaks = ("console.error", "showToast", "alert")
        for match in re.finditer(r"return;", source):
            window = source[max(0, match.start() - 500):match.start()]
            assert any(word in window for word in speaks), (
                "a silent return is the defect this dispatcher exists to end")

    def test_a_throwing_function_is_also_reported(self):
        """A modal that throws while opening leaves a backdrop and no
        content, which reads as a hung page rather than an error."""
        source = self._dispatcher()
        assert "catch (e)" in source
        tail = source[source.index("catch (e)"):]
        assert "console.error" in tail
        assert "failed" in tail

    def test_it_is_its_own_script_block(self):
        """Not appended to another partial's block, so a parse error
        elsewhere cannot take the buttons down with it."""
        source = self._dispatcher()
        assert source.count("<script>") == 1
        assert "function nsotAction" in source
