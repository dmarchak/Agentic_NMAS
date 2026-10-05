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
from typing import NamedTuple

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


def live_seconds() -> int:
    """How long the LIVE PromQL store keeps metrics (`metrics_live_retention_days`)."""
    try:
        from modules.list_settings import default_layer     # per network next (P.8 step 8)
        days = int(default_layer("metrics_live_retention_days", LIMITS["prometheus"][0] // 86400))
    except (TypeError, ValueError):
        days = LIMITS["prometheus"][0] // 86400
    return max(days, 1) * 86400


def history_store(datasources: list) -> tuple:
    """``(datasource or None, why)``: the HISTORY PromQL datasource a range past the live
    store's retention reads (C406, `grafana_history_datasource_uid`). None with why "" when
    none is set; None with the reason when the setting names one Grafana does not hold, or one
    that is not a PromQL datasource."""
    from modules.list_settings import default_layer         # per network next (P.8 step 8)
    uid = str(default_layer("grafana_history_datasource_uid", "") or "").strip()
    if not uid:
        return None, ""
    ds = next((d for d in datasources or [] if d.get("uid") == uid), None)
    if ds is None:
        return None, (f"the history datasource {uid} (grafana_history_datasource_uid) is not "
                      "one Grafana holds")
    if ds.get("type") != "prometheus":
        return None, (f"the history datasource {uid} is a {ds.get('type')} datasource, not "
                      "PromQL")
    return {"uid": uid, "type": "prometheus", "name": ds.get("name") or uid}, ""


def uses_history(seconds: int, backend: str, history) -> bool:
    """A PromQL range longer than the live store keeps, with a history store to read."""
    return backend == "prometheus" and history is not None and seconds > live_seconds()


def limit_words(datasources: list) -> str:
    """The range control's limit, said at the control: the live store's retention, and the
    history store that serves past it when one is set (C406)."""
    days = live_seconds() // 86400
    history, why = history_store(datasources)
    if history:
        return (f"The live store keeps {days} days; a longer range reads the history store "
                f"{history['name']}")
    return f"The live store keeps {days} days" + (f" ({why})" if why else "")


def store_words(seconds: int, panel: dict, dashboard: dict, values: dict, default_ds: dict,
                history) -> str:
    """Which store answered, said when it is not the live one (C406): "from the history store
    Thanos (lake): the live store keeps 90 days"; "" for the live store."""
    for t in panel.get("targets") or []:
        ds = datasource_for(t.get("datasource") or panel.get("datasource"), dashboard, values,
                            default_ds)
        if uses_history(seconds, ds.get("type", "prometheus"), history):
            return (f"from the history store {history['name']}: the live store keeps "
                    f"{live_seconds() // 86400} days")
    return ""


def check_range(seconds: int, backend: str, history=None, history_why: str = "") -> None:
    """Refuse a range past the backend's limit, naming it. A PromQL range past the LIVE
    store's retention is served by the history store when one is set (C406), never trimmed."""
    if backend == "prometheus":
        if seconds <= live_seconds() or history is not None:
            return
        days = live_seconds() // 86400
        raise RangeRefused(f"the live store keeps {days} days, and "
                           + (history_why or "no history store is set "
                                             "(grafana_history_datasource_uid)")
                           + f"; this range is {describe(seconds)}")
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


#: A metric name in a query: an identifier followed by its selector. PromQL
#: functions are followed by `(`, so they are not matched; a Loki stream
#: selector starts with `{` and names no metric.
_METRIC = re.compile(r"([A-Za-z_][A-Za-z0-9_:]*)\s*\{")
#: The model-driven telemetry series (Telegraf's Cisco IOS-XE plugin).
TELEMETRY_METRIC = re.compile(r"^Cisco_IOS_XE_[A-Za-z0-9_]+:")


def telemetry_only(panel: dict) -> bool:
    """Does this panel read ONLY model-driven telemetry? True when every
    target names a metric and every metric it names is a telemetry one. A
    panel with an SNMP fallback (`telemetry or (snmp unless ...)`) is not."""
    names = [n for t in panel.get("targets") or [] for n in _METRIC.findall(t.get("expr") or "")]
    return bool(names) and all(TELEMETRY_METRIC.match(n) for n in names)


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


def metrics_of(panel: dict) -> list:
    """Every metric name the panel's queries read."""
    return [n for t in panel.get("targets") or [] for n in _METRIC.findall(t.get("expr") or "")]


_SELECTOR = re.compile(r"([A-Za-z_][A-Za-z0-9_:]*)\s*\{([^{}]*)\}")


def selectors_of(panel: dict, values: dict) -> list:
    """The metric selectors the panel's queries ask with, its variables filled from *values*
    (``ifHCInOctets{device="r2"}``), each once, in the order written: what an empty panel says
    matched nothing (C412: "No interface counters from telemetry or SNMP" claimed an absence the
    page never measured)."""
    out = []
    for t in panel.get("targets") or []:
        for name, labels in _SELECTOR.findall(interpolate(t.get("expr") or "", values)):
            sel = f"{name}{{{labels.strip()}}}"
            if sel not in out:
                out.append(sel)
    return out


def series_request(panel: dict, dashboard: dict, values: dict, default_ds: dict,
                   seconds: int = 3600) -> dict:
    """ONE instant request: does anything match the panel's selectors for this device within
    *seconds*? Asked before a declared fold hides the panel (C412)."""
    sels = selectors_of(panel, values)
    t = dict((panel.get("targets") or [{}])[0])
    expr = "count(" + " or ".join(f"count_over_time({s}[{seconds}s])" for s in sels) + ")"
    probe = {"type": "stat", "targets": [dict(t, refId="S", expr=expr, instant=True)]}
    return build_request(probe, dashboard, values, seconds, default_ds)


# ---------------------------------------------------------------------------
# A panel that does not apply to THIS device folds (the operator, 2026-09-30).
# One rule for "nothing to show here": no source, not collected on this
# platform, or withheld by the panel's own condition. A panel that SHOULD
# show data and does not (a stopped stream, an erroring query, an empty
# answer where the device should report) never folds: it stays in place and
# says what is wrong. So every fold is DECLARED, never inferred from an empty
# answer.
# ---------------------------------------------------------------------------

class PlatformFold(NamedTuple):
    """A panel that reads ONLY these metrics is not applicable to a device
    whose model matches: measured, with its basis."""
    metrics: frozenset
    models: "re.Pattern"
    short: str
    basis: str


PLATFORM_FOLDS = (
    PlatformFold(
        frozenset({"cempMemPoolUsed", "cempMemPoolFree"}), re.compile(r"^vios", re.I),
        "not reported by vIOS",
        "measured on s3 by the operator, 2026-09-30: vIOS answers No Such Object for the "
        "memory tables (docs/PROMETHEUS_TARGETS.md); staged run 6 asks the older family, and "
        "this rule goes if it answers"),
    PlatformFold(
        frozenset({"cpmCPUTotal1minRev"}), re.compile(r"^vios", re.I),
        "not reported by vIOS",
        "measured on the host, read-only, 2026-10-04 (C429): s1 to s4 answer SNMP and none "
        "reports cpmCPUTotal1minRev, while all five C8000V routers do"),
)


def known_limit(panel: dict, model: str):
    """The declared platform rule that explains *panel* being empty on a device of *model*, or
    None: the rule covers every metric the panel reads, and the model matches it or is unknown
    (C429: a known platform limit leads with its reason, never the query). A model KNOWN not
    to match has no such excuse: its empty panel says what matched nothing."""
    names = set(metrics_of(panel))
    if not names:
        return None
    return next((r for r in PLATFORM_FOLDS
                 if names <= r.metrics and (not model or r.models.search(model))), None)


def platform_fold(panel: dict, model: str):
    """The declared rule that makes *panel* not applicable to a device of
    *model*, or None. The panel must read nothing BUT the rule's metrics, so a
    panel with another source is never folded by it; an unknown model folds
    nothing."""
    names = set(metrics_of(panel))
    if not names or not model:
        return None
    return next((r for r in PLATFORM_FOLDS if names <= r.metrics and r.models.search(model)),
                None)


#: A panel whose single query is `<value> and on(<labels>) (<condition>)`
#: withholds its value where its own condition does not hold: "Up for" is
#: shown only where the device's clock keeps real time.
_GUARD = re.compile(r"^(?P<value>.+?)\s+and\s+on\s*\([^()]*\)\s*\((?P<cond>.+)\)\s*$", re.S)

#: What a guard's condition is about, in the fold line's words; a guard not
#: named here reads "withheld by its own condition".
GUARD_WORDS = ((re.compile(r"(?:deriv|rate)\(\s*sysUpTime"), "slow clock"),)


def _balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            return False
    return depth == 0


def guard_of(panel: dict):
    """``{"value", "cond", "short"}`` when the panel's one query is guarded at
    its top level, else None."""
    targets = [t for t in panel.get("targets") or [] if (t.get("expr") or "").strip()]
    if len(targets) != 1:
        return None
    m = _GUARD.match(targets[0]["expr"].strip())
    if not m or not _balanced(m.group("value")) or not _balanced(m.group("cond")):
        return None
    short = next((w for rx, w in GUARD_WORDS if rx.search(m.group("cond"))),
                 "withheld by its own condition")
    return {"value": m.group("value").strip(), "cond": m.group("cond").strip(), "short": short,
            "expr": targets[0]["expr"], "target": targets[0]}


def guard_request(panel: dict, dashboard: dict, values: dict, default_ds: dict) -> dict:
    """ONE request asking both halves of a guarded panel now: the value alone
    (`V`) and the panel's own query (`F`)."""
    g = guard_of(panel)
    t = g["target"]
    probe = {"type": "stat", "targets": [dict(t, refId="V", expr=g["value"], instant=True),
                                         dict(t, refId="F", expr=g["expr"], instant=True)]}
    return build_request(probe, dashboard, values, 3600, default_ds)


def has_data(answer: dict, ref: str) -> bool:
    return any(s["ref"] == ref and any(v is not None for v in s["values"])
               for s in frames_to_series(answer, {}))


def withheld(answer: dict) -> bool:
    """The guard held the value back: the value exists and the guarded query
    returned nothing. Both empty is NOT withheld: the device should report
    and does not, which is the panel's to show."""
    return has_data(answer, "V") and not has_data(answer, "F")


def layout(drawn: list, folded=()) -> list:
    """The drawn panels placed as the dashboard places them: in (y, x) order,
    each with its gridPos column start (x, 0-23), width (w, 1-24) and height
    (h, in Grafana's 30 px units), and the heading of each Grafana row before
    its first drawn panel. Nothing is invented: rearranging the dashboard in
    Grafana rearranges the page (the operator, 2026-09-30).

    *folded*: the ids of panels that do not apply to this device. A line (the
    panels sharing a `y`) that lost one CLOSES UP: its remaining panels keep
    the dashboard's order, pack to the line's left edge and share the width
    the whole line took, in proportion to their own widths, so a fold never
    leaves a hole that reads as a panel failing to load. A line that lost
    nothing keeps its exact gridPos. A row whose panels all fold is gone,
    heading and all, because a heading is drawn only before a drawn panel."""
    def pos(p):
        g = p.get("gridPos") or {}
        return int(g.get("y") or 0), int(g.get("x") or 0)

    def geom(p):
        g = p.get("gridPos") or {}
        x = min(max(int(g.get("x") or 0), 0), 23)
        return x, min(max(int(g.get("w") or 24), 1), 24 - x), max(int(g.get("h") or 8), 3)

    folded = set(folded or ())
    lines = {}
    for p in drawn:
        lines.setdefault(((p.get("row") or ""), pos(p)[0]), []).append(p)
    place = {}
    for members in lines.values():
        members.sort(key=pos)
        kept = [p for p in members if p.get("id") not in folded]
        if len(kept) == len(members) or not kept:
            for p in kept:
                place[id(p)] = geom(p)[:2]
            continue
        start = min(geom(p)[0] for p in members)
        span = max(geom(p)[0] + geom(p)[1] for p in members) - start
        weights = [geom(p)[1] for p in kept]
        widths = [max(1, span * w // sum(weights)) for w in weights]
        widths[-1] += span - sum(widths)                # the rounding lands on the last
        x = start
        for p, w in zip(kept, widths):
            place[id(p)] = (x, w)
            x += w

    out, row = [], None
    for p in sorted((p for p in drawn if p.get("id") not in folded), key=pos):
        if (p.get("row") or "") != row:
            row = p.get("row") or ""
            if row:
                out.append({"kind": "row", "title": row})
        x, w = place[id(p)]
        out.append({"kind": "panel", "panel": p, "x": x, "w": w, "h": geom(p)[2]})
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


def build_request(panel: dict, dashboard: dict, values: dict, seconds: int, default_ds: dict,
                  history=None, history_why: str = "") -> dict:
    """The body for Grafana's `api/ds/query`, bounded: the range, the step,
    the most points. Only the dashboard's own queries; the browser never
    supplies an expression on this path. A PromQL range past the live store's retention reads
    *history* (C406), the same expression on the store that keeps it."""
    step = step_for(seconds)
    queries = []
    for t in panel.get("targets") or []:
        if not (t.get("expr") or "").strip():
            continue
        ds = datasource_for(t.get("datasource") or panel.get("datasource"), dashboard, values, default_ds)
        check_range(seconds, ds.get("type", "prometheus"), history, history_why)
        if uses_history(seconds, ds.get("type", "prometheus"), history):
            ds = {"uid": history["uid"], "type": "prometheus"}
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


#: The panel types this app draws itself from an `api/ds/query` answer. Any
#: other (an alert list, a text panel, a logs panel) holds no series to draw:
#: it keeps its place on the page and says Grafana draws it, never an empty
#: chart that reads as no data (the operator, 2026-10-01: the fleet dashboard
#: rcn-lab-overview holds all three).
NATIVE_TYPES = frozenset({"timeseries", "stat", "gauge", "bargauge", "table", "state-timeline"})


def drawn_elsewhere(layout: list, uid: str, grafana_url: str = "") -> list:
    """Mark each panel of *layout* this app does not draw with the words and,
    where Grafana's address is known, the link that opens it there."""
    for item in layout:
        p = item.get("panel") or {}
        if item.get("kind") == "panel" and p.get("type") not in NATIVE_TYPES:
            item["elsewhere"] = {
                "words": f"A {p.get('type') or 'typeless'} panel: Grafana draws it, this page does not.",
                "href": (f"{grafana_url.rstrip('/')}/d/{uid}?viewPanel={p.get('id')}" if grafana_url else "")}
    return layout


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
    # VALUE MAPPINGS travel with the payload and are applied where the value
    # is drawn: a stat's value, a table's column, a stepped series' axis.
    mappings = list(panel.get("mappings") or [])
    # The panel's words for an empty answer (Grafana's noValue).
    out["no_value"] = str(panel.get("no_value") or "")
    if panel.get("type") == "table":
        keys = sorted({k for s in shown for k in s["labels"] if k not in ("__name__", "instance", "job")})
        # The panel's own `organize` step, as Grafana applies it: columns it
        # excludes are dropped and those it renames drawn by their new name.
        # Grafana calls the value column `Value`; with no organize step it
        # keeps the name it always had here.
        org = panel.get("organize") or {}
        exclude, rename = set(org.get("exclude") or []), dict(org.get("rename") or {})
        src = [k for k in keys if k not in exclude] + ["Value"]
        names = [rename.get(k, k) for k in src]
        if not org:
            names[-1] = "value"
        fields = panel.get("field_mappings") or {}
        out["columns"] = names
        out["rows"] = [[s["labels"].get(k, "") for k in src[:-1]] + [s["values"][-1] if s["values"] else None]
                       for s in shown]
        out["column_mappings"] = [fields.get(n) or fields.get(k) or (mappings if k == "Value" else [])
                                  for k, n in zip(src, names)]
    elif panel.get("type") in ("stat", "gauge", "bargauge"):
        last = [s["values"][-1] for s in shown if s["values"] and s["values"][-1] is not None]
        out["value"] = last[0] if len(last) == 1 else (sum(last) if last else None)
        out["thresholds"] = panel.get("thresholds") or []
        out["mappings"] = mappings
        # The one series' own label (its legend): which source the value is
        # from, drawn under the value.
        labelled = [s["label"] for s in shown if s["values"] and s["values"][-1] is not None]
        out["label"] = labelled[0] if len(labelled) == 1 else ""
        # NEVER AN IMPOSSIBLE VALUE (the operator, 2026-10-01: the clock rate
        # read -2475% after s3's reboot). A stat whose panel declares its
        # valid range (Grafana's min and max) draws words, never a number
        # outside it: a reading outside what the quantity can be is a failed
        # measurement, not a measurement.
        span = valid_range(panel)
        if span and out["value"] is not None and not (span[0] <= out["value"] <= span[1]):
            out["implausible"] = {"value": out["value"], "range": list(span),
                                  "words": f"Not a valid reading (outside {_range_words(span, out['unit'])}): "
                                           "measuring"}
            out["value"] = None
    else:
        out["series"] = [{"label": s["label"], "times": s["times"], "values": s["values"]} for s in shown]
        out["mappings"] = mappings
    return out


# ---------------------------------------------------------------------------
# A stat's valid range, and a restart that explains a reading outside it.
# ---------------------------------------------------------------------------

def valid_range(panel: dict):
    """``(low, high)`` when the panel declares both Grafana's ``min`` and
    ``max`` (the builder sets them only where the quantity has a physical
    range: a percentage, a clock rate), else None."""
    lo, hi = panel.get("min"), panel.get("max")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo < hi:
        return float(lo), float(hi)
    return None


def _range_words(span: tuple, unit: str) -> str:
    lo, hi = span
    if unit == "percentunit":
        return f"{lo * 100:g}–{hi * 100:g}%"
    if unit == "percent":
        return f"{lo:g}–{hi:g}%"
    return f"{lo:g}–{hi:g}"


def reads_uptime(panel: dict) -> bool:
    """Does the panel compute from sysUpTime (so a restart explains a reading
    outside its range)?"""
    return any("sysUpTime" in (t.get("expr") or "") for t in panel.get("targets") or [])


def restart_panel(panel: dict, variable: str) -> dict:
    """A synthetic panel asking for the device's own sysUpTime, on the panel's
    data source, so the restart can be found where the reading came from."""
    return {"type": "timeseries", "datasource": panel.get("datasource"),
            "targets": [{"refId": "R", "expr": f'sysUpTime{{device="${variable}"}}',
                         "datasource": (panel.get("targets") or [{}])[0].get("datasource")}]}


def last_restart(answer: dict):
    """When the device last restarted, from a sysUpTime series: the newest
    point where the count dropped, less the uptime it then read (the device's
    own ticks, so about). None when no drop is in the answer."""
    best = None
    for s in frames_to_series(answer, {}):
        vals, times = s["values"], s["times"]
        for i in range(1, len(vals)):
            if vals[i] is not None and vals[i - 1] is not None and vals[i] < vals[i - 1]:
                at = times[i] - vals[i] / 100.0
                best = at if best is None or at > best else best
    return best
