# Analyse with the trace tool: the analyst asking Mercury for reads

SDN › Flows' **Analyse with the trace tool** asks the same question as **Analyse this network**,
about the same snapshot, but lets the model ask Mercury for a few reads before it answers: a
packet **trace** from one host to another through the switches' flow tables, a switch's flows,
its ports, or a link's state. Mercury checks every read the model asks for and answers it from
the kept snapshot alone, so nothing is read again from the network. When both have answered the
same snapshot, the card compares them. Nothing is sent to a switch.

![Analyse with the trace tool: the same kept snapshot as Analyse this network, its seal checked; a first recorded, capped call through the AI gateway with the snapshot's facts and the hosts a trace can take, which answers or asks for up to three reads; Mercury checks each read against the closed set and what the snapshot holds, and answers the allowed ones from the snapshot alone, the trace walking its flow tables, never a live read, each answer masked, cut and logged first; a second call with the reads, which cannot ask again, within the loop's total token cap; the final answer checked as the first analyst's; then compared with it on the same snapshot. Nothing is sent to a switch.](diagrams/sdn-analyse-tools.svg)

## The steps

1. `snapshot`: the snapshot **Analyse this network** names, the latest kept. Its seal is
   checked first: a snapshot changed since it was kept is refused, and nothing is sent.
2. `first`: one recorded, capped AI call as the person who pressed the button, on its own task
   (Haiku 5.5, the same model as Analyse this network). It sends the same facts and prompt,
   with two additions: the reads it may ask for, and the hosts the controller learned (the
   only places a trace can start or end). The model answers, and may ask for up to three
   reads, each with why it asks.
3. `check_reads`: each read asked for is held to the closed set: `trace`, `switch_flows`,
   `port_stats` and `link_state`, nothing else. Its arguments are parsed by their shape (an
   IPv4 or IPv6 address or a MAC, a switch's 16 hex digits, a port) and compared with what the
   snapshot holds: a switch it does not hold, a port that switch does not list, or a host its
   host table does not list is refused, naming what it compared. A fourth read is refused.
4. `reads`: each allowed read is answered from the snapshot alone, never a live read. The
   trace walks the snapshot's own flow tables by OpenFlow's rules, as
   [A flow-table trace](sdn-trace) does, and says how the packet ends and which evidence ids
   it passed. A switch whose table the snapshot holds only part of is walked over what it
   holds, and the answer says so. Every answer is masked, cut to 4 KiB, and written to the send
   log before anything of it is sent (History › Reads).
5. `second`: a second recorded call with the reads, which cannot ask again. It is sent only
   within the AI gateway's caps and the loop's own total, at most 80,000 tokens over both calls
   by the gateway's over-estimate; past it, the first answer stands and the card says why.
6. `check`: the final answer is checked exactly as Analyse this network's: every evidence id
   held to the snapshot's, and to the reads that ran (`read:1` to `read:3`); a finding citing
   nothing either holds is dropped, and the card counts it.
7. `compare`: each planted issue is **found** or **missed** by the snapshot's evidence ids the
   findings cite (a read's id never finds one). When both have answered the same snapshot, a
   table shows each technique's findings, found, missed, **false positives**, calls and cost.

## The tool calls

Under the answer, **Tool calls** lists each read the model asked for, in order: its id, the
operation and its arguments, whether Mercury ran it, refused it (with the reason) or could not
run it, and what it returned in short (a trace's outcome and path, a count of flows or ports, a
port's state). The line under it says how many reads were asked for and whether the second call
was sent.

## False positives

A finding is judged in code, never by the model:

| Judged | When |
|---|---|
| planted | it cites evidence a planted issue names |
| real | it cites a fact Mercury measures as abnormal: a port down (not the switch's own LOCAL port), a link not up, a drop flow, a port dropping packets or at 80% or more of its speed |
| info | its severity is info |
| false positive | any other finding |

## The cost

The line beside the button gives about what both calls cost (by an over-estimate of their
size) and that there are at most two; the AI mark's hover names the cap of each call. While the
snapshot holds no host table (one kept before the collection read hosts), the trace cannot be
asked for, and the line says so: **Collect now** keeps a snapshot that holds one.

## The evaluation

`scripts/nmas-sdn-b4-eval` compares both on fixed snapshots, each with its planted issues, a
number of runs each, and writes a report. It spends only with `--yes-spend`, and says first what
it would spend.

Besides the recorded cases, it can run on snapshots that **Collect now** kept on the lab's
switches: `--snapshots` names a copy of the network's analyst folder, which it only reads, and
`--clean` names the snapshots kept with every planted issue restored; leave the sheet as it is
when you restore them. Each snapshot whose seal holds is a case. Its planted issues are the ones
planted on the sheet by the time it was collected, each found by the same rule as the sheet's.
An issue you removed from the sheet was a mistake, so it counts for no snapshot. A clean
snapshot answered with a finding of medium or above counts as a benign one answered as a
threat; if the sheet still holds issues for it, the report says so. A snapshot whose seal fails, or that holds no
planted issue and is not named clean, is skipped, and the run says why. These cases are
reported as their own role; whether the trace tool improves results is still judged on the
blind cases alone.

Four more cases, the role `sitting`, model what both techniques got wrong on the lab's
switches on 2026-11-10, rebuilt on Mercury's test fabric: a flow that sends traffic for a host
out of a port leading away from it, which must be found (IPv4 and IPv6), and a flow dropping
DHCP replies beside a flow forwarding DHCP requests, which share no packet and must not be
reported as a conflict (DHCP and DHCPv6). A run that cites both of those flows in one finding
above info counts as a benign case answered as a threat. They are never blind and decide
nothing; `--roles sitting` runs them alone.

`--prompt 2` asks both techniques with the next version of the prompt, which says each
evidence item is one id and nothing else, so it can be measured before it replaces the
version in use. The report names the prompts it asked.

## Check this answer again

**Check this answer again**, under the findings, makes no AI call: it reads the recorded
answer again and checks it against the same snapshot and the reads that ran, draws the result
under the first one, and counts found, missed and the comparison's row from it, saying so
([Check this answer again](sdn-analyse#recheck)).

## Was this right?

Under the findings, **Was this right?** records your verdict on the answer
([Was this right?](ai-feedback)). **The call** opens the call's record in History.
