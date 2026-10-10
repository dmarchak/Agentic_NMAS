"""The v2 screens, each with the mockup sign-off it was built from (the operator, 2026-10-02:
"no new screen or tab without a mockup and my sign-off"; rules_audit check 4).

`tests/test_signed_off_screens.py` holds every page template under `templates/v2/` that
extends the frame, and every device-page tab, to this registry EXACTLY: a new page or tab
fails until it is entered here, and entering it means naming the sign-off (when, and where
it is recorded). A screen built without one is UNSIGNED with its reason and what happens to
it; that list only shrinks.

What this cannot check: that the mockup drew every link and control the built screen has,
and that the sign-off happened. It makes the question unavoidable; the answer is a person's.
"""

#: page template (or "tab:<key>") -> (date signed off, where it is recorded)
SIGNED_OFF = {
    "landing.html": ("2026-09-29", "NSOT_GUI_BRIEF section 13: the mockup review of the landing "
                                   "page, the device list and the Device page"),
    "devices.html": ("2026-09-29", "NSOT_GUI_BRIEF section 13 (the device list); its selection "
                                   "bar, Actions and Startup column from 7.4's board A "
                                   "(FleetSelect), approved 2026-10-04 (C593)"),
    "save.html": ("2026-10-04", "7.4's board C (SaveAll, 'one Save does both'), approved "
                                "2026-10-04 (C593): the plan from stored records, the run in "
                                "place, the result with Retry the failed. Its first count is "
                                "what is measured, not the board's 'startup differs'"),
    "device.html": ("2026-09-29", "NSOT_GUI_BRIEF section 13 (the Device page); the spike in "
                                  "option A approved 2026-09-30 (brief 9b). Its ACTIONS on v2 "
                                  "(signed off 2026-10-02, the mockups' 'Device actions on v2' "
                                  "page): the preview in place of the tab's content, the result "
                                  "in place with its next steps, the refusal when the device "
                                  "moved, a check failing on a holder, and the phone width; one "
                                  "change, the read timings on hover. Built in the order "
                                  "capture, persist, rotate, deploy with Mode B. The rest "
                                  "(boards 8 to 12, signed off 2026-10-03 with two changes, "
                                  "redrawn): seed, restore (a job, carrying its list), revert "
                                  "and retry, retire (its retired record at the address), the "
                                  "Actions menu every action runs from; built in the order "
                                  "restore, revert and retry, seed, retire"),
    "about.html": ("2026-09-30", "NSOT_STAGE7_PLAN 1g, mockup version 7 (Help > About carries "
                                 "the version)"),
    "monitoring.html": ("2026-09-30", "NSOT_STAGE7_PLAN 1g, the Services mockups (fleet-wide "
                                      "Monitoring, native panels)"),
    "history.html": ("2026-10-03", "board D, History as one timeline (C369), signed off "
                                   "2026-10-03 by the operator: one reader (modules/"
                                   "history_sources.timeline) across every device and the fleet's "
                                   "own records, filtered by device, person, kind and time, "
                                   "Commits a kind; Baselines and Authorisations keep their tabs. "
                                   "Before it: NSOT_GUI_BRIEF 3.4, signed off 2026-10-02"),
    "credentials.html": ("2026-10-03", "board 7, the break-glass record on Source of truth > "
                                       "Credentials (its placement signed off 2026-10-03, the card "
                                       "the same night's revision): the record's state, the export "
                                       "(A), checked intact by the browser (B), Check a break-glass "
                                       "file (C) and the offline drill (D), every section built"),
    "help.html": ("2026-10-02", "NSOT_GUI_BRIEF 10b, the manual's mockup"),
    "templates.html": ("2026-10-05", "7.6's Templates, boards A to C (canvas v47, page '7.6 "
                                     "Source of truth, Templates'), signed off 2026-10-05: the "
                                     "network's configuration templates with their approvals "
                                     "(A); Approve…, the check device by device naming every "
                                     "failing line and where to acknowledge it (B); the result "
                                     "in place and Revoke… with its reason (C). Editing and "
                                     "bindings stay on today's page until their own boards"),
    "apply.html": ("2026-10-02", "the stepper mockup (\"Applying to 3 devices... in the order you "
                                 "set\"), signed off 2026-10-02, with the rollout order decided "
                                 "at the 2026-09-29 review. 7.4's selection may change it; then "
                                 "it needs a new mockup"),
    "monitoring_profile.html": ("2026-10-07", "C566 board A, Monitoring › Profile and Propose on v2, canvas v80 page C566"),
    "show_commands.html": ("2026-10-08", "C548 boards B and E (canvas page 'reads'), signed off "
                                         "2026-10-08 with NSOT_READS.md and R1 to R5; named "
                                         "Show commands under OBSERVE (R4)"),
    "show_commands_run.html": ("2026-10-08", "C548 boards C, D and E (canvas page 'reads'), "
                                             "signed off 2026-10-08: the summary, the groups, "
                                             "side by side and only the differences"),
    "coverage.html": ("2026-10-02", "the REDRAW, artboards A (the grid) and A2 (Deploy missing "
                                    "templates), signed off 2026-10-02: row checkboxes only, no "
                                    "box on a fully covered device; icons only with the why on "
                                    "hover; a not-reporting cell links to its diagnosis, never a "
                                    "redeploy; one combined program per device, verified and "
                                    "rolled back as one, in a settable order stopping at the "
                                    "first failure; configured-but-not-reporting templates "
                                    "excluded and named. Built to it in three steps: the "
                                    "not-reporting reader (2026-10-03), the grid and selection "
                                    "(2026-10-03; Deploy missing templates opens the profile's "
                                    "batch preview until the combined deploy replaces it), then "
                                    "the combined deploy"),
    "coverage_deploy.html": ("2026-10-02", "artboard A2, Deploy missing templates (the mockups' "
                                           "CoverageDeploy board), signed off with Coverage's "
                                           "redraw: a card per device in a settable order "
                                           "(Earlier, Later, Leave out), its ONE program, its "
                                           "checks, a configured template not reporting named "
                                           "with Diagnose, the bound statement, Back and one "
                                           "confirm. The combined deploy, Coverage's third step"),
    "update.html": ("2026-10-02","reviewed IN USE: designed in docs/UPDATE.md, used on the host "
                                  "repeatedly and corrected through C243, C244, C246, C268, "
                                  "C274, C279 and C285. Its next change gets a mockup"),
    "settings.html": ("2026-10-05", "P.8 Settings per network, the canvas's settings page: "
                                    "boards A to E approved 2026-10-05, F to J (inheritance "
                                    "optional) approved the same day as redrawn (NSOT_P8_DESIGN "
                                    "section 6 step 7 and section 8). Built: a network's cards "
                                    "with each group's three-way choice and its previewed "
                                    "switch (A, B, C, I, J2), the mode and its switch (J1), "
                                    "Default's cards counting who inherits (D, G), the scope "
                                    "bar and picker (H). Not yet: Installation (F), G's warning "
                                    "on a Default change, board I's creation form (the v1 gap "
                                    "the operator accepted)"),
    "settings_installation.html": ("2026-10-09", "Settings › Installation: board F (approved "
                                   "2026-10-05) with board F2, its records database card "
                                   "(approved 2026-10-09 with the operator's three conditions) "
                                   "and board F3, its other cards with every setting a control "
                                   "(signed off 2026-10-09, the TFTP root retired). Built: the "
                                   "page, its tabs, Connections (the Records database, NetBox "
                                   "connection, Proxmox and Commit author cards) and Server. Not "
                                   "yet: the Access and identity, Platforms and roles, AI and "
                                   "workflow and Diagnostics tabs, each said on the page and "
                                   "linked to today's"),
    "tab:overview": ("2026-09-29", "NSOT_GUI_BRIEF section 13 (the Device page's Overview)"),
    "tab:monitoring": ("2026-09-30", "NSOT_STAGE7_PLAN 1g, the Services mockups (the device "
                                     "page's service sections)"),
    "tab:logs": ("2026-09-30", "NSOT_STAGE7_PLAN 1g, the Services mockups (Logs)"),
    "tab:netbox": ("2026-09-30", "NSOT_STAGE7_PLAN 1g, the Services mockups (the NetBox "
                                 "browser's device slice)"),
    "tab:intent": ("2026-09-30", "NSOT_STAGE7_PLAN 1g: the OBSERVE heading and the device "
                                 "tabs approved, step (a)"),
    "tab:history": ("2026-10-03", "board D (C369), signed off 2026-10-03: the History page's "
                                  "timeline filtered to the device, the same reader and drawing. "
                                  "Before it: NSOT_STAGE7_PLAN 1g, step (a)"),
    "tab:neighbours": ("2026-09-30", "NSOT_STAGE7_PLAN 1g: the device tabs approved, step (a)"),
    "tab:ask": ("2026-10-08", "C547, board A (canvas page 'reads'), signed off 2026-10-08 with "
                              "the design NSOT_READS.md and R1 to R5; the tab's name approved "
                              "2026-09-30 (NSOT_STAGE7_PLAN 1g)"),
    "retired.html": ("2026-10-03", "the device-actions canvas, board 12 (Retire), its last card: "
                                   "a retired device's address shows its retired record (C185); "
                                   "NSOT_STAGE7_PLAN, the boards 8 to 12 sign-off"),
}

#: built without a recorded sign-off: (why, what happens to it). Only shrinks.
UNSIGNED = {
    "heartbeat.html": ("built 2026-10-01 (C300) with no mockup",
                       "removed: replaced by the monitoring templates (C322, NSOT_GUI_BRIEF 14)"),
    "ip_sla.html": ("built 2026-10-01 (P.9 d4) with no mockup",
                    "removed: replaced by the monitoring templates (C322)"),
    "pending.html": ("a pending onboarding's page (C291, 2026-10-01), built so every Devices "
                     "link answers", "a mockup with 7.4's onboarding on v2"),
    "not_found.html": ("the 404 page, no mockup", "kept: a page with nothing to sign off"),
}

UNSIGNED_CEILING = 4
