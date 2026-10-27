"""Renders the Ryu fixtures beside it with Ryu 4.34's OWN code, no switch connected.

Run INSIDE the Ryu 4.34 image (it imports ryu, which Mercury does not install), with this
folder mounted at /out:

    docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/tests/fixtures/sdn/ryu:/out" \
        --entrypoint python mercury-ryu-trial:4.34 /out/render_with_ryu.py /out

Each multipart reply is built as WIRE BYTES (the OpenFlow 1.3 header, the multipart header,
then each entry packed with ofproto_v1_3's own pack strings, its match and instructions
serialised by ofproto_v1_3_parser's own classes), parsed back by Ryu's own
`ofproto_parser.msg`, and delivered to `ryu.lib.ofctl_v1_3`'s get_* function through a dummy
datapath, as Ryu's own tests do (ryu/tests/unit/lib/test_ofctl.py's DummyDatapath). The body
written is `json.dumps` of what that function returns, exactly as `ryu.app.ofctl_rest`'s
`stats_method` answers it. The flows, ports and meters are the author's choice of what the
lab's application would install (README.md beside this file says which); the SHAPE and every
conversion (`dl_src` for eth_src, `tp_dst` for tcp_dst, `OUTPUT:CONTROLLER`, `METER:1`, an
empty action list for a drop) are Ryu's.
"""
import json
import struct
import sys

from ryu.lib import ofctl_v1_3
from ryu.ofproto import ofproto_parser
from ryu.ofproto import ofproto_v1_3 as ofp
from ryu.ofproto import ofproto_v1_3_parser as parser
from ryu.ofproto.ofproto_protocol import ProtocolDesc

DPID = 1


class DummyDatapath(ProtocolDesc):
    """Ryu's own test double (ryu/tests/unit/lib/test_ofctl.py), without its nose import."""

    def __init__(self):
        super().__init__(ofp.OFP_VERSION)
        self.id = DPID
        self.reply = None
        self.waiters = None

    @staticmethod
    def set_xid(msg):
        msg.set_xid(0)
        return 0

    def send_msg(self, msg):
        msg.serialize()
        lock, msgs = self.waiters[self.id][msg.xid]
        msgs.append(self.reply)
        del self.waiters[self.id][msg.xid]
        lock.set()


def multipart_reply(dp, mp_type, entries: bytes):
    """A whole OFPT_MULTIPART_REPLY on the wire, parsed back by Ryu's own parser."""
    length = ofp.OFP_HEADER_SIZE + struct.calcsize(ofp.OFP_MULTIPART_REPLY_PACK_STR) + len(entries)
    buf = struct.pack(ofp.OFP_HEADER_PACK_STR, ofp.OFP_VERSION, ofp.OFPT_MULTIPART_REPLY,
                      length, 0)
    buf += struct.pack(ofp.OFP_MULTIPART_REPLY_PACK_STR, mp_type, 0) + entries
    return ofproto_parser.msg(dp, ofp.OFP_VERSION, ofp.OFPT_MULTIPART_REPLY, length, 0, buf)


def flow_entry(table_id, duration, priority, idle, hard, cookie, packets, octets, match,
               instructions, flags=0):
    fixed = struct.calcsize(ofp.OFP_FLOW_STATS_0_PACK_STR)
    buf = bytearray(fixed)
    offset = fixed + match.serialize(buf, fixed)
    for inst in instructions:
        inst.serialize(buf, offset)
        offset += inst.len
    struct.pack_into(ofp.OFP_FLOW_STATS_0_PACK_STR, buf, 0, offset, table_id, duration[0],
                     duration[1], priority, idle, hard, flags, cookie, packets, octets)
    return bytes(buf)


def apply(*actions):
    return parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, list(actions))


def out(port):
    return parser.OFPActionOutput(port, 0)


def flows():
    """The lab application's kinds of flow, and the responses Mercury will install."""
    m = parser.OFPMatch
    return b"".join([
        # simple_switch_13's table-miss: everything else to the controller, unbuffered.
        flow_entry(0, (912, 4000000), 0, 0, 0, 0, 41, 4466, m(),
                   [apply(parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER))]),
        # simple_switch_13's learned L2 flow (in_port, eth_dst, eth_src).
        flow_entry(0, (874, 120000000), 1, 0, 0, 0, 12, 1036,
                   m(in_port=1, eth_dst="00:00:00:00:00:02", eth_src="00:00:00:00:00:01"),
                   [apply(out(2))]),
        # The L4 application's per-destination-port flow, idle 30 s (TCP).
        flow_entry(0, (3, 500000000), 2, 30, 0, 0, 2, 132,
                   m(in_port=1, eth_type=0x0800, ipv4_src="192.0.2.1", ipv4_dst="192.0.2.2",
                     ip_proto=6, tcp_dst=22), [apply(out(2))]),
        # The same for UDP, so tp_dst is read back as udp_dst.
        flow_entry(0, (5, 0), 2, 30, 0, 0, 1, 74,
                   m(in_port=2, eth_type=0x0800, ipv4_src="192.0.2.2", ipv4_dst="192.0.2.3",
                     ip_proto=17, udp_dst=53), [apply(out(3))]),
        # An IPv6 TCP flow beside the IPv4 one.
        flow_entry(0, (7, 250000000), 2, 30, 0, 0, 3, 258,
                   m(in_port=1, eth_type=0x86dd, ipv6_src="2001:db8::1",
                     ipv6_dst="2001:db8::2", ip_proto=6, tcp_dst=443), [apply(out(3))]),
        # A response's drop flow: a masked source, no instructions, a hard timeout and a cookie.
        flow_entry(0, (40, 0), 100, 0, 300, 0x4D45524300000001, 980, 58800,
                   m(eth_type=0x0800, ipv4_src=("192.0.2.0", "255.255.255.0")), []),
        # A response's rate limit: meter 1, then out of port 2.
        flow_entry(0, (12, 0), 90, 0, 300, 0x4D45524300000002, 5000, 7500000,
                   m(in_port=3, eth_type=0x0800, ipv4_src="192.0.2.3"),
                   [parser.OFPInstructionMeter(1, ofp.OFPIT_METER), apply(out(2))]),
        # Write-actions and a goto, so both instruction forms are read back.
        flow_entry(0, (60, 0), 5, 0, 0, 0, 0, 0, m(in_port=3, eth_type=0x0806),
                   [parser.OFPInstructionActions(ofp.OFPIT_WRITE_ACTIONS, [out(1)]),
                    parser.OFPInstructionGotoTable(1)]),
        # A flow in table 1 setting a field (a VLAN-tagged match, read back as dl_vlan).
        flow_entry(1, (60, 0), 1, 0, 0, 0, 0, 0, m(vlan_vid=(0x1000 | 10)),
                   [apply(parser.OFPActionSetField(eth_dst="00:00:00:00:00:03"), out(3))]),
    ])


def ports():
    rows = [(1, 120, 118, 9480, 9310), (2, 118, 121, 9320, 9500), (3, 40, 38, 3200, 3100),
            (ofp.OFPP_LOCAL, 0, 0, 0, 0)]
    return b"".join(struct.pack(ofp.OFP_PORT_STATS_PACK_STR, no, rxp, txp, rxb, txb, 0,
                                3 if no == 3 else 0, 0, 0, 0, 0, 0, 0, 912, 4000000)
                    for no, rxp, txp, rxb, txb in rows)


def meter_stats():
    head = struct.calcsize(ofp.OFP_METER_STATS_PACK_STR)
    band = struct.calcsize(ofp.OFP_METER_BAND_STATS_PACK_STR)
    return (struct.pack(ofp.OFP_METER_STATS_PACK_STR, 1, head + band, 1, 5000, 7500000, 12, 0)
            + struct.pack(ofp.OFP_METER_BAND_STATS_PACK_STR, 1200, 1800000))


def meter_config():
    bands = bytearray()
    parser.OFPMeterBandDrop(rate=1000, burst_size=100).serialize(bands, 0)
    head = struct.calcsize(ofp.OFP_METER_CONFIG_PACK_STR)
    return (struct.pack(ofp.OFP_METER_CONFIG_PACK_STR, head + len(bands),
                        ofp.OFPMF_KBPS | ofp.OFPMF_BURST | ofp.OFPMF_STATS, 1) + bytes(bands))


def meter_features():
    return struct.pack(ofp.OFP_METER_FEATURES_PACK_STR, 200,
                       (1 << ofp.OFPMBT_DROP) | (1 << ofp.OFPMBT_DSCP_REMARK),
                       ofp.OFPMF_KBPS | ofp.OFPMF_PKTPS | ofp.OFPMF_BURST | ofp.OFPMF_STATS,
                       1, 0)


def desc():
    return struct.pack(ofp.OFP_DESC_PACK_STR, b"Example Manufacturer", b"Example Switch",
                       b"0.0.0", b"None", b"s1")


#: Only the EMPTY answers are written as files: the full ones were rendered too (2026-10-26),
#: found byte-identical to the answers Ryu's REST gave with peer_switch.py connected serving
#: the same entries, and are kept once, as that capture (rest_with_peer.json).
RENDERS = {
    "flow_stats_empty.json": (ofp.OFPMP_FLOW, lambda: b"", ofctl_v1_3.get_flow_stats),
    "meter_stats_empty.json": (ofp.OFPMP_METER, lambda: b"", ofctl_v1_3.get_meter_stats),
    "meter_config_empty.json": (ofp.OFPMP_METER_CONFIG, lambda: b"",
                                ofctl_v1_3.get_meter_config),
}


def main(folder):
    for name, (mp_type, entries, get) in RENDERS.items():
        dp = DummyDatapath()
        dp.waiters = {}
        dp.reply = multipart_reply(dp, mp_type, entries())
        body = json.dumps(get(dp, dp.waiters))         # ofctl_rest's stats_method, exactly
        answer = {"status": 200, "content_type": "application/json", "body": body}
        with open(f"{folder}/{name}", "w", encoding="utf-8") as fh:
            json.dump(answer, fh, indent=1)
            fh.write("\n")


if __name__ == "__main__":
    main(sys.argv[1])
