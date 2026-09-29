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

The capture is compared in the form it is STORED (`strip_for_repo`, the
filter `golden_body` applies), never raw. A raw `show running-config` carries
`! NVRAM config last updated at ...` after every save and `ntp clock-period`
on a device running NTP, and the render has neither, so the raw comparison
counted each as a departure. Measured on the host: r2's restore commit
(ed6548e) says `Intent-Match: no: r2 (-2)`, the second line being the NVRAM
comment, while its committed golden departs by one. A deploy saves the
device, so after every deploy a device at intent read "no" and denied the
baseline.
"""

import logging
import os

log = logging.getLogger(__name__)

#: How many differing lines a result carries. The counts are always whole.
LINE_CAP = 20


def intent_match(repo: str, list_name: str, hostname: str, config_text: str,
                 platform: str = "") -> dict:
    """``{"state", "adds", "removes", "reordered", "lines", "why"}``."""
    from modules.nsot import hostvars, normalize, templates_repo
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
        stored = "\n".join(normalize.strip_for_repo(config_text or ""))
        artifact = build_artifact(hostname, stored, platform, template=template,
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


def explain(result: dict) -> str:
    """The departure in WORDS a reader needs no key for (the operator,
    2026-09-28: "committed intent: -1" was the one line that decided the
    operation, and read as a number). A `-` line is on the device and not in
    intent; a `+` line is in intent and not on the device. Up to three lines
    of each kind, the rest counted."""
    if result.get("state") == "match":
        return "matches its committed intent"
    if result.get("state") != "differs":
        return f"cannot be compared with its committed intent ({result.get('why') or '?'})"
    lines = list(result.get("lines") or [])
    parts = []
    for sign, count, what in (("-", result.get("removes", 0),
                               "on the device that intent does not have"),
                              ("+", result.get("adds", 0),
                               "in intent that the device does not have")):
        if not count:
            continue
        mine = [l[2:] for l in lines if l.startswith(sign + " ")][:DENIAL_LINES]
        shown = "; ".join(f"`{l}`" for l in mine)
        more = count - len(mine)
        parts.append(f"{count} line(s) {what}" + (f" ({shown}" + (f"; and {more} more" if more > 0
                                                              else "") + ")" if mine else ""))
    if result.get("reordered"):
        parts.append(f"{result['reordered']} section(s) in a different order")
    return "departs from its committed intent: " + ("; ".join(parts) or "differs")


def resolutions(result: dict) -> list:
    """The two ways out of a departure, each with what it ASSERTS (the operator,
    2026-09-28): when a blocker has two resolutions that mean opposite things,
    the screen names both. Never an action here, and never one click: adopting
    the device into intent is the path that degrades the record if taken by
    reflex (a hand change laundered into what should be).

    A line on the device and not in intent (`-`) CANNOT be removed by the tool:
    every deploy is merge-only and a restore is additive; removal (Mode B) is
    not built. Said, so "bring it back to intent" is not read as a button."""
    if result.get("state") != "differs":
        return []
    out = []
    if result.get("removes"):
        out += [{"do": "Remove it from the device, by hand on the console, then capture it",
                 "asserts": "the device is wrong and intent is right",
                 "note": "the tool cannot remove a line: every deploy is merge-only and a "
                         "restore is additive (removal, Mode B, is not built)"},
                {"do": "Adopt it into intent: Edit intent and commit the line",
                 "asserts": "the device is right, and intent will deploy it from now on",
                 "note": "a deliberate edit, never automatic: a hand change adopted by reflex "
                         "becomes what the tool calls intended"}]
    if result.get("adds"):
        out += [{"do": "Deploy it: the device's plan adds what intent has",
                 "asserts": "intent is right and the device is behind it", "note": ""},
                {"do": "Remove it from intent: Edit intent",
                 "asserts": "the device is right and intent was wrong", "note": ""}]
    return out


#: How many of a device's differing lines a denial names (the rest counted).
DENIAL_LINES = 3


def baseline_denial(results: dict) -> list:
    """Why these captures cannot earn a baseline, or ``[]``. Each names the
    device, the counts AND the lines (masked, up to three, the rest counted:
    a view that shows a subset says so), because "r2 (+1 -1)" sends the reader
    looking, and "load-interval 30" is the blocker (the operator, 2026-09-28:
    Save All was run on the panel's advice and could not succeed)."""
    out = []
    for h, r in sorted(results.items()):
        if r["state"] == "match":
            continue
        lines = list(r.get("lines") or [])
        named = "; ".join(lines[:DENIAL_LINES])
        more = (r.get("adds", 0) + r.get("removes", 0)) - len(lines[:DENIAL_LINES])
        detail = (f": {named}" + (f"; and {more} more" if more > 0 else "")) if named else ""
        out.append(f"{h} does not match its committed intent ({words(r)}{detail})")
    return out
