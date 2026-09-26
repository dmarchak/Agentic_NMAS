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
| **(B) An include fragment the tool owns** (recommended) | The management subnet's `reservations` come from a separate file via Kea's `<?include?>`; the file is owned by the NMAS service user, group `_kea`, mode `0640` (a handoff names its reader); the tool writes it, then `config-test`, then `config-reload` | Reservations for that subnet only: the tool cannot touch any other part of Kea's config | Yes: it is a file |
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

The transport is a measurement, not a choice (M3):

- **TFTP** needs port 69, which is privileged. The unit would need
  `CAP_NET_BIND_SERVICE`, which belongs with the unit hardening in 6.5.
- **HTTP** on the app's own port needs nothing new, if the platform accepts an
  HTTP URL in option 67.

### D3. Where the destination lives

§6a's open question. For P.6 the answer is that the config server's address is
**derived, not configured**: it is the host's own address on the interface
Kea's reserving subnet is served on (`10.255.0.10` today). A configured copy of
that fact is how `tftp_server_ip` came to name `192.168.0.30`. A per-list
store beside `source.json` is the right shape when a second network needs a
second segment, and P.6 does not need one.

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
