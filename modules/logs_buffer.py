"""Each device's recent syslog, held in the background for the pages that draw it (C3166's
slice 2; the operator's rule, 2026-11-12: no page load waits on Loki).

**One writer.** The `logs-tail` reader (modules/readers/logs_tail.py) fills it incrementally:
every 5 s one query for every device since the last line it holds (a short overlap for a line
that reaches Loki late), and, until what it holds reaches back as far as each kind is kept, one
older page a read. It writes a device's file only when that device sent something new. The
reader's own stored value carries what the buffer COVERS (`cover`, per kind, from and to) and
when it was read, so a page draws the buffer's age and says when the last refresh failed.

**Three kinds, each bounded:**
- ``lines``: the device's lines but heartbeats, the last `LINES_SECONDS` (24 h, the Logs tab's
  window), at most `DEVICE_LINES`, newest first;
- ``beats``: the receive times of its heartbeat lines (`device_logs.HEARTBEAT_LINE`), the last
  24 h, at most `DEVICE_BEATS`;
- ``changes``: its configuration and restart lines (`device_logs.CHANGE_MNEMONICS`), the last
  `CHANGE_SECONDS` (30 days, the drift row's longest ask), at most `DEVICE_CHANGES`.

A device whose kind is full holds it only from its oldest line kept (`device_cover`): older
lines are older than the buffer, and a page that needs them asks Loki for them alone, as a part
that loads after the page (`logs_v2.older`).

**Display only** (CLAUDE.md, the rule that no page load or badge poll waits on a source, and its
Display only clause): the heal pipeline, deploys and their reads never read this; they read
Loki live (`device_logs.lines_held`).

**A cache, never a record:** every file is re-derivable from Loki, so an unreadable one is read
as empty and rewritten by the next line (reader_job rule 10), and the page says what it holds.
Each line's text is masked on the way in (`redact_text`), as every line Mercury keeps is.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

#: How far back each kind is held: the Logs tab's 24 h, and the drift row's 30 days (Loki's own
#: longest ask, `max_query_length`, 30 days 1 hour, measured 2026-10-10).
LINES_SECONDS = 24 * 3600
CHANGE_SECONDS = 30 * 86400
HORIZON = {"lines": LINES_SECONDS, "beats": LINES_SECONDS, "changes": CHANGE_SECONDS}
#: The most kept per device: twice the Logs tab's 100 and the syslog view's 50 a page, so a
#: filtered view has lines to filter; a heartbeat every minute for 24 h; the drift row's 50.
DEVICE_LINES = 200
DEVICE_BEATS = 1440
DEVICE_CHANGES = 50
LIMITS = {"lines": DEVICE_LINES, "beats": DEVICE_BEATS, "changes": DEVICE_CHANGES}
KINDS = ("lines", "beats", "changes")


def root(store: str) -> str:
    """Beside the readers' own stored values (`reader_job.store_path`), one folder a store."""
    from modules import reader_job
    return os.path.join(os.path.dirname(reader_job.store_path(store)), "logs-buffer", store)


def _path(store: str, dev: str) -> str:
    return os.path.join(root(store), f"{dev}.json")


def load(store: str, dev: str) -> dict:
    """The device's held lines, ``{kind: [...]}``; empty for a device with none, and for an
    unreadable file (a cache: rebuilt by the next line, said by the page's cover)."""
    try:
        with open(_path(store, dev), encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("logs_buffer: %s's held lines in %s could not be read (%s): read as none",
                    dev, store, exc)
        return {}
    return doc if isinstance(doc, dict) else {}


def _key(entry) -> tuple:
    if isinstance(entry, dict):
        return entry.get("ns"), entry.get("mn"), entry.get("text")
    return entry, None, None


def _ns(entry) -> int:
    return int(entry.get("ns") if isinstance(entry, dict) else entry)


def merge(before: list, new: list, kind: str, now: float) -> list:
    """*before* and *new* as one list, newest first, each line once, inside its kind's horizon
    and at most its limit."""
    floor = int((now - HORIZON[kind]) * 1e9)
    seen, out = set(), []
    for e in sorted(list(new) + list(before or []), key=_ns, reverse=True):
        k = _key(e)
        if k in seen or _ns(e) < floor:
            continue
        seen.add(k)
        out.append(e)
        if len(out) >= LIMITS[kind]:
            break
    return out


def write(store: str, by_device: dict, now: float) -> int:
    """Merge each device's new lines (``{dev: {kind: [...]}}``) into its file. Returns how many
    files were written. A file that cannot be written raises: the reader's read fails and keeps
    its last good value, whose cover never claims what was not written."""
    from modules import filestore

    n = 0
    for dev, kinds in sorted(by_device.items()):
        if not any(kinds.get(k) for k in KINDS):
            continue
        doc = load(store, dev)
        for k in KINDS:
            if kinds.get(k):
                doc[k] = merge(doc.get(k) or [], kinds[k], k, now)
        os.makedirs(root(store), exist_ok=True)
        filestore.write_atomic(_path(store, dev), json.dumps(doc, separators=(",", ":")))
        n += 1
    return n


# ---------------------------------------------------------------------------- the pages' read

def held(list_name: str, dev: str, now: float = None) -> dict:
    """What the pages draw of one device: ``{"state", "why", "value_at", "failed", "stale",
    "cover", "lines", "beats", "changes"}``. *stale* is `stale_words`' line, or "". *state* is
    ``ok``, ``never`` (the reader has not read yet),
    ``not_configured``, ``not_applicable`` or ``unreadable``; *cover* is each kind's
    ``{"from", "reach", "to", "whole", "full"}`` for this device (epoch seconds: from when this
    device's lines are all held, `device_cover`; *reach*, how far back the buffer has read for
    every device; *whole* when that is as far as the kind is kept; *full* when the device's
    list is at its limit). Each kind's lines are those inside
    the kept horizon, newest first. No call leaves the process."""
    from modules import reader_job
    from modules.readers import logs_tail

    now = time.time() if now is None else now
    got = reader_job.read_cached_for(logs_tail.READER_NAME, list_name)
    out = {"state": got.get("state"), "why": got.get("why") or "", "value_at": "", "failed": "",
           "stale": "", "cover": {}, "lines": [], "beats": [], "changes": []}
    if out["state"] in ("not_applicable", "not_configured", "unreadable"):
        out["why"] = out["why"] or "the logs reader's store could not be read"
        return out
    doc = got.get("doc") or {}
    attempt = doc.get("last_attempt") or {}
    out["failed"] = "" if attempt.get("ok", True) else (attempt.get("error")
                                                         or "the last read failed")
    last = doc.get("last_good") or {}
    value = last.get("value") or {}
    if not last:
        return dict(out, state="never")
    if not value.get("configured"):
        return dict(out, state="not_configured", why="Loki is not configured for this network")
    out["value_at"] = last.get("value_at", "")
    out["stale"] = stale_words(doc, now)
    buf = value.get("buffer") or {}
    if not buf.get("store"):
        # A value stored before the buffer was (this release's first read is yet to come).
        return dict(out, state="never")
    mine = load(buf["store"], dev)
    out["state"] = "ok"
    read_ns = int((value.get("read_at_ts") or now) * 1e9)
    for kind in KINDS:
        c = buf.get(kind) or {}
        if not c.get("to"):
            out["cover"][kind] = {"from": None, "reach": None, "to": None, "whole": False,
                                  "full": False}
            continue
        floor = max(c["from"] / 1e9, now - HORIZON[kind])
        kept = [e for e in mine.get(kind) or [] if _ns(e) >= int(floor * 1e9)]
        # Whole: the reader's buffer reached back as far as the kind is kept, at its read (the
        # reader holds a whole kind's from at that read's horizon, `logs_tail.read`).
        out["cover"][kind] = {"from": device_cover(kept, kind, floor), "reach": floor,
                              "to": c["to"] / 1e9,
                              "whole": c["from"] <= read_ns - HORIZON[kind] * 10 ** 9 + 10 ** 9,
                              "full": len(kept) >= LIMITS[kind]}
        out[kind] = kept
    return out


def promise_seconds() -> int:
    """How old the held lines may be before a page says so: the logs-tail reader's interval
    times its stale factor, as its job-health row judges it (reader_job rule 7)."""
    from modules.readers import logs_tail

    return logs_tail.INTERVAL_SECONDS * logs_tail.READER.stale_after_intervals


def stale_words(doc: dict, now: float) -> str:
    """C3330: what a page draws in place of its held-by line when the last good read is older
    than its promise ("" when it is not): the lines' age and why, the last error in its own
    words, so held lines never look current."""
    from modules import reader_job
    from modules.history_ask import duration_words

    good = (doc or {}).get("last_good") or {}
    at = reader_job._parse_iso(good.get("value_at"))      # noqa: SLF001 (one parser)
    if at is None or now - at <= promise_seconds():
        return ""
    attempt = (doc or {}).get("last_attempt") or {}
    error = attempt.get("error") or ""
    if error.startswith("RuntimeError: "):
        error = error[len("RuntimeError: "):]
    why = (error if not attempt.get("ok", True) and error else
           f"it has not read since {attempt.get('at') or good.get('value_at')}")
    return (f"Held lines are {duration_words(max(1, int(now - at)))} old: the logs reader has "
            f"stopped ({why})")


def device_cover(kept: list, kind: str, floor: float) -> float:
    """From when this device's *kind* is whole: the buffer's from, or, when the device's list is
    full, its oldest line kept (anything older was let go)."""
    if len(kept) >= LIMITS[kind]:
        return max(floor, _ns(kept[-1]) / 1e9)
    return floor
