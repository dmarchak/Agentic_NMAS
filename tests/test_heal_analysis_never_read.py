"""The heal loop never reads the AI analysis (board H, H8; docs/HEAL_TO_INTENT.md section 12:
"Nothing in the heal loop reads its output ... Mechanised: a test parses modules/heal/ and
refuses any reference from the loop's modules to modules.ai or to the incident's analysis
field. Only the notifier and the pages draw it").

The scan parses every module of `modules/heal/` (a floor on its population, so a scan of
nothing never passes) and refuses, in code (docstrings are prose and are not read):
- an import of `modules.ai` or anything under it, or of the analysis (`heal_analysis`);
- an import of the fix-it path (`modules.fixit` or anything under it: an incident's
  troubleshooting record holds the AI's proposals; the operator's order of 2026-11-12,
  "Section 12's rule stays in force");
- a name, an attribute or a string naming an analysis (``analysis``, ``analyses``,
  ``analyse``), so ``incident["analysis"]`` or ``.analysis`` is found as surely as an import;
- any reference to the notifier (`modules.heal_notice`) but the runner's one notify step,
  whose result is discarded (a bare call statement): the loop starts the notifier and reads
  nothing back from it.
Planted cases show each is found.

**Two references to `modules.ai` predate the analysis** (H2 and H6), each a deterministic
helper that makes no call: the configuration-change line's pattern and its parse
(`modules.ai.who`, read by `heal.attribution`) and the change record's facts
(`modules.ai.change_record.facts`, read by `heal.change_record`). They are `KNOWN`, exactly:
an entry no longer found fails, so the list only shrinks, and moving them out of `modules.ai`
is the register's row (section 12's rule names any reference to `modules.ai`).
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAL = os.path.join(ROOT, "modules", "heal")
#: The modules of the loop today: detect, decide, act, verify and record's (and their stores).
FLOOR = 15
WORDS = ("analysis", "analyses", "analyse")
#: The one place the loop names the notifier: the runner's notify step (`detect._notify_step`).
NOTIFY_STEP = ("detect.py", "_notify_step")
#: The loop's references to `modules.ai` that predate H8, each a deterministic helper that makes
#: no call (the module docstring): ``(file, the name imported)``. Only shrinks.
KNOWN = {("attribution.py", "modules.ai.who.CONFIG_LOG"),
         ("attribution.py", "modules.ai.who.config_change"),
         ("change_record.py", "modules.ai.change_record")}


def _docstrings(tree) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value,
                                                                     ast.Constant):
                out.add(id(body[0].value))
    return out


def _parents(tree) -> dict:
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[id(child)] = node
    return out


def _enclosing(node, parents):
    while node is not None and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        node = parents.get(id(node))
    return node.name if node is not None else ""


def imported(tree) -> list:
    """``(line, name, node)`` for every name *tree* imports, each as its full dotted name (an
    ``import a.b`` is ``a.b``; a ``from a import b`` is ``a.b``)."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(node.lineno, a.name, node) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out += [(node.lineno, f"{node.module or ''}.{a.name}", node) for a in node.names]
    return out


def found(name: str, source: str, known=frozenset(KNOWN)) -> list:
    """Every reference the loop may not make in *source* (the module *name*), as
    ``(line, what)``; *known* the references that predate the rule (`KNOWN`)."""
    tree = ast.parse(source)
    docs, parents, out = _docstrings(tree), _parents(tree), []

    def named(text: str) -> bool:
        return any(w in text.lower() for w in WORDS)

    for lineno, m, node in imported(tree):
        if (name, m) in known:
            continue
        if m == "modules.ai" or m.startswith("modules.ai.") or "heal_analysis" in m:
            out.append((lineno, f"imports {m}"))
        elif m == "modules.fixit" or m.startswith("modules.fixit."):
            out.append((lineno, f"imports {m}, the fix-it path, whose record holds the AI's "
                                "proposals"))
        elif "heal_notice" in m and (name, _enclosing(node, parents)) != NOTIFY_STEP:
            out.append((lineno, f"imports {m} outside the runner's notify step"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and named(node.id):
            out.append((node.lineno, f"names {node.id}"))
        elif isinstance(node, ast.Attribute) and named(node.attr):
            out.append((node.lineno, f"reads .{node.attr}"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs and named(node.value):
            out.append((node.lineno, f"names {node.value[:40]!r}"))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id == "heal_notice":
            parent = parents.get(id(node))
            stmt = parents.get(id(parent)) if isinstance(parent, ast.Call) else None
            if not (isinstance(stmt, ast.Expr)
                    and (name, _enclosing(node, parents)) == NOTIFY_STEP):
                out.append((node.lineno, f"uses heal_notice.{node.attr} and reads its answer"))
    return sorted(set(out))


def _modules() -> dict:
    out = {}
    for f in sorted(os.listdir(HEAL)):
        if f.endswith(".py"):
            with open(os.path.join(HEAL, f), encoding="utf-8") as fh:
                out[f] = fh.read()
    return out


def test_no_module_of_the_heal_loop_reads_the_analysis():
    mods = _modules()
    assert len(mods) >= FLOOR, sorted(mods)
    bad = {name: got for name, src in mods.items() if (got := found(name, src))}
    assert bad == {}, bad


def test_the_references_that_predate_it_are_exact_and_only_shrink():
    mods = _modules()
    have = {(name, m) for name, src in mods.items() for _l, m, _n in imported(ast.parse(src))}
    assert KNOWN <= have, f"no longer found, so leaves KNOWN: {sorted(KNOWN - have)}"
    # Each is a helper that makes no call: none of them is the gateway or the analysis.
    assert not any("gateway" in m or "heal_analysis" in m or m.endswith(".calls")
                   for _f, m in KNOWN)


def test_the_runner_starts_the_notifier_and_reads_nothing_back():
    src = _modules()["detect.py"]
    assert "heal_notice.run(name)" in src, "the notify step is the runner's"
    assert found("detect.py", src) == []


def test_each_planted_reference_is_found():
    planted = {
        "from modules.ai import heal_analysis\n": "imports modules.ai",
        "import modules.ai.gateway\n": "imports modules.ai.gateway",
        "from modules.fixit import incident\n": "imports modules.fixit.incident, the fix-it",
        "def f():\n    from modules.fixit.validate import check\n    return check\n":
            "imports modules.fixit.validate.check, the fix-it",
        "import modules.fixit\n": "imports modules.fixit, the fix-it",
        "def f(inc):\n    return inc['analysis']\n": "names 'analysis'",
        "def f(inc):\n    return inc.get('analyses')\n": "names 'analyses'",
        "def f(inc):\n    return inc.analysis\n": "reads .analysis",
        "def f():\n    from modules import heal_notice\n    return heal_notice.run('n')\n":
            "outside the runner's notify step",
    }
    for src, want in planted.items():
        got = found("decide.py", src)
        assert any(want in w for _l, w in got), (src, got)
    # The runner's own step, its result discarded, passes; one that reads it back does not.
    ok = ("def _notify_step():\n    from modules import heal_notice\n"
          "    heal_notice.run('n')\n")
    assert found("detect.py", ok) == []
    read_back = ("def _notify_step():\n    from modules import heal_notice\n"
                 "    got = heal_notice.run('n')\n    return got\n")
    assert any("reads its answer" in w for _l, w in found("detect.py", read_back))
    # A docstring may say the word: it is prose.
    assert found("decide.py", '"""Never reads the analysis."""\n') == []
