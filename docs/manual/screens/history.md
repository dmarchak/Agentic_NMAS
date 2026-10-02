# History

What happened to the network's record, and when. Until the redesign's History page is built
(signed off 2026-10-02), the sidebar item opens today's Git and Baselines views.

## Commits {#commits}

Every commit in the network's repository, newest first: what it changed, its workflow
(capture, deploy, restore, intent, profile, rotation, onboarding), who did it and how that was
established, and the baseline it earned or why it earned none. Filter by device, person,
workflow and time; a row opens its files and its diff.

## Baselines {#baselines}

Every baseline: when, what it earned, whether it can be re-applied without changing a held
credential, and, if withdrawn, why. Re-apply is explained in
[Restore and re-apply a baseline](restore).

## Authorisations {#authorisations}

Each divergence between Oxidized's copy of a device and its approved golden that a person
authorised, with the reason and when it expires.

## The remote {#remote}

Whether everything committed is pushed to the network's remote repository, and Push now.
