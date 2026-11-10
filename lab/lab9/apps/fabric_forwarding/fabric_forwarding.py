"""fabric_forwarding v0: Mercury's frame for the fabric's forwarding app (the SDN platform design
revision 6, section 14: "shortest path, loop-safe on the ring, reroute on link down, reconcile
on connect; deployed by H"; P7a). A Ryu 4.34 app on OpenFlow 1.3, written for Python 3.5, the
controller's interpreter (C2646). The logic is plain data in `fabric_logic` and the path choice,
the team's, in `fabric_paths`; this module is the wiring:

- **switch connect** (`EventOFPStateChange` to MAIN): the switch's ports and its flows are
  read; when the flows arrive, its own DELIVER flows rebuild the hosts, and the switch is
  RECONCILED: its missing punt and DELIVER flows are added at once (they depend on no path);
  the TRANSIT flows a path decides are added or changed, and the app's own extras removed, once
  every connected switch is read and the topology has settled (no switch, port or link found
  for `settle_s`), and nothing else is sent, so a controller restart never moves or removes a
  path a switch still forwards on before discovery has found its links. Another owner's flow
  is never touched (`fabric_logic.difference`);
- **switch leave** (to DEAD): its links and hosts go, and every path is recomputed around it;
- **port status**: a port that goes down takes its links and hosts with it, and every path is
  recomputed AT ONCE (the reroute: the new next hops overwrite the old flows, same match and
  priority, so nothing is removed first); a port that comes up is an edge only after
  `settle_s`;
- **links** (`ryu.topology`'s link events, from `--observe-links`): added or removed, then the
  paths recomputed; a host learned on a port that turns out to be a link is forgotten;
- **packet-in**: a frame from an edge port teaches its sender's address; a frame for a known
  host goes straight out of that host's port, and a broadcast, multicast or unknown destination
  is relayed by the controller out of the edge ports only, once (never flooded in the data
  plane; `fabric_logic`'s docstring, "Loop safety");
- **errors**: each switch's last refusals are kept and shown by `/health`.

**The config** is read AT LOAD from the start-time file Mercury's deploy compiled and staged
beside this version (`mercury_app.start_config`, decision K9; its tables from each switch's
platform profile, the manifest's `compiled`; C2729, C2760), so after the deploy's restart the
app serves without a push; `PUT /fabric_forwarding/config` (H's policy push) can replace it
while it runs. Either is held to the manifest's `config_schema` (`fabric_logic.parse_config`
refuses a field by name). While no config is in force no switch is served and `/health` says
why (the SDK not importable, the file absent, unreadable or refused): the tables are the
network's, never guessed.

**REST** (under `/fabric_forwarding`): `GET /health`, `GET` and `PUT /config`, `GET /state`
(the switches, links, edge ports, hosts and counters, for the harness's acceptance and for
Mercury's trace).
"""

import hashlib
import json
import time

from ryu.app.wsgi import ControllerBase, Response, WSGIApplication, route
from ryu.base import app_manager
from ryu.controller import event, ofp_event
from ryu.controller.handler import DEAD_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import arp, ethernet, ipv4, ipv6, packet
from ryu.ofproto import ofproto_v1_3
from ryu.topology import event as topo_event

import fabric_logic as logic

try:
    import mercury_app
    HAVE_SDK = True
except ImportError:                     # the SDK is not deployed beside the app: /health says so
    HAVE_SDK = False

NAME = "fabric_forwarding"
VERSION = "0.3.0"
PREFIX = "/" + NAME
#: How often the settle timer looks (it acts only through an event, on the app's own thread).
TICK_S = 0.25
#: How many refusals a switch keeps for /health.
ERRORS_KEPT = 10
#: A removal's cookie mask: the flow's own cookie exactly, so no other owner's flow matches.
EXACT = 0xffffffffffffffff


class EventSettleCheck(event.EventBase):
    """The settle timer's tick, handled on the app's own event thread."""


class FabricForwarding(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"wsgi": WSGIApplication}
    _EVENTS = [EventSettleCheck]

    def __init__(self, *args, **kwargs):
        super(FabricForwarding, self).__init__(*args, **kwargs)
        self.config = None
        self.datapaths = {}             # dpid -> datapath
        self.up_ports = {}              # dpid -> set of ports up
        self.up_since = {}              # (dpid, port) -> when it came up
        self.links = set()              # (src_dpid, src_port, dst_dpid, dst_port)
        self.hosts = {}                 # address -> (dpid, port)
        self.flows = {}                 # dpid -> {key: (actions, cookie)}: the app's own, as sent
        self.others = {}                # dpid -> {key: cookie}: other owners', as read
        self.reading = {}               # dpid -> flows read so far, while a read is in parts
        self.read_done = set()          # the switches whose flows were read since they connected
        self.errors = {}                # dpid -> [words]
        self.problems = []
        self.last_topology_change = time.time()
        self.held = 0                   # changes and removals waiting for the topology to settle
        self.relay = logic.Recent(logic.DEFAULTS["dedup_s"])
        self.counters = {"packet_in": 0, "packet_in_others": 0, "relayed": 0,
                         "relay_dropped_repeat": 0,
                         "relay_refused_not_edge": 0, "delivered": 0, "flows_added": 0,
                         "flows_removed": 0, "recomputes": 0, "reroutes": 0}
        kwargs["wsgi"].register(FabricRest, {"fabric_app": self})
        # The start-time config, read once at load (C2729): no switch has connected yet.
        answer = mercury_app.start_config(NAME, VERSION) if HAVE_SDK else None
        config, self.start_error = logic.from_start_config(answer)
        self.start = {"read": config is not None, "error": self.start_error,
                      "path": (answer or {}).get("path", ""),
                      "sha256": (answer or {}).get("sha256", "")}
        if config is not None:
            self._take_config(config, "its start-time config %s" % self.start["path"])
        else:
            self.logger.warning("%s: %s; no switch is served until a config is pushed", NAME,
                                self.start_error)
        hub.spawn(self._settle_timer)

    # ── the config ──────────────────────────────────────────────────────────────────────────

    def set_config(self, data):
        config, problems = logic.parse_config(data)
        if config is None:
            return problems
        self._take_config(config, "a push")
        return []

    def _take_config(self, config, where):
        self.config = config
        self.relay = logic.Recent(config["dedup_s"])
        self.logger.info("%s: config set from %s: %d switches named, default tables %s", NAME,
                         where, len(config["switches"]), config["default_tables"])
        # Every switch is read again and reconciled as its flows arrive, never before: a flow
        # sent ahead of a read already asked for would be missing from that read, and sent
        # twice.
        for dpid in sorted(self.datapaths):
            self.read_done.discard(dpid)
            self._read(self.datapaths[dpid])

    def served(self):
        return sorted(d for d in self.datapaths if logic.tables_for(self.config, d) is not None)

    # ── switches ────────────────────────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change(self, ev):
        dp = ev.datapath
        if dp.id is None:
            return
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
            self.read_done.discard(dp.id)
            self.last_topology_change = time.time()
            self._read(dp)
        elif ev.state == DEAD_DISPATCHER and self.datapaths.get(dp.id) is dp:
            del self.datapaths[dp.id]
            self.read_done.discard(dp.id)
            self.up_ports.pop(dp.id, None)
            self.flows.pop(dp.id, None)
            self.others.pop(dp.id, None)
            self.links = set(l for l in self.links if dp.id not in (l[0], l[2]))
            self.hosts = dict((a, h) for a, h in self.hosts.items() if h[0] != dp.id)
            self._recompute("switch %d left" % dp.id, reroute=True)

    def _read(self, dp):
        parser = dp.ofproto_parser
        dp.send_msg(parser.OFPPortDescStatsRequest(dp, 0))
        self.reading[dp.id] = []
        dp.send_msg(parser.OFPFlowStatsRequest(dp, 0, dp.ofproto.OFPTT_ALL, dp.ofproto.OFPP_ANY,
                                               dp.ofproto.OFPG_ANY, 0, 0, parser.OFPMatch()))

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def _port_desc(self, ev):
        dp = ev.msg.datapath
        now = time.time()
        up = set()
        for port in ev.msg.body:
            if port.port_no <= dp.ofproto.OFPP_MAX and self._port_is_up(dp, port):
                up.add(port.port_no)
                self.up_since.setdefault((dp.id, port.port_no), now)
        self.up_ports[dp.id] = up

    @staticmethod
    def _port_is_up(dp, port):
        ofp = dp.ofproto
        return not (port.state & ofp.OFPPS_LINK_DOWN) and not (port.config & ofp.OFPPC_PORT_DOWN)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status(self, ev):
        dp, port = ev.msg.datapath, ev.msg.desc
        ofp = dp.ofproto
        if port.port_no > ofp.OFPP_MAX:
            return
        up = ev.msg.reason != ofp.OFPPR_DELETE and self._port_is_up(dp, port)
        ports = self.up_ports.setdefault(dp.id, set())
        if up and port.port_no not in ports:
            ports.add(port.port_no)
            self.up_since[(dp.id, port.port_no)] = time.time()
            self.last_topology_change = time.time()
        elif not up and port.port_no in ports:
            ports.discard(port.port_no)
            self.up_since.pop((dp.id, port.port_no), None)
            self.links = set(l for l in self.links if (l[0], l[1]) != (dp.id, port.port_no)
                             and (l[2], l[3]) != (dp.id, port.port_no))
            self.hosts = dict((a, h) for a, h in self.hosts.items() if h != (dp.id, port.port_no))
            self._recompute("port %d of switch %d went down" % (port.port_no, dp.id),
                            reroute=True)

    # ── links ───────────────────────────────────────────────────────────────────────────────

    @set_ev_cls(topo_event.EventLinkAdd)
    def _link_add(self, ev):
        link = (ev.link.src.dpid, ev.link.src.port_no, ev.link.dst.dpid, ev.link.dst.port_no)
        if link in self.links:
            return
        self.links.add(link)
        self.last_topology_change = time.time()
        ends = ((link[0], link[1]), (link[2], link[3]))
        self.hosts = dict((a, h) for a, h in self.hosts.items() if h not in ends)
        self._recompute("a link %d:%d -> %d:%d was found" % link)

    @set_ev_cls(topo_event.EventLinkDelete)
    def _link_delete(self, ev):
        link = (ev.link.src.dpid, ev.link.src.port_no, ev.link.dst.dpid, ev.link.dst.port_no)
        if link not in self.links:
            return
        self.links.discard(link)
        self._recompute("the link %d:%d -> %d:%d went" % link, reroute=True)

    # ── flows: read, reconcile, send ────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats(self, ev):
        dp = ev.msg.datapath
        got = self.reading.setdefault(dp.id, [])
        for stat in ev.msg.body:
            got.append(self._flow_of(dp, stat))
        if ev.msg.flags & dp.ofproto.OFPMPF_REPLY_MORE:
            return
        current = self.reading.pop(dp.id)
        self.flows[dp.id] = dict(((t, p, m), (a, c)) for (t, p, m, a, c) in current
                                 if logic.is_ours(c))
        self.others[dp.id] = dict(((t, p, m), c) for (t, p, m, a, c) in current
                                  if not logic.is_ours(c))
        for address, at in sorted(logic.hosts_from_flows(dp.id, current).items()):
            self.hosts.setdefault(address, at)
        self.read_done.add(dp.id)
        self.logger.info("%s: switch %d read: %d own flows, %d of other owners", NAME, dp.id,
                         len(self.flows[dp.id]), len(self.others[dp.id]))
        self._recompute("switch %d connected and its flows were read" % dp.id)

    @staticmethod
    def _flow_of(dp, stat):
        """`(table, priority, match, actions, cookie)` of a flow as read, in fabric_logic's
        terms."""
        parser, ofp = dp.ofproto_parser, dp.ofproto
        match = []
        for field, value in stat.match.items():
            if field in ("ipv4_dst", "ipv6_dst") and not isinstance(value, tuple):
                found = logic.address_match(value)
                value = found[2] if found is not None else value
            match.append((field, value))
        actions = []
        for inst in stat.instructions:
            if isinstance(inst, parser.OFPInstructionGotoTable):
                actions.append(("GOTO", inst.table_id))
            elif isinstance(inst, parser.OFPInstructionActions) \
                    and inst.type == ofp.OFPIT_APPLY_ACTIONS:
                for act in inst.actions:
                    if isinstance(act, parser.OFPActionOutput):
                        actions.append(logic.CONTROLLER if act.port == ofp.OFPP_CONTROLLER
                                       else ("OUTPUT", act.port))
                    else:
                        actions.append(("OTHER", type(act).__name__))
            else:
                actions.append(("OTHER", type(inst).__name__))
        return (stat.table_id, stat.priority, tuple(sorted(match)), tuple(actions), stat.cookie)

    def _recompute(self, why, reroute=False):
        """Every served switch's desired flows from the topology and hosts, and the difference
        sent: the punt and DELIVER flows at once; TRANSIT flows once every connected switch is
        read and the topology has settled, or at once on a reroute; the app's own extras
        removed only once it has settled."""
        self.counters["recomputes"] += 1
        if reroute:
            self.counters["reroutes"] += 1
        served = [d for d in self.served() if d in self.read_done]
        graph = logic.graph_of(self.links, self.up_ports, served)
        desired, problems = logic.desired_flows(self.config, graph, self.hosts)
        self.problems = problems
        # Until every connected switch's flows are read, the graph is partial: a path over it
        # is not the fabric's, so only a reroute acts before then.
        complete = len(served) == len(self.served())
        settled = complete and time.time() - self.last_topology_change >= self._settle_s()
        held = 0
        for dpid in served:
            mine = self.flows.get(dpid, {})
            current = [k + v for k, v in mine.items()]
            current += [k + ((), c) for k, c in self.others.get(dpid, {}).items()]
            diff = logic.difference(desired.get(dpid, {}), current)
            dp = self.datapaths[dpid]
            for key, actions, value in diff["add"]:
                # A TRANSIT flow (the one kind a path decides) is added or changed once the
                # topology has settled, so a path computed while discovery is still finding
                # links never moves a flow that forwards; at once on a reroute (a link or switch
                # went: the old path is gone). The punt flows and a host's own DELIVER flow
                # depend on no path, and go at once.
                if logic.kind_of(value) == logic.TRANSIT and not (settled or reroute):
                    held += 1
                    continue
                self._send(dp, key, actions, value, dp.ofproto.OFPFC_ADD)
            if settled:
                for key, value in diff["delete"]:
                    self._send(dp, key, (), value, dp.ofproto.OFPFC_DELETE_STRICT)
            else:
                held += len(diff["delete"])
            self.problems = self.problems + ["switch %d: %s" % (dpid, c)
                                             for c in diff["conflicts"]]
        self.held = held
        self.logger.info("%s: recomputed (%s): %d switches served, %d hosts, %d changes and "
                         "removals held until the topology settles", NAME, why, len(served),
                         len(self.hosts), held)

    def _send(self, dp, key, actions, value, command):
        parser, ofp = dp.ofproto_parser, dp.ofproto
        table, priority, match = key
        fields = dict(match)
        if command == ofp.OFPFC_DELETE_STRICT:
            dp.send_msg(parser.OFPFlowMod(dp, cookie=value, cookie_mask=EXACT, table_id=table,
                                          command=command, priority=priority,
                                          out_port=ofp.OFPP_ANY,
                                          out_group=ofp.OFPG_ANY,
                                          match=parser.OFPMatch(**fields)))
            self.flows.get(dp.id, {}).pop(key, None)
            self.counters["flows_removed"] += 1
            self.logger.info("%s: switch %d: removed table %d priority %d %s", NAME, dp.id,
                             table, priority, fields)
            return
        inst = []
        for act in actions:
            if act[0] == "GOTO":
                inst.append(parser.OFPInstructionGotoTable(act[1]))
            elif act == logic.CONTROLLER:
                inst.append(parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, [
                    parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]))
            else:
                inst.append(parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, [
                    parser.OFPActionOutput(act[1])]))
        dp.send_msg(parser.OFPFlowMod(dp, cookie=value, table_id=table, command=command,
                                      priority=priority, buffer_id=ofp.OFP_NO_BUFFER,
                                      match=parser.OFPMatch(**fields), instructions=inst))
        self.flows.setdefault(dp.id, {})[key] = (tuple(actions), value)
        self.counters["flows_added"] += 1
        self.logger.info("%s: switch %d: sent table %d priority %d %s -> %s", NAME, dp.id,
                         table, priority, fields, list(actions))

    def _settle_s(self):
        return self.config["settle_s"] if self.config else logic.DEFAULTS["settle_s"]

    def _settle_timer(self):
        while True:
            hub.sleep(TICK_S)
            if self.held and \
                    time.time() - self.last_topology_change >= self._settle_s():
                self.send_event(self.name, EventSettleCheck())

    @set_ev_cls(EventSettleCheck)
    def _settled(self, ev):
        if self.held:
            self._recompute("the topology settled")

    @set_ev_cls(ofp_event.EventOFPErrorMsg, MAIN_DISPATCHER)
    def _error(self, ev):
        msg = ev.msg
        kept = self.errors.setdefault(msg.datapath.id, [])
        kept.append("type %d code %d" % (msg.type, msg.code))
        del kept[:-ERRORS_KEPT]
        self.logger.warning("%s: switch %d refused a message: type %d code %d", NAME,
                            msg.datapath.id, msg.type, msg.code)

    # ── packets ─────────────────────────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        if not logic.handles_packet_in(msg.cookie):     # OpenFlow 1.3's packet-in carries it
            self.counters["packet_in_others"] += 1
            return
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == logic.ETH_LLDP:
            return
        if logic.tables_for(self.config, dp.id) is None or dp.id not in self.read_done:
            return
        self.counters["packet_in"] += 1
        in_port = msg.match["in_port"]
        now = time.time()
        edges = logic.edge_ports(self.up_ports, self.links, self.up_since, now,
                                 self._settle_s())
        at_edge = in_port in edges.get(dp.id, [])
        source, target = self._addresses(pkt)
        if at_edge and source is not None and logic.address_match(source) is not None:
            text = logic.address_match(source)[2]
            if self.hosts.get(text) != (dp.id, in_port):
                self.hosts[text] = (dp.id, in_port)
                self._recompute("host %s learned at %d:%d" % (text, dp.id, in_port))
        known = logic.address_match(target) if target is not None else None
        if known is not None and known[2] in self.hosts:
            at, port = self.hosts[known[2]]
            if at in self.datapaths and (at, port) != (dp.id, in_port):
                self._packet_out(self.datapaths[at], port, msg.data)
                self.counters["delivered"] += 1
            return
        if not at_edge:
            self.counters["relay_refused_not_edge"] += 1
            return
        if self.relay.seen(hashlib.sha256(msg.data).hexdigest(), now):
            self.counters["relay_dropped_repeat"] += 1
            return
        self.counters["relayed"] += 1
        for dpid in sorted(edges):
            if dpid not in self.datapaths or logic.tables_for(self.config, dpid) is None:
                continue
            for port in edges[dpid]:
                if (dpid, port) != (dp.id, in_port):
                    self._packet_out(self.datapaths[dpid], port, msg.data)

    @staticmethod
    def _addresses(pkt):
        """`(source, target)` addresses of a frame: ARP's sender and target, or the IP
        header's; None for one it does not carry."""
        found = pkt.get_protocol(arp.arp)
        if found is not None:
            return found.src_ip, found.dst_ip
        for kind in (ipv4.ipv4, ipv6.ipv6):
            found = pkt.get_protocol(kind)
            if found is not None:
                return found.src, found.dst
        return None, None

    @staticmethod
    def _packet_out(dp, port, data):
        parser, ofp = dp.ofproto_parser, dp.ofproto
        dp.send_msg(parser.OFPPacketOut(dp, buffer_id=ofp.OFP_NO_BUFFER,
                                        in_port=ofp.OFPP_CONTROLLER,
                                        actions=[parser.OFPActionOutput(port)], data=data))

    # ── what REST shows ─────────────────────────────────────────────────────────────────────

    def health(self):
        served = self.served()
        unserved = sorted(d for d in self.datapaths if d not in served)
        problems = list(self.problems)
        if self.config is None:
            problems.insert(0, "%s, and none was pushed (PUT %s/config): no switch is served"
                            % (self.start_error, PREFIX))
        problems += ["switch %d is connected and the config names no tables for it: not "
                     "served" % d for d in unserved]
        problems += ["switch %d refused: %s" % (d, ", ".join(e)) for d, e in
                     sorted(self.errors.items()) if e]
        return {"ok": not problems, "app": NAME, "version": VERSION,
                "configured": self.config is not None, "start_config": dict(self.start),
                "switches": len(self.datapaths),
                "served": len(served), "links": len(self.links), "hosts": len(self.hosts),
                "held_until_settled": self.held, "problems": problems,
                "counters": dict(self.counters)}

    def state(self):
        now = time.time()
        edges = logic.edge_ports(self.up_ports, self.links, self.up_since, now,
                                 self._settle_s())
        served = [d for d in self.served() if d in self.read_done]
        graph = logic.graph_of(self.links, self.up_ports, served)
        return {"switches": sorted(self.datapaths), "served": served,
                "links": [list(l) for l in sorted(self.links)],
                "graph": dict((str(d), dict((str(n), p) for n, p in sorted(graph[d].items())))
                              for d in sorted(graph)),
                "edge_ports": dict((str(d), p) for d, p in sorted(edges.items())),
                "hosts": dict((a, list(h)) for a, h in sorted(self.hosts.items())),
                "own_flows": dict((str(d), len(f)) for d, f in sorted(self.flows.items())),
                "counters": dict(self.counters)}


class FabricRest(ControllerBase):
    """The app's REST, under PREFIX (the manifest's `rest`)."""

    def __init__(self, req, link, data, **config):
        super(FabricRest, self).__init__(req, link, data, **config)
        self.app = data["fabric_app"]

    @staticmethod
    def _json(body, status=200):
        return Response(status=status, content_type="application/json", charset="utf-8",
                        body=json.dumps(body, sort_keys=True).encode("utf-8"))

    @route(NAME, PREFIX + "/health", methods=["GET"])
    def health(self, req, **_kwargs):
        return self._json(self.app.health())

    @route(NAME, PREFIX + "/state", methods=["GET"])
    def state(self, req, **_kwargs):
        return self._json(self.app.state())

    @route(NAME, PREFIX + "/config", methods=["GET"])
    def get_config(self, req, **_kwargs):
        config = self.app.config
        if config is None:
            return self._json({"configured": False})
        shown = {"switches": dict((str(d), {"forward_table": t[0], "punt_table": t[1]})
                                  for d, t in sorted(config["switches"].items())),
                 "default_tables": None if config["default_tables"] is None else {
                     "forward_table": config["default_tables"][0],
                     "punt_table": config["default_tables"][1]},
                 "settle_s": config["settle_s"], "dedup_s": config["dedup_s"]}
        return self._json({"configured": True, "config": shown})

    @route(NAME, PREFIX + "/config", methods=["PUT"])
    def put_config(self, req, **_kwargs):
        try:
            data = json.loads(req.body.decode("utf-8"))
        except ValueError as exc:
            return self._json({"ok": False, "error": "the body is not JSON (%s)" % exc}, 400)
        problems = self.app.set_config(data)
        if problems:
            return self._json({"ok": False, "error": "; ".join(problems)}, 400)
        return self._json({"ok": True, "error": ""})
