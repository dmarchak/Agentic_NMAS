# Fidelity: Credentials › The break-glass record (board 7)

The break-glass record's page as built, compared region by region with its approved board, after
the operator's walk W1 (2026-10-16, step 38: the record "not current" after s1's rotation, the
export built, verified and downloaded intact; C539). Read from shots of the boards and the page
side by side, in the same headless Firefox (`tests/test_board_shots.py::test_credentials`), on
test_breakglass_export's lab (a real key, two devices' credentials, the real export, check, drill
and record format): a real export, drilled by the CLI's own `nmas-breakglass drill` and its
receipt recorded, its download recorded intact; then r1 rotated and job health's read after the
export judging the record stale (the board's "not current"). The page at rest; the export opened
(A, `open=export`); the kept file checked (C, the export's own file posted as the form posts it,
r1 rotated since); and the export's result (B, the browser's word on the download posted as the
page posts it). Read beside them: the operator's W1 captures 32 (the export card before the
passphrase was typed, nine devices) and 33 (Default's record, Downloaded intact, the offline
drill's card under it), at about half desktop width.

Boards: `DevBreakglassExport.dc.html` (board 7, 1440 wide) on the NMAS v2 mockups canvas, page
"Device actions on v2", signed off 2026-10-03 (its placement on Credentials the same day, the card
that night's revision), sections A to D each compared below. `BreakglassRestore.dc.html` (board 20,
1440 wide, the same canvas page, approved 2026-10-05): restore from a break-glass record when the
store is lost, and a device refusing its stored credential. It is not built on this page: the
record's card has no third action, and no route restores from a record or tries a record's
credential on a device (NSOT_STAGE7_PLAN section 20); its regions are **later**. The Profiles tab
was drawn under the Phase 7 mode with no board file (docs/STANDING_APPROVAL_LOG.md, "Board:
Credentials › Profiles"), so it has no comparison here; only its tab beside the record's is in a
region below.
Shots: the boards at 1440; the page at rest at 1440, 1280 and 390 (and its first screen); the
export, the check and the result at 1440 and 390. Compared 2026-10-16.
Templates compared: templates/v2/credentials.html, templates/v2/_breakglass_record.html, templates/v2/_breakglass_export.html, templates/v2/_breakglass_check.html, templates/v2/_breakglass_done.html, templates/v2/_breakglass_drill.html, templates/v2/_credential_read_account.html
Templates sha256: `c9e8425914944fbe2c463ab3841bbce5b1fa2748033e10176a9cd0b4f4347126`

**Compared again 2026-11-13 (the read-only account through intent, C2657):** by the template's
diff against the regions below, not from new shots. In `_credential_read_account.html`, the
**On the devices** value alone changes its words: it named the intent route as waiting on a
measurement, and now names the `users` entry it is (`read-account:profile:<profile>`, an
account added, never changed, deployed by a person), still "not read yet"; the same element in
the same position, no region added, removed or moved. Every verdict stands.
Templates sha256 before: `80e5913eeebd6ad52195fefb7c5c03c7ed0d0facdff6b6721c7194866add65ef`.

**Compared again 2026-11-11 (board E2a, display names):** by the templates' diff against the
regions below, not from new shots. In `_breakglass_record.html`, `_breakglass_done.html`,
`_breakglass_drill.html` and `_credential_read_account.html`, each place that draws a person
(who exported, checked or drilled, who set the read-only account) now draws them through the
`people` filter, by display name (the name the person set, else the part of their identity
before the "@"), in the same element and position; no region is added, removed or moved, and no
other word changes. Where the board draws an identity the built screen draws the name, a
deviation logged once for every screen (log: Display names: a person is drawn by display name
on every screen). Every other verdict stands.
Templates sha256 before: `4cf8d5aded5ffe96b1d64a610b0e492727e8fbce3e4ce3288570513e942cbbfa`.

Compared again 2026-10-17 (C1023) after Check it (`_breakglass_check.html`) and Record the drill
(`_breakglass_drill.html`) declared themselves busy (`hx-disabled-elt="this"`): their busy words
were already in the templates and never shown, because each is a form's submit button. At rest
the page draws the same words; the busy words show only while the request is out. Compared by
the template and the page the tests draw (tests/test_v2_busy_on_itself.py), not a new shot; no
region's verdict changed.

**Compared again 2026-11-07 (board H, artboard N; H28):** `credentials.html` draws the
Read-only account card (`_credential_read_account.html`) under Credential profiles, on the
Profiles tab only; the break-glass record's tab renders as before, so every verdict above
stands. The card is compared with artboard N's left half (docs/boards/heal-to-intent.html,
approved by the operator 2026-11-03) from tests/test_board_shots.py's
`test_read_account_and_ai_classes` (`read-account` and `read-account-form`, at 1440, 1280 and
390: Default's read-only account set by a person, a role profile without one, the form open on
Set), in the regions whose names begin "N:" below.

**Compared again 2026-11-07 (the operator's walk of the card):** the coverage line counts every
network's devices, a local inventory's too ("Of the N devices the networks hold (a NetBox
inventory's as last loaded, a local inventory's as its devices file lists them)", and that a
local inventory's devices take their read-only account from the profiles); it had counted
NetBox inventories only, so Default's local devices drew "0 devices". The form's labels sit by
their own fields: its heading took the label column and moved "Account name" beside it and
"Password" beside the name field; the stylesheet now spans a form's heading, paragraph and
notice across both columns. Read from `test_read_account_and_ai_classes`' `read-account` and
`read-account-form` shots at 1440, 1280 and 390 beside artboard N: at 1280 the heading spans
the form, "Account name" beside its field and "Password" beside the password field, the
coverage line in place above the table; at 390 each label above its own field. N: The coverage
chip keeps its deviation (the count now covers local inventories, the same log line); every
other verdict stands. Held by tests/test_credentials_profiles_in_a_browser.py (each label by
its own field, at 1280 and 390) and tests/test_read_only_account.py (the count).

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | Credentials under SOURCE OF TRUTH, current | the same, current on this page | **same** |
| Breadcrumb | "Source of truth / Credentials" | none: the sidebar names the place, as on every v2 sidebar page | **deviation** (log: Credentials: no breadcrumb on a sidebar page) |
| Header | "Credentials", the (i), "Lab: the record that holds every device's credential and the key, and how to recover with it." | the same ("Default: the record that holds every device's …", capture 33) | **same** |
| Tabs | The break-glass record alone; the note says the credential list and expiries join as tabs | The break-glass record and Profiles (capture 33) | **deviation** (log: Board: Credentials › Profiles) |
| The record's card | the list's name, the state chip in danger, Export the record… (primary) with its (i), Check a break-glass file… with its (i) | the same; the card's border and chip follow the state (current, not current, not intact, none exported, not judged yet, unknown); redrawn at once when an export, its intact check or a drill is logged (P7-05) | **same** |
| Why | the device the record cannot recover, rotated since | the same words from job health's judgement, with when it judged ("The record cannot recover s1: rotated since it was exported", pasted at the walk's step 38) | **same** |
| The drill on the record's card | "Last done 23 Aug; due in 49 days (D below)" | not on the record's card: the drill's own card below carries its due date | **deviation** (log: Credentials: the drill's due date on its own card only) |
| Last export | named inside Why only | its own part: when, by whom, the device count, the key, the sha256, and the browser's word (downloaded intact, not intact, or not reported) | **deviation** (log: Credentials: the record's card names its last export) |
| Every way in | the rotation's result, Needs attention's row and Settings each open this page | compared by the templates they live in, held by tests/test_credentials_v2.py::TestEveryWayInOpensItHere (not shot); the walk came in from Needs attention's row (step 34) | **same** |
| A: What | the sentence, and "Why now: r3's rotation replaced a credential your last record holds" | the sentence, and the preview's summary ("Export Default's break-glass record to this browser, sealed with your passphrase", capture 32), though the record is not current | **deviation** (log: Credentials: the export does not say why now or what changed since the last record (a defect, register C650 follow-up)) |
| A: What will not happen | no device contacted; the passphrase never kept; no copy on the host | the preview contract's four items, saying the same (capture 32) | **same** |
| A: What it will hold | devices named, the key's fingerprint and "opens 31 of 31 stored values", "Since the last record: 1 credential changed" | a line per device (name, address, platform, an enable secret marked), the list, the device count, the key's fingerprint, "Key opens 52 of 52 stored value(s)", the credentials hash (capture 32); nothing since the last record | **deviation** (log: Credentials: the export does not say why now or what changed since the last record (a defect, register C650 follow-up)) |
| A: Checks | three, each pass | six from the preview contract: two pass, four "at confirm" (the passphrase twice, the credentials unchanged, the record opens and verifies, the reveal recorded; capture 32) | **deviation** (log: Credentials: the export's checks are the preview contract's) |
| A: Passphrase | Passphrase and Again, the hint | the same, the hint adding that it is never stored, logged or sent back | **same** |
| A: Confirm | a primary button naming what stops it ("The two passphrases differ"), "Bound to this preview" | the button names what stops it, drawn in danger ("The passphrase needs 12 characters or more", capture 32); the note adds what the file holds, who confirms and the preview's hash | **deviation** (log: Credentials: the export's confirm is drawn in danger) |
| B: The result's head | "Lab's record", Downloaded intact, How does this work?, Close | the same ("Default's record", Downloaded intact, capture 33) | **same** |
| B: What happened | the file, its devices and key, who and when; "Downloaded intact" with the sha256; Not intact in danger | the same (capture 33); Not intact and Not checked each drawn in danger, the export not counted as current (both rendered by tests/test_credentials_v2.py) | **same** |
| B: What next, Recorded, Still true | Check a break-glass file…; the reveal and the export recorded; the row clears, the drill separate | the same (capture 33); Still true says the host never sees where the file goes, the drill's card being beside | **same** |
| C: Check a break-glass file | Choose file…, its passphrase, the hint, Check it | the file, its passphrase, the hint, Check it (busy on itself) over "Nothing on a device or in the stores changes" (the form compared by its template; filled and sent by tests/test_credentials_v2.py's real browser) | **same** |
| C: The verdict | "1 of 9 not current", the file opened, a table of device and credential with the current ones in one row, the key, "This copy cannot recover r3. Export the record again…" | the same, the opened file its own part, r1 not current with why | **same** |
| D: The offline drill | the chip (due in N days), Last done, To do it with the file's name in the command and Copy, the receipt and Record the drill with its (i), When overdue | the same parts (capture 33: "due in 77 days"); the command takes `<the .bg file you kept>`, and the newest export's name is said beside it as it was downloaded (C387: the host never sees what the file is called where it is kept) | **deviation** (log: Credentials: the drill's command names no file) |
| D: after an export | the drill's card names the newest export | the drill's card is not redrawn when an export is logged: after the walk's export it still named the export of two days before as the newest (capture 33), until the page was read again | **deviation** (log: Credentials: the drill card names the previous export until the page is reloaded (a defect, register C650 follow-up)) |
| Restore (board 20, A to D) | Restore from a break-glass record… on the card when the store cannot be read; the file and passphrase; the preview against the goldens; the result | not built: no control, no route | **later** NSOT_STAGE7_PLAN section 20 (recover from a break-glass record in the app) |
| A device refusing its credential (board 20, E) | the device's refusal row offering the record's credential, tried read-only, then adopted and rotated | not built, and drawn on the device page, not this one | **later** NSOT_STAGE7_PLAN section 20, situation 2 |
| Phone | no phone board; the board's parts stack below 700 px | at 390 the header's actions wrap under the title, each part's label above its text, the drill's command wraps | **same** |
| N: Where it is | Credentials, a profile's card | the Profiles tab, under Credential profiles and Scheduled rotation | **same** |
| N: The card | one profile's card, "Credentials · profile default", its accounts as a list | one Read-only account card, a row per profile in the resolver's order | **deviation** (log: Board H built: the read-only account is one card over every profile) |
| N: Deploy account | admin · password set 2 Nov, never shown · used by device-changing operations | the deploy account's name, "used by device-changing operations" on hover; its password's date in Credential profiles' table above | **deviation** (log: Board H built: the read-only account is one card over every profile) |
| N: Read-only account | mercury-ro · password set 3 Nov by operator@example.com, never shown | the same words from the store: the name, when set and by whom, never shown | **same** |
| N: The coverage chip | on 11 of 11 devices | Resolves for N devices per row, a line counting the devices that resolve one and those that do not, and a closed group naming the latter | **deviation** (log: Board H built: the read-only account's coverage says what resolves, not what devices hold) |
| N: What it may run | the AI read set's show commands and bounded ping and traceroute, at a low privilege level | the same, saying its device-side shape is measured on an IOS and an IOS-XE device first | **same** |
| N: Used by | the AI analysis's reads (required); diagnosis, collection and drift reads may move to it later | the same | **same** |
| N: The actions | Set the read-only account…, Replace its password…, Which devices hold it | Set or Replace on each row by state, the form in place; "On the devices: not read yet" in place of the link | **deviation** (log: Board H built: Set and Replace are one control per row, by state) |
| N: The callout | added as an intent change, deployed by a person; the operator types the password; a device without one refused, naming it; retirement removes it | the same facts under the card and in "On the devices"; Needs attention names no such device yet | **later** (the device-side intent and its Needs attention row, once the account's shape is measured on the devices) |
| N: How does this work? | beside the card's head | the same, and compact beside each action, opening Credentials › The read-only account | **same** |
| N: Phone | no phone board | at 390 the table scrolls sideways inside its card, as Credential profiles' does; the form stacks its labels above its fields | **same** |
