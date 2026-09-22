#!/usr/bin/env python3
"""Stage C: add a user-skip to the c8000v launch patch, minimally and visibly.

Run this on the lab host, against a COPY of rcn-lab1's launch patch. It prints
a unified diff and writes nothing unless you pass --write.

    cp ~/labs/lab/patches/c8000v-launch.py patches/c8000v-launch-userskip.py
    python3 patches/patch-skip-injected-user.py patches/c8000v-launch-userskip.py
    python3 patches/patch-skip-injected-user.py patches/c8000v-launch-userskip.py --write

WHY THIS IS A SCRIPT AND NOT A .patch FILE
------------------------------------------
The launch script is not in this repository and is not on the machine the
change was written on, so a hand-written diff would carry invented context
lines. This locates its anchors in the real file, refuses if they are not
exactly what stage B measured, and generates the diff from the file itself.
A patch you cannot verify against the thing it patches is a guess with line
numbers on it.

WHAT IT CHANGES
---------------
Two edits, both minimal:

1. One helper function at module scope.
2. One line -- the concatenation `cfg = self.gen_bootstrap_config() +
   startup_cfg` -- wrapped in a call to it.

`gen_bootstrap_config()` itself is not touched. The injection still happens
for every user the startup config does not define, so a node with no startup
config, or one defining a different user, boots exactly as it does today.
"""

import argparse
import difflib
import os
import re
import sys

# The helper, inserted verbatim at module scope. Kept free of `self` so it
# does not depend on the VM class's attribute names: it uses `logging`, which
# every vrnetlab launch script already imports and configures.
HELPER = '''
def _skip_users_defined_in_startup(bootstrap, startup):
    """Drop bootstrap's `username X ...` when the startup config defines X.

    NMAS stage-B finding, measured on a C8000v on 2026-09-21: this script's
    injected `username admin privilege 15 password admin` is applied BEFORE
    the startup config, so a `username admin ... secret 9 <hash>` line in that
    config is REFUSED --

        %CVAC-4-CLI_FAILURE: Configuration command failure:
          'username admin privilege 15 secret 9 $9$...' was rejected

    -- because IOS-XE will not accept a secret for a user that already has a
    password. The node then keeps admin/admin while its startup file says
    otherwise, and `Startup complete` is still reached, so nothing announces
    it.

    Skipping the injection for a user the startup config defines itself lets
    the file's own credential land. Users the startup config does not define
    are still injected, unchanged.
    """
    defined = set(re.findall(r"(?m)^\\s*username\\s+(\\S+)\\s", startup or ""))
    if not defined:
        return bootstrap

    kept = []
    skipped = []
    for line in (bootstrap or "").splitlines(True):
        match = re.match(r"\\s*username\\s+(\\S+)\\s", line)
        if match and match.group(1) in defined:
            skipped.append(match.group(1))
        else:
            kept.append(line)

    if skipped:
        logging.getLogger(__name__).info(
            "startup config defines %s; not injecting vrnetlab's own username "
            "line for it", ", ".join(sorted(set(skipped))))

    # A dropped final line must not join the next block to the previous one.
    if kept and not kept[-1].endswith("\\n"):
        kept[-1] += "\\n"
    return "".join(kept)

'''

#: The line stage B measured, at launch.py:89. Matched by content, not number.
CONCAT = re.compile(
    r"^(?P<indent>[ \t]*)cfg\s*=\s*self\.gen_bootstrap_config\(\)\s*\+\s*startup_cfg\s*$")

#: The injected line, at launch.py:157. Checked for PRESENCE only -- if it is
#: gone, this patch is solving a problem the file no longer has. Deliberately
#: unanchored: the line lives inside a quoted config block whose indentation
#: is the author's business, and an anchor here bought nothing except a
#: refusal that named the wrong anchor.
INJECTED = re.compile(r"username\s+\S+\s+privilege\s+15\s+password\s+")


class Refused(Exception):
    """An anchor was not what stage B measured. Do not patch blind."""


def patch(text):
    if "_skip_users_defined_in_startup" in text:
        raise Refused("already patched -- the helper is present")

    # Imports via the PARSER. A regex for `^import re` misses
    # `import datetime, logging, os, re, signal` -- the combined form these
    # launch scripts actually use -- and would refuse the real file for a
    # reason that is not true of it. A guard that cries wolf on a correct
    # file is one somebody edits out.
    imported = set()
    try:
        import ast

        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                imported.update(a.asname or a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.update(a.asname or a.name for a in node.names)
    except SyntaxError as exc:
        raise Refused(f"this file does not parse as Python: {exc}") from exc

    for module in ("re", "logging"):
        if module not in imported:
            raise Refused(
                "the helper needs `import %s` and this file does not have it. "
                "Add the import deliberately rather than letting this script "
                "do it silently." % module)

    if not INJECTED.search(text):
        raise Refused(
            "no `username <x> privilege 15 password ...` line found. Stage B "
            "measured one at line 157; without it there is nothing to skip "
            "and this patch is answering a stale reading of the file.")

    lines = text.splitlines(True)

    sites = [i for i, line in enumerate(lines) if CONCAT.match(line.rstrip("\n"))]
    if len(sites) != 1:
        raise Refused(
            "expected exactly one `cfg = self.gen_bootstrap_config() + "
            "startup_cfg`, found %d. Two call sites means one of them would "
            "keep the old behaviour." % len(sites))

    index = sites[0]
    indent = CONCAT.match(lines[index].rstrip("\n")).group("indent")
    lines[index] = (
        "%scfg = _skip_users_defined_in_startup(\n"
        "%s    self.gen_bootstrap_config(), startup_cfg) + startup_cfg\n"
        % (indent, indent))

    # Module scope, above the first class, so it is defined before use.
    classes = [i for i, line in enumerate(lines) if line.startswith("class ")]
    if not classes:
        raise Refused("no module-level class; cannot place the helper safely")
    lines.insert(classes[0], HELPER.lstrip("\n") + "\n")

    return "".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="a COPY of the launch patch, never the original")
    parser.add_argument("--write", action="store_true",
                        help="apply the change (default: print the diff only)")
    args = parser.parse_args()

    if os.path.realpath(args.path).startswith(
            os.path.expanduser("~/labs/lab") + os.sep):
        sys.exit("refusing to edit rcn-lab1's own patch in place. Copy it first.")

    with open(args.path, encoding="utf-8") as handle:
        before = handle.read()

    try:
        after = patch(before)
    except Refused as exc:
        sys.exit("REFUSED: %s" % exc)

    diff = difflib.unified_diff(
        before.splitlines(True), after.splitlines(True),
        fromfile=args.path + " (rcn-lab1 patch)",
        tofile=args.path + " (+ user skip)")
    sys.stdout.writelines(diff)

    if not args.write:
        print("\n-- diff only. Re-run with --write to apply.")
        return

    with open(args.path, "w", encoding="utf-8") as handle:
        handle.write(after)
    print("\nwritten: %s" % args.path)


if __name__ == "__main__":
    main()
