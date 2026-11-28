"""The assistant's model selector (the operator, 2026-11-28: "add a model selector to the chat").

A person may ask the toolbar assistant a question on another model than its pin: the models its
task offers (`profiles.CHOOSABLE`, the pin's first), chosen in the box beside Send and sent with
the question. The choice is checked twice: by the route, which refuses an unoffered model at
once and keeps nothing, and by the gateway's one home of what is sent (`gateway.request_body`),
which refuses a model the task does not offer, a task that offers none, and any call that is not
a person's, so a background call always runs on its pin. The call is then sent, counted, capped,
priced and recorded as the chosen model; a model whose profile cannot turn thinking off (Opus)
is sent with adaptive thinking. Choosing the pin's own model sends exactly what no choice sends.
The panel draws the offered models with what each costs against the default, the newest answer's
model chosen, so a choice follows the person across pages and reloads.
"""
import json
from html import unescape

import pytest

from modules.ai import assistant, gateway, profiles, triggers
from tests import assistant_ask
from tests.ai_person import PERSON
from tests.test_ai_assistant import world  # noqa: F401 (the fixture)
from tests.test_ai_assistant_stage2 import DEVICE_PATH, lab, panel  # noqa: F401

HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
Q = "How do I reload a device safely?"


def _answer(world_):
    from modules.ai import manual_index
    chosen = manual_index.select(Q, screen="Devices")
    assert chosen, "the premise: a passage is chosen"
    world_["state"]["answer"] = {"answer": "Open the device page, then Actions › Reload…",
                                 "cites": [chosen[0]["link"]], "covered": True,
                                 "screens": ["Devices"]}


def _ask(model=None):
    return assistant.answer(Q, screen="Devices", actor=PERSON, trigger=triggers.person(PERSON),
                            model=model)


def _rows(world_):
    import os
    from modules.ai import calls
    path = calls._path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ── what may be chosen ─────────────────────────────────────────────────────────────────────────

class TestWhatMayBeChosen:
    def test_the_assistant_offers_its_pin_first_then_the_larger_models(self):
        assert profiles.CHOOSABLE["assistant"][0] == profiles.task("assistant")["model"]
        assert set(profiles.CHOOSABLE["assistant"]) == {HAIKU, SONNET, OPUS}
        assert all(m in profiles.MODELS for m in profiles.CHOOSABLE["assistant"])

    def test_an_offered_model_on_a_persons_press_is_allowed(self):
        for m in (HAIKU, SONNET, OPUS):
            assert profiles.choice_refusal("assistant", m, person=True) == ""

    def test_a_model_the_task_does_not_offer_is_refused_naming_it_and_the_offered(self):
        why = profiles.choice_refusal("assistant", "claude-unknown-1", person=True)
        assert "'claude-unknown-1'" in why and SONNET in why and OPUS in why

    def test_a_task_that_offers_no_choice_is_refused_naming_its_pin(self):
        why = profiles.choice_refusal("explain", SONNET, person=True)
        assert "offers no model choice" in why
        assert profiles.task("explain")["model"] in why

    def test_a_call_that_is_not_a_persons_never_chooses(self):
        why = profiles.choice_refusal("assistant", SONNET, person=False)
        assert "only by a person's press" in why

    def test_opus_is_sent_with_adaptive_thinking_as_it_cannot_turn_thinking_off(self):
        assert profiles.task("assistant")["thinking"] == "off", "the premise"
        assert profiles.chosen_pin("assistant", OPUS)["thinking"] == "adaptive"
        assert profiles.chosen_pin("assistant", SONNET)["thinking"] == "off"
        assert profiles.chosen_pin("assistant", OPUS)["model"] == OPUS
        assert profiles.chosen_pin("assistant", HAIKU) == profiles.task("assistant")

    def test_each_choice_says_what_it_costs_against_the_default(self):
        got = {m["model"]: m for m in profiles.choices("assistant")}
        assert got[HAIKU]["pinned"] and got[HAIKU]["times"] == 1
        assert (got[SONNET]["times"], got[OPUS]["times"]) == (20, 40)
        assert got[OPUS]["words"] == "Claude Opus 5.5"
        assert profiles.choices("explain") == []


# ── what is sent and recorded ──────────────────────────────────────────────────────────────────

class TestWhatIsSent:
    @pytest.fixture(autouse=True)
    def _pressed(self):
        """Each call here is a verified person's press (tests/ai_person.py)."""
        from tests.ai_person import pressed_by
        with pressed_by(PERSON):
            yield

    def test_a_chosen_model_is_the_model_sent_recorded_and_priced(self, world):
        _answer(world)
        got = _ask(SONNET)
        assert (got["ok"], got["state"]) == (True, "answered"), got
        (req,) = world["sent"]
        assert req["body"]["model"] == SONNET
        assert got["model"] == SONNET and got["model_words"] == "Claude Sonnet 5.5"
        (row,) = [r for r in _rows(world) if r.get("id") == got["call_id"]]
        assert row["model"] == SONNET and row.get("model_chosen") == SONNET
        # Priced at Sonnet's rates for the fake's usage (3000 in, 200 out), never the pin's.
        assert row["cost_usd"] == pytest.approx(profiles.cost_usd(SONNET, 3000, 200))
        assert row["cost_usd"] > profiles.cost_usd(HAIKU, 3000, 200) * 10

    def test_opus_is_sent_without_a_thinking_off_it_would_refuse(self, world):
        _answer(world)
        got = _ask(OPUS)
        assert got["state"] == "answered", got
        (req,) = world["sent"]
        assert req["body"]["model"] == OPUS
        assert "thinking" not in req["body"], req["body"].get("thinking")

    def test_choosing_the_pins_own_model_sends_what_no_choice_sends(self, world):
        _answer(world)
        _ask(None)
        _ask(HAIKU)
        first, second = world["sent"]
        assert first["body"] == second["body"]
        assert first["body"]["model"] == HAIKU
        assert not any(r.get("model_chosen") for r in _rows(world)), "recorded as no choice"

    def test_a_call_asked_once_more_after_a_mid_answer_error_keeps_the_chosen_model(
            self, world, monkeypatch):
        from modules.ai import anthropic_adapter as A
        _answer(world)
        bodies, real = [], A.send

        def send(body, key, **kw):
            bodies.append(body["model"])
            if len(bodies) == 1:
                raise A.StreamError("overloaded_error mid-answer",
                                    usage={"input_tokens": 3000, "output_tokens": 20},
                                    partial=True, output_began=True)
            return real(body, key, **kw)
        monkeypatch.setattr(A, "send", send)
        got = _ask(SONNET)
        assert got["state"] == "answered", got
        assert bodies == [SONNET, SONNET], "the retry is a new call on the same chosen model"

    def test_a_call_with_no_choice_asked_once_more_stays_on_its_pin_unrefused(
            self, world, monkeypatch):
        # The review of 2026-11-28: the retry passed the model SENT as a choice, refused for
        # every task that offers none ("nl_query offers no model choice").
        from modules.ai import anthropic_adapter as A
        _answer(world)
        bodies, real = [], A.send

        def send(body, key, **kw):
            bodies.append(body["model"])
            if len(bodies) == 1:
                raise A.StreamError("overloaded_error mid-answer",
                                    usage={"input_tokens": 3000, "output_tokens": 20},
                                    partial=True, output_began=True)
            return real(body, key, **kw)
        monkeypatch.setattr(A, "send", send)
        got = _ask(None)
        assert got["state"] == "answered", got
        assert bodies == [HAIKU, HAIKU]
        assert not any(r.get("model_chosen") for r in _rows(world)), "no choice was made"

    def test_opus_thinking_is_sized_by_its_own_maximum_never_the_pins_measured_bound(
            self, world):
        from modules.ai import background
        _answer(world)
        pinned = background.output_bound("assistant")
        got = _ask(OPUS)
        assert got["state"] == "answered", got
        (req,) = world["sent"]
        assert req["body"]["max_tokens"] > pinned["tokens"], (req["body"]["max_tokens"], pinned)

    @pytest.mark.parametrize("feature,model,kind,why", [
        ("assistant", "claude-unknown-1", triggers.PERSON, "is not one of the models"),
        ("explain", SONNET, triggers.PERSON, "offers no model choice"),
        ("assistant", SONNET, triggers.BACKGROUND, "only by a person's press"),
    ])
    def test_the_gateway_refuses_a_choice_the_task_or_the_trigger_does_not_allow(
            self, feature, model, kind, why):
        got = gateway.request_body(feature, assistant.PROMPT, assistant.AssistantAnswerV3,
                                   {"question": Q}, kind=kind, model=model)
        assert got.get("refused"), got
        assert got["refused"][0] == "model_choice"
        assert why in got["refused"][1] and "nothing was sent" in got["refused"][1]
        assert "body" not in got

    def test_a_refused_choice_is_a_recorded_call_and_nothing_is_sent(self, world):
        _answer(world)
        got = gateway.ask("assistant", assistant.PROMPT, assistant.AssistantAnswerV3,
                          {"question": Q}, actor=PERSON, trigger=triggers.person(PERSON),
                          model="claude-unknown-1")
        assert (got["ok"], got["error"]) == (False, "model_choice"), got
        assert world["sent"] == []
        (row,) = [r for r in _rows(world) if r.get("id") == got["call_id"]]
        assert row["verdict"] == "model_choice"


# ── the box ────────────────────────────────────────────────────────────────────────────────────

class TestTheBox:
    def test_a_question_sent_on_a_model_is_answered_on_it_and_the_panel_keeps_it(self, lab):
        # The box as a person first sees it: the offered models beside Send, the default chosen.
        r, html = panel(lab)
        assert r.status_code == 200
        start = html.index('id="asst-model"')
        select = html[start:html.index("</select>", start)]
        assert 'name="model"' in html[html.rindex("<select", 0, start):html.index(">", start)]
        for m, words in ((HAIKU, "Haiku 5.5 · default"), (SONNET, "Sonnet 5.5 · 20× the cost"),
                         (OPUS, "Opus 5.5 · 40× the cost")):
            assert f'value="{m}"' in select and words in select, (m, select)
        assert f'value="{HAIKU}" selected' in select
        assert html.index('id="asst-model"') < html.index('id="asst-send"'), "beside Send"
        # Sent on Opus: answered on it, and the panel opens on it again.
        _answer(lab)
        r = assistant_ask.ask(lab["client"], {"question": Q, "screen": "", "path": DEVICE_PATH,
                                              "model": OPUS}, query_string={"list": "Lab"})
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 200, html[-400:]
        assert lab["sent"] and lab["sent"][-1]["body"]["model"] == OPUS
        assert "Claude Opus 5.5" in html, "the answer's quiet line names the model it ran on"
        _r, again = panel(lab)
        start = again.index('id="asst-model"')
        assert f'value="{OPUS}" selected' in again[start:again.index("</select>", start)]

    def test_a_model_the_assistant_does_not_offer_is_refused_at_once_and_kept_nowhere(self, lab):
        _answer(lab)
        r = lab["client"].post("/v2/assistant/ask?list=Lab",
                               data={"question": Q, "screen": "", "path": DEVICE_PATH,
                                     "model": "claude-unknown-1"})
        html = unescape(r.get_data(as_text=True))
        assert "Couldn't answer" in html and "'claude-unknown-1'" in html, html[-600:]
        assert 'data-turn-state="working"' not in html
        assert lab["sent"] == []
        from modules.ai import assistant_threads
        assert not assistant_threads.read(PERSON).get("rows")
