"""The OpenFlow configuration of an Open vSwitch server, NSoT-driven (docs/LAB9_OPENFLOW.md,
section 2; the operator's decision 7, 2026-11-05: OVS first).

One operation, its stages in order (`STEPS`):

1. **values**: the server's OpenFlow values from the network's committed NSOT export
   (`openflow_config.values_from_export`, C2777): NetBox's state as committed, offline, its
   SHA-256 in the plan's hash; no committed export refuses, naming the NSOT export card on SDN ›
   Apps. A missing or ill-shaped value refuses, named, with nothing read from the server.
2. **render**: the `ovs` template (`openflow_templates.render`), one `sudo -n ovs-vsctl`
   transaction.
3. **read before**: the bridge as it is now, by the OVS reads only (`modules/sdn/ovs.py`): the
   bridges, and for this bridge its controller targets, fail mode, protocols, datapath-id
   override and ports. From it the **undo**, one transaction putting back exactly what this one
   changes (the bridge deleted if it did not exist).
4. **hash** (`openflow_config.plan_hash`) over the network, the server, the template, the
   program, the undo, the before and the NSOT export's SHA-256.
   The preview draws the program, the undo, the values with where each came from, and the
   template's status.
5. **apply** (`apply`): refused unless the template is CONFIRMED on this network
   (`openflow_templates.push_refusal`); planned again and the hash compared (a moved bridge or
   NetBox value is refused, naming both hashes; nothing is sent); the server **held**
   (`device_ops.hold`, across processes) while the transaction is sent.
6. **verify**: the bridge read back (controller target, protocols, fail mode, ports, datapath id
   override), then the **controller's switch list** (`openflow_config.seen_by_controller`,
   shared with the vendor switches': `ControllerDriver.switches` of the Mercury connection named
   by the config context's ``openflow.connection``, or the network's only one, read up to
   `VERIFY_READS` times `VERIFY_PAUSE` apart until the bridge's datapath id is in it).
7. **rollback**: on a failed send or a failed check, the undo is sent and the bridge read again.
8. **record**: the operation's whole run in the network's SDN operation record
   (`openflow_config.record`, ``response.kind`` ``openflow_config``), which History reads.

**A bridge already as intended** (the operator, 2026-11-10: a result says "already as intended,
nothing sent" where nothing changed): the plan asks Verify's own checks of the bridge
(`bridge_checks`) of the bridge as it is BEFORE; when every one passes, the plan is
``unchanged``, its ``changes`` are empty, and the apply sends no transaction and verifies (the
bridge read back, then the controller's switch list), as a vendor switch's does; a controller
that does not list it ends ``unverified``, with nothing to put back. A check that fails before
is one row of ``changes`` (``{"value", "before", "after"}``), so what the result calls changed
is exactly what Verify will check.

No save: OVSDB persists by itself (ovs-vsctl(8)). Nothing here writes a flow: the controller
does that (LAB9_SDN_GAP, the one controller path).
"""

import json
import logging
import re
import secrets
import time

from modules.sdn import openflow_config
#: The controller's switch list read after the send (`openflow_config.seen_by_controller`).
from modules.sdn.openflow_config import VERIFY_PAUSE, VERIFY_READS  # noqa: F401

log = logging.getLogger(__name__)

TEMPLATE = "ovs"
STEPS = ("values", "render", "read before", "hash", "hold", "send", "verify", "rollback",
         "record")


class Refused(ValueError):
    pass


def _vsctl(*words) -> str:
    return "sudo -n ovs-vsctl " + " ".join(words)


def _lines(text: str) -> list:
    return [x.strip() for x in (text or "").splitlines() if x.strip()]


def _unquote(text: str) -> str:
    t = (text or "").strip()
    return t[1:-1] if len(t) >= 2 and t[0] == t[-1] == '"' else t


def _protocols(text: str) -> list:
    """`get bridge <br> protocols` prints ``["OpenFlow13"]`` or ``[]``."""
    t = (text or "").strip()
    if not (t.startswith("[") and t.endswith("]")):
        return []
    return [_unquote(x) for x in t[1:-1].split(",") if x.strip()]


def _failed(text: str) -> str:
    """ovs-vsctl's or sudo's own words when *text* is a failure, else ``""``."""
    for line in _lines(text):
        if line.startswith(("ovs-vsctl:", "sudo:")):
            return line[:200]
    return ""


def _number(text: str) -> str:
    """`get interface <p> ofport_request` prints ``[]`` (none) or a number; `ofport` a number
    (``-1`` when the port could not be given one)."""
    t = (text or "").strip()
    return t if re.fullmatch(r"-?[0-9]+", t) else ""


def read_bridge(ask, bridge: str, ports=()) -> dict:
    """The bridge as it is, through *ask* (a session's send, given one OVS read whole):
    ``{"exists", "controllers", "fail_mode", "protocols", "datapath_override", "ports",
    "datapath_id", "ofport_request", "ofport", "error"}``. For each of *ports* on the bridge,
    its requested and given OpenFlow port numbers (C2603), ``""`` for none."""
    out = {"exists": False, "controllers": [], "fail_mode": "", "protocols": [],
           "datapath_override": "", "ports": [], "datapath_id": "", "ofport_request": {},
           "ofport": {}, "error": ""}
    got = ask(_vsctl("list-br"))
    if _failed(got):
        out["error"] = _failed(got)
        return out
    out["exists"] = bridge in _lines(got)
    if not out["exists"]:
        return out
    out["controllers"] = _lines(ask(_vsctl("get-controller", bridge)))
    out["fail_mode"] = (_lines(ask(_vsctl("get-fail-mode", bridge))) or [""])[0]
    out["protocols"] = _protocols(ask(_vsctl("get", "bridge", bridge, "protocols")))
    out["datapath_override"] = _unquote(ask(_vsctl("--if-exists", "get", "bridge", bridge,
                                                   "other-config:datapath-id")))
    out["ports"] = _lines(ask(_vsctl("list-ports", bridge)))
    out["datapath_id"] = _unquote(ask(_vsctl("get", "bridge", bridge, "datapath_id")))
    for p in ports:
        if p in out["ports"]:
            out["ofport_request"][p] = _number(ask(_vsctl("get", "interface", p,
                                                          "ofport_request")))
            out["ofport"][p] = _number(ask(_vsctl("get", "interface", p, "ofport")))
    for key in ("controllers", "ports"):
        bad = [x for x in out[key] if x.startswith(("ovs-vsctl:", "sudo:"))]
        if bad:
            out["error"] = bad[0]
    return out


def undo_of(bridge: str, before: dict, values: dict) -> str:
    """One transaction putting back what the program changes, from *before*."""
    if not before.get("exists"):
        return _vsctl("--if-exists", "del-br", bridge)
    parts = []
    parts.append(f"set-controller {bridge} " + " ".join(before["controllers"])
                 if before["controllers"] else f"del-controller {bridge}")
    parts.append(f"set-fail-mode {bridge} {before['fail_mode']}" if before["fail_mode"]
                 else f"del-fail-mode {bridge}")
    parts.append(f"set bridge {bridge} protocols={','.join(before['protocols'])}"
                 if before["protocols"] else f"clear bridge {bridge} protocols")
    if values.get("openflow.datapath_id"):
        parts.append(f"set bridge {bridge} other-config:datapath-id={before['datapath_override']}"
                     if before["datapath_override"]
                     else f"remove bridge {bridge} other-config datapath-id")
    numbers = values.get("port.openflow_port") or {}
    for p in values.get("ports") or []:
        if p not in before["ports"]:
            parts.append(f"--if-exists del-port {bridge} {p}")
        elif p in numbers and (before.get("ofport_request") or {}).get(p, "") != numbers[p]:
            # A port already on the bridge whose number the program requests: its own request
            # put back (C2603), or none.
            old = (before.get("ofport_request") or {}).get(p, "")
            parts.append(f"set interface {p} ofport_request={old}" if old
                         else f"clear interface {p} ofport_request")
    return "sudo -n ovs-vsctl " + " -- ".join(parts)


def _inventory(network: str, device: str):
    from modules.device import load_saved_devices
    from modules.nsot import listref
    for d in load_saved_devices(listref.resolve(network).csv_path):
        if d.get("hostname") == device:
            return d
    return None


def plan(network: str, device: str, *, values=None, session=None) -> dict:
    """The operation for *device*, planned with no write: ``{"ok", "error", "at", "values",
    "defaults", "where", "status", "lines", "program", "undo", "before", "hash",
    "export_sha256"}``. *values* (tests) replaces the committed NSOT export's read; *session*
    (tests) `connection.with_temp_connection`."""
    from modules.sdn import openflow_templates as T
    from modules.sdn import openflow_values as V
    from modules.sdn import ovs

    out = {"ok": False, "error": "", "at": "values", "network": network, "device": device,
           "template": TEMPLATE, "values": {}, "defaults": [], "where": V.WHERE,
           "status": T.status(network, TEMPLATE), "lines": [], "program": [], "undo": "",
           "before": None, "hash": "", "citations": T.load(TEMPLATE)["citations"],
           "excluded": [], "export_sha256": "", "family": "Open vSwitch", "steps": STEPS,
           "unchanged": False, "source": openflow_config.source_of({}), "changes": []}
    dev = _inventory(network, device)
    if dev is None:
        out["error"] = f"{device} is not a device of {network}"
        return out
    if dev.get("device_type") != "ovs_linux":
        out["error"] = (f"{device}'s driver is {dev.get('device_type') or '(none)'}, and an Open "
                        "vSwitch server's is ovs_linux (Settings › Installation › Platforms "
                        "and roles)")
        return out
    got = values if values is not None else openflow_config.values_from_export(network, device)
    out["values"], out["defaults"] = dict(got.get("values") or {}), list(got.get("defaults") or [])
    # The server's management interface, never a bridge port, said by name in the preview.
    out["excluded"] = list(out["values"].get("excluded") or [])
    # C2777: the export the values were read from, in the hash.
    out["export_sha256"] = str(out["values"].get("nsot.export_sha256") or "")
    out["source"] = openflow_config.source_of(got)
    if not got.get("ok"):
        out["error"] = got.get("error") or "the NSOT export's values could not be read"
        return out
    v = out["values"]
    if v.get("openflow.transport") != "tcp":
        out["error"] = (f"the transport is {v.get('openflow.transport')}, and Mercury renders tcp "
                        "only for Open vSwitch: ssl needs the server's private key, certificate "
                        "and CA certificate (ovs-vsctl(8), set-ssl), which Mercury does not "
                        "hold")
        return out
    bad = [x for x in [v.get("openflow.instance")] + list(v.get("ports") or [])
           if x and not ovs.NAME.match(x)]
    if bad:
        out["error"] = (f"{', '.join(map(repr, bad))}: an Open vSwitch bridge or port name is one "
                        "Linux interface name of at most 15 characters")
        return out
    out["at"] = "render"
    r = T.render(TEMPLATE, v)
    if not r["ok"]:
        out["error"] = r["error"]
        return out
    # Every port the bridge takes, each with why (B: none of them protected, C2589).
    out["lines"], out["program"], out["takes"] = r["lines"], r["program"], r["takes"]
    why = ovs.write_refusal(out["program"][0])
    if why:
        out["error"] = f"the rendered transaction is not of its shape: {why}"
        return out
    out["at"] = "read before"
    if session is None:
        from modules.connection import with_temp_connection as session
    bridge = v["openflow.instance"]
    try:
        before = session(dev, lambda conn: read_bridge(
            lambda c: conn.send_command_timing(c, read_timeout=30) or "", bridge,
            ports=list(v.get("ports") or [])))
    except Exception as exc:                          # noqa: BLE001 (that server's failure)
        from modules.utils import error_text
        out["error"] = f"{device} could not be read: {error_text(exc)}"[:300]
        return out
    if before.get("error"):
        out["error"] = f"{device}'s bridge could not be read: {before['error']}"
        return out
    out["before"] = before
    # Verify's own checks, asked of the bridge as it is now: each one that fails is a value
    # this program changes, and none failing is a bridge already as intended.
    out["changes"] = [{"value": c["value"], "before": c["have"], "after": c["want"]}
                      for c in bridge_checks(before, bridge, T.derived(v)) if not c["ok"]]
    out["unchanged"] = not out["changes"]
    out["undo"] = undo_of(bridge, before, v)
    why = ovs.write_refusal(out["undo"])
    if why:
        # A controller target or setting Mercury could not put back (a ptcp: or unix: target,
        # say): refused before anything is sent, never a rollback that cannot run.
        out["error"] = (f"{device}'s bridge {bridge} now holds what Mercury could not put back "
                        f"on a rollback ({json.dumps(before, sort_keys=True)[:200]}): {why}")
        return out
    out["at"] = "hash"
    out["hash"] = openflow_config.plan_hash(network, device, TEMPLATE, out["program"],
                                            out["undo"], before, out["export_sha256"])
    out["ok"] = True
    return out


def _connection_name(network: str, values: dict, given: str = "") -> str:
    try:
        return openflow_config.connection_name(network, values, given)
    except openflow_config.Refused as exc:
        raise Refused(str(exc)) from exc


def bridge_checks(state: dict, bridge: str, values: dict) -> list:
    """What the bridge must read as, each asked of *state* (`read_bridge`'s answer; *values*
    `openflow_templates.derived`'s): ``[{"name", "ok", "words", "value", "have", "want"}]``.
    Verify asks them of the bridge after the send (``name``, ``ok``, ``words``); the plan asks
    the same of the bridge before, and a check that fails there is a value the program changes
    (``value``, from ``have`` to ``want``). One list, so what a result calls changed is what
    Verify checks."""
    def check(name, ok, words, value, have, want):
        return {"name": name, "ok": bool(ok), "words": words, "value": value,
                "have": have or "none", "want": want or "none"}

    want_target = f"tcp:{values.get('controller.host')}:{values.get('controller.port')}"
    proto = {"1.0": "OpenFlow10", "1.3": "OpenFlow13"}.get(values.get("openflow.version"))
    want_ports = list(values.get("ports") or [])
    held = list(state["ports"])
    checks = [
        check("the bridge exists", state["exists"], f"{bridge} in list-br",
              "bridge", bridge if state["exists"] else "", bridge),
        check("its controller", state["controllers"] == [want_target],
              f"get-controller {state['controllers'] or 'none'}, wanted {want_target}",
              "controller", ", ".join(state["controllers"]), want_target),
        check("its OpenFlow version", state["protocols"] == [proto],
              f"protocols {state['protocols'] or 'none'}, wanted {proto}",
              "OpenFlow version", ", ".join(state["protocols"]), proto),
        check("its fail mode", state["fail_mode"] == values.get("openflow.fail_mode"),
              f"fail mode {state['fail_mode'] or 'none'}, wanted "
              f"{values.get('openflow.fail_mode')}",
              "fail mode", state["fail_mode"], values.get("openflow.fail_mode")),
        check("its OpenFlow ports", set(want_ports) <= set(held),
              f"ports {', '.join(held) or 'none'}, wanted {', '.join(want_ports)}",
              "ports", ", ".join(held),
              # The program adds ports and takes none away: what the bridge holds, then its.
              ", ".join(held + [p for p in want_ports if p not in held])),
    ]
    if values.get("openflow.datapath_id"):
        checks.append(check(
            "its datapath id", state["datapath_id"] == values["openflow.datapath_id"],
            f"datapath_id {state['datapath_id'] or 'none'}, wanted "
            f"{values['openflow.datapath_id']}",
            "datapath id", state["datapath_id"], values["openflow.datapath_id"]))
    numbers = values.get("port.openflow_port") or {}
    if numbers:
        # Each port's OpenFlow number as OVS gave it, against NetBox's (C2603): a request OVS
        # could not honour (the number taken) leaves the port numbered otherwise.
        given = state.get("ofport") or {}
        wrong = sorted(p for p, n in numbers.items() if given.get(p) != n)
        checks.append(check(
            "its OpenFlow port numbers", not wrong,
            ", ".join(f"{p} is {given.get(p) or 'unnumbered'}, wanted {numbers[p]}"
                      for p in wrong) or
            ", ".join(f"{p} {n}" for p, n in sorted(numbers.items())),
            "OpenFlow port numbers",
            ", ".join(f"{p} {given.get(p) or 'unnumbered'}" for p in wrong),
            ", ".join(f"{p} {numbers[p]}" for p in wrong)))
    return checks


def verify(ask, bridge: str, values: dict, drv, *, sleep=time.sleep) -> dict:
    """The checks after the send: ``{"ok", "checks": [{"name", "state", "words"}], "dpid"}``."""
    after = read_bridge(ask, bridge, ports=list(values.get("ports") or []))
    checks = [(c["name"], c["ok"], c["words"]) for c in bridge_checks(after, bridge, values)]
    out = {"ok": False, "checks": [{"name": n, "state": "pass" if ok else "fail", "words": w}
                                   for n, ok, w in checks], "dpid": after["datapath_id"]}
    if not all(ok for _n, ok, _w in checks):
        out["checks"].append({"name": "the controller's switch list", "state": "not_reached",
                              "words": "not read: the bridge did not read back as rendered"})
        return out
    out["checks"].append(openflow_config.seen_by_controller(drv, after["datapath_id"],
                                                            sleep=sleep))
    out["ok"] = out["checks"][-1]["state"] == "pass"
    return out


def apply(network: str, device: str, confirmed_hash: str, *, actor: str,
          actor_verified: str = "", values=None, session=None, driver=None,
          connection: str = "", sleep=time.sleep, now=time.time) -> dict:
    """Apply the previewed configuration as *actor*, bound to *confirmed_hash*. ``{"ok",
    "error", "at", "outcome", "id", "hash", "plan", "sent", "verify", "rollback", "record"}``;
    ``outcome`` one of ``refused``, ``verified``, ``rolled_back``, ``rollback_failed``, and for
    a bridge already as intended (nothing sent) whose controller does not list it,
    ``unverified``. *driver* (tests) replaces `connections.driver_for`."""
    from modules.nsot import device_ops
    from modules.sdn import openflow_templates as T

    op_id = f"ofcfg-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(now()))}-{secrets.token_hex(4)}"
    out = {"ok": False, "error": "", "at": "values", "outcome": "refused", "id": op_id,
           "hash": "", "plan": None, "sent": [], "verify": {"checks": []},
           "rollback": {"ran": False}, "record": {"ok": False, "error": ""}, "actor": actor}
    if not actor or actor_verified in ("", "none"):
        out["error"] = "an OpenFlow configuration is applied by a verified person"
        return out
    why = T.push_refusal(network, TEMPLATE)
    if why:
        out["error"] = why
        return out
    p = plan(network, device, values=values, session=session)
    out["plan"] = p
    if not p["ok"]:
        out["at"], out["error"] = p["at"], p["error"]
        return out
    out["at"], out["hash"] = "hash", p["hash"]
    if p["hash"] != confirmed_hash:
        out["error"] = (f"the preview's hash was {str(confirmed_hash)[:12] or 'none'}, and the "
                        f"plan made now is {p['hash'][:12]}: the bridge or its NetBox values "
                        "moved since the preview, so nothing was sent; preview again")
        return out
    try:
        name = _connection_name(network, p["values"], connection)
    except Refused as exc:
        out["error"] = str(exc)
        return out
    if driver is not None:
        made = driver(network, name)
    else:
        from modules.sdn import connections
        made = connections.driver_for(network, name)
    if not made.get("ok"):
        out["error"] = f"the controller connection {name} could not be opened: {made.get('error')}"
        return out
    drv = made["driver"]
    if session is None:
        from modules.connection import with_temp_connection as session
    dev = _inventory(network, device)
    bridge = p["values"]["openflow.instance"]
    from modules.sdn import openflow_templates
    vals = openflow_templates.derived(p["values"])
    started = now()
    out["at"] = "hold"
    try:
        with device_ops.hold(network, device, "openflow config", actor,
                             detail=f"the {TEMPLATE} template's transaction",
                             ip=dev.get("ip", "")):
            def run(conn):
                def ask(c):
                    return conn.send_command_timing(c, read_timeout=30) or ""
                if p["unchanged"]:
                    # Already as intended (every check of the bridge passed before): nothing
                    # is sent, and Verify still reads the bridge and the controller's list.
                    out["sent"] = []
                else:
                    out["at"] = "send"
                    answer = ask(p["program"][0])
                    out["sent"] = [{"command": p["program"][0], "answer": answer[:400]}]
                    failed = _failed(answer)
                    if failed:
                        out["error"] = f"the server refused the transaction: {failed}"
                if not out["error"]:
                    out["at"] = "verify"
                    began = now()
                    out["verify"] = openflow_config.timed(
                        verify(ask, bridge, vals, drv, sleep=sleep), began, now())
                    if out["verify"]["ok"]:
                        out["outcome"], out["ok"] = "verified", True
                        return
                    out["error"] = "Verify failed: " + "; ".join(
                        c["words"] for c in out["verify"]["checks"] if c["state"] == "fail")
                if not out["sent"]:
                    # Nothing was sent, so nothing is put back: the bridge is configured and
                    # the controller does not list it.
                    out["outcome"] = "unverified"
                    return
                out["at"] = "rollback"
                undone = ask(p["undo"])
                back = read_bridge(ask, bridge)
                same = (not _failed(undone)
                        and {k: back[k] for k in ("exists", "controllers", "fail_mode",
                                                  "protocols", "ports")}
                        == {k: p["before"][k] for k in ("exists", "controllers", "fail_mode",
                                                        "protocols", "ports")})
                out["rollback"] = {"ran": True, "ok": same, "command": p["undo"],
                                   "answer": undone[:400],
                                   "words": ("the bridge reads as it did before" if same else
                                             "the bridge does not read as it did before: "
                                             f"{json.dumps(back, sort_keys=True)[:300]}")}
                out["outcome"] = "rolled_back" if same else "rollback_failed"
            session(dev, run)
    except device_ops.DeviceBusy as exc:
        out["error"] = f"refused: {exc}"
        return out
    except Exception as exc:                          # noqa: BLE001 (that server's failure)
        from modules.utils import error_text
        out["error"] = (out["error"] + "; " if out["error"] else "") + \
            f"the session failed at {out['at']}: {error_text(exc)}"[:300]
        if out["outcome"] == "refused" and out["at"] in ("send", "verify", "rollback"):
            out["outcome"] = "rollback_failed"
    out["record"] = _record(network, p, out, actor=actor, actor_verified=actor_verified,
                            connection=name, started=started, ended=now())
    if not out["record"]["ok"]:
        out["error"] = ((out["error"] + "; ") if out["error"] else "") + \
            f"the record could not be kept: {out['record']['error']}"
    return out


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _record(network, p, out, *, actor, actor_verified, connection, started, ended) -> dict:
    status = p["status"]
    row = {"id": out["id"], "at": _iso(ended), "started": _iso(started), "ended": _iso(ended),
           "connection": connection, "dpid_hex": out["verify"].get("dpid") or "",
           "hash": p["hash"], "words": [x["text"] for x in p["lines"]],
           "requests": p["program"], "undo": p["undo"], "before": p["before"],
           "sent": out["sent"], "verify": out["verify"], "rollback": out["rollback"],
           "outcome": out["outcome"], "error": out["error"], "mode": "hitl",
           "export_sha256": p.get("export_sha256", ""),
           "source": p.get("source") or openflow_config.source_of({}),
           "changes": p.get("changes") or [],
           "response": {"kind": "openflow_config", "device": p["device"], "template": TEMPLATE,
                        "template_capture": status.get("capture", "")},
           "actor": actor, "actor_verified": actor_verified}
    return openflow_config.record(network, row)
