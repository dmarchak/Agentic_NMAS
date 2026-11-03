"""Each network's heal policy, its mode and the kill switch (board H, part H1;
docs/HEAL_TO_INTENT.md sections 6, 7, 9, 13 and 18). Deterministic; no device, no AI.

**The policy** is the network's settings group ``heal_policy`` (`POLICY_KEYS`): the mode, AUTO's
expiry, the Tier 1 kinds AUTO may heal, the Tier 2 kinds proposed, and the hard stops' values
(section 6). It is each network's own and never inherited from Default
(`settings_scope.OWN_ONLY`): enabling healing on Default must not enable it on every network
that inherits. Written only here (`settings_scope.CARDLESS`):
- **a change** (`plan`, then `apply`): previewed in the six parts (`preview_confirm.
  heal_policy_preview`), confirmed by the preview's fingerprint as a verified person with a
  reason; refused when the policy, the stage or the kill switch moved since the preview,
  naming both fingerprints and what moved. The confirmation is stored with the values
  (``heal_policy_confirmed``: who, how verified, when, the reason, the policy's fingerprint and
  AUTO's expiry) and recorded in the network's settings record with the values before and after;
- **Turn off** (`turn_off`): one press, no confirm, effective at once, recorded with who and
  when. A heal already applying finishes its own verify and rollback; nothing new starts.
  Turning a network back on is a change, previewed and confirmed by hash.

**The mode now** (`current`) fails closed, in section 6's order, each refusal naming what it
compared:
1. the installation's kill switch (``heal_stopped``) stopped, or unreadable: off;
2. the policy unreadable: off; the mode set off: off; values that are not the ones a person
   confirmed (a hand edit, or no confirmation at all): off, naming both fingerprints;
3. AUTO past its expiry: dry run (N8: never off, so the record keeps running), recorded once
   (`record_expiry`); AUTO on a network not marked lab (C2009's guard, `sdn.modes.stage`, until
   PHASE8_PLAN 17.7's gate is complete): dry run, suspended, naming the stage and the gate.

**AUTO's limits** (N8, the operator, 2026-11-03): only on a network marked lab, at most 7 days
per enablement (`MAX_AUTO_SECONDS`), expiring to dry run; it names at least one Tier 1 kind, and
a change allows at most one more (Tier 1 kinds are enabled one at a time). A kind's tier is a
ceiling in code (section 5): only `TIER1_KINDS` may be allowed AUTO, only `TIER2_KINDS`
proposed; Tiers 3 and 4 are not settings.

**Lab defaults** (N1, N3): on a network marked lab, a hard stop the network does not set reads
its lab default (`LAB_DEFAULTS`: a 120 s grace period and a 60-minute topology hold) in place of
the production default the schema holds (900 s, 240 minutes). Each value says which it is.

**The kill switch** (`stopped`, `stop`, `resume_plan`, `resume`): ``heal_stopped``, the
installation's. Stop is one press, no confirm, recorded with who, when and why in the
installation's settings record; resuming is previewed (every network's mode once resumed) and
confirmed by hash as a verified person with a reason.
"""

import calendar
import hashlib
import json
import logging
import os
import time

log = logging.getLogger(__name__)

GROUP = "heal_policy"
MODES = ("off", "dry_run", "auto")
MODE_WORDS = {"off": "off", "dry_run": "dry run", "auto": "AUTO"}
MODE_KEY = "heal_mode"
UNTIL_KEY = "heal_mode_until"
CONFIRMED_KEY = "heal_policy_confirmed"
KINDS_AUTO_KEY = "heal_kinds_auto"
KINDS_PROPOSE_KEY = "heal_kinds_propose"
KILL_KEY = "heal_stopped"

#: The fix kinds a policy may name, by tier (section 5). Tier 1 may be allowed AUTO, Tier 2 is
#: proposed for a person; Tiers 3 and 4 are never settings.
TIER1_KINDS = ("missing_line", "changed_line", "added_line", "admin_down")
TIER2_KINDS = ("process_reset", "qos_policy", "secret_added_back")
KIND_WORDS = {
    "missing_line": "a missing line", "changed_line": "a changed line, single-valued",
    "added_line": "an added line, a measured shape", "admin_down": "admin down where intent "
    "says up", "process_reset": "a fix that takes effect only through a process reset",
    "qos_policy": "a QoS policy", "secret_added_back": "a line in a secret position, added back",
}

#: The hard stops a network sets, in section 6's order, each with its unit.
GUARD_KEYS = ("heal_topology_hold_minutes", "heal_max_devices_drifting",
              "heal_person_working_changes", "heal_person_working_minutes",
              "heal_grace_seconds", "heal_max_per_device_hour", "heal_max_per_network_hour",
              "heal_repeat_halts_hours", "heal_max_removed_units", "heal_max_units")
GUARD_WORDS = {
    "heal_topology_hold_minutes": "a recent change holds healing for (minutes)",
    "heal_max_devices_drifting": "more devices than this drifting at once escalates",
    "heal_person_working_changes": "a person working: changes outside intent",
    "heal_person_working_minutes": "a person working: within (minutes)",
    "heal_grace_seconds": "a deviation must persist for (seconds)",
    "heal_max_per_device_hour": "heals per device an hour",
    "heal_max_per_network_hour": "heals per network an hour",
    "heal_repeat_halts_hours": "the same deviation healed twice within (hours) halts",
    "heal_max_removed_units": "removal units a heal",
    "heal_max_units": "sections a heal",
}
#: N1 and N3: on a network marked lab, a hard stop the network does not set reads these.
LAB_DEFAULTS = {"heal_grace_seconds": 120, "heal_topology_hold_minutes": 60}

#: Section 6, in order: the guard's number, its name, and the settings it reads (none: always
#: on). H3 checks them in this order and names the first that applies.
GUARDS = (
    (1, "the kill switch", (KILL_KEY,)),
    (2, "the network's mode", (MODE_KEY, UNTIL_KEY)),
    (3, "planned work", ()),
    (4, "the device's golden departs from its intent", ()),
    (5, "a recent change", ("heal_topology_hold_minutes",)),
    (6, "many devices at once", ("heal_max_devices_drifting",)),
    (7, "a person working", ("heal_person_working_changes", "heal_person_working_minutes")),
    (8, "the grace period", ("heal_grace_seconds",)),
    (9, "rate: per device", ("heal_max_per_device_hour",)),
    (10, "rate: per network", ("heal_max_per_network_hour",)),
    (11, "the same deviation healed twice", ("heal_repeat_halts_hours",)),
    (12, "the program's size", ("heal_max_removed_units", "heal_max_units")),
    (13, "the tier", (KINDS_AUTO_KEY, KINDS_PROPOSE_KEY)),
    (14, "a rolled-back heal", ()),
)

#: What a person confirms: everything of the group but the confirmation itself.
POLICY_KEYS = (MODE_KEY, UNTIL_KEY, KINDS_AUTO_KEY, KINDS_PROPOSE_KEY) + GUARD_KEYS

#: N8: AUTO is on for at most 7 days per enablement, then dry run.
MAX_AUTO_SECONDS = 7 * 24 * 3600
#: Where a network's preview and apply are serialised across processes.
LOCK_NAME = "heal_policy"
#: The record kinds this module writes in a network's settings record.
RECORD_KINDS = ("heal_policy", "heal_off", "heal_auto_expired")
#: And in the installation's.
INSTALL_RECORD_KINDS = ("heal_stopped", "heal_resumed")

#: Turn off's words: what it stops and what it lets finish (section 16).
OFF_EFFECT = ("nothing new starts; a heal already applying finishes its own verify and "
              "rollback")
#: Apply's steps, in order, for the manual's How it works page (H10).
APPLY_STEPS = ("check", "re-plan", "compare", "write", "record")
OFF_STEPS = ("write", "record")


class PolicyRefused(ValueError):
    """A policy change, a Turn off or the kill switch refused, in words."""


class NotAPerson(PolicyRefused):
    """Refused because the request is not a verified person's."""


# ── Small helpers ───────────────────────────────────────────────────────────────────────────

def _now(now=None) -> float:
    return time.time() if now is None else float(now)


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def parse_until(value) -> float:
    """AUTO's expiry as an epoch, from ``YYYY-MM-DDTHH:MM:SSZ`` (UTC); `PolicyRefused` naming
    what was sent when it is not one."""
    try:
        return float(calendar.timegm(time.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        raise PolicyRefused(f"AUTO's expiry is a UTC time, YYYY-MM-DDTHH:MM:SSZ, not "
                            f"{value!r}") from None


def _hash(obj) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def policy_fingerprint(values: dict) -> str:
    """The fingerprint of a policy's values (`POLICY_KEYS`): what a person confirmed, and what
    each heal records as the authority it stands on (section 11)."""
    return _hash({k: values.get(k) for k in POLICY_KEYS})


def _words(value) -> str:
    if isinstance(value, list):
        return ", ".join(value) if value else "none"
    if value in ("", None):
        return "none"
    return MODE_WORDS.get(value, str(value)) if isinstance(value, str) else str(value)


def _lock(network: str):
    from modules.config import list_data_path
    from modules.filestore import PathLock

    return PathLock(lambda: os.path.join(list_data_path(network), LOCK_NAME))


# ── Reading ─────────────────────────────────────────────────────────────────────────────────

def _read(network: str) -> dict:
    """The network's stored policy: ``{"state", "error", "values", "origins", "confirmed"}``.
    ``state``: ``ok`` or ``unreadable`` (its settings could not be read: never read as on)."""
    from modules import list_settings as L
    from modules.config import SettingsUnreadable

    if not network:
        return {"state": "unreadable", "error": "no network was named", "values": {},
                "origins": {}, "confirmed": {}}
    values, origins = {}, {}
    try:
        store = None if L.is_default(network) else L.load(network)
        for k in POLICY_KEYS + (CONFIRMED_KEY,):
            values[k], origins[k] = L.resolve(network, k, store)
    except (L.ListSettingsUnreadable, SettingsUnreadable) as exc:
        return {"state": "unreadable", "error": f"{network}'s heal policy cannot be read "
                f"({exc})", "values": {}, "origins": {}, "confirmed": {}}
    confirmed = values.pop(CONFIRMED_KEY) or {}
    origins.pop(CONFIRMED_KEY, None)
    return {"state": "ok", "error": "", "values": values, "origins": origins,
            "confirmed": confirmed if isinstance(confirmed, dict) else {}}


def _is_set(origin: str) -> bool:
    from modules import list_settings as L

    return origin == L.SET_HERE


def guards(values: dict, origins: dict, lab: bool) -> dict:
    """Each hard stop's value now: ``{key: {"value", "source", "words"}}``, *source* ``set``
    (the network's own), ``lab default`` or ``default``."""
    from modules.settings_schema import DEFAULTS

    out = {}
    for k in GUARD_KEYS:
        if _is_set(origins.get(k, "")):
            value, source = values.get(k), "set"
        elif lab and k in LAB_DEFAULTS:
            value, source = LAB_DEFAULTS[k], "lab default"
        else:
            value, source = values.get(k, DEFAULTS.get(k)), "default"
        tail = (f" (lab default; {DEFAULTS.get(k)} on a network not marked lab)"
                if source == "lab default" else "")
        out[k] = {"value": value, "source": source,
                  "words": f"{GUARD_WORDS[k]}: {value}{tail}"}
    return out


def stopped() -> dict:
    """The installation's kill switch: ``{"stopped", "state", "by", "at", "why", "words"}``.
    An unreadable switch is stopped (it fails closed, never open)."""
    from modules import installation_settings as I
    from modules.config import SettingsUnreadable
    from modules.settings_schema import get_setting

    try:
        on = bool(get_setting("heal_stopped", False))   # KILL_KEY, literal for the read scan
    except SettingsUnreadable as exc:
        return {"stopped": True, "state": "unreadable", "by": "", "at": "", "why": "",
                "words": (f"the kill switch cannot be read ({exc}), so self-healing is "
                          "stopped everywhere")}
    if not on:
        return {"stopped": False, "state": "ok", "by": "", "at": "", "why": "",
                "words": "self-healing is not stopped"}
    rows = I.changes(kinds=("heal_stopped",))
    last = rows["rows"][0] if rows.get("rows") else {}
    by = last.get("actor_label") or last.get("actor") or ""
    at = last.get("at_iso") or ""
    why = last.get("why") or ""
    said = (f" by {by} at {at}" if by else
            (" (who stopped it is not recorded: the record " +
             ("cannot be read)" if rows.get("state") == "unreadable" else "holds no stop)")))
    return {"stopped": True, "state": "ok", "by": by, "at": at, "why": why,
            "words": f"self-healing is stopped everywhere{said}" + (f": {why}" if why else "")}


#: The kill switch as resuming would leave it: what `resume_plan` asks `current` about.
NOT_STOPPED = {"stopped": False, "state": "ok", "by": "", "at": "", "why": "",
               "words": "self-healing is not stopped"}


def current(network: str, now: float = None, *, kill: dict = None) -> dict:
    """*network*'s heal policy now: ``{"network", "mode", "set", "state", "error", "words",
    "until", "expired", "suspended", "confirmed", "fingerprint", "kinds_auto",
    "kinds_propose", "guards", "stage", "stopped"}``. *mode* is what runs now (``off``,
    ``dry_run`` or ``auto``), after the kill switch, the confirmation, the expiry and the stage
    guard; *set* is the mode stored. *kill*: the kill switch to judge by, `stopped()` unless
    given (the resume preview asks with `NOT_STOPPED`)."""
    from modules.sdn import modes as sdn_modes

    now = _now(now)
    got = _read(network)
    stage = sdn_modes.stage(network) if network else {"stage": "", "state": "unreadable",
                                                      "words": "no network was named"}
    lab = stage.get("stage") == sdn_modes.AUTO_STAGE
    kill = stopped() if kill is None else kill
    values = got["values"]
    out = {"network": network, "mode": "off", "set": values.get(MODE_KEY, ""),
           "state": got["state"], "error": got["error"], "until": values.get(UNTIL_KEY, ""),
           "expired": False, "suspended": "", "confirmed": got["confirmed"],
           "fingerprint": policy_fingerprint(values) if values else "",
           "kinds_auto": list(values.get(KINDS_AUTO_KEY) or []),
           "kinds_propose": list(values.get(KINDS_PROPOSE_KEY) or []),
           "guards": guards(values, got["origins"], lab) if values else {},
           "stage": stage, "stopped": kill}
    if kill["stopped"]:
        return dict(out, words=f"off: {kill['words']}")
    if got["state"] != "ok":
        return dict(out, words=f"off: {got['error']}, and a policy that cannot be read is "
                               "never read as on")
    mode = values.get(MODE_KEY)
    if mode not in MODES or mode == "off":
        return dict(out, words=(f"off: self-healing is off for {network}" if mode == "off"
                                else f"off: {MODE_KEY} holds {mode!r}, which is not "
                                     f"{', '.join(MODES)}"))
    confirmed = got["confirmed"]
    if confirmed.get("fingerprint") != out["fingerprint"]:
        said = (f"the ones {confirmed.get('by')} confirmed (confirmed "
                f"{confirmed.get('fingerprint')}, now {out['fingerprint']})"
                if confirmed.get("fingerprint") else
                f"confirmed by anyone (now {out['fingerprint']}, and no confirmation is held)")
        return dict(out, words=(f"off: {network}'s heal policy holds values that are not {said}, "
                                "so it is not in force until a person confirms it"))
    if mode == "auto":
        until = values.get(UNTIL_KEY) or ""
        try:
            until_epoch = parse_until(until)
        except PolicyRefused:
            until_epoch = 0.0
        if now >= until_epoch:
            return dict(out, mode="dry_run", expired=True,
                        words=(f"dry run: AUTO by {confirmed.get('by')} expired "
                               f"{until or '(no expiry held)'}, and an expired AUTO is dry run"))
        refused = sdn_modes.auto_refusal(network)
        if refused:
            return dict(out, mode="dry_run", suspended=refused,
                        words=f"dry run: AUTO is set and suspended, since {refused}")
        return dict(out, mode="auto",
                    words=(f"AUTO until {until}, by {confirmed.get('by')}: "
                           f"{confirmed.get('reason')} (allows {_words(out['kinds_auto'])})"))
    return dict(out, mode="dry_run",
                words=(f"dry run, by {confirmed.get('by')}: {confirmed.get('reason')}; every "
                       "step runs except the apply"))


# ── A change: plan, then apply ──────────────────────────────────────────────────────────────

def _proposed(before: dict, proposed: dict, now: float) -> dict:
    """The policy after *proposed*: the network's values with the sent ones in place, checked
    for shape (`PolicyRefused` names the field)."""
    from modules.settings_schema import DEFAULTS, validate

    if not isinstance(proposed, dict) or not proposed:
        raise PolicyRefused("a policy change names at least one value, and none was sent")
    stray = sorted(set(proposed) - set(POLICY_KEYS))
    if stray:
        raise PolicyRefused(f"{', '.join(stray)} {'is' if len(stray) == 1 else 'are'} not part "
                            f"of a heal policy, which holds {', '.join(POLICY_KEYS)}")
    after = dict(before)
    after.update(proposed)
    mode = after.get(MODE_KEY)
    if mode not in MODES:
        raise PolicyRefused(f"the mode is {', '.join(MODES)}, not {mode!r}")
    if mode != "auto":
        after[UNTIL_KEY] = ""
    else:
        until = after.get(UNTIL_KEY) or ""
        if not until:
            raise PolicyRefused("AUTO is set with an expiry (at most 7 days; it then returns "
                                "to dry run), and none was given")
        epoch = parse_until(until)
        if epoch <= now:
            raise PolicyRefused(f"AUTO's expiry is in the future, and {until} is not (now "
                                f"{_iso(now)})")
        if epoch - now > MAX_AUTO_SECONDS:
            raise PolicyRefused(f"AUTO may be on for at most {MAX_AUTO_SECONDS // 86400} days "
                                f"(N8); {until} is {round((epoch - now) / 86400, 1)} days away")
    for key, allowed, tier in ((KINDS_AUTO_KEY, TIER1_KINDS, "Tier 1"),
                               (KINDS_PROPOSE_KEY, TIER2_KINDS, "Tier 2")):
        got = after.get(key)
        if not isinstance(got, list) or any(k not in allowed for k in got):
            bad = got if not isinstance(got, list) else [k for k in got if k not in allowed]
            raise PolicyRefused(f"{key} names {tier} kinds only ({', '.join(allowed)}), not "
                                f"{bad!r}: a kind's tier is a ceiling in code")
    candidate = dict(DEFAULTS)
    candidate.update(after)
    ok, why = validate(candidate)
    if not ok:
        raise PolicyRefused(f"not a heal policy: {why}")
    return after


def plan(network: str, proposed: dict, now: float = None) -> dict:
    """What changing *network*'s policy to *proposed* would do; writes nothing.
    ``{"network", "before", "after", "changes", "gates", "confirmable", "fingerprint",
    "operands", "stage", "stopped", "policy_fingerprint", "confirmed"}``. *fingerprint* binds
    the confirm to this preview: the network, its stage, the kill switch, the values and
    confirmation now, and the values after."""
    from modules.sdn import modes as sdn_modes

    now = _now(now)
    if not network:
        raise PolicyRefused("a heal policy is one network's, and none was named")
    got = _read(network)
    if got["state"] != "ok":
        raise PolicyRefused(f"{got['error']}: nothing can be previewed or saved until it can")
    before = got["values"]
    after = _proposed(before, proposed, now)
    stage = sdn_modes.stage(network)
    kill = stopped()
    changes = [[k, before.get(k), after.get(k)] for k in POLICY_KEYS
               if before.get(k) != after.get(k)]
    confirmed = got["confirmed"]
    in_force = confirmed.get("fingerprint") == policy_fingerprint(before)
    gates = []
    if after[MODE_KEY] == "auto":
        refused = sdn_modes.auto_refusal(network)
        gates.append({"name": "AUTO only on a network marked lab (C2009)",
                      "state": "fail" if refused else "pass",
                      "why": refused or stage["words"]})
        gates.append({"name": "AUTO names the Tier 1 kinds it heals",
                      "state": "pass" if after[KINDS_AUTO_KEY] else "fail",
                      "why": (f"allows {_words(after[KINDS_AUTO_KEY])}" if after[KINDS_AUTO_KEY]
                              else "AUTO allows no kind, so it would heal nothing while looking "
                                   "on: choose dry run, or allow one Tier 1 kind")})
        gates.append({"name": "AUTO's expiry, at most 7 days (N8)", "state": "pass",
                      "why": f"until {after[UNTIL_KEY]}, then dry run"})
    else:
        gates.append({"name": "AUTO only on a network marked lab (C2009)",
                      "state": "not_applicable",
                      "why": f"the mode is {MODE_WORDS[after[MODE_KEY]]}"})
    added = [k for k in after[KINDS_AUTO_KEY] if k not in (before.get(KINDS_AUTO_KEY) or [])]
    gates.append({"name": "Tier 1 kinds allowed AUTO one at a time (N8)",
                  "state": "fail" if len(added) > 1 else "pass",
                  "why": (f"this change allows {len(added)} more ({', '.join(added)}); allow "
                          "one, run its scenario, then the next" if len(added) > 1 else
                          f"this change allows {len(added)} more"
                          + (f" ({added[0]})" if added else ""))})
    something = bool(changes) or (after[MODE_KEY] != "off" and not in_force)
    gates.append({"name": "something to confirm", "state": "pass" if something else "fail",
                  "why": ("the values change" if changes else
                          "the values are not the ones confirmed, so confirming them puts the "
                          "policy in force" if something else
                          "the policy would be what it is now")})
    operands = {"network": network, "stage": stage.get("stage"), "stopped": kill["stopped"],
                "before": {k: before.get(k) for k in POLICY_KEYS},
                "confirmed": confirmed.get("fingerprint", ""),
                "after": {k: after.get(k) for k in POLICY_KEYS}}
    return {"network": network, "before": operands["before"], "after": operands["after"],
            "changes": changes, "gates": gates,
            "confirmable": all(g["state"] != "fail" for g in gates),
            "fingerprint": _hash(operands), "operands": operands, "stage": stage,
            "stopped": kill, "policy_fingerprint": policy_fingerprint(after),
            "confirmed": confirmed, "in_force": in_force,
            "guards": guards(after, {k: ("set here" if k in proposed else v)
                                     for k, v in got["origins"].items()},
                             stage.get("stage") == sdn_modes.AUTO_STAGE)}


def _moved(seen: dict, now: dict) -> str:
    """What moved between the operands previewed (*seen*, sent back) and now, both values."""
    if not isinstance(seen, dict):
        return "the preview's operands were not sent back, so what moved cannot be named"
    out = []
    for k in ("network", "stage", "stopped", "confirmed"):
        if seen.get(k) != now.get(k):
            out.append(f"{k}: previewed {seen.get(k)!r}, now {now.get(k)!r}")
    for part in ("before", "after"):
        old, new = seen.get(part) or {}, now.get(part) or {}
        for k in POLICY_KEYS:
            if old.get(k) != new.get(k):
                out.append(f"{k} ({part}): previewed {old.get(k)!r}, now {new.get(k)!r}")
    return "; ".join(out) or ("what the page sent back matches today's, so the fingerprint it "
                              "sent is not that preview's")


def _person_refusal(actor: str, actor_verified: str, person: bool, what: str) -> None:
    if not actor or actor_verified in ("", "none") or not person:
        raise NotAPerson(f"{what} is confirmed by a verified person, and this request "
                            f"is not one (actor {actor or 'none'}, verified "
                            f"{actor_verified or 'none'})")


def apply(network: str, proposed: dict, fingerprint: str, *, actor: str, actor_verified: str,
          person: bool, reason: str, now: float = None, seen: dict = None) -> dict:
    """Make the change the person confirmed, and record it. Re-planned under the network's
    lock; refused when the plan is not confirmable or its fingerprint is not *fingerprint*,
    naming both and what moved. ``{"ok", "network", "mode", "until", "fingerprint",
    "policy_fingerprint", "changes", "recorded", "at"}``."""
    from modules import list_settings as L

    _person_refusal(actor, actor_verified, person, "a heal policy")
    reason = (reason or "").strip()
    if not reason:
        raise PolicyRefused("a heal policy is confirmed with a recorded reason, and none was "
                            "given")
    now = _now(now)
    with _lock(network):
        p = plan(network, proposed, now)                                   # re-plan
        if not p["confirmable"]:
            raise PolicyRefused("not saved: " + "; ".join(
                f"{g['name']}: {g['why']}" for g in p["gates"] if g["state"] == "fail"))
        if p["fingerprint"] != fingerprint:                                # compare
            raise PolicyRefused(f"{network}'s heal policy moved since the preview (confirmed "
                                f"{fingerprint or 'none'}, now {p['fingerprint']}): "
                                f"{_moved(seen, p['operands'])}. Nothing was saved")
        after = p["after"]
        confirmation = {"by": actor, "actor_verified": actor_verified, "at": _iso(now),
                        "reason": reason, "fingerprint": p["policy_fingerprint"],
                        "until": after[UNTIL_KEY]}
        updates = {k: after[k] for k in POLICY_KEYS if k in proposed or
                   k == UNTIL_KEY and p["before"].get(k) != after[k]}
        updates[CONFIRMED_KEY] = confirmation
        got = L.write(network, updates, actor=actor)                       # write
        if not got.get("ok"):
            raise PolicyRefused(f"not saved: {got.get('error') or 'the policy was not written'}")
    entry = L._record(network, {                                           # record
        "kind": "heal_policy", "group": GROUP, "written": sorted(updates),
        "changes": p["changes"], "mode": after[MODE_KEY], "until": after[UNTIL_KEY],
        "policy_fingerprint": p["policy_fingerprint"], "fingerprint": p["fingerprint"],
        "reason": reason, "actor": actor, "actor_verified": actor_verified})
    log.info("heal: %s confirmed %s's policy %s (mode %s)", actor, network,
             p["policy_fingerprint"], after[MODE_KEY])
    return {"ok": True, "network": network, "mode": after[MODE_KEY], "until": after[UNTIL_KEY],
            "fingerprint": p["fingerprint"], "policy_fingerprint": p["policy_fingerprint"],
            "changes": p["changes"], "recorded": entry.get("recorded", False),
            "at": confirmation["at"]}


# ── Turn off: one press, no confirm ─────────────────────────────────────────────────────────

def turn_off(network: str, *, actor: str, actor_verified: str = "", now: float = None) -> dict:
    """Self-healing off for *network* at once, recorded with who and when. No confirm: turning
    healing off takes nothing a person must keep. ``{"ok", "network", "nothing", "before",
    "recorded", "at", "words"}``; off already, or a policy that cannot be read (so already
    off), writes nothing and says so."""
    from modules import list_settings as L

    if not network:
        raise PolicyRefused("self-healing is turned off for one network, and none was named")
    if not actor:
        raise PolicyRefused("Turn off records who pressed it, and no actor was given")
    now = _now(now)
    with _lock(network):
        got = _read(network)
        if got["state"] != "ok":
            return {"ok": True, "network": network, "nothing": True, "before": "",
                    "recorded": False, "at": _iso(now),
                    "words": (f"Nothing written: {got['error']}, so self-healing is already "
                              f"off for {network}, and stays off until the policy can be read "
                              "and a person confirms it")}
        before = got["values"].get(MODE_KEY)
        if before == "off":
            return {"ok": True, "network": network, "nothing": True, "before": before,
                    "recorded": False, "at": _iso(now),
                    "words": f"Self-healing is already off for {network}"}
        out = L.write(network, {MODE_KEY: "off", UNTIL_KEY: ""}, actor=actor)    # write
        if not out.get("ok"):
            raise PolicyRefused(f"not turned off: {out.get('error')}")
    entry = L._record(network, {"kind": "heal_off", "group": GROUP,              # record
                                "written": [MODE_KEY, UNTIL_KEY], "before": before,
                                "until_before": got["values"].get(UNTIL_KEY, ""),
                                "actor": actor, "actor_verified": actor_verified})
    log.info("heal: %s turned self-healing off for %s (was %s)", actor, network, before)
    return {"ok": True, "network": network, "nothing": False, "before": before,
            "recorded": entry.get("recorded", False), "at": entry.get("at", _iso(now)),
            "words": (f"Self-healing turned off for {network} by {actor} (was "
                      f"{MODE_WORDS.get(before, before)}): {OFF_EFFECT}")}


def record_expiry(network: str, now: float = None) -> dict:
    """Record, once per confirmed policy, that AUTO's expiry passed and the mode is dry run
    (the loop calls it each pass). ``{"recorded": bool}``."""
    from modules import list_settings as L

    mode = current(network, now)
    if not mode["expired"]:
        return {"recorded": False}
    fp = mode["confirmed"].get("fingerprint", "")
    with _lock(network):
        rows = L.changes(network)
        if rows["state"] == "unreadable":
            return {"recorded": False, "error": rows.get("error", "the record cannot be read")}
        if any(r.get("kind") == "heal_auto_expired" and r.get("policy_fingerprint") == fp
               for r in rows["rows"]):
            return {"recorded": False}
        entry = L._record(network, {
            "kind": "heal_auto_expired", "group": GROUP, "policy_fingerprint": fp,
            "until": mode["until"], "actor": "Mercury", "actor_verified": "system",
            "why": (f"AUTO by {mode['confirmed'].get('by')} ({mode['confirmed'].get('reason')})"
                    f" reached its expiry {mode['until']}; the mode is dry run")})
    return {"recorded": bool(entry.get("recorded"))}


# ── The installation's kill switch ──────────────────────────────────────────────────────────

def stop(*, actor: str, actor_verified: str = "", why: str = "") -> dict:
    """Stop self-healing everywhere at once (guard 1). One press, no confirm; recorded with
    who, when and why in the installation's settings record. A reason is asked for and never
    required: a stop must not wait on typing. ``{"ok", "nothing", "recorded", "at",
    "words"}``."""
    from modules import installation_settings as I
    from modules.config import SettingsUnreadable
    from modules.settings_schema import write_settings

    if not actor:
        raise PolicyRefused("Stop self-healing everywhere records who pressed it, and no actor "
                            "was given")
    now = stopped()
    if now["stopped"]:
        return {"ok": True, "nothing": True, "recorded": False, "at": now["at"],
                "words": f"Nothing written: {now['words']}"}
    try:
        out = write_settings({KILL_KEY: True}, actor=actor)                     # write
    except SettingsUnreadable as exc:
        return {"ok": True, "nothing": True, "recorded": False, "at": "",
                "words": (f"Nothing written: the settings cannot be read ({exc}), so "
                          "self-healing is already stopped everywhere")}
    if not out.get("ok"):
        raise PolicyRefused(f"not stopped: {out.get('error')}")
    entry = I._record({"kind": "heal_stopped", "card": "heal", "fields": [KILL_KEY],  # record
                       "why": (why or "").strip(), "actor": actor,
                       "actor_verified": actor_verified})
    log.info("heal: %s stopped self-healing everywhere", actor)
    return {"ok": True, "nothing": False, "recorded": entry.get("recorded", False),
            "at": entry.get("at_iso", ""),
            "words": f"Self-healing stopped everywhere by {actor}: {OFF_EFFECT}"}


def resume_plan(now: float = None) -> dict:
    """What resuming self-healing does: each network's mode once resumed. ``{"stopped",
    "networks": [{"network", "mode", "words"}], "fingerprint", "confirmable", "why"}``."""
    from modules.integration_groups import network_names

    kill = stopped()
    if kill["state"] != "ok":
        raise PolicyRefused(f"{kill['words']}: it is resumed once the settings can be read")
    if not kill["stopped"]:
        raise PolicyRefused("self-healing is not stopped, so there is nothing to resume")
    rows = []
    for name in network_names():
        got = _resumed(name, now)
        rows.append({"network": name, "mode": got["mode"], "words": got["words"]})
    operands = {"stopped_at": kill["at"], "stopped_by": kill["by"],
                "networks": [[r["network"], r["mode"]] for r in rows]}
    return {"stopped": kill, "networks": rows, "fingerprint": _hash(operands),
            "operands": operands, "confirmable": True,
            "why": (f"{sum(1 for r in rows if r['mode'] != 'off')} of {len(rows)} networks "
                    "heal once resumed")}


def _resumed(network: str, now: float = None) -> dict:
    """*network*'s mode with the kill switch read as not stopped (for the resume preview)."""
    return current(network, now, kill=NOT_STOPPED)


def resume(fingerprint: str, *, actor: str, actor_verified: str, person: bool, reason: str,
           now: float = None) -> dict:
    """Resume self-healing as previewed: a verified person, a reason, the preview's
    fingerprint. ``{"ok", "recorded", "at", "networks"}``."""
    from modules import installation_settings as I
    from modules.config import SettingsUnreadable, settings_lock
    from modules.settings_schema import write_settings

    _person_refusal(actor, actor_verified, person, "resuming self-healing")
    reason = (reason or "").strip()
    if not reason:
        raise PolicyRefused("resuming self-healing is recorded with a reason, and none was "
                            "given")
    with settings_lock():
        p = resume_plan(now)
        if p["fingerprint"] != fingerprint:
            raise PolicyRefused(f"what resuming does moved since the preview (confirmed "
                                f"{fingerprint or 'none'}, now {p['fingerprint']}). Nothing "
                                "was saved; look at it again")
        try:
            out = write_settings({KILL_KEY: False}, actor=actor)
        except SettingsUnreadable as exc:
            raise PolicyRefused(f"not resumed: the settings cannot be read ({exc})") from None
        if not out.get("ok"):
            raise PolicyRefused(f"not resumed: {out.get('error')}")
    entry = I._record({"kind": "heal_resumed", "card": "heal", "fields": [KILL_KEY],
                       "why": reason, "actor": actor, "actor_verified": actor_verified,
                       "networks": p["operands"]["networks"], "fingerprint": fingerprint})
    log.info("heal: %s resumed self-healing everywhere", actor)
    return {"ok": True, "recorded": entry.get("recorded", False), "at": entry.get("at_iso", ""),
            "networks": p["networks"]}
