# History › Export: the two logs

History › Export downloads two logs of what Mercury already records, for a report such as a
lab's: **the call and cost log**, every AI call and what it cost, and **the false-positive and
failure log**, where the AI layer was wrong or the network's automation failed, and what was
done about it. Each is a CSV or a JSON file for one network or every network, over whole UTC
days. The export reads; it writes nothing, and it asks no device, controller or model anything.

![History's Export: a person chooses the network and the whole UTC days, at most 31, and a longer range is refused with nothing read; the call and cost log reads every AI call the ledger recorded in the range, one row each, with a total per UTC day and per feature, the dollars the ledger's summed by day; the false-positive and failure log reads each network's SDN responses and flow operations, every analysis's planted-issue sheet, its record of evaluation runs (the false-positive runs, the analyst evaluations and the classification case recordings), the ledger's evaluation calls and the answers said wrong; every text is masked on the way out, and the file, CSV or JSON, opens with its range, network, when and who. Nothing is written.](diagrams/history-export.svg)

## The steps

1. `range`: you choose the **Network** (one, or **Every network**) and the whole UTC days
   **From** and **To**, both included, at most 31. A longer range is refused, naming its
   length, and so are a From after its To and a network no one has: nothing is read.
2. `calls`: every AI call the ledger recorded in the range (the record History's AI calls
   draw), one row each, oldest first, then a total per UTC day and per feature. The dollars
   are the ledger's own cost per call, summed by UTC day from the rows read now, never carried
   forward from an earlier total; the provider bills.
3. `failures`: each source's rows, one row each with its record's link:
   - from each network's own records: every SDN detection a person dismissed (the reason and
     who), every AI classification the check refused (its call), every response AUTO decided
     on and could not send (a protected-flow refusal named as one), every flow change,
     policy, response or re-apply of a verified person's that the protected set refused (who
     and how they were verified, what was asked, and each protected flow, protected object or
     the control channel that refused it, with its citation), and every flow operation whose
     Verify failed or whose request the controller refused, with what its rollback achieved;
   - from SDN › Flows' analyses: every planted issue each analysis in the range missed, B1's
     and the trace tool's, one row per issue per analysis, linking that analysis's call; an
     issue planted after an analysis was made is not its miss;
   - from each network's record of SDN evaluation runs: every detection a false-positive run
     (`nmas-sdn-false-positives`) found on traffic declared normal, with its rule, its
     measurement against its threshold, its evidence, its run and what Mercury does with it;
     and every analyst evaluation run (`nmas-sdn-b4-eval`) that missed its case's planted
     issue, kept a false-positive finding, or answered a benign case as a threat, per
     technique and run, linking its call; and every run of every classification case a
     recording (`nmas-sdn-cases`) missed, with its case, the case file's expectation, what was
     got, the judge's misses and the recording's run, linking its call where it made one;
   - from the ledger: every evaluation call that found a threat in a collection no rule fired
     on, a false positive by the evaluation's own definition; and every policy's AI call whose
     answer the protected set refused before Mercury kept a record of each refusal;
   - from Was this right?: every AI answer a person said was wrong, and its review.
4. `mask`: every text a row carries is masked on the way out, as History masks what it draws.
5. `file`: CSV or JSON. Its first lines name the log, the range, the network, when it was made
   and who made it; then the summary, what could not be read, and how many rows it left out
   past its 10000. Nothing is written.

## The call and cost log's columns

| Column | What it holds |
|---|---|
| `at`, `day` | when the call was recorded, and its UTC day |
| `call` | the call's id |
| `feature` | the task: Explain, Ask in words, the SDN classifier, the analyst… |
| `trigger`, `by` | person (who pressed), background (the job, its feature and finding) or evaluation (its run) |
| `network` | the network the call names, when it names one |
| `about` | what the call was about, in History's words |
| `model`, `prompt` | the model, and the prompt with its version |
| `tokens_in`, `tokens_out`, `cache_write`, `cache_read` | the provider's counts |
| `usd`, `latency_s` | the ledger's cost, and the seconds the provider took |
| `verdict`, `outcome` | the gateway's verdict, and what it means: ok, refused by validation, refused at a cap, refused by a gate, failed, joined another's call |
| `detail`, `then` | why, and what became of the answer |
| `link` | the call's row on History |

Then the totals by UTC day and by feature: calls, dollars, each outcome, the tokens.

`then` holds the whole reason, however long. Some features cut a reason to 200 characters
when they recorded it. The file cannot tell such a reason from a whole one of that length, so
it marks every reason exactly 200 characters long: "[200 characters: as long as the cut made
when this was recorded, so its end may be missing]".

## Protected-flow refusals

A write the protected set refuses sends nothing, and it is counted under **protected-flow
refusals** whoever made it. Each row's `got` column begins with which it was:

| `got` begins | What was refused | Where it is kept |
|---|---|---|
| AUTO's response | a response AUTO decided on | the response itself, on SDN › Responses |
| a person's flow change | Add, Edit or Remove on SDN › Flows, at its preview or its confirm | the network's flow record; a row on History |
| a person's policy | a policy on SDN › Policies, when it was drafted, checked again, previewed or confirmed | the same record; a row on History; its AI call is named |
| a person's response, a person's re-apply | a response or a Re-apply… a person previewed or confirmed | the same record; a row on History |
| an AI call's answer | a policy refused before Mercury kept a record of each refusal | only the call's own row |

The row's `reason` is the refusal as it was said. `who` names the person and, when they were
verified another way than the access proxy's sign-in (the local account, a host login), how.
`got` names each protected flow, protected object or the control channel that refused it,
with its citation.

A record is made for a verified person only. A preview needs no sign-in, so someone not
signed in can still be refused by the protected set; that refusal is drawn on their card,
which says it is not recorded, and it is not in this file.

A flow change or a policy refused before Mercury kept these records was kept nowhere, so it
is not in the file; a policy's refusal from then is there only as its AI call.

## Which network a call belongs to

Every call the gateway records names the network it was asked for, sent or refused: a
person's press, a background job's and an evaluation's. A call that names none (the
installation's own, such as the connection check, or one recorded before 2026-11-10) is counted
under one network's line and listed in **Every network**'s log. For a lab's report covering
older calls too, download **Every network**.

## Where the evaluation runs are kept

`nmas-sdn-false-positives`, `nmas-sdn-b4-eval` and `nmas-sdn-cases` each keep what they found
wrong in the network's own record of evaluation runs, beside their own `--out` files, which
are unchanged. A false-positive run is kept under the network its series names, or the
network `--network` or `--list` names; a run whose network Mercury does not have is refused
before anything is judged. A classification case recording keeps its missed runs in one write
once its report is written, under the network `--network` names, else `--list`, else its case
file's own; it classifies on that same network, and a network Mercury does not have, a case
file for another network, or a `--network` and `--list` naming two networks is refused before
anything is asked. The normal-traffic classification runs (`nmas-sdn-classify-normal`)
need no record of their own: each call keeps its collection and its answer in the ledger, and
a threat found there is the run's own definition of a false positive. A record that cannot be
read is said on the card and in the file, never a shorter log.

## What is not in the failure log

The per-case misses of the other four case scripts (`nmas-intent-cases`, `nmas-heal-cases`,
`nmas-nl-cases` and `nmas-assistant-cases`) are written only to their own report files, never to a record Mercury
reads, so the failure log cannot hold them; the card and each file say so. Attach that report
beside the file.
