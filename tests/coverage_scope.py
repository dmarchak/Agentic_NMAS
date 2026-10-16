"""What the coverage tool (scripts/nmas_coverage.py) counts as Mercury's automation code: the
package structure decides, and this file names ONLY the exceptions, each with its reason.
(Not a test module; tests/test_nmas_coverage.py holds it whole.)

The structure (`RULES`, first match wins):
- `modules/nsot/`, `modules/readers/`, `modules/inventory/`, `modules/integrations/`, and
  every other module directly in `modules/`: **automation**, the code that reads, renders,
  checks, deploys and records network state;
- `routes/` and `app.py`: **support**, the web layer around it.

A module the rules do not reach fails the tool, so a new package can never drop out of the
report unseen; an exception naming a file that no longer exists fails it too, so this list
cannot rot. Categories: **automation** (counted), **support** (shown, not in the totals),
**retiring** (shown in its own section, not in the totals: leaving with a decided removal),
**excluded** (not shown: no code to count).
"""

AUTOMATION, SUPPORT, RETIRING, EXCLUDED = "automation", "support", "retiring", "excluded"

#: (path prefix, category, why), first match wins; a prefix ending "/" is a folder.
RULES = (
    ("modules/nsot/", AUTOMATION, "the NSoT core: intent, templates, goldens, operations"),
    ("modules/readers/", AUTOMATION, "readers of device and service state"),
    ("modules/inventory/", AUTOMATION, "device inventory sources"),
    ("modules/integrations/", AUTOMATION, "NetBox, Kea, git, S3 and the other services"),
    ("modules/", AUTOMATION, "Mercury's modules, unless named below"),
    ("routes/", SUPPORT, "the web routes: the interface around the automation"),
    ("app.py", SUPPORT, "the web application's entry point and its legacy routes"),
)

#: path -> (category, why): the files the rules above would place wrongly.
EXCEPTIONS = {
    # ── Retiring (decided removals) ─────────────────────────────────────────────────────────
    # None now: the last, today's Backups (its module), was removed 2026-10-14 (C632, 7.8).
    # ── Support (the interface, settings and the app's own plumbing) ────────────────────────
    "modules/acknowledgements.py": (SUPPORT, "Needs attention's acknowledgements"),
    "modules/alert_bands.py": (SUPPORT, "the monitoring page's alert bands"),
    "modules/app_interpreter.py": (SUPPORT, "which Python the app runs on"),
    "modules/app_log.py": (SUPPORT, "the app's own log"),
    "modules/approval_queue.py": (SUPPORT, "the approval store behind drift rows"),
    "modules/attention.py": (SUPPORT, "the Needs attention page's model"),
    "modules/brand.py": (SUPPORT, "the interface's brand"),
    "modules/breakglass_page.py": (SUPPORT, "the Credentials page's break-glass card"),
    "modules/config.py": (SUPPORT, "the app's paths and settings access"),
    "modules/credential_profiles_page.py": (SUPPORT, "the Credentials page's profiles model"),
    "modules/csp.py": (SUPPORT, "the pages' content security policy"),
    "modules/device_actions.py": (SUPPORT, "the device page's actions and steppers"),
    "modules/device_list.py": (SUPPORT, "the Devices page's model"),
    "modules/device_logs.py": (SUPPORT, "the device page's Logs tab"),
    "modules/device_netbox.py": (SUPPORT, "the device page's NetBox tab"),
    "modules/device_page.py": (SUPPORT, "the device page's model"),
    "modules/dhcp_page.py": (SUPPORT, "the DHCP page's model"),
    "modules/discovery_page.py": (SUPPORT, "the Discovered page's model"),
    "modules/filestore.py": (SUPPORT, "the app's atomic file writes"),
    "modules/history_query.py": (SUPPORT, "History's query page"),
    "modules/history_sources.py": (SUPPORT, "History's event sources"),
    "modules/host_helpers.py": (SUPPORT, "host-side helpers for the app"),
    "modules/host_steps.py": (SUPPORT, "the host steps' page"),
    "modules/identity.py": (SUPPORT, "who is asking: the access proxy's assertion"),
    "modules/in_flight.py": (SUPPORT, "what is running, for the pages"),
    "modules/installation_diagnostics.py": (SUPPORT, "Settings › Installation › Diagnostics"),
    "modules/installation_settings.py": (SUPPORT, "Settings › Installation"),
    "modules/integration_groups.py": (SUPPORT, "Settings' integration groups"),
    "modules/invalidation.py": (SUPPORT, "which screens a change refreshes"),
    "modules/job_health.py": (SUPPORT, "job health's rows for Needs attention"),
    "modules/list_settings.py": (SUPPORT, "per-network settings access"),
    "modules/logs_page.py": (SUPPORT, "the Logs page's model"),
    "modules/logs_tail_page.py": (SUPPORT, "the live log tail's model"),
    "modules/manual.py": (SUPPORT, "the manual's pages"),
    "modules/manual_diagrams.py": (SUPPORT, "the manual's diagrams"),
    "modules/monitoring_profile_page.py": (SUPPORT, "the monitoring profile's page"),
    "modules/network_admin.py": (SUPPORT, "network administration pages"),
    "modules/network_choice.py": (SUPPORT, "which network a page shows"),
    "modules/network_store.py": (SUPPORT, "a network's own store, never another's (C487)"),
    "modules/op_progress.py": (SUPPORT, "operation progress for the pages"),
    "modules/operation_stages.py": (SUPPORT, "the declared stages of each operation route"),
    "modules/outbound.py": (SUPPORT, "the app's outbound request guard"),
    "modules/panels.py": (SUPPORT, "the pages' panels"),
    "modules/preview_confirm.py": (SUPPORT, "the previews and confirms the pages draw"),
    "modules/reads_page.py": (SUPPORT, "the reads page's model"),
    "modules/records_db.py": (SUPPORT, "the records database's access"),
    "modules/records_migrate.py": (SUPPORT, "the records database's migration"),
    "modules/remote_setup.py": (SUPPORT, "the git remote's setup page"),
    "modules/reveal_audit.py": (SUPPORT, "the audit of revealed values"),
    "modules/route_gates.py": (SUPPORT, "every mutating route's gate declaration"),
    "modules/run_stepper.py": (SUPPORT, "the one progress display's model"),
    "modules/save_page.py": (SUPPORT, "the Save page's model"),
    "modules/saved_views.py": (SUPPORT, "saved views on the pages"),
    "modules/settings_page.py": (SUPPORT, "the Settings page's model"),
    "modules/settings_schema.py": (SUPPORT, "the settings' schema"),
    "modules/settings_scope.py": (SUPPORT, "where each setting lives"),
    "modules/topology_layout.py": (SUPPORT, "the Topology page's layout"),
    "modules/topology_page.py": (SUPPORT, "the Topology page's model"),
    "modules/topology_positions.py": (SUPPORT, "the Topology page's saved positions"),
    "modules/update_op.py": (SUPPORT, "the app's own update"),
    "modules/utils.py": (SUPPORT, "small shared helpers"),
    "modules/integrations/grafana.py": (SUPPORT, "dashboards for the monitoring pages"),
    "modules/integrations/loki.py": (SUPPORT, "log queries for the Logs pages"),
    "modules/integrations/prometheus.py": (SUPPORT, "metric queries for the monitoring pages"),
}


def classify(path: str):
    """`(category, why)` for a repository-relative path, or None when no rule reaches it."""
    if path in EXCEPTIONS:
        return EXCEPTIONS[path]
    for prefix, category, why in RULES:
        if path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
            return (category, why)
    return None
