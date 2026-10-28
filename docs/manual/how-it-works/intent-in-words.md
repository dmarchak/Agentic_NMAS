# Change it in words

On a device's **Intent** tab, **Change it in words** takes a change as you would say it
("describe GigabitEthernet3 as core uplink to edge1 and shut GigabitEthernet4") and drafts it as a
change to that device's committed intent. The draft is shown in the intent editor's own
preview: what it changes, what a deploy would send, and the editor's checks, exactly as for an
edit you type. Nothing is written, and nothing reaches the device.

Nothing is written until you commit the draft: **Commit this draft** commits it to the
device's intent as you, and **Commit and plan deploy** commits it and opens the deploy preview,
where you still confirm the deploy by its hash. **Discard draft** drops it; a draft lives on
the page only.

It makes one call to a hosted model (Anthropic's, the model named in the button's hover),
through {{product}}'s AI gateway: allowed only once hosted AI is allowed on **Settings ›
Installation › AI (hosted)**, capped, and recorded with who asked. The row carries the **AI**
mark; when hosted AI cannot answer, the box and **Draft the change** are disabled, the reason
is written under them, and **Edit** stays as usable as ever (see
[The AI mark](installation-settings#ai-mark)).

![Change it in words: quoted text is held back as placeholders, and the device and the interfaces, VLANs and networks the sentence names are read by code, a sentence naming none or leaving a quote open stopping there with nothing sent; the names as people say them (G1/0, the host port, the uplink to edge1) are resolved by code against the device's intent and neighbours, several matches and alternatives asked about with controls that continue the draft, both ends of a link made one draft of both devices, and a change no operation makes refused, before any call; one recorded, capped call through the AI gateway carries only the resolved parts' current values and the keys a change may set, and answers with a patch; the patch is refused before any preview if it changes what the sentence did not name or misuses a placeholder, and the quoted text is put back; the intent editor previews it, its diff and what a deploy would send; nothing is written and no device is asked.](diagrams/intent-in-words.svg)

## Naming an interface as you would say it {#names}

You can name an interface the way people do, and {{product}} resolves it by code, against the
device's committed intent and its neighbours, before anything is sent. The model is only ever
given the device's own names, and the draft lists how your words were read.

- **Shorthand:** G1/0, Gi1/0, gi1/0, Gig1/0 or GigabitEthernet 1/0, as the device's own CLI
  reads them; Te, Fa, Po, Lo, Vl and Tu likewise. Only a name the device holds is resolved.
- **The host port(s):** an access port, enabled in intent, with no managed neighbour. This is
  read from the port's role, never its description; a shut access port is not one unless you
  name it.
- **The port to desk7:** a device of the network, by its neighbour; an endpoint, first where
  {{product}} observed it (the endpoint layer: a switch's MAC table on an access port, named
  by its DHCP lease, with when it was last seen there), and otherwise the port whose
  description names desk7 as a whole word (desk7 never matches desk70). When the observation
  and a description disagree, the observation is used and the draft says "drift". A host that
  has been idle for longer than the switch remembers MACs (minutes) is located only by where
  it was last seen. The draft says it was matched
  by description, because a description can be out of date.
- **The uplink(s):** ports toward a router or the management path; "the uplink to edge1"
  toward edge1. **The trunk(s):** trunk ports. **The VLAN 10 ports:** access ports in VLAN 10. A
  reference means a port, never an SVI, loopback or tunnel.
- "Host ports", "all uplinks", "both trunks": every match. One match is used. Several, when you
  said one, and {{product}} asks which before any call, each candidate named by its neighbour or
  description, with **Both** or **All N**; your choice continues the same draft. None, or a name
  the device does not hold: {{product}} says so and lists the device's interfaces to choose
  from, with a link to its neighbours.
- **Only a definite reference is read:** "the trunk", "that uplink", "all host ports", "the port
  to edge1", or the device's own name as a possessive on its tab ("edge2's trunk" on edge2).
  "A trunk", "an access port", "as a trunk", "to a routed port" describe the state you want,
  never a port, and stay as your words.
- A description's own words ("set Gi0/2's description to uplink to edge1", "set the description
  of Gi0/1 to uplink to edge1", "describe Gi0/1 as the trunk to edge2") are never resolved.

## Quoted text {#quotes}

Text you put in quotes is kept exactly and never read as anything but a value: {{product}}
takes it out before anything else reads your sentence, and the model is sent a placeholder
(`<<text_1>>`, `<<text_2>>`, in order) in its place, never the text itself. After the draft is
checked, the placeholders are put back with your exact text, so the draft, its preview and the
commit carry what you typed. Words inside quotes never name an interface, a VLAN or a device,
and never widen what the change may touch.

- Straight and curly double quotes ("…", “…”) always count. Single quotes ('…', ‘…’) count only
  where they cannot be an apostrophe: "Gi0/2's" and "don't" are never quotes.
- The first quote opens and its own kind closes; other quotes inside are part of the text
  (“spare for 'rack 4'” keeps 'rack 4').
- A quote left open, or text shaped like `<<text_1>>` outside quotes, is asked about before any
  call: close the quote, or put the text in quotes.
- A draft that leaves out a quoted text, uses a placeholder your sentence does not have, or puts
  one where only a name or a number belongs (an interface, a prefix, an area) is refused at
  `check`, naming it. History keeps the request and answer as sent (with the placeholders), and
  says what each placeholder stood for.

## Your words are masked before they leave {#typed-masked}

The rest of your sentence, outside quotes, is masked by the AI gateway before it is sent, as
on Ask in words (see [Your words are masked before they leave](ask-in-words#typed-masked)):
a value in a secret's place in a configuration line (an SNMP community, a password or
secret, a key string, a TACACS or RADIUS key, a pre-shared key, an authentication key,
SNMPv3's keys, a password hash, a URL's user and password, an encrypted secret), and any
credential {{product}} holds, wherever it appears. Interface names, VLANs, prefixes and
addresses (IPv4 and IPv6) go as you typed them, and a sentence with nothing to mask is sent
as typed.

When something was masked, a note under the row says what, in words, never the value: "1 value
was masked before sending: a pre-shared key. The model read a placeholder in its place, and
the value never left Mercury." The box, and **Why, in one line** that starts from it, then
hold your sentence as it was sent, each masked value as its placeholder, so the value is
neither drawn back on the page nor carried into a commit's line by default. The call's
record holds the masked sentence only; **History** draws the request as it was sent. Quoted text never leaves the host at
all, so it is not masked: it is put back exactly into the draft. A secret does not belong in
a description: leave it out of your words, quoted or not.

## When {{product}} asks or refuses before any call {#before}

Where code can tell the words leave a choice only you can make, or ask for a change the
operations do not make, {{product}} answers itself: no call, nothing spent, and never a choice
made for you. Each question is answered with its own controls (buttons, or a field and
**Continue**), each busy on itself; your answer continues the same draft with no retyping, and
the sentence as decided is shown above what comes next. **Cancel** leaves nothing drafted.

- **Alternatives** ("VLAN 40 or 41, whichever is free", "Gi0/1 or Gi0/2"): each is said with
  what the committed intent holds of it, and for a VLAN to add or remove, which of them can be.
  Each one that can is a button (when only one can, the question says so and it is the one
  button: the choice is still yours); two interfaces are buttons with their state, and **Both**.
- **An OSPF network to add with no area:** the device's processes and areas are said; each area
  is a button, and **Another area** takes a number or a dotted area (checked before it is used).
- **A description to set with no text** ("set a description on Gi0/1"): its current one is
  said; you type the text, and it reaches the model as a placeholder, never as words to follow.
- **A change no operation makes:** an interface made a trunk, an access port or a routed port,
  its access VLAN or allowed VLANs, its MTU, speed or duplex, a static route, an OSPF cost. It
  is refused naming the operations there are; make it with **Edit**. A word inside a
  description ("describe Gi0/1 as trunk to edge2") never counts. Anything else outside the
  operations (an address, a hostname) is the model's to refuse.

## Both ends of a link {#both-ends}

"Describe both ends of the link to edge2 as core" asks for a change on two devices. When the far
end is a device of the network and the network model or the Topology read names the link (from
either end), it is **one draft holding both devices' changes**, drawn side by side: the sentence
the model is given names both ends ("edge1 GigabitEthernet4 and edge2 GigabitEthernet4"), and each
device may change only its own end. A draft that changes one end only is refused: never half a
change.

Before the draft is offered, {{product}} compares the two ends in committed intent with the two
ends the draft would leave: a trunk's allowed and native VLANs, a tunnel's source, destination
and addressing, the OSPF area (OSPFv3's too) and the OSPF authentication type. A mismatch the
draft creates, or one whose values it changes, is refused, naming both ends' values, and
nothing is offered to commit. A mismatch already in committed intent that the draft leaves as
it is does not stop it: it is said beside the draft ("…, already in committed intent; this
change does not touch it"). When the draft changes the same link's trunk, tunnel, OSPF or
OSPFv3 settings as that mismatch, it says **This change may fail** instead, naming the
mismatch: the change is made on a link the mismatch already breaks. The draft says what the
ends share.

**Commit both devices' intent** makes one commit holding both devices' changes, as you, with
your one line: refused, writing nothing, if either device's intent moved since the draft, or if
what is handed to it is not the pair the AI call drafted (either end alone included), or if the
link the draft was made for does not name the two devices. Nothing is sent. Its answer offers
**Deploy both ends…**, which opens the plan for both devices, both ticked, as one change across
the link: one preview, one confirm by hash; then verify reads the link itself, and if either end
fails, or the link does, both are rolled back (see
[the paired deploy](deploy#the-paired-deploy)).

When the far end is not a device {{product}} manages (a host), or no read names what the port
links to, {{product}} asks first: **Draft <device>'s end only**, or, when the far end is unknown,
the device at the far end as a button.
- **A change no operation makes:** an interface made a trunk, an access port or a routed port,
  its access VLAN or allowed VLANs, its MTU, speed or duplex, a static route, an OSPF cost. It
  is refused naming the operations there are; make it with **Edit**. A word inside a
  description ("describe Gi0/1 as trunk to edge2") never counts. Anything else outside the
  operations (an address, a hostname) is the model's to refuse.

## What it can change {#what}

Four kinds of change, the same four a typed patch can make:

- an interface's description, set (the whole new text) or cleared;
- an interface shut down, or brought up;
- a VLAN added (with a name, or none) or removed; added only on a device with a VLAN database
  (see [A VLAN needs a VLAN database](#vlan-database));
- an OSPF network statement added or removed, by its IPv4 prefix, process and area.

Anything else (an address, a speed, a route, a hostname) is refused, saying why; make it with
**Edit**. An OSPF network is OSPFv2's, IPv4 only: an IPv6 prefix is refused by name.

## A VLAN needs a VLAN database {#vlan-database}

A `vlan <N>` line creates a VLAN only on a device with a VLAN database, a switch. A router's
intent holds an empty list of VLANs just as a switch's can, so the intent alone cannot tell
them apart. {{product}} adds a VLAN only where a VLAN database is known, and otherwise refuses
the draft at `preview`, with nothing previewed, saying where the answer came from:

1. **Declared**, by the device's platform and device type: {{product}}'s platform table names
   device types with and without a VLAN database (a Catalyst 8000V, a virtual router, has
   none), keyed by the device type as NetBox names it (its model). A device type the table
   does not name is not declared.
2. **Else measured**: the device's own answer to `show vlan id 1`, run on it through
   [Show commands](show-commands), or **Ask the device** on its page, and kept with its time.
   A device that lists VLAN 1 has a VLAN database; one that refuses the command
   (`% Invalid input detected`) has none; any other answer counts as no answer. The newest
   readable answer counts, and an answer from before the device's name was last retired or
   onboarded belongs to an earlier device, so it does not count.
3. **Else unknown**, and the VLAN is refused: "whether *device* (*platform*, device type
   *type*) has a VLAN database is not declared and not measured: run `show vlan id 1` on
   *device* (Show commands, or Ask the device on its page) to measure it", followed by what
   the device type would answer: with none named, "or name its device type in NetBox, by
   which Mercury's platform table declares a VLAN database (none is named)"; with one named,
   that the table declares nothing for it.

It is never judged from a device's name or its role: a device named or classed as a switch
gets no VLAN without a declaration or a measurement. The answer is read from what is stored
when you draft and once when you commit; no device is asked by the draft. Removing a VLAN
needs none of this: it takes the line out of intent, and a merge-only deploy sends nothing for
it. The same check, in the same words, holds wherever intent is written: the
[intent editor](edit-intent)'s commit and [Bulk intent](bulk-intent) refuse a VLAN they would
add on such a device too.

## The steps {#steps}

1. `quote`: the text you quoted is taken out and a placeholder put in its place, before
   anything else reads the sentence (see [Quoted text](#quotes)); a quote left open stops here,
   with nothing sent.
2. `scope`: on a device's tab the change is that device's alone. Another device's name in your
   sentence is only words (a description may name a neighbour, "uplink to edge2"); a draft
   that changes that device is refused at `check`, naming it. {{product}} then reads, by
   code, what the sentence names: interfaces in any of their written forms (Gi0/1,
   GigabitEthernet 0/1), VLANs after the word "vlan" ("Vlan10" is an interface), and network
   prefixes (an address with a wildcard or mask is read as its prefix). A sentence naming no
   interface, VLAN or network stops here too: nothing is sent, nothing is spent, and
   {{product}} asks you to name what to change.
3. `screen`: a change no operation makes is refused, and on a device's tab alternatives, an OSPF
   network with no area and a description with no text are asked about, each before any call
   and answered with controls that continue the draft (see
   [When {{product}} asks or refuses before any call](#before)). Both ends of a link to a device
   of the network become one draft of both devices' changes, and a far end that is not one is
   asked about (see [Both ends of a link](#both-ends)).
4. `resolve`: the names as you said them are resolved by code (see
   [Naming an interface as you would say it](#names)): shorthand to the device's own name, and
   a reference to the ports it means. Several matches ask which, and none says so with the
   device's interfaces, both before any call; the sentence the model is given holds the
   resolved names only.
5. `ask`: one call through the AI gateway, as you. What leaves the host is your sentence (any
   quoted text as its placeholder only, and any secret in it masked: see
   [Your words are masked before they leave](#typed-masked)), the keys a change may set, and the CURRENT VALUES of only the parts of the device's intent your
   sentence names (each named interface's description and whether it is shut, each named
   VLAN's name, each named network statement with its area and process), with the device's
   platform and role, and what you named that the device does not hold. Never the intent
   document, never any other part of it, never an address, an account or a secret reference.
   The answer must be a draft in a fixed shape, one question back when your words leave a
   choice only you can make, or a refusal saying why.
6. `check`: before any preview, a draft that changes anything your sentence did not name (an
   interface, a VLAN, a network, another device) is refused, naming it, and so is one that
   leaves out, invents or misplaces a placeholder. Your quoted text is then put back exactly,
   and the change's own rules hold, as for a typed change: a printable description of at most 240 characters, a VLAN
   the device may create, a network with its host bits clear.
7. `preview`: the intent editor previews the draft against the committed intent: an interface,
   VLAN or process the intent does not hold is refused, naming both, and so is a VLAN added to
   a device with no VLAN database, declared or measured (see
   [A VLAN needs a VLAN database](#vlan-database)); otherwise you see the
   changes in words, what they change in the device's configuration, what a deploy would send,
   and the editor's checks. A removal a merge-only deploy would not carry is said, as for an
   edit. A draft that changes no line of the configuration (an interface already up) says
   "Already so" and offers no commit.
8. `commit`: you commit the draft, with a one-line reason that starts from your words. It is
   committed exactly as drafted: {{product}} refuses it, writing nothing, if the device's intent
   moved since the draft, or if what is handed to the commit is not the patch the AI call
   drafted on that version. The commit is yours (its Actor), its Source is `ai-draft`, and its
   `AI-Call:` names the call, so History links the call and the commit both ways. **Commit and
   plan deploy** opens the deploy preview next; the deploy is unchanged from there (preview,
   confirm by hash, apply, verify, roll back on failure), and nothing is confirmed for you. A
   draft of both ends of a link is committed as one commit holding both devices' changes, and
   each device is then deployed from its own page.

## What it costs, and what is recorded {#cost}

Each call is priced at the pinned model's rates and refused before it is sent if its worst
case would cross the task's per-call cap or the day's cap. Every call is a row in **History**:
who asked, the device, the masked request and the answer (opened in place with **Show the
prompt and the answer**), its verdict, its tokens and its cost, and what became of the draft.
