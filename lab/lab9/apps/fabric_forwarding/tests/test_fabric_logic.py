"""fabric_logic over plain data: the topology, the flows each switch should hold, loop safety,
and reconcile (the module's docstring). Plain functions and asserts, Python 3.5 and Mercury's
alike. The ring is the one Ryu recorded (tests/test_fabric_paths.py says where); addresses are
documentation ones, an IPv4 and an IPv6 host side by side.
"""

try:
    from mercury_app.testing import covers
except ImportError:                     # run with no SDK on the path (the app gate reads the import)
    def covers(*_names):
        return lambda test: test

import fabric_logic as L

S3, S4 = 3, 4
ARISTA_A, ARISTA_C, PROCURVE = 2214744208935, 2843895626628, 56298109234905574
SWITCHES = (S3, S4, ARISTA_A, ARISTA_C, PROCURVE)
RECORDED = [(S4, 3, PROCURVE, 3), (S3, 2, S4, 2), (ARISTA_A, 19, PROCURVE, 2),
            (ARISTA_A, 18, S3, 1), (ARISTA_C, 18, S4, 1)]
H3, H4 = "192.0.2.13", "2001:db8::14"
HOSTS = {H3: (S3, 5), H4: (S4, 5)}
#: Mercury's compile for the ring: the ProCurve's tables 100 and 200 (C2601), table 0 elsewhere.
CONFIG = L.parse_config({"switches": {str(PROCURVE): {"forward_table": 100, "punt_table": 200}},
                         "default_tables": {"forward_table": 0, "punt_table": 0}})[0]


def links(without=()):
    out = set()
    for (a, pa, b, pb) in RECORDED:
        if (a, b) not in without and (b, a) not in without:
            out.add((a, pa, b, pb))
            out.add((b, pb, a, pa))
    return out


def up_ports():
    out = dict((d, set([5])) for d in SWITCHES)
    for (a, pa, _b, _pb) in links():
        out[a].add(pa)
    return out


def graph(without=()):
    return L.graph_of(links(without), up_ports(), SWITCHES)


def host_out(flows, dpid, address):
    """The port *dpid*'s flow for *address* outputs to, or None."""
    for key, (actions, _cookie) in flows[dpid].items():
        if dict(key[2]).get("ipv4_dst", dict(key[2]).get("ipv6_dst")) == address:
            return actions[0][1]
    return None


@covers("a host is reached on the shortest path of the recorded ring")
def test_each_switch_forwards_toward_the_host_by_its_next_hop():
    flows, problems = L.desired_flows(CONFIG, graph(), HOSTS)
    assert problems == []
    assert host_out(flows, S3, H3) == 5 and host_out(flows, S4, H4) == 5
    assert host_out(flows, S3, H4) == 2 and host_out(flows, S4, H3) == 2
    assert host_out(flows, ARISTA_C, H3) == 18          # to 4, then the link to 3
    deliver = [k for k, (_a, c) in flows[S4].items() if L.kind_of(c) == L.DELIVER]
    assert deliver == [(0, 100, (("eth_type", L.ETH_IPV6), ("ipv6_dst", H4)))]


@covers("a ring link going down reroutes the other way round")
def test_a_link_down_reroutes_round_the_ring_and_nothing_loops():
    before, _ = L.desired_flows(CONFIG, graph(), HOSTS)
    after, problems = L.desired_flows(CONFIG, graph(without=[(S3, S4)]), HOSTS)
    assert problems == []
    assert host_out(after, S3, H4) == 1                 # to Arista A
    assert host_out(after, ARISTA_A, H4) == 19          # to the ProCurve
    assert host_out(after, PROCURVE, H4) == 3           # to 4
    # A reroute overwrites: the same keys, new actions, so nothing is removed first.
    assert sorted(before[S3]) == sorted(after[S3])
    hops, _ = L.next_hops(graph(without=[(S3, S4)]), S4)
    assert L.forwarding_loop(hops, S4) is None


def test_the_procurve_gets_its_own_tables_and_a_goto_for_the_hardware_tables_miss():
    flows, _ = L.desired_flows(CONFIG, graph(), HOSTS)
    keys = sorted(flows[PROCURVE])
    assert (200, 0, ()) in keys and (200, 10, (("eth_type", L.ETH_ARP),)) in keys
    assert flows[PROCURVE][(100, 0, (("eth_type", L.ETH_IPV4),))][0] == (("GOTO", 200),)
    assert flows[PROCURVE][(100, 0, (("eth_type", L.ETH_IPV6),))][0] == (("GOTO", 200),)
    assert all(k[0] == 100 for k, (_a, c) in flows[PROCURVE].items()
               if L.kind_of(c) in (L.DELIVER, L.TRANSIT))
    assert not [k for k in flows[S3] if k[0] != 0]
    assert not [k for k, (_a, c) in flows[S3].items() if L.kind_of(c) == L.GOTO]


def test_nothing_floods_and_the_relay_leaves_only_by_edge_ports():
    flows, _ = L.desired_flows(CONFIG, graph(), HOSTS)
    for dpid in flows:
        for _key, (actions, _cookie) in flows[dpid].items():
            assert all(a[0] in ("OUTPUT", "GOTO", "CONTROLLER") for a in actions), actions
    since = dict(((d, p), 0.0) for d, ports in up_ports().items() for p in ports)
    edges = L.edge_ports(up_ports(), links(), since, 10.0, 3.0)
    assert edges[S3] == [5] and edges[ARISTA_A] == [5]
    # A port up for less than the settle time is not an edge yet.
    since[(S3, 5)] = 9.0
    assert L.edge_ports(up_ports(), links(), since, 10.0, 3.0)[S3] == []
    # A link one end alone reported still keeps both ports off the edge.
    one_way = set([(S3, 2, S4, 2)])
    assert 2 not in L.edge_ports({S3: set([2, 5])}, one_way, {}, 10.0, 0.0)[S3]


def test_a_one_way_or_down_link_is_no_part_of_the_graph():
    half = set([(S3, 2, S4, 2)])
    assert L.graph_of(half, {S3: set([2]), S4: set([2])}, [S3, S4]) == {S3: {}, S4: {}}
    both = links()
    ports = up_ports()
    ports[S4].discard(2)
    assert S4 not in L.graph_of(both, ports, SWITCHES)[S3]
    assert ARISTA_C not in L.graph_of(both, up_ports(), [S3, S4])


def test_a_looping_or_wrong_path_answer_is_refused_by_name():
    assert L.forwarding_loop({1: (2, 1), 2: (3, 1), 3: (1, 1)}, 9) == [1, 2, 3, 1]

    def wrong(_graph, src, dst):
        return [src, 99, dst]
    hops, problems = L.next_hops(graph(), S4, path=wrong)
    assert hops == {} and len(problems) == len(SWITCHES) - 1
    assert "not a simple path" in problems[0]


@covers("reconcile changes only the app's own flows")
def test_reconcile_adds_the_missing_removes_its_own_stale_and_leaves_another_owners():
    desired = L.desired_flows(CONFIG, graph(), HOSTS)[0][S3]
    right = [k + v for k, v in sorted(desired.items())
             if L.kind_of(v[1]) in (L.MISS, L.DELIVER)]
    stale = (0, 100, (("eth_type", L.ETH_IPV4), ("ipv4_dst", "192.0.2.99")),
             (("OUTPUT", 7),), L.cookie(L.TRANSIT))
    arp_key = (0, 10, (("eth_type", L.ETH_ARP),))
    foreign = arp_key + ((("OUTPUT", 9),), 0x1)
    lldp = (0, 65535, (("eth_dst", "01:80:c2:00:00:0e"), ("eth_type", L.ETH_LLDP)),
            (L.CONTROLLER,), 0x0)
    got = L.difference(desired, right + [stale, foreign, lldp])
    assert got["kept"] == len(right)
    assert [d[0] for d in got["delete"]] == [stale[:3]]
    added = [a[0] for a in got["add"]]
    assert arp_key not in added and len(got["conflicts"]) == 1
    assert "another owner's" in got["conflicts"][0]
    assert sorted(added + [k[:3] for k in right] + [arp_key]) == sorted(desired)
    # Reconciled once, the second pass sends nothing.
    after = right + [a[0] + (a[1], a[2]) for a in got["add"]] + [foreign, lldp]
    again = L.difference(desired, after)
    assert again["add"] == [] and again["delete"] == [] and again["kept"] == len(desired) - 1


def test_the_hosts_are_rebuilt_from_the_switches_own_deliver_flows():
    flows, _ = L.desired_flows(CONFIG, graph(), HOSTS)
    current = [k + v for k, v in flows[S4].items()]
    assert L.hosts_from_flows(S4, current) == {H4: (S4, 5)}
    foreign = [(0, 100, (("eth_type", L.ETH_IPV4), ("ipv4_dst", H3)), (("OUTPUT", 5),), 0x1)]
    assert L.hosts_from_flows(S4, foreign) == {}


def test_a_frame_is_relayed_once_within_the_window():
    recent = L.Recent(0.5)
    assert not recent.seen("a", 0.0)
    assert recent.seen("a", 0.2)
    assert not recent.seen("b", 0.2)
    assert not recent.seen("a", 0.8)


def test_addresses_ipv4_and_ipv6_and_what_is_not_a_host():
    assert L.address_match("192.0.2.1") == ("ipv4_dst", L.ETH_IPV4, "192.0.2.1")
    assert L.address_match("2001:DB8:0::1") == ("ipv6_dst", L.ETH_IPV6, "2001:db8::1")
    for text in ("255.255.255.255", "0.0.0.0", "::", "ff02::1", "224.0.0.1", "127.0.0.1",
                 "not an address"):
        assert L.address_match(text) is None, text


def test_the_config_refuses_each_field_by_name_and_serves_only_what_it_names():
    config, problems = L.parse_config({"switches": {"3": {"forward_table": 0,
                                                          "punt_table": 0}}})
    assert problems == [] and L.tables_for(config, 3) == (0, 0)
    assert L.tables_for(config, 4) is None and L.tables_for(None, 3) is None
    config, problems = L.parse_config({"switches": {"x": {}, "4": {"forward_table": 300,
                                                                    "punt_table": 0}},
                                       "settle_s": -1, "other": 1})
    assert config is None
    words = " | ".join(problems)
    for part in ("'other'", "switches: 'x'", "switches.4.forward_table", "settle_s"):
        assert part in words, part


def test_the_start_time_config_is_taken_at_load_and_one_not_read_is_named():
    config, why = L.from_start_config({"ok": True, "path": "/a/0.2.0.config.json", "config": {
        "switches": {str(PROCURVE): {"forward_table": 100, "punt_table": 200}}}})
    assert why == "" and L.tables_for(config, PROCURVE) == (100, 200)
    config, why = L.from_start_config({"ok": False, "error": "no start-time config at /a"})
    assert config is None
    assert why == "its start-time config was not read: no start-time config at /a"
    assert L.from_start_config(None) == (None, L.NO_SDK)
    config, why = L.from_start_config({"ok": True, "path": "/a",
                                       "config": {"switches": {"x": {}}}})
    assert config is None
    assert why.startswith("its start-time config /a is refused: switches: 'x'")
