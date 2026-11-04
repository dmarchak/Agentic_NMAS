# Lab 9, the final SDN lab: the read-only gap-check board

Drafted 2026-11-03 ~19:3x UTC (13:3x UTC−6) from the code at `e93fe977`. Nothing was built,
and no host, device, network or credential was touched. This is the board that PHASE8_PLAN 0.3
calls workstream 2's first step ("Gap board Nov 3–5").

**What the lab is to Mercury.** The operator's final SDN lab, due 2026-11-30, runs on physical
hardware. The operator plans it as if working alone, with Mercury as the only management
interface, so the lab is a requirements list for Mercury as an SDN management tool. The lab's
own text is kept outside the repository, because it names a course and an institution. Its
requirements are restated here in neutral terms.

**Not to be confused with** the "Lab 9 redeploy" of C1547 and PHASE8_PLAN 15.9, which was a
lab topology. Here "Lab 9" always means the final SDN lab.

**The hardware:**
- two Arista switches and one HP switch, each a hybrid switch with OpenFlow on some ports;
- two Open vSwitch servers on bare-metal Linux;
- a Cisco internet router, which also does DHCP and inter-VLAN routing;
- a Cisco management switch;
- a controller server.

**How to read the states:**
- **exists:** the code does it today, and the handler is cited.
- **partial:** some of it exists; what is missing is named.
- **missing:** nothing in the code does it.

**About the citations:**
- Every citation was read, either by the board's author or by a read-only survey run for this
  board, and was checked against the file. Line numbers are approximate (±2).
- "(inferred)" marks a vendor or practice fact that was not measured here.

**About the estimates:**
- They are in **agent-days**: one agent's focused day of building, gated and pushed, including
  its tests. The operator's sittings are not included.
- **Read them through the measured ratio** (C2380, the operator, 2026-11-03).
  - One agent-day is about 1.3 wall-clock hours for one agent (0.7 to 2.6) and about 4M
    weighted tokens (2.5M to 9M), measured on eight items finished on 2026-11-03.
  - So the 46 agent-days left after the cuts are about 30 to 40 hours with two agents, the gates
    alone about 17 hours, and 185M to 225M weighted tokens (about 15 to 18% of a week's usage at
    that day's rate).
  - The binding limits are usage, the gates run one at a time, and the operator's hardware
    sittings, not calendar days.
- They are inferred. The only finished stage of the same kind is Lab 8's SDN slice (17.1). It
  was planned at about 69 focused hours to land between Oct 26 and Oct 30. Its build continued
  to Nov 2 (S-HR, C2279, 0.2), so it ran about 75% long. Read every figure here with that in
  mind (section 3).

---

## 1. The lab's requirements against Mercury today

### Part A

| Req | What the lab asks | Mercury today (cited) | State | What is missing | Item |
|---|---|---|---|---|---|
| A1 | **Network build:** internet through the router, which also does DHCP and inter-VLAN routing; management isolated; OVS on bare-metal servers with OpenFlow, reaching the controller out of band; hybrid vendor switches with OpenFlow on the right ports and a separate non-OpenFlow management network; the controller on the management network, with internet, controlling every OpenFlow switch; **the network survives the designated redundant link failing**; the design documented | **The Cisco router and management switch are Mercury's home ground.** IOS intent keeps unmodelled lines verbatim (`modules/nsot/parsers/base.py`, module docstring: "anything with no handler into `unmodeled` verbatim"), and NAT is parsed (`_h_ip_nat`, ~L145). So DHCP pools, dot1Q subinterfaces and NAT deploy through the intent editor and the 9-stage pipeline (`modules/pipeline.py`). **The OpenFlow side:** controller connections exist (`modules/sdn/connections.py:save_connection`, ~L349). The Ryu application is lab tooling (`lab/sdn/ryu/l4_switch_13.py`): it learns at L2 and installs per-L4 flows | **partial** | **No platform but Cisco** (item 1). **No loop-free forwarding on redundant links:** `l4_switch_13.py` learns at L2 with no spanning tree or path computation, so a redundant OpenFlow link floods broadcasts in a loop (inferred from how Ryu's simple_switch learning works; to be measured on the hardware). **No link-failure survival** (item 6). The design document is the operator's | 1, 6 |
| A2 | **NSOT-driven OpenFlow configuration:** switch IP, controller IP, OpenFlow port, version and transport; configures every hardware switch; verifies and displays each switch's connection; the NSOT describes more than connections | **Reading the controller's switch list exists:** `modules/sdn/drivers/ryu.py:RyuDriver._switches` (~L282) and `_switch_desc` (~L344). It is drawn on SDN › Controllers (`modules/sdn_page.py:controllers_view`, ~L166). **NetBox already holds devices, platforms and IPAM** (MERCURY_CHARTER, the sources of truth) | **partial** | **No OpenFlow parameters are modelled** in NetBox or in intent. **No template** renders a vendor's OpenFlow configuration. **No push** to EOS, HP or OVS (item 1). **No check that a configured switch appeared in the controller's list.** Configured devices and connected DPIDs are not joined (item 2) | 2 |
| A3 | **DNS blacklist:** DNS forced to the controller; an external JSON verdict service queried from the controller; bad names blocked, good ones allowed; bonus +3 for a modified reply showing a "blocked" page | **The flow write path exists:** `modules/sdn/flow_ops.py:plan` (~L317) and `apply` (~L955) preview, confirm by hash, hold, send, verify, roll back and record. **No DNS function exists:** `modules/sdn/` and `routes/` hold no match on UDP 53 and no DNS service | **missing** | **The steering flows:** UDP and TCP 53, IPv4 and IPv6, rewritten to the filter and back. **A DNS-filter service** on the controller server that asks the verdict service, blocks or forwards, and optionally answers with the block page's address. **The app's settings and its health** in Mercury (item 3) | 3 |
| A4 | **DHCP:** requests forced to the router; unicast from the edge | Nothing (no match on UDP 67/68 in `modules/sdn/`). Mercury's DHCP screen fronts Kea (`routes/dhcp_v2.py`), not a router's pools | **missing** | **Edge flows:** a client's DHCP broadcast unicast to the router's MAC on its port, and server replies dropped from any port but the router's. The router's pool goes in its IOS intent (A1). **DHCPv6 is not covered;** the screen says so by name (CLAUDE.md, IPv6 parity) | 3 |
| A5 | **Trace:** source and destination from the CLI or GUI; the DPIDs along the path; bonus +3 for ingress and egress ports | Topology's Path… traces **routed** paths from CEF (`modules/path_trace.py:trace`, ~L221; `routes/topology_v2.py:path_run`, ~L152). The controller's topology exists (`modules/sdn/topology.py:layer`, ~L321; `endpoint_hosts`, ~L460). The OpenFlow match semantics and effects exist (`modules/sdn/flow_intent.py:effect`, ~L880; `modules/sdn/match_rules.py`) | **missing** (registered C1911, C, "later") | **A flow-table walk.** It starts at the source host's port (the controller's hosts), matches a synthesised packet against each switch's table in priority order, follows the output port across the controller's links, and ends delivered, dropped, sent to the controller, or with no match. The hops are DPIDs, then in and out ports (the bonus) | 3 |
| A6 | **All of the above through the controller's REST API** | **Every SDN read and write goes through the driver's northbound calls** (`modules/sdn/drivers/base.py:ControllerDriver`, ~L570; `ryu.py` `render_*`, ~L423 to L461). A write's body is a value, hashed before it is sent (17.2) | **exists** for flows and meters | **Groups are absent** (needed for fast failover, item 6), and so is **port description** (needed for link status, item 7). Both are Ryu `ofctl_rest` calls the driver does not make yet. The DNS service's verdict queries go from the controller server, not through Mercury | 6, 7 |

### Part B

| Req | What the lab asks | Mercury today (cited) | State | What is missing | Item |
|---|---|---|---|---|---|
| B1 | **Analyst:** live state from all four hardware devices (flows, port stats and rates, drop rules, link status); reports what is abnormal, with an explanation; at least three planted issues, including the redundant-link failure; found, missed and why | **Collection exists:** `modules/sdn/closed_loop.py:collect_threat_data` (~L209) reads flows, active and drop flows, coverage, and two port-stat samples into rates (`_rates`, ~L169). **Explain** (P1) answers any SDN detection, because a detection is an alert with an evidence pack (`modules/evidence_pack.py:build_detection`, ~L1511) | **partial** | **No link status:** the driver reads `/stats/port` counters only (`ryu.py:_port_stats`, ~L357). A link's `state` in `topology.layer` is "up" when the link was present in the read, else "unknown" (~L363); that is not a link-down signal. **No analyst** (S19 is plan only). The closest is `closed_loop.judge_collection` (~L1027), an evaluation path that answers threat yes or no. **No planted-issue report** (item 7) | 7 |
| B2 | **Intent controller:** natural language to a structured policy, applied after a person's confirmation; validated against the NSOT (unknown hosts or devices, conflicts, protected flows); at least four intents, one on a vendor switch and one on an OVS server; bad requests refused or questioned (ambiguous, impossible, contradictory) | **The pattern exists for device intent** (feature 7). `modules/ai/intent_words.py:screen` (~L957) holds quotes, scopes and resolves names before any call. `resolve_names` (~L996) and `modules/ai/intent_names.py` settle ambiguity in code (11.2). `to_patches` (~L452) validates after the call. **Flow conflict analysis exists** in `flow_intent.effect` (shadows, diverts, drops, lifts). **The SDN Policies board is drawn** (S9, `SdnPolicies.dc.html`, PHASE8_PLAN 19.1) | **missing** for SDN | **S17, Policies:** compile a policy to flows, then a conflict check. **S18, a policy in words.** **NetBox validation** of hosts and devices. **The impossible class:** a capability the switch lacks (a meter on a switch without meters) or a host not on any OpenFlow port. **The contradictory class:** two clauses of one request, or a request against a committed policy. **About 30 recorded cases and a blind set** (item 4) | 4 |
| B3 | **Closed loop:** scan, flood, unauthorised flow and link failure detected; bonus +3 for an automated link-failure response; HITL and autonomous modes; actions on both OVS servers and at least one vendor switch; a vendor limit such as meters documented with its fallback; false-positive runs on normal traffic; a continuous loop of at least 5 minutes while threats are introduced | **Detection:** scan, flood, unauthorised flow and high rate (`modules/sdn/detect.py`: `RULES`, ~L129; `scan`, ~L430; `flood`, ~L740; `unauthorised`, ~L975). **Classify:** `closed_loop.classify_threat` (~L654). **Respond:** `build_response` (~L1738) and `respond_to_threat` (~L1934), from `CATALOGUE` (~L1109). **Modes:** HITL and AUTO (`modules/sdn/modes.py:turn_on`, ~L235; `decide`, ~L317), with AUTO only on a network marked lab (`stage`, ~L82). **The loop:** `modules/sdn/loop.py:start` (~L1662), `run_pass` (~L1259), `stop` (~L1733). **False-positive runs:** `closed_loop.prepare_collection` and `judge_collection`, run by `scripts/nmas-sdn-classify-normal`. **Meter features are read:** `ryu.py:_meter_features` (~L403) | **partial** | **No link-failure rule.** **No reroute.** **No per-switch capability matrix:** capabilities are declared per controller (`RyuDriver.capabilities`), not per switch; meter features are read but not tabled with groups, tables, version or set_field. **C2305** is open (B): benign detections are always answered as a threat, 0 of 100 runs. **The loop has no stated stop condition but Stop:** `start` takes an interval only. The lab asks that every loop have a stop condition (item 6) | 6 |
| B4 | **An advanced technique beyond Labs 6 to 8,** proposed early to the instructor or a TA and evaluated against the baseline | The pieces exist (section 4) | **missing** | Section 4's candidates, put to a TA this week (item 11) | 11 |
| B5 | **Logs and analysis:** a false-positive and failure log; an API call and cost log; an AI-use disclosure; a production-readiness analysis | **The AI call record exists:** `modules/ai/calls.py:record` (~L132), with each call's feature, model, trigger, tokens, cost, verdict and latency. History draws it (`modules/history_sources.py:ai_calls`, ~L1112; `routes/v2.py:history_ai_call`, ~L1006). **The SDN outcomes are kept:** dismissals with their reasons (`loop.resolve`, ~L385, in `sdn_responses.jsonl`); refused classifications on the proposed row; Verify and rollback outcomes as operation rows (`flow_intent.record_operation`, ~L405). **The production gate is written:** PHASE8_PLAN 17.7 | **partial** | **No export.** The only SDN download is one loop run's text log (`routes/sdn_v2.py:log_download`, ~L99). **No CSV or JSON** of the call and cost log, and none of the false-positive and failure log (item 10). The disclosure and the analysis are the operator's documents, drawn from 17.7 and the export | 10 |

### The integration rules

| Rule | Mercury today (cited) | State | What is missing | Item |
|---|---|---|---|---|
| **Protected flows** (DNS, DHCP, management) defined in the NSOT and enforced in code | **The control-plane guard** (`modules/sdn/control_plane.py:refusal`, ~L141; `covers`, ~L109) refuses a response covering LLDP, the controller's addresses or OpenFlow's port. **It is called only from the closed loop's responses** (`closed_loop.build_response` ~L1903, `respond_to_threat` ~L1999), **not from `flow_ops.plan`**. So a flow added on SDN › Flows (`routes/sdn_v2.py:flow_preview`, ~L160) is not checked. Protected hosts are C2010 (open, B) | **partial** | **Protected flows** (DNS, DHCP, management) **as NetBox objects.** **One check in `flow_ops.plan`,** the write path every writer shares: the flow form, responses, re-apply, and the policies and apps to come. **A screen** to see them and add them in Mercury (item 5). *Candidate finding for the register (not recorded here; this board writes no register row): the control-plane guard is outside `flow_ops.plan`, so the flow editor bypasses it.* | 5 |
| **One source of truth:** the NSOT drives A2 and validates the AI | NetBox owns devices and IPAM; intent is in the network's git repository (MERCURY_CHARTER) | **partial** | The OpenFlow parameters and protected flows modelled in NetBox (items 2 and 5) | 2, 5 |
| **One controller path** | Every SDN write goes through `flow_ops` and the connection's driver (`connections.driver_for`, ~L176) | **exists** | Keep the apps (item 3) and intent (item 4) on it. **Mercury does not write flows by SSH to an OVS server.** Item 1's OVS driver configures the bridge's controller only | — |
| **Never trust model output** | Pydantic v2 strict schemas; code checks after every call (`closed_loop.check_classification`, ~L566; `intent_words.to_patches`); the agent proposes and never confirms (charter) | **exists** | The same discipline for S18 and the analyst | 4, 7 |
| **Economy-tier models; every loop with a stop condition; the API key out of the repository** | **Models:** `sdn_classify`, `assistant` and `change_record` are pinned to Haiku. **But `explain`, `intent_patch` and `nl_query` are pinned to Sonnet** (`modules/ai/pins/`). **The key** is in the secrets store, never in git (docs/SECRETS.md). **Stopping:** the loop stops on Stop, and AI calls stop at the day cap | **partial** | **Explain on Lab 9's network must run on Haiku,** and so must the policy-in-words feature (item 8). **A stop condition** on the loop beyond Stop (item 6) | 6, 8 |

---

## 2. The operator's items 1 to 11

| # | Item | Today (cited) | State | Missing | Estimate (agent-days) |
|---|---|---|---|---|---|
| 1 | **Multi-vendor:** Arista EOS, HP or Aruba, and OVS on Linux (netmiko drivers, OpenFlow and management templates, verify). Golden and drift later | One dialect list, `modules/nsot/platform.py:DIALECTS` (~L68), = `{"cisco_ios", "cisco_iosxe"}`; `require_platform` (~L109) refuses any other. The netmiko type comes from the `platform_map` setting (`netmiko_type_for_dialect`, ~L212). See 2.1 | **missing** | A per-dialect adapter for the OpenFlow and management sections (2.1) | **9.5** lean (2 shared seam, 2 EOS, 2.5 HP, 3 OVS); the full pipeline per platform is 21 to 32 (2.1) |
| 2 | **OpenFlow onboarding from NetBox and intent** (controller, port, version, transport); verified from the controller's switch list, and shown | The switch list and description reads exist (`ryu.py:_switches`, `_switch_desc`); SDN › Controllers draws them | **partial** | The NetBox model (2.2), the derived intent section, rendering through item 1, the verify join (configured device to DPID seen), and the SDN › Switches view (board A) | **3** |
| 3 | **SDN apps:** DNS filtering, DHCP steering, a path trace | Only the flow write path (`flow_ops`) | **missing** | The DNS steering app and its settings (2), the DNS-filter service (2), the block page (0.5); DHCP steering (1.25); the trace by DPID (2.5) and its ports (0.5) | **8.75** |
| 4 | **An SDN intent controller:** words to a flow policy, NetBox validation, confirm, apply; refuses ambiguous, impossible and contradictory requests | Feature 7's pattern (`intent_words.screen`, `resolve_names`, `to_patches`); `flow_intent.effect`; board S9 drawn | **missing** | S17 compile and conflicts (2.5), S18 words (1.5), NetBox validation (1), the three refusal classes and about 30 cases (1.5), the screens (1) | **7.5** (minimal B2: **4**) |
| 5 | **Protected flows** (DNS, DHCP, management) in NetBox, enforced by every writer | The control-plane guard, responses only (above) | **partial** | The NetBox model (2.2), one check in `flow_ops.plan`, tests across each writer, the SDN › Protected tab (board C) | **2.5** |
| 6 | **Closed loop:** link-failure detection and reroute; HITL and AUTO on a lab-marked network; a per-vendor capability matrix (with the meters fallback); false-positive runs; a continuous 5-minute loop; C2305 fixed first | The loop, its detections, the modes and the lab guard exist (B3 above); C2305 open | **partial** | C2305 (1.25, counted in the schedule's first window). The link-down rule (1). Reroute (1.5): fast-failover groups in the driver, or path flows. The capability matrix (1). False-positive runs on the hardware (0.5). A loop stop condition (run-for minutes) and the 5-minute run (0.5) | **5** + C2305 **1.25** |
| 7 | **Live analyst:** link status in the collection; planted-issue reporting (found, missed, why) | `collect_threat_data`; Explain on detections; no link status, no analyst | **partial** | Port description and link status read and kept (1); "Analyse this network", an AI-marked, person-triggered button on SDN › Flows, its schema, the check that every claim cites evidence, and its cases (2); the planted-issue report (0.5) | **3.5** |
| 8 | **Per-network model choice** (economy tier, Haiku) | The model is fixed per task by its pin (`modules/ai/profiles.py:load_pins` and `TASKS`, ~L88 and L108; `modules/ai/gateway.py:_prepared` reads `profiles.TASKS.get(feature)`, ~L562). `ai_background` is per network and per feature but holds no model (`modules/settings_schema.py`, ~L154). Haiku 5.5 is in the price table (`profiles.MODELS`, ~L31; `PRICES_AS_OF` 2026-10-27) | **partial** | A per-network tier (economy or standard) on Settings › AI (board G); `_prepared` choosing from the trigger's network; caps and estimates from that model; each feature's recorded cases measured on Haiku, or the pinned-model test (`tests/test_ai_gateway.py`) refuses it | **1.5** (spend: about $1 to $2 for Explain's and words' Haiku rounds) |
| 9 | **Laptop deployment:** Mercury native in a venv plus netbox-docker, its own data folder and key, local git only; two legs (Ethernet to lab management, Wi-Fi to the internet); everything that assumes the NMAS host degrades cleanly | See 2.3: most already degrades cleanly. **Identity is the blocker** (`modules/identity.py:identify`, ~L275; `is_configured`, ~L188) | **partial** | The install recipe (0.5); identity (1.5, a decision, section 5); an installation kind so job health, the updater and the GitHub readers say "not applicable on this install" (1, lean wording only: 0.5); the walk on the laptop (0.5 to 1) | **3** lean, **5** full; macOS +1 |
| 10 | **B5 report export:** the false-positive and failure log, and the call and cost log, from History's AI audit, spend and evaluation logs | The records exist (B5 above); no export | **partial** | History › Export (board H): two CSV and JSON downloads, each with a date range and a network, columns stated, masked as History masks | **1.75** |
| 11 | **B4:** propose 2 or 3 candidates built on existing work, to put to a TA this week | — | **this board** (section 4) | The proposal is section 4 (0.25, done). The build is 2 to 4 by candidate | **3.25** (proposal plus candidate 1's build) |
| — | **Hardware integration:** fixtures captured from each real switch, and the fixes the first real runs surface | — | — | — | **3** |
| — | **Manual pages and fidelity records** for each new screen (a v2 screen is not done without them, CLAUDE.md) | — | — | — | **2.5** |
| | **Total** | | | | **about 56** |

### 2.1 Platform assumptions that block Arista EOS, HP/Aruba and OVS on Linux

**netmiko 4.3.0 is installed and locked** (`requirements.txt`, `requirements.lock`). The keys
present in its `ssh_dispatcher.py` `CLASS_MAPPER`, verbatim:

| Vendor | Keys |
|---|---|
| Arista | `arista_eos` (and `arista_eos_telnet`) |
| HP ProCurve / ArubaOS-Switch | `hp_procurve`, `aruba_procurve`, `aruba_osswitch` (all HPProcurveSSH) |
| HP Comware | `hp_comware` |
| Aruba wireless controllers, not switches (inferred from netmiko's naming) | `aruba_os` |
| Linux | `linux`, `ovs_linux` (`OvsLinuxSSH` is `LinuxSSH` with nothing added) |

**AOS-CX has no key in 4.3.0.** `aruba_aoscx` is in netmiko 4.6.0, which the system Python
carries. So an AOS-CX switch means a netmiko upgrade, a lock change, and a retest of Mercury's
netmiko-boundary code.

**What to ask the operator:** the HP switch's exact model and OS. The candidates are:
- ArubaOS-Switch, also known as ProCurve (2920, 2930F, 3810, 5400R, and the like, inferred);
- AOS-CX (6300, 8320, and the like);
- Comware (5130, 5900, and the like).

The answer decides the driver, the OpenFlow syntax and the netmiko version.

**The hard-coded IOS assumptions** (each needs a per-dialect hook; none exists):

**Connection, `modules/connection.py`:**
- `connection_params` (~L161) sets `secret = password`. On Linux that makes the login password
  the sudo password.
- `verify_device_connection` (~L806), `get_persistent_connection` (~L877) and
  `with_temp_connection` (~L931) always call `enable()`. On Linux that is `sudo -s`.
- `prompt.rstrip("#>")` (~L823) misreads a Linux prompt.
- `vty_lines` (~L314) budgets sessions from `line vty`.
- `_guard_writes` (~L653) treats anything off the read-only allowlist as a write.

**Read-only allowlist, `modules/readonly_commands.py`:**
- `READ_ONLY_VERBS` (~L80) is `show`, `ping`, `traceroute`, `dir` and `more`.
- `refusal` (~L403) takes no platform. So every `ovs-vsctl` and `ovs-ofctl` read is refused,
  and EOS's `| json` is refused too.

**Command runner and config read:**
- `modules/commands.py` hard-codes `CONFIG_READS` (~L27). Its prompt check needs
  `[A-Za-z0-9._-]+` (`modules/config_read.py:USABLE_PROMPT`, ~L120), which fails on a Linux
  prompt.
- `config_read.problems` (~L69) needs one `end`, last, and a `hostname X` line. ProCurve's
  quoted hostname and missing `end` fail it (inferred).

**Pipeline, `modules/pipeline.py`:**
- `_stage_pre_snapshot` (~L686) reads `show running-config`.
- `_push_via_netmiko` (~L1036) sends `send_config_set` with `IOS_ERROR_PATTERN`.
- `_stage_save_startup` (~L2371) calls `onboard.persist_on_device` (~L3808), which runs
  `save_config()` and then checks `show startup-config`.
- The routing and interface reads are IOS commands parsed as IOS output.

**Parsing and diffing:**
- `modules/nsot/parsers/base.py:split_blocks` (~L45) assumes IOS-style indentation.
- `modules/nsot/deploy.py`: `merge_commands` (~L613) and `rollback_commands` (~L1143) undo by
  `no <line>` and `exit`.
- `modules/nsot/verify_scope.py:MANAGEMENT` (~L31) is IOS regexes.

**SDN authority:**
- `modules/sdn/authority.py:of` (~L120) makes a device whose platform starts with `openflow`
  controller-managed.
- Every direct route then refuses it (`DIRECT`, ~L29; `check_request`, ~L176).
- So **a hybrid switch, or an OVS server whose controller address Mercury configures, needs a
  split authority:** management direct, flows only through the controller.
- It must not be recorded as `openflow*`, or Mercury could never configure its OpenFlow
  section.

**Adding a dialect today touches:**
- `platform.py`'s four tables;
- the `platform_map` default (`modules/settings_schema.py`, ~L500);
- a parser in `modules/nsot/parsers/`;
- a template directory;
- the per-dialect JSON data files;
- about ten per-dialect tables (`reload_op`, `bootstrap_config`, `prometheus_targets`, and
  others);
- `tests/test_platform_keying.py`'s KEYING.

**The design, by practice.** Network automation frameworks separate the transport from the
driver, and give each driver the same operations: load a candidate, compare, commit or discard,
and roll back. NAPALM is the reference design: drivers for EOS, IOS, Junos and NX-OS, with a
community ProCurve driver. Ansible's `network_cli` platforms do the same. So Mercury adds:
- **One adapter seam,** `render`, `send`, `read_back`, `undo`, `save`, keyed by dialect. Item
  1's lean scope is only the OpenFlow and management sections, run as one new operation with
  the five stages, not the IOS merge pipeline.
- **EOS:** a configure session with `commit timer`, EOS's own confirmed commit, so a lost
  session rolls back by itself (inferred from EOS documentation; to check on the switch).
  - This matches the plan for EOS as the second vendor (`docs/NSOT_STAGE10_PLAN.md`, 12.6:
    cEOS, configure sessions, `commit timer`).
  - The difference is scope: Lab 9 needs only the OpenFlow and management sections, before
    that full second vendor.
- **ArubaOS-Switch:** commands in the `openflow` context, and a read-back of `show openflow`.
  The undo is the before-state re-applied. In ArubaOS-Switch an OpenFlow instance binds to
  member VLANs, not ports, so "OpenFlow on the right ports" is a VLAN membership (inferred from
  the vendor's OpenFlow guide; to check).
- **OVS on Linux:** one `ovs-vsctl` invocation with `--` separated commands, which is one OVSDB
  transaction. For example: `set-controller br0 tcp:<controller>:6653`, `set bridge br0
  protocols=OpenFlow13`, `set-fail-mode br0 secure`. The read-back is
  `ovs-vsctl --columns=is_connected list controller`. There is no save, because OVSDB persists
  by itself. Sudo is the only privilege needed, with an allowlist of fixed command shapes for
  reads.

**Not a new package:** NAPALM (Apache-2.0) would be a new third-party licence, which is the
operator's to approve. The seam above needs none.

**Estimates:**

| Scope | Agent-days |
|---|---|
| Lean, OpenFlow and management sections only | shared seam 2, EOS 2, HP 2.5, OVS 3: **9.5** |
| Full pipeline parity per platform (the survey's figures) | shared 3 to 5, EOS 4 to 6, ProCurve 6 to 9, OVS 8 to 12; AOS-CX +3 to 5 on top of ProCurve |
| Golden and drift, later | EOS +2 to 3, HP +3 to 4, OVS +3 to 5 |

**The hardware risk** (inferred, to measure first; nothing here was read from a switch):
- **Arista's OpenFlow support is limited by platform and release.** Historically it is
  OpenFlow 1.0 on some 7050-series releases, and OpenFlow was dropped from later EOS releases.
  If the switches speak OpenFlow 1.0 only:
  - they have no meters, no groups and one table;
  - Mercury writes OpenFlow 1.3 field names. The read side translates 1.0 names
    (`ryu.py:match_from_ryu`, ~L121), but whether Ryu's 1.0 path accepts the names Mercury
    writes is UNKNOWN. **The measurement:** one `add_flow` to a 1.0 switch, read back.
- **The first reads on the hardware are `show version` and `show openflow`** (or the vendor's
  equivalent), for each switch.

### 2.2 The NetBox model for OpenFlow and protected flows (decided by practice)

**Where things go in NetBox.** NetBox's own guidance puts each fact on the object that owns it:
- device facts as custom fields;
- shared settings as config contexts (inherited by site, role or platform);
- an application endpoint as a Service (NetBox's `ipam.Service`: protocol, ports, device and
  addresses).

Nautobot's Golden Config and NetBox's config templates render from the same split.

**For OpenFlow:**

| Fact | Where in NetBox |
|---|---|
| The controller | a Device or VM, the controller server, with a Service `openflow` (TCP 6653) |
| The version and transport (`tcp` or `tls`) | a config context on the role "openflow switch", overridable per device |
| A switch's datapath id (optional) and its OpenFlow instance | custom fields |
| OpenFlow ports | interfaces tagged `openflow` (or the VLAN, on ArubaOS-Switch) |
| The management address | the device's primary IP |

Mercury reads these and derives an intent section, `openflow:` in `host_vars`, committed as
derived intent. It renders the section through item 1 and verifies it.

**For protected flows:**
- each one is a NetBox Service tagged `protected`, with a `kind` of dns, dhcp or management,
  on the device that serves it: the DNS filter on the controller server, DHCP on the router,
  SSH, HTTPS and OpenFlow on management addresses;
- the management prefix is an IPAM prefix with the role `management`.

Mercury compiles these into the match sets that no writer may cover. **Mercury is the one
interface:** they are added and edited on SDN › Protected (board C), written into NetBox as a
confirmed step (charter, NetBox writes need the master switch and a declared authority).

### 2.3 What assumes the NMAS host, and how a laptop install degrades

Survey of the product (`app.py`, `modules/`, `routes/`, the runtime scripts):
- **Works as is:**
  - The data folder: `NMAS_DATA_DIR` (`modules/config.py`, ~L38).
  - A fresh credential key, created by `read_or_create_key` (~L157). A copied store without its
    key is refused by name.
  - Files instead of PostgreSQL: an empty `records_db_host` keeps every store on its files
    (`modules/records_db.py`).
  - Local git with no remote: `modules/nsot/repo.py:commit` (~L1596) always publishes. The push
    hook answers "no remote configured" (`modules/nsot/remote.py:auto_push_decision`, ~L1286).
  - The integrations: off unless configured (`modules/integrations/base.py:is_configured`,
    ~L108).
  - The interpreter: falls back to the one that started it (`modules/app_interpreter.py`).
- **Degrades with a stated reason:**
  - The Update page (`modules/update_op.py:plan`, ~L608) says "not installed" and has no origin
    to compare with.
  - The About page says "not compared yet: <reason>" (`routes/v2.py:installation`).
- **Degrades, but the screen is wrong for a laptop:**
  - Job health's systemd, Proxmox and updater rows stay permanently not-ok
    (`modules/job_health.py:job_status` ~L103, `image_jobs` ~L421).
  - The version-mismatch remedy says `sudo systemctl restart flask-app.service` (`version_rows`,
    ~L1396).
  - The two GitHub readers fail every interval (`modules/readers/app_pushed.py:judge`, ~L48).
  - The fix is an installation kind (host or laptop) that marks these not applicable, which the
    charter already asks for ("an outside service that could not be asked is … never a Needs
    attention row").
- **Silently wrong:** `FLASK_HOST` defaults to `0.0.0.0` (`modules/config.py`, ~L555). On a
  laptop that is both the lab Ethernet and the Wi-Fi. The recipe sets `NMAS_HOST=127.0.0.1`.
- **Breaks: identity.**
  - `identify` needs a verified Cloudflare Access assertion AND a trusted peer, with no
    localhost exemption (by design: the comment in `modules/settings_schema.py`, ~L319).
  - Without them, every mutating request is refused (`modules/route_gates.py:enforce`, ~L366),
    including Settings.
  - Setting `require_identity_for_*` false by hand records the actor as `unverified`. Some paths
    still refuse in code: SDN rate-limit proposals (`modules/sdn/loop.py`, ~L510), the AI person
    triggers (`modules/ai/triggers.py:_person`), and the background-AI settings.
  - So the stopgap is not enough for Lab 9. The choice is section 5's decision 1.
- **Not used by the app:** `deploy/systemd/`, `scripts/nmas-render-units`, `scripts/nmas-host`,
  `data/lab_hosts.json` and `scripts/nmas-deploy` are not used by the running product.
  `modules/host_steps.py:owed` would show a future `Host-Step:` row on a laptop; the
  installation kind filters it.
- **Two network legs:** netmiko follows the OS's routes, and Mercury pins no interface outside
  ZTP. The recipe routes the lab management prefixes through the Ethernet leg. ZTP and Kea are
  not needed for Lab 9 (they stay off: `kea_ztp_fragment` is empty by default).
- **macOS adds about 1 day:**
  - the lock is compiled for x86_64 Linux with hashes;
  - port 5000 is usually held by AirPlay (inferred);
  - `modules/readers/topology_graph.py:here` uses Linux ioctls.

---

### 2.4 The Lab 9 laptop, as given by the operator (2026-11-04)

| Fact | Value | What it settles |
|---|---|---|
| OS | Ubuntu 26.04.1 LTS | Its system Python is newer than CI's 3.12.3. So Mercury's venv is built on 3.12.3, installed by uv as the development laptop's is, never on the system interpreter. `telnetlib.py`'s shim covers 3.13 and later if the system one is ever used. |
| CPU | 24 threads | Mercury, netbox-docker and the SDN controller run side by side with headroom. |
| Memory | 30 GB usable | The same. netbox-docker's stack (NetBox, PostgreSQL, Redis, the worker) is the largest part. |
| Docker | 29.1.3, Ubuntu's `docker.io` package | Apache 2.0, an OS package, approved by the licence rule (docs/THIRD_PARTY_DEV_TOOLS.md). The same version the local CI runner was measured on. |
| Docker Compose | 2.40.3 | Compose v2, the form netbox-docker's recipe needs. |

**Planned now, independent of the switch models:** items 2 to 5 and 7 to 10 of section 2, plus the laptop install itself (item 9) on these facts. **Waits for the Arista and HP switch models (Thursday 2026-11-05):** item 1's drivers. Section 2.1's platform assumptions are sized again once the models are known.

## 3. The estimates against the schedule's windows

**Capacity, stated so it can be checked:**
- **Lanes:** at most two code agents at once (the laptop's memory).
- **Nov 5–14:** one lane, because Lab 10's build takes the other.
- **Nov 15–19:** 1.5 lanes (Lab 10's walks are the operator's sittings, with support).
- **Nov 20–23:** 1.75 lanes (Lab 10 is submitted).
- **Nov 24–30:** about 1.75 lanes, bounded by when the operator is at the hardware.
- **Usage, not lanes, may be the real bound:** this week's usage was about 3.5 days at the
  week's rate (0.3).

| Window | Items (agent-days) | Demand | Capacity | Gap |
|---|---|---|---|---|
| Nov 3–5 | this board | — | — | — |
| Nov 5–14 | C2305 1.25, laptop 3, drivers 9.5 | **13.75** | 10 | **−3.75** |
| Nov 15–19 | onboarding 3, protected flows 2.5, apps 8.75 | **14.25** | 7.5 | **−6.75** |
| Nov 20–23 | SDN intent 7.5 | **7.5** | 7 | **−0.5** |
| Nov 24–30 | link failure and loop 5, analyst 3.5, model tier 1.5, B5 export 1.75, B4 3.25, hardware 3, manual 2.5 | **20.5** | 12 | **−8.5** |
| **All** | | **about 56** | **about 36.5** | **about −19.5** |

**Fit: it does not fit at full scope.**
- **The operator's cut order** saves about 4.5 days, leaving it about 15 short:
  1. trace ports, 0.5;
  2. the DNS block page, 0.5;
  3. a minimal B2 (four intents; block, allow, rate-limit and isolate only; NetBox validation
     kept), 3.5.
- **Five further cuts**, proposed for the operator to choose among. Each keeps a lab
  requirement met; together they save about 5.5:
  - **B4 is candidate 1,** the cheapest (section 4): saves 1.25.
  - **The analyst reuses Explain** over an SDN collection packed as evidence, with no new AI
    feature: saves 1.5. It loses a planted-issue score of its own.
  - **The model tier is per installation, not per network** (the laptop install runs every
    feature on Haiku): saves 1. It loses the product feature.
  - **The B5 export is two plain CSV routes** on History, with no card: saves 0.75.
  - **Reroute uses fast-failover groups only where the switch supports them,** and Mercury only
    detects and verifies elsewhere: saves 1. The capability matrix states the gap.
- **With every cut, demand is about 46 against 36.5: still about 9.5 short.**
- **The remaining levers are the operator's** (section 5, decision 7):
  - more usage in Nov 15–19 and Nov 24–30;
  - drop the OVS servers' item-1 path. OVS is configured once by the lean adapter, read-only
    after;
  - or move B1's analyst behind B3.

**The top risks, in order:**
1. **The vendor switches' OpenFlow support is unknown.** It sets item 1's and item 6's real
   size: version, meters, groups, set_field and hybrid mode. Arista OpenFlow 1.0 only would
   remove meters and fast failover there (2.1). **Measure first:** `show version` and
   `show openflow` on each switch, the day the operator is at it.
2. **Redundant links loop under the current Ryu application** (A1). A loop-free forwarding
   application is lab tooling the plan has not counted:
   - Ryu's spanning-tree example (`simple_switch_stp_13`), or a shortest-path application on
     the controller's topology;
   - +1 to 1.5 days (inferred), and needed before any link-failure test.
3. **Identity on the laptop** blocks every write until decision 1 is made.
4. **The estimates are inferred.** The last stage of the same kind ran about 75% long.
   **Re-forecast after EOS's driver lands (about Nov 8),** from its actual days (CLAUDE.md,
   "forecast only from a finished stage of the same kind"), and say behind or ahead in that
   report.
5. **C2305 holds the classifier back.** Every B3 HITL proposal on benign traffic is wrong while
   it is open, and false-positive runs are a graded item.
6. **Hardware time.** Fixtures can only come from the real switches. OVS can be rehearsed on
   any Linux VM. EOS's container image does not run OpenFlow (inferred). ArubaOS-Switch has no
   simulator; AOS-CX has one.

---

## 4. B4: three candidates for the operator to put to a TA

**The baseline for all three:**
- **For classification:** sdn_classify v3 on Haiku, a single call per detection. Its blind
  round: 10 of 36 cases reliable, and 0 of 100 runs saying no threat on benign traffic (C2305).
- **For the intent controller:** item 4's single words-to-policy call.

**Each candidate is measured on:**
- the same recorded and blind sets, at 10 runs, against the 85% blind floor (0.1.1);
- calls, tokens and dollars from the ledger (`scripts/nmas-ai-ledger`).

| Rank | Candidate | Builds on | Evaluated against the baseline | Cost | Risk |
|---|---|---|---|---|---|
| **1** | **A second model checking the first (a verifier).** Haiku classifies (or drafts a policy). A second, differently framed Haiku call then sees the same evidence pack and NetBox facts and must name the evidence for and against, including a benign explanation. It confirms, downgrades to "no threat", or returns the request to a person. Code stays the final gate. This is LLM-as-a-judge and self-verification, a known technique beyond Labs 6 to 8's single call | the gateway and pins (`modules/ai/gateway.py`); the evidence pack ids (`modules/evidence_pack.py:build_detection`); the deterministic check (`closed_loop.check_classification`); the blind sets (`tests/fixtures/ai_cases/sdn_classify/`); feature 7's `to_patches` for policies | **False-positive rate** on the benign cases (BF1 to BF3, BS3, and the fresh blind set's benign cases) and **threat recall** on the rest, with and without the verifier, at 10 runs. **For B2:** the refusal accuracy on ambiguous, impossible and contradictory requests | **Build 2 to 3 agent-days.** Spend: twice the calls. At the measured batch rate ($0.000326 a call) a 36-case, 10-run round is about $0.25. **Latency** in the loop roughly doubles; to be measured | **Low.** The same model checking itself can share its errors; a different framing and evidence order reduce that, and the measurement shows it. **It directly attacks C2305, the lab's weakest graded item.** Fits economy tier |
| **2** | **Retrieval over vendor documentation and the NSOT.** Before classifying, or compiling a policy, Mercury retrieves: the switch's documented OpenFlow limits (meters, groups, table size, hybrid rules); the NetBox facts for the hosts named (role, services, protected flows); and the network context (`network_model.context_for`). It sends them as cited passages, so "impossible" requests are refused from evidence, and the classifier sees what the hosts are for | BM25 retrieval (`modules/ai/manual_index.py:ranked`, ~L210; `select`, ~L248; recall@k in `evaluate`); the network context (`modules/network_model.py:context_for`, ~L1070); the citation checks the assistant already uses | **Refusal accuracy** on impossible requests, **misclassification of approved activity**, and **citation validity** (every cited passage exists), with and without retrieval; **recall@5** on a labelled question set | **Build 3 to 4 agent-days.** Spend: larger prompts, about 1.5 to 2 times the tokens a call | **Medium.** Preparing the corpus takes time. **Vendor documents are copyrighted:** the corpus stays local and gitignored, never committed (the repository is public). BM25 on vendor manuals may miss; the recall measurement says so |
| **3** | **Tool calling into the trace.** The analyst gets read-only tools: the path trace (item 3), a switch's flows, port stats and link status, and a NetBox lookup. It asks for what it needs in a bounded loop (at most N tool calls, a stop condition), instead of receiving a fixed pack | the driver's reads (`modules/sdn/drivers/ryu.py`); the trace (to be built); the adapter, which passes `tools` through but sends none today (`modules/ai/anthropic_adapter.py`, ~L32, L59); the strict output schema (`gateway.build_request`, ~L291) | **Planted issues found and missed,** and false findings, against the fixed-pack analyst (item 7), with tool calls, tokens and dollars per analysis | **Build 4 to 5 agent-days** (a new gateway path: tool turns, a mask on each tool result, a loop bound). Spend: 3 to 5 times the tokens per analysis | **High.** A new egress path is the irreversible tier, so it needs a hand check (CLAUDE.md, mutation). Injection through tool results. The trace must exist first. It does not fit the schedule unless B1 slips |

**The recommendation is candidate 1:**
- it is the cheapest;
- it is measured on sets that already exist;
- it improves the weakest graded number.

Candidate 2 is the strongest fallback if the TA wants retrieval. Candidate 3 is the most
"advanced" but the least likely to finish.

---

## 5. Decisions for the operator (only what practice does not decide)

**Decided by the operator, 2026-11-03 ~20:3x UTC, on the summary table in the ratio:**
- **No cuts for time.** Trace ports, the DNS block page and the full B2 are restored (about 4.5
  agent-days: about 6 h and 18M weighted tokens). Section 3's cut list is withdrawn.
- **The usage-cut order** applies only if usage tightens:
  1. B5 as two CSV routes;
  2. B4 as candidate 1;
  3. reroute through fast-failover only where supported;
  4. the analyst reusing Explain;
  5. last, the model tier per installation.
- **Order:** Lab 10 stays first. Lab 9's items that need no hardware (2, 3, 4, 5, 7, 8, 9, 10)
  take agent slots as they free. Items 1 and 6 wait on the hardware checklist's readings at the
  operator's first lab-room visit (~/Documents/nmas-reports/lab9-hardware-checklist.md).
- **B4:** the operator proposes one of section 4's candidates to a TA this week.

1. **Identity on the laptop** (a standing rule: no localhost exemption). There are three
   options:
   - **(a) A single-user local provider:** loopback bind enforced, a passphrase set at first
     run, a session cookie, and `Actor-Verified: local`. It takes 1.5 days. It reverses the
     no-localhost rule for this install kind, so it is an exception that names its expiry: the
     lab's end, or Keycloak's arrival.
     - **It departs from the product's identity decision.** The operator decided on
       2026-10-16 that the product's identity is Keycloak (one per instance, with local
       accounts held in Keycloak, not in Mercury; `docs/OFFLINE_OPERATION.md`, section 1).
     - That decision supersedes the in-app local accounts of `docs/NSOT_STAGE10_PLAN.md`,
       2.2 (a). The provider interface itself is 2.1.
   - **(b) Cloudflare Access and `cloudflared` on the laptop,** with the trusted peer set to
     127.0.0.1. No code (about 0.5 day of setup), but it needs the Wi-Fi leg up for every write.
   - **(c) The gate-off settings.** Not enough: SDN proposals and AI triggers still refuse in
     code.
   - **(d) Keycloak in Docker beside netbox-docker, and Mercury's OIDC provider.** This is the
     product's direction, but the provider interface and OIDC are not built: 3 to 5 days
     (inferred), which the schedule cannot hold.
   - **Practice favours (a) for a single-user desktop tool,** time-boxed, with (d) kept as the
     product's path. The rule and the exception are the operator's.
2. **The cut order past the operator's three** (section 3): which of the five further cuts, and
   which lever for the remaining gap.
3. **AUTO on the Lab 9 network.** It is built for a network marked lab (`modules/sdn/modes.py`,
   `AUTO_STAGE`). Marking the Lab 9 network lab is an admin's action, and AUTO stays outside
   Phase 8's bar (17.4). Confirm that the lab's autonomous runs are on that marking.
4. **A DNS library for the filter service.** dnspython (ISC licence) is a new third-party
   licence, which is the operator's. Practice says parse untrusted DNS with a vetted library,
   not by hand.
5. **The B4 candidate** to put to the TA (section 4).
6. **Item 1's HP path** if the switch is AOS-CX: the netmiko 4.3.0 to 4.6.0 upgrade, a lock
   change (not a new licence).
7. **The remaining gap's lever** (section 3): more usage, the OVS path lean, or B1 behind B3.

**Decided here by practice** (each recorded so it can be questioned):
- **The controller stays Ryu.** The driver is built, captured and walked (17.2, 17.6), and
  swapping the controller under a deadline costs the integration again.
  - Ryu's last release (4.34) needs Python 3.9 (17.6). os-ken, the fork OpenStack maintains,
    carries the same `ofctl_rest` (inferred), and is the move if the controller server's Python
    forbids 3.9.
  - **Its northbound REST has no authentication.** Bind it to loopback on the controller server
    and front it with TLS and basic authentication (for example, nginx) on the management
    address only. Mercury's connection already carries TLS verification and credentials (17.1
    S2).
- **The DNS filter is a service Mercury steers to and reads, not part of Mercury.** It is like
  Kea: the charter's "Mercury is not a source of truth". DNS-layer security products (Cisco
  Umbrella, Infoblox Threat Defense, RPZ on BIND or Unbound) are resolvers that a network steers
  to. So:
  - Mercury owns the steering flows, the app's settings and the filter's health;
  - the filter (a small DNS proxy asking the verdict service) is lab tooling, `lab/sdn/`;
  - the verdict service's URL is a setting, off unless configured.
  - **Fail-open or fail-closed** when the verdict service is unreachable is a per-network
    setting, default open, as C2264 already states for responses.
- **Steering uses `set_field` on the destination address and MAC, with the reverse rewrite on
  the replies.** This is the standard OpenFlow form of DNS interception. Where a vendor switch
  cannot rewrite in hardware (the capability matrix), its edge ports send UDP and TCP 53 to the
  OVS path instead, and the matrix says so.
- **DHCP steering is DHCP-snooping's model in flows:**
  - client broadcasts (UDP 67) are unicast at the edge to the router's MAC on its port;
  - server replies (UDP 68 from port 67) are dropped on every port but the router's (the
    trusted-port rule of DHCP snooping, RFC 2131's roles);
  - the router's pool is IOS intent;
  - DHCPv6 is named on the screen as not covered.
- **Link failure is repaired locally, then re-optimised** (RFC 5714's IP fast-reroute
  framework; OpenFlow 1.3 fast-failover groups, used by ONOS's Trellis fabric):
  - where the matrix shows fast-failover groups, Mercury installs the primary and backup as one
    group from the policy;
  - the loop detects the port or link down and verifies the backup carries the traffic;
  - elsewhere, the loop proposes the reroute flows (HITL) or applies them (AUTO, on a
    lab-marked network).
- **The trace has one home:** Topology's Path… gains the controller's layer, and SDN › Flows
  links to it ("one home per action", CLAUDE.md). Hops are DPIDs with in and out ports. The lab
  allows GUI or CLI; Mercury's GUI meets it (no terminal steps).
- **Protected flows are checked in `flow_ops.plan`,** the one write path, so every writer is
  covered by construction.

---

## 6. Questions the operator listed, and the board's own

1. **The Arista switches:** exact model, and EOS version (`show version`), and whether OpenFlow
   is licensed and enabled (`show openflow`).
2. **The HP switch:** exact model and OS (ArubaOS-Switch or ProCurve, AOS-CX, or Comware) and
   its firmware.
3. **The laptop:** its OS and version, its RAM (netbox-docker wants about 4 GiB besides
   Mercury, inferred), whether Docker or Podman is installed, and its CPU architecture (x86_64
   or arm64: the lock is x86_64 Linux).
4. **The OVS servers:** the Ubuntu version, the NIC count (one management NIC and the data
   ports), and the OVS version.
5. **The controller server:** its OS and Python version (Ryu 4.34 needs 3.9, or a container).
6. **The external JSON verdict service:** its URL, its request and answer shape, whether a key
   is needed (typed by the operator), and its rate limit.
7. **The redundant link:** which link the lab designates, and between which switches.
8. **Hardware time:** the days the operator is at the hardware, because fixtures and every
   measurement in section 3 wait on them.

---

## 7. The board

New screens and cards are needed, so the board is `docs/boards/lab9-sdn.html`, in the house
format, with nine artboards:

| Board | What it draws |
|---|---|
| **A** | SDN › Switches: OpenFlow onboarding's verify view, and its preview and result |
| **B** | SDN › Apps: DNS filtering and DHCP steering |
| **C** | SDN › Protected: protected flows, and a writer's refusal |
| **D** | Topology › Path…: the trace through flow tables |
| **E** | SDN › Policies: the intent controller's validation and its three refusals (board S9 holds the rest) |
| **F** | SDN › Responses: the link-failure rule, the capability matrix and the loop's run-for bound |
| **G** | Settings › AI: the per-network model tier |
| **H** | History › Export |
| **I** | SDN › Flows: Analyse this network |

**Its sign-off** is the operator's, or is self-signed under the Phase 7 mode with a line in
`docs/STANDING_APPROVAL_LOG.md` and a row in PHASE8_PLAN 19.1. Neither was written by this
read-only board.
