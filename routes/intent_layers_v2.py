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


@bp.route("/change", methods=["GET"])
def change():
    """FC2's Edit… (``path``), Add a value… and Add a layer… (no ``layer``): the page with the
    change's form open above the layers. Reads only."""
    from routes.v2 import _page

    ctx = _ctx()
    chosen = (request.args.get("layer") or "").strip()
    if ctx["known"]:
        ctx["f"] = _change_form(ctx["list_name"], chosen,
                                (request.args.get("path") or "").strip())
    return _page("v2/intent_layers.html", active_nav="intent", **ctx)


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
    layer = (request.form.get("layer") or "").strip()
    if not layer:
        rank = (request.form.get("rank") or "").strip()
        slug = (request.form.get("slug") or "").strip().lower()
        layer = "network" if rank == "network" else f"{rank}-{slug}"
    rows = _rows()
    steps, problems = steps_of(rows)
    if problems or not steps:
        return _plan_card({"state": "refused", "list": name, "layer": layer,
                           "error": "; ".join(problems) or "the change has no setting"}, 400)
    job = fleet_change.plan_start(name, layer, steps, identity.request_actor())
    return _plan_card({"state": "planning", "list": name, "layer": layer, "job": job})


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
    drawn = {"layer": dict({k: plan["layer"][k] for k in ("key", "label", "file")},
                           before=as_yaml(plan["layer"]["before"]),
                           after=as_yaml(plan["layer"]["after"])),
             "base": plan["base"], "groups": plan["groups"], "unchanged": plan["unchanged"],
             "refused": plan["refused"], "headline": plan["headline"], "hash": plan["hash"],
             "planned": len(plan["devices"]),
             "pending": [{"device": d["device"], "pending": d["pending"]}
                         for d in plan["devices"] if d["pending"]]}
    return _plan_card({"state": "plan", "list": name, "layer": layer, "job": job, "plan": drawn,
                       "elapsed_s": got.get("elapsed_s")})


def _plan_card(p: dict, code: int = 200):
    return _strict(render_template("v2/_fleet_plan.html", p=p), code)
