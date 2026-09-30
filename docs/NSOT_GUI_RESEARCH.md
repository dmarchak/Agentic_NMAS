# GUI redesign, step 1: research

*Section 1g of [NSOT_STAGE7_PLAN.md](NSOT_STAGE7_PLAN.md). Written 2026-09-29 for the
operator's sign-off. The design brief (step 2) is not started. It begins from this document
once the operator has signed it off.*

## What this is

This document records how established products and design systems handle the patterns the
operator named:
- navigation;
- row and bulk actions;
- status at a glance;
- progressive disclosure;
- empty states;
- forms;
- spacing and typography;
- in-product help;
- page layout.

It also covers three things the network products add that bear on this tool: a
"needs attention" view, change review, and the audit trail. Each finding carries its
source.

The last column of each table, **"For NMAS"**, is an observation to carry into the brief.
It is not a decision. Appendix A is a measured inventory of today's GUI, which the brief
will map from.

**Sources.**
- **Design systems:** AWS Cloudscape, Red Hat PatternFly and IBM Carbon, from their
  official guidance pages.
- **Network products:** Cisco Meraki Dashboard, Juniper Mist, Arista CloudVision, Cisco
  Catalyst Center and NetBox 4.x, from their official documentation, lab guides and
  (for NetBox) source code.

**Where the sources ran out.**
- Arista's help center renders client-side and could not be fetched. CloudVision rests on
  Arista's own Test Drive lab guides and search excerpts of its configuration guide.
- Some Meraki and Arista items rest on a search-result excerpt rather than a full read.
  They are marked *(excerpt)*.
- Carbon has no current page-header guidance page, and PatternFly's typography page moved.
  Both are noted where they would have been cited.
- NetBox's per-model "Help" link is documented only in a plugin issue, so it is treated as
  unverified.

## 1. Navigation

| Source | What it does | For NMAS |
|---|---|---|
| Cloudscape | Side navigation for the structure. Settings, notifications and the user menu sit in the top bar's utility area. The side navigation is two levels deep at most, and deeper pages are reached by links and breadcrumbs. "Keeping the navigation shallow helps." ([service navigation](https://cloudscape.design/patterns/general/service-navigation/), [side navigation](https://cloudscape.design/patterns/general/service-navigation/side-navigation/)) | The five destinations plus Settings and Help fit one level. The device page is reached by link and breadcrumb, never as a sidebar item. |
| PatternFly | Vertical navigation "when you have 5 or more primary navigation items". Settings (cog) and Help sit in the masthead, with the user menu right-most. Cascading flyouts are not recommended. ([navigation](https://www.patternfly.org/components/navigation/design-guidelines), [masthead](https://www.patternfly.org/components/masthead/design-guidelines)) | Five destinations crosses its threshold for a sidebar. |
| Carbon | A left panel for more than five items, and never three tiers ("use tabs within the page"). Help has a fixed place among the header icons. ([left panel](https://carbondesignsystem.com/components/UI-shell-left-panel/usage/), [header](https://carbondesignsystem.com/components/UI-shell-header/usage/)) | Tabs inside a page (the device page's sections) are the sanctioned third level. |
| Catalyst Center | A collapsible main menu of Design, Policy, Provision, Assurance, Workflows, Tools, Platform, Activities and System. The first four follow the network's lifecycle. ([user guide, ch. 1](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/3-1-x/user_guide/b_cisco_catalyst_center_user_guide_3_1_x/b_cisco_catalyst_center_ug_3_1_x_chapter_01.html)) | The only product organised by task. That is the plan's principle (section 0: "around the task list, never around subsystems"). |
| Meraki | Menus by product (Network-wide, Security & SD-WAN, Switching, Wireless), each split into Monitor and Configure, plus Organization for administration. ([organization menu](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Design_and_Configure/Organizations_and_Networks/Organization_Menu)) | Organised by object type, which the plan rejected for NMAS. |
| Mist, NetBox | A left menu by object type. NetBox's 4.0 menus run Organization, Racks, Devices, Connections, IPAM … Admin. ([Mist](https://www.juniper.net/documentation/us/en/software/mist/mist-management/topics/concept/guide-intro.html), [NetBox menu.py](https://raw.githubusercontent.com/netbox-community/netbox/main/netbox/netbox/navigation/menu.py)) | NetBox is a record browser, and its menu is its schema. NMAS's questions are tasks. |
| CloudVision | Mixes task areas (Studios, Workspaces, Change Control) with object areas (Devices, Events). ([lab guide](https://labguides.testdrive.arista.com/2025.1/data_center/cvp_adv_cc_studio/)) | |

**All three design systems agree:**
- a left sidebar, shallow (two levels at most);
- settings, help and the user in a utility area;
- page-level tabs for a third level.

**Among the products,** administration is a separate area every time (Meraki
Organization, Mist Organization > Admin, Catalyst System, NetBox Admin).

## 2. Row actions, bulk actions, lists

| Source | What it does | For NMAS |
|---|---|---|
| Cloudscape | Actions for ONE item go in the row; actions on the collection or on a selection go in the table header. It also asks for: the total count beside the title; status in the second column; filtering, pagination and sorting only above five items; `-` for an empty value; the selected count in the header, never "0/150"; and selection reset on filter or page changes. ([actions](https://cloudscape.design/patterns/general/actions/), [table](https://cloudscape.design/components/table/)) | Plan 6a already decided a Fleet row carries status and a link, and no action; the selection carries the batch operations. Cloudscape's table rules are a checklist for the Fleet list. |
| PatternFly | Row actions live in a kebab in the final column. A toolbar exposes "no more than 2 buttons", one primary and one secondary, and the rest go to an overflow menu. Bulk select covers the current page. ([table](https://www.patternfly.org/components/table/design-guidelines), [toolbar](https://www.patternfly.org/components/toolbar/design-guidelines)) | The selection toolbar: one primary action plus an overflow, not the current bulk panel's six sub-cards. |
| Carbon | An overflow menu per row, inline when there are fewer than three actions. Selecting rows raises a batch action bar at the top and disables the row actions. Pagination sits at the bottom. Destructive items sit below a divider. ([data table](https://carbondesignsystem.com/components/data-table/usage/), [overflow menu](https://carbondesignsystem.com/components/overflow-menu/usage/)) | |
| Meraki, Mist, Catalyst, NetBox | Every one uses a searchable, column-configurable table, with checkbox selection feeding a bulk menu above it: Meraki's inventory (Claim, Add, Remove), Mist's "More" menu, Catalyst's "Actions" drop-down, NetBox's bulk edit and delete. A row's name is the link to the device page. ([Meraki inventory](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Inventory_and_Devices/Using_the_Organization_Inventory), [Mist switches](https://www.juniper.net/documentation/us/en/software/mist/mist-wired/topics/concept/switches-page-mist.html), [Catalyst inventory](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/3-1-x/user_guide/b_cisco_catalyst_center_user_guide_3_1_x/b_cisco_catalyst_center_ug_3_1_x_chapter_011.html), [NetBox tables](https://netboxlabs.com/docs/netbox/plugins/development/tables/)) | The same shape as plan 6a. Today's rows carry five buttons each (Appendix A). |

## 3. Status at a glance

| Source | What it does | For NMAS |
|---|---|---|
| Cloudscape | "Always include text"; "never rely on color alone". Types: error, warning, success, information, stopped, pending, in progress, loading, not started. ([status indicator](https://cloudscape.design/components/status-indicator/)) | One status vocabulary, with icon and word as well as colour. The project's rule that colour is part of the result (a partial success is never green) fits here. |
| PatternFly | STATUS (danger, warning, success, info) and SEVERITY (critical, important, moderate, minor) are separate sets and "not interchangeable"; an icon never appears without a label. ([status and severity](https://www.patternfly.org/patterns/status-and-severity)) | Needs attention rows carry a level (a severity) while devices carry a state (a status). Keeping them as two vocabularies avoids "warning" meaning two things. |
| Carbon | At least two of colour, shape and symbol. Named attention tiers: high, medium, low. ([status indicator](https://carbondesignsystem.com/patterns/status-indicator-pattern/)) | |
| Meraki | A colour per device (online, alerting, offline, dormant), the positive state moved from green to light blue, and a 24-hour connectivity bar per row. A "Health" widget shows healthy against total per class, takes the worst status, and links to the list. ([status colors](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Troubleshooting_and_Support/Troubleshooting/Updated_status_colors), [health](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Monitoring_and_Reporting/Meraki_Health_-_Network-Wide)) | "Healthy of total, worst first" is the project's "checked 7 of 9" rule, drawn. |
| Catalyst | Network Health splits devices into Good, Fair, Poor and No data. Issues are ranked P1 to P4, each with its impact and "suggested actions". ([assurance](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center-assurance/3-1-x/b_cisco_catalyst_assurance_3_1_x_ug/b_cisco_catalyst_assurance_3_1_x_ug_chapter_0110.html)) | "No data" as its own bucket matches the rule that unknown is never counted as healthy. |

## 4. Progressive disclosure

| Source | What it does | For NMAS |
|---|---|---|
| Cloudscape | Expandable sections hold "only secondary content"; "don't hide error messages or critical information"; no nesting; collapsed by default. A split panel shows the selected rows' details and never replaces a details page. Help works as a ramp: text on the page, then the help panel, then the documentation. ([expandable section](https://cloudscape.design/components/expandable-section/), [split view](https://cloudscape.design/patterns/resource-management/view/split-view/), [help system](https://cloudscape.design/patterns/general/help-system/)) | Matches the presentation rule already decided: the answer first, the evidence one level down, and nothing that decides the outcome hidden. |
| PatternFly | "Hide optional or advanced content by default", with toggle text that changes ("Show more"/"Show less"). Primary-detail puts a list beside a drawer. ([expandable section](https://www.patternfly.org/components/expandable-section/design-guidelines), [primary-detail](https://www.patternfly.org/patterns/primary-detail/design-guidelines)) | |
| Carbon | Disclosures are "user initiated", one open at a time, never nested, and "do not hide critical information". ([disclosures](https://carbondesignsystem.com/patterns/disclosures-pattern/)) | |
| Products | The device page opens on a summary, and detail lives in tabs: Meraki's "Summary" tab by default; Catalyst Device 360's health timeline, summary and then Issues; Mist's front panel and tiles; NetBox's attribute panels and then tabs. ([Meraki AP page](https://documentation.meraki.com/Wireless/Operate_and_Maintain/User_Guides/Monitoring_and_Reporting/Access_Point_Status_Page), [Catalyst 360](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center-assurance/3-1-x/b_cisco_catalyst_assurance_3_1_x_ug/b_cisco_catalyst_assurance_3_1_x_ug_chapter_0110.html), [Mist switch](https://www.juniper.net/documentation/us/en/software/mist/mist-wired/topics/concept/switch-dashboard.html), [NetBox object.html](https://raw.githubusercontent.com/netbox-community/netbox/main/netbox/templates/generic/object.html)) | Plan 1c's Overview first (intent, device, the difference, each check with its time) is the same shape. |

## 5. Empty states

| Source | What it does | For NMAS |
|---|---|---|
| Cloudscape | A heading that explains the state, plus one next action: "Create…" when there are no resources, "Clear filter" when a filter returns nothing. "Don't use empty states for errors"; a table's failed fetch is an alert inside its empty state. ([empty states](https://cloudscape.design/patterns/general/empty-states/), [table view](https://cloudscape.design/patterns/resource-management/view/table-view/)) | Three different facts, never one blank: nothing yet, nothing matches, and could not be read. The project already requires the third to be distinct ("a failed read is not an empty list"). |
| PatternFly | Icon, heading, why the space is empty, and what the user can do. Types: getting started, no results, required configuration, no access, back-end failure, creation. "Avoid saying that something hasn't been found", which reads as a system error. ([empty state](https://www.patternfly.org/components/empty-state/design-guidelines)) | "Required configuration" matches the project's `unset_guard` and not-configured states. |
| Carbon | Three types: no data, user action (no results) and error (permissions, system, configuration). Plain language with no codes; a tertiary button, so an empty state never holds a primary action. ([empty states](https://carbondesignsystem.com/patterns/empty-states-pattern/)) | |

## 6. Forms, and confirming what cannot be undone

| Source | What it does | For NMAS |
|---|---|---|
| Cloudscape | Mark only the optional fields. Validate on blur, never on first visit, and "don't disable the form's submission button". Server errors go in an alert above submit. Deletion has three tiers, the last a typed "confirm" for a resource that cannot be recreated or whose loss risks an outage. ([form field](https://cloudscape.design/components/form-field/), [validation](https://cloudscape.design/patterns/general/errors/validation/), [delete](https://cloudscape.design/patterns/resource-management/delete/delete-with-additional-confirmation/)) | The preview-then-confirm component is already this project's highest tier: the exact program plus a confirm bound to its hash. The research does not suggest adding a typed word on top of it. |
| PatternFly | Single-column forms with top-aligned labels. Required fields get an asterisk, or "All fields are required". Validate on blur or on submit. A serious deletion enables its danger button only once the phrase is typed. ([form](https://www.patternfly.org/components/forms/form/design-guidelines), [modal](https://www.patternfly.org/components/modal/design-guidelines)) | Retire is the one action that removes a device from management. Typing the device's name is a candidate for it. |
| Carbon | Single-column. Mark whichever group is the minority, required or optional. Validate inline when a field loses focus. A high-impact deletion has the user "type the name of the resource". ([forms](https://carbondesignsystem.com/patterns/forms-pattern/), [common actions](https://carbondesignsystem.com/patterns/common-actions/)) | |

## 7. Spacing and typography

| Source | What it does | For NMAS |
|---|---|---|
| Cloudscape | A 4 px base unit, from 2 to 40 px. Body text 14/20, headings 24/20/18/16/14. Comfortable by default, with a compact mode "for data intensive views". ([spacing](https://cloudscape.design/foundation/visual-foundation/spacing/), [typography](https://cloudscape.design/foundation/visual-foundation/typography/), [density](https://cloudscape.design/foundation/visual-foundation/content-density/)) | Bootstrap's spacers are 4, 8, 16, 24 and 48 px (0.25 to 3 rem), so a 4 px scale is already the stack's own. A design layer over Bootstrap needs tokens and a type scale, not a new grid. |
| PatternFly | Spacers xs 4 to 4xl 80 px. Headings h1 24, h2 20, h3 18; body 14 px; page padding 24 px. Density per component (a compact table). ([spacers](https://www.patternfly.org/foundations-and-styles/spacers), [typography](https://www.patternfly.org/foundations-and-styles/typography)) | All three converge on a 14 px body and 24 px page headings. |
| Carbon | An 8 px mini unit, with tokens from 2 to 160 px. A 14 px "productive" type set for tools. ([2x grid](https://carbondesignsystem.com/elements/2x-grid/overview/), [spacing](https://carbondesignsystem.com/elements/spacing/overview/), [type sets](https://carbondesignsystem.com/elements/typography/type-sets/)) | |

## 8. In-product help

| Source | What it does | For NMAS |
|---|---|---|
| Cloudscape | "Info" links anchored to headers and field labels open a side help panel, which shows page-level help by default. "Learn more" links to the documentation. Never a popover for help; tooltips only for icons and truncated text. ([help system](https://cloudscape.design/patterns/general/help-system/), [popover](https://cloudscape.design/components/popover/)) | The manual's per-screen link (section 1g) is Cloudscape's "Learn more". Plan section 2.4 ("the explanation, one expansion away") is its help panel. |
| PatternFly | A tooltip identifies (on hover); a popover describes (on click, from a question-circle icon on labels, titles and column headings). Documentation lives in the masthead's Help menu. ([tooltip](https://www.patternfly.org/components/tooltip/design-guidelines), [popover](https://www.patternfly.org/components/popover/design-guidelines)) | |
| Carbon | Tooltips carry "nonessential" information with no interactive elements; a toggletip opens on click and may hold links. "Never house essential information in a tooltip"; use "i", not "?". ([tooltip](https://carbondesignsystem.com/components/tooltip/usage/), [toggletip](https://carbondesignsystem.com/components/toggletip/usage/)) | Today's pages put reasoning in `title` hovers. Anything a person must read to act moves out of a hover. |
| Products | A top-right "?" to documentation and support (Meraki, Mist, Catalyst); guided walkthroughs (Mist Visual Guides, Catalyst Interactive Help); a global search. ([Mist help](https://www.juniper.net/documentation/us/en/software/mist/mist-management/topics/task/help.html), [Catalyst ch. 1](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/3-1-x/user_guide/b_cisco_catalyst_center_user_guide_3_1_x/b_cisco_catalyst_center_ug_3_1_x_chapter_01.html)) | The operator's requirement puts Help in the sidebar, not only in the top bar. The brief reconciles that with the utility-area convention. |

## 9. Page layout

| Source | What it does | For NMAS |
|---|---|---|
| All three | **One primary button per page**, stated as a rule by Cloudscape ("The Highlander") and Carbon, and as "try to limit" by PatternFly. Breadcrumbs show where a page sits, not the user's history. A page header holds the title, a brief description, and the actions at its right. ([Cloudscape button](https://cloudscape.design/components/button/), [Carbon button](https://carbondesignsystem.com/components/button/usage/), [PatternFly page](https://www.patternfly.org/components/page/design-guidelines), [PatternFly breadcrumb](https://www.patternfly.org/components/breadcrumb/design-guidelines)) | The device page's header today holds 11 controls (Appendix A). One primary with the rest in an overflow is the convergent answer. |
| Products | NetBox: breadcrumbs, title, a top-right controls block, then tabs. Mist: actions in a top-right "Utilities" drop-down. Meraki: actions in a "Tools" tab. ([NetBox object.html](https://raw.githubusercontent.com/netbox-community/netbox/main/netbox/templates/generic/object.html), [Mist switch](https://www.juniper.net/documentation/us/en/software/mist/mist-wired/topics/concept/switch-dashboard.html)) | |

## 10. What the network products add

- **A "needs attention" view separate from dashboards.**
  - Meraki's Alerts Hub gives category, severity, count, dismiss and time.
  - Mist has Marvis Actions and Alerts.
  - Catalyst ranks Issues P1 to P4, each with its impact and suggested actions.
  - CloudVision has Events.

  NMAS's landing page is already this, with one action per row.
  ([Meraki alerts](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Monitoring_and_Reporting/Organization_Alerts_and_Alert_Hub),
  [Marvis Actions](https://www.juniper.net/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-actions-overview.html))
- **Change review before apply: two of five.**
  - CloudVision reviews a Workspace (with its diff), then a Change Control (review and
    approve, then execute, with snapshots before and after, and a Rollback that is itself
    a change control).
  - Catalyst Center makes a CLI preview mandatory by default: "you cannot deploy your
    device configurations until you review them".

  Meraki and Mist apply on save, and NetBox applies directly unless its Branching plugin is
  installed. NMAS's preview-then-confirm puts it with CloudVision and Catalyst Center.
  ([CloudVision change control](https://labguides.testdrive.arista.com/2025.1/cloudvision_portal/cvp_adv_cc/),
  [Catalyst visibility and control](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/3-2-x/admin-guide/cisco-catalyst-center-admin-guide-3-2-x/manage-system-configurations/t_configure-visibility-and-control.html))
- **An audit trail with the actor and the before and after values.**
  - Meraki's change log records time, admin, page, old value and new value.
  - Mist has audit logs, and Catalyst has Activities > Audit Logs.
  - NetBox's change log keeps pre- and post-change snapshots.

  NMAS's equivalents are git commits with trailers, deploy receipts and the NetBox
  modification record. The Versions destination is where they meet.
  ([Meraki change log](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Design_and_Configure/Organizations_and_Networks/Organization_Menu/Organization_Change_Log),
  [NetBox change logging](https://netboxlabs.com/docs/netbox/features/change-logging/))

## 11. What the sources agree on, and where they differ

**Agreed across all three design systems:**
1. One primary action per page.
2. Never colour alone: a status carries an icon and a word.
3. Secondary actions go into an overflow menu, with few exposed, and destructive ones set
   apart.
4. Bulk actions come from a row selection and appear above the table, away from row
   actions.
5. An empty state explains itself and offers one next action. "Nothing matches" is a
   different state from "nothing yet", and a failure is neither.
6. Single-column forms, validated when a field loses focus, with a server's errors
   summarised above the submit.
7. Irreversible actions escalate to typed confirmation.
8. Critical information is never behind a disclosure or a tooltip, and disclosures are
   never nested.
9. Breadcrumbs show where a page sits.
10. Navigation is shallow: two levels, and tabs in the page for a third.

**Where they differ, for the brief to choose:**
- **Row actions:**
  - Carbon uses an overflow per row (inline when there are fewer than three);
  - PatternFly uses a kebab in the last column;
  - Cloudscape uses selection and header actions.

  NMAS's plan 6a already chose the last: no row actions.
- **Marking required fields:** Cloudscape marks the optional ones, PatternFly marks the
  required ones, and Carbon marks whichever group is the minority.
- **Disabling submit:** Cloudscape never does; PatternFly does until the form is valid.
  NMAS's rule for a refused confirm ("the button states the refusal instead of being
  greyed out", plan section 2) is closer to Cloudscape's.
- **Status and severity:** only PatternFly separates them.
- **Base unit:** Cloudscape 4 px, Carbon 8 px, PatternFly rem steps from 4 px. Bootstrap's
  own scale is 4 px based.
- **Density:** Cloudscape has a global comfortable/compact mode; the other two set density
  per component.
- **Help:** Cloudscape uses a help panel reached by Info links; PatternFly and Carbon use
  popovers or toggletips plus a Help menu.
- **Settings:** all three put it in the top utility area. NMAS's plan makes it a
  destination. The operator's sidebar requirement puts it in the sidebar, which Cloudscape's
  side-navigation example also shows.

**Among the network products,** only Catalyst Center organises its navigation by task and
lifecycle. The rest organise by object type. The plan's rule (tasks, never subsystems) has
one close precedent, not five.

## Appendix A. Today's GUI, measured (2026-09-29)

Read from `templates/` and the scripts they load. Line numbers are as of commit `c27ea7f`.

**Size:**
- **16 top-level tabs:** 11 on the main page and 5 on the device page, plus 4 nested
  topology sub-tabs.
- **About 47 cards or panels on the main page and 9 on the device page**, plus 14 Settings
  sections and 9 integration cards.
- **28 modals:** 13 static on the main page, 1 on the device page, 1 base overlay, and 13
  built in JavaScript.
- **About 140 distinct actions**, not counting the Configure tab's 112 form-type buttons,
  which share one handler.

**Main page tabs:** Devices, Topology, Ansible, History, NetBox, Agent, Approvals,
Monitoring, Configure, Git, Logs. The Device List selector, New List, Delete List and
Settings sit above the tabs.

**Device page tabs:** Utilities, File Management, Terminal, Backups, Changes. The header
holds 11 controls: Restore Golden Config, Restore from…, Capture as golden, Seed intent,
Revert intent…, Retry rolled-back change…, Rotate credential…, Persist…, Retire…, Ask AI,
Back to Devices.

**The device list's row:**
- five buttons: Manage (link), Template preview, Deploy plan, Edit intent, Golden history;
- a checkbox feeding a Bulk Operations card. The card holds a command box, a TFTP server
  field, upload, download, config download, delete file, and restore golden.

**Duplicated functions** (24 groups; each location is the one first measured):

| # | Function | Where it is reachable |
|---|---|---|
| D1 | Capture a golden | Save All, "Capture devices with no golden", the device page's Capture, Approve, Approve All (one component, five entry points) |
| D2 | A device's config read into a store | Device Backups "Backup Config"; the template preview's "Refresh capture" (the same route); bulk config download; the Ansible wizard's backup; an AI suggestion; the `wfAutoBackup` setting |
| D3 | Restore to a golden | Bulk Restore Golden Config; the device page's Restore Golden Config (which navigates to the main page) and Restore from…; Re-apply this baseline; an approval handing off (one component, five entry points) |
| D4 | Version history and compare | The row's Golden history (with Compare); the Git tab's log and diff; the device page's Compare Backups; the History tab; the device page's Changes tab |
| D5 | The remote | The Remote card under the device list; the Git tab's status line; the Settings nsot_git card. Auto-push is both a Settings switch and a Remote card button |
| D6 | Background agent on/off | Settings `#settingsBackgroundAgentEnabled` (persists); Settings `#bgAgentEnabled` (never read or saved); the Agent tab's Pause (in memory only); the AI master switch |
| D7 | Drift check interval | The Approvals tab's drift select; the Agent tab's timers |
| D8 | Playbook list and delete | The Ansible tab; the AI panel's Playbooks drawer |
| D9 | Playbook generation | The Configure tab's Ansible Wizard, apart from the Ansible tab |
| D10 | TFTP server address | Settings; the bulk panel; the device page's Files tab (a second `saveTftpServer` definition) |
| D11 | File upload, download, delete | The device page's Files tab, and the bulk panel (one device against many; two implementations) |
| D12 | Run a command | Utilities' custom command and quick actions; bulk Execute; the Terminal; the AI assistant; the Ansible wizard; SNMP Quick Poll |
| D13 | Open the AI assistant | The navbar; the device page's Ask AI; "Ask AI about selection"; suggestion prompts |
| D14 | NetBox import of the current list | "Import Current List"; the current list's row "Sync" |
| D15 | Permit NetBox writes | The Settings switch; the checkbox in the NetBox safety modal |
| D16 | NetBox connection | The Settings Test Connection; the NetBox tab's badge; the Monitoring tab's NetBox card |
| D17 | Integration health | The status bar; the Settings status strip; the Monitoring Integrations cards; each integration's Test |
| D18 | Topology | The topology service card; "Built-in discovery (legacy)", which its own template calls a second implementation |
| D19 | Collector configuration | Monitoring's OOB Collector IP; the Settings collector switches |
| D20 | Break-glass export | Settings; a Needs attention row; the rotate result's next step (one component, three entry points) |
| D21 | Open Settings | Five buttons and links |
| D22 | Refresh identity | Refresh Hostnames (pending renames), committed separately by "Sync device names to repo"; Refresh from NetBox |
| D23 | Configure form types | `ipv6/dhcpv6` offered twice; "DHCPv6 Server" labelled twice |
| D24 | Intent authoring | The row's Edit intent; the device page's Seed, Revert and Retry (with no Edit intent there); the Configure forms, which send nothing and point at the intent editor |

D1, D3 and D20 already follow plan 6a's rule: several entry points into one component, which
is allowed. The brief decides, for each of the rest, which home it keeps.

**Misplacements measured:**
1. The Remote card sits under the device list; the Git tab also reports remote state.
2. Baselines, the migration card and "Sync device names" are on the Devices tab.
3. The template library sits under the device list, with no destination of its own.
4. `#deployWizard` is an empty element.
5. Pending onboardings are drawn at the bottom of the page, far from "Onboard a device".
6. The inventory-source banner sits below the table it governs.
7. The Ansible Wizard is on the Configure tab.
8. The drift controls are on Approvals, and the drift timer on Agent.
9. Per-device golden history is only on the list row; the device page has capture and
   restore but no history.
10. Retire, Rotate and Persist exist only on the device page, and a note on the list
    page sends people there.
11. Settings' "Jump to NetBox" points at the NetBox tab's heading.
12. The TFTP server is set in three places, and the TFTP root in a fourth.
13. The device page's two Restore controls navigate away to the main page.
14. The device page loads Bootstrap twice.
15. Stale text: "No devices saved yet. Add one below." (Add Device is gone).
16. Two legacy blocks (topology discovery, collectors) are collapsed inside current tabs.
