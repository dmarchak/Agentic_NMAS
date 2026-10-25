"""The model profiles and the tasks' pins (PHASE8_PLAN 7, 10.3, 13.2; the operator's sprint
ruling of 2026-10-25: a model is pinned per task, chosen by its recorded cases, not by default).

**Prices** are Anthropic's pricing page's, per million tokens (`PRICES_SOURCE`, read on
`PRICES_AS_OF`): base input, a 5-minute cache write, a cache read (a hit or refresh) and output.
Haiku 5.5 is priced by prompt length: a prompt over 100,000 tokens (all its input, cache reads
and writes included) pays every rate at its long tier, 5x. The card draws this table, and says
so when it is older than `PRICES_STALE_DAYS`.

**Tasks** pin their model, and the bounds their caps derive from: the most a prompt may hold
(`max_prompt_tokens`, always under a model's long tier) and the most an answer may
(`max_tokens`). A task's per-call cap is its pinned model's worst case at those bounds; there is
no model switch at run time. Changing a task's model is an edit here that re-runs the task's
recorded cases (their recorded model must be the pinned one: tests/test_ai_gateway.py). The
rule: a task runs on the cheapest model that meets its floor.
"""
import datetime

#: Each provider's API shape has one adapter (PHASE8_PLAN 10.3); the gateway is neutral.
ANTHROPIC = "anthropic"

PRICES_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICES_AS_OF = "2026-10-25"
PRICES_STALE_DAYS = 90

#: Per million tokens, from PRICES_SOURCE on PRICES_AS_OF (its "Model pricing" table).
MODELS = {
    "claude-haiku-5-5": {
        "provider": ANTHROPIC, "words": "Claude Haiku 5.5",
        "price": {"input": 0.10, "cache_write": 0.125, "cache_read": 0.01, "output": 0.50},
        # "for prompts over 100,000 tokens"
        "long_prompt_tokens": 100_000,
        "long_price": {"input": 0.50, "cache_write": 0.625, "cache_read": 0.05,
                       "output": 2.50},
    },
    "claude-sonnet-5-5": {
        "provider": ANTHROPIC, "words": "Claude Sonnet 5.5",
        # Cache hits at 0.05x the input rate (the page's note 2; C1679).
        "price": {"input": 2.00, "cache_write": 2.50, "cache_read": 0.10, "output": 10.00},
    },
}

#: Each task's pinned model and bounds (the operator's ruling of 2026-10-25). `explain` starts
#: on Sonnet 5.5, then its cases run on Haiku 5.5, pinned there if it meets its 90% floor.
TASKS = {
    "connection_check": {"model": "claude-haiku-5-5", "max_prompt_tokens": 2_000,
                         "max_tokens": 64, "words": "Test connection"},
    # Measured 2026-10-25 on the lab's captured catalogue: 2,301 to 3,026 tokens (estimated,
    # an over-estimate) for five questions, 20 metrics offered; 8,000 is about 2.6x, and the
    # local tier's context (13.1).
    "nl_query": {"model": "claude-haiku-5-5", "max_prompt_tokens": 8_000,
                 "max_tokens": 1_024, "words": "Ask in words (History › Query)"},
    "explain": {"model": "claude-sonnet-5-5", "max_prompt_tokens": 20_000,
                "max_tokens": 1_024, "words": "Explain an alert (Monitoring › Alerts)"},
    "intent_patch": {"model": "claude-sonnet-5-5", "max_prompt_tokens": 40_000,
                     "max_tokens": 2_048, "words": "An intent change in words"},
}

#: The default only for a profile's own checks; a call always takes its task's pin.
DEFAULT_MODEL = "claude-haiku-5-5"


def profile(model: str) -> dict:
    """The profile of *model*, or KeyError naming the models Mercury knows."""
    try:
        return MODELS[model]
    except KeyError:
        raise KeyError(f"no model profile for {model!r}; known: {', '.join(sorted(MODELS))}"
                       ) from None


def task(name: str) -> dict:
    """The task's pin, or KeyError naming the tasks Mercury knows."""
    try:
        return TASKS[name]
    except KeyError:
        raise KeyError(f"no task {name!r}; known: {', '.join(sorted(TASKS))}") from None


def prices_for(model: str, prompt_tokens: int) -> dict:
    """The rates a call of *model* with *prompt_tokens* in all is charged at: its long tier's
    over the threshold, as Anthropic bills it (the whole call, not the excess)."""
    p = profile(model)
    long_at = p.get("long_prompt_tokens")
    tier = "long" if long_at and prompt_tokens > long_at else "base"
    rates = p["long_price"] if tier == "long" else p["price"]
    return dict(rates, tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)


def cost_usd(model: str, input_tokens: int, output_tokens: int, *,
             cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> float:
    """What a call costs at *model*'s rates for its prompt's length (`prices_for`)."""
    rates = prices_for(model, input_tokens + cache_write_tokens + cache_read_tokens)
    return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"]
            + cache_read_tokens * rates["cache_read"]
            + output_tokens * rates["output"]) / 1_000_000


def cap_per_call(name: str) -> float:
    """A task's per-call cap: its pinned model's worst case at its bounds (every prompt token
    a cache write, the dearest input, and all of max_tokens)."""
    t = task(name)
    return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])


def cases_off_pin(root: str) -> list:
    """Every recorded case (``<root>/<task>/*.json``, each naming the ``model`` it was
    recorded on) whose model is not its task's pin, as ``(path, recorded, pinned)``: a pin
    changed is a task whose cases must be recorded again (the operator, 2026-10-25). A case
    of a task no pin names is listed with ``pinned`` empty."""
    import json
    import os

    out = []
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        pinned = (TASKS.get(name) or {}).get("model", "")
        for case in sorted(f for f in os.listdir(folder) if f.endswith(".json")):
            path = os.path.join(folder, case)
            # Read as bytes: JSON's own rule finds the encoding (RFC 8259, UTF-8), so no
            # encoding is named whose spelling could change and mean the same.
            with open(path, "rb") as fh:
                recorded = (json.load(fh) or {}).get("model", "")
            if recorded != pinned:
                out.append((path, recorded, pinned))
    return out


def prices_age_days(today: str = None) -> int:
    day = (datetime.date.fromisoformat(today) if today
           else datetime.datetime.now(datetime.timezone.utc).date())
    return (day - datetime.date.fromisoformat(PRICES_AS_OF)).days


def table(today: str = None) -> dict:
    """What the AI card draws, read-only: each task → its model → the rates its cap uses →
    the cap; the prices' page, date and whether they are stale."""
    rows = []
    for name in sorted(TASKS):
        t = TASKS[name]
        p = profile(t["model"])
        rows.append({"task": name, "words": t["words"], "model": t["model"],
                     "model_words": p["words"], "price": p["price"],
                     "long_prompt_tokens": p.get("long_prompt_tokens"),
                     "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],
                     "cap_usd": cap_per_call(name)})
    age = prices_age_days(today)
    return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,
            "stale": age > PRICES_STALE_DAYS, "stale_days": PRICES_STALE_DAYS}
