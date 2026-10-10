"""Every place v2 still sends a person to today's (v1) page: the cutover gaps, by name.

The operator, 2026-10-08 (C569): a v2 page or result never links to a v1 route, except an
explicit link LABELLED "today's page" where v2 genuinely lacks the screen, and each of those
is a cutover gap, listed. A link to a v1 route carries `data-todays-page="<key>"`, its key is
here, and its words say "today's"; `tests/test_v2_links_stay_on_v2.py` holds every v2
template and every rendered v2 page to that. This list ONLY SHRINKS: a gap leaves it when v2
draws the screen and its links point there.
"""

#: key -> what v2 lacks, and where the work is recorded.
GAPS = {
    "acknowledge": "Capture's acknowledgement reason field (today's device page); C486",
    "deploy_plan": "Plan a deploy for several ticked devices (today's page); Stage 7, CUTOVER",
    "reapply": "History's Re-apply of an authorisation (today's page); Stage 7, CUTOVER",
    "onboard": "onboarding: Add device, Verify, Abandon, the bootstrap config, onboard again "
               "(today's page); Stage 7, CUTOVER",
    "logs": "the fleet's Logs screen (today's page); Stage 7, CUTOVER",
    "dhcp": "the DHCP screen (today's page); Stage 7, CUTOVER",
    "netbox": "the NetBox screen (today's page); Stage 7, CUTOVER",
}

#: Not a link: a v2 request that fails draws a minimal "Couldn't load" state (routes/
#: v2_failure.py), not a designed page; a designed one needs a mockup and sign-off.
OTHER_GAPS = {
    "v2_error_page": "a designed v2 error page: the failure state is minimal until one is "
                     "signed off (C569)",
}

#: The list's count; it may only fall, and it falls with the gap that closes (C629: closing
#: installation_settings left it at 8 over 7, room for one gap to come back unseen).
CEILING = 7
