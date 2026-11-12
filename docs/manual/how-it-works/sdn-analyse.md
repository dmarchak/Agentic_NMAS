# Analyse this network: what is abnormal in an SDN fabric

SDN › Flows' **Analyse this network** asks an AI model what is abnormal in one collection of the
network's live state: every switch's flow table and drop rules, its ports' rates and drops, and
whether each port and link is up. Every finding names the evidence it rests on, and Mercury
checks each one against the collection before it is shown. **Planted issues** compare what the
model found with problems you planted yourself, for an evaluation such as a lab's. Nothing is
sent to a switch: the analysis reads, and it changes nothing on the network.

![Analyse this network: Collect now runs a read job, never a page view, that reads every switch's flows, its port counters twice and its port descriptions, and the controller's links, through the controller's driver; the collection is kept as a snapshot under its own id, each fact with its evidence id, masked and sealed; Analyse sends that snapshot's facts and nothing else in one recorded, capped call through the AI gateway, while the topology class is allowed; the answer is parsed strictly and each finding's evidence held to the snapshot, a finding citing nothing it holds dropped and counted; each planted issue is marked found or missed by the evidence its findings cite. Nothing is sent to a switch.](diagrams/sdn-analyse.svg)

## The steps

1. `collect`: **Collect now** starts a read job on the network's controllers, through each
   connection's controller driver: every switch's flows, its port counters twice 5 seconds
   apart (so each port's rates are per second), its port descriptions, and the links the
   controller discovered. A port is down when the switch reports its LINK_DOWN state, never by
   its LIVE bit, which some switches leave clear on a working port. One collection runs at a
   time on a network: a second is refused, naming who started the first and until when, and
   never queued. It is bounded by the interval and the connections' timeouts; when it ends the
   page redraws. Opening the page never reads a controller.
2. `snapshot`: the collection is kept as a snapshot under its own id (`snap-` and 16 hex
   digits), each fact with its **evidence id**, masked as everything Mercury sends a model is,
   and sealed by its hash, so the same snapshot can be analysed again. A link an earlier
   snapshot discovered and this one does not is kept as **not discovered now**, with when it was
   last seen: a controller forgets a link once its discovery packets stop, which is exactly
   what a failed link looks like.
3. `egress`: flows and port rates are the topology class. They are sent only while that class is
   allowed for the network (Settings › AI), and never for a network carrying a classification
   marking; otherwise nothing is sent and the card says why.
4. `ask`: one recorded, capped AI call through the AI gateway, as the person who pressed
   **Analyse this network**, on its own task (Haiku 5.5, the smallest model). It sends the
   snapshot's facts, one to a line, and nothing else: no planted issue's name, evidence or note
   ever reaches it. There is no retry and no second call: one press, one call.
5. `check`: the answer is parsed against a strict schema (a severity from info, low, medium,
   high and critical; the finding; why; the evidence ids). An answer that is not that shape is
   refused, named, and nothing of it is used. Then each finding's evidence ids are held to the
   snapshot's: an id the snapshot does not hold is removed, and a finding left citing nothing
   it holds is **dropped**. The card says how many were dropped and why. An evidence entry that
   is a whole line of the snapshot (the id, then the fact's words) is read as its id, the
   line's first word, which must still be an id the snapshot holds; the card says how many
   entries were cut so. Long text is shortened and said so; at most 20 findings are kept.
6. `compare`: each planted issue is **found** when a kept finding cites evidence it names, else
   **missed**; an issue planted after the analysis was made reads **planted after this
   analysis**, neither found nor missed, since it was not there to be found. **Why** is your
   note, saved on the row. A planted issue's name and evidence are corrected with **Edit…**,
   or it is taken off the sheet with **Remove…**; each change is kept with who made it, when,
   and what it was.

## The evidence ids

| Id | What its line holds |
|---|---|
| `port:<controller>:<switch>:<port>` | the port as its switch describes it: link up or down, administratively up or down, its name and speed |
| `rate:<controller>:<switch>:<port>` | its packet and byte rates over the interval, its drops in it, and its load against its speed |
| `flow:<controller>:<switch>:t<table>:p<priority>:<match digest>` | a flow that forwards or changes traffic: its match, actions, counts, age, timeouts and cookie |
| `drop:<controller>:<switch>:t<table>:p<priority>:<match digest>` | a flow with no actions, which drops what it matches |
| `link:<controller>:<switch>:<port>-<switch>:<port>` | a link between two switch ports: up, discovered with an end down, or not discovered now |

A switch is its datapath ID in 16 hex digits. A flow's id is the same from one collection to the
next while its table, priority and match stay the same; an address never appears in an id, so a
flow matching an IPv4 or an IPv6 host is cited alike. A switch with many flows sends its 60
busiest by packets and every drop flow, the rest counted, and the facts say so.

## Collect now {#collect}

**Collect now** is the one read of the network's switches this screen makes, and the only one:
the line beside **Analyse this network** names how many switches the latest snapshot holds, when
it was collected, the model, and about what a call costs (by an over-estimate of its size; the
AI mark's hover names the call's cap). **Analyse this network** asks about exactly the snapshot
that line names. While no snapshot is kept, it is off and says so. A newer snapshot than the
latest answer's is said above the findings.

Under that line the card names the latest snapshot by its id, as text, with **Copy**, the time
it was collected, who collected it, and how many switches and flows it holds. The id is
what the evaluation is given, so copy it from here.

**Kept snapshots** counts every snapshot the network keeps. Open it to list them, newest
first, ten to a page, with **Older** and **Newer**: each one's id with **Copy**, when it was
collected (UTC) and by whom, how many switches and flows it holds, and its **seal**. A seal
that **holds** means the snapshot is exactly what was collected. One that is **broken**
changed since it was kept, so **Analyse this network** and the evaluation refuse it. One that
is **unreadable** says why. The list is read when you open it, never on a page view, and
reading it changes nothing.

Each collection is a row on History, under SDN flow operations: who started it and how they
were verified, and how many switches and flows the snapshot holds, or why it kept nothing.
The snapshot's id is under the row's Details for the record. A snapshot kept before Mercury
recorded collections is in **Kept snapshots** and has no row on History.

## Planted issues {#planted}

**Add a planted issue…** takes a name for the problem you planted, the evidence it should be
found by, and optionally why. Evidence is one or more evidence ids, as the findings cite them,
or patterns with `*` (`port:ctl-1:0000000000000003:*` is every port of that switch). For a
failed redundant link, name its `link:` id and its two `port:` ids. The sheet never reaches the
model.

After each analysis every row says **found** (hover: which findings cited its evidence) or
**missed**. A row planted after the analysis was made says **planted after this analysis**
(hover: when it was planted and when the analysis was made): it is neither found nor missed,
and the counts at the card's head leave it out. The downloaded sheet and History › Export's
failure log read it the same way, so it is never counted as a miss. Type why in the row's
**Why** and **Save**: what made it findable, or what the collection could not show.
**Download the sheet** gives the sheet as Markdown (or **as CSV**), its first lines naming the
network, the analysis, its snapshot, its call and model, how many were found, missed and
planted after, and who downloaded it when: the table for a lab document, and the record of
false positives and misses. The Markdown ends with every change to the sheet.

## Correct or remove a planted issue {#correct}

A mistyped evidence id reads as missed, because no finding can cite an id that does not exist.
**Edit…** on the row opens its name and evidence in place; change them and **Save changes**.
The issue keeps its place and when it was planted, so every analysis is marked against the
corrected evidence: an issue an analysis cited by the right id now reads **found** there, on
the page, in the downloads and in History › Export. Nothing is changed when the name and
evidence are the ones kept, and the change is refused, naming both, when the issue was changed
in another tab since the form was drawn.

**Remove…** asks first, and says what survives: the issue leaves the sheet, its found and
missed counts and History › Export's failure log, but nothing is deleted. Its name, evidence
and why are kept in the network's planted-issue record, marked removed with who and when.
**Remove from the sheet** takes it off.

Both are a verified person's, never a service's. Each change is listed, newest first, under
**Changes to the sheet** (collapsed, under the card): who, when, and what the issue was and is
(an addition, a why saved, a correction, a removal). The downloaded Markdown lists them all.

## Check this answer again {#recheck}

**Check this answer again**, under the findings, makes **no AI call** and costs nothing. The
record of AI calls keeps every answer as the model gave it. This reads that answer again,
parses it by the schema it was asked under, and holds it to the same kept snapshot with the
check as it is now. Use it when the check has changed since the answer was made: an answer
whose findings were dropped by an older check can be read by today's without asking the model
again.

The first check's findings and counts stay on the card exactly as they were. Under them the
card draws **Checked again**, when and by whom, **no new AI call**, with the findings that check
kept and what it dropped. The planted issues are then marked **found** or **missed** from the
re-check, and a line above the sheet says so; the downloaded sheet and History › Export are
marked the same way, the download naming the re-check and what the first check kept. Checking
again later replaces the earlier re-check, never the first check. The call's record in History
gains a line saying the answer was checked again, by whom.

It is refused, saying why, and keeps nothing, when the analysis made no call or its call kept
no answer (a call refused before anything was sent), when the record of AI calls no longer
holds the call, when the recorded answer does not parse, when the snapshot changed since it
was kept, or when a newer analysis was kept since the card was drawn.

**Analyse with the trace tool** has the same control under its own findings. There the
answer is also held to the reads that ran, as its first check was, and the comparison's row
says when it is counted from a re-check.

## Was this right?

Under the findings, **Was this right?** records your verdict on the answer, as under every AI
answer ([Was this right?](ai-feedback)). **The call** opens the call's record in History: its
request, its answer, its cost and what became of it (how many findings were shown and dropped).
