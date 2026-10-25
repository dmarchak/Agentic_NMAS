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
import time
from enum import Enum

from modules.ai import gateway
from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

FEATURE = "nl_query"
#: v2 (the operator, 2026-10-25, from the first live run of the recorded cases): an unstated
#: scope is one line per device, never collapsed unprompted. v3 (v2's live run, case 9):
#: things in a state are counted, never maxed. v4 (v3's five runs, the operator): the defaults
#: the runs alternated between, fixed: the 5-minute CPU, the 64-bit counter, a rate over 5m,
#: no group for one named device. v5 (v4's five runs, the operator): a gauge grouped by avg
#: (max for highest or peak), never summed; one interface label, ifName; a rate unless a
#: count is asked for. Earlier versions stay for their record.
PROMPT = ("nl_metrics", 5)
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
         "interface": ("if", "link"), "interfaces": ("if", "link"), "port": ("if",),
         "ports": ("if",), "flap": ("updown",), "flapping": ("updown",),
         "flaps": ("updown",), "adjacency": ("adjchg",), "neighbors": ("adjchg", "peer"),
         "configuration": ("config",), "changed": ("config",),
         "memory": ("mem", "memory"), "ram": ("mem", "memory"),
         "down": ("oper", "status", "updown"),
         "status": ("oper", "status"), "state": ("state", "status"), "drops": ("discards",),
         "dropped": ("discards",), "temperature": ("temp", "temperature"),
         "neighbour": ("peer",), "neighbor": ("peer",), "uptime": ("uptime", "up"),
         "up": ("up",)}
_SPLIT = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


class OpKind(str, Enum):
    """The builder's operations (history_promq: RANGE_OPS, CHANGES_OPS, UNIT_OPS, AGGS,
    COMPARE)."""
    rate = "rate"
    increase = "increase"
    changes = "changes"
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
    #: From `from_utc` to `to_utc` (the builder's From… to…, to the minute, UTC).
    custom = "custom"


class Outcome(str, Enum):
    """What the answer is: the builder's choices; one question back, when the words leave
    the choice to the person (which device, or per device); or a refusal, saying why."""
    answer = "answer"
    ask = "ask"
    refuse = "refuse"


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


# v2 (2026-10-25): the builder's `changes` operation joined OpKind (recorded case 13, the
# operator's ruling); v1's schema is in git's history and in the calls recorded against it.
@register("nl_metrics", 2)
class MetricsChoices(StrictModel):
    """The builder's choices for one question; or the one question that settles what the
    words leave open; or why the builder cannot answer it. (v1 changed in place 2026-10-25,
    before any call was made with it or any case recorded: `answerable` became `outcome`.)"""
    outcome: Outcome
    question: str
    why_not: str
    metric: str
    devices: list[str]
    role: str
    interfaces: list[str]
    filters: list[Filter]
    operations: list[Operation]
    top: Top
    range: Range
    from_utc: str
    to_utc: str


def _words(text: str) -> set:
    return {w.lower() for w in _SPLIT.findall(text or "")}


def terms(question: str) -> dict:
    """The question's words that can name a metric, each with the network's other words for
    it: ``{word: {word, ...}}``."""
    out = {}
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]*", question or ""):
        w = w.lower()
        # A short word counts only when the network's words name it ("up", as in uptime).
        if (len(w) < 3 and w not in _ALSO) or w in _STOP:
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


def retrieve(question: str, cat: dict, devices_carry: set = frozenset()) -> list:
    """The metrics to offer for *question*: ``[(name, kind, unit, help)]``. Each of the
    question's words counts 2 when the name holds it and 1 when only the help does; the best
    first; among equals, a metric the network's devices carry (*devices_carry*: the names
    whose series hold the builder's device label, `device_metrics`) before one they do not
    (the monitoring host's own CPU beside the routers'), then a shorter name before a longer
    (the YANG paths hold many words), then by name; at most `OFFERED`."""
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
            scored.append((-score, name not in devices_carry,
                           pq.kind_of(name, meta) == "unknown", not help_,
                           len(in_name), name, help_))
    scored.sort()
    return [(name, pq.kind_of(name, meta), pq.unit_of(name, meta)[0], help_)
            for *_k, name, help_ in scored[:OFFERED]]


def device_metrics(client, rng: dict, devices=(), label: str = None):
    """The metric names whose series carry the builder's device label over *rng*, or with
    *devices*, one of those values of *label* (the device label unless named: the role label
    for a named role, one short selector however many devices hold it); one read of
    Prometheus's label-values API. None when it cannot be read. Unread, the offer falls back
    to the words alone, said nowhere, because nothing is lost but a tie-break, or a
    narrowing."""
    from modules import history_promq as pq

    label = label or pq.DEVICE_LABEL
    # Each value a literal in the label's regex: escaped for RE2, then for PromQL's string.
    sel = (label + '=~"' + "|".join(re.escape(d).replace("\\", "\\\\")
                                    for d in devices) + '"' if devices
           else label + '!=""')
    names, err = pq._json(client, "api/v1/label/__name__/values",
                          **{"match[]": "{" + sel + "}",
                             "start": str(int(rng["start"])), "end": str(int(rng["end"]))})
    if err:
        log.warning("nl_query: the metrics carrying %s could not be read: %s", sel, err)
        return None
    return {n for n in names or [] if isinstance(n, str)}


def vocabulary() -> str:
    """The builder's vocabulary, the same bytes on every call (the cached prefix)."""
    from modules import history_promq as pq

    lines = ["Ranges (range): " + ", ".join(f"{k} = {w}" for k, (w, _s) in pq.RANGES.items()),
             "Operations, in order, at most %d:" % pq.MAX_OPS]
    lines += [f"- {k}: {w}; its argument is a window, one of "
              + ", ".join(pq.WINDOWS) + "; it applies to a counter, and only first"
              for k, w in pq.RANGE_OPS.items()]
    lines += [f"- {k}: how many times a gauge's value changed in the window before each "
              "point (a state such as an interface's up or down), never by how much; its "
              "argument is a window, one of " + ", ".join(pq.CHANGES_WINDOWS)
              + "; over a whole range, the window is the range's own length ("
              + ", ".join(f"{r} = {pq.changes_window(s)}" for r, (_w, s) in pq.RANGES.items())
              + "); it applies to a gauge, never a counter, and only first"
              for k in pq.CHANGES_OPS]
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


def named_roles(question: str, roles: list) -> list:
    """The network's roles the question names, each as a whole word or its plural ("all
    switches" names the role switch)."""
    said = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", question or "")}
    return sorted(r for r in roles
                  if r and {r.lower(), r.lower() + "s", r.lower() + "es"} & said)


def named_devices(question: str, rows: list) -> list:
    """The inventory's devices the question names, each as a whole word, in its case."""
    said = {w.lower() for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*", question or "")}
    return sorted(d["hostname"] for d in rows
                  if d.get("hostname") and d["hostname"].lower() in said)


def parts(question: str, offered: list, devices: list, roles: list, now: float) -> dict:
    """The call's own data, in the user turn (the time too: it moves every call, so it is
    never in the cached prefix)."""
    return {
        "question": question,
        "now_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(now)),
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
            "top": "" if c.top is Top.none else c.top.value, "range": c.range.value,
            **({"from": c.from_utc, "to": c.to_utc} if c.range is Range.custom else {})}


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
    rows = _inventory(list_name)
    roles = sorted({d["role"] for d in rows if d.get("role")})
    named = named_devices(question, rows)
    by_role = named_roles(question, roles)
    # A question naming devices or roles is offered only what they carry (2026-10-25: recorded
    # case 13, an IOS switch offered the IOS-XE routers' flap counter it has none of; v3's
    # case 11, "all switches" offered the monitoring host's own memory). One read for each
    # kind named; any unreadable, the offer is the whole catalogue's, as before.
    reads = ([device_metrics(probe, rng, named)] if named else []) + \
        ([device_metrics(probe, rng, by_role, label=pq.ROLE_LABEL)] if by_role else [])
    theirs = set().union(*reads) if reads and None not in reads else None
    pool = dict(cat, names=[n for n in cat["names"] if n in theirs]) if theirs is not None \
        else cat
    offered = retrieve(question, pool, device_metrics(probe, rng) or set())
    if not offered:
        scope = named + [f"the {r} role" for r in by_role]
        among = (f"{', '.join(scope)} carr{'ies' if len(scope) == 1 else 'y'}"
                 if theirs is not None else "Prometheus holds")
        # Mercury answers this itself, no model asked and nothing spent (the operator,
        # 2026-10-25, C1700): what it could not match, what to name, and where to start.
        return {"ok": False, "error": "no_match", "offered": [], "by": "mercury",
                "call_id": "", "cost_usd": 0.0,
                "guide": {"unmatched": list(terms(question)), "devices": named,
                          "searched": len(pool["names"]), "among": among},
                "detail": f"no metric of the {len(pool['names'])} {among} shares a "
                          "word with the question; nothing was sent (try the metric's own "
                          "words, or search the builder's Metric box)"}
    got = gateway.ask(FEATURE, PROMPT, MetricsChoices,
                      parts(question, offered, named, roles, now),
                      actor=actor, context={"builder": vocabulary()}, send=send, today=today)
    if not got["ok"]:
        return dict(got, offered=[o[0] for o in offered])
    c, base = got["output"], {"call_id": got["call_id"], "cost_usd": got["cost_usd"],
                              "offered": [o[0] for o in offered],
                              # The model's own answer, as recorded cases keep it.
                              "choices": got["output"].model_dump(mode="json")}
    if c.outcome is Outcome.ask:
        # One question back, never a guess (the operator's cases, 2026-10-25): the person
        # answers it in their words and asks again.
        return dict(base, ok=False, error="ask", clarify=c.question[:200],
                    detail=f"which one is meant: {c.question[:200]}")
    if c.outcome is Outcome.refuse:
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


# ---------------------------------------------------------------------------- the logs half

PROMPT_LOGS = ("nl_logs", 1)
#: At most this many mnemonics are offered for one question.
OFFERED_MNEMONICS = 20


class Severity(str, Enum):
    """At this severity or worse (the logs builder's `sev`; device_logs.SEVERITY's names)."""
    any = "any"
    emergency = "0"
    alert = "1"
    critical = "2"
    error = "3"
    warning = "4"
    notice = "5"
    informational = "6"
    debug = "7"


class Show(str, Enum):
    lines = "lines"
    counts = "counts"


class Every(str, Enum):
    """A count's window (history_logq.WINDOWS)."""
    one_minute = "1m"
    five_minutes = "5m"
    one_hour_window = "1h"
    one_day_window = "1d"


class LogsRange(str, Enum):
    one_hour = "1h"
    one_day = "24h"
    seven_days = "7d"
    thirty_days = "30d"
    custom = "custom"


@register("nl_logs", 1)
class LogsChoices(StrictModel):
    """The logs builder's choices for one question; or the one question that settles what the
    words leave open; or why the builder cannot answer it."""
    outcome: Outcome
    question: str
    why_not: str
    kinds: list[str]
    devices: list[str]
    role: str
    severity: Severity
    mnemonics: list[str]
    contains: str
    excludes: str
    show: Show
    by: str
    every: Every
    range: LogsRange
    from_utc: str
    to_utc: str


def _mnemonic_words(mn: str) -> set:
    return {w.lower() for w in re.split(r"[%_\-]+", mn) if w and not w.isdigit()}


def offer_mnemonics(question: str, seen: list) -> list:
    """The mnemonics to offer: the builder's Start-from chips' and those the logs reader
    counted (*seen*, ``[(mnemonic, n)]``), each sharing a word with the question; the most seen
    first; at most `OFFERED_MNEMONICS`. A question naming none is offered none: severity and
    text answer it."""
    from modules import history_logq as lq

    want = terms(question)
    counted = dict(seen)
    for _k, _t, params in lq.PRESETS:
        for mn in params.get("mn", ()):
            counted.setdefault(mn, 0)
    hits = [(-n, mn) for mn, n in counted.items()
            if any(_matches(f, _mnemonic_words(mn)) for f in want.values())]
    return [mn for _n, mn in sorted(hits)[:OFFERED_MNEMONICS]]


def vocabulary_logs() -> str:
    """The logs builder's vocabulary, the same bytes on every call (the cached prefix)."""
    from modules import history_logq as lq
    from modules.device_logs import SEVERITY

    return "\n".join([
        "Ranges (range): " + ", ".join(f"{k} = {w}" for k, (w, _s) in lq.RANGES.items())
        + ", or custom (from_utc to to_utc, YYYY-MM-DD HH:MM, UTC)",
        "Kinds (kinds): the log streams' job label values offered; empty for every kind",
        "Severity (severity): this severity or worse, any for all: "
        + ", ".join(f"{k} {SEVERITY[k]}" for k in sorted(SEVERITY)),
        "Mnemonics (mnemonics): only those offered, as %FACILITY-SEVERITY-NAME",
        f"Text (contains, excludes): plain text the line holds or does not, at most "
        f"{lq.TEXT_MAX} characters",
        "Show (show): lines (each line, newest first) or counts (lines counted over time)",
        "Counted by (by, for counts): device, mnemonic, or a label offered",
        "Window (every, for counts): " + ", ".join(
            f"{k} = {w}" for k, (w, _s, _d) in lq.WINDOWS.items()),
    ])


def parts_logs(question: str, kinds: list, mns: list, labels: list, devices: list,
               roles: list, now: float) -> dict:
    return {
        "question": question,
        "now_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(now)),
        "kinds": "\n".join(kinds) or "(none)",
        "mnemonics": "\n".join(mns) or "(none)",
        "labels": "\n".join(labels) or "(none)",
        "devices_named": "\n".join(devices) or "(none)",
        "roles": "\n".join(roles) or "(none)",
    }


def values_logs(c: LogsChoices) -> dict:
    """The logs builder's address for the choices (history_logq's own keys)."""
    return {"job": list(c.kinds), "dev": list(c.devices), "role": c.role,
            "sev": "" if c.severity is Severity.any else c.severity.value,
            "mn": list(c.mnemonics), "has": c.contains, "not": c.excludes,
            "show": c.show.value, "by": c.by or "device", "every": c.every.value,
            "range": c.range.value,
            **({"from": c.from_utc, "to": c.to_utc} if c.range is LogsRange.custom else {})}


def logs(list_name: str, question: str, *, actor: str, send=None, client=None,
         now: float = None, today: str = None) -> dict:
    """``{"ok", "error", "detail", "values", "view", "lines", ...}``: the logs builder filled
    from *question*, read back by the builder, and its test run (one count over the range);
    or a refusal, or one question back, with nothing filled."""
    from modules import history_logq as lq

    question = " ".join((question or "").split())
    if not question:
        return {"ok": False, "error": "empty", "detail": "type a question first"}
    if len(question) > QUESTION_MAX:
        return {"ok": False, "error": "too_long",
                "detail": f"the question is {len(question)} characters; at most "
                          f"{QUESTION_MAX} are taken"}
    now = lq._now() if now is None else now
    probe = client or lq._client(list_name, 15.0)
    if not probe.is_configured():
        return {"ok": False, "error": "not_configured",
                "detail": "no log store is configured for this network (its Loki card in "
                          "Settings)"}
    rng = lq.window(dict(lq.DEFAULTS, range="7d"), now)
    disc = lq.discover(list_name, rng["start"], rng["end"], client=probe, now=now)
    if disc["state"] != "ok":
        return {"ok": False, "error": "catalogue", "detail": disc["error"]}
    kinds = list(disc["values"].get("job") or [])
    seen = lq.mnemonics(list_name, rng, []).get("rows") or []
    mns = offer_mnemonics(question, seen)
    labels = [l for l in disc["labels"] if l not in ("job", "device")]
    rows = _inventory(list_name)
    roles = sorted({d["role"] for d in rows if d.get("role")})
    got = gateway.ask(FEATURE, PROMPT_LOGS, LogsChoices,
                      parts_logs(question, kinds, mns, labels,
                                 named_devices(question, rows), roles, now),
                      actor=actor, context={"builder": vocabulary_logs()}, send=send,
                      today=today)
    if not got["ok"]:
        return dict(got, offered=mns)
    c = got["output"]
    base = {"call_id": got["call_id"], "cost_usd": got["cost_usd"], "offered": mns,
            "choices": c.model_dump(mode="json")}
    if c.outcome is Outcome.ask:
        return dict(base, ok=False, error="ask", clarify=c.question[:200],
                    detail=f"which one is meant: {c.question[:200]}")
    if c.outcome is Outcome.refuse:
        return dict(base, ok=False, error="unanswerable",
                    detail=f"the builder cannot answer this: {c.why_not[:200]}")
    v, said = values_logs(c), []
    for key, allowed, what in (("job", set(kinds), "kind"), ("mn", set(mns), "mnemonic")):
        out_ = [x for x in v[key] if x not in allowed]
        if out_:
            said.append(f"left out the {what} {', '.join(out_[:3])}: not one offered")
            v[key] = [x for x in v[key] if x in allowed]
    held = {d["hostname"] for d in rows if d.get("hostname")}
    unknown = [d for d in v["dev"] if d not in held]
    if unknown:
        said.append(f"left out {', '.join(unknown[:3])}: not a device of {list_name}")
        v["dev"] = [d for d in v["dev"] if d in held]
    if v["role"] and v["role"] not in roles:
        said.append(f"left out the role {v['role'][:40]!r}: no device of {list_name} has it")
        v["role"] = ""
    view = lq.view(list_name, v, now=now, client=probe)
    out = dict(base, ok=True, error="", values=v, view=view,
               errors=said + list(view["errors"]), lines=None, test="")
    built = view.get("built") or {}
    if built.get("log_query"):
        n = lq._count(client or lq._client(list_name, TEST_WAIT), built["log_query"],
                      view["range"])
        out["lines"] = n
        out["test"] = (f"Loki did not answer the test run within {TEST_WAIT:.0f} s, or "
                       "refused it" if n is None else
                       f"the test run matches {n} line(s) over the range")
    return out
