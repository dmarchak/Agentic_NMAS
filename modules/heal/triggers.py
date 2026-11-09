"""Heal triggers: after-store steps on the readers, and the drift record (board H, part H2;
docs/HEAL_TO_INTENT.md section 3, and N2). Each trigger asks one question, "check this device
now", and none of them heals: it is sighted into the network's incidents
(`incidents.sight`), and the detect pass reads the device (`modules/heal/detect.py`).

**Where each is seen** (section 3's table), each on the reader that already reads the whole
fleet once per interval, so a trigger adds no per-device work per request:
- **a configuration change not from Mercury**: the `logs-tail` reader's lines (every 5 s,
  masked on the way in), a ``CONFIG_I``, ``CONFIG_P`` or DMI ``CONFIG_I`` line
  (`attribution.is_change`), judged by `attribution.attribute` (Mercury's hold, receipt or
  rotation at the line's receive time, never the account it names). Mercury's own lines are
  not triggers; the person the line names is kept to name them (N12);
- **any firing alert on a managed device** (N2, which also covers "Interface down"): the
  `grafana-alerts` reader's firing instances (the condition holds; a rule whose no data is
  its fault included, C2174), each once per alert episode (`evidence_pack.alert_key`). Its
  device is the instance's (by label, by line, or by its polled address, IPv4 or IPv6); an
  alert naming an interface (``ifDescr`` or ``ifName``) also checks the far end committed
  intent names for that interface's subnet, IPv4 or IPv6;
- **an adjacency down**: the `adjacencies` reader's adjacencies down for its two reads
  (`adjacencies.PERSIST_READS`), once per episode (its ``since``), both ends checked;
- **a logged adjacency drop**: the `adjacency-log` reader's drops, each once, both ends
  checked (the peer named by its router id or address in committed intent, IPv4 or IPv6); a
  drop a planned restart or a deploy explains is not one (`attention._explained`, the row's
  own rule);
- **a duplicate router-id logged** (C2446): the same reader's duplicate router-id reports,
  once per episode on each device that logged it and on the neighbour committed intent names
  by the address it saw; R8's verify reads it again (`act.duplicate_logged`). No planned
  window explains one;
- **the drift record**: each device a drift run found departed (`DriftChecker.record`), its
  run's read kept as the incident's first read.
The `topology-graph` reader's step records when each network's observed link set last changed
(`link_set`), for the topology hold (`hold.topology`, N3).

**Only where healing is on.** A network whose mode is off (`policy.current`, after the kill
switch and the confirmation) sights nothing; what each reader showed is still consumed (each
store's cursor moves), so turning healing on later does not replay old lines.

**Never stops a reader.** Each step runs after the reader stored its value; a step that fails
is logged, and the reader goes on (`reader_job._run_once`'s rule). A step reads its reader's
stored value only when what the page draws moved.
"""

import calendar
import hashlib
import ipaddress
import json
import logging
import os
import time

log = logging.getLogger(__name__)

#: The readers whose stores carry triggers (and the link set), each its step.
READERS = ("logs-tail", "grafana-alerts", "adjacencies", "adjacency-log", "topology-graph")
#: The labels by which an alert names an interface.
INTERFACE_LABELS = ("ifDescr", "ifName")
CURSOR_DIR = "heal"
CURSOR_FILE = "triggers.json"

_installed = {"on": False}


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _epoch(iso) -> float:
    try:
        return float(calendar.timegm(time.strptime(str(iso)[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return 0.0


def _key(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


# ── Installation ────────────────────────────────────────────────────────────────────────────

def install() -> None:
    """Run the steps after every reader store (`reader_job.after_any_store`). Installed where
    the readers start (`reader_job.start`), so a process that runs no readers sights
    nothing."""
    from modules import reader_job

    if not _installed["on"]:
        reader_job.after_any_store(_after_store)
        _installed["on"] = True


def uninstall() -> None:
    from modules import reader_job

    reader_job.after_any_store(_after_store, remove=True)
    _installed["on"] = False


def _after_store(reader, moved: bool = True) -> None:
    """A reader stored: its trigger step, when it is one of `READERS` and what it holds moved.
    Never raises (a reader is never stopped by a heal step)."""
    from modules import reader_job

    base = (getattr(reader, "name", "") or "").split("@", 1)[0]
    if base not in STEPS or not moved:
        return
    try:
        got = reader_job.read_cached(reader.name)
        good = (got.get("doc") or {}).get("last_good") or {}
        value = good.get("value")
        if not isinstance(value, dict):
            return
        STEPS[base](reader.name, value)
    except Exception as exc:
        log.error("heal: the %s trigger step failed: %s: %s", reader.name,
                  type(exc).__name__, exc)


# ── The cursors: what each store showed that was already consumed ──────────────────────────

def _cursor_path() -> str:
    from modules import config

    return os.path.join(config.DATA_DIR, CURSOR_DIR, CURSOR_FILE)


def _cursors() -> dict:
    """The cursors as stored, or {} when absent or unreadable (said)."""
    p = _cursor_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        log.error("heal: the triggers' cursors cannot be read (%s)", type(exc).__name__)
        return {}


def _move(fn):
    """Change the cursors under their lock; *fn(doc)* changes it in place."""
    from modules import filestore

    p = _cursor_path()
    with filestore.PathLock(p):
        doc = filestore.read_json_for_write(p, empty={})
        before = json.dumps(doc, sort_keys=True)
        out = fn(doc)
        if json.dumps(doc, sort_keys=True) != before:
            filestore.write_atomic(p, json.dumps(doc, indent=1, sort_keys=True))
    return out


def link_set(network: str) -> dict:
    """When *network*'s observed link set last changed: ``{"fingerprint", "first_seen",
    "changed_at", "changed_epoch"}`` ({} before the topology reader first stored it)."""
    return dict((_cursors().get("link_sets") or {}).get(network) or {})


# ── Where a device is ───────────────────────────────────────────────────────────────────────

class _Context:
    """One step's reads, each made once and only when needed: the networks' inventories, each
    network's mode, intent and blast radius."""

    def __init__(self, now: float):
        self.now = now
        self._nets = self._inv = None
        self._modes, self._intents, self._radius, self._peers = {}, {}, {}, {}

    def networks_of(self, device: str, allowed=None) -> list:
        from modules import attention as A

        if self._nets is None:
            self._nets = A._device_networks()
            if self._nets is None:
                raise RuntimeError("the networks' inventories cannot be read")
        held = self._nets.get(device) or []
        return [n for n in held if allowed is None or n in allowed]

    def by_address(self, address: str) -> list:
        from modules import attention as A
        from modules.heal.attribution import address_of

        if self._inv is None:
            inv, why = A._inventory()
            if inv is None:
                raise RuntimeError(why)
            self._inv = {}
            for ip, names in (inv[1] or {}).items():
                self._inv.setdefault(address_of(ip) or ip, set()).update(names)
        return sorted(self._inv.get(address_of(address) or address) or ())

    def mode(self, network: str) -> str:
        from modules.heal import policy

        if network not in self._modes:
            try:
                self._modes[network] = policy.current(network, self.now)["mode"]
            except Exception as exc:
                log.error("heal: %s's mode cannot be read (%s); it sights nothing",
                          network, exc)
                self._modes[network] = "off"
        return self._modes[network]

    def intents(self, network: str) -> dict:
        from modules.neighbours import committed_intents
        from modules.nsot import listref

        if network not in self._intents:
            got, err = ({}, "no such network")
            if listref.exists(network):
                got, err = committed_intents(listref.resolve(network).repo_dir)
            if err:
                log.warning("heal: %s's committed intent cannot be read (%s)", network, err)
            self._intents[network] = got or {}
        return self._intents[network]

    def radius_of(self, network: str):
        from modules.nsot import blast_radius

        if network not in self._radius:
            intents = self.intents(network)
            nets = blast_radius.host_networks()
            self._radius[network] = lambda d: blast_radius.radius(intents, nets, d)
        return self._radius[network]

    def peers(self, network: str) -> dict:
        from modules import attention as A

        return A._peer_names(network, self._peers)


def _store_networks(store: str, base: str):
    """The networks the store *store* of the reader *base* serves (its configuration's lists),
    or None when it cannot be told (then any network holding the device may take it)."""
    from modules import integration_groups as IG
    from modules import reader_job

    reader = {r.name: r for r in reader_job.readers()}.get(base)
    if reader is None or not reader.per_group:
        return None
    for g in IG.groups(tuple(reader.per_group)):
        if IG.store_name(base, g["id"]) == store:
            return set(g["lists"])
    return None


def _one_network(ctx: _Context, device: str, allowed=None) -> tuple:
    """``(network, why)``: the one network holding *device*, or ``(None, why)``."""
    held = ctx.networks_of(device, allowed)
    if len(held) == 1:
        return held[0], ""
    return None, (f"{device} is in no network's inventory" if not held else
                  f"{device} is in {len(held)} networks ({', '.join(held)}), so which one is not "
                  "decided")


def _subnets(iface: dict) -> set:
    out = set()
    raw = (iface.get("ipv4") or "").strip()
    if raw:
        try:
            out.add(ipaddress.ip_interface(raw.replace(" ", "/")).network)
        except ValueError:
            pass
    for addr in iface.get("ipv6") or []:
        try:
            net = ipaddress.ip_interface(str(addr).split()[0]).network
        except ValueError:
            continue
        if not net.is_link_local:
            out.add(net)
    return out


def far_ends(intents: dict, device: str, interface: str) -> list:
    """The devices committed intent puts at the far end of *device*'s *interface*: those with an
    interface in one of its subnets, IPv4 or IPv6 (a link-local one is no subnet). [] when
    intent does not hold the interface."""
    want = (interface or "").strip().lower()
    mine = next((i for i in ((intents.get(device) or {}).get("interfaces") or [])
                 if (i.get("name") or "").strip().lower() == want), None)
    if not want or mine is None:
        return []
    nets = _subnets(mine)
    out = set()
    for host, hv in intents.items():
        if host == device:
            continue
        for iface in (hv or {}).get("interfaces") or []:
            if not iface.get("shutdown") and _subnets(iface) & nets:
                out.add(host)
    return sorted(out)


# ── The steps ───────────────────────────────────────────────────────────────────────────────

def from_logs_tail(store: str, value: dict, now: float = None) -> dict:
    """The `logs-tail` step: each configuration-change line newer than the store's cursor."""
    from modules.heal import attribution as AT

    now = time.time() if now is None else float(now)
    lines = sorted((value or {}).get("lines") or [], key=lambda l: float(l.get("ts") or 0))
    seen = (_cursors().get("cursors") or {}).get(store)
    new = [l for l in lines if seen is None or float(l.get("ts") or 0) > float(seen)]
    if not new:
        return _counts()
    _move(lambda d: d.setdefault("cursors", {}).__setitem__(
        store, max(float(l.get("ts") or 0) for l in new)))
    ctx, counts, out = _Context(now), _counts(), []
    allowed = _store_networks(store, "logs-tail")
    for l in new:
        if not AT.is_change(l.get("mn"), l.get("text")):
            continue
        dev = l.get("dev") or ""
        network, why = _one_network(ctx, dev, allowed)
        if network is None:
            counts["unplaced"].append(why)
            continue
        if ctx.mode(network) == "off":
            counts["off"] += 1
            continue
        at = float(l.get("ts") or 0)
        a = AT.attribute(network, dev, at)
        if a["by"] == AT.MERCURY:
            counts["mercury"] += 1
            continue
        person = AT.person_of(l.get("mn"), l.get("text"))
        out.append((network, dev, {
            "kind": "config_change", "key": "cfg:" + _key(dev, l.get("ts"), l.get("text")),
            "epoch": at, "at": l.get("at") or _iso(at), "source": store,
            "attribution": {k: a.get(k) for k in ("by", "words", "evidence")},
            "person": person,
            "words": (f"{l.get('mn')} on {dev} at {l.get('at') or _iso(at)}: {a['words']}; "
                      f"{person.get('words') or 'the line names nobody'}")}))
    return _deliver(ctx, out, counts)


def from_alerts(store: str, value: dict, now: float = None) -> dict:
    """The `grafana-alerts` step (N2): each firing alert on a managed device, once an episode."""
    from modules.evidence_pack import alert_key, firing

    now = time.time() if now is None else float(now)
    insts = firing(value or {})
    keys = {alert_key(i): i for i in insts}
    seen = set((_cursors().get("seen") or {}).get(store) or [])
    _move(lambda d: d.setdefault("seen", {}).__setitem__(store, sorted(keys)))
    new = [(k, i) for k, i in keys.items() if k not in seen]
    if not new:
        return _counts()
    ctx, counts, out = _Context(now), _counts(), []
    allowed = _store_networks(store, "grafana-alerts")
    for key, inst in new:
        device = inst.get("device") or ""
        if not device and inst.get("address"):
            found = ctx.by_address(inst["address"])
            device = found[0] if len(found) == 1 else ""
            if not device:
                counts["unplaced"].append(
                    f"the polled address {inst['address']} is "
                    + ("no device's" if not found else f"{len(found)} devices'"))
                continue
        if not device:
            counts["unplaced"].append(f"the alert {inst.get('rule')} names no device")
            continue
        network, why = _one_network(ctx, device, allowed)
        if network is None:
            counts["unplaced"].append(why)
            continue
        if ctx.mode(network) == "off":
            counts["off"] += 1
            continue
        labels = inst.get("labels") or {}
        iface = next((labels[k] for k in INTERFACE_LABELS if labels.get(k)), "")
        far = far_ends(ctx.intents(network), device, iface) if iface else []
        at = (_epoch(inst.get("active_at")) or _epoch(inst.get("starts_at")) or now)
        on = f" on {iface}" if iface else ""
        silenced = " (silenced in Grafana)" if inst.get("silenced_by") else ""
        base = {"kind": "alert", "epoch": at, "at": _iso(at), "source": store,
                "rule": inst.get("rule") or "", "interface": iface}
        if labels.get("nmas") == "telemetry" and labels.get("subscription"):
            # A lost telemetry stream (scripts/nmas-telemetry-rules' labels): its subscription,
            # and how long its alert takes to see a stopped stream, for the stream runbook
            # (C2828, `diagnose_stream.stream_of`).
            base["subscription"] = str(labels["subscription"])
            if labels.get("detect_seconds"):
                base["detect_seconds"] = str(labels["detect_seconds"])
        out.append((network, device, dict(
            base, key=f"alert:{key}", related=far,
            words=(f"the alert {inst.get('rule') or '?'} fired on {device}{on}{silenced}"
                   + (f": {inst['absence']}" if inst.get("absence") else "")))))
        for end in far:
            out.append((network, end, dict(
                base, key=f"alert:{key}:{end}", related=[device],
                words=(f"the alert {inst.get('rule') or '?'} fired on {device}{on}{silenced}; "
                       f"{end} is the far end committed intent names for it"))))
    return _deliver(ctx, out, counts)


def from_adjacencies(store: str, value: dict, now: float = None) -> dict:
    """The `adjacencies` step: each adjacency down for its two reads, once an episode."""
    from modules.readers.adjacencies import PERSIST_READS

    now = time.time() if now is None else float(now)
    down = {f"{k}|{e.get('since')}": e for k, e in ((value or {}).get("adjacencies") or {}).items()
            if int(e.get("reads") or 0) >= PERSIST_READS}
    seen = set((_cursors().get("seen") or {}).get(store) or [])
    _move(lambda d: d.setdefault("seen", {}).__setitem__(store, sorted(down)))
    new = [(k, e) for k, e in down.items() if k not in seen]
    if not new:
        return _counts()
    ctx, counts, out = _Context(now), _counts(), []
    for ident, e in new:
        network = e.get("list") or ""
        if ctx.mode(network) == "off":
            counts["off"] += 1
            continue
        devices = sorted(e.get("devices") or [])
        at = _epoch(e.get("since")) or now
        for d in devices:
            out.append((network, d, {
                "kind": "adjacency", "key": "adj:" + _key(ident, d), "epoch": at,
                "at": _iso(at), "source": store, "protocol": e.get("protocol") or "",
                "related": [x for x in devices if x != d],
                "words": (f"the {e.get('protocol') or 'routing'} adjacency "
                          f"{' – '.join(devices)} is down since {e.get('since')} "
                          f"({e.get('reads')} reads)")}))
    return _deliver(ctx, out, counts)


def from_adjacency_log(store: str, value: dict, now: float = None, *, planned=None,
                       receipts=None) -> dict:
    """The `adjacency-log` step: each logged drop newer than the store's cursor that no planned
    restart or deploy explains, both ends; and each new duplicate router-id episode (C2446)."""
    from modules import attention as A

    now = time.time() if now is None else float(now)
    adj = (value or {}).get("adjacencies") or {}
    seen = (_cursors().get("cursors") or {}).get(store)
    new = [(k, a, d) for k, a in adj.items() for d in a.get("drops") or []
           if seen is None or float(d.get("epoch") or 0) > float(seen)]
    episodes = _duplicate_episodes(store, value)
    if not new and not episodes:
        return _counts()
    if new:
        _move(lambda doc: doc.setdefault("cursors", {}).__setitem__(
            store, max(float(d.get("epoch") or 0) for _k, _a, d in new)))
    ctx, counts, out = _Context(now), _counts(), []
    _duplicate_triggers(store, episodes, ctx, counts, out)
    if planned is None and new:
        from modules import restarts
        planned = restarts.planned_rows()
    if receipts is None:
        from modules.heal import attribution
        receipts = attribution._receipts
    for k, a, d in sorted(new, key=lambda x: float(x[2].get("epoch") or 0)):
        network, device = a.get("list") or "", a.get("device") or ""
        if ctx.mode(network) == "off":
            counts["off"] += 1
            continue
        peers = ctx.peers(network)
        if A._explained(d, a, planned, receipts, peers):
            counts["explained"] += 1
            continue
        peer = peers.get(str(a.get("neighbor") or ""), "")
        at = float(d.get("epoch") or 0)
        # C2823: the drop's own facts, kept for the decision to name its cause (the interface
        # it was logged on, the neighbour, who logged it and why). ``port``, never
        # ``interface``: a logged drop is not a link's symptom (`decide._symptom`).
        base = {"kind": "adjacency_log", "epoch": at, "at": d.get("at") or _iso(at),
                "source": store, "protocol": a.get("protocol") or "",
                "port": a.get("interface") or "", "neighbor": str(a.get("neighbor") or ""),
                "peer": peer, "logged_by": device, "reason": d.get("reason") or "",
                "words": (f"{device} logged its {a.get('protocol')} adjacency to "
                          f"{a.get('neighbor')}" + (f" ({peer})" if peer else "")
                          + f" down at {d.get('at') or _iso(at)}: {d.get('reason') or ''}")}
        out.append((network, device, dict(base, key="adjlog:" + _key(k, at),
                                          related=[peer] if peer else [])))
        if peer and peer != device:
            out.append((network, peer, dict(base, key="adjlog:" + _key(k, at, peer),
                                            related=[device])))
    return _deliver(ctx, out, counts)


def _duplicate_episodes(store: str, value: dict) -> list:
    """C2446: each device's duplicate router-id report with a line newer than the store's
    cursor, ``[(group key, group, device, report, episode start)]``, the cursors moved. One
    EPISODE per device and id: a report whose first line in the window comes more than the
    reader's quiet time after the last line consumed starts a new one; any other continues the
    episode under way (a gap inside the window is not seen, and continues it)."""
    from modules.readers import adjacency_log as AL

    dups = (value or {}).get("duplicates") or {}
    if not dups:
        return []

    def change(doc):
        held = doc.setdefault("duplicates", {}).setdefault(store, {})
        out = []
        for k, g in sorted(dups.items()):
            for device, r in sorted((g.get("reports") or {}).items()):
                last, first = float(r.get("last_epoch") or 0), float(r.get("first_epoch") or 0)
                was = held.get(f"{k}|{device}") or {}
                if was and last <= float(was.get("last") or 0):
                    continue
                start = (first if not was or first - float(was.get("last") or 0)
                         > AL.QUIET_SECONDS else float(was.get("episode") or first))
                held[f"{k}|{device}"] = {"last": last, "episode": start}
                if not was or start != float(was.get("episode") or 0):
                    out.append((k, g, device, r, start))
        return out

    return _move(change)


def _duplicate_triggers(store: str, episodes: list, ctx, counts: dict, out: list) -> None:
    """Each new episode a trigger on the device that logged it, and on each device committed
    intent gives a neighbour address it named (both ends, as a logged drop's)."""
    for k, g, device, r, start in episodes:
        network = g.get("list") or ""
        if ctx.mode(network) == "off":
            counts["off"] += 1
            continue
        peers = ctx.peers(network)
        named = sorted({peers.get(a, "") for a in r.get("neighbors") or []} - {"", device})
        claimers = sorted(set(g.get("reports") or {}) - {device})
        rid, proto = g.get("router_id") or "", g.get("protocol") or "OSPF"
        base = {"kind": "duplicate_router_id", "epoch": start, "at": _iso(start),
                "source": store, "protocol": proto, "router_id": rid,
                "words": (f"{device} logged a duplicate {proto} router-id {rid}"
                          + "".join(f" from {a}" + (f" ({peers[a]})" if peers.get(a) else "")
                                    for a in r.get("neighbors") or [])
                          + "".join(f" on {i}" for i in r.get("interfaces") or [])
                          + f" since {_iso(start)}")}
        related = sorted(set(named) | set(claimers))
        out.append((network, device, dict(base, key="dup:" + _key(k, device, start),
                                          related=related)))
        for peer in named:
            if peer not in claimers:
                out.append((network, peer, dict(base, key="dup:" + _key(k, device, start, peer),
                                                related=[device])))


def _link_fingerprint(graph: dict) -> str:
    from modules.readers.topology_graph import _link_key

    keys = sorted(f"{layer}:{_link_key(layer, l)}"
                  for layer, links in ((graph or {}).get("layers") or {}).items()
                  for l in links or [])
    return _key(*keys) if keys else ""


def from_topology(store: str, value: dict, now: float = None) -> dict:
    """The `topology-graph` step: when each network's observed link set (each layer's links,
    their states aside) last changed, for the topology hold. The first sighting is no change:
    the set was not watched before it."""
    from modules.integration_groups import network_names
    from modules.readers.topology_graph import network_of

    now = time.time() if now is None else float(now)
    if not (value or {}).get("configured"):
        return _counts()
    found = {}
    for name in network_names():
        try:
            graph = network_of(value, name)
        except Exception:
            graph = None
        if graph is not None:
            found[name] = _link_fingerprint(graph)

    def change(doc):
        sets = doc.setdefault("link_sets", {})
        moved = []
        for name, fp in found.items():
            was = sets.get(name)
            if was is None:
                sets[name] = {"fingerprint": fp, "first_seen": _iso(now), "changed_at": "",
                              "changed_epoch": 0}
            elif was.get("fingerprint") != fp:
                sets[name] = dict(was, fingerprint=fp, changed_at=_iso(now), changed_epoch=now)
                moved.append(name)
        return moved

    moved = _move(change)
    return dict(_counts(), link_sets_changed=moved)


def after_drift_record(network: str, result: dict, now: float = None) -> dict:
    """The drift record's trigger (`DriftChecker.record`): each device the run found departed,
    its read kept as the incident's first; and each device the run READ at its golden
    (``clean_devices``, C2813) ends the incident standing on a departure it judged before that
    read (`clean_ended`). A run that names no device read clean (one recorded before the field,
    or a run that read none) ends nothing: absence is not evidence of a clean read."""
    now = time.time() if now is None else float(now)
    ctx, counts, out = _Context(now), _counts(), []
    drifted = (result or {}).get("drifted_devices") or []
    clean = (result or {}).get("clean_devices") or []
    if not drifted and not clean:
        return counts
    if ctx.mode(network) == "off":
        counts["off"] += len(drifted)
        return counts
    counts["ended"] = clean_ended(network, result, now)
    if not drifted:
        return counts
    for e in drifted:
        host = e.get("hostname") or ""
        at = float(e.get("read_at") or now)
        read = {"epoch": at, "at": _iso(at), "state": "drifted",
                "departure": e.get("departure") or "", "changed_lines": e.get("changed_lines"),
                "error": "", "by": f"the drift check ({(result or {}).get('triggered_by')})"}
        out.append((network, host, {
            "kind": "drift", "key": f"drift:{host}@{at}", "epoch": at, "at": _iso(at),
            "source": "drift-check", "read": read,
            "words": (f"the drift check ({(result or {}).get('triggered_by') or '?'}) found "
                      f"{host} departed from its golden ({e.get('changed_lines')} line(s))")}))
    return _deliver(ctx, out, counts)


def clean_ended(network: str, result: dict, now: float) -> list:
    """C2813: each device the drift run read at its golden (``clean_devices``, each with its
    ``read_at``) whose incident stands on a departure from that golden (`incidents.
    ends_at_golden`) and was decided BEFORE the read is ended: nothing to heal, the run named
    (`decide.end_standing`). Returns the decisions recorded. Never raises: a failure is
    logged, and the incident stands until the next run reads it."""
    from modules.heal import decide, incidents

    by = (result or {}).get("triggered_by") or "?"
    ended = []
    for e in (result or {}).get("clean_devices") or []:
        host = (e or {}).get("hostname") or ""
        at = float((e or {}).get("read_at") or 0)
        try:
            inc = incidents.standing_of(network, host) if host else {}
            s = inc.get("standing") or {}
            if not inc or not at or at <= float(s.get("epoch") or 0) \
                    or not incidents.ends_at_golden(s):
                continue
            d = decide.end_standing(
                network, inc["id"],
                (f"nothing to heal: the drift check ({by}) read {host} at its golden at "
                 f"{decide._hhmm(at)} UTC, after its decision {s.get('decision') or '?'}, so the "
                 "departure it judged no longer stands"),
                now=now, by=f"the drift check ({by})",
                read_words=(f"{host} read by the drift check ({by}) at {_iso(at)}: at its "
                            "golden"))
        except Exception as exc:
            log.error("heal: %s's clean read in %s did not end its incident: %s: %s", host,
                      network, type(exc).__name__, exc)
            continue
        if d:
            ended.append(d["id"])
    return ended


def _counts() -> dict:
    return {"sighted": 0, "mercury": 0, "off": 0, "explained": 0, "unplaced": [],
            "failed": [], "incidents": []}


def _deliver(ctx: _Context, out: list, counts: dict) -> dict:
    """Sight each ``(network, device, trigger)`` and wake the detect pass."""
    from modules.heal import detect, incidents

    for network, device, trigger in out:
        try:
            got = incidents.sight(network, device, trigger, now=ctx.now,
                                  radius_of=ctx.radius_of(network))
        except Exception as exc:
            counts["failed"].append(f"{device} in {network}: {type(exc).__name__}: {exc}")
            log.error("heal: a trigger on %s in %s was not recorded: %s: %s", device, network,
                      type(exc).__name__, exc)
            continue
        counts["sighted"] += 1
        counts["incidents"].append(got)
        if trigger.get("read") and got["action"] != "duplicate":
            try:
                incidents.record_read(network, got["incident"], device, trigger["read"])
            except Exception as exc:
                log.error("heal: %s's read in %s was not kept: %s", device, network, exc)
    if counts["sighted"]:
        detect.wake()
    if counts["sighted"] or counts["failed"] or counts["unplaced"]:
        log.info("heal: triggers: %d sighted, %d Mercury's own, %d where healing is off, %d "
                 "unplaced, %d failed", counts["sighted"], counts["mercury"], counts["off"],
                 len(counts["unplaced"]), len(counts["failed"]))
    return counts


STEPS = {"logs-tail": from_logs_tail, "grafana-alerts": from_alerts,
         "adjacencies": from_adjacencies, "adjacency-log": from_adjacency_log,
         "topology-graph": from_topology}
