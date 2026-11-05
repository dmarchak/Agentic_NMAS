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
| `kit init <sha>` | the kit folder (owner-only), the worktree at `<sha>`, the marker, `kit.env`, NetBox's internal secrets, the images pulled, the installation's settings and the `lab9` network |
| `kit netbox-admin` | NetBox's superuser; **the operator types its passphrase** |
| `kit start` | the check (refuses on any finding), the last exception said, the exception on with its timer, NetBox up, Mercury started, then waits up to 100 s for `/health` ready |
| `kit preflight` | section 7's lines, the safety lines and the settings check, one PASS or FAIL each |
| `kit status` | the pinned sha, what runs, the last exception record |
| `kit stop` | the gates restored and recorded, the timer cancelled, Mercury stopped by its pid (only if it is still `app.py`), NetBox stopped |
| `kit repin <sha>` | the worktree moved to `<sha>` (Mercury stopped first, the worktree clean) |
| `kit check` | the settings check alone |
| `kit reset` | asks for `RESET`, stops, then deletes the kit's data folder and NetBox's volumes. The main checkout, the NMAS host and the lab are untouched. `kit init` writes the settings and `lab9` again |

**NetBox's API token:** the operator creates it in NetBox (the user menu, API Tokens) and enters
it in Mercury at Settings › Installation › NetBox. Mercury keeps it encrypted, and nobody else
reads it.

## 5. Discovery for the unknown switches

The switch models are unknown until the sitting. The read-only onboarding path and the per-vendor
capture lists (Arista EOS through `arista_eos`; HP through `aruba_os` and `hp_procurve`, and
AOS-CX if the HP is one) are in docs/LAB9_DISCOVERY.md. The output of each capture is the input
to the driver build (LAB9_SDN_GAP.md section 2, item 1). Nothing is written to a switch.

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
  - read a Comware switch (`display` is not allowlisted, C2530);
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
carries the lab's subnets, and the laptop forwards nothing between them. Each step ends with the
line it must print.

1. **Before the lab:** stop Docker from turning forwarding on, then restart it.
   - Docker sets `net.ipv4.ip_forward=1` when it starts. The kit's NetBox talks only on its own
     bridge and to loopback, which needs no forwarding.
   - `sudo install -m 0644 /dev/null /etc/docker/daemon.json` only if the file does not exist.
     Otherwise add the key to it by hand.
   - Then set it to `{"ip-forward": false}`, and run
     `sudo systemctl restart docker && sudo sysctl -w net.ipv4.ip_forward=0`.
   - PASS: `cat /proc/sys/net/ipv4/ip_forward` prints `0`.
2. **Plug in the lab cable** (the interface named in `kit.env` as `LAB_IF`).
   - PASS: `ip -br link show <LAB_IF>` shows `UP`.
3. **Address the lab leg with no default route.** Use the address the lab's management plan
   gives, or the lab's DHCP with its default route ignored:
   - `nmcli con add type ethernet ifname <LAB_IF> con-name lab9 ipv4.method <manual|auto>
     ipv4.addresses <addr/len> ipv4.never-default yes ipv6.never-default yes
     ipv4.ignore-auto-dns yes`;
   - `nmcli con up lab9`.
   - PASS: `ip route show default` names only the Wi-Fi interface.
4. **Route the lab's subnets over the lab leg,** each one it does not reach directly:
   `nmcli con mod lab9 +ipv4.routes "<subnet/len> <lab gateway>"`, then `nmcli con up lab9`.
   - PASS: `ip route get <a switch's management address>` names `dev <LAB_IF>`.
5. **Forwarding stays off,** IPv4 and IPv6.
   - PASS: `sysctl net.ipv4.ip_forward net.ipv6.conf.all.forwarding` prints both `= 0`.
6. **Fill `kit.env`:** `LAB_IF` and `CONTROLLER_ADDR` (the controller server's address on the lab
   leg).
   - PASS: `kit preflight` prints "PASS lab interface up", "PASS default route via Wi-Fi",
     "PASS IP forwarding off" and "PASS controller OpenFlow port".

The preflight checks steps 2 to 6 on every run, and changes nothing.
