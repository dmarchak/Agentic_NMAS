"""Run a script under the interpreter the app runs (Phase 4 section 8.1; the operator, 2026-10-09).

Every Mercury script a person or a unit starts on the host calls `adopt(__name__)` first, before
any import outside the standard library. It reads the interpreter `flask-app` runs from systemd
(the unit's ExecStart) and, when another interpreter started the script, re-runs the script
under that one, saying so on stderr. So the app and its tools import the same versions in every
state: `/usr/bin/python3` before the virtualenv switch, the venv's link after it and across every
swap, `/usr/bin/python3` again after the switch's undo. No shell's PATH decides.

Where no `flask-app` unit exists (the laptop, CI) the script runs as started, saying nothing.
A re-run that still reports another prefix is refused, never looped.

STANDARD LIBRARY ONLY: it runs before the interpreter is settled. One home: no script carries a
copy (tests/test_app_interpreter.py holds every script to calling it).
"""

import hashlib
import os
import re
import subprocess
import sys

#: The unit whose interpreter every Mercury script takes.
APP_UNIT = "flask-app.service"
#: Set on the re-run: an interpreter still reporting another prefix is refused, never looped.
REEXEC = "NMAS_ADOPTED_APP_INTERPRETER"
#: Measured on the host 2026-10-09: 11 to 14 ms; bounded at about 2.5 times a slow start.
SYSTEMCTL_TIMEOUT_S = 10


def app_interpreter(show=None):
    """The program APP_UNIT's ExecStart runs, read from systemd, or None where it cannot be read
    (no unit, no systemctl). *show* is `systemctl show -p ExecStart --value`'s output, for tests."""
    if show is None:
        try:
            show = subprocess.run(["systemctl", "show", "-p", "ExecStart", "--value", APP_UNIT],
                                  capture_output=True, text=True,
                                  timeout=SYSTEMCTL_TIMEOUT_S).stdout
        except (OSError, subprocess.SubprocessError):
            return None
    m = re.search(r"\bpath=(\S+)", show or "")
    return m.group(1) if m else None


def interpreter_to_read(path, prefix=None):
    """The interpreter to re-run under, or None when the running one is it. An interpreter's
    prefix is the folder above its bin/: /usr for /usr/bin/python3, the venv's link for
    <link>/bin/python (through a link a venv reports the link: measured 2026-10-09)."""
    prefix = sys.prefix if prefix is None else prefix
    return None if os.path.dirname(os.path.dirname(path)) == prefix else path


def adopt(name, show=None, execve=os.execve, environ=None, argv=None):
    """Re-run the calling script under the app's interpreter when another one started it.

    *name* is the caller's `__name__`: a script loaded as a module (a test, the updater's copy of
    nmas-deploy) is never re-run. Exits 2, naming both, when a re-run still reports another
    prefix."""
    if name != "__main__":
        return None
    environ = os.environ if environ is None else environ
    argv = sys.argv if argv is None else argv
    path = app_interpreter(show)
    target = interpreter_to_read(path) if path else None
    if target is None:
        return None
    if environ.get(REEXEC):
        print(f"REFUSED: re-run under {APP_UNIT}'s interpreter {target}, which reports prefix "
              f"{sys.prefix}, not {os.path.dirname(os.path.dirname(target))}", file=sys.stderr)
        raise SystemExit(2)
    print(f"{APP_UNIT} runs {target}, and this is {sys.executable}: re-running under {target}",
          file=sys.stderr, flush=True)
    execve(target, [target, os.path.abspath(argv[0]), *argv[1:]], {**environ, REEXEC: "1"})
    return None


#: What a venv is built from, in order (section 8.3): its identity changes when either does.
VENV_INPUTS = ("requirements.lock", "requirements-test.txt")


def venv_id(checkout):
    """The identity of the venv *checkout*'s release needs: the first 12 hex of the sha256 of
    VENV_INPUTS' bytes, in order. Names its folder, /opt/mercury-venv-<id> (section 8.3); the
    host steps and, once 8.4 is built, the deploy all read it here."""
    digest = hashlib.sha256()
    for name in VENV_INPUTS:
        with open(os.path.join(checkout, name), "rb") as fh:
            digest.update(fh.read())
    return digest.hexdigest()[:12]


if __name__ == "__main__":
    # For the host steps (bash): `python3 -m modules.app_interpreter venv-id <checkout>`.
    if sys.argv[1:2] == ["venv-id"] and len(sys.argv) == 3:
        print(venv_id(sys.argv[2]))
    else:
        raise SystemExit("usage: python3 -m modules.app_interpreter venv-id <checkout>")
