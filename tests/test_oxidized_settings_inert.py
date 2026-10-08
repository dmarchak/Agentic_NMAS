"""Oxidized's settings are inert (Phase 3, the operator's P3-3, 2026-10-08).

Oxidized is retired. Its settings keys stay DECLARED for one release, in the schema
(`settings_schema.py`), the scope table (`settings_scope.py`, as `retiring`) and the secret
list (`secrets_store.py`), so a rollback to the release before finds them; the release after
removes them with a settings version bump. Until then nothing else in the product may read
them: a read would be a path still talking to, or deciding on, a system that is gone.

Found by PARSING, never by a substring of a file (prose about Oxidized is allowed): in every
Python file under modules/, routes/ and scripts/ and app.py, a string constant equal to one of
the keys, or an f-string whose literal part opens with ``oxidized_``, is a read. The three
declaring files are the only ones excused.
"""

import ast
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYS = frozenset({"oxidized_url", "oxidized_username", "oxidized_password",
                  "oxidized_verify_tls", "oxidized_node_identity", "oxidized_router_db",
                  "oxidized_rest_url"})
SCOPE = ("modules", "routes", "scripts", "app.py")
DECLARING = {"modules/settings_schema.py", "modules/settings_scope.py",
             "modules/secrets_store.py"}
#: Python files in SCOPE measured on 2026-10-08 (298); the scan must not quietly shrink.
FLOOR = 250


def python_files(root=ROOT) -> list:
    """Every tracked Python file in SCOPE: a ``.py``, or a script whose first line names
    python."""
    files = subprocess.run(["git", "-C", root, "ls-files", "--", *SCOPE], capture_output=True,
                           text=True, check=True).stdout.split()
    out = []
    for f in files:
        path = os.path.join(root, f)
        if not os.path.isfile(path) or os.path.islink(path):
            continue
        if f.endswith(".py"):
            out.append(f)
            continue
        if f.startswith("scripts/") and "." not in os.path.basename(f):
            with open(path, "rb") as fh:
                if b"python" in fh.readline():
                    out.append(f)
    return sorted(out)


def reads(source: str) -> list:
    """``[(line, text)]``: each string constant naming an Oxidized settings key."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in KEYS:
            found.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr) and node.values:
            first = node.values[0]
            if (isinstance(first, ast.Constant) and isinstance(first.value, str)
                    and first.value.startswith("oxidized_")):
                found.append((node.lineno, first.value + "{...}"))
    return found


def offenders(root=ROOT) -> dict:
    out = {}
    for f in python_files(root):
        if f in DECLARING:
            continue
        with open(os.path.join(root, f), encoding="utf-8") as fh:
            got = reads(fh.read())
        if got:
            out[f] = got
    return out


def test_the_population_is_found():
    files = python_files()
    assert len(files) >= FLOOR, f"the scan shrank: {len(files)} Python files"
    assert DECLARING <= set(files)
    assert "scripts/nmas-clab-targets" in files            # an extensionless python script


def test_the_declaring_files_still_declare_every_key():
    """Inert, never undeclared, for this release (P3-3)."""
    from modules import settings_scope
    from modules.secrets_store import SECRET_KEYS
    from modules.settings_schema import DEFAULTS

    assert KEYS <= set(DEFAULTS) and KEYS <= set(settings_scope.SCOPES)
    assert "oxidized_password" in SECRET_KEYS
    assert {settings_scope.scope_of(k)[0] for k in KEYS} <= {settings_scope.RETIRING,
                                                            settings_scope.DEAD}


def test_nothing_else_reads_an_oxidized_setting():
    assert offenders() == {}, ("an Oxidized setting is read outside its declarations; "
                               "Oxidized is retired (Phase 3, P3-3)")


def test_a_planted_read_is_found():
    planted = ("from modules.settings_schema import get_setting\n"
               "x = get_setting('oxidized_url')\n"
               "y = default_layer(f'oxidized_{name}', '')\n"
               "z = 'oxidized_url is how it was spelled'\n")
    assert reads(planted) == [(2, "oxidized_url"), (3, "oxidized_{...}")]


def test_prose_about_a_key_is_not_a_read():
    assert reads('"""The oxidized_url key is retired."""\n# get_setting("oxidized_url")\n') == []
