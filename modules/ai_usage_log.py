"""ai_usage_log.py

Server-side, cross-session log of AI agent token usage and spend.

The chat UI shows a per-turn cost badge, but that number only lives in the
browser and resets on reload. Every run_chat() turn also appends one JSON
line here (append-only, so it's cheap and crash-safe) regardless of which UI
session or background job triggered it -- this is the durable record used to
answer "how much are we actually spending" and "is prompt caching working"
over time.

Log file: data/ai_usage_log.jsonl (one JSON object per line).
"""

import json
import os
import threading
import time
from datetime import datetime, timezone

_LOG_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
_LOG_FILE = os.path.join(_LOG_DIR, "ai_usage_log.jsonl")
_lock = threading.Lock()


def log_usage(
    *,
    session_id: str,
    provider_id: str,
    model: str,
    list_name: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    cost_usd: float = 0.0,
    iterations: int = 0,
    tool_calls: int = 0,
    status: str = "ok",   # "ok" | "error" | "interrupted" | "max_iterations"
    task_preview: str = "",
) -> None:
    """Append one usage record. Best-effort -- logging must never break a chat turn."""
    record = {
        "ts":          datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id":  session_id,
        "provider":    provider_id,
        "model":       model,
        "list":        list_name,
        "input":       input_tokens,
        "output":      output_tokens,
        "cache_write": cache_write_tokens,
        "cache_read":  cache_read_tokens,
        "cost_usd":    round(cost_usd, 6),
        "iterations":  iterations,
        "tool_calls":  tool_calls,
        "status":      status,
        "task":        (task_preview or "")[:120],
    }
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        with _lock, open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _read_records(since_ts: float = 0.0) -> list:
    if not os.path.exists(_LOG_FILE):
        return []
    out = []
    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if since_ts:
                    try:
                        rec_ts = datetime.fromisoformat(rec["ts"]).timestamp()
                    except Exception:
                        continue
                    if rec_ts < since_ts:
                        continue
                out.append(rec)
    except Exception:
        pass
    return out


def _totals(records: list) -> dict:
    t = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0,
         "cost_usd": 0.0, "turns": len(records), "tool_calls": 0, "errors": 0}
    for r in records:
        for k in ("input", "output", "cache_write", "cache_read", "tool_calls"):
            t[k] += r.get(k, 0)
        t["cost_usd"] += r.get("cost_usd", 0.0)
        if r.get("status") == "error":
            t["errors"] += 1
    # Cache hit rate: share of billable input tokens that were served from
    # cache (cheap reads) rather than paid at full fresh-input price.
    billable_in = t["cache_read"] + t["input"]
    t["cache_hit_rate"] = round(t["cache_read"] / billable_in, 4) if billable_in else 0.0
    t["cost_usd"] = round(t["cost_usd"], 6)
    return t


def _by_provider(records: list) -> list:
    agg: dict = {}
    for r in records:
        p = r.get("provider", "unknown")
        a = agg.setdefault(p, {"provider": p, "cost_usd": 0.0, "turns": 0,
                                "input": 0, "output": 0, "cache_write": 0, "cache_read": 0})
        a["cost_usd"] += r.get("cost_usd", 0.0)
        a["turns"]    += 1
        for k in ("input", "output", "cache_write", "cache_read"):
            a[k] += r.get(k, 0)
    for a in agg.values():
        a["cost_usd"] = round(a["cost_usd"], 6)
    return sorted(agg.values(), key=lambda x: -x["cost_usd"])


def summarize(days: int = 30) -> dict:
    """Aggregate totals for the trailing `days` window, all-time totals, a
    daily series for charting, and a per-provider breakdown."""
    cutoff  = time.time() - days * 86400
    records = _read_records(since_ts=cutoff)

    daily: dict = {}
    for r in records:
        day = r["ts"][:10]
        d = daily.setdefault(day, {"cost_usd": 0.0, "input": 0, "output": 0,
                                    "cache_write": 0, "cache_read": 0, "turns": 0})
        d["cost_usd"] += r.get("cost_usd", 0.0)
        d["turns"]    += 1
        for k in ("input", "output", "cache_write", "cache_read"):
            d[k] += r.get(k, 0)
    for d in daily.values():
        d["cost_usd"] = round(d["cost_usd"], 6)
    daily_series = [dict(date=day, **vals) for day, vals in sorted(daily.items())]

    return {
        "window_days": days,
        "window":      _totals(records),
        "all_time":    _totals(_read_records()),
        "daily":       daily_series,
        "by_provider": _by_provider(records),
    }
