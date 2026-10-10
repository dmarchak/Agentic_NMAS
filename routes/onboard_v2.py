"""routes/onboard_v2.py — onboarding on v2 (cutover blocker 3, 2026-10-10; board E and the
pending page's actions, drawn under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md).

Devices › Add device…: the fields, then the plan's review (the preview component's parts: the
startup config it will boot, its operands and every refusal at once), then Create, bound to that
review's fingerprint; the plan is rebuilt under the hostname's hold and refused, naming what
moved, if it is not the one reviewed. The result says the device is PENDING and links its page.

A pending device's page: Verify… (phase 2's preview, then its confirm bound to the preview's
fingerprint), Get the bootstrap config… (a reveal, a person, recorded), and Abandon… (its dry run
drawn as the preview, the confirm bound to it). Every action is `routes/onboard.py`'s core, the
one code path today's wizard and banner call too.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("onboard_v2", __name__, url_prefix="/v2/onboard")

#: The form's fields, in its order; `_plan_args` reads each (tests/
#: test_server_reads_nothing_the_form_cannot_send.py holds the two to each other).
FIELDS = ("list_name", "hostname", "platform", "role", "address_source", "mgmt_ip",
          "mgmt_mask", "mgmt_mac", "manager_interface", "manager_gateway", "mgmt_interface",
          "domain")


def _form() -> dict:
    """The fields as sent, each one the form has; the inventory source is the network's own."""
    out = {k: (request.form.get(k) or "").strip() for k in FIELDS}
    out["source_kind"] = _source_kind(out["list_name"])
    return out


def _source_kind(list_name: str) -> str:
    """``local`` or ``netbox``: the network's configured inventory source, never the form's."""
    if not list_name:
        return "local"
    try:
        from modules.inventory.source_config import load

        return load(list_name).get("source") or "local"
    except Exception as exc:                          # noqa: BLE001 (refused by the plan)
        log.warning("onboard_v2: the inventory source of %r could not be read: %s",
                    list_name, exc)
        return "local"


def _add(code: int = 200, **ctx):
    from routes.onboard import platform_choices

    return _strict(render_template("v2/_onboard_add.html", platforms=platform_choices(),
                                   **ctx), code)


@bp.route("/new", methods=["GET"])
def new():
    """Add device…: the form, for the network named (the page's own)."""
    from modules.nsot import listref

    name = (request.args.get("list") or "").strip() or listref.active_name()
    # A retired device's "Onboard it again…" names it.
    return _add(f={"list_name": name, "address_source": "static",
                   "hostname": (request.args.get("hostname") or "").strip()})


@bp.route("/preview", methods=["POST"])
def preview():
    """The plan's review for the fields sent; creates nothing."""
    from routes.onboard import plan_of

    f = _form()
    if request.form.get("edit"):
        return _add(f=f)
    out, status = plan_of(f, bound=True)
    if not out.get("ok"):
        return _add(status, f=f, refused=out.get("error") or "the plan could not be made")
    return _add(f=f, pv=out)


@bp.route("/create", methods=["POST"])
def create():
    """Create as reviewed, as the verified person; phase 1 reaches no device."""
    from modules import identity
    from routes.onboard import create_run, plan_of

    f = _form()
    ident, refusal = identity.require(request, action="approve", operation="onboard_device")
    if refusal is not None:
        return _add(403, f=f, refused=refusal.get("error", "a person must create"))
    out, status = create_run(dict(f, shown=request.form.get("shown", ""),
                                  fingerprint=request.form.get("fingerprint", "")),
                             ident.actor, bound=True)
    if status != 200 and not out.get("result"):
        again, _s = plan_of(f, bound=True)
        return _add(status, f=f, refused=out.get("error") or "not created",
                    pv=again if again.get("ok") else None)
    return _add(status, f=f, done=out)


# ---------------------------------------------------------------------------
# A pending device's actions, drawn in place on its page.
# ---------------------------------------------------------------------------

def _pending(name: str, code: int = 200, **ctx):
    return _strict(render_template("v2/_onboard_pending.html", name=name,
                                   list_name=(request.form.get("list_name") or "").strip(),
                                   **ctx), code)


@bp.route("/<name>/actions", methods=["GET"])
def actions(name):
    """The actions at rest (Cancel)."""
    return _strict(render_template("v2/_onboard_pending.html", name=name,
                                   list_name=(request.args.get("list_name") or "").strip()))


@bp.route("/<name>/verify/preview", methods=["POST"])
def verify_preview(name):
    """Verify's preview: reaches the device with its staged credential and reads it; sends
    nothing."""
    from routes.onboard import verify_preview_of

    out, status = verify_preview_of(name, request.form, request)
    if not out.get("ok"):
        return _pending(name, status, mode="verify", refused=out.get("error", ""),
                        causes=out.get("causes") or [])
    pv = out["preview"]
    fp = ((pv.get("targets") or [{}])[0].get("select_data") or {}).get("fingerprint", "")
    return _pending(name, mode="verify", pv=pv, fingerprint=fp)


@bp.route("/<name>/verify", methods=["POST"])
def verify(name):
    """Verify (phase 2) as previewed, as the verified person."""
    from modules import identity
    from routes.onboard import verify_run

    ident, refusal = identity.require(request, action="confirm", operation="onboard_verify")
    if refusal is not None:
        return _pending(name, 403, mode="verify", refused=refusal.get("error", ""))
    out, status = verify_run(name, request.form, ident)
    if not out.get("result"):
        return _pending(name, status, mode="verify", refused=out.get("error", ""))
    return _pending(name, status, mode="verified", done=out)


@bp.route("/<name>/abandon/preview", methods=["POST"])
def abandon_preview(name):
    """Abandon's dry run: what it would remove, step by step; removes nothing."""
    from modules import identity
    from modules.nsot.onboard import abandon_fingerprint
    from modules.preview_confirm import confirm_part
    from routes.onboard import abandon_run

    out, status = abandon_run(name, dict(request.form.items(), dry_run="1"),
                              identity.request_actor() or "")
    if not out.get("steps"):
        return _pending(name, status if status != 200 else 409, mode="abandon",
                        refused=out.get("error") or "nothing to abandon")
    return _pending(name, mode="abandon", dry=out, fingerprint=abandon_fingerprint(out),
                    may=confirm_part(request))


@bp.route("/<name>/abandon", methods=["POST"])
def abandon(name):
    """Abandon as previewed, as the verified person."""
    from modules import identity
    from routes.onboard import abandon_run

    ident, refusal = identity.require(request, action="confirm", operation="onboard_abandon")
    if refusal is not None:
        return _pending(name, 403, mode="abandon", refused=refusal.get("error", ""))
    fingerprint = (request.form.get("fingerprint") or "").strip()
    if not fingerprint:
        return _pending(name, 400, mode="abandon", refused=(
            "Abandon confirms what its preview showed, and no preview fingerprint was sent: "
            "preview first"))
    out, status = abandon_run(name, request.form, ident.actor, confirmed=fingerprint)
    if not out.get("result"):
        return _pending(name, status, mode="abandon", refused=out.get("error", ""))
    return _pending(name, status, mode="abandoned", done=out)


@bp.route("/<name>/bootstrap", methods=["POST"])
def bootstrap(name):
    """The bootstrap config, revealed in place to a person and recorded."""
    from routes.onboard import bootstrap_reveal

    out, status = bootstrap_reveal(name, request.form, request)
    if not out.get("ok"):
        return _pending(name, status, mode="bootstrap",
                        refused=out.get("error") or out.get("reason") or "not revealed")
    return _pending(name, mode="bootstrap", config=out.get("config", ""),
                    revealed_by=out.get("revealed_by", ""))
