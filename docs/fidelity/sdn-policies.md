# Fidelity: SDN › Policies (2026-11-10)

Board: `docs/boards/lab9-sdn.html` artboard E (1440), self-signed under the Phase 7 mode
2026-11-10 (docs/STANDING_APPROVAL_LOG.md, "Board lab9-sdn E (SDN › Policies, Lab 9 B2)").
Board S9 (SdnPolicies), which artboard E says holds the tab, the compiled flows and the effect
in words, is not in docs/boards: the preview is SDN › Flows' operation card (boards SdnResponse
and SdnFlowEdit, docs/fidelity/sdn.md). Its yellow dashed notes are the board's annotations.

**Compared from the templates and their rendering, not from shots.** tests/test_board_shots.py
has no case for this tab yet, so the regions below were read from the built templates and the
HTML tests/test_sdn_policies_v2.py's Lab 9 world renders (the NSOT export with end hosts and the
protected DNS and DHCP Services, Ryu's captured topology, FakeRyu behind the real Ryu driver)
and tests/v2_context.py's `_sdn_policies` provider (every answer state, the preview and its
result, the committed list), beside the board's HTML. A shot at 1440, 1280 and 390 is the next
step of this record.

Templates compared: templates/v2/sdn_policies.html, templates/v2/_sdn_policies.html, templates/v2/_sdn_policy_answer.html, templates/v2/_sdn_op.html, templates/v2/_sdn_tabs.html
Templates sha256: `44de5b7ad9a63298de43ea7b7eabd7734d1dfb568cf865f02df56b8358d835c0`

**Compared again 2026-11-11 (board E2a, display names):** by the template's diff against the
regions below, not from new shots. In `_sdn_policies.html`, the policies table's "by" column
now draws the person through the `people` filter, by display name (the name the person set,
else the part of their identity before the "@"), in the same cell; no region is added, removed
or moved, and no other word changes. Where the board draws an identity the built screen draws
the name, a deviation logged once for every screen (log: Display names: a person is drawn by
display name on every screen). Every other verdict stands.
Hashed again 2026-11-10: the answer card draws Was this right? under an AI-drafted policy (the
shared control every AI answer carries; none under an answer Mercury gave in code).
Hashed again 2026-11-11 ~07:5x UTC for C2944 (History › Export read 0 protected-flow refusals
with refusals made): a refusal by a protected flow gains one small line inside its notice,
under "Nothing was sent.": "This refusal is recorded in History, as you: the policy asked and
each protected flow that refused it.", History a link to the network's SDN rows; or, when the
record could not be written, "This refusal could not be recorded: <why>.". `_sdn_op.html`
gains the same line under a preview or a confirm the protected set refused (its words in
docs/fidelity/sdn.md). Every other answer, the checked policy, Mercury's question and every
other refusal draw exactly as before; the region row "Refused by a protected flow" keeps its
verdict, and this line is not on the board. Compared by
reading the templates, with no new shot; the state is drawn by tests/test_sdn_refusals.py
(the templates before hashed
`81b6b0f3113f1385439001d83816385b8caa5fee91cf61317bbfa230137da7f2`). Its line in
docs/STANDING_APPROVAL_LOG.md: "Boards SdnFlowEdit, SdnResponse and lab9-sdn E built for
C2944".
Hashed again 2026-11-11 ~08:3x UTC, C2944 again (the record is a verified person's): the line
has a third form, drawn for a check again or a preview pressed by someone who is no verified
person, a plain small line and never a warning: "This refusal is not recorded: a refusal's
record is made for a verified person, and this request is not one. Sign in, and a refusal like
this one is recorded in History." The refusal itself reads as it did; `_sdn_op.html` draws the
same words under its own refusal (docs/fidelity/sdn.md). Compared by reading the templates,
with no new shot; the state is drawn by tests/test_sdn_refusals.py's `TestWhoIsRecorded` (the
templates before hashed `53a714066f063b0a7b4d51f6796053bdec23404e9d402cf8a08c15ffc35b4cae`).

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Page head | "SDN (i)" | "SDN · Policies (i)" and the tab's sub-line, as every SDN tab is built | **same** (SDN's one page head, log: Board lab9-sdn A built, 9) |
| Tabs | Controllers, Switches, Flows, Apps, Protected, Policies (on), Responses | Controllers, Switches, Flows, Apps, Policies (on), Responses (`_sdn_tabs.html`) | **later** (Protected is an artboard of its own, not built) |
| Describe a policy | the words box, Draft the policy (AI), "Haiku 5.5 (this network's economy tier) · about $0.001", How does this work? | the same box and button with its AI mark (its hover the task, model and cap), busy on itself; "Claude Haiku 5.5 (the economy tier) · at most $0.0015 a call" and the committed export's short hash; How does this work?; disabled with the reason when hosted AI cannot answer | **deviation** (log: Board lab9-sdn E built, 1) |
| Checked against NetBox and the network | Hosts named, Where it applies, Conflicts with installed flows, Committed policies, Protected flows; "Checked. Preview the flows…" | the same five rows in the same order, each name's resolution, the switch's platform and placement; the policy's rules above; "Checked. Nothing has been sent." with Preview the flows… | **deviation** (log: Board lab9-sdn E built, 2) |
| Which h1? | "isolate h1": two hosts named h1, a button each and Neither, "asked before any AI call" | "Which db?": the stem of db-1 and db-2 (or a host and a tag), Draft with <host> each and Neither, "asked before any AI call", the AI mark | **deviation** (log: Board lab9-sdn E built, 3) |
| Impossible | a rate limit at a switch with no meters, the capability matrix linked, "Compared: the action rate-limit against of-eos-1's features", Drop instead…, Rate-limit at ovs-1 instead… | the same words and both offers (each checked again in code, no call), the meter features read from the controller now, no matrix link | **deviation** (log: Board lab9-sdn E built, 4) |
| Contradictory | the two parts named, "the second part blocks what the first allows", "Compared: the two parts' matches; the allow lies inside the block. Say which should win, or ask again." | the same, each part in words and both matches named; also against a committed policy, naming it | **same** |
| Unknown host | "block h9": "NetBox holds no host h9 and the controller has not seen one. Compared: the name against 14 NetBox hosts and 12 controller-learned hosts." | the same sentence, the network's own counts | **same** |
| Refused by a protected flow | the classes covered named with their source, "Compared: the policy's match against 4 protected flows; 2 covered", a narrowing | the same, each class with its invariant and NetBox source, and a narrowing the schema can state | **deviation** (log: Board lab9-sdn E built, 5) |
| The callout | "The model returns a structured policy only (…); names resolve in code; every check above is code. Its answer never reaches a switch unchecked." | the same sentence under the words box | **deviation** (log: Board lab9-sdn E built, 6) |
| Committed policies | not drawn (board S9) | a card: each policy's id, words, rules, switch, flows, who and when; withdrawn on SDN › Flows | **deviation** (log: Board lab9-sdn E built, 6) |
| The preview | "board S9's preview: the flows, the REST bodies, the effect in words, confirm by hash" | SDN › Flows' card headed "Policy <id>: <words> on <DPID>": What it does, Exactly these requests, What will not happen, Verify, Send bound to the hash; its result in place | **deviation** (log: Board lab9-sdn E built, 7) |
| Phone width | not drawn | the cards stack as every SDN tab's do; not shot | **later** (the record's shot) |
