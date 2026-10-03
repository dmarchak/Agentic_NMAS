# Seed intent

A device that was just onboarded has only bootstrap intent: a hostname, logging and secret references, no interfaces or routing. It cannot be deployed to until it has full intent. Seeding gives it one, once, by parsing its committed golden into an intent document and committing that document. Nothing is sent to any device and no golden changes.

![Seeding: the tool reads the device's committed golden from the repository, parses it through the platform's parser and template into an intent document, shows it as a diff against the intent committed now, and on your confirm stores the secrets in the credential store and commits the document; the device is never contacted.](diagrams/seed.svg)

You start it from the device's page, under Actions (Seed intent…), for that device: its card opens in place of the tab, and the confirm and the result happen in the same card. The operation can also take a whole list (every device whose intent is absent or only the bootstrap), but no screen offers that yet.

## The preview

Nothing here opens a session: the golden is read from git.

1. **The committed golden is parsed**. Read: the device's golden as committed at HEAD (never a working file), and the template the list's library binds to it for its platform. Sent: nothing. Recorded: nothing. The platform's parser turns the configuration into an intent document; the template renders that document back, and the two are compared to see what the template reproduces.
2. **The document is shown**. Read: the intent committed now. Sent: nothing. Recorded: nothing. It is drawn as a diff against what is committed, with what the template cannot reproduce named line by line (lines it does not render, lines it renders that the device lacks, and unmodelled lines), and the secret references that would move into the credential store. A device the template does not fully model is still seeded; its deploys stay blocked until those lines are modelled or acknowledged in its intent. The lines the device generates for itself are listed apart, as the device's own, and never block: its self-signed trustpoint (named after its chassis and regenerated at boot), every certificate body, and the licence UDI (its serial). They are never intent and never in any program, so a device that regenerates its certificate is never sent the old one.
3. **Only absent or bootstrap-only intent is offered.** Read: the committed intent's state (never committed, bootstrap only, or full; unparseable intent counts as full). Sent: nothing. Recorded: nothing. A device with full intent is shown and not selectable: seeding over it would replace what the device should be with what it is, erasing every intended change not yet deployed.
4. **The hash**. Read: nothing more. Sent: nothing. Recorded: nothing. You confirm a hash of the document and of the golden it came from, so a golden whose only change is a secret value (which the document holds only as a reference) still moves the hash. A device another operation holds is drawn as not selectable, naming the holder.

## The apply

The apply holds every confirmed device for the whole apply, so a capture or a deploy cannot rewrite a golden while it is parsed. A device another operation holds is refused alone, naming the holder.

1. **Parsed again**. Read: each device's committed golden, as in the preview. Sent: nothing. Recorded: nothing. A device whose seed hash moved since the preview is refused, naming both hashes; one that has gained full intent meanwhile is refused too.
2. **Secrets stored**. Read: nothing. Sent: nothing. Recorded: each secret value from the parse in the credential store, under a key scoped to this list and device. The document itself carries references, never values, and writing it refuses one that would carry a value.
3. **One commit**. Read: nothing. Sent: nothing. Recorded: each seeded device's intent file, and one commit of exactly those files, as you, with `Source: seed` and one `Seeded-From:` trailer per device naming the golden commit it came from. If the commit fails, each written file is put back as it was committed (or removed, when nothing had been), and the result says so; the secrets stored in step 2 stay in the credential store.

From then on the device's changes are deploys (see [Deploy a change](deploy)).

## What seeding does not do

- It sends nothing to the device and reads nothing from it.
- It changes no golden.
- It never replaces full intent: that is changed by editing intent.
