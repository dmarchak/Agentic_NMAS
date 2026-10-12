#!/usr/bin/env bash
# C722 (docs/OPEN_FINDINGS.md): Loki's streams carry no `device` label (their `host` is the
# collector), so every device filter read the line by a regex. This gives Alloy a `loki.process`
# stage on each source that sets `device` from the line itself: a syslog line's own name before
# its timestamp (`logging origin-id hostname`; the same pattern as Mercury's
# `device_logs.LOGQL_FIELDS`, held equal by tests/test_device_label_step.py), and a trap's name
# as snmptrapd prints it. Everything else in the config is as it was (read 2026-10-12): the two
# sources, their labels, the journal relabel, the one writer.
#
# The proof, before and after: syslog lines arrive; after the restart they still do, and every
# device that sent a line in the next six minutes (each sends a heartbeat every five) carries
# the label, with no line naming a device left without it. A trap's label is not provable here
# until one arrives (the newest was 2026-10-09). On any failure the previous config is put back.
# Run on the NMAS host, as the operator's own user:
#     bash <checkout>/scripts/host-steps/c722-device-label.sh
. "$(dirname "$0")/lib.sh"

CONFIG=/etc/alloy/config.alloy
BEFORE=/etc/alloy/config.alloy.before-c722
export DIR HOSTLABEL
DIR=$(mktemp -d)
HOSTLABEL=$(hostname -s)

cat > "$DIR/config.alloy" <<ALLOY
// Mercury's device label (C722, scripts/host-steps/c722-device-label.sh): each syslog line and
// trap carries \`device\`, the name the device gives itself in the line.
loki.source.journal "snmptrapd" {
  forward_to    = [loki.process.trap_device.receiver]
  matches       = "_SYSTEMD_UNIT=snmptrapd.service"
  labels        = { job = "snmptrapd", host = "$HOSTLABEL" }
  relabel_rules = loki.relabel.journal.rules
}

loki.relabel "journal" {
  forward_to = []
  rule {
    source_labels = ["__journal__systemd_unit"]
    target_label  = "unit"
  }
}

loki.process "trap_device" {
  forward_to = [loki.write.local.receiver]
  stage.regex {
    expression = \`^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d (?P<device>[A-Za-z][A-Za-z0-9._-]*) \[\`
  }
  stage.labels {
    values = { device = "" }
  }
}

loki.write "local" {
  endpoint {
    url = "http://localhost:3100/loki/api/v1/push"
  }
}

local.file_match "network_syslog" {
  path_targets = [{
    "__path__" = "/var/log/network/*.log",
    "job"      = "network_syslog",
    "host"     = "$HOSTLABEL",
  }]
}

loki.source.file "network_syslog" {
  targets    = local.file_match.network_syslog.targets
  forward_to = [loki.process.syslog_device.receiver]
}

loki.process "syslog_device" {
  forward_to = [loki.write.local.receiver]
  stage.regex {
    expression = \`\s(?P<device>[A-Za-z][A-Za-z0-9._-]*):\s+\*?\.?[A-Z][a-z]{2}\s+\d+\s+[\d:.]+(?:\s+[A-Z]{3,4})?:\s+\`
  }
  stage.labels {
    values = { device = "" }
  }
}
ALLOY

# Loki's answers, as one number each (an empty answer is 0). The regex is the line's device
# name as Mercury reads it (device_logs.LOGQL_FIELDS).
cat > "$DIR/loki.py" <<'PY'
import json, sys, urllib.parse, urllib.request
NAMED = (r"\s(?P<dev>[A-Za-z][A-Za-z0-9._-]*):\s+\*?\.?[A-Z][a-z]{2}\s+\d+\s+[\d:.]+"
         r"(?:\s+[A-Z]{3,4})?:\s+")
W = sys.argv[2] if len(sys.argv) > 2 else "6m"
Q = {"arrive": f'sum(count_over_time({{job="network_syslog"}}[{W}]))',
     "named": f'count(sum by (dev) (count_over_time({{job="network_syslog"}} | regexp `{NAMED}` | dev != "" [{W}])))',
     "labelled": f'count(sum by (device) (count_over_time({{job="network_syslog", device=~".+"}}[{W}])))',
     "unlabelled": f'sum(count_over_time({{job="network_syslog", device=""}} | regexp `{NAMED}` | dev != "" [{W}]))'}
u = "http://127.0.0.1:3100/loki/api/v1/query?" + urllib.parse.urlencode({"query": Q[sys.argv[1]]})
d = json.load(urllib.request.urlopen(u, timeout=20))
print(int(sum(float(x["value"][1]) for x in d["data"]["result"])))
PY

ON_FAIL_WHAT="put the previous config back and restart Alloy"
ON_FAIL="[ -e '$BEFORE' ] && sudo install -m 0644 -o root -g root '$BEFORE' '$CONFIG' && sudo systemctl restart alloy && systemctl is-active alloy"

plan "run as the operator's own user, not root" \
     "Loki answers" \
     "the host label is the one Loki holds" \
     "syslog lines arrive (the last 10 minutes)" \
     "the new config is valid Alloy" \
     "Alloy runs" \
     "syslog lines still arrive (six minutes after the restart)" \
     "lines carry a device label" \
     "every device that sent a line is labelled" \
     "no line naming a device lacks the label" \
     "Alloy logged no error since the restart"

not_root
check "Loki answers" eq "ready" "curl -s --max-time 5 http://127.0.0.1:3100/ready"
check "the host label is the one Loki holds" has "\"$HOSTLABEL\"" \
    "curl -sG --max-time 10 http://127.0.0.1:3100/loki/api/v1/label/host/values"
check "syslog lines arrive (the last 10 minutes)" ge 1 "python3 '$DIR/loki.py' arrive 10m"
check "the new config is valid Alloy" rc0 "" "alloy fmt '$DIR/config.alloy' >/dev/null"

step "keep the config as it was (once: a second run keeps the first copy)" \
    "[ -e '$BEFORE' ] || sudo cp -p '$CONFIG' '$BEFORE'"
step "install the new config" "sudo install -m 0644 -o root -g root '$DIR/config.alloy' '$CONFIG'"
export START
START=$(date -u '+%Y-%m-%d %H:%M:%S')
step "restart Alloy" "sudo systemctl restart alloy"
check "Alloy runs" eq "active" "sleep 5; systemctl is-active alloy"
echo "== waiting six and a half minutes: every device sends a heartbeat every five"
step "wait" "sleep 390"

check "syslog lines still arrive (six minutes after the restart)" ge 1 "python3 '$DIR/loki.py' arrive"
check "lines carry a device label" ge 1 "python3 '$DIR/loki.py' labelled"
echo "   devices named by their lines: $(python3 "$DIR/loki.py" named); labelled: $(python3 "$DIR/loki.py" labelled)"
check "every device that sent a line is labelled" eq "$(python3 "$DIR/loki.py" named)" \
    "python3 '$DIR/loki.py' labelled"
check "no line naming a device lacks the label" eq "0" "python3 '$DIR/loki.py' unlabelled"
check "Alloy logged no error since the restart" eq "0" \
    "sudo journalctl -u alloy --since '$START UTC' --no-pager -q | grep -c 'level=error' || true"
echo "   A trap's label waits for the next trap: {job=~\".*snmptrapd\", device=~\".+\"}."
summary
