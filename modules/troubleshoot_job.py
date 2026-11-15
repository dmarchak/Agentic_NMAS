"""AI troubleshooting's investigation as a JOB (the operator, 2026-11-14: "AI start returns at once,
runs as a job, pushes progress"): Start AI troubleshooting, Modify and Ask the AI again, and R1's
automatic start, each run one investigation in the background, so no request waits on the model
(Cloudflare's tunnel cuts a request at about 100 s with a 524).

**One path** (`start`): the caller has taken the incident's start line under the record's lock
(`fixit.incident.claim_start`), so a second press, or a second worker, never starts a second
paid call; this starts the job carrying the investigation (`capture_job.start`: the verified
identity carried into its thread, listed under In progress with the incident's page as its
link) and returns its id at once. The card's running state is the start line's (the section's
``investigating``, drawn the same after a reload or in another worker); the job's end is
announced through the invalidation path (`ANNOUNCER`, its keys), so the open page re-fetches
the card; nothing polls. A job that fails keeps its failure as the start's own ``failed`` line
(`record_failure`), drawn in place: "Couldn't troubleshoot: <why>", never silent.

The work is the caller's: a person's press runs AI troubleshooting's own investigation in the
press's request context (its trigger the person's, `routes/fixit_v2.py`), and R1's automatic
start its background job (`heal_notice.fixit_investigation`, its trigger ``fixit_auto``'s).
Nothing here calls a model, holds a device or sends to one.
"""

import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

#: The job's kind, its announcer (`invalidation.ANNOUNCERS`) and what its end announces: the AI
#: calls it made and the incident's troubleshooting record (``drift``, the incident pages' key),
#: and In progress.
KIND = "AI troubleshooting"
ANNOUNCER = "fixit-investigation"
ANNOUNCE_KEYS = ("ai_calls", "drift", "in_progress")
#: Where a failure's words stop when kept.
WORDS_CHARS = 400


def page_of(network: str, incident_id: str) -> str:
    """The incident's page, where In progress reopens the job."""
    return f"/v2/incident/{incident_id}?list={quote(network)}"


def start(network: str, incident_id: str, actor: str, work, *, label: str = "",
          actor_kind: str = "") -> str:
    """Start *work* (``work(job_id) -> payload``) as the investigation's job for *incident_id*
    on *network*, as *actor*: its id, at once (`capture_job.start`). R1's automatic start
    passes *actor_kind* ``policy``, so the job is drawn as Mercury's own, never "by" anyone
    (C3161)."""
    from modules.nsot import capture_job

    job = capture_job.start(network, label or f"AI troubleshooting {incident_id}", actor,
                            work, kind=KIND, announce_keys=ANNOUNCE_KEYS,
                            announcer=ANNOUNCER, page=page_of(network, incident_id),
                            actor_kind=actor_kind)
    _announce_start()
    return job


#: What an investigation's start announces (Gate 2, the operator, 2026-11-15: Incidents' rows
#: and Needs attention's say "AI investigating" while it runs, live): the incident pages' key,
#: so they read the start line its caller has already taken. Its end is the job's own.
START_KEYS = ("drift",)


def _announce_start() -> None:
    """Tell open pages an investigation started. Never raised: with no emitter (a script, a
    test) there is nobody to tell; any other failure is logged, and the next announcement or
    page load draws it."""
    from modules import invalidation

    try:
        invalidation.announce(START_KEYS, by=ANNOUNCER, ok=True)
    except RuntimeError:
        pass
    except Exception as exc:                          # noqa: BLE001
        log.warning("an AI investigation's start was not announced: %s", exc)


def record_failure(incident, key: str, words: str, *, trigger: str, by: str = "",
                   verified: str = "") -> None:
    """Keep an investigation's failure as its start's ``failed`` line (``<key>:failed``), so the
    card draws "Couldn't troubleshoot: <why>" in place, in every worker. Logged, never raised: a
    record that cannot be written leaves the job's own failure under In progress."""
    from modules.fixit import incident as F

    try:
        F.claim_start(incident, f"{key}:failed", trigger=trigger, state="failed",
                      words=str(words or "it gave no reason")[:WORDS_CHARS], by=by,
                      verified=verified)
    except (F.Refused, OSError, ValueError) as exc:
        log.error("fixit job: %s's failure was not kept: %s", incident.id, exc)


def done_words(job_id: str):
    """The finished job's own words (its payload's), or None while it runs: a press whose job
    ended before its answer was drawn says what it found."""
    from modules.nsot import capture_job

    job = capture_job.get(job_id) or {}
    if job.get("state") == "done":
        return (job.get("payload") or {}).get("words") or ""
    if job.get("state") == "failed":
        return f"Couldn't troubleshoot: {job.get('error') or 'the job failed'}"
    return None
