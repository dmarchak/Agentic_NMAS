"""The top bar's AI chip and the spend panel it opens (boards AI1 and AI2, signed off under the
Phase 7 mode 2026-10-27; PHASE8_PLAN 18.3 rules 8 and 10a, 10b; CLAUDE.md, "AI spend is shown
where people work"; C1843). Through the real routes, the real settings file, the real record of
AI calls and the real Settings › AI Turn off; only the provider key's presence is planted.

Each test holds one purpose:
- every v2 page carries the chip, asked on load and again on `ai_calls` and `settings`, never
  on a timer; the panel is asked only when opened (its own event, never a body key);
- the chip's words and colour: "AI $X today · N background on", neutral under 50%, amber from
  50% and red from 80% of the day cap, the figure's provenance (and that the provider bills) on
  hover, the figure alone at phone width;
- "AI off" with hosted AI off or no key, never blank, in every state;
- no day cap: neutral, "no cap" beside the figure;
- an unreadable record: red "AI spend unknown", never $0;
- the panel draws today, the viewer's own spend, today by trigger and each evaluation run, the
  7- and 30-day averages, month to date against the month cap with its projection, each
  background feature with its trigger, caps and estimate against actual, and Turn off;
- the panel says an unreadable record, and still offers Turn off on each feature on;
- Turn off in the panel is Settings › AI's route and gate, answered in the panel, and the
  feature's next call is refused;
- a person who may not change background features is refused in the panel, nothing written;
- both fragments are under the strict policy;
- Needs attention's AI spend rows (C2056; board AI2's second region) each draw Open the spend
  panel, a feature's row Settings › AI beside it; and in a real browser the row's control opens
  the panel in place, the page unmoved, again after Esc closed it.
"""
import datetime
import re
from html import unescape

import pytest

from modules import csp, identity
from modules.ai import background as B
from modules.ai import calls, profiles
from tests.conftest import TEST_PERSON
from tests.test_settings_ai_v2 import NET, _call, _post, _record, _turn_on, ai  # noqa: F401
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

CHIP = "/v2/ai/chip"
PANEL = "/v2/ai/spend"
OFF = f"/v2/settings/installation/ai/background/{NET}/fake_loop/off?answer=panel"


@pytest.fixture
def spend(ai, monkeypatch):  # noqa: F811 (the fixture above)
    """Settings › AI's world (hosted AI allowed, a $1.50 day cap, the fake feature) with a
    provider key set."""
    from modules import secrets_store
    monkeypatch.setattr(secrets_store, "is_set", lambda key: key == "anthropic_api_key")
    return ai


def _get(w, path):
    r = w.client.get(path, headers={"HX-Request": "true"})
    return r, unescape(r.get_data(as_text=True))


def _now_iso(hours_ago=0.0):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)
    # Never before today's midnight (UTC, the day cap's default boundary).
    midnight = t.replace(hour=0, minute=0, second=1, microsecond=0)
    return max(t, midnight).strftime("%Y-%m-%dT%H:%M:%SZ")


def _spent(cost, actor="someone@example.com", trigger=None, **extra):
    row = {"id": calls.new_id(), "at": _now_iso(), "feature": "connection_check",
           "actor": actor, "model": "m", "verdict": "ok", "cost_usd": cost}
    if trigger:
        row["trigger"] = trigger
    row.update(extra)
    assert calls.record(row)["recorded"]


def _text(html):
    """What a person reads: the tags out, the spaces they leave collapsed."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    return re.sub(r" ([,.;:)])", r"\1", text)


def _chip(html):
    m = re.search(r'<span class="ai-chip ai-([a-z]+)" data-state="([a-z]+)" title="([^"]*)" '
                  r'aria-label="([^"]*)"><span class="ai-chip-mark" aria-hidden="true">AI</span>'
                  r'<span class="ai-text">([^<]*)</span><span class="ai-short" '
                  r'aria-hidden="true">([^<]*)</span>(<span class="ai-nc">no cap</span>)?</span>',
                  html)
    assert m, html
    return dict(zip(("level", "state", "title", "label", "text", "short", "no_cap"),
                    m.groups()))


# ── on every page, live, never on a timer ─────────────────────────────────────────────────────

@pytest.mark.parametrize("page", ["/v2/", "/v2/devices", "/v2/history",
                                  "/v2/settings/installation?tab=ai", "/v2/help/getting-started"])
def test_every_page_carries_the_chip_and_its_panel(spend, page):
    r = spend.client.get(page)
    assert r.status_code == 200, page
    html = r.get_data(as_text=True)
    summary = re.search(r'<summary id="nmas-ai"[^>]*>', html)
    assert summary, f"{page} carries no AI chip"
    tag = summary.group(0)
    # The page's network rides along on every address it draws (routes/page_network.py).
    assert re.search(rf'hx-get="{CHIP}(\?list=[^"]*)?"', tag), tag
    trigger = re.search(r'hx-trigger="([^"]*)"', tag).group(1).split(", ")
    assert trigger == ["load", "nmas:ai_calls from:body", "nmas:settings from:body"], trigger
    # Never blank, even before its first answer.
    first = re.search(r'<summary id="nmas-ai"[^>]*>(.*?)</summary>', html, re.S).group(1)
    assert re.sub(r"<[^>]+>", "", first).strip() == "AIreading spend……"
    panel = re.search(r'<div class="menu ai-menu card"[^>]*id="nmas-ai-panel"[^>]*>', html).group(0)
    assert re.search(rf'hx-get="{PANEL}(\?list=[^"]*)?"', panel), panel
    assert 'hx-trigger="nmas-ai-open"' in panel, panel


def test_the_chip_and_the_panel_are_read_by_their_keys_never_by_a_timer():
    """The chip re-reads on the keys every AI call and every settings change carry; the panel
    on its opening and on `ai_calls` while open (nmas_v2.js), never polled."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = open(os.path.join(root, "templates", "v2", "base.html"), encoding="utf-8").read()
    js = open(os.path.join(root, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
    block = base[base.index('<details class="ai-spend'):base.index("</details>",
                                                                   base.index('id="ai-spend"'))]
    assert "every " not in block and "poll" not in block
    for key in ("ai_calls", "settings"):
        assert f"function relay{''.join(p.title() for p in key.split('_'))}() {{ relay('{key}'); }}" \
            in js, key
    assert "root.document.addEventListener('nmas:ai_calls', aiSpendPanel);" in js
    assert "root.document.addEventListener('toggle', aiSpendToggled, true);" in js
    assert "setInterval(aiSpend" not in js and "setTimeout(aiSpend" not in js


# ── the chip ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("usd,level", [(0.0, "neutral"), (0.74, "neutral"), (0.75, "amber"),
                                       (1.19, "amber"), (1.20, "red"), (1.60, "red")])
def test_the_chip_says_todays_spend_coloured_by_its_share_of_the_day_cap(spend, usd, level):
    if usd:
        _spent(usd)
    r, html = _get(spend, CHIP)
    assert r.status_code == 200
    c = _chip(html)
    assert c["state"] == "on" and c["level"] == level, c
    assert c["text"] == f"${usd:.2f} today · 0 background on"
    assert c["label"] == f"AI ${usd:.2f} today · 0 background on"
    assert c["short"] == f"${usd:.2f}" and c["no_cap"] is None
    pct = int(round(usd / 1.5 * 100))
    calls_n = 1 if usd else 0
    assert c["title"].startswith(f"${usd:.2f} in {calls_n} call{'' if calls_n == 1 else 's'} "
                                 "since midnight UTC (the day cap's boundary), of the day cap "
                                 f"$1.50 ({pct}%). Read from the record of AI calls at ")
    assert c["title"].endswith(f"priced from Mercury's table as of {profiles.PRICES_AS_OF}; "
                               "the provider bills what is spent.")


def test_the_chip_counts_the_background_features_on(spend):
    _turn_on(spend)
    c = _chip(_get(spend, CHIP)[1])
    assert c["text"] == "$0.00 today · 1 background on"
    assert c["short"] == "$0.00", "at phone width the count moves into the panel"


def test_the_chip_says_ai_off_never_blank(spend, monkeypatch):
    from modules import secrets_store
    from modules.settings_schema import write_settings
    monkeypatch.setattr(secrets_store, "is_set", lambda key: False)
    c = _chip(_get(spend, CHIP)[1])
    assert (c["state"], c["level"], c["text"], c["short"]) == ("off", "neutral", "AI off", "off")
    assert "no provider key is set" in c["title"] and "Nothing is sent to a model." in c["title"]
    monkeypatch.setattr(secrets_store, "is_set", lambda key: True)
    assert write_settings({"ai_hosted": {}})["ok"]
    c = _chip(_get(spend, CHIP)[1])
    assert c["text"] == "AI off" and c["title"].startswith("Hosted AI is off:")


def test_with_no_day_cap_the_chip_is_neutral_and_says_no_cap(spend):
    from modules.settings_schema import write_settings
    assert write_settings({"ai_cap_usd_per_day": None})["ok"]
    _spent(40.0)
    c = _chip(_get(spend, CHIP)[1])
    assert c["level"] == "neutral" and c["no_cap"] and c["text"] == "$40.00 today · 0 background on"
    assert "with no day cap set (an admin chose no cap)" in c["title"]


def test_an_unreadable_record_is_red_and_unknown_never_zero(spend, monkeypatch):
    monkeypatch.setattr(calls, "rows_since", lambda start: {"state": "unreadable", "rows": [],
                                                            "error": "a torn line"})
    c = _chip(_get(spend, CHIP)[1])
    assert (c["state"], c["level"], c["text"], c["short"]) == (
        "unreadable", "red", "AI spend unknown", "unknown")
    assert "(a torn line)" in c["title"] and "never drawn as $0" in c["title"]
    assert "$0" not in c["text"] + c["short"]


# ── the panel ─────────────────────────────────────────────────────────────────────────────────

def _bg(network="branch"):
    return {"kind": "background", "feature": "fake_loop", "job": "j1", "network": network,
            "finding": {"kind": "detection", "id": "d"}}


def test_the_panel_draws_every_figure(spend):
    _turn_on(spend)
    _spent(0.20, actor=TEST_PERSON, trigger={"kind": "person", "by": TEST_PERSON})
    _spent(0.30, trigger={"kind": "person", "by": "someone@example.com"})
    _spent(0.05, actor="evaluation:run-7", trigger={"kind": "evaluation", "run": "run-7"})
    _spent(0.10, actor="job:j1", trigger=_bg())
    r, html = _get(spend, PANEL)
    assert r.status_code == 200
    text = _text(html)
    for words in ("AI spend", "How does this work?", "TODAY".title(),
                  "$0.65", "of the day cap $1.50 · 43% · 4 calls", "marks at 50% and 80%",
                  "resets", "Yours today $0.20", "People's presses $0.50",
                  "Background (1 feature) $0.10", "Evaluation runs (1) · run-7 $0.05 $0.05",
                  "Last 7 complete days", "Last 30 complete days", "a day",
                  "At this rate, by", "the day cap $1.50 times the month's",
                  "The fake loop", "network Branch",
                  "Trigger: a detection rule fires (1 call per finding)",
                  "Today $0.10 of $0.50 (20%)", "This month $0.10 of $10.00 (1%)",
                  "Estimate when turned on", "no complete day since it was turned on",
                  f"Turned on by {TEST_PERSON}", "with that estimate",
                  f"Prices from Mercury's table as of {profiles.PRICES_AS_OF}.",
                  "The provider bills what is spent; its own limit is the backstop.",
                  "Every AI call (History)", "Settings › AI"):
        assert words in text, words
    assert re.search(r"This month \([A-Z][a-z]+, [0-9.]+ of (28|29|30|31) days\)", text), text
    off = re.search(r'<button[^>]*hx-post="([^"]*)"[^>]*>', html).group(1)
    assert off == f"/v2/settings/installation/ai/background/branch/fake_loop/off?answer=panel"
    assert 'hx-target="#nmas-ai-panel"' in html and 'data-op="ai-background"' in html
    assert html.count('class="ai-bar"') == 2, "today's bar and the month's"


def test_a_feature_stopped_by_its_cap_is_said_with_how_it_resumes(spend):
    _turn_on(spend, day="0.10")
    _spent(0.0, actor="job:j1", trigger=_bg(), verdict="feature_cap", cap_kind="day")
    text = _text(_get(spend, PANEL)[1])
    assert "stopped by its day cap" in text
    assert "It resumes when the day's count resets" in text
    assert "Mercury never raises a cap." in text


def test_with_no_feature_on_the_panel_says_where_one_is_turned_on(spend):
    text = _text(_get(spend, PANEL)[1])
    assert "None. A background feature is turned on only in Settings › AI, after its estimate." \
        in text


def test_ai_off_is_said_on_the_panel_and_what_was_spent_still_drawn(spend, monkeypatch):
    from modules import secrets_store
    _spent(0.40)
    monkeypatch.setattr(secrets_store, "is_set", lambda key: False)
    text = _text(_get(spend, PANEL)[1])
    assert "no provider key is set" in text and "what was spent before is below" in text
    assert "of the day cap $1.50 · 27% · 1 call" in text


def test_an_unreadable_record_is_said_on_the_panel_with_turn_off_kept(spend, monkeypatch):
    _turn_on(spend)
    monkeypatch.setattr(calls, "rows_since", lambda start: {"state": "unreadable", "rows": [],
                                                            "error": "a torn line"})
    html = _get(spend, PANEL)[1]
    text = _text(html)
    assert "Couldn't read the record of AI calls: a torn line." in text
    assert "Nothing here is drawn as $0." in text and "Yours today" not in text
    assert "Background features on: 1." in text and "The fake loop · Branch" in text
    assert f'hx-post="/v2/settings/installation/ai/background/branch/fake_loop/off' \
           f'?answer=panel"' in html


# ── Turn off, in the panel ────────────────────────────────────────────────────────────────────

def test_turn_off_in_the_panel_is_settings_turn_off_answered_in_the_panel(spend):
    _turn_on(spend)
    assert _call(spend)["ok"] is True and len(spend.sent) == 1
    r, html = _post(spend, OFF)
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
    text = _text(html)
    assert 'data-result="off"' in html and "fake_loop turned off for Branch" in text
    assert "AI spend" in text and "Background features on" in text, "the panel is the answer"
    assert 'id="ai-bg"' not in html, "not the Settings section"
    assert "settings" in r.headers["X-NMAS-Invalidates"], "the chip reads again"
    got = _call(spend)
    assert got["ok"] is False and got.get("error") == "feature_off" and len(spend.sent) == 1
    assert [x["kind"] for x in _record(spend)] == ["ai_background_on", "ai_background_off"]
    # Off already: nothing written, said in the panel.
    r, html = _post(spend, OFF)
    assert "Already off:" in unescape(html) and len(_record(spend)) == 2


def test_a_service_is_refused_in_the_panel_and_nothing_is_written(spend, monkeypatch):
    _turn_on(spend)
    svc = identity.Identity(actor="service:ci", kind="service", service_id="ci", verified=True,
                            outcome="ok", peer="127.0.0.1", peer_trusted=True)
    from modules.settings_schema import write_settings
    assert write_settings({"require_person_for_configure": False})["ok"]
    monkeypatch.setattr(identity, "identify", lambda _request: svc)
    r, html = _post(spend, OFF)
    assert r.status_code == 403 and "Not changed:" in html and "is a service" in html
    assert "AI spend" in html, "refused in the panel"
    assert B.entry_of("branch", "fake_loop") is not None
    assert [x["kind"] for x in _record(spend)] == ["ai_background_on"]


@pytest.mark.parametrize("path", [CHIP, PANEL])
def test_both_fragments_are_under_the_strict_policy(spend, path):
    r = spend.client.get(path, headers={"HX-Request": "true"})
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY


# ── Needs attention's AI spend rows (C2056) ───────────────────────────────────────────────────

OPEN_PANEL = ('<a class="btn btn-small btn-outline" data-op="getting-started" '
              'data-next-acts="ai_spend_panel" data-ai-open href="#nmas-ai-panel">'
              'Open the spend panel</a>')


def _ai_rows(html):
    """{row id: its article's HTML} for every AI spend row Needs attention draws."""
    return {m.group(1): m.group(2) for m in re.finditer(
        r'<article class="att att-[a-z]+" data-attention-row="(ai_spend:[^"]+)">(.*?)</article>',
        html, re.S)}


def test_a_day_cap_row_draws_open_the_spend_panel_and_how_it_clears(spend):
    _spent(1.25)
    r, html = _get(spend, "/v2/attention")
    assert r.status_code == 200
    (body,) = _ai_rows(html).values()
    text = _text(body)
    assert "AI spend is at 83% of the day cap ($1.25 of $1.50)" in text
    assert "Clears when the day ends (the day cap's midnight)" in text
    assert OPEN_PANEL in body
    assert 'data-manual="getting-started#ai-spend"' in body, "its How does this work?"
    assert body.count("<a class=\"btn") == 1, "the day cap's row has the one control"


def test_a_features_row_draws_the_panel_and_settings_beside_it(spend):
    _turn_on(spend)                                         # $0.50 a day for Branch
    _spent(0.30, actor="job:j1", trigger=_bg())             # 60% of it, 20% of the day cap
    rows = _ai_rows(_get(spend, "/v2/attention")[1])
    (body,) = [b for i, b in rows.items() if i.startswith("ai_spend:branch:fake_loop:day")]
    assert OPEN_PANEL in body
    assert '<a class="btn btn-small btn-outline" href="/v2/settings/installation?tab=ai">' \
           'Open…</a>' in body


def test_the_rows_control_opens_the_panel_in_place_in_a_real_browser(spend):
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    _spent(1.25)
    panel_open = ("return document.getElementById('ai-spend').open && "
                  "!!document.querySelector('#nmas-ai-panel .ai-head')")
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/"))
            b.wait_for("return !!(window.Alpine && document.querySelector("
                       "'[data-attention-row^=\"ai_spend:day_cap:\"] [data-ai-open]'))", 15)
            assert b.js("return document.getElementById('ai-spend').open") is False
            b.click('[data-attention-row^="ai_spend:day_cap:"] [data-ai-open]')
            b.wait_for(panel_open, 10)
            assert "$1.25" in b.js("return document.getElementById('nmas-ai-panel').innerText")
            assert b.js("return location.pathname + location.hash") == "/v2/", \
                "the page moved or took the fragment"
            b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', "
                 "bubbles: true})); return 1")
            b.wait_for("return !document.getElementById('ai-spend').open", 5)
            b.click('[data-attention-row^="ai_spend:day_cap:"] [data-ai-open]')
            b.wait_for(panel_open, 10)
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
