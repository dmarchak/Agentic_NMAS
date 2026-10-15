# Mercury: Network Management and Automation

Mercury is a Flask application that manages, automates and monitors Cisco IOS and IOS-XE
devices. It is the frontend and control plane of a small network-automation platform (NMAS):
it reads and writes the systems that own the facts, and it executes changes on the network.
It is not itself a source of truth.

The governing definition is [docs/MERCURY_CHARTER.md](docs/MERCURY_CHARTER.md).

## Sources of truth

| Facts | Owner | Mercury |
|---|---|---|
| Devices: existence, identity, role, site, platform, status | NetBox | reads them; writes only as the first step of a confirmed operation |
| Intent, golden configurations, templates | the network's git repository | the one writer, every write a commit |
| DHCP reservations | Kea | the front end to them |
| Metrics and dashboards | Prometheus, Grafana | reads; generates targets from the inventory |
| Logs | Loki | reads |
| The archive past retention | MinIO | reads and writes archives |

## How a change reaches a device

Every device-changing operation runs the same lifecycle:

1. **Preview:** the exact program that will be sent, secrets masked.
2. **Confirm:** a verified person confirms it by its hash; what is confirmed is what is sent,
   byte for byte, recomputed at apply and refused if anything moved.
3. **Apply:** merge-only, holding the device (one operation per device, across processes); a
   removal is a separate, explicit mode where each unit is selected with a reason.
4. **Verify:** scaled to what the program touched, waiting out settle windows.
5. **Roll back** what landed, if verify fails, and say what that achieved per device.
6. **Record:** a commit in the network's repository and a receipt, readable later.

Intent lives as committed `host_vars/<device>.yml`, rendered through templates; goldens are
committed configurations. Readers take what is committed, never a working-tree file.

## The interface

The current interface is under `/v2/` (`templates/v2/`): server-rendered pages with vendored
htmx and Alpine.js under a strict Content Security Policy. Each screen has a page in the
built-in manual (`docs/manual/`, served at `/v2/help/<page>`). The older Bootstrap pages are
being retired ([docs/CUTOVER.md](docs/CUTOVER.md)).

## Identity and secrets

- A person is identified by an access proxy's **signed** assertion (Cloudflare Access), verified
  against the proxy's keys, together with a trusted socket peer; a header alone is not evidence
  (`modules/identity.py`, [docs/NSOT_AUTHORIZATION.md](docs/NSOT_AUTHORIZATION.md)). Confirming,
  approving and revealing need a verified person.
- Device credentials are encrypted at rest (Fernet); the key is `data/key.key`, created on first
  run. Back it up: without it the stored credentials cannot be opened
  ([docs/SECRETS.md](docs/SECRETS.md)).
- Secrets are masked on the way out: in previews, downloads, logs and every response carrying
  configuration.

## Running it

Python 3.10 or later (CI uses 3.12.3).

```bash
pip install -r requirements.txt
python app.py                      # http://127.0.0.1:5000
NMAS_HEADLESS=1 python app.py      # without opening a browser
```

Settings (integrations, server bind) are set from the Settings pages. A Linux deployment as
a service is described in [docs/DEPLOY_LINUX.md](docs/DEPLOY_LINUX.md), updates in
[docs/UPDATE.md](docs/UPDATE.md).

## Tests

The suite runs offline: every test is refused any non-loopback connection, and a run that
changes the checkout's `data/` fails.

```bash
scripts/nmas-test            # the suite, confined to loopback
scripts/nmas-test -n auto    # in parallel
```

CI runs it in four shards, measures which automation functions the unit tests reach (a
ratchet that only rises), and a nightly job runs mutation testing on changed automation
functions. Details: [docs/TESTING.md](docs/TESTING.md).

## Repository map

- `app.py`, `routes/`: the web application and its blueprints (`routes/v2.py`,
  `routes/device_v2.py` for the current interface).
- `modules/nsot/`: the network-source-of-truth core: the repository and its manifest, intent,
  rendering, deploy, verify, restore, receipts and the operations.
- `modules/`: stores and safety (settings, secrets, identity, route gates, redaction), the
  readers, jobs and the data behind each screen.
- `modules/integrations/`: NetBox, Grafana, Prometheus, Loki, Kea, MinIO.
- `docs/`: the charter, the plans, the register of findings
  ([docs/OPEN_FINDINGS.md](docs/OPEN_FINDINGS.md)) and the architecture
  ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

## Author

[Author]
