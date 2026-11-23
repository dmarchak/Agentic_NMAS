# Turn on self-healing and fix all, and the control strip

When several devices of a network depart from their intent at once, self-healing holds them
all (guard 6, many devices at once): a fleet-wide departure is escalated, never healed by
itself. Each hold keeps what its fix would send. Needs attention then shows one card for the
network: **"N devices have faults. Mercury can fix M."**, with guard 6's words and the exact
fix for each device, and one button, **Turn on self-healing and fix all**; the card is drawn
only while such a batch is held. The **control strip**, at the top of the Incidents page,
switches self-healing and automatic AI troubleshooting for the page's network.

Since 2026-11-17 guard 6 holds nothing (the operator: "remove guard 4 and guard 6 holds
entirely"), so the batch's card is no longer drawn; the same steps, below, are what turning the
control strip's **Self-healing** switch on runs for the problems already open.

![Turn on self-healing and fix all: guard 6 held several devices that departed at once, and each hold kept what its fix would send; Needs attention's card says how many devices have faults and how many Mercury can fix, with each program, before you press; you press once, as a verified person who may change self-healing, bound to the card's hash; the AI starts on each incident with no fix, as your press under every cap; a job turns on Auto for the network's default duration and records the approval, then fixes one device first through the heal, held and verified, and only then the rest at once, each held and verified, starting none after a failure; guard 10 still counts every heal; the outcome is recorded and the strip shows each step.](diagrams/heal-batch.svg)

Who may: a verified person allowed to change self-healing settings. Anyone else sees the card
and the strip with the state, the controls disabled, and why.

## Turn on self-healing and fix all {#fix-all}

Since 2026-11-18 this press is removed too (the operator): there is no **Turn on self-healing
and fix all** to press, and the steps below run only when the control strip's **Self-healing**
switch is turned on. What follows describes the card as it was.

On Needs attention, the batch's row offers **Turn on self-healing and fix all…**, which opens
the card. The card is the preview: before you press, it lists each device Mercury fixes with its program
(masked, the line count, each one a click away), each held device it cannot fix and why, and
each open incident with no fix Mercury can run. Nothing is sent until you press. One press, no
dialog:

- The press is bound to the card's hash: every device, incident, decision and program hash on
  it, and every incident the AI starts on. If any of it moved since the card was drawn,
  nothing starts, and both hashes are named. Read the card again and press again.
- **The AI** starts at once on each incident with no fix, in parallel with the fix: your press,
  held to the incident's AI cap, the day cap and the calls already in flight. It only
  proposes; nothing it proposes runs until a person approves it on the incident's page. A
  start a cap refuses is said on that incident's page, naming the cap.
- The rest runs as one job, each step on the stepper above Needs attention's list (and on the
  Incidents page's strip) as it happens, so a long fix never
  holds the page or the tunnel's request open:

1. `auto`: self-healing is turned on in Auto for the network for its default duration (Auto
   lasts, 1 hour unless the network says 8), through the self-healing policy's own write: Auto
   on any network, its expiry at most 7 days away. The change is
   recorded in the network's settings record with your name and the reason, and History shows
   it. Already in Auto, nothing is written.
2. `approve`: the batch is approved by its hash and recorded in the network's self-healing
   record: who, when, the hash, each device and its program's hash. Guard 6 is resolved for
   this batch only, and its grace period is dropped; every other guard still applies, and
   guard 10 (the most heals a network has in an hour) still counts every heal of the batch.
3. `fix`: every device at once, each on its own, with no device first (the operator,
   2026-11-16: a self-healing batch "runs every device at once: each held, preconditions
   checked, verified and rolled back on its own; no canary device first"). Each restore's
   incident is decided again with guard 6 resolved; a program that moved since the card was
   drawn is refused, nothing sent: its incident stays open, the refusal is on its device's
   History, and it is a failure the AI may start troubleshooting on, as any refused fix is.
   Then the self-healing fix itself: the device held, the
   deploy's nine stages, verified, rolled back on failure, and recorded, as any heal is
   ([Self-healing](heal)). Each saved script runs through its own path, its plan hash the one
   approved. A device that fails stops no other: its outcome is said on its own incident.
4. `record`: the batch's outcome is recorded with each device's: healed and verified, or did
   not heal (and why).

Each device's fix is also its own card on that device's page and under In progress.

## The Self-healing toggle {#self-healing-toggle}

On is Auto **until someone turns it off** (the operator, 2026-11-16), on any network, pressed by
a person who may change the network's self-healing; its label then reads **On**, and its hover
"Self-healing fixes problems by itself on <network> until someone turns it off". The change is
recorded on History as that person's decision. An Auto set in Settings with an expiry (1 h to 7
days) reads **On until HH:MM**, and returns to Dry run at that time. Off is Dry run:
self-healing still watches and says what it would fix, and sends nothing. One press, no
dialog; the toggle is busy on itself until the answer, then the strip is drawn again with the
state now. Switching it on is the approval for what is already open (the operator, 2026-11-16,
C3823): the open problems Mercury can fix run as one batch, in the steps above, named after the
switch-on. While self-healing is off, one line beside the switch says what turning it on does:
"Also fixes the N open problems (2 restores, 1 saved script)", and the open incidents with no
fix decided yet, "decided again in Auto, each fixed by itself only if its kind is allowed
Auto", said apart and never counted as fixed. What Auto heals by itself is still the kinds the
policy allows in Auto: a Tier 1 kind not allowed stays a dry run, and a Tier 2 fix is proposed
to a person. Every run's own preconditions and verify, guard 4 (a device Mercury may not
change), the findings and the notifications hold as in any Auto. A gate the policy holds
refuses it, naming the gate, and nothing changes. The gear opens the network's full
Self-healing settings, where every limit and kind is set.

## The AI troubleshooting toggle {#ai-toggle}

"AI troubleshooting: Automatic" is the network's AI troubleshooting control's **Automatic**
([Settings › AI](settings-ai#ai-troubleshooting)). With open incidents it would start on, one
line beside it says so first: "Also starts on N open incidents, about $X". Nothing else: no
list to tick, no form. One press turns it on, in these steps:

1. **Ready**: the network's spending limits and their estimate were acknowledged in Settings,
   and neither changed since. Otherwise the press is refused, naming what is missing or what
   moved, with a link to the limits, and nothing changes.
2. **The line**: the open incidents it starts on are read again; if they moved since the line
   was drawn, the press is refused, naming both, and the strip draws the line now.
3. **The mode**: a network whose mode was Off is set to Manual first.
4. **The switch**: turned on with the acknowledged estimate and limits, recorded on History with
   who, when and every open incident it starts on.
5. **The starts**: each listed incident starts once, as its own job under **In progress**, in
   your name, planned against every cap (its incident's, the network's day and month limits and
   the installation's day cap) before any starts. One past a cap is refused, and its incident's
   page names the cap.

Off goes back to Manual at once; an investigation already running finishes, and the limits
stay acknowledged. The gear opens the network's AI troubleshooting card in Settings › AI.

## The top bar

While self-healing is in Auto, or AI troubleshooting starts by itself, on any network, the top
bar shows a status chip ("Self-healing: Auto until …", "Self-healing: Auto until turned off",
"AI on"). It opens that network's control strip on the Incidents page. With neither on, there
is no chip.
