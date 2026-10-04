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
    """``{check: (job-health row id, states it folds)}``, from the registry."""
    return {h["check"]: (f"job_health:{h['unit']}", tuple(h["folds"])) for h in registry()}


def sources() -> list:
    """Every repository path a root-installed file comes from, the rendered units' folder
    included."""
    return sorted({h["source"] for h in registry()} | set(RENDERED))


def _setting(key: str) -> str:
    from modules.settings_schema import get_setting
    return str(get_setting(key, "") or "").strip()


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


def helper_rows() -> list:
    """Job health's rows for the root-installed helpers the updater's rows do not cover; a
    check that raises is said as such, never a missing row."""
    rows = []
    for unit, fn in (("helper:oxidized-cred", oxidized_row),
                     ("helper:topology-renderer", topology_row)):
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
