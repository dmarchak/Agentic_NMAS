"""routes/adopt_v2.py — Devices › Adopt a device… on v2 (7.4's board G, "adopt finishes the job",
signed off 2026-10-04; built 2026-10-10).

A device the tool did not build, brought under management with a login somebody gives. The
preview READS the device with that login and sends nothing (`adopt.plan`: every gate by name,
the program masked, what a save makes permanent, what NetBox holds, what it does not do). The
confirm starts `adopt.apply` as a job holding the device, drawn on the one stepper.

The supplied credential is somebody else's: it reaches the server in the form a person types
it in, is held in memory for the one call, and is NEVER drawn back into a page (a response
carrying it would be a credential returned). So the confirm asks for it again rather than
carrying it from the preview.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("adopt_v2", __name__, url_prefix="/v2/adopt")

#: The form's fields that are not secrets, in its order; the card carries them back.
FIELDS = ("list_name", "hostname", "mgmt_ip", "platform", "role", "supplied_username",
          "convert_supplied")


def _form() -> dict:
    return {k: (request.form.get(k) or "").strip() for k in FIELDS}


def _card(code: int = 200, **ctx):
    from routes.onboard import platform_choices

    return _strict(render_template("v2/_adopt.html", platforms=platform_choices(), **ctx), code)


def _dialect(slug: str) -> str:
    from routes.onboard import _dialect as d
    return d(slug)


@bp.route("/new", methods=["GET"])
def new():
    """Adopt a device…: the form, for the network the page names."""
    from modules.nsot import listref

    name = (request.args.get("list") or "").strip() or listref.active_name()
    return _card(f={"list_name": name})


@bp.route("/preview", methods=["POST"])
def preview():
    """The plan: reads the device with the supplied login and sends nothing. Every reason to
    refuse is drawn at once; the supplied credential is drawn nowhere."""
    from modules import identity
    from modules.nsot import adopt
    from modules.outbound import mask_payload
    from modules.preview_confirm import confirm_part

    f = _form()
    if not f["list_name"]:
        return _card(400, f=f, refused="no network was named: an adoption records into one")
    try:
        p = adopt.plan(f["list_name"], f["hostname"], mgmt_ip=f["mgmt_ip"],
                       platform=_dialect(f["platform"]),
                       supplied_username=f["supplied_username"],
                       supplied_password=request.form.get("supplied_password", ""),
                       supplied_enable=request.form.get("supplied_enable", ""),
                       actor=identity.request_actor() or "",
                       convert_supplied=f["convert_supplied"] == "on",
                       role=f["role"].lower())
    except Exception as exc:                          # noqa: BLE001 (said on the card)
        log.exception("adopt_v2: the preview of %s failed", f["hostname"])
        return _card(500, f=f, refused=f"the preview could not be made: {exc}")
    return _card(f=f, p=mask_payload(adopt.public(p)), may=confirm_part(request, "confirm"))


@bp.route("/confirm", methods=["POST"])
def confirm():
    """Adopt as previewed, as the verified person: the supplied login typed again (never carried
    from the preview), bound to the preview's fingerprint, the apply a job holding the device."""
    from modules import identity, invalidation
    from modules.nsot import adopt, capture_job
    from modules.outbound import mask_payload

    ident, refusal = identity.require(request, action="confirm", operation="adopt")
    f = _form()
    if refusal is not None:
        return _card(403, f=f, refused=refusal.get("error", ""))
    fingerprint = (request.form.get("fingerprint") or "").strip()
    password = request.form.get("supplied_password", "")
    if not fingerprint or not password:
        return _card(400, f=f, refused=(
            "the confirm needs the preview's fingerprint and the supplied password typed again "
            "(it is never carried from the preview); nothing was sent"))
    actor = identity.request_actor()
    args = dict(mgmt_ip=f["mgmt_ip"], platform=_dialect(f["platform"]),
                supplied_username=f["supplied_username"], supplied_password=password,
                supplied_enable=request.form.get("supplied_enable", ""),
                confirmed_fingerprint=fingerprint, actor=actor,
                reason=(request.form.get("reason") or "").strip(),
                convert_supplied=f["convert_supplied"] == "on", role=f["role"].lower())
    list_name, host = f["list_name"], f["hostname"]

    def work(_job_id):
        with identity.carried(ident):
            return mask_payload(adopt.apply(list_name, host, **args))

    job = capture_job.start(list_name, f"adopting {host}", actor, work, kind="adopt",
                            announce_keys=invalidation.ANNOUNCERS[ANNOUNCER],
                            announcer=ANNOUNCER)
    return _card(f=f, job=job, running=True, steps=_steps(list_name, host))


#: Its announcer: what an adoption's end changes is declared once, in `invalidation.ANNOUNCERS`.
ANNOUNCER = "adopt"


def _steps(list_name: str, host: str) -> list:
    from modules import device_actions
    return device_actions.job_steps("adopt", list_name, host)


@bp.route("/job/<job>", methods=["GET"])
def job_card(job):
    """The adoption's card for its job: running on the stepper, or its result."""
    from modules.nsot import capture_job

    f = {k: (request.args.get(k) or "").strip() for k in FIELDS}
    got = capture_job.get(job)
    if got is None:
        return _card(404, f=f, refused="this server has no record of that adoption: it ended "
                                       "more than 30 minutes ago, or the server restarted")
    if got["state"] == "running":
        return _card(f=f, job=job, running=True, steps=_steps(f["list_name"], f["hostname"]))
    if got["state"] == "failed":
        return _card(f=f, refused=f"the adoption raised: {got.get('error')}")
    return _card(f=f, r=got.get("payload") or {})
