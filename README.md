# Agentic Network Management and Automation

A Flask-based web application for managing, automating, and monitoring Cisco IOS network devices. It provides a unified interface for device inventory, remote SSH command execution, multi-device parallel operations, live terminal access, Jenkins CI/CD integration, topology visualization, SNMP/NetFlow/syslog monitoring, NetBox IPAM/DCIM sync, config generation, and config backup and drift detection.

## Features

### Device Management
- Per-list device inventory stored as encrypted CSV files (`data/lists/{slug}/devices.csv`)
- Fernet-encrypted credential storage (passwords, enable secrets)
- Real-time online/offline status via background ping worker
- Multiple named device lists with create, rename, delete, and switch support
- Drag-and-drop device reordering
- Manage button opens device page in a new tab

### Remote Execution
- Single-device command execution with automatic prompt/timing routing
- Multi-line scripts in enable or configure-terminal mode
- Multi-device parallel operations (enable commands, config sets, TFTP upload/download, flash file management, static-route removal)

### AI
The AI assistant, its background agent, the chat panel and the approval tab were removed on
2026-10-14 (tag `pre-remove/ai-family`). Phase 8 brings AI back as a responder that proposes
changes for a person to confirm and never confirms one (docs/PHASE8_PLAN.md).

### CI/CD Integration
- Jenkins pipeline creation, scheduling, triggering, and result polling
- Per-list pipeline registry with build history
- Deleting a device list automatically removes all associated Jenkins pipelines

### Config Generation
- Cisco IOS configuration generator for 10 feature types (routing, interfaces, ACLs, NAT, VPN, QoS, and more)
- Generates Python Jenkins verification scripts and pipeline XML for each pushed config
- Per-job metadata stored so CI success callbacks can create golden-config approval requests

### Drift Detection
- Standalone drift checker (`modules/drift_check.py`) that runs on a schedule without consuming Claude API tokens
- SSHes devices and diffs their running config against the golden config baseline
- Findings are routed to the approval queue for human review

### NetBox IPAM/DCIM Integration
- Syncs device inventory to NetBox DCIM: model, serial, platform, and software version extracted from `show version` / `show inventory`
- Each device list creates its own NetBox region, site, and VRF
- All interface IPs are pushed to NetBox IPAM under the list VRF (per-interface VRF respected as override)
- Secondary IPs, IPv6 addresses, LAG (port-channel) membership, switchport mode/VLAN tags, and dot1q sub-interfaces all synced
- Static routes synced as IPAM prefixes
- VPN tunnels (GRE, DMVPN/mGRE, IPsec) synced to NetBox VPN tunnel records with termination endpoints
- Structured local-context data for OSPF, BGP, NTP, and SNMP per device
- Protocol tags auto-applied based on running config (OSPF, BGP, DMVPN, NTP, SNMP, ACL, NAT, etc.)
- Primary IPv4 fallback chain: exact SSH-IP match → IPAM search → Loopback0 preference → first available IP → SSH IP created as /32
- "Remove" button in the NetBox panel cleans up the list's region, site, VRF, and all associated device records
- Deleting a device list automatically removes its NetBox data and Jenkins pipelines before wiping local files

### Topology
- CDP (physical), OSPF, BGP, and DMVPN/mGRE tunnel topology discovery
- Interactive vis.js graph with per-protocol sub-tabs and hide/show per node
- Hub/spoke role labels for tunnel overlays; OSPF area and BGP AS number shown on edges
- Saved node positions and hidden-node state persisted per list

### Monitoring
- Syslog event monitoring (the in-app SNMP trap receiver and NetFlow collector left with the AI
  family, 2026-10-14)

### History & Audit
- Timestamped config backup with unified-diff comparison between any two backups
- Golden config baselines for drift detection

## Project Structure

```
Claude_NMAS/
├── app.py                          # Flask application — all routes and SocketIO handlers
├── requirements.txt                # Python dependencies
├── Jenkinsfile                     # Reference Jenkinsfile for CI pipeline
├── telnetlib.py                    # telnetlib shim (removed from Python 3.13+)
├── CLAUDE.md                       # Project instructions for Claude Code
├── modules/
│   ├── approval_queue.py           # The drift check's queue of items a capture closes
│   ├── backups.py                  # Config backup retrieval and storage
│   ├── bulk_ops.py                 # Multi-device parallel operations
│   ├── commands.py                 # SSH command execution with prompt/timing routing
│   ├── config.py                   # Paths, constants, user settings
│   ├── configure.py                # Cisco IOS config generator (10 feature types) + Jenkins XML
│   ├── connection.py               # Netmiko SSH connection pool and ping worker
│   ├── device.py                   # Device CRUD, encryption, multi-list management
│   ├── drift_check.py              # Scheduled golden-config drift checker
│   ├── jenkins_runner.py           # Jenkins CI pipeline integration
│   ├── netbox_client.py            # NetBox IPAM/DCIM sync (devices, IPs, tunnels, VRFs)
│   ├── quick_actions.py            # Quick action (command shortcut) persistence
│   ├── terminal.py                 # Live SSH terminal via Paramiko + SocketIO
│   └── utils.py                    # Shared utility helpers
├── templates/
│   ├── base.html                   # Base layout and navigation
│   ├── index.html                  # Device list, topology, monitoring, and settings
│   └── device.html                 # Per-device management page
├── static/
│   ├── css/                        # Bootstrap CSS
│   └── js/                         # Bootstrap and xterm.js
└── data/                           # Runtime data (auto-created on first run)
    ├── key.key                     # Fernet encryption key (auto-generated)
    ├── secret.key                  # Flask session secret (auto-generated)
    ├── device_lists.json           # Active list and list registry
    ├── jenkins_checks.json         # Jenkins server connection settings
    ├── agent_timers.json           # The drift check's schedule (the file kept its old name)
    ├── user_settings.json          # User preference overrides (TFTP IP, NetBox URL/token, etc.)
    └── lists/
        └── {slug}/                 # Per-list data directory
            ├── devices.csv         # Encrypted device inventory
            ├── backups/            # Config backup files + index
            ├── golden_configs/     # Golden config baselines
            ├── approval_queue.json # The drift check's queued items
            └── jenkins_pipelines.json
```

## Prerequisites

- Python 3.10+
- `pip install -r requirements.txt`
- Cisco IOS devices with SSH enabled (`ip ssh version 2`)
- Jenkins server (optional, for CI/CD pipeline features)
- SNMP-enabled devices pointing traps at this host (optional)
- NetBox instance (optional, for IPAM/DCIM sync)

## Quick Start

1. Clone or download the project.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the application:
   ```bash
   python app.py
   ```
   The app opens `http://127.0.0.1:5000` in your browser automatically.

## Configuration

All settings are configurable from the **Settings** button on the home page, including:
- **Jenkins** — server URL, username, API key, and webhook token
- **TFTP server IP** — used for bulk file transfer operations
- **NetBox** — instance URL and API token for IPAM/DCIM sync

The `data/` directory and all subdirectories are created automatically on first run. The Fernet encryption key (`data/key.key`) is auto-generated on first run — **back this up**, as losing it makes stored credentials unrecoverable.

## NetBox Integration

The NetBox sync reads golden configs as the source of truth — no live SSH sessions needed:

1. Open **Settings** and enter your NetBox URL and API token.
2. Click **Sync to NetBox** in the NetBox panel on the dashboard.
3. Each device list is created as a region, site, and VRF in NetBox.
4. All devices, interfaces, IP addresses, VPN tunnels, and static routes are pushed automatically.
5. To clean up, click **Remove** in the NetBox panel — this deletes the list's region, site, VRF, and all associated records from NetBox.

## Testing

The suite runs offline: every test, unit or not, is refused any network connection, and a run
that touches the checkout's `data/` fails. `scripts/nmas-test` runs it; `scripts/nmas-coverage`
reports which automation functions the unit tests reach, and CI gates on that report as a
ratchet. How to run both, the test tiers, how coverage is counted and how to read the report:
[docs/TESTING.md](docs/TESTING.md).

## Security Notes

- All device passwords and enable secrets are encrypted at rest using Fernet symmetric encryption. The key lives at `data/key.key` — protect it.
- There is no built-in authentication system. The app is intended for use on a trusted management workstation or network segment. Do not expose port 5000 to untrusted networks.
- The `.env` file is excluded from version control via `.gitignore`.
- SSH connections use Paramiko/Netmiko with `AutoAddPolicy` for host keys — acceptable for a closed lab environment, but review before using on untrusted networks.

## Author

[Author]
