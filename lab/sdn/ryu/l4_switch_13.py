"""A learning switch whose flows match L4 (lab environment, not product: PHASE8_PLAN 17.6).

Ryu's simple_switch_13 installs flows on in_port, eth_src and eth_dst, so a port scan is one
flow and invisible in flow data. This one installs, for IPv4 TCP and UDP, a flow per
(in_port, ipv4_src, ipv4_dst, ip_proto, L4 destination port), idle-timed so a scan leaves one
flow per probed port for a while; other traffic is learned at L2 as simple_switch_13 does.
Run by the lab's container (lab/sdn/ryu/Dockerfile) beside ryu.app.ofctl_rest."""
from ryu.app import simple_switch_13
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, set_ev_cls
from ryu.lib.packet import ethernet, ether_types, ipv4, packet, tcp, udp
from ryu.ofproto import inet

#: Seconds an L4 flow stays without traffic: long enough for two flow-table reads.
L4_IDLE = 30


class L4Switch13(simple_switch_13.SimpleSwitch13):
    """simple_switch_13, with IPv4 TCP and UDP learned per destination port."""

    def _l4_match(self, parser, in_port, pkt):
        ip = pkt.get_protocol(ipv4.ipv4)
        if ip is None:
            return None
        if ip.proto == inet.IPPROTO_TCP and pkt.get_protocol(tcp.tcp):
            return parser.OFPMatch(in_port=in_port, eth_type=ether_types.ETH_TYPE_IP,
                                   ipv4_src=ip.src, ipv4_dst=ip.dst, ip_proto=ip.proto,
                                   tcp_dst=pkt.get_protocol(tcp.tcp).dst_port)
        if ip.proto == inet.IPPROTO_UDP and pkt.get_protocol(udp.udp):
            return parser.OFPMatch(in_port=in_port, eth_type=ether_types.ETH_TYPE_IP,
                                   ipv4_src=ip.src, ipv4_dst=ip.dst, ip_proto=ip.proto,
                                   udp_dst=pkt.get_protocol(udp.udp).dst_port)
        return None

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle=0):
        ofproto, parser = datapath.ofproto, datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        kw = {"datapath": datapath, "priority": priority, "match": match,
              "instructions": inst, "idle_timeout": idle}
        if buffer_id is not None:
            kw["buffer_id"] = buffer_id
        datapath.send_msg(parser.OFPFlowMod(**kw))

    # Ryu registers a handler by this decorator on the method itself: an override without it
    # is never called.
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath, parser = msg.datapath, msg.datapath.ofproto_parser
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        in_port = msg.match["in_port"]
        l4 = self._l4_match(parser, in_port, pkt)
        if l4 is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            super()._packet_in_handler(ev)
            return
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})[eth.src] = in_port
        out_port = self.mac_to_port[dpid].get(eth.dst, datapath.ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        if out_port != datapath.ofproto.OFPP_FLOOD:
            self.add_flow(datapath, 2, l4, actions, idle=L4_IDLE)
        data = msg.data if msg.buffer_id == datapath.ofproto.OFP_NO_BUFFER else None
        datapath.send_msg(parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                              in_port=in_port, actions=actions, data=data))
