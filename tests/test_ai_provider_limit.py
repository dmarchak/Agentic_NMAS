"""The provider's workspace usage limit (C2084; `anthropic_adapter.WorkspaceLimit`,
`modules/ai/provider_limit.py`, the gateway, the AI controls, the chip, the spend panel and
Needs attention).

On 2026-10-28 the provider refused every call with HTTP 400, ``invalid_request_error``, "You
have reached your specified workspace API usage limits. You will regain access on 2026-11-01 at
00:00 UTC.", and Mercury filed it as a malformed request (``bad_request``), so every AI feature
failed as if its request were wrong and nothing said AI was unavailable or until when. Each
test holds one purpose:

- the adapter: that refusal is its own kind, carrying its moment, asked once (never retried);
  a message naming no moment carries none; the moment's forms; another 400 (another message,
  or the phrase under another type) stays a bad request; the token count reads it the same;
- the gateway: the refusal recorded and said in the words every screen shares, the provider's
  own words on the row; every later call refused by Mercury without a provider request, also
  when another PROCESS met the limit; the card's Test, a person's press, still asks, and its
  answer clears the hold for every feature; a background call of the same task does not ask;
  after the moment a call asks again, and its answer clears the hold; one sent before the
  hold was recorded clears nothing; no moment named holds for `RECHECK_S`; an unreadable store
  is read as no hold; the store is owner-only;
- the screens: the words after a press (Ask in words) and before one (every AI control's
  reason, tests/ai_controls_check.py's state ``workspace_limit``, through each screen's route);
  in a real browser the moment in the viewer's own time with UTC's beside it;
- the chip: red, "AI unavailable until 1 Nov 00:00 UTC", its hover the provider's words and
  what lifts it, never blank; AI off still says AI off; the panel says it above what was spent;
- Needs attention: one row naming the provider's words and the moment, its action (raise the
  limit in the provider's console, then Test; or wait), clearing at the moment by time or when
  a call is answered; none with AI off.

The clock the hold is judged by is `provider_limit.clock`, set by each test to a moment before
or after the provider's, so no test depends on today's date.
"""
import datetime
import json
import os
import re
import stat
import subprocess
import sys
from html import unescape

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, connection, explain, gateway, provider_limit, triggers
from tests.ai_person import pressed_by
from tests.test_ai_gateway import KEY, _Resp, _Session, own_record  # noqa: F401 (the fixture)
# Ask in words' world (hosted AI allowed, a $1.50 day cap, a key, the record of AI calls in the
# test's folder) serves the gateway's tests and its page's alike.
from tests.test_ai_nl_query import site, world  # noqa: F401 (the fixtures)
from tests.test_history_ask_metrics import web  # noqa: F401 (the fixture)
# Settings › AI's world with a key set (a real settings file): the chip, the panel and Needs
# attention.
from tests.test_ai_spend_v2 import CHIP, PANEL, _chip, _get, spend  # noqa: F401
from tests.test_settings_ai_v2 import ai  # noqa: F401 (the fixture)
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACTOR = "operator@example.com"
#: The adapter's own send, kept before any test replaces it.
REAL_SEND = A.send
#: The provider's words of 2026-10-28, whole.
MESSAGE = ("You have reached your specified workspace API usage limits. You will regain "
           "access on 2026-11-01 at 00:00 UTC.")
#: What every screen says of it.
WORDS = ("AI is unavailable: the provider's workspace usage limit is reached, until 1 November "
         "2026 00:00 UTC; an admin raises it in the provider's console")
PING = {"content": [{"type": "text", "text": '{"echo": "w"}'}], "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 5}}


def _epoch(iso):
    return datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc).timestamp()


BEFORE = _epoch("2026-10-28T12:00:00Z")
MOMENT = _epoch("2026-11-01T00:00:00Z")


def _limited(message=MESSAGE, kind="invalid_request_error", status=400):
    return _Resp(status, {"type": "error", "error": {"type": kind, "message": message}})


@pytest.fixture
def clock(monkeypatch):
    """`provider_limit.clock`, set by the test: ``clock.t`` (before the provider's moment)."""
    class C:
        t = BEFORE
    monkeypatch.setattr(provider_limit, "clock", lambda: C.t)
    return C


class Provider:
    """The provider as the adapter meets it: each send goes through the real adapter against a
    fake session answering *answers* in turn (the limit's refusal, or a 200)."""

    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []

    def send(self, body, key):
        self.sent.append(body)
        item = self.answers.pop(0) if self.answers else _limited()
        return REAL_SEND(body, key, session=_Session(item), sleep=pytest.fail)


def _explain(send, actor=ACTOR):
    """A person's Explain through the gateway: a task the limit holds."""
    with pressed_by(actor):
        return gateway.ask("explain", explain.PROMPT, explain.SCHEMA_OF[explain.PROMPT[1]],
                           {"pack": "{}"}, actor=actor, trigger=triggers.person(actor),
                           send=send, today="2026-10-28")


def _test_press(send, actor=ACTOR):
    """A person's press of the AI card's Test: the connection check."""
    with pressed_by(actor):
        return gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                           actor=actor, trigger=triggers.person(actor), send=send,
                           today="2026-10-28")


def _rows():
    return calls.read()["rows"]


# ── The adapter ────────────────────────────────────────────────────────────────────────────

def test_the_workspace_limit_is_its_own_kind_with_its_moment_and_asked_once():
    s = _Session(_limited())
    with pytest.raises(A.WorkspaceLimit) as got:
        REAL_SEND({"model": "m"}, KEY, session=s, sleep=pytest.fail)
    exc = got.value
    assert exc.kind == "workspace_limit" and exc.until == "2026-11-01T00:00:00Z"
    assert (exc.status, exc.attempts, len(s.sent)) == (400, 1, 1), "never retried"
    assert exc.said == f"invalid_request_error: {MESSAGE}" and KEY not in str(exc)
    assert not isinstance(exc, A.BadRequest)


def test_a_limit_naming_no_moment_carries_none():
    s = _Session(_limited("You have reached your specified workspace API usage limits."))
    with pytest.raises(A.WorkspaceLimit) as got:
        REAL_SEND({}, KEY, session=s, sleep=pytest.fail)
    assert got.value.until is None


@pytest.mark.parametrize("text,moment", [
    (MESSAGE, "2026-11-01T00:00:00Z"),
    ("You will regain access on 2026-12-31 at 23:59:30 UTC.", "2026-12-31T23:59:30Z"),
    ("you will REGAIN ACCESS ON 2027-01-01 AT 06:00 utc", "2027-01-01T06:00:00Z"),
    ("You will regain access on 2026-13-01 at 00:00 UTC.", None),
    ("You will regain access on 2026-11-01 at 00:00.", None),
    ("You will regain access soon.", None),
    ("", None),
])
def test_the_moment_is_read_from_the_message(text, moment):
    assert A.regain_moment(text) == moment


@pytest.mark.parametrize("resp", [
    _limited("max_tokens: 99999 > 64000, the maximum for this model"),
    _limited("prompt is too long: 250000 tokens > 200000 maximum"),
    _limited(MESSAGE, kind="billing_error"),
    _Resp(400, None, text="<html>bad request</html>"),
    _Resp(400, {"error": {"type": "invalid_request_error"}}),
], ids=["max_tokens", "too_long", "phrase_under_another_type", "not_json", "no_message"])
def test_another_400_stays_a_bad_request(resp):
    with pytest.raises(A.AdapterError) as got:
        REAL_SEND({}, KEY, session=_Session(resp), sleep=pytest.fail)
    assert type(got.value) is A.BadRequest, type(got.value)


def test_the_token_count_reads_the_limit_the_same_way():
    with pytest.raises(A.WorkspaceLimit) as got:
        A.count_tokens({"model": "m", "messages": []}, KEY, session=_Session(_limited()))
    assert got.value.until == "2026-11-01T00:00:00Z"


# ── The gateway ────────────────────────────────────────────────────────────────────────────

def test_the_refusal_is_recorded_and_said_in_the_shared_words(world, clock):
    provider = Provider(_limited())
    got = _explain(provider.send)
    assert got["ok"] is False and got["error"] == "workspace_limit"
    assert got["detail"] == WORDS and len(provider.sent) == 1
    row = _rows()[0]
    assert row["verdict"] == "workspace_limit" and row["detail"] == WORDS
    assert row["limit"] == {"since": "2026-10-28T12:00:00Z", "until": "2026-11-01T00:00:00Z",
                            "recheck_at": "2026-11-01T00:00:00Z",
                            "provider": f"invalid_request_error: {MESSAGE}",
                            "call_id": row["id"]}
    assert row["attempts"] == 1


def test_every_later_call_is_refused_without_asking_the_provider(world, clock):
    provider = Provider(_limited())
    _explain(provider.send)
    second = _explain(provider.send)
    assert len(provider.sent) == 1, "the second call reached the provider"
    assert second["error"] == "workspace_limit" and second["detail"] == WORDS
    row = _rows()[0]
    assert row["verdict"] == "workspace_limit" and "request" not in row, "nothing was built"
    assert row["limit"]["until"] == "2026-11-01T00:00:00Z"


CHILD = r"""
import sys
sys.path.insert(0, sys.argv[1])
from modules.ai import anthropic_adapter as A, calls, provider_limit
calls._path = lambda: sys.argv[2]
exc = A.WorkspaceLimit("HTTP 400: limit", until="2026-11-01T00:00:00Z",
                       said="invalid_request_error: " + sys.argv[4], status=400)
hold = provider_limit.record(exc, call_id="ai-child", feature="explain",
                             now=float(sys.argv[3]))
print(hold["recheck_at"], flush=True)
"""


def test_a_limit_another_process_met_stops_this_one(world, clock):
    """The hold is the store's, not a process's memory: a worker process that met the limit
    (a child recording it) stops a call here, nothing sent."""
    done = subprocess.run([sys.executable, "-c", CHILD, ROOT, calls._path(), str(BEFORE),
                           MESSAGE], capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "2026-11-01T00:00:00Z"
    provider = Provider(_Resp(200, PING))
    got = _explain(provider.send)
    assert provider.sent == [] and got["error"] == "workspace_limit"
    assert got["detail"] == WORDS


def test_a_limit_met_here_is_read_by_another_process(world, clock):
    """The converse: met here, a child process reading the store finds the hold."""
    _explain(Provider(_limited()).send)
    reader = ("import sys; sys.path.insert(0, sys.argv[1]); "
              "from modules.ai import calls, provider_limit; calls._path = lambda: sys.argv[2]; "
              "h = provider_limit.holding(float(sys.argv[3])); print(h and h['until'])")
    done = subprocess.run([sys.executable, "-c", reader, ROOT, calls._path(), str(BEFORE)],
                          capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "2026-11-01T00:00:00Z"


def test_the_cards_test_still_asks_and_its_answer_clears_the_hold(world, clock):
    """An admin raised the limit in the provider's console and pressed Test: it asks the
    provider (a person's press of the re-check), is answered, and the hold is gone, so the
    next Explain is sent."""
    provider = Provider(_limited(), _Resp(200, PING), _Resp(200, PING))
    _explain(provider.send)
    clock.t = BEFORE + 3600
    assert _test_press(provider.send)["ok"] is True and len(provider.sent) == 2
    assert provider_limit.read()["hold"] is None
    _explain(provider.send)
    assert len(provider.sent) == 3, "the next call asked the provider"


def test_the_cards_test_refused_again_holds_again(world, clock):
    provider = Provider(_limited(), _limited())
    _explain(provider.send)
    clock.t = BEFORE + 60
    got = _test_press(provider.send)
    assert got["error"] == "workspace_limit" and len(provider.sent) == 2
    assert provider_limit.read()["hold"]["since"] == "2026-10-28T12:01:00Z"


def test_a_background_call_of_the_re_checks_task_does_not_ask(world, clock, monkeypatch):
    """Only a person's press of Test is the re-check: a background job naming the same task
    is refused like every other call, nothing sent."""
    from modules.ai import background
    # A background feature whose task is the re-check's (tests/test_settings_ai_v2.py's fake
    # loop), admitted as if on.
    monkeypatch.setitem(background.FEATURES, "fake_loop", {
        "task": "connection_check", "words": "The fake loop", "findings": ("detection",),
        "trigger_words": "a detection rule fires", "calls_per_finding": 1,
        "frequency": lambda network: {"per_day": 4.0, "basis": "planted"}})
    monkeypatch.setattr(background, "admit", lambda trigger: "")
    _explain(Provider(_limited()).send)
    provider = Provider(_Resp(200, PING))
    t = triggers.background("fake_loop", "j1", "Lab", "detection", "scan-1")
    got = gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                      actor=triggers.actor_of(t), trigger=t, send=provider.send,
                      today="2026-10-28")
    assert got["error"] == "workspace_limit" and provider.sent == []


def test_after_the_moment_a_call_asks_again_and_its_answer_clears_the_hold(world, clock):
    provider = Provider(_limited(), _Resp(200, PING))
    _explain(provider.send)
    clock.t = MOMENT - 1
    assert _explain(provider.send)["error"] == "workspace_limit" and len(provider.sent) == 1
    clock.t = MOMENT
    got = _explain(provider.send)
    assert len(provider.sent) == 2, "the call after the moment asked the provider"
    assert got["error"] != "workspace_limit" and provider_limit.read()["hold"] is None


def test_after_the_moment_a_refusal_holds_again(world, clock):
    provider = Provider(_limited(), _limited("You have reached your specified workspace API "
                                             "usage limits. You will regain access on "
                                             "2026-12-01 at 00:00 UTC."))
    _explain(provider.send)
    clock.t = MOMENT + 5
    got = _explain(provider.send)
    assert len(provider.sent) == 2 and got["error"] == "workspace_limit"
    assert "until 1 December 2026 00:00 UTC" in got["detail"]


def test_an_answer_to_a_call_sent_before_the_hold_clears_nothing(world, clock):
    """A call sent before another call's refusal was recorded, answered after: the hold
    stands (its answer says nothing about the limit now)."""
    hold = provider_limit.record(A.WorkspaceLimit("x", until="2026-11-01T00:00:00Z"))
    assert provider_limit.clear(BEFORE - 1, call_id="ai-older") is False
    assert provider_limit.read()["hold"] == hold
    assert provider_limit.clear(BEFORE, call_id="ai-same-second") is True
    assert provider_limit.read()["hold"] is None


def test_no_moment_named_holds_for_the_re_check_bound(world, clock):
    provider = Provider(_limited("You have reached your specified workspace API usage limits."),
                        _Resp(200, PING))
    first = _explain(provider.send)
    assert provider_limit.RECHECK_S == 600
    assert first["detail"] == (
        "AI is unavailable: the provider's workspace usage limit is reached, and it named no "
        "time access returns (Mercury asks it again from 28 October 2026 12:10 UTC); an admin "
        "raises it in the provider's console")
    clock.t = BEFORE + provider_limit.RECHECK_S - 1
    assert _explain(provider.send)["error"] == "workspace_limit" and len(provider.sent) == 1
    clock.t = BEFORE + provider_limit.RECHECK_S
    _explain(provider.send)
    assert len(provider.sent) == 2 and provider_limit.read()["hold"] is None


def test_a_moment_already_past_holds_for_the_re_check_bound(world, clock):
    clock.t = MOMENT + 60
    hold = provider_limit.record(A.WorkspaceLimit("x", until="2026-11-01T00:00:00Z"))
    assert hold["until"] is None
    assert hold["recheck_at"] == "2026-11-01T00:11:00Z"


def test_an_unreadable_store_is_no_hold_and_the_next_refusal_replaces_it(world, clock):
    with open(provider_limit._path(), "w", encoding="utf-8") as fh:
        fh.write("{torn")
    assert provider_limit.read()["state"] == "unreadable"
    provider = Provider(_limited())
    _explain(provider.send)
    assert len(provider.sent) == 1, "an unreadable store is read as no hold"
    assert provider_limit.read()["hold"]["until"] == "2026-11-01T00:00:00Z"


def test_the_store_is_owner_only_and_holds_no_request_or_key(world, clock):
    _explain(Provider(_limited()).send)
    mode = stat.S_IMODE(os.stat(provider_limit._path()).st_mode)
    assert mode == 0o600, oct(mode)
    with open(provider_limit._path(), encoding="utf-8") as fh:
        stored = json.load(fh)
    assert set(stored) == {"since", "until", "recheck_at", "said", "status", "call_id",
                           "feature"}
    assert KEY not in json.dumps(stored)


def test_a_selector_counts_nothing_while_the_limit_holds(world, clock):
    _explain(Provider(_limited()).send)
    with pressed_by(ACTOR):
        c = gateway.counter("explain", actor=ACTOR, trigger=triggers.person(ACTOR))
    assert c.allowed is False and c.why_not == f"not counted: {WORDS}"


# ── The screens ────────────────────────────────────────────────────────────────────────────

def _words_page(site):
    r = site.post("/v2/history/query/ask/metrics/words",
                  data={"list": "Lab", "words": "input errors per interface"},
                  headers={"HX-Request": "true"})
    return r, unescape(r.get_data(as_text=True))


@pytest.fixture
def nl_site(site, clock, monkeypatch):
    """Ask in words' page (tests/test_ai_nl_query.py's world), the provider refusing for its
    workspace's limit through the real adapter."""
    provider = Provider(_limited())
    monkeypatch.setattr(A, "send", provider.send)
    site.provider = provider
    return site


def _text(html):
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    return re.sub(r" ([,.;:)])", r"\1", text)


def test_after_a_press_ask_in_words_says_so_and_the_next_press_sends_nothing(nl_site):
    r, html = _words_page(nl_site)
    assert r.status_code == 200
    assert f"Not filled: {WORDS}." in html
    # The row is drawn again with the press's answer: its control disabled, its reason the
    # same words with the moment in the viewer's time and UTC's beside it.
    reason = re.search(r'<p class="ai-off" role="note" data-ai-off-reason="ask_in_words">(.*?)'
                       r"</p>", html, re.S)
    assert reason and _text(reason.group(1)).strip() == (
        "AI is unavailable: the provider's workspace usage limit is reached, until 1 November "
        "2026 00:00 UTC (1 November 2026 00:00 UTC); an admin raises it in the provider's "
        "console. Open Settings › Installation, AI (hosted)"), reason
    assert 'datetime="2026-11-01T00:00:00Z" data-clock="date"' in reason.group(1)
    _r, again = _words_page(nl_site)
    assert len(nl_site.provider.sent) == 1, "the second press reached the provider"
    assert f"Not filled: {WORDS}." in again


def test_in_a_browser_the_moment_is_the_viewers_own_time_with_utc_beside_it(site, clock,
                                                                         monkeypatch):
    """Firefox started with TZ=America/Denver: the reason's moment reads the viewer's own date
    and time of the provider's instant (Oct 31 18:00 MDT), UTC's beside it."""
    from tests import ai_controls_check as AIC
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as APP

    AIC.set_state(monkeypatch, "workspace_limit")
    monkeypatch.setenv("TZ", "America/Denver")
    with browser.Served(APP.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/history/query/ask/metrics?list=Lab&m=ifHCInOctets"))
            b.wait_for("var t = document.querySelector('[data-ai-off-reason] time');"
                       " return t && /M[DS]T/.test(t.textContent)", 15)
            words = b.js("return document.querySelector('[data-ai-off-reason]').textContent")
        finally:
            b.go("about:blank")
    assert ("AI is unavailable: the provider's workspace usage limit is reached, until Oct 31 "
            "18:00 MDT (1 November 2026 00:00 UTC); an admin raises it in the provider's "
            "console.") in " ".join(words.split()), words


# ── The chip and the panel ─────────────────────────────────────────────────────────────────

def _hold(message=MESSAGE):
    """The provider's refusal, recorded as the gateway records it."""
    until = A.regain_moment(message)
    return provider_limit.record(A.WorkspaceLimit("HTTP 400", until=until, status=400,
                                                  said=f"invalid_request_error: {message}"),
                                 call_id="ai-met", feature="explain")


def test_the_chip_says_ai_is_unavailable_until_when_in_red(spend, clock):
    _hold()
    _r, html = _get(spend, CHIP)
    c = _chip(html)
    assert (c["state"], c["level"]) == ("unavailable", "red")
    assert c["label"] == "AI unavailable until 1 Nov 00:00 UTC"
    assert c["text"] == "unavailable until 1 Nov 00:00 UTC" and c["short"] == "unavailable"
    assert c["title"] == (
        f"{WORDS}. The provider refused a call: “invalid_request_error: {MESSAGE}”. Until "
        "then Mercury refuses every AI call itself, without asking the provider; the AI "
        "(hosted) card's Test still asks, and any answer clears it.")


def test_the_chip_with_no_moment_named_says_so(spend, clock):
    _hold("You have reached your specified workspace API usage limits.")
    c = _chip(_get(spend, CHIP)[1])
    assert c["label"] == "AI unavailable: the provider's usage limit" and c["level"] == "red"
    assert "Mercury asks it again from 28 October 2026 12:10 UTC" in c["title"]


def test_the_chip_returns_to_the_spend_after_the_moment(spend, clock):
    _hold()
    clock.t = MOMENT
    c = _chip(_get(spend, CHIP)[1])
    assert c["state"] == "on" and c["text"].endswith("today · 0 background on")


def test_ai_off_is_still_ai_off(spend, clock):
    from modules.settings_schema import write_settings
    _hold()
    assert write_settings({"ai_hosted": {}})["ok"]
    c = _chip(_get(spend, CHIP)[1])
    assert (c["state"], c["text"]) == ("off", "AI off")


def test_the_panel_says_it_above_what_was_spent(spend, clock):
    _hold()
    _r, html = _get(spend, PANEL)
    assert f"{WORDS}. Nothing is sent to a model; what was spent before is below." in html


# ── Needs attention ────────────────────────────────────────────────────────────────────────

def _limit_rows():
    from modules import attention
    got = attention.ai_spend_source()
    return got, [r for r in got["rows"] if r["kind"] == "workspace_limit"]


def test_one_row_names_the_providers_words_the_moment_and_the_action(spend, clock):
    from modules import attention
    _hold()
    _got, rows = _limit_rows()
    assert len(rows) == 1
    (row,) = rows
    assert row["id"] == "ai_spend:workspace_limit" and row["level"] == "danger"
    assert row["what"] == WORDS
    assert row["cause"] == (
        "The provider refused call ai-met at 2026-10-28T12:00:00Z (HTTP 400): "
        f"“invalid_request_error: {MESSAGE}”. Mercury refuses every AI call until 1 November "
        "2026 00:00 UTC, without asking the provider: people's presses and background "
        "features alike; the AI (hosted) card's Test still asks, and an answer clears it")
    assert row["action"]["label"] == (
        "An admin raises the workspace's usage limit in the provider's console, then presses "
        "Test on Settings › Installation › Connections, the AI (hosted) card, which asks the "
        "provider again; or wait until 1 November 2026 00:00 UTC")
    assert row["action"]["href"] == "/v2/settings/installation?tab=connections#card-ai"
    assert row["clears"] == {"ways": ["resolves", "time"],
                             "when": attention.CLEARS[("ai_spend", "workspace_limit")][1]}
    assert row["clears_at"] == "2026-11-01T00:00:00Z"
    assert row["operands"]["provider"] == f"invalid_request_error: {MESSAGE}"


def test_the_row_clears_at_the_moment(spend, clock):
    _hold()
    clock.t = MOMENT
    got, rows = _limit_rows()
    assert rows == [] and "no provider workspace usage limit is held" in got["checked"]


def test_the_row_clears_when_a_call_is_answered(spend, clock):
    _hold()
    clock.t = BEFORE + 60
    assert provider_limit.clear(clock.t, call_id="ai-test") is True
    assert _limit_rows()[1] == []


def test_with_no_moment_the_row_clears_at_the_re_check_and_its_words_name_the_bound(spend,
                                                                                    clock):
    from modules import attention
    _hold("You have reached your specified workspace API usage limits.")
    (row,) = _limit_rows()[1]
    assert row["clears_at"] == "2026-10-28T12:10:00Z"
    assert "until 28 October 2026 12:10 UTC, when Mercury asks the provider again" in row["cause"]
    minutes = provider_limit.RECHECK_S // 60
    assert f"{minutes} minutes after its refusal" in \
        attention.CLEARS[("ai_spend", "workspace_limit")][1]


def test_no_row_while_ai_is_off(spend, clock):
    from modules.settings_schema import write_settings
    _hold()
    assert write_settings({"ai_hosted": {}})["ok"]
    got, rows = _limit_rows()
    assert rows == [] and "the provider's workspace usage limit was not read" in got["checked"]
