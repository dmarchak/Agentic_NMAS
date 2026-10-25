"""Phase 8's 8.0b (2026-10-25; PHASE8_PLAN 13.1, 15.8, 15.12): Settings › Installation's
AI (hosted) card, through the real routes as a verified person, the adapter replaced so no
test reaches a network.

- The card draws on the Connections tab, hosted AI off by default, the key not set, the caps,
  today's spend.
- Replace… stores the key as a secret, records the field's name and never its value, never
  draws it back; its Test is refused while hosted AI is off, and nothing is sent.
- Allow needs a reason of 10 to 300 characters (a short one writes nothing); it writes who,
  when and the reason and records them; Turn off empties it and records it; off again writes
  nothing.
- Test, allowed and keyed, is one call through the gateway as the person who pressed it, its
  word echoed, recorded, and announces `ai_calls`.
- The caps save as numbers; a word, or one over the schema's maximum, is refused.
"""
import json
import re
from html import unescape

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

KEY = "sk-ant-planted-card-key-0123456789"


def _get(n, path):
    r = n["client"].get(path)
    return r, r.get_data(as_text=True)


def _post(n, path, data=None):
    r = n["client"].post(path, data=data or {}, headers={"HX-Request": "true"})
    return r, r.get_data(as_text=True)


def _card(html):
    m = re.search(r'<section class="card set-card[^"]*" id="card-ai".*?</section>', html, re.S)
    assert m, "no AI card"
    return re.sub(r"\s+", " ", m.group(0))


def _page(n):
    return _get(n, "/v2/settings/installation?tab=connections")[1]


def _loaded(n):
    m = re.search(r'id="form-ai".*?name="loaded" value=\'([^\']*)\'', _page(n), re.S)
    assert m, "the AI card draws no loaded field"
    return unescape(m.group(1))


def _record(n):
    p = n["dir"] / "settings_record.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


@pytest.fixture
def no_send(monkeypatch):
    from modules.ai import anthropic_adapter

    def refuse(*a, **k):
        raise AssertionError("a call was sent")
    monkeypatch.setattr(anthropic_adapter, "send", refuse)


def test_the_card_draws_off_by_default(networks, no_send):
    card = _card(_page(networks))
    assert "AI (hosted)" in card and "Hosted AI" in card
    assert ">off<" in card and "every call is refused until a person allows hosted AI" in card
    assert "API key" in card and ">not set<" in card
    assert 'name="ai_cap_usd_per_call"' not in card, "a call's cap is its task's (retiring)"
    assert 'name="ai_cap_usd_per_day"' in card and 'value="1.5"' in card
    assert "Spent today" in card and "$0.0000" in card and "in 0 calls today" in card


def test_the_card_draws_each_task_s_pinned_model_and_prices_read_only(networks, no_send):
    """The operator, 2026-10-25: task → model (its exact id) → input and output price per
    million tokens → the page and the date; each task's cap from its pin."""
    from modules.ai import profiles
    card = unescape(_card(_page(networks)))
    for name, t in profiles.TASKS.items():
        p = profiles.MODELS[t["model"]]["price"]
        row = re.search(r'<tr data-task="' + name + r'"><td>' + re.escape(t["words"])
                        + r"</td>(.*?)</tr>", card)
        assert row, name
        cells = row.group(1)
        assert t["model"] in cells and f"${p['input']} / ${p['output']}" in cells, cells
        assert f"${profiles.cap_per_call(name):.4f}" in cells, cells
    assert profiles.PRICES_SOURCE in card and f"read {profiles.PRICES_AS_OF}" in card
    assert "older than" not in card, "fresh prices say no staleness"
    assert '<input' not in card.split('class="set-prices"')[1].split("</div>")[0], "read-only"


def test_the_card_says_when_the_prices_are_older_than_90_days(networks, no_send, monkeypatch):
    from modules.ai import profiles
    real = profiles.table
    monkeypatch.setattr(profiles, "table", lambda today=None: real(today="2027-02-01"))
    card = unescape(_card(_page(networks)))
    assert "99 days ago, older than 90; read the page again and update the table" in card


def test_replace_stores_the_key_never_draws_it_and_its_test_is_refused_while_off(networks,
                                                                                 no_send):
    r, html = _post(networks, "/v2/settings/installation/card/ai/replace",
                    {"anthropic_api_key": KEY})
    card = _card(html)
    assert r.status_code == 200 and "API key replaced" in card and KEY not in html
    assert "Test failed" in card and "ai off" in card
    from modules.secrets_store import SECRET_KEYS, get_secret
    assert get_secret("anthropic_api_key") == KEY
    # Sealed at rest, never in clear in the settings file (the operator, 2026-10-25: a test
    # fails if anthropic_api_key leaves SECRET_KEYS).
    from modules.config import USER_SETTINGS_FILE
    assert "anthropic_api_key" in SECRET_KEYS
    with open(USER_SETTINGS_FILE, encoding="utf-8") as fh:
        stored = json.load(fh)["anthropic_api_key"]
    assert KEY not in stored and stored.startswith("enc:v1:"), "the key is sealed at rest"
    (row,) = [x for x in _record(networks) if x["kind"] == "card_replace"]
    assert row["card"] == "ai" and row["fields"] == ["anthropic_api_key"]
    assert KEY not in json.dumps(_record(networks))
    _r, form = _get(networks, "/v2/settings/installation/card/ai/replace")
    assert "makes one small, recorded call to the model" in form


def test_the_card_s_test_is_an_ai_control_and_save_replace_allow_stay_usable(networks, no_send,
                                                                            monkeypatch):
    """PHASE8_PLAN 15.13, through the Installation page's real route: the AI card's Test
    carries the AI mark with its task, model and cap; while hosted AI cannot answer it is
    disabled with the reason in place (the card's link for a person who may configure), and
    Save, Replace… and Allow beside it need no AI and are never disabled for it."""
    from tests import ai_controls_check as AIC

    def get():
        return _page(networks)

    def parity(html):
        card = re.search(r'<section class="card set-card[^"]*" id="card-ai".*?</section>', html,
                         re.S).group(0)
        save = re.findall(r'<button type="submit" class="btn btn-primary btn-small"[^>]*>', card)
        allow = re.findall(r'<form class="set-form" id="form-ai-allow".*?<button[^>]*>', card,
                           re.S)
        assert len(save) == 1 and len(allow) == 1, (save, allow)
        assert "data-ai-off" not in save[0] and "data-ai-off" not in allow[0]
        assert "/installation/card/ai/replace" in card, "Replace… is drawn"
    AIC.check_screen(monkeypatch, get, "ai_card_test", parity)


@pytest.mark.parametrize("reason", ["", "too short", "x" * 301])
def test_allow_needs_a_reason_of_its_bounds(networks, no_send, reason):
    r, html = _post(networks, "/v2/settings/installation/ai/allow", {"reason": reason})
    assert r.status_code == 409 and "a reason of 10 to 300 characters is required" in html
    from modules.settings_schema import get_setting
    assert get_setting("ai_hosted", {}) == {} and _record(networks) == []


def test_allow_writes_who_when_and_why_and_turn_off_empties_it(networks, no_send):
    why = "the lab's proof of concept, workspace capped at its monthly limit"
    r, html = _post(networks, "/v2/settings/installation/ai/allow", {"reason": why})
    card = _card(html)
    assert r.status_code == 200 and "Hosted AI allowed" in card and why in unescape(card)
    from modules.settings_schema import get_setting
    got = get_setting("ai_hosted", {})
    assert got["reason"] == why and got["by"] and got["at"]
    allow = [x for x in _record(networks) if x["kind"] == "ai_hosted_allow"]
    assert len(allow) == 1 and allow[0]["reason"] == why
    r, html = _post(networks, "/v2/settings/installation/ai/off")
    assert r.status_code == 200 and "Hosted AI turned off" in _card(html)
    assert get_setting("ai_hosted", {}) == {}
    assert [x["kind"] for x in _record(networks)][-1] == "ai_hosted_off"
    r, html = _post(networks, "/v2/settings/installation/ai/off")
    assert "Already off" in _card(html)
    assert [x["kind"] for x in _record(networks)].count("ai_hosted_off") == 1


def test_a_test_allowed_and_keyed_is_one_recorded_call_as_the_person(networks, monkeypatch):
    from modules.ai import anthropic_adapter, calls
    from modules.secrets_store import set_secret

    set_secret("anthropic_api_key", KEY)
    _post(networks, "/v2/settings/installation/ai/allow",
          {"reason": "the lab's proof of concept, capped"})
    sent = []

    def echo(body, key):
        sent.append(json.dumps(body))
        word = body["messages"][0]["content"].split("\n")[1]
        return anthropic_adapter.Reply(
            status=200, body={"content": [{"type": "text", "text": json.dumps({"echo": word})}],
                              "stop_reason": "end_turn",
                              "usage": {"input_tokens": 90, "output_tokens": 9}})
    monkeypatch.setattr(anthropic_adapter, "send", echo)
    r, html = _post(networks, "/v2/settings/installation/card/ai/test")
    card = _card(html)
    assert r.status_code == 200 and "Test passed" in card and "answered" in card
    assert len(sent) == 1 and KEY not in sent[0]
    (row,) = calls.read()["rows"]
    assert row["verdict"] == "ok" and row["feature"] == "connection_check" and row["actor"]
    assert "ai_calls" in r.headers.get("X-NMAS-Invalidates", "")


def test_the_day_cap_saves_as_a_number_and_refuses_a_word_or_too_much(networks, no_send):
    from modules.settings_schema import get_setting
    r, html = _post(networks, "/v2/settings/installation/card/ai/save",
                    {"ai_cap_usd_per_day": "0.75", "loaded": _loaded(networks)})
    assert r.status_code == 200 and "Saved</strong>" in _card(html)
    assert get_setting("ai_cap_usd_per_day") == 0.75
    r, html = _post(networks, "/v2/settings/installation/card/ai/save",
                    {"ai_cap_usd_per_day": "lots", "loaded": _loaded(networks)})
    assert r.status_code == 409 and "is not an amount in US dollars" in html
    r, html = _post(networks, "/v2/settings/installation/card/ai/save",
                    {"ai_cap_usd_per_day": "99", "loaded": _loaded(networks)})
    assert r.status_code == 409 and get_setting("ai_cap_usd_per_day") == 0.75
