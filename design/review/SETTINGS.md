# Settings inventory (GUI usability review)

**252 keys.** Found by parsing `DEFAULTS` and `SCHEMA["properties"]` in `modules/settings_schema.py`
(AST, every declared key), placed on screen from `modules/settings_scope.py` (each key's scope and
group), `modules/settings_page.py` (`INTEGRATIONS`, `TABS`, `tab_of`), `modules/installation_settings.py`
(`CARDS`, `TABS`) and the v2 templates. "Read by" is a grep of each key as a quoted string over
`modules/`, `routes/`, `scripts/`, `app.py` and `templates/v2/`, excluding `tests/`, `docs/`, the
stale `mutants/` copies, comment lines, and the three declaring files (`settings_schema`,
`settings_scope`, `secrets_store`); the enclosing function comes from the AST. Keys read through an
f-string were traced by hand (`records_db:backend`, `identity:may`).

**Legend.** *Net ›* = Settings › (a network, Default included) › tab (`/v2/settings/network/<list>?tab=…`).
*Inst ›* = Settings › Installation › tab (`/v2/settings/installation?tab=…`). "—" = not on any screen.
"(constant)" = the key is held in a module constant and read through it. "(client keys)" = listed
in an integration client's key list, which the client reads generically. "+N" = N more readers.
Each generic network card (Net › Integrations / Network) offers inherit / its own / not applicable,
Save and, for integrations, Test.

| # | Key | Where on screen | Read by (module:function) | Type | Default | What it does |
|---|---|---|---|---|---|---|
| 1 | `settings_schema_version` | — | settings_schema:migrate | integer (1–) | `SCHEMA_VERSION` | Version of the settings file's layout, used by migration. |
| 2 | `flask_host` | Inst › Connections, Server card | config (constant) | string | `"0.0.0.0"` | Address the web server listens on; takes effect at restart. |
| 3 | `flask_port` | Inst › Connections, Server card | config (constant) | integer (1–65535) | `5000` | TCP port the web server listens on; takes effect at restart. |
| 4 | `auto_open_browser` | — | **nothing** | bool | `True` | Retired: whether starting the app opened a browser (now an environment variable). |
| 5 | `tftp_root` | — | **nothing** | string | `/srv/tftp` (Linux) | Retired: folder the old TFTP file routes served from. |
| 6 | `ai_enabled` | — | **nothing** | bool | `True` | Retired: switch for the removed first AI assistant. |
| 7 | `background_agent_enabled` | — | **nothing** | bool | `False` | Retired: switch for the removed background AI agent. |
| 8 | `anthropic_api_key` | Inst › AI, AI (hosted) card (Replace…) | ai/gateway:_api_key, ai/spend:hosted_on, ai/controls:_key_set | secret | `""` | The AI provider's API key (typed by an admin, never shown). |
| 9 | `person_label_key` | — (generated at start) | display_names (constant), display_names:_label_key, display_names:install_label_key | secret | `""` | Secret key used to hash people's names before they go to the AI. |
| 10 | `ai_hosted` | Inst › AI, AI (hosted) card (Allow / Turn off) | installation_settings:ai_allow, installation_settings:ai_off, ai/gateway:hosted_allowed | map | `{}` | The admin's recorded permission (who, when, why) to use hosted AI at all; empty = AI refused. |
| 11 | `ai_cap_usd_per_call` | — | **nothing** | number (0–) | `0.05` | Retiring: old per-call AI spend cap; each task now has its own cap. |
| 12 | `ai_cap_usd_per_day` | Inst › AI, AI (hosted) card | ai/gateway:day_cap | number or null (0–) | `1.50` | Most the installation may spend on AI per day (USD); null = no cap. |
| 13 | `ai_cap_day_boundary` | Inst › AI, AI (hosted) card | ai/calls:boundary | string | `"UTC"` | Time zone whose midnight resets the AI day cap. |
| 14 | `ai_background` | Inst › AI, background features (per network) | ai/background (constant), ai/background:switches | map | `{}` | Per network, which background AI features are on, their caps and who turned them on; also holds each network's own AI troubleshooting mode and per-incident cap. |
| 15 | `ai_troubleshoot_mode` | Inst › AI, AI troubleshooting card | history_sources (constant), troubleshoot_control:_set_mode, fixit/policy (constant) +1 | choice: manual/off | `"manual"` | Default AI troubleshooting mode for incidents: Manual (on a person's press) or Off. |
| 16 | `ai_cap_usd_per_incident` | Inst › AI, AI troubleshooting card | fixit/policy (constant), fixit/policy:_cap_of | number (0–) | `1.00` | Most one incident's AI troubleshooting may spend (USD). |
| 17 | `ai_read_account_ping_traceroute` | — (file only) | ai/router_reads (constant), ai/router_reads:ping_traceroute_on | bool | `False` | Let the read-only device account run ping and traceroute (adds privilege lines to devices). |
| 18 | `ai_device_reads_as` | Inst › AI, AI troubleshooting card | nsot/reads (constant), nsot/reads:ai_reads_as | choice: mercury/read_only | `"mercury"` | Which device account the AI's show commands log in as: Mercury's or the read-only one. |
| 19 | `ai_assistant_on` | Inst › AI, Assistant card | installation_settings:assistant_on | bool | `False` | Show the Assistant button and panel in the top bar. |
| 20 | `wf_read_first` | — | **nothing** | bool | `True` | Retired: told the removed assistant to read before changing. |
| 21 | `wf_auto_backup` | — | **nothing** | bool | `True` | Retired: told the removed assistant to back up first. |
| 22 | `wf_run_jenkins` | — | **nothing** | bool | `True` | Dead: told the removed assistant to run Jenkins. |
| 23 | `wf_save_golden` | — | **nothing** | bool | `True` | Dead: told the removed assistant to save a golden after CI. |
| 24 | `wf_update_vars` | — | **nothing** | bool | `True` | Retired: told the removed assistant to update variables. |
| 25 | `wf_require_approval` | — | **nothing** | bool | `False` | Retired: told the removed assistant to ask for approval. |
| 26 | `tftp_server_ip` | — | **nothing** | string | `""` | Retired: TFTP server address for the removed file routes. |
| 27 | `netbox_url` | Inst › Connections, NetBox card | netbox_client:get_netbox_config, netbox_client:_sync_list_to_netbox_impl, integrations/netbox (client keys) | string | `""` | Address of the central NetBox (source of truth). |
| 28 | `netbox_token` | Inst › Connections, NetBox card (Replace…) | netbox_client:get_netbox_config, readers/credential_health:netbox, integrations/netbox (client keys) +4 | secret | `""` | NetBox API token. |
| 29 | `netbox_auth_scheme` | Inst › Connections, NetBox card | netbox_client:get_netbox_config, netbox_client:test_connection, integrations/netbox (client keys) +2 | choice: Bearer/Token | `"Bearer"` | How the token is sent: Bearer (NetBox 4.x) or Token (older). |
| 30 | `netbox_verify_tls` | Inst › Connections, NetBox card | netbox_client:get_netbox_config, integrations/netbox (client keys) | bool | `True` | Check NetBox's TLS certificate. |
| 31 | `netbox_allow_writes` | Inst › Connections, NetBox card (Turn off only; turned on at a NetBox write's confirm) | netbox_client:get_netbox_config, netbox_guard:writes_allowed, installation_settings:_writes_state +4 | bool | `False` | Master switch: may Mercury write to NetBox at all. |
| 32 | `netbox_remove_on_list_delete` | — | **nothing** | bool | `False` | Dead: once deleted NetBox objects when a device list was deleted. |
| 33 | `prometheus_url` | Net › Integrations, Prometheus card | monitoring_coverage:expected, monitoring_coverage:_expected_columns, nsot/profile_propose (constant) +2 | string | `""` | Address of the network's Prometheus. |
| 34 | `prometheus_auth_mode` | Net › Integrations, Prometheus card | integrations/prometheus (client keys), integrations/prometheus:_auth_headers, integrations/prometheus:session | choice: none/basic/bearer | `"none"` | How Mercury logs in to Prometheus. |
| 35 | `prometheus_username` | Net › Integrations, Prometheus card | integrations/prometheus (client keys), integrations/prometheus:session | string (not validated) | `""` | Prometheus basic-auth username. |
| 36 | `prometheus_password` | Net › Integrations, Prometheus card | integrations/prometheus (client keys), integrations/prometheus:session | secret | `""` | Prometheus basic-auth password. |
| 37 | `prometheus_bearer_token` | Net › Integrations, Prometheus card | integrations/prometheus (client keys), integrations/prometheus:_auth_headers | secret | `""` | Prometheus bearer token. |
| 38 | `prometheus_verify_tls` | Net › Integrations, Prometheus card | integrations/prometheus (client keys) | bool | `True` | Check Prometheus's TLS certificate. |
| 39 | `prometheus_targets_dir` | Net › Integrations, Prometheus card | prometheus_targets:target_dir, integrations/prometheus (client keys) | string | `""` | Folder where Mercury writes Prometheus scrape-target files. |
| 40 | `grafana_url` | Net › Integrations, Grafana card | device_page:_grafana_url, device_page:fleet_monitoring, attention:dashboard_roles_source +1 | string | `""` | Address of the network's Grafana. |
| 41 | `grafana_token` | Net › Integrations, Grafana card | readers/credential_health:grafana, readers/credential_health:grafana_other_networks, integrations/grafana (client keys) +2 | secret | `""` | Grafana API token. |
| 42 | `grafana_token_expires` | Net › Integrations, Grafana card | attention (constant), readers/credential_health:grafana, readers/credential_health:grafana_other_networks +1 | string | `""` | Declared expiry date of the Grafana token (Grafana can't report it). |
| 43 | `grafana_embed_mode` | — | **nothing** (only listed in integrations/grafana's key list) | choice: link/iframe | `"link"` | Dead: whether Grafana was linked or embedded. |
| 44 | `grafana_verify_tls` | Net › Integrations, Grafana card | integrations/grafana (client keys) | bool | `True` | Check Grafana's TLS certificate. |
| 45 | `grafana_device_dashboard_uid` | Net › Integrations, Grafana dashboards card | device_page:device_dashboard_settings, attention (constant), readers/grafana_dashboards (constant) +1 | string | `""` | Grafana dashboard drawn on every device page's Monitoring tab. |
| 46 | `grafana_fleet_dashboard_uid` | Net › Integrations, Grafana dashboards card | device_page:fleet_dashboard_uid, attention (constant), readers/grafana_dashboards (constant) +1 | string | `""` | Grafana dashboard drawn on the fleet Monitoring page. |
| 47 | `grafana_history_datasource_uid` | Net › Integrations, Grafana dashboards card | history_query:coverage, panels:history_store | string | `""` | Grafana datasource holding long-term metrics (Thanos, Mimir) for long ranges. |
| 48 | `metrics_live_retention_days` | Net › Integrations, Grafana dashboards card | history_query:coverage, panels:live_seconds | integer (1–) | `90` | Days the live metrics store keeps data; longer ranges use the history datasource. |
| 49 | `grafana_device_variable` | Net › Integrations, Grafana dashboards card | device_page:device_dashboard_settings, integrations/grafana (client keys) | string | `"device"` | Name of the device variable in the device dashboard. |
| 50 | `grafana_device_variable_value` | Net › Integrations, Grafana dashboards card | device_page:device_dashboard_settings, integrations/grafana (client keys) | choice: hostname/address | `"hostname"` | What fills that variable: the device's hostname or address. |
| 51 | `loki_url` | Net › Integrations, Loki card | monitoring_coverage:expected, nsot/profile_propose (constant), integrations/loki (client keys) | string | `""` | Address of the network's Loki (syslog store). |
| 52 | `loki_auth_mode` | Net › Integrations, Loki card | integrations/loki (client keys), integrations/loki:_auth_headers, integrations/loki:session +1 | choice: none/basic/bearer | `"none"` | How Mercury logs in to Loki. |
| 53 | `loki_username` | Net › Integrations, Loki card | integrations/loki (client keys), integrations/loki:session | string (not validated) | `""` | Loki basic-auth username. |
| 54 | `loki_password` | Net › Integrations, Loki card | integrations/loki (client keys), integrations/loki:session | secret | `""` | Loki basic-auth password. |
| 55 | `loki_bearer_token` | Net › Integrations, Loki card | integrations/loki (client keys), integrations/loki:_auth_headers | secret | `""` | Loki bearer token. |
| 56 | `loki_verify_tls` | Net › Integrations, Loki card | integrations/loki (client keys) | bool | `True` | Check Loki's TLS certificate. |
| 57 | `loki_selector_template` | Net › Integrations, Loki card | integrations/loki (client keys) | string | `'{host="{ip}"}'` | Loki label selector that finds one device's logs. |
| 58 | `logs_retention_days` | Net › Integrations, Loki card | history_query:coverage, readers/logs_summary:_retention | integer (1–) | `90` | Days the network's Loki keeps logs; the Logs view uses it to explain gaps. |
| 59 | `oxidized_url` | — | **nothing** | string | `""` | Retired with Oxidized: its address. |
| 60 | `oxidized_username` | — | **nothing** | string (not validated) | `""` | Retired with Oxidized: login. |
| 61 | `oxidized_password` | — | **nothing** | secret | `""` | Retired with Oxidized: password. |
| 62 | `oxidized_node_identity` | — | **nothing** | choice: hostname/ip | `"hostname"` | Retired with Oxidized: how nodes were named. |
| 63 | `oxidized_verify_tls` | — | **nothing** | bool | `True` | Retired with Oxidized: TLS check. |
| 64 | `kea_url` | Net › Integrations, Kea card | integrations/kea (client keys) | string | `""` | Address of the network's Kea DHCP Control Agent. |
| 65 | `kea_username` | Net › Integrations, Kea card | integrations/kea (client keys), integrations/kea:command | string (not validated) | `""` | Kea Control Agent username. |
| 66 | `kea_password` | Net › Integrations, Kea card | integrations/kea (client keys), integrations/kea:command | secret | `""` | Kea Control Agent password. |
| 67 | `kea_services` | Net › Integrations, Kea card (as a JSON field) | integrations/kea (client keys), integrations/kea:command | list | `["dhcp4"]` | Which Kea services to talk to: dhcp4, dhcp6. |
| 68 | `kea_verify_tls` | Net › Integrations, Kea card | integrations/kea (client keys) | bool | `True` | Check Kea's TLS certificate. |
| 69 | `proxmox_url` | Inst › Connections, Proxmox card | readers/credential_health:tls, integrations/proxmox (client keys), integrations/proxmox:missing_settings | string | `""` | Address of the Proxmox hypervisor (backup and snapshot checks). |
| 70 | `proxmox_node` | Inst › Connections, Proxmox card | integrations/proxmox (client keys), integrations/proxmox:node, integrations/proxmox:missing_settings | string | `""` | Proxmox node name. |
| 71 | `proxmox_token_id` | Inst › Connections, Proxmox card (Replace…) | integrations/proxmox (client keys), integrations/proxmox:missing_settings, integrations/proxmox:_auth_headers | string | `""` | Proxmox API token id (replaced together with its secret). |
| 72 | `proxmox_token_secret` | Inst › Connections, Proxmox card (Replace…) | integrations/proxmox (client keys), integrations/proxmox:missing_settings, integrations/proxmox:_auth_headers | secret | `""` | Proxmox API token secret. |
| 73 | `proxmox_token_expires` | Inst › Connections, Proxmox card | attention (constant), readers/credential_health:proxmox, integrations/proxmox (client keys) | string | `""` | Declared expiry of the Proxmox token. |
| 74 | `proxmox_backup_storage` | Inst › Connections, Proxmox card | integrations/proxmox (client keys), integrations/proxmox:storage, integrations/proxmox:missing_settings | string | `""` | Proxmox storage that holds the backups Mercury checks. |
| 75 | `proxmox_backup_vmids` | Inst › Connections, Proxmox card | integrations/proxmox (client keys), integrations/proxmox:vmids, integrations/proxmox:missing_settings | string (pattern) | `""` | VM ids whose backups Mercury checks. |
| 76 | `proxmox_verify_tls` | Inst › Connections, Proxmox card | integrations/proxmox (client keys) | bool | `True` | Check Proxmox's TLS certificate. |
| 77 | `topology_service_url` | — | **nothing** | string | `""` | Retired topology service: address. |
| 78 | `topology_service_type` | — | **nothing** | choice: json/svg/iframe | `"json"` | Retired topology service: format. |
| 79 | `topology_service_token` | — | **nothing** | secret | `""` | Retired topology service: token. |
| 80 | `topology_service_verify_tls` | — | **nothing** | bool | `True` | Retired topology service: TLS check. |
| 81 | `nsot_git_repo_path` | — | **nothing** (only listed in integrations/nsot_git's key list) | string | `""` | Dead: old single config-repo path (each network now has its own). |
| 82 | `nsot_git_remote_url` | — | **nothing** (only listed in integrations/nsot_git's key list) | string | `""` | Dead: old config-repo remote (now per network on History › Remote set-up). |
| 83 | `nsot_git_branch` | — | **nothing** (only listed in integrations/nsot_git's key list) | string | `"main"` | Dead: old config-repo branch. |
| 84 | `nsot_git_author_name` | Inst › Connections, Commit author card | nsot/repo:_git_env, integrations/nsot_git (client keys) | string | `"NMAS"` | Author name on every commit Mercury makes. |
| 85 | `nsot_git_author_email` | Inst › Connections, Commit author card | nsot/repo:_git_env, integrations/nsot_git (client keys) | string | `"nmas@localhost"` | Author email on every commit Mercury makes. |
| 86 | `nsot_git_auto_push` | — | **nothing** (only listed in integrations/nsot_git's key list) | bool | `False` | Dead: old auto-push switch. |
| 87 | `nsot_git_auth_mode` | — | **nothing** (only listed in integrations/nsot_git's key list) | choice: ssh_key/token | `"ssh_key"` | Dead: old push auth mode. |
| 88 | `nsot_git_token` | — | **nothing** (only listed in integrations/nsot_git's key list) | secret | `""` | Dead: old push token. |
| 89 | `cf_access_team_domain` | Inst › Access and identity (read-only; Record this decision) | identity (constant), identity:certs_url, identity:_identify_access +1 | string | `""` | Cloudflare Access team domain whose sign-ins Mercury trusts. |
| 90 | `cf_access_aud` | Inst › Access and identity (read-only; Record this decision) | identity (constant), identity:_identify_access, identity:posture | string | `""` | Cloudflare Access application audience tag. |
| 91 | `cf_access_trusted_peers` | Inst › Access and identity (read-only; Record this decision) | identity:trusted_peers, identity (constant) | string | `""` | Proxy addresses allowed to hand Mercury a sign-in assertion. |
| 92 | `cf_access_jwks_ttl` | Inst › Access and identity (read-only, "Key cache") | identity:jwks_ttl | integer (300–86400) | `3600` | How long Cloudflare's signing keys are cached (seconds). |
| 93 | `allowed_host_names` | — (laptop kit writes it) | request_origin:allowed_hosts | string | `""` | Host names a request may use (DNS-rebinding guard); blank checks none. |
| 94 | `require_same_origin_writes` | — (file only) | request_origin:same_origin_required | bool | `False` | Refuse writes that don't come from Mercury's own pages. |
| 95 | `local_account_enabled` | Inst › Access and identity, Local account card (state shown; set on the host) | local_account (constant), local_account:state | bool | `False` | Allow the one local (non-proxy) account to sign in, loopback only. |
| 96 | `installation_kind` | — (kit init writes it) | installation_kind:kind | choice: host/laptop_kit | `"host"` | Server install or laptop kit; a kit hides server-only checks. |
| 97 | `cf_access_service_labels` | Inst › Access and identity (read-only) | installation_settings:access_view, identity:service_label | map | `{}` | Friendly names for Cloudflare service tokens. |
| 98 | `credential_rotation_policies` | Credentials › Profiles, Rotation policy… | nsot/scheduled_rotation (constant), nsot/scheduled_rotation:policies | map | `{}` | Per credential profile, the scheduled password rotation (how often, window, batch size). |
| 99 | `no_change_windows` | — to set (shown on Credentials › Profiles) | change_windows (constant), change_windows:windows | list | `[]` | Daily times when no scheduled change may start (e.g. a backup window). |
| 100 | `heal_stopped` | Net › Self-healing, Stop / Resume self-healing everywhere… | heal/guards:g1_kill_switch, heal/policy (constant), heal/policy:stopped +1 | bool | `False` | Kill switch: stop self-healing on every network. |
| 101 | `require_identity_for_reveal` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a verified sign-in to reveal a secret. |
| 102 | `require_identity_for_approve` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a verified sign-in to approve. |
| 103 | `require_identity_for_confirm` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a verified sign-in to confirm a change. |
| 104 | `require_identity_for_publish_remote` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a verified sign-in to publish to a git remote. |
| 105 | `require_identity_for_configure` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a verified sign-in to change settings. |
| 106 | `require_identity_for_break_glass` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a verified sign-in for break-glass actions. |
| 107 | `require_person_for_reveal` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a person (not a service token) to reveal a secret. |
| 108 | `require_person_for_approve` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a person to approve. |
| 109 | `require_person_for_confirm` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a person to confirm a change. |
| 110 | `require_person_for_publish_remote` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a person to publish to a git remote. |
| 111 | `require_person_for_configure` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a person to change settings. |
| 112 | `require_person_for_break_glass` | Inst › Access and identity (read-only; Record this decision) | identity:may (f-string) | bool | `True` | Require a person for break-glass actions. |
| 113 | `service_allowed_operations` | Inst › Access and identity (read-only; Record this decision) | installation_settings:access_view, identity:service_may, identity:posture | list | `[]` | Which operations a service token (not a person) may run. |
| 114 | `access_rights` | — (named in Saved plans' text; C3597) | identity:holders | map | `{}` | Who holds the self-healing and admin approval rights; empty = every verified person. |
| 115 | `netbox_excluded_vrfs` | Net › Network, NetBox excluded VRFs card | netbox_client:excluded_vrfs | list | `[]` | VRFs whose addresses the NetBox import skips. |
| 116 | `settings_not_applicable` | — (host script) | job_health:settings_rows | map | `{}` | Guard settings declared deliberately unused on this host, with who and why. |
| 117 | `kea_ztp_fragment` | Net › Integrations, Kea card | job_health:ztp_responder_rows, dhcp_reservations:_ztp_fragment, nsot/ztp_responder:_fragment_paths +3 | string | `""` | Path of the Kea reservations file Mercury owns for ZTP. |
| 118 | `kea_dhcp4_config` | Net › Integrations, Kea card | dhcp_reservations (constant), nsot/ztp:kea_home | string | `"/etc/kea/kea-dhcp4.conf"` | Path of the kea-dhcp4 config that includes Mercury's file. |
| 119 | `kea_dhcp6_config` | Net › Integrations, Kea card | dhcp_reservations (constant) | string | `"/etc/kea/kea-dhcp6.conf"` | Path of the kea-dhcp6 config used to test IPv6 reservations. |
| 120 | `syslog_host` | Net › Integrations, Monitoring profile card | installation_kind (constant), nsot/onboard:syslog_baseline, nsot/profile_propose:connector_value +3 | string | `""` | Syslog collector onboarding gives every device; onboarding refuses while empty. |
| 121 | `syslog_trap_level` | Net › Integrations, Monitoring profile card | nsot/onboard:syslog_baseline, nsot/profile_propose:connector_value, integrations/monitoring_profile (client keys) | choice: syslog levels | `"notifications"` | Syslog severity devices send. |
| 122 | `syslog_origin_id` | Net › Integrations, Monitoring profile card | nsot/onboard:syslog_baseline, nsot/profile_propose:connector_value, integrations/monitoring_profile (client keys) | string | `"hostname"` | What devices stamp in each syslog line. |
| 123 | `syslog_source_interface` | Net › Integrations, Monitoring profile card | nsot/onboard:syslog_baseline, nsot/profile_propose:connector_value, integrations/monitoring_profile (client keys) | string | `"Loopback0"` | Interface syslog (and traps, TFTP, SSH client) leave from. |
| 124 | `syslog_heartbeat_seconds` | Net › Integrations, Monitoring profile card | heartbeat_windows:plan, readers/coverage_reporting:read, nsot/onboard:syslog_baseline +2 | integer (60–) | `300` | Interval of the device heartbeat message that proves logging works. |
| 125 | `ntp_servers` | Net › Integrations, Monitoring profile card | netbox_client:_parse_routing_context_from_config, monitoring_coverage:_expected_columns, nsot/profile_propose:section_value +7 | list | `[]` | NTP servers the monitoring profile gives devices. |
| 126 | `telemetry_receiver` | Net › Integrations, Monitoring profile card | monitoring_coverage:_expected_columns, ai/fixit_reads (constant), ai/router_reads (constant) +14 | string (pattern) | `""` | Telegraf model-driven telemetry listener (address:port). |
| 127 | `snmp_trap_host` | Net › Integrations, Monitoring profile card | redact (constant), nsot/profile_propose:connector_value, integrations/monitoring_profile (client keys) +1 | string | `""` | Where devices send SNMP traps. |
| 128 | `snmp_exporter_config` | Net › Integrations, Monitoring profile card | installation_kind (constant), nsot/profile_propose:connector_value, integrations/monitoring_profile (client keys) +2 | string | `""` | Path of snmp_exporter's config (the SNMP community is read from it). |
| 129 | `snmp_exporter_auth` | Net › Integrations, Monitoring profile card | nsot/profile_propose:connector_value, integrations/monitoring_profile (client keys), integrations/monitoring_profile:checks | string | `"public_v2"` | Which snmp_exporter auth module to use. |
| 130 | `oxidized_rest_url` | — | **nothing** | string | `""` | Dead: duplicate of the Oxidized address. |
| 131 | `oxidized_router_db` | — | **nothing** | string | `"/opt/oxidized/router.db"` | Retired with Oxidized: router.db path. |
| 132 | `yang_push_script` | — | installation_kind (constant), nsot/credential_rotation:consumer_report, nsot/credential_rotation:_yang_push_consumer | string | `""` | Path to a lab telemetry helper script (its script retired; declared not applicable on the host). |
| 133 | `s3_endpoint` | Net › Integrations, S3 archive card | integrations/s3_archive (client keys) | string | `""` | S3/MinIO archive address (old answers and alert history move here). |
| 134 | `s3_bucket` | Net › Integrations, S3 archive card | integrations/s3_archive (client keys), integrations/s3_archive:is_configured, integrations/s3_archive:bucket | string | `""` | S3 bucket name. |
| 135 | `s3_access_key` | Net › Integrations, S3 archive card | integrations/s3_archive (client keys), integrations/s3_archive:client | secret | `""` | S3 access key. |
| 136 | `s3_secret_key` | Net › Integrations, S3 archive card | integrations/s3_archive (client keys), integrations/s3_archive:client | secret | `""` | S3 secret key. |
| 137 | `s3_region` | Net › Integrations, S3 archive card | integrations/s3_archive (client keys), integrations/s3_archive:client | string | `""` | S3 region. |
| 138 | `s3_prefix` | Net › Integrations, S3 archive card | integrations/s3_archive (client keys), integrations/s3_archive:key | string | `""` | Key prefix inside the bucket. |
| 139 | `s3_verify_tls` | Net › Integrations, S3 archive card | integrations/s3_archive (client keys) | bool | `True` | Check the S3 endpoint's TLS certificate. |
| 140 | `notify_smtp_host` | Inst › Notifications, Email relay card | notify_page:_relay, notify/relay:config | string | `""` | Email relay for notifications; empty = no email. |
| 141 | `notify_smtp_port` | Inst › Notifications, Email relay card | notify/relay:config | integer (1–65535) | `587` | Email relay port. |
| 142 | `notify_smtp_tls` | Inst › Notifications, Email relay card | notify/relay:config | choice: starttls/implicit/none | `"starttls"` | Relay security; none only to a loopback relay. |
| 143 | `notify_smtp_username` | Inst › Notifications, Email relay card | notify/relay:config | string | `""` | Relay login; empty = no login. |
| 144 | `notify_smtp_from` | Inst › Notifications, Email relay card | notify/relay:config | string | `""` | Sender address on notification emails. |
| 145 | `notify_link_base` | Inst › Notifications, Email relay card | notify/message:link_url | string (pattern) | `""` | Mercury's public address, used to build links in messages. |
| 146 | `records_db_host` | Inst › Connections, Records database card | records_db:config, installation_settings:_typed, installation_settings:_records_drawn +1 | string | `""` | PostgreSQL host for Mercury's records; empty = keep records in files. |
| 147 | `records_db_port` | Inst › Connections, Records database card | records_db:config, installation_settings:_typed, installation_settings:_records_drawn +1 | integer (1–65535) | `5433` | Records database port. |
| 148 | `records_db_name` | Inst › Connections, Records database card | records_db:config, installation_settings:_typed, installation_settings:_records_drawn +1 | string | `"mercury"` | Records database name. |
| 149 | `records_db_user` | Inst › Connections, Records database card | records_db:config, installation_settings:_typed, installation_settings:_records_drawn +1 | string | `"mercury"` | Records database role. |
| 150 | `records_db_password` | Inst › Connections, Records database card (Replace…) | records_db:config, records_db:_resolve, routes/settings_v2:records_replace | secret | `""` | Records database password. |
| 151 | `records_store_receipts` | Inst › Connections, Record stores | records_db:backend (f-string), records_migrate (constant) | choice: file/postgres | `"file"` | Store for deploy receipts: files or the records DB. |
| 152 | `records_store_acknowledgements` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for Needs attention acknowledgements. |
| 153 | `records_store_restarts` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for device restarts seen. |
| 154 | `records_store_restart_windows` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for planned-restart windows. |
| 155 | `records_store_restart_window_ends` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for restart windows ended early. |
| 156 | `records_store_rotations` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for credential rotations and saves. |
| 157 | `records_store_breakglass_exports` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for break-glass exports. |
| 158 | `records_store_breakglass_intact` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for break-glass intact checks. |
| 159 | `records_store_breakglass_checks` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for break-glass checks. |
| 160 | `records_store_breakglass_drills` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for break-glass drills. |
| 161 | `records_store_reveals` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for the secret-reveal record. |
| 162 | `records_store_host_steps_done` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for host steps said done. |
| 163 | `records_store_heartbeat_rules` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for heartbeat-window re-measures. |
| 164 | `records_store_netbox_removals` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for NetBox removals. |
| 165 | `records_store_network_settings_record` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for each network's settings-change record. |
| 166 | `records_store_onboarding_runs` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for onboarding runs. |
| 167 | `records_store_inventory_edits` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for inventory edits. |
| 168 | `records_store_approval_queue` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for each network's approval queue. |
| 169 | `records_store_rollback_blocks` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for rollback blocks. |
| 170 | `records_store_retry_log` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for authorised retries. |
| 171 | `records_store_netbox_created` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for NetBox objects Mercury created. |
| 172 | `records_store_netbox_modified` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for NetBox objects Mercury modified. |
| 173 | `records_store_netbox_adopted` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for NetBox objects Mercury adopted. |
| 174 | `records_store_interrupted_holds` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for operations interrupted while holding a device. |
| 175 | `records_store_reader_values` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for background readers' held values. |
| 176 | `records_store_ai_calls` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for the record of AI calls (the day cap sums it). |
| 177 | `records_store_evidence_packs` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for alerts' evidence packs. |
| 178 | `records_store_alert_history` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for alert state transitions. |
| 179 | `records_store_flow_intent` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for SDN flow intent. |
| 180 | `records_store_explain_answers` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for Explain's AI answers. |
| 181 | `records_store_alert_rule_changes` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for Grafana alert-rule changes. |
| 182 | `records_store_ai_feedback` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for "Was this right?" feedback. |
| 183 | `records_store_heal_steps` | Inst › Connections, Record stores | records_db:backend (f-string) | choice: file/postgres | `"file"` | Store for the self-healing step log. |
| 184 | `platform_map` | Inst › Platforms and roles | credential_profiles_page:exists, platform_maps:_maps, platform_maps:view +9 | map | (map: see schema) | Per platform: the device driver and config dialect Mercury uses. |
| 185 | `platform_default_netmiko_type` | Inst › Platforms and roles | platform_maps:_maps, platform_maps:apply, inventory/netbox_source:map_platform | string | `""` | Driver for a device whose platform isn't in the map (a guess). |
| 186 | `verify_settle_windows` | Net › Network, Verify settle windows card (JSON field) | nsot/convergence:window_for | map | (map: see schema) | Per protocol, how long verify waits for the network to settle after a change. |
| 187 | `deploy_max_workers` | Net › Network, Deploy workers card | nsot/deploy:max_workers | integer (1–16) | `1` | Devices a deploy changes at once. |
| 188 | `deploy_verify_failure_limit` | Net › Network, Deploy failure limit card | nsot/deploy:__init__ | integer (1–) | `2` | Failed devices after which a restore batch stops. |
| 189 | `nsot_device_tag_retention` | Net › Network, Golden tags kept card | nsot/repo:_prune_device_tags | integer (0–) | `50` | Golden-config tags kept per device before old ones are pruned. |
| 190 | `nsot_config_read_timeout` | Net › Network, Configuration read timeout card | config_read:read_timeout, pipeline:_capture_failure_state, pipeline:_rollback_readback +3 | integer (5–) | `120` | Seconds to wait for a device's running config. |
| 191 | `reads_answer_cap_kib` | Net › Network, Show commands: answer cap (KiB) card | nsot/reads:cap_bytes | integer (1–4096) | `32` | Largest show-command answer kept (KiB); longer ones are cut. |
| 192 | `reads_max_workers` | Net › Network, Show commands: devices read at once card | nsot/reads:max_workers | integer (1–16) | `6` | Devices Show commands reads at once. |
| 193 | `reads_retention_days` | Net › Network, Show commands: answers kept (days) card | nsot/reads:retention_days | integer (1–) | `30` | Days show-command answers stay before moving to the archive. |
| 194 | `alert_history_retention_days` | Net › Network, Alert history: transitions kept (days) card | alert_history:retention_days | integer (1–) | `90` | Days alert state changes are kept before moving to the archive. |
| 195 | `ai_topology_class` | Net › Network, AI: the topology class card | ai/egress_classes (constant) | bool | `True` | May AI calls about this network include its topology (devices, links)? |
| 196 | `ai_device_state_class` | Net › Network, What AI may send card | ai/egress_classes (constant) | bool | `False` | May AI calls about this network include show-command output? |
| 197 | `ai_device_state_on` | Net › Network, What AI may send card (Turn on… reason) | ai/egress_classes (constant) | map | `{}` | Who turned the device-state class on, when and why. |
| 198 | `endpoint_read_interval_minutes` | Net › Network, Endpoints card | readers/endpoints (constant) | integer (5–1440) | `15` | How often MAC, ARP and IPv6-neighbour tables are read. |
| 199 | `endpoint_stale_after_hours` | Net › Network, Endpoints card | endpoints (constant) | integer (1–) | `24` | Age after which an endpoint's last location is called stale. |
| 200 | `sdn_controllers` | Net › Integrations, SDN controllers card | attention (constant), attention:sdn_controllers_source, readers/sdn_controllers (constant) +1 | list | `[]` | The network's SDN controller connections. |
| 201 | `network_stage` | Net › Integrations, SDN controllers card (stage line) | sdn/modes (constant), sdn/modes:_stage_lock, sdn/modes:set_stage | choice: ''/lab/pilot/production | `""` | Lab, pilot or production; only lab allows SDN and heal AUTO. |
| 202 | `code_repository` | Net › Network, Code repository card | coderepo (constant), coderepo:set_location | string | `""` | Git repository holding the network's SDN apps and jobs. |
| 203 | `code_repository_branch` | Net › Network, Code repository card | coderepo (constant) | string | `""` | Branch of that repository to fetch. |
| 204 | `code_review` | Net › Network, Code repository card (Who may publish) | coderepo (constant), coderepo:set_review | choice: another_person/self_recorded | `"another_person"` | Who may publish an app version: another person, or its author (recorded). |
| 205 | `sdn_scan_ports` | SDN › Responses, Detection rules (shown, not editable) | sdn/detect (constant), sdn/detect:scan | integer (2–65535) | `20` | Distinct ports one source must hit to count as a scan. |
| 206 | `sdn_scan_window_seconds` | SDN › Responses, Detection rules (shown, not editable) | sdn/incidents (constant), sdn/detect (constant), sdn/detect:scan | integer (1–3600) | `60` | Window for counting a scan. |
| 207 | `sdn_scan_fallback_pps` | SDN › Responses, Detection rules (shown, not editable) | sdn/detect (constant), sdn/detect:scan | number (0–) | `100` | Packet rate that flags a scan where flows aren't L4. |
| 208 | `sdn_flood_factor` | SDN › Responses, Detection rules (shown, not editable) | sdn/detect (constant), sdn/detect:flood | number (1.5–1000) | `5` | Times a port's normal rate that counts as a flood. |
| 209 | `sdn_flood_window_seconds` | SDN › Responses, Detection rules (shown, not editable) | sdn/incidents (constant), sdn/detect (constant), sdn/detect:thresholds +2 | integer (0–3600) | `30` | How long the high rate must last. |
| 210 | `sdn_flood_max_mean_bytes` | SDN › Responses, Detection rules (shown, not editable) | sdn/detect (constant), sdn/detect:scan, sdn/detect:flood +1 | number (40–65535) | `200` | Mean packet size at or below which a high rate is a flood. |
| 211 | `sdn_response_hard_timeout_seconds` | SDN › Responses (shown; overridable per response) | sdn/flow_ops (constant), sdn/flow_ops:settings_of, sdn/closed_loop:request_blocks +1 | integer (1–) | `600` | Default lifetime of a flow installed in response to a threat. |
| 212 | `sdn_response_max_seconds` | SDN › Responses (shown) | sdn/flow_ops (constant), sdn/flow_ops:settings_of, sdn/flow_ops:_plan_add_flow +3 | integer (1–65535) | `3600` | Longest a response flow may live. |
| 213 | `sdn_escalate_after_minutes` | Net › Network, SDN: escalate an unanswered incident after (minutes) card | attention (constant) | integer (1–1440) | `15` | Minutes an SDN incident may wait for a person before it escalates. |
| 214 | `sdn_response_policy` | SDN › Responses, Response policy | sdn/closed_loop (constant), sdn/closed_loop:_policy_lock, sdn/closed_loop:save_policy | map | (map: see schema) | Per detection rule, which responses are allowed (first = default). |
| 215 | `heal_mode` | Net › Self-healing (mode) | heal/guards:g2_mode, heal/policy (constant) | choice: off/dry_run/auto | `"off"` | Self-healing mode for the network: off, dry run, or auto. |
| 216 | `heal_mode_until` | Net › Self-healing (mode's expiry) | heal/policy (constant) | string (pattern) | `""` | When auto mode ends (then dry run). |
| 217 | `heal_policy_confirmed` | Net › Self-healing (written by each confirm; display unverified) | heal/policy (constant) | map | `{}` | Who confirmed the heal policy in force, when, why, and its fingerprint. |
| 218 | `heal_kinds_auto` | Net › Self-healing (fix kinds) | heal_page (constant), heal/policy (constant) | list | `[]` | Fix kinds auto mode may apply without asking. |
| 219 | `heal_kinds_propose` | Net › Self-healing (fix kinds) | heal_page (constant), heal/policy (constant) | list | (list: see schema) | Fix kinds proposed for a person to approve. |
| 220 | `heal_topology_hold_minutes` | — | heal/hold (constant), heal/policy (constant) | integer (0–10080) | `240` | Hold healing after a recent change. policy.GUARDS says guard 5 holds nothing since 2026-11-16 (unverified end to end). |
| 221 | `heal_max_devices_drifting` | — | heal/decide:_decide_one, heal/decide:guard_holds, heal/decide:script_hold +2 | integer (1–) | `3` | More devices drifting at once than this escalates. **Still in force** (guard 6, heal/decide) but its row was removed from the Self-healing tab as "retired" (heal_page.GUARD_ROWS). |
| 222 | `heal_person_working_changes` | — | heal/bounce:decide, heal/policy (constant) | integer (1–) | `3` | Changes outside intent that mean a person is working. Guard 7 holds nothing, but heal/bounce:decide still reads it; not on screen. |
| 223 | `heal_person_working_minutes` | — | heal/bounce:decide, heal/policy (constant) | integer (1–1440) | `10` | Window for that count. Same as the row above. |
| 224 | `heal_grace_seconds` | — | heal/decide:_decide_one, heal/decide:guard_holds, heal/decide:script_hold +2 | integer (60–86400) | `900` | How long a deviation must persist. Guard 8 holds nothing, but it is **still guard 6's window** and read by heal/detect:run; not on screen. |
| 225 | `heal_max_per_device_hour` | — | heal/policy (constant) | integer (0–) | `1` | Heals per device per hour. Read, but guard 9 holds nothing (heal/guards.py). |
| 226 | `heal_max_per_network_hour` | — | heal/policy (constant) | integer (0–) | `6` | Heals per network per hour. Read, but guard 10 holds nothing. |
| 227 | `heal_repeat_halts_hours` | Net › Self-healing (stops table) | heal_page (constant), heal/bounce:decide, heal/actions (constant) +3 | integer (1–720) | `24` | Repeat window: a second bounce need inside it becomes a dampening proposal. |
| 228 | `heal_max_removed_units` | — | heal/policy (constant) | integer (0–1) | `1` | Removal units one heal may carry. Read, but guard 12 holds nothing. |
| 229 | `heal_max_units` | — | heal/policy (constant) | integer (0–1) | `1` | Config sections one heal may carry. Read, but guard 12 holds nothing. |
| 230 | `heal_flap_transitions` | Net › Self-healing (stops table) | heal_page (constant), heal/bounce:decide, heal/actions (constant) +1 | integer (2–100) | `3` | Up/down transitions that make an interface flapping. |
| 231 | `heal_flap_minutes` | Net › Self-healing (stops table) | heal_notice:_cleared, heal_page (constant), heal/bounce:decide +3 | integer (1–60) | `10` | Window for counting a flap (also the stability window). |
| 232 | `heal_bounce_per_port_hour` | Net › Self-healing (stops table) | heal_page (constant), heal/bounce:decide, heal/actions (constant) +3 | integer (0–1) | `1` | Port bounces allowed per port per hour. |
| 233 | `heal_security_revert_adjacency` | — (no control yet, C2868) | heal/policy (constant) | bool | `False` | May a heal undo a one-sided security change that broke an adjacency? |
| 234 | `heal_recurrence_count` | Net › Self-healing (stops table) | attention:_heal_finding_rows, heal_page (constant), heal/findings:settings +1 | integer (2–100) | `3` | Times a problem may return before it is a finding. |
| 235 | `heal_recurrence_hours` | Net › Self-healing (stops table) | attention:_heal_finding_rows, heal_page (constant), heal/findings:settings +3 | integer (1–720) | `24` | Window for recurrence and fight counts. |
| 236 | `heal_fight_count` | Net › Self-healing (stops table) | attention:_heal_finding_rows, heal_page (constant), heal/findings:settings +3 | integer (2–100) | `3` | Times a fix may be undone before it is a fight. |
| 237 | `heal_fight_minutes` | Net › Self-healing (stops table) | attention:_heal_finding_rows, heal_page (constant), heal/findings:settings +3 | integer (1–1440) | `10` | A fix undone within this many minutes counts toward a fight. |
| 238 | `heal_fight_stop` | — | attention:_heal_finding_rows, heal/findings:settings, heal/findings:notify_fights +1 | bool | `False` | Stop fixing on a fight. Retired: guard 11 holds nothing (heal/policy.GUARD_WORDS). |
| 239 | `heal_auto_default_hours` | Net › Network, Self-healing: Auto lasts (hours) card | heal/batch:default_hours | choice: 1/8 | `1` | How long one-press Auto lasts (1 or 8 hours). |
| 240 | `heal_notify_team` | Net › Self-healing, Who is told card | heal_notify (constant) | string (pattern) | `""` | Team told about this network's self-healing. |
| 241 | `heal_notify_events` | Net › Self-healing, Who is told card | heal_notify (constant) | list | (list: see schema) | Which heal events tell that team. |
| 242 | `jenkins_step_shell` | — | **nothing** | choice: bat/sh | `"bat"` | Dead: Jenkins step shell. |
| 243 | `collector_trap_enabled` | — | **nothing** | bool | `True` | Retired: trap receiver switch. |
| 244 | `collector_netflow_enabled` | — | **nothing** | bool | `True` | Retired: NetFlow collector switch. |
| 245 | `collector_syslog_enabled` | — | **nothing** | bool | `True` | Retired: syslog collector switch. |
| 246 | `monitoring_identity_mode` | — | **nothing** | choice: ip/hostname/netbox_custom_field | `"ip"` | Retired: how monitoring identified a device. |
| 247 | `monitoring_identity_field` | — | **nothing** | string | `""` | Retired: NetBox field for that identity. |
| 248 | `monitoring_prom_label` | — | **nothing** | string | `"instance"` | Retired: Prometheus label for a device. |
| 249 | `monitoring_strip_port` | — | **nothing** | bool | `True` | Retired: strip the port from targets. |
| 250 | `promql_device_up` | — | **nothing** | string | `'up{{{label}="{target}"}}'` | Retired: PromQL for device up. |
| 251 | `promql_cpu` | — | **nothing** | string | `""` | Retired: PromQL for CPU. |
| 252 | `promql_interface_oper` | — | **nothing** | string | `""` | Retired: PromQL for interface state. |

## Counts

| | Keys |
|---|---|
| On a screen and editable | 162 (of them: Net › generic cards 65; Inst › cards 39; Record stores 33, set only by Move…) |
| Shown on a screen, not editable there | 27 (Access and identity's read-only keys, the Local account state, SDN › Responses' thresholds and timeouts) |
| Not on any screen, but read | 21 (host files, kit init, generated keys, and 11 heal keys not drawn on the Self-healing tab) |
| Read by nothing | 42 |
| **Total** | **252** |

Counted with awk over this table's "Where" and "Read by" columns. "Editable" includes keys set only
by a dedicated control (Replace…, Move…, Turn on…, Allow).

## Duplicates: two keys doing one job, or one job set in two places

1. **Four switches decide whether AI runs:** `ai_hosted` (Allow / Turn off), `ai_background` (per
   network and feature), `ai_troubleshoot_mode` (Off), `ai_assistant_on`. Three sit on Inst › AI;
   there is no single "AI is on / off" readout. The retiring `ai_enabled` is a fifth, read by nothing.
2. **AI troubleshooting's mode and per-incident cap are set in two places:** the installation's
   `ai_troubleshoot_mode` / `ai_cap_usd_per_incident` (AI troubleshooting card), and each network's
   own `mode` / `incident_cap_usd` stored inside `ai_background[network]["fixit_auto"]`
   (docs/SETTINGS.md, Gate 2), set from the same AI tab and the control strip.
3. **How long Auto self-healing lasts is set in two places:** `heal_mode_until` (Self-healing tab,
   quick choices 1 h to 7 days) and `heal_auto_default_hours` (Net › Network card, one-press Auto,
   1 or 8 h). Same job, two tabs.
4. **AI spend caps:** `ai_cap_usd_per_call` (retiring) beside the per-task caps in
   `modules/ai/profiles.py`; the installation day cap `ai_cap_usd_per_day` beside each background
   feature's day and month caps inside `ai_background`.
5. **Heal stops replaced but kept:** `heal_max_per_device_hour` / `heal_max_per_network_hour` were
   replaced by `heal_recurrence_count` / `heal_recurrence_hours`; `heal_repeat_halts_hours` and
   `heal_recurrence_hours` are both "within N hours" windows; `heal_fight_stop` is retired beside
   `heal_fight_count` / `heal_fight_minutes`.
6. **How a device is named to an outside tool, four shapes:** `grafana_device_variable_value`
   (hostname/address), `loki_selector_template` (`{host="{ip}"}`), and the retired
   `monitoring_identity_mode` and `oxidized_node_identity`.
7. **`syslog_source_interface` does two jobs:** the syslog source, and the management source for
   traps, TFTP and the SSH client (docs/SETTINGS.md, monitoring profile).
8. **`network_stage` is set on Net › Integrations (SDN controllers card) but gates heal AUTO too**,
   which is set on Net › Self-healing: one fact, set away from one of the two places it matters.
9. **`netbox_allow_writes`:** turned off on Inst › Connections, turned on only inside a NetBox
   write's confirm (Source of truth › NetBox): one switch, two places.
10. **Identity gates come in pairs:** `require_identity_for_<action>` and
    `require_person_for_<action>` for six actions (12 keys); a person is always also an identity.
11. **Dead duplicates:** `oxidized_rest_url` = `oxidized_url`; `nsot_git_remote_url` (dead) vs
    each network's remote on History › Remote set-up.
12. **Per-response vs default timeout:** `sdn_response_hard_timeout_seconds` (default, file only)
    and the hard-timeout field in each response's preview on SDN › Responses.

## Keys read by nothing (42)

Grep found no reader outside the schema, `settings_scope`, `secrets_store`, docs and tests. All are
scoped `retiring` or `dead` in `modules/settings_scope.py`, so the code already knows.

- **Retired features:** `auto_open_browser`, `tftp_root`, `tftp_server_ip`, `ai_enabled`,
  `background_agent_enabled`, `ai_cap_usd_per_call`.
- **Old assistant workflow:** `wf_read_first`, `wf_auto_backup`, `wf_run_jenkins`,
  `wf_save_golden`, `wf_update_vars`, `wf_require_approval`, `jenkins_step_shell`.
- **Oxidized (7):** `oxidized_url`, `oxidized_username`, `oxidized_password`,
  `oxidized_node_identity`, `oxidized_verify_tls`, `oxidized_rest_url`, `oxidized_router_db`.
- **Topology service (4):** `topology_service_url`, `topology_service_type`,
  `topology_service_token`, `topology_service_verify_tls`.
- **Old single git repo (6), listed only in `integrations/nsot_git`'s key list:**
  `nsot_git_repo_path`, `nsot_git_remote_url`, `nsot_git_branch`, `nsot_git_auto_push`,
  `nsot_git_auth_mode`, `nsot_git_token`.
- **Others:** `grafana_embed_mode` (listed only in `integrations/grafana`'s key list),
  `netbox_remove_on_list_delete`.
- **Old Settings modal's monitoring form (10):** `collector_trap_enabled`,
  `collector_netflow_enabled`, `collector_syslog_enabled`, `monitoring_identity_mode`,
  `monitoring_identity_field`, `monitoring_prom_label`, `monitoring_strip_port`,
  `promql_device_up`, `promql_cpu`, `promql_interface_oper`.

**Read but changing nothing (so in effect unused):** `heal_max_per_device_hour`,
`heal_max_per_network_hour`, `heal_max_removed_units`, `heal_max_units`, `heal_fight_stop` (their
guards return None in `modules/heal/guards.py`); `heal_topology_hold_minutes` (guard 5, said to hold
nothing by `heal/policy.GUARDS`; unverified end to end).

## Other findings for the review

- **In force but hidden:** `heal_max_devices_drifting` and `heal_grace_seconds` still drive guard 6
  (`modules/heal/decide.py`), but the Self-healing tab dropped their rows as retired
  (`modules/heal_page.py` `GUARD_ROWS`). A person can't see or change a limit that still escalates
  heals.
- **The docs and the code disagree:** docs/SETTINGS.md lists `reads_*`, `deploy_*`,
  `nsot_config_read_timeout`, `nsot_device_tag_retention`, `alert_history_retention_days`,
  `ai_topology_class`, `kea_services`, `verify_settle_windows` and the Endpoints keys as file-only
  or "no form yet". The code draws every non-cardless network group as a generic card
  (`settings_scope.network_groups`, `settings_page.tab_groups`), so each one is on Net › Network or
  Integrations (lists and maps as a raw JSON field).
- **Settings kept outside the schema, also on Settings screens:** display names
  (`display_names.json`), each person's time zone (`time_zones.json`), the drift-check interval
  (`modules/drift_interval`), notification teams and webhooks (`modules/notify`), credential
  profiles. A shared settings component needs to cover these stores as well.
- **Types the schema doesn't validate:** `prometheus_username`, `loki_username`, `kea_username` and
  `oxidized_username` have no schema property.
