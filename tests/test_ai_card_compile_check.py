"""The AI card's Test asks the provider whether each AI troubleshooting request compiles (the
operator, 2026-11-15: "Fakes can't catch this, so add one live 'does the request compile' check
that I can press from the UI (cheapest possible call), and run it in every rehearsal").

Settings › Installation › AI, Test: the connection's ping, then each schema troubleshooting
sends (`connection.compiled_schemas`) as the answer's schema of one call on the Test's own pin
(64 output tokens). A schema the provider compiles passes (an answer cut at max_tokens is
generated only from a compiled grammar); one it refuses with HTTP 400 fails the Test, named
with the provider's words. Pressed through the real route as a verified person; the provider
stood in (tests/test_ai_request_compiles.py holds the schemas' shape).
"""
import json
from html import unescape

from modules.ai import anthropic_adapter as AD
from modules.ai import schemas
from modules.ai import fixit_troubleshoot as FT
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

REFUSED = ("HTTP 400: invalid_request_error: The compiled grammar is too large, which would "
           "cause performance issues. Simplify your tool schemas or reduce the number of "
           "strict tools.")


def sent_schema(model) -> dict:
    return schemas.schema_for(model)


def _press_test(n, monkeypatch, reply):
    """The AI card's Test pressed through its route as a verified person (tests/test_ai_card.py's
    way), the provider stood in by *reply* (``reply(body) -> (status, text or None)``; a 400
    raises as the adapter does, None stops at max_tokens). ``(card words, bodies sent)``."""
    from modules.secrets_store import set_secret
    from tests.test_ai_card import KEY, _card, _post

    set_secret("anthropic_api_key", KEY)
    _post(n, "/v2/settings/installation/ai/allow", {"reason": "the compile check, capped"})
    sent = []

    def send(body, key):
        sent.append(body)
        status, text = reply(body)
        if status == 400:
            raise AD.BadRequest(text, status=400)
        return AD.Reply(status=200, body={
            "content": [{"type": "text", "text": text or "{"}],
            "stop_reason": "max_tokens" if text is None else "end_turn",
            "usage": {"input_tokens": 900, "output_tokens": 64}})
    monkeypatch.setattr(AD, "send", send)
    r, html = _post(n, "/v2/settings/installation/card/ai/test")
    assert r.status_code == 200
    return unescape(_card(html)), sent


def _is_ping(body) -> bool:
    return "echo" in json.dumps(body["output_config"])


def _echo(body) -> str:
    word = body["messages"][0]["content"].split("\n")[1]
    return json.dumps({"echo": word})


def test_the_check_runs_on_the_model_troubleshooting_uses():
    # The operator, 2026-11-15: the schema check on the model the feature actually uses, not
    # only the cheap one.
    from modules.ai import connection, profiles
    assert profiles.TASKS[connection.COMPILE_FEATURE]["model"] == \
        profiles.TASKS[FT.FEATURE]["model"]
    assert connection.COMPILE_FEATURE != connection.FEATURE


def test_the_card_s_test_passes_when_each_schema_compiles(networks, monkeypatch):  # noqa: F811
    from modules.ai import profiles
    card, sent = _press_test(networks, monkeypatch,
                             lambda b: (200, _echo(b) if _is_ping(b) else None))
    assert "Test passed" in card and "every AI request's schema compiles" in card, card
    # The investigation's three passes since C3797 (v11, v12, v13).
    assert "fixit_troubleshoot.v11: the provider compiles it" in card
    # Each schema sent on the feature's own model, the ping on the cheap one.
    assert [b["model"] for b in sent[1:]] == [profiles.TASKS[FT.FEATURE]["model"]] * 3
    assert sent[0]["model"] == profiles.TASKS["connection_check"]["model"]
    # The ping, then each schema as the answer's: exactly the schemas the press sends.
    assert [b["output_config"]["format"]["schema"] for b in sent[1:]] == [
        sent_schema(FT.TroubleshootInvestigate), sent_schema(FT.TroubleshootInvestigateAgain),
        sent_schema(FT.TroubleshootInvestigated)]


def test_the_card_s_test_fails_naming_the_schema_the_provider_refuses(networks,  # noqa: F811
                                                                      monkeypatch):
    def reply(body):
        if _is_ping(body):
            return 200, _echo(body)
        # The last pass's schema refused (v13 since C3797), the others compiled.
        refused = body["output_config"]["format"]["schema"] == sent_schema(
            FT.TroubleshootInvestigated)
        return (400, REFUSED) if refused else (200, None)
    card, _sent = _press_test(networks, monkeypatch, reply)
    assert "Test passed" not in card, card
    assert "fixit_troubleshoot.v13: the provider refused it" in card, card
    assert "The compiled grammar is too large" in card
    assert "fixit_troubleshoot.v11: the provider compiles it" in card
