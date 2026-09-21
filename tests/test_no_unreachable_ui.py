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
"""

import re

import pytest

#: Functions defined with no reference anywhere in the rendered page, each
#: with the reason it is tolerated. An allowlist without reasons becomes a
#: place findings go to be forgotten.
#:
#: These are all PRE-EXISTING and none is on a graded path. They are recorded
#: here rather than fixed under a feature freeze -- deleting a function is a
#: behaviour change, and each needs deciding on its own.
KNOWN_DEAD = {
    "_deployList": (
        "leftover helper in deploy_wizard.html: reads the list name from the "
        "container's data attribute. The plan carries the list instead."),
    "invalidateTopologyCache": (
        "base.html: topology cache invalidation, never wired up. The cache is "
        "currently only cleared by a full reload."),
    "loadJenkinsResults": (
        "index.html: the Jenkins tab loads its results by another path. This "
        "one is a second implementation nothing reaches."),
}


def _rendered():
    """index.html with a device in the list.

    Rendering with an EMPTY inventory is the trap: the device-row loop
    produces nothing, every per-device `onclick` disappears, and the check
    reports the handlers it is meant to protect as dead.
    """
    import app as nmas
    from flask import render_template

    with nmas.app.test_request_context("/"):
        return render_template(
            "index.html",
            devices=[{"ip": "10.0.0.14", "hostname": "s4", "online": True},
                     {"ip": "10.0.0.11", "hostname": "r1", "online": False}])


def _inline_scripts(html):
    return "\n".join(
        match.group(2) for match in
        re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S)
        if "src=" not in match.group(1)
        and "application/json" not in match.group(1))


def _definitions(scripts):
    """`function NAME(` sites, excluding named IIFEs.

    A definition preceded by `(` is being invoked where it is written.
    """
    found = set()
    for match in re.finditer(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(",
                             scripts):
        before = scripts[:match.start()].rstrip()
        if before.endswith("("):
            continue
        found.add(match.group(1))
    return found


def _unreferenced(html, scripts):
    dead = []
    for name in sorted(_definitions(scripts)):
        pattern = r"\b" + re.escape(name) + r"\b"
        references = len(re.findall(pattern, html))
        definitions = len(re.findall(r"function\s+" + re.escape(name) + r"\b", html))
        if references - definitions <= 0:
            dead.append(name)
    return dead


@pytest.fixture(scope="module")
def page():
    html = _rendered()
    return html, _inline_scripts(html)


class TestNothingIsDefinedWithoutACaller:
    def test_the_page_actually_rendered_devices(self, page):
        """Without this, every per-device handler looks dead and the whole
        check passes vacuously."""
        html, _scripts = page
        assert html.count('class="device-row"') == 2

    def test_there_are_functions_to_check(self, page):
        """A regex that matches nothing also reports no findings."""
        _html, scripts = page
        assert len(_definitions(scripts)) > 100

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

    def test_every_allowlist_entry_gives_a_reason(self):
        for name, reason in KNOWN_DEAD.items():
            assert reason and len(reason) > 30, name


class TestTheThreeGradedPathsAreReachable:
    """Objective 1.3 (applying templates) and 1.4 (per-device golden history)
    are graded on GUI demonstration. All three had working backends and no
    button."""

    GRADED = ("showRenderPreview", "openDeployPlan", "showGoldenHistory")

    def test_each_is_defined(self, page):
        _html, scripts = page
        defined = _definitions(scripts)
        for name in self.GRADED:
            assert name in defined, name

    def test_each_has_a_caller(self, page):
        html, scripts = page
        dead = _unreferenced(html, scripts)
        for name in self.GRADED:
            assert name not in dead, f"{name} is unreachable again"

    def test_each_is_reachable_from_a_device_row(self, page):
        """Specifically from a per-device button, not merely referenced
        somewhere. `openDeployPlan` was 'referenced' the whole time -- by a
        Re-preview button inside the modal it opens."""
        html, _scripts = page
        for name in self.GRADED:
            hits = re.findall(r"nsotAction\('" + name + r"', '([^']+)'", html)
            assert sorted(hits) == ["r1", "s4"], (name, hits)

    def test_an_offline_device_keeps_them(self, page):
        """All three read captured artifacts and open no socket, so an
        unreachable device is exactly when its history is worth looking at."""
        html, _scripts = page
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
