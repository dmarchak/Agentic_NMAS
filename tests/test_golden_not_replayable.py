"""A golden is not replayable as a startup file as it stands (docs/STARTUP_FROM_GOLDEN.md).

These tests were in tests/test_startup_safety_composite.py, whose other classes tested the
product's lab startup-file checker; C663 took that checker out, and this class, about the
golden's own header and the sendability guard, moved here unchanged but for its addresses
(192.0.2.x).
"""

import pytest


class TestAGoldenIsNotReplayableAsIs:
    """**The assessment's load-bearing measurement**, pinned so it is not
    re-derived — and so it fails if the header ever changes.

    `docs/STARTUP_FROM_GOLDEN.md`. Building startup files from goldens is
    the right direction; a golden **cannot be used as one unmodified**,
    because its own header line carries an em dash and an emulator may replay a
    startup file into a console line by line.

    A platform that loads its startup config as a file would boot the
    identical content, so **one platform can never reveal this** — which is
    why it is a test rather than a probe.
    """

    def test_the_golden_header_is_non_ascii(self):
        import inspect

        from modules.nsot import repo

        src = inspect.getsource(repo)
        assert '! Golden config —' in src, \
            "the header changed; re-derive the assessment before relying on it"

    def test_and_the_sendability_guard_refuses_it(self):
        from modules.nsot.deploy import assert_sendable

        header = "! Golden config — r1 (192.0.2.11)"
        with pytest.raises(Exception) as err:
            assert_sendable([header, "hostname r1", "end"])
        assert "U+2014" in str(err.value) or "ASCII" in str(err.value)

    def test_stripping_the_header_is_what_makes_it_sendable(self):
        """**The floor.** A guard that refused everything would satisfy the
        test above and say nothing about the fix."""
        from modules.nsot.deploy import assert_sendable
        from modules.nsot.normalize import strip_nmas_header

        text = ("! Golden config — r1 (192.0.2.11)\n"
                "hostname r1\ninterface Gi1\nend\n")
        assert_sendable(strip_nmas_header(text))       # must not raise

    def test_push_safe_lines_is_the_WRONG_filter_for_a_startup_file(self):
        """It drops `end`, which a startup config needs. `CLAUDE.md` already
        says the filters are four different jobs and this one is a
        truncation guard for a config-mode push. **A startup file is a
        fifth job**, and reaching for the nearest filter truncates it at
        exactly the line that ends it."""
        from modules.nsot.normalize import push_safe_lines, strip_for_repo

        text = "hostname r1\n!\ninterface Gi1\nend\n"

        assert "end" not in push_safe_lines(text)
        kept = strip_for_repo(text)
        assert "end" in (kept if isinstance(kept, list) else kept.splitlines())
