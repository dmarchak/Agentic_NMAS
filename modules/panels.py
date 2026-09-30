"""Grafana panels, rendered by the app from the dashboard's own definition
(NSOT_GUI_BRIEF 14.2): which panels a device page draws, the variables that
fill their queries, the bounded range and step, the request sent to Grafana's
`api/ds/query`, and its answer turned into series a chart can draw.

Pure where it can be, so each rule is tested on its own against REAL captures
(tests/fixtures/grafana/): the `rcn-lab1-snmp` model and three real answers.

**Nothing here invents a panel.** The panels are the dashboard's; the app
only decides which of them it may draw on a device page, and says why it left
the others out.
"""

import re

#: The ranges offered as one click, and the words for them.
PRESETS = {"15m": 900, "1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}

#: The longest range each backend serves, MEASURED on the host 2026-09-30
#: (NSOT_GUI_BRIEF 14.2): Prometheus keeps 90 days; Loki's
#: `max_query_length` is 30d1h. A range past it is refused naming it, never
#: trimmed: a trimmed answer reads as the whole range.
LIMITS = {"prometheus": (90 * 86400, "Prometheus keeps 90 days"),
          "loki": (30 * 86400 + 3600, "Loki serves at most 30 days 1 hour a query")}

#: Readable steps, and the most points a series is asked for.
STEPS = (15, 30, 60, 120, 300, 600, 900, 1800, 3600, 10800, 21600, 43200, 86400)
MAX_POINTS = 1000
#: The most series one panel draws. More are drawn up to this and SAID.
MAX_SERIES = 200

_RELATIVE = re.compile(r"^\s*(?:last\s+)?(\d{1,4})\s*(m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)\s*$", re.I)
_UNIT = {"m": 60, "h": 3600, "d": 86400}


class RangeRefused(ValueError):
    """A range the app will not ask for, with the reason in words."""


def parse_range(text: str) -> int:
    """A preset key (`1h`) or a relative range (`last 90 minutes`, `3d`), in
    seconds. Anything else is refused by name."""
    text = (text or "1h").strip()
    if text in PRESETS:
        return PRESETS[text]
    m = _RELATIVE.match(text)
    if not m or int(m.group(1)) == 0:
        raise RangeRefused(f"{text!r} is not a range: use a preset or 'last N minutes, hours or days'")
    return int(m.group(1)) * _UNIT[m.group(2)[0].lower()]


def step_for(seconds: int) -> int:
    """The step: the range over at most MAX_POINTS points, rounded up to a
    readable unit, never below 15 s."""
    need = seconds / MAX_POINTS
    for s in STEPS:
        if s >= need:
            return s
    return STEPS[-1]


def check_range(seconds: int, backend: str) -> None:
    """Refuse a range past the backend's measured limit, naming the limit."""
    limit = LIMITS.get(backend)
    if limit and seconds > limit[0]:
        raise RangeRefused(f"{limit[1]}; this range is {describe(seconds)}")


def describe(seconds: int) -> str:
    """`90 minutes`, `3 days`: the range in words."""
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds % size == 0 and seconds >= size:
            n = seconds // size
            return f"{n} {unit}{'s' if n != 1 else ''}"
    return f"{seconds} seconds"


def uses_variable(expr: str, name: str) -> bool:
    """Does a query reference the variable (`$device` or `${device}`)?"""
    return bool(re.search(r"\$(?:\{%s(?::[^}]*)?\}|%s\b)" % (re.escape(name), re.escape(name)), expr or ""))


def split_device_panels(dashboard: dict, variable: str) -> tuple:
    """(drawn, left_out): the panels a device page draws, those whose query
    references the device variable, and every other panel with why it was
    left out. Rows are neither: they are layout."""
    drawn, left_out = [], []
    for p in dashboard.get("panels") or []:
        if p.get("type") == "row":
            continue
        exprs = [t.get("expr") or "" for t in p.get("targets") or []]
        if any(uses_variable(e, variable) for e in exprs):
            drawn.append(p)
        elif not exprs or not any(exprs):
            left_out.append({"panel": p, "reason": "this panel runs no query to filter"})
        else:
            left_out.append({"panel": p, "reason": "this panel's query does not select by device",
                             "query": exprs[0]})
    return drawn, left_out


def layout(drawn: list) -> list:
    """The drawn panels placed as the dashboard places them: in (y, x) order,
    each with its gridPos column start (x, 0-23), width (w, 1-24) and height
    (h, in Grafana's 30 px units), and the heading of each Grafana row before
    its first drawn panel. Nothing is invented: rearranging the dashboard in
    Grafana rearranges the page (the operator, 2026-09-30)."""
    def pos(p):
        g = p.get("gridPos") or {}
        return int(g.get("y") or 0), int(g.get("x") or 0)

    out, row = [], None
    for p in sorted(drawn, key=pos):
        g = p.get("gridPos") or {}
        if (p.get("row") or "") != row:
            row = p.get("row") or ""
            if row:
                out.append({"kind": "row", "title": row})
        x = min(max(int(g.get("x") or 0), 0), 23)
        w = min(max(int(g.get("w") or 24), 1), 24 - x)
        out.append({"kind": "panel", "panel": p, "x": x, "w": w,
                    "h": max(int(g.get("h") or 8), 3)})
    return out


def variable_of(dashboard: dict, name: str):
    for v in dashboard.get("variables") or []:
        if v.get("name") == name:
            return v
    return None


def dashboards_with_variable(dashboards: dict, name: str) -> list:
    """The dashboards a device page may offer: only those with the variable."""
    return sorted((d for d in dashboards.values() if variable_of(d, name)),
                  key=lambda d: d.get("title", "").lower())


def interpolate(expr: str, values: dict) -> str:
    """Fill `$name` and `${name}` from *values*. A variable not in *values*
    is left as written, so Grafana's own macros (`$__rate_interval`) reach
    Grafana, whose back end expands them (measured)."""
    def sub(m):
        name = m.group(1) or m.group(2)
        return values[name] if name in values else m.group(0)
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[^}]*)?\}|\$([A-Za-z_][A-Za-z0-9_]*)", sub, expr or "")


def default_datasource(datasources: list, kind: str = "prometheus") -> dict:
    """The data source a variable of that plugin type resolves to when it has
    no current value: Grafana's default if it is of that type, else the first
    of that type. Empty when there is none, which the caller says."""
    of_kind = [d for d in datasources or [] if d.get("type") == kind]
    pick = next((d for d in of_kind if d.get("is_default")), of_kind[0] if of_kind else None)
    return {"uid": pick["uid"], "type": pick["type"]} if pick else {}


def variable_values(dashboard: dict, device_var: str, device_value: str,
                    datasources: list = ()) -> dict:
    """Every variable a device page fills: the device variable with the
    device, a text box with its written default, a data source with its
    current value or the default of its plugin type, and any other with its
    current value (`$__all` as `.*`)."""
    out = {}
    for v in dashboard.get("variables") or []:
        name = v.get("name")
        if name == device_var:
            out[name] = device_value
        elif v.get("type") == "textbox":
            out[name] = v.get("query") or (v.get("current") or "")
        elif v.get("type") == "datasource" and not v.get("current"):
            ds = default_datasource(datasources, v.get("query") or "prometheus")
            if ds:
                out[name] = ds["uid"]
        else:
            cur = v.get("current")
            if isinstance(cur, list):
                cur = cur[0] if len(cur) == 1 else ".*"
            if cur in (None, "", "$__all"):
                cur = ".*" if v.get("type") != "datasource" else ""
            if cur != "":
                out[name] = str(cur)
    return out


def datasource_for(ref, dashboard: dict, values: dict, default: dict) -> dict:
    """A target's data source, `{uid, type}`: its own, the panel's, a
    variable's value, or the default data source."""
    if isinstance(ref, dict) and ref.get("uid"):
        uid = interpolate(ref["uid"], values)
        if uid.startswith("$") or uid == "":
            return dict(default)
        return {"uid": uid, "type": ref.get("type") or default.get("type", "prometheus")}
    return dict(default)


def build_request(panel: dict, dashboard: dict, values: dict, seconds: int, default_ds: dict) -> dict:
    """The body for Grafana's `api/ds/query`, bounded: the range, the step,
    the most points. Only the dashboard's own queries; the browser never
    supplies an expression on this path."""
    step = step_for(seconds)
    queries = []
    for t in panel.get("targets") or []:
        if not (t.get("expr") or "").strip():
            continue
        ds = datasource_for(t.get("datasource") or panel.get("datasource"), dashboard, values, default_ds)
        check_range(seconds, ds.get("type", "prometheus"))
        instant = bool(t.get("instant")) or panel.get("type") == "table"
        queries.append({"refId": t.get("refId") or "A", "datasource": ds,
                        "expr": interpolate(t["expr"], values),
                        "legendFormat": t.get("legendFormat") or "",
                        "range": not instant, "instant": instant,
                        "intervalMs": step * 1000, "maxDataPoints": MAX_POINTS})
    return {"queries": queries, "from": f"now-{seconds}s", "to": "now"}


def _label(field: dict, legend: str) -> str:
    labels = field.get("labels") or {}
    if legend:
        return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", lambda m: str(labels.get(m.group(1), "")), legend)
    shown = {k: v for k, v in labels.items() if k != "__name__"}
    return ", ".join(f"{k}={v}" for k, v in sorted(shown.items())) or field.get("name") or "value"


def frames_to_series(answer: dict, legends: dict) -> list:
    """Every series in Grafana's answer: its label, its times in SECONDS and
    its values. A frame with no rows is no series (C232's empty answer)."""
    out = []
    for ref, res in ((answer or {}).get("results") or {}).items():
        for frame in res.get("frames") or []:
            fields = (frame.get("schema") or {}).get("fields") or []
            values = (frame.get("data") or {}).get("values") or []
            if len(fields) < 2 or len(values) < 2 or not values[0]:
                continue
            times = [t / 1000.0 for t in values[0]]
            for f, vals in zip(fields[1:], values[1:]):
                out.append({"ref": ref, "label": _label(f, legends.get(ref, "")),
                            "labels": f.get("labels") or {}, "times": times, "values": vals})
    return out


def answer_errors(answer: dict) -> list:
    """Grafana's per-query errors, each naming its query."""
    return [f"{ref}: {res.get('error')}" for ref, res in ((answer or {}).get("results") or {}).items()
            if res.get("error")]


def render_payload(panel: dict, answer: dict, seconds: int) -> dict:
    """What the browser draws: the panel's type, title and unit, and its
    series (a time series), its rows (a table) or its value (a stat), with the
    range and step it was asked for. Bounded, and a cut is said."""
    legends = {t.get("refId") or "A": t.get("legendFormat") or "" for t in panel.get("targets") or []}
    series = frames_to_series(answer, legends)
    shown = series[:MAX_SERIES]
    out = {"ok": True, "type": panel.get("type"), "title": panel.get("title"),
           "unit": panel.get("unit") or "", "range": describe(seconds), "step": step_for(seconds),
           "series_total": len(series), "series_shown": len(shown),
           "note": (f"{len(series)} series: the first {MAX_SERIES} are drawn" if len(series) > MAX_SERIES else "")}
    if panel.get("type") == "table":
        keys = sorted({k for s in shown for k in s["labels"] if k not in ("__name__", "instance", "job")})
        out["columns"] = keys + ["value"]
        out["rows"] = [[s["labels"].get(k, "") for k in keys] + [s["values"][-1] if s["values"] else None]
                       for s in shown]
    elif panel.get("type") in ("stat", "gauge", "bargauge"):
        last = [s["values"][-1] for s in shown if s["values"] and s["values"][-1] is not None]
        out["value"] = last[0] if len(last) == 1 else (sum(last) if last else None)
        out["thresholds"] = panel.get("thresholds") or []
    else:
        out["series"] = [{"label": s["label"], "times": s["times"], "values": s["values"]} for s in shown]
    return out
