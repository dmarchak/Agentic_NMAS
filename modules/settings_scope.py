"""Which settings belong to a NETWORK and which to the host (P.8, step 1; NSOT_P8_DESIGN).

The operator decided P.8 on 2026-10-04: two lists are two networks, the global settings file is
the Default network's layer (no migration), and an integration inherits as a GROUP, never key
by key, so a list that sets its own Grafana URL never sends Default's token to it. This table is
the one declaration of each key's scope and group, read by the resolver P.8 builds next; this
step changes no behaviour.

Scopes:
- ``network``: the key belongs to one network (a list); its *group* inherits together.
- ``host``: one installation-wide value (identity, the web server, NetBox's connection, the
  platform and role maps, Proxmox, the AI).
- ``retiring``: read by nothing at run time; decided 2026-10-04 to retire after checking
  nothing outside the app reads it, each retirement recorded in CUTOVER (P.8 decision 3).
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
             "loki_bearer_token", "loki_verify_tls", "loki_selector_template"),
    **_group(NETWORK, "oxidized", "oxidized_url", "oxidized_username", "oxidized_password",
             "oxidized_verify_tls", "oxidized_node_identity", "oxidized_router_db"),
    **_group(NETWORK, "kea", "kea_url", "kea_username", "kea_password", "kea_services",
             "kea_verify_tls", "kea_ztp_fragment", "kea_dhcp4_config"),
    **_group(NETWORK, "topology_service", "topology_service_url", "topology_service_type",
             "topology_service_token", "topology_service_verify_tls"),
    **_group(NETWORK, "lab", "clab_host", "clab_configs_dir", "clab_launch_patch", "clab_labs",
             "clab_sync_script", "clab_declared_unmapped"),
    **_group(NETWORK, "monitoring_profile", "syslog_host", "syslog_trap_level",
             "syslog_origin_id", "syslog_source_interface", "syslog_heartbeat_seconds",
             "ntp_servers", "telemetry_receiver", "snmp_trap_host", "snmp_exporter_config",
             "snmp_exporter_auth"),
    **_group(NETWORK, "s3_archive", "s3_endpoint", "s3_bucket", "s3_access_key",
             "s3_secret_key", "s3_region", "s3_prefix", "s3_verify_tls"),
    # ── Per network: each a group of one ─────────────────────────────────────────────────
    **{k: (NETWORK, k) for k in (
        "verify_settle_windows", "deploy_max_workers", "deploy_verify_failure_limit",
        "nsot_device_tag_retention", "nsot_config_read_timeout", "netbox_excluded_vrfs",
        "tftp_server_ip", "settings_not_applicable")},
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
    **_group(HOST, "platforms", "platform_map", "platform_default_netmiko_type", "role_map"),
    **_group(HOST, "web_server", "flask_host", "flask_port", "auto_open_browser", "tftp_root"),
    **_group(HOST, "ai", "ai_enabled", "background_agent_enabled"),
    **_group(HOST, "workflow", "wf_auto_backup", "wf_read_first", "wf_require_approval",
             "wf_save_golden", "wf_update_vars"),
    **_group(HOST, "git_author", "nsot_git_author_name", "nsot_git_author_email"),
    # Lab 2's NETCONF demo script: global, and lab tooling (P.8 decision 4; NSOT_STAGE10_PLAN
    # 6.0b moves it to lab/).
    **_group(HOST, "lab_demo", "yang_push_script"),
    **_group(HOST, "schema", "settings_schema_version"),
    # ── Read by nothing at run time: to retire (P.8 decision 3) ──────────────────────────
    **_group(RETIRING, "form_only", "collector_trap_enabled", "collector_netflow_enabled",
             "collector_syslog_enabled", "monitoring_identity_mode",
             "monitoring_identity_field", "monitoring_prom_label", "monitoring_strip_port",
             "promql_device_up", "promql_cpu", "promql_interface_oper"),
    # ── Already dead, recorded (never split) ─────────────────────────────────────────────
    **_group(DEAD, "dead", "jenkins_step_shell", "wf_run_jenkins",
             "netbox_remove_on_list_delete", "oxidized_rest_url", "grafana_embed_mode",
             "grafana_device_dashboard_url", "nsot_git_repo_path", "nsot_git_remote_url",
             "nsot_git_branch", "nsot_git_auto_push", "nsot_git_auth_mode", "nsot_git_token"),
}


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
