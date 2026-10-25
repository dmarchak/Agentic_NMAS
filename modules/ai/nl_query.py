"""Ask in words (PHASE8_PLAN feature 1, 8.1; AI_ANTHROPIC_PLAN F1): a sentence becomes History ›
Query's metrics builder's own choices, never a query nobody can see.

The model only chooses: a metric from those offered, the builder's operations, filters and
range, in a strict schema (`MetricsChoices`). Everything else is Mercury's, deterministic:

- **What is offered** (`retrieve`): the metrics whose name or help shares a word with the
  question, at most `OFFERED`, never the whole catalogue (F1: "about 2K tokens, never the whole
  catalogue"); the roles the network's devices carry; and the devices the question names that
  the inventory holds. A question that matches no metric is answered without a call.
- **The cached prefix:** the prompt and the builder's vocabulary (`vocabulary`), the same bytes
  call after call; the call's own data (the question and what was offered) rides in the user
  turn. Prometheus's help text and label values are data a device or an exporter wrote, so
  they are offered as data, never instructions (13.2's red-team cases).
- **The read-back:** the answer becomes the builder's address (`values`), and the builder's own
  `view` reads it as it reads a person's, checking the metric is held, its labels, the
  operations; a metric not offered or a device the inventory does not hold is refused or left
  out, and said. Then one time-limited test run (`TEST_WAIT` s, Prometheus's `count` of the
  query at the range's end) shows the query parses and how many series it answers.

The person sees the builder filled, the query as the builder forms it, and presses Ask
themselves: nothing runs as an answer until they do.
"""
import logging
import re
from enum import Enum

from modules.ai import gateway
from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

FEATURE = "nl_query"
PROMPT = ("nl_metrics", 1)
#: The operation's steps, named on its manual page (docs/manual/how-it-works/ask-in-words.md).
STEPS = (
    ("offer", "the metrics sharing a word with the question, never the whole catalogue"),
    ("ask", "one recorded, capped call through the AI gateway, as the person who asked"),
    ("read_back", "the answer read back by the builder, as it reads a person's choices"),
    ("test_run", "one time-limited count of the query's series"),
    ("fill", "the builder drawn filled; nothing runs until the person presses Ask"),
)
#: At most this many metrics are offered for one question.
OFFERED = 20
#: The test run's bound, seconds: a count at one instant answers in well under a second on the
#: lab's Prometheus; 10 s is the bound for a slow store, and a run past it says so.
TEST_WAIT = 10.0
QUESTION_MAX = 300
#: A metric's help is offered to this many characters, one line (an exporter writes it, so its
#: length is not Mercury's: the bound keeps the prompt under its task's).
HELP_MAX = 200

#: Words that say nothing about which metric is meant.
_STOP = frozenset((
    "the and for per with what which how many much show over last from that this are was were "
    "has have each all any not its their there into than then them they top day days hour hours "
    "week weeks month months minute minutes year today now ago since between during most least "
    "highest lowest more less give list tell want see does did doing been being who where when "
    "why can could would should will just only also very some every "
    # The builder's own choices (a grouping, a device, a role), never a metric's words.
    "device devices router routers switch switches node nodes host hosts role roles network "
    "fleet").split())
#: The network's words for what SNMP's names call otherwise (generic vocabulary, no network).
_ALSO = {"traffic": ("octets",), "bandwidth": ("octets",), "throughput": ("octets",),
         "bytes": ("octets",), "bits": ("octets",), "processor": ("cpu",),
         "input": ("in",), "inbound": ("in",), "incoming": ("in",), "received": ("in",),
         "output": ("out",), "outbound": ("out",), "outgoing": ("out",), "sent": ("out",),
         "interface": ("if",), "interfaces": ("if",), "port": ("if",), "ports": ("if",),
         "memory": ("mem", "memory"), "ram": ("mem", "memory"), "down": ("oper", "status"),
         "status": ("oper", "status"), "state": ("state", "status"), "drops": ("discards",),
         "dropped": ("discards",), "temperature": ("temp", "temperature"),
         "neighbour": ("peer",), "neighbor": ("peer",), "uptime": ("uptime",)}
_SPLIT = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


class OpKind(str, Enum):
    """The builder's operations (history_promq: RANGE_OPS, UNIT_OPS, AGGS, COMPARE)."""
    rate = "rate"
    increase = "increase"
    bits = "bits"
    per_min = "per_min"
    sum = "sum"
    avg = "avg"
    min = "min"
    max = "max"
    count = "count"
    ne = "ne"
    eq = "eq"
    gt = "gt"
    lt = "lt"


class FilterOp(str, Enum):
    exactly = "="
    not_ = "!="
    matches = "=~"
    not_matches = "!~"


class Range(str, Enum):
    one_hour = "1h"
    one_day = "24h"
    seven_days = "7d"
    thirty_days = "30d"
    ninety_days = "90d"


class Top(str, Enum):
    none = "none"
    five = "5"
    ten = "10"


class Filter(StrictModel):
    label: str
    op: FilterOp
    value: str


class Operation(StrictModel):
    """One step: *kind*, and its argument (a rate's window, a group's label or none, a
    comparison's number; empty for bits and per_min)."""
    kind: OpKind
    arg: str


@register("nl_metrics", 1)
class MetricsChoices(StrictModel):
    """The builder's choices for one question, or why the builder cannot answer it."""
    answerable: bool
    why_not: str
    metric: str
    devices: list[str]
    role: str
    interfaces: list[str]
    filters: list[Filter]
    operations: list[Operation]
    top: Top
    range: Range


def _words(text: str) -> set:
    return {w.lower() for w in _SPLIT.findall(text or "")}


def terms(question: str) -> dict:
    """The question's words that can name a metric, each with the network's other words for
    it: ``{word: {word, ...}}``."""
    out = {}
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]*", question or ""):
        w = w.lower()
        if len(w) < 3 or w in _STOP:
            continue
        out[w] = {w, *_ALSO.get(w, ())}
    return out


def _stem(w: str) -> str:
    return w[:max(4, len(w) - 2)] if len(w) > 4 else w


def _matches(forms: set, words: set) -> bool:
    # A word and its plural or its stem ("errors" is "error", "discard" is "discards"); a
    # short word ("in", "if") only as itself.
    return any(w == t or (len(w) >= 4 and len(t) >= 4 and
                          (w.startswith(_stem(t)) or t.startswith(_stem(w))))
               for t in forms for w in words)


def retrieve(question: str, cat: dict) -> list:
    """The metrics to offer for *question*: ``[(name, kind, unit, help)]``. Each of the
    question's words counts 2 when the name holds it and 1 when only the help does; the best
    first, a shorter name before a longer (the YANG paths hold many words), then by name; at
    most `OFFERED`."""
    from modules import history_promq as pq

    want = terms(question)
    if not want:
        return []
    meta, scored = cat.get("meta") or {}, []
    for name in cat.get("names") or []:
        help_ = pq.help_of(name, meta)
        in_name, in_help = _words(name), _words(help_)
        score = sum(2 if _matches(f, in_name) else 1 if _matches(f, in_help) else 0
                    for f in want.values())
        if score:
            # As the builder's own search orders: a metric whose type Prometheus states, and
            # one with help, before one without (search, history_promq).
            scored.append((-score, pq.kind_of(name, meta) == "unknown", not help_,
                           len(in_name), name, help_))
    scored.sort()
    return [(name, pq.kind_of(name, meta), pq.unit_of(name, meta)[0], help_)
            for *_k, name, help_ in scored[:OFFERED]]


def vocabulary() -> str:
    """The builder's vocabulary, the same bytes on every call (the cached prefix)."""
    from modules import history_promq as pq

    lines = ["Ranges (range): " + ", ".join(f"{k} = {w}" for k, (w, _s) in pq.RANGES.items()),
             "Operations, in order, at most %d:" % pq.MAX_OPS]
    lines += [f"- {k}: {w}; its argument is a window, one of "
              + ", ".join(pq.WINDOWS) + "; it applies to a counter, and only first"
              for k, w in pq.RANGE_OPS.items()]
    lines += [f"- {k}: {w}; no argument" for k, w in pq.UNIT_OPS.items()]
    lines += [f"- {k}: groups the series ({pq.AGG_WORDS[k][0]} one line per label); its "
              "argument is the label to keep, or empty for one line" for k in pq.AGGS]
    lines += [f"- {k}: keeps the series {w} a number; its argument is the number"
              for k, (_op, w) in pq.COMPARE.items()]
    lines += ["Filters (filters), at most %d: a label, one of " % pq.MAX_FILTERS
              + ", ".join(f"{op} ({w})" for op, w in pq.FILTER_OPS.items()) + ", a value",
              f"Labels Mercury knows: {pq.DEVICE_LABEL} (devices), {pq.ROLE_LABEL} (role), "
              + " or ".join(pq.INTERFACE_LABELS) + " (interfaces)",
              "Top (top): none, or " + " or ".join(pq.TOPS) + " highest series at each step"]
    return "\n".join(lines)


def _inventory(list_name: str) -> list:
    from modules.device import load_saved_devices
    from modules.nsot import listref
    try:
        return load_saved_devices(listref.resolve(list_name).csv_path)
    except Exception as exc:                          # noqa: BLE001
        log.warning("nl_query: %s's inventory could not be read: %s", list_name, exc)
        return []


def named_devices(question: str, rows: list) -> list:
    """The inventory's devices the question names, each as a whole word, in its case."""
    said = {w.lower() for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*", question or "")}
    return sorted(d["hostname"] for d in rows
                  if d.get("hostname") and d["hostname"].lower() in said)


def parts(question: str, offered: list, devices: list, roles: list) -> dict:
    """The call's own data, in the user turn."""
    return {
        "question": question,
        "metrics": "\n".join(f"{n} | {k} | {u or 'no unit'} | {' '.join(h.split())[:HELP_MAX]}"
                             for n, k, u, h in offered),
        "devices_named": "\n".join(devices) or "(none)",
        "roles": "\n".join(roles) or "(none)",
    }


def values(c: MetricsChoices) -> dict:
    """The builder's address for the choices (history_promq's own tokens)."""
    from modules import history_promq as pq

    return {"m": c.metric, "dev": list(c.devices), "role": c.role, "if": list(c.interfaces),
            "f": [pq.filter_token(f.label, f.op.value, f.value) for f in c.filters],
            "op": [pq.op_token(o.kind.value, o.arg) for o in c.operations],
            "top": "" if c.top is Top.none else c.top.value, "range": c.range.value}


def metrics(list_name: str, question: str, *, actor: str, send=None, client=None,
            now: float = None, today: str = None) -> dict:
    """``{"ok", "error", "detail", "values", "view", "series", "call_id", "cost_usd",
    "offered"}``: the builder filled from *question*, read back by the builder, and its
    test run; or a refusal naming why, with nothing filled."""
    from modules import history_promq as pq

    question = " ".join((question or "").split())
    if not question:
        return {"ok": False, "error": "empty", "detail": "type a question first"}
    if len(question) > QUESTION_MAX:
        return {"ok": False, "error": "too_long",
                "detail": f"the question is {len(question)} characters; at most "
                          f"{QUESTION_MAX} are taken"}
    now = pq._now() if now is None else now
    probe = client or pq._client(list_name, 15.0)     # the builder's own read bound
    if not probe.is_configured():
        return {"ok": False, "error": "not_configured",
                "detail": "no metrics store is configured for this network (its Prometheus "
                          "card in Settings)"}
    rng = pq.window(dict(pq.DEFAULTS), now)
    cat = pq.catalogue(list_name, probe, rng, now)
    if cat["state"] != "ok":
        return {"ok": False, "error": "catalogue", "detail": cat["error"]}
    offered = retrieve(question, cat)
    if not offered:
        return {"ok": False, "error": "no_match", "offered": [],
                "detail": f"no metric of the {len(cat['names'])} Prometheus holds shares a "
                          "word with the question; nothing was sent (try the metric's own "
                          "words, or search the builder's Metric box)"}
    rows = _inventory(list_name)
    roles = sorted({d["role"] for d in rows if d.get("role")})
    got = gateway.ask(FEATURE, PROMPT, MetricsChoices,
                      parts(question, offered, named_devices(question, rows), roles),
                      actor=actor, context={"builder": vocabulary()}, send=send, today=today)
    if not got["ok"]:
        return dict(got, offered=[o[0] for o in offered])
    c, base = got["output"], {"call_id": got["call_id"], "cost_usd": got["cost_usd"],
                              "offered": [o[0] for o in offered]}
    if not c.answerable:
        return dict(base, ok=False, error="unanswerable",
                    detail=f"the builder cannot answer this: {c.why_not[:200]}")
    names = {o[0] for o in offered}
    if c.metric not in names:
        return dict(base, ok=False, error="not_offered",
                    detail=f"the answer chose {c.metric[:80]!r}, which was not one of the "
                           f"{len(names)} metrics offered; nothing was filled")
    v, said = values(c), []
    held = {d["hostname"] for d in rows if d.get("hostname")}
    unknown = [d for d in v["dev"] if d not in held]
    if unknown:
        said.append(f"left out {', '.join(unknown[:3])}: not a device of {list_name}")
        v["dev"] = [d for d in v["dev"] if d in held]
    if v["role"] and v["role"] not in roles:
        said.append(f"left out the role {v['role'][:40]!r}: no device of {list_name} has it")
        v["role"] = ""
    view = pq.view(list_name, v, now=now, client=probe)
    out = dict(base, ok=True, error="", values=v, view=view,
               errors=said + list(view["errors"]), series=None, test="")
    built = view.get("built")
    if built and view["state"] == "ok":
        n = pq.instant_count(client or pq._client(list_name, TEST_WAIT), built["query"],
                             view["range"]["end"])
        out["series"] = n
        out["test"] = (f"Prometheus did not answer the test run within {TEST_WAIT:.0f} s, or "
                       "refused it" if n is None else
                       f"the test run answers {n} series now")
    return out
