"""modules/logs_page.py — the Logs view: the network's syslog by device (C652; History › Query
board C, `AskLogs.dc.html`, "Syslog by device", signed off 2026-10-04; compared region by region
in docs/fidelity/logs.md).

The counts are the `logs-summary` reader's, kept per day (modules/readers/logs_summary.py): this
sums the days the range asks for and never counts per request. A device opened draws its lines
from the `logs-tail` reader's buffer (modules/logs_buffer.py, its last 24 h; C3166: no page load
waits on Loki), filtered by severity, mnemonic, time and text; only when the range reaches before
what the buffer holds, and it holds fewer than a page, the lines before it are one Loki query of
at most 50 lines from at most 30 days (Loki's query limit), asked by a part of the page after it
has drawn (`older`, `logs_v2.older`), each line masked before it is drawn.

The coverage is said, never implied: a range reaching before the store's first line, or past
the network's Logs retention, says how many of its days hold nothing and why; Loki holding lines
older than the retention says the setting may be lower than what Loki keeps; days the reader is
still counting are said as such.
"""

import calendar
import logging
import re
import time
from urllib.parse import urlencode

from modules.device_logs import mnemonic

log = logging.getLogger(__name__)

READER = "logs-summary"
RANGES = {"24h": ("24 h", 1), "7d": ("7 d", 7), "30d": ("30 d", 30), "120d": ("120 d", 120)}
SEVERITIES = {"error": ("error or worse (0 to 3)", 3), "warning": ("warning or worse", 4),
              "all": ("every severity", 7)}
#: A device's lines drawn at once, and Loki's longest single query (its `max_query_length`,
#: 30 days 1 hour, measured on the lab's Loki 2026-10-10).
PAGE = 50
WINDOW_DAYS = 30
#: How many mnemonics the trend draws, the most frequent first (the board draws two).
TREND_SERIES = 3
ASKS = {"range": "7d", "sev": "error", "d": "", "mn": "", "text": "", "from": "", "to": "",
        "before": ""}


def ask(values) -> dict:
    s = {k: (values.get(k) or "").strip() or v for k, v in ASKS.items()}
    s["range"] = s["range"] if s["range"] in RANGES else "7d"
    s["sev"] = s["sev"] if s["sev"] in SEVERITIES else "error"
    return s


def qs(list_name: str, s: dict, over: dict = None) -> str:
    merged = dict(s, **(over or {}))
    pairs = [("list", list_name)] + [(k, merged[k]) for k, v in ASKS.items()
                                     if merged.get(k) and merged[k] != v]
    return "?" + urlencode(pairs)


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def _ts(day: str) -> float:
    return float(calendar.timegm(time.strptime(day, "%Y-%m-%d")))


def _sev(mn: str):
    from modules.device_logs import mnemonic_severity
    return mnemonic_severity(mn)


def _devices(list_name: str) -> list:
    """The network's device names: the inventory, read with no I/O to a device."""
    from modules.readers.adjacencies import lists
    for name, _ref, hosts in lists():
        if name == list_name:
            return sorted(hosts)
    return []


def stored(list_name: str) -> dict:
    from modules import reader_job

    got = reader_job.read_cached_for(READER, list_name)
    state = got.get("state")
    if state in ("not_applicable", "not_configured", "unreadable"):
        return {"state": state, "why": got.get("why") or "the reader's store could not be read"}
    doc = got.get("doc") or {}
    last = doc.get("last_good") or {}
    attempt = doc.get("last_attempt") or {}
    failed = "" if attempt.get("ok", True) else (attempt.get("error") or "the last read failed")
    if not last:
        return {"state": "never", "failed": failed}
    value = last.get("value") or {}
    if not value.get("configured"):
        return {"state": "not_configured", "why": "Loki is not configured for this network"}
    return {"state": "ok", "value": value, "value_at": last.get("value_at", ""),
            "failed": failed}


def view(list_name: str, values, now: float = None) -> dict:
    """Everything the Logs view draws for one network and question."""
    s = ask(values)
    now = time.time() if now is None else now
    out = {"list": list_name, "s": s, "qs": lambda over=None: qs(list_name, s, over),
           "ranges": RANGES, "severities": SEVERITIES}
    st = stored(list_name)
    out.update(state=st["state"], why=st.get("why", ""), failed=st.get("failed", ""),
               value_at=st.get("value_at", ""))
    if st["state"] != "ok":
        return out
    v = st["value"]
    words, n_days = RANGES[s["range"]]
    limit = SEVERITIES[s["sev"]][1]
    mine = set(_devices(list_name))
    today = v.get("today") or _day(now)
    if s["range"] == "24h":
        span = [("", v.get("last_24h") or {})]
        start_day = _day(now - 86400)
    else:
        start_day = _day(_ts(today) - (n_days - 1) * 86400)
        span = [(d, c) for d, c in (v.get("days") or {}).items() if start_day <= d <= today]
    table, others = {}, 0
    for day, by_dev in span:
        for dev, mns in by_dev.items():
            for mn, n in mns.items():
                sev = _sev(mn)
                if sev is None or sev > limit:
                    continue
                if dev not in mine:
                    others += n
                    continue
                row = table.setdefault(dev, {"device": dev, "lines": 0, "mn": {}, "days": {}})
                row["lines"] += n
                row["mn"][mn] = row["mn"].get(mn, 0) + n
                if day:
                    row["days"].setdefault(day, {})[mn] = row["days"].get(day, {}).get(mn, 0) + n
    rows = []
    for dev, row in table.items():
        top = max(row["mn"].items(), key=lambda kv: (kv[1], kv[0]))
        # Newest at the severity asked: the exact time when the reader saw it, else the last day
        # the counts hold a line at it (the board's "2 Oct"), never a line of another severity.
        seen = [iso for sev, iso in ((v.get("newest") or {}).get(dev) or {}).items()
                if isinstance(iso, str) and sev.isdigit() and int(sev) <= limit]
        last_day = max(row["days"]) if row["days"] else ""
        row.update(top=top[0], top_n=top[1], newest=max(seen) if seen else "",
                   newest_day=time.strftime("%-d %b", time.gmtime(_ts(last_day)))
                   if last_day else "")
        if row["newest"] and last_day and row["newest"][:10] < last_day:
            row["newest"] = ""          # the counts know a later day than the lines seen
        rows.append(row)
    rows.sort(key=lambda r: (-r["lines"], r["device"]))
    out.update(rows=rows, total=sum(r["lines"] for r in rows), others=others,
               quiet=sorted(mine - set(table)), range_words=words,
               sev_words=SEVERITIES[s["sev"]][0])
    out["coverage"] = _coverage(v, start_day, today, n_days if s["range"] != "24h" else 1)
    out["retention_days"] = v.get("retention_days")
    out["first_day"] = v.get("first_day", "")
    if s["d"]:
        out["open"] = _open(list_name, s, next((r for r in rows if r["device"] == s["d"]), None),
                            v, start_day, today, now, mine)
    return out


def _coverage(v: dict, start_day: str, today: str, n_days: int) -> dict:
    """What the range can hold: days before the store's first line, days past the retention,
    days still being counted, and Loki holding more than the retention says."""
    first = v.get("first_day") or ""
    retention = int(v.get("retention_days") or 90)
    kept_from = _day(_ts(today) - (retention - 1) * 86400)
    out = {"before_store": 0, "past_retention": 0, "counting": 0, "older_than_setting": False,
           "first": first, "retention": retention}
    d = _ts(start_day)
    while _day(d) <= today:
        day = _day(d)
        if day < kept_from:
            out["past_retention"] += 1
        elif first and day < first:
            out["before_store"] += 1
        elif day not in (v.get("days") or {}):
            out["counting"] += 1
        d += 86400
    out["older_than_setting"] = bool(first and first < kept_from)
    out["whole"] = not (out["before_store"] or out["past_retention"] or out["counting"])
    out["days"] = n_days
    return out


_TEXT_OK = re.compile(r"^[^`\"\\\r\n]{0,120}$")
_MN_OK = re.compile(r"^%" + mnemonic() + "$")
_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?$")


def _when(text: str, default: float):
    """``(epoch, error)`` from "YYYY-MM-DD", "YYYY-MM-DD HH:MM" (UTC) or "now"."""
    text = (text or "").strip()
    if not text or text == "now":
        return default, ""
    if not _WHEN.match(text):
        return default, f"{text!r} is not a time this reads: write 2026-10-04 or 2026-10-04 09:30 (UTC), or now"
    fmt = "%Y-%m-%d %H:%M" if " " in text else "%Y-%m-%d"
    return float(calendar.timegm(time.strptime(text, fmt))), ""


def _bounds(s: dict, start_day: str, now: float) -> tuple:
    """``(start, end, errors)``: the opened device's window, from its range, From, To and the
    page's `before`, and what in the address cannot be read."""
    errors = []
    start, e1 = _when(s["from"], _ts(start_day) if s["range"] != "24h" else now - 86400)
    end, e2 = _when(s["to"], now)
    if s["before"]:
        try:
            end = min(end, int(s["before"]) / 1e9)
        except ValueError:
            pass
    for e in (e1, e2):
        if e:
            errors.append(e)
    if s["mn"] and not _MN_OK.match(s["mn"]):
        errors.append(f"{s['mn']!r} is not a mnemonic (%FACILITY-SEVERITY-NAME)")
    if not _TEXT_OK.match(s["text"]):
        errors.append("the text may not hold a quote, a backtick or a backslash, and is "
                      "at most 120 characters")
    return start, end, errors


def _row(e: dict) -> dict:
    """A held line (modules/logs_buffer.py) as the opened device draws one."""
    from modules import device_logs

    row = device_logs._held_row(e)                      # noqa: SLF001 (one row shape)
    row["at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(row["ns"] / 1e9))
    return row


def _matches(e: dict, s: dict) -> bool:
    """Whether a held line answers the filters as the Loki query's stages would: a mnemonic at
    or worse than the severity, the mnemonic chosen, and the text in the line."""
    limit = SEVERITIES[s["sev"]][1]
    sev = _sev(e.get("mn") or "")
    if limit < 7 and (sev is None or sev > limit):
        return False
    line = " ".join(x for x in (e.get("devts"), e.get("mn"), e.get("text")) if x)
    if s["mn"] and s["mn"] not in line:
        return False
    return not s["text"] or s["text"] in line


def _open(list_name, s, row, v, start_day, today, now, mine) -> dict:
    """A device opened: its filters, the trend by mnemonic, and its lines: those the logs-tail
    reader's buffer holds (C3166: never Loki on the request), and, when the range reaches
    before the buffer and it holds fewer than a page, ``older``: the part that asks Loki for
    the lines before it, after the page has drawn (`older`, `logs_v2.older`)."""
    from modules import device_logs, logs_buffer

    dev = s["d"]
    out = {"device": dev, "errors": [], "lines": [], "row": row}
    if dev not in mine or not device_logs._NAME.match(dev):        # noqa: SLF001
        out["errors"].append(f"{dev} is not a device of {list_name}")
        return out
    out["mnemonics"] = sorted((row or {}).get("mn", {}).items(), key=lambda kv: (-kv[1], kv[0]))
    # From the first day counted: before the store's first line the range holds nothing, and a
    # day the reader has not counted yet is unknown, never zero (the notice says both).
    counted = min(v.get("days") or {today: 0})
    out["trend"] = _trend(row, max(start_day, v.get("first_day") or start_day, counted), today, s)
    start, end, out["errors"] = _bounds(s, start_day, now)
    if out["errors"]:
        return out
    out["cut_window"] = end - start > WINDOW_DAYS * 86400
    start = max(start, end - WINDOW_DAYS * 86400)
    out["window"] = (time.strftime("%Y-%m-%d %H:%M", time.gmtime(start)),
                     time.strftime("%Y-%m-%d %H:%M", time.gmtime(end)))
    # The whole count is known only for the range as kept, whole days and no text.
    if row and not (s["text"] or s["from"] or s["to"] or s["before"]):
        out["matching"] = row["mn"].get(s["mn"], 0) if s["mn"] else row["lines"]
    h = logs_buffer.held(list_name, dev, now=now)
    out["held"] = device_logs._held_words(h, "lines")             # noqa: SLF001
    held_from = end
    if h["state"] == "ok":
        held_from = min(end, h["cover"]["lines"]["from"] or end)
        lo, hi = int(max(start, held_from) * 1e9), int(end * 1e9)
        rows = [_row(e) for e in h["lines"] if lo <= int(e.get("ns") or 0) < hi
                and _matches(e, s)]
        out["lines"] = rows[:PAGE]
        if len(rows) >= PAGE:
            out["more"] = True
            out["next_before"] = str(rows[PAGE - 1]["ns"] - 1)
            return out
    out["more"] = False
    out["next_before"] = ""
    if start < held_from:
        # The boundary on the next whole minute, so the part's question stays the same while
        # the buffer moves under it, and `older` answers it from what it asked (`OLDER_KEEP`);
        # the held lines are drawn from the same boundary, so none is drawn twice or missed.
        edge = min(end, -(-held_from // 60) * 60)
        if h["state"] == "ok":
            lo = int(max(start, edge) * 1e9)
            out["lines"] = [r for r in out["lines"] if r["ns"] >= lo]
        out["older"] = {"before": str(int(edge * 1e9)),
                        "from_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(edge))}
    return out


#: How long an older part's answer is kept, per question (the device, its filters, the range and
#: the boundary): the boundary moves by whole minutes, so a region redrawn when the logs reader
#: announces (every 5 s while lines arrive) asks Loki at most once a minute for it. The most
#: kept, the oldest let go first.
OLDER_KEEP = 60
OLDER_MOST = 256
_OLDER = {}


def older(list_name: str, values, now: float = None) -> dict:
    """The opened device's lines older than the buffer (`_open`'s ``older``): one Loki query of
    at most `PAGE` lines before `before`, in the range and filters asked. The part a page asks
    for after it has drawn, never the page (C3166: "only a query older than the buffer goes to
    Loki, as a part of the page that says 'loading older lines'"); the same question within
    `OLDER_KEEP` seconds is answered from what was asked (``asked_at`` says when). Never
    raises."""
    s = ask(values)
    now = time.time() if now is None else now
    key = (list_name, tuple(sorted(s.items())))
    got = _OLDER.get(key)
    if got and now - got[0] < OLDER_KEEP:
        return got[1]
    out = _older(list_name, s, now)
    if not out["errors"]:
        _OLDER[key] = (now, out)
        while len(_OLDER) > OLDER_MOST:
            _OLDER.pop(min(_OLDER, key=lambda k: _OLDER[k][0]))
    return out


def _older(list_name: str, s: dict, now: float) -> dict:
    from modules import device_logs
    from modules.integrations.loki import LokiIntegration
    from modules.redact import redact_text

    out = {"qs": lambda over=None: qs(list_name, s, over),
           "device": s["d"], "errors": [], "lines": [], "more": False, "next_before": "",
           "asked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))}
    dev = s["d"]
    if dev not in set(_devices(list_name)) or not device_logs._NAME.match(dev):  # noqa: SLF001
        out["errors"].append(f"{dev or 'no device'} is not a device of {list_name}")
        return out
    _words, n_days = RANGES[s["range"]]
    start_day = _day(now - 86400) if s["range"] == "24h" else _day(_ts(_day(now))
                                                                   - (n_days - 1) * 86400)
    start, end, out["errors"] = _bounds(s, start_day, now)
    if not s["before"]:
        out["errors"].append("no time to read before was given")
    if out["errors"]:
        return out
    start = max(start, end - WINDOW_DAYS * 86400)
    if end <= start:
        return out
    loki = LokiIntegration(list_name=list_name)
    try:
        sel = device_logs.selector(dev, start=start, client=loki)
    except device_logs.NoSyslogJob as exc:
        out["errors"].append(f"The syslog job could not be found: {exc}")
        return out
    q = f"{sel} !~ `{device_logs.HEARTBEAT_LINE}`"
    limit = SEVERITIES[s["sev"]][1]
    if limit < 7:
        q += f' |~ `%{mnemonic(f"[0-{limit}]")}`'
    if s["mn"]:
        q += f' |= "{s["mn"]}"'
    if s["text"]:
        q += f' |= "{s["text"]}"'
    r = loki._get("loki/api/v1/query_range", query=q, limit=PAGE,       # noqa: SLF001
                  start=str(int(start * 1e9)), end=str(int(end * 1e9)), direction="backward")
    if not r.get("ok"):
        out["errors"].append(f"Loki could not be asked for {dev}'s lines: {r.get('error')}")
        return out
    try:
        streams = (r["response"].json().get("data") or {}).get("result") or []
    except ValueError as exc:
        out["errors"].append(f"Loki's answer could not be read: {exc}")
        return out
    rows = []
    for stream in streams:
        for ns, line in stream.get("values") or []:
            p = device_logs.parse(redact_text(line), dev)
            p.update(ns=int(ns), at=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(ns) / 1e9)))
            rows.append(p)
    rows.sort(key=lambda r_: r_["ns"], reverse=True)
    # What the part draws of each line, and no more (its time, severity, mnemonic, text).
    out["lines"] = [{k: r_.get(k) for k in ("at", "sev", "sev_word", "kind", "mnemonic", "text")}
                    for r_ in rows[:PAGE]]
    out["more"] = len(rows) >= PAGE
    out["next_before"] = str(rows[-1]["ns"] - 1) if rows else ""
    return out


def _trend(row, start_day, today, s) -> dict:
    """Lines per day for the device's most frequent mnemonics, as SVG points (1000 x 130)."""
    if not row or s["range"] == "24h":
        return {}
    days = []
    d = _ts(start_day)
    while _day(d) <= today:
        days.append(_day(d))
        d += 86400
    if len(days) < 3:
        return {}
    names = [mn for mn, _n in sorted(row["mn"].items(), key=lambda kv: (-kv[1], kv[0]))]
    if s["mn"]:
        names = [s["mn"]] if s["mn"] in row["mn"] else []
    names = names[:TREND_SERIES]
    series = {mn: [row["days"].get(day, {}).get(mn, 0) for day in days] for mn in names}
    top = max([max(v) for v in series.values()] + [1])
    step = 10 ** max(len(str(top)) - 1, 0)
    ymax = ((top + step - 1) // step) * step
    out = []
    for i, mn in enumerate(names):
        pts = " ".join(f"{round(j * 1000 / (len(days) - 1))},{round(130 - n * 130 / ymax)}"
                       for j, n in enumerate(series[mn]))
        out.append({"mnemonic": mn, "points": pts, "series": i, "total": sum(series[mn])})
    ticks = [days[0], days[len(days) // 3], days[2 * len(days) // 3], days[-1]]
    return {"series": out, "ymax": ymax, "ymid": ymax // 2,
            "xticks": [time.strftime("%-d %b", time.gmtime(_ts(t))) for t in ticks],
            "from": days[0], "to": days[-1]}
