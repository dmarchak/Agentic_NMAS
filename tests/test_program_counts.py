"""C3413: a program's size is counted as a person reads it (`deploy.config_line_count`: no
blank line, no sub-mode `exit`, no `!`) wherever it is said in words: the NetBox journal entry
(modules/heal/journal.py), History's heal record and dampening's plan words. The journal's
words checked directly; the three modules held by a parsed scan: no f-string that says
"line(s)" counts with `len(`."""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = ("modules/heal/journal.py", "modules/history_sources.py", "modules/heal/dampening.py")


def test_the_journal_counts_the_lines_a_person_reads():
    from modules.heal import journal
    decision = {"id": "hd-1", "program": ["interface Gi1", " description up", " exit", "!"],
                "program_hash": "abc", "kind": "intent", "incident": "hi-1"}
    words = journal.comments("Lab", "r2", decision, "healed", link="")
    assert "(2 line(s))" in words, words


def _len_counts(src: str) -> list:
    """Every f-string saying "line(s)" whose parts call `len(`: (line, text)."""
    out = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.JoinedStr):
            text = "".join(v.value for v in n.values if isinstance(v, ast.Constant))
            calls = [c for v in n.values if isinstance(v, ast.FormattedValue)
                     for c in ast.walk(v.value)
                     if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "len"]
            if "line(s)" in text and calls:
                out.append((n.lineno, text[:60]))
    return out


def test_no_program_count_in_words_counts_every_command():
    assert _len_counts('x = f"{len(p)} line(s), hash"\ny = f"{count(p)} line(s)"\n') == [
        (1, " line(s), hash")], "the scan finds a planted one and leaves the right one"
    found = {m: _len_counts(open(os.path.join(ROOT, m), encoding="utf-8").read())
             for m in MODULES}
    assert not any(found.values()), found
