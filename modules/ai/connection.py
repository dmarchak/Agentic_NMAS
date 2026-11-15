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
#: The compile check's own task: AI troubleshooting's model (its pin, modules/ai/pins/
#: compile_check.json), 64 output tokens.
COMPILE_FEATURE = "compile_check"


@register("ping", 1)
class Ping(StrictModel):
    """The connection check's answer: the word it was given, back."""
    echo: str


#: The compile check's prompt (the operator, 2026-11-15: "add one live 'does the request
#: compile' check that I can press from the UI (cheapest possible call)").
COMPILE_PROMPT = ("compile_check", 1)


def compiled_schemas() -> list:
    """The answer schemas the AI features ask now that the compile check sends, ``[(name,
    version, model)]``: AI troubleshooting's two passes (`fixit_troubleshoot.PROMPT_PLAN_READS`
    and `PROMPT_PLAN`), whose schema the provider refused on 2026-11-15 ("The compiled grammar
    is too large")."""
    from modules.ai import fixit_troubleshoot as FT

    return [(FT.FEATURE, v, FT.SCHEMA_OF[v])
            for v in (FT.PROMPT_PLAN_READS[1], FT.PROMPT_PLAN[1])]


def compile_check(*, actor: str, trigger: dict, send=None, today: str = None) -> list:
    """Each of `compiled_schemas` sent once as the answer's schema of one call on the feature's
    own model (`COMPILE_FEATURE`'s pin: AI troubleshooting's model, 64 output tokens; the
    operator, 2026-11-15: never only the cheap model, since the morning's failure came from an
    untested assumption), ``[{"schema", "state", "words", "call_id"}]``, *state* ``compiles``
    (the provider took the schema: an answer, or one cut at max_tokens, is generated only from a
    compiled grammar), ``rejected`` (HTTP 400 from the provider, which compiles before it
    generates: the schema, its words) or ``unknown`` (any other failure: nothing is said of the
    schema). A few cents a run."""
    out = []
    for name, version, model in compiled_schemas():
        got = gateway.ask(COMPILE_FEATURE, COMPILE_PROMPT, model, {"check": "compile"},
                          actor=actor, trigger=trigger, send=send, today=today)
        kind, detail = got.get("error") or "", str(got.get("detail") or "")
        state = ("compiles" if got.get("ok") or kind == "max_tokens" else
                 "rejected" if kind == "bad_request" or detail.startswith("HTTP 400") else
                 "unknown")
        words = {"compiles": "the provider compiles it",
                 "rejected": f"the provider refused it: {detail[:200]}",
                 "unknown": f"not known: {(kind or 'failed').replace('_', ' ')}: {detail[:160]}"
                 }[state]
        out.append({"schema": f"{name}.v{version}", "state": state, "words": words,
                    "call_id": got.get("call_id", ""), "cost_usd": float(got.get("cost_usd") or 0)})
    return out


def check(*, actor: str, trigger: dict, send=None, today: str = None) -> dict:
    """``{"ok", "detail", "call_id", ...}``: the gateway's answer to one ping, its word
    compared with the one sent. *trigger* is what started it (`triggers`)."""
    word = "mercury-" + secrets.token_hex(4)
    got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, trigger=trigger,
                      send=send, today=today)
    if not got["ok"]:
        return got
    if got["output"].echo != word:
        return {"ok": False, "error": "schema", "call_id": got["call_id"],
                "detail": f"the answer echoed {got['output'].echo[:40]!r}, not {word!r}"}
    return {"ok": True, "detail": f"answered, ${got['cost_usd']:.5f}",
            "call_id": got["call_id"], "cost_usd": got["cost_usd"]}


def card_test(*, actor: str, trigger: dict) -> dict:
    """The AI card's Test (the operator, 2026-11-15): `check`, then, when it answered,
    `compile_check`. ``{"ok", "error", "detail", "call_id", "compiled"}``: passes only when the
    ping answered and every schema compiles, the detail naming each schema's state."""
    got = check(actor=actor, trigger=trigger)
    if not got.get("ok"):
        return got
    compiled = compile_check(actor=actor, trigger=trigger)
    usd = float(got.get("cost_usd") or 0) + sum(c["cost_usd"] for c in compiled)
    said = "; ".join(f"{c['schema']}: {c['words']}" for c in compiled)
    if any(c["state"] != "compiles" for c in compiled):
        rejected = any(c["state"] == "rejected" for c in compiled)
        return {"ok": False, "error": "schema_rejected" if rejected else "schema_unknown",
                "call_id": got["call_id"], "compiled": compiled, "cost_usd": usd,
                "detail": f"answered, but not every AI request's schema compiles: {said}"}
    return {"ok": True, "detail": f"answered, and every AI request's schema compiles ({said}), "
                                  f"${usd:.5f}",
            "call_id": got["call_id"], "cost_usd": usd, "compiled": compiled}
