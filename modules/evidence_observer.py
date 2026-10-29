"""The monitoring side over an alert's window (C1896, the first slice of C1722's host telemetry):
the evidence pack's `observer` section. When several devices fail at once from one collector,
the collector and what is beneath the devices are candidate causes beside each device's own;
this section is the collector's side of that question, the health section the devices'.

**Over the health section's window** (`evidence_health.window`: from 15 minutes before the
onset to the alert's time, its last 70 minutes when longer), every question evaluated at the
alert's time, read-only, nothing written.

**Which collector:** the Prometheus scrape jobs that poll the alert's device or a device within
two hops of it (the health section's devices, `evidence_health.devices_of`), found by their
``up`` series' ``device`` label, at most `MAX_JOBS` (the rest counted and said). Each job is
read across ALL its targets, not only those devices: a collector failing is many targets
failing together.

**The pieces, each with a stable reference ``observer:<what>``** and its read state, as the
health figures carry theirs (``ok``, ``absent`` when Prometheus holds nothing for it,
``unreadable`` when a question failed, ``not_configured`` with no Prometheus): never omitted,
never invented.
- ``observer:job:<job>``, one per job: its targets, its scrapes and how many failed (``up`` 0,
  from the raw samples), how many targets failed at least once; minute by minute, how many of
  its targets were failing (the most at once and when, the first and last failing minute, the
  minutes with half or more failing); its slowest scrape against its timeout (the timeout and
  interval from Prometheus's configuration as it is now, `status/config`, said so); and the
  quickest failed scrape: a failure that runs to the timeout is a target that did not answer in
  time, one over in under `REFUSED_UNDER_S` was refused.
- ``observer:exporter``: the SNMP exporter, as Prometheus holds it. Its own scrape of itself
  (a job whose target exposes ``snmp_exporter_build_info``) when Prometheus scrapes one, else
  said not collected; the packets it sent and retried and its slowest walk, from the
  ``snmp_scrape_*`` series it adds to every scrape that completes; and how many targets of its
  jobs had a failure over in under `REFUSED_UNDER_S` (refused). Absent when no job's scrapes came
  through an SNMP exporter.
- ``observer:host:cpu``, ``observer:host:load``, ``observer:host:memory``: the host Prometheus
  runs on, from the node exporter it scrapes on that host (its instance a loopback address,
  `LOCAL_INSTANCE`: ``localhost``, ``127.0.0.1`` or ``[::1]``): CPU busy (percent) and the 1-minute
  load, each min, avg and max over the window with the max's time, beside its usual (the median
  over the `USUAL_SECONDS` before the window) and the host's CPU count; and the memory available
  (percent of the total), min, avg and max. Absent when Prometheus scrapes no node exporter on
  its own host.

**Bounded:** six questions for the whole set (the jobs, their figures, their minutes, the
configuration, and the host's two), each aggregated by job or by host, so their size does not
grow with the fleet; each carries Prometheus's own evaluation bound (`QUERY_TIMEOUT_S`, the
client's own wait, so Prometheus stops evaluating a question Mercury has stopped waiting for).
"""
import logging

log = logging.getLogger(__name__)

#: A failed scrape over in under this was refused (by the SNMP exporter or Prometheus), never a
#: device that did not answer. Measured over 44 days on the lab's Prometheus (the alert backtest
#: of 2026-10-27, C1856): every device-side failure ran 20 to 55 s, to its timeout; the SNMP
#: exporter's refusals of 2026-09-19 were each over in under 1 s.
REFUSED_UNDER_S = 5
#: The step of the one subquery (the quickest failed scrape): finer than any scrape interval
#: (the lab's are 30 s, tests/fixtures/prometheus/status_config.json), so no failed sample is
#: stepped over; a minimum is not moved by a sample seen at two steps.
SUB_STEP_SECONDS = 15
#: The host's CPU rate range: four samples of the node exporter's 30 s scrape (the lab's
#: configuration, as above), so a busy minute is not averaged away.
HOST_RATE = "2m"
#: The host's usual: the median over the day before the window (a day holds the host's own
#: daily jobs, so a nightly peak does not read as unusual).
USUAL_SECONDS = 86400
#: The node exporter on Prometheus's own host: a loopback instance, IPv4 or IPv6.
LOCAL_INSTANCE = r"(localhost|127\.0\.0\.1|\[::1\]):[0-9]+"
#: Each question's evaluation bound in Prometheus (its `timeout` parameter): the client's own
#: wait (`integrations.base.DEFAULT_TIMEOUT`, 5 s). Measured on the lab's Prometheus
#: (2026-10-27, read-only, for Walk 2's alert, 7 jobs and their 40 targets, and a quiet window
#: of 2026-10-25): the slowest question, the jobs' figures, took 0.06 s and the host's day-long
#: usual 0.01 s; 5 s is over 80 times the slowest, so the bound fires only on a Prometheus that
#: is itself in trouble, and the piece then says which question it was.
QUERY_TIMEOUT_S = 5
#: The most jobs read (the rest counted): a scale guard. A device is scraped by a handful of
#: jobs (the lab's routers by up to six, its switches by up to four), so the two-hop devices'
#: jobs are a few; 20 keeps the figures' answer a few hundred series at most.
MAX_JOBS = 20
#: The ``q`` tags of the job figures' one question.
JOB_FIGURES = ("targets", "scrapes", "failed", "targets_failed", "slowest", "quickest_failed",
               "refused", "snmp_sent", "snmp_retried", "snmp_walk")


def _tag(expr: str, value: str) -> str:
    from modules.evidence_health import _tag as tag
    return tag(expr, value)


def jobs_query(names: list, seconds: int) -> str:
    """The jobs that scraped any of *names* in the window: one series per job."""
    from modules.history_ask import matcher
    return (f"count by (job) (count_over_time(up{{{matcher('device', names)}}}"
            f"[{int(seconds)}s]))")


def job_queries(jobs: list, seconds: int) -> dict:
    """``{"figures", "minutes"}``: every target of *jobs*, aggregated by job. *figures* is one
    instant question (each part tagged ``q``, `JOB_FIGURES`), *minutes* a range question's
    expression (a point a minute): how many targets were failing, and how many there were."""
    from modules.history_ask import matcher

    sel = "{" + matcher("job", jobs) + "}"
    w = f"[{int(seconds)}s]"
    count, total = f"count_over_time(up{sel}{w})", f"sum_over_time(up{sel}{w})"
    failed_each = f"({count} - {total})"
    fail_dur = f"(scrape_duration_seconds{sel} and on(instance, job) (up{sel} == 0))"
    quickest = f"min_over_time({fail_dur}[{int(seconds)}s:{SUB_STEP_SECONDS}s])"
    parts = {
        "targets": f"count by (job) ({count})",
        "scrapes": f"sum by (job) ({count})",
        "failed": f"sum by (job) ({failed_each})",
        "targets_failed": f"count by (job) ({failed_each} > 0)",
        "slowest": f"max by (job) (max_over_time(scrape_duration_seconds{sel}{w}))",
        "quickest_failed": f"min by (job) ({quickest})",
        "refused": f"count by (job) ({quickest} < {REFUSED_UNDER_S})",
        "snmp_sent": f"sum by (job) (sum_over_time(snmp_scrape_packets_sent{sel}{w}))",
        "snmp_retried": f"sum by (job) (sum_over_time(snmp_scrape_packets_retried{sel}{w}))",
        "snmp_walk": f"max by (job) (max_over_time(snmp_scrape_duration_seconds{sel}{w}))",
    }
    # The exporter's own scrape of itself: any job whose target exposes the exporter's build.
    own = f"on(job, instance) last_over_time(snmp_exporter_build_info{w})"
    parts["self_scrapes"] = f"sum by (job) (count_over_time(up{w}) and {own})"
    parts["self_failed"] = (f"sum by (job) ((count_over_time(up{w}) - sum_over_time(up{w})) "
                            f"and {own})")
    figures = " or ".join(_tag(e, k) for k, e in parts.items())
    minutes = " or ".join([_tag(f"sum by (job) (1 - up{sel})", "failing"),
                           _tag(f"count by (job) (up{sel})", "targets")])
    return {"figures": figures, "minutes": minutes}


def host_queries(seconds: int) -> dict:
    """``{"range", "now"}``: the collector's host, a range question (a point a minute: CPU busy,
    load, memory available) and one instant question (its CPU count, and the usual of CPU and
    load over the day before the window)."""
    from modules.history_ask import string

    inst = "instance=~" + string(LOCAL_INSTANCE)
    cpu = (f"100 * (1 - avg by (instance) (rate(node_cpu_seconds_total{{mode=\"idle\", "
           f"{inst}}}[{HOST_RATE}])))")
    load = f"max by (instance) (node_load1{{{inst}}})"
    mem = (f"100 * max by (instance) (node_memory_MemAvailable_bytes{{{inst}}}) / "
           f"max by (instance) (node_memory_MemTotal_bytes{{{inst}}})")
    rng = " or ".join([_tag(cpu, "cpu"), _tag(load, "load"), _tag(mem, "memory")])
    off = f"offset {int(seconds)}s"
    now = " or ".join([
        _tag(f"count by (instance) (node_cpu_seconds_total{{mode=\"idle\", {inst}}})", "cpus"),
        _tag(f"quantile_over_time(0.5, ({cpu})[{USUAL_SECONDS}s:5m] {off})", "usual_cpu"),
        _tag(f"max by (instance) (quantile_over_time(0.5, node_load1{{{inst}}}"
             f"[{USUAL_SECONDS}s] {off}))", "usual_load")])
    return {"range": rng, "now": now}


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _iso(ts) -> str:
    from modules.evidence_health import _iso as iso
    return iso(ts)


def _summary(points: list) -> dict:
    from modules.evidence_health import _summary as summary
    return summary(points)


def _seconds(text) -> float:
    from modules.history_ask import parse_duration
    return parse_duration(str(text)) if text else None


def timeouts(prom) -> tuple:
    """``({job: {"interval_s", "timeout_s"}}, error)`` from Prometheus's configuration as it is
    now (`status/config`): each job's own, else the global's. Thanos Query serves no
    configuration: then ``({}, why)``, and each job says its timeout is not known."""
    import yaml

    r = prom._get("api/v1/status/config")                # noqa: SLF001 (the client's one GET)
    if not r.get("ok"):
        return {}, f"Prometheus's configuration could not be read ({r.get('error')})"
    try:
        doc = yaml.safe_load(((r["response"].json() or {}).get("data") or {}).get("yaml")
                             or "") or {}
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        return {}, f"Prometheus's configuration could not be read ({type(exc).__name__})"
    glob = doc.get("global") or {}
    out = {}
    for job in doc.get("scrape_configs") or []:
        name = job.get("job_name")
        if not name:
            continue
        out[name] = {"interval_s": _seconds(job.get("scrape_interval")
                                            or glob.get("scrape_interval") or "1m"),
                     "timeout_s": _seconds(job.get("scrape_timeout")
                                           or glob.get("scrape_timeout") or "10s")}
    return out, ""


def _rows(prom, path: str, **params) -> tuple:
    from modules.evidence_health import _prom
    return _prom(prom, path, timeout=f"{QUERY_TIMEOUT_S}s", **params)


def _by(rows, key: str) -> dict:
    """``{(q, key value): row}``."""
    return {((r.get("metric") or {}).get("q"), (r.get("metric") or {}).get(key)): r
            for r in rows or []}


def _value(row):
    return _num((row or {}).get("value", [None, None])[1]) if row else None


def _round(x, places=1):
    return None if x is None else round(x, places)


def _minutes(failing: list, targets: dict) -> dict:
    """The minutes' figures of one job from its range points: ``[(t, failing)]`` and
    ``{t: targets}``."""
    bad = [(t, n) for t, n in failing if n and n > 0]
    if not bad:
        return {"minutes": len(failing), "minutes_failing": 0, "most_failing": 0,
                "most_failing_at": None, "first_failing_at": None, "last_failing_at": None,
                "minutes_half_failing": 0}
    most = max(bad, key=lambda p: (p[1], -p[0]))
    half = sum(1 for t, n in bad if targets.get(t) and n >= targets[t] / 2)
    return {"minutes": len(failing), "minutes_failing": len(bad), "most_failing": int(most[1]),
            "most_failing_at": _iso(most[0]), "most_failing_of": int(targets.get(most[0]) or 0),
            "first_failing_at": _iso(bad[0][0]), "last_failing_at": _iso(bad[-1][0]),
            "minutes_half_failing": half}


def read(network: str, names: list, onset, at: float, prom=None) -> dict:
    """The observer's pieces over the window ending at *at*, for the jobs polling *names* (the
    health section's devices): ``{"window", "pieces", "errors", "asked", "jobs_total"}``. Never
    raises: a question that fails is each of its pieces saying so. *prom* stands in for the
    network's client (tests)."""
    from modules import evidence_health as H

    win = H.window(onset, at)
    start, end, seconds = win["start"], win["end"], win["seconds"]
    read_at = _iso(end)
    span = f"between {_iso(start)} and {_iso(end)}"
    errors, asked = [], 0
    if prom is None:
        from modules.integrations.prometheus import PrometheusIntegration
        prom = PrometheusIntegration(list_name=network)
    try:
        prom_on = prom.is_configured()
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        prom_on, errors = False, [f"Prometheus's configuration could not be read ({exc})"]
    pieces = []

    def piece(what, state, why="", **fields):
        pieces.append({"ref": f"observer:{what}", "what": what, "state": state,
                       "read_at": read_at, **fields, **({"why": why} if why else {})})

    def ask(name, path, **params):
        nonlocal asked
        asked += 1
        try:
            rows, err = _rows(prom, path, **params)
        except Exception as exc:                      # noqa: BLE001
            rows, err = None, f"Prometheus could not be asked ({type(exc).__name__})"
        if err:
            errors.append(f"{name}: {err}")
        return rows, err

    if not prom_on:
        why = errors[0] if errors else f"no Prometheus is configured for {network}"
        for what in ("jobs", "exporter", "host:cpu", "host:load", "host:memory"):
            piece(what, "not_configured", why)
        return _out(win, pieces, errors, asked, 0)

    at_end = {"time": f"{end:.3f}"}
    ranged = {"start": f"{start:.3f}", "end": f"{end:.3f}", "step": str(H.STEP_SECONDS)}
    # The jobs polling the devices, then every target of theirs.
    jobs, total = [], 0
    rows, err = ask("jobs", "api/v1/query", query=jobs_query(names, seconds), **at_end) \
        if names else ([], "")
    if err:
        piece("jobs", "unreadable", err)
        piece("exporter", "unreadable", err)
    else:
        found = sorted({(r.get("metric") or {}).get("job") for r in rows or []} - {None, ""})
        total, jobs = len(found), found[:MAX_JOBS]
        if not jobs:
            piece("jobs", "absent", f"Prometheus holds no up series for "
                                    f"{', '.join(names) or 'any device'} {span}")
            piece("exporter", "absent", "no job polls these devices")
    if jobs:
        conf, conf_err = timeouts(prom)
        asked += 1
        if conf_err:
            errors.append(f"configuration: {conf_err}")
        q = job_queries(jobs, seconds)
        figs, ferr = ask("figures", "api/v1/query", query=q["figures"], **at_end)
        mins, merr = ask("minutes", "api/v1/query_range", query=q["minutes"], **ranged)
        figs, mins = _by(figs, "job"), _by(mins, "job")
        for job in jobs:
            if ferr:
                piece(f"job:{job}", "unreadable", ferr, job=job)
                continue
            n = _value(figs.get(("targets", job)))
            if not n:
                piece(f"job:{job}", "absent", f"Prometheus holds no up series for job {job} "
                                              f"{span}", job=job)
                continue
            got = {k: _value(figs.get((k, job))) for k in JOB_FIGURES}
            c = conf.get(job) or {}
            fields = {"job": job, "targets": int(n), "scrapes": int(got["scrapes"] or 0),
                      "failed": int(got["failed"] or 0),
                      "targets_failed": int(got["targets_failed"] or 0),
                      "slowest_s": _round(got["slowest"]),
                      "timeout_s": c.get("timeout_s"), "interval_s": c.get("interval_s"),
                      "quickest_failed_s": _round(got["quickest_failed"]),
                      "refused_targets": int(got["refused"] or 0)}
            if not c:
                fields["timeout_from"] = (conf_err or f"job {job} is not in Prometheus's "
                                                      "configuration as it is now")
            else:
                fields["timeout_from"] = "Prometheus's configuration as it is now"
            if merr:
                fields["minutes_why"] = merr
            else:
                fail = [(float(t), _num(v)) for t, v in
                        (mins.get(("failing", job)) or {}).get("values") or []]
                tgt = {float(t): _num(v) for t, v in
                       (mins.get(("targets", job)) or {}).get("values") or []}
                fields.update(_minutes(fail, tgt))
            piece(f"job:{job}", "ok", **fields)
        # The SNMP exporter: the jobs its series came through, and its own scrape.
        snmp = [j for j in jobs if _value(figs.get(("snmp_sent", j))) is not None]
        own = sorted({j for (k, j) in figs if k == "self_scrapes"})
        if ferr:
            piece("exporter", "unreadable", ferr)
        elif not snmp and not own:
            piece("exporter", "absent", "no job's scrapes came through an SNMP exporter (no "
                                        f"snmp_scrape_* series) {span}")
        else:
            walk = [_value(figs.get(("snmp_walk", j))) for j in snmp]
            fields = {"jobs": snmp,
                      "packets_sent": int(sum(_value(figs.get(("snmp_sent", j))) or 0
                                              for j in snmp)),
                      "packets_retried": int(sum(_value(figs.get(("snmp_retried", j))) or 0
                                                 for j in snmp)),
                      "slowest_walk_s": _round(max([w for w in walk if w is not None],
                                                   default=None)),
                      "refused_targets": int(sum(_value(figs.get(("refused", j))) or 0
                                                 for j in snmp)),
                      "refused_under_s": REFUSED_UNDER_S}
            if own:
                fields["self"] = {j: {"scrapes": int(_value(figs.get(("self_scrapes", j))) or 0),
                                      "failed": int(_value(figs.get(("self_failed", j))) or 0)}
                                  for j in own}
            else:
                fields["self_why"] = ("not collected: Prometheus scrapes no SNMP exporter of its "
                                      "own (no target exposes snmp_exporter_build_info)")
            piece("exporter", "ok", **fields)
    # The collector's host.
    hq = host_queries(seconds)
    hr, herr = ask("host", "api/v1/query_range", query=hq["range"], **ranged)
    hn, nerr = ask("host usual", "api/v1/query", query=hq["now"], **at_end)
    _host(piece, hr, herr, hn, nerr, span)
    return _out(win, pieces, errors, asked, total)


def _host(piece, rows, err, now_rows, now_err, span) -> None:
    """The host's three pieces from the range rows and the instant rows."""
    if err:
        for what in ("host:cpu", "host:load", "host:memory"):
            piece(what, "unreadable", err)
        return
    by = {}
    for r in rows or []:
        m = r.get("metric") or {}
        pts = [(float(t), _num(v)) for t, v in r.get("values") or []]
        by.setdefault(m.get("instance") or "", {})[m.get("q")] = [p for p in pts
                                                                  if p[1] is not None]
    if not by:
        why = ("Prometheus scrapes no node exporter on its own host (an instance at localhost, "
               f"127.0.0.1 or [::1]) {span}")
        for what in ("host:cpu", "host:load", "host:memory"):
            piece(what, "absent", why)
        return
    inst = sorted(by)[0]
    mine = by[inst]
    extra = {}
    for r in now_rows or []:
        m = r.get("metric") or {}
        if (m.get("instance") or inst) == inst:
            extra[m.get("q")] = _value(r)
    cpus = int(extra["cpus"]) if extra.get("cpus") else None
    usual_why = {"usual_why": now_err} if now_err else {}
    for what, q, unit in (("host:cpu", "cpu", "percent"), ("host:load", "load", "load1"),
                          ("host:memory", "memory", "percent")):
        pts = mine.get(q) or []
        if not pts:
            piece(what, "absent", f"Prometheus holds no {q} series for {inst} {span}",
                  instance=inst)
            continue
        fields = {"instance": inst, **_summary(pts), "points": len(pts), "unit": unit}
        if q in ("cpu", "load"):
            fields["cpus"] = cpus
            fields["usual"] = _round(extra.get(f"usual_{q}"))
            fields.update(usual_why)
        if q == "memory":
            # Available memory's trouble is its least: the min's time, not the max's.
            low = min(pts, key=lambda p: (p[1], p[0]))
            fields["low_at"] = _iso(low[0])
            fields.pop("peak_at", None)
        piece(what, "ok", **fields)


def _out(win, pieces, errors, asked, total) -> dict:
    return {"window": {"from": _iso(win["start"]), "to": _iso(win["end"]),
                       "basis": win["basis"],
                       "words": (f"the {win['seconds'] // 60} minutes {win['basis']}"
                                 + (f"; {win['bounded']}" if win["bounded"] else "")),
                       **({"bounded": win["bounded"]} if win["bounded"] else {})},
            "pieces": pieces, "errors": errors, "asked": asked, "jobs_total": total}


#: How the pieces go to a model: one line each, its reference first (the health figures' own
#: trim, the operator's of 2026-10-26).
LINE_FORMAT = (
    "one line per piece, its reference first: observer:job:<job> (<targets> targets, every "
    "<interval>s, timeout <timeout>s): '<failed>/<scrapes> scrapes failed on <n> of <targets> "
    "targets', 'failing <first>-<last>, most at once <k> of <targets> at <time>, <m> of "
    "<minutes> minutes failing, <h> with half or more', 'slowest <s>s, quickest failure <s>s'; "
    "observer:exporter: the jobs it served, packets sent and retried, its slowest walk, the "
    "targets refused, its own scrape; observer:host:cpu and observer:host:load: min/avg/max "
    "peak <time>, usual <median over the day before>, on <n> CPUs; observer:host:memory: "
    "available min/avg/max%; or the piece's state and why it was not measured")


def _clock(iso) -> str:
    return (iso or "")[11:19] or "-"


def _n(x) -> str:
    return "-" if x is None else f"{x:g}"


def line(p: dict) -> str:
    """One piece in a few words (`LINE_FORMAT`)."""
    ref, state = p["ref"], p.get("state")
    if state != "ok":
        return f"{ref}: {state}" + (f" ({p['why']})" if p.get("why") else "")
    what = p.get("what") or ""
    if what.startswith("job:"):
        head = (f"{ref} ({p['targets']} targets, every {_n(p.get('interval_s'))}s, timeout "
                f"{_n(p.get('timeout_s'))}s): {p['failed']}/{p['scrapes']} scrapes failed on "
                f"{p['targets_failed']} of {p['targets']} targets")
        if p.get("minutes_why"):
            head += f"; minutes unreadable ({p['minutes_why']})"
        elif p.get("minutes_failing"):
            head += (f"; failing {_clock(p['first_failing_at'])}-"
                     f"{_clock(p['last_failing_at'])}, most at once {p['most_failing']} of "
                     f"{p.get('most_failing_of') or p['targets']} at "
                     f"{_clock(p['most_failing_at'])}, {p['minutes_failing']} of "
                     f"{p['minutes']} minutes failing, {p['minutes_half_failing']} with half "
                     "or more")
        else:
            head += f"; no minute failing of {p.get('minutes', 0)}"
        head += f"; slowest {_n(p.get('slowest_s'))}s"
        if p.get("quickest_failed_s") is not None:
            head += f", quickest failure {_n(p['quickest_failed_s'])}s"
        if p.get("refused_targets"):
            head += f", {p['refused_targets']} targets refused (a failure under " \
                    f"{REFUSED_UNDER_S}s)"
        return head
    if what == "exporter":
        own = ("; its own scrape " + ", ".join(f"{j} {v['failed']}/{v['scrapes']} failed"
                                               for j, v in sorted((p.get("self") or {}).items()))
               if p.get("self") else f"; its own scrape {p.get('self_why', 'not collected')}")
        return (f"{ref}: through {', '.join(p.get('jobs') or []) or 'no job'}: "
                f"{p.get('packets_sent', 0)} packets sent, {p.get('packets_retried', 0)} "
                f"retried; slowest walk {_n(p.get('slowest_walk_s'))}s; "
                f"{p.get('refused_targets', 0)} targets refused (a failure under "
                f"{p.get('refused_under_s', REFUSED_UNDER_S)}s){own}")
    if what == "host:memory":
        return (f"{ref} ({p['instance']}): available {_n(p['min'])}/{_n(p['avg'])}/"
                f"{_n(p['max'])}% low {_clock(p.get('low_at'))}")
    unit = "%" if what == "host:cpu" else ""
    name = "busy" if what == "host:cpu" else "load1"
    usual = f", usual {_n(p.get('usual'))}{unit}" if p.get("usual") is not None else (
        f", usual not read ({p['usual_why']})" if p.get("usual_why") else "")
    cpus = f" on {p['cpus']} CPUs" if p.get("cpus") else ""
    return (f"{ref} ({p['instance']}): {name} {_n(p['min'])}/{_n(p['avg'])}/{_n(p['max'])}{unit} "
            f"peak {_clock(p.get('peak_at'))}{usual}{cpus}")


def lines(pieces: list) -> list:
    return [line(p) for p in pieces]


def at_once(p: dict) -> int:
    """How many of a job piece's targets failed together: its most failing at once (the minute
    figures), else, when those were not read, how many of its targets failed at all. One count
    for the grader (`cases._across`, C2111) and Explain's fact sheet (`fact_sheet.observer_line`)."""
    return int(p.get("most_failing", p.get("targets_failed")) or 0)
