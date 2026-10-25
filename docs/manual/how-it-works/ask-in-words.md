# Ask in words

On **History › Query › Ask your own › Metrics**, **Ask in words** takes a question as you
would say it ("input errors per interface, top 5, last 7 days") and fills the metrics
builder's choices for you: the metric, the devices, the operations, the range. It never writes
a query you cannot see. The builder forms the query from those choices, as it does from yours,
and checks them, and nothing runs as an answer until you press **Ask**.

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
   uptime). A question that names devices, or a role ("all switches"), is offered only the
   metrics those devices carry, from one read of Prometheus for each; if a read fails, the
   offer is the whole catalogue's. It is
   never the whole catalogue sent. A question that matches no metric stops here: nothing is
   sent, nothing is spent, and {{product}} answers it itself. **Mercury answered this itself**
   says which of your words it could not match, asks you to name what to measure and which
   devices, and gives the Start-from chips as links.
2. `ask`: one call through the AI gateway, as you. What is sent is masked first. The builder's
   vocabulary (its ranges, operations and filters) is the same on every call, so it is cached.
   Your question, the metrics offered, the devices you named that this network holds, and its
   roles go as data. Metric help text is written by an exporter, not by {{product}}, so it is
   data too, and an instruction inside it is not followed. The answer must be the builder's
   own choices, in a fixed shape, or one of two other answers. What your words leave unsaid
   takes a default you see in the builder and can change: one line per device unless you ask
   for a total (never different devices in one line unasked), and no grouping when you name
   one device; the inbound variant when you do not say in or out; a count of the things in a
   state ("sessions not established"); the 5-minute CPU measure; a 64-bit counter where both
   are offered; and a rate over 5 minutes as a counter's first operation.
   **A question back**, when your words leave a choice no default settles (which interface,
   or a device this network does not have): it is shown as "One question first", your words
   stay in the box, and nothing is filled; add the answer and fill again.
   **A refusal**, when no offered metric answers the question or the builder cannot express it
   (counting restarts, for one): it says why, and nothing is filled. A period like "yesterday"
   becomes the builder's From… to…, in UTC, worked out from the time the question was asked.
3. `read_back`: the choices become the builder's address, and the builder checks them as it
   checks yours. A metric that was not offered is refused, and nothing is filled. A device or
   role this network lacks is left out, and so is a label the metric does not carry, or an
   operation it cannot take. Each one is said above the builder.
4. `test_run`: Prometheus is asked once to count the query's series at the range's end,
   within 10 seconds. The note says how many series it answers now, or that the test run did
   not answer.
5. `fill`: the builder is drawn with the choices, and its address is the page's. Check the
   choices and the query, change any of them, then press **Ask**.

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
builder: `offer` gives the kinds of log Loki holds, its other labels, and the mnemonics that
share a word with your question (the Start-from chips' and those the logs reader counted:
"OSPF adjacency changes" offers `%OSPF-5-ADJCHG`); a question about severity or a word in the
line is offered none, and is answered by the severity and text filters. `ask`, `read_back`
and `fill` are as above: a kind or mnemonic that was not offered is left out and said.
`test_run` counts the lines the query matches over the range, within 10 seconds. Nothing reads
the lines until you press **Ask**.
