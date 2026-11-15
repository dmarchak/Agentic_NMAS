"""The AI's read loop never reaches NetBox's reads (the operator, 2026-11-14: "NetBox reads have
no person-facing home (C3719), so the AI's read loop must not reach them. Keep netbox_reads.py
for the DHCP plan's subnet lookup only (plan code, shown in the preview), outside the AI's read
loop. Add a test that the AI read loop can't call netbox_reads.").

THE POPULATION, by property, parsed from every module under modules/ and routes/ (its syntax
tree, imports inside functions included): a module OF THE READ LOOP is `modules/ai/read_loop.py`
itself or any module importing it (each read family, and each feature that runs the loop over
one). Its floor is the read loop and the families known when this was written.

- **No module of the read loop imports `modules.ai.netbox_reads`,** in any form (`import`,
  `from … import`, or the module's dotted name as a string, as `importlib` or a dotted
  reference takes it); a planted one is found, each form.
- **`netbox_reads` is not of the read loop:** it imports nothing of it and declares no read
  family or operation; a planted one is found.
"""
import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOP = "modules.ai.read_loop"
NETBOX = "modules.ai.netbox_reads"


def dotted(path: str) -> str:
    rel = os.path.relpath(path, ROOT)[:-3].replace(os.sep, ".")
    return rel[:-len(".__init__")] if rel.endswith(".__init__") else rel


def imported(source: str, module: str = "") -> set:
    """Every module *source* imports (dotted), wherever the import stands, and every string
    that is a dotted name under ``modules.`` (``importlib.import_module("modules.x")``, a
    ``"modules.x:f"`` reference); *module* resolves a relative import."""
    out = set()
    package = module.rsplit(".", 1)[0] if module else ""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                parts = parts[:len(parts) - (node.level - 1)] if node.level > 1 else parts
                base = ".".join(p for p in parts + ([base] if base else []) if p)
            out.add(base)
            out |= {f"{base}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and \
                node.value.startswith("modules."):
            out.add(node.value.split(":", 1)[0])
    return out


def declares_a_family(source: str) -> list:
    """Each call constructing a read family or one of its operations (`ReadFamily(`,
    `Operation(`), by its line."""
    return [n.lineno for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and (
        (isinstance(n.func, ast.Attribute) and n.func.attr in ("ReadFamily", "Operation")) or
        (isinstance(n.func, ast.Name) and n.func.id in ("ReadFamily", "Operation")))]


def sources() -> dict:
    """Every tracked module of modules/ and routes/ (`source_index.tracked`: an untracked copy,
    an agent's worktree, is never read as program)."""
    from tests import source_index

    out = {}
    for path in source_index.tracked("modules", "routes", suffix=".py"):
        with open(path, encoding="utf-8") as fh:
            out[dotted(path)] = fh.read()
    return out


def of_the_loop(modules: dict) -> set:
    return {m for m, src in modules.items() if m == LOOP or LOOP in imported(src, m)}


def reaching(modules: dict) -> list:
    """Each module of the read loop that imports netbox_reads, with how."""
    return sorted(m for m in of_the_loop(modules) if NETBOX in imported(modules[m], m))


class TestTheReadLoopNeverReachesNetBox:
    def test_the_population_is_real(self):
        modules = sources()
        loop = of_the_loop(modules)
        assert len(modules) > 300, len(modules)
        assert {LOOP, "modules.ai.fixit_reads", "modules.ai.router_reads",
                "modules.ai.fixit_troubleshoot"} <= loop, sorted(loop)
        assert NETBOX in modules, "the module the plan's prefix read lives in"

    def test_no_module_of_the_read_loop_imports_netbox_reads(self):
        assert reaching(sources()) == []

    def test_netbox_reads_is_not_of_the_read_loop(self):
        src = sources()[NETBOX]
        assert LOOP not in imported(src, NETBOX)
        assert declares_a_family(src) == []

    @pytest.mark.parametrize("planted", [
        "from modules.ai import netbox_reads\n",
        "def f():\n    from modules.ai.netbox_reads import read\n    return read\n",
        "import modules.ai.netbox_reads\n",
        "import importlib\nNR = importlib.import_module('modules.ai.netbox_reads')\n",
        "RUN = 'modules.ai.netbox_reads:read'\n",
    ], ids=["from-import", "inside a function", "import", "importlib", "a dotted reference"])
    def test_a_planted_family_reaching_netbox_is_found(self, planted):
        modules = dict(sources())
        modules["modules.ai.planted_reads"] = (
            "from modules.ai import read_loop as RL\n" + planted)
        assert reaching(modules) == ["modules.ai.planted_reads"]

    @pytest.mark.parametrize("planted", [
        "from modules.ai import read_loop as RL\n",
        "FAMILY = ReadFamily(name='netbox')\n",
        "OP = RL.Operation(name='netbox_prefixes')\n",
    ])
    def test_a_planted_family_in_netbox_reads_is_found(self, planted):
        src = sources()[NETBOX] + "\n" + planted
        assert LOOP in imported(src, NETBOX) or declares_a_family(src)
