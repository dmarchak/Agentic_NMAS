# P.6 — ZTP as a third address source: scope

Written 2026-09-26, after P.5, before any P.6 code. It answers the operator's
standing questions first, then states what was measured, what must be decided,
what the throwaway must measure before anything is built, and what counts as
done for course Labs 8 and 9.

ZTP here means **zero-touch provisioning of one new device**: it boots with no
configuration, gets an address somebody reserved for it in advance, fetches its
bootstrap configuration from the tool, and is then reached by the tool. In this
design it is another **address source** in onboarding, beside `static` and
`dhcp`, with the same two phases after it.

---

## 0. The standing questions, answered

**Where does §6a sit now?** [NSOT_STAGE7_GUI.md](NSOT_STAGE7_GUI.md) §6a
("where a bootstrap config goes") is a design, not a build. It set three rules
for any delivery path, and P.6 builds the first delivery path other than the
browser download, so P.6 is bound by them:

- never deliver silently ("the config was fetched" and "the config was
  produced" are different facts);
- never keep a copy (the config is re-derivable precisely so that it is not
  stored);
- the reveal gate still applies (delivering the file hands over the one-time
  credential).

§6a also left one question open: the settings that would become delivery
destinations are installation-wide today. Section 3, decision D3, answers it
for P.6.

**Does Phase 2's Kea work cover the addressing half?** The READ half, yes:
`reservation_for()` refuses a plan without a reservation, `discover_dhcp_address()`
reads the lease and refuses when lease and reservation disagree, and the prefix
comes from the lease's subnet. The WRITE half, no: nothing in the tool writes a
reservation or a boot-file option, and nothing serves a config. Those are P.6's
build, and section 1 measures what the host allows.

**Does a device that arrives by ZTP get the guarantees onboarding makes?** Yes,
by construction, because ZTP changes only how the bootstrap config REACHES the
device:

- phase 1 is unchanged: a one-time credential is staged, and the initial intent
  is committed with the P.1 syslog block already merged in (`build_plan()`
  does this for every source);
- phase 2 is unchanged: reach, capture, rotate the credential, remove the RW
  community, save a true first golden, record in NetBox, promote last;
- the template is validated against the device at its own first deploy (scheme
  3, P.5), and the syslog block lands with that deploy (Lab 9).

The device is not in the inventory until phase 2 promotes it, so it cannot be
"managed in name" while outside those guarantees.

**Is ZTP the scale path?** It is the greenfield one: a device gets an address
reserved in advance and fetches its own config, so N devices are N reservations
and N fetches, with no wizard pass each. P.6 proves ONE device, on a throwaway.
The bulk job (buckets, retries, per-device outcomes grouped) is the feature
audit's section 8c job and comes after Stage 7. P.6 must not preclude it: the
reservation writer takes a set, and every outcome is per device.

---

## 1. Measured on the host (2026-09-26, read-only)

| Fact | Measured | Consequence for P.6 |
|---|---|---|
| Kea version and place | Kea 2.4.1 on the NMAS host itself; Control Agent `127.0.0.1:8001`; DHCP listening on `10.255.0.10:67` (the management segment) | The config server and the DHCP server are one host, on one segment |
| Kea credentials | `kea_username` and `kea_password` are set (Phase 2 found them unset, HTTP 403) | The tool can call the Control Agent |
| Reservation commands | 51 commands, **no `reservation-*`**: the `host_cmds` hook is not installed (installed: `bootp`, `flex_option`, `ha`, `lease_cmds`, `mysql_cb`, `pgsql_cb`, `run_script`, `stat_cmds`; configured: `lease_cmds` only) | A reservation cannot be added by API without another mechanism (D1) |
| Config commands | `config-get`, `config-set`, `config-test`, `config-write`, `config-reload` present | A whole-config route exists |
| Config file | `/etc/kea/kea-dhcp4.conf`, `root:root 0644`; Kea runs as `_kea` | **`config-write` would fail, so a reservation added by `config-set` would live in memory only and vanish at Kea's next restart**, which is a wrong thing looking right |
| TFTP | no TFTP daemon active; `/srv/tftp` does not exist | Nothing serves a config today |
| `tftp_server_ip` | `192.168.0.30`, which is none of the host's addresses (`10.0.0.211`, `10.255.0.10`, and the docker bridges); read only by `config.TFTP_SERVER_IP` for image copies | A stale setting from an older setup. ZTP must not read it (D3); recorded as C48 |

---

## 2. The design in one paragraph

`ztp` is `dhcp` plus two things the tool now does itself. Phase 1 writes a Kea
reservation for the device's MAC, carrying the boot-file option that names its
config, and the tool serves that config on request. Everything after the fetch
is Phase 2 as it stands: the lease is discovered from Kea, the device is
reached with the staged credential, and the seven steps run.

**The states, each observed from its own source, never inferred:**

| State | Observed from |
|---|---|
| planned | the plan (a reservation is about to be written) |
| reservation written | the reservation read BACK from where it is stored, after the write |
| leased | Kea's lease for that MAC (Phase 2's reader) |
| config fetched | the config server's own record of the fetch (a reveal row) |
| reached | Phase 2's verify (SSH answered with the staged credential) |
| promoted | Phase 2's last step |

"Fetched, not reached" and "leased, not fetched" are distinct states, and the
pending row reports them (the Stage 7.4 per-source progress column draws them
later; P.6 only produces them).

---

## 3. Decisions (the operator's)

### D1. How the tool writes a reservation

| Option | What it takes | Blast radius | Survives a restart |
|---|---|---|---|
| **(B) An include fragment the tool owns** (recommended) | The management subnet's `reservations` come from a separate file via Kea's `<?include?>`; the directory `/etc/kea/nmas/` is owned by the NMAS service user, mode `0755`, and the file is `0644`: measured at D1, since Kea's AppArmor profile withholds `dac_override`, so the offline `kea-dhcp4 -t` as root is held to the mode bits and `0640` shut it out (P6_ZTP_PROBE.md, D1 "As run"); the tool writes it, then `config-test`, then `config-reload` | Reservations for that subnet only: the tool cannot touch any other part of Kea's config | Yes: it is a file |
| (A) `config-get` / `config-set` / `config-write` | `_kea` write access to `kea-dhcp4.conf` | The whole DHCP config, every subnet, on every write | Only if `config-write` works, which today it cannot |
| (C) The `host_cmds` hook | ISC's own package, not Ubuntu's | Reservations only | Depends on the host backend |
| (D) Manual, as Phase 2 | Nothing | None | Yes |

(C) is a third package source on a host whose environment is already hard to
reproduce (C40). (D) proves Lab 8 but leaves the write half unbuilt. (B) is
the narrowest grant that makes the write half real. Its guard: after every
write, read the reservation back from the file AND from `config-get`, and
refuse unless exactly the intended reservations changed, naming both operands.
Two preconditions it must refuse on: a MAC or an address already reserved for
another device, and an address already leased to another MAC.

### D2. How the config is served

§6a's rules decide most of this. A TFTP daemon serving files from `/srv/tftp`
keeps a copy on disk for as long as the file waits, which breaks "never keep a
copy", and serves it to anyone who asks for the name, which bypasses the
reveal gate.

**Recommended: a responder in the tool that renders on request.** It renders
the bootstrap artefact from committed intent and the staged credential at the
moment of the request (`bootstrap_artifact()`, which already exists), and
writes nothing to disk. It serves:

- only a device that is pending;
- only to the address reserved for that device (the reservation is what makes
  the requester's address meaningful);
- once per request, each fetch a reveal row with the requester's address and
  the hash of what was served.

Anything else is refused and recorded.

**The transport is TFTP, decided by measurement (M3, 2026-09-27).** Offered
66 and 67, the node sent `RRQ "bp-ztp-a.cfg" octet` to port 69: 21 bytes, so
plain RFC 1350 with no TFTP options (no `blksize`), 512-byte blocks, and a
bootstrap config of a few blocks.

**What that costs on the host (measured):**
- the app's unit (`flask-app.service`) runs as `dmarchak` with no ambient
  capabilities;
- `ip_unprivileged_port_start` is 1024;
- no TFTP library is installed.

Two decisions follow, both the operator's:

**D5. How port 69 is bound** (proposed: (a)).

- **(a) A systemd socket unit** (`ListenDatagram=69`, `BindToDevice=enp6s19`)
  activating a small `nmas-ztp-responder.service` as `dmarchak`. systemd
  binds the privileged port, so the process holds no capability at all.
  `BindToDevice` names the interface, not an address, so it follows D3
  (derived, never a literal). The responder is its own process, so a fault
  in it cannot take the app down, and the app's unit is untouched until
  6.5.
- (b) `AmbientCapabilities=CAP_NET_BIND_SERVICE` on `flask-app.service`.
  One line, but it hands the whole web application the right to bind any
  privileged port, for the sake of one responder.
- (c) An nftables redirect of udp/69 to a high port the app binds. No
  capability, but a NAT rule a rebuild must reproduce, and a second place
  the port lives.

In every case ufw needs `allow in on enp6s19 proto udp from 10.255.0.0/24
to any port 69`. Only the inbound request needs the rule: the server's DATA
leaves from a new port and the client's ACKs return on that flow, which
conntrack already tracks as established. The rule is the second layer; the
responder's "only the reserved address" is the first.

**D6. The TFTP implementation** (proposed: (a)).

- **(a) A minimal responder in the tool: read requests only, octet mode, no
  options, retransmit on timeout.** There is no write path to guard because
  none exists. A write request is answered with a TFTP error and recorded.
  It is testable over loopback under the network guard.
- (b) `tftpy`: a new dependency, so the host lock is regenerated (C37), and
  a library whose server also implements writes, which then has to be shown
  unreachable.

**The filename is a second operand, not the key.** The requester's address
selects the device (only the reserved address is served). The RRQ's filename
must then equal that reservation's option 67. A mismatch is refused and
recorded with both names, because a device asking for a file it was not told
about is a device that is not in the state the tool thinks it is.

### D3. Where the destination lives

§6a's open question. For P.6 the answer is that the config server's address is
**derived, not configured**: it is the host's own address on the interface
Kea's reserving subnet is served on (`10.255.0.10` today). A configured copy of
that fact is how `tftp_server_ip` came to name `192.168.0.30`. A per-list
store beside `source.json` is the right shape when a second network needs a
second segment, and P.6 does not need one.

### D4. What a ZTP reservation offers (decided, the operator's, 2026-09-26)

Measured in M1's re-run: a configless IOS-XE 17.6 node with DNS and a route
out resolves `devicehelper.cisco.com` and sends it a PnP HELLO, carrying its
UDI, before it finds anything local. On an air-gapped network that fails
harmlessly. On a network with a way out, it discloses the device's identity
to a third party. A 600 s PnP backoff followed; whether that delays local
discovery was not measured.

**This is a property of ZTP, not a lab setting**, and the operator's framing
is the reason: every greenfield device on a network with a way out does this,
so a deployment that has not thought about it announces its inventory to a
third party during onboarding.

**Refined by M3 (2026-09-27): withholding stops the CALL, not the
ATTEMPT.** With no resolver the node broadcast DNS queries for
`tools.cisco.com` to `255.255.255.255:53`: 8 queries, 0 replies. So anyone on
the segment can see that it wanted to phone home, and anything on the
segment that answers broadcast DNS would give it a resolver with no DHCP
option at all. That is a property of ZTP, recorded as such (the operator's
framing). D4 therefore has TWO conditions:

1. **no route or resolver OPTION reaches the reservation** (the check
   above);
2. **nothing on the ZTP segment answers DNS.** Measured 2026-09-27: the NMAS
   host listens on loopback only, and no fleet golden carries
   `ip dns server`. The build's job-health row asks both.

The node REQUESTS 3, 6 and 33 (its parameter request list, read from the
capture), and Kea sends a requested option wherever it is configured. That
is the measured reason D4 is a check and not a default. The name it asked
for is Cisco's Call Home endpoint, not PnP's redirect (M1's re-run), so two
subsystems reach for Cisco.

**Decided:** a reservation the tool writes carries the address and the
config-source options it needs (option 67, and 150 or 66 as M3 decides) and
**never `routers` or `domain-name-servers`**. The node reaches the config
server on its own `/24` (D3 derives that address from the interface Kea
serves the subnet on), so it needs neither.

**A CHECK, not a happy accident** (the operator's requirement). Subnet 255
carries no option data today (measured 2026-09-26), but that holds only
because nobody has touched it, while subnets 10 and 20 hand out both. So the
check computes the options a reservation in the ZTP subnet would EFFECTIVELY
receive: global, shared-network, subnet and reservation `option-data`
together. It refuses anything that gives a route or a resolver: `routers`
(3), `domain-name-servers` (6), `static-routes` (33) and
`classless-static-route` (121). Option 121 is on the list because a default
route can arrive that way with no option 3 at all. It runs in two places:
at plan time, where a `ztp` onboarding is refused while the check fails,
and as a job-health row, so an option added to subnet 255 later is named
the day it appears rather than at the next onboarding. Client classes can
also carry options; if the config defines any, the check reports it
could not rule them out, rather than passing. Built with the P.6
reservation writer, with a control for each option code.

---

## 4. What the throwaway measures first

These are the states nobody has observed. Each has a prediction stated before
the run, so a result cannot be read as confirming whatever happened.

| # | Question | Prediction | Why it matters |
|---|---|---|---|
| M1 | Does a vrnetlab node run AutoInstall/ZTP at all? vrnetlab gives every node a day-0 config (typed over the console on vIOS, CVAC on the C8000v), and AutoInstall runs only when there is no startup config | **No, unmodified.** A launch-script variant that skips the day-0 config is needed, bound as the probe's OWN copy (the rule from `test_probe_topologies.py`) | If no node can boot configless, the lab cannot exhibit ZTP at all, and the measurement decides the platform |
| M2 | Which interface does the node DHCP on? | On a C8000v, Gi1 is vrnetlab's docker management and the lab segment is Gi2; the prediction is that AutoInstall tries every interface that is up | Kea answers only on `10.255.0.10`'s segment |
| M3 | TFTP (options 66/150 plus 67) or an HTTP URL in 67, and which filename is requested? | IOS AutoInstall asks by TFTP; IOS-XE may accept HTTP | Decides D2's transport |
| M4 | Does the fetched config apply, and is the node then reachable with the staged credential? | Yes, if the config is the bootstrap artefact; the Stage B injected-user hazard applies only where vrnetlab still injects a user | This is the whole of Lab 8 |
| M5 | Does a reservation written by D1's mechanism survive `config-reload` AND a Kea restart? | Yes for (B); no for (A) as the host stands | A reservation that vanishes at restart is the failure D1 exists to prevent |

Also recorded, not assumed: whether Kea 2.4.1 defines option 150 or needs an
option definition, and whether the `<?include?>` directive is accepted inside
a subnet's `reservations` value (`config-test` answers it without touching
the running server).

**The variant needed more than the ISO removed** (found by reading, before
M1 ran): the image's install step saved a startup config into the overlay
the launch script boots, so a variant that removed only the ISO would have
booted that config and answered M1 "no" about the instrument, not the
platform. The variant now boots the base disk; the runbook's P-M0 checks it
on the device. **If M2 finds Gi1's qemu DHCP ends discovery**, the prepared
fallback is the node as its own Proxmox VM on `vmbr10`, with no qemu user
network. It is scoped, with its image, network, resource and model costs
measured, in [P6_ZTP_PROBE.md](P6_ZTP_PROBE.md) section 11. Not built.

---

## 5. Build steps, after the measurements

1. **The reservation writer** (D1): a set in, per-device outcomes out; verified
   by reading back; refuses the two preconditions; abandon removes the
   reservation.
2. **The config responder** (D2): renders on request, serves only a pending
   device to its reserved address, records every fetch and every refusal as a
   reveal row, keeps nothing.
3. **`ztp` in `build_plan()`**: a stated source (`static | dhcp | ztp`),
   requiring a MAC and an address like `dhcp`, with its blocking reasons named.
   One more option in today's selector, and nothing else in today's interface
   (Stage 7 re-homes onboarding).
4. **The pending row reports ZTP states** (section 2) from their own sources.
5. **Phase 2 unchanged.**
6. **Abandon reverses it**: the reservation is removed and the responder stops
   serving the device.

Every step carries its negative controls, run confined (`scripts/nmas-test`).

---

## 6. Acceptance: Labs 8 and 9, on a throwaway

**Lab 8 (ZTP):** a node booted with NO configuration:

- is leased an address from a reservation the TOOL wrote;
- fetches its bootstrap config from the tool, recorded as a reveal row naming
  its address and the hash of what was served;
- is reached by the tool with the staged credential.

Each of those is observed from its own source.

**Lab 9 (ZTP + IaC):** the same device then runs:

- Phase 2: rotation, RW removal, a true first golden, NetBox, and promotion;
- one intent deploy, which lands the P.1 syslog block; the heartbeat then
  arrives in Loki.

"Infrastructure as code" is literal here: the device's configuration came
from committed intent, through an approved template, by a confirmed program.

**What it does not prove, stated before the run:**

- a relayed path (DHCP phase 3);
- physical hardware;
- Cisco PnP (option 43), and Python-script ZTP on IOS-XE;
- the bulk job;
- reboot-safety (the throwaway is destroyed, not rebooted).

---

## 7. States that would be wrong and look right, and what makes each visible

| Wrong state | What makes it visible |
|---|---|
| A reservation in memory only, gone at Kea's next restart | The write is verified by reading the FILE back, and M5 restarts Kea |
| A config fetched but not applied | "Fetched, not reached" is its own pending state, with the reveal row's time |
| A served config that is not the committed one | The responder renders from committed intent at request time and records the hash it served |
| A config served to something other than the device | Only the reserved address is served; every refusal is a row |
| A stale server address handed to devices | Derived from Kea's subnet interface, never read from `tftp_server_ip` |
| A device ZTP'd but outside the model's guarantees | Not in the inventory until Phase 2 promotes it, and Phase 2 is unchanged |
