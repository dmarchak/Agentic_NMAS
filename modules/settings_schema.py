"""settings_schema.py

Schema, defaults, and forward-migration for ``data/user_settings.json``.

Every setting added by the NSoT integrations work is declared here with a
default that reproduces the behaviour the app had before the setting existed.
A user who never opens the Integrations panel sees no change.

Validation uses ``jsonschema`` rather than ``pydantic``: settings are plain
dicts round-tripped through ``config.load_user_settings`` /
``config.save_user_settings``, so a declarative schema layers onto the existing
code without rewriting every settings access as a typed model.

Secret-bearing keys are declared in :mod:`modules.secrets_store` and stored
encrypted; the defaults here are always "" (unset).
"""

import logging
import os

from modules.config import load_user_settings, save_user_settings

log = logging.getLogger(__name__)

# Bumped whenever a migration step is added below.
SCHEMA_VERSION = 1

_IS_WINDOWS = os.name == "nt"


def _default_tftp_root() -> str:
    """OS-appropriate TFTP root.

    The historical default was the Windows path ``C:/TFTP-Root``, which on Linux
    caused config.py to create a literal directory named ``C:`` in the repo root.
    """
    return "C:/TFTP-Root" if _IS_WINDOWS else "/srv/tftp"


# ---------------------------------------------------------------------------
# Defaults — each reproduces pre-existing behaviour
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "settings_schema_version": SCHEMA_VERSION,

    # ── Server / portability ────────────────────────────────────────────────
    "flask_host":        "0.0.0.0",
    "flask_port":        5000,
    # Historically an unconditional webbrowser.open() at startup.
    "auto_open_browser": True,

    # ── File transfer ───────────────────────────────────────────────────────
    "tftp_root":      _default_tftp_root(),
    "tftp_server_ip": "",

    # ── NetBox ──────────────────────────────────────────────────────────────
    "netbox_url":         "",
    "netbox_token":       "",      # encrypted at rest
    "netbox_auth_scheme": "Bearer",
    "netbox_verify_tls":  True,
    # Fail-closed write gate. Off means no NetBox write can be issued at all.
    "netbox_allow_writes": False,
    # Whether deleting a device list also removes its objects from NetBox.
    # Historically this cascade ran silently and unconditionally.
    "netbox_remove_on_list_delete": False,

    # ── Prometheus / Thanos ─────────────────────────────────────────────────
    "prometheus_url":          "",
    "prometheus_auth_mode":    "none",   # none | basic | bearer
    "prometheus_username":     "",
    "prometheus_password":     "",
    "prometheus_bearer_token": "",
    "prometheus_verify_tls":   True,

    # ── Grafana ─────────────────────────────────────────────────────────────
    "grafana_url":            "",
    "grafana_token":          "",
    "grafana_embed_mode":     "link",    # link | iframe
    "grafana_device_dashboard_url": "",  # supports {hostname} / {ip}
    "grafana_verify_tls":     True,

    # ── Loki ────────────────────────────────────────────────────────────────
    "loki_url":              "",
    "loki_auth_mode":        "none",
    "loki_username":         "",
    "loki_password":         "",
    "loki_bearer_token":     "",
    "loki_verify_tls":       True,
    "loki_selector_template": '{host="{ip}"}',

    # ── Oxidized ────────────────────────────────────────────────────────────
    "oxidized_url":           "",
    "oxidized_username":      "",
    "oxidized_password":      "",
    "oxidized_node_identity": "hostname",   # hostname | ip
    "oxidized_verify_tls":    True,

    # ── Kea Control Agent ───────────────────────────────────────────────────
    "kea_url":        "",
    "kea_username":   "",
    "kea_password":   "",
    "kea_services":   ["dhcp4"],
    "kea_verify_tls": True,

    # ── External topology service ───────────────────────────────────────────
    "topology_service_url":   "",
    "topology_service_type":  "json",    # json | svg | iframe
    "topology_service_token": "",
    "topology_service_verify_tls": True,

    # ── NSoT git repo ───────────────────────────────────────────────────────
    "nsot_git_repo_path":    "",         # blank = per-list data/lists/{slug}/config_repo
    "nsot_git_remote_url":   "",
    "nsot_git_branch":       "main",
    "nsot_git_author_name":  "NMAS",     # config_git.py's historical hardcoded values
    "nsot_git_author_email": "nmas@localhost",
    "nsot_git_auto_push":    False,
    "nsot_git_auth_mode":    "ssh_key",  # ssh_key | token
    "nsot_git_token":        "",

    # ── Identity: Cloudflare Access ─────────────────────────────────────────
    # The app has no auth layer of its own; identity comes from the tunnel in
    # front of it. The EMAIL HEADER IS NOT EVIDENCE — anything that can reach
    # the port can set it. What is verified is the signed assertion:
    # `Cf-Access-Jwt-Assertion`, RS256, against the team's certs endpoint, with
    # `aud` and `iss` checked. The email is then read from the verified claims.
    "cf_access_team_domain": "",         # <team>.cloudflareaccess.com
    "cf_access_aud":         "",         # Application Audience tag
    #: Raw socket peers allowed to present an identity. The SECOND, independent
    #: condition: a valid JWT replayed from elsewhere on the LAN still fails.
    #: It is also the layer that survives a firewall rule being edited later.
    "cf_access_trusted_peers": "",       # comma-separated; blank disables the check
    "cf_access_jwks_ttl":    3600,       # key-cache seconds; survives a short outage
    #: ``{client-id: friendly name}`` for service tokens, so an audit row reads
    #: "nmas-automation" rather than 32 hex characters. A LABEL ONLY — never a
    #: grant. Identity still comes from the verified assertion; an unlabelled
    #: token authenticates exactly as well, it just reads worse.
    "cf_access_service_labels": {},
    #: All three default ON. Reveal exposes a secret; approve and confirm are
    #: the two actions that put configuration **on a device**. An audit entry
    #: for any of them is worthless without a name attached to it, and the two
    #: device-pushing actions are the ones whose consequences are physical.
    #:
    #: There is deliberately **no localhost exemption**. An exemption for
    #: "requests from the box itself" is an exemption for anything that has
    #: reached the box, which is precisely the situation where the audit trail
    #: matters most. Automation authenticates the same way everyone does — a
    #: Cloudflare Access **service token** through the tunnel, verified as a
    #: normal assertion and recorded as the service.
    "require_identity_for_reveal":  True,
    "require_identity_for_approve": True,
    "require_identity_for_confirm": True,
    #: A verified SERVICE is still not a person. Approve and confirm are the
    #: points where a human is supposed to have looked at an exact command list
    #: before it reaches a device; the confirm hash is only worth something
    #: because somebody read what it covers.
    #:
    #: Reveal is included because the service credential lives in a file on a
    #: workstation, and if it leaks, reveal is the largest blast radius it has.
    #: Nothing planned needs it: Part 2's rotation runs in-process and never
    #: calls the HTTP reveal route. Services authenticate, plan and queue;
    #: anything that exposes a secret or changes a device has a person behind
    #: it.
    "require_person_for_reveal":  True,
    "require_person_for_approve": True,
    "require_person_for_confirm": True,
    #: The narrow exception: operation kinds a *service* may approve/confirm
    #: despite the two settings above. **Starts empty**, so the exception grants
    #: nothing until somebody names something. Part 2 adds
    #: `credential_rotation` by name — one kind, chosen deliberately, rather
    #: than a flag that opens all of them at once.
    "service_allowed_operations": [],

    # ── Config persistence (Oxidized → containerlab startup files) ──────────
    # The pipeline lives outside this repo; see docs/ARCHITECTURE.md. These are
    # settings rather than constants because they are deployment facts, and
    # because modules/nsot/ may not contain IP literals — a rule that caught
    # them here.
    "oxidized_rest_url":    "",          # e.g. http://127.0.0.1:8888
    "oxidized_router_db":   "/opt/oxidized/router.db",
    "clab_sync_script":     "",          # the flock wrapper
    "clab_host":            "",          # user@host of the containerlab VM
    "clab_configs_dir":     "labs/lab/configs",

    # ── S3-compatible archive ───────────────────────────────────────────────
    "s3_endpoint":   "",
    "s3_bucket":     "",
    "s3_access_key": "",
    "s3_secret_key": "",
    "s3_region":     "",
    "s3_prefix":     "",
    "s3_verify_tls": True,

    # ── Platform map (NetBox platform slug → how NMAS treats the device) ────
    # This map is what makes multi-vendor support a configuration change rather
    # than a code change. Seeded for the two reference platforms; the operator
    # edits it in Settings.
    "platform_map": {
        "cisco-ios-xe": {
            "netmiko_device_type": "cisco_xe",
            "template_dir":        "cisco-ios-xe",
            "deploy_transport":    "ssh",
            "supports_netconf":    True,
            "prometheus_cpu_query": "",
        },
        "cisco-ios": {
            "netmiko_device_type": "cisco_ios",
            "template_dir":        "cisco-ios",
            "deploy_transport":    "ssh",
            "supports_netconf":    False,
            "prometheus_cpu_query": "",
        },
    },
    # Fallback netmiko type for a platform absent from the map. Empty means
    # "skip the device with a warning"; setting it trades a skip for a guess.
    "platform_default_netmiko_type": "",

    # ── Role map (NetBox role slug → NMAS role) ─────────────────────────────
    # NMAS roles drive topology icons and are one of router/switch/firewall.
    # An unmapped role resolves to "" so topology._infer_role(hostname) applies,
    # which is the same behaviour a local list with a blank role field gets.
    "role_map": {
        "router": "router",
        "core-router": "router",
        "edge-router": "router",
        "switch": "switch",
        "access-switch": "switch",
        "distribution-switch": "switch",
        "core-switch": "switch",
        "firewall": "firewall",
    },

    # ── Deploy verification ─────────────────────────────────────────────────
    # Per-check settle windows, in seconds. Verifying immediately after a
    # change produces spurious failures: RIP updates every 30s, so its window
    # spans more than two update cycles. OSPF settles in seconds.
    "verify_settle_windows": {
        "ospf":       {"initial_wait": 5,  "timeout": 45, "interval": 5},
        "rip":        {"initial_wait": 15, "timeout": 90, "interval": 15},
        "bgp":        {"initial_wait": 10, "timeout": 60, "interval": 10},
        "interfaces": {"initial_wait": 2,  "timeout": 20, "interval": 4},
    },

    # ── Deploy concurrency and safety ───────────────────────────────────────
    # Sequential by default. vIOS-L2 has limited vty lines, and Oxidized, the
    # drift checker, the ping worker and a nine-device batch can all want the
    # same device at once.
    "deploy_max_workers": 1,
    # Stop attempting after this many VERIFY failures. One drifted device means
    # someone touched a box; three verify failures means something systemic.
    "deploy_verify_failure_limit": 2,

    # ── NSoT repo tag retention ─────────────────────────────────────────────
    # baseline/* tags are always kept — they are the network-wide restore points.
    # Per-device golden/<device>/* tags are pruned beyond the last N.
    # 0 = keep all. Commits retain full history regardless of tag pruning.
    "nsot_device_tag_retention": 50,
    # Seconds to wait for a full `show running-config` when reading a device
    # back after a failed deploy. Generous on purpose: this read happens
    # moments after `write memory`, and on an emulated device NVRAM writes
    # leave it slow for tens of seconds. Measured on a containerlab vIOS-L2 —
    # 5.5s idle, >16s immediately after a save. A number that happens to work
    # on one lab is the kind of assumption this project keeps out of the code,
    # so it is a setting with a wide default rather than a constant.
    "nsot_config_read_timeout": 120,

    # ── Jenkins ─────────────────────────────────────────────────────────────
    # Every generated pipeline emitted Windows `bat` steps; that stays the
    # default so existing pipelines regenerate byte-identically.
    "jenkins_step_shell": "bat",         # bat | sh

    # ── Built-in collectors ─────────────────────────────────────────────────
    # Ports already lived in modules/collector_config.py per list; only the
    # enable/disable toggles are new, and both default on as before.
    "collector_trap_enabled":    True,
    "collector_netflow_enabled": True,
    "collector_syslog_enabled":  True,

    # ── Monitoring identity mapping ─────────────────────────────────────────
    "monitoring_identity_mode":   "ip",   # ip | hostname | netbox_custom_field
    "monitoring_identity_field":  "",
    "monitoring_prom_label":      "instance",
    "monitoring_strip_port":      True,

    # ── PromQL query templates (settings, not code) ─────────────────────────
    "promql_device_up":     'up{{{label}="{target}"}}',
    "promql_cpu":           "",
    "promql_interface_oper": "",
}


# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------

_STR = {"type": "string"}
_BOOL = {"type": "boolean"}

SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    # Unknown keys are allowed on purpose: user_settings.json also holds keys
    # owned by older features, and constraint 1 says keep them readable.
    "additionalProperties": True,
    "properties": {
        "settings_schema_version": {"type": "integer", "minimum": 1},

        "flask_host": _STR,
        "flask_port": {"type": "integer", "minimum": 1, "maximum": 65535},
        "auto_open_browser": _BOOL,

        "tftp_root": _STR,
        "tftp_server_ip": _STR,

        "netbox_url": _STR,
        "netbox_token": _STR,
        "netbox_auth_scheme": {"enum": ["Bearer", "Token"]},
        "netbox_verify_tls": _BOOL,
        "netbox_allow_writes": _BOOL,
        "netbox_remove_on_list_delete": _BOOL,

        "prometheus_url": _STR,
        "prometheus_auth_mode": {"enum": ["none", "basic", "bearer"]},
        "prometheus_verify_tls": _BOOL,

        "grafana_url": _STR,
        "grafana_embed_mode": {"enum": ["link", "iframe"]},
        "grafana_verify_tls": _BOOL,

        "loki_url": _STR,
        "loki_auth_mode": {"enum": ["none", "basic", "bearer"]},
        "loki_verify_tls": _BOOL,
        "loki_selector_template": _STR,

        "oxidized_url": _STR,
        "oxidized_node_identity": {"enum": ["hostname", "ip"]},
        "oxidized_verify_tls": _BOOL,

        "kea_url": _STR,
        "kea_services": {"type": "array", "items": {"enum": ["dhcp4", "dhcp6"]}},
        "kea_verify_tls": _BOOL,

        "topology_service_url": _STR,
        "topology_service_type": {"enum": ["json", "svg", "iframe"]},
        "topology_service_verify_tls": _BOOL,

        "nsot_git_repo_path": _STR,
        "nsot_git_remote_url": _STR,
        "nsot_git_branch": _STR,
        "nsot_git_author_name": _STR,
        "nsot_git_author_email": _STR,
        "nsot_git_auto_push": _BOOL,
        "nsot_git_auth_mode": {"enum": ["ssh_key", "token"]},

        "cf_access_team_domain": _STR,
        "cf_access_aud": _STR,
        "cf_access_trusted_peers": _STR,
        "cf_access_jwks_ttl": {"type": "integer", "minimum": 0},
        "cf_access_service_labels": {"type": "object"},
        "require_identity_for_reveal": _BOOL,
        "require_identity_for_approve": _BOOL,
        "require_identity_for_confirm": _BOOL,
        "require_person_for_reveal": _BOOL,
        "require_person_for_approve": _BOOL,
        "require_person_for_confirm": _BOOL,
        "service_allowed_operations": {"type": "array", "items": _STR},

        "oxidized_rest_url": _STR,
        "oxidized_router_db": _STR,
        "clab_sync_script": _STR,
        "clab_host": _STR,
        "clab_configs_dir": _STR,

        "s3_endpoint": _STR,
        "s3_bucket": _STR,
        "s3_region": _STR,
        "s3_prefix": _STR,
        "s3_verify_tls": _BOOL,

        "platform_map": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "netmiko_device_type":  {"type": "string"},
                    "template_dir":         {"type": "string"},
                    "deploy_transport":     {"enum": ["ssh", "netconf"]},
                    "supports_netconf":     {"type": "boolean"},
                    "prometheus_cpu_query": {"type": "string"},
                },
                "required": ["netmiko_device_type"],
            },
        },
        "platform_default_netmiko_type": _STR,
        "role_map": {
            "type": "object",
            # "" is allowed and means "fall back to hostname inference".
            "additionalProperties": {"enum": ["router", "switch", "firewall", ""]},
        },

        "nsot_device_tag_retention": {"type": "integer", "minimum": 0},
        "nsot_config_read_timeout": {"type": "integer", "minimum": 5},
        "deploy_max_workers": {"type": "integer", "minimum": 1, "maximum": 16},
        "deploy_verify_failure_limit": {"type": "integer", "minimum": 1},
        "verify_settle_windows": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "initial_wait": {"type": "integer", "minimum": 0},
                    "timeout":      {"type": "integer", "minimum": 0},
                    "interval":     {"type": "integer", "minimum": 1},
                },
            },
        },

        "jenkins_step_shell": {"enum": ["bat", "sh"]},

        "collector_trap_enabled": _BOOL,
        "collector_netflow_enabled": _BOOL,
        "collector_syslog_enabled": _BOOL,

        "monitoring_identity_mode": {"enum": ["ip", "hostname", "netbox_custom_field"]},
        "monitoring_identity_field": _STR,
        "monitoring_prom_label": _STR,
        "monitoring_strip_port": _BOOL,

        "promql_device_up": _STR,
        "promql_cpu": _STR,
        "promql_interface_oper": _STR,
    },
}


def validate(settings: dict) -> tuple:
    """Validate *settings* against :data:`SCHEMA`.

    Returns ``(ok, error)``. A missing jsonschema install degrades to "valid"
    with a warning rather than taking the settings page down.
    """
    try:
        import jsonschema
    except ImportError:
        log.warning("settings_schema: jsonschema not installed — skipping validation")
        return True, ""
    try:
        jsonschema.validate(instance=settings, schema=SCHEMA)
        return True, ""
    except jsonschema.ValidationError as exc:
        path = ".".join(str(p) for p in exc.absolute_path) or "(root)"
        return False, f"{path}: {exc.message}"


def get_setting(key: str, default=None):
    """Read a setting, falling back to the declared default."""
    settings = load_user_settings()
    if key in settings:
        return settings[key]
    return DEFAULTS.get(key, default)


def migrate() -> dict:
    """Bring ``user_settings.json`` up to :data:`SCHEMA_VERSION`. Idempotent.

    Old keys are never deleted — constraint 1 requires they stay readable.
    Returns a summary describing what changed.
    """
    settings = load_user_settings()
    current  = settings.get("settings_schema_version", 0)
    summary  = {"from_version": current, "to_version": SCHEMA_VERSION,
                "added_keys": [], "encrypted_keys": [], "changed": False}

    if current >= SCHEMA_VERSION:
        # Still upgrade any secret that predates the encrypted store.
        from modules.secrets_store import migrate_plaintext
        upgraded = migrate_plaintext()
        if upgraded:
            summary["encrypted_keys"] = upgraded
            summary["changed"] = True
        return summary

    # ── v0 → v1 ─────────────────────────────────────────────────────────────
    # Seed any absent key with its default. Existing values win, so behaviour
    # for a configured install is unchanged.
    for key, value in DEFAULTS.items():
        if key not in settings:
            settings[key] = value
            summary["added_keys"].append(key)

    # Carry the legacy TFTP server IP forward if config.py had stored one.
    if not settings.get("tftp_server_ip"):
        settings["tftp_server_ip"] = load_user_settings().get("tftp_server_ip", "")

    settings["settings_schema_version"] = SCHEMA_VERSION
    save_user_settings(settings)

    # Encrypt secrets that were written in plaintext by earlier builds
    # (netbox_token is the one that existed before this work).
    from modules.secrets_store import migrate_plaintext
    summary["encrypted_keys"] = migrate_plaintext()
    summary["changed"] = True

    log.info("settings_schema: migrated v%d → v%d (%d key(s) seeded, %d secret(s) encrypted)",
             current, SCHEMA_VERSION, len(summary["added_keys"]),
             len(summary["encrypted_keys"]))
    return summary
