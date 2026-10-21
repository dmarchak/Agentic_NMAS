#!/bin/bash
# Pin each lab VM's kernel kvm-pit thread to its node's CPUs: a switch's to its own CPU, a
# router's to the others' set. Run by lab-pin-pit.timer as root (installed once by
# install.sh); idempotent; logs to the journal.
#
# Why (C1485, the tuning sprint, 2026-10-21): containerlab's cpu-set pins each node's container,
# its qemu and every thread. The kvm-pit threads that inject the vIOS switches' timer ticks are
# KERNEL threads (parent kthreadd, cgroup root), outside every container, so cpu-set cannot reach
# them, and a redeploy makes new ones.
#
# Each thread is matched to its VM (pinning-lib.sh `pit_map`), and a switch's match is
# confirmed by behaviour: its PIT ticks about 1,000 times a second, a router's not at all
# (measured on all twelve, 2026-10-21). A switch whose match does not tick is not trusted: every
# PIT thread then goes to the switches' set, as one shared set, and the journal says so.
set -u
here=$(dirname "$(readlink -f "$0")")
. "$here/pinning.conf"
. "$here/pinning-lib.sh"
log() { logger -t lab-pin-pit "$*"; echo "$*"; }
pin() { taskset -pc "$1" "$2" >/dev/null 2>&1; }
[ "$(id -u)" = 0 ] || { echo "run as root (the timer does)"; exit 1; }

map=$(pit_map)
[ -n "$map" ] || { log "no lab VM found: nothing to pin"; exit 0; }
trusted=1
while read -r node pid pit; do
  cpu=$(switch_cpu "$node")
  [ -n "$cpu" ] || continue
  if [ "$pit" = none ]; then log "switch $node (qemu $pid): no kvm-pit thread matched"; trusted=0; continue; fi
  t=$(ticks "$pit")
  [ "$t" -ge 200 ] || { log "switch $node: matched kvm-pit $pit ticks $t/s, not a switch's; not trusted"; trusted=0; }
done <<<"$map"

n=0
if [ "$trusted" = 1 ]; then
  while read -r node pid pit; do
    [ "$pit" = none ] && continue
    cpu=$(switch_cpu "$node")
    want=${cpu:-$OTHERS_SET}
    have=$(taskset -pc "$pit" 2>/dev/null | sed 's/.*: //')
    [ "$have" = "$want" ] && continue
    if pin "$want" "$pit"; then n=$((n + 1)); log "$node: kvm-pit $pit -> CPUs $want (was $have)";
    else log "$node: kvm-pit $pit could not be pinned to $want"; fi
  done <<<"$map"
else
  for t in $(ps -eLo tid,comm | awk '$2 ~ /^kvm-pit/ {print $1}'); do
    have=$(taskset -pc "$t" 2>/dev/null | sed 's/.*: //')
    [ "$have" = "$SWITCH_SET" ] && continue
    pin "$SWITCH_SET" "$t" && n=$((n + 1))
  done
  log "the map was not trusted: every kvm-pit thread pinned to the switches' set $SWITCH_SET ($n moved)"
fi
[ "$n" = 0 ] || log "pinned $n kvm-pit thread(s)"
exit 0
