"""routes/network_v2.py — the network picker in every v2 page's top bar (board N, approved
2026-10-05).

"Network <name>" opens a searchable list, the person's recent networks first, each with its mode
(Default the base, standalone, inheriting, differing from Default, or its settings unreadable).
Choosing one records it for that verified person only (`modules/network_choice.py`) and opens
the same kind of page for that network, its address carrying ``?list=``; a device page opens
that network's Devices. The list is read when the picker is opened, never on every page.
"""

import logging
from urllib.parse import quote, urlsplit

from flask import Blueprint, make_response, redirect, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("network_v2", __name__, url_prefix="/v2/network")

#: Pages that belong to one device: choosing another network opens that network's Devices.
_DEVICE_PAGES = ("/v2/device/", "/v2/pending/", "/v2/retired/")


def rows(viewer_actor: str, q: str = "") -> list:
    """``[{"name", "mode", "recent"}]``: the person's recent networks first (newest first),
    then every other one by name; filtered by *q* (any part of the name, any case)."""
    from modules import integration_groups as IG
    from modules import list_settings as L
    from modules import network_choice
    from modules import settings_page

    bar = settings_page.scope_bar("")
    words = {}
    for key, said in (("standalone", "standalone"), ("differs", "differs from Default"),
                      ("inherits", "inherits")):
        for r in bar[key]:
            words[r["name"]] = said
    for name in bar["unreadable"]:
        words[name] = "its settings cannot be read"
    # Only the networks the registry holds: the base among them as the base, never a "Default"
    # an installation does not have.
    from modules.nsot import listref

    modes = {n: ("the base" if L.is_default(n) else words.get(n, "inherits"))
             for n in IG.network_names() if listref.exists(n)}
    recent = [n for n in network_choice.of(viewer_actor)["recent"] if n in modes]
    ordered = recent + sorted((n for n in modes if n not in recent), key=str.lower)
    needle = (q or "").strip().lower()
    return [{"name": n, "mode": modes[n], "recent": n in recent}
            for n in ordered if needle in n.lower()]


def target(next_path: str, name: str) -> str:
    """Where a choice goes: the same v2 page for *name* (a device's page: its Devices), only
    ever a path on this app."""
    path = urlsplit(next_path or "").path
    if not path.startswith("/v2/") or path.startswith("//"):
        path = "/v2/"
    if path.startswith(_DEVICE_PAGES):
        path = "/v2/devices"
    return f"{path}?list={quote(name)}"


@bp.app_context_processor
def _page_network():
    """Every v2 page's top bar names its network: the page's own ``list_name`` when it passes
    one (an explicit value always wins over this), else the page's network (`listref.active`).
    Settings › Installation passed none, and its top bar drew an empty name."""
    from flask import has_request_context

    if not has_request_context() or not request.path.startswith("/v2/"):
        return {}
    try:
        return {"list_name": _current()}
    except Exception:                                 # noqa: BLE001 (a page still draws)
        log.warning("network_v2: the page's network could not be read", exc_info=True)
        return {"list_name": "(unreadable)"}


def _viewer_actor() -> str:
    from modules import identity

    ident = identity.viewer()
    return ident.actor if getattr(ident, "kind", "") == "person" else ""


@bp.route("/picker", methods=["GET"])
def picker():
    """The picker's body: a search box and the list, read now."""
    return _strict(render_template("v2/_network_picker.html",
                                   rows=rows(_viewer_actor(), request.args.get("q", "")),
                                   next=request.args.get("next", "/v2/"),
                                   current=_current()))


@bp.route("/picker/items", methods=["GET"])
def picker_items():
    """The list alone, filtered by the search box."""
    return _strict(render_template("v2/_network_picker_items.html",
                                   rows=rows(_viewer_actor(), request.args.get("q", "")),
                                   next=request.args.get("next", "/v2/"),
                                   current=_current()))


def _current() -> str:
    """The page's network by NAME: drawing it builds no ref, so it creates no folder."""
    from modules.nsot import listref

    return listref.active_name()


@bp.route("/choose", methods=["POST"])
def choose():
    """Record the verified person's choice, then open the same kind of page for it."""
    from html import escape

    from modules import identity, network_choice
    from modules.nsot import listref

    name = (request.form.get("name") or "").strip()
    if not name or not listref.exists(name):
        return _strict(f'<p class="notice notice-danger">There is no network '
                       f'{escape(repr(name))}: nothing was chosen.</p>', 404)
    name = listref.resolve(name).name
    try:
        network_choice.choose(identity.request_actor(), name)
    except (network_choice.Unreadable, ValueError) as exc:
        return _strict(f'<p class="notice notice-danger">Not chosen: {escape(str(exc))}.</p>',
                       409)
    where = target(request.form.get("next", ""), name)
    if request.headers.get("HX-Request"):
        resp = make_response("", 204)
        resp.headers["HX-Redirect"] = where
        return resp
    return redirect(where, code=303)
