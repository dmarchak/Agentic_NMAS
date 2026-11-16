"""routes/fixes_v2.py — Troubleshooting › Fixes and a fix's own page (C3849 pieces 2 to 4;
boards docs/boards/fixes-list.html and docs/boards/fix-bpdu-guard.html, approved by the
operator 2026-11-16 with changes), drawn from `modules/fix_page.py`.

- ``GET /v2/fixes``: every fix the page's network has, saved and built-in, grouped, each group
  its first 20 rows and the rest counted; ``q``, ``mode`` and ``kind`` filter on the server.
- ``GET /v2/fixes/<key>``: one fix's page: its BLUF with Run…, then Contents, Origin, Record
  and How it runs, folded. A built-in's is read-only.
- ``GET /v2/fixes/<key>/run``: Run…'s card in place: a device and a port chosen from what
  Mercury holds (never a device read), the runner's own preview, and Run posting to the
  EXISTING run path (`fixit_v2.fix_with_script` on the matched incident, or
  `saved_plans_v2.device_run`), each answering here through `run_answer` when asked with
  ``view=fix``. ``close=1`` draws the slot empty (Cancel); ``run=<id>`` the run's state.

- ``POST /v2/fixes/<key>/delete`` and ``/restore`` (Delete… and Restore… inside How it
  runs, the operator, 2026-11-16): the saved fix kept, marked deleted or restored with the
  verified person's reason (`saved_plans.retire`), answered by the fold in place; History
  draws each (`history_sources.saved_fixes`). Neither sends anything to a device.

Every GET here is a read: nothing is written, no network is created and no device is asked.
Each draws the viewer through `identity.viewer()` and carries the strict policy.
"""

import logging

from flask import Blueprint, abort, render_template, request

from routes.device_v2 import _page_ref, _strict, _who, carry_list

log = logging.getLogger(__name__)

bp = Blueprint("fixes_v2", __name__, url_prefix="/v2/fixes")
bp.url_defaults(carry_list)       # the page's network on every URL it draws (C494)


@bp.route("", methods=["GET"])
def page():
    """Troubleshooting › Fixes, for the page's network."""
    from modules import fix_page

    ref = _page_ref()
    a = request.args
    mode = (a.get("mode") or "").strip()
    kind = (a.get("kind") or "").strip()
    p = fix_page.listing(ref.name, q=(a.get("q") or "").strip()[:80],
                         mode=mode if mode in fix_page.MODES else "",
                         kind=kind if kind in ("saved", "builtin", "deleted") else "")
    return _strict(render_template("v2/fixes.html", p=p, who=_who(), active_nav="fixes"))


@bp.route("/<key>", methods=["GET"])
def fix(key):
    """One fix's page, for the page's network; a key it does not hold is a 404 saying so."""
    from modules import fix_page

    from routes.saved_plans_v2 import _who as person

    ref = _page_ref()
    key = str(key)[:64]
    p = fix_page.page(ref.name, key)
    form = fix_page.delete_form(ref.name, key, person()) if p["kind"] == "saved" else None
    return _strict(render_template("v2/fix.html", p=p, form=form, said={}, who=_who(),
                                   active_nav="fixes"),
                   404 if p["kind"] == "unknown" else 200)


def _right() -> str:
    """The viewer's refusal for running a plan (`identity.right_refusal`, ``run_plan``), or
    ``""``: the Run button is drawn disabled with it."""
    from modules import identity
    from routes.saved_plans_v2 import _who as who

    return identity.right_refusal("run_plan", **who())


@bp.route("/<key>/run", methods=["GET"])
def run(key):
    """Run…'s card in place (a read: the runner's own preview, asking no device)."""
    from modules import fix_page

    ref = _page_ref()
    a = request.args
    key = str(key)[:64]
    if a.get("close") == "1":
        return _strict(render_template("v2/_fix_run.html", c={"state": "closed", "key": key,
                                                              "network": ref.name}))
    if a.get("run"):
        return run_answer(ref.name, key, run=(a.get("run") or "").strip())
    if fix_page.find(ref.name, key)["kind"] == "unknown":
        abort(404)
    c = fix_page.run_card(ref.name, key, device=(a.get("device") or "").strip(),
                          interface=(a.get("interface") or "").strip(), right=_right())
    return _strict(render_template("v2/_fix_run.html", c=c))


def _how(network: str, key: str, code: int = 200, **said):
    """The How it runs fold drawn again in place, its Delete… or Restore… answer leading it."""
    from modules import fix_page
    from routes.saved_plans_v2 import _who as who

    p = fix_page.page(network, key)
    return _strict(render_template("v2/_fix_how.html", p=p, form=fix_page.delete_form(
        network, key, who()), said=said, open_fold=True), code)


def _delete_or_restore(key: str, restore: bool):
    from modules.nsot import saved_plans as S
    from routes.saved_plans_v2 import _who as who

    ref = _page_ref()
    key = str(key)[:64]
    try:
        f = S.retire(key, network=ref.name, reason=(request.form.get("reason") or ""),
                     restore=restore, **who())
    except S.Refused as exc:
        return _how(ref.name, key, 403 if "may not" in str(exc) or "does not hold" in str(exc)
                    or "verified person" in str(exc) else 409, level="danger",
                    words=f"Not {'restored' if restore else 'deleted'}: {exc}")
    log.info("fixes: %s %s on %s", key, "restored" if restore else "deleted", ref.name)
    return _how(ref.name, key, level="ok", words=(
        f"Restored {f.get('name') or key}: offered, matched and run as before" if restore else
        f"Deleted {f.get('name') or key}: no longer offered, matched or run, and not in the "
        "AI's catalog. Its record, origin and runs are kept here; Restore… brings it back"))


@bp.route("/<key>/delete", methods=["POST"])
def delete(key):
    """Delete… a saved fix (the operator, 2026-11-16): kept in the store, never removed, marked
    deleted with the verified person's reason (`saved_plans.retire`); History draws it."""
    return _delete_or_restore(key, restore=False)


@bp.route("/<key>/restore", methods=["POST"])
def restore(key):
    """Restore… a deleted saved fix, with the person's reason; both kept on the fix."""
    return _delete_or_restore(key, restore=True)


def run_answer(network: str, key: str, code: int = 200, *, incident: str = "",
               device: str = "", interface: str = "", run: str = "", refused: str = "",
               done: str = "", level: str = "", words: str = "", **_said):
    """The answer of the existing run path pressed on a fix's page (``view=fix``): its refusal
    or its start, drawn on the page's run card; a run's state from its own record while it
    runs. Called by `fixit_v2.fix_with_script` and `saved_plans_v2._device_draw`."""
    from modules import fix_page

    said = refused or done or words
    if incident and said.startswith(incident):
        # No raw ids on the fix's page (the operator's change 3): the incident is linked.
        said = "The incident" + said[len(incident):]
    c = {"state": "answer", "key": key, "network": network, "device": device,
         "interface": interface, "incident": incident,
         "level": "danger" if refused or level == "danger" else "ok",
         "words": said.replace(incident, "the incident") if incident else said, "run": None}
    if run:
        c.update(state="run", run=fix_page.run_state(network, run))
    return _strict(render_template("v2/_fix_run.html", c=c), code)
