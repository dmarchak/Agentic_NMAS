"""routes/oob_onboard_v2.py — out-of-band onboarding in one decision, on v2 (the operator's
approved design of 2026-10-23; the board docs/boards/oob-onboarding.html, drawn under the Phase 7
mode and logged in docs/STANDING_APPROVAL_LOG.md).

- Add device › Address from › **Out-of-band (console)**: the option is drawn enabled only when
  `oob_onboard.eligibility` says so, else disabled with its reason and the link that fixes it
  (`source_view`, asked as the name is typed; the form never waits on NetBox).
- **Review the plan** with that source draws ONE review card (`review_ctx`, called by
  `onboard_v2.preview` too): every derived field and where it came from, the console path with
  the console server's full host-key fingerprint, what the run creates, the exact console
  program, the stop rules, what it will not do, and ONE button bound to the review's hash.
- The confirm (`confirm`) runs `oob_onboard.run` as a job and answers at once with THE stepper
  (C1579's pattern): Preview and Confirm done, Hold running from now, every other step not yet
  run; each step's `device_progress` fills it in place and the run's record replaces it
  (`console_ztp`). The Answering step says until when the SSH key settles.
- Each run has a page of its own (`run_page`), opened by the device's name: the In progress
  list's rows open it, and the running card says it is safe to leave (C1595).

Each template is handed only what it draws (`review_view`, `record_view`, `source_ctx`): the
review's and the record's whole dicts stay on the server.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("oob_onboard_v2", __name__, url_prefix="/v2/onboard/oob")


def _fields(values) -> dict:
    from modules.nsot import oob_onboard as O

    return {k: (values.get(k) or "").strip() for k in O.FORM_FIELDS + O.ASKED_FIELDS}


def _pick(d, keys):
    return {k: d.get(k) for k in keys} if isinstance(d, dict) else None


# ── what each template draws ───────────────────────────────────────────────────────────────

def review_view(pv: dict) -> dict:
    """The review as the card draws it, and nothing it does not (`oob_onboard.preview`'s)."""
    d = pv.get("derived") or {}
    path = pv.get("path")
    said = d.get("from") or {}
    return {
        "ok": bool(pv.get("ok")), "refused_by": dict(pv.get("refused_by") or {}),
        "device_id": pv.get("device_id"), "role": pv.get("role", ""),
        "platform": pv.get("platform", ""),
        "profile": _pick(pv.get("profile"), ("name", "version", "sha256")),
        "path": ({"console_port": {"name": path["console_port"]["name"]},
                  "cable": {"id": path["cable"]["id"]},
                  "server": {"name": path["server"]["name"]},
                  "server_port": {"name": path["server_port"]["name"]}} if path else None),
        "port_id": pv.get("port_id"), "transport": pv.get("transport", ""),
        "port": _pick(pv.get("port"), ("driver", "host", "ssh_port", "container", "tcp_port",
                                       "credential_ref", "jump_host")),
        "host_key": _pick(pv.get("host_key"), ("state", "host", "type", "fingerprint",
                                               "kept_at", "error")),
        "derived": {"asked": list(d.get("asked") or []),
                    "why": {"uplink": (d.get("why") or {}).get("uplink", "")},
                    "relay": _pick(d.get("relay"), ("device", "iface")),
                    "address": d.get("address", ""), "mask": d.get("mask", ""),
                    "vlan": d.get("vlan"), "interface": d.get("interface", ""),
                    "uplink": d.get("uplink", ""), "gateway": d.get("gateway", ""),
                    "server": d.get("server", ""), "filename": d.get("filename", ""),
                    "from": {k: said.get(k, "") for k in ("address", "vlan", "interface",
                                                          "uplink", "gateway")}},
        "gate": pv.get("gate", ""), "creates": list(pv.get("creates") or []),
        "plan": _pick(pv.get("plan"), ("fingerprint",)),
        "program": ({k: pv["program"][k] for k in ("wake", "prelude", "reads", "recheck",
                                                    "lines", "read_back", "copy")}
                    if pv.get("program") else None),
        "not_read": list(pv.get("not_read") or []), "stops": list(pv.get("stops") or []),
        "not_doing": list(pv.get("not_doing") or []), "hash": pv.get("hash", ""),
    }


def record_view(rec):
    """A run's record as the card draws it: what happened, never the whole record."""
    if not rec:
        return None
    out = _pick(rec, ("id", "outcome", "reason", "address", "mask", "interface", "gateway",
                      "mac", "mac_record_error", "bytes_written", "sent", "transcript", "actor",
                      "actor_verified", "reason_given", "at", "started_at", "finished_at",
                      "list", "index_error"))
    out["copy"] = _pick(rec.get("copy"), ("why",))
    out["answering"] = _pick(rec.get("answering"), ("claim", "tries"))
    out["created"] = {"ok": bool((rec.get("created") or {}).get("ok"))}
    return out


# ── Add device's option ────────────────────────────────────────────────────────────────────

def source_ctx(list_name: str, hostname: str, chosen: str) -> dict:
    """What Add device's Address from draws: the four sources, the out-of-band one enabled or
    disabled with its reason and fix (`oob_onboard.eligibility`)."""
    from flask import url_for

    from modules.nsot import oob_onboard as O

    try:
        el = O.eligibility(list_name, hostname)
    except Exception as exc:                          # noqa: BLE001 - said, never raised
        log.exception("oob onboard: eligibility of %r could not be read", hostname)
        el = {"state": "unreadable", "why": f"{type(exc).__name__}: {exc}", "fix": {}}
    fix = _pick(el.get("fix") or {}, ("href", "words", "where"))
    if fix.get("where") == "console_servers":
        fix["href"] = url_for("settings_v2.installation", tab="console")
    return {"oob": {"state": el.get("state", ""), "why": el.get("why", ""), "fix": fix},
            "chosen": chosen or "static", "hostname": hostname}


@bp.route("/source", methods=["GET"])
def source_view():
    """Address from, drawn again for the name typed: one NetBox read and the port store."""
    a = request.args
    return _strict(render_template(
        "v2/_oob_source.html",
        s=source_ctx((a.get("list_name") or "").strip(), (a.get("hostname") or "").strip(),
                     (a.get("address_source") or "").strip())))


# ── the card ───────────────────────────────────────────────────────────────────────────────

def run_steps(list_name: str, device: str, rec=None, *, now=None) -> list:
    """The run's rows for THE stepper: Preview and Confirm done, then the run's declared steps
    read from the device's hold (`device_actions.stepper`, *starts*). The Answering step's
    words are the record's: until when the SSH key settles, then SSH at the address."""
    from modules import device_actions, run_stepper
    from modules.nsot import device_ops
    from modules.nsot import oob_onboard as O

    try:
        holder = (device_ops.holder(list_name, device) or {}) if device else {}
    except device_ops.HoldsUnreadable:
        holder = {}
    progress = holder.get("progress") if holder.get("operation") == O.OP else None
    before = [{"key": k, "words": O.STEP_LABELS[k], "state": "done"} for k in O.BEFORE_RUN]
    rows = device_actions.stepper(O.run_stepper_steps(), progress, now=now, starts=True)
    for row in rows:
        if row["key"] == "answering" and row["state"] == "running":
            row["waits"] = O.settle_words(rec or {}, now)
    return run_stepper.from_stepper(before + rows)


def _held_by_run(list_name: str, device: str) -> bool:
    from modules.nsot import device_ops
    from modules.nsot import oob_onboard as O

    try:
        return bool(device) and (device_ops.holder(list_name, device) or {}).get(
            "operation") == O.OP
    except device_ops.HoldsUnreadable:
        return False


def _blank(list_name: str, hostname: str, **over) -> dict:
    c = {"list_name": list_name, "hostname": hostname, "state": "lost", "pv": None,
         "fields": {}, "add": False, "error": "", "run": "", "job": "", "rec": None,
         "steps": [], "job_error": ""}
    c.update(over)
    return c


def card(list_name: str, args) -> dict:
    """The card's context in the state its query names: ``running``, ``result``, ``failed`` or
    ``lost`` (a run), from ``run``, ``job`` and ``hostname``. Contacts nothing."""
    from modules.nsot import capture_job
    from modules.nsot import oob_onboard as O

    c = _blank(list_name, (args.get("hostname") or "").strip(),
               run=(args.get("run") or "").strip(), job=(args.get("job") or "").strip(),
               add=args.get("add") == "1")
    job = capture_job.get(c["job"]) if c["job"] else None
    try:
        rec = O.get_run(list_name, c["run"]) if c["run"] else None
    except ValueError:
        rec = None
    device = (rec or {}).get("device") or c["hostname"]
    # The JOB first, then the record (C642's order), as the console card reads them.
    if rec is not None and rec.get("outcome") != "running":
        c.update(state="result")
    elif job is not None and job["state"] == "running":
        c.update(state="running", steps=run_steps(list_name, device, rec))
    elif job is not None and job["state"] == "failed":
        c.update(state="failed", job_error=job.get("error") or "the run failed")
    elif rec is not None and _held_by_run(list_name, device):
        # No job here (another process's, or a page opened by the device's name): the hold is
        # the run's liveness, and its record says the run is not over.
        c.update(state="running", steps=run_steps(list_name, device, rec))
    c.update(rec=record_view(rec), hostname=device)
    return c


def _draw(c: dict, code: int = 200):
    return _strict(render_template("v2/_oob_onboard.html", c=c), code)


def review(fields: dict, *, add: bool = False, code: int = 200, error: str = ""):
    """The one review, drawn alone (the card's own Review again, and a refused confirm)."""
    c, status = review_ctx(fields, add=add, code=code, error=error)
    return _draw(c, status)


def review_ctx(fields: dict, *, add: bool = False, code: int = 200, error: str = "") -> tuple:
    """``(card context, status)``: the one review (Add device's Review the plan with the
    out-of-band source draws it inside its card). Contacts no device; writes nothing."""
    from modules.nsot import oob_onboard as O

    fields = {k: (fields.get(k) or "").strip() for k in O.FORM_FIELDS + O.ASKED_FIELDS}
    list_name = fields.get("list_name", "")
    try:
        pv = O.preview(list_name, fields)
    except Exception as exc:                          # noqa: BLE001 - drawn, never raised
        log.exception("oob onboard: the review of %r failed", fields.get("hostname"))
        pv = {"ok": False, "refused_by": {"review": f"{type(exc).__name__}: {exc}"},
              "device": fields.get("hostname")}
    c = _blank(list_name, pv.get("device") or fields.get("hostname", ""), state="review",
               pv=review_view(pv), fields=fields, add=add, error=error)
    return c, (code if (pv.get("ok") or code != 200) else 409)


@bp.route("/preview", methods=["POST"])
def preview_view():
    """The review again, with the asked fields the card's form sent; creates nothing."""
    return review(_fields(request.form), add=request.form.get("add") == "1")


@bp.route("/card", methods=["GET"])
def card_view():
    """The card alone, in the state its query names (redrawn on `device_progress` and
    `console_ztp`). Contacts nothing."""
    return _draw(card((request.args.get("list_name") or "").strip(), request.args))


@bp.route("/confirm", methods=["POST"])
def confirm():
    """The onboarding as reviewed, as a verified person with a reason, bound to the review's
    hash; started as a job, its stepper drawn at once."""
    from modules import identity
    from modules.nsot import capture_job, reads
    from modules.nsot import console_ztp as Z
    from modules.nsot import oob_onboard as O

    form = request.form
    fields = _fields(form)
    add = form.get("add") == "1"
    ident, refusal = identity.require(request, action="confirm", operation="console_onboard")
    if refusal is not None:
        return review(fields, add=add, code=403, error=refusal.get("error", ""))
    actor = ident.actor
    verified = identity.actor_verification(actor)
    why = Z.verified_person(actor, verified).replace("a kick-start", "an out-of-band onboarding")
    if why:
        return review(fields, add=add, code=403, error=why + ". Nothing was sent.")
    reason = (form.get("reason") or "").strip()
    if not reason:
        return review(fields, add=add, code=409,
                      error="a reason is given for typing on a device, and none was. Nothing "
                            "was sent.")
    list_name = fields["list_name"]
    pv = O.preview(list_name, fields)
    confirmed = (form.get("hash") or "").strip()
    if not pv["ok"]:
        return review(fields, add=add, code=409,
                      error="; ".join(pv["refusals"]) + ". Nothing was sent.")
    if confirmed != pv["hash"]:
        return review(fields, add=add, code=409, error=(
            f"the onboarding changed since the review you confirmed ({confirmed or 'no hash'} "
            f"-> {pv['hash']}): read this review and confirm again. Nothing was sent."))
    run_id = reads.new_id()
    device = pv["device"]

    def work(_job_id):
        return {"run": O.run(list_name, fields, confirmed_hash=confirmed, actor=actor,
                             actor_verified=verified, reason=reason, run_id=run_id,
                             timings=O.DEFAULT_TIMINGS)["id"]}

    job = capture_job.start(list_name, f"out-of-band onboarding of {device}", actor, work,
                            kind="console onboard", announce_keys=Z.ANNOUNCE_KEYS,
                            announcer=Z.ANNOUNCER)
    log.info("oob onboard of %s in %s started by %s: job %s, run %s", device, list_name,
             actor, job, run_id)
    return _draw(_blank(list_name, device, state="running", run=run_id, job=job, add=add,
                        steps=run_steps(list_name, device)))


# ── a run's own page ───────────────────────────────────────────────────────────────────────

@bp.route("/run", methods=["GET"])
def run_page():
    """A device's newest console run, on a page of its own (the In progress list opens it by
    the device's name): its card, live while it runs. Reads the run records; contacts
    nothing."""
    from routes.v2 import _page

    from modules.nsot import oob_onboard as O

    list_name = (request.args.get("list") or "").strip()
    device = (request.args.get("device") or "").strip()
    try:
        rec = O.latest_run(list_name, device) if list_name and device else None
    except Exception as exc:                          # noqa: BLE001 - drawn, never raised
        log.exception("oob onboard: %s's runs could not be read", device)
        rec, error = None, f"{type(exc).__name__}: {exc}"
    else:
        error = ""
    kind = (rec or {}).get("kind", "")
    c = card(list_name, {"run": rec.get("id", ""), "hostname": device}) \
        if rec is not None and kind == O.KIND else None
    zc = None
    if rec is not None and kind != O.KIND:
        # A console survey or kick-start: its own card, in its run's state.
        from routes import console_ztp_v2 as R

        zc = R.card(list_name, rec.get("device_id") or 0,
                    {"step": kind, "run": rec.get("id", ""), "hostname": device})
        if rec.get("outcome") == "running":
            zc.update(state="running", rec=rec, steps=R.run_steps(kind, list_name, device))
    # The page's network: the one named, else the active one (`_page`'s default), so every
    # link it draws names a network (tests/test_page_network.py).
    named = {"list_name": list_name} if list_name else {}
    return _page("v2/oob_run.html", active_nav="devices", c=c, zc=zc,
                 has_run=rec is not None, device=device, error=error, run_list=list_name,
                 **named)
