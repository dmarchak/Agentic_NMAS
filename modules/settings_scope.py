"""Which settings belong to a NETWORK and which to the host (P.8, step 1; NSOT_P8_DESIGN).

The operator decided P.8 on 2026-10-04: two lists are two networks, the global settings file is
the Default network's layer (no migration), and an integration inherits as a GROUP, never key
by key, so a list that sets its own Grafana URL never sends Default's token to it. This table is
the one declaration of each key's scope and group, read by the resolver P.8 builds next; this
step changes no behaviour.

Scopes:
- ``network``: the key belongs to one network (a list); its *group* inherits together.
- ``host``: one installation-wide value (identity, the web server, NetBox's connection, the
  platform and role maps, Proxmox).
- ``retiring``: read by nothing at run time; decided 2026-10-04 to retire after checking
  nothing outside the app reads it, each retirement recorded in CUTOVER (P.8 decision 3);
  Oxidized's keys joined them when Oxidized retired (Phase 3, P3-3).
- ``dead``: already read by nothing and recorded as such (C171, C155, P.4); never split.

`tests/test_settings_scope.py` holds every declared setting to exactly one row here.
"""

NETWORK, HOST, RETIRING, DEAD = "network", "host", "retiring", "dead"


def _group(scope: str, group: str, *keys) -> dict:
    return {k: (scope, group) for k in keys}


SCOPES: dict = {
    # ── Per network: integrations, each one group ───────────────────────────────────────
    **_group(NETWORK, "grafana", "grafana_url", "grafana_token", "grafana_token_expires",
             "grafana_verify_tls"),
    **_group(NETWORK, "grafana_roles", "grafana_fleet_dashboard_uid",
             "grafana_device_dashboard_uid", "grafana_device_variable",
             "grafana_device_variable_value", "grafana_history_datasource_uid",
             "metrics_live_retention_days"),
    **_group(NETWORK, "prometheus", "prometheus_url", "prometheus_auth_mode",
             "prometheus_username", "prometheus_password", "prometheus_bearer_token",
             "prometheus_verify_tls", "prometheus_targets_dir"),
    **_group(NETWORK, "loki", "loki_url", "loki_auth_mode", "loki_username", "loki_password",
             "loki_bearer_token", "loki_verify_tls", "loki_selector_template",
             "logs_retention_days"),
    **_group(NETWORK, "kea", "kea_url", "kea_username", "kea_password", "kea_services",
             "kea_verify_tls", "kea_ztp_fragment", "kea_dhcp4_config",
             "kea_dhcp6_config"),
    **_group(NETWORK, "monitoring_profile", "syslog_host", "syslog_trap_level",
             "syslog_origin_id", "syslog_source_interface", "syslog_heartbeat_seconds",
             "ntp_servers", "telemetry_receiver", "snmp_trap_host", "snmp_exporter_config",
             "snmp_exporter_auth"),
    # C1772: the endpoint layer's schedule and when a kept location is stale, one network's.
    **_group(NETWORK, "endpoints", "endpoint_read_interval_minutes",
             "endpoint_stale_after_hours"),
    **_group(NETWORK, "s3_archive", "s3_endpoint", "s3_bucket", "s3_access_key",
             "s3_secret_key", "s3_region", "s3_prefix", "s3_verify_tls"),
    # PHASE8_PLAN 17.1 S2: a network's SDN controller connections, one list (their credentials
    # are the credential store's, keyed by the network). Each network's own, never inherited
    # from Default (`OWN_ONLY`, C1841); drawn by its own Settings card, never a generic one
    # (`CARDLESS`).
    **_group(NETWORK, "sdn_controllers", "sdn_controllers"),
    # PHASE8_PLAN 17.1 S6: the SDN detection rules' thresholds, one network's together (a
    # scan's ports and window, its fallback rate, a flood's factor and window). Drawn on SDN ›
    # Responses (17.5, board 3), not on a generic card (`CARDLESS`).
    **_group(NETWORK, "sdn_detection", "sdn_scan_ports", "sdn_scan_window_seconds",
             "sdn_scan_fallback_pps", "sdn_flood_factor", "sdn_flood_window_seconds"),
    # PHASE8_PLAN 17.1 S8: a response's hard timeout and its ceiling, one network's together.
    # Drawn on SDN › Responses beside the response they bound, not on a generic card.
    **_group(NETWORK, "sdn_responses", "sdn_response_hard_timeout_seconds",
             "sdn_response_max_seconds"),
    # ── Per network: each a group of one ─────────────────────────────────────────────────
    **{k: (NETWORK, k) for k in (
        "verify_settle_windows", "deploy_max_workers", "deploy_verify_failure_limit",
        "nsot_device_tag_retention", "nsot_config_read_timeout", "netbox_excluded_vrfs",
        "settings_not_applicable", "reads_answer_cap_kib",
        "reads_max_workers", "reads_retention_days", "ai_topology_class",
        "alert_history_retention_days")},
    # ── Host-wide ─────────────────────────────────────────────────────────────────────────
    **_group(HOST, "netbox_connection", "netbox_url", "netbox_token", "netbox_auth_scheme",
             "netbox_verify_tls", "netbox_allow_writes"),
    **_group(HOST, "proxmox", "proxmox_url", "proxmox_node", "proxmox_token_id",
             "proxmox_token_secret", "proxmox_token_expires", "proxmox_verify_tls",
             "proxmox_backup_storage", "proxmox_backup_vmids"),
    **_group(HOST, "identity", "cf_access_aud", "cf_access_jwks_ttl", "cf_access_service_labels",
             "cf_access_team_domain", "cf_access_trusted_peers", "service_allowed_operations",
             *(f"require_{w}_for_{a}" for w in ("identity", "person")
               for a in ("approve", "break_glass", "configure", "confirm", "publish_remote",
                         "reveal"))),
    **_group(HOST, "platforms", "platform_map", "platform_default_netmiko_type"),
    # C724: keyed by credential profile, which is the installation's (as the profiles are).
    **_group(HOST, "credential_rotation", "credential_rotation_policies"),
    # C1317: the installation's (a nightly backup or a freeze is the host's, not a network's).
    **_group(HOST, "no_change_windows", "no_change_windows"),
    **_group(HOST, "web_server", "flask_host", "flask_port"),
    **_group(HOST, "git_author", "nsot_git_author_name", "nsot_git_author_email"),
    # Mercury's records database: one for the installation (P4-2), never a network's.
    **_group(HOST, "records_db", "records_db_host", "records_db_port", "records_db_name",
             "records_db_user", "records_db_password", "records_store_receipts",
             "records_store_acknowledgements", "records_store_restarts",
             "records_store_restart_windows", "records_store_restart_window_ends",
             "records_store_rotations", "records_store_breakglass_exports",
             "records_store_breakglass_intact", "records_store_breakglass_checks",
             "records_store_breakglass_drills", "records_store_reveals",
             "records_store_host_steps_done", "records_store_heartbeat_rules",
             "records_store_netbox_removals", "records_store_network_settings_record",
             "records_store_onboarding_runs", "records_store_inventory_edits",
             "records_store_approval_queue", "records_store_rollback_blocks",
             "records_store_retry_log", "records_store_netbox_created",
             "records_store_netbox_modified", "records_store_netbox_adopted",
             "records_store_interrupted_holds", "records_store_reader_values",
             "records_store_ai_calls", "records_store_evidence_packs",
             "records_store_alert_history", "records_store_flow_intent",
             "records_store_explain_answers"),
    # Phase 8's gateway (modules/ai): one key, one allowance and two caps for the installation.
    **_group(HOST, "ai_gateway", "anthropic_api_key", "ai_hosted", "ai_cap_usd_per_day",
           "ai_cap_day_boundary",
           # Per network INSIDE one installation value (PHASE8_PLAN 18.3 rule 2): a network's
           # background AI switch is never inherited, so it cannot be a network group.
           "ai_background"),
    # Retiring by expand, then contract (the operator, 2026-10-25: a call's cap is its task's,
    # derived from its pinned model): read by nothing from this release, declared for one
    # more so the previous release still reads it, then removed.
    **_group(RETIRING, "ai_cap_per_call", "ai_cap_usd_per_call"),
    # Lab 2's NETCONF demo script: global, and lab tooling (P.8 decision 4; NSOT_STAGE10_PLAN
    # 6.0b moves it to lab/).
    **_group(HOST, "lab_demo", "yang_push_script"),
    **_group(HOST, "schema", "settings_schema_version"),
    # One value for the installation, keyed by list INSIDE ({list: {device: declaration}}),
    # written by retire under the settings lock: a table of every list's declarations, not a
    # network's setting. Step 9 folds each list's rows into its own store (2026-10-05).
    # ── Read by nothing at run time: to retire (P.8 decision 3) ──────────────────────────
    **_group(RETIRING, "form_only", "collector_trap_enabled", "collector_netflow_enabled",
             "collector_syslog_enabled", "monitoring_identity_mode",
             "monitoring_identity_field", "monitoring_prom_label", "monitoring_strip_port",
             "promql_device_up", "promql_cpu", "promql_interface_oper"),
    # Oxidized is retired (Phase 3, the operator's P3-3, 2026-10-08): its keys are read by
    # nothing and stay declared for one release, so a rollback to the release before finds
    # them; the release after removes them with a settings version bump. No longer a
    # network's group, so no Settings screen draws a card for them.
    **_group(RETIRING, "oxidized", "oxidized_url", "oxidized_username", "oxidized_password",
             "oxidized_verify_tls", "oxidized_node_identity", "oxidized_router_db"),
    # The topology service, retired at 7.8 (2026-10-12): OBSERVE › Topology replaced it.
    **_group(RETIRING, "topology_service", "topology_service_url", "topology_service_type",
             "topology_service_token", "topology_service_verify_tls"),
    # The TFTP setting, retired at 7.8 (D16, 2026-10-13): its last readers, the device and bulk
    # file routes, left the same day; declared for one release, as Oxidized's keys are.
    **_group(RETIRING, "tftp_setting", "tftp_server_ip", "tftp_root"),
    # C815 (the operator, 2026-10-15): the browser at startup is the environment's alone
    # (NMAS_AUTO_OPEN_BROWSER, NMAS_HEADLESS; modules/config.py); the key had no control on any
    # page once today's Settings modal left; declared for one release, as the TFTP keys are.
    **_group(RETIRING, "browser_at_startup", "auto_open_browser"),
    # The AI family, removed (D15, 2026-10-14): the assistant's switch, the background agent's
    # and the workflow switches that only changed the assistant's prompt; declared for one
    # release, as Oxidized's keys are.
    **_group(RETIRING, "ai", "ai_enabled", "background_agent_enabled"),
    **_group(RETIRING, "workflow", "wf_auto_backup", "wf_read_first", "wf_require_approval",
             "wf_save_golden", "wf_update_vars"),
    # ── Already dead, recorded (never split) ─────────────────────────────────────────────
    **_group(DEAD, "dead", "jenkins_step_shell", "wf_run_jenkins",
             "netbox_remove_on_list_delete", "oxidized_rest_url", "grafana_embed_mode",
             "nsot_git_repo_path", "nsot_git_remote_url",
             "nsot_git_branch", "nsot_git_auto_push", "nsot_git_auth_mode", "nsot_git_token"),
}


#: What a person calls each network group (P.8 boards A to J): a card's title, a preview's row.
#: A group of one not named here is called by its key.
GROUP_LABELS: dict = {
    "grafana": "Grafana", "grafana_roles": "Grafana dashboards", "prometheus": "Prometheus",
    "loki": "Loki", "kea": "Kea",
    "monitoring_profile": "Monitoring profile", "s3_archive": "S3 archive",
    "verify_settle_windows": "Verify settle windows", "deploy_max_workers": "Deploy workers",
    "deploy_verify_failure_limit": "Deploy failure limit",
    "nsot_device_tag_retention": "Golden tags kept", "nsot_config_read_timeout":
    "Configuration read timeout", "netbox_excluded_vrfs": "NetBox excluded VRFs",
    "reads_answer_cap_kib": "Show commands: answer cap (KiB)",
    "reads_max_workers": "Show commands: devices read at once",
    "reads_retention_days": "Show commands: answers kept (days)",
    "ai_topology_class": "AI: the topology class",
    "alert_history_retention_days": "Alert history: transitions kept (days)",
    "endpoints": "Endpoints", "sdn_controllers": "SDN controllers",
    "sdn_detection": "SDN detection thresholds", "sdn_responses": "SDN response timeouts",
}

#: Network groups no generic Settings card draws or saves, each with the one module that
#: writes it: a generic card would draw the group's value as a JSON field and save it past its
#: writer's checks. `sdn_controllers`: `modules/sdn/connections.py` (save, remove, test),
#: drawn by its own card on a network's Integrations tab (board SdnSettings,
#: `templates/v2/_sdn_settings.html`). `sdn_detection`: the thresholds belong on SDN ›
#: Responses beside the rules they set (17.5, board 3); until that tab is built
#: `list_settings.write` writes them, and `modules/sdn/detect.py` reads them. `sdn_responses`:
#: the same, read by `modules/sdn/flow_ops.py`.
CARDLESS = ("sdn_controllers", "sdn_detection", "sdn_responses")

#: Network groups that are each network's own and never inherited from Default, whatever the
#: network's mode or choice: a network that sets none has none (the operator's decision of
#: 2026-10-27, C1841: a controller is one network's fabric, and inheriting Default's would
#: read, and later change, another network's switches). `list_settings.group_choice` answers
#: OWN for them unless the network declared them not applicable, so the resolver and
#: `integration_groups.group_id` agree.
OWN_ONLY = ("sdn_controllers",)

#: The key whose value says a group's outside service is configured at all: with it empty
#: nothing can be asked, so a reader skips the configuration and says "not configured"
#: (NSOT_P8_DESIGN section 8, step 5) rather than failing every interval.
URL_KEYS: dict = {
    "grafana": "grafana_url", "prometheus": "prometheus_url", "loki": "loki_url",
    "kea": "kea_url",
    "s3_archive": "s3_endpoint",
    # A network's controller list is what names its services: with none set there is nothing
    # to read, so the SDN reader keeps no store for it (C1841: none is none, never Default's).
    "sdn_controllers": "sdn_controllers",
}


def network_groups() -> tuple:
    """Every group a network chooses for (inherit, its own, not applicable), sorted. The
    host's declarations of "deliberately none" (`settings_not_applicable`) are the Default
    network's own bookkeeping, never a group another network inherits or owns. A `CARDLESS`
    group is left out: it is read through the resolver as any group is, and written only by
    its own module."""
    return tuple(sorted({g for k, (s, g) in SCOPES.items()
                         if s == NETWORK and g != "settings_not_applicable"
                         and g not in CARDLESS}))


def group_label(group: str) -> str:
    return GROUP_LABELS.get(group, group)


def scope_of(key: str) -> tuple:
    """``(scope, group)`` of a declared setting; KeyError names an undeclared one."""
    try:
        return SCOPES[key]
    except KeyError:
        raise KeyError(f"setting {key!r} has no scope in modules/settings_scope.py: declare "
                       "whether it belongs to a network or the host, and its group") from None


def group_keys(group: str) -> tuple:
    """Every key of *group*, sorted: what inherits together."""
    return tuple(sorted(k for k, (_s, g) in SCOPES.items() if g == group))
