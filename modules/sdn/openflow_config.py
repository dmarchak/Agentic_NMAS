"""A switch's OpenFlow configuration, NSoT-driven: one operation for every switch Mercury has an
OpenFlow template for, dispatched on the switch's template (docs/LAB9_OPENFLOW.md sections 4
and 4b; Lab 9 Objective 2).

**The values come from the committed NSOT export** (C2777): `values_from_export` reads the
network's ``nsot/export.json`` at HEAD (`modules/nsot/export.py`) and the switch's values from it
(`openflow_values.from_export`), and every plan's hash includes the export's SHA-256, so a plan
names the bytes it read and an export committed since the preview refuses the confirm. A network
with no committed export is refused, naming the NSOT export card on SDN › Apps.

**Dispatch** (`template_for`): the switch's driver chooses its template
(`openflow_templates.for_driver`). An Open vSwitch server's (``ovs``) is
`modules/sdn/ovs_config.py`'s, one OVSDB transaction; a CLI template with a vendor driver
(`modules/sdn/openflow_cli.py`: ``arista_eos``, ``aruba_os_switch``) is this module's, its stages
in order (`CLI_STEPS`):

1. **values**: from the export; a missing or ill-shaped value refuses, named, with nothing read
   from the switch.
2. **read before**: `show version` (its OS version selects the platform profile's entry,
   `profile.select`) and `show running-config`, parsed into the template's OpenFlow model
   (`openflow_state.parse`). The configuration text itself is never kept: only its parsed model.
3. **render**: `openflow_state.render_against`, which decides ``state.bind_changed`` (the EOS
   agent's restart, C2599) from the switch's model. A program that would leave the switch still
   differing from intent (the template only adds) is refused here, naming what would remain.
4. **undo**: the vendor driver's lines putting back exactly what the program changes, checked
   by parsing the configuration as it would be after the program and the undo: it must read as
   it did before, or nothing is sent. Every program and undo line is one of the template's
   shapes (`openflow_cli.SHAPES`), the only configuration the session carries.
5. **hash** (`plan_hash`): over the network, the switch, the template, the program, the undo,
   the parsed before and the export's SHA-256.
6. **hold**, **send**: refused unless the template is CONFIRMED on the network
   (`openflow_templates.push_refusal`); planned again and the hash compared (a moved switch or
   export is refused, naming both hashes, nothing sent); the switch held (`device_ops.hold`)
   while the lines are sent in one configuration set. No save (section 4b: undecided): the
   result says the running configuration holds the change until the switch reloads.
7. **verify**: the running configuration read back and parsed, its OpenFlow layer compared
   with the program's (no difference); then the switch's datapath id (NetBox's when given, else
   the switch's own `show openflow`) in the controller's switch list (`seen_by_controller`,
   shared with Open vSwitch's).
8. **rollback**: on a refused line or a failed check, the undo is sent and the configuration
   read again: the result says whether its OpenFlow layer reads as it did before.
9. **record**: the run in the network's SDN operation record (`record`, shared with Open
   vSwitch's; ``response.kind`` ``openflow_config``), which History reads.

A switch already as intended plans as unchanged: its apply sends nothing and verifies.

**What a plan says of itself, kept in its record** (the operator, 2026-11-10: a result and its
History record name their source and give before and after for each changed value):
``source`` (`source_of`: the export's SHA-256 and the commit that wrote it, and each value's
origin as `openflow_values` resolved it) and ``changes`` (``[{"value", "before", "after"}]``:
for a CLI switch `openflow_state.changes`, the comparison the plan already made; for Open
vSwitch the bridge's checks, `ovs_config.bridge_checks`). Verify is timed (``verify.seconds``,
``verify.at``).
"""

import hashlib
import json
import logging
import secrets
import time

log = logging.getLogger(__name__)

CLI_STEPS = ("values", "read before", "render", "undo", "hash", "hold", "send", "verify",
             "rollback", "record")
#: The controller's switch list read after a send: a switch connects within seconds.
VERIFY_READS = 6
VERIFY_PAUSE = 2.0
#: Said in every vendor result (docs/LAB9_OPENFLOW.md section 4b).
NOT_SAVED = ("not saved to the startup configuration: whether the OpenFlow configuration "
             "saves is undecided (docs/LAB9_OPENFLOW.md section 4b), so the running "
             "configuration holds it until the switch reloads")
EXPORT_CARD = "the NSOT export card on SDN › Apps (Export from NetBox…)"


class Refused(ValueError):
    pass


# --------------------------------------------------------------------------- the values

def values_from_export(network: str, device: str) -> dict:
    """*device*'s OpenFlow values from *network*'s committed NSOT export: `from_export`'s
    answer (``{"ok", "values", "defaults", "origins", "error"}``, the values carrying
    ``nsot.export_sha256``) with ``export_commit``, the commit that wrote that export
    (`export.last_commit`), or a refusal naming the export card when none is committed."""
    from modules.nsot import export as X
    from modules.sdn import openflow_values as V

    got = X.read(network)
    if not got["ok"]:
        why = (f"{network} has no committed NSOT export, and a switch's OpenFlow values are read "
               f"from it: commit one with {EXPORT_CARD} first" if got.get("absent") else
               f"{network}'s committed NSOT export cannot be used: {got['error']}")
        return {"ok": False, "values": {}, "defaults": [], "error": why}
    return dict(V.from_export(got["export"], device),
                export_commit=str((X.last_commit(network) or {}).get("commit") or ""))


def source_of(got: dict) -> dict:
    """What a plan was built from, for its result and its record: ``{"export_sha256",
    "export_commit", "origins"}`` out of the values' answer *got* (`values_from_export`): the
    committed export's hash and the commit that wrote it, and where each value came from, as
    `openflow_values` resolved it. Carried, never derived again by a reader."""
    values = got.get("values") or {}
    return {"export_sha256": str(values.get("nsot.export_sha256") or ""),
            "export_commit": str(got.get("export_commit") or ""),
            "origins": [dict(o) for o in got.get("origins") or []]}


def built_from(network: str, source: dict) -> dict:
    """A plan's or a record's *source* (`source_of`) as a screen says it, one way on the result
    card and on History (templates/v2/_sdn_built_from.html): ``{"network", "export_sha256",
    "export_commit", "clauses"}``, the clauses `openflow_values.origin_words`' of the origins
    it kept; ``{}`` for a source naming no export (a record from before sources were kept)."""
    from modules.sdn import openflow_values as V

    source = source or {}
    if not source.get("export_sha256"):
        return {}
    return {"network": network, "export_sha256": str(source["export_sha256"]),
            "export_commit": str(source.get("export_commit") or ""),
            "clauses": V.origin_words(source.get("origins") or [])}


def sent_words(sent: list) -> str:
    """What a run sent, in words: ``"12 lines"``, ``"1 transaction"``, or ``""`` for nothing
    (a vendor switch's record keeps its line count, Open vSwitch's its one command)."""
    said = []
    for s in sent or []:
        n = s.get("lines")
        said.append(f"{n} line{'s' if n != 1 else ''}" if n else "1 transaction")
    return ", ".join(said)


def _inventory(network: str, device: str):
    from modules.device import load_saved_devices
    from modules.nsot import listref
    for d in load_saved_devices(listref.resolve(network).csv_path):
        if d.get("hostname") == device:
            return d
    return None


def template_for(dev: dict) -> tuple:
    """``(template, "")`` for the inventory device *dev*, or ``("", why)``."""
    from modules.sdn import openflow_cli, openflow_templates as T
    driver = (dev or {}).get("device_type") or ""
    name = T.for_driver(driver)
    if name is None:
        return "", (f"{dev.get('hostname')}'s driver is {driver or '(none)'}, and no OpenFlow "
                    f"template is for it ({', '.join(T.names())})")
    if name != "ovs" and name not in openflow_cli.DRIVERS:
        return "", (f"the {name} template has no vendor driver yet, so Mercury renders it and "
                    "sends nothing")
    return name, ""


def plan_hash(network: str, device: str, template: str, program: list, undo: list,
              before: dict, export_sha256: str) -> str:
    body = json.dumps({"network": network, "device": device, "template": template,
                       "program": program, "undo": undo, "before": before,
                       "export_sha256": export_sha256}, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- the plan

def plan(network: str, device: str, *, values=None, session=None) -> dict:
    """The operation for *device*, planned with no write: dispatched on its template. *values*
    (tests) replaces the export read; *session* (tests) `connection.with_temp_connection`."""
    dev = _inventory(network, device)
    if dev is None:
        return {"ok": False, "error": f"{device} is not a device of {network}", "at": "values",
                "device": device, "network": network, "template": ""}
    name, why = template_for(dev)
    if why:
        return {"ok": False, "error": why, "at": "values", "device": device,
                "network": network, "template": ""}
    if name == "ovs":
        from modules.sdn import ovs_config
        return ovs_config.plan(network, device, values=values, session=session)
    return _cli_plan(network, device, dev, name, values=values, session=session)


def _read_switch(conn, driver, instance: str) -> dict:
    """The switch's own version and running configuration (two reads on its capture list)."""
    version = conn.send_command("show version", read_timeout=60) or ""
    running = conn.send_command("show running-config", read_timeout=120) or ""
    return {"version": driver.version(version), "running": running}


def _cli_plan(network, device, dev, name, *, values=None, session=None) -> dict:
    from modules.platforms import profile as P
    from modules.sdn import openflow_cli, openflow_state as S, openflow_templates as T
    from modules.sdn import openflow_values as V

    drv = openflow_cli.DRIVERS[name]
    out = {"ok": False, "error": "", "at": "values", "network": network, "device": device,
           "template": name, "family": drv.family, "values": {}, "defaults": [],
           "where": V.WHERE, "status": T.status(network, name), "lines": [], "program": [],
           "undo": [], "before": None, "hash": "", "citations": T.load(name)["citations"],
           "excluded": [], "takes": [], "different": [], "unchanged": False, "version": "",
           "profile": "", "export_sha256": "", "steps": CLI_STEPS, "source": source_of({}),
           "changes": []}
    got = values if values is not None else values_from_export(network, device)
    out["values"], out["defaults"] = dict(got.get("values") or {}), list(got.get("defaults") or [])
    out["excluded"] = list(out["values"].get("excluded") or [])
    out["export_sha256"] = str(out["values"].get("nsot.export_sha256") or "")
    out["source"] = source_of(got)
    if not got.get("ok"):
        out["error"] = got.get("error") or "the NSOT export's values could not be read"
        return out
    v = out["values"]
    out["at"] = "read before"
    if session is None:
        from modules.connection import with_temp_connection as session
    try:
        read = session(dev, lambda conn: _read_switch(conn, drv, v.get("openflow.instance", "")))
    except Exception as exc:                          # noqa: BLE001 (that switch's failure)
        from modules.utils import error_text
        out["error"] = f"{device} could not be read: {error_text(exc)}"[:300]
        return out
    out["version"] = read["version"]
    if not read["version"]:
        out["error"] = (f"{device}'s show version names no {drv.family} version, so which "
                        "platform profile entry covers it cannot be told: nothing is rendered")
        return out
    selected = P.select(dev.get("device_type"), read["version"])
    if not selected.get("ok"):
        out["error"] = selected["error"]
        return out
    out["profile"] = selected["profile"]
    try:
        before = S.parse(name, read["running"])
    except S.Unparsable as exc:
        out["error"] = f"{device}'s running configuration could not be parsed: {exc}"
        return out
    out["at"] = "render"
    # B (modules/protected.py) asked here, by the template's render: every port the switch's
    # OpenFlow instance would take is refused when it is a protected object.
    first = T.render(name, v, selected=selected)
    r = S.render_against(name, v, before, selected, first=first)
    if not r["ok"]:
        out["error"] = r["error"]
        return out
    rendered = r["rendered"]
    out["lines"], out["program"], out["takes"] = (rendered["lines"], rendered["program"],
                                                  rendered["takes"])
    # A running configuration is the whole text: a controller, instance or VLAN the program
    # makes and the text does not hold is absent from the switch, never unread.
    out["different"] = r["different"] + [f"{u}: wanted, the switch has none" for u in r["unread"]]
    # The same comparison, value by value, for the result and the record.
    out["changes"] = S.changes(r["want"], before)
    out["before"] = before
    program = list(rendered["program"])
    after = S.parse(name, read["running"] + "\n" + "\n".join(program))
    left, missing = S.differences(r["want"], after)
    left += [f"{u}: still none" for u in missing]
    if left:
        out["error"] = (f"after this program {device} would still differ from intent "
                        f"({'; '.join(left)}): the {name} template adds and never removes what "
                        "the switch holds beyond NetBox's values, so nothing is sent")
        return out
    out["at"] = "undo"
    undo, why = drv.undo(before, r["want"], v)
    if undo is None:
        out["error"] = f"{device}: {why}: nothing is sent"
        return out
    why = openflow_cli.line_refusal(name, program) or (
        undo and openflow_cli.line_refusal(name, undo))
    if why:
        out["error"] = f"the rendered lines are not of their shapes: {why}"
        return out
    back = S.parse(name, "\n".join([read["running"]] + program + undo))
    d, u = S.differences(before, back)
    if d or u:
        out["error"] = (f"the undo would not put {device} back as it is ({'; '.join(d + u)}), "
                        "so nothing is sent")
        return out
    out["undo"] = undo
    out["unchanged"] = not out["different"]
    out["at"] = "hash"
    out["hash"] = plan_hash(network, device, name, program, undo, before, out["export_sha256"])
    out["ok"] = True
    return out


# --------------------------------------------------------------------------- shared steps

def connection_name(network: str, values: dict, given: str = "") -> str:
    """The Mercury controller connection a switch is verified against: the config context's
    ``openflow.connection``, or the network's only one (`connections.choose`)."""
    from modules.sdn import connections
    name, why = connections.choose(network, given or values.get("openflow.connection", ""),
                                   purpose="the one to verify against")
    if why:
        raise Refused(why)
    return name


def seen_by_controller(drv, dpid_hex: str, *, sleep=time.sleep) -> dict:
    """The check that the controller lists the switch: its switch list read up to
    `VERIFY_READS` times `VERIFY_PAUSE` apart until datapath *dpid_hex* is in it.
    ``{"name", "state", "words"}``."""
    try:
        dpid = int(dpid_hex, 16)
    except (TypeError, ValueError):
        return {"name": "the controller's switch list", "state": "fail",
                "words": f"the switch's datapath id {dpid_hex!r} is not hex"}
    seen, last = False, ""
    for i in range(VERIFY_READS):
        got = drv.switches()
        if got.get("ok"):
            dpids = [s.get("dpid") for s in got.get("switches") or []]
            seen = dpid in dpids
            last = f"{len(dpids)} switch(es)"
        else:
            last = f"unreadable: {got.get('error')}"
        if seen:
            break
        if i < VERIFY_READS - 1:
            sleep(VERIFY_PAUSE)
    return {"name": "the controller's switch list", "state": "pass" if seen else "fail",
            "words": (f"datapath {dpid_hex} is in the controller's switch list ({last})" if seen
                      else f"datapath {dpid_hex} is not in the controller's switch list after "
                           f"{VERIFY_READS} reads {VERIFY_PAUSE:g} s apart ({last})")}


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def record(network: str, row: dict) -> dict:
    """The run in *network*'s SDN operation record (`flow_intent.record_operation`), said,
    never raised: ``{"ok", "error"}``."""
    from modules.sdn import flow_intent
    try:
        flow_intent.record_operation(network, row)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "error": ""}


def _controller(network, values, connection, driver):
    name = connection_name(network, values, connection)
    if driver is not None:
        made = driver(network, name)
    else:
        from modules.sdn import connections
        made = connections.driver_for(network, name)
    if not made.get("ok"):
        raise Refused(f"the controller connection {name} could not be opened: "
                      f"{made.get('error')}")
    return name, made["driver"]


# --------------------------------------------------------------------------- apply

def apply(network: str, device: str, confirmed_hash: str, *, actor: str,
          actor_verified: str = "", values=None, session=None, driver=None,
          connection: str = "", sleep=time.sleep, now=time.time) -> dict:
    """Apply *device*'s previewed configuration as *actor*, bound to *confirmed_hash*,
    dispatched on its template. ``outcome`` one of ``refused``, ``verified``, ``rolled_back``,
    ``rollback_failed``, and for a switch already as intended (nothing sent) whose controller
    does not list it, ``unverified``."""
    dev = _inventory(network, device)
    name, why = template_for(dev) if dev else ("", f"{device} is not a device of {network}")
    if why:
        return {"ok": False, "error": why, "at": "values", "outcome": "refused", "id": "",
                "hash": "", "plan": None, "sent": [], "verify": {"checks": []},
                "rollback": {"ran": False}, "record": {"ok": False, "error": ""},
                "actor": actor, "device": device}
    if name == "ovs":
        from modules.sdn import ovs_config
        return dict(ovs_config.apply(network, device, confirmed_hash, actor=actor,
                                     actor_verified=actor_verified, values=values,
                                     session=session, driver=driver, connection=connection,
                                     sleep=sleep, now=now), device=device)
    return _cli_apply(network, device, dev, name, confirmed_hash, actor=actor,
                      actor_verified=actor_verified, values=values, session=session,
                      driver=driver, connection=connection, sleep=sleep, now=now)


def _cli_apply(network, device, dev, name, confirmed_hash, *, actor, actor_verified, values,
               session, driver, connection, sleep, now) -> dict:
    from modules.nsot import device_ops
    from modules.sdn import openflow_cli, openflow_templates as T

    drv = openflow_cli.DRIVERS[name]
    op_id = f"ofcfg-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(now()))}-{secrets.token_hex(4)}"
    out = {"ok": False, "error": "", "at": "values", "outcome": "refused", "id": op_id,
           "hash": "", "plan": None, "sent": [], "verify": {"checks": []},
           "rollback": {"ran": False}, "record": {"ok": False, "error": ""}, "actor": actor,
           "device": device, "template": name, "saved": False, "save_words": NOT_SAVED}
    if not actor or not actor_verified:
        out["error"] = "an OpenFlow configuration is applied by a verified person"
        return out
    why = T.push_refusal(network, name)
    if why:
        out["error"] = why
        return out
    # Planned again by the vendor planner itself (its device and template are `apply`'s, read
    # moments before), which asks B through the template's render.
    p = _cli_plan(network, device, dev, name, values=values, session=session)
    out["plan"] = p
    if not p["ok"]:
        out["at"], out["error"] = p["at"], p["error"]
        return out
    out["at"], out["hash"] = "hash", p["hash"]
    if p["hash"] != confirmed_hash:
        out["error"] = (f"the preview's hash was {str(confirmed_hash)[:12] or 'none'}, and the "
                        f"plan made now is {p['hash'][:12]}: the switch or the NSOT export moved "
                        "since the preview, so nothing was sent; preview again")
        return out
    try:
        conn_name, ctl = _controller(network, p["values"], connection, driver)
    except Refused as exc:
        out["error"] = str(exc)
        return out
    if session is None:
        from modules.connection import with_temp_connection as session
    from modules.sdn import openflow_state as S
    values_ = p["values"]
    instance = values_.get("openflow.instance") or ""
    want = S.model_of(name, {"program": p["program"]})
    started = now()
    out["at"] = "hold"
    try:
        with device_ops.hold(network, device, "openflow config", actor,
                             detail=f"the {name} template's OpenFlow lines",
                             ip=dev.get("ip", "")):
            def run(conn):
                if p["unchanged"]:
                    out["sent"] = []
                else:
                    out["at"] = "send"
                    answer = conn.send_config_set(p["program"], read_timeout=60) or ""
                    out["sent"] = [{"lines": len(p["program"]), "answer": answer[-400:]}]
                    refused = openflow_cli.failed(answer)
                    if refused:
                        out["error"] = f"{device} refused a line: {refused}"
                if not out["error"]:
                    out["at"] = "verify"
                    began = now()
                    out["verify"] = timed(_verify(conn, name, drv, want, values_, instance, ctl,
                                                  sleep=sleep), began, now())
                    if out["verify"]["ok"]:
                        out["outcome"], out["ok"] = "verified", True
                        return
                    out["error"] = "Verify failed: " + "; ".join(
                        c["words"] for c in out["verify"]["checks"] if c["state"] == "fail")
                if not out["sent"]:
                    # Already as intended, so nothing was sent and nothing is put back: the
                    # switch is configured and the controller does not list it.
                    out["outcome"] = "unverified"
                    return
                out["at"] = "rollback"
                undone = conn.send_config_set(p["undo"], read_timeout=60) or ""
                out["rollback"] = roll_back_read(conn, name, p, undone)
                out["outcome"] = "rolled_back" if out["rollback"]["ok"] else "rollback_failed"
            session(dev, run)
    except device_ops.DeviceBusy as exc:
        out["error"] = f"refused: {exc}"
        return out
    except Exception as exc:                          # noqa: BLE001 (that switch's failure)
        from modules.utils import error_text
        out["error"] = (out["error"] + "; " if out["error"] else "") + \
            f"the session failed at {out['at']}: {error_text(exc)}"[:300]
        if out["outcome"] == "refused" and out["at"] in ("send", "verify", "rollback"):
            out["outcome"] = "rollback_failed"
    ended = now()
    status = p["status"]
    row = {"id": out["id"], "at": _iso(ended), "started": _iso(started), "ended": _iso(ended),
           "connection": conn_name, "dpid_hex": out["verify"].get("dpid") or "",
           "hash": p["hash"], "words": [x["text"] for x in p["lines"]],
           "requests": p["program"], "undo": p["undo"], "before": p["before"],
           "sent": out["sent"], "verify": out["verify"], "rollback": out["rollback"],
           "outcome": out["outcome"], "error": out["error"], "mode": "hitl",
           "saved": False, "save_words": NOT_SAVED,
           "export_sha256": p.get("export_sha256", ""),
           "source": p.get("source") or source_of({}), "changes": p.get("changes") or [],
           "response": {"kind": "openflow_config", "device": device, "template": name,
                        "template_capture": status.get("capture", "")},
           "actor": actor, "actor_verified": actor_verified}
    out["record"] = record(network, row)
    if not out["record"]["ok"]:
        out["error"] = ((out["error"] + "; ") if out["error"] else "") + \
            f"the record could not be kept: {out['record']['error']}"
    return out


def timed(verify: dict, began: float, ended: float) -> dict:
    """*verify* (a Verify's answer) with how long it took and when it ended: ``seconds`` (to a
    tenth) and ``at`` (UTC). Shared with Open vSwitch's."""
    return dict(verify, seconds=round(max(0.0, ended - began), 1), at=_iso(ended))


def roll_back_read(conn, name: str, p: dict, undone: str) -> dict:
    """After the undo was sent (its answer *undone*): the configuration read again and its
    OpenFlow layer compared with the plan's before. ``{"ran", "ok", "lines", "answer",
    "words"}``."""
    from modules.sdn import openflow_cli, openflow_state as S
    text = conn.send_command("show running-config", read_timeout=120) or ""
    d, u = S.differences(p["before"], S.parse(name, text))
    same = not d and not u and not openflow_cli.failed(undone)
    return {"ran": True, "ok": same, "lines": len(p["undo"]), "answer": undone[-400:],
            "words": ("the OpenFlow configuration reads as it did before" if same else
                      "the OpenFlow configuration does not read as it did before: "
                      + "; ".join(x for x in d + u + [openflow_cli.failed(undone)] if x)[:300])}


def _verify(conn, name, drv, want, values, instance, ctl, *, sleep) -> dict:
    """The checks after the send: the running configuration's OpenFlow layer, then the
    controller's switch list. ``{"ok", "checks", "dpid"}``."""
    from modules.sdn import openflow_state as S
    text = conn.send_command("show running-config", read_timeout=120) or ""
    try:
        d, u = S.differences(want, S.parse(name, text))
    except S.Unparsable as exc:
        d, u = [f"the running configuration could not be parsed: {exc}"], []
    checks = [{"name": "the running configuration's OpenFlow layer",
               "state": "pass" if not d and not u else "fail",
               "words": ("reads as the program sets it" if not d and not u
                         else "; ".join(d + [f"{x} unread" for x in u])[:300])}]
    dpid = values.get("openflow.datapath_id") or ""
    if not dpid:
        shown = (conn.send_command("show openflow", read_timeout=60) if name == "arista_eos"
                 else conn.send_command(f"show openflow instance {instance}", read_timeout=60))
        dpid = drv.dpid(shown or "")
    out = {"ok": False, "checks": checks, "dpid": dpid}
    if checks[0]["state"] != "pass":
        checks.append({"name": "the controller's switch list", "state": "not_reached",
                       "words": "not read: the switch did not read back as rendered"})
        return out
    if not dpid:
        checks.append({"name": "the controller's switch list", "state": "fail",
                       "words": ("the switch names no datapath id and NetBox gives none "
                                 "(openflow_datapath_id), so the controller's list cannot be "
                                 "asked for it")})
        return out
    checks.append(seen_by_controller(ctl, dpid, sleep=sleep))
    out["ok"] = checks[-1]["state"] == "pass"
    return out
