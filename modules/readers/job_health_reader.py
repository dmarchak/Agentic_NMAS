"""Job health as a reader job: the first instance of modules/reader_job.py.

**Measured on the host 2026-09-28 (the operator):** one job-health read took
9,797 ms, and every other Needs attention source together under 60 ms. Job
health was 99.4% of the landing view's cost, because the page asked systemd,
the journal and Proxmox on every load: the scale rule (section 0a) broken
by the page built to surface problems. So it is read here, on a schedule,
and the page reads what was stored (rule 1).

**Its own liveness is NOT in its value.** The stored rows exclude every
``reader:*`` row, and Needs attention judges the readers' liveness from their
stores at the time of the request (a file read each). Otherwise a stopped
job-health reader would freeze a cache whose own row says ``ok`` for ever:
the one row that must be live, read from the thing that stopped.

`/jobs/health` stays a LIVE read: it is the ask-now diagnostic, and says so.
"""

from modules import reader_job

INTERVAL_SECONDS = 300


def read() -> dict:
    """Every job-health row except the readers' own (above)."""
    from modules import job_health
    return {"health": job_health.health(readers=[])}


READER = reader_job.register(reader_job.Reader(
    name="job-health",
    what="job health: the timers, services and stores the host checks, read for Needs attention",
    endpoints=("systemctl show", "journalctl", "the Proxmox API", "the NMAS data stores"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("one read costs 9.8 s on the host (measured 2026-09-28); its timers move "
                    "hourly or daily, and the two rows that move in minutes are drawn live "
                    "elsewhere (SSH sessions on the in-flight panel, the running commit on "
                    "/health)"),
    read=read,
    invalidates=("job_health",),
    remedy="Read the error above: it names what the job-health read could not ask",
    window="the state at the read",
))
