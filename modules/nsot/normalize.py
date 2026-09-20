"""nsot/normalize.py

Config-line filtering, in one place.

Six call sites each carried their own hardcoded prefix tuple. They were *not*
copies of one list — they do four different jobs, and collapsing them into a
single ``strip_volatile()`` would change drift results and could break config
push. So this module holds every tuple, named and documented, and each call site
imports the one that matches its job. The duplication is gone; the differences
are deliberate and visible.

Four jobs:

* :func:`strip_for_diff` — normalise both sides before diffing a running config
  against a golden config. Removes lines that change on their own.
* :func:`strip_nmas_header` — remove NMAS's own header from a config before it
  is written to the repo.
* :func:`push_safe_lines` — decide which lines may be **sent to a device**. This
  is a safety filter, not cleanup: ``end`` mid-config silently truncates a
  startup-config, and a bare ``!`` is noise that breaks some parsers.
* :func:`strip_all` — both of the first two, for comparing a golden file with a
  running config.
"""

import logging

log = logging.getLogger(__name__)

#: Header lines NMAS writes into a golden config file itself.
NMAS_HEADER_PREFIXES = (
    "! Golden config",
    "! Saved:",
    "! Source:",
    "! Pre-change",
)

#: IOS lines that change without anyone configuring anything.
IOS_EPHEMERAL_PREFIXES = (
    "! Last configuration",   # IOS change timestamp
    "! NVRAM config",         # NVRAM write timestamp
    "! No configuration",     # empty-config marker
    "Building configuration", # `show run` / `show start` header
    "Current configuration",  # byte-count header
    "ntp clock-period",       # NTP drift — changes every few minutes
    "upgrade fpd",            # auto-inserted by IOS
    "version ",               # IOS version line
)

# ── Per-call-site tuples ────────────────────────────────────────────────────
# These are reproduced exactly as each site had them. Where they differ, the
# difference is real and load-bearing; tests assert byte-equivalence with the
# pre-consolidation behaviour.

#: drift_check, agent_runner, ai_assistant. Note: no "! Pre-change".
DIFF_PREFIXES = IOS_EPHEMERAL_PREFIXES + (
    "! Golden config", "! Saved:", "! Source:",
)

#: pipeline — as DIFF_PREFIXES plus "! Pre-change", because the pipeline writes
#: pre-change snapshots that carry that header.
PIPELINE_DIFF_PREFIXES = DIFF_PREFIXES + ("! Pre-change",)

#: config_git's repo copy. Deliberately keeps "upgrade fpd" and "version " —
#: the repo stores the config as the device reports it, and the IOS version is
#: a real, reviewable fact in a golden config rather than noise in a diff.
REPO_PREFIXES = (
    "! Last configuration", "! NVRAM config", "! No configuration",
    "Building configuration", "Current configuration", "ntp clock-period",
) + NMAS_HEADER_PREFIXES

#: Lines that must never be sent to a device. Not "volatile" — a guard.
#: "end" mid-config silently truncates everything after it when the result is
#: used as a startup-config.
PUSH_SKIP_PREFIXES = (
    "Building configuration",
    "Current configuration",
    "Last configuration change",
    "NVRAM config last updated",
    "!",
    "end",
    "version ",
)


def _strip(text, prefixes, drop_blank=True, drop_bang=False) -> list:
    """Return *text*'s lines with any line starting with *prefixes* removed."""
    out = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if drop_blank and not stripped:
            continue
        if drop_bang and stripped == "!":
            continue
        if any(stripped.startswith(p) for p in prefixes):
            continue
        out.append(line)
    return out


def strip_for_diff(text: str, include_pre_change: bool = False,
                   drop_bang: bool = True) -> list:
    """Normalise a config for diffing. Returns a list of lines."""
    prefixes = PIPELINE_DIFF_PREFIXES if include_pre_change else DIFF_PREFIXES
    return _strip(text, prefixes, drop_blank=True, drop_bang=drop_bang)


def strip_nmas_header(text: str) -> list:
    """Remove NMAS's header lines. Blank lines are preserved."""
    return _strip(text, NMAS_HEADER_PREFIXES, drop_blank=False)


def strip_for_repo(text: str) -> list:
    """Filter a config for storage in the git repo."""
    return _strip(text, REPO_PREFIXES, drop_blank=False)


def push_safe_lines(text: str) -> list:
    """Lines that are safe to send to a device.

    A safety filter: ``end`` appearing mid-config truncates a startup-config,
    and a bare ``!`` is dropped as noise.
    """
    return _strip(text, PUSH_SKIP_PREFIXES, drop_blank=True)


def has_nmas_header(text: str) -> bool:
    first = (text or "").split("\n", 1)[0]
    return first.startswith("! Golden config")
