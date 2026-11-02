"""routes/intent_layers_v2.py — Source of Truth › Intent: a network's intent layers (board FC's
FC2, approved with changes 2026-11-01; PHASE8_PLAN 22.1 (8)(c); C2283), read-only in phase 1.

The layers committed under the network's `layers/` folder, in merge order, each with the
devices it reaches; the chosen one (``?layer=<key>``) with its values, each value's reach and
what overrides it, the secret references it names and its file's last commit; every same-rank
conflict, by path, with the devices it stops rendering (`modules/intent_layers_page.py`). The
region re-reads when intent is committed (`nmas:goldens`). Nothing here writes: adding, editing
and planning a layer's change are phase 2's.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("intent_layers_v2", __name__, url_prefix="/v2/intent")


def _ctx() -> dict:
    from modules import intent_layers_page
    from modules.nsot import listref
    from routes.list_param import named_list

    name = named_list(request) or listref.active().name
    known = listref.exists(name)
    chosen = (request.args.get("layer") or "").strip()
    return {"list_name": name, "known": known,
            "v": intent_layers_page.view(listref.resolve(name), chosen) if known else None}


@bp.route("", methods=["GET"])
def page():
    """FC2: the network's layers and the chosen one's values."""
    from routes.v2 import _page

    return _page("v2/intent_layers.html", active_nav="intent", **_ctx())


@bp.route("/region", methods=["GET"])
def region():
    """The page's region alone: its live redraw when intent is committed."""
    return _strict(render_template("v2/_intent_layers.html", **_ctx()))


# ---------------------------------------------------------------------------
# A layer's change, planned (board FC4; PHASE8_PLAN 22.2 (c)): the form, the plan as a job,
# its card. Nothing here writes: approving and running the plan is (d).
# ---------------------------------------------------------------------------

def _shown(value) -> str:
    """A committed value as the form's box holds it: YAML, masked (a layer names references,
    never values; a value a hand edit put there is masked, and the plan then refuses its
    before as not matching, never sending it)."""
    import yaml

    from modules.redact import redact_text
    from routes.bulk_intent_v2 import ABSENT_WORD

    if value is None:
        return ABSENT_WORD
    text = yaml.safe_dump(value, default_flow_style=True, sort_keys=False).strip()
    return redact_text(text.removesuffix("\n...").strip())      # a scalar's document end


def _change_form(name: str, chosen: str, path: str) -> dict:
    """The form: Edit… prefills *path* with what the layer holds there, before and after;
    Add a value… one empty row whose before is absent; no *chosen*, a new layer's name."""
    from modules.nsot import bulk_intent as B
    from modules.nsot import intent_layers as L
    from modules.nsot import listref
    from routes.bulk_intent_v2 import ABSENT_WORD

    row = {"path": "", "before": ABSENT_WORD, "after": ""}
    if chosen and path:
        try:
            docs = {L.layer_file(r, s): d for r, s, _l, d in
                    L.read_layers(listref.resolve(name).repo_dir)}
        except L.LayersRefused:
            docs = {}
        doc = docs.get(f"{L.LAYERS_DIR}/{chosen}.yml") or {}
        held = B.get_path(doc, path.split("."))
        now = _shown(None if B._is_absent(held) else held)
        row = {"path": path, "before": now, "after": now}
    m = L._FILE.match(f"{chosen}.yml") if chosen else None
    label = (L.layer_label("network" if m.group(1) == "network" else m.group(2), m.group(3) or "")
             if m else chosen)
    return {"list": name, "layer": chosen, "label": label, "new": not chosen, "rows": [row],
            "absent": ABSENT_WORD, "ranks": ("network", "site", "role", "tag")}


def _ticked(name: str) -> list:
    """The devices Devices' selection names: each ``device`` sent, or, for ALL MATCHING
    (``match=1``), the devices resolved here from the list's search and filters
    (`device_list.matching`), never the names sent."""
    from modules import device_list
    from modules.nsot import listref
    from routes.bulk_intent_v2 import _devices

    every = device_list.matching(listref.resolve(name), request.values) \
        if request.values.get("match") else None
    return _devices() if every is None else every


def _selection_form(name: str, devices: list, layers: list) -> dict:
    """FC1's Change across the N ticked… (phase 2 (f2)): the form for each ticked device's own
    document, or a layer every ticked device takes (*layers*, `intent_layers_page.view`'s, each
    with the devices it reaches)."""
    from routes.bulk_intent_v2 import ABSENT_WORD

    n = len(devices)
    shared = [{"key": l["key"], "label": l["label"], "count": l["count"],
               "beyond": len(set(l["devices"]) - set(devices))}
              for l in layers if set(devices) <= set(l["devices"])]
    return {"list": name, "selection": True, "devices": devices, "shared": shared,
            "label": f"the {n} ticked", "new": False, "layer": "",
            "rows": [{"path": "", "before": ABSENT_WORD, "after": ""}], "absent": ABSENT_WORD}


@bp.route("/change", methods=["GET"])
def change():
    """FC2's Edit… (``path``), Add a value… and Add a layer… (no ``layer``): the page with the
    change's form open above the layers. With ticked devices (Devices' Change across the N
    ticked…, ``device`` or ``match``), the form for those devices. Reads only."""
    from routes.v2 import _page

    ctx = _ctx()
    chosen = (request.args.get("layer") or "").strip()
    if ctx["known"]:
        ticked = _ticked(ctx["list_name"])
        ctx["f"] = (_selection_form(ctx["list_name"], ticked, (ctx["v"] or {}).get("layers") or [])
                    if ticked else
                    _change_form(ctx["list_name"], chosen, (request.args.get("path") or "").strip()))
    return _page("v2/intent_layers.html", active_nav="intent", **ctx)


def _target_of(form) -> tuple:
    """``(target, layer key or "")`` from a posted form: ``target=devices`` with each
    ``device`` (each ticked device's own document), ``target=layer:<key>``, or the layer form's
    ``layer`` (or a new layer's rank and slug)."""
    from routes.bulk_intent_v2 import _devices

    target = (form.get("target") or "").strip()
    if target == "devices":
        return {"devices": _devices()}, ""
    if target.startswith("layer:"):
        key = target.split(":", 1)[1]
        return key, key
    layer = (form.get("layer") or "").strip()
    if not layer:
        rank = (form.get("rank") or "").strip()
        slug = (form.get("slug") or "").strip().lower()
        layer = "network" if rank == "network" else f"{rank}-{slug}"
    return layer, layer


@bp.route("/change/plan", methods=["POST"])
def change_plan():
    """Start the plan as a job (it reads every reached device's program) and answer with its
    card at once; the card re-reads when the job announces `fleet_change`. Writes nothing."""
    from modules import identity
    from modules.nsot import fleet_change, listref
    from routes.bulk_intent_v2 import _rows, steps_of

    name = (request.form.get("list") or "").strip()
    if not listref.exists(name):
        return _plan_card({"state": "refused", "error": f"no network is named {name}"}, 404)
    target, layer = _target_of(request.form)
    label = fleet_change.named(target)
    rows = _rows()
    steps, problems = steps_of(rows)
    if isinstance(target, dict) and not target["devices"]:
        problems = problems + ["no device is ticked"]
    if problems or not steps:
        return _plan_card({"state": "refused", "list": name, "layer": layer, "label": label,
                           "error": "; ".join(problems) or "the change has no setting"}, 400)
    job = fleet_change.plan_start(name, target, steps, identity.request_actor())
    return _plan_card({"state": "planning", "list": name, "layer": layer, "label": label,
                       "job": job})


@bp.route("/change/job/<job>", methods=["GET"])
def change_job(job):
    """The plan's card for its job: still planning, the plan, its refusal, or why there is
    none. Re-read when the job announces `fleet_change`."""
    from modules.nsot import capture_job

    got = capture_job.get(job)
    name = (request.args.get("list") or "").strip()
    layer = (request.args.get("layer") or "").strip()
    if got is None:
        return _plan_card({"state": "unknown", "list": name, "layer": layer, "job": job})
    if got["state"] == "running":
        return _plan_card({"state": "planning", "list": name, "layer": layer, "job": job})
    if got["state"] == "failed":
        return _plan_card({"state": "refused", "list": name, "layer": layer,
                           "error": f"the plan did not finish: {got['error']}"})
    plan = got["payload"] or {}
    if not plan.get("ok"):
        return _plan_card({"state": "refused", "list": name, "layer": layer,
                           "error": plan.get("error", "")})
    # What the card draws, and nothing else (every carried field is drawn).
    import yaml

    def as_yaml(doc):
        return yaml.safe_dump(doc, sort_keys=False).strip() if doc else "(an empty layer)"
    selection = plan.get("target") if not plan.get("layer") else None
    drawn = {"layer": dict({k: plan["layer"][k] for k in ("key", "label", "file")},
                           before=as_yaml(plan["layer"]["before"]),
                           after=as_yaml(plan["layer"]["after"])) if not selection else None,
             # Each ticked device's own document (FC1): the devices named, the change committed
             # to each one's intent file, never the documents themselves (the rows say the change).
             "selection": {"devices": selection["devices"],
                           "taking": sorted(plan.get("texts") or {})} if selection else None,
             "base": plan["base"], "groups": plan["groups"], "unchanged": plan["unchanged"],
             "refused": plan["refused"], "headline": plan["headline"], "hash": plan["hash"],
             "planned": len(plan["devices"]),
             # The approval form carries the change as planned, and offers the planned devices
             # as the canary; what it carries is masked, so a masked value cannot match and the
             # approval refuses rather than send it.
             "rows": [{"path": ".".join(map(str, s["path"])), "before": _shown(_held(s, "before")),
                       "after": _shown(_held(s, "after"))} for s in plan.get("steps") or []],
             "hosts": [d["device"] for d in plan["devices"]],
             # The approval still commits a change no program moves on (a value each device's
             # own document holds); a layer left as it is commits nothing.
             "commits": (bool(plan.get("texts")) if selection else
                         plan["layer"]["before"] != plan["layer"]["after"]),
             "pending": [{"device": d["device"], "pending": d["pending"]}
                         for d in plan["devices"] if d["pending"]]}
    return _plan_card({"state": "plan", "list": name, "layer": layer, "job": job, "plan": drawn,
                       "elapsed_s": got.get("elapsed_s")})


def _held(step: dict, side: str):
    """A step's *side* as the form's box writes it: None for the absent marker."""
    from modules.nsot import bulk_intent as B
    value = step.get(side)
    return None if B._is_absent(value) else value


def _plan_card(p: dict, code: int = 200):
    return _strict(render_template("v2/_fleet_plan.html", p=p), code)


# ---------------------------------------------------------------------------
# (d) The approval and the run (board FC4 and FC5; PHASE8_PLAN 22.2 (3) and (4)).
# ---------------------------------------------------------------------------

@bp.route("/change/approve", methods=["POST"])
def change_approve():
    """Approve the plan as a verified person, with a summary and a reason, and run it: one job
    recomputes the plan and refuses unless its hash is the one confirmed, commits the layer
    once, then runs the canary (and every batch when the person chose not to pause), each
    device through THE deploy, the first failure stopping it. Answers at once with the run's
    card."""
    from modules import identity
    from modules.nsot import fleet_change, listref
    from routes.bulk_intent_v2 import _rows, steps_of

    name = (request.form.get("list") or "").strip()
    target, layer = _target_of(request.form)
    if not listref.exists(name):
        return _run_card({"state": "refused", "list": name, "layer": layer,
                          "error": f"no network is named {name}"}, 404)
    steps, problems = steps_of(_rows())
    if problems or not steps:
        return _run_card({"state": "refused", "list": name, "layer": layer,
                          "error": "; ".join(problems) or "the change has no setting"}, 400)
    after = (request.form.get("after_canary") or "pause").strip()
    try:
        batch = max(1, int(request.form.get("batch") or 1))
    except ValueError:
        batch = 1
    who = identity.identify(request)
    job = fleet_change.approve_and_run_start(
        name, target, steps, (request.form.get("hash") or "").strip(),
        summary=request.form.get("summary") or "", reason=request.form.get("reason") or "",
        canary=(request.form.get("canary") or "").strip(), batch=batch,
        after_canary=after if after in fleet_change.AFTER_CANARY else "pause",
        actor=identity.request_actor(), actor_kind=getattr(who, "kind", ""))
    return _run_card({"state": "running", "list": name, "layer": layer, "job": job})


@bp.route("/change/go-on", methods=["POST"])
def change_go_on():
    """After the canary, as a verified person: run every batch left, from the paused run's own
    record (its plan, commit and batches); each device's program is checked again before it is
    sent. Answers at once with the run's card."""
    from modules import identity
    from modules.nsot import capture_job, fleet_change

    paused = (request.form.get("job") or "").strip()
    name = (request.form.get("list") or "").strip()
    layer = (request.form.get("layer") or "").strip()
    got = capture_job.get(paused)
    run = (got or {}).get("payload") or {}
    if run.get("state") != "paused":
        return _run_card({"state": "refused", "list": name, "layer": layer,
                          "error": "that run is not paused after its canary (it finished, "
                                   "stopped, or this server has no record of it); nothing "
                                   "was sent"}, 409)
    who = identity.identify(request)
    job = fleet_change.run_start(name, run["plan"], run["commit"], run["batches"],
                                 after_canary="go", actor=identity.request_actor(),
                                 actor_kind=getattr(who, "kind", ""), start_at=run["next"])
    return _run_card({"state": "running", "list": name, "layer": layer, "job": job})


@bp.route("/change/run/<job>", methods=["GET"])
def change_run(job):
    """The run's card for its job: running, paused after the canary, stopped, done, refused, or
    why there is none. Re-read when the run announces `fleet_change` and as each device steps."""
    from modules.nsot import capture_job

    got = capture_job.get(job)
    name = (request.args.get("list") or "").strip()
    layer = (request.args.get("layer") or "").strip()
    if got is None:
        return _run_card({"state": "unknown", "list": name, "layer": layer, "job": job})
    if got["state"] == "running":
        return _run_card({"state": "running", "list": name, "layer": layer, "job": job})
    if got["state"] == "failed":
        return _run_card({"state": "refused", "list": name, "layer": layer,
                          "error": f"the run did not finish: {got['error']}"})
    run = got["payload"] or {}
    if run.get("state") == "refused":
        return _run_card({"state": "refused", "list": name, "layer": layer,
                          "error": run.get("error", "")})
    rows = [{"device": r.get("device", ""), "outcome": r.get("outcome", ""),
             "verified": (r.get("verify") or {}).get("ok"),
             "reason": r.get("reason") or (r.get("verify") or {}).get("summary") or ""}
            for r in run.get("results") or []]
    batch_of = {d: n for n, b in enumerate(run.get("batches") or []) for d in b}
    return _run_card({"state": run["state"], "list": name, "layer": layer, "job": job,
                      "title": _run_title(run.get("plan") or {}, layer),
                      "commit": run.get("commit", ""), "stopped": run.get("stopped", ""),
                      "rows": [dict(r, batch=batch_of.get(r["device"], 0)) for r in rows],
                      "left": [d for b in (run.get("batches") or [])[run.get("next", 0):]
                               for d in b] if run["state"] == "paused" else []})


def _run_title(plan: dict, layer: str) -> str:
    """The run card's heading: a layer's change by its label, or the change across the ticked
    devices (each one's own document)."""
    from modules.nsot import fleet_change

    target = plan.get("target") if not plan.get("layer") else None
    if target:
        return f"Change across the {len(target.get('devices') or [])} ticked"
    label = fleet_change.label_of(plan) if plan else layer
    return f"{label[:1].upper()}{label[1:]}'s change"


def _run_card(r: dict, code: int = 200):
    return _strict(render_template("v2/_fleet_run.html", r=r), code)
