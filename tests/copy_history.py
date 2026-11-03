"""The shipped templates' git history, read in mutmut's copy of the checkout (C1651).

mutmut runs the suite in a copy at `mutants/`, inside the checkout and untracked. There
`templates_repo` asks the application's git for a shipped template's history at its path
relative to the repository's root, `mutants/modules/nsot/templates/<file>`, which git has
never tracked, so it finds none. `history_in_copy` wraps that ONE lookup: a path under the
copy's own prefix is read at the same path without it, the original's history of the same
file. Nothing else is redirected: a network repository's history (`git` given), a path
outside the copy's prefix, and every read of a template's content are left as they are.
"""
import os


def copy_prefix(copy_root: str, copy_of: str) -> str:
    """The copy's folder relative to the checkout it copies (``mutants``), or "" when
    *copy_root* is not inside *copy_of* (no copy, or one elsewhere)."""
    if not copy_of:
        return ""
    root, of = os.path.realpath(copy_root), os.path.realpath(copy_of)
    if root == of or not root.startswith(of + os.sep):
        return ""
    return os.path.relpath(root, of).replace(os.sep, "/")


def history_in_copy(history, prefix: str):
    """*history* (`templates_repo._history`) with the application's own lookups of a path
    under *prefix* read at the path without it."""
    def wrapped(cwd, rel, git=None):
        if git is None and prefix and rel.startswith(prefix + "/"):
            rel = rel[len(prefix) + 1:]
        return history(cwd, rel, git=git)
    wrapped.copy_prefix = prefix
    return wrapped
