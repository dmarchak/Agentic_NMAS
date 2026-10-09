"""Phase 4 section 8.1 (the operator, 2026-10-09): every Mercury script runs under the interpreter
`flask-app` runs, never a shell's `python3`, through ONE standard-library helper,
`modules.app_interpreter.adopt(__name__)`, called before any import outside the standard library.

The helper is tested against the host's captured ExecStart; every script under scripts/ with a
python shebang is parsed and held to calling it, except the exemptions section 8.1 lists.
"""

import ast
import os
import sys

import pytest

from modules import app_interpreter as ai
from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Captured from `systemctl show -p ExecStart --value flask-app.service` on the host (2026-10-09),
# the checkout's path replaced; the venv's line is the same unit after section 8's switch.
SYSTEM_EXECSTART = ("{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 <checkout>/app.py ; "
                    "ignore_errors=no ; start_time=[Fri 2026-10-09 04:44:34 UTC] ; "
                    "stop_time=[n/a] ; pid=255576 ; code=(null) ; status=0/0 }")
VENV_EXECSTART = SYSTEM_EXECSTART.replace("/usr/bin/python3", "/opt/mercury-venv/bin/python")

#: Section 8.1's exemptions, each with its reason. Nothing else may skip the call.
EXEMPT = {
    # The laptop's own tools: they never run on the host.
    "scripts/hooks/claude-no-claude-md-edits": "a laptop hook",
    "scripts/hooks/claude-no-heredoc-interpreter": "a laptop hook",
    "scripts/hooks/claude-no-host-writes": "a laptop hook",
    "scripts/hooks/claude-no-raw-config-reads": "a laptop hook",
    "scripts/check_removed_definitions.py": "the pre-commit hook's and CI's",
    "scripts/nmas-gate": "the laptop's gate",
    "scripts/nmas-stage-guard": "the laptop's gate",
    "scripts/nmas-host": "the laptop's reach to the hosts",
    "scripts/nmas-ci-log": "the laptop's CI reader",
    "scripts/nmas-host-step-check": "the commit-msg hook's and CI's",
    # Fed to `python3 -` on stdin by the agent: no file to re-run; standard library and
    # modules.redact only (standard library only, measured 2026-10-09).
    "scripts/nmas-config-read": "run from stdin",
    # A root-installed copy, run `/usr/bin/python3 -I`: it never imports the user-writable
    # checkout, so it cannot import the helper.
    "scripts/nmas-oxidized-cred": "a root-installed copy",
}
#: Loaded as a module by root's updater from a copy beside no checkout, so its call is the first
#: statement of its `__main__` block; allowed only because nothing outside the standard library
#: is imported at its top level.
MAIN_BLOCK = {"scripts/nmas-deploy"}


def _python_scripts():
    out = []
    for path in tracked("scripts"):
        rel = os.path.relpath(path, ROOT)
        if rel.startswith("scripts/host-steps/"):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
        if first.startswith("#!") and "python" in first:
            out.append(rel)
    return sorted(out)


def _is_adopt_call(node):
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name) and node.value.func.id == "adopt"
            and [getattr(a, "id", None) for a in node.value.args] == ["__name__"])


def _is_adopt_import(node):
    return (isinstance(node, ast.ImportFrom) and node.module == "modules.app_interpreter"
            and [a.name for a in node.names] == ["adopt"])


def _is_main_block(node):
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
            and getattr(node.test.left, "id", None) == "__name__")


def _top_imports(tree):
    """Imports that run when the module is loaded: not inside a def, a class or the main block."""
    found = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if _is_main_block(child):
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                found.append(child)
            visit(child)
    visit(tree)
    return found


def _outside_stdlib(node):
    if isinstance(node, ast.ImportFrom):
        if node.level or node.module == "__future__":
            return node.level > 0
        names = [node.module]
    else:
        names = [a.name for a in node.names]
    return any(n.split(".")[0] not in sys.stdlib_module_names for n in names)


def problems(rel, text):
    """What is wrong with *rel*'s call, or [] when it adopts the app's interpreter first."""
    tree = ast.parse(text)
    body = tree.body
    calls = [i for i, n in enumerate(body) if _is_adopt_call(n)]
    early = [n for n in _top_imports(tree) if _outside_stdlib(n) and not _is_adopt_import(n)]
    if calls:
        i = calls[0]
        if i == 0 or not _is_adopt_import(body[i - 1]):
            return [f"{rel}: adopt(__name__) is not just after `from modules.app_interpreter "
                    "import adopt`"]
        line = body[i].lineno
        before = [n for n in early if n.lineno < line]
        return [f"{rel}:{n.lineno}: imports outside the standard library before adopt(__name__)"
                for n in before]
    if rel in MAIN_BLOCK:
        mains = [n for n in body if _is_main_block(n)]
        if early:
            return [f"{rel}:{n.lineno}: a top-level import outside the standard library, so the "
                    "call cannot wait for the main block" for n in early]
        first = [n for n in (mains[0].body if mains else [])
                 if not (isinstance(n, ast.Expr) and "sys.path" in ast.unparse(n))]
        if len(first) >= 2 and _is_adopt_import(first[0]) and _is_adopt_call(first[1]):
            return []
        return [f"{rel}: its __main__ block does not begin with the adopt import and call"]
    return [f"{rel}: never calls adopt(__name__)"]


def test_every_script_takes_the_app_interpreter_first():
    scripts = _python_scripts()
    # Measured 2026-10-09: 79 scripts with a python shebang under scripts/.
    assert len(scripts) >= 70, len(scripts)
    assert set(EXEMPT) <= set(scripts), sorted(set(EXEMPT) - set(scripts))
    bad = []
    for rel in scripts:
        if rel in EXEMPT:
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            bad += problems(rel, fh.read())
    assert bad == []


GOOD = ("#!/usr/bin/env python3\nimport os\nimport sys\nsys.path.insert(0, 'x')\n"
        "from modules.app_interpreter import adopt  # noqa: E402\nadopt(__name__)\n"
        "import yaml  # noqa: E402\n")


@pytest.mark.parametrize("text, why", [
    (GOOD.replace("adopt(__name__)\n", ""), "never calls"),
    ("#!/usr/bin/env python3\nimport yaml\n"
     "from modules.app_interpreter import adopt\nadopt(__name__)\n", "before adopt"),
    ("#!/usr/bin/env python3\ntry:\n    import requests\nexcept ImportError:\n    pass\n"
     "from modules.app_interpreter import adopt\nadopt(__name__)\n", "before adopt"),
    ("#!/usr/bin/env python3\nfrom modules.config import DATA_DIR\n"
     "from modules.app_interpreter import adopt\nadopt(__name__)\n", "before adopt"),
])
def test_the_check_finds_a_planted_script(text, why):
    assert problems("scripts/planted", GOOD) == []
    found = problems("scripts/planted", text)
    assert found and why in found[0], found


def test_the_main_block_form_is_held_to_no_early_import():
    ok = ("#!/usr/bin/env python3\nimport sys\ndef main():\n    import yaml\n"
          "if __name__ == '__main__':\n    from modules.app_interpreter import adopt\n"
          "    adopt(__name__)\n    sys.exit(main())\n")
    assert problems("scripts/nmas-deploy", ok) == []
    assert problems("scripts/nmas-deploy", "import yaml\n" + ok)
    assert problems("scripts/nmas-deploy", ok.replace("    adopt(__name__)\n", ""))


# --- the helper itself ---------------------------------------------------------------------------

def test_it_reads_the_interpreter_from_the_units_execstart():
    assert ai.app_interpreter(SYSTEM_EXECSTART) == "/usr/bin/python3"
    assert ai.app_interpreter(VENV_EXECSTART) == "/opt/mercury-venv/bin/python"
    assert ai.app_interpreter("") is None


def test_it_rereads_only_when_another_interpreter_started_the_script():
    # Started by /usr/bin/python3 before the switch, or the venv's after it: no re-run.
    assert ai.interpreter_to_read("/usr/bin/python3", "/usr") is None
    assert ai.interpreter_to_read("/opt/mercury-venv/bin/python", "/opt/mercury-venv") is None
    # Started by /usr/bin/python3 after the switch: re-run under the venv's link.
    assert (ai.interpreter_to_read("/opt/mercury-venv/bin/python", "/usr")
            == "/opt/mercury-venv/bin/python")
    # The venv's after the switch's undo: re-run under the system's.
    assert ai.interpreter_to_read("/usr/bin/python3", "/opt/mercury-venv") == "/usr/bin/python3"


def test_adopt_reruns_the_script_under_the_apps_interpreter(capsys):
    ran = []
    target = os.path.join(os.path.dirname(os.path.dirname(sys.prefix)), "elsewhere", "bin", "python")
    show = f"{{ path={target} ; argv[]={target} app.py ; }}"
    ai.adopt("__main__", show=show, environ={}, argv=["scripts/nmas-x", "--flag"],
             execve=lambda *a: ran.append(a))
    (path, argv, env), = ran
    assert path == target and argv == [target, os.path.abspath("scripts/nmas-x"), "--flag"]
    assert env[ai.REEXEC] == "1"
    assert "re-running under" in capsys.readouterr().err


def test_adopt_keeps_the_interpreter_silently_where_there_is_no_unit(capsys):
    ran = []
    ai.adopt("__main__", show="", environ={}, argv=["x"], execve=lambda *a: ran.append(a))
    assert ran == [] and capsys.readouterr().err == ""


def test_adopt_does_nothing_for_a_script_loaded_as_a_module():
    ran = []
    ai.adopt("nmas_update_gate", show=VENV_EXECSTART.replace("/opt/mercury-venv", "/elsewhere"),
             environ={}, argv=["x"], execve=lambda *a: ran.append(a))
    assert ran == []


def test_the_venv_identity_is_the_inputs_sha256_by_an_independent_path(tmp_path):
    """Section 8.3: the folder's name. The expectation comes from coreutils' sha256sum over the
    files concatenated, never from hashlib."""
    import subprocess

    for name, text in (("requirements.lock", "a==1\n"), ("requirements-test.txt", "b==2\n")):
        (tmp_path / name).write_text(text)
    want = subprocess.run(["sh", "-c", "cat requirements.lock requirements-test.txt | sha256sum"],
                          cwd=tmp_path, capture_output=True, text=True, check=True).stdout[:12]
    assert ai.venv_id(str(tmp_path)) == want
    (tmp_path / "requirements-test.txt").write_text("b==3\n")
    assert ai.venv_id(str(tmp_path)) != want, "a change to the test tools is a new venv"
    out = subprocess.run([sys.executable, "-m", "modules.app_interpreter", "venv-id",
                          str(tmp_path)], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ai.venv_id(str(tmp_path))


def test_a_rerun_that_still_reports_another_prefix_is_refused_not_looped(capsys):
    show = "{ path=/elsewhere/bin/python ; }"
    with pytest.raises(SystemExit) as stop:
        ai.adopt("__main__", show=show, environ={ai.REEXEC: "1"}, argv=["x"],
                 execve=lambda *a: pytest.fail("looped"))
    assert stop.value.code == 2
    assert "REFUSED" in capsys.readouterr().err
