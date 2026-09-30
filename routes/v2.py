"""routes/v2.py — the redesign's pages beyond the device page (option A,
approved 2026-09-30): the landing page (Needs attention) and Help > About.

Every route here is a READ under the strict policy, drawn from what the app
already computes: Needs attention is `attention.needs_attention()`, masked on
the way out as `/attention` masks it; About's version is
`routes.health.version_facts()`, the one composition `/health/version` serves;
whether the running commit is what is pushed is the `app-pushed` reader.
"""

import logging
import os
import subprocess

from flask import Blueprint, render_template

from routes.device_v2 import _strict, _who

log = logging.getLogger(__name__)

bp = Blueprint("v2", __name__, url_prefix="/v2")

#: How many receipts the landing shows under "Recent changes".
RECENT_RECEIPTS = 5


def _attention() -> dict:
    from modules.attention import needs_attention
    from modules.outbound import mask_payload

    # Rows quote their sources' own words: masked on the way out, as /attention does.
    return mask_payload(needs_attention())


def _recent() -> dict:
    """The last deploys and restores of the active list, from their receipts."""
    from modules.nsot import listref, receipts

    ref = listref.active()
    got = receipts.read(ref.name, limit=RECENT_RECEIPTS)
    # The rows as the receipts hold them (masked at write); the template reads
    # device, action, outcome, at, actor, reason and program_lines.
    return {"state": got["state"], "rows": list(got.get("rows") or []), "list": ref.name}


def _page(template: str, **ctx):
    from modules.nsot import listref

    ctx.setdefault("list_name", listref.active().name)
    return _strict(render_template(template, who=_who(), **ctx))


@bp.route("/", methods=["GET"])
def landing():
    """Needs attention: what is wrong and what needs a person, worst first."""
    return _page("v2/landing.html", a=_attention(), recent=_recent(), active_nav="attention")


@bp.route("/attention", methods=["GET"])
def attention_list():
    """The list alone, re-fetched when a source's reader announces."""
    return _strict(render_template("v2/_attention.html", a=_attention()))


def _subject(commit: str) -> str:
    if not commit:
        return ""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        out = subprocess.run(["git", "-C", root, "log", "-1", "--format=%s", commit],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def installation() -> dict:
    """About this installation: the running commit, its CI verdict, whether it
    is what is pushed, and who is looking. Each from its one source."""
    from modules import reader_job
    from modules.readers import app_pushed
    from routes import health

    facts = health.version_facts()
    got = reader_job.read_cached("app-pushed")
    good = ((got.get("doc") or {}).get("last_good") or {})
    value = good.get("value") or {}
    if got["state"] != "ok" or not good:
        pushed = {"state": "unknown", "words": "not compared yet: "
                  + (got.get("why") or "the reader has stored nothing")}
    elif value.get("running") != facts.get("running"):
        pushed = {"state": "not_judged", "words": "the stored comparison is for another commit; "
                  "this one is compared at the reader's next run"}
    else:
        pushed = {"state": value.get("state"), "words": app_pushed.words(value),
                  "value_at": good.get("value_at")}
    from modules import update_op

    last = update_op.outcome()
    lv = last.get("value") or {}
    last["words"] = (f"{update_op.OUTCOME_WORDS.get(lv.get('outcome'), lv.get('outcome'))}: "
                     f"{str(lv.get('from') or '')[:10]} to {str(lv.get('to') or '')[:10]}"
                     + (f" by {lv['requested_by']}" if lv.get("requested_by") else "")) if lv else ""
    return {"running": facts.get("running") or "", "subject": _subject(facts.get("running")),
            "started_at": facts.get("started_at"), "pid": os.getpid(),
            "version": facts.get("version") or {}, "ci": facts.get("ci") or {}, "pushed": pushed,
            "last_update": last}


@bp.route("/help/about", methods=["GET"])
def about():
    """Help > About: the software, moved out of the top bar."""
    return _page("v2/about.html", inst=installation(), active_nav="help")


@bp.route("/help/installation", methods=["GET"])
def installation_card():
    """About's installation card alone, re-fetched when the CI verdict or the
    pushed comparison is re-read."""
    return _strict(render_template("v2/_installation.html", inst=installation(), who=_who()))


# ------------------------------------------------------------- the Update button
# (the operator, 2026-09-30; modules/update_op.py; docs/UPDATE.md). ONE page,
# two entry points: Needs attention's "behind what is pushed" row and Help >
# About. The page draws the preview from the `app-pushed` reader's stored
# value (no page load fetches or asks GitHub), confirms by the preview's hash,
# then waits on /health for the new commit, never on a timer.

def _update_ctx() -> dict:
    from flask import request

    from modules import update_op
    from modules.outbound import mask_payload
    from modules.preview_confirm import confirm_part

    p = update_op.plan()
    return {"p": mask_payload(p), "hist": update_op.history(5),
            "confirm": confirm_part(request, "confirm"),
            "words": update_op.OUTCOME_WORDS, "up_bound_s": update_op.UP_BOUND_S,
            "updater_timeout_s": update_op.UPDATER_TIMEOUT_S}


@bp.route("/update", methods=["GET"])
def update():
    """Update NMAS: the preview, the confirm, and the last update's outcome."""
    return _page("v2/update.html", active_nav="help", **_update_ctx())


@bp.route("/update/panel", methods=["GET"])
def update_panel():
    """The preview alone, re-fetched when the reader announces `app_version`."""
    return _strict(render_template("v2/_update.html", who=_who(), **_update_ctx()))
