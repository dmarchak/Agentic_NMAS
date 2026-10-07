# Bring in a shipped template

A network's templates are copied into its own repository when it is first used, and a copy is
never overwritten by the tool: a template you changed on purpose must survive. So a fix shipped
in the templates later does not reach the network by itself. **Templates** says, for each file,
how the network's copy stands against the shipped one, and where the copy is an older shipped
version that nobody edited, it offers **Bring in the shipped version…** on its row. Nothing is
sent to any device.

![Bringing in a shipped template: the network's copy is compared with the shipped file and offered only when it is an older shipped version, unedited; every device bound to a template that imports it is rendered both ways and what its render gains and loses is shown; you confirm, bound to both files; the file is written, every approval over it revoked, and both committed as you. No device is contacted.](diagrams/bring-template.svg)

## The states

- **Current**: the network's copy is the shipped file. Nothing to do.
- **Behind**: an older shipped version, unedited. The shipped file changed since; bringing it
  in loses nothing local, so it is one action.
- **Edited**: changed here on purpose, and the shipped file has not moved since. Not a problem.
- **Edited and behind**: changed here AND the shipped file moved since. A merge a person makes;
  named, and never offered as one action.
- A file the tool does not ship is the network's own, and is not compared.

A shared macro file (`_common.j2`) has its own row: it has no approval of its own, and the
templates that import it carry the approval that covers it.

## The steps

1. `compare`: the network's copy against the shipped file. Read: the copy in the network's
   library, and every shipped version of the file in the application's history. Sent: nothing.
   Recorded: nothing. The card shows the lines the shipped file adds and removes.
2. `measure`: every device bound to a template that imports the file is rendered through the
   library as it is and with the shipped file in its place. Read: each device's committed intent
   with the network's profile, and its stored secrets in memory. Sent: nothing. Recorded:
   nothing. The card says how many devices change, and what each one's render gains and loses,
   masked; a device that cannot be measured is named with why.
3. `confirm`: you confirm, as yourself. If the network's copy or the shipped file changed since
   the card showed them, or the copy is no longer behind, nothing is written and the card says
   what moved, naming both versions.
4. `write`: the shipped file is written over the network's copy.
5. `revoke`: the approval of every template that imports the file is revoked, with the reason
   "brought to the shipped version". No deploy renders through them until a person approves
   again, with Approve… on each row (see [Approve a template](approve-template)).
6. `commit`: the file and the revocations in one commit, as you.

## Then

Approve each template again. The devices are then planned against the new file: Monitoring ›
Coverage shows what each device lacks, and Apply sends it. The template never sends anything
itself.
