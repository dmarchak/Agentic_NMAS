# Friction log

**Why it exists** (the operator, 2026-10-20): as Mercury grows it is getting harder to use, and
ease of use is a product requirement, not polish. Every time a walk, a rehearsal or the
operator's feedback hits friction, one line goes here: the date, the screen or action, what
happened, and the cost (a retry, a near miss, a wasted step).

The full usability review reads this log; it is scheduled after Lab 9 (11-04) and before
Core 1.0's sign-off (C1438, K67). Until that review, logged friction is not fixed unless it
blocks a lab or is a safety issue (the operator's rule). Where a line has a register row, the
row is named. A fix that ships closes nothing here; the review decides each line.

| Date | Screen or action | What happened | Cost | Register |
|---|---|---|---|---|
| 2026-10-20 | Device › Intent (editing r4 Gi5, Lab 8 step 4) | One decision ("Gi5 up, addressed, in area 10") took 8 hand edits in two sections of the YAML | 8 edits and two sections to find, for one intent | docs/INTENT_AUTHORING_DESIGN.md |
| 2026-10-20 | Device › Intent (r4 Gi5) | Contradictory flags (`shutdown` beside `no_shutdown`, `no_ip_address` beside an address) passed the checks | two traps, found by reading the plan | C1429 (fixed) |
| 2026-10-20 | Device › Intent | No search and no jump to a section in a long document | scrolling for each edit | C1428 |
| 2026-10-20 | Device › Intent's preview against Plan a deploy | The editor said 7 lines and "shutdown stays"; the plan sent 8 with ` no shutdown` | a contradiction to resolve before confirming | C1426 (waits on C1432) |
| 2026-10-20 | Device › Intent (s3, `static_routes`) | Two look-alike route lines; the one to the manager was deleted by hand instead of the stale one | a near miss, put back 3.5 minutes later | C1430 |
| 2026-10-20 | Deploy › Left on the device (Mode B, s3, step 4b) | A removal took a reason on its tick and a second one through a declaration | two reasons for one removal | C1434 |
| 2026-10-20 | Deploy › Confirm (s3, step 4b) | Confirm was enabled before the removal's authorisation existed; the apply then refused, naming neither the line nor the control | a refused confirm and a retry | C1434 |
| 2026-10-20 | DHCP › Add a subnet (step 5.1) | Preview silently did nothing without a pool | a blocked step, a log read to find why | C1436 (fixed) |
| 2026-10-20 | Add device (r6, step 5.3) | Gateway is marked "(optional)" but is refused empty behind a relay | a refusal for a field labelled optional | C1439 |
| 2026-10-20 | Add device (r6, step 5.3) | Gateway and Route option (3) ask for the same fact | the same address typed or chosen twice | C1439 |
| 2026-10-20 | Add device › the bootstrap (r6, step 5.3) | Gi2's description says "manager is on this subnet" on a relayed device | a description that is wrong on the device | C1440 |
| 2026-10-20 | Add device › the result (r6, step 5.3) | The reserve step read "(aa:bb:cc:00:04:06 -> ?)" while the row said "awaiting DHCP (10.255.4.2)"; Kea held the reservation complete | a doubt about the reservation, a read to settle it | C1441 |
| 2026-10-20 | Device page left open across Verify (r6, step 5) | It kept "Pending onboarding: pending" after Verify promoted r6 | a stale page that looked current | C1443 |
| 2026-10-20 | Device page header (r6, step 5) | "Onboarded 2 h ago" for a device created minutes earlier | a wrong age, a doubt | C1443 |
| 2026-10-20 | Onboarding row (r6, step 5) | "fetched its config 12 times" in 6 s, each a reveal-audit record | a question whether something looped | C1444 |
| 2026-10-20 | Step 5b, C1432's measurement on R6 | Not possible cleanly through Mercury: no Mode B shape for a helper, an IPv6 address or a virtual interface, and C1432 itself hides an extra NTP server from Mode B | a planned measurement skipped | C1432 |
| 2026-10-20 | Device page left open across Retire (r6, step 1) | The open page did not switch to the retired view; a reload did | a stale page that looked live | C1418 (fixed) |
