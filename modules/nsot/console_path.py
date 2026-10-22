"""nsot/console_path.py — a device's console path in NetBox: read it, and create it behind the
write gate (O4 of out-of-band ZTP, docs/LAB9_PLAN.md section 8, architecture piece 1).

NetBox's console model is the source of truth for WHICH console-server port a device's console
is cabled to: the device's console port, a cable, and the console server's port on the far end.
How Mercury reaches that port (driver, host, credential reference) is Mercury's own store,
keyed by the console-server port's NetBox id (`modules/nsot/console_servers.py`), never a
NetBox custom field.

**The read** (`read_console_path`) asks three things and says which one came back empty:

1. ``dcim/console-ports/?device_id=<id>``: the device's console ports, paged until NetBox's
   ``count`` is reached (a read returning exactly its page size with no more pages and no count
   is TRUNCATED, never complete; one that falls short of its count is unreadable);
2. each port's ``cable`` (its brief: the id), and the cable by id (``dcim/cables/<id>/``);
3. the cable's far end: exactly one termination, a console-server port, with its device.

The shapes it relies on are the measured ones (tests/fixtures/netbox/console_shapes.json,
NetBox 4.6.9, 2026-10-22): a port's ``cable`` brief and a cable's terminations with their
``object`` brief. A read that fails is ``unreadable`` with its reason, never "no path": an
absence is a finding only when the store that would hold it answered.

**The create** (`ensure_console_path`) makes what is missing of: the device's console port,
the console-server port on a NAMED console-server device that already exists, and the cable
between them. Every write goes through `netbox_client`'s chokepoints, so each object is tagged
``nmas-managed`` and recorded as created for the network (`netbox_guard`). It is idempotent: a
second call finds the path and creates nothing. It never re-cables: a port already cabled
elsewhere refuses, naming both cables. It refuses before reading anything when the master
switch is off, or the authority declared is not this operation's (`AUTHORITY`), naming both.
A preview (`plan_console_path`) runs the same code in a dry run and returns the plan and its
hash, which the confirm is bound to (O6).

**The removal** (`remove_console_path`) deletes the cable and the device's console port, each
only when tagged AND recorded as created (anything else is skipped and named). The console
server's port is kept: Mercury's console-server store is keyed by its id, and the port belongs
to the console server, which serves the next device.
"""

import logging
from urllib.parse import urlencode

log = logging.getLogger(__name__)

#: THE WRITE AUTHORITY this operation's NetBox writes stand on (C155's `for_list(authority=)`):
#: a declared authority must name it, as `authority_for` builds it. Any other authority (an
#: import's confirmation, a Verify) is refused here: these writes stand on the console path's
#: own confirmation and nothing else.
AUTHORITY = "console path"

#: Objects per page of a list read (NetBox's own default page is 50).
PAGE_SIZE = 50
#: The most pages one list read follows before it says it could not finish.
MAX_PAGES = 1000

CONSOLE_PORT = "dcim.consoleport"
SERVER_PORT = "dcim.consoleserverport"
EP_PORTS = "dcim/console-ports"
EP_SERVER_PORTS = "dcim/console-server-ports"
EP_CABLES = "dcim/cables"
EP_DEVICES = "dcim/devices"

#: NetBox's longest component name.
NAME_MAX = 64


def authority_for(hostname: str, actor: str, plan_hash: str = "") -> str:
    """The declared authority for one console path's writes: this operation's name, the device,
    who confirmed it, and the plan's hash when the confirm is bound to one."""
    text = f"{AUTHORITY} for {hostname}, confirmed by {actor or 'unknown'}"
    return f"{text} (plan {plan_hash[:12]})" if plan_hash else text


def _query(endpoint: str, params: dict) -> str:
    return f"{endpoint}/?{urlencode(params)}" if params else f"{endpoint}/"


def _list(session, base: str, endpoint: str, **params) -> tuple:
    """``(rows, error)``: every object a list read matches, paged by ``limit``/``offset`` and
    NetBox's ``next`` link until its ``count`` is reached. *error* names the query and why it
    could not be finished; *rows* is then None (never a partial list read as whole)."""
    what = _query(endpoint, params)
    url = f"{base}/api/{endpoint}/"
    query = dict(params, limit=PAGE_SIZE, offset=0)
    rows, count, page = [], None, []
    for _ in range(MAX_PAGES):
        try:
            r = session.get(url, params=query, timeout=15)
        except Exception as exc:                        # noqa: BLE001 - said, never raised
            return None, f"{what} could not be read: {type(exc).__name__}: {exc}"
        if not r.ok:
            return None, f"{what} answered HTTP {r.status_code}"
        try:
            data = r.json()
        except ValueError as exc:
            return None, f"{what}: NetBox's answer was not JSON ({exc})"
        page = data.get("results") or []
        rows.extend(page)
        count = data.get("count")
        url, query = data.get("next"), None
        if not url:
            break
    else:
        return None, f"{what} still had more pages after {MAX_PAGES}"
    if count is None:
        if len(page) >= PAGE_SIZE:
            return None, (f"{what} returned a full page of {PAGE_SIZE} with no count and no "
                          "next page: the read is truncated")
    elif len(rows) != count:
        return None, f"{what} returned {len(rows)} of the {count} NetBox counts: truncated"
    return rows, ""


def _ref_id(ref):
    """The id a brief (or a bare id) names, or None."""
    value = ref.get("id") if isinstance(ref, dict) else ref
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _far_end(cable: dict, port_id: int) -> tuple:
    """``(terminations, "")`` at the end of *cable* away from console port *port_id*, or
    ``(None, why)`` when the port is on neither end."""
    for mine, far in (("a_terminations", "b_terminations"), ("b_terminations", "a_terminations")):
        for t in cable.get(mine) or []:
            if t.get("object_type") == CONSOLE_PORT and t.get("object_id") == port_id:
                return list(cable.get(far) or []), ""
    return None, f"cable {cable.get('id')} does not terminate on console port {port_id}"


def _brief(obj) -> dict:
    obj = obj if isinstance(obj, dict) else {}
    return {"id": obj.get("id"), "name": obj.get("name") or obj.get("display") or ""}


def _status(value) -> str:
    return value.get("value", "") if isinstance(value, dict) else (value or "")


def _one_path(session, base: str, port: dict) -> tuple:
    """``(path, gap, error)`` for one console port: exactly one of them is set. *error* is a
    read that failed (the whole answer is then unreadable)."""
    from modules.netbox_client import _nb_read_by_id

    mine = _brief(port)
    cable_id = _ref_id(port.get("cable"))
    if cable_id is None:
        return None, {"console_port": mine,
                      "why": f"console port {mine['name']!r} (id {mine['id']}) has no cable"}, ""
    state, cable = _nb_read_by_id(session, base, EP_CABLES, cable_id)
    if state == "gone":
        return None, {"console_port": mine,
                      "why": f"{EP_CABLES}/{cable_id}/ answered 404: the cable console port "
                             f"{mine['name']!r} names is not there"}, ""
    if state != "ok":
        return None, None, f"{EP_CABLES}/{cable_id}/: {cable}"
    far, why = _far_end(cable, mine["id"])
    if far is None:
        return None, {"console_port": mine, "why": why}, ""
    kinds = sorted({t.get("object_type") or "?" for t in far})
    if len(far) != 1 or kinds != [SERVER_PORT]:
        return None, {"console_port": mine,
                      "why": (f"cable {cable_id}'s far end is {len(far)} termination(s) of "
                              f"{', '.join(kinds) or 'nothing'}, not one console-server port: "
                              "a path through patch panels is not read (C1536)")}, ""
    peer = far[0].get("object") or {}
    server = peer.get("device") if isinstance(peer.get("device"), dict) else {}
    if not peer or not server:
        return None, {"console_port": mine,
                      "why": (f"cable {cable_id}'s far end (console-server port "
                              f"{far[0].get('object_id')}) came without its port or device")}, ""
    return {"console_port": mine,
            "cable": {"id": cable_id, "label": cable.get("label") or "",
                      "status": _status(cable.get("status"))},
            "server_port": _brief(peer), "server": _brief(server)}, None, ""


def _ready(session, base):
    if session is not None:
        return session, base, ""
    from modules.netbox_client import _nb_ready

    ok, err, session, base = _nb_ready()
    return (session, base, "") if ok else (None, "", f"NetBox is not reachable: {err}")


def _bad_id(value) -> bool:
    return not isinstance(value, int) or isinstance(value, bool) or value <= 0


def read_console_path(device_id: int, *, session=None, base: str = "") -> dict:
    """NetBox device *device_id*'s console path. ``{"ok", "state", "device_id", "paths",
    "gaps", "why", "error"}``: *state* is ``path`` (at least one complete path), ``no_path``
    (every lookup answered; *why* names the one that came back empty or what each port lacks),
    or ``unreadable`` (``ok`` false; *error* names the read that failed). Each path is
    ``{console_port, cable, server_port, server}``, each part its id and name."""
    out = {"ok": False, "state": "unreadable", "device_id": device_id, "paths": [], "gaps": [],
           "why": "", "error": ""}
    if _bad_id(device_id):
        return dict(out, error=f"a NetBox device id is a positive number, not {device_id!r}")
    session, base, err = _ready(session, base)
    if err:
        return dict(out, error=err)
    query = {"device_id": device_id}
    ports, err = _list(session, base, EP_PORTS, **query)
    if err:
        return dict(out, error=err)
    if not ports:
        return dict(out, ok=True, state="no_path",
                    why=(f"{_query(EP_PORTS, query)} returned nothing: NetBox holds no console "
                         "port on this device"))
    for port in ports:
        path, gap, err = _one_path(session, base, port)
        if err:
            return dict(out, paths=[], gaps=[], error=err)
        if path:
            out["paths"].append(path)
        else:
            out["gaps"].append(gap)
    if out["paths"]:
        return dict(out, ok=True, state="path")
    return dict(out, ok=True, state="no_path",
                why="; ".join(g["why"] for g in out["gaps"]))


# ── the create ──────────────────────────────────────────────────────────────────────────────

def refusal(list_name: str, authority: str) -> str:
    """Why a real write of a console path must not start, or "": the network it is recorded
    under, the master switch and the declared authority. The switch and the authority are named
    TOGETHER, whichever refused: both are needed, and each says what it holds."""
    from modules import netbox_guard

    if netbox_guard.is_dry_run():
        return ""                                       # a preview writes nothing
    if not (list_name or "").strip():
        return ("Not written: no network was named, and the created-object record is kept per "
                "network, so an object created without one could never be removed by Mercury.")
    switch = netbox_guard.writes_allowed()
    declared = (authority or "").strip()
    ours = declared == AUTHORITY or declared.startswith(AUTHORITY + " ")
    if switch and ours:
        return ""
    held = repr(declared) if declared else "none"
    if not ours:
        held += ", not this operation's"
    return (f"Not written: NetBox writes are {'on' if switch else 'OFF'} (the master switch, "
            "Writes allowed, on Settings › Installation › Connections) and the authority "
            f"declared is {held} ({AUTHORITY!r}, as `authority_for` builds it). A console path "
            "is written only with the switch on AND its own confirmation declared.")


def _names(**names) -> str:
    for label, value in names.items():
        text = value if isinstance(value, str) else ""
        if not text.strip():
            return f"the {label.replace('_', ' ')} is empty"
        if len(text) > NAME_MAX or text != text.strip() or any(ord(c) < 32 for c in text):
            return (f"the {label.replace('_', ' ')} {text!r} is not a NetBox name (1 to "
                    f"{NAME_MAX} printable characters, no leading or trailing space)")
    return ""


def _find(session, base: str, endpoint: str, **params) -> list:
    """A get-or-create lookup through `netbox_client._nb_get` (a dry run's own planned objects
    found too, so a preview plans what the real run makes)."""
    from modules.netbox_client import _nb_get

    return _nb_get(session, base, f"{endpoint}/", **params)


def _ensure(session, base, device_id, port_name, server_name, server_port_name, created) -> dict:
    """The create's body, inside the caller's guard context. Raises on a failed write (the
    caller says it, with what was created before it)."""
    from modules import netbox_guard
    from modules.netbox_client import _nb_post, _nb_read_by_id

    state, device = _nb_read_by_id(session, base, EP_DEVICES, device_id)
    if state == "gone":
        return {"ok": False, "error": f"{EP_DEVICES}/{device_id}/ answered 404: no such device"}
    if state != "ok":
        return {"ok": False, "error": f"{EP_DEVICES}/{device_id}/: {device}"}
    servers = _find(session, base, EP_DEVICES, name=server_name)
    if len(servers) != 1:
        what = ("returned nothing: Mercury does not create a console server's device"
                if not servers else f"returned {len(servers)} devices, not one")
        return {"ok": False, "error": f"{_query(EP_DEVICES, {'name': server_name})} {what}"}
    server = servers[0]
    if server.get("id") == device_id:
        return {"ok": False, "error": (f"the console server {server_name!r} is the device "
                                       f"itself (NetBox id {device_id})")}
    ports = _find(session, base, EP_PORTS, device_id=device_id, name=port_name)
    sports = _find(session, base, EP_SERVER_PORTS, device_id=server["id"], name=server_port_name)
    port, sport = (ports[0] if ports else None), (sports[0] if sports else None)
    cable_a = _ref_id((port or {}).get("cable"))
    cable_b = _ref_id((sport or {}).get("cable"))
    if (cable_a or cable_b) and cable_a != cable_b:
        held = []
        if cable_a:
            held.append(f"console port {port_name!r} is on cable {cable_a}")
        if cable_b:
            held.append(f"{server_name} port {server_port_name!r} is on cable {cable_b}")
        return {"ok": False, "error": ("Not cabled: " + " and ".join(held) + "; Mercury never "
                                       "re-cables a port. Remove that cable first.")}
    hostname = device.get("name") or f"device {device_id}"
    existing = []
    if port is None:
        port = _nb_post(session, base, f"{EP_PORTS}/", {"device": device_id, "name": port_name})
        created.append({"endpoint": EP_PORTS, "id": port.get("id"), "name": port_name})
    else:
        existing.append({"endpoint": EP_PORTS, "id": port.get("id"), "name": port_name})
    if sport is None:
        sport = _nb_post(session, base, f"{EP_SERVER_PORTS}/",
                         {"device": server["id"], "name": server_port_name})
        created.append({"endpoint": EP_SERVER_PORTS, "id": sport.get("id"),
                        "name": server_port_name})
    else:
        existing.append({"endpoint": EP_SERVER_PORTS, "id": sport.get("id"),
                         "name": server_port_name})
    if cable_a:
        existing.append({"endpoint": EP_CABLES, "id": cable_a, "name": ""})
        cable_id = cable_a
    else:
        label = f"{hostname} {port_name} to {server_name} {server_port_name}"[:100]
        cable = _nb_post(session, base, f"{EP_CABLES}/", {
            "a_terminations": [{"object_type": CONSOLE_PORT, "object_id": port.get("id")}],
            "b_terminations": [{"object_type": SERVER_PORT, "object_id": sport.get("id")}],
            "status": "connected", "label": label})
        created.append({"endpoint": EP_CABLES, "id": cable.get("id"), "name": label})
        cable_id = cable.get("id")
    return {"ok": True, "error": "", "dry_run": netbox_guard.is_dry_run(),
            "console_port": {"id": port.get("id"), "name": port_name},
            "server_port": {"id": sport.get("id"), "name": server_port_name},
            "server": {"id": server["id"], "name": server_name}, "cable": {"id": cable_id},
            "existing": existing}


def ensure_console_path(list_name: str, device_id: int, *, port_name: str, server_name: str,
                        server_port_name: str, actor: str, authority: str,
                        session=None, base: str = "") -> dict:
    """Create what is missing of NetBox device *device_id*'s console path to port
    *server_port_name* of the console server *server_name* (an existing NetBox device), its own
    console port named *port_name*. ``{"ok", "error", "refused", "created", "existing",
    "console_port", "server_port", "server", "cable", "path"}``: *created* lists each object
    made (endpoint, id, name), *existing* each found; after a real create *path* is the path
    read back (`read_console_path`), and a path that does not read back is not ok.

    Refused before anything is read (*refused* true) when the network is unnamed, the master
    switch is off or the authority is not this operation's (`refusal`), and when another
    writer holds the network's NetBox objects. In a dry run (`plan_console_path`) nothing is
    written and no authority is needed."""
    from modules import netbox_guard

    out = {"ok": False, "error": "", "refused": False, "created": [], "existing": []}
    if _bad_id(device_id):
        return dict(out, error=f"a NetBox device id is a positive number, not {device_id!r}")
    bad = _names(port_name=port_name, server_name=server_name, server_port_name=server_port_name)
    if bad:
        return dict(out, error=f"Not written: {bad}.")
    why = refusal(list_name, authority)
    if why:
        return dict(out, refused=True, error=why)
    session, base, err = _ready(session, base)
    if err:
        return dict(out, error=err)
    dry = netbox_guard.is_dry_run()
    created = out["created"]
    try:
        if dry:
            with netbox_guard.for_list(list_name, actor=actor, authority=authority):
                got = _ensure(session, base, device_id, port_name, server_name,
                              server_port_name, created)
        else:
            with netbox_guard.list_writer(list_name, f"the console path of device {device_id}",
                                          actor), \
                    netbox_guard.for_list(list_name, actor=actor, authority=authority):
                got = _ensure(session, base, device_id, port_name, server_name,
                              server_port_name, created)
    except netbox_guard.NetBoxBusy as exc:
        return dict(out, refused=True, error=f"Not written: {exc}. Nothing was created.")
    except Exception as exc:                            # noqa: BLE001 - said with what landed
        log.warning("console path: device %s: %s", device_id, exc)
        made = ", ".join(f"{c['endpoint']} {c['id']}" for c in created) or "nothing"
        return dict(out, error=f"{type(exc).__name__}: {exc} (created before it: {made})")
    out.update(got)
    out["created"] = created
    if not got.get("ok") or dry:
        return out
    path = read_console_path(device_id, session=session, base=base)
    out["path"] = path
    if not any(p["console_port"]["id"] == got["console_port"]["id"]
               and p["server_port"]["id"] == got["server_port"]["id"]
               for p in path.get("paths") or []):
        out.update(ok=False, error=("the console path was written and did not read back: "
                                    + (path.get("error") or path.get("why") or "no path")))
    return out


def plan_console_path(list_name: str, device_id: int, *, port_name: str, server_name: str,
                      server_port_name: str, actor: str = "", session=None,
                      base: str = "") -> dict:
    """The preview: `ensure_console_path` in a dry run. ``{"ok", "error", "plan", "hash",
    "changes_nothing", ...}``: *plan* is the dry run's creates (nothing is written), *hash*
    the plan's (`netbox_authz.compute_plan_hash`), which the confirm is bound to."""
    from modules import netbox_authz, netbox_guard

    with netbox_guard.dry_run() as plan:
        got = ensure_console_path(list_name, device_id, port_name=port_name,
                                  server_name=server_name, server_port_name=server_port_name,
                                  actor=actor, authority="", session=session, base=base)
    summary = plan.summary()
    return dict(got, plan=summary, hash=netbox_authz.compute_plan_hash(summary),
                changes_nothing=bool(got.get("ok")) and not summary["create_count"])


# ── the removal ─────────────────────────────────────────────────────────────────────────────

def _ours(session, base, list_name: str, endpoint: str, obj_id) -> tuple:
    """``(obj, why_not)``: *obj* when NetBox holds it tagged ``nmas-managed`` AND the network's
    created record holds it; else None and why (both tests named)."""
    from modules import netbox_guard
    from modules.netbox_client import _nb_read_by_id

    state, obj = _nb_read_by_id(session, base, endpoint, obj_id)
    if state != "ok":
        return None, f"{endpoint}/{obj_id}/ is {state}" + (f": {obj}" if obj else "")
    tagged = netbox_guard.has_managed_tag(obj)
    recorded = netbox_guard.was_created_by_nmas(list_name, endpoint, obj_id)
    if tagged and recorded:
        return obj, ""
    return None, (f"{endpoint} {obj_id} is {'' if tagged else 'not '}tagged nmas-managed and "
                  f"{'' if recorded else 'not '}recorded as created for this network: kept")


def remove_console_path(list_name: str, device_id: int, *, port_name: str, actor: str,
                        authority: str, session=None, base: str = "") -> dict:
    """Delete the device's console port *port_name* and its cable, each only when Mercury
    created it (tagged AND recorded); the console server's port is kept (the module's note).
    ``{"ok", "error", "refused", "deleted", "skipped"}``: *skipped* names each object kept and
    why. Refused as the create is (`refusal`)."""
    from modules import netbox_guard
    from modules.netbox_client import _nb_delete, last_delete_failure

    out = {"ok": False, "error": "", "refused": False, "deleted": [], "skipped": []}
    if _bad_id(device_id):
        return dict(out, error=f"a NetBox device id is a positive number, not {device_id!r}")
    bad = _names(port_name=port_name)
    if bad:
        return dict(out, error=f"Not removed: {bad}.")
    why = refusal(list_name, authority)
    if why:
        return dict(out, refused=True, error=why.replace("Not written", "Not removed"))
    session, base, err = _ready(session, base)
    if err:
        return dict(out, error=err)

    def _drop(endpoint, obj_id):
        obj, why_not = _ours(session, base, list_name, endpoint, obj_id)
        if obj is None:
            out["skipped"].append({"endpoint": endpoint, "id": obj_id, "why": why_not})
            return False
        if _nb_delete(session, base, f"{endpoint}/", obj_id):
            out["deleted"].append({"endpoint": endpoint, "id": obj_id})
            return True
        out["skipped"].append({"endpoint": endpoint, "id": obj_id,
                               "why": f"NetBox refused the delete: {last_delete_failure()}"})
        return False

    try:
        with netbox_guard.list_writer(list_name, f"removing the console path of device "
                                                 f"{device_id}", actor), \
                netbox_guard.for_list(list_name, actor=actor, authority=authority):
            ports = _find(session, base, EP_PORTS, device_id=device_id, name=port_name)
            for port in ports:
                cable_id = _ref_id(port.get("cable"))
                if cable_id is not None and not _drop(EP_CABLES, cable_id):
                    out["skipped"].append({"endpoint": EP_PORTS, "id": port.get("id"),
                                           "why": f"its cable {cable_id} was kept"})
                    continue
                _drop(EP_PORTS, port.get("id"))
    except netbox_guard.NetBoxBusy as exc:
        return dict(out, refused=True, error=f"Not removed: {exc}. Nothing was deleted.")
    except Exception as exc:                            # noqa: BLE001 - said with what landed
        log.warning("console path removal: device %s: %s", device_id, exc)
        return dict(out, error=f"{type(exc).__name__}: {exc}")
    out["ok"] = not out["skipped"]
    if out["skipped"]:
        out["error"] = "; ".join(s["why"] for s in out["skipped"])
    return out
