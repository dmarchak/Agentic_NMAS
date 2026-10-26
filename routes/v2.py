"""routes/v2.py — the redesign's pages beyond the device page (option A,
approved 2026-09-30): the landing page (Needs attention) and Help > About.

Every route here is a READ under the strict policy, drawn from what the app
already computes: Needs attention is `attention.needs_attention()`, masked on
the way out (`outbound.mask_payload`; today's JSON `/attention` did the same until it left at
7.8, P7-27); About's version is
`routes.health.version_facts()`, the one composition (its JSON form, `/health/version`, left
with today's status bar at 7.8);
whether the running commit is what is pushed is the `app-pushed` reader.
"""

import logging
import os
import re
import subprocess

from flask import Blueprint, render_template, request
from modules.outbound import no_store
from html import escape

from routes.device_v2 import _strict, _who

log = logging.getLogger(__name__)

bp = Blueprint("v2", __name__, url_prefix="/v2")

@bp.app_template_filter("one_run")
def one_run(steps, name, label="Progress", device=True) -> dict:
    """A one-device operation's steps (`device_actions.job_steps`) as THE stepper's card
    (`run_stepper.single`), for `run_stepper(c.steps | one_run(c.host, 'Deploy progress'))`;
    *device* False for a device with no page to link to yet."""
    from modules import run_stepper
    return run_stepper.single(steps or [], name, label, device=bool(device))


@bp.app_template_filter("verify_verdict")
def verify_verdict(checks) -> dict:
    """A receipt's checks as THE verify verdict (`preview_confirm.verify_verdict`, C1541): the
    batch card draws the receipt's own decision, the one the device card and the level take."""
    from modules.preview_confirm import verify_verdict as verdict
    return verdict(checks or {})


@bp.app_template_filter("masked_parts")
def masked_parts(text) -> list:
    """A masked line as ``[(piece, is_a_mask)]``, so each masked value is marked where the line
    is drawn (board F3's Lines view). The pieces join back to *text* exactly."""
    from modules.redact import PLACEHOLDER

    mask = re.compile(re.escape(PLACEHOLDER).replace(re.escape("{label}"), r"[^<>\s]+"))
    text, out, at = str(text or ""), [], 0
    for m in mask.finditer(text):
        if m.start() > at:
            out.append((text[at:m.start()], False))
        out.append((m.group(0), True))
        at = m.end()
    if at < len(text) or not out:
        out.append((text[at:], False))
    return out


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

    # Rows quote their sources' own words: masked on the way out.
    return mask_payload(needs_attention())


def _recent() -> dict:
    """The last deploys and restores of the active list, from their receipts."""
    from modules.nsot import listref, receipts

    from modules.redact import redact_text

    ref = listref.active()
    got = receipts.read(ref.name, limit=RECENT_RECEIPTS)
    # The rows as the receipts hold them (masked at write), the reason masked again on the way
    # out (C1128: a row written before masking, or by hand, is the second layer's case, as
    # History's receipts are); the template reads device, action, outcome, at, actor, reason
    # and program_lines.
    rows = [dict(r, reason=redact_text(str(r["reason"]))) if r.get("reason") else r
            for r in got.get("rows") or []]
    return {"state": got["state"], "rows": rows, "list": ref.name}


def _page(template: str, **ctx):
    from modules.nsot import listref

    ctx.setdefault("list_name", listref.active().name)
    return _strict(render_template(template, who=_who(), **ctx))


@bp.route("/", methods=["GET"])
def landing():
    """Needs attention: what is wrong and what needs a person, worst first."""
    return _page("v2/landing.html", a=_attention(), recent=_recent(), active_nav="attention")


@bp.route("/recent", methods=["GET"])
def recent():
    """Recent changes alone, redrawn when a deploy or restore announces (C1189)."""
    return _strict(render_template("v2/_recent.html", recent=_recent()))


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
    from modules.attention import BEHIND_TOO_LONG_S
    return {"running": facts.get("running") or "", "subject": _subject(facts.get("running")),
            "started_at": facts.get("started_at"), "pid": os.getpid(),
            "version": facts.get("version") or {}, "ci": facts.get("ci") or {}, "pushed": pushed,
            "last_update": last, "check": check_state(),
            # When a host behind becomes a Needs attention row (the footer says it; the
            # operator's walk, 2026-10-18: the words said it always was).
            "behind_row_hours": BEHIND_TOO_LONG_S // 3600}


@bp.route("/help/about", methods=["GET"])
def about():
    """Help > About: the software, moved out of the top bar."""
    from modules import manual
    return _page("v2/about.html", inst=installation(), nav=manual.nav(), active_nav="help")


# ------------------------------------------------------------------ History
# (NSOT_GUI_BRIEF 3.4; board D, History as one timeline, signed off 2026-10-03, C369:
# modules/history_sources.timeline, the one reader behind this page and every device's tab)

#: Board D's tabs, and Query between Timeline and Baselines (C667: History › Query, boards A to
#: C on the canvas page "History, Query").
HISTORY_TABS = (("timeline", "Timeline"), ("query", "Query"), ("baselines", "Baselines"))
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._@+-]{1,128}$")


def _history_filters(request) -> dict:
    """The timeline's filters, each in the address so a view is a link. A device or person
    that is not a name is refused (said), never passed on."""
    from modules import history_sources as HS

    a = request.args
    since = a.get("since", "7")
    # A kind the reader does not know is ignored and said by name (the operator's walk,
    # 2026-10-18, B), never dropped unsaid.
    kinds, kind_error = HS.kind_filter(a.getlist("kind"))
    # The Commits tab became a kind (board D): its old links open the timeline on commits.
    if a.get("tab") == "commits" and not kinds:
        kinds = ["commits"]
    f = {"device": a.get("device", "").strip(), "person": a.get("person", "").strip(),
         "kinds": kinds,
         "since": since if since in [s for s, _w in HS.SINCE_CHOICES] else "7",
         "limit": a.get("limit", ""), "error": "",
         # 7.5's identity line: "unverified" keeps only the commits not signed in through the
         # access proxy; any other value is no filter.
         "identity": "unverified" if a.get("identity") == "unverified" else "",
         # 15.14 part B: the page's place (Load more's cursor, `before=<time>~<id>`), a day
         # jumped to (`on=YYYY-MM-DD`), and one AI call by its id (a feature's link to its
         # row), each in the address so Back and a shared link return to the same place.
         "before": a.get("before", "").strip(), "on": a.get("on", "").strip(),
         "call": a.get("call", "").strip()}
    errors = []
    for name in ("device", "person"):
        if f[name] and not _SAFE_NAME.match(f[name]):
            errors.append(f"the {name} filter {f[name]!r} is not a name")
            f[name] = ""
    for name, parse in (("before", HS.parse_cursor), ("on", HS.parse_day)):
        _place, err = parse(f[name])
        if err:
            errors.append(err)
            f[name] = ""
    f["before_at"] = f["before"].rpartition("~")[0]
    if f["call"] and not _CALL_ID.match(f["call"]):
        errors.append(f"the call {f['call'][:64]!r} is not an AI call's id")
        f["call"] = ""
    f["error"] = "; ".join(errors + ([kind_error] if kind_error else []))
    # Every filter the timeline's own addresses keep (its redraw, Load more's fragment and the
    # page address it pushes, Back to the newest): one list, so none drops one (15.14 part B:
    # Load more carries them all; the redraw had dropped `identity`). The address's own pairs,
    # (name, value), a value None left out by `url_for`.
    f["keep"] = [("device", f["device"] or None), ("person", f["person"] or None),
                 ("kind", f["kinds"] or None), ("since", f["since"]),
                 ("limit", f["limit"] or None), ("identity", f["identity"] or None),
                 ("on", f["on"] or None)]
    return f


#: An AI call's id (`modules/ai/calls.new_id`: "ai-" and hex), as the call filter takes it.
_CALL_ID = re.compile(r"^ai-[0-9a-f]{1,32}$")


#: What an uncommitted path is, by the folder it is in, and what clears it (C1136). Every write
#: Mercury makes commits in its own call, so a path left over is a finding.
_UNCOMMITTED_MEANS = {
    "golden": "a golden no save committed; readers of the working tree take it as the device's "
              "golden. Capture as golden on the device's page records what it holds through the "
              "save path.",
    "host_vars": "intent not committed; a deploy reads committed intent only. Save it from the "
                 "device's Intent tab to commit it.",
    "templates": "a template not committed; its approval is refused while it differs. Save it "
                 "again from Source of truth › Templates (Edit…).",
    ".nsot": "Mercury's own record (identity changes, reloads), committed with the network's "
             "next commit.",
}
_UNCOMMITTED_ELSE = ("nothing in Mercury writes here, so it was changed outside Mercury on this "
                     "host; whoever administers the host commits or removes it.")


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
    # An unreadable record is drawn as itself (C172): read as nothing, the card lost the last
    # failure and said nothing of why pushes stopped.
    rec, out["record_unreadable"] = NR.config_or_refusal(ref.name)
    # Whether a remote is RECORDED, for the set-up link's words: the reader's state cannot say
    # it before its first read ("not read" is not "no remote").
    out["configured"] = bool(rec)
    rec = rec or {}
    failure = rec.get("last_push_failure") or None
    if failure:
        failure = dict(failure, reason=redact_text(str(failure.get("reason") or "")))
    verify = rec.get("last_verify") or None
    if verify:
        # Each failed check's remedy as the check wrote it (C1016), masked like its detail.
        verify = dict(verify, failed=[dict(f, detail=redact_text(str(f.get("detail") or "")),
                                           fix=redact_text(str(f.get("fix") or "")))
                                      for f in verify.get("failed") or []])
    out.update(push_failure=failure, last_verify=verify, dirty_paths=[], dirty_items=[],
               no_repository=False, unreadable="")
    # A network with no repository yet (C945): its folder has no `.git`, the property
    # `repo.run_git` names when a read fails there (C931), decided by the folder and never by
    # git's words (`repo.has_repository`, the timeline's test too, C957). Its first commit
    # makes the repository; that is said, not "could not be read".
    if not R.has_repository(ref.repo_dir):
        out["no_repository"] = True
        return out
    rc, text, err = R.git(ref.repo_dir, "status", "--porcelain")
    if rc != 0:
        out["unreadable"] = redact_text(err or f"git status exited {rc}")
        return out
    # Parsed, never sliced: `repo.git` strips its output, so the first line's leading space
    # (" M golden/r1.cfg") is gone and a fixed column slice ate the path's first letter
    # ("olden/r1.cfg"). Today's Git tab's status (`config_git.get_repo_status`) had fixed it
    # there; found here rebasing its tests onto this header (7.8, 2026-10-17).
    paths = [m.group(2).split(" -> ")[-1].strip('"')
             for m in (re.match(r"^\s*(\S{1,2})\s+(.*)$", l) for l in (text or "").splitlines())
             if m]
    out["dirty"] = len(paths)
    # Named here, never "see today's Git tab" (C637): the first five, and how many more.
    out["dirty_paths"] = paths[:5]
    # Each with what it is and what clears it (C1136: today's Git tab said so, and left at 7.8,
    # P7-21), by the folder it is in; never a terminal step.
    out["dirty_items"] = [{"path": p, "means": _UNCOMMITTED_MEANS.get(
        p.split("/", 1)[0], _UNCOMMITTED_ELSE)} for p in paths[:5]]
    # Never "in sync" beside paths no commit holds (B5): the sentence says what is on the
    # remote and what is on this host only.
    out["d"] = RP.describe(pub, uncommitted=len(paths))
    return out


def _history_members(ref):
    """The network's devices, ``[]`` for a network with none, or None when its inventory
    cannot be read (absent and unreadable are different: the timeline then says so)."""
    from modules.device import load_saved_devices
    try:
        return sorted(d.get("hostname", "") for d in load_saved_devices(ref.csv_path)
                      if d.get("hostname"))
    except Exception as exc:                          # noqa: BLE001
        log.warning("v2 history: the inventory could not be read: %s", exc)
        return None


def _history_timeline(ref, f, members) -> dict:
    """THE timeline (C369), filtered as the address says. *members* as `_history_members`
    read them, passed AS READ: an empty network's ``[]`` keeps none of another network's rows
    (C1028: ``members or None`` made it "every network's"), and None (unreadable) lets the
    timeline read it again and say why it cannot."""
    from modules import history_sources as HS
    h = HS.timeline(ref, device=f["device"], person=f["person"], kinds=f["kinds"],
                    since_days=f["since"],
                    limit=int(f["limit"]) if str(f["limit"]).isdigit() else HS.DEFAULT_LIMIT,
                    members=members, unverified=f.get("identity") == "unverified",
                    before=HS.place(HS.parse_cursor(f.get("before"))[0],
                                    HS.parse_day(f.get("on"))[0]),
                    call=f.get("call", ""))
    # A filter not applied (`f["error"]`) is drawn by the timeline card as itself, "Not
    # applied: ...", never among the stores that could not be read: the rows are all there.
    return h


def _history_ctx(request) -> dict:
    from modules import history_sources as HS
    from modules import reader_job
    from modules.nsot import listref

    ref = listref.active()
    tab = request.args.get("tab", "timeline")
    if tab == "commits":
        tab = "timeline"
    if tab not in [t for t, _l in HISTORY_TABS]:
        tab = "timeline"
    f = _history_filters(request)
    ctx = {"tab": tab, "tabs": HISTORY_TABS, "f": f, "ref": ref,
           "remote": _history_remote(ref), "since_choices": HS.SINCE_CHOICES,
           "kind_groups": HS.KIND_GROUPS, "quick_kinds": HS.QUICK_KINDS}
    if tab == "timeline":
        members = _history_members(ref)
        ctx["devices"] = members or []
        ctx["h"] = _history_timeline(ref, f, members)
    elif tab == "query":
        from modules import history_query
        ctx["lib"] = history_query.library(ref.name)
    elif tab == "baselines":
        got = reader_job.read_cached("baseline-usability")
        good = (got.get("doc") or {}).get("last_good") or {}
        ctx["b"] = (((good.get("value") or {}).get("lists") or {}).get(ref.name) or {})
        ctx["b_at"] = good.get("value_at")
    return ctx


# ---------------------------------------------------------------------------
# History › Baselines › Re-apply… (a nice-to-have after the cutover blockers, 2026-10-10; drawn
# under the Phase 7 mode): every device a baseline holds, restored to it as ONE batch, through
# THE restore plan (`routes.golden.restore_plan`) and the restore job a device's own Restore
# runs (`deploy_job.start_restore`). The page is the preview; the confirm starts the job.
# ---------------------------------------------------------------------------

#: A device's row on the re-apply page: why it is, or is not, part of the batch.
REAPPLY_STATES = {"ready": ("will be restored", "ok"),
                  "needs_reason": ("needs a stated reason: restore it on its own page", "warn"),
                  "blocked": ("blocked: nothing is sent", "danger"),
                  "nothing": ("already as the baseline holds it", "muted")}


def _reapply_ctx(req) -> dict:
    """The baseline's re-apply, planned: every device's program and checks (masked on the way
    out, after every hash is computed), the counts by state first, and the confirm body built
    HERE from the hashes drawn, for the devices that can go as they are."""
    from modules.nsot import listref
    from modules.nsot.restore import WithdrawnBaseline
    from modules.outbound import mask_payload
    from routes.golden import restore_plan
    from routes.list_param import named_list

    name = named_list(req) or listref.active().name
    tag = (req.args.get("tag") or "").strip()
    ctx = {"list_name": name, "tag": tag, "rows": [], "counts": {}, "error": "",
           "confirm_body": None, "states": REAPPLY_STATES, "skipped": []}
    if not tag.startswith("baseline/"):
        ctx["error"] = f"{tag or 'nothing'} is not a baseline: a re-apply names a baseline tag"
        return ctx
    try:
        plan = restore_plan(name, tag, None, req=req)
    except WithdrawnBaseline as exc:
        ctx["error"] = str(exc)
        return ctx
    shown = mask_payload(plan)
    rows, ready = [], []
    for raw, d in zip(plan.get("devices") or [], shown.get("devices") or []):
        intent = d.get("intent") or {}
        if d.get("error") or not d.get("deployable") or d.get("busy"):
            state = "blocked"
        elif d.get("authorisation_ok") is False:
            state = "needs_reason"
        elif not d.get("commands") and intent.get("action") != "restore":
            state = "nothing"
        else:
            state = "ready"
            ready.append(raw)
        rows.append({"name": d.get("device", ""), "state": state,
                     "program": d.get("commands") or [], "error": d.get("error", ""),
                     "blocking": list(d.get("blocking_reasons") or [])
                     + ([d["busy"]] if d.get("busy") else []),
                     "checks": d.get("checks") or [], "intent": intent,
                     "residue": len(d.get("residue") or []),
                     "excluded": d.get("excluded_unrenderable") or []})
    ctx["rows"] = sorted(rows, key=lambda r: (list(REAPPLY_STATES).index(r["state"]),
                                              r["name"]))
    ctx["counts"] = {s: sum(1 for r in rows if r["state"] == s) for s in REAPPLY_STATES}
    ctx["skipped"] = [{"name": s.get("hostname", ""),
                       "why": s.get("reason") or ("the baseline predates it"
                                                  if s.get("not_at_ref") else "")}
                      for s in (plan.get("skipped") or [])]
    if ready:
        ctx["confirm_body"] = {"list": name, "tag": tag,
                               "confirmations": {d["device"]: d.get("capture_hash", "")
                                                 for d in ready},
                               "command_hashes": {d["device"]: d.get("command_hash", "")
                                                  for d in ready}}
    from modules.preview_confirm import confirm_part
    ctx["may"] = confirm_part(req, "confirm")
    return ctx


@bp.route("/history/reapply", methods=["GET"])
def history_reapply():
    """Re-apply a baseline: the preview of every device it holds, restored to it as one batch.
    A READ: the plan reads captured configs only."""
    from flask import request
    return _page("v2/reapply.html", active_nav="history", **_reapply_ctx(request))


@bp.route("/history/reapply/confirm", methods=["POST"])
def history_reapply_confirm():
    """Start the confirmed re-apply as a job, as the verified person: each device's program is
    computed again and a different hash refuses that device alone, with nothing sent to it
    (`deploy_job.start_restore`, a device's own Restore's job). Posted by htmx from the page's
    confirm, the body the page drew in its fields (C850); answers 202 with the job's card,
    drawn in place below the preview, or 400 with the refusal and nothing sent."""
    from flask import request

    from modules import deploy_job, identity
    from modules.nsot import listref

    form = request.form
    list_name, tag = (form.get("list") or "").strip(), (form.get("tag") or "").strip()
    if not list_name or not listref.exists(list_name) or not tag.startswith("baseline/"):
        return _apply_answer("", 400, refused=(
            "Nothing was sent: the confirm names no known network and baseline "
            f"({list_name or 'no network'}, {tag or 'no baseline'})."))
    try:
        data = _confirm_fields(form, ("confirmations", "command_hashes"))
    except ValueError as exc:
        return _apply_answer("", 400, refused=f"Nothing was sent: {exc}.")
    confirmations, hashes = data["confirmations"], data["command_hashes"]
    if not confirmations or any(not hashes.get(d) for d in confirmations):
        return _apply_answer("", 400, refused=(
            "Nothing was sent: every device needs the capture and command hashes its preview "
            "showed."))
    job = deploy_job.start_restore(
        list_name, tag, confirmations, hashes, authorise={}, un_onboard=None,
        actor=identity.request_actor(),
        actor_kind=getattr(identity.identify(request), "kind", ""),
        ident=identity.verified_identity())
    return _apply_answer(job, 202, started_op="restore")


@bp.route("/history", methods=["GET"])
def history_page():
    """History: one timeline of everything that happened to the network and its devices,
    its baselines and authorisations, with the remote's state at the top."""
    from flask import request
    return _page("v2/history.html", active_nav="history", **_history_ctx(request))


@bp.route("/history/query/syslog", methods=["GET"])
def history_query_syslog():
    """History › Query › Syslog by device (board C, AskLogs): the logs reader's stored counts,
    and a device's lines from Loki when it is opened. A read; the view redraws through
    `logs_v2.region` when the reader announces `logs`."""
    from flask import request

    return _page("v2/history_syslog.html", active_nav="history", **syslog_ctx(request))


@bp.route("/history/query/metric/<key>", methods=["GET"])
def history_query_metric(key):
    """History › Query › a metrics question (board B, AskMetric): the question, its device and
    interface, the range, and the chart, which reads `history_query_metric_data`. A read."""
    from flask import abort, request

    from modules import history_query
    from modules.nsot import listref
    from routes.list_param import named_list

    if history_query.question(key) is None:
        abort(404)
    ref = listref.active()
    m = history_query.metric_view(key, named_list(request) or ref.name, request.args)
    return _page("v2/history.html", active_nav="history", tab="query", tabs=HISTORY_TABS,
                 ref=ref, remote=_history_remote(ref), f=_history_filters(request), metric=m)


@bp.route("/history/query/metric/<key>/data", methods=["GET"])
def history_query_metric_data(key):
    """The question's series for the chart (the Monitoring panel's payload): the question's
    PromQL, never the browser's, asked of the network's Grafana. A read."""
    from flask import jsonify, request

    from modules import history_query
    from modules.nsot import listref
    from routes.list_param import named_list

    payload, code = history_query.metric_data(key, named_list(request) or listref.active().name,
                                              request.args)
    return jsonify(payload), code


# ---------------------------------------------------------------------------
# History › Query › Ask your own, the logs builder (board F3, QueryBuilderLogs3, approved
# 2026-10-15; modules/history_logq.py): the choices in the address, the query Mercury forms
# from them, and, asked, the answer. Reads: nothing is written and no list is created.
# ---------------------------------------------------------------------------

def _ask_logs_ctx(q: dict = None) -> dict:
    from modules import history_logq
    from modules.nsot import listref
    from routes.list_param import named_list

    ref = listref.active()
    if q is None:
        q = history_logq.view(named_list(request) or ref.name, request.args)
    _words_model(q)
    return {"tab": "query", "tabs": HISTORY_TABS, "ref": ref, "remote": _history_remote(ref),
            "f": _history_filters(request), "ask_logs": True, "q": q}


def _words_model(q: dict) -> None:
    """Ask in words' row on either builder: the result so far (none) and the model it calls."""
    from modules.ai import profiles

    pin = profiles.task("nl_query")
    q.setdefault("words", None)
    q["words_model"] = f"{profiles.profile(pin['model'])['words']}, {pin['model']}"


@bp.route("/history/query/ask/logs", methods=["GET"])
def history_ask_logs():
    """History › Query › Ask your own, logs (board F3): the builder, the query as the choices
    form it, and the answer once asked. A read."""
    return _page("v2/history_ask_logs.html", active_nav="history", **_ask_logs_ctx())


@bp.route("/history/query/ask/logs/region", methods=["GET"])
def history_ask_logs_region():
    """The builder and its answer alone, redrawn as a choice is made or Ask is pressed; the
    page's own address for the choices is pushed, so what is drawn is a link. A read."""
    from flask import url_for

    ctx = _ask_logs_ctx()
    resp = _strict(render_template("v2/_history_ask_logs.html", **ctx))
    resp.headers["HX-Push-Url"] = url_for("v2.history_ask_logs") + ctx["q"]["qs"]()
    return resp


@bp.route("/history/query/ask/logs/reveal", methods=["POST"])
@no_store
def history_ask_logs_reveal():
    """Reveal one log line (C818; board F3's Reveal…): to a verified person with a stated
    reason, the line read from Loki again by its stream and time, recorded before it is drawn
    (modules/log_reveal.py), drawn in place under its row and kept nowhere."""
    from modules import identity, log_reveal
    from modules.nsot import listref

    ident, refused = identity.require(request, "reveal", operation="log_line")
    name = (request.form.get("list") or "").strip()
    if name and not listref.exists(name):
        c, status = log_reveal.refusal(request.form, f"there is no network named "
                                                     f"{name[:60]!r}: nothing was read"), 404
    else:
        c, status = log_reveal.reveal(name or listref.active().name, request.form, ident,
                                      refused=refused)
    return _strict(render_template("v2/_history_reveal.html", c=c), status)


# ---------------------------------------------------------------------------
# History › Query › Ask your own, the metrics builder (board E3, QueryBuilderMetrics3, approved
# 2026-10-15; modules/history_promq.py): the choices in the address, the PromQL Mercury forms
# from them, and, asked, the answer. Reads: nothing is written and no list is created.
# ---------------------------------------------------------------------------

def _ask_metrics_ctx(q: dict = None) -> dict:
    from modules import history_promq
    from modules.nsot import listref
    from routes.list_param import named_list

    ref = listref.active()
    if q is None:
        q = history_promq.view(named_list(request) or ref.name, request.args)
    _words_model(q)
    return {"tab": "query", "tabs": HISTORY_TABS, "ref": ref, "remote": _history_remote(ref),
            "f": _history_filters(request), "ask_metrics": True, "q": q}


@bp.route("/history/query/ask/metrics", methods=["GET"])
def history_ask_metrics():
    """History › Query › Ask your own, metrics (board E3): the builder, the PromQL as the
    choices form it, and the answer once asked. A read."""
    return _page("v2/history_ask_metrics.html", active_nav="history", **_ask_metrics_ctx())


@bp.route("/history/query/ask/metrics/region", methods=["GET"])
def history_ask_metrics_region():
    """The metrics builder and its answer alone, redrawn as a choice is made or Ask is
    pressed; the page's own address for the choices is pushed, so what is drawn is a link.
    A read."""
    from flask import url_for

    ctx = _ask_metrics_ctx()
    resp = _strict(render_template("v2/_history_ask_metrics.html", **ctx))
    resp.headers["HX-Push-Url"] = url_for("v2.history_ask_metrics") + ctx["q"]["qs"]()
    return resp


@bp.route("/history/query/ask/metrics/words", methods=["POST"])
def history_ask_metrics_words():
    """Ask in words (PHASE8_PLAN feature 1, 8.1; modules/ai/nl_query.py): the question becomes
    the builder's choices through the AI gateway, one recorded call as the person who asked,
    read back by the builder and test-run; the region is drawn filled and its address pushed.
    Nothing runs as an answer until the person presses Ask. Refused, the builder is drawn as
    it was (the form carries its choices) with the reason."""
    from modules import history_promq
    from modules.ai import nl_query

    def fill(name, question, actor):
        # "Today" is midnight in the viewer's browser's timezone (the form's `tz`, or its
        # `tz_off` minutes east of UTC), until an installation timezone exists (C1740).
        return nl_query.metrics(name, question, actor=actor, viewer_zone=nl_query.zone(
            request.form.get("tz", ""), request.form.get("tz_off", "")))
    return _ask_words(fill, history_promq.view, "v2/_history_ask_metrics.html",
                      _ask_metrics_ctx, "v2.history_ask_metrics")


@bp.route("/history/query/ask/logs/words", methods=["POST"])
def history_ask_logs_words():
    """Ask in words on the logs builder (8.1's LogQL half): as the metrics builder's, the
    logs builder filled, read back and test-run; nothing runs until Ask."""
    from modules import history_logq
    from modules.ai import nl_query

    def fill(name, question, actor):
        # The named days and weeks in the viewer's browser's timezone, as the metrics
        # builder's (C1740).
        return nl_query.logs(name, question, actor=actor, viewer_zone=nl_query.zone(
            request.form.get("tz", ""), request.form.get("tz_off", "")))
    return _ask_words(fill, history_logq.view, "v2/_history_ask_logs.html",
                      _ask_logs_ctx, "v2.history_ask_logs")


def _ask_words(fill, view, template: str, ctx, page: str):
    """Both builders' Ask in words, one path: the network the form names (refused, with the
    builder drawn on the active one, 409), the fill as the person who asked, the region drawn
    with the result and, filled, its address pushed."""
    from flask import url_for

    from modules import identity
    from modules.ai import nl_query
    from modules.nsot import listref
    from routes.list_param import submitted_list

    name, refused = submitted_list(request)
    question = request.form.get("words", "")
    if refused:
        got = {"ok": False, "error": "network", "detail": refused}
        q = view(listref.active().name, request.form)
    else:
        got = fill(name, question, actor=identity.request_actor())
        if got["ok"]:
            q = got.pop("view")
            q["errors"] = got["errors"]
        else:
            q = view(name, request.form)
    got["question"] = " ".join(question.split())[:nl_query.QUESTION_MAX]
    q["words"] = got
    resp = _strict(render_template(template, **ctx(q)))
    if refused:
        return resp, 409
    if got["ok"]:
        resp.headers["HX-Push-Url"] = url_for(page) + q["qs"]()
    return resp


# ---------------------------------------------------------------------------
# History › Query's saved views (C667; board A's "Saved by your team", board B's "Save this
# view…"): links to reads, kept per network (modules/saved_views.py). Each write answers with
# what it did, in place, and announces `saved_views`, on which the list redraws.
# ---------------------------------------------------------------------------

def _views_region(status: int = 200, op: dict = None, name: str = ""):
    from modules import saved_views
    from modules.nsot import listref
    from routes.list_param import named_list

    name = name or named_list(request)
    if not name or not listref.exists(name):
        name = listref.active().name          # a refused write's network may be none
    op = op or {}
    html = render_template("v2/_history_views.html", views=saved_views.read(name),
                           list_name=name, op=op)
    if request.method == "POST":
        html += "\n" + render_template("v2/_history_views_result.html", op=op)
    return _strict(html), status


def _save_slot(status: int = 200, **op):
    return _strict(render_template("v2/_history_save.html", op=op)), status


@bp.route("/history/query/views", methods=["GET"])
def history_views():
    """Saved by your team, redrawn when `saved_views` is announced. A read."""
    return _views_region()


@bp.route("/history/query/views/remove", methods=["GET"])
def history_view_remove_form():
    """Remove…: what removing does, asked in place; nothing written."""
    return _views_region(op={"state": "removing", "id": (request.args.get("id") or "").strip()})


@bp.route("/history/query/views/save", methods=["GET"])
def history_view_save_form():
    """Save this view…: a title asked, in place; nothing written. The form carries the page's
    network, so the save lands on it (C838)."""
    from modules.nsot import listref
    from routes.list_param import named_list

    return _save_slot(state="form", address=(request.args.get("address") or "").strip(),
                      list_name=named_list(request) or listref.active().name)


@bp.route("/history/query/views", methods=["POST"])
def history_view_save():
    """Save the view the page shows, with a title, for the network its form names (C838), as
    the verified person; recorded."""
    from modules import identity, saved_views
    from routes.list_param import submitted_list

    where = (request.form.get("address") or "").strip()
    name, refused = submitted_list(request)
    if refused:
        return _save_slot(409, state="form", address=where, refused=refused,
                          title=request.form.get("title", ""),
                          list_name=(request.form.get("list") or "").strip())
    got = saved_views.save(name, request.form.get("title", ""), where,
                           identity.request_actor())
    if not got["ok"]:
        return _save_slot(400, state="form", address=where, refused=got["error"],
                          title=request.form.get("title", ""), list_name=name)
    return _save_slot(state="saved", view=got["view"], record_error=got["record_error"],
                      list_name=name)


@bp.route("/history/query/views/<view_id>/pin", methods=["POST"])
def history_view_pin(view_id):
    """Pin or unpin a view, for everyone, on the network its form names (C838), as the
    verified person; recorded."""
    from modules import identity, saved_views
    from routes.list_param import submitted_list

    name, refused = submitted_list(request)
    if refused:
        return _views_region(409, op={"state": "refused", "refused": refused})
    pinned = request.form.get("pinned") == "1"
    got = saved_views.pin(name, view_id, pinned, identity.request_actor())
    if not got["ok"]:
        return _views_region(409, op={"state": "refused", "refused": got["error"]}, name=name)
    return _views_region(op=dict(got, state=got["action"]), name=name)


@bp.route("/history/query/views/<view_id>/remove", methods=["POST"])
def history_view_remove(view_id):
    """Remove a view, on the network its form names (C838), as the verified person: only the
    saved link goes, the history it asks is untouched; recorded."""
    from modules import identity, saved_views
    from routes.list_param import submitted_list

    name, refused = submitted_list(request)
    if refused:
        return _views_region(409, op={"state": "refused", "refused": refused})
    got = saved_views.remove(name, view_id, identity.request_actor())
    if not got["ok"]:
        return _views_region(409, op={"state": "refused", "refused": got["error"]}, name=name)
    return _views_region(op=dict(got, state="removed"), name=name)


def syslog_ctx(request) -> dict:
    """History › Query › Syslog by device's context, for its home and for the sidebar's Logs,
    which draws the same page (C667): only what the tab draws, never the timeline's reads."""
    from modules import logs_page
    from modules.nsot import listref
    from routes.list_param import named_list

    ref = listref.active()
    return {"tab": "query", "tabs": HISTORY_TABS, "ref": ref, "remote": _history_remote(ref),
            "f": _history_filters(request), "syslog": True,
            "g": logs_page.view(named_list(request) or ref.name, request.args)}


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


@bp.route("/history/timeline/more", methods=["GET"])
def history_timeline_more():
    """Load more (15.14 part B): the next rows older than the address's place (`before`, the
    last row shown), filtered as the address says, appended in place under the rows shown,
    with the next Load more. A read; its button pushes the History page's own address with
    the same place, so Back and a shared link return to it."""
    from flask import request

    from modules.nsot import listref
    ref = listref.active()
    f = _history_filters(request)
    return _strict(render_template("v2/_history_timeline.html", page_only=True,
                                   h=_history_timeline(ref, f, _history_members(ref)), f=f))


@bp.route("/history/ai-call/<call_id>", methods=["GET"])
def history_ai_call(call_id):
    """One AI call's prompt as sent and answer as received, masked (15.14), drawn when a
    person opens its row, as a commit's change is."""
    from modules import history_sources as HS
    return _strict(render_template("v2/_history_ai_call.html", c=HS.ai_call(call_id)))


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
            "check": check_state(),
            "update_run": update_op.run_card(p["facts"].get("target") or ""),
            "updater_timeout_s": update_op.UPDATER_TIMEOUT_S,
            # The host steps the person ticked, carried through a live redraw (C472): the
            # panel's redraw sends its boxes, and each stays ticked exactly when it was. The
            # confirm's own answer (routes/update.py) carries the boxes it posted the same way.
            "host_steps_ticked": set(request.values.getlist("host_step"))}


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

    ref = listref.active()
    c = monitoring_coverage.fleet(ref)
    c["not_covered"] = _not_covered(ref, c)
    return c


def _not_covered(ref, c: dict) -> list:
    """C718's board A: each device whose IP SLA is not in its intent, and why, in the IP SLA
    page's own words (its suggestion for the device, or why it suggests none), so the row can
    offer Add to intent… and Decline… beside it. One computation from committed intent."""
    from modules.nsot import ip_sla_policy

    hosts = c.get("ip_sla_missing") or []
    if not hosts:
        return []
    try:
        p = ip_sla_policy.plan(ref, hosts)
    except ip_sla_policy.Refused as exc:
        return [{"host": h, "section": "ip_sla", "why": str(exc), "suggested": False}
                for h in hosts]
    out = []
    for h in hosts:
        mine = [s for s in p.get("suggestions") or [] if s.get("on") == h]
        skipped = [s["why"] for s in p.get("skipped") or [] if s.get("device") == h]
        why = ("; ".join(s["why"] for s in mine) if mine else
               "; ".join(skipped) or "the policy suggests no probe for it")
        out.append({"host": h, "section": "ip_sla", "why": why, "suggested": bool(mine)})
    return out


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


# ── Monitoring › Profile (C566, board A, signed off 2026-10-07) ──────────────────────────────

def _profile_ctx(op: dict = None) -> dict:
    from modules import monitoring_profile_page as MP
    from modules.nsot import listref

    return {"p": MP.sections(listref.active()), "op": op}


def _profile_op(list_name: str, refused: str = "", choose: dict = None) -> dict:
    from modules import monitoring_profile_page as MP, preview_confirm
    from modules.nsot import profile as _p

    try:
        q = MP.proposal(list_name, choose=choose)
    except _p.ProfileRefused as exc:
        return {"state": "refused", "why": (f"{list_name}'s committed profile cannot be read, so "
                                            f"nothing is proposed: {exc}")}
    return {"state": "propose", "q": q, "may": preview_confirm.confirm_part(request, "approve"),
            "refused": refused}


@bp.route("/monitoring/profile", methods=["GET"])
def monitoring_profile():
    """Monitoring › Profile: the committed profile, section by section, with how many devices
    hold each; ``propose=1`` opens Propose's card in place (the button's link, and a deep link),
    with any ``choose`` of a section's version (C1269) the link carries."""
    from modules import monitoring_profile_page as MP
    from modules.nsot import listref

    op = (_profile_op(listref.active().name,
                      choose=MP.parse_choose(request.args.getlist("choose")))
          if request.args.get("propose") == "1" else None)
    return _page("v2/monitoring_profile.html", active_nav="monitoring",
                 monitoring_tab="profile", **_profile_ctx(op))


@bp.route("/monitoring/profile/table", methods=["GET"])
def monitoring_profile_table():
    """The region (the table, no card): what Cancel and Close put back."""
    return _strict(render_template("v2/_profile.html", **_profile_ctx()))


@bp.route("/monitoring/profile/rows", methods=["GET"])
def monitoring_profile_rows():
    """The table alone, re-read when intent, goldens or templates move; the card below is left
    as it is. Writes nothing."""
    return _strict(render_template("v2/_profile_table.html", **_profile_ctx()))


@bp.route("/monitoring/profile/propose", methods=["GET"])
def profile_propose_form():
    """Propose from the connectors: the preview, `profile_propose.propose`, with whether the
    network's templates render each changed section. Writes nothing. ``choose`` (repeated,
    ``<section>:<version id>``) is a person's choice between the versions of a section's shared
    fields the devices hold (C1269), previewed here and carried to the confirm."""
    from modules import monitoring_profile_page as MP
    from modules.nsot import listref

    name = (request.args.get("list") or "").strip() or listref.active().name
    return _strict(render_template("v2/_profile_op.html", op=_profile_op(
        name, choose=MP.parse_choose(request.args.getlist("choose")))))


@bp.route("/monitoring/profile/propose", methods=["POST"])
def profile_propose_commit():
    """The confirm: the proposal recomputed and refused when it moved, else committed as the
    verified person; the region redrawn with the result. The list is CARRIED from the card."""
    from modules import identity, monitoring_profile_page as MP

    name = (request.form.get("list") or "").strip()
    confirmed = (request.form.get("hash") or "").strip()
    if not name or not confirmed:
        op = {"state": "refused", "why": "No list or no proposal was named: nothing committed."}
        return _strict(render_template("v2/_profile.html", **_profile_ctx(op)), 400)
    actor = identity.request_actor()
    # The version choices the card previewed (C1269): in the hash, so a confirm carrying other
    # choices than it previewed is refused as moved.
    choose = MP.parse_choose(request.form.getlist("choose"))
    out = MP.commit(name, confirmed, actor, choose=choose)
    if out.get("outcome") == "committed":
        op = {"state": "committed", "r": out, "actor": actor}
        code = 200
    elif out.get("outcome") == "moved":
        op, code = _profile_op(name, refused=out.get("reason", ""), choose=choose), 409
    else:
        op = {"state": "refused", "why": out.get("reason") or out.get("why") or out.get("outcome")}
        code = 409 if out.get("outcome") != "nothing" else 200
    return _strict(render_template("v2/_profile.html", **_profile_ctx(op)), code)


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
# Monitoring > Alerts: every firing alert with the evidence pack Mercury gathered when it began
# (PHASE8_PLAN 15.9, P1, no AI; modules/evidence_pack.py). Reads only: the alerts reader's
# stores and the pack store, once each; the pack itself opens on expand.
# ---------------------------------------------------------------------------

_PACK_KEY = re.compile(r"^[0-9a-f]{20}$")


def _alerts_ctx() -> dict:
    from modules import evidence_pack

    want = request.args.get("open", "")
    return {"e": evidence_pack.tab(request.args.get("q", "")),
            "open_key": want if _PACK_KEY.match(want) else ""}


@bp.route("/monitoring/alerts", methods=["GET"])
def monitoring_alerts():
    """Monitoring > Alerts: each firing alert, grouped, a closed card with its pack."""
    return _page("v2/monitoring.html", active_nav="monitoring", monitoring_tab="alerts",
                 **_alerts_ctx())


@bp.route("/monitoring/alerts/list", methods=["GET"])
def monitoring_alerts_list():
    """The list alone, re-fetched when the alerts reader announces."""
    return _strict(render_template("v2/_alert_evidence.html", **_alerts_ctx()))


@bp.route("/monitoring/alerts/pack/<pack_id>", methods=["GET"])
def monitoring_alert_pack(pack_id):
    """One pack, drawn in its card when the card opens; one that is not kept says so, in
    place (404)."""
    from modules import evidence_pack

    pid = pack_id[:64]
    pack, state, error = (evidence_pack.find(pid) if pid.startswith("ep-")
                          else (None, "ok", ""))
    html = render_template("v2/_evidence_pack.html", pack=pack, state=state, error=error,
                           pid=pid, intact=evidence_pack.intact(pack) if pack else False,
                           explain_model=_explain_model())
    return _strict(html, 200 if pack else 404)


def _explain_model() -> str:
    from modules.ai import profiles

    pin = profiles.task("explain")
    return f"{profiles.profile(pin['model'])['words']}, {pin['model']}"


@bp.route("/monitoring/alerts/pack/<pack_id>/explain", methods=["POST"])
def monitoring_alert_explain(pack_id):
    """Explain (PHASE8_PLAN 15.9, P1's one AI step; modules/ai/explain.py): the pack's
    hypotheses, each citing it, from one recorded call as the person who pressed Explain,
    drawn in the pack; a refusal says why in place. Nothing runs."""
    from modules import identity
    from modules.ai import explain

    got = explain.explain(pack_id[:64], actor=identity.request_actor())
    return _strict(render_template("v2/_explain.html", x=got, explain_model=_explain_model()))


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
    # Devices › Plan a deploy for the ticked devices (7.4's board B, signed off 2026-10-04;
    # built 2026-10-10): each device's WHOLE committed intent, merge-only, in a rollout order.
    "intent": {"title": "Deploy committed intent",
               "sub": ("To the devices ticked on Devices, one at a time in the order below. Each "
                       "receives exactly the program shown: what its committed intent renders "
                       "that it lacks, verified and rolled back alone if it fails."),
               "has_all": "it already holds everything its committed intent renders",
               "only": "Merge-only: nothing on a device is removed.",
               "none_can": "No device here can be deployed to now: each says why above.",
               "all_nothing": ("Nothing to deploy: every device chosen already holds everything "
                               "its committed intent renders.")},
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


#: The page's scope -> the deploy plan's (`routes.deploy.SCOPES`): `intent` is the whole
#: committed intent, the plan's empty scope, named here so it is never a default.
PLAN_SCOPE = {"intent": ""}


def plan_scope(scope: str) -> str:
    return PLAN_SCOPE.get(scope, scope)


def _scope(req=None) -> str:
    """The scope the request carries (the preview's form, or the confirm's
    body), `profile` when none is named. An unknown one is refused, never
    read as the profile (a lookup that misses is a fact about the query)."""
    from modules.nsot import profile_apply
    if req is None:
        return profile_apply.SCOPE
    got = req.args.get("scope")
    if got is None and req.method == "POST":
        got = req.form.get("scope")
    got = (got or profile_apply.SCOPE).strip()
    if got not in SCOPE_WORDS:
        raise UnknownScope(f"unknown scope {got!r}: this page applies "
                           + " or ".join(sorted(SCOPE_WORDS)) + "; nothing was planned or sent")
    return got


def _apply_args(req, names: list = None) -> dict:
    """What the preview form carries: the list, the devices in the rollout
    order (a move or a leave-out applied), the superseded lines ticked for
    removal (by id) and each one's stated reason. A `move` comes from Coverage's
    combined deploy (`_coverage_deploy_preview.html`); the batch Apply's preview
    reorders in the page and sends its devices in the order shown (C888). *names*, when
    given, are the devices in place of the request's (Devices' all matching, resolved by
    `devices_deploy`)."""
    from routes.list_param import named_list

    order = []
    for d in (req.args.getlist("device") if names is None else names):
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
                   "management": "Management sources",
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


def _apply_ctx(req, scope: str = None, names: list = None) -> dict:
    """The batch preview: every device's profile-scoped plan, as
    `routes.deploy.plan_devices` with scope `profile` computes it, masked on the way out
    AFTER every hash is computed, and the confirm body built from those
    hashes, so the confirm sends exactly what this preview showed."""
    from modules.nsot import listref
    from modules.outbound import mask_payload
    from modules.preview_confirm import deploy_preview
    from routes.deploy import plan_devices

    args = _apply_args(req, names)
    scope = scope or _scope(req)
    list_name = args["list"] or listref.active().name
    ctx = {"list_name": list_name, "order": args["order"], "rows": [], "preview": None,
           "confirm_body": None, "ready": [], "scope": scope, "words": SCOPE_WORDS[scope]}
    if not args["order"]:
        return ctx
    devices = plan_devices(list_name, args["order"], remove=args["picked"], scope=plan_scope(scope))
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
                               authorise=authorise, scope=plan_scope(scope))
    preview = deploy_preview(devices, req, scope=plan_scope(scope))
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


#: The confirm body's structured fields, each sent as JSON in its own form field (C850: the
#: preview draws them into the confirm's `hx-vals`, as the device page's Deploy does), and what
#: each is when absent.
CONFIRM_JSON_FIELDS = {"order": [], "confirmations": {}, "command_hashes": {}, "remove": {},
                       "authorise": {}}


def _confirm_fields(form, names) -> dict:
    """The confirm's structured fields, read from *form*: {name: value}. A field that is not
    JSON of its kind raises ValueError naming it."""
    import json

    out = {}
    for name in names:
        default = CONFIRM_JSON_FIELDS[name]
        raw = form.get(name)
        try:
            value = json.loads(raw) if raw else default
        except ValueError:
            raise ValueError(f"the field {name} is not readable JSON") from None
        if not isinstance(value, type(default)):
            raise ValueError(f"the field {name} is not a {type(default).__name__}")
        out[name] = value
    return out


def _apply_answer(job: str, code: int = 200, started_op: str = "", refused: str = ""):
    """The batch's card (`v2/_apply_job.html`): where it is, then its result; or, as the
    confirm's answer, the batch just started (the confirm drawn again as started) or the
    confirm refused with nothing sent."""
    if refused:
        return _strict(render_template("v2/_apply_job.html", j=None, job="", run=None,
                                       arrivals=None, refused=refused), code)
    from modules import arrival_watch, deploy_job
    got = deploy_job.state(job)
    if got and not (got.get("list") or "").strip():
        # C839: a record naming no network is refused, naming that, never a 500: where its
        # devices are held, and so where it is, is read in a network.
        return _strict(str(escape(
            f"Couldn't load: the batch {job} has a record that names no network (its `list` "
            "is missing or empty), so where it is cannot be read. What each device received "
            "is in its receipts and in the golden history.")), 409)
    run = deploy_job.run_card(got, got["list"], q=request.args.get("q", "")) if got else None
    # C1499: a finished batch on a scope this page previews offers each failed device's Retry:
    # a new preview of that device alone, never a resend of this batch's hash.
    scope = (got or {}).get("scope") or ""
    retry = deploy_job.failed_devices(got) if scope in SCOPE_WORDS else []
    return _strict(render_template("v2/_apply_job.html", j=got, job=job, run=run,
                                   arrivals=arrival_watch.state(job), started_op=started_op,
                                   retry=retry, retry_scope=scope),
                   code if got or started_op else 404)


@bp.route("/monitoring/apply/confirm", methods=["POST"])
def profile_apply_confirm():
    """Start the confirmed batch as a job, as the verified person, in the
    rollout order. Every device's program is computed again by the apply and
    compared with the hash this confirm carries; a moved one is refused alone,
    with nothing sent to it. Posted by htmx from the preview's confirm, the body the preview
    drew in its fields (C850), its `order` the rollout list as the page shows it (C888);
    answers 202 with the job's card, drawn in place below the preview, or 400 with the
    refusal and nothing sent: an order that is not exactly the confirmed devices, each once,
    is refused naming both."""
    from flask import request

    from modules import deploy_job, identity
    from modules.nsot import listref

    form = request.form
    try:
        scope = _scope(request)
    except UnknownScope as exc:
        return _apply_answer("", 400, refused=str(exc))
    list_name = (form.get("list") or "").strip()
    if not list_name or not listref.exists(list_name):
        return _apply_answer("", 400, refused=(
            "No known list named: the batch records into one list's repository, so the list "
            "comes from the preview you confirmed. Nothing was sent."))
    try:
        data = _confirm_fields(form, CONFIRM_JSON_FIELDS)
    except ValueError as exc:
        return _apply_answer("", 400, refused=f"Nothing confirmed: {exc}. Nothing was sent.")
    order = [d for d in data["order"] if isinstance(d, str) and d]
    confirmations, hashes = data["confirmations"], data["command_hashes"]
    # A device in the order with no confirmation is refused by the order check below, which
    # names both sides (C1265: a second check of it here could not be observed).
    if not order or any(not hashes.get(d) for d in order):
        return _apply_answer("", 400, refused=(
            "Nothing confirmed: every device needs the capture and command hashes its preview "
            "showed. Nothing was sent."))
    # The order is the person's, set in the page (C888: a move plans nothing, since no
    # device's program or hash depends on its place), and is bound HERE: it must be exactly
    # the devices whose hashes this confirm carries, each once. A device dropped from it or
    # named twice would run a batch the preview never showed.
    if len(order) != len(set(order)) or set(order) != set(confirmations):
        return _apply_answer("", 400, refused=(
            f"Nothing confirmed: the rollout order sent ({', '.join(order)}) is not exactly the "
            f"devices this confirm carries hashes for ({', '.join(sorted(confirmations))}), "
            "each once. Nothing was sent."))
    job = deploy_job.start(
        list_name, order, confirmations, hashes,
        authorise=data["authorise"], remove=data["remove"],
        scope=plan_scope(scope), actor=identity.request_actor(),
        actor_kind=getattr(identity.identify(request), "kind", ""),
        ident=identity.verified_identity())
    return _apply_answer(job, 202,
                         started_op="deploy" if scope == "intent" else "monitoring-templates")


@bp.route("/monitoring/apply/job/<job>", methods=["GET"])
def profile_apply_job(job):
    """Where the batch is, in the rollout order, then its result: drawn from
    the receipts the apply wrote. Redrawn when the job announces."""
    return _apply_answer(job)


# ---------------------------------------------------------------------------
# Monitoring > IP SLA (P.9 d4, the ADD path): the profile's policy, the probes
# it suggests for the chosen devices (where each lives, what path it
# measures, why there, its expected CPU cost), one commit of the ticked ones
# into the devices' intent, then the batch Apply scoped to IP SLA lines.
# Changing a running probe is the re-create (C290), gated on staged run 9.
# ---------------------------------------------------------------------------

def _ip_sla_unsent(ref, name: str) -> tuple:
    """C1499: ``(rows, error)``, a row per device whose committed IP SLA intent its golden does
    not run (`ip_sla_policy.unsent`): ``{on, ops, last}``, ``last`` its newest IP SLA send when
    that one did not deploy (``{at, words, reason}``). Every golden read in one `cat-file`
    batch and the receipts once, never a read per device (the scale rule)."""
    from modules.neighbours import committed_intents
    from modules.nsot import ip_sla_policy, receipts
    from modules.preview_confirm import OUTCOME_WORDS
    from modules.readers.netbox_lag import goldens_by_device

    intents, err = committed_intents(ref.repo_dir)
    if err:
        return [], err
    holding = {h: hv for h, hv in (intents or {}).items() if (hv or {}).get("ip_sla")}
    if not holding:
        return [], ""
    goldens, _ids, gerr = goldens_by_device(name, ref, list(holding))
    if gerr:
        return [], gerr
    by_on = {}
    for r in ip_sla_policy.unsent(holding, goldens):
        by_on.setdefault(r["on"], []).append(r)
    if not by_on:
        return [], ""
    newest = {}
    for row in receipts.read(name, limit=400).get("rows") or []:      # newest first
        dev = row.get("device")
        if dev in by_on and dev not in newest and row.get("scope") == ip_sla_policy.SCOPE:
            newest[dev] = row
    out = []
    for on, ops in by_on.items():
        last = newest.get(on)
        if last and last.get("outcome") != "deployed":
            last = {"at": (last.get("at") or "").replace("T", " ").replace("Z", " UTC"),
                    "words": OUTCOME_WORDS.get(last.get("outcome"), last.get("outcome", "")),
                    "reason": " ".join(str(last.get("reason") or "").split())}
        else:
            last = None
        out.append({"on": on, "ops": ops, "last": last})
    return out, ""


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
    # C1499: probes committed and not on their device (a send that failed after the batch
    # committed intent), listed whatever was chosen, each with its Retry.
    ctx["unsent"], ctx["unsent_error"] = _ip_sla_unsent(ref, name)
    if not chosen:
        # Opened from the tab: every device whose committed intent declares no
        # probe, said as such (a population the page chose is named).
        chosen, err = ip_sla_policy.without_probes(ref)
        ctx.update(chosen=chosen, defaulted=True, error=err)
        if err:
            return ctx
    # The plan whenever there is a policy (C1491): its frequency changes for probes that already
    # run concern every device, not only the chosen ones without a probe.
    if (ctx["policy"]["section"] or {}).get("policy"):
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
            ctx["commit_body"] = {"list": name, "devices": chosen,
                                  "fingerprint": got["fingerprint"]}
            # Carried only as the page draws it (every carried field is drawn): the
            # suggestions and their costs as `by_on`, the fingerprint in the commit's body, and
            # no row's platform, which only the costs and the operation's text needed.
            for k in ("suggestions", "cost_by_device", "fingerprint"):
                got.pop(k, None)
            for row in [r for g in got["by_on"] for r in g["rows"]] + got.get("retunes", []):
                row.pop("platform", None)
            ctx["plan"] = got
    return ctx


def _decline_ctx(req, values) -> dict:
    """The decline card's context (C718's board B and D): the list it carries, the entry
    (`decline.entry`, a read), and who would confirm."""
    from modules import identity
    from modules.nsot import decline, listref
    from modules.nsot.intent_ops import public
    from modules.preview_confirm import confirm_part

    name = (values.get("list") or "").strip() or listref.active().name
    device = (values.get("device") or "").strip()
    section = (values.get("section") or "").strip()
    undo = values.get("undo") == "1"
    if not listref.exists(name):
        return {"state": "refused", "list": name, "device": device, "section": section,
                "undo": undo, "error": f"no network named {name!r}: nothing was committed"}
    ident = identity.identify(req)
    e = decline.entry(name, device, section, reason=values.get("reason", ""),
                      actor=ident.actor if ident.is_identified else "",
                      at=(values.get("at") or "").strip(), undo=undo)
    return {"state": "refused" if e["error"] else "preview", "list": name, "device": device,
            "section": section, "undo": undo, "e": public(e), "error": e["error"],
            "confirm": confirm_part(req, "approve"),
            "words": decline.WORDS.get(section, section)}


@bp.route("/monitoring/decline", methods=["GET"])
def decline_card():
    """Decline… or Undo decline… (C718, board B and D): the reason, the intent change it
    records and its checks, bound by hash. A READ: nothing is written; typing the reason asks
    again. `close=1` answers the empty slot (Cancel)."""
    if request.args.get("close") == "1":
        return _strict('<div id="decline-card"></div>')
    return _strict(render_template("v2/_decline.html", d=_decline_ctx(request, request.args)))


@bp.route("/monitoring/decline/confirm", methods=["POST"])
def decline_confirm():
    """Record the confirmed decline (or its undo) in the device's intent as the verified
    person: computed again under the device's hold and refused if it moved; one intent commit
    (`decline.apply`). Nothing is sent to the device."""
    from modules import identity
    from modules.nsot import decline, listref

    f = request.form
    name = (f.get("list") or "").strip()
    d = {"list": name, "device": (f.get("device") or "").strip(),
         "section": (f.get("section") or "").strip(), "undo": f.get("undo") == "1"}
    d["words"] = decline.WORDS.get(d["section"], d["section"])
    if not listref.exists(name):
        d.update(state="refused", error=f"no network named {name!r}: nothing was committed")
        return _strict(render_template("v2/_decline.html", d=d)), 400
    if not (f.get("hash") or "").strip():
        d.update(state="refused", error="the confirm carried no preview hash: nothing was "
                                        "committed; open Decline… again")
        return _strict(render_template("v2/_decline.html", d=d)), 400
    out = decline.apply(name, d["device"], d["section"], (f.get("hash") or "").strip(),
                        actor=identity.identify(request).actor or "",
                        reason=f.get("reason", ""), at=(f.get("at") or "").strip(),
                        undo=d["undo"])
    d.update(state="result", out=out)
    return _strict(render_template("v2/_decline.html", d=d))


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
        picked = data.get("picked")
        out = HW.apply(data.get("fingerprint") or "", identity.request_actor(),
                       picked=picked if isinstance(picked, list) else None,
                       bound=data.get("bound") if isinstance(data.get("bound"), dict) else None)
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


# ---------------------------------------------------------------------------
# Devices › Save (C593, boards A and C, approved 2026-10-04): the ticked devices, or every
# device of the network, saved to startup and recorded as golden together
# (`modules/nsot/save_op.py`). The page is the plan; the confirm starts a job; the card is
# redrawn when the job announces `save`, and as each device steps.
# ---------------------------------------------------------------------------

def _save_selection(req, ref) -> list:
    """The devices a Save names: ``all=1`` for every device of the network; ``match=1`` for
    every device the Devices list's search and filters match, resolved here
    (`device_list.matching`); else each ``device`` the Devices page's form ticked, in its
    order."""
    from modules import device_list
    from modules.nsot.restore import _devices_of

    if req.values.get("all") == "1":
        return [d["hostname"] for d in _devices_of(ref.name) if d.get("hostname")]
    every = device_list.matching(ref, req.values)
    if every is not None:
        return every
    return list(dict.fromkeys(d for d in req.values.getlist("device") if d))


@bp.route("/devices/deploy", methods=["GET"])
def devices_deploy():
    """Devices › Plan a deploy for the ticked devices (7.4's board B): each device's whole
    committed intent, one preview in a rollout order, then one confirm whose run is a job,
    drawn in place (the batch Apply's page, preview, confirm and job, with scope `intent`).
    Devices' ALL MATCHING (``match=1``) is resolved here from the list's search and filters
    (`device_list.matching`); the preview then carries each device it planned by name."""
    from flask import request

    from modules import device_list
    from modules.nsot import listref
    from routes.list_param import named_list

    every = device_list.matching(listref.resolve(named_list(request) or listref.active().name),
                                 request.args)
    ctx = _apply_ctx(request, scope="intent", names=every)
    return _page("v2/apply.html", active_nav="devices", **ctx)


@bp.route("/devices/save", methods=["GET"])
def save():
    """Devices › Save: what Save would do for the selection, from stored records only, and
    its confirm."""
    from modules import save_page
    from modules.nsot import listref
    from modules.preview_confirm import confirm_part
    from routes.list_param import named_list

    # An unknown named list is refused before this runs (routes/list_param.py).
    ref = listref.resolve(named_list(request) or listref.active().name)
    # A scope in place of a selection (C1232: `no_golden`, every device with no committed
    # golden); an unknown one is refused, naming the ones there are.
    scope = (request.values.get("scope") or "").strip()
    if scope:
        s = save_page.scope_card(ref.name, scope, may=confirm_part(request, "confirm"))
    else:
        s = save_page.plan_card(ref.name, _save_selection(request, ref),
                                may=confirm_part(request, "confirm"))
    return _page("v2/save.html", active_nav="devices", s=s, list_name=ref.name), \
        (400 if s["state"] == "refused" else 200)


@bp.route("/devices/save/confirm", methods=["POST"])
def save_confirm():
    """Start the confirmed Save as a job, as the verified person, bound to the plan's hash: a
    plan that moved is refused with nothing sent. The card then waits for the job."""
    from modules import identity, save_page
    from modules.nsot import capture_job, listref, save_op

    name = (request.form.get("list") or "").strip()
    if not name or not listref.exists(name):
        return _strict(render_template("v2/_save.html", s={
            "state": "refused", "list": name, "error": (
                f"the confirm names no network this server knows ({name or 'none given'}), "
                "and a Save records into one network's repository. Nothing was sent.")}), 400)
    hosts = list(dict.fromkeys(d for d in request.form.getlist("device") if d))
    confirmed = (request.form.get("hash") or "").strip()
    if not hosts or not confirmed:
        return _strict(render_template("v2/_save.html", s={
            "state": "refused", "list": name, "devices": hosts, "error": (
                "the confirm carried no devices or no plan to be bound to. Nothing was "
                "sent.")}), 400)
    got = save_op.start(name, hosts, identity.request_actor(), confirmed)
    if "refused" in got:
        return _strict(render_template("v2/_save.html", s={
            "state": "refused", "list": name, "devices": hosts, "error": got["refused"]}), 409)
    s = save_page.job_card(name, got["job"], capture_job.get(got["job"]))
    return _strict(render_template("v2/_save.html", s=s))


@bp.route("/devices/save/job/<job>", methods=["GET"])
def save_job(job):
    """The Save card for its job: running, its result, or why there is none. Re-read when the
    job announces `save` or a device steps; the search and outcome filter ride along."""
    from modules import save_page
    from modules.nsot import capture_job

    s = save_page.job_card(request.args.get("list", ""), job, capture_job.get(job),
                           q=request.args.get("q", ""), outcome=request.args.get("outcome", ""))
    return _strict(render_template("v2/_save.html", s=s))
