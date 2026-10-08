#!/usr/bin/env bash
# Phase 4 step 1, host steps 4d and 4e (docs/NSOT_PHASE4_MINIO.md section 4): the minio package
# in the app's interpreter, and the lock regenerated from the host (requirements.lock's rule).
# Stops if the interpreter is not a virtualenv, if this user cannot write it, or if the dry run
# would change any package already installed. The operator's, on the NMAS host:
#     bash <checkout>/scripts/host-steps/minio-4d-4e.sh
# It writes /tmp/requirements.lock.new and changes nothing in the checkout: the session that
# asked for it reads that file and commits it.
. "$(dirname "$0")/lib.sh"

export SPEC='minio>=7.2,<8'
export WORK
WORK=$(mktemp -d)
export PY
PY=$(systemctl cat flask-app.service 2>/dev/null | sed -n 's/^ExecStart=\([^ ]*python[^ ]*\).*/\1/p' | head -1)
echo "   the app's interpreter: ${PY:-none found in flask-app.service}"

plan "run as the operator's own user, not root" \
     "flask-app.service names a Python interpreter" \
     "the interpreter is a virtualenv" \
     "this user can write the virtualenv" \
     "pip can do a dry run" \
     "the dry run installs minio" \
     "the dry run changes no package already installed" \
     "minio imports, at the version the dry run named" \
     "the client takes cert_check (TLS verification, C355)" \
     "the lock is generated (exit 0)" \
     "the new lock only adds what the dry run installed"

not_root
check "flask-app.service names a Python interpreter" eq "yes" '[ -n "$PY" ] && [ -x "$PY" ] && echo yes'
check "the interpreter is a virtualenv" eq "True" \
    '"$PY" -c "import sys; print(sys.prefix != sys.base_prefix)"'
check "this user can write the virtualenv" eq "yes" \
    '[ -w "$("$PY" -c "import sys; print(sys.prefix)")" ] && echo yes'
check "pip can do a dry run" ge 1 '"$PY" -m pip install --help | grep -c -- "--dry-run" || true'

step "dry run" '"$PY" -m pip install --dry-run "$SPEC" > "$WORK/dry.txt" 2>&1; cat "$WORK/dry.txt" | tail -n 3'
# "Would install a-1.0 b-2.0": each name-version, the name split at its last dash.
"$PY" - "$WORK/dry.txt" > "$WORK/would.txt" <<'PY'
import re, sys
line = next((l for l in open(sys.argv[1]) if l.startswith("Would install")), "")
for item in line.split()[2:]:
    name, _, version = item.rpartition("-")
    print(re.sub(r"[-_.]+", "-", name).lower(), version)
PY
"$PY" -m pip list --format=freeze 2>/dev/null \
    | sed -n 's/==.*//p' | tr 'A-Z_.' 'a-z--' | sort -u > "$WORK/installed.txt"
echo "   the dry run would install: $(awk '{print $1"-"$2}' "$WORK/would.txt" | tr '\n' ' ')"
check "the dry run installs minio" re "^minio " 'cat "$WORK/would.txt"'
check "the dry run changes no package already installed" eq "" \
    'awk "{print \$1}" "$WORK/would.txt" | sort -u | comm -12 - "$WORK/installed.txt"'

step "install" '"$PY" -m pip install "$SPEC"'
check "minio imports, at the version the dry run named" eq "$(awk '$1=="minio"{print $2}' "$WORK/would.txt")" \
    '"$PY" -c "import importlib.metadata as m; print(m.version(\"minio\"))"'
check "the client takes cert_check (TLS verification, C355)" eq "True" \
    '"$PY" -c "import inspect; from minio import Minio; print(\"cert_check\" in inspect.signature(Minio).parameters)"'

step "generate the lock from this host" \
    'cd "$CHECKOUT" && "$PY" scripts/nmas-lock-from-host > /tmp/requirements.lock.new'
check "the lock is generated (exit 0)" eq "yes" '[ -s /tmp/requirements.lock.new ] && echo yes'
check "the new lock only adds what the dry run installed" eq "" \
    'diff <(grep -v "^#" "$CHECKOUT/requirements.lock") <(grep -v "^#" /tmp/requirements.lock.new) | sed -n "s/^[<>] //p" | sed "s/==.*//" | tr "A-Z_." "a-z--" | sort -u | comm -23 - <(awk "{print \$1}" "$WORK/would.txt" | sort -u)'
echo "   /tmp/requirements.lock.new is ready to be read and committed."
summary
