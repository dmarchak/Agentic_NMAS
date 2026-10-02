# Seed intent

A device that was just onboarded has only bootstrap intent: a hostname, logging and secret
references, no interfaces or routing. It cannot be deployed to until it has full intent.
Seeding gives it one, once, from its committed golden.

## The preview

1. **The committed golden is parsed** through the platform's parser into an intent document.
2. **The document is shown** as a diff against the intent committed now, with what the
   template cannot reproduce named line by line, and which secrets would move into the
   credential store.
3. **Only absent or bootstrap-only intent is offered.** A device with full intent is shown
   and not selectable: seeding over it would replace what the device should be with what it
   is, erasing every intended change not yet deployed.

Nothing here opens a session: the golden is read from git.

## The apply

1. Each device is **parsed again**; one whose golden moved since the preview is refused.
2. The secrets are stored in the credential store; the document carries references, never
   values.
3. **One commit** of exactly the seeded files, as you, with `Source: seed` and `Seeded-From:`
   naming the golden it came from.

From then on the device's changes are deploys (see [Deploy a change](deploy)).
