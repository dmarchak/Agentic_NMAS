#!/usr/bin/env bash
# After the app host's reboot (2026-10-09: kernel 6.8.0-142 installed, 6.8.0-139 running): what
# was running before comes back on its own, the stopped Oxidized containers stay stopped, and
# each service answers its own health endpoint. READ ONLY: it changes nothing. The operator's,
# on the app host, from the checkout, a minute or two after the reboot:
#     bash <checkout>/scripts/host-steps/post-reboot-check.sh
#
# Its lists were read on the host before the reboot (2026-10-09, read only, via LAN): every
# container's restart policy and state, every unit enabled and active, the endpoints that
# answered 200, and the one unit already failed (openipmi.service: no IPMI device), which is
# the only failure it allows.
. "$(dirname "$0")/lib.sh"

# unless-stopped or always, running before the reboot.
CONTAINERS="loki mercury-postgres netbox-docker-netbox-1 netbox-docker-netbox-worker-1
netbox-docker-postgres-1 netbox-docker-redis-1 netbox-docker-redis-cache-1 snmp-exporter"
# Exited before the reboot; oxidized has restart=no, oxidized-pre-c143 unless-stopped (a stopped
# unless-stopped container is not started by the daemon), and both must stay down.
STOPPED="oxidized oxidized-pre-c143"
SERVICES="docker flask-app minio grafana-server prometheus prometheus-node-exporter alloy
kea-ctrl-agent kea-dhcp4-server kea-dhcp6-server snmpd thanos-compact thanos-query
thanos-sidecar thanos-store"
# snmptrapd is socket-activated: its socket listens from boot.
TRIGGERS="clab-sync.path nmas-update.path snmptrapd.socket clab-sync.timer
nmas-heartbeat-check.timer nmas-netbox-backup.timer nmas-netbox-restore-test.timer
nmas-startup-check.timer nmas-telemetry-check.timer"
ENDPOINTS="app=http://127.0.0.1:5000/health minio=http://127.0.0.1:9000/minio/health/live
loki=http://127.0.0.1:3100/ready prometheus=http://127.0.0.1:9090/-/ready
grafana=http://127.0.0.1:3000/api/health netbox=http://127.0.0.1:8000/login/
alloy=http://127.0.0.1:12345/-/ready snmp-exporter=http://127.0.0.1:9116/metrics
node-exporter=http://127.0.0.1:9100/metrics"
ALLOWED_FAILED="openipmi.service"
NEWEST=$(ls /boot/vmlinuz-* | sed 's|/boot/vmlinuz-||' | sort -V | tail -n 1)
export CONTAINERS STOPPED SERVICES TRIGGERS ENDPOINTS ALLOWED_FAILED

plan "run as the operator's own user, not root" \
     "running the newest installed kernel" \
     "no reboot is still required" \
     "the clock is synchronised" \
     "every service is active" \
     "every path, timer and socket is active" \
     "every container that ran is running" \
     "every container with a health check is healthy" \
     "the Oxidized containers stayed stopped" \
     "the restart policies are as before" \
     "every health endpoint answers 200" \
     "Mercury's records database answers a query" \
     "5433 is published on 127.0.0.1 only" \
     "no unit failed but the one failed before"

not_root
check "running the newest installed kernel" eq "$NEWEST" 'uname -r'
check "no reboot is still required" eq "no" \
    '[ -e /var/run/reboot-required ] && echo yes || echo no'
check "the clock is synchronised" eq "yes" 'timedatectl show -p NTPSynchronized --value'
check "every service is active" eq "" \
    'for u in $SERVICES; do systemctl is-active -q "$u" || echo "$u: $(systemctl is-active "$u")"; done'
check "every path, timer and socket is active" eq "" \
    'for u in $TRIGGERS; do systemctl is-active -q "$u" || echo "$u: $(systemctl is-active "$u")"; done'

# Not measured: how long these take to come back after a boot (NetBox's own start is the
# slowest seen to answer). Waits up to 300 s for the containers and endpoints, and says how
# long it took.
pending() {
    local n h pair code
    for n in $CONTAINERS; do
        [ "$(docker inspect -f '{{.State.Status}}' "$n" 2>/dev/null)" = running ] || { echo "$n"; return; }
        h=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$n" 2>/dev/null)
        [ -z "$h" ] || [ "$h" = healthy ] || { echo "$n"; return; }
    done
    for pair in $ENDPOINTS; do
        code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "${pair#*=}")
        [ "$code" = 200 ] || { echo "${pair%%=*}"; return; }
    done
}
echo "== waiting for the containers and endpoints (up to 300 s)"
for i in $(seq 1 60); do
    still=$(pending)
    [ -z "$still" ] && { echo "   all up after about $(( (i - 1) * 5 )) s"; break; }
    [ $((i % 6)) = 0 ] && echo "   still waiting on: $still"
    sleep 5
done

check "every container that ran is running" eq "" \
    'for n in $CONTAINERS; do s=$(docker inspect -f "{{.State.Status}}" "$n" 2>&1); [ "$s" = running ] || echo "$n: $s"; done'
check "every container with a health check is healthy" eq "" \
    'for n in $CONTAINERS; do h=$(docker inspect -f "{{if .State.Health}}{{.State.Health.Status}}{{end}}" "$n" 2>&1); [ -z "$h" ] || [ "$h" = healthy ] || echo "$n: $h"; done'
check "the Oxidized containers stayed stopped" eq "" \
    'for n in $STOPPED; do s=$(docker inspect -f "{{.State.Status}}" "$n" 2>&1); [ "$s" = exited ] || echo "$n: $s"; done'
check "the restart policies are as before" eq "mercury-postgres=unless-stopped oxidized=no" \
    'for n in mercury-postgres oxidized; do printf "%s=%s " "$n" "$(docker inspect -f "{{.HostConfig.RestartPolicy.Name}}" "$n")"; done | sed "s/ $//"'
check "every health endpoint answers 200" eq "" \
    'for pair in $ENDPOINTS; do c=$(curl -s -o /dev/null -m 5 -w "%{http_code}" "${pair#*=}"); [ "$c" = 200 ] || echo "${pair%%=*}: $c"; done'
check "Mercury's records database answers a query" eq "1" \
    'docker exec mercury-postgres psql -U postgres -d mercury -tAc "select 1"'
check "5433 is published on 127.0.0.1 only" eq "127.0.0.1:5433" \
    'ss -ltnH "sport = :5433" | tr -s " " | cut -d " " -f 4 | sort -u | paste -sd " "'
check "no unit failed but the one failed before" eq "" \
    'systemctl --failed --no-legend --plain | cut -d " " -f 1 | grep -vxF "$ALLOWED_FAILED" || true'
summary
