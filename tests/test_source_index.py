"""A scan of the checkout's source takes its files from what git tracks (C585).

Measured 2026-10-08: an agent's git worktree under `.claude/worktrees/` (excluded
from git by `.git/info/exclude`) is a whole second copy of the program inside the
checkout, and test_inventory_dispatch_refuses.py's survey walked the disk and
failed on the copies. 54 test files walked the checkout's source on disk, at 67
sites. The fix constrains the shape rather than the members: one list,
`source_index.tracked()`, from `git ls-files`, and a scan of every test file for
a walk (`os.walk`, `glob.glob`, `glob.iglob`, a path's `.glob`, `.rglob` or
`.walk`) whose path resolves to the checkout.

A path "resolves to the checkout" when it is built from `__file__`, from a
relative path (the suite runs with the checkout as its working directory), or
from `os.getcwd()`, through names, `os.path` and `pathlib` calls, the arguments a
function in the same file is called with, a function's return value, and a
module-level name imported from another test module. What it assumes stays true,
and so does not follow: a path held in a product module's constant
(`config.DATA_DIR` is the store, walked on purpose), a path a fixture returns,
and a path built by a call it does not know (`resolve(LIST).data_dir`). A walk the
scan finds that must stay a walk says why in a comment on its own line or the line
above it: ``# disk walk: <why>``.
"""

import ast
import io
import os
import re
import subprocess
import tokenize

import pytest

from tests import source_index

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: A walk that says why it stays one. Three words at least: a bare marker is not a reason.
EXEMPT = re.compile(r"#\s*disk walk:\s*(\S+(?:\s+\S+){2,})")

#: Calls that hand their first argument's place on through to their result.
_PASS_FIRST = {"os.path.join", "os.path.dirname", "os.path.abspath", "os.path.realpath",
               "os.path.normpath", "os.path.expanduser", "Path", "pathlib.Path",
               "PurePath", "pathlib.PurePath", "PosixPath", "str", "os.fspath", "sorted",
               "list", "tuple", "set", "frozenset", "reversed", "iter"}
_PASS_ANY = {"itertools.chain", "chain"}
_CWD = {"os.getcwd", "Path.cwd", "pathlib.Path.cwd"}
_PATH_METHODS = {"resolve", "absolute", "joinpath", "expanduser", "with_name", "with_suffix"}


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


class _File:
    """One test file's walks, with each walk's path resolved to the checkout or not."""

    def __init__(self, src, name, exports=None):
        self.src, self.name, self.exports = src, name, exports or {}
        self.tree = ast.parse(src, filename=name)
        self.parent = {}
        for n in ast.walk(self.tree):
            for c in ast.iter_child_nodes(n):
                self.parent[c] = n
        self.locals = {}            # scope node -> set of names bound in it
        self.funcs = {}             # name -> [FunctionDef]
        self.modules = {}           # alias -> module ("os", "glob", "pathlib", "tests.x")
        self.imported = []          # (scope, alias, module, name)
        for n in ast.walk(self.tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                if not isinstance(n, ast.Lambda):
                    self.funcs.setdefault(n.name, []).append(n)
                a = n.args
                for arg in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg]:
                    if arg is not None:
                        self.locals.setdefault(n, set()).add(arg.arg)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                self.locals.setdefault(self.scope(n), set()).add(n.id)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    self.modules[a.asname or a.name.split(".")[0]] = a.name if a.asname else \
                        a.name.split(".")[0]
            elif isinstance(n, ast.ImportFrom) and n.module:
                for a in n.names:
                    alias = a.asname or a.name
                    self.locals.setdefault(self.scope(n), set()).add(alias)
                    full = f"{n.module}.{a.name}"
                    if n.module in ("os", "glob", "pathlib", "itertools") or \
                            full.startswith("tests.") and full.count(".") == 1:
                        self.modules[alias] = full
                    self.imported.append((self.scope(n), alias, n.module, a.name))
        self.tainted = set()
        self._solve()

    # -- scopes ---------------------------------------------------------------
    def scope(self, node):
        """The function, class body or module a node is evaluated in."""
        child, n = node, self.parent.get(node)
        while n is not None:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                # Defaults, decorators and annotations run where the def is.
                if child is not n.args and child not in getattr(n, "decorator_list", ()) \
                        and child is not getattr(n, "returns", None):
                    return n
            elif isinstance(n, ast.ClassDef):
                if child not in n.bases and child not in n.decorator_list and \
                        child not in n.keywords:
                    return n
            child, n = n, self.parent.get(n)
        return self.tree

    def key(self, scope, name):
        """Where *name*, read in *scope*, is bound: Python's rule, class bodies skipped
        from inside their methods."""
        s, first = scope, True
        while True:
            if name in self.locals.get(s, ()) and (first or not isinstance(s, ast.ClassDef)):
                return (s, name)
            if s is self.tree:
                return (s, name)
            first = False
            s = self.scope(s)

    # -- does an expression name a place in the checkout? -------------------------
    def checkout(self, e, scope):
        if e is None:
            return False
        if isinstance(e, ast.Name):
            return e.id == "__file__" or self.key(scope, e.id) in self.tainted
        if isinstance(e, ast.Constant):
            return isinstance(e.value, str) and not e.value.startswith(("/", "~"))
        if isinstance(e, ast.JoinedStr):
            first = e.values[0] if e.values else None
            if isinstance(first, ast.FormattedValue):
                return self.checkout(first.value, scope)
            return first is None or self.checkout(first, scope)
        if isinstance(e, ast.BinOp) and isinstance(e.op, (ast.Div, ast.Add, ast.Mod)):
            return self.checkout(e.left, scope)
        if isinstance(e, (ast.Tuple, ast.List, ast.Set)):
            return any(self.checkout(x, scope) for x in e.elts)
        if isinstance(e, ast.Starred):
            return self.checkout(e.value, scope)
        if isinstance(e, ast.IfExp):
            return self.checkout(e.body, scope) or self.checkout(e.orelse, scope)
        if isinstance(e, ast.BoolOp):
            return any(self.checkout(x, scope) for x in e.values)
        if isinstance(e, ast.NamedExpr):
            return self.checkout(e.value, scope)
        if isinstance(e, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return self.checkout(e.elt, self.scope(e.elt))
        if isinstance(e, ast.Subscript):        # `p.parents[1]`; never a dict's value
            return isinstance(e.value, ast.Attribute) and e.value.attr == "parents" and \
                self.checkout(e.value, scope)
        if isinstance(e, ast.Attribute):
            if e.attr in ("parent", "parents"):
                return self.checkout(e.value, scope)
            if isinstance(e.value, ast.Name) and e.value.id in ("self", "cls"):
                return ("attr", e.attr) in self.tainted
            mod = self.modules.get(_dotted(e.value) or "")
            if mod and mod.startswith("tests."):
                return e.attr in self.exports.get(mod, ())
            return False
        if isinstance(e, ast.Call):
            name = self._callee(e.func)
            if name in _CWD:
                return True
            if name in _PASS_FIRST:
                return not e.args and name.endswith("Path") or bool(e.args) and \
                    self.checkout(e.args[0], scope)
            if name in _PASS_ANY:
                return any(self.checkout(a, scope) for a in e.args)
            if isinstance(e.func, ast.Attribute) and e.func.attr in _PATH_METHODS:
                return self.checkout(e.func.value, scope)
            return any(("ret", id(f)) in self.tainted for f in self._targets(e))
        return False

    def _callee(self, func):
        d = _dotted(func)
        if d is None:
            return None
        head, _, rest = d.partition(".")
        mod = self.modules.get(head)
        return (mod + ("." + rest if rest else "")) if mod else d

    def _targets(self, call):
        """The functions in this file a call may reach, by name."""
        f = call.func
        if isinstance(f, ast.Name):
            return self.funcs.get(f.id, [])
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and \
                f.value.id not in self.modules:
            return self.funcs.get(f.attr, [])
        return []

    # -- what flows where ---------------------------------------------------------
    def _bind(self, target, scope):
        keys = set()
        for n in ast.walk(target):
            if isinstance(n, ast.Name):
                keys.add(self.key(scope, n.id))
                if isinstance(scope, ast.ClassDef):
                    keys.add(("attr", n.id))
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and \
                    n.value.id in ("self", "cls"):
                keys.add(("attr", n.attr))
        return keys

    def _flows(self):
        out = []
        for n in ast.walk(self.tree):
            s = self.scope(n)
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    out.append((self._bind(t, s), n.value, s))
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign)) and n.value is not None:
                out.append((self._bind(n.target, s), n.value, s))
            elif isinstance(n, ast.NamedExpr):
                out.append((self._bind(n.target, s), n.value, s))
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                out.append((self._bind(n.target, s), n.iter, s))
            elif isinstance(n, ast.comprehension):
                cs = self.scope(n.target)
                out.append((self._bind(n.target, cs), n.iter, cs))
            elif isinstance(n, ast.withitem) and n.optional_vars is not None:
                out.append((self._bind(n.optional_vars, s), n.context_expr, s))
            elif isinstance(n, ast.Return) and n.value is not None:
                fn = s
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(({("ret", id(fn))}, n.value, s))
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a, outer = n.args, self.scope(n)
                pos = a.posonlyargs + a.args
                for arg, d in zip(pos[len(pos) - len(a.defaults):], a.defaults):
                    out.append(({(n, arg.arg)}, d, outer))
                for arg, d in zip(a.kwonlyargs, a.kw_defaults):
                    if d is not None:
                        out.append(({(n, arg.arg)}, d, outer))
            elif isinstance(n, ast.Call):
                for f in self._targets(n):
                    params = [x.arg for x in f.args.posonlyargs + f.args.args]
                    if isinstance(n.func, ast.Attribute) and params[:1] in (["self"], ["cls"]):
                        params = params[1:]
                    for p, v in zip(params, n.args):
                        out.append(({(f, p)}, v, s))
                    for kw in n.keywords:
                        if kw.arg:
                            out.append(({(f, kw.arg)}, kw.value, s))
        return out

    def _solve(self):
        for scope, alias, module, name in self.imported:
            mod = module if module.startswith("tests.") else f"tests.{module}"
            if name in self.exports.get(mod, ()):
                self.tainted.add(self.key(scope, alias))
        flows = self._flows()
        changed = True
        while changed:
            changed = False
            for keys, value, scope in flows:
                if keys - self.tainted and self.checkout(value, scope):
                    self.tainted |= keys
                    changed = True

    # -- the walks ----------------------------------------------------------------
    def walks(self):
        """``(line, call text, resolves to the checkout, exempted)`` for every walk."""
        reasons = {}
        for tok in tokenize.generate_tokens(io.StringIO(self.src).readline):
            if tok.type == tokenize.COMMENT and EXEMPT.match(tok.string):
                reasons[tok.start[0]] = tok.string
        out = []
        for n in ast.walk(self.tree):
            if not isinstance(n, ast.Call):
                continue
            name, f, path = self._callee(n.func), n.func, None
            if name in ("os.walk", "glob.glob", "glob.iglob"):
                path = n.args[0] if n.args else None
                root_dir = next((k.value for k in n.keywords if k.arg == "root_dir"), None)
                if root_dir is not None:
                    path = root_dir
            elif isinstance(f, ast.Attribute) and f.attr in ("glob", "rglob", "walk") and \
                    name not in ("glob.glob", "ast.walk"):
                path = f.value
            else:
                continue
            here = self.checkout(path, self.scope(n))
            out.append((n.lineno, ast.unparse(n)[:100], here,
                        n.lineno in reasons or n.lineno - 1 in reasons))
        return sorted(out)

    def module_names(self):
        return {name for scope, name in self.tainted if scope is self.tree}


def _test_files():
    return source_index.tracked("tests", suffix=".py")


def _module(path):
    return "tests." + os.path.splitext(os.path.relpath(path, os.path.join(ROOT, "tests")))[0] \
        .replace(os.sep, ".")


def survey(files=None):
    """``{relative path: [walks]}`` over every tracked test file. Module-level names a
    test module exports are resolved first, so an import carries them."""
    files = files or _test_files()
    srcs = {p: open(p, encoding="utf-8").read() for p in files}
    exports = {}
    for _ in range(3):                     # helpers importing helpers: settles in two
        exports = {_module(p): _File(s, p, exports).module_names() for p, s in srcs.items()}
    return {os.path.relpath(p, ROOT): _File(s, p, exports).walks() for p, s in srcs.items()}


@pytest.fixture(scope="module")
def walks():
    return survey()


# -- the helper ---------------------------------------------------------------------

def _git(repo, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                    "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                    "-c", "core.hooksPath=/dev/null", *args],
                   check=True, capture_output=True, env=env, timeout=30)


@pytest.fixture
def planted(tmp_path):
    """A repository whose answer is known without the helper: three committed files,
    one staged, one untracked, one ignored, one committed then deleted from disk."""
    repo = tmp_path / "repo"
    (repo / "modules" / "nsot").mkdir(parents=True)
    (repo / "templates").mkdir()
    for rel in ("app.py", "modules/a.py", "modules/nsot/b.py", "modules/gone.py",
                "templates/x.html"):
        (repo / rel).write_text("x\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "app.py", "modules/a.py", "modules/nsot/b.py", "modules/gone.py")
    _git(repo, "commit", "-q", "-m", "planted")
    _git(repo, "add", "templates/x.html")                     # staged, never committed
    (repo / ".gitignore").write_text("ignored.py\n")
    (repo / "ignored.py").write_text("x\n")
    (repo / "modules" / "untracked.py").write_text("x\n")
    (repo / ".claude" / "worktrees" / "copy" / "modules").mkdir(parents=True)
    (repo / ".claude" / "worktrees" / "copy" / "modules" / "a.py").write_text("x\n")
    (repo / "modules" / "gone.py").unlink()
    return repo


class TestTracked:
    def _rel(self, repo, paths):
        return [os.path.relpath(p, repo).replace(os.sep, "/") for p in paths]

    def test_lists_what_the_index_holds_and_nothing_else(self, planted):
        assert self._rel(planted, source_index.tracked(root=planted)) == [
            "app.py", "modules/a.py", "modules/nsot/b.py", "templates/x.html"]

    def test_never_a_file_under_git_an_untracked_file_or_a_worktree_copy(self, planted):
        got = self._rel(planted, source_index.tracked(root=planted))
        assert not [p for p in got if p.startswith((".git/", ".claude/"))]
        assert "modules/untracked.py" not in got and "ignored.py" not in got
        # The control: each one IS on disk, so a walk would have found it.
        on_disk = {os.path.relpath(os.path.join(d, f), planted).replace(os.sep, "/")
                   for d, _s, fs in os.walk(planted) for f in fs}
        assert {"modules/untracked.py", "ignored.py", ".claude/worktrees/copy/modules/a.py",
                ".git/HEAD"} <= on_disk

    def test_a_tracked_file_deleted_from_disk_is_left_out(self, planted):
        assert "modules/gone.py" not in self._rel(planted, source_index.tracked(root=planted))

    def test_folders_suffixes_and_depth(self, planted):
        t = source_index.tracked
        assert self._rel(planted, t("modules", root=planted)) == ["modules/a.py",
                                                                  "modules/nsot/b.py"]
        assert self._rel(planted, t("modules", root=planted, recursive=False)) == \
            ["modules/a.py"]
        assert self._rel(planted, t(str(planted / "modules" / "nsot"), root=planted)) == \
            ["modules/nsot/b.py"]
        assert self._rel(planted, t("app.py", "templates", root=planted)) == \
            ["app.py", "templates/x.html"]
        assert self._rel(planted, t(root=planted, suffix=(".html",))) == ["templates/x.html"]
        assert self._rel(planted, t("modul", root=planted)) == []      # a folder, not a prefix
        with pytest.raises(ValueError, match="outside"):
            t(str(planted.parent), root=planted)

    def test_a_root_git_cannot_read_is_raised_never_an_empty_list(self, tmp_path):
        with pytest.raises(RuntimeError, match="ls-files"):
            source_index.tracked(root=tmp_path)

    def test_on_the_checkout(self):
        got = source_index.tracked()
        assert len(got) > 1000, len(got)                                 # the floor
        assert os.path.join(ROOT, "tests", "source_index.py") in got
        rel = [os.path.relpath(p, ROOT).replace(os.sep, "/") for p in got]
        assert not [p for p in rel if p.startswith((".git/", ".claude/worktrees/"))]


# -- the shape ----------------------------------------------------------------------

PLANT = '''
import glob, os
from pathlib import Path
from tests.helper import TEMPLATES
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROOT = Path(__file__).resolve().parent.parent

def a():
    return os.walk(os.path.join(ROOT, "modules"))               # line 9: by a name

def b(tmp_path):
    return list(tmp_path.rglob("*.py"))                          # line 12: a temporary folder

def c(root=ROOT):
    return os.walk(root)                                         # line 15: by a default

def d():
    return glob.glob("routes/**/*.py", recursive=True)           # line 18: relative

def e():
    return sorted((PROOT / "routes").rglob("*.py"))              # line 21: a Path

def f():
    return os.walk(TEMPLATES)                                    # line 24: imported

def g():
    # disk walk: data is the store, untracked by design
    return os.walk(os.path.join(ROOT, "data"))                   # line 28: exempt

def h():
    return os.walk(os.path.join(ROOT, "x"))  # disk walk: no

def k(x):
    return os.walk(x)                                            # line 34: by an argument

def m():
    return k(PROOT)

def n(store):
    return glob.glob(os.path.join(store, "*.json"))              # line 40: never called
'''


class TestTheScanFindsTheShape:
    def _walks(self, src=PLANT):
        return {line: (here, exempt) for line, _t, here, exempt in
                _File(src, "plant.py", {"tests.helper": {"TEMPLATES"}}).walks()}

    def test_each_way_a_path_reaches_the_checkout_is_found(self):
        got = self._walks()
        assert {line for line, (here, _e) in got.items() if here} == \
            {9, 15, 18, 21, 24, 28, 31, 34}
        assert got[12] == (False, False) and got[40] == (False, False)

    def test_an_exemption_needs_a_reason(self):
        got = self._walks()
        assert got[28] == (True, True)
        assert got[31] == (True, False)

    def test_an_unrelated_walk_is_left_alone(self):
        src = "import ast\ndef f(tree):\n    return list(ast.walk(tree))\n"
        assert self._walks(src) == {}


class TestNoTestWalksTheCheckout:
    def test_the_population(self, walks):
        """Floors, so a scan that found nothing cannot pass: the files, the walks it
        judged, and the calls of `tracked()` the conversion left."""
        assert len(walks) >= 400, len(walks)
        assert sum(len(w) for w in walks.values()) >= 15     # 19 walks left, 2026-10-08
        calls = 0
        for rel in walks:
            for n in source_index.nodes(os.path.join(ROOT, rel)):
                if isinstance(n, ast.Call) and _dotted(n.func) in ("tracked",
                                                                   "source_index.tracked"):
                    calls += 1
        assert calls >= 60, calls

    def test_every_walk_of_the_checkout_goes_through_tracked(self, walks):
        bad = [f"{rel}:{line} {text}" for rel, ws in walks.items() for line, text, here, exempt in ws
               if here and not exempt]
        assert bad == [], (
            "these walk the checkout on disk, so an untracked copy (an agent's worktree "
            "under .claude/worktrees/) is scanned as program: take the list from "
            "source_index.tracked(), or say why on the line (# disk walk: <why>):\n"
            + "\n".join(bad))
