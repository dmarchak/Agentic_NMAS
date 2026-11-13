"""routes/fixit_v2.py — the incident page's "AI troubleshooting" section's controls (board
recurring-fixes v2; the fix-it plan's S4 and S5), drawn from `modules/fixit/section.py`.

Each post answers with the section drawn again in place (`templates/v2/_fixit_section.html`),
its answer leading it; none opens a second card elsewhere on the page:

- ``cancel``: Cancel. One line in the incident's troubleshooting record, a verified person's;
  nothing runs, nothing is sent, and the incident stays open (`incident.cancel`).
- ``retry``: Retry with more information's Ask Mercury's diagnosis to re-plan. The
  per-incident cap asked again at the press, then Mercury's own diagnosis re-plans
  (`section.retry`): one proposal line, the person's note kept with it. No AI call.
- ``troubleshoot``: Troubleshoot with AI, and Retry's Ask the AI to re-plan (S5): ONE
  investigation asked as the verified person who pressed (`triggers.person`), the mode and
  the per-incident cap asked again at the press, its answer checked by code and, when it names
  one catalog operation, that proposal held to the same check as Mercury's own and opened in
  its operation's own preview (`fixit_troubleshoot.troubleshoot`). It runs nothing: the
  proposal's Approve is the operation's own card and confirm, by its preview's hash.
- ``handover``: Hand over. The write-up built from the incident's records with no AI, kept as
  a new version, and sent to the teams ticked, each one told about the network's can't-fix
  (`handover.hand_over`).
- ``handover_send``: Send again, a kept write-up sent once more to the same teams.
- ``handover_page``: the write-up's own page, ``/v2/incident/<id>/handover/<version>`` (a GET;
  ``?download=md`` gives it as Markdown).

Every post is a verified person's, gated ``configure`` (`modules/route_gates.py`; the board's
decision 8: Troubleshoot, Retry, Cancel and Hand over as Explain), and each declares what it
invalidates (`modules/invalidation.py`). The proposal's Approve is the operation's own card and
confirm (routes/resubscribe_v2.py), which carries the incident, the attempt and the proposal
into its run's record. Nothing here holds a device or starts a job, and only ``troubleshoot``
asks a model, on a person's press.
"""

import logging
import time

from flask import Blueprint, Response, render_template, request

from routes.device_v2 import _page_ref, _strict, _who, carry_list

log = logging.getLogger(__name__)

bp = Blueprint("fixit_v2", __name__, url_prefix="/v2/incident")
bp.url_defaults(carry_list)       # the page's network on every URL it draws (C494)


def _found(incident_id: str):
    """``(network, found)`` for *incident_id* on the page's network (`incident_page.resolve`)."""
    from modules import incident_page

    ref = _page_ref()
    return ref.name, incident_page.resolve(ref.name, incident_id)


def _ended(found: dict) -> str:
    """How the incident ended, by the page's own rule (`incident_page.state_of`: fixed,
    cleared or a declined proposal), or ``""`` while it stands."""
    from modules import incident_page

    state = incident_page.state_of(found["incident"], found["entry"], found["decisions"])
    return state if state in ("fixed", "cleared", "cancelled") else ""


def _resolved_at(found: dict):
    """When the incident resolved (epoch seconds), or None while it stands."""
    from modules.fixit.section import _epoch

    if not _ended(found):
        return None
    closed = (found["incident"] or {}).get("closed_at") or ""
    return _epoch(closed) or time.time()


def _section(network: str, found: dict, status: int = 200, **answer):
    """The section drawn again, its *answer* leading it."""
    from modules.fixit import section

    x = section.drawn(network, found, resolved=_resolved_at(found), ended=_ended(found))
    # A can't-fix's AI analysis in full (C3488), as the incident's page draws it.
    from routes.v2 import with_heal_analysis
    with_heal_analysis(x)
    return _strict(render_template("v2/_fixit_section.html", x=x, answer=answer), status)


def _missing(incident_id: str, found: dict):
    """The answer for an id with no page: 404, said in place."""
    x = {"state": "none", "id": incident_id, "network": found.get("network") or "",
         "why": (f"{incident_id} is no incident this network's records hold"
                 if found["found"] != "unreadable" else
                 "its records could not be read: " + "; ".join(found["unreadable"]))}
    return _strict(render_template("v2/_fixit_section.html", x=x, answer={}), 404)


def _person() -> dict:
    """The request's verified actor, how it was established and whether it is a person
    (`identity.verified_identity`, which fails closed)."""
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "actor_verified": identity.actor_verification(actor),
            "person": bool(ident is not None and ident.kind == "person")}


def _not_a_person(who: dict, what: str) -> str:
    if who["person"] and who["actor"] and who["actor_verified"] not in ("", "none"):
        return ""
    return (f"{what} is a verified person's press, and this request is not one (its actor is "
            f"{who['actor'] or 'none'}, verified by {who['actor_verified'] or 'nothing'}). "
            "Nothing was recorded")


@bp.route("/<incident_id>/fixit/cancel", methods=["POST"])
def cancel(incident_id):
    """Cancel: one line recorded for the verified person; nothing runs, the incident stays
    open (`section.CANCEL_STEPS`)."""
    from modules.fixit import incident as F
    from modules.fixit import section

    network, found = _found(incident_id)
    if found["found"] != "page":
        return _missing(incident_id, found)
    if _ended(found):
        return _section(network, found, 409, refused=(
            f"{incident_id} is resolved ({_ended(found)}), and its AI troubleshooting is "
            "read-only. Nothing was recorded or sent"))
    who = _person()
    why = _not_a_person(who, "Cancel")                                             # person
    if why:
        return _section(network, found, 403, refused=why)
    got = section.incident_of(network, found)
    if got["incident"] is None:
        return _section(network, found, 409, refused=got["why"])
    try:
        line = F.cancel(got["incident"], who["actor"], who["actor_verified"])      # record
    except (F.Refused, OSError, ValueError) as exc:
        return _section(network, found, 409, refused=f"Not cancelled: {exc}")
    return _section(network, found, done=(
        f"Cancelled: one line recorded, with {line['attempts']} attempt"
        f"{'s' if line['attempts'] != 1 else ''} as they stand. Nothing ran and nothing was "
        "sent; the incident stays open."))


@bp.route("/<incident_id>/fixit/retry", methods=["POST"])
def retry(incident_id):
    """Retry with more information (`section.STEPS`): the cap asked again at the press, then
    Mercury's own diagnosis re-plans; one proposal line with the person's note. No AI call."""
    from modules.fixit import section

    network, found = _found(incident_id)
    if found["found"] != "page":
        return _missing(incident_id, found)
    if _ended(found):
        return _section(network, found, 409, refused=(
            f"{incident_id} is resolved ({_ended(found)}), and its AI troubleshooting is "
            "read-only. Nothing was recorded or sent"))
    form = request.form
    try:
        got = section.retry(network, found, note=form.get("note") or "",
                            drawn_spent=form.get("drawn_spent") or "",
                            drawn_cap=form.get("drawn_cap") or "", **_person())
    except section.Refused as exc:
        return _section(network, found, exc.status, refused=str(exc))
    line = got["line"]
    if line.get("operation"):
        done = ("Re-planned by Mercury's diagnosis, with no AI: its proposal is below, checked "
                "against this incident, the heal guards and committed intent. Nothing runs "
                "until you approve it in its card.")
    else:
        done = ("Re-planned by Mercury's diagnosis, with no AI: it names no fix Mercury can "
                "run, said below. Nothing ran.")
    return _section(network, found, done=done)


@bp.route("/<incident_id>/fixit/troubleshoot", methods=["POST"])
def troubleshoot(incident_id):
    """Troubleshoot with AI (and Retry's Ask the AI to re-plan): one investigation, asked as
    the verified person who pressed, its answer checked and at most one proposal opened in its
    operation's preview (`fixit_troubleshoot.STEPS`). Refused in place, with nothing sent,
    when the incident is resolved, the press is no verified person's, the mode is off or the
    per-incident cap would be passed (naming what moved since the panel was drawn)."""
    from modules.ai import fixit_troubleshoot as AIT
    from modules.fixit import policy as P
    from modules.fixit import section

    network, found = _found(incident_id)
    if found["found"] != "page":
        return _missing(incident_id, found)
    if _ended(found):
        return _section(network, found, 409, refused=(
            f"{incident_id} is resolved ({_ended(found)}), and its AI troubleshooting is "
            "read-only. Nothing was sent"))
    who = _person()
    why = _not_a_person(who, "Troubleshoot with AI").replace("Nothing was recorded",
                                                             "Nothing was sent")
    if why:
        return _section(network, found, 403, refused=why)
    got = section.incident_of(network, found)
    inc = got["incident"]
    if inc is None:
        return _section(network, found, 409, refused=got["why"])
    cs = P.cap_state(inc, AIT.worst_usd())                                         # cap
    if cs["state"] != "allowed":
        moved = section._moved_words(request.form.get("drawn_spent") or "",
                                     request.form.get("drawn_cap") or "", cs)
        return _section(network, found, 409, refused=(
            cs["words"].replace("Retry isn't available", "Not asked", 1)
            + (f". Since the panel was drawn, {moved}" if moved else "") + ". Nothing was sent"))
    try:
        out = AIT.troubleshoot(network, found, inc, actor=who["actor"],
                               actor_verified=who["actor_verified"], person=who["person"],
                               note=request.form.get("note") or "", resolved=_resolved_at(found))
    except AIT.Refused as exc:
        return _section(network, found, exc.status, refused=str(exc))
    level = {"proposed": "muted", "gap": "warn", "no_fix": "warn", "unanswerable": "warn",
             "refused_fix": "warn", "unchecked": "warn"}.get(out["state"], "warn")
    if out["state"] == "failed" and not out["proposal"]:
        return _section(network, found, 502, refused=f"Couldn't troubleshoot: {out['words']}")
    return _section(network, found, level=level, done=out["words"],
                    typed_masked=out.get("typed_masked"))


def _teams() -> list:
    return [t for t in request.form.getlist("team") if t][:20]


@bp.route("/<incident_id>/fixit/handover", methods=["POST"])
def handover(incident_id):
    """Hand over: the write-up kept as a new version and sent to the teams ticked."""
    from modules import incident_page
    from modules.fixit import handover as H
    from modules.fixit import incident as F
    from modules.fixit import section

    network, found = _found(incident_id)
    if found["found"] != "page":
        return _missing(incident_id, found)
    if _ended(found):
        return _section(network, found, 409, refused=(
            f"{incident_id} is resolved ({_ended(found)}), and its AI troubleshooting is "
            "read-only. Nothing was recorded or sent"))
    who = _person()
    why = _not_a_person(who, "Hand over")
    if why:
        return _section(network, found, 403, refused=why)
    got = section.incident_of(network, found)
    inc = got["incident"]
    if inc is None:
        return _section(network, found, 409, refused=got["why"])
    rec = F.read(inc)
    notes = [ln.get("note") for ln in rec["lines"] if "proposal" in ln and ln.get("note")]
    teams = _teams()
    try:
        out = H.hand_over(inc, actor=who["actor"], actor_verified=who["actor_verified"],
                          note=request.form.get("note") or "", notes=notes, team_ids=teams,
                          diagnosis=section.diagnosis_of(inc),
                          advisory=[a.get("words") for a in found["advisories"][-1:]],
                          title=incident_page.title(found["incident"], found["entry"],
                                                    found["decisions"]),
                          resolved=_resolved_at(found))
    except (H.Refused, F.Refused, OSError, ValueError) as exc:
        return _section(network, found, 409, refused=f"Not handed over: {exc}")
    sent = out["sent"]
    level = "muted" if sent["ok"] else "warn"
    return _section(network, found, level=level,
                    done=f"Hand-over {out['version']} kept. {sent['words']}.",
                    resend=out["version"] if not sent["ok"] and teams else None,
                    resend_teams=teams)


@bp.route("/<incident_id>/fixit/handover/<int:version>/send", methods=["POST"])
def handover_send(incident_id, version):
    """Send again: a kept write-up sent once more to the teams it was sent to."""
    from modules.fixit import handover as H
    from modules.fixit import section

    network, found = _found(incident_id)
    if found["found"] != "page":
        return _missing(incident_id, found)
    if _ended(found):
        return _section(network, found, 409, refused=(
            f"{incident_id} is resolved ({_ended(found)}), and its AI troubleshooting is "
            "read-only. Nothing was recorded or sent"))
    who = _person()
    why = _not_a_person(who, "Send again")
    if why:
        return _section(network, found, 403, refused=why)
    got = section.incident_of(network, found)
    inc = got["incident"]
    if inc is None:
        return _section(network, found, 409, refused=got["why"])
    teams = _teams()
    try:
        chosen = H.checked_teams(network, teams)
    except H.Refused as exc:
        return _section(network, found, 409, refused=str(exc))
    sent = H.send(inc, version, [t["id"] for t in chosen])
    return _section(network, found, level="muted" if sent["ok"] else "warn",
                    done=f"Hand-over {version}: {sent['words']}.",
                    resend=version if not sent["ok"] and teams else None, resend_teams=teams)


@bp.route("/<incident_id>/handover/<int:version>", methods=["GET"])
def handover_page(incident_id, version):
    """The write-up's own page, its nine sections, linked back to the incident's page;
    ``?download=md`` gives it as Markdown. A read."""
    from modules import incident_page
    from modules.display_names import people_payload
    from modules.fixit import handover as H
    from modules.fixit import section

    network, found = _found(incident_id)
    doc, why = None, ""
    if found["found"] != "page":
        why = f"{incident_id} is no incident this network's records hold"
    else:
        got = section.incident_of(network, found)
        if got["incident"] is None:
            why = got["why"]
        else:
            kept = H.read_version(got["incident"], version)
            if kept["state"] == "ok":
                doc = people_payload(kept["doc"])
            else:
                why = kept["error"] or f"{incident_id} has no hand-over {version}"
    if doc is not None and request.args.get("download") == "md":
        return Response(doc["markdown"], mimetype="text/markdown",
                        headers={"Content-Disposition": (
                            f'attachment; filename="{incident_id}-handover-{version}.md"')})
    title = (incident_page.title(found["incident"], found["entry"], found["decisions"])
             if found["found"] == "page" else f"Incident {incident_id}")
    if doc is not None:
        # The page draws the sections; the Markdown is the download's alone.
        doc = {k: v for k, v in doc.items() if k != "markdown"}
    return _strict(render_template("v2/incident_handover.html", doc=doc, why=why,
                                   incident_id=incident_id, version=version, network=network,
                                   title=title, who=_who(), active_nav="attention"),
                   200 if doc is not None else 404)
