# Deploying NMAS on Ubuntu (headless)

Development is on Windows 11; this is the Linux deployment path. Nothing here is
specific to any network — every address below is a placeholder.

## Prerequisites

```bash
sudo apt install python3 python3-venv python3-pip git
```

`git` is required: the config repository uses `subprocess` git, not a library.

## Install

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin nmas
sudo -u nmas git clone <your-repo-url> /home/nmas/agentic-nmas
cd /home/nmas/agentic-nmas
sudo -u nmas python3 -m venv .venv
sudo -u nmas .venv/bin/pip install --no-deps -r requirements.lock
```

### The local hosts file, `data/lab_hosts.json` (2026-09-29)

The repository is public, so the hosts' users, addresses and tunnel hostnames
are not in it. They live in `data/lab_hosts.json` (`data/` is gitignored), one
entry per host:

```json
{"nmas": {"user": "<user>", "lan": "<nmas-host>", "tunnel": "ssh-nmas.<domain>"},
 "clab": {"user": "<user>", "lan": "<lab-host>", "tunnel": "ssh-clab.<domain>"},
 "pve":  {"user": "root",   "lan": "<hypervisor>", "tunnel": "ssh-pve.<domain>"}}
```

The `nmas` entry may also carry `home` and `checkout`; without them the unit
renderer uses the user's home directory and the checkout it runs from. Three
things read the file, and each REFUSES naming it when it is missing:

- `scripts/nmas-host` (the laptop's way to the hosts);
- `scripts/clab-startup-sync.sh` (the clab sync, on this host; `oxidized-to-config.sh` until Phase 3, still a link to it for one release), for
  `NMAS_URL` and `CLAB` when neither the environment nor the map sets them.
  **The host's `clab-sync` job sets neither, so it needs this file on the host;**
  without it every run refuses and job health names it;
- `scripts/nmas-render-units`, which fills the `deploy/systemd/` templates
  (every unit install step below renders first; the units are never copied).

`scripts/nmas-rotate-credential` reads it only for an advice line, and says the
address cannot be named instead of refusing a rotation.

### Which environment a rebuild produces (measured 2026-09-26, register C40)

**The running host cannot be reproduced by pip's resolver.** It runs Ubuntu
24.04's system Python (3.12.3) with most packages from apt and a few user-level
pip installs, and no venv. Two facts make a naive rebuild different:

- **`requirements.txt` describes no machine.** Installing it gives paramiko
  3.4.0 where the host runs 2.12.0, pysnmp 6.x where the host runs 4.4.12,
  jsonschema 4.20+ where the host runs 4.10.3, and a Flask-SocketIO /
  python-socketio pair that drops a Socket.IO message in the test client (C35).
- **pip refuses the host's own combination.** PyPI's netmiko 4.3.0 declares
  `textfsm>=1.1.3`, and the host runs textfsm 1.1.2 through Ubuntu, which works.
  And Ubuntu ships netmiko, pysnmp, scp and textfsm with NO Python dependency
  metadata, so their real dependencies (lxml, pyasn1, pysmi, ntc-templates, six)
  are visible only to `dpkg`.

So the two faithful rebuilds are:
1. **Ubuntu 24.04 and its apt packages**, the way the host was built. This is
   the only one with Debian's patches.
2. **A venv with `pip install --require-hashes --no-deps -r requirements.lock`.**
   These are the lock's exact files without a resolver, which is what CI does.
   `requirements.lock` is compiled on the laptop from `requirements.txt` by
   `uv pip compile` (its header names the command; docs/NSOT_PHASE4_RECORDS_POSTGRES.md
   section 8.2). Mercury's own venv, `/opt/mercury-venv`, is built by the host steps in
   section 8.3 of that document.

The test tools the host runs the suite with (`nmas-deploy --offline`) are
pinned in `requirements-test.txt`, the same versions CI installs. On the
current host, where pytest is a user-level install:
`python3 -m pip install --user --break-system-packages --no-deps -r requirements-test.txt`.
`--offline` runs in parallel only when the installed `pytest-xdist` is the
pinned version, and says which it did.

`pip install -r requirements.txt`, or the lock WITHOUT `--no-deps`, gives a
third environment that has never been tested against this code.

### Kea: the reservation fragment NMAS owns (P.6 D1, 2026-09-26)

A rebuild must reproduce this host change, or every reservation the tool
writes lives only in Kea's memory until the next restart (register C49).
`kea-dhcp4.conf` stays `root:root 0644` and the tool never writes it. The
tool owns one directory, and subnet 255 includes one file from it:

```bash
sudo install -d -o <user> -g _kea -m 0755 /etc/kea/nmas
sudo install -o <user> -g _kea -m 0644 /dev/null /etc/kea/nmas/reservations-255.json
printf '[]\n' > /etc/kea/nmas/reservations-255.json
```

In subnet `id: 255`, `"reservations": []` becomes
`"reservations": <?include "/etc/kea/nmas/reservations-255.json"?>`. Then
`sudo kea-dhcp4 -t /etc/kea/kea-dhcp4.conf` and a restart. Replace
`<user>` with the service user on a host where NMAS runs as `nmas`.

Three constraints decide the shape, each measured:

- **Under `/etc/kea`, because of AppArmor.** Kea's profiles allow reads of
  `/etc/kea/**` only; a fragment anywhere else is refused whatever its mode.
- **A directory the tool owns, because the tool writes by
  temp-then-rename.** `/etc/kea` is `root 755`, so a fragment directly in
  it would force truncate-in-place, the mechanism that erased
  `user_settings.json` on 2026-09-23.
- **`0755`/`0644`, not `0750`/`0640`, because a confined root is not root
  for file modes.** The profile withholds `dac_override` and
  `dac_read_search`, so `kea-dhcp4 -t` run as root is held to the mode bits
  and could not read `0640`. The daemon runs as `_kea` and could have, so
  `0640` works in production and breaks the offline syntax check. The file
  holds MAC-to-address reservations (inventory, not secrets).

Then tell NMAS where it is: `kea_ztp_fragment` =
`/etc/kea/nmas/reservations-255.json` in `data/user_settings.json`
(`kea_dhcp4_config` defaults to `/etc/kea/kea-dhcp4.conf`). While
`kea_ztp_fragment` is empty, job health shows it as an `unset_guard` row and
a `ztp` plan refuses.

### The ZTP config responder (P.6 D2, D5, D6)

A read-only TFTP responder that serves a pending ZTP device its bootstrap
config. **systemd binds udp/69, so the responder holds no capability**, and
it binds the ZTP INTERFACE, not an address (D3). Install the two units from
the repository and enable the SOCKET, never the service (the socket starts
it):

```bash
# The units are TEMPLATES (the repository is public): render them from data/lab_hosts.json.
# A FRESH directory, and only the files named (render-units refuses a folder holding anything).
d=$(mktemp -d) && scripts/nmas-render-units --out "$d" deploy/systemd/nmas-ztp-responder.socket deploy/systemd/nmas-ztp-responder.service && sudo install -m 0644 "$d/nmas-ztp-responder.socket" "$d/nmas-ztp-responder.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nmas-ztp-responder.socket
systemctl show -p ActiveState,Listen nmas-ztp-responder.socket
```

`BindToDevice=enp6s19` is the interface Kea listens on for the ZTP subnet
(`interfaces-config` in `kea-dhcp4.conf`); edit it if that differs.

**The firewall rule, the second layer** (the responder's "only the reserved
address" is the first). Only the inbound request needs it: the transfer
leaves from a new port and the device's ACKs return on that flow, which
connection tracking already treats as established.

```bash
sudo ufw allow in on enp6s19 proto udp from 10.255.0.0/24 to any port 69 comment 'NMAS ZTP responder (P.6)'
sudo ufw status numbered | grep -n 69
```

Every fetch and every refusal is a row in `data/reveal_audit.jsonl`
(`actor: ztp:<address>`, `kind: device`), with the served config's sha256
and never its text.

Create `.env` with the Anthropic API key (mode `600`, owned by `nmas`):

```bash
sudo -u nmas install -m 600 /dev/null /home/nmas/agentic-nmas/.env
echo 'ANTHROPIC_API_KEY=sk-ant-...' | sudo -u nmas tee -a /home/nmas/agentic-nmas/.env
```

### The startup-config credential check (register C53)

An hourly, READ-ONLY job asks every device whether its startup config
carries the credential NMAS holds (two show commands each, never a save),
writes `data/startup_check.json`, and job health reads that file:

```bash
d=$(mktemp -d) && scripts/nmas-render-units --out "$d" deploy/systemd/nmas-startup-check.service deploy/systemd/nmas-startup-check.timer deploy/systemd/nmas-job-finished@.service && sudo install -m 0644 "$d/nmas-startup-check.service" "$d/nmas-startup-check.timer" "$d/nmas-job-finished@.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nmas-startup-check.timer
sudo systemctl start nmas-startup-check.service
python3 -c 'import json; d=json.load(open("<home>/python/Agentic_NMAS/data/startup_check.json")); print(d["counts"])'
```

Until it is installed, job health's `nmas-startup-check` row reads
`not_installed`, so the gap is visible rather than silent.

### The topology service (register C256, 2026-09-30)

`rcn-topology.service` runs `/usr/local/bin/rcn-topology.py`, which until
2026-09-30 was a copy no commit recorded. The repository's copy is
`deploy/topology/rcn-topology.py`. Install it as a symlink, so the
checkout is the one copy (the C14 rule), keeping the old file beside it:

```bash
sudo cp -p /usr/local/bin/rcn-topology.py /usr/local/bin/rcn-topology.py.pre-c256
sudo ln -sf <home>/python/Agentic_NMAS/deploy/topology/rcn-topology.py /usr/local/bin/rcn-topology.py
sudo systemctl restart rcn-topology.service
curl -s http://localhost:8088/graph.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["meta"])'
```

The last line prints an `islands` count (0 while r6 is not yet polled).
The old script's meta has no `islands` key, so its absence means the old
copy is still the one running. A device appears on the map once its golden
configures SNMP (the generated targets, C232); one with no LLDP link to the
rest is then drawn in the band at the bottom with its reason.

## Deploying an update

`scripts/nmas-deploy` fast-forwards the checkout to origin/main ONLY if CI
passed for that exact commit, then restarts the service and checks it answers.
Link it into your PATH (one copy, versioned):
`ln -sf ~/python/Agentic_NMAS/scripts/nmas-deploy ~/bin/nmas-deploy`. On a
machine that cannot reach GitHub, `nmas-deploy --offline` runs the whole suite
here against the target instead. There is no flag that deploys an unverified
commit. `nmas-deploy --wait` follows a run that is still going (every 20 s, at
most 600 s, printing what it is doing) and deploys when it passes; the gate is
unchanged, only the retrying moves from you to the tool.

**The verdict is of the SET of runs for the commit** (C124). A commit can have
several runs (a push can start two in the same second, and the workflow
cancels superseded runs). Cancelled runs are abandoned attempts, not verdicts;
any run still going means **PENDING (exit 7, wait)**; otherwise the latest
conclusive run by run number decides: **FAILED (exit 1, do not deploy)**, or a
pass. A commit whose every run was cancelled is **CANCELLED (exit 8, deploy the
newer commit or re-run CI)**. Until 2026-09-28 it took the run with the latest
`created_at`, a one-second timestamp: a cancelled run and a passing one from
the same second tied, the cancelled one won, and a good commit was refused
until it was deployed around the gate (C44's first instance).

**Run it in a terminal on the host.** The restart needs `sudo`, and the
restart is deliberately a person's step (a passwordless rule was declined:
CI gates what deploys, a person gates when). Before moving anything it checks
it can restart: with a terminal it asks for the sudo password first; with no
terminal and no cached credential it exits **6** and leaves the checkout
exactly where it was. If a restart still fails after the move, the first line
reads `MIXED VERSION: checkout at X, service running Y -- run sudo systemctl
restart flask-app.service`, and job health's `running-version` row says the
same until it is done.

## Back up the Fernet key

`data/key.key` encrypts stored device credentials **and** settings secrets.
Losing it makes both unrecoverable. Back it up before the first run and keep it
out of git (`data/` is already gitignored).

## systemd unit

`/etc/systemd/system/nmas.service`:

```ini
[Unit]
Description=Agentic NMAS
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=nmas
Group=nmas
WorkingDirectory=/home/nmas/agentic-nmas
Environment="NMAS_HEADLESS=1"
Environment="NMAS_HOST=127.0.0.1"
Environment="NMAS_PORT=5000"
Environment="NMAS_TFTP_ROOT=/srv/tftp"
ExecStart=/home/nmas/agentic-nmas/.venv/bin/python app.py
Restart=on-failure
RestartSec=5

# The app writes only inside its own directory and the TFTP root.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=/home/nmas/agentic-nmas /srv/tftp

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nmas
sudo journalctl -u nmas -f
```

> **What the deployment host actually runs** (measured 2026-09-25). The
> unit is **`flask-app.service`**, not `nmas`: `User=<user>`,
> `WorkingDirectory=` the checkout, `Restart=always`, enabled at boot,
> journal output. It has **none** of the hardening above and no
> `NMAS_HEADLESS` / `NMAS_HOST`. `~/bin/nmas-deploy` restarts it by name
> after a fast-forward pull. Neither file is in this repository.
>
> **The log is `logs/device_manager.log`, not the journal**, under either
> unit name. `app.py` attaches its rotating file handler at the root logger,
> so every `modules.*` logger writes there. The journal gets only what
> reaches stdout, which is the werkzeug start-up banner. `journalctl -u nmas`
> prints `-- No entries --` on that host, and `journalctl -u flask-app`
> would show start-ups and not much else. Neither is the place to look for a
> failure. Hardening the unit is [NSOT_PLAN.md](NSOT_PLAN.md) **6.5**.

`NMAS_HEADLESS=1` is what stops the app trying to open a browser at startup.

## A CSP violation in the browser console is not a defect

Cloudflare's Web Analytics, when enabled for the hostname, injects a beacon
script into every page. The Content-Security-Policy blocks it (as it should:
the pages load scripts only from the host), and the console reports that.
Turn Web Analytics off for the hostname in Cloudflare rather than widening the
policy (docs/UPDATE.md, 2026-09-30).

## Binding and exposure

**The app has no authentication layer.** It is built for a trusted lab or
management network. Do not bind it to a public interface.

`NMAS_HOST=127.0.0.1` keeps it on loopback. To reach it from elsewhere, put it
behind something that authenticates:

- **Reverse proxy** (nginx/Caddy) terminating TLS and enforcing auth. Proxy to
  `127.0.0.1:5000`. The app uses Socket.IO, so the proxy must pass WebSocket
  upgrades:

  ```nginx
  location / {
      proxy_pass http://127.0.0.1:5000;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
  }
  ```

- **Zero Trust tunnel** (Cloudflare Tunnel, Tailscale) pointed at
  `127.0.0.1:5000`, with access policy at the tunnel.

Either way the identity check happens in front of the app, because the app has
none of its own.

## Collector ports

The built-in SNMP trap receiver (UDP 1162) and NetFlow collector (UDP 9996) use
unprivileged ports by default, so no `CAP_NET_BIND_SERVICE` is needed. If an
external collector already owns a port, turn the built-in one off in
**Settings → Integrations → Built-in collectors** rather than changing code.

Ports themselves are per-device-list settings in `modules/collector_config.py`.

## SSH algorithm compatibility

Older network devices need legacy KEX and host-key algorithms that OpenSSH 9.x
disables by default. Netmiko/Paramiko negotiate independently of the system SSH
client, so this usually needs no change — but if you add a system-level
`ssh_config`, do not tighten algorithms the devices still require.

## Verify

```bash
cd /home/nmas/agentic-nmas
sudo -u nmas .venv/bin/pytest          # expect 209 passed
curl -s localhost:5000/settings/integrations/status | head
```

A healthy unconfigured install reports every integration as `not_configured` —
that is correct, not an error.
