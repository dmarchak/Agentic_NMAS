"""A switch's OpenFlow values, read from NetBox (docs/LAB9_SDN_GAP.md 2.2, the decided model;
docs/LAB9_OPENFLOW.md section 1). Read only: nothing here writes to NetBox.

| Value | Where in NetBox |
|---|---|
| ``switch.address`` | the device's primary IP (IPv4, else IPv6) |
| ``controller.address``, ``controller.port`` | the Service named ``openflow`` (TCP): its first port, and its first IP address, else its device's primary IP |
| ``openflow.version``, ``openflow.transport``, ``openflow.fail_mode`` | the device's config context, key ``openflow`` (inherited by role, site or platform; overridable per device) |
| ``openflow.instance`` | the device's custom field ``openflow_instance``, else the config context's ``openflow.instance`` |
| ``openflow.datapath_id`` (optional) | the device's custom field ``openflow_datapath_id`` (16 hex digits) |
| ``ports`` | the device's interfaces tagged ``openflow`` |
| ``port.openflow_port`` | each of those interfaces' custom field ``openflow_port`` (its OpenFlow port number, ``{port: number}``; C2603) |
| ``openflow.vlan`` | the untagged VLAN those interfaces share |
| ``mgmt.vlan`` | the VLAN of the interface holding the primary IP (its untagged VLAN, or a ``vlan<N>`` interface's N) |

**The management interface is never an OpenFlow port** (Lab 9's management network is separate
and non-OpenFlow; the operator, 2026-11-05). An interface is the management interface when NetBox
marks it ``mgmt_only``, or it holds the device's primary IP (IPv4 or IPv6), or its OOB IP
(``oob_ip``) (`management_reason`). Such an interface is left out of ``ports`` even when tagged
``openflow``, and ``excluded`` says so by name. A device whose only tagged interfaces are
management ones is refused, naming them, and so is an OpenFlow VLAN equal to the management
VLAN.

Which controller: a config context's ``openflow.controller`` names the controller's device when
NetBox holds more than one ``openflow`` Service; with one, it is that one. ``openflow.version``
defaults to ``1.3`` and ``openflow.fail_mode`` to ``secure`` (Lab 8's switches: Mininet's
`OVSSwitch` is secure by default, and a controller-only network is the lab's intent), each
said in ``defaults`` when used; ``openflow.transport`` defaults to ``tcp``.

**Every value is checked for its shape** before any template sees it (a field spliced into a
command is one token of its shape): an address by `ipaddress`, a port 1 to 65535, a name one
interface-name token, a VLAN 1 to 4094, a datapath id 16 hex digits and not all zero, an
OpenFlow port number 1 to 65279 (Open vSwitch's `ofport_request` range, inside OpenFlow 1.3's
physical ports) and no number given to two ports of one switch. Whether a port number is
REQUIRED, and whether it must equal the platform's own numbering, is the platform profile's
(`port_numbering`), checked at render (`openflow_templates.numbering_problems`).

**From NetBox or from an export:** `from_netbox` takes the records as NetBox's REST API returns
them; `from_export` takes a committed NSOT export (`modules/nsot/export.py`), so a plan reads the
same bytes offline that it names the hash of.
"""

import ipaddress
import logging
import re

log = logging.getLogger(__name__)

#: Where each value comes from in NetBox, as a refusal names it.
WHERE = {
    "switch.address": "NetBox: the device's primary IPv4 or IPv6 address",
    "controller.address": "NetBox: the 'openflow' Service's IP address, or its device's primary IP",
    "controller.port": "NetBox: the 'openflow' Service's port",
    "openflow.instance": ("NetBox: the device's custom field openflow_instance, or its config "
                          "context's openflow.instance"),
    "openflow.datapath_id": "NetBox: the device's custom field openflow_datapath_id",
    "openflow.version": "NetBox: the config context's openflow.version",
    "openflow.transport": "NetBox: the config context's openflow.transport",
    "openflow.fail_mode": "NetBox: the config context's openflow.fail_mode",
    "openflow.vlan": "NetBox: the untagged VLAN of the interfaces tagged openflow",
    "mgmt.vlan": "NetBox: the VLAN of the interface holding the device's primary IP",
    "ports": "NetBox: the device's interfaces tagged openflow",
    "port.openflow_port": "NetBox: each OpenFlow interface's custom field openflow_port",
}
#: An OpenFlow port number: Open vSwitch's `ofport_request` takes 1 to 65279
#: (ovs-vswitchd.conf.db(5), Interface table), inside OpenFlow 1.3's physical ports.
PORT_MIN, PORT_MAX = 1, 65279
TAG = "openflow"
SERVICE = "openflow"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,63}\Z")
_HEX16 = re.compile(r"[0-9a-fA-F]{16}\Z")


class Refused(ValueError):
    """The values could not be read or are not of their shape, naming which."""


def _addr(value) -> str:
    """The address of a NetBox ``address`` (``192.0.2.5/24``) or a bare one, or ``""``."""
    text = str((value or {}).get("address") if isinstance(value, dict) else value or "")
    try:
        return str(ipaddress.ip_interface(text).ip) if text else ""
    except ValueError:
        return ""


def _slugs(obj: dict) -> set:
    return {str(t.get("slug") or t.get("name") or "").lower() for t in obj.get("tags") or []}


def _service_parent(svc: dict) -> str:
    """The service's device name (NetBox before 4.3: ``device``; after: ``parent``)."""
    parent = svc.get("device") or svc.get("virtual_machine") or svc.get("parent") or {}
    return str(parent.get("name") or parent.get("display") or "")


def from_netbox(device: dict, interfaces: list, services: list, controllers: dict) -> dict:
    """The values from NetBox records already fetched (the seam tests use): *device* (with its
    ``config_context`` and ``custom_fields``), its *interfaces* (each with ``tags``,
    ``untagged_vlan`` and ``ip_addresses``), the *services* named ``openflow``, and
    *controllers* (``{device name: its record}``, for a Service with no address of its own).
    ``{"ok", "values", "defaults", "error"}``; a value of the wrong shape is refused, named."""
    ctx = (device.get("config_context") or {}).get("openflow") or {}
    cf = device.get("custom_fields") or {}
    v, defaults, bad = {"switch.name": device.get("name", "")}, [], []

    v["switch.address"] = _addr(device.get("primary_ip4")) or _addr(device.get("primary_ip6"))

    chosen = services
    if len(services) > 1:
        want = str(ctx.get("controller") or "")
        chosen = [s for s in services if _service_parent(s) == want]
        if not want or len(chosen) != 1:
            return {"ok": False, "values": {}, "defaults": [], "error": (
                f"NetBox holds {len(services)} 'openflow' Services "
                f"({', '.join(sorted(_service_parent(s) for s in services))}), and the config "
                f"context's openflow.controller names {want or 'none'}: name one")}
    if chosen:
        svc = chosen[0]
        ports = svc.get("ports") or []
        v["controller.port"] = str(ports[0]) if ports else ""
        own = [_addr(a) for a in svc.get("ipaddresses") or [] if _addr(a)]
        parent = controllers.get(_service_parent(svc)) or {}
        v["controller.address"] = (own[0] if own else _addr(parent.get("primary_ip4"))
                                   or _addr(parent.get("primary_ip6")))
        v["controller.name"] = _service_parent(svc)
        proto = str(((svc.get("protocol") or {}).get("value")
                     if isinstance(svc.get("protocol"), dict) else svc.get("protocol")) or "")
        if proto and proto.lower() != "tcp":
            bad.append(f"the 'openflow' Service's protocol is {proto}, and OpenFlow is TCP")

    for key, default in (("version", "1.3"), ("transport", "tcp"), ("fail_mode", "secure")):
        given = ctx.get(key)
        if given in (None, ""):
            defaults.append(f"openflow.{key} {default} (no openflow.{key} in the config context)")
            given = default
        v[f"openflow.{key}"] = str(given)
    v["openflow.instance"] = str(cf.get("openflow_instance") or ctx.get("instance") or "")
    # The Mercury controller connection a switch's appearance is verified against, when the
    # network has more than one (SDN › Controllers' name).
    v["openflow.connection"] = str(ctx.get("connection") or "")
    v["openflow.datapath_id"] = str(cf.get("openflow_datapath_id") or "").lower()

    tagged = [i for i in interfaces or [] if TAG in _slugs(i)]
    # The management interface is never an OpenFlow port (Lab 9's management network is
    # separate and non-OpenFlow, the operator, 2026-11-05), tagged or not, and is said by name.
    excluded = [(str(i.get("name") or ""), management_reason(device, i)) for i in tagged
                if management_reason(device, i)]
    of_ifaces = [i for i in tagged if not management_reason(device, i)]
    v["excluded"] = [f"{name} is the management interface ({why}): excluded from OpenFlow"
                     for name, why in excluded]
    if tagged and not of_ifaces:
        bad.append("every interface tagged openflow is a management interface ("
                   + "; ".join(f"{n}: {w}" for n, w in excluded)
                   + "), and the management network is never OpenFlow: tag the OpenFlow ports")
    v["ports"] = [str(i.get("name") or "") for i in of_ifaces]
    # Each OpenFlow port's number as NetBox holds it (C2603); a port without one is absent
    # here, and the render refuses it where the platform numbers ports by add order.
    v["port.openflow_port"] = {
        str(i.get("name") or ""): str((i.get("custom_fields") or {}).get("openflow_port"))
        for i in of_ifaces
        if (i.get("custom_fields") or {}).get("openflow_port") not in (None, "")}
    vlans ={(i.get("untagged_vlan") or {}).get("vid") for i in of_ifaces}
    v["openflow.vlan"] = str(vlans.pop()) if len(vlans) == 1 and None not in vlans else ""
    if len({(i.get("untagged_vlan") or {}).get("vid") for i in of_ifaces}) > 1:
        bad.append("the interfaces tagged openflow are on more than one untagged VLAN: "
                   + ", ".join(sorted(str((i.get("untagged_vlan") or {}).get("vid"))
                                      for i in of_ifaces)))
    v["mgmt.vlan"] = _mgmt_vlan(device, interfaces)
    if v["openflow.vlan"] and v["openflow.vlan"] == v["mgmt.vlan"]:
        bad.append(f"the OpenFlow VLAN {v['openflow.vlan']} is the management VLAN "
                   f"{v['mgmt.vlan']}, and the management network is never OpenFlow")

    bad += _shape_problems(v)
    if bad:
        return {"ok": False, "values": v, "defaults": defaults, "error": "; ".join(bad)}
    return {"ok": True, "values": v, "defaults": defaults, "error": ""}


def management_reason(device: dict, iface: dict) -> str:
    """Why *iface* is *device*'s management interface, or ``""``: NetBox marks it
    ``mgmt_only``, or it holds the device's primary IP (IPv4 or IPv6), or its OOB IP
    (``oob_ip``, NetBox 4)."""
    held = {_addr(a) for a in iface.get("ip_addresses") or []} - {""}
    if iface.get("mgmt_only"):
        return "mgmt_only"
    for key, words in (("primary_ip4", "primary IP"), ("primary_ip6", "primary IP"),
                       ("oob_ip", "OOB IP")):
        if _addr(device.get(key)) and _addr(device.get(key)) in held:
            return words
    return ""


def _mgmt_vlan(device: dict, interfaces: list) -> str:
    """The management VLAN: of the interface holding the primary IP, else of any other
    management interface (`management_reason`)."""
    primary = _addr(device.get("primary_ip4")) or _addr(device.get("primary_ip6"))
    ranked = sorted(interfaces or [], key=lambda i: primary not in {
        _addr(a) for a in i.get("ip_addresses") or []})
    for i in ranked:
        if not management_reason(device, i):
            continue
        vid = (i.get("untagged_vlan") or {}).get("vid")
        if vid:
            return str(vid)
        m = re.fullmatch(r"(?i)vlan[ -]?([0-9]{1,4})", str(i.get("name") or ""))
        if m:
            return m.group(1)
    return ""


def _shape_problems(v: dict) -> list:
    bad = []
    for key in ("switch.address", "controller.address"):
        if v.get(key):
            try:
                ipaddress.ip_address(v[key])
            except ValueError:
                bad.append(f"{key} {v[key]!r} is not an address")
    port = v.get("controller.port")
    if port and not (port.isdigit() and 1 <= int(port) <= 65535):
        bad.append(f"controller.port {port!r} is not 1 to 65535")
    for key in ("openflow.vlan", "mgmt.vlan"):
        if v.get(key) and not (v[key].isdigit() and 1 <= int(v[key]) <= 4094):
            bad.append(f"{key} {v[key]!r} is not a VLAN 1 to 4094")
    dpid = v.get("openflow.datapath_id")
    if dpid and (not _HEX16.match(dpid) or set(dpid) == {"0"}):
        bad.append(f"openflow.datapath_id {dpid!r} is not 16 hex digits, not all zero")
    for key in ("openflow.instance",):
        if v.get(key) and not NAME.match(v[key]):
            bad.append(f"{key} {v[key]!r} is not one name token")
    for p in v.get("ports") or []:
        if not NAME.match(p):
            bad.append(f"the OpenFlow port {p!r} is not one interface-name token")
    numbers = v.get("port.openflow_port") or {}
    for p, n in sorted(numbers.items()):
        if not (n.isdigit() and PORT_MIN <= int(n) <= PORT_MAX):
            bad.append(f"{p}'s openflow_port {n!r} is not {PORT_MIN} to {PORT_MAX}")
    by_number: dict = {}
    for p, n in numbers.items():
        by_number.setdefault(n, []).append(p)
    for n, ports in sorted(by_number.items()):
        if len(ports) > 1:
            bad.append(f"openflow_port {n} is given to {', '.join(sorted(ports))}: one number "
                       "names one port")
    if v.get("openflow.version") not in ("1.0", "1.3"):
        bad.append(f"openflow.version {v.get('openflow.version')!r} is not 1.0 or 1.3")
    if v.get("openflow.transport") not in ("tcp", "tls"):
        bad.append(f"openflow.transport {v.get('openflow.transport')!r} is not tcp or tls")
    if v.get("openflow.fail_mode") not in ("secure", "standalone"):
        bad.append(f"openflow.fail_mode {v.get('openflow.fail_mode')!r} is not secure or "
                   "standalone")
    return bad


def from_export(export: dict, device_name: str) -> dict:
    """*device_name*'s values from a committed NSOT export (`modules/nsot/export.py`'s document),
    with no NetBox read: the export's records put back in NetBox's shapes and read by
    `from_netbox`, so both read one way. ``{"ok", "values", "defaults", "error"}``; the values
    carry the export's hash (``nsot.export_sha256``)."""
    from modules.nsot import export as X

    dev = X.device(export, device_name)
    if dev is None:
        return {"ok": False, "values": {}, "defaults": [],
                "error": f"the NSOT export ({str(export.get('sha256'))[:12]}) holds no device "
                         f"{device_name!r}"}

    def addr(text):
        return {"address": text} if text else None

    def tags(obj):
        return [{"slug": t} for t in obj.get("tags") or []]

    device = dict(dev, primary_ip4=addr(dev.get("primary_ip4")),
                  primary_ip6=addr(dev.get("primary_ip6")), oob_ip=addr(dev.get("oob_ip")),
                  tags=tags(dev))
    interfaces = [dict(i, tags=tags(i),
                       untagged_vlan={"vid": i["untagged_vlan"]}
                       if i.get("untagged_vlan") is not None else None,
                       ip_addresses=[{"address": a} for a in i.get("ip_addresses") or []])
                  for i in X.interfaces_of(export, device_name)]
    services = [dict(s, device={"name": s.get("parent", "")},
                     ipaddresses=[{"address": a} for a in s.get("ipaddresses") or []])
                for s in X.services_named(export, SERVICE)]
    controllers = {}
    for s in services:
        parent = X.device(export, s["parent"]) or {}
        controllers[s["parent"]] = {"primary_ip4": addr(parent.get("primary_ip4")),
                                    "primary_ip6": addr(parent.get("primary_ip6"))}
    got = from_netbox(device, interfaces, services, controllers)
    got["values"]["nsot.export_sha256"] = str(export.get("sha256") or "")
    return got


def read(device_name: str) -> dict:
    """*device_name*'s values from NetBox, through Mercury's NetBox client (reads only):
    `from_netbox`'s answer, or ``{"ok": False, "error"}`` naming what could not be read."""
    from modules.netbox_client import _nb_get, _nb_ready
    from modules.nsot.context import _fetch_full_device, _fetch_interfaces

    ok, err, session, base = _nb_ready()
    if not ok:
        return {"ok": False, "values": {}, "defaults": [], "error": f"NetBox: {err}"}
    try:
        device = _fetch_full_device(session, base, device_name)
        if not device:
            return {"ok": False, "values": {}, "defaults": [],
                    "error": f"NetBox holds no device {device_name!r}"}
        interfaces = _fetch_interfaces(session, base, device["id"])
        services = _nb_get(session, base, "ipam/services/", name=SERVICE)
        controllers = {}
        for s in services:
            parent = _service_parent(s)
            if parent and parent not in controllers:
                got = _nb_get(session, base, "dcim/devices/", name=parent)
                controllers[parent] = got[0] if got else {}
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.warning("openflow_values: NetBox read failed for %s: %s", device_name, exc)
        return {"ok": False, "values": {}, "defaults": [],
                "error": f"NetBox could not be read: {type(exc).__name__}: {exc}"[:300]}
    return from_netbox(device, interfaces, services, controllers)
