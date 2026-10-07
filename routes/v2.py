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
import re
import subprocess

from flask import Blueprint, render_template
from html import escape

from routes.device_v2 import _strict, _who

log = logging.getLogger(__name__)

bp = Blueprint("v2", __name__, url_prefix="/v2")

@bp.app_template_filter("age_words")
def age_words(iso, now=None) -> str:
    """An ISO time as the page's own age words ("just now", "3 min ago", "2 h ago"), the
    SAME words `ageWords` in static/js/nmas_v2.js draws and keeps fresh.

    Drawn on the server so a fragment's first paint already reads right (C459, 2026-10-05:
    `stamp()` drew the raw ISO time, and the script rewrote it only after htmx settled, so
    every live redraw flashed "2026-10-05T02:31:00Z" and back). An unreadable time is drawn
    as itself, as before."""
    import time as _time
    from datetime import datetime

    try:
        then = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return str(iso or "")
    s = round((_time.time() if now is None else now) - then)
    s = max(s, 0)
    if s < 45:
        return "just now"
    if s < 90:
        return "1 min ago"
    m = round(s / 60)
    if m < 60:
        return f"{m} min ago"
    h = round(m / 60)
    if h < 36:
        return f"{h} h ago"
    return f"{round(h / 24)} d ago"


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
    from modules import manual
    return _page("v2/about.html", inst=installation(), nav=manual.nav(), active_nav="help")


# ------------------------------------------------------------------ History
# (NSOT_GUI_BRIEF 3.4; board D, History as one timeline, signed off 2026-10-03, C369:
# modules/history_sources.timeline, the one reader behind this page and every device's tab)

HISTORY_TABS = (("timeline", "Timeline"), ("baselines", "Baselines"),
                ("authorisations", "Authorisations"))
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._@+-]{1,128}$")


def _history_filters(request) -> dict:
    """The timeline's filters, each in the address so a view is a link. A device or person
    that is not a name is refused (said), never passed on."""
    from modules import history_sources as HS

    a = request.args
    since = a.get("since", "7")
    kinds = [k for k in a.getlist("kind") if k in HS.KIND_FILTERS]
    # The Commits tab became a kind (board D): its old links open the timeline on commits.
    if a.get("tab") == "commits" and not kinds:
        kinds = ["commits"]
    f = {"device": a.get("device", "").strip(), "person": a.get("person", "").strip(),
         "kinds": kinds,
         "since": since if since in [s for s, _w in HS.SINCE_CHOICES] else "7",
         "limit": a.get("limit", ""), "error": ""}
    for name in ("device", "person"):
        if f[name] and not _SAFE_NAME.match(f[name]):
            f["error"] = f"the {name} filter {f[name]!r} is not a name"
            f[name] = ""
    return f


def _history_remote(ref) -> dict:
    """The header: the remote's one sentence (``remote_publication.describe``),
    and whether anything is uncommitted (one ``git status``)."""
    from modules.nsot import repo as R
    from modules.readers import remote_publication as RP

    from modules.nsot import remote as NR
    from modules.redact import redact_text

    pub = RP.status_for(ref.name)
    out = {"d": RP.describe(pub), "value_at": pub.get("value_at"), "dirty": None,
           "list": ref.name}
    # The last failed push and the last Verify, from the list's own record (the operator,
    # 2026-10-05): a push's answer announces `remote`, which redraws this card, so an answer
    # held only in the browser vanished as it arrived. Drawn from the store, any redraw keeps
    # it. A successful push clears the failure (`record_push`). Masked on the way out.
    try:
        rec = NR.load_remote(ref.name) or {}
    except Exception as exc:                          # noqa: BLE001
        log.warning("v2 history: the remote record could not be read: %s", exc)
        rec = {}
    failure = rec.get("last_push_failure") or None
    if failure:
        failure = dict(failure, reason=redact_text(str(failure.get("reason") or "")))
    verify = rec.get("last_verify") or None
    if verify:
        verify = dict(verify, failed=[dict(f, detail=redact_text(str(f.get("detail") or "")))
                                      for f in verify.get("failed") or []])
    out.update(push_failure=failure, last_verify=verify)
    rc, text, _err = R.git(ref.repo_dir, "status", "--porcelain")
    out["dirty"] = len([l for l in (text or "").splitlines() if l.strip()]) if rc == 0 else None
    return out


def _history_members(ref) -> list:
    from modules.device import load_saved_devices
    try:
        return sorted(d.get("hostname", "") for d in load_saved_devices(ref.csv_path)
                      if d.get("hostname"))
    except Exception as exc:                          # noqa: BLE001
        log.warning("v2 history: the inventory could not be read: %s", exc)
        return []


def _history_timeline(ref, f, members) -> dict:
    """THE timeline (C369), filtered as the address says."""
    from modules import history_sources as HS
    h = HS.timeline(ref, device=f["device"], person=f["person"], kinds=f["kinds"],
                    since_days=f["since"],
                    limit=int(f["limit"]) if str(f["limit"]).isdigit() else HS.DEFAULT_LIMIT,
                    members=members or None)
    if f["error"]:
        h["errors"] = [f["error"]] + h["errors"]
    return h


def _history_ctx(request) -> dict:
    from modules import history_sources as HS
    from modules import reader_job
    from modules.nsot import freshness, listref

    ref = listref.active()
    tab = request.args.get("tab", "timeline")
    if tab == "commits":
        tab = "timeline"
    if tab not in [t for t, _l in HISTORY_TABS]:
        tab = "timeline"
    f = _history_filters(request)
    ctx = {"tab": tab, "tabs": HISTORY_TABS, "f": f, "ref": ref,
           "remote": _history_remote(ref), "since_choices": HS.SINCE_CHOICES,
           "kind_groups": HS.KIND_GROUPS}
    if tab == "timeline":
        ctx["devices"] = _history_members(ref)
        ctx["h"] = _history_timeline(ref, f, ctx["devices"])
    elif tab == "baselines":
        got = reader_job.read_cached("baseline-usability")
        good = (got.get("doc") or {}).get("last_good") or {}
        ctx["b"] = (((good.get("value") or {}).get("lists") or {}).get(ref.name) or {})
        ctx["b_at"] = good.get("value_at")
    else:
        try:
            rows = freshness.authorisations(ref.name, include_expired=True)
            ctx["auth"] = {"rows": list(reversed(rows)), "error": ""}
        except Exception as exc:                          # noqa: BLE001
            ctx["auth"] = {"rows": [], "error": f"{type(exc).__name__}: {exc}"}
    return ctx


@bp.route("/history", methods=["GET"])
def history_page():
    """History: one timeline of everything that happened to the network and its devices,
    its baselines and authorisations, with the remote's state at the top."""
    from flask import request
    return _page("v2/history.html", active_nav="history", **_history_ctx(request))


@bp.route("/history/timeline", methods=["GET"])
def history_timeline():
    """The timeline alone, redrawn when a record lands."""
    from flask import request

    from modules import history_sources as HS
    from modules.nsot import listref
    ref = listref.active()
    f = _history_filters(request)
    return _strict(render_template("v2/_history_timeline.html",
                                   h=_history_timeline(ref, f, _history_members(ref)), f=f,
                                   kind_groups=HS.KIND_GROUPS))


@bp.route("/history/commit/<sha>", methods=["GET"])
def history_commit(sha):
    """One commit's change, masked (C77), drawn when a person opens its row."""
    from modules import history_sources as HS
    from modules.nsot import listref
    d = HS.diff(listref.active().repo_dir, sha)
    return _strict(render_template("v2/_history_diff.html", d=d, sha=sha))


@bp.route("/history/remote", methods=["GET"])
def history_remote():
    """The header alone, redrawn when the remote is re-read (``remote``)."""
    from modules.nsot import listref
    return _strict(render_template("v2/_history_remote.html",
                                   remote=_history_remote(listref.active())))


# ------------------------------------------------------------------ Credentials
# Source of truth > Credentials, its first piece: the break-glass record (board 7, signed off
# 2026-10-03; modules/breakglass_page.py). The export itself is routes/breakglass.py's, the
# one implementation; these draw it, and record the browser's word on the download.

def _credentials_list(req) -> str:
    """The list named in the address (every way in names it), else the active one; a name
    that is no list is said by the page, never replaced by another list."""
    from modules.nsot import listref
    from routes.list_param import named_list
    return named_list(req) or listref.active().name


def _breakglass_export_ctx(list_name: str) -> dict:
    from flask import request

    from modules.breakglass_export import export_plan
    from modules.outbound import mask_payload
    from modules.preview_confirm import breakglass_preview

    return {"list_name": list_name,
            "p": mask_payload(breakglass_preview(export_plan(list_name), request=request))}


@bp.route("/credentials", methods=["GET"])
def credentials():
    """The break-glass record: whether it holds the credentials in use, its last export, and
    the export opened in place when the address asks (``open=export``)."""
    from flask import request

    from modules import breakglass_page
    from modules.nsot import listref

    name = _credentials_list(request)
    ctx = {"list_name": name, "known": listref.exists(name),
           "r": breakglass_page.record(name) if listref.exists(name) else None,
           "open": request.args.get("open", "")}
    if ctx["known"] and ctx["open"] == "export":
        ctx.update(_breakglass_export_ctx(name))
    ctx["check"] = ctx["known"] and ctx["open"] == "check"
    ctx["drill"] = breakglass_page.drill(name) if ctx["known"] else None
    return _page("v2/credentials.html", active_nav="credentials", **ctx)


@bp.route("/credentials/export", methods=["GET"])
def credentials_export():
    """The export card alone, opened in place by the record's button."""
    from flask import request

    from modules.nsot import listref

    name = _credentials_list(request)
    if not listref.exists(name):
        return _strict(render_template("v2/_breakglass_refused.html",
                                       why=f"No list is named {name!r}: nothing to export.")), 404
    return _strict(render_template("v2/_breakglass_export.html", **_breakglass_export_ctx(name)))


@bp.route("/credentials/check", methods=["GET"])
def credentials_check_form():
    """"Check a break-glass file" (board 7, C), opened in place: a file and its passphrase."""
    from flask import request

    from modules.nsot import listref

    name = _credentials_list(request)
    if not listref.exists(name):
        return _strict(render_template("v2/_breakglass_refused.html",
                                       why=f"No list is named {name!r}: nothing to check.")), 404
    return _strict(render_template("v2/_breakglass_check.html", list_name=name, c=None))


@bp.route("/credentials/check", methods=["POST"])
def credentials_check():
    """Open the kept file IN MEMORY, compare each credential and the key with the ones in use,
    record who, when, the file's sha256 and the verdict, and draw the verdict in place. The
    passphrase and the file leave in nothing this route writes or answers."""
    from flask import request

    from modules import identity
    from modules.breakglass_export import check_file
    from modules.nsot import listref

    name = (request.form.get("list") or "").strip()
    if not listref.exists(name):
        return _strict(render_template("v2/_breakglass_refused.html", why=(
            f"No list is named {name!r}: nothing was opened."))), 404
    upload = request.files.get("file")
    blob = upload.read() if upload else b""
    actor = identity.identify(request).actor
    out = check_file(name, blob, request.form.get("passphrase") or "", actor=actor)
    blob = None
    log.info("breakglass: %s checked a file for %s: %s", actor, name,
             out.get("counts") if out.get("ok") else f"refused at {out.get('stage')}")
    return _strict(render_template("v2/_breakglass_check.html", list_name=name, c=out,
                                   filename=(upload.filename if upload else "")))


@bp.route("/credentials/drill", methods=["POST"])
def credentials_drill():
    """Record the offline drill (board 7, D): the receipt line `nmas-breakglass drill` printed
    where the file is kept, checked against a logged export of the list (its sha256, device
    count and key), then recorded; the drill's card redrawn in place. A receipt that matches no
    export is refused naming what it said and what the log holds."""
    import modules.breakglass as bg
    from flask import request

    from modules import breakglass_page, identity
    from modules.config import DATA_DIR
    from modules.nsot import listref

    name = (request.form.get("list") or "").strip()
    if not listref.exists(name):
        return _strict(render_template("v2/_breakglass_refused.html", why=(
            f"No list is named {name!r}: nothing was recorded."))), 404
    error = ""
    try:
        receipt = bg.parse_drill_receipt(request.form.get("receipt", ""))
        if receipt["list"] != name:
            raise bg.BreakglassError(f"the receipt is for {receipt['list']}, not {name}: record it "
                                     f"on {receipt['list']}'s Credentials")
        rows = [r for r in bg.all_exports(DATA_DIR).get("rows") or [] if r.get("list") == name]
        match = next((r for r in rows if r.get("sha256") == receipt["sha256"]), None)
        if not match:
            raise bg.BreakglassError(
                f"no export of {name} logged here has sha256 {receipt['sha256'][:12]}: this host "
                f"logged {len(rows)} export(s), the newest {str((rows[-1] if rows else {}).get('sha256', 'none'))[:12]}")
        held = len(match.get("devices") or {})
        if receipt["devices"] != held or receipt["key"] != (match.get("key_fingerprint") or "none"):
            raise bg.BreakglassError(
                f"the receipt says {receipt['devices']} device(s) and the key {receipt['key']}; that "
                f"export holds {held} and the key {match.get('key_fingerprint') or 'none'}")
        bg.record_drill(DATA_DIR, list_name=name, actor=identity.identify(request).actor,
                        receipt=receipt)
    except bg.BreakglassError as exc:
        error = f"Not recorded: {exc}."
    return _strict(render_template("v2/_breakglass_drill.html", list_name=name,
                                   d=breakglass_page.drill(name), error=error))


@bp.route("/credentials/intact", methods=["POST"])
def credentials_intact():
    """The browser's word on the download it just received (board 7, B): its sha256 of the
    bytes against the server's. Recorded either way, then the result card is drawn in place;
    a download not intact is said in danger and the export is not counted as current."""
    import modules.breakglass as bg
    from flask import request

    from modules import identity
    from modules.config import DATA_DIR
    from modules.nsot import listref

    name = (request.form.get("list") or "").strip()
    sha = (request.form.get("sha256") or "").strip().lower()
    got = (request.form.get("browser_sha256") or "").strip().lower()
    if not listref.exists(name) or not re.fullmatch(r"[0-9a-f]{64}", sha or "x"):
        return _strict(render_template("v2/_breakglass_refused.html", why=(
            f"Not recorded: the list {name!r} or the file's sha256 {sha[:16]!r} is not one the "
            "export sent."))), 400
    last = (bg.last_exports(DATA_DIR).get("by_list") or {}).get(name) or {}
    if last.get("sha256") != sha:
        return _strict(render_template("v2/_breakglass_refused.html", why=(
            f"Not recorded: {name}'s newest export is sha256 {str(last.get('sha256', ''))[:12]}, "
            f"and this download is {sha[:12]}: an export made since replaced it."))), 409
    actor = identity.identify(request).actor
    row = bg.record_intact(DATA_DIR, list_name=name, sha256=sha, browser_sha256=got,
                           actor=actor)
    log.info("breakglass: %s's download of %s %s intact", actor, name,
             "arrived" if row["ok"] else "did NOT arrive")
    from modules import breakglass_page
    # The record's card above redraws with the answer (out of band): a change leaves the screen
    # showing the new state, never "none exported" above a finished export.
    return _strict(render_template("v2/_breakglass_done.html", list_name=name, last=last,
                                   row=row, at=breakglass_page._iso(row["at"]),
                                   filename=request.form.get("filename", ""),
                                   devices=len(last.get("devices") or {}),
                                   r=breakglass_page.record(name), oob=True))


@bp.route("/help/<slug>", methods=["GET"])
def help_page(slug):
    """A manual page (NSOT_GUI_BRIEF section 10): ``docs/manual/``, rendered
    by ``modules.manual``. An unknown page is a 404 naming the pages there are."""
    from flask import abort

    from modules import manual
    try:
        doc = manual.load(slug)
    except manual.ManualError:
        abort(404)
    return _page("v2/help.html", doc=doc, nav=manual.nav(), active_nav="help")


@bp.route("/help/<slug>/panel", methods=["GET"])
def help_panel(slug):
    """One manual section for the side help panel an info link opens: the
    SAME file the Help page renders, never a second copy of the words."""
    from flask import request

    from modules import manual
    try:
        sec = manual.section(slug, request.args.get("section", ""))
    except manual.ManualError as exc:
        return _strict(render_template("v2/_help_panel.html", sec=None, error=str(exc))), 404
    return _strict(render_template("v2/_help_panel.html", sec=sec, error=""))


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
            "updater_timeout_s": update_op.UPDATER_TIMEOUT_S,
            # The host steps the person ticked, carried through a live redraw (C472): the
            # panel's redraw sends its boxes, and each stays ticked exactly when it was.
            "host_steps_ticked": set(request.args.getlist("host_step"))}


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
    return _page("v2/coverage.html", c=_coverage(), active_nav="monitoring",
                 monitoring_tab="coverage")


@bp.route("/monitoring/coverage/table", methods=["GET"])
def coverage_table():
    """The table alone, re-fetched when goldens, intent or job health move.

    THE PERSON'S SELECTION SURVIVES THE REDRAW (C435): another person's deploy announces
    `goldens` and `intent` to every page, and the redraw ticked every offered row, so an
    untick reverted while its person chose. The redraw sends its form (`picked` and the
    ticked `device`s), and an offered row is ticked exactly when its person had it ticked.
    A row newly offered since arrives unticked: nothing joins a selection unseen."""
    from flask import request

    c = _coverage()
    if request.args.get("picked") == "1":
        kept = set(request.args.getlist("device"))
        for row in c["devices"]:
            if row.get("selectable"):
                row["checked"] = row["host"] in kept
    return _strict(render_template("v2/_coverage.html", c=c))


def _monitoring_network() -> str:
    """The network a Monitoring request shows (P.8 step 8; decided 2026-10-04, the URL is
    authoritative): the one its `list` names, which `list_param` has already refused when no
    such list exists, else the active list. Every link the page draws carries it, so a copied
    link shows the same network."""
    from flask import request

    from modules.nsot import listref
    from routes.list_param import named_list

    named = named_list(request)
    return listref.resolve(named).name if named else listref.active().name


def _fleet_ctx() -> dict:
    from flask import request

    from modules import device_page
    from modules.integration_groups import network_names
    return {"networks": network_names(),
            "m": device_page.fleet_monitoring(_monitoring_network(),
                                              chosen_uid=request.args.get("dashboard", ""),
                                              range_text=request.args.get("range", "1h"))}


@bp.route("/monitoring", methods=["GET"])
def monitoring_page():
    """Monitoring: the FLEET dashboard by default, with the selector, and
    Coverage as a tab beside it (the operator, 2026-10-01)."""
    return _page("v2/monitoring.html", active_nav="monitoring", monitoring_tab="dashboards",
                 **_fleet_ctx())


@bp.route("/monitoring/dashboard", methods=["GET"])
def monitoring_dashboard():
    """The fleet dashboard alone: the selector, the range and the panels."""
    return _strict(render_template("v2/_fleet.html", **_fleet_ctx()))


@bp.route("/monitoring/panel/<uid>/<int:panel_id>", methods=["GET"])
def monitoring_panel(uid, panel_id):
    """One fleet panel's data, for the browser to draw: a panel the dashboard
    holds, with the dashboard's own query."""
    from flask import jsonify, request

    from modules import device_page
    payload, code = device_page.fleet_panel_data(_monitoring_network(), uid, panel_id,
                                                 request.args.get("range", "1h"))
    return jsonify(payload), code


# ---------------------------------------------------------------------------
# Monitoring > Coverage's batch Apply (P.9 step d2): the preview, the confirm
# and the result, drawn server-side from the six-part contract (today's
# renderer emits inline handlers, which the strict policy refuses). The
# devices are applied in the ROLLOUT ORDER the preview shows and sets:
# sequential, the circuit breaker stopping after repeated failed devices.
# ---------------------------------------------------------------------------

#: The scopes this page applies, each with its words: the network's
#: monitoring profile's lines (P.9 b), or only the IP SLA probes committed to
#: the devices' intent (P.9 d4's add path, from the IP SLA page).
SCOPE_WORDS = {
    "profile": {"title": "Apply the monitoring profile",
                "sub": ("To the devices ticked on Coverage, one at a time in the order below. Each "
                        "receives exactly the program shown, and only the profile's lines."),
                "has_all": "it already has every line the profile supplies",
                "only": ("No line outside the profile's is sent, and nothing on a device is removed "
                         "unless you ticked it above."),
                "none_can": "No device here can receive the profile now: each says why above.",
                "all_nothing": ("Nothing to apply: every device chosen already has every line the "
                                "profile supplies.")},
    "ip_sla": {"title": "Send the IP SLA probes",
               "sub": ("The probes just committed to these devices' intent, one device at a time in "
                       "the order below. Each receives exactly the program shown: its new IP SLA "
                       "operations and their schedules, nothing else."),
               "has_all": "it already runs every IP SLA probe its intent declares",
               "only": ("No line but an IP SLA operation or its schedule is sent, and nothing on a "
                        "device is removed."),
               "none_can": "No device here can receive its probes now: each says why above.",
               "all_nothing": ("Nothing to send: every device chosen already runs every probe its "
                               "intent declares.")},
    # Coverage's combined deploy (artboard A2, signed off 2026-10-02): its own page.
    "templates": {"title": "Deploy missing templates",
                  "sub": ("Each device gets ONE program: every template it is missing, in the order "
                          "shown, sent and verified as one change, rolled back as one. Nothing else "
                          "in its intent is sent. Devices go one at a time, in this order; the "
                          "first that fails stops the rest."),
                  "has_all": "it already has every template the profile and its intent supply",
                  "only": ("No line outside the missing templates is sent, and nothing on a device "
                           "is removed."),
                  "none_can": "No device here can receive its templates now: each says why above.",
                  "all_nothing": ("Nothing to deploy: every device chosen already has every "
                                  "template the profile and its intent supply.")},
}


class UnknownScope(ValueError):
    """A scope this page does not apply; nothing is planned or sent."""


def _scope(req=None) -> str:
    """The scope the request carries (the preview's form, or the confirm's
    body), `profile` when none is named. An unknown one is refused, never
    read as the profile (a lookup that misses is a fact about the query)."""
    from modules.nsot import profile_apply
    if req is None:
        return profile_apply.SCOPE
    got = req.args.get("scope")
    if got is None and req.method == "POST":
        got = (req.get_json(silent=True) or {}).get("scope")
    got = (got or profile_apply.SCOPE).strip()
    if got not in SCOPE_WORDS:
        raise UnknownScope(f"unknown scope {got!r}: this page applies "
                           + " or ".join(sorted(SCOPE_WORDS)) + "; nothing was planned or sent")
    return got


def _apply_args(req) -> dict:
    """What the preview form carries: the list, the devices in the rollout
    order (a move or a leave-out applied), the superseded lines ticked for
    removal (by id) and each one's stated reason."""
    from routes.list_param import named_list

    order = []
    for d in req.args.getlist("device"):
        d = d.strip()
        if d and d not in order:
            order.append(d)
    move = (req.args.get("move") or "").strip()
    if ":" in move:
        way, name = move.split(":", 1)
        if name in order:
            i = order.index(name)
            j = i - 1 if way == "up" else i + 1 if way == "down" else i
            if 0 <= j < len(order):
                order[i], order[j] = order[j], order[i]
    drop = (req.args.get("drop") or "").strip()
    order = [d for d in order if d != drop]
    picked, reasons = {}, {}
    for d in order:
        ids = [i for i in req.args.getlist(f"rm::{d}") if i]
        if ids:
            picked[d] = ids
        for i in ids:
            reasons[(d, i)] = (req.args.get(f"why::{d}::{i}") or "").strip()
    return {"list": named_list(req), "order": order, "picked": picked, "reasons": reasons}


#: A template's name in Coverage's words, for a section of the program (CDP has no column).
_TEMPLATE_WORDS = {"snmp": "SNMP", "syslog": "Syslog", "heartbeat": "Heartbeat", "ntp": "NTP",
                   "lldp": "LLDP", "telemetry": "Telemetry", "ip_sla": "IP SLA", "cdp": "CDP"}


def _sent_templates(sc: dict) -> list:
    """The templates the program SENDS, in Coverage's words (`monitoring_coverage.sent_columns`,
    the one home the arrival watch shares)."""
    from modules.monitoring_coverage import sent_columns
    return [_TEMPLATE_WORDS.get(k, k) for k in sent_columns(sc)]


def _coverage_words(list_name: str, rows: list) -> None:
    """Artboard A2's not-reporting words on each row, from Coverage's own reading of the chosen
    devices (one stored read, `monitoring_coverage.fleet`): each configured template whose data
    is not arriving, NOT part of the deploy, with where its cause is looked for."""
    from modules import monitoring_coverage as MC
    from modules.device import load_saved_devices
    from modules.nsot import listref

    names = {r["name"] for r in rows}
    words = dict(MC.COLUMNS)
    try:
        ref = listref.resolve(list_name)
        devs = [(ref, d) for d in load_saved_devices(ref.csv_path)
                if (d.get("hostname") or "").strip() in names]
        by_host = {r["host"]: r for r in MC.fleet(ref, devices=devs)["devices"]}
    except Exception as exc:                            # noqa: BLE001
        log.warning("coverage deploy: Coverage could not be read for %s: %s", list_name, exc)
        by_host, why = {}, f"Coverage could not be read ({type(exc).__name__}: {exc})"
    else:
        why = ""
    for r in rows:
        cov = by_host.get(r["name"])
        r["coverage_unread"] = why or ("" if cov else "not in Coverage's reading")
        r["not_reporting"] = [{"name": words[k], "words": cov["cells"][k]["words"],
                               "where": cov["cells"][k].get("where", "")}
                              for k in (cov or {}).get("not_reporting") or []]


def _apply_ctx(req) -> dict:
    """The batch preview: every device's profile-scoped plan, as
    `/deploy/plan` with scope `profile` computes it, masked on the way out
    AFTER every hash is computed, and the confirm body built from those
    hashes, so the confirm sends exactly what this preview showed."""
    from modules.nsot import listref
    from modules.outbound import mask_payload
    from modules.preview_confirm import deploy_preview
    from routes.deploy import plan_devices

    args = _apply_args(req)
    scope = _scope(req)
    list_name = args["list"] or listref.active().name
    ctx = {"list_name": list_name, "order": args["order"], "rows": [], "preview": None,
           "confirm_body": None, "ready": [], "scope": scope, "words": SCOPE_WORDS[scope]}
    if not args["order"]:
        return ctx
    devices = plan_devices(list_name, args["order"], remove=args["picked"], scope=scope)
    # Each ticked removal needs its stated reason in the confirm hash (Mode B,
    # C140): the keys are known only once the removal is planned, so a ticked
    # line with a reason is planned again carrying it.
    authorise = {}
    for d in devices:
        rm = d.get("removals") or {}
        auth = [{"line": key, "reason": args["reasons"].get((d.get("device"), rid), "")}
                for rid, key in zip(rm.get("ids") or [], rm.get("keys") or [])]
        if any(a["reason"] for a in auth):
            authorise[d["device"]] = [a for a in auth if a["reason"]]
    if authorise:
        devices = plan_devices(list_name, args["order"], remove=args["picked"],
                               authorise=authorise, scope=scope)
    preview = deploy_preview(devices, req, scope=scope)
    out = mask_payload({"devices": devices, "preview": preview})
    # The six parts keep a target's state and selectability under "what", and
    # its program, operands and gates under "targets": one row of both.
    by_name = {t["name"]: dict(t) for t in out["preview"]["targets"]}
    for w in out["preview"]["what"]["targets"]:
        by_name.setdefault(w["name"], {}).update(state=w.get("state", ""),
                                                 selectable=w.get("selectable"),
                                                 why_not=w.get("why_not", ""))
    rows, ready = [], []
    for d in out["devices"]:
        name = d.get("device", "")
        t = by_name.get(name) or {}
        sc = d.get("profile_scope") or {}
        chosen = set((d.get("removals") or {}).get("ids") or [])
        superseded = [{"id": s.get("id", ""),
                       "text": " > ".join(list(s.get("chain") or []) + [s["line"].strip()]),
                       "why_not": s.get("why_not", ""), "picked": s.get("id") in chosen,
                       "reason": args["reasons"].get((name, s.get("id")), "")}
                      for s in sc.get("superseded") or []]
        row = {"name": name, "state": t.get("state", ""), "selectable": t.get("selectable"),
               "program": (t.get("program") or {}).get("lines") or [],
               "none": (t.get("program") or {}).get("none", ""),
               "notes": (t.get("program") or {}).get("notes") or [],
               "verify": (t.get("program") or {}).get("verify"),
               "templates": _sent_templates(sc),
               "gates": t.get("gates") or [], "operands": t.get("operands") or [],
               "superseded": superseded,
               "authorisation_error": d.get("authorisation_error", ""),
               "blocking": list(d.get("blocking_reasons") or []),
               "refused": d.get("refused") or d.get("error") or "",
               "busy": d.get("busy") or ""}
        # A ticked removal with no stated reason (or any line awaiting one)
        # is not confirmable: the apply would refuse it, so it is not offered
        # (the shared preview checks only dangerous and re-added lines).
        if t.get("selectable") and d.get("authorisation_ok") is False:
            row.update(selectable=False, state="not_authorised")
        # NOTHING TO SEND (C295, the operator, 2026-10-01): a device that
        # already holds every line the profile supplies reads so, leaves the
        # rollout order (no Earlier, Later or Leave out to give it), and is no
        # part of the confirm.
        row["nothing"] = bool(row["selectable"] and not row["program"])
        if row["nothing"]:
            row.update(selectable=False, state="nothing")
        rows.append(row)
        if row["selectable"]:
            ready.append(name)
    if scope == "templates":
        _coverage_words(list_name, rows)
    # The devices with nothing to send go last in the order the page carries,
    # so Earlier and Later move a device past a neighbour the person can see.
    rows = [r for r in rows if not r["nothing"]] + [r for r in rows if r["nothing"]]
    ctx["order"] = [r["name"] for r in rows]
    ctx.update(rows=rows, preview=out["preview"], ready=ready,
               all_nothing=bool(rows) and all(r["nothing"] for r in rows))
    if ready:
        # The confirm body, computed HERE from the hashes this preview drew: the
        # browser sends it back unchanged, in the rollout order.
        plan = {d["device"]: d for d in devices}
        ctx["confirm_body"] = {
            "list": list_name, "order": ready, "scope": scope,
            "confirmations": {n: plan[n].get("capture_hash", "") for n in ready},
            "command_hashes": {n: plan[n].get("command_hash", "") for n in ready},
            "remove": {n: list((plan[n].get("removals") or {}).get("ids") or [])
                       for n in ready if (plan[n].get("removals") or {}).get("ids")},
            "authorise": {n: authorise[n] for n in ready if n in authorise}}
    return ctx


@bp.route("/monitoring/apply", methods=["GET"])
def profile_apply():
    """Apply the monitoring profile to the devices ticked on Coverage: one
    batch preview, the rollout order drawn and settable, then one confirm."""
    from flask import request
    try:
        ctx = _apply_ctx(request)
    except UnknownScope as exc:
        return _strict(str(escape(str(exc))), 400)
    # Coverage's combined deploy is its own page (artboard A2); the profile and IP SLA
    # scopes keep the stepper's (signed off 2026-10-02).
    page = "v2/coverage_deploy.html" if ctx["scope"] == "templates" else "v2/apply.html"
    return _page(page, active_nav="monitoring", monitoring_tab="coverage", **ctx)


@bp.route("/monitoring/apply/preview", methods=["GET"])
def profile_apply_preview():
    """The preview alone, planned again: a device moved or left out, a
    superseded line ticked for removal, or a reason typed."""
    from flask import request
    try:
        ctx = _apply_ctx(request)
    except UnknownScope as exc:
        return _strict(str(escape(str(exc))), 400)
    part = ("v2/_coverage_deploy_preview.html" if ctx["scope"] == "templates"
            else "v2/_apply_preview.html")
    return _strict(render_template(part, **ctx))


@bp.route("/monitoring/apply/confirm", methods=["POST"])
def profile_apply_confirm():
    """Start the confirmed batch as a job, as the verified person, in the
    rollout order. Every device's program is computed again by the apply and
    compared with the hash this confirm carries; a moved one is refused alone,
    with nothing sent to it. Answers 202 with the job's id."""
    from flask import jsonify, request

    from modules import deploy_job, identity
    from modules.nsot import listref

    data = request.get_json(silent=True) or {}
    try:
        scope = _scope(request)
    except UnknownScope as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    list_name = (data.get("list") or "").strip()
    if not list_name or not listref.exists(list_name):
        return jsonify({"ok": False, "error": (
            "No known list named: the batch records into one list's repository, so the list "
            "comes from the preview you confirmed. Nothing was sent.")}), 400
    order = [d for d in (data.get("order") or []) if isinstance(d, str) and d]
    confirmations = data.get("confirmations") or {}
    hashes = data.get("command_hashes") or {}
    if not order or any(d not in confirmations or not hashes.get(d) for d in order):
        return jsonify({"ok": False, "error": (
            "Nothing confirmed: every device needs the capture and command hashes its preview "
            "showed. Nothing was sent.")}), 400
    job = deploy_job.start(
        list_name, order, confirmations, hashes,
        authorise=data.get("authorise") or {}, remove=data.get("remove") or {},
        scope=scope, actor=identity.request_actor(),
        actor_kind=getattr(identity.identify(request), "kind", ""),
        ident=identity.verified_identity())
    from flask import url_for
    return jsonify({"ok": True, "job": job,
                    "url": url_for("v2.profile_apply_job", job=job)}), 202


@bp.route("/monitoring/apply/job/<job>", methods=["GET"])
def profile_apply_job(job):
    """Where the batch is, in the rollout order, then its result: drawn from
    the receipts the apply wrote. Redrawn when the job announces."""
    from modules import deploy_job
    got = deploy_job.state(job)
    from modules import arrival_watch
    return _strict(render_template("v2/_apply_job.html", j=got, job=job,
                                   arrivals=arrival_watch.state(job))), (200 if got else 404)


# ---------------------------------------------------------------------------
# Monitoring > IP SLA (P.9 d4, the ADD path): the profile's policy, the probes
# it suggests for the chosen devices (where each lives, what path it
# measures, why there, its expected CPU cost), one commit of the ticked ones
# into the devices' intent, then the batch Apply scoped to IP SLA lines.
# Changing a running probe is the re-create (C290), gated on staged run 9.
# ---------------------------------------------------------------------------

def _ip_sla_ctx(req) -> dict:
    from modules.nsot import ip_sla_policy, listref, profile
    from routes.list_param import named_list

    name = named_list(req) or listref.active().name
    ref = listref.resolve(name) if listref.exists(name) else None
    chosen = []
    for d in req.args.getlist("device"):
        d = d.strip()
        if d and d not in chosen:
            chosen.append(d)
    ctx = {"list_name": name, "chosen": chosen, "policy": None, "plan": None, "error": "",
           "defaulted": False,
           "policies": [(p, ip_sla_policy.POLICY_WORDS[p]) for p in profile.IP_SLA_POLICIES],
           "default_frequency": ip_sla_policy.DEFAULT_FREQUENCY}
    if ref is None:
        ctx["error"] = f"no list named {name!r}"
        return ctx
    ctx["policy"] = ip_sla_policy.policy_view(ref)
    if not chosen:
        # Opened from the tab: every device whose committed intent declares no
        # probe, said as such (a population the page chose is named).
        chosen, err = ip_sla_policy.without_probes(ref)
        ctx.update(chosen=chosen, defaulted=True, error=err)
        if err:
            return ctx
    if chosen and (ctx["policy"]["section"] or {}).get("policy"):
        try:
            got = ip_sla_policy.plan(ref, chosen)
        except ip_sla_policy.Refused as exc:
            ctx["error"] = str(exc)
        else:
            by_on = {}
            for s in got["suggestions"]:
                by_on.setdefault(s["on"], []).append(s)
            got["by_on"] = [{"on": on, "rows": rows, "cost": got["cost_by_device"].get(on, "")}
                            for on, rows in by_on.items()]
            ctx["plan"] = got
            ctx["commit_body"] = {"list": name, "devices": chosen,
                                  "fingerprint": got["fingerprint"]}
    return ctx


@bp.route("/monitoring/ip-sla", methods=["GET"])
def ip_sla():
    """The IP SLA policy and the probes it suggests for the devices chosen on
    Coverage (those running none)."""
    from flask import request
    return _page("v2/ip_sla.html", active_nav="monitoring", monitoring_tab="coverage",
                 **_ip_sla_ctx(request))


# ---------------------------------------------------------------------------
# Monitoring > Heartbeat (NSOT_PLAN P.7's heartbeat generator, as an action):
# re-measure every device's window, preview old against new, confirm, write
# the rules file, then the one host step with every value filled in.
# ---------------------------------------------------------------------------

def _heartbeat_ctx() -> dict:
    from modules import heartbeat_windows as HW
    ctx = {"plan": None, "error": "", "state": {}, "last": HW.last_written(), "host_step": ""}
    try:
        ctx["plan"] = HW.plan()
    except HW.Refused as exc:
        ctx["error"] = str(exc)
    except Exception as exc:                              # noqa: BLE001
        ctx["error"] = f"the measurement failed: {type(exc).__name__}: {exc}"
    path = (ctx["plan"] or {}).get("written_path", "")
    ctx["state"] = HW.state(path)
    if ctx["state"].get("pending"):
        ctx["host_step"] = HW.host_step(path or HW._script().OUT)
    return ctx


@bp.route("/monitoring/heartbeat", methods=["GET"])
def heartbeat():
    """Each device's heartbeat window: installed against measured now, the
    check's own verdict, and the re-measure's confirm."""
    return _page("v2/heartbeat.html", active_nav="attention",
                 **_heartbeat_ctx())


@bp.route("/monitoring/heartbeat/apply", methods=["POST"])
def heartbeat_apply():
    """Write the re-measured rules as the verified person, refusing a moved
    measurement; the page then names the host step that installs them."""
    from flask import jsonify, request

    from modules import heartbeat_windows as HW
    from modules import identity

    data = request.get_json(silent=True) or {}
    try:
        out = HW.apply(data.get("fingerprint") or "", identity.request_actor())
    except HW.Refused as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, **out})


def _ip_sla_ref(data):
    from modules.nsot import listref
    name = (data.get("list") or "").strip()
    if not name or not listref.exists(name):
        return None
    return listref.resolve(name)


@bp.route("/monitoring/ip-sla/policy", methods=["POST"])
def ip_sla_policy_set():
    """Commit the profile's IP SLA policy and frequency as the verified
    person, bound to the profile the page showed."""
    from flask import jsonify, request

    from modules import identity
    from modules.nsot import ip_sla_policy

    data = request.get_json(silent=True) or {}
    ref = _ip_sla_ref(data)
    if ref is None:
        return jsonify({"ok": False, "error": "no known list named: nothing was committed"}), 400
    try:
        freq = int(data.get("frequency"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "the frequency is a whole number of seconds: "
                                              "nothing was committed"}), 400
    if not 10 <= freq <= 3600:
        return jsonify({"ok": False, "error": "the frequency is 10 to 3600 seconds: nothing was "
                                              "committed"}), 400
    try:
        out = ip_sla_policy.set_policy(ref, (data.get("policy") or "").strip(), freq,
                                       identity.request_actor(), data.get("profile_hash") or "")
    except ip_sla_policy.Refused as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, **out})


@bp.route("/monitoring/ip-sla/commit", methods=["POST"])
def ip_sla_commit():
    """Commit the ticked suggestions into the devices' intent (one commit, as
    the verified person), refusing a plan that moved; answers with the scoped
    batch Apply that sends them."""
    from flask import jsonify, request, url_for

    from modules import identity
    from modules.nsot import ip_sla_policy

    data = request.get_json(silent=True) or {}
    ref = _ip_sla_ref(data)
    if ref is None:
        return jsonify({"ok": False, "error": "no known list named: nothing was committed"}), 400
    chosen = [d for d in (data.get("devices") or []) if isinstance(d, str) and d]
    picked = [k for k in (data.get("picked") or []) if isinstance(k, str) and k]
    try:
        out = ip_sla_policy.apply(ref, chosen, picked, data.get("fingerprint") or "",
                                  identity.request_actor())
    except ip_sla_policy.Refused as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    out["url"] = url_for("v2.profile_apply", list=ref.name, scope=ip_sla_policy.SCOPE,
                         device=out["devices"])
    return jsonify({"ok": True, **out})


# ---------------------------------------------------------------------------
# Devices (NSOT_GUI_BRIEF 3.3; step 4): the list, from a fixed number of
# reads whatever its size (modules/device_list.py).
# ---------------------------------------------------------------------------

def _devices_ctx(req) -> dict:
    from modules import device_list
    from modules.nsot import listref

    ref = listref.active()
    return {"d": device_list.listing(ref, q=req.args.get("q", ""),
                                     state=req.args.get("state", ""),
                                     platform=req.args.get("platform", "")),
            "list_name": ref.name, "states": device_list.STATES}


@bp.route("/devices", methods=["GET"])
def devices():
    """Devices: every device of the active list, pending onboardings among
    them, searchable and filtered; ticking rows raises the selection bar."""
    from flask import request
    return _page("v2/devices.html", active_nav="devices", **_devices_ctx(request))


@bp.route("/devices/table", methods=["GET"])
def devices_table():
    """The list alone: searched or filtered, or redrawn when a reader moves it.

    THE PERSON'S TICKS SURVIVE THE REDRAW (C472, C435's shape): a reader or another person's
    commit redraws the list, and the redraw sends its form, so a row is ticked exactly when
    its person had it ticked. Rows start unticked, so nothing joins a selection unseen."""
    from flask import request

    ctx = _devices_ctx(request)
    ticked = set(request.args.getlist("device"))
    for row in ctx["d"].get("rows") or []:
        row["checked"] = row.get("name") in ticked
    return _strict(render_template("v2/_devices.html", **ctx))
