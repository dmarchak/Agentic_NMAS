"""What a device's ENVIRONMENT owns, read from NetBox (C663 step 3, the operator, 2026-10-11).

Some devices boot inside something that configures part of them before Mercury does: an
emulator that addresses a management port of its own and injects its own account, say. Those
are facts about where a device runs, not about its platform: a real C8000v has no injected
user and no emulator-owned port. So they are read like any other NetBox fact, per device,
and **a device with none has none**:

* **The environment's management interfaces** are the device's interfaces NetBox marks
  management-only (`mgmt_only`). The address the manager reaches the device on never goes on
  one, and an interface the config gives the platform's own management address must be one.
* **The environment's own lines** are the device's config context key
  `environment_owned_lines`: configuration lines the environment puts on the device itself
  (a NetBox config context assigned by a tag, for example). A `username` line among them
  means an account is injected ahead of the device's own config, so a bootstrap config uses
  the form that account accepts beside it (`password`, never `secret`); an `ip ssh` or
  `crypto key` line means the environment brings SSH up, so the bootstrap does not generate a
  key it would be using.

NetBox not configured, or the device not in it, is an empty environment, said by its source.
A NetBox that is configured and cannot be read RAISES (`EnvironmentUnreadable`): "could not
read" is not "nothing there", and a bootstrap config built on a guess is the one a device
boots and is unreachable on.

**The record itself comes with it** (C676, the operator, 2026-10-11): a device a person made
in NetBox as Planned is onboarded from that record, so its status, site, role (and the role's
`mercury_kind`), platform and tags are read here, in the same read, for onboarding to judge
(`netbox`); the record's id is recorded, so phase 2 updates that record and never makes a
second.
"""

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

#: The config context key holding the environment's own lines.
CONTEXT_KEY = "environment_owned_lines"


class EnvironmentUnreadable(Exception):
    """NetBox is configured and the device's environment could not be read from it."""


@dataclass(frozen=True)
class Environment:
    #: canonical interface name -> why the manager's address may not go there
    reserved: dict = field(default_factory=dict)
    #: the environment's own configuration lines, verbatim
    owned_lines: tuple = ()
    #: where this was read, in words ("NetBox device r6 (id 12)", "not in NetBox", ...)
    source: str = "none given"
    #: NetBox's record of the device, when it holds one: ``{id, status, status_label, site,
    #: role, role_name, role_kind, platform, platform_name, tags, url}`` (`_record`); empty
    #: when NetBox holds none or is not configured
    netbox: dict = field(default_factory=dict)

    @property
    def injects_user(self) -> bool:
        return any(line.split()[:1] == ["username"] for line in self.owned_lines)

    @property
    def owns_ssh(self) -> bool:
        return any(line.startswith(("ip ssh", "crypto key")) for line in self.owned_lines)

    @property
    def management_interfaces(self) -> list:
        return sorted(self.reserved)

    def record(self) -> dict:
        """What a render used, to be recorded beside it and rebuilt for a re-render that must
        be byte-identical (`from_record`). Derived facts only, never the lines themselves: an
        injected account's line carries its password."""
        return {"source": self.source, "injects_user": self.injects_user,
                "owns_ssh": self.owns_ssh, "management_interfaces": self.management_interfaces,
                # Not read by a render: the record phase 2 updates (C676).
                "netbox_id": self.netbox.get("id"), "netbox_status": self.netbox.get("status")}

    @classmethod
    def from_record(cls, rec: dict) -> "Environment":
        """The environment a recorded render used. Its lines are stand-ins carrying only the
        two facts the render reads from them."""
        rec = rec or {}
        lines = ((("username <injected>",) if rec.get("injects_user") else ())
                 + (("ip ssh <environment>",) if rec.get("owns_ssh") else ()))
        return cls(reserved={n: "recorded at onboarding as the environment's own management "
                                "interface" for n in rec.get("management_interfaces") or []},
                   owned_lines=lines,
                   source=f"recorded at onboarding ({rec.get('source') or 'none given'})")


#: No environment: every rule falls back to what a device on its own would need.
NONE = Environment()


def _reason(name: str) -> str:
    return (f"NetBox marks {name} management-only (mgmt_only): it is the environment's own "
            "management interface")


def read(hostname: str, *, ready=None) -> Environment:
    """The environment NetBox records for *hostname*. *ready* replaces
    `netbox_client._nb_ready` (tests)."""
    from modules.netbox_client import _nb_get, _nb_ready
    from modules.nsot.ifnames import canonical

    ok, _err, session, base = (ready or _nb_ready)()
    if not ok:
        return Environment(source="NetBox is not configured")
    try:
        hits = [d for d in _nb_get(session, base, "dcim/devices", name=hostname)
                if d.get("name") == hostname]
    except Exception as exc:                      # noqa: BLE001
        raise EnvironmentUnreadable(f"NetBox could not be asked for {hostname}: {exc}") from exc
    if not hits:
        return Environment(source=f"{hostname} is not in NetBox")
    if len(hits) > 1:
        raise EnvironmentUnreadable(
            f"NetBox holds {len(hits)} devices named {hostname} (ids "
            + ", ".join(str(d.get("id")) for d in hits) + "), so none is read")
    dev_id = hits[0].get("id")
    try:
        r = session.get(f"{base}/api/dcim/devices/{dev_id}/", timeout=15)
        r.raise_for_status()
        detail = r.json() or {}
        mgmt = _nb_get(session, base, "dcim/interfaces", device_id=dev_id, mgmt_only=True)
        role_id = (detail.get("role") or detail.get("device_role") or {}).get("id")
        role = {}
        if role_id:
            rr = session.get(f"{base}/api/dcim/device-roles/{role_id}/", timeout=15)
            rr.raise_for_status()
            role = rr.json() or {}
    except Exception as exc:                      # noqa: BLE001
        raise EnvironmentUnreadable(
            f"NetBox's record of {hostname} (id {dev_id}) could not be read: {exc}") from exc
    lines = (detail.get("config_context") or {}).get(CONTEXT_KEY) or []
    if not isinstance(lines, list) or not all(isinstance(l, str) for l in lines):
        raise EnvironmentUnreadable(
            f"{hostname}'s config context `{CONTEXT_KEY}` is not a list of lines")
    reserved = {canonical(i["name"]): _reason(i["name"]) for i in mgmt
                if i.get("mgmt_only") and i.get("name")}
    return Environment(reserved=reserved,
                       owned_lines=tuple(l.strip() for l in lines if l.strip()),
                       source=f"NetBox device {hostname} (id {dev_id})",
                       netbox=_record(base, detail, role))


def _record(base: str, detail: dict, role: dict) -> dict:
    """The facts onboarding judges a NetBox record by (C676)."""
    from modules.inventory.role_kind import FIELD, KINDS

    status = detail.get("status") or {}
    if not isinstance(status, dict):
        status = {"value": status}
    site = detail.get("site") or {}
    platform = detail.get("platform") or {}
    kind = str((role.get("custom_fields") or {}).get(FIELD) or "").strip().lower()
    return {"id": detail.get("id"),
            "status": str(status.get("value") or "").lower(),
            "status_label": str(status.get("label") or status.get("value") or "none"),
            "site": site.get("name") or site.get("display") or "",
            "role": role.get("slug") or "", "role_name": role.get("name") or "",
            "role_kind": kind if kind in KINDS else "",
            "platform": platform.get("slug") or "",
            "platform_name": platform.get("name") or platform.get("display") or "",
            "tags": sorted(t.get("name") or t.get("slug") or "" for t in detail.get("tags") or []),
            "url": f"{base.rstrip('/')}/dcim/devices/{detail.get('id')}/"}
