"""C2820 (the plain-language survey, item 9's word, 2026-11-24; the week plan's Stage 5): a
device off its golden or its intent is said to DIFFER, never to have "departed". No string
self-healing draws or records (every string constant in modules/heal/*.py but docstrings) says
"departed"; the scan finds a planted one and counts its population."""
import ast

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORD = re.compile(r"\bdeparted\b", re.I)


def _said(source: str) -> list:
    """Every string constant of *source* holding the word, docstrings left out: (line, text)."""
    tree = ast.parse(source)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
            and WORD.search(n.value)]


def _heal_sources() -> dict:
    from tests import source_index
    return {os.path.relpath(p, ROOT): open(p, encoding="utf-8").read()
            for p in source_index.tracked("modules/heal", suffix=".py", recursive=False)}


def test_no_self_healing_words_say_departed():
    sources = _heal_sources()
    assert len(sources) > 30, "the population: every module of modules/heal"
    found = {path: _said(text) for path, text in sources.items()}
    found = {p: hits for p, hits in found.items() if hits}
    assert not found, f"self-healing's words still say 'departed': {found}"


def test_the_scan_finds_a_planted_word_and_leaves_docstrings_out():
    planted = ('"""It departed, says the docstring."""\n'
               'WORDS = {"drift": "{device} departed from its golden"}\n'
               'def f():\n    """departed here too, a docstring"""\n    return f"x {1} departed"\n')
    assert [line for line, _ in _said(planted)] == [2, 5], _said(planted)
