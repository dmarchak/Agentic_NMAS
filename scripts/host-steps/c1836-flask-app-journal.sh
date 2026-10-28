#!/usr/bin/env bash
# C1836: Alloy reads flask-app's journal into Loki (job="mercury"), so a refusal on a walk can be
# matched to the requests and log lines before it. Alloy already reads snmptrapd's journal the
# same way (`loki.source.journal "snmptrapd"`, its user in systemd-journal, read 2026-10-28), so
# this adds one marked block to /etc/alloy/config.alloy, between `// c1836: begin` and
# `// c1836: end`, using the config's own `loki.relabel.journal` rules and `loki.write.local`.
# On its first start the source reads back Alloy's default 7 hours of the journal.
# Mercury's request lines are the app's part of C1836, not this step's: this ships whatever the
# journal holds (756 lines from 2026-10-21 to 2026-10-28, none in a device's syslog form).
# Two of Mercury's reads take every job whose lines are in a device's syslog form (device_logs'
# job count, evidence_health's heartbeat count), so the step refuses when the journal holds
# such a line, and checks afterwards that the syslog jobs are the ones they were.
# Loki must be published on loopback only first (C1916): the app's log is not shipped into a
# store the LAN can read.
# Run on the NMAS host, as the operator's own user (sudo is asked for the config and Alloy):
#     bash <checkout>/scripts/host-steps/c1836-flask-app-journal.sh            # apply, then check
#     bash <checkout>/scripts/host-steps/c1836-flask-app-journal.sh check      # checks only
#     bash <checkout>/scripts/host-steps/c1836-flask-app-journal.sh rollback   # the block removed
. "$(dirname "$0")/lib.sh"

MODE=${1:-apply}
CONFIG=/etc/alloy/config.alloy
BEFORE=/etc/alloy/config.alloy.before-c1836
BEGIN='// c1836: begin'
END='// c1836: end'
HOSTLABEL=$(hostname -s)
DIR=$(mktemp -d)
FORM='\s[A-Za-z][A-Za-z0-9._-]*:\s+\*?\.?[A-Z][a-z]{2}\s+\d+\s+[\d:.]+(?:\s+[A-Z]{3,4})?:\s+%[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*-[0-7]-[A-Z0-9_]+'
export CONFIG BEFORE BEGIN END HOSTLABEL DIR FORM
# The jobs whose last 24 hours hold a line in a device's syslog form: device_logs.job_query's
# question, asked of Loki directly.
SYSLOG_JOBS='curl -sG -m 20 http://127.0.0.1:3100/loki/api/v1/query --data-urlencode "query=sum by (job) (count_over_time({job=~\".+\"} |~ \`$FORM\` [24h]))" | python3 -c "import json,sys; print(\" \".join(sorted(r[\"metric\"].get(\"job\",\"\") for r in json.load(sys.stdin)[\"data\"][\"result\"])))"'
MERCURY_LINES='curl -sG -m 20 http://127.0.0.1:3100/loki/api/v1/query --data-urlencode "query=sum(count_over_time({job=\"mercury\"}[8h]))" | python3 -c "import json,sys; r=json.load(sys.stdin)[\"data\"][\"result\"]; print(int(float(r[0][\"value\"][1])) if r else 0)"'
export SYSLOG_JOBS MERCURY_LINES
RESTORE='sudo install -m 0644 -o root -g root "$DIR/without.alloy" "$CONFIG" && sudo systemctl restart alloy'

plan "run as the operator's own user, not root" \
     "outside the backup window (08:30 to 09:10 UTC)" \
     "Loki is published on loopback only (C1916)" \
     "flask-app's journal holds no line in a device's syslog form" \
     "the new config is valid Alloy" \
     "Alloy runs" \
     "Alloy logged no error since the restart" \
     "flask-app's lines reach Loki as job=mercury" \
     "the syslog jobs are the ones they were" \
     "the config holds the block once" \
     "the config is unchanged outside the block"
not_root
check "outside the backup window (08:30 to 09:10 UTC)" eq "outside" \
    'm=$((10#$(date -u +%H) * 60 + 10#$(date -u +%M))); [ $m -ge 510 ] && [ $m -lt 550 ] && echo inside || echo outside'
check "Loki is published on loopback only (C1916)" eq "127.0.0.1:3100" \
    'sudo docker port loki 3100/tcp | sort -u | tr -d "\n"'

case $MODE in
apply)
    check "flask-app's journal holds no line in a device's syslog form" eq "0" \
        'sudo journalctl -u flask-app --no-pager -q -o cat | { grep -cP "$FORM" || true; }'
    export JOBS_BEFORE
    JOBS_BEFORE=$(bash -o pipefail -c "$SYSLOG_JOBS" 2>&1)
    echo "   syslog jobs before: $JOBS_BEFORE"
    step "write the new config in $DIR (the block appended)" \
        'sudo cat "$CONFIG" > "$DIR/without.alloy" && grep -qxF "$BEGIN" "$DIR/without.alloy" && { echo "the block is already installed"; exit 1; } || true; test -z "$(tail -c1 "$DIR/without.alloy")" || { echo "the config does not end in a newline"; exit 1; }; { cat "$DIR/without.alloy"; printf "%s\n" "$BEGIN"; printf "%s\n" "loki.source.journal \"flask_app\" {" "  forward_to    = [loki.write.local.receiver]" "  matches       = \"_SYSTEMD_UNIT=flask-app.service\"" "  labels        = { job = \"mercury\", host = \"$HOSTLABEL\" }" "  relabel_rules = loki.relabel.journal.rules" "}"; printf "%s\n" "$END"; } > "$DIR/config.alloy"'
    # `alloy validate`, not only `alloy fmt` (ibn7: validate also refuses an unknown stage).
    check "the new config is valid Alloy" rc0 "" 'alloy validate "$DIR/config.alloy" >/dev/null'
    step "keep the config as it was (once: a second run keeps the first copy)" \
        '[ -e "$BEFORE" ] || sudo cp -p "$CONFIG" "$BEFORE"'
    export START
    START=$(date -u '+%Y-%m-%d %H:%M:%S')
    ON_FAIL=$RESTORE
    ON_FAIL_WHAT="install the config without the block and restart Alloy (as before)"
    step "install the new config" 'sudo install -m 0644 -o root -g root "$DIR/config.alloy" "$CONFIG"'
    step "restart Alloy" 'sudo systemctl restart alloy'
    ;;
rollback)
    step "write the config without the block in $DIR" \
        'strip_marked <(sudo cat "$CONFIG") "$BEGIN" "$END" > "$DIR/without.alloy" && test -s "$DIR/without.alloy"'
    check "the new config is valid Alloy" rc0 "" 'alloy validate "$DIR/without.alloy" >/dev/null'
    export START
    START=$(date -u '+%Y-%m-%d %H:%M:%S')
    step "install it and restart Alloy" "$RESTORE"
    check "Alloy runs" eq "active" 'sleep 5; systemctl is-active alloy'
    check "Alloy logged no error since the restart" eq "0" \
        'sudo journalctl -u alloy --since "$START UTC" --no-pager -q | { grep -c "level=error" || true; }'
    check "the config holds the block once" eq "0" 'sudo grep -cxF "$BEGIN" "$CONFIG" || true'
    not_asked "flask-app's journal holds no line in a device's syslog form" "asked by apply, before the block is installed"
    not_asked "flask-app's lines reach Loki as job=mercury" "rollback stops new lines; those Loki holds stay until its retention"
    not_asked "the syslog jobs are the ones they were" "asked by apply"
    not_asked "the config is unchanged outside the block" "asked by apply and check"
    summary
    exit 0
    ;;
check)
    not_asked "flask-app's journal holds no line in a device's syslog form" "asked by apply, before the block is installed"
    not_asked "the new config is valid Alloy" "asked by apply and rollback, of the config they write"
    export START
    START=$(systemctl show alloy -p ActiveEnterTimestamp --value | xargs -I{} date -u -d "{}" '+%Y-%m-%d %H:%M:%S')
    ;;
*) echo "usage: $0 [apply|check|rollback]"; exit 2 ;;
esac

check "Alloy runs" eq "active" 'sleep 5; systemctl is-active alloy'
echo "== waiting 60 s for Alloy to read the journal and push"
sleep 60
check "Alloy logged no error since the restart" eq "0" \
    'sudo journalctl -u alloy --since "$START UTC" --no-pager -q | { grep -c "level=error" || true; }'
# The source reads back 7 hours on its first start; flask-app wrote at least its last start's
# lines in that time on every day read (2026-10-21 to 28).
check "flask-app's lines reach Loki as job=mercury" ge 1 "$MERCURY_LINES"
if [ "$MODE" = apply ]; then
    check "the syslog jobs are the ones they were" eq "$JOBS_BEFORE" "$SYSLOG_JOBS"
else
    check "the syslog jobs are the ones they were" lacks "mercury" "$SYSLOG_JOBS"
fi
check "the config holds the block once" eq "1" 'sudo grep -cxF "$BEGIN" "$CONFIG"'
check "the config is unchanged outside the block" eq "$(sudo sha256sum "$BEFORE" 2>/dev/null | cut -d' ' -f1)" \
    'strip_marked <(sudo cat "$CONFIG") "$BEGIN" "$END" | sha256sum | cut -d" " -f1'
summary
