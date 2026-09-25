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
sudo -u nmas .venv/bin/pip install -r requirements.txt
```

Create `.env` with the Anthropic API key (mode `600`, owned by `nmas`):

```bash
sudo -u nmas install -m 600 /dev/null /home/nmas/agentic-nmas/.env
echo 'ANTHROPIC_API_KEY=sk-ant-...' | sudo -u nmas tee -a /home/nmas/agentic-nmas/.env
```

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
> unit is **`flask-app.service`**, not `nmas`: `User=dmarchak`,
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

## Jenkins step shell

Generated pipelines default to Windows `bat` steps. For a Linux Jenkins agent,
set **Settings → Integrations → Jenkins step shell** to `sh` before creating
pipelines. Existing pipelines are not rewritten; regenerate them.

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
