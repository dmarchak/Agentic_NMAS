#!/bin/bash
# After a deploy, on the lab host (sudo): pin the kernel's kvm-pit threads to the switches' CPUs.
# containerlab's cpu-set (rcn-lab1.clab.yml) pins each node's qemu and its threads, which live in
# the container's cgroup; the kvm-pit threads that inject the vIOS switches' timer ticks are
# KERNEL threads (parent kthreadd, cgroup root), outside every container, so cpu-set cannot
# reach them (measured 2026-10-21). Only the switches' PIT threads tick (the C8000vs keep time
# with KVM's paravirtual clock), so all of them go to the switches' set: one shared set, no
# guess about which thread belongs to which switch.
# Revert: sudo taskset -pc 0-23 <tid> for each (or a redeploy, which makes new threads).
set -u
here=$(dirname "$(readlink -f "$0")")
. "$here/pinning.conf"
n=0
for t in $(ps -eLo tid,comm | awk '$2 ~ /^kvm-pit/ {print $1}'); do
  if sudo -n taskset -pc "$SWITCH_SET" "$t" >/dev/null; then n=$((n + 1));
  else echo "FAILED: kvm-pit thread $t could not be pinned"; fi
done
echo "pinned $n kvm-pit thread(s) to CPUs $SWITCH_SET"
[ "$n" -gt 0 ] || { echo "no kvm-pit thread found: is the lab deployed?"; exit 1; }
