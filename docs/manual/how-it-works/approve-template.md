# Approve a template

A deploy renders a device's intent through its network's template for its platform, and only
through an approved one. Approving says the template, as it is now, reproduces at least one
real device; it is recorded as you, with each bound device's result as evidence. It is done on
**Templates**, from the template's row. Nothing is sent to any device.

![Approving a template: every bound device's captured configuration is parsed, rendered back through the template and compared line by line, its unmodelled lines judged against its committed intent's acknowledgement; you confirm, bound to the template's fingerprint and the check you read; the approval is recorded and committed. A revocation records its reason. No device is contacted.](diagrams/approve-template.svg)

## The steps

1. `check`: every device bound to the template is checked against its captured configuration.
   Read: each bound device's golden at HEAD, the template and every file it imports, and each
   device's committed intent. Sent: nothing. Recorded: nothing. The capture is parsed into
   intent, rendered back through the template and compared with the capture line by line.
   Each device names every line that failed: what the render misses, what it invents, the
   sections it reorders, and the lines the parser does not model that the device's committed
   intent has not acknowledged (its `unmodeled_ack`, written by the
   [intent editor](edit-intent)), or acknowledges and the capture no longer has. A bound
   device with no capture yet is named as not validated; it is checked at its own deploy.
   Lines the device writes for itself never count. The template is approvable when at least
   one device reproduces exactly.
2. `approve`: you confirm, as yourself. Read: the template's fingerprint and the check again.
   Sent: nothing. Recorded: the approval (the fingerprint, you, when, and each device's result
   as evidence) in the network's approvals record. If the template or a file it imports
   changed since the card showed it, or the check's outcome changed since you read it (a
   capture, an acknowledgement or a binding moved), nothing is approved and the card says what
   moved, naming both.
3. `commit`: the approvals record is committed to the network's repository as you. A deploy
   counts an approval only once it is committed, so if the commit fails the card says the
   template is not approved yet.

## Revoking an approval {#revoke}

4. `revoke`: **Revoke…** on an approved template's row asks why. Read: the record. Sent:
   nothing. Recorded: the revocation, with your reason, who and when, and what it withdrew,
   committed. Every deploy through the template is refused until it is approved again; the
   reason is shown on its row. A revocation is never deleted: it is the record of why the
   template stopped deploying.

## What approval does not do

- It contacts no device and changes no configuration.
- It does not say every device renders faithfully: each device is checked at its own deploy.
- It never acknowledges a line for you: that is a person's decision, made in the device's
  intent.
