# sdn_classify blind held-out set: candidate scenarios

**Purpose.** Candidate test scenarios for C1939, sdn_classify's blind held-out set, drawn from real
industry patterns (sources at the end). The operator confirms the expected answers, then an agent draws
a random, balanced subset and builds them as cases.

**How it stays blind.**
1. **The operator confirms or edits every "Expected" cell before any draw.** The expected answers below
   are proposals only. The operator's judgement is the answer key.
2. **Lock the file once confirmed.** Commit it and record its hash. After that, expected answers never
   change to match what the model says.
3. **Draw at random, stratified.** The drawing agent uses a recorded seed and takes **k per category**
   (suggested k = 3, about 24 cases), so every category is represented. The seed and the drawn ids are
   recorded.
4. **The case builder never sees the prompt or the schema's guidance.** It reproduces each drawn
   scenario on the lab topology, lets Mercury's detection capture the evidence pack, and writes the case
   with the locked expected answer. It may not edit an expected answer. If a scenario can't be
   reproduced, it reports that rather than substituting another.
5. **Held-out means held out.** These cases are only ever run to measure. When one fails and the prompt
   is then fixed, that case moves to the recorded set, and a fresh scenario is drawn to replace it.

**Disclosure.** The scenario list was drafted by an assistant that has seen sdn_classify's schema and
detection rules, though not the prompt text. The operator's confirmation of the expected answers is what
makes the answer key independent.

**Expected-answer key** (SDN lab policy as of 2026-10-27):
- **Scan** → `rate_limit_source`. **Flood** → `rate_limit_source`, or `drop_source` where allowed.
  **Unauthorised flow** → `remove_flow`. **Benign** → `threat_detected: false`, action `none`.
- **"Rule"** says whether Mercury's deterministic rule is expected to fire. When it says **No**, the
  classifier is never called. That case then tests detection, not the classifier, and a miss is a
  detection gap to register.
- **"Lab"** says whether the scenario can be reproduced in the Mininet/OVS/Ryu lab: Y, P (partial or
  approximate), or N.

---

## S: real scans (8)

| ID | Scenario (operator's words) | How to reproduce (sketch) | Rule | Expected | Lab | Basis |
|---|---|---|---|---|---|---|
| S1 | Fast vertical SYN scan of one host's ports 1-1024 | `nmap -sS -T4 -p1-1024` from h1 to h3 | scan | port_scan, medium/high, rate_limit_source (src h1) | Y | [7][8] |
| S2 | Full TCP connect scan of common service ports | `nmap -sT --top-ports 200` | scan | port_scan, medium, rate_limit_source | Y | [7] |
| S3 | UDP port scan | `nmap -sU --top-ports 100` | scan (if UDP counted) | port_scan, medium, rate_limit_source | Y | [7] |
| S4 | Stealth FIN/Xmas/NULL scan | `nmap -sF` / `-sX` / `-sN` | scan | port_scan, high (evasion intent), rate_limit_source | Y | [7] |
| S5 | Horizontal sweep: one port (telnet 23/2323) across every host, Mirai-style | hping3/nmap `-p23` across h2-h4 | **No** (one port per host) | detection gap: should be a scan of hosts | P | [4] |
| S6 | Slow scan: one port every 10 s (`nmap -T1`) | `nmap -T1 -p1-100` | **No** (under 20 in 60 s) | detection gap: low-and-slow | Y | [7] |
| S7 | Distributed scan: three hosts each probe 15 ports of one target | h1, h2, h4 → h3, 15 ports each | **No** (each under threshold) | detection gap: aggregate by target | Y | [7] |
| S8 | Web-exploit sweep: 80/443/8080/8443 across all hosts (Log4Shell-era pattern) | short port list × every host | No or borderline | port_scan of hosts; detection gap if missed | Y | [7] |

## BS: benign traffic that looks like a scan (7)

| ID | Scenario | How to reproduce (sketch) | Rule | Expected | Lab | Basis |
|---|---|---|---|---|---|---|
| BS1 | Authorised vulnerability scanner (Nessus/Qualys) sweeping a host | same as S1, from a "scanner" host | scan | **port_scan from the evidence** (the model cannot know it's authorised); suppression is the exemption's job, not the model's | Y | [7] |
| BS2 | Monitoring checks: 8 service ports on each host every 5 min (Nagios/PRTG) | loop of TCP connects to 8 ports per host | No (normally) | none; if it fires, no threat | Y | [7] |
| BS3 | Passive FTP or SIP/RTP between two hosts, using many high ephemeral ports | many short TCP/UDP flows on random high ports between h1 and h3 | possibly scan | **no threat** (full sessions, data on each, two peers); a known false-positive source for port-count rules | P | [7] |
| BS4 | Peer-to-peer client contacting several peers on varied ports | h1 → h2-h4, varied high ports, data exchanged | possibly scan | no threat, or low with a person deciding | P | [7] |
| BS5 | Load-balancer health checks: one port, every second, to each backend | `hping3 -S -p80 -i u1000000` to each host | No | none | Y | [7] |
| BS6 | Many short HTTP sessions from one client to one server (same port) | `ab`/curl loop h1 → h3:80 | No | none | Y | [7] |
| BS7 | Service discovery bursts (SSDP/mDNS multicast) at host start-up | multicast to 239.255.255.250:1900 / 224.0.0.251:5353 | No | none | P | [7] |

## F: real floods (7)

| ID | Scenario | How to reproduce (sketch) | Rule | Expected | Lab | Basis |
|---|---|---|---|---|---|---|
| F1 | UDP flood, fixed-size packets, one source | `iperf -u -b 50M` h2 → h4 | flood | flood, high, rate_limit_source (src h2) | Y | [1][2] |
| F2 | SYN flood: small packets, random source ports, no handshakes completed | `hping3 -S --flood -p80` h2 → h3 | flood (and maybe the scan fallback) | flood, high, rate_limit_source | Y | [1][2] |
| F3 | ICMP flood | `hping3 -1 --flood` | flood | flood, high, rate_limit_source | Y | [2] |
| F4 | DNS-reflection pattern: the victim receives large UDP from port 53 from several "resolvers" | h1, h2, h4 send 1400-byte UDP from src port 53 to h3 | flood | flood, high; **several sources, so action none and a person decides** (rate-limiting a resolver may harm legitimate DNS) | P | [1][2] |
| F5 | Short attack: a 40-second burst (record attacks lasted 35-45 s) | `iperf -u -b 50M -t 40` | flood at 30 s | flood, high, rate_limit_source; note it may end before a person answers | Y | [1] |
| F6 | Multi-source flood: three hosts flood one target together | h1, h2, h4 → h3 UDP | flood | flood, high; several sources, so none or per-source with a person deciding | Y | [1][2] |
| F7 | Flood just under the threshold (4× baseline, sustained) | rate tuned to 4× the port's baseline | **No** | detection gap only if harmful; documents the threshold | Y | [6] |

## BF: benign volume that looks like a flood (7)

| ID | Scenario | How to reproduce (sketch) | Rule | Expected | Lab | Basis |
|---|---|---|---|---|---|---|
| BF1 | Nightly backup: bulk TCP, full-size packets, one long session | `iperf -t 120` TCP h1 → h3 | flood | **no threat** (large packets, complete TCP session, many bytes per flow) | Y | [6] |
| BF2 | VM migration / database replication: one elephant flow at line rate | `iperf -P1 -t 90` at max rate | flood | no threat | Y | [6] |
| BF3 | Software-update fan-out: one server to every host at once | h3 → h1, h2, h4 TCP bulk | flood | no threat (TCP sessions, server-to-clients) | Y | [6] |
| BF4 | Throughput test (iperf), as in Lab 8's 3.3 checks | `iperf -t 10` | flood or scan fallback | no threat | Y | Lab 8 |
| BF5 | Video streaming: steady medium rate, UDP or TCP | `iperf -u -b 8M -t 120` (steady, mixed sizes if possible) | flood (if 5× baseline) | no threat, or low with a person deciding; a genuinely ambiguous case | P | [6] |
| BF6 | Microburst: a 5-second spike well under the window | `iperf -u -b 100M -t 5` | **No** (window 30 s) | none | Y | [6] |
| BF7 | Flash crowd: many clients ramping up to one server over minutes | gradual increase from h1, h2, h4 to h3:80 | possibly flood | no threat; ramp shape and complete sessions | P | [6] |

## U: real unauthorised flows (8)

| ID | Scenario | How to reproduce (sketch) | Rule | Expected | Lab | Basis |
|---|---|---|---|---|---|---|
| U1 | Redirect: a host's traffic sent out another host's port (interception) | `add-flow s2 "cookie=0xbad0,priority=100,ip,nw_dst=h3,actions=output:<h4 port>"` | unauth | unauthorised_flow, high, remove_flow | Y | [3] |
| U2 | Mirror: traffic still delivered **and** copied to an attacker port | `actions=output:<h3 port>,output:<h4 port>` | unauth | unauthorised_flow, **high** (silent exfiltration; traffic still works) | Y | [3] |
| U3 | Blackhole: a host's traffic dropped | `priority=200,ip,nw_dst=h3,actions=drop` | unauth | unauthorised_flow, high, remove_flow | Y | [3] |
| U4 | Shadow a mitigation: same match and priority as Mercury's rate-limit flow, action NORMAL | as Lab 8's 0xbad1 | unauth | unauthorised_flow, high (undoes an active mitigation), remove_flow + reinstall | Y | Lab 8 |
| U5 | Header rewrite: set_field changes the destination so traffic is diverted | `actions=set_field:<mac>->eth_dst,output:<port>` | unauth | unauthorised_flow, high, remove_flow | Y | [3] |
| U6 | Link-discovery manipulation: a flow overriding LLDP (eth_type 0x88cc) or the table-miss entry | `priority=65535,dl_type=0x88cc,actions=output:<port>` | unauth | unauthorised_flow, **critical** (poisons the controller's topology) | P | [3] |
| U7 | Flow-table exhaustion: 300 junk flows with random cookies | script of add-flow with random matches | unauth (many) | unauthorised_flow, high; also tests evidence-pack bounds | Y | [3] |
| U8 | Bypass: a high-priority allow flow above a policy or rate-limit flow | `priority=400,ip,nw_src=h1,actions=NORMAL` over Mercury's 300 | unauth | unauthorised_flow, high, remove_flow | Y | [3] |

## BU: unauthorised by cookie, but plausibly legitimate (4)

| ID | Scenario | How to reproduce (sketch) | Rule | Expected | Lab | Basis |
|---|---|---|---|---|---|---|
| BU1 | Engineer's emergency fix: a static flow that forwards exactly as the controller would | flow with an undeclared cookie, same output as the learned path | unauth | unauthorised_flow, **low/medium**; remove_flow proposed, but a person should consider adopting it | Y | 4.3 |
| BU2 | Monitoring application's sampling flow (copy to the controller) | `actions=output:<normal>,CONTROLLER` with its own cookie | unauth | unauthorised_flow, low; a person decides | P | 4.3 |
| BU3 | Controller restart reinstalls its flows with a different cookie | restart Ryu with a changed cookie, if configurable | unauth | unauthorised_flow, low; the cookie declaration is wrong, not an attack | P | ops |
| BU4 | Switch reboot leaves a vendor default (priority 0, NORMAL) | `ovs-ofctl add-flow s1 "priority=0,actions=NORMAL"` with cookie 0 | **No** (cookie 0 is the controller's) | none; documents that cookie 0 is trusted | Y | ops |

## N: normal traffic, no rule fires (5) (classify-normal path)

| ID | Scenario | How to reproduce | Expected | Lab |
|---|---|---|---|---|
| N1 | Idle fabric (LLDP only) | no traffic | none | Y |
| N2 | Light pings across all pairs | `lab8_pingall.sh 15 10` | none | Y |
| N3 | Mixed small traffic: DNS-like UDP, SSH-like TCP, HTTP | short scripted sessions | none | Y |
| N4 | Busy but normal: 50 short web sessions a minute | curl loop | none | Y |
| N5 | Right after a mitigation expired (meter removed, flows gone) | run after a response's hard timeout | none | Y |

---

## Suggested draw

- **k = 3 per category** from S, BS, F, BF, U and BU, and **2 from N**: about 20 cases, with a recorded
  seed.
- Scenarios marked **Rule: No** go into a separate **detection-gap list**, not the classifier's set,
  because they test the rules. They are still worth running: S5, S6, S7 and F7 are the patterns
  attackers use to stay under thresholds.
- Scenarios marked **Lab: N or P**, if drawn and not reproducible, are reported and redrawn within the
  same category.

## Sources

1. [Cloudflare DDoS threat report, 2025 Q1](https://blog.cloudflare.com/ddos-threat-report-for-2025-q1).
   SYN flood the most common L3/4 vector, then DNS flood and Mirai-launched attacks; 89% of L3/4 attacks
   ended within 10 minutes; record attacks lasted about 35-45 s; CLDAP and ESP reflection rising.
2. [Cloudflare Radar DDoS report 2025 Q1](https://radar.cloudflare.com/reports/ddos-2025-q1) and
   [eWeek: most common DDoS attack vectors](https://www.eweek.com/security/recognizing-the-most-common-ddos-attack-vectors-in-an-it-system/).
3. [Manipulating OpenFlow link discovery packet forwarding for topology poisoning (arXiv 2408.16940)](https://arxiv.org/pdf/2408.16940).
   Higher-priority flow entries override routing to redirect traffic; flows overriding the LLDP and
   table-miss entries poison topology; the "gap patching" that hides it.
4. [SANS ISC: the Mirai botnet, a look back](https://isc.sans.edu/diary/22786). Telnet on any port
   (23, 2323), about 200 addresses a second per infected host.
5. [PORTFILER: port-level network profiling for self-propagating malware (arXiv 2112.13798)](https://arxiv.org/pdf/2112.13798).
6. [ManageEngine: DDoS detection with network traffic analysis](https://www.manageengine.com/products/netflow/ddos-detection-network-traffic-analysis.html).
   Legitimate surges ramp over minutes; floods show uniform packet sizes; bytes per flow is the
   strongest discriminator; incomplete sessions mark attack flows.
7. [Effective detection rules for net and port scans (lopes.id)](https://lopes.id/2023-detection-netscan-portscan).
   Vulnerability scanners and monitoring systems as the main false-positive sources; allowlists used
   sparingly; one-minute windows; slow scans not addressed.
8. Nmap's documented scan types and timing templates (-sS, -sT, -sU, -sF/-sX/-sN; -T1 to -T5).
