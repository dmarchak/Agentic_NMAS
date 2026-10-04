"""A chronic alert acknowledged WITHIN ITS MEASURED BAND (C433; the operator's decision,
2026-10-04).

An alert that is always on stops meaning anything: s3's output discards on Gi1/1 were above
their rule's 0.1 pps threshold in 64% of 5-minute windows over 7 days, so the row was read as
noise, and a real change on that port would look the same. A person acknowledges such a row
with a reason; the acknowledgement records the series' 7-day p95 as its BAND, and it holds
only while the series' value stays inside that band. When the value leaves it, the row comes
back naming the band and the value. One rule for every chronic row, never per device.

The value is the rule's own query: its PromQL (query A) with its trailing threshold removed,
narrowed to the alert's series by its labels. Only a rule whose query A is PromQL with one
trailing numeric comparison can be banded; any other says why it cannot.
"""

import logging
import re

log = logging.getLogger(__name__)

WINDOW = "7d"
STEP = "5m"
QUANTILE = 0.95
#: The labels Grafana adds to an alert instance that its query's series does not carry.
NOT_SERIES = frozenset({"alertname", "grafana_folder", "__alert_rule_uid__", "rulename"})

_TRAILING = re.compile(r"\s*(?:>=|<=|==|!=|>|<)\s*(?:bool\s+)?[-+]?(?:\d+\.?\d*|\.\d+)"
                       r"(?:[eE][-+]?\d+)?\s*$")


def value_expr(expr: str) -> str:
    """The rule's PromQL without its trailing threshold (`... > 0.1` gives `...`), or ""
    when the query ends in no numeric comparison: it cannot be banded."""
    expr = (expr or "").strip()
    m = _TRAILING.search(expr)
    if not m or m.start() == 0:
        return ""
    return expr[:m.start()].strip()


def series_key(rule_uid: str, labels: dict) -> str:
    """One alert series, stable across its re-fires: the rule and its labels, sorted."""
    pairs = sorted((k, v) for k, v in (labels or {}).items() if k not in NOT_SERIES)
    return f"{rule_uid}|" + ",".join(f"{k}={v}" for k, v in pairs)


def _matching(result: list, labels: dict):
    """The one series of *result* whose every label equals the alert's, or None."""
    for row in result or []:
        metric = {k: v for k, v in (row.get("metric") or {}).items() if k != "__name__"}
        if metric and all(labels.get(k) == v for k, v in metric.items()):
            return row
    return None


def _ask(expr: str, labels: dict, prom=None) -> tuple:
    """``(value, "")`` for *expr*'s series matching *labels*, or ``(None, why)``."""
    if prom is None:
        from modules.integrations.prometheus import PrometheusIntegration
        prom = PrometheusIntegration()
    if not prom.is_configured():
        return None, "Prometheus is not configured"
    got = prom._get("api/v1/query", query=expr)
    if not got.get("ok"):
        return None, f"Prometheus could not be asked: {got.get('error')}"
    result = ((got["response"].json() or {}).get("data") or {}).get("result") or []
    row = _matching(result, labels)
    if row is None:
        return None, (f"Prometheus holds no series of the rule's query with this alert's "
                      f"labels ({len(result)} series answered)")
    try:
        return float(row["value"][1]), ""
    except (KeyError, IndexError, TypeError, ValueError):
        return None, "Prometheus answered a value that is not a number"


def band(vexpr: str, labels: dict, prom=None) -> tuple:
    """``(p95, "")``: the series' 95th percentile over the last 7 days at 5-minute steps,
    measured now; or ``(None, why)``."""
    if not vexpr:
        return None, "the rule's query is not PromQL ending in a threshold, so it has no band"
    return _ask(f"quantile_over_time({QUANTILE}, ({vexpr})[{WINDOW}:{STEP}])", labels, prom)


def current(vexpr: str, labels: dict, prom=None) -> tuple:
    """``(value, "")``: the series' value now, or ``(None, why)``."""
    if not vexpr:
        return None, "the rule's query is not PromQL ending in a threshold"
    return _ask(vexpr, labels, prom)


def words(b: float) -> str:
    """A band in a person's words: the number, and what it is."""
    return f"{b:.3g} (its 7-day 95th percentile when acknowledged)"
