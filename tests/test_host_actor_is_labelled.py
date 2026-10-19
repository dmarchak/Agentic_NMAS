"""C237: a host command's recorded actor is the OS login LABELLED, never bare.

The app records a verified email; the host commands recorded `getpass.getuser()` bare (or as
"user (host shell)", or "user@host"), so the audit trail held two unlabelled identities for
one person. Now every host command names who ran it through `identity.host_actor()`
(`inventory_edit.actor_label`'s rule: "<user> (host login, not a verified identity)").

The shape is constrained, never the members enumerated: a parse of every tracked Python file
in `modules/` and `scripts/` finds each `getpass.getuser()` call, and only `host_actor` itself
and the files excused below, each with its reason, may hold one. A floor and a planted case
show the parse finds what it looks for.
"""

import ast
import os

from tests import source_index

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Files that may read the OS login for something that is not a recorded actor, each with why.
#: Only shrinks.
EXCUSED = {
    "scripts/nmas-deploy": "the deploy log's `user` and the check that .git is owned by the "
                           "deploying login: a file owner, not an actor of Mercury's records",
    "scripts/nmas-inventory-role": "records the login and `actor_verified: host-shell` apart; "
                                   "every reader labels it with `actor_label`",
}


def _python(path: str) -> bool:
    if path.endswith(".py"):
        return True
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline()
    except (UnicodeDecodeError, OSError):
        return False
    return first.startswith("#!") and "python" in first


def getuser_calls(paths, root=ROOT) -> dict:
    """``{relative path: [(line, enclosing function)]}`` for each `getpass.getuser()` call."""
    out = {}
    for path in paths:
        if not _python(path):
            continue
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        for fn in [tree] + [n for n in ast.walk(tree)
                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            body = fn.body if fn is not tree else [n for n in tree.body if not isinstance(
                n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            for stmt in body:
                for node in ast.walk(stmt):
                    f = getattr(node, "func", None)
                    if (isinstance(node, ast.Call) and isinstance(f, ast.Attribute)
                            and f.attr == "getuser" and isinstance(f.value, ast.Name)
                            and f.value.id == "getpass"):
                        out.setdefault(os.path.relpath(path, root), []).append(
                            (node.lineno, getattr(fn, "name", "<module>")))
    return {k: sorted(set(v)) for k, v in out.items()}


def _program():
    return source_index.tracked("modules", "scripts")


class TestEveryHostActorIsLabelled:
    def test_only_host_actor_reads_the_login(self):
        stray = {}
        for path, calls in getuser_calls(_program()).items():
            left = [c for c in calls if (path, c[1]) != ("modules/identity.py", "host_actor")]
            if left and path not in EXCUSED:
                stray[path] = left
        assert stray == {}, (
            "a host command reads the OS login for a record: name it through "
            f"identity.host_actor() (C237), or excuse the file with its reason: {stray}")

    def test_every_excused_file_still_reads_it(self):
        found = getuser_calls(_program())
        assert sorted(k for k in EXCUSED if k not in found) == [], \
            "an excused file no longer reads the login: drop it from EXCUSED (it only shrinks)"

    def test_the_scan_finds_something(self):
        """The floor: host_actor's own call and the excused files' (3 files on 2026-10-19)."""
        assert len(getuser_calls(_program())) >= 3

    def test_the_parse_sees_a_planted_call_and_ignores_prose(self, tmp_path):
        p = tmp_path / "planted"
        p.write_text('#!/usr/bin/env python3\n"""getpass.getuser() in prose is no call."""\n'
                     'import getpass\n\n\ndef main():\n    return getpass.getuser()\n',
                     encoding="utf-8")
        assert getuser_calls([str(p)], root=str(tmp_path)) == {"planted": [(7, "main")]}


class TestTheLabel:
    def test_host_actor_is_the_labelled_login(self, monkeypatch):
        from modules import identity

        monkeypatch.setattr("getpass.getuser", lambda: "ops")
        assert identity.host_actor() == "ops (host login, not a verified identity)"
