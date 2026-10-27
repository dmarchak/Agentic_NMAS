"""Renders `lldp_from_ryu.json` beside it with Ryu 4.34's OWN code: the LLDP frame Ryu's link
discovery sends out of a switch port (`ryu.topology.switches.LLDPPacket.lldp_packet`), parsed
back by Ryu's own `ryu.lib.packet`, so a test can hold what a neighbouring device's LLDP table
would hold for it: the chassis id (subtype and text) and the port id (subtype and bytes).

Run INSIDE the Ryu 4.34 image (it imports ryu, which Mercury does not install), with this
folder mounted at /out:

    docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/tests/fixtures/sdn/ryu:/out" \
        --entrypoint python mercury-ryu-trial:4.34 -B /out/render_lldp_with_ryu.py /out

The datapath ids and ports are the author's choice (the first is the lab capture's switch 1,
port 3; the second a DPID with every byte set, port 65534); the frame and every field are
Ryu's.
"""
import json
import sys

from ryu.lib.packet import lldp, packet
from ryu.topology.switches import LLDPPacket

CASES = ((1, 3, "1e:8a:d1:09:f1:bd"), (0x0123456789ABCDEF, 65534, "02:00:00:00:00:fe"))


def render(dpid, port_no, hw_addr):
    data = LLDPPacket.lldp_packet(dpid, port_no, hw_addr, 120)
    tlvs = [p for p in packet.Packet(data) if isinstance(p, lldp.lldp)][0].tlvs
    chassis, port = tlvs[0], tlvs[1]
    return {"dpid": dpid, "port_no": port_no,
            "chassis_id_subtype": chassis.subtype,
            "chassis_id": chassis.chassis_id.decode("ascii"),
            "port_id_subtype": port.subtype,
            "port_id_hex": port.port_id.hex(),
            "frame_hex": data.hex(),
            "tlv_types": [t.tlv_type for t in tlvs],
            "parsed_back": list(LLDPPacket.lldp_parse(data))}


def main(out_dir):
    doc = {"ryu": "4.34", "made_by": "render_lldp_with_ryu.py",
           "frames": [render(*case) for case in CASES]}
    with open(f"{out_dir}/lldp_from_ryu.json", "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main(sys.argv[1])
