# A network's code repository: set it, and fetch it

A network's jobs and apps (its controller apps, such as `of_versions` and `switch_quirks`) live
in the network's own code repository, apart from its configuration repository, which holds its
goldens and intent. Mercury never shares a repository, a copy or a reader between the two. You
set where the code repository is, and fetch it, on its card: Settings › the network › Network ›
**Code repository**. What a fetch registers is listed on [SDN › Apps](sdn#apps).

A fetch only reads the repository. Mercury writes to it in one way only: **Add an app as a
Draft…** on SDN › Apps adds a new app folder as one commit, previewed and confirmed by you, and
only to a repository at a local path ([Add an app to the code repository as a
Draft](draft-write)). Every other change to the repository is yours.

![A network's code repository: you set where its jobs and apps live, a local path or an https URL and a branch; Fetch now fetches that branch into Mercury's own read-only copy, with only git's file and https transports, no prompt and no hooks, bounded; each apps folder at the fetched commit is registered as a Draft, pinned by the location, the commit and its content hash, read from git's blobs and never a working tree; the fetch is recorded, a failed one with why, and SDN › Apps lists what is registered. Nothing is written to the repository, and the configuration repository is never read.](diagrams/code-repository.svg)

## The setting {#the-setting}

- **Location:** a local path on the Mercury host (starting `/`, or `file://`), or an
  `https://` URL. An IPv6 host is written in brackets (`https://[2001:db8::10]/code.git`). A URL
  with a user name or password in it is refused: the credential would sit in the settings file
  in the clear. ssh, `git://` and `http://` are refused, naming why, and so is a path inside
  Mercury's own data.
- **Branch:** the branch to fetch; empty fetches the repository's default branch.

Each network's own: a network with none set has no code, and none is inherited from Default,
so another network's apps are never listed for this network's controller. **Save** is a
verified person's, refused when the setting moved since the card drew it (both values named),
and recorded in the network's settings record with the value before and after.

## The fetch {#the-fetch}

1. `check`: the setting is read and checked again, and Mercury's record of fetches must be
   readable (an unreadable record refuses the fetch, since writing would replace it).
2. `fetch`: the branch is fetched into Mercury's copy (`code_repo/` in the network's folder,
   beside its configuration repository and never inside it). The copy has no working tree:
   nothing is checked out, so there is no file in it to read, only git's objects. git may use
   only its local and https transports, asks for no credential and runs no hook, and the fetch
   is bounded (120 s, a placeholder until a fetch is measured).
3. `register`: each `apps/<name>/` folder at the fetched commit is read from git's blobs (its
   `manifest.yml` parsed) and registered as a Draft, pinned by the repository's location, the
   commit and the folder's content hash. A folder with no manifest, or whose manifest names
   another app, registers nothing and is listed under Not registered, naming the file and why.
   The same version with another hash is that Draft moved: the newer pin replaces it. An older
   version stays registered at its own commit, so a rollback can stage it.
4. `record`: the fetch is kept with who, when, from where, the commit and what it registered;
   a failed fetch is kept with why, and the copy keeps the commit it had.
5. `announce`: the card on every open page and SDN › Apps read again.

## What is listed {#registered}

SDN › Apps lists the versions registered from the location the setting names now, each read
again from blobs at its commit and its hash compared with the one registered. If the setting
was changed since the last fetch, nothing is listed until you fetch again: the old location's
versions are never shown as the new one's.

Every registered version is a **Draft** until it is published (the review, with a reviewer other
than its author), and a Draft deploys only in the container harness: SDN › Apps draws it
disabled, with that reason.
