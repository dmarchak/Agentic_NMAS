# AI troubleshooting: Start, Approve, Modify, Deny and Hand over

An incident's page ([An incident's page](incident)) leads with its bottom line: what happened,
its impact, and the one next action. Under it is one card, **Fixing it**, where What to do and
AI troubleshooting used to be two: a status line, the AI's plan when there is one, and,
collapsed, every fix tried in the incident with what each cost in AI. When Mercury's own fix
fails, the AI investigates by itself where its background feature is on ([Starting by
itself](#automatic)); otherwise **Start AI troubleshooting** is the next action. The AI
proposes a plan; you **Approve** it by its hash, **Modify…** it or **Deny…** it. Nothing runs
until a person approves it, and nothing that already failed in the incident is offered as its
next action (the operator's rule of 2026-11-14).

![AI troubleshooting on an incident's page: an attempt is a catalogue operation's run on the incident's device, read from the operation's own record; a failed attempt is said by the card's status line, and nothing more runs until the AI is started, by itself where its background feature is on for the network, or by a person's Start AI troubleshooting. The per-incident cap is asked again first; one AI investigation (at most two calls, its answer checked against what was sent) proposes a plan of catalogue operations, each step preflighted against the incident, the heal guards and committed intent, a step that repeats a failed attempt refused. The plan runs only when a person approves it by its hash; Modify asks for a revised plan and Deny records why not, and neither runs anything. Hand over keeps a write-up and sends its link to the teams chosen. Nothing in the card reaches the device but the plan a person approved.](diagrams/fixit-troubleshoot.svg)

## Starting by itself {#automatic}

"Start AI troubleshooting automatically when Mercury's fix fails" is a background AI feature,
off by default on every network. It is one row among the other background features (Settings ›
AI, Background features, [Settings › AI](settings-ai)), turned on with **Turn on…** after its
estimate (per incident, against the per-incident cap and the day cap) and off with **Turn
off**, each only by a verified person and recorded. It starts anything only while self-healing
is in **Auto** on the network (its policy in force now, not expired): with self-healing off or
in Dry run, nobody asked Mercury to fix anything, so nothing starts. While both are on, a code
fix that fails or does not verify, of a kind Auto allows, or a problem for which no code fix
exists (a can't-fix, a lost telemetry stream), starts one AI investigation, once per failure,
within the caps; a cap that would be passed starts nothing,
and the card says which cap and offers **Hand over…**. The AI only proposes: a person approves
every plan by its hash.

Turning it on never catches up, and neither does turning self-healing's Auto on. An incident
whose fix failed before either was on (or while either was off, or self-healing was in Dry
run) shows **Start AI troubleshooting** as its next action, a person's press that runs the same
investigation once.

## Approve, Modify and Deny {#approve}

The AI's plan is drawn in the card: what the AI found, then each step with its preflight, the
check Mercury runs on each step before it can be approved ("preflight passed", or "refused at
its preflight:" and why). The plan's hash and each step's are in the page's record.

**Approve** runs the plan exactly as drawn, held to the plan's hash: a step that moved since
the page was drawn is refused, naming what moved, and nothing is sent. A plan with a step
refused at its preflight has no Approve; the line under the buttons says why.

## Modify {#modify}

**Modify…** opens a box, anchored to it, for what should change. **Revise the plan** sends your
words (masked before they are sent) to the AI, which returns a revised plan with a new hash.
Nothing runs: Approve, Modify… and Deny… come back with the new plan. **Cancel**, or Escape,
closes the box with nothing sent.

## Deny {#deny}

**Deny…** opens its confirm, with an optional reason. **Deny the plan** records the denial and
your reason; nothing runs and the incident stays open, with **Ask the AI again** and **Hand
over…** as its next actions. **Keep the plan** closes the confirm with nothing recorded.

## Ask the AI again {#ask-again}

After a denial, **Ask the AI again** runs a new investigation, told what was denied and why,
under the same caps as the first. Its plan is drawn with Approve, Modify… and Deny… again.

## Start AI troubleshooting {#start}

On Needs attention, the row about such an incident offers the same:
**Start AI troubleshooting…**, a link to the incident's bottom line, where the button is. A lost
telemetry stream's row offers it in place of Re-subscribe while the incident offers it, so the
row and the page never name two different next actions.

**Start AI troubleshooting** is the next action when Mercury's fix failed and the AI was not
started by itself. Its cost is drawn beside it before you press. It runs one investigation, as
you ([the investigation](#ask-ai)); the plan it returns runs only when you approve it.

## The attempts {#attempts}

An **attempt** is a run of one of Mercury's catalogue operations (Re-subscribe a device's
telemetry, or Re-add a receiver a run left removed) on the incident's device, started after the
incident was detected. Each one is read from the operation's own record every time the page is
drawn, so its outcome is the operation's words. A run started from the section's proposal also
names the incident in its record, and is that incident's attempt whatever its time.

Each attempt is one line, under the card's collapsed **Attempts**: when it ran, the operation
and its parameters, who proposed it (when it came from a proposal here) and who approved it,
its outcome, its AI cost, and **Open the run**, which opens the run's own card with its steps
and verify reads. A fix that failed is listed again under **Other actions**, with the attempt
it failed in and its record; it is never the next action.

The card's collapsed **Costs** says what this incident's AI calls have cost against its cap,
and today's spend against the day cap. Both are summed from the record of AI calls each time.

## A failed attempt stops {#the-stop}

When the newest attempt did not pass its verify, the card's status line says so, and its
collapsed **What attempt <n> found** says what the run found, from the run's own record, one
line per subscription with its state in words (the operation's outcome, or what its checks
said), each line opening to its three checks with their addresses, ports and connection
numbers, and any stale session flagged. No page load, no refresh and no announcement starts
another attempt. What comes next is the bottom line's one action: the AI's investigation
([Starting by itself](#automatic), or **Start AI troubleshooting**), or **Hand over…**.

## The steps, from a plan to its run {#steps}

Each press in the card is a verified person's, refused with nothing recorded or sent
otherwise, and each takes these steps, which its code keeps:

1. `preflight`: before the plan is drawn, each step is checked by code against the catalogue's
   schema, what the incident names (its device and its lost subscriptions), the heal guards (a
   planned window, the device held by another run) and committed intent, and a step that
   repeats an attempt that failed here is refused. A refused step is drawn refused with why,
   and the plan then has no Approve.
2. `approve`: **Approve** sends the plan's hash; the plan is preflighted again and refused,
   naming both hashes, when it moved. Then Mercury runs each step in order through its own
   operation (its preview again, its apply re-checking its own hash, its verify, its record),
   stops at the first that does not pass, and retries nothing.
3. `modify`: **Modify…** sends your words to the AI with the evidence, under the cap; the AI
   returns a revised plan with a new hash. Nothing runs.
4. `deny`: **Deny…** records the denial and your reason. Nothing runs.
5. `ask_again`: after a denial, or an answer that proposed no plan, **Ask the AI again** runs a
   new investigation under the cap. Nothing runs.
6. `start`: **Start AI troubleshooting** runs the one investigation for an incident whose
   failure did not start one by itself, once. Nothing runs.

Start, Modify… and Ask the AI again each answer at once: the investigation runs as a job (under
**In progress** too), the card says "The AI is investigating" with when it started, after a
reload as well, and it is drawn again when the job ends. A second press while one runs is
refused, naming the one running, so no investigation is paid for twice. A job that fails says
so in the card: "Couldn't troubleshoot:" and why, with **Ask the AI again**.

Mercury's own re-plan (Retry with more information) and Cancel are no longer on the page (the
operator, 2026-11-14: Modify… and Deny… replace them).

## The investigation {#ask-ai}

**Start AI troubleshooting** and **Ask the AI again** each run one investigation; with the
background feature on, the failure itself starts it ([Starting by itself](#automatic)). Its
cost is drawn before you press: at most two calls at the AI's per-call cap (at most $0.25
today), and about what it has cost before once it has been measured; the incident's spend so
far against its cap, and today's against the day cap, under the card's **Costs**. The button
carries the AI mark; when hosted AI cannot answer now (it is off, no key is set, the day cap is
reached, or the provider's usage limit holds), it is drawn disabled with why.

It runs these steps, one investigation:

1. `person`: a press is a verified person's, or it is refused with nothing sent; the press is
   the call's trigger, and the gateway refuses it for anyone but the person who pressed. A
   start by itself is a background call, the background feature's, under its caps, once per
   failure; no timer, job or page load starts one.
2. `mode`: AI troubleshooting's mode (Settings › Installation › AI, AI troubleshooting) is
   Manual. Off refuses the press, with nothing sent.
3. `cap`: the per-incident cap is asked again ([the cap](#the-cap)): spent so far plus this
   investigation's worst case. Past it, the press is refused, naming both figures and what moved
   since the panel was drawn, and nothing is sent.
4. `pack`: what the AI is sent is built in code: the incident's evidence pack (what started it,
   the device, its History and Intent check, its neighbours, health, its log lines, what
   self-healing tried and Mercury's diagnosis, configuration only by kind), the incident's
   attempts (each `attempt:<n>`), Mercury's own Seen before (`seen_before:1`), the operations
   it may propose from, and your note (`note:1`), masked as it leaves and said back to you
   when something in it was masked. Every person in any of it is a stable label
   ("person-3f9a1c"), never a name or an address, and any address left anywhere in the
   request is replaced by its label before it leaves.
5. `ask`: one call through the AI gateway, under the day cap and the per-call cap, and under
   the task's prompt bound: before it asks, Mercury fits the request to that bound, both calls
   (the second with room for three reads at their cap), by its own over-estimate of a prompt's
   size; when it is over, the topology is left out first, then the pack's largest sections
   (logs, neighbours, history, observer, health) are cut to half their pieces, each cut said in
   the section, and the preview says what was done. With the
   network's device state class on (its Network tab, What AI may send), the AI may ask Mercury for up to three
   read-only reads, and a second call carries them; it cannot ask again. A read is either of
   the incident's device, asked as an engineer types it in Show commands (show, ping or
   traceroute and the rest of the command: a show of one of the AI's command families, an
   engineer's troubleshooting reads, each in one of its forms, held whole by Mercury's
   allowlist too; standby and VRRP only in their brief forms; each address in it one of the
   network's and each interface, written as one word, one the device's golden holds; a
   configuration form only under the configuration class, off on every network), run
   through Mercury's own reads engine as Mercury's account (or the read-only account, under
   Settings › AI's hardened choice) and kept on History › Reads with whom it signed in as; or
   Mercury's own of what it holds about a device in scope: its intent, its golden (the
   configuration class's), its neighbours, its History, its log lines from Loki, its health
   figures, the collector's side of one of the incident's streams on Mercury's host (its
   listener and the device's sessions on the port intent gives its receiver, IPv4 or IPv6), or
   whether the stream has data in Prometheus now. Each is held to the incident's scope, and
   each is a row in the send log and on History beside the two calls. A read Mercury refuses
   because it lacks it (off the allowlist, left out on purpose, no such read), and a gap no
   catalogue operation fills, is recorded as a **missing capability** for people to review
   (History, kind AI missing capabilities); Mercury never acts on one. With the class off, no
   read is asked for.
6. `check`: the answer is checked against what was sent: every reference it cites must be
   there (a past incident Seen before does not hold is refused), every confirming step must be
   a read-only read, a device it names must be cited, and its fix must be exactly one catalogue
   operation with that operation's parameters, each of its shape, acting only on the incident's
   own device and subscriptions (never one a read or the note named). An answer that fails is
   drawn "couldn't be checked, so it isn't shown", with why; its cost still counts.
7. `propose`: a fix passes the same check as Mercury's own proposal (the incident's scope, the
   heal guards, committed intent through the operation's own preview), and a repeat of a failed
   attempt is flagged. When no catalogue operation does what the fix needs, the answer is a
   **gap**: said, with no Approve.
8. `record`: one proposal line is kept in the incident's troubleshooting record: the operation
   and its parameters (or why there is none), its AI calls, who pressed, your note, and what the
   AI said (its rationale and each hypothesis with what it cites). The call's own record on
   History says what became of its answer and links back to the incident's page.

Nothing runs. A proposed plan is drawn with its steps and **Approve**, **Modify…** and
**Deny…**; it runs only when you approve it by its hash. If it fails, the card says so, and the
AI is asked again only by a press, or once by itself for the new failure.

## A repeated proposal is refused {#a-repeat}

A plan's steps are compared with every attempt in the incident that did not pass. A step of the
same operation with the same parameters is refused at its preflight, naming the attempt it
repeats and what that attempt said, so the plan has no Approve: nothing that already failed in
the incident is offered as its next action. The failed operation stays under **Attempts** and
**Other actions**, with its record. The same operation with other parameters is a variation,
and is offered.

## The run's record {#the-run}

A fix confirmed from the section's proposal writes the incident's id, the attempt's number and
the proposal's id into its run's record, with what is different now for a repeat. The attempt's
line then says who proposed it, and the incident's list can tell later how it was fixed.

## The per-incident cap {#the-cap}

**AI spend per incident** (Settings › Installation › AI, the AI troubleshooting card, $1.00 by
default) holds every attempt: what the incident's AI calls have cost so far plus the next
attempt's worst case is compared with it. At the cap exactly is allowed; past it, nothing
starts, the card says which cap would be passed (spent, the worst case, their sum and the cap),
and **Hand over…** is the next action. An attempt's worst case is two calls at the per-call cap
of the AI's pinned model (at most $0.25 today). There is no "no cap", and Mercury never raises
it. **AI mode** on the same card is Manual or Off; Off offers no AI at all.

## Cancel and Retry are gone {#cancel}

Cancel and Retry with more information were removed on 2026-11-14: **Deny…** records that a
plan is not wanted, and **Modify…** says what the AI should change. An incident cancelled
before then keeps its line in its troubleshooting record and on its page's status line.

## Hand over {#hand-over}

**Hand over…** builds a write-up for an engineer from the incident's records, with no AI: its
summary, the impact now, what Mercury knows, what was tried, what the AI said (or that no AI was
asked), the configuration now, the next steps, the notes and the cost. People are named by
display name and teams by name; no email address and no secret is in it. Each hand-over is kept
as a new version, never written over, on its own page, linked from the section and from the
incident's record, with Download as Markdown. Its page draws every time in your time zone, its
UTC on the hover; the Markdown and the message sent to a team say each time in UTC, since
they leave Mercury. **Send the hand-over** sends it to the teams you
tick, each one of the teams told about the network's can't-fix (Settings › Notifications); with
none ticked it is kept and sent to nobody. A send that fails says so, with **Send again**.
**Hand over…** is beside the next action, as a link, while the incident is open, and is the
next action itself when nothing else is left (a cap passed). Once the incident is resolved, the
card is read-only: a press sent to it then is refused, with nothing recorded.
