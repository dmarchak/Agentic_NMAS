"""routes/incidents_v2.py — Troubleshooting › Incidents, the incident's own home (board T, the
sidebar's Troubleshooting section; ~/Documents/nmas-reports/boards/troubleshooting-nav.html,
parts 1, 2 and 4; the GUI review's proposal 17 and finding IN9). Provisional, operator review
pending (the operator, 2026-11-13).

Two reads, and nothing else: they write nothing, create no network, start nothing and reach
no device (`modules/incidents_list.py` says what each reads).

- ``GET /v2/incidents``: the list, its Open and Closed tabs (``tab``), a search (``q``) and a
  device filter (``device``), for the page's network (``list``). Every row opens the incident's
  own page, `/v2/incident/<id>`.
- ``GET /v2/incidents/heal-auto``: the top bar's Self-healing chip, drawn only while some
  network's self-healing runs in Auto ("Self-healing: Auto until <local time>"), nothing in dry
  run or off (the operator, 2026-11-14: the sidebar is navigation only; status lives in the top
  bar, by exception). The sidebar's two chips it replaces (Incidents' "N open", Self-healing's
  mode) are gone: Needs attention's badge is the one count.

Each draws the viewer through `identity.viewer()` and carries the strict policy.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _page_ref, _strict, _who

log = logging.getLogger(__name__)

bp = Blueprint("incidents_v2", __name__, url_prefix="/v2/incidents")


@bp.route("", methods=["GET"])
def page():
    """The incidents list, for the page's network, the control strip (C3748) above it."""
    from modules import control_strip, incidents_list

    ref = _page_ref()
    p = incidents_list.page(ref.name, request.args.get("tab") or "open",
                            request.args.get("q") or "", request.args.get("device") or "")
    return _strict(render_template("v2/incidents.html", p=p, who=_who(),
                                   active_nav="incidents",
                                   strip=control_strip.view(ref.name)))


@bp.route("/heal-auto", methods=["GET"])
def heal_auto():
    """The top bar's Self-healing chip: drawn only while some network runs in Auto (the
    operator, 2026-11-14); nothing at all in dry run or off. Whether Auto is in force that
    could not be read at all is said, never drawn as nothing."""
    from modules import incidents_list

    try:
        a = dict(incidents_list.heal_auto(), error="")
    except Exception as exc:                            # noqa: BLE001 (the top bar still draws)
        log.warning("incidents: whether self-healing runs in Auto could not be read (%s)",
                    type(exc).__name__)
        a = {"on": False, "network": "", "until": "", "n": 0, "networks": [], "reread_s": 0,
             "error": f"whether any network's self-healing runs in Auto could not be read "
                      f"({type(exc).__name__})"}
    return _strict(render_template("v2/_heal_auto_chip.html", a=a))
