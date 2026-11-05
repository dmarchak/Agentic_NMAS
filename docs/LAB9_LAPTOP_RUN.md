# The final SDN lab on the laptop: the lab kit

The operator's request, 2026-11-05, for the first hardware sitting (Thursday 2026-11-05). Mercury
runs on the laptop, connected to the lab, with a second Claude Code session troubleshooting it
live. "Lab 9" here is the final SDN lab of docs/LAB9_SDN_GAP.md, never the automation course's
Lab 9 (docs/LAB9_PLAN.md).

The kit is `lab/sdn-laptop/`. It is lab tooling, never product code (CLAUDE.md, "The product is
network-agnostic").

## 1. What the kit is

A separate Mercury installation on the laptop:

| Part | Where | What keeps it separate |
|---|---|---|
| Mercury's code | `~/nmas-sdn-lab/mercury/`, a git worktree detached at the pinned sha | never the main working tree; `kit start` refuses a worktree that is not clean |
| Mercury's data | `~/nmas-sdn-lab/data/` (`NMAS_DATA_DIR`): its own settings, credential key and credentials | nothing is read from or written to the checkout's `data/` |
| NetBox | Docker Compose, `lab/sdn-laptop/compose.yml`, project `nmas-sdn-lab-netbox`, on 127.0.0.1:8001 | its own volumes; its internal secrets generated owner-only in `~/nmas-sdn-lab/netbox/secrets.env`, never printed |
| The network list | `lab9`, created by `kit init` | no git remote: `kit check` refuses one |
| The run | `~/nmas-sdn-lab/run/` (pid, log, the exception's expiry) | Mercury on 127.0.0.1:5080 only |

`~/nmas-sdn-lab` is `KIT_HOME`; set `KIT_HOME` to move it.

**The refusals:**
- **`kit start` refuses to start** when any setting points at the NMAS host's services, its
  golden repository or a GitHub config repository (`lab/sdn-laptop/kit_check.py`).
  - It reads the installation's settings, every list's settings, and every list's
    config-repository remotes.
  - It takes the NMAS host's LAN address and tunnel name (and that name's domain) from
    `data/lab_hosts.json` through `scripts/nmas-host --field`. It prints key names, never values.
  - It also refuses a Mercury bound off loopback, a NetBox that is not the kit's own, and a
    missing host name (it cannot rule out what it was not given).
- **`nmas-deploy` refuses to run from this installation:** `kit init` writes `.nmas-lab-kit` in
  the worktree's root, and `scripts/nmas-deploy` refuses any run from a checkout holding it, or
  aimed at one (`LAB_KIT_MARKER`, tests/test_lab_sdn_laptop_kit.py).

**The pinned sha** is the newest sha that is deployed on the NMAS host and CI-green, recorded as
`PIN_SHA` in `~/nmas-sdn-lab/kit.env`. `kit status` prints it. A fix the second session commits
on `lab9-live` is run by `kit repin <sha>` (section 6).

## 2. What runs where

| Service | Where | Needed for | Without it |
|---|---|---|---|
| NetBox | the laptop (the kit's Compose) | **required:** inventory, onboarding, the lab9 list, intent | nothing works |
| Mercury | the laptop, 127.0.0.1:5080 | **required** | — |
| The SDN controller | **the lab's controller server**, not the laptop. The lab's hardware list names a controller server (LAB9_SDN_GAP.md, "The hardware"), and the OVS servers reach it out of band (Part A, A1). Mercury reaches its REST API over the lab leg | every SDN read and write (A2 to A6, B2, B3): through the driver's northbound calls (LAB9_SDN_GAP.md A6) | the SDN screens say the controller cannot be asked |
| Grafana | optional, not in the kit | the Monitoring page and the device Monitoring tab | they say Grafana is not configured |
| Prometheus | optional, not in the kit | interface rates and the telemetry-driven checks | those checks say not configured |
| Loki | optional, not in the kit | the Logs tab, syslog-driven restart detection and the log checks | those say not configured |
| PostgreSQL records | not used | — | every records store stays on its files (`records_db_host` empty) |
| Kea, ZTP | not used | — | off (LAB9_SDN_GAP.md 2.3: not needed for this lab) |

Discovery and onboarding need NetBox, Mercury and SSH to the switches, and none of the optional
three. Job health shows the NMAS host's own jobs (systemd units, the updater, Proxmox, the GitHub
readers) as failing on the laptop. That is C2521, expected, and not a fault of the kit.

## 3. Safety defaults on the kit

| Default | How | Shown by |
|---|---|---|
| Heal off | `heal_mode` off (written by `kit init`; the default) | `kit preflight`'s "heal off" |
| The SDN loop in human-in-the-loop mode | a new network is not marked `lab`, and AUTO runs only on a network marked lab (`modules/sdn/modes.py` `AUTO_STAGE`); the loop's mode is HITL until a person turns AUTO on | "SDN AUTO impossible", "SDN loop in HITL" |
| Background AI off | `ai_background` empty (the default) | "background AI off" |
| Read-only onboarding first | section 5: the switches enter read-only, and nothing is written to them | the discovery captures |
| Identity: option (c), the gate-off settings, for the sitting only (the operator, 2026-11-05; C2520) | `kit start` turns off the gates for configure, confirm and approve; reveal, publish_remote and break_glass stay on | "reveal, publish and break-glass gated"; History |
| Host and Origin checks | `allowed_host_names` 127.0.0.1, localhost and ::1; `require_same_origin_writes` on (`modules/request_origin.py`) | "Host check on", "same-origin writes on" |

**The identity exception and its expiry:**
- `kit start` records it in the installation's History: Installation, "identity exception on",
  with each gate's old and new value and the reason with its expiry.
- **Its expiry is enforced.** A user timer (`nmas-sdn-kit-expiry.timer`) runs `kit stop` 14 hours
  after the start, and the exception never outlives the sitting.
- `kit stop` restores the three gates and records "identity exception off" in History.
- The next `kit start` prints the last record ("last restored at …") before it turns the
  exception on again.

**The Host and Origin checks:**
- A request whose Host is not 127.0.0.1, localhost or ::1 is refused (DNS rebinding).
- A write is refused when:
  - its `Sec-Fetch-Site` is anything but `same-origin`;
  - its `Origin` is not Mercury's own;
  - it has no Origin and a foreign `Referer`;
  - it carries none of the three.
- The Socket.IO handshake accepts only Mercury's own origin.

Mercury carries no CSRF tokens (C248). These standard-header checks stand in for them. Both are
off on every other install until the operator's report on their callers (C2522).

## 4. The commands

Run them from the kit's own copy, `~/nmas-sdn-lab/mercury/lab/sdn-laptop/kit`, once `init` has
made it. `init` itself runs from the main checkout's `lab/sdn-laptop/kit`.

| Command | What it does |
|---|---|
| `kit init <sha>` | the kit folder (owner-only), the worktree at `<sha>`, the marker, `kit.env`, NetBox's internal secrets (its v2-token pepper among them, by `kit ensure-pepper`), the images pulled, the installation's settings and the `lab9` network |
| `kit ensure-pepper` | NetBox's v2-token pepper (`API_TOKEN_PEPPER_1`, which the image turns into `API_TOKEN_PEPPERS = {1: …}`, as the NMAS host's netbox-docker does) added to `secrets.env` once, 64 hex characters, owner-only, never printed, never replaced (a new one would void every v2 token issued); it takes effect at the next `kit start` |
| `kit netbox-admin` | NetBox's superuser; **the operator types its passphrase** |
| `kit start` | the check (refuses on any finding), lab9guard installed on `LAB_IF` (sudo asks; refuses if `LAB_IF` is unset or absent), the last exception said, the exception on with its timer, NetBox up, Mercury started as the user unit `nmas-sdn-kit-mercury`, then waits up to 100 s for `/health` ready |
| `kit preflight` | section 7's lines (lab9guard read by `sudo -n`: run `sudo -v` first), the safety lines and the settings check, one PASS or FAIL each |
| `kit status` | the pinned sha, what runs, the last exception record |
| `kit stop` | the gates restored and recorded, the timer cancelled, Mercury's unit stopped, NetBox stopped, lab9guard removed (sudo asks; an unattended stop leaves it in place and logs so) |
| `kit repin <sha>` | the worktree moved to `<sha>` (Mercury stopped first, the worktree clean) |
| `kit check` | the settings check alone |
| `kit reset` | asks for `RESET`, stops, then deletes the kit's data folder and NetBox's volumes. The main checkout, the NMAS host and the lab are untouched. `kit init` writes the settings and `lab9` again |

**NetBox's API token:** the operator creates it in NetBox (the user menu, API Tokens) and enters
it in Mercury at Settings › Installation › Connections › NetBox connection (API token,
Replace…). Mercury keeps it encrypted, and nobody else reads it.
- **A v2 token** (NetBox 4.6's own) needs the pepper above. The auth scheme is `Bearer`.
- **A v1 token** works without it. The auth scheme is `Token`. The operator's first run used one,
  because the kit's first release gave NetBox no pepper (NetBox: "Unable to save v2 tokens:
  API_TOKEN_PEPPERS is not defined").
- **The preflight's "NetBox can save a v2 token"** reads NetBox's running settings in its
  container for a pepper of id 1, at least 50 characters. It prints the length, never the
  value.

## 5. Discovery for the unknown switches

The switch models are unknown until the sitting. The read-only onboarding path and the per-vendor
capture lists are in docs/LAB9_DISCOVERY.md:
- Arista EOS through `arista_eos`;
- HP through `hp_procurve`, `hp_comware` or `aruba_os` (AOS-CX, if the HP is one);
- the Open vSwitch servers through `ovs_linux`. The output of each capture is the input
to the driver build (LAB9_SDN_GAP.md section 2, item 1). Nothing is written to a switch.

**The OpenFlow configuration** that the captures confirm is in docs/LAB9_OPENFLOW.md. It covers
the values read from NetBox, the per-vendor templates with their citations, the draft and
confirmed rule, and Open vSwitch's operation end to end.

**At the sitting:**
- **What it can do:**
  - map each switch's NetBox platform to its discovery driver on Settings › Installation ›
    Platforms and roles, its dialect "none: read only";
  - give the switches a login on Credentials › Profiles (the operator types it);
  - read the capture list through Show commands or Ask the device, masked;
  - every write to these switches is refused, held or not, naming the driver and the call
    (`modules/discovery.py`, `connection._guard_writes`).
- **What it cannot do yet:**
  - **create the switches' NetBox records in Mercury:** Add device… and Adopt a device… need a
    dialect, so the records are made in NetBox's own UI for now (C2527);
  - import a switch whose only management address is IPv6 (C1245);
  - rely on `aruba_os` paging on AOS-CX (C2529);
  - deploy, verify, take a golden or check drift on these switches: that waits for the driver
    build.

## 6. The second session (troubleshooting, live)

- **Its worktree:** branch `lab9-live` at the pinned sha. Its first prompt is
  `~/Documents/nmas-reports/lab9-live-first-prompt.md` (kept outside the repository).
- **Its scope:**
  - it troubleshoots the laptop installation;
  - it commits a fix on `lab9-live` and runs it at once with `kit stop`,
    `kit repin <sha>` and `kit start`;
  - it gates before any push, after the sitting;
  - it changes no device and never deploys to the NMAS host (the kit's marker refuses
    `nmas-deploy`).

## 7. The laptop's networking: the operator's sheet

The laptop is dual-homed: the Wi-Fi carries the default route to the internet, the Ethernet
carries the lab's subnets, and the laptop forwards nothing to or from the lab. Each step ends
with the line it must print.

**Forwarding stays on for the laptop; only the lab interface is fenced** (the operator,
2026-11-05). Turning forwarding off globally would break every container's and VM's outbound
access on the laptop, and Docker already sets the FORWARD policy to DROP when it enables
forwarding. So the kit installs its own guard:
- **`kit start` installs the nftables table `inet lab9guard`:** a forward chain at priority -10,
  before Docker's filter chains, that drops anything whose `iifname` or `oifname` is the lab
  interface. That interface is `LAB_IF` in `kit.env`, checked at start to exist.
- **`kit stop` removes the table.**
- Each one asks for sudo, says why, and logs that it did in `~/nmas-sdn-lab/run/kit.log`.
- An unattended stop (the identity exception's expiry timer) cannot answer sudo. It leaves the
  guard in place and logs that it did, which is the safe direction.
- The template is `lab/sdn-laptop/lab9guard.nft.in`. The preflight's check
  (`kit_guard_check.py`) reads the table's rules and counters, never the forwarding sysctl.

1. **Plug in the lab cable** (the interface named in `kit.env` as `LAB_IF`).
   - PASS: `ip -br link show <LAB_IF>` shows `UP`.
2. **The lab leg with no default route: the NetworkManager profile `lab9`** on `LAB_IF`, with
   never-default and ignore-auto-dns for IPv4 and IPv6. The operator made it on 2026-11-05 on
   `enp129s0` (the laptop's built-in Ethernet, a stable name), DHCP for both families. To
   remake it: `nmcli con add type ethernet ifname <LAB_IF> con-name lab9 ipv4.method auto
   ipv6.method auto ipv4.never-default yes ipv6.never-default yes ipv4.ignore-auto-dns yes
   ipv6.ignore-auto-dns yes`.
   - The preflight's "lab profile" line checks the profile bound to `LAB_IF` (`LAB_PROFILE` in
     `kit.env`), each of the four settings `yes`, and, once a cable is in, the profile active
     on `LAB_IF` (`kit_net_check.py`).
   - Its "default route stays on the Wi-Fi" line checks every IPv4 and IPv6 default route on
     `WIFI_IF` (`wlp130s0`), none on the lab interface.
   - PASS: "PASS lab profile: 'lab9' is active on enp129s0 …" with the cable in ("… is ready on
     enp129s0 …, not active: no carrier" without), and "PASS default route stays on the Wi-Fi:
     IPv4 via wlp130s0, IPv6 via wlp130s0".
3. **Route the lab's subnets over the lab leg,** each one it does not reach directly:
   `nmcli con mod lab9 +ipv4.routes "<subnet/len> <lab gateway>"`, then `nmcli con up lab9`.
   - PASS: `ip route get <a switch's management address>` names `dev <LAB_IF>`.
4. **Fill `kit.env`:** `LAB_IF` and `CONTROLLER_ADDR` (the controller server's address on the lab
   leg).
5. **`kit start`,** which installs lab9guard (sudo asks).
   - PASS: "lab9guard: installed (inet lab9guard, forward priority -10, drops iifname and
     oifname <LAB_IF>), by sudo".
6. **`sudo -v`, then `kit preflight`,** which reads the table with `sudo -n` and asks nothing.
   - PASS: "PASS lab interface up", "PASS lab profile: 'lab9' is active on <LAB_IF> …", "PASS
     default route stays on the Wi-Fi …", "PASS no forwarding to or from the lab interface:
     lab9guard in force on <LAB_IF> …" and "PASS controller OpenFlow port".

The preflight checks steps 1 to 6 on every run, and changes nothing.
