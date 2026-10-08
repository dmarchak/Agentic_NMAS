# Tier 2: "Run a privileged command…" (APPROVED 2026-10-08; BUILT the same day from the measurements in section 5, except the soft BGP refresh)

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

## 5. Measurements before the build (made 2026-10-08 on r2 and s1; the soft BGP refresh not yet)

**The probe is BUILT (2026-10-08): `scripts/nmas-tier2-probe`, the operator's to run.** It holds
the device, reads each step's before-state (kept, masked, capped), sends the command once,
answers exactly `[confirm]` with Enter and stops on any other question (unanswered, the session
closed), reads the after-state, watches ARP come back, and compares the BGP peer's Up/Down. It
refuses the hypervisor's backup window and the interface carrying the management address, and
measures a live BGP soft refresh only with `--allow-live-bgp`. The run, on one device of each
platform (the lab's rule: r2 for IOS-XE, s1 for IOS, never s3), outside 08:30 to 09:10 UTC:

    scripts/nmas-tier2-probe --list Default --device r2 --apply --actor <operator> \
        --interface <a data interface> --arp-interface GigabitEthernet3 --out /dev/shm/tier2-r2.json

The dry run (no `--apply`) prints the plan and connects nothing; `--step` limits a run to the
steps named.

**MEASURED 2026-10-08** (the operator ran it on r2 at 17:42 and s1 at 17:43 UTC; the reads are
in `tests/fixtures/operational/`, its README's "Tier 2 probe" section):

| Step | r2 (IOS-XE) | s1 (IOS) |
|---|---|---|
| `clear counters <interface>` | asks `Clear "show interface" counters on this interface [confirm]`; after Enter the counters read 0 and `Last clearing of "show interface" counters` reads `00:00:05` (was `never`) | the same prompt; `00:00:02` |
| `clear arp-cache interface <i>` (Gi3; Vlan20) | asks nothing; 2 of 2 entries back at the first read (0 s at one-second resolution) | asks nothing; 3 of 3 back, 0 s |
| `clear logging` | asks `Clear logging buffer [confirm]`; the buffer is EMPTY after (nothing after `Log Buffer (… bytes):`); `messages logged` is NOT reset (4596 after) | the same prompt and outcome |
| `undebug all` | asks nothing; prints `All possible debugging has been turned off`; `show debugging` with nothing on prints IOS-XE's conditional-debug headers | the same answer; `show debugging` prints nothing |
| `clear ip bgp <peer> soft` | NOT MEASURED (`--allow-live-bgp` not given) | NOT MEASURED |

Two things the run showed about the probe itself:
- **C583:** the first version cleared counters on Loopback0 by default. In this lab that interface
  carries the management address, while the docstring said the probe never used the
  management interface. Harmless for counters, and a loopback's counters barely move. Fixed:
  `--interface` names a data interface, there is no default, and the management interface is
  refused for every step that names one.
- `--step` was added, so the BGP measurement runs alone. r4's peers, from its committed golden:
  198.51.100.3 (IPv4, AS 65002) and 2001:DB8:51:1::2 (IPv6). Its dry run sends exactly
  `clear ip bgp 198.51.100.3 soft` and reads `show ip bgp summary` before and after; the
  operator decides whether to run it:

      scripts/nmas-tier2-probe --list Default --device r4 --apply --actor <operator> \
          --step bgp-soft --allow-live-bgp --bgp-peer 198.51.100.3 --out /dev/shm/tier2-r4.json

**What the build takes from it:**
- the two prompts, answered with Enter only when the device's last line is exactly one of
  them;
- counters verified by `Last clearing of "show interface" counters` reading under a minute;
- logging verified by an empty buffer, never by `messages logged`;
- ARP verified at the first read (0 s measured), polled up to 3 s (about 2.5 times the
  probe's one-second resolution);
- `undebug all` saying "changes nothing" only when `show debugging` is EXACTLY a measured
  nothing-on form (s1's empty, r2's headers), and otherwise just running;
- `clear ip bgp <peer> soft` refused, "not measured", until r4's run.

The three questions this section began with (2026-10-08, before the run): the exact prompts
(measured above, and `clear counters <interface>` asks about "this interface", not "all
interfaces" as written from memory here); whether a soft refresh resets anything (r4's run);
how long ARP takes to return (measured, 0 s).
