"""Loki's bounds and labels, for History › Query › Ask your own's logs builder (board F3; C3166's
slice 2, the operator's rule of 2026-11-12: no page load waits on Loki).

**Why a reader.** The builder offers only what Loki holds (modules/history_logq.py, "Discovered,
never assumed"): its label names, the job and device values over the range, when the device and
severity labels began, and Loki's own bounds from its /config. Asked per page load, that was
four to eight Loki reads before the builder could draw. This reads them in the background, once
per Loki configuration every `INTERVAL_SECONDS`, for each range the builder's chips offer (1 h,
24 h, 7 days, 30 days) and each job's devices, and the builder draws what it holds and how old.

**What is kept:** ``limits`` (`history_logq.limits`' answer), ``ranges``: for each chip, the
label names, the job and device values, the devices of each job (``device_by_job``) and when
the device and severity labels began (``since``); ``read_at``. A range the chips do not offer
(From… to…) draws the smallest held range that covers it, and says which (`history_logq`).

**Display only:** Ask's answer is the person's question, asked of Loki when Ask is pressed.
"""

import logging
import time

from modules import reader_job

log = logging.getLogger(__name__)

READER_NAME = "loki-labels"
#: Labels move when a new job or device starts logging: five minutes behind is a choice offered
#: five minutes late, never a wrong one (the answer reads Loki itself). The lab's Loki answers a
#: label read in about 5 ms (its frontend's mean, measured 2026-11-12), so a run of about 19
#: reads costs well under a second.
INTERVAL_SECONDS = 300
KEEPALIVE_SECONDS = 1800
#: The most jobs whose devices are read each run (the lab's Loki holds one syslog job).
MAX_JOBS = 20


def _client(list_name: str):
    from modules import history_logq
    return history_logq._client(list_name, 15.0)       # noqa: SLF001 (the builder's client)


def read(list_name: str = "", client=None, clock=time.time) -> dict:
    """One configuration's bounds and labels (see the module). A Loki that refuses a label read
    fails the read: the last good value is kept and the builder says the refresh failed."""
    from modules import history_logq as Q

    list_name = list_name or _default()
    client = client or _client(list_name)
    if not client.is_configured():
        return {"configured": False}
    now = clock()
    lim = Q.limits(list_name, client=client, now=now)
    ranges = {}
    for key, (_words, seconds) in Q.RANGES.items():
        start = now - seconds
        disc = Q.discover(list_name, start, now, client=client, now=now)
        if disc["state"] != "ok":
            raise RuntimeError(disc.get("error") or f"Loki's labels could not be read ({key})")
        by_job = {}
        if "device" in disc["labels"]:
            window = {"start": str(int(start * 1e9)), "end": str(int(now * 1e9))}
            for job in disc["values"]["job"][:MAX_JOBS]:
                vals, err = Q._json(client, "loki/api/v1/label/device/values",  # noqa: SLF001
                                    query="{" + Q._matcher("job", [job]) + "}", **window)
                if err:
                    raise RuntimeError(err)
                by_job[job] = sorted(v for v in vals or [] if isinstance(v, str))
        ranges[key] = {"labels": disc["labels"], "values": disc["values"],
                       "since": disc["since"], "device_by_job": by_job}
    return {"configured": True, "limits": lim, "ranges": ranges,
            "read_at": Q._iso(now), "read_at_ts": now}                    # noqa: SLF001


def changed(previous, value) -> bool:
    """Announce when a bound or a label moved, never for the read's own time."""
    strip = lambda v: {k: x for k, x in (v or {}).items()              # noqa: E731
                       if k not in ("read_at", "read_at_ts")}
    lim = lambda v: {k: x for k, x in ((v or {}).get("limits") or {}).items()  # noqa: E731
                     if k != "read_at"}
    return (strip(previous) | {"limits": lim(previous)}) != (strip(value) | {"limits": lim(value)})


def _default() -> str:
    from modules.list_settings import DEFAULT_LIST
    return DEFAULT_LIST


READER = reader_job.register(reader_job.Reader(
    name=READER_NAME,
    what="Loki's bounds and labels for each range the logs builder offers (C3166)",
    endpoints=("Loki: GET /config (its limits)",
               "Loki: GET /loki/api/v1/labels and /label/<job|device>/values, for each of the "
               "builder's four ranges and each job's devices",
               "Loki: GET /loki/api/v1/query_range (one line each: when the device and "
               "severity labels began, asked at most hourly)"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("labels move when a new job or device starts logging; five minutes late is "
                    "a choice offered late, never a wrong answer (Ask reads Loki itself)"),
    read=read,
    invalidates=("logs",),
    remedy="Read the error above: it names what Loki answered",
    window="each of the builder's ranges (1 h, 24 h, 7 days, 30 days) before each read",
    per_group=("loki",),
    read_for=lambda list_name: read(list_name=list_name),
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
