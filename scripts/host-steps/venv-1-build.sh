#!/usr/bin/env bash
# DRAFT, not approved to run (the operator, 2026-10-09: planned right after receipts; "no change
# until I approve"). Phase 4 section 8, step 1 of 3: build Mercury's virtualenv from the lock and
# prove it imports what the app and its tools import today. It changes nothing that runs: every
# unit keeps /usr/bin/python3 until step 2. The operator's, on the app host, from the deployed
# checkout:
#     bash <checkout>/scripts/host-steps/venv-1-build.sh
#
# Why (C606): the app's interpreter searches the user's pip folder, then a root pip folder, then
# apt's, so three installers decide what it imports; requirements.lock already names exactly what
# it runs. The venv holds the lock and nothing else, outside the checkout (never written into the
# live checkout), root-owned and readable.
. "$(dirname "$0")/lib.sh"

VENV=/opt/mercury-venv
LOCK="$CHECKOUT/requirements.lock"
# What venv-2-switch.sh installs. While any of them exists something runs on the venv, and
# `venv --clear` would remove it under the running app and units (C607).
IN_USE="/etc/systemd/system/flask-app.service.d/mercury-venv.conf /etc/systemd/system/nmas-.service.d/mercury-venv.conf"
# Every Python program that runs Mercury's code on this host (Phase 4 section 8's inventory):
# app.py, every script in the checkout with a python shebang (the units run some of them, a
# person the rest), and the updater's root-owned copies.
PROGRAMS=$(cd "$CHECKOUT" && { echo app.py; git ls-files scripts | while read -r f; do
    head -1 "$f" 2>/dev/null | grep -q '^#!.*python' && echo "$f"; done; } | tr '\n' ' ')
for f in /usr/local/sbin/nmas-update /usr/local/lib/nmas-update/nmas-deploy; do
    [ -f "$f" ] && PROGRAMS="$PROGRAMS $f"
done
export VENV LOCK CHECKOUT IN_USE PROGRAMS

plan "run as the operator's own user, not root" \
     "the venv is not in use yet (nothing venv-2-switch.sh installs exists)" \
     "the deployed checkout holds the lock" \
     "the Python programs on this host are listed" \
     "the system interpreter is Python 3.12.3" \
     "the venv's interpreter is Python 3.12.3" \
     "the venv takes nothing from outside it (no system or user site)" \
     "every pin in the lock is installed in the venv at its version" \
     "the venv imports every pinned distribution at the version the app imports today" \
     "psycopg loads its libpq in the venv" \
     "every Python program on this host imports in the venv what it imports today"

not_root
check "the venv is not in use yet (nothing venv-2-switch.sh installs exists)" eq "" \
    'for f in $IN_USE; do [ -e "$f" ] && echo "$f"; done; true'
check "the deployed checkout holds the lock" ge 10 'grep -c "==" "$LOCK"'
# Measured 2026-10-09 in the repository: app.py and 79 scripts with a python shebang.
check "the Python programs on this host are listed" ge 50 'echo $PROGRAMS | wc -w'
check "the system interpreter is Python 3.12.3" eq "3.12.3" \
    '/usr/bin/python3 -c "import platform; print(platform.python_version())"'

step "make the venv (root-owned, readable)" 'sudo /usr/bin/python3 -m venv --clear "$VENV"'
step "install exactly the lock, --no-deps (CI's command)" \
    'sudo "$VENV/bin/python" -m pip install --quiet --no-deps -r "$LOCK"'

check "the venv's interpreter is Python 3.12.3" eq "3.12.3" \
    '"$VENV/bin/python" -c "import platform; print(platform.python_version())"'
check "the venv takes nothing from outside it (no system or user site)" eq "False False" \
    '"$VENV/bin/python" -c "import site, sys; print(site.ENABLE_USER_SITE, any(p.startswith(\"/usr/lib/python3/dist-packages\") or \"/.local/\" in p for p in sys.path))"'
check "every pin in the lock is installed in the venv at its version" eq "" \
    '"$VENV/bin/python" -m pip freeze --all 2>/dev/null | tr "[:upper:]_" "[:lower:]-" | sort > /tmp/.venv-freeze.$$; grep "==" "$LOCK" | tr "[:upper:]_" "[:lower:]-" | sort | comm -23 - /tmp/.venv-freeze.$$; rm -f /tmp/.venv-freeze.$$'
# What each interpreter imports, for every distribution the lock pins: the app's today (the
# system interpreter AS the app's user, user site and all) against the venv's. Equal, or named.
# cffi: Debian's python3-cffi-backend ships the module `_cffi_backend` with no cffi metadata
# (measured read only on the host, 2026-10-09: the lock's 68 other pins equal what the app
# imports, cffi's metadata absent), so what both interpreters LOAD is compared: its version.
COMPARE='import importlib.metadata as md, re, sys
for line in open(sys.argv[1]):
    m = re.match(r"^([A-Za-z0-9_.-]+)==", line)
    if not m:
        continue
    name = m.group(1).lower().replace("_", "-")
    if name == "cffi":
        import _cffi_backend
        print(name, "backend", _cffi_backend.__version__)
        continue
    try: print(name, md.version(m.group(1)))
    except md.PackageNotFoundError: print(name, "ABSENT")'
# Every module each program imports, at any depth of its code (an import inside a function
# included), imported for real; prints "<program>: <module> (<error>)" for each that fails.
# Some fail under both interpreters by design (a laptop-only tool's test fixtures, a guarded
# optional import), so the venv is held to TODAY's interpreter: it may fail nothing today's
# does not.
IMPORTS='import ast, importlib, sys
bad = set()
for path in sys.argv[1:]:
    for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module]
        else:
            continue
        for name in names:
            try:
                importlib.import_module(name)
            except BaseException as exc:
                bad.add(f"{path}: {name} ({type(exc).__name__})")
print("\n".join(sorted(bad)))'
export COMPARE IMPORTS
APP_USER=$(systemctl show -p User --value flask-app.service)
export APP_USER
check "the venv imports every pinned distribution at the version the app imports today" eq "" \
    'diff <(sudo -u "$APP_USER" /usr/bin/python3 -c "$COMPARE" "$LOCK") <("$VENV/bin/python" -c "$COMPARE" "$LOCK")'
check "psycopg loads its libpq in the venv" re '^3\.' \
    '"$VENV/bin/python" -c "import psycopg; print(psycopg.__version__)"'
# From the checkout, as the app's user, writing no bytecode into the live checkout.
check "every Python program on this host imports in the venv what it imports today" eq "" \
    'cd "$CHECKOUT" && comm -13 \
        <(sudo -u "$APP_USER" env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -c "$IMPORTS" $PROGRAMS) \
        <(env PYTHONDONTWRITEBYTECODE=1 "$VENV/bin/python" -c "$IMPORTS" $PROGRAMS)'
echo "Next, when the operator approves: venv-2-switch.sh points flask-app and every nmas- unit"
echo "at $VENV."
summary
