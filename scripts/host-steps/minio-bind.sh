#!/usr/bin/env bash
# C749's follow-up (the operator, 2026-10-13): "a host step binding MinIO's console (9001) to
# 127.0.0.1 and limiting the API (9000) to the addresses that need it, with matching ufw rules".
# On the NMAS host, as the operator's own user (sudo asked for):
#     bash <checkout>/scripts/host-steps/minio-bind.sh
#
# Measured before this was written (read-only, 2026-10-13, 12 samples over 60 s of the
# established connections to 9000 and 9001): every client is this host itself (Mercury, Thanos,
# telegraf and the hourly lake archive, by its LAN address, which the kernel delivers over the
# loopback interface, and ufw accepts loopback before any rule) or the Loki container on
# Docker's default bridge (docker0). Nothing on the LAN connected; the replica (minio-dr) is
# written TO by this MinIO and never connects in. ufw is active with incoming ALLOWED by
# default, so a port is closed only by a rule.
#
#   1. a dated copy of /etc/default/minio (root's, mode 700);
#   2. MINIO_OPTS: the console on 127.0.0.1:9001 (the API stays on :9000, since its clients
#      name this host's LAN address);
#   3. ufw, in order: 9000 allowed in on docker0 from docker0's network (Loki), then 9000 and
#      9001 denied from anywhere else (logged: a refused client shows as [UFW BLOCK]);
#   4. MinIO restarted; the proof: the console listens on loopback only, the API answers here,
#      Mercury's key, Thanos and Loki still reach it, and no [UFW BLOCK] to 9000 from docker0.
# Any failure after step 2 starts puts the file back, deletes the rules this step added, and
# restarts MinIO (ON_FAIL). The console is then reached through an SSH tunnel, for example
# `ssh -L 9001:127.0.0.1:9001 <nmas-host>` and http://127.0.0.1:9001 on the laptop.
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
ENVFILE=/etc/default/minio
OBJSTORE=/etc/thanos/objstore.yml
LOKI=${LOKI_CONTAINER:-loki}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COPY=/var/backups/minio/bind-$STAMP
SINCE=$(date -u '+%Y-%m-%d %H:%M:%S')
WANT_BEFORE='"--address :9000 --console-address :9001"'
WANT_AFTER='"--address :9000 --console-address 127.0.0.1:9001"'
# docker0's network, from its address (for example 172.17.0.1/16 -> 172.17.0.0/16).
DOCKNET=$(ip -4 -o addr show docker0 2>/dev/null | awk '{print $4}' | python3 -c "import sys, ipaddress; v = sys.stdin.read().strip(); print(ipaddress.ip_interface(v).network if v else '')")
RULE_LOKI="allow in on docker0 from $DOCKNET to any port 9000 proto tcp comment 'MinIO API: Loki on docker0 (C749)'"
RULE_API="deny log 9000/tcp comment 'MinIO API: this host and docker0 only (C749)'"
RULE_CONSOLE="deny log 9001/tcp comment 'MinIO console: loopback only (C749)'"
export PYTHONDONTWRITEBYTECODE=1 CHECKOUT PY ENVFILE OBJSTORE LOKI COPY SINCE WANT_BEFORE WANT_AFTER DOCKNET RULE_LOKI RULE_API RULE_CONSOLE

plan "run as the operator's own user, not root" \
     "this is the NMAS host: minio.service, ufw active, docker0" \
     "MINIO_OPTS is the one this step was written against" \
     "Loki runs on docker0's network" \
     "ufw holds no rule for 9000 or 9001 yet" \
     "the dated copy reads back the same as the original" \
     "MINIO_OPTS puts the console on loopback" \
     "ufw holds the three rules, the allow first" \
     "MinIO answers after its restart" \
     "the console listens on loopback only, the API on every address" \
     "Mercury's own key still answers" \
     "Thanos still reads its bucket" \
     "Loki reaches MinIO and nothing from docker0 was blocked"

not_root
check "this is the NMAS host: minio.service, ufw active, docker0" eq "yes" \
    'systemctl cat minio.service >/dev/null 2>&1 && sudo ufw status | grep -q "^Status: active" && [ -n "$DOCKNET" ] && [ -x "$PY" ] && echo yes || echo no'
check "MINIO_OPTS is the one this step was written against" eq "$WANT_BEFORE" \
    'sudo grep -E "^MINIO_OPTS=" "$ENVFILE" | cut -d= -f2-'
check "Loki runs on docker0's network" eq "yes" \
    'ip=$(sudo docker inspect -f "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}" "$LOKI" | awk "{print \$1}"); python3 -c "import ipaddress, sys; print(\"yes\" if ipaddress.ip_address(sys.argv[1]) in ipaddress.ip_network(sys.argv[2]) else \"no: \" + sys.argv[1])" "$ip" "$DOCKNET"'
check "ufw holds no rule for 9000 or 9001 yet" eq "0" \
    'sudo ufw status | grep -cE "^(9000|9001)(/tcp)?[[:space:]]|port 900[01]" || true'

step "a dated copy of MinIO's environment file (root's, mode 700)" \
    'sudo install -d -m 700 "$COPY" && sudo cp -a "$ENVFILE" "$COPY/"'
check "the dated copy reads back the same as the original" rc0 "" 'sudo cmp "$ENVFILE" "$COPY/minio"'

ON_FAIL='sudo cp -p "$COPY/minio" "$ENVFILE"; for r in "$RULE_CONSOLE" "$RULE_API" "$RULE_LOKI"; do eval "sudo ufw delete ${r% comment *}" >/dev/null 2>&1; done; sudo systemctl restart minio; echo "ufw rules for 9000 or 9001 left: $(sudo ufw status | grep -cE "900[01]" || true)"'
ON_FAIL_WHAT="MinIO's environment file put back, this step's ufw rules deleted, MinIO restarted"
step "MINIO_OPTS: the console on 127.0.0.1:9001" \
    'sudo python3 -c "import os, re, sys; p, want = sys.argv[1], sys.argv[2]; st = os.stat(p); t = open(p).read(); n = re.subn(r\"(?m)^MINIO_OPTS=.*$\", lambda m: \"MINIO_OPTS=\" + want, t); assert n[1] == 1, n[1]; tmp = p + \".tmp\"; open(tmp, \"w\").write(n[0]); os.chown(tmp, st.st_uid, st.st_gid); os.chmod(tmp, st.st_mode & 0o7777); os.replace(tmp, p)" "$ENVFILE" "$WANT_AFTER"'
check "MINIO_OPTS puts the console on loopback" eq "$WANT_AFTER" \
    'sudo grep -E "^MINIO_OPTS=" "$ENVFILE" | cut -d= -f2-'
step "ufw: 9000 from docker0 allowed, then 9000 and 9001 denied (logged)" \
    'eval "sudo ufw $RULE_LOKI" && eval "sudo ufw $RULE_API" && eval "sudo ufw $RULE_CONSOLE"'
check "ufw holds the three rules, the allow first" eq "ALLOW-9000 DENY-9000 DENY-9001" \
    'sudo ufw status | awk "/900[01]/ && !/\\(v6\\)/ {split(\$1, p, \"/\"); a = (\$0 ~ /ALLOW/) ? \"ALLOW\" : \"DENY\"; port = (\$0 ~ /9001/) ? \"9001\" : \"9000\"; printf \"%s%s-%s\", sep, a, port; sep = \" \"}"'
step "MinIO restarted" 'sudo systemctl restart minio'
check "MinIO answers after its restart" rc0 "" \
    'for i in $(seq 1 30); do curl -sf "http://127.0.0.1:9000/minio/health/live" && exit 0; sleep 1; done; exit 1'
# The console binds after the API answers (C756: read 1 s after the health check, 9001 had no
# listener yet; MinIO's own log said "WebUI: http://127.0.0.1:9001"). Read until it holds, at most
# 15 s, then say what was last seen.
check "the console listens on loopback only, the API on every address" eq "9000:* 9001:127.0.0.1" \
    'for i in $(seq 1 15); do got=$(sudo ss -ltnp | awk "/\"minio\"/ {print \$4}" | python3 -c "import sys; got = {}; [got.setdefault(a.rsplit(\":\", 1)[1], set()).add(a.rsplit(\":\", 1)[0]) for a in sys.stdin.read().split()]; c = sorted(got.get(\"9001\", [])); print(\"9000:\" + (\"*\" if \"*\" in got.get(\"9000\", set()) else \",\".join(sorted(got.get(\"9000\", [])))) + \" 9001:\" + \",\".join(c))"); [ "$got" = "9000:* 9001:127.0.0.1" ] && break; sleep 1; done; echo "$got"'
check "Mercury's own key still answers" eq "True" \
    'cd "$CHECKOUT" && "$PY" -c "from modules.integrations.s3_archive import S3ArchiveIntegration as S; print(S().test_connection(write=False).get(\"ok\"))"'
check "Thanos still reads its bucket" rc0 "" \
    'sudo -u prometheus thanos tools bucket ls --objstore.config-file="$OBJSTORE" >/dev/null 2>&1'
# Loki flushes about one object every 20 s (27 in the 10 minutes measured): one written since the
# change is the proof it still reaches MinIO; the bound is about 2.5x a minute's wait.
check "Loki reaches MinIO and nothing from docker0 was blocked" eq "loki wrote: yes; blocked from docker0: 0" \
    'w=no; for i in $(seq 1 30); do [ "$(sudo find /var/lib/minio/data/loki -name xl.meta -newermt "$SINCE UTC" | head -1)" ] && { w=yes; break; }; sleep 5; done; b=$(sudo journalctl -k --since "$SINCE UTC" --no-pager | grep "UFW BLOCK" | grep -E "DPT=900[01]" | grep -cE "SRC=$(echo "$DOCKNET" | cut -d. -f1-2)\." || true); echo "loki wrote: $w; blocked from docker0: $b"'
ON_FAIL=""
echo "== The dated copy: $COPY. Blocks from elsewhere show as [UFW BLOCK] ... DPT=9000 in the kernel log."
summary
