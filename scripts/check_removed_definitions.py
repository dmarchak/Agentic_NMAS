#!/usr/bin/env python3
"""List definitions a diff removes. Read-only. Run it before committing.

Three edits in this project have destroyed code the author was not looking at:
``modules/nsot/deploy.py`` grew to 2.4MB of recursion, a pruning script deleted
test class headers, and a slice replacement to EOF removed ``_deploy_one()`` —
the only function in ``routes/deploy.py`` that connects to a device — which then
sat on the live host for three commits while 1133 tests passed.

All three share one signature: **a block of deleted ``def``/``class`` lines the
author did not mean to delete.** That is cheap to look for and hard to see in a
long diff, so it gets a script rather than a habit.

The output is ranked, because a raw list of every removed definition is noise
during a refactor:

* **BROKEN**     — not defined afterwards, and **still called in the same
                   file**. That is a ``NameError`` waiting for the first
                   request that reaches it, and it is precisely what happened
                   to ``_deploy_one``: a private helper called only from its
                   own module, so no cross-file search would have found it.
* **GONE**       — not defined afterwards, still referenced by another file.
* **gone**       — not defined afterwards, and nothing references it.
* **moved**      — still defined in the same file; the diff moved or reindented it.

Usage::

    python scripts/check_removed_definitions.py            # staged changes
    python scripts/check_removed_definitions.py --unstaged
    python scripts/check_removed_definitions.py HEAD~3     # against a ref

Exit code is 1 when anything is BROKEN or GONE, so it can gate a commit hook;
every other outcome exits 0 and simply reports.
"""

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: `-` then optional indent then a definition. Captures indent and name, because
#: a NESTED def is an implementation detail of the function around it: removing
#: one alongside its parent is correct, and reporting it as a lost definition is
#: how a checker earns `--no-verify`.
REMOVED = re.compile(r"^-(\s*)(?:async\s+)?(def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
DEFINED = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")


def _git(*args) -> str:
    proc = subprocess.run(["git", "-C", ROOT, *args],
                          capture_output=True, text=True)
    return proc.stdout


def _after(args) -> str:
    """The revision the diff ends at, or "" for the working tree.

    A historical range must be judged against the file **as it was at the end
    of that range**, not against today's working tree — otherwise pointing the
    script at the commit that did the damage reports it as clean, because the
    fix is already in the checkout.
    """
    if args.ref and ".." in args.ref:
        right = args.ref.split("..")[-1]
        return right or "HEAD"
    return ""


def _diff(args) -> str:
    if args.ref:
        return _git("diff", args.ref, "--unified=0")
    if args.unstaged:
        return _git("diff", "--unified=0")
    return _git("diff", "--cached", "--unified=0")


def _read_at(path: str, rev: str) -> str:
    if rev:
        return _git("show", f"{rev}:{path}")
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return ""
    with open(full, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _defined_now(path: str, rev: str = "") -> set:
    return {m.group(1)
            for m in (DEFINED.match(l) for l in _read_at(path, rev).splitlines())
            if m}


def _called_in(name: str, path: str, rev: str = "") -> bool:
    """Is *name* still called in its own file, with no definition left?"""
    called = re.compile(rf"(?<![\w.]){re.escape(name)}\s*\(")
    for line in _read_at(path, rev).splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", "def ", "class ", "async def ")):
            continue
        if called.search(line):
            return True
    return False


def _referenced_elsewhere(name: str, path: str, rev: str = "") -> list:
    """Files other than *path* that still mention *name* AND do not define it.

    A file carrying its own function of the same name is not a caller of the
    removed one. ``_ios_error`` existed as a private helper inside two
    unrelated modules; removing one was reported as breaking the other.
    """
    args = ["grep", "-l", "-w"]
    if rev:
        args.append(rev)
    out = _git(*args, name, "--", "*.py", "*.html")
    files = [l.split(":", 1)[-1] if rev else l for l in out.splitlines()]
    return sorted(f for f in files
                  if f and f != path and name not in _defined_now(f, rev))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ref", nargs="?", default="")
    ap.add_argument("--unstaged", action="store_true")
    args = ap.parse_args()

    diff = _diff(args)
    if not diff.strip():
        print("no changes to scan")
        return 0

    path, removed = "", []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            continue
        if not path.endswith(".py"):
            continue
        match = REMOVED.match(line)
        if match:
            removed.append((path, match.group(2), match.group(3),
                            len(match.group(1))))

    if not removed:
        print("no definitions removed by this diff")
        return 0

    after = _after(args)
    still_defined = {}
    findings = []
    for path, kind, name, indent in removed:
        if indent:
            # Nested. It lived inside something else, and if that something
            # else survived, the name is still defined in this file — which the
            # check below establishes. Reported as `local`, never as BROKEN.
            findings.append(("local", path, kind, name, []))
            continue
        if path not in still_defined:
            still_defined[path] = _defined_now(path, after)
        if name in still_defined[path]:
            findings.append(("moved", path, kind, name, []))
            continue

        # The same file first. A private helper is usually called only from its
        # own module, so a cross-file search reports the worst case as the
        # mildest one — which is how this script would have shrugged at the
        # deletion it exists to catch.
        if _called_in(name, path, after):
            findings.append(("BROKEN", path, kind, name, [path]))
            continue
        callers = _referenced_elsewhere(name, path, after)
        findings.append(("GONE" if callers else "gone", path, kind, name, callers))

    order = {"BROKEN": 0, "GONE": 1, "gone": 2, "local": 3, "moved": 4}
    findings.sort(key=lambda f: (order[f[0]], f[1], f[3]))

    width = max(len(f[3]) for f in findings)
    print(f"\n{len(findings)} definition(s) removed by this diff\n")
    for status, path, kind, name, callers in findings:
        print(f"  {status:<6}  {kind:<5} {name.ljust(width)}  {path}")
        if callers:
            print(f"{' ' * (16 + width)}still referenced in: "
                  f"{', '.join(callers[:4])}")

    broken = [f for f in findings if f[0] == "BROKEN"]
    if broken:
        print(f"\n{len(broken)} removed definition(s) are STILL CALLED in the "
              "same file. Whatever the edit was aimed at, it took these too.")

    critical = [f for f in findings if f[0] == "GONE"]
    if critical:
        print(f"\n{len(critical)} removed definition(s) are still referenced "
              "elsewhere. If that was not the intent, the edit took something "
              "it was not aimed at.")
    if broken or critical:
        return 1

    gone = [f for f in findings if f[0] == "gone"]
    if gone:
        print(f"\n{len(gone)} definition(s) are gone with no remaining "
              "references. Confirm each was meant to go.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
