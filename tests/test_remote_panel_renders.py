"""The Remote card must render, and must say so when it does not.

It shipped in the page and was never called. `loadGoldenRepoPanel()` invoked
it at line 402 and created its container at line 408 — in the same function,
six lines later — so `getElementById` found nothing and the card returned
quietly. The result was a blank space, a clean console, and no request in the
server log. Nothing distinguished "not loaded" from "loaded and empty".

Two properties, both of which would have caught it before deployment:

* the container is **server-rendered and contains default text**, so a card
  that never runs leaves a visible message rather than whitespace;
* the card **initialises itself**, so no other block's internal call order can
  decide whether it runs.
"""

import os
import re

from tests.js_source import read_shipped

PARTIAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "templates", "partials", "golden_repo.html")


def _source():
    return read_shipped(PARTIAL)


def _scripts(text):
    return re.findall(r"<script[^>]*>(.*?)</script>", text, re.S)


def _markup(text):
    """The template with every script element removed."""
    return re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.S)


class TestTheContainerIsServerRenderedWithDefaultText:
    """An empty div can only ever look like success."""

    def test_the_container_is_in_the_markup_not_built_by_script(self):
        markup = _markup(_source())
        assert 'id="remotePanel"' in markup, (
            "the container is created by JavaScript, so anything that runs "
            "before it sees nothing to render into")

    def test_it_carries_a_visible_default_message(self):
        markup = _markup(_source())
        block = markup[markup.index('id="remotePanel"'):]
        block = block[:block.index("</div>", block.index("</div>") + 1)]
        assert "did not load" in block
        assert "console" in block.lower(), (
            "the default text should say where to look")

    def test_the_default_is_replaced_on_success(self):
        """Otherwise it would be permanent furniture rather than a signal."""
        script = "\n".join(_scripts(_source()))
        assert "host.innerHTML" in script

    def test_no_script_recreates_the_container(self):
        """Two owners of one id is how the first version went wrong."""
        for body in _scripts(_source()):
            assert 'id="remotePanel"' not in body, (
                "a script rebuilding the container reintroduces the ordering "
                "dependency this test exists to remove")


class TestTheCardInitialisesItself:
    """A component that needs another component's call order is not isolated."""

    def _blocks(self):
        """(index, body) for every inline script, parsed ONCE.

        Parsing twice and comparing with `is` compares two different string
        objects and always differs — which silently turned "no other block
        calls it" into "every block calls it".
        """
        return list(enumerate(_scripts(_source())))

    def _remote_block(self):
        for _i, body in self._blocks():
            if "function loadRemotePanel" in body:
                return body
        raise AssertionError("no script block defines loadRemotePanel")

    def _remote_index(self):
        for i, body in self._blocks():
            if "function loadRemotePanel" in body:
                return i
        raise AssertionError("no script block defines loadRemotePanel")

    def test_its_own_block_registers_its_own_initialiser(self):
        block = self._remote_block()
        assert re.search(r"addEventListener\(\s*['\"]DOMContentLoaded['\"]\s*,\s*"
                         r"loadRemotePanel\s*\)", block), (
            "the card must start itself, not wait to be called")

    def test_no_other_block_calls_it(self):
        """The dependency is removed, not merely guarded.

        A `typeof` guard made the failure silent without making it less
        likely: the symbol existed, the container did not, and the call was
        simply too early.
        """
        mine = self._remote_index()
        for i, body in self._blocks():
            if i == mine:
                continue
            assert "loadRemotePanel" not in body, (
                f"block {i} calls into the card and can get the order wrong")

    def test_a_missing_container_is_reported_not_swallowed(self):
        block = self._remote_block()
        head = block[block.index("function loadRemotePanel"):]
        head = head[:head.index("try {")]
        assert "console.error" in head, (
            "returning quietly is how this failed the first time")

    def test_a_failed_fetch_replaces_the_default_text(self):
        """Otherwise a broken endpoint looks identical to a card that never ran."""
        block = self._remote_block()
        # The catch CLAUSE, not the word — which also appears in a comment
        # explaining why try/catch cannot rescue a parse error.
        tail = block[block.index("} catch ("):]
        assert "innerHTML" in tail[:400]
        assert "failed to load" in tail[:400]


class TestTheCardUsesTheStatusEndpoint:
    """The symptom that exposed all of this: the browser never requested it."""

    def test_it_fetches_remote_status(self):
        block = "\n".join(_scripts(_source()))
        assert "'/remote/status'" in block or '"/remote/status"' in block

    def test_every_action_has_an_endpoint(self):
        block = "\n".join(_scripts(_source()))
        for path in ("/remote/verify", "/remote/verify-write", "/remote/preview",
                     "/remote/acknowledge", "/remote/push", "/remote/auto-push"):
            assert path in block, path


class TestResultsSurviveTheCardRefresh:
    """A failure reason that disappears is worse than none.

    Every action ends by refreshing the card, and the output area used to be
    inside the markup that refresh replaces — so a result flashed and was
    wiped. The operator knows something was said and cannot read it.
    """

    def _markup(self):
        return _markup(_source())

    def _scripts_joined(self):
        return "\n".join(_scripts(_source()))

    def test_the_output_area_is_outside_the_card(self):
        markup = self._markup()
        assert 'id="remoteOut"' in markup, (
            "the output area is built by the card, so the card's refresh "
            "destroys it")

    def test_the_card_does_not_rebuild_the_output_area(self):
        """Two owners of one id is exactly how the results vanished."""
        for body in _scripts(_source()):
            assert 'id="remoteOut"' not in body, (
                "a script recreating the output area wipes what is in it")

    def test_the_output_area_is_not_a_child_of_the_card(self):
        """Structurally outside, not merely declared before."""
        markup = self._markup()
        panel = markup.index('id="remotePanel"')
        out = markup.index('id="remoteOut"')
        between = markup[panel:out]
        assert between.count("</div>") >= between.count("<div"), (
            "remoteOut appears to be nested inside remotePanel")

    def test_results_are_kept_in_state_as_well(self):
        script = self._scripts_joined()
        assert "_remoteLastResult" in script
        assert "_remoteRestore" in script

    def test_the_card_restores_the_last_result_after_rendering(self):
        script = self._scripts_joined()
        body = script[script.index("function loadRemotePanel"):]
        body = body[:body.index("} catch (")]
        assert "_remoteRestore()" in body, (
            "a refresh that ignores the last result loses it on any re-render")

    def test_a_result_can_be_dismissed(self):
        script = self._scripts_joined()
        assert "remoteDismiss" in script
        assert "btn-close" in script

    def test_progress_messages_are_transient_and_results_are_not(self):
        """"verifying…" should not persist; the verification result should."""
        script = self._scripts_joined()
        assert "transient: true" in script
        # The spinner LITERALS, not the bare words — "pushing" also occurs in
        # prose ("rotating them after pushing does not unpublish them"), which
        # is how this assertion first failed on correct code.
        for spinner in ("'verifying\u2026'", "'probing write access\u2026'",
                        "'scanning history\u2026'", "'pushing\u2026'"):
            assert spinner in script, spinner
            window = script[script.index(spinner):][:90]
            assert "transient" in window, f"{spinner} persists as a result"
