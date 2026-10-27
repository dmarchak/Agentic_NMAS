"""The Ryu driver: Ryu's `ryu.app.ofctl_rest` (read from Ryu 4.34's source, PHASE8_PLAN 17.2).

What ofctl_rest offers, and what this driver reads of it:
- `GET /stats/switches`: the connected datapath ids, as integers (`test`, `switches`);
- `GET /stats/desc/<dpid>`, `/stats/flow/<dpid>`, `/stats/port/<dpid>`,
  `/stats/meterconfig/<dpid>`, `/stats/meter/<dpid>`, `/stats/meterfeatures/<dpid>`: each
  answers `{"<dpid in decimal>": ...}`, built by `ryu.lib.ofctl_v1_3`;
- `POST /stats/flowentry/add`, `/stats/flowentry/delete_strict`, `/stats/meterentry/add`,
  `/stats/meterentry/delete`: the body names the switch (`dpid`), and the answer is an empty
  200 once Ryu has SENT the message. The switch's own answer (an OpenFlow error) is never
  reported back, so a write's 200 says sent, not installed: Verify reads the table back.

What it reads of Ryu's topology REST (`ryu.app.rest_topology`, a separate application,
PHASE8_PLAN 17.1 S14; the lab's controller runs it with `--observe-links` since 2026-10-27):
- `GET /v1.0/topology/switches`: each switch, `{"dpid": "<16 hex>", "ports": [port]}`, a
  port `{"dpid", "port_no": "<8 hex>", "hw_addr", "name"}`;
- `GET /v1.0/topology/links`: `[{"src": port, "dst": port}]`, one entry per direction, found
  by Ryu's own LLDP (its chassis id `dpid:<16 hex>`, its port id the port number packed in
  four bytes, ryu/topology/switches.py `LLDPPacket`);
- `GET /v1.0/topology/hosts`: `[{"mac", "ipv4": [...], "ipv6": [...], "port": port}]`.
  **Ryu keeps a host until it restarts and records no time** (its `HostState` is a dict that
  only grows; a host that moved replaces its port, one that left stays), so a listed host is
  "listed by the controller", never "here now": the answer's `hosts_note` says so.
- **Without the application every topology call is Ryu's HTML 404** (captured,
  rest_no_switch.json), said as the application not running, never as no links. **Without
  `--observe-links`** the application answers, and its links are always empty (Ryu sends no
  LLDP): an empty link list between two or more switches is said with that possibility
  (`modules/sdn/topology.py`), never as a fabric with no cables.

What it does not offer:
- **no version**: no call answers one and the server sends no version header, so `test` says
  so rather than inventing one.

Ryu's quirks the translation answers:
- **Its match keys are OpenFlow 1.0's on the way out** (`ryu.lib.ofctl_v1_3.match_to_str`):
  `dl_src`, `dl_dst`, `dl_type`, `dl_vlan`, `nw_src`, `nw_dst`, `nw_proto`, and `tp_src` /
  `tp_dst` for TCP's and UDP's ports alike, so `ip_proto` decides which. A VLAN id comes back
  as a decimal string. Each is translated to its OXM name; a key it cannot translate is kept as
  Ryu wrote it, and such a flow cannot be sent back (a render refuses a non-OXM key).
- **Its actions are strings** (`OUTPUT:2`, `OUTPUT:CONTROLLER`, `METER:1`, `GOTO_TABLE:1`,
  `SET_FIELD: {eth_dst:...}`, `{"WRITE_ACTIONS": [...]}`), and a drop is an empty list
  (OpenFlow 1.0's `DROP` is read as the same). One it cannot translate is kept as `UNPARSED`
  with Ryu's text, never guessed at.
- **It reads a request body with Python's `ast.literal_eval`, not a JSON parser**, so JSON's
  `true`, `false` and `null` fail it (a 500 with a traceback, captured). A render therefore
  carries numbers, strings, lists and mappings only, and checks the body reads the same both
  ways before answering.
- **It drops what it does not know without a word**: an unknown match field or action is logged
  on the controller and left out of the message, so a flow would be installed broader than
  asked, or as a drop. A render refuses an unknown field or action instead (base.py).
"""

import ast
import json

from modules.sdn.drivers.base import (
    ACTION_FIELDS, UINT64_MAX, UNPARSED, ControllerDriver, Flow, Meter, MeterBand,
    MeterFeatures, PortStats, SpecError, dpid_hex, flow_from_spec, meter_from_spec, topo_host,
    topo_port)

#: Ryu's OpenFlow 1.0 match keys, and the OXM name each stands for.
_MATCH_FROM_RYU = {"dl_src": "eth_src", "dl_dst": "eth_dst", "dl_type": "eth_type",
                   "dl_vlan": "vlan_vid", "nw_src": "ipv4_src", "nw_dst": "ipv4_dst",
                   "nw_proto": "ip_proto"}
#: `tp_src`/`tp_dst` by the flow's IP protocol.
_TRANSPORT = {6: "tcp", 17: "udp"}
_NO_ARGUMENT = frozenset(k for k, fields in ACTION_FIELDS.items() if not fields)
_ONE_NUMBER = {"GOTO_TABLE": "table_id", "METER": "meter_id", "PUSH_VLAN": "ethertype",
               "PUSH_MPLS": "ethertype", "POP_MPLS": "ethertype", "PUSH_PBB": "ethertype",
               "SET_MPLS_TTL": "mpls_ttl", "SET_NW_TTL": "nw_ttl", "SET_QUEUE": "queue_id",
               "GROUP": "group_id"}

FLOW_ADD = "/stats/flowentry/add"
FLOW_MODIFY_STRICT = "/stats/flowentry/modify_strict"
FLOW_DELETE_STRICT = "/stats/flowentry/delete_strict"
METER_ADD = "/stats/meterentry/add"
METER_DELETE = "/stats/meterentry/delete"

SENT_NOTE = ("the controller sent it to the switch; Ryu's ofctl_rest does not report the "
             "switch's own answer, so read the table back to verify")

TOPOLOGY = "/v1.0/topology"
#: What a 404 from the topology REST means, said in place of "no links".
NO_TOPOLOGY_APP = ("the topology app is not running (start ryu-manager with --observe-links "
                   "and ryu.app.rest_topology)")
HOSTS_NOTE = ("Ryu keeps a host until the controller restarts and records no time, so a "
              "host listed is one it learned since then, not necessarily one there now")
LINKS_NOTE = ("none cabled, or the controller discovers none (Ryu discovers links only when "
              "run with --observe-links)")


def port_from_ryu(entry: dict) -> dict:
    """One of the topology REST's ports in the one shape (base.topo_port)."""
    if not isinstance(entry, dict):
        raise SpecError(f"a port is a mapping, not {entry!r}")
    return topo_port(entry.get("dpid"), entry.get("port_no"), entry.get("name"),
                     entry.get("hw_addr"))


def link_from_ryu(entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise SpecError(f"a link is a mapping, not {entry!r}")
    return {"src": port_from_ryu(entry.get("src")), "dst": port_from_ryu(entry.get("dst"))}


def host_from_ryu(entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise SpecError(f"a host is a mapping, not {entry!r}")
    return topo_host(entry.get("mac"), entry.get("ipv4"), entry.get("ipv6"),
                     port_from_ryu(entry.get("port")))


def _number(text):
    """An int from Ryu's decimal or hex text, or None."""
    try:
        return int(str(text).strip(), 0)
    except ValueError:
        return None


def match_from_ryu(match: dict) -> dict:
    """Ryu's match (OpenFlow 1.0 names where it uses them) as OXM field names."""
    proto = match.get("nw_proto", match.get("ip_proto"))
    out = {}
    for key, value in match.items():
        name = _MATCH_FROM_RYU.get(key, key)
        if key in ("tp_src", "tp_dst") and proto in _TRANSPORT:
            name = f"{_TRANSPORT[proto]}_{key[3:]}"
        if name == "vlan_vid" and isinstance(value, str) and value.isdigit():
            value = int(value)
        out[name] = value
    return out


def action_from_ryu(item):
    """One of Ryu's action strings (or its WRITE_ACTIONS mapping) as a normalised action;
    None for OpenFlow 1.0's DROP, which is no action at all."""
    if isinstance(item, dict):
        if set(item) == {"WRITE_ACTIONS"} and isinstance(item["WRITE_ACTIONS"], list):
            inner = [action_from_ryu(a) for a in item["WRITE_ACTIONS"]]
            return {"type": "WRITE_ACTIONS", "actions": [a for a in inner if a is not None]}
        return {"type": UNPARSED, "text": json.dumps(item, sort_keys=True)}
    text = str(item)
    if text == "DROP":
        return None
    name, sep, argument = text.partition(":")
    name, argument = name.strip(), argument.strip()
    if not sep and name in _NO_ARGUMENT:
        return {"type": name}
    if sep and name == "OUTPUT":
        port = _number(argument) if argument[:1].isdigit() else argument
        if port is not None and port != "":
            return {"type": "OUTPUT", "port": port}
    if sep and name in _ONE_NUMBER and _number(argument) is not None:
        return {"type": name, _ONE_NUMBER[name]: _number(argument)}
    if sep and name == "WRITE_METADATA":
        value, _slash, mask = argument.partition("/")
        if _number(value) is not None and (not mask or _number(mask) is not None):
            # Ryu prints the mask only when it is not zero (ofctl_v1_3.actions_to_str).
            return {"type": name, "metadata": _number(value),
                    "metadata_mask": _number(mask) if mask else 0}
    if sep and name == "SET_FIELD" and argument.startswith("{") and argument.endswith("}"):
        field, colon, value = argument[1:-1].partition(":")
        if colon and field.strip():
            value = value.strip()
            return {"type": name, "field": field.strip(),
                    "value": int(value) if value.isdigit() else value}
    return {"type": UNPARSED, "text": text}


def flow_from_ryu(dpid: int, entry: dict) -> Flow:
    actions = [action_from_ryu(a) for a in entry.get("actions") or []]
    return Flow(dpid=dpid, table_id=entry.get("table_id", 0), priority=entry.get("priority", 0),
                cookie=entry.get("cookie", 0), match=match_from_ryu(entry.get("match") or {}),
                actions=[a for a in actions if a is not None],
                idle_timeout=entry.get("idle_timeout", 0),
                hard_timeout=entry.get("hard_timeout", 0),
                packet_count=entry.get("packet_count"), byte_count=entry.get("byte_count"),
                duration_sec=entry.get("duration_sec"))


def _body(value: dict) -> str:
    """The exact text a write sends: JSON, keys sorted, that Ryu's `ast.literal_eval` reads as
    the same value (no true, false or null can be in it; checked, never assumed)."""
    text = json.dumps(value, sort_keys=True)
    try:
        same = ast.literal_eval(text) == json.loads(text)
    except (ValueError, SyntaxError):
        same = False
    if not same:
        raise SpecError("the request would not read the same to Ryu's parser")
    return text


class RyuDriver(ControllerDriver):
    kind = "ryu"
    label = "Ryu"
    status = "built"
    capabilities = frozenset({"read_topology", "read_flows", "read_port_stats", "read_meters",
                              "write_flows", "write_meters", "delete_flows"})
    #: ryu/topology/switches.py `LLDPPacket.CHASSIS_ID_FMT` (rendered by Ryu's own code:
    #: tests/fixtures/sdn/ryu/lldp_from_ryu.json).
    lldp_chassis_prefix = "dpid:"
    links_note = LINKS_NOTE
    write_routes = {("POST", FLOW_ADD): "write_flows",
                    ("POST", FLOW_MODIFY_STRICT): "write_flows",
                    ("POST", FLOW_DELETE_STRICT): "delete_flows",
                    ("POST", METER_ADD): "write_meters",
                    ("POST", METER_DELETE): "write_meters"}

    # ── reading an answer ───────────────────────────────────────────────────────────────────

    def _failure(self, got: dict, path: str, dpid=None) -> dict:
        """A non-2xx answer in words: which switch, which call, or the controller's own last
        line (a 500 is a Python traceback, whose last line names the exception)."""
        status, text = got["status"], (got.get("text") or "").strip()
        out = {"ok": False, "status": status}
        if status in (401, 403):
            out.update(refused=True, error=f"HTTP {status}: the controller refused the tool's "
                                           "credential")
        elif status == 404 and not text and dpid is not None:
            out.update(no_switch=True, error=f"HTTP 404: the controller has no switch {dpid} "
                                             f"({dpid_hex(dpid)})")
        elif status == 404:
            out["error"] = (f"HTTP 404: the controller has no call {path} (is the application "
                            "serving it loaded?)")
        elif status == 400:
            out["error"] = "HTTP 400: the controller refused the request as malformed"
        elif status == 501:
            out["error"] = ("HTTP 501: the switch's OpenFlow version does not support this "
                            "request")
        else:
            out["error"] = f"HTTP {status}"
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines and "html" not in got.get("content_type", ""):
                out["detail"] = lines[-1][:500]
        return out

    def _get(self, path: str, dpid=None):
        """`(data, None)` for a 200 with JSON, else `(None, failure)`."""
        got = self._http("GET", path)
        if not got.get("ok"):
            return None, got
        if got["status"] != 200:
            return None, self._failure(got, path, dpid)
        try:
            return json.loads(got["text"]), None
        except ValueError:
            return None, {"ok": False, "status": 200,
                          "error": f"HTTP 200 from {path} with a body that is not JSON"}

    def _per_switch(self, path: str, dpid: int):
        """The value of a `{"<dpid>": value}` answer for *dpid*, or a failure naming what the
        controller answered for instead."""
        data, failed = self._get(path, dpid)
        if failed:
            return None, failed
        if not isinstance(data, dict) or str(dpid) not in data:
            named = sorted(data) if isinstance(data, dict) else type(data).__name__
            return None, {"ok": False, "error": f"the controller answered {path} for {named}, "
                                                f"not switch {dpid}"}
        return data[str(dpid)], None

    # ── the reads ───────────────────────────────────────────────────────────────────────────

    def _switch_list(self):
        data, failed = self._get("/stats/switches")
        if failed:
            return None, failed
        if not isinstance(data, list) or not all(isinstance(d, int) for d in data):
            return None, {"ok": False, "error": "the controller's switch list is not a list "
                                                "of datapath ids"}
        return sorted(data), None

    def _test(self) -> dict:
        dpids, failed = self._switch_list()
        if failed:
            return failed
        return {"ok": True, "answers": True, "version": None,
                "version_note": "Ryu's ofctl_rest reports no version", "switch_count": len(dpids)}

    def _switches(self) -> dict:
        dpids, failed = self._switch_list()
        if failed:
            return failed
        return {"ok": True, "switches": [{"dpid": d, "dpid_hex": dpid_hex(d)} for d in dpids]}

    # ── the topology REST (ryu.app.rest_topology: switches, links, hosts) ───────────────────

    def _topology_get(self, what: str, parse):
        """`(items, None)` from `GET /v1.0/topology/<what>`, each parsed by *parse*, or
        `(None, failure)`; a 404 is the application not running, said so."""
        path = f"{TOPOLOGY}/{what}"
        got = self._http("GET", path)
        if not got.get("ok"):
            return None, got
        if got["status"] == 404:
            return None, {"ok": False, "status": 404, "no_topology_app": True,
                          "error": f"HTTP 404 from {path}: {NO_TOPOLOGY_APP}"}
        if got["status"] != 200:
            return None, self._failure(got, path)
        try:
            data = json.loads(got["text"])
        except ValueError:
            return None, {"ok": False, "status": 200,
                          "error": f"HTTP 200 from {path} with a body that is not JSON"}
        if not isinstance(data, list):
            return None, {"ok": False, "error": f"{path} answered a {type(data).__name__}, "
                                                "not a list"}
        try:
            return [parse(item) for item in data], None
        except SpecError as exc:
            return None, {"ok": False, "error": f"{path}: {exc}"}

    def _links(self) -> dict:
        links, failed = self._topology_get("links", link_from_ryu)
        return failed or {"ok": True, "links": links}

    def _hosts(self) -> dict:
        hosts, failed = self._topology_get("hosts", host_from_ryu)
        return failed or {"ok": True, "hosts": hosts, "hosts_note": HOSTS_NOTE}

    def _topology(self) -> dict:
        def switch(entry):
            if not isinstance(entry, dict):
                raise SpecError(f"a switch is a mapping, not {entry!r}")
            first = port_from_ryu({"dpid": entry.get("dpid"), "port_no": 0})
            return {"dpid": first["dpid"], "dpid_hex": first["dpid_hex"],
                    "ports": [port_from_ryu(p) for p in entry.get("ports") or []]}

        switches, failed = self._topology_get("switches", switch)
        if failed:
            return failed
        links, failed = self._topology_get("links", link_from_ryu)
        if failed:
            return failed
        hosts, failed = self._topology_get("hosts", host_from_ryu)
        if failed:
            return failed
        return {"ok": True, "switches": sorted(switches, key=lambda s: s["dpid"]),
                "links": links, "hosts": hosts, "hosts_note": HOSTS_NOTE,
                "links_note": LINKS_NOTE}

    def _switch_desc(self, dpid) -> dict:
        desc, failed = self._per_switch(f"/stats/desc/{dpid}", dpid)
        if failed:
            return failed
        return {"ok": True, "dpid": dpid, "desc": desc}

    def _flows(self, dpid) -> dict:
        entries, failed = self._per_switch(f"/stats/flow/{dpid}", dpid)
        if failed:
            return failed
        return {"ok": True, "dpid": dpid,
                "flows": [flow_from_ryu(dpid, e).as_dict() for e in entries]}

    def _port_stats(self, dpid) -> dict:
        entries, failed = self._per_switch(f"/stats/port/{dpid}", dpid)
        if failed:
            return failed
        keys = [k for k in PortStats.__dataclass_fields__ if k not in ("dpid", "port_no")]
        return {"ok": True, "dpid": dpid,
                "ports": [PortStats(dpid=dpid, port_no=e.get("port_no"),
                                    **{k: e.get(k, 0) for k in keys}).as_dict()
                          for e in entries]}

    def _meters(self, dpid) -> dict:
        configs, failed = self._per_switch(f"/stats/meterconfig/{dpid}", dpid)
        if failed:
            return failed
        stats, failed = self._per_switch(f"/stats/meter/{dpid}", dpid)
        if failed:
            return failed
        by_id = {s.get("meter_id"): s for s in stats}
        meters = []
        for config in configs:
            stat = by_id.pop(config.get("meter_id"), {})
            band_stats = stat.get("band_stats") or []
            bands = []
            for i, band in enumerate(config.get("bands") or []):
                counted = band_stats[i] if i < len(band_stats) else {}
                bands.append(MeterBand(type=band.get("type", ""), rate=band.get("rate", 0),
                                       burst_size=band.get("burst_size", 0),
                                       prec_level=band.get("prec_level"),
                                       packet_band_count=counted.get("packet_band_count"),
                                       byte_band_count=counted.get("byte_band_count")).as_dict())
            meters.append(self._meter(dpid, config.get("meter_id"), config.get("flags") or [],
                                      bands, stat))
        # A meter counted but not configured was added between the two reads: kept, with no
        # configuration, never dropped.
        for meter_id, stat in sorted(by_id.items(), key=lambda kv: str(kv[0])):
            meters.append(self._meter(dpid, meter_id, [], [], stat))
        return {"ok": True, "dpid": dpid, "meters": meters}

    @staticmethod
    def _meter(dpid, meter_id, flags, bands, stat) -> dict:
        return Meter(dpid=dpid, meter_id=meter_id, flags=list(flags), bands=bands,
                     flow_count=stat.get("flow_count"),
                     packet_in_count=stat.get("packet_in_count"),
                     byte_in_count=stat.get("byte_in_count"),
                     duration_sec=stat.get("duration_sec")).as_dict()

    def _meter_features(self, dpid) -> dict:
        entries, failed = self._per_switch(f"/stats/meterfeatures/{dpid}", dpid)
        if failed:
            return failed
        if not entries:
            return {"ok": True, "dpid": dpid, "features": None}
        first = entries[0]
        return {"ok": True, "dpid": dpid,
                "features": MeterFeatures(dpid=dpid, max_meter=first.get("max_meter", 0),
                                          band_types=list(first.get("band_types") or []),
                                          capabilities=list(first.get("capabilities") or []),
                                          max_bands=first.get("max_bands", 0),
                                          max_color=first.get("max_color", 0)).as_dict()}

    # ── the renders (no I/O) ────────────────────────────────────────────────────────────────

    @staticmethod
    def _rendered(path: str, body: dict) -> dict:
        return {"ok": True, "error": "", "method": "POST", "path": path, "body": _body(body)}

    def _render_add_flow(self, dpid, spec) -> dict:
        flow = flow_from_spec(dpid, spec)
        return self._rendered(FLOW_ADD, {
            "dpid": flow.dpid, "table_id": flow.table_id, "priority": flow.priority,
            "cookie": flow.cookie, "idle_timeout": flow.idle_timeout,
            "hard_timeout": flow.hard_timeout, "match": dict(flow.match),
            "actions": [dict(a) for a in flow.actions]})

    def _render_modify_flow_strict(self, dpid, spec) -> dict:
        """OFPFC_MODIFY_STRICT: the same body as an add, sent to modify_strict; the switch
        replaces the instructions of the flow with exactly this table, priority and match."""
        flow = flow_from_spec(dpid, spec)
        return self._rendered(FLOW_MODIFY_STRICT, {
            "dpid": flow.dpid, "table_id": flow.table_id, "priority": flow.priority,
            "cookie": flow.cookie, "idle_timeout": flow.idle_timeout,
            "hard_timeout": flow.hard_timeout, "match": dict(flow.match),
            "actions": [dict(a) for a in flow.actions]})

    def _render_delete_flow_strict(self, dpid, spec) -> dict:
        """OFPFC_DELETE_STRICT: the flow with exactly this match and priority in this table,
        and (the cookie masked whole) this cookie only, never a neighbour sharing the match."""
        flow = flow_from_spec(dpid, spec)
        return self._rendered(FLOW_DELETE_STRICT, {
            "dpid": flow.dpid, "table_id": flow.table_id, "priority": flow.priority,
            "cookie": flow.cookie, "cookie_mask": UINT64_MAX, "match": dict(flow.match)})

    def _render_add_meter(self, dpid, spec) -> dict:
        meter = meter_from_spec(dpid, spec)
        bands = []
        for band in meter.bands:
            out = {"type": band["type"], "rate": band["rate"],
                   "burst_size": band.get("burst_size", 0)}
            if band["type"] == "DSCP_REMARK":
                out["prec_level"] = band["prec_level"]
            bands.append(out)
        return self._rendered(METER_ADD, {"dpid": meter.dpid, "meter_id": meter.meter_id,
                                          "flags": list(meter.flags), "bands": bands})

    def _render_delete_meter(self, dpid, spec) -> dict:
        meter = meter_from_spec(dpid, spec, delete=True)
        return self._rendered(METER_DELETE, {"dpid": meter.dpid, "meter_id": meter.meter_id})

    # ── a write's answer ────────────────────────────────────────────────────────────────────

    def _write_answer(self, method, path, body, got) -> dict:
        if got["status"] == 200:
            return {"ok": True, "status": 200, "sent": True, "note": SENT_NOTE}
        try:
            dpid = json.loads(body).get("dpid")
        except (ValueError, AttributeError):
            dpid = None
        return self._failure(got, path, dpid if isinstance(dpid, int) else None)
