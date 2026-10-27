"""Management authority (`modules/sdn/authority.py`; PHASE8_PLAN 17.1 S12): every route that
configures a device directly refuses one its SDN controller manages, naming the controller,
before the route runs; tested across every device-changing route through the real app.

- **The population:** every confirm- and approve-gated endpoint (`route_gates.GATES`) is either
  DIRECT (configures an inventory device, with where its request names it) or NOT_DIRECT (with
  why not), exactly, both ways, with a floor;
- **each DIRECT route**, posted naming a controller-managed device the way its own form does,
  answers 409 naming the controller, and the route's view never runs;
- the same route naming a direct device is not refused by the authority (whatever the route
  then answers of its own);
- a device's authority: ``openflow via <name>`` names its controller; ``openflow`` alone takes
  the network's one connection; anything else is direct; a network with no controller
  connection reads no inventory.
"""
import json

import pytest

from modules.route_gates import GATES
from modules.sdn import authority as A

MANAGED = {"hostname": "of-s9", "ip": "192.0.2.90", "device_type": "openflow",
           "platform": "openflow via lab-ctl"}
DIRECT_DEV = {"hostname": "r9", "ip": "192.0.2.91", "device_type": "cisco_ios"}
DEVICE_KINDS = ("confirm", "approve")
POPULATION_FLOOR = 40


def _app():
    import app as M
    return M.app


def test_every_confirm_and_approve_route_is_declared_direct_or_not():
    gated = {e for e, g in GATES.items() if g.kind in DEVICE_KINDS}
    assert len(gated) >= POPULATION_FLOOR
    assert set(A.DIRECT) | set(A.NOT_DIRECT) == gated, sorted(
        gated ^ (set(A.DIRECT) | set(A.NOT_DIRECT)))
    assert not set(A.DIRECT) & set(A.NOT_DIRECT)


@pytest.mark.parametrize("device,want", [
    (MANAGED, ("controller", "lab-ctl")),
    (dict(MANAGED, platform="openflow"), ("controller", "only-one")),
    (dict(MANAGED, platform="", device_type="openflow"), ("controller", "only-one")),
    (DIRECT_DEV, ("direct", "")),
])
def test_a_device_s_authority(device, want):
    got = A.of(device, "Default", conns=[{"name": "only-one"}])
    assert (got["kind"], got["controller"]) == want


def test_openflow_with_several_controllers_says_none_is_named():
    got = A.of(dict(MANAGED, platform="openflow"), "Default",
               conns=[{"name": "a"}, {"name": "b"}])
    assert got["kind"] == "controller" and "none is named on its record" in got["words"]


def _url(app, endpoint):
    rule = next(r for r in app.url_map.iter_rules() if r.endpoint == endpoint)
    return rule.rule.replace("<name>", "{name}")


def _post(client, app, endpoint, name):
    where, key = A.DIRECT[endpoint]
    url = _url(app, endpoint).format(name=name)
    data = {"list": "Default", "hash": "h"}
    if where == "form":
        data[key] = name
    elif where == "form_list":
        data[key] = [name]
    elif where == "json_keys":
        data[key] = json.dumps({name: {"x": 1}})
        data["order"] = json.dumps([name])
    return client.post(url, data=data)


@pytest.fixture
def inventory(monkeypatch):
    from modules import device

    monkeypatch.setattr(device, "load_saved_devices", lambda path=None: [MANAGED, DIRECT_DEV])
    monkeypatch.setattr(A, "_connections", lambda network: [{"name": "lab-ctl"}])
    ran = []
    app = _app()
    for endpoint in A.DIRECT:
        view = app.view_functions[endpoint]
        monkeypatch.setitem(app.view_functions, endpoint,
                            lambda *a, _e=endpoint, _v=view, **k: ran.append(_e) or ("ran", 418))
    return ran


@pytest.mark.parametrize("endpoint", sorted(A.DIRECT))
def test_each_direct_route_refuses_a_controller_managed_device_naming_it(inventory, endpoint):
    app = _app()
    resp = _post(app.test_client(), app, endpoint, MANAGED["hostname"])
    assert resp.status_code == 409, (endpoint, resp.status_code)
    got = resp.get_json()
    assert got["outcome"] == "controller_managed" and got["controller"] == "lab-ctl"
    assert ("of-s9 is managed by its controller, lab-ctl; Mercury does not configure it "
            "directly") in got["error"]
    assert inventory == []


@pytest.mark.parametrize("endpoint", sorted(A.DIRECT))
def test_each_direct_route_lets_a_direct_device_through_to_its_view(inventory, endpoint):
    app = _app()
    resp = _post(app.test_client(), app, endpoint, DIRECT_DEV["hostname"])
    assert resp.status_code == 418 and inventory == [endpoint]


def test_a_network_with_no_controller_reads_no_inventory(monkeypatch):
    from modules import device

    read = []
    monkeypatch.setattr(device, "load_saved_devices", lambda path=None: read.append(path) or
                        [MANAGED])
    monkeypatch.setattr(A, "_connections", lambda network: [])
    app = _app()
    monkeypatch.setitem(app.view_functions, "device_v2.deploy_confirm", lambda **k: ("ran", 418))
    resp = app.test_client().post("/v2/device/of-s9/deploy/confirm", data={"list": "Default"})
    assert resp.status_code == 418 and read == []
