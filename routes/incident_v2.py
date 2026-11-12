"""routes/incident_v2.py — one incident's own page (the incident page's board, parts B and C;
the operator's design change of 2026-11-11: "each incident gets its own page").

Its first slice: ``GET /v2/incident/<id>`` for a self-healing incident (an ``hi-`` id) of the
page's network, read-only: its header with the four recorded times and TIME TO REPAIR, what is
wrong, what Mercury has done (THE stepper, from the incident's own recorded steps), what to do
(links only), the AI troubleshooting frame, its evidence and its record
(`modules/incident_page.py`).

A READ, and the only route here: it writes nothing, creates no network, starts nothing and
reaches no device. Any viewer the frame serves may open it; it draws the viewer through
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
    p = incident_page.page(ref.name, incident_id)
    if p["kind"] == "folded":
        return redirect(url_for("incident_v2.incident", incident_id=p["into"], list=ref.name),
                        code=302)
    code = 404 if p["kind"] in ("unknown", "other_kind") else 200
    return _strict(render_template("v2/incident.html", p=p, who=_who(), active_nav="attention"),
                   code)
