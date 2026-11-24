# Refresh audit: what a page's own redraw can destroy

Read-only audit of the v2 interface, by reading code (no app or browser run), at 4f2c6c76
(static/js and templates/v2 unchanged since b3ddcc58). The week plan's Stage 5 item: "Auto-refresh
never destroys what a person is looking at". Model of the defect class: C4081 (ccbdeceb), where
the redraw a press's own `X-NMAS-Invalidates` asked for merged its region and removed the answer
the press had just drawn and focused. Every severity below is UNKNOWN until measured; each root
cause names its one measurement.

## Summary

Nine client paths replace DOM without a click (section 1). One of them, the live merge, carries
nearly all live traffic: 121 `nmas:` triggers in 103 templates. It keeps most of what a person is
doing, except in the cases below.

| Mechanism | Count | Focus | Unsent text | Tick or choice | Open details | Modal | Inner scroll | Press answer |
|---|---|---|---|---|---|---|---|---|
| M1 live merge | 121 triggers | kept | kept | kept only if its subtree is untouched | kept | kept | kept, but rows can push it | kept only while focused or held |
| M1 inside a restarted component | 9 region templates with `x-data`, plus parts that gain `load` | lost | lost | lost | lost | lost | lost | lost |
| M2 live redraw of a region with no copy | not counted | id only | held whole | lost | `data-keep` only | held whole | lost | held whole if marked |
| M5 out-of-band parts | 12 | merged if remembered, else replaced | | | | | | |
| M6 timed chart redraw | 2 templates | n/a | n/a | n/a | n/a | n/a | lost (table panels) | chart hover lost |
| M9 own press on a whole region | about 214 controls, 35 region ids | id only | lost outside the press's form | lost | `data-keep` only | lost | lost | (it is the answer) |

What is lost, counted by template exposure (section 3): non-text controls in live regions (30
templates with a select, 20 with a checkbox or radio) have no keep; 47 templates draw a press's
answer (`.set-result`) without `data-holds-live`; 31 templates draw an inner scrolling panel.

## 1. The refresh mechanisms

- **M1, the live merge.** A reader announces keys over the socket (`nmas_invalidation.js:181-189`,
  `:381`), relayed as `nmas:<key>` on `<body>` (`nmas_v2.js:1419-1422`, subscriptions
  `:1790-1861`). Each region re-fetches by its `hx-trigger`. `holdWhileEditing` (`:478-502`) has
  its say, then `mergeLive` (`:1135-1138`) turns innerHTML or outerHTML into the merge's swap.
  `mergeInto` (`:1078-1119`), `morph` (`:829-854`) and `mergeChildren` (`:920-1006`) bring the
  page to the answer by comparing it with the server's previous drawing (`drawnFrom`, `:645`).
- **M3, a re-fetch after another control's post.** The post's `X-NMAS-Invalidates` header is read
  at `htmx:afterRequest` (`nmas_invalidation.js:392-400`) and for `fetch` (`:402-409`), then
  dispatched by the same registry (`:145-155`). From there it is M1 or M2. The same goes for
  catch-up on reconnect (`:196-206`), a key missed while a region was in flight
  (`nmas_v2.js:1447-1455`) and the first-connect catch-up (`:1480-1488`).
- **M4, a released hold.** A 1 s tick (`:2769`) and every `focusout` (`:2827`) run `releaseHeld`
  (`:1296-1305`); `redrawHeld` (`:1262-1292`) asks again by merge (Show it now: whole, by design).
- **M2, a live redraw that cannot merge.** A region the page holds no copy of falls to htmx's own
  swap (`mergeSpec`, `:1124-1134`). So does a swap style other than inner or outerHTML. A region
  drawn inside a body a person loaded into another region is never remembered (`captureSwapped`,
  `:727-731`). Here a hold stops the whole swap (`:488`).
- **M5, out-of-band parts.** `mergeOob` (`:750-770`) merges a remembered part. Outside any region,
  an unequal drawing is htmx's to replace (`:755-760`). There are 12 `hx-swap-oob` uses.
- **M6, timed redraws.** Chart panels re-read every 30 s (`_macros.html:237`;
  `nmas_panels.js:574-586`), and each answer destroys and rebuilds the chart (`draw`, `:477-483`).
  The heal-auto chip re-reads at its expiry by a plain innerHTML swap (`_heal_auto_chip.html:23`).
  The Update panel polls every 2 s while a run is in flight (`nmas_update.js:284`). Text-only ticks
  replace no element with state: ages (`nmas_v2.js:2770`), elapsed counters (`:1324`), stale
  notes (`:1686-1712`), the pushed badge (`:1759-1778`).
- **M7, script re-plans.** A typed deploy reason replaces three parts of the card (`:2002-2004`),
  or, when the program has moved, the whole card through a `change`, a plain swap (`:1999`). A
  drop asks the rollout order again (`nmas_apply.js:383-388`), as does a set-aside drag answer
  (`nmas_drag.js:68-72`).
- **M8, whole-page reloads with no click at that moment:** a page restored from the
  back/forward cache (`nmas_v2.js:2737-2743`); 1.5 s after an update ends (`nmas_update.js:283`);
  an IP SLA outcome (`nmas_apply.js:629`); `HX-Refresh` answers (`routes/settings_v2.py:1057`,
  `:1074`; `routes/device_v2.py:132`).
- **M9, a person's own press whose target is a whole live region.** This is not a live update, so
  there is no hold (`:480`) and no merge (`:1125`). htmx replaces the region, and the answer is
  then captured as the server's drawing (`:725`). Counted by matching `hx-target="#id"` against
  the ids of `nmas:` regions: about 214 controls on 35 ids. Among them are `#device-op` (53),
  `#dhcp` (31), `#topo` (22), `#sdn` (16, plus `HX-Retarget`, `routes/sdn_v2.py:562`) and
  `#cred-profiles` (15).

## 2. What each preserves

Under M1, the merge itself:

- **Focus:** kept. An unchanged node is untouched (`:832`), a focused button is a kept part
  (`pointedAt`, `:462-464`), `giveFocusBack` refocuses by node or id (`:1013-1019`), and `wire`
  keeps htmx's `[autofocus]` settle from taking the focus (`:1057-1063`).
- **Unsent text:** kept. `isEditing` (`:234-249`) counts a focused or changed input of a `TEXTY`
  type (`:232`) or a textarea, and `heldParts` (`:385-399`) keeps its form or component
  (`editUnit`, `:376-380`).
- **A select's choice, or a checkbox or radio:** there is no keep for these. They are not in
  `TEXTY`, and `pointedAt` keeps them only under the pointer (`:442-447`). They survive only
  when their subtree is unchanged, or when `mergeAttrs` (`:787-810`) leaves their dirty state
  alone. They are lost whenever the subtree is replaced (M1's restart, M2, M9).
- **An open `<details>`:** kept. `mergeAttrs` never sets `open` (`:791`, `:802`), an open
  `details[hx-get]` is a kept part (`:392`), and any swap reopens `data-keep` keys (`:519-539`,
  listener `:2780`) and remembered sections (`:559-569`). 10 of 198 `<details>` carry none of
  these; unkeyed, they match by place (`:943-948`), so after a reorder the open mark stays with
  the place.
- **An open modal:** kept. `openModal` marks the dialog `data-holds-live` (`:2597`), which makes it
  a kept part (`:392`). `modalClosed` clears the mark (`:2639`).
- **Scroll inside a panel:** the element is kept, so its `scrollTop` stays. New keyed rows are
  hidden behind "N new" only when they land above the window's top. `landsAbove` and `heldAfter`
  test the window rectangle (`:864-868`, `:469-476`), never the scrolling ancestor, so rows
  inserted above a panel's visible part push it.
- **Rows a person expanded or loaded:** kept as the page's own (`:831`, `:922-924`, Load more `:953-965`); sort order is applied again (`:610-619`).
- **A press's answer shown in place:** kept while focused (`answerRead`, `:409-414`; C4081) or
  marked `data-holds-live` (`:392`). Drawn into a part inside a region, it is the page's own and
  kept (`:729`), possibly stale over a newer state; drawn into the region itself or a
  `data-live-part` (`:714-726`), it is the server's drawing, and the next merge removes it.

The merge's exceptions, where none of the above holds:

- `morph` rebuilds any element with `x-data`, or any part whose new trigger fires on load, from
  the server's drawing whenever the server drew it differently (`:844-849`). The test of
  `ctx.keep` (`:833`) covers only the element itself, not what is inside it.
- `mergeInto` replaces the region whole when the answer is not one element with the same tag and
  id, or the region now starts on load (`:1085-1094`). It never looks at `ctx.keep`.

Under M2 and M9, htmx's swap keeps focus by id only. Under M2 a hold reason (editing, sending,
an open `details[hx-get]`, a reviewed card) keeps the whole region back (`:306-312`, `:488`); M9
has no hold. `data-keep` details, remembered sections and sort order survive. Selects, ticks,
unkeyed open details, inner scroll, Alpine state and other forms' text (M9) are lost. Separate
holds: the Update panel's `data-update-hold` (`nmas_update.js:366-372`) and a drag's
(`nmas_drag.js:1-30`).

Under M6, `draw` destroys the chart and clears its body every 30 s, changed or not, and the hover
read-out and a table panel's scroll go with it (`nmas_panels.js:480-483`).

## 3. Pages and panels exposed

Counts are of templates that hold an `nmas:` trigger, 103 files. Each file is counted once; its
includes are not expanded, so these are floors.

| Group | Count | Exposed to | Examples |
|---|---|---|---|
| Form inside a live region | 61 | text kept; choices and ticks only as in section 2 | DHCP, SDN, Credentials, device op cards |
| Select | 30 | no keep (M1 changed subtree, M2, M9) | filters, mode pickers |
| Checkbox or radio | 20 | no keep; lost on a component restart | Devices `_devices.html:84`, Coverage `_coverage.html:80` |
| `x-data` component inside a region | 9 | restart (`:844`) | Devices selection form `_devices.html:33`, Coverage `_coverage.html:45`, menus on Monitoring (`_fleet.html:14`, `:27`; `_monitoring.html:15`), `_history_remote.html:21`, `:26` |
| `<details>` | 44 | kept (M1); `data-keep` only (M2, M9) | Needs attention, History, Incidents |
| Modal (`_modal.html`) | 3 callers | kept (M1); lost under M9 and restarts | Self-healing, Fix it, heal change |
| Inner scrolling panel (18 overflow rules) | 31 | rows inserted above the reader; lost when replaced | `.att-batch-list`, `.hist-diff`, `.sdn-log`, `.set-log`, `.inc-proof-read` |
| Press answer without `data-holds-live` | 47 of 58 `.set-result` templates | removed by the next merge unless focused | Settings cards, Credentials, Hand over's siblings |
| Whole-page region every press replaces (M9) | 5 pages | everything outside the press's form | DHCP, SDN views, Topology, Credentials profiles, device op card |
| Chart grid on a timer (M6) | 2 | hover, table scroll | `_monitoring.html` and `_fleet.html` through `panel_grid` |

The clearest exposure is the Devices page. Its region (`_devices.html:17-18`) listens for eight
keys, and its selection form is an Alpine component (`:33`) holding every row's checkbox (`:84`).
Any row the server draws differently (a reachability change) makes the form's copy differ, and
`morph` rebuilds the form (`nmas_v2.js:844`). Ticks the server did not draw (`r.checked` comes
from the query) and the head box's indeterminate state are lost. A checkbox is never a kept
part, and the form never is either. Coverage (`_coverage.html:45`) has the same shape.

The page-level test, `tests/test_live_merge.py:446-505`, announces each key without changing what
the server draws (`:472`). So the merge's changed-data paths (restart, fallback, removal of
answers) are exercised only by fragment tests (`:121-260`). One of those asserts the restart
(`:218-233`).

## 4. Root causes, ranked by places one shared fix would cover

1. **A person's own press on a whole region bypasses the merge.** `mergeSpec` requires a live
   trigger (`nmas_v2.js:1125`), and `holdWhileEditing` returns for non-live swaps (`:480`).
   About 214 controls on 35 region ids. Fix once: merge every answer into a remembered region,
   keeping `heldParts` outside the pressed control's own form or card. Measure: on DHCP, type into
   one card's field, press another card's Close, then read the field.
2. **Non-text controls are never "a part a person is working in".** `isEditing` counts only
   `TEXTY` fields (`:232-248`). 30 region templates have a select and 20 a checkbox or radio. Fix
   once: count a control whose `checked` differs from `defaultChecked`, or whose option
   `selected` differs from `defaultSelected`. Measure: as in cause 4, on Devices.
3. **A press's unfocused answer is removed by the next merge.** The answer is captured as the
   server's drawing when its target is the region (`:725`) or a `data-live-part` (`:726`), and
   only focus (`:409-414`) or `data-holds-live` keeps it. That covers 47 templates; C4081 fixed
   the focused case only (its Not-Done names Approve, Modify, Deny and Send again). Fix once: an
   answer drawn by a press is a kept part until the person presses, closes or types in its
   region. Measure: press a Settings card's save, move the focus away, announce `settings` with a
   change.
4. **A component restart ignores what is kept inside it.** `morph`'s restart (`:844-849`) and
   `mergeInto`'s fallback (`:1085-1094`) test `ctx.keep` against the element only. This covers 9
   region templates with `x-data`, plus every part that gains `load`, and every kind of state is
   lost there, including kept text, a modal and focus. Fix once: when `holdsPart(live, ctx)`,
   merge into it, or keep it and revisit it later, instead of rebuilding. This is the most severe
   cause (Devices ticks). Measure: on `/v2/devices`, tick two rows, then announce
   `reachability` with one row changed.
5. **New rows are placed against the window, never the scrolling panel** (`:864-868`,
   `:469-476`). This covers 31 templates. Fix once: use the nearest scrolling ancestor's
   rectangle.
6. **A kept part is not revisited once released.** Its ancestors are recorded as drawn from the
   new answer (`:852`, `:1107`), so an equal later redraw stops above the stale part.
   `answerRevisited` (`:421-434`) fixes this for `.set-result` only. Fix once: run it for every
   kept part (5 kinds in `heldParts`). This is a wrong thing looking right, not a loss.
7. **Chart panels poll and rebuild on a timer** (`nmas_panels.js:581-586`, `:480-483`), against
   "no polling". This covers 2 templates. Fix once: skip `draw` when the answer equals
   `__nmasLast`, or redraw on an announced key.
8. **Holds in four vocabularies**: `data-holds-live`, `data-editing`, `data-update-hold`
   (`nmas_update.js:366`) and `NMAS_DRAG` holds. A page that uses a different one is outside the
   merge's keep. Fix once: one kind in `heldParts`, the others mapped onto it.

## 5. Proposed rule for the contributor docs

- **A refresh never destroys what a person is looking at or doing.** Every swap into a live
  region, a person's own press included, goes through the merge in `static/js/nmas_v2.js`.
- The merge keeps each part a person is working in: the focus, unsent text, a changed tick or
  choice, an open disclosure or modal, an answer not yet left, and an inner panel's scroll.
- The merge never rebuilds an element around a kept part, and draws the part's new state once
  the person leaves it.
- A new kind of hold is a kind in `heldParts`, never an attribute in another script. Nothing
  redraws on a timer unless its answer changed.
- Proven by `tests/test_live_merge.py` with changed server data on every live page.
