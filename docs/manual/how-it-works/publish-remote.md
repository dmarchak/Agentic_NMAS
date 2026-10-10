# Publish to the remote: push and verify

Each network's repository (its goldens, intent, templates and tags) lives on the host.
Publishing copies its history to the network's own remote repository, so the record survives
the host. Every commit hands itself to the push, a gate holds any push that would publish a
secret nobody has agreed to publish, and a reader asks the remote itself whether it holds
what the host holds. Publishing sends nothing to a device, and the tool never force-pushes.

![A commit is handed to the push hook, which checks the publication gate and either pushes the branch and the commit's tags to the remote or holds them for a person; the remote is then read again to say whether the host and the remote agree.](diagrams/publish-remote.svg)

## Before the first push {#setup}

On **History**, the header's **Set up the remote…** (or **Remote set-up…** once there is one)
opens the set-up card below it. Each act is a verified person's, except reading what a push
would publish, and each is recorded.

### Connect {#connect}

**Connect** records the network's existing remote: the SSH alias, the owner, the repository,
the branch and, optionally, the key's path. Make the deploy key and the SSH alias on the host
first; Mercury never edits the host's SSH configuration. Each field must be one token of its
shape, said beside it (an alias starts with a letter or digit, an owner and a repository follow
GitHub's rules), because each reaches `ssh` or git as one argument: a field that is not is
refused by name and nothing is recorded. A network that already has a remote is refused.

### The write probe {#write-probe}

**Run the write probe** runs the read-only checks (below) and one more, which pushes an empty
commit holding no files to a scratch ref and removes the ref. It publishes no content, but it
is a write, so it needs a person. Each check is drawn with its answer. **Push refuses until
this has passed once.**

### What a first push publishes, and acknowledging it

**What a first push publishes** reads the whole history: the commits, the tags by kind, the
note refs, every gated secret by kind, salted fingerprint and device (never its value), and the
dead values and hashes counted. If anything is gated, the card asks you to type the gated kinds
to **Acknowledge** (next section); then **Push now**, in the header.

### Automatic pushing {#auto-push}

**Turn on automatic pushing** is offered only after a push has succeeded. From then on each
commit pushes itself (below), unless it would publish a secret nobody acknowledged, which holds
it for a person.

## The publication gate {#gate}

A push publishes every version of every golden, so the gate reads the whole history, not
only the current configuration. It looks for secrets in their secret positions: SNMP
communities, account and enable passwords (which can be read back), and account and enable
secret hashes (which cannot).

- A value is **live** when it still serves as a secret: it sits in a secret position in a
  current golden, or the credential store holds it. A value found only in older commits is
  **dead**.
- Only **live values that can be read back** are gated. Dead values and hashes are counted
  and never gated.

**Acknowledging** means typing the gated kinds exactly as named, which makes it an act of
reading rather than a click. The tool checks what you typed against the history as it is
now, not as the page showed it, and records who, when, the kinds and their counts, the commit
it was measured at, and each live secret by a salted fingerprint (never its value).

An acknowledgement keeps covering later commits until a **new kind** or a **new value**
appears. Another copy of a value already acknowledged (a new device given the same
community, say) is not new: it is counted and never holds a push. An acknowledgement made
before fingerprints were recorded counts occurrences instead, until it is made once more.

## Every commit pushes itself {#commit}

Every commit in a list's repository is handed to the post-commit hooks the moment it is made.
They run in the background with short time limits: they never delay a commit and never undo
one. The push runs first:

1. **The commit is handed over**. Read: nothing. Sent: nothing. Recorded: the commit, its
   list, and the tags it created. A process that is about to exit waits up to 90 seconds for
   its push, and says so if the push has not finished.
2. **The push decides** (`git-push`). Read: the list's remote record and the history scan.
   Sent: nothing. Recorded: if the gate holds the commit, a **hold**, with its reason and
   since when, and the commit's tags kept as pending. With no remote record for the list, or
   automatic pushing off, nothing is pushed and nothing is recorded.
3. **The branch is pushed**. Read: nothing. Sent: nothing to any device; the commit, to the
   remote's branch. Recorded: on a refusal, a push failure with git's reason. A remote that
   holds commits this repository does not is never overwritten: the failure says so.
4. **The tags are pushed**, one at a time: exactly the tags this commit created, and any
   pending tags an earlier held or failed push named. Read: nothing. Sent: those tags, to the
   remote. Recorded: a tag that could not be sent stays pending for the next push.
5. **The push is recorded**. Read: nothing. Sent: nothing. Recorded: the last push (by
   automatic push, when, the commit, the tags sent, whether it carried a commit or tags
   only). A success clears an earlier failure and an earlier hold.
6. **The remote is read again** (`publication-check`). Read: the remote's branch. Sent:
   nothing. Recorded: the reader's new answer, so every screen shows the push at once.

## Push now {#push}

On [History](history#remote), Push now appears while commits or tags are not on the remote,
while a push is held, or while the remote has no branch yet. It needs a signed-in person.

1. **The push is checked**. Read: the remote record and the history scan. Sent: nothing.
   Recorded: nothing. It refuses, saying why, unless the write probe has passed and the
   acknowledgement still covers what would go out. A held push stays held until somebody
   acknowledges on the Remote card.
2. **The remote's refs are read**. Read: every ref the remote holds. Sent: nothing. Recorded:
   nothing.
3. **The branch is pushed, with its tags**. Read: nothing. Sent: the commits, to the
   remote's branch, with every annotated tag on those commits the remote lacks, then any
   notes. Recorded: nothing yet.
4. **The push is recorded**. Read: the remote's refs again, to count what it gained. Sent:
   nothing. Recorded: the last push, by you, with the tags it gained; an earlier failure, a
   hold and the pending tags are cleared.
5. **The remote is read again** in the background. Read: the remote's branch. Sent: nothing.
   Recorded: the reader's answer, which redraws the header.

The button says **Pushed**, or **Not pushed** with the reason. Automatic pushing can then be
turned on from the Remote card.

## Verify the remote {#verify}

On History, Verify the remote runs the read-only checks and changes nothing. Anyone may run
it, because it is how you decide whether to publish.

1. **The key** answers, and is scoped to this one repository. A key that can reach every
   repository of an account is refused. If the key does not answer, the other checks do not
   run.
2. **A read** of the remote works.
3. **The repository is private**: the key can read it and an anonymous request cannot. If the
   anonymous request cannot be made at all, the check fails: an unverified privacy claim is
   not a privacy claim.
4. **It is the right repository**: not this application's own, not another list's, and empty
   or sharing this list's history.

Read: the remote, four ways. Sent: nothing. Recorded: when all four pass, the time of the
read-only verification. The button says **Verified: 4 of 4 checks passed**, or names each
check that failed. The write probe is not among these; it is on the Remote card.

## What the reader measures {#reader}

Whether a list's history is on its remote is measured by asking the remote, never taken from
the push's own record: a commit that never reached the push leaves no record at all. Every
two minutes, after every commit and after every Push now, the reader compares the
repository's HEAD with the remote's branch (`git ls-remote`, through the repository's own
`origin`, or the recorded address when there is none) and answers one state:

- **in sync**;
- **ahead**: how many commits are not pushed, and the oldest with its age;
- **held**: ahead, and the gate held the push, with its reason;
- **tags not pushed**: the branch is in step and some of the tool's tags (baselines, goldens,
  golden states) are not on the remote; a withdrawn baseline is left out;
- **no branch**: the remote has no such branch yet;
- **remote ahead** or **diverged**: the remote holds commits this repository lacks;
- **could not ask**: the remote did not answer within 10 seconds, or the read failed, with the
  reason. This is never read as in sync.

Its one sentence is what History's header, the Remote card and
[Needs attention](needs-attention) all draw. Commits not pushed are a warning, and danger once
the oldest has waited ten minutes, or at once when the push is held. Remote ahead and
diverged are danger. A remote record that cannot be read is named on every state, because
the push refuses every commit of that list until the record is repaired. It is never read as
"no remote": Verify, Push now and the acknowledgement refuse naming the file, History's header
and the Remote card say it cannot be read, and the file is left as it is.

## What it does not do {#not-done}

- It never force-pushes. When the remote is ahead or the histories have diverged, a person
  compares the two and decides which is the record.
- It never unpublishes. Rotating a credential after a push does not remove the old value from
  the remote's history.
- A failed or held push never undoes the commit: the commit stays on the host, the failure
  or hold is recorded, and the screens say so.
- It never pushes a list that has no remote of its own. There is no fallback to a shared
  address, so one network's history cannot land in another's repository.
- History does not yet carry the acknowledgement, the write probe or the automatic-push
  switch: those are on today's Remote card.
