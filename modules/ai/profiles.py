"""The model profiles: which model a feature calls, pinned, and what it costs (PHASE8_PLAN 7,
10.3, 13.2: "the model profile (data)", "the pinned model version").

Data, never code paths: a model change is one edit here and re-runs the whole evaluation
(PHASE8_PLAN 7: "any model change re-runs the full eval suite"). The prices are Anthropic's
first-party rates per million tokens, read 2026-10-25 from the API reference (cached
2026-10-06): Haiku 5.5 $0.10 in and $0.50 out for prompts up to 100,000 tokens, $0.50 and
$2.50 beyond; Sonnet 5.5 $2 and $10. The caps judge a call by its worst case at these prices.
"""

#: Each provider's API shape has one adapter (PHASE8_PLAN 10.3); the gateway is neutral.
ANTHROPIC = "anthropic"

#: The models Mercury may call, by the exact id the provider takes (no date suffix).
MODELS = {
    "claude-haiku-5-5": {"provider": ANTHROPIC, "words": "Claude Haiku 5.5",
                         "usd_per_mtok_in": 0.10, "usd_per_mtok_out": 0.50,
                         "long_prompt_tokens": 100_000,
                         "long_usd_per_mtok_in": 0.50, "long_usd_per_mtok_out": 2.50},
    "claude-sonnet-5-5": {"provider": ANTHROPIC, "words": "Claude Sonnet 5.5",
                          "usd_per_mtok_in": 2.00, "usd_per_mtok_out": 10.00},
}

#: The default (PHASE8_PLAN 7: "Haiku 5.5 by default; Sonnet only where the eval shows the
#: need; Opus never by default").
DEFAULT_MODEL = "claude-haiku-5-5"


def profile(model: str) -> dict:
    """The profile of *model*, or KeyError naming the models Mercury knows."""
    try:
        return MODELS[model]
    except KeyError:
        raise KeyError(f"no model profile for {model!r}; known: {', '.join(sorted(MODELS))}")


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """What a call of *model* with these token counts costs, at its profile's prices (a prompt
    over the long threshold priced whole at the long rate, as Anthropic bills it)."""
    p = profile(model)
    long_at = p.get("long_prompt_tokens")
    if long_at and input_tokens > long_at:
        rate_in, rate_out = p["long_usd_per_mtok_in"], p["long_usd_per_mtok_out"]
    else:
        rate_in, rate_out = p["usd_per_mtok_in"], p["usd_per_mtok_out"]
    return (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000
