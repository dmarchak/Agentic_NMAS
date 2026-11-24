# The five worst card-heavy v2 pages

**How measured.** A script walked each v2 page template and every partial it includes, recursively,
counting elements whose class is a card (`card`, `op-card`, `set-card`, `heal-card`, `pack-card`,
`ntf-card`, `lq-card`, `inc-card`, `inc-rail-card`, `inc-tile`, `panel`), plus `<h2>`/`<h3>` and
`<details>`. A static count adds up every branch, including mutually exclusive states and op forms
drawn only on demand. So each candidate was then read by hand to get the cards **drawn at once on
an ordinary visit** (the "at rest" figure). Cards inside a `{% for %}` are counted once and marked
"+1 per item". Lazy-loaded cards (`hx-trigger="load"`) were checked by hand. Nothing was rendered:
these are template measurements.

| Rank | Page (URL) | Template | Cards at rest (static total) | Why it is bad |
|---|---|---|---|---|
| 1 | Settings › *network* › Network (`/v2/settings/network/<list>?tab=network`) | `templates/v2/settings.html`, with `_settings_card.html` ×14, `_network_source.html`, `_code_repo.html`, `_ai_classes.html`, `_network_delete.html` | **18** (14 generic + 4) | A flat wall of 14 near-identical cards. 13 of them hold a single setting (Endpoints holds two), and each has its own inherit/own chip, Save, and up to two `<details>` (Replace…, Who). The one consequential card, **Inventory source** (local or NetBox), is drawn after all 14 (settings.html line 63). So are Code repository, What AI may send and Delete. There is no grouping, summary or search. Lists and maps (`verify_settle_windows`, `netbox_excluded_vrfs`) appear as raw JSON fields. |
| 2 | Incident (`/v2/incident/<id>`) | `templates/v2/incident.html`, with `_inc_story.html` and `_fixit_section.html` | **≈7 top-level, 6 more nested** (14 elements; 31 `<details>`) | Four story cards (Summary, Hypotheses, Confidence, AI call) come before the incident card, which holds the one action a person came for. That card's single Details nests six more cards: timings, events, What's wrong, What Mercury has done, Seen before, The record. Facts repeat: the page h1 "Incident …" and the card's h1 title; the Summary's "What" and the card's title (`B.what`); state on the page head and in the card's status. Its 31 collapsibles hide most of the evidence. |
| 3 | SDN › Apps (`/v2/sdn/apps`) | `templates/v2/sdn.html` → `_sdn_view.html` → `_sdn_apps.html`, with `_sdn_export.html`, `_sdn_app_draft.html`, `_sdn_dhcp.html` | **3 + 1 per controller** (19 elements across states; 20 headings) | What a person comes for is what each controller runs and the apps to deploy. It is drawn only after three utility cards: NSOT export, Add an app as a Draft, DHCP steering (`_sdn_apps.html` lines 16-20). Each of those has 4-6 state variants that swap in place, so the top of the page changes shape with each one. |
| 4 | Update (`/v2/update`) | `templates/v2/update.html` → `_update.html` | **7** (12 headings) | Four of the seven cards are one list split by status: Still to do on the host, Host steps declined, Host steps said done, Host steps the tool checked done. That is one fact (host steps) told four times. The Update action itself is the second card, after "The last update"; Earlier updates is a seventh. |
| 5 | Settings › *network* › Integrations (`/v2/settings/network/<list>?tab=integrations`) | `templates/v2/settings.html`, with `_settings_card.html` ×7 and `_sdn_settings.html` | **8** (4-10 fields each) | One card per service group, each repeating the inherit/own/not-applicable chip, Save, Test, Replace… and Who. Grafana is split across two cards (Grafana: 4 keys; Grafana dashboards: 6). Monitoring profile carries 10 fields. The SDN controllers card, its own design, sits beside the generic ones. Network stage (lab/pilot/production), which also gates self-healing, is a line inside the SDN card. |

**Runners-up, measured:** Settings › Installation › Connections (`settings_installation.html`): 6
cards; the Records database card comes before NetBox, and the Record stores card lists 33 stores.
DHCP (`/v2/dhcp`, `_dhcp_view.html`): a summary plus 5 section cards, with subnets before leases
and reservations. SDN › Responses (`_sdn_responses.html`): 6 cards and 9 headings at once, but
incidents awaiting a person come first. Topology (`_topology_map.html`): 7 panels, several
conditional. Credentials › Profiles (`_credential_profiles.html`): 2-4 at rest; its 7 card
elements are mostly mutually exclusive op forms.

**Not card-heavy:** Needs attention (`landing.html` → `_attention.html`, 582 lines) draws rows, not
cards (0 card elements, 10 `<details>`). The device page's Overview (`_overview.html`) draws 2.
