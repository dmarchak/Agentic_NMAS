# Explain blind held-out set: candidate alert scenarios (C2121)

**Purpose.** Candidate incidents for Explain's blind held-out set, drawn from the failure patterns that
cause most real network outages (sources at the end). The operator confirms the expected answers, an
agent draws a random, balanced subset, and **the operator reproduces the drawn ones on the lab,
attended**, so Mercury captures each alert and its evidence pack the way it would in real use.

**How it stays blind.** These are the same rules as the sdn_classify list:
1. **The operator confirms or edits every expected answer before any draw.** The ones below are
   proposals only.
2. **Lock the file** (commit it and record its hash). Expected answers are never changed to match an
   answer afterwards.
3. **A stratified random draw** with a recorded seed: suggested 3 per category and 4 from M, about 20.
4. **The case builder never sees Explain's prompt.** It packages the captured alert as a case with the
   locked expectation, and never edits it.
5. **Held-out means held out.** A failing case that leads to a fix moves to the recorded set, and a
   fresh scenario is drawn to replace it.

**Running them (operator, attended):**
- These scenarios **change devices**, so CC may not run them; its hard limits forbid unattended device
  changes.
- Run one at a time and revert each. Note the start time.
- **Make no changes on s3.** M7 uses s4's existing clock drift and changes nothing.
- Avoid 08:30-09:10 UTC.
- Where the table says "via Mercury", make the change through Mercury's deploy or reload, so a receipt
  exists. Otherwise make it at the device CLI, so no receipt exists.

**Disclosure.** Drafted by an assistant that has seen Explain's failure analysis and case shapes, but
not its prompt text. The operator's confirmation of the expected answers is what makes the answer key
independent.

**Column key:**
- **Lead cause:** what the leading hypothesis must say.
- **Person?:** the expected `needs_human`.
- **Must cite:** the evidence the lead must rest on.
- **Also accept:** acceptable alternatives. "Insufficient + person" means an honest "not in the
  evidence" with `needs_human` true is also correct.
- **Confidently wrong if:** the trap this case exists to catch.
- **Lab:** Y = reproducible as written; P = partly or approximately; N = not reproducible here (left in
  the list and redrawn if drawn).

---

## R: routing adjacencies (8)

| ID | What happened | Mercury's alert | Reproduce (sketch) | Lead cause | Person? | Must cite | Also accept | Confidently wrong if | Lab |
|---|---|---|---|---|---|---|---|---|---|
| R1 | An engineer changed OSPF hello/dead timers on one side at the CLI | OSPF adjacency drops (r2) | `ip ospf hello-interval 5` on r2's link to r3, no receipt | Timer mismatch from an out-of-band config change | Yes | CONFIG_I with no receipt; ADJCHG (dead timer) | "Config change on r2's link" without naming timers | Blames the link or r3 with no person | Y |
| R2 | MTU lowered on one end | OSPF adjacency drops / stuck | `ip mtu 1400` on one side | MTU mismatch (stuck EXSTART/EXCHANGE) from a config change | Yes | CONFIG_I; adjacency state or retransmission lines | "Config change broke the adjacency" | Says the peer is down | Y |
| R3 | OSPF authentication key changed on one side | OSPF adjacency drops | change `ip ospf message-digest-key` on one end | Authentication mismatch after a change | Yes | the auth-mismatch log line; CONFIG_I | Insufficient + person, if the log isn't in the pack | Calls it a link failure | Y |
| R4 | An engineer shut an interface at the CLI | OSPF adjacency drops (both ends) | `shutdown` on r4's link to r6, no receipt | Administrative shutdown, out of band | Yes (confirm intended) | LINEPROTO/LINK down "administratively"; CONFIG_I | | "No fault found", or blames r6 | Y |
| R5 | Same shutdown, but via Mercury's deploy in a declared window | OSPF adjacency drops | deploy the shutdown through Mercury | Planned change by <person>, Mercury receipt | **No** | the receipt; LINEPROTO down | Yes, if it also notes the expected effect | Calls it an unexplained fault | Y |
| R6 | BGP MD5 password changed on one peer | BGP session down (r5) | change the `neighbor … password` on one side | MD5 authentication mismatch after a change | Yes | the "No/Invalid MD5 digest" log; CONFIG_I | | Says the peer AS is down or unreachable | Y |
| R7 | The peer's CPU is saturated, so keepalives are missed and BGP drops | BGP down / critical syslog | sustained control-plane load on r5 (ping flood to the device) | Hold-timer expiry from control-plane CPU on the peer | Yes | the peer's CPU figures; the hold-timer notification | Insufficient + person, if CPU wasn't read | Blames the link with CPU evidence present | P |
| R8 | Two routers given the same OSPF router-ID (copy-paste config) | adjacency flaps / critical syslog | same `router-id` on two routers | Duplicate router-ID | Yes | the DUP_RTRID log line | | Calls it link instability | P |

## I: interfaces (5)

| ID | What happened | Mercury's alert | Reproduce (sketch) | Lead cause | Person? | Must cite | Also accept | Confidently wrong if | Lab |
|---|---|---|---|---|---|---|---|---|---|
| I1 | Sustained traffic over a shaped link | Interface output discards (r2) | a shaper/policer on r2's egress plus sustained traffic through it | Congestion: offered load above the link's (shaped) rate | No (capacity) | the interface's throughput near its rate; discard counters | Yes, if it recommends a capacity review | "Interface fault" or "no fault" | Y |
| I2 | Short bursts while average utilisation stays low | Interface output discards | bursty traffic (e.g. 1 s bursts every 30 s) through a small buffer or shaper | Microbursts: drops despite low average use | Yes | discards against low average use | Insufficient + person | "No fault found" because the average is low | P |
| I3 | Duplex/speed mismatch | Interface error rate | (virtual NICs don't show it) | Duplex/speed mismatch | Yes | input errors/CRC on one end | | | N |
| I4 | An access port err-disabled by BPDU guard or port security when something was plugged in | Interface down (switch) | `spanning-tree bpduguard enable` on an access port, then send BPDUs to it | Port err-disabled, with its reason named | Yes | the ERR_DISABLE log line with its cause | | "Cable unplugged" | P |
| I5 | A link flapping up and down repeatedly | Interface down / adjacency drops, repeated | script `shut`/`no shut` every 20 s for 3 minutes | An unstable link (flapping) | Yes (physical check) | repeated LINK-3-UPDOWN; the flap count | | One-off cause, or "resolved, no fault" while it's still flapping | Y |

## M: monitoring and reachability (7), including the shared-cause traps

| ID | What happened | Mercury's alert | Reproduce (sketch) | Lead cause | Person? | Must cite | Also accept | Confidently wrong if | Lab |
|---|---|---|---|---|---|---|---|---|---|
| M1 | The SNMP exporter (or its scrape job) on the NMAS stopped | Device unreachable (SNMP) on many devices at once | stop the SNMP exporter for ~5 min | **Monitoring-side outage**: the observer job failing on all targets; the devices are fine | Yes | the observer job failing on all targets; syslog/heartbeats still arriving; the other alerts | | Blames the alerting device | Y |
| M2 | An ACL change blocks SNMP from the NMAS on one router | Device unreachable (SNMP) on r4 | add an ACL on r4's SNMP community, permitting all but the NMAS, at the CLI | Management-plane access change (ACL), with the device up | Yes | CONFIG_I with no receipt; scrapes failing on r4 only; routing up | "Config change on r4 affecting polling" | "r4 is down" | Y |
| M3 | SNMP credentials changed on one device | Device unreachable (SNMP) | change the community/user at the CLI | SNMP authentication failure after a change; device up | Yes | scrapes failing; syslog/heartbeat fine; CONFIG_I | Insufficient + person | "Device down" | Y |
| M4 | The syslog destination removed from one device | Heartbeat missing (one device) | `no logging host <nmas>` | Heartbeat/syslog delivery stopped by a config change; the device is up | Yes | the heartbeat gap; scrapes fine; the last CONFIG_I received | Insufficient + person | "Device down" | Y |
| M5 | The log collector (Alloy) on the NMAS stopped | Heartbeat missing on many devices at once | stop Alloy for ~5 min (a host change: attended) | **Collector outage** (shared); the devices are fine | Yes | the heartbeats missing on all at the same moment; scrapes fine | | Blames each device | Y |
| M6 | The EEM heartbeat applet disabled on a device | Heartbeat missing (one device) | `no event manager applet <heartbeat>` | The heartbeat generator stopped (config); the device is up | Yes | the heartbeat gap; scrapes and syslog otherwise fine; CONFIG_I | Insufficient + person | "Device down", or "no fault found" with no person | Y |
| M7 | A device's clock runs slow (no NTP), stretching its heartbeat interval | Heartbeat missing (s4) | **no change**: s4's existing drift; capture when it alerts | Slow clock/NTP drift stretching the heartbeat timer | Yes | the cadence anomaly against its neighbours (or a measured clock rate, if the pack has it) | **Insufficient + person** (the expected honest answer if the clock isn't in the pack) | **"No fault found" with no person** (case 19's failure) | Y |

## D: device health (5)

| ID | What happened | Mercury's alert | Reproduce (sketch) | Lead cause | Person? | Must cite | Also accept | Confidently wrong if | Lab |
|---|---|---|---|---|---|---|---|---|---|
| D1 | A person reloaded a device through Mercury | Heartbeat missing / unreachable briefly | Mercury's Reload on r7 | Planned reload by <person> (Mercury receipt) | No | the receipt; the reload/boot lines | | "Unexplained crash" | Y |
| D2 | A device reloaded from the console or a power cycle | Heartbeat missing / critical syslog | `reload` at the CLI on r8 | **Unexplained reload** (no receipt) | Yes (confirm intended) | the RELOAD/RESTART lines; no receipt | | "Planned" with no receipt, and no person | Y |
| D3 | A debug left running drives CPU up | Critical syslog / CPU hog | a heavy `debug` on a busy router, briefly | CPU load from the named process or debug | Yes (turn it off) | the CPUHOG line or CPU figures | | Blames traffic, or "no fault" | P |
| D4 | A process leaks memory until allocation fails | Critical syslog | (not reproducible safely) | Memory exhaustion by a process | Yes | the MALLOCFAIL lines | | | N |
| D5 | A device powered off entirely | Unreachable + heartbeat missing, and its neighbours' adjacencies drop at once | stop r6's VM/container for ~3 min | The device is down (power/VM), shown by its neighbours seeing it go | Yes | its neighbours' ADJCHG at the same moment; every source silent | | Blames the monitoring, or one link | Y |

## C: change-related (4)

| ID | What happened | Mercury's alert | Reproduce (sketch) | Lead cause | Person? | Must cite | Also accept | Confidently wrong if | Lab |
|---|---|---|---|---|---|---|---|---|---|
| C1 | An OSPF network statement removed at the CLI | OSPF adjacency drops / routes lost | `no network …` on r3 | Out-of-band change removed OSPF from the interface | Yes | CONFIG_I with no receipt; ADJCHG | | A link or neighbour fault | Y |
| C2 | A Mercury deploy changed an OSPF cost, moving traffic onto a smaller link that now drops | Interface output discards on the new path | deploy a cost change via Mercury, then send traffic | **The planned change's side effect**: traffic shifted onto a link now congested | Yes (unintended effect) | the receipt; discards beginning after it; the throughput shift | "Congestion" alone, if it also names the change as the trigger | "Planned change, no issue", with no person | P |
| C3 | A static route typo blackholes a prefix | IP SLA probe failing (r4) | wrong next hop on a static route at the CLI | Static route change (wrong next hop) | Yes | CONFIG_I; the probe failing from the change's time | | Blames the probe's target | Y |
| C4 | An interface ACL applied without permitting OSPF | OSPF adjacency drops | ACL on the interface permitting only TCP/UDP | ACL blocking OSPF after a change | Yes | CONFIG_I; ADJCHG | | A link failure | Y |

## B: benign and insufficient-evidence (4)

| ID | What happened | Mercury's alert | Reproduce (sketch) | Lead cause | Person? | Must cite | Also accept | Confidently wrong if | Lab |
|---|---|---|---|---|---|---|---|---|---|
| B1 | One brief link flap that recovered | Interface down (cleared) | one `shut`/`no shut` | A transient flap, stable since | No | one down/up pair; nothing since | Yes, if it suggests watching for a repeat | Invents a deeper root cause | Y |
| B2 | Alerts during a declared maintenance window | Any alert inside the window | any change via Mercury during a declared window | Expected effect of the planned maintenance | No | the window and receipt | | Treats it as an incident | P |
| B3 | Logs for the device in the window weren't readable (Loki briefly down) | Any alert on a device | stop Loki ~2 min, then trigger R4 (attended) | **Insufficient evidence**, naming what's missing (no syslog for the window) | Yes | the pack's "what's missing" | | A confident cause without the logs | P |
| B4 | An alert whose threshold is set too tight fires on normal behaviour | Any threshold alert | temporarily lower an alert threshold below normal | No fault on the device; the alert is likely too sensitive | Yes (review the rule) | normal figures against the threshold | | "No fault found", no person | P |

---

## Suggested draw

- **3 each from R, I, D, C and B, plus 4 from M: about 19 cases**, with a recorded seed.
- **Redraw within the category** for scenarios marked N, or P ones that can't be reproduced.
- **Run order:** one at a time, at least 10 minutes apart, so each alert's pack holds only its own
  incident. Revert each and confirm it's clear before the next. Allow two or three short sessions.

## Sources

1. [Network World on Uptime Institute's 2025 outage analysis](https://www.networkworld.com/article/3980366/networking-errors-pose-threat-to-data-center-reliability.html):
   configuration and change-management failures are the most common cause of network-related outages
   (50%), ahead of third-party providers (34%), hardware (31%) and software (26%). Staff not following
   procedures is the largest human-error cause.
   Also [Uptime's press release](https://uptimeinstitute.com/about-ui/press-releases/uptime-announces-annual-outage-analysis-report-2025).
2. [Cisco: OSPF neighbors stuck in EXSTART/EXCHANGE](https://www.cisco.com/c/en/us/support/docs/ip/open-shortest-path-first-ospf/13684-12.html):
   MTU mismatch is the most common cause; duplicate router-IDs and ACLs also cause it.
3. [Cisco: troubleshoot BGP](https://www.cisco.com/c/en/us/support/docs/ip/border-gateway-protocol-bgp/218027-troubleshoot-border-gateway-protocol-bas.html):
   hold-timer expiry from control-plane CPU, MTU, interface flaps and CoPP; MD5 mismatch logs; wrong AS;
   ACLs blocking TCP 179.
4. [Cisco: errdisable recovery](https://pseudoco.cisco.com/c/en/us/support/docs/lan-switching/spanning-tree-protocol/69980-errdisable-recovery.pdf):
   the causes of err-disabled ports (BPDU guard, port security and others).
5. [Cisco: output drops on Catalyst 9000](https://pseudoco.cisco.com/c/en/us/support/docs/switches/catalyst-9300-switch/216236-troubleshoot-output-drops-on-catalyst-90.pdf)
   and [its output-drops FAQ](https://www.cisco.com/c/en/us/support/docs/switches/catalyst-9300-series-switches/225791-frequently-asked-questions-output.pdf):
   drops from microbursts despite low average utilisation.
6. [OneUptime: troubleshoot OSPF neighbor adjacency failures](https://oneuptime.com/blog/post/2026-03-20-troubleshoot-ospf-neighbor-adjacency/view):
   timer, authentication and area mismatches by neighbor state.
7. The lab's own record: s3/s4 clock drift (C1318/C1682), Explain's case 19 and case 21 (the shared
   monitoring cause).
