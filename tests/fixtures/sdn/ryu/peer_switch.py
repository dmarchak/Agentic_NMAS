"""A scripted OpenFlow 1.3 peer standing in for a switch, so Ryu 4.34's REST can be captured with
a datapath connected (no Mininet: running it needs root, the operator's).

Run INSIDE the Ryu 4.34 image, on the host's network beside a running controller, with this
folder mounted at /out:

    docker run --rm --network host --user "$(id -u):$(id -g)" \
        -v "$PWD/tests/fixtures/sdn/ryu:/out" --entrypoint python mercury-ryu-trial:4.34 \
        /out/peer_switch.py 127.0.0.1 6653 /out/peer_log.json 40

It says HELLO, answers FEATURES_REQUEST as datapath 1, answers the port description Ryu asks
for before it treats the switch as connected, answers ECHO and BARRIER, and answers each
statistics request with the same entries render_with_ryu.py renders (its functions, imported).
Every FLOW_MOD and METER_MOD Ryu sends is decoded by Ryu's own parser (a meter's by its pack
strings) and written to the log: what a REST write became on the wire.
"""
import json
import socket
import struct
import sys
import time

import render_with_ryu as R
from ryu.ofproto import ofproto_parser
from ryu.ofproto import ofproto_v1_3 as ofp
from ryu.ofproto.ofproto_protocol import ProtocolDesc

STATS = {ofp.OFPMP_FLOW: R.flows, ofp.OFPMP_PORT_STATS: R.ports, ofp.OFPMP_METER: R.meter_stats,
         ofp.OFPMP_METER_CONFIG: R.meter_config, ofp.OFPMP_METER_FEATURES: R.meter_features,
         ofp.OFPMP_DESC: R.desc}


def header(msg_type, length, xid):
    return struct.pack(ofp.OFP_HEADER_PACK_STR, ofp.OFP_VERSION, msg_type, length, xid)


def message(msg_type, xid, body=b""):
    return header(msg_type, ofp.OFP_HEADER_SIZE + len(body), xid) + body


def multipart(mp_type, xid, entries):
    body = struct.pack(ofp.OFP_MULTIPART_REPLY_PACK_STR, mp_type, 0) + entries
    return message(ofp.OFPT_MULTIPART_REPLY, xid, body)


def port_desc():
    rows = [(1, b"s1-eth1"), (2, b"s1-eth2"), (3, b"s1-eth3"), (ofp.OFPP_LOCAL, b"s1")]
    return b"".join(struct.pack(ofp.OFP_PORT_PACK_STR, no, bytes([0, 0, 0, 0, 0, i + 1]), name,
                                0, ofp.OFPPS_LIVE, 0, 0, 0, 0, 10000000, 10000000)
                    for i, (no, name) in enumerate(rows))


def meter_mod(buf):
    command, flags, meter_id = struct.unpack_from(ofp.OFP_METER_MOD_PACK_STR, buf,
                                                  ofp.OFP_HEADER_SIZE)
    offset, bands = ofp.OFP_HEADER_SIZE + struct.calcsize(ofp.OFP_METER_MOD_PACK_STR), []
    while offset < len(buf):
        kind, length, rate, burst = struct.unpack_from(ofp.OFP_METER_BAND_HEADER_PACK_STR, buf,
                                                       offset)
        bands.append({"type": kind, "rate": rate, "burst_size": burst})
        offset += length
    return {"OFPMeterMod": {"command": command, "flags": flags, "meter_id": meter_id,
                            "bands": bands}}


def main(host, port, log_path, seconds):
    sock = socket.create_connection((host, int(port)), timeout=2)
    sock.sendall(message(ofp.OFPT_HELLO, 1))
    log, pending, end = [], b"", time.time() + float(seconds)
    while time.time() < end:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            continue
        if not chunk:
            break
        pending += chunk
        while len(pending) >= ofp.OFP_HEADER_SIZE:
            _v, msg_type, length, xid = struct.unpack_from(ofp.OFP_HEADER_PACK_STR, pending)
            if len(pending) < length:
                break
            buf, pending = pending[:length], pending[length:]
            if msg_type == ofp.OFPT_FEATURES_REQUEST:
                sock.sendall(message(ofp.OFPT_FEATURES_REPLY, xid, struct.pack(
                    ofp.OFP_SWITCH_FEATURES_PACK_STR, R.DPID, 0, 254, 0,
                    ofp.OFPC_FLOW_STATS | ofp.OFPC_PORT_STATS, 0)))
            elif msg_type == ofp.OFPT_ECHO_REQUEST:
                sock.sendall(message(ofp.OFPT_ECHO_REPLY, xid, buf[ofp.OFP_HEADER_SIZE:]))
            elif msg_type == ofp.OFPT_BARRIER_REQUEST:
                sock.sendall(message(ofp.OFPT_BARRIER_REPLY, xid))
            elif msg_type == ofp.OFPT_MULTIPART_REQUEST:
                mp_type, = struct.unpack_from("!H", buf, ofp.OFP_HEADER_SIZE)
                if mp_type == ofp.OFPMP_PORT_DESC:
                    sock.sendall(multipart(mp_type, xid, port_desc()))
                elif mp_type in STATS:
                    sock.sendall(multipart(mp_type, xid, STATS[mp_type]()))
            elif msg_type == ofp.OFPT_FLOW_MOD:
                msg = ofproto_parser.msg(ProtocolDesc(ofp.OFP_VERSION), ofp.OFP_VERSION,
                                         msg_type, length, xid, buf)
                log.append(msg.to_jsondict())
            elif msg_type == ofp.OFPT_METER_MOD:
                log.append(meter_mod(buf))
    with open(log_path, "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=1, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main(*sys.argv[1:5])
