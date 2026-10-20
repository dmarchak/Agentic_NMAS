#!/usr/bin/env bash
# C1419's stopgap (the operator, 2026-10-20), for ONE retired device at a time: Grafana keeps a
# provisioned alert rule its file has dropped unless a file names it under `deleteRules`, and
# Retire has no telemetry step, so a retired device's heartbeat and telemetry rules outlive it
# ("NMAS heartbeat missing: <device>", uid nmas-hb-<device>; "NMAS telemetry stream lost:
# <device> subscription <n>", uid nmas-tel-<device>-<n>). The collector needs nothing: Telegraf's
# cisco_telemetry_mdt is a listener the device dialled out to. This step:
#   1. refuses unless every live rule naming the device is in its own uid range, and one at
#      least is (nothing to do otherwise);
#   2. refuses unless Mercury's own files no longer hold a rule for it: the installed heartbeat
#      file, and the telemetry rules regenerated from the committed goldens (it is retired);
#   3. refuses unless the regenerated telemetry rules hold exactly the installed file's streams
#      less the device's;
#   4. installs them and a one-off deleteRules file naming exactly the device's live uids,
#      restarts Grafana, proves Grafana runs no rule naming the device and every other rule as
#      before;
#   5. removes the one-off file, so a later restart cannot delete a new device of that name's
#      rules.
# The real fix (C1419): both generators write deleteRules for what they drop, and Retire gains a
# telemetry step. A dated copy of the installed rules is taken first; a failure puts it back.
# Run on the NMAS host, as the operator's own user (sudo asked for the copy and the install):
#     bash <checkout>/scripts/host-steps/c1419-retired-device-rules.sh <device>
. "$(dirname "$0")/lib.sh"

DEV=${1:-}
if ! [[ "$DEV" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    echo "REFUSED: name the retired device: bash $0 <device> (got '${DEV}')"
    exit 2
fi
PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
RULES="cd '$CHECKOUT' && '$PY' scripts/nmas-grafana-rules"
TEL="cd '$CHECKOUT' && '$PY' scripts/nmas-telemetry-rules"
DIR=/etc/grafana/provisioning/alerting
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COPY=/var/backups/grafana/c1419-$DEV-$STAMP
WORK=$(mktemp -d)
DEVRE=$(printf '%s' "$DEV" | sed 's/[.]/\\./g')
NAMES="(: $DEVRE\$| $DEVRE subscription )"
OWN="^(nmas-hb-$DEVRE|nmas-tel-$DEVRE-[0-9]+)\$"
echo "== the device: $DEV; the dated copy goes to $COPY"

plan "run as the operator's own user, not root" \
     "Grafana answers, and every live rule naming the device is in its own uid range" \
     "Mercury's heartbeat file holds no rule for the device" \
     "the dated copy reads back the same as the installed rules" \
     "the regenerated telemetry rules hold no rule for the device" \
     "the regenerated telemetry rules hold exactly the installed streams less the device's" \
     "the one-off deleteRules file names exactly the device's live uids" \
     "Grafana answers again after the restart" \
     "Grafana runs no rule naming the device" \
     "every other live rule is as before" \
     "the one-off deleteRules file is removed"

not_root
step "the device's live rules, read" \
    "$RULES list nmas-hb- nmas-tel- | awk -F'\t' '\$3 ~ /$NAMES/ {print \$1}' | sort > '$WORK/uids' && cat '$WORK/uids'"
check "Grafana answers, and every live rule naming the device is in its own uid range" eq "ok" \
    "[ -s '$WORK/uids' ] || { echo 'none: nothing to delete'; exit 0; }; grep -vE '$OWN' '$WORK/uids' && exit 0; echo ok"
check "Mercury's heartbeat file holds no rule for the device" eq "0" \
    "grep -cE 'nmas-hb-$DEVRE([^A-Za-z0-9_.-]|\$)' '$DIR/nmas-heartbeat.yaml' || true"
step "every other live rule, recorded before" \
    "$RULES list | cut -f1 | grep -vxF -f '$WORK/uids' | sort > '$WORK/others.before' && wc -l < '$WORK/others.before'"

step "a fresh dated copy of the installed rules (root's, mode 700)" \
    "sudo install -d -m 700 '$COPY' && sudo cp -a '$DIR/nmas-telemetry.yaml' '$DIR/nmas-heartbeat.yaml' '$COPY/'"
check "the dated copy reads back the same as the installed rules" rc0 0 \
    "sudo cmp '$DIR/nmas-telemetry.yaml' '$COPY/nmas-telemetry.yaml' && sudo cmp '$DIR/nmas-heartbeat.yaml' '$COPY/nmas-heartbeat.yaml'"

step "regenerate the telemetry rules from the committed goldens" \
    "$TEL --out '$WORK/nmas-telemetry.yaml'"
check "the regenerated telemetry rules hold no rule for the device" eq "0" \
    "grep -cE 'nmas-tel-$DEVRE-[0-9]+' '$WORK/nmas-telemetry.yaml' || true"
check "the regenerated telemetry rules hold exactly the installed streams less the device's" eq "" \
    "diff <(grep -oE 'nmas-tel-[A-Za-z0-9_.-]+' '$DIR/nmas-telemetry.yaml' | sort -u | grep -vE '^nmas-tel-$DEVRE-[0-9]+\$') \
          <(grep -oE 'nmas-tel-[A-Za-z0-9_.-]+' '$WORK/nmas-telemetry.yaml' | sort -u)"

step "the one-off deleteRules file, written for exactly the device's live uids" \
    "{ echo 'apiVersion: 1'; echo 'deleteRules:'; while read -r u; do echo '  - orgId: 1'; echo \"    uid: \$u\"; done < '$WORK/uids'; } > '$WORK/nmas-c1419-delete.yaml' && cat '$WORK/nmas-c1419-delete.yaml'"
check "the one-off deleteRules file names exactly the device's live uids" eq "" \
    "grep -oE 'uid: .*' '$WORK/nmas-c1419-delete.yaml' | cut -d' ' -f2 | sort | diff '$WORK/uids' -"

ON_FAIL="sudo install -m 0644 '$COPY/nmas-telemetry.yaml' '$DIR/nmas-telemetry.yaml' && \
         sudo rm -f '$DIR/nmas-c1419-delete.yaml' && sudo systemctl restart grafana-server"
ON_FAIL_WHAT="the telemetry rules put back from the dated copy, the one-off file removed, Grafana restarted"
step "install the telemetry rules and the one-off deleteRules file, then restart Grafana" \
    "sudo install -m 0644 '$WORK/nmas-telemetry.yaml' '$DIR/nmas-telemetry.yaml' && \
     sudo install -m 0644 '$WORK/nmas-c1419-delete.yaml' '$DIR/nmas-c1419-delete.yaml' && \
     sudo systemctl restart grafana-server"
check "Grafana answers again after the restart" re '^[0-9]+$' \
    "for i in \$(seq 1 60); do n=\$($RULES count 2>/dev/null) && [[ \"\$n\" =~ ^[0-9]+\$ ]] && { echo \$n; exit 0; }; sleep 2; done; echo 'no answer in 120 s'"
check "Grafana runs no rule naming the device" eq "" \
    "$RULES list | awk -F'\t' '\$3 ~ /$NAMES/ {print \$1}'"
check "every other live rule is as before" eq "" \
    "$RULES list | cut -f1 | sort | diff '$WORK/others.before' -"
ON_FAIL=""
step "remove the one-off deleteRules file (by name)" "sudo rm -f '$DIR/nmas-c1419-delete.yaml'"
check "the one-off deleteRules file is removed" eq "absent" \
    "[ -e '$DIR/nmas-c1419-delete.yaml' ] && echo present || echo absent"
echo "== the dated copy: $COPY"
summary
