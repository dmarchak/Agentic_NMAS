"""Every file a person installs on the host as root, and whether the installed copy is this
release's (the operator, 2026-10-03: helper drift: "every root-installed helper covered by the
Host-Step check; job health compares each installed helper with this release and raises the
install step BEFORE an operation needs it").

ONE registry, built from the constants each owner already declares (the updater's
`update_op.INSTALLED`, the rotation's `HELPER_INSTALLED` and `HELPER_SOURCE_REL`), so a
path is written once. Read by:

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
#: Installed root-owned by their host step, compared with this release by nothing yet: Mercury's
#: records database's compose file and init script (/opt/mercury-postgres/, P4-1). The database
#: itself is measured by the records settings' Test, not by a drift row.
BY_HAND = ("deploy/postgres/",)


def registry() -> list:
    """``[{"name", "installed", "source", "how", "needed_by", "checked_by", "check", "unit",
    "folds"}]``: every root-installed file and the repository file it is a copy of (or links
    to). *check* is its host-step check (`host_steps.CHECKS`), which a commit changing it
    names in its step (scripts/nmas-host-step-check); *unit* is its job-health row; *folds*
    are that row's states one install clears, so while a step with that check is owed the row
    attaches to the step's (C419: one cause, one row, for every helper)."""
    from modules import update_op

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
    # The topology renderer was retired at 7.8 (2026-10-12: OBSERVE › Topology replaced it)
    # and its host step removed the link and the unit (`topology-renderer-gone` in
    # host_steps.CHECKS still measures that), so it is no longer a root-installed file here.
    return out


def folds() -> dict:
    """``{check: (job-health row id, states it folds)}``, from the registry. The helper's pin
    has its own check (C443) and no row of its own: an unpinned helper is the helper's row,
    reading ``differs``, so a pin step owed takes that row too (one cause, one row)."""
    return {h["check"]: (f"job_health:{h['unit']}", tuple(h["folds"])) for h in registry()
            if h["unit"]}


def sources() -> list:
    """Every repository path a root-installed file comes from, the rendered units' folder and
    the folders installed by hand included."""
    return sorted({h["source"] for h in registry()} | set(RENDERED) | set(BY_HAND))


#: Job health's rows about a root-installed file, by unit: each is the same file the host-step
#: check reads live, so a stored reading of one that says not-ok is asked again when Needs
#: attention is read (`attention._install_rows_asked_again`, C439). Every registry unit
#: (tests/test_install_rows_rechecked.py holds the two together).
INSTALL_UNITS = ("updater",)

#: ``(unit, row function)`` for each root-installed helper the updater's rows do not cover.
#: None since the topology renderer was retired (7.8, 2026-10-12); the Oxidized helper's row
#: and the retired devices' router.db row (C398) went with Oxidized (Phase 3 step 2).
HELPERS = ()


def ask_now(unit: str) -> list:
    """One install unit's job-health rows, read now."""
    if unit == "updater":
        from modules import job_health
        return job_health.updater_rows()
    row = dict(HELPERS)[unit]()
    return [row] if row else []


def helper_rows() -> list:
    """Job health's rows for the root-installed helpers the updater's rows do not cover; a
    check that raises is said as such, never a missing row."""
    rows = []
    for unit, fn in HELPERS:
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
