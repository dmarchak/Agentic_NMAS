#!/usr/bin/env bash
# C1916: Loki is published on loopback only. Docker-published ports bypass ufw, and Loki was
# published on 0.0.0.0:3100 and [::]:3100, so anyone on the LAN could read and push logs with no
# authentication (the operator's check from the laptop, 2026-10-27: /ready answered "ready").
# Every client is local (read on the host 2026-10-27 ~08:0x UTC): Alloy pushes to
# localhost:3100, Grafana's Loki datasource reads http://localhost:3100, Mercury's loki_url is
# http://127.0.0.1:3100; Loki's own MinIO traffic leaves the container. So the container is made
# again with `-p 127.0.0.1:3100:3100`, everything else as it was (image, config, data, restart
# policy, user, and its two S3 variables, copied from the old container into an owner-only env
# file and never printed). The old container is kept, stopped, as loki-before-c1916 until
# `finish`; a failed step or check puts it back.
# Run on the NMAS host, as the operator's own user (sudo is asked for docker and the env file):
#     bash <checkout>/scripts/host-steps/c1916-loki-loopback.sh            # apply, then check
#     bash <checkout>/scripts/host-steps/c1916-loki-loopback.sh check      # checks only
#     bash <checkout>/scripts/host-steps/c1916-loki-loopback.sh rollback   # back to 0.0.0.0:3100
#     bash <checkout>/scripts/host-steps/c1916-loki-loopback.sh finish     # remove the kept old one
# After apply, from the laptop: curl -m 5 http://<nmas-host>:3100/ready must be refused.
. "$(dirname "$0")/lib.sh"

MODE=${1:-apply}
IMAGE=grafana/loki:3.3.2
ENVF=/etc/loki/loki-s3.env
OLD=loki-before-c1916
export IMAGE ENVF OLD
RUN_LOOPBACK='sudo docker run -d --name loki --restart unless-stopped -p 127.0.0.1:3100:3100 \
  -v /etc/loki/local-config.yaml:/etc/loki/local-config.yaml:ro -v /var/lib/loki:/loki \
  --env-file "$ENVF" "$IMAGE" -config.file=/etc/loki/local-config.yaml -config.expand-env=true'
PUT_BACK='sudo docker rm -f loki 2>/dev/null; sudo docker rename "$OLD" loki && sudo docker start loki'
READY='for i in $(seq 1 45); do r=$(curl -s -m 2 http://127.0.0.1:3100/ready); [ "$r" = ready ] && break; sleep 2; done; echo "$r"'

plan "run as the operator's own user, not root" \
     "Loki answers ready on 127.0.0.1:3100" \
     "Loki is published on loopback only" \
     "Loki holds its two S3 variables" \
     "Alloy's pushes are accepted (no failed batch in 2 minutes)" \
     "a line arrived in the last 2 minutes" \
     "the old container is kept, stopped, for rollback"
not_root

case $MODE in
apply)
    check "Loki holds its two S3 variables" eq "2" \
        'sudo docker inspect loki --format "{{range .Config.Env}}{{println .}}{{end}}" | grep -c "^LOKI_S3_"'
    step "copy the S3 variables into an owner-only env file (values never printed)" \
        'sudo sh -c "umask 077; docker inspect loki --format \"{{range .Config.Env}}{{println .}}{{end}}\" | grep \"^LOKI_S3_\" > \"$ENVF\"" && sudo test -s "$ENVF" && echo "names: $(sudo cut -d= -f1 "$ENVF" | tr "\n" " ")"'
    step "stop Loki and keep it as $OLD" 'sudo docker stop loki >/dev/null && sudo docker rename loki "$OLD"'
    ON_FAIL=$PUT_BACK
    ON_FAIL_WHAT="put the old container back (0.0.0.0:3100, as before)"
    step "start Loki published on 127.0.0.1:3100 only" "$RUN_LOOPBACK"
    ;;
rollback)
    step "put the old container back" "$PUT_BACK"
    check "Loki answers ready on 127.0.0.1:3100" eq "ready" "$READY"
    not_asked "Loki is published on loopback only" "rollback publishes 0.0.0.0:3100 again"
    not_asked "Loki holds its two S3 variables" "the old container holds them"
    not_asked "Alloy's pushes are accepted (no failed batch in 2 minutes)" "asked by apply and check"
    not_asked "a line arrived in the last 2 minutes" "asked by apply and check"
    not_asked "the old container is kept, stopped, for rollback" "it is the running one again"
    summary
    exit 0
    ;;
finish)
    step "remove the kept old container" 'sudo docker rm "$OLD"'
    not_asked "Loki answers ready on 127.0.0.1:3100" "finish only removes the old container"
    not_asked "Loki is published on loopback only" "finish only removes the old container"
    not_asked "Loki holds its two S3 variables" "finish only removes the old container"
    not_asked "Alloy's pushes are accepted (no failed batch in 2 minutes)" "finish only removes the old container"
    not_asked "a line arrived in the last 2 minutes" "finish only removes the old container"
    not_asked "the old container is kept, stopped, for rollback" "finish only removes the old container"
    summary
    exit 0
    ;;
check) ;;
*) echo "usage: $0 [apply|check|rollback|finish]"; exit 2 ;;
esac

check "Loki answers ready on 127.0.0.1:3100" eq "ready" "$READY"
check "Loki is published on loopback only" eq "127.0.0.1:3100" \
    'sudo docker port loki 3100/tcp | sort -u | tr -d "\n"'
check "Loki holds its two S3 variables" eq "2" \
    'sudo docker inspect loki --format "{{range .Config.Env}}{{println .}}{{end}}" | grep -c "^LOKI_S3_"'
echo "== waiting 120 s for Alloy's next pushes"
sleep 120
check "Alloy's pushes are accepted (no failed batch in 2 minutes)" lacks "error sending batch" \
    'sudo journalctl -u alloy --since "-2min" --no-pager'
check "a line arrived in the last 2 minutes" re '"values":\[\[' \
    'curl -sG -m 10 http://127.0.0.1:3100/loki/api/v1/query_range --data-urlencode "query={job=~\".+\"}" --data-urlencode "limit=1" --data-urlencode "start=$(( ($(date +%s) - 120) * 1000000000 ))"'
check "the old container is kept, stopped, for rollback" eq "exited" \
    'sudo docker inspect "$OLD" --format "{{.State.Status}}"'
summary
