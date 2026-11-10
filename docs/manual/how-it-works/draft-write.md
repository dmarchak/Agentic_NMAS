# Add an app to the code repository as a Draft

A network's apps live in its code repository, and Mercury registers each `apps/<name>/` folder
it fetches from there as a **Draft**. **Add an app as a Draft…** on [SDN › Apps](sdn#apps) puts
an app there for you: you choose the app's folder, Mercury shows the one commit it would make,
and you confirm it. It is Mercury's only way of writing to a code repository, and it can do
two things only: add a **new app** folder, or add a **new version** of an app Mercury has
registered (an app you fixed after a test, say), replacing that folder's files. A Draft still
runs only in the container harness: **Publish** stays a person's review and a passing run of
its tests at its hash ([Publish an app version](app-publish)).

![Adding an app as a Draft: you choose the app's folder; the preview checks every file and reads the branch's commit from the code repository now, into a throwaway repository removed again, and shows the exact commit and its hash; you confirm, bound to that hash; the program is made again and refused if the base commit or the files moved; the commit is built in a throwaway repository and pushed fast-forward only; the write is recorded, then the repository is fetched so the new folder or version registers as a Draft. A new version replaces only its folder's files, and only when that folder is a version the tool registered; every registered version stays at its own commit, and no device or controller is contacted.](diagrams/draft-write.svg)

## The steps {#steps}

1. `check`: the folder is checked before the repository is read. Its name is the app's
   (lowercase letters, digits and `_`, starting with a letter), its `manifest.yml` is at its
   top and names the same app, and every file is UTF-8 text with a plain relative path inside
   the folder (no `..`, no `.git`, no absolute path, only letters, digits and `. _ + -`). A
   folder holds at most 64 files, 128 KiB a file and 256 KiB in all: Lab 9's largest app,
   `fabric_forwarding`, is 7 files and 65 KiB. You choose the folder in the card that
   **Add an app as a Draft…** opens, then press **Preview adding it**; **Cancel** closes the
   card, adding nothing.
2. `preview`: Mercury reads the branch's commit from the code repository now (`git
   ls-remote`) and fetches it into a throwaway repository, removed again, to see whether
   `apps/<name>/` is there. If it is not, this is a **new app**. If it is, this is a **new
   version**, allowed only as [A new version](#version) says. The card shows the program:
   where it goes and on which branch, the commit it goes on top of (none for an empty
   repository's first commit), the folder, for a new version the version it supersedes and
   each file added, changed, removed or unchanged with its sha256 before and after, each file's
   path, size and sha256, the commit message, and you as its author. All of it is bound to one
   hash. Nothing is written to the repository, to Mercury's copy or to its record.
3. `confirm`: you press **Add <name> as a Draft**, as a verified person.
4. `build`: inside the code repository's lock, Mercury makes the program again and compares
   its hash with the one you confirmed. If the branch moved or the files changed, nothing is
   added and the card says which, with both values. The commit is built in a throwaway
   repository under the network's folder in Mercury's data, never in Mercury's copy and never
   in a working tree: the branch's tree, less each file a new version removes, plus each file
   as a new blob (a regular file, never a link), one commit with you as author and committer
   and the `Actor:` and `Actor-Verified:` lines Mercury's commits carry. Before it is pushed,
   the commit is read back: it must add exactly the folder's files (a new app), or make exactly
   the previewed additions, changes and removals inside the folder (a new version), and change
   nothing else.
5. `push`: the commit is pushed to the branch with no force, so git itself refuses anything but
   a fast-forward. If someone pushed in between, git's refusal is shown and recorded. git runs
   as a fetch does: no hooks, no credential helper or prompt, only its local and https
   transports. The throwaway repository is removed whatever happened.
6. `record`: the write is kept in the code repository's record: who, when, the location and
   branch, the commit it went on top of, the new commit, the folder and each file's hash, and
   for a new version the version it supersedes and each file added, changed or removed. A
   refused push is kept too, with git's words.
7. `register`: Mercury fetches the repository, as **Fetch now** does, so the new app or version
   is registered as a Draft in the same operation. The card says whether it registered; if the
   fetch failed, it says why, and **Fetch now** on the Code repository card registers it.
8. `announce`: the Code repository card and SDN › Apps read again. Open the app's page for
   **Run its tests**, then **Review and publish…**.

There is no rollback, and none is needed: the commit adds a new folder, or a new version's
files in a folder whose earlier versions stay at their own commits, and is pushed fast-forward
only; a refusal at any step changes nothing in the repository.

## A new version {#version}

When `apps/<name>/` is already on the branch, the folder you chose is a new version of that app,
and Mercury adds it only when all of these hold:
- **The folder is exactly a version Mercury registered:** its content hash at the branch's
  commit equals that of a version Mercury registered for this app at this location. A change
  made there outside Mercury since is never overwritten: Fetch now registers it first.
- **The files are not the same:** at least one file is added, changed or removed.
- **Its version is higher** than every version of the app Mercury registered. Versions compare
  as three numbers, major, then minor, then patch (so 1.10.0 is above 1.9.0), as semver orders
  versions with no pre-release part; a manifest's version is always three numbers.

The commit replaces exactly the folder's files: a file you removed from the folder is removed
from the branch, a new one is added, and nothing outside `apps/<name>/` changes.

**Every registered version stays pinned.** A new version is a new commit on the branch, so the
version it supersedes keeps the commit and the content hash it was registered at. Mercury reads
each version from git at its own commit, never from the branch's head, so a **Published**
version stays Published at its hash and deploys exactly as before, and the new version is a
Draft until it is reviewed and its tests pass at its own hash.

## The preview {#preview}

The preview is the commit exactly as it would be made. Its hash covers the location, the
branch, the commit it goes on top of, the folder, whether it is a new app or a new version, the
version it supersedes and the highest registered, every file's path and sha256 and what changes
in each, the message and you, so the confirm adds that commit or nothing.

## The confirm {#confirm}

The confirm is yours, as a verified person: Mercury does not add a Draft for a service or for
an unverified caller. The confirm carries the files back as the preview drew them, and the
hash is checked again against them.

## Refusals {#refusals}

Each refusal names what it compared, with both sides:
- **An https location:** Mercury adds a Draft only to a code repository at a local path. A
  push over https needs a push credential Mercury does not hold, so it is refused, and the
  control says so before you choose a folder.
- **The folder is there, and Mercury registered no version of it:** Fetch now on the Code
  repository card registers what is there, then add the new version; or choose another name.
- **The folder is no registered version:** its content hash at the branch's commit is not one
  Mercury registered, so it was changed outside Mercury, and Mercury does not overwrite that.
  The refusal names the hash it read and each registered version's.
- **Nothing changed:** the files are the registered version's, file for file.
- **The version is not higher** than the highest registered, which the refusal names.
- **The branch moved, or the files changed,** since the preview.
- **No default branch:** an empty repository with no branch named in the setting. Name the
  branch on the Code repository card (Settings › the network › Network).
- **The folder itself:** a name that is not an app's, no `manifest.yml` or one naming another
  app, a path outside the folder, a file that is not UTF-8 text, or one over a cap.

A refusal adds nothing. **Choose the folder again** opens the picker again; **Close** puts the
control back.

## Registered {#register}

The answer names the new commit, the commit it went on top of and the folder, for a new version
the version it supersedes (which stays at its commit) and how many files were added, changed
and removed, and whether the fetch registered it as a Draft. **Open <name>'s page** opens the
app's page, where its row offers **Run its tests** and **Review and publish…**. If the fetch
did not register it, **Open the Code repository's card** takes you to **Fetch now**.
