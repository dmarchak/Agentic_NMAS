"""The gateway: Mercury's one way to a model (PHASE8_PLAN 13.2, AI_ANTHROPIC_PLAN 3.1).

`ask(feature, prompt, schema, parts, ...)` returns ``{"ok": True, "output": <the validated
StrictModel>, "call_id", "cost_usd"}`` or ``{"ok": False, "error": <kind>, "detail", "call_id"}``,
and every call, sent or refused, is one `ai_calls` row. In order, before anything is sent:

1. **Hosted AI is allowed** on this installation: the admin's setting `ai_hosted`, with who,
   when and the recorded reason (PHASE8_PLAN 13.1, 15.8). Off by default.
2. **A key is set** (`anthropic_api_key`, in the secrets store, typed by a person).
3. **The prompt** is a registered, versioned file; **the schema** a registered StrictModel.
4. **Masked for egress**: the request built (the prompt as the system text, each part as
   delimited data, never as instructions), then `redact.egress_payload` over all of it; a
   known stored secret still present refuses the call (`unmasked_secret`), naming its label.
5. **The caps**, judged by the worst case (the input estimated from the masked request's
   size, plus all of `max_tokens`, at the model's prices): the per-call cap, and the day's
   spend so far plus this call against the day cap. A refusal names both operands.

Then the adapter sends it; a refusal, a `max_tokens` stop, an answer that is not the schema,
and each provider failure are each their own kind, never a parser's crash (13.5).
"""
import json
import logging
import time

from pydantic import ValidationError

from modules.ai import anthropic_adapter, calls, profiles, prompts, schemas

log = logging.getLogger(__name__)

#: Characters per token the input estimate assumes: under English's usual 4, so the worst
#: case is over, never under. The recorded usage replaces it once the call is answered.
CHARS_PER_TOKEN = 3.0

#: The defaults the schema seeds (modules/settings_schema.py): a call's worst case, and a
#: day's spend. PHASE8_PLAN 7 caps a month at $50 globally; $1.50 a day is under that.
DEFAULT_CAP_PER_CALL = 0.05
DEFAULT_CAP_PER_DAY = 1.50


def hosted_allowed() -> dict:
    """``{"allowed": bool, "why": str, "by", "at", "reason"}`` from the admin's setting."""
    from modules.settings_schema import get_setting
    got = get_setting("ai_hosted", {}) or {}
    if not isinstance(got, dict) or not got.get("reason") or not got.get("by"):
        return {"allowed": False, "why": "hosted AI is off: an admin allows it in Settings, "
                "with a recorded reason (PHASE8_PLAN 15.8)", "by": "", "at": "", "reason": ""}
    return {"allowed": True, "why": "", "by": got.get("by", ""), "at": got.get("at", ""),
            "reason": got.get("reason", "")}


def caps() -> dict:
    """The two caps, by their literal keys (a value that is not a number reads as its
    default)."""
    from modules.settings_schema import get_setting

    def num(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return {"per_call": num(get_setting("ai_cap_usd_per_call", DEFAULT_CAP_PER_CALL),
                            DEFAULT_CAP_PER_CALL),
            "per_day": num(get_setting("ai_cap_usd_per_day", DEFAULT_CAP_PER_DAY),
                           DEFAULT_CAP_PER_DAY)}


def _api_key() -> str:
    from modules.secrets_store import get_secret
    return get_secret("anthropic_api_key") or ""


def build_request(prompt: dict, schema_model, parts: dict, model: str, max_tokens: int) -> dict:
    """The Messages API body: the prompt as the system text; each part as data, delimited by
    its name, in one user turn; the answer's schema in `output_config.format`."""
    blocks = []
    for name in sorted(parts):
        blocks.append(f'<data name="{name}">\n{parts[name]}\n</data>')
    return {
        "model": model,
        "max_tokens": int(max_tokens),
        "system": prompt["text"],
        "messages": [{"role": "user", "content": "\n\n".join(blocks) or "(no data)"}],
        "output_config": {"format": {"type": "json_schema",
                                     "schema": schemas.schema_for(schema_model)}},
    }


def worst_case_usd(model: str, body: dict) -> float:
    est_in = int(len(json.dumps(body, ensure_ascii=False)) / CHARS_PER_TOKEN) + 1
    return profiles.cost_usd(model, est_in, int(body.get("max_tokens", 0)))


def _text_of(reply_body: dict) -> str:
    return "".join(b.get("text", "") for b in reply_body.get("content") or []
                   if b.get("type") == "text")


def ask(feature: str, prompt: tuple, schema_model, parts: dict, *, actor: str,
        model: str = profiles.DEFAULT_MODEL, max_tokens: int = 1024, send=None,
        today: str = None) -> dict:
    """One schema-bound call (the module's docstring has the order). *send* replaces the
    adapter (tests); *today* the UTC day the caps count."""
    call_id = calls.new_id()
    row = {"id": call_id, "feature": feature, "actor": actor, "model": model,
           "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "verdict": "", "detail": "",
           "cost_usd": 0.0}

    def refuse(kind, detail, **extra):
        out = calls.record(dict(row, verdict=kind, detail=detail, **extra))
        log.info("ai: %s refused for %s: %s", feature, kind, detail)
        return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,
                "recorded": out.get("recorded", False)}

    hosted = hosted_allowed()
    if not hosted["allowed"]:
        return refuse("ai_off", hosted["why"])
    key = _api_key()
    if not key:
        return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")
    try:
        profile = profiles.profile(model)
    except KeyError as exc:
        return refuse("unknown_model", str(exc))
    if profile["provider"] != profiles.ANTHROPIC:
        return refuse("unknown_model", f"{model} is not served by the Anthropic adapter")
    ident = getattr(schema_model, "__ai_schema__", None)
    if ident is None or schemas.REGISTRY.get(ident) is not schema_model:
        return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "
                      "registered AI schema")
    row["schema"] = f"{ident[0]}.v{ident[1]}"
    try:
        prompt_file = prompts.load(*prompt)
    except prompts.PromptError as exc:
        return refuse("prompt", str(exc))
    row["prompt_sha256"] = prompt_file["sha256"]

    from modules import redact
    body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,
                                               max_tokens))
    leaked = redact.contains_known_secret(body)
    if leaked:
        return refuse("unmasked_secret", "a stored secret is still in the request after "
                      f"masking ({', '.join(leaked)}); nothing was sent")
    row["request"] = body

    cap = caps()
    worst = worst_case_usd(model, body)
    if worst > cap["per_call"]:
        return refuse("over_cap", f"this call's worst case ${worst:.4f} is over the per-call "
                      f"cap ${cap['per_call']:.4f}", worst_usd=worst)
    day = today or time.strftime("%Y-%m-%d", time.gmtime())
    spent = calls.spent_usd(day)
    if spent["state"] == "unreadable":
        return refuse("over_cap", "the record of AI calls cannot be read, so today's spend "
                      f"is unknown ({spent['error']}); nothing was sent")
    if spent["usd"] + worst > cap["per_day"]:
        return refuse("over_cap", f"today's spend ${spent['usd']:.4f} plus this call's worst "
                      f"case ${worst:.4f} is over the day cap ${cap['per_day']:.4f}",
                      worst_usd=worst)

    try:
        reply = (send or anthropic_adapter.send)(body, key)
    except anthropic_adapter.AdapterError as exc:
        return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)

    usage = reply.body.get("usage") or {}
    tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",
                                                   "cache_read_input_tokens",
                                                   "cache_creation_input_tokens")}
    cost = profiles.cost_usd(model, tokens["input_tokens"] + tokens["cache_read_input_tokens"]
                             + tokens["cache_creation_input_tokens"], tokens["output_tokens"])
    text = _text_of(reply.body)
    sent = dict(row, cost_usd=cost, tokens=tokens, latency_s=round(reply.latency_s, 3),
                attempts=reply.attempts, ratelimit=reply.headers,
                stop_reason=reply.body.get("stop_reason", ""),
                response=redact.redact_egress(text))
    stop = reply.body.get("stop_reason")
    if stop == "refusal":
        details = reply.body.get("stop_details") or {}
        return _answered(sent, "refusal", "the model declined "
                         f"(category {details.get('category') or 'none given'})")
    if stop == "max_tokens":
        return _answered(sent, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")
    try:
        output = schema_model.model_validate_json(text)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ())) or "the answer"
        return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "
                         f"{first.get('msg', 'invalid')}")
    out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))
    return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,
            "recorded": out.get("recorded", False)}


def _answered(row, kind, detail):
    out = calls.record(dict(row, verdict=kind, detail=detail))
    return {"ok": False, "error": kind, "detail": detail, "call_id": row["id"],
            "cost_usd": row["cost_usd"], "recorded": out.get("recorded", False)}
