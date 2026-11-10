"""dns_blacklist v0: Lab 9 Objective 3 as a controller app (the DNS blacklist; docs/LAB9_SDN_GAP.md,
A3). A Ryu 4.34 app on OpenFlow 1.3, written for Python 3.5, the controller's oldest measured
interpreter (C2646). The logic is plain data in `blacklist_logic`, the wire format in
`blacklist_wire`; this module is the wiring:

- **switch connect** (`EventOFPStateChange` to MAIN): the switch's ports and the app's own
  flows (read by its cookie) are read, and once both are in, the switch is RECONCILED: the
  steering flows (UDP 53 to the controller, IPv4 and IPv6, per edge port, in the forward table,
  `blacklist_logic`'s docstring) missing are added and the app's own extras removed; nothing
  else is touched. Ports going up or down and links found or lost (`ryu.topology`'s events)
  reconcile again;
- **packet-in carrying the app's cookie** (a query its own flow sent; every other packet-in is
  another app's and is left alone): the frame and its question are read (`blacklist_wire`);
  the name's verdict comes from the cache, or from the verdict service, asked FROM THE
  CONTROLLER through `mercury_app.egress("verdict_service", ...)` on a green thread of its own,
  so the app's event loop never waits on the network; the answer comes back as an event;
- **the decision** (`blacklist_logic.decide`): an allowed query is RE-INJECTED unchanged into
  the same switch's tables from the controller (packet-out, `in_port` CONTROLLER, output
  TABLE), so it takes the path every other packet takes (fabric_forwarding's flows) and the
  resolver's reply comes back on the normal path; or, when `upstream` is configured, sent out
  of that switch port. A blocked query is answered with a reply carrying the block page's
  address (the bonus) when one is configured, out of the port it came in on, or dropped;
- **bounds:** each lookup has a deadline (`verdict_service.timeout_s`, 2 s by default), swept
  every `TICK_S`; a query still waiting then follows the fail mode, and the SDK's own timeout
  is the same number. At most `MAX_LOOKUPS` names are asked at once and `MAX_WAITING` queries
  wait on one; the cache holds at most `cache.max_entries` names;
- **errors:** each switch's last refusals are kept and shown by `/health`.

**The config** is read AT LOAD from the start-time file Mercury's deploy compiled and staged
(`mercury_app.start_config`, C2729): the forward tables from each switch's platform profile
(the manifest's `compiled`), the schema's defaults for the rest. `PUT /dns_blacklist/config`
can replace it. While no config is in force, no switch is served, a query the app's flows
still send is forwarded unchecked (the default fail mode, open), and `/health` says why.

**REST** (under `/dns_blacklist`): `GET /health` (the counts of queries, allowed, blocked,
verdict errors and cache hits, and the verdict service's state), `GET` and `PUT /config`, `GET
/state` (the switches, their edge ports and the app's flows, the cache and lookups in flight,
and the last decisions).
"""

import hashlib
import json
import time

from ryu.app.wsgi import ControllerBase, Response, WSGIApplication, route
from ryu.base import app_manager
from ryu.controller import event, ofp_event
from ryu.controller.handler import DEAD_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_3
from ryu.topology import event as topo_event

import blacklist_logic as logic
import blacklist_wire as wire

try:
    import mercury_app
    HAVE_SDK = True
except ImportError:                     # the SDK is not deployed beside the app: /health says so
    HAVE_SDK = False

NAME = "dns_blacklist"
VERSION = "0.1.0"
PREFIX = "/" + NAME
#: How often the deadline sweep looks (it acts only through an event, on the app's own thread).
TICK_S = 0.25
#: How many refusals a switch keeps, and how many decisions /state shows.
ERRORS_KEPT = 10
DECISIONS_KEPT = 20
#: A removal's cookie mask: the flow's own cookie exactly, so no other owner's flow matches.
EXACT = 0xffffffffffffffff


class EventVerdict(event.EventBase):
    """A lookup's answer, handled on the app's own event thread."""

    def __init__(self, name, answer, seconds):
        super(EventVerdict, self).__init__()
        self.domain, self.answer, self.seconds = name, answer, seconds


class EventTick(event.EventBase):
    """The deadline sweep's tick, handled on the app's own event thread."""


class DnsBlacklist(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"wsgi": WSGIApplication}
    _EVENTS = [EventVerdict, EventTick]

    def __init__(self, *args, **kwargs):
        super(DnsBlacklist, self).__init__(*args, **kwargs)
        self.config = None
        self.datapaths = {}             # dpid -> datapath
        self.up_ports = {}              # dpid -> set of ports up
        self.links = set()              # (src_dpid, src_port, dst_dpid, dst_port)
        self.flows = {}                 # dpid -> {key: (actions, cookie)}: the app's own
        self.reading = {}               # dpid -> flows read so far, while a read is in parts
        self.ports_read, self.flows_read = set(), set()
        self.errors = {}                # dpid -> [words]
        self.cache = logic.Cache(logic.DEFAULTS["max_entries"], logic.DEFAULTS["ttl_cap_s"])
        self.pending = logic.Pending()
        self.recent = logic.Recent()
        self.decisions = []
        self.answers = {}               # verdict -> the last answer that gave it, for the demo
        self.service = {"state": "not asked yet", "error": "", "since": None}
        self.lookup_s = {"last": None, "max": None}
        self.counters = dict((k, 0) for k in (
            "queries", "allowed", "blocked", "verdict_errors", "cache_hits", "lookups",
            "timeouts", "overflow", "unparsed", "answered", "dropped", "fail_open",
            "fail_closed", "transit", "flows_added", "flows_removed"))
        kwargs["wsgi"].register(BlacklistRest, {"blacklist_app": self})
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
        hub.spawn(self._timer)

    # ── the config ──────────────────────────────────────────────────────────────────────────

    def set_config(self, data):
        config, problems = logic.parse_config(data)
        if config is None:
            return problems
        self._take_config(config, "a push")
        return []

    def _take_config(self, config, where):
        self.config = config
        self.cache = logic.Cache(config["max_entries"], config["ttl_cap_s"])
        self.logger.info("%s: config set from %s: %d switches named, fail %s, block page %s",
                         NAME, where, len(config["switches"]), config["fail_mode"],
                         config["block_ipv4"] or config["block_ipv6"] or "none (drop)")
        for dpid in sorted(self.datapaths):
            self._read(self.datapaths[dpid])

    def _fail_mode(self):
        return self.config["fail_mode"] if self.config else logic.DEFAULTS["fail_mode"]

    def served(self):
        return sorted(d for d in self.datapaths if logic.table_for(self.config, d) is not None)

    # ── switches, ports and links ───────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change(self, ev):
        dp = ev.datapath
        if dp.id is None:
            return
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
            self._read(dp)
        elif ev.state == DEAD_DISPATCHER and self.datapaths.get(dp.id) is dp:
            del self.datapaths[dp.id]
            for held in (self.up_ports, self.flows, self.reading):
                held.pop(dp.id, None)
            self.ports_read.discard(dp.id)
            self.flows_read.discard(dp.id)
            self.links = set(l for l in self.links if dp.id not in (l[0], l[2]))

    def _read(self, dp):
        parser, ofp = dp.ofproto_parser, dp.ofproto
        self.ports_read.discard(dp.id)
        self.flows_read.discard(dp.id)
        dp.send_msg(parser.OFPPortDescStatsRequest(dp, 0))
        self.reading[dp.id] = []
        dp.send_msg(parser.OFPFlowStatsRequest(dp, 0, ofp.OFPTT_ALL, ofp.OFPP_ANY, ofp.OFPG_ANY,
                                               logic.COOKIE_PREFIX, logic.COOKIE_MASK,
                                               parser.OFPMatch()))

    @staticmethod
    def _port_is_up(dp, port):
        ofp = dp.ofproto
        return not (port.state & ofp.OFPPS_LINK_DOWN) and not (port.config & ofp.OFPPC_PORT_DOWN)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def _port_desc(self, ev):
        dp = ev.msg.datapath
        self.up_ports[dp.id] = set(p.port_no for p in ev.msg.body
                                   if p.port_no <= dp.ofproto.OFPP_MAX
                                   and self._port_is_up(dp, p))
        self.ports_read.add(dp.id)
        self._reconcile(dp.id, "its ports were read")

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status(self, ev):
        dp, port = ev.msg.datapath, ev.msg.desc
        ofp = dp.ofproto
        if port.port_no > ofp.OFPP_MAX:
            return
        up = ev.msg.reason != ofp.OFPPR_DELETE and self._port_is_up(dp, port)
        ports = self.up_ports.setdefault(dp.id, set())
        if up != (port.port_no in ports):
            (ports.add if up else ports.discard)(port.port_no)
            self._reconcile(dp.id, "port %d went %s" % (port.port_no, "up" if up else "down"))

    @set_ev_cls(topo_event.EventLinkAdd)
    def _link_add(self, ev):
        self._link(ev.link, True)

    @set_ev_cls(topo_event.EventLinkDelete)
    def _link_delete(self, ev):
        self._link(ev.link, False)

    def _link(self, link, present):
        key = (link.src.dpid, link.src.port_no, link.dst.dpid, link.dst.port_no)
        if present == (key in self.links):
            return
        (self.links.add if present else self.links.discard)(key)
        for dpid in sorted(set([key[0], key[2]])):
            self._reconcile(dpid, "a link %d:%d -> %d:%d %s" % (key + (
                "was found" if present else "went",)))

    # ── the steering flows: read, reconcile, send ───────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats(self, ev):
        dp = ev.msg.datapath
        got = self.reading.setdefault(dp.id, [])
        for stat in ev.msg.body:
            if logic.is_ours(stat.cookie):
                got.append(self._flow_of(dp, stat))
        if ev.msg.flags & dp.ofproto.OFPMPF_REPLY_MORE:
            return
        self.flows[dp.id] = dict((k, (a, c)) for (k, a, c) in self.reading.pop(dp.id))
        self.flows_read.add(dp.id)
        self._reconcile(dp.id, "its flows were read")

    @staticmethod
    def _flow_of(dp, stat):
        """`(key, actions, cookie)` of a flow as read, in blacklist_logic's terms."""
        parser, ofp = dp.ofproto_parser, dp.ofproto
        actions = []
        for inst in stat.instructions:
            if isinstance(inst, parser.OFPInstructionActions) \
                    and inst.type == ofp.OFPIT_APPLY_ACTIONS:
                for act in inst.actions:
                    if isinstance(act, parser.OFPActionOutput) \
                            and act.port == ofp.OFPP_CONTROLLER:
                        actions.append(logic.CONTROLLER)
                    else:
                        actions.append(("OTHER", type(act).__name__))
            else:
                actions.append(("OTHER", type(inst).__name__))
        key = (stat.table_id, stat.priority, tuple(sorted(stat.match.items())))
        return key, tuple(actions), stat.cookie

    def _reconcile(self, dpid, why):
        """*dpid*'s steering flows made what its edge ports want, once its ports and flows are
        read: the missing added, the app's own extras removed, nothing else sent."""
        dp = self.datapaths.get(dpid)
        table = logic.table_for(self.config, dpid)
        if dp is None or table is None or dpid not in self.ports_read \
                or dpid not in self.flows_read:
            return
        ports = logic.edge_ports(self.up_ports, self.links, dpid)
        diff = logic.difference(logic.desired_flows(table, ports), self.flows.get(dpid, {}))
        for key, actions, value in diff["add"]:
            self._send(dp, key, actions, value, dp.ofproto.OFPFC_ADD)
        for key, value in diff["delete"]:
            self._send(dp, key, (), value, dp.ofproto.OFPFC_DELETE_STRICT)
        if diff["add"] or diff["delete"]:
            self.logger.info("%s: switch %d reconciled (%s): %d edge ports, %d flows added, "
                             "%d removed", NAME, dpid, why, len(ports), len(diff["add"]),
                             len(diff["delete"]))

    def _send(self, dp, key, actions, value, command):
        parser, ofp = dp.ofproto_parser, dp.ofproto
        table, priority, match = key
        fields = dict(match)
        if command == ofp.OFPFC_DELETE_STRICT:
            dp.send_msg(parser.OFPFlowMod(dp, cookie=value, cookie_mask=EXACT, table_id=table,
                                          command=command, priority=priority,
                                          out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
                                          match=parser.OFPMatch(**fields)))
            self.flows.get(dp.id, {}).pop(key, None)
            self.counters["flows_removed"] += 1
            return
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, [
            parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)])]
        dp.send_msg(parser.OFPFlowMod(dp, cookie=value, table_id=table, command=command,
                                      priority=priority, buffer_id=ofp.OFP_NO_BUFFER,
                                      match=parser.OFPMatch(**fields), instructions=inst))
        self.flows.setdefault(dp.id, {})[key] = (tuple(actions), value)
        self.counters["flows_added"] += 1

    @set_ev_cls(ofp_event.EventOFPErrorMsg, MAIN_DISPATCHER)
    def _error(self, ev):
        msg = ev.msg
        kept = self.errors.setdefault(msg.datapath.id, [])
        kept.append("type %d code %d" % (msg.type, msg.code))
        del kept[:-ERRORS_KEPT]
        self.logger.warning("%s: switch %d refused a message: type %d code %d", NAME,
                            msg.datapath.id, msg.type, msg.code)

    # ── queries ─────────────────────────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in(self, ev):
        msg = ev.msg
        if not logic.is_ours(msg.cookie):
            return                      # another app's punt: never this app's to forward
        dp = msg.datapath
        now = time.time()
        self.counters["queries"] += 1
        item = {"dpid": dp.id, "in_port": msg.match["in_port"], "data": msg.data,
                "frame": None, "query": None}
        digest = hashlib.sha256(msg.data).hexdigest()
        if self.recent.is_repeat(digest, now):
            # A query this app allowed, back from the next switch on a port not yet known as a
            # link: forwarded again, not asked again.
            self.counters["transit"] += 1
            self._forward(dp, msg.data)
            return
        item["frame"], why = wire.parse_frame(msg.data)
        if item["frame"] is not None:
            item["query"], why = wire.parse_query(item["frame"]["payload"])
        if item["query"] is None:
            self.counters["unparsed"] += 1
            self._act(item, logic.UNKNOWN, "not read: %s" % why, now)
            return
        name = item["query"]["name"]
        cached = self.cache.get(name, now)
        if cached is not None:
            self.counters["cache_hits"] += 1
            self._act(item, cached, "cache", now)
            return
        timeout = self.config["timeout_s"] if self.config else logic.DEFAULTS["timeout_s"]
        started = self.pending.start(name, item, now, timeout)
        if started == logic.Pending.ASK:
            self.counters["lookups"] += 1
            hub.spawn(self._lookup, name, timeout)
        elif started == logic.Pending.FULL:
            self.counters["overflow"] += 1
            self._act(item, logic.UNKNOWN, "lookups full", now)

    def _lookup(self, name, timeout):
        """On a green thread of its own: the verdict service asked about *name* from the
        controller, through the SDK's egress; its answer comes back as an EventVerdict."""
        started = time.time()
        if not HAVE_SDK:
            answer = {"ok": False, "error": logic.NO_SDK}
        else:
            try:
                answer = mercury_app.egress("verdict_service", path=logic.verdict_path(name),
                                            timeout=timeout, accept=logic.VERDICT_ACCEPT)
            except Exception as exc:    # EgressRefused, or a refused name: a verdict error
                answer = {"ok": False, "error": str(exc)}
        self.send_event(self.name, EventVerdict(name, answer, time.time() - started))

    @set_ev_cls(EventVerdict)
    def _verdict(self, ev):
        now = time.time()
        verdict, ttl, why = logic.read_verdict(ev.answer)
        self.lookup_s["last"] = round(ev.seconds, 3)
        self.lookup_s["max"] = max(self.lookup_s["max"] or 0, self.lookup_s["last"])
        if verdict == logic.UNKNOWN:
            self.counters["verdict_errors"] += 1
            if self.service["state"] != "down":
                self.service = {"state": "down", "error": why, "since": now}
            self.service["error"] = why
        elif self.service["state"] != "up":
            self.service = {"state": "up", "error": "", "since": now}
        # The JSON verdict as the service gave it (or why there was none), shown by /state.
        self.answers[verdict] = {"name": ev.domain, "at": round(now, 3), "why": why,
                                 "body": ev.answer.get("body") if ev.answer.get("ok")
                                 else None}
        self.cache.put(ev.domain, verdict, ttl, now)
        for item in self.pending.finish(ev.domain):
            self._act(item, verdict, "lookup" if verdict != logic.UNKNOWN else why, now)

    def _timer(self):
        while True:
            hub.sleep(TICK_S)
            if self.pending.size():
                self.send_event(self.name, EventTick())

    @set_ev_cls(EventTick)
    def _tick(self, ev):
        now = time.time()
        for _name, items in self.pending.expired(now):
            self.counters["timeouts"] += 1
            self.counters["verdict_errors"] += 1
            why = "no answer within the lookup's bound, %g s" % (
                self.config["timeout_s"] if self.config else logic.DEFAULTS["timeout_s"])
            if self.service["state"] != "down":
                self.service = {"state": "down", "error": why, "since": now}
            for item in items:
                self._act(item, logic.UNKNOWN, "no verdict within the lookup's bound", now)

    def _act(self, item, verdict, source, now):
        """*item* decided by *verdict* (`blacklist_logic.decide`) and sent, counted and kept."""
        dp = self.datapaths.get(item["dpid"])
        config = self.config or {"fail_mode": self._fail_mode(), "block_ipv4": None,
                                 "block_ipv6": None}
        decision = logic.decide(verdict, config)
        if decision == logic.ANSWER and item["query"] is None:
            decision = logic.DROP       # a frame not read cannot be answered
        if verdict == logic.UNKNOWN:
            self.counters["fail_open" if decision == logic.ALLOW else "fail_closed"] += 1
        if decision == logic.ALLOW:
            self.counters["allowed"] += 1
            if dp is not None:
                self.recent.allowed(hashlib.sha256(item["data"]).hexdigest(), now)
                self._forward(dp, item["data"])
        else:
            self.counters["blocked"] += 1
            if decision == logic.ANSWER and dp is not None:
                self.counters["answered"] += 1
                reply = wire.synthesise_reply(item["frame"], item["query"],
                                              config["block_ipv4"], config["block_ipv6"])
                self._packet_out(dp, item["in_port"], reply)
            else:
                self.counters["dropped"] += 1
        query = item["query"] or {}
        self.decisions.append({"name": query.get("name"), "type": query.get("type_name"),
                               "switch": item["dpid"], "port": item["in_port"],
                               "verdict": verdict, "decision": decision, "source": source,
                               "at": round(now, 3)})
        del self.decisions[:-DECISIONS_KEPT]
        self.logger.info("%s: switch %d port %d: %s %s is %s (%s): %s", NAME, item["dpid"],
                         item["in_port"], query.get("type_name", "?"), query.get("name", "?"),
                         verdict, source, decision)

    def _forward(self, dp, data):
        """An allowed query sent on unchanged: out of the upstream port when one is configured
        and its switch is connected, else re-injected into *dp*'s own tables."""
        upstream = self.config["upstream"] if self.config else None
        if upstream is not None and upstream[0] in self.datapaths:
            self._packet_out(self.datapaths[upstream[0]], upstream[1], data)
            return
        self._packet_out(dp, dp.ofproto.OFPP_TABLE, data)

    @staticmethod
    def _packet_out(dp, port, data):
        parser, ofp = dp.ofproto_parser, dp.ofproto
        dp.send_msg(parser.OFPPacketOut(dp, buffer_id=ofp.OFP_NO_BUFFER,
                                        in_port=ofp.OFPP_CONTROLLER,
                                        actions=[parser.OFPActionOutput(port)], data=data))

    # ── what REST shows ─────────────────────────────────────────────────────────────────────

    def health(self):
        served = self.served()
        problems = []
        if self.config is None:
            problems.append("%s, and none was pushed (PUT %s/config): no switch is served"
                            % (self.start_error, PREFIX))
        if not HAVE_SDK:
            problems.append(logic.NO_SDK + ", and no verdict can be asked")
        if self.service["state"] == "down":
            problems.append("the verdict service did not answer the last lookup (%s): a query "
                            "with no cached verdict is %s (fail %s)" % (
                                self.service["error"],
                                "forwarded unchecked" if self._fail_mode() == logic.FAIL_OPEN
                                else "blocked", self._fail_mode()))
        problems += ["switch %d is connected and the config names no table for it: not "
                     "served" % d for d in sorted(self.datapaths) if d not in served]
        upstream = self.config["upstream"] if self.config else None
        if upstream is not None and upstream[0] not in self.datapaths:
            problems.append("the upstream switch %d is not connected: allowed queries are "
                            "re-injected where they came in" % upstream[0])
        problems += ["switch %d refused: %s" % (d, ", ".join(e)) for d, e in
                     sorted(self.errors.items()) if e]
        return {"ok": not problems, "app": NAME, "version": VERSION,
                "configured": self.config is not None, "start_config": dict(self.start),
                "fail_mode": self._fail_mode(),
                "verdict_service": dict(self.service, lookup_seconds=dict(self.lookup_s)),
                "switches": len(self.datapaths), "served": len(served),
                "cache_entries": self.cache.size(), "lookups_in_flight": self.pending.size(),
                "problems": problems, "counters": dict(self.counters)}

    def state(self):
        return {"switches": sorted(self.datapaths), "served": self.served(),
                "edge_ports": dict((str(d), logic.edge_ports(self.up_ports, self.links, d))
                                   for d in sorted(self.datapaths)),
                "own_flows": dict((str(d), len(f)) for d, f in sorted(self.flows.items())),
                "links": [list(l) for l in sorted(self.links)],
                "cache_entries": self.cache.size(), "lookups_in_flight": self.pending.size(),
                "decisions": list(self.decisions), "last_answers": dict(self.answers),
                "counters": dict(self.counters)}

    def shown_config(self):
        config = self.config
        if config is None:
            return {"configured": False}
        shown = dict((k, config[k]) for k in ("timeout_s", "fail_mode", "ttl_cap_s",
                                              "max_entries", "block_ipv4", "block_ipv6"))
        shown["switches"] = dict((str(d), t) for d, t in sorted(config["switches"].items()))
        shown["default_table"] = config["default_table"]
        shown["upstream"] = list(config["upstream"]) if config["upstream"] else None
        return {"configured": True, "config": shown}


class BlacklistRest(ControllerBase):
    """The app's REST, under PREFIX (the manifest's `rest`)."""

    def __init__(self, req, link, data, **config):
        super(BlacklistRest, self).__init__(req, link, data, **config)
        self.app = data["blacklist_app"]

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
        return self._json(self.app.shown_config())

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
