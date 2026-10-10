"""The fleet's syslog, counted per day, for the Logs view (C652; History › Query board C,
"Syslog by device", signed off 2026-10-04, NSOT_STAGE7_PLAN 13 and 15).

**Why a reader.** Counting the fleet's lines by device and severity took 0.45 s for a day, 1.4 s
for 7 days and 9.4 s for 30 days on the lab's Loki, and Loki refuses one query longer than 30
days 1 hour (measured 2026-10-10, C652): a 120-day view asked per request would take about 40 s.
So this reads each day ONCE, keeps its counts, and re-reads only today and the last 24 h; the
page sums what is kept. A device's own lines are one bounded query when a person opens it.

**What is kept, per Loki configuration** (P.8: one store per distinct configuration):
- ``days``: each UTC day's lines by device and mnemonic (the severity is the mnemonic's digit),
  heartbeats left out (by their exact line form, as the device page's Logs tab leaves them);
- ``last_24h``: the same for the 24 hours before the read;
- ``unparsed``: lines the fields do not match (no device name or mnemonic), per day;
- ``newest``: each device's newest line seen, from the lines since the last read;
- ``first_day``: the store's first line, found once, so the page can say a range reaches past
  what was ever kept.

**Bounded per read:** today, the last 24 h, the newest lines, and at most ``BACKFILL_PER_READ``
past days not yet kept, newest first, inside this network's Logs retention
(`logs_retention_days`). A day older than the retention is dropped.
"""

import logging
import re
import time

from modules import reader_job

log = logging.getLogger(__name__)

READER_NAME = "logs-summary"
#: A day costs about 0.45 s (measured 2026-10-10), so a read stays under about 6 s.
BACKFILL_PER_READ = 7
#: Lines change by the second; a Logs view five minutes behind answers "what happened" questions.
INTERVAL_SECONDS = 300
KEEPALIVE_SECONDS = 1800
#: How far back the store's first line is looked for, at most (the lab keeps 2 years).
FIRST_LOOKBACK_DAYS = 760
#: One Loki query spans at most 30 days 1 hour (its `max_query_length`, measured 2026-10-10).
WINDOW_DAYS = 30
#: The newest lines read each time, for each device's newest (more than a read's worth).
NEWEST_LIMIT = 2000


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def selector() -> str:
    from modules import device_logs
    return f'{{job="{device_logs.JOB}"}} !~ `{device_logs.HEARTBEAT_LINE}`'


def count_query(seconds: int) -> str:
    """Every line in the *seconds* before the query's time, by device and mnemonic."""
    from modules import device_logs
    return (f"sum by (dev, mn) (count_over_time({selector()} | regexp "
            f"`{device_logs.LOGQL_FIELDS}` [{int(seconds)}s]))")


def counts(answer: list) -> tuple:
    """``({device: {mnemonic: n}}, unparsed)`` from a count query's result."""
    out, unparsed = {}, 0
    for row in answer or []:
        m = row.get("metric") or {}
        try:
            n = int(float(row["value"][1]))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        dev, mn = m.get("dev"), m.get("mn")
        if not dev or not mn:
            unparsed += n
            continue
        out.setdefault(dev, {})[mn] = out.get(dev, {}).get(mn, 0) + n
    return out, unparsed


class _Loki:
    """One configuration's Loki, asked through the integration client (its auth and TLS)."""

    def __init__(self, list_name: str):
        from modules.integrations.loki import LokiIntegration
        self.client = LokiIntegration(list_name=list_name) if list_name else LokiIntegration()

    def configured(self) -> bool:
        return self.client.is_configured()

    def ask(self, path: str, **params) -> list:
        r = self.client._get(path, **params)          # noqa: SLF001 (the client's one GET)
        if not r.get("ok"):
            raise RuntimeError(f"Loki could not be asked ({path}): {r.get('error')}")
        try:
            return (r["response"].json().get("data") or {}).get("result") or []
        except ValueError as exc:
            raise RuntimeError(f"Loki's answer to {path} could not be read: {exc}") from exc


def _first_day(loki, now: float) -> str:
    """The day of the store's first line: 30-day windows forward from the furthest look-back,
    the first window that holds a line answering."""
    start = now - FIRST_LOOKBACK_DAYS * 86400
    while start < now:
        end = min(start + WINDOW_DAYS * 86400, now)
        got = loki.ask("loki/api/v1/query_range", query=f'{{job="{_job()}"}}', limit=1,
                       start=str(int(start * 1e9)), end=str(int(end * 1e9)),
                       direction="forward")
        stamps = [int(v[0]) for s in got for v in s.get("values") or []]
        if stamps:
            return _day(min(stamps) / 1e9)
        start = end
    return ""


def _job() -> str:
    from modules import device_logs
    return device_logs.JOB


_LINE_DEVICE = None


def _device_of(line: str) -> str:
    global _LINE_DEVICE                               # noqa: PLW0603 (compiled once)
    if _LINE_DEVICE is None:
        from modules import device_logs
        _LINE_DEVICE = re.compile(device_logs.LOGQL_FIELDS)
    m = _LINE_DEVICE.search(line)
    return m.group("dev") if m else ""


def read(list_name: str = "", loki=None, clock=time.time, previous=None,
         retention_days=None) -> dict:
    """One configuration's counts, the previous value carried forward (see the module)."""
    loki = loki or _Loki(list_name)
    if not loki.configured():
        return {"configured": False}
    now = clock()
    if previous is None:
        got = reader_job.read_cached_for(READER_NAME, list_name or _default())
        previous = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    if retention_days is None:
        retention_days = _retention(list_name)
    today = _day(now)
    oldest_kept = _day(now - (retention_days - 1) * 86400)
    days = {d: v for d, v in (previous.get("days") or {}).items() if oldest_kept <= d < today}
    unparsed = {d: n for d, n in (previous.get("unparsed") or {}).items() if d in days}
    first_day = previous.get("first_day") or _first_day(loki, now)

    def day_counts(end: float, seconds: int):
        return counts(loki.ask("loki/api/v1/query", query=count_query(seconds),
                               time=str(int(end))))

    midnight = now - now % 86400
    days[today], unparsed[today] = day_counts(now, max(int(now - midnight), 1))
    # The past, newest first: each day not yet kept, inside the retention and since the first
    # line, at most BACKFILL_PER_READ a read.
    missing = []
    d = midnight - 86400
    while _day(d) >= oldest_kept and (not first_day or _day(d) >= first_day):
        if _day(d) not in days:
            missing.append(d)
        d -= 86400
    for start in missing[:BACKFILL_PER_READ]:
        days[_day(start)], unparsed[_day(start)] = day_counts(start + 86400, 86400)
    last_24h, unparsed_24h = day_counts(now, 86400)
    newest = dict(previous.get("newest") or {})
    since = (previous.get("read_at_ts") or (now - 86400))
    lines = loki.ask("loki/api/v1/query_range", query=selector(), limit=NEWEST_LIMIT,
                     start=str(int(since * 1e9)), end=str(int(now * 1e9)), direction="backward")
    for stream in lines:
        for ts, line in stream.get("values") or []:
            dev = _device_of(line)
            if dev and int(ts) / 1e9 > _ts(newest.get(dev)):
                newest[dev] = _iso(int(ts) / 1e9)
    return {"configured": True, "first_day": first_day, "retention_days": retention_days,
            "today": today, "days": dict(sorted(days.items())), "unparsed": unparsed,
            "last_24h": last_24h, "unparsed_24h": unparsed_24h, "newest": newest,
            "days_missing": max(len(missing) - BACKFILL_PER_READ, 0),
            "read_at": _iso(now), "read_at_ts": now}


def _ts(iso: str) -> float:
    if not iso:
        return 0.0
    import calendar
    return float(calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")))


def _default() -> str:
    from modules.list_settings import DEFAULT_LIST
    return DEFAULT_LIST


def _retention(list_name: str) -> int:
    from modules.list_settings import value
    try:
        return max(int(value(list_name or _default(), "logs_retention_days", 90)), 1)
    except (TypeError, ValueError):
        return 90


def changed(previous, value) -> bool:
    """Announce when the counts moved, never for the read's own time."""
    strip = lambda v: {k: x for k, x in (v or {}).items()              # noqa: E731
                       if k not in ("read_at", "read_at_ts")}
    return strip(previous) != strip(value)


READER = reader_job.register(reader_job.Reader(
    name=READER_NAME,
    what="the fleet's syslog counted per day by device and mnemonic, for the Logs view (C652)",
    endpoints=("Loki: GET /loki/api/v1/query (today, the last 24 h, and up to 7 past days, each "
               "one count by device and mnemonic)",
               "Loki: GET /loki/api/v1/query_range (the lines since the last read, for each "
               "device's newest; the store's first line, once)"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("a day's count took 0.45 s on the lab's Loki (2026-10-10); five minutes keeps "
                    "the view current for questions asked in hours and days"),
    read=read,
    invalidates=("logs",),
    remedy="Read the error above: it names what Loki answered",
    window="each UTC day inside the network's Logs retention, today to the read, and the 24 h "
           "before the read",
    per_group=("loki",),
    read_for=lambda list_name: read(list_name=list_name),
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
