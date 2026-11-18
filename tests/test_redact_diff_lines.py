"""A diff's marked line is masked as the configuration line it carries (C3989, found by the
fast-lane correctness review, 2026-11-18): `redact_positional`'s secret patterns are anchored at a
line's start, so a diff's marker before the line (difflib.ndiff's "+ " / "- ", a unified diff's
"+" / "-") let an enable secret, a type-7 or type-0 line password and a plaintext enable
password through unmasked (measured: every one of them, with every marker), in
`command_plan_run.net_zero`'s run-record lines, `intent_normalise`'s differing lines, and any
diff masked as one text. Fixed at the root: every line starting with one marker is masked as the
line after it, its marker kept. Test values only."""
import difflib

import pytest

from modules import redact

#: (a configuration line, the secret in it): the shapes measured leaking, and two that did not.
SECRET_LINES = [
    ("enable secret 5 $1$abcd$efgh", "$1$abcd$efgh"),
    ("enable secret 9 $9$abcdefgh$ijkl", "$9$abcdefgh$ijkl"),
    (" password 7 0822455D0A16", "0822455D0A16"),
    (" password 0 plaintext1", "plaintext1"),
    ("enable password plainpass", "plainpass"),
    ("username u privilege 15 secret 5 $1$aa$bb", "$1$aa$bb"),
    ("snmp-server community s3cretcomm RO", "s3cretcomm"),
]


@pytest.mark.parametrize("line,secret", SECRET_LINES)
@pytest.mark.parametrize("marker", ["+ ", "- ", "+", "-"])
def test_a_marked_line_is_masked_as_its_configuration_line(line, secret, marker):
    got = redact.redact_text(marker + line)
    assert secret not in got, got
    assert got.startswith(marker), "the diff's marker is kept"
    assert got == marker + redact.redact_text(line)


def test_a_whole_unified_diff_is_masked_line_by_line():
    before = "hostname edge1\nline vty 0 4\n password 7 0822455D0A16\nenable secret 5 $1$ab$cd\n"
    after = "hostname edge1\nline vty 0 4\n password 7 1511021F0725\nenable secret 5 $1$ef$gh\n"
    diff = "\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                         "before", "after", lineterm=""))
    got = redact.redact_text(diff)
    for secret in ("0822455D0A16", "1511021F0725", "$1$ab$cd", "$1$ef$gh"):
        assert secret not in got, got
    assert got.splitlines()[0] == "--- before" and got.splitlines()[1] == "+++ after"


def test_lines_with_no_secret_and_diff_headers_are_unchanged():
    for text in ("+ interface Gi0/1", "-hostname edge1", "+++ after", "--- before",
                 "+-+ banner", "plain prose - with a dash"):
        assert redact.redact_text(text, values={}) == text, text


def test_nothing_to_mask_is_returned_as_it_came():
    assert redact.redact_positional("") == ""
    assert redact.redact_positional(None) is None


def test_net_zero_masks_secret_lines_with_their_marker():
    from modules.nsot.command_plan_run import net_zero
    before = "line vty 0 4\n password 7 0822455D0A16\nenable secret 5 $1$ab$cd\n"
    after = "line vty 0 4\n password 7 1511021F0725\nenable secret 5 $1$ef$gh\n"
    got = net_zero(before, after)
    assert len(got) == 4, got
    joined = "\n".join(got)
    for secret in ("0822455D0A16", "1511021F0725", "$1$ab$cd", "$1$ef$gh"):
        assert secret not in joined, joined
    assert {g[:2] for g in got} == {"+ ", "- "}
