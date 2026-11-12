# Mercury's UI rules

Every v2 screen follows these rules. The complete GUI review the operator queued on 2026-11-11
(it starts once every Lab 10 feature is verified on the host) researches established practice
and rewrites this file into the full rule set, each rule marked enforceable by a test or not,
with the tests it proposes. Until then this file holds the rules already in force: the operator
said on 2026-11-11 that every new UI follows them before the review, and added more on
2026-11-12.

Each rule says where it is held: a test, or `[not mechanised]` when only this file holds it.

## Pages wait on nothing

**No page load or badge poll waits on Grafana, Loki, NetBox, a device or a computation:
every page draws at once from data the background already holds, shows each source's age
("checked 20 s ago"), and updates itself while open; there is no refresh button** (the
operator, 2026-11-12; C3166: Needs attention's badge queued from 1.6 s to 26 s during a heal,
and a device's Logs tab waited 5 to 15 s on Loki). Each source refreshes on its own cadence,
fast while viewed or alerting and slowly while idle; an event recomputes only the sources it
touches, debounced, so a heal's step announcements cause one recompute; a fix made through
Mercury still clears its row within seconds. **Display only:** the held values draw pages; the
heal pipeline (detect, decide, guards, apply, verify, can't-fix), deploys and their before and
after reads always read live. Cost: one background refresh per source, and the CPU and memory
it adds on the host, stated. Prevents: a page as slow as its slowest source, a request storm
whenever a heal announces, and a decision made on a page's stale copy.
[the routes that still wait, named and only shrinking, every other GET route calling out
nothing: tests/test_no_page_waits.py; display only: tests/test_attention_display_only.py;
Needs attention's background store, its cadence and its one recompute per burst:
tests/test_attention_store.py]

What it means on a screen, as slice 1 built it for Needs attention:

- The value drawn is the one the background holds (modules/attention_store.py); before the
  first one lands the screen says "Reading …", busy, and fills itself when it does.
- Every value says its age: the list says when it was checked and how old its oldest source's
  read is, and What was checked has a Checked column, one age per source.
- A refresh that fails keeps the last good value and says so, on its source's line and in the
  summary; a source past its own promise is a Needs attention row of its own.
- The sidebar's count is pushed over the page's live connection when it moves; after the page
  loads it is asked for again only on that page's own acknowledgement, which the background
  has already taken into account (a person's own press is drawn at once).

## In force now, before the review (the operator, 2026-11-11)

Each is `[not mechanised]` until the review proposes its test.

- **One primary action** per card or page.
- **Menus hold items and short reasons**, never paragraphs.
- **A status notice is a banner**, not menu text (the held-device banner, not a line inside
  the Actions menu).
- **A card's text stops at a stated length**, and more goes to its page (the collapsed
  last-run line).
- **Each fact appears once** on a screen (a failure is said once).
- **Tables never scroll inside a card.**
- **A stepper uses labels of 2 to 4 words** (the short stepper labels; never a sentence in a
  stepper column).
- **One main area per page.**
- **No secrets or emails on screen** (a person is named by display name; an identity is held
  only in a collapsed record, board E2a).
- **One time zone per screen:** local time, with UTC on hover (the operator, 2026-11-11, on the
  run card: "The card mixes "20:01 UTC" with steps in MST").

## Rules added 2026-11-12 (the operator)

Each is `[not mechanised]` until the review proposes its test (for the first, the review's
proposal: an action's response draws inside a dialog anchored to it, focus inside, Escape
closes).

- **An action does not open a second card or menu elsewhere on the page.** If a confirm step
  is justified (a preview, a reason, a hash, as for any change Mercury makes on its own), it
  opens as a MODAL over the page, anchored to the action, with focus moved into it, and closed
  by Cancel or Escape. Never a card appearing somewhere else on the page.
- **Self-healing:** the Fix kinds table's Heal / Dry run only toggle IS the control; pressing
  it opens that modal (what this changes, reason, Confirm). The mode is a dropdown (Off / Dry
  run / Auto) opening the same modal (C3158).
- **A time limit is never a typed UTC string** ("Auto until"): quick choices (1 h, 2 h, 4 h,
  8 h, 24 h, 7 days) plus a date-time picker in local time, showing the UTC beside it.
- **Every "…" button in Mercury is reviewed for the modal rule**, and listed with its fix (the
  review's section 3).
