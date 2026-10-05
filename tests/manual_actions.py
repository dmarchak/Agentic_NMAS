"""The action controls in the v2 templates, and the "How does this work?" link beside each
(NSOT_GUI_BRIEF 10b). Shared by tests/test_manual.py; not a test module.

The POPULATION is every control a person presses to start something: a button or link styled
as a button (class token ``btn``), a menu row (``role="menuitem"``), and a link whose words end
in an ellipsis (the convention for "opens an operation"). Each is either an OPERATION, marked
``data-op="<manual page>"`` and followed directly by ``{{ how('<that page>', ...) }}``, or a
named non-operation in ``NOT_AN_OPERATION`` with why. A new control is neither until declared,
so it fails the check rather than shipping without its link.
"""

import re

_OPEN = re.compile(r"<(button|a)\b([^>]*)>", re.S)
_JINJA = re.compile(r"\{[{%#].*?[}%#]\}", re.S)
_HOW = re.compile(r"\{\{\s*how\(\s*(?:'([a-z0-9-]+)'|([a-z_]+))")


def _attr(attrs: str, name: str) -> str:
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else ""


def controls(text: str) -> list:
    """``[{"tag", "label", "op", "after", "classes"}]`` for every control in the population.
    *after* is the template text right after the control's closing tag."""
    out = []
    for m in _OPEN.finditer(text):
        tag, attrs = m.group(1), m.group(2)
        close = text.find(f"</{tag}>", m.end())
        if close < 0:
            continue
        inner = text[m.end():close]
        label = " ".join(re.sub(r"<[^>]+>", " ", _JINJA.sub(" ", inner)).split())
        classes = _attr(attrs, "class").split()
        member = ("btn" in classes or 'role="menuitem"' in attrs
                  or (tag == "a" and label.endswith("…")))
        if not member:
            continue
        out.append({"tag": tag, "label": label or _attr(attrs, "aria-label") or " ".join(classes),
                    "op": _attr(attrs, "data-op"),
                    "after": text[close + len(tag) + 3:close + len(tag) + 3 + 200].lstrip(),
                    "classes": classes})
    return out


def how_calls(text: str) -> list:
    """Every ``how(...)`` call's literal page (a variable page is checked through its loop)."""
    return [m.group(1) for m in _HOW.finditer(text) if m.group(1)]


#: (template, the control's label) -> why it starts no operation.
NOT_AN_OPERATION = {
    ("_fleet.html", "Dashboard"): "chooses which dashboard to draw",
    ("_fleet.html", "Network"): "chooses which network to show, by opening its address",
    ("_monitoring.html", "Dashboard"): "chooses which dashboard to draw",
    ("_macros.html", "Apply"): "applies a time range to the charts (range_controls)",
    ("history.html", "Show"): "applies the commit filters",
    ("heartbeat.html", "Copy"): "copies the host step's command to the clipboard",
    ("_attention.html", "Copy"): "copies a row's command to the clipboard",
    ("_attention.html", "Open"): "navigates to the device page",
    ("_attention.html", "Open…"): "navigates to the screen the row names",
    ("_attention.html", "Open on GitHub"): "opens the CI run a row names, on GitHub, a read (C418)",
    ("_attention.html", "Acknowledge…"): "opens the reason field; the Acknowledge beside it carries the link",
    ("_attention.html", "Cancel"): "closes the reason field, recording nothing",
    ("_macros.html", "btn btn-small"): "Check again: re-reads origin and CI now, a read",
    ("_apply_job.html", "Check now"): "re-reads the job's progress: a read",
    ("_breakglass_drill.html", "Copy"): "copies the drill's command to the clipboard",
    ("_breakglass_check.html", "Close"): "closes the check, opening nothing",
    ("_breakglass_done.html", "Close"): "puts back the record's card, recording nothing",
    ("_breakglass_export.html", "Cancel"): "closes the export, building nothing",
    ("_breakglass_export.html", "Preview it again"): "reads the export's preview again: a read",
    ("_coverage.html", "Clear"): "unticks every device in Coverage's selection, recording nothing",
    ("_apply_preview.html", "Earlier"): "moves a device earlier in the rollout order the confirm carries",
    ("_apply_preview.html", "Later"): "moves a device later in the rollout order the confirm carries",
    ("_apply_preview.html", "Leave out"): "leaves a device out of the rollout the confirm carries",
    ("_coverage_deploy_preview.html", "Earlier"): "moves a device earlier in the order the confirm carries",
    ("_coverage_deploy_preview.html", "Later"): "moves a device later in the order the confirm carries",
    ("_coverage_deploy_preview.html", "Leave out"): "leaves a device out of the deploy the confirm carries",
    ("_coverage_deploy_preview.html", "Back"): "returns to Coverage, sending nothing",
    ("_timeline.html", "Show the change"): "reads one commit's masked change",
    ("device.html", "Actions"): "opens the actions menu; each row carries its own link",
    ("_capture.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_capture.html", "Edit intent…"): ("opens today's intent editor on the device (C372); "
                                        "editing intent has no How it works page of its own"),
    ("_persist.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_rotate.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_deploy.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_restore.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_restore.html", "Choose another moment"): "returns to the moments, a read",
    ("_revert.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_retry.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_seed.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_template_op.html", "btn"): "Cancel and Close: put back the templates table without the card, recording nothing",
    ("_seed.html", "Open the Intent tab"): "opens the device's Intent tab to read what was committed, a read",
    ("_retire.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_retire.html", "Back to Devices"): "opens the Devices list, a read",
    ("retired.html", "Its history (the same timeline, filtered to )"): "opens the History page filtered to the device, a read",
    ("_settings_mode.html", "Cancel"): "puts back the network's mode banner, saving nothing",
    ("_settings_mode.html", "See its settings"): "opens the network's Settings page again, a read",
    ("_settings_switch.html", "Cancel"): "puts back the group's card, saving nothing",
    ("_settings_refused.html", "Read 's settings again"): "opens the network's Settings page again, a read",
    ("_intent_edit.html", "Discard the edit"): "puts back the read-only Intent card, writing nothing",
    ("_intent_edit.html", "Back to the intent"): "puts back the read-only Intent card, a read",
    ("_intent_check.html", "Write the ticked lines into the document"): (
        "rewrites the editor's document (its unmodeled_ack block); the commit beside it, which "
        "carries the link, writes it"),
}


def problems(templates: dict) -> list:
    """Every control that is neither a linked operation nor a named non-operation, every
    operation whose link is missing or names another page, and every exemption naming a
    control that does not exist."""
    bad, seen = [], set()
    for name, text in templates.items():
        for c in controls(text):
            key = (name, c["label"])
            if c["op"]:
                after = _HOW.match(c["after"])
                page = (after.group(1) or after.group(2)) if after else ""
                if not after:
                    bad.append(f"{name}: {c['label']!r} (data-op={c['op']}) has no how() link right after it")
                elif after.group(1) and page != c["op"]:
                    bad.append(f"{name}: {c['label']!r} is marked {c['op']} and links {page}")
            elif key in NOT_AN_OPERATION:
                seen.add(key)
            else:
                bad.append(f"{name}: {c['label']!r} is neither an operation (data-op and its "
                           "link) nor a declared non-operation")
    for key in set(NOT_AN_OPERATION) - seen:
        if key[0] in templates:
            bad.append(f"{key[0]}: the exemption for {key[1]!r} names no control")
    return bad
