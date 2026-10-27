#!/usr/bin/env python3
"""Lab 8's topology (lab environment, not product: PHASE8_PLAN 17.1, C1837).

Two OpenFlow 1.3 switches in series, two hosts on each:

    h1 --+            +-- h3
         s1 -------- s2
    h2 --+            +-- h4

Each host has an IPv4 address and an IPv6 address on one segment (`--ip-base`, `--ipv6-base`;
documentation prefixes by default, so nothing here is an address of the lab's own network).
The switches answer to a remote controller at `--controller-ip`, port `--controller-port`
(6653). No address of the controller is in this file: give it, or set `LAB8_CONTROLLER_IP`,
or let the script read the NMAS host's LAN address from the lab's hosts file
(`NMAS_LAB_HOSTS`, else `<repo>/data/lab_hosts.json`, the `nmas` entry's `lan`), read at run
time and never printed. No `--nat`: the hosts reach nothing outside Mininet.

Run it as root on the Mininet VM (`sudo mn -c` first):
- `sudo python3 lab8_topology.py` opens Mininet's CLI;
- `sudo python3 lab8_topology.py --hold /tmp/lab8.json` starts the network, writes each host's
  name, process id and addresses to that file (what `lab8_threats.sh` reads), and holds the
  network up until it is sent SIGTERM or SIGINT, then stops it.
"""

import argparse
import ipaddress
import json
import os
import signal
import sys
import threading

HOSTS = (("h1", "s1"), ("h2", "s1"), ("h3", "s2"), ("h4", "s2"))
DEFAULT_IP_BASE = "192.0.2.0/24"
DEFAULT_IPV6_BASE = "2001:db8:8::/64"


def controller_ip(given: str) -> str:
    """The controller's address: the argument, the environment, or the lab's hosts file."""
    if given:
        return given
    if os.environ.get("LAB8_CONTROLLER_IP"):
        return os.environ["LAB8_CONTROLLER_IP"]
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.environ.get("NMAS_LAB_HOSTS") or os.path.join(here, "..", "..", "data",
                                                            "lab_hosts.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["nmas"]["lan"]
    except (OSError, ValueError, KeyError, TypeError):
        sys.exit("lab8_topology: no controller address: give --controller-ip, set "
                 "LAB8_CONTROLLER_IP, or provide the lab's hosts file (NMAS_LAB_HOSTS)")


def addresses(ip_base: str, ipv6_base: str) -> dict:
    """Each host's IPv4 and IPv6 address with its prefix length: h<n> gets host n."""
    v4, v6 = ipaddress.ip_network(ip_base), ipaddress.ip_network(ipv6_base)
    return {name: {"ipv4": f"{v4.network_address + n}/{v4.prefixlen}",
                   "ipv6": f"{v6.network_address + n}/{v6.prefixlen}"}
            for n, (name, _sw) in enumerate(HOSTS, start=1)}


def build(args):
    from mininet.net import Mininet
    from mininet.node import OVSSwitch, RemoteController

    addr = addresses(args.ip_base, args.ipv6_base)
    net = Mininet(controller=None, switch=OVSSwitch, autoSetMacs=True, build=False)
    net.addController("c0", controller=RemoteController, ip=controller_ip(args.controller_ip),
                      port=args.controller_port)
    s1 = net.addSwitch("s1", protocols="OpenFlow13", dpid="0000000000000001")
    s2 = net.addSwitch("s2", protocols="OpenFlow13", dpid="0000000000000002")
    switches = {"s1": s1, "s2": s2}
    for name, sw in HOSTS:
        host = net.addHost(name, ip=addr[name]["ipv4"])
        net.addLink(host, switches[sw])
    net.addLink(s1, s2)
    net.build()
    net.start()
    for name, _sw in HOSTS:
        host = net.get(name)
        host.cmd(f"ip -6 addr add {addr[name]['ipv6']} dev {name}-eth0 nodad")
    return net, addr


def described(net, addr) -> dict:
    """What `lab8_threats.sh` reads: each host's process id, interface and addresses, and each
    switch's ports by the host or switch on their far end."""
    out = {"hosts": {}, "switches": {}}
    for name, _sw in HOSTS:
        host = net.get(name)
        out["hosts"][name] = {"pid": host.pid, "intf": f"{name}-eth0",
                              "mac": host.MAC(), **addr[name]}
    for sw in ("s1", "s2"):
        node = net.get(sw)
        ports = {}
        for intf in node.intfList():
            if intf.link is None:
                continue
            far = intf.link.intf1 if intf.link.intf2 == intf else intf.link.intf2
            ports[far.node.name] = node.ports[intf]
        out["switches"][sw] = {"dpid": node.dpid, "ports": ports}
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--controller-ip", default="")
    parser.add_argument("--controller-port", type=int, default=6653)
    parser.add_argument("--ip-base", default=DEFAULT_IP_BASE)
    parser.add_argument("--ipv6-base", default=DEFAULT_IPV6_BASE)
    parser.add_argument("--hold", metavar="FILE", default="",
                        help="write the hosts' description to FILE and hold the network up "
                             "until SIGTERM or SIGINT, instead of opening the CLI")
    args = parser.parse_args(argv)
    from mininet.log import setLogLevel

    setLogLevel("info")
    net, addr = build(args)
    try:
        if args.hold:
            with open(args.hold, "w", encoding="utf-8") as fh:
                json.dump(described(net, addr), fh, indent=2, sort_keys=True)
            done = threading.Event()
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *_a: done.set())
            print(f"lab8_topology: up; hosts described in {args.hold}; SIGTERM stops it",
                  flush=True)
            while not done.wait(1.0):
                pass
        else:
            from mininet.cli import CLI

            CLI(net)
    finally:
        net.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
