"""The model profiles and the tasks' pins (PHASE8_PLAN 7, 10.3, 13.2; the operator's sprint
ruling of 2026-10-25: a model is pinned per task, chosen by its recorded cases, not by default).

**Prices** are Anthropic's pricing page's, per million tokens (`PRICES_SOURCE`, read on
`PRICES_AS_OF`): base input, a 5-minute cache write, a cache read (a hit or refresh) and output.
Haiku 5.5 is priced by prompt length: a prompt over 100,000 tokens (all its input, cache reads
and writes included) pays every rate at its long tier, 5x. The card draws this table, and says
so when it is older than `PRICES_STALE_DAYS`.

**Tasks** pin their model; a person's press may choose another only where its task offers a
choice (`CHOOSABLE`, the operator, 2026-11-28: "add a model selector to the chat"; the
assistant alone), and a background call always runs on its pin. Each task's pin is a file,
`pins/<task>.json`, with its request settings (thinking, temperature). **No size bound of
Mercury's own** (the operator, 2026-11-16: "remove every AI token/size limit Mercury sets
itself. The spending limits ... are the only governor"): a prompt is bounded only by its model's
real context window (`context_window`; the fit cuts only to stay inside it, `prompt_room`), and
an answer's ``max_tokens`` is sized per call by the gateway to what the remaining spend can pay
for, at most the model's maximum (`max_output`). A pin's ``max_prompt_tokens`` is kept in the
file (the pin's keys are exact, `PIN_KEYS`) and enforced by nothing; its ``max_tokens`` is the
stand-in for a task's typical answer until its calls are measured
(`background.typical_output`). Changing a task's model re-runs the task's recorded cases (their
recorded model must be the pinned one: tests/test_ai_gateway.py). The rule: a task runs on the
cheapest model that meets its floor.
"""
import datetime
import json
import os

#: Each provider's API shape has one adapter (PHASE8_PLAN 10.3); the gateway is neutral.
ANTHROPIC = "anthropic"

PRICES_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICES_AS_OF = "2026-10-27"
PRICES_STALE_DAYS = 90

#: Where each model's context window and most output tokens are stated (the operator,
#: 2026-11-16): every model's ``context_window`` and ``max_output_tokens`` below.
LIMITS_SOURCE = "the Claude API reference, cached 2026-11-03"
#: The three models' shared figures, from `LIMITS_SOURCE`: a 1,000,000-token context window and
#: at most 128,000 output tokens a call.
_WINDOW = {"context_window": 1_000_000, "max_output_tokens": 128_000,
           "limits_source": LIMITS_SOURCE}

#: Per million tokens, from PRICES_SOURCE on PRICES_AS_OF (its "Model pricing" table); each
#: model's context window and most output tokens from LIMITS_SOURCE (`_WINDOW`).
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
        **_WINDOW,
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
        **_WINDOW,
    },
    # A measurement ceiling (the operator, 2026-10-27: Opus against Sonnet on Explain), never a
    # product default unless nothing smaller meets the bar (PHASE8_PLAN 15.12). Its prices read
    # from PRICES_SOURCE on 2026-10-27, its row in "Model pricing".
    "claude-opus-5-5": {
        "provider": ANTHROPIC, "words": "Claude Opus 5.5",
        # Thinking is always on: `disabled` is a 400 at every effort, as is a budget; depth is
        # `output_config.effort` (the claude-api reference's curl examples, read 2026-10-27).
        # So no thinking-off form: a pin of "off" on it is refused by the gateway.
        "thinking_off": None,
        # `temperature`, `top_p` and `top_k` are a 400 (its error codes, read 2026-10-27):
        # only the default.
        "temperatures": [1],
        # Cache hits at 0.05x the input rate (the page's note 2).
        "price": {"input": 4.00, "cache_write": 5.00, "cache_read": 0.20, "output": 20.00},
        **_WINDOW,
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


#: The tasks a person may run on a model other than its pin, and the models offered for each,
#: the pin's own first (the operator, 2026-11-28: "add a model selector to the chat"). Only a
#: person's press chooses one (`choice_refusal`); a background call always runs on its pin.
CHOOSABLE = {"assistant": ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")}


def choice_refusal(task_name: str, model: str, person: bool) -> str:
    """Why *model* may not be chosen for a call of *task_name*, or ``""``: the task offers no
    choice, the model is not one it offers (both named), or the call is not a person's."""
    offered = CHOOSABLE.get(task_name)
    if not offered:
        return (f"{task_name!r} offers no model choice; it runs on its pin, "
                f"{task(task_name)['model']}")
    if model not in offered:
        return f"{model!r} is not one of the models {task_name!r} offers ({', '.join(offered)})"
    if not person:
        return "a model is chosen only by a person's press; a background call runs on its pin"
    return ""


def chosen_pin(task_name: str, model: str) -> dict:
    """*task_name*'s pin with *model* in its pin's place. Its thinking is the pin's where the
    model's profile can send it, else ``adaptive`` (a model whose profile names no way to turn
    thinking off, `thinking_off` None: Opus); every other setting the pin's. Assumes
    `choice_refusal` found nothing."""
    pin = task(task_name)
    if model == pin["model"]:
        return pin
    thinking = pin["thinking"]
    if thinking == "off" and not profile(model).get("thinking_off"):
        thinking = "adaptive"
    return dict(pin, model=model, thinking=thinking)


def choices(task_name: str) -> list:
    """The models a person may choose for *task_name*, as a selector draws them: each one's id,
    name, whether it is the pin's, its prices against the pin's (input and output alike,
    `MODELS`'s table: "20x") and its input and output rates, ``[]`` when the task offers none."""
    offered = CHOOSABLE.get(task_name) or ()
    if not offered:
        return []
    base = profile(task(task_name)["model"])["price"]
    out = []
    for m in offered:
        p = profile(m)["price"]
        times = max(p["input"] / base["input"], p["output"] / base["output"])
        out.append({"model": m, "words": profile(m)["words"],
                    "pinned": m == task(task_name)["model"],
                    "times": round(times),
                    "price": {"input": p["input"], "output": p["output"]}})
    return out


def context_window(model: str) -> int:
    """*model*'s context window in tokens (`LIMITS_SOURCE`): the prompt plus a call's
    ``max_tokens`` must fit inside it."""
    return int(profile(model)["context_window"])


def max_output(model: str) -> int:
    """The most output tokens one call of *model* may ask for (`LIMITS_SOURCE`)."""
    return int(profile(model)["max_output_tokens"])


def prompt_room(name: str) -> int:
    """The most a task's prompt may hold for a caller's fit, in tokens: its model's context
    window less the model's most output tokens, so a prompt fitted to it always leaves room for
    the largest answer the caps could pay for (872,000 for every model today). The only size
    bound a fit cuts to (the operator, 2026-11-16); the gateway's own check is the window
    itself (`gateway._prepared`)."""
    model = task(name)["model"]
    return context_window(model) - max_output(model)


def unmeasured_cost(name: str) -> float:
    """A task's stand-in cost of one call while none is measured: its pin's old bounds priced as
    the gateway prices a prompt (every prompt token a cache write) plus the pin's ``max_tokens``
    of answer. Said as not measured wherever it is drawn (`background.measured_cost`)."""
    t = task(name)
    return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])


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


# ── The batch rate (the operator's decision of 2026-10-29, PHASE8_PLAN 15.12: evaluation rounds,
#    never a live feature, go through the provider's Message Batches API) ────────────────────

#: Where the batch rate is stated, and when it was read: "every batched request is charged at
#: 50% of standard prices" (e.g. Sonnet 5.5 at $1 in and $5 out a million tokens); prompt
#: caching's multipliers stack with it.
BATCH_SOURCE = "https://platform.claude.com/docs/en/build-with-claude/batch-processing"
BATCH_AS_OF = "2026-10-29"
#: Every rate a batched request is charged at, as a share of its standard rate.
BATCH_MULTIPLIER = 0.5
#: A 1-hour cache write as a multiple of the base input rate (the 5-minute write is 1.25x,
#: `price["cache_write"]`): the claude-api reference's prompt caching, "Economics" ("cache
#: writes cost 1.25x for 5-minute TTL, 2x for 1-hour TTL"), read 2026-10-29; its live page is
#: `CACHE_SOURCE`, not fetched for this. A batched request is cached with the 1-hour TTL, as
#: the batch page recommends.
CACHE_WRITE_1H_MULTIPLIER = 2.0
CACHE_SOURCE = "https://platform.claude.com/docs/en/build-with-claude/prompt-caching"


def batch_prices_for(model: str, prompt_tokens: int) -> dict:
    """The rates a batched request of *model* with *prompt_tokens* in all is charged at: the
    standard rates for its prompt's length (`prices_for`, the long tier included), plus the
    1-hour cache write (`CACHE_WRITE_1H_MULTIPLIER` times the input rate), each at the batch
    rate (`BATCH_MULTIPLIER`); dated, its sources named."""
    rates = prices_for(model, prompt_tokens)
    out = {k: rates[k] * BATCH_MULTIPLIER for k in ("input", "cache_write", "cache_read",
                                                    "output")}
    out["cache_write_1h"] = rates["input"] * CACHE_WRITE_1H_MULTIPLIER * BATCH_MULTIPLIER
    return dict(out, tier=rates["tier"], as_of=rates["as_of"], source=rates["source"],
                batch={"multiplier": BATCH_MULTIPLIER, "as_of": BATCH_AS_OF,
                       "source": BATCH_SOURCE, "cache_source": CACHE_SOURCE})


def batch_cost_usd(model: str, input_tokens: int, output_tokens: int, *,
                   cache_write_tokens: int = 0, cache_write_1h_tokens: int = 0,
                   cache_read_tokens: int = 0) -> float:
    """What a batched request costs at *model*'s batch rates for its prompt's length
    (`batch_prices_for`): *cache_write_tokens* written with the 5-minute TTL,
    *cache_write_1h_tokens* with the 1-hour."""
    rates = batch_prices_for(model, input_tokens + cache_write_tokens + cache_write_1h_tokens
                             + cache_read_tokens)
    return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"]
            + cache_write_1h_tokens * rates["cache_write_1h"]
            + cache_read_tokens * rates["cache_read"]
            + output_tokens * rates["output"]) / 1_000_000


#: What `cap_per_call`'s figure is, in a person's words (the operator, 2026-11-16: "'Cap per
#: call' in Settings becomes the measured typical cost per task, labelled as such").
PER_CALL_LABEL = "typical cost per call (measured)"


def cap_per_call(name: str) -> float:
    """A task's **measured typical cost per call** (no longer a cap: the spending limits are the
    only governor, and each call's ``max_tokens`` is sized by the gateway to what they leave):
    the mean cost of its sent calls over the cost window (`background.measured_cost`), or, with
    none measured, its stand-in (`unmeasured_cost`), said there as not measured. The name is
    kept for its callers; `PER_CALL_LABEL` is how a screen labels it."""
    from modules.ai import background

    return float(background.measured_cost(name)["usd_per_call"])


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
    """What the AI card draws, read-only: each task → its model → its rates → its measured
    typical cost per call (`cap_per_call`, labelled `PER_CALL_LABEL`, with its basis), and the
    model's context window and most output tokens; the prices' page, date and whether they are
    stale."""
    from modules.ai import background

    rows = []
    for name in sorted(TASKS):
        t = TASKS[name]
        p = profile(t["model"])
        cost = background.measured_cost(name)
        rows.append({"task": name, "words": t["words"], "model": t["model"],
                     "model_words": p["words"], "price": p["price"],
                     "long_prompt_tokens": p.get("long_prompt_tokens"),
                     "context_window": p["context_window"],
                     "max_output_tokens": p["max_output_tokens"],
                     "cap_usd": float(cost["usd_per_call"]), "cap_label": PER_CALL_LABEL,
                     "cap_measured": bool(cost["measured"]), "cap_basis": cost["basis"]})
    age = prices_age_days(today)
    return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,
            "stale": age > PRICES_STALE_DAYS, "stale_days": PRICES_STALE_DAYS,
            "limits_source": LIMITS_SOURCE}
