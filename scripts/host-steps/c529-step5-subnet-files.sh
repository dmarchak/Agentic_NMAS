#!/usr/bin/env bash
# C529 step 5's host side, ONCE (the operator's decision, 2026-10-06: one careful host step, no
# per-subnet move and no new root helper): Kea's hand-written subnets move into Mercury's own
# files, `/etc/kea/nmas/subnets4.json` and `subnets6.json`, verbatim (each subnet's reservation
# include kept), and Kea's main files include them. Afterwards Mercury owns every subnet through
# its files and `config-reload` (board C), the rights it already uses for reservations and ZTP.
#
# Nothing a client sees changes, and this step proves it: a snapshot of Kea's running
# configuration, every reservation and every lease, both families, is taken before anything is
# changed and again after the reload, and the two must be EQUAL (and Kea's own configuration
# hash unchanged); otherwise the step undoes itself (Kea's files put back, reloaded) and says
# what moved.
#
# FIRST a fresh dated copy of Kea's configuration and lease files (the operator's condition,
# 2026-10-11), read back against the originals before anything is changed; its path is printed
# and goes in docs/END_OF_SESSION.md. Kea's main configuration files are root's: the app writes
# the candidates (`scripts/nmas-kea-subnet-files candidates`, each tested by Kea's own `-t`), and
# this step installs them by name.
# Run on the NMAS host, as the operator's own user (sudo asked for the copy and the install):
#     bash <checkout>/scripts/host-steps/c529-step5-subnet-files.sh
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
TOOL="cd '$CHECKOUT' && '$PY' scripts/nmas-kea-subnet-files"
KEA=/etc/kea
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COPY=/var/backups/kea/c529-step5-$STAMP
WORK=$(mktemp -d)
echo "== the dated copy goes to $COPY"

plan "run as the operator's own user, not root" \
     "Kea answers, both families" \
     "the dated copy reads back the same as the originals" \
     "the before snapshot is taken: configuration, reservations and leases, both families" \
     "the candidates pass Kea's own check" \
     "the installed files are the tested candidates" \
     "every subnet comes from Mercury's file, both families" \
     "Kea's configuration hash is unchanged, both families" \
     "Kea's configuration, every reservation and every lease are the same after"

not_root
# Kea's hash is upper-case hex (measured on the host, 2026-10-11): both families' lines counted.
check "Kea answers, both families" eq 2 \
    "$TOOL hash | tee '$WORK/hash-before' | grep -cE '^dhcp[46] [0-9A-Fa-f]{64}$'"

step "a fresh dated copy of Kea's configuration and lease files (root's, mode 700)" \
    "sudo install -d -m 700 '$COPY' '$COPY/etc-kea' '$COPY/var-lib-kea' && \
     sudo cp -a '$KEA/kea-dhcp4.conf' '$KEA/kea-dhcp6.conf' '$KEA/kea-ctrl-agent.conf' '$COPY/etc-kea/' && \
     sudo cp -a '$KEA/nmas' '$COPY/etc-kea/nmas' && \
     sudo cp -a /var/lib/kea/. '$COPY/var-lib-kea/'"
check "the dated copy reads back the same as the originals" rc0 0 \
    "sudo cmp '$KEA/kea-dhcp4.conf' '$COPY/etc-kea/kea-dhcp4.conf' && \
     sudo cmp '$KEA/kea-dhcp6.conf' '$COPY/etc-kea/kea-dhcp6.conf' && \
     sudo cmp '$KEA/kea-ctrl-agent.conf' '$COPY/etc-kea/kea-ctrl-agent.conf' && \
     sudo diff -r '$KEA/nmas' '$COPY/etc-kea/nmas' && sudo diff -r /var/lib/kea '$COPY/var-lib-kea'"

check "the before snapshot is taken: configuration, reservations and leases, both families" \
    rc0 0 "$TOOL snapshot '$WORK/before.json' && sudo cp '$WORK/before.json' '$COPY/before.json'"

step "what the step will do (the plan)" "$TOOL plan"
check "the candidates pass Kea's own check" rc0 0 "$TOOL candidates"

# Installed by name, each only if its candidate exists (a family already moved has none).
ON_FAIL="sudo install -m 644 -o root -g root '$COPY/etc-kea/kea-dhcp4.conf' '$KEA/kea-dhcp4.conf' && \
         sudo install -m 644 -o root -g root '$COPY/etc-kea/kea-dhcp6.conf' '$KEA/kea-dhcp6.conf' && \
         $TOOL reload && $TOOL snapshot '$WORK/undone.json' && \
         $TOOL compare '$WORK/before.json' '$WORK/undone.json'"
ON_FAIL_WHAT="Kea's two configuration files put back from the dated copy, Kea reloaded, and the result compared with the before snapshot"
step "install the tested candidates over Kea's configuration" \
    "for svc in dhcp4 dhcp6; do c='$KEA/nmas/.c529-candidate-'\$svc'.conf'; \
       if [ -f \"\$c\" ]; then sudo install -m 644 -o root -g root \"\$c\" '$KEA/kea-'\$svc'.conf' \
       && cp \"\$c\" '$WORK/'\$svc'.installed' && rm \"\$c\" && echo \"installed kea-\$svc.conf\"; \
       else echo \"kea-\$svc.conf: nothing to change\"; fi; done"
check "the installed files are the tested candidates" rc0 0 \
    "for svc in dhcp4 dhcp6; do [ ! -f '$WORK/'\$svc'.installed' ] || \
       cmp '$WORK/'\$svc'.installed' '$KEA/kea-'\$svc'.conf' || exit 1; done"
step "Kea reloads its configuration, both families" "$TOOL reload"
check "every subnet comes from Mercury's file, both families" rc0 0 "$TOOL verify"
check "Kea's configuration hash is unchanged, both families" eq "$(cat "$WORK/hash-before")" \
    "$TOOL hash"
check "Kea's configuration, every reservation and every lease are the same after" rc0 0 \
    "$TOOL snapshot '$WORK/after.json' && sudo cp '$WORK/after.json' '$COPY/after.json' && \
     $TOOL compare '$WORK/before.json' '$WORK/after.json'"
echo "== the dated copy: $COPY (with before.json and after.json)"
summary
