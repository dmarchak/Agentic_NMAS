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
    from modules.preview_confirm import confirm_part

    return dict({"v": P.view(), "kinds": P.KINDS, "may": confirm_part(request, "configure")},
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
