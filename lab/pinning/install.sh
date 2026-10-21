#!/bin/bash
# Install the lab's kvm-pit pinning on the lab host, once (the operator runs it with sudo, from
# a copy of this folder): the scripts and their values into /usr/local/lib/lab-pinning/, the
# service and timer into /etc/systemd/system/, each file by name; the timer enabled and started;
# one run at once; then the check. Re-running it installs the same files again.
# Remove: systemctl disable --now lab-pin-pit.timer; rm the two units and the folder by name.
set -eu
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
src=$(dirname "$(readlink -f "$0")")
dst=/usr/local/lib/lab-pinning
install -d -m 0755 "$dst"
for f in pin-pit-threads.sh check-pinning.sh pinning-lib.sh; do
  install -m 0755 "$src/$f" "$dst/$f"
done
install -m 0644 "$src/pinning.conf" "$dst/pinning.conf"
for f in lab-pin-pit.service lab-pin-pit.timer; do
  install -m 0644 "$src/systemd/$f" "/etc/systemd/system/$f"
done
systemctl daemon-reload
systemctl enable --now lab-pin-pit.timer
systemctl start lab-pin-pit.service
echo "== the first run, from the journal:"
journalctl -t lab-pin-pit --since "-2 min" --no-pager -o cat | tail -20
echo "== the check:"
"$dst/check-pinning.sh" || true
