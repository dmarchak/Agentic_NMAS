"""Routing adjacencies a managed device LOGGED going down (C589; Core 1.0's K2, troubleshooting
for 5840 Lab 10).

**Why the log.** The adjacency reader (`adjacencies`, C38) judges what Prometheus scrapes once
a minute, and raises a row only once a link has been down for two reads, so a deploy's settle
window passes first. An adjacency that drops and comes back between two scrapes is invisible
to it. Measured 2026-10-08: r1 logged `%OSPF-5-ADJCHG … from 2WAY to DOWN, Neighbor Down: Dead
timer expired` at 19:16:05 UTC and was back within 54 s, and no scrape saw it. Only the
device's own log line shows it.

**What it reads.** Loki, once for the whole fleet: the routing adjacency changes every managed
device logged over the last `WINDOW_DAYS` days. It keeps the DOWN ones:
- `%OSPF-5-ADJCHG` and `%OSPFv3-5-ADJCHG` ("from <state> to DOWN");
- `%BGP-5-ADJCHANGE` ("neighbor <address> Down").

**Each drop is timed by Loki's receive time,** never the device's clock (CLAUDE.md). A line is
attributed to the managed device whose name it carries, by the same anchored pattern the
device's Logs tab uses (`device_logs.host_pattern`).

**Per adjacency, not per drop.** Measured 2026-10-19 on the lab's Loki over seven days:
- r1 logged its OSPF adjacency to s3 down 20 to 26 times a day, and to s4 1 to 9 times, nearly
  all "2WAY to DOWN, Dead timer expired";
- a few drops toward r2, r3 and r4, over OSPFv3.
A row per drop would be about 30 rows a day. So each adjacency (the logging device, the
protocol, the neighbour) carries:
- its drops in the last day, each with its time and reason (masked);
- its count per UTC day over the window;
- its BAND, the highest of those daily counts. A person may acknowledge an adjacency within its
  band (C433's pattern), and it stays quiet while its day's count stays at or under the band.

Needs attention decides which drops a planned restart or a deploy explains
(`attention.adjacency_log_source`); the rest are counted on the row.

**IPv6** (docs/IPV6_PARITY.md, the standing rule): an OSPFv3 neighbour is named by its router
id, and a BGP neighbour by an address of either family. Both are parsed, and each is tested
with an IPv6 case.

**Nothing reaches a device.** One Loki query per read. A page returned full is refused as
partial (rule 5), and the last good value is kept.
"""

import logging
import re
import time

from modules import reader_job

log = logging.getLogger(__name__)

#: The window the band is measured over (a week, as C433's alert bands are).
WINDOW_DAYS = 7
#: The last day: the drops a row counts, and the time after which a row clears.
DAY_SECONDS = 86400
#: The lab's busiest week held about 250 adjacency lines (2026-10-19); a full page is refused as
#: partial, never stored as whole.
LIMIT = 5000
#: Two minutes: Loki keeps the line, so nothing is lost between reads. The interval only sets
#: how soon a row appears; a day of the lab's syslog was counted in 0.12 s (2026-10-16).
INTERVAL_SECONDS = 120
#: The mnemonics, as a LogQL line filter (a regex, one token).
PATTERN = r"%(OSPF|OSPFV3|OSPFv3)-5-ADJCHG|%BGP-5-ADJCHANGE"

_OSPF = re.compile(r"Nbr (?P<nbr>\S+) on (?P<intf>\S+) from (?P<from>[\w-]+) to (?P<to>[\w-]+),?"
                   r"\s*(?P<reason>.*)$")
_BGP = re.compile(r"neighbor (?P<nbr>\S+)(?: vpn vrf (?P<vrf>\S+))? (?P<to>Up|Down)\b\s*"
                  r"(?P<reason>.*)$")


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


#: The adjacency mnemonic and its text, after the device's own name. Matched here, not through
#: `device_logs.parse`, whose mnemonic pattern takes capitals only and so reads no `%OSPFv3-…`
#: line (registered as its own row, found building this).
_MNEMONIC = re.compile(r"%(?P<m>OSPF(?:v3|V3)?-5-ADJCHG|BGP-5-ADJCHANGE):\s*(?P<text>.*)$")


def event(line: str, hostname: str) -> dict:
    """``{protocol, neighbor, interface, from, to, down, reason}`` for one adjacency line of
    *hostname*'s, or ``{}`` when it is not one (another device's line included: the name is
    matched anchored, as the Logs tab matches it). The reason is the device's words, masked."""
    from modules.device_logs import host_pattern
    from modules.redact import redact_text

    own = re.search(host_pattern(hostname), line)
    found = _MNEMONIC.search(line[own.end():]) if own else None
    if not found:
        return {}
    mnem, text = found.group("m").upper(), found.group("text")
    if mnem.startswith("OSPF"):
        m = _OSPF.search(text)
        if not m:
            return {}
        to = m.group("to").upper()
        return {"protocol": "OSPFv3" if mnem.startswith("OSPFV3") else "OSPF",
                "neighbor": m.group("nbr"), "interface": m.group("intf"),
                "from": m.group("from").upper(), "to": to, "down": to == "DOWN",
                "reason": redact_text(m.group("reason").strip())}
    if mnem == "BGP-5-ADJCHANGE":
        m = _BGP.search(text)
        if not m:
            return {}
        return {"protocol": "BGP", "neighbor": m.group("nbr"), "interface": "",
                "from": "", "to": m.group("to"), "down": m.group("to") == "Down",
                "reason": redact_text(m.group("reason").strip())}
    return {}


def _population() -> list:
    """``[(list name, hostname)]``: every managed device, across every network."""
    from modules.readers.adjacencies import lists
    return [(name, host) for name, _ref, hosts in lists() for host in hosts]


def _ask(query: str, start: float, end: float) -> list:
    """``[(ns, line)]`` from Loki. Raises naming what Loki answered."""
    from modules.integrations.loki import LokiIntegration

    loki = LokiIntegration()
    if not loki.is_configured():
        raise LookupError("Loki is not configured")
    r = loki._get("loki/api/v1/query_range", query=query, limit=LIMIT,  # noqa: SLF001
                  start=int(start * 1e9), end=int(end * 1e9), direction="backward")
    if not r.get("ok"):
        raise RuntimeError(f"Loki could not be asked: {r.get('error')}"
                           + (f" ({r['detail']})" if r.get("detail") else ""))
    streams = (r["response"].json().get("data") or {}).get("result") or []
    return [(ns, line) for s in streams for ns, line in s.get("values") or []]


def key(list_name: str, device: str, protocol: str, neighbor: str) -> str:
    return f"{list_name}|{device}|{protocol}|{neighbor}"


def read(clock=time.time, ask=None, population=None, job=None) -> dict:
    """``{"configured", "adjacencies", "lines", "devices", "window_days"}``. *adjacencies* is
    ``{key: {list, device, protocol, neighbor, interface, drops, by_day, band}}``: *drops* the
    last day's, newest first, each ``{at, epoch, reason}``; *by_day* the count per UTC day over
    the window; *band* its highest. Only adjacencies with a drop in the window are listed.
    *ask*, *population* and *job* stand in for Loki, the inventory and the syslog job in a
    test."""
    from modules.device_logs import host_pattern, job_matcher

    now = clock()
    pop = _population() if population is None else population
    out = {"configured": True, "adjacencies": {}, "lines": 0,
           "devices": len({d for _n, d in pop}), "window_days": WINDOW_DAYS}
    if not pop:
        return out
    query = f'{{{job if job is not None else job_matcher()}}} |~ `{PATTERN}`'
    got = (ask or _ask)(query, now - WINDOW_DAYS * DAY_SECONDS, now)
    reader_job.refuse_truncated(got, LIMIT, "Loki's adjacency lines")
    out["lines"] = len(got)
    patterns = [(name, host, re.compile(host_pattern(host))) for name, host in pop]
    for ns, line in got:
        owner = next(((n, h) for n, h, rx in patterns if rx.search(line)), None)
        if owner is None:
            continue                        # not a managed device's line
        e = event(line, owner[1])
        if not e.get("down"):
            continue
        at = int(ns) / 1e9
        k = key(owner[0], owner[1], e["protocol"], e["neighbor"])
        a = out["adjacencies"].setdefault(k, {
            "list": owner[0], "device": owner[1], "protocol": e["protocol"],
            "neighbor": e["neighbor"], "interface": e["interface"], "drops": [], "by_day": {}})
        day = _iso(at)[:10]
        a["by_day"][day] = a["by_day"].get(day, 0) + 1
        if at >= now - DAY_SECONDS:
            a["drops"].append({"at": _iso(at), "epoch": at, "reason": e["reason"]})
    for a in out["adjacencies"].values():
        a["drops"].sort(key=lambda d: d["epoch"], reverse=True)
        a["band"] = max(a["by_day"].values()) if a["by_day"] else 0
    return out


READER = reader_job.register(reader_job.Reader(
    name="adjacency-log",
    what=("routing adjacencies a managed device logged going down, which a drop between two "
          "scrapes leaves only in the log (C589)"),
    endpoints=("Loki: GET /loki/api/v1/query_range for the devices' syslog job, filtered to "
               "%OSPF-5-ADJCHG, %OSPFv3-5-ADJCHG and %BGP-5-ADJCHANGE, the last "
               f"{WINDOW_DAYS} days (the whole fleet, one query)",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("Loki keeps the line, so nothing is lost between reads; two minutes is how "
                    "soon a row appears, and a day of the lab's syslog was counted in 0.12 s "
                    "(2026-10-16)"),
    read=read,
    invalidates=("adjacencies",),
    remedy="Read the error above: it names what Loki answered",
    window=f"the devices' syslog lines of the last {WINDOW_DAYS} days",
))
