# Add an app to the code repository as a Draft

A network's apps live in its code repository, and Mercury registers each `apps/<name>/` folder
it fetches from there as a **Draft**. **Add an app as a Draft…** on [SDN › Apps](sdn#apps) puts
a new app there for you: you choose the app's folder, Mercury shows the one commit it would
make, and you confirm it. It is Mercury's only way of writing to a code repository, and it can
only add a new folder. A Draft still runs only in the container harness: **Publish** stays a
person's review and a passing run of its tests at its hash ([Publish an app
version](app-publish)).

![Adding an app as a Draft: you choose the app's folder; the preview checks every file and reads the branch's commit from the code repository now, into a throwaway repository removed again, and shows the exact commit and its hash; you confirm, bound to that hash; the program is made again and refused if the base commit or the files moved; the commit is built in a throwaway repository and pushed fast-forward only; the write is recorded, then the repository is fetched so the new folder registers as a Draft. Nothing already in the repository is changed, and no device or controller is contacted.](diagrams/draft-write.svg)

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
   ls-remote`) and fetches it into a throwaway repository, removed again, to see that
   `apps/<name>/` is not there yet. The card shows the program: where it goes and on which
   branch, the commit it goes on top of (none for an empty repository's first commit), the
   folder, each file's path, size and sha256, the commit message, and you as its author. All of
   it is bound to one hash. Nothing is written to the repository, to Mercury's copy or to its
   record.
3. `confirm`: you press **Add <name> as a Draft**, as a verified person.
4. `build`: inside the code repository's lock, Mercury makes the program again and compares
   its hash with the one you confirmed. If the branch moved or the files changed, nothing is
   added and the card says which, with both values. The commit is built in a throwaway
   repository under the network's folder in Mercury's data, never in Mercury's copy and never
   in a working tree: the branch's tree, plus each file as a new blob (a regular file, never a
   link), one commit with you as author and committer and the `Actor:` and `Actor-Verified:`
   lines Mercury's commits carry. Before it is pushed, the commit is read back: it must add
   exactly the folder's files and change nothing else.
5. `push`: the commit is pushed to the branch with no force, so git itself refuses anything but
   a fast-forward. If someone pushed in between, git's refusal is shown and recorded. git runs
   as a fetch does: no hooks, no credential helper or prompt, only its local and https
   transports. The throwaway repository is removed whatever happened.
6. `record`: the write is kept in the code repository's record: who, when, the location and
   branch, the commit it went on top of, the new commit, the folder and each file's hash. A
   refused push is kept too, with git's words.
7. `register`: Mercury fetches the repository, as **Fetch now** does, so the new version is
   registered as a Draft in the same operation. The card says whether it registered; if the
   fetch failed, it says why, and **Fetch now** on the Code repository card registers it.
8. `announce`: the Code repository card and SDN › Apps read again. Open the app's page for
   **Run its tests**, then **Review and publish…**.

There is no rollback, and none is needed: the commit only adds a new folder and is pushed
fast-forward only, and a refusal at any step changes nothing in the repository.

## The preview {#preview}

The preview is the commit exactly as it would be made. Its hash covers the location, the
branch, the commit it goes on top of, the folder, every file's path and sha256, the message
and you, so the confirm adds that commit or nothing.

## The confirm {#confirm}

The confirm is yours, as a verified person: Mercury does not add a Draft for a service or for
an unverified caller. The confirm carries the files back as the preview drew them, and the
hash is checked again against them.

## Refusals {#refusals}

Each refusal names what it compared, with both sides:
- **An https location:** Mercury adds a Draft only to a code repository at a local path. A
  push over https needs a push credential Mercury does not hold, so it is refused, and the
  control says so before you choose a folder.
- **The folder is already there:** a Draft is a new app folder only, never a change to one in
  the repository, so nothing registered or published is ever changed. Choose another name, or
  change that app in the repository.
- **The branch moved, or the files changed,** since the preview.
- **No default branch:** an empty repository with no branch named in the setting. Name the
  branch on the Code repository card (Settings › the network › Network).
- **The folder itself:** a name that is not an app's, no `manifest.yml` or one naming another
  app, a path outside the folder, a file that is not UTF-8 text, or one over a cap.

A refusal adds nothing. **Choose the folder again** opens the picker again; **Close** puts the
control back.

## Registered {#register}

The answer names the new commit, the commit it went on top of and the folder, and whether the
fetch registered it as a Draft. **Open <name>'s page** opens the app's page, where its row
offers **Run its tests** and **Review and publish…**. If the fetch did not register it, **Open
the Code repository's card** takes you to **Fetch now**.
