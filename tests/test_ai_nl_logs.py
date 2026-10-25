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


def test_the_request_holds_its_prompt_vocabulary_and_seven_data_blocks(world):
    from modules.ai import prompts
    world.answer = _choices()
    _ask(world)
    _ask(world, "OSPF neighbours changing on s1")
    a, b = (s["body"] for s in world.sent)
    assert a["system"] == b["system"] and a["system"][-1]["cache_control"]
    assert a["system"][0]["text"] == prompts.load(*nl_query.PROMPT_LOGS)["text"]
    assert "Severity (severity)" in a["system"][1]["text"]
    data = re.findall(r'<data name="([^"]+)">', a["messages"][0]["content"])
    assert set(data) == {"question", "now_utc", "kinds", "mnemonics", "labels",
                         "devices_named", "roles"} and len(data) == 7
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


def test_the_logs_schema_is_registered_and_committed():
    from modules.ai import schemas
    assert schemas.REGISTRY[("nl_logs", 1)] is nl_query.LogsChoices
    with open(schemas.committed_path("nl_logs", 1), encoding="utf-8") as fh:
        assert fh.read() == schemas.committed_text(nl_query.LogsChoices)
