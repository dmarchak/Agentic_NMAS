"""The assistant chat in a real browser (the operator's order of 2026-11-28; board
assistant-chat; static/js/nmas_assistant.js, templates/v2/_assistant_panel.html). Firefox, the
app served from this process (tests/browser.py), the provider a fake (tests/
test_ai_assistant_stage2's `lab`), every person the harness's verified one (tests/conftest.py,
TEST_PERSON). Each test states the person's action and reads the page after it is drawn.

- Enter sends and Shift+Enter is a new line; the box grows with its text up to eight lines;
- the conversation keeps to its newest answer as one is drawn, unless the person scrolled up;
- the panel's left edge resizes it, by pointer and by the arrow keys, between 320 px and 60%
  of the window, the page reflowing beside it, and the width is remembered by this browser;
- Stop is in Send's place while a question is answered, and Send comes back at its end;
- the reads an answer ran are one collapsed line, each read opening to its record;
- Looking at follows the page's address as the person moves within a page and to another;
- only the newest planned answer previews when the panel opens, an older one on scroll (C4331).
"""
import pytest

from modules.ai import assistant_threads
from tests.conftest import TEST_PERSON
from tests.test_ai_assistant import world  # noqa: F401 (the fixture)
from tests.test_ai_assistant_stage2 import lab, words  # noqa: F401

PANEL_OPEN = ("var p = document.getElementById('asst-panel');"
              "return !!p && getComputedStyle(p).display !== 'none'"
              " && !!document.getElementById('asst-q');")
AT_FOOT = ("var l = document.getElementById('asst-answer');"
           "return l.scrollHeight - l.scrollTop - l.clientHeight <= 32;")
ENTER, SHIFT, NULL = "", "", ""


@pytest.fixture
def served(lab):  # noqa: F811
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as APP
    with browser.Served(APP.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1366, "height": 768})
            yield srv, b
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def _open(srv, b, path="/v2/devices"):
    b.go(srv.url(path))
    b.wait_for("return !!window.Alpine && !!window.htmx", 15)
    if not b.js(PANEL_OPEN):
        b.js("document.getElementById('nmas-assistant').click(); return 1")
    b.wait_for(PANEL_OPEN, 15)


def _keys(b, css, text):
    """Real key events into *css* in one WebDriver call (a modifier held until NULL)."""
    el = b._call("POST", f"/session/{b.session}/element", {"using": "css selector", "value": css})
    key = next(iter(el.values()))
    b._call("POST", f"/session/{b.session}/element/{key}/value", {"text": text})


def _drag(b, x, y, to_x):
    b._call("POST", f"/session/{b.session}/actions", {"actions": [{
        "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
        "actions": [{"type": "pointerMove", "x": int(x), "y": int(y), "origin": "viewport"},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pointerMove", "x": int(to_x), "y": int(y), "duration": 150,
                     "origin": "viewport"},
                    {"type": "pointerUp", "button": 0}]}]})
    b._call("DELETE", f"/session/{b.session}/actions")


def _press_key(b, value):
    b._call("POST", f"/session/{b.session}/actions", {"actions": [{
        "type": "key", "id": "kbd", "actions": [{"type": "keyDown", "value": value},
                                                {"type": "keyUp", "value": value}]}]})


def _long(n):
    return "\n\n".join(f"Paragraph {k} of answer {n}: " + "words " * 40 for k in range(3))


def _plant(n):
    for k in range(n):
        assistant_threads.keep(TEST_PERSON, f"Question {k}", "Devices · Lab",
                               {"state": "answered", "answer": _long(k), "sources": [],
                                "calls": [], "model_words": "Haiku 5.5", "cost_usd": 0.001})


def test_enter_sends_shift_enter_is_a_new_line_and_the_box_grows_to_eight_lines(lab, served):
    from modules.ai import manual_index
    srv, b = served
    chosen = manual_index.select("How do I reload a device safely?")
    lab["state"]["answer"] = words("Open the device page, then Actions › Reload….",
                                   cites=[chosen[0]["link"]])
    _open(srv, b)
    one = b.js("return document.getElementById('asst-q').offsetHeight")
    _keys(b, "#asst-q", "How do I reload")
    _keys(b, "#asst-q", SHIFT + ENTER + NULL)
    _keys(b, "#asst-q", "a device safely?")
    value = b.js("return document.getElementById('asst-q').value")
    turns = b.js("return document.querySelectorAll('#asst-answer .asst-turn').length")
    two = b.js("return document.getElementById('asst-q').offsetHeight")
    for _ in range(12):
        _keys(b, "#asst-q", SHIFT + ENTER + NULL)
    most = b.js("var q = document.getElementById('asst-q'); return [q.offsetHeight,"
                " getComputedStyle(q).overflowY, parseFloat(getComputedStyle(q).lineHeight)];")
    assert value == "How do I reload\na device safely?", repr(value)
    assert turns == 0, "Shift+Enter sent nothing"
    assert two > one, (one, two)
    height, overflow, line = most
    assert abs(height - (one + 7 * line)) <= 2 and overflow == "auto", (one, most)
    # Enter sends: the question is drawn in the conversation, the box emptied, the answer under it.
    b.js("var q = document.getElementById('asst-q'); q.value = 'How do I reload a device "
         "safely?'; q.dispatchEvent(new Event('input', {bubbles: true})); return 1")
    _keys(b, "#asst-q", ENTER)
    b.wait_for("return document.querySelectorAll('#asst-answer .asst-answer').length === 1", 15)
    said = b.js("return document.getElementById('asst-answer').textContent")
    left = b.js("var q = document.getElementById('asst-q'); return [q.value, q.offsetHeight];")
    assert "Actions › Reload…" in said and "How do I reload a device safely?" in said, said
    assert left == ["", one], left
    assert len(lab["sent"]) == 1


def test_it_keeps_to_the_newest_answer_unless_the_person_scrolled_up(lab, served):
    srv, b = served
    _plant(8)
    import time
    turns = {}
    for name in ("a", "b"):
        turn = f"t-{name * 16}"
        turns[name] = turn
        assistant_threads._write_turns(TEST_PERSON, dict(assistant_threads._turns(TEST_PERSON), **{
            turn: {"turn": turn, "at": "2026-11-28T00:00:0%dZ" % len(turns), "started": time.time(),
                   "alive": time.time(), "question": f"Working {name}", "looking_at": "",
                   "page": "/v2/devices", "steps": ["Asking the model"], "stop_at": None}}))
    _open(srv, b)
    b.wait_for(AT_FOOT, 5)
    long_got = {"state": "answered", "answer": _long(99), "sources": [], "calls": []}
    assistant_threads.finish(TEST_PERSON, turns["a"], long_got)
    b.js("htmx.trigger(document.body, 'nmas:assistant'); return 1")
    b.wait_for(f"var t = document.getElementById('asst-turn-{turns['a']}');"
               "return !!t && t.getAttribute('data-turn-state') === 'done';", 10)
    b.wait_for("return new Promise(function (r) { setTimeout(function () { r(true); }, 300); });")
    at_foot = b.js(AT_FOOT)
    b.js("var l = document.getElementById('asst-answer'); l.scrollTop = 0; return 1")
    b.wait_for("return new Promise(function (r) { setTimeout(function () { r(true); }, 300); });")
    assistant_threads.finish(TEST_PERSON, turns["b"], long_got)
    b.js("htmx.trigger(document.body, 'nmas:assistant'); return 1")
    b.wait_for(f"var t = document.getElementById('asst-turn-{turns['b']}');"
               "return !!t && t.getAttribute('data-turn-state') === 'done';", 10)
    b.wait_for("return new Promise(function (r) { setTimeout(function () { r(true); }, 300); });")
    top = b.js("return document.getElementById('asst-answer').scrollTop")
    assert at_foot is True, "at the foot, an answer drawn keeps it at the newest"
    assert top < 40, f"scrolled up, an answer drawn leaves the person where they read: {top}"


def test_the_left_edge_resizes_it_within_its_limits_and_the_width_is_remembered(lab, served):
    srv, b = served
    _open(srv, b)
    rect = ("var p = document.getElementById('asst-panel').getBoundingClientRect();"
            "var m = document.getElementById('main').getBoundingClientRect();"
            "return [Math.round(p.left), Math.round(p.width), Math.round(m.right),"
            " document.documentElement.clientWidth];")
    left, width, _main, vw = b.js(rect)
    _drag(b, left + 1, 300, left - 199)
    wider = b.js(rect)
    _drag(b, wider[0] + 1, 300, 5)
    widest = b.js(rect)
    _drag(b, widest[0] + 1, 300, vw - 5)
    narrowest = b.js(rect)
    b.js("document.querySelector('[data-asst-resize]').focus(); return 1")
    _press_key(b, "")      # ArrowLeft: wider by 16
    keyed = b.js(rect)
    kept = b.js("return localStorage.getItem('nmas-asst-width')")
    now = b.js("return document.querySelector('[data-asst-resize]').getAttribute('aria-valuenow')")
    b.go(srv.url("/v2/devices"))
    b.wait_for(PANEL_OPEN, 15)
    again = b.js(rect)
    assert abs(wider[1] - (width + 200)) <= 3, (width, wider)
    assert wider[2] <= wider[0] + 1, f"the page reflows beside the panel: {wider}"
    assert widest[1] == int(vw * 0.6), (vw, widest)
    assert narrowest[1] == 320, narrowest
    assert keyed[1] == 336 and kept == "336" and now == "336", (keyed, kept, now)
    assert again[1] == 336, f"remembered by this browser: {again}"


#: Which of Send and Stop a person sees in the box's slot.
SHOWN_CONTROL = ("var s = document.querySelector('#asst-act [data-asst-stop]');"
                 "var g = document.querySelector('#asst-act button[type=submit]');"
                 "return [s.checkVisibility(), g.checkVisibility()];")
PAUSE = "return new Promise(function (r) { setTimeout(function () { r(true); }, 300); });"


def test_stop_is_in_send_s_place_while_a_question_is_answered(lab, served):
    srv, b = served
    got = assistant_threads.begin(TEST_PERSON, "Is r2 up?", "Devices · Lab", "/v2/devices")
    assistant_threads.step(TEST_PERSON, got["turn"], "Asking the model")
    _open(srv, b)
    before = b.js(SHOWN_CONTROL)
    working = b.js("return document.querySelector('#asst-answer .asst-working').textContent")
    # Enter sends nothing while one is answered.
    _keys(b, "#asst-q", "another" + ENTER)
    b.wait_for(PAUSE)
    turns = b.js("return document.querySelectorAll('#asst-answer .asst-turn').length")
    b.click("[data-asst-stop]")
    b.wait_for("return document.getElementById('asst-answer').textContent"
               ".indexOf('Stopping: closing the model') >= 0;", 10)
    asked = assistant_threads.stop_asked(TEST_PERSON, got["turn"])
    stopping = b.js(SHOWN_CONTROL)
    from modules.ai import assistant
    assistant_threads.finish(TEST_PERSON, got["turn"], {"state": "stopped",
                                                        "detail": assistant.STOPPED})
    # The job's end is announced; here the test announces it, as the job would.
    b.js("htmx.trigger(document.body, 'nmas:assistant'); return 1")
    b.wait_for("return document.getElementById('asst-answer').textContent"
               ".indexOf('Stopped by you.') >= 0;", 10)
    b.wait_for(PAUSE)
    after = b.js(SHOWN_CONTROL)
    assert before == [True, False], before
    assert "Asking the model" in working, working
    assert turns == 1 and lab["sent"] == [], "Enter sent nothing while one was answered"
    assert asked is True and stopping == [True, False], (asked, stopping)
    assert after == [False, True], f"Send is back once the answer ended: {after}"


def test_its_reads_are_one_collapsed_line_and_each_opens_to_its_record(lab, served):
    srv, b = served
    from modules.nsot import reads
    run = reads.new_id()
    assistant_threads.keep(TEST_PERSON, "What version is r2 running?", "r2 (device) · Lab", {
        "state": "answered", "answer": "r2 runs 17.9.", "call_id": "ai-0123456789abcdef",
        "sources": [], "calls": ["ai-0123456789abcdef"],
        "reads": [{"id": "read:1", "words": "r2's version", "verdict": "run", "reason": "",
                   "device": "r2", "tab": "ask", "tab_words": "Ask the device", "run": run,
                   "network": "Lab"},
                  {"id": "read:2", "words": "r6's version", "verdict": "refused",
                   "reason": "r6 is not the device in view", "device": "r6", "tab": "ask",
                   "tab_words": "Ask the device", "run": "", "network": "Lab"}]})
    _open(srv, b)
    shown = ("return [document.querySelector('.asst-reads').open,"
             " document.querySelector('.asst-read').checkVisibility(),"
             " document.querySelector('.asst-reads > summary').textContent.trim()];")
    closed = b.js(shown)
    assert closed == [False, False, "Ran 2 reads"], closed
    b.click(".asst-reads > summary")
    opened = b.js(shown)
    assert opened[:2] == [True, True], opened
    first = b.js("var d = document.querySelector('.asst-read');"
                 "return [d.open, d.querySelector('p').checkVisibility()];")
    assert first == [False, False], first
    b.click(".asst-read > summary")
    record = b.js("var d = document.querySelector('.asst-read'); var a = d.querySelector('a');"
                  "return [d.open, d.querySelector('p').checkVisibility(),"
                  " a ? a.getAttribute('href') : ''];")
    assert record[:2] == [True, True] and f"/v2/show-commands/run/{run}" in record[2], record


def test_looking_at_follows_the_page_s_address(lab, served, monkeypatch):
    """Moving within a page (a device's tab, its address pushed) asks the server what the panel
    looks at again, and the next question carries the new address; another page draws its own."""
    from tests.test_v2_layout_in_a_browser import R2, R6
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(R2), dict(R6)])
    srv, b = served
    _open(srv, b, "/v2/device/r2?tab=overview&list=Lab")
    chip = "return document.getElementById('asst-place').getAttribute('data-asked');"
    first = b.js(chip)
    label = b.js("return document.getElementById('asst-place').textContent")
    b.click("a[hx-push-url*='tab=intent']")
    b.wait_for("return (document.getElementById('asst-place').getAttribute('data-asked') || '')"
               ".indexOf('tab=intent') >= 0;", 15)
    path = b.js("return document.querySelector('#asst-compose input[name=path]').value")
    b.go(srv.url("/v2/devices?list=Lab"))
    b.wait_for(PANEL_OPEN, 15)
    other = b.js("return document.getElementById('asst-place').textContent")
    assert "tab=overview" in first and "r2 (device)" in label, (first, label)
    assert "tab=intent" in path, path
    assert "Devices" in other and "r2 (device)" not in other, other


def test_only_the_newest_plan_previews_when_the_panel_opens(lab, served, monkeypatch):
    """C4331: a conversation of planned answers previewed every one of them (each a request
    running every step's preview) on every open of the panel. The newest answer's card loads at
    once; an older one's when the person scrolls it into view."""
    from routes import plans_v2
    asked = []

    def counted(call_id, network):
        asked.append(call_id)
        return None, "counted by the test"
    monkeypatch.setattr(plans_v2, "_answered_plan", counted)
    for k in range(20):
        assistant_threads.keep(TEST_PERSON, f"Change {k}", "Devices · Lab", {
            "state": "answered", "answer": _long(k), "sources": [], "calls": [],
            "call_id": f"ai-{k:016x}", "model_words": "Haiku 5.5", "cost_usd": 0.001,
            "plan": {"plan": "change", "list": "Lab", "title": f"Change {k}",
                     "params": {"steps": [{"operation": "intent-description", "params": {
                         "device": "edge1", "interface": "GigabitEthernet1",
                         "description": f"uplink {k}"}}]}}})
    import time

    def until(test, bound=15):
        end = time.monotonic() + bound
        while time.monotonic() < end and not test():
            time.sleep(0.1)
        return test()

    srv, b = served
    _open(srv, b)
    b.wait_for(AT_FOOT, 15)
    newest = until(lambda: f"ai-{19:016x}" in asked)
    time.sleep(1.5)                  # any other load-triggered card has asked by now
    opened = list(asked)
    b.js("document.getElementById('asst-answer').scrollTop = 0; return 1")
    first = until(lambda: f"ai-{0:016x}" in asked)
    assert newest, f"the newest answer's card never asked its preview: {asked}"
    assert len(opened) <= 3, f"the panel's open asked {len(opened)} previews: {opened}"
    assert first, "scrolled to the first answer, its card asked its preview"
