# Revert or retry after a rollback

When a deploy fails verify, the rollback puts the device back, and intent still asks for
the change that failed. The tool then blocks that device's next plan, so it cannot offer the
same failing program again as if it were new. There are two ways out, and they mean opposite
things. **Revert** says the change was wrong: intent stops asking for it. **Retry** says the
change was right and the failure was elsewhere: the block is lifted so the next deploy may
send it again. Neither sends anything to the device.

![A rollback leaves a block beside the device's intent. Revert commits the inverse of one intent commit and then measures whether the block still applies; retry lifts the block with a stated reason recorded in the retry log. Neither reaches the device.](diagrams/revert-retry.svg)

## The block a rollback leaves {#block}

A rollback records, for that device, the lines the failed deploy added, the intent commit it
was deploying, when, and why. The block is **containment**, not equality: it stands while
those lines are still among the lines a fresh plan would send. An unrelated edit does not
lift it, and neither does an edit that only adds more lines around it. The block lifts in
three ways only: the failed lines are measured gone from the program, the device has no
committed intent any more, or a person authorises a retry.

If the record of blocks cannot be read, every plan on the list is blocked until it is
repaired, because whether any device's program is one that was rolled back is then unknown.

Both operations are under the device page's Actions: **Revert intent…** and **Retry
rolled-back change…**. They are offered only while a block stands on the device; otherwise
each row says why it is not offered (no block, or the record of blocks cannot be read). A
deploy or restore whose verify failed and rolled back offers both in its result too. Each
opens its card in place of the tab: the preview below, then the confirm, then the result in
the same card. A revert whose block still stands says so, and offers another revert or a
deploy plan.

## Revert: the change was wrong {#revert}

A revert undoes ONE intent commit's change and keeps every later commit. It applies the
inverse of that commit's own diff onto the intent committed now, as a new commit. It never
rewinds intent to an older snapshot, which would either bring the failed change back or
throw away an unrelated edit made since.

### The revert preview {#revert-preview}

1. **Choose the commit**. Read: the device's recent intent commits (the last 20) and its
   block, if any. Sent: nothing. Recorded: nothing. The chooser starts on the commit the
   rollback was recorded against, marked as the change a rollback undid; with no block, it
   starts on the newest.
2. **Compute the revert** (`plan_revert`). Read: the device's intent before that commit, at
   that commit, and at HEAD. Sent: nothing. Recorded: nothing. Every setting the commit
   changed goes back to its value before the commit; nothing else moves.
3. **Refuse a conflict**. Read: the same three versions. Sent: nothing. Recorded: nothing.
   If a later commit changed any of the same settings, the revert is refused with those
   settings named, because which edit should win is your decision, made by editing intent.
   The first intent commit a device has is refused too: there is no earlier state to return
   to.
4. **Show the result**. Read: nothing more. Sent: nothing. Recorded: nothing. The preview
   draws the intent document after the revert against the document committed now, each
   setting with its value now and after, the later commits it keeps, and the block. The
   confirm is bound to a hash of the commit, the intent committed now and the document that
   would be committed.

### The revert apply {#revert-apply}

1. **Hold the device**. Read: who else holds it. Sent: nothing. Recorded: nothing. A device
   another operation holds is refused, naming the holder, and nothing is committed.
2. **Compute again and compare**. Read: the same as the preview. Sent: nothing. Recorded:
   nothing. A different hash refuses with both hashes named, because intent or the commit
   moved since you looked.
3. **Commit** (`Source: revert`). Read: nothing. Sent: nothing. Recorded: one commit of
   exactly this device's intent file, as you, with a `Reverts:` trailer naming the commit
   undone. A document holding a secret value or a character a device cannot accept is
   refused before the commit; a failed commit puts the file back as committed.
4. **Measure the block**. Read: the program a plan would send now. Sent: nothing. Recorded:
   the block is removed only if the failed lines are measurably no longer in that program.
   Otherwise it STANDS, and the result says so: the failed lines may come from an earlier
   commit than the one reverted. If the program cannot be computed, the block is left
   standing and the next plan decides.

The device is not touched. Its next plan shows what a deploy would send to bring it to the
reverted intent; see [Deploy a change](deploy).

## Retry: the change was right {#retry}

A retry leaves intent as it is and lifts the block, with a reason you state. It is the only
way a block lifts while the failed change is still in intent.

### The retry preview {#retry-preview}

1. **Read the block** (`note_applicability`). Read: the block as recorded, and the program a
   plan would send now. Sent: nothing. Recorded: nothing. A device with no block, or whose
   block no longer applies, is not offered: a retry would authorise nothing.
2. **Show it with its history**. Read: the retry log. Sent: nothing. Recorded: nothing. The
   preview draws the program that failed, whether the block applies now, and how often this
   device was retried before, with the last time, person and reason. An unreadable retry log
   is said, never counted as none. The confirm is bound to a hash of the block as recorded.

### The retry apply {#retry-apply}

1. **Check the reason**. Read: the reason you typed. Sent: nothing. Recorded: nothing. A
   reason without the shape of one (empty, too short, or a copy of the line) is refused.
   It is recorded as testimony, not checked for truth.
2. **Hold the device**. Read: who else holds it. Sent: nothing. Recorded: nothing. A held
   device is refused, naming the holder.
3. **Read the block again and compare**. Read: the block. Sent: nothing. Recorded: nothing.
   A block recorded again since the preview refuses, with nothing authorised.
4. **Record the retry**. Read: the retry log. Sent: nothing. Recorded: a row in the retry
   log with the device, you, the reason, the time and the block it lifts. If the log cannot
   be read, the retry is refused and the block stands: a retry the record cannot hold is one
   nobody can see later.
5. **Lift the block**. Read: nothing. Sent: nothing. Recorded: the device's block is
   removed.

The next plan offers the failed program again. That deploy is planned, confirmed and
verified like any other, and if it fails it rolls back and blocks again.

## What neither does {#not}

- Neither sends anything to the device or opens a session. A revert changes intent; a
  retry changes the block. Converging the device is a deploy.
- A revert does not lift a block by its name. It lifts one only when the measurement after
  its commit says the failed lines are gone.
- A retry does not change intent, and does not approve the change for any later failure.
- The block and the retry log are kept on the host, beside the repository and ignored by it:
  they are not commits and are not pushed to the remote. The revert itself is a commit.
