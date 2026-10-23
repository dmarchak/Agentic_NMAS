# Fidelity: the one-decision out-of-band onboarding's card and a console run's page

The ONE review card (board B), the running card and the result (board C), and a console run's
own page (board C), as built, compared region by region with the boards of
`docs/boards/oob-onboarding.html`, drawn and counted as signed off by the agent under the
Phase 7 mode (2026-10-23, docs/STANDING_APPROVAL_LOG.md). Compared by the templates against the
boards and by tests/test_oob_onboard_v2.py (the review, the confirm's stepper, the result and
the page, each drawn on the fake console's run), not from shots: no shot test is written for
this page yet (its first real run on the lab is its walk). There is no phone board; the card is
the console card's layout (`op-card`, `op-part`), which reflows at phone width.
Compared 2026-10-23.
Templates compared: templates/v2/oob_run.html, templates/v2/_oob_onboard.html
Templates sha256: `3b0eccc8c9b6c41943916f13ceae2586b712badc08dc4dd5f1733d9b8f61b4be`
Hash rewritten 2026-10-23 at the Phase B merge: the run page's links name their network as `?list=` (they said `?list_name=`), and the run page's Devices link takes the page's network; no drawn text, region or control moved, every verdict stands.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Review: the head (B) | "Out-of-band onboarding of edge1" and a chip "ready to confirm", How does this work? | the same; "refused" in red when a check fails | **same** |
| Review: the checks (B's note) | refused, the card leads with its checks, each named with both values, and draws no confirm | the same: each check by its part (the Planned record, the planned address, the relay, the uplink, the console path, the port's record, Create's plan, the role) | **same** |
| Review: the asked uplink (B's note) | "Uplink: the port on edge1 that reaches the relay (relay1 GigabitEthernet3)" with Review again | the same, with NetBox's reason above it | **same** |
| Review: Device (B) | the device, Planned in NetBox with its id kept in the plan and the manifest; role and platform; the profile and its whole sha256 | the same | **same** |
| Review: Console (B) | the path, how it is reached, the host key's type and whole fingerprint and when it was kept | the same; "none held: the first contact keeps the key …" when none is, and "this driver speaks no SSH" for a raw console | **same** |
| Review: Address (static) (B) | each value with where it came from under it; the MAC read from the device; where the bootstrap is copied from | the same, the responder's gate in words under the server | **same** |
| Review: Creates, in order (B) | four lines, the last "no Kea subnet, reservation or MAC rule; nothing in NetBox until Verify" | the same, and Create's plan's fingerprint under them | **same** |
| Review: the console program (B) | every line filled: the wake, the preludes by state, the reads, the blank check again, the lines, the read-backs, the copy | the same, one line each in send order; a line not read back (`vlan 1`) said under it | **same** |
| Review: stops and will not (B) | the stop rules on one line; four things it will not do | a list each | **same** |
| Review: the one button (B) | Reason, "Onboard edge1 through its console", Change the fields, the binding said | the same; How does this work? beside the button | **same** |
| Running: THE stepper (C) | Preview and Confirm done, each step with its time, Answering's "waiting for edge1's SSH key to settle, until 14:32:07 UTC" | the one stepper (`run_stepper`), the same steps and words, filled on each step | **same** |
| Running: leaving (C, C1595) | "Safe to leave this page: the run continues." prominent, with "Open edge1's page – the run continues" (or this run's page before Create) | the same | **same** |
| Result (C) | the chip ("onboarded, answering: ready to Verify"), what happened, the MAC, the copy's answer, "Open edge1's page to Verify" | the same, with the bytes written, what was sent and the transcript behind disclosures, and the record's line (who, how verified, the reason, when, the run) | **same** |
| The page (C) | "Devices / edge1", "edge1" and a chip "console run", the card under it | the same, a sub-line saying the page can close; a survey's or kick-start's run draws its own card here; a device with none says so with Open Devices | **same** |
