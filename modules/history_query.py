"""History › Query (C667; board A, AskLibrary, on the canvas page "History, Query"): ask the
network's history, starting from a question.

What the landing draws: what the history holds (the metrics' live store and whether a
long-term store answers past it, the logs' retention and the store's first day, each from
the setting or the reader that knows it, never assumed), and the ready-made questions, each
either opening its answer or said "not built yet". The board's saved views and "Ask your
own" are a later step of C667, said on the page as such.
"""

import logging

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
           "errors": ("v2.history_query_metric", {"key": "errors"})}

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
}


class AskRefused(ValueError):
    """A question asked with a value it cannot carry, named."""


def metric_ask(values) -> dict:
    """The question's values from the address: device, interface, range. A name that is not
    one is refused by name, never passed into the expression."""
    s = {"d": (values.get("d") or "").strip(), "i": (values.get("i") or "").strip(),
         "range": (values.get("range") or "30d").strip()}
    if s["range"] not in METRIC_RANGES:
        raise AskRefused(f"{s['range']!r} is not one of the ranges: "
                         + ", ".join(METRIC_RANGES))
    for k, what in (("d", "a device"), ("i", "an interface")):
        if s[k] and not _NAME.match(s[k]):
            raise AskRefused(f"{s[k]!r} is not {what} name")
    if s["i"] and not s["d"]:
        raise AskRefused("an interface is asked of one device: choose the device first")
    return s


def metric_expr(key: str, s: dict) -> str:
    """The question's PromQL for these values."""
    q = METRICS[key]
    if not s["d"]:
        return q["by_device"]
    sel = f'device="{s["d"]}"' + (f',ifName="{s["i"]}"' if s["i"] else "")
    return q["by_interface"].format(sel=sel)


def metric_panel(key: str, s: dict) -> dict:
    """The question as a panel the chart draws: its PromQL, its unit and its legend."""
    q = METRICS[key]
    legend = "{{device}}" if not s["d"] else "{{ifName}}"
    return {"id": 0, "type": "timeseries", "title": q["title"],
            "fieldConfig": {"defaults": {"unit": q["unit"]}},
            "targets": [{"refId": "A", "expr": metric_expr(key, s), "legendFormat": legend}]}


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

    if key not in METRICS:
        return {"ok": False, "error": f"{key!r} is not a question"}, 404
    try:
        s = metric_ask(values)
    except AskRefused as exc:
        return {"ok": False, "error": str(exc)}, 400
    client, datasources, err = _grafana(list_name)
    if err:
        return {"ok": False, "error": err}, 503
    panel = metric_panel(key, s)
    seconds = METRIC_RANGES[s["range"]][1]
    default_ds = panels.default_datasource(datasources, "prometheus")
    st = panels.stores(datasources, list_name)
    try:
        body = panels.build_request(panel, {}, {}, seconds, default_ds, st)
    except panels.RangeRefused as exc:
        return {"ok": False, "error": str(exc)}, 400
    got = client.query(body)
    if not got.get("ok"):
        return {"ok": False, "error": f"Grafana: {got.get('error')}"}, 502
    payload = panels.render_payload(panel, got["body"], seconds)
    payload["errors"] = panels.answer_errors(got["body"])
    payload["store"] = panels.store_words(seconds, panel, {}, {}, default_ds, st)
    payload["asked"] = [metric_expr(key, s)]
    return payload, 200


def metric_view(key: str, list_name: str, values) -> dict:
    """What board B draws around the chart: the question, its devices and (for one device) its
    interfaces, the range, the stores that hold it, the source and the PromQL."""
    from modules import logs_page, panels

    q = METRICS[key]
    out = {"key": key, "q": q, "list": list_name, "ranges": METRIC_RANGES, "error": "",
           "devices": logs_page._devices(list_name), "interfaces": [], "interfaces_why": ""}
    try:
        s = metric_ask(values)
    except AskRefused as exc:
        s = {"d": "", "i": "", "range": "30d"}
        out["error"] = str(exc)
    out["s"] = s
    out["expr"] = metric_expr(key, s)
    client, datasources, err = _grafana(list_name)
    st = panels.stores(datasources, list_name) if not err else None
    seconds = METRIC_RANGES[s["range"]][1]
    out["live_days"] = (st.live // 86400) if st else None
    out["history_store"] = (st.history or {}).get("name", "") if st else ""
    out["past_live"] = bool(st and seconds > st.live)
    out["grafana_error"] = err
    if s["d"] and not err:
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
    return {"coverage": coverage(list_name), "questions": qs, "list": list_name}
