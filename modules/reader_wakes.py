"""reader_wakes.py

An operation that resolves a Needs attention cause re-reads, AT ONCE, the reader that reports
it (C539, the operator, 2026-10-06, bucket A).

A baseline was taken and "no baseline applies" stood until the baseline reader's next 300 s
cycle, and another person seeing it could take a second baseline: the operation's own result
was current, and the row naming the cause it had just resolved waited on a schedule. So every
operation's invalidation keys, the ones a mutating route declares (`invalidation.DECLARED`) and
the ones a job announces (`invalidation.ANNOUNCERS`), now wake each reader whose answer they
change, and that reader's announcement redraws the row for every viewer.

**One table, by reader** (:data:`WOKEN_BY`): each reader of a store Mercury's operations write
names the keys of those operations; each reader of outside state only names why nothing Mercury
does changes its answer (:data:`NOT_WOKEN`). Every registered reader is in exactly one of the
two (`tests/test_reader_wakes.py`), so a new reader declares its wakes the day it is written.

**A run in progress may have read before the write.** A wake that finds one waits for it and
runs once more, so the answer stored last is read after the operation.

A wake runs only where the readers run (`reader_job.running`): the app starts them; a CLI, a
test or another process asks nothing, as `/jobs/finished` does.
"""

import logging
import threading

log = logging.getLogger(__name__)

#: reader -> the invalidation keys of the operations that change its answer, each because it
#: reads a store those operations write (its `endpoints` name the store).
WOKEN_BY = {
    # committed host_vars at HEAD: an intent commit moves the adjacencies intent implies; a
    # settings change can move the Prometheus it reads.
    "adjacencies": ("intent", "settings"),
    # the baseline tags, and the goldens and intent at each, against the credentials held now:
    # a baseline taken, a golden or intent commit, a credential changed or rotated.
    "baseline-usability": ("baselines", "goldens", "intent", "credentials", "rotation"),
    # the rotation record and the credential store's metadata; NetBox, Proxmox and TLS by
    # settings.
    "credential-health": ("credentials", "rotation", "settings"),
    # the band acknowledgements it re-reads each series for (C433, C533); Grafana by settings.
    "grafana-alerts": ("acknowledgements", "settings"),
    "grafana-dashboards": ("settings",),
    "coverage-reporting": ("settings",),
    "platform-facts": ("settings",),
    # each integration's health endpoint, by settings.
    "integrations": ("settings",),
    # Mercury's stores: the rotation record, the save records a persist and a deploy's save
    # write, the break-glass export log, its intact checks and drills, the credentials held.
    "job-health": ("rotation", "credentials", "device_state", "breakglass"),
    # each lab startup file against the committed goldens.
    "lab-startup": ("goldens", "baselines"),
    # NetBox's config contexts and the record of what Mercury modified there.
    "netbox-secrets": ("netbox", "settings"),
    # the planned-restart windows a person declares; Prometheus by settings.
    "restarts": ("restarts", "settings"),
    # each network's receipts file and the records database's table: a deploy or restore
    # writes a receipt (v2 announces deploy_job; today's routes declare device_state); a move
    # or move back switches the store (a settings write). A capture writes none.
    "records-check": ("deploy_job", "device_state", "settings"),
    # HEAD against the remote: also re-read by its own post-commit hook.
    "remote-publication": ("goldens", "intent", "templates", "remote"),
}

#: reader -> why no operation of Mercury's changes its answer.
NOT_WOKEN = {
    "app-pushed": "the application repository's origin: changed by a push to GitHub, read again "
                  "when an update's host job finishes (routes/update.py)",
    "ci-verdict": "GitHub Actions: changed by CI, never by an operation here",
    "reachability": "whether each device answers ICMP and SSH: read every 5 s, and no operation's "
                    "write changes it",
}


def _reader(name: str):
    from modules import reader_job
    return next((r for r in reader_job.readers() if r.name == name), None)


def readers_for(keys) -> list:
    """The readers *keys* wake, sorted."""
    keys = set(keys or ())
    return sorted(name for name, woken in WOKEN_BY.items() if keys & set(woken))


#: How long a wake waits for a run in progress before running anyway: 2.5x the slowest reader's
#: measured run (baseline-usability, 8 to 9 s for twelve tags, 2026-09-28) rounded up to a
#: minute, beyond which the run it waits on is the reader's own problem, and its row says so.
AFTER_BOUND_S = 60


def _after(reader, by: str, sleep=None, clock=None, spawn=None) -> None:
    """Wait for the run in progress (`request_in_flight`), then run once more: it may have read
    before the write. A scheduled run needs no wait: `run_once` takes the reader's lock, so a
    request queued behind it reads after it."""
    import time

    from modules import reader_job
    sleep = sleep or time.sleep
    clock = clock or time.monotonic

    def go():
        deadline = clock() + AFTER_BOUND_S
        while reader_job.request_in_flight(reader.name) is not None and clock() < deadline:
            sleep(0.5)
        reader_job.request_run(reader, by, kind="after_operation",
                               announce=reader_job.announce_via_page)
    if spawn is not None:
        spawn(go)
        return
    threading.Thread(target=go, name=f"wake-after:{reader.name}", daemon=True).start()


def wake(keys, by: str) -> list:
    """Run, now, each reader *keys* wake that runs in this process; ``[names]`` woken. Never
    raises: a wake that cannot start is logged, and the reader's own schedule still holds."""
    from modules import reader_job

    woke = []
    for name in readers_for(keys):
        try:
            reader = _reader(name)
            if reader is None or not reader_job.running(name):
                continue
            got = reader_job.request_run(reader, by, kind="after_operation",
                                         announce=reader_job.announce_via_page)
            if not got.get("started"):
                _after(reader, by)
            woke.append(name)
        except Exception as exc:                          # noqa: BLE001
            log.warning("reader wake: %s after %s did not start (%s); its schedule holds",
                        name, by, exc)
    if woke:
        log.info("reader wake: %s re-read after %s", ", ".join(woke), by)
    return woke
