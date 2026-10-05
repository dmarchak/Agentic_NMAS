"""Every file a person installs on the host as root, and whether the installed copy is this
release's (the operator, 2026-10-03: helper drift: "every root-installed helper covered by the
Host-Step check; job health compares each installed helper with this release and raises the
install step BEFORE an operation needs it").

ONE registry, built from the constants each owner already declares (the updater's
`update_op.INSTALLED`, the rotation's `HELPER_INSTALLED` and `HELPER_SOURCE_REL`, the topology
renderer's link in `host_steps`), so a path is written once. Read by:

- the Host-Step check: every source here is under `HOST_STEP_PATHS`, so a commit changing one
  says what the host needs (tests/test_host_helpers.py holds the two together);
- job health: each helper's own check, asked every cycle, so a drifted or missing helper is a
  Needs attention row naming its install command before the operation that runs it refuses.
  The updater's pieces are `updater_rows`' already (`update_op.install_rows`); this adds the
  rest.
"""

import logging

log = logging.getLogger(__name__)

#: The units are rendered from templates with the host's values (scripts/nmas-render-units), so
#: no release copy is byte-identical to them: the updater's install check reads them.
RENDERED = ("deploy/systemd/",)


def registry() -> list:
    """``[{"name", "installed", "source", "how", "needed_by", "checked_by", "check", "unit",
    "folds"}]``: every root-installed file and the repository file it is a copy of (or links
    to). *check* is its host-step check (`host_steps.CHECKS`), which a commit changing it
    names in its step (scripts/nmas-host-step-check); *unit* is its job-health row; *folds*
    are that row's states one install clears, so while a step with that check is owed the row
    attaches to the step's (C419: one cause, one row, for every helper)."""
    from modules import host_steps, update_op
    from modules.nsot import credential_rotation as cr

    out = [{"name": name, "installed": path, "source": source, "how": "copy",
            "needed_by": "the Update button", "checked_by": "updater_rows",
            "check": "updater", "unit": "updater", "folds": ("differs",)}
           for name, path, source in update_op.INSTALLED if source]
    out.append({"name": "the Oxidized credential helper", "installed": cr.HELPER_INSTALLED,
                "source": cr.HELPER_SOURCE_REL, "how": "copy",
                "needed_by": "a rotation's persistence (its Oxidized row) and its preflight",
                "checked_by": "helper_rows", "check": "oxidized-cred",
                "unit": "helper:oxidized-cred", "folds": ("differs", "not_installed")})
    out.append({"name": "the topology renderer", "installed": host_steps.TOPOLOGY_LINK,
                "source": host_steps.TOPOLOGY_SOURCE_REL, "how": "symlink",
                "needed_by": "the topology panel", "checked_by": "helper_rows",
                "check": "topology-renderer", "unit": "helper:topology-renderer",
                "folds": ("differs",)})
    return out


def folds() -> dict:
    """``{check: (job-health row id, states it folds)}``, from the registry. The helper's pin
    has its own check (C443) and no row of its own: an unpinned helper is the helper's row,
    reading ``differs``, so a pin step owed takes that row too (one cause, one row)."""
    out = {h["check"]: (f"job_health:{h['unit']}", tuple(h["folds"])) for h in registry()}
    out["oxidized-pin"] = (out["oxidized-cred"][0], ("differs",))
    return out


def sources() -> list:
    """Every repository path a root-installed file comes from, the rendered units' folder
    included."""
    return sorted({h["source"] for h in registry()} | set(RENDERED))


def _setting(key: str) -> str:
    from modules.list_settings import default_layer   # one helper and one renderer on the host
    return str(default_layer(key, "") or "").strip()


def oxidized_row() -> dict:
    """The Oxidized credential helper, from the rotation's own check (`helper_status`, and
    whether sudo will run it): an optional lab integration, so an installation with no
    Oxidized configured and no helper has no row."""
    from modules.nsot import credential_rotation as cr

    st = cr.helper_status()
    what = "the Oxidized credential helper is this release's, root-owned, runnable by sudo"
    if st["state"] == "not_installed" and not _setting("oxidized_url"):
        return {}
    row = {"unit": "helper:oxidized-cred", "what": what, "max_age_minutes": 0}
    if st["state"] == "ok":
        sudo = cr.helper_sudo_status()
        if not sudo.get("ok"):
            return dict(row, state="cannot_run", detail=sudo.get("reason", ""),
                        action={"label": "Give the service user its sudoers entry, before a "
                                         "rotation needs it",
                                "command": f"{cr._user()} ALL=(root) NOPASSWD: "
                                           f"{cr.HELPER_INSTALLED}"})
        return dict(row, state="ok", detail=f"{cr.HELPER_INSTALLED} is this release's "
                                            f"{cr.HELPER_SOURCE_REL} ({st.get('source_sha')})")
    if st["state"] == "unpinned":
        # C414: the helper refuses every write as root until its pin names the router.db
        # this tool is configured with; one host step (the pin) clears it.
        return dict(row, state="differs", detail=st.get("reason", "") + ". A rotation refuses "
                    "at its preflight until the pin names it.",
                    action={"label": "Pin the helper to the router.db this tool uses, before "
                                     "a rotation needs it", "command": st.get("reinstall", "")})
    state = {"drifted": "differs", "not_installed": "not_installed",
             "not_root_owned": "writable", "group_or_world_writable": "writable"}.get(
        st["state"], "unknown")
    detail = (st.get("reason", "")
              + (f" (installed {st['installed_sha']}, this release {st['source_sha']})"
                 if st.get("installed_sha") else "")
              + ". A rotation refuses at its preflight until it is installed.")
    return dict(row, state=state, detail=detail,
                action={"label": "Install this release's helper, before a rotation needs it",
                        "command": st.get("reinstall", "")})


def topology_row(check=None) -> dict:
    """The topology renderer: a symlink to the checkout's copy, its service restarted after the
    file changed (`host_steps.check_topology_renderer`). Optional: an installation with no
    topology service configured and no renderer has no row."""
    import os

    from modules import host_steps

    if not _setting("topology_service_url") and not os.path.lexists(host_steps.TOPOLOGY_LINK):
        return {}
    got = (check or host_steps.check_topology_renderer)()
    row = {"unit": "helper:topology-renderer", "max_age_minutes": 0,
           "what": "the topology renderer is this release's, and its service runs it"}
    if got["state"] == "done":
        return dict(row, state="ok", detail=got["detail"])
    if got["state"] == "unknown":
        return dict(row, state="unknown", detail=got["detail"])
    return dict(row, state="differs", detail=got["detail"] + ". The topology panel draws the "
                                                             "installed copy until then.",
                action={"label": "Link this release's renderer and restart its service",
                        "command": (f"sudo ln -sfn {os.path.join(host_steps.ROOT, host_steps.TOPOLOGY_SOURCE_REL)} "
                                    f"{host_steps.TOPOLOGY_LINK} && sudo systemctl restart "
                                    f"{host_steps.TOPOLOGY_UNIT}")})


def oxidized_orphans_row(addresses=None, lists=None) -> dict:
    """Oxidized's router.db against the devices the tool manages (C398, the operator's
    decision, 2026-10-04): a row the tool RETIRED that router.db still holds is ``orphaned``,
    naming each device, whose retired record's "Finish this retirement" removes it through the
    helper and reads it back. An address the tool never managed is not its to remove (Oxidized
    may poll devices of its own): counted in the detail, never a row. No Oxidized configured is
    no row; a helper that is not this release's is its own row, not this one.

    *addresses* is the helper's answer (``{"ok", "addresses"}``) and *lists* ``[(name, csv,
    repo)]``, each read here when not given."""
    from modules.nsot import credential_rotation as cr
    from modules.nsot import retire

    if not cr.oxidized_managed():
        return {}
    row = {"unit": "oxidized:retired-rows", "max_age_minutes": 0,
           "what": "Oxidized's router.db holds no row for a device the tool retired"}
    if addresses is None:
        if not cr.helper_status()["ok"]:
            return {}
        addresses = cr.oxidized_addresses()
    if not addresses.get("ok"):
        return dict(row, state="unknown",
                    detail=f"the helper's address list could not be read: "
                           f"{addresses.get('error') or 'no reason given'}")
    managed, retired = set(), {}
    for name, csv, repo in (_every_list() if lists is None else lists):
        from modules.device import load_saved_devices
        managed |= {d.get("ip", "") for d in load_saved_devices(csv)}
        for ip, host in retire.retired_addresses(repo).items():
            retired.setdefault(ip, (host, name))
    held = list(addresses.get("addresses") or [])
    left = [(ip, *retired[ip]) for ip in held if ip not in managed and ip in retired]
    foreign = [ip for ip in held if ip not in managed and ip not in retired]
    counts = (f"router.db holds {len(held)} address(es): {len(held) - len(left) - len(foreign)} "
              f"managed by the tool, {len(left)} of devices it retired, {len(foreign)} it never "
              "managed (not the tool's to remove)")
    if not left:
        return dict(row, state="ok", detail=counts)
    names = ", ".join(f"{host} ({ip}, retired from {lst})" for ip, host, lst in left)
    return dict(row, state="orphaned", devices=[host for _ip, host, _l in left],
                headline=(f"Oxidized still polls {len(left)} device(s) the tool retired, and "
                          f"router.db keeps their credentials: {names}"),
                detail=counts,
                action={"label": "Open each retired device and press Finish this retirement: "
                                 "the helper removes its row and reads router.db back"})


def _every_list() -> list:
    """``[(name, devices.csv, config repo)]`` for every device list."""
    from modules.device import get_device_lists
    from modules.nsot import listref

    out = []
    for item in get_device_lists():
        try:
            ref = listref.resolve(item["name"])
        except Exception as exc:                            # noqa: BLE001
            log.warning("host_helpers: list %r could not be resolved: %s", item.get("name"), exc)
            continue
        out.append((ref.name, ref.csv_path, ref.repo_dir))
    return out


#: Job health's rows about a root-installed file, by unit: each is the same file the host-step
#: check reads live, so a stored reading of one that says not-ok is asked again when Needs
#: attention is read (`attention._install_rows_asked_again`, C439). Every registry unit
#: (tests/test_install_rows_rechecked.py holds the two together).
INSTALL_UNITS = ("updater", "helper:oxidized-cred", "helper:topology-renderer")


def ask_now(unit: str) -> list:
    """One install unit's job-health rows, read now."""
    if unit == "updater":
        from modules import job_health
        return job_health.updater_rows()
    check = {"helper:oxidized-cred": oxidized_row, "helper:topology-renderer": topology_row}
    row = check[unit]()
    return [row] if row else []


def helper_rows() -> list:
    """Job health's rows for the root-installed helpers the updater's rows do not cover; a
    check that raises is said as such, never a missing row."""
    rows = []
    for unit, fn in (("helper:oxidized-cred", oxidized_row),
                     ("helper:topology-renderer", topology_row),
                     ("oxidized:retired-rows", oxidized_orphans_row)):
        try:
            row = fn()
        except Exception as exc:                            # noqa: BLE001
            log.warning("host_helpers: %s raised %s: %s", unit, type(exc).__name__, exc)
            row = {"unit": unit, "state": "unknown", "max_age_minutes": 0,
                   "what": "a root-installed helper is this release's",
                   "detail": f"the check raised {type(exc).__name__}: {exc}"}
        if row:
            rows.append(row)
    return rows
