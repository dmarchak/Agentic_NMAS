"""A device's LOGS, for the device page's Logs tab (NSOT_GUI_BRIEF 3.3; step 4):
what the device sent to syslog, as Loki holds it. Read from LOKI, never from
the device, so it adds no session to one.

**One device's lines are matched by the device's own name** (`logging
origin-id hostname`, the anchored `\\s<host>:\\s`), exactly as
`scripts/nmas-heartbeat-rules` matches them, never by rsyslog's hostname
field (C13).

**Heartbeats are folded, by their exact line form**, into one count and the
time of the last: twelve an hour would crowd out everything else. They are
excluded by `HEARTBEAT_LINE`, never by the marker, because an EEM error about
the applet NAMES the marker and is exactly the line a person needs to see
(C21: counting a line that merely contains the marker read a broken applet's
own error as a sign of life).

**Times**: each line is drawn at the time the NMAS RECEIVED it (Loki's); the
device's own timestamp is shown beside it, and one IOS marks unsynchronised
(`*`) is said, because a device whose clock is wrong (s3's ran days behind,
2026-10-01) prints a time that means nothing.
"""

import logging
import re
import time

log = logging.getLogger(__name__)

JOB = "network_syslog"
MARKER = "NMAS-HEARTBEAT"
HEARTBEAT_LINE = r"%HA_EM-\d-LOG: " + re.escape(MARKER) + ": " + re.escape(MARKER)
#: The window and the page size. A cut list says it is cut.
WINDOW_HOURS = 24
LIMIT = 100
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_MESSAGE = re.compile(
    r"^(?P<devts>\*?\.?[A-Z][a-z]{2}\s+\d+\s+[\d:.]+(?:\s+[A-Z]{3,4})?):\s+"
    r"(?P<mnemonic>%[A-Z0-9_]+(?:-[A-Z0-9_]+)*-(?P<sev>[0-7])-[A-Z0-9_]+):?\s*(?P<text>.*)$")
SEVERITY = {0: "emergency", 1: "alert", 2: "critical", 3: "error", 4: "warning",
            5: "notice", 6: "informational", 7: "debug"}


def host_pattern(hostname: str) -> str:
    return r"\s" + re.escape(hostname) + r":\s"


def selector(hostname: str) -> str:
    """This device's lines. The substring stage first is only for Loki's cost;
    the anchored regex is the match (a prefix of another name never matches)."""
    return f'{{job="{JOB}"}} |= "{hostname}:" |~ `{host_pattern(hostname)}`'


def _kind(sev):
    if sev is None:
        return "muted"
    return "danger" if sev <= 3 else "warn" if sev == 4 else "muted"


def parse(line: str, hostname: str) -> dict:
    """``{devts, unsync, mnemonic, sev, sev_word, kind, text}`` for one line.
    A line with no mnemonic keeps its text whole, never dropped."""
    m = re.search(host_pattern(hostname), line)
    rest = line[m.end():] if m else line
    mm = _MESSAGE.match(rest)
    if not mm:
        return {"devts": "", "unsync": False, "mnemonic": "", "sev": None, "sev_word": "",
                "kind": "muted", "text": rest}
    sev = int(mm.group("sev"))
    return {"devts": mm.group("devts").lstrip("*."), "unsync": mm.group("devts").startswith("*"),
            "mnemonic": mm.group("mnemonic"), "sev": sev, "sev_word": SEVERITY[sev],
            "kind": _kind(sev), "text": mm.group("text")}


def _iso(ns) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ns) / 1e9))


def for_device(dev: dict, *, now: float = None) -> dict:
    """The Logs tab's view. Never raises; a source that could not be read is
    said, never drawn as a quiet device."""
    from modules.integrations.loki import LokiIntegration
    from modules.redact import redact_text

    host = dev.get("hostname", "")
    view = {"configured": True, "errors": [], "lines": [], "cut": False,
            "heartbeat": None, "window_hours": WINDOW_HOURS, "limit": LIMIT, "unsync": 0}
    if not _NAME.match(host or ""):
        view["errors"].append(f"the name {host!r} cannot be matched safely in a log query")
        return view
    loki = LokiIntegration()
    if not loki.is_configured():
        view["configured"] = False
        return view
    now = now if now is not None else time.time()
    start, end = int((now - WINDOW_HOURS * 3600) * 1e9), int(now * 1e9)
    sel = selector(host)

    def ask(path, query, **extra):
        r = loki._get(path, query=query, **extra)
        if not r.get("ok"):
            view["errors"].append(f"Loki could not be asked: {r.get('error')}")
            return None
        try:
            return (r["response"].json().get("data") or {}).get("result") or []
        except ValueError as exc:
            view["errors"].append(f"Loki's answer could not be read: {exc}")
            return None

    streams = ask("loki/api/v1/query_range", f"{sel} !~ `{HEARTBEAT_LINE}`",
                  limit=LIMIT, start=start, end=end, direction="backward")
    if streams is None:
        return view
    rows = []
    for stream in streams:
        for ns, line in stream.get("values") or []:
            row = parse(redact_text(line), host)
            row.update(ns=int(ns), at_iso=_iso(ns))
            rows.append(row)
    rows.sort(key=lambda r: r["ns"], reverse=True)
    view["lines"] = rows[:LIMIT]
    view["cut"] = len(rows) >= LIMIT
    view["unsync"] = sum(1 for r in view["lines"] if r["unsync"])

    last = ask("loki/api/v1/query_range", f"{sel} |~ `{HEARTBEAT_LINE}`",
               limit=1, start=start, end=end, direction="backward")
    count = ask("loki/api/v1/query",
                f"sum(count_over_time({sel} |~ `{HEARTBEAT_LINE}` [{WINDOW_HOURS}h]))",
                time=end)
    if last is not None and count is not None:
        stamps = [int(ns) for s in last for ns, _l in s.get("values") or []]
        try:
            n = int(float(count[0]["value"][1])) if count else 0
        except (KeyError, IndexError, ValueError, TypeError):
            n = 0
        view["heartbeat"] = {"count": n, "last_iso": _iso(max(stamps)) if stamps else ""}
    return view
