# How a baseline is earned

A baseline is a restore point for the whole network: a tag, `baseline/<time>`, on the one
commit at which every device's golden was recorded and every device was at its committed
intent. It is a claim about the network, so the tool takes one only when it has measured
that the claim is true, and records why when it has not.

![How a baseline is earned: every device in the inventory is read, each capture is compared with its committed intent, and only when every device was read and every one matches is the commit tagged baseline/<time>; otherwise the commit records the denial and its reason.](diagrams/baselines.svg)

## What the tag claims {#claim}

A baseline says: at this commit, the goldens are the network, and the network is what intent
says it should be. Two conditions make that true, and both must hold:

- **Coverage.** Every device in the inventory was read in this save. A device skipped,
  unreadable or refused leaves the claim unproven, and unproven is a denial: a baseline
  cannot speak for a device nobody measured.
- **At intent.** Each capture matches the device's committed intent: the render of its
  intent (with what it inherits from the network's monitoring profile) reproduces what the
  device runs. A device with no committed intent cannot match, because nothing says what it
  should be.

Comparing a capture with its golden would prove nothing, because the capture becomes the
golden. Intent is the comparison that survives.

## The decision is recorded on the commit {#decision}

Every save that asks for a baseline records its decision in the commit itself, so the answer
can be read again later in [History](history):

- `Intent-Match:` says whether each capture matched its committed intent (`yes (N of N)`, or
  `no:` naming each device that departs and by how many lines).
- `Baseline: earned`, or `Baseline: denied:` followed by each reason: the devices not
  captured, and each device that departs from intent with the lines that decide it.

The tag is the fact; the trailer is the decision. A denied save still commits its goldens,
and says why it earned nothing.

## Which saves ask for a baseline {#which}

- **Save All** (the fleet capture) always asks. A capture of one device never does: it makes
  no claim about the network, so it records no decision. See [Capture and Save All](capture).
- **A deploy batch** asks. Coverage here means the whole inventory was targeted and every
  device succeeded; a device with nothing to send is still read back, because "nothing to
  send" was decided against a stored capture, not the device now. A deploy to some devices
  is denied, naming the ones not targeted. See [Deploy a change](deploy).
- **A restore** asks, and its claim is stronger: the network is back at the chosen moment.
  Every device in the inventory must be read back afterwards and compared, section by
  section, with that moment's golden. Residue denies it: a merge cannot remove a line, so
  the network is not at that moment while residue remains. See
  [Restore and re-apply a baseline](restore).
- **The golden-state command** on the host asks, with an operational snapshot (see
  [below](#golden-state)). No v2 screen offers it.

## Nothing changed still decides {#nothing-changed}

A Save All where every device equals its golden changes no file, and still makes the
decision. The tool records it as an empty commit whose subject says so (`golden: no
configuration changed; decision recorded`), carrying the same `Intent-Match:` and
`Baseline:` trailers and a `Not-Done:` line saying no golden changed. If the decision was
earned, the tag goes on that commit. A denial is therefore never only a message on a screen:
its reason is in the history, and the save's preview says at the confirm that nothing will
be recorded but the denial.

## Two claims: configured, and configured and working {#golden-state}

A baseline records configuration, so a broken moment and a good one look the same. Every
baseline tag's message states which claim it makes:

- **configured**: every device's configuration captured, at intent. A baseline taken
  without an operational snapshot can make only this claim, and says so.
- **configured and working**: that, and every routing protocol each device's intent
  declares was up on that device at the same moment (OSPF neighbours FULL or 2WAY, BGP peers
  established, RIP sources heard). Only then does the tool add a second tag,
  `golden-state/<time>`, on the same commit.

v2 has no control that takes the working claim: no screen reaches the code that adds the
`golden-state/<time>` tag. It is taken only by the golden-state command on the host, which
reads and judges by default and commits nothing, and takes the baseline with its claim only
when told to commit. This is a gap, registered (C1357). The tag's message names each
device's state, each routing peer outside management (whose state the tool sees from one
side only), and what the snapshot does not read.

A baseline taken before baselines recorded their decision is drawn as **not recorded**,
never as earned: nothing says every device was at its intent.

## A withdrawn baseline {#withdrawn}

A baseline that records a state nobody should go back to (a deliberately broken device, for
instance) can be withdrawn. A withdrawal is kept in the tool's own table of withdrawn
baselines, keyed by the baseline's commit, with who decided, when and why. v2 has no control
to withdraw one: an entry is added to that table in the code (a gap, registered, C1358).
From then on:

- every restore route refuses it, whichever screen asked, and sends nothing;
- a device's list of restore points does not offer it;
- the Baselines tab draws it with its reason; once its tag is deleted it is no longer
  drawn. The commit and its goldens stay in history.

## A baseline decays with every rotation {#decay}

A baseline is a moment, and moments contain credentials. After a rotation, every older
baseline holds the password the rotation retired. Re-applying one would change the account
the tool signs in with, so the restore refuses that line, and holds back any secret the
device no longer has until a person authorises it with a reason (see
[Credentials: rotate and persist](credentials-lifecycle)).

So the tool judges, for every baseline, whether it can still be re-applied:

- **usable**: not withdrawn, and re-applying it would change no device's credential. A
  device the baseline predates does not count against it: a re-apply leaves that device
  as it is.
- **unusable**: withdrawn, or it would rewrite some device's credential, named.

The judgement is a background reader (every 5 minutes, recomputed only when the
repository's head or its tags move), and History's Baselines tab draws it. When no baseline
can be re-applied, [Needs attention](needs-attention) shows one row per network, "No stored
baseline can be re-applied", with its action: take a current baseline (Save All captures
every device and earns one if each is at its committed intent). When the last Save All was
denied, the row reads "No stored baseline can be re-applied, and a new one cannot be earned
yet", names the denial and its commit, and its action is to resolve each departure the
denial names first (change the device if intent is right, or edit intent if the device is
right), then Save All.

## What a baseline is not

- It is not proof the network works, unless it also carries a `golden-state/<time>` tag.
- It is not a NetBox backup. A baseline versions device configuration and intent, nothing in
  NetBox.
- It is never pruned. Per-device golden tags are trimmed to a retention count; baselines
  and commits are kept.
