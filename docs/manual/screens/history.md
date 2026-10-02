# History

What happened to the network's record, and when: its commits, its baselines, and the
Oxidized divergences people authorised, with the remote's state at the top.

## The remote {#remote}

One sentence says whether everything is committed and whether it is pushed to the network's
remote repository, with when that was last checked. **Verify the remote** runs the read-only
checks against it (the key's scope, a read, that it is private and the right repository).
**Push now** appears while something is not pushed; it needs a person, and the sentence
redraws once the remote is read again.

## Commits {#commits}

Every commit in the network's repository, newest first, for the time you choose (7 days by
default). Each commit is one line, and opens underneath at full width; the Baselines and
Authorisations tabs work the same way, with each baseline's reasons and each authorisation's
stated reason under its line:

- **What**: the commit's subject. Open a row for the devices and files it changed, its
  `Intent-Match:` (whether each capture matched its intent), and **Show the change**: the
  commit's diff, with every secret masked.
- **Workflow**: what made it (capture, save all, deploy, restore, intent, profile, rotation,
  onboarding).
- **Who**: the person or service, and how that was established: signed in through the tunnel
  (nothing added), a host login (not verified), or before verification was recorded.
- **Baseline**: earned (with its tag); denied, and why; or not taken (a deploy that did not
  cover every device). A commit whose record is known to be wrong says so in its row.

Filter by device (the commits that changed its golden or intent), person, workflow and time.
A long list shows the newest and says so, with Show more.

## Baselines {#baselines}

Every baseline: when it was taken, what its commit recorded it earned, and whether it can be
re-applied without changing a credential a device holds now (a baseline older than a
rotation cannot). A withdrawn baseline is drawn with why. The judgement is made in the
background whenever a commit or a tag moves. Re-applying is explained in
[Restore and re-apply a baseline](restore); it opens on today's page until the redesign
carries it.

## Authorisations {#authorisations}

Each divergence between Oxidized's copy of a device and its approved golden that a person
authorised, with who, why, and when it expires (or that it has).
