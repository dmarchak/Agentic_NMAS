"""History › Query › Ask your own, the METRICS builder (board E3, `QueryBuilderMetrics3.dc.html`
and its phone board, approved by the operator 2026-10-15; compared region by region in
docs/fidelity/history-ask-metrics.md). Its sibling, the logs builder, is modules/history_logq.py;
what the two share (one token each, durations, the range, the address) is modules/history_ask.py.

A person builds a PromQL question by choosing, never by typing PromQL: what (a metric Prometheus
holds, found by searching its names and help text), the devices, the interfaces, filters on any
label the metric carries, a chain of operations (a rate or an increase, × 8 for bits, per
minute, sum, average, lowest, highest or count by a label, a comparison), the top so many, and
a range. Mercury forms the query from those choices and draws it as it forms, the last choice
marked and said in plain words; Ask sends it.

**Discovered, never assumed.** Every metric name, help text and type is Prometheus's (its
metadata and label-values APIs); every label name and value the builder offers is read from
Prometheus for the chosen metric over the range (its labels and label-values APIs, through the
Prometheus integration client's one GET). The labels it reads by name are Mercury's own
(`device` and `role`, which modules/prometheus_targets.py writes on every target) and IF-MIB's
interface names (`ifDescr`, `ifName`); a metric without one has no such row.

**The counter rule.** A counter (Prometheus's metadata says so) is asked as a rate or an
increase first, never its raw value, and the unit follows the chain: bytes, × 8 is bits, rate
is per second.

**One token each.** A value reaches Prometheus only inside a string Mercury quotes
(`history_ask.string`); several values are an alternation of literals; a pattern typed for
=~ or !~ is one string too (Prometheus anchors it at both ends); a metric or label NAME cannot
be quoted, so it must be one Prometheus holds, else it is refused by name.

**Bounds.** Prometheus's own (its flags: how long it keeps, how long one ask may run, how many
samples one ask may load; its configuration: how often each job is scraped) and Mercury's (the
step widens with the range so a series is at most 1,000 points, `panels.step_for`; at most 200
series an answer, the 20 highest drawn). A question past one is refused naming both operands,
with nothing asked of the range.

**A read.** Nothing is written and no list is created.
"""

import logging
import math
import re
import time

from modules import history_ask
from modules.history_ask import (REMEMBER, duration_words, iso, matcher, parse_duration,
                                 string, utc)

log = logging.getLogger(__name__)

PAGE_PATH = "/v2/history/query/ask/metrics"

#: The ranges the chips offer: key -> (words, seconds).
RANGES = {"1h": ("1 h", 3600), "24h": ("24 h", 86400), "7d": ("7 days", 7 * 86400),
          "30d": ("30 days", 30 * 86400), "90d": ("90 days", 90 * 86400)}
#: A rate's or an increase's window: key -> (words, seconds).
WINDOWS = {"1m": ("1 minute", 60), "5m": ("5 minutes", 300), "15m": ("15 minutes", 900),
           "1h": ("1 hour", 3600)}
#: The operations: kind -> (the menu's words, its group).
RANGE_OPS = {"rate": "rate per second", "increase": "increase over the window"}
UNIT_OPS = {"bits": "× 8, bytes to bits", "per_min": "per minute (× 60)"}
AGGS = {"sum": "sum", "avg": "avg", "min": "min", "max": "max", "count": "count"}
#: What a group does, said under the query, and in the whole query's sentence.
AGG_WORDS = {"sum": ("adds up the series into", "added up into"),
             "avg": ("averages the series into", "averaged into"),
             "min": ("takes the lowest value of the series for", "the lowest for"),
             "max": ("takes the highest value of the series for", "the highest for"),
             "count": ("counts the series into", "counted into")}
COMPARE = {"ne": ("!=", "not equal to"), "eq": ("==", "equal to"), "gt": (">", "above"),
           "lt": ("<", "below")}
FILTER_OPS = {"=": "is exactly", "!=": "is not", "=~": "matches the pattern",
              "!~": "does not match the pattern"}
TOPS = ("5", "10")

#: Mercury's labels on every target (modules/prometheus_targets.py), and IF-MIB's interface
#: names, the one a metric carries first used.
DEVICE_LABEL = "device"
ROLE_LABEL = "role"
INTERFACE_LABELS = ("ifDescr", "ifName")

#: Mercury's bounds: series drawn of an answer, metrics listed for a search, values offered as
#: chips, operations and filters a question holds, and the longest value and pattern taken.
DRAWN = 20
PICK = 8
CHIPS = 3
MAX_OPS = 6
MAX_FILTERS = 8
VALUE_MAX = 128
PATTERN_MAX = 200
SEARCH_MAX = 80
#: The client's wait when Prometheus's query.timeout is not read: its default, 2 minutes, + 5 s.
DEFAULT_WAIT = 125.0

#: Start from (the board's four chips): key, the chip's words, the answer's title, the choices.
#: The metrics are IF-MIB's and Cisco's MIBs' (the product's devices), never a lab's; a chip
#: whose metric Prometheus does not hold is drawn as such, never as a link that goes nowhere.
PRESETS = (
    ("errors", "Errors per interface, top 5", "Input errors per interface",
     {"m": "ifInErrors", "op": ["rate:5m"], "top": "5", "range": "24h"}),
    ("cpu", "CPU per device, 7 days", "CPU per device",
     {"m": "cpmCPUTotal5minRev", "op": ["max:device"], "range": "7d"}),
    ("bgp", "BGP sessions not established", "BGP sessions not established, per device",
     {"m": "cbgpPeer2State", "op": ["ne:6", "count:device"], "range": "24h"}),
    ("bytes", "Bytes in, per role", "Bytes in per role",
     {"m": "ifHCInOctets", "f": ["ifDescr != Null0"], "op": ["rate:5m", "bits", "sum:role"],
      "range": "24h"}),
)

#: Every value the address carries, and its default. Lists are the repeatable ones.
DEFAULTS = {"m": "", "mq": "", "dev": [], "role": "", "if": [], "f": [], "op": [], "top": "",
            "range": "24h", "within": "", "from": "", "to": "", "fe": "", "fl": "", "fo": "",
            "fv": "", "fadd": "", "ask": "", "hl": ""}
LISTS = ("dev", "if", "f", "op")
#: The question's choices (what a preset sets or leaves at its default).
FILTERS = ("m", "dev", "role", "if", "f", "op", "top")
#: The keys a saved view keeps (modules/saved_views.py): the question and the range, asked.
ADDRESS_KEYS = ("m", "dev", "role", "if", "f", "op", "top", "range", "within", "from", "to",
                "ask")

_NAME = re.compile(r"^[A-Za-z_:][A-Za-z0-9_:]*$")
_LABEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUMBER = re.compile(r"^-?\d{1,12}(?:\.\d{1,6})?$")
_FILTER = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*) (=|!=|=~|!~) (.*)$", re.S)
#: SNMP exporter's help ends with the object's OID: dropped from the words drawn.
_OID_TAIL = re.compile(r"\s+-\s+\d+(?:\.\d+){3,}\s*$")

_CACHE = {}


def _now() -> float:
    """The clock (one seam, so a test fixes it without fixing every clock in the process)."""
    return time.time()


def forget():
    """Drop what is remembered about Prometheus (its bounds, its metadata): for tests."""
    _CACHE.clear()


# ---------------------------------------------------------------------------- the address

def parse_filter(token: str):
    """``(label, op, value)`` from a filter as the address carries it, "ifDescr != Null0" (one
    space each side of the operator, so a value starting with ~ or = is never read as part of
    it); None when it is not one."""
    m = _FILTER.match(token or "")
    return (m.group(1), m.group(2), m.group(3)) if m else None


def filter_token(label: str, op: str, value: str) -> str:
    return f"{label} {op} {value}"


def parse_op(token: str):
    """``(kind, arg)`` from an operation as the address carries it ("rate:5m", "bits",
    "sum:role", "sum:", "ne:6"); None when it is not one. A label named in it is checked
    against what the metric carries later (`check_ops`)."""
    token = token or ""
    kind, _sep, arg = token.partition(":")
    if kind in RANGE_OPS:
        return (kind, arg) if arg in WINDOWS else None
    if kind in UNIT_OPS:
        return (kind, "") if not arg else None
    if kind in AGGS:
        return (kind, arg) if not arg or _LABEL.match(arg) else None
    if kind in COMPARE:
        return (kind, arg) if _NUMBER.match(arg) else None
    return None


def op_token(kind: str, arg: str = "") -> str:
    return kind if kind in UNIT_OPS else f"{kind}:{arg}"


def _ops_from_form(values) -> list:
    """The chain as the Operations row's selects send it: kind `ok<i>` and argument `oa<i>`
    for each operation in order (the address itself carries `op` tokens)."""
    out = []
    for i in range(1, MAX_OPS + 1):
        kind = (values.get(f"ok{i}") or "").strip()
        if not kind:
            break
        arg = (values.get(f"oa{i}") or "").strip()
        if kind in RANGE_OPS and arg not in WINDOWS:
            arg = "5m"
        out.append(op_token(kind, arg))
    return out


def ask(values) -> tuple:
    """``(spec, errors)``: the choices the address (or the builder's form) carries, each
    checked for its shape; a value the builder cannot carry is left out and said (*errors*),
    never passed on. Whether a name is one Prometheus holds is `view`'s, after discovery."""
    spec, errors = history_ask.read_values(values, DEFAULTS, LISTS), []
    if (values.get("ok1") or "").strip():
        spec["op"] = _ops_from_form(values)
    if spec["m"] and not _NAME.match(spec["m"]):
        errors.append(f"{spec['m'][:60]!r} is not a metric name")
        spec["m"] = ""
    spec["mq"] = spec["mq"][:SEARCH_MAX]
    for key, what in (("dev", "device"), ("if", "interface")):
        long = [v for v in spec[key] if len(v) > VALUE_MAX]
        if long:
            errors.append(f"a {what} value of {len(long[0])} characters is longer than the "
                          f"{VALUE_MAX} taken")
            spec[key] = [v for v in spec[key] if len(v) <= VALUE_MAX]
    if len(spec["role"]) > VALUE_MAX:
        errors.append(f"a role of {len(spec['role'])} characters is longer than the "
                      f"{VALUE_MAX} taken")
        spec["role"] = ""
    # A filter written in the editor and added (Add sends `fadd`): it joins the list.
    if spec["fadd"] and spec["fl"]:
        spec["f"] = spec["f"] + [filter_token(spec["fl"], spec["fo"] or "=", spec["fv"])]
        spec.update(fe="", fl="", fo="", fv="", fadd="")
    spec["fadd"] = ""
    kept = []
    for token in spec["f"]:
        got = parse_filter(token)
        if not got:
            errors.append(f"{token[:60]!r} is not a filter (a label, = != =~ or !~, a value)")
            continue
        label, op, value = got
        limit = PATTERN_MAX if op in ("=~", "!~") else VALUE_MAX
        if len(value) > limit:
            errors.append(f"the {label} filter's value is {len(value)} characters; at most "
                          f"{limit} are taken")
            continue
        kept.append(token)
    spec["f"] = kept[:MAX_FILTERS]
    if len(kept) > MAX_FILTERS:
        errors.append(f"{len(kept)} filters; at most {MAX_FILTERS} are taken")
    ops = []
    for token in spec["op"]:
        if parse_op(token) is None:
            errors.append(f"{token[:40]!r} is not an operation")
            continue
        ops.append(token)
    if len(ops) > MAX_OPS:
        errors.append(f"{len(ops)} operations; at most {MAX_OPS} are taken")
    spec["op"] = ops[:MAX_OPS]
    if spec["top"] and spec["top"] not in TOPS:
        errors.append(f"{spec['top'][:10]!r} is not a top this offers: " + " or ".join(TOPS))
        spec["top"] = ""
    if spec["fo"] and spec["fo"] not in FILTER_OPS:
        spec["fo"] = ""
    if spec["fl"] and not _LABEL.match(spec["fl"]):
        spec["fl"] = ""
    spec["fv"] = spec["fv"][:PATTERN_MAX]
    if spec["range"] not in RANGES and spec["range"] != "custom":
        errors.append(f"{spec['range'][:20]!r} is not a range: " + ", ".join(RANGES)
                      + ", or From… to…")
        spec["range"] = "24h"
    return spec, errors


def qs(spec: dict, list_name: str = "", over: dict = None) -> str:
    """The address for *spec* with *over* applied: only what differs from the defaults."""
    return history_ask.qs(spec, DEFAULTS, LISTS, list_name, over)


def preset_over(params: dict) -> dict:
    """A Start-from chip's address: its choices, every other choice at its default."""
    over = {k: DEFAULTS[k] for k in FILTERS}
    over.update(params)
    over.update(ask="1", hl="start", fe="", fl="", fo="", fv="", mq="", within="",
                **{"from": "", "to": ""})
    return over


def preset_on(spec: dict) -> str:
    """The Start-from chip the question is exactly (its range aside), or ""."""
    for key, _title, _answer, params in PRESETS:
        want = dict({k: DEFAULTS[k] for k in FILTERS}, **params)
        if all(spec.get(k) == want[k] for k in FILTERS if k not in ("dev", "role")):
            return key
    return ""


def window(spec: dict, now: float) -> dict:
    """The range asked, to the minute (history_ask.window over this builder's chips)."""
    return history_ask.window(spec, now, RANGES)


# ---------------------------------------------------------------------------- Prometheus

def _client(list_name: str, wait: float = DEFAULT_WAIT):
    from modules.integrations.prometheus import PrometheusIntegration
    return PrometheusIntegration(timeout=wait, list_name=list_name)


def _words(r: dict, client) -> str:
    """A failed GET in the board's words: Prometheus's own reason where it gave one."""
    error = r.get("error") or "no answer"
    if r.get("detail"):
        return f"Prometheus refused the query: {r['detail']}"
    if error.startswith("Timed out"):
        return (f"Prometheus did not answer within {duration_words(max(client.timeout - 5, 1))} "
                "(its query.timeout; Mercury waits 5 s more)")
    return f"Prometheus: {error}"


def _json(client, path: str, **params) -> tuple:
    """``(data, error)`` from one GET through the integration client."""
    r = client._get(path, **params)                  # noqa: SLF001 (the client's one GET)
    if not r.get("ok"):
        return None, _words(r, client)
    try:
        body = r["response"].json()
    except ValueError as exc:
        return None, f"Prometheus's answer could not be read: {exc}"
    if (body or {}).get("status") != "success":
        return None, f"Prometheus refused the query: {(body or {}).get('error') or 'no reason'}"
    return body.get("data"), ""


def limits(list_name: str, client, now: float) -> dict:
    """Prometheus's own bounds, read from its flags and its configuration (remembered an
    hour): how long it keeps (`storage.tsdb.retention.time`, `.size`), how long one ask may
    run (`query.timeout`), how many samples one ask may load (`query.max-samples`), and how
    often each job is scraped. ``{"read_at", "error", <name>: {...}, "scrape": {job: s},
    "scrape_default": s}``; a bound it does not state is absent."""
    key = ("limits", list_name)
    got = _CACHE.get(key)
    if got and now - got[0] < REMEMBER:
        return got[1]
    out = {"read_at": iso(now), "error": "", "scrape": {}, "scrape_default": None}
    flags, err = _json(client, "api/v1/status/flags")
    if err:
        out["error"] = f"its flags could not be read: {err}"
        return out                                     # not remembered: asked again next time
    for name in ("storage.tsdb.retention.time", "query.timeout"):
        secs = parse_duration((flags or {}).get(name))
        if secs:
            out[name] = {"text": flags[name], "seconds": secs}
    size = (flags or {}).get("storage.tsdb.retention.size")
    if size and size not in ("0", "0B"):
        out["storage.tsdb.retention.size"] = {"text": size}
    try:
        n = int((flags or {}).get("query.max-samples") or 0)
    except ValueError:
        n = 0
    if n:
        out["query.max-samples"] = {"text": flags["query.max-samples"], "n": n}
    conf, err = _json(client, "api/v1/status/config")
    if not err:
        import yaml
        try:
            doc = yaml.safe_load((conf or {}).get("yaml") or "") or {}
        except yaml.YAMLError:
            doc = {}
        default = parse_duration(((doc.get("global") or {}).get("scrape_interval")) or "1m")
        out["scrape_default"] = default
        for job in doc.get("scrape_configs") or []:
            if isinstance(job, dict) and job.get("job_name"):
                out["scrape"][str(job["job_name"])] = (parse_duration(job.get("scrape_interval"))
                                                       or default)
    _CACHE[key] = (now, out)
    return out


def catalogue(list_name: str, client, rng: dict, now: float) -> dict:
    """The metrics Prometheus holds over the range (its `__name__` values) and each one's
    metadata (help, type, unit; remembered an hour). ``{"state", "error", "names", "meta",
    "read_at"}``."""
    names, err = _json(client, "api/v1/label/__name__/values",
                       start=str(int(rng["start"])), end=str(int(rng["end"])))
    if err:
        return {"state": "error", "error": err, "names": [], "meta": {}, "read_at": iso(now)}
    key = ("meta", list_name)
    got = _CACHE.get(key)
    if got and now - got[0] < REMEMBER:
        meta = got[1]
    else:
        data, err = _json(client, "api/v1/metadata")
        meta = {}
        if not err:
            for name, entries in (data or {}).items():
                if isinstance(entries, list) and entries and isinstance(entries[0], dict):
                    meta[name] = entries[0]
            _CACHE[key] = (now, meta)
    return {"state": "ok", "error": "", "read_at": iso(now),
            "names": sorted(n for n in names or [] if isinstance(n, str) and _NAME.match(n)),
            "meta": meta}


def _base(name: str) -> str:
    return re.sub(r"_(?:bucket|count|sum|total)$", "", name)


def kind_of(name: str, meta: dict) -> str:
    """The metric's type as Prometheus's metadata gives it: counter, gauge, histogram, summary
    or unknown. A histogram's or summary's `_count`, `_sum` and `_bucket` are counters."""
    m = meta.get(name)
    if m:
        return m.get("type") or "unknown"
    base = meta.get(_base(name))
    if base and base.get("type") in ("histogram", "summary"):
        return "counter"
    return "unknown"


def help_of(name: str, meta: dict) -> str:
    m = meta.get(name) or meta.get(_base(name)) or {}
    return _OID_TAIL.sub("", str(m.get("help") or "")).strip()


def unit_of(name: str, meta: dict) -> tuple:
    """``(unit, where)``: bytes or seconds, from Prometheus's metadata `unit`, else the name's
    suffix, else an octet named in the name or the help (SNMP's word for a byte); ("", "")
    when none says."""
    m = meta.get(name) or {}
    u = str(m.get("unit") or "")
    if u in ("bytes", "seconds"):
        return u, "Prometheus's metadata"
    if re.search(r"_bytes(?:_total)?$", name):
        return "bytes", "its name"
    if re.search(r"_seconds(?:_total|_count|_sum)?$", name):
        return "seconds", "its name"
    if re.search(r"octet", name + " " + help_of(name, meta), re.I):
        return "bytes", "an octet in its name or help, SNMP's word for a byte"
    return "", ""


def search(cat: dict, text: str, chosen: str) -> dict:
    """The metrics matching *text* (in the name or the help, any case), the chosen one first:
    ``{"rows": [(name, help, kind, unit)], "total"}``, at most `PICK` drawn."""
    names, meta = cat.get("names") or [], cat.get("meta") or {}
    want = (text or "").strip().lower()
    hits = [n for n in names if not want or want in n.lower()
            or want in help_of(n, meta).lower()]
    # A name holding the words first, then one whose help does; within each, a metric whose
    # type Prometheus states before one it does not, then by name.
    hits.sort(key=lambda n: (want not in n.lower(), kind_of(n, meta) == "unknown", n))
    ordered = ([chosen] if chosen in hits else []) + [n for n in hits if n != chosen]
    rows = [(n, help_of(n, meta), kind_of(n, meta), unit_of(n, meta)[0])
            for n in ordered[:PICK]]
    return {"rows": rows, "total": len(hits)}


def labels_of(list_name: str, client, metric: str, rng: dict, extra=()) -> dict:
    """The labels *metric* carries over the range, and the values of the ones the builder
    offers (device, role, the interface label, job, and *extra*). ``{"state", "error",
    "labels", "values": {label: [..]}, "iface"}``."""
    span = {"start": str(int(rng["start"])), "end": str(int(rng["end"]))}
    match = {"match[]": "{__name__=" + string(metric) + "}"}
    labels, err = _json(client, "api/v1/labels", **match, **span)
    if err:
        return {"state": "error", "error": err, "labels": [], "values": {}, "iface": ""}
    held = sorted(l for l in labels or [] if isinstance(l, str) and _LABEL.match(l)
                  and l != "__name__")
    iface = next((l for l in INTERFACE_LABELS if l in held), "")
    out = {"state": "ok", "error": "", "labels": held, "values": {}, "iface": iface}
    for name in dict.fromkeys([DEVICE_LABEL, ROLE_LABEL, iface, "job", *extra]):
        if name and name in held:
            vals, err = _json(client, f"api/v1/label/{name}/values", **match, **span)
            if err:
                return dict(out, state="error", error=err)
            out["values"][name] = sorted(v for v in vals or [] if isinstance(v, str))
    return out


def instant_count(client, expr: str, at: float):
    """How many series *expr* answers at *at* (one instant `count(…)`), or None."""
    data, err = _json(client, "api/v1/query", query=f"count({expr})", time=str(int(at)))
    if err:
        return None
    try:
        res = (data or {}).get("result") or []
        return int(float(res[0]["value"][1])) if res else 0
    except (KeyError, IndexError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------- the query

def check_ops(spec: dict, kind: str, unit: str, labels: list) -> tuple:
    """``(ops, errors, notes)``: the chain the metric can take. The counter rule puts a rate
    first where a counter has none; a rate of a gauge, × 8 of what is not bytes, per minute
    before a rate, and a group by a label the series no longer carry are each left out and
    said."""
    errors, notes, ops = [], [], []
    tokens = list(spec["op"])
    first = parse_op(tokens[0]) if tokens else None
    if kind == "counter" and not (first and first[0] in RANGE_OPS):
        tokens.insert(0, "rate:5m")
        notes.append(f"{spec['m']} is a counter (Prometheus's metadata says so), so the first "
                     "step is a rate or an increase, never its raw value: rate over 5 minutes "
                     "is put first")
    held, rated = set(labels), False
    for i, token in enumerate(tokens):
        k, arg = parse_op(token)
        if k in RANGE_OPS:
            if i != 0:
                errors.append(f"{RANGE_OPS[k]} applies to the metric itself, so it is the "
                              "first operation; it was not")
                continue
            if kind == "gauge":
                errors.append(f"{spec['m']} is a gauge (Prometheus's metadata says so): a "
                              f"{k} is for counters, so it is left out")
                continue
            rated = True
        elif k == "bits" and unit != "bytes":
            errors.append(f"× 8 turns bytes into bits, and {spec['m']} is not counted in bytes")
            continue
        elif k == "per_min" and not rated:
            errors.append("per minute turns a per-second rate into a per-minute one: put a "
                          "rate first")
            continue
        elif k in AGGS:
            if arg and arg not in held:
                errors.append(f"the series hold no label {arg!r} at that step, so {k} by "
                              f"{arg} is left out")
                continue
            held = {arg} if arg else set()
        ops.append(op_token(k, arg))
    return ops, errors, notes


def op_rows(ops: list, kind: str, unit: str, labels: list) -> tuple:
    """``(rows, menu)``: each operation as the Operations row draws it (its kind and argument,
    the kinds and arguments it may change to, and whether it may be removed: a counter's rate
    may not), and what + operation may add next."""
    rows, held, rated = [], set(labels), False
    for i, token in enumerate(ops, 1):
        k, arg = parse_op(token)
        if k in RANGE_OPS:
            group, kinds, args = "range", list(RANGE_OPS), list(WINDOWS)
            rated = True
        elif k in UNIT_OPS:
            group, args = "unit", []
            kinds = [x for x in UNIT_OPS if x == k or (x == "bits" and unit == "bytes")
                     or (x == "per_min" and rated)]
        elif k in AGGS:
            group, kinds, args = "agg", list(AGGS), [""] + sorted(held)
            held = {arg} if arg else set()
        else:
            group, kinds, args = "cmp", list(COMPARE), []
        rows.append({"i": i, "kind": k, "arg": arg, "group": group, "kinds": kinds, "args": args,
                     "removable": not (i == 1 and group == "range" and kind == "counter")})
    first = parse_op(ops[0])[0] if ops else ""
    menu = {"range": first not in RANGE_OPS and kind != "gauge",
            "bits": unit == "bytes" and "bits" not in ops,
            "per_min": rated and "per_min" not in ops, "full": len(ops) >= MAX_OPS}
    return rows, menu


def _unit_after(unit: str, ops: list) -> tuple:
    """``(words, chart unit)`` of the answer: the unit followed through the chain."""
    per = ""
    for token in ops:
        k, arg = parse_op(token)
        if k == "rate":
            per = "second"
        elif k == "increase":
            per = WINDOWS[arg][0]
        elif k == "bits" and unit == "bytes":
            unit = "bits"
        elif k == "per_min":
            per = "minute"
        elif k == "count":
            unit, per = "series", ""
    words = (unit or "") + (f" per {per}" if per else "")
    words = words.strip() or "as Prometheus holds it (no unit stated)"
    chart = {("bits", "second"): "bps", ("bytes", "second"): "Bps", ("bytes", ""): "bytes",
             ("seconds", ""): "s"}.get((unit, per), "")
    return words, chart


def build(spec: dict, kind: str, unit: str, iface: str, ops: list, meta_help: str = "") -> dict:
    """The query the choices form: ``{"parts": [(text, key)], "query", "selector",
    "explain": {key: words}, "reads", "unit_words", "chart_unit"}``. Each value is one token
    (`string`, or an alternation of literals); every name is the caller's to have checked."""
    metric = spec["m"]
    explain, reads = {}, []
    explain["what"] = f"asks {metric}" + (f": {meta_help}" if meta_help else "")
    sel, keys = [], []
    if spec["dev"]:
        sel.append(matcher(DEVICE_LABEL, spec["dev"]))
        keys.append("dev")
        names = " and ".join(spec["dev"][:3]) + (f" and {len(spec['dev']) - 3} more"
                                                  if len(spec["dev"]) > 3 else "")
        explain["dev"] = f"keeps the series whose {DEVICE_LABEL} label is {names}"
        reads.append(f"from {names}")
    if spec["role"]:
        sel.append(matcher(ROLE_LABEL, [spec["role"]]))
        keys.append("dev")
        explain["dev"] = (explain.get("dev", "") + "; " if spec["dev"] else "") + \
            f"keeps the series whose {ROLE_LABEL} label is {spec['role']}"
        reads.append(f"of the {spec['role']} role")
    if spec["if"] and iface:
        sel.append(matcher(iface, spec["if"]))
        keys.append("if")
        explain["if"] = f"keeps the series whose {iface} is " + " or ".join(spec["if"])
        reads.append(f"on {' or '.join(spec['if'])}")
    for i, token in enumerate(spec["f"], 1):
        label, op, value = parse_filter(token)
        sel.append(f"{label}{op}{string(value)}")
        keys.append(f"f{i}")
        how = FILTER_OPS[op] + (" (anchored at both ends)" if "~" in op else "")
        explain[f"f{i}"] = f'keeps the series whose {label} {how} "{value}"'
        reads.append(f'whose {label} {FILTER_OPS[op]} "{value}"')
    selector = metric + ("{" + ", ".join(sel) + "}" if sel else "")
    parts = [(metric, "what")]
    if sel:
        parts.append(("{", ""))
        for n, (text, key) in enumerate(zip(sel, keys)):
            parts.append((text + (", " if n < len(sel) - 1 else ""), key))
        parts.append(("}", ""))
    words = [f"{metric}" + (f" ({meta_help})" if meta_help else "")] + reads
    prec = 9                                       # an atom: a selector, a call, a group
    for i, token in enumerate(ops, 1):
        k, arg = parse_op(token)
        key = f"op{i}"
        if k in RANGE_OPS:
            parts = [(f"{k}(", key)] + parts + [(f"[{arg}])", key)]
            w = WINDOWS[arg][0]
            explain[key] = (f"turns the counter into a per-second rate over {w}" if k == "rate"
                            else f"is the counter's increase over each {w}")
            words.append(f"as a per-second rate over {w}" if k == "rate"
                         else f"as its increase over each {w}")
            prec = 9
        elif k in UNIT_OPS:
            if prec < 5:
                parts = [("(", "")] + parts + [(")", "")]
            n = "8" if k == "bits" else "60"
            parts = parts + [(f" * {n}", key)]
            explain[key] = ("multiplies by 8, bytes to bits" if k == "bits"
                            else "multiplies by 60, per second to per minute")
            words.append("× 8 for bits" if k == "bits" else "× 60 for per minute")
            prec = 5
        elif k in COMPARE:
            if prec < 5:
                parts = [("(", "")] + parts + [(")", "")]
            sym, w = COMPARE[k]
            parts = parts + [(f" {sym} {arg}", key)]
            explain[key] = (f"keeps only the values {w} {arg}: a series is left out at each "
                            "step where it is not")
            words.append(f"only where the value is {w} {arg}")
            prec = 3
        else:
            # The group's own words marked, never the parenthesis that opens its argument.
            head, opener = (f"{k} by ({arg})", " (") if arg else (k, "(")
            parts = [(head, key), (opener, "")] + parts + [(")", "")]
            per = f"one line per {arg}" if arg else "one line"
            explain[key] = f"{AGG_WORDS[k][0]} {per}"
            words.append(f"{AGG_WORDS[k][1]} {per}")
            prec = 9
    if spec["top"]:
        parts = [(f"topk({spec['top']}, ", "top")] + parts + [(")", "")]
        explain["top"] = (f"keeps the {spec['top']} highest series at each step (topk), so "
                          f"over a range more than {spec['top']} can appear")
        words.append(f"the {spec['top']} highest at each step")
    unit_words, chart_unit = _unit_after(unit, ops)
    query = "".join(t for t, _k in parts)
    return {"parts": parts, "query": query, "selector": selector, "explain": explain,
            "reads": ", ".join(words) + f"; in {unit_words}", "unit_words": unit_words,
            "chart_unit": chart_unit}


# ---------------------------------------------------------------------------- the answer

def _trim(n: float) -> str:
    a = abs(n)
    if a >= 100 or a == 0:
        return str(int(math.floor(n + 0.5)))
    if a >= 10:
        return str(math.floor(n * 10 + 0.5) / 10).rstrip("0").rstrip(".")
    return str(math.floor(n * 100 + 0.5) / 100).rstrip("0").rstrip(".")


def fmt_value(v, unit: str) -> str:
    """One value in the answer's unit, as the chart writes it (nmas_panels.js formatValue):
    "4.9 Mb/s", "1.65 MB", "12"."""
    if v is None:
        return "—"
    scaled = _trim(v)
    for size, prefix in ((1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k")):
        if abs(v) >= size:
            scaled = _trim(v / size) + " " + prefix
            break
    suffix = {"bps": "b/s", "Bps": "B/s", "bytes": "B"}.get(unit)
    if unit == "s":
        return _trim(v) + " s"
    if suffix:
        return scaled + ("" if " " in scaled else " ") + suffix
    return scaled


def _float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _series_label(metric: dict, varying: list) -> str:
    shown = [f'{k}="{metric.get(k, "")}"' for k in varying if k in metric]
    return ", ".join(shown) or "the one series"


def refusals(spec: dict, built: dict, rng: dict, step: int, lim: dict, jobs: list,
             counts: dict) -> list:
    """``[(words, [(label, over)])]``: each bound the ask passes, both operands named, with the
    choice that fits. *counts* holds the instant counts asked first: ``{"selector": n,
    "answer": n}``."""
    from modules import panels

    out = []
    ops = [parse_op(t) for t in spec["op"]]
    win = next((WINDOWS[a][1] for k, a in ops if k in RANGE_OPS), 0)
    longest = max((lim.get("scrape") or {}).get(j) or lim.get("scrape_default") or 0
                  for j in jobs) if jobs else 0
    if win and longest and win < 2 * longest:
        fit = next((k for k, (_w, s) in WINDOWS.items() if s >= 2 * longest), None)
        idx = next(i for i, (k, _a) in enumerate(ops) if k in RANGE_OPS)
        k, _a = ops[idx]
        fixed = list(spec["op"])
        if fit:
            fixed[idx] = op_token(k, fit)
        out.append((f"Refused: a {k} needs two samples in each window, and the slowest job "
                    f"this metric comes from is scraped every {duration_words(longest)} (its "
                    f"scrape_interval). A window of {duration_words(win)} is shorter than two "
                    f"scrapes, {duration_words(2 * longest)}.",
                    [(f"{k.capitalize()} over {WINDOWS[fit][0]}", {"op": fixed})] if fit
                    else []))
    points = int(rng["seconds"] // step) + 1
    per = max(1, win // longest) if win and longest else 1
    most = (lim.get("query.max-samples") or {}).get("n")
    sel = counts.get("selector")
    if most and sel is not None and sel * points * per > most:
        out.append((f"Refused: one ask loads at most {most:,} samples (Prometheus's "
                    f"query.max-samples). This ask loads at least {sel * points * per:,} "
                    f"({sel:,} series × {points:,} points"
                    + (f" × {per} samples a window" if per > 1 else "") + ").",
                    [("Narrow to the last 24 h", {"range": "24h", "within": "", "from": "",
                                                  "to": ""})]
                    if rng["seconds"] > 86400 else []))
    n = counts.get("answer")
    if n is not None and n > panels.MAX_SERIES:
        out.append((f"Refused: at most {panels.MAX_SERIES} series an answer (Mercury's bound). "
                    f"This query answers {n:,} series at the range's end.",
                    [] if spec["top"] == "10" else [("Only the top 10", {"top": "10"})]))
    return out


def answer(client, built: dict, rng: dict, step: int, now: float) -> dict:
    """The series over the range: each one's label, its values on the step's grid, its value
    now and its highest and lowest; the `DRAWN` highest drawn, the rest counted."""
    t0 = time.time()
    data, err = _json(client, "api/v1/query_range", query=built["query"],
                      start=str(int(rng["start"])), end=str(int(rng["end"])), step=str(step))
    took = int((time.time() - t0) * 1000)
    if err:
        return {"state": "error", "error": err, "asked_at": iso(now)}
    if (data or {}).get("resultType") != "matrix":
        return {"state": "error", "asked_at": iso(now),
                "error": f"Prometheus answered {(data or {}).get('resultType')}, not series"}
    grid = list(range(int(rng["start"]), int(rng["end"]) + 1, step))
    result = (data or {}).get("result") or []
    keys = sorted({k for r in result for k in (r.get("metric") or {}) if k != "__name__"})
    varying = [k for k in keys
               if len({(r.get("metric") or {}).get(k) for r in result}) > 1] or keys
    first = [DEVICE_LABEL, *INTERFACE_LABELS, ROLE_LABEL]
    varying = sorted(varying, key=lambda k: (first.index(k) if k in first else 9, k))
    series = []
    for r in result:
        got = {}
        for ts, v in r.get("values") or []:
            got[int(float(ts))] = _float(v)
        vals = [got.get(g) for g in grid]
        present = [v for v in vals if v is not None]
        series.append({"label": _series_label(r.get("metric") or {}, varying), "values": vals,
                       "now": vals[-1] if vals else None,
                       "high": max(present) if present else None,
                       "low": min(present) if present else None})
    series.sort(key=lambda s: (-(s["high"] if s["high"] is not None else -math.inf), s["label"]))
    shown = series[:DRAWN]
    unit = built["chart_unit"]
    for s in shown:
        s["now_words"], s["high_words"], s["low_words"] = (
            fmt_value(s["now"], unit), fmt_value(s["high"], unit), fmt_value(s["low"], unit))
    payload = {"ok": True, "type": "timeseries", "legend_off": True, "title": "",
               "unit": unit, "range": rng["words"].replace("the last ", ""), "step": step,
               "read_at": iso(now), "asked": [built["query"]],
               "series": [{"label": s["label"], "times": grid, "values": s["values"]}
                          for s in shown],
               "note": (f"{len(series)} series: the {DRAWN} highest are drawn"
                        if len(series) > DRAWN else "")}
    return {"state": "ok" if any(s["high"] is not None for s in series) else "empty",
            "series": shown, "series_total": len(series), "payload": payload, "took_ms": took,
            "read_at": iso(now), "end_words": utc(grid[-1], "%H:%M") if grid else ""}


# ---------------------------------------------------------------------------- the view

def _probe(list_name: str) -> dict:
    """What the integrations probe last said of Prometheus: ``{"state", "at"}`` or {}."""
    from modules import reader_job
    try:
        got = reader_job.read_cached_for("integrations", list_name)
    except Exception:                                 # noqa: BLE001
        return {}
    good = ((got.get("doc") or {}).get("last_good") or {})
    for i in ((good.get("value") or {}).get("integrations") or []):
        if i.get("name") == "prometheus":
            return {"state": i.get("state", ""), "at": good.get("value_at", "")}
    return {}


def _stores(list_name: str) -> dict:
    """The network's PromQL stores as Code mode reads them (panels.stores, from Grafana's data
    sources as last read; no I/O): how long the live store keeps, and the long-term store past
    it, or why there is none. The builder itself asks Prometheus."""
    from modules import history_query, panels
    try:
        _client_, datasources, err = history_query._grafana(list_name)  # noqa: SLF001
        if err:
            return {"error": err, "history": "", "why": ""}
        st = panels.stores(datasources, list_name)
    except Exception as exc:                          # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "history": "", "why": ""}
    return {"error": "", "history": (st.history or {}).get("name", ""), "why": st.why,
            "live_days": st.live // 86400}


def _loki_limits(list_name: str, now: float) -> dict:
    """The logs builder's bounds (modules/history_logq.limits, Loki's /config, remembered an
    hour), drawn in the same limits table; {} when no Loki is configured."""
    from modules import history_logq
    client = history_logq._client(list_name, 15.0)   # noqa: SLF001
    if not client.is_configured():
        return {}
    lim = history_logq.limits(list_name, client=client, now=now)
    for item in lim.values():
        if isinstance(item, dict) and "seconds" in item:
            item["words"] = duration_words(item["seconds"])
    return lim


def saved(list_name: str) -> dict:
    """The network's saved views (modules/saved_views.py) as the Saved queries list draws them:
    each one's title, language, the query where its address holds it, and its pin."""
    from urllib.parse import parse_qsl, urlsplit

    from modules import saved_views
    try:
        got = saved_views.read(list_name)
    except Exception as exc:                          # noqa: BLE001
        return {"state": "unreadable", "error": str(exc), "rows": []}
    rows = []
    for v in got.get("views") or []:
        parts = urlsplit(v.get("address") or "")
        args = parse_qsl(parts.query)
        one = dict(args)
        if parts.path == PAGE_PATH:
            lang = "PromQL"
            spec, _e = ask({k: [x for kk, x in args if kk == k] if k in LISTS else one.get(k)
                            for k in DEFAULTS})
            # The address holds the whole question but the interface label's name, which
            # only Prometheus can say: such a view is drawn by its title alone.
            code = (build(spec, "", "", "", spec["op"])["query"]
                    if spec["m"] and not spec["if"] else "")
        elif parts.path.endswith("/ask/logs"):
            lang, code = "LogQL", ""
        elif one.get("lang") == "logql" or parts.path.endswith("/syslog"):
            lang, code = "LogQL", one.get("q", "")
        else:
            lang, code = "PromQL", one.get("q", "")
        rows.append({"title": v.get("title", ""), "address": v.get("address", ""),
                     "lang": lang, "code": code, "pinned": bool(v.get("pinned"))})
    return {"state": got.get("state", "ok"), "error": got.get("error", ""), "rows": rows}


def view(list_name: str, values, now: float = None, client=None) -> dict:
    """Everything board E3 draws for one network and the choices in the address."""
    from modules import panels

    now = _now() if now is None else now
    spec, errors = ask(values)
    rng = window(spec, now)
    if rng["error"]:
        errors.append(rng["error"])
    step = panels.step_for(int(rng["seconds"]))
    probe = client or _client(list_name, 15.0)
    configured = probe.is_configured()
    lim = limits(list_name, probe, now) if configured else {}
    # The wait is Prometheus's own query.timeout and 5 s (its default, 2 min, when not read).
    wait = ((lim.get("query.timeout") or {}).get("seconds") or (DEFAULT_WAIT - 5)) + 5
    client = client or _client(list_name, wait)
    out = {"list": list_name, "s": spec, "errors": errors, "notes": [], "range": rng,
           "limits": lim, "step": step, "step_words": duration_words(step),
           "points": int(rng["seconds"] // step) + 1, "ranges": RANGES, "windows": WINDOWS,
           "presets": PRESETS, "range_ops": RANGE_OPS, "unit_ops": UNIT_OPS, "aggs": AGGS,
           "compare": COMPARE, "filter_ops": FILTER_OPS, "tops": TOPS, "drawn": DRAWN,
           "max_points": panels.MAX_POINTS, "max_series": panels.MAX_SERIES,
           "ladder": [(RANGES[k][0], duration_words(panels.step_for(s)))
                      for k, (_w, s) in RANGES.items()],
           "chips": CHIPS, "now": iso(now), "now_ts": now, "answer": None, "state": "ok",
           "error": "", "qs": lambda over=None: qs(spec, list_name, over),
           "preset_qs": lambda params: qs(spec, list_name, preset_over(params)),
           "range_words": duration_words(rng["seconds"]), "saved": saved(list_name),
           "cat": {"names": [], "meta": {}, "state": ""}, "pick": {"rows": [], "total": 0},
           "presets_held": {}, "kind": "", "unit": "", "unit_where": "", "help": "",
           "disc": {"labels": [], "values": {}, "iface": "", "state": ""}, "built": None,
           "fe_count": None, "op_rows": [], "menu": {}}
    for item in lim.values():
        if isinstance(item, dict) and "seconds" in item:
            item["words"] = duration_words(item["seconds"])
    out["stores"], out["loki"] = _stores(list_name), _loki_limits(list_name, now)
    out["kept"] = (lim.get("storage.tsdb.retention.time") or {}).get("seconds")
    out["kept_words"] = duration_words(out["kept"]) if out["kept"] else ""
    out["kept_from"] = now - out["kept"] if out["kept"] else None
    if not configured:
        out.update(state="not_configured", cat={"names": [], "meta": {}, "state": "error"},
                   error="no metrics store is configured for this network (its Prometheus "
                         "card in Settings)")
        return _finish(out, spec)
    cat = catalogue(list_name, client, rng, now)
    out["cat"] = cat
    if cat["state"] != "ok":
        out.update(state="error", error=cat["error"])
        return _finish(out, spec)
    names = set(cat["names"])
    out["presets_held"] = {k: p["m"] in names for k, _t, _a, p in PRESETS}
    if spec["m"] and spec["m"] not in names:
        errors.append(f"Prometheus holds no metric {spec['m']!r} over {rng['words']}")
        spec["m"] = ""
    out["pick"] = search(cat, spec["mq"], spec["m"])
    if not spec["m"]:
        return _finish(out, spec)
    meta = cat["meta"]
    out["kind"] = kind = kind_of(spec["m"], meta)
    out["unit"], out["unit_where"] = unit_of(spec["m"], meta)
    out["help"] = help_of(spec["m"], meta)
    extra = (spec["fl"],) if spec["fe"] and spec["fl"] else ()
    disc = labels_of(list_name, client, spec["m"], rng, extra)
    out["disc"] = disc
    if disc["state"] != "ok":
        out.update(state="error", error=disc["error"])
        return _finish(out, spec)
    held = set(disc["labels"])
    for key, label in (("dev", DEVICE_LABEL), ("role", ROLE_LABEL)):
        if spec[key] and label not in held:
            errors.append(f"{spec['m']} carries no {label} label over {rng['words']}, so "
                          f"the {label} chosen is left out")
            spec[key] = [] if key == "dev" else ""
    if spec["if"] and not disc["iface"]:
        errors.append(f"{spec['m']} carries no interface label ({', '.join(INTERFACE_LABELS)})"
                      ", so the interfaces chosen are left out")
        spec["if"] = []
    kept = []
    for token in spec["f"]:
        label, _op, _v = parse_filter(token)
        if label not in held:
            errors.append(f"{spec['m']} carries no label {label!r} over {rng['words']}, so "
                          "that filter is left out")
            continue
        kept.append(token)
    spec["f"] = kept
    if spec["fl"] and spec["fl"] not in held:
        spec["fl"] = ""
    ops, op_errors, notes = check_ops(spec, kind, out["unit"], disc["labels"])
    spec["op"] = ops
    errors.extend(op_errors)
    out["notes"] = notes
    out["op_rows"], out["menu"] = op_rows(ops, kind, out["unit"], disc["labels"])
    built = build(spec, kind, out["unit"], disc["iface"], ops, out["help"])
    built["explain"]["range"] = (f"the range is not part of the query: Prometheus is asked for "
                                 f"{rng['words']}, a point every {out['step_words']}")
    built["explain"]["start"] = "the Start-from chip set every choice below"
    out["built"] = built
    # The open filter editor: how many series the filter being written keeps or leaves out.
    if spec["fe"] and spec["fl"] and spec["fo"] and spec["fv"]:
        op = spec["fo"]
        inverse = {"!=": "=", "!~": "=~"}.get(op, op)
        sel = built["selector"]
        extra_m = f"{spec['fl']}{inverse}{string(spec['fv'])}"
        probe_sel = (sel[:-1] + ", " + extra_m + "}") if sel.endswith("}") else \
            sel + "{" + extra_m + "}"
        n = instant_count(client, probe_sel, rng["end"])
        out["fe_count"] = (n, "leave out" if op in ("!=", "!~") else "keep")
    return _finish(out, spec, client=client, lim=lim, disc=disc)


def _finish(out: dict, spec: dict, client=None, lim=None, disc=None) -> dict:
    """The answer's title, the code mode's range, and, asked, the answer."""
    rng, now = out["range"], out["now"]
    out["preset_on"] = preset_on(spec) if spec["m"] else ""
    title = next((a for k, _t, a, _p in PRESETS if k == out["preset_on"]), "") or spec["m"]
    built = out.get("built")
    if built:
        title = f"{title}, in {built['unit_words']}" if built["unit_words"][0].isalpha() and \
            "no unit" not in built["unit_words"] else title
    out["answer_title"] = f"{title}, {utc(rng['start'])} to {utc(rng['end'])} UTC"
    out["between"] = (f"{utc(rng['start'], '%-d %b %Y %H:%M')} and "
                      f"{utc(rng['end'], '%-d %b %Y %H:%M')} UTC")
    secs = rng["seconds"]
    out["code_range"] = ("24h" if secs <= 86400 else "7d" if secs <= 7 * 86400 else
                         "30d" if secs <= 30 * 86400 else "180d")
    if spec["ask"] != "1":
        return out
    if out["state"] != "ok":
        probe = _probe(out["list"])
        out["answer"] = {"state": "error", "error": out["error"], "asked_at": now,
                         "probe": probe}
        if out["state"] == "not_configured":
            out["answer"] = None
        return out
    if out["errors"] or not built:
        out["answer"] = {"state": "refused", "asked_at": now,
                         "refusals": [(e, []) for e in out["errors"]] or
                         [("Nothing is asked yet: choose what to ask", [])]}
        return out
    step = out["step"]
    counts = {"selector": instant_count(client, built["selector"], rng["end"]),
              "answer": instant_count(client, built["query"], rng["end"])}
    jobs = disc["values"].get("job") or []
    refused = refusals(spec, built, rng, step, lim, jobs, counts)
    if refused:
        out["answer"] = {"state": "refused", "refusals": refused, "asked_at": now}
        return out
    ans = answer(client, built, rng, step, out["now_ts"])
    if ans["state"] == "error":
        ans["probe"] = _probe(out["list"])
    kept_from = out["kept_from"]
    ans["inside_kept"] = bool(kept_from) and rng["start"] >= kept_from
    ans["kept_from_words"] = utc(kept_from, "%-d %b %Y %H:%M UTC") if kept_from else ""
    if kept_from and rng["start"] < kept_from:
        start = int(-(-kept_from // 3600) * 3600)
        ans["start_at"] = {"words": utc(start, "%-d %b"), "over": {
            "range": "custom", "within": "", "from": utc(start, "%Y-%m-%d %H:%M"),
            "to": utc(rng["end"], "%Y-%m-%d %H:%M"), "ask": "1", "hl": "range"}}
    out["answer"] = ans
    return out
