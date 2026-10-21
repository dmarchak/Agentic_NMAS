#!/bin/bash
# Proxmox hookscript (post-start): pin each guest NUMA node's vCPUs to the host CPUs of the host
# node it is bound to, read at run time, never assumed (the operator, 2026-10-21):
#   - which vCPUs belong to which guest node, and which host node it is bound to: the VM's own
#     `numaN: cpus=A-B,hostnodes=H,...` lines (qm config);
#   - which host CPUs belong to host node H: /sys/devices/system/node/nodeH/cpulist;
#   - each vCPU's thread: QEMU's own answer (`info cpus` on the VM's monitor).
# Each vCPU is pinned to its node's whole CPU set, not one CPU each. Logged to the journal.
# Install (the operator): storage with `snippets` content, this file in it, then
#   qm set 100 --hookscript <storage>:snippets/phase3-vcpu-pin.sh
# Revert: qm set 100 --delete hookscript (and taskset each vCPU thread back, or restart the VM).
set -u
vmid="$1"; phase="$2"
[ "$phase" = "post-start" ] || exit 0
log() { logger -t "vcpu-pin[$vmid]" "$*"; echo "vcpu-pin[$vmid]: $*"; }

# vCPU index -> thread id, from QEMU (lines like "* CPU #0: thread_id=12345").
declare -A tid
while read -r idx t; do tid[$idx]=$t; done < <(
  echo "info cpus" | qm monitor "$vmid" 2>/dev/null |
    sed -n 's/.*CPU #\([0-9]\+\):.*thread_id=\([0-9]\+\).*/\1 \2/p')
[ "${#tid[@]}" -gt 0 ] || { log "no vCPU threads read from the monitor; nothing pinned"; exit 0; }

pinned=0
while IFS= read -r line; do
  # numa0: cpus=0-11,hostnodes=0,memory=32768,policy=bind
  cpus=$(sed -n 's/.*cpus=\([0-9;-]*\).*/\1/p' <<<"$line")
  node=$(sed -n 's/.*hostnodes=\([0-9]\+\).*/\1/p' <<<"$line")
  [ -n "$cpus" ] && [ -n "$node" ] || { log "skipped, unreadable: $line"; continue; }
  set_=$(cat "/sys/devices/system/node/node$node/cpulist" 2>/dev/null) ||
    { log "host node $node has no cpulist; skipped"; continue; }
  first=${cpus%-*}; last=${cpus#*-}
  for v in $(seq "$first" "$last"); do
    t=${tid[$v]:-}
    [ -n "$t" ] || { log "vCPU $v: no thread id"; continue; }
    if taskset -pc "$set_" "$t" >/dev/null; then pinned=$((pinned + 1));
    else log "vCPU $v (thread $t): taskset failed"; fi
  done
  log "guest vCPUs $cpus -> host node $node CPUs $set_"
done < <(qm config "$vmid" | grep -E '^numa[0-9]+:')
log "pinned $pinned of ${#tid[@]} vCPU threads"
exit 0
