# SDN › Policies

The intent controller: a traffic policy in words, checked against the network's NetBox records
and its switches before any flow is shown, then previewed and confirmed by its hash. Opening the
tab reads only stored state (the committed NSOT export's hash and the network's flow intent);
it contacts no switch and no controller, and calls no model. How a draft works, step by step:
[An SDN policy in words](sdn-policy).

## Describe a policy

Type the policy as you would say it, and press **Draft the policy** (one recorded AI call,
capped; the model and the most a call can cost are beside it, with the committed NSOT export's
short hash the checks read). The answer is drawn under the box:

- **Checked against NetBox and the network**: the hosts named, where it applies, conflicts with
  installed flows, committed policies and protected flows, then **Preview the flows…**;
- **Which one?**: a word that names several hosts, asked before any AI call, with one button per
  host (**Draft with <host>**) and **Neither**;
- a refusal before any flow (**Unknown host**, **Impossible**, **Contradictory**, **Refused by a
  protected flow**, **Conflicts with an installed flow**, **Not a policy**), each naming what it
  compared; an impossible rate limit offers **Drop instead…** and **Rate-limit at <switch>
  instead…**;
- **One question first**: the model's own question, to answer in the policy's words.

Under the answer, **Preview the flows…** draws SDN › Flows' preview card: what it does, exactly
these requests, what will not happen, Verify, and **Send**, bound to the hash. Its result (the
outcome, what was sent, Verify's checks, any rollback and the record) is drawn in its place.

## Committed policies

Every policy confirmed here on this network, newest first: its id and words, its rules, the
switch it is on (a link to SDN › Flows, where its flows are listed), how many flows, and who
confirmed it and when, with its operation's id on History. A policy is withdrawn by removing
its flows on SDN › Flows (each flow's Remove), and one with a duration ends by itself; either
leaves this list. A flow intent that cannot be read is said here, and no policy can be drafted
until it can.
