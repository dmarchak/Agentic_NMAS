"""The laptop kit's settings, through Mercury's own write path (docs/LAB9_LAPTOP_RUN.md).

Run by `kit` from the kit's pinned worktree, with NMAS_DATA_DIR naming the kit's data folder,
never the checkout's. Prints names and states, never a value that could be a secret.

    kit_settings.py init                  the installation's settings and the lab9 network
    kit_settings.py exception-on UNTIL    the identity exception, recorded in History
    kit_settings.py exception-off WHY     the gates restored, recorded in History
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
PORT = os.environ.get("MERCURY_PORT", "5080")
NETBOX = f"http://127.0.0.1:{os.environ.get('NETBOX_PORT', '8001')}"
INSTALLATION = {
    "flask_host": "127.0.0.1",
    "flask_port": int(PORT),
    "allowed_host_names": "127.0.0.1, localhost, ::1",
    "require_same_origin_writes": True,
    "heal_mode": "off",
    "ai_background": {},
    "records_db_host": "",
    "netbox_url": NETBOX,
}


def _write(values: dict) -> None:
    from modules.settings_schema import write_settings

    got = write_settings(values, actor=ACTOR)
    if not got.get("ok"):
        sys.exit(f"kit_settings: refused: {got.get('error')}")


def init() -> None:
    from modules import network_admin

    _write(INSTALLATION)
    print("installation settings: " + ", ".join(sorted(INSTALLATION)))
    pv = network_admin.create_preview(NETWORK)
    if pv.get("refused"):
        print(f"network {NETWORK}: {pv['refused']}")
    else:
        network_admin.create(NETWORK, pv["fingerprint"], ACTOR, VERIFIED)
        print(f"network {NETWORK}: created, no git remote")


def _gates() -> dict:
    from modules.settings_schema import get_setting

    return {a: bool(get_setting(f"require_identity_for_{a}", True)) for a in OPENED + KEPT_ON}


def _record(kind: str, before: dict, after: dict, reason: str) -> None:
    from modules import installation_settings as IS

    changes = [{"key": f"require_identity_for_{a}", "label": f"Require identity for {a}",
                "kind": "bool", "old": before[a], "new": after[a]}
               for a in OPENED if before[a] != after[a]]
    got = IS._record({"kind": kind, "actor": ACTOR, "actor_verified": VERIFIED,
                      "changes": changes, "fields": [c["key"] for c in changes],
                      "reason": reason})
    if not got.get("recorded"):
        sys.exit(f"kit_settings: the change was made and NOT recorded: {got.get('record_error')}")


def exception_on(until: str) -> None:
    before = _gates()
    _write({f"require_identity_for_{a}": False for a in OPENED})
    _record("identity_exception_on", before, _gates(),
            f"the final SDN lab's hardware sitting, option (c) (C2520): configure, confirm and "
            f"approve need no verified identity on this install until {until} or the kit's "
            f"stop, whichever is first; Host and Origin checks on; reveal, publish_remote and "
            f"break_glass stay gated")
    print(f"identity exception: ON until {until} (recorded in History)")


def exception_off(why: str) -> None:
    before = _gates()
    _write({f"require_identity_for_{a}": True for a in OPENED})
    _record("identity_exception_off", before, _gates(), f"restored: {why}")
    print("identity exception: OFF, the gates restored (recorded in History)")


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
        ("reveal, publish and break-glass gated",
         all(_gates()[a] for a in KEPT_ON), ", ".join(a for a in KEPT_ON if not _gates()[a])),
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
        exception_on(args[0])
    elif cmd == "exception-off" and args:
        exception_off(" ".join(args))
    elif cmd == "last-exception":
        last_exception()
    elif cmd == "safety":
        sys.exit(safety())
    else:
        sys.exit(__doc__)
