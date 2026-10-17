"""routes/dhcp_v2.py — SOURCE OF TRUTH › DHCP: one network's Kea (C529 step 1; board A, "Item 5,
DHCP on v2", approved 2026-10-06; docs/fidelity/dhcp.md).

A read: the DHCP reader's stored value, drawn by modules/dhcp_page.py; never a Kea call per
view. The region redraws when the reader announces `dhcp`, with its question.
"""

import logging

from flask import Blueprint, render_template, request

from modules import dhcp_page

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("dhcp_v2", __name__, url_prefix="/v2/dhcp")


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _ctx() -> dict:
    from modules import dhcp_page
    return {"g": dhcp_page.view(_list_name(), request.args)}


def _not_owner() -> str:
    """``""`` when the page's network owns the Kea a change here would write; otherwise the
    refusal, naming both networks (C1181, the operator's design 2026-10-17: a Kea has one
    owning network, where it is set; a network inheriting it changes nothing in it). Asked by
    every preview and confirm, before Kea or any file is read."""
    from modules import list_settings as L

    page = _list_name()
    try:
        owner, why = L.kea_owner(page)
    except L.ListSettingsUnreadable as exc:
        return (f"whose Kea {page}'s DHCP page shows could not be read ({exc}), so the change "
                "could not be recorded in its owner's repository. Nothing was written")
    if L.same_network(owner, page):
        return ""
    return (f"{page} uses {owner}'s Kea ({why}): a change to it is made on {owner}'s DHCP "
            f"page and recorded in {owner}'s repository, never from {page}'s. Nothing was "
            "written")


def _refused_plan(why: str) -> dict:
    """A preview refused before it was planned: the card draws why, and no confirm."""
    return {"ok": False, "refused": why}


def _refused_result(why: str) -> dict:
    """A confirm refused before anything ran (no step reached, so no stepper)."""
    return {"ok": False, "error": why}


@bp.route("", methods=["GET"])
def page():
    """The page. A read: the reader's stored value, drawn."""
    from routes.v2 import _page

    return _page("v2/dhcp.html", active_nav="dhcp", list_name=_list_name(), **_ctx())


@bp.route("/view", methods=["GET"])
def region():
    """The page's region alone: re-read when `dhcp` is announced, and asked again with a tab, a
    filter, a search or a group opened. Writes nothing."""
    return _strict(render_template("v2/_dhcp_view.html", **_ctx()))


def _op_region(op: dict, code: int = 200):
    """The Reservations tab with board B's card in place: the region for htmx, the whole page
    for a direct visit (the link without script, a bookmark)."""
    from modules import dhcp_reservations as D
    from modules.preview_confirm import confirm_part

    op = dict(op, run=dhcp_page.write_run(op.get("result")),       # THE stepper
              said=dhcp_page.write_said(op.get("result")))
    ctx = _ctx()
    ctx["g"]["s"] = dict(ctx["g"]["s"], tab="res")
    extra = dict(op=op, offered=D.OFFERED, words=D.WORDS, may=confirm_part(request, "confirm"))
    if not request.headers.get("HX-Request"):
        from routes.v2 import _page
        return _page("v2/dhcp.html", active_nav="dhcp", list_name=_list_name(), **extra,
                     **ctx), code
    return _strict(render_template("v2/_dhcp_view.html", **extra, **ctx), code)


@bp.route("/reservation", methods=["GET"])
def reservation_preview():
    """Board B's card in place of the Reservations tab: the form (Add, Edit) and, once it names
    the reservation, the preview: the change, its checks, what it does not do, and its hash.
    A read: Kea is asked and Mercury's file read; nothing is written."""
    from modules import dhcp_reservations as D

    s = D.ask(request.args)
    filled = s["op"] == "remove" or (s["family"] and s["subnet"] and s["identity"] and
                                     s["address"])
    refused = _not_owner()
    if refused:
        p = _refused_plan(refused)
    else:
        p = D.plan(_list_name(), request.args) if filled else None
    return _op_region({"state": "preview" if filled or refused else "form", "ask": s,
                       "plan": p, "subnets": _op_subnets()})


@bp.route("/reservation", methods=["POST"])
def reservation_confirm():
    """Apply the previewed change as the verified person, bound to the preview's hash: write
    Mercury's file for the subnet, reload Kea, read it back, record; the result in place."""
    from modules import dhcp_reservations as D
    from modules import identity

    actor = identity.request_actor()
    refused = _not_owner()
    got = _refused_result(refused) if refused else D.apply(
        _list_name(), request.form, request.form.get("hash", ""), actor=actor,
        reason=request.form.get("reason", ""))
    s = D.ask(request.form)
    if not got["ok"]:
        return _op_region({"state": "refused", "ask": s, "plan": got.get("plan"),
                           "result": got, "subnets": _op_subnets(),
                           "reason": request.form.get("reason", "")},
                          409 if not got.get("rolled_back") else 502)
    return _op_region({"state": "done", "ask": s, "plan": got["plan"], "result": got,
                       "actor": actor, "subnets": _op_subnets()})


# ---------------------------------------------------------------------------------- board C

def _sop_region(sop: dict, code: int = 200):
    """The Subnets tab with board C's card in place (region for htmx, the page otherwise)."""
    from modules.preview_confirm import confirm_part

    sop = dict(sop, run=dhcp_page.write_run(sop.get("result")),    # THE stepper
               said=dhcp_page.write_said(sop.get("result")))
    ctx = _ctx()
    ctx["g"]["s"] = dict(ctx["g"]["s"], tab="sub")
    sub = next((x for x in ctx["g"].get("subnets") or []
                if x.get("family") == sop["ask"]["family"]
                and str(x.get("id")) == sop["ask"]["id"]), None)
    extra = dict(sop=dict(sop, subnet=sub), may=confirm_part(request, "confirm"))
    if not request.headers.get("HX-Request"):
        from routes.v2 import _page
        return _page("v2/dhcp.html", active_nav="dhcp", list_name=_list_name(), **extra,
                     **ctx), code
    return _strict(render_template("v2/_dhcp_view.html", **extra, **ctx), code)


def _intent() -> dict:
    from modules import dhcp_page
    return (dhcp_page.stored(_list_name()).get("value") or {}).get("intent") or {}


@bp.route("/subnet", methods=["GET"])
def subnet_preview():
    """Board C's card in place of the Subnets tab: the form, and once a value is changed the
    preview (the change, the leases it affects, its checks, its hash). A read: Kea is asked and
    Mercury's subnet file read; nothing is written."""
    from modules import dhcp_subnets as S

    s = S.ask(request.args)
    filled = (s["op"] == "remove" or (s["op"] == "add" and s["prefix"] and s["pool"])
              or (s["op"] == "edit" and (any(s[k] for k in ("pool", "gateway", "dns", "domain",
                                                            "valid", "preferred"))
                                         # C709: the description is always sent once the form
                                         # is submitted; unchanged, the plan says nothing moves.
                                         or s["pool_note"] is not None)))
    refused = _not_owner()
    if refused:
        p = _refused_plan(refused)
    else:
        p = S.plan(_list_name(), request.args, intent=_intent()) if filled else None
    return _sop_region({"state": "preview" if filled or refused else "form", "ask": s,
                        "plan": p})


@bp.route("/subnet", methods=["POST"])
def subnet_confirm():
    """Apply the previewed subnet change as the verified person, bound to the preview's hash:
    Kea's own check on the candidate, Mercury's subnet file written, Kea reloaded and read back,
    recorded; the result in place."""
    from modules import dhcp_subnets as S
    from modules import identity

    actor = identity.request_actor()
    refused = _not_owner()
    got = _refused_result(refused) if refused else S.apply_edit(
        _list_name(), request.form, request.form.get("hash", ""), actor=actor,
        reason=request.form.get("reason", ""), intent=_intent())
    s = S.ask(request.form)
    if not got["ok"]:
        return _sop_region({"state": "refused", "ask": s, "plan": got.get("plan"),
                            "result": got, "reason": request.form.get("reason", "")},
                           409 if not got.get("rolled_back") else 502)
    return _sop_region({"state": "done", "ask": s, "plan": got["plan"], "result": got,
                        "actor": actor})


# ---------------------------------------------------------------------------------- board D

def _xop_region(xop: dict, code: int = 200):
    """The Exclusions tab with board D's card in place (region for htmx, the page otherwise)."""
    from modules.preview_confirm import confirm_part

    xop = dict(xop, run=dhcp_page.write_run(xop.get("result")),    # THE stepper
               said=dhcp_page.write_said(xop.get("result")))
    ctx = _ctx()
    ctx["g"]["s"] = dict(ctx["g"]["s"], tab="exc")
    extra = dict(xop=xop, may=confirm_part(request, "confirm"))
    if not request.headers.get("HX-Request"):
        from routes.v2 import _page
        return _page("v2/dhcp.html", active_nav="dhcp", list_name=_list_name(), **extra,
                     **ctx), code
    return _strict(render_template("v2/_dhcp_view.html", **extra, **ctx), code)


@bp.route("/exclusion", methods=["GET"])
def exclusion_preview():
    """Board D's card in place of the Exclusions tab: the form (Add an exclusion…, or Exclude…
    from a conflict with its reason filled from the source), and once it names a range the
    preview: the pool as set and as Kea is told, the leases on those addresses, the checks. A
    read: Kea is asked, Mercury's subnet file and the committed record read; nothing written."""
    from modules import dhcp_exclusions as E

    s = E.ask(request.args)
    filled = (s["op"] == "remove" and s["was"]) or (s["op"] == "add" and s["family"] and
                                                     s["id"] and s["range"] and s["reason"])
    refused = _not_owner()
    if refused:
        p = _refused_plan(refused)
    else:
        p = E.plan(_list_name(), request.args, intent=_intent()) if filled else None
    return _xop_region({"state": "preview" if filled or refused else "form", "ask": s,
                        "plan": p, "subnets": _op_subnets()})


@bp.route("/exclusion", methods=["POST"])
def exclusion_confirm():
    """Apply the previewed exclusion as the verified person, bound to the preview's hash: the
    subnet's pools written as the pieces through board C's write path (Kea's own check,
    config-reload, read back), the record committed; the result in place."""
    from modules import dhcp_exclusions as E
    from modules import dhcp_subnets as S
    from modules import identity

    actor = identity.request_actor()
    refused = _not_owner()
    got = _refused_result(refused) if refused else S.apply_edit(
        _list_name(), request.form, request.form.get("hash", ""), actor=actor,
        reason=request.form.get("why", "") or request.form.get("reason", ""),
        intent=_intent(), planner=E.plan, record=E.record_commit)
    s = E.ask(request.form)
    if not got["ok"]:
        return _xop_region({"state": "refused", "ask": s, "plan": got.get("plan"),
                            "result": got, "subnets": _op_subnets(),
                            "why": request.form.get("why", "")},
                           409 if not got.get("rolled_back") else 502)
    return _xop_region({"state": "done", "ask": s, "plan": got["plan"], "result": got,
                        "actor": actor, "subnets": _op_subnets()})


def _op_subnets() -> list:
    """The subnets a reservation can be made in, from the DHCP reader's stored value: every
    subnet of both families but ZTP's (onboarding's)."""
    from modules import dhcp_page

    st = dhcp_page.stored(_list_name())
    out = []
    for svc, fam in sorted(((st.get("value") or {}).get("families") or {}).items()):
        for sub in fam.get("subnets") or []:
            if not sub.get("ztp"):
                out.append({"family": fam.get("words", svc), "id": sub.get("id"),
                            "prefix": sub.get("prefix", "")})
    return out
