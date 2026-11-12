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

**One run per burst** (the operator's overnight item 9, 2026-11-12: "A fix made through Mercury
re-runs the check that raised its row"): an operation announces many times as it goes (a heal's
steps, a deploy's devices), and each announcement woke every reader its keys name, so an hourly
NetBox read could run several times for one fix. A wake now marks the reader, and the reader
runs once `DEBOUNCE_S` after the first mark of its burst, through `reader_job.request_run` (its
own run path, recorded `after_operation` with every operation of the burst named), the same
debounce Needs attention's store gives the sources it recomputes. A mark after the run has
started opens the next burst, so the answer stored last is still read after the last write.

A wake runs only where the readers run (`reader_job.running`): the app starts them; a CLI, a
test or another process asks nothing, as `/jobs/finished` does.
"""

import functools
import logging
import threading

log = logging.getLogger(__name__)

#: reader -> the invalidation keys of the operations that change its answer, each because it
#: reads a store those operations write (its `endpoints` name the store).
WOKEN_BY = {
    # committed host_vars at HEAD: an intent commit moves the adjacencies intent implies; a
    # settings change can move the Prometheus it reads.
    "adjacencies": ("intent", "settings"),
    # Loki's syslog and the inventory it attributes lines by: a list's devices change with the
    # inventory; Loki by settings.
    "adjacency-log": ("inventory", "settings"),
    # the baseline tags, and the goldens and intent at each, against the credentials held now:
    # a baseline taken, a golden or intent commit, a credential changed or rotated.
    "baseline-usability": ("baselines", "goldens", "intent", "credentials", "rotation"),
    # C1693: each network's committed host_vars at HEAD, judged for the round trip: an intent
    # commit (Normalise's, or any edit, which saves in Mercury's own formatting) clears a row.
    "intent-format": ("intent",),
    # the rotation record and the credential store's metadata; NetBox, Proxmox and TLS by
    # settings.
    "credential-health": ("credentials", "rotation", "settings"),
    # the band acknowledgements it re-reads each series for (C433, C533); Grafana by settings.
    "grafana-alerts": ("acknowledgements", "settings"),
    # each network's committed goldens (its management path) and inventory; Prometheus by
    # settings.
    "drained": ("goldens", "inventory", "settings"),
    "grafana-dashboards": ("settings",),
    "coverage-reporting": ("settings",),
    "platform-facts": ("settings",),
    # each integration's health endpoint, by settings.
    "integrations": ("settings",),
    # each network's SDN controller connections (the `sdn_controllers` settings group): a
    # connection saved or removed (`settings`) is read at once, not at the next 30 s. Never
    # woken by `sdn`, the key this reader announces itself, which would wake it in a loop.
    "sdn-controllers": ("settings",),
    # Mercury's stores: the rotation record, the save records a persist and a deploy's save
    # write, the break-glass export log, its intact checks and drills, the credentials held.
    "job-health": ("rotation", "credentials", "device_state", "breakglass"),
    # each lab startup file against the committed goldens.
    # NetBox's config contexts and the record of what Mercury modified there.
    "netbox-secrets": ("netbox", "settings"),
    # C1344: each device's committed golden against what NetBox holds of it, and the Topology
    # reader's stored LLDP: an import, an adoption or an onboarding's Verify writes NetBox
    # (`netbox`), a deploy or a save commits a golden (`goldens`), a device joins or leaves
    # (`inventory`), NetBox and the excluded VRFs by settings.
    "netbox-lag": ("netbox", "goldens", "inventory", "settings"),
    # the planned-restart windows a person declares; Prometheus by settings.
    "restarts": ("restarts", "settings"),
    # C906: the planned windows that expect new host keys; TIME closes a window, but a window
    # recorded with a start in the past (a correction) may be closed the moment it is declared.
    "host-key-windows": ("restarts",),
    # each network's receipts file and the records database's table: a deploy or restore
    # writes a receipt (v2 announces deploy_job; today's routes declare device_state); a move
    # or move back switches the store (a settings write). A capture writes none.
    "records-check": ("deploy_job", "device_state", "settings"),
    # P.11's graph: committed host_vars at HEAD for the routing layers' intended adjacencies, the
    # inventory for its nodes; Prometheus by settings; a network's expected islands (Topology's
    # declare and withdraw invalidate `topology`).
    "topology-graph": ("intent", "inventory", "settings", "topology"),
    # C662: RIP and RIPng as the devices answer, for the devices whose committed host_vars
    # configure them (intent), their inventory rows and stored credentials; a deploy changes
    # what a device runs.
    "rip": ("intent", "inventory", "credentials", "deploy_job"),
    # The fleet's syslog per day from each network's Loki; a network's Logs retention and Loki
    # by settings. Nothing Mercury does writes Loki's lines.
    "logs-summary": ("settings",),
    # The network's Kea, by settings. Board A also reads again after every reservation change:
    # the key joins this row with the operation that sends it (C529 step 2).
    "dhcp": ("settings", "dhcp"),
    # A reservation or a subnet change can make a discovered device a picked one.
    "ztp-discovery": ("settings", "dhcp"),
    # Create, Verify and Abandon add or end a pending onboarding; a reservation moves a ZTP
    # device's stage (C1193).
    "onboarding-progress": ("pending", "settings", "dhcp"),
    # C1772: who is where, from each device's MAC table and ARP (inventory, credentials), the
    # trunks that locate nothing (intent), a deploy changing a port, and the leases that name
    # each host (dhcp).
    "endpoints": ("intent", "inventory", "credentials", "deploy_job", "dhcp"),
    # HEAD against the remote: also re-read by its own post-commit hook.
    "remote-publication": ("goldens", "intent", "templates", "remote"),
}

#: reader -> why no operation of Mercury's changes its answer.
NOT_WOKEN = {
    "app-pushed": "the application repository's origin: changed by a push to GitHub, read again "
                  "when an update's host job finishes (routes/update.py)",
    "ci-verdict": "GitHub Actions: changed by CI, never by an operation here",
    "scheduled-jobs": "GitHub Actions' scheduled runs: changed by GitHub's schedule, never by an "
                      "operation here",
    "ci-agreement": "GitHub Actions' push runs and the local CI runner's store: changed by the "
                    "two runners, never by an operation here",
    "reachability": "whether each device answers ICMP and SSH: read every 5 s, and no operation's "
                    "write changes it",
    "logs-tail": "the network's log store's last 15 minutes and each device's buffer: devices "
                 "write it, never an operation here; read every 5 s",
    "loki-labels": "the log store's labels and bounds: the log shipper and Loki's configuration "
                   "change them, never an operation here",
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


def debounce_s() -> float:
    """How long after the first wake of a burst its reader runs: Needs attention's own
    debounce (`attention_store.DEBOUNCE_S`, about 2 s: a heal's steps announce within a second
    of each other), so a fix's row is read again and recomputed on the same burst."""
    from modules import attention_store
    return float(attention_store.DEBOUNCE_S)


#: reader name -> the operations whose wakes this burst holds, in order (`wake`, `_fire`).
_BURSTS: dict = {}
_BURSTS_MU = threading.Lock()


def _timer(seconds: float, fn) -> None:
    t = threading.Timer(seconds, fn)
    t.daemon = True
    t.name = "reader-wake"
    t.start()


#: How a burst's end is scheduled: ``(seconds, fn)``. A daemon timer; a test replaces it.
_schedule = _timer


def _by_words(ops: list) -> str:
    """The operations of one burst, for the run's recorded cause (`trigger_words`)."""
    if len(ops) <= 3:
        return " and ".join(ops) if len(ops) <= 2 else f"{ops[0]}, {ops[1]} and {ops[2]}"
    return f"{ops[0]}, {ops[1]} and {len(ops) - 2} more"


def _fire(name: str) -> bool:
    """The end of *name*'s burst: run it once, through its own run path; True when asked."""
    from modules import reader_job

    with _BURSTS_MU:
        ops = _BURSTS.pop(name, None)
    if not ops:
        return False
    by = _by_words(ops)
    try:
        reader = _reader(name)
        if reader is None:
            return False
        got = reader_job.request_run(reader, by, kind="after_operation",
                                     announce=reader_job.announce_via_page)
        if not got.get("started"):
            _after(reader, by)
    except Exception as exc:                              # noqa: BLE001
        log.warning("reader wake: %s after %s did not start (%s); its schedule holds",
                    name, by, exc)
        return False
    log.info("reader wake: %s re-read after %s", name, by)
    return True


def pending() -> dict:
    """The bursts not yet run: ``{reader: [operations]}`` (a copy)."""
    with _BURSTS_MU:
        return {k: list(v) for k, v in _BURSTS.items()}


def wake(keys, by: str) -> list:
    """Mark each reader *keys* wake that runs in this process, ``[names]`` marked: each runs
    once, `debounce_s` after the first mark of its burst. Never raises: a wake that cannot be
    marked is logged, and the reader's own schedule still holds."""
    from modules import reader_job

    woke, first = [], []
    for name in readers_for(keys):
        try:
            reader = _reader(name)
            if reader is None or not reader_job.running(name):
                continue
        except Exception as exc:                          # noqa: BLE001
            log.warning("reader wake: %s after %s was not marked (%s); its schedule holds",
                        name, by, exc)
            continue
        with _BURSTS_MU:
            ops = _BURSTS.get(name)
            if ops is None:
                _BURSTS[name] = [by]
                first.append(name)
            elif by not in ops:
                ops.append(by)
        woke.append(name)
    for name in first:
        try:
            _schedule(debounce_s(), functools.partial(_fire, name))
        except Exception as exc:                          # noqa: BLE001
            log.warning("reader wake: %s's run after %s could not be scheduled (%s); it runs "
                        "now", name, by, exc)
            _fire(name)
    return woke
