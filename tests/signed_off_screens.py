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
    "devices.html": ("2026-09-29", "NSOT_GUI_BRIEF section 13 (the device list)"),
    "device.html": ("2026-09-29", "NSOT_GUI_BRIEF section 13 (the Device page); the spike in "
                                  "option A approved 2026-09-30 (brief 9b)"),
    "about.html": ("2026-09-30", "NSOT_STAGE7_PLAN 1g, mockup version 7 (Help > About carries "
                                 "the version)"),
    "monitoring.html": ("2026-09-30", "NSOT_STAGE7_PLAN 1g, the Services mockups (fleet-wide "
                                      "Monitoring, native panels)"),
    "history.html": ("2026-10-02", "modules/fleet_history.py: NSOT_GUI_BRIEF 3.4, the mockup "
                                   "signed off 2026-10-02"),
    "help.html": ("2026-10-02", "NSOT_GUI_BRIEF 10b, the manual's mockup"),
    "apply.html": ("2026-10-02", "the stepper mockup (\"Applying to 3 devices... in the order you "
                                 "set\"), signed off 2026-10-02, with the rollout order decided "
                                 "at the 2026-09-29 review. 7.4's selection may change it; then "
                                 "it needs a new mockup"),
    "update.html": ("2026-10-02", "reviewed IN USE: designed in docs/UPDATE.md, used on the host "
                                  "repeatedly and corrected through C243, C244, C246, C268, "
                                  "C274, C279 and C285. Its next change gets a mockup"),
    "tab:overview": ("2026-09-29", "NSOT_GUI_BRIEF section 13 (the Device page's Overview)"),
    "tab:monitoring": ("2026-09-30", "NSOT_STAGE7_PLAN 1g, the Services mockups (the device "
                                     "page's service sections)"),
    "tab:logs": ("2026-09-30", "NSOT_STAGE7_PLAN 1g, the Services mockups (Logs)"),
    "tab:netbox": ("2026-09-30", "NSOT_STAGE7_PLAN 1g, the Services mockups (the NetBox "
                                 "browser's device slice)"),
    "tab:intent": ("2026-09-30", "NSOT_STAGE7_PLAN 1g: the OBSERVE heading and the device "
                                 "tabs approved, step (a)"),
    "tab:history": ("2026-09-30", "NSOT_STAGE7_PLAN 1g: the device tabs approved, step (a)"),
    "tab:neighbours": ("2026-09-30", "NSOT_STAGE7_PLAN 1g: the device tabs approved, step (a)"),
    "tab:ask": ("2026-09-30", "NSOT_STAGE7_PLAN 1g: the device tabs approved, step (a); not "
                              "built (drawn disabled)"),
}

#: built without a recorded sign-off: (why, what happens to it). Only shrinks.
UNSIGNED = {
    "coverage.html": ("built for P.9 (d1) on 2026-10-01 with no recorded mockup",
                      "its redraw's mockup is owed (NSOT_STAGE7_PLAN 1h)"),
    "heartbeat.html": ("built 2026-10-01 (C300) with no mockup",
                       "removed: replaced by the monitoring templates (C322, NSOT_GUI_BRIEF 14)"),
    "ip_sla.html": ("built 2026-10-01 (P.9 d4) with no mockup",
                    "removed: replaced by the monitoring templates (C322)"),
    "pending.html": ("a pending onboarding's page (C291, 2026-10-01), built so every Devices "
                     "link answers", "a mockup with 7.4's onboarding on v2"),
    "not_found.html": ("the 404 page, no mockup", "kept: a page with nothing to sign off"),
}

UNSIGNED_CEILING = 5
