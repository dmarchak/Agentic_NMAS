"""routes/credential_profiles_v2.py — Source of truth › Credentials › Profiles on v2 (the board
drawn 2026-10-10 under the Phase 7 mode; CUTOVER's "Credential profiles").

The profiles the resolver gives a NetBox inventory's devices (role, site, default), each with
what it covers, set or not set, never a value; Add a profile…, Edit… and Delete… in place, each
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

    return dict({"v": P.view(), "kinds": P.KINDS, "may": confirm_part(request, "configure"),
                 "rot": SR.page_view(), "may_rotate": confirm_part(request, "confirm")},
                **extra)


def _region(code: int = 200, **extra):
    return _strict(render_template("v2/_credential_profiles.html", **_ctx(**extra)), code)


@bp.route("", methods=["GET"])
def page():
    """The Profiles tab. A read: nothing is written and no value is read out."""
    from routes.v2 import _credentials_list, _page

    return _page("v2/credentials.html", active_nav="credentials", tab="profiles",
                 list_name=_credentials_list(request), known=True, **_ctx())


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
    if p["backup_window"]:
        return _region(409, op={"state": "rotate_preview", "p": p, "refused": (
            "inside the nightly backup window, 08:30 to 09:10 UTC: no run starts then; "
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
