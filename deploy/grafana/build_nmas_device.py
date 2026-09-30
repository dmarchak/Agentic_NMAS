#!/usr/bin/env python3
"""Build deploy/grafana/nmas-device.json, the NMAS device dashboard (UID
`nmas-device`), designed for the device pages (approved by the operator,
2026-09-30, with gRPC telemetry as the primary source where a device streams).

    python3 deploy/grafana/build_nmas_device.py            # rewrite the JSON
    python3 deploy/grafana/build_nmas_device.py --check    # exit 1 if it differs

The operator imports the JSON in Grafana (Dashboards > New > Import), maps the
Prometheus and Loki data sources, and sets `nmas-device` as the device
dashboard in Settings. The NMAS never pushes a dashboard.

Rules the panels follow (tests/test_nmas_device_dashboard.py holds them):
- EVERY query selects `device="$device"`: no fleet-wide panel under a
  device's name. The telemetry series carry `device` once the operator's
  relabel rule copies `source` into it (PROMETHEUS_TARGETS.md); until then the
  telemetry half of a panel matches nothing and the SNMP half answers.
- Where a device streams, telemetry is the PRIMARY source and SNMP the
  fallback: `telemetry or (snmp unless on(device) telemetry)`, per device.
  Each series carries `via` ("gRPC telemetry" or "SNMP") and every panel says
  its source, so two collectors are never compared unawares.
- Only native panel types (stat, timeseries, table, and rows), units and
  meaningful thresholds on every value, plain titles, and a `noValue` sentence
  saying why a panel can be empty for a device.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "nmas-device.json")

D = 'device="$device"'
TI = "Cisco_IOS_XE_interfaces_oper:interfaces_interface_statistics_"
TC = "Cisco_IOS_XE_process_cpu_oper:cpu_usage_cpu_utilization_"
NOT_NULL = 'ifName!~"Nu[0-9].*|Vo[0-9].*"'
PROM = {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}
LOKI = {"type": "loki", "uid": "${DS_LOKI}"}


def via(expr: str, source: str) -> str:
    return f'label_replace({expr}, "via", "{source}", "", "")'


def pick(tele: str, snmp: str) -> str:
    """Telemetry where the device streams, SNMP where it does not."""
    return f'{via(tele, "gRPC telemetry")} or ({via(snmp, "SNMP")} unless on(device) {tele})'


def rename_if(expr: str) -> str:
    return f'label_replace({expr}, "name", "$1", "ifName", "(.*)")'


def per_if(tele_metrics, snmp_metrics) -> str:
    """Bits or packets per second per interface, the two sources' counters."""
    t = " + ".join(f"sum by (device, name) (rate({TI}{m}{{{D}}}[$__rate_interval]))" for m in tele_metrics)
    s = " + ".join(f"sum by (device, ifName) (rate({m}{{{D}, {NOT_NULL}}}[$__rate_interval]))"
                   for m in snmp_metrics)
    return t, rename_if(f"({s})")


def thresholds(*steps):
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for v, c in steps]}


GREEN_ZERO_RED = thresholds((None, "green"), (1, "red"))
GREEN_ZERO_AMBER = thresholds((None, "green"), (1, "orange"))


def mapping(values: dict) -> list:
    return [{"type": "value", "options": {str(k): {"text": t, "color": c, "index": i}
                                          for i, (k, (t, c)) in enumerate(values.items())}}]


_panels, _id = [], [0]


def _next_id():
    _id[0] += 1
    return _id[0]


def row(title, y):
    _panels.append({"id": _next_id(), "type": "row", "title": title, "collapsed": False,
                    "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []})


def panel(ptype, title, pos, targets, *, unit, description, no_value="", th=None, maps=None,
          overrides=None, organize=None, legend=True):
    x, y, w, h = pos
    defaults = {"unit": unit, "noValue": no_value}
    if th:
        defaults["thresholds"] = th
        defaults["color"] = {"mode": "thresholds"}
    if maps:
        defaults["mappings"] = maps
    p = {"id": _next_id(), "type": ptype, "title": title, "description": description,
         "datasource": targets[0].get("datasource", PROM),
         "gridPos": {"h": h, "w": w, "x": x, "y": y},
         "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
         "targets": [dict({"refId": chr(65 + i), "datasource": PROM, "editorMode": "code"}, **t)
                     for i, t in enumerate(targets)]}
    if ptype == "stat":
        p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "colorMode": "value", "graphMode": "none", "textMode": "auto"}
    if ptype == "timeseries":
        p["options"] = {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": legend},
                        "tooltip": {"mode": "multi"}}
    if ptype == "table":
        for t in p["targets"]:
            t.update(instant=True, range=False, format="table")
        if organize:
            p["transformations"] = [{"id": "organize", "options": organize}]
    _panels.append(p)


def build() -> dict:
    _panels.clear()
    _id[0] = 0
    cpu_t = f"max by (device) ({TC}one_minute{{{D}}})"
    # IOS's own CPU: telemetry on IOS-XE; on vIOS the old CISCO MIB's busy
    # figure, which IS IOS's (no forwarding engine polls there).
    cpu_s = f"max by (device) (cpuAvgBusy1{{{D}}})"
    platform_cpu = f"max by (device) (cpmCPUTotal1minRev{{{D}}})"
    wrong_states = (f"count(({{__name__=~\"ospfNbrState|ospfv3NbrState\", {D}}} < 4) "
                    f"or ({{__name__=~\"ospfNbrState|ospfv3NbrState\", {D}}} > 4 < 8) "
                    f"or (cbgpPeer2State{{{D}}} != 6 and on(device, cbgpPeer2RemoteAddr) "
                    f"cbgpPeer2AdminStatus{{{D}}} == 2)) or vector(0)")
    syslog_crit = ('sum(count_over_time({job="network_syslog"} |~ `\\d+: $device: ` '
                   '|~ `%[A-Z0-9_]+-[0-2]-` [24h])) or vector(0)')

    # ---- at a glance ------------------------------------------------------
    row("At a glance", 0)
    panel("stat", "Answering SNMP", (0, 1, 4, 4),
          [{"expr": f'max by (device) (up{{job=~"cisco_8000v|cisco_vios_l2", {D}}})', "legendFormat": "via SNMP"}],
          unit="none", maps=mapping({1: ("Yes", "green"), 0: ("No", "red")}),
          no_value="Not a target: its configuration has no SNMP. Needs attention says what to do.",
          description="Whether this device answered the last SNMP scrape (30 s).")
    # CPU AT A GLANCE IS IOS'S OWN (the operator's measurement on r3,
    # 2026-09-30): `show processes cpu` read 2/6/15% while `show processes cpu
    # platform` read 40/41/70%, with ucode_pkt_PQF0 alone at 90%+. That is the
    # virtual router's forwarding engine, which busy-polls whether or not
    # packets arrive, and it holds SNMP's platform figure at 52-55% on every
    # router, idle or not. IOS's control-plane CPU is the number that says a
    # router is under strain: telemetry's on IOS-XE (8-11%, matching), and on
    # vIOS SNMP's busy figure, which is already IOS's. One label on both, so
    # they compare. The platform figure is one level down, with its note.
    panel("stat", "IOS CPU, 1-minute average", (4, 1, 4, 4),
          [{"expr": pick(cpu_t, cpu_s), "legendFormat": "IOS CPU (via {{via}})"}],
          unit="percent", th=thresholds((None, "green"), (70, "orange"), (90, "red")),
          no_value="No IOS CPU reading. On IOS-XE it comes from telemetry, and this router is not "
                   "streaming; its platform CPU is one level down.",
          description="IOS's own control-plane CPU over the last minute: from gRPC telemetry on "
                      "IOS-XE, from SNMP on vIOS (the caption says which). The same measurement on "
                      "both. Amber from 70%, red from 90%.")
    mem_used = f'sum by (device) (cempMemPoolUsed{{{D}, cempMemPoolIndex="1"}})'
    mem_free = f'sum by (device) (cempMemPoolFree{{{D}, cempMemPoolIndex="1"}})'
    panel("stat", "Memory used", (8, 1, 4, 4),
          [{"expr": via(f"100 * {mem_used} / ({mem_used} + {mem_free})", "SNMP"), "legendFormat": "via {{via}}"}],
          unit="percent", th=thresholds((None, "green"), (80, "orange"), (90, "red")),
          no_value="Memory isn't available over SNMP on vIOS.",
          description="The processor memory pool in use. Amber from 80%, red from 90%.")
    panel("stat", "Interfaces down that should be up", (12, 1, 4, 4),
          [{"expr": via(f"sum by (device) ((ifOperStatus{{{D}}} != bool 1) * on(device, ifIndex) "
                        f"(ifAdminStatus{{{D}}} == bool 1))", "SNMP"), "legendFormat": "via {{via}}"}],
          unit="none", th=GREEN_ZERO_RED, no_value="No interface reading over SNMP.",
          description="Interfaces configured up that are not up. An interface shut down on purpose "
                      "is not counted. Red from 1.")
    panel("stat", "Routing neighbours in a wrong state", (16, 1, 4, 4),
          [{"expr": wrong_states, "legendFormat": "via SNMP"}],
          unit="none", th=GREEN_ZERO_RED,
          description="OSPF and OSPFv3 neighbours down, attempting, initialising or stuck forming "
                      "(exstart, exchange, loading), and BGP peers configured up and not established. "
                      "Two-way is NOT counted: it is the expected state between routers that are "
                      "neither the designated router nor its backup. Red from 1.")
    panel("stat", "Critical syslog lines, last 24 h", (20, 1, 4, 4),
          [{"expr": syslog_crit, "legendFormat": "via syslog", "datasource": LOKI, "queryType": "range"}],
          unit="none", th=GREEN_ZERO_RED,
          description="Syslog lines of severity 0 to 2 (emergency, alert, critical) from this device "
                      "in the last 24 hours. Red from 1; the lines are on the Logs tab.")

    panel("stat", "Up for", (0, 5, 5, 4),
          [{"expr": f"sysUpTime{{{D}}} / 100 and on(device) (deriv(sysUpTime{{{D}}}[1h]) / 100 > 0.9)",
            "legendFormat": "via SNMP (sysUpTime)"}],
          unit="dtdurations",
          no_value="Not shown: this device's own clock runs slow, so its uptime count under-reads. "
                   "Reboots are counted beside it, and the clock's rate is its own panel.",
          description="Time since the device's SNMP agent started, shown only where the device's "
                      "clock keeps real time (rate at least 90%).")
    panel("stat", "Reboots detected", (5, 5, 5, 4),
          [{"expr": f"resets(sysUpTime{{{D}}}[$__range])", "legendFormat": "via SNMP (sysUpTime)"}],
          unit="none", th=GREEN_ZERO_AMBER, no_value="Not a target: no SNMP.",
          description="Times the uptime counter reset in the chosen range: a reboot, counted "
                      "reliably however slowly the device's clock runs. Amber from 1.")
    panel("stat", "Device clock rate", (10, 5, 5, 4),
          [{"expr": f"deriv(sysUpTime{{{D}}}[1h]) / 100", "legendFormat": "via SNMP (sysUpTime against real time)"}],
          unit="percentunit", th=thresholds((None, "red"), (0.7, "orange"), (0.9, "green")),
          no_value="Not a target: no SNMP, or less than an hour of history.",
          description="How fast the device's own clock runs against real time, over the last hour "
                      "(100% keeps time). The emulated vIOS switches run slow (C9); NTP corrects the "
                      "time of day, not this rate. Red below 70%, amber below 90%.")
    panel("stat", "Telemetry stream", (15, 5, 5, 4),
          [{"expr": f"time() - max by (device) (timestamp({TI}in_octets{{{D}}}))",
            "legendFormat": "via gRPC telemetry (the interface subscription)"}],
          unit="s", th=thresholds((None, "green"), (90, "orange"), (300, "red")),
          no_value="No stream: nothing received in 5 min. IOS-XE devices stream once the monitoring "
                   "profile subscribes them; vIOS has no telemetry.",
          description="Seconds since the newest sample of this device's interface telemetry. Amber after 90 s "
                      "(three missed scrapes), red after 5 min; after that the series are stale and "
                      "the panel says no stream, never fresh.")
    panel("stat", "LLDP neighbours", (20, 5, 4, 4),
          [{"expr": via(f"count by (device) (lldpRemEntry{{{D}}})", "SNMP"), "legendFormat": "via {{via}}"}],
          unit="none", no_value="None reported over LLDP.",
          description="Physical neighbours this device reports over LLDP. No colour: the right "
                      "number depends on how it is cabled.")

    # ---- traffic ----------------------------------------------------------
    row("Traffic (bits per second, each interface)", 9)
    t_in, s_in = per_if(["in_octets"], ["ifHCInOctets"])
    t_out, s_out = per_if(["out_octets_64"], ["ifHCOutOctets"])
    for title, x, t, s in (("Traffic in", 0, t_in, s_in), ("Traffic out", 12, t_out, s_out)):
        panel("timeseries", title, (x, 10, 12, 8),
              [{"expr": pick(f"({t}) * 8", f"({s}) * 8"), "legendFormat": "{{name}} (via {{via}})"}],
              unit="bps", no_value="No interface counters from telemetry or SNMP.",
              description=f"{title} per interface, from gRPC telemetry where the device streams, "
                          "else SNMP. Null and VoIP-Null interfaces are left out.")

    row("Errors and discards (packets per second, each interface)", 18)
    t_e, s_e = per_if(["in_errors", "out_errors"], ["ifInErrors", "ifOutErrors"])
    t_d, s_d = per_if(["in_discards", "out_discards"], ["ifInDiscards", "ifOutDiscards"])
    for title, x, t, s in (("Interface errors", 0, t_e, s_e), ("Interface discards", 12, t_d, s_d)):
        panel("timeseries", title, (x, 19, 12, 7),
              [{"expr": pick(t, s), "legendFormat": "{{name}} (via {{via}})"}],
              unit="pps", no_value="No interface counters from telemetry or SNMP.",
              description=f"{title}, in and out together, per interface.")

    # ---- routing ----------------------------------------------------------
    row("Routing neighbours", 26)
    ospf_map = {1: ("down", "red"), 2: ("attempt", "orange"), 3: ("init", "orange"),
                4: ("two-way", "text"), 5: ("exstart", "orange"), 6: ("exchange", "orange"),
                7: ("loading", "orange"), 8: ("full", "green")}
    bgp_map = {1: ("idle", "red"), 2: ("connect", "orange"), 3: ("active", "orange"),
               4: ("opensent", "orange"), 5: ("openconfirm", "orange"), 6: ("established", "green")}

    def state_override(values):
        return [{"matcher": {"id": "byName", "options": "State"},
                 "properties": [{"id": "mappings", "value": mapping(values)}]}]

    panel("table", "OSPF neighbours", (0, 27, 12, 8),
          [{"expr": f"max by (ospfNbrRtrId, ospfNbrIpAddr) (ospfNbrState{{{D}}})", "legendFormat": "via SNMP"}],
          unit="none", overrides=state_override(ospf_map),
          organize={"excludeByName": {"Time": True},
                    "renameByName": {"Value": "State", "ospfNbrRtrId": "Router ID",
                                     "ospfNbrIpAddr": "Address"}},
          no_value="No OSPF neighbour: no OSPF on this device, or its OSPF table is not scraped yet.",
          description="Each OSPFv2 neighbour and its state, via SNMP (OSPF-MIB). Two-way is expected "
                      "between routers that are neither DR nor BDR.")
    panel("table", "OSPFv3 neighbours", (12, 27, 6, 8),
          [{"expr": f"max by (ospfv3NbrRtrId, ospfv3NbrIfIndex) (ospfv3NbrState{{{D}}})", "legendFormat": "via SNMP"}],
          unit="none", overrides=state_override(ospf_map),
          organize={"excludeByName": {"Time": True},
                    "renameByName": {"Value": "State", "ospfv3NbrRtrId": "Router ID",
                                     "ospfv3NbrIfIndex": "Interface index"}},
          no_value="No OSPFv3 neighbour. vIOS does not report OSPFv3 over SNMP.",
          description="Each OSPFv3 neighbour and its state, via SNMP (OSPFV3-MIB, IOS-XE only).")
    panel("table", "BGP peers", (18, 27, 6, 8),
          [{"expr": f"max by (cbgpPeer2RemoteAddr) (cbgpPeer2State{{{D}}})", "legendFormat": "via SNMP"}],
          unit="none", overrides=state_override(bgp_map),
          organize={"excludeByName": {"Time": True},
                    "renameByName": {"Value": "State", "cbgpPeer2RemoteAddr": "Peer"}},
          no_value="No BGP peer on this device.",
          description="Each BGP peer, IPv4 and IPv6, and its session state, via SNMP (CISCO-BGP4-MIB).")

    # ---- reachability and load --------------------------------------------
    row("Reachability and load", 35)
    panel("timeseries", "IP SLA round-trip time", (0, 36, 8, 7),
          [{"expr": f"rttMonLatestRttOperCompletionTime{{{D}}}",
            "legendFormat": "operation {{rttMonCtrlAdminIndex}} (via SNMP)"}],
          unit="ms", no_value="No IP SLA operation on this device.",
          description="The latest round-trip time of each IP SLA operation this device runs.")
    panel("stat", "IP SLA operations failing", (8, 36, 4, 7),
          [{"expr": f"sum by (device) (rttMonLatestRttOperSense{{{D}}} != bool 1)", "legendFormat": "via SNMP"}],
          unit="none", th=GREEN_ZERO_RED, no_value="No IP SLA operation on this device.",
          description="Operations whose latest result is not ok. Red from 1.")
    panel("timeseries", "IOS CPU over time", (12, 36, 12, 7),
          [{"expr": pick(cpu_t, cpu_s), "legendFormat": "IOS CPU (via {{via}})"}],
          unit="percent", no_value="No IOS CPU reading from telemetry or SNMP.",
          description="IOS's own control-plane CPU over the chosen range, from the same source as "
                      "the value at a glance.")

    # ---- interfaces ---------------------------------------------------------
    row("Interfaces", 43)
    if_map = {1: ("up", "green"), 2: ("down", "red"), 3: ("testing", "orange"), 5: ("dormant", "text"),
              6: ("not present", "text"), 7: ("lower layer down", "orange")}
    panel("table", "Interface status", (0, 44, 24, 8),
          [{"expr": f"max by (ifName, ifAlias) (ifOperStatus{{{D}, {NOT_NULL}}})", "legendFormat": "via SNMP"}],
          unit="none", overrides=state_override(if_map),
          organize={"excludeByName": {"Time": True},
                    "renameByName": {"Value": "State", "ifName": "Interface", "ifAlias": "Description"}},
          no_value="No interface reading over SNMP.",
          description="Each interface's operational state, via SNMP. Null and VoIP-Null are left out.")

    # ---- one level down -----------------------------------------------------
    row("Detail", 52)
    panel("timeseries", "Syslog lines by severity", (0, 53, 12, 7),
          [{"expr": ('sum by (sev) (count_over_time({job="network_syslog"} |~ `\\d+: $device: ` '
                     '| regexp `%[A-Z0-9_]+-(?P<sev>[0-7])-` [$__interval]))'),
            "legendFormat": "severity {{sev}} (via syslog)", "datasource": LOKI, "queryType": "range"}],
          unit="none", no_value="No syslog line from this device in the range.",
          description="Syslog lines per interval by severity (0 emergency to 7 debug). The lines "
                      "themselves are on the Logs tab.")
    panel("timeseries", "Interface flaps", (12, 53, 12, 7),
          [{"expr": f"max by (device, name) ({TI}num_flaps{{{D}}})", "legendFormat": "{{name}} (via gRPC telemetry)"}],
          unit="none", no_value="IOS-XE telemetry only: this device does not stream.",
          description="Each interface's flap count since its counters were cleared.")
    panel("timeseries", "Device clock rate over time", (0, 60, 12, 6),
          [{"expr": f"deriv(sysUpTime{{{D}}}[1h]) / 100", "legendFormat": "clock rate (via SNMP)"}],
          unit="percentunit", no_value="Not a target: no SNMP, or less than an hour of history.",
          description="The device's clock rate against real time, over time (100% keeps time).")
    panel("timeseries", "SNMP collection time", (12, 60, 12, 6),
          [{"expr": f"max by (device, job) (snmp_scrape_duration_seconds{{{D}}})",
            "legendFormat": "{{job}} (via SNMP)"}],
          unit="s", no_value="Not a target: no SNMP.",
          description="How long one SNMP read of this device takes, per job; its limit is 30 s.")
    panel("timeseries", "Platform CPU (the whole route processor)", (0, 66, 12, 6),
          [{"expr": via(platform_cpu, "SNMP"), "legendFormat": "platform CPU (via SNMP, CISCO-PROCESS-MIB)"}],
          unit="percent",
          no_value="vIOS reports no platform figure apart from IOS's; IOS CPU is at a glance.",
          description="The route processor's whole CPU, forwarding engine included. On a virtual "
                      "router the forwarding engine busy-polls continuously whether or not packets "
                      "arrive (measured on r3: ucode_pkt_PQF0 alone at 90% and more), so a high flat "
                      "line is normal here; IOS CPU at a glance is the figure that shows strain.")

    return {
        "__inputs": [
            {"name": "DS_PROMETHEUS", "label": "Prometheus", "type": "datasource",
             "pluginId": "prometheus", "pluginName": "Prometheus"},
            {"name": "DS_LOKI", "label": "Loki", "type": "datasource",
             "pluginId": "loki", "pluginName": "Loki"}],
        "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "10.0.0"},
            {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0"},
            {"type": "datasource", "id": "loki", "name": "Loki", "version": "1.0.0"},
            {"type": "panel", "id": "stat", "name": "Stat", "version": ""},
            {"type": "panel", "id": "timeseries", "name": "Time series", "version": ""},
            {"type": "panel", "id": "table", "name": "Table", "version": ""}],
        "uid": "nmas-device", "title": "NMAS device", "tags": ["nmas", "device"],
        "description": "One network device, for the NMAS device page: every panel selects the "
                       "`device` variable. Built by deploy/grafana/build_nmas_device.py.",
        "editable": True, "schemaVersion": 39, "version": 1, "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"}, "timezone": "",
        "templating": {"list": [{
            "name": "device", "label": "Device", "type": "query", "datasource": PROM,
            "query": {"query": 'label_values(up{job=~"cisco_8000v|cisco_vios_l2"}, device)',
                      "refId": "device"},
            "definition": 'label_values(up{job=~"cisco_8000v|cisco_vios_l2"}, device)',
            "refresh": 2, "sort": 1, "multi": False, "includeAll": False,
            "current": {}, "options": []}]},
        "annotations": {"list": []},
        "panels": list(_panels),
    }


def render() -> str:
    return json.dumps(build(), indent=2) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = render()
    if "--check" in argv:
        current = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if current != text:
            print(f"{OUT} differs from what the builder produces: run it without --check", file=sys.stderr)
            return 1
        print("nmas-device.json matches the builder")
        return 0
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {OUT} ({len(build()['panels'])} panels and rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
