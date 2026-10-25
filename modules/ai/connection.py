"""Test connection: one cheap call through the whole gateway (AI_ANTHROPIC_PLAN 3.2: "Test
connection sends one cheap request and never shows the key"), so a passing check means the
allowance, the key, the mask, the caps, the adapter, the schema and the record all held.

Its answer is one word Mercury chose (`ping`'s `echo`), so a check cannot pass on a model's
fluent guess: the word is in the request's data, and the answer must return it exactly.
"""
import secrets

from modules.ai import gateway
from modules.ai.schemas import StrictModel, register

FEATURE = "connection_check"
PROMPT = ("ping", 1)


@register("ping", 1)
class Ping(StrictModel):
    """The connection check's answer: the word it was given, back."""
    echo: str


def check(*, actor: str, send=None, today: str = None) -> dict:
    """``{"ok", "detail", "call_id", ...}``: the gateway's answer to one ping, its word
    compared with the one sent."""
    word = "mercury-" + secrets.token_hex(4)
    got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, max_tokens=64,
                      send=send, today=today)
    if not got["ok"]:
        return got
    if got["output"].echo != word:
        return {"ok": False, "error": "schema", "call_id": got["call_id"],
                "detail": f"the answer echoed {got['output'].echo[:40]!r}, not {word!r}"}
    return {"ok": True, "detail": f"answered, ${got['cost_usd']:.5f}",
            "call_id": got["call_id"], "cost_usd": got["cost_usd"]}
