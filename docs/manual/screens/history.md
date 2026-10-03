# History

What happened to the network and its devices, and when: one timeline of everything the tool
records, the network's baselines, and the Oxidized divergences people authorised, with the
remote's state at the top.

## The remote {#remote}

One sentence says whether everything is committed and whether it is pushed to the network's
remote repository, with when that was last checked. **Verify the remote** runs the read-only
checks against it (the key's scope, a read, that it is private and the right repository).
**Push now** appears while something is not pushed; it needs a person, and the sentence
redraws once the remote is read again.

## Timeline {#timeline}

Every record the tool keeps, across every device, newest first, for the time you choose (7 days
by default). It also holds the records that belong to no one device: a commit to the monitoring
profile or the templates, a Save All's baseline decision, an update of the app. A device's
History tab is this same timeline filtered to that device, read by the same code, so the two
can never show different things.

Each record is one line:

- **When.**
- **Kind.**
- **Device:** one device, a few, how many, "every device" (a window for the whole list), or
  **fleet** for a record about no one device.
- **What.**
- **Who.**

Open a line for the full record underneath. It shows:

- the reason and each step with its result;
- how the person was identified;
- for a commit, **Show the change**: its diff, with every secret masked;
- **Open (device)'s History** for each device the record names.

The Baselines and Authorisations tabs work the same way, with each baseline's reasons and each
authorisation's stated reason under its line.

Filters:

- **Device:** that device's records only; the fleet's own records drop out.
- **Person.**
- **Kind,** in four groups:
  - **The repository:** commits (golden, intent, profile) and measured-unchanged saves.
  - **What ran on a device:** deploys and restores, rotations, persists, onboarding and adopt,
    runs cut off midway, and authorised retries.
  - **What happened to a device:** restarts and planned windows.
  - **Decisions and records:** approvals, acknowledgements, freshness authorisations,
    break-glass exports, baseline decisions and app updates.
- **Since.**

**Every kind** and **Commits only** are one click away. Each filter is part of the page's
address, so a view is a link you can share. A long list shows the newest and says how many there
are, with **Show more**. A record store that could not be read is said above the list. A
commit whose record is known to be wrong says so in its row.

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
