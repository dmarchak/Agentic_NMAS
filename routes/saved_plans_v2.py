"""routes/saved_plans_v2.py — saved plans on the incident card (Gate 1b; C3696, C3763;
modules/nsot/saved_plans.py), drawn by `templates/v2/_saved_plans_saves.html`, which the
incident's AI troubleshooting section includes and asks for in place.

- ``card`` (GET): what the incident offers: after a command plan that ran and passed its own
  verify, Save as a self-heal script (its R4 match, previewed on the open incidents, and its
  open parameters) and Save as a reusable action (its name and parameters); the scripts whose
  match its problem holds, each with Promote; the network's provisional shapes, each with
  Approve. A read.
- ``save_script``, ``save_action``, ``promote``, ``approve_shape`` (POST): each as the
  verified person, through the one chokepoint (`identity.right_refusal`): the self-healing
  right for a script and its promotion, the admin right for an action and a shape. Each
  answers with the card, its result or refusal drawn in place.

Its declarations live in their tables (`route_gates.GATES`, `invalidation.DECLARED`,
`operation_stages.STAGES`).
"""

import logging

from flask import Blueprint, render_template, request

from routes.assistant_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("saved_plans_v2", __name__, url_prefix="/v2/saved-plans")


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _who() -> dict:
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "actor_verified": identity.actor_verification(actor),
            "person": bool(ident is not None and ident.kind == "person")}


def _draw(network: str, incident: str, code: int = 200, *, show: bool = False, **said):
    from modules.nsot import command_policy, saved_plans

    got = saved_plans.offer(network, incident, **_who())
    # What the card draws, and nothing it does not (the run's id and the problem stay the
    # offer's: a save reads them again).
    c = {k: got[k] for k in ("state", "why", "plan", "match", "optional", "fills", "rights",
                             "scripts", "unset", "saved", "name", "dismissed")}
    c.update(preview={"matched": len((got.get("preview") or {}).get("matched") or []),
                      "read": (got.get("preview") or {}).get("read") or 0},
             list=network, incident=incident, shapes=command_policy.provisional(network),
             said=said, show=bool(show))
    return _strict(render_template("v2/_saved_plans_saves.html", c=c), code)


@bp.route("/<incident>/card", methods=["GET"])
def card(incident):
    """The incident's saves, promotions and shapes, in place; ``show=1`` draws the offer again
    after Not now put it off (its Save this fix…)."""
    return _draw(_list_name(), incident, show=request.args.get("show") == "1")


@bp.route("/<incident>/not-now", methods=["POST"])
def not_now(incident):
    """Not now (board R5's screen 5): the offer to save the incident's verified fix put off for
    this incident, as the verified person: one choice line in its troubleshooting record
    (`fixit.incident.record_save`, ``dont_save``). Saves nothing, sends nothing to a device;
    the card then says so in one line, with Save this fix… to show the offer again."""
    from modules import incident_page
    from modules.fixit import incident as F
    from modules.fixit import section

    network, who = _list_name(), _who()
    if not (who["person"] and who["actor"] and who["actor_verified"] not in ("", "none")):
        return _draw(network, incident, 403, level="danger", words=(
            f"Not recorded: Not now is a verified person's press, and this request is not one "
            f"(its actor is {who['actor'] or 'none'})"))
    found = incident_page.resolve(network, incident)
    inc = (section.incident_of(network, found).get("incident")
           if found.get("found") == "page" else None)
    if inc is None:
        return _draw(network, incident, 409, level="danger",
                     words=f"Not recorded: {incident} has no troubleshooting record to keep it")
    try:
        F.record_save(inc, "dont_save", who["actor"], who["actor_verified"])
    except (F.Refused, OSError, ValueError) as exc:
        return _draw(network, incident, 409, level="danger", words=f"Not recorded: {exc}")
    return _draw(network, incident)


def _refused(network, incident, exc, code=409):
    return _draw(network, incident, 403 if "may not approve" in str(exc)
                 or "does not hold" in str(exc) or "verified person" in str(exc) else code,
                 level="danger", words=f"Not saved: {exc}")


@bp.route("/<incident>/save-script", methods=["POST"])
def save_script(incident):
    """Save the incident's verified run as a self-heal script, in Dry run: its match the
    problem's fields the person kept (the condition always), its fills the card's."""
    from modules.nsot import saved_plans as S

    network, form = _list_name(), request.form
    o = S.offer(network, incident, **_who())
    if o["state"] != "ready":
        return _draw(network, incident, 409, level="danger", words=f"Not saved: {o['why']}")
    match = {"condition": o["match"]["condition"],
             **{k: v for k, v in o["match"].items()
                if k in S.OPTIONAL_MATCH and form.get(f"keep_{k}") == "1"}}
    try:
        e = S.save_script(network, run_id=o["run"], name=(form.get("name") or "").strip(),
                          match=match, fills=o["fills"], **_who())
    except S.Refused as exc:
        return _refused(network, incident, exc)
    # Its result is the card's own line for what is saved from the run ("Saved: <name>, Dry
    # run", `saved_plans.saved_from`), its form collapsed: the redraw its announcement asks
    # for draws the same line (item 7, the operator, 2026-11-15).
    log.info("saved plans: %s saved as a self-heal script of %s", e["key"], network)
    return _draw(network, incident)


@bp.route("/<incident>/save-action", methods=["POST"])
def save_action(incident):
    """Save the incident's verified run as a reusable action (an admin's)."""
    from modules.nsot import saved_plans as S

    network, form = _list_name(), request.form
    o = S.offer(network, incident, **_who())
    if o["state"] != "ready":
        return _draw(network, incident, 409, level="danger", words=f"Not saved: {o['why']}")
    try:
        e = S.save_action(network, run_id=o["run"], name=(form.get("name") or "").strip(),
                          words=(form.get("words") or "").strip(), **_who())
    except S.Refused as exc:
        return _refused(network, incident, exc)
    # Its result is the card's line "Saved: <name>, in the catalog" (`saved_from`), as above.
    log.info("saved plans: %s saved as a reusable action", e["key"])
    return _draw(network, incident)


@bp.route("/<incident>/promote", methods=["POST"])
def promote(incident):
    """Promote a saved script from Dry run to Auto (self-healing rights)."""
    from modules.nsot import saved_plans as S

    network = _list_name()
    try:
        e = S.promote((request.form.get("key") or "").strip(), network=network, **_who())
    except S.Refused as exc:
        return _refused(network, incident, exc)
    return _draw(network, incident, level="ok", words=(
        f"Promoted {e['name']}: when its match holds it runs, while self-healing is in Auto"))


@bp.route("/<incident>/approve-shape", methods=["POST"])
def approve_shape(incident):
    """Approve a provisional shape into Mercury's rule for raw lines (an admin's)."""
    from modules.nsot import command_policy

    network, form = _list_name(), request.form
    got = command_policy.approve_as(network, (form.get("dialect") or "").strip(),
                                    (form.get("shape") or "").strip(), **_who())
    if not got["ok"]:
        return _draw(network, incident, 403 if "may not approve" in got["words"]
                     or "does not hold" in got["words"] else 409,
                     level="danger", words=f"Not approved: {got['words']}")
    return _draw(network, incident, level="ok", words=got["words"])


# ── A device's interface view: a saved action on one interface (board saved-plans D) ────────

def _device_draw(network: str, device: str, code: int = 200, *, key: str = "",
                 interface: str = "", run: str = "", **said):
    """The device's saved-actions card: the actions an interface fills and the device's
    interfaces; with *key* and *interface*, that action's preview by the runner's own preview
    (asking no device: the program masked, every check, the hash Run is bound to); with *run*,
    the run's state from its own record."""
    from modules.nsot import command_plan as CP
    from modules.nsot import privileged, saved_plans

    c = saved_plans.device_offer(network, device, **_who())
    c.update(list=network, device=device, said=said, preview=None, run=None, key=key,
             interface=interface)
    if key and interface and key in saved_plans.interface_actions():
        p = CP.preview(network, key, {"device": device, "interface": interface})
        c["preview"] = {"ok": p["ok"], "title": p.get("title") or "", "hash": p["hash"],
                        "refusals": list(p.get("refusals") or []),
                        "drawn": dict(p.get("drawn") or {})}
    if run:
        try:
            rec = privileged.get(network, run) or {}
        except (ValueError, OSError):
            rec = {}
        c["run"] = {"id": run, "state": rec.get("state") or "running",
                    "outcome": rec.get("outcome") or "", "why": rec.get("why") or "",
                    "title": rec.get("title") or ""}
    return _strict(render_template("v2/_saved_actions_device.html", c=c), code)


@bp.route("/device/<device>/actions", methods=["GET"])
def device_actions(device):
    """The device's saved actions, a preview of one on one interface, or a run's state."""
    a = request.args
    return _device_draw(_list_name(), device, key=(a.get("key") or "").strip(),
                        interface=(a.get("interface") or "").strip(),
                        run=(a.get("run") or "").strip())


@bp.route("/device/<device>/run", methods=["POST"])
def device_run(device):
    """Run a saved action on one interface, as the verified person, bound to its previewed
    hash: the runner's own run as a job (the device held, the preconditions read again, sent,
    verified, rolled back on a failed verify, recorded), its state drawn in place."""
    from modules.nsot import capture_job
    from modules.nsot import command_plan_run as CR
    from modules.nsot import reads, saved_plans

    network, form = _list_name(), request.form
    key, iface = (form.get("key") or "").strip(), (form.get("interface") or "").strip()
    confirmed = (form.get("hash") or "").strip()
    who = _who()
    if key not in saved_plans.interface_actions():
        return _device_draw(network, device, 409, level="danger",
                            words=f"Not run: {key or 'no action'} is no saved action on one "
                                  "interface")
    from modules import identity

    why = identity.right_refusal("run_plan", **who)
    if why:
        return _device_draw(network, device, 403, key=key, interface=iface, level="danger",
                            words=f"Not run: {why}")
    run_id = reads.new_id()

    def work(_job):
        rec = CR.run(network, key, {"device": device, "interface": iface}, run_id=run_id,
                     confirmed=confirmed, reason=f"a saved action pressed on {device}",
                     **who)
        return {"run": rec.get("id"), "state": rec.get("state"),
                "words": CR.OUTCOME_WORDS.get(rec.get("outcome") or "", "")
                or str(rec.get("why") or "")}
    # A page's job (`capture_job.start`'s ``page``), not a device card's: In progress lists it
    # and reopens it at the device's Overview with this run, where its card draws the run's
    # state from its record (`_saved_actions_slot.html` passes the run on).
    from urllib.parse import quote, urlencode
    capture_job.start(network, f"{key} on {device} {iface}", who["actor"], work,
                      kind="saved action", announce_keys=CR.ANNOUNCE_KEYS,
                      announcer=CR.ANNOUNCER,
                      page=(f"/v2/device/{quote(device, safe='')}?"
                            + urlencode({"tab": "overview", "list": network, "run": run_id})))
    return _device_draw(network, device, run=run_id)
