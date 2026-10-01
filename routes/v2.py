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


def _run_words(run: dict, me: str) -> str:
    """One run's cause and duration, for a hover: "checked on your request, 1.1 s"."""
    from modules import reader_job

    words = reader_job.trigger_words((run or {}).get("trigger"), me)
    took = (run or {}).get("took_ms")
    return f"{words}, {took / 1000:.1f} s" if isinstance(took, int) else words


def check_state(name: str = "app-pushed") -> dict:
    """What Check again draws (reader_job rule 13), for the person looking: a
    run on request still owed an answer and for how long it has run, how long
    the page waits before calling the answer late, and a last attempt that
    failed. The stored answer's cause and duration are `hover`, for the
    timestamp's title and never the row (the operator, 2026-09-30: the
    timestamp changing to "just now" IS the confirmation). Ages, never epochs:
    the browser's clock is not the host's."""
    import time

    from modules import identity, reader_job

    who = identity.viewer()
    me = who.actor if who.is_identified else ""
    doc = reader_job.read_cached(name).get("doc") or {}
    good = doc.get("last_good") or {}
    attempt = doc.get("last_attempt") or {}
    flight = reader_job.request_in_flight(name)
    bound = reader_job.answer_bound(name)
    failed = None
    if attempt and not attempt.get("ok"):
        failed = {"at": attempt.get("at"), "error": attempt.get("error") or "no reason recorded",
                  "words": _run_words(attempt, me)}
    return {"running_for": round(time.time() - flight["since"], 1) if flight else None,
            "bound_seconds": bound["seconds"], "bound_basis": bound["basis"],
            "hover": _run_words(good, me) if good else "", "failed": failed}


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
            "last_update": last, "check": check_state()}


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

    from modules import host_steps
    from routes import health

    p = update_op.plan()
    return {"p": mask_payload(p), "hist": update_op.history(5),
            "owed": host_steps.owed(health._COMMIT) if health._COMMIT else None,
            "confirm": confirm_part(request, "confirm"),
            "words": update_op.OUTCOME_WORDS, "up_bound_s": update_op.UP_BOUND_S,
            "ci_badge": update_op.CI_BADGE, "step_words": update_op.STEP_WORDS,
            "steps": update_op.STEPS, "check": check_state(),
            "updater_timeout_s": update_op.UPDATER_TIMEOUT_S}


@bp.route("/update", methods=["GET"])
def update():
    """Update NMAS: the preview, the confirm, and the last update's outcome."""
    return _page("v2/update.html", active_nav="help", **_update_ctx())


@bp.route("/update/panel", methods=["GET"])
def update_panel():
    """The preview alone, re-fetched when the reader announces `app_version`."""
    return _strict(render_template("v2/_update.html", who=_who(), **_update_ctx()))


def _coverage() -> dict:
    """Monitoring > Coverage for the active list (P.9 (d))."""
    from modules import monitoring_coverage
    from modules.nsot import listref

    return monitoring_coverage.fleet(listref.active())


@bp.route("/monitoring/coverage", methods=["GET"])
def coverage():
    """Monitoring > Coverage: each device by integration, from its committed
    golden, and the monitoring profile's batch Apply (NSOT_GUI_BRIEF 14.3)."""
    return _page("v2/coverage.html", c=_coverage(), active_nav="monitoring")


@bp.route("/monitoring/coverage/table", methods=["GET"])
def coverage_table():
    """The table alone, re-fetched when goldens, intent or job health move."""
    return _strict(render_template("v2/_coverage.html", c=_coverage()))
