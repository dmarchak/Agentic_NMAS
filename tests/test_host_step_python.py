"""Every host step's embedded Python compiles (C744; 2026-10-13: c734-sealed-store-counts.sh
stopped on the host with "SyntaxError: unexpected character after line continuation character").

Its Python sat in a bash single-quoted variable, where `\\"` stays two characters, so
`f"{check[\\"verdict\\"]}"` reached Python with a stray backslash in an expression: no version
of Python accepts it, and nothing in the suite compiled a host step's Python, so the operator
found it on the host. This compiles each block exactly as bash hands it over:

- a heredoc tagged `PY` (`cat > "$DIR/x.py" <<'PY'` … `PY`): quoted, so its text is literal;
- a single-quoted variable assignment alone on its line (`COUNT='` … `'`), run with `-c`: a
  single-quoted string is literal too, up to the closing quote alone on its line.

Python passed inline through `-c "…"` inside a check's command is not read here: it is a
double-quoted string inside a single-quoted one, and only bash reads that faithfully.
"""

import os
import re

import pytest

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_HEREDOC = re.compile(r"<<'PY'\s*$")
_ASSIGN = re.compile(r"^([A-Z_][A-Z0-9_]*)='$")


def blocks(path: str) -> list:
    """``[(name, source)]``: each embedded Python block of the script at *path*, as bash
    would hand it to the interpreter."""
    lines = open(path, encoding="utf-8").read().split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        m = _ASSIGN.match(line)
        end = "PY" if _HEREDOC.search(line) else "'" if m else None
        if end is None:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and lines[j] != end:
            j += 1
        name = f"{os.path.basename(path)}:{i + 1}:" + (m.group(1) if m else "PY")
        out.append((name, "\n".join(lines[i + 1:j]) + "\n"))
        i = j + 1
    return out


def every_block() -> list:
    # What the repository holds (C585), never what is on disk.
    return [b for p in sorted(tracked("scripts/host-steps", suffix=".sh"))
            for b in blocks(os.path.join(ROOT, p))]


def test_the_scan_finds_the_blocks():
    """A floor, so a scan that finds nothing cannot pass: five scripts write a `PY` heredoc and
    c734's counts are one single-quoted block (2026-10-13)."""
    names = [n for n, _src in every_block()]
    assert len(names) >= 6, names
    assert any(n.startswith("c734-sealed-store-counts.sh:") and n.endswith(":COUNT")
               for n in names), names


def test_the_scan_reads_a_block_as_bash_hands_it_over(tmp_path):
    """The planted case: a single-quoted block keeps `\\"` as two characters, so it fails to
    compile, as it did on the host."""
    f = tmp_path / "planted.sh"
    f.write_text("X='\nprint(f\"{d[\\\"k\\\"]}\")\n'\n", encoding="utf-8")
    [(name, src)] = blocks(str(f))
    assert name == "planted.sh:1:X"
    with pytest.raises(SyntaxError):
        compile(src, name, "exec")


@pytest.mark.parametrize("name,src", every_block(), ids=[n for n, _s in every_block()])
def test_each_block_compiles(name, src):
    compile(src, name, "exec")
