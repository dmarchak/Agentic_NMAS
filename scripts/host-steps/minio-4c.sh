#!/usr/bin/env bash
# Phase 4 step 1, host step 4c (docs/NSOT_PHASE4_MINIO.md section 4): Mercury's MinIO user,
# `mercury`, holding mercury-rw, and the proof that its key can write and read its bucket,
# cannot delete (M-2) and cannot reach another bucket. The operator's, on the NMAS host, with
# the mc alias `lab`, after minio-4a-4b.sh:
#     bash <checkout>/scripts/host-steps/minio-4c.sh
#
# The secret is PROMPTED for (input hidden), never printed and never an argument: it reaches mc
# on its standard input (`mc admin user add lab` reads the keys there) and, for the checks, in
# an environment variable (MC_HOST_<alias>), never on a command line. Keep it for Settings.
. "$(dirname "$0")/lib.sh"

plan "run as the operator's own user, not root" \
     "the mc alias lab answers" \
     "mercury-rw exists (minio-4a-4b.sh ran)" \
     "the secret is letters, digits and . _ ~ - only, 20 characters or more" \
     "the user mercury exists and is enabled" \
     "it holds mercury-rw" \
     "its key writes the bucket" \
     "its key reads back what it wrote" \
     "its key cannot delete" \
     "its key cannot reach another bucket"

not_root
check "the mc alias lab answers" rc0 "" 'mc admin info lab >/dev/null'
check "mercury-rw exists (minio-4a-4b.sh ran)" has "mercury" 'mc admin policy info lab mercury-rw'

echo "Mercury's MinIO secret. Generate one in another terminal, for example:"
echo "    openssl rand -base64 30 | tr -d '/+='"
read -r -s -p "Secret for the user mercury (hidden): " SECRET; echo
read -r -s -p "The same again: " AGAIN; echo
if [ "$SECRET" != "$AGAIN" ]; then
    echo "The two entries differ; nothing was changed."
    _stop "the secret is letters, digits and . _ ~ - only, 20 characters or more"
fi
unset AGAIN
REDACT=$SECRET
export SECRET
check "the secret is letters, digits and . _ ~ - only, 20 characters or more" eq "ok" \
    '[[ "$SECRET" =~ ^[A-Za-z0-9._~-]{20,}$ ]] && echo ok || echo "not ok (length ${#SECRET})"'

if mc admin user list lab | grep -qw mercury; then
    echo "== the user mercury exists already: not re-added (that would change its secret);"
    echo "   the checks below prove the secret you entered is its secret."
else
    echo "== STEP: add the user mercury (keys on mc's standard input)"
    if ! printf '%s\n%s\n' mercury "$SECRET" | mc admin user add lab >/dev/null 2>&1; then
        echo "mc did not take the keys on its standard input. Run  mc admin user add lab  and"
        echo "answer its prompts (access key: mercury), then run this script again: it will find"
        echo "the user and go on to the checks."
        _stop "the user mercury exists and is enabled"
    fi
fi
step "attach mercury-rw" \
    'mc admin user info lab mercury | grep -q "mercury-rw" || mc admin policy attach lab mercury-rw --user mercury'

check "the user mercury exists and is enabled" has "enabled" 'mc admin user info lab mercury'
check "it holds mercury-rw" has "mercury-rw" 'mc admin user info lab mercury'

# The checks speak as mercury, through an alias held only in this process's environment.
LAB_URL=$(mc alias list lab --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["URL"])')
export MC_HOST_mercurycheck
MC_HOST_mercurycheck=$(LAB_URL="$LAB_URL" python3 -c '
import os, urllib.parse
u = urllib.parse.urlsplit(os.environ["LAB_URL"])
print(u.scheme + "://mercury:" + os.environ["SECRET"] + "@" + u.netloc)')
check "its key writes the bucket" rc0 "" \
    'echo "Mercury host step 4c" | mc pipe mercurycheck/mercury/_probe/mercury-connection-test'
check "its key reads back what it wrote" eq "Mercury host step 4c" \
    'mc cat mercurycheck/mercury/_probe/mercury-connection-test'
check "its key cannot delete" has "Access Denied" \
    'mc rm mercurycheck/mercury/_probe/mercury-connection-test 2>&1 || true'
check "its key cannot reach another bucket" has "Access Denied" \
    'mc ls mercurycheck/raw-telemetry 2>&1 || true'
unset MC_HOST_mercurycheck SECRET
summary
