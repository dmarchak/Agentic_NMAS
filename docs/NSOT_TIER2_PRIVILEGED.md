# Tier 2: "Run a privileged command…" (APPROVED by the operator, 2026-10-08; decisions in section 4; built after the measurements in section 5)

The command policy (NSOT_READS.md section 11, the operator, 2026-10-08) puts the exec commands
that change a device's state recoverably in Tier 2: refused by the reads engine today, naming
this operation, which is drafted here and on the mockup canvas (page "reads", boards T2-A to
T2-D). Nothing is built until it is signed off.

## 1. What it is

One operation, from the device page's Actions menu: **Run a privileged command…**. It runs one
Tier 2 command on one device, through the lifecycle every device-changing operation has
(CLAUDE.md): a preview of what it affects, read from the device; a confirm bound by hash to that
preview, as a verified person, with a reason; the command applied while the device is held;
verify, read back; and a record (a receipt, and History). Rollback does not apply, and the
preview says why: what these commands change, the device rebuilds by itself (counters count
again, ARP relearns, a soft refresh re-sends routes), and nothing can put back what was cleared.
This is the same shape as Persist's "a save cannot be undone".

## 2. The commands (an allowlist; each argument one token of its shape)

| Command | The preview reads (before) | What it affects, said at the confirm | Verify reads (after) |
|---|---|---|---|
| `clear counters [<interface>]` | `show interfaces [<interface>]`, the counter lines | the counters a diagnosis reads are zeroed; they are KEPT in the receipt first | the same counters, near zero |
| `clear arp-cache [interface <interface>]` | `show ip arp [<interface>] \| count Internet` (or the entries, up to the cap) | N entries relearned; traffic to them waits one ARP exchange | the entries return (count, within a settle window) |
| `clear ip bgp <peer> soft [in\|out]` | `show ip bgp neighbors <peer>`: state, uptime, route refresh capability | routes re-sent or re-read; the session is NOT reset (soft); refused when the peer is not Established, or lacks route refresh and has no soft-reconfiguration inbound | the session's uptime did NOT reset, and it is still Established; prefixes received counted again |
| `clear logging` | `show logging \| include messages logged` and the buffer's size | the device's log buffer is emptied; Loki keeps what was sent to it (lines at or under the trap level), the rest is lost; the buffer is KEPT in the receipt first, masked | the buffer's count, near zero |
| `undebug all` | `show debugging` | each debug that is on is turned off; with none on, it **changes nothing**, said at the confirm, and the button says what it still does | `show debugging` is empty |

Anything else is refused as today, naming its tier. Tier 3 stays refused.

## 3. The card (boards T2-A to T2-D)

- **T2-A, choose:** the command picked from the five above (never typed free), its argument
  from the device's own list: an interface from its interfaces, a peer from its BGP
  neighbours. The card reads the preview at once, held for the read only.
- **T2-B, the preview and the confirm:**
  - the before read, masked;
  - what it affects (the table's third column, with this device's numbers);
  - what it will not do (no configuration change, no session reset for soft);
  - rollback: does not apply, and why;
  - a reason, required (one line, recorded);
  - the confirm, bound to the preview's hash. A preview older than the hash's life, or a
    device that changed, is read again and refused, naming both values.
- **T2-C, the result:** applied, verified (the after read beside the before), recorded. A
  verify that fails says what it read: a soft clear that reset the session is drawn red,
  naming both uptimes.
- **T2-D, the case that changes nothing:** `undebug all` with no debug on. "This changes
  nothing: no debug is on." The button reads "Run undebug all anyway (records it)".

## 4. Decisions (APPROVED by the operator, 2026-10-08, with boards T2-A to T2-D and T2 phone)

- **T2-1, one device for now.** A fleet-wide `clear counters` comes later, once measured.
- **T2-2, a reason is required**, three words at least, as a dangerous line's is.
- **T2-3, the agent never RUNS Tier 2.** It may PROPOSE a Tier 2 command in a recommendation,
  for a person to run here (the charter's rule).
- **T2-4, the before-state is kept in the record**, masked and size-capped: the counters
  before `clear counters`, the log buffer before `clear logging` (those commands destroy
  evidence).
- **Order:** the build comes after the measurements in section 5, made as a Mercury probe (no
  terminal steps), after boards C2, F and G are built and after Phase 3's clab sync rewrite.

## 5. Measurements before the build (nothing here has been sent to a device)

- The confirm prompts: `clear counters` asks `Clear "show interface" counters on all
  interfaces [confirm]`, and `clear logging` asks `Clear logging buffer [confirm]`, by common
  knowledge. Each is to be MEASURED on r2 (IOS-XE) and s1 (IOS) before the build: the exact
  prompt, so the operation answers only that prompt (send, read, decide), and refuses anything
  else it sees.
- Whether `clear ip bgp <peer> soft` resets anything on these platforms: the session's uptime
  before and after, on r2.
- How long ARP takes to come back after `clear arp-cache` on a lab segment, which sets verify's
  settle window (about 2.5 times the measured time).
