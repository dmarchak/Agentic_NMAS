"""Equivalence of the consolidated filters with the pre-consolidation behaviour.

Six call sites each carried a hardcoded prefix tuple. They were not copies of
one list — collapsing them into a single filter would change drift results and
could break config push. These tests pin each site's *exact* previous tuple, so
a future "tidy-up" that merges them fails loudly here.

The tuples below are transcribed from the code as it stood before Phase 2.
"""

import pytest

from modules.nsot import normalize

# ── Verbatim pre-consolidation tuples ───────────────────────────────────────

LEGACY_DRIFT = (
    "! Last configuration", "! NVRAM config", "! No configuration",
    "! Golden config", "! Saved:", "! Source:",
    "Building configuration", "Current configuration",
    "ntp clock-period", "upgrade fpd", "version ",
)

LEGACY_PIPELINE = (
    "! Last configuration", "! NVRAM config", "! No configuration",
    "! Golden config", "! Pre-change", "! Saved:", "! Source:",
    "Building configuration", "Current configuration",
    "ntp clock-period", "upgrade fpd", "version ",
)

LEGACY_CONFIG_GIT = (
    "! Last configuration", "! NVRAM config", "! No configuration",
    "Building configuration", "Current configuration", "ntp clock-period",
    "! Golden config", "! Saved:", "! Source:", "! Pre-change",
)

LEGACY_PUSH = [
    "Building configuration", "Current configuration",
    "Last configuration change", "NVRAM config last updated",
    "!", "end", "version ",
]

SAMPLE = """! Golden config — R1 (203.0.113.1)
! Saved: 2026-09-20 01:00:00
! Source: show startup-config
!
Building configuration...

Current configuration : 4096 bytes
!
! Last configuration change at 10:00:00 UTC
! NVRAM config last updated at 10:00:00 UTC
version 17.6
upgrade fpd auto
!
hostname R1
!
ntp clock-period 17179869
ntp server 203.0.113.123
!
interface GigabitEthernet1
 ip address 203.0.113.1 255.255.255.0
 no shutdown
!
! Pre-change snapshot
router ospf 1
 network 203.0.113.0 0.0.0.255 area 0
!
end
"""


class TestTupleContents:
    """The consolidated tuples must equal the originals, set for set."""

    def test_diff_tuple_matches_legacy(self):
        assert set(normalize.DIFF_PREFIXES) == set(LEGACY_DRIFT)

    def test_pipeline_tuple_matches_legacy(self):
        assert set(normalize.PIPELINE_DIFF_PREFIXES) == set(LEGACY_PIPELINE)

    def test_repo_tuple_matches_legacy(self):
        assert set(normalize.REPO_PREFIXES) == set(LEGACY_CONFIG_GIT)

    def test_push_tuple_matches_legacy(self):
        assert list(normalize.PUSH_SKIP_PREFIXES) == LEGACY_PUSH

    def test_the_tuples_are_genuinely_different(self):
        """If these ever become equal, the consolidation was wrong, not clever."""
        assert set(normalize.DIFF_PREFIXES) != set(normalize.REPO_PREFIXES)
        assert set(normalize.DIFF_PREFIXES) != set(normalize.PIPELINE_DIFF_PREFIXES)
        assert set(normalize.PUSH_SKIP_PREFIXES) != set(normalize.DIFF_PREFIXES)

    def test_repo_keeps_version_and_upgrade_fpd(self):
        """config_git deliberately retains these; drift deliberately strips them."""
        assert not any(p == "version " for p in normalize.REPO_PREFIXES)
        assert not any(p == "upgrade fpd" for p in normalize.REPO_PREFIXES)
        assert "version " in normalize.DIFF_PREFIXES
        assert "upgrade fpd" in normalize.DIFF_PREFIXES


def _legacy_strip(text, prefixes, drop_blank=True, drop_bang=False):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if drop_blank and not s:
            continue
        if drop_bang and s == "!":
            continue
        if any(s.startswith(p) for p in prefixes):
            continue
        out.append(line)
    return out


class TestOutputEquivalence:
    """Byte-for-byte output equality against the legacy implementations."""

    def test_diff_output_identical(self):
        assert normalize.strip_for_diff(SAMPLE, drop_bang=True) == \
            _legacy_strip(SAMPLE, LEGACY_DRIFT, drop_blank=True, drop_bang=True)

    def test_pipeline_output_identical(self):
        assert normalize.strip_for_diff(SAMPLE, include_pre_change=True, drop_bang=True) == \
            _legacy_strip(SAMPLE, LEGACY_PIPELINE, drop_blank=True, drop_bang=True)

    def test_repo_output_identical(self):
        assert normalize.strip_for_repo(SAMPLE) == \
            _legacy_strip(SAMPLE, LEGACY_CONFIG_GIT, drop_blank=False)

    def test_push_output_identical(self):
        assert normalize.push_safe_lines(SAMPLE) == \
            _legacy_strip(SAMPLE, LEGACY_PUSH, drop_blank=True)


class TestJobsActuallyDiffer:
    """The reason they cannot be merged, demonstrated on real content."""

    def test_push_filter_removes_end(self):
        """`end` mid-config silently truncates a startup-config."""
        assert "end" not in [l.strip() for l in normalize.push_safe_lines(SAMPLE)]

    def test_diff_filter_keeps_end(self):
        """A golden config legitimately ends with `end`; diffing must see it."""
        assert "end" in [l.strip() for l in normalize.strip_for_diff(SAMPLE)]

    def test_repo_keeps_version_line_but_diff_drops_it(self):
        repo = "\n".join(normalize.strip_for_repo(SAMPLE))
        diff = "\n".join(normalize.strip_for_diff(SAMPLE))
        assert "version 17.6" in repo
        assert "version 17.6" not in diff

    def test_nmas_header_always_removed(self):
        for out in (normalize.strip_for_repo(SAMPLE),
                    normalize.strip_for_diff(SAMPLE),
                    normalize.strip_nmas_header(SAMPLE)):
            joined = "\n".join(out)
            assert "! Golden config" not in joined
            assert "! Saved:" not in joined


class TestHelpers:
    def test_has_nmas_header(self):
        assert normalize.has_nmas_header(SAMPLE)
        assert not normalize.has_nmas_header("hostname R1\n")

    def test_empty_input(self):
        assert normalize.strip_for_diff("") == []
        assert normalize.push_safe_lines(None) == []
