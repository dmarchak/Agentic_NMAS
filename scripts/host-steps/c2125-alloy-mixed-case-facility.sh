#!/usr/bin/env bash
# C2125: Alloy's severity stage (ibn7's) takes a mixed-case facility, as Mercury's patterns do
# since C1813, so an OSPFv3 line (%OSPFv3-5-ADJCHG) carries its `severity` label like OSPF's.
# The installed stage reads the facility as upper case alone: `%[A-Z0-9_]+(?:-[A-Z0-9_]+)*-`.
# This replaces that one expression, and nothing else, with `%[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*-`
# (ibn7's script carries the same since C1813; tests/test_severity_trap_label_step.py holds it
# equal to Mercury's pattern). The config is kept as it was until `rollback` puts it back.
# Run on the NMAS host, as the operator's own user (sudo is asked for the config and Alloy):
#     bash <checkout>/scripts/host-steps/c2125-alloy-mixed-case-facility.sh            # apply, then check
#     bash <checkout>/scripts/host-steps/c2125-alloy-mixed-case-facility.sh check      # checks only
#     bash <checkout>/scripts/host-steps/c2125-alloy-mixed-case-facility.sh rollback   # the kept config back
. "$(dirname "$0")/lib.sh"

MODE=${1:-apply}
CONFIG=/etc/alloy/config.alloy
BEFORE=/etc/alloy/config.alloy.before-c2125
DIR=$(mktemp -d)
OLD='%[A-Z0-9_]+(?:-[A-Z0-9_]+)*-(?P<severity>[0-7])-'
NEW='%[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*-(?P<severity>[0-7])-'
export CONFIG BEFORE DIR OLD NEW
LINES='curl -sG -m 20 http://127.0.0.1:3100/loki/api/v1/query --data-urlencode "query=sum(count_over_time({severity=~\"[0-7]\"}[6m]))" | python3 -c "import json,sys; r=json.load(sys.stdin)[\"data\"][\"result\"]; print(int(float(r[0][\"value\"][1])) if r else 0)"'
export LINES
RESTORE='sudo install -m 0644 -o root -g root "$BEFORE" "$CONFIG" && sudo systemctl restart alloy'

plan "run as the operator's own user, not root" \
     "outside the backup window (08:30 to 09:10 UTC)" \
     "the installed stage takes an upper-case facility alone, once" \
     "the new config is valid Alloy" \
     "the new config differs only in that expression" \
     "Alloy runs" \
     "Alloy logged no error since the restart" \
     "lines still arrive with a severity label" \
     "the installed stage takes a mixed-case facility"
not_root
check "outside the backup window (08:30 to 09:10 UTC)" eq "outside" \
    'm=$((10#$(date -u +%H) * 60 + 10#$(date -u +%M))); [ $m -ge 510 ] && [ $m -lt 550 ] && echo inside || echo outside'

case $MODE in
apply)
    check "the installed stage takes an upper-case facility alone, once" eq "1" \
        'sudo grep -cF -- "$OLD" "$CONFIG"'
    step "write the new config in $DIR (the one expression replaced)" \
        'sudo cat "$CONFIG" > "$DIR/old.alloy" && python3 -c "import os,sys; t=open(sys.argv[1]).read(); assert t.count(os.environ[\"OLD\"]) == 1; open(sys.argv[2], \"w\").write(t.replace(os.environ[\"OLD\"], os.environ[\"NEW\"]))" "$DIR/old.alloy" "$DIR/config.alloy"'
    check "the new config is valid Alloy" rc0 "" 'alloy validate "$DIR/config.alloy" >/dev/null'
    check "the new config differs only in that expression" eq "1" \
        'diff "$DIR/old.alloy" "$DIR/config.alloy" | grep -c "^>"'
    step "keep the config as it was (once: a second run keeps the first copy)" \
        '[ -e "$BEFORE" ] || sudo cp -p "$CONFIG" "$BEFORE"'
    export START
    START=$(date -u '+%Y-%m-%d %H:%M:%S')
    ON_FAIL=$RESTORE
    ON_FAIL_WHAT="put the kept config back and restart Alloy (as before)"
    step "install the new config" 'sudo install -m 0644 -o root -g root "$DIR/config.alloy" "$CONFIG"'
    step "restart Alloy" 'sudo systemctl restart alloy'
    ;;
rollback)
    export START
    START=$(date -u '+%Y-%m-%d %H:%M:%S')
    step "put the kept config back and restart Alloy" "$RESTORE"
    check "Alloy runs" eq "active" 'sleep 5; systemctl is-active alloy'
    check "Alloy logged no error since the restart" eq "0" \
        'sudo journalctl -u alloy --since "$START UTC" --no-pager -q | { grep -c "level=error" || true; }'
    check "the installed stage takes an upper-case facility alone, once" eq "1" \
        'sudo grep -cF -- "$OLD" "$CONFIG"'
    not_asked "the new config is valid Alloy" "asked by apply, of the config it writes"
    not_asked "the new config differs only in that expression" "asked by apply"
    not_asked "lines still arrive with a severity label" "asked by apply and check"
    not_asked "the installed stage takes a mixed-case facility" "rollback puts the old one back"
    summary
    exit 0
    ;;
check)
    not_asked "the installed stage takes an upper-case facility alone, once" "asked by apply and rollback"
    not_asked "the new config is valid Alloy" "asked by apply, of the config it writes"
    not_asked "the new config differs only in that expression" "asked by apply"
    export START
    START=$(systemctl show alloy -p ActiveEnterTimestamp --value | xargs -I{} date -u -d "{}" '+%Y-%m-%d %H:%M:%S')
    ;;
*) echo "usage: $0 [apply|check|rollback]"; exit 2 ;;
esac

check "Alloy runs" eq "active" 'sleep 5; systemctl is-active alloy'
# Every device sends a line at least every five minutes (ibn7's measurement, 2026-10-15).
echo "== waiting six and a half minutes: the longest gap between syslog lines is five"
sleep 390
check "Alloy logged no error since the restart" eq "0" \
    'sudo journalctl -u alloy --since "$START UTC" --no-pager -q | { grep -c "level=error" || true; }'
check "lines still arrive with a severity label" ge 1 "$LINES"
check "the installed stage takes a mixed-case facility" eq "1" 'sudo grep -cF -- "$NEW" "$CONFIG"'
summary
