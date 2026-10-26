"""The health of the devices around an alert, over the incident's window (C1714, the operator's
ruling of 2026-10-25 and his correction the same day): the evidence pack's `health` section. A
few compact figures for the alerting device and every device within two hops of it, so Explain
can say whether a device's own figures explain it, and cite the neighbour whose do.

**Who:** the devices `network_model.capture` reached within `HOPS` (a shared segment's members
are one hop: the model's own walk, a segment of more than `network_model.MAX_SEGMENT` listed and
not walked), the managed ones, nearest first (the alert's own device first), at most
`MAX_DEVICES` (the rest counted and said). The topology DETAIL Explain sends stays at its own
one hop; these figures reach two.

**When: the incident's window, never one instant** (the operator's correction, 2026-10-25): from
`ONSET_BEFORE_SECONDS` before the onset to the alert's time, so a spike during the trouble is
visible even when it has passed by the time the alert is found. An onset that is not recorded
is said, and the window is the `ONSET_BEFORE_SECONDS` before the alert's time. A window longer
than `MAX_WINDOW_SECONDS` keeps its last `MAX_WINDOW_SECONDS` and says so (`window["bounded"]`).

**What, each one compact line per device per figure, never a series,** each over that window,
each asked as one question for the whole set of devices (four in all), every one evaluated at
the alert's time:
- ``cpu``: the device's CPU as Prometheus holds it, the 5-minute busy: min, avg and max over
  the raw samples in the window, the max's time, how many samples, and which metric answered.
  Measured, never keyed on a name: the routers carry CISCO-PROCESS-MIB's
  ``cpmCPUTotal5minRev`` and the IOS switches only OLD-CISCO's ``cpuAvgBusy5`` (the lab's
  Prometheus, read on the host 2026-10-11 for History's CPU question and again 2026-10-25,
  tests/fixtures/prometheus/ask_device_names*.json); the first where a device carries it, else
  the second (History's own rule, history_query "cpu"). One question: the raw samples of both
  (a range vector), several CPUs of one device folded to their max per sample.
- ``heartbeat``: Mercury's syslog heartbeat, the line the heartbeat rules count
  (`device_logs.HEARTBEAT_LINE`, matched by the device's own name before its timestamp, as
  `scripts/nmas-heartbeat-rules` matches it), from Loki: how many arrived, the longest gap
  between two and when it ended, and the seconds since the last at the alert's time.
- ``scrapes``: Prometheus's ``up`` for every job scraping the device, from its raw samples
  (each one scrape): how many, how many failed (``up`` 0), the first and the last failed
  scrape's time, and which jobs failed.
- ``discards``: the interface discards (``ifInDiscards`` and ``ifOutDiscards``) as a rate
  summed per device (History's own expression, history_query "errors"), asked as a range at
  one point per `STEP_SECONDS`: min, avg and max of that rate over the window, the max's time.

**Each figure is a piece with a stable reference** (``health:<device id>:<figure>``, the id the
network model gives the device) and its ``read_at``, the time its question was evaluated at
(the window's end); a figure that could not be read says so (``unreadable``,
``not_configured``), one the source holds nothing for says that (``absent``, ``empty``): never
omitted, never invented. Read-only: four questions to the network's Prometheus and Loki,
nothing written.
"""
import logging
import re
import time

log = logging.getLogger(__name__)

HOPS = 2
#: The most devices whose figures a pack keeps: those nearest the alert's device. A two-hop
#: reach through segments of up to 16 is a few dozen at most; 24 devices at four figures keep
#: the section near 100 small pieces, a few thousand tokens. A scale guard, not a measurement.
MAX_DEVICES = 24
#: The window opens this long before the onset (the pack's log window's own lead) and closes
#: at the alert's time.
ONSET_BEFORE_SECONDS = 900
#: The longest window read. Measured: the alerts reader's alerts fire 1 to 13 minutes after
#: their onset (the capture of 2026-09-28, evidence_pack's log window), so the longest window
#: is about 900 + 780 = 1,680 s; 2.5x that is 4,200 s (70 minutes). A longer window (an onset
#: recorded long before the alert is found) keeps its last 70 minutes, and says so.
MAX_WINDOW_SECONDS = 4200
#: The discards rate's own range and the range query's step: four samples of the 60 s SNMP
#: scrape in each rate, one point a minute (the scrape interval).
RATE = "5m"
STEP_SECONDS = 60
#: The heartbeat lines read: a page. 24 devices beating every five minutes for 70 minutes are
#: about 340 lines; a page this size is said as cut when it comes back full.
HEARTBEAT_LINES = 2000
FIGURES = ("cpu", "heartbeat", "scrapes", "discards")
FIGURE_WORDS = {
    "cpu": "CPU busy, 5-minute (percent): min, avg, max over the window, the max's time",
    "heartbeat": ("Mercury's syslog heartbeat: beats in the window, the longest gap (seconds) "
                  "and when it ended, seconds since the last at the alert's time"),
    "scrapes": ("Prometheus scrapes of the device (up): scrapes, failed, the first and last "
                "failed scrape's time, the failing jobs"),
    "discards": ("interface discards, summed over the device (packets/s): min, avg, max over "
                 "the window, the max's time")}
#: The CPU metrics, in the order they are taken (the module's docstring has the measurement).
CPU_METRICS = ("cpmCPUTotal5minRev", "cpuAvgBusy5")


def _iso(ts) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))


def window(onset, at: float) -> dict:
    """The window the figures are of: ``{"start", "end", "seconds", "basis", "bounded"}``, from
    `ONSET_BEFORE_SECONDS` before the onset to the alert's time *at*."""
    end = float(at)
    if onset is None:
        start = end - ONSET_BEFORE_SECONDS
        basis = (f"the onset is not recorded, so the {ONSET_BEFORE_SECONDS // 60} minutes "
                 "before the alert's time")
    else:
        start = min(float(onset) - ONSET_BEFORE_SECONDS, end - STEP_SECONDS)
        basis = (f"from {ONSET_BEFORE_SECONDS // 60} minutes before the onset "
                 f"({_iso(onset)}) to the alert's time")
    bounded = ""
    if end - start > MAX_WINDOW_SECONDS:
        bounded = (f"the window from {_iso(start)} is {int(end - start)} s, over the "
                   f"{MAX_WINDOW_SECONDS} s read: its last {MAX_WINDOW_SECONDS // 60} minutes "
                   "are read")
        start = end - MAX_WINDOW_SECONDS
    return {"start": start, "end": end, "seconds": int(round(end - start)), "basis": basis,
            "bounded": bounded}


def _tag(expr: str, value: str) -> str:
    """*expr* with the constant label ``q`` set to *value*."""
    return f'label_replace({expr}, "q", "{value}", "", "")'


def queries(names: list, seconds: int) -> dict:
    """The three Prometheus questions for *names*: ``{"cpu", "scrapes"}`` instant queries of
    the raw samples in the window (range vectors) and ``"discards"``, a range query's
    expression (asked at `STEP_SECONDS`)."""
    from modules.history_ask import matcher, string

    dev = matcher("device", names)
    w = f"[{int(seconds)}s]"
    cpu = ("{__name__=~" + string("|".join(CPU_METRICS)) + ", " + dev + "}" + w)
    scrapes = "up{" + dev + "}" + w
    sel = "{" + dev + "}"
    discards = (f"sum by (device) (rate(ifInDiscards{sel}[{RATE}]) + "
                f"rate(ifOutDiscards{sel}[{RATE}]))")
    return {"cpu": cpu, "scrapes": scrapes, "discards": discards}


def heartbeat_query(names: list) -> str:
    """Every heartbeat line from *names*: the heartbeat rules' own filters
    (`scripts/nmas-heartbeat-rules` `query_for`), the device matched by its own name before its
    timestamp, every job (a selector needs one label; the line's form is the match)."""
    from modules.device_logs import MARKER
    from modules.history_ask import alternation, literal, string

    beat = r"%HA_EM-\d-LOG: " + literal(MARKER) + ": " + literal(MARKER)
    who = r"\s(?:" + alternation(names) + r"):\s"
    return (f"{{job=~{string('.+')}}} |= {string(MARKER)} |~ {string(beat)} "
            f"|~ {string(who)}")


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x                         # NaN is no value


def _prom(prom, path: str, **params) -> tuple:
    """``(rows, error)``: one question's result rows."""
    r = prom._get(path, **params)                        # noqa: SLF001 (the client's one GET)
    if not r.get("ok"):
        detail = f": {r['detail']}" if r.get("detail") else ""
        return None, f"Prometheus could not be asked ({r.get('error') or 'no answer'}{detail})"
    try:
        body = r["response"].json()
    except (ValueError, AttributeError) as exc:
        return None, f"Prometheus's answer could not be read ({type(exc).__name__})"
    if (body or {}).get("status") == "error":
        return None, f"Prometheus refused the query: {body.get('error') or 'no reason given'}"
    return ((body or {}).get("data") or {}).get("result") or [], ""


def _samples(row, start: float, end: float) -> list:
    """``[(t, value)]`` of one series inside the window, NaN left out."""
    out = []
    for t, v in row.get("values") or ([row["value"]] if row.get("value") else []):
        x, t = _num(v), float(t)
        if x is not None and start <= t <= end:
            out.append((t, x))
    return out


def _summary(points: list) -> dict:
    """min, avg, max (one decimal) and the max's time of ``[(t, value)]``, the first peak if
    it repeats."""
    peak = max(points, key=lambda p: (p[1], -p[0]))
    return {"min": round(min(v for _t, v in points), 1),
            "avg": round(sum(v for _t, v in points) / len(points), 1),
            "max": round(peak[1], 1), "peak_at": _iso(peak[0])}


def _cpu(rows, start, end) -> dict:
    """``{device: {metric: [(t, value)]}}``, several CPUs folded to their max per sample."""
    out = {}
    for row in rows:
        m = row.get("metric") or {}
        metric = m.get("__name__") or ""
        if m.get("device") and metric in CPU_METRICS:
            held = out.setdefault(m["device"], {}).setdefault(metric, {})
            for t, v in _samples(row, start, end):
                held[t] = max(v, held.get(t, v))
    return {d: {k: sorted(v.items()) for k, v in ms.items()} for d, ms in out.items()}


def _scrapes(rows, start, end) -> dict:
    """``{device: {job: [(t, up)]}}``."""
    out = {}
    for row in rows:
        m = row.get("metric") or {}
        if m.get("device"):
            out.setdefault(m["device"], {}).setdefault(m.get("job") or "", []).extend(
                _samples(row, start, end))
    return out


def _discards(rows, start, end) -> dict:
    """``{device: [(t, rate)]}``."""
    return {(r.get("metric") or {}).get("device"): _samples(r, start, end)
            for r in rows if (r.get("metric") or {}).get("device")}


def _heartbeats(loki, names: list, start: float, end: float) -> tuple:
    """``({device: [arrival seconds]}, error, cut)``: the heartbeat lines in the window,
    attributed by the device's own name in the line (the rules' own match), else its label."""
    from modules.device_logs import HEARTBEAT_LINE

    r = loki._get("loki/api/v1/query_range", query=heartbeat_query(names),     # noqa: SLF001
                  start=str(int(start * 1e9)), end=str(int(end * 1e9)),
                  limit=HEARTBEAT_LINES, direction="backward")
    if not r.get("ok"):
        detail = f": {r['detail']}" if r.get("detail") else ""
        return None, f"Loki could not be asked ({r.get('error') or 'no answer'}{detail})", False
    try:
        data = (r["response"].json() or {}).get("data") or {}
    except (ValueError, AttributeError) as exc:
        return None, f"Loki's answer could not be read ({type(exc).__name__})", False
    who = re.compile(r"\s(" + "|".join(re.escape(n) for n in names) + r"):\s")
    beat = re.compile(HEARTBEAT_LINE)
    out, lines = {}, 0
    for stream in data.get("result") or []:
        label = (stream.get("stream") or {}).get("device") or ""
        for ns, line in stream.get("values") or []:
            lines += 1
            if not beat.search(line or ""):
                continue
            m = who.search(line)
            dev = m.group(1) if m else (label if label in names else "")
            t = int(ns) / 1e9
            if dev and start <= t <= end:
                out.setdefault(dev, []).append(t)
    return out, "", lines >= HEARTBEAT_LINES


def _piece(dev, name, hop, fig, state, read_at, why="", **fields) -> dict:
    return {"ref": f"health:{dev}:{fig}", "dev": dev, "device": name, "hop": hop,
            "figure": fig, "state": state, "read_at": read_at, **fields,
            **({"why": why} if why else {})}


def devices_of(capture: dict, host: str, subject_id: str = "") -> tuple:
    """``([(id, name, hop)], total)``: who the figures are read for, nearest first and by
    name, the alert's device first; at most `MAX_DEVICES`."""
    if not capture or not capture.get("ok"):
        return [(subject_id or f"dev:@{host}", host, 0)], 1
    nodes, reached = capture.get("nodes") or {}, capture.get("reached") or {}
    rows = sorted(((reached[n]["hop"], nodes[n].get("name") or n, n) for n in nodes
                   if n in reached), key=lambda r: (r[0], r[1]))
    return [(n, name, hop) for hop, name, n in rows[:MAX_DEVICES]], len(rows)


def read(network: str, devices: list, onset, at: float, prom=None, loki=None) -> dict:
    """The figures of *devices* (``[(id, name, hop)]``) over the incident's window ending at
    *at*: ``{"window", "pieces", "errors", "asked"}``. Never raises: a source that fails is
    each of its figures saying so. *prom* and *loki* stand in for the network's clients
    (tests)."""
    win = window(onset, at)
    start, end, seconds = win["start"], win["end"], win["seconds"]
    names = [n for _d, n, _h in devices]
    read_at = _iso(end)
    errors, asked, answers = [], 0, {}
    if prom is None:
        from modules.integrations.prometheus import PrometheusIntegration
        prom = PrometheusIntegration(list_name=network)
    try:
        prom_on = prom.is_configured()
    except Exception as exc:                            # noqa: BLE001 (said, never raised)
        prom_on, errors = False, [f"Prometheus's configuration could not be read ({exc})"]
    if prom_on and names:
        q = queries(names, seconds)
        asks = {"cpu": ("api/v1/query", {"query": q["cpu"], "time": f"{end:.3f}"}),
                "scrapes": ("api/v1/query", {"query": q["scrapes"], "time": f"{end:.3f}"}),
                "discards": ("api/v1/query_range", {
                    "query": q["discards"], "start": f"{start:.3f}", "end": f"{end:.3f}",
                    "step": str(STEP_SECONDS)})}
        for fig, (path, params) in asks.items():
            asked += 1
            try:
                rows, err = _prom(prom, path, **params)
            except Exception as exc:                    # noqa: BLE001
                rows, err = None, f"Prometheus could not be asked ({type(exc).__name__})"
            answers[fig] = (rows, err)
            if err:
                errors.append(f"{fig}: {err}")
    beats, beat_err, cut = None, "", False
    try:
        if loki is None:
            from modules import history_logq as Q
            loki = Q._client(network, Q.wait(Q.limits(network)))     # noqa: SLF001
        loki_on = loki.is_configured()
    except Exception as exc:                            # noqa: BLE001
        loki_on, beat_err = False, f"Loki's configuration could not be read ({exc})"
    if loki_on and names:
        asked += 1
        try:
            beats, beat_err, cut = _heartbeats(loki, names, start, end)
        except Exception as exc:                        # noqa: BLE001
            beats, beat_err = None, f"Loki could not be asked ({type(exc).__name__})"
        if beat_err:
            errors.append(f"heartbeat: {beat_err}")

    def got(fig, fold):
        rows = (answers.get(fig) or (None, ""))[0]
        return fold(rows, start, end) if rows is not None else None

    cpu, scr, dis = got("cpu", _cpu), got("scrapes", _scrapes), got("discards", _discards)
    span = f"between {_iso(start)} and {_iso(end)}"

    def failed(fig):
        err = (answers.get(fig) or (None, ""))[1]
        if not prom_on:
            return "not_configured", err or f"no Prometheus is configured for {network}"
        return "unreadable", err

    pieces = []
    for dev, name, hop in devices:
        def p(fig, state, why="", **f):
            pieces.append(_piece(dev, name, hop, fig, state, read_at, why, **f))
        # CPU
        if cpu is None:
            p("cpu", *failed("cpu"))
        else:
            mine = cpu.get(name) or {}
            metric = next((m for m in CPU_METRICS if mine.get(m)), "")
            if metric:
                p("cpu", "ok", metric=metric, **_summary(mine[metric]),
                  samples=len(mine[metric]), unit="percent")
            else:
                p("cpu", "absent", f"Prometheus holds no CPU series for {name} "
                                   f"({' or '.join(CPU_METRICS)}) {span}")
        # Heartbeat
        if beats is None:
            if not loki_on and not beat_err:
                p("heartbeat", "not_configured", f"no log store is configured for {network}")
            else:
                p("heartbeat", "unreadable", beat_err)
        else:
            t = sorted(beats.get(name) or [])
            if not t:
                p("heartbeat", "empty", f"Loki holds no heartbeat line from {name} {span}",
                  beats=0, since_last_s=None, max_gap_s=None)
            else:
                gaps = [(b - a, b) for a, b in zip(t, t[1:])]
                # The first of the longest, to the second (a tie is the earlier gap).
                longest = max(gaps, key=lambda g: round(g[0])) if gaps else None
                extra = {"cut": f"Loki's page of {HEARTBEAT_LINES} lines came back full: "
                                "earlier heartbeats were not read"} if cut else {}
                p("heartbeat", "ok", beats=len(t),
                  max_gap_s=round(longest[0]) if longest else None,
                  max_gap_ended_at=_iso(longest[1]) if longest else None,
                  since_last_s=round(end - t[-1]), last_at=_iso(t[-1]), **extra)
        # Scrapes
        if scr is None:
            p("scrapes", *failed("scrapes"))
        else:
            jobs = scr.get(name) or {}
            samples = [(ts, v, job) for job, pts in jobs.items() for ts, v in pts]
            if not samples:
                p("scrapes", "absent", f"Prometheus holds no up series for {name} {span}")
            else:
                bad = sorted(ts for ts, v, _j in samples if v == 0)
                p("scrapes", "ok", scrapes=len(samples), failed=len(bad),
                  first_failed_at=_iso(bad[0]) if bad else None,
                  last_failed_at=_iso(bad[-1]) if bad else None,
                  jobs_failing=sorted({j for _t, v, j in samples if v == 0}))
        # Discards
        if dis is None:
            p("discards", *failed("discards"))
        else:
            pts = dis.get(name) or []
            if not pts:
                p("discards", "absent", f"Prometheus holds no interface discard counters for "
                                        f"{name} {span}")
            else:
                p("discards", "ok", **_summary(pts), points=len(pts), unit="packets/s")
    return {"window": {"from": _iso(start), "to": _iso(end), "basis": win["basis"],
                       "words": (f"the {seconds // 60} minutes {win['basis']}"
                                 + (f"; {win['bounded']}" if win["bounded"] else "")),
                       **({"bounded": win["bounded"]} if win["bounded"] else {}),
                       "step_s": STEP_SECONDS},
            "pieces": pieces, "errors": errors, "asked": asked}


#: How the figures go to a model (the operator, 2026-10-26: one line per device, every device
#: kept; C1547's 11 devices took about 5,600 tokens as pieces and about 810 as lines). Each
#: figure keeps its reference, `health:<device id>:<figure>`, from the device id the line
#: names; times are the window's, UTC, to the second.
LINE_FORMAT = ("one line per device: <device> (<device id>, hop <n>): then each figure, "
               "'cpu min/avg/max% peak <time>', 'heartbeat <beats> beats, gap <longest gap>s "
               "to <when it ended>, last <seconds before the alert>s', 'scrapes "
               "<failed>/<scrapes> failed <first>-<last> (<jobs>)', 'discards min/avg/max/s "
               "peak <time>' ('discards 0/s' when there were none), or the figure's state and "
               "why it was not measured. A figure's reference is health:<device id>:<figure>.")


def _clock(iso) -> str:
    return (iso or "")[11:19] or "-"


def _figure_words(p: dict) -> str:
    """One figure in a few words (`LINE_FORMAT`), from its piece."""
    fig, state = p["figure"], p.get("state")
    if state != "ok":
        return f"{fig} {state}" + (f" ({p['why']})" if p.get("why") else "")
    if fig == "cpu":
        return f"cpu {p['min']:g}/{p['avg']:g}/{p['max']:g}% peak {_clock(p.get('peak_at'))}"
    if fig == "discards":
        if not p["max"]:
            return "discards 0/s"
        return (f"discards {p['min']:g}/{p['avg']:g}/{p['max']:g}/s "
                f"peak {_clock(p.get('peak_at'))}")
    if fig == "heartbeat":
        gap = (f", gap {p['max_gap_s']}s to {_clock(p.get('max_gap_ended_at'))}"
               if p.get("max_gap_s") is not None else "")
        last = (f", last {p['since_last_s']}s" if p.get("since_last_s") is not None else "")
        return f"heartbeat {p.get('beats', 0)} beats{gap}{last}" + (
            f" ({p['cut']})" if p.get("cut") else "")
    out = f"scrapes {p.get('failed', 0)}/{p.get('scrapes', 0)} failed"
    if p.get("failed"):
        out += (f" {_clock(p.get('first_failed_at'))}-{_clock(p.get('last_failed_at'))}"
                f" ({', '.join(p.get('jobs_failing') or [])})")
    return out


def lines(pieces: list) -> list:
    """The pieces as one line per device, in the pieces' order (nearest first)."""
    order, by = [], {}
    for p in pieces:
        key = (p.get("device"), p.get("dev"), p.get("hop"))
        if key not in by:
            order.append(key)
            by[key] = []
        by[key].append(_figure_words(p))
    return [f"{d} ({i}, hop {h}): " + "; ".join(by[(d, i, h)]) for d, i, h in order]
