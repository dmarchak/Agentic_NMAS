"""What a feature may send off the host, by class (PHASE8_PLAN 15.11): allowed, topology,
configuration, never. The gateway's egress mask (`redact.egress_payload`) covers every byte
sent, whatever its class; this module decides which classes a feature puts in the request at
all, before the gateway is asked.

**The topology class** (the operator's egress ruling, 2026-10-25): the network context model's
slice (modules/network_model.py): devices, roles, sites, platforms, links with their subnets,
expected and observed adjacencies; no configuration line, no secret. **On by default** wherever
hosted AI is on; an admin turns it off per network with the network setting
`ai_topology_class` (scope `network`, a group of one; false is off). A setting that cannot be
read is off: what leaves the host is decided closed, never open.

**A classification marking forces AI off whatever the class settings say** (13.1). No marking
exists yet (planned, C1720, a public-release blocker): `classification_marking` is the
named seam every class decision asks first, and it answers "" (unmarked) until the marking is
built. Explain asks it before anything else and sends nothing for a marked network.
"""
import logging

log = logging.getLogger(__name__)

TOPOLOGY_SETTING = "ai_topology_class"


def classification_marking(network: str) -> str:
    """The network's classification marking, or "" when it carries none. A NO-OP SEAM: no
    marking is stored anywhere yet, so every network reads as unmarked. When the marking is
    built, it answers here and every feature asking (Explain today) refuses to send anything."""
    del network
    return ""


def topology_allowed(network: str) -> dict:
    """``{"allowed": bool, "why": str}``: whether a call about *network* may carry the
    topology class. Off when the network carries a classification marking, when an admin turned
    the class off for it, or when its setting cannot be read; on otherwise (the default)."""
    from modules import list_settings

    if not network:
        return {"allowed": False, "why": "no one network is named, so no network model is read"}
    marked = classification_marking(network)
    if marked:
        return {"allowed": False, "why": f"{network} carries the classification marking "
                f"{marked!r}, which forces AI off"}
    try:
        value = list_settings.value(network, TOPOLOGY_SETTING, True)
    except Exception as exc:                            # noqa: BLE001 (closed, and said)
        log.warning("egress: %s's %s could not be read (%s); the topology class is off",
                    network, TOPOLOGY_SETTING, exc)
        return {"allowed": False, "why": f"{network}'s {TOPOLOGY_SETTING} could not be read "
                f"({type(exc).__name__}), so the topology class is off"}
    if value is not True:
        return {"allowed": False, "why": f"the topology class is off for {network} "
                f"({TOPOLOGY_SETTING}, an admin's setting)"}
    return {"allowed": True, "why": ""}
