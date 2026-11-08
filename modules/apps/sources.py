"""The controller app deploy's sources, wired (C2765): what `modules/apps/deploy_op.py` reads,
each from the carrier Mercury already has for it, and the one that has none refused by name.

| Read (`deploy_op.Sources`) | Where it comes from |
|---|---|
| ``controllers`` | the network's committed NSOT export (`modules/nsot/export.read`, HEAD, never the working tree): each device that parents a Service named ``openflow``; its listen address and port from that Service (`openflow_values.service_target`, IPv4 or IPv6); its systemd unit from its rendered config context's ``openflow.unit``; its login from the network's inventory (`load_saved_devices`, no I/O) |
| ``registered`` | **not built**: the app registry is P4's (the SDN design revision 7, 11c.3); refused by name, `deploy_op.NOT_WIRED["registered"]` |
| ``host_reads`` | the host's three shaped reads (`channel.host_commands`), asked through the reads engine (`reads.run`, the one engine: the capture list's rule, the device held, masked, recorded in History › Reads), as the person previewing or confirming |
| ``expected`` | the same committed export: every switch whose OpenFlow values (`openflow_values.from_export`) name this controller, its DPID from ``openflow_datapath_id`` as an integer (the driver's form, C2756), its profile entry by its platform and its ``os_version`` (`profile.select`); every connected cable between two of their OpenFlow ports, each end numbered by its ``openflow_port``, else by its platform's own numbering (`openflow_templates.numbered_by_platform`) |
| ``observe`` | the controller live, through the network's controller connection (`connections.choose`: the controller host's ``openflow.connection``, or the only one) and its driver's ``switches()`` and ``links()``; no app's ``/health`` is read (the driver's read is not built, C2677), so each is said as no answer |
| ``controller_read`` | stored, for the Apps tab: the newest run in the reads engine's records holding both the unit's ``systemctl show`` and ``systemctl cat`` answers for the host (`reads.runs`), and the SDN reader's stored topology for its connection (`topology.stored`); nothing is asked of a device on a page view |

**Each refusal names what it compared and both sides:** a controller host the export names
with no unit, a unit not of a unit's shape, a host not in the inventory, two ``openflow``
Services on one host, a switch whose values cannot be read, a cable end with no OpenFlow port
number. A controller with such a problem is still listed (so the Apps tab draws it with its
record), and every read that needs what is missing refuses, naming it.

Reads only: nothing here writes but the reads engine's own record of a host read (a preview
asks the host, as Show commands does).
"""

import logging
import time

from modules.apps import deploy_op

log = logging.getLogger(__name__)

#: The rendered config context's keys on the controller host's device (NetBox's data, read
#: through the export): the unit Ryu runs as, and the Mercury controller connection it answers
#: on when the network has more than one.
UNIT_KEY = ("openflow", "unit")
CONNECTION_KEY = ("openflow", "connection")
SERVICE = "openflow"
#: The reads engine's records searched for the stored host read, newest first.
STORED_RUNS = 50


def _iso(epoch) -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))
    except (TypeError, ValueError):
        return ""


def _ctx(device: dict, path: tuple) -> str:
    node = (device or {}).get("config_context") or {}
    for part in path:
        if not isinstance(node, dict):
            return ""
        node = node.get(part)
    return str(node).strip() if isinstance(node, (str, int)) else ""


def _export(network: str) -> dict:
    """``{"ok", "export", "error"}``: *network*'s committed export, or why not."""
    from modules.nsot import export as X

    try:
        got = X.read(network)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.warning("controller sources: %s's export could not be read: %s", network, exc)
        return {"ok": False, "export": None,
                "error": f"its NSOT export could not be read ({type(exc).__name__}: {exc})"}
    if not got.get("ok"):
        return {"ok": False, "export": None, "error": got.get("error") or "no export"}
    return {"ok": True, "export": got["export"], "error": ""}


def _inventory(network: str) -> dict:
    """``{hostname (case-folded): row}`` from the network's inventory (no I/O for NetBox's)."""
    from modules.device import load_saved_devices
    from modules.nsot import listref

    rows = load_saved_devices(listref.resolve(network).csv_path)
    return {str(d.get("hostname") or "").lower(): d for d in rows}


def controllers_from(export: dict, network: str, inventory: dict) -> list:
    """Each controller host the export names (the parent of a Service named ``openflow``), as
    `deploy_op.Sources.controllers` lists it, with ``problems`` naming what is missing."""
    from modules import discovery
    from modules.nsot import export as X
    from modules.sdn import openflow_values

    by_parent: dict = {}
    for svc in X.services_named(export, SERVICE):
        by_parent.setdefault(svc.get("parent") or "", []).append(svc)
    sha = str(export.get("sha256") or "")[:12]
    out = []
    for parent in sorted(by_parent):
        svcs, problems = by_parent[parent], []
        if not parent:
            problems.append("a Service named openflow has no parent device or virtual machine")
        device = X.device(export, parent) or {}
        if parent and not device:
            problems.append(f"the NSOT export ({sha}) holds no device {parent!r}, the parent "
                            "of its openflow Service")
        if len(svcs) > 1:
            problems.append(f"{parent} parents {len(svcs)} Services named openflow (ports "
                            f"{', '.join(str(s.get('ports')) for s in svcs)}), and a controller "
                            "listens on one")
        svc = svcs[0]
        proto = str(svc.get("protocol") or "")
        if proto and proto.lower() != "tcp":
            problems.append(f"{parent}'s openflow Service's protocol is {proto}, and OpenFlow "
                            "is TCP")
        target = openflow_values.service_target(svc, device)
        port = int(target["port"]) if target["port"].isdigit() else None
        if not target["address"]:
            problems.append(f"{parent}'s openflow Service has no IP address and {parent} no "
                            "primary IPv4 or IPv6, so where Ryu listens is not known")
        if port is None:
            problems.append(f"{parent}'s openflow Service has no port")
        unit = _ctx(device, UNIT_KEY)
        if not unit:
            problems.append(f"NetBox's config context for {parent} has no openflow.unit, the "
                            "systemd unit Ryu runs as, so the host's reads can't name it")
        elif discovery.command_refusal("linux", f"systemctl cat {unit}"):
            problems.append(f"{parent}'s openflow.unit {unit[:80]!r} is not a unit's name (one "
                            "token: letters, digits, _ . @ -)")
            unit = ""
        dev = inventory.get(parent.lower())
        if parent and dev is None:
            problems.append(f"{parent} is not a device of {network}'s inventory, so Mercury has "
                            "no login to reach it by (it enters as a host: its role's "
                            "mercury_kind host, its platform linux)")
        out.append({"name": parent, "unit": unit, "dev": dict(dev or {}),
                    "listen": {"host": target["address"], "port": port},
                    "service": (f"NetBox's openflow Service on {parent}, from the NSOT export "
                                f"{sha}"),
                    "connection": _ctx(device, CONNECTION_KEY), "problems": problems,
                    "export_sha256": str(export.get("sha256") or "")})
    return out


def _select(device: dict) -> dict:
    """`profile.select`'s answer for a switch, by its platform (the platform map) and NetBox's
    ``os_version``; "can't tell" naming which is missing, never a pass."""
    from modules.inventory.netbox_source import map_platform
    from modules.platforms import profile

    name = device.get("name") or "?"
    driver, warning = map_platform(device.get("platform") or "")
    if not driver:
        return {"ok": False, "error": f"{name}: {warning}"}
    version = str((device.get("custom_fields") or {}).get("os_version") or "").strip()
    if not version:
        return {"ok": False, "error": (f"NetBox holds no os_version for {name} (its custom "
                                       "field), so which platform profile entry covers it "
                                       "can't be told")}
    return profile.select(driver, version)


def expected_from(export: dict, controller: str) -> dict:
    """``{"switches", "links", "problems"}`` for *controller* from *export* (see the module's
    table). Pure: the seam the tests use."""
    from modules.nsot import export as X
    from modules.sdn import openflow_templates, openflow_values
    from modules.sdn.drivers.base import SpecError, parse_dpid

    body = export.get("body") or {}
    # A controller host (the parent of an openflow Service) is never one of its switches.
    hosts = {s.get("parent") for s in X.services_named(export, SERVICE)}
    tagged = sorted({i.get("device") for i in body.get("interfaces") or []
                     if openflow_values.TAG in (i.get("tags") or [])} - {None, ""} - hosts)
    switches, problems, values = [], [], {}
    for name in tagged:
        device = X.device(export, name) or {}
        got = openflow_values.from_export(export, name)
        if not got["ok"]:
            problems.append(f"{name}'s OpenFlow values can't be read: {got['error']}")
            continue
        v = got["values"]
        if v.get("controller.name") != controller:
            continue
        dpid = None
        if v.get("openflow.datapath_id"):
            try:
                dpid = parse_dpid(v["openflow.datapath_id"])
            except SpecError as exc:
                problems.append(f"{name}'s openflow_datapath_id: {exc}")
                continue
        selected = _select(device)
        values[name] = (v, selected, dpid)
        switches.append({"name": name, "dpid": dpid, "selected": selected})

    def port_no(device, port):
        v, selected, _dpid = values[device]
        given = (v.get("port.openflow_port") or {}).get(port)
        if given:
            return int(given), ""
        mode = ((selected.get("entry") or {}).get("openflow") or {}).get("port_numbering") \
            if selected.get("ok") else None
        own = openflow_templates.numbered_by_platform(port, mode)
        if own is not None:
            return own, ""
        return None, (f"{device}'s {port} has no OpenFlow port number: NetBox's openflow_port "
                      f"is not set, and its platform's numbering ({mode or 'not known'}) gives "
                      "none")

    links = []
    for cable in body.get("cables") or []:
        if str(cable.get("status") or "connected") != "connected":
            continue
        a, b = cable.get("a") or [], cable.get("b") or []
        ends = [e for e in a + b if len(e) == 2 and e[0] in values
                and e[1] in (values[e[0]][0].get("ports") or [])]
        if len(ends) < 2 or len(a) != 1 or len(b) != 1:
            if len(ends) >= 2:
                problems.append(f"a cable between {', '.join(':'.join(e) for e in ends)} has "
                                "more than one termination on a side, so which ports it joins "
                                "can't be told")
            continue
        words = f"the cable {':'.join(a[0])} to {':'.join(b[0])}"
        got, why = [], []
        for dev_name, port in (a[0], b[0]):
            number, missing = port_no(dev_name, port)
            got.append({"dpid": values[dev_name][2], "port_no": number})
            if missing:
                why.append(missing)
        if why:
            problems.append(f"{words}: {'; '.join(why)}")
            continue
        if any(e["dpid"] is None for e in got):
            continue          # its switch has no DPID: the plan refuses that switch by name
        links.append({"src": got[0], "dst": got[1]})
    return {"switches": switches, "links": links, "problems": problems}


class Wired(deploy_op.Sources):
    """The production sources (the module's table). *actor* is the person a host read is held
    and recorded for (`for_actor`); a page view's sources have none and ask no device."""

    def __init__(self, actor: str = ""):
        self.actor = actor

    def for_actor(self, actor: str):
        return Wired(actor)

    def controllers(self, network):
        got = _export(network)
        if not got["ok"]:
            return {"state": "unreadable", "controllers": [],
                    "error": (f"they are read from {network}'s committed NSOT export, and "
                              f"{got['error']}")}
        try:
            inventory = _inventory(network)
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            return {"state": "unreadable", "controllers": [],
                    "error": f"{network}'s inventory could not be read ({exc})"}
        return {"state": "ok", "error": "",
                "controllers": controllers_from(got["export"], network, inventory)}

    def registered(self, network):
        return {"state": "not_wired", "apps": [], "repo": {},
                "error": deploy_op.NOT_WIRED["registered"]}

    def host_reads(self, network, controller):
        from modules.apps import channel
        from modules.nsot import reads

        empty = {"show": "", "ls": "", "cat": "", "at": None}
        problems = controller.get("problems") or []
        if problems:
            return dict(empty, state="unreadable", error="; ".join(problems))
        if not self.actor:
            return dict(empty, state="unreadable",
                        error="a host's reads are asked for a person, and none was named")
        host = (controller.get("dev") or {}).get("hostname") or controller["name"]
        cmds = channel.host_commands(controller["unit"])
        try:
            rec = reads.run(network, [host], list(cmds.values()), self.actor,
                            purpose="the controller app deploy's plan: the host's three reads",
                            inline=True)
        except reads.Refused as exc:
            return dict(empty, state="unreadable", error=str(exc))
        res = (rec.get("results") or {}).get(host) or {}
        answers = {a.get("command"): a for a in res.get("answers") or []}
        out, why = dict(empty, run=rec.get("id", "")), []
        for part, command in cmds.items():
            a = answers.get(command) or {}
            if a.get("state") != reads.ANSWERED:
                said = a.get("why") or res.get("why") or res.get("state") or "no answer"
                why.append(f"`{command}` was not answered ({said})")
            elif a.get("cut"):
                why.append(f"`{command}`'s answer was cut at {a.get('bytes')} bytes (the "
                           "network's reads cap), so it can't be read whole")
            else:
                out[part] = a.get("answer") or ""
        if why:
            return dict(out, state="unreadable", error="; ".join(why))
        ats = [a.get("at") for a in answers.values() if a.get("at")]
        return dict(out, state="ok", error="", at=_iso(max(ats)) if ats else None)

    def expected(self, network, controller):
        got = _export(network)
        if not got["ok"]:
            return {"state": "unreadable", "switches": [], "links": [],
                    "error": f"{network}'s committed NSOT export: {got['error']}"}
        exp = expected_from(got["export"], controller["name"])
        if exp["problems"]:
            return {"state": "unreadable", "switches": [], "links": [],
                    "error": "; ".join(exp["problems"])}
        return {"state": "ok", "error": "", "switches": exp["switches"], "links": exp["links"]}

    def _driver(self, network, controller):
        from modules.sdn import connections

        name, why = connections.choose(network, controller.get("connection") or "",
                                       purpose=f"the one {controller.get('name')} answers on")
        if why:
            return None, name, why
        made = connections.driver_for(network, name)
        if not made.get("ok"):
            return None, name, made.get("error") or "no driver"
        return made["driver"], name, ""

    def observe(self, network, controller):
        drv, name, why = self._driver(network, controller)
        if drv is None:
            no = {"ok": False, "error": f"the controller connection: {why}"}
            return {"switches": dict(no), "links": dict(no), "health": {}, "connection": name}
        out = {"health": {}, "connection": name}
        for what in ("switches", "links"):
            try:
                out[what] = getattr(drv, what)()
            except Exception as exc:                  # noqa: BLE001 (a read's failure, said)
                out[what] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
        return out

    def controller_read(self, network, controller):
        from modules.apps import channel
        from modules.nsot import listref, reads

        none = {"at": None, "show": "", "cat": "", "health": {}, "observed": None}
        problems = controller.get("problems") or []
        if problems:
            return dict(none, state="unread", error="; ".join(problems))
        host = (controller.get("dev") or {}).get("hostname") or controller["name"]
        cmds = channel.host_commands(controller["unit"])
        try:
            got = reads.runs(network, device=host, limit=STORED_RUNS,
                             data_dir=listref.resolve(network).data_dir)
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            return dict(none, state="unreadable", error=f"the reads' records: {exc}")
        for r in got["runs"]:
            res = (r.get("results") or {}).get(host) or {}
            answers = {a.get("command"): a for a in res.get("answers") or []
                       if a.get("state") == reads.ANSWERED and "answer" in a
                       and not a.get("cut")}
            if cmds["show"] in answers and cmds["cat"] in answers:
                show, cat = answers[cmds["show"]], answers[cmds["cat"]]
                return dict(none, state="ok", error="",
                            at=_iso(max(show.get("at") or 0, cat.get("at") or 0)),
                            run=r.get("id", ""), show=show["answer"], cat=cat["answer"],
                            observed=self._stored_topology(network, controller))
        return dict(none, state="unread",
                    error=(f"no read of {controller['unit']} on {host} is recorded "
                           f"(`{cmds['show']}` and `{cmds['cat']}` in one run): a deploy's "
                           "preview reads it" + (f"; {len(got['unreadable'])} reads record(s) "
                                                 "could not be read" if got["unreadable"]
                                                 else "")))

    def _stored_topology(self, network, controller):
        """The SDN reader's stored switches and links for the controller's connection, in the
        post-check's shape, or None when it holds no read of it."""
        from modules.sdn import connections, topology

        name, why = connections.choose(network, controller.get("connection") or "")
        if why:
            return None
        got = topology.stored(network)
        entry = next((c for c in got.get("controllers") or [] if c.get("name") == name), None)
        if not entry or entry.get("state") != "read":
            return None
        return {"switches": {"ok": True, "switches": entry.get("switches") or []},
                "links": {"ok": True, "links": entry.get("links") or []}, "health": {},
                "at": entry.get("read_at", "")}
