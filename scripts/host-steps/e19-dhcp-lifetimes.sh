#!/usr/bin/env bash
# E19's lease lifetimes, ONCE (docs/DHCP_LIFETIMES_PROPOSAL.md; modules/dhcp_lifetimes.py; the
# operator's decisions 2026-10-13: "pool 4 h, reserved 7 days ..., management 7 days; T1/T2 at
# 50%/80%. Build it."). Three parts:
#   1. Kea's main files (root's, so this step installs them), both families: the global lifetime
#      becomes the pool's (4 h; IPv6 preferred 2 h), the global fixed renew and rebind timers go
#      and Kea computes them at 50% and 80% of each lease's own lifetime, and `client-classes`
#      moves into Mercury's own file (nmas/classes4.json, classes6.json) through an include, the
#      discovery classes carried over unchanged and the class `mercury-reserved` added
#      (`member('KNOWN')`: every reserved client, 7 days; IPv6 preferred 3.5 days);
#   2. the management (ZTP) subnet is left as it is: it is onboarding's (Subnets › Edit refuses
#      it), and every client there already takes a class's lifetime, a reserved device
#      `mercury-reserved`'s 7 days and an unreserved one discovery's 300 s, since its only pools
#      are the discovery classes'; verify checks that no pool there serves any client;
#   3. proof that nothing else moved: a snapshot of Kea's running configuration, every
#      reservation and every lease, both families, before and after.
# A fresh dated copy of Kea's configuration is taken first; a failure puts it back and reloads.
# Run on the NMAS host, as the operator's own user (sudo asked for the copy and the install):
#     bash <checkout>/scripts/host-steps/e19-dhcp-lifetimes.sh
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
TOOL="cd '$CHECKOUT' && '$PY' scripts/nmas-kea-lifetimes"
SNAP="cd '$CHECKOUT' && '$PY' scripts/nmas-kea-subnet-files"
KEA=/etc/kea
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COPY=/var/backups/kea/e19-lifetimes-$STAMP
WORK=$(mktemp -d)
echo "== the dated copy goes to $COPY"

plan "run as the operator's own user, not root" \
     "Kea answers, both families" \
     "the dated copy reads back the same as the originals" \
     "the before snapshot is taken: configuration, reservations and leases, both families" \
     "both candidates pass Kea's own check" \
     "the installed files are the tested candidates" \
     "Kea runs the lifetimes, both families" \
     "every client of the management (ZTP) subnet takes a class's lifetime" \
     "only the lifetimes, timers and the reserved class moved; every reservation and lease as before"

not_root
check "Kea answers, both families" eq 2 "$SNAP hash | grep -cE '^dhcp[46] [0-9A-Fa-f]{64}$'"

step "a fresh dated copy of Kea's configuration (root's, mode 700)" \
    "sudo install -d -m 700 '$COPY' '$COPY/etc-kea' && \
     sudo cp -a '$KEA/kea-dhcp4.conf' '$KEA/kea-dhcp6.conf' '$COPY/etc-kea/' && \
     sudo cp -a '$KEA/nmas' '$COPY/etc-kea/nmas'"
check "the dated copy reads back the same as the originals" rc0 0 \
    "sudo cmp '$KEA/kea-dhcp4.conf' '$COPY/etc-kea/kea-dhcp4.conf' && \
     sudo cmp '$KEA/kea-dhcp6.conf' '$COPY/etc-kea/kea-dhcp6.conf' && \
     sudo diff -r '$KEA/nmas' '$COPY/etc-kea/nmas'"
check "the before snapshot is taken: configuration, reservations and leases, both families" \
    rc0 0 "$SNAP snapshot '$WORK/before.json' && sudo cp '$WORK/before.json' '$COPY/before.json'"

step "what the step will do (the plan)" "$TOOL plan"
check "both candidates pass Kea's own check" rc0 0 "$TOOL candidates"

ON_FAIL="sudo install -m 644 -o root -g root '$COPY/etc-kea/kea-dhcp4.conf' '$KEA/kea-dhcp4.conf' && \
         sudo install -m 644 -o root -g root '$COPY/etc-kea/kea-dhcp6.conf' '$KEA/kea-dhcp6.conf' && $TOOL reload"
ON_FAIL_WHAT="Kea's two main files put back from the dated copy, and Kea reloaded"
for svc in dhcp4 dhcp6; do
    step "install the tested candidate over Kea's $svc configuration" \
        "c='$KEA/nmas/.lifetimes-candidate-$svc.conf'; if [ -f \"\$c\" ]; then \
           sudo install -m 644 -o root -g root \"\$c\" '$KEA/kea-$svc.conf' && \
           cp \"\$c\" '$WORK/$svc.installed' && rm \"\$c\" && echo 'installed kea-$svc.conf'; \
         else echo 'kea-$svc.conf: nothing to change'; fi"
done
check "the installed files are the tested candidates" rc0 0 \
    "{ [ ! -f '$WORK/dhcp4.installed' ] || cmp '$WORK/dhcp4.installed' '$KEA/kea-dhcp4.conf'; } && \
     { [ ! -f '$WORK/dhcp6.installed' ] || cmp '$WORK/dhcp6.installed' '$KEA/kea-dhcp6.conf'; }"
step "Kea reloads both families" "$TOOL reload"
check "Kea runs the lifetimes, both families" eq 2 \
    "$TOOL verify | grep -cE '^IPv[46]: Kea runs the lifetimes: on$' || true"
check "every client of the management (ZTP) subnet takes a class's lifetime" rc0 0 \
    "$TOOL verify"
check "only the lifetimes, timers and the reserved class moved; every reservation and lease as before" \
    rc0 0 "$SNAP snapshot '$WORK/after.json' && sudo cp '$WORK/after.json' '$COPY/after.json' && \
     $TOOL expected '$WORK/before.json' '$WORK/after.json'"
echo "== the dated copy: $COPY (with before.json and after.json)"
rm -rf "$WORK"
summary
