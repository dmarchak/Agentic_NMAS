#!/usr/bin/env bash
# Board L's discovery range, ONCE (NSOT_STAGE7_PLAN 16; modules/dhcp_discovery.py): a device no
# reservation names, asking on the ZTP segment, is given a five-minute address with no boot file,
# router or DNS, so it can be seen and picked by a person. Two parts:
#   1. two client classes in Kea's main IPv4 file (root's, so this step installs them), each
#      CONFINED to the ZTP subnet's own clients (not reserved, not relayed, arrived on the ZTP
#      interface): Kea's classes are global and a class's lease time beats every subnet's
#      (measured on a throwaway Kea, 2026-10-11), so an unconfined class would cut every
#      unreserved client's lease in every subnet to five minutes;
#   2. two pools in the ZTP subnet (ciscopnp's, then the rest's), written to Mercury's subnet file
#      through board C's one write path (Kea's own check, reload, read back, recorded).
# Nothing else may move, and this step proves it: a snapshot of Kea's running configuration,
# every reservation and every lease, both families, before and after, and only the two classes
# and the two pools may differ. A fresh dated copy of Kea's configuration is taken first.
# Run on the NMAS host, as the operator's own user (sudo asked for the copy and the install):
#     bash <checkout>/scripts/host-steps/ztp-discovery-range.sh [RANGE]
# RANGE (a block of 32 addresses in the ZTP subnet) is optional: without it, the highest block
# that holds nothing, which the plan prints before anything is changed.
. "$(dirname "$0")/lib.sh"

RANGE=${1:-}
PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
TOOL="cd '$CHECKOUT' && '$PY' scripts/nmas-kea-discovery-range"
SNAP="cd '$CHECKOUT' && '$PY' scripts/nmas-kea-subnet-files"
KEA=/etc/kea
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COPY=/var/backups/kea/ztp-discovery-$STAMP
WORK=$(mktemp -d)
echo "== the dated copy goes to $COPY"

plan "run as the operator's own user, not root" \
     "Kea answers, IPv4" \
     "the dated copy reads back the same as the originals" \
     "the before snapshot is taken: configuration, reservations and leases, both families" \
     "the classes' candidate passes Kea's own check" \
     "the installed file is the tested candidate" \
     "Kea runs the two discovery classes" \
     "the pools are written through Mercury's write path: tested, reloaded, read back, recorded" \
     "Kea runs the discovery range: both classes and both pools" \
     "only the classes and the ZTP subnet's pools moved; every reservation and lease as before"

not_root
check "Kea answers, IPv4" eq 1 "$SNAP hash | grep -cE '^dhcp4 [0-9A-Fa-f]{64}$'"

step "a fresh dated copy of Kea's configuration (root's, mode 700)" \
    "sudo install -d -m 700 '$COPY' '$COPY/etc-kea' && \
     sudo cp -a '$KEA/kea-dhcp4.conf' '$COPY/etc-kea/' && sudo cp -a '$KEA/nmas' '$COPY/etc-kea/nmas'"
check "the dated copy reads back the same as the originals" rc0 0 \
    "sudo cmp '$KEA/kea-dhcp4.conf' '$COPY/etc-kea/kea-dhcp4.conf' && \
     sudo diff -r '$KEA/nmas' '$COPY/etc-kea/nmas'"
check "the before snapshot is taken: configuration, reservations and leases, both families" \
    rc0 0 "$SNAP snapshot '$WORK/before.json' && sudo cp '$WORK/before.json' '$COPY/before.json'"

step "what the step will do (the plan)" "$TOOL plan $RANGE"
check "the classes' candidate passes Kea's own check" rc0 0 "$TOOL classes"

ON_FAIL="sudo install -m 644 -o root -g root '$COPY/etc-kea/kea-dhcp4.conf' '$KEA/kea-dhcp4.conf' && \
         sudo cat '$COPY/etc-kea/nmas/subnets4.json' > '$KEA/nmas/subnets4.json' && $TOOL reload"
ON_FAIL_WHAT="Kea's IPv4 file and Mercury's IPv4 subnet file put back from the dated copy, and Kea reloaded"
step "install the tested candidate over Kea's IPv4 configuration" \
    "c='$KEA/nmas/.discovery-candidate-dhcp4.conf'; if [ -f \"\$c\" ]; then \
       sudo install -m 644 -o root -g root \"\$c\" '$KEA/kea-dhcp4.conf' && \
       cp \"\$c\" '$WORK/dhcp4.installed' && rm \"\$c\" && echo 'installed kea-dhcp4.conf'; \
     else echo 'kea-dhcp4.conf: nothing to change'; fi"
check "the installed file is the tested candidate" rc0 0 \
    "[ ! -f '$WORK/dhcp4.installed' ] || cmp '$WORK/dhcp4.installed' '$KEA/kea-dhcp4.conf'"
step "Kea reloads its IPv4 configuration" "$TOOL reload"
check "Kea runs the two discovery classes" has "the classes: done" "$TOOL plan $RANGE"
check "the pools are written through Mercury's write path: tested, reloaded, read back, recorded" \
    rc0 0 "$TOOL pools $RANGE"
check "Kea runs the discovery range: both classes and both pools" rc0 0 "$TOOL verify"
check "only the classes and the ZTP subnet's pools moved; every reservation and lease as before" \
    rc0 0 "$SNAP snapshot '$WORK/after.json' && sudo cp '$WORK/after.json' '$COPY/after.json' && \
     $TOOL expected '$WORK/before.json' '$WORK/after.json'"
echo "== the dated copy: $COPY (with before.json and after.json)"
summary
