"""The per-test store guard's content comparison (C571, the operator's approval, 2026-10-08).

The per-test guard in conftest compared PATHS: a test that rewrote a file already in the shared
store passed unseen, and one did (`test_session_write_guard`'s fixture rewrote the Default list's
`devices.csv`; CI #516 went red in another test, order-dependently). Measured before this check
was made: 0 of 9,490 tests rewrite or delete an existing store file, so no exemption is needed.

Each test's start keeps every store file's BYTES (the shared store holds a few small files when
a test begins); after it, a file whose bytes differ is ``rewritten`` and one gone is
``deleted``. The guard puts each back, so one offender never becomes the next test's failure,
then fails the offender naming the file. A module of its own, with no side effects, so a test
can import it (tests/store_guard.py says why conftest cannot be).
"""

import os


def contents(root: str) -> dict:
    """``{path: bytes}`` for every file under *root*, `.git` folders left out (they churn on
    any read)."""
    out = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            path = os.path.join(folder, name)
            try:
                with open(path, "rb") as fh:
                    out[path] = fh.read()
            except OSError:
                continue
    return out


def changes(before: dict) -> list:
    """``[(path, "rewritten" | "deleted")]``: each file of *before* whose bytes differ now, or
    that is gone."""
    out = []
    for path, data in sorted(before.items()):
        try:
            with open(path, "rb") as fh:
                now = fh.read()
        except FileNotFoundError:
            out.append((path, "deleted"))
            continue
        except OSError:
            continue
        if now != data:
            out.append((path, "rewritten"))
    return out


def restore(before: dict, changed: list) -> None:
    """Put each changed file back as it was."""
    for path, _kind in changed:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(before[path])
