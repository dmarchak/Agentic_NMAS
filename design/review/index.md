# Every page against the rubric (Stage 5 step 6)

The week plan's Stage 5 step 6: "The rest, against the rubric: the answer within 5 s without
scrolling at 1366x768, one home per task, toggles not cards for on/off, plain language, the
same layout pattern, refresh keeps state. Before/after screenshots; one line per page."

**How surveyed.** Every v2 page shot at 1366x768 on 2026-11-26 02:48 UTC by
`tools/review_screenshots.py` in the suite's fixture world (two example routers, mostly empty
data, a network the registry does not hold), after Stage 5 steps 1 to 5's first slices; the
before shots are the review's of 2026-11-24 (`design/review/shots/`, gitignored). Each first
screen was read against C's drawings (`design/proposals/C-document/`). "Boxed cards" counts the
bordered boxes in the first screen. Refresh keeps state cannot be judged from a shot (its
tests are tests/test_live_merge.py and tests/test_live_redraw_keeps_form.py). A page that shows
"nothing yet" is the fixture, not a defect: the lines judge layout and words.

**Done since the survey:** Incidents leads with its answer (9bf41fc0); History's Query pages
open on their question (aa98dc77); SDN › Apps without git's message or its repeated notice
(194d7db1, 9e015b6a); Credentials › Profiles leads with its answer; the alerts tab's green "Nothing is firing" over a reader never read
(C4269, 104ba715); the Devices list's count sentence (8611fd2f); "no reader has written <path>"
in plain words on every page that drew it. **Recorded:** the bare crash page of Topology and
AI's background page (C4270, UNKNOWN: whether an installation can reach it).

| Page | Answer above the fold | Boxed cards | Plain language | Pattern | The one change that would help most |
|---|---|---|---|---|---|
| `/v2/` (Needs attention, reworked) | yes: count sentence, then the queue | 1 (the queue list) | ok; "Clears when the source is read again successf…" is cut off on every row | yes | Drop the cut-off "Clears when…" column into the row's expand, so each row reads as one line. |
| `/v2/credentials` | partly: one warning, no sentence about state | 1 | "No list is named Lab", "the list's own page" | partly | Replace the warning with one sentence that says what to do, with a link to it. |
| `/v2/credentials/profiles` | partly: answer hidden under a precedence paragraph | 3 | "`mercury_kind`", "the store does not exist yet" | no | Lead with "No profile is set; 2 devices have no login", and fold the precedence rules into a section. |
| `/v2/device/r2` (reworked) | yes: the sentence leads | 0 | raw reader file paths (now plain words), "cisco_iosxe" | yes | Say "not read yet" in place of the reader's file path in Reachable and Alerts (done). |
| `/v2/devices` | partly: no count sentence (now added) | 2 (table card, selection bar) | ok ("golden changed" is borderline) | partly | The count sentence (done). The two "How does this work?" links in the head each sit beside their own action (Add device…, Adopt a device…), as CLAUDE.md asks of every action: kept, where this line first said remove one. |
| `/v2/devices/deploy` | yes: "No device was chosen" | 1 | ok | partly | Unbox the empty state and put it as the sentence under the title. |
| `/v2/devices/save` | yes: "No device chosen" | 1 | ok | partly | Title "Save 0 devices" reads oddly; name the task, then give the state in the sentence. |
| `/v2/dhcp` | partly: two banners, no sentence | 2 | "Kea", "Default's repository", "The DHCP reader" | no | Use one sentence: "Lab uses Default's DHCP server; not read yet (reads every 5 min)". |
| `/v2/dhcp/exclusion`, `/lease`, `/reservation`, `/subnet` | partly: render as `/v2/dhcp` | 2 | as `/v2/dhcp` | no | As `/v2/dhcp`; name the open view in the title. |
| `/v2/fixes` | yes: "17 fixes · 0 saved · 17 built-in" | 1 (table card) | ok | yes | Add the state to the count line ("none has run yet"), and unbox the table. |
| `/v2/help/getting-started` | yes: manual page opens on its topic | 0 | "`host_vars/<device>.yml`", "Mode B" in the nav | partly | Make the subtitle a one-line summary of what the page teaches. |
| `/v2/help/about` | partly: product card first, installation state second | 2 | raw reader paths (now plain), "process <pid>", "Stage 10", "origin/main" | partly | Remove Pushed/Update/Check again (the Update page's job). |
| `/v2/history` | partly: repo-state box sits above the timeline | 3 | "1 path(s) are not committed: templates/.", "save_all", "no remote" | partly | Lead with a sentence about recent changes; move the uncommitted/remote notice into a section below. |
| `/v2/history/query/ask/logs` | partly: repo box and banners push the builder down | 4 | "Loki's labels", "templates/." | no | Stop repeating History's repo box on every tab; open on the query. |
| `/v2/history/query/ask/metrics` | partly: red error leads | 4 | "Could not connect to <address>", "Prometheus" | no | Make the error one line and keep the builder in the first screen. |
| `/v2/history/query/syslog` | partly: one banner under the repeated repo box | 2 | "The logs reader", "reads Loki" | partly | Drop the repeated repo box; say "Not read yet" under the title. Check overlap with `/v2/logs`. |
| `/v2/history/reapply` | yes: refusal, but garbled | 2 (nested) | "nothing is not a baseline: a re-apply names a baseline tag" | partly | Rewrite the refusal: "Choose a baseline on History › Baselines first", with the link. |
| `/v2/incidents` | partly: the answer "No incident is open" is last | 3 (+ 2 dashed "needs" cards) | "UnknownList …", "needs: SDN incidents in the incident store" | no | Lead with "No incident is open"; move the self-healing and AI switches' detail to Self-healing (their home). |
| `/v2/intent`, `/v2/intent/change` | yes: refusal | 1 | "No network is named Lab" (the top bar says Lab) | partly | Make the refusal say what to do next, as the sentence under the title. |
| `/v2/logs` | partly: banner only, no sentence | 1 | "The logs-tail reader", "log store" | no | Put a sentence under the title: "Live device logs for Lab; not read yet". |
| `/v2/monitoring` | partly: banner after two pickers | 1 | raw reader path (now plain), "Default's Grafana" | partly | Drop the page's own Network picker (the top bar has one). |
| `/v2/monitoring/alerts` | partly: "0 firing" but never read | 2 | "(grafana-alerts)", raw reader path (now plain) | partly | No green "Nothing is firing" when alerts were never read (done, C4269). |
| `/v2/monitoring/alerts/history` | yes: "0 alerts fired and cleared" | 1 | "scripts/nmas-alert-backfill" | yes | Remove the script name from the notice. |
| `/v2/monitoring/apply` | yes: "No device was chosen" | 1 | ok | partly | Unbox the empty state and make it the sentence. |
| `/v2/monitoring/coverage` | yes: "1 of 2 devices fully covered" | 2 | raw reader path (now plain), "cisco_iosxe" | partly | Lift the count sentence out of the card; shorten the 4-line legend. |
| `/v2/monitoring/heartbeat` | partly: red refusal under a long rule | 2 (nested) | "no Loki to measure from" | partly | Lead with "Not measured: no log store is connected", with a link. Its sidebar marks Needs attention, not Monitoring. |
| `/v2/monitoring/ip-sla` | no: two cards say "no list named 'Lab'" | 4 | "no list named 'Lab'" | no | One refusal sentence under the title instead of two cards. |
| `/v2/monitoring/profile` | yes: "Lab has no profile yet" | 2 (nested) | ok | partly | Unbox: the sentence plus the Propose button. |
| `/v2/netbox` | partly: "not configured" inside a Connection card | 3 | "the integrations reader has not stored a value" | no | Lead with "NetBox isn't connected: set it up in Settings"; Connection and Networks as sections. |
| `/v2/onboard/discovered` | partly: banner only | 1 | "The discovery reader", "Kea" | partly | A sentence under the title: "No unknown device has asked for an address (not read yet)". |
| `/v2/onboard/oob/run` | no: title "No device named" in code type | 1 | "no device has no console run in no network" | no | A real title ("Console run") and a sentence that reads, with the Devices link. |
| `/v2/plans/preview` | partly: refusal names internals | 1 | internal plan ids, "'' was named" | partly | Refuse in words ("No plan was chosen: start one from …"). |
| `/v2/sdn`, `/v2/sdn/flows` | yes: "No SDN controller is connected" | 1 | ok | partly | Make the banner the sentence under the title. |
| `/v2/sdn/apps` | no: five boxes and a git error | 5 | "NSOT export", "'local'", "fatal: path 'nsot/export.json' does not exist in 'HEAD'" | no | One sentence ("No apps: Lab has no exported network to run them against; export it first"), no git error. |
| `/v2/sdn/policies` | partly: warning, then a big boxed form | 3 | "NSOT export" | no | Lead with "No policy can be drafted yet: export first"; the form as a section. |
| `/v2/sdn/responses` | partly: "0 awaiting approval · mode HITL · the loop stopped" | 3 | "HITL", "AUTO", "catalogue actions" | partly | "A person confirms each response" for "HITL"; unbox Incidents and Mode. Check overlap with Incidents. |
| `/v2/sdn/switches` | partly: two banners before the counts | 4 | "NSOT export", "DPID", "SDN controllers is not configured for Lab" | no | Merge the banners into the count sentence ("0 switches: no export and no controller"). |
| `/v2/settings` (reworked) | yes | 2 | "Lab is not a network" beside "deleted" in the strip | yes | One statement (deleted, or never existed), not both. |
| `/v2/settings/installation` (reworked) | partly: no state sentence | 1 (scope strip) | "receipts first" | partly | A sentence: "Records stay on files; NetBox <state>; …" before the tabs. |
| `/v2/settings/installation/ai/background` | no: bare crash page (C4270) | 1 | "UnknownList" | no | Draw it in its frame with a plain refusal. |
| `/v2/show-commands` | yes: the subtitle says what it is for | 1 | "`MERCURY-LOGTEST <id>`", "logging trap" | partly | Unbox the form; the logging-path test's words into its button's help. |
| `/v2/templates`, `/v2/templates/coverage` | yes: refusal | 1 | "APPROVED", "macro file"; the subtitle is a rule | partly | The state as the sentence ("N templates, M approved"; coverage's own). |
| `/v2/topology`, `/expected`, `/map` | no: bare crash page (C4270) | 1 | "UnknownList" | no | Draw it in its frame with a plain refusal. |
| `/v2/update` (reworked) | partly: a run-on "Not now:" paragraph | 1 | "origin/main", "installation_kind host", "path unit", "docs/UPDATE.md" | partly | "Not now: 3 of 10 checks fail" as one line; Checks carries the detail. |
| `/v2/device/r2?tab=ask` | yes: "Ask r2" with the box | 1 | "TIER 1" | partly | Unbox the tab body as Overview does; drop "Tier 1". |
| `/v2/device/r2?tab=history` | partly: no sentence, filters first | 1 | ok | partly | A one-line sentence ("1 event in 55 days: a planned restart"); unbox. |
| `/v2/device/r2?tab=intent` | partly: commit line, then raw YAML | 1 | commit subject, "HEAD" | no | Lead with a sentence ("Intent last changed 2 min ago by extraction"); the YAML as a section. |
| `/v2/device/r2?tab=logs` | yes: not read yet | 1 | "Reading Loki", "origin-id" | partly | "Logs not read yet"; unbox. |
| `/v2/device/r2?tab=monitoring` | partly: the answer is at the card's foot | 3 | raw reader path (now plain), "Mgmt sources" | partly | Move "r2 is configured for everything the network uses" to the top as the sentence. |
| `/v2/device/r2?tab=neighbours` | yes: not read yet | 1 | "adjacencies reader", "RIPng" | partly | Shorten the method paragraph into the info hover; unbox. |
| `/v2/device/r2?tab=netbox` | yes: NetBox not configured | 1 | "Settings > Integrations" (others say Settings › Installation › Connections) | partly | The same Settings path as the NetBox page, as a link; unbox. |

## The changes that would help a person most, in order

1. `/v2/topology` and its views, and AI's background page: a bare crash page with no frame
   (C4270, UNKNOWN whether an installation reaches it).
2. `/v2/incidents`: its answer ("No incident is open") comes last.
3. `/v2/monitoring/alerts`: green over a reader never read (done, C4269).
4. `/v2/history`: a repository-state box leads every tab.
5. `/v2/devices`: no count sentence (done; its two help links are each its action's, kept).
6. `/v2/sdn/apps`: five boxes and a git error as the main words (the git error gone, C4273;
   the repeated red notice gone).
7. `/v2/credentials/profiles`: the answer under a precedence paragraph naming a field key
   (done: the answer first, the order closed under it).
8. Shared: "no reader has written <path>" on five pages (done, in one place).
