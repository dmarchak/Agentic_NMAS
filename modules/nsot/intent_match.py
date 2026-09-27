"""Does a capture match the device's COMMITTED INTENT? (register C89 (c), (d))

A capture becomes the golden, so comparing a capture against the golden is
empty by construction: the trap of validating a masked render against itself.
The comparison that survives a capture is the one against committed intent,
and it is the deploy plan's own: `build_artifact(...).intent_drift`, the
render of committed intent against a config. Nothing here is a second copy
of that computation.

Three states, never two:
- ``match``: the render of committed intent reproduces the capture;
- ``differs``: it does not, with the counts and the lines (masked: the
  render is masked by construction);
- ``unknown``: no committed intent, or the render could not be made. Unknown
  is not a match: a baseline asserts intent, and an unmade comparison cannot
  support one.
"""

import logging
import os

log = logging.getLogger(__name__)

#: How many differing lines a result carries. The counts are always whole.
LINE_CAP = 20


def intent_match(repo: str, list_name: str, hostname: str, config_text: str,
                 platform: str = "") -> dict:
    """``{"state", "adds", "removes", "reordered", "lines", "why"}``."""
    from modules.nsot import hostvars, templates_repo
    from modules.nsot import manifest as _manifest
    from modules.nsot.render_artifact import build_artifact

    try:
        committed = hostvars.read_committed(repo, hostname)
    except Exception as exc:                   # noqa: BLE001
        return _unknown(f"committed intent could not be read: {exc}")
    if committed is None:
        return _unknown("no committed intent: nothing says what this device should be")
    try:
        if not platform:
            entry = _manifest.find_by_name(repo, hostname)[1] or {}
            platform = entry.get("platform") or committed.get("platform") or ""
        intent = hostvars.hydrate_secrets(committed, hostname, list_name)
        template = templates_repo.template_for_device(repo, hostname, platform)
        artifact = build_artifact(hostname, config_text, platform, template=template,
                                  host_vars=intent,
                                  template_root=templates_repo.templates_dir(repo))
    except Exception as exc:                   # noqa: BLE001
        log.warning("intent_match: %s: could not render committed intent: %s", hostname, exc)
        return _unknown(f"committed intent could not be rendered: {exc}")
    drift = artifact.intent_drift
    details = (artifact.report or {}).get("details") or {}
    lines = ([f"+ {m.get('line', '')}" for m in details.get("extra") or []]
             + [f"- {m.get('line', '')}" for m in details.get("missing") or []])
    return {"state": "differs" if drift.get("differs") else "match",
            "adds": drift.get("adds", 0), "removes": drift.get("removes", 0),
            "reordered": drift.get("reordered", 0), "lines": lines[:LINE_CAP], "why": ""}


def _unknown(why: str) -> dict:
    return {"state": "unknown", "adds": 0, "removes": 0, "reordered": 0,
            "lines": [], "why": why}


def words(result: dict) -> str:
    """One device's state in the trailer's words."""
    if result["state"] == "match":
        return "matches"
    if result["state"] == "differs":
        parts = [f"+{result['adds']}" if result["adds"] else "",
                 f"-{result['removes']}" if result["removes"] else "",
                 f"{result['reordered']} reordered" if result["reordered"] else ""]
        return " ".join(p for p in parts if p) or "differs"
    return f"unknown ({result['why']})"


def trailer(results: dict) -> str:
    """The ``Intent-Match:`` trailer for a save, computed at commit time
    whatever the path: ``yes (9 of 9)``, or ``no: r2 (+1 -1)``, naming every
    device that does not match, unknown included."""
    total = len(results)
    off = {h: r for h, r in sorted(results.items()) if r["state"] != "match"}
    if not off:
        return f"Intent-Match: yes ({total} of {total})"
    named = "; ".join(f"{h} ({words(r)})" for h, r in off.items())
    return f"Intent-Match: no: {named}"


def baseline_denial(results: dict) -> list:
    """Why these captures cannot earn a baseline, or ``[]``."""
    return [f"{h} does not match its committed intent ({words(r)})"
            for h, r in sorted(results.items()) if r["state"] != "match"]
