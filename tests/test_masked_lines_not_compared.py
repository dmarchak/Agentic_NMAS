"""A masked line cannot be compared, and the panel must say so.

The preview renders with secrets masked (`render_artifact.MASK`) while the
capture holds the real value, so **every secret-bearing line differs for
ever**. That is not a defect in masking -- `intended/` and previews are masked
precisely so neither can be a deploy source -- but a permanent difference is
one people learn to scroll past, in the section where real drift would appear.

Neutralising them is only half the job. A preview that goes clean by hiding
what it could not check is a **stronger** claim than the one it is entitled
to make, and that is the trap this project keeps hitting: a protection that
reads as present because nothing says it is absent. So the count is shown.
"""

import pytest

from modules.nsot.render_artifact import MASK
from modules.nsot.roundtrip import MASKED_TOKEN, canonical_diff

from tests.js_source import read_shipped

GOLDEN = """hostname s1
!
snmp-server community s3cr3tRO RO
snmp-server host 10.0.0.1 s3cr3tRO
!
username admin privilege 15 secret 9 $9$saltsalt$hashhash
!
end
"""

RENDER = f"""hostname s1
!
snmp-server community {MASK} RO
snmp-server host 10.0.0.1 {MASK}
!
username admin privilege 15 secret 9 {MASK}
!
end
"""


class TestMaskedLinesAreNotReportedAsDifferences:
    def test_an_otherwise_identical_config_is_clean(self):
        diff, masked = canonical_diff(GOLDEN, RENDER, report_masked=True)
        assert diff == "", diff
        assert masked == 3

    def test_each_masked_line_is_counted(self):
        _diff, masked = canonical_diff(GOLDEN, RENDER, report_masked=True)
        assert masked == 3, "three secret-bearing lines, three uncomparable"

    def test_the_count_is_not_returned_unless_asked(self):
        """The signature stays compatible for callers that only want a diff."""
        assert isinstance(canonical_diff(GOLDEN, RENDER), str)


class TestOnlyTheVALUEIsUnknowable:
    """The line itself stays under comparison."""

    def test_a_changed_access_mode_still_shows(self):
        """`RO` -> `RW` is a different line, not a different secret."""
        render = RENDER.replace(f"community {MASK} RO", f"community {MASK} RW")
        diff, masked = canonical_diff(GOLDEN, render, report_masked=True)
        assert diff != ""
        assert "RW" in diff
        assert masked == 2, "the other two still pair"

    def test_a_changed_trap_host_still_shows(self):
        render = RENDER.replace("snmp-server host 10.0.0.1",
                                "snmp-server host 10.0.0.9")
        diff, _masked = canonical_diff(GOLDEN, render, report_masked=True)
        assert "10.0.0.9" in diff

    def test_a_changed_username_still_shows(self):
        render = RENDER.replace("username admin privilege 15",
                                "username admin privilege 1")
        diff, _masked = canonical_diff(GOLDEN, render, report_masked=True)
        assert diff != ""

    def test_a_masked_line_the_capture_lacks_entirely_shows(self):
        golden = GOLDEN.replace("snmp-server host 10.0.0.1 s3cr3tRO\n", "")
        diff, masked = canonical_diff(golden, RENDER, report_masked=True)
        assert "snmp-server host" in diff
        assert masked == 2

    def test_an_unmasked_difference_still_shows(self):
        render = RENDER.replace("hostname s1", "hostname s1-renamed")
        diff, _masked = canonical_diff(GOLDEN, render, report_masked=True)
        assert "s1-renamed" in diff


class TestTheNeutralisedLineSaysWhatHappened:
    def test_it_reads_as_not_compared_not_as_a_value(self):
        """`render_artifact.MASK` is a run of bullets, which in a diff looks
        like a value that differs from the real one."""
        diff, _masked = canonical_diff(
            GOLDEN, RENDER.replace("hostname s1", "hostname other"),
            report_masked=True)
        assert MASKED_TOKEN in diff
        assert "not compared" in MASKED_TOKEN

    def test_an_empty_value_does_not_pair_with_anything(self):
        """Without a length check the mask could stand for nothing and pair
        with a line that merely shares a prefix and suffix."""
        golden = "snmp-server community  RO\n"
        render = f"snmp-server community {MASK} RO\n"
        _diff, masked = canonical_diff(golden, render, report_masked=True)
        assert masked == 0


class TestThePanelSaysTheComparisonWasIncomplete:
    """A gap that is named is a finding; one implied by masking is a trap."""

    def _partial(self):
        import os

        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "templates", "partials",
            "template_editor.html")
        return read_shipped(path)

    def test_the_route_returns_the_count(self):
        from tests.astcheck import code_of

        from routes import templates as route_module

        assert "masked_not_compared" in code_of(route_module.preview)

    def test_the_panel_renders_it(self):
        source = self._partial()
        assert "masked_not_compared" in source
        assert "could not be compared" in source

    def test_it_says_a_hand_change_would_not_show(self):
        """The specific consequence, not a vague caveat."""
        assert "changed by hand on" in self._partial()

    def test_it_names_where_the_real_comparison_happens(self):
        """Otherwise the note reads as "nothing checks this", which is worse
        than the truth and equally misleading."""
        assert "Drift check compares the real values" in self._partial()

    def test_it_is_silent_when_nothing_was_masked(self):
        source = self._partial()
        note = source[source.index("const _tMaskedNote"):]
        note = note[:note.index("};")]
        assert "!obj.masked_not_compared" in note
