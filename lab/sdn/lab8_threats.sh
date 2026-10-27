#!/usr/bin/env bash
# Lab 8's three threats, and the traffic that measures the pairs a response must leave alone
# (lab environment, not product: PHASE8_PLAN 17.1, C1837).
#
# Run as root on the Mininet VM while `lab8_topology.py --hold FILE` holds the network up; every
# command runs inside a Mininet host's own network namespace (`mnexec -a <pid>`), so the traffic
# stays between Mininet's hosts and reaches nothing outside Mininet.
#
#   sudo lab8_threats.sh scan     [FILE]   h1 SYN-scans h3 over many TCP ports (hping3)
#   sudo lab8_threats.sh flood    [FILE]   h2 floods h4 with UDP (iperf), FLOOD_SECONDS long
#   sudo lab8_threats.sh redirect [FILE]   an unauthorised flow on s2: h3's IPv4 traffic sent to
#                                          h4's port, with a cookie neither Mercury's nor the
#                                          controller application's (ovs-ofctl add-flow)
#   sudo lab8_threats.sh unredirect [FILE] removes that flow by its cookie (the lab's own undo)
#   sudo lab8_threats.sh pair A B [FILE]   legitimate traffic A -> B: ping (IPv4 and IPv6) and an
#                                          iperf TCP run, each figure printed
#
# FILE is what lab8_topology.py wrote (default /tmp/lab8.json). The knobs, each with its default:
# SCAN_COUNT=300 probes, SCAN_GAP_US=20000 between them (50 a second); FLOOD_SECONDS=60,
# FLOOD_RATE=20M; REDIRECT_COOKIE=0xbad0, REDIRECT_PRIORITY=100; PAIR_SECONDS=5.
set -euo pipefail

what=${1:?usage: lab8_threats.sh scan|flood|redirect|unredirect|pair A B [FILE]}
shift
if [ "$what" = pair ]; then
    a=${1:?pair needs two hosts}; b=${2:?pair needs two hosts}; shift 2
fi
desc=${1:-/tmp/lab8.json}
[ -r "$desc" ] || { echo "lab8_threats: $desc is not readable: is lab8_topology.py --hold running?" >&2; exit 2; }

get() {  # get <python expression over d>
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "$desc" "$1"
}
pid() { get "d['hosts']['$1']['pid']"; }
ip4() { get "d['hosts']['$1']['ipv4'].split('/')[0]"; }
ip6() { get "d['hosts']['$1']['ipv6'].split('/')[0]"; }
port() { get "d['switches']['$1']['ports']['$2']"; }
in_host() { local h=$1; shift; mnexec -a "$(pid "$h")" "$@"; }
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

case "$what" in
scan)
    echo "$(stamp) scan: h1 -> h3 ($(ip4 h3)), ${SCAN_COUNT:-300} SYN probes to ports 1 and up, one every ${SCAN_GAP_US:-20000} us"
    in_host h1 hping3 -S -p ++1 -c "${SCAN_COUNT:-300}" -i "u${SCAN_GAP_US:-20000}" "$(ip4 h3)" 2>&1 | tail -4 || true
    echo "$(stamp) scan: done"
    ;;
flood)
    echo "$(stamp) flood: h2 -> h4 ($(ip4 h4)) UDP at ${FLOOD_RATE:-20M} for ${FLOOD_SECONDS:-60} s"
    in_host h4 iperf -s -u -p 5001 >/tmp/lab8-iperf-udp-server.log 2>&1 &
    server=$!
    sleep 1
    in_host h2 iperf -u -c "$(ip4 h4)" -p 5001 -b "${FLOOD_RATE:-20M}" -t "${FLOOD_SECONDS:-60}" -i 10 2>&1 || true
    kill "$server" 2>/dev/null || true
    wait "$server" 2>/dev/null || true
    echo "$(stamp) flood: done; the server's report:"
    tail -4 /tmp/lab8-iperf-udp-server.log || true
    ;;
redirect)
    out=$(port s2 h4)
    echo "$(stamp) redirect: on s2, cookie ${REDIRECT_COOKIE:-0xbad0}, priority ${REDIRECT_PRIORITY:-100}: IPv4 to h3 ($(ip4 h3)) sent out port $out (h4's)"
    ovs-ofctl -O OpenFlow13 add-flow s2 "cookie=${REDIRECT_COOKIE:-0xbad0},table=0,priority=${REDIRECT_PRIORITY:-100},ip,nw_dst=$(ip4 h3),actions=output:$out"
    ovs-ofctl -O OpenFlow13 dump-flows s2 "cookie=${REDIRECT_COOKIE:-0xbad0}/-1"
    ;;
unredirect)
    echo "$(stamp) unredirect: removing cookie ${REDIRECT_COOKIE:-0xbad0} from s2"
    ovs-ofctl -O OpenFlow13 del-flows s2 "cookie=${REDIRECT_COOKIE:-0xbad0}/-1"
    ;;
pair)
    echo "$(stamp) pair $a -> $b: ping IPv4 ($(ip4 "$b"))"
    in_host "$a" ping -c 5 -i 0.2 -W 1 "$(ip4 "$b")" 2>&1 | tail -2 || true
    echo "$(stamp) pair $a -> $b: ping IPv6 ($(ip6 "$b"))"
    in_host "$a" ping -6 -c 5 -i 0.2 -W 1 "$(ip6 "$b")" 2>&1 | tail -2 || true
    echo "$(stamp) pair $a -> $b: iperf TCP for ${PAIR_SECONDS:-5} s"
    in_host "$b" iperf -s -p 5002 >/tmp/lab8-iperf-tcp-server.log 2>&1 &
    server=$!
    sleep 1
    in_host "$a" timeout $(( ${PAIR_SECONDS:-5} + 10 )) iperf -c "$(ip4 "$b")" -p 5002 -t "${PAIR_SECONDS:-5}" 2>&1 | tail -1 || true
    kill "$server" 2>/dev/null || true
    wait "$server" 2>/dev/null || true
    ;;
*)
    echo "lab8_threats: $what is not one of scan, flood, redirect, unredirect, pair" >&2
    exit 2
    ;;
esac
