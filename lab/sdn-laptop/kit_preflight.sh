#!/bin/bash
# The laptop kit's preflight (docs/LAB9_LAPTOP_RUN.md): one PASS or FAIL line per check, then the
# count. Run by `kit preflight`, which sets KIT_HOME and sources kit.env. Read-only: it changes
# nothing on the laptop, the lab or Mercury. Exit status: the number of FAILs.
set -u
: "${KIT_HOME:?}" "${MERCURY_PORT:=5080}" "${NETBOX_PORT:=8001}" "${OPENFLOW_PORT:=6653}"
: "${CONTROLLER_REST_PORT:=8080}" "${LAB_IF:=}" "${CONTROLLER_ADDR:=}"
fails=0
line() {                                    # line PASS|FAIL name detail
  printf '%s %s%s\n' "$1" "$2" "${3:+: $3}"
  [ "$1" = PASS ] || fails=$((fails + 1))
}
tcp() {                                     # tcp HOST PORT: a connect within 3 s
  timeout 3 bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$1" "$2" 2>/dev/null
}

# 1. Docker
if docker info >/dev/null 2>&1; then line PASS "Docker up" "$(docker version -f '{{.Server.Version}}' 2>/dev/null)"
else line FAIL "Docker up" "docker info failed (is the daemon running, and is the user in the docker group?)"; fi

# 2. NetBox answers on loopback
code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:$NETBOX_PORT/login/" 2>/dev/null)
if [ "$code" = 200 ]; then line PASS "NetBox answers" "127.0.0.1:$NETBOX_PORT/login/ 200"
else line FAIL "NetBox answers" "127.0.0.1:$NETBOX_PORT/login/ gave ${code:-no answer} (kit start brings it up)"; fi

# 3. Mercury's /health says ready, and it listens on loopback only
health=$(curl -s -m 5 -H "Host: 127.0.0.1:$MERCURY_PORT" "http://127.0.0.1:$MERCURY_PORT/health" 2>/dev/null)
ready=$(printf '%s' "$health" | python3 -I -c 'import json,sys
try: b=json.load(sys.stdin)
except ValueError: print("no answer"); raise SystemExit
print("ready" if b.get("ready") is True else ("no ready field (a commit before C2465)" if "ready" not in b else "not ready: " + str(b.get("not_ready"))))' 2>/dev/null)
if [ "$ready" = ready ]; then line PASS "Mercury ready" "/health ready on 127.0.0.1:$MERCURY_PORT"
else line FAIL "Mercury ready" "${ready:-no answer} on 127.0.0.1:$MERCURY_PORT"; fi
listen=$(ss -ltnH "sport = :$MERCURY_PORT" 2>/dev/null | awk '{print $4}' | sed 's/:[0-9]*$//' | sort -u | tr '\n' ' ')
if [ -z "$listen" ]; then line FAIL "Mercury on loopback only" "nothing listens on port $MERCURY_PORT"
elif printf '%s' "$listen" | grep -qvE '^(127\.0\.0\.1|\[::1\]| )+$'; then line FAIL "Mercury on loopback only" "listening on $listen"
else line PASS "Mercury on loopback only" "$listen"; fi

# 4. The controller (the lab's controller server, reached over the lab leg)
if [ -z "$CONTROLLER_ADDR" ]; then line FAIL "controller reachable" "CONTROLLER_ADDR is not set in $KIT_HOME/kit.env"
else
  if tcp "$CONTROLLER_ADDR" "$OPENFLOW_PORT"; then line PASS "controller OpenFlow port" "$CONTROLLER_ADDR:$OPENFLOW_PORT connects"
  else line FAIL "controller OpenFlow port" "$CONTROLLER_ADDR:$OPENFLOW_PORT does not connect in 3 s"; fi
  if tcp "$CONTROLLER_ADDR" "$CONTROLLER_REST_PORT"; then line PASS "controller REST port" "$CONTROLLER_ADDR:$CONTROLLER_REST_PORT connects"
  else line FAIL "controller REST port" "$CONTROLLER_ADDR:$CONTROLLER_REST_PORT does not connect in 3 s"; fi
fi

# 5. The lab interface is up, with carrier, and carries no default route
if [ -z "$LAB_IF" ]; then line FAIL "lab interface up" "LAB_IF is not set in $KIT_HOME/kit.env"
elif ! ip link show "$LAB_IF" >/dev/null 2>&1; then line FAIL "lab interface up" "$LAB_IF does not exist"
else
  state=$(ip -br link show "$LAB_IF" | awk '{print $2}')
  if ip link show "$LAB_IF" | grep -q LOWER_UP; then line PASS "lab interface up" "$LAB_IF $state, carrier"
  else line FAIL "lab interface up" "$LAB_IF $state, no carrier (is the lab cable in?)"; fi
  addr=$(ip -br addr show "$LAB_IF" | awk '{$1=$2=""; print $0}' | xargs)
  if [ -n "$addr" ]; then line PASS "lab interface addressed" "$LAB_IF $addr"
  else line FAIL "lab interface addressed" "$LAB_IF has no address"; fi
fi

# 6. The default route is the Wi-Fi's, and only the Wi-Fi's
defs=$(ip route show default | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | sort -u)
if [ -z "$defs" ]; then line FAIL "default route via Wi-Fi" "no default route"
else
  bad=""; for d in $defs; do [ -d "/sys/class/net/$d/wireless" ] || bad="$bad $d"; done
  if [ -n "$bad" ]; then line FAIL "default route via Wi-Fi" "a default route via a wired interface:$bad"
  else line PASS "default route via Wi-Fi" "$(echo $defs)"; fi
fi
d6=$(ip -6 route show default | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | sort -u)
bad6=""; for d in $d6; do [ -d "/sys/class/net/$d/wireless" ] || bad6="$bad6 $d"; done
if [ -n "$bad6" ]; then line FAIL "IPv6 default route via Wi-Fi" "a default route via a wired interface:$bad6"
else line PASS "IPv6 default route via Wi-Fi" "${d6:-none}"; fi

# 7. IP forwarding off, IPv4 and IPv6
f4=$(cat /proc/sys/net/ipv4/ip_forward); f6=$(cat /proc/sys/net/ipv6/conf/all/forwarding)
if [ "$f4" = 0 ] && [ "$f6" = 0 ]; then line PASS "IP forwarding off" "ipv4 $f4, ipv6 $f6"
else line FAIL "IP forwarding off" "ipv4 $f4, ipv6 $f6 (Docker sets ipv4 forwarding on: docs/LAB9_LAPTOP_RUN.md section 7, step 1)"; fi

echo "preflight: $fails FAIL"
exit "$fails"
