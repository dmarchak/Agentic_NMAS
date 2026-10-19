# The relayed-ZTP probe (Labs 8 and 9, step 0d)

**The questions.**
- **0d (C1346):** does a configless C8000v's AutoInstall work through a DHCP relay? That means
  DORA through the relay, Kea choosing the subnet by giaddr, and the TFTP fetch routed back.
  And does it need option 3? D4 restated (docs/P6_ZTP.md) allows option 3 only if it does.
- **0g (C1350): dropped** (the operator, 2026-10-19; part 3). It asked whether
  `containerlab restart -n` brings a healthy node back with a link added to the topology file.

The agent's attempt on r5 showed that the restart parks the links before it stops the node
(C1372).

**Where.** A throwaway lab of its own (`docs/bootstrap-probe/nmas-relay-probe.clab.yml`: `zr4`
the relay, `zr6` the configless device). The lab's nodes are not touched, and s3 is not on its
path. Cost: two C8000v, about 9 GiB and 3.7 CPUs on the lab host (C1318's capacity).

**Gates, checked before and during.**
- Outside 08:30 to 09:10 UTC.
- s3's heartbeat gap rate is no worse than its 10-19 baseline: 6.5% of the day's gaps over
  620 s, 2.6% over the last 6 hours, measured 16:53 UTC by `s3_gaps.py`. It is re-read before
  and after, and the probe stops if it worsens.
- No sitting is in progress.

## Predictions (written before the run)

| | Prediction | Why |
|---|---|---|
| P-R1 | zr6's DISCOVER reaches Kea relayed (giaddr 10.255.96.1); Kea offers 10.255.96.2 from subnet 96 with options 66 and 67 | the relay as the lab's hosts already use it (subnets 10 and 20) |
| P-R2 | **without option 3**, no RRQ reaches 10.255.0.10: zr6 holds a /30 address and no route to an off-subnet server | AutoInstall has no route until a config gives one |
| P-R3 | **with option 3** = 10.255.96.1, the RRQ for `zr6.cfg` reaches the NMAS host from 10.255.96.2, routed through zr4 | a default route through the relay |
| P-R4 | the responder REFUSES it, naming the peer and the file: the reservation is not tool-written (0e builds that) | the responder serves only a Mercury fragment's reservation |
| P-G1 | (0g, dropped: not run) | |

## 0d through Mercury's own path (the operator, 2026-10-19; supersedes parts 1 and 2's hand Kea)

Every Mercury step is Mercury's own operation, run by the agent through the same functions the
v2 screens call, each previewed, confirmed by its hash and recorded. Nothing is written to Kea by
hand. Parts 1 and 2 below are kept as the first design; their predictions P-R1 to P-R4 still
apply.

**The network.** A throwaway network, `relay-probe` (Settings › Networks › New network…, its own
folder and repository): its devices' intent, goldens and receipts live there. It inherits
Default's Kea (C1181), so its DHCP subnet and reservations are recorded in Default's repository,
and they are removed through Mercury at the end.

**Gates, read before, during and after:** outside 08:30 to 09:10 UTC; s3's gap rate for the day
at or under 6.5% (6.2% at 20:52 UTC on 10-19), the probe stopped if it passes it; no sitting in
progress; s3 never on the probe's path (the host route below keeps the replies off it).

1. **Network:** `relay-probe` created (its name previewed, then created).
2. **zr4, the relay, by ZTP on the management segment:** on the lab host, the host bridge
   `br-zr96` made (`ip link add br-zr96 type bridge stp_state 0 forward_delay 0`, up; not
   persisted, deleted in step 9). Add device in `relay-probe`: zr4, IOS-XE, role router,
   address from ZTP, Gi2's MAC `aa:bb:cc:00:02:94`, 10.255.0.94/24, management interface
   GigabitEthernet2, no gateway (D4). Create (phase 1) writes its reservation; then
   `containerlab deploy -t nmas-relay-probe.clab.yml` (zr4 alone, configless, its Gi3 on
   `br-zr96`); zr4 boots, AutoInstall fetches its bootstrap, and onboarding's Verify promotes it.
   **Why two labs (2026-10-19):** zr6 must boot only once the relay, the subnet and its
   reservation exist (AutoInstall gives up after about 2.5 min, M4), and no node is restarted to
   make it ask again; so zr6 is its own lab, `nmas-relay-probe-zr6.clab.yml`, joining
   `br-zr96` later: Lab 8's own shape (R4 waits on `br-r4r6`, R6 joins from its own topology).
3. **The host route, temporary (a host step, reverted in step 9):** on the NMAS host,
   `ip route add 10.255.96.0/30 via 10.255.0.94 dev enp6s19`. Without it the replies to
   10.255.96.2 follow the host's route for the lab's address space to s3, which does not know
   the subnet.
4. **zr4's relay intent:** Gi3 `10.255.96.1 255.255.255.252`, `ip helper-address 10.255.0.10`,
   `no shutdown`; previewed, confirmed by hash, applied, verified (as r2 Gi4 was, 2026-10-19).
5. **The relayed subnet:** DHCP › Add a subnet, 10.255.96.0/30, relay 10.255.96.1, For ZTP
   onboarding ticked (0e), previewed and confirmed; the D4 check line read.
6. **zr6 behind the relay, run 1 (no option 3):** Add device in `relay-probe`: zr6, IOS-XE,
   address from ZTP, `aa:bb:cc:00:02:96`, 10.255.96.2/30, Route option (3) None. Create writes
   its reservation (options 66 and 67, no 3, no 6). The captures started (`tcpdump -ni enp6s19
   'udp port 67 or 68 or 69'` on the NMAS host, kept to a file, counts reported), then
   `containerlab deploy -t nmas-relay-probe-zr6.clab.yml`: zr6 boots and asks through zr4.
   Watch zr6's console through the read-only reader. Record P-R1 and P-R2.
7. **Run 2 (option 3 = the relay's own address), only if run 1 fetched nothing:** zr6's
   onboarding abandoned, Add device again with Route option (3) "The relay's own address"; zr6's
   lab destroyed and deployed again (the one redeploy command for a lab: no node is restarted
   by containerlab or docker); zr4 is untouched. Record P-R3, P-R4.
8. **Verify** promotes zr6 when its bootstrap landed: its management reached over the relay.
9. **The end:** zr6 and zr4 retired through Mercury (Retire, previewed, confirmed); the
   relayed subnet removed through DHCP › Subnets › Remove (C1377); `relay-probe` deleted; both
   probe labs destroyed (`containerlab destroy -t … --cleanup`, zr6's then zr4's); `br-zr96`
   deleted; the host route deleted; each shown gone (`ip route`, Kea's `config-get` holding subnets 10, 20 and
   255 only, br-mgmt holding `enp6s19`, `s3-mgmt`, `r6-mgmt`), and s3's gap rate read again.

## Part 1: set up (the first design, superseded above; each step's revert is in part 4)

1. **Lab host.**
   - Make `~/labs/relay-probe/` with `patches/` (`c8000v-launch.py` from `~/labs/lab/patches/`,
     `c8000v-launch-configless.py` from `~/labs/ztp-a/patches/`) and `configs/zr4.cfg`:
     - `hostname zr4`;
     - Gi2 `ip address 10.255.0.96 255.255.255.0`, `no shutdown`;
     - Gi3 `ip address 10.255.96.1 255.255.255.252`, `ip helper-address 10.255.0.10`,
       `no shutdown`.
   - Then `containerlab deploy -t nmas-relay-probe.clab.yml`.
2. **NMAS host**, temporary and never persisted:
   - `ip route add 10.255.96.0/30 via 10.255.0.96 dev enp6s19`;
   - `ufw allow in on enp6s19 proto udp from 10.255.96.0/30 to any port 69 comment relay-probe`;
   - Kea, in memory only: `config-get`, add subnet 96 (`10.255.96.0/30`, relay ip-addresses
     `10.255.96.1`, no pool), with one reservation:
     - `hw-address aa:bb:cc:00:02:96`, `ip-address 10.255.96.2`;
     - option 66 `10.255.0.10`, option 67 `zr6.cfg`, and NO option 3 or 6.
   - Then `config-test`, then `config-set`.
3. **Captures:** `tcpdump -ni enp6s19 'udp port 67 or udp port 68 or udp port 69'` on the NMAS
   host, and the same on `zr4-mgmt` on the lab host.

## Part 2: 0d's two runs

- **Run 1 (no option 3):** zr6 boots, taking about 7 to 9 min (P.6). Watch the captures and
  zr6's console through the read-only reader (type nothing: console input ends discovery).
  AutoInstall gives up after about 2.5 min and 9 requests (M4). Record P-R1, P-R2.
- **Run 2 (option 3 = 10.255.96.1):**
  - `config-set` again with option 3 added to the reservation only.
  - zr6 is redeployed alone (`containerlab destroy` and `deploy` of the probe lab with zr6 only,
    or the configless boot again).
  - Record P-R3 and P-R4, and the responder's refusal row naming the peer and `zr6.cfg`.

## Part 3: 0g (dropped)

Dropped by the operator on 2026-10-19: a lab node is never restarted by containerlab
(`restart`, `restart -n`) or by docker (`restart`, `start`), so there is nothing to measure.
A node restarts only by a reload from its own CLI, or by a full redeploy (lab/REDEPLOY.md).
P-G1 is not run.

## Part 4: revert (always, and on any stop)

1. **Lab host:** `containerlab destroy -t nmas-relay-probe.clab.yml --cleanup`, then check
   `br-mgmt` holds what it held before (`enp6s19`, `s3-mgmt`, `r6-mgmt`).
2. **NMAS host:**
   - Kea `config-reload`; then `config-get` holds subnets 10, 20 and 255 only.
   - `ip route del 10.255.96.0/30`.
   - `ufw delete allow in on enp6s19 proto udp from 10.255.96.0/30 to any port 69`.
3. **s3's gap rate** read again.

## Results (2026-10-19, 20:57 to 23:18 UTC)

**The answer: relayed ZTP works through Mercury's own path, and it needs option 3, the relay's
own address** (D4 restated's allowance). Without it, DHCP through the relay completes and the
device never fetches its file. Lab 8's R6 is added with Route option (3) "The relay's own
address".

| | Prediction | Measured |
|---|---|---|
| P-R1 | the DISCOVER reaches Kea relayed, an offer with 66 and 67 | **held.** 22:07:22 (run 1) and 23:05:12 (run 2): zr4 relays from giaddr 10.255.96.1 to 10.255.0.10:67; Kea offers 10.255.96.2 from subnet 256 with option 66 (10.255.0.10) and 67 (`probe-zr6.cfg`), no 3 and no 6 in run 1 |
| P-R2 | without option 3, no RRQ reaches 10.255.0.10 | **held.** Run 1: no packet to udp/69 in 60 captured; from 22:09 the device asks DNS for `tools.cisco.com` (Plug and Play's cloud fallback) once a minute, those packets reaching 10.255.0.10 (the relay answering proxy ARP), but AutoInstall never asks for its file |
| P-R3 | with option 3, the RRQ reaches the host routed through the relay | **held.** Run 2: `RRQ "probe-zr6.cfg"` from 10.255.96.2 at 23:05:49, 28 in all |
| P-R4 | the responder refuses (before 0e) | **held for the wrong reason, then served.** The running responder had started at 02:57, before 0e's change was deployed (C1404): "10.255.96.2 holds no reservation the tool wrote". Restarted at 23:07:40, it served the next retry at 23:07:43 to 23:07:44, 476 bytes, DATA and ACK through the relay |

Then Verify promoted probe-zr6 over the relay at 23:11 (answered, captured, credential rotated
and persisted, NetBox 22 objects).

**What the run cost, each registered:**
- the throwaway network could not use its own relay: C1399. The probe moved into Default (the
  operator's option 2), relay-probe retired and deleted, its 8 NetBox objects left by Stop
  tracking (C1097);
- a transient first-contact key: C1400 (Verify waits about 3 min after the fetch);
- Verify ignores declined profile sections: C1402;
- run 1's lease blocked run 2 (`ALLOC_ENGINE_V4_DISCOVER_ADDRESS_CONFLICT`): C1403, deleted by
  hand with `lease4-del` at 22:57:53, and both probes' leases at 23:16:52;
- the responder ran pre-0e code: C1404;
- the firewall had never admitted the relayed subnet: `c1346-ztp-relayed-firewall.sh` run at
  22:07:48, before any TFTP request (none was sent in run 1, so it decided nothing);
- the subnet's Remove left its empty reservations file: C1405.

**Reverted and shown gone (23:16 to 23:19 UTC):** probe-zr6 and probe-zr4 retired (every step);
their two leases deleted; subnet 256 removed through Mercury (Kea holds 10, 20 and 255 only);
the ufw rule for 10.255.96.0/30 deleted and the firewall record re-written (udp/69 from
10.255.0.0/24 only); the host route deleted; both probe labs destroyed, no container or network
left; `br-zr96` deleted; br-mgmt holding `enp6s19`, `s3-mgmt`, `r6-mgmt`. Nothing inherited: no
current host key at 10.255.0.94 or 10.255.96.2; no probe in Default's inventory, manifest or
intent; no monitoring target, heartbeat rule or telemetry rule naming one; the telemetry check
passing; no Needs attention row naming one but the baseline row, which a Save All after Lab 8's
R4 and R6 deploys answers (C1406). s3's gap rate for 10-19: 6.2% before the run (20:52 UTC), 5.5%
after it (23:20 UTC), under the 6.5% gate throughout; the 24-hour test reads it again (C1380).
