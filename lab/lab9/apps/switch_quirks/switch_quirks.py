"""switch_quirks 1.0.0: each switch's pipeline specifics as a managed app (C2670; the SDN platform
design revision 6, section 12, "the compile step"; loaded second, after of_versions). A Ryu 4.34
app written for Python 3.5 and parsing as 3.9 (r7, section 11c.6). Its logic is
`quirks_logic`, plain data; this module is the wiring:

- **the config** is read AT LOAD from the start-time file Mercury compiled from each switch's
  platform profile and staged beside this version (`mercury_app.start_config`; decision K9;
  C2760): each switch's forward, punt and meter tables, by DPID. It is the only config: while it
  is not in force no switch is served and `/health` says why (the SDK not importable, the file
  absent, unreadable or refused);
- **switch connect** (`EventOFPStateChange` to MAIN): an OpenFlow 1.3 switch the config names
  has its flows read and is RECONCILED as they arrive (`quirks_logic.difference`): its missing
  pipeline flows added, a stale one of the app's own removed, another owner's never touched;
- **switch leave** (to DEAD): what it held is forgotten;
- **errors**: each switch's last refusals are kept and shown by `/health`;
- **REST** (under `/switch_quirks`): `GET /health` (read by Mercury's post-check) and
  `GET /tables`, each switch's tables, for the other apps and for Mercury.
"""

import json

from ryu.app.wsgi import ControllerBase, Response, WSGIApplication, route
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import DEAD_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_0, ofproto_v1_3

import quirks_logic as logic

try:
    import mercury_app
    HAVE_SDK = True
except ImportError:                     # the SDK is not deployed beside the app: /health says so
    HAVE_SDK = False

NAME = "switch_quirks"
VERSION = "1.0.0"
PREFIX = "/" + NAME
#: How many refusals a switch keeps for /health.
ERRORS_KEPT = 10
#: A removal's cookie mask: the flow's own cookie exactly, so no other owner's flow matches.
EXACT = 0xffffffffffffffff


class SwitchQuirks(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION, ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"wsgi": WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(SwitchQuirks, self).__init__(*args, **kwargs)
        self.datapaths = {}             # dpid -> datapath
        self.reading = {}               # dpid -> flows read so far, while a read is in parts
        self.reconciled = set()         # the switches reconciled since they connected
        self.problems = {}              # dpid -> [words]
        self.errors = {}                # dpid -> [words]
        self.counters = {"flows_added": 0, "flows_removed": 0, "conflicts": 0}
        kwargs["wsgi"].register(QuirksRest, {"quirks_app": self})
        answer = mercury_app.start_config(NAME, VERSION) if HAVE_SDK else None
        self.config, self.start_error = logic.from_start_config(answer)
        self.start = {"read": self.config is not None, "error": self.start_error,
                      "path": (answer or {}).get("path", ""),
                      "sha256": (answer or {}).get("sha256", "")}
        if self.config is None:
            self.logger.warning("%s: %s; no switch is served", NAME, self.start_error)
        else:
            self.logger.info("%s: config read from %s: %d switches named", NAME,
                             self.start["path"], len(self.config["switches"]))

    # ── switches ────────────────────────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change(self, ev):
        dp = ev.datapath
        if dp.id is None:
            return
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
            self.reconciled.discard(dp.id)
            self.problems.pop(dp.id, None)
            tables = logic.tables_for(self.config, dp.id)
            if tables is None:
                return
            _flows, problems = logic.desired_flows(tables, dp.ofproto.OFP_VERSION)
            if problems or dp.ofproto.OFP_VERSION == logic.OF10:
                # OpenFlow 1.0: one table, nothing to install, nothing to read.
                self.problems[dp.id] = problems
                self.reconciled.add(dp.id)
                return
            parser = dp.ofproto_parser
            self.reading[dp.id] = []
            dp.send_msg(parser.OFPFlowStatsRequest(dp, 0, dp.ofproto.OFPTT_ALL,
                                                   dp.ofproto.OFPP_ANY, dp.ofproto.OFPG_ANY,
                                                   0, 0, parser.OFPMatch()))
        elif ev.state == DEAD_DISPATCHER and self.datapaths.get(dp.id) is dp:
            del self.datapaths[dp.id]
            self.reconciled.discard(dp.id)
            self.reading.pop(dp.id, None)
            self.problems.pop(dp.id, None)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats(self, ev):
        dp = ev.msg.datapath
        if dp.id not in self.reading:
            return
        for stat in ev.msg.body:
            self.reading[dp.id].append(self._flow_of(dp, stat))
        if ev.msg.flags & dp.ofproto.OFPMPF_REPLY_MORE:
            return
        current = self.reading.pop(dp.id)
        tables = logic.tables_for(self.config, dp.id)
        flows, problems = logic.desired_flows(tables, dp.ofproto.OFP_VERSION)
        diff = logic.difference(flows, current)
        for key, actions, value in diff["add"]:
            self._send(dp, key, actions, value, dp.ofproto.OFPFC_ADD)
        for key, value in diff["delete"]:
            self._send(dp, key, (), value, dp.ofproto.OFPFC_DELETE_STRICT)
        self.counters["conflicts"] += len(diff["conflicts"])
        self.problems[dp.id] = problems + diff["conflicts"]
        self.reconciled.add(dp.id)
        self.logger.info("%s: switch %d reconciled: %d added, %d removed, %d conflicts", NAME,
                         dp.id, len(diff["add"]), len(diff["delete"]), len(diff["conflicts"]))

    @staticmethod
    def _flow_of(dp, stat):
        """`(table, priority, match, actions, cookie)` of a flow as read, in quirks_logic's
        terms."""
        parser, ofp = dp.ofproto_parser, dp.ofproto
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
        return (stat.table_id, stat.priority, tuple(sorted(stat.match.items())),
                tuple(actions), stat.cookie)

    def _send(self, dp, key, actions, value, command):
        parser, ofp = dp.ofproto_parser, dp.ofproto
        table, priority, match = key
        fields = dict(match)
        if command == ofp.OFPFC_DELETE_STRICT:
            dp.send_msg(parser.OFPFlowMod(dp, cookie=value, cookie_mask=EXACT, table_id=table,
                                          command=command, priority=priority,
                                          out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
                                          match=parser.OFPMatch(**fields)))
            self.counters["flows_removed"] += 1
            return
        inst = []
        for act in actions:
            if act[0] == "GOTO":
                inst.append(parser.OFPInstructionGotoTable(act[1]))
            else:
                inst.append(parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, [
                    parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]))
        dp.send_msg(parser.OFPFlowMod(dp, cookie=value, table_id=table, command=command,
                                      priority=priority, buffer_id=ofp.OFP_NO_BUFFER,
                                      match=parser.OFPMatch(**fields), instructions=inst))
        self.counters["flows_added"] += 1
        self.logger.info("%s: switch %d: sent table %d priority %d %s -> %s", NAME, dp.id,
                         table, priority, fields, list(actions))

    @set_ev_cls(ofp_event.EventOFPErrorMsg, MAIN_DISPATCHER)
    def _error(self, ev):
        msg = ev.msg
        kept = self.errors.setdefault(msg.datapath.id, [])
        kept.append("type %d code %d" % (msg.type, msg.code))
        del kept[:-ERRORS_KEPT]
        self.logger.warning("%s: switch %d refused a message: type %d code %d", NAME,
                            msg.datapath.id, msg.type, msg.code)

    # ── what REST shows ─────────────────────────────────────────────────────────────────────

    def health(self):
        out = logic.health(self.config, self.start_error, sorted(self.datapaths),
                           self.reconciled, self.problems, self.errors)
        out.update({"app": NAME, "version": VERSION, "start_config": dict(self.start),
                    "counters": dict(self.counters)})
        return out


class QuirksRest(ControllerBase):
    """The app's REST, under PREFIX (the manifest's `rest`)."""

    def __init__(self, req, link, data, **config):
        super(QuirksRest, self).__init__(req, link, data, **config)
        self.app = data["quirks_app"]

    @staticmethod
    def _json(body):
        return Response(status=200, content_type="application/json", charset="utf-8",
                        body=json.dumps(body, sort_keys=True).encode("utf-8"))

    @route(NAME, PREFIX + "/health", methods=["GET"])
    def health(self, req, **_kwargs):
        return self._json(self.app.health())

    @route(NAME, PREFIX + "/tables", methods=["GET"])
    def tables(self, req, **_kwargs):
        return self._json(logic.tables_view(self.app.config))
