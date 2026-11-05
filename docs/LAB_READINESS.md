# Lab readiness: Lab 10 and the final SDN lab

Read-only, written from the documents and the repository at HEAD `d200788d`, 2026-11-05 ~02:0x
UTC (2026-11-04 20:0x, UTC−6). No host, device or register row was touched. One row per graded
objective. The points are the operator's (2026-11-05); none is estimated. Estimates are
agent-days, as each cited document gives them; one agent-day is about 1.3 wall-clock hours
(0.7 to 2.6) and about 4M weighted tokens (PHASE8_PLAN 0.3). A status with no evidence is
"not shown". The queue is PHASE8_PLAN 0.3, workstreams 1 (Lab 10) and 2 (the final SDN lab).

## The head

- **Lab 10:** due Mon 2026-11-23 23:59 MT (2026-11-24 06:59 UTC), **19.2 days left**. 8 objectives (R1 to R4, V1 to V4): 0 done, 4 built and not walked, 2 in progress, 2 not started.
- **The final SDN lab:** due 2026-11-30 (no hour recorded), **about 25 days left**. 11 graded rows (100 points), 3 bonus rows (+9) and 1 rule row: the rule done, 14 left.
- **Open decisions, Lab 10: 0.** HEAL_TO_INTENT 18 (N1 to N13) and 19.10 (N14 to N24) are decided; 19.10 by the operator's approval in commit `c94d8b08`. What waits on the operator is trials, a password, switches turned on and sittings (the table).
- **Open decisions, the final SDN lab: 5 of LAB9_SDN_GAP 5's seven** (1, 3, 4, 6 and 7). Decision 1 is answered in the gate, 2026-11-05. Also open: 7 of section 6's 8 questions, the TA's answer on B4 (section 4) and the board's sign-off (section 7).
- **Critical path, Lab 10:** stream B is 11.25 to 14.25 agent-days left (H9's and H25's remainders unsplit), about 15 to 19 h of one agent plus about 5.5 h of gates. That is against 19.2 days, 9.9 of them in the build window (to Nov 14). The agent time fits. The binding chain is the operator's: the trials (C2424, C2425, C2418), the read-only account's password (C2420), then the walks (Nov 15 to 19) and the recording (Nov 20 to 22).
- **Recomputed 2026-11-05 ~02:2x UTC on the operator's scope correction** (A1 is the team's build
  by hand; Mercury starts at ZTP and A2):
  - the hardware chain is about **16.5 agent-days**: the readings, then templates, ZTP and
    discovery (about 2.5), the per-vendor confirm-and-push path (about 3, inferred, in place of
    item 1's 9.5), item 2's onboarding (3), hardware integration (3) and link failure (5);
  - total demand is about **50 agent-days against about 36.5 lane-days, about 14 short**: the
    drivers fall by 6.5, the laptop install's 3 landed as the kit, and loop-free forwarding's 1 to
    1.5 moves to the team;
  - the points Mercury carries are 80 and the 9 bonus points: A1's 20 are the team's;
  - the lines below are the board as first drawn, before the correction.
- **The binding constraint, named (2026-11-05 ~02:3x UTC, the operator's question).** "About
  36.5 lane-days" is LAB9_SDN_GAP section 3's calendar assumption: one agent-day per lane per
  calendar day (10 × 1 + 5 × 1.5 + 4 × 1.75 + 7 × 1.75). It is neither gate throughput, nor
  usage, nor the lanes. Under the calibration (PHASE8_PLAN 0.3: one agent-day ≈ 1.3 h of one
  agent, ≈ 4M weighted tokens):
  - **agent time:** 50 agent-days ≈ 65 agent-hours, about 33 h of wall time on two lanes;
  - **gates:** serial and run alone, about one per 1.35 agent-days (LAB9_SDN_GAP's own 46 → 17 h),
    so about 37 gates. At 16 to 17 min each (measured 2026-11-05 with 1 worker, MemAvailable
    11.6 GiB) that is about 10.5 h; about 6 h if the operator's freed memory gives 2 workers
    (inferred, measured on the next gate);
  - **usage:** 50 × 4M ≈ 200M weighted tokens, about 16% of a week (a week ≈ 1.26B by
    HEAL_TO_INTENT 19.7's 151M ≈ 12%); Lab 10's remainder adds about 50M;
  - **what binds:** the serial path (the main session's bring-in, the fast checks, one gate at a
    time, the deploys) and the operator's hardware sittings, since the hardware rows cannot move
    before the readings. Calendar lanes do not bind: about 43 to 50 h of active session over 25
    days, under 2 h a day;
  - **after the operator's decisions 1 to 3 below, no gap remains at the calibration.** "More
    usage" is not needed. What would reopen a gap is a hardware row's checkpoint missed, and
    that row then goes by hand (decision 3).
- **Decision 7, the operator's choices (2026-11-05):**
  1. **B1 goes behind B3.**
  2. **A2 is OVS first:** the NSoT-driven OpenFlow configuration works end to end on the
     servers' Open vSwitch before the vendor templates, which then add to it.
  3. **Each row has a checkpoint date.** If its Mercury path is not working by then, the team
     does that row by hand for the grade, and the gap stays registered for Mercury after the
     labs.

  "More usage" waits until after 1 to 3: none needed (above).

**The order and the checkpoints (the final SDN lab, due 2026-11-30; Lab 10 stays first, its
build to Nov 14 and its walks Nov 15 to 19).**

**The checkpoint dates are tripwires, not targets** (the operator, 2026-11-05): each is the latest
a row's Mercury path may slip before the team takes it by hand. Work goes at full speed, and each
row starts the moment its prerequisites land. Finishing weeks early is the expected case. Rows are
reported as they land, never against their dates. A date is read only when a row has not landed
by it.

A checkpoint means the row's Mercury path works end to end on the lab's hardware or its fabric.
Each date leaves the team at least three days by hand before the due date.

| Order | Row | Checkpoint | Mercury's path by then | If missed |
|---|---|---|---|---|
| 1 | A2, OVS first | **Nov 12** | NetBox to the servers' OVS OpenFlow configuration, previewed, confirmed and verified from the controller's switch list | the team configures OVS by hand |
| 2 | A4 DHCP | Nov 14 | DHCP steering with the router's DHCP (the team's A1) | by hand |
| 3 | A5 trace (+3 ports) | Nov 18 | the trace by DPID, ports for the bonus | the controller's own REST by hand |
| 4 | A2, vendor templates | Nov 19 | each vendor's template confirmed by its capture and added to OVS's path (the first sitting's captures, then later sittings) | the switches' OpenFlow by hand; templates stay draft |
| 5 | A3 DNS blacklist (+3 reply) | Nov 21 | the steering app and the filter service | by hand on the controller |
| 6 | B3 closed loop (+3 link failure) | Nov 24 | scan, flood, unauthorised flow and link failure, HITL and AUTO (a network marked lab) | the loop's demo on Lab 8's fabric, the hardware by hand |
| 7 | B2 intent controller | Nov 24 | words to a confirmed flow policy, validated against NetBox | the four core intents only, then by hand |
| 8 | B4 advanced technique | Nov 25 | the AI read loop (H25 onward), with the TA's answer | the evaluation reported "not measured blind" |
| 9 | B1 AI analyst (behind B3) | Nov 26 | the analyst over the four devices' live state | Explain over an evidence pack |
| 10 | B5 reliability, safety and cost | Nov 26 | the export, the economy tier, protected flows | the written analysis alone |
| — | A6 REST | with each row | every SDN read and write through the controller's REST (the driver) | — |
| — | A1 network build | the team's | the hardware build and base setup by hand | — |
- **Critical path, the final SDN lab (as first drawn):** the hardware chain is about 21.5 to 22 agent-days, about 28 h of one lane. It runs: the switch readings, then item 1's drivers (9.5), onboarding (3), link failure and the loop (5, plus 1 to 1.5 for loop-free forwarding, inferred) and hardware integration (3). It cannot start before the readings. **Total demand is about 59 agent-days against about 36.5 lane-days, about 22 short** (LAB9_SDN_GAP 3, with B4 at section 5's 6.0). "No cuts for time" stands (section 5), so the gap's lever is decision 7.
- **Most exposed, Lab 10: R1.** Nothing is walked, and R3 and V1 wait on unmeasured removal shapes (C2373). R8 waits on an unmeasured process reset (C2374). The diagnosis runbooks (5.75, never cut) are not started (C2413).
- **Most exposed, the final SDN lab: A1, 20 points.** It is blocked on hardware not yet read, unbuilt drivers, an uncounted loop-free forwarding app, and redundant-link survival at the end of the chain. HEAL_TO_INTENT 19.7 names B4 instead (8 points; the last link of Lab 10's stream B).
- **Points at risk, the final SDN lab: all 100 and the 9 bonus points.** 38 wait on the hardware (A1, A2, B3). 46 are not started and need no hardware (A3, A4, A5, B1, B2, B5). 16 are in progress (A6, B4).
- **Point values not recorded:** every Lab 10 row ("none given"); the API-key rule row; and the final SDN lab's other integration rules (protected flows, one source of truth, one controller path, model output, economy tier, stop conditions), which have no row of their own.

## Lab 10: heal to intent (board H)

The handout's own words are not in the repository: docs/LAB_REQUIREMENTS.md has no Lab 10
section. The rows are the operator's request of 2026-11-05. The design is
docs/HEAL_TO_INTENT.md. Parts H1 to H31 are its sections 16 and 19.7.

| # | Objective | Points | Status | Evidence | Left: the agent (agent-days) | Left: the operator |
|---|---|---|---|---|---|---|
| R1 | Detect and remedy common troubleshooting scenarios | none given | in progress | H1 to H6: `24aef7b6`, `70b09ab5`, `9034432f`, `ca8a9517`, `644917bd`; tests/test_heal_triggers.py, test_heal_decide.py, test_heal_act.py, test_heal_propose.py, test_heal_detect.py; C2371, C2373, C2374, C2413, C2414 | H11 removal shapes and process reset on r2 and s1 (0.5); H14 to H18 diagnosis runbooks (5.75); H12 replays (0.75) | none beyond R2's |
| R2 | Correct basic issues automatically, without human interaction | none given | built, not walked | H1 policy, AUTO at most 7 days (`24aef7b6`, `policy.MAX_AUTO_SECONDS`); H4 act (`9034432f`); Lift the halt (`91e0d717`); tests/test_heal_policy.py; C2393, C2399 | H11's dry-run walk of each Tier 1 kind (section 7, step 1); H9's rest (C2399's Right / Wrong, C2401's held row; within 1.75); H19 to H23 actions (6.75), the bounce last in the cut order (19.8) | mark Default lab: Settings · Default, the SDN card's Stage (N8) |
| R2 | (the enablement, continued) | | | HEAL_TO_INTENT 7 and 9; N8 | | Self-healing tab: Auto, one Tier 1 kind at a time, each after its dry run passes |
| R2 | (the enablement, continued) | | | `policy.MAX_AUTO_SECONDS` | | expiry required, at most 7 days, then dry run: on at the first walk, Nov 15, until Nov 22; once more if recording runs late |
| R2 | (the trials) | | | C2424, C2425, C2418 | | the r4 and s1 revert-timer trial; the lab-host flap trial |
| R3 | When it can't correct a problem, notify an engineer and list the steps taken | none given | built, not walked | H7 notifier (`24aef7b6`); H8 analysis and notice (`6dea173e`, `modules/heal/detect.py` `_notify_step`); tests/test_notify.py, test_heal_notice.py, test_heal_analysis.py, test_heal_analysis_never_read.py; C2443, C2485, C2488, C2378 | H13 measurement (0.5, about $1); the other notices (C2485, no estimate); H24, H26, H27, H28 and H25's wiring (up to 5.5; H25's core built, `e6493d19`) | a relay and a team (Settings › Installation › Notifications; any secret typed by the operator) |
| R3 | (continued) | | | C2419, C2420; CLAUDE.md, "AI cost safety" | | turn on the heal analysis in Settings › Installation › AI; the read-only account's password; the device state class on, with a reason |
| R4 | When a change is made, update the documentation and test it | none given | built, not walked | H6: golden commit and trailers, change record, NetBox journal, History source (`644917bd`); H4's golden re-check (`9034432f`); tests/test_heal_records.py | H10 manual pages (0.75); the walk | none beyond the walks |
| V1 | Video: problems corrected | none given | not started | HEAL_TO_INTENT 15, rows 1 to 6; C2373 (R3, V1), C2374 (R8) | the demo script (PHASE8_PLAN 0.1, item 5); captured fixtures (H11) | each scenario's change at the CLI (section 15); the walks, Nov 15 to 19; the recording (no video work by the agent, PHASE8_PLAN 0.3) |
| V2 | Video: a problem it attempts and can't correct | none given | not started | HEAL_TO_INTENT 15, rows 7 to 9 (C4, I5, V1 rolled back); C2418, C2391 | V1's sheet from the lab's intent (row 9); H17's diagnosis on Alert incidents | the lab-host flap trial for I5 (C2418); the recording |
| V3 | Video: unit testing and code coverage for the self-healing tool | none given | in progress | 15 test files (tests/test_heal_*.py, test_notify*.py, test_ai_read_loop.py), red then green (section 14); `scripts/nmas-coverage` (`--html`, `--summary`) | H12: the replays and the report filtered to `modules/heal/` (0.75) | the recording |
| V4 | Video: specific examples of the documentation | none given | built, not walked | H6's records (`644917bd`); section 15's "video's beats" | H10 (0.75, counted in R4) | the recording |

## The final SDN lab

Its requirements against Mercury are docs/LAB9_SDN_GAP.md section 1, and its items and estimates
are section 2. No register row is tagged "Lab 9: blocks" but C2379 and C2427. The laptop kit
(docs/LAB9_LAPTOP_RUN.md) and the read-only discovery (docs/LAB9_DISCOVERY.md) are in the gate,
2026-11-05, and are not counted here.

| # | Objective | Points | Status | Evidence | Left: the agent (agent-days) | Left: the operator |
|---|---|---|---|---|---|---|
| A1 | Network build | 20 | **the operator's team, by hand** (the operator's scope correction, 2026-11-05) | the hardware build and base setup, and loop-free forwarding with them (formerly 1 to 1.5 agent-days, inferred) | none: Mercury's first involvement is ZTP and A2. The laptop install (formerly 3) is the kit, landed 2026-11-05 | the build and base setup; its design document; the switch readings at the first sitting |
| A2 | NSoT-driven OpenFlow configuration | 8 | in progress (2026-11-05) | section 1 A2 (partial: `RyuDriver._switches` read); read-only discovery (docs/LAB9_DISCOVERY.md); the OpenFlow templates, ZTP profiles and discovery reads in build, draft until a capture confirms each | templates, ZTP and discovery (about 2.5, under way); the confirm-and-push path per vendor once captures confirm (about 3, inferred, in place of item 1's full drivers, 9.5); item 2 onboarding (3); hardware integration (3); the board's sign-off, self-signed under the Phase 7 mode (section 7) | the captures from each switch; decision 6 (AOS-CX's netmiko) |
| A3 | DNS blacklist | 10 | not started | section 1 A3 (missing); no commit | steering app (2); the filter service (2) | decision 4 (dnspython's licence); question 6 (the verdict service; any key typed by the operator) |
| A4 | DHCP | 6 | in progress (2026-11-05): the router's pool as intent, built, not yet on a device | section 1 A4; "A4: the router's pool" below; the DHCP server pack (`modules/nsot/features/dhcp.py`), tests/test_feature_pack_dhcp.py | DHCP steering (1.25); the pool's remainder (about 0.75, below) | the router's running config once a pool is on it (one capture, below) |
| A5 | SDN trace | 8 | not started | section 1 A5 (missing); C1911 | the trace by DPID (2.5) | none |
| A6 | REST implementation | 8 | in progress | section 1 A6 (exists for flows and meters); C2427 | groups (in item 6's reroute, 1.5); port description (in item 7, 1) | question 5 (the controller server) |
| B1 | AI Network Analyst | 8 | not started | section 1 B1 (partial: collection only); C2495 | item 7 (3.5) | the planted issues, in a sitting |
| B2 | Intent Controller | 9 | not started | section 1 B2 (missing for SDN; board S9 drawn) | item 4 (7.5) | none |
| B3 | Closed-Loop Responder | 10 | in progress | Lab 8's loop (`modules/sdn/loop.py`, `detect.py`, `modes.py`); C2305 open, B | C2305 (1.25); item 6 (5) | decision 3: the lab's network marked lab for AUTO, at most a day per enablement (`modes.MAX_AUTO_SECONDS`) |
| B3 | (continued) | | | | | question 7 (the redundant link); the 5-minute and false-positive runs on the hardware |
| B4 | Advanced Technique | 8 | in progress | H25's core (`e6493d19`), hand check (`6638af7f`), D1 to D4 (`77a78a82`); tests/test_ai_read_loop.py; C2419, C2427 | the rest of 6.0, up to about 10 (section 5): H24, H28's class (0.5), H26, H29 to H31 | the TA's answer (section 4); the fresh blind set's capture, 2 h 45 min (PHASE8_PLAN 0.4); the device state class on (D2) |
| B5 | Reliability, Safety, and Cost | 5 | not started | section 1 B5 (partial: `modules/ai/calls.py` `record`); C2379 | item 10 export (1.75); item 8 economy tier (1.5); item 5 protected flows (2.5) | the AI-use disclosure and the production-readiness analysis (section 1 B5) |
| +3 | DNS modified reply | +3 | not started | section 1 A3 | the block page (0.5) | none |
| +3 | Trace ingress and egress ports | +3 | not started | section 1 A5 | the trace's ports (0.5) | none |
| +3 | Automated response to link failure | +3 | not started | section 1 B3; section 5, "link failure is repaired locally" | in item 6's reroute (1.5) | decision 3; the hardware |
| Rule | The API key is kept out of the code repository | none given | done (evidence) | the key sealed in `modules/secrets_store.py` (`anthropic_api_key`), docs/SECRETS.md; tests/test_nothing_personal_is_published.py; tests/test_p3_secrets_write_only.py | none | none |

Two estimates of section 2 sit across rows: the manual and fidelity records (2.5) and
hardware integration (3, under A1).

### A4: the router's pool

Written 2026-11-05. **A4 is two things** (LAB9_SDN_GAP section 1, A4; section 5, "DHCP
steering"): the router serves DHCP from its own pool, and the OpenFlow edge forces clients'
requests to it. Under the operator's scope correction (2026-11-05) the team builds the hardware
by hand (A1), and the pool is Mercury's: IOS intent, rendered, previewed, confirmed by hash, sent
merge-only, verified and recorded by the pipeline every intent change already takes
(`modules/pipeline.py`). Not Kea: Mercury's DHCP page (`routes/dhcp_v2.py`) fronts Kea, and
nothing of it is used here.

**The design.** The pool is a feature pack (docs/FEATURE_PACKS.md, "DHCP server"), the shape the
routing packs set: a schema of DHCP's own concepts, a partial in IOS's words, a parse that
models a line only when the partial writes it back exactly, and the round trip as the judge.
Intent holds `dhcp_server`:

```yaml
dhcp_server:
  excluded:                       # ip dhcp excluded-address <low> [<high>]
    - {low: 192.0.2.1, high: 192.0.2.10}
  pools:
    - name: LAN10                 # ip dhcp pool LAN10
      network: 192.0.2.0/25       # network 192.0.2.0 255.255.255.128
      default_router: [192.0.2.1] # option 3, in order of preference
      dns_servers: [192.0.2.53]   # option 6
      domain_name: lab.example    # option 15
      lease: {days: 0, hours: 8}  # lease 0 8; or {infinite: true}; absent: one day
      raw: [option 150 ip 192.0.2.5]   # any other line, verbatim
```

**What practice settles** (Cisco, "Configuring the Cisco IOS DHCP Server", IP Addressing: DHCP
Configuration Guide, Cisco IOS Release 15M&T,
https://www.cisco.com/c/en/us/td/docs/ios-xml/ios/ipaddr_dhcp/configuration/15-mt/dhcp-15-mt-book/config-dhcp-server.html,
read 2026-11-05; RFC 2132, https://www.rfc-editor.org/rfc/rfc2132.html, read 2026-11-05):

- the commands and their shapes: `ip dhcp excluded-address low-address [high-address]`;
  `network network-number [mask | /prefix-length]`; `default-router` and `dns-server` take "up
  to eight" addresses; `lease {days [hours [minutes]] | infinite}`, default one day;
- the router's own interface address "is automatically excluded" (the guide), so intent need
  not exclude the gateway; any other address the server must not offer is excluded by hand;
- a router is "on the client's subnet" (RFC 2132, 3.5), so a default router outside its pool's
  network is refused; routers and name servers are "listed in order of preference" (3.5, 3.8),
  so both lists keep their order;
- the DHCP server is on by default (the guide), so no `service dhcp` line is written.

**This increment (code and tests only; nothing sent to a device):** the schema and its checks,
the partial for both Cisco dialects (one copy in `_common.j2`, called from `services_block`, so
a library whose `_common.j2` is brought in renders it unchanged), the parser's two handlers,
the schema sections, a library from before the pack handed its lines (`dhcp.lines_view`), a pool
compared as a set by the round trip, and tests on the lab's real captures with Cisco's example
pools inserted: the round trip, the parse, the exact lines, the preview's program and its
undo, the refusals with the IPv6 case beside each IPv4 one, and the old library.

**DHCPv6 is not covered.** IOS's DHCPv6 server (`ipv6 dhcp pool`) stays verbatim lines, and an
IPv6 address in any field is refused naming it (CLAUDE.md, IPv6 parity). A4's steering screen
names it too (LAB9_SDN_GAP 5).

**Not measured: how a lab IOS or IOS-XE device prints a pool.** No capture holds one. The guide's
example writes the network in mask form, and so does the partial; IOS's own line order inside a
pool, whether it prints `lease 1` (the default), and how it spaces `default-router` are not
shown. One measurement settles them: the router's running config read through Mercury after its
first pool lands, kept as a fixture. Until then a line the partial does not reproduce stays raw,
and the round trip compares a pool as a set.

**What is left:**

- **the pool's remainder, about 0.75 agent-days:** ZTP's options as fields (150, 66 and 67,
  the switches' TFTP server and file, today `raw`); a check that each pool's network is a subnet
  of one of the router's own interfaces (the guide's "directly connected clients", or a relay);
  the capture's fixture and any partial change it shows; the manual's intent page entry;
- **DHCP steering, 1.25 agent-days** (LAB9_SDN_GAP section 2, item 3): the edge flows (a client's
  broadcast to the router's port, server replies dropped from any other port). **Its screen is a
  new tab, SDN › Apps, board B (LAB9_SDN_GAP section 7); none is drawn here.**
