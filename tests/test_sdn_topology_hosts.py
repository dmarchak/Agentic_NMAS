"""A controller's hosts on Topology: one per MAC on its switch port, and only on a switch the
read still has (C1991, C2026; board F revised 2026-10-28), no network.

The controller's answers are REAL: Ryu 4.34's topology REST read 2026-10-27
(tests/fixtures/sdn/ryu/topology_rest.json: two switches, their link, six hosts, each holding
IPv4 beside IPv6 or only a link-local IPv6 address). Two cases are minimal edits of it, said where
they are made: the teardown C2026 measured on the host (2026-10-28 01:03 UTC: switches 0, links
0, the same six hosts still listed), as the capture with its switch and link answers emptied; and
one MAC listed on two ports, as the capture with one host's entry copied onto the other switch.
Every expected value is read off the capture by hand.

- **C1991:** a host is one node per MAC on its switch port, holding every address; labelled by
  its global IPv4 address, else its global IPv6, else "host on <switch> port <n>", never a
  link-local address; its card lists the MAC and every address, link-local marked; the same MAC
  on two ports is two nodes, each saying where else; the header counts hosts, never addresses;
  Path and what-if never offer a host; the Devices list groups hosts under their switch, closed.
- **C2026:** a host is drawn and located only when its switch is in the same read; the rest are
  counted in words ("6 hosts reported by c1 on switches no longer connected, not drawn"); the
  controller is a node with its state and switch count ("connected, 0 switches") and Mercury is
  drawn reading it; no analysis names an undrawn host.
"""
import copy
import json
import os
import re

from modules.readers import topology_graph as T
from modules.sdn import topology as SDN
from tests.test_sdn_topology import BASE, TOPO, _driver, _graph
from tests.test_sdn_topology import _controller as _plain_controller


def _controller(**kw):
    """The shared helper's controller entry, with the northbound address `stored` gives every
    entry (from the capture's base URL)."""
    return dict(_plain_controller(**kw), northbound=SDN.northbound(BASE))


def _edited(switches=None, links=None, hosts=None):
    """The capture with the named answers' bodies replaced (a minimal edit, said by its
    caller)."""
    out = copy.deepcopy(TOPO)
    for e in out:
        if e["path"] in ("/v1.0/topology/switches", "/stats/switches") and switches is not None:
            e["body"] = json.dumps(switches)
        elif e["path"] == "/v1.0/topology/links" and links is not None:
            e["body"] = json.dumps(links)
        elif e["path"] == "/v1.0/topology/hosts" and hosts is not None:
            e["body"] = json.dumps(hosts)
    return out


def _hosts_answer():
    return json.loads(next(e["body"] for e in TOPO if e["path"] == "/v1.0/topology/hosts"))


def _topo(entries):
    got = _driver(entries).topology()
    assert got["ok"], got
    return got


def _teardown():
    """C2026's teardown: the capture with no switch and no link, the six hosts still listed."""
    return _controller(topo=_topo(_edited(switches=[], links=[])))


def _two_ports():
    """MAC 00:00:00:00:00:02, captured on s1 port 2, also listed on s2 port 3 (a minimal edit:
    its entry copied with the port of s2-eth3 from the capture's link)."""
    hosts = _hosts_answer()
    h2 = next(h for h in hosts if h["mac"] == "00:00:00:00:00:02")
    moved = dict(h2, port={"dpid": "0000000000000002", "port_no": "00000003",
                           "hw_addr": "e2:5e:9c:43:d8:97", "name": "s2-eth3"})
    return _controller(topo=_topo(_edited(hosts=hosts + [moved])))


def _host_nodes(g):
    return {k: v for k, v in g["nodes"].items() if k.startswith(SDN.HOST_PREFIX)}


# ───────────────────────────────────────────────────────────────────────────── C1991

def test_each_captured_host_is_one_node_holding_ipv4_beside_ipv6():
    g = _graph({"state": "read", "controllers": [_controller()]})
    hosts = _host_nodes(g)
    assert len(hosts) == 6 and g["sdn"]["hosts"] == 6
    h1 = hosts["host:00:00:00:00:00:01@0000000000000001/1"]["host"]
    assert h1["ipv4"] == ["192.0.2.1"]
    assert h1["ipv6"] == ["2001:db8:8::1", "fe80::200:ff:fe00:1"]
    assert h1["label"] == "192.0.2.1"
    # No address is a node of its own: no key names an address.
    assert not [k for k in hosts if "192.0.2." in k or "::" in k.split("@")[0][5:].replace(
        ":", "")]


def test_the_label_is_the_global_ipv4_else_the_global_ipv6_else_the_switch_port():
    h = {"mac": "00:00:00:00:00:04", "dpid": 2, "port_no": 2, "ipv4": ["192.0.2.4"],
         "ipv6": ["2001:db8:8::4", "fe80::200:ff:fe00:4"]}
    assert SDN.host_label(h, "s2") == "192.0.2.4"
    v6 = dict(h, ipv4=[])
    assert SDN.host_label(v6, "s2") == "2001:db8:8::4"
    v6_first_ll = dict(v6, ipv6=["fe80::200:ff:fe00:4", "2001:db8:8::4"])
    assert SDN.host_label(v6_first_ll, "s2") == "2001:db8:8::4"
    ll = dict(h, ipv4=["169.254.7.1"], ipv6=["fe80::200:ff:fe00:4"])
    assert SDN.host_label(ll, "s2") == "host on s2 port 2"
    assert SDN.host_label(ll) == "host on of:…0002 port 2"


def test_a_host_known_only_by_link_local_is_named_by_its_switch_port_in_the_capture():
    g = _graph({"state": "read", "controllers": [_controller()]})
    stale = _host_nodes(g)["host:12:da:aa:70:da:9f@0000000000000001/1"]["host"]
    assert stale["ipv6"] == ["fe80::10da:aaff:fe70:da9f"]
    assert stale["label"] == "host on of:…0001 port 1"
    from modules.topology_page import label
    assert label("host:12:da:aa:70:da:9f@0000000000000001/1", g["nodes"]) == \
        "host on of:…0001 port 1"


def test_the_card_lists_the_mac_and_every_address_link_local_marked():
    from modules.topology_page import host_lines
    g = _graph({"state": "read", "controllers": [_controller()]})
    h1 = _host_nodes(g)["host:00:00:00:00:00:01@0000000000000001/1"]["host"]
    assert host_lines(h1) == ["MAC 00:00:00:00:00:01", "IPv4 192.0.2.1",
                              "IPv6 2001:db8:8::1", "IPv6 fe80::200:ff:fe00:1 (link-local)"]


def test_the_same_mac_on_two_ports_is_two_nodes_each_saying_where_else():
    g = _graph({"state": "read", "controllers": [_two_ports()]})
    hosts = _host_nodes(g)
    twos = [v["host"] for v in hosts.values() if v["host"]["mac"] == "00:00:00:00:00:02"]
    assert len(twos) == 2, sorted(hosts)
    a, b = sorted(twos, key=lambda h: h["switch"])
    assert (a["switch"], a["port"], b["switch"], b["port"]) == (
        "of:0000000000000001", "port 2", "of:0000000000000002", "port 3")
    assert a["elsewhere"] == ["of:…0002 port 3"] and b["elsewhere"] == ["of:…0001 port 2"]
    assert a["ipv4"] == b["ipv4"] == ["192.0.2.2"] and "2001:db8:8::2" in b["ipv6"]
    assert len(hosts) == 7 and g["sdn"]["hosts"] == 7
    from modules.topology_page import host_lines
    assert "the same MAC is also listed on of:…0002 port 3" in host_lines(a)


def test_the_counts_are_hosts_never_addresses():
    (said,) = SDN.said([_controller()])
    addresses = sum(len(h["ipv4"]) + len(h["ipv6"]) for h in _controller()["hosts"])
    assert said["hosts"] == 6 and addresses == 14 and said["orphans"] == 0
    assert "2 switches, 1 link, 6 hosts" in SDN.words(said)


def test_path_and_what_if_offer_no_host_and_no_analysis_names_one():
    from modules import path_trace
    from modules.topology_page import what_if
    g = _graph({"state": "read", "controllers": [_controller()]})
    assert not [n for n in path_trace.sources(g["nodes"]) if n.startswith("host:")]
    an = g["analysis"]["physical"]
    named = {d for i in an["islands"] for d in i} | {s["device"] for s in an["spof"]} | \
        set(an["main"]) | {c["device"] for c in an.get("critical") or []}
    assert not [n for n in named if n.startswith(("host:", "ctl:", "@"))], named
    cut = what_if(g["layers"]["physical"], g["nodes"], "of:0000000000000001")
    assert not [n for n in cut["lost"] if n.startswith("host:")]


# ───────────────────────────────────────────────────────────────────────────── C2026

def test_after_a_teardown_no_host_is_drawn_and_the_six_are_counted_in_words():
    c = _teardown()
    assert c["switches"] == [] and len(c["hosts"]) == 6
    g = _graph({"state": "read", "controllers": [c]})
    assert _host_nodes(g) == {}
    assert g["sdn"]["hosts"] == 0 and g["sdn"]["orphans"] == {"c1": 6}
    (said,) = g["sdn"]["controllers"]
    assert said["hosts"] == 0 and said["orphans"] == 6
    assert SDN.orphan_words("c1", 6) == \
        "6 hosts reported by c1 on switches no longer connected, not drawn"
    assert SDN.orphan_words("c1", 1) == \
        "1 host reported by c1 on switches no longer connected, not drawn"
    assert SDN.orphan_words("c1", 0) == ""


def test_after_a_teardown_the_controller_is_a_node_with_zero_switches_and_mercury_reads_it():
    from modules.topology_page import controller_words
    g = _graph({"state": "read", "controllers": [_teardown()]})
    ctl = g["nodes"]["ctl:c1"]["controller"]
    assert ctl["switches"] == 0 and ctl["orphans"] == 6 and ctl["state"] == "read"
    assert controller_words(ctl) == "connected, 0 switches"
    nb = [l for l in g["layers"]["physical"] if l.get("kind") == "northbound"]
    assert [(l["a"], l["b"], l["overlay"]) for l in nb] == [(T.MANAGER, "ctl:c1", True)]
    assert g["nodes"][T.MANAGER]["manager"]


def test_a_switch_that_left_takes_its_hosts_and_their_endpoints_with_it():
    sw = json.loads(next(e["body"] for e in TOPO if e["path"] == "/v1.0/topology/switches"))
    only_s1 = [s for s in sw if s["dpid"] == "0000000000000001"]
    c = _controller(topo=_topo(_edited(switches=only_s1, links=[])))
    g = _graph({"state": "read", "controllers": [c]})
    hosts = _host_nodes(g)
    assert sorted(h["host"]["mac"] for h in hosts.values()) == \
        ["00:00:00:00:00:01", "00:00:00:00:00:02", "12:da:aa:70:da:9f"]
    assert g["sdn"]["orphans"] == {"c1": 3}
    located = SDN.endpoint_hosts([c])
    assert sorted(e["mac"] for e in located) == \
        ["00:00:00:00:00:01", "00:00:00:00:00:02", "12:da:aa:70:da:9f"]
    assert {a for e in located for a in e["addresses"]} >= {"192.0.2.1", "2001:db8:8::1"}
    assert not SDN.endpoint_hosts([_teardown()])


def test_the_northbound_address_is_host_and_port_never_credentials_ipv6_bracketed():
    assert SDN.northbound("http://127.0.0.1:8080") == "127.0.0.1:8080"
    assert SDN.northbound("http://[2001:db8::5]:8181/onos/v1") == "[2001:db8::5]:8181"
    assert SDN.northbound("https://admin:secret@192.0.2.5/") == "192.0.2.5"
    assert SDN.northbound("") == "" and SDN.northbound("not a url") == ""


def test_link_local_and_unspecified_are_never_global_in_either_family():
    assert SDN.is_global("192.0.2.1") and SDN.is_global("2001:db8:8::1")
    for a in ("fe80::200:ff:fe00:1", "169.254.1.1", "::", "0.0.0.0", "::1", "127.0.0.1",
              "ff02::1", "224.0.0.5", "nonsense"):
        assert not SDN.is_global(a), a


# ───────────────────────────────────────────────────────────────────────────── the view

def _web(tmp_path, monkeypatch, controllers):
    from tests.test_topology_v2 import _store
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.topology_expected._path",
                        lambda name: str(tmp_path / "lab" / "topology_expected.json"))
    _store(sdn_value(controllers))


def sdn_value(controllers):
    """The Topology reader's value for Lab from the real captures (tests/test_topology_v2.py's
    `_value`), r6's LLDP neighbour named by Ryu's own chassis id, with *controllers* as the
    network's controller layer (tests/v2_context.py's `_topology_sdn` draws it too)."""
    from tests.test_sdn_topology import LLDP, _r6_facing
    from tests.test_topology_graph import MANAGED, _capture, _intents
    from tests.test_topology_v2 import _value
    frame = LLDP["frames"][0]
    raw = bytes.fromhex(frame["port_id_hex"]).decode("latin-1")
    res, up = _capture()
    res.setdefault("r6", {}).update(_r6_facing(frame["chassis_id"], raw))
    value = _value(results=res, up=up)
    intents = {h: hv for h, hv in _intents().items() if h != "r5"}
    value["networks"]["Lab"] = T.network_graph(
        MANAGED, {h: ("router" if h.startswith("r") else "switch") for h in MANAGED}, intents,
        res, up, now="2026-10-10T19:00:00Z", at_here=[],
        sdn={"state": "read", "controllers": controllers})
    return value


def _page(query=""):
    import app as A
    from modules import reader_job
    try:
        return A.app.test_client().get(f"/v2/topology/map?list=Lab{query}").get_data(
            as_text=True)
    finally:
        os.remove(reader_job.store_path("topology-graph"))


def test_the_page_names_hosts_by_address_counts_them_and_groups_them_closed(tmp_path,
                                                                            monkeypatch):
    _web(tmp_path, monkeypatch, [_controller()])
    html = _page("&tab=dev")
    head = re.search(r'<span class="topo-sub">(.*?)</span>', html, re.S).group(1)
    assert "2 switches, 6 hosts" in head
    names = re.findall(r'<text class="topo-name"[^>]*>([^<]*)</text>', html)
    assert {"192.0.2.1", "192.0.2.2", "192.0.2.3", "192.0.2.4", "host on of:…0001 port 1",
            "host on of:…0002 port 1"} <= set(names)
    assert not [n for n in names if n.startswith("fe80")]
    assert "IPv6 fe80::200:ff:fe00:1 (link-local)" in html and "IPv6 2001:db8:8::1" in html
    groups = re.findall(r'<details class="topo-hostsw" data-keep="[^"]+"( open)?><summary class="small">([^<]*)'
                        r'</summary>', html)
    assert groups == [("", "of:…0001 · 3 hosts"), ("", "of:…0002 · 3 hosts")]
    assert "port 1 · MAC 00:00:00:00:00:01 · 3 addresses" in html
    assert "Hosts a controller learned (6) on 2 switches" in html
    assert re.search(r'<text class="topo-sdnline"[^>]*>connected, 2 switches</text>', html)


def test_the_page_after_a_teardown_draws_the_controller_and_the_count_never_a_host(
        tmp_path, monkeypatch):
    _web(tmp_path, monkeypatch, [_teardown()])
    html = _page("&labels=on")
    assert 'data-node="ctl:c1"' in html and f'data-node="{T.MANAGER}"' in html
    assert re.search(r'<text class="topo-sdnline"[^>]*>connected, 0 switches</text>', html)
    assert 'data-node="host:' not in html
    strip = re.search(r'<div class="topo-cov small".*?</div>', html, re.S).group(0)
    assert "6 hosts reported by c1 on switches no longer connected, not drawn" in strip
    assert "0 switches, 0 links, 0 hosts" in strip
    head = re.search(r'<span class="topo-sub">(.*?)</span>', html, re.S).group(1)
    assert "0 switches, 0 hosts" in head
    assert "reads c1 over its northbound API at 127.0.0.1:8080" in html
    assert re.search(r'<text class="topo-st-t topo-st-src"[^>]*>northbound REST</text>', html)
    assert re.search(r'class="topo-line topo-ok topo-ov topo-ov-northbound"', html)
