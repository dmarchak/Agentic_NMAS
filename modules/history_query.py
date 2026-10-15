"""History › Query (C667; board A, AskLibrary, on the canvas page "History, Query"): ask the
network's history, starting from a question.

What the landing draws: what the history holds (the metrics' live store and whether a
long-term store answers past it, the logs' retention and the store's first day, each from
the setting or the reader that knows it, never assumed), and the ready-made questions, each
either opening its answer or said "not built yet". The board's saved views and "Ask your
own" are a later step of C667, said on the page as such.
"""

import logging

from modules.history_ask import duration_words

log = logging.getLogger(__name__)

#: The board's six ready-made questions, in its order: (key, title, what it answers, source).
#: A question opens its answer when `ANSWERS` names its route; the rest are said "not built
#: yet", never drawn as a link that goes nowhere.
QUESTIONS = (
    ("errors", "Interface errors and discards over time",
     "Which interfaces drop or corrupt packets, and since when", "metrics · per interface"),
    ("cpu", "CPU and memory trend", "Is a device getting busier, week on week",
     "metrics · per device"),
    ("neighbours", "Routing neighbour changes", "When OSPF and BGP neighbours went up and down",
     "metrics · per neighbour"),
    ("syslog", "Syslog by device",
     "Lines by severity and mnemonic, each device's lines one click away", "logs · per line"),
    ("restarts", "Restarts", "Each restart, planned or not, with its window",
     "metrics and logs"),
    ("telemetry", "Telemetry rates", "Is each device still streaming, and how much",
     "metrics · per device"),
)
#: The questions built, by the route that answers each (and its arguments).
ANSWERS = {"syslog": ("v2.history_query_syslog", {}),
           **{k: ("v2.history_query_metric", {"key": k})
              for k in ("errors", "cpu", "neighbours", "restarts", "telemetry")}}

# ---------------------------------------------------------------------------
# A metrics answer (board B, AskMetric): one question's PromQL for a device (or every device)
# and an interface (or every interface), over a range, asked of the network's Grafana through
# the same path a Monitoring panel takes (`panels.build_request`: the range, the step, the
# store that keeps it), drawn by the same chart. The expression is the question's, never the
# browser's: a device or an interface name reaches it only as one checked label value.
# ---------------------------------------------------------------------------

#: The ranges board B offers: key -> (words, seconds).
METRIC_RANGES = {"24h": ("24 h", 86400), "7d": ("7 d", 7 * 86400), "30d": ("30 d", 30 * 86400),
                 "180d": ("180 d", 180 * 86400), "1y": ("1 y", 365 * 86400)}
#: A label value that may reach the expression: a device's or an interface's name.
_NAME = __import__("re").compile(r"^[A-Za-z0-9._/:-]{1,64}$")

METRICS = {
    "errors": {
        "title": "Interface errors and discards over time",
        "y": "discards per second (packets/s)", "unit": "pps",
        "source": ("SNMP interface counters (ifInDiscards, ifOutDiscards), every 60 s, read from "
                   "Prometheus through Grafana"),
        "by_device": ("sum by (device) (rate(ifInDiscards[$__rate_interval]) + "
                      "rate(ifOutDiscards[$__rate_interval]))"),
        "by_interface": ('sum by (ifName) (rate(ifInDiscards{{{sel}}}[$__rate_interval]) + '
                         'rate(ifOutDiscards{{{sel}}}[$__rate_interval]))'),
        "names": 'count by (ifName) (ifInDiscards{{device="{d}"}})',
    },
    # Board A's "CPU and memory trend", drawn in board B's layout with a device and no
    # interface. Measured on the host 2026-10-11 (series and labels, read-only): the routers
    # carry CISCO-PROCESS-MIB's cpmCPUTotal5minRev and the memory pools (ciscoMemoryPoolUsed and
    # Free, pool "Processor"); the switches carry only OLD-CISCO's cpuAvgBusy5, no memory pool.
    "cpu": {
        "title": "CPU and memory trend",
        "y": "percent busy and percent of memory used", "unit": "percent",
        "source": ("SNMP every 60 s, read from Prometheus through Grafana: CPU, the 5-minute "
                   "busy (cpmCPUTotal5minRev where a device has it, else cpuAvgBusy5); memory, "
                   "the Processor pool's used share (ciscoMemoryPoolUsed and Free)"),
        "covers": ("CPU on every device that answers either CPU object; memory only where the "
                   "device's scrape carries a memory pool: a device whose scrape carries none "
                   "draws CPU alone"),
        "series": (
            ("max by (device) (cpmCPUTotal5minRev or cpuAvgBusy5)",
             'max(cpmCPUTotal5minRev{{device="{d}"}} or cpuAvgBusy5{{device="{d}"}})',
             "{{device}} CPU", "CPU"),
            ('100 * sum by (device) (ciscoMemoryPoolUsed{ciscoMemoryPoolName="Processor"}) / '
             '(sum by (device) (ciscoMemoryPoolUsed{ciscoMemoryPoolName="Processor"}) + '
             'sum by (device) (ciscoMemoryPoolFree{ciscoMemoryPoolName="Processor"}))',
             '100 * sum(ciscoMemoryPoolUsed{{device="{d}",ciscoMemoryPoolName="Processor"}}) / '
             '(sum(ciscoMemoryPoolUsed{{device="{d}",ciscoMemoryPoolName="Processor"}}) + '
             'sum(ciscoMemoryPoolFree{{device="{d}",ciscoMemoryPoolName="Processor"}}))',
             "{{device}} memory", "memory (Processor pool)"),
        ),
    },
    # Board A's "Routing neighbour changes", in board B's layout. Measured on the host
    # 2026-10-11: OSPF-MIB's ospfNbrState on 6 devices, OSPFV3-MIB's ospfv3NbrState on 4, and
    # CISCO-BGP4-MIB's cbgpPeer2State on 2. The established adjacencies are counted, a gauge:
    # a neighbour lost is a dip, whatever the step, where counting the event counters per step
    # would over- or under-count as the step moves.
    "neighbours": {
        "title": "Routing neighbour changes",
        "y": "established neighbours", "unit": "short",
        "source": ("SNMP every 60 s, read from Prometheus through Grafana: OSPF neighbours in "
                   "state full (ospfNbrState 8), OSPFv3 likewise (ospfv3NbrState 8), BGP peers "
                   "established (cbgpPeer2State 6)"),
        "covers": ("each protocol on the devices that report it; a dip is a neighbour going "
                   "down and its return the neighbour coming back; a neighbour down and back "
                   "between two reads (60 s) is not seen"),
        "series": (
            ("count by (device) (ospfNbrState == 8)",
             'count(ospfNbrState{{device="{d}"}} == 8)', "{{device}} OSPF", "OSPF"),
            ("count by (device) (ospfv3NbrState == 8)",
             'count(ospfv3NbrState{{device="{d}"}} == 8)', "{{device}} OSPFv3", "OSPFv3"),
            ("count by (device) (cbgpPeer2State == 6)",
             'count(cbgpPeer2State{{device="{d}"}} == 6)', "{{device}} BGP", "BGP"),
        ),
    },
    # Board A's "Restarts": the uptime counter falling, the restart rule's own measure (never a
    # boot time from uptime), with Mercury's restart record beside the chart for whether each
    # was planned and its window (`restart_record`).
    "restarts": {
        "title": "Restarts",
        "y": "restarts (the uptime counter falling)", "unit": "short",
        "source": ("SNMP sysUpTime every 60 s, read from Prometheus through Grafana: each fall "
                   "of the counter is a restart; whether it was planned is Mercury's restart "
                   "record, below"),
        "covers": ("every device whose uptime is scraped; a restart is drawn in the step it "
                   "fell in, so at a long range several restarts of one device can share a "
                   "point"),
        "series": (
            ("sum by (device) (resets(sysUpTime[$__interval]))",
             'sum(resets(sysUpTime{{device="{d}"}}[$__interval]))', "{{device}}", "restarts"),
        ),
    },
    # Board A's "Telemetry rates". Measured on the host 2026-10-11: the IOS-XE model-driven
    # telemetry Telegraf exposes carries the YANG model in the metric name (Cisco_IOS_XE_…),
    # 957 series with a device label, none without; a classic IOS device streams none.
    "telemetry": {
        "title": "Telemetry rates",
        "y": "telemetry series held", "unit": "short",
        "source": ("model-driven telemetry as the collector exposes it, read from Prometheus "
                   "through Grafana: the series each device's stream holds, by YANG model for "
                   "one device"),
        "covers": ("devices that stream IOS-XE telemetry (Cisco_IOS_XE_ models); a device "
                   "that stops streaming loses its series when the collector expires them, "
                   "so its line falls to nothing; a device that never streamed is not drawn"),
        "series": (
            ('count by (device) ({__name__=~"Cisco_IOS_XE_.+", device!=""})',
             'count by (model) (label_replace({{__name__=~"Cisco_IOS_XE_.+", device="{d}"}}, '
             '"model", "$1", "__name__", "Cisco_IOS_XE_([^:]+):.*"))',
             "{{device}}", "{{model}}"),
        ),
    },
}


# ---------------------------------------------------------------------------
# Your own query (board B's "The query (PromQL), editable"; board A's "Ask your own (PromQL or
# LogQL)"): a question's PromQL edited in place, or a query of your own in board B's layout
# with an empty question. It is a READ of the network's Grafana (PromQL, through the panel
# path's range and step bounds) or Loki (LogQL lines, at most `LOGQL_LIMIT` from at most
# `LOGQL_MAX_DAYS`, masked), carried in the address so a link shows the same answer, and
# marked as yours wherever it is drawn, never passed off as the question's.
# ---------------------------------------------------------------------------

#: The longest query taken, the most PromQL expressions (one a line, each a series), and the
#: LogQL bounds: Loki answers at most 30 days 1 hour at a time; 200 lines is board C's page.
QUERY_MAX = 2000
QUERY_LINES = 4
LOGQL_LIMIT = 200
LOGQL_MAX_DAYS = 30
LANGS = {"promql": "PromQL", "logql": "LogQL"}

# Code mode is free text, BOUNDED (the operator's decision, 2026-10-15, C817): it reads only
# through the stores' read endpoints, over at most `LOGQL_MAX_DAYS`, at most `LOGQL_LIMIT`
# lines, waiting at most `history_logq.DEFAULT_WAIT`, every line and label masked by
# `redact_text`. The query text never chooses an endpoint: each ask names its path here first.
#: The only paths Code mode asks of each store.
READS = {"loki": ("loki/api/v1/query", "loki/api/v1/query_range", "loki/api/v1/labels"),
         "grafana": ("api/ds/query",)}
#: The data source types Code mode's PromQL is asked of, through Grafana's query endpoint.
PROMQL_SOURCES = ("prometheus",)

ASK = {"title": "Ask your own", "y": "your query's values", "unit": "short",
       "source": ("your own query: PromQL asked of the network's Grafana, from the store that "
                  "keeps the range; LogQL asked of the network's Loki, its lines masked")}


class AskRefused(ValueError):
    """A question asked with a value it cannot carry, named."""


def read_only(store: str, path: str) -> str:
    """*path* when it is one of the read endpoints Code mode asks *store* through; else
    refused, naming both."""
    allowed = READS[store]
    if path not in allowed:
        raise AskRefused(f"Refused: Code mode reads {store} only through "
                         f"{', '.join(allowed)}; this ask names {path!r}")
    return path


def promql_sources(body: dict) -> None:
    """Every query in a Grafana `api/ds/query` *body* is asked of a Prometheus data source,
    named by uid; else refused, naming the query and its source."""
    for q in body.get("queries") or []:
        ds = q.get("datasource") or {}
        if ds.get("type") in PROMQL_SOURCES and ds.get("uid"):
            continue
        source = (f"a {ds.get('type') or 'typeless'} data source ({ds['uid']})" if ds.get("uid")
                  else "no named data source (the network's Grafana lists none of that type)")
        raise AskRefused(f"Refused: Code mode's PromQL is asked only of a "
                         f"{' or '.join(PROMQL_SOURCES)} data source; query "
                         f"{q.get('refId', '?')} would be asked of {source}")


def question(key: str):
    """The question *key* asks: one of `METRICS`, or ``ask`` (your own); None if neither."""
    return ASK if key == "ask" else METRICS.get(key)


def custom_query(text: str, lang: str = "promql") -> str:
    """A query of your own, as it is asked: printable ASCII, at most `QUERY_MAX` characters,
    at most `QUERY_LINES` PromQL expressions (one a line) or one LogQL line; refused by name."""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    if len(text) > QUERY_MAX:
        raise AskRefused(f"the query is {len(text)} characters; at most {QUERY_MAX} are asked")
    bad = sorted({c for c in text if c != "\n" and not 32 <= ord(c) <= 126})
    if bad:
        raise AskRefused("the query may hold only printable ASCII; it holds "
                         + ", ".join(f"U+{ord(c):04X}" for c in bad))
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lang == "promql" and len(lines) > QUERY_LINES:
        raise AskRefused(f"the query holds {len(lines)} expressions; at most {QUERY_LINES} are "
                         "asked, one a line")
    if lang == "logql" and len(lines) > 1:
        raise AskRefused("a LogQL query is one line")
    return "\n".join(lines)


def metric_ask(values, key: str = "errors") -> dict:
    """The question's values from the address: device, interface, range, and your own query
    (``q``, and ``lang`` for Ask your own). A name that is not one is refused by name, never
    passed into the expression; an interface is refused for a question asked per device."""
    s = {"d": (values.get("d") or "").strip(), "i": (values.get("i") or "").strip(),
         "range": (values.get("range") or "30d").strip(), "q": "",
         "lang": (values.get("lang") or "promql").strip().lower() if key == "ask" else ""}
    if key == "ask" and s["lang"] not in LANGS:
        raise AskRefused(f"{s['lang']!r} is not a query language here: PromQL or LogQL")
    if key == "ask" and (s["d"] or s["i"]):
        raise AskRefused("your own query names its own devices: Ask your own takes no device or "
                         "interface")
    if s["i"] and "series" in METRICS.get(key, {}):
        raise AskRefused(f"{METRICS[key]['title']} is asked per device, not per interface")
    if s["range"] not in METRIC_RANGES:
        raise AskRefused(f"{s['range']!r} is not one of the ranges: "
                         + ", ".join(METRIC_RANGES))
    if s["lang"] == "logql" and METRIC_RANGES[s["range"]][1] > LOGQL_MAX_DAYS * 86400:
        raise AskRefused(f"Refused: a LogQL query spans at most {LOGQL_MAX_DAYS} days (Code "
                         f"mode's bound; Loki answers at most 30 days 1 hour at a time); this "
                         f"range is {duration_words(METRIC_RANGES[s['range']][1])}: choose "
                         "30 d or shorter")
    for k, what in (("d", "a device"), ("i", "an interface")):
        if s[k] and not _NAME.match(s[k]):
            raise AskRefused(f"{s[k]!r} is not {what} name")
    if s["i"] and not s["d"]:
        raise AskRefused("an interface is asked of one device: choose the device first")
    s["q"] = custom_query(values.get("q"), s["lang"] or "promql")
    return s


def metric_exprs(key: str, s: dict) -> list:
    """``[(PromQL, legend)]``: the question's series for these values, or your own query's
    (one series a line, labelled by Grafana from the series' labels)."""
    if s.get("q") and s.get("lang", "promql") in ("promql", ""):
        return [(line, "") for line in s["q"].split("\n")]
    if key == "ask":
        return []
    q = METRICS[key]
    if "series" in q:
        return [(every, legend_every) if not s["d"] else
                (one.format(d=s["d"]), legend_one)
                for every, one, legend_every, legend_one in q["series"]]
    if not s["d"]:
        return [(q["by_device"], "{{device}}")]
    sel = f'device="{s["d"]}"' + (f',ifName="{s["i"]}"' if s["i"] else "")
    return [(q["by_interface"].format(sel=sel), "{{ifName}}")]


def metric_expr(key: str, s: dict) -> str:
    """The question's PromQL for these values, each series' on its own line."""
    return "\n".join(e for e, _l in metric_exprs(key, s))


def metric_panel(key: str, s: dict) -> dict:
    """The question as a panel the chart draws: its PromQL, its unit and its legends."""
    q = question(key)
    return {"id": 0, "type": "timeseries", "title": q["title"],
            "fieldConfig": {"defaults": {"unit": q["unit"]}},
            "targets": [{"refId": "ABCDEFGH"[n], "expr": e, "legendFormat": legend}
                        for n, (e, legend) in enumerate(metric_exprs(key, s))]}


def _grafana(list_name: str) -> tuple:
    """``(client, datasources, error)`` for the network's Grafana, from the stored dashboards'
    read (the data sources and their stores)."""
    from modules import device_page
    value, _at, why = device_page._cached("grafana-dashboards", list_name)
    if value is None:
        return None, [], f"Grafana's data sources are not read yet: {why}"
    return device_page.grafana_client(list_name), value.get("datasources") or [], ""


def metric_data(key: str, list_name: str, values) -> tuple:
    """``(payload, status)``: the question's series, as a Monitoring panel's payload."""
    from modules import panels

    if question(key) is None:
        return {"ok": False, "error": f"{key!r} is not a question"}, 404
    try:
        s = metric_ask(values, key)
    except AskRefused as exc:
        return {"ok": False, "error": str(exc)}, 400
    if s["lang"] == "logql":
        return {"ok": False, "error": "a LogQL query is drawn on its page from Loki's answer, "
                                      "not read here"}, 400
    if not metric_exprs(key, s):
        return {"ok": False, "error": "nothing is asked yet: write a query and run it"}, 400
    client, datasources, err = _grafana(list_name)
    if err:
        return {"ok": False, "error": err}, 503
    panel = metric_panel(key, s)
    seconds = METRIC_RANGES[s["range"]][1]
    default_ds = panels.default_datasource(datasources, "prometheus")
    st = panels.stores(datasources, list_name)
    try:
        body = panels.build_request(panel, {}, {}, seconds, default_ds, st)
        # A read, and only of Prometheus (C817): Grafana's query endpoint, never another path,
        # and never a data source of another type, whatever the query says.
        from modules.integrations.grafana import GrafanaIntegration
        read_only("grafana", GrafanaIntegration.QUERY_PATH)
        promql_sources(body)
    except (panels.RangeRefused, AskRefused) as exc:
        return {"ok": False, "error": str(exc)}, 400
    got = client.query(body)
    if not got.get("ok"):
        return {"ok": False, "error": f"Grafana: {got.get('error')}"}, 502
    payload = panels.render_payload(panel, got["body"], seconds)
    payload["errors"] = panels.answer_errors(got["body"])
    payload["store"] = panels.store_words(seconds, panel, {}, {}, default_ds, st)
    payload["asked"] = [e for e, _l in metric_exprs(key, s)]
    return payload, 200


def metric_view(key: str, list_name: str, values) -> dict:
    """What board B draws around the chart: the question, its devices and (for one device) its
    interfaces, the range, the stores that hold it, the source and the PromQL."""
    from modules import logs_page, panels

    q = question(key)
    out = {"key": key, "q": q, "list": list_name, "ranges": METRIC_RANGES, "error": "",
           "devices": logs_page._devices(list_name), "interfaces": [], "interfaces_why": "",
           "langs": LANGS, "limits": {"chars": QUERY_MAX, "lines": QUERY_LINES,
                                      "logql_lines": LOGQL_LIMIT, "logql_days": LOGQL_MAX_DAYS}}
    try:
        s = metric_ask(values, key)
    except AskRefused as exc:
        # The refused query stays in the box, so the person can correct it; nothing is asked.
        s = {"d": "", "i": "", "range": "30d", "q": "",
             "lang": "promql" if key == "ask" else ""}
        out["error"] = str(exc)
        out["refused_text"] = (values.get("q") or "")[:QUERY_MAX]
    out["s"] = s
    own = dict(s, q="")
    out["own_expr"] = metric_expr(key, own) if key != "ask" else ""
    out["edited"] = bool(s["q"]) and key != "ask"
    out["expr"] = s["q"] or out.get("refused_text") or out["own_expr"]
    out["asked"] = bool(s["q"]) or key != "ask"
    if s.get("lang") == "logql" and s["q"]:
        out["logql"] = logql_answer(list_name, s)
    client, datasources, err = _grafana(list_name)
    st = panels.stores(datasources, list_name) if not err else None
    seconds = METRIC_RANGES[s["range"]][1]
    out["live_days"] = (st.live // 86400) if st else None
    out["history_store"] = (st.history or {}).get("name", "") if st else ""
    out["past_live"] = bool(st and seconds > st.live)
    out["grafana_error"] = err
    if key == "restarts":
        out["record"] = restart_record(list_name, s["d"], seconds)
    if s["d"] and not err and "names" in q:
        probe = {"type": "table", "targets": [{"refId": "N", "expr": q["names"].format(d=s["d"]),
                                               "instant": True}]}
        try:
            got = client.query(panels.build_request(
                probe, {}, {}, 3600, panels.default_datasource(datasources, "prometheus"), st))
            names = sorted({(sr.get("labels") or {}).get("ifName", "") for sr in
                            panels.frames_to_series(got.get("body") or {}, {})} - {""}) \
                if got.get("ok") else []
            out["interfaces"] = names
            if not got.get("ok"):
                out["interfaces_why"] = f"Grafana: {got.get('error')}"
        except Exception as exc:                      # noqa: BLE001
            out["interfaces_why"] = f"{type(exc).__name__}: {exc}"
    return out


def _number(v):
    """A sample's value as a number, or None (a gap) when it is not one."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def logql_answer(list_name: str, s: dict, now: float = None) -> dict:
    """Your own LogQL query, asked of the network's Loki once over the range, BOUNDED (C817):
    through `query_range` only (`read_only`), over at most `LOGQL_MAX_DAYS`, waiting at most
    `history_logq.DEFAULT_WAIT` (Loki's default query_timeout and 5 s; its /config is not read,
    being no query endpoint), every line and label masked by `redact_text`.

    A log query answers LINES: newest first, at most `LOGQL_LIMIT`, a full page said to be cut.
    A metric query (count_over_time, rate, sum by …: C819) answers SERIES, drawn by the
    Monitoring chart as the logs builder's counts are (a `data-panel-json` payload): one series
    a label set, its values at Loki's step (the builder's window ladder, at most
    `history_logq.MAX_WINDOWS` a series), the `history_logq.MAX_SERIES` largest drawn and the
    rest counted. ``{"kind": "lines"|"series"|"", "error", "lines", "cut", "payload",
    "series_total", "window", "bounds"}``."""
    import time as _time

    from modules import history_logq as LQ
    from modules.redact import redact_text

    now = _time.time() if now is None else now
    seconds = METRIC_RANGES[s["range"]][1]
    step = next((secs for _w, secs, _d in LQ.WINDOWS.values()
                 if seconds // secs <= LQ.MAX_WINDOWS), 86400)
    out = {"kind": "", "lines": [], "error": "", "cut": False, "payload": None,
           "series_total": 0,
           "window": (_time.strftime("%Y-%m-%d %H:%M", _time.gmtime(now - seconds)),
                      _time.strftime("%Y-%m-%d %H:%M", _time.gmtime(now))),
           "bounds": {"lines": LOGQL_LIMIT, "days": LOGQL_MAX_DAYS, "series": LQ.MAX_SERIES,
                      "step": duration_words(step), "wait": "",
                      "reads": ", ".join(p.rsplit("/", 1)[-1] for p in READS["loki"])}}
    # The wait is fixed, never read from Loki's /config: Code mode asks Loki nothing but its
    # query endpoints (`READS`). Loki's default query_timeout, 1 min, and 5 s.
    wait = LQ.DEFAULT_WAIT
    out["bounds"]["wait"] = duration_words(wait)
    client = LQ._client(list_name, wait)                                  # noqa: SLF001
    if not client.is_configured():
        out["error"] = "no log store is configured for this network (its Loki card in Settings)"
        return out
    try:
        path = read_only("loki", "loki/api/v1/query_range")
    except AskRefused as exc:
        out["error"] = str(exc)
        return out
    data, err = LQ._json(client, path, query=s["q"], limit=LOGQL_LIMIT,   # noqa: SLF001
                         step=str(step),
                         start=str(int((now - seconds) * 1e9)), end=str(int(now * 1e9)),
                         direction="backward")
    if err:
        out["error"] = (f"Loki did not answer within {duration_words(wait)} (Code mode's wait: "
                        "Loki's default query_timeout, 1 min, and 5 s)"
                        if err.startswith("Loki did not answer") else err)
        return out
    data = data or {}
    kind = data.get("resultType")
    if kind == "matrix":
        return dict(out, **_logql_series(data.get("result") or [], s, step, now, LQ, redact_text))
    if kind not in (None, "streams"):
        out["error"] = (f"Loki answered {kind}, neither lines (a log query) nor series over "
                        "time (a metric query): nothing is drawn")
        return out
    rows = []
    for stream in data.get("result") or []:
        labels = ", ".join(f"{k}={v}" for k, v in sorted((stream.get("stream") or {}).items()))
        for ns, line in stream.get("values") or []:
            rows.append({"ns": int(ns), "text": redact_text(line), "labels": redact_text(labels),
                         "at": _time.strftime("%Y-%m-%d %H:%M:%S", _time.gmtime(int(ns) / 1e9))})
    rows.sort(key=lambda x: x["ns"], reverse=True)
    out.update(kind="lines", lines=rows[:LOGQL_LIMIT], cut=len(rows) >= LOGQL_LIMIT)
    return out


def _logql_series(result: list, s: dict, step: int, now: float, LQ, redact_text) -> dict:
    """A LogQL metric answer as the Monitoring chart's payload: each series' label set masked,
    its own times and values (a missing point is a gap the chart leaves, never a zero)."""
    series = []
    for row in result:
        metric = row.get("metric") or {}
        label = redact_text(", ".join(f'{k}="{v}"' for k, v in sorted(metric.items()))) \
            or "no labels"
        times, values = [], []
        for ts, v in row.get("values") or []:
            try:
                times.append(int(float(ts)))
            except (TypeError, ValueError):
                continue
            values.append(_number(v))
        series.append({"label": "{" + label + "}" if metric else label, "times": times,
                       "values": values, "size": sum(abs(v) for v in values if v is not None)})
    series.sort(key=lambda x: (-x["size"], x["label"]))
    shown = series[:LQ.MAX_SERIES]
    payload = {"ok": True, "type": "timeseries", "title": "", "unit": "",
               "range": METRIC_RANGES[s["range"]][0], "step": step,
               "read_at": LQ._iso(now), "asked": [s["q"]],                # noqa: SLF001
               "series": [{"label": x["label"], "times": x["times"], "values": x["values"]}
                          for x in shown],
               "note": (f"{len(series)} series: the {LQ.MAX_SERIES} largest are drawn"
                        if len(series) > LQ.MAX_SERIES else "")}
    return {"kind": "series", "payload": payload, "series_total": len(series)}


def restart_record(list_name: str, device: str, seconds: int, now: float = None) -> dict:
    """Mercury's restart record over the range, beside the Restarts chart: each restart newest
    first, judged planned or not against the planned windows recorded now, with its window
    and the device's own reason. ``{"state", "error", "rows", "since"}``: *since* is the
    record's first row, so a range reaching past it says the record began then."""
    import time as _time

    from modules import restarts

    now = _time.time() if now is None else now
    got = restarts.events(device=device, list_name=list_name)
    if got.get("state") == "unreadable":
        return {"state": "unreadable", "error": got.get("error") or "the record could not be read",
                "rows": [], "since": ""}
    every = got.get("rows") or []
    try:
        rows = restarts.judged(every, restarts.planned_rows())
        error = ""
    except RuntimeError as exc:
        rows, error = every, str(exc)
    cut = now - seconds
    shown = [dict(r, words=restarts.words(r)) for r in rows
             if restarts._epoch(r.get("at", "")) >= cut]
    return {"state": got.get("state") or "ok", "error": error, "rows": shown,
            "since": min((r.get("at", "") for r in every), default="")}


def _setting(list_name: str, key: str, default):
    from modules.list_settings import value
    try:
        return value(list_name, key, default)
    except Exception as exc:                          # noqa: BLE001
        log.warning("history query: %s could not be read for %s: %s", key, list_name, exc)
        return default


def coverage(list_name: str) -> dict:
    """What the history holds, each part from where it is known."""
    from modules import logs_page

    live = int(_setting(list_name, "metrics_live_retention_days", 90) or 90)
    long_term = bool((_setting(list_name, "grafana_history_datasource_uid", "") or "").strip())
    logs_days = int(_setting(list_name, "logs_retention_days", 90) or 90)
    st = logs_page.stored(list_name)
    value = st.get("value") or {}
    return {"metrics_live_days": live, "metrics_long_term": long_term,
            "logs_days": logs_days, "logs_state": st.get("state"),
            "logs_first_day": value.get("first_day", ""), "read_at": st.get("value_at", "")}


def library(list_name: str) -> dict:
    """The landing: the coverage, and each question with where it opens (or not yet)."""
    from flask import url_for

    qs = []
    for key, title, what, source in QUESTIONS:
        route, args = ANSWERS.get(key) or ("", {})
        qs.append({"key": key, "title": title, "what": what, "source": source,
                   "url": url_for(route, **args) if route else ""})
    from modules import saved_views
    return {"coverage": coverage(list_name), "questions": qs, "list": list_name,
            "saved": saved_views.read(list_name)}
