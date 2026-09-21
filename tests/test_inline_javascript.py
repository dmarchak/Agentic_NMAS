"""Every inline <script> in every template must be syntactically valid.

A single-quoted JS string spanned a line break in the Remote card:

    kinds.map(k => `  ${k} x${counts[k]}`).join('
    ') +

The browser rejected the entire script block, which took the Baselines loader
with it — so the panel that warns about credential-regressing baselines
stopped rendering because of an unrelated card added above it.

It reached a deployed page past 1656 tests, none of which had ever parsed a
line of this JavaScript. Python tests had checked that markup *contained* the
right strings; nothing checked the result was a program.

Two checkers, deliberately:

* ``node --check`` when node exists, which is the real answer;
* a string-literal scanner that always runs, because node is not installed on
  the development machine OR on the deployment host, and a test that is
  skipped everywhere protects nothing.

The scanner only looks for the defect that actually happened — a quoted
string opened and not closed before the end of its line. That is a narrow
check, and narrow is the point: it runs everywhere and cannot be waved away.
"""

import os
import re
import shutil
import subprocess
import tempfile

import pytest

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "templates")

#: `/` begins a regex rather than a division when the previous meaningful
#: character is one of these. Without this the scanner trips over
#: `/[&<>"']/g`, which legitimately contains a quote.
REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%<>~^")


def _templates():
    for root, _dirs, files in os.walk(TEMPLATES):
        for name in sorted(files):
            if name.endswith(".html"):
                yield os.path.join(root, name)


def _scripts(path):
    """Inline script bodies, skipping `src=` includes and JSON blocks."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for match in re.finditer(r"<script([^>]*)>(.*?)</script>", text, re.S):
        attrs, body = match.group(1), match.group(2)
        if "src=" in attrs or "application/json" in attrs:
            continue
        line = text[:match.start()].count("\n") + 1
        yield line, body


def unterminated_string_lines(source: str):
    """Line numbers where a ' or " string is opened and never closed.

    Tracks comments, template literals and regex literals well enough not to
    cry wolf on the ones this codebase actually contains.
    """
    bad = []
    i, line, n = 0, 1, len(source)
    quote = None            # the quote character of an open '..' or ".." string
    quote_line = 0
    prev_meaningful = ""

    while i < n:
        ch = source[i]

        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == "\n":
                bad.append(quote_line)
                quote = None
                line += 1
                i += 1
                continue
            if ch == quote:
                quote = None
            i += 1
            continue

        two = source[i:i + 2]
        if two == "//":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if two == "/*":
            end = source.find("*/", i + 2)
            end = n if end == -1 else end + 2
            line += source.count("\n", i, end)
            i = end
            continue
        if ch == "`":                       # template literal: newlines are legal
            i += 1
            while i < n:
                if source[i] == "\\":
                    i += 2
                    continue
                if source[i] == "\n":
                    line += 1
                elif source[i] == "`":
                    i += 1
                    break
                i += 1
            prev_meaningful = "`"
            continue
        if ch == "/" and prev_meaningful in REGEX_PRECEDERS:
            i += 1                          # regex literal
            while i < n and source[i] not in "\n":
                if source[i] == "\\":
                    i += 2
                    continue
                if source[i] == "/":
                    i += 1
                    break
                i += 1
            prev_meaningful = "/"
            continue
        if ch in "'\"":
            quote, quote_line = ch, line
            i += 1
            continue
        if ch == "\n":
            line += 1
        elif not ch.isspace():
            prev_meaningful = ch
        i += 1

    if quote:
        bad.append(quote_line)
    return bad


class TestNoStringLiteralSpansALineBreak:
    """The exact defect, checked everywhere, with no external dependency."""

    def test_every_inline_script_in_every_template(self):
        offenders = []
        for path in _templates():
            for start, body in _scripts(path):
                for relative in unterminated_string_lines(body):
                    offenders.append(
                        f"{os.path.relpath(path, TEMPLATES)}:"
                        f"{start + relative - 1}")
        assert not offenders, (
            "a quoted string is opened and not closed on the same line — the "
            f"browser rejects the whole block: {offenders}")

    def test_the_scanner_catches_the_defect_it_was_written_for(self):
        """Verbatim, so the checker cannot quietly stop working.

        It reports the opening line and then cascades, because the closing
        quote on the next line opens a string of its own. Reporting the first
        line is what matters; the cascade is inherent to recovering at the
        newline and is not worth suppressing.
        """
        broken = "const a = ['x'].join('\n');\n"
        found = unterminated_string_lines(broken)
        assert found, "the defect that broke a deployed page went unnoticed"
        assert found[0] == 1

    def test_the_scanner_allows_a_template_literal_across_lines(self):
        ok = "const a = `line one\nline two`;\n"
        assert unterminated_string_lines(ok) == []

    def test_the_scanner_allows_a_quote_inside_a_regex(self):
        """`/[&<>\"']/g` is real code in this codebase."""
        ok = "s.replace(/[&<>\"']/g, c => c);\n"
        assert unterminated_string_lines(ok) == []

    def test_the_scanner_allows_an_escaped_quote(self):
        ok = "const a = 'it\\'s fine';\n"
        assert unterminated_string_lines(ok) == []

    def test_the_scanner_ignores_comments(self):
        ok = "// it's a comment\nconst a = 1;\n"
        assert unterminated_string_lines(ok) == []


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node is not installed; the scanner above still runs")
class TestNodeParsesEveryInlineScript:
    """The real answer, when the tool is available."""

    def test_every_inline_script_parses(self):
        failures = []
        for path in _templates():
            for start, body in _scripts(path):
                with tempfile.NamedTemporaryFile(
                        "w", suffix=".js", delete=False, encoding="utf-8") as fh:
                    fh.write(body)
                    tmp = fh.name
                try:
                    proc = subprocess.run(["node", "--check", tmp],
                                          capture_output=True, text=True,
                                          timeout=30)
                    if proc.returncode != 0:
                        first = (proc.stderr or "").strip().splitlines()
                        failures.append(
                            f"{os.path.relpath(path, TEMPLATES)} "
                            f"(script at line {start}): "
                            f"{first[-1] if first else 'syntax error'}")
                finally:
                    os.unlink(tmp)
        assert not failures, failures
