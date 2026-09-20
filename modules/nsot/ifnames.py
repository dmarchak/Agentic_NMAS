"""nsot/ifnames.py

Canonical interface names.

``Gi0/0`` and ``GigabitEthernet0/0`` are the same interface, but a golden config
uses the long form while CDP/LLDP output and operators use the short one. A
round-trip comparison that treats them as different lines reports false drift on
every abbreviated reference.

Two existing maps in this codebase go long → short for *display*
(``topology._short_if_name`` and ``netbox_client``'s abbreviation table). This
module owns the shared table and derives both directions from it, so the two can
no longer drift apart.
"""

import re

#: (canonical prefix, accepted abbreviations). Longest abbreviations first
#: within each entry so "TenGig" is not swallowed by "Te".
INTERFACE_PREFIXES = (
    ("TenGigabitEthernet",     ("TenGigabitEthernet", "TenGigE", "TenGig", "Te")),
    ("FortyGigabitEthernet",   ("FortyGigabitEthernet", "FortyGigE", "Fo")),
    ("HundredGigE",            ("HundredGigE", "Hu")),
    ("TwentyFiveGigE",         ("TwentyFiveGigE", "Twe")),
    ("GigabitEthernet",        ("GigabitEthernet", "GigEthernet", "GigE", "Gi")),
    ("FastEthernet",           ("FastEthernet", "Fa")),
    ("Ethernet",               ("Ethernet", "Eth", "Et")),
    ("Port-channel",           ("Port-channel", "Po")),
    ("Loopback",               ("Loopback", "Lo")),
    ("Tunnel",                 ("Tunnel", "Tu")),
    ("Vlan",                   ("Vlan", "Vl")),
    ("Serial",                 ("Serial", "Se")),
    ("BDI",                    ("BDI",)),
    ("Multilink",              ("Multilink", "Mu")),
    ("VirtualPortGroup",       ("VirtualPortGroup", "Vi")),
)

#: canonical prefix → shortest display abbreviation
_SHORT_FORM = {canonical: abbrevs[-1] for canonical, abbrevs in INTERFACE_PREFIXES}

# Built longest-first so "TenGigabitEthernet0/1" is not matched as "Te" + junk.
_LOOKUP = sorted(
    ((abbrev, canonical)
     for canonical, abbrevs in INTERFACE_PREFIXES
     for abbrev in abbrevs),
    key=lambda pair: len(pair[0]), reverse=True,
)

_SPLIT_RE = re.compile(r"^([A-Za-z][A-Za-z\-]*)\s*([\d/.:]*)$")


def canonical(name: str) -> str:
    """Expand an interface name to its canonical long form.

    ``Gi0/0`` → ``GigabitEthernet0/0``. An unrecognised name is returned
    unchanged rather than guessed at — a wrong expansion is worse than none.
    """
    if not name:
        return ""
    raw = name.strip()
    match = _SPLIT_RE.match(raw)
    if not match:
        return raw
    word, numbers = match.group(1), match.group(2)

    for abbrev, target in _LOOKUP:
        if word.lower() == abbrev.lower():
            return f"{target}{numbers}"
    return raw


def abbreviate(name: str) -> str:
    """Shorten an interface name for display. ``GigabitEthernet0/0`` → ``Gi0/0``."""
    if not name:
        return ""
    raw = name.strip()
    match = _SPLIT_RE.match(raw)
    if not match:
        return raw
    word, numbers = match.group(1), match.group(2)

    for abbrev, target in _LOOKUP:
        if word.lower() == abbrev.lower():
            return f"{_SHORT_FORM[target]}{numbers}"
    return raw


def same_interface(a: str, b: str) -> bool:
    """True if two names refer to the same interface."""
    return canonical(a).lower() == canonical(b).lower()


_LINE_RE = re.compile(
    r"\b("
    + "|".join(sorted((abbrev for abbrev, _ in _LOOKUP), key=len, reverse=True))
    + r")(\d[\d/.:]*)",
)


def canonicalise_line(line: str) -> str:
    """Expand every interface reference in a config line.

    Applies to lines like ``passive-interface Gi0/2`` and
    ``track 1 interface Gi0/2 line-protocol``, not just interface headers.
    """
    if not line:
        return line
    return _LINE_RE.sub(lambda m: canonical(f"{m.group(1)}{m.group(2)}"), line)
