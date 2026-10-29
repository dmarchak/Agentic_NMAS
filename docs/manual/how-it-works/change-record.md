# A change record drafted from the deploy preview

On a device's **Deploy** preview, between **Checks** and the confirm, **Draft a change record**
drafts a change record and rollback plan for the program the preview shows, in a change board's
format: Summary, Scope, Risk, Implementation, Verification, Rollback plan, Window and approver,
and Status. You copy it as text or download it (.md) for your change board or ticket. It is a
draft, labelled **DRAFT by AI** and **Advisory (beta)**, and it is not reviewed by anyone until
you read it.

![A change record drafted from the deploy preview. You press Draft a change record; Mercury plans the preview again from the card's own form and refuses if its program is not the one the card drew; it fills every fact code knows (the program and its hash, the stated reasons, Verify's scope and checks, the rollback's lines as the pipeline computes them, the risk's level by its rule); it sends one recorded, capped call through the AI gateway carrying the program's shape in keywords and Mercury's own words, never a configuration value; it refuses words naming an interface or device the change does not hold; and it draws the draft in the preview, each section marked Mercury or AI. Nothing is sent to the device, and Deploy is unchanged.](diagrams/change-record.svg)

**Its effect on Mercury's checks: neither stricter nor looser.** It is a document. The program
and the preview stay what you confirm: the confirm never reads the draft, and **Deploy** is the
same button, bound to the same program hash, with or without one. It never commits, deploys or
approves anything.

**Mercury writes the facts; the model writes the words around them.** Every section a fact
fills is marked **Mercury**: the device and its interfaces, the program's lines exactly as the
preview draws them (copied from the program, never from the model), its hash, your stated
reasons, what Verify checks, and the rollback plan, computed from the program and the device's
captured configuration by the same function the pipeline's rollback runs. The risk's level is
Mercury's, by a stated rule: **high** when an adjacency is expected to drop or a line is removed
(Mode B), **medium** when a line needs a stated reason, an interface is shut or a routing
protocol is touched, **low** otherwise. Only the **Summary** and the Risk's reading are the
model's, marked **AI**. **Window and approver** are left for you: Mercury does not know them.

It makes one call to a hosted model (Anthropic's, the model named in the button's hover),
through {{product}}'s AI gateway, as you (trigger person): allowed only once hosted AI is
allowed on **Settings › Installation › AI (hosted)**, capped, and recorded with who asked. The
control carries the **AI** mark; when hosted AI cannot answer, it is disabled with the reason
written beside it, and the preview and **Deploy** are as usable as ever (see
[The AI mark](installation-settings#ai-mark)). It is never a background feature.

## What leaves the host {#what-leaves}

**No configuration value, and no line but its leading keywords.** A deploy's program is
configuration, which does not leave the host, so the model is sent the program's shape in
{{product}}'s own words:

- each section the program touches, an interface by its name (GigabitEthernet2) and any other
  section by at most two leading keywords (router ospf, ntp server);
- what each line sets, by at most two leading keywords (ipv6 ospf, shutdown, description),
  never its value: a word holding a digit, a capital, a dot, a colon or a slash ends the
  keywords, and a free-text command (a description, a banner) keeps its first word only;
- a line that would be masked on its way out (a secret's position or shape) left out whole,
  only counted;
- the device and its platform, Verify's scope, the preview's derived effects and verify checks
  in the preview's own words, the counts, and Mercury's risk level.

Your stated reasons are never sent. Interfaces and adjacencies are the topology class, so the
call is made only where the network's topology class is on (an admin's setting, on by default);
where it is off, nothing is sent and the draft says why. The AI gateway's egress mask covers
every byte as for every call.

## Draft a change record {#draft}

The control is drawn on a preview with a program to send. **Draft a change record** reads
"Drafting…" until the draft is drawn in place.

1. `plan`: the preview is planned again from the card's own form: the reasons you typed and the
   lines you ticked, exactly as the card draws it. Read: committed intent and the device's
   captured configuration. If its program is not the one the card drew, nothing is sent, and
   the refusal names both program hashes.
2. `facts`: Mercury fills every fact code knows: the program and its hash, your stated reasons,
   Verify's scope and checks, the rollback's lines and the risk's level by its rule. Read: the
   plan, the captured configuration, the device's golden now. Sent: nothing.
3. `shape`: what is sent is built from the facts: the program's shape in keywords, never a
   value (see [What leaves the host](change-record#what-leaves)). Where the network's topology
   class is off, nothing is sent.
4. `ask`: one recorded, capped call through the AI gateway, as you. Recorded: the call, with
   the preview's facts as its subject (masked), in the record of AI calls.
5. `check`: the words are refused, never drawn, when they name an interface the program does
   not touch, another device of the network, or quote a configuration line: "Couldn't draft:
   the answer named GigabitEthernet3, which the program does not touch." The call stays in
   History.
6. `draw`: the draft is drawn in the preview, each section marked Mercury or AI, with who asked,
   the model and the call's cost, and a link to the call in History. **Deploy** below is
   unchanged.

## A draft that no longer matches {#stale}

The draft is for the program it names. When the preview is planned again and its program hash
moves (you type a reason, tick a line for removal, or intent moves), the draft stays, marked:
"This draft is for program e81f07c2; the preview now is 7a01c9d4. Its Implementation and
Rollback plan no longer match." It is drafted again only when you press **Draft again**; until
then the old draft is shown muted under that notice. Planning the preview again brings the draft
back with it, read from its call: nothing on the page is trusted to redraw it.

## Copy, download, and the call {#copy}

**Copy as text** copies the whole draft, every section and its source; **Download (.md)** saves
the same text, read from the call's record. **Draft again** makes a new call. Under the draft,
**Was this right?** records whether it was right (see
[Was this right?](ai-feedback#answer)). The call, its request as it left the host and its
answer are in **History**, on the device's tab and the fleet's, opened in place.

## How it was measured {#measured}

It is labelled **Advisory (beta)** until its recorded cases are measured on the pinned model
(the deploy previews of real captured configurations, each with what the draft must say and
must never say, graded by code). Until then, read every word against the preview above it.
