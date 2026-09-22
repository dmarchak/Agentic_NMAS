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

Three checkers now, and the middle one is why:

* ``node --check`` when node exists, which is the real answer;
* **a real parse via dukpy**, which is pinned in ``requirements.txt`` and so
  runs everywhere;
* a string-literal scanner, kept because it names the original defect
  precisely.

**The dukpy parse was added after a second defect shipped past this file.**
An edit replaced ``function loadGoldenRepoPanel(`` in a file where the text
was ``async function loadGoldenRepoPanel(`` — so the ``async`` stayed behind
and attached to the newly inserted function above it. The result was a
function using ``await`` nine times without ``async``: a hard SyntaxError,
which kills the **entire script block**, so every function in it became
undefined and the Remote card reported ``_gLastPush is not defined``.

The string scanner could not see it — it looks for unterminated quotes — and
``node --check`` is skipped on both the development machine and the
deployment host. So the file that exists to catch "the JavaScript does not
parse" was, for this class, skipped everywhere. dukpy parses it for real and
rejects exactly that construct.
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


# ---------------------------------------------------------------------------
# A real parse, everywhere
# ---------------------------------------------------------------------------

def _parses(body: str):
    """``(ok, message)`` from an actual JavaScript parser.

    Wrapped in a function so a block's top-level ``return`` or ``await`` is
    legal where it is legal, and illegal where it is not — which is the
    distinction that matters here.
    """
    import dukpy

    try:
        dukpy.evaljs("function __syntax_check_wrapper__() {\n" + body + "\n}")
        return True, ""
    except Exception as exc:                  # noqa: BLE001
        return False, str(exc).splitlines()[0]


class TestEveryInlineScriptParses:
    """Not skipped anywhere. dukpy is pinned, node is not installed."""

    def test_dukpy_is_available(self):
        """A parser that is not there checks nothing, and this file has
        already been silently skipped once."""
        import dukpy

        assert dukpy.evaljs("1 + 1") == 2

    def test_the_parser_rejects_the_defect_that_shipped(self):
        """`await` without `async` — the construct that killed a whole block
        and left every function in it undefined."""
        ok, message = _parses("function f() { await g(); }")
        assert not ok, "the parser accepts the bug it was added to catch"
        assert "SyntaxError" in message

    def test_the_parser_accepts_what_this_codebase_writes(self):
        """A checker that rejects valid code gets removed. Template
        literals, arrows, destructuring, async/await, optional chaining."""
        for source in ("const f = (a) => `x ${a} y`;",
                       "const [a, b] = [1, 2];",
                       "async function f() { await g(); }",
                       "var y = a?.b;"):
            ok, message = _parses(source)
            assert ok, f"{source!r} rejected: {message}"

    def test_every_block_in_the_RENDERED_page_parses(self):
        """The rendered page, not the template source.

        A template is not JavaScript. `window.applyAiEnabled({{ ai_enabled |
        tojson }})` is valid Jinja and, read as JS, is an object literal with
        an invalid property name — so parsing the raw file reports a defect
        in correct code. The browser receives the *rendered* output, so that
        is what has to parse.

        Rendering `/` covers base.html, index.html and every partial included
        from them, which is where all of this project's inline script lives.
        A template reachable only from another route is not covered here; the
        string scanner above still walks every file on disk.
        """
        import re as _re

        import app as nmas

        html = nmas.app.test_client().get("/").get_data(as_text=True)
        failures = []
        for match in _re.finditer(r"<script([^>]*)>(.*?)</script>", html, _re.S):
            attrs, body = match.group(1), match.group(2)
            if "src=" in attrs or "application/json" in attrs:
                continue
            ok, message = _parses(body)
            if not ok:
                line = html[:match.start()].count("\n") + 1
                failures.append(f"rendered page line {line} — {message}")
        assert not failures, "\n".join(failures)

    def test_the_rendered_page_actually_had_scripts(self):
        """An empty sweep would make the check above vacuously true."""
        import re as _re

        import app as nmas

        html = nmas.app.test_client().get("/").get_data(as_text=True)
        inline = [m for m in _re.finditer(r"<script([^>]*)>(.*?)</script>",
                                          html, _re.S)
                  if "src=" not in m.group(1)]
        assert len(inline) >= 5, len(inline)
