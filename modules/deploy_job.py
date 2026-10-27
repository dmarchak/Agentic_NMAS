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
today's `/deploy/apply` declared them until 7.8 (2026-10-17).

**The person behind it.** The confirm's verified identity is carried into the
thread (`identity.carried`), so the golden commit reads `Actor-Verified:
access` and the receipts name the person, as a request's confirm does.

In memory: a restart loses the job, and its page says so; the receipts and
the golden history are the record.
"""

import logging
import threading
import time

from modules.nsot.receipts import SCOPES

log = logging.getLogger(__name__)

KIND = SCOPES["profile"][0]
#: What the in-flight panel calls the job, by its scope (C364: an IP SLA send and, since the
#: device page's deploy runs here too, a whole-intent deploy were both "monitoring profile
#: apply"). The receipt's noun and the hold's operation are the same words.
KINDS = {**{scope: words[0] for scope, words in SCOPES.items()}, "": "deploy"}
ANNOUNCER = "deploy-job"
#: Announced as each device finishes: the page's progress moved.
PROGRESS_KEYS = ("deploy_job",)
#: Announced at the end: what a deploy changes (today's `/deploy/apply` declared these).
DONE_KEYS = ("deploy_job", "device_state", "baselines", "drift", "rolled_back",
             "goldens", "remote")

_progress: dict = {}
_lock = threading.Lock()


def start(list_name: str, order: list, confirmations: dict, command_hashes: dict, *,
          authorise: dict, remove: dict, scope: str, actor: str, actor_kind: str,
          ident, declare: dict = None, card: str = "", pair: dict = None) -> str:
    """Start the batch, in *order*, and return the job's id at once. *declare*: each device's
    declared effects (C506 phase 3), checked again at apply and folded into its hash. *card*:
    the one device's page card that started it (C537: that page reopens it). *pair*: the two
    devices are both ends of this link, deployed as one change (C1908, C1909;
    `modules.nsot.paired_deploy`)."""
    from modules import identity
    from modules.nsot import capture_job

    order = [d for d in order if d in confirmations]
    label = f"{len(order)} device(s): " + ", ".join(order)
    if pair:
        from modules.nsot.paired_deploy import link_words
        label = f"both ends of the link {link_words(pair)}"

    def work(job_id):
        from modules.outbound import mask_payload
        from routes.deploy import apply_batch

        with _lock:
            _progress[job_id] = {"order": list(order), "done": {}, "current": "",
                                 "started": {}, "scope": scope}

        def on_device(event, name, result):
            with _lock:
                p = _progress.get(job_id)
                if p is None:
                    return
                if event == "start":
                    p["current"], p["started"][name] = name, time.time()
                else:
                    p["current"] = ""
                    checks = (result or {}).get("checks") or {}
                    p["done"][name] = {"outcome": (result or {}).get("outcome", ""),
                                       "stage": (result or {}).get("stage", ""),
                                       "reason": (result or {}).get("reason", ""),
                                       # Sent, and its verify did not pass (C394).
                                       "partial": bool(checks.get("ran") and not checks.get("ok")),
                                       "took_s": round(time.time() - p["started"].get(
                                           name, time.time()), 1),
                                       # Its steps' trail, kept while the batch still holds
                                       # it, so its finished row keeps each step's time (the
                                       # one stepper, 2026-10-12).
                                       "trail": _trail(list_name, name), "at": time.time()}
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
                                 on_device=on_device, declare=declare,
                                 **({"pair": pair} if pair else {}))
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
        # Coverage's combined deploy: each deployed device's sent templates are watched for
        # their first data, from now, never blocking (modules/arrival_watch.py).
        if report.get("templates_sent") is not None:
            from modules import arrival_watch
            deployed = {r.get("device") for r in report.get("results") or []
                        if r.get("outcome") == "deployed"}
            arrival_watch.start(job_id, {d: cols for d, cols in report["templates_sent"].items()
                                         if d in deployed and cols})
        return mask_payload({"ok": True, "list": list_name, **report})

    kind = KINDS.get(scope, KIND)
    one = order[0] if card and len(order) == 1 else ""
    job = capture_job.start(list_name, label, actor, work, kind=kind,
                            announce_keys=DONE_KEYS, announcer=ANNOUNCER,
                            device=one, card=card if one else "")
    log.info("deploy job %s: %s on %s started by %s", job, kind, label, actor)
    return job


#: What a restore changes, announced at its end (the declaration today's /golden/restore/apply
#: carried until it left at 7.8, 2026-10-17).
RESTORE_DONE_KEYS = ("deploy_job", "device_state", "intent", "baselines", "drift", "approvals",
                     "rolled_back", "goldens", "remote")


def start_restore(list_name: str, ref: str, confirmations: dict, command_hashes: dict, *,
                  authorise: dict, un_onboard: list, actor: str, actor_kind: str,
                  ident, card: str = "") -> str:
    """A restore (re-apply *ref*) run as a JOB, as the v2 device page's deploy is (board 10):
    the apply today's /golden/restore/apply ran until 7.8 (`restore.build_targets`, `routes.deploy.
    run_targets`: the program computed again and refused alone if its hash moved, the device
    held, verify, rollback, ONE commit of the golden and the intent half, the receipts), in
    the LIST the preview was drawn in (C396), as the person who confirmed. Returns the job's
    id at once."""
    from modules import identity
    from modules.nsot import capture_job

    devices = list(confirmations)
    label = f"re-apply {ref} to " + ", ".join(devices)

    def work(job_id):
        from modules.nsot.restore import build_targets
        from modules.outbound import mask_payload
        from routes.deploy import run_targets

        with identity.carried(ident):
            targets, skipped = build_targets(list_name, ref, devices,
                                             un_onboard=un_onboard, authorise=authorise)
            report = run_targets(list_name, targets,
                                 {"confirmations": confirmations,
                                  "command_hashes": command_hashes, "authorise": authorise},
                                 label=label, source_ref=ref, skipped=skipped,
                                 actor=actor, actor_kind=actor_kind)
        return mask_payload({"ok": True, "list": list_name, "ref": ref, "mode": "re-apply",
                             **report})

    one = devices[0] if card and len(devices) == 1 else ""
    job = capture_job.start(list_name, label, actor, work, kind="restore",
                            announce_keys=RESTORE_DONE_KEYS, announcer=ANNOUNCER,
                            device=one, card=card if one else "")
    log.info("deploy job %s: restore %s started by %s", job, label, actor)
    return job


def _trail(list_name: str, host: str) -> list:
    """The steps the device's pipeline noted on its hold so far (`device_ops.note`), or []."""
    from modules.nsot import device_ops
    try:
        return list(((device_ops.holder(list_name, host) or {}).get("progress") or {})
                    .get("trail") or [])
    except Exception:                                 # noqa: BLE001 (a row's times)
        return []


#: A finished device's outcome as the one stepper groups it (`run_stepper.GROUPS`).
_DONE = {"deployed": "done", "captured": "done", "unchanged": "done",
         "unattempted": "not_reached", "skipped_not_selected": "not_reached"}


def _took(done: dict) -> str:
    """A finished device's time on its row: its own turn, and apart from it the time it waited
    for that turn (C887: the wait was charged to its first step)."""
    from modules import device_actions, pipeline

    waited = device_actions.waited_for_turn(pipeline.STEPS, done.get("trail") or [])
    return f"{done.get('took_s') or 0} s" + (f", after {waited} s waiting its turn"
                                             if waited else "")


def failed_devices(st: dict) -> list:
    """The devices a FINISHED batch did not deploy, in its order (C1499: its card offers each a
    Retry): every target whose outcome is not done and not "not reached", read from the result,
    the authority once the batch ends (never the card's rows, which Find may filter)."""
    if not st or st.get("state") == "running":
        return []
    result = (st.get("payload") or {}).get("result") or {}
    return [t.get("name", "") for t in result.get("targets") or []
            if t.get("name") and _DONE.get(t.get("outcome"), "failed") == "failed"]


def run_card(st: dict, list_name: str, *, q: str = "") -> dict:
    """The batch on THE stepper (`modules.run_stepper`): a row per device in the rollout order,
    the pipeline's declared steps (`pipeline.STEPS`) with the time in each, read from its hold
    while it runs and from the trail kept when it finished; the batch's commit as the last
    row. *st* is `state()`'s."""
    from modules import device_actions, pipeline
    from modules import run_stepper as RS
    from modules.preview_confirm import OUTCOME_WORDS

    def steps_of(progress, at=None):
        return RS.from_stepper(device_actions.stepper(pipeline.STEPS, progress, now=at,
                                                      starts=True))

    rows = []
    by_name = {s["device"]: s for s in st.get("steps") or []}
    result = (st.get("payload") or {}).get("result") or {}
    if st.get("state") != "running" and result.get("targets"):
        # Ended: the result is the authority for each device's outcome and words (C394: sent,
        # its verify not passed, is never green); its steps' times come from the trail kept.
        said = {x.get("name"): x.get("words", "") for x in
                (result.get("happened") or {}).get("targets") or []}
        for t in result["targets"]:
            name = t.get("name", "")
            checks = t.get("checks") or {}
            group = _DONE.get(t.get("outcome"), "failed")
            if group == "done" and t.get("outcome") == "deployed" and checks.get("ran") \
                    and not checks.get("ok"):
                group = "partial"
            words = said.get(name) or OUTCOME_WORDS.get(t.get("outcome"), t.get("outcome", ""))
            if group == "partial":
                words += ", and its verify did not pass"
            if t.get("reason") and group != "done":
                words += f": {t['reason']}"
            kept = by_name.get(name) or {}
            # A partial here is its verify not passing (above): that step is the partial one,
            # never drawn done beside it (C1541).
            steps = (RS.finished(steps_of({"trail": kept["trail"]}, kept.get("at")),
                                 group if group in ("done", "partial") else "failed",
                                 partial_at="verify")
                     if kept.get("trail") else [])
            rows.append(RS.row(name, group, steps, detail="" if group == "done" else words,
                               elapsed_words=_took(kept) if steps else ""))
        return RS.card(rows, label=f"Applied to {len(rows)} devices", key=f"apply-{st['job']}",
                       search=("v2.profile_apply_job", {"job": st["job"]}),
                       search_target="#apply-job",
                       q=q, final={"name": "Commit", "state": "done", "detail": "",
                                   "words": "the batch's goldens and receipts are committed"})
    for s in st.get("steps") or []:
        name = s["device"]
        if s["state"] == "running":
            from modules.nsot import device_ops
            prog = (device_ops.holder(list_name, name) or {}).get("progress")
            rows.append(RS.row(name, "running", steps_of(prog),
                               elapsed_words=f"running {round(s.get('took_s') or 0)} s"))
        elif s["state"] == "done":
            group = _DONE.get(s.get("outcome"), "failed")
            if group == "done" and s.get("partial"):
                group = "partial"
            # `state()`'s words: the outcome, and while the batch runs, that its record is
            # committed when the batch ends.
            words = s.get("words") or OUTCOME_WORDS.get(s.get("outcome"), s.get("outcome", ""))
            detail = words + (f": {s['reason']}" if s.get("reason") and group == "failed" else "")
            if s.get("trail"):
                steps = RS.finished(steps_of({"trail": s["trail"]}, s.get("at")),
                                    "failed" if group == "failed" else group,
                                    partial_at="verify")
            else:
                steps = []
            rows.append(RS.row(name, group, steps, detail=detail,
                               elapsed_words=_took(s) if steps else ""))
        elif s["state"] == "pending":
            rows.append(RS.row(name, "waiting", detail="waiting its turn: one device at a time, "
                                                       "in the rollout order"))
        else:
            rows.append(RS.row(name, "not_reached",
                               detail="not reached: the batch stopped before it"))
    running = st.get("state") == "running"
    left = any(r["group"] in ("running", "waiting") for r in rows)
    final = {"name": "Commit",
             "detail": "not started" if running and left else ("running" if running else "done"),
             "state": "waiting" if running and left else ("running" if running else "done"),
             "words": ("waits for every device's turn, then one golden commit for the batch and "
                       "each device's receipt" if running and left else
                       "committing the batch's goldens and receipts now" if running else
                       "the batch's goldens and receipts are committed")}
    return RS.card(rows, label=f"Applying {len(rows)} devices", final=final, q=q,
                   search=("v2.profile_apply_job", {"job": st.get("job", "")}),
                   search_target="#apply-job",
                   key=f"apply-{st.get('job', '')}")


def _doing(list_name: str, host: str) -> str:
    """What the running device's pipeline is doing NOW, in words, from the stage it noted on
    the device's hold (a quick verify says it reads each line back; a full one, the settle
    windows): ``""`` when nothing is noted yet."""
    from modules import pipeline
    from modules.nsot import device_ops
    try:
        step = ((device_ops.holder(list_name, host) or {}).get("progress") or {}).get("step", "")
    except Exception:                                 # noqa: BLE001 (a running row's words)
        return ""
    return pipeline.stage_doing(step) if step else ""


def state(job_id: str):
    """``{"job", "state", "order", "steps", "list", "scope", "elapsed_s", "payload", "error"}``,
    or None when this server has no record of the job (``scope``: the batch's, so its card can
    offer a failed device's Retry on the same scope, C1499). Each step is a device
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
             "started": dict(p["started"]), "scope": p.get("scope", "")}
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
                          "took_s": round(now - p["started"].get(name, now), 1),
                          "doing": _doing(job.get("list", ""), name)})
        else:
            steps.append({"device": name, "state": ("pending" if job["state"] == "running"
                                                    else "not_reached")})
    return {"job": job_id, "state": job["state"], "order": p["order"], "steps": steps,
            "list": job.get("list", ""), "scope": p["scope"],
            "elapsed_s": job.get("elapsed_s"), "payload": job.get("payload"),
            "error": job.get("error", "")}
