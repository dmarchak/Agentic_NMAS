"""AI troubleshooting's read family (the fix-it plan's S6; docs/HEAL_TO_INTENT.md section 12,
"The AI call (S5)": "The model reads only through Mercury's read families
(`modules/ai/router_reads.py` for a device, each command whole on its allowlist;
`modules/ai/fixit_reads.py` for what Mercury and its host already hold), each read recorded in
the send log and on History, and composes no command").

`FAMILY` is one `read_loop.ReadFamily` holding two kinds of read, each held to its own
transport's read rule when it is declared and again on every rendered request:

- **Since C3661 (the operator, 2026-11-14), `FAMILY` is v5's:** the device's reads by Mercury's
  command families (`router_reads.COMMAND_OPS`: the model names a read's verb and its words; a
  show is one of `SHOW_FAMILIES`' forms, and Mercury's allowlist decides the whole command
  too), signed in by "AI device reads sign in
  as" (Mercury's account by default), and Mercury's own reads of a device in scope (`OWN_READS`:
  intent, golden, neighbours, history, logs, metrics) beside the stream's two. What follows
  describes the fixed shapes, kept as `SHAPES_FAMILY` (the probe's) and `FAMILY_V4` (v4's).
- **The device's reads** are the router read set's operations (`router_reads.AI_READS`, over
  ``cli``: the whole command on the read-only allowlist, its shape matched token by token, each
  argument compared with what Mercury holds) and the lost stream's three shapes of
  `router_reads.SHAPES` that only this family asks for (`router_reads.TELEMETRY`:
  ``telemetry_brief``, ``telemetry_receiver``, and ``telemetry_connection``, the device's
  connections, IOS-XE's form, C3640). They run through Mercury's reads engine as kind
  ``ai_analysis``, signed in as the device's read-only account, each recorded on History ›
  Reads as an AI-requested read (`router_reads.run`).
- **Mercury's own reads** (``local``: one line naming the read, never a command):
  - ``collector_sessions`` {device, subscription}: the collector's side of the subscription's
    stream on Mercury's host (`diagnose_stream.read_collector`: its listener and the device's
    sessions on the receiver's port, each with bytes received and time since its last receive,
    from the kernel's tables; no root, nothing written). The collector's address and port are
    the receiver the device's committed intent declares for that subscription
    (`diagnose_stream.receiver_of`), and the sessions are those from the device's own
    addresses: the model names neither, so it cannot read another device's or another port's.
    IPv4 and IPv6 alike.
  - ``stream_series`` {device, subscription}: whether the stream has data now, by the
    lost-stream alert's own query through Mercury's Prometheus client
    (`diagnose_stream.series_of`).

Each argument is held to the incident (`scope_for`): the device is the incident's own, and the
subscription one the incident names and the device's intent declares. Every read goes out under
the device state class (off by default per network: then no read is asked for at all), is
masked by the egress mask and logged in the send log before anything of it is sent
(`read_loop`), and History draws each request beside the calls (`history_sources.ai_reads`).
Nothing here sends to a device but through the reads engine, holds a device but as the reads
engine does, writes, or starts an operation (tests/test_ai_fix_rule.py).
"""

import dataclasses
import logging

from modules.ai import read_loop as RL
from modules.ai import router_reads as RR

log = logging.getLogger(__name__)

#: The family's name, and the operations its ``local`` transport serves.
NAME = "fixit"
LOCAL_OPS = ("collector_sessions", "stream_series")


def _incident_device(value, scope) -> str:
    own = ((scope or {}).get("fixit") or {}).get("device") or ""
    if value != own:
        return (f"{value} is not the incident's device (it is {own or 'none'}): Mercury's own "
                "reads are of the incident's device alone")
    return ""


def _incident_stream(args, scope) -> str:
    fx = (scope or {}).get("fixit") or {}
    sub = args["subscription"]
    streams = fx.get("streams") or {}
    if sub not in streams:
        return (f"subscription {sub} is not one the incident names (it names "
                f"{RR._listed(sorted(streams))})")
    return ""


def _local(name: str, words: str) -> RL.Operation:
    return RL.Operation(
        name, args={"device": RL.Arg(RL.Text(RR.DEVICE, "a device name"),
                                     against=_incident_device),
                    "subscription": RL.Arg(RR.SUBSCRIPTION)},
        sends=(f"local {name} {{device}} {{subscription}}",), against=_incident_stream,
        words=words, transport="local")


LOCAL = (
    _local("collector_sessions", "the collector's side of the subscription's stream on "
                                 "Mercury's host: its listener and the device's sessions on "
                                 "the receiver's port, each with bytes received and time since "
                                 "its last receive"),
    _local("stream_series", "whether the subscription's stream has data in Prometheus now, by "
                            "the lost-stream alert's own query"),
)


def _collector(fx: dict, sub: str) -> dict:
    from modules.heal import diagnose_stream as DS

    stream = (fx.get("streams") or {}).get(sub) or {}
    if stream.get("why"):
        raise RuntimeError(f"subscription {sub}'s collector is not known: {stream['why']}")
    read = fx.get("collector") or DS.read_collector
    got = read(stream["address"], int(stream["port"]), list(fx.get("sources") or []))
    if got.get("state") != "read":
        raise RuntimeError(f"the collector at {stream['address']} port {stream['port']} was not "
                           f"read: {got.get('why') or 'no reason given'}")
    return {"collector": f"{got['address']} port {got['port']}",
            "listening": list(got.get("listening") or []),
            "sessions": [{k: s.get(k) for k in ("remote", "rport", "state", "bytes_received",
                                                "lastrcv_ms")} for s in got.get("sessions")
                         or []],
            "others_established": int(got.get("others") or 0),
            "activity": got.get("activity") or ""}


def _series(fx: dict, device: str, sub: str) -> dict:
    from modules.heal import diagnose_stream as DS

    got = (fx.get("series") or DS.series_of)(device, sub)
    return {k: got.get(k) for k in ("state", "count", "why")}


# ── Mercury's own reads of what it holds about a device in scope (C3661) ─────────────────────
#
# The operator, 2026-11-14: "plus topology, neighbours, the evidence pack, logs, history,
# metrics, intent and golden". Each is the evidence pack's own builder for that section, read
# now for a device in the investigation's scope (`evidence_pack`: one home for each), never a
# device session; the golden is the configuration class's, so it is refused wherever that class
# is off (every network until C1720).

#: The operation, what it reads, and its class (None: the family's, the device state class).
OWN = (
    ("intent", "the device's committed intent (its host vars, secrets as references) and the "
               "Intent check of its committed golden against it", None),
    ("golden", "the device's committed golden configuration (the configuration class's)",
     "configuration"),
    ("neighbours", "the device's expected and reported neighbours (the Neighbours tab's view: "
                   "committed intent against Prometheus's routing tables)", None),
    ("history", "the device's recent History: deploys, restores, goldens, intent, restarts and "
                "reloads", None),
    ("logs", "the device's log lines from Loki around the incident's onset, masked", None),
    ("metrics", "the device's health figures from Prometheus and Loki over the incident's "
                "window (CPU, scrapes, interface discards, the syslog heartbeat)", None),
)
OWN_OPS = tuple(name for name, _w, _c in OWN)
#: A Mercury read of the log or the metrics without an onset reads this far back.
OWN_WINDOW_SECONDS = 15 * 60


def _scope_device(value, scope) -> str:
    devices = (scope or {}).get("devices") or {}
    if value not in devices:
        return (f"{value} is not a device in this investigation's scope (it holds "
                f"{RR._listed(sorted(devices))})")
    return ""


def _own(name: str, words: str, cls) -> RL.Operation:
    return RL.Operation(
        name, args={"device": RL.Arg(RL.Text(RR.DEVICE, "a device name"),
                                     against=_scope_device)},
        sends=(f"local {name} {{device}}",), egress_class=cls, words=words,
        transport="local")


OWN_READS = tuple(_own(*o) for o in OWN)


def _own_read(op: str, host: str, scope: dict):
    """Mercury's own read *op* of *host*, through the evidence pack's builder for it."""
    import time

    from modules import evidence_pack as EP
    from modules.device import load_saved_devices
    from modules.nsot import listref

    network = (scope or {}).get("network") or ""
    ref = listref.resolve(network)
    if op in ("intent", "golden"):
        intents, goldens = RR._committed(network, [host])
        if op == "golden":
            return {"device": host, "golden": goldens.get(host) or "",
                    "why": "" if goldens.get(host) else f"{host} has no committed golden"}
        dev = next((d for d in load_saved_devices(ref.csv_path)
                    if d.get("hostname") == host), {"hostname": host})
        return {"device": host, "intent": intents.get(host) or {},
                "check": EP.intent_section(ref, dev)}
    now = time.time()
    onset = ((scope or {}).get("fixit") or {}).get("onset") or (now - OWN_WINDOW_SECONDS)
    if op == "neighbours":
        dev = next((d for d in load_saved_devices(ref.csv_path)
                    if d.get("hostname") == host), {"hostname": host})
        return EP.neighbours_section(ref, dev)
    if op == "history":
        return EP.history_section(ref, host)
    if op == "logs":
        return EP.logs_section(ref, host, onset, now)
    return EP.health_section(ref, host, {"ok": False}, onset, now, now)


def run(op: str, args: dict, requests: list, scope: dict):
    """The family's executor: a device's read through the router read set's own executor (the
    reads engine, `router_reads.run`), a local one through Mercury's own read of it, handed
    exactly the request the check allowed."""
    if op in OWN_OPS:
        return _own_read(op, args["device"], scope)
    if op not in LOCAL_OPS:
        return RR.run(op, args, requests, scope)
    fx = (scope or {}).get("fixit") or {}
    if op == "collector_sessions":
        return _collector(fx, args["subscription"])
    return _series(fx, args["device"], args["subscription"])


#: The fixed shapes' family (S6, as AI troubleshooting's v4 asked): the router read set
#: (``cli``), the lost stream's shapes and Mercury's two stream reads, each under the device
#: state class. Kept for the read-only account probe, which measures the account against these
#: shapes (`read_account_probe._cli_operations`; post-lab hardening, C3665), and for the
#: diagnosis's own forms.
SHAPES_FAMILY = RL.ReadFamily(
    name=NAME, transport="local", egress_class="device_state",
    operations=tuple(dataclasses.replace(op, transport="cli")
                     for op in RR.AI_READS.operations + RR.TELEMETRY_OPS) + LOCAL,
    run=run, words="AI troubleshooting's reads by fixed shapes: the device's, and Mercury's own")

#: v4's family exactly as its committed schema declares it (schemas/ai/fixit_troubleshoot.v4.json:
#: the two telemetry shapes it shipped with), kept so a call recorded under v4 stays readable.
FAMILY_V4 = RL.ReadFamily(
    name=NAME, transport="local", egress_class="device_state",
    operations=tuple(op for op in SHAPES_FAMILY.operations
                     if op.name != "telemetry_connection"),
    run=run, words=SHAPES_FAMILY.words)

#: AI troubleshooting's read family (v5; the operator, 2026-11-14, C3661): the device's reads by
#: Mercury's own allowlist (`router_reads.COMMAND_OPS`: any read Show commands holds whole, as
#: Show commands runs it), Mercury's own reads of what it holds about a device in scope
#: (`OWN_READS`), and the two stream reads (`LOCAL`).
FAMILY = RL.ReadFamily(
    name=NAME, transport="local", egress_class="device_state",
    operations=tuple(dataclasses.replace(op, transport="cli") for op in RR.COMMAND_OPS)
    + OWN_READS + LOCAL,
    run=run, words="AI troubleshooting's reads: the device's by Mercury's allowlist, and "
                   "Mercury's own")


def scope_for(network: str, incident, *, actor: str, collector=None, series=None) -> dict:
    """What `FAMILY`'s comparisons read for *incident* (a `fixit.incident.Incident`): the router
    read set's scope for the incident's device (`router_reads.scope_for`), the incident's
    subscriptions as the device scope's, and ``fixit``: the device, each subscription's
    receiver from committed intent (``streams``) and the device's addresses (``sources``).
    *collector* and *series* replace the two local reads (tests). Reads committed intent; one
    that cannot be read names no stream, so every local read is refused."""
    from modules.heal import diagnose_stream as DS

    try:
        scope = RR.scope_for(network, [incident.device], incident=incident.id,
                             turned_on_by=actor)
        intents, _goldens = RR._committed(network, [incident.device])
    except Exception as exc:                          # noqa: BLE001 (closed: no device named)
        log.error("fixit reads: the scope of %s could not be built: %s", incident.id, exc)
        scope, intents = {"network": network, "devices": {}, "addresses": [],
                          "prefixes": []}, {}
    hv = intents.get(incident.device) or {}
    declared = {str(s.get("subscription")): s.get("settings") or []
                for s in hv.get("telemetry") or [] if isinstance(s, dict)}
    streams = {}
    for sub in incident.subscriptions:
        streams[sub] = (DS.receiver_of(declared[sub]) if sub in declared else
                        {"why": f"{incident.device}'s intent declares no subscription {sub}"})
    scope["subscriptions"] = list(incident.subscriptions)
    scope["fixit"] = {"device": incident.device, "streams": streams,
                      "sources": DS._addresses(hv), "collector": collector, "series": series}
    scope["actor"] = (f"AI troubleshooting of incident {incident.id}, pressed by "
                      f"{actor or 'nobody named'}")
    return scope
