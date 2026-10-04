"""External topology service integration (Phase 0: connection test only).

Generic by design: the service may serve a JSON graph, an SVG, or a page to
embed. The built-in CDP/LLDP/OSPF/BGP discovery is unaffected.
"""

from modules.integrations.base import IntegrationClient


class TopologyServiceIntegration(IntegrationClient):
    name = "topology_service"
    label = "Topology service"
    url_key = "topology_service_url"
    secret_keys = ("topology_service_token",)
    plain_keys = ("topology_service_type", "topology_service_verify_tls")

    def _auth_headers(self) -> dict:
        token = self._secret("topology_service_token")
        return {"Authorization": f"Bearer {token}"} if token else {}

    def test_connection(self) -> dict:
        r = self._get("")
        if not r["ok"]:
            return r
        return {"ok": True, "message": f"HTTP {r.get('status', 200)}"}
