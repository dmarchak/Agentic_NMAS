"""What kind of installation this is, and which checks a laptop kit has no use for (C2521).

`installation_kind` (docs/SETTINGS.md) is ``host``, the Mercury host's install and the default,
or ``laptop_kit``, the final SDN lab's laptop kit (lab/sdn-laptop, docs/LAB9_LAPTOP_RUN.md).
docs/LAB9_SDN_GAP.md 2.3 surveyed what assumes the Mercury host; the operator's report of
2026-11-05 measured it on the kit: 29 Needs attention rows, nearly all checks of the server's
own install. On a kit each of those is marked "not applicable on a laptop kit" under What
was checked, one line naming the check and why, instead of a row: explicit, never hidden,
never critical. On ``host`` nothing here changes anything.

This module is the ONE table of them. Each entry says why the check is the server's (its
systemd units, its updater, Proxmox, its local CI, GitHub, its monitoring stack, its host
steps) and why on a kit it cannot be a real problem. Anything not named here stays a row as
before: NetBox down while the kit runs, a device unreachable, anything about the kit's own
network's devices. A monitoring reader is marked only while the service it reads is not
configured: a kit that configures Grafana gets Grafana's failures as rows.
"""

HOST, LAPTOP_KIT = "host", "laptop_kit"
KINDS = (HOST, LAPTOP_KIT)
MARK = "not applicable on a laptop kit"


def kind() -> str:
    """The installation's kind; anything but a declared kind reads as ``host``, the prior
    behaviour (the schema refuses any other value on write). An unreadable settings file reads
    as ``host`` too: every check stays a row, the louder answer, and job health's own
    settings row says the file cannot be read."""
    from modules.settings_schema import get_setting

    try:
        got = get_setting("installation_kind", HOST)
    except Exception:                                   # noqa: BLE001 (unreadable: host)
        return HOST
    return got if got in KINDS else HOST


def is_laptop_kit() -> bool:
    """Whether this installation is the laptop kit."""
    return kind() == LAPTOP_KIT


_SYSTEMD = ("a systemd timer of the Mercury host's install (deploy/systemd, docs/DEPLOY_LINUX.md); "
            "a laptop kit runs Mercury as its own user unit and installs none of them, so "
            "'not installed' is how a kit is built, not a fault")
_GITHUB = ("it compares the running commit with GitHub's origin and its CI, the server's "
           "deploy workflow (Update deploys only a commit CI passed); a laptop kit is pinned to "
           "one commit, moved only by `kit repin`, and nmas-deploy refuses it, so being behind "
           "origin or unverified by CI is how a kit is run")
_SCHEDULED = ("it reads the scheduled GitHub workflows (the nightly coverage and the weekly "
              "mutation runs), the repository's, not an installation's; the Mercury host watches "
              "them, and a laptop kit has nothing to do about one")

#: Job-health units (`modules/job_health.py`, and the readers' liveness rows) the server's
#: install alone has, with why each is the server's.
JOB_UNITS = {
    "nmas-netbox-backup": _SYSTEMD + "; the kit's NetBox is its own Compose stack, emptied by "
                          "`kit reset`, and nothing on the laptop is backed up",
    "nmas-netbox-restore-test": _SYSTEMD + "; it restores the server's hourly NetBox copy, and "
                                "a kit takes none",
    "nmas-heartbeat-check": _SYSTEMD + "; it measures heartbeats in the server's Loki and its "
                            "Grafana rules, and a kit runs neither",
    "nmas-telemetry-check": _SYSTEMD + "; it compares telemetry alert rules in the server's "
                            "Grafana, and a kit runs none",
    "nmas-startup-check": _SYSTEMD + "; a rotation whose startup config is not known safe is "
                          "still a row of its own (the rotation rows), on a kit as on a host",
    "updater": ("the Update button's root-owned updater on the Mercury host (docs/UPDATE.md); a "
                "laptop kit is moved only by `kit repin`, and nmas-deploy refuses the kit"),
    "reader:app-pushed": _GITHUB,
    "reader:ci-verdict": _GITHUB,
    "reader:ci-agreement": _GITHUB + "; it also reads the Mercury host's local CI runner "
                           "(/var/lib/nmas-local-ci), which a kit has not",
    "reader:scheduled-jobs": _SCHEDULED,
}

#: Units marked only in the state named, where another state is a real problem a kit could
#: have: the nightly VM images are watched only once Proxmox is configured, and a kit that
#: configures one gets its images' rows.
JOB_UNIT_STATES = {
    ("vm-images", "not_configured"): (
        "the nightly VM images of the lab's Proxmox host (B6, docs/VM_IMAGES.md); a laptop kit "
        "has no Proxmox, so nothing is there to watch"),
}

#: Guard settings (`job_health.settings_rows`) that name a part of the server's monitoring
#: stack; empty on a kit because the kit runs none of it. Marked only while EMPTY.
SETTINGS = {
    "snmp_exporter_config": ("the SNMP exporter's config file on the Mercury host, read for the "
                             "community the server's Prometheus polls with; a laptop kit runs "
                             "no SNMP exporter or Prometheus"),
    "syslog_host": ("the syslog receiver feeding the server's Loki, given to onboarded devices; "
                    "a laptop kit runs no syslog receiver or Loki, so an onboarded device is "
                    "given no syslog block"),
    "yang_push_script": ("the YANG push script on the Mercury host that the rotation's consumer "
                         "warning names; a laptop kit has no such script"),
}

#: Monitoring readers, marked while every service they read is NOT configured.
_MONITORING = ("it reads the server's monitoring stack ({services}), which a laptop kit does "
               "not run and has not configured; configured, its failures are rows again")
READER_SERVICES = {
    "reader:grafana-alerts": ("grafana",),
    "reader:grafana-dashboards": ("grafana",),
    "reader:coverage-reporting": ("prometheus", "loki"),
}

#: Needs attention's sources that are the server's as a whole: on a kit each is one line under
#: What was checked, its reason, and is not read.
SOURCES = {
    "host_steps": ("a Host-Step trailer is a step for the Mercury host's own install (its units, "
                   "its updater, its local CI runner); a laptop kit takes none: its steps are "
                   "`kit init` and `kit repin`"),
    "pushed": _GITHUB,
    "ci": _GITHUB,
    "ci_agreement": _GITHUB + "; it also reads the Mercury host's local CI runner, which a kit "
                    "has not",
    "scheduled_jobs": _SCHEDULED,
}

#: Sources marked while the service they read is not configured.
SOURCE_SERVICES = {"grafana": ("grafana",)}


def _configured(service: str) -> bool:
    """Whether the Default network's *service* is configured at all: its URL key set
    (`settings_scope.URL_KEYS`, the key a reader skips a configuration on). Default's, because
    the readers' and the source's base stores are Default's configuration; another network's
    own Grafana has a store and a source of its own, which are never marked."""
    from modules import list_settings
    from modules.settings_scope import URL_KEYS

    got = list_settings.value(list_settings.DEFAULT_LIST, URL_KEYS[service], "")
    return bool(str(got or "").strip())


def _monitoring_words(services) -> str:
    from modules.settings_scope import GROUP_LABELS

    return _MONITORING.format(services=" and ".join(GROUP_LABELS.get(s, s) for s in services))


def job(row: dict, kit: bool = None) -> str:
    """Why job-health *row* is not applicable here, or "" (a host, or a check a kit can fail).
    Asked only of a row that is not ok. *kit* is `is_laptop_kit()` read once by a caller asking
    of many rows (one settings read per page, not one per row)."""
    if not (is_laptop_kit() if kit is None else kit):
        return ""
    unit, state = str(row.get("unit") or ""), str(row.get("state") or "")
    if unit in JOB_UNITS:
        return JOB_UNITS[unit]
    if (unit, state) in JOB_UNIT_STATES:
        return JOB_UNIT_STATES[(unit, state)]
    if unit.startswith("setting:") and state == "unset_guard" and unit[8:] in SETTINGS:
        return SETTINGS[unit[8:]]
    services = READER_SERVICES.get(unit)
    if services and not any(_configured(s) for s in services):
        return _monitoring_words(services)
    return ""


def source(name: str) -> str:
    """Why Needs attention's source *name* is not applicable here as a whole, or ""."""
    if not is_laptop_kit():
        return ""
    if name in SOURCES:
        return SOURCES[name]
    services = SOURCE_SERVICES.get(name)
    if services and not any(_configured(s) for s in services):
        return _monitoring_words(services)
    return ""
