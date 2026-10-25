"""P1's Explain with the network context model (PHASE8_PLAN 15.15; the topology class, 15.11;
modules/ai/explain.py, modules/network_model.py, modules/ai/egress_classes.py), against planted
answers through a fake `send`, on tests/test_ai_explain.py's world (the pack built by the real
builder from the real captures: r1 by IPv6, an instruction planted in an interface description).

Beside the pack, the network's intent: the REAL fleet configs of r1, r2, r3 and s3 parsed and
committed (tests/test_network_model.py's `commit_fleet`, an interface description carrying a
secret's shape), an inventory row per device carrying a planted NetBox description and its
encrypted credentials, and the Topology reader's value from the real captures.

- **The request's order:** the prompt v2, then the cached context (the network's summary, the
  pack's format, the topology's format), the same bytes on two calls a read apart; the call's
  own data last (the subgraph, the pack, the alert, the alert last).
- **Only the topology class:** the subgraph's every key is one the class holds (devices, links,
  subnets, adjacencies, observed, and their ids); no configuration line, no description.
- **Planted secrets:** a secret's shape in a NetBox description and in an interface
  description, and a credential, never reach the bytes sent; a stored secret's value the model
  carries (a VRF named with it) is masked by the gateway in the bytes sent.
- **The check:** a hypothesis citing the subgraph's ids is shown, its topology ids drawn as
  text; an id the subgraph does not hold, even one the model does, is couldn't analyse.
- **Off:** with the network's topology class off, nothing of the topology is sent and the
  result says so, drawn on the card; an unreadable setting is off; a classification marking
  (its seam) sends nothing; a model that cannot be built is said in the call.
"""
import json
import re

import pytest
import yaml

from modules import evidence_pack as EP
from modules import network_model as NM
from modules.ai import explain
from tests.test_ai_explain import _answer, _explain, _refs, world  # noqa: F401 (fixtures)
from tests.test_device_v2 import _unstore, lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import (DEVICES, INJECTION, V6, _alerts, _build,  # noqa: F401
                                      pack_lab)
from tests.test_network_model import (NOW, PLANTED, READ_AT, commit_fleet,
                                      store_observed)

HOSTS = ["r1", "r2", "r3", "s3"]
#: A stored secret's value, planted as the name of a VRF on one of r1's interfaces.
STORED = "Vrf5t0redS3cretValue"


@pytest.fixture
def topo(world, monkeypatch):  # noqa: F811
    rows = [dict(d, _netbox_id=200 + i, _site="site-a", description=PLANTED, comments=PLANTED,
                 password="gAAAAplantedEncryptedPassword",
                 role="router" if d["hostname"].startswith("r") else "switch")
            for i, d in enumerate(DEVICES + [{"hostname": "s3", "ip": "192.0.2.23",
                                              "device_type": "cisco_ios",
                                              "platform": "cisco_ios", "username": "nmas"}])]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(r) for r in rows])

    def plant(h, hv):
        if h == "r1":
            hv["interfaces"][3]["vrf"] = STORED
    commit_fleet(world.lab["repo"], hosts=HOSTS, edit=plant)
    store_observed()
    monkeypatch.setattr(NM, "_now", lambda: NOW)
    NM.forget()
    world.ids = {r["hostname"]: f"dev:{r['_netbox_id']}" for r in rows}
    # The pack built now that the network is committed and observed: it captures the overlay
    # (C1712) and the health figures (C1714) as of its alert's time, and is the one Explain
    # reads (the newest with its id).
    world.pack = _build(_alerts(V6, extra_labels={"ifAlias": INJECTION}))
    assert EP.record(world.pack)["ok"]
    yield world
    NM.forget()
    _unstore(NM.OBSERVED_READER)


def _blocks(text, tag):
    return re.findall(rf'<{tag} name="([^"]+)">', text)


def _block(text, tag, name):
    return re.search(rf'<{tag} name="{name}">\n(.*?)\n</{tag}>', text, re.S).group(1)


def _sent(w):
    body = w.sent[-1]["body"]
    return body, body["messages"][0]["content"], body["system"][1]["text"]


# ------------------------------------------------------------------------- the request

def test_stable_context_first_and_the_alert_last(topo):
    from modules.ai import prompts
    topo.answer = _answer(topo.pack)
    got = _explain(topo)
    assert got["ok"] is True, got
    body, user, ctx = _sent(topo)
    assert body["system"][0]["text"] == prompts.load("explain", 3)["text"]
    assert explain.PROMPT == ("explain", 3)
    assert _blocks(ctx, "context") == ["network", "pack_format", "topology_format"]
    assert body["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert _blocks(user, "data") == ["network_topology", "pack", "the_alert"]
    assert got["topology"]["sent"] is True and got["topology"]["subject"] == "r1"
    # r1's four, and s1, LLDP's neighbour on its Gi3, which this inventory does not manage.
    assert set(got["topology"]["devices"]) == {topo.ids[h] for h in HOSTS} | {"ext:s1"}


def test_the_cached_prefix_is_the_same_bytes_and_a_later_read_changes_nothing(topo):
    """C1712: the observed overlay is the pack's capture. A later read of the Topology
    reader moves nothing Explain sends, the cached prefix or the call's own data."""
    topo.answer = _answer(topo.pack)
    _explain(topo)
    first_system, first_user = topo.sent[-1]["body"]["system"], topo.sent[-1]["body"][
        "messages"][0]["content"]
    store_observed(at="2026-10-15T08:20:30Z")
    _explain(topo)
    body = topo.sent[-1]["body"]
    assert json.dumps(body["system"]) == json.dumps(first_system)
    assert body["messages"][0]["content"] == first_user
    assert "2026-10-15T08:20:30Z" not in body["messages"][0]["content"]
    assert READ_AT in body["messages"][0]["content"]
    assert not re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d", json.dumps(body["system"]))


#: Every key the topology class's subgraph may hold, besides the ids (dev:, link:, adj:,
#: cable:, ext:, mercury) that key its maps.
CLASS_KEYS = {
    "network", "model", "subject", "hops", "devices", "links", "adjacencies", "cables",
    "observed", "model_errors", "name", "role", "site", "platform", "address", "interfaces",
    "ospf", "ospfv3", "bgp", "intent", "inventory", "hop", "via", "detail", "managed", "what",
    "addresses", "vrf", "mode", "vlan", "trunk_vlans", "shutdown", "ospf_area", "ospfv3_area",
    "router_id", "areas", "passive", "asn", "peers", "remote_as", "subnet", "members", "dev",
    "interface", "expanded", "note", "members_total", "listed", "proto", "between", "link",
    "expected", "outside_management", "state", "words", "read_at", "since", "ends", "port",
    "reported", "down_at", "mercury_attaches_here", "source", "as_of"}
ID = re.compile(r"^(dev|link|adj|cable|ext):|^mercury$")


def _keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)
    return out


def test_the_subgraph_holds_only_the_topology_class(topo):
    topo.answer = _answer(topo.pack)
    _explain(topo)
    _b, user, ctx = _sent(topo)
    sub = _block(user, "data", "network_topology")
    keys = {k for k in _keys(yaml.safe_load(sub), set()) if not ID.match(str(k))}
    assert keys <= CLASS_KEYS, keys - CLASS_KEYS
    for line in ("description", "router ospf", "ip address", "remote-as", "passive-interface",
                 "snmp-server", "network 10.", "username", "password"):
        assert line not in sub and line not in _block(ctx, "context", "network"), line


def test_planted_secrets_never_reach_the_bytes_sent(topo, monkeypatch):
    from modules import redact
    model, _e = NM.model_for("Lab")
    assert STORED in json.dumps(model), "the planted value is in the model"
    monkeypatch.setattr(redact, "known_secret_values", lambda: {STORED: "Lab:planted"})
    topo.answer = _answer(topo.pack)
    assert _explain(topo)["ok"] is True
    sent = topo.sent[-1]["bytes"]
    for planted in (STORED, "Pl4ntedModelSecret", "gAAAAplanted"):
        assert planted not in sent, planted
    assert _blocks(_sent(topo)[1], "data")[0] == "network_topology"


# ------------------------------------------------------------------------- the check

def _citing(w, refs):
    a = _answer(w.pack)
    a["hypotheses"][0]["evidence_refs"] = refs
    return a


def test_a_hypothesis_citing_the_subgraph_is_shown(topo):
    from html import unescape
    s3, core = topo.ids["s3"], "link:10.255.3.0/24"
    topo.answer = _citing(topo, [_refs(topo.pack, "logs")[0], s3, core])
    got = _explain(topo)
    assert got["ok"] is True, got
    assert got["answer"]["hypotheses"][0]["cites"] == [
        {"ref": _refs(topo.pack, "logs")[0], "in_pack": True},
        {"ref": s3, "in_pack": False}, {"ref": core, "in_pack": False}]
    r = topo.lab["client"].post(f"/v2/monitoring/alerts/pack/{topo.pack['id']}/explain",
                                headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert f'<code class="topo-ref" data-ref="{s3}"' in html
    assert f'href="#{topo.pack["id"]}-{s3}"' not in html
    assert "or the network around r1" in html


@pytest.mark.parametrize("ref", ["dev:@nowhere", "adj:ospf:{r2}~{r3}:10.255.3.0/24"])
def test_an_id_the_subgraph_does_not_hold_is_couldnt_analyse(topo, ref):
    """The second is in the model (r2's adjacency to r3) and not in r1's one-hop subgraph:
    the check is against what was sent, never the whole model."""
    ref = ref.format(r2=topo.ids["r2"], r3=topo.ids["r3"])
    if ref.startswith("adj:"):
        model, _e = NM.model_for("Lab")
        assert ref in model["adjacencies"]
    topo.answer = _citing(topo, [ref])
    got = _explain(topo)
    assert got["error"] == "couldnt_analyse", got
    assert "which is not in the pack or the topology sent" in got["detail"]


# ------------------------------------------------------------------------- off

def test_the_topology_class_off_sends_none_and_says_so(topo, monkeypatch):
    import os
    from html import unescape
    from modules import list_settings
    # The network's own settings file, beside its repository (the lab's folder).
    monkeypatch.setattr("modules.config.list_data_path",
                        lambda name: os.path.dirname(topo.lab["repo"]))
    assert list_settings.write("Lab", {"ai_topology_class": False},
                               actor="operator@example.com")["ok"]
    topo.answer = _answer(topo.pack)
    got = _explain(topo)
    assert got["ok"] is True
    body, user, ctx = _sent(topo)
    assert _blocks(user, "data") == ["pack", "the_alert"]
    assert _blocks(ctx, "context") == ["pack_format"]
    # Nothing of the network around it: the only device id sent is the alert's own device's,
    # in its own health figures' references (C1714; who is near it is topology).
    assert set(re.findall(r"dev:\d+", topo.sent[-1]["bytes"])) == {topo.ids["r1"]}
    assert "adj:" not in topo.sent[-1]["bytes"] and "cable:" not in topo.sent[-1]["bytes"]
    why = "the topology class is off for Lab (ai_topology_class, an admin's setting)"
    assert got["topology"] == dict(got["topology"], sent=False, why=why, devices=[])
    r = topo.lab["client"].post(f"/v2/monitoring/alerts/pack/{topo.pack['id']}/explain",
                                headers={"HX-Request": "true"})
    assert f"No topology was sent with the pack: {why}." in unescape(r.get_data(as_text=True))
    topo.answer = _citing(topo, [topo.ids["s3"]])
    assert _explain(topo)["error"] == "couldnt_analyse"


def test_an_unreadable_setting_is_off(topo, monkeypatch):
    from modules import list_settings

    def boom(*a, **k):
        raise list_settings.ListSettingsUnreadable("planted")
    monkeypatch.setattr(list_settings, "value", boom)
    topo.answer = _answer(topo.pack)
    got = _explain(topo)
    assert got["topology"]["sent"] is False and "could not be read" in got["topology"]["why"]
    assert _blocks(_sent(topo)[1], "data") == ["pack", "the_alert"]


def test_a_classification_marking_sends_nothing(topo, monkeypatch):
    from modules.ai import egress_classes
    monkeypatch.setattr(egress_classes, "classification_marking", lambda net: "restricted")
    got = _explain(topo)
    assert got["error"] == "classified" and topo.sent == []
    assert "forces AI off" in got["detail"]


def test_a_model_that_cannot_be_built_is_said_in_the_call(topo, monkeypatch):
    monkeypatch.setattr(NM, "model_for", lambda net: (None, "planted failure"))
    topo.answer = _answer(topo.pack)
    got = _explain(topo)
    _b, user, ctx = _sent(topo)
    assert _block(user, "data", "network_topology") == \
        "could not read: the network model (planted failure)"
    assert _blocks(ctx, "context") == ["pack_format"]
    assert got["topology"]["sent"] is False
    assert "planted failure" in got["topology"]["why"]


def test_the_observed_read_time_rides_with_each_item(topo):
    topo.answer = _answer(topo.pack)
    _explain(topo)
    sub = yaml.safe_load(_block(_sent(topo)[1], "data", "network_topology"))
    observed = [a["observed"] for a in sub["adjacencies"].values()]
    assert observed and all(o["read_at"] == READ_AT for o in observed if isinstance(o, dict))
