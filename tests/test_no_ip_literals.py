"""Constraint 3: the new packages must stay network-agnostic.

Every endpoint, credential, query template, and identity mapping is set by the
user in Settings. A hardcoded IPv4 literal in these packages means someone's
lab address leaked into the tool, so this test fails on any it finds.

Documentation-range addresses from RFC 5737 (192.0.2.0/24, 198.51.100.0/24,
203.0.113.0/24) are allowed in docstrings and examples, as are the structural
non-addresses (0.0.0.0 for bind-all, 127.0.0.1 for loopback) and version-like
strings. Everything else is a finding.
"""

import ipaddress
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Packages introduced by the NSoT work. modules/nsot/ arrives in later phases;
#: it is listed now so it is covered the moment it exists.
SCANNED_PACKAGES = (
    "modules/integrations",
    "modules/nsot",
    "routes",
)

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

#: Structural addresses that carry no network-specific meaning.
ALLOWED_EXACT = {
    "0.0.0.0",        # bind-all
    "127.0.0.1",      # loopback
    "255.255.255.255",
    "8.8.8.8",        # only if used as an illustrative public resolver
}

#: RFC 5737 documentation ranges, safe to use in examples.
DOC_NETWORKS = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
)


def _is_allowed(candidate: str) -> bool:
    if candidate in ALLOWED_EXACT:
        return True
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError:
        return True          # e.g. a version string like 1.2.3.4444 — not an IP
    return any(addr in net for net in DOC_NETWORKS)


def _python_files():
    for package in SCANNED_PACKAGES:
        root = REPO_ROOT / package
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


def test_scanned_packages_exist():
    """At least one scanned package must be present, or this test proves nothing."""
    assert any((REPO_ROOT / p).is_dir() for p in SCANNED_PACKAGES), (
        "None of the scanned packages exist — the scanner would pass vacuously"
    )


@pytest.mark.parametrize("path", list(_python_files()),
                         ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_ipv4_literals(path):
    findings = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for match in _IPV4_RE.findall(line):
            if not _is_allowed(match):
                findings.append(f"  {path.relative_to(REPO_ROOT)}:{lineno}: {match}")
    assert not findings, (
        "Hardcoded IPv4 literal(s) found — these belong in Settings:\n"
        + "\n".join(findings)
    )


def test_scanner_catches_a_planted_literal(tmp_path):
    """The scanner must actually detect a literal, not pass by accident."""
    planted = tmp_path / "leaky.py"
    planted.write_text('NETBOX = "http://10.255.1.10:8000"\n', encoding="utf-8")
    found = [m for m in _IPV4_RE.findall(planted.read_text()) if not _is_allowed(m)]
    assert found == ["10.255.1.10"]


def test_documentation_addresses_are_allowed():
    assert _is_allowed("203.0.113.1")
    assert _is_allowed("192.0.2.50")
    assert _is_allowed("0.0.0.0")
    assert not _is_allowed("192.168.0.30")
    assert not _is_allowed("10.255.1.10")
