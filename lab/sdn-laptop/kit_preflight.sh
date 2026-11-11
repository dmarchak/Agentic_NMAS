#!/bin/bash
# The laptop kit's preflight (docs/LAB9_LAPTOP_RUN.md): one PASS or FAIL line per check, then the
# count. Run by `kit preflight`, which sets KIT_HOME and sources kit.env. Read-only: it changes
# nothing on the laptop, the lab or Mercury. Exit status: the number of FAILs.
set -u
: "${KIT_HOME:?}" "${MERCURY_PORT:=5080}" "${NETBOX_PORT:=8001}" "${OPENFLOW_PORT:=6653}"
: "${CONTROLLER_REST_PORT:=8080}" "${LAB_IF:=}" "${CONTROLLER_ADDR:=}" "${PROMETHEUS_PORT:=9090}"
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
loopback_only() {   # loopback_only NAME PORT: kit_net_check.py's `listen` line, as this script's
  # The kit's loopback rule ("nothing is exposed to teammates"), judged on what LISTENS on the
  # port now (`ss`), whoever published it: every listening address must be exactly 127.0.0.1
  # or [::1], the set this line accepted before kit_net_check.py judged it, and nothing wider.
  local got; got=$(LISTEN=$(ss -ltnH "sport = :$2" 2>/dev/null) PORT="$2" LABEL="$1" \
    python3 -I "$(dirname "$0")/kit_net_check.py" listen)
  case "$got" in PASS*) line PASS "${got#PASS }" ;; *) line FAIL "${got#FAIL }" ;; esac
}
loopback_only Mercury "$MERCURY_PORT"

# 3b. The kit's Prometheus (compose.yml, pinned v2.53.0) answers on loopback, and is published
#     on loopback only: anything listening but 127.0.0.1 or [::1] (0.0.0.0, [::], a LAN
#     address, another 127.x address) is a FAIL naming it.
code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:$PROMETHEUS_PORT/-/ready" 2>/dev/null)
if [ "$code" = 200 ]; then line PASS "Prometheus answers" "127.0.0.1:$PROMETHEUS_PORT/-/ready 200"
else line FAIL "Prometheus answers" "127.0.0.1:$PROMETHEUS_PORT/-/ready gave ${code:-no answer} (kit start brings it up)"; fi
loopback_only Prometheus "$PROMETHEUS_PORT"

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

# 6. The lab profile (bound to LAB_IF, never-default and ignore-auto-dns for IPv4 and IPv6,
#    active once a cable is in), and the default route staying on WIFI_IF, IPv4 and IPv6.
: "${WIFI_IF:=}" "${LAB_PROFILE:=lab9}"
judge() {   # judge profile|routes: kit_net_check.py's one line, as this script's
  local got; got=$(python3 -I "$(dirname "$0")/kit_net_check.py" "$1")
  case "$got" in PASS*) line PASS "${got#PASS }" ;; *) line FAIL "${got#FAIL }" ;; esac
}
carrier=0; [ -n "$LAB_IF" ] && ip link show "$LAB_IF" 2>/dev/null | grep -q LOWER_UP && carrier=1
NM_PROFILE=$(nmcli -g connection.interface-name,ipv4.never-default,ipv6.never-default,ipv4.ignore-auto-dns,ipv6.ignore-auto-dns connection show "$LAB_PROFILE" 2>/dev/null) \
NM_ACTIVE=$(nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null) \
CARRIER=$carrier LAB_IF="$LAB_IF" LAB_PROFILE="$LAB_PROFILE" judge profile
if [ -z "$WIFI_IF" ]; then line FAIL "default route stays on the Wi-Fi" "WIFI_IF is not set in $KIT_HOME/kit.env"
else
  ROUTE4=$(ip route show default) ROUTE6=$(ip -6 route show default) \
  WIFI_IF="$WIFI_IF" LAB_IF="$LAB_IF" judge routes
fi

# 7. No forwarding to or from the lab interface: the lab9guard table in force (its rules and
#    counters), never the forwarding sysctl, which stays on for the laptop's containers and VMs.
#    Reading nftables needs root: `sudo -n` asks nothing, so run `sudo -v` first if this fails.
if [ -z "$LAB_IF" ]; then line FAIL "no forwarding to or from the lab interface" "LAB_IF is not set"
elif ! out=$(sudo -n nft -j list table inet lab9guard 2>&1); then
  line FAIL "no forwarding to or from the lab interface" "the lab9guard table could not be read: $(printf '%s' "$out" | head -c 120) (run sudo -v first, or kit start installs it)"
else
  got=$(printf '%s' "$out" | python3 -I "$(dirname "$0")/kit_guard_check.py" "$LAB_IF")
  case "$got" in PASS*) line PASS "${got#PASS }" ;; *) line FAIL "${got#FAIL }" ;; esac
fi

echo "preflight: $fails FAIL"
exit "$fails"
