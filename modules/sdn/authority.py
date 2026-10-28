"""Management authority per device (PHASE8_PLAN 17.1 S12): ``direct`` (Mercury configures it)
or ``controller`` (only through its SDN controller). Every route that configures a device
directly refuses a controller-managed one, naming its controller, before the route runs
(`route_gates.enforce` calls `check_request` after the identity gate). Deterministic.

**Which devices are controller-managed.** A device whose inventory record names an OpenFlow
platform: its ``platform`` (or ``device_type``) begins with ``openflow``, as 17.1's
integration writes it, ``openflow via <controller>``. Its controller is the name after
``via``; with none named, the network's one controller connection, or, with several,
"its controller" said as not named. Every other device is direct, and so is every device of a
network with no controller connection (nothing there could manage a device but Mercury, so
the check reads no inventory there).

**Which routes configure a device directly** (`DIRECT`): each endpoint, and where its request
names the device or devices:
- ``("view", key)``: the address's argument (`/v2/device/<name>/...`);
- ``("form", key)``: a form field, one device; ``("form_list", key)``: every value of it;
- ``("json_keys", key)``: the keys of a form field holding a JSON mapping by device (a batch's
  confirmations).
Every other confirm- or approve-gated route is in `NOT_DIRECT`, with why it configures no
inventory device (tests/test_sdn_authority.py holds the two to the gate table exactly).
"""

import json
import logging

log = logging.getLogger(__name__)

DIRECT = {
    # Sends to the device, from its page.
    "device_v2.deploy_confirm": ("view", "name"),
    "device_v2.restore_confirm": ("view", "name"),
    "device_v2.rotate_confirm": ("view", "name"),
    "device_v2.persist_confirm": ("view", "name"),
    "device_v2.reload_confirm": ("view", "name"),
    "device_v2.rekey_confirm": ("view", "name"),
    "privileged_v2.confirm": ("view", "name"),
    "onboard_v2.verify": ("view", "name"),
    # Records what the device holds, or what Mercury will send it (its golden and intent).
    "device_v2.capture_confirm": ("view", "name"),
    "device_v2.seed_confirm": ("view", "name"),
    "device_v2.revert_confirm": ("view", "name"),
    "device_v2.retry_confirm": ("view", "name"),
    "intent_v2.commit": ("view", "name"),
    "intent_v2.words_commit": ("view", "name"),
    "v2.decline_confirm": ("form", "device"),
    # Batches over named devices.
    "v2.save_confirm": ("form_list", "device"),
    "bulk_intent_v2.apply": ("form_list", "device"),
    "v2.profile_apply_confirm": ("json_keys", "confirmations"),
    "v2.pair_apply_confirm": ("json_keys", "confirmations"),
    "v2.history_reapply_confirm": ("json_keys", "confirmations"),
}

NOT_DIRECT = {
    "device_v2.retire_confirm": "retirement removes Mercury's records of the device; a "
                                "controller-managed switch is retired the same way",
    "onboard_v2.create": "a device being created has no inventory record yet",
    "onboard_v2.abandon": "abandoning removes a pending device's records; nothing is sent",
    "adopt_v2.confirm": "adoption names an address, not an inventory device",
    "oob_onboard_v2.confirm": "out-of-band onboarding names a console port, not an inventory "
                              "device",
    "console_ztp_v2.survey_confirm": "a console survey names a NetBox device id on a console "
                                     "port, before it is in the inventory",
    "console_ztp_v2.kickstart_confirm": "a kick-start names a NetBox device id on a console "
                                        "port, before it is in the inventory",
    "console_servers_v2.rekey_confirm": "a console server is not an inventory device",
    "credential_profiles_v2.rotate_due_confirm": "the due list is computed from the "
                                                 "inventory's credentials; a controller-managed "
                                                 "switch has no login credential to rotate",
    "dhcp_v2.exclusion_confirm": "changes Kea, not a device",
    "dhcp_v2.lease_confirm": "changes Kea, not a device",
    "dhcp_v2.reservation_confirm": "changes Kea, not a device",
    "dhcp_v2.subnet_confirm": "changes Kea, not a device",
    "update.apply": "updates the app, not a device",
    "update.step_done": "records a host step, not a device",
    "netbox_v2.confirm": "writes NetBox's records, not a device",
    "templates_v2.approve": "changes a template's approval, not a device",
    "templates_v2.revoke": "changes a template's approval, not a device",
    "templates_v2.seed": "changes the template library, not a device",
    "templates_v2.bindings_apply": "changes which template renders which device; nothing is "
                                   "configured until a deploy, which is refused",
    "templates_v2.edit_commit": "changes a template, not a device",
    "templates_v2.bring": "changes a template, not a device",
    "v2.profile_propose_commit": "changes the network's monitoring profile, not a device",
    "v2.ip_sla_policy_set": "changes the network's IP SLA policy, not a device",
    "v2.ip_sla_commit": "commits suggested probes for the devices the suggestion names, each a "
                        "Cisco device the profile chose; nothing is sent",
    # Mercury's own SDN operations go THROUGH the controller: they are the authority's path.
    "sdn_v2.flow_confirm": "changes flows through the switch's controller, the authority's "
                           "own path",
    "sdn_v2.response_confirm": "answers a threat through the switch's controller, the "
                               "authority's own path",
    "sdn_v2.reapply_confirm": "puts a lost response back through the switch's controller, the "
                              "authority's own path (C2018)",
}


def _connections(network: str) -> list:
    try:
        from modules.sdn import connections

        got = connections.connections(network)
        return got.get("connections") or [] if got.get("ok") else []
    except Exception:                                 # noqa: BLE001 (a name only)
        return []


def of(device: dict, network: str = "", conns=None) -> dict:
    """*device*'s management authority: ``{"kind": "direct"|"controller", "controller",
    "words"}``."""
    text = " ".join(str((device or {}).get(k) or "") for k in ("platform", "device_type"))
    first = next((str((device or {}).get(k) or "").strip() for k in ("platform", "device_type")
                  if str((device or {}).get(k) or "").strip().lower().startswith("openflow")),
                 "")
    if not first:
        return {"kind": "direct", "controller": "", "words": "Mercury configures it directly"}
    _, via, named = first.partition(" via ")
    controller = named.strip() if via else ""
    if not controller:
        found = conns if conns is not None else _connections(network)
        controller = found[0].get("name", "") if len(found) == 1 else ""
    name = (device or {}).get("hostname") or "the device"
    said = controller or "its controller (none is named on its record)"
    return {"kind": "controller", "controller": controller, "platform": text.strip(),
            "words": (f"Refused: {name} is managed by its controller, {said}; Mercury does not "
                      "configure it directly. Its flows are changed through the controller "
                      "(SDN › Flows and SDN › Responses).")}


def names_in(request, how: tuple) -> list:
    """The device names a request carries, where *how* says (`DIRECT`'s values)."""
    where, key = how
    if where == "view":
        value = (request.view_args or {}).get(key)
        return [str(value)] if value else []
    if where == "form":
        value = (request.form.get(key) or "").strip()
        return [value] if value else []
    if where == "form_list":
        return [v.strip() for v in request.values.getlist(key) if v.strip()]
    if where == "json_keys":
        try:
            got = json.loads(request.form.get(key) or "{}")
        except ValueError:
            return []
        return [str(k) for k in got] if isinstance(got, dict) else []
    return []


def refusal(network: str, names: list, devices: list) -> dict:
    """The refusal for the first of *names* that is controller-managed in *devices* (the
    network's inventory rows), or None."""
    wanted = {n.lower() for n in names}
    for dev in devices or []:
        if (dev.get("hostname") or "").lower() not in wanted:
            continue
        auth = of(dev, network)
        if auth["kind"] == "controller":
            return {"ok": False, "outcome": "controller_managed", "error": auth["words"],
                    "device": dev.get("hostname"), "controller": auth["controller"]}
    return None


def check_request(request) -> dict:
    """`route_gates.enforce`'s check: for a `DIRECT` endpoint, the refusal naming the
    controller of the first controller-managed device the request names, else None. Reads the
    network's inventory once, only for those endpoints."""
    how = DIRECT.get(request.endpoint or "")
    if how is None:
        return None
    names = names_in(request, how)
    if not names:
        return None
    from modules.device import load_saved_devices
    from modules.nsot import listref
    from routes.list_param import named_list

    network = (request.form.get("list") or "").strip() or named_list(request)
    try:
        ref = listref.resolve(network) if network and listref.exists(network) else \
            listref.active()
        # A network with no controller connection has nothing that could manage a device but
        # Mercury: its inventory is not read (the cost of this check is then one settings
        # read).
        if not _connections(ref.name):
            return None
        devices = load_saved_devices(ref.csv_path)
    except Exception as exc:                          # noqa: BLE001 (the route decides)
        log.warning("sdn authority: the inventory could not be read (%s)", type(exc).__name__)
        return None
    return refusal(ref.name, names, devices)
