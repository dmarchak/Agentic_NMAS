"""AI troubleshooting's read family (the fix-it plan's S6; docs/HEAL_TO_INTENT.md section 12,
"The AI call (S5)": "The model reads only through Mercury's read families
(`modules/ai/router_reads.py` for a device, each command whole on its allowlist;
`modules/ai/fixit_reads.py` for what Mercury and its host already hold), each read recorded in
the send log and on History, and composes no command").

`FAMILY` is one `read_loop.ReadFamily` holding two kinds of read, each held to its own
transport's read rule when it is declared and again on every rendered request:

- **The device's reads** are the router read set's operations (`router_reads.AI_READS`, over
  ``cli``: the whole command on the read-only allowlist, its shape matched token by token, each
  argument compared with what Mercury holds) and the lost stream's two shapes of
  `router_reads.SHAPES` that only this family asks for (`router_reads.TELEMETRY`:
  ``telemetry_brief``, ``telemetry_receiver``). They run through Mercury's reads engine as kind
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


def run(op: str, args: dict, requests: list, scope: dict):
    """The family's executor: a device's read through the router read set's own executor (the
    reads engine, `router_reads.run`), a local one through Mercury's own read of it, handed
    exactly the request the check allowed."""
    if op not in LOCAL_OPS:
        return RR.run(op, args, requests, scope)
    fx = (scope or {}).get("fixit") or {}
    if op == "collector_sessions":
        return _collector(fx, args["subscription"])
    return _series(fx, args["device"], args["subscription"])


#: AI troubleshooting's read family: the router read set (``cli``) and Mercury's own reads
#: (``local``), each under the device state class.
FAMILY = RL.ReadFamily(
    name=NAME, transport="local", egress_class="device_state",
    operations=tuple(dataclasses.replace(op, transport="cli")
                     for op in RR.AI_READS.operations + RR.TELEMETRY_OPS) + LOCAL,
    run=run, words="AI troubleshooting's reads: the device's, and Mercury's own")


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
