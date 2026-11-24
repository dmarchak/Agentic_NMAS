# Research: interface patterns for Mercury (week plan, Stage 3)

This note collects patterns from network-operations products and design systems for four concerns: the AI assistant, dense pages, progress feedback, and minimalism without hiding information.
Every pattern names the products that use it, each with a link, and one line on where it fits in Mercury (device list, device page, incident page, Settings, and a config change's preview → confirm → push → verify → rollback).
The pages were read on 2026-11-23. Where a vendor page could not be fetched and the claim comes from a search engine's summary of it, the entry says "(search summary)". Where no source was found, it says "not found".

## (a) AI assistant integration in an operations product

### a1. A side panel that stays open across pages, with a full-page mode for long work

**Pattern.** The assistant opens from one fixed toolbar control on every page and docks beside the content, not over it. It stays open while the person moves between pages. A separate full-page view holds long investigations and earlier conversations.

**Used by.**
- Grafana Assistant "appears in a sidebar and stays open as you navigate the UI" ([Grafana blog](https://grafana.com/blog/llm-grafana-assistant/)). Its Workspace is a "full-page Assistant experience": the conversation list on the left, the chat in the centre and a canvas on the right for panels and reports ([Grafana Workspace](https://grafana.com/docs/grafana-cloud/machine-learning/assistant/workspace/)).
- Marvis (Mist) opens from an icon in the portal's top-left or bottom-right corner, or with Ctrl+K. Its window docks to the bottom or the right, can be resized, and keeps that place and size across sessions ([Marvis conversational assistant](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-conv-assistant-enhanced.html)).
- Meraki's AI Assistant sits in the dashboard's upper-right corner beside Help, Alerts and the user icon ([Meraki AI Assistant](https://documentation.meraki.com/Platform_Management/Cross-Platform_Content/AI_Assistant_for_Networking)).
- Vercel Agent opens from "Agent" in the dashboard's top-right corner ([Vercel Agent](https://vercel.com/docs/agent)).
- Datadog offers both a full-page Bits Chat and a Bits Chat panel. The page doesn't say where the panel sits ([Bits Chat](https://docs.datadoghq.com/bits_ai/bits_assistant)).
- Microsoft's Copilot UX guidance names three frameworks: immersive (the whole canvas), assistive (a side bar inside the app) and embedded (one entry point on one item). Its rule of thumb is "the more important the task, the more real estate required" ([Microsoft Learn, UX guidance](https://learn.microsoft.com/en-us/microsoft-cloud/dev/copilot/isv/ux-guidance)).
- Atlassian's Rovo patterns offer full-page, sidebar and floating-chat layouts. Full-page is for large outputs (search summary of [Rovo and AI patterns](https://atlassian.design/patterns/rovo-ai)).
- Carbon AI Chat can float as a launcher in the lower-right corner, or render into a container the product chooses, such as a sidebar or a full screen ([Carbon AI Chat](https://chat.carbondesignsystem.com/tag/latest/docs/documents/Overview.html)).

**For Mercury.** One toolbar control would open the assistant panel on every v2 page. htmx swaps only the main region, so the panel survives navigation. An incident's investigation would get an "Open full page" view with the conversation on one side and its evidence on the other.

### a2. Embedded entry points on the object being looked at

**Pattern.** Besides the general panel, specific objects carry their own AI action, and the wording keeps the person as the subject. Microsoft's example is "Summarize with copilot", not "copilot, summarize".

**Used by.**
- Microsoft recommends adding an embedded entry point alongside an immersive or assistive one, for example highlighting code or diving into one chart ([Microsoft Learn, UX guidance](https://learn.microsoft.com/en-us/microsoft-cloud/dev/copilot/isv/ux-guidance)).
- Meraki Table Summarization summarises the change log, login attempts and network events tables, highlighting "key patterns, events, or changes" ([Meraki Table Summarization](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Monitoring_and_Reporting/Table_Summarization_-_Public_Beta)).
- Linear's Triage Intelligence shows suggested properties and possible duplicates inline on the issue. Each can be accepted, declined or explained ([Linear Triage Intelligence](https://linear.app/docs/triage-intelligence)).

**For Mercury.** A Needs attention row, a device's Logs tab and a failed verify step would each carry "Explain with AI". It opens the panel with that object already attached as context, so the person types nothing to describe it.

### a3. Page context is attached automatically, shown, and editable

**Pattern.** When the panel opens, the current page's object becomes the assistant's context. The context is drawn as removable chips above the prompt, so the person can see what the assistant will use and change it.

**Used by.**
- Grafana passes the current view's context when the sidebar opens. "@" or "Add context" adds data sources, dashboards or metrics ([Grafana blog](https://grafana.com/blog/llm-grafana-assistant/)). In the Workspace, "Selected items appear as tags above the prompt", and the prompt area shows context-window usage ([Grafana Workspace](https://grafana.com/docs/grafana-cloud/machine-learning/assistant/workspace/)).
- Meraki "strictly matches its query and response boundaries" to the active Dashboard view. From Global Overview, answers span every organisation the person administers ([Meraki AI Assistant](https://documentation.meraki.com/Platform_Management/Cross-Platform_Content/AI_Assistant_for_Networking)). Deep Reasoning uses the network being viewed unless the prompt names another ([Meraki Deep Reasoning](https://documentation.meraki.com/Platform_Management/AgenticOps_for_Networking/Deep_Reasoning_Mode)).
- Marvis works within the scope the person gives it (a site, client or device) and looks back 24 hours unless told otherwise ([Marvis conversational assistant](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-conv-assistant-enhanced.html)).
- Rovo Chat's content-read skill includes "the current browser URL for Jira work items or Confluence pages" ([Rovo Chat capabilities](https://support.atlassian.com/rovo/docs/chat-actions/)).
- Notion AI takes @-mentions of pages, people and dates, and AI blocks have a "Specified context" setting ([Notion AI FAQ](https://www.notion.com/help/notion-ai-faqs)).
- Vercel Agent "limits each request to the selected team and project context" ([Vercel Agent permissions](https://vercel.com/docs/agent/chat/permissions)).

**For Mercury.** Opening the panel on a device page would attach chips such as "Device: `<device>`", "Last 24 h" and "Row: drift on `<device>`". Each chip can be removed, and the time window shows on its chip. The chips are the whole statement of what the assistant may read.

### a4. The assistant has the viewer's permissions, never more

**Pattern.** The assistant reads and acts only with the permissions of the person asking.

**Used by.**
- Meraki: network-only admins get the same permissions in the assistant as in Dashboard ([Meraki AI Assistant](https://documentation.meraki.com/Platform_Management/Cross-Platform_Content/AI_Assistant_for_Networking)).
- Datadog Bits Chat runs with the person's Datadog role ([Bits Chat](https://docs.datadoghq.com/bits_ai/bits_assistant)).
- Rovo only reads content the person can already view ([Rovo Chat capabilities](https://support.atlassian.com/rovo/docs/chat-actions/)).
- Vercel Agent uses the person's existing Vercel permissions and is "read-only by default" ([Vercel Agent permissions](https://vercel.com/docs/agent/chat/permissions)).

**For Mercury.** The assistant's device reads would go through the same read-only allowlist and the same verified identity as the person's own clicks. Its record would name both the person and the trigger.

### a5. Answers cite their evidence, and "inconclusive" is an allowed answer

**Pattern.** Each claim links to what it came from: a query, a log line, a panel or a document. The link opens that evidence in place. An investigation shows the hypotheses it tested and how each ended, and it may conclude that the data can't decide.

**Used by.**
- Grafana Workspace: inline citations such as "Source 1" open the referenced panel in a Sources view. Investigations add Report, Hypotheses and Sources tabs ([Grafana Workspace](https://grafana.com/docs/grafana-cloud/machine-learning/assistant/workspace/)).
- Datadog Bits Investigation tests hypotheses, which end validated, invalidated or inconclusive. It ends with either an evidence-backed conclusion or "inconclusive". An Investigation Steps view shows its reasoning live, and a Hypothesis Tree view shows the path once it finishes ([Bits Investigation](https://docs.datadoghq.com/bits_ai/bits_investigation/investigate_issues/)).
- Meraki has streamed its reasoning steps since February 2026, and Deep Reasoning returns "structured findings, supporting evidence, and recommended next steps" ([Meraki product updates](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Troubleshooting_and_Support/Support/AI_Assistant_for_Networking_-_Product_Updates)). How Meraki displays citations: not found.
- Marvis: "Certain debug answers include embedded links that open in a new tab" ([Marvis conversational assistant](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-conv-assistant-enhanced.html)).
- Rovo's Search QA returns answers together with the sources used ([Rovo Chat capabilities](https://support.atlassian.com/rovo/docs/chat-actions/)).
- Microsoft recommends citations and direct quotes that take the person to the exact location, and warns that references do not completely stop fabrication ([Microsoft Learn, UX guidance](https://learn.microsoft.com/en-us/microsoft-cloud/dev/copilot/isv/ux-guidance)).
- GitHub Copilot's agent session log shows its reasoning and the tools it used, and each commit message links back to its session log ([Track Copilot sessions](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/track-copilot-sessions)).
- How GitHub Copilot Chat displays references, and how Notion displays citations: not found.

**For Mercury.** An incident answer would list its hypotheses, each marked confirmed, ruled out or can't tell, and each citing the masked command output, syslog line or golden commit behind it. A click opens that evidence one level down. "Can't tell from what was read" would be drawn as a result, never as a failure.

### a6. AI-made content is labelled, and the label opens its explanation

**Pattern.** A small, consistent label marks AI-produced content. Clicking it opens a short explanation of where the content came from. If the person edits the content, the label goes, and the original can be restored.

**Used by.**
- Carbon requires an AI label and an explainability popover on every AI component. The guidance is to "Start with summarized explanations" in the popover and to offer "revert to AI" after a manual edit ([Carbon for AI](https://carbondesignsystem.com/guidelines/carbon-for-ai/)).
- Atlassian: "People should always know when they're interacting with AI" (search summary of [Rovo and AI patterns](https://atlassian.design/patterns/rovo-ai)).
- Microsoft advises against anthropomorphising the copilot and recommends a notice on outputs that they may be wrong ([Microsoft Learn, UX guidance](https://learn.microsoft.com/en-us/microsoft-cloud/dev/copilot/isv/ux-guidance)).
- Linear highlights edits made by its agent "separately so they're easy to review", and version history can restore any checkpoint ([Linear agent-assisted editing](https://linear.app/changelog/2026-07-23-agent-assisted-editing)).

**For Mercury.** An "AI" label on assistant text and on any change it drafted would open a popover naming the model, the trigger (a person or a job), what it read and what the answer cost.

### a7. Cost and model are visible where the assistant is used, and capped

**Pattern.** Each answer or session shows its usage. A usage page breaks spend down by feature and by person. Administrators set caps, and reaching one produces a clear banner. Model choice is visible and controlled by an administrator.

**Used by.**
- Vercel Agent charges by tokens. Chat includes 50 messages per member per day, and approving a plan is charged even with free messages left. A Usage page shows cost per feature over a chosen time range, and each source of automatic usage can be switched off on its own ([Vercel Agent pricing](https://vercel.com/docs/agent/pricing)).
- Datadog AI Credits take organisation, role and per-user caps. At a cap, a banner shows the reset date, and the API returns 429 "AI_CREDITS_EXHAUSTED". Automatic runs roll up to "Autonomous Agents", separate from people. Datadog has no built-in warning before a cap; it suggests a monitor ([Datadog AI credit limits](https://docs.datadoghq.com/account_management/billing/ai_credit_limits/)).
- GitHub Copilot Chat has a model dropdown under the prompt and a retry that regenerates the answer with another model. "Different models consume AI credits at different rates" ([Copilot Chat on GitHub](https://docs.github.com/en/copilot/how-tos/chat-with-copilot/chat-in-github)). A session's overview shows its token usage ([Track Copilot sessions](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/track-copilot-sessions)).
- Notion: administrators choose which models members may pick, high-consumption models stay off until a workspace owner turns them on, and owners can set per-member credit limits ([Notion AI FAQ](https://www.notion.com/help/notion-ai-faqs)).
- Meraki limits AI-generated workflows to 10 per organisation per day, resetting at midnight UTC ([Meraki AI Assistant](https://documentation.meraki.com/Platform_Management/Cross-Platform_Content/AI_Assistant_for_Networking)).

**For Mercury.** This is what Mercury's AI cost rules already require: the toolbar chip, the spend panel and per-feature caps. Two additions would carry over. A small cost line under each answer ("$0.04 · model X") would make spend visible as it happens. Background spend would be shown apart from people's spend, the way Datadog separates "Autonomous Agents".

### a8. A change is handed off as a scoped plan that a person approves, never applied by the assistant

**Pattern.** The assistant reads freely but writes nothing. A change comes back as a plan listing the exact targets and operations. The plan enters the product's normal review path, and only a person approves it. Approval covers exactly that plan. Changing the target produces a new plan. The AI's own approval never counts.

**Used by.**
- Vercel Agent is read-only by default. A change needs plan approval, and "the exact operation and resource are shown in the plan". "Approval applies only to the listed targets, operations, scopes, and risk"; "a new plan requires new approval"; the agent "does not expand an approved plan" and proposes a replacement instead. Approvals are written to the Activity Log with the person's name ([Vercel Agent permissions](https://vercel.com/docs/agent/chat/permissions)).
- Notion's Plan mode writes a plan page (goal, steps, a preview of what will change, and risks to confirm) and makes no edits until the person approves it. The approval settings are "Always ask", "Review for me" and "Skip all approvals", and administrators can turn off the skip (search summary of [Notion plans](https://www.notion.com/help/review-and-approve-plans-before-notion-ai-runs)).
- GitHub Copilot's agent opens a pull request and requests review. Where approvals are required, the requester's own approval of a Copilot pull request "won't count", so a second person must approve. Workflows don't run until someone presses "Approve and run workflows" ([Review Copilot PRs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/review-copilot-prs)).
- In Grafana, an investigation's fix appears in its report. "Review" opens it in Changes to create a pull request, and a conversation waiting for approval carries a shield in the list ([Grafana Workspace](https://grafana.com/docs/grafana-cloud/machine-learning/assistant/workspace/)).
- Meraki: since September 2026, automated workflows show "richer confirmation details before the user approves execution" ([Meraki product updates](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Troubleshooting_and_Support/Support/AI_Assistant_for_Networking_-_Product_Updates)). Deep Reasoning "does not make any configurations to the networks" ([Meraki Deep Reasoning](https://documentation.meraki.com/Platform_Management/AgenticOps_for_Networking/Deep_Reasoning_Mode)).
- Rovo's skills "typically require confirmation from the person who prompted the agent", and deleting needs a further confirmation ([Rovo Chat capabilities](https://support.atlassian.com/rovo/docs/chat-actions/)).
- Marvis Actions has two modes. Driver-assist recommends and the person acts. Self-driving needs a permission that is off by default, granted per organisation or per site, and switchable per action ([Self-driving Marvis Actions](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/self-driving-marvis-actions.html)).
- Microsoft's Copilot app guidance asks for "Explicit confirmations for sensitive operations" and "Transparent outcomes of what was created, modified, or updated" ([Microsoft Learn, MCP apps UI](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-mcp-apps-ui-guidelines)).

**For Mercury.** An AI proposal would end in one button, "Open as a change". It produces Mercury's normal preview: the exact masked program and its hash, confirmed by a verified person in the standard flow. The proposal page would never be the confirm. A follow-up that changes the target device or the commands would make a new proposal with a new hash.

### a9. Feedback on each answer, and a history of answers

**Pattern.** Each answer carries helpful and unhelpful controls with an optional reason. Earlier answers stay reachable, so trying again loses nothing.

**Used by.**
- Meraki: thumbs up and down after an interaction, and for a wrong answer a description of what was expected ([Meraki AI Assistant](https://documentation.meraki.com/Platform_Management/Cross-Platform_Content/AI_Assistant_for_Networking)).
- GitHub: thumbs on Copilot's pull requests and comments ([Review Copilot PRs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/review-copilot-prs)).
- Microsoft: "Keep a history of outputs and prompts" and "Encourage granular feedback" ([Microsoft Learn, UX guidance](https://learn.microsoft.com/en-us/microsoft-cloud/dev/copilot/isv/ux-guidance)).

**For Mercury.** Feedback would sit on each answer in the panel. The incident page would keep every AI answer given for that incident, in time order.

## (b) Dense pages built around what the person came for

### b1. Counts by outcome come first, and each count is a filter

**Pattern.** The page opens with a short row of counts by state, led by the states that need action. Clicking a count filters the list below to that state. The list follows. Charts come after the counts, if at all.

**Used by.**
- The Marvis Actions page has three sections: category counts of open issues (Wireless, Wired, WAN and others), then a time-series chart, then the issues resolved automatically. Clicking a category lists its actions, and a status filter covers Open, In progress, AI Validated, Self Driven and Resolved by User ([Marvis Actions overview](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-actions-overview.html)).
- Each Mist SLE block shows a success percentage, a timeline and the classifiers behind the failures. Every failure is attributed to one classifier, so the shares total 100% ([Mist SLEs](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/service-level-expectations.html)).
- Datadog's Triggered Monitors view lists only monitors in Alert, Warn or No Data, with one row per triggered group, so 14 failing hosts show as 14 rows ([Datadog Manage Monitors](https://docs.datadoghq.com/monitors/manage/)).
- Carbon: a group of statuses takes the colour of its most urgent member, and more than five or six indicators "can overwhelm users" ([Carbon status indicators](https://carbondesignsystem.com/patterns/status-indicator-pattern/)).

**For Mercury.** The device list would open with a strip such as "3 unreachable · 14 drifted · 886 in sync" (of about 900). Each figure would be a filter link, problems first. Healthy devices are a count, never a wall of green rows.

### b2. A table is the default for a fleet, with density chosen deliberately

**Pattern.** A fleet is a table with compact rows, columns the person can choose, a toolbar with search and a few global actions, and a bar for actions on selected rows.

**Used by.**
- Carbon data table: five row heights from 24 to 64 px (40 px by default), header height matching the rows, at most five toolbar actions before an overflow menu, search collapsed behind an icon or always open, a batch-action bar that appears once rows are selected, expandable rows, pagination at the bottom, and optional zebra stripes ([Carbon data table](https://carbondesignsystem.com/components/data-table/usage/)).
- Datadog's Infrastructure List takes columns from attributes, tags or metrics, which can be reordered, resized or hidden. By default it shows only hosts active in the last 15 minutes ([Datadog Infrastructure List](https://docs.datadoghq.com/infrastructure/list/)).
- Meraki's Organization Overview adds and moves columns through a "+" button and filters devices by model, status and description ([Meraki Organization Overview](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Inventory_and_Devices/Organization_Overview)).

**For Mercury.** The device list would be a small-row table (about 32 px) with name, site, role, state, last checked and drift. Optional columns would be chosen per person, and selecting rows would reveal batch actions such as Capture or Check.

### b3. Grouping and collapse, with group headers that stay visible

**Pattern.** The person groups the list by one property and optionally sub-groups it. Group headers carry counts and stay pinned while scrolling. Empty groups are hidden unless asked for. Choosing what each row displays is separate from filtering.

**Used by.**
- Linear's display options group, sub-group and order a list. Headers stay sticky. "Show empty groups" is a toggle. "Display properties" choose the fields shown on each row without filtering anything. Changes apply to one person's view unless "Set as default" applies them to the workspace ([Linear display options](https://linear.app/docs/display-options)).
- Grafana's alert rules list defaults to a grouped view (folder, then evaluation group, then rules) and can switch to a flat list ([Grafana alert rules](https://grafana.com/docs/grafana/latest/alerting/monitor-status/view-alert-rules/)).
- Datadog's Host Map nests groupings, for example by zone and then by instance type, and colours each host cell by a chosen metric ([Datadog Host Map](https://docs.datadoghq.com/infrastructure/hostmap/)).

**For Mercury.** Grouping the device list by site or role would draw collapsed groups headed with counts ("Site A · 120 · 2 drifted"). Groups holding a problem would open by default and the rest would stay closed. Across about 1000 devices, the page stays a few dozen lines tall.

### b4. Filter chips, search across all fields, saved views, and a stated subset

**Pattern.** Filters are chips above the table, each either suggested or active. A "Clear filters" link appears only when a filter is set. Search matches every field. A filter set can be saved as a view. Counts are worked out after filtering, so they describe what is shown.

**Used by.**
- Stripe's filter chips are either suggested ("+") or active (a value with a clear "×"). "Clear filters" shows only when a filter is active. Labels match the column headers. Data is filtered before it reaches the table "to keep pagination and row counts accurate" ([Stripe filter controls](https://docs.stripe.com/stripe-apps/patterns/filter-controls.md)).
- Meraki's search tool "will attempt to match that string across all available fields" (search summary of [Meraki Search Tool](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Inventory_and_Devices/Search_Tool)).
- Grafana's alert search takes `key:value` terms, saved searches, and a default search ([Grafana alert rules](https://grafana.com/docs/grafana/latest/alerting/monitor-status/view-alert-rules/)).
- Datadog saves a filter and column setup as a starred view ([Datadog Infrastructure List](https://docs.datadoghq.com/infrastructure/list/)).
- Vercel filters deployments by branch, date range, environment and status ([Vercel managing deployments](https://vercel.com/docs/deployments/managing-deployments)).

**For Mercury.** Filters would live in the URL, so a view can be bookmarked and shared. The table caption would say "Showing 14 of 903 · filter: drifted · Clear", so the subset always says so.

### b5. Master-detail: a peek at one item without leaving the list

**Pattern.** Selecting a row opens its summary in a side panel or an expanded row, and the list stays in place. The full page is one more click away.

**Used by.**
- Linear's Peek opens an issue preview with the Space bar, and Cmd/Ctrl+K has a similar quick look (search summary of [Linear Peek](https://linear.app/docs/peek)).
- Datadog: clicking a host opens a side panel (the same one the Resource Catalog uses) with tags, metrics, containers and logs ([Datadog Infrastructure List](https://docs.datadoghq.com/infrastructure/list/)).
- Carbon's expandable rows fit "large amounts of data into a small space" ([Carbon data table](https://carbondesignsystem.com/components/data-table/usage/)).

**For Mercury.** Clicking a device row would open a side panel with its state, its open Needs attention rows and its last change, plus "Open device". The device page itself stays the place for the full detail.

## (c) Progress feedback after a click

### c1. Choose the feedback by how long the work takes

**Pattern.** Short waits get no indicator. Medium waits get a spinner on the control. Long waits get a determinate indicator. Anything over about ten seconds becomes a background job the person can leave.

**Used by.**
- Primer: under 1 s, nothing; 1 to 3 s, an indeterminate indicator; 3 to 10 s, a determinate one if possible; over 10 s, a determinate indicator and a background task. The lifecycle has four stages: started, in progress, succeeded and failed, and a failure explains itself and offers a retry ([Primer loading](https://primer.style/product/ui-patterns/loading)).
- Carbon: skeletons "should only appear for only a few seconds". A full-page loader is for when the whole page is processing, and a process that runs for minutes should be paired with a notification ([Carbon loading](https://carbondesignsystem.com/patterns/loading-pattern/)).

**For Mercury.** A check that returns in a second updates in place. A capture or a deploy, which runs past ten seconds, would become a job with its own URL as soon as it is confirmed.

### c2. Busy on the control itself, and the result in its place

**Pattern.** The pressed control shows that it is busy and is disabled until the answer arrives. The answer replaces the control's area. The label changes from "Saving…" to "Saved". The status is a drawn state, never only text, and never a toast in a far corner.

**Used by.**
- Carbon inline loading has inactive, active, finished and error states. It appears where the content was, and controls tied to the action are disabled while it runs. A success shows for 1.5 s before an optional callback runs. The label should change with the state ([Carbon inline loading](https://carbondesignsystem.com/components/inline-loading/usage/)).
- htmx puts the `htmx-request` class on the element that made the request by default ([htmx hx-indicator](https://htmx.org/attributes/hx-indicator/)). `hx-disabled-elt` disables elements "for the duration of the request" ([htmx hx-disabled-elt](https://htmx.org/attributes/hx-disabled-elt/)).
- Stripe's Button takes a `pending` prop rather than a hand-placed spinner (search summary of [Stripe loading](https://docs.stripe.com/stripe-apps/patterns/loading)).
- Primer puts an InlineMessage "near the action they are related to" and steers away from toasts, toward banners, inline messages or dialogs ([Primer notification messaging](https://primer.style/product/ui-patterns/notification-messaging)).
- Microsoft: widgets show loading, disabled, success and error-with-recovery states, and should "Never rely on model text alone to communicate system status" ([Microsoft Learn, MCP apps UI](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-mcp-apps-ui-guidelines)).

**For Mercury.** This matches Mercury's existing busy-on-itself rule and its no-toast rule. htmx's built-in request class and `hx-disabled-elt` cover the mechanics without new script.

### c3. Optimistic for local state only; device state shown as sent, then as verified

**Pattern.** An optimistic update shows the expected result at once and falls back if the action fails. That suits low-stakes local state. Where the outcome is uncertain, products show two separate states: done, then confirmed by a later check.

**Used by.**
- React's `useOptimistic` renders the optimistic value only "while an Action is in progress". If the action throws, the person sees "what it showed before the optimistic update" ([React useOptimistic](https://react.dev/reference/react/useOptimistic)).
- Marvis self-driving actions move to "HPE Marvis Self Driven" when the fix is applied, then to "AI Validated" if the issue doesn't come back within the validation period. If it does come back, the action reopens ([Self-driving Marvis Actions](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/self-driving-marvis-actions.html)).
- Vercel runs a rollback or promotion as a background job, one per project at a time. A second request gets `409 Conflict`. The job's status reads pending, in-progress, succeeded, failed or skipped ([Vercel Instant Rollback](https://vercel.com/docs/instant-rollback)).
- Optimistic UI in Linear: no vendor documentation found.

**For Mercury.** Collapsing a group or dismissing a hint can be optimistic. A device change would never be drawn as done until it is verified: "Sent" (grey) and "Verified" (green) are separate states, and a recurrence reopens the row.

### c4. A vertical stepper for a known, linear flow

**Pattern.** A fixed sequence of three or more steps is drawn as a stepper, each step complete, current, not started or failed. Vertical reads best. Steps that vary with conditions are not a stepper.

**Used by.**
- Carbon's progress indicator has completed, current, not started, error and disabled states. It is for linear processes of three or more steps, not for steps that vary "based on conditional logic", and "When possible, arrange the progress indicator vertically" ([Carbon progress indicator](https://carbondesignsystem.com/components/progress-indicator/usage/)).
- Arista's CloudVision workflow module lists workspace states (pending, built, submitted, abandoned, deleted) and change-control states (pending approval, approved, running, completed) ([Arista AVD cv_workflow](https://avd.arista.com/5.4/docs/plugins/Modules_and_action_plugins/cv_workflow.html)). In the GUI, the Review and Approve dialog shows the configuration differences. After approval, the button becomes Execute Change Control, and Unapprove reverts the approval (search summary of [CloudVision change control](https://arista.com/cg-cv/cv-using-the-change-control-module); the page refused automated fetch).

**For Mercury.** A config change page would draw Preview → Confirm → Push → Verify as a vertical stepper. A failed verify marks that step red and adds a Rollback step with its own state, rather than hiding the failure.

### c5. A step log with expandable, linkable steps, the failed step opened

**Pattern.** Under the stepper, each step's output can be expanded. The failed step opens on its own. Lines can be linked and searched. Each step shows its duration. A batch shows one row per target with its status icon.

**Used by.**
- GitHub Actions splits each job's log into steps: "Any failed steps are automatically expanded to display the results". It offers log search, a link to any line and per-step durations ([Actions run logs](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs)). Its run graph updates live, with a status icon per job and lines for dependencies (search summary of [Actions visualization graph](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-the-visualization-graph)).
- Vercel's build logs colour warnings yellow and errors red. Clicking a timestamp links to the line (`#L6`, or `#L6-L9` for a range). Logs are kept indefinitely, and secret values are replaced with `[REDACTED]` ([Vercel build logs](https://vercel.com/docs/deployments/logs)).
- Datadog shows an investigation's steps live, then as a tree once it finishes ([Bits Investigation](https://docs.datadoghq.com/bits_ai/bits_investigation/investigate_issues/)).
- GitHub's PR checks have statuses (queued, in_progress, completed) and conclusions (success, failure, timed_out, action_required and others). Failures and action-required conclusions call for review before merging ([About status checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks)).

**For Mercury.** A push to 40 devices would show "38 verified · 1 rolled back · 1 unreachable", then one collapsed row per device. A failed device's row would open on its own, showing the masked device output with line anchors that can be pasted into a record.

### c6. A job outlives the page and can be found again

**Pattern.** Long work runs on the server. Leaving the page doesn't stop it. A list of running jobs can be reached from any page, and returning to the object shows the job's current step. A resubmitted request is recognised, not run twice.

**Used by.**
- GitHub Copilot agent sessions keep running after the laptop closes. A sessions list in the agents panel can be reached from any page, and "Stop session" keeps the commits already pushed ([Track Copilot sessions](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/track-copilot-sessions)).
- Primer shows long-running progress in a Banner that a success or error message later replaces. If people can leave mid-action, it recommends the notification system ([Primer notification messaging](https://primer.style/product/ui-patterns/notification-messaging)).
- Carbon pairs a process that runs for minutes with a notification ([Carbon loading](https://carbondesignsystem.com/patterns/loading-pattern/)).
- In Grafana, a conversation that waits for approval shows a shield in the list ([Grafana Workspace](https://grafana.com/docs/grafana-cloud/machine-learning/assistant/workspace/)).
- Stripe idempotency keys let a client "safely repeat the request without risk of creating a second object or performing the update twice". A reused key with different parameters is an error ([Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests)).

**For Mercury.** Every operation would have a job URL. The toolbar would show "1 running", opening the list of running jobs. Returning to a device page would show "Deploy running: Verify, step 4 of 5". A second confirm with the same hash would return the running job, not start a second one.

### c7. Rollback is a previewed action that says what it will and won't undo

**Pattern.** Undo is not a silent button. It previews what will be restored, states what it can't restore, takes a confirm, and leaves a visible record of the rolled-back state.

**Used by.**
- Vercel Instant Rollback opens a dialog with the current deployment and the eligible ones. The person checks the domains affected, the fact that environment variables won't change, and a reminder about external APIs and databases, then presses Confirm Rollback. Afterwards the production tile highlights the rolled-back commits, and auto-assignment stays off until the rollback is undone ([Vercel Instant Rollback](https://vercel.com/docs/instant-rollback)).
- CloudVision runs a change inside configuration sessions, which gives a state to revert to (search summary of the [CloudVision lab guide](https://labguides.testdrive.arista.com/2025.1/data_center/cvp_adv_cc_studio/); the page returned 404 when fetched).
- Linear restores "to any previous checkpoint from version history" ([Linear agent-assisted editing](https://linear.app/changelog/2026-07-23-agent-assisted-editing)).

**For Mercury.** Rollback would be drawn per device ("restores 6 lines on `<device>`; the BGP session reset it caused is not undone"). Afterwards the device page would carry a "Rolled back" state, linked to the receipt, until the next change.

## (d) Minimalism without hiding information

### d1. The answer is on the surface, and disclosure is for supplements only

**Pattern.** Information needed to decide or act is always visible. Disclosure (show more, toggles, popovers) is used sparingly, opened only by the person, one at a time, never nested, and labelled with text beside the icon.

**Used by.**
- Primer uses progressive disclosure "sparingly, only when it's necessary to truncate information". It avoids moving the person's focus and pairs the chevron with text such as "Show more" ([Primer progressive disclosure](https://primer.style/product/ui-patterns/progressive-disclosure)).
- Carbon: don't hide critical information or required input in a disclosure, keep key information at a higher level, open only one disclosure at a time, and never nest them ([Carbon disclosures](https://carbondesignsystem.com/patterns/disclosures-pattern/)).
- Microsoft: "Progressive complexity: Start lightweight. Expand only when needed" and "Show summaries, not systems" ([Microsoft Learn, MCP apps UI](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-mcp-apps-ui-guidelines)).

**For Mercury.** The incident page's first screen would answer three questions in plain lines: what is wrong, what Mercury is doing, and what the person must decide. Timelines, raw output and history sit below, collapsed, each with a labelled chevron.

### d2. Evidence one level down: summary, then cause, then affected items

**Pattern.** Every summary number or verdict opens to the evidence behind it: a breakdown by cause, then the affected items, then the raw data and the query that produced it.

**Used by.**
- Mist SLEs go from a success rate to classifiers. Clicking an SLE or classifier opens Root Cause Analysis with sub-classifiers, distributions and an Affected Items tab with a filter box ([Mist SLEs](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/service-level-expectations.html)).
- Grafana's panel inspector has Data (the raw results), Stats (query duration and volume), Query (the requests sent) and JSON tabs. An Errors tab appears only when there is an error or notice ([Grafana panel inspector](https://grafana.com/docs/grafana/latest/panels-visualizations/panel-inspector/)).
- Marvis Actions' "View More Details" shows the port, client and VLAN behind an action, and the list exports to CSV ([Self-driving Marvis Actions](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/self-driving-marvis-actions.html)).

**For Mercury.** A Needs attention row would open "Why" to the check that raised it: the command, the masked output, and what it was compared with. A verify verdict would open the before and after reads. The inspector's errors-only tab suits Mercury's "Couldn't load" detail.

### d3. Hover for provenance, click for anything interactive or essential

**Pattern.** A tooltip on hover or focus carries short, non-essential context: where a value came from, when it was read, and why a suggestion appeared. Anything interactive, or anything needed to finish a task, opens on click or stays on the page.

**Used by.**
- Carbon's tooltip is for "brief, supplemental information that is not interactive", "contextual, helpful, and nonessential". The toggletip opens on click and can hold controls. Neither holds critical information ([Carbon toggletip](https://carbondesignsystem.com/components/toggletip/usage/)).
- Linear Triage Intelligence: "Hover over the suggestion to see why it's appearing" ([Linear Triage Intelligence](https://linear.app/docs/triage-intelligence)).
- Datadog's Host Map shows a tooltip, such as average CPU, when a host cell is hovered ([Datadog Host Map](https://docs.datadoghq.com/infrastructure/hostmap/)).
- Carbon's AI explainability popover opens from the AI label ([Carbon for AI](https://carbondesignsystem.com/guidelines/carbon-for-ai/)).

**For Mercury.** A value's source and age ("from NetBox, read 20 s ago") would show on hover, as Mercury's rule already says. A stale value would show its age on the page itself, because then the age is decision information.

### d4. Empty, no match, unreadable and loading are four different states

**Pattern.** "Nothing exists", "nothing matches your filter", "it couldn't be read" and "still loading" are drawn differently and worded differently. Each names its next step. An unreadable source is never drawn as empty.

**Used by.**
- Stripe renders "loading first, then error if the fetch failed, then empty if the result set is empty, then content". It doesn't offer to create a first item when items exist but are filtered out: "No customers match your filters" goes with Clear filters. An empty section within a page gets a compact block with a dashed border ([Stripe empty state](https://docs.stripe.com/stripe-apps/patterns/empty-state.md)).
- Carbon's empty states come in three kinds: no data, after a person's action, and error management (no permission, a failing related system, configuration required, action not supported). The empty state replaces the table and its headers, so screen readers don't read an empty structure ([Carbon empty states](https://carbondesignsystem.com/patterns/empty-states-pattern/)).
- Primer's error empty state uses an alert icon and names the problem, for example "Repositories could not be loaded due to a system error" ([Primer empty states](https://primer.style/product/ui-patterns/empty-states)).

**For Mercury.** A device's Logs tab would say one of four things: "No log lines in the last hour" (empty), "No lines match 'BGP'" with Clear (no match), "Couldn't read Loki: not answering; last good read 4 min ago" (unreadable), or "Waiting for Loki, started 40 s ago" (loading or the start grace).

### d5. Degrade one section, never the whole page, and never imply data loss

**Pattern.** When a secondary source fails, the page still draws everything else. The failed section says what is unavailable. Counts that depend on the missing data are hidden rather than shown as zero. Outage messages are few.

**Used by.**
- Primer's degraded experiences: show an error page only when the primary content can't be provided. Replace missing inline content with a short warning, and a larger area with a Blankslate. "Don't try to conceal or downplay that something is wrong". Don't use generic empty states for content people created. Hide counts and badges whose data is unavailable. Keep a page's outage messages to "5 or less" ([Primer degraded experiences](https://primer.style/product/ui-patterns/degraded-experiences)).

**For Mercury.** If Grafana is down, only the device page's Monitoring tab would say so. The Needs attention badge would hide its count rather than show "0" while its source is unreadable, and a separate row would name the unreadable source.

### d6. Status is a shape, an icon and a word as well as a colour

**Pattern.** A status combines colour with a shape or icon and a text label. Indicators appear only where they call for action, and there are few of them.

**Used by.**
- Carbon: "Relying solely on color to convey status is insufficient". Use shape, symbol, colour and a label, avoid indicators when no action is needed, and more than five or six can overwhelm ([Carbon status indicators](https://carbondesignsystem.com/patterns/status-indicator-pattern/)).
- GitHub's check conclusions include separate partial and blocking outcomes (neutral, skipped, timed_out, action_required), and a skipped job reports "Success" ([About status checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks)).

**For Mercury.** State pills would read "✓ Verified", "◐ Partly verified" and "✕ Rolled back", and a partial result would never be green. Fully healthy rows carry no pill at all, so the pills mark the exceptions.

### d7. Not found, for the record

- Fluent 2: the site has no AI- or Copilot-specific guidance pages ([Fluent 2](https://fluent2.microsoft.design/)). Microsoft's Copilot guidance lives on Microsoft Learn instead (cited above), which points to Fluent 2 components.
- Arista AVA's assistant interface: not found in pages that could be fetched. Arista's product brief and CloudVision guide pages refused automated fetch.
- How Datadog Bits Chat uses the current page as context: not found ([Bits Chat](https://docs.datadoghq.com/bits_ai/bits_assistant)).
- Row density settings in Linear: not found ([Linear display options](https://linear.app/docs/display-options)).
- Summary counts on Meraki's Organization Overview: not found ([Meraki Organization Overview](https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Inventory_and_Devices/Organization_Overview)).

## Patterns to carry into proposals

1. One assistant panel opened from the toolbar on every v2 page, staying open across navigation, with a full-page view for an incident's investigation (Grafana, Marvis, Microsoft "assistive").
2. Context attached automatically from the page and drawn as removable chips above the prompt (Grafana tags, Meraki view scoping).
3. "Explain with AI" on the object itself (a Needs attention row, a log view, a failed verify), never a blank prompt (Meraki Table Summarization, Microsoft "embedded").
4. Every AI claim cites the masked output, log line or commit it rests on; hypotheses end confirmed, ruled out or can't tell (Datadog Bits Investigation, Grafana Sources).
5. An AI change becomes a normal Mercury preview with its hash, confirmed by a person; the proposal is never the confirm, and a changed target is a new proposal (Vercel Agent plans, GitHub's "approval won't count", Notion Plan mode).
6. AI content carries a label whose popover names the model, the trigger, the inputs and the cost; each answer shows its own cost, and background spend is shown apart from people's (Carbon AI label, Vercel Usage, Datadog "Autonomous Agents").
7. Fleet pages lead with counts by outcome, problems first, each count a filter link; healthy is a number, not rows (Marvis Actions, Mist SLE classifiers).
8. The device list is a compact table with chosen columns, collapsible groups with counts and sticky headers, and problem groups open by default (Carbon data table, Linear display options, Grafana grouped view).
9. Filters as chips that live in the URL, with "Showing N of M · Clear" whenever a subset is drawn; counts come after filtering (Stripe filter controls).
10. A row click opens a peek panel; the full page is one more click (Linear Peek, Datadog host panel).
11. Feedback by duration: nothing under 1 s, busy on the control up to about 10 s, a job with its own URL beyond that (Primer loading, Carbon loading).
12. A vertical stepper Preview → Confirm → Push → Verify (→ Rollback), with one collapsed row per device and the failed one open, line-linkable and masked (Carbon progress indicator, GitHub Actions logs, Vercel build logs).
13. "Sent" and "Verified" are separate states; nothing device-side is optimistic; a recurrence reopens the row (Marvis Self Driven → AI Validated).
14. Jobs outlive the page: a "running" indicator in the toolbar, the current step shown on the device page, and a repeated confirm returns the running job (Copilot sessions, Primer banners, Stripe idempotency).
15. Empty, no match, unreadable and waiting are four worded states; a failed source degrades only its own section and hides its counts rather than showing zero (Stripe empty state, Carbon empty states, Primer degraded experiences).

## Sources

AI assistants and agents
- Meraki, AI Assistant for Networking: https://documentation.meraki.com/Platform_Management/Cross-Platform_Content/AI_Assistant_for_Networking
- Meraki, AI Assistant product updates: https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Troubleshooting_and_Support/Support/AI_Assistant_for_Networking_-_Product_Updates
- Meraki, Deep Reasoning Mode: https://documentation.meraki.com/Platform_Management/AgenticOps_for_Networking/Deep_Reasoning_Mode
- Meraki, Table Summarization: https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Monitoring_and_Reporting/Table_Summarization_-_Public_Beta
- HPE Mist, Marvis conversational assistant: https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-conv-assistant-enhanced.html
- HPE Mist, Marvis Actions overview: https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-actions-overview.html
- HPE Mist, Self-driving Marvis Actions: https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/self-driving-marvis-actions.html
- Datadog, Bits Chat: https://docs.datadoghq.com/bits_ai/bits_assistant
- Datadog, Bits Investigation: https://docs.datadoghq.com/bits_ai/bits_investigation/investigate_issues/
- Datadog, AI credit limits: https://docs.datadoghq.com/account_management/billing/ai_credit_limits/
- Grafana, Introducing Grafana Assistant: https://grafana.com/blog/llm-grafana-assistant/
- Grafana, Assistant Workspace: https://grafana.com/docs/grafana-cloud/machine-learning/assistant/workspace/
- GitHub, Copilot Chat on GitHub: https://docs.github.com/en/copilot/how-tos/chat-with-copilot/chat-in-github
- GitHub, Review Copilot pull requests: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/review-copilot-prs
- GitHub, Track Copilot sessions: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/track-copilot-sessions
- Vercel, Vercel Agent: https://vercel.com/docs/agent
- Vercel, Vercel Agent permissions: https://vercel.com/docs/agent/chat/permissions
- Vercel, Vercel Agent pricing: https://vercel.com/docs/agent/pricing
- Linear, Triage Intelligence: https://linear.app/docs/triage-intelligence
- Linear, Agent-assisted editing (changelog): https://linear.app/changelog/2026-07-23-agent-assisted-editing
- Atlassian, Rovo Chat capabilities: https://support.atlassian.com/rovo/docs/chat-actions/
- Atlassian Design, Rovo and AI patterns (search summary): https://atlassian.design/patterns/rovo-ai
- Notion, Notion AI FAQ: https://www.notion.com/help/notion-ai-faqs
- Notion, Review and approve plans (search summary): https://www.notion.com/help/review-and-approve-plans-before-notion-ai-runs
- Microsoft Learn, UX guidance for generative AI applications: https://learn.microsoft.com/en-us/microsoft-cloud/dev/copilot/isv/ux-guidance
- Microsoft Learn, UX guidelines for MCP apps in Microsoft 365 Copilot: https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-mcp-apps-ui-guidelines
- Microsoft, Fluent 2 (no AI guidance found): https://fluent2.microsoft.design/
- IBM Carbon, Carbon for AI: https://carbondesignsystem.com/guidelines/carbon-for-ai/
- IBM Carbon, Carbon AI Chat: https://chat.carbondesignsystem.com/tag/latest/docs/documents/Overview.html

Dense pages and fleets
- Mist, Service Level Expectations: https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/service-level-expectations.html
- Meraki, Organization Overview: https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Inventory_and_Devices/Organization_Overview
- Meraki, Search Tool (search summary): https://documentation.meraki.com/Platform_Management/Dashboard_Administration/Operate_and_Maintain/Inventory_and_Devices/Search_Tool
- Datadog, Infrastructure List: https://docs.datadoghq.com/infrastructure/list/
- Datadog, Host Map: https://docs.datadoghq.com/infrastructure/hostmap/
- Datadog, Manage Monitors: https://docs.datadoghq.com/monitors/manage/
- Grafana, View alert rules: https://grafana.com/docs/grafana/latest/alerting/monitor-status/view-alert-rules/
- Linear, Display options: https://linear.app/docs/display-options
- Linear, Peek preview (search summary): https://linear.app/docs/peek
- Stripe, Filter controls: https://docs.stripe.com/stripe-apps/patterns/filter-controls.md
- Vercel, Managing deployments: https://vercel.com/docs/deployments/managing-deployments
- IBM Carbon, Data table: https://carbondesignsystem.com/components/data-table/usage/
- IBM Carbon, Status indicators: https://carbondesignsystem.com/patterns/status-indicator-pattern/

Progress and long-running work
- GitHub, Workflow run logs: https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs
- GitHub, Visualization graph (search summary): https://docs.github.com/en/actions/how-tos/monitor-workflows/use-the-visualization-graph
- GitHub, About status checks: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks
- Vercel, Instant Rollback: https://vercel.com/docs/instant-rollback
- Vercel, Build logs: https://vercel.com/docs/deployments/logs
- Arista, AVD cv_workflow module: https://avd.arista.com/5.4/docs/plugins/Modules_and_action_plugins/cv_workflow.html
- Arista, CloudVision change control module (search summary; refused fetch): https://arista.com/cg-cv/cv-using-the-change-control-module
- Arista, CloudVision change control lab guide (search summary; 404 on fetch): https://labguides.testdrive.arista.com/2025.1/data_center/cvp_adv_cc_studio/
- Stripe, Loading (search summary): https://docs.stripe.com/stripe-apps/patterns/loading
- Stripe, Idempotent requests: https://docs.stripe.com/api/idempotent_requests
- IBM Carbon, Loading: https://carbondesignsystem.com/patterns/loading-pattern/
- IBM Carbon, Inline loading: https://carbondesignsystem.com/components/inline-loading/usage/
- IBM Carbon, Progress indicator: https://carbondesignsystem.com/components/progress-indicator/usage/
- GitHub Primer, Loading: https://primer.style/product/ui-patterns/loading
- GitHub Primer, Notification messaging: https://primer.style/product/ui-patterns/notification-messaging
- htmx, hx-indicator: https://htmx.org/attributes/hx-indicator/
- htmx, hx-disabled-elt: https://htmx.org/attributes/hx-disabled-elt/
- React, useOptimistic: https://react.dev/reference/react/useOptimistic

Minimalism and states
- GitHub Primer, Progressive disclosure: https://primer.style/product/ui-patterns/progressive-disclosure
- GitHub Primer, Degraded experiences: https://primer.style/product/ui-patterns/degraded-experiences
- GitHub Primer, Empty states: https://primer.style/product/ui-patterns/empty-states
- Stripe, Empty state: https://docs.stripe.com/stripe-apps/patterns/empty-state.md
- IBM Carbon, Empty states: https://carbondesignsystem.com/patterns/empty-states-pattern/
- IBM Carbon, Disclosures: https://carbondesignsystem.com/patterns/disclosures-pattern/
- IBM Carbon, Toggletip and tooltip: https://carbondesignsystem.com/components/toggletip/usage/
- Grafana, Panel inspector: https://grafana.com/docs/grafana/latest/panels-visualizations/panel-inspector/
