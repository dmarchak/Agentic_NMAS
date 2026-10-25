"""The AI boundary (the operator, 2026-10-25; PHASE8_PLAN 15.12): every AI feature reaches the
model only through the gateway, so the single egress path (the gateway's payload builder, the
egress mask, the adapter's send) is the only code that can put data in front of a cloud model.

Read by parsing every product Python file (the repository's top-level modules, `modules/`,
`routes/`, and the Python scripts in `scripts/`), never by substring:

- only `modules/ai/anthropic_adapter.py` holds a string naming Anthropic's API host or its key
  header (`x-api-key`);
- only `modules/ai/gateway.py` imports the adapter;
- nothing imports an Anthropic SDK (`anthropic`; PHASE8_PLAN 15.12: the SDK is not taken);
- only the gateway reads the stored key (`get_secret("anthropic_api_key")`).

A floor on the files read, and each rule shown finding a planted case.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER = "modules/ai/anthropic_adapter.py"
GATEWAY = "modules/ai/gateway.py"
ADAPTER_MODULE = "modules.ai.anthropic_adapter"
KEY_SETTING = "anthropic_api_key"


def product_files() -> list:
    """Every product Python file git tracks, relative to the repository (never a disk walk:
    an agent's worktree under .claude/ is not the program)."""
    from tests.source_index import tracked

    # The top level's own modules (app.py, netbox_client.py): tracked() with no folder is the
    # whole checkout, so a path with a folder in it is not one of them.
    out = [rel for rel in (os.path.relpath(p, ROOT) for p in tracked(suffix=".py"))
           if os.sep not in rel]
    out += [os.path.relpath(p, ROOT) for p in tracked("modules", "routes", suffix=".py")]
    for p in tracked("scripts", recursive=False):
        if p.endswith(".py"):
            out.append(os.path.relpath(p, ROOT))
            continue
        with open(p, "rb") as fh:
            if b"python" in fh.readline():
                out.append(os.path.relpath(p, ROOT))
    return sorted(set(out))


def _imports_adapter(node) -> bool:
    if isinstance(node, ast.Import):
        return any(a.name == ADAPTER_MODULE or a.name.startswith(ADAPTER_MODULE + ".")
                   for a in node.names)
    if isinstance(node, ast.ImportFrom) and node.module:
        if node.module == ADAPTER_MODULE or node.module.startswith(ADAPTER_MODULE + "."):
            return True
        return node.module == "modules.ai" and any(a.name == "anthropic_adapter"
                                                   for a in node.names)
    return False


def _imports_sdk(node) -> bool:
    if isinstance(node, ast.Import):
        return any(a.name.split(".")[0] == "anthropic" for a in node.names)
    return isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "anthropic" \
        and node.level == 0


def _reads_key(node) -> bool:
    if not (isinstance(node, ast.Call) and node.args):
        return False
    fn = node.func
    name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
    first = node.args[0]
    return name == "get_secret" and isinstance(first, ast.Constant) and first.value == KEY_SETTING


def _names_the_api(node) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and (
        "api.anthropic.com" in node.value.lower() or node.value.lower() == "x-api-key")


def violations(path: str, text: str) -> list:
    """``[(rule, line)]``: what *path*'s source does that only the gateway or the adapter may."""
    out = []
    for node in ast.walk(ast.parse(text, filename=path)):
        line = getattr(node, "lineno", 0)
        if _names_the_api(node) and path != ADAPTER:
            out.append(("names Anthropic's API or its key header", line))
        if _imports_adapter(node) and path != GATEWAY:
            out.append(("imports the adapter", line))
        if _imports_sdk(node):
            out.append(("imports an Anthropic SDK", line))
        if _reads_key(node) and path != GATEWAY:
            out.append(("reads the stored key", line))
    return out


def test_no_module_but_the_gateway_reaches_the_model():
    files = product_files()
    assert len(files) >= 300 and GATEWAY in files and ADAPTER in files, len(files)
    found = []
    for path in files:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            found += [(path, rule, line) for rule, line in violations(path, fh.read())]
    assert found == [], found


def test_the_gateway_and_the_adapter_are_where_the_scan_says():
    """The scan's population holds what the rules allow: the adapter names the API, the
    gateway imports the adapter and reads the key (a rule allowing nothing would pass too)."""
    def read(p):
        with open(os.path.join(ROOT, p), encoding="utf-8") as fh:
            return ast.parse(fh.read())
    assert any(_names_the_api(n) for n in ast.walk(read(ADAPTER)))
    gw = list(ast.walk(read(GATEWAY)))
    assert any(_imports_adapter(n) for n in gw) and any(_reads_key(n) for n in gw)


PLANTED = {
    "a feature naming the API": 'URL = "https://api.anthropic.com/v1/messages"\n',
    "a feature with the key header": 'h = {"X-Api-Key": k}\n',
    "a feature importing the adapter": "from modules.ai import anthropic_adapter\n",
    "a feature importing it by path": "import modules.ai.anthropic_adapter as a\n",
    "a feature importing its send": "from modules.ai.anthropic_adapter import send\n",
    "a feature importing the SDK": "import anthropic\n",
    "a feature importing the SDK's client": "from anthropic import Anthropic\n",
    "a feature reading the key": 'k = get_secret("anthropic_api_key")\n',
    "a feature reading it by module": 'k = secrets_store.get_secret("anthropic_api_key")\n',
}


def test_each_rule_finds_its_planted_case():
    for what, text in PLANTED.items():
        assert violations("modules/ai/nl_query.py", text), what
    assert violations("modules/ai/nl_query.py", "from modules.ai import gateway\n") == []
    assert violations("modules/ai/nl_query.py", 'KEY = "anthropic_api_key"\n') == [], \
        "naming the setting (the card, the schema) is not reading its value"
