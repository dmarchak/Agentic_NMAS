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


def start(list_name: str, label: str, actor: str, work, *, kind: str = "capture preview",
          announce_keys: tuple = ANNOUNCE_KEYS, announcer: str = ANNOUNCER,
          device: str = "", card: str = "") -> str:
    """Run ``work(job_id) -> payload`` on its own thread and return the id at
    once. *payload* is the response as the page reads it (masked by the
    caller). A raising *work* is the job's `failed` state with its reason.

    *kind*, *announce_keys* and *announcer* let another operation run as a job
    (the rotate screen's apply, 7.3): one registry, each job announcing its
    own keys, each announcer declared in `invalidation.ANNOUNCERS`.

    *device* and *card* (C537): a job one device's page started, and the card that draws it
    there (`rotate`, `deploy`, `restore`, `reload`), so the device's page reopens that card
    while it runs and its result until each person has opened it (`for_device`), and the top
    bar's In progress chip lists it (`card_jobs`)."""
    from modules import identity, op_progress

    # The identity THIS request's gate verified, carried into the job's thread, so a commit
    # the work makes as that person reads `Actor-Verified: access` as it would inside the
    # request (C686: Save All's commits read "none" because only some jobs carried it). Every
    # job, never each caller: None outside a gated request, which carries nothing.
    ident = identity.verified_identity()
    job_id = uuid.uuid4().hex
    now = time.time()
    with _lock:
        _purge(now)
        _jobs[job_id] = {"job": job_id, "list": list_name, "state": "running",
                         "kind": kind, "keys": tuple(announce_keys), "announcer": announcer,
                         "started_at": now, "finished_at": None, "payload": None,
                         "error": "", "announced": None, "thread": None,
                         "device": device, "card": card, "actor": actor, "opened": set()}
    op_progress.start(job_id, kind, label, actor=actor, counts="")
    _announce_moved()

    def run():
        state, payload, error = "done", None, ""
        try:
            with identity.carried(ident):
                payload = work(job_id)
        except Exception as exc:                  # noqa: BLE001
            log.exception("%s %s failed", kind, job_id)
            state, error = "failed", f"{type(exc).__name__}: {exc}"
        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update(state=state, payload=payload, error=error,
                           finished_at=time.time())
        op_progress.finish(job_id, state)
        _announce(job_id, state == "done")
        _announce_moved()

    t = threading.Thread(target=run, name=f"{announcer}-{job_id[:8]}", daemon=True)
    with _lock:
        _jobs[job_id]["thread"] = t
    t.start()
    return job_id


def _announce(job_id: str, ok: bool) -> None:
    """Tell open pages the job finished. A failed announcement is recorded on
    the job and logged, never raised: the reads happened, and the page can
    still ask by id (it offers "Check now" while it waits)."""
    from modules import invalidation

    with _lock:
        job = _jobs.get(job_id) or {}
        keys, by = job.get("keys", ANNOUNCE_KEYS), job.get("announcer", ANNOUNCER)
    try:
        invalidation.announce(keys, by=by, ok=ok)
        heard = True
    except Exception as exc:                      # noqa: BLE001
        log.warning("job %s (%s) finished and was not announced: %s; an open page "
                    "shows it when asked (Check now)", job_id, by, exc)
        heard = False
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job["announced"] = heard


#: Announced when a job starts or finishes (C537): the top bar's In progress chip reads again.
MOVED_KEYS = ("in_progress",)
MOVED_ANNOUNCER = "in-progress"


def _announce_moved() -> None:
    """Tell open pages a job started or finished (`in_progress`), so the In progress chip
    reads again. Never raised: with no emitter (a script, a test) there is nobody to tell."""
    try:
        from modules import invalidation
        invalidation.announce(MOVED_KEYS, by=MOVED_ANNOUNCER, ok=True)
    except RuntimeError:
        pass
    except Exception as exc:                      # noqa: BLE001
        log.warning("a job's start or end was not announced to the In progress chip: %s", exc)


def card_jobs(now: float = None) -> list:
    """Every job a device's page started that is still kept (running, or finished inside
    `KEEP_S`), newest first: ``{"job", "list", "device", "card", "kind", "state", "actor",
    "started_at", "finished_at", "opened"}``. A READ of this process's registry."""
    now = time.time() if now is None else now
    with _lock:
        _purge(now)
        rows = [{"job": k, "list": v["list"], "device": v.get("device", ""),
                 "card": v.get("card", ""), "kind": v["kind"], "state": v["state"],
                 "actor": v.get("actor", ""), "started_at": v["started_at"],
                 "finished_at": v["finished_at"], "opened": set(v.get("opened") or ())}
                for k, v in _jobs.items() if v.get("card") and v.get("device")]
    return sorted(rows, key=lambda r: r["started_at"], reverse=True)


def for_device(list_name: str, device: str, card: str = "", now: float = None):
    """The newest kept job *device*'s page started in *list_name* (of *card* when named), or
    None."""
    return next((r for r in card_jobs(now) if r["list"] == list_name and r["device"] == device
                 and (not card or r["card"] == card)), None)


def mark_opened(job_id: str, viewer: str) -> bool:
    """*viewer* has seen *job_id*'s result, so the chip stops listing it for them. Kept in
    memory beside the job it marks, so it lasts exactly as long as the result it is about.
    When it is news, every open page's chip reads again (`in_progress`): this person's other
    tabs drop the row too. True when it was news."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job.get("finished_at") is None or viewer in job["opened"]:
            return False
        job["opened"].add(viewer)
    _announce_moved()
    return True


def get(job_id: str):
    """The job as the page reads it, or None when this server has no record
    of it (never started here, expired, or the server restarted)."""
    now = time.time()
    with _lock:
        _purge(now)
        job = _jobs.get(job_id)
        job = ({k: v for k, v in job.items()
                if k not in ("thread", "keys", "announcer", "opened")}
               if job else None)
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
