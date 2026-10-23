"""routes/console_ztp_v2.py — out-of-band ZTP on v2: the console survey and the console
kick-start (O6b, docs/LAB9_PLAN.md section 8; the board docs/boards/console-ztp.html, drawn
under the Phase 7 mode and logged in docs/STANDING_APPROVAL_LOG.md).

A device being onboarded has no device page yet (it is a Planned record in NetBox, and Create
has not run), so its console card is drawn in place inside Add device (O7, the review's
"Kick-start through the console…"), keyed by the network and the device's NetBox id, the id
`console_path.read_console_path` reads its console path by; after Create, the same card is
offered on Create's result and on the device's pending page (`pending_console`, C1575, board F),
so closing Add device never loses it. One card, in the state its query names:

- the survey: ``choose`` (the profile), ``confirm`` (its preview: the console path, the port's
  record, the transport, the profile and its hash, the program by state, what it does not do,
  and the confirm bound to the hash), ``running`` (a job: THE stepper from the confirm's own answer, filled on each
  ``device_progress``, its record read on ``console_ztp``; C1579) and
  ``result`` (blank, not blank or unknown with its reasons, the MAC, the masked transcript);
- the kick-start: the same four, its preview the EXACT lines it types and the survey it stands
  on, its confirm a verified person's.

Every action is `modules/nsot/console_ztp.py`'s: the preview here is its preview, the confirm
runs its run as a job (`capture_job`), which recomputes the preview and refuses, naming both
hashes, when it moved. The kick-start is offered only once the device is in the network (Create
ran): Create writes what the device asks for when the kick-start makes it ask (its reservation
and its bootstrap).
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("console_ztp_v2", __name__, url_prefix="/v2/onboard/console")

STEPS = ("survey", "kickstart")
#: A kick-start parameter's form field is this prefix and the parameter's name (the profile
#: declares the names, `console_profiles`); the hostname is never a field: it is the device's
#: NetBox name (`console_ztp.kickstart_params`).
PARAM_FIELD = "param_"


# ── the offer (O7): drawn by Add device's review ───────────────────────────────────────────

def profile_for(platform: str, role: str) -> str:
    """The shipped console profile for a device of *platform* (a dialect) and *role*: the one
    whose platform is the device's and whose name ends with its role; else the platform's only
    one; else ``""`` (the card then asks)."""
    from modules.nsot import console_profiles as P

    fits = []
    for name in P.shipped():
        try:
            if P.load(name).platform == platform:
                fits.append(name)
        except P.ProfileError:
            continue
    by_role = [n for n in fits if role and n.endswith("_" + role)]
    if len(by_role) == 1:
        return by_role[0]
    return fits[0] if len(fits) == 1 else ""


def offer(list_name: str, netbox_id, hostname: str, platform: str = "", role: str = "") -> dict:
    """Whether Add device offers "Kick-start through the console" for *hostname*, and why not:
    ``{"state": "path" | "no_record" | "no_path" | "unreadable", "why", "paths", "device_id",
    "profile", "list_name", "hostname"}``. One read of NetBox (the console path), only for a
    device NetBox holds as a Planned record (*netbox_id*)."""
    out = {"state": "no_record", "why": "", "paths": [], "device_id": netbox_id,
           "profile": profile_for(platform, role), "list_name": list_name,
           "hostname": hostname}
    if not netbox_id:
        out["why"] = (f"NetBox holds no Planned record of {hostname or 'this device'}, and a "
                      "console path is read from the device's NetBox record: plan the device "
                      "in NetBox, with its console port cabled to a console server's port, to "
                      "be offered a console kick-start")
        return out
    from modules.nsot import console_path

    got = console_path.read_console_path(netbox_id)
    if got["state"] == "path":
        out.update(state="path", paths=got["paths"])
    elif got["state"] == "no_path":
        out.update(state="no_path", why=got.get("why") or "NetBox shows no console path")
    else:
        out.update(state="unreadable", why=got.get("error") or "the console path could not "
                                                               "be read")
    return out


@bp.route("/offer", methods=["GET"])
def offer_view():
    """The offer, drawn in Add device's review as it loads (one NetBox read, the console path):
    "Kick-start through the console…" when NetBox shows one, its absence said when not. With
    ``pending=1``, on a pending device's page with no survey recorded (C1575): "Survey its
    console…" when NetBox shows a path, nothing when it shows none (the device is onboarded
    another way), and an unreadable NetBox said."""
    args = request.args
    nb = (args.get("netbox_id") or "").strip()
    console = offer((args.get("list_name") or "").strip(), int(nb) if nb.isdigit() else None,
                    (args.get("hostname") or "").strip(), (args.get("platform") or "").strip(),
                    (args.get("role") or "").strip())
    return _strict(render_template("v2/_console_offer.html", console=console,
                                   pending=args.get("pending") == "1"))


def surveyed_offer(list_name: str, hostname: str):
    """After Create: the kick-start offer for *hostname* when a console survey of it is
    recorded in *list_name* (the installation's index; no NetBox read), else None."""
    from modules.nsot import console_ztp as Z

    got = Z.read_index()
    if got["state"] != "read":
        return None
    hits = [e for e in got["devices"].values()
            if e.get("list") == list_name and e.get("survey")
            and str(e.get("device") or "").lower() == str(hostname or "").lower()]
    if len(hits) != 1:
        return None
    entry = hits[0]
    survey = entry["survey"]
    # What the offer draws of the survey (`_console_kick.html`), and nothing it does not. `by`
    # is who ran the recorded survey, a stored record's field (never this request's actor).
    return {"device_id": entry.get("device_id"), "list_name": list_name,
            "hostname": entry.get("device") or hostname,
            "survey": {"at": survey.get("at"),
                       "by": survey["actor"] if "actor" in survey else "",
                       "blank": survey.get("blank"),
                       "profile": {"name": (survey.get("profile") or {}).get("name")}}}


def pending_console(list_name: str, hostname: str) -> dict:
    """A pending device's console part (C1575: once Add device's card is closed, its page is
    the way back): ``{"kick", "netbox_id", "platform", "role", "list_name", "hostname"}``.
    *kick* is `surveyed_offer` (the card at the kick-start, or at the survey again when the
    recorded survey did not find it blank); without one, *netbox_id* is the NetBox record its
    onboarding recorded, whose console path the page asks for as it draws (`offer_view`,
    ``pending=1``), so the page itself never waits on NetBox. Reads the installation's index
    and the network's manifest; creates nothing."""
    from modules.nsot import listref, manifest

    out = {"kick": surveyed_offer(list_name, hostname), "netbox_id": None, "platform": "",
           "role": "", "list_name": list_name, "hostname": hostname}
    if out["kick"] is not None or not list_name or not listref.exists(list_name):
        return out
    try:
        entry = manifest.find_by_name(listref.resolve(list_name).repo_dir, hostname)[1] or {}
    except Exception:                      # noqa: BLE001 - a read; the page draws no offer
        log.warning("console ZTP: %s's manifest could not be read for %s", list_name, hostname,
                    exc_info=True)
        entry = {}
    nb = entry.get("netbox_id")
    out.update(netbox_id=nb if isinstance(nb, int) and nb > 0 else None,
               platform=entry.get("platform") or "", role=entry.get("role") or "")
    return out


# ── the card ───────────────────────────────────────────────────────────────────────────────

def _profiles() -> list:
    from modules.nsot import console_profiles as P

    out = []
    for name in P.shipped():
        try:
            prof = P.load(name)
        except P.ProfileError as exc:
            out.append({"name": name, "version": "", "sha256": "", "why": str(exc)})
            continue
        out.append({"name": prof.name, "version": prof.version, "sha256": prof.sha256,
                    "description": prof.data.get("description", ""), "why": ""})
    return out


def _onboarded(list_name: str, hostname: str) -> str:
    """Why a kick-start may not be typed yet for *hostname* in *list_name* (Create has not run:
    no entry in the network's manifest), or ``""``. Read only: creates nothing."""
    from modules.nsot import listref, manifest

    if not hostname:
        return ""                          # the preview refuses the device itself, by its id
    if not listref.exists(list_name):
        return f"no network named {list_name!r}"
    try:
        entry = manifest.find_by_name(listref.resolve(list_name).repo_dir, hostname)[1]
    except Exception as exc:              # noqa: BLE001 - a read; said, never raised
        return f"{list_name}'s manifest could not be read ({type(exc).__name__}: {exc})"
    if not entry:
        return (f"{hostname} is not in {list_name} yet: Create it in Add device first, so its "
                "reservation and bootstrap exist when the kick-start makes it ask for them")
    return ""


def _never_asked() -> tuple:
    """The kick-start's parameters no form field asks for: the hostname (the device's NetBox
    name) and the static address, mask and gateway (its out-of-band onboarding's plan, C1592:
    `console_kickstart.PLAN_PARAMS`)."""
    from modules.nsot.console_kickstart import PLAN_PARAMS
    return ("hostname",) + PLAN_PARAMS


def _kick_params(profile_name: str, form) -> dict:
    """The kick-start's parameters the form sends: one field per parameter the profile declares
    (`PARAM_FIELD` + its name), those Mercury derives excepted (`_never_asked`)."""
    from modules.nsot import console_profiles as P

    try:
        declared = P.load(profile_name).kickstart_params if profile_name else {}
    except P.ProfileError:
        declared = {}
    return {n: (form.get(PARAM_FIELD + n) or "").strip() for n in declared
            if n not in _never_asked()}


def _declared(profile_name: str) -> list:
    """The parameters the kick-start's form asks for, in the profile's order: ``[{name,
    shape}]`` (those Mercury derives left out, `_never_asked`)."""
    from modules.nsot import console_profiles as P

    try:
        params = P.load(profile_name).kickstart_params if profile_name else {}
    except P.ProfileError:
        return []
    return [{"name": n, "shape": s} for n, s in params.items() if n not in _never_asked()]


def run_steps(kind: str, list_name: str, device: str, *, now=None) -> list:
    """A run's rows for THE stepper (C1579; the deploy's pattern: drawn at the confirm and
    filled by each `device_progress` announcement): the preview and the confirm done, then the
    run's declared steps (`console_ztp.run_stepper_steps`) read from *device*'s hold, noted as
    each begins (`device_actions.stepper`, *starts*). Until the job takes the hold, the first
    is running from now and the rest have not run; a hold by another operation is not this
    run's progress. In THE stepper's own step shape (`run_stepper.from_stepper`: what it waits
    on already its note), so the card carries only what it draws."""
    from modules import device_actions, run_stepper
    from modules.nsot import console_ztp as Z
    from modules.nsot import device_ops

    try:
        holder = (device_ops.holder(list_name, device) or {}) if device else {}
    except device_ops.HoldsUnreadable:
        holder = {}
    op = Z.OP_SURVEY if kind == Z.KIND_SURVEY else Z.OP_KICKSTART
    progress = holder.get("progress") if holder.get("operation") == op else None
    before = [{"key": key, "words": Z.STEP_LABELS[key], "state": "done"}
              for key in Z.BEFORE_RUN]
    return run_stepper.from_stepper(before + device_actions.stepper(
        Z.run_stepper_steps(kind), progress, now=now, starts=True))


def card(list_name: str, device_id: int, args) -> dict:
    """The card's context from its query: ``step``, ``state``, ``profile``, ``profiles``,
    ``params`` (typed kick-start fields), ``run``, ``job``, ``rec`` (a run's record), ``error``,
    ``survey`` (the latest survey, for the kick-start), ``add`` (drawn inside Add device),
    ``steps`` (a running run's stepper rows, `run_steps`)."""
    from modules.nsot import capture_job
    from modules.nsot import console_ztp as Z

    step = args.get("step") if args.get("step") in STEPS else "survey"
    c = {"list_name": list_name, "device_id": device_id, "step": step, "state": "choose",
         "profile": (args.get("profile") or "").strip(), "profiles": _profiles(),
         "hostname": (args.get("hostname") or "").strip(), "add": args.get("add") == "1",
         "run": (args.get("run") or "").strip(), "job": (args.get("job") or "").strip(),
         "rec": None, "error": "", "job_error": "", "pv": None, "survey": None, "params": {},
         "declared": [], "steps": []}
    if step == "kickstart":
        c["survey"], why = Z.latest_survey(list_name, device_id)
        c["profile"] = ((c["survey"] or {}).get("profile") or {}).get("name") or c["profile"]
        c["declared"] = _declared(c["profile"])
        c["params"] = {d["name"]: (args.get(PARAM_FIELD + d["name"]) or "").strip()
                       for d in c["declared"]}
        if c["survey"] is None:
            c["error"] = why
        else:
            c["hostname"] = c["hostname"] or c["survey"].get("device") or ""
            c["error"] = _onboarded(list_name, c["hostname"])
    if c["run"]:
        # The JOB first, then the record (C642's order): a job seen ended means its record is
        # final; read the other way round, a run finishing between the reads drew as running.
        job = capture_job.get(c["job"]) if c["job"] else None
        try:
            rec = Z.get_run(list_name, c["run"])
        except ValueError:
            rec = None
        if rec is not None and rec.get("outcome") != "running":
            c.update(state="result", rec=rec)
        elif job is not None and job["state"] == "running":
            c.update(state="running", rec=rec, steps=run_steps(
                step, list_name, (rec or {}).get("device") or c["hostname"]))
        elif job is not None and job["state"] == "failed":
            c.update(state="failed", rec=rec, job_error=job.get("error") or "the run failed")
        elif rec is not None:
            c.update(state="lost", rec=rec)
        else:
            c.update(state="lost")
    return c


def _draw(c: dict, code: int = 200):
    return _strict(render_template("v2/_console_ztp.html", c=c), code)


def _device_id(value) -> int:
    return value if isinstance(value, int) and value > 0 else 0


@bp.route("/<int:device_id>", methods=["GET"])
def card_view(device_id):
    """The card alone, in the state its query names. Contacts no console and no NetBox."""
    list_name = (request.args.get("list_name") or "").strip()
    return _draw(card(list_name, _device_id(device_id), request.args))


def _preview_card(device_id: int, form, code: int = 200, **extra):
    """The confirm state: the step's preview, drawn, or the choose state with its refusals."""
    from modules.nsot import console_ztp as Z

    list_name = (form.get("list_name") or "").strip()
    c = card(list_name, device_id, form)
    if c["step"] == "survey":
        pv = Z.survey_preview(list_name, device_id, profile=c["profile"])
    else:
        if c["error"]:
            c.update(extra)
            return _draw(c, code if code != 200 else 409)
        pv = Z.kickstart_preview(list_name, device_id, _kick_params(c["profile"], form))
    c.update(pv=pv, state="confirm" if pv["ok"] else "choose", **extra)
    c["hostname"] = pv.get("device") or c["hostname"]
    return _draw(c, code if (pv["ok"] or code != 200) else 409)


@bp.route("/<int:device_id>/survey/preview", methods=["POST"])
def survey_preview(device_id):
    """The survey's preview: NetBox read, nothing contacted, nothing written."""
    return _preview_card(_device_id(device_id), request.form)


@bp.route("/<int:device_id>/kickstart/preview", methods=["POST"])
def kickstart_preview(device_id):
    """The kick-start's preview: the exact lines; nothing contacted, nothing written."""
    return _preview_card(_device_id(device_id), request.form)


def _start(device_id: int, kind: str, confirmed: str):
    """Refuse now (drawn, nothing sent) or start the run as a job and draw it running."""
    from modules import identity
    from modules.nsot import capture_job, reads
    from modules.nsot import console_ztp as Z

    form = request.form
    list_name = (form.get("list_name") or "").strip()
    operation = "console_survey" if kind == Z.KIND_SURVEY else "console_kickstart"
    ident, refusal = identity.require(request, action="confirm", operation=operation)
    if refusal is not None:
        return _preview_card(device_id, form, 403, error=refusal.get("error", ""))
    actor = ident.actor
    verified = identity.actor_verification(actor)
    c = card(list_name, device_id, form)
    if kind == Z.KIND_SURVEY:
        pv = Z.survey_preview(list_name, device_id, profile=c["profile"])
    else:
        if c["error"]:
            return _draw(dict(c, error=c["error"] + ". Nothing was sent."), 409)
        why = Z.verified_person(actor, verified)
        if why:
            return _preview_card(device_id, form, 403, error=why + ". Nothing was sent.")
        params = _kick_params(c["profile"], form)
        pv = Z.kickstart_preview(list_name, device_id, params)
    what = "survey" if kind == Z.KIND_SURVEY else "kick-start"
    if not pv["ok"]:
        return _draw(dict(c, pv=pv, state="choose",
                          error="; ".join(pv["refusals"]) + ". Nothing was sent."), 409)
    if confirmed != pv["hash"]:
        return _draw(dict(c, pv=pv, state="confirm", error=(
            f"the {what} changed since the preview you confirmed ({confirmed or 'no hash'} -> "
            f"{pv['hash']}): its console path, port, transport, profile"
            + (" or survey" if kind == Z.KIND_KICKSTART else "")
            + " moved. Nothing was sent; read this preview and confirm again")), 409)
    run_id = reads.new_id()
    device = pv["device"]
    if kind == Z.KIND_SURVEY:
        profile = c["profile"]

        def work(_job_id):
            return {"run": Z.survey_run(list_name, device_id, profile=profile,
                                        confirmed_hash=confirmed, actor=actor,
                                        actor_verified=verified, run_id=run_id,
                                        timings=Z.DEFAULT_TIMINGS)["id"]}
    else:
        params = pv["params"]

        def work(_job_id):
            return {"run": Z.kickstart_apply(list_name, device_id, confirmed, actor, verified,
                                             params=params, run_id=run_id,
                                             timings=Z.DEFAULT_TIMINGS)["id"]}
    job = capture_job.start(list_name, f"console {what} of {device}", actor, work,
                            kind=f"console {what}", announce_keys=Z.ANNOUNCE_KEYS,
                            announcer=Z.ANNOUNCER)
    log.info("console %s of %s (NetBox device %s) in %s started by %s: job %s, run %s", what,
             device, device_id, list_name, actor, job, run_id)
    # The stepper at once (C1579): every run step not yet run, the first running from now.
    return _draw(dict(c, state="running", run=run_id, job=job, hostname=device, pv=pv,
                      step=kind, steps=run_steps(kind, list_name, device)))


@bp.route("/<int:device_id>/survey", methods=["POST"])
def survey_confirm(device_id):
    """The survey as previewed, as the verified person, bound to the preview's hash."""
    from modules.nsot import console_ztp as Z

    return _start(_device_id(device_id), Z.KIND_SURVEY, (request.form.get("hash") or "").strip())


@bp.route("/<int:device_id>/kickstart", methods=["POST"])
def kickstart_confirm(device_id):
    """The kick-start as previewed, as a verified person, bound to the preview's hash."""
    from modules.nsot import console_ztp as Z

    return _start(_device_id(device_id), Z.KIND_KICKSTART,
                  (request.form.get("hash") or "").strip())
