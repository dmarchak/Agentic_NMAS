# The assistant: how to do something, from the manual

The top bar's **AI Assistant**, after the AI chip, opens a panel on the right, in the help panel's
place: a conversation, like a chat. On a window wide enough, the page moves over to make room
for it, so nothing is under the panel and the page stays usable beside it; on a narrow one it
covers the page's right edge. Ask how to do something in {{product}}, or what {{product}} holds
about the device or incident you are looking at, in your own words, in the box at the foot of
the panel, and press **Send** (or Enter; Shift+Enter starts a new line, and the box grows with
your text up to eight lines). Your question appears at the foot of the conversation, and the
answer under it when it arrives; the conversation keeps itself at the newest answer unless you
have scrolled up to read. The answer rests on this manual's sections and on the reads
{{product}} ran for it, each linked. It is marked AI and labelled beta: a person should confirm
it (**About the assistant**, the ⓘ in the panel's head, says so in full). Esc or **Close the
assistant** (✕) closes the panel; it and the help panel take the same place, one at a time.
While the Assistant is off (**Settings › Installation › AI**, the Assistant card) the button is
greyed and disabled, and its hover says where it is turned on; while hosted AI is off it is
greyed, still opens, and **Send** says why.

**Its width is yours.** Drag the panel's left edge to make it wider or narrower, or focus the
edge and press the arrow keys: from 320 px to 60% of the window, so the page stays usable. The
width is kept in this browser only, never in {{product}}.

![The toolbar assistant's answer. You ask on any page; Mercury notes what you are looking at from the page's path (the screen, the network, the device and the incident), chooses the manual's passages for the question by code (below the floor, the manual's gap, and no call), and sends one recorded, capped call through the AI gateway, your question masked. When the answer asks for reads, Mercury runs them on the device in view only, each judged by its read-only check and recorded, then makes one more recorded call with their answers. It checks that every citation is a passage it sent or a read that ran, and draws the answer with its sources, the model and the cost, offering a hand-off to the gated flow for a change, or says the manual does not cover it and records the gap. Only reads reach a device; nothing is changed.](diagrams/assistant.svg)

**It never changes anything.** It answers how to do a thing, and where, and what the reads show;
it never changes, deploys, approves or saves anything, writes nothing to any source of truth,
and names no command to type into a device. A change you ask for is handed to its own gated
flow (below), where you preview and confirm it as ever. For a fact across the network use
**Ask in words** (History › Query).

**What NetBox reads send.** Only fixed fields are read (names, statuses, addresses, prefixes,
VLANs, sites, descriptions), never contacts, comments or custom fields; an email address, and
the display name of anyone Mercury knows, in a description becomes that person's label before
it is sent. A third party's name typed into a description, someone Mercury holds no display
name for, cannot be recognised as a name and is sent as typed.

## What it is looking at {#looking-at}

The panel's head says what it is looking at: **Looking at: edge1 (device) · Default** on a device's
page, the incident's id on an incident's, and the screen's name on any other page, then the
network. {{product}} works it out itself from the page's address, by its own map of its pages:
the screen, the network, the device and the incident. It changes as you move: another page, or
a tab of the same page. Each question is kept with the page it was asked on (under it, "on
edge1 (device) · Default"; the page's address on its hover). The reads are only ever of that device,
or of the incident's device; on any other page nothing is read (the chip's hover says which).

## How an answer is made {#answer}

1. `place`: what you are looking at is resolved from the page's address, as above.
2. `choose`: the manual's passages are chosen for your question by code, never by the model:
   a keyword ranking (BM25) over the manual's sections, a long section split into passages
   that keep its link; a maintained list of the words people use for what the manual says
   otherwise (host key and re-key, password and secret reference, reboot and reload); and a
   boost for the page of the screen you asked from. Below a floor (no passage scores enough,
   or the best meets too little of your question) no passage is sent; with nothing to read
   either, the answer is **The manual doesn't cover this.** and no call is made. The ranking
   reads your question with any secret masked out, so a pasted value never ranks the manual.
3. `ask`: one recorded, capped call through {{product}}'s AI gateway, as you (trigger
   person): the instructions, the list of screens, the plans and the reads it may ask for
   first, the same on every question and cached, then your question, what you are looking at
   and the passages. Your question is masked before it leaves: a value in a secret's place,
   and any credential {{product}} holds wherever it appears. The answer says what was masked,
   by its kind and never its value.
4. `read`: when your question is about the device in view, the answer may ask for up to three
   reads ([below](#reads)); {{product}} checks each, runs those it allows, and makes one more
   recorded call with their answers.
5. `check`: {{product}} checks the answer before it is drawn: every section it cites is one
   it was sent, every read it cites is one that ran, and every screen it names is one this
   manual names. An answer that fails is never drawn: **Couldn't answer:** says why, and the
   call is in History.
6. `draw`: the answer is drawn with its sources ([below](#sources)). When nothing covers your
   question, it says **The manual doesn't cover this.**, names the nearest sections it holds,
   and records the question as a gap in the manual. **Was this right?** under the answer
   records whether it was.

While it works, the conversation shows where it is, under your question: "Choosing the
manual's passages", "Asking the model", "Running the 2 reads it asked for", "Answering from the
reads (call 2)". The answer arrives whole, not word by word: {{product}} checks the whole answer
(its citations, its reads, its hand-off) before any of it is drawn, so the steps are drawn
instead. The work runs on {{product}}'s host, not in your page: changing page or refreshing
leaves it running, and the panel draws it where it got to. One question is answered at a time:
while one is, **Send** is **Stop**.

## Stop {#stop}

**Stop** stops the answer being made: the model's answer is closed at {{product}}'s next check
of it (from there it bills no more), and no call is made after it, so no new round of reads
starts. A round of device reads already running when you press it finishes its reads first.
What was already spent is recorded in History like any other call, each call marked as stopped
by the person who asked, and the question stays in the conversation, marked **Stopped by
you**, with its calls' links. Stop cannot take back the part of a call the provider has already
billed. While it is stopping, **Send** waits for it.

## The reads {#reads}

The reads are the same read-only tools a person has: the device's own reads by {{product}}'s
allowlist (show, a configuration form, ping and traceroute, as Show commands holds them whole)
and {{product}}'s reads of what it already holds about the device (its committed intent, its
golden configuration, its neighbours, History, logs and health figures). Each read goes through
{{product}}'s own tools: the allowlist and its checks (an address or interface must be the
device's), its reads engine, which holds the device while it reads and signs in as AI device
reads do, and the egress classes: while the device state class is off for the network (the
default, **Settings › AI**), nothing is read and the answer comes from the manual alone. Every
read is recorded: on History beside the calls, and a device read on History › Reads. A read's
answer is masked before it is sent, a line with a secret's shape withheld.

## Its sources, model, cost and calls {#sources}

An answer's words are drawn as {{product}} renders them: lists, code and tables, every character
the model wrote shown as text (a link it wrote is shown as its words, never followed). Under
them, its sources as small chips, each with **Open**: a manual passage opens its section, and a
read opens the device tab it came from (Intent, Overview for the golden, Neighbours, History,
Logs, Monitoring, or Ask the device for a device read). The reads it ran are one line, **Ran 2
reads**, closed; opened, it lists every read asked for, run, refused (with why) or failed, and
each read opens to its record on History › Reads. Last, one quiet line: the model that answered,
the cost, how long it took and each call's link in History (for example "Haiku 5.5 · $0.0031 ·
9 s · History").

## A change you ask for {#handoff}

When you ask {{product}} to change something, the answer says so and offers the gated flow that
does it, filled in and not started: **Change it in words…** opens the device's Intent tab with
its sentence box filled (you press **Draft the change**, preview and commit as ever), and on an
incident **Open AI troubleshooting** opens the incident's own AI troubleshooting card (you press
**Start AI troubleshooting** there). One of the plan engine's plans stays **Preview the plan…**.

## Your conversations {#thread}

Your questions and their answers stay in the panel as you move between pages and refresh:
{{product}} keeps your conversation, its newest 20 exchanges, yours alone, on its host.
Opening the panel, changing page and refreshing only read it; nothing is asked again. Whether
the panel is open is kept in this browser.

**New conversation**, in the panel's head, keeps the conversation you have under **Past
conversations** and starts another. **Past conversations** lists them, newest first, each with
its first question, when it was asked and how many exchanges it holds; **Reopen** makes one your
conversation again, and the one you had is kept in the list in its place. Nothing is deleted.
While a question is being answered, both wait for it (press **Stop**, or let it finish).

## A gap in the manual {#gaps}

A question the manual does not answer is recorded, masked, with the screen it was asked from
and who asked: for whoever keeps the manual. It is never a Needs attention row: nobody must act
on it now.

## The call {#call}

It makes one call to a hosted model (Anthropic's) for each press, and one more for each round of
reads, through {{product}}'s AI gateway, as you: allowed only once hosted AI is allowed on
**Settings › Installation › AI (hosted)**, capped, and recorded with who asked. No call is made
until you press **Send**. When hosted AI cannot answer, **Send** is disabled and the panel says
why; the manual stays yours to read under **Help**.
