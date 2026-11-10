# An SDN policy in words: the intent controller

On [SDN › Policies](sdn-policies), **Describe a policy** takes a traffic policy as you would say
it ("Block desk2 from reaching the web servers on TCP 443 for an hour") and turns it into flows on
the switch where the source enters the fabric. {{product}} checks every part of it against the
network's NetBox records and its switches before any flow is shown, and nothing reaches a switch
until you confirm the exact requests by their hash, through the same path as every flow change
on [SDN › Flows](sdn-flows).

**Draft the policy** makes one call to a hosted model (Anthropic's, the network's economy tier,
named beside the button), through {{product}}'s AI gateway: allowed only once hosted AI is
allowed on **Settings › Installation › AI (hosted)**, capped, and recorded with who asked. The
model only restates your sentence as a structured policy (kind, source, destination, protocol,
port, rate, duration) over the names {{product}} resolved; every decision after it is code. When
hosted AI cannot answer, the box and **Draft the policy** are disabled with the reason under
them, and **Add flow…** on SDN › Flows stays as usable as ever (see
[The AI mark](installation-settings#ai-mark)).

![A policy in words on SDN › Policies: quoted text is held back; every name is resolved in code against the committed NSOT export and the controller's learned hosts, a word naming several hosts asked back and an unknown one refused, with no call; one recorded, capped AI call returns a structured policy only; code checks it (names, impossible, contradictory within the request and against committed policies, the installed flows, the protected flows) before any flow is shown; it is compiled on the source's ingress switch and previewed by the flow-operation core; you confirm, bound to the requests' hash; every check runs again, the switch is held, each request is sent through the controller and the table read back, a failure rolled back; each flow is recorded as the policy, and later requests are checked against it.](diagrams/sdn-policy.svg)

## What a policy can say

- **block** (block, deny, drop, isolate): the traffic is dropped;
- **allow** (allow, permit): the traffic is sent to the switch's own forwarding (OpenFlow's
  NORMAL port), above every flow that could match it;
- **rate-limit** (limit, throttle, cap): one meter on the switch, a drop band at the rate in
  kbit/s, and the traffic sent through it to the switch's own forwarding. Only a switch that
  reports meters can hold one.

Each part names a **source** (a host, a NetBox tag such as `web`, an address or a subnet), a
**destination** (the same, or any), a **protocol** (tcp, udp, icmp or any), a destination
**port** (tcp or udp only), and how long it lasts (a flow's hard timeout, at most 65,535 seconds,
about 18 hours; none means until it is withdrawn). One request holds up to four parts. There is
no redirect: a redirect needs a port to send to, and no name says one.

## The steps

1. `quote`: text you put in quotes is taken out first, and an opaque placeholder put in its
   place, so the model never reads it as an instruction. A quoted text that is exactly a NetBox
   host's name, a tag or an address is put back as that name; any other is never a name.
2. `names`: each name is resolved by code, before any call, against the network's committed
   NSOT export (its end hosts, tagged `mercury-end-host`, by name, tag and address) and the
   controller's learned hosts (by address). A word that names several hosts (the stem of
   `db-1` and `db-2`, or a word that is both a host and a tag) is asked back with one button per
   host, **Draft with <host>** (its hover names the host's addresses), and **Neither**; your
   choice continues the same draft. A word shaped like a host's name
   (`desk9`) that names nothing is refused, naming the comparison: the name against the NetBox
   hosts and the controller-learned hosts. A switch's name is never taken for a host. Nothing is
   sent in either case, and nothing is spent.
3. `ask`: one recorded, capped call through the AI gateway, as you, given your sentence and the
   resolved names only. The model may answer a policy, one question back (drawn as it asked
   it), or why the sentence is not a policy.
4. `check`: the answer is parsed strictly and every rule checked in code, each refusal naming
   what it compared and both operands:
   - **not a policy**: a name the sentence did not resolve to, a rate on a rule that is not a
     rate limit, a rate limit with no rate;
   - **impossible**: a source of any, a source on no OpenFlow port (NetBox records no cable to
     a switch port with an `openflow_port`, and the controller has not learned it), a source
     whose hosts enter at more than one switch, the same host at both ends, a port without tcp
     or udp, a duration past 65,535 s, no address family both ends share, and a rate limit
     where the source's switch reports no meters. That last one offers **Drop instead…** and
     **Rate-limit at <switch> instead…** for a switch the controller links to it that reports
     meters; either is checked again in code with no call;
   - **contradictory**: two parts of the request whose matches overlap with different kinds
     ("allow desk2 to web-1 on 443 and block desk2 from all web servers on 443"), or a part that
     overlaps a **committed policy** of a different kind (or two rate limits on the same
     traffic): say which should win, or withdraw the committed one first;
   - **a conflict with an installed flow**: a policy sits above every flow that could match it,
     and may not lift or shadow a flow of {{product}}'s (a response's drop or meter);
   - **a protected flow**: a match that meets one of the network's protected classes (the
     controller's channel, management, the Services tagged `mercury-protected` such as DNS and
     DHCP, or the config context's), refused with a narrowing: name the protocol and port to
     block, or a destination, so it leaves the class alone.

   A policy that passes is drawn as **Checked against NetBox and the network**: the hosts named,
   where it applies (the switch, its platform and how the source was placed), the conflicts
   with installed flows, the committed policies and the protected flows.
5. `compile`: the policy becomes flows on the source's ingress switch, one per source and
   destination address of one family (IPv4 and IPv6 alike), each with the duration as its hard
   timeout and {{product}}'s cookie.

## Preview and Send {#preview}

6. `preview`: **Preview the flows…** opens the flow-operation core's preview: what each request
   does in words, exactly these requests (the REST method, path and body the controller is sent,
   each with its undo), what will not happen, what Verify checks, and the hash. Nothing is sent.
7. `confirm`: **Send** confirms as you, a verified person, bound to the hash. Every check above
   runs again on the policy, and it must compile to the same requests (a moved table or policy
   sends nothing); then the switch is held, each request sent through the controller, the table
   read back, and anything that landed rolled back on a failure, as on
   [SDN › Flows](sdn-flows).
8. `record`: each flow is recorded in the network's flow intent with its policy, which is what
   **Committed policies** lists and every later request is checked against; the operation is on
   History. A policy is withdrawn by removing its flows on SDN › Flows; one with a duration ends
   by itself.

Verify checks installation and counters; testing traffic between the hosts is yours.
