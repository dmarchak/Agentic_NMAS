"""Where each device's startup config lives — the one producer of that map.

The containerlab sync harvests configs from Oxidized and writes them into a
lab's `configs/` directory. It used to write into **one** directory, which
was correct while there was one lab; r6 was onboarded into its own, and a
reboot would have brought it back on its bootstrap config.

**The sync asks rather than keeping a copy.** A second copy of a
device → lab map is how the two come to disagree — the rule that produced
`ListRef` and the reason `platform_for_device()` is the only translator —
and here the disagreement is invisible until the next reboot, because the
file lands somewhere plausible either way.

The text format exists so a shell script needs no JSON parser. It carries
**paths, not secrets**, which is why this is an ordinary read.
"""

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("clab", __name__, url_prefix="/clab")


@bp.route("/sync_targets", methods=["GET"])
def sync_targets():
    """``hostname<TAB>configs_dir<TAB>lab`` per line, or JSON.

    A device whose lab is named but describes no `configs_dir` is reported
    with an error and **omitted from the text form**, so a script consuming
    it cannot write that device anywhere. Serving it with a blank field
    would invite exactly the guess this endpoint exists to remove.
    """
    from modules.device import get_current_device_list
    from modules.nsot.credential_rotation import sync_targets as _targets

    list_name = request.args.get("list") or get_current_device_list()[0]
    try:
        result = _targets(list_name)
    except Exception as exc:                   # noqa: BLE001
        log.exception("clab: sync_targets failed for %r", list_name)
        return jsonify({"ok": False, "error": str(exc)}), 500

    if not result.get("ok"):
        return jsonify(result), 500

    if request.args.get("format") == "json":
        return jsonify(result)

    lines = [f"{r['hostname']}\t{r['configs_dir']}\t{r['lab']}"
             for r in result["targets"] if not r.get("error")]
    body = "\n".join(lines) + ("\n" if lines else "")
    if result["incomplete"]:
        # On stdout it would be parsed as a device. It goes in a header, so
        # a caller that ignores headers loses nothing it could have used.
        body += "".join(
            f"# INCOMPLETE {r['hostname']}: {r['error']}\n"
            for r in result["targets"] if r.get("error"))
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}
