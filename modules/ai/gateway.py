"""The gateway: Mercury's one way to a model (PHASE8_PLAN 13.2, AI_ANTHROPIC_PLAN 3.1).

`ask(feature, prompt, schema, parts, ...)` returns ``{"ok": True, "output": <the validated
StrictModel>, "call_id", "cost_usd"}`` or ``{"ok": False, "error": <kind>, "detail", "call_id"}``,
and every call, sent or refused, is one `ai_calls` row. In order, before anything is sent:

1. **Hosted AI is allowed** on this installation: the admin's setting `ai_hosted`, with who,
   when and the recorded reason (PHASE8_PLAN 13.1, 15.8). Off by default.
2. **A key is set** (`anthropic_api_key`, in the secrets store, typed by a person).
3. **The task** is one `profiles.TASKS` pins: its model, its prompt bound and its answer
   bound (the operator's ruling of 2026-10-25: pinned per task, never chosen at run time).
   **The prompt** is a registered, versioned file; **the schema** a registered StrictModel.
4. **Masked for egress**: the request built (the prompt as the system text, each part as
   delimited data, never as instructions), then `redact.egress_payload` over all of it; a
   known stored secret still present refuses the call (`unmasked_secret`), naming its label.
5. **The prompt's length**: the estimate from the masked request's size under the task's
   bound, which is always under its model's long tier (Haiku 5.5 over 100,000 tokens pays
   every rate 5x); over it the call is refused (`prompt_too_long`), both numbers named.
6. **The caps**, judged by the worst case (that estimate as cache writes, plus all of
   `max_tokens`, at the pinned model's prices): the task's per-call cap (its pinned model's
   worst case at its bounds, `profiles.cap_per_call`), and the day's spend so far plus this
   call against the installation's day cap. A refusal names both operands.

Then the adapter sends it; a refusal, a `max_tokens` stop, an answer that is not the schema,
and each provider failure are each their own kind, never a parser's crash (13.5).
"""
import datetime
import json
import logging

from pydantic import ValidationError

from modules.ai import anthropic_adapter, calls, profiles, prompts, schemas

log = logging.getLogger(__name__)

#: Characters per token the input estimate assumes: under English's usual 4, so the worst
#: case is over, never under. The recorded usage replaces it once the call is answered.
CHARS_PER_TOKEN = 3.0

#: The default the schema seeds (modules/settings_schema.py): a day's spend for the
#: installation. PHASE8_PLAN 7 caps a month at $50 globally; $1.50 a day is under that. A
#: call's cap is its task's (`profiles.cap_per_call`).
DEFAULT_CAP_PER_DAY = 1.50


def hosted_allowed() -> dict:
    """``{"allowed": bool, "why": str, "by", "at", "reason"}`` from the admin's setting."""
    from modules.settings_schema import get_setting
    got = get_setting("ai_hosted") or {}
    if not isinstance(got, dict) or not got.get("reason") or not got.get("by"):
        return {"allowed": False, "why": "hosted AI is off: an admin allows it in Settings, "
                "with a recorded reason (PHASE8_PLAN 15.8)", "by": "", "at": "", "reason": ""}
    # `by` and `reason` are there (the guard above); only `at` may be absent.
    return {"allowed": True, "why": "", "by": got["by"], "at": got.get("at", ""),
            "reason": got["reason"]}


def caps(feature: str) -> dict:
    """The task's per-call cap (derived from its pin) and the installation's day cap (its
    literal key; a value that is not a number reads as its default)."""
    from modules.settings_schema import get_setting

    try:
        # The schema declares the key's default, so `get_setting` never falls past it.
        per_day = float(get_setting("ai_cap_usd_per_day"))
    except (TypeError, ValueError):
        per_day = DEFAULT_CAP_PER_DAY
    return {"per_call": profiles.cap_per_call(feature), "per_day": per_day}


def _api_key() -> str:
    from modules.secrets_store import get_secret
    return get_secret("anthropic_api_key") or ""


def _delimited(tag: str, parts: dict) -> str:
    return "\n\n".join(f'<{tag} name="{name}">\n{parts[name]}\n</{tag}>' for name in sorted(parts))


def build_request(prompt: dict, schema_model, parts: dict, pin: dict, context: dict = None,
                  profile: dict = None) -> dict:
    """The Messages API body. **The stable prefix, cached** (the operator, 2026-10-25): the
    prompt, then the *context* (what every call of a feature shares, as 8.1's builder
    vocabulary), as system blocks, the last marked `cache_control` (the 5-minute TTL). **The
    call's own parts, uncached**: each as data, delimited by its name, in one user turn (a
    question, an evidence pack). The answer's schema in `output_config.format`. Nothing
    volatile (a time, an id) is ever in the system blocks: any byte that moves there misses
    the cache for everything after it. **The request's settings are the task's *pin*'s**
    (its file, `profiles.load_pins`): its model and `max_tokens`; its `thinking` off sent in
    the model's own form (*profile*'s `thinking_off`), adaptive sending none; its
    `temperature` sent when it names one, null sending none. `ask` checks the pin's settings
    against the model before this is built."""
    system = [{"type": "text", "text": prompt["text"]}]
    if context:
        system.append({"type": "text", "text": _delimited("context", context)})
    system[-1]["cache_control"] = {"type": "ephemeral"}
    body = {
        "model": pin["model"],
        "max_tokens": int(pin["max_tokens"]),
        "system": system,
        "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],
        "output_config": {"format": {"type": "json_schema",
                                     "schema": schemas.schema_for(schema_model)}},
    }
    if pin.get("thinking") == "off":
        body["thinking"] = dict((profile or {})["thinking_off"])
    if pin.get("temperature") is not None:
        body["temperature"] = pin["temperature"]
    return body


def prompt_tokens(body: dict) -> int:
    """The masked request's prompt, in tokens, estimated from its size (an over-estimate)."""
    return int(len(json.dumps(body, ensure_ascii=False)) / CHARS_PER_TOKEN) + 1


def worst_case_usd(model: str, body: dict) -> float:
    """The call's cost if nothing is read from the cache: the whole input estimated from the
    masked request's size and priced as a cache write (the dearer of the two), plus all of
    `max_tokens` (every body `build_request` makes carries it)."""
    return profiles.cost_usd(model, 0, int(body["max_tokens"]),
                             cache_write_tokens=prompt_tokens(body))


def _text_of(reply_body: dict) -> str:
    return "".join(b.get("text", "") for b in reply_body.get("content") or []
                   if b.get("type") == "text")


def ask(feature: str, prompt: tuple, schema_model, parts: dict, *, actor: str,
        context: dict = None, send=None, today: str = None, thinking: str = None,
        subject: dict = None) -> dict:
    """One schema-bound call of the task *feature* (the module's docstring has the order): its
    model and bounds are its pin in `profiles.TASKS`, never an argument. *context* is the
    stable prefix every call of the task shares, cached; *parts* the call's own data,
    uncached. *send* replaces the adapter (tests); *today* the UTC day the caps count.
    *thinking* (one of `profiles.THINKING`) replaces the task's for this call alone, as a
    measurement of both asks; by default the task's pin, "adaptive" when it names none. The
    row records which was sent. *subject* is what the call is about, written with it (15.14:
    the device, the alert or the query, ``{"kind", "id", "devices"}``), on every row, sent or
    refused."""
    call_id = calls.new_id()
    pin = profiles.TASKS.get(feature) or {}
    model = pin.get("model", "")
    # No verdict here: every path that records the row sets its own (a refusal's kind,
    # `_answered`'s, or "ok").
    row = {"id": call_id, "feature": feature, "actor": actor, "model": model,
           "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,
           "subject": dict(subject or {})}

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
    if not pin:
        return refuse("unknown_task", f"{feature!r} is not a task profiles.TASKS pins; known: "
                      f"{', '.join(sorted(profiles.TASKS))}")
    max_tokens = int(pin["max_tokens"])
    try:
        profile = profiles.profile(model)
    except KeyError as exc:
        return refuse("unknown_model", str(exc))
    if profile["provider"] != profiles.ANTHROPIC:
        return refuse("unknown_model", f"{model} is not served by the Anthropic adapter")
    # The request's settings are the pin file's; a measurement's *thinking* replaces its one.
    asked = dict(pin, thinking=thinking) if thinking is not None else pin
    mode = asked["thinking"]                    # every pin names it (profiles.PIN_KEYS)
    row["thinking"] = mode
    if mode not in profiles.THINKING:
        return refuse("thinking", f"thinking {mode!r} is not one of "
                      f"{', '.join(profiles.THINKING)}; nothing was sent")
    if mode == "off" and not profile.get("thinking_off"):
        return refuse("thinking", f"{model}'s profile names no way to turn thinking off; "
                      "nothing was sent")
    temperature = asked["temperature"]
    if temperature is not None and temperature not in profile.get("temperatures", ()):
        return refuse("temperature", f"the pin's temperature {temperature!r} is not one "
                      f"{model} takes ({profile.get('temperatures') or 'none'}); nothing "
                      "was sent")
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
    body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,
                                               context=context, profile=profile))
    leaked = redact.contains_known_secret(body)
    if leaked:
        return refuse("unmasked_secret", "a stored secret is still in the request after "
                      f"masking ({', '.join(leaked)}); nothing was sent")
    row["request"] = body

    est = prompt_tokens(body)
    if est > pin["max_prompt_tokens"]:
        long_at = profile.get("long_prompt_tokens")
        return refuse("prompt_too_long", f"this prompt is about {est} tokens, over the task's "
                      f"bound of {pin['max_prompt_tokens']}"
                      + (f" ({model} charges every rate at its long tier over {long_at})"
                         if long_at else "") + "; nothing was sent", prompt_tokens=est)
    cap = caps(feature)
    worst = worst_case_usd(model, body)
    if worst > cap["per_call"]:
        return refuse("over_cap", f"this call's worst case ${worst:.4f} is over the "
                      f"{feature} task's per-call cap ${cap['per_call']:.4f}", worst_usd=worst)
    # The UTC day, from a clock asked for UTC by name (never a local time read by default).
    day = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
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
    cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],
                             cache_write_tokens=tokens["cache_creation_input_tokens"],
                             cache_read_tokens=tokens["cache_read_input_tokens"])
    charged = profiles.prices_for(model, tokens["input_tokens"]
                                  + tokens["cache_creation_input_tokens"]
                                  + tokens["cache_read_input_tokens"])
    text = _text_of(reply.body)
    sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,
                latency_s=round(reply.latency_s, 3),
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
        # A ValidationError Pydantic raises always holds an error, each with its loc and msg.
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "the answer"
        return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "
                         f"{first['msg']}")
    out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))
    return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,
            "recorded": out.get("recorded", False)}


def _answered(row, kind, detail):
    out = calls.record(dict(row, verdict=kind, detail=detail))
    return {"ok": False, "error": kind, "detail": detail, "call_id": row["id"],
            "cost_usd": row["cost_usd"], "recorded": out.get("recorded", False)}
