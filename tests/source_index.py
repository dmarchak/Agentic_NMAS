"""One parse of each source file per test process (register C45), and one
list of the files the repository holds (register C585).

The source-tree scans parsed the same files again for every question: 4,402
parses across seven scan files in one profile, and walking the trees was most
of the rest. These trees are SHARED between the tests that ask for them:
read them, never modify them (no `NodeTransformer`, no attributes set on a
node). A file is re-read when its mtime or size moves, so a scan of a file a
test just wrote sees the new content.

`tracked()` is where a scan of the checkout's own source takes its population:
what `git ls-files` lists (the index), never what a walk of the disk finds. A
walk counted an agent's git worktree under `.claude/worktrees/` (excluded from
git, a whole second copy of the program) as more program, and a scan failed on
the copies (C585). What the index holds: committed files and staged ones, so a
new file is scanned once it is `git add`-ed (the gate stages before the suite,
and CI's checkout is the index); an untracked or ignored file never is.
tests/test_source_index.py holds the shape: no test walks the checkout's source
except through `tracked()` or a walk that says why on its own line.

No side effects on import.
"""

import ast
import functools
import os
import subprocess

#: The checkout: this file is tests/source_index.py.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Variables a git hook exports that would point `git -C <root>` at another
#: repository's directory or index (a suite run inside a hook, or a planted
#: repository under one).
_GIT_REDIRECTS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                  "GIT_OBJECT_DIRECTORY", "GIT_PREFIX")


@functools.lru_cache(maxsize=None)
def _listing(root):
    """Every path the index at *root* holds, relative and '/'-separated, once per
    process per root. A failure is raised, naming the command: an empty list would
    make every scan over it pass."""
    cmd = ["git", "-C", root, "ls-files", "-z"]
    env = {k: v for k, v in os.environ.items() if k not in _GIT_REDIRECTS}
    # Measured 0.005 s for 1,415 files (2026-10-08); the bound is for a process
    # start on a loaded runner, which 2.5x of that could not cover.
    r = subprocess.run(cmd, capture_output=True, env=env, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} exited {r.returncode}: "
                           f"{r.stderr.decode(errors='replace').strip()}")
    return tuple(p for p in r.stdout.decode("utf-8", errors="surrogateescape").split("\0") if p)


def track_all(root):
    """Make a planted tree (a test's temporary folder) a repository whose index holds
    every file in it, so a scan that reads through `tracked(root=...)` sees the plant.
    Nothing is committed: `ls-files` reads the index."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_REDIRECTS}
    for args in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                       env=env, timeout=30)
    _listing.cache_clear()
    return str(root)


def tracked(*folders, suffix=None, recursive=True, root=None):
    """Absolute paths, sorted, of the files git tracks under *root* (the checkout by
    default) that exist in the working tree, limited to *folders* when given.

    A folder is relative to *root* or absolute inside it, and may name a single file
    (`tracked("app.py", "modules")`). *suffix* is a string or a tuple of them, as
    `str.endswith` takes. ``recursive=False`` keeps only a folder's direct children,
    as a glob of ``folder/*`` would. A tracked file deleted from the working tree is
    left out, never an error. Paths are *root* joined with git's path, so a caller's
    `os.path.relpath(p, root)` gives back git's spelling."""
    root = os.path.abspath(str(root)) if root is not None else ROOT
    wanted = []
    for f in folders:
        f = str(f)
        rel = os.path.relpath(f, root) if os.path.isabs(f) else os.path.normpath(f)
        if rel == os.curdir:
            rel = ""
        elif rel == os.pardir or rel.startswith(os.pardir + os.sep):
            raise ValueError(f"{f!r} is outside {root!r}")
        wanted.append(rel.replace(os.sep, "/").strip("/"))
    out = []
    for p in _listing(root):
        if suffix is not None and not p.endswith(suffix):
            continue
        if folders:
            for w in wanted:
                if w == "":
                    rest = p
                elif p == w:
                    rest = os.path.basename(p)
                elif p.startswith(w + "/"):
                    rest = p[len(w) + 1:]
                else:
                    continue
                if recursive or "/" not in rest:
                    break
            else:
                continue
        full = os.path.join(root, *p.split("/"))
        if os.path.isfile(full):
            out.append(full)
    return sorted(out)


@functools.lru_cache(maxsize=None)
def _parse(path, mtime_ns, size):
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=path)


@functools.lru_cache(maxsize=None)
def _nodes(path, mtime_ns, size):
    return tuple(ast.walk(_parse(path, mtime_ns, size)))


def _key(path):
    st = os.stat(path)
    return os.path.realpath(path), st.st_mtime_ns, st.st_size


def tree(path):
    """The parsed module at *path* (shared: read-only)."""
    return _parse(*_key(str(path)))


def nodes(path):
    """Every node of *path*'s tree, in `ast.walk` order (shared: read-only)."""
    return _nodes(*_key(str(path)))
