"""The sidebar's Logs: the network's syslog as it arrives (C675; board D, `LogsTail.dc.html`,
drawn 2026-10-11 under the Phase 7 mode). Everything here is the logs-tail reader's stored
window (modules/readers/logs_tail.py), filtered in memory: never a Loki call per view.

- counts for the whole window first (lines, by severity, devices), whatever the filters;
- the filters (device, severity, mnemonic, text), named as the syslog view names them (`d`,
  `sev`, `mn`, `text`), so History › Query's "Open these lines on Logs" arrives filtered and
  "older than 15 minutes" goes back with the same filters;
- the newest ``SHOWN`` matching lines, newest first, a cut list saying so;
- paused (`paused=<the read time>` in the address): the window as it was, and how many matching
  lines arrived since; Resume is the same address without it;
- the store's states each said: never read, not configured, unreadable, and the last read
  failing (the last good window drawn with its error and age).
"""

import calendar
import logging
import time
from urllib.parse import urlencode

log = logging.getLogger(__name__)

READER = "logs-tail"
SHOWN = 200
SEVERITIES = {"all": ("every severity", 7), "warning": ("warning or worse", 4),
              "error": ("error or worse (0 to 3)", 3)}
ASKS = {"d": "", "sev": "all", "mn": "", "text": "", "paused": "", "from": ""}


def ask(values) -> dict:
    s = {k: (values.get(k) or "").strip() or v for k, v in ASKS.items()}
    s["sev"] = s["sev"] if s["sev"] in SEVERITIES else "all"
    s["mn"] = s["mn"].upper()
    s["text"] = s["text"][:120]
    return s


def qs(list_name: str, s: dict, over: dict = None) -> str:
    merged = dict(s, **(over or {}))
    pairs = [("list", list_name)] + [(k, merged[k]) for k, v in ASKS.items()
                                     if merged.get(k) and merged[k] != v]
    return "?" + urlencode(pairs)


def _ts(iso: str) -> float:
    try:
        return float(calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return 0.0


def matches(line: dict, s: dict) -> bool:
    if s["d"] and line.get("dev") != s["d"]:
        return False
    sev = line.get("sev")
    if s["sev"] != "all" and (sev is None or sev > SEVERITIES[s["sev"]][1]):
        return False
    if s["mn"] and s["mn"] not in (line.get("mn") or ""):
        return False
    if s["text"] and s["text"].lower() not in (line.get("text") or "").lower():
        return False
    return True


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
        return {"state": "not_configured", "why": "no log store is configured for this network"}
    return {"state": "ok", "value": value, "value_at": last.get("value_at", ""),
            "failed": failed, "failed_at": attempt.get("at", "") if failed else ""}


def view(list_name: str, values, now: float = None) -> dict:
    now = time.time() if now is None else now
    s = ask(values)
    st = stored(list_name)
    out = {"list": list_name, "s": s, "state": st["state"], "why": st.get("why", ""),
           "failed": st.get("failed", ""), "failed_at": st.get("failed_at", ""),
           "severities": SEVERITIES,
           "qs": lambda over=None: qs(list_name, s, over)}
    if st["state"] != "ok":
        return out
    v = st["value"]
    window = v.get("lines") or []
    paused = _ts(s["paused"]) if s["paused"] else 0.0
    shown_from = [l for l in window if not paused or l.get("ts", 0) <= paused]
    hits = [l for l in shown_from if matches(l, s)]
    counts = {"error": 0, "warning": 0, "other": 0}
    for l in window:
        sev = l.get("sev")
        counts["error" if sev is not None and sev <= 3 else "warning" if sev == 4 else "other"] += 1
    read_at = v.get("read_at", "")
    out.update(
        lines=hits[:SHOWN], matching=len(hits), total=len(window), counts=counts,
        devices=sorted({l.get("dev") for l in window if l.get("dev")}),
        truncated=bool(v.get("truncated")), window_minutes=int(v.get("window_seconds", 900)) // 60,
        read_at=read_at, age_s=max(int(now - _ts(read_at)), 0) if read_at else None,
        newest_at=window[0].get("at", "") if window else "",
        paused_at=s["paused"] if paused else "",
        new_since=sum(1 for l in window if paused and l.get("ts", 0) > paused and matches(l, s)),
        filtered=any(s[k] for k in ("d", "mn", "text")) or s["sev"] != "all",
        from_query=s["from"] == "query",
        older={k: s[k] for k in ("d", "mn", "text")} | {"sev": "all" if s["sev"] == "all" else
                                                          s["sev"], "range": "24h"})
    return out
