"""modules/readers/sdn_controllers.py — the SDN reader (PHASE8_PLAN 17.1 S11): one network's
controller connections, read for SDN › Controllers and SDN › Flows (boards SdnControllers and
SdnFlows, signed off 2026-10-27).

Everything those screens draw about a controller comes from here, never a controller call per
page view (CLAUDE.md, "Enterprise scale"). Per network, every `sdn_controllers` connection
(`modules/sdn/connections.py`, each network's own, C1841), each read through its driver:
- **the closed loop's read** (`closed_loop.collect_threat_data`, one home for what a switch's
  table and ports are): the switch list, each switch's whole flow table, its port counters
  twice `SAMPLE_INTERVAL` apart, and the flow granularity found (``coverage``);
- **per connection,** the driver's `test()` (the controller's version where it reports one);
- **per switch,** what it says it is (`switch_desc`: its own name, ``dp_desc``), and where the
  driver declares `read_meters`, its meters and its meter features, each read on its own;
- **whose each flow is** (`flow_intent.classify` over the network's flow intent): Mercury's,
  Mercury's and not as recorded, the controller's own, or unauthorised; each of Mercury's flows
  not installed, missing or expired, and each of Mercury's recorded meters the switch does not
  hold (``meter_records``, `flow_intent.meter_records`; C2018);
- **per connection, its topology** where the driver declares `read_topology` (PHASE8_PLAN 17.1
  S14): the switches with their ports, the links the controller discovered and the hosts it
  learned (`topology`, one read), the one source of the Topology view's controller layer and
  the endpoint layer's controller-learned hosts (`modules/sdn/topology.py` reads it from this
  store); a topology that cannot be read keeps its last good read with that read's time.

**A connection that fails keeps what it last read** (reader_job rule 3, per connection): it is
``not_answering`` with the error, since when and how many reads in a row, and its switches as
last read, with that read's time. A network whose connection list cannot be read fails the whole
read, and the reader keeps its last good value. A network with no connection is ``none``;
another network's never reads Default's (C1841), and one with none set is not read at all
(`settings_scope.URL_KEYS`: its list is its "URL").

**Calls per read**, a connection with N switches: the closed loop's 1 + 3N, `test()`'s 1, the
topology's 1 (3 requests on Ryu: switches, links, hosts), and per switch its description, and
its meters and meter features for a driver that reads meters (3N driver calls; 4N requests on
Ryu, whose meters are two, configuration and statistics), else N: every switch's reads at once
(`fanout.read_each`).
"""

import logging
import time

from modules import reader_job

log = logging.getLogger(__name__)

READER_NAME = "sdn-controllers"
#: The lab's controller application idles its flows out after 30 s (PHASE8_PLAN 17.6:
#: `l4_switch_13.py`, one flow per probed port "for at least one read interval"), so a read
#: every 30 s sees each flow at least once.
INTERVAL_SECONDS = 30
#: The two port samples' spacing: the closed loop's least (`closed_loop.MIN_INTERVAL`), since
#: these screens draw no rate; the loop's own detection reads at its own interval (S10).
SAMPLE_INTERVAL = 1.0
STATES = ("connected", "partial", "not_answering", "not_built")


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _previous(network: str) -> dict:
    """*network*'s last good value, or {} (none yet, or the store unreadable: a reader's cache
    is re-derivable, rule 10)."""
    got = reader_job.read_cached_for(READER_NAME, network)
    return (((got.get("doc") or {}).get("last_good") or {}).get("value")) or {}


def _meter_owner(meter_id, flows) -> dict:
    """Whose a meter is, by the flows that use it (`METER` among their actions): Mercury's when
    one of Mercury's flows does, the controller's own when one of its own does, else no flow
    read uses it."""
    users = [f for f in flows if any(a.get("type") == "METER" and a.get("meter_id") == meter_id
                                     for a in f.get("actions") or [])]
    owners = {f.get("owner") for f in users}
    for owner in ("mercury", "mercury_differs", "unauthorised", "controller_own"):
        if owner in owners:
            return {"owner": owner, "flows": len(users)}
    return {"owner": "unused", "flows": 0}


def _switch_extras(drv, dpid: int, reads_meters: bool) -> dict:
    """What a switch says it is, and its meters and meter features where the driver reads
    them: each read on its own, its failure said, never dropping the others."""
    out = {"name": "", "desc_error": "", "meters": None, "meters_error": "",
           "meter_features": None, "features_error": ""}
    desc = drv.switch_desc(dpid)
    if desc.get("ok"):
        out["name"] = str(((desc.get("desc") or {}).get("dp_desc")) or "").strip()
    else:
        out["desc_error"] = desc.get("error") or "no answer"
    if reads_meters:
        got = drv.meters(dpid)
        if got.get("ok"):
            out["meters"] = got.get("meters") or []
        else:
            out["meters_error"] = got.get("error") or "no answer"
        feat = drv.meter_features(dpid)
        if feat.get("ok"):
            out["meter_features"] = feat.get("features")
        else:
            out["features_error"] = feat.get("error") or "no answer"
    return out


def _carried(conn: dict, before: dict, error: str, now_iso: str) -> dict:
    """A connection that failed this read: its error, since when and how many reads in a row,
    and what it last read whole (its switches, version, that read's time, its topology)."""
    was_failing = before.get("state") == "not_answering"
    return dict(conn, state="not_answering", error=error,
                failing_since=(before.get("failing_since") if was_failing else None) or now_iso,
                failures=(before.get("failures") or 0) + 1 if was_failing else 1,
                version=before.get("version"), version_note=before.get("version_note", ""),
                switches=before.get("switches") or [],
                last_good_at=before.get("last_good_at"),
                topology=_topology_kept((before.get("topology") or {}), error))


#: A connection's topology as stored (PHASE8_PLAN 17.1 S14): ``state`` read, could not read
#: (with ``error``, and the last good read's ``switches``, ``links`` and ``hosts`` kept with
#: ``read_at``, that read's time), or not_declared (the driver has no `read_topology`).
TOPOLOGY_STATES = ("read", "could not read", "not_declared")


def _topology_kept(before: dict, error: str) -> dict:
    """The last good topology, kept whole with its own time, marked as not read now."""
    return {"state": "could not read" if before.get("state") != "not_declared"
            else "not_declared", "error": error,
            "read_at": before.get("read_at") or "",
            "switches": before.get("switches") or [], "links": before.get("links") or [],
            "hosts": before.get("hosts") or [], "hosts_note": before.get("hosts_note", ""),
            "links_note": before.get("links_note", "")}


def _topology(drv, decl: dict, before: dict, now_iso: str) -> dict:
    """The controller's topology this read: its switches with their ports, its links and the
    hosts it learned (`ControllerDriver.topology`), or, when it cannot be read, the last good
    one kept with its time and why; a driver that does not declare `read_topology` says so."""
    if "read_topology" not in decl.get("capabilities", []):
        why = (decl.get("absent") or {}).get("read_topology", "")
        return {"state": "not_declared", "read_at": "", "switches": [], "links": [],
                "hosts": [], "hosts_note": "",
                "error": "the driver does not declare read_topology" + (f": {why}" if why
                                                                         else "")}
    got = drv.topology()
    if not got.get("ok"):
        return _topology_kept(before, got.get("error") or "no answer")
    return {"state": "read", "error": "", "read_at": now_iso,
            "switches": got.get("switches") or [], "links": got.get("links") or [],
            "hosts": got.get("hosts") or [], "hosts_note": got.get("hosts_note", ""),
            "links_note": got.get("links_note", "")}


def read(list_name: str = "", clock=time.time, previous=None, driver=None,
         sleep=time.sleep) -> dict:
    """One network's controllers (see the module). *driver* is ``driver(network, name) ->
    connections.driver_for``'s answer (a test's fakes); *previous* the last good value (read
    from the store when None); *clock* the wall clock the value is stamped with."""
    from modules import fanout
    from modules import list_settings as L
    from modules.sdn import closed_loop, connections, flow_intent
    from modules.sdn.drivers import DRIVERS

    network = list_name or L.DEFAULT_LIST
    now_iso = _iso(clock())
    out = {"network": network, "read_at": now_iso, "state": "none", "error": "",
           "controllers": [], "intent": {"state": "ok", "error": ""}}
    listed = connections.connections(network)
    if listed["state"] == "unreadable":
        raise RuntimeError(f"{network}'s controller connections could not be read: "
                           f"{listed['error']}")
    if listed["state"] != "ok":
        out["state"] = listed["state"]
        return out
    if previous is None:
        previous = _previous(network)
    before = {c.get("name"): c for c in (previous or {}).get("controllers") or []}
    make = driver or connections.driver_for
    opened = {}

    def open_once(net, name):
        if name not in opened:
            opened[name] = make(net, name)
        return opened[name]

    data = closed_loop.collect_threat_data(network, SAMPLE_INTERVAL, sleep=sleep,
                                           now=clock, driver=open_once)
    collected = {c["connection"]: c for c in data.get("controllers") or []}
    intent = flow_intent.intent(network)
    out["intent"] = {"state": intent["state"], "error": intent.get("error", "")}
    meter_rows = (flow_intent.meters(network).get("meters") or []) \
        if intent["state"] == "ok" else []
    for conn in listed["connections"]:
        cls = DRIVERS.get(conn["kind"])
        decl = cls.declaration() if cls else {"capabilities": [], "absent": {}}
        entry = {"name": conn["name"], "kind": conn["kind"], "label": conn["label"],
                 "status": conn["status"], "url": conn["url"],
                 "verify_tls": conn["verify_tls"], "timeout": conn["timeout"],
                 "southbound": conn["southbound"], "own_cookies": conn["own_cookies"],
                 "capabilities": decl["capabilities"], "absent": decl["absent"],
                 "read_at": now_iso}
        prior = before.get(conn["name"]) or {}
        got = collected.get(conn["name"]) or {"state": "unreadable", "error": "not read",
                                         "switches": []}
        if conn["status"] != "built":
            out["controllers"].append(dict(entry, state="not_built", error=(
                f"the {conn['label']} driver is not built (status: {conn['status']}), so "
                "nothing is read"), switches=[]))
            continue
        drv = (opened.get(conn["name"]) or {}).get("driver")
        if drv is None or (got["state"] == "unreadable" and not got.get("switches")):
            out["controllers"].append(_carried(entry, prior, got.get("error") or
                                               (opened.get(conn["name"]) or {}).get("error")
                                               or "no answer", now_iso))
            continue
        test = drv.test()
        entry.update(version=test.get("version"), version_note=test.get("version_note", ""))
        entry["topology"] = _topology(drv, decl, prior.get("topology") or {}, now_iso)
        reads_meters = "read_meters" in decl["capabilities"]
        switches = got.get("switches") or []
        extras = fanout.read_each(lambda s: _switch_extras(drv, s["dpid"], reads_meters),
                                  switches, name="sdn-switch")
        flows = [f for s in switches for f in s.get("flows") or []]
        judged = [s["dpid"] for s in switches if s.get("active_flows") is not None]
        classed = flow_intent.classify(flows, conn, intent, read_switches=judged,
                                       now=clock())
        by_dpid = {}
        for f in classed.get("flows") or []:
            by_dpid.setdefault(f.get("dpid"), []).append(f)
        records = {}
        for r in classed.get("records") or []:
            records.setdefault(r.get("dpid"), []).append(r)
        rows = []
        for s, x in zip(switches, extras):
            if isinstance(x, fanout.Failed):
                x = {"name": "", "desc_error": f"the read raised {x}", "meters": None,
                     "meters_error": f"the read raised {x}", "meter_features": None,
                     "features_error": ""}
            sflows = by_dpid.get(s["dpid"], []) if classed.get("state") == "ok" else \
                s.get("flows") or []
            meters = [dict(m, **_meter_owner(m.get("meter_id"), sflows))
                      for m in x["meters"] or []]
            rows.append({"dpid": s["dpid"], "dpid_hex": s["dpid_hex"], "name": x["name"],
                         "state": s["state"], "error": s["error"],
                         "flows": sflows, "records": records.get(s["dpid"], []),
                         "meter_records": flow_intent.meter_records(
                             conn["name"], s["dpid"],
                             [m.get("meter_id") for m in x["meters"]]
                             if x["meters"] is not None else None, meter_rows, now=clock()),
                         "active_flows": s.get("active_flows"),
                         "coverage": s.get("coverage"), "meters": meters,
                         "meters_read": x["meters"] is not None,
                         "meters_error": x["meters_error"],
                         "meter_features": x["meter_features"],
                         "features_error": x["features_error"],
                         "desc_error": x["desc_error"]})
        entry.update(state="connected" if got["state"] == "ok" else "partial",
                     error=got.get("error", ""), switches=rows, last_good_at=now_iso,
                     classified=classed.get("state"),
                     classify_error=classed.get("error", ""))
        out["controllers"].append(entry)
    states = {c["state"] for c in out["controllers"]}
    out["state"] = "ok"
    if states & {"not_answering", "partial"}:
        out["error"] = "; ".join(f"{c['name']}: {c['error']}" for c in out["controllers"]
                                 if c["state"] in ("not_answering", "partial"))
    return out


READER = reader_job.register(reader_job.Reader(
    name=READER_NAME,
    what=("each network's SDN controller connections: whether each answers, its switches, "
          "their flow tables with whose each flow is, their meters, for SDN › Controllers and "
          "Flows (PHASE8_PLAN 17.1 S11)"),
    endpoints=("each connection's driver: test, the switch list, its topology (switches, "
               "links, hosts) where it declares read_topology, and per switch its flows, "
               "port counters (twice), description, meters and meter features",
               "the network's flow intent (flow_intent.jsonl or the records database)"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the lab's controller application idles its flows out after 30 s "
                    "(PHASE8_PLAN 17.6), so a read every 30 s sees each at least once"),
    read=read,
    invalidates=("sdn",),
    remedy=("Read the connection's error on SDN › Controllers: it names the call the "
            "controller did not answer; its connection is edited on the network's Settings "
            "page, its Integrations tab, the SDN controllers card"),
    window="each controller's switches and flow tables as they are at the read",
    per_group=("sdn_controllers",),
    read_for=lambda list_name: read(list_name=list_name),
))
