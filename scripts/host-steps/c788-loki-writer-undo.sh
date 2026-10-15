#!/usr/bin/env bash
# C788's undo, by hand: puts back what c788-loki-writer-rotate.sh changed, from the dated copy
# it made (the rotation runs the same undo itself when it fails after MinIO's secret changes).
# The operator's, on the NMAS host, as their own user (sudo asked once):
#     bash <checkout>/scripts/host-steps/c788-loki-writer-undo.sh /var/backups/loki/writer-rotate-<stamp>
#
# loki-writer's OLD key set again in MinIO (MinIO's root password asked, hidden; the old key read
# from the copy by the rotation's own helper, kept there, and handed to mc on its standard input,
# never printed), the copied configuration in place, the env file removed, and the container
# recreated as it was before the rotation. The policy (loki-only, C584's) is left as it is.
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
CONFIG=/etc/loki/local-config.yaml
ENVFILE=/etc/loki/loki-s3.env
MINIO_ENV=/etc/default/minio
IMAGE=grafana/loki:3.3.2
COPY=${1:-}
export PY CONFIG ENVFILE MINIO_ENV IMAGE COPY

# recreate: the container as it was before the rotation (the rotation's `recreate before`).
recreate() {
    sudo docker rm -f loki >/dev/null
    sudo docker run -d --name loki --restart unless-stopped -p 3100:3100 \
        -v /var/lib/loki:/loki -v /etc/loki/local-config.yaml:/etc/loki/local-config.yaml:ro \
        "$IMAGE" -config.file=/etc/loki/local-config.yaml >/dev/null
}
ready() {
    local i
    for i in $(seq 1 60); do
        curl -sf http://127.0.0.1:3100/ready >/dev/null && return 0
        sleep 2
    done
    return 1
}
export -f recreate ready

plan "run as the operator's own user, not root" \
     "the dated copy holds the configuration and the rotation's helper" \
     "MinIO's root answers as an admin" \
     "loki-writer's old key answers again" \
     "the configuration is the copy's again" \
     "the env file is gone" \
     "Loki ready, as before" \
     "the running Loki container is the one the rotation found"

not_root
check "the dated copy holds the configuration and the rotation's helper" eq "yes" \
    '[ -n "$COPY" ] && sudo test -s "$COPY/local-config.yaml" && sudo test -s "$COPY/keys.py" && echo yes || echo "no: name the copy, /var/backups/loki/writer-rotate-<stamp>"'
ENDPOINT=$(sudo "$PY" "$COPY/keys.py" endpoint "$COPY/local-config.yaml")
ROOT_USER=$(sudo grep -E '^MINIO_ROOT_USER=' "$MINIO_ENV" | head -1 | cut -d= -f2- | tr -d '"')
read -r -s -p "MinIO's root password, for $ROOT_USER (hidden): " ROOT_PW; echo
MC_HOST_lokiadm=$(printf '%s' "$ROOT_PW" | ROOT_USER=$ROOT_USER ENDPOINT=$ENDPOINT python3 -c "import sys, os, urllib.parse as u; print('http://' + u.quote(os.environ['ROOT_USER'], safe='') + ':' + u.quote(sys.stdin.read(), safe='') + '@' + os.environ['ENDPOINT'])")
unset ROOT_PW
export MC_HOST_lokiadm
check "MinIO's root answers as an admin" rc0 "" 'mc admin info lokiadm >/dev/null'

step "loki-writer's old key set again (on mc's standard input)" \
    'sudo "$PY" "$COPY/keys.py" old-to-mc "$COPY/local-config.yaml" | mc admin user add lokiadm >/dev/null'
check "loki-writer's old key answers again" eq "ANSWERED" \
    'sudo "$PY" "$COPY/keys.py" old-refused "$COPY/local-config.yaml"'
step "the copied configuration in place, the env file removed, the container as it was" \
    'sudo install -m 640 -o root -g 10001 "$COPY/local-config.yaml" "$CONFIG" && sudo rm -f "$ENVFILE" && recreate'
check "the configuration is the copy's again" rc0 "" 'sudo cmp "$CONFIG" "$COPY/local-config.yaml"'
check "the env file is gone" eq "gone" 'sudo test -e "$ENVFILE" && echo present || echo gone'
check "Loki ready, as before" rc0 "" 'ready'
check "the running Loki container is the one the rotation found" eq "grafana/loki:3.3.2 [-config.file=/etc/loki/local-config.yaml] 3100 /var/lib/loki:/loki /etc/loki/local-config.yaml:/etc/loki/local-config.yaml:ro unless-stopped bridge 10001 env-as-image" \
    'echo "$(sudo docker inspect loki --format "{{.Config.Image}} {{.Args}} {{range \$p, \$b := .HostConfig.PortBindings}}{{(index \$b 0).HostPort}}{{end}} {{join .HostConfig.Binds \" \"}} {{.HostConfig.RestartPolicy.Name}} {{.HostConfig.NetworkMode}} {{.Config.User}}") $([ "$(sudo docker inspect loki --format "{{json .Config.Env}}")" = "$(sudo docker image inspect "$IMAGE" --format "{{json .Config.Env}}")" ] && echo env-as-image || echo env-differs)"'
unset MC_HOST_lokiadm
summary
