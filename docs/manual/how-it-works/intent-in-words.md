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

![Change it in words: the device and the interfaces, VLANs and networks the sentence names are read by code, and a sentence naming none stops there with nothing sent; the names as people say them (G1/0, the host port, the uplink to edge1) are resolved by code against the device's intent and neighbours, several matches asking which and none saying so, before any call; one recorded, capped call through the AI gateway carries only the resolved parts' current values and the keys a change may set, and answers with a patch; the patch is refused before any preview if it changes what the sentence did not name; the intent editor previews it, its diff and what a deploy would send; nothing is written and no device is asked.](diagrams/intent-in-words.svg)

## Naming an interface as you would say it {#names}

You can name an interface the way people do, and {{product}} resolves it by code, against the
device's committed intent and its neighbours, before anything is sent. The model is only ever
given the device's own names, and the draft lists how your words were read.

- **Shorthand:** G1/0, Gi1/0, gi1/0, Gig1/0 or GigabitEthernet 1/0, as the device's own CLI
  reads them; Te, Fa, Po, Lo, Vl and Tu likewise. Only a name the device holds is resolved.
- **The host port(s):** an access port, enabled in intent, with no managed neighbour. This is
  read from the port's role, never its description; a shut access port is not one unless you
  name it.
- **The port to desk7:** a device of the network, by its neighbour; otherwise the port whose
  description names desk7 as a whole word (desk7 never matches desk70). The draft says it was matched
  by description, because a description can be out of date.
- **The uplink(s):** ports toward a router or the management path; "the uplink to edge1"
  toward edge1. **The trunk(s):** trunk ports. **The VLAN 10 ports:** access ports in VLAN 10. A
  reference means a port, never an SVI, loopback or tunnel.
- "Host ports", "all uplinks", "both trunks": every match. One match is used. Several, when you
  said one, and {{product}} asks which before any call, each candidate named by its neighbour or
  description, with **Both** or **All N**; your choice continues the same draft. None, or a name
  the device does not hold: {{product}} says so and lists the device's interfaces to choose
  from, with a link to its neighbours.
- A description's own words ("set Gi0/2's description to uplink to edge1") are never resolved.

## What it can change {#what}

Four kinds of change, the same four a typed patch can make:

- an interface's description, set (the whole new text) or cleared;
- an interface shut down, or brought up;
- a VLAN added (with a name, or none) or removed;
- an OSPF network statement added or removed, by its IPv4 prefix, process and area.

Anything else (an address, a speed, a route, a hostname) is refused, saying why; make it with
**Edit**. An OSPF network is OSPFv2's, IPv4 only: an IPv6 prefix is refused by name.

## The steps {#steps}

1. `scope`: on a device's tab the change is that device's alone. Another device's name in your
   sentence is only words (a description may name a neighbour, "uplink to edge2"); a draft
   that changes that device is refused at `check`, naming it. {{product}} then reads, by
   code, what the sentence names: interfaces in any of their written forms (Gi0/1,
   GigabitEthernet 0/1), VLANs after the word "vlan" ("Vlan10" is an interface), and network
   prefixes (an address with a wildcard or mask is read as its prefix). A sentence naming no
   interface, VLAN or network stops here too: nothing is sent, nothing is spent, and
   {{product}} asks you to name what to change.
2. `resolve`: the names as you said them are resolved by code (see
   [Naming an interface as you would say it](#names)): shorthand to the device's own name, and
   a reference to the ports it means. Several matches ask which, and none says so with the
   device's interfaces, both before any call; the sentence the model is given holds the
   resolved names only.
3. `ask`: one call through the AI gateway, as you. What leaves the host is your sentence, the
   keys a change may set, and the CURRENT VALUES of only the parts of the device's intent your
   sentence names (each named interface's description and whether it is shut, each named
   VLAN's name, each named network statement with its area and process), with the device's
   platform and role, and what you named that the device does not hold. Never the intent
   document, never any other part of it, never an address, an account or a secret reference.
   The answer must be a draft in a fixed shape, one question back when your words leave a
   choice only you can make, or a refusal saying why.
4. `check`: before any preview, a draft that changes anything your sentence did not name (an
   interface, a VLAN, a network, another device) is refused, naming it. The change's own rules
   then hold, as for a typed change: a printable description of at most 240 characters, a VLAN
   the device may create, a network with its host bits clear.
5. `preview`: the intent editor previews the draft against the committed intent: an interface,
   VLAN or process the intent does not hold is refused, naming both; otherwise you see the
   changes in words, what they change in the device's configuration, what a deploy would send,
   and the editor's checks. A removal a merge-only deploy would not carry is said, as for an
   edit. A draft that changes no line of the configuration (an interface already up) says
   "Already so" and offers no commit.
6. `commit`: you commit the draft, with a one-line reason that starts from your words. It is
   committed exactly as drafted: {{product}} refuses it, writing nothing, if the device's intent
   moved since the draft, or if what is handed to the commit is not the patch the AI call
   drafted on that version. The commit is yours (its Actor), its Source is `ai-draft`, and its
   `AI-Call:` names the call, so History links the call and the commit both ways. **Commit and
   plan deploy** opens the deploy preview next; the deploy is unchanged from there (preview,
   confirm by hash, apply, verify, roll back on failure), and nothing is confirmed for you.

## What it costs, and what is recorded {#cost}

Each call is priced at the pinned model's rates and refused before it is sent if its worst
case would cross the task's per-call cap or the day's cap. Every call is a row in **History**:
who asked, the device, the masked request and the answer (opened in place with **Show the
prompt and the answer**), its verdict, its tokens and its cost, and what became of the draft.
