"""A NetBox stood in for the AI's NetBox reads (`modules/ai/netbox_reads.py`): its list endpoints
over planted records in NetBox 4's shapes, GET only (any write raises), and the fixture that
hands it to `netbox_reads`. Not a test module: tests/test_ai_netbox_reads.py and
tests/test_ai_lookups.py import it, one home for the fake."""
import pytest

from modules.ai import netbox_reads


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(f"HTTP {self.status_code}")

    def json(self):
        return self.data


class FakeNetBox:
    """NetBox's list endpoints over *records* ({endpoint path: [records]}), answering GET with
    NetBox's filters as `netbox_reads` sends them; *count* overrides an endpoint's total (a
    truncated read); *down* makes every request fail. Each request recorded as
    ``(method, path, params)``."""

    def __init__(self, records=None, count=None, down=False):
        self.records, self.count, self.down, self.sent = dict(records or {}), dict(count or {}), \
            down, []

    def get(self, url, params=None, timeout=None):
        path = url.split("netbox.invalid", 1)[1]
        self.sent.append(("GET", path, dict(params or {})))
        if self.down:
            raise ConnectionError("planted: NetBox does not answer")
        rows = [r for r in self.records.get(path, []) if self._match(r, params or {})]
        limit = (params or {}).get("limit") or 50
        return Resp({"count": self.count.get(path, len(rows)), "results": rows[:limit]})

    @staticmethod
    def _match(r, params):
        import ipaddress
        for k, v in params.items():
            if k == "limit":
                continue
            if k == "address" and str(r.get("address", "")).split("/")[0] != str(v):
                return False
            if k == "contains" and ipaddress.ip_address(v) not in ipaddress.ip_network(
                    r.get("prefix", "0.0.0.0/32"), strict=False):
                return False
            if k == "prefix" and r.get("prefix") != v:
                return False
            if k == "name" and r.get("name") != v:
                return False
            if k == "vid" and r.get("vid") != v:
                return False
            if k == "device" and ((r.get("device") or (r.get("assigned_object") or {}).get(
                    "device") or {}).get("name")) != v:
                return False
        return True

    def __getattr__(self, name):
        # Any other method (post, patch, put, delete) is a write: refused loudly.
        raise AssertionError(f"netbox_reads used session.{name}: only GET is a read")


#: NetBox's records for the B1 ranges, in NetBox 4's shapes (custom fields, comments and a
#: config context planted, none of which may be read).
NETBOX = {
    "/api/ipam/prefixes/": [
        {"id": 1, "prefix": "192.0.2.0/24", "status": {"value": "active"},
         "description": "printers", "scope": {"name": "lab"}, "custom_fields": {"x": "planted"},
         "comments": "planted comment"},
        {"id": 2, "prefix": "2001:db8:50::/64", "status": {"value": "active"},
         "description": "printers v6", "scope": {"name": "lab"}},
    ],
    "/api/ipam/ip-addresses/": [
        {"id": 9, "address": "192.0.2.1/24", "status": {"value": "active"},
         "assigned_object": {"device": {"name": "r2"}, "name": "GigabitEthernet2"},
         "comments": "planted comment"},
    ],
    "/api/dcim/devices/": [
        {"id": 5, "name": "r2", "status": {"value": "active"}, "site": {"name": "lab"},
         "role": {"name": "router"}, "platform": {"name": "cisco-ios-xe"},
         "primary_ip4": {"address": "192.0.2.12/24"},
         "config_context": {"planted": "context"}, "local_context_data": {"p": 1},
         "custom_fields": {"secret_ish": "planted"}},
    ],
    "/api/ipam/vlans/": [{"id": 3, "vid": 20, "name": "users", "status": {"value": "active"},
                          "site": {"name": "lab"}}],
}


@pytest.fixture
def netbox(monkeypatch):
    nb = FakeNetBox(NETBOX)
    monkeypatch.setattr(netbox_reads, "_ready",
                        lambda: (True, "", nb, "http://netbox.invalid"))
    return nb


