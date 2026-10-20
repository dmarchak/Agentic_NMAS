#!/usr/bin/env bash
# C1419's install step (the real fix after the stopgap, 2026-10-20), for one generated rules
# file and its delete file: Grafana keeps a provisioned alert rule its file has dropped unless a
# file names it under `deleteRules`, so each generator (`nmas-heartbeat-rules`,
# `nmas-telemetry-rules`, and Retire's and the re-measure's heartbeat writes) writes, beside its
# rules file, `<rules>-delete.yaml` naming the rules in its own uid range that Grafana or the
# installed file held and the new file no longer generates (modules/grafana_rule_deletes.py).
# This step, the stopgap's measured shape made general:
#   1. refuses unless the rules file generates rules in its own range only, and the delete
#      file (when there is one) names uids in that range only and none the rules file generates;
#   2. takes a dated copy of the installed rules file;
#   3. installs the rules file and the delete file, restarts Grafana;
#   4. proves Grafana runs none of the deleted rules and every rule the file generates;
#   5. removes the delete file (installed and written), so a later restart never deletes a rule
#      of the same uid generated again (a device onboarded again under the name).
# A failure puts the dated copy back, removes the installed delete file and restarts Grafana.
# Run on the NMAS host, as the operator's own user (sudo asked for the copy and the install):
#     bash <checkout>/scripts/host-steps/c1419-install-alert-rules.sh <heartbeat|telemetry> \
#         [written rules file] [installed rules file]
. "$(dirname "$0")/lib.sh"

KIND=${1:-}
case "$KIND" in
    heartbeat) PREFIX=nmas-hb- ;;
    telemetry) PREFIX=nmas-tel- ;;
    *) echo "REFUSED: name the rules: bash $0 <heartbeat|telemetry> [written] [installed] (got '${KIND}')"
       exit 2 ;;
esac
WRITTEN=${2:-$CHECKOUT/deploy/grafana/provisioning/alerting/nmas-$KIND.yaml}
INSTALLED=${3:-/etc/grafana/provisioning/alerting/nmas-$KIND.yaml}
DELETE="${WRITTEN%.yaml}-delete.yaml"
DELETE_INSTALLED="${INSTALLED%.yaml}-delete.yaml"
PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
RULES="cd '$CHECKOUT' && '$PY' scripts/nmas-grafana-rules"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COPY=/var/backups/grafana/c1419-install-$KIND-$STAMP
WORK=$(mktemp -d)
echo "== the $KIND rules: $WRITTEN -> $INSTALLED; the delete file: $DELETE; the dated copy: $COPY"

plan "run as the operator's own user, not root" \
     "the written rules file generates rules in its own range only" \
     "the delete file names uids in its range only and none the rules file generates" \
     "the dated copy reads back the same as the installed rules" \
     "Grafana answers again after the restart" \
     "Grafana runs none of the deleted rules" \
     "Grafana runs every rule the file generates" \
     "the delete file is removed, installed and written"

not_root
step "the uids the written rules file generates" \
    "$RULES rules '$WRITTEN' > '$WORK/generated' && wc -l < '$WORK/generated'"
check "the written rules file generates rules in its own range only" eq "ok" \
    "[ -s '$WORK/generated' ] || { echo 'it generates no rule'; exit 0; }; grep -v '^$PREFIX' '$WORK/generated' && exit 0; echo ok"
step "the uids the delete file names (none when there is no delete file)" \
    "$RULES deletes '$DELETE' > '$WORK/deletes' && cat '$WORK/deletes'"
check "the delete file names uids in its range only and none the rules file generates" eq "" \
    "grep -v '^$PREFIX' '$WORK/deletes'; comm -12 '$WORK/deletes' '$WORK/generated'"

step "a fresh dated copy of the installed rules (root's, mode 700)" \
    "sudo install -d -m 700 '$COPY' && sudo cp -a '$INSTALLED' '$COPY/'"
check "the dated copy reads back the same as the installed rules" rc0 0 \
    "sudo cmp '$INSTALLED' '$COPY/$(basename "$INSTALLED")'"

ON_FAIL="sudo install -m 0644 '$COPY/$(basename "$INSTALLED")' '$INSTALLED' && \
         sudo rm -f '$DELETE_INSTALLED' && sudo systemctl restart grafana-server"
ON_FAIL_WHAT="the installed rules put back from the dated copy, the delete file removed, Grafana restarted"
step "install the rules file and its delete file, then restart Grafana" \
    "sudo install -m 0644 '$WRITTEN' '$INSTALLED' && \
     { [ ! -s '$WORK/deletes' ] || sudo install -m 0644 '$DELETE' '$DELETE_INSTALLED'; } && \
     sudo systemctl restart grafana-server"
check "Grafana answers again after the restart" re '^[0-9]+$' \
    "for i in \$(seq 1 60); do n=\$($RULES count 2>/dev/null) && [[ \"\$n\" =~ ^[0-9]+\$ ]] && { echo \$n; exit 0; }; sleep 2; done; echo 'no answer in 120 s'"
step "Grafana's rules in this range, read" \
    "$RULES list '$PREFIX' | cut -f1 | sort > '$WORK/live' && wc -l < '$WORK/live'"
check "Grafana runs none of the deleted rules" eq "" \
    "comm -12 '$WORK/deletes' '$WORK/live'"
check "Grafana runs every rule the file generates" eq "" \
    "comm -23 '$WORK/generated' '$WORK/live'"
ON_FAIL=""
step "remove the delete file, installed and written (by name)" \
    "sudo rm -f '$DELETE_INSTALLED' && rm -f '$DELETE'"
check "the delete file is removed, installed and written" eq "absent" \
    "[ -e '$DELETE_INSTALLED' ] || [ -e '$DELETE' ] && echo present || echo absent"
echo "== the dated copy: $COPY"
summary
