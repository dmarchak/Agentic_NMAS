"""routes/fixit_v2.py — the incident page's "AI troubleshooting" section's controls (board
recurring-fixes v2; the fix-it plan's S4 and S5), drawn from `modules/fixit/section.py`.

Each post answers with the section drawn again in place (`templates/v2/_fixit_section.html`),
its answer leading it; none opens a second card elsewhere on the page:

- ``approve``, ``modify``, ``deny`` (the operator's R1, 2026-11-14, replacing Cancel and Retry
  with more information): Approve runs the waiting plan by its preflighted hash as the plan
  engine's incident-fix plan; Modify sends the person's words to the AI for a revised plan with
  a new hash, running nothing; Deny records an optional reason, running nothing.
- ``start`` (Start AI troubleshooting, once, for an incident whose failure did not start an
  investigation by itself) and ``ask_again`` (after a denial): ONE investigation asked as the
  verified person who pressed (`triggers.person`), the per-incident cap asked again at the
  press (naming what moved since the panel was drawn), the section's own offer re-checked, its
  answer checked by code and its plan preflighted (`fixit_troubleshoot.troubleshoot`). It runs
  nothing. The one press that starts the AI is Start: Troubleshoot with AI is gone.
- ``handover``: Hand over. The write-up built from the incident's records with no AI, kept as
  a new version, and sent to the teams ticked, each one told about the network's can't-fix
  (`handover.hand_over`).
- ``handover_send``: Send again, a kept write-up sent once more to the same teams.
- ``handover_page``: the write-up's own page, ``/v2/incident/<id>/handover/<version>`` (a GET;
  ``?download=md`` gives it as Markdown).

Every post is a verified person's, gated (`modules/route_gates.py`: Approve a confirm, the rest
``configure``), and each declares what it invalidates (`modules/invalidation.py`). Approve
starts the plan engine's job; nothing else here holds a device or starts a job, and only
``start``, ``ask_again`` and ``modify`` ask a model, on a person's press.
"""

import logging
import time

from flask import Blueprint, Response, render_template, request

from routes.device_v2 import _page_ref, _strict, _who, carry_list

log = logging.getLogger(__name__)

bp = Blueprint("fixit_v2", __name__, url_prefix="/v2/incident")
bp.url_defaults(carry_list)       # the page's network on every URL it draws (C494)


def _found(incident_id: str):
    """``(network, found)`` for *incident_id* on the page's network (`incident_page.resolve`)."""
    from modules import incident_page

    ref = _page_ref()
    return ref.name, incident_page.resolve(ref.name, incident_id)


def _ended(found: dict) -> str:
    """How the incident ended, by the page's own rule (`incident_page.state_of`: fixed,
    cleared or a declined proposal), or ``""`` while it stands."""
    from modules import incident_page

    state = incident_page.state_of(found["incident"], found["entry"], found["decisions"])
    if state in ("fixed", "cleared", "cancelled"):
        return state
    # C3876: closed in the store with its fix never confirmed: ended all the same (its AI
    # troubleshooting read-only), said as what it is.
    if (found["incident"] or {}).get("state") == "closed":
        return incident_page.UNCONFIRMED_WORDS.lower()
    return ""


def _resolved_at(found: dict):
    """When the incident resolved (epoch seconds), or None while it stands."""
    from modules.fixit.section import _epoch

    if not _ended(found):
        return None
    closed = (found["incident"] or {}).get("closed_at") or ""
    return _epoch(closed) or time.time()


def _section(network: str, found: dict, status: int = 200, **answer):
    """The section drawn again, its *answer* leading it."""
    from modules.fixit import section

    x = section.drawn(network, found, resolved=_resolved_at(found), ended=_ended(found))
    # A can't-fix's AI analysis in full (C3488), as the incident's page draws it.
    from routes.v2 import with_heal_analysis
    with_heal_analysis(x)
    return _strict(render_template("v2/_fixit_section.html", x=x, answer=answer), status)


def _missing(incident_id: str, found: dict):
    """The answer for an id with no page: 404, said in place."""
    x = {"state": "none", "id": incident_id, "network": found.get("network") or "",
         "why": (f"{incident_id} is no incident this network's records hold"
                 if found["found"] != "unreadable" else
                 "its records could not be read: " + "; ".join(found["unreadable"]))}
    return _strict(render_template("v2/_fixit_section.html", x=x, answer={}), 404)


def _person() -> dict:
    """The request's verified actor, how it was established and whether it is a person
    (`identity.verified_identity`, which fails closed)."""
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "actor_verified": identity.actor_verification(actor),
            "person": bool(ident is not None and ident.kind == "person")}


def _not_a_person(who: dict, what: str) -> str:
    if who["person"] and who["actor"] and who["actor_verified"] not in ("", "none"):
        return ""
    return (f"{what} is a verified person's press, and this request is not one (its actor is "
            f"{who['actor'] or 'none'}, verified by {who['actor_verified'] or 'nothing'}). "
            "Nothing was recorded")


def _gate(incident_id: str, what: str):
    """``(network, found, incident, who, None)`` for a verified person's press on a standing
    incident, or ``(…, response)``: the refusal drawn in place, nothing recorded or sent."""
    from modules.fixit import section

    network, found = _found(incident_id)
    if found["found"] != "page":
        return network, found, None, None, _missing(incident_id, found)
    if _ended(found):
        return network, found, None, None, _section(network, found, 409, refused=(
            f"{incident_id} is resolved ({_ended(found)}), and its AI troubleshooting is "
            "read-only. Nothing was recorded or sent"))
    who = _person()
    why = _not_a_person(who, what)
    if why:
        return network, found, None, who, _section(network, found, 403, refused=why)
    got = section.incident_of(network, found)
    if got["incident"] is None:
        return network, found, None, who, _section(network, found, 409, refused=got["why"])
    return network, found, got["incident"], who, None


def _proposal_named(inc, named: str):
    """``(line, why)``: the proposal a person may decide on now (`section._current_proposal`),
    which must be the one the form names (``proposal``), or None with why."""
    from modules.fixit import incident as F
    from modules.fixit import section

    rec = F.read(inc)
    if rec["state"] == "unreadable":
        return None, rec["error"]
    # An approve whose run never started (`section.approve_lost`) decides nothing: its
    # proposal may be approved again, as the card offers it.
    line = section._current_proposal(rec, inc.network, inc.id)
    named = str(named or "").strip()
    if line is None:
        return None, f"{inc.id} has no proposal waiting for a decision now"
    if named != line["proposal"]:
        return None, (f"the proposal decided on is {named or 'none named'}, and the one waiting "
                      f"now is {line['proposal']}: the page was drawn before it changed; read "
                      "it again")
    return line, ""


@bp.route("/<incident_id>/fixit/script", methods=["POST"])
def fix_with_script(incident_id):
    """"Fix with saved script: <name>" (C3805): one of the fixes the incident offers (any whose
    match its problem holds, `saved_plans.fix_offers`, C3849; ``key`` names which) run once
    as the verified person who pressed, bound to the hash the page drew (``key``, ``hash``), by
    the runner as a job (the device held, preconditions read again, sent, verified, rolled back
    on a failed verify, recorded); verified, the incident closes Fixed. No AI."""
    from urllib.parse import quote

    from modules.nsot import capture_job
    from modules.nsot import command_plan_run as CR
    from modules.nsot import saved_plans as S

    # Its own gate: a held or watching incident has no troubleshooting record yet, and none is
    # needed to run a saved script on it (the operator, 2026-11-16: "Fix now").
    network, found = _found(incident_id)
    key, sent = (request.values.get("key") or "").strip(), (request.values.get("hash") or "")

    def answer(status=200, **said):
        """The section drawn again; or, pressed on the fix's own page (``view=fix``, its
        Run…, C3849 piece 4), that page's run card: one run path, two places it answers."""
        if request.values.get("view") == "fix":
            from routes import fixes_v2
            return fixes_v2.run_answer(network, key, status, incident=incident_id, **said)
        return _section(network, found, status, **said)
    if found["found"] != "page":
        if request.values.get("view") == "fix":
            return answer(404, refused=("Not run: that incident is in no record Mercury can "
                                        "read now. Nothing ran"))
        return _missing(incident_id, found)
    if _ended(found):
        return answer(409, refused=(
            f"{incident_id} is resolved ({_ended(found)}). Nothing ran"))
    who = _person()
    why = _not_a_person(who, "Fix with saved script")
    if why:
        return answer(403, refused=why)
    # Any fix the incident offers (C3849: every matching fix is a button), the one pressed.
    offer = next((o for o in S.fix_offers(network, found) if o["key"] == key), {})
    if not offer:
        return answer(409, refused=(
            f"Not run: {key or 'no script'} is no saved script matching this incident's "
            "problem now. Nothing ran"))
    if sent.strip() != offer["hash"]:
        return answer(409, refused=(
            f"Not run: you pressed {offer['name']} at {sent or 'no hash'}, and its preview now "
            f"is {offer['hash']}: it moved since the page was drawn. Nothing ran"))
    e = S.scripts(network).get(key)
    if not e:
        return answer(409, refused=(
            f"Not run: {offer['name']} is no longer saved. Nothing ran"))

    def work(_job):
        rec = CR.run(network, key, offer["values"], confirmed=offer["hash"],
                     incident=incident_id, reason=(f"saved script {offer['name']} pressed on "
                                                   f"incident {incident_id}"), **who)
        if S.run_verified(rec):     # a run that sent nothing closes nothing (C3)
            S.close_fixed(network, incident_id, {"id": rec.get("id"),
                                                 "device": offer["values"].get("device")},
                          e, who["actor"])
        return {"run": rec.get("id"), "state": rec.get("state"),
                "words": CR.OUTCOME_WORDS.get(rec.get("outcome") or "", "")
                or str(rec.get("why") or "")}
    capture_job.start(network, f"{offer['name']} on {incident_id}", who["actor"], work,
                      kind="saved script", announce_keys=CR.ANNOUNCE_KEYS,
                      announcer=CR.ANNOUNCER,
                      page=f"/v2/incident/{incident_id}?list={quote(network)}")
    return answer(done=(
        f"Running {offer['name']} on {offer['values'].get('device')}: held, checked, sent, "
        "verified and recorded; the incident closes Fixed when it verifies"))


@bp.route("/<incident_id>/fixit/approve", methods=["POST"])
def approve(incident_id):
    """Approve: the waiting plan, preflighted again, approved by its hash as the verified person
    who pressed (``hash``), and started as the plan engine's ``incident-fix`` plan: each step in
    order through its own operation's preview, apply (re-checking its own hash), verify and
    record; the first that does not pass stops it; nothing retried. One approve line names the
    run. Refused with nothing run when the hash is not the one preflighted now (both named) or
    a step would be refused. C3867: the preflight is the page's own (the incident's records, no
    device or collector read); the approval is recorded and the answer is "Starting…" at once,
    and the live reads and the start follow it (`_start_approved`), a refusal there drawn on
    the card."""
    from modules.fixit import incident as F
    from modules.fixit import plan as FP

    network, found, inc, who, refused = _gate(incident_id, "Approve")
    if refused is not None:
        return refused
    line, why = _proposal_named(inc, request.form.get("proposal"))
    if line is None:
        return _section(network, found, 409, refused=f"Not approved: {why}. Nothing ran")
    plan = FP.preflight(inc, line)
    if not plan or not plan["approvable"]:
        return _section(network, found, 409, refused=(
            "Not approved: " + ((plan or {}).get("why_refused") or "the proposal names no "
                                "plan Mercury runs") + ". Nothing ran"))
    sent = (request.form.get("hash") or "").strip()
    if sent != plan["hash"]:
        return _section(network, found, 409, refused=(
            f"Not approved: you approved the plan {sent or 'with no hash'}, and the plan "
            f"preflighted now is {plan['hash']}: it moved since the page was drawn. Read it "
            "again. Nothing ran"))
    reason = " ".join((request.form.get("reason") or "").split()) or (
        f"approved plan {plan['hash']} on incident {incident_id}'s page")
    params, bound = FP.plan_params(inc, line), plan["hash"]
    # The approval is kept BEFORE the run starts, naming the run it starts (its id given to
    # the engine), so a run never exists without the person's approval on the record.
    from modules.nsot import reads
    run_id = reads.new_id()
    try:
        F.record_approve(inc, who["actor"], who["actor_verified"], proposal=line["proposal"],
                         plan_hash=plan["hash"], run=run_id)
    except (F.Refused, OSError, ValueError) as exc:
        return _section(network, found, 409, refused=f"Not approved: {exc}. Nothing ran")
    # C3867 (the operator, 2026-11-16: "Approve: checks the posted hash against the plan as
    # shown ... starts the plan engine's job at once and answers "Starting…" in place"): the
    # hash is checked above against the plan as the page draws it (`FP.preflight`, from the
    # incident's records: no device or collector read), and everything that reads live goes
    # after the answer (`_start_approved`): each collector session read again, the engine's
    # preview and its hash, the start; a refusal there is drawn on the card as before.
    _start_approved(network, inc, params, bound, plan, run_id, who, reason)
    return _section(network, found, done=(
        f"Starting… Approved plan {plan['hash'][:12]} runs step by step and stops at the "
        "first step that does not pass; each step's own record is under Attempts."))


def _start_approved(network: str, inc, params: dict, bound: str, plan: dict, run_id: str,
                    who: dict, reason: str) -> None:
    """The approved plan started after Approve's answer (C3867), as its own job
    (`capture_job.start`: an In progress row opening the incident's card, its failed state
    readable there, its end announced by the plan engine's announcer, `privileged`, `drift`,
    `in_progress`), its work in the request's context so the verified person is carried to the
    engine's own job (`copy_current_request_context`; `identity.verified_identity` reads a
    request): each collector step's session, read when the plan was proposed and bound by the
    plan's hash (C3725, `plan_params`), read again (the close helper's dry run) and refused,
    naming both, when the collector holds another; then the plan engine's own start
    (`PE.start`: its preview of every step and its hash compared with the one approved, then
    the run as its job, whose apply re-checks each step's own hash). A refusal is kept on the
    incident's card after its approval (`troubleshoot_job.record_failure`, in every worker)
    and ends this job failed, naming it."""
    from urllib.parse import quote

    from flask import copy_current_request_context

    from modules import plan_engine as PE
    from modules.nsot import capture_job

    def refused(why: str):
        # Kept after its approval, so the card says it, never a run that never was.
        from modules import troubleshoot_job
        words = f"the approved plan did not start: {why}"
        troubleshoot_job.record_failure(inc, f"approve:{run_id}", words, trigger="person",
                                        by=who["actor"], verified=who["actor_verified"])
        raise RuntimeError(words)                     # the job's failed state says it

    def go(_job=None):
        got = {}
        try:
            from modules.heal import resubscribe as R
            read = {str(s.get("n")): s for s in plan.get("sessions") or []}
            for n, s in enumerate(params["steps"], 1):
                if s["operation"] not in R.COLLECTOR_STEP_KEYS:
                    continue
                kept = read.get(str(n)) or {}
                now = PE.collector_session(network, s["params"]["device"],
                                           s["params"].get("subscriptions") or [])
                if now["session"] != s.get("session"):
                    held = (f"the one from {now['session']}" if now["session"]
                            else f"none ({now['refused']})")
                    got = {"refused": (
                        f"step {n}'s collector session moved since the plan was proposed: "
                        f"the plan read the session from {s.get('session')} at "
                        f"{kept.get('at') or 'its proposal'}, and the collector holds "
                        f"{held} now. Ask again for a plan that reads it. Nothing ran")}
                    break
            # `PE.start` previews every step and compares its hash with the one approved
            # (the session is bound by the preflight's hash, `plan_params`), refusing, naming
            # both, when it moved.
            if not got:
                got = PE.start(network, PE.INCIDENT_FIX, params, bound, actor=who["actor"],
                               actor_verified=who["actor_verified"], person=who["person"],
                               reason=reason, run_id=run_id)
        except Exception as exc:                      # noqa: BLE001 (kept on the card)
            log.exception("fixit approve: run %s did not start", run_id)
            got = {"refused": f"{type(exc).__name__}: {exc}. Nothing ran"}
        if got.get("refused"):
            refused(got["refused"])
        return {"run": run_id, "job": got.get("job"), "state": "done",
                "words": f"the approved plan's run started ({run_id})"}
    capture_job.start(network, f"Starting the approved plan on {inc.id}", who["actor"],
                      copy_current_request_context(go), kind="approved plan start",
                      announce_keys=("privileged", "drift", "in_progress"),
                      announcer=PE.ANNOUNCER,
                      page=f"/v2/incident/{quote(inc.id)}?list={quote(network)}#inc-run")


@bp.route("/<incident_id>/fixit/deny", methods=["POST"])
def deny(incident_id):
    """Deny: the waiting proposal declined, with the person's optional reason; nothing runs and
    nothing is sent; the incident stays open with Ask the AI again and Hand over."""
    from modules.fixit import incident as F

    network, found, inc, who, refused = _gate(incident_id, "Deny")
    if refused is not None:
        return refused
    line, why = _proposal_named(inc, request.form.get("proposal"))
    if line is None:
        return _section(network, found, 409, refused=f"Not denied: {why}. Nothing was recorded")
    try:
        F.deny(inc, who["actor"], who["actor_verified"], proposal=line["proposal"],
               reason=request.form.get("reason") or "")
    except (F.Refused, OSError, ValueError) as exc:
        return _section(network, found, 409, refused=f"Not denied: {exc}")
    return _section(network, found, done=(
        "Denied: nothing ran and nothing was sent. The incident stays open: ask the AI again, "
        "or hand it over."))


def _ask(incident_id: str, what: str, *, note: str, allowed: str):
    """One investigation asked as the verified person who pressed (`fixit_troubleshoot`), the
    section's own offer re-checked first (*allowed*, the contract's action: ``modify``,
    ``ask_again`` or ``start``); a Start is taken once under the record's lock (a person's
    ``start`` line), so two presses start one. It runs nothing."""
    from modules.ai import fixit_troubleshoot as AIT
    from modules.fixit import incident as F
    from modules.fixit import section

    from modules.fixit import policy as P

    network, found, inc, who, refused = _gate(incident_id, what)
    if refused is not None:
        return refused
    # The cap asked again at the press, naming what moved since the panel was drawn (the
    # figures the press carries, ``drawn_spent`` and ``drawn_cap``, compared and never sent).
    cs = P.cap_state(inc, AIT.worst_usd())                                         # cap
    if cs["state"] != "allowed":
        moved = section._moved_words(request.form.get("drawn_spent") or "",
                                     request.form.get("drawn_cap") or "", cs)
        return _section(network, found, 409, refused=(
            cs["words"].replace("Retry isn't available", "Not asked", 1)
            + (f". Since the panel was drawn, {moved}" if moved else "") + ". Nothing was sent"))
    drawn = section.view(network, found, resolved=_resolved_at(found), ended=_ended(found))
    act = (drawn.get("actions") or {}).get(allowed) or {}
    if drawn.get("state") == "investigating":
        # One investigation at a time, read from the record (every worker sees it).
        return _section(network, found, 409, refused=(
            f"Not asked: the AI is already investigating this incident ({drawn.get('status')}). "
            "Nothing was sent"))
    if not act.get("offered"):
        return _section(network, found, 409, refused=(
            f"Not asked: {what} is not offered now"
            + (f" ({act['refused']})" if act.get("refused") else "") + ". Nothing was sent"))
    if allowed == "modify":
        line, why = _proposal_named(inc, request.form.get("proposal"))
        if line is None:
            return _section(network, found, 409, refused=f"Not asked: {why}. Nothing was sent")
        if not " ".join(note.split()):
            return _section(network, found, 400, refused=(
                "Not asked: Modify sends your words to the AI, and none were typed. Nothing "
                "was sent"))
    # ONE start path (the operator, 2026-11-16: "One start path, not two"): the press is R1's
    # start (`heal_notice.start_catch_up` in its press mode, G6's): planned and claimed under
    # the network's start lock, every cap asked (the mode, hosted AI, this incident's cap, the
    # day cap and the calls in flight; never ``fixit_auto``'s switch or caps), its worst case
    # reserved, and its investigation `_investigation`, Mercury's own confirmation read first
    # (C3870). Its key: the incident's untaken failure's, as R1's (so R1 never starts on that
    # failure again), else Start's one key or the next of the person's presses, as before; a
    # second press at the same moment is refused, naming the investigation that runs.
    from modules import heal_notice, troubleshoot_job

    people = [ln for ln in F.starts(inc)["starts"] if ln.get("trigger") == "person"
              and not str(ln.get("start") or "").endswith(":failed")]
    key = "person:start" if allowed == "start" else f"person:{len(people) + 1}"
    at = time.time()
    own = {"id": incident_id, "incident": inc,
           "failure": {"key": key, "kind": "person", "id": incident_id, "outcome": allowed,
                       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at))}}
    ended, jobs = {}, []

    def starter(_network, _iid, k, run):
        def work(_job):
            try:
                out = run()
            except Exception as exc:                  # noqa: BLE001 (said, then the job's)
                ended["error"] = str(exc)
                raise
            words = out.get("words") or ""
            if out.get("state") == "failed" and not out.get("proposal"):
                # Kept on the card by `_investigation` (its ``failed`` start line); said here.
                ended["error"] = words
            elif allowed == "modify" and out.get("state") == "proposed":
                words = ("The AI revised its plan with your words: the new plan, with its new "
                         "hash, is below. Nothing ran.")
            ended["out"] = {"state": out.get("state"), "words": words,
                            "typed_masked": out.get("typed_masked")}
            return ended["out"]
        jobs.append(troubleshoot_job.start(network, incident_id, who["actor"], work,
                                           label=f"{what}: {incident_id}", key=k,
                                           trigger="person"))
    try:
        got = heal_notice.start_catch_up(
            network, [incident_id], actor=who["actor"], verified=who["actor_verified"], now=at,
            starter=starter, press=what, fallback={incident_id: own}, line_words="", note=note,
            resolved=_resolved_at(found))
    except Exception as exc:                          # noqa: BLE001 (said in place)
        return _section(network, found, 409, refused=f"Not asked: {exc}")
    if not got["started"]:
        why = (got["why"].get(incident_id)
               or next((s["why"] for s in got["skipped"] + got["failed"]
                        if s.get("id") == incident_id), ""))
        if any(s.get("id") == incident_id for s in got["skipped"]):
            why = ("the AI is already investigating this incident (its start was taken a "
                   "moment ago, by another press)")
        why = str(why or "it could not be started").removeprefix("Not started: ").rstrip(".")
        return _section(network, found, 409, refused=f"Not asked: {why}. Nothing was sent")
    job = jobs[0] if jobs else ""
    # The job runs on; its end is announced and the card re-fetches. A job that ended before
    # this answer is drawn (a quick refusal) says what it found.
    said = (f"Couldn't troubleshoot: {ended['error']}" if "error" in ended else
            (ended["out"] or {}).get("words") if "out" in ended else
            troubleshoot_job.done_words(job))
    if said is None:
        return _section(network, found, 202, level="muted", done=(
            "The AI is investigating. This card updates when it answers; nothing runs until "
            "you approve a plan."))
    return _section(network, found, level="muted" if not said.startswith("Couldn't") else
                    "warn", done=said,
                    typed_masked=(ended.get("out") or {}).get("typed_masked"))


@bp.route("/<incident_id>/fixit/modify", methods=["POST"])
def modify(incident_id):
    """Modify: the person's words (``text``) sent to the AI through the gateway's typed part
    (masked, the injection screen) with the evidence; the AI returns a revised plan with a new
    hash. Nothing runs; it counts toward the incident's cap."""
    return _ask(incident_id, "Modify", note=request.form.get("text") or "", allowed="modify")


@bp.route("/<incident_id>/fixit/ask_again", methods=["POST"])
def ask_again(incident_id):
    """Ask the AI again, after a denial: the same investigation, the person's optional words
    (``text``) with it. Nothing runs."""
    return _ask(incident_id, "Ask the AI again", note=request.form.get("text") or "",
                allowed="ask_again")


@bp.route("/<incident_id>/fixit/start", methods=["POST"])
def start(incident_id):
    """Start AI troubleshooting: the one start for an incident whose failure did not start an
    investigation by itself (the network's switch off, or the failure recorded before it was
    turned on; e.g. hi-22cfdc299000), a person's press, the R1 flow from step 3."""
    return _ask(incident_id, "Start AI troubleshooting", note=request.form.get("text") or "",
                allowed="start")


def _teams() -> list:
    return [t for t in request.form.getlist("team") if t][:20]


@bp.route("/<incident_id>/fixit/handover", methods=["POST"])
def handover(incident_id):
    """Hand over: the write-up kept as a new version and sent to the teams ticked."""
    from modules import incident_page
    from modules.fixit import handover as H
    from modules.fixit import incident as F
    from modules.fixit import section

    network, found = _found(incident_id)
    if found["found"] != "page":
        return _missing(incident_id, found)
    if _ended(found):
        return _section(network, found, 409, refused=(
            f"{incident_id} is resolved ({_ended(found)}), and its AI troubleshooting is "
            "read-only. Nothing was recorded or sent"))
    who = _person()
    why = _not_a_person(who, "Hand over")
    if why:
        return _section(network, found, 403, refused=why)
    got = section.incident_of(network, found)
    inc = got["incident"]
    if inc is None:
        return _section(network, found, 409, refused=got["why"])
    rec = F.read(inc)
    notes = [ln.get("note") for ln in rec["lines"] if "proposal" in ln and ln.get("note")]
    teams = _teams()
    try:
        out = H.hand_over(inc, actor=who["actor"], actor_verified=who["actor_verified"],
                          note=request.form.get("note") or "", notes=notes, team_ids=teams,
                          diagnosis=section.diagnosis_of(inc),
                          advisory=[a.get("words") for a in found["advisories"][-1:]],
                          title=incident_page.title(found["incident"], found["entry"],
                                                    found["decisions"]),
                          resolved=_resolved_at(found))
    except (H.Refused, F.Refused, OSError, ValueError) as exc:
        return _section(network, found, 409, refused=f"Not handed over: {exc}")
    sent = out["sent"]
    level = "muted" if sent["ok"] else "warn"
    return _section(network, found, level=level,
                    done=f"Hand-over {out['version']} kept. {sent['words']}.",
                    resend=out["version"] if not sent["ok"] and teams else None,
                    resend_teams=teams)


@bp.route("/<incident_id>/fixit/handover/<int:version>/send", methods=["POST"])
def handover_send(incident_id, version):
    """Send again: a kept write-up sent once more to the teams it was sent to."""
    from modules.fixit import handover as H
    from modules.fixit import section

    network, found = _found(incident_id)
    if found["found"] != "page":
        return _missing(incident_id, found)
    if _ended(found):
        return _section(network, found, 409, refused=(
            f"{incident_id} is resolved ({_ended(found)}), and its AI troubleshooting is "
            "read-only. Nothing was recorded or sent"))
    who = _person()
    why = _not_a_person(who, "Send again")
    if why:
        return _section(network, found, 403, refused=why)
    got = section.incident_of(network, found)
    inc = got["incident"]
    if inc is None:
        return _section(network, found, 409, refused=got["why"])
    teams = _teams()
    try:
        chosen = H.checked_teams(network, teams)
    except H.Refused as exc:
        return _section(network, found, 409, refused=str(exc))
    sent = H.send(inc, version, [t["id"] for t in chosen])
    return _section(network, found, level="muted" if sent["ok"] else "warn",
                    done=f"Hand-over {version}: {sent['words']}.",
                    resend=version if not sent["ok"] and teams else None, resend_teams=teams)


@bp.route("/<incident_id>/handover/<int:version>", methods=["GET"])
def handover_page(incident_id, version):
    """The write-up's own page, its nine sections, linked back to the incident's page;
    ``?download=md`` gives it as Markdown. A read."""
    from modules import incident_page
    from modules.display_names import people_payload
    from modules.fixit import handover as H
    from modules.fixit import section

    network, found = _found(incident_id)
    doc, why = None, ""
    if found["found"] != "page":
        why = f"{incident_id} is no incident this network's records hold"
    else:
        got = section.incident_of(network, found)
        if got["incident"] is None:
            why = got["why"]
        else:
            kept = H.read_version(got["incident"], version)
            if kept["state"] == "ok":
                doc = people_payload(kept["doc"])
            else:
                why = kept["error"] or f"{incident_id} has no hand-over {version}"
    if doc is not None and request.args.get("download") == "md":
        return Response(doc["markdown"], mimetype="text/markdown",
                        headers={"Content-Disposition": (
                            f'attachment; filename="{incident_id}-handover-{version}.md"')})
    title = (incident_page.title(found["incident"], found["entry"], found["decisions"])
             if found["found"] == "page" else f"Incident {incident_id}")
    if doc is not None:
        # The page draws the sections; the Markdown is the download's alone.
        doc = {k: v for k, v in doc.items() if k != "markdown"}
    return _strict(render_template("v2/incident_handover.html", doc=doc, why=why,
                                   incident_id=incident_id, version=version, network=network,
                                   title=title, who=_who(), active_nav="attention"),
                   200 if doc is not None else 404)
