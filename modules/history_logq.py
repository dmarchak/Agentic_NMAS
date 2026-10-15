"""History › Query › Ask your own, the LOGS builder (board F3, `QueryBuilderLogs3.dc.html` and
its phone board, approved by the operator 2026-10-15; compared region by region in
docs/fidelity/history-ask-logs.md).

A person builds a LogQL question by choosing, never by typing LogQL: the kinds (Loki's `job`
label values), the devices, a severity at or worse than, mnemonics, text the line contains or
excludes, lines or counts over time, and a range. Mercury forms the query from those choices
and draws it as it forms, the last choice highlighted and said in plain words; Ask sends it.

**Discovered, never assumed.** Every label name and value the builder offers is read from Loki
for the range (its label and label-values APIs, through the Loki integration client): the jobs,
the devices, whether a `severity` label exists. A label is used only over the part of time it
covers: each label's first line is measured (`first_labelled`), and a range starting before it
matches by the line instead (a device by its own name before the timestamp, a severity by the
digit in the line's mnemonic), said in the query's words. Loki's own bounds (its longest ask,
its timeout, its retention) are read from its /config and named where they refuse.

**One token each.** A value from the address reaches Loki only inside a string Mercury quotes
(`string`): a quote, a backslash, a newline or any control character is escaped, so it can
never end the string or add a stage; a value inside a pattern is escaped as a literal first
(`literal`). A label NAME cannot be quoted, so a count's `by` is a discovered label or refused.

**A read.** Nothing is written and no list is created; the answer is masked like every other
log line Mercury shows (`redact_text`), and a line's time is when the collector received it.
"""

import logging
import re
import time

from modules import history_ask
# What the two builders share (board E3's and this one's): one token each, durations, the
# range and the address, in modules/history_ask.py.
from modules.history_ask import (REMEMBER, alternation, duration_words, literal,  # noqa: F401
                                 parse_duration, string)
from modules.history_ask import iso as _iso, matcher as _matcher  # noqa: F401
from modules.history_ask import utc as _utc, when as _when  # noqa: F401

log = logging.getLogger(__name__)

#: Mercury's own bounds: lines a page, windows a series, series drawn.
PAGE = 200
MAX_WINDOWS = 1000
MAX_SERIES = 20
#: The ranges the chips offer: key -> (words, seconds).
RANGES = {"1h": ("1 h", 3600), "24h": ("24 h", 86400), "7d": ("7 days", 7 * 86400),
          "30d": ("30 days", 30 * 86400)}
#: A count's windows: key -> (words, seconds, LogQL duration).
WINDOWS = {"1m": ("1 minute", 60, "1m"), "5m": ("5 minutes", 300, "5m"),
           "1h": ("1 hour", 3600, "1h"), "1d": ("1 day", 86400, "1d")}
#: The client's wait when Loki's own query_timeout is not read: its default, 1 minute, and 5 s.
DEFAULT_WAIT = 65.0
#: The longest text a contains/excludes filter takes, and a device or job value.
TEXT_MAX = 200
VALUE_MAX = 128

#: Start from (the board's four chips): a title and the choices it makes. The mnemonics are
#: Cisco IOS's own (the product's devices), never a lab's; every other value is discovered.
PRESETS = (
    ("links", "Interfaces going down, per device",
     {"mn": ["%LINK-3-UPDOWN"], "has": "down", "show": "counts", "by": "device", "every": "5m",
      "range": "24h"}),
    ("ospf", "OSPF adjacency changes",
     {"mn": ["%OSPF-5-ADJCHG"], "show": "counts", "by": "device", "every": "5m",
      "range": "24h"}),
    ("config", "Configuration changes, by whom",
     {"mn": ["%SYS-5-CONFIG_I"], "show": "lines", "range": "7d"}),
    ("errors", "Errors and worse, last 24 h", {"sev": "3", "show": "lines", "range": "24h"}),
)

#: Every value the address carries, and its default. Lists are the repeatable ones.
DEFAULTS = {"job": [], "dev": [], "role": "", "sev": "", "mn": [], "has": "", "not": "",
            "show": "lines", "by": "device", "every": "5m", "range": "24h", "within": "",
            "from": "", "to": "", "ask": "", "before": "", "at": "", "hl": ""}
LISTS = ("job", "dev", "mn")
#: The keys a saved view keeps (modules/saved_views.py): the question and the range, asked.
ADDRESS_KEYS = ("job", "dev", "role", "sev", "mn", "has", "not", "show", "by", "every", "range",
                "within", "from", "to", "ask")
#: The filter choices (what a preset sets or leaves at its default).
FILTERS = ("job", "dev", "role", "sev", "mn", "has", "not", "show", "by", "every", "range",
           "within", "from", "to")

_MN = re.compile(r"^%?[A-Z0-9_]+(?:-[A-Z0-9_]+)*-[0-7]-[A-Z0-9_]+$")
_LABEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_CACHE = {}


def _now() -> float:
    """The clock (one seam, so a test fixes it without fixing every clock in the process)."""
    return time.time()


def forget():
    """Drop what is remembered about Loki (its bounds, when its labels began): for tests."""
    _CACHE.clear()


# ---------------------------------------------------------------------------- the address

class Refused(ValueError):
    """A value the builder cannot carry, named."""


def ask(values) -> tuple:
    """``(spec, errors)``: the choices the address carries, each checked; a value the builder
    cannot carry is left out and said (*errors*), never passed on."""
    spec, errors = history_ask.read_values(values, DEFAULTS, LISTS), []
    for key in ("job", "dev"):
        long = [v for v in spec[key] if len(v) > VALUE_MAX]
        if long:
            errors.append(f"a {'job' if key == 'job' else 'device'} value of {len(long[0])} "
                          f"characters is longer than the {VALUE_MAX} taken")
            spec[key] = [v for v in spec[key] if len(v) <= VALUE_MAX]
    mns = []
    for v in spec["mn"]:
        if not _MN.match(v):
            errors.append(f"{v[:60]!r} is not a mnemonic (%FACILITY-SEVERITY-NAME)")
            continue
        mns.append(v if v.startswith("%") else "%" + v)
    spec["mn"] = mns
    if spec["sev"] and not re.fullmatch(r"[0-7]", spec["sev"]):
        errors.append(f"{spec['sev'][:20]!r} is not a severity (0 to 7)")
        spec["sev"] = ""
    for key in ("has", "not"):
        if len(spec[key]) > TEXT_MAX:
            errors.append(f"the text filter is {len(spec[key])} characters; at most {TEXT_MAX} "
                          "are taken")
            spec[key] = ""
    if spec["show"] not in ("lines", "counts"):
        spec["show"] = "lines"
    if spec["every"] not in WINDOWS:
        errors.append(f"{spec['every'][:20]!r} is not a window: "
                      + ", ".join(w for w, _s, _d in WINDOWS.values()))
        spec["every"] = "5m"
    if spec["by"] != "mnemonic" and not _LABEL.match(spec["by"]):
        errors.append(f"{spec['by'][:40]!r} is not a label name")
        spec["by"] = "device"
    if spec["range"] not in RANGES and spec["range"] != "custom":
        errors.append(f"{spec['range'][:20]!r} is not a range: "
                      + ", ".join(RANGES) + ", or From… to…")
        spec["range"] = "24h"
    for key in ("before", "at"):
        if spec[key] and not spec[key].isdigit():
            spec[key] = ""
    if len(spec["role"]) > VALUE_MAX:
        spec["role"] = ""
    return spec, errors


def qs(spec: dict, list_name: str = "", over: dict = None) -> str:
    """The address for *spec* with *over* applied: only what differs from the defaults."""
    return history_ask.qs(spec, DEFAULTS, LISTS, list_name, over)


def preset_over(params: dict) -> dict:
    """A Start-from chip's address: its choices, every other filter at its default."""
    over = {k: DEFAULTS[k] for k in FILTERS}
    over.update(params)
    over.update(ask="1", before="", at="", hl="start")
    return over


def preset_on(spec: dict) -> str:
    """The Start-from chip the choices are exactly, or ""."""
    for key, _title, params in PRESETS:
        want = dict({k: DEFAULTS[k] for k in FILTERS}, **params)
        mine = {k: spec.get(k) for k in FILTERS}
        if all(mine[k] == want[k] for k in FILTERS if k not in ("job", "dev", "role")):
            return key
    return ""


# ---------------------------------------------------------------------------- Loki

def _client(list_name: str, wait: float = DEFAULT_WAIT):
    from modules.integrations.loki import LokiIntegration
    return LokiIntegration(timeout=wait, list_name=list_name)


def _json(client, path: str, **params) -> tuple:
    """``(data, error)`` from one GET through the integration client."""
    r = client._get(path, **params)                  # noqa: SLF001 (the client's one GET)
    if not r.get("ok"):
        return None, _loki_words(r.get("error") or "no answer", client)
    try:
        body = r["response"].json()
    except ValueError as exc:
        return None, f"Loki's answer could not be read: {exc}"
    return (body or {}).get("data"), ""


def _loki_words(error: str, client) -> str:
    """Loki's failure in the board's words: a timeout names the wait and where it came from."""
    if error.startswith("Timed out"):
        return (f"Loki did not answer within {duration_words(max(client.timeout - 5, 1))} "
                "(its query_timeout; Mercury waits 5 s more)")
    return f"Loki: {error}"


def limits(list_name: str, client=None, now: float = None) -> dict:
    """Loki's own bounds, read from its /config (remembered an hour): the longest ask, its
    timeout, the most lines and series an ask returns, the retention. ``{"read_at", "error",
    <name>: {"text", "seconds"|"n"}}``; a bound it does not state is absent."""
    now = _now() if now is None else now
    key = ("limits", list_name)
    got = _CACHE.get(key)
    if got and now - got[0] < REMEMBER:
        return got[1]
    import yaml

    client = client or _client(list_name, 15.0)
    r = client._get("config")                          # noqa: SLF001
    out = {"read_at": _iso(now), "error": ""}
    if not r.get("ok"):
        out["error"] = f"Loki's /config could not be read: {r.get('error')}"
        return out                                     # not remembered: asked again next time
    try:
        lc = (yaml.safe_load(r["response"].text) or {}).get("limits_config") or {}
    except (yaml.YAMLError, AttributeError) as exc:
        out["error"] = f"Loki's /config could not be read: {exc}"
        return out
    for name in ("max_query_length", "query_timeout", "retention_period"):
        secs = parse_duration(lc.get(name))
        if secs is not None:
            out[name] = {"text": str(lc[name]), "seconds": secs}
    for name in ("max_entries_limit_per_query", "max_query_series"):
        if isinstance(lc.get(name), int):
            out[name] = {"text": str(lc[name]), "n": lc[name]}
    _CACHE[key] = (now, out)
    return out


def first_labelled(list_name: str, label: str, client, now: float, lookback: float) -> float:
    """When Loki's first line carrying *label* arrived, within *lookback* seconds (epoch; the
    window's start when the label is older than it, so a range before is never assumed to be
    covered), remembered an hour; None when no line carries it or Loki could not say."""
    key = ("since", list_name, label)
    got = _CACHE.get(key)
    if got and now - got[0] < REMEMBER:
        return got[1]
    start = now - lookback
    data, err = _json(client, "loki/api/v1/query_range",
                      query="{" + f"{label}=~{string('.+')}" + "}", limit=1,
                      start=str(int(start * 1e9)), end=str(int(now * 1e9)), direction="forward")
    if err:
        log.warning("history_logq: when %s began could not be asked: %s", label, err)
        return None
    stamps = [int(ns) for s in (data or {}).get("result") or [] for ns, _l in s.get("values") or []]
    since = max(min(stamps) / 1e9, start) if stamps else None
    _CACHE[key] = (now, since)
    return since


def discover(list_name: str, start: float, end: float, client=None, now: float = None) -> dict:
    """What Loki holds over the range: its label names, the values of the job and device labels,
    whether it carries `severity`, and when each of device and severity began. ``{"state":
    "ok"|"not_configured"|"error", ...}``."""
    now = _now() if now is None else now
    client = client or _client(list_name)
    out = {"state": "ok", "error": "", "labels": [], "values": {"job": [], "device": []},
           "since": {}, "read_at": _iso(now)}
    if not client.is_configured():
        return dict(out, state="not_configured",
                    error="no log store is configured for this network (its Loki card in "
                          "Settings)")
    window = {"start": str(int(start * 1e9)), "end": str(int(end * 1e9))}
    labels, err = _json(client, "loki/api/v1/labels", **window)
    if err:
        return dict(out, state="error", error=err)
    out["labels"] = sorted(l for l in labels or [] if isinstance(l, str) and _LABEL.match(l))
    for name in ("job", "device"):
        if name in out["labels"]:
            vals, err = _json(client, f"loki/api/v1/label/{name}/values", **window)
            if err:
                return dict(out, state="error", error=err)
            out["values"][name] = sorted(v for v in vals or [] if isinstance(v, str))
    lim = limits(list_name, now=now)
    span = (lim.get("max_query_length") or {}).get("seconds") or 30 * 86400
    for name in ("device", "severity"):
        if name in out["labels"]:
            out["since"][name] = first_labelled(list_name, name, client, now, span)
    return out


# ---------------------------------------------------------------------------- the range

def window(spec: dict, now: float) -> dict:
    """``{start, end, seconds, words, error}``: the range asked, to the minute (the chips
    `RANGES`, the last so many, or From… to…; history_ask.window)."""
    return history_ask.window(spec, now, RANGES)


# ---------------------------------------------------------------------------- the query

def _devices_of_role(list_name: str, role: str) -> list:
    from modules.device import load_saved_devices
    from modules.nsot import listref
    try:
        rows = load_saved_devices(listref.resolve(list_name).csv_path)
    except Exception as exc:                          # noqa: BLE001
        log.warning("history_logq: %s's inventory could not be read: %s", list_name, exc)
        return []
    return sorted(d.get("hostname", "") for d in rows
                  if d.get("hostname") and (d.get("role") or "") == role)


def roles(list_name: str) -> list:
    """The roles the network's devices carry, each with how many (the inventory, no I/O)."""
    from modules.device import load_saved_devices
    from modules.nsot import listref
    try:
        rows = load_saved_devices(listref.resolve(list_name).csv_path)
    except Exception:                                 # noqa: BLE001
        return []
    out = {}
    for d in rows:
        if d.get("role"):
            out[d["role"]] = out.get(d["role"], 0) + 1
    return sorted(out.items())


def build(spec: dict, disc: dict, rng: dict, devices: list) -> dict:
    """The query the choices form: ``{"parts": [(text, key)], "query", "log_query", "explain":
    {key: words}, "reads", "by_label", "notes"}``. Each value is one token (`string`)."""
    labels = set(disc.get("labels") or [])
    since = disc.get("since") or {}
    sel, pipe, explain, reads, notes = [], [], {}, [], []
    jobs = spec["job"]
    sel.append((_matcher("job", jobs) if jobs else f"job=~{string('.+')}", "job"))
    jw = " and ".join(jobs) if jobs else "every job"
    explain["job"] = (f"keeps the lines of {'the job' if len(jobs) == 1 else 'the jobs'} {jw}"
                      if jobs else "asks every job Loki holds (a selector needs one label)")
    reads.append(f"lines of {jw}" if jobs else "lines of every job")

    def covers(name):
        return name in labels and since.get(name) is not None and rng["start"] >= since[name]

    # How a device and a severity are matched over this range: by the label where it covers
    # the whole range, else by the line itself (which reads labelled and older lines alike).
    modes = {"dev": "label" if covers("device") else "line",
             "sev": "label" if covers("severity") else "line"}
    if devices:
        names = " and ".join(devices[:3]) + (f" and {len(devices) - 3} more"
                                             if len(devices) > 3 else "")
        if covers("device"):
            sel.append((_matcher("device", devices), "dev"))
            explain["dev"] = f"keeps the lines whose device label is {names}"
        else:
            # The device's own name before its timestamp (`logging origin-id hostname`), as
            # device_logs.host_pattern anchors it: a prefix of another name never matches.
            pat = (r"\s(?:" + alternation(devices) + r"):\s" if len(devices) > 1 else
                   r"\s" + literal(devices[0]) + r":\s")
            pipe.append((f"|~ {string(pat)}", "dev"))
            began = _utc(since["device"], "%-d %b %H:%M UTC") if since.get("device") else ""
            explain["dev"] = (f"keeps the lines {names} sent, by the device's own name before "
                              "its timestamp: " + (f"the device label began {began}, after "
                                                  "this range starts" if began else
                                                  "Loki holds no device label here"))
            notes.append(explain["dev"])
        reads.append(f"from {names}")
    if spec["sev"]:
        n = int(spec["sev"])
        from modules.device_logs import SEVERITY
        if covers("severity"):
            sel.append((f"severity=~{string(f'[0-{n}]')}", "sev"))
            explain["sev"] = (f"keeps the lines whose severity label is {n} ({SEVERITY[n]}) or "
                              "worse; a line with no severity (a trap) is left out")
        else:
            pipe.append((f"|~ {string(f'%[A-Z0-9_]+(?:-[A-Z0-9_]+)*-[0-{n}]-[A-Z0-9_]+')}",
                         "sev"))
            began = _utc(since["severity"], "%-d %b %H:%M UTC") if since.get("severity") else ""
            explain["sev"] = (f"keeps the lines whose mnemonic carries severity {n} "
                              f"({SEVERITY[n]}) or worse, read from the line: "
                              + (f"the severity label began {began}, after this range starts"
                                 if began else "Loki holds no severity label here"))
            notes.append(explain["sev"])
        reads.append(f"severity {n} or worse")
    if spec["mn"]:
        mns = spec["mn"]
        pipe.append(((f"|= {string(mns[0])}" if len(mns) == 1 else
                      f"|~ {string('(?:' + alternation(mns) + ')')}"), "mn"))
        explain["mn"] = f"keeps the lines holding {' or '.join(m.lstrip('%') for m in mns)}"
        reads.append(" or ".join(m.lstrip("%") for m in mns) + " lines")
    if spec["has"]:
        pipe.append((f"|= {string(spec['has'])}", "has"))
        explain["has"] = f'keeps the lines containing "{spec["has"]}", exactly as written'
        reads.append(f'containing "{spec["has"]}"')
    if spec["not"]:
        pipe.append((f"!= {string(spec['not'])}", "not"))
        explain["not"] = f'leaves out the lines containing "{spec["not"]}"'
        reads.append(f'not containing "{spec["not"]}"')
    # device_logs' heartbeat line, its marker written as an RE2 literal (`literal` leaves the
    # hyphen as it is, where Python's re.escape writes `\-`): the same lines matched, and the
    # query drawn names the marker as the identifier it is.
    from modules.device_logs import MARKER
    heartbeat = r"%HA_EM-\d-LOG: " + literal(MARKER) + ": " + literal(MARKER)
    pipe.append((f"!~ {string(heartbeat)}", "hb"))
    explain["hb"] = "leaves out Mercury's heartbeat lines, as every log view does"
    selector = "{" + ", ".join(t for t, _k in sel) + "}"
    log_parts = [("{", ""), *[(t + (", " if i < len(sel) - 1 else ""), k)
                             for i, (t, k) in enumerate(sel)], ("}", "")]
    log_parts += [(" " + t, k) for t, k in pipe]
    log_query = selector + "".join(" " + t for t, _k in pipe)
    out = {"log_query": log_query, "explain": explain, "notes": notes, "by_label": "",
           "modes": modes}
    if spec["show"] == "counts":
        w_words, _secs, w_dur = WINDOWS[spec["every"]]
        by, extract = spec["by"], ""
        if by == "mnemonic":
            extract, by_label = "mn", "mn"
        elif by == "device" and not covers("device"):
            extract, by_label = "dev", "dev"
        else:
            by_label = by
        stage = ""
        if extract:
            from modules.device_logs import LOGQL_FIELDS
            stage = f" | regexp {string(LOGQL_FIELDS)}"
        head = f"sum by ({by_label}) (count_over_time("
        tail = f"{stage} [{w_dur}]))"
        out["query"] = head + log_query + tail
        out["parts"] = [(head, "count")] + log_parts + [(tail, "count")]
        per = {"mn": "per mnemonic", "dev": "per device"}.get(by_label, f"per {by}")
        explain["count"] = (f"counts the matching lines in each {w_words} window "
                            f"(count_over_time, [{w_dur}]) and makes one line {per} "
                            f"(sum by ({by_label}))"
                            + (", the field read from each line by Mercury's own pattern"
                               if extract else ""))
        reads.append(f"counted every {w_words} {per}")
        out["by_label"] = by_label
    else:
        out["query"] = log_query
        out["parts"] = log_parts
        reads.append("newest first")
    explain["range"] = f"the range is not part of the query: Loki is asked for {rng['words']}"
    explain["start"] = "the Start-from chip set every choice below"
    out["reads"] = ", ".join(reads) + f", over {rng['words']}"
    return out


# ---------------------------------------------------------------------------- the answer

def _refusals(spec: dict, rng: dict, lim: dict) -> list:
    """``[(words, [(label, over)])]``: each bound the ask passes, both operands named, with the
    choices that would fit."""
    out = []
    longest = (lim.get("max_query_length") or {}).get("seconds")
    if longest and rng["seconds"] > longest:
        out.append((f"Refused: one ask spans at most {duration_words(longest)} (Loki's "
                    f"max_query_length, {lim['max_query_length']['text']}). This range is "
                    f"{duration_words(rng['seconds'])}.",
                    [("Narrow to the last 30 days", {"range": "30d", "within": "", "from": "",
                                                     "to": ""})]))
    if spec["show"] == "counts":
        secs = WINDOWS[spec["every"]][1]
        n = int(rng["seconds"] // secs)
        if n > MAX_WINDOWS:
            fit = next((k for k, (_w, s, _d) in WINDOWS.items()
                        if rng["seconds"] // s <= MAX_WINDOWS), "1d")
            out.append((f"Refused: at most {MAX_WINDOWS:,} windows a series (Mercury's bound). "
                        f"{duration_words(rng['seconds'])} every {WINDOWS[spec['every']][0]} is "
                        f"{n:,} windows.",
                        [(f"Count every {WINDOWS[fit][0]}", {"every": fit})]))
    return out


def _last_good(list_name: str) -> str:
    from modules import reader_job
    try:
        got = reader_job.read_cached_for("logs-tail", list_name)
    except Exception:                                 # noqa: BLE001
        return ""
    return (((got.get("doc") or {}).get("last_good") or {}).get("value_at")) or ""


def _kind_of(stream: dict) -> str:
    return stream.get("job") or ""


def lines(list_name: str, spec: dict, built: dict, rng: dict, client, now: float) -> dict:
    """A page of the lines, newest first, masked: at most `PAGE`, and how many match in all."""
    from modules import device_logs
    from modules.redact import redact_text

    end = rng["end"]
    if spec["before"]:
        end = min(end, int(spec["before"]) / 1e9)
    t0 = time.time()
    data, err = _json(client, "loki/api/v1/query_range", query=built["log_query"], limit=PAGE,
                      start=str(int(rng["start"] * 1e9)), end=str(int(end * 1e9)),
                      direction="backward")
    took = int((time.time() - t0) * 1000)
    if err:
        return {"state": "error", "error": err, "asked_at": _iso(now)}
    if (data or {}).get("resultType") not in (None, "streams"):
        return {"state": "error", "error": f"Loki answered {data.get('resultType')}, not lines",
                "asked_at": _iso(now)}
    from modules.readers.logs_summary import _fields_of

    rows = []
    for stream in (data or {}).get("result") or []:
        labels = stream.get("stream") or {}
        for ns, raw in stream.get("values") or []:
            text = redact_text(raw)
            # The device by its label, else by its own name in the line (the logs readers'
            # pattern); a line naming none (a trap's own words) keeps its text whole.
            dev = labels.get("device") or _fields_of(text)[0] or ""
            p = device_logs.parse(text, dev) if dev else {"sev": None, "mnemonic": "",
                                                          "text": text}
            sev = labels.get("severity")
            sev = int(sev) if isinstance(sev, str) and sev.isdigit() else p.get("sev")
            line = f"{p['mnemonic']}: {p['text']}" if p.get("mnemonic") else p.get("text", text)
            rows.append({"ns": int(ns), "at": _utc(int(ns) / 1e9, "%-d %b %H:%M:%S"),
                         "iso": _iso(int(ns) / 1e9), "device": dev, "kind": _kind_of(labels),
                         "sev": sev, "sev_word": device_logs.SEVERITY.get(sev, "")
                         if sev is not None else "", "text": line})
    rows.sort(key=lambda r: r["ns"], reverse=True)
    rows = rows[:PAGE]
    at = int(spec["at"] or 0)
    out = {"state": "ok" if rows else "empty", "rows": rows, "took_ms": took, "read_at": _iso(now),
           "at": at, "more": len(rows) >= PAGE,
           "next_before": str(rows[-1]["ns"] - 1) if rows else "", "total": None}
    if len(rows) >= PAGE or at:
        out["total"] = _count(client, built["log_query"], rng)
    else:
        out["total"] = len(rows)
    if not rows:
        out["context"] = _context(client, spec, built, rng)
    return out


def _count(client, log_query: str, rng: dict):
    """How many lines *log_query* matches over the whole range (one instant count), or None."""
    q = f"sum(count_over_time({log_query} [{int(rng['seconds'])}s]))"
    data, err = _json(client, "loki/api/v1/query", query=q, time=str(int(rng["end"] * 1e9)))
    if err:
        return None
    try:
        res = (data or {}).get("result") or []
        return int(float(res[0]["value"][1])) if res else 0
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _context(client, spec, built, rng) -> dict:
    """An empty answer's context: how many lines the same jobs and devices sent in the range,
    before the filters, so "no lines" is said against what there was."""
    sel = built["log_query"].split("}", 1)[0] + "}"
    return {"sent": _count(client, sel, rng),
            "filtered": bool(spec["sev"] or spec["mn"] or spec["has"] or spec["not"])}


def counts(list_name: str, spec: dict, built: dict, rng: dict, client, now: float,
           href=None) -> dict:
    """The counts over time, one series per value of the count's label, as the Monitoring
    chart's payload, and the legend's numbers per series."""
    w_words, step, _d = WINDOWS[spec["every"]]
    # Loki aligns a metric query's points to multiples of the step (measured on the lab's
    # Loki 3.3, 2026-10-15: asked from 08:25, its points fell on the hour). So the windows are
    # aligned here first: whole windows inside the range, each point closing its window.
    first = -(-int(rng["start"]) // step) * step
    last = int(rng["end"]) // step * step
    start = first + step
    t0 = time.time()
    data, err = _json(client, "loki/api/v1/query_range", query=built["query"],
                      start=str(int(start * 1e9)), end=str(int(last * 1e9)), step=str(step))
    took = int((time.time() - t0) * 1000)
    if err:
        return {"state": "error", "error": err, "asked_at": _iso(now)}
    if (data or {}).get("resultType") != "matrix":
        return {"state": "error", "error": f"Loki answered {(data or {}).get('resultType')}, "
                                           "not counts over time", "asked_at": _iso(now)}
    grid = list(range(int(start), int(last) + 1, step))
    by = built["by_label"]
    shown_label = {"mn": "mnemonic", "dev": "device"}.get(by, by)
    series = []
    for row in (data or {}).get("result") or []:
        value = (row.get("metric") or {}).get(by, "")
        got = {}
        for ts, v in row.get("values") or []:
            try:
                got[int(float(ts))] = int(float(v))
            except (TypeError, ValueError):
                continue
        vals = [got.get(g, 0) for g in grid]
        total = sum(vals)
        last = max((g for g, v in zip(grid, vals) if v), default=None)
        series.append({"value": value, "label": f'{shown_label}="{value}"' if value else
                       f"no {shown_label}", "total": total, "most": max(vals) if vals else 0,
                       "last": last, "values": vals,
                       "href": href(shown_label, value) if href and value else ""})
    series.sort(key=lambda s: (-s["total"], s["label"]))
    shown = series[:MAX_SERIES]
    payload = {"ok": True, "type": "timeseries", "stepped": True, "legend_off": True,
               "title": "", "unit": "", "range": rng["words"].replace("the last ", ""),
               "step": step, "read_at": _iso(now), "asked": [built["query"]],
               "series": [{"label": s["label"], "times": grid, "values": s["values"],
                           "href": s["href"]} for s in shown],
               "note": (f"{len(series)} series: the {MAX_SERIES} with the most lines are drawn"
                        if len(series) > MAX_SERIES else "")}
    for s in shown:
        s["last_words"] = (f"{_utc(s['last'] - step, '%-d %b %H:%M')} to "
                           f"{_utc(s['last'], '%H:%M')} UTC") if s["last"] else "none"
    out = {"state": "ok" if any(s["total"] for s in series) else "empty", "series": shown,
           "series_total": len(series), "payload": payload, "took_ms": took,
           "read_at": _iso(now), "window_words": w_words, "label": shown_label,
           "covers": (first, last)}
    if out["state"] == "empty":
        out["context"] = _context(client, spec, built, rng)
    return out


# ---------------------------------------------------------------------------- the view

def mnemonics(list_name: str, rng: dict, devices: list) -> dict:
    """The mnemonics the logs reader counted for the chosen devices over the range, most first:
    ``{"state", "why", "rows": [(mnemonic, n)]}`` (its store, never a Loki read per request)."""
    from modules import logs_page

    st = logs_page.stored(list_name)
    if st["state"] != "ok":
        return {"state": st["state"], "why": st.get("why") or "the logs reader has not counted "
                                                               "yet", "rows": []}
    v = st["value"]
    first, last = _utc(rng["start"], "%Y-%m-%d"), _utc(rng["end"], "%Y-%m-%d")
    spans = ([v.get("last_24h") or {}] if rng["seconds"] <= 86400 else
             [c for d, c in (v.get("days") or {}).items() if first <= d <= last])
    want = set(devices)
    got = {}
    for by_dev in spans:
        for dev, mns in (by_dev or {}).items():
            if want and dev not in want:
                continue
            for mn, n in mns.items():
                got[mn] = got.get(mn, 0) + n
    return {"state": "ok", "why": "", "value_at": st.get("value_at", ""),
            "rows": sorted(got.items(), key=lambda kv: (-kv[1], kv[0]))}


def view(list_name: str, values, now: float = None, client=None) -> dict:
    """Everything board F3 draws for one network and the choices in the address."""
    now = _now() if now is None else now
    spec, errors = ask(values)
    rng = window(spec, now)
    if rng["error"]:
        errors.append(rng["error"])
    probe = client or _client(list_name, 15.0)
    lim = limits(list_name, client=probe, now=now) if probe.is_configured() else {}
    # The wait is Loki's own query_timeout and 5 s (its default, 1 min, when it is not read).
    wait = ((lim.get("query_timeout") or {}).get("seconds") or (DEFAULT_WAIT - 5)) + 5
    client = client or _client(list_name, wait)
    disc = discover(list_name, rng["start"], rng["end"], client=client, now=now)
    devices = list(spec["dev"])
    role_devices = _devices_of_role(list_name, spec["role"]) if spec["role"] else []
    if spec["role"]:
        devices = sorted(set(devices) | set(role_devices))
        if not role_devices:
            errors.append(f"no device of {list_name} carries the role {spec['role']!r}")
    if spec["by"] not in ("device", "mnemonic") and spec["by"] not in disc["labels"] \
            and disc["state"] == "ok":
        errors.append(f"Loki holds no label {spec['by']!r} in this range: counted per device")
        spec["by"] = "device"
    built = build(spec, disc, rng, devices)
    page = "/v2/history/query/ask/logs"
    out = {"list": list_name, "s": spec, "errors": errors, "range": rng, "limits": lim,
           "disc": disc, "built": built, "devices": devices, "role_devices": role_devices,
           "roles": roles(list_name), "presets": PRESETS, "preset_on": preset_on(spec),
           "ranges": RANGES, "windows": WINDOWS, "page": PAGE, "max_windows": MAX_WINDOWS,
           "max_series": MAX_SERIES, "mnemonics": mnemonics(list_name, rng, devices),
           "qs": lambda over=None: qs(spec, list_name, over),
           "preset_qs": lambda params: qs(spec, list_name, preset_over(params)),
           "now": _iso(now), "answer": None}
    from modules.device_logs import SEVERITY
    out["severities"] = SEVERITY
    out["by_choices"] = ["device", "mnemonic"] + [l for l in disc["labels"]
                                                  if l not in ("device",)]
    out["since_words"] = {k: _utc(v, "%-d %b %Y %H:%M UTC")
                          for k, v in (disc.get("since") or {}).items() if v}
    for item in lim.values():
        if isinstance(item, dict) and "seconds" in item:
            item["words"] = duration_words(item["seconds"])
    out["range_words"] = duration_words(rng["seconds"])
    windows = int(rng["seconds"] // WINDOWS[spec["every"]][1])
    longest = (lim.get("max_query_length") or {}).get("seconds")
    out["fit"] = {"windows": windows,
                  "words": ("longer than one ask spans" if longest and rng["seconds"] > longest
                            else "more windows than are drawn"
                            if spec["show"] == "counts" and windows > MAX_WINDOWS
                            else "within every limit below")}
    title = next((t for k, t, _p in PRESETS if k == out["preset_on"]), "")
    if spec["show"] == "counts":
        title = (title or "Lines") + f" per {WINDOWS[spec['every']][0]}"
    else:
        title = title or "The lines"
    who = (" and ".join(devices) if len(devices) <= 3 else f"{len(devices)} devices") \
        if devices else "every device"
    out["answer_title"] = (f"{title}, {who}, {_utc(rng['start'])} to {_utc(rng['end'])} UTC")
    out["code_range"] = spec["range"] if spec["range"] in ("24h", "7d", "30d") else "30d"
    if spec["ask"] != "1":
        return out
    if errors or disc["state"] != "ok":
        out["answer"] = {"state": "error" if disc["state"] == "error" else "refused",
                         "error": disc["error"] if disc["state"] != "ok" else "",
                         "refusals": [(e, []) for e in errors], "asked_at": _iso(now),
                         "last_good": _last_good(list_name)}
        return out
    refusals = _refusals(spec, rng, lim)
    if refusals:
        out["answer"] = {"state": "refused", "refusals": refusals, "asked_at": _iso(now)}
        return out

    def href(label, value):
        param = {"device": "dev", "mnemonic": "mn", "job": "job"}.get(label)
        over = {"show": "lines", "range": "custom", "within": "", "ask": "1", "before": "",
                "at": "", "hl": ""}
        if param:
            over[param] = [value]
            if param == "dev":
                over["role"] = ""
        return page + qs(spec, list_name, over)

    if spec["show"] == "counts":
        ans = counts(list_name, spec, built, rng, client, now, href=href)
    else:
        ans = lines(list_name, spec, built, rng, client, now)
    if ans["state"] == "error":
        ans["last_good"] = _last_good(list_name)
    if ans.get("covers"):
        # Whole windows inside the range: the title names the span they cover.
        out["answer_title"] = (out["answer_title"].rsplit(", ", 1)[0] + f", {_utc(ans['covers'][0])}"
                               f" to {_utc(ans['covers'][1])} UTC")
    ans["kept"] = (lim.get("retention_period") or {}).get("seconds")
    ans["kept_words"] = duration_words(ans["kept"]) if ans["kept"] else ""
    ans["inside_kept"] = bool(ans["kept"]) and rng["start"] >= now - ans["kept"]
    out["answer"] = ans
    return out
