# Day 1 automation: the full service configuration after ZTP (design, for the operator's review)

**Status: a design, 2026-10-20. Nothing in it is built.** Labs 8 and 9 come first; this is lab
work. It does not delay the one-file redeploy.

## 1. Day 0, Day 1, Day 2: the framing

| Day | What | How it reaches the device | Today |
|---|---|---|---|
| **Day 0** | The management plane only: hostname, a one-time account, the domain, the management address, SSH. Then the credential rotated, the first capture, the NetBox record and the monitoring profile | the bootstrap over **TFTP**, minimal, with no service configuration and no lasting secret in clear text (its one-time credential is rotated away at Verify); the rest over SSH at Verify | **automatic** (ZTP, onboarding's Verify) |
| **Day 1** | The full service configuration: interfaces and addresses, routing, relays, VLANs | over **SSH, after the rotation, through the normal deploy path** (preview, confirm by hash, apply holding the device, verify, rollback, record) | **manual**: Seed, hand-written intent, a deploy |
| **Day 2** | Operating it: drift, changes, Needs attention, rotation, removal, retirement | the deploy path and the operations | built |

**The gap this closes:** Day 1's intent exists only once a person writes it after the device is
up, and its deploy is one more separate step.

**The goal:** Day 1's intent exists before the device boots, and its deploy follows Day 0 under
an approval a person gave by hash, without weakening any guarantee:
- **merge-only:** a Day 1 program adds and never removes; a removal stops the automatic path;
- **what is confirmed is what is sent, byte for byte**;
- **Verify and rollback** as for any deploy.

## 2. Where the approval can be given

The operator's design puts the decision at **Add device**: Day 1's program is rendered against
the predicted post-Day-0 state, and approved by hash before the device exists. **Measured
against R6 (2026-10-20), that prediction is not knowable from what Mercury renders alone.**

R6's first capture held lines Mercury never rendered:
- the image's own defaults: `call-home` with Cisco's profile, `license boot level`,
  `platform qfp utilization`, `platform punt-keepalive`, `platform console serial`,
  `memory free low-watermark`, `diagnostic bootup level`, `login on-success log`,
  `multilink bundle-name`, `subscriber templating`, the SLA trust point;
- a per-boot value: `ip dhcp client client-id ascii <serial>`, which vrnetlab generates anew
  each boot.

The program is the intent's render minus what the device already runs. So a Day 1 intent that
contains any of these (a seed always does) yields a different program on the real device from
the one predicted, and the automatic path would stop every time. Making the prediction exact
needs a **platform baseline**: the lines every capture of that image holds, learned from earlier
onboardings, minus the per-device ones. That is buildable (2.3), but not safely by Thursday.

**Two places to approve, both keeping every guarantee:**

### 2.1 At Verify (recommended first)

**A person is already there at Verify, confirming Day 0's last program by hash from a real
capture.** So Verify's preview also shows Day 1's program:
- the attached intent (section 3), with the per-boot keys taken from this capture, rendered;
- minus what the capture holds;
- minus Day 0's own program, which Mercury knows exactly because it sends it;
- minus the credential families, because the rotation owns the account. A deploy may add an
  account, never change one.

**One fingerprint covers both programs.** After Verify applies Day 0 and promotes the device:
1. Day 1 runs as a **deploy job through the normal pipeline**, bound to the confirmed Day 1
   hash.
2. The pipeline already recomputes the program at apply and refuses on any difference, naming
   what moved. So Day 1 is sent only if the device is exactly in the predicted state.
3. On a refusal, nothing is sent. The device page offers the normal preview of the same Day 1
   intent, and Needs attention names the device ("Day 1 not applied: <what moved>").
4. Verify (FULL), rollback on failure and the receipt follow, as for any deploy.

### 2.2 At Add device (the operator's design; for Lab 9 or later)

The same, with the decision moved to plan time. It needs 2.3's platform baseline, so that the
post-Day-0 capture can be predicted exactly. When the real capture differs from the prediction,
the automatic path stops and offers the normal preview: the same rule as 2.1. The approval at
Add device then covers Day 0's bootstrap, Day 0's profile and Day 1 in one decision.

### 2.3 The platform baseline (needed by 2.2)

Every onboarding's first capture is kept. The baseline of an image is the lines all of them
share, after removing the per-device ones: hostname, addresses, keys, certificates and the
per-boot client-id. Each line carries its provenance: the image and the captures it came from.
- A baseline from fewer than two captures is not used.
- A capture that differs from the prediction refines it and is never trusted blindly.

## 3. Where Day 1's intent comes from

- **Short term (Lab 8): a stored intent document,** checked against the intent schema
  (`hostvars.validate`, contradictions included, C1429) and attached at Add device. Examples:
  `lab/lab8/r6-intent.yml` and R7's. **The per-boot keys are always the capture's**:
  - the management interface's `ipv4: dhcp` and its `unmodeled` client-id line;
  - the image's default lines, kept as the seed captured them;
  - `call_home`.

  The attached document gives everything else.
- **Lab 9 and after: generated from the source of truth,** a NetBox Planned record plus a role
  template:
  - the role, site and interfaces;
  - the addresses from IPAM, and the cables, which say which interface faces which device;
  - the role template (INTENT_AUTHORING_DESIGN's role profiles) supplies the routing for the
    role, for example OSPF in the site's area for a branch router.

  It is generated into the same document form, so 2.1 and 2.2 work unchanged. This needs
  Mercury to read a Planned record and its cables (C1447 plans the record in Mercury; C1442
  derives NetBox from operational addresses after the fact).
- **Never** a document typed into a free-text field on the screen: an attachment is a file
  checked against the schema, or a generation from NetBox, each shown in the preview.

## 4. How it fits the rest

- **C1460:** Add device creates the link's subnet. Day 1's intent then holds the parent's side
  too: the relay is already there (it is on the parent), so nothing changes on the parent
  during Day 1.
- **Role profiles and actions** (INTENT_AUTHORING_DESIGN): the role template of section 3 is a
  role profile, and an action ("Enable OSPF on…") is how a person edits the generated intent
  before Add device.
- **"Auto-onboard approved devices"** (MANUAL_STEPS M14, C1464): with that policy on, Verify's
  press is no longer a person's. **Day 1 cannot then be approved at Verify (2.1),** because
  nobody would be confirming. Under that policy Day 1's approval must move to Add device
  (2.2). Until 2.2 exists, an auto-onboarded device stops after Day 0 and its Day 1 waits for a
  person's preview.
- **C1442** (NetBox from operational addresses): Day 1's addresses become the device's real
  ones, so the NetBox writes after Day 1 come from the post-Day-1 capture.
- **C1421** (Planned becomes Active): stays at onboarding's record step (built). Day 1's deploy
  does not change NetBox's status.
- **Management to the loopback (C1410): not in Day 1.**
  - It changes the path Mercury reaches the device on. Under the standing rule that needs a
    repair route independent of that path.
  - It also changes the manifest's management address, the monitoring targets and the Kea
  reservation's role.
  - It is a Day 2 operation of its own (C1410), after Day 1, with its own preview and its own
    rule. Lab 8 keeps management on Gi2 by DHCP (decided 2026-10-20).

## 5. Options, sized

### (a) Lab 8 minimum, by Thursday 10-22: NOT safely, as specified

**Approval at Add device against a predicted state (2.2) cannot be gated safely by Thursday.**
The prediction is not exact without 2.3's platform baseline, which needs captures that Lab 8
has only one of (R6's).

**The smaller version that keeps every guarantee: (a′), approval at Verify (2.1), with a stored
intent attached at Add device.**

| Piece | Size |
|---|---|
| Add device takes an attached intent document (validated, shown in the preview, stored with the pending device, committed as intent at promotion, with the capture's per-boot keys merged in) | M |
| Verify's preview computes Day 1's program from the same capture, with Day 0's program and the credential families excluded, under one fingerprint | M |
| After promotion, a deploy job bound to the confirmed Day 1 hash; the pipeline's own recompute-and-refuse; on refusal the normal preview offered and a Needs attention row | M |
| The Verify card drawn with both programs (a board first, and the fidelity record), the manual's onboard page, tests with controls | M |

- **(a′) in total:** L by the inventory's sizes (about 10 to 16 h mid).
- **Before Thursday, it competes with tomorrow's redeploy, R6's redo and R7** for gates and
  deploy slots. A deploy may not fall in the D/E window, and the operator's attention goes to
  the walk.
- **My call: (a′) is not something to put into Saturday's recording untried.** Its first real
  run would be R6's redo tomorrow, with no rehearsal of the automatic path before Friday.

**Recommended for Lab 8: Day 0 automatic, Day 1 through the safe deploy path,** from the stored
intent:
- R6's redo: Seed intent…, then `lab/lab8/r6-intent.yml` applied as edits, keeping the seed's
  per-boot keys;
- then one preview and one confirm by hash.

The video says so plainly: "Day 0 is zero-touch; Day 1 is one approved, verified change; Lab 9
moves that approval up front." That is the walk as written; nothing new needs gating before
Thursday.

### (b) Lab 9 full: Day 1 generated and approved up front

| Piece | Size |
|---|---|
| (a′), as above | L |
| Generation from a NetBox Planned record: interfaces, IPAM addresses, cables, the site's area; read only, through NetBox's read path | M to L |
| The role template, for the router role (and the switch role for s5) | M |
| 2.3's platform baseline, from every onboarding's first capture (R6, R7, R8; s5 once 0a is measured) | M |
| 2.2: the approval at Add device, its prediction checked against the real capture, the stop-and-preview on a difference | M |

- **(b) in total:** L to XL (about 20 to 35 h mid).
- **For R8 and s5:** by 10-30 if (a′) lands first, in the week after Lab 8, between 0a's
  measurement and the second redeploy.
- **If it does not land by 10-30:** Lab 9 shows (a′) at Verify. That is still a real step: Day 1
  approved at Verify and applied automatically, with the generation from NetBox as the
  following step.

## 6. In the walks and the documentation

- **Lab 8's walk (section 1)** names Day 0 (ZTP, onboarding's Verify) and Day 1 (the stored
  intent, one deploy) at each device.
- **Lab 9's plan** names Day 1 approved at Verify, and generated from NetBox if (b) lands.
- **The manual's onboarding page** opens with the framing. Each day's how-it-works page is
  updated when it is built.
