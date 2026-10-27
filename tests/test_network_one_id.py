"""One network, one id, on every read path (C1903, the operator's design of 2026-10-27).

The defect, measured on the host: `network_model.model_for` built the same model for
``Default`` and ``default``, but `network_model.observed` found the Topology reader's read only
under ``Default`` (the key it was written under) and said "holds nothing for default", so a
caller holding the id lost every observed link and said so only in a `said` line.

The design: a network has one canonical id (its lower-case slug), separate from its display
name; every lookup goes through one resolver (`listref.network_id`, and `listref.keyed` over a
stored map) that takes either spelling and raises for a name no network answers to.

Each read path is given ``Default``, ``default`` and ``nosuch``, on a network registered as
``Default`` (the lab's), with the Topology read stored as the host holds it today (keyed by the
display name, written by the release before this one) and as this release writes it (keyed by
the id): the first two give identical data, and the third an error naming it, never an empty
answer. The paths: the resolver and the stored-map lookup, the Topology reader's own lookup
and its write, the network model (`model_for`, `observed`, `capture`, `context_for`), feature
7's neighbours (`intent_names.neighbours_of`), the endpoint store, an evidence pack's concurrent
alerts (an IPv6 address among them), Topology's page, the pack replay's observed read, and the
evaluation runners' network (`cases.run_network`). The case fixtures carry the id.
"""

import json
import os

import pytest

from modules import network_model as NM
from modules.nsot import listref
from tests import test_topology_graph as TG
from tests.test_device_v2 import _store, _unstore, lab  # noqa: F401 (the fixture `net` uses)
from tests.test_network_model import NOW, READ_AT, net  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPELLINGS = ("Default", "default")
UNKNOWN = "nosuch"
#: The endpoint store's read for the network: one host by IPv4 and IPv6 on s1.
ENDPOINTS = {"endpoints": [{"mac": "02:00:00:00:00:50", "addresses": ["192.0.2.50",
                                                                       "2001:db8::50"],
                            "hostname": "h1", "device": "s1", "interface": "GigabitEthernet1/0",
                            "vlan": "10", "last_seen": READ_AT}],
             "read_at": READ_AT, "devices": {"s1": {"error": "", "not_supported": []}}}


class Said(Exception):
    """A path that answers an error rather than raising it, its error raised here."""


def _registered(tmp_path, monkeypatch, others=None):
    registry = tmp_path / "device_lists_c1903.json"
    registry.write_text(json.dumps({"current_list": "Default",
                                    "lists": dict({"Default": "default"}, **(others or {}))}),
                        encoding="utf-8")
    monkeypatch.setattr("modules.device.DEVICE_LISTS_CONFIG", str(registry))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Default")


def _store_topology(key):
    _store(NM.OBSERVED_READER, {"configured": True, "networks": {key: TG._graph()},
                                "read_at": READ_AT}, at=READ_AT)


@pytest.fixture(params=["Default", "default"], ids=["stored-by-name", "stored-by-id"])
def default_net(net, tmp_path, monkeypatch, request):  # noqa: F811
    """test_network_model's lab registered as ``Default``, the Topology read and the endpoint
    read stored under *param*: the display name (as the host holds them today) or the id (as
    this release writes the Topology read)."""
    _registered(tmp_path, monkeypatch)
    _store_topology(request.param)
    _store("endpoints", {"lists": {request.param: ENDPOINTS}}, at=READ_AT)
    NM.forget()
    yield net
    NM.forget()
    _unstore("endpoints")


def _model(network):
    model, err = NM.model_for(network)
    if model is None:
        raise Said(err)
    return model


def _answered(got):
    if not got.get("ok"):
        raise Said(got.get("error"))
    return got


def _observed(network):
    return NM.observed(network, _model("Default"), now=NOW)


def _concurrent(network):
    from modules import alert_history as AH
    from modules import evidence_pack as EP

    at = AH.epoch(READ_AT)
    rows = [AH._row("grafana-alerts", ["Default"], "Device unreachable (SNMP)", "Alerting",
                    {"alertname": "Device unreachable (SNMP)", "device": "r3",
                     "instance": "192.0.2.43"}, at - 300, "backfill"),
            AH._row("grafana-alerts", ["Default"], "Interface output discards", "Alerting",
                    {"alertname": "Interface output discards", "instance": "2001:db8::77"},
                    at - 240, "backfill"),
            AH._row("grafana-alerts", ["Other"], "Device unreachable (SNMP)", "Alerting",
                    {"alertname": "Device unreachable (SNMP)", "device": "r2"}, at - 200,
                    "backfill")]
    return EP.concurrent_section(network, "grafana-alerts", "another alert", at - 60, at, at,
                                 rows=rows)


def _page(network):
    from modules import topology_page
    return {k: v for k, v in topology_page.view(network, {}).items() if not callable(v)}


def _replayed(network):
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader(
        "nmas_pack_replay_c1903", os.path.join(ROOT, "scripts", "nmas-pack-replay"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    res, up = TG._capture()
    return mod.observed_then(network, NOW, source=lambda: (True, res, up))


def _runner(network):
    from modules.ai import cases
    name, refusal = cases.run_network(network, "default")
    if refusal:
        raise Said(refusal)
    return name


def _network_of(network):
    from modules import topology_page
    from modules.readers.topology_graph import network_of
    return network_of(topology_page.stored()["value"], network)


def _neighbours(network):
    from modules.ai import intent_names
    return intent_names.neighbours_of(network, "s1")


def _endpoints(network):
    from modules import endpoints
    return endpoints.stored(network)


def _observed_port(got):
    return any(p["by"].startswith("observed") for ps in got["ports"].values() for p in ps)


#: Each read path: (name, ``path(network) -> data``, ``held(data)``: the data is the network's,
#: read, not an empty answer that two spellings could share), raising for a name no network has.
PATHS = [
    ("network_id", listref.network_id, lambda d: d == "default"),
    ("keyed", lambda n: listref.keyed({"Default": 1, "Other": 2}, n), lambda d: d == 1),
    ("topology_graph.network_of", _network_of, lambda d: bool((d or {}).get("nodes"))),
    ("network_model.model_for", lambda n: _model(n)["version"], lambda d: bool(d.get("key"))),
    ("network_model.observed", _observed, lambda d: d["state"] == "read" and bool(d["cables"])),
    ("network_model.capture", lambda n: _answered(NM.capture(n, "s1", now=NOW)),
     lambda d: d["overlay"]["state"] == "read" and bool(d["overlay"]["cables"])),
    ("network_model.context_for",
     lambda n: _answered(NM.context_for(n, "s1", overlay=_observed("Default"))),
     lambda d: d["observed"] == "read" and "dev:104" in d["reached"]),
    ("intent_names.neighbours_of", _neighbours, _observed_port),
    ("endpoints.stored", _endpoints, lambda d: d["state"] == "read" and bool(d["endpoints"])),
    # Default's two alerts, one by its IPv6 address; the other network's left out.
    ("evidence_pack.concurrent_section", _concurrent, lambda d: len(d["pieces"]) == 2),
    ("topology_page.view", _page, lambda d: d["state"] == "ok"),
    ("nmas-pack-replay observed_then", _replayed,
     lambda d: bool(d["value"]["networks"])),
    ("cases.run_network", _runner, lambda d: d == "Default"),
]


@pytest.mark.parametrize("path,held", [(p, h) for _n, p, h in PATHS],
                         ids=[n for n, _p, _h in PATHS])
def test_each_read_path_gives_both_spellings_the_same_data_and_an_unknown_name_an_error(
        default_net, path, held):
    """Purpose: the operator's test. ``Default`` and ``default`` read identical data on every
    path, whichever key the stored reads are under, and it is the network's data, read;
    ``nosuch`` is an error naming it."""
    first, second = (path(n) for n in SPELLINGS)
    assert first == second
    assert held(first), first
    with pytest.raises((listref.UnknownList, Said), match=UNKNOWN):
        path(UNKNOWN)


def test_the_id_reads_every_observed_link_the_defect_lost(default_net):
    """Purpose: C1903's measurement, as a test. Asked by the id, the observed overlay is read
    (not "holds nothing for default"), with the physical links, and s1's neighbour s2 is
    observed by LLDP on GigabitEthernet0/3 (what feature 7's "the port to s2" resolves to)."""
    from modules.ai import intent_names

    obs = _observed("default")
    assert obs["state"] == "read", obs["why"]
    assert obs["cables"], "no observed link read under the id"
    ports = intent_names.neighbours_of("default", "s1")["ports"]
    assert any(p["name"] == "s2" and p["by"].startswith("observed")
               for p in ports.get("GigabitEthernet0/3", [])), ports


def test_the_topology_reader_writes_its_value_under_the_id(default_net):
    """Purpose: the writer's half. The Topology reader keys each network's graph by its one
    id, never its display name, so a later reader by either spelling finds the same graph."""
    got = _replayed("Default")["value"]
    assert set(got["networks"]) == {"default"}


def test_the_case_fixtures_carry_the_canonical_id(default_net):
    """Purpose: the fixture files carry the network's id. Every AI case file names its network
    in the id's form (its own slug: lower case, nothing a slug changes), every kind of case
    file among them; the lab's, ``default``, is what the resolver gives back for Default."""
    from modules.config import list_slug

    from tests.source_index import tracked

    here = os.path.join(ROOT, "tests", "fixtures", "ai_cases")
    files = [p for p in tracked(os.path.join("tests", "fixtures", "ai_cases"), suffix=".json")
             if os.path.basename(os.path.dirname(os.path.dirname(p))) == "ai_cases"]
    kinds, networks = set(), set()
    for path in files:
        with open(path, encoding="utf-8") as fh:
            network = json.load(fh).get("network")
        assert network, f"{path} names no network"
        assert network == list_slug(network), f"{path}: {network!r} is not in an id's form"
        kinds.add(os.path.basename(os.path.dirname(path)))
        networks.add(network)
    assert kinds == {d for d in os.listdir(here) if os.path.isdir(os.path.join(here, d))}
    assert len(kinds) >= 4, kinds
    assert "default" in networks and listref.network_id("Default") == "default"


def test_a_runner_refuses_a_case_file_of_another_network(default_net, tmp_path, monkeypatch):
    """Purpose: a recording runs one network. A case file naming another registered network
    than the one given is refused, naming both, before anything is read or asked."""
    from modules.ai import cases

    _registered(tmp_path, monkeypatch, {"Other": "other"})
    name, refusal = cases.run_network("Default", "other")
    assert name == "" and "'other'" in refusal and "'Default'" in refusal, refusal
    assert cases.run_network("Other", "other") == ("Other", "")
