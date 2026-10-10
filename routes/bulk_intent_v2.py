"""routes/bulk_intent_v2.py — Devices › Change a setting on the ticked devices (7.4's board D,
"change a setting on N devices, not an editor", approved 2026-10-04 on canvas v32; built
2026-10-10).

One change to many devices' committed intent, as one commit, through THE bulk intent core
(`routes/templatize.bulk_plan_of` and `bulk_apply_of`, which today's JSON routes and
`scripts/nmas-bulk-intent` run): each setting is a path, the value it holds now and the value
it becomes. The preview groups the accepted devices by what changes in their rendered
configuration, each device's intent diff one level down, and draws the refused devices with
each reason; the apply recomputes it and commits only when it is what was previewed. Nothing
is sent to a device: the devices change when they are deployed.
"""

import difflib
import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("bulk_intent_v2", __name__, url_prefix="/v2/devices/change")

#: The form's rows: a new page draws this many, and Add a setting one more, up to MAX_ROWS.
ROWS, MAX_ROWS = 1, 12
#: Typed in a value's box, the setting is not there (before) or is removed (after).
ABSENT_WORD = "(absent)"


def _devices() -> list:
    return list(dict.fromkeys(d.strip() for d in request.values.getlist("device") if d.strip()))


def _rows() -> list:
    """The form's settings as typed, one dict per row, blank rows dropped."""
    paths = request.values.getlist("path")
    before = request.values.getlist("before")
    after = request.values.getlist("after")
    out = []
    for i, path in enumerate(paths):
        row = {"path": path.strip(), "before": (before[i] if i < len(before) else "").strip(),
               "after": (after[i] if i < len(after) else "").strip()}
        if row["path"] or row["before"] or row["after"]:
            out.append(row)
    return out


def _value(text: str):
    """A typed value: ``(absent)`` is the absent marker; anything else is YAML, so ``514`` is
    a number, ``true`` a boolean and ``{a: 1}`` a mapping, as the intent file holds them."""
    import yaml

    from modules.nsot.bulk_intent import ABSENT

    if text == ABSENT_WORD:
        return dict(ABSENT)
    return yaml.safe_load(text)


def steps_of(rows: list) -> tuple:
    """``(steps, problems)``: each row as the core's step, or why it is not one, by row."""
    steps, problems = [], []
    for n, row in enumerate(rows, 1):
        if not row["path"]:
            problems.append(f"setting {n} names no path")
            continue
        if not row["before"] or not row["after"]:
            problems.append(f"setting {n} ({row['path']}) needs the value it holds now and the "
                            f"value it becomes; type {ABSENT_WORD} for a setting not there, "
                            "or to remove one")
            continue
        try:
            steps.append({"path": row["path"], "before": _value(row["before"]),
                          "after": _value(row["after"])})
        except Exception as exc:                      # noqa: BLE001 (said by row)
            problems.append(f"setting {n} ({row['path']}): a value is not YAML: {exc}")
    return steps, problems


def _form(list_name: str, devices: list, rows: list, summary: str, count: int = 0) -> dict:
    rows = rows or []
    count = max(ROWS, len(rows), min(count, MAX_ROWS))
    return {"list": list_name, "devices": devices, "summary": summary,
            "rows": rows + [{"path": "", "before": "", "after": ""}] * (count - len(rows)),
            "max_rows": MAX_ROWS, "absent": ABSENT_WORD}


def _diff(was: str, text: str) -> list:
    return [l.rstrip("\n") for l in difflib.unified_diff(
        (was or "").splitlines(True), (text or "").splitlines(True), "committed", "after", n=1)
        ][2:]


def preview_of(list_name: str, devices: list, rows: list, summary: str) -> dict:
    """The card's preview: THE core's report, each accepted device's intent diff, grouped as
    the core groups them, masked on the way out."""
    from modules.outbound import mask_payload
    from routes.templatize import bulk_plan_of

    steps, problems = steps_of(rows)
    if problems:
        return {"state": "refused", "error": "; ".join(problems)}
    report, _status = bulk_plan_of({"list_name": list_name, "devices": devices,
                                    "steps": steps, "summary": summary})
    if not report.get("ok"):
        return mask_payload({"state": "refused", "error": report.get("error", ""),
                             "refused": report.get("refused", [])})
    by_host = {a["device"]: a for a in report["accepted"]}
    groups = []
    for n, g in enumerate(report["groups"], 1):
        members = [by_host[h] for h in g["devices"]]
        groups.append({
            "n": n, "added": g["added"], "removed": g["removed"],
            "devices": [{"host": a["device"], "diff": _diff(a.get("was"), a.get("text")),
                         "deployable": a["deployable"], "blocking": a["blocking_reasons"]}
                        for a in members],
            "blocked": sum(1 for a in members if not a["deployable"])})
    return mask_payload({
        "state": "preview", "headline": report["headline"], "hash": report["hash"],
        "accepted": len(report["accepted"]), "groups": groups,
        "refused": report["refused"]})


@bp.route("", methods=["GET"])
def page():
    """The page: the ticked devices and an empty change; asked by the card itself, the form
    alone, redrawn with what was typed (and one more setting with ``more``). A read: nothing
    is computed but the form."""
    from modules.nsot import listref
    from routes.list_param import named_list
    from routes.v2 import _page

    ref = listref.resolve(named_list(request) or listref.active().name)
    count = len(_rows()) + (1 if request.args.get("more") else 0)
    f = _form(ref.name, _devices(), _rows(), (request.args.get("summary") or "").strip(),
              count)
    if request.headers.get("HX-Request"):
        return _strict(render_template("v2/_bulk_intent.html", f=f, c={"state": "form"}))
    return _page("v2/bulk_intent.html", active_nav="devices", f=f, c={"state": "form"},
                 list_name=ref.name)


@bp.route("/preview", methods=["POST"])
def preview():
    """The change against each ticked device's committed intent. Writes nothing."""
    from modules.preview_confirm import confirm_part

    f = _form((request.form.get("list") or "").strip(), _devices(), _rows(),
              (request.form.get("summary") or "").strip())
    if not f["list"]:
        return _card(400, f, {"state": "refused", "error": (
            "no network was named: the change commits into one network's repository, and "
            "which is stated, never inferred")})
    c = preview_of(f["list"], f["devices"], _rows(), f["summary"])
    c["may"] = confirm_part(request, "approve")
    return _card(200 if c["state"] == "preview" else 400, f, c)


@bp.route("/apply", methods=["POST"])
def apply():
    """Commit the change as previewed, as the verified person: the core recomputes the
    preview and commits only when its hash is the one confirmed."""
    from modules import identity
    from modules.outbound import mask_payload
    from routes.templatize import bulk_apply_of

    f = _form((request.form.get("list") or "").strip(), _devices(), _rows(),
              (request.form.get("summary") or "").strip())
    confirmed = (request.form.get("hash") or "").strip()
    steps, problems = steps_of(_rows())
    if problems or not confirmed:
        return _card(400, f, {"state": "refused", "error": "; ".join(problems) or (
            "the confirm carried no preview to be bound to; nothing was committed")})
    result, status = bulk_apply_of({"list_name": f["list"], "devices": f["devices"],
                                    "steps": steps, "summary": f["summary"],
                                    "confirmed_hash": confirmed}, identity.request_actor())
    log.info("bulk_intent_v2: %s on %d device(s): %s", f["list"], len(f["devices"]),
             "committed" if result.get("ok") else result.get("error", ""))
    return _card(status, f, mask_payload(dict(result, state="done",
                                              actor=identity.request_actor())))


def _card(code: int, f: dict, c: dict):
    return _strict(render_template("v2/_bulk_intent.html", f=f, c=c), code)
