# Recovery ZTP: a managed device that boots blank

**Status:** design, not built; not for Lab 8 (the operator, 2026-10-21). Sized below and
placed in the build order at the end. CORE: a device whose configuration is lost while Mercury
holds its committed golden and intent is the case the source of truth exists for
(MERCURY_CHARTER).

## 1. What Mercury does today (read in the code, 2026-10-21)

The case: a device onboarded by ZTP and promoted (r6: a manifest entry with `verified_at`, a
NetBox record, a committed golden and intent) reboots with its startup configuration lost
(`write erase` and a reload, a corrupted flash, or a replaced box). It boots configless,
asks DHCP, then asks TFTP for its boot file. Its SSH account is gone with its configuration.

| Part | What it does today | Where |
|---|---|---|
| Kea reservation | **Still there.** Promotion never touches Kea; only Abandon (refused for a promoted device) and Retire remove it. The device is offered its reserved address, its hostname (option 12), option 66 (Mercury) and boot file `<hostname>.cfg` (option 67). On a ZTP subnet `match-client-id` is false, so the serial-form client-id still gets the MAC's address (C1403). | `ztp.reservation_entry` (`modules/nsot/ztp.py`); `onboard.promote_device`; `retire._remove_reservations` |
| ZTP responder | **Refuses.** It serves only a PENDING ZTP device (`manifest.pending_devices` skips `verified_at`). `r6.cfg` is refused as "no pending ZTP device holds the reservation <mac> -> <ip> (promoted, abandoned, or never onboarded as ztp)"; `network-confg` and the rest as "its reservation names 'r6.cfg'". The device gets a TFTP error. The audit row is `bootstrap_config_refused` with target `?`, and History shows such rows only on a pending device's page, so for a promoted device they show nowhere. | `ztp_responder.decide`; `history_sources` |
| The bootstrap itself | **Could not be produced anyway.** The Day 0 bootstrap renders from the STAGED bootstrap credential, which phase 2's rotation replaces and clears. | `onboard.bootstrap_artifact`; phase 2's rotate step |
| Devices list, device page | "Not answering" once three probes miss. ICMP is not permitted from the deploy host, so a configless box with a DHCP address still reads as not answering. Nothing says "it is asking for its boot file". | `readers/reachability.py`; `device_list.py`; `device_page.py` |
| Needs attention | "r6 is not answering" (danger, "Check the path from Mercury first…"); drift's "r6 could not be checked for drift"; routing rows as neighbours drop. **No row says the device has booted blank, and none offers a recovery.** | `attention.py` (reachability, drift) |
| Restore, deploy, Reload | Each needs an SSH (or NETCONF) session to the device. | `pipeline._push_config`; `reload_op.py` |
| Revert by reload (one-shot TFTP) | Design only, and it copies to startup over SSH. | `docs/NSOT_REVERT_BY_RELOAD.md` |
| Break-glass record | Holds the credentials for a console login; after `write erase` the device no longer has them. It helps only a person rebuilding by hand. | `modules/breakglass.py` |
| Onboarding again | Refused at every step without a Retire: Add device ("'r6' already has an identity"), the MAC ("already reserved"), Verify ("already promoted"), Abandon (promoted). | `onboard.py`; `ztp.py` |
| Retire, then Add device again | Needs no SSH, and works. But it releases the identity, sets the NetBox record to Decommissioning under a new name, archives the golden tags, cuts History at the retirement (C1420), and serves Day 0 only (Day 1 is C1471). **A different device, by the rule that a retired name inherits nothing.** | `retire.py`; C1420, C1471 |

**So today:** nothing recovers a blank managed device through Mercury without losing its
identity. The paths are a person at the console pasting configuration (labour, outside
Mercury's record) or Retire and re-add (a new identity). The operator's expectation was right.

## 2. The design

### 2.1 Detect: a known device asking for its boot file while not answering

- The responder already decides on the reservation. For a reservation whose device is
  PROMOTED it records the refusal with its target named (the device, its MAC, the file asked
  for), never `?`.
- A **reader** joins that with reachability: the device is promoted, it has asked for its boot
  file within the last N minutes (the responder's record), and SSH does not answer. That state
  is `booted_blank`. Either one alone is not enough:
  - asking without being down is a device someone is testing;
  - being down without asking is an outage, which keeps its own row.
- **The row** (Needs attention, danger): "r6 has booted without its configuration: it asked for
  r6.cfg at 03:12 and SSH does not answer." Action: **Recover…** on r6's page. It clears when
  the device is recovered, or when the device answers again with its configuration (rebooted
  from a surviving startup). It is never acknowledged away: a blank managed device is not a
  state to accept.
- The device page draws the same state in its header, and History shows the responder's
  refusals on the managed device's page too.

### 2.2 Recover…: Day 0 again, same identity

A preview, then a confirm by hash as a verified person. The preview names:
- **Kept:** the identity (manifest entry, NetBox ID, History, golden tags, intent), the
  reservation, and the address.
- **The bootstrap that will be served:** Day 0, rendered by the onboarding's own
  `bootstrap_artifact`, with a NEW one-time credential staged for this recovery (never the
  rotated one, which only the golden holds as a hash).
- **The window:** served once, within 30 minutes, to this MAC at this address, then refused
  again.
- **What follows:** recovery phase 2.

On confirm:
- the manifest entry gains `recovering` (who, when, why);
- the responder's `decide` serves a recovering device exactly as it serves a pending one;
- the audit row is `bootstrap_config_served` with the device named.

### 2.3 Recovery phase 2: back to its golden, through the deploy path

When the device answers SSH with the one-time credential:
1. **Rotate** the credential to a device-generated secret, as onboarding's phase 2 does. The
   credential store is updated, and the break-glass record goes stale (its own row, as after any
   rotation).
2. **Restore** the newest committed golden (the device's current golden tag, or the newest
   earned baseline, the same source as `startup_source`), through `restore.py`'s preview:
   - the exact program, masked, against the Day 0 configuration the device runs;
   - confirmed by hash as a verified person;
   - applied merge-only, holding the device; verified; rolled back on failure; recorded.

   The golden's `username` lines are not sent: the rule "a deploy may add an account, never
   change one" stands, and the account phase 2 just rotated is the one Mercury holds. The
   receipt says which lines were left out and why.
3. **Persist** (save to startup, read back), then **capture** the golden. The new capture
   carries the rotated account's hash, so the golden and the device agree again.
4. **Clear** `recovering`. The History row reads "recovered from a blank boot: Day 0 served
   03:14, restored 03:21 from golden/r6/<ts>, verified", one record keyed by the identity.

Verify is the restore's own: neighbours, routes, interfaces and read-back, scaled to the
program (FULL). A partial restore is amber, never green.

### 2.4 Hardware replacement: a new MAC

The box is replaced, so a NEW MAC asks for an address on the device's link.
- It takes a discovery-pool lease (or none, on a relayed subnet with no pool), and the
  Discovery screen lists it.
- Its row offers **Replace <device>'s hardware…**, never a guess by resemblance: the operator
  chooses which managed device this box replaces.
- The preview names the old MAC and the new one, and the serial when it reported one (option 61
  in the serial form, C1479). It also names what changes:
  - the Kea reservation moves to the new MAC;
  - NetBox's interface MAC and the device's serial are updated, each recording its before;
  - the stored host key is cleared, so a new key is expected and accepted once, within the
    window.
- A confirm by hash, then the same flow from 2.2. The identity, NetBox ID and History stay.
- The old MAC's reservation is removed; if the old box answers again later, it is an unknown
  device.

### 2.5 Refusals (each naming its comparison and both operands)

- **A device that answers SSH:** "r6 answers SSH at 10.255.4.2: it is not blank; recover is for
  a device that cannot be reached." Restore is the path for a device that answers.
- **A device that has not asked for its boot file within the window:** refused, naming the last
  time it asked, or that it never did.
- **A device with no committed golden:** refused. There is nothing to recover to, and Retire and
  Add device is the path.
- **A static or DHCP-onboarded device whose platform does not ask for a boot file** (the lab's
  vIOS switches): the row and the manual name the console as the repair route (a person's,
  recorded as LABOUR in `docs/MANUAL_STEPS.md`). It is never a silent gap.
- **IPv6** (CLAUDE.md, IPv6 parity): DHCPv6 AutoInstall is not measured on this fleet. The row
  and the manual say recovery ZTP is IPv4 until it is.

## 3. Size

| Part | Size | Notes |
|---|---|---|
| The responder names the target for a promoted reservation; History shows refusals on a managed device's page | S | `ztp_responder.decide`, `history_sources` |
| The `booted_blank` reader and its Needs attention row | S to M | a new reader (the responder's record joined with reachability), `attention.py`, CLEARS |
| Recover… (preview, confirm, `recovering`, one-time serve) | M | a card on the device page (a board, its fidelity record), `route_gates`, `invalidation`, the manual's How it works page, operation stages |
| Recovery phase 2 (rotate, restore without account lines, persist, capture, record) | M | reuses onboarding's phase 2 steps and `restore.py`; the account rule's exception is declared in the hash and the receipt |
| Hardware replacement | M | Discovery's row action, Kea's reservation move, NetBox MAC and serial with before, host-key reset |
| Tests and a real run on the lab (R7: `write erase`, reload, recover) | M | a planned-restart window first |

**In all: L, about 5 to 7 days.**

## 4. Place in the build order

After Lab 9's own needs (R8 and the switch by ZTP, C1442, C1487, C1450, C1476's members on
camera) and before Core 1.0's sign-off: it is the recovery half of ZTP, and a release that
onboards by ZTP and cannot recover a ZTP device without losing it is unfinished. It depends on
C1471 (Day 1 automation), because recovery's restore and Day 1's apply share the "intent onto a
Day 0 device" step; build that step once.

## 5. Friday's rehearsal: the deliberate test

Run it as the first part of R7's rehearsal reset, before R7's Retire, so it costs no extra
redeploy:
1. **[YOU]** Declare a planned-restart window for R7 (the standing rule).
2. **[YOU]** On R7's console: `write erase`, confirm, `reload`, confirm, do not save. This is
   LAB labour; Mercury has no `write erase` operation.
3. **[ME] read, expected today:**
   - R7 boots configless and gets 10.255.4.6 through R6's relay (its reservation stands).
   - It asks for `r7.cfg`; the responder refuses ("no pending ZTP device holds the reservation …
     (promoted …)"), and the audit row carries target `?`.
   - The Devices list reads "Not answering", Needs attention "r7 is not answering", drift "could
     not be checked", and R6 loses R7's RIP routes.
   - Nothing names the blank boot or offers recovery.
   - The capture shows how often R7 asks, and whether AutoInstall gives up.
4. **[YOU]** Then the reset as planned: Retire R7 (it needs no SSH; the break-glass record holds
   the current credential), Add device › ZTP again. R7 then fetches its Day 0 and the rehearsal
   continues.

The test's record is today's behaviour, measured: the "before" of this design.
