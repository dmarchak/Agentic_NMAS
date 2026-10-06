# Help links on the v2 pages: an audit for C503

C503 (the operator, 2026-10-05): help links appear in two forms with no rule a reader can see:
the (i) alone in some places, the (i) with "How does this work?" in others. The signed-off rule
is the manual's board (NSOT_GUI_BRIEF 10b): **"How does this work?" beside every action button,
and (i) on every menu row.** This audit lists every help link in `templates/v2/` (the `how()`
and `info()` calls, 161 on 2026-10-06), its form, and what it sits beside, so the operator can
decide the rule. Nothing here has been changed to fit either rule.

**Forms.** `how()` draws the (i) with the words, or the (i) alone with `compact=True` (its
accessible name and tooltip still say the words). `info()` draws the (i) alone.

**Placement**, read from the template around each call: a *button* (a `<button>` or a link
styled as one), a *menu row* (the device page's Actions menu), a *heading* (a page title or an
op card's head row), or *other* (a tab's opening line, a paragraph, a control group).

## The count

| Beside | (i) and the words | (i) alone | Under the signed-off rule |
|---|---|---|---|
| a menu row | 0 | 7 | all follow it |
| a button | 11 | 63 | 11 follow it, 63 break it |
| a heading | 43 | 20 | the rule says nothing |
| other | 0 | 17 | the rule says nothing |

## What the practice is

**Corrected 2026-10-06, after the operator chose option 3:** the check that enforces the chosen
rule found the practice NOT consistent. Eight contexts draw a lone (i) in a card with no words
anywhere in it (the Settings cards, the Templates table, the intent editor, History's
baselines, About's installation card, Update's "Still to do on the host", Update while waiting,
and the Settings switch's choice outside a card); they are register C522. The paragraph below
described the op cards and was written as if it covered every button.

The practice in the op cards, and where it differs from the signed-off rule:

- **Words for the whole operation.** Every op card's head row carries "How does this work?"
  (43), and so does a page's main action that stands alone (11: Update, Apply, Deploy on the
  device list, Verify on Pending, and the rest below).
- **The (i) alone where the words are already on screen.** The buttons inside an op card (63:
  Confirm, Check again, Revert another commit…, the ways on) sit under the card's head, which
  already says "How does this work?", so their (i) carries the words only in its tooltip and
  accessible name. The same holds for Needs attention's row actions.
- **The (i) alone beside page titles and tab openings** (37: `info()`), where it says what the
  page or tab is, not how an action works.
- **Menu rows** carry the (i) alone (7), as signed off.

## The choice

1. **Keep the signed-off rule as written:** the 63 buttons inside cards change to carry the
   words. Each card then says "How does this work?" two to five times, once in its head and
   once beside each button.
2. **The operator's suggestion (2026-10-05):** the (i) with the words beside a button or a
   heading, the (i) alone only inside menus. The 63 buttons and the 20 page titles change to
   carry the words; the 17 others need a ruling (a tab's opening line is neither).
3. **Write down the practice:** the words where a link stands for a whole operation (a card's
   head, a page's lone action); the (i) alone where the words are already on screen (a card's
   own buttons, under a head that says them), in menus, and beside page titles and tab
   openings. Nothing changes on screen; the rule becomes one a reader can see.

Whichever is chosen, the browser check added with C505
(`tests/test_v2_layout_in_a_browser.py`, `HELP_BESIDE_JS`) already holds every drawn
"How does this work?" to sit right after the control it documents, or in a heading row, and
never beside a second one.

## Every link

**Menu rows, the (i) alone (7):** _actions_menu.html:13, 15, 19, 24, 25, 32, 35.

**Buttons, with the words (11):** _apply_preview.html:130, _coverage.html:54,
_devices.html:53, _history_remote.html:25, _monitored_by.html:23, _update.html:109,
heartbeat.html:58, ip_sla.html:44, ip_sla.html:79, pending.html:32, retired.html:20.

**Buttons, the (i) alone (63):** _attention.html:52, 53, 54, 55, 56, 72;
_breakglass_check.html:40; _breakglass_done.html:19; _breakglass_drill.html:33;
_breakglass_export.html:47, 53; _capture.html:36, 82, 87, 103, 117; _coverage.html:123;
_coverage_deploy_preview.html:80; _deploy.html:85, 92, 122, 123, 141; _history_remote.html:20;
_installation.html:27; _intent_edit.html:37, 67, 86, 90; _persist.html:43, 46, 57;
_restore.html:53, 125, 132, 161, 162; _retire.html:50, 57; _retire_finish.html:8, 16;
_retry.html:52; _revert.html:57, 72, 73; _rotate.html:52, 56, 81, 98; _seed.html:75, 98;
_settings_card.html:59; _settings_mode.html:33, 60; _settings_switch.html:50;
_template_op.html:84, 89, 121; _templates_table.html:25, 27, 29; _update.html:114, 136.

**Headings, with the words (43):** every op card's head row: _breakglass_check.html:10,
_breakglass_done.html:9, _breakglass_drill.html:13, _breakglass_export.html:18,
_capture.html:23, 29, 43, 94; _deploy.html:19, 101, 109, 133; _intent.html:18;
_persist.html:15, 53, 66; _restore.html:21, 60, 76, 141, 149, 172; _retire.html:18, 68, 95;
_retry.html:17, 65, 76; _revert.html:17, 66, 83; _rotate.html:24, 65, 73, 90; _seed.html:18,
84, 108; _template_op.html:14, 97, 108, 132; and devices.html:11 (Onboard, beside the page
title).

**Headings, the (i) alone (20):** page titles: about.html:7, apply.html:7, coverage.html:7,
coverage_deploy.html:11, credentials.html:11, devices.html:7, heartbeat.html:13, help.html:10,
history.html:11, ip_sla.html:14, landing.html:7, monitoring.html:7, pending.html:15,
retired.html:12, settings.html:12, templates.html:11, update.html:7; and _apply_job.html:60,
_breakglass_record.html:13 (two).

**Other, the (i) alone (17):** each device tab's opening line ("About this tab"):
_history.html:9, _intent.html:9, _logs.html:8, _monitoring.html:8, _neighbours.html:11,
_netbox.html:8, _overview.html:5; History's section notes: history.html:23, 58, 99;
_history_remote.html:16; beside a control that is not a button: _settings_card.html:26 (the
switch's segmented choice), history.html:83 (a baseline's Re-apply link),
_breakglass_check.html:28 (a link), _restore.html:181; device.html:19 (the Actions menu's (i),
beside the menu's button); _fleet.html:26 (the network chooser).

Line numbers are the templates' as of the C505 commit.
