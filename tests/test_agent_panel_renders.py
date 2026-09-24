"""The RENDERED panel, executed — not the payload, and not a grep.

Three guards in one feature each hid the same data, and **every test passed
at each stage while the screen said nothing**:

1. the route returned `{"entries": [], "status": {}}` with a 503 when AI was
   off — fixed, and the endpoint then carried 26 failures and the
   workspace-id rejection;
2. `success` meant "no exception reached the top", so a no-op run ended the
   failure streak — fixed, and the streak then read 26;
3. **the client had its own "disabled means show nothing" branch**, so the
   page still rendered *"AI is disabled — enable it in Settings"* with no
   count.

The boundary kept being drawn above the last remaining guard. A test that
asserts the endpoint carries the data cannot see a client that refuses to
draw it, and a test that greps the template for a string cannot see a branch
that returns before reaching it.

So this file **executes the shipped JavaScript**. `agentHealthBanner` and
`agentBadgeState` are pure — no DOM, no network — and are pulled out of the
**rendered page**, not a copy, so they cannot drift from what ships.
"""

import re

import pytest

from tests.js_source import with_loaded_scripts

dukpy = pytest.importorskip("dukpy")


WS = ("anthropic-workspace-id is required when authenticating with an "
      "identity-linked API key")

#: The health block the deployed endpoint actually returned, 2026-09-23.
LIVE_HEALTH = {
    "failing": True, "consecutive_failures": 26, "runs_since_ok": 27,
    "never_succeeded": True, "same_error": True, "same_error_count": 26,
    "last_error": WS, "last_failure_at": "2026-08-28 23:21:55",
    "runs_recorded": 27, "tool_calls_total": 0,
    "outcomes": {"ok": 0, "failed": 26, "interrupted": 0, "inconclusive": 1},
}


@pytest.fixture(scope="module")
def page():
    import app as nmas

    return with_loaded_scripts(nmas.app.test_client().get("/").get_data(as_text=True))


@pytest.fixture(scope="module")
def js(page):
    """The two pure functions, lifted out of the rendered page verbatim."""
    out = []
    for name in ("agentHealthBanner", "agentBadgeState"):
        start = page.index(f"function {name}(")
        depth, i, seen = 0, page.index("{", start), False
        while i < len(page):
            if page[i] == "{":
                depth += 1
                seen = True
            elif page[i] == "}":
                depth -= 1
                if seen and depth == 0:
                    break
            i += 1
        out.append(page[start:i + 1])
    return "\n".join(out)


def _run(js, expr, status):
    import json

    return dukpy.evaljs(js + "\n" + expr.replace("STATUS", json.dumps(status)))


def _disabled(**over):
    status = {"enabled": False, "ai_enabled": True, "paused": False,
              "user_active": False, "current_task": None,
              "health": dict(LIVE_HEALTH)}
    status.update(over)
    return status


class TestTheBannerRendersWhileDisabled:
    """The screen, with the exact payload the deployed instance returns."""

    def test_it_renders_something_at_all(self, js):
        html = _run(js, "agentHealthBanner(STATUS)", _disabled())
        assert html.strip(), "the panel rendered nothing while disabled"

    def test_it_shows_the_streak(self, js):
        html = _run(js, "agentHealthBanner(STATUS)", _disabled())
        assert "26 consecutive failed runs" in re.sub(r"\s+", " ", html)

    def test_it_names_the_error(self, js):
        html = _run(js, "agentHealthBanner(STATUS)", _disabled())
        assert "anthropic-workspace-id" in html

    def test_it_gives_the_time_of_the_last_failure(self, js):
        html = _run(js, "agentHealthBanner(STATUS)", _disabled())
        assert "2026-08-28 23:21:55" in html

    def test_it_says_they_will_not_retry(self, js):
        html = re.sub(r"\s+", " ", _run(js, "agentHealthBanner(STATUS)", _disabled()))
        assert "will not retry" in html

    def test_it_says_the_same_error_every_time(self, js):
        html = re.sub(r"\s+", " ", _run(js, "agentHealthBanner(STATUS)", _disabled()))
        assert "The same error every time" in html

    def test_it_says_it_has_never_completed_a_run(self, js):
        html = re.sub(r"\s+", " ", _run(js, "agentHealthBanner(STATUS)", _disabled()))
        assert "It has never completed a run." in html

    def test_it_says_no_tool_has_ever_executed(self, js):
        html = re.sub(r"\s+", " ", _run(js, "agentHealthBanner(STATUS)", _disabled()))
        assert "No tool has ever executed" in html

    def test_it_renders_with_the_AI_MASTER_switch_off_too(self, js):
        """The client keyed on `window._aiEnabled`, which is this one."""
        html = _run(js, "agentHealthBanner(STATUS)",
                    _disabled(ai_enabled=False))
        assert "26 consecutive failed runs" in re.sub(r"\s+", " ", html)

    def test_it_is_amber_when_disabled_and_red_when_live(self, js):
        off = _run(js, "agentHealthBanner(STATUS)", _disabled())
        live = _run(js, "agentHealthBanner(STATUS)",
                    _disabled(enabled=True, ai_enabled=True))
        assert "alert-warning" in off and "alert-danger" not in off
        assert "alert-danger" in live

    def test_a_healthy_agent_renders_nothing(self, js):
        """The banner must not become permanent furniture."""
        healthy = _disabled(enabled=True, health={"failing": False,
                                                  "never_succeeded": False})
        assert _run(js, "agentHealthBanner(STATUS)", healthy).strip() == ""

    def test_the_error_text_is_escaped(self, js):
        status = _disabled()
        status["health"]["last_error"] = "<script>alert(1)</script>"
        html = _run(js, "agentHealthBanner(STATUS)", status)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestTheBadgeRendersWhileDisabled:

    def test_it_carries_both_facts(self, js):
        state = _run(js, "JSON.stringify(agentBadgeState(STATUS))", _disabled())
        assert "Disabled · 26 failed" in state

    def test_the_ai_master_switch_gets_its_own_wording(self, js):
        """Two switches, two fixes. An operator who turns the wrong one back
        on has learned nothing from the badge."""
        state = _run(js, "JSON.stringify(agentBadgeState(STATUS))",
                     _disabled(ai_enabled=False))
        assert "AI off · 26 failed" in state

    def test_a_live_failure_is_red(self, js):
        state = _run(js, "JSON.stringify(agentBadgeState(STATUS))",
                     _disabled(enabled=True))
        assert "bg-danger" in state and "Failing (26)" in state

    def test_a_running_task_outranks_everything(self, js):
        state = _run(js, "JSON.stringify(agentBadgeState(STATUS))",
                     _disabled(current_task={"task": "x"}))
        assert "Running" in state

    def test_a_healthy_enabled_agent_is_active(self, js):
        state = _run(js, "JSON.stringify(agentBadgeState(STATUS))",
                     _disabled(enabled=True, ai_enabled=True,
                               health={"failing": False}))
        assert "Active" in state and "bg-success" in state


class TestTheClientGuardIsGone:
    """The third guard, pinned. It returned before any of the above ran."""

    def test_loadagenttab_has_no_show_nothing_branch(self, page):
        start = page.index("async function loadAgentTab()")
        body = page[start:start + 2500]
        assert "enable it in Settings to use the background agent" not in body, (
            "the client still replaces the panel with a disabled message")

    def test_it_calls_the_pure_renderers(self, page):
        start = page.index("async function loadAgentTab()")
        body = page[start:page.index("async function", start + 10)]
        assert "agentHealthBanner(status)" in body
        assert "agentBadgeState(status)" in body

    def test_the_badge_chain_exists_once(self, page):
        """An inline copy is how the badge and the banner came to disagree
        about what "disabled" means."""
        assert page.count("function agentBadgeState(") == 1
        assert page.count("badgeEl.textContent = 'Active'") == 0


class TestLoadAgentTabItself:
    """The only test in this file that spans the guard.

    **The pure-function tests above sit BELOW it.** They call
    `agentHealthBanner` directly, so they pass whether or not `loadAgentTab`
    ever reaches it — which is the same mistake, one layer down, that this
    whole feature has made three times. Proven: reinstating the client guard
    left nineteen of the twenty passing.

    So this class runs `loadAgentTab` itself, in duktape, against a stub DOM
    and a stub `fetch` returning the payload the deployed endpoint actually
    returns, and reads what lands in the elements. It is the only assertion
    here that can see a branch that returns early.
    """

    DOM = """
    var __els = {};
    function __el(id) {
      if (!__els[id]) __els[id] = {
        id: id, innerHTML: '', textContent: '', className: '', disabled: false,
        style: {}, title: '', parentNode: null,
        insertBefore: function (n) { __els[n.id] = n; },
        querySelector: function () { return null; },
        addEventListener: function () {},
      };
      return __els[id];
    }
    __el('agentActivityLog').parentNode = __el('__parent');
    var document = {
      getElementById: function (id) {
        // Only the ids the page actually creates; anything else is absent,
        // which is what a real page does and what the code must tolerate.
        return ['agentActivityLog','agentStatusBadge','agentPauseBtn',
                'agentBadge','agentFailureBanner','agentLiveTask',
                'agentTimersPanel','__parent'].indexOf(id) >= 0
               ? __el(id) : null;
      },
      createElement: function () { return __el('agentFailureBanner'); },
      querySelector: function () { return null; },
    };
    var window = {_aiEnabled: AI_ENABLED};
    var console = {error: function () {}, log: function () {}};
    var _agentPaused = false;
    function showToast() {}
    function _esc(s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    function loadAgentTimers() {}
    var fetch = function () {
      return {then: null, json: function () { return PAYLOAD; }, ok: true};
    };
    """

    def _run(self, page, payload, ai_enabled):
        """Execute the shipped `loadAgentTab` and return the stub DOM."""
        import json

        start = page.index("async function loadAgentTab()")
        end = page.index("\nasync function ", start + 10)
        source = page[start:end]

        # The two pure renderers it calls, also from the page.
        helpers = []
        for name in ("agentHealthBanner", "agentBadgeState"):
            s0 = page.index(f"function {name}(")
            depth, i, seen = 0, page.index("{", s0), False
            while i < len(page):
                if page[i] == "{":
                    depth += 1
                    seen = True
                elif page[i] == "}":
                    depth -= 1
                    if seen and depth == 0:
                        break
                i += 1
            helpers.append(page[s0:i + 1])

        dom = (self.DOM
               .replace("AI_ENABLED", "true" if ai_enabled else "false")
               .replace("PAYLOAD", json.dumps(payload)))

        # DUKTAPE PARSES `async` AND HAS NO EVENT LOOP, so calling an async
        # function returns a promise whose body never continues past the
        # first `await`. Measured: every element came back empty.
        #
        # So the asynchrony is stripped — and ONLY the asynchrony. `await X`
        # becomes `X`, which is correct here because the stub `fetch` returns
        # a plain object rather than a promise. **No branch is touched**, and
        # the guard under test is a branch, so the property survives the
        # transform. The assertions below confirm the strip applied; a
        # silent no-op would make this whole class vacuous, which is the
        # failure mode this file exists to stop repeating.
        stripped = source.replace("async function", "function")
        stripped = re.sub(r"\bawait\s+", "", stripped)
        assert stripped != source, "the async strip did nothing"
        assert "await " not in stripped
        source = stripped

        return dukpy.evaljs(
            dom + "\n".join(helpers) + "\n" + source
            + "\nloadAgentTab();\n"
            + "JSON.stringify({banner: __els['agentFailureBanner'] ? "
              "__els['agentFailureBanner'].innerHTML : '', "
              "badge: __els['agentStatusBadge'].textContent, "
              "log: __els['agentActivityLog'].innerHTML});")

    @pytest.fixture
    def rendered(self, page):
        payload = {"ok": True, "entries": [],
                   "status": {"enabled": False, "ai_enabled": False,
                              "paused": False, "user_active": False,
                              "current_task": None, "health": dict(LIVE_HEALTH)}}
        import json
        return json.loads(self._run(page, payload, ai_enabled=False))

    def test_the_banner_lands_in_the_dom(self, rendered):
        """With `window._aiEnabled === false` — the exact condition the old
        client guard returned on."""
        assert "26 consecutive failed runs" in re.sub(r"\s+", " ",
                                                      rendered["banner"])

    def test_the_error_lands_in_the_dom(self, rendered):
        assert "anthropic-workspace-id" in rendered["banner"]

    def test_the_badge_lands_in_the_dom(self, rendered):
        assert "26 failed" in rendered["badge"]

    def test_the_panel_is_not_replaced_by_a_disabled_message(self, rendered):
        assert "enable it in Settings" not in rendered["log"]


class TestTheTimersPanelDoesNotBlankItself:
    """The one other client loader found by the sweep that rendered nothing.

    `loadAgentTimers` did `panel.innerHTML = ''` when AI was off. Milder than
    the agent panel — a schedule is configuration rather than history — but
    the same instinct, and a schedule you cannot see is one you cannot check.

    The three other client loaders that short-circuit on an unconfigured
    state all render a reason and are correct: `loadRemotePanel` ("No remote
    for this list. Its history is on this host only."), `topoSvcRefresh`
    (names the setting), and `_stackRender` (shows the tool's own message).
    `base.html`'s single `_aiEnabled` guard is on a `setInterval` that
    auto-troubleshoots Jenkins failures — an action, correctly skipped.
    """

    def test_it_no_longer_blanks_the_panel(self, page):
        """Asserted on the ASSIGNMENT, not on a substring.

        The first version searched for `panel.innerHTML = ''` in the function
        body — and the comment explaining the fix quotes that exact code, so
        the test failed against correct code. Prose about code matching a
        grep for code, from the third direction this project has hit it.
        """
        start = page.index("async function loadAgentTimers()")
        body = page[start:start + 1600]
        blanking = [ln for ln in body.splitlines()
                    if re.match(r"\s*panel\.innerHTML\s*=\s*''\s*;", ln)]
        assert not blanking, blanking

    def test_it_renders_the_timers_with_the_note(self, page):
        start = page.index("async function loadAgentTimers()")
        assert "panel.innerHTML = note +" in page[start:start + 1600]

    def test_it_says_why_they_will_not_fire(self, page):
        flat = re.sub(r"\s+", " ", page)
        assert "none of these will fire" in flat

    def test_it_says_why_they_are_still_shown(self, page):
        """A phrase that does not span the JS concatenation. The first
        version spanned `... because a ' + 'schedule you cannot ...`."""
        flat = re.sub(r"\s+", " ", page)
        assert "you cannot see is one you cannot check" in flat
