"""One parse of each source file per test process (register C45).

The source-tree scans parsed the same files again for every question: 4,402
parses across seven scan files in one profile, and walking the trees was most
of the rest. These trees are SHARED between the tests that ask for them:
read them, never modify them (no `NodeTransformer`, no attributes set on a
node). A file is re-read when its mtime or size moves, so a scan of a file a
test just wrote sees the new content.

No side effects on import.
"""

import ast
import functools
import os


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
