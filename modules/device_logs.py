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
#: The same fields as a LogQL `regexp` stage, for counting the whole fleet in one query (the
#: Logs view, C652): the device's own name before its timestamp (`dev`), and the mnemonic
#: (`mn`, its severity the digit inside it). A line it does not match has neither label.
LOGQL_FIELDS = (r"\s(?P<dev>[A-Za-z][A-Za-z0-9._-]*):\s+\*?\.?[A-Z][a-z]{2}\s+\d+\s+[\d:.]+"
                r"(?:\s+[A-Z]{3,4})?:\s+(?P<mn>%[A-Z0-9_]+(?:-[A-Z0-9_]+)*-[0-7]-[A-Z0-9_]+)")
_MN_SEV = re.compile(r"-([0-7])-[A-Z0-9_]+$")


def mnemonic_severity(mnemonic: str):
    """The severity a mnemonic carries (``%LINK-3-UPDOWN`` is 3), or None."""
    m = _MN_SEV.search(mnemonic or "")
    return int(m.group(1)) if m else None


def host_pattern(hostname: str) -> str:
    return r"\s" + re.escape(hostname) + r":\s"


#: C820: the syslog JOB is MEASURED, never named in the product (a job's name is the log
#: shipper's configuration's choice, so each network names its own). It is every job whose
#: lines carry a device's syslog form (`LOGQL_FIELDS`: the device's own name, its timestamp
#: and a mnemonic) in Loki's last JOB_WINDOW_HOURS: ONE count by job across what Loki holds,
#: the way F3's builder takes its jobs from Loki rather than from a list (0.12 s on the lab's
#: Loki, which answered its one syslog job with 3,699 lines in 24 h, measured 2026-10-16).
#: Asked at most every LABEL_ASK_EVERY seconds for each Loki; a failed ask is not remembered,
#: and an ask that fails or finds none keeps the jobs last found (a stored answer keeps its
#: last good value). No setting: the store answers the question, so nothing is kept in step.
JOB_WINDOW_HOURS = 24
_JOBS = {}


class NoSyslogJob(RuntimeError):
    """Loki holds no device's syslog line in the window, or could not be asked which job does:
    its words say which, for the page that could not draw the lines."""


def job_query(hours: int = JOB_WINDOW_HOURS) -> str:
    """The count by job of every line carrying a device's syslog form."""
    return (f'sum by (job) (count_over_time({{job=~".+"}} |~ `{LOGQL_FIELDS}` '
            f"[{int(hours)}h]))")


def syslog_jobs(client=None, now: float = None) -> list:
    """The jobs holding the devices' syslog in *client*'s Loki (the installation's by
    default), sorted. Raises `NoSyslogJob` naming why when none is known. Remembered per Loki
    (its address) for LABEL_ASK_EVERY seconds."""
    now = time.time() if now is None else now
    if client is None:
        from modules.integrations.loki import LokiIntegration

        client = LokiIntegration()
    held = _JOBS.get(client.url) or {}
    if held.get("asked") is not None and now - held["asked"] < LABEL_ASK_EVERY:
        if held.get("jobs"):
            return list(held["jobs"])
        raise NoSyslogJob(held.get("why") or "no syslog job is known")
    r = client._get("loki/api/v1/query", query=job_query(), time=str(int(now)))  # noqa: SLF001
    if not r.get("ok"):
        detail = f" ({r['detail']})" if r.get("detail") else ""
        why = (f"Loki could not be asked which job holds the devices' syslog: "
               f"{r.get('error')}{detail}")
    else:
        try:
            rows = (r["response"].json().get("data") or {}).get("result") or []
        except (ValueError, AttributeError) as exc:
            rows, why = None, f"Loki's answer on which job holds the devices' syslog could not " \
                              f"be read: {exc}"
        if rows is not None:
            found = sorted({(row.get("metric") or {}).get("job") for row in rows
                            if isinstance(row, dict) and (row.get("metric") or {}).get("job")})
            why = (f"no job in Loki holds a device's syslog line (a device's own name, its time "
                   f"and a mnemonic) in the last {JOB_WINDOW_HOURS} h")
            if found:
                _JOBS[client.url] = {"jobs": found, "asked": now, "why": ""}
                return list(found)
            if not held.get("jobs"):
                _JOBS[client.url] = {"jobs": [], "asked": now, "why": why}
    if held.get("jobs"):
        log.warning("device_logs: %s; keeping the jobs last found, %s", why, held["jobs"])
        return list(held["jobs"])
    raise NoSyslogJob(why)


def job_matcher(client=None, now: float = None) -> str:
    """The stream selector's job matcher for the devices' syslog, as F3's `history_ask.matcher`
    builds it: an equality for one job, an alternation for several, each value one token.
    Raises `NoSyslogJob`."""
    from modules.history_ask import matcher

    return matcher("job", syslog_jobs(client, now=now))


#: C722: Alloy labels each line with its `device` (the same pattern as LOGQL_FIELDS, set by
#: scripts/host-steps/c722-device-label.sh) from the moment that step ran. When that was is
#: MEASURED, as Loki's first labelled line, and asked again at most this often (seconds).
LABEL_ASK_EVERY = 3600
_LABEL = {"since": None, "asked": None}


def label_since(now: float = None, ask=None):
    """When the first `device`-labelled line reached Loki (epoch seconds), within Loki's 30-day
    query limit; None when none is held or Loki could not say (then every window is read by the
    line regex, which matches labelled and unlabelled lines alike). *ask(query, start, end)*
    returns Loki's answer (`LokiIntegration._get`'s), for tests."""
    now = time.time() if now is None else now
    if _LABEL["asked"] is not None and now - _LABEL["asked"] < LABEL_ASK_EVERY:
        return _LABEL["since"]
    start, end = int((now - 30 * 86400) * 1e9), int(now * 1e9)
    loki = None
    if ask is None:
        from modules.integrations.loki import LokiIntegration

        loki = LokiIntegration()
        if not loki.is_configured():
            return None
    try:
        query = f'{{{job_matcher(loki, now=now)}, device=~".+"}}'
    except NoSyslogJob as exc:
        log.warning("device_logs: when the device label began could not be asked: %s", exc)
        return None                           # not remembered: asked again next time
    if ask is None:
        r = loki._get("loki/api/v1/query_range", query=query, limit=1, start=start,  # noqa: SLF001
                      end=end, direction="forward")
    else:
        r = ask(query, start, end)
    if not r.get("ok"):
        log.warning("device_logs: when the device label began could not be asked: %s",
                    r.get("error"))
        return None                           # not remembered: asked again next time
    try:
        streams = (r["response"].json().get("data") or {}).get("result") or []
    except (ValueError, AttributeError) as exc:
        log.warning("device_logs: Loki's answer on the device label could not be read: %s", exc)
        return None
    stamps = [int(ns) for s in streams for ns, _l in s.get("values") or []]
    _LABEL.update(since=min(stamps) / 1e9 if stamps else None, asked=now)
    return _LABEL["since"]


def selector(hostname: str, start: float = None, client=None) -> str:
    """This device's lines over a window from *start* (epoch seconds). By its `device` label
    when the window starts after the label began (C722); otherwise by the line itself: the
    substring stage first is only for Loki's cost, the anchored regex is the match (a prefix of
    another name never matches), and it reads labelled and unlabelled lines alike. The job is
    *client*'s Loki's syslog job (`syslog_jobs`); raises `NoSyslogJob` when none is known."""
    job = job_matcher(client)
    if start is not None:
        since = label_since(now=None)
        if since is not None and start >= since:
            return f'{{{job}, device="{hostname}"}}'
    return f'{{{job}}} |= "{hostname}:" |~ `{host_pattern(hostname)}`'


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


#: C342: the lines in which a device says its configuration changed or it restarted, by Cisco
#: IOS's own mnemonics (the product's devices), never a lab's: configured from a terminal
#: (CONFIG_I) or programmatically (CONFIG_P), a command the configuration logger recorded
#: (CFGLOG_LOGGEDCMD), and a restart or a reload requested.
CHANGE_MNEMONICS = ("%SYS-5-CONFIG_I", "%SYS-5-CONFIG_P", "%PARSER-5-CFGLOG_LOGGEDCMD",
                    "%SYS-5-RESTART", "%SYS-5-RELOAD")
CHANGE_PATTERN = "(?:" + "|".join(re.escape(m) for m in CHANGE_MNEMONICS) + "):"
#: The page and the longest window the drift row asks over: Loki's own longest ask is 30 days
#: (its default `max_query_length`, 721 h), as `label_since` asks.
CHANGE_LIMIT = 50
CHANGE_MAX_DAYS = 30


def change_lines(dev: dict, since: float = None, *, now: float = None) -> dict:
    """What the device's own log says about when and how it changed (C342, the device page's
    drift row): its configuration and restart lines (`CHANGE_MNEMONICS`) from *since* (epoch
    seconds: the moment its golden was recorded) to now, newest first, at most `CHANGE_LIMIT`.
    Each line is masked and drawn at the time Mercury RECEIVED it, the device's own time beside
    it (never the device clock, never its uptime). A window longer than Loki is asked over
    starts `CHANGE_MAX_DAYS` back and says so (`capped`). A page returned full is cut and says
    so. Never raises: Loki unconfigured, unaskable or unreadable is its own answer (`error`),
    never "no lines". One device, read from Loki on a person's request; nothing reaches the
    device."""
    from modules.integrations.loki import LokiIntegration
    from modules.redact import redact_text

    host = dev.get("hostname", "")
    now = time.time() if now is None else now
    floor = now - CHANGE_MAX_DAYS * 86400
    start = floor if since is None or since < floor else since
    view = {"configured": True, "error": "", "lines": [], "cut": False, "limit": CHANGE_LIMIT,
            "start_iso": _iso(int(start * 1e9)), "capped": since is None or since < floor,
            "max_days": CHANGE_MAX_DAYS, "unsync": 0}
    if not _NAME.match(host or ""):
        view["error"] = f"the name {host!r} cannot be matched safely in a log query"
        return view
    loki = LokiIntegration()
    if not loki.is_configured():
        view["configured"] = False
        return view
    try:
        sel = selector(host, start=start, client=loki)
    except NoSyslogJob as exc:
        view["error"] = f"the syslog job could not be found: {exc}"
        return view
    r = loki._get("loki/api/v1/query_range", query=f"{sel} |~ `{CHANGE_PATTERN}`",  # noqa: SLF001
                  limit=CHANGE_LIMIT, start=int(start * 1e9), end=int(now * 1e9),
                  direction="backward")
    if not r.get("ok"):
        detail = f" ({r['detail']})" if r.get("detail") else ""
        view["error"] = f"Loki could not be asked: {r.get('error')}{detail}"
        return view
    try:
        streams = (r["response"].json().get("data") or {}).get("result") or []
    except (ValueError, AttributeError) as exc:
        view["error"] = f"Loki's answer could not be read: {exc}"
        return view
    rows = []
    for stream in streams:
        for ns, line in stream.get("values") or []:
            row = parse(redact_text(line), host)
            row.update(ns=int(ns), at_iso=_iso(ns))
            rows.append(row)
    rows.sort(key=lambda x: x["ns"], reverse=True)
    view["lines"] = rows[:CHANGE_LIMIT]
    view["cut"] = len(rows) >= CHANGE_LIMIT
    view["unsync"] = sum(1 for x in view["lines"] if x["unsync"])
    return view


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
    try:
        sel = selector(host, start=now - WINDOW_HOURS * 3600, client=loki)
    except NoSyslogJob as exc:
        view["errors"].append(f"The syslog job could not be found: {exc}")
        return view

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
