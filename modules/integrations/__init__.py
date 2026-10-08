"""integrations — clients for the external tools NMAS reads from.

Phase 0 ships the settings framework and a ``test_connection()`` per tool.
Full read clients land in Phase 5.

Every integration is optional: an unconfigured tool reports
"Not configured — set in Settings" and never raises into a request handler.
"""

from modules.integrations.base import IntegrationClient, DEFAULT_TIMEOUT
from modules.integrations.netbox import NetBoxIntegration
from modules.integrations.prometheus import PrometheusIntegration
from modules.integrations.grafana import GrafanaIntegration
from modules.integrations.loki import LokiIntegration
from modules.integrations.kea import KeaIntegration
from modules.integrations.topology_service import TopologyServiceIntegration
from modules.integrations.nsot_git import NsotGitIntegration
from modules.integrations.s3_archive import S3ArchiveIntegration
from modules.integrations.proxmox import ProxmoxIntegration
from modules.integrations.monitoring_profile import MonitoringProfileIntegration

#: Registry keyed by settings prefix. Drives the Settings panel and the
#: dashboard status strip.
REGISTRY: dict = {
    cls.name: cls
    for cls in (
        NetBoxIntegration,
        PrometheusIntegration,
        GrafanaIntegration,
        LokiIntegration,
        KeaIntegration,
        TopologyServiceIntegration,
        NsotGitIntegration,
        S3ArchiveIntegration,
        ProxmoxIntegration,
        MonitoringProfileIntegration,
    )
}


def get_integration(name: str, list_name: str = ""):
    """Return an instance for *name*, FOR the network *list_name* when given (P.8 step 3),
    or None if unknown."""
    cls = REGISTRY.get(name)
    return cls(list_name=list_name) if cls else None


def all_statuses() -> list:
    """Badge state for every registered integration."""
    out = []
    for name, cls in REGISTRY.items():
        try:
            st = cls().status()
        except Exception as exc:              # noqa: BLE001 - a bad client must not break the strip
            st = {"ok": False, "state": "down", "label": cls.label, "message": str(exc)}
        st["name"] = name
        out.append(st)
    return out


__all__ = [
    "IntegrationClient", "DEFAULT_TIMEOUT", "REGISTRY",
    "get_integration", "all_statuses",
    "NetBoxIntegration", "PrometheusIntegration", "GrafanaIntegration",
    "LokiIntegration", "KeaIntegration",
    "TopologyServiceIntegration", "NsotGitIntegration", "S3ArchiveIntegration",
]
