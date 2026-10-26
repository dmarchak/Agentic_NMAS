"""History › Query › Ask your own: what its two builders share (board E3, the metrics builder,
modules/history_promq.py; board F3, the logs builder, modules/history_logq.py; both approved by
the operator 2026-10-15).

- **One token each.** A value reaches a query only inside a string Mercury quotes (`string`):
  PromQL and LogQL both read a double-quoted string with Go's rules (strconv.Unquote), so a
  quote, a backslash, a newline or any control character is escaped and can never end the
  string or add to the query's structure. A value inside a pattern is escaped as a literal
  first (`literal`, RE2's metacharacters), so it matches exactly itself.
- **Durations** as Prometheus and Loki write them ("30d1h", "2m"), and in words.
- **The range**: a chip, the last so many minutes, hours or days, or From… to… in UTC, to the
  minute (`window`).
- **The address**: every choice is in it, so a link shows the same question (`read_values`,
  `qs`).
"""

import calendar
import re
import time
from urllib.parse import urlencode

#: How long a measured fact about a store (its bounds, its metadata) is kept, seconds.
REMEMBER = 3600

_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?$")
_WITHIN = re.compile(r"^(\d{1,4})\s*(m|min|mins|minutes?|h|hours?|d|days?)$", re.I)
_DUR = re.compile(r"(\d+)(ms|y|w|d|h|m|s)")
_UNIT = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 7 * 86400, "y": 365 * 86400}
#: RE2's metacharacters: escaped with a backslash to stand for themselves.
_RE2_META = set("\\.+*?()|[]{}^$")


# ---------------------------------------------------------------------------- one token each

def string(value: str) -> str:
    """*value* as ONE string token of PromQL or LogQL: double-quoted, a backslash and a quote
    escaped, and every control character (a newline among them) written as \\xHH, so nothing
    in it can end the string. Both read it back with Go's strconv.Unquote, which takes each of
    these."""
    out = []
    for ch in str(value):
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append("\\x%02x" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def literal(value: str) -> str:
    """*value* as an RE2 pattern matching exactly itself: each metacharacter escaped, each
    control character as \\x{HH}."""
    out = []
    for ch in str(value):
        if ch in _RE2_META:
            out.append("\\" + ch)
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append("\\x{%02x}" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def alternation(values) -> str:
    """One pattern matching exactly any of *values*."""
    return "|".join(literal(v) for v in values)


def matcher(label: str, values) -> str:
    """``label="v"`` for one value, ``label=~"a|b"`` (each a literal) for several: the label
    NAME is the caller's to have checked; every value is one token."""
    values = list(values)
    if len(values) == 1:
        return f"{label}={string(values[0])}"
    return f"{label}=~{string(alternation(values))}"


# ---------------------------------------------------------------------------- durations

def parse_duration(text) -> float:
    """Seconds in a Prometheus or Loki duration ("30d1h", "1m", "2y", "0s"); None when it is
    not one."""
    text = str(text or "").strip()
    if not text:
        return None
    parts = _DUR.findall(text)
    if not parts or "".join(n + u for n, u in parts) != text:
        return None
    return sum(int(n) * _UNIT[u] for n, u in parts)


def duration_words(seconds) -> str:
    """Seconds as words: "30 days 1 hour", "1 min", "2 years"."""
    seconds = int(seconds or 0)
    if seconds <= 0:
        return "no limit"
    out = []
    for unit, size in (("year", 365 * 86400), ("day", 86400), ("hour", 3600), ("min", 60),
                       ("s", 1)):
        n, seconds = divmod(seconds, size)
        if n:
            out.append(f"{n} {unit}" + ("s" if n != 1 and unit in ("year", "day", "hour") else ""))
    return " ".join(out[:2])


def utc(ts: float, fmt: str = "%-d %b %H:%M") -> str:
    return time.strftime(fmt, time.gmtime(ts))


def span(start: float, end: float) -> str:
    """Two instants as one span in UTC, the end's date written when it is another day's:
    "22 Oct 08:00 to 09:00", "22 Oct 00:00 to 23 Oct 00:00" (the operator, 2026-10-26: a
    day's window read "22 Oct 00:00 to 00:00")."""
    same = utc(start, "%Y-%m-%d") == utc(end, "%Y-%m-%d")
    return f"{utc(start)} to {utc(end, '%H:%M' if same else '%-d %b %H:%M')}"


def iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


# ---------------------------------------------------------------------------- the range

def when(text: str):
    """"YYYY-MM-DD HH:MM" or "YYYY-MM-DD", read as UTC, to epoch seconds; None otherwise."""
    if not _WHEN.match(text or ""):
        return None
    fmt = "%Y-%m-%d %H:%M" if " " in text else "%Y-%m-%d"
    return float(calendar.timegm(time.strptime(text, fmt)))


def window(spec: dict, now: float, ranges: dict, fallback: str = "24h") -> dict:
    """``{start, end, seconds, words, error}``: the range asked, to the minute. *ranges* are the
    builder's chips (key -> (words, seconds)); a range this cannot read falls back to the chip
    *fallback* and says why (*error*)."""
    end = float(int(now // 60) * 60)
    fb_words, fb_secs = ranges[fallback]
    fb = {"start": end - fb_secs, "end": end, "seconds": fb_secs, "words": f"the last {fb_words}"}
    if spec["range"] in ranges:
        words, secs = ranges[spec["range"]]
        return {"start": end - secs, "end": end, "seconds": secs, "words": f"the last {words}",
                "error": ""}
    if spec["within"] and not (spec["from"] or spec["to"]):
        m = _WITHIN.match(spec["within"])
        if not m:
            return dict(fb, error=f"{spec['within'][:40]!r} is not a span this reads: write "
                                  "3 days, 12 hours or 90 minutes")
        n, unit = int(m.group(1)), m.group(2).lower()[0]
        secs = n * {"m": 60, "h": 3600, "d": 86400}[unit]
        if not secs:
            return dict(fb, error=f"{spec['within'][:40]!r} is no time at all")
        return {"start": end - secs, "end": end, "seconds": secs,
                "words": f"the last {duration_words(secs)}", "error": ""}
    start, stop = when(spec["from"]), (when(spec["to"]) if spec["to"] else end)
    if start is None or stop is None:
        bad = spec["from"] if start is None else spec["to"]
        return dict(fb, error=f"{bad[:40]!r} is not a time this reads: write 2026-10-12 10:00 "
                              "(UTC)")
    if start >= stop:
        return dict(fb, error=f"From ({spec['from']}) is not before To ({spec['to'] or 'now'})")
    return {"start": start, "end": stop, "seconds": stop - start,
            "words": f"{utc(start)} to {utc(stop)} UTC", "error": ""}


# ---------------------------------------------------------------------------- the address

def read_values(values, defaults: dict, lists) -> dict:
    """The address's values for *defaults*' keys, each stripped; a repeatable key (*lists*)
    read in order with blanks and repeats dropped. Nothing outside *defaults* is read."""
    getlist = getattr(values, "getlist", None)
    spec = {}
    for key, default in defaults.items():
        if key in lists:
            raw = getlist(key) if getlist else (values.get(key) or [])
            raw = [raw] if isinstance(raw, str) else list(raw)
            seen = []
            for v in raw:
                v = (v or "").strip() if isinstance(v, str) else ""
                if v and v not in seen:
                    seen.append(v)
            spec[key] = seen
        else:
            v = values.get(key)
            spec[key] = (v if isinstance(v, str) else default).strip() if v is not None else default
    return spec


def qs(spec: dict, defaults: dict, lists, list_name: str = "", over: dict = None) -> str:
    """The address for *spec* with *over* applied: only what differs from the defaults."""
    merged = dict(spec, **(over or {}))
    pairs = [("list", list_name)] if list_name else []
    for key, default in defaults.items():
        v = merged.get(key, default)
        if key in lists:
            pairs += [(key, x) for x in v or []]
        elif v and v != default:
            pairs.append((key, v))
    return "?" + urlencode(pairs)
