# Ask in words

On **History › Query › Ask your own › Metrics**, **Ask in words** takes a question as you
would say it ("input errors per interface, top 5, last 7 days") and fills the metrics
builder's choices for you: the metric, the devices, the operations, the range. It never writes
a query you cannot see. The builder forms the query from those choices, as it does from yours,
and checks them, and nothing runs as an answer until you press **Ask**. When your words
do not fill it (a refusal, a question back, or {{product}}'s own answer), the builder keeps what
it held before them, marked **Left from your previous question**, and **Ask** is off until
you press **Keep these choices** or change a choice, so Ask never answers an earlier question
in place of yours.

It makes one call to a hosted model (Anthropic's, the model named in the button's hover),
through {{product}}'s AI gateway: allowed only once hosted AI is allowed on **Settings ›
Installation › AI (hosted)**, capped, and recorded with who asked.

The row carries the **AI** mark: hover it for the task, its pinned model and its cap per call.
When hosted AI cannot answer (it is off, no key is set, or today's cap would be crossed), the
box and **Fill the builder** are disabled and the reason is written under them; the builder
itself, its choices and **Ask**, stays as usable as ever (see
[The AI mark](installation-settings#ai-mark)).

![Ask in words: the question's words choose the metrics to offer, never the whole catalogue, and a question matching none stops there with nothing sent; one recorded, capped call through the AI gateway, the builder's vocabulary as its cached prefix and the question and the offered metrics as data, answers with the builder's choices; the builder reads them back as it reads a person's, a metric not offered refused and a device the network lacks left out; one time-limited count of the query's series tests it; the builder is drawn filled, and nothing runs until the person presses Ask.](diagrams/ask-in-words.svg)

## The steps {#steps}

1. `offer`: the metrics Prometheus holds whose name or help shares a word with your question
   are offered, at most 20, a word in the name counting twice a word in the help. Among equals,
   the metrics your network's devices carry (their series hold the device label) come before
   the monitoring stack's own, so "CPU" means the routers' CPU before the monitoring host's. A
   few network words are read as SNMP's ("traffic" as octets, "interface" as if, "up" as
   uptime, and "rebooted", "reloaded" or "restarted" as uptime too: a device restarting is its
   uptime falling, which the builder's **resets** counts). A question that names devices, or a role ("all switches"), is offered only the
   metrics those devices carry, from one read of Prometheus for each; if a read fails, the
   offer is the whole catalogue's. It is
   never the whole catalogue sent. A question that matches no metric stops here: nothing is
   sent, nothing is spent, and {{product}} answers it itself. **Mercury answered this itself**
   says which of your words it could not match, asks you to name what to measure and which
   devices, and gives the Start-from chips as links.
2. `ask`: one call through the AI gateway, as you. What is sent is masked first. The builder's
   vocabulary (its ranges, operations and filters) is the same on every call, so it is cached.
   Your question, the metrics offered, the devices you named that this network holds, and its
   roles go as data, with the time now and the time today began (see
   [What "today" means](#today)). Metric help text is written by an exporter, not by
   {{product}}, so it is data too, and an instruction inside it is not followed. The answer
   must be the builder's own choices, in a fixed shape, or one of two other answers. What
   your words leave unsaid takes a default you see in the builder and can change: one line
   per device unless you ask for a total (never different devices in one line unasked), and
   no grouping when you name one device; a level such as CPU averaged per device (its
   maximum when you say highest, peak or busiest), never summed; no grouping when you ask per
   interface or for the top interfaces, as each interface is already its own line; the
   inbound variant when you do not say in or out; a count of the things in a state
   ("sessions not established"); the 5-minute CPU measure, and the per-CPU total where an
   older average is offered beside it; a 64-bit counter where both are offered; a rate over
   5 minutes as a counter's first operation; a top 5 or 10 only when you say "top" or give a
   number ("highest" alone draws every line); bits only when you say bits or bandwidth
   ("traffic" keeps bytes); and "today", "yesterday", "this week" and "last week" as the
   calendar's, from their midnights (see [What "today" means](#today)).
   **A question back**, when your words leave a choice no default settles (which interface,
   or a device this network does not have): it is shown as "One question first", your words
   stay in the box, and nothing is filled; add the answer and fill again.
   **A refusal**, when no offered metric answers the question or the builder cannot express it:
   it says why, and nothing is filled. When the question is about an event a device logs (a
   reload, an interface or adjacency going down, a configuration change), the refusal adds
   where the logs answer it, with the mnemonics: "the logs can answer it: ask in Logs
   (%SYS-5-CONFIG_I)". Those words are {{product}}'s, from the platform's event mnemonics,
   not the model's. Any other named period no
   range fits becomes the builder's From… to…, in UTC, worked out from the time the question
   was asked.
3. `read_back`: the choices become the builder's address, and the builder checks them as it
   checks yours. A metric that was not offered is refused, and nothing is filled. A device or
   role this network lacks is left out, and so is a label the metric does not carry, or an
   operation it cannot take. Each one is said above the builder.
4. `test_run`: Prometheus is asked once to count the query's series at the range's end,
   within 10 seconds. The note says how many series it answers now, or that the test run did
   not answer.
5. `fill`: the builder is drawn with the choices, and its address is the page's. The note
   says how your words' period was read, every time: "Read as Mon 19 Oct 13:20 to Mon 26 Oct
   13:20 America/Denver (7 days; 2026-10-19 19:20 to 2026-10-26 19:20 UTC)". Check the choices
   and the query, change any of them, then press **Ask**.

## What "today" means {#today}

"Today" runs from midnight to now, and midnight depends on where you are. {{product}} has no
installation timezone setting yet, so it uses your browser's: the form sends your browser's
timezone name (and its offset from UTC, in case the name is missing or unknown), and
{{product}} works out when today's midnight was, in UTC, correctly across a daylight-saving
change. The model is given that time as it is; it never works out a timezone itself. The
builder's From… to… shows the range in UTC.

When an answer's range starts at today's midnight, the note under the question says whose
midnight it was: "'Today' runs from midnight America/New_York (your browser's timezone; no
installation timezone is set)". If your browser named no timezone {{product}} knows, its
offset is used and said ("midnight UTC-04:00"). If nothing usable was sent, today starts at
midnight UTC, and the note says that too, and why.

"Yesterday", "this week" and "last week" are counted the same way, in the same timezone as
today: yesterday from the midnight before today's to today's; this week from midnight on
Monday to now; last week from the Monday before to this Monday. {{product}} works each start
out (calendar days, so a daylight-saving change between them moves nothing) and gives it to
the model as it gives today's. The note under the question says whose midnight the span was
counted from: "'This week' is counted from midnight on Monday America/New_York (…)". "The
last 7 days" or "the past week" is not a calendar week: it is the builder's 7 days, ending
now.

## What it costs, and what is recorded {#cost}

Each call is priced at the pinned model's rates (**Settings › Installation › AI (hosted)**
shows the table) and refused before it is sent if its worst case would cross the task's
per-call cap or the day's cap. Every call is a row in **History**: who asked, the masked
request, the answer, its verdict, its tokens and its cost. The question's metrics and labels
come from Prometheus; nothing is read from or sent to a device.

## When it says no {#refusals}

- **Hosted AI is off, no key is set, or today's cap is reached:** the row is disabled before
  you can ask, with the reason; a call made as the state changed elsewhere is refused before
  anything is sent, saying the same.
- **No metric shares a word:** {{product}} answers itself, at no cost: name what to measure in
  a metric's words and which devices, start from a chip, or search the builder's Metric box.
- **The answer ran past its length:** nothing is filled, the builder stays as you had it, and
  it says "Not filled: the answer ran past max_tokens".
- **Not one of the metrics offered:** the answer named a metric {{product}} did not offer, so
  nothing is filled.
- **Over a cap:** the call's worst case, and the cap it would cross, are both named.

## On the logs builder {#logs}

**History › Query › Ask your own › Logs** has the same row, and the same steps fill the logs
builder: `offer` gives the kinds of log Loki holds, its other labels, the events your
devices' platforms log, each with what it records (a reload, a restart, an interface or line
protocol going up or down, an OSPF or BGP adjacency changing, a configuration change),
whether or not the range holds one, and the mnemonics that share a word with your question
(the Start-from chips' and those the logs reader counted: "OSPF adjacency changes" offers
`%OSPF-5-ADJCHG`). So "which devices rebooted?" is answered by the reload and restart
mnemonics, never by the word "reboot", which no device logs. With the question go the
network's devices by role and what {{product}} collects about it (each layer present or not
collected), so a question resting on something not collected is said to be, not guessed.
{{product}}'s own heartbeat lines are left out of every query, and a question about them is
answered on the device's Logs tab. `ask`, `read_back`
and `fill` are as above: a kind or mnemonic that was not offered is left out and said.
`test_run` counts the lines the query matches over the range, within 10 seconds. A count of
none that rests on a text filter says so: "no line contains 'reboot', which may not be how the
platform logs it". A device logs an event by its mnemonic (a reload is `%SYS-5-RELOAD`, a
restart `%SYS-5-RESTART`), not by the word a person uses for it, so an empty answer to a text
filter is never called an answer; the answer's own card says the same and offers to drop the
text.
- **A mnemonic carries the event.** When a mnemonic records the event asked about, no word
  for the event is added. Only a direction no chosen mnemonic expresses stays, cased as the
  line writes it ("down" on an interface's line).
- **A text is matched in any case.** Whenever the answer holds a text for **Text contains**,
  `read_back` writes it in lower case and ticks the builder's **any case**, so "Down", "DOWN"
  and "down" are one answer and find the same lines (Loki compares text case by case). The
  answer as the model gave it is kept with the call's record beside the one filled. The
  excluded text is left exactly as the model wrote it: matched in any case it could leave out
  lines the answer never named.
- **An interface flap** is both its link and its line protocol mnemonics.
- **A BGP neighbour going up or down** is `%BGP-5-ADJCHANGE` alone.
- **One device meant by its role alone** ("what went wrong on the switch") among several of
  that role is answered by {{product}}'s own question back, which device, before anything is
  sent and with nothing spent.

Nothing reads the lines until you press **Ask**. Periods are read as people mean them: "this week", "the
past week" and "the last 7 days" are the last 7 days; "since Monday" or "so far this week" is
the calendar week. "Today", "yesterday" and "last week" are the calendar's, counted from
midnight in your browser's timezone as on the metrics builder (see
[What "today" means](#today)), and the note under the question says how the period was read.
