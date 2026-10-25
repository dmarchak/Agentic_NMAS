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


#: Prompt caching's prices, as multiples of the input rate (the API reference's prompt-caching
#: page, read 2026-10-25): a write to the 5-minute cache 1.25x, a read about 0.1x on Haiku 5.5
#: and Sonnet 5.5. The cache's 5-minute TTL is the only one Mercury asks for (the operator,
#: 2026-10-25). A prefix under the model's minimum (512 tokens on Haiku 5.5) is not cached at
#: all, silently: the record's cache counts show it.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10


def cost_usd(model: str, input_tokens: int, output_tokens: int, *,
             cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> float:
    """What a call of *model* costs: uncached input at the input rate, a cache write at 1.25x
    it, a cache read at 0.1x, output at the output rate. A prompt (all three inputs together)
    over the long threshold is priced whole at the long rate, as Anthropic bills it."""
    p = profile(model)
    prompt = input_tokens + cache_write_tokens + cache_read_tokens
    long_at = p.get("long_prompt_tokens")
    if long_at and prompt > long_at:
        rate_in, rate_out = p["long_usd_per_mtok_in"], p["long_usd_per_mtok_out"]
    else:
        rate_in, rate_out = p["usd_per_mtok_in"], p["usd_per_mtok_out"]
    return (input_tokens * rate_in
            + cache_write_tokens * rate_in * CACHE_WRITE_MULTIPLIER
            + cache_read_tokens * rate_in * CACHE_READ_MULTIPLIER
            + output_tokens * rate_out) / 1_000_000
