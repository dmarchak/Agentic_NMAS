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

import re
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


#: The trustpoint a device generates for ITSELF, named after its own chassis
#: id. Narrow on purpose: `TP-self-signed-<digits>`, not every trustpoint.
_SELF_SIGNED = re.compile(
    r"^crypto pki (?:trustpoint|certificate chain) (TP-self-signed-\d+)\s*$")

#: The words a person reads in place of a regenerated certificate's hex (the
#: operator, 2026-10-01: "49 lines of hex" in a Save All preview after a
#: redeploy, where the one thing to know is that the device made a new one).
CERT_REGENERATED = "regenerated self-signed certificate (expected after a boot)"


def _self_signed_block(text) -> tuple:
    """``(names, lines)``: the device's own self-signed stanzas in *text*, the
    complement of :func:`strip_self_signed_certs`."""
    lines = text if isinstance(text, list) else (text or "").splitlines()
    names, out, inside = [], [], False
    for line in lines:
        m = _SELF_SIGNED.match(line.strip()) if not line[:1].isspace() else None
        if m:
            inside = True
            if m.group(1) not in names:
                names.append(m.group(1))
            out.append(line)
            continue
        if inside and (line[:1].isspace() or not line.strip()):
            out.append(line)
            continue
        inside = False
    return names, out


def self_signed_note(before, after) -> str:
    """One line naming a change to the device's own self-signed certificate
    between *before* and *after*, or ``""`` when it did not change. A diff
    built over :func:`strip_self_signed_certs` carries this line in place of
    the certificate's hex; the golden itself is recorded verbatim."""
    old_names, old = _self_signed_block(before)
    new_names, new = _self_signed_block(after)
    if [l.rstrip() for l in old if l.strip()] == [l.rstrip() for l in new if l.strip()]:
        return ""
    was = ", ".join(old_names) or "none"
    now = ", ".join(new_names) or "none"
    what = f"{was} -> {now}" if was != now else f"{now}, its body changed"
    return (f"~ {CERT_REGENERATED}: {what}; "
            f"{sum(1 for l in new if l.strip())} line(s) recorded verbatim, not drawn")


#: The words a person reads in place of comment lines that differ (the operator,
#: 2026-10-02: r3's "drift" of 9 lines after a crash-reboot was ONE line, "! Call-home is
#: enabled by Smart-Licensing.", which IOS-XE writes itself depending on its licensing
#: state). A comment changes nothing on a device.
COMMENTS_DIFFER = "comment line(s) differ (a comment changes nothing on the device)"


def _comment_lines(text) -> list:
    """Every comment line of *text* (``!`` then words, at any indentation), outside banners:
    a ``!`` line inside a banner is the banner's text, which is configuration a person reads.
    A bare ``!`` is a separator section parsing reads, never a comment here."""
    lines = text if isinstance(text, list) else (text or "").splitlines()
    out, delim = [], None
    for line in lines:
        s = line.strip()
        if delim is not None:                          # inside a banner body
            if delim in line:
                delim = None
            continue
        if line.startswith(_BANNER_OPENERS):
            rest = line.split(None, 2)[2] if len(line.split(None, 2)) > 2 else ""
            d = rest[:2] if rest.startswith("^") else rest[:1]
            if d and d not in rest[len(d):]:
                delim = d
            continue
        if s.startswith("!") and s[1:].strip():
            out.append(line)
    return out


def strip_comments(text) -> list:
    """*text* without its comment lines (:func:`_comment_lines`): for the comparisons that
    ask whether the CONFIGURATION changed, drift and the capture preview. A golden is
    recorded verbatim, comments and all; only the comparison sets them aside, and
    :func:`comment_note` says when it did."""
    lines = text if isinstance(text, list) else (text or "").splitlines()
    drop = _comment_lines(lines)
    out, i = [], 0
    for line in lines:
        if i < len(drop) and line is drop[i]:
            i += 1
            continue
        out.append(line)
    return out


def comment_note(before, after) -> str:
    """One line saying the comment lines differ between *before* and *after*, naming up to
    three of each side, or ``""`` when they do not. A diff built over
    :func:`strip_comments` carries this line in place of them."""
    old = [l.strip() for l in _comment_lines(before)]
    new = [l.strip() for l in _comment_lines(after)]
    if old == new:
        return ""
    gone = [l for l in old if l not in new]
    came = [l for l in new if l not in old]
    shown = ([f"no longer {l!r}" for l in gone[:3]] + [f"now {l!r}" for l in came[:3]]
             or ["reordered"])
    more = len(gone) + len(came) - min(len(gone), 3) - min(len(came), 3)
    return (f"~ {COMMENTS_DIFFER}: " + "; ".join(shown)
            + (f"; and {more} more" if more > 0 else "") + "; recorded verbatim, not drift")


def strip_self_signed_certs(text) -> list:
    """Drop the device's own self-signed trustpoint and certificate chain.

    **Block-aware**, because `_strip()` matches line prefixes and a
    certificate chain is a stanza: a header plus an indented body of hex.

    **Volatile in the true sense** — it changes with nobody changing the
    config. The lab's startup sync drops these blocks wholesale, the device
    regenerates one at boot, and the new body and trustpoint name differ
    from the ones in the golden. Measured on the 2026-09-22 redeploy: r1, r2
    and r4 logged *"yang-infra: ERROR: Failed to create a new self-signed
    trustpoint"*, the goldens then showed regenerated bodies with new
    validity dates, and commit 758d1f56's **only** changes were
    certificates.

    **It is a correct omission, not a blind spot.** Measured: r1-r5 run
    `restconf` with `ip http secure-server`, which uses the certificate, so
    one must *exist* — and the device makes a fresh one every boot. The
    yang-push subscriptions ride NETCONF over SSH and need no certificate at
    all, and nothing in this stack pins one. So it must exist and need not
    survive.

    **What it leaves behind is a permanent, unexplained difference between
    golden and device**, and `configs_equivalent()` reported it as drift:
    measured, a regenerated body and trustpoint name produce three
    `only_left` and three `only_right` lines. Nobody saw it because the
    drift checker has been off since 2026-08-30 — **switched off three
    minutes after a run that flagged all nine devices.** Re-enabling it
    without this would flag every C8000v for something correct, which is
    precisely the condition that silenced it last time.

    **Narrow on purpose.** A CA-signed trustpoint is configuration somebody
    chose, and a change to it is real drift. Only the device's own
    `TP-self-signed-<digits>` is removed.
    """
    lines = text if isinstance(text, list) else (text or "").splitlines()
    out, skipping = [], False
    for line in lines:
        if _SELF_SIGNED.match(line.strip()) and not line[:1].isspace():
            skipping = True
            continue
        if skipping:
            # The stanza's body is indented; the next unindented line ends it.
            if line[:1].isspace() or not line.strip():
                continue
            skipping = False
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


def strip_provenance_comments(text) -> list:
    """Whole-line comments out. **A fifth job, and here is why it is its own.**

    Three stores each stamp their own provenance into a config as a comment:
    a golden opens with ``! Golden config — <host> (<ip>)``, Oxidized stores
    its own metadata header, and the lab's startup sync wrote
    ``! <host> - from Oxidized HEAD <sha>`` until C313 (2026-10-01). None of them is configuration —
    a device does nothing with a comment — and all three differ between
    stores by construction.

    **Measured, and the measurement is narrower than it first looked.**
    :func:`strip_for_diff` already drops *NMAS's own* header, because that
    exact prefix is in ``DIFF_PREFIXES``. It keeps every **other** comment
    line, so Oxidized's metadata header and the sanitiser's provenance line
    both survive it — and a golden compared against Oxidized's copy therefore
    differs on Oxidized's first line for every device on every run. That is
    the noise floor that silences a checker, and it is on the side nobody
    thought to look at: the store this project does not write.

    Not folded into ``strip_for_diff``: it feeds restore baselines and the
    drift diff, where a captured config's comments are part of what was
    captured, and removing them silently would change what a baseline claims.

    **Anchored at column 0**, and a bare ``!`` is kept: it is a block
    separator that section parsing reads, not provenance. A banner body line
    beginning with ``!`` is indented, and the sanitiser drops banners outright
    for an unrelated reason.
    """
    if isinstance(text, (list, tuple)):
        lines = list(text)
    else:
        lines = (text or "").splitlines()
    return [line for line in lines
            if not (line.startswith("!") and line[1:].strip())]


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


def _opens_device_owned(stripped: str, line: str) -> bool:
    """Whether *line* opens a block the DEVICE generates for itself, never configuration
    someone chose: a certificate body, the licence UDI, and the device's own self-signed
    trustpoint (C397: its name follows the chassis id and regenerates at boot, so intent
    holding it would send a trustpoint and an `rsakeypair` the device no longer has). Every
    such block is out of the parse (so out of intent), out of every program and residue
    (`deploy._section_chains`), and out of every round trip, all through
    :func:`strip_for_roundtrip`; :func:`device_owned` names them."""
    if line[:1].isspace():
        return False
    return (any(stripped.startswith(p) for p in UNRENDERABLE_BLOCK_PREFIXES)
            or bool(_SELF_SIGNED.match(stripped)))


#: AutoInstall's DHCP client-id (C485, the operator, 2026-10-05): a ZTP-onboarded IOS-XE device
#: writes, inside the interface it took its lease on, `ip dhcp client client-id ascii
#: cisco-<dotted MAC>-<that interface's SHORT name>`, the identity it sent as option 61. The
#: device generates it from its MAC and the interface, as it generates its licence UDI, and every
#: ZTP onboarding carries it. Only that exact form, the name matched against the interface it
#: sits in AS IOS WRITES IT (`Gi2` inside `GigabitEthernet2`): a client-id a person chose keeps
#: its normal path, so nothing a person configured is dropped.
_AUTOINSTALL_CLIENT_ID = re.compile(
    r"^\s+ip dhcp client client-id ascii cisco-[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}-(\S+)\s*$")


#: C1479 (2026-10-21, measured from R6's and R7's captures): a configless C8000v runs two DHCP
#: clients on its uplink, one sending the MAC form above and one sending its SERIAL NUMBER, and
#: AutoInstall writes the client-id of whichever exchange was answered. The serial form is the
#: device's own only when it is exactly the serial the same configuration's licence UDI names
#: (`license udi pid <pid> sn <serial>`): equality with the device's own identity, never a
#: resemblance, so a client-id a person chose keeps its normal path.
_AUTOINSTALL_SERIAL_CLIENT_ID = re.compile(r"^\s+ip dhcp client client-id ascii (\S+)\s*$")
_LICENCE_SERIAL = re.compile(r"^license udi pid \S+ sn (\S+)\s*$", re.M)


def _device_serial(text: str) -> str:
    """The serial the configuration's licence UDI line names, or '' when it names none."""
    m = _LICENCE_SERIAL.search(text or "")
    return m.group(1) if m else ""


def _autoinstall_client_id(line: str, interface: str, serial: str = "") -> bool:
    """Whether *line*, a child of ``interface <interface>``, is AutoInstall's own client-id: the
    MAC form for that interface (C485), or the device's own *serial* (C1479)."""
    from modules.nsot import ifnames

    m = _AUTOINSTALL_CLIENT_ID.match(line)
    if m and interface and m.group(1) == ifnames.abbreviate(interface):
        return True
    s = _AUTOINSTALL_SERIAL_CLIENT_ID.match(line)
    return bool(s and interface and serial and s.group(1) == serial)


#: BGP's neighbour-change logging (C1182, the operator, W4 after step 50, 2026-10-17): IOS-XE
#: writes ` bgp log-neighbor-changes` under `router bgp` on its own. Measured: every IOS-XE
#: capture that runs BGP holds it (r3, r4, r5 of tests/fixtures/configs/fleet/), and s5, whose
#: intent never sent it, held it after its first deploy, so its intent departed by
#: "- bgp log-neighbor-changes" at once. It is the device's own, as AutoInstall's client-id is:
#: never intent, never sent, never residue, never a departure. Only that exact line, directly
#: under `router bgp`: its negation is a person's choice and stays configuration. The rule is
#: in IOS syntax and keyed on that shape, not on the platform (no comparison here knows it);
#: classic IOS documents the same default (on since 15.0(1)M), its print not yet measured on
#: this fleet (no IOS device runs BGP).
_BGP_LOG_NEIGHBOR_CHANGES = " bgp log-neighbor-changes"


def _bgp_own(line: str, section: str) -> bool:
    """Whether *line*, a child of the top-level *section*, is BGP's own neighbour logging."""
    return section.startswith("router bgp ") and line.rstrip() == _BGP_LOG_NEIGHBOR_CHANGES


def device_owned(text: str) -> list:
    """The header of every block in *text* the device generates for itself, in order: what a
    screen lists as the device's own, never as unmodelled and never as blocking."""
    return [h for h in excluded_unrenderable(text)
            if _opens_device_owned(h, h) or h.startswith(("interface ", "router bgp "))]


#: The line `show startup-config` prints above the configuration, on both platforms (measured,
#: tests/fixtures/transcripts: `Using 5438 out of 33554432 bytes` on a C8000v, `Using 3079 out
#: of 262144 bytes, uncompressed size = 5981 bytes` on vIOS): how full nvram is, never
#: configuration. Running's own headers (`Building configuration...`) are DIFF_PREFIXES'.
STARTUP_HEADER = re.compile(r"Using \d+ out of \d+ bytes\b")


def strip_startup_header(text: str) -> str:
    """*text*, a `show startup-config` read, without :data:`STARTUP_HEADER` (top level only)."""
    return "\n".join(line for line in (text or "").splitlines()
                     if not STARTUP_HEADER.match(line))


#: A certificate STARTUP keeps as a file (IOS-XE, measured on r1 and r6): inside a device-owned
#: certificate chain, ` certificate ca 01 nvram:CiscoLicensi#1CA.cer`, where running prints the
#: same certificate inline (` certificate ca 01`, its hex body, `quit`). Group 1 is the
#: certificate's own line as running prints it (type and serial), group 2 the file.
_CERT_POINTER = re.compile(r"^\s+(certificate\s.*?\S)\s+nvram:(\S+)\s*$")


def certificate_pointers(startup: str) -> list:
    """Every certificate *startup* keeps as a file in nvram:, in order: ``[{"chain",
    "certificate", "file", "line"}]``, ``chain`` the block's header, ``line`` startup's own. Only inside a block
    :func:`_opens_device_owned` opens: the one definition of the device's own blocks."""
    found, chain = [], ""
    for line in (startup or "").splitlines():
        stripped = line.strip()
        if not line[:1].isspace():
            chain = stripped if _opens_device_owned(stripped, line) else ""
            continue
        m = _CERT_POINTER.match(line) if chain else None
        if m:
            found.append({"chain": chain, "certificate": " ".join(m.group(1).split()),
                          "file": "nvram:" + m.group(2), "line": line})
    return found


def nvram_files(listing: str) -> set:
    """The file names a `dir nvram:` read lists: each entry line's last word. An error read
    lists nothing, so every file it was asked about is absent."""
    if not listing or "%Error" in listing or "Invalid input" in listing:
        return set()
    return {line.split()[-1] for line in listing.splitlines()
            if line.strip() and not line.lstrip().startswith(("Directory of", "%"))
            and "bytes total" not in line}


def certificate_storage(startup: str, running: str, nvram_dir: str) -> dict:
    """Where startup and running differ only in how a certificate is STORED, not what it is.

    IOS-XE writes a device-owned certificate chain's certificates to nvram: as files, and its
    startup configuration holds a pointer (` certificate ca 01 nvram:CiscoLicensi#1CA.cer`)
    where running prints the certificate inline. The same certificate: the same chain, the
    same type and serial. Each pointer in *startup* (:func:`certificate_pointers`) whose
    certificate *running* holds inline, in the same chain, has running's inline form (the
    line, its deeper-indented body, its `quit`) replaced by startup's pointer line, so a
    comparison over the result sees only what else differs. A pointer running holds no such
    certificate for is left as it is: a different certificate is a difference.

    *nvram_dir* is the device's `dir nvram:` read: a pointer whose file it lists is
    ``present``; one it does not list is ``missing`` (the device would boot without it), named
    by the caller. ``{"running": <text>, "present": [...], "missing": [...]}``, each entry
    :func:`certificate_pointers`' shape."""
    lines = (running or "").splitlines()
    listed = nvram_files(nvram_dir)
    present, missing = [], []
    for ptr in certificate_pointers(startup):
        start = next((i for i, l in enumerate(lines)
                      if not l[:1].isspace() and l.strip() == ptr["chain"]), None)
        if start is None:
            continue
        i, at = start + 1, None
        while i < len(lines) and (lines[i][:1].isspace() or lines[i].strip() == "quit"):
            if " ".join(lines[i].split()) == ptr["certificate"]:
                at = i
                break
            i += 1
        if at is None:
            continue
        depth = len(lines[at]) - len(lines[at].lstrip())
        end = at + 1
        while end < len(lines) and lines[end].strip() and (
                len(lines[end]) - len(lines[end].lstrip()) > depth
                or lines[end].strip() == "quit"):
            end += 1
        if end == at + 1:
            continue                                   # no body: not the inline form
        lines[at:end] = [ptr["line"]]
        (present if ptr["file"][len("nvram:"):] in listed else missing).append(ptr)
    return {"running": "\n".join(lines), "present": present, "missing": missing}

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


def excluded_unrenderable(text: str) -> list:
    """Name every block :func:`strip_for_roundtrip` removes from both sides.

    The exclusion is right — a certificate body cannot be reproduced from
    intent, the same argument as a ``$9$`` hash — but it happens on *both*
    sides of the comparison, so the resulting ``modeled_coverage: 100.0`` with
    ``unmodeled: []`` reads exactly like "everything in this config is
    modelled". On r2 that hid two ``crypto pki certificate chain`` blocks:
    not modelled, not unmodelled, not counted.

    Returned as **names, not a count**. A bare number recreates the problem one
    level up: "2 blocks excluded" is no more answerable than "100%".

    Information, never a gate. ``template_report`` decides deployability;
    this says what the figure beside it did not examine.
    """
    found, in_block, in_banner, interface, section = [], False, False, "", ""
    serial = _device_serial(text)

    for line in (text or "").splitlines():
        stripped = line.strip()

        if in_banner:
            if "^C" in line or stripped == "!":
                in_banner = False
            continue

        if any(stripped.startswith(p) for p in _BANNER_OPENERS):
            found.append(stripped)
            in_banner = line.count("^C") < 2
            continue

        if in_block:
            if line.startswith((" ", "\t")) or stripped == "quit":
                continue
            in_block = False

        if _opens_device_owned(stripped, line):
            found.append(stripped)
            in_block = True
            continue

        if not line[:1].isspace():
            section = stripped
            interface = stripped[len("interface "):] if stripped.startswith("interface ") else ""
        elif _autoinstall_client_id(line, interface, serial):
            found.append(f"interface {interface}: {stripped}")
        elif _bgp_own(line, section):
            found.append(f"{section}: {stripped}")

    return found


def strip_for_roundtrip(text: str) -> list:
    """Remove lines a template cannot render, for round-trip comparison.

    Removes certificate chains and their hex bodies, the device's own
    self-signed trustpoint (C397), AutoInstall's client-id (C485), IOS-XE's
    own ``bgp log-neighbor-changes`` (C1182), banner blocks, boot markers, licence UDI
    lines, and the ``show version`` preamble NMAS prefixes
    to a golden config. Everything else is left alone — including lines the
    parser does not yet model, which must stay visible so coverage is honest.
    """
    out = []
    in_block = False
    in_banner = False
    interface = section = ""
    serial = _device_serial(text)

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

        if _opens_device_owned(stripped, line):
            in_block = True
            continue

        if not line[:1].isspace():
            section = stripped
            interface = stripped[len("interface "):] if stripped.startswith("interface ") else ""
        elif _autoinstall_client_id(line, interface, serial):
            continue                        # AutoInstall's own (C485, C1479): never intent, never sent
        elif _bgp_own(line, section):
            continue                        # IOS-XE's own (C1182): never intent, never sent

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
