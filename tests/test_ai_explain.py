"""P1's Explain (PHASE8_PLAN 15.9, card P1's one AI step; modules/ai/explain.py), against
planted answers (live cases wait for Allow): the pack is tests/test_evidence_pack.py's, built
from the real captures by the real builder (r1 by IPv6, the planted community line in its logs,
an instruction planted in an interface description), the gateway allowed with a fake `send`.

- The request: its prompt and the pack's format as the cached prefix, exactly three data
  blocks (the network around the device, the pack and the alert, in that order; prompt v2,
  tests/test_ai_explain_topology.py), no tool offered, the prompt under its task's bound; the planted
  instruction only in the data; a stored secret's value the pack kept is not in the bytes sent.
- The check: an answer citing only the pack's references and naming a read on the allowlist is
  shown; a reference the pack does not hold, a confirming command that is not a read, an
  answer citing nothing, more than three hypotheses, or a schema failure is "couldn't analyse"
  and nothing of it is shown; a refusal says why.
- The pack: one changed since it was built is not explained; one not kept says so; hosted AI
  off is said as information, the pack still drawn.
- The card, through the real routes and in a real browser: Explain draws the hypotheses in the
  pack, each reference a link to its piece.
"""
import json
import re

import pytest

from modules import evidence_pack as EP
from modules.ai import anthropic_adapter as A
from modules.ai import calls, explain, gateway, profiles
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import (INJECTION, V6, _alerts, _build, _section,  # noqa: F401
                                      pack_lab)

KEY = "sk-planted-test-key-0123456789"


@pytest.fixture
def world(pack_lab, monkeypatch, tmp_path):
    settings = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                              "reason": "the lab's proof of concept"},
                "ai_cap_usd_per_day": 1.50}
    from modules import settings_schema
    monkeypatch.setattr(settings_schema, "get_setting", lambda k, d=None: settings.get(k, d))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    # The AI controls ask whether a key is stored, presence only (modules/ai/controls.py).
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    pack = _build(_alerts(V6, extra_labels={"ifAlias": INJECTION}))
    assert EP.record(pack)["ok"]

    class W:
        pass
    w = W()
    w.lab, w.pack, w.sent, w.answer, w.settings = pack_lab, pack, [], None, settings

    def send(body, key):
        w.sent.append({"bytes": json.dumps(body), "body": body})
        return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(
            w.answer) if not isinstance(w.answer, str) else w.answer}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 4000, "output_tokens": 300}},
            attempts=1, latency_s=0.9)
    w.send = send
    monkeypatch.setattr(A, "send", send)
    return w


def _refs(pack, section):
    return [p["ref"] for p in _section(pack, section)["pieces"]]


def _answer(pack, **over):
    a = {"outcome": "answer",
         "rationale": "Input errors rose on r1 while its log shows a configuration change.",
         "hypotheses": [{"claim": "A configuration change on r1 preceded the errors.",
                         "evidence_refs": [_refs(pack, "logs")[0], "alert"],
                         "confirm_with": "show interfaces | include errors"}],
         "needs_human": False, "why_not": ""}
    a.update(over)
    return a


def _explain(world):
    return explain.explain(world.pack["id"], actor="operator@example.com", send=world.send,
                           today="2026-10-25")


# ---------------------------------------------------------------------------- the request

def test_the_request_is_the_pack_as_data_with_no_tool(world):
    from modules.ai import prompts
    world.answer = _answer(world.pack)
    assert _explain(world)["ok"] is True
    body = world.sent[0]["body"]
    assert "tools" not in body and set(body) == {"model", "max_tokens", "system", "messages",
                                                 "output_config"}
    assert body["model"] == profiles.TASKS["explain"]["model"]
    assert body["system"][0]["text"] == prompts.load(*explain.PROMPT)["text"]
    assert "evidence pack has sections" in body["system"][1]["text"]
    data = re.findall(r'<data name="([^"]+)">', body["messages"][0]["content"])
    # Prompt v2 (15.15): the network around the device beside the pack, the alert last
    # (tests/test_ai_explain_topology.py holds what the topology carries).
    assert data == ["network_topology", "pack", "the_alert"]
    assert gateway.prompt_tokens(body) <= profiles.TASKS["explain"]["max_prompt_tokens"]


def test_the_planted_instruction_rides_only_as_data(world):
    world.answer = _answer(world.pack)
    _explain(world)
    body = world.sent[0]["body"]
    marker = "Ignore all previous instructions"
    assert marker in body["messages"][0]["content"]
    assert marker not in json.dumps(body["system"])


def test_a_stored_secret_the_pack_kept_is_masked_in_the_bytes_sent(world, monkeypatch):
    """The pack was built before this value was a known secret, so it holds it; the egress
    mask, by value, keeps it from the bytes sent."""
    from modules import redact
    alias = _section(world.pack, "alert")["pieces"][0]["labels"]["ifAlias"]
    stored = alias.split()[2]                       # "previous", of the planted description
    assert len(stored) >= 8 and stored in json.dumps(world.pack)
    monkeypatch.setattr(redact, "known_secret_values", lambda: {stored: "Lab:enable"})
    world.answer = _answer(world.pack)
    assert _explain(world)["ok"] is True
    assert stored not in world.sent[0]["bytes"]


# ---------------------------------------------------------------------------- the check

def test_an_answer_citing_the_pack_with_an_allowed_read_is_shown(world):
    world.answer = _answer(world.pack)
    got = _explain(world)
    assert got["ok"] is True
    assert got["answer"]["hypotheses"][0]["confirm_with"] == "show interfaces | include errors"


@pytest.mark.parametrize("change,words", [
    ({"evidence_refs": ["logs:999"]}, "cites 'logs:999', which is not in the pack"),
    ({"evidence_refs": []}, "cites nothing in the pack"),
    ({"confirm_with": "configure terminal"}, "is not a read Mercury allows"),
    ({"confirm_with": "reload"}, "is not a read Mercury allows"),
])
def test_an_answer_the_pack_does_not_bear_out_is_couldnt_analyse(world, change, words):
    a = _answer(world.pack)
    a["hypotheses"][0].update(change)
    world.answer = a
    got = _explain(world)
    assert got["ok"] is False and got["error"] == "couldnt_analyse", got
    assert words in got["detail"] and "answer" not in got


def test_more_than_three_hypotheses_is_couldnt_analyse(world):
    a = _answer(world.pack)
    a["hypotheses"] = a["hypotheses"] * 4
    world.answer = a
    assert _explain(world)["error"] == "couldnt_analyse"


def test_a_schema_failure_shows_nothing(world):
    world.answer = '{"outcome": "answer", "rationale": "x"}'
    got = _explain(world)
    assert got["ok"] is False and got["error"] == "schema" and "answer" not in got


def test_a_refusal_says_why(world):
    world.answer = _answer(world.pack, outcome="refuse", rationale="", hypotheses=[],
                           needs_human=True, why_not="every section is unreadable")
    got = _explain(world)
    assert got["error"] == "unanswerable" and "every section is unreadable" in got["detail"]


# ---------------------------------------------------------------------------- the pack

def test_a_pack_changed_since_it_was_built_is_not_explained(world, monkeypatch):
    changed = json.loads(json.dumps(world.pack))
    changed["rule"] = "something else"
    monkeypatch.setattr(EP, "find", lambda pid: (changed, "ok", ""))
    got = _explain(world)
    assert got["error"] == "changed" and world.sent == []


def test_a_pack_not_kept_says_so(world):
    got = explain.explain("ep-0000000000", actor="a", send=world.send)
    assert got["error"] == "no_pack" and world.sent == []


def test_hosted_ai_off_sends_nothing_and_the_pack_still_draws(world):
    world.settings.pop("ai_hosted")
    got = _explain(world)
    assert got["error"] == "ai_off" and world.sent == []
    from html import unescape
    c = world.lab["client"]
    html = unescape(c.get(f"/v2/monitoring/alerts/pack/{world.pack['id']}").get_data(as_text=True))
    assert "Explain" in html and 'data-op="alert-evidence"' in html
    r = c.post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
               headers={"HX-Request": "true"})
    assert "hosted AI is off until it is allowed" in unescape(r.get_data(as_text=True))


def test_explain_is_an_ai_control_and_the_pack_stays_drawn(world, monkeypatch):
    """PHASE8_PLAN 15.13, through the pack's real route: Explain carries the AI mark with its
    task, model and cap; while hosted AI cannot answer it is disabled with the reason in place
    (the AI card's link for a person who may configure), and the evidence pack is drawn whole
    beside it."""
    from tests import ai_controls_check as AIC

    def get():
        return world.lab["client"].get(
            f"/v2/monitoring/alerts/pack/{world.pack['id']}").get_data(as_text=True)

    def parity(html):
        assert f'data-pack="{world.pack["id"]}"' in html
        assert html.count('class="pack-section"') == len(world.pack["sections"]), \
            "every section of the pack is drawn"
    AIC.check_screen(monkeypatch, get, "explain", parity)


# ---------------------------------------------------------------------------- the card

def test_explain_draws_the_hypotheses_in_the_pack(world):
    from html import unescape
    world.answer = _answer(world.pack)
    c = world.lab["client"]
    r = c.post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
               headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and "A configuration change on r1 preceded the errors." in html
    ref = _refs(world.pack, "logs")[0]
    assert f'href="#{world.pack["id"]}-{ref}"' in html
    assert "show interfaces | include errors" in html and "Nothing was run" in html
    page = unescape(c.get(f"/v2/monitoring/alerts/pack/{world.pack['id']}").get_data(as_text=True))
    assert f'id="{world.pack["id"]}-{ref}"' in page, "a cited piece has its anchor"


def test_a_couldnt_analyse_shows_none_of_the_answer(world):
    from html import unescape
    a = _answer(world.pack)
    a["hypotheses"][0]["evidence_refs"] = ["logs:999"]
    world.answer = a
    r = world.lab["client"].post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
                                 headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert "Not explained: couldn't analyse" in html
    assert "A configuration change on r1" not in html


def test_explain_in_a_real_browser(world):
    """In Firefox: the card opened, its pack drawn, Explain pressed: the hypotheses draw inside
    the pack, the cited reference a link to its piece; nothing scrolls sideways at 1440."""
    from tests import browser
    from tests.test_evidence_pack import _with_packs
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as APP

    value = _with_packs(world.lab)
    six = next(i for i in EP.firing(value) if i["labels"]["instance"] == V6)
    key = EP.alert_key(six)
    pack, _s, _e = EP.find(EP.pack_id(key))
    world.answer = _answer(pack)
    sel = f'details[data-keep="pack-{key}"]'
    with browser.Served(APP.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
            b.go(srv.url("/v2/monitoring/alerts"))
            b.wait_for("return !!(window.htmx && document.querySelector('details.pack-card'))")
            b.click(f"{sel} > summary")
            # The form arrives in a swap: clicked before htmx has processed it, it would submit
            # as a plain form and leave the page (a race seen twice in three runs).
            b.wait_for(f"var f = document.querySelector('{sel} form.explain-ask');"
                       "return !!(f && f['htmx-internal-data'])", 15)
            b.js(f"document.querySelector('{sel} [data-op=alert-evidence]').click(); return 1")
            try:
                b.wait_for(f"return !!document.querySelector('{sel} .explain-list li')", 15)
            except AssertionError:
                raise AssertionError(b.js("return location.href + ' | ' + "
                                          "document.body.innerHTML.slice(0, 400)")) from None
            claim = b.js(f"return document.querySelector('{sel} .explain-list li strong')"
                         ".textContent")
            href = b.js(f"return document.querySelector('{sel} .explain-list a.pack-ref')"
                        ".getAttribute('href')")
            target = b.js(f"return !!document.getElementById("
                          f"'{href[1:]}')") if href else False
            wide = b.js("return document.documentElement.scrollWidth <= window.innerWidth")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert claim == "A configuration change on r1 preceded the errors.", claim
    assert target is True and wide is True, (href, target, wide)


def test_the_schema_is_registered_and_committed():
    from modules.ai import schemas
    assert schemas.REGISTRY[("explain", 1)] is explain.Explanation
    with open(schemas.committed_path("explain", 1), encoding="utf-8") as fh:
        assert fh.read() == schemas.committed_text(explain.Explanation)


def test_an_explanation_stopped_at_max_tokens_shows_nothing(world):
    """A complete, valid explanation whose stop is max_tokens shows nothing (the operator,
    2026-10-25; tests/test_ai_truncated_answers.py)."""
    from tests.test_ai_truncated_answers import _cut
    got = explain.explain(world.pack["id"], actor="operator@example.com",
                          send=_cut(world, json.dumps(_answer(world.pack))), today="2026-10-25")
    bound = profiles.TASKS["explain"]["max_tokens"]
    assert got["ok"] is False and "answer" not in got
    assert got["error"] == "max_tokens"
    assert got["detail"] == f"the answer ran past max_tokens ({bound})"
    (row,) = calls.read()["rows"]
    assert row["verdict"] == "max_tokens" and "output" not in row
    from flask import render_template
    from modules import csp
    from app import app
    with app.test_request_context():
        html = render_template("v2/_explain.html", x=got, csp=csp)
    assert f"Not explained: the answer ran past max_tokens ({bound})." in html
    assert "hypothes" not in html.lower(), "a cut explanation was drawn"
