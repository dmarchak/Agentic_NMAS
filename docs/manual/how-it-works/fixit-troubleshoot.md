# AI troubleshooting: Retry, Cancel and Hand over

An incident's page ([An incident's page](incident)) has an **AI troubleshooting** section. It
lists every fix tried in the incident, says what each one cost in AI, and offers what a person
may do next. This first version makes no AI call: **Retry with more information** asks
Mercury's own diagnosis to plan again. The AI's own call comes in a later version, behind the
same controls and the same cap.

![AI troubleshooting on an incident's page, with no AI call yet: an attempt is a catalogue operation's run on the incident's device, read from the operation's own record; a failed attempt stops the section, and nothing more runs until a person chooses. Retry with more information asks the per-incident cap again at the press, then Mercury's own diagnosis names its fix as one catalogue operation, checked against the incident, the heal guards and committed intent, and kept as one proposal line with the person's note; a proposal that repeats a failed attempt is flagged. The fix runs only through its operation's own card, previewed and confirmed by hash, and its run's record names the incident, the attempt and the proposal. Cancel and Hand over each record one line, and Hand over keeps a write-up and sends its link to the teams chosen. Nothing in the section reaches the device but the operation a person confirmed.](diagrams/fixit-troubleshoot.svg)

## The attempts {#attempts}

An **attempt** is a run of one of Mercury's catalogue operations (Re-subscribe a device's
telemetry, or Re-add a receiver a run left removed) on the incident's device, started after the
incident was detected. Each one is read from the operation's own record every time the page is
drawn, so its outcome is the operation's words. A run started from the section's proposal also
names the incident in its record, and is that incident's attempt whatever its time.

Each attempt is one line: when it ran, the operation and its parameters, who proposed it (when
it came from a proposal here) and who approved it, its outcome, its AI cost, and **Open the
run**, which opens the run's own card with its steps and verify reads.

The section's first line says what this incident's AI calls have cost against its cap, and
today's spend against the day cap. Both are summed from the record of AI calls each time.

## A failed attempt stops {#the-stop}

When the newest attempt did not pass its verify, the section **stops**: it says what the run
found, from the run's own record, and "Nothing more runs unless you choose." No page load, no
refresh and no announcement starts another attempt or asks for another plan. The choices are
Retry with more information, Cancel and Hand over.

## Retry with more information {#retry}

Retry has a box for what you know that Mercury doesn't. Mercury's diagnosis does not read
words: they are kept with the retry, for the hand-over and for the AI once it is built. Before
you press, the panel shows what the retry costs, what the incident has spent, what it would
have spent at most afterwards against its cap, and today's spend. It also lists what the AI
would be sent once it is asked.

Pressing **Ask Mercury's diagnosis to re-plan** runs these steps:

1. `person`: the press is a verified person's, or it is refused with nothing recorded.
2. `cap`: the per-incident cap is asked again ([the cap](#the-cap)). Past it, the press is
   refused, naming both figures and what moved since the panel was drawn, and Mercury's
   diagnosis is not asked.
3. `propose`: Mercury's own diagnosis of the incident (the newest one attached to it) names its
   next step as one catalogue operation, with its parameters. A diagnosis whose next step is no
   catalogue operation, or no diagnosis at all, names none, and says why.
4. `check`: the proposal is checked by code against the catalogue's schema, against what the
   incident names (its device and its lost subscriptions), against the heal guards (a planned
   window, the device held by another run) and against committed intent.
5. `record`: one proposal line is kept in the incident's troubleshooting record, with the
   operation and its parameters (or why there is none), who pressed, and the note.

Nothing runs. The proposal is drawn with **Open the fix's card…**, which opens the operation's
own card in the section: its program, its hash and your reason, exactly as everywhere else. The
fix runs only when you confirm it there.

## A repeated proposal is flagged {#a-repeat}

A proposal is compared with every attempt in the incident that did not pass. The same operation
with the same parameters is drawn "Proposed before in this incident: attempt N, failed: …", with
its time and its parameter hash. Its card then asks **what is different now**, at least three
words, and refuses the confirm without it. The same operation with other parameters is drawn as
a variation, naming each parameter that changed. A repeat is never hidden.

## The run's record {#the-run}

A fix confirmed from the section's proposal writes the incident's id, the attempt's number and
the proposal's id into its run's record, with what is different now for a repeat. The attempt's
line then says who proposed it, and the incident's list can tell later how it was fixed.

## The per-incident cap {#the-cap}

**AI spend per incident** (Settings › Installation › AI, the AI troubleshooting card, $1.00 by
default) holds every attempt: what the incident's AI calls have cost so far plus the next
attempt's worst case is compared with it. At the cap exactly is allowed; past it, Retry is not
offered and the section says spent, the worst case, their sum and the cap. A retry's worst case
is two calls at the per-call cap of the AI's pinned model (at most $0.25 today), even though
this version's retry calls no AI. There is no "no cap", and Mercury never raises it. **AI mode**
on the same card is Manual (an AI troubleshoot only on a person's press) or Off.

## Cancel {#cancel}

**Cancel** records one line: who cancelled, when, and the attempts and AI spend as they stood.
It runs nothing, sends nothing and holds no device. The incident stays open at its page, and the
section reads "Troubleshooting cancelled at <time> by <name>". A later Retry ends the cancelled
state.

## Hand over {#hand-over}

**Hand over…** builds a write-up for an engineer from the incident's records, with no AI: its
summary, the impact now, what Mercury knows, what was tried, what the AI said (or that no AI was
asked), the configuration now, the next steps, the notes and the cost. People are named by
display name and teams by name; no email address and no secret is in it. Each hand-over is kept
as a new version, never written over, on its own page, linked from the section and from the
incident's record, with Download as Markdown. **Send the hand-over** sends it to the teams you
tick, each one of the teams told about the network's can't-fix (Settings › Notifications); with
none ticked it is kept and sent to nobody. A send that fails says so, with **Send again**. Once
the incident is resolved, the section is read-only: a Cancel, Retry or Hand over sent to it then
is refused, with nothing recorded.
