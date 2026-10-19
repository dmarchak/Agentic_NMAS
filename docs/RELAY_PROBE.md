# The relayed-ZTP probe (Labs 8 and 9, steps 0d and 0g)

**The questions.**
- **0d (C1346):** does a configless C8000v's AutoInstall work through a DHCP relay? That means
  DORA through the relay, Kea choosing the subnet by giaddr, and the TFTP fetch routed back.
  And does it need option 3? D4 restated (docs/P6_ZTP.md) allows option 3 only if it does.
- **0g (C1350):** does `containerlab restart -n` bring a HEALTHY node back with a link added to
  the topology file since it was deployed? How long does it take, and does the other end's link
  survive?

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
| P-G1 | `containerlab restart -n zr4` brings zr4 back with both links, the new one included; zr6's ends stay up | a healthy node can be stopped and started, unlike r5 |

## Part 1: set up (each step's revert is in part 4)

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

## Part 3: 0g

Add the second link (zr4 eth3, zr6 eth2) to the topology file. Then run
`containerlab restart -t nmas-relay-probe.clab.yml -n zr4`, timing it to zr4's console prompt.
Record P-G1:
- zr4's interfaces, the new one included;
- zr6's two links;
- the park namespace emptied;
- `tc` mirroring present on each eth/tap pair.

## Part 4: revert (always, and on any stop)

1. **Lab host:** `containerlab destroy -t nmas-relay-probe.clab.yml --cleanup`, then check
   `br-mgmt` holds what it held before (`enp6s19`, `s3-mgmt`, `r6-mgmt`).
2. **NMAS host:**
   - Kea `config-reload`; then `config-get` holds subnets 10, 20 and 255 only.
   - `ip route del 10.255.96.0/30`.
   - `ufw delete allow in on enp6s19 proto udp from 10.255.96.0/30 to any port 69`.
3. **s3's gap rate** read again.

## Results

(Written when the probe has run.)
