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
import datetime as dt
import logging
import re
import time
from enum import Enum
from zoneinfo import ZoneInfo

from modules.ai import calls, gateway
from modules.ai.needs import Need
from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

FEATURE = "nl_query"
#: v2 (the operator, 2026-10-25, from the first live run of the recorded cases): an unstated
#: scope is one line per device, never collapsed unprompted. v3 (v2's live run, case 9):
#: things in a state are counted, never maxed. v4 (v3's five runs, the operator): the defaults
#: the runs alternated between, fixed: the 5-minute CPU, the 64-bit counter, a rate over 5m,
#: no group for one named device. v5 (v4's five runs, the operator): a gauge grouped by avg
#: (max for highest or peak), never summed; one interface label, ifName; a rate unless a
#: count is asked for. v6 (v5's five runs, C1724; the operator's ruling, 2026-10-25): the four
#: choices the runs still alternated between, fixed: a top N only when the question says "top"
#: or a number; no group when the series are already one per interface asked; bits only when
#: the question says bits or bandwidth; "today" a custom range from `today_start_utc` (midnight
#: in the viewer's timezone, worked out here, never by the model) to now. v7 (C1740's ruling
#: and v6's runs on the 20, never held-out set 1's, 2026-10-25): "yesterday", "this week" and
#: "last week" as calendar spans in the same timezone, each start given as data; the per-CPU
#: MIB over the older average when both are offered. Earlier versions stay for their record.
PROMPT = ("nl_metrics", 7)
#: The candidate, asked only when a measurement names it (`metrics(prompt=...)`,
#: scripts/nmas-nl-cases --prompt) until it meets the adoption bar (the operator, 2026-10-26:
#: no case the current version passes may fail, consistency at the floor, cost reported).
#: v8, the network-context version: the network's summary in the cached prefix, the coverage
#: of its layers with the question, `needs` (C1780), the builder's `resets` (a reboot is the
#: uptime falling), and "this week" as the last 7 days unless the words say since Monday (the
#: operator's walk, 2026-10-26). v8 could not be measured: its prompt passed the task's 8,000
#: estimated tokens (the local tier's context too) on 9 of the 22, refused before any call.
#: v9 is v8 with its network context compacted (`network_context(compact=True)`: each layer's
#: state and why, the builders' summary) and its needs section tightened; measured once.
CANDIDATE = ("nl_metrics", 9)
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
         "up": ("up",),
         # A restart is the uptime falling (the operator's walk, 2026-10-26): "rebooted"
         # shares no word with sysUpTime, so the question was never offered it.
         **{w: ("uptime", "up", "time") for w in (
             "reboot", "reboots", "rebooted", "rebooting", "reload", "reloads", "reloaded",
             "restart", "restarts", "restarted", "crashed", "crash", "crashes")}}
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


class OpKindV3(str, Enum):
    """v3: the builder's `resets` beside `changes` (a device's uptime falling is its restart)."""
    rate = "rate"
    increase = "increase"
    changes = "changes"
    resets = "resets"
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


class OperationV3(StrictModel):
    kind: OpKindV3
    arg: str


@register("nl_metrics", 3)
class MetricsChoicesV3(StrictModel):
    """Prompt v8's answer (the network-context version, the operator, 2026-10-26): v2's
    choices, `resets` among the operations, and `needs`, what the answer lacked that Mercury
    looks up once (`modules/ai/needs.py`, C1780)."""
    outcome: Outcome
    question: str
    why_not: str
    metric: str
    devices: list[str]
    role: str
    interfaces: list[str]
    filters: list[Filter]
    operations: list[OperationV3]
    top: Top
    range: Range
    from_utc: str
    to_utc: str
    needs: list[Need]


#: Each prompt version's answer schema: v1 to v7 answer `MetricsChoices` (v2), so a recorded
#: case replays as it was asked.
SCHEMA_OF = {8: MetricsChoicesV3, 9: MetricsChoicesV3}


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
    lines += [f"- {k}: how many times a gauge's value "
              + ("fell in the window before each point (a device's uptime falling is its "
                 "restart)" if k == "resets" else
                 "changed in the window before each point (a state such as an interface's up "
                 "or down)")
              + ", never by how much; its argument is a window, one of "
              + ", ".join(pq.CHANGES_WINDOWS)
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


def network_context(list_name: str, store: str, compact: bool = False) -> dict:
    """What of the network goes with a question (metrics v8, logs v3; PHASE8_PLAN 15.15):
    ``{"summary", "coverage"}``, text. The summary (the devices by name and role, platforms,
    sites: the topology class, 15.11) only when the network allows that class, else why not;
    the coverage of every layer always, so a question resting on a layer not collected is
    said, never inferred (with the class off, each layer's state alone: a why can name a
    device). *store* is the builder's own (``metrics`` or ``logs``): its layer is present,
    the other builder's is said to be there."""
    from modules import endpoints as E
    from modules import network_model as NM
    from modules.ai import egress_classes

    gate = egress_classes.topology_allowed(list_name)
    model, err = NM.model_for(list_name)
    if model is None:
        said = f"could not read: the network model ({err})"
        return {"summary": said, "coverage": said}
    here = {"state": "present", "age": "", "why": ""}
    there = {"state": "not_collected", "source": "", "age": ""}
    carried = {
        "performance": (dict(here, source="this network's metrics store (Prometheus), the "
                                          "builder's own") if store == "metrics" else
                        dict(there, why="metrics are the Metrics builder's, not this one's")),
        "events": (dict(here, source="this network's log store (Loki), the builder's own")
                   if store == "logs" else
                   dict(there, why="log lines are the Logs builder's, not this one's")),
        "endpoints": E.coverage_layer(list_name)}
    obs = NM.unread("Ask in words reads no observed adjacency; the builders read metrics and "
                    "logs")
    cov = NM.coverage(model, obs, dict(model["nodes"]), carried)
    if compact:
        # Metrics v9 (2026-10-26): each layer's state, and why where it is not present, and
        # the builders' summary: v8's sources, ages and Explain's summary took its largest
        # prompt to 8,531 estimated tokens against the task's 8,000, the local tier's context
        # too, and nine of its 22 cases were refused before any call.
        lines = [f"{layer}: {c['state']}" + (f" ({c['why']})" if c.get("why")
                                             and gate["allowed"] and c["state"] != "present"
                                             else "")
                 for layer, c in cov.items()]
        summary = summary_for_builders(model)
    else:
        lines = []
        for layer, c in cov.items():
            if not gate["allowed"]:
                lines.append(f"{layer}: {c['state']}")
                continue
            lines.append(f"{layer}: {c['state']}" + "".join(
                f"; {k} {c[k]}" for k in ("source", "age", "why") if c.get(k)))
        summary = NM.summary(model)
    return {"summary": (summary if gate["allowed"] else
                        f"withheld: {gate['why']} (the topology class, 15.11)"),
            "coverage": "\n".join(lines)}


def summary_for_builders(model: dict) -> str:
    """The network as a builder's choice reads it: its devices by role and by platform, and
    each device's name with its role (a role or a device named in the words), never the links,
    adjacencies or citation ids Explain's summary carries (`network_model.summary`)."""
    nodes = list(model["nodes"].values())

    def tally(key):
        out = {}
        for n in nodes:
            v = n.get(key) or "not recorded"
            out[v] = out.get(v, 0) + 1
        return ", ".join(f"{k} {n}" for k, n in sorted(out.items()))
    index = ("; ".join(f"{n['name']} {n.get('role') or 'no role'}"
                       for n in sorted(nodes, key=lambda n: n["name"]))
             if len(nodes) <= 50 else f"not listed: {len(nodes)} devices")
    return (f"network {model['network']}: {len(nodes)} devices; by role: {tally('role')}; "
            f"by platform: {tally('platform')}; devices: {index}")


def looked_up(results: list) -> str:
    """The needs round's results as the follow-up's data (`modules/ai/needs.py`): each need,
    fulfilled with what was found, or unfulfilled with why."""
    import json

    return "\n".join(
        f"{r['kind']} {r['subject']}: "
        + (json.dumps(r["data"], sort_keys=True, ensure_ascii=False)
           if r["state"] == "fulfilled" else f"unfulfilled ({r['why']})")
        for r in results) or "(nothing looked up)"


def _ask_round(schema, prompt, data: dict, *, list_name, actor, ctx, send, today, thinking,
               subject) -> dict:
    """One question's call, and its needs round when the answer names needs (at most one
    follow-up, `needs.run`): the gateway's answer, the follow-up's in place of the first's
    when there was one, ``cost_usd`` the round's combined, ``parent_call_id`` the first
    call's."""
    from modules.ai import needs as N

    kw = {"actor": actor, "context": ctx, "send": send, "today": today, "thinking": thinking}
    got = gateway.ask(FEATURE, prompt, schema, dict(data, looked_up=looked_up([])),
                      subject=subject, **kw)
    wanted = list(getattr(got.get("output"), "needs", None) or []) if got.get("ok") else []
    if not wanted:
        return got
    held = {}

    def follow(results, link):
        held["got"] = gateway.ask(FEATURE, prompt, schema,
                                  dict(data, looked_up=looked_up(results)),
                                  subject=dict(subject, **link), **kw)
        return held["got"]

    rnd = N.run(got["call_id"], list_name, [n.model_dump(mode="json") for n in wanted],
                actor=actor, follow=follow)
    second = held.get("got")
    if not rnd["ok"] or second is None:
        return dict(got, needs_said=rnd["error"] or "nothing could be looked up")
    total = round((got.get("cost_usd") or 0) + (second.get("cost_usd") or 0), 6)
    return dict(second, cost_usd=total, parent_call_id=got["call_id"],
                needs_said="; ".join(f"{r['kind']} {r['subject']}: {r['state']}"
                                     for r in rnd["results"]))


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


# ------------------------------------------------------------------------ "today" (C1724)
#
# "Today" starts at midnight, and midnight is a timezone's. No installation timezone setting
# exists (C1740), so until one does, the viewer's browser names its own: the words form
# carries the IANA name (`tz`) and the offset east of UTC in minutes (`tz_off`) as a fallback,
# filled by static/js/nmas_logq.js. Mercury works out midnight as a UTC time, DST-correct, and
# hands the model that time as data: the model never computes a timezone.

#: The longest IANA name taken (the longest in the database is 32 characters).
ZONE_NAME_MAX = 64
#: An IANA name's shape: letters, digits, `_`, `+`, `-`, in at most three parts. Checked
#: before zoneinfo reads it, so no path ("../") reaches the zone files.
_ZONE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(?:/[A-Za-z0-9_+\-]+){0,2}$")
#: The widest offset any zone has: UTC+14 (Kiritimati) and UTC-12; ±14 h either way.
OFFSET_MAX_MIN = 14 * 60


def _offset_name(minutes: int) -> str:
    sign = "-" if minutes < 0 else "+"
    return f"UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def zone(name: str = "", offset: str = "") -> dict:
    """The timezone "today" is counted in, from what the viewer's browser sent: ``{"tz",
    "name", "source", "ignored"}``. *source* is ``browser`` (an IANA name zoneinfo knows),
    ``offset`` (no usable name; the offset, minutes east of UTC, within ±14 h) or ``none``
    (neither: UTC). *ignored* says what was sent and not used, or is empty."""
    name, offset, ignored = (name or "").strip(), (offset or "").strip(), []
    if name:
        if len(name) <= ZONE_NAME_MAX and _ZONE_NAME.match(name):
            try:
                return {"tz": ZoneInfo(name), "name": name, "source": "browser",
                        "ignored": ""}
            # ZoneInfoNotFoundError is a KeyError; a folder ("America") is an OSError.
            except (KeyError, ValueError, OSError):
                pass
        ignored.append(f"the timezone {name[:ZONE_NAME_MAX]!r} is not one Mercury knows")
    if offset:
        try:
            minutes = int(offset)
        except ValueError:
            minutes = None
        if minutes is not None and abs(minutes) <= OFFSET_MAX_MIN:
            return {"tz": dt.timezone(dt.timedelta(minutes=minutes)),
                    "name": _offset_name(minutes), "source": "offset",
                    "ignored": "; ".join(ignored)}
        ignored.append(f"the offset {offset[:12]!r} is not a whole number of minutes within "
                       "±14 hours")
    return {"tz": dt.timezone.utc, "name": "UTC", "source": "none",
            "ignored": "; ".join(ignored)}


def today_start(now: float, tz) -> float:
    """Today's first instant in *tz*, as epoch seconds: midnight of the date *now* falls on
    there. A midnight a DST change skips is the day's first instant (its earlier offset)."""
    return day_start(now, tz)


def day_start(now: float, tz, days_back: int = 0) -> float:
    """The first instant, in *tz*, of the calendar day *days_back* days before the one *now*
    falls on there (0 today, 1 yesterday), as epoch seconds: counted in calendar days, never
    in 24-hour steps, so a DST change between them moves nothing."""
    day = dt.datetime.fromtimestamp(now, tz).date() - dt.timedelta(days=days_back)
    return dt.datetime.combine(day, dt.time(0, 0), tzinfo=tz).timestamp()


#: Weeks start on Monday (ISO 8601), said beside a filled week (the operator's C1740 ruling,
#: 2026-10-25: "this week" and "last week" in the same timezone as "today").
WEEK_STARTS = "Monday"


def week_start(now: float, tz, weeks_back: int = 0) -> float:
    """Midnight in *tz* of the Monday of the week *now* falls in there, less *weeks_back*
    weeks (0 this week, 1 last week), as epoch seconds; in calendar days, as `day_start`."""
    local = dt.datetime.fromtimestamp(now, tz).date()
    monday = local - dt.timedelta(days=local.weekday() + 7 * weeks_back)
    return dt.datetime.combine(monday, dt.time(0, 0), tzinfo=tz).timestamp()


def spans(now: float, tz) -> dict:
    """The named spans' starts, UTC stamps as the data gives them: ``{"today", "yesterday",
    "this week", "last week"}``. Each ends where the next one up starts, or now."""
    return {"today": _stamp(day_start(now, tz)), "yesterday": _stamp(day_start(now, tz, 1)),
            "this week": _stamp(week_start(now, tz)),
            "last week": _stamp(week_start(now, tz, 1))}


def _stamp(epoch: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(epoch))


def today_words(z: dict) -> str:
    """Which midnight "today" ran from, and why that timezone (said beside the filled range)."""
    if z["source"] == "browser":
        why = "your browser's timezone; no installation timezone is set"
    elif z["source"] == "offset":
        why = ("your browser's offset from UTC, as it named no timezone Mercury knows; no "
               "installation timezone is set")
    elif z["ignored"]:
        what = "both were" if "; " in z["ignored"] else "it was"
        why = f"{z['ignored']}, so {what} ignored; no installation timezone is set"
    else:
        why = "no timezone was sent; no installation timezone is set"
    return f"'Today' runs from midnight {z['name']} ({why})"


def span_words(z: dict, span: str) -> str:
    """Which midnight a named span was counted from, said beside the filled range: today's
    words as ever; yesterday's, this week's and last week's in the same timezone, a week's
    naming the day it starts on."""
    if span == "today":
        return today_words(z)
    words = today_words(z).split(" (", 1)[1]
    start = {"yesterday": "midnight", "this week": f"midnight on {WEEK_STARTS}",
             "last week": f"midnight on {WEEK_STARTS}"}[span]
    return f"'{span[0].upper()}{span[1:]}' is counted from {start} {z['name']} ({words}"


def range_said(rng: dict, z: dict, span: str = None) -> str:
    """How the words' period was read, said in the fill's notice every time (the operator's
    walk, 2026-10-26: "this week" on a Monday read as today, and nothing said so): the range
    the builder holds, from and to, in the viewer's timezone with UTC beside it; a named span's
    start in its words."""
    start, end = rng.get("start"), rng.get("end")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return ""

    def at(epoch):
        local = dt.datetime.fromtimestamp(epoch, z["tz"])
        return local.strftime("%a %d %b %H:%M")

    hours = (end - start) / 3600
    length = (f"{hours:.0f} hours" if hours < 48 else f"{hours / 24:.1f} days".replace(
        ".0 days", " days"))
    named = f" ('{span}')" if span else ""
    return (f"Read as{named} {at(start)} to {at(end)} {z['name']} ({length}; "
            f"{_stamp(start)} to {_stamp(end)} UTC)")


def _sentence(text: str) -> str:
    """*text* as the end of a sentence the screen closes with its own full stop (the
    operator's walk, 2026-10-26: a refusal ended in ".."), at most 200 characters."""
    return (text or "")[:200].rstrip().rstrip(".")


def logs_route(list_name: str, question: str) -> str:
    """When a metrics question is about an event the device logs (a reload, an interface or
    adjacency going down, a configuration change), where the logs answer it: "; the logs can
    answer it: ask in History › Query's Logs (%SYS-5-RELOAD, %SYS-5-RESTART)"; else "" (the
    operator's walk, 2026-10-26: a refusal offers the logs route). Mercury's own words: the
    platform pack's event mnemonics whose words the question holds, no call."""
    mns = [e["mnemonic"] for e in events_for(list_name) if _event_hit(e, question)]
    return (f"; the logs can answer it: ask in Logs ({', '.join(mns[:4])})" if mns else "")


#: The platform pack's event mnemonics (modules/nsot/platform_events.json), per dialect.
EVENTS_PACK = None


def _events_pack() -> dict:
    global EVENTS_PACK
    if EVENTS_PACK is None:
        import json
        import os

        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "nsot", "platform_events.json")
        with open(path, encoding="utf-8") as fh:
            EVENTS_PACK = json.load(fh)["events"]
    return EVENTS_PACK


def events_for(list_name: str, rows: list = None) -> list:
    """The event mnemonics of the dialects *list_name*'s devices speak, each once, in the
    pack's order: ``[{"mnemonic", "records", "words"}]``."""
    from modules.nsot.platform import platform_for_device

    pack, out, seen = _events_pack(), [], set()
    dialects = []
    for row in rows if rows is not None else _inventory(list_name):
        try:
            d = platform_for_device(row)
        except Exception:                                # noqa: BLE001 (a device skipped)
            continue
        if d not in dialects:
            dialects.append(d)
    for d in dialects:
        for e in pack.get(d) or []:
            if e["mnemonic"] not in seen:
                seen.add(e["mnemonic"])
                out.append(e)
    return out


def _event_hit(event: dict, question: str) -> bool:
    words = {w.lower() for w in re.findall(r"[A-Za-z0-9]+", question or "")}
    return bool(words & set(event["words"]))


def parts(question: str, offered: list, devices: list, roles: list, now: float,
          z: dict = None) -> dict:
    """The call's own data, in the user turn (the time too: it moves every call, so it is
    never in the cached prefix). *z* is `zone`'s answer; none, UTC."""
    z = z or zone()
    s = spans(now, z["tz"])
    return {
        "question": question,
        "now_utc": _stamp(now),
        "today_start_utc": s["today"],
        "yesterday_start_utc": s["yesterday"],
        "week_start_utc": s["this week"],
        "last_week_start_utc": s["last week"],
        "today_zone": z["name"],
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
            now: float = None, today: str = None, viewer_zone: dict = None,
            thinking: str = None, prompt: tuple = None) -> dict:
    """``{"ok", "error", "detail", "values", "view", "series", "call_id", "cost_usd",
    "offered", "today", "range_said"}``: the builder filled from *question*, read back by the
    builder, and its test run; or a refusal naming why, with nothing filled. *viewer_zone* is
    `zone`'s answer for the viewer (none: UTC, said); *today* is the gateway's spend day, not
    this. A filled range that starts at today's midnight carries ``today``, the words saying
    which midnight; every filled range carries ``range_said``, how the words' period was read
    (the operator's walk, 2026-10-26: always shown). *thinking* and *prompt* are a
    measurement's (scripts/nmas-nl-cases --thinking, --prompt); the screen sends neither, so
    the task's pin and `PROMPT` hold."""
    from modules import history_promq as pq

    prompt = tuple(prompt or PROMPT)
    schema = SCHEMA_OF.get(prompt[1], MetricsChoices)
    z = viewer_zone or zone()

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
                          "words, or search the builder's Metric box)"
                          + logs_route(list_name, question)}
    # What the call is about, written with it (15.14): the network's query, its named devices.
    subject = {"kind": "query", "id": list_name, "devices": list(named)}
    data = parts(question, offered, named, roles, now, z)
    if prompt[1] >= 8:
        net = network_context(list_name, "metrics", compact=prompt[1] >= 9)
        got = _ask_round(schema, prompt, dict(data, coverage=net["coverage"]),
                         list_name=list_name, actor=actor,
                         ctx={"builder": vocabulary(), "network": net["summary"]}, send=send,
                         today=today, thinking=thinking, subject=subject)
    else:
        got = gateway.ask(FEATURE, prompt, schema, data,
                          actor=actor, context={"builder": vocabulary()}, send=send,
                          today=today, thinking=thinking, subject=subject)
    if not got["ok"]:
        return dict(got, offered=[o[0] for o in offered])
    c, base = got["output"], {"call_id": got["call_id"], "cost_usd": got["cost_usd"],
                              "offered": [o[0] for o in offered],
                              # The model's own answer, as recorded cases keep it.
                              "choices": got["output"].model_dump(mode="json"),
                              **{k: got[k] for k in ("parent_call_id", "needs_said")
                                 if got.get(k)}}
    links = {"page": f"/v2/history/query/ask/metrics?list={list_name}"}
    if c.outcome is Outcome.ask:
        # One question back, never a guess (the operator's cases, 2026-10-25): the person
        # answers it in their words and asks again.
        calls.record_use(got["call_id"], "asked a question back", actor=actor,
                         detail=c.question[:200], links=links)
        return dict(base, ok=False, error="ask", clarify=c.question[:200],
                    detail=f"which one is meant: {_sentence(c.question)}")
    if c.outcome is Outcome.refuse:
        calls.record_use(got["call_id"], "shown: the builder cannot answer", actor=actor,
                         detail=c.why_not[:200], links=links)
        return dict(base, ok=False, error="unanswerable",
                    detail=f"the builder cannot answer this: {_sentence(c.why_not)}"
                           + logs_route(list_name, question))
    names = {o[0] for o in offered}
    if c.metric not in names:
        calls.record_use(got["call_id"], "refused by validation", actor=actor,
                         detail=f"{c.metric[:80]!r} was not offered", links=links)
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
    # The range is a named span's when it starts at a start the call was given: then the
    # filled notice says whose midnight that was (the operator, 2026-10-25, C1724, C1740).
    # On a Monday "today" and "this week" start together; the day is said.
    started = {v_: k for k, v_ in reversed(spans(now, z["tz"]).items())}
    span = started.get(v.get("from")) if c.range is Range.custom else None
    out = dict(base, ok=True, error="", values=v, view=view,
               errors=said + list(view["errors"]), series=None, test="",
               today=span_words(z, span) if span else "",
               range_said=range_said(view.get("range") or {}, z, span))
    built = view.get("built")
    if built and view["state"] == "ok":
        n = pq.instant_count(client or pq._client(list_name, TEST_WAIT), built["query"],
                             view["range"]["end"])
        out["series"] = n
        out["test"] = (f"Prometheus did not answer the test run within {TEST_WAIT:.0f} s, or "
                       "refused it" if n is None else
                       f"the test run answers {n} series now")
    calls.record_use(got["call_id"], "filled the builder", actor=actor,
                     detail="; ".join(out["errors"])[:200],
                     links=_filled_links(links, "/v2/history/query/ask/metrics", view))
    return out


def _filled_links(links: dict, page: str, view: dict) -> dict:
    """A fill's use row's links (15.14: the call's History row links to what it produced): the
    builder's address with every choice the answer filled (the view's own `qs`), else the
    builder's page as *links* names it."""
    try:
        return dict(links, page=page + view["qs"]())
    except Exception:                                  # noqa: BLE001 - the page alone
        return links


# ---------------------------------------------------------------------------- the logs half

#: v2 (C1740's logs half, 2026-10-26): the named days and weeks counted in the viewer's
#: timezone, given as data as v7 of the metrics half gives them; v1 worked "yesterday" out
#: from now_utc, in UTC.
PROMPT_LOGS = ("nl_logs", 2)
#: The logs candidate, as `CANDIDATE`: v3 is the network-context version, the platform pack's
#: event mnemonics offered with every question (each with what it records), `needs`, and
#: "this week" as the last 7 days unless the words say since Monday (the operator's walk,
#: 2026-10-26).
CANDIDATE_LOGS = ("nl_logs", 3)
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


@register("nl_logs", 2)
class LogsChoicesV2(StrictModel):
    """Logs prompt v3's answer: v1's choices, and `needs` (C1780), as `MetricsChoicesV3`."""
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
    needs: list[Need]


SCHEMA_OF_LOGS = {3: LogsChoicesV2}


def offer_events(question: str, seen: list, events: list) -> list:
    """Logs v3's offer: ``[(mnemonic, what)]``, the platform pack's *events* first, each with
    what it records, whether or not the range holds one (the operator's walk, 2026-10-26: a
    reload the range happens not to hold is still named); then `offer_mnemonics`' own, each
    with how often the reader counted it, at most `OFFERED_MNEMONICS` in all."""
    counted = dict(seen)
    out = [(e["mnemonic"], e["records"] + (f"; seen {counted[e['mnemonic']]} times in 7 days"
                                           if counted.get(e["mnemonic"]) else ""))
           for e in events]
    have = {m for m, _w in out}
    for mn in offer_mnemonics(question, seen):
        if mn not in have and len(out) < OFFERED_MNEMONICS:
            out.append((mn, f"seen {counted.get(mn, 0)} times in 7 days"))
    return out[:max(OFFERED_MNEMONICS, len(events))]


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


def vocabulary_logs(version: int = 2) -> str:
    """The logs builder's vocabulary, the same bytes on every call (the cached prefix). From
    prompt v3 it says what every query leaves out (Mercury's own heartbeat lines: a question
    about them answered 0 while the switch sent 8, the logs case set's evidence, 2026-10-26,
    C1817)."""
    from modules import history_logq as lq
    from modules.device_logs import SEVERITY

    left_out = (["Left out of every query: Mercury's own heartbeat lines (NMAS-HEARTBEAT); a "
                 "question about them cannot be answered here (a device's Logs tab counts "
                 "them)"] if version >= 3 else [])
    return "\n".join(left_out + [
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
               roles: list, now: float, z: dict = None) -> dict:
    """The logs call's own data, the named spans' starts with it, as `parts` gives them. *z*
    is `zone`'s answer; none, UTC."""
    z = z or zone()
    s = spans(now, z["tz"])
    return {
        "question": question,
        "now_utc": _stamp(now),
        "today_start_utc": s["today"],
        "yesterday_start_utc": s["yesterday"],
        "week_start_utc": s["this week"],
        "last_week_start_utc": s["last week"],
        "today_zone": z["name"],
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
         now: float = None, today: str = None, viewer_zone: dict = None,
         prompt: tuple = None) -> dict:
    """``{"ok", "error", "detail", "values", "view", "lines", ..., "today", "range_said"}``: the
    logs builder filled from *question*, read back by the builder, and its test run (one count
    over the range); or a refusal, or one question back, with nothing filled. *viewer_zone* is
    `zone`'s answer for the viewer (none: UTC, said), as `metrics` takes it (C1740); *prompt*
    a measurement's, as `metrics` takes it."""
    from modules import history_logq as lq

    prompt = tuple(prompt or PROMPT_LOGS)
    schema = SCHEMA_OF_LOGS.get(prompt[1], LogsChoices)
    z = viewer_zone or zone()
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
    labels = [l for l in disc["labels"] if l not in ("job", "device")]
    rows = _inventory(list_name)
    roles = sorted({d["role"] for d in rows if d.get("role")})
    named = named_devices(question, rows)
    # What the call is about, written with it (15.14): the network's query, its named devices.
    subject = {"kind": "query", "id": list_name, "devices": list(named)}
    if prompt[1] >= 3:
        offered_ = offer_events(question, seen, events_for(list_name, rows))
        mns = [m for m, _w in offered_]
        data = parts_logs(question, kinds, mns, labels, named, roles, now, z)
        net = network_context(list_name, "logs")
        got = _ask_round(schema, prompt,
                         dict(data, mnemonics="\n".join(f"{m} | {w}" for m, w in offered_),
                              coverage=net["coverage"]),
                         list_name=list_name, actor=actor,
                         ctx={"builder": vocabulary_logs(prompt[1]), "network": net["summary"]},
                         send=send, today=today, thinking=None, subject=subject)
    else:
        mns = offer_mnemonics(question, seen)
        got = gateway.ask(FEATURE, prompt, schema,
                          parts_logs(question, kinds, mns, labels, named, roles, now, z),
                          actor=actor, context={"builder": vocabulary_logs()}, send=send,
                          today=today, subject=subject)
    if not got["ok"]:
        return dict(got, offered=mns)
    c = got["output"]
    base = {"call_id": got["call_id"], "cost_usd": got["cost_usd"], "offered": mns,
            "choices": c.model_dump(mode="json"),
            **{k: got[k] for k in ("parent_call_id", "needs_said") if got.get(k)}}
    links = {"page": f"/v2/history/query/ask/logs?list={list_name}"}
    if c.outcome is Outcome.ask:
        calls.record_use(got["call_id"], "asked a question back", actor=actor,
                         detail=c.question[:200], links=links)
        return dict(base, ok=False, error="ask", clarify=c.question[:200],
                    detail=f"which one is meant: {_sentence(c.question)}")
    if c.outcome is Outcome.refuse:
        calls.record_use(got["call_id"], "shown: the builder cannot answer", actor=actor,
                         detail=c.why_not[:200], links=links)
        return dict(base, ok=False, error="unanswerable",
                    detail=f"the builder cannot answer this: {_sentence(c.why_not)}")
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
    # Whose midnight a named span ran from, said beside the filled range, as the metrics half
    # says it (C1740).
    started = {v_: k for k, v_ in reversed(spans(now, z["tz"]).items())}
    span = started.get(v.get("from")) if c.range is LogsRange.custom else None
    out = dict(base, ok=True, error="", values=v, view=view,
               errors=said + list(view["errors"]), lines=None, test="",
               today=span_words(z, span) if span else "",
               range_said=range_said(view.get("range") or {}, z, span))
    built = view.get("built") or {}
    if built.get("log_query"):
        n = lq._count(client or lq._client(list_name, TEST_WAIT), built["log_query"],
                      view["range"])
        out["lines"] = n
        out["test"] = (f"Loki did not answer the test run within {TEST_WAIT:.0f} s, or "
                       "refused it" if n is None else
                       f"the test run matches {n} line(s) over the range")
        if n == 0 and v.get("has"):
            # A zero that rests on free text says so, never "an answer" (the operator's walk,
            # 2026-10-26: "reboot", which IOS never logs, read as no reboots).
            out["test"] += (f"; no line contains '{v['has']}', which may not be how the "
                            "platform logs it")
    calls.record_use(got["call_id"], "filled the builder", actor=actor,
                     detail="; ".join(out["errors"])[:200],
                     links=_filled_links(links, "/v2/history/query/ask/logs", view))
    return out
