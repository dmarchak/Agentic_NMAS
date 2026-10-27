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
        # A control busy on itself carries its idle and busy words (`op-idle`, `op-busy`): its
        # name is the idle one (C602: "Earlier" read "Earlier Moving…").
        inner = re.sub(r'<span class="op-busy">.*?</span>', " ", inner, flags=re.S)
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
    ("_history_body.html", "Show"): "applies the commit filters",
    ("_logs_tail.html", "Show"): "applies the live tail's filters to the stored window, a read",
    ("_alert_evidence.html", "Show"): "narrows Monitoring › Alerts' cards to a rule, device or "
                                      "label, a read of the stored alerts and packs",
    ("_alert_history.html", "Show"): "narrows Monitoring › Alerts › History to words, a rule, a "
                                     "device and a time, a read of the alert history",
    ("_alert_history.html", "Explain"): "drawn disabled beside Build evidence on a past alert "
                                        "with no pack (Explain reads a pack); the pack Build "
                                        "evidence draws carries the live one, linked",
    ("devices.html", "Discovered"): "opens Onboard devices › Discovered, a page of its own",
    ("_onboard_discovered.html", "Search"): "narrows the discovered devices to a MAC, client-id "
                                            "or hostname, a read of the reader's stored value",
    ("heartbeat.html", "Copy"): "copies the host step's command to the clipboard",
    ("_attention.html", "Copy"): "copies a row's command to the clipboard",
    ("_attention.html", "Open"): "navigates to the device page",
    ("_attention.html", "Open…"): "navigates to the screen the row names",
    ("_attention.html", "Open on GitHub"): "opens the CI run a row names, on GitHub, a read (C418)",
    ("_attention.html", "Acknowledge…"): "opens the reason field; the Acknowledge beside it carries the link",
    ("_attention.html", "Cancel"): "closes the reason field, recording nothing",
    ("_dhcp_reserve.html", "Cancel"): "puts the Reservations tab back, writing nothing",
    ("_intent_words.html", "Discard draft"): "reopens the Intent tab without the draft, which "
                                             "lived on the page only; nothing was written",
    ("_intent_words.html", "btn btn-small iw-choice"):"answers Mercury's own question (which "
                                                       "interface a reference or a name means) "
                                                       "and continues the same draft; Draft the "
                                                       "change in the row carries the link",
    ("_dhcp_reserve.html", "Close"): "puts the Reservations tab back after a change, a read",
    ("_dhcp_subnet.html", "Cancel"): "puts the Subnets tab back, writing nothing",
    ("_dhcp_subnet.html", "Close"): "puts the Subnets tab back after a change, a read",
    ("_dhcp_exclusion.html", "Cancel"): "puts the Exclusions tab back, writing nothing",
    ("_dhcp_exclusion.html", "Close"): "puts the Exclusions tab back after a change, a read",
    ("_dhcp_lease.html", "Cancel"): "puts the Leases tab back, releasing nothing",
    ("_dhcp_lease.html", "Close"): "puts the Leases tab back after a release, a read",
    ("_decline.html", "Cancel"): "closes the decline card, committing nothing",
    ("_decline.html", "Close"): "closes the decline card after its answer, a read",
    ("_macros.html", "btn btn-small"): "Check again: re-reads origin and CI now, a read",
    ("_apply_job.html", "Check now"): "re-reads the job's progress: a read",
    ("_breakglass_drill.html", "Copy"): "copies the drill's command to the clipboard",
    ("_breakglass_check.html", "Close"): "closes the check, opening nothing",
    ("_breakglass_done.html", "Close"): "puts back the record's card, recording nothing",
    ("_breakglass_export.html", "Cancel"): "closes the export, building nothing",
    ("_records_db_replace.html", "Cancel"): "puts the records database card back, replacing nothing",
    ("_install_card_replace.html", "Cancel"): "puts the Installation card back, replacing nothing",
    ("_install_card.html", "Cancel"): "puts the AI card back from the day cap's confirmation, "
                                      "saving nothing",
    ("_install_platforms_preview.html", "Cancel"): "puts the map cards back, saving nothing",
    ("_records_stores.html", "Cancel"): "puts the record stores back, moving nothing",
    ("_remote_setup.html", "Close"): "closes the remote set-up card, recording nothing",
    ("_netbox_job.html", "Close"): "returns to the NetBox page, a read; a job runs on",
    ("_netbox_removals.html", "Close"): "returns to the NetBox page, a read",
    ("_network_create.html", "Change the name"): "puts the name's form back, creating nothing",
    ("_template_edit.html", "Discard the edit"): "puts the Templates table back, a read; "
                                                 "nothing was written",
    ("_template_edit.html", "Open it again"): "opens the template again on what is committed "
                                              "now, a read",
    ("_template_edit.html", "Close"): "puts the Templates table back, a read",
    ("_reload.html", "btn"): "Cancel or Close: puts back the tab the card replaced, a read",
    ("_console_server_op.html", "btn btn-small"): "Cancel or Close: reopens Settings › "
                                                  "Installation › Console servers, writing "
                                                  "nothing",
    ("_reload.html", "Its break-glass record"): "opens Credentials, where the record is, a read",
    ("_template_bindings.html", "btn"): "Cancel or Close: puts the Templates table back, a read",
    ("_logs_view.html", "Copy the link"): "copies this view's address (the question it carries), "
                                          "a read",
    ("_logs_view.html", "Show"): "redraws the opened device's lines with the filters asked, a read",
    ("_history_metric.html", "Copy the link"): "copies this question's address (its device, "
                                               "interface and range), a read",
    ("_history_metric.html", "Show"): "asks the question again for the device and interface "
                                      "chosen, a read",
    ("_history_views.html", "Ask your own (PromQL or LogQL)…"): "opens Ask your own's metrics "
                                                                "builder (board E3; Code one "
                                                                "click away), a read",
    ("_history_views.html", "Pin"): "pins a saved view for everyone: a link to a read, in "
                                    "Mercury's own store, recorded; no device",
    ("_history_views.html", "Unpin"): "unpins a saved view for everyone, recorded; no device",
    ("_history_views.html", "Remove…"): "asks, in place, whether to remove a saved view; "
                                        "nothing written",
    ("_history_views.html", "Remove"): "removes a saved view: only the link goes, the history "
                                       "it asks is untouched, recorded; no device",
    ("_history_views.html", "Keep"): "keeps the saved view and redraws the list, a read",
    ("_history_save.html", "Save this view…"): "asks a title for the view the page shows, in "
                                               "place; nothing written",
    ("_history_save.html", "Save"): "saves the view the page shows for the network, with its "
                                    "title, recorded; no device",
    ("_history_metric.html", "Run"): "asks your own query (the question's PromQL edited, or Ask "
                                     "your own's PromQL or LogQL), its text in the address, a read",
    # Both Ask your own builders' shared pieces (boards E3 and F3, _history_ask_parts.html).
    ("_history_ask_parts.html", "Ask"): "asks Prometheus (metrics) or Loki (logs) the query the "
                                        "builder formed, a read; nothing is written and nothing "
                                        "reaches a device",
    ("_history_ask_logs.html", "Add"): "adds a device Loki holds lines from to the choices and "
                                       "redraws the query, asking nothing",
    ("_history_ask_logs.html", "Cancel"): "closes a line's Reveal… box, revealing nothing",
    ("_history_ask_parts.html", "Apply"): "applies From… to…'s range to the choices and redraws "
                                          "the query, asking nothing",
    ("_history_ask_parts.html", "Cancel"): "closes From… to…, changing nothing",
    ("_history_ask_parts.html", "Copy the link"): "copies the builder's address (every choice, "
                                                  "asked), a read",
    ("_history_ask_metrics.html", "Add"): "adds a device, an interface or a filter to the "
                                          "metrics builder's choices and redraws the query, "
                                          "asking nothing",
    ("_topology_map.html", "'s Neighbours"): "opens that end's Neighbours tab on its device "
                                             "page, a read",
    ("_credential_profiles.html", "Cancel"): "puts the profiles table back, writing nothing",
    ("_credential_profiles.html", "Close"): "puts the profiles table back after a scheduled "
                                            "rotation run, a read",
    ("_bulk_intent.html", "Back to Devices"):"returns to Devices, a read",
    ("_bulk_intent.html", "Change the settings"): "puts the change's form back with what was "
                                                  "typed, computing nothing",
    ("_bulk_intent.html", "Add a setting"): "redraws the form with one more row, computing "
                                            "nothing",
    ("_adopt.html", "Close"):"returns to Devices, a read; nothing was sent",
    ("_adopt.html", "Open 's page"): "opens the adopted device's page, a read",
    ("_onboard_add.html", "Close"): "returns to Devices, a read; nothing was created",
    ("_onboard_add.html", "Open 's page"): "opens the new device's pending page, a read",
    ("_onboard_add.html", "Add another"): "puts an empty Add device form back, creating nothing",
    ("_onboard_add.html", "Change the fields"): "puts the fields back with their values, "
                                                 "creating nothing",
    ("_onboard_pending.html", "btn btn-small"): "Cancel or Close: puts the pending device's "
                                                "actions back at rest, a read",
    ("_onboard_pending.html", "btn btn-small btn-primary"): "opens the verified device's page or "
                                                            "Devices, a read",
    ("_network_create.html", "Open 's settings"): "opens the new network's Settings page, a read",
    ("_network_create.html", "Its devices"): "opens the new network's Devices, a read",
    ("_network_delete.html", "Cancel"): "puts the Delete card back, deleting nothing",
    ("_network_source.html", "Cancel"): "puts the Inventory source card back, changing nothing",
    ("_network_delete.html", "Default's settings"): "opens Default's Settings page, a read",
    ("_history_remote.html", "btn btn-small"): "Set up the remote… / Remote set-up…: opens the "
                                               "set-up card, a read; each act in it carries its link",
    ("_records_stores.html", "Close"): "puts the record stores back after a move's result, a read",
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
    ("_timeline.html", "Show the prompt and the answer"): "reads one AI call's masked prompt "
                                                          "and its answer (15.14)",
    ("_timeline.html", "Load more"): "reads the timeline's next rows older than the last one "
                                     "shown and draws them under it (15.14 part B)",
    ("_history.html", "Go"): "starts a device's History tab at the end of the day chosen, a "
                             "read (15.14 part B)",
    ("_actions_menu.html", "Actions"): "opens the actions menu; each row carries its own link",
    ("_devices.html", "Actions"): "opens the Devices selection's actions menu; each row carries "
                                  "its own link (C593, board A)",
    ("_devices.html", "Clear selection"): "unticks every device in the Devices selection, "
                                          "recording nothing",
    ("_save.html", "Back"): "returns to Devices, sending nothing",
    ("_sc_pick.html", "Remove"): "redraws the card without that command row; asks no device",
    ("_sc_pick.html", "Add a command"): "redraws the card with one more command row; asks no device",
    ("_sc_pick.html", "Use"): "opens Show commands with the saved set's commands filled in",
    ("_sc_result.html", "Side by side"): ("draws two devices' answers side by side on the run's "
                                          "page, the pair the person chose; reads only the run's record"),
    ("_lp_result.html", "Open 's Logs"): ("opens the device's Logs tab, what Loki holds from it; a "
                                           "read"),
    ("_ask.html", "Compare with the last answer"): ("redraws the card with the lines that "
                                                    "changed since the device's last answer; "
                                                    "reads only the kept runs"),
    ("_capture.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_capture.html", "Edit intent…"): ("opens the device's Intent tab editor on v2 (C569); "
                                        "editing intent has no How it works page of its own"),
    ("_persist.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_rekey.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_privileged.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_rotate.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_deploy.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_restore.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_restore.html", "Choose another moment"): "returns to the moments, a read",
    ("_revert.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_retry.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_seed.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_template_op.html", "btn"): "Cancel and Close: put back the templates table without the card, recording nothing",
    ("_profile_op.html", "btn"): "Cancel and Close: put back the profile table without the card, recording nothing",
    ("_profile_op.html", "the version held by"): (
        "Use (or Using) the version held by <devices> (C1269): previews the proposal again with "
        "that version of the section chosen, a read; the commit beside it, which carries the "
        "link, records the choice"),
    ("_seed.html", "Open the Intent tab"): "opens the device's Intent tab to read what was committed, a read",
    ("_retire.html", "btn"): "Cancel and Close: put back the tab the card replaced, recording nothing",
    ("_retire.html", "Back to Devices"): "opens the Devices list, a read",
    ("retired.html", "Its history (the same timeline, filtered to )"): "opens the History page filtered to the device, a read",
    ("_settings_mode.html", "Cancel"): "puts back the network's mode banner, saving nothing",
    ("_settings_mode.html", "See its settings"): "opens the network's Settings page again, a read",
    ("_settings_switch.html", "Cancel"): "puts back the group's card, saving nothing",
    ("_settings_refused.html", "Read 's settings again"): "opens the network's Settings page again, a read",
    ("_settings_refused.html", "Read the installation's settings again"): "opens Settings › Installation again, a read",
    ("_intent_edit.html", "Discard the edit"): "puts back the read-only Intent card, writing nothing",
    ("_intent_edit.html", "Back to the intent"): "puts back the read-only Intent card, a read",
    ("_apply_job.html", "Started: its progress is below"): (
        "the batch confirm drawn again by its answer (C850, out of band), disabled: it starts "
        "nothing, and the confirm it replaces keeps its link beside it"),
    # C537: the In progress chip's rows open a device's page, which reopens the card (a read).
    ("_in_progress.html", "btn btn-small"): "Open its card, or Open <device>: opens the device's "
                                            "page, where a running operation's card reopens, a read",
    ("_in_progress.html", "Open the result"): "opens the device's page on the finished "
                                              "operation's result, a read",
    # The one-decision out-of-band onboarding: a console run's row opens the run's own page
    # (its live stepper, a read), on the chip's list and on Devices' In progress list.
    ("_in_progress.html", "Open its stepper"): "opens a console run's own page, its live "
                                               "stepper, a read",
    ("_in_progress_panel.html", "Open its stepper"): "opens a console run's own page, its "
                                                     "live stepper, a read",
    ("_in_progress_panel.html", "btn btn-small"): "Open its card, or Open <device>: opens the "
                                                  "device's page, where a running operation's "
                                                  "card reopens, a read",
    ("_console_ztp.html", "Open this run's page – the run continues"): (
        "opens the run's own page while it runs (C1595), a read; the run goes on"),
    ("_oob_onboard.html", "Open this run's page – the run continues"): (
        "opens the run's own page while it runs (C1595), a read; the run goes on"),
    ("_oob_onboard.html", "Open 's page – the run continues"): (
        "opens the device's page once Create has made it (C1595), a read; the run goes on"),
    ("_oob_onboard.html", "Open 's page to Verify"): (
        "opens the onboarded device's page, where Verify is its own operation, a read"),
    ("_oob_onboard.html", "Open 's page"): "opens the pending device's page, a read",
    ("_oob_onboard.html", "Change the fields"): "puts back Add device's form with its fields, "
                                                "creating nothing",
    ("oob_run.html", "Open Devices"): "opens Devices, a read",
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
