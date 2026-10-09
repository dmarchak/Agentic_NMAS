#!/usr/bin/env bash
# DRAFT, not approved to run (Phase 4 section 8.3, signed off by the operator 2026-10-09; the
# host steps are the operator's to run). Build the venv a release needs BESIDE whatever runs,
# prove it, and mark it proved. It changes nothing that runs. The operator's, on the app host,
# from the checkout of the release to be deployed:
#     bash <checkout>/scripts/host-steps/venv-1-build.sh
#
# /opt/mercury-venv-<id>, <id> the release's venv identity (modules.app_interpreter.venv_id: the
# lock and requirements-test.txt). Never rebuilt in place: it refuses when <id> is what the link
# /opt/mercury-venv or /opt/mercury-venv.previous points at. A proved build of <id> is reported
# and left; an unproved one (an earlier build that failed) is removed and built again. Nothing
# else is removed here: the swap removes venvs older than the previous one.
#
# Why (C606, C607): the app's interpreter searched the user's pip folder, a root pip folder and
# apt's. The venv holds the lock's files and nothing else, root-owned, outside the checkout.
. "$(dirname "$0")/lib.sh"

LINK=/opt/mercury-venv
PREVIOUS=/opt/mercury-venv.previous
LOCK="$CHECKOUT/requirements.lock"
TESTS="$CHECKOUT/requirements-test.txt"
OVERRIDES="$CHECKOUT/requirements-overrides.txt"
ID=$(cd "$CHECKOUT" && /usr/bin/python3 -m modules.app_interpreter venv-id "$CHECKOUT" 2>&1)
DIR="/opt/mercury-venv-$ID"
# The interpreter the app runs now (the system's before the first switch, the link after it),
# and the user it runs as: what this build is compared with.
CURRENT=$(systemctl show -p ExecStart --value flask-app.service | sed -n 's/.*path=\([^ ;]*\).*/\1/p')
APP_USER=$(systemctl show -p User --value flask-app.service)
# Every Python program that runs Mercury's code on this host (section 8's inventory): app.py,
# every script in the checkout with a python shebang, and the updater's root-owned copies.
PROGRAMS=$(cd "$CHECKOUT" && { echo app.py; git ls-files scripts | while read -r f; do
    head -1 "$f" 2>/dev/null | grep -q '^#!.*python' && echo "$f"; done; } | tr '\n' ' ')
for f in /usr/local/sbin/nmas-update /usr/local/lib/nmas-update/nmas-deploy; do
    [ -f "$f" ] && PROGRAMS="$PROGRAMS $f"
done
export LINK PREVIOUS LOCK TESTS OVERRIDES ID DIR CURRENT APP_USER PROGRAMS CHECKOUT

plan "run as the operator's own user, not root" \
     "the release's venv identity is read" \
     "the folder is neither the running venv nor the previous one (never rebuilt in place)" \
     "the app's current interpreter and user are read" \
     "the Python programs on this host are listed" \
     "the system interpreter is Python 3.12.3" \
     "the venv's interpreter is Python 3.12.3" \
     "the venv takes nothing from outside it (no system or user site)" \
     "every pin in the lock and requirements-test.txt is installed at its version" \
     "pip check names exactly the overrides' complaints" \
     "psycopg loads its libpq in the venv" \
     "every Python program on this host imports in the venv what it imports today" \
     "the first build holds every pinned distribution at the version the app imports today" \
     "the build is marked proved"

not_root
check "the release's venv identity is read" re '^[0-9a-f]{12}$' 'echo "$ID"'
check "the folder is neither the running venv nor the previous one (never rebuilt in place)" eq "" \
    'for l in $LINK $PREVIOUS; do [ "$(readlink -f "$l" 2>/dev/null)" = "$DIR" ] && echo "$l points at $DIR"; done; true'
if [ -f "$DIR/.mercury-proved" ]; then
    echo "== $DIR is already built and proved:"
    sed 's/^/   /' "$DIR/.mercury-proved"
    echo "   Nothing to do. Next: venv-2-switch.sh (the first switch) or venv-swap.sh."
    summary
    exit 0
fi
check "the app's current interpreter and user are read" re '^/.+ .+$' 'echo "$CURRENT $APP_USER"'
# Measured 2026-10-09 in the repository: app.py and 79 scripts with a python shebang.
check "the Python programs on this host are listed" ge 50 'echo $PROGRAMS | wc -w'
check "the system interpreter is Python 3.12.3" eq "3.12.3" \
    '/usr/bin/python3 -c "import platform; print(platform.python_version())"'

if [ -e "$DIR" ]; then
    # An unproved build of this identity, which nothing points at (checked above).
    step "remove the unproved earlier build $DIR" \
        '[[ "$DIR" =~ ^/opt/mercury-venv-[0-9a-f]{12}$ ]] && sudo rm -rf -- "$DIR"'
fi
step "make the venv beside what runs (root-owned, readable)" 'sudo /usr/bin/python3 -m venv "$DIR"'
step "install exactly the lock's files (--require-hashes --no-deps, as CI)" \
    'sudo "$DIR/bin/python" -m pip install --quiet --disable-pip-version-check --require-hashes --no-deps -r "$LOCK"'
step "install the test tools beside it (--no-deps, as CI)" \
    'sudo "$DIR/bin/python" -m pip install --quiet --disable-pip-version-check --no-deps -r "$TESTS"'

check "the venv's interpreter is Python 3.12.3" eq "3.12.3" \
    '"$DIR/bin/python" -c "import platform; print(platform.python_version())"'
check "the venv takes nothing from outside it (no system or user site)" eq "False False" \
    '"$DIR/bin/python" -c "import site, sys; print(site.ENABLE_USER_SITE, any(p.startswith(\"/usr/lib/python3/dist-packages\") or \"/.local/\" in p for p in sys.path))"'
# name==version, normalised, from the lock's pin lines (each ends " \", hashes below) and the
# test file; every one must be in the venv's freeze.
check "every pin in the lock and requirements-test.txt is installed at its version" eq "" \
    'norm() { sed -n "s/^\([A-Za-z0-9_.-]*==[^ ]*\).*/\1/p" \
         | awk -F== "{n = tolower(\$1); gsub(/[_.]/, \"-\", n); print n \"==\" \$2}" | LC_ALL=C sort; }; \
     LC_ALL=C comm -23 <(cat "$LOCK" "$TESTS" | norm) <("$DIR/bin/python" -m pip freeze --all 2>/dev/null | norm)'
# Each override replaces what a dependency declares, so causes one complaint; anything else
# unsatisfied is a finding (the same rule CI's tests/test_requirements_lock.py holds).
PIPCHECK='import re, subprocess, sys
from packaging.requirements import Requirement
norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()
over = {norm(Requirement(l.split("#")[0].strip()).name) for l in open(sys.argv[1])
        if l.split("#")[0].strip()}
out = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True).stdout
lines = [l for l in out.splitlines() if l.strip()]
named = lambda l: {norm(w) for w in re.findall(r"[A-Za-z0-9_.-]+", l)} & over
for l in lines:
    if not named(l): print("unexplained:", l)
for n in sorted(over - set().union(*map(named, lines))): print("override with no complaint:", n)'
export PIPCHECK
check "pip check names exactly the overrides' complaints" eq "" \
    '"$DIR/bin/python" -c "$PIPCHECK" "$OVERRIDES"'
check "psycopg loads its libpq in the venv" re '^3\.' \
    '"$DIR/bin/python" -c "import psycopg; print(psycopg.__version__)"'
# Every module each program imports, at any depth of its code, imported for real; prints
# "<program>: <module> (<error>)" for each that fails. Some fail under both interpreters by
# design (a laptop tool's test fixtures, a guarded optional import), so the new venv may fail
# nothing the app's CURRENT interpreter does not. From the checkout, as the app's user, writing
# no bytecode into the live checkout.
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
export IMPORTS
check "every Python program on this host imports in the venv what it imports today" eq "" \
    'cd "$CHECKOUT" && comm -13 \
        <(sudo -u "$APP_USER" env PYTHONDONTWRITEBYTECODE=1 "$CURRENT" -c "$IMPORTS" $PROGRAMS) \
        <(env PYTHONDONTWRITEBYTECODE=1 "$DIR/bin/python" -c "$IMPORTS" $PROGRAMS)'
# The FIRST venv changes where the libraries live, not which versions (the operator,
# 2026-10-09): before the first switch (no link) every pinned distribution must be what the app
# imports today. A later build follows its lock, so this holds only the first.
# cffi: Debian's python3-cffi-backend ships `_cffi_backend` with no cffi metadata (measured
# 2026-10-09), so what both interpreters LOAD is compared: its version.
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
export COMPARE
check "the first build holds every pinned distribution at the version the app imports today" eq "" \
    'if [ -L "$LINK" ]; then exit 0; fi; \
     diff <(sudo -u "$APP_USER" "$CURRENT" -c "$COMPARE" "$LOCK") <("$DIR/bin/python" -c "$COMPARE" "$LOCK")'
step "mark it proved (written last, only now)" \
    'printf "id %s\ncommit %s\nbuilt %s\n" "$ID" "$(git -C "$CHECKOUT" rev-parse HEAD)" "$(date -u +%FT%TZ)" \
     | sudo tee "$DIR/.mercury-proved" > /dev/null'
check "the build is marked proved" has "id $ID" 'cat "$DIR/.mercury-proved"'
if [ -L "$LINK" ]; then
    echo "Next: venv-swap.sh from this checkout swaps the link to $DIR."
else
    echo "Next, when the operator approves: venv-2-switch.sh points flask-app and every nmas- unit"
    echo "at $LINK, a link to $DIR."
fi
summary
