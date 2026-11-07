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

**The device state class** (the operator, N20; HEAL_TO_INTENT 19.5, H28): the answers to the AI
read set's show commands, operational state and never configuration, masked, a secret-shaped
line dropped whole (`read_loop`). **Off by default on every network**, and each network's own
(`settings_scope.OWN_ONLY`: Default's must not turn it on for every network that inherits).
An admin (a verified person; Mercury holds no roles yet, so every verified person is one)
turns it on for one network with a reason of at least three words (`turn_on_device_state`),
written with who, how verified, when and why (`ai_device_state_on`) and recorded in the
network's settings record; off is one press, no confirm, effective at once
(`turn_off_device_state`), recorded too. **Fails closed** (`device_state_allowed`): on only when
the switch is true AND the record of who turned it on, with a reason, is in force; a hand edit
of the switch alone, an unreadable setting, or a classification marking is off. Written only
here (`settings_scope.CARDLESS`); drawn on the network's Settings › Network tab, "What AI may
send" (board H, artboard N).

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


# ── The device state class (N20, H28) ───────────────────────────────────────────────────────

DEVICE_STATE_SETTING = "ai_device_state_class"
DEVICE_STATE_ON = "ai_device_state_on"
DEVICE_STATE_GROUP = "ai_device_state"
#: A reason to turn it on: at least this many words (board N: "at least three words", the
#: dangerous lines' and Show commands' rule).
REASON_WORDS = 3
#: The record kinds written in the network's settings record.
ON_KIND, OFF_KIND = "ai_device_state_on", "ai_device_state_off"
LOCK_NAME = ".ai_device_state.lock"
#: What turning it off does, said in its answer.
OFF_EFFECT = ("no read answer leaves the host for this network from now on: the AI analysis's "
              "reads are not asked, and its first pass is the whole analysis")


class DeviceStateRefused(ValueError):
    """The device state class was not changed; the words say why, naming both operands."""


def _lock(network: str):
    import os

    from modules.config import list_data_path
    from modules.filestore import PathLock

    return PathLock(lambda: os.path.join(list_data_path(network), LOCK_NAME))


def _iso(epoch: float) -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def device_state(network: str) -> dict:
    """The class's stored state for *network*: ``{"state": "on"|"off"|"unreadable",
    "switch", "on_record", "why"}``. ``on`` only when the switch is true and the record of who
    turned it on, with a reason, is in force; anything else is off (fails closed)."""
    from modules import list_settings

    if not network:
        return {"state": "unreadable", "switch": False, "on_record": {},
                "why": "no one network is named"}
    try:
        switch = list_settings.value(network, DEVICE_STATE_SETTING, False)
        record = list_settings.value(network, DEVICE_STATE_ON, {}) or {}
    except Exception as exc:                            # noqa: BLE001 (closed, and said)
        log.warning("egress: %s's %s could not be read (%s); the device state class is off",
                    network, DEVICE_STATE_SETTING, exc)
        return {"state": "unreadable", "switch": False, "on_record": {}, "why": (
            f"{network}'s {DEVICE_STATE_SETTING} could not be read ({type(exc).__name__}), "
            "so it is off")}
    record = record if isinstance(record, dict) else {}
    if switch is not True:
        return {"state": "off", "switch": False, "on_record": {}, "why": (
            f"off by default, and no admin has turned it on ({DEVICE_STATE_SETTING} is "
            f"{_shown(switch)})")}
    if not (record.get("by") and len(str(record.get("reason") or "").split()) >= REASON_WORDS):
        return {"state": "off", "switch": True, "on_record": record, "why": (
            f"{DEVICE_STATE_SETTING} is true, but {DEVICE_STATE_ON} names "
            f"{'a reason of fewer than three words' if record.get('by') else 'no one'}, so the "
            "switch is not in force: an admin turns it on from Settings with a reason")}
    return {"state": "on", "switch": True, "on_record": record, "why": ""}


def _shown(value) -> str:
    return "false" if value is False else ("unset" if value is None else repr(value))


def device_state_allowed(network: str) -> dict:
    """``{"allowed": bool, "why": str}``: whether a call about *network* may carry the
    device state class (the AI read set's answers). Off when the network carries a
    classification marking, by default, when an admin turned it off, when the switch is on
    with no record of who turned it on and why, or when its setting cannot be read."""
    if not network:
        return {"allowed": False, "why": "no one network is named, so no device is read"}
    marked = classification_marking(network)
    if marked:
        return {"allowed": False, "why": f"{network} carries the classification marking "
                f"{marked!r}, which forces AI off"}
    got = device_state(network)
    return {"allowed": got["state"] == "on", "why": got["why"]}


def _person(actor: str, actor_verified: str, person: bool, what: str) -> None:
    if not actor or actor_verified in ("", "none") or not person:
        raise DeviceStateRefused(
            f"{what} is an admin's decision, made by a verified person, and this request is "
            f"not one (actor {actor or 'none'}, verified {actor_verified or 'none'})")


def turn_on_device_state(network: str, reason: str, *, actor: str, actor_verified: str,
                         person: bool, now: float = None) -> dict:
    """Turn the device state class on for *network*, as a verified person with a reason,
    recorded with who, how verified, when and why. ``{"ok", "network", "at", "recorded",
    "record_error", "nothing"}``; raises `DeviceStateRefused` with nothing written."""
    import time

    from modules import list_settings as L

    _person(actor, actor_verified, person, "turning the device state class on")
    reason = " ".join((reason or "").split())
    if len(reason.split()) < REASON_WORDS:
        raise DeviceStateRefused(
            f"a reason of at least {REASON_WORDS} words turns device state on, and the reason "
            f"given has {len(reason.split())}; nothing was changed")
    if not network:
        raise DeviceStateRefused("device state is turned on for one network, and none was "
                                 "named")
    marked = classification_marking(network)
    if marked:
        raise DeviceStateRefused(f"{network} carries the classification marking {marked!r}, "
                                 "which forces every AI class off; nothing was changed")
    now = time.time() if now is None else now
    with _lock(network):
        before = device_state(network)
        if before["state"] == "unreadable":
            raise DeviceStateRefused(f"not turned on: {before['why']}")
        if before["state"] == "on":
            r = before["on_record"]
            return {"ok": True, "network": network, "nothing": True, "at": r.get("at", ""),
                    "recorded": False, "record_error": "",
                    "words": f"Device state is already on for {network}, turned on by "
                             f"{r.get('by')} at {r.get('at')}"}
        on = {"by": actor, "actor_verified": actor_verified, "at": _iso(now), "reason": reason}
        got = L.write(network, {DEVICE_STATE_SETTING: True, DEVICE_STATE_ON: on}, actor=actor)
        if not got.get("ok"):
            raise DeviceStateRefused(f"not turned on: {got.get('error')}")
    entry = L._record(network, {"kind": ON_KIND, "group": DEVICE_STATE_GROUP,
                                "written": [DEVICE_STATE_SETTING, DEVICE_STATE_ON],
                                "reason": reason, "actor": actor,
                                "actor_verified": actor_verified})
    log.info("egress: %s turned the device state class on for %s", actor, network)
    return {"ok": True, "network": network, "nothing": False, "at": on["at"],
            "recorded": entry.get("recorded", False),
            "record_error": entry.get("record_error", ""),
            "words": f"Device state turned on for {network} by {actor}"}


def turn_off_device_state(network: str, *, actor: str, actor_verified: str, person: bool,
                          now: float = None) -> dict:
    """The device state class off for *network* at once: one press, no confirm, recorded
    with who and when. Off already writes nothing and says so."""
    import time

    from modules import list_settings as L

    _person(actor, actor_verified, person, "turning the device state class off")
    if not network:
        raise DeviceStateRefused("device state is turned off for one network, and none was "
                                 "named")
    now = time.time() if now is None else now
    with _lock(network):
        before = device_state(network)
        if not before["switch"] and before["state"] != "unreadable":
            return {"ok": True, "network": network, "nothing": True, "at": _iso(now),
                    "recorded": False, "record_error": "",
                    "words": f"Device state is already off for {network}"}
        got = L.write(network, {DEVICE_STATE_SETTING: False, DEVICE_STATE_ON: {}},
                      actor=actor)
        if not got.get("ok"):
            raise DeviceStateRefused(f"not turned off: {got.get('error')}")
    entry = L._record(network, {"kind": OFF_KIND, "group": DEVICE_STATE_GROUP,
                                "written": [DEVICE_STATE_SETTING, DEVICE_STATE_ON],
                                "before": before["on_record"], "actor": actor,
                                "actor_verified": actor_verified})
    log.info("egress: %s turned the device state class off for %s", actor, network)
    return {"ok": True, "network": network, "nothing": False, "at": _iso(now),
            "recorded": entry.get("recorded", False),
            "record_error": entry.get("record_error", ""),
            "words": f"Device state turned off for {network} by {actor}: {OFF_EFFECT}"}


def classes_view(network: str) -> dict:
    """Board N's "What AI may send" card for *network*: ``{"network", "marked", "rows"}``,
    each row ``{"key", "name", "what", "state", "words", "detail"}`` in the board's order."""
    marked = classification_marking(network)
    topo = topology_allowed(network)
    ds = device_state(network)
    ds_words = {"on": "on", "off": "off", "unreadable": "off: cannot be read"}[ds["state"]]
    on = ds["on_record"] if ds["state"] == "on" else {}
    return {"marked": marked, "device_state_on": ds["state"] == "on", "rows": [
        {"key": "allowed", "name": "Allowed",
         "what": "alert labels, metric series, masked log lines, intent diffs",
         "state": "ok", "words": "on where AI is on", "detail": ""},
        {"key": "topology", "name": "Topology",
         "what": "the network model's slice: devices, links, adjacencies",
         "state": "ok" if topo["allowed"] else "muted",
         "words": "on" if topo["allowed"] else "off", "detail": topo["why"]},
        {"key": "device_state", "name": "Device state",
         "what": ("answers to the AI read set's show commands (state, not configuration), "
                  "masked, a secret-shaped line dropped whole"),
         "state": "ok" if ds["state"] == "on" and not marked else "muted",
         "words": "off: the classification marking" if marked else ds_words,
         "detail": (f"turned on by {on.get('by')} at {on.get('at')}: “{on.get('reason')}”"
                    if on else ds["why"])},
        {"key": "configuration", "name": "Configuration",
         "what": "configuration lines, through the configuration masking",
         "state": "muted", "words": "off: the classification marking is not built",
         "detail": "C1720"},
    ]}
