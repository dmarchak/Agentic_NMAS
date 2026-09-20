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
* :func:`strip_for_roundtrip` — remove what a template **cannot render**, before
  comparing a rendered config with the real one. Distinct from
  :func:`strip_for_diff`: these lines are unrenderable, not volatile. A
  certificate body and a device-inserted banner are perfectly stable — they just
  cannot be reproduced from intent, so counting them as "missing from render"
  would understate coverage for a reason that has nothing to do with modelling.
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


#: Prefixes that may match an **indented** line. Everything else anchors to
#: column 0.
#:
#: This default exists because of a real bug: ``version 17.6`` at column 0 is
#: the device's image version and is not renderable, but ``  version 2`` inside
#: ``router rip`` is RIPv2 — actual configuration. Matching it as "volatile"
#: stripped RIPv2 from every switch, and because the strip was applied to *both*
#: sides of the comparison, the round trip still reported success. A
#: normalisation step can hide exactly what it destroys, so patterns are
#: top-level-only by default and nesting is opt-in.
NESTED_OK_PREFIXES = frozenset({
    # Nothing yet. Add a prefix here only with a comment explaining why a nested
    # occurrence is genuinely volatile rather than configuration.
})


def _matches(stripped: str, line: str, prefixes) -> bool:
    """True if *line* should be stripped.

    A prefix only matches an indented line when it is in
    :data:`NESTED_OK_PREFIXES`.
    """
    indented = line[:1] in (" ", "\t")
    for prefix in prefixes:
        if not stripped.startswith(prefix):
            continue
        if indented and prefix not in NESTED_OK_PREFIXES:
            continue
        return True
    return False


def _strip(text, prefixes, drop_blank=True, drop_bang=False) -> list:
    """Return *text*'s lines with any top-level line starting with *prefixes* removed."""
    out = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if drop_blank and not stripped:
            continue
        if drop_bang and stripped == "!":
            continue
        if _matches(stripped, line, prefixes):
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


#: Block openers whose entire indented body is unrenderable.
UNRENDERABLE_BLOCK_PREFIXES = (
    "crypto pki certificate chain",   # hex certificate bodies
    "license udi",                    # per-chassis serial, set at manufacture
)

#: Single lines that cannot come from intent.
#:
#: Includes NMAS's own golden header and the two lines IOS prints above a
#: `show running-config` / `show startup-config`. Those five were the entire
#: gap between a real NMAS golden file and the fixtures here: every fixture was
#: built from raw device output, so none of them carried the header NMAS itself
#: writes, and the round trip reported five unreproducible lines on all nine
#: devices. A template cannot emit "Current configuration : 4240 bytes".
UNRENDERABLE_LINE_PREFIXES = NMAS_HEADER_PREFIXES + (
    "Building configuration",
    "Current configuration",
    "boot-start-marker",
    "boot-end-marker",
    "! Call-home is enabled",
    "! Image:",
    "! Chassis type:",
    "! Processor ID:",
    "! CPU:",
    "! Memory:",
    "! NAME:",
    "! PID:",
    "! VTP:",
    "! Cisco IOS",
    "! Last configuration change",
    "version ",
)

#: Folded into UNRENDERABLE_LINE_PREFIXES now that every pattern is
#: top-level-anchored by default.
UNRENDERABLE_TOPLEVEL_ONLY = ()

#: Banner delimiters. A banner body is operator text the device echoes back
#: verbatim; the delimiter is a literal ^C control sequence in the config.
_BANNER_OPENERS = ("banner motd", "banner login", "banner exec", "banner incoming")


def strip_for_roundtrip(text: str) -> list:
    """Remove lines a template cannot render, for round-trip comparison.

    Removes certificate chains and their hex bodies, banner blocks, boot
    markers, licence UDI lines, and the ``show version`` preamble NMAS prefixes
    to a golden config. Everything else is left alone — including lines the
    parser does not yet model, which must stay visible so coverage is honest.
    """
    out = []
    in_block = False
    in_banner = False

    for line in (text or "").splitlines():
        stripped = line.strip()

        if in_banner:
            # A banner ends at the closing delimiter, which IOS writes as ^C.
            if "^C" in line or stripped == "!":
                in_banner = False
            continue

        if any(stripped.startswith(p) for p in _BANNER_OPENERS):
            # A single-line banner opens and closes on the same line.
            in_banner = line.count("^C") < 2
            continue

        if in_block:
            # Indented body, or the "quit" terminator of a certificate.
            if line.startswith((" ", "\t")) or stripped == "quit":
                continue
            in_block = False

        if any(stripped.startswith(p) for p in UNRENDERABLE_BLOCK_PREFIXES):
            in_block = True
            continue

        if _matches(stripped, line, UNRENDERABLE_LINE_PREFIXES):
            continue

        out.append(line)

    return out


def has_nmas_header(text: str) -> bool:
    first = (text or "").split("\n", 1)[0]
    return first.startswith("! Golden config")


# ---------------------------------------------------------------------------
# Sendability
# ---------------------------------------------------------------------------

#: The IOS CLI accepts printable ASCII. Anything else is not "unusual input" —
#: it desynchronises the parser. An em dash (U+2014) is three UTF-8 bytes; the
#: device consumed the first, lost the rest of the line, and stored
#: ``description NSoT-managed b``. Netmiko then could not match its echo, so
#: the failure surfaced as a timeout rather than as "that character is invalid".
PRINTABLE_MIN, PRINTABLE_MAX = 0x20, 0x7E


def find_non_printable(text: str) -> list:
    """Every character outside printable ASCII: ``[(column, char, codepoint)]``.

    Column is 1-based, counting characters, so it points at what a person sees
    in an editor. Tabs and newlines are reported too — a tab inside a config
    line is a real source of silent difference.
    """
    found = []
    for index, char in enumerate(text or ""):
        if not (PRINTABLE_MIN <= ord(char) <= PRINTABLE_MAX):
            found.append((index + 1, char, ord(char)))
    return found


def describe_non_printable(found: list, limit: int = 3) -> str:
    """Human-readable summary of :func:`find_non_printable` output."""
    parts = [f"{char!r} (U+{code:04X}) at column {column}"
             for column, char, code in found[:limit]]
    if len(found) > limit:
        parts.append(f"and {len(found) - limit} more")
    return ", ".join(parts)
