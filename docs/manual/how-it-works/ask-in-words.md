# Ask in words

On **History › Query › Ask your own › Metrics**, **Ask in words** takes a question as you
would say it ("input errors per interface, top 5, last 7 days") and fills the metrics
builder's choices for you: the metric, the devices, the operations, the range. It never writes
a query you cannot see. The builder forms the query from those choices, as it does from yours,
and checks them, and nothing runs as an answer until you press **Ask**.

It makes one call to a hosted model (Anthropic's, the model named in the button's hover),
through {{product}}'s AI gateway: allowed only once hosted AI is allowed on **Settings ›
Installation › AI (hosted)**, capped, and recorded with who asked.

![Ask in words: the question's words choose the metrics to offer, never the whole catalogue, and a question matching none stops there with nothing sent; one recorded, capped call through the AI gateway, the builder's vocabulary as its cached prefix and the question and the offered metrics as data, answers with the builder's choices; the builder reads them back as it reads a person's, a metric not offered refused and a device the network lacks left out; one time-limited count of the query's series tests it; the builder is drawn filled, and nothing runs until the person presses Ask.](diagrams/ask-in-words.svg)

## The steps {#steps}

1. `offer`: the metrics Prometheus holds whose name or help shares a word with your question
   are offered, at most 20, a word in the name counting twice a word in the help. A few
   network words are read as SNMP's ("traffic" as octets, "interface" as if). It is never the
   whole catalogue. A question that matches no metric stops here, and nothing is sent.
2. `ask`: one call through the AI gateway, as you. What is sent is masked first. The builder's
   vocabulary (its ranges, operations and filters) is the same on every call, so it is cached.
   Your question, the metrics offered, the devices you named that this network holds, and its
   roles go as data. Metric help text is written by an exporter, not by {{product}}, so it is
   data too, and an instruction inside it is not followed. The answer must be the builder's
   own choices, in a fixed shape. If the model finds that no offered metric answers the
   question, it says why, and nothing is filled.
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

- **Hosted AI is off:** nothing is sent until it is allowed, with a reason, on the AI card.
- **No metric shares a word:** try the metric's own words, or search the builder's Metric box.
- **Not one of the metrics offered:** the answer named a metric {{product}} did not offer, so
  nothing is filled.
- **Over a cap:** the call's worst case, and the cap it would cross, are both named.

It answers metrics questions only. Questions about logs use the logs builder by hand.
