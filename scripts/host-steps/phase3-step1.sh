#!/usr/bin/env bash
# Phase 3 step 1 (docs/NSOT_PHASE3_RETIRE_OXIDIZED.md section 5): stop Oxidized and keep its git
# store read-only until its bundle is in MinIO (P3-1). The operator's, on the NMAS host:
#     bash <checkout>/scripts/host-steps/phase3-step1.sh
. "$(dirname "$0")/lib.sh"

plan "run as the operator's own user, not root" \
     "the running release asks nothing of Oxidized (no oxidized-fetch hook)" \
     "exactly one git store under /opt/oxidized" \
     "the oxidized container is not running" \
     "its restart policy is no" \
     "the store has no writable file" \
     "the store's history is unchanged"

not_root
check "the running release asks nothing of Oxidized (no oxidized-fetch hook)" eq "0" \
    "grep -c 'oxidized-fetch' '$CHECKOUT/modules/nsot/archive.py'"
check "exactly one git store under /opt/oxidized" eq "1" \
    'ls -d /opt/oxidized/*.git | wc -l'
export STORE
STORE=$(ls -d /opt/oxidized/*.git)
COMMITS=$(git -C "$STORE" rev-list --all --count 2>/dev/null)
echo "   the store holds $COMMITS commits"

step "stop the container" 'docker stop oxidized'
step "keep it stopped across restarts" 'docker update --restart=no oxidized'
step "make the store read-only" 'sudo chmod -R a-w "$STORE"'

check "the oxidized container is not running" eq "0" \
    "docker ps --filter name='^oxidized\$' --format '{{.Names}}' | wc -l"
check "its restart policy is no" eq "no" \
    "docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' oxidized"
check "the store has no writable file" eq "0" \
    'sudo find "$STORE" -perm /222 | wc -l'
check "the store's history is unchanged" eq "$COMMITS" \
    'git -C "$STORE" rev-list --all --count'
summary
