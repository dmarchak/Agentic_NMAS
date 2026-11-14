"""routes/incidents_v2.py — Troubleshooting › Incidents, the incident's own home (board T, the
sidebar's Troubleshooting section; ~/Documents/nmas-reports/boards/troubleshooting-nav.html,
parts 1, 2 and 4; the GUI review's proposal 17 and finding IN9). Provisional, operator review
pending (the operator, 2026-11-13).

Three reads, and nothing else: they write nothing, create no network, start nothing and reach
no device (`modules/incidents_list.py` says what each reads).

- ``GET /v2/incidents``: the list, its Open and Closed tabs (``tab``), a search (``q``) and a
  device filter (``device``), for the page's network (``list``). Every row opens the incident's
  own page, `/v2/incident/<id>`.
- ``GET /v2/incidents/count``: the sidebar's Incidents chip, the open incidents ("3 open").
- ``GET /v2/incidents/heal-mode``: the sidebar's Self-healing chip, the mode that runs now
  (Off, Dry run or Auto).

Each draws the viewer through `identity.viewer()` and carries the strict policy.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _page_ref, _strict, _who

log = logging.getLogger(__name__)

bp = Blueprint("incidents_v2", __name__, url_prefix="/v2/incidents")


@bp.route("", methods=["GET"])
def page():
    """The incidents list, for the page's network."""
    from modules import incidents_list

    ref = _page_ref()
    p = incidents_list.page(ref.name, request.args.get("tab") or "open",
                            request.args.get("q") or "", request.args.get("device") or "")
    return _strict(render_template("v2/incidents.html", p=p, who=_who(),
                                   active_nav="incidents"))


@bp.route("/count", methods=["GET"])
def count():
    """The sidebar's Incidents chip: the page's network's open incidents."""
    from modules import incidents_list

    try:
        c = incidents_list.open_count(_page_ref().name)
    except Exception as exc:                            # noqa: BLE001 (the sidebar still draws)
        log.warning("incidents: the open count could not be read (%s)", type(exc).__name__)
        c = {"n": 0, "ok": False}
    return _strict(render_template("v2/_incidents_chip.html", chip="count", c=c))


@bp.route("/heal-mode", methods=["GET"])
def heal_mode():
    """The sidebar's Self-healing chip: the page's network's mode as it runs now."""
    from modules import incidents_list

    try:
        m = incidents_list.heal_mode(_page_ref().name)
    except Exception as exc:                            # noqa: BLE001 (the sidebar still draws)
        log.warning("incidents: the heal mode could not be read (%s)", type(exc).__name__)
        m = {"mode": "off", "words": "", "why": "the mode could not be read"}
    return _strict(render_template("v2/_incidents_chip.html", chip="mode", m=m))
