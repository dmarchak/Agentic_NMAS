# Agentic Network Management and Automation

A Flask-based web application for managing, automating, and monitoring Cisco IOS network devices. It provides a unified interface for device inventory, remote SSH command execution, multi-device parallel operations, live terminal access, an AI-powered autonomous network agent (Claude), Jenkins CI/CD integration, topology visualization, SNMP/NetFlow/syslog monitoring, NetBox IPAM/DCIM sync, config generation, and config backup and drift detection.

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
- Ansible playbook execution via the AI agent

### AI Assistant
- Autonomous network agent powered by Claude (Anthropic) with a rich tool set:
  SSH commands, config push, golden config management, compliance checks, CI pipeline control, variable store read/write, backup, topology, SNMP/NetFlow queries, and more
- Auto-continue: the agent keeps running tool calls until the task is complete without user intervention
- Golden config baselines per device; drift detection compares running config against baseline
- Config-push workflow: backup → push → Jenkins CI → save golden → update variables (no human approval needed when CI passes)
- Human-in-the-loop approval queue for potentially destructive actions
- File upload: attach configs, diffs, or any text file to the chat for context
- Background autonomous mode: processes events (Jenkins failures, SNMP traps, config drift) while the user is idle
- Configurable agent timing intervals (hot-reload, no restart needed)
- Chunked report generation (`report_begin` / `report_append` / `report_finish`) to handle large multi-device reports without hitting token limits
- All settings (API key, Jenkins, TFTP, NetBox) configurable via the UI Settings panel

### CI/CD Integration
- Jenkins pipeline creation, scheduling, triggering, and result polling
- Per-list pipeline registry with build history
- Event monitor fires AI investigation tasks on build failures
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
- SNMP v1/v2c trap receiver (UDP 1162) with ring buffer and AI-driven alert analysis
- SNMP OID polling (GET/WALK) and device summary (uptime, interfaces)
- NetFlow v5/v9 UDP collector (port 9996) with per-source traffic aggregates
- Syslog event monitoring

### Variables
- Persistent key-value network fact store (`variables.json`) per device list
- Auto-populated by regex extraction from running configs (no AI tokens needed for discovery)
- AI agent reads variables before every config push and updates them automatically after

### History & Audit
- Timestamped config backup with unified-diff comparison between any two backups
- Golden config baselines used by the AI for drift detection and compliance
- Agent activity log (last 100 background tasks) persisted across restarts

## Project Structure

```
Claude_NMAS/
├── app.py                          # Flask application — all routes and SocketIO handlers
├── requirements.txt                # Python dependencies
├── Jenkinsfile                     # Reference Jenkinsfile for CI pipeline
├── telnetlib.py                    # telnetlib shim (removed from Python 3.13+)
├── CLAUDE.md                       # Project instructions for Claude Code
├── modules/
│   ├── ai_assistant.py             # AI agent core: tool definitions, run_chat(), golden configs
│   ├── agent_runner.py             # Background autonomous agent daemon
│   ├── agent_timers.py             # Configurable agent timing intervals
│   ├── approval_queue.py           # Human-in-the-loop approval queue
│   ├── backups.py                  # Config backup retrieval and storage
│   ├── bulk_ops.py                 # Multi-device parallel operations
│   ├── collector_config.py         # SNMP/NetFlow/syslog collector IP settings
│   ├── commands.py                 # SSH command execution with prompt/timing routing
│   ├── config.py                   # Paths, constants, user settings
│   ├── configure.py                # Cisco IOS config generator (10 feature types) + Jenkins XML
│   ├── connection.py               # Netmiko SSH connection pool and ping worker
│   ├── device.py                   # Device CRUD, encryption, multi-list management
│   ├── drift_check.py              # Scheduled golden-config drift checker (no AI tokens)
│   ├── event_monitor.py            # Jenkins/drift/compliance event monitor
│   ├── jenkins_runner.py           # Jenkins CI pipeline integration
│   ├── netbox_client.py            # NetBox IPAM/DCIM sync (devices, IPs, tunnels, VRFs)
│   ├── netflow_collector.py        # NetFlow v5/v9 UDP collector
│   ├── quick_actions.py            # Quick action (command shortcut) persistence
│   ├── snmp_collector.py           # SNMP trap receiver and OID polling
│   ├── terminal.py                 # Live SSH terminal via Paramiko + SocketIO
│   ├── topology.py                 # CDP/OSPF/BGP/tunnel topology discovery
│   ├── utils.py                    # Shared utility helpers
│   └── variable_discovery.py       # Regex-based network fact extraction
├── templates/
│   ├── base.html                   # Base layout, navigation, and AI chat panel
│   ├── index.html                  # Device list, topology, monitoring, and settings
│   └── device.html                 # Per-device management page
├── static/
│   ├── css/                        # Bootstrap CSS
│   └── js/                         # Bootstrap and xterm.js
└── data/                           # Runtime data (auto-created on first run)
    ├── key.key                     # Fernet encryption key (auto-generated)
    ├── secret.key                  # Flask session secret (auto-generated)
    ├── device_lists.json           # Active list and list registry
    ├── provider_config.json        # Active AI provider selection
    ├── jenkins_checks.json         # Jenkins server connection settings
    ├── agent_activity.json         # Background agent task log
    ├── agent_timers.json           # Agent timing interval overrides
    ├── user_settings.json          # User preference overrides (TFTP IP, NetBox URL/token, etc.)
    └── lists/
        └── {slug}/                 # Per-list data directory
            ├── devices.csv         # Encrypted device inventory
            ├── backups/            # Config backup files + index
            ├── variables.json      # Network variable/fact store
            ├── golden_configs/     # Golden config baselines
            ├── approval_queue.json # Pending AI action approvals
            └── jenkins_pipelines.json
```

## Prerequisites

- Python 3.10+
- `pip install -r requirements.txt`
- Cisco IOS devices with SSH enabled (`ip ssh version 2`)
- Jenkins server (optional, for CI/CD pipeline features)
- SNMP-enabled devices pointing traps at this host (optional)
- NetBox instance (optional, for IPAM/DCIM sync)
- An Anthropic API key for the AI assistant features

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
- **Anthropic API key** — saved to `.env` and takes effect immediately without a restart
- **Jenkins** — server URL, username, API key, and webhook token
- **TFTP server IP** — used for bulk file transfer operations
- **NetBox** — instance URL and API token for IPAM/DCIM sync

Alternatively, create a `.env` file in the project root:
```
ANTHROPIC_API_KEY=sk-ant-...
```

The `data/` directory and all subdirectories are created automatically on first run. The Fernet encryption key (`data/key.key`) is auto-generated on first run — **back this up**, as losing it makes stored credentials unrecoverable.

## AI Assistant

The AI assistant uses Claude (Anthropic) with a large tool set that lets it act autonomously on your network:

- **Read-first**: checks golden configs and variable store before opening any SSH session
- **SSH execution**: run any IOS command on any device in the list
- **Config push workflow**: pre-change backup → push config → Jenkins CI → save golden config → update variables from golden config. CI pass = no human approval required.
- **Golden configs**: save a device's running config as a verified baseline; detect drift automatically
- **Variable store**: network facts (IPs, OSPF IDs, BGP AS numbers, etc.) persisted and reused across sessions
- **Jenkins CI**: trigger pipelines, wait for results, auto-diagnose failures, roll back if needed
- **Topology**: query CDP/OSPF/BGP/tunnel topology data
- **SNMP/NetFlow**: inspect trap history and flow data
- **File upload**: attach a config file, diff, or design doc to the chat for additional context
- **Chunked reports**: large multi-device reports are written in sections to avoid API token limits

The background agent mode processes events autonomously (Jenkins failures, SNMP traps, config drift) while the user is away, and pauses automatically when the user opens the chat.

Potentially destructive actions (updating a golden config, reverting a device) are routed through the **approval queue** — the agent proposes the action and the user approves or rejects it from the UI.

## NetBox Integration

The NetBox sync reads golden configs as the source of truth — no live SSH sessions needed:

1. Open **Settings** and enter your NetBox URL and API token.
2. Click **Sync to NetBox** in the NetBox panel on the dashboard.
3. Each device list is created as a region, site, and VRF in NetBox.
4. All devices, interfaces, IP addresses, VPN tunnels, and static routes are pushed automatically.
5. To clean up, click **Remove** in the NetBox panel — this deletes the list's region, site, VRF, and all associated records from NetBox.

## Security Notes

- All device passwords and enable secrets are encrypted at rest using Fernet symmetric encryption. The key lives at `data/key.key` — protect it.
- There is no built-in authentication system. The app is intended for use on a trusted management workstation or network segment. Do not expose port 5000 to untrusted networks.
- The `.env` file containing the Anthropic API key is excluded from version control via `.gitignore`.
- SSH connections use Paramiko/Netmiko with `AutoAddPolicy` for host keys — acceptable for a closed lab environment, but review before using on untrusted networks.

## Author

Dustin Marchak
