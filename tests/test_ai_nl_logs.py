"""Ask in words, logs (PHASE8_PLAN feature 1's LogQL half, 8.1; modules/ai/nl_query.py `logs`),
no network: the lab's Loki as the logs builder's tests capture it (tests/test_history_ask_logs.py's
stand-in over tests/fixtures/loki/ask_*.json), the gateway allowed with a fake `send`.

- Offered: the kinds Loki holds, the other labels, and the mnemonics sharing a word with the
  question (the Start-from chips' and those the logs reader counted), none for a question that
  names none; the builder's vocabulary is the cached prefix, the question rides uncached, and
  the request holds exactly its seven data blocks.
- Read back by the logs builder: the answer becomes its address and its own view reads it; a
  kind or mnemonic not offered, a device or role the network lacks, is left out and said; one
  count over the range tests it. A question back and a refusal fill nothing.
- Egress: a stored secret's value in the question is not in the bytes sent.
- The screen: the logs builder draws Ask in words; Fill the builder fills and pushes its
  address, running nothing.
"""
import json
import re
from html import unescape

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, gateway, nl_query
from tests.test_history_ask_logs import NOW, web  # noqa: F401 (the fixture)

KEY = "sk-planted-test-key-0123456789"


@pytest.fixture
def world(web, monkeypatch, tmp_path):
    settings = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                              "reason": "the lab's proof of concept"},
                "ai_cap_usd_per_day": 1.50}
    from modules import settings_schema
    monkeypatch.setattr(settings_schema, "get_setting", lambda k, d=None: settings.get(k, d))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    # The AI controls ask whether a key is stored, presence only (modules/ai/controls.py).
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    monkeypatch.setattr(nl_query, "_inventory", lambda name: [
        {"hostname": "r1", "role": "router"}, {"hostname": "s1", "role": "switch"},
        {"hostname": "s2", "role": "switch"}])

    class W:
        pass
    w = W()
    w.web, w.loki, w.sent, w.answer = web, web.loki, [], None

    def send(body, key):
        w.sent.append({"bytes": json.dumps(body), "body": body})
        return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(
            w.answer)}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 700, "output_tokens": 90}}, attempts=1, latency_s=0.3)
    w.send = send
    monkeypatch.setattr(A, "send", send)
    return w


def _choices(**over):
    c = {"outcome": "answer", "question": "", "why_not": "", "kinds": [], "devices": [],
         "role": "", "severity": "any", "mnemonics": ["%OSPF-5-ADJCHG"], "contains": "",
         "excludes": "", "show": "counts", "by": "device", "every": "5m", "range": "24h",
         "from_utc": "", "to_utc": ""}
    c.update(over)
    return c


def _ask(world, question="OSPF adjacency changes per device", **kw):
    return nl_query.logs("Lab", question, actor="operator@example.com", send=world.send,
                         client=world.loki, now=NOW, today="2026-10-25", **kw)


def test_the_offer_is_the_question_s_mnemonics_and_none_for_a_severity_question():
    assert nl_query.offer_mnemonics("OSPF adjacency changes", []) == ["%OSPF-5-ADJCHG"]
    assert nl_query.offer_mnemonics("interfaces going down", []) == ["%LINK-3-UPDOWN"]
    assert nl_query.offer_mnemonics("who changed the configuration", []) == ["%SYS-5-CONFIG_I"]
    assert nl_query.offer_mnemonics("errors and worse last 24 hours", []) == []
    seen = [("%LINEPROTO-5-UPDOWN", 40), ("%OSPF-5-ADJCHG", 3), ("%SYS-5-CONFIG_I", 9)]
    assert nl_query.offer_mnemonics("line protocol flapping", seen) == [
        "%LINEPROTO-5-UPDOWN", "%LINK-3-UPDOWN"], "the most seen first, the chips' after"


def test_the_request_holds_its_prompt_vocabulary_and_twelve_data_blocks(world):
    from modules.ai import prompts
    world.answer = _choices()
    _ask(world)
    _ask(world, "OSPF neighbours changing on s1")
    a, b = (s["body"] for s in world.sent)
    assert a["system"] == b["system"] and a["system"][-1]["cache_control"]
    assert a["system"][0]["text"] == prompts.load(*nl_query.PROMPT_LOGS)["text"]
    assert "Severity (severity)" in a["system"][1]["text"]
    data = re.findall(r'<data name="([^"]+)">', a["messages"][0]["content"])
    # The named spans' starts and their zone (C1740, nl_logs v2), as the metrics half's.
    assert set(data) == {"question", "now_utc", "today_start_utc", "yesterday_start_utc",
                         "week_start_utc", "last_week_start_utc", "today_zone", "kinds",
                         "mnemonics", "labels", "devices_named", "roles"} and len(data) == 12
    assert "network_syslog" in a["messages"][0]["content"]
    assert "%OSPF-5-ADJCHG" in a["messages"][0]["content"]


def test_the_answer_fills_the_logs_builder_and_its_test_run_counts(world):
    world.answer = _choices()
    got = _ask(world)
    assert got["ok"] is True, got
    v = got["values"]
    assert v["mn"] == ["%OSPF-5-ADJCHG"] and v["show"] == "counts" and v["by"] == "device"
    assert "OSPF-5-ADJCHG" in got["view"]["built"]["log_query"]
    assert "mn=%25OSPF-5-ADJCHG" in got["view"]["qs"]() or "OSPF-5-ADJCHG" in got["view"]["qs"]()
    assert got["lines"] == 1240 and got["test"] == "the test run matches 1240 line(s) over the range"


def test_what_was_not_offered_is_left_out_and_said(world):
    world.answer = _choices(kinds=["network_syslog", "made_up"],
                            mnemonics=["%OSPF-5-ADJCHG", "%BGP-5-ADJCHANGE"],
                            devices=["r1", "r99"], role="edge")
    got = _ask(world, "OSPF and BGP adjacency changes on r1 and r99 at the edge")
    assert got["ok"] is True
    assert got["values"]["job"] == ["network_syslog"]
    assert got["values"]["mn"] == ["%OSPF-5-ADJCHG"] and got["values"]["dev"] == ["r1"]
    joined = " | ".join(got["errors"])
    for word in ("made_up", "%BGP-5-ADJCHANGE", "r99", "'edge'"):
        assert word in joined, word


def test_a_question_back_and_a_refusal_fill_nothing(world):
    world.answer = _choices(outcome="ask", question="Which device?", mnemonics=[])
    got = _ask(world, "show me the logs")
    assert got["error"] == "ask" and got["clarify"] == "Which device?" and "values" not in got
    world.answer = _choices(outcome="refuse", why_not="logs do not hold CPU", mnemonics=[])
    got = _ask(world, "the CPU from the logs")
    assert got["error"] == "unanswerable" and "logs do not hold CPU" in got["detail"]


def test_a_stored_secret_in_the_question_is_masked_in_the_bytes_sent(world, monkeypatch):
    from modules import redact
    stored = "PlantedStoredPw9x"
    monkeypatch.setattr(redact, "known_secret_values", lambda: {stored: "Lab:enable"})
    world.answer = _choices()
    got = _ask(world, f"OSPF adjacency changes after {stored} was set")
    assert got["ok"] is True
    assert stored not in world.sent[0]["bytes"] and "OSPF adjacency changes" in world.sent[0]["bytes"]


def test_the_logs_builder_draws_ask_in_words_and_a_fill_pushes_its_address(world):
    html = unescape(world.web.get("/v2/history/query/ask/logs?list=Lab").get_data(as_text=True))
    assert 'name="words"' in html and 'data-op="ask-in-words"' in html
    assert "/v2/history/query/ask/logs/words" in html
    world.answer = _choices()
    r = world.web.post("/v2/history/query/ask/logs/words",
                       data={"list": "Lab", "words": "OSPF adjacency changes per device"},
                       headers={"HX-Request": "true"})
    page = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and "Filled from your words" in page
    assert "/v2/history/query/ask/logs?" in r.headers["HX-Push-Url"]
    assert not any(p.get("direction") == "backward" for _path, p in world.loki.asked), \
        "it read lines as an answer"


def _words_post(world, question, **form):
    r = world.web.post("/v2/history/query/ask/logs/words",
                       data=dict({"list": "Lab", "words": question}, **form),
                       headers={"HX-Request": "true"})
    return unescape(r.get_data(as_text=True))


def _ask_button(html):
    return re.search(r'<button id="lq-ask"[^>]*>', html).group(0)


def test_not_filled_the_builder_is_marked_left_and_ask_is_off_until_kept(world):
    """The operator's walk of 2026-10-26: after "Not filled" the builder still held the
    previous question's query with Ask on, so Ask answered the wrong question. It is marked,
    Ask is off, and one click keeps the choices (Ask on); filled, nothing is marked."""
    world.answer = _choices(outcome="refuse", why_not="logs do not hold CPU", mnemonics=[])
    html = _words_post(world, "the CPU from the logs", mn="%LINK-3-UPDOWN", show="counts")
    assert "Not filled:" in html and "Left from your previous question" in html
    assert "left from your previous question</span>" in html, "the query box is not marked"
    assert " disabled" in _ask_button(html) and 'aria-describedby="lq-left"' in _ask_button(html)
    keep = re.search(r'<a class="btn btn-small" href="[^"]+" hx-get="([^"]+)"[^>]*>Keep these '
                     r'choices</a>', html).group(1)
    assert "mn=%25LINK-3-UPDOWN" in keep and "show=counts" in keep and "words" not in keep
    again = unescape(world.web.get(keep, headers={"HX-Request": "true"}).get_data(as_text=True))
    assert "Left from your previous question" not in again
    assert " disabled" not in _ask_button(again)
    # Nothing chosen before the words: the builder's defaults, said so, Ask off the same.
    html = _words_post(world, "the CPU from the logs")
    assert "Not filled from these words" in html and " disabled" in _ask_button(html)
    # A question back is not filled either.
    world.answer = _choices(outcome="ask", question="Which device?", mnemonics=[])
    html = _words_post(world, "show me the logs", mn="%LINK-3-UPDOWN")
    assert "One question first" in html and " disabled" in _ask_button(html)
    # Filled: nothing left from before, Ask on.
    world.answer = _choices()
    html = _words_post(world, "OSPF adjacency changes per device", mn="%LINK-3-UPDOWN")
    assert "Filled from your words" in html and "Left from your previous" not in html
    assert " disabled" not in _ask_button(html)


def test_ask_in_words_on_the_logs_builder_is_an_ai_control_and_the_builder_stays_usable(
        world, monkeypatch):
    """PHASE8_PLAN 15.13 on the logs builder's page, through its real route: the AI mark, and
    the row disabled with its reason while hosted AI cannot answer; the builder's Ask and
    choices stay usable."""
    import re

    from tests import ai_controls_check as AIC

    def get():
        return world.web.get("/v2/history/query/ask/logs?list=Lab").get_data(as_text=True)

    def parity(html):
        ask = re.findall(r'<button id="lq-ask"[^>]*>', html)
        assert len(ask) == 1 and " disabled" not in ask[0], ask
        assert 'id="lq-form"' in html and 'class="lq-chip' in html, "the builder is drawn"
    AIC.check_screen(monkeypatch, get, "ask_in_words", parity)


def test_ask_in_words_on_the_logs_builder_in_a_browser(world):
    """In a real browser: typed and pressed, the logs builder fills in place and pushes its
    address; nothing scrolls sideways at 1440 or at a phone's 390."""
    from tests import browser
    from tests.test_ai_nl_query import OVERFLOW
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as APP

    world.answer = _choices()
    with browser.Served(APP.app) as srv, browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
        b.go(srv.url("/v2/history/query/ask/logs?list=Lab"))
        b.wait_for("return document.getElementById('lq-words')", 15)
        b.js("document.getElementById('lq-words').value = 'OSPF adjacency changes per device';"
             "return 1")
        b.js("document.querySelector('[data-op=ask-in-words]').click(); return 1")
        b.wait_for("return location.search.indexOf('OSPF') >= 0", 15)
        note = b.js("return document.querySelector('.lq-build .notice').textContent")
        try:
            b.wait_for("return document.documentElement.scrollWidth <= window.innerWidth", 5)
            wide = True
        except Exception:                               # noqa: BLE001 (said below)
            wide = b.js(OVERFLOW)
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 390, "height": 900})
        b.go(srv.url("/v2/history/query/ask/logs?list=Lab"))
        b.wait_for("return document.getElementById('lq-words')", 15)
        narrow = b.js("return document.documentElement.scrollWidth <= window.innerWidth + 1")
        b.go("about:blank")
    assert "Filled from your words" in note, note
    assert wide is True and narrow, (wide, narrow)


# ------------------------------------------- C1740's logs half: the named spans in the zone

#: NOW is Thursday 2026-10-15 08:25 UTC, 04:25 in New York (EDT, UTC-4): worked by hand, the
#: midnights there are these UTC times (an expectation by a path independent of `spans`).
NEW_YORK = {"today_start_utc": "2026-10-15 04:00", "yesterday_start_utc": "2026-10-14 04:00",
            "week_start_utc": "2026-10-12 04:00", "last_week_start_utc": "2026-10-05 04:00"}


def test_the_named_spans_ride_as_data_in_the_viewer_s_zone(world):
    world.answer = _choices()
    _ask(world, viewer_zone=nl_query.zone("America/New_York"))
    user = world.sent[-1]["body"]["messages"][0]["content"]
    for name, value in dict(NEW_YORK, today_zone="America/New_York").items():
        assert f'<data name="{name}">\n{value}\n</data>' in user, name


def test_with_no_zone_the_spans_are_utc_s():
    """No zone given (the screen sends one; a measurement may not): UTC's midnights."""
    sent = nl_query.parts_logs("q", [], [], [], [], [], NOW)
    assert (sent["today_start_utc"], sent["yesterday_start_utc"], sent["today_zone"]) == (
        "2026-10-15 00:00", "2026-10-14 00:00", "UTC")


@pytest.mark.parametrize("frm,to,said", [
    ("2026-10-15 04:00", "2026-10-15 08:25",
     "'Today' runs from midnight America/New_York (your browser's timezone; no installation "
     "timezone is set)"),
    ("2026-10-14 04:00", "2026-10-15 04:00",
     "'Yesterday' is counted from midnight America/New_York (your browser's timezone; no "
     "installation timezone is set)"),
    ("2026-10-12 04:00", "2026-10-15 08:25",
     "'This week' is counted from midnight on Monday America/New_York (your browser's "
     "timezone; no installation timezone is set)"),
    ("2026-10-05 04:00", "2026-10-12 04:00",
     "'Last week' is counted from midnight on Monday America/New_York (your browser's "
     "timezone; no installation timezone is set)"),
], ids=["today", "yesterday", "this-week", "last-week"])
def test_a_range_from_a_named_span_says_whose_midnight(world, frm, to, said):
    world.answer = _choices(range="custom", from_utc=frm, to_utc=to)
    got = _ask(world, viewer_zone=nl_query.zone("America/New_York"))
    assert got["ok"] is True and got["today"] == said, got


def test_a_range_from_no_named_span_says_nothing_of_midnight(world):
    world.answer = _choices(range="custom", from_utc="2026-10-14 06:00",
                            to_utc="2026-10-14 09:00")
    got = _ask(world, viewer_zone=nl_query.zone("America/New_York"))
    assert got["ok"] is True and got["today"] == ""
    world.answer = _choices()
    assert _ask(world, viewer_zone=nl_query.zone("America/New_York"))["today"] == ""


def test_the_words_form_sends_the_zone_and_the_notice_says_whose_midnight(world):
    """The route: the logs form draws the timezone inputs and posts them, and the filled
    notice names the zone (the metrics half's own test is tests/test_ai_nl_query.py's)."""
    html = unescape(world.web.get("/v2/history/query/ask/logs?list=Lab").get_data(
        as_text=True))
    form = re.search(r'<form class="lq-row lq-words".*?</form>', html, re.S).group(0)
    assert '<input type="hidden" name="tz" value="" data-lq-tz="name">' in form
    assert '<input type="hidden" name="tz_off" value="" data-lq-tz="offset">' in form
    world.answer = _choices(range="custom", from_utc=NEW_YORK["yesterday_start_utc"],
                            to_utc=NEW_YORK["today_start_utc"])
    r = world.web.post("/v2/history/query/ask/logs/words", data={
        "list": "Lab", "words": "OSPF adjacency changes yesterday", "tz": "America/New_York",
        "tz_off": "-240"}, headers={"HX-Request": "true"})
    note = unescape(r.get_data(as_text=True)).split("Filled from your words", 1)[1]
    assert "'Yesterday' is counted from midnight America/New_York" in note.split("</p>")[0]
    user = world.sent[-1]["body"]["messages"][0]["content"]
    assert '<data name="today_zone">\nAmerica/New_York\n</data>' in user


def test_v2_is_the_prompt_and_says_the_named_spans():
    from modules.ai import prompts
    assert nl_query.PROMPT_LOGS == ("nl_logs", 2)
    # Refuses a prompt naming JSON; the words compared as read, the text's wrapping aside.
    text = " ".join(prompts.load("nl_logs", 2)["text"].split())
    for said in ('"yesterday_start_utc"', '"week_start_utc"', '"last_week_start_utc"',
                 '"today_zone"', '"yesterday" from yesterday_start_utc to today_start_utc',
                 '"the past week" is a span of time, not a calendar week: 7d'):
        assert said in text, said
    assert prompts.load("nl_logs", 1)["version"] == 1, "the earlier version stays"


def test_the_logs_schema_is_registered_and_committed():
    from modules.ai import schemas
    assert schemas.REGISTRY[("nl_logs", 1)] is nl_query.LogsChoices
    with open(schemas.committed_path("nl_logs", 1), encoding="utf-8") as fh:
        assert fh.read() == schemas.committed_text(nl_query.LogsChoices)


def test_an_answer_stopped_at_max_tokens_fills_nothing(world):
    """A complete, valid answer whose stop is max_tokens fills nothing (the operator,
    2026-10-25; tests/test_ai_truncated_answers.py has the metrics half and the route)."""
    from tests.test_ai_truncated_answers import _cut
    got = nl_query.logs("Lab", "OSPF adjacency changes per device",
                        actor="operator@example.com", send=_cut(world, json.dumps(_choices())),
                        client=world.loki, now=NOW, today="2026-10-25")
    assert got["ok"] is False and got["error"] == "max_tokens"
    assert "values" not in got and "view" not in got and "choices" not in got
    (row,) = calls.read()["rows"]
    assert row["verdict"] == "max_tokens" and "output" not in row


# ---------------------------------------------------- the operator's walk, 2026-10-26 (C1804)

IOS_ROWS = [{"hostname": "r1", "role": "router", "platform": "cisco_iosxe"},
            {"hostname": "s1", "role": "switch", "platform": "cisco_ios"},
            {"hostname": "s2", "role": "switch", "platform": "cisco_ios"}]


def test_v3_offers_the_platform_s_events_whether_or_not_the_range_holds_one(world, monkeypatch):
    """C1804 (6a): the reload and restart mnemonics are offered for "rebooted", with what each
    records, though no word of the question is in them and the range need not hold one."""
    monkeypatch.setattr(nl_query, "_inventory", lambda name: IOS_ROWS)
    monkeypatch.setattr(nl_query, "network_context", lambda name, store: {
        "summary": "s", "coverage": "c"})
    world.answer = dict(_choices(mnemonics=["%SYS-5-RELOAD", "%SYS-5-RESTART"], range="7d"),
                        needs=[])
    got = _ask(world, "Which devices rebooted this week?", prompt=nl_query.CANDIDATE_LOGS)
    assert got["ok"] is True, got
    assert got["values"]["mn"] == ["%SYS-5-RELOAD", "%SYS-5-RESTART"]
    user = world.sent[-1]["body"]["messages"][0]["content"]
    assert ("%SYS-5-RELOAD | a reload was requested (the device is about to restart)" in user)
    assert "%SYS-5-RESTART | the system restarted" in user
    assert '<data name="coverage">' in user and '<data name="looked_up">' in user


def test_the_platform_s_events_are_the_dialects_the_network_speaks():
    assert nl_query.events_for("Lab", rows=[]) == []
    names = [e["mnemonic"] for e in nl_query.events_for("Lab", rows=IOS_ROWS)]
    assert names[:2] == ["%SYS-5-RELOAD", "%SYS-5-RESTART"] and len(names) == len(set(names))
    for want in ("%LINK-3-UPDOWN", "%OSPF-5-ADJCHG", "%BGP-5-ADJCHANGE", "%SYS-5-CONFIG_I"):
        assert want in names, want
    assert nl_query.events_for("Lab", rows=[{"hostname": "x", "platform": "unknown_os"}]) == []


def test_a_zero_resting_on_free_text_says_so(world, monkeypatch):
    """C1804 (6b): the fill's test run says the text may not be how the platform logs it."""
    from modules import history_logq as lq
    monkeypatch.setattr(lq, "_count", lambda client, q, rng: 0)
    world.answer = _choices(mnemonics=[], contains="reboot", show="lines", range="7d")
    got = _ask(world, "Which devices rebooted this week?")
    assert got["ok"] is True and got["lines"] == 0
    assert got["test"] == ("the test run matches 0 line(s) over the range; no line contains "
                           "'reboot', which may not be how the platform logs it"), got["test"]


def test_a_logs_refusal_ends_in_one_full_stop(world):
    world.answer = _choices(outcome="refuse", why_not="The logs do not hold CPU.", mnemonics=[])
    got = _ask(world, "the CPU from the logs")
    assert got["detail"] == "the builder cannot answer this: The logs do not hold CPU"


def test_the_logs_v3_schema_and_prompt_are_registered_and_committed():
    from modules.ai import prompts, schemas
    assert schemas.REGISTRY[("nl_logs", 2)] is nl_query.LogsChoicesV2
    with open(schemas.committed_path("nl_logs", 2), encoding="utf-8") as fh:
        assert fh.read() == schemas.committed_text(nl_query.LogsChoicesV2)
    text = " ".join(prompts.load(*nl_query.CANDIDATE_LOGS)["text"].split())
    for said in ("An event a device logs is found by its mnemonic, never by a word for it",
                 '"this week", "the past week" and "the last 7 days" are the last 7 days: 7d',
                 '"coverage"', '"looked_up"'):
        assert said in text, said
    assert nl_query.PROMPT_LOGS == ("nl_logs", 2), "the candidate is adopted only by its bar"
