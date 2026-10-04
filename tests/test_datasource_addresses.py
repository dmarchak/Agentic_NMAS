"""The stored datasource list says where each datasource points (the operator, 2026-10-04).

Host step 14.14 confirms the history datasource before setting it, and its prompt showed "?":
the `grafana-dashboards` reader kept each datasource's uid, type and name from Grafana's
front-end settings, which carry only a proxy path. Now it also reads `api/datasources` and
keeps each one's address as `url`. A token that cannot read that list leaves the addresses
unknown, says why on each, and the read still succeeds: an address is information for a
confirm, never a reason to lose the dashboards.

The front-end settings are built from the 2026-09-29 capture; the list is the real 2026-10-04
answer, reduced to the fields read."""

import json
import os
from types import SimpleNamespace

from modules.readers import grafana_dashboards as G

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "grafana", "dashboards")


def _fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


class _Grafana:
    def __init__(self, listed=None):
        self.listed = listed if listed is not None else {
            "ok": True, "response": SimpleNamespace(json=lambda: _fixture("datasources_api.json"))}

    def _get(self, path, **_params):
        if path == "api/search":
            return {"ok": True, "response": SimpleNamespace(json=lambda: [])}
        if path == "api/frontend/settings":
            ds = _fixture("datasources.json")
            front = {"defaultDatasource": next(d["name"] for d in ds if d["is_default"]),
                     "datasources": {d["name"]: {"uid": d["uid"], "type": d["type"]} for d in ds}}
            return {"ok": True, "response": SimpleNamespace(json=lambda: front)}
        if path == "api/datasources":
            return self.listed
        return {"ok": False, "error": f"unexpected {path}"}


def test_each_datasource_carries_its_address():
    by_name = {d["name"]: d for d in G.read(_Grafana())["datasources"]}
    assert by_name["Thanos (lake)"]["url"] == "http://localhost:19193"
    assert by_name["prometheus"]["url"] == "http://localhost:9090"
    assert by_name["loki"]["url"] == "http://localhost:3100"
    assert not any("url_why" in d for d in by_name.values())


def test_a_token_that_cannot_list_them_says_why_and_the_read_succeeds():
    value = G.read(_Grafana({"ok": False, "status": 403, "error": "HTTP 403"}))
    assert value["datasources"], "the datasources were lost with their addresses"
    for d in value["datasources"]:
        assert d["url"] == ""
        assert d["url_why"] == ("api/datasources answered 403: the token cannot read data "
                                "source settings")


def test_a_datasource_the_list_does_not_name_says_so():
    listed = [d for d in _fixture("datasources_api.json") if d["name"] != "loki"]
    value = G.read(_Grafana({"ok": True, "response": SimpleNamespace(json=lambda: listed)}))
    loki = next(d for d in value["datasources"] if d["name"] == "loki")
    assert loki["url"] == "" and loki["url_why"] == "api/datasources does not list it"


def test_the_endpoint_is_declared():
    assert "api/datasources" in G.READER.endpoints
