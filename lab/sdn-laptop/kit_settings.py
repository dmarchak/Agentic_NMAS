"""The laptop kit's settings, through Mercury's own write path (docs/LAB9_LAPTOP_RUN.md).

Run by `kit` from the kit's pinned worktree, with NMAS_DATA_DIR naming the kit's data folder,
never the checkout's. Prints names and states, never a value that could be a secret.

    kit_settings.py init                  the installation's settings that are missing
                                          (installation_kind laptop_kit and the kit's own
                                          Prometheus's URL among them; a stored one is
                                          kept), the lab9 network if missing, made the
                                          installation's current one if none was set, and
                                          lab9's code repository (the kit's bare one) if
                                          none is set; run again by `kit repin`
    kit_settings.py exception-on UNTIL [--reveal]
                                          the identity exception, recorded in History;
                                          --reveal opens reveal too, for the S1 sitting only
                                          (C2897, refused after REVEAL_UNTIL)
    kit_settings.py exception-off WHY     the gates restored, recorded in History
    kit_settings.py netbox-writes-on WHY  NetBox's master write switch on, recorded (C2548)
    kit_settings.py local-account-on WHY  the local account's sign-in allowed, recorded
    kit_settings.py local-account-off WHY the local account's sign-in off again, recorded
    kit_settings.py last-exception        the newest exception record, one line
    kit_settings.py safety                the safety defaults, one PASS/FAIL line each

The identity exception is the operator's option (c) for the hardware sitting (C2520): the gates
for configure, confirm and approve are turned off on this install only, with
`allowed_host_names` and `require_same_origin_writes` on (modules/request_origin.py). The gates
for reveal, publish_remote and break_glass stay on: nothing at the sitting needs them.
"""
import os
import sys

DATA = os.environ.get("NMAS_DATA_DIR", "")
if not DATA or not os.path.isabs(DATA):
    sys.exit("kit_settings: NMAS_DATA_DIR must name the kit's data folder (an absolute path)")
sys.path.insert(0, os.getcwd())

ACTOR = "lab kit (scripts: lab/sdn-laptop)"
VERIFIED = "none"
NETWORK = "lab9"
OPENED = ("configure", "confirm", "approve")
KEPT_ON = ("reveal", "publish_remote", "break_glass")
#: C2897 (the operator's approval of 2026-11-10, "scoped to the S1 sitting only, expiring
#: automatically after it"): `exception-on UNTIL --reveal` also opens the reveal gate, so Show
#: commands' reads run through Mercury at the sitting; it is refused after REVEAL_UNTIL, and the
#: kit's stop (run by the exception's own expiry timer) closes it with the rest.
REVEAL_SITTING = "S1 (Tue 2026-11-10)"
REVEAL_UNTIL = "2026-11-11T07:00Z"


def _reveal_allowed(now=None) -> bool:
    import datetime as dt

    # KIT_NOW (ISO, UTC) stands in for the clock in tests/test_lab_sdn_laptop_kit.py, so the
    # cap is tested on both sides of it whatever the date the suite runs on.
    given = os.environ.get("KIT_NOW", "")
    if now is None and given:
        now = dt.datetime.strptime(given, "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    now = now or dt.datetime.now(dt.timezone.utc)
    cap = dt.datetime.strptime(REVEAL_UNTIL, "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    return now < cap
PORT = os.environ.get("MERCURY_PORT", "5080")
NETBOX = f"http://127.0.0.1:{os.environ.get('NETBOX_PORT', '8001')}"
#: The kit's own Prometheus (compose.yml's `prometheus`, published on loopback only).
PROMETHEUS = f"http://127.0.0.1:{os.environ.get('PROMETHEUS_PORT', '9090')}"
INSTALLATION = {
    "flask_host": "127.0.0.1",
    "flask_port": int(PORT),
    "allowed_host_names": "127.0.0.1, localhost, ::1",
    "require_same_origin_writes": True,
    "heal_mode": "off",
    "ai_background": {},
    "records_db_host": "",
    "netbox_url": NETBOX,
    # The operator's work order after the Lab 9 sitting (2026-11-10: Topology said "Prometheus
    # is not configured", and the URL was then set by hand): the kit runs a Prometheus, so
    # the installation's layer names it, which every network takes unless it sets its own
    # (modules/settings_scope.py's `prometheus` group). Added only when the key is absent, as
    # every value here: a URL set in Settings is kept.
    "prometheus_url": PROMETHEUS,
    # C2521: Needs attention marks the server's own checks (its systemd units, updater, local
    # CI, GitHub, Proxmox, monitoring stack, host steps) "not applicable on a laptop kit".
    "installation_kind": "laptop_kit",
}


def _write(values: dict) -> None:
    from modules.settings_schema import write_settings

    got = write_settings(values, actor=ACTOR)
    if not got.get("ok"):
        sys.exit(f"kit_settings: refused: {got.get('error')}")


def _current_is_set() -> str:
    """The installation's current network when one was SET, or "": a `network_current`
    record in History (this init's, or anyone's), or a registry naming a network other than
    Default. The registry's "Default" on its own is Mercury's first-run placeholder, written
    when the registry is first read, never a choice; with no verified person on the kit, the
    picker cannot set one either (it records a person's own choice)."""
    import json

    from modules import installation_settings as IS
    from modules.config import DEVICE_LISTS_CONFIG

    try:
        with open(DEVICE_LISTS_CONFIG, encoding="utf-8") as fh:
            current = json.load(fh).get("current_list") or ""
    except FileNotFoundError:
        return ""
    except (OSError, ValueError) as exc:
        sys.exit(f"kit_settings: the network registry cannot be read ({type(exc).__name__}): "
                 "nothing is made current over it")
    if current and current != "Default":
        return current
    if any(r.get("kind") == "network_current" for r in IS.changes().get("rows", [])):
        return current or "Default"
    return ""


def init() -> None:
    """Adds what is missing and never overwrites (the operator, 2026-11-05: `kit repin` runs
    it again): an installation setting is written only when its key is ABSENT from the stored
    settings file (not from the schema's defaults), so a value the operator set (NetBox's URL,
    token and auth scheme, the heal mode, anything stored) is kept; lab9 is created only when
    missing, and made current only when no current network was set."""
    from modules import network_admin
    from modules.config import load_user_settings

    stored = load_user_settings()
    added = {k: v for k, v in INSTALLATION.items() if k not in stored}
    kept = sorted(k for k in INSTALLATION if k in stored)
    if added:
        _write(added)
    print("installation settings: added " + (", ".join(sorted(added)) or "none")
          + "; kept " + (", ".join(kept) or "none") + " (already set, never overwritten)")
    current = _current_is_set()
    pv = network_admin.create_preview(NETWORK)
    if pv.get("refused"):
        print(f"network {NETWORK}: {pv['refused']}")
    else:
        network_admin.create(NETWORK, pv["fingerprint"], ACTOR, VERIFIED)
        print(f"network {NETWORK}: created, no git remote")
    code_repository()
    if current:
        print(f"network {NETWORK}: the installation's current network is {current}, set "
              "before: kept")
        return
    # Mercury opens on lab9 (C2521): the kit has no verified person whose own choice the picker
    # could record, so the installation's current network is lab9, recorded in History.
    got = network_admin.make_current(NETWORK, ACTOR, VERIFIED)
    if got.get("changed") and not got.get("recorded"):
        sys.exit(f"kit_settings: {NETWORK} made current and NOT recorded: "
                 f"{got.get('record_error')}")
    print(f"network {NETWORK}: the installation's current network"
          + (" (recorded in History)" if got.get("changed") else " already"))


def code_repository() -> None:
    """lab9's code repository: the kit's own bare repository, ``$KIT_HOME/code/lab9.git`` on
    branch main, which `kit init` makes empty (the operator's decision of 2026-11-10: Drafts
    are added through Mercury, SDN › Apps' Add an app as a Draft…, never committed by hand).
    Set through Mercury's per-network settings write only when lab9 has none (a location set
    before is kept), and recorded in lab9's settings record as the Code repository card's Save
    records it. Who may publish (`code_review`) is never set here: that choice is the
    operator's, on the card."""
    from modules import coderepo
    from modules import list_settings as L

    home = os.environ.get("KIT_HOME") or os.path.dirname(DATA)
    path = os.path.join(home, "code", f"{NETWORK}.git")
    held = coderepo.location(NETWORK)
    if held["location"]:
        print(f"code repository: {NETWORK}'s is set before: kept")
        return
    if held["state"] == "unreadable":
        sys.exit(f"kit_settings: {held['error']}: the code repository is not set")
    if not os.path.isfile(os.path.join(path, "HEAD")):
        print(f"code repository: no repository at {path} (kit init makes it): not set")
        return
    if not coderepo.parse_location(path)["ok"]:
        sys.exit(f"kit_settings: {coderepo.parse_location(path)['error']}")
    got = L.write(NETWORK, {coderepo.LOCATION_KEY: path, coderepo.BRANCH_KEY: "main"},
                  actor=ACTOR)
    if not got.get("ok"):
        sys.exit(f"kit_settings: the code repository was refused: {got.get('error')}")
    rec = L._record(NETWORK, {"kind": "code_repository", "group": coderepo.LOCATION_KEY,
                              "written": [coderepo.LOCATION_KEY, coderepo.BRANCH_KEY],
                              "before": "\n", "after": f"{path}\nmain", "actor": ACTOR,
                              "actor_verified": VERIFIED})
    if not rec.get("recorded"):
        sys.exit(f"kit_settings: the code repository was set and NOT recorded: "
                 f"{rec.get('record_error')}")
    print(f"code repository: {NETWORK}'s set to {path}, branch main (recorded); who may "
          "publish is the operator's, on its card")


def _gates() -> dict:
    from modules.settings_schema import get_setting

    return {a: bool(get_setting(f"require_identity_for_{a}", True)) for a in OPENED + KEPT_ON}


def _record(kind: str, before: dict, after: dict, reason: str) -> None:
    from modules import installation_settings as IS

    changes = [{"key": f"require_identity_for_{a}", "label": f"Require identity for {a}",
                "kind": "bool", "old": before[a], "new": after[a]}
               for a in OPENED + ("reveal",) if before[a] != after[a]]
    got = IS._record({"kind": kind, "actor": ACTOR, "actor_verified": VERIFIED,
                      "changes": changes, "fields": [c["key"] for c in changes],
                      "reason": reason})
    if not got.get("recorded"):
        sys.exit(f"kit_settings: the change was made and NOT recorded: {got.get('record_error')}")


def exception_on(until: str, reveal: bool = False) -> None:
    if reveal and not _reveal_allowed():
        sys.exit(f"kit_settings: --reveal refused: C2897 opened reveal for the sitting "
                 f"{REVEAL_SITTING} only, until {REVEAL_UNTIL}, and that time has passed; the "
                 "exception was not started")
    before = _gates()
    opened = OPENED + (("reveal",) if reveal else ())
    _write({f"require_identity_for_{a}": False for a in opened})
    kept = ("publish_remote and break_glass stay gated; reveal is open too, for the sitting "
            f"{REVEAL_SITTING} only (C2897), until {REVEAL_UNTIL} at the latest"
            if reveal else "reveal, publish_remote and break_glass stay gated")
    _record("identity_exception_on", before, _gates(),
            f"the final SDN lab's hardware sitting, option (c) (C2520): "
            f"{', '.join(opened)} need no verified identity on this install until {until} or "
            f"the kit's stop, whichever is first; Host and Origin checks on; {kept}")
    print(f"identity exception: ON until {until}"
          + (" (reveal open too, C2897)" if reveal else "") + " (recorded in History)")


def exception_off(why: str) -> None:
    before = _gates()
    # Reveal too, whether or not this exception opened it (C2897): the stop closes everything.
    _write({f"require_identity_for_{a}": True for a in OPENED + ("reveal",)})
    _record("identity_exception_off", before, _gates(), f"restored: {why}")
    print("identity exception: OFF, the gates restored (recorded in History)")


def netbox_writes_on(why: str) -> None:
    """NetBox's master write switch on for the kit's installation (the operator's sitting,
    2026-11-05). As built, Mercury turns it on only in the confirm of an authorised NetBox
    write (an import into NetBox, `netbox_ops`), and an import is not offered for a network
    with no devices, while onboarding a first device needs the switch on: a fresh install
    cannot start (C2548). The kit's bridge: the setting written through Mercury's own path and
    recorded in History with its reason, as the identity exception is. Turn off is the NetBox
    connection card's (Settings › Installation › Connections)."""
    from modules import installation_settings as IS
    from modules.settings_schema import get_setting

    if not why.strip():
        sys.exit("kit_settings: NetBox writes need a reason (kit netbox-writes-on \"<why>\")")
    if get_setting("netbox_allow_writes", False):
        print("netbox writes: already ON, nothing written")
        return
    _write({"netbox_allow_writes": True})
    got = IS._record({"kind": "netbox_writes_on", "card": "netbox", "actor": ACTOR,
                      "actor_verified": VERIFIED, "fields": ["netbox_allow_writes"],
                      "changes": [{"key": "netbox_allow_writes", "label": "Writes allowed",
                                   "kind": "bool", "old": False, "new": True}],
                      "reason": f"the laptop kit (C2548's bridge): {why.strip()}"})
    if not got.get("recorded"):
        sys.exit(f"kit_settings: turned on and NOT recorded: {got.get('record_error')}")
    print("netbox writes: ON (recorded in History); Turn off is on Settings › Installation › "
          "Connections, NetBox connection")


def local_account(on: bool, why: str) -> None:
    """The local account's setting on or off for the kit's installation (the operator,
    2026-11-10: the kit had no verified person, so every operation asking for one refused).
    Written through Mercury's own path and recorded in History with its reason. It only allows
    a sign-in: the account and its password are `scripts/nmas-local-account`'s, and Mercury
    still refuses it unless it listens on loopback only (`modules/local_account.state`)."""
    from modules import installation_settings as IS
    from modules import local_account as LA
    from modules.settings_schema import get_setting

    if not why.strip():
        sys.exit("kit_settings: the local account's setting needs a reason")
    was = bool(get_setting(LA.SETTING, False))
    if was == on:
        print(f"local account: already {'ON' if on else 'OFF'}, nothing written")
    else:
        _write({LA.SETTING: on})
        got = IS._record({"kind": "local_account_" + ("on" if on else "off"), "card": "access",
                          "actor": ACTOR, "actor_verified": VERIFIED, "fields": [LA.SETTING],
                          "changes": [{"key": LA.SETTING, "label": "Local account sign-in",
                                       "kind": "bool", "old": was, "new": on}],
                          "reason": f"the laptop kit: {why.strip()}"})
        if not got.get("recorded"):
            sys.exit(f"kit_settings: written and NOT recorded: {got.get('record_error')}")
        print(f"local account: {'ON' if on else 'OFF'} (recorded in History)")
    st = LA.state()
    print("local account sign-in: " + ("possible" if st["enabled"] else f"not yet: {st['why']}"))


def last_exception() -> None:
    from modules import installation_settings as IS

    rows = [r for r in IS.changes().get("rows", [])
            if r.get("kind", "").startswith("identity_exception")]
    if not rows:
        print("identity exception: none recorded on this install")
        return
    r = max(rows, key=lambda x: x.get("at") or 0)
    state = "ON" if r["kind"].endswith("_on") else "restored"
    print(f"identity exception: last {state} at {r.get('at_iso')} ({r.get('reason', '')})")


def safety() -> int:
    from modules.settings_schema import get_setting
    from modules.sdn import modes

    lines = [
        ("heal off", get_setting("heal_mode", "") == "off", get_setting("heal_mode", "")),
        ("background AI off", not any((get_setting("ai_background", {}) or {}).values()),
         "features on: " + ", ".join(k for k, v in (get_setting("ai_background", {}) or {})
                                     .items() if v) or "none"),
        ("SDN AUTO impossible (lab9 not marked lab)", modes.stage(NETWORK)["stage"] != "lab",
         modes.stage(NETWORK)["words"]),
        ("SDN loop in HITL", modes.current(NETWORK).get("mode", "hitl") == "hitl",
         str(modes.current(NETWORK).get("mode", "hitl"))),
        ("records on files", not get_setting("records_db_host", ""), "records_db_host"),
        ("same-origin writes on", bool(get_setting("require_same_origin_writes", False)), ""),
        ("Host check on", bool(get_setting("allowed_host_names", "")), ""),
        ("publish and break-glass gated",
         all(_gates()[a] for a in ("publish_remote", "break_glass")),
         ", ".join(a for a in ("publish_remote", "break_glass") if not _gates()[a])),
        # C2897: reveal is gated, or open for the S1 sitting before its cap; never after.
        ("reveal gated (or open for the sitting " + REVEAL_SITTING + " until " + REVEAL_UNTIL
         + ", C2897)", _gates()["reveal"] or _reveal_allowed(),
         "" if _gates()["reveal"] else "open"),
    ]
    fails = 0
    for name, ok, detail in lines:
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
    return fails


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd == "init":
        init()
    elif cmd == "exception-on" and args:
        exception_on(args[0], reveal="--reveal" in args[1:])
    elif cmd == "exception-off" and args:
        exception_off(" ".join(args))
    elif cmd == "netbox-writes-on" and args:
        netbox_writes_on(" ".join(args))
    elif cmd == "local-account-on" and args:
        local_account(True, " ".join(args))
    elif cmd == "local-account-off" and args:
        local_account(False, " ".join(args))
    elif cmd == "last-exception":
        last_exception()
    elif cmd == "safety":
        sys.exit(safety())
    else:
        sys.exit(__doc__)
