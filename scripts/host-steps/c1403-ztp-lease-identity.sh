#!/usr/bin/env bash
# C1403 part 2, ONCE (modules/dhcp_lease_identity.py; the operator's design, 2026-10-19): every
# ZTP subnet Kea runs says "match-client-id": false, so a lease there is matched to its client
# by MAC, never by client-id. Measured on this host's Kea 2.4.1 (a throwaway copy on loopback,
# tests/fixtures/kea/c1403_match_client_id_probe.txt): with it true, a reserved device back with
# the same MAC and a new client-id is never answered (ALLOC_ENGINE_V4_DISCOVER_ADDRESS_CONFLICT,
# 0d's run 2); with it false it is offered and acknowledged its reserved address.
# A subnet Mercury adds for ZTP behind a relay is written with it from now on; the directly
# attached ZTP subnet is onboarding's (Subnets › Edit refuses it), so this step writes it, and
# any relayed one written before, through board C's one write path (Kea's own check on a
# candidate, write to Mercury's subnet file, config-reload, read back, recorded in
# dhcp/subnets.yml). Kea's own files are not touched. Nothing else may move, and this step
# proves it: a snapshot of Kea's running configuration, every reservation and every lease, both
# families, before and after, and only match-client-id on the ZTP subnets may differ. A fresh
# dated copy of Mercury's subnet files is taken first.
# Run on the NMAS host, as the operator's own user (sudo asked for the copy):
#     bash <checkout>/scripts/host-steps/c1403-ztp-lease-identity.sh
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
TOOL="cd '$CHECKOUT' && '$PY' scripts/nmas-kea-lease-identity"
SNAP="cd '$CHECKOUT' && '$PY' scripts/nmas-kea-subnet-files"
KEA=/etc/kea
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COPY=/var/backups/kea/c1403-lease-identity-$STAMP
WORK=$(mktemp -d)
echo "== the dated copy goes to $COPY"

plan "run as the operator's own user, not root" \
     "Kea answers, IPv4" \
     "the dated copy reads back the same as the originals" \
     "the before snapshot is taken: configuration, reservations and leases, both families" \
     "each ZTP subnet is written through Mercury's write path: tested, reloaded, read back, recorded" \
     "Kea runs match-client-id false on every ZTP subnet" \
     "only match-client-id moved, on the ZTP subnets; every reservation and lease as before"

not_root
check "Kea answers, IPv4" eq 1 "$SNAP hash | grep -cE '^dhcp4 [0-9A-Fa-f]{64}$'"

step "a fresh dated copy of Mercury's subnet files (root's, mode 700)" \
    "sudo install -d -m 700 '$COPY' && sudo cp -a '$KEA/nmas' '$COPY/nmas'"
check "the dated copy reads back the same as the originals" rc0 0 \
    "sudo diff -r '$KEA/nmas' '$COPY/nmas'"
check "the before snapshot is taken: configuration, reservations and leases, both families" \
    rc0 0 "$SNAP snapshot '$WORK/before.json' && sudo cp '$WORK/before.json' '$COPY/before.json'"

step "what the step will do (the plan)" "$TOOL plan"
check "each ZTP subnet is written through Mercury's write path: tested, reloaded, read back, recorded" \
    rc0 0 "$TOOL apply"
check "Kea runs match-client-id false on every ZTP subnet" rc0 0 "$TOOL verify"
check "only match-client-id moved, on the ZTP subnets; every reservation and lease as before" \
    rc0 0 "$SNAP snapshot '$WORK/after.json' && sudo cp '$WORK/after.json' '$COPY/after.json' && \
     $TOOL expected '$WORK/before.json' '$WORK/after.json'"
echo "== the dated copy: $COPY (with before.json and after.json)"
summary
