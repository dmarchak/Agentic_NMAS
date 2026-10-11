#!/usr/bin/env bash
# C529 step 2's host side, once, before the first reservation Mercury writes (board B): every
# Kea subnet but ZTP's (which already does) takes its reservations from a file of Mercury's,
# `/etc/kea/nmas/reservations-<id>.json` (`reservations6-<id>.json` for IPv6), each starting as
# an empty list. Nothing a client sees changes: Kea's own configuration hash is compared before
# and after, and the step undoes itself if they differ.
#
# FIRST a dated copy of Kea's configuration and lease files (the operator's condition, overnight
# item 7), read back against the originals before anything is changed; its path is printed and
# goes in docs/END_OF_SESSION.md. Kea's main configuration files are root's: the app writes the
# candidates (`scripts/nmas-kea-reservation-files candidates`, each tested by Kea's own `-t`),
# and this step installs them by name. The subnets' own definitions stay in Kea's files: moving
# them into Mercury's is the subnet move, C529 step 5, with a fresh copy of its own.
# Run on the NMAS host, as the operator's own user (sudo asked for the copy and the install):
#     bash <checkout>/scripts/host-steps/c529-step2-reservation-files.sh
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
TOOL="cd '$CHECKOUT' && '$PY' scripts/nmas-kea-reservation-files"
KEA=/etc/kea
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COPY=/var/backups/kea/c529-step2-$STAMP
WORK=$(mktemp -d)
echo "== the dated copy goes to $COPY"

plan "run as the operator's own user, not root" \
     "Kea answers, both families" \
     "the dated copy reads back the same as the originals" \
     "the candidates pass Kea's own check" \
     "the installed files are the tested candidates" \
     "every subnet takes its reservations from Mercury's file" \
     "Kea's configuration hash is unchanged, both families"

not_root
check "Kea answers, both families" re '^dhcp4 [0-9a-f]+
dhcp6 [0-9a-f]+$' "$TOOL hash | tee '$WORK/hash-before'"

step "a dated copy of Kea's configuration and lease files (root's, mode 700)" \
    "sudo install -d -m 700 '$COPY' '$COPY/etc-kea' '$COPY/var-lib-kea' && \
     sudo cp -a '$KEA/kea-dhcp4.conf' '$KEA/kea-dhcp6.conf' '$KEA/kea-ctrl-agent.conf' '$COPY/etc-kea/' && \
     sudo cp -a '$KEA/nmas' '$COPY/etc-kea/nmas' && \
     sudo cp -a /var/lib/kea/. '$COPY/var-lib-kea/'"
check "the dated copy reads back the same as the originals" rc0 0 \
    "sudo cmp '$KEA/kea-dhcp4.conf' '$COPY/etc-kea/kea-dhcp4.conf' && \
     sudo cmp '$KEA/kea-dhcp6.conf' '$COPY/etc-kea/kea-dhcp6.conf' && \
     sudo cmp '$KEA/kea-ctrl-agent.conf' '$COPY/etc-kea/kea-ctrl-agent.conf' && \
     sudo diff -r '$KEA/nmas' '$COPY/etc-kea/nmas' && sudo diff -r /var/lib/kea '$COPY/var-lib-kea'"

step "what the step will do (the plan)" "$TOOL plan"
check "the candidates pass Kea's own check" rc0 0 "$TOOL candidates"

# Installed by name, each only if its candidate exists (a family with nothing to add has none).
ON_FAIL="sudo install -m 644 -o root -g root '$COPY/etc-kea/kea-dhcp4.conf' '$KEA/kea-dhcp4.conf' && \
         sudo install -m 644 -o root -g root '$COPY/etc-kea/kea-dhcp6.conf' '$KEA/kea-dhcp6.conf' && \
         $TOOL reload"
ON_FAIL_WHAT="Kea's two configuration files put back from the dated copy, and Kea reloaded"
step "install the tested candidates over Kea's configuration" \
    "for svc in dhcp4 dhcp6; do c='$KEA/nmas/.c529-candidate-'\$svc'.conf'; \
       if [ -f \"\$c\" ]; then sudo install -m 644 -o root -g root \"\$c\" '$KEA/kea-'\$svc'.conf' \
       && cp \"\$c\" '$WORK/'\$svc'.installed' && rm \"\$c\" && echo \"installed kea-\$svc.conf\"; \
       else echo \"kea-\$svc.conf: nothing to change\"; fi; done"
check "the installed files are the tested candidates" rc0 0 \
    "for svc in dhcp4 dhcp6; do [ ! -f '$WORK/'\$svc'.installed' ] || \
       cmp '$WORK/'\$svc'.installed' '$KEA/kea-'\$svc'.conf' || exit 1; done"
step "Kea reloads its configuration, both families" "$TOOL reload"
check "every subnet takes its reservations from Mercury's file" rc0 0 "$TOOL verify"
check "Kea's configuration hash is unchanged, both families" eq "$(cat "$WORK/hash-before")" \
    "$TOOL hash"
echo "== the dated copy: $COPY"
summary
