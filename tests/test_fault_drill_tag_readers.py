"""Who reads a declared fault drill's tag (`modules/fault_drills.py`; the operator's decision,
2026-11-11: a drill is exempt from guards 9 and 11 "Nothing else"). So nothing else may change
what it decides: the tag is read only by its writer (`modules/heal/incidents.py`, at the
incident's creation), the guards and their callers (guards 9 and 11's exemption and their real
count), the real figures that leave drills out, and the records and the page that say it was a
drill. Each file is named below with why; the list is compared EXACTLY, so a new reader fails
here until it is named, and a reader that leaves fails until it is removed.

The scan parses every module under `modules/` and `routes/` (a floor on its population) and
finds, in code (docstrings are prose and are not read): the tag's field as a string
(``"fault_drill"``), an attribute of the fault-drill module that reads a tag
(`READERS`: ``fault_drills.tag_of``, ``.FIELD`` and the rest), an import of one, and the
incidents module's ``drill_of``. Planted cases show each is found.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELD = "fault_drill"
#: The fault-drill module's names that read or write a tag.
READERS = {"tag_of", "is_drill", "real_only", "FIELD", "tag_for", "covering"}
#: Every product file that reads the tag, with why: compared exactly.
READ_BY = {
    "modules/fault_drills.py": "the owner: the field, the declarations and the accessors",
    "modules/heal/incidents.py": "the one writer: the tag at creation (tag_for), a member's "
                                 "own carried, and drill_of for the guards' callers",
    "modules/heal/guards.py": "guards 9 and 11: the exemption, and their count of real heals",
    "modules/heal/decide.py": "a guards' caller: the incident's tag to guards 9 and 11 and "
                              "onto its decision",
    "modules/heal/bounce.py": "a guards' caller: the incident's tag to guard 9 and onto its "
                              "decision",
    "modules/heal/session_clear.py": "a guards' caller: the incident's tag to guard 9 and onto "
                                     "its decision",
    "modules/heal/decisions.py": "the dry run's Right / Wrong counts leave drills out; "
                                 "drill_counts counts them apart",
    "modules/heal/steplog.py": "keeps a decision's tag on its rows, for History",
    "modules/history_sources.py": "History: a drill heal's row says it was a drill",
}
SCANNED_AT_LEAST = 300


def _docstrings(tree) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value,
                                                                     ast.Constant):
                out.add(id(body[0].value))
    return out


def reads(text: str) -> list:
    """Each way *text* (a module's source) names the tag, in code."""
    tree = ast.parse(text)
    prose = _docstrings(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == FIELD and id(node) not in prose:
            found.append(f"the string {FIELD!r}")
        elif isinstance(node, ast.Attribute) and node.attr in READERS and \
                isinstance(node.value, ast.Name) and node.value.id in ("fault_drills", "FD"):
            found.append(f"{node.value.id}.{node.attr}")
        elif isinstance(node, ast.Attribute) and node.attr == "drill_of":
            found.append("drill_of")
        elif isinstance(node, ast.ImportFrom) and (node.module or "").endswith("fault_drills") \
                and any(a.name in READERS for a in node.names):
            found.append(f"from {node.module} import a reader")
    return found


def _population() -> dict:
    from tests.source_index import tracked

    out = {}
    for path in tracked("modules", "routes", suffix=".py", root=ROOT):
        with open(path, encoding="utf-8") as fh:
            out[os.path.relpath(path, ROOT)] = fh.read()
    return out


def test_only_the_named_files_read_the_tag():
    files = _population()
    assert len(files) >= SCANNED_AT_LEAST, len(files)
    found = {rel for rel, text in files.items() if reads(text)}
    assert found == set(READ_BY), {"unnamed": sorted(found - set(READ_BY)),
                                   "named and gone": sorted(set(READ_BY) - found)}


def test_each_named_file_reads_it_in_code():
    files = _population()
    for rel in READ_BY:
        assert reads(files[rel]), rel


def test_a_planted_reader_is_found():
    assert reads("def f(inc):\n    return inc.get('fault_drill')\n") == ["the string 'fault_drill'"]
    assert reads("from modules import fault_drills\n"
                 "def f(inc):\n    return fault_drills.tag_of(inc)\n") == ["fault_drills.tag_of"]
    assert reads("from modules.fault_drills import is_drill\n")
    assert reads("def f(n, i):\n    return incidents.drill_of(n, i)\n") == ["drill_of"]


def test_prose_and_other_names_are_not_a_reader():
    assert reads('"""A fault drill is read by fault_drills.tag_of."""\n') == []
    assert reads("from modules import fault_drills\nX = fault_drills.MAX_MINUTES\n"
                 "Y = 'fault_drill_declare'\n") == []
