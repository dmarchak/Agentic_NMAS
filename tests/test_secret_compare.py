"""Secrets compared by keyed hash (C1792's design, built for C1693's Normalise proof; C924's
baseline comparison reuses it): `modules/secret_compare.py`.

- What is compared is exactly what is masked: each line's found values, put back as
  placeholders, are `redact.redact_text`'s output byte for byte, on every secret shape the
  masking knows (its own canary lines, which are the shapes Mercury itself emits) and on r2's
  real golden.
- Equal values are "identical"; a value that moved inside a secret position is named by its
  line and masked text, never its value, whether the position is syntactic or a known value.
- Lines pair by their masked text, so two texts whose lines moved still pair; a masked line
  with no partner is said apart, by side.
- Nothing returned holds a value or a hash: counts, line numbers and masked text only.
- The key is random per process and in memory only.
"""

import os

import pytest

from modules import redact, secret_compare as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: The masking's own lines, one per secret shape Mercury emits (`redact.CANARY_LINES`).
LINES = [line for _label, line in redact.CANARY_LINES]
TOKENS = list(redact.CANARY_TOKENS.values())


def _golden():
    with open(os.path.join(ROOT, "tests", "fixtures", "committed", "r2.cfg"),
              encoding="utf-8") as fh:
        return fh.read()


class TestWhatIsComparedIsWhatIsMasked:
    @pytest.mark.parametrize("line", LINES + ["no secret here", "interface Loopback0",
                                              " password 7 0822455D0A16",
                                              "snmp-server community <redacted:snmp_community> RO"])
    def test_each_line_masks_as_redact_text_does(self, line):
        masked, values = S.masked_values(line)
        assert masked == redact.redact_text(line, {})
        assert all(v not in masked for v in values)
        assert bool(values) == (masked != line)

    def test_a_known_value_is_found_where_it_stands(self):
        known = {"LongKnownValue99": "snmp_community_ro"}
        pattern, table = redact._compile(known)
        line = "banner motd ^LongKnownValue99^"
        masked, values = S.masked_values(line, pattern, table)
        assert masked == redact.redact_text(line, known)
        assert values == ["LongKnownValue99"]

    def test_r2s_golden_lines_mask_alike(self):
        """r2's real golden (its secrets already placeholders, which are left alone)."""
        checked = 0
        for line in _golden().splitlines():
            assert S.masked_values(line)[0] == redact.redact_text(line, {})
            checked += 1
        assert checked > 100


class TestTheComparison:
    def test_identical_values_are_identical(self):
        text = "\n".join(LINES) + "\n"
        got = S.compare(text, text, values={})
        assert got["compared"] == len(LINES) and got["identical"] == len(LINES)
        assert got["differs"] == [] and got["unpaired"] == []
        assert [p["line"] for p in got["paired"]] == list(range(1, len(LINES) + 1))

    @pytest.mark.parametrize("index", range(len(LINES)))
    def test_a_value_that_moved_is_named_by_line_and_masked_text(self, index):
        before = "\n".join(LINES)
        token = TOKENS[index]
        after = before.replace(token, token + "X")
        got = S.compare(before, after, values={})
        assert got["compared"] == len(LINES) and got["identical"] == len(LINES) - 1
        assert got["differs"] == [{"line": index + 1,
                                   "masked": redact.redact_text(LINES[index], {})}]
        assert token not in repr(got) and token + "X" not in repr(got)

    def test_a_short_secret_is_compared_too(self):
        """A 6-character SNMP community: below value masking's floor, in its position."""
        got = S.compare("snmp-server community abc123 RO\n", "snmp-server community abc124 RO\n",
                        values={})
        assert got["compared"] == 1 and got["identical"] == 0

    def test_a_known_value_that_moved_is_found(self):
        known = {"LongKnownValue99": "x", "LongKnownValue98": "x"}
        got = S.compare("banner motd ^LongKnownValue99^\n", "banner motd ^LongKnownValue98^\n",
                        values=known)
        assert got["compared"] == 1 and got["identical"] == 0

    def test_lines_pair_by_their_masked_text(self):
        before = "hostname r2\n" + "\n".join(LINES) + "\n"
        after = "\n".join(reversed(LINES)) + "\nhostname r2\n"
        got = S.compare(before, after, values={})
        assert got["compared"] == len(LINES) == got["identical"]

    def test_a_masked_line_with_no_partner_is_said_by_side(self):
        before = LINES[0] + "\n" + LINES[3] + "\n"
        after = LINES[0] + "\n"
        got = S.compare(before, after, values={})
        assert got["compared"] == 1 and got["unpaired"] == [
            {"side": "before", "line": 2, "masked": redact.redact_text(LINES[3], {})}]
        got = S.compare(after, before, values={})
        assert got["unpaired"] == [
            {"side": "after", "line": 2, "masked": redact.redact_text(LINES[3], {})}]

    def test_an_unpaired_line_does_not_stop_the_lines_after_it(self):
        before = LINES[0] + "\n"
        after = LINES[3] + "\n" + LINES[0].replace("A1", "A9") + "\n"
        got = S.compare(before, after, values={})
        assert got["compared"] == 1 and got["identical"] == 0
        assert got["differs"] == [{"line": 2, "masked": redact.redact_text(LINES[0], {})}]
        assert got["paired"] == [{"line": 2, "masked": redact.redact_text(LINES[0], {})}]

    def test_the_unpaired_are_in_order_by_side_then_line(self):
        """Grouped by masked text inside, said in the order a person reads them."""
        before = "\n".join([LINES[0], LINES[3], LINES[0].replace("A1", "A2")]) + "\n"
        after = LINES[4] + "\n" + LINES[1] + "\n"
        got = S.compare(before, after, values={})
        assert [(u["side"], u["line"]) for u in got["unpaired"]] == [
            ("after", 1), ("after", 2), ("before", 1), ("before", 2), ("before", 3)]

    def test_the_store_s_known_values_are_used_when_none_are_given(self, monkeypatch):
        monkeypatch.setattr(redact, "known_secret_values",
                            lambda: {"LongKnownValue99": "x", "LongKnownValue98": "x"})
        got = S.compare("motd LongKnownValue99\n", "motd LongKnownValue98\n")
        assert got["compared"] == 1 and got["identical"] == 0


class TestNothingLeaves:
    def test_the_answer_holds_no_value_and_no_hash(self):
        before = "\n".join(LINES)
        after = before.replace("CanaryTokenD4", "CanaryTokenD5")
        got = S.compare(before, after, values={})

        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    yield from walk(v)
            elif isinstance(node, list):
                for v in node:
                    yield from walk(v)
            else:
                yield node
        leaves = list(walk(got))
        assert leaves and all(isinstance(v, (int, str)) for v in leaves), \
            "no bytes: no digest is returned"
        for token in TOKENS + ["CanaryTokenD5"]:
            assert token not in repr(got)

    def test_the_key_is_random_and_32_bytes(self):
        assert isinstance(S._KEY, bytes) and len(S._KEY) == 32
        assert S._digest("a") != S._digest("b") and S._digest("a") == S._digest("a")
        import hashlib
        assert S._digest("a") != hashlib.sha256(b"a").digest(), "keyed, not a plain hash"
