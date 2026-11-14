"""routes/credential_profiles_v2.py — Source of truth › Credentials › Profiles on v2 (the board
drawn 2026-10-10 under the Phase 7 mode; CUTOVER's "Credential profiles").

The profiles the resolver gives a NetBox inventory's devices (platform, kind, site, default),
each with what it covers, set or not set, never a value; Add a profile…, Edit… and Delete… in
place, each
a verified person's, each recorded (modules/credential_profiles_page.py over the store's one
write path). Installation-wide, as the store is: the page names the network it was opened from
only for the top bar.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("credential_profiles_v2", __name__, url_prefix="/v2/credentials/profiles")


def _ctx(**extra) -> dict:
    from modules import credential_profiles_page as P
    from modules.nsot import scheduled_rotation as SR
    from modules.preview_confirm import confirm_part

    known = P.exists()
    return dict({"v": P.view(), "kinds": P.choices(known), "scopes": P.scope_options(known),
                 "may": confirm_part(request, "configure"),
                 "rot": SR.page_view(), "may_rotate": confirm_part(request, "confirm")},
                **extra)


def _region(code: int = 200, **extra):
    return _strict(render_template("v2/_credential_profiles.html", **_ctx(**extra)), code)


@bp.route("", methods=["GET"])
def page():
    """The Profiles tab. A read: nothing is written and no value is read out."""
    from routes.v2 import _credentials_list, _page

    from modules import credential_profiles_page as P

    return _page("v2/credentials.html", active_nav="credentials", tab="profiles",
                 list_name=_credentials_list(request), known=True, ro=P.read_view(), **_ctx(),
                 **fleet_ctx())


@bp.route("/region", methods=["GET"])
def region():
    """The tab's region alone: re-read when `credentials` is announced, and what Cancel puts
    back."""
    return _region()


@bp.route("/form", methods=["GET"])
def form():
    """Add a profile… (no ``name``) or Edit… (``name``): the form in place, nothing written."""
    from modules import credential_profiles_page as P

    name = (request.args.get("name") or "").strip()
    return _region(op={"state": "form", "name": name,
                       "covers": P.covers(name) if name else {}})


@bp.route("", methods=["POST"])
def save():
    """Save the profile as the verified person, and record it; the result in place."""
    from modules import credential_profiles_page as P
    from modules import identity

    actor = identity.request_actor()
    editing = (request.form.get("name") or "").strip()
    got = P.save(request.form.get("kind", ""), request.form.get("value", ""),
                 request.form.get("username", ""), request.form.get("password", ""),
                 request.form.get("secret", ""), actor=actor,
                 verified=identity.actor_verification(actor), editing=editing)
    if not got["ok"]:
        return _region(400, op={"state": "form", "name": editing, "refused": got["error"],
                                "kind": request.form.get("kind", ""),
                                "value": request.form.get("value", ""),
                                "username": request.form.get("username", ""),
                                "covers": P.covers(editing) if editing else {}})
    return _region(op=dict(got, state="saved", actor=actor))


@bp.route("/delete", methods=["GET"])
def delete_form():
    """Delete…: what the profile covers and where those devices' login comes from after it;
    nothing deleted."""
    from modules import credential_profiles_page as P

    name = (request.args.get("name") or "").strip()
    return _region(op={"state": "delete", "name": name, "covers": P.covers(name)})


@bp.route("/delete", methods=["POST"])
def delete():
    """Delete the profile as the verified person, and record it; the result in place."""
    from modules import credential_profiles_page as P
    from modules import identity

    actor = identity.request_actor()
    name = (request.form.get("name") or "").strip()
    got = P.delete(name, actor=actor, verified=identity.actor_verification(actor))
    if not got["ok"]:
        return _region(409, op={"state": "delete", "name": name, "covers": P.covers(name),
                                "refused": got["error"]})
    return _region(op=dict(got, state="deleted", actor=actor))


# ---------------------------------------------------------------- the read-only account (H28)

def _read_region(code: int = 200, **op):
    from modules import credential_profiles_page as P
    from modules.preview_confirm import confirm_part

    return _strict(render_template("v2/_credential_read_account.html", ro=P.read_view(),
                                   may=confirm_part(request, "configure"), op=op or None),
                   code)


@bp.route("/read-account", methods=["GET"])
def read_account_region():
    """The Read-only account card alone: re-read when `credentials` is announced, and what
    Cancel puts back. A read: no value is read out."""
    return _read_region()


@bp.route("/read-account/form", methods=["GET"])
def read_account_form():
    """Set the read-only account… (no account yet) or Replace its password… for one profile:
    the form in place, nothing written."""
    from modules import credentials

    name = (request.args.get("name") or "").strip()
    held = credentials.read_accounts().get(name) or {}
    return _read_region(state="form", name=name, username=held.get("username", ""),
                        replace=bool(held))


@bp.route("/read-account", methods=["POST"])
def read_account_save():
    """Set the profile's read-only account as the verified person, and record it; the result
    in place. The password typed is sealed in the store and never drawn again."""
    from modules import credential_profiles_page as P
    from modules import credentials, identity

    actor = identity.request_actor()
    name = (request.form.get("name") or "").strip()
    got = P.save_read(name, request.form.get("username", ""),
                      request.form.get("password", ""), actor=actor,
                      verified=identity.actor_verification(actor))
    if not got["ok"]:
        held = credentials.read_accounts().get(name) or {}
        return _read_region(400, state="form", name=name, refused=got["error"],
                            username=held.get("username") or request.form.get("username", ""),
                            replace=bool(held))
    return _read_region(**dict(got, state="saved", actor=actor))


# ------------------------------------------- the read-only account on the devices (board R)
# Board R (provisional, operator review pending; the operator, 2026-11-13): the coverage the
# read-account-coverage reader holds, Add the read-only account… through the intent editor's
# one commit path, and the rollout through the batch deploy. modules/nsot/read_account.py.

def fleet_ctx(**chosen) -> dict:
    """The On the devices region's context: the held coverage (never computed here) and its
    age, filtered by *chosen*. The page and the card's own region draw it."""
    from modules.nsot import read_account as RA

    got = RA.held()
    return {"fleet": RA.view(got["value"], **chosen) if got["value"] is not None else None,
            "held_at": got["at"], "held_why": got["why"]}


def _fleet_region(code: int = 200, **chosen):
    return _strict(render_template("v2/_read_account_coverage.html", **fleet_ctx(**chosen)),
                   code)


def _op(code: int = 200, op=None):
    """The card in place under the coverage: Add's form, preview or result, or the
    rollout's form, preview or run."""
    from modules.preview_confirm import confirm_part

    return _strict(render_template("v2/_read_account_op.html", op=op or {},
                                   may=confirm_part(request, "approve"),
                                   may_send=confirm_part(request, "confirm")), code)


def _chosen(args) -> dict:
    return {k: (args.get(k) or "").strip() for k in ("q", "network", "platform", "state")} | {
        "open_group": (args.get("open") or "").strip()}


@bp.route("/read-account/fleet", methods=["GET"])
def read_account_fleet():
    """On the devices: the held coverage, filtered and searched; re-read when the coverage
    reader announces `read_account`. A read: nothing is written, no device is asked."""
    return _fleet_region(**_chosen(request.args))


@bp.route("/read-account/close", methods=["GET"])
def read_account_close():
    """Cancel: the card's place empty again, nothing changed."""
    return _op()


@bp.route("/read-account/add", methods=["GET"])
def read_account_add_form():
    """Add the read-only account…: the devices to tick, from the held coverage; nothing
    written. ``tick`` (all-not-yet, network:<name>, platform:<words>) ticks a group."""
    from modules.nsot import read_account as RA

    tick = (request.args.get("tick") or "").strip()
    return _op(op={"state": "add_form", "c": RA.candidates(), "tick": tick})


@bp.route("/read-account/add/preview", methods=["POST"])
def read_account_add_preview():
    """The Add's preview: per ticked device the intent change and the lines a deploy will
    send, masked, and the devices refused by name. Writes nothing."""
    from modules.nsot import read_account as RA
    from modules.outbound import mask_payload

    picks = RA.picks_of(request.form.getlist("device"))
    reason = " ".join((request.form.get("reason") or "").split())
    p = mask_payload(RA.add_preview(picks))
    code = 200 if p.pop("ok") else 400        # said by the status and by `p.error`
    return _op(code, op={"state": "add_preview", "p": p, "reason": reason,
                                   "picked": [f"{n}/{d}" for n, d in picks]})


@bp.route("/read-account/add", methods=["POST"])
def read_account_add():
    """Commit the previewed Add as the verified person with their reason: refused, nothing
    written, unless the preview made again has the confirmed hash; one commit per network."""
    from modules import identity
    from modules.nsot import read_account as RA
    from modules.outbound import mask_payload

    picks = RA.picks_of(request.form.getlist("device"))
    reason = " ".join((request.form.get("reason") or "").split())
    got = RA.add_commit(picks, request.form.get("hash") or "", reason,
                        identity.request_actor())
    if not got["ok"] and not got["commits"]:
        p = mask_payload(got.get("preview") or RA.add_preview(picks))
        p.pop("ok", None)
        return _op(409, op={"state": "add_preview", "p": p, "reason": reason,
                                      "picked": [f"{n}/{d}" for n, d in picks],
                                      "refused": got["error"]})
    done = [c for c in got["commits"] if c["commit"]]
    roll = None
    if done:
        # The coverage reads again only once its reader has been woken by the commit, so the
        # devices just committed are offered with those it held as waiting already.
        net = done[0]["network"]
        roll = _rollout_form(net, sorted(set(RA.pending_of(net)) | set(done[0]["devices"])))
    return _op(op={"state": "added", "commits": got["commits"], "error": got["error"],
                   "actor": identity.request_actor(), "roll": roll})


def _rollout_form(network: str, devices=None, canary: str = "", size=None, named=()) -> dict:
    from modules.nsot import listref
    from modules.nsot import read_account as RA

    pending = RA.pending_of(network)
    chosen = [d for d in (devices if devices is not None else pending)]
    return {"network": network, "networks": listref.names(),
            "devices": chosen, "canary": canary, "size": size or RA.WAVE,
            "wave_max": RA.WAVE_MAX, "named": [d for d in named if d]}


@bp.route("/read-account/rollout", methods=["GET"])
def read_account_rollout_form():
    """Roll it out: the network, its devices whose intent names the account and whose golden
    does not hold it (the held coverage), the canary and the wave size; nothing sent."""
    from modules.nsot import listref

    network = (request.args.get("network") or "").strip() or listref.active().name
    return _op(op={"state": "roll_form", "roll": _rollout_form(network)})


def _size(form) -> int:
    from modules.nsot import read_account as RA
    try:
        return max(1, min(RA.WAVE_MAX, int(form.get("size") or RA.WAVE)))
    except ValueError:
        return RA.WAVE


@bp.route("/read-account/rollout/plan", methods=["POST"])
def read_account_rollout_plan():
    """Start the rollout's one preview as a job (every chosen device's program through the
    deploy's own plan) and answer with its card at once. Sends nothing, writes nothing."""
    from modules import identity
    from modules.nsot import read_account as RA

    network = (request.form.get("network") or "").strip()
    devices = [d for d in request.form.getlist("device") if d.strip()]
    canary = (request.form.get("canary") or "").strip()
    size = _size(request.form)
    named = request.form.getlist("management")
    roll = _rollout_form(network, devices, canary, size, named)
    if not devices:
        return _op(400, op={"state": "roll_form", "roll": roll,
                                      "refused": "no device is chosen: tick one to roll out"})
    job = RA.plan_start(network, devices, canary, size, identity.request_actor(), named)
    return _op(op={"state": "roll_planning", "job": job, "roll": roll})


@bp.route("/read-account/rollout/plan/<job>", methods=["GET"])
def read_account_rollout_planned(job):
    """The rollout's preview for its job: still planning, the plan, its refusal, or why there
    is none. Re-read when the plan job announces `fleet_change`."""
    from modules.nsot import capture_job

    got = capture_job.get(job)
    roll = _rollout_form((request.args.get("network") or "").strip(),
                         request.args.getlist("device"),
                         (request.args.get("canary") or "").strip(), _size(request.args),
                         request.args.getlist("management"))
    if got is None:
        return _op(op={"state": "roll_unknown", "job": job, "roll": roll})
    if got["state"] == "running":
        return _op(op={"state": "roll_planning", "job": job, "roll": roll})
    plan = got.get("payload") or {}
    if got["state"] == "failed" or not plan.get("ok"):
        return _op(op={"state": "roll_form", "roll": roll, "refused": (
            got.get("error") or plan.get("error") or "the plan did not finish")})
    # Drawn: every field but `ok`, which this branch is (a refused plan is the form's).
    return _op(op={"state": "roll_plan", "plan": {k: v for k, v in plan.items() if k != "ok"},
                   "roll": roll, "elapsed_s": got.get("elapsed_s")})


@bp.route("/read-account/rollout", methods=["POST"])
def read_account_rollout_confirm():
    """Confirm the rollout's hash as a verified person: one job makes the plan again, refuses
    unless its hash is the one confirmed, then deploys the canary alone through THE apply and
    pauses. Answers at once with the run's card."""
    from modules import identity
    from modules.nsot import read_account as RA

    network = (request.form.get("network") or "").strip()
    who = identity.identify(request)
    job = RA.rollout_start(network, [d for d in request.form.getlist("device") if d.strip()],
                           (request.form.get("canary") or "").strip(), _size(request.form),
                           (request.form.get("hash") or "").strip(),
                           actor=identity.request_actor(), actor_kind=getattr(who, "kind", ""),
                           named=request.form.getlist("management"))
    return _op(202, op={"state": "roll_running", "job": job, "network": network})


@bp.route("/read-account/rollout/go-on", methods=["POST"])
def read_account_rollout_go_on():
    """Go on after a pause, as a verified person: the next waves from the paused run's own
    record; a management-path device's wave only on the confirm naming it."""
    from modules import identity
    from modules.nsot import capture_job
    from modules.nsot import read_account as RA

    paused = (request.form.get("job") or "").strip()
    run = ((capture_job.get(paused) or {}).get("payload")) or {}
    why = RA.go_on_refusal(run, request.form.get("confirm_device") or "")
    if why:
        return _op(409, op={"state": "roll_refused", "error": why, "job": paused,
                                      "network": run.get("network", "")})
    who = identity.identify(request)
    job = RA.rollout_go_on(run, actor=identity.request_actor(),
                           actor_kind=getattr(who, "kind", ""))
    return _op(202, op={"state": "roll_running", "job": job,
                                  "network": run.get("network", "")})


@bp.route("/read-account/rollout/run/<job>", methods=["GET"])
def read_account_rollout_run(job):
    """The rollout's card for its job: running, paused (after the canary, or before a
    management-path device), stopped, done, refused, or why there is none."""
    from modules.nsot import capture_job

    got = capture_job.get(job)
    if got is None:
        return _op(op={"state": "roll_unknown", "job": job,
                                 "roll": {"network": (request.args.get("network") or "")}})
    if got["state"] == "running":
        return _op(op={"state": "roll_running", "job": job,
                                 "network": (request.args.get("network") or "")})
    run = got.get("payload") or {}
    if got["state"] == "failed" or run.get("state") == "refused":
        return _op(op={"state": "roll_refused", "job": job,
                                 "network": run.get("network", ""),
                                 "error": got.get("error") or run.get("error") or
                                 "the run did not finish"})
    return _op(op={"state": "roll_run", "job": job, "r": _run_view(run)})


def _run_view(run: dict) -> dict:
    """What the run's card draws: each wave with its devices' outcomes in place."""
    plan = run.get("plan") or {}
    results = {r.get("device"): r for r in run.get("results") or []}
    waves = []
    for n, batch in enumerate(plan.get("batches") or []):
        rows = []
        for d in batch:
            r = results.get(d)
            if r is None:
                outcome, why = ("waiting" if n >= run.get("next", 0) else "not attempted"), ""
            else:
                outcome = r.get("outcome") or ""
                why = r.get("reason") or (r.get("verify") or {}).get("summary") or ""
                if outcome == "deployed" and (r.get("verify") or {}).get("ok") is False:
                    outcome = "verify failed"
            rows.append({"device": d, "outcome": outcome, "why": why,
                         "carries": len((plan.get("carries") or {}).get(d) or [])})
        waves.append({"n": n, "kind": ("canary" if n == 0 else "management"
                                        if n in (plan.get("confirm_at") or []) else "wave"),
                      "rows": rows})
    nxt = run.get("next", 0)
    upcoming = (plan.get("batches") or [])[nxt] if nxt < len(plan.get("batches") or []) else []
    return {"state": run.get("state", ""), "network": run.get("network", ""),
            "stopped": run.get("stopped", ""), "waits": run.get("waits", ""), "waves": waves,
            "upcoming": upcoming, "hash": plan.get("hash", ""),
            "carries": {d: len(v) for d, v in (plan.get("carries") or {}).items()}}


@bp.route("/read-account/probe", methods=["GET"])
def read_account_probe_preview():
    """Probe the read-only account…: the probe's own plan for one device (whom it signs in as,
    every command in order and what is expected, its hash). Touches no device; writes nothing."""
    from modules.nsot import read_account_op as RAO

    p = RAO.preview((request.args.get("network") or "").strip(),
                    (request.args.get("device") or "").strip())
    return _op(200 if p["ok"] else 400, op={"state": "probe_preview", "p": p})


@bp.route("/read-account/probe", methods=["POST"])
def read_account_probe_confirm():
    """Confirm the probe's hash as a verified person: one job makes the plan again, refuses
    unless its hash is the one confirmed (or inside the backup window), then runs the probe
    holding the device and records it. Answers at once with the run's card."""
    from modules import identity
    from modules.nsot import read_account_op as RAO

    network = (request.form.get("network") or "").strip()
    device = (request.form.get("device") or "").strip()
    job = RAO.start(network, device, (request.form.get("hash") or "").strip(),
                    identity.request_actor())
    return _op(202, op={"state": "probe_running", "job": job, "network": network,
                        "device": device})


@bp.route("/read-account/probe/job/<job>", methods=["GET"])
def read_account_probe_job(job):
    """The probe's card for its job: running, its result (the verdict and each row), refused,
    or why there is none (its record is on History either way)."""
    from modules.nsot import capture_job

    network = (request.args.get("network") or "").strip()
    device = (request.args.get("device") or "").strip()
    got = capture_job.get(job)
    if got is None:
        return _op(op={"state": "probe_unknown", "network": network, "device": device})
    if got["state"] == "running":
        return _op(op={"state": "probe_running", "job": job, "network": network,
                       "device": device})
    run = got.get("payload") or {}
    if got["state"] == "failed" or run.get("state") != "done":
        return _op(op={"state": "probe_refused", "network": network, "device": device,
                       "error": got.get("error") or run.get("error") or
                       "the probe did not finish"})
    return _op(op={"state": "probe_done", "network": network, "device": device,
                   "r": run["rec"], "record": run["record"]})


# ---------------------------------------------------------------- scheduled rotation (C724)

@bp.route("/policy", methods=["GET"])
def policy_form():
    """Rotation policy…: the profile's policy in a form in place; nothing written."""
    from modules.nsot import scheduled_rotation as SR

    name = (request.args.get("name") or "").strip()
    return _region(op={"state": "policy", "name": name,
                       "policy": SR.policies().get(name) or {}})


@bp.route("/policy", methods=["POST"])
def policy_save():
    """Set the profile's rotation policy as the verified PERSON, and record it (who, when,
    what); the result in place."""
    from modules import identity
    from modules.nsot import scheduled_rotation as SR

    actor = identity.request_actor()
    ident = identity.verified_identity()
    name = (request.form.get("name") or "").strip()
    got = SR.set_policy(name, request.form, actor=actor,
                        verified=identity.actor_verification(actor),
                        person=bool(ident is not None and ident.kind == "person"))
    if not got["ok"]:
        return _region(400, op={"state": "policy", "name": name, "refused": got["error"],
                                "policy": dict(request.form)})
    return _region(op=dict(got, state="policy_saved", actor=actor))


@bp.route("/rotate-due", methods=["GET"])
def rotate_due_preview():
    """Rotate due devices now…: the devices it would take and those it leaves, each with why,
    and the hash to confirm. Reads files only; asks no device and changes nothing."""
    from modules.nsot import scheduled_rotation as SR

    return _region(op={"state": "rotate_preview", "p": SR.preview()})


@bp.route("/rotate-due", methods=["POST"])
def rotate_due_confirm():
    """Start the run as a job, as the verified person, bound to the previewed hash (the run
    recomputes it and refuses, naming both, when the due devices moved)."""
    from modules import identity
    from modules.nsot import scheduled_rotation as SR

    confirmed = (request.form.get("hash") or "").strip()
    p = SR.preview()
    if not confirmed or confirmed != p["hash"]:
        return _region(409, op={"state": "rotate_preview", "p": p, "refused": (
            f"the due devices changed since the preview you confirmed ({confirmed or 'none'} "
            f"-> {p['hash']}): nothing was sent; read them again and confirm")})
    if p["no_change"]:
        return _region(409, op={"state": "rotate_preview", "p": p, "refused": (
            f"inside {p['no_change']}: no run starts then; "
            "nothing was sent")})
    job, run_id = SR.start_now(actor=identity.request_actor(), confirmed=confirmed)
    return _region(202, op={"state": "rotating", "job": job, "run": run_id,
                            "r": SR.run_card(run_id)})


@bp.route("/rotate-due/job/<job>", methods=["GET"])
def rotate_due_job(job):
    """The run's card for its job: running on the one stepper, its result, or why there is
    none (this process has no record of it: the run's own record is on the page)."""
    from modules.nsot import capture_job
    from modules.nsot import scheduled_rotation as SR

    run_id = (request.args.get("run") or "").strip()
    got = capture_job.get(job)
    r = SR.run_card(run_id)
    if got is None or r is None:
        return _region(op={"state": "rotate_unknown", "job": job, "run": run_id})
    if got["state"] == "failed":
        return _region(op={"state": "rotate_failed", "job": job, "run": run_id,
                           "error": got.get("error") or "no reason was recorded", "r": r})
    state = "rotating" if got["state"] == "running" else "rotate_done"
    result = ((got.get("payload") or {}).get("result")) or {}
    return _region(op={"state": state, "job": job, "run": run_id, "r": r, "result": result})
