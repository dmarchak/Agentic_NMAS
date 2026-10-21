#!/bin/bash
# Read-only, on the lab host: are the switches still pinned? (C1485: losing the pinning brings
# the stalls back silently, so the check says so.) It judges where the threads RUN, whichever
# way they were pinned:
#   - each switch's qemu threads exactly on its own CPU;
#   - every other node's processes within the others' set;
#   - every kvm-pit thread within the switches' set.
# Each line says whether the container's cpuset declares it (rcn-lab1.clab.yml's cpu-set,
# reapplied by every deploy) or it is pinned by hand (taskset, lost at the next deploy).
# Exits 0 when all hold, 1 naming what was lost, 2 when the lab is not deployed.
set -u
here=$(dirname "$(readlink -f "$0")")
. "$here/pinning.conf"
lost=0
cpuset() { docker inspect -f '{{.HostConfig.CpusetCpus}}' "$LAB_PREFIX-$1" 2>/dev/null; }
how() { [ "$(cpuset "$1")" = "$2" ] && echo "declared" || echo "by hand"; }
# Every CPU a list like "0-19" or "20,22" names, one per line.
expand() { tr ',' '\n' <<<"$1" | awk -F- '{ if (NF == 2) for (i = $1; i <= $2; i++) print i; else print $1 }'; }
within() { # within <affinity> <set>: every CPU of the affinity is in the set
  local a s
  a=$(expand "$1" | sort); s=$(expand "$2" | sort)       # comm compares lexical order
  [ -z "$(comm -23 <(echo "$a") <(echo "$s"))" ]
}
pids_of() { docker top "$LAB_PREFIX-$1" -eo pid 2>/dev/null | tail -n +2; }
for pair in $SWITCHES; do
  node=${pair%%:*}; cpu=${pair##*:}
  [ -n "$(docker ps -q -f name="^$LAB_PREFIX-$node$")" ] || { echo "NOT DEPLOYED: $node"; exit 2; }
  pid=$(docker top "$LAB_PREFIX-$node" -eo pid,comm | awk '/qemu/{print $1; exit}')
  aff=$(for t in /proc/"$pid"/task/*; do taskset -pc "${t##*/}" | sed 's/.*: //'; done | sort -u | tr '\n' ' ')
  if [ "$aff" = "$cpu " ]; then echo "ok    $node: qemu threads on CPU $cpu ($(how "$node" "$cpu"))";
  else echo "LOST  $node: qemu threads on '$aff', want CPU $cpu"; lost=1; fi
done
for node in $OTHERS; do
  [ -n "$(docker ps -q -f name="^$LAB_PREFIX-$node$")" ] || continue
  bad=""
  for p in $(pids_of "$node"); do
    for t in /proc/"$p"/task/*; do
      a=$(taskset -pc "${t##*/}" 2>/dev/null | sed 's/.*: //')
      [ -n "$a" ] && ! within "$a" "$OTHERS_SET" && bad="$bad ${t##*/}:$a"
    done
  done
  if [ -z "$bad" ]; then echo "ok    $node: within CPUs $OTHERS_SET ($(how "$node" "$OTHERS_SET"))";
  else echo "LOST  $node: threads outside $OTHERS_SET:$bad"; lost=1; fi
done
for t in $(ps -eLo tid,comm | awk '$2 ~ /^kvm-pit/ {print $1}'); do
  aff=$(taskset -pc "$t" | sed 's/.*: //')
  within "$aff" "$SWITCH_SET" || { echo "LOST  kvm-pit thread $t on '$aff', want within $SWITCH_SET"; lost=1; }
done
if [ "$lost" = 0 ]; then echo "PINNING HOLDS"; else echo "PINNING LOST: run lab/pinning/pin-pit-threads.sh, or redeploy with the lab file's cpu-set"; fi
exit "$lost"
