#!/usr/bin/env bash
# C794 (docs/OPEN_FINDINGS.md): Loki 3 guesses a `detected_level` for every line from its words
# (`limits_config.discover_log_levels`, on by default) beside Mercury's own `severity` label,
# and nothing in Mercury reads it; traps read "unknown". The operator approved turning it off
# (2026-10-15). This adds `discover_log_levels: false` under `limits_config` in
# /etc/loki/local-config.yaml, written IN PLACE (the container bind-mounts that one file, so a
# replaced file would not be the one it reads), restarts Loki, and checks that the lines
# arriving after the restart carry no detected_level while every one still carries severity.
# Lines stored before keep theirs.
#
# Measured 2026-10-15 ~17:30 UTC, read-only: 26 lines in 10 minutes, all job network_syslog,
# every one carrying severity and detected_level; Loki's effective configuration (/config) said
# `discover_log_levels: true`; the file's limits_config holds retention_period,
# allow_structured_metadata and volume_enabled, and no discover_log_levels.
#
# The operator's, on the NMAS host, as their own user (sudo asked once):
#     bash <checkout>/scripts/host-steps/c794-loki-detected-level-off.sh
# About 7 minutes (a 5-minute wait for new lines, at about 2.6 a minute). On a failure after
# the write it puts the copied file back and restarts Loki. Undo by hand later (the step
# prints the folder):
#     sudo cp /var/backups/loki/c794-<stamp>/local-config.yaml /etc/loki/local-config.yaml && sudo docker restart loki
. "$(dirname "$0")/lib.sh"

export CFG=/etc/loki/local-config.yaml
export L=http://127.0.0.1:3100
export BACKUP
BACKUP=/var/backups/loki/c794-$(date -u +%Y%m%dT%H%M%SZ)
export NEW
NEW=$(mktemp -d)/local-config.yaml
# The window the after-checks ask about: from the restart, 5 minutes (about 13 lines expected).
export WAIT_S=300

# ready: Loki answers /ready within 120 s (c788's bound; it waits 15 s after its ring is ready).
ready() {
    local i
    for i in $(seq 1 60); do
        curl -sf "$L/ready" >/dev/null && return 0
        sleep 2
    done
    return 1
}
# count QUERY SINCE: Loki's count of lines matching the LogQL stream QUERY since epoch SINCE.
count() {
    local secs=$(( $(date +%s) - $2 + 1 ))
    curl -s --max-time 20 -G "$L/loki/api/v1/query" \
        --data-urlencode "query=sum(count_over_time($1[${secs}s]))" \
        | python3 -c 'import json, sys; r = json.load(sys.stdin)["data"]["result"]; print(int(float(r[0]["value"][1])) if r else 0)'
}
# The new file: limits_config's own block gains the line, nothing else changes.
render() {
    sudo awk '{ print } /^limits_config:[[:space:]]*$/ { print "  discover_log_levels: false" }' "$CFG"
}
undo() {
    sudo cp "$BACKUP/local-config.yaml" "$CFG" && sudo docker restart loki >/dev/null && ready \
        && echo "  undone: the copied configuration back, Loki ready" \
        || echo "  the undo did NOT finish: $BACKUP holds the copy"
}
export -f ready count render undo

plan "run as the operator's own user, not root" \
     "Loki is ready before" \
     "the file's limits_config does not name discover_log_levels yet" \
     "the copy is the file, byte for byte" \
     "the new file differs from the old by that one line alone" \
     "Loki is ready after the restart" \
     "Loki's effective configuration says discover_log_levels: false" \
     "lines arrived in the 5 minutes after the restart" \
     "none of them carries detected_level" \
     "every one of them carries severity"

not_root
check "Loki is ready before" rc0 "" 'curl -sf "$L/ready" >/dev/null'
check "the file's limits_config does not name discover_log_levels yet" eq "0" \
    'sudo grep -c "discover_log_levels" "$CFG" || true'

step "copy the configuration to $BACKUP" \
    'sudo mkdir -p "$BACKUP" && sudo cp -p "$CFG" "$BACKUP/local-config.yaml"'
check "the copy is the file, byte for byte" rc0 "" 'sudo cmp "$CFG" "$BACKUP/local-config.yaml"'
step "render the new configuration" 'render > "$NEW"'
check "the new file differs from the old by that one line alone" eq "> discover_log_levels: false" \
    'sudo diff "$CFG" "$NEW" | grep "^[<>]" | sed "s/^> */> /"'

ON_FAIL='undo'
ON_FAIL_WHAT="the copied configuration back, and Loki restarted"
step "write it in place (same file, owner and mode)" 'sudo tee "$CFG" < "$NEW" >/dev/null'
step "restart Loki" 'sudo docker restart loki >/dev/null'
export RESTARTED
RESTARTED=$(date +%s)
check "Loki is ready after the restart" rc0 "" 'ready'
check "Loki's effective configuration says discover_log_levels: false" has \
    "discover_log_levels: false" 'curl -s "$L/config" | grep "discover_log_levels"'

echo "== waiting ${WAIT_S} s for new lines (about 2.6 a minute measured)"
sleep "$WAIT_S"
check "lines arrived in the 5 minutes after the restart" ge 1 \
    'count "{job=~\".+\"}" "$RESTARTED"'
check "none of them carries detected_level" eq "0" \
    'count "{job=~\".+\"} | detected_level=~\".+\"" "$RESTARTED"'
check "every one of them carries severity" eq "same" \
    'a=$(count "{job=~\".+\"}" "$RESTARTED"); b=$(count "{job=~\".+\", severity=~\".+\"}" "$RESTARTED"); [ "$a" = "$b" ] && echo same || echo "$b of $a"'
echo "   the copy: $BACKUP/local-config.yaml"
summary
