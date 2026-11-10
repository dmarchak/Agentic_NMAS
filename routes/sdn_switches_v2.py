"""routes/sdn_switches_v2.py — OBSERVE › SDN › Switches (board docs/boards/lab9-sdn.html,
artboard A, self-signed 2026-11-10; Lab 9 Objective 2; C2902).

The tab is a read of stored state (modules/sdn_switches_page.py): the committed NSOT export, the
SDN reader's stored switch list and the network's SDN operation record; never a switch or a
controller call per view. Its region redraws when the SDN reader announces `sdn`.

Its operations, each a card drawn in place:
- **Configure from NetBox…** (`configure_preview`, `configure_confirm`): the OpenFlow
  configuration (`modules/sdn/openflow_config.py`) of the switches chosen, or of every one that
  differs: each switch's exact program, the export it read, its verify, its undo and the hash;
  confirmed by that hash as a verified person, each switch planned again, held, sent, verified,
  rolled back on failure and recorded; the result per switch in the card's place.
- **Confirm against a capture…** (`template_preview`, `template_confirm`): a template beside a
  saved capture of one of its devices, committed as the verified person
  (`openflow_templates.confirm`), bound to both hashes.
- **Verify now** (`verify`): the SDN reader asked to read the controllers again now; the tab
  redraws when it has.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("sdn_switches_v2", __name__, url_prefix="/v2/sdn/switches")


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _ctx() -> dict:
    from modules import sdn_page, sdn_switches_page
    from routes.sdn_v2 import TABS

    network = _list_name()
    g = sdn_switches_page.switches_view(network, {
        "q": request.args.get("q") or "", "state": request.args.get("state") or "",
        "platform": request.args.get("platform") or ""})
    return {"g": g, "tabs": TABS, "fresh": sdn_page.redraw_promise()}


@bp.route("", methods=["GET"])
def page():
    """SDN › Switches (board lab9-sdn, artboard A). A read."""
    from routes.v2 import _page

    return _page("v2/sdn_switches.html", active_nav="sdn", list_name=_list_name(), **_ctx())


@bp.route("/view", methods=["GET"])
def region():
    """The tab's region alone: re-read when `sdn` is announced, and asked again with a filter.
    Writes nothing."""
    return _strict(render_template("v2/_sdn_switches.html", **_ctx()))


@bp.route("/slot", methods=["GET"])
def slot():
    """An operation card's slot, empty: Cancel and Close draw it again. A read."""
    which = "of-template-op" if request.args.get("card") == "template" else "of-config-op"
    return _strict(render_template("v2/_sdn_of_slot.html", which=which))


def _network() -> tuple:
    from routes.list_param import submitted_list

    return submitted_list(request)


def _card(template: str, d: dict, status: int = 200):
    return _strict(render_template(template, d=d)), status


# --------------------------------------------------------------------------- the templates

@bp.route("/template/preview", methods=["POST"])
def template_preview():
    """Confirm against a capture…: the template's lines beside the capture's masked text and
    the two hashes the confirm binds. Writes nothing."""
    from modules import sdn_switches_page

    network, refused = _network()
    if refused:
        return _card("v2/_sdn_of_template.html", {"state_card": "refused", "network": network,
                                                  "error": refused}, 400)
    d = sdn_switches_page.template_preview(network, (request.form.get("template") or "").strip(),
                                           (request.form.get("capture") or "").strip())
    return _card("v2/_sdn_of_template.html", d, 200 if d["state_card"] == "preview" else 409)


@bp.route("/template/confirm", methods=["POST"])
def template_confirm():
    """Commit the template's confirmation as the verified person, bound to the template's and
    the capture's hashes as previewed; a moved one is refused naming both."""
    from modules import identity
    from modules.sdn import openflow_templates as T

    network, refused = _network()
    if refused:
        return _card("v2/_sdn_of_template.html", {"state_card": "refused", "network": network,
                                                  "error": refused}, 400)
    actor = identity.request_actor()
    name = (request.form.get("template") or "").strip()
    capture = (request.form.get("capture") or "").strip()
    got = T.confirm(network, name, capture, actor, identity.actor_verification(actor),
                    template_sha256=(request.form.get("template_sha256") or "").strip(),
                    capture_sha256=(request.form.get("capture_sha256") or "").strip())
    if not got["ok"]:
        return _card("v2/_sdn_of_template.html", {"state_card": "refused", "network": network,
                                                  "template": name, "error": got["error"]}, 409)
    return _card("v2/_sdn_of_template.html", {"state_card": "confirmed", "network": network,
                                              "template": name, "capture": capture,
                                              "path": got["path"], "commit": got["commit"],
                                              "actor": actor})


# --------------------------------------------------------------------------- configure

@bp.route("/configure/preview", methods=["POST"])
def configure_preview():
    """Configure from NetBox… (or Preview the fix… on a row): each chosen switch planned from
    the committed NSOT export and its own running configuration, read only. Writes nothing."""
    from modules import sdn_switches_page

    network, refused = _network()
    if refused:
        return _card("v2/_sdn_of_config.html", {"state_card": "refused", "network": network,
                                                "error": refused}, 400)
    chosen = [d.strip() for d in request.form.getlist("device") if d.strip()]
    if not chosen:
        view = sdn_switches_page.switches_view(network)
        chosen = [r["name"] for r in view["rows"] if r["state"] != "connected"]
    if not chosen:
        return _card("v2/_sdn_of_config.html", {
            "state_card": "refused", "network": network,
            "error": "every switch marked for OpenFlow is connected as intended, and none was "
                     "chosen: nothing to configure"}, 409)
    return _card("v2/_sdn_of_config.html", sdn_switches_page.configure_preview(network, chosen))


@bp.route("/configure/confirm", methods=["POST"])
def configure_confirm():
    """Configure the previewed switches as the verified person, bound to the preview's hash;
    each switch planned again and its own hash compared, held, sent, verified, rolled back on
    failure and recorded. The result per switch in the card's place."""
    from modules import identity, sdn_switches_page

    network, refused = _network()
    if refused:
        return _card("v2/_sdn_of_config.html", {"state_card": "refused", "network": network,
                                                "error": refused}, 400)
    actor = identity.request_actor()
    pairs = []
    for item in request.form.getlist("plan"):
        device, _sep, h = item.partition("=")
        if device.strip() and h.strip():
            pairs.append((device.strip(), h.strip()))
    d = sdn_switches_page.configure_apply(network, pairs, (request.form.get("hash") or "").strip(),
                                          actor=actor,
                                          actor_verified=identity.actor_verification(actor))
    return _card("v2/_sdn_of_config.html", d, 409 if d["state_card"] == "refused" else 200)


@bp.route("/verify", methods=["POST"])
def verify():
    """Verify now: the SDN reader reads the network's controllers again now (its own run, as its
    schedule would); the tab redraws when it announces. Sends nothing to a switch."""
    from modules import identity, reader_job
    from modules.readers import sdn_controllers

    if not reader_job.running(sdn_controllers.READER_NAME):
        words = ("the reader jobs do not run in this process, so nothing was read; the SDN "
                 "reader reads every 30 seconds where they run")
        return _strict(render_template("v2/_sdn_of_verify.html", started=False, words=words)), 409
    got = reader_job.request_run(sdn_controllers.READER, identity.request_actor(),
                                 announce=reader_job.announce_via_page)
    return _strict(render_template("v2/_sdn_of_verify.html", started=True, words=(
        "reading the controllers now" if got["started"] else
        "a read is already running; this tab redraws when it ends")))
