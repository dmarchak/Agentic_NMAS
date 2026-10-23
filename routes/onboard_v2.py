"""routes/onboard_v2.py — onboarding on v2 (cutover blocker 3, 2026-10-10; board E and the
pending page's actions, drawn under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md).

Devices › Add device…: the fields, then the plan's review (the preview component's parts: the
startup config it will boot, its operands and every refusal at once), then Create, bound to that
review's fingerprint; the plan is rebuilt under the hostname's hold and refused, naming what
moved, if it is not the one reviewed. The result says the device is PENDING and links its page.

A pending device's page: Verify… (phase 2's preview, then its confirm bound to the preview's
fingerprint), Get the bootstrap config… (a reveal, a person, recorded), and Abandon… (its dry run
drawn as the preview, the confirm bound to it). Every action is `routes/onboard.py`'s core, the
one code path (today's wizard and pending banner, which called it too, left at 7.8 on
2026-10-17, P7-25).
"""

import logging
import re

from flask import Blueprint, render_template, request
from modules.outbound import no_store

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("onboard_v2", __name__, url_prefix="/v2/onboard")

#: The form's fields, in its order; `_plan_args` reads each (tests/
#: test_server_reads_nothing_the_form_cannot_send.py holds the two to each other).
FIELDS = ("list_name", "hostname", "platform", "role", "address_source", "mgmt_ip",
          "mgmt_mask", "mgmt_mac", "manager_interface", "manager_gateway", "mgmt_interface",
          "domain", "ztp_router")


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
    # A retired device's "Onboard it again…" names it; Discovered's Pick… gives the MAC it
    # asked with, and ZTP reserves it by that MAC and serves its first config (board L: "By MAC").
    mac = (request.args.get("mac") or "").strip().lower()
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", mac):
        mac = ""
    return _add(f={"list_name": name, "address_source": "ztp" if mac else "static",
                   "mgmt_mac": mac, "hostname": (request.args.get("hostname") or "").strip()})


# ---------------------------------------------------------------------------
# Onboard devices › Discovered (board L): the discovery reader's devices, drawn.
# ---------------------------------------------------------------------------

def _discovered_ctx() -> dict:
    from modules import discovery_page
    from modules.nsot import listref
    from routes.list_param import named_list

    return {"g": discovery_page.view(named_list(request) or listref.active().name, request.args)}


@bp.route("/discovered", methods=["GET"])
def page():
    """The page. A read: the discovery reader's stored value, drawn."""
    from routes.v2 import _page

    ctx = _discovered_ctx()
    return _page("v2/onboard.html", active_nav="devices", list_name=ctx["g"]["list"], **ctx)


@bp.route("/discovered/view", methods=["GET"])
def region():
    """The page's region alone: re-read when `ztp-discovery` is announced, and asked again with a
    filter or a search. Writes nothing."""
    return _strict(render_template("v2/_onboard_discovered.html", **_discovered_ctx()))


@bp.route("/preview", methods=["POST"])
def preview():
    """The plan's review for the fields sent; creates nothing."""
    from routes.onboard import plan_of

    f = _form()
    if request.form.get("edit"):
        return _add(f=f)
    out, status = plan_of(f)
    if not out.get("ok"):
        return _add(status, f=f, refused=out.get("error") or "the plan could not be made")
    # Out-of-band ZTP's offer (O7) is its own fragment, asked for as the review draws
    # (routes/console_ztp_v2.offer_view): the review never waits on NetBox's console model.
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
                             ident.actor)
    if status != 200 and not out.get("result"):
        again, _s = plan_of(f)
        return _add(status, f=f, refused=out.get("error") or "not created",
                    pv=again if again.get("ok") else None)
    from routes.console_ztp_v2 import surveyed_offer

    # After Create: the kick-start, for a device whose console survey is recorded (O7).
    return _add(status, f=f, done=out,
                kick=surveyed_offer(f["list_name"], f["hostname"]) if out.get("ok") else None)


# ---------------------------------------------------------------------------
# A pending device's actions, drawn in place on its page.
# ---------------------------------------------------------------------------

def _pending(name: str, code: int = 200, **ctx):
    return _strict(render_template("v2/_onboard_pending.html", name=name,
                                   list_name=(request.form.get("list_name") or "").strip(),
                                   **ctx), code)


@bp.route("/<name>/actions", methods=["GET"])
def actions(name):
    """The actions at rest (Cancel), with the console card's offer when it has one (C1575)."""
    from routes.console_ztp_v2 import pending_console

    list_name = (request.args.get("list_name") or "").strip()
    return _strict(render_template("v2/_onboard_pending.html", name=name, list_name=list_name,
                                   console=pending_console(list_name, name)))


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
    # `select_data` is carried under `what.targets` only (`preview_confirm.build`; C1150).
    fp = ((((pv.get("what") or {}).get("targets")) or [{}])[0].get("select_data")
          or {}).get("fingerprint", "")
    return _pending(name, mode="verify", pv=pv, fingerprint=fp)


@bp.route("/<name>/verify", methods=["POST"])
def verify(name):
    """Verify (phase 2) as previewed, as the verified person."""
    from modules import identity
    from modules.nsot.onboard import phase_two_run
    from modules.outbound import mask_payload
    from routes.onboard import verify_run

    ident, refusal = identity.require(request, action="confirm", operation="onboard_verify")
    if refusal is not None:
        return _pending(name, 403, mode="verify", refused=refusal.get("error", ""))
    out, status = verify_run(name, request.form, ident)
    if not out.get("result"):
        return _pending(name, status, mode="verify", refused=out.get("error", ""))
    nxt = _next_intent((request.form.get("list_name") or "").strip(), name) if out.get("ok") \
        else None
    # THE stepper (the one stepper, 2026-10-12): the steps phase two reached.
    return _pending(name, status, mode="verified", nxt=nxt,
                    done=dict(out, run=mask_payload(phase_two_run(name, out))))


def _next_intent(list_name: str, name: str) -> dict:
    """Board M's step after arrival: what its committed intent says beyond what it runs, its
    first golden (``intent_match`` once, for the one device Verify just recorded). ``{state:
    deploy|write|seed|unknown, adds, why}``: lines to deploy as an ordinary deploy, an intent
    that says nothing more than the device runs (write it first), its intent the first-boot
    config only (Seed intent first, C1188: `why` is then the comparison's own words, for the
    Details toggle), or not known, with why."""
    from modules.nsot import intent_match as _im
    from modules.nsot import listref, manifest
    from modules.nsot import repo as R

    list_name = list_name or listref.active_name()
    if not listref.exists(list_name):
        # A read creates no list (tests/test_reads_create_no_list.py).
        return {"state": "unknown", "adds": 0, "why": f"no network named {list_name!r}"}
    try:
        ref = listref.resolve(list_name)
        entry = manifest.find_by_name(ref.repo_dir, name)[1]
        golden = R.committed_golden_for(ref.repo_dir, entry) if entry else {}
        if not golden.get("text"):
            return {"state": "unknown", "adds": 0,
                    "why": golden.get("refused") or "no golden is recorded for it yet"}
        im = _im.intent_match(ref.repo_dir, ref.name, name, golden["text"])
    except Exception as exc:                          # noqa: BLE001 (a read, said in place)
        log.warning("onboard_v2: %s's intent could not be compared: %s", name, exc)
        return {"state": "unknown", "adds": 0, "why": f"{type(exc).__name__}: {exc}"}
    if _im.first_boot(ref.repo_dir, name):
        return {"state": "seed", "adds": 0, "why": im.get("why") or ""}
    if im["state"] == "unknown":
        return {"state": "unknown", "adds": 0, "why": im["why"]}
    return {"state": "deploy" if im["adds"] else "write", "adds": im["adds"], "why": ""}


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
@no_store
def bootstrap(name):
    """The bootstrap config, revealed in place to a person and recorded."""
    from routes.onboard import bootstrap_reveal

    out, status = bootstrap_reveal(name, request.form, request)
    if not out.get("ok"):
        return _pending(name, status, mode="bootstrap",
                        refused=out.get("error") or out.get("reason") or "not revealed")
    return _pending(name, mode="bootstrap", config=out.get("config", ""),
                    revealed_by=out.get("revealed_by", ""))
