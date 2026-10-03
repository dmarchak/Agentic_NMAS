"""Coverage's NOT-REPORTING reader (NSOT_GUI_BRIEF 14.3; artboard A, signed off 2026-10-02):
for every device, when each monitoring source last ARRIVED, so Coverage can say of a
configured template "its data is not arriving" and name for how long.

ONE QUERY PER SOURCE FOR THE WHOLE FLEET (enterprise scale), never one per device:

- **SNMP and IP SLA**: Prometheus's active targets, once. A target is the tool's when it
  carries a `device` label and came from a file `prometheus_targets` generates (its
  `__meta_filepath`); IP SLA's are the ones from `nmas-snmp-ipsla.json`, the rest are
  SNMP. Beside it, ONE query for each device's and job's last successful scrape
  (`up == 1`) within the lookback, which says for how long a failing target has failed.
- **Telemetry**: ONE query for each `source`'s last minute with a series (the Cisco MDT
  tag Telegraf sets; docs/PROMETHEUS_TARGETS.md).
- **Syslog** and **the heartbeat**: ONE Loki query each, the device's name pulled from
  each line by :data:`NAME_RX`, counted per minute over the lookback; the last minute
  with a line is its last arrival.

Measured on the host, 2026-10-03: the five queries took 0.02 to 0.14 s for nine devices;
:data:`NAME_RX` named exactly the devices, with exactly the counts, that the anchored
per-device query of `device_logs` names (3,326 lines over 24 h, no other name).

It stores ARRIVALS only, never a verdict: whether a template is configured is the
committed golden's, read by `monitoring_coverage`, which calls :func:`judge` for each
configured cell. A source that cannot be asked is said, and the rest are kept.
"""

import os
import time

from modules import reader_job

NAME = "coverage-reporting"
INTERVAL_SECONDS = 60
#: How far back an arrival is looked for; older reads "over 3 h" (the board's longest).
LOOKBACK_SECONDS = 3 * 3600
STEP_SECONDS = 60
#: Telemetry streams every 10 s (docs/PROMETHEUS_TARGETS.md); none for 5 min is a
#: stream that stopped, not one late update (the rule proposed and signed with board A).
TELEMETRY_SILENT_SECONDS = 300
#: A target unscraped for twice its interval is one Prometheus has stopped scraping.
SCRAPE_INTERVALS = 2
#: The device's name in a syslog line: the name `logging origin-id hostname` puts after
#: IOS's sequence number. The same name `device_logs` anchors on (C13), never rsyslog's
#: hostname field.
NAME_RX = r"\d+:\s(?P<dev>[A-Za-z][A-Za-z0-9._-]*):\s"
TELEMETRY_SELECTOR = '{source!=""}'
IPSLA_FILE = "nmas-snmp-ipsla.json"

#: Where each template's cause is looked for: the device page's tab (board A).
WHERE = {"snmp": "monitoring", "ip_sla": "monitoring", "telemetry": "monitoring",
         "syslog": "logs", "heartbeat": "logs"}


def _ages_words(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 90:
        return f"{s} s"
    if s < 90 * 60:
        return f"{round(s / 60)} min"
    return f"{round(s / 3600)} h"


def _epoch(iso: str):
    from datetime import datetime
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _interval(text: str) -> float:
    from modules.prometheus_targets import seconds
    return seconds(text or "", default=60.0)


def _json(r: dict, what: str):
    if not r.get("ok"):
        raise RuntimeError(f"{what} could not be asked: {r.get('error')}")
    try:
        body = r["response"].json()
    except ValueError as exc:
        raise RuntimeError(f"{what}'s answer could not be read: {exc}") from exc
    if body.get("status") not in (None, "success"):
        raise RuntimeError(f"{what} refused the query: {body.get('error') or body.get('status')}")
    return body.get("data") or {}


# ── the sources: each returns its part of the value, or raises naming itself ──

def targets(prom) -> dict:
    """``{device: [{job, file, health, last_scrape, interval, error}]}``."""
    from modules.prometheus_targets import PREFIX
    from modules.redact import redact_text

    data = _json(prom._get("api/v1/targets", state="active"), "Prometheus's targets")
    out = {}
    for t in data.get("activeTargets") or []:
        labels = t.get("labels") or {}
        path = os.path.basename((t.get("discoveredLabels") or {}).get("__meta_filepath") or "")
        host = labels.get("device")
        if not host or not path.startswith(PREFIX):
            continue
        out.setdefault(host, []).append({
            "job": labels.get("job") or "", "file": path, "health": t.get("health") or "",
            "last_scrape": _epoch(t.get("lastScrape")),
            "interval": _interval(t.get("scrapeInterval")),
            "error": redact_text(t.get("lastError") or "")[:200]})
    return out


def _instant(prom, query: str, what: str, now: float) -> list:
    return _json(prom._get("api/v1/query", query=query, time=now), what).get("result") or []


def last_up(prom, now: float) -> dict:
    """``{device: {job: epoch}}``: each target's last successful scrape in the lookback."""
    q = (f'max by (device, job) (max_over_time(timestamp(up{{device!=""}} == 1)'
         f'[{LOOKBACK_SECONDS}s:{STEP_SECONDS}s]))')
    out = {}
    for r in _instant(prom, q, "Prometheus's last good scrapes", now):
        m = r.get("metric") or {}
        out.setdefault(m.get("device"), {})[m.get("job") or ""] = float(r["value"][1])
    return out


def telemetry(prom, now: float) -> dict:
    """``{device: epoch}``: the last minute each source had a series."""
    q = (f"max by (source) (max_over_time(timestamp(count by (source) ({TELEMETRY_SELECTOR}))"
         f"[{LOOKBACK_SECONDS}s:{STEP_SECONDS}s]))")
    return {(r.get("metric") or {}).get("source"): float(r["value"][1])
            for r in _instant(prom, q, "Prometheus's telemetry series", now)}


def _loki_last(loki, extra: str, what: str, now: float) -> dict:
    q = (f'sum by (dev) (count_over_time({{job="{_job()}"}}{extra} | regexp `{NAME_RX}` '
         f"[{STEP_SECONDS}s]))")
    data = _json(loki._get("loki/api/v1/query_range", query=q,
                           start=int((now - LOOKBACK_SECONDS) * 1e9), end=int(now * 1e9),
                           step=STEP_SECONDS), what)
    out = {}
    for s in data.get("result") or []:
        dev = (s.get("metric") or {}).get("dev")
        stamps = [float(ts) for ts, v in s.get("values") or [] if float(v) > 0]
        if dev and stamps:
            # A minute's point counts the lines BEFORE it; an aligned point can sit past
            # now, and an arrival is never in the future.
            out[dev] = min(max(stamps), now)
    return out


def _job() -> str:
    from modules.device_logs import JOB
    return JOB


def syslog(loki, now: float) -> dict:
    return _loki_last(loki, "", "Loki's syslog lines", now)


def heartbeat(loki, now: float) -> dict:
    from modules.device_logs import HEARTBEAT_LINE
    return _loki_last(loki, f" |~ `{HEARTBEAT_LINE}`", "Loki's heartbeat lines", now)


def windows() -> dict:
    """``{device: {window, basis}}``: the heartbeat window each device's ALERT uses, from
    the rules Grafana loads, so Coverage and the alert never disagree. Unreadable is said;
    absent is an empty map (the period's own window applies)."""
    import yaml

    from modules import heartbeat_windows as HW
    try:
        with open(HW.INSTALLED, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}
    got = HW._script().installed(doc)
    return {h: {"window": w, "basis": b} for h, (w, b, _uid) in got.items()}


def read(now: float = None, prom=None, loki=None) -> dict:
    from modules.integrations.loki import LokiIntegration
    from modules.integrations.prometheus import PrometheusIntegration
    from modules.settings_schema import get_setting

    now = time.time() if now is None else now
    prom = prom or PrometheusIntegration()
    loki = loki or LokiIntegration()
    value = {"read_at": now, "lookback_seconds": LOOKBACK_SECONDS,
             "heartbeat_period": int(get_setting("syslog_heartbeat_seconds") or 0),
             "sources": {}}
    plan = (("targets", prom, lambda: targets(prom)), ("up", prom, lambda: last_up(prom, now)),
            ("telemetry", prom, lambda: telemetry(prom, now)),
            ("syslog", loki, lambda: syslog(loki, now)),
            ("heartbeat", loki, lambda: heartbeat(loki, now)),
            ("windows", None, windows))
    for key, client, fn in plan:
        if client is not None and not client.is_configured():
            value["sources"][key] = {"ok": False, "error": f"{client.label} is not configured"}
            continue
        try:
            value[key] = fn()
            value["sources"][key] = {"ok": True, "error": ""}
        except Exception as exc:                        # noqa: BLE001
            value["sources"][key] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if not any(s["ok"] for k, s in value["sources"].items() if k != "windows"):
        raise RuntimeError("no source could be asked: " + "; ".join(
            f"{k}: {s['error']}" for k, s in value["sources"].items() if not s["ok"]))
    return value


# ── the judgement, for monitoring_coverage ──────────────────────────────────

def _cell(state, words, column) -> dict:
    out = {"state": state, "words": words}
    if state == "not_reporting":
        out["where"] = WHERE[column]
    return out


def _since(at, value, now) -> str:
    if at is None:
        return f"over {_ages_words(value.get('lookback_seconds') or LOOKBACK_SECONDS)}"
    return _ages_words(now - at)


def _source_down(value, *keys):
    for k in keys:
        s = (value.get("sources") or {}).get(k) or {}
        if not s.get("ok"):
            return s.get("error") or f"the {k} source was not read"
    return ""


def _targets(value, host, column, now) -> dict:
    down = _source_down(value, "targets", "up")
    if down:
        return _cell("unjudged", f"whether it reports is unknown: {down}", column)
    mine = [t for t in (value.get("targets") or {}).get(host) or []
            if (t["file"] == IPSLA_FILE) == (column == "ip_sla")]
    if not mine:
        what = "IP SLA target" if column == "ip_sla" else "SNMP target"
        return _cell("not_reporting", f"not scraped: Prometheus has no {what} for it", column)
    ups = ((value.get("up") or {}).get(host) or {})
    failing = []
    for t in mine:
        last = ups.get(t["job"])
        if t["health"] != "up":
            failing.append((t["job"], last, t["error"]))
        elif t["last_scrape"] is None or now - t["last_scrape"] > SCRAPE_INTERVALS * t["interval"]:
            failing.append((t["job"], t["last_scrape"], "Prometheus has stopped scraping it"))
    if not failing:
        newest = max((t["last_scrape"] or 0) for t in mine)
        return _cell("reporting", f"scraped {_ages_words(now - newest)} ago", column)
    if len(failing) == len(mine):
        last = max((f[1] for f in failing if f[1] is not None), default=None)
        why = next((f[2] for f in failing if f[2]), "")
        return _cell("not_reporting", f"no scrape for {_since(last, value, now)}"
                     + (f" ({why})" if why else ""), column)
    names = ", ".join(sorted(f[0] for f in failing))
    last = max((f[1] for f in failing if f[1] is not None), default=None)
    return _cell("not_reporting", f"{names} not scraped for {_since(last, value, now)}; "
                 "the rest answer", column)


def heartbeat_window(value, host) -> tuple:
    """(seconds, basis words): the device's alert window, else twice the period."""
    w = (value.get("windows") or {}).get(host)
    if w:
        return int(w["window"]), f"its alert's {w['basis']} window"
    period = int(value.get("heartbeat_period") or 0)
    return (2 * period, "twice the heartbeat period") if period else (0, "")


def judge(column: str, host: str, value, now: float = None,
          stale_after: int = None, heartbeat_configured: bool = False) -> dict:
    """``{state, words[, where]}`` for one CONFIGURED cell: ``reporting``,
    ``not_reporting`` (its data is not arriving; *where* is the device tab to diagnose it),
    ``unproven`` (syslog with no heartbeat: nothing proves the path, and silence is not a
    fault) or ``unjudged`` (the reader's value is missing, stale, or its source unread:
    never "not reporting", which would accuse every device of the reader's failure)."""
    now = time.time() if now is None else now
    if value is None:
        return _cell("unjudged", "whether it reports is unknown: no reading yet", column)
    age = now - float(value.get("read_at") or 0)
    stale_after = stale_after or INTERVAL_SECONDS * reader_job.STALE_AFTER_INTERVALS
    if age > stale_after:
        return _cell("unjudged", "whether it reports is unknown: the last reading is "
                     f"{_ages_words(age)} old", column)
    if column in ("snmp", "ip_sla"):
        return _targets(value, host, column, now)
    if column == "telemetry":
        down = _source_down(value, "telemetry")
        if down:
            return _cell("unjudged", f"whether it reports is unknown: {down}", column)
        at = (value.get("telemetry") or {}).get(host)
        if at is not None and now - at <= TELEMETRY_SILENT_SECONDS:
            return _cell("reporting", f"streaming, a series {_ages_words(now - at)} ago", column)
        return _cell("not_reporting", f"no stream for {_since(at, value, now)}", column)
    window, basis = heartbeat_window(value, host)
    if column == "heartbeat":
        down = _source_down(value, "heartbeat")
        if down:
            return _cell("unjudged", f"whether it reports is unknown: {down}", column)
        if not window:
            return _cell("unjudged", "whether it beats is unknown: no heartbeat period is set",
                         column)
        at = (value.get("heartbeat") or {}).get(host)
        if at is not None and now - at <= window:
            return _cell("reporting", f"beating, the last {_ages_words(now - at)} ago", column)
        return _cell("not_reporting", f"none for {_since(at, value, now)} "
                     f"({basis}: {_ages_words(window)})", column)
    if column == "syslog":
        down = _source_down(value, "syslog")
        if down:
            return _cell("unjudged", f"whether it reports is unknown: {down}", column)
        at = (value.get("syslog") or {}).get(host)
        if heartbeat_configured and window:
            if at is not None and now - at <= window:
                return _cell("reporting", f"a line {_ages_words(now - at)} ago", column)
            return _cell("not_reporting", f"no lines for {_since(at, value, now)}", column)
        if at is not None and window and now - at <= window:
            return _cell("reporting", f"a line {_ages_words(now - at)} ago", column)
        return _cell("unproven", "nothing proves it arrives: no heartbeat, and "
                     + ("no line in " + _since(None, value, now) if at is None
                        else f"the last line {_ages_words(now - at)} ago"), column)
    raise ValueError(f"no reporting rule for {column!r}")


#: The arrival times move every minute; a page redraws only when a verdict could (rule 9).
KEEPALIVE_SECONDS = 300


def signature(value: dict) -> dict:
    """What Coverage's verdicts are made from, without the times that move every read: each
    source's state, each target's health and staleness, and whether each device's stream,
    heartbeat and last line fall inside their windows."""
    value = value or {}
    now = float(value.get("read_at") or 0)
    sig = {"sources": {k: s.get("ok") for k, s in (value.get("sources") or {}).items()}}
    sig["targets"] = {h: sorted((t["job"], t["health"], t["last_scrape"] is None or
                                 now - t["last_scrape"] > SCRAPE_INTERVALS * t["interval"])
                                for t in ts)
                      for h, ts in (value.get("targets") or {}).items()}
    sig["telemetry"] = sorted(h for h, at in (value.get("telemetry") or {}).items()
                              if now - at <= TELEMETRY_SILENT_SECONDS)
    for key in ("heartbeat", "syslog"):
        sig[key] = sorted(h for h, at in (value.get(key) or {}).items()
                          if now - at <= heartbeat_window(value, h)[0])
    return sig


def changed(previous: dict, value: dict) -> bool:
    return signature(previous) != signature(value)


READER = reader_job.register(reader_job.Reader(
    name=NAME,
    what="when each device's monitoring data last arrived (SNMP, IP SLA, telemetry, syslog, "
         "the heartbeat), for Coverage's not-reporting cells",
    endpoints=("Prometheus: GET /api/v1/targets", "Prometheus: GET /api/v1/query (2 queries)",
               "Loki: GET /loki/api/v1/query_range (2 queries)",
               "this host: the heartbeat rules Grafana loads"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the shortest window judged is telemetry's 5 min; a minute names a "
                    "stopped source within a fifth of it, and the five queries took 0.02 to "
                    "0.14 s for nine devices (measured 2026-10-03)"),
    read=read,
    invalidates=("coverage_reporting",),
    remedy="Read the error above: it names which of Prometheus or Loki could not be asked",
    window="the last 3 h of arrivals",
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
