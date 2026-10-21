#!/bin/bash
# Read-only, on the lab host: are the switches still pinned? (C1485: losing the pinning brings
# the stalls back silently, so the check says so.) Four parts, each line ok or LOST:
#   1. the timer that pins the kernel's kvm-pit threads is active, and its last run succeeded;
#   2. the lab file declares each node's cpu-set (so the next deploy applies it);
#   3. each container applies it, and where its threads run: a switch's qemu threads exactly
#      on its own CPU, every other node's processes within the others' set;
#   4. each switch's own kvm-pit thread on its CPU (matched as the timer matches it), every other
#      kvm-pit thread within the others' set.
# Exits 0 when all hold, 1 naming what was lost, 2 when the lab is not deployed.
set -u
here=$(dirname "$(readlink -f "$0")")
. "$here/pinning.conf"
. "$here/pinning-lib.sh"
lost=0
say() { echo "$1"; [ "${1%% *}" = "LOST" ] && lost=1; return 0; }
expand() { tr ',' '\n' <<<"$1" | awk -F- '{ if (NF == 2) for (i = $1; i <= $2; i++) print i; else print $1 }'; }
within() { [ -z "$(comm -23 <(expand "$1" | sort) <(expand "$2" | sort))" ]; }

# 1. The timer.
if systemctl is-active --quiet lab-pin-pit.timer; then
  res=$(systemctl show lab-pin-pit.service -p Result --value 2>/dev/null)
  if [ "$res" = success ]; then say "ok    timer: lab-pin-pit.timer active, its last run $res";
  else say "LOST  timer: lab-pin-pit.timer active, its last run '$res'"; fi
else
  say "LOST  timer: lab-pin-pit.timer is not active (install: lab/pinning/install.sh)"
fi

# 2. The lab file.
if [ -r "$LAB_FILE" ]; then
  declared=$(python3 - "$LAB_FILE" <<'PY'
import sys, yaml
t = yaml.safe_load(open(sys.argv[1]))["topology"]
kinds = t.get("kinds") or {}
for name, n in (t.get("nodes") or {}).items():
    s = n.get("cpu-set") or (kinds.get(n.get("kind")) or {}).get("cpu-set") or ""
    print(name, s)
PY
)
  for node in $(lab_nodes); do
    want=$(switch_cpu "$node"); want=${want:-$OTHERS_SET}
    got=$(awk -v n="$node" '$1 == n {print $2}' <<<"$declared")
    if [ "$got" = "$want" ]; then say "ok    $node: the lab file declares cpu-set $got";
    else say "LOST  $node: the lab file declares cpu-set '$got', want $want"; fi
  done
else
  say "LOST  the lab file $LAB_FILE cannot be read"
fi

# 3. The containers.
for node in $(lab_nodes); do
  [ -n "$(docker ps -q -f name="^$LAB_PREFIX-$node$")" ] || {
    [ -n "$(switch_cpu "$node")" ] && { echo "NOT DEPLOYED: $node"; exit 2; }; continue; }
  want=$(switch_cpu "$node"); want=${want:-$OTHERS_SET}
  applied=$(docker inspect -f '{{.HostConfig.CpusetCpus}}' "$LAB_PREFIX-$node" 2>/dev/null)
  bad=""
  for p in $(docker top "$LAB_PREFIX-$node" -eo pid 2>/dev/null | tail -n +2); do
    for t in /proc/"$p"/task/*; do
      a=$(taskset -pc "${t##*/}" 2>/dev/null | sed 's/.*: //')
      [ -n "$a" ] && ! within "$a" "$want" && bad="$bad ${t##*/}:$a"
    done
  done
  how=$([ "$applied" = "$want" ] && echo "applied by the container" || echo "by hand, the container's cpuset '$applied'")
  if [ -z "$bad" ]; then say "ok    $node: runs within CPUs $want ($how)";
  else say "LOST  $node: threads outside $want:$bad ($how)"; fi
done

# 4. The kvm-pit threads.
while read -r node pid pit; do
  [ "$pit" = none ] && continue
  want=$(switch_cpu "$node"); want=${want:-$OTHERS_SET}
  a=$(taskset -pc "$pit" 2>/dev/null | sed 's/.*: //')
  if within "$a" "$want"; then say "ok    $node: kvm-pit $pit on $a";
  else say "LOST  $node: kvm-pit $pit on '$a', want within $want"; fi
done < <(pit_map)

if [ "$lost" = 0 ]; then echo "PINNING HOLDS"; else echo "PINNING LOST: see the LOST lines"; fi
exit "$lost"
