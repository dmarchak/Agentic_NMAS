"""The toolbar assistant's stage 1 (card P7; PHASE8_PLAN 16.10, its build;
modules/ai/assistant.py, routes/assistant_v2.py): a question answered from the manual's passages
code chose, through the real gateway with a fake provider (no provider is called), hosted AI
allowed with a key, the record of AI calls in the test's folder.

- **The request:** the passages chosen for the question are what is sent, after the cached
  screens; nothing of the network.
- **Mercury's check:** an answer citing a passage it was not sent, or naming a screen the manual
  does not, is refused, never drawn, and recorded as a gap; an answer that is not covered, or
  cites nothing, is drawn as "The manual doesn't cover this."
- **A question no passage answers** makes no call and is a gap.
- **A pasted secret** is masked before it leaves, the person told in words, and the gap's record
  holds it masked.
- **The route** draws the answer with its passages' links, as the person who asked.
"""
import json
import re

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import assistant, calls, gateway, manual_index
from tests.ai_person import PERSON, pressed_by  # noqa: F401

KEY = "sk-ant-test-0000"
Q = "How do I reload a device safely?"


@pytest.fixture(autouse=True)
def as_person(request):
    """Every call here is a verified person's press (tests/ai_person.py); but the controls'
    check, whose pages are each their own request (the controls' state is asked once per
    request, `controls.control`, so a request context held open would hold the first state)."""
    if "panel_is_an_ai_control" in request.node.name:
        yield
        return
    with pressed_by(PERSON):
        yield


@pytest.fixture
def world(monkeypatch, tmp_path):
    from tests.test_profile_apply import lab_setup

    lab = lab_setup(monkeypatch, tmp_path)
    lab["settings"].update(ai_hosted={"by": PERSON, "at": "2026-10-25T05:00:00Z",
                                      "reason": "the lab's proof of concept"},
                           ai_cap_usd_per_day=1.50)
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    monkeypatch.setattr(assistant, "_gaps_path", lambda: str(tmp_path / "manual_gaps.jsonl"))
    sent, state = [], {"answer": None}

    def send(body, key):
        sent.append({"bytes": json.dumps(body), "body": body})
        return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(
            state["answer"])}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 3000, "output_tokens": 200}}, attempts=1, latency_s=0.2)
    monkeypatch.setattr(A, "send", send)
    lab.update(sent=sent, state=state)
    return lab


def _answer(world, chosen, **over):
    world["state"]["answer"] = dict({"answer": "Open the device page, then Actions › Reload…",
                                     "cites": [chosen[0]["link"]], "covered": True,
                                     "screens": ["Devices"]}, **over)


def ask(world, question=Q, screen="Devices"):
    from modules.ai import triggers
    return assistant.answer(question, screen=screen, actor=PERSON,
                            trigger=triggers.person(PERSON))


def test_the_passages_chosen_are_sent_after_the_cached_screens(world):
    chosen = manual_index.select(Q, screen="Devices")
    assert chosen and chosen[0]["slug"] == "reload"
    _answer(world, chosen)
    got = ask(world)
    assert (got["ok"], got["state"]) == (True, "answered"), got
    assert got["cites"] == [{"link": chosen[0]["link"], "page": chosen[0]["page"],
                             "heading": chosen[0]["heading"]}]
    (req,) = world["sent"]
    text = req["bytes"]
    assert all(json.dumps(p["text"])[1:40] in text for p in chosen), "every passage chosen"
    assert text.index('\\"screens\\"') < text.index('\\"passages\\"') or \
        text.index('"screens"') < text.index('"passages"'), "the screens, cached, first"
    assert "203.0.113" not in text, "nothing of the network: no device's address"


@pytest.mark.parametrize("over,why", [
    ({"cites": ["/v2/help/nowhere#none"]}, "which it was not sent"),
    ({"screens": ["Mission control"]}, "which is no screen the manual names"),
])
def test_an_answer_mercury_s_check_refuses_is_never_drawn_and_is_a_gap(world, over, why):
    chosen = manual_index.select(Q, screen="Devices")
    _answer(world, chosen, **over)
    got = ask(world)
    assert (got["state"], got["gap"]) == ("refused", True) and why in got["detail"]
    assert "answer" not in got


@pytest.mark.parametrize("over", [{"covered": False, "cites": []}, {"cites": []}])
def test_an_answer_that_is_not_covered_says_the_manual_does_not_cover_it(world, over):
    _answer(world, manual_index.select(Q, screen="Devices"), **over)
    got = ask(world)
    assert (got["state"], got["detail"], got["gap"]) == (
        "not_covered", assistant.NOT_COVERED, True)


def test_a_question_no_passage_answers_makes_no_call(world):
    got = ask(world, "What is the capital of France?")
    assert (got["state"], got["gap"]) == ("not_covered", True) and world["sent"] == []


def test_a_pasted_secret_is_masked_before_it_leaves_and_said(world):
    q = "How do I rotate this? enable secret 9 $9$abcdefghijklmn$opqrstuvwxyz0123456789ABCDEFG"
    chosen = manual_index.select("How do I rotate this? enable secret 9")
    assert chosen, "the premise: the question, its secret masked out, reaches the manual"
    _answer(world, chosen, screens=[])
    got = ask(world, q, screen="")
    assert "opqrstuvwxyz0123456789" not in world["sent"][0]["bytes"]
    assert got["typed_masked"], got


def test_the_panel_is_an_ai_control_and_the_page_and_its_help_stay_usable(world, monkeypatch):
    """The panel's Ask through the AI controls' one check (tests/ai_controls_check.py): ready,
    then each state that cannot answer drawn disabled with its reason; beside it, the page and
    its manual (Help, How does this work?) need no AI."""
    from tests import ai_controls_check as AIC

    # The panel as the top bar's Assistant asks for it on the Devices page.
    def get():
        page = world["client"].get("/v2/devices").get_data(as_text=True)
        asked = re.search(r'<div class="asst-body" id="asst-body" hx-get="([^"]*)"', page)
        assert asked, "the page carries the panel's shell"
        from html import unescape
        return world["client"].get(unescape(asked.group(1))).get_data(as_text=True)

    def parity(html):
        page = world["client"].get("/v2/devices").get_data(as_text=True)
        assert 'id="nmas-assistant"' in page and " disabled" not in re.search(
            r'<button[^>]*id="nmas-assistant"[^>]*>', page).group(0), "the panel still opens"
        assert 'href="/v2/help/assistant"' in html, "its manual needs no AI"
        assert 'name="screen" value="Devices"' in html, "the page's screen ranks first"
    AIC.check_screen(monkeypatch, get, "assistant", parity)


def test_the_route_draws_the_answer_and_records_a_gap_masked(world):
    from html import unescape
    chosen = manual_index.select(Q, screen="Devices")
    _answer(world, chosen)
    r = world["client"].post("/v2/assistant/ask", data={"question": Q, "screen": "Devices"})
    page = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and f'href="{chosen[0]["link"]}"' in page
    assert "Open the device page, then Actions › Reload…" in page
    secret = "enable secret 9 $9$abcdefghijklmn$opqrstuvwxyz0123456789ABCDEFG"
    r = world["client"].post("/v2/assistant/ask",
                             data={"question": f"weather tomorrow {secret}", "screen": ""})
    assert "The manual doesn't cover this." in unescape(r.get_data(as_text=True))
    (gap,) = assistant.gaps()["rows"]
    assert gap["state"] == "not_covered" and "opqrstuvwxyz0123456789" not in json.dumps(gap)
