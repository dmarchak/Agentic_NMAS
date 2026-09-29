"""A capture preview as a background job (register C188, step 2).

The preview read every device and answered only when the last one had: 107 s
for nine devices on the host (2026-09-29), past Cloudflare's 100 s edge limit,
which ends a request with no response (a 524 the app never sees). Step 1 made
the reads concurrent (about the slowest device's time); this makes the
request not wait on a device at all. POST starts the job and answers at once;
the reads run here; the in-flight panel shows them (`op_progress`); when they
finish the job ANNOUNCES `capture_preview` (C58) and the page reads the
result by its id.

In memory, like `op_progress` and the one-shot tokens: a restart loses a job,
and its GET says so ("unknown"), never an empty preview. A finished job is
kept for `KEEP_S`, long enough for a person to read a preview and confirm it.
Keeping it longer buys nothing: the confirm is bound to each device's capture
hash, and the apply reads every device again, so an old preview is refused
device by device, never applied.
"""

import logging
import threading
import time
import uuid

log = logging.getLogger(__name__)

KEEP_S = 1800
_MAX = 16
ANNOUNCE_KEYS = ("capture_preview",)
ANNOUNCER = "capture-preview"

_jobs: dict = {}
_lock = threading.Lock()


def _purge(now: float) -> None:
    for k in [k for k, v in _jobs.items()
              if v.get("finished_at") and now - v["finished_at"] > KEEP_S]:
        del _jobs[k]
    while len(_jobs) > _MAX:
        oldest = next((k for k, v in _jobs.items() if v.get("finished_at")), None)
        if oldest is None:
            break                      # never drop a job still running
        del _jobs[oldest]


def start(list_name: str, label: str, actor: str, work) -> str:
    """Run ``work(job_id) -> payload`` on its own thread and return the id at
    once. *payload* is the preview response as the page reads it (masked by
    the caller). A raising *work* is the job's `failed` state with its reason."""
    from modules import op_progress

    job_id = uuid.uuid4().hex
    now = time.time()
    with _lock:
        _purge(now)
        _jobs[job_id] = {"job": job_id, "list": list_name, "state": "running",
                         "started_at": now, "finished_at": None, "payload": None,
                         "error": "", "announced": None, "thread": None}
    op_progress.start(job_id, "capture preview", label, actor=actor, counts="")

    def run():
        state, payload, error = "done", None, ""
        try:
            payload = work(job_id)
        except Exception as exc:                  # noqa: BLE001
            log.exception("capture preview %s failed", job_id)
            state, error = "failed", f"{type(exc).__name__}: {exc}"
        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update(state=state, payload=payload, error=error,
                           finished_at=time.time())
        op_progress.finish(job_id, state)
        _announce(job_id, state == "done")

    t = threading.Thread(target=run, name=f"capture-preview-{job_id[:8]}", daemon=True)
    with _lock:
        _jobs[job_id]["thread"] = t
    t.start()
    return job_id


def _announce(job_id: str, ok: bool) -> None:
    """Tell open pages the job finished. A failed announcement is recorded on
    the job and logged, never raised: the reads happened, and the page can
    still ask by id (it offers "Check now" while it waits)."""
    from modules import invalidation

    try:
        invalidation.announce(ANNOUNCE_KEYS, by=ANNOUNCER, ok=ok)
        heard = True
    except Exception as exc:                      # noqa: BLE001
        log.warning("capture preview %s finished and was not announced: %s; an open page "
                    "shows it when asked (Check now)", job_id, exc)
        heard = False
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job["announced"] = heard


def get(job_id: str):
    """The job as the page reads it, or None when this server has no record
    of it (never started here, expired, or the server restarted)."""
    now = time.time()
    with _lock:
        _purge(now)
        job = _jobs.get(job_id)
        job = {k: v for k, v in job.items() if k != "thread"} if job else None
    if job is None:
        return None
    job["elapsed_s"] = round((job["finished_at"] or now) - job["started_at"], 1)
    return job


def wait(job_id: str, timeout: float) -> bool:
    """Block until the job finishes; True when it has. For a caller with
    nothing else to do (the tests, a script); the page never waits."""
    with _lock:
        job = _jobs.get(job_id)
        t = job.get("thread") if job else None
    if t is None:
        return False
    t.join(timeout)
    return not t.is_alive()
