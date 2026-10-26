# Change it in words

On a device's **Intent** tab, **Change it in words** takes a change as you would say it
("describe GigabitEthernet3 as core uplink to edge1 and shut GigabitEthernet4") and drafts it as a
change to that device's committed intent. The draft is shown in the intent editor's own
preview: what it changes, what a deploy would send, and the editor's checks, exactly as for an
edit you type. Nothing is written, and nothing reaches the device.

The draft is not committed yet: committing a drafted change is the next step of this feature.
To make the change now, press **Edit** and make it in the document by hand; the draft shows
you the lines.

It makes one call to a hosted model (Anthropic's, the model named in the button's hover),
through {{product}}'s AI gateway: allowed only once hosted AI is allowed on **Settings ›
Installation › AI (hosted)**, capped, and recorded with who asked. The row carries the **AI**
mark; when hosted AI cannot answer, the box and **Draft the change** are disabled, the reason
is written under them, and **Edit** stays as usable as ever (see
[The AI mark](installation-settings#ai-mark)).

![Change it in words: the device and the interfaces, VLANs and networks the sentence names are read by code, and a sentence naming none stops there with nothing sent; one recorded, capped call through the AI gateway carries only those parts' current values and the keys a change may set, and answers with a patch; the patch is refused before any preview if it changes what the sentence did not name; the intent editor previews it, its diff and what a deploy would send; nothing is written and no device is asked.](diagrams/intent-in-words.svg)

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
   interface, VLAN or network ("shut the uplink") stops here too: nothing is sent, nothing is
   spent, and {{product}} asks you to name what to change.
2. `ask`: one call through the AI gateway, as you. What leaves the host is your sentence, the
   keys a change may set, and the CURRENT VALUES of only the parts of the device's intent your
   sentence names (each named interface's description and whether it is shut, each named
   VLAN's name, each named network statement with its area and process), with the device's
   platform and role, and what you named that the device does not hold. Never the intent
   document, never any other part of it, never an address, an account or a secret reference.
   The answer must be a draft in a fixed shape, one question back when your words leave a
   choice only you can make, or a refusal saying why.
3. `check`: before any preview, a draft that changes anything your sentence did not name (an
   interface, a VLAN, a network, another device) is refused, naming it. The change's own rules
   then hold, as for a typed change: a printable description of at most 240 characters, a VLAN
   the device may create, a network with its host bits clear.
4. `preview`: the intent editor previews the draft against the committed intent: an interface,
   VLAN or process the intent does not hold is refused, naming both; otherwise you see the
   changes in words, what they change in the device's configuration, what a deploy would send,
   and the editor's checks. A removal a merge-only deploy would not carry is said, as for an
   edit.

## What it costs, and what is recorded {#cost}

Each call is priced at the pinned model's rates and refused before it is sent if its worst
case would cross the task's per-call cap or the day's cap. Every call is a row in **History**:
who asked, the device, the masked request and the answer (opened in place with **Show the
prompt and the answer**), its verdict, its tokens and its cost, and what became of the draft.
