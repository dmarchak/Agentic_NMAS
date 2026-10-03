"""A batch deploy run as a JOB (P.9 step d2: the v2 "Apply monitoring
profile" for the devices ticked on Monitoring > Coverage).

A batch deploys its devices one after another (the circuit breaker's order),
and each device's verify waits out its settle windows, so a batch of a few
devices passes Cloudflare's 100 s edge limit, which ends a request with no
response. So the confirm starts the batch HERE and answers at once, as the
capture preview and rotate do (`capture_job`, one registry); the page follows
it by id.

**What the page sees, in the rollout order.** Each device's start and finish
is recorded (`progress`) and ANNOUNCED (`deploy_job`), so the page redraws
where the batch is: done (with its outcome), running, or not reached, never a
spinner. At the end the job announces every key a deploy changes, as
`/deploy/apply` declares them.

**The person behind it.** The confirm's verified identity is carried into the
thread (`identity.carried`), so the golden commit reads `Actor-Verified:
access` and the receipts name the person, as at `/deploy/apply`.

In memory: a restart loses the job, and its page says so; the receipts and
the golden history are the record.
"""

import logging
import threading
import time

log = logging.getLogger(__name__)

KIND = "monitoring profile apply"
#: What the in-flight panel calls the job, by its scope (C364: an IP SLA send and, since the
#: device page's deploy runs here too, a whole-intent deploy were both "monitoring profile
#: apply").
KINDS = {"profile": KIND, "ip_sla": "IP SLA send", "": "deploy"}
ANNOUNCER = "deploy-job"
#: Announced as each device finishes: the page's progress moved.
PROGRESS_KEYS = ("deploy_job",)
#: Announced at the end: what a deploy changes (`/deploy/apply`'s declaration).
DONE_KEYS = ("deploy_job", "device_state", "baselines", "drift", "rolled_back", "freshness",
             "goldens", "remote")

_progress: dict = {}
_lock = threading.Lock()


def start(list_name: str, order: list, confirmations: dict, command_hashes: dict, *,
          authorise: dict, remove: dict, scope: str, actor: str, actor_kind: str,
          ident) -> str:
    """Start the batch, in *order*, and return the job's id at once."""
    from modules import identity
    from modules.nsot import capture_job

    order = [d for d in order if d in confirmations]
    label = f"{len(order)} device(s): " + ", ".join(order)

    def work(job_id):
        from modules.outbound import mask_payload
        from routes.deploy import apply_batch

        with _lock:
            _progress[job_id] = {"order": list(order), "done": {}, "current": "",
                                 "started": {}}

        def on_device(event, name, result):
            with _lock:
                p = _progress.get(job_id)
                if p is None:
                    return
                if event == "start":
                    p["current"], p["started"][name] = name, time.time()
                else:
                    p["current"] = ""
                    p["done"][name] = {"outcome": (result or {}).get("outcome", ""),
                                       "stage": (result or {}).get("stage", ""),
                                       "reason": (result or {}).get("reason", ""),
                                       "took_s": round(time.time() - p["started"].get(
                                           name, time.time()), 1)}
            try:
                from modules import invalidation
                invalidation.announce(PROGRESS_KEYS, by=ANNOUNCER)
            except Exception as exc:              # noqa: BLE001
                log.info("deploy job %s: progress not announced (%s); the page asks "
                         "when Check now is pressed", job_id, exc)

        with identity.carried(ident):
            report = apply_batch(list_name, {d: confirmations[d] for d in order},
                                 command_hashes, authorise=authorise, remove=remove,
                                 scope=scope, actor=actor, actor_kind=actor_kind,
                                 on_device=on_device)
        # A device refused at apply (its program moved) or skipped as drifted
        # never reaches the batch's own loop, so no event names it: it is
        # recorded from the report, or its row would read "not reached", the
        # circuit breaker's words, for a refusal.
        with _lock:
            p = _progress.get(job_id)
            for r in (report.get("results") or []) if p is not None else []:
                name = r.get("device")
                if name in p["order"] and name not in p["done"]:
                    p["done"][name] = {"outcome": r.get("outcome", ""),
                                       "stage": r.get("stage", ""),
                                       "reason": r.get("reason", ""), "took_s": 0}
        return mask_payload({"ok": True, "list": list_name, **report})

    kind = KINDS.get(scope, KIND)
    job = capture_job.start(list_name, label, actor, work, kind=kind,
                            announce_keys=DONE_KEYS, announcer=ANNOUNCER)
    log.info("deploy job %s: %s on %s started by %s", job, kind, label, actor)
    return job


def state(job_id: str):
    """``{"job", "state", "order", "steps", "elapsed_s", "payload", "error"}``,
    or None when this server has no record of the job. Each step is a device
    in the rollout order: ``done`` (with its outcome in words), ``running``,
    ``pending`` (its turn has not come) while the batch runs, or
    ``not_reached`` once it has ended without reaching it (the breaker)."""
    from modules.nsot import capture_job
    from modules.preview_confirm import OUTCOME_WORDS

    job = capture_job.get(job_id)
    if job is None:
        return None
    with _lock:
        p = _progress.get(job_id) or {"order": [], "done": {}, "current": "", "started": {}}
        p = {"order": list(p["order"]), "done": dict(p["done"]), "current": p["current"],
             "started": dict(p["started"])}
    now = time.time()
    steps = []
    for name in p["order"]:
        if name in p["done"]:
            row = p["done"][name]
            words = OUTCOME_WORDS.get(row["outcome"], row["outcome"].replace("_", " "))
            if job["state"] == "running":
                # Its receipt row is written, commit pending, until the batch commits.
                words += "; its record is committed when the batch ends"
            steps.append({"device": name, "state": "done", **row, "words": words})
        elif name == p["current"]:
            steps.append({"device": name, "state": "running",
                          "took_s": round(now - p["started"].get(name, now), 1)})
        else:
            steps.append({"device": name, "state": ("pending" if job["state"] == "running"
                                                    else "not_reached")})
    return {"job": job_id, "state": job["state"], "order": p["order"], "steps": steps,
            "elapsed_s": job.get("elapsed_s"), "payload": job.get("payload"),
            "error": job.get("error", "")}
