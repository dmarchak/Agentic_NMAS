# Shared by pin-pit-threads.sh and check-pinning.sh (sourced; reads pinning.conf's values).
#
# pit_map: prints "<node> <qemu pid> <kvm-pit tid>" for every lab node with a qemu, one line
# each, the kvm-pit thread matched to its VM. The kernel names it `kvm-pit/<n>`, n being the
# qemu's pid INSIDE its container, which two containers can share. It creates it right after its
# qemu (KVM_CREATE_PIT2 at start-up), so each qemu, in pid order, takes the `kvm-pit/<n>` thread
# with the lowest tid above its own pid that no earlier qemu took (measured 2026-10-21: s1
# 963866 -> 964075, s2 964135 -> 964184, s3 964190 -> 964235, s4 963876 -> 964044).
pit_map() {
  local node pid ns
  declare -A taken=()
  for node in $(lab_nodes); do
    pid=$(docker top "$LAB_PREFIX-$node" -eo pid,comm 2>/dev/null | awk '/qemu/{print $1; exit}')
    [ -n "$pid" ] || continue
    ns=$(awk '/^NSpid:/{print $NF}' "/proc/$pid/status" 2>/dev/null)
    echo "$pid $ns $node"
  done | sort -n | while read -r pid ns node; do
    local best=""
    for t in $(ps -eLo tid,comm | awk -v n="kvm-pit/$ns" '$2 == n {print $1}' | sort -n); do
      [ "$t" -gt "$pid" ] && [ -z "${taken[$t]:-}" ] && { best=$t; break; }
    done
    [ -n "$best" ] && taken[$best]=1
    echo "$node $pid ${best:-none}"
  done
}

# lab_nodes: every node pinning.conf names (switches first).
lab_nodes() {
  local pair
  for pair in $SWITCHES; do echo "${pair%%:*}"; done
  for n in $OTHERS; do echo "$n"; done
}

# switch_cpu <node>: the switch's own CPU, or nothing for a node that is not a switch.
switch_cpu() {
  local pair
  for pair in $SWITCHES; do [ "${pair%%:*}" = "$1" ] && { echo "${pair##*:}"; return; }; done
}

# ticks <tid>: the thread's wake-ups over one second (a switch's PIT ticks about 1,000 times).
ticks() {
  local a b
  a=$(awk '{print $3}' "/proc/$1/schedstat" 2>/dev/null) || { echo 0; return; }
  sleep 1
  b=$(awk '{print $3}' "/proc/$1/schedstat" 2>/dev/null) || { echo 0; return; }
  echo $((b - a))
}
