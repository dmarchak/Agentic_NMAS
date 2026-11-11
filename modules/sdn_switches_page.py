"""SDN › Switches (board docs/boards/lab9-sdn.html, artboard A, self-signed 2026-11-10; Lab 9
Objective 2): every switch NetBox marks for OpenFlow, what the committed NSOT export says it
should be, what the controller lists and what Mercury last configured, joined on one row.

**Stored reads only, never a switch or controller call per view:**
- the network's committed NSOT export (`modules/nsot/export.py`): every device with an
  interface tagged ``openflow``, and its OpenFlow values (`openflow_values.from_export`);
- the SDN reader's stored switch list (`sdn_page.stored`): the datapath ids each controller
  listed at its last good read;
- the network's SDN operation record (`flow_intent.operations`): each switch's newest
  OpenFlow configuration (``response.kind`` ``openflow_config``);
- the inventory (the switch's driver, so its template) and each template's status on the
  network (`openflow_templates.status`).

**A switch's state** (`state_of`), worst first:
- ``differs``: its last configuration rolled back or failed;
- ``netbox_changed``: its last configuration held, and was made from an export other than the
  committed one: NetBox's values moved after the switch was configured, so the cause is said
  as NetBox's change and never as the switch's (the operator, the Lab 9 sitting, 2026-11-10).
  `netbox_moved` names what changed for the switch, each value before and after, between the
  two exports, from the origins its record kept (`openflow_config.source_of`) and the
  committed export's; where the record kept none, or none of them changed, it says that;
- ``not_connected``: configured (verified) and its datapath id is not in the controller's list;
- ``not_configured``: Mercury never configured it, and the controller does not list it;
- ``connected``: in the controller's list, and either configured from the committed export or
  never configured by Mercury (connected by hand, as the lab's base setup leaves it).
A datapath id the controller lists and no export switch carries is a fifth count, ``seen by the
controller, not in NetBox``. The switch's own configuration is read by Preview (the plan), never
by this view: the board's "Switch reports" column is the last configuration's read-back.

The previews and confirms (Configure from NetBox…, Confirm against a capture…) build their cards
here from the operation's answers (`openflow_config.plan`, `openflow_templates.confirm`).
"""

import hashlib
import json
import logging

log = logging.getLogger(__name__)

STATES = (("differs", "Differs from intent", "danger"),
          ("netbox_changed", "NetBox changed since configured", "warn"),
          ("not_connected", "Configured, not connected", "warn"),
          ("not_configured", "Not configured", "muted"),
          ("connected", "Connected as intended", "ok"))
STATE_WORDS = {k: (label, tone) for k, label, tone in STATES}
PLATFORMS = {"arista_eos": "Arista EOS", "aruba_os_switch": "ArubaOS-Switch",
             "ovs": "OVS on Linux", "hp_comware": "HP Comware", "aruba_aoscx": "AOS-CX"}
#: Where a template cannot take an IPv6 controller (its `ipv6_controller`), said on the screen.
IPV6_WORDS = ("Arista EOS and ArubaOS-Switch take an IPv4 controller only (their vendor "
              "documents): an IPv6 openflow Service address is refused at the preview, named. "
              "Open vSwitch and Comware take either.")
#: The most switches one group draws before it folds the rest (built for large fleets).
GROUP_SHOWN = 25


def _short(sha: str) -> str:
    return (sha or "")[:12]


def _records_by_switch(network: str) -> tuple:
    """``({switch: its newest openflow_config record}, error)``."""
    from modules.sdn import flow_intent
    got = flow_intent.operations(network)
    out = {}
    for row in got["rows"]:
        resp = row.get("response") or {}
        if resp.get("kind") == "openflow_config" and resp.get("device"):
            out[resp["device"]] = row                  # oldest first: the newest wins
    return out, got.get("error", "")


def _listed(network: str) -> dict:
    """The SDN reader's stored switch lists: ``{"state", "dpids": {int: controller}, "at"}``."""
    from modules import sdn_page
    got = sdn_page.stored(network)
    out = {"state": got.get("state"), "dpids": {}, "at": got.get("value_at", ""),
           "why": got.get("why", "") or got.get("failed", "")}
    for c in (got.get("value") or {}).get("controllers") or []:
        for s in c.get("switches") or []:
            if isinstance(s.get("dpid"), int):
                out["dpids"][s["dpid"]] = c.get("name", "")
    return out


def _marked(export: dict) -> list:
    """The export's devices with an interface tagged openflow, by name."""
    from modules.nsot import export as X
    body = export.get("body") or {}
    names = sorted({i.get("device") for i in body.get("interfaces") or []
                    if "openflow" in (i.get("tags") or []) and i.get("device")})
    return [X.device(export, n) for n in names if X.device(export, n)]


def _dpid_int(text: str):
    try:
        return int(str(text or ""), 16) if text else None
    except ValueError:
        return None


def state_of(record, dpid, listed: set, export_sha: str) -> str:
    """The switch's state (see the module's list)."""
    seen = dpid is not None and dpid in listed
    if record:
        if record.get("outcome") in ("rolled_back", "rollback_failed"):
            return "differs"
        if record.get("export_sha256") and record["export_sha256"] != export_sha:
            return "netbox_changed"
        if record.get("outcome") in ("verified", "unverified"):
            return "connected" if seen else "not_connected"
    return "connected" if seen else "not_configured"


def netbox_moved(network: str, record: dict, export_sha: str, export_commit: str,
                 now_origins: list) -> dict:
    """What NetBox changed for a switch between the export its last configuration was built
    from (*record*: its ``export_sha256`` and its ``source``, `openflow_config.source_of`) and
    the committed one (*export_sha*, written by *export_commit*; *now_origins*: the switch's
    origins in it, `openflow_values.from_export`). The comparison is of the two exports'
    values, never of the switch: this view reads no switch.

    ``{"network", "from_sha", "from_commit", "to_sha", "to_commit", "known", "changes":
    [{"value", "before", "after"}]}``: one change per value whose words differ between the two
    (a value one export gives and the other does not reads "not given"). ``known`` is False
    for a record kept before origins were (nothing to compare: which value changed is not
    known, and none is guessed); True with no change when the export moved for something
    else in NetBox. A datapath id is not compared here: an origin names where it came from
    and never prints it."""
    source = record.get("source") or {}

    def by_value(origins):
        return {str(o.get("value")): str(o.get("is") or "") for o in origins or []
                if o.get("value")}
    before, now = by_value(source.get("origins")), by_value(now_origins)
    changes = [{"value": k, "before": before.get(k) or "not given",
                "after": now.get(k) or "not given"}
               for k in list(before) + [k for k in now if k not in before]
               if before.get(k, "") != now.get(k, "")]
    return {"network": network, "from_sha": str(record.get("export_sha256") or ""),
            "from_commit": str(source.get("export_commit") or ""),
            "to_sha": export_sha, "to_commit": export_commit,
            "known": bool(before), "changes": changes if before else []}


def switches_view(network: str, args=None) -> dict:
    """The tab's data from stored reads (see the module). *args*: ``q`` (name, DPID or
    address), ``state`` and ``platform`` filters."""
    from modules.device import load_saved_devices
    from modules.nsot import export as X, listref
    from modules.sdn import openflow_templates as T, openflow_values as V

    args = args or {}
    q = str(args.get("q") or "").strip().lower()
    want_state = str(args.get("state") or "")
    want_platform = str(args.get("platform") or "")
    out = {"network": network, "q": q, "state": want_state,
           "platform": want_platform, "states": STATES, "platforms": PLATFORMS,
           "export": {"state": "none", "sha256": "", "error": ""}, "rows": [], "groups": [],
           "summary": {}, "unknown": [], "listed": {}, "templates": [], "records_error": "",
           "ipv6_words": IPV6_WORDS, "shown": 0, "total": 0}
    got = X.read(network)
    if got["ok"]:
        out["export"] = {"state": "ok", "sha256": got["sha256"], "error": ""}
    elif not got.get("absent"):
        out["export"] = {"state": "unreadable", "sha256": "", "error": got["error"]}
    listed = _listed(network)
    out["listed"] = {k: v for k, v in listed.items() if k != "dpids"}
    records, out["records_error"] = _records_by_switch(network)
    try:
        inventory = {d.get("hostname"): d for d in
                     load_saved_devices(listref.resolve(network).csv_path)}
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.warning("sdn switches: %s's inventory could not be read: %s", network, exc)
        inventory = {}
    rows, export = [], got.get("export") if got["ok"] else None
    committed = None                      # the commit that wrote the export: read once, if asked

    def export_commit():
        nonlocal committed
        if committed is None:
            committed = str((X.last_commit(network) or {}).get("commit") or "")
        return committed
    for dev in (_marked(export) if export else []):
        name = dev["name"]
        vals = V.from_export(export, name)
        v = vals.get("values") or {}
        inv = inventory.get(name) or {}
        template = T.for_driver(inv.get("device_type") or "") or ""
        rec = records.get(name)
        dpid_hex = v.get("openflow.datapath_id") or (rec or {}).get("dpid_hex") or ""
        dpid = _dpid_int(dpid_hex)
        state = state_of(rec, dpid, set(listed["dpids"]), out["export"]["sha256"])
        address = v.get("switch.address") or dev.get("primary_ip4") or dev.get("primary_ip6")
        rows.append({
            "name": name, "address": str(address or "").split("/")[0],
            "platform": template, "platform_words": PLATFORMS.get(template, "no template"),
            "driver": inv.get("device_type") or "", "in_inventory": bool(inv),
            "intent": (f"{v.get('controller.address') or '?'}:{v.get('controller.port') or '?'}"
                       f" · {v.get('openflow.version') or '?'} · "
                       f"{v.get('openflow.transport') or '?'}"),
            "values_ok": vals.get("ok", False), "values_error": vals.get("error", ""),
            "instance": v.get("openflow.instance") or "", "ports": v.get("ports") or [],
            "defaults": vals.get("defaults") or [], "excluded": v.get("excluded") or [],
            "dpid": dpid_hex, "seen": dpid is not None and dpid in listed["dpids"],
            "seen_by": listed["dpids"].get(dpid, "") if dpid is not None else "",
            "record": _record_words(rec), "state": state,
            # What NetBox changed since the switch was configured, said with the state.
            "netbox": netbox_moved(network, rec, out["export"]["sha256"], export_commit(),
                                   vals.get("origins") or [])
            if state == "netbox_changed" else {},
            "state_words": STATE_WORDS[state][0], "tone": STATE_WORDS[state][1]})
    known = {_dpid_int(r["dpid"]) for r in rows} - {None}
    out["unknown"] = [{"dpid": f"{d:016x}", "controller": c}
                      for d, c in sorted(listed["dpids"].items()) if d not in known]
    out["total"] = len(rows)
    out["summary"] = {"marked": len(rows), "unknown": len(out["unknown"]),
                      **{k: sum(1 for r in rows if r["state"] == k) for k, _l, _t in STATES}}

    def keep(r):
        if want_state and r["state"] != want_state:
            return False
        if want_platform and r["platform"] != want_platform:
            return False
        return not q or q in r["name"].lower() or q in r["address"].lower() \
            or q in r["dpid"].lower()
    shown = [r for r in rows if keep(r)]
    out["shown"] = len(shown)
    out["groups"] = [{"state": k, "label": label, "tone": tone,
                      "rows": [r for r in shown if r["state"] == k][:GROUP_SHOWN],
                      "count": sum(1 for r in shown if r["state"] == k)}
                     for k, label, tone in STATES if any(r["state"] == k for r in shown)]
    out["rows"] = shown
    out["templates"] = templates_card(network, rows)
    return out


def _record_words(rec) -> dict:
    if not rec:
        return {}
    return {"id": rec.get("id", ""), "at": rec.get("at", ""), "actor": rec.get("actor", ""),
            "outcome": rec.get("outcome", ""), "error": rec.get("error", ""),
            "export_sha256": rec.get("export_sha256", ""),
            "verify": [c.get("words", "") for c in (rec.get("verify") or {}).get("checks") or []]}


# --------------------------------------------------------------------------- the templates card

#: The most captures one template's picker offers (newest first).
CAPTURES_OFFERED = 20


def fitting_captures(drivers: list, earlier: str, caps: list) -> dict:
    """The captures a template for *drivers* is confirmed against, out of *caps*
    (`discovery.captures`, newest first), and the one its picker starts on (C3012; the
    charter: a picker's default fits the question asked, never the newest item of any kind).

    A template's lines are configuration, so the capture that answers "does this syntax fit
    this release" is one of the device's configuration read (`discovery.config_command`, per
    driver); and where the network confirmed the template before (*earlier*: that
    confirmation's capture name, kept when the template has changed since), of the command
    that capture was of. ``{"commands": [the commands, the earlier confirmation's first],
    "offered": [captures of them, newest first], "default": the name of the newest capture of
    the first of those commands that has one, "others": how many captures of the drivers'
    devices are of another command}``."""
    from modules import discovery

    mine = [c for c in caps if c.get("driver") in drivers and not c.get("archived")]
    parts = str(earlier or "").split("/")
    was = parts[1] if len(parts) == 3 else ""
    slugs, commands = [], []

    def want(slug, command):
        if slug and slug not in slugs:
            slugs.append(slug)
            commands.append(command)
    # The earlier confirmation's command, said as a capture of it names it (its slug alone
    # is in the confirmation; a capture of it gives the command's own words).
    want(was, next((c["command"] for c in mine
                    if discovery.command_slug(c.get("command")) == was),
                   was.replace("_", " ")))
    for d in drivers:
        command = discovery.config_command(d)
        want(discovery.command_slug(command), command)
    fits = [c for c in mine if discovery.command_slug(c.get("command")) in slugs]
    default = ""
    for slug in slugs:
        default = next((c["name"] for c in fits
                        if discovery.command_slug(c.get("command")) == slug), "")
        if default:
            break
    return {"commands": commands,
            "offered": [{k: c.get(k) for k in ("name", "device", "command", "at")}
                        for c in fits[:CAPTURES_OFFERED]],
            "default": default, "others": len(mine) - len(fits)}


def templates_card(network: str, rows: list) -> list:
    """Each template that renders, with the network's switches on it, its status, and the
    captures a person may confirm it against: those of the command it is confirmed against
    (`fitting_captures`), newest first, the picker starting on the newest. ``captures_error``
    says why the network's reads could not be read, apart from a network that holds no such
    capture (absent and unreadable are different states)."""
    from modules import discovery
    from modules.sdn import openflow_templates as T

    caps, error = [], ""
    try:
        got = discovery.captures(network)
        caps = got.get("captures") or []
        if got.get("unreadable"):
            n = len(got["unreadable"])
            error = (f"{n} of {network}'s saved reads could not be read "
                     f"({', '.join(got['unreadable'][:3])}{', …' if n > 3 else ''})")
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.warning("sdn switches: %s's captures could not be read: %s", network, exc)
        error = f"{network}'s saved reads could not be read ({type(exc).__name__}: {exc})"[:300]
    out = []
    for name in T.names():
        t = T.load(name)
        if t.get("support") == "unknown":
            continue
        status = T.status(network, name)
        fit = fitting_captures(t.get("drivers") or [], status.get("capture", ""), caps)
        out.append({"name": name, "family": t.get("family", ""),
                    "switches": [r["name"] for r in rows if r["platform"] == name],
                    "status": status, "captures": fit["offered"],
                    "capture_default": fit["default"],
                    "capture_commands": fit["commands"], "capture_others": fit["others"],
                    "captures_error": error,
                    "ipv6": bool(t.get("ipv6_controller")),
                    "vendor_driver": name == "ovs" or name in _cli_names()})
    return out


def _cli_names():
    from modules.sdn import openflow_cli
    return set(openflow_cli.DRIVERS)


def template_preview(network: str, name: str, capture_name: str) -> dict:
    """The confirm card: the template's lines (each with its citation and why) beside the
    capture's masked text, and the two hashes the confirm binds. Writes nothing."""
    from modules import discovery
    from modules.sdn import openflow_templates as T

    if name not in T.names():
        return {"state_card": "refused", "network": network, "template": name,
                "error": f"no OpenFlow template is named {name!r}"}
    t = T.load(name)
    cap = discovery.capture(network, capture_name)
    if cap is None:
        return {"state_card": "refused", "network": network, "template": name,
                "error": f"{network} holds no capture named {capture_name!r}"}
    if cap["driver"] not in (t.get("drivers") or []):
        return {"state_card": "refused", "network": network, "template": name,
                "error": (f"the capture {capture_name} was read with {cap['driver']}, and the "
                          f"{name} template is for {', '.join(t.get('drivers') or [])}")}
    return {"state_card": "preview", "network": network, "template": name,
            "family": t.get("family", ""),
            "lines": [{k: line.get(k) for k in ("text", "cite", "why", "when")}
                      for line in t.get("lines") or []],
            "capture": {k: cap.get(k) for k in ("name", "device", "driver", "command", "at",
                                                 "sha256", "text")},
            "template_sha256": T.sha256(name), "status": T.status(network, name)}


# --------------------------------------------------------------------------- configure

def batch_hash(plans: list) -> str:
    """The confirm's one hash over every switch's plan hash (sorted by switch)."""
    body = json.dumps(sorted((p["device"], p["hash"]) for p in plans), sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def configure_preview(network: str, devices: list, *, session=None) -> dict:
    """The preview card for *devices*: each switch's plan (`openflow_config.plan`), its exact
    program and undo, the export it read, the hash; a switch on a draft template or whose plan
    refused is named and not sent. Writes nothing."""
    from modules.sdn import openflow_config as OC
    from modules.sdn import openflow_templates as T

    plans, skipped, exports = [], [], set()
    for name in devices:
        p = OC.plan(network, name, session=session)
        status = p.get("status") or {}
        entry = {"device": name, "template": p.get("template", ""),
                 "family": p.get("family", ""),
                 "program": p.get("program") or [],
                 "undo": p.get("undo") or "", "hash": p.get("hash", ""),
                 # Each value the program changes, before and after, and where each value it
                 # was built from came from: the plan's own (`openflow_config` module).
                 "changes": p.get("changes") or [], "unchanged": p.get("unchanged"),
                 "built": OC.built_from(network, p.get("source")),
                 "defaults": p.get("defaults") or [], "excluded": p.get("excluded") or [],
                 "version": p.get("version", ""),
                 # What Verify checks on this family beyond the two checks the card names
                 # (an Arista's bound interfaces read back, C2779).
                 "verify_also": p.get("verify_also") or []}
        if p.get("export_sha256"):
            exports.add(p["export_sha256"])
        if not p.get("ok"):
            skipped.append({"device": name, "why": p.get("error", "")})
        elif status.get("status") != T.CONFIRMED:
            skipped.append({"device": name,
                            "why": (f"not sent: its template {entry['template']} is a draft on "
                                    f"{network} ({status.get('why', '')})")})
        else:
            plans.append(entry)
    return {"state_card": "preview" if plans else "nothing", "network": network,
            "plans": plans, "skipped": skipped, "hash": batch_hash(plans) if plans else "",
            "exports": sorted(exports)}


def configure_apply(network: str, pairs: list, confirmed: str, *, actor: str,
                    actor_verified: str, session=None, driver=None) -> dict:
    """Apply each previewed switch (*pairs*: ``[(device, its plan hash)]``) as *actor*, bound
    to *confirmed* (`batch_hash` of the pairs); each switch's own apply plans again and
    compares its hash. One after another: a switch's result never waits on another's."""
    from modules.sdn import openflow_config as OC

    got = batch_hash([{"device": d, "hash": h} for d, h in pairs])
    if not pairs or got != confirmed:
        return {"state_card": "refused", "network": network,
                "error": (f"the confirm's switches hash to {got[:12]}, and the preview's hash was "
                          f"{str(confirmed)[:12] or 'none'}: preview again")}
    results = []
    for device, h in pairs:
        out = OC.apply(network, device, h, actor=actor, actor_verified=actor_verified,
                       session=session, driver=driver)
        results.append(result_row(network, device, out))
    ok = sum(1 for r in results if r["outcome"] == "verified")
    level = "ok" if ok == len(results) else ("danger" if ok == 0 else "warn")
    return {"state_card": "result", "network": network, "results": results, "ok": ok,
            "level": level, "total": len(results)}


def result_row(network: str, device: str, out: dict) -> dict:
    """One switch's row of the result card from its apply's answer *out*
    (`openflow_config.apply`): what was sent (in words, and the lines themselves), each value
    before and after, Verify's checks with how long they took, the outcome, and what the plan
    was built from. ``as_intended``: the plan found nothing to change and nothing was sent.
    The changes are drawn only when something was sent: a refused run changed nothing."""
    from modules.sdn import openflow_config as OC

    plan = out.get("plan") or {}
    sent = out.get("sent") or []
    verify = out.get("verify") or {}
    checks = verify.get("checks") or []
    # The lines as they were sent: a vendor switch's program, Open vSwitch's one command.
    lines = [s["command"] for s in sent if s.get("command")] or \
        (list(plan.get("program") or []) if sent else [])
    return {"device": device, "outcome": out.get("outcome", "refused"),
            "error": out.get("error", ""), "id": out.get("id", ""),
            "sent_words": OC.sent_words(sent), "sent_lines": lines,
            "as_intended": bool(plan.get("unchanged")) and not sent
            and out.get("outcome") in ("verified", "unverified"),
            "changes": list(plan.get("changes") or []) if sent else [],
            "built": OC.built_from(network, plan.get("source")),
            "verify": checks,
            "verify_passed": sum(1 for c in checks if c.get("state") == "pass"),
            "verify_seconds": verify.get("seconds"), "verify_at": verify.get("at", ""),
            "dpid": verify.get("dpid") or "",
            "rollback": out.get("rollback") or {},
            "saved": out.get("saved"), "save_words": out.get("save_words", ""),
            "recorded": (out.get("record") or {}).get("ok", False)}
