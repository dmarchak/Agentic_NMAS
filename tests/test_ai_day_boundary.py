"""The AI day cap's day, stated (the operator, 2026-10-26: "make it explicit in the product";
modules/ai/calls.py `today`, `resets_at`, `reset_info`; setting `ai_cap_day_boundary`, UTC by
default).

- The day and its reset: UTC by default; a zone's midnight when stated, its daylight-saving
  change followed (America/Denver leaves DST on 1 Nov 2026). Across every hour from 30 Oct to
  3 Nov the reset is the first instant of the next day, the one the counter turns over at.
- The counter (`spent_usd`) and the gateway's refusal count the stated day.
- The AI card states the boundary beside the cap, saves a zone and refuses a name the zone
  database lacks, and says "resets" with the same instant the counter uses; an AI control's
  day-cap reason says it too.
- In Firefox, its zone America/Denver: "resets 18:00 MDT (00:00 UTC)" on 26 Oct, "17:00 MST
  (00:00 UTC)" on 1 Nov.
"""
import datetime
import json
import re

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, connection, gateway

UTC = datetime.timezone.utc


def _at(text):
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


# ── the day and its reset ────────────────────────────────────────────────────

@pytest.mark.parametrize("now,zone,day,reset", [
    ("2026-10-26T13:00:00Z", "UTC", "2026-10-26", "2026-10-27T00:00:00Z"),
    ("2026-10-26T23:59:59Z", "UTC", "2026-10-26", "2026-10-27T00:00:00Z"),
    ("2026-10-27T03:00:00Z", "America/Denver", "2026-10-26", "2026-10-27T06:00:00Z"),
    # Denver's last MDT day, and its first MST one: midnight is 06:00 UTC, then 07:00.
    ("2026-10-31T12:00:00Z", "America/Denver", "2026-10-31", "2026-11-01T06:00:00Z"),
    ("2026-11-01T12:00:00Z", "America/Denver", "2026-11-01", "2026-11-02T07:00:00Z"),
], ids=["utc", "utc-last-second", "denver-evening", "denver-before-dst-ends",
        "denver-after-dst-ends"])
def test_the_day_and_its_reset(now, zone, day, reset):
    assert calls.today(_at(now), zone) == day
    assert calls.resets_at(_at(now), zone).strftime("%Y-%m-%dT%H:%M:%SZ") == reset


@pytest.mark.parametrize("zone", ["UTC", "America/Denver"])
def test_the_reset_is_where_the_counter_turns_over_across_a_dst_change(zone):
    start = _at("2026-10-30T00:00:00Z")
    for hour in range(0, 24 * 5):
        now = start + datetime.timedelta(hours=hour)
        reset = calls.resets_at(now, zone)
        before = calls.day_of(reset - datetime.timedelta(seconds=1), zone)
        assert before == calls.today(now, zone), (now, reset)
        nxt = (datetime.date.fromisoformat(before) + datetime.timedelta(days=1)).isoformat()
        assert calls.day_of(reset, zone) == nxt, (now, reset)
        info = calls.reset_info(now, zone)
        assert info["at"] == reset.strftime("%Y-%m-%dT%H:%M:%SZ") and calls.today(now, zone) == before
        if zone == "America/Denver":
            assert info["zone_hm"] == "00:00" and info["utc"] in ("06:00", "07:00")


def test_an_unknown_zone_is_refused_and_a_stored_one_this_host_lacks_is_utc(monkeypatch):
    from modules import settings_schema
    assert calls.valid_boundary("America/Denver") and calls.valid_boundary("UTC")
    assert not calls.valid_boundary("Mars/Olympus")
    monkeypatch.setattr(settings_schema, "get_setting",
                        lambda k, d=None: "Mars/Olympus" if k == "ai_cap_day_boundary" else d)
    assert calls.boundary() == "UTC"


# ── the counter and the gateway count the stated day ───────────────────────────

@pytest.fixture
def record(tmp_path, monkeypatch):
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    # A call at 17:00 MDT on 26 Oct (23:00 UTC): yesterday in UTC at 03:00 UTC on 27 Oct,
    # today in Denver.
    calls.record({"id": "ai-0000000000000001", "feature": "connection_check", "verdict": "ok",
                  "cost_usd": 1.50, "at": "2026-10-26T23:00:00Z"})
    monkeypatch.setattr(calls, "_now", lambda: _at("2026-10-27T03:00:00Z"))


def test_the_counter_counts_the_stated_day(record):
    assert calls.spent_usd("2026-10-27", "UTC")["usd"] == 0
    assert calls.spent_usd("2026-10-26", "America/Denver")["usd"] == pytest.approx(1.50)


@pytest.mark.parametrize("zone,refused", [("UTC", False), ("America/Denver", True)])
def test_the_gateway_refuses_by_the_stated_day(record, monkeypatch, zone, refused):
    from modules import settings_schema
    settings = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                              "reason": "the lab's proof of concept"},
                "ai_cap_usd_per_day": 1.50, "ai_cap_day_boundary": zone}
    monkeypatch.setattr(settings_schema, "get_setting", lambda k, d=None: settings.get(k, d))
    monkeypatch.setattr(gateway, "_api_key", lambda: "sk-planted-test-key-0123456789")
    sent = []

    def send(body, key):
        sent.append(body)
        return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(
            {"word": "w"})}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 120, "output_tokens": 8}}, attempts=1, latency_s=0.2)
    got = gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                      actor="operator@example.com", send=send)
    assert (got.get("error") == "over_cap") is refused, got
    assert bool(sent) is not refused


# ── the screens say it ─────────────────────────────────────────────────────────

def _card(networks):
    html = networks["client"].get("/v2/settings/installation?tab=connections").get_data(
        as_text=True)
    m = re.search(r'<section class="card set-card[^"]*" id="card-ai".*?</section>', html, re.S)
    assert m, "no AI card"
    return re.sub(r"\s+", " ", m.group(0))


from tests.test_settings_v2 import networks  # noqa: E402,F401 (the fixture: a temporary store)


def test_the_card_states_the_boundary_and_its_reset_is_the_counter_s(networks, monkeypatch):
    from modules.ai import anthropic_adapter
    monkeypatch.setattr(anthropic_adapter, "send", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("a call was sent")))
    monkeypatch.setattr(calls, "_now", lambda: _at("2026-10-26T13:00:00Z"))
    card = _card(networks)
    assert 'name="ai_cap_day_boundary"' in card and 'value="UTC"' in card
    assert "The day begins at" in card
    assert ('resets <time class="clock" datetime="2026-10-27T00:00:00Z" data-clock'
            in card), card[card.find("Spent today"):][:400]
    assert ">00:00 UTC</time> (00:00 UTC)" in card
    loaded = re.search(r"name=\"loaded\" value='([^']*)'", card).group(1)
    from html import unescape
    form = {"ai_cap_usd_per_day": "1.5", "loaded": unescape(loaded)}
    r = networks["client"].post("/v2/settings/installation/card/ai/save",
                                data=dict(form, ai_cap_day_boundary="Mars/Olympus"),
                                headers={"HX-Request": "true"})
    assert r.status_code == 409 and "is not UTC, or a time zone" in r.get_data(as_text=True)
    r = networks["client"].post("/v2/settings/installation/card/ai/save",
                                data=dict(form, ai_cap_day_boundary="America/Denver"),
                                headers={"HX-Request": "true"})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    card = _card(networks)
    # 13:00 UTC is 07:00 MDT on 26 Oct: the day ends at Denver's midnight, 06:00 UTC on 27 Oct.
    assert 'datetime="2026-10-27T06:00:00Z"' in card
    assert ">00:00 America/Denver</time> (06:00 UTC)" in card


def test_an_ai_control_s_day_cap_reason_says_when_it_resets(monkeypatch):
    from flask import render_template_string
    import app as APP
    from modules.ai import controls
    monkeypatch.setattr(calls, "_now", lambda: _at("2026-10-26T13:00:00Z"))
    monkeypatch.setattr(controls, "_hosted", lambda: {"allowed": True})
    monkeypatch.setattr(controls, "_key_set", lambda: True)
    got = controls.readiness("connection_check", spent=lambda day: {"state": "ok", "usd": 9.99})
    assert got["kind"] == "day_cap" and got["resets"] == calls.reset_info()
    with APP.app.test_request_context("/"):
        html = render_template_string(
            '{% import "v2/_ai.html" as ai %}{{ ai.reason(c) }}',
            c=dict(got, name="ai_card_test", ready=False, may_configure=False))
    assert 'datetime="2026-10-27T00:00:00Z" data-clock' in html and "(00:00 UTC)" in html


@pytest.mark.parametrize("now,said", [
    ("2026-10-26T13:00:00Z", "18:00 MDT"),
    ("2026-11-01T13:00:00Z", "17:00 MST"),
], ids=["mdt", "mst"])
def test_in_a_browser_in_denver_the_reset_is_its_local_time(networks, monkeypatch, now, said):
    """Firefox started with TZ=America/Denver: the card's reset reads the viewer's own time
    of the counter's instant, and UTC's beside it, on both sides of the DST change."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as APP
    monkeypatch.setenv("TZ", "America/Denver")
    monkeypatch.setattr(calls, "_now", lambda: _at(now))
    with browser.Served(APP.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/settings/installation?tab=connections"))
            b.wait_for("var t = document.querySelector('#card-ai time[data-clock]');"
                       " return t && /M[DS]T/.test(t.textContent)", 15)
            words = b.js("var t = document.querySelector('#card-ai time[data-clock]');"
                         " return t.parentNode.textContent")
        finally:
            b.go("about:blank")
    assert f"resets {said} (00:00 UTC)" in " ".join(words.split()), words
