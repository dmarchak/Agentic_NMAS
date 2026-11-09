# Publish an app version: run its tests, and review it

A controller app version Mercury registers from the network's code repository is a **Draft**:
it can run only in the container harness, never on the network's controller. Publishing it
records that a person reviewed exactly that version, and that its own tests passed at exactly
that content hash. Only a Published version can be deployed from [SDN › Apps](sdn#apps).
Both actions are on an app's page, on each Draft's row: **Run its tests** and **Review and
publish…**.

![Publishing an app version: Run its tests stages the version from Mercury's copy at its commit and runs its own tests in the container harness on the network's controller Python, keeping the run with the version by its hash; Review and publish shows its pin, author, test run and who may publish under the network's policy, bound to a hash; you confirm with a reason; the folder is read again from its blobs and the test run checked at that hash; the publication is kept with the version's record, and the version can then be deployed. No device and no controller is contacted.](diagrams/app-publish.svg)

## Run its tests {#tests}

**Run its tests** stages the version from Mercury's copy of the code repository, from git's
blobs at its registered commit and never from a working tree. Its folder's hash is checked
against the one it was registered with. Mercury then runs the tests its `manifest.yml` lists,
in the container harness, on the Python the network's controller runs apps on:
- the folder is read-only and has no network;
- the app's code never runs inside Mercury.

The answer is drawn on the page: how many passed, and, when any failed, the output's last
lines, masked. The run is kept with the version's record by its content hash, so a later commit
of the same version number is a new pin, with no run yet. A network whose controller Python is
not recorded cannot run them, and says so.

## The steps {#steps}

1. `read`: **Review and publish…** reads the version's record. It shows the version's pin
   (commit and content hash), its author (the commit's, from git), its newest test run at that
   hash, who may publish under the network's policy, and whether you may. Reading it writes
   nothing.
2. `confirm`: you type why it is ready and press the Publish button, which names the version
   (**Publish 1.1.0**, say). The confirm is bound to
   one hash, covering the folder's hash, the test run and the policy.
3. `check`: inside the record's lock, the folder is read again from its blobs and must hash as
   it did. The test run must be this version's, at that hash, and must have passed. You must be
   allowed by the policy. Anything that moved publishes nothing, and the card names what moved.
4. `publish`: the publication is kept with the version's record. It holds who, when, why, the
   test run it rests on, the policy, and whether it was a self-review.
5. `announce`: every open page listing versions reads them again. The version can now be chosen
   and deployed to the controller.

## Who may publish {#who-may-publish}

The network's **Code repository** card (Settings › the network › Network) says who may publish
its versions:
- **someone other than its author** (the default);
- **its author too, recorded as self-review**, for a network one person runs.

Mercury does not yet know a network's roles, so it cannot count how many people review its
code. The network says so instead. A change is saved as you, with the value before and after.

## What is not checked yet {#not-yet}

The gate's mutation, survivors, reconcile and `@covers` checks are not part of Publish yet
(after the course labs; register C2728). Publish rests on a person's review and the version's
own tests passing.

## Publish {#publish}

A Published version is never moved by a later fetch. If the folder's hash changes, the version
is registered as a new Draft pin, and the publication stays with the hash it was made for.
