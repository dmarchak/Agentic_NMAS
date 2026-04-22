# CLAUDE.md — Agentic Network Management and Automation (NMAS)

## Project Overview

Flask-based web application for managing, automating, and monitoring Cisco IOS network devices. Built by Dustin Marchak as a capstone/school project. The app is a single-host management tool — not a multi-tenant SaaS — so there is no built-in auth system.

**Stack:** Python 3.10+, Flask, Flask-SocketIO, Netmiko/Paramiko (SSH), Anthropic Claude API (AI agent), vis.js (topology), Bootstrap 5, Jenkins CI integration.

## What We've Built Together

### Core modules
- **[app.py](app.py)** (~4600 lines) — all Flask routes and SocketIO handlers
- **[modules/ai_assistant.py](modules/ai_assistant.py)** (~6000 lines) — AI agent core: tool definitions, `run_chat()`, golden config management, read-first workflow
- **[modules/agent_runner.py](modules/agent_runner.py)** (~1350 lines) — background autonomous agent daemon; pauses when user opens chat
- **[modules/topology.py](modules/topology.py)** (~1080 lines) — CDP/OSPF/BGP/DMVPN tunnel discovery; vis.js graph with hub/spoke labels
- **[modules/jenkins_runner.py](modules/jenkins_runner.py)** (~1160 lines) — Jenkins pipeline create/trigger/poll/diagnose
- **[modules/snmp_collector.py](modules/snmp_collector.py)** (~760 lines) — SNMP v1/v2c trap receiver + OID polling
- **[modules/variable_discovery.py](modules/variable_discovery.py)** (~256 lines) — regex-based network fact extraction (no AI tokens)

### New modules (untracked, in progress)
- **[modules/configure.py](modules/configure.py)** (~1018 lines) — Cisco IOS config generator for 10 feature types; also generates Python Jenkins verification scripts and pipeline XML; manages per-job metadata so CI success callback can create golden-config approval
- **[modules/drift_check.py](modules/drift_check.py)** — standalone Python drift checker (no Claude API needed); runs on schedule, SSHes devices, diffs against golden config, routes findings to approval queue
- **[modules/netbox_client.py](modules/netbox_client.py)** (~1420 lines) — NetBox IPAM/DCIM sync; maps device lists → NetBox regions/sites; syncs device records (model, serial, platform, SW version) via SSH `show version`/`show inventory`

## Key Architecture Decisions

- **Data storage:** `data/lists/{slug}/` per device list — devices.csv (Fernet-encrypted creds), variables.json, golden_configs/, backups/, approval_queue.json, jenkins_pipelines.json
- **AI read-first:** agent checks golden configs and variables before opening any SSH session
- **Config push workflow:** backup → push → Jenkins CI → save golden → update variables. CI pass = auto-approve, no human needed.
- **Approval queue:** destructive AI actions (golden config update, revert) go through `approval_queue.py` for human review
- **Connection pool:** Netmiko SSH connections reused via pool in `modules/connection.py`; background ping worker tracks online/offline
- **Auto-continue:** AI agent loops tool calls until task complete without user intervention
- **telnetlib shim:** `telnetlib.py` in root — needed because Python 3.13 removed telnetlib from stdlib

## Running the App

```bash
pip install -r requirements.txt
python app.py
# Opens http://127.0.0.1:5000 automatically
```

Settings (API key, Jenkins, TFTP) are all configurable from the UI Settings panel — no restart needed.

## Recent Work (as of April 2026)

Last few commits:
- Restored auto browser launch on startup
- Added AI read-first workflow, file upload, settings UI, banner cleanup
- Fixed tunnel topology: DMVPN/mGRE detection, `nhrp_hub` field, hub/spoke role labels
- Added `jenkins_delete_failed_builds` tool to AI schema
- Fixed dead-socket retry on SSH execute
- Fixed Jenkins CI network-full-verification pipeline (CDATA, curl patterns, Windows bat steps)

Currently uncommitted changes span nearly every module — likely mid-feature work on configure.py, drift_check.py, and netbox_client.py integration.

## File Naming / Conventions

- All routes in `app.py` (monolithic by design)
- Module files in `modules/` are imported by app.py
- Templates: `base.html` (layout + AI chat panel), `index.html` (main dashboard), `device.html` (per-device page)
- JSON data files in `data/` are auto-created on first run
- Fernet key at `data/key.key` — back it up; losing it makes stored creds unrecoverable
- `.env` holds `ANTHROPIC_API_KEY`; excluded from git

## Things to Keep in Mind

- Windows development environment (bash shell, but running on Windows 11)
- Jenkins pipeline uses `bat` steps (not `sh`) because Windows
- `telnetlib.py` shim must stay in root for Python 3.13+ compat
- No test suite currently (pytest.ini was removed)
- App is intended for a trusted lab/management network — no auth layer
