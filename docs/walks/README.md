# Walk scripts

A walk script is the list of steps the operator follows in their own browser for one sitting of
docs/PHASE7_BURNDOWN.md section 1b: W1, W2 and W3. Each one is needed because a confirm by hash
needs a verified person, and the agent cannot be one.

The agent writes each script from the code and from a read-only look at the host the day it is
written:

- **Each step names a page and an action, then gives its PASS.** The page is a v2 address,
  relative to the host. The action is the exact control to press or the exact text to type. The
  PASS is what the screen should then say, quoted from the templates or the code that draws it.
  No step uses a device console, a host shell or one of today's (v1) pages.
- **A change names its target and its undo.** Each target is chosen from the host as it was read
  that day: never s3, and never the management path. A step that changes a device says what to
  do if its PASS does not appear. A device that one step changes is put back by a later step,
  and the last section checks that every device is as it started.
- **A screen built from a board names the board.** That is the board's canvas and file, plus two
  to four things to compare. A screenshot of that screen is then enough for the board-fidelity
  record (C650; docs/fidelity/), so the record comes out of the same sitting.

**How results come back.** For each step number, paste one block into the session with the
agent: `PASS`, or what the screen showed instead. Add a screenshot where the step asks for one.
Stop at the first step whose PASS you do not see, unless the step says to go on, and say which
step it was. The agent then records each result in the register row or CUTOVER row the step
clears. It also turns the screenshots into fidelity records. It logs every deviation in
docs/STANDING_APPROVAL_LOG.md and registers anything new before the sitting's report is written.

A script is good for the host state it was written against. Its "Before you start" section says
what that state was. If what you see differs from it, stop and tell the agent before the first
step that changes anything.

| Sitting | Script |
|---|---|
| W1, Devices and device | [W1.md](W1.md) |
