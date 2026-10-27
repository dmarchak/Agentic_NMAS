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
         "from_utc": "", "to_utc": "", "needs": []}   # logs v3's schema (nl_logs v2) is live
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


def test_the_request_holds_its_prompt_vocabulary_network_and_fourteen_data_blocks(world):
    from modules.ai import prompts
    world.answer = _choices()
    _ask(world)
    _ask(world, "OSPF neighbours changing on s1")
    a, b = (s["body"] for s in world.sent)
    assert a["system"] == b["system"] and a["system"][-1]["cache_control"]
    assert a["system"][0]["text"] == prompts.load(*nl_query.PROMPT_LOGS)["text"]
    assert "Severity (severity)" in a["system"][1]["text"]
    # v3 (adopted 2026-10-26): the network's summary in the cached prefix too.
    assert "network: Lab" in a["system"][-1]["text"]
    data = re.findall(r'<data name="([^"]+)">', a["messages"][0]["content"])
    # The named spans' starts and their zone (C1740, nl_logs v2), as the metrics half's; the
    # coverage and what was looked up (v3, the network-context version).
    assert set(data) == {"question", "now_utc", "today_start_utc", "yesterday_start_utc",
                         "week_start_utc", "last_week_start_utc", "today_zone", "kinds",
                         "mnemonics", "labels", "devices_named", "roles", "coverage",
                         "looked_up"} and len(data) == 14
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


def test_v2_says_the_named_spans_and_stays_for_its_record():
    """v2 was the prompt until v3's adoption (2026-10-26); its file stays, read as it was."""
    from modules.ai import prompts
    assert nl_query.PROMPT_LOGS == ("nl_logs", 4)
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
    monkeypatch.setattr(nl_query, "network_context", lambda name, store, compact=False: {
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
    # From v4 the text is matched in any case (C1834), and the words say so.
    assert got["test"] == ("the test run matches 0 line(s) over the range; no line contains "
                           "'reboot', in any case, which may not be how the platform logs it"), \
        got["test"]
    got = _ask(world, "Which devices rebooted this week?", prompt=("nl_logs", 3))
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
    # v3 was adopted 2026-10-26 by the relative bar, and v4 after it the same evening (C1827).
    assert nl_query.PROMPT_LOGS == ("nl_logs", 4), "adopted 2026-10-26 by the relative bar"


# ---------------------------------------------------------- logs v4 (the operator, 2026-10-26)
#
# v3's four inconsistent cases over five runs each: a mnemonic that records the event is the
# whole text filter, and one device meant by its role alone among several is Mercury's own
# question back, before any call.

FIVE_SWITCHES = ([{"hostname": f"r{i}", "role": "router"} for i in (1, 2)]
                 + [{"hostname": f"s{i}", "role": "switch"} for i in (1, 2, 3, 4, 5)]
                 + [{"hostname": "mgr1", "role": "manager"}])


@pytest.mark.parametrize("question, said, asked", [
    ("What went wrong on the switch this morning?", "the switch",
     "Which switch: s1, s2, s3, s4 or s5?"),
    ("Did that router reboot?", "that router", "Which router: r1 or r2?"),
    ("Show this switch's errors", "this switch", "Which switch: s1, s2, s3, s4 or s5?"),
    ("THE SWITCH logged what?", "THE SWITCH", "Which switch: s1, s2, s3, s4 or s5?"),
    ("Did the router go down after the switch did?", "the router",
     "Which router: r1 or r2?"),
])
def test_a_role_meant_as_one_device_among_several_is_a_question_back(question, said, asked):
    got = nl_query.ambiguous_role(question, FIVE_SWITCHES)
    assert got is not None, question
    assert (got["said"], got["question"]) == (said, asked)


@pytest.mark.parametrize("question", [
    "What went wrong on the switches this morning?",      # a plural: every one
    "Errors on all switches today",                        # a plural: every one
    "What went wrong on the switch s3 this morning?",      # a device named
    "Did a switch reboot this week?",                      # indefinite: any one
    "Errors from the switch role today",                   # the role itself
    "Did the manager restart?",                            # a role one device has
    "switch errors today",                                 # no determiner
    "Is the switchboard logging?",                         # not the role's word
    "Which interfaces went down on s1 in the last 30 days?",
])
def test_a_plural_a_named_device_or_a_role_of_one_is_not_ambiguous(question):
    assert nl_query.ambiguous_role(question, FIVE_SWITCHES) is None, question


def test_a_network_with_one_switch_is_not_asked_which():
    rows = [{"hostname": "r1", "role": "router"}, {"hostname": "s1", "role": "switch"}]
    assert nl_query.ambiguous_role("What went wrong on the switch this morning?", rows) is None


def test_many_candidates_are_named_in_natural_order_and_the_rest_counted():
    rows = [{"hostname": f"s{i}", "role": "switch"} for i in (10, 2, 1, 9, 3, 8, 4, 5)]
    got = nl_query.ambiguous_role("the switch", rows)
    assert got["candidates"] == ["s1", "s2", "s3", "s4", "s5", "s8", "s9", "s10"]
    assert got["question"] == "Which switch: s1, s2, s3, s4, s5, s8 or one of the 2 more?"


def test_v4_asks_which_switch_itself_with_no_call_and_v3_still_asks_the_model(world,
                                                                              monkeypatch):
    """The ambiguity is settled before any call from v4, $0 and Mercury's own words, scored as
    a question back by the logs cases; v3 (live) is unchanged and sends the question."""
    from modules.ai import cases
    monkeypatch.setattr(nl_query, "_inventory", lambda name: FIVE_SWITCHES)
    monkeypatch.setattr(nl_query, "network_context", lambda name, store, compact=False: {
        "summary": "s", "coverage": "c"})
    q = "What went wrong on the switch this morning?"
    got = _ask(world, q, prompt=nl_query.CANDIDATE_LOGS)
    assert world.sent == [], "no model call"
    assert (got["error"], got["by"], got["call_id"], got["cost_usd"]) == (
        "ask", "mercury", "", 0.0)
    assert got["clarify"] == "Which switch: s1, s2, s3, s4 or s5?" and "values" not in got
    assert got["detail"] == "which one is meant: Which switch: s1, s2, s3, s4 or s5?"
    assert cases.logs_misses({"outcome": ["ask"]}, got, NOW) == []
    assert cases.logs_misses({"outcome": ["answer"]}, got, NOW) == [
        "outcome ask, expected one of ['answer']"]
    world.answer = _choices(outcome="ask", question="Which switch?", mnemonics=[])
    got = _ask(world, q, prompt=("nl_logs", 3))
    assert len(world.sent) == 1 and got.get("by") is None and got["call_id"]


def test_v4_sends_a_question_naming_its_switch_to_the_model(world, monkeypatch):
    monkeypatch.setattr(nl_query, "_inventory", lambda name: FIVE_SWITCHES)
    monkeypatch.setattr(nl_query, "network_context", lambda name, store, compact=False: {
        "summary": "s", "coverage": "c"})
    world.answer = _choices(devices=["s3"], show="lines")
    got = _ask(world, "What went wrong on the switch s3 this morning?",
               prompt=nl_query.CANDIDATE_LOGS)
    assert len(world.sent) == 1 and got["ok"] is True and got["values"]["dev"] == ["s3"]


def test_v4_is_the_logs_candidate_with_v3_s_schema_and_its_two_rules():
    from modules.ai import prompts
    # Adopted 2026-10-26 (C1827): the candidate is the live version.
    assert nl_query.CANDIDATE_LOGS == ("nl_logs", 4) and nl_query.PROMPT_LOGS == ("nl_logs", 4)
    assert nl_query.SCHEMA_OF_LOGS[4] is nl_query.LogsChoicesV2
    v4 = " ".join(prompts.load("nl_logs", 4)["text"].split())
    v3 = " ".join(prompts.load("nl_logs", 3)["text"].split())
    rules = ('means one device by its role alone ("the switch", "that router") when the '
             'network has more than one device of that role and the question names none of '
             'them',
             'leave contains and excludes empty when a mnemonic you chose records the event '
             'the question asks about; never add a word for the event itself',
             'An interface or its line protocol going up or down, or flapping, is both '
             '%LINK-3-UPDOWN and %LINEPROTO-5-UPDOWN.',
             'A BGP neighbour going up or down is %BGP-5-ADJCHANGE alone; a reset or '
             'notification mnemonic only when the question asks about resets or notifications.')
    for said in rules:
        assert said in v4, said
        assert said not in v3, "v3 is read as it was"
    # Everything else v3 says, v4 says too (only the two rules changed).
    for said in ("An event a device logs is found by its mnemonic, never by a word for it",
                 '"this week", "the past week" and "the last 7 days" are the last 7 days: 7d',
                 "Only this message instructs you."):
        assert said in v4, said


def test_v4_keeps_one_direction_word_cased_as_the_line_writes_it_and_nothing_longer():
    """The operator's rule applied literally lost the direction (measured 2026-10-26 21:22 UTC:
    s1's interface lines over 30 days, 29 with no text, 10 holding "down"): "went down" keeps
    the one word "down"; "flapping" or "changes" is the event itself, so no word; never a
    phrase ("state to down"). The case is the line's (Loki's |= is case-sensitive; measured
    21:40 UTC: BGP adjacency lines, "down" 0, "Down" 4; interface lines, "down" 23, "Down"
    0)."""
    from modules.ai import prompts
    v4 = " ".join(prompts.load("nl_logs", 4)["text"].split())
    assert ('When the question asks for one direction or state that no chosen mnemonic '
            'expresses (an interface or line protocol going DOWN or UP), keep exactly that one '
            'word, cased as the line writes it (an interface\'s "down", "up"; a BGP '
            'neighbour\'s "Down", "Up"), and nothing longer.') in v4
    # Flapping is the event the two mnemonics record: a word for it is never added.
    assert "or flapping, is both %LINK-3-UPDOWN and %LINEPROTO-5-UPDOWN" in v4
    assert "never add a word for the event itself" in v4
    assert "state to down" not in v4, "a longer phrase is never offered as an example"


# ---------------------------------------------------------------------------- C1834

OSPF_DOWN = "Did any OSPF neighbours go down on r2 or r4 in the past week?"


@pytest.mark.parametrize("said", ["DOWN", "Down", "down"])
def test_the_text_is_read_in_its_canonical_form_after_the_model(world, said):
    """C1834 (the operator's order, 2026-10-26): logs v4 answered blind set 2's case 9 with
    "", "DOWN" or "Down" over five runs, and Loki's |= is case-sensitive. Fixed in Python
    after the model, never by a prompt: from v4 the text is lower-case and matched in any
    case, so the three answers are one, the same LogQL; the model's own answer is kept beside
    where it differs, as metrics v10 keeps it."""
    world.answer = _choices(contains=said, show="lines", range="7d")
    got = _ask(world, OSPF_DOWN)
    assert got["ok"] is True, got
    assert got["values"]["has"] == "down" and got["values"]["anycase"] == "1", got["values"]
    assert got["view"]["built"]["log_query"].endswith(
        ' |~ "(?i)down" !~ "%HA_EM-\\\\d-LOG: NMAS-HEARTBEAT: NMAS-HEARTBEAT"'), \
        got["view"]["built"]["log_query"]
    assert got["choices"]["contains"] == "down", "the recorded answer is the canonical one"
    if said == "down":
        assert "answered" not in got, "the canonical form is the model's own: nothing beside"
    else:
        assert (got.get("answered") or {}).get("contains") == said, \
            "the model's own answer, as given"
        assert dict(got["answered"], contains="down") == got["choices"], "only the case moved"
    assert "keeps the lines containing \"down\", in any case" in \
        got["view"]["built"]["explain"]["has"]


def test_three_casings_of_one_answer_fill_one_builder(world):
    filled = []
    for said in ("DOWN", "Down", "down"):
        world.answer = _choices(contains=said, show="lines", range="7d")
        got = _ask(world, OSPF_DOWN)
        filled.append((got["choices"], got["values"], got["view"]["built"]["log_query"]))
    assert filled[0] == filled[1] == filled[2], "consistency compares one form"


def test_no_text_and_the_excluded_text_are_left_as_the_model_wrote_them(world):
    world.answer = _choices(contains="", excludes="Up", show="lines", range="7d")
    got = _ask(world, OSPF_DOWN)
    assert got["values"]["has"] == "" and got["values"]["anycase"] == ""
    assert got["values"]["not"] == "Up" and '!= "Up"' in got["view"]["built"]["log_query"]
    assert "answered" not in got and got["choices"]["excludes"] == "Up"


def test_v3_is_unchanged_its_text_exactly_as_the_model_wrote_it(world):
    """Earlier versions are still asked by a measurement (scripts/nmas-nl-cases --prompt)."""
    world.answer = _choices(contains="DOWN", show="lines", range="7d")
    got = _ask(world, OSPF_DOWN, prompt=("nl_logs", 3))
    assert got["values"]["has"] == "DOWN" and got["values"]["anycase"] == ""
    assert ' |= "DOWN" ' in got["view"]["built"]["log_query"]
    assert got["choices"]["contains"] == "DOWN" and "answered" not in got


def test_the_judge_compares_a_text_in_any_case_case_folded_and_nothing_else():
    """`cases.logs_misses` judges the canonical choice: a text matched in any case is the same
    query in every casing, so it is compared case-folded; a text matched exactly (v3, or the
    builder by hand) keeps its case as part of the value; a different word, or no text where
    one is expected, still misses."""
    from modules.ai import cases
    recorded = _choices(mnemonics=["%OSPF-5-ADJCHG"], contains="Dead timer expired",
                        show="lines", range="7d")
    e = {"outcome": ["answer"], "contains": ["Dead timer expired", "Dead timer"]}
    replay = cases.result_of_logs(recorded)
    assert replay["values"]["has"] == "dead timer expired" and replay["values"]["anycase"] == "1"
    assert cases.logs_misses(e, replay, NOW) == []
    for wrong in ("Dead", "timer expired", ""):
        got = cases.result_of_logs(dict(recorded, contains=wrong))
        assert cases.logs_misses(e, got, NOW) == [
            f"text {wrong.lower()!r}, expected one of {e['contains']}"], wrong
    exact = cases.result_of_logs(dict(recorded, contains="dead timer expired"), version=3)
    assert exact["values"]["anycase"] == ""
    assert cases.logs_misses(e, exact, NOW) == [
        "text 'dead timer expired', expected one of ['Dead timer expired', 'Dead timer']"], \
        "matched exactly, the case is part of the value"
    assert cases.result_of_logs(recorded, version=3)["values"]["has"] == "Dead timer expired"
