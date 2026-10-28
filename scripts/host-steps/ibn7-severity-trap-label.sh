#!/usr/bin/env bash
# IBN_DESIGN section 9, decision 7 (the operator, 2026-10-13): Loki's `severity` label set at
# ingest, and a stable trap label with the trap's OID parsed, before History › Query's builder
# (board F3) is built. The label decisions (the operator, 2026-10-14): severity is the digit 0-7;
# traps carry no severity; facility stays a line filter, never a label; trap_oid is the OID as
# snmptrapd prints it, and this step checks the MIB set it prints with is the one measured; the
# `<UNKNOWN>` host field on traps (C789) is a separate step.
#
# What it changes: /etc/alloy/config.alloy only. Everything in C722's config stays as it is (the
# two sources, `device` on both, the journal relabel, the one writer); three things are added:
#   1. network_syslog: `severity`, the digit (0-7) inside the line's Cisco mnemonic
#      (%LINK-3-UPDOWN is 3), read by Mercury's own pattern (device_logs.LOGQL_FIELDS): the
#      device's name before its timestamp, then the mnemonic. rsyslog's file format does not
#      keep the PRI, so the mnemonic is the line's only severity. A line without a mnemonic gets
#      no label (absent, never a guessed value).
#   2. snmptrapd: a STABLE `job="snmptrapd"`. Today Alloy replaces the config's job with its own
#      component name, `loki.source.journal.snmptrapd` (measured 2026-10-14); a process stage
#      runs after the source, so the value set there is the one Loki stores. Older traps keep the
#      old job; every Grafana query on traps reads `job=~".*snmptrapd"`, which matches both
#      (read through Mercury's Grafana connection 2026-10-15: 6 dashboards, 25 alert rules, 0
#      library panels; no exact match on the old name, so nothing in Grafana changes).
#   3. snmptrapd: `trap_oid`, the notification's snmpTrapOID.0 as snmptrapd prints it
#      (`IF-MIB::linkUp`; numeric when no MIB names it). A notification TYPE, so bounded (2 values
#      in 29 days). Varbind values (ifDescr, ifIndex, uptime) are NEVER labels.
#
# The proof: syslog lines still arrive after the restart; every line Mercury's pattern reads a
# mnemonic in carries `severity`; its values are digits 0-7 only; `device` still labels every
# named line (C722 holds); Alloy logged no error. A trap's labels cannot be proved until a trap
# arrives (the newest was 2026-10-09 17:41 UTC): NOT ASKED here; Update's after-step check
# `[trap-label]` reads it once the operator's port flap sends one. On any failure the previous
# config is put back.
#
# Run on the NMAS host, as the operator's own user, outside 08:30-09:10 UTC:
#     bash <checkout>/scripts/host-steps/ibn7-severity-trap-label.sh
. "$(dirname "$0")/lib.sh"

CONFIG=/etc/alloy/config.alloy
BEFORE=/etc/alloy/config.alloy.before-ibn7
export DIR HOSTLABEL
DIR=$(mktemp -d)
HOSTLABEL=$(hostname -s)

# The MIB set snmptrapd prints trap OIDs with (it runs as root, so root's ~/.snmp/mibs too):
# every file in its MIB directories by checksum, the MIB lines of its two configurations, and
# the unit's active ExecStart and Environment. Measured 2026-10-15 01:2x UTC, twice, equal:
# 13 files a503984725018043. A changed set would change what trap_oid holds (a name can turn
# into digits, or the reverse) and split one notification across two label values.
MIBSET_MEASURED="13 files a503984725018043"
mibset() {
    local n
    n=$(sudo find /usr/share/snmp/mibs /root/.snmp/mibs -type f 2>/dev/null | wc -l)
    {
        sudo find /usr/share/snmp/mibs /root/.snmp/mibs -type f -print0 2>/dev/null | sort -z | sudo xargs -0 -r sha256sum
        for f in /etc/snmp/snmp.conf /etc/snmp/snmptrapd.conf; do
            sudo grep -E '^[[:space:]]*(mibs|mibdirs|mibfile)[[:space:]]' "$f" 2>/dev/null | sed "s|^|$f: |"
        done
        systemctl cat snmptrapd.service | grep -E '^ExecStart=.' | tail -1
        systemctl show snmptrapd.service -p Environment
    } | sha256sum | cut -c1-16 | sed "s/^/$n files /"
}
export -f mibset

cat > "$DIR/config.alloy" <<ALLOY
// Mercury's labels at ingest. \`device\` (C722, scripts/host-steps/c722-device-label.sh): the name
// the device gives itself in the line. \`severity\` (IBN decision 7): the digit in a syslog line's
// mnemonic. Traps: a stable \`job\` and \`trap_oid\`, the notification's snmpTrapOID.0.
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
  stage.static_labels {
    values = { job = "snmptrapd" }
  }
  stage.regex {
    expression = \`^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d (?P<device>[A-Za-z][A-Za-z0-9._-]*) \[\`
  }
  stage.regex {
    expression = \`(?:^|\s)SNMPv2-MIB::snmpTrapOID\.0 = OID: (?P<trap_oid>[A-Za-z][A-Za-z0-9-]*::[A-Za-z][A-Za-z0-9]*(?:\.\d+){0,16}|\.?\d+(?:\.\d+){1,31})(?:\s|$)\`
  }
  stage.labels {
    values = { device = "", trap_oid = "" }
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
  stage.regex {
    expression = \`\s[A-Za-z][A-Za-z0-9._-]*:\s+\*?\.?[A-Z][a-z]{2}\s+\d+\s+[\d:.]+(?:\s+[A-Z]{3,4})?:\s+%[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*-(?P<severity>[0-7])-[A-Z0-9_]+\`
  }
  stage.labels {
    values = { device = "", severity = "" }
  }
}
ALLOY

# The severity stage takes a mixed-case facility since C1813 (%OSPFv3-5-ADJCHG); the stage this
# step installed on 2026-10-15 takes an upper-case facility alone until C2125's step replaces it.
# Loki's answers, one number each (an empty answer is 0). MN is Mercury's pattern
# (device_logs.LOGQL_FIELDS) with the mnemonic's digit named.
cat > "$DIR/loki.py" <<'PY'
import json, sys, urllib.parse, urllib.request
MN = (r"\s(?P<dev>[A-Za-z][A-Za-z0-9._-]*):\s+\*?\.?[A-Z][a-z]{2}\s+\d+\s+[\d:.]+"
      r"(?:\s+[A-Z]{3,4})?:\s+%[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*-(?P<sev>[0-7])-[A-Z0-9_]+")
W = sys.argv[2] if len(sys.argv) > 2 else "6m"
S = '{job="network_syslog"}'
Q = {"arrive": f'sum(count_over_time({S}[{W}]))',
     "mnemonic": f'sum(count_over_time({S} | regexp `{MN}` | sev != "" [{W}]))',
     "severity": f'sum(count_over_time({{job="network_syslog", severity=~"[0-7]"}}[{W}]))',
     "unsevered": f'sum(count_over_time({{job="network_syslog", severity=""}} | regexp `{MN}` | sev != "" [{W}]))',
     "named": f'count(sum by (dev) (count_over_time({S} | regexp `{MN}` | dev != "" [{W}])))',
     "labelled": f'count(sum by (device) (count_over_time({{job="network_syslog", device=~".+"}}[{W}])))'}
if sys.argv[1] == "values":       # every severity value Loki holds since the restart window
    u = "http://127.0.0.1:3100/loki/api/v1/label/severity/values?" + urllib.parse.urlencode(
        {"since": W})
    print(" ".join(sorted(json.load(urllib.request.urlopen(u, timeout=20)).get("data") or [])))
    sys.exit(0)
u = "http://127.0.0.1:3100/loki/api/v1/query?" + urllib.parse.urlencode({"query": Q[sys.argv[1]]})
d = json.load(urllib.request.urlopen(u, timeout=20))
print(int(sum(float(x["value"][1]) for x in d["data"]["result"])))
PY

ON_FAIL_WHAT="put the previous config back and restart Alloy"
ON_FAIL="[ -e '$BEFORE' ] && sudo install -m 0644 -o root -g root '$BEFORE' '$CONFIG' && sudo systemctl restart alloy && systemctl is-active alloy"

plan "run as the operator's own user, not root" \
     "outside the backup window (08:30 to 09:10 UTC)" \
     "Loki answers" \
     "the host label is the one Loki holds" \
     "the installed config is C722's (two process stages, no severity yet)" \
     "the MIB set snmptrapd prints trap OIDs with is the one measured" \
     "syslog lines arrive (the last 10 minutes)" \
     "the new config is valid Alloy" \
     "Alloy runs" \
     "syslog lines still arrive (six minutes after the restart)" \
     "every line Mercury reads a mnemonic in carries severity" \
     "severity holds only the digits 0 to 7" \
     "every device that sent a line is still labelled (C722)" \
     "Alloy logged no error since the restart" \
     "a trap carries job=snmptrapd and trap_oid"

not_root
check "outside the backup window (08:30 to 09:10 UTC)" eq "outside" \
    'm=$((10#$(date -u +%H) * 60 + 10#$(date -u +%M))); [ $m -ge 510 ] && [ $m -lt 550 ] && echo inside || echo outside'
check "Loki answers" eq "ready" "curl -s --max-time 5 http://127.0.0.1:3100/ready"
check "the host label is the one Loki holds" has "\"$HOSTLABEL\"" \
    "curl -sG --max-time 10 http://127.0.0.1:3100/loki/api/v1/label/host/values"
# A drifted config is not overwritten blind: the one this replaces is C722's, as read 2026-10-15
# (1450 bytes, 2026-10-13 00:33 UTC). A second run finds its own config and is refused here too;
# put the backup back first if a re-run is wanted.
check "the installed config is C722's (two process stages, no severity yet)" eq "2 0" \
    "echo \"\$(sudo grep -c '^loki.process ' '$CONFIG') \$(sudo grep -c 'severity' '$CONFIG')\""
check "the MIB set snmptrapd prints trap OIDs with is the one measured" eq "$MIBSET_MEASURED" 'mibset'
check "syslog lines arrive (the last 10 minutes)" ge 1 "python3 '$DIR/loki.py' arrive 10m"
# `alloy validate`, not only `alloy fmt`: fmt checks syntax, validate also refuses an unknown
# stage (shown 2026-10-14: a planted `stage.no_such_stage` fails validate; this config passes).
check "the new config is valid Alloy" rc0 "" "alloy validate '$DIR/config.alloy' >/dev/null"

step "keep the config as it was (once: a second run keeps the first copy)" \
    "[ -e '$BEFORE' ] || sudo cp -p '$CONFIG' '$BEFORE'"
step "install the new config" "sudo install -m 0644 -o root -g root '$DIR/config.alloy' '$CONFIG'"
export START
START=$(date -u '+%Y-%m-%d %H:%M:%S')
step "restart Alloy" "sudo systemctl restart alloy"
check "Alloy runs" eq "active" "sleep 5; systemctl is-active alloy"
# Every device sends a line at least every five minutes: the longest gap between syslog lines
# in the 24 hours before 2026-10-15 01:10 UTC was 300 s.
echo "== waiting six and a half minutes: the longest gap between syslog lines is five"
step "wait" "sleep 390"

check "syslog lines still arrive (six minutes after the restart)" ge 1 "python3 '$DIR/loki.py' arrive"
echo "   lines with a mnemonic: $(python3 "$DIR/loki.py" mnemonic); with severity: $(python3 "$DIR/loki.py" severity)"
check "every line Mercury reads a mnemonic in carries severity" eq "0" \
    "python3 '$DIR/loki.py' unsevered"
check "severity holds only the digits 0 to 7" re '^[0-7]( [0-7])*$' "python3 '$DIR/loki.py' values 6m"
check "every device that sent a line is still labelled (C722)" eq "$(python3 "$DIR/loki.py" named)" \
    "python3 '$DIR/loki.py' labelled"
check "Alloy logged no error since the restart" eq "0" \
    "sudo journalctl -u alloy --since '$START UTC' --no-pager -q | grep -c 'level=error' || true"
not_asked "a trap carries job=snmptrapd and trap_oid" \
    "no trap can be made here without a device; the operator's port flap sends one, and Update's [trap-label] check reads {job=\"snmptrapd\", trap_oid=~\".+\"}"
summary
