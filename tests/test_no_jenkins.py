"""P.4 step 1 (docs/NSOT_CI.md acceptance 1): no Jenkins code remains.

Jenkins was a demonstration that did not work as designed, and no working
path depended on it: unconfigured on the host, its only touch on the deploy
path skipped silently, its webhook accepted any unauthenticated POST, and its
check runner hardcoded `cisco_ios` and read a CSV a NetBox list does not have.
Removing it lost nothing that worked.
"""

import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REMOVED_MODULES = ("jenkins_runner", "check_runner", "jenkins_shell", "pipeline_builder")


def _python_files():
    out = [os.path.join(ROOT, "app.py")]
    for sub in ("modules", "routes", "scripts", "tests"):
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, sub)):
            for name in files:
                path = os.path.join(dirpath, name)
                if name.endswith(".py"):
                    out.append(path)
                elif sub == "scripts" and "." not in name:
                    with open(path, "rb") as fh:
                        if b"python" in fh.read(64):
                            out.append(path)
    return out


def _imports(path):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            yield base
            for a in node.names:
                yield f"{base}.{a.name}" if base else a.name


def _all_imports():
    return {os.path.relpath(p, ROOT): set(_imports(p)) for p in _python_files()}


def test_the_scan_finds_the_population():
    found = _all_imports()
    assert len(found) >= 200, len(found)
    assert any("modules.pipeline" in names for names in found.values()), \
        "positive anchor: the deploy path's own import must be visible"


def test_no_file_imports_a_removed_module():
    bad = sorted((path, name) for path, names in _all_imports().items()
                 for name in names
                 if any(name == f"modules.{m}" or name.startswith(f"modules.{m}.")
                        or name.endswith(f".{m}") and name.startswith("modules")
                        for m in REMOVED_MODULES))
    assert bad == [], bad


@pytest.mark.parametrize("name", REMOVED_MODULES)
def test_the_module_file_is_gone(name):
    assert not os.path.exists(os.path.join(ROOT, "modules", f"{name}.py"))


def test_the_stale_jenkinsfile_is_gone():
    assert not os.path.exists(os.path.join(ROOT, "Jenkinsfile"))


def test_no_route_serves_jenkins():
    import app as A
    rules = [r.rule for r in A.app.url_map.iter_rules()]
    assert len(rules) >= 150, len(rules)
    assert [r for r in rules if "jenkins" in r.lower()] == []
