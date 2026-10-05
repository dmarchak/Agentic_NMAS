"""A device's ROLE in the inventory, corrected through one recorded path (C225).

Measured on the host, 2026-09-30: `default`'s devices.csv says `router` for
all four switches and nothing for r6. The switches' value came from
`device.save_device()`'s `setdefault("role", "router")` (April 2026), the
old Add Device's writer, and r6's absence from onboarding's promotion, which
writes no role. Nothing could correct either: no route, form or command
edited a role, and the generated Prometheus targets (C232), the topology's
icons and the NetBox import all read it. So the targets carried `router` for
the switches, and the dashboard's `role` variable offered only that.

ONE implementation for every entry point (the Device page's role edit, and
`scripts/nmas-inventory-role` until it exists), in the preview-then-confirm
shape:

- ``plan()`` reads the row and says what changes and what follows from it
  (the Prometheus targets' `role` label, the topology icon, NetBox at its
  next import), and a fingerprint of exactly that;
- ``apply()`` re-reads the row under the list's CSV lock, refuses a moved
  fingerprint, writes the one field, and appends an audit row (who, how the
  who was established, when, before, after, the stated reason) to the list's
  `inventory_edits.jsonl`, 0600. The row is the record: devices.csv is not
  versioned, since it holds every device's encrypted credential.

A NetBox-sourced list is refused: its roles are NetBox's (`role_map`).
"""

import hashlib
import json
import logging
import os
import time

log = logging.getLogger(__name__)

#: The roles NMAS knows (topology draws each): `netbox_source.VALID_ROLES`
#: without the empty one. An empty role is not offered: a correction to
#: nothing is not a correction.
ROLES = ("router", "switch", "firewall")
AUDIT_FILE = "inventory_edits.jsonl"


class RoleEditRefused(ValueError):
    """The edit cannot be planned or applied; the message names why."""


#: How the actor was established, in words (the operator, 2026-09-30: "by
#: <user>" from a host command beside the app's verified email is two
#: identities for one person, unlabelled). The record keeps both fields; this
#: is how every reader of it says who.
ACTOR_BASIS = {"access": "", "host-shell": "host login, not a verified identity",
               "none": "not identified"}


def actor_label(actor: str, actor_verified: str) -> str:
    """``actor``, or ``actor (how, when it is not a verified person)``."""
    basis = ACTOR_BASIS.get(actor_verified, f"established as {actor_verified!r}")
    return f"{actor} ({basis})" if basis else actor


def suggest_role(list_name: str, dialect: str) -> dict:
    """What THIS network's own inventory says devices of *dialect* are:
    ``{"role", "count"}`` when every such device shares one role, else ``{}``.

    Never a platform rule. `cisco_ios` holds vIOS routers and L2 switches and
    `cisco_iosxe` routers and Catalyst switches, so a role keyed on the
    platform is a rule about one deployment wearing a platform's name (the
    operator's own pattern). A network whose every `cisco_ios` device is a
    switch is a fact about that network, said as one, and still a suggestion:
    the person chooses."""
    from modules.device import load_saved_devices
    from modules.nsot import listref
    from modules.nsot.platform import platform_for_device

    try:
        rows = load_saved_devices(listref.resolve(list_name).csv_path)
    except Exception:                                   # noqa: BLE001
        return {}
    roles = [(r.get("role") or "").strip() for r in rows if platform_for_device(r) == dialect]
    if roles and all(roles) and len(set(roles)) == 1:
        return {"role": roles[0], "count": len(roles)}
    return {}


def role_problem(role: str, list_name: str = "", dialect: str = "") -> str:
    """Why *role* cannot be recorded for a new device, or ``""``."""
    if (role or "").strip().lower() in ROLES:
        return ""
    hint = ""
    if list_name and dialect:
        s = suggest_role(list_name, dialect)
        if s:
            hint = (f" Every {dialect} device in {list_name} is a {s['role']} "
                    f"({s['count']}), which is a suggestion, not a rule.")
    got = f"{role!r} is not one of router, switch, firewall" if role else "no role was chosen"
    return (f"{got}: the role becomes the device's Prometheus role label, its topology "
            f"icon and its NetBox role, so it is asked, never guessed from the platform."
            + hint)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _row(ref, hostname: str) -> dict:
    from modules.device import load_saved_devices

    rows = [d for d in load_saved_devices(ref.csv_path)
            if (d.get("hostname") or "").strip() == hostname]
    if not rows:
        raise RoleEditRefused(f"{hostname} is not in {ref.name}'s inventory")
    if len(rows) > 1:
        raise RoleEditRefused(f"{hostname} is in {ref.name}'s inventory {len(rows)} times; "
                              "a role edit needs one row")
    return rows[0]


def _fingerprint(list_name: str, hostname: str, before: str, after: str, reason: str) -> str:
    raw = json.dumps([list_name, hostname, before, after, reason.strip()])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _reason_problem(reason: str) -> str:
    from modules.nsot.authorisation import reason_problem

    return reason_problem({"line": "the role edit", "reason": (reason or "").strip()})


def plan(list_name: str, hostname: str, role: str, reason: str = "") -> dict:
    """What setting *hostname*'s role to *role* changes, and its fingerprint.
    Writes nothing. Refusals are gates by name, never an exception, except an
    unknown list or device (nothing to preview)."""
    from modules.inventory.source_config import is_netbox_sourced
    from modules.nsot import listref

    ref = listref.resolve(list_name)
    if is_netbox_sourced(ref.name):
        raise RoleEditRefused(f"{ref.name} takes its inventory from NetBox: a device's role "
                              "is NetBox's there (and `role_map` maps it). Edit it in NetBox")
    row = _row(ref, hostname)
    before, after = (row.get("role") or "").strip(), (role or "").strip().lower()
    gates = []
    if after not in ROLES:
        gates.append({"gate": "a known role", "state": "fail",
                      "why": f"{role!r} is not one of {', '.join(ROLES)}"})
    else:
        gates.append({"gate": "a known role", "state": "pass", "why": after})
    if after == before:
        gates.append({"gate": "a change", "state": "fail",
                      "why": f"{hostname}'s role is already {before!r}: nothing would change"})
    else:
        gates.append({"gate": "a change", "state": "pass",
                      "why": f"{before or '(none)'} to {after}"})
    problem = _reason_problem(reason)
    gates.append({"gate": "a stated reason", "state": "fail" if problem else "pass",
                  "why": problem or "stated"})
    follows = [
        f"Prometheus: {hostname}'s SNMP targets carry role={after!r}"
        + (f" (was {before!r})" if before else " (they carried no role)")
        + ", once Mercury regenerates the targets (at once in the app; within 300 s "
          "after a command on the host)",
        f"Topology: {hostname} is drawn as a {after}",
        f"NetBox: the next import records {hostname}'s role as {after}"]
    not_done = ["No device is contacted and no configuration changes",
                "Series Prometheus stored before the change keep their old role label "
                "until retention removes them"]
    return {"list": ref.name, "device": hostname, "before": before, "after": after,
            "reason": (reason or "").strip(), "gates": gates, "follows": follows,
            "not_done": not_done,
            "confirmable": all(g["state"] == "pass" for g in gates),
            "fingerprint": _fingerprint(ref.name, hostname, before, after, reason or "")}


def apply(list_name: str, hostname: str, role: str, reason: str, fingerprint: str,
          actor: str, actor_verified: str) -> dict:
    """Write the role the person confirmed, and record it. Refuses a plan
    that moved since the preview (another edit, or a different row), naming
    both fingerprints."""
    from modules.config import open_secure
    from modules.device import devices_csv_lock, load_saved_devices, write_devices_csv
    from modules.nsot import listref

    if not actor:
        raise RoleEditRefused("a role edit records who made it, and no actor was given")
    ref = listref.resolve(list_name)
    with devices_csv_lock(ref.csv_path):
        p = plan(ref.name, hostname, role, reason)
        if not p["confirmable"]:
            raise RoleEditRefused("; ".join(g["why"] for g in p["gates"] if g["state"] != "pass"))
        if p["fingerprint"] != fingerprint:
            raise RoleEditRefused(
                f"the inventory moved since the preview: confirmed {fingerprint}, now "
                f"{p['fingerprint']} ({hostname}'s role now reads {p['before']!r}); nothing "
                "was written")
        rows = load_saved_devices(ref.csv_path)
        for r in rows:
            if (r.get("hostname") or "").strip() == hostname:
                r["role"] = p["after"]
        write_devices_csv(rows, ref.csv_path)
    rec = {"at": _now_iso(), "list": ref.name, "device": hostname, "field": "role",
           "before": p["before"], "after": p["after"], "reason": p["reason"],
           "actor": actor, "actor_verified": actor_verified,
           "actor_label": actor_label(actor, actor_verified), "fingerprint": p["fingerprint"]}
    path = os.path.join(ref.data_dir, AUDIT_FILE)
    try:
        with open_secure(path, "a") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        rec["recorded"] = True
    except OSError as exc:
        # The role IS written: say so first, and that its record is not.
        log.error("inventory edit: %s's role written and NOT recorded: %s", hostname, exc)
        rec.update(recorded=False, record_error=f"{type(exc).__name__}: {exc}")
    log.info("inventory edit: %s role %r -> %r by %s (%s)", hostname, p["before"], p["after"],
             actor, actor_verified)
    return dict(rec, follows=p["follows"])


def history(list_name: str, hostname: str = "") -> dict:
    """The recorded edits, newest first. ``state``: ``absent`` (none yet),
    ``ok``, or ``unreadable`` (never read as none)."""
    from modules.nsot import listref

    ref = listref.resolve(list_name)
    path = os.path.join(ref.data_dir, AUDIT_FILE)
    if not os.path.exists(path):
        return {"state": "absent", "rows": []}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{type(exc).__name__}: {exc}"}
    rows = [dict(r, actor_label=r.get("actor_label") or actor_label(r.get("actor", ""),
                                                                     r.get("actor_verified", "")))
            for r in rows if not hostname or r.get("device") == hostname]
    return {"state": "ok", "rows": list(reversed(rows))}
