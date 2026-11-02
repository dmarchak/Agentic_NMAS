"""routes/intent_layers_v2.py — Source of Truth › Intent: a network's intent layers (board FC's
FC2, approved with changes 2026-11-01; PHASE8_PLAN 22.1 (8)(c); C2283), read-only in phase 1.

The layers committed under the network's `layers/` folder, in merge order, each with the
devices it reaches; the chosen one (``?layer=<key>``) with its values, each value's reach and
what overrides it, the secret references it names and its file's last commit; every same-rank
conflict, by path, with the devices it stops rendering (`modules/intent_layers_page.py`). The
region re-reads when intent is committed (`nmas:goldens`). Nothing here writes: adding, editing
and planning a layer's change are phase 2's.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("intent_layers_v2", __name__, url_prefix="/v2/intent")


def _ctx() -> dict:
    from modules import intent_layers_page
    from modules.nsot import listref
    from routes.list_param import named_list

    name = named_list(request) or listref.active().name
    known = listref.exists(name)
    chosen = (request.args.get("layer") or "").strip()
    return {"list_name": name, "known": known,
            "v": intent_layers_page.view(listref.resolve(name), chosen) if known else None}


@bp.route("", methods=["GET"])
def page():
    """FC2: the network's layers and the chosen one's values."""
    from routes.v2 import _page

    return _page("v2/intent_layers.html", active_nav="intent", **_ctx())


@bp.route("/region", methods=["GET"])
def region():
    """The page's region alone: its live redraw when intent is committed."""
    return _strict(render_template("v2/_intent_layers.html", **_ctx()))
