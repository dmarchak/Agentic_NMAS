"""routes/fixes_v2.py — Troubleshooting › Fixes and a fix's own page (C3849 pieces 2 to 4;
boards docs/boards/fixes-list.html and docs/boards/fix-bpdu-guard.html, approved by the
operator 2026-11-16 with changes), drawn from `modules/fix_page.py`.

- ``GET /v2/fixes``: every fix the page's network has, saved and built-in, grouped, each group
  its first 20 rows and the rest counted; ``q``, ``mode`` and ``kind`` filter on the server.
- ``GET /v2/fixes/<key>``: one fix's page: its BLUF with Run…, then Contents, Origin, Record
  and How it runs, folded. A built-in's is read-only; a built-in command plan's has Run…, the
  same card and run paths as a saved fix's (the operator, 2026-11-17).
- ``GET /v2/fixes/<key>/run``: Run…'s card in place: a device and a port chosen from what
  Mercury holds (never a device read), the runner's own preview, and Run posting to the
  EXISTING run path (`fixit_v2.fix_with_script` on the matched incident, or
  `saved_plans_v2.device_run`), each answering here through `run_answer` when asked with
  ``view=fix``. ``close=1`` draws the slot empty (Cancel); ``run=<id>`` the run's state.

- ``GET``/``POST /v2/fixes/new`` (New fix…, board fix-manual-controls screen 2), ``GET``/``POST
  /v2/fixes/<key>/edit`` (Edit… in the Contents fold, screen 3) and ``POST
  /v2/fixes/<key>/automatic`` (Set Automatic… in How it runs): the form drawn in place as each
  choice changes (`fix_editor.card`, a read: the runner's own preview of the draft), saved by
  `saved_plans.new_fix`, `edit_fix` and `promote`. A new fix starts Manual only; a change to
  what runs is a new version. None sends anything to a device. Run… (screen 1) is above:
  "Run on an open incident…" posts to `fixit_v2.fix_with_script`, "Or choose a device and
  interface…" to `saved_plans_v2.device_run`.

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
    from modules import server_timing
    with server_timing.timed("fixes listing"):
        p = fix_page.listing(ref.name, q=(a.get("q") or "").strip()[:80],
                             mode=mode if mode in fix_page.MODES else "",
                             kind=kind if kind in ("saved", "builtin", "deleted") else "")
    with server_timing.timed("render"):
        html = render_template("v2/fixes.html", p=p, who=_who(), active_nav="fixes")
    return _strict(html)


def _new_form(network: str, code: int = 200, form=None, **said):
    """New fix…'s card in place (`fix_editor.card`), its answer leading it when *said*."""
    from modules import fix_editor
    from routes.saved_plans_v2 import _who as person

    c = fix_editor.card(network, form, who=person())
    return _strict(render_template("v2/_fix_form.html", c=fix_editor.drawn(c), said=said),
                   code)


@bp.route("/new", methods=["GET"])
def new():
    """New fix… on the Fixes page (board fix-manual-controls screen 2): its form in place,
    drawn again as each choice changes (``drafted=1``, the form as it sends itself), with the
    runner's own preview of the draft on an example (asking no device). ``close=1`` draws the
    slot empty (Cancel). A read: nothing is written."""
    ref = _page_ref()
    if request.args.get("close") == "1":
        return _strict('<div id="fix-new" hidden></div>')
    return _new_form(ref.name, form=request.args)


@bp.route("/new", methods=["POST"])
def new_save():
    """Save as Manual only (board fix-manual-controls screen 2): the draft the form sends,
    built again here (`fix_editor.build`) and saved as one fix of the page's network
    (`saved_plans.new_fix`): Manual only, settable Automatic after its first verified run.
    The self-healing right with a match, the admin right without; the AI none. A shape not
    measured is held provisional for an admin. Sends nothing to a device."""
    from modules import fix_editor
    from modules.nsot import saved_plans as S
    from routes.saved_plans_v2 import _who as person

    ref = _page_ref()
    who = person()
    c = fix_editor.card(ref.name, request.form, who=who)
    if c["right"]:
        return _new_form(ref.name, 403, request.form, level="danger",
                         words=f"Not saved: {c['right']}")
    if not c["built"]["saveable"]:
        return _new_form(ref.name, 409, request.form, level="danger",
                         words="Not saved: " + "; ".join(c["built"]["refusals"]
                                                       or ["the draft does not build"]))
    d = c["draft"]
    try:
        f = S.new_fix(ref.name, name=d["name"], words=d["words"], match=d["match"],
                      fills=c["built"]["fills"], template=c["built"]["doc"], **who)
    except S.Refused as exc:
        return _new_form(ref.name, 403 if "may not" in str(exc) or "does not hold" in str(exc)
                         or "verified person" in str(exc) else 409, request.form,
                         level="danger", words=f"Not saved: {exc}")
    log.info("fixes: %s written on %s", f["key"], ref.name)
    return _strict(render_template("v2/_fix_form.html", c=None, saved=f, network=ref.name,
                                   said={}))


def _contents(network: str, key: str, code: int = 200, edit_card=None, **said):
    """The Contents fold drawn again in place, Edit…'s form in it when *edit* (its card): the
    fix's page model cut to what the fold draws (`CONTENTS_DRAWS`)."""
    from modules import fix_editor, fix_page

    p = fix_page.page(network, key)
    fold = {k: p[k] for k in CONTENTS_DRAWS}
    if fold["contents"]:
        # Each check's limits on a port that is down are How it runs' (`p.limits`).
        fold["contents"] = dict(fold["contents"], checks=[
            {k: v for k, v in c.items() if k != "limits"} for c in fold["contents"]["checks"]])
    return _strict(render_template("v2/_fix_contents.html", p=fold,
                                   edit=fix_editor.drawn(edit_card), said=said), code)


#: What the Contents fold (`_fix_contents.html`) draws of a fix's page model: the rest is the
#: other folds' and the BLUF's, drawn by the whole page.
CONTENTS_DRAWS = ("key", "network", "fixes", "version", "versions", "contents", "editable")


@bp.route("/<key>/edit", methods=["GET"])
def edit(key):
    """Edit… in a fix's Contents fold (board fix-manual-controls screen 3): its form in place,
    drawn again as each choice changes (``drafted=1``), the Save button naming whether it saves
    in place or as a new version. ``close=1`` draws the fold as it was (Cancel). A read."""
    from modules import fix_editor
    from modules.nsot import saved_plans as S
    from routes.saved_plans_v2 import _who as person

    ref = _page_ref()
    key = str(key)[:64]
    f = S.fixes(ref.name).get(key)
    if not f:
        abort(404)
    if request.args.get("close") == "1":
        return _contents(ref.name, key)
    return _contents(ref.name, key, edit_card=fix_editor.card(ref.name, request.args, fix=f,
                                                         who=person()))


@bp.route("/<key>/edit", methods=["POST"])
def edit_save(key):
    """Save (or Save as version N): name, description and match in place; a change to the
    lines, checks or verify saved as a new version, the old kept, an Automatic fix held Manual
    only until the new version has a verified run (`saved_plans.edit_fix`). The right changing
    it takes before and after; the AI none. Answered by the whole fix page in place (its
    BLUF, Contents and How it runs all move). Sends nothing to a device."""
    from modules import fix_editor, fix_page
    from modules.nsot import saved_plans as S
    from routes.saved_plans_v2 import _who as person

    ref = _page_ref()
    key = str(key)[:64]
    who = person()
    f = S.fixes(ref.name).get(key)
    if not f:
        abort(404)
    c = fix_editor.card(ref.name, request.form, fix=f, who=who)

    def page_again(code=200, edit_card=None, **said):
        p = fix_page.page(ref.name, key)
        return _strict(render_template(
            "v2/fix.html", p=p, form=fix_page.delete_form(ref.name, key, who), said={},
            edit=fix_editor.drawn(edit_card), contents_said=said,
            auto=fix_page.automatic_form(ref.name, key, who),
            who=_who(), active_nav="fixes"), code)
    if c["right"]:
        return page_again(403, c, level="danger", words=f"Not saved: {c['right']}")
    if not c["built"]["saveable"]:
        return page_again(409, c, level="danger", words="Not saved: " + "; ".join(
            c["built"]["refusals"] or ["the draft does not build"]))
    d = c["draft"]
    try:
        got = S.edit_fix(key, network=ref.name, version=int(request.form.get("version") or 0),
                         name=d["name"], words=d["words"], match=d["match"],
                         fills=c["built"]["fills"], template=c["built"]["doc"], **who)
    except (S.Refused, ValueError) as exc:
        return page_again(403 if "may not" in str(exc) or "does not hold" in str(exc)
                          or "verified person" in str(exc) else 409, c, level="danger",
                          words=f"Not saved: {exc}")
    log.info("fixes: %s edited on %s (new version: %s)", key, ref.name, got["new_version"])
    n = got["version"]
    held = ("; Manual only until its next verified run" if f.get("how") == "automatic"
            and got.get("how") != "automatic" else "")
    words = (f"Saved as version {n}; version {n - 1} and its runs are kept" + held
             if got["new_version"] else f"Saved in place: still version {n}" + held)
    if got.get("proposed"):
        words += (f". Held provisional until an admin approves: "
                  f"{', '.join(got['proposed'])}; it cannot run until then")
    return page_again(level="ok", words=words)


@bp.route("/<key>/automatic", methods=["POST"])
def automatic(key):
    """Set Automatic… in How it runs: a matched fix held Manual only (or in Dry run) promoted
    to Automatic, binding its plan's digest, once its version has a verified run
    (`saved_plans.promote`, the incident card's Promote's own path); then, as that Promote does,
    the retry pass tries its open matches whose fixes failed once (`heal.retry.run_soon`).
    The self-healing right; the AI none. Sends nothing to a device itself."""
    from modules.heal import retry
    from modules.nsot import saved_plans as S
    from routes.saved_plans_v2 import _who as who

    ref = _page_ref()
    key = str(key)[:64]
    try:
        e = S.promote(key, network=ref.name, **who())
    except S.Refused as exc:
        return _how(ref.name, key, 403 if "may not" in str(exc) or "does not hold" in str(exc)
                    or "verified person" in str(exc) else 409, level="danger",
                    words=f"Not set Automatic: {exc}")
    retry.run_soon(ref.name, "script_saved", script=e["key"],
                   instance=f"{e['key']}:{e.get('promoted_at') or ''}", how="promoted",
                   by=who()["actor"])
    return _how(ref.name, key, level="ok", words=(
        f"Set Automatic: {e.get('name') or key} runs by itself on a matching incident while "
        f"{ref.name}'s self-healing is in Auto"))


@bp.route("/<key>", methods=["GET"])
def fix(key):
    """One fix's page, for the page's network; a key it does not hold is a 404 saying so."""
    from modules import fix_page

    from routes.saved_plans_v2 import _who as person

    ref = _page_ref()
    key = str(key)[:64]
    p = fix_page.page(ref.name, key)
    form = fix_page.delete_form(ref.name, key, person()) if p["kind"] == "saved" else None
    auto = fix_page.automatic_form(ref.name, key, person()) if p["kind"] == "saved" else None
    return _strict(render_template("v2/fix.html", p=p, form=form, auto=auto, said={},
                                   who=_who(), active_nav="fixes"),
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
    # Run on an open incident (``incident``), or Or choose a device and interface (``port=1``,
    # its device, interface and each choice the plan takes; the server reads only these).
    c = fix_page.run_card(ref.name, key, incident=(a.get("incident") or "").strip()[:64],
                          device=(a.get("device") or "").strip(),
                          interface=(a.get("interface") or "").strip(),
                          port=a.get("port") == "1",
                          choices={k[len("choice_"):]: (v or "").strip()[:40]
                                   for k, v in a.items() if k.startswith("choice_")},
                          right=_right())
    return _strict(render_template("v2/_fix_run.html", c=c))


def _how(network: str, key: str, code: int = 200, **said):
    """The How it runs fold drawn again in place, its Delete… or Restore… answer leading it."""
    from modules import fix_page
    from routes.saved_plans_v2 import _who as who

    p = fix_page.page(network, key)
    return _strict(render_template("v2/_fix_how.html", p=p, form=fix_page.delete_form(
        network, key, who()), auto=fix_page.automatic_form(network, key, who()), said=said,
        open_fold=True), code)


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
    runs. Called by `fixit_v2.fix_with_script` and `saved_plans_v2._device_draw`. *interface*
    is taken from them and not carried: the answer draws the device and the run path's own
    words, never the port alone."""
    from modules import fix_page

    del interface
    said = refused or done or words
    if incident and said.startswith(incident):
        # No raw ids on the fix's page (the operator's change 3): the incident is linked.
        said = "The incident" + said[len(incident):]
    c = {"state": "answer", "key": key, "network": network, "device": device,
         "incident": incident,
         "level": "danger" if refused or level == "danger" else "ok",
         "words": said.replace(incident, "the incident") if incident else said, "run": None}
    if run:
        c.update(state="run", run=fix_page.run_state(network, run))
    return _strict(render_template("v2/_fix_run.html", c=c), code)
