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
no model switch at run time. Each task's pin is a file, `pins/<task>.json`, with its request
settings (thinking, temperature) beside its bounds: tuning one is an edit to that file, read by
the gateway's unchanged code. Changing a task's model re-runs the task's recorded cases (their
recorded model must be the pinned one: tests/test_ai_gateway.py). The rule: a task runs on the
cheapest model that meets its floor.
"""
import datetime
import json
import os

#: Each provider's API shape has one adapter (PHASE8_PLAN 10.3); the gateway is neutral.
ANTHROPIC = "anthropic"

PRICES_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICES_AS_OF = "2026-10-25"
PRICES_STALE_DAYS = 90

#: Per million tokens, from PRICES_SOURCE on PRICES_AS_OF (its "Model pricing" table).
MODELS = {
    "claude-haiku-5-5": {
        "provider": ANTHROPIC, "words": "Claude Haiku 5.5",
        # Thinking off, as this model accepts it: `disabled`, at effort low, medium or high
        # (its default is medium, which Mercury never changes). Its temperature cannot be
        # lowered: any value but 1, the default, is a 400, thinking on or off (the claude-api
        # reference's Haiku 5.5 migration, breaking change 2; read 2026-10-25).
        "thinking_off": {"type": "disabled"},
        # The temperatures a pin may send: only the default (same reference, read 2026-10-25).
        "temperatures": [1],
        "price": {"input": 0.10, "cache_write": 0.125, "cache_read": 0.01, "output": 0.50},
        # "for prompts over 100,000 tokens"
        "long_prompt_tokens": 100_000,
        "long_price": {"input": 0.50, "cache_write": 0.625, "cache_read": 0.05,
                       "output": 2.50},
    },
    "claude-sonnet-5-5": {
        "provider": ANTHROPIC, "words": "Claude Sonnet 5.5",
        # This model refuses `disabled`; its lowest setting is `between_tools` (the same
        # reference's error codes, read 2026-10-25).
        "thinking_off": {"type": "between_tools"},
        # Only the default temperature (its migration checklist: remove temperature, top_p
        # and top_k; read 2026-10-25).
        "temperatures": [1],
        # Cache hits at 0.05x the input rate (the page's note 2; C1679).
        "price": {"input": 2.00, "cache_write": 2.50, "cache_read": 0.10, "output": 10.00},
    },
}

#: A task's thinking: "adaptive", the model's own default (no `thinking` sent), or "off", as
#: its model's profile says (`thinking_off`). The batched gateway change (the operator,
#: 2026-10-25): per task, and a measurement may ask either for one run (`gateway.ask`).
THINKING = ("adaptive", "off")

#: Each task's pin is its own file, `pins/<task>.json` (the operator, 2026-10-25: a task's
#: request settings are read from its pin file, so tuning one is a change to the file, never
#: to the tier's code). Its keys, exactly: the model and the bounds, and the request's own
#: settings (`thinking`, one of THINKING; `temperature`, null for the model's default or one
#: its profile's `temperatures` holds), and `why`, each setting's reason in words.
PIN_KEYS = ("words", "model", "max_prompt_tokens", "max_tokens", "thinking", "temperature",
            "why")
PINS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pins")


def load_pins(folder: str = PINS) -> dict:
    """Every task's pin from *folder*, ``{task: pin}``, a task named by its file. A file whose
    keys are not exactly `PIN_KEYS`, or that is not JSON, is refused at import, naming it: no
    task runs on a pin half read."""
    out = {}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as fh:
            pin = json.load(fh)
        if sorted(pin) != sorted(PIN_KEYS):
            raise ValueError(f"pin {name}: keys {sorted(pin)}, expected {sorted(PIN_KEYS)}")
        out[name[:-len(".json")]] = pin
    return out


#: Each task's pinned model, bounds and request settings (the operator's ruling of
#: 2026-10-25), from its pin file.
TASKS = load_pins()

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
