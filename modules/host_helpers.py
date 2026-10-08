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

    out = [{"name": name, "installed": path, "source": source, "how": "copy",
            "needed_by": "the Update button", "checked_by": "updater_rows",
            "check": "updater", "unit": "updater", "folds": ("differs",)}
           for name, path, source in update_op.INSTALLED if source]
    # The Oxidized credential helper is still a root-installed file until Phase 3's host steps
    # remove it, so a commit changing it still names a host step; but nothing a rotation,
    # onboarding or retire does runs it since Phase 3 step 2 (2026-10-08), so it has no
    # job-health row (`unit` empty) and folds nothing.
    from modules.nsot import credential_rotation as cr
    out.append({"name": "the Oxidized credential helper (retired)",
                "installed": cr.HELPER_INSTALLED, "source": cr.HELPER_SOURCE_REL,
                "how": "copy", "needed_by": "nothing since Phase 3 step 2: the host steps remove it",
                "checked_by": "", "check": "oxidized-cred", "unit": "", "folds": ()})
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
    return {h["check"]: (f"job_health:{h['unit']}", tuple(h["folds"])) for h in registry()
            if h["unit"]}


def sources() -> list:
    """Every repository path a root-installed file comes from, the rendered units' folder
    included."""
    return sorted({h["source"] for h in registry()} | set(RENDERED))


def _setting(key: str) -> str:
    from modules.list_settings import default_layer   # one helper and one renderer on the host
    return str(default_layer(key, "") or "").strip()



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


#: Job health's rows about a root-installed file, by unit: each is the same file the host-step
#: check reads live, so a stored reading of one that says not-ok is asked again when Needs
#: attention is read (`attention._install_rows_asked_again`, C439). Every registry unit
#: (tests/test_install_rows_rechecked.py holds the two together).
INSTALL_UNITS = ("updater", "helper:topology-renderer")


def ask_now(unit: str) -> list:
    """One install unit's job-health rows, read now."""
    if unit == "updater":
        from modules import job_health
        return job_health.updater_rows()
    check = {"helper:topology-renderer": topology_row}
    row = check[unit]()
    return [row] if row else []


def helper_rows() -> list:
    """Job health's rows for the root-installed helpers the updater's rows do not cover; a
    check that raises is said as such, never a missing row."""
    rows = []
    # The Oxidized helper's row and the retired devices' router.db row (C398) went with
    # Oxidized (Phase 3 step 2, 2026-10-08).
    for unit, fn in (("helper:topology-renderer", topology_row),):
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
