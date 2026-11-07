#!/usr/bin/env python3
"""fabric_forwarding's acceptance in the container harness (the SDN platform design revision 6,
section 15, S3's step 4, run on Open vSwitch instead of the ring's hardware; P7a). Test-only:
it drives the harness's own containers and nothing else, never a device.

    scripts/nmas-harness up --python 3.5 --apps lab/lab9/apps/fabric_forwarding
    python3 lab/lab9/fabric_forwarding_acceptance.py
    scripts/nmas-harness down

**The ring** is built in the running switch container beside the harness's own two bridges
(tests/containers/ovs/bridges.conf): four userspace bridges, br11 to br14 (datapath ids 0x11 to
0x14), each with one host port (OVS's dummy netdev, its sent frames captured to a pcap file in
the container's tmpfs) and two ring ports, each a dummy netdev joined to its neighbour's over a
unix stream socket (so a cable can be pulled: `CUT`). Frames are injected with
`ovs-appctl netdev-dummy/receive`; documentation addresses only (192.0.2.0/24, 2001:db8::/32,
02:00:... MACs).

**What it asserts, each with its number printed** (S3's step 4):
1. shortest path: IPv4 and IPv6 between hosts take the shortest way round the ring (a tie broken
   to the lower switch), read from the flows' own counters;
2. loop-safe: a burst of broadcasts reaches every other host port exactly once each, the
   controller relays each frame once, and no other ring switch's punt flows count a packet
   (the flooding counters stay flat);
3. reroute: a stream from h11 to h12 while the ring cable between them is pulled (its frames
   stop and both ends report LINK_DOWN); the frames lost and the outage, from the stream's own
   timestamps; then the cable put back and the path back on it;
4. reconcile: with Ryu stopped, one of the app's flows is deleted, a stale flow is planted under
   the app's cookie and another owner's flow is added; Ryu is started, the config pushed again
   (H's policy push), and the app's flows come back exactly as before, no key twice, the stale
   one gone, the app having sent exactly that difference (one added, one removed), and the
   other owner's flow and Ryu's own LLDP flow untouched.

Exits 0 when every assertion holds, 1 naming the first that does not.
"""

import json
import re
import struct
import subprocess
import sys
import time

PROJECT = "mercury-harness"
DB = "--db=unix:/run/openvswitch/db.sock"
RUN = "/run/openvswitch"
RING = (0x11, 0x12, 0x13, 0x14)
HOST_PORT, CLOCKWISE, ANTICLOCKWISE = 1, 2, 3
APP_COOKIE = 0x4646000000000000
COOKIE_MASK = 0xffff000000000000
FOREIGN_COOKIE = 0x99
#: The config H's policy push would send (Open vSwitch: table 0 for both).
CONFIG = {"default_tables": {"forward_table": 0, "punt_table": 0}}
#: Bounds, each about 2.5x what the harness measured (2026-11-07 runs of this script).
DISCOVERY_BOUND_S = 20.0        # the ring's links found and its edges settled: ~6 s measured
RECONNECT_BOUND_S = 30.0        # Ryu restarted to every bridge back: ~9 s (OVS's backoff)
STREAM = 2500                   # frames in the reroute stream: 1.3 to 2.3 ms each, measured
CUT_AFTER_S = 1.0               # the cable pulled this far into it
#: OVS's userspace datapath hands flow counters to OpenFlow at its revalidator's pass (500 ms by
#: default); a first run read 13 of 20 frames at once. 2.5x the pass, rounded up.
STATS_S = 1.5


class Failed(Exception):
    pass


def check(condition, words):
    if not condition:
        raise Failed(words)
    print("  PASS " + words)


def run(command, data=None, check_exit=True):
    got = subprocess.run(command, input=data, capture_output=True)
    if check_exit and got.returncode != 0:
        raise Failed("%s exited %d: %s" % (" ".join(command), got.returncode,
                                          got.stderr.decode(errors="replace").strip()[-600:]))
    return got


def container(service):
    got = run(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + PROJECT,
               "--filter", "label=com.docker.compose.service=" + service]).stdout.split()
    if len(got) != 1:
        raise Failed("expected one %s container in %s, found %d: is the harness up?"
                     % (service, PROJECT, len(got)))
    return got[0].decode()


OVS = RYU = None


def ovs(*args, **kw):
    return run(["docker", "exec", "-e", "OVS_RUNDIR=" + RUN, OVS] + list(args), **kw)


def vsctl(*args):
    return ovs("ovs-vsctl", DB, *args).stdout.decode()


def ofctl(*args):
    return ovs("ovs-ofctl", "-O", "OpenFlow13", *args).stdout.decode()


_REST = ("import sys, urllib.request as u, urllib.error as e\n"
         "body = sys.argv[3].encode() if len(sys.argv) > 3 else None\n"
         "r = u.Request('http://127.0.0.1:8080' + sys.argv[1], data=body, method=sys.argv[2])\n"
         "r.add_header('Content-Type', 'application/json')\n"
         "try:\n    print(u.urlopen(r, timeout=10).read().decode())\n"
         "except e.HTTPError as x:\n    print(x.read().decode())\n")


def rest(path, method="GET", body=None):
    args = ["docker", "exec", RYU, "python", "-c", _REST, path, method]
    if body is not None:
        args.append(json.dumps(body))
    return json.loads(run(args).stdout.decode())


def wait_for(what, bound, test):
    start = time.monotonic()
    last = None
    while time.monotonic() - start < bound:
        try:
            last = test()
        except Failed as exc:
            last = str(exc)
        if last is True:
            return time.monotonic() - start
        time.sleep(0.5)
    raise Failed("%s: not within %g s; last seen %r" % (what, bound, last))


# ── frames ──────────────────────────────────────────────────────────────────────────────────

def mac(n):
    return bytes([2, 0, 0, 0, 0, n])


def v4(n):
    return bytes([192, 0, 2, n])


def v6(n):
    return bytes.fromhex("20010db8" + "00" * 11) + bytes([n])


def checksum(data):
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return (~total) & 0xffff


def arp_request(src, target_ip):
    body = struct.pack("!HHBBH6s4s6s4s", 1, 0x0800, 6, 4, 1, mac(src), v4(src), b"\0" * 6,
                       target_ip)
    return b"\xff" * 6 + mac(src) + b"\x08\x06" + body


def arp_reply(src, dst):
    body = struct.pack("!HHBBH6s4s6s4s", 1, 0x0800, 6, 4, 2, mac(src), v4(src), mac(dst),
                       v4(dst))
    return mac(dst) + mac(src) + b"\x08\x06" + body


def udp4(src, dst, seq):
    payload = struct.pack("!I", seq) + b"fabric-forwarding"
    udp = struct.pack("!HHHH", 40000, 40001, 8 + len(payload), 0) + payload
    head = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), seq & 0xffff, 0, 64, 17, 0,
                       v4(src), v4(dst))
    head = head[:10] + struct.pack("!H", checksum(head)) + head[12:]
    return mac(dst) + mac(src) + b"\x08\x00" + head + udp


def udp6(src, dst, seq):
    payload = struct.pack("!I", seq) + b"fabric-forwarding"
    udp = struct.pack("!HHHH", 40000, 40001, 8 + len(payload), 0) + payload
    pseudo = v6(src) + v6(dst) + struct.pack("!IxxxB", len(udp), 17)
    udp = udp[:6] + struct.pack("!H", checksum(pseudo + udp)) + udp[8:]
    head = struct.pack("!IHBB16s16s", 0x60000000, len(udp), 17, 64, v6(src), v6(dst))
    return mac(dst) + mac(src) + b"\x86\xdd" + head + udp


def inject(host, frame):
    ovs("ovs-appctl", "-t", "ovs-vswitchd", "netdev-dummy/receive", "h%x" % host, frame.hex())


def pcap(host):
    """The frames host port h<n> sent, from its tx_pcap."""
    data = ovs("cat", "%s/h%x.pcap" % (RUN, host)).stdout
    if len(data) < 24:
        return []
    endian = "<" if data[:4] == b"\xd4\xc3\xb2\xa1" else ">"
    out, at = [], 24
    while at + 16 <= len(data):
        _s, _u, incl, _orig = struct.unpack(endian + "IIII", data[at:at + 16])
        out.append(data[at + 16:at + 16 + incl])
        at += 16 + incl
    return out


def udp_seqs(frames, ethertype):
    seqs = []
    for f in frames:
        if f[12:14] != ethertype:
            continue
        start = 14 + (20 if ethertype == b"\x08\x00" else 40) + 8
        seqs.append(struct.unpack("!I", f[start:start + 4])[0])
    return seqs


# ── flows ───────────────────────────────────────────────────────────────────────────────────

FLOW = re.compile(r"cookie=(0x[0-9a-f]+).*?table=(\d+), n_packets=(\d+).*?priority=(\d+)"
                  r"(?:,(\S*))? actions=(\S+)")


def flows(bridge):
    """`[(cookie, table, priority, match, actions, n_packets)]` of bridge br<n>."""
    out = []
    for line in ofctl("dump-flows", "br%x" % bridge).splitlines():
        m = FLOW.search(line)
        if m:
            out.append((int(m.group(1), 16), int(m.group(2)), int(m.group(4)),
                        m.group(5) or "", m.group(6), int(m.group(3))))
    return out


def own(bridge):
    return [f for f in flows(bridge) if f[0] & COOKIE_MASK == APP_COOKIE]


def flow_for(bridge, address):
    for f in own(bridge):
        if re.search(r"(nw_dst|ipv6_dst)=%s(,|$)" % re.escape(address), f[3]):
            return f
    return None


def out_port(bridge, address):
    f = flow_for(bridge, address)
    return int(f[4].split(":")[1]) if f is not None and f[4].startswith("output:") else None


def punts(bridge):
    """Packets counted by the app's miss and ARP flows on br<n>."""
    return sum(f[5] for f in own(bridge) if f[2] in (0, 10) and "nw_dst" not in f[3])


# ── the steps ───────────────────────────────────────────────────────────────────────────────

def build_ring():
    target = vsctl("get-controller", "br3").strip()
    for n in RING:
        b = "br%x" % n
        vsctl("--may-exist", "add-br", b, "--", "set", "bridge", b, "datapath_type=netdev",
              "protocols=OpenFlow10,OpenFlow13", "other-config:datapath-id=%016x" % n,
              "fail_mode=secure", "--", "set-controller", b, target)
        vsctl("--may-exist", "add-port", b, "h%x" % n, "--", "set", "interface", "h%x" % n,
              "type=dummy", "ofport_request=%d" % HOST_PORT,
              "options:tx_pcap=%s/h%x.pcap" % (RUN, n))
    for i, n in enumerate(RING):
        m = RING[(i + 1) % len(RING)]
        a, z = "l%x-%x" % (n, m), "l%x-%x" % (m, n)
        vsctl("--may-exist", "add-port", "br%x" % n, a, "--", "set", "interface", a,
              "type=dummy", "ofport_request=%d" % CLOCKWISE,
              "options:pstream=punix:%s/%s.sock" % (RUN, a),
              "--", "--may-exist", "add-port", "br%x" % m, z, "--", "set", "interface", z,
              "type=dummy", "ofport_request=%d" % ANTICLOCKWISE,
              "options:stream=unix:%s/%s.sock" % (RUN, a))
    print("built the ring: %s, controller %s" % (", ".join("br%x" % n for n in RING), target))


def ring_ready():
    state = rest("/fabric_forwarding/state")
    graph = state["graph"]
    ring = [str(n) for n in RING]
    if not all(len(graph.get(n, {})) == 2 for n in ring):
        return "graph %s" % {n: graph.get(n) for n in ring}
    if not all(state["edge_ports"].get(n) == [HOST_PORT] for n in ring):
        return "edges %s" % {n: state["edge_ports"].get(n) for n in ring}
    held = rest("/fabric_forwarding/health")["held_until_settled"]
    return True if held == 0 else "%d changes held until the topology settles" % held


def step_shortest_path():
    print("1. shortest path")
    # h12 answers h11's ARP, so both are learned; then IPv4 both ways.
    inject(0x11, arp_request(0x11, v4(0x12)))
    inject(0x12, arp_reply(0x12, 0x11))
    for n in (0x13, 0x14):
        inject(n, arp_request(n, v4(0x11)))
    wait_for("the four IPv4 hosts' flows", 10, lambda: all(
        out_port(b, "192.0.2.%d" % h) is not None for b in RING for h in RING) or "waiting")
    check(out_port(0x11, "192.0.2.18") == CLOCKWISE,
          "br11 sends to h12 (192.0.2.18) straight to br12, the ring link between them")
    before = dict((b, flow_for(b, "192.0.2.18")[5]) for b in RING)
    for seq in range(20):
        inject(0x11, udp4(0x11, 0x12, seq))
    time.sleep(STATS_S)
    after = dict((b, flow_for(b, "192.0.2.18")[5]) for b in RING)
    moved = dict((("br%x" % b), after[b] - before[b]) for b in RING)
    check(moved == {"br11": 20, "br12": 20, "br13": 0, "br14": 0},
          "20 IPv4 frames h11 -> h12 counted on br11 and br12 only: %s" % moved)
    check(sorted(udp_seqs(pcap(0x12), b"\x08\x00"))[-20:] == list(range(20)),
          "h12's port sent all 20, in order")
    # IPv6, h11 to h13: two hops either way round; the tie goes to the lower switch, br12.
    inject(0x13, udp6(0x13, 0x11, 0))
    inject(0x11, udp6(0x11, 0x13, 0))
    address = "2001:db8::13"
    wait_for("h13's IPv6 flows", 10, lambda: out_port(0x11, address) is not None or "waiting")
    time.sleep(STATS_S)
    before = dict((b, flow_for(b, address)[5]) for b in RING)
    for seq in range(1, 11):
        inject(0x11, udp6(0x11, 0x13, seq))
    time.sleep(STATS_S)
    moved = dict((("br%x" % b), flow_for(b, address)[5] - before[b]) for b in RING)
    check(out_port(0x11, address) == CLOCKWISE and moved == {"br11": 10, "br12": 10,
                                                             "br13": 10, "br14": 0},
          "10 IPv6 frames h11 -> h13 (2001:db8::13) went br11 -> br12 -> br13: %s" % moved)


def step_loop_safe():
    print("2. loop-safe on the ring")
    burst = 50
    others = [n for n in RING if n != 0x11]
    time.sleep(STATS_S)
    before_punts = dict((n, punts(n)) for n in RING)
    before_counters = rest("/fabric_forwarding/health")["counters"]
    for i in range(burst):
        inject(0x11, arp_request(0x11, bytes([198, 51, 100, i + 1])))   # unknown targets
    time.sleep(STATS_S)
    # Counted from each host port's capture, by the burst's own target addresses: the port's
    # tx counter also counts Ryu's LLDP, which it sends out of every port.
    got_tx = dict(("h%x" % n, len([f for f in pcap(n) if f[12:14] == b"\x08\x06"
                                   and f[38:41] == bytes([198, 51, 100])])) for n in others)
    got_punts = dict(("br%x" % n, punts(n) - before_punts[n]) for n in RING)
    counters = rest("/fabric_forwarding/health")["counters"]
    relayed = counters["relayed"] - before_counters["relayed"]
    check(got_tx == dict(("h%x" % n, burst) for n in others),
          "each other host port sent each of the %d broadcasts once: %s" % (burst, got_tx))
    check(got_punts == {"br11": burst, "br12": 0, "br13": 0, "br14": 0},
          "punt counters: br11 counted the %d, the other ring switches none (flat): %s"
          % (burst, got_punts))
    check(relayed == burst, "the controller relayed %d frames for %d broadcasts" % (relayed,
                                                                                    burst))


#: Pulling the h11-h12 ring cable, as a cable pull does both: the frames stop (the dummy link's
#: stream cleared) and both ends report LINK_DOWN (admin state down). Measured 2026-11-07 in
#: this harness: a patch port cannot be set down (`ovs-ofctl mod-port ... down` left config 0
#: and state LIVE, and frames passed), and a dummy link set down reports LINK_DOWN but goes on
#: carrying frames, so either alone would let a missing reroute look like a working one.
CUT = ("ovs-vsctl %s remove interface l12-11 options stream && "
       "ovs-appctl -t ovs-vswitchd netdev-dummy/set-admin-state l11-12 down >/dev/null && "
       "ovs-appctl -t ovs-vswitchd netdev-dummy/set-admin-state l12-11 down >/dev/null" % DB)
RESTORE = ("ovs-appctl -t ovs-vswitchd netdev-dummy/set-admin-state l11-12 up >/dev/null && "
           "ovs-appctl -t ovs-vswitchd netdev-dummy/set-admin-state l12-11 up >/dev/null && "
           "ovs-vsctl %s set interface l12-11 options:stream=unix:%s/l11-12.sock" % (DB, RUN))


def step_reroute():
    print("3. reroute on link down")
    address = "192.0.2.18"
    script = ["set -e"]
    for s in range(STREAM):
        script.append("ovs-appctl -t ovs-vswitchd netdev-dummy/receive h11 %s"
                      % udp4(0x11, 0x12, 1000 + s).hex())
        script.append("echo %d $(date +%%s%%N)" % (1000 + s))
    stream = subprocess.Popen(["docker", "exec", "-i", "-e", "OVS_RUNDIR=" + RUN, OVS, "sh",
                               "-s"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    stream.stdin.write(("\n".join(script) + "\n").encode())
    stream.stdin.close()
    time.sleep(CUT_AFTER_S)
    cut = ovs("sh", "-c", "date +%s%N; " + CUT + "; date +%s%N")
    cut_start, cut_end = [int(x) for x in cut.stdout.split()]
    out, err = stream.communicate(timeout=120)
    if stream.returncode != 0:
        raise Failed("the stream exited %d: %s" % (stream.returncode, err.decode()[-400:]))
    sent = dict((int(a), int(b)) for a, b in (l.split() for l in out.decode().splitlines()))
    delivered = set(s for s in udp_seqs(pcap(0x12), b"\x08\x00") if s >= 1000)
    lost = sorted(s for s in sent if s not in delivered)
    rate = (max(sent.values()) - min(sent.values())) / 1e6 / (len(sent) - 1)
    print("  the stream: %d frames, one every %.2f ms; the cut at %.0f ms into it"
          % (len(sent), rate, (cut_start - min(sent.values())) / 1e6))
    if lost:
        before = [s for s in sent if s < lost[0] and s in delivered]
        after = [s for s in sent if s > lost[-1] and s in delivered]
        if not before or not after:
            raise Failed("the stream lost %d of %d frames, from %d, and %s: no reroute"
                         % (len(lost), len(sent), lost[0], "none arrived after them"
                            if before else "none arrived before them"))
        outage = (sent[after[0]] - sent[before[-1]]) / 1e6
        print("  lost %d frames (%d to %d); outage %.1f ms (last frame before it to the "
              "first after); the cut took %.1f ms to send"
              % (len(lost), lost[0], lost[-1], outage, (cut_end - cut_start) / 1e6))
        check(lost == list(range(lost[0], lost[-1] + 1)), "the frames lost are one run, the "
                                                          "cut's, and none after it")
    else:
        print("  lost 0 frames; the cut took %.1f ms to send" % ((cut_end - cut_start) / 1e6))
    check(len(delivered) > 0.9 * STREAM, "%d of %d delivered" % (len(delivered), STREAM))
    check(out_port(0x11, address) == ANTICLOCKWISE,
          "br11 now sends to h12 the other way round (port %d, to br14)" % ANTICLOCKWISE)
    check(out_port(0x14, address) == ANTICLOCKWISE and out_port(0x13, address) == ANTICLOCKWISE,
          "br14 -> br13 -> br12 carry it")
    last_lost = lost[-1] if lost else 0
    after_cut = [s for s in sent if sent[s] > cut_end and s > last_lost]
    check(len(after_cut) >= 300 and all(s in delivered for s in after_cut),
          "all %d frames sent after the cut and the outage arrived, on the new path (at least "
          "300 asked, so the new path is shown carrying the stream)" % len(after_cut))
    ovs("sh", "-c", RESTORE)
    took = wait_for("the restored link back in the path", DISCOVERY_BOUND_S,
                    lambda: out_port(0x11, address) == CLOCKWISE or "waiting")
    print("  the cable put back: the path back on it after %.1f s (Ryu's discovery, then the "
          "app's settle time)" % took)


def own_keys():
    """Each ring switch's app flows as `{bridge: sorted [(table, priority, match, actions)]}`."""
    return dict((b, sorted((f[1], f[2], f[3], f[4]) for f in own(b))) for b in RING)


def step_reconcile():
    print("4. reconcile on reconnect")
    before = own_keys()
    lldp_before = [f[:5] for f in flows(0x12) if f[0] == 0]
    victim = flow_for(0x13, "192.0.2.17")
    check(victim is not None, "br13 holds the app's flow for h11 (192.0.2.17): %s" % (victim,))
    run(["docker", "stop", "-t", "5", RYU])
    ofctl("del-flows", "--strict", "br13", "priority=%d,%s" % (victim[2], victim[3]))
    ofctl("add-flow", "br14", "cookie=%#x,priority=100,ip,nw_dst=192.0.2.250,actions=output:2"
          % (APP_COOKIE | 5))
    ofctl("add-flow", "br11", "cookie=%#x,priority=50,ip,nw_dst=192.0.2.200,actions=drop"
          % FOREIGN_COOKIE)
    print("  with Ryu stopped: deleted br13's flow for 192.0.2.17, planted a stale flow under "
          "the app's cookie on br14 and another owner's on br11")
    started = time.monotonic()
    run(["docker", "start", RYU])

    def reconnected():
        got = vsctl("--columns=is_connected", "list", "controller").split()
        return got.count("true") == len(RING) + 2 or "%d connected" % got.count("true")
    wait_for("every bridge back on Ryu", RECONNECT_BOUND_S, reconnected)
    wait_for("Ryu's REST", RECONNECT_BOUND_S, lambda: "app" in rest(
        "/fabric_forwarding/health") or "waiting")
    put = rest("/fabric_forwarding/config", "PUT", CONFIG)
    check(put.get("ok") is True, "the config pushed again (H's policy push): %s" % put)
    wait_for("the ring rediscovered", DISCOVERY_BOUND_S, ring_ready)

    def back():
        health = rest("/fabric_forwarding/health")
        return (own_keys() == before and health["held_until_settled"] == 0) or "waiting"
    took = wait_for("the app's flows back as before", DISCOVERY_BOUND_S, back)
    print("  reconnected and reconciled %.1f s after Ryu was started"
          % (time.monotonic() - started))
    check(own_keys() == before, "every ring switch holds exactly the app flows it held before "
                                "(%d in all), br13's deleted one back"
          % sum(len(v) for v in before.values()))
    for b in RING:
        keys = [(f[1], f[2], f[3]) for f in own(b)]
        check(len(keys) == len(set(keys)), "br%x: no app flow twice (%d)" % (b, len(keys)))
    check(not [f for f in flows(0x14) if "192.0.2.250" in f[3]], "br14's stale flow removed")
    foreign = [f for f in flows(0x11) if f[0] == FOREIGN_COOKIE]
    check(len(foreign) == 1 and foreign[0][4] == "drop", "br11's other owner's flow untouched")
    lldp_after = [f[:5] for f in flows(0x12) if f[0] == 0]
    check(lldp_after == lldp_before, "Ryu's own LLDP flow (cookie 0) untouched: %s"
          % lldp_after)
    health = rest("/fabric_forwarding/health")
    sent = (health["counters"]["flows_added"], health["counters"]["flows_removed"])
    check(sent == (1, 1), "since the restart the app sent exactly the difference: %d flow "
                          "added, %d removed (nothing re-sent)" % sent)
    check(health["ok"] is True, "/health ok: %s" % health)
    del took


def main():
    global OVS, RYU
    OVS, RYU = container("ovs"), container("ryu")
    put = rest("/fabric_forwarding/config", "PUT", CONFIG)
    if put.get("ok") is not True:
        raise Failed("the config push was refused: %s" % put)
    build_ring()
    took = wait_for("the ring's links found and its edges settled", DISCOVERY_BOUND_S,
                    ring_ready)
    print("the ring discovered and settled after %.1f s" % took)
    step_shortest_path()
    step_loop_safe()
    step_reroute()
    step_reconcile()
    print("fabric_forwarding acceptance: every step passed")


if __name__ == "__main__":
    try:
        main()
    except Failed as exc:
        print("FAILED: %s" % exc)
        sys.exit(1)
