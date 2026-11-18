"""routes/incident_v2.py — one incident's own page (the incident page's board, parts B and C;
the operator's design change of 2026-11-11: "each incident gets its own page").

Its first slice: ``GET /v2/incident/<id>`` for a self-healing incident (an ``hi-`` id) of the
page's network, read-only: its header with the four recorded times and TIME TO REPAIR, what is
wrong, what Mercury has done (THE stepper, from the incident's own recorded steps), what to do
(the page's one state in words and, while a person is needed, the ONE action its Needs
attention item offers, as the page's primary button; the GUI review's item 2, C3450), the AI
troubleshooting frame, its evidence and its record (`modules/incident_page.py`).

A READ, as its one part is (``GET /v2/incident/<id>/step``, the investigation's live step on the
status line, board R5's screen 3): it writes nothing, creates no network, starts nothing and
reaches no device. The action's own card (a proposal's, a Re-subscribe's) is its operation's
route, read when its button is pressed. Any viewer the frame serves may open it; it draws the viewer through
`identity.viewer()` and carries the strict policy.

- A closed incident folded into another answers 302 to the surviving incident's page.
- An id no store holds is a 404 on the frame, saying so; an id of another kind (an alert
  group's, an SDN response's) is a 404 saying its page comes with a later slice.
- A record that could not be read is a 200 that says so: absent and unreadable differ.
"""

import logging

from flask import Blueprint, redirect, render_template, url_for

from routes.device_v2 import _page_ref, _strict, _who

log = logging.getLogger(__name__)

bp = Blueprint("incident_v2", __name__, url_prefix="/v2/incident")


@bp.route("/<incident_id>", methods=["GET"])
def incident(incident_id):
    """One incident's page, for the page's network."""
    from modules import incident_page

    ref = _page_ref()
    # Needs attention's list as it is drawn for this request (the value the background holds,
    # masked, a run's hold marked): the incident's own item on it carries the page's action.
    # Asked for only by an id that has a page.
    from modules import server_timing
    from routes.v2 import _attention, with_heal_analysis
    p = incident_page.page(ref.name, incident_id, attention=_attention)
    if p["kind"] == "page":
        # A can't-fix's AI analysis in full, in the AI troubleshooting section (C3488).
        with server_timing.timed("heal analysis"):
            with_heal_analysis(p["fixit"])
    if p["kind"] == "folded":
        return redirect(url_for("incident_v2.incident", incident_id=p["into"], list=ref.name),
                        code=302)
    code = 404 if p["kind"] in ("unknown", "other_kind") else 200
    # Its home is Troubleshooting › Incidents (board T; provisional, operator review pending).
    with server_timing.timed("render"):
        html = render_template("v2/incident.html", p=p, who=_who(), active_nav="incidents")
    return _strict(html, code)


@bp.route("/<incident_id>/step", methods=["GET"])
def step(incident_id):
    """The incident's running investigation's live step (board R5's screen 3, approved
    2026-11-15: `troubleshoot_job.shown`), its status line's part redrawn when the job
    announces ``ai_step``. A read of this process's memory: it waits on nothing and writes
    nothing; no step kept (none runs, or another process runs it) draws the part empty."""
    from modules import incident_page
    from modules.fixit import incident as F
    from modules.fixit import progress

    ref = _page_ref()
    steps = []
    if F.valid_id(incident_id):
        # The live stepper (the operator, 2026-11-16): the investigation's, else the run's (an
        # approved plan's, or a saved script's, 2026-11-15).
        found = incident_page.resolve(ref.name, incident_id)
        device = (found.get("incident") or {}).get("device") or ""
        # An approved plan running in another process: its record's steps (`recorded`).
        steps = (progress.investigation(ref.name, incident_id)
                 or progress.run(ref.name, incident_id, device)
                 or progress.recorded(ref.name, found, device, running=True))
    said = ""
    if F.valid_id(incident_id) and not steps:
        # C3913: the investigation just ended, its section not redrawn yet: the next state's
        # words in place of an empty part (the card was its title alone), from the record.
        said = _settled_words(ref.name, found)
    return _strict(render_template("v2/_inc_step.html", iid=incident_id, network=ref.name,
                                   steps=steps, said=said), 200)


def _settled_words(network: str, found: dict) -> str:
    """The words of an AI investigation's answer kept in the last `investigation_bound_s`
    (the newest line of the incident's record, newer than its newest start): "Plan ready:
    approve it below" for a plan, else its own first sentence; ``""`` otherwise. A read."""
    import time
    from modules.fixit import incident as F
    from modules.fixit import section as S

    try:
        inc = S.incident_of(network, found).get("incident")
        lines = F.read(inc)["lines"] if inc is not None else []
    except Exception:                                 # noqa: BLE001 (drawn without it)
        return ""
    newest = lines[-1] if lines else {}
    if "proposal" not in newest or newest.get("source") != "ai" or \
            time.time() - float(newest.get("epoch") or 0) > S.investigation_bound_s():
        return ""
    if newest.get("steps"):
        # Never "ready to approve": a plan its preflight refused is drawn below as not
        # approvable (the review of round 1), so the words claim only that it is there.
        return "The AI's plan is below"
    return S._first_sentence(newest.get("words") or "", S.FINDING_CHARS)
