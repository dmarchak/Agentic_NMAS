"""nsot/context.py

``build_render_context(device_name)`` — the single way a template gets data.

The pipeline, render previews, the onboarding wizard, and the AI tools all go
through here, so there is exactly one definition of what a template can see.

```python
{
  "device":     {...},   # full NetBox device, including rendered config_context
  "interfaces": [...],   # NetBox interfaces, each with ip_addresses
  "site":       {...},
  "vars":       {},      # merged YAML — Phase 3; empty until then
  "params":     {...},   # operator inputs for this run
}
```

Two defects this fixes:

* ``_compact_device`` carries ``local_context_data`` but not the **merged**
  ``config_context``, which is the field NetBox actually renders for a device.
* Pipeline stage 1 fetched interfaces and stage 2 threw them away, reading only
  ``["device"]``. Templates never saw an interface or an IP address.

``_compact_device`` stays lean — it feeds AI tool payloads where size matters.
The full records are fetched here instead.
"""

import logging

log = logging.getLogger(__name__)


def _fetch_full_device(session, base: str, device_name: str):
    """Full NetBox device record including its rendered config_context."""
    from modules.netbox_client import _nb_get, _resolve_device

    device = _resolve_device(session, base, device_name)
    if not device:
        return None

    # ?include=config_context asks NetBox to render the merged context, which is
    # the whole point of config contexts and is absent from the plain record.
    try:
        full = _nb_get(session, base, "dcim/devices/", id=device["id"],
                       include="config_context")
        if full:
            return full[0]
    except Exception as exc:                  # noqa: BLE001
        log.debug("nsot.context: config_context fetch failed for %s: %s",
                  device_name, exc)
    return device


def _fetch_interfaces(session, base: str, device_id: int) -> list:
    """Interfaces for a device, each carrying its assigned IP addresses."""
    from modules.netbox_client import _nb_get

    interfaces = _nb_get(session, base, "dcim/interfaces/", device_id=device_id)
    addresses = _nb_get(session, base, "ipam/ip-addresses/", device_id=device_id)

    by_interface: dict = {}
    for addr in addresses:
        assigned = addr.get("assigned_object") or {}
        iface_id = assigned.get("id")
        if iface_id:
            by_interface.setdefault(iface_id, []).append({
                "address": addr.get("address", ""),
                "family":  (addr.get("family") or {}).get("value")
                           if isinstance(addr.get("family"), dict) else addr.get("family"),
                "vrf":     (addr.get("vrf") or {}).get("name", ""),
                "status":  (addr.get("status") or {}).get("value", ""),
                "description": addr.get("description", ""),
            })

    for iface in interfaces:
        iface["ip_addresses"] = by_interface.get(iface["id"], [])
    return interfaces


def build_render_context(device_name: str, params: dict = None) -> dict:
    """Build the render context for *device_name*.

    Returns ``{"ok": bool, "error": str, "context": {...}}``. Never raises: a
    template render must fail with a message, not a traceback.
    """
    context = {"device": {}, "interfaces": [], "site": {}, "vars": {},
               "params": dict(params or {})}

    from modules.netbox_client import _nb_ready

    ok, err, session, base = _nb_ready()
    if not ok:
        return {"ok": False, "error": err, "context": context}

    try:
        device = _fetch_full_device(session, base, device_name)
        if not device:
            return {"ok": False,
                    "error": (f"Device '{device_name}' not found in NetBox by exact "
                              "name or by assigned IP address"),
                    "context": context}

        context["device"] = device
        context["interfaces"] = _fetch_interfaces(session, base, device["id"])

        site_ref = device.get("site") or {}
        if site_ref.get("id"):
            from modules.netbox_client import _nb_get
            sites = _nb_get(session, base, "dcim/sites/", id=site_ref["id"])
            context["site"] = sites[0] if sites else site_ref

        # context["vars"] stays empty until Phase 3 introduces host_vars and
        # group_vars. Templates written now can reference it safely.
        log.debug("nsot.context: built context for %s — %d interface(s)",
                  device_name, len(context["interfaces"]))
        return {"ok": True, "error": "", "context": context}

    except Exception as exc:                  # noqa: BLE001
        log.exception("nsot.context: failed to build context for '%s'", device_name)
        return {"ok": False, "error": str(exc), "context": context}
